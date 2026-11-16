"""E01: durable control, bounded process lifecycle, wake handoff and release records."""
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate,coordinated
import ast
from contextlib import contextmanager
import json
from digital_life.domain.tool_learning_contract import loads as strict_json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from digital_life.domain.contracts import utc,identifier,dumps,sha,Forbidden,Conflict,ContractError,RuntimeIdentity
from digital_life.infrastructure.persistence.sqlite_store import PROJECT,RESOURCES

CONTROL_ID=1345335351

class Control:
    def __init__(self,root,instance_id):
        self.root=Path(root).resolve(); path=self.root/'control.sqlite'
        if path.exists():
            check=sqlite3.connect(str(path)); app=check.execute('PRAGMA application_id').fetchone()[0]; check.close()
            if app!=CONTROL_ID: raise ContractError('control schema mismatch; explicit migration required')
        else:
            db=sqlite3.connect(str(path)); db.executescript((RESOURCES/'supervisor.sql').read_text())
            db.execute('PRAGMA application_id='+str(CONTROL_ID)); db.commit(); db.close()
        self.db=sqlite3.connect(str(path),isolation_level=None); self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON'); self.instance=instance_id
        if not self.db.execute('SELECT id FROM instance_control_state WHERE instance_ref=?',(instance_id,)).fetchone():
            with self.tx(): self.insert('instance_control_state',instance_ref=instance_id,user_stopped=1)
    def close(self): self.db.close()
    @contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try: yield; self.db.execute('COMMIT')
        except BaseException: self.db.execute('ROLLBACK'); raise
    def insert(self,table,**fields):
        allowed={'instance_control_state','control_commands','wake_schedules','wake_firings','inbound_requests','control_sleep_handoffs','deployments','process_runs','wake_checks','release_switches','rollback_runs','backup_manifests'}
        if table not in allowed: raise ContractError('control table not allowed')
        fields.setdefault('id',identifier())
        values=[dumps(v) if isinstance(v,(dict,list)) else v for v in fields.values()]
        self.db.execute('INSERT INTO '+table+' ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',values)
        return fields['id']
    def state(self): return dict(self.db.execute('SELECT * FROM instance_control_state WHERE instance_ref=?',(self.instance,)).fetchone())
    def assert_startable(self):
        if (self.root/'MODEL_USAGE_REVIEW_REQUIRED').exists():raise Forbidden('model usage requires explicit review before restart')
        if (self.root/'WAKE_DISABLED').exists(): raise Forbidden('explicit user wake lock remains in place')
        if (self.root/'RESTORE_RECONCILIATION_REQUIRED').exists(): raise Forbidden('restored identity and external effects require reconciliation')
        if self.state()['user_stopped']: raise Forbidden('user stopped the instance')
    def command(self,kind,key,payload,authority='controller'):
        checksum=sha(dumps(payload))
        old=self.db.execute('SELECT * FROM control_commands WHERE instance_ref=? AND source=? AND command_key=?',(self.instance,authority,key)).fetchone()
        if old:
            if old['payload_hash']!=checksum: raise Conflict('control idempotency conflict')
            return old['id'],True
        return self.insert('control_commands',instance_ref=self.instance,source=authority,command_key=key,kind=kind,payload=payload,payload_hash=checksum,generation=payload.get('generation'),authority_kind=authority,authority_ref=authority,state='received',received_at=utc()),False
    @coordinated
    def stop(self,key):
        with self.tx():
            command,duplicate=self.command('stop',key,{})
            if not duplicate:
                self.db.execute('UPDATE instance_control_state SET user_stopped=1,control_revision=control_revision+1,last_stop_command_id=? WHERE instance_ref=?',(command,self.instance))
                self.db.execute("UPDATE control_commands SET state='succeeded',finished_at=? WHERE id=?",(utc(),command))
            return self.state()
    @coordinated
    def resume(self,key,expected_stop=None):
        if (self.root/'WAKE_DISABLED').exists(): raise Forbidden('wake lock must be explicitly removed by user; resume does not remove it')
        if (self.root/'RESTORE_RECONCILIATION_REQUIRED').exists(): raise Forbidden('restore reconciliation remains required')
        with self.tx():
            command,duplicate=self.command('resume',key,{'expected_stop':expected_stop} if expected_stop is not None else {})
            if not duplicate:
                if expected_stop is not None:
                    current=self.state()
                    if current['last_stop_command_id']!=expected_stop or not current['user_stopped'] or current['active_process_run_id']:raise Conflict('update stop superseded; resume cancelled')
                self.db.execute('UPDATE instance_control_state SET user_stopped=0,control_revision=control_revision+1 WHERE instance_ref=?',(self.instance,))
                self.db.execute("UPDATE control_commands SET state='succeeded',finished_at=? WHERE id=?",(utc(),command))
            return self.state()
    def set_wake(self,key,generation,due):
        if type(generation) is not int or generation<0: raise ContractError('invalid generation')
        with self.tx():
            command,duplicate=self.command('set_wake' if due else 'clear_wake',key,{'generation':generation,'due':due},authority='runtime-service')
            row=self.db.execute('SELECT * FROM wake_schedules WHERE instance_ref=?',(self.instance,)).fetchone()
            if duplicate: return {'generation':row['generation'] if row else None,'duplicate':True}
            if row and generation<=row['generation']:
                self.db.execute("UPDATE control_commands SET state='rejected',error_code='STALE_GENERATION',finished_at=? WHERE id=?",(utc(),command))
                return {'generation':row['generation'],'stale':True}
            if row: self.db.execute('UPDATE wake_schedules SET generation=?,next_due_at=?,enabled=?,last_control_command_id=?,updated_at=? WHERE id=?',(generation,due,int(due is not None),command,utc(),row['id']))
            else: self.insert('wake_schedules',instance_ref=self.instance,generation=generation,next_due_at=due,enabled=int(due is not None),last_control_command_id=command,updated_at=utc())
            self.db.execute("UPDATE control_commands SET state='succeeded',finished_at=? WHERE id=?",(utc(),command))
            return {'generation':generation,'applied':True,'command':command}
    def due_wakes(self):
        # Produces durable notifications only. Caller must separately authorize a process start.
        with self.tx():
            rows=self.db.execute('SELECT * FROM wake_schedules WHERE instance_ref=? AND enabled=1 AND next_due_at<=?',(self.instance,utc())).fetchall(); output=[]
            for row in rows:
                prior=self.db.execute('SELECT id FROM wake_firings WHERE schedule_id=? AND generation=? AND scheduled_due_at=?',(row['id'],row['generation'],row['next_due_at'])).fetchone()
                if prior: continue
                suppressed=self.state()['user_stopped'] or (self.root/'WAKE_DISABLED').exists()
                ref=self.insert('wake_firings',schedule_id=row['id'],generation=row['generation'],scheduled_due_at=row['next_due_at'],fired_at=utc(),source_event_id=identifier(),state='suppressed' if suppressed else 'pending',suppression_reason='user-control' if suppressed else None)
                output.append(ref)
            return output
    def accept_inbound(self,source,key,payload,authority):
        from digital_life.domain.contracts import text
        text(source,120); text(key,240)
        if not isinstance(payload,dict) or set(payload)!={'text'}: raise ContractError('invalid inbound envelope')
        text(payload['text'])
        raw=dumps(payload); checksum=sha(raw)
        folder=self.root/'inbound'; folder.mkdir(exist_ok=True)
        with self.tx():
            prior=self.db.execute('SELECT * FROM inbound_requests WHERE instance_ref=? AND source=? AND source_event_id=?',(self.instance,source,key)).fetchone()
            if prior:
                if prior['payload_hash']!=checksum: raise Conflict('inbound key mismatch')
                return prior['id']
            path=folder/checksum
            if not path.exists():
                with path.open('x') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            return self.insert('inbound_requests',instance_ref=self.instance,source=source,source_event_id=key,request_kind='task',payload_path=checksum,payload_hash=checksum,authority_ref=authority,received_at=utc(),expires_at=utc(86400),retention_class='until-transferred',state='received')
    def transfer_inbound(self,store):
        from digital_life.application.runtime.engine import Engine
        transferred=[]
        for row in self.db.execute("SELECT * FROM inbound_requests WHERE instance_ref=? AND state IN ('received','transferring') ORDER BY received_at",(self.instance,)).fetchall():
            if row['expires_at']<=utc():
                with self.tx(): self.db.execute("UPDATE inbound_requests SET state='expired' WHERE id=?",(row['id'],))
                continue
            path=self.root/'inbound'/row['payload_path']
            if path.is_symlink() or path.parent!=self.root/'inbound': raise Forbidden('invalid inbound payload path')
            raw=path.read_text()
            if sha(raw)!=row['payload_hash']: raise ContractError('inbound payload changed')
            activity=Engine(store).submit(json.loads(raw)['text'],row['source_event_id'],row['source'])
            event=store.db.execute("SELECT id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='activity.created'",(store.instance_id,activity)).fetchone()
            if not event: raise ContractError('runtime input acknowledgement missing')
            with self.tx(): self.db.execute("UPDATE inbound_requests SET state='delivered',runtime_ack_event_id=?,delivered_at=? WHERE id=?",(event['id'],utc(),row['id']))
            transferred.append(activity)
        return transferred
    def prepare_sleep(self,store,identity):
        if identity.epoch!=self.state()['runtime_epoch']: raise Conflict('runtime epoch changed')
        with store.tx():
            ready=store.db.execute("SELECT count(*) FROM jobs WHERE instance_id=? AND state IN ('queued','leased') AND due_at<=?",(store.instance_id,utc())).fetchone()[0]
            unknown=store.db.execute("SELECT count(*) FROM action_intents WHERE instance_id=? AND state IN ('running','dispatching','unknown')",(store.instance_id,)).fetchone()[0]
            if ready or unknown: raise Conflict('work or external effects unresolved')
            epoch=store.rows('instance_wake_state')[0]
            due=store.db.execute("SELECT min(due_at) FROM jobs WHERE instance_id=? AND state='queued'",(store.instance_id,)).fetchone()[0]
            generation=epoch['desired_generation']+1
            command=store.insert('supervisor_commands',command_key=identifier(),kind='set_wake' if due else 'clear_wake',schedule_generation=generation,payload={'due':due},payload_hash=sha(dumps({'due':due})),state='pending',next_attempt_at=utc(),runtime_epoch=identity.epoch,process_run_id=identity.process_id)
            store.db.execute('UPDATE instance_wake_state SET desired_generation=?,desired_due_at=? WHERE id=?',(generation,due,epoch['id']))
        ack=self.set_wake(command,generation,due)
        if not ack.get('applied'): raise Conflict('wake handoff not accepted')
        with store.tx():
            ready=store.db.execute("SELECT count(*) FROM jobs WHERE instance_id=? AND state IN ('queued','leased') AND due_at<=?",(store.instance_id,utc())).fetchone()[0]
            if ready: raise Conflict('new work arrived during sleep handoff')
            store.db.execute("UPDATE supervisor_commands SET state='acknowledged',ack_control_command_id=?,acknowledged_at=? WHERE id=?",(ack['command'],utc(),command))
            store.db.execute('UPDATE instance_wake_state SET acknowledged_generation=?,acknowledged_due_at=? WHERE id=?',(generation,due,epoch['id']))
        seq=store.db.execute('SELECT coalesce(max(event_seq),0) FROM runtime_events').fetchone()[0]
        with self.tx(): return self.insert('control_sleep_handoffs',instance_ref=self.instance,runtime_epoch=identity.epoch,process_run_id=identity.process_id,sleep_generation=generation,wake_generation=generation,state_manifest_hash=sha(dumps({'event_seq':seq,'generation':generation})),phase='prepared',last_runtime_event_seq=seq)
    def commit_sleep(self,store,handoff):
        with self.tx():
            row=self.db.execute('SELECT * FROM control_sleep_handoffs WHERE id=? AND instance_ref=?',(handoff,self.instance)).fetchone()
            if not row or row['phase']!='prepared': raise Conflict('sleep handoff not prepared')
            with store.tx():
                seq=store.db.execute('SELECT coalesce(max(event_seq),0) FROM runtime_events').fetchone()[0]
                ready=store.db.execute("SELECT count(*) FROM jobs WHERE instance_id=? AND state IN ('queued','leased') AND due_at<=?",(store.instance_id,utc())).fetchone()[0]
                inbound=self.db.execute("SELECT count(*) FROM inbound_requests WHERE instance_ref=? AND state IN ('received','transferring','waking')",(self.instance,)).fetchone()[0]
                changed=ready or inbound or seq!=row['last_runtime_event_seq'] or self.state()['runtime_epoch']!=row['runtime_epoch']
                phase='aborted' if changed else 'committed'
                self.db.execute('UPDATE control_sleep_handoffs SET phase=?,reason=? WHERE id=?',(phase,'new-input-or-work' if changed else None,handoff))
                return {'phase':phase,'handoff':handoff}
    def begin_run(self,deployment):
        self.assert_startable()
        with self.tx():
            release=self.db.execute("SELECT * FROM deployments WHERE id=? AND state='active'",(deployment,)).fetchone()
            if not release: raise Forbidden('runtime requires an active verified deployment')
            state=self.state()
            if state['active_process_run_id']:
                row=self.db.execute('SELECT * FROM process_runs WHERE id=?',(state['active_process_run_id'],)).fetchone()
                if row and row['exited_at'] is None: raise Conflict('active run already registered; explicit reconcile required')
            epoch=state['runtime_epoch']+1
            ref=self.insert('process_runs',deployment_id=deployment,instance_ref=self.instance,pid=os.getpid(),started_at=utc(),user_stopped=0)
            self.db.execute('UPDATE instance_control_state SET runtime_epoch=?,active_process_run_id=?,control_revision=control_revision+1 WHERE instance_ref=?',(epoch,ref,self.instance))
            return RuntimeIdentity(epoch,ref)
    def finish_run(self,identity):
        with self.tx():
            self.db.execute('UPDATE process_runs SET exited_at=? WHERE id=?',(utc(),identity.process_id))
            self.db.execute('UPDATE instance_control_state SET active_process_run_id=NULL WHERE instance_ref=? AND active_process_run_id=?',(self.instance,identity.process_id))

class Releases:
    def __init__(self,control): self.c=control
    def stage(self,source):
        source=Path(source).resolve()
        if not source.is_dir() or not (source/'digital_life').is_dir(): raise ContractError('release must contain digital_life package')
        compatibility=source/'digital_life/resources/release.json'
        from digital_life.application.learning.bridge import declaration,source_files,baseline_candidate,register_baseline
        bounds=declaration(strict_json(compatibility.read_text()) if compatibility.is_file() else {'schema_min':2,'schema_max':2})
        files=source_files(source)
        manifest={str(path):sha(raw) for path,raw in files}; checksum=sha(dumps(manifest)); destination=self.c.root/'releases'/checksum
        if (self.c.root/'releases').is_symlink() or destination.is_symlink():raise Forbidden('release directory symlink')
        if not destination.exists():
            import tempfile
            destination.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='stage-',dir=destination.parent) as temp:
                pending=Path(temp)/'release';pending.mkdir()
                for relative,raw in files:
                    target=pending/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                (pending/'manifest.json').write_text(dumps(manifest))
                try:pending.rename(destination)
                except FileExistsError:pass
        self.verify_path(destination,checksum)
        proof=baseline_candidate(source,manifest,bounds)
        register_baseline(self.c,checksum,proof)
        with self.c.tx():
            return self.c.insert('deployments',release=checksum,build_hash=checksum,schema_min=bounds['schema_min'],schema_max=bounds['schema_max'],state='candidate')
    @staticmethod
    def verify_path(path,checksum):
        path=Path(path)
        if path.is_symlink() or path.parent.is_symlink() or not path.is_dir():raise Forbidden('release path invalid')
        manifest_file=path/'manifest.json'
        if manifest_file.is_symlink():raise Forbidden('release manifest symlink')
        manifest=strict_json(manifest_file.read_text())
        if not isinstance(manifest,dict) or sha(dumps(manifest))!=checksum:raise ContractError('release manifest integrity failure')
        actual=set()
        for file in path.rglob('*'):
            if file.is_symlink():raise Forbidden('release contains symlink')
            if file.is_file() and file!=manifest_file:actual.add(str(file.relative_to(path)))
        if actual!=set(manifest):raise ContractError('release file set mismatch')
        for name,digest in manifest.items():
            relative=Path(name)
            if relative.is_absolute() or '..' in relative.parts or not isinstance(digest,str):raise ContractError('invalid release manifest path')
            file=path/relative
            if sha(file.read_bytes())!=digest:raise ContractError('release integrity failure')
        return path
    def verify(self,deployment):
        row=self.c.db.execute('SELECT * FROM deployments WHERE id=?',(deployment,)).fetchone()
        if not row:raise ContractError('deployment missing')
        if row['release']!=row['build_hash'] or Path(row['release']).name!=row['release']:raise ContractError('invalid release hash')
        path=self.verify_path(self.c.root/'releases'/row['release'],row['build_hash'])
        declaration=path/'digital_life/resources/release.json'
        bounds=strict_json(declaration.read_text()) if declaration.is_file() else {'schema_min':2,'schema_max':2}
        if any(bounds.get(k)!=row[k] for k in ('schema_min','schema_max')):raise ContractError('release compatibility metadata mismatch')
        from digital_life.application.learning.bridge import declaration,verified_baseline
        if row['schema_max']==4:verified_baseline(self.c,row,strict_json((path/'manifest.json').read_text()),bounds)
        else:declaration(bounds)
        return path
    def compatible(self,deployment):
        row=self.c.db.execute('SELECT schema_min,schema_max FROM deployments WHERE id=?',(deployment,)).fetchone()
        if not row:return False
        db=sqlite3.connect((self.c.root/'runtime.sqlite').as_uri()+'?mode=ro',uri=True)
        try:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            from digital_life.application.learning.bridge import verify_schema4_layout,protected_storage_required
            protected=protected_storage_required(db,self.c)
            if protected:
                if row['schema_max']!=4:return False
                try:verify_schema4_layout(db)
                except ContractError:return False
        finally:db.close()
        if not row['schema_min']<=version<=row['schema_max']:return False
        if protected:
            try:self.verify(deployment)
            except (ContractError,OSError,ValueError):return False
        return True
    def recoverable(self,deployment):
        try:self.verify(deployment);return self.compatible(deployment)
        except (ContractError,OSError,ValueError):return False
    def activate(self,deployment,verify):
        # Verifier is an explicit dependency; syntax checks alone cannot certify wake/readiness.
        row=self.c.db.execute('SELECT * FROM deployments WHERE id=?',(deployment,)).fetchone()
        if not row: raise ContractError('deployment missing')
        active=self.c.db.execute("SELECT * FROM deployments WHERE state='active'").fetchone()
        if self.c.state()['active_process_run_id']: raise Conflict('cannot switch during active run')
        with self.c.tx(): switch=self.c.insert('release_switches',old_deployment_id=active['id'] if active else None,new_deployment_id=deployment,phase='prepared',evidence={})
        try:
            path=self.verify(deployment)
            if not self.compatible(deployment):raise ContractError('release incompatible with current database schema')
            evidence=verify(path)
            if evidence.get('ready') is not True or evidence.get('schema_compatible') is not True: raise ContractError('release verification failed')
            if 'handshake' in evidence:
                from digital_life.application.learning.bridge import verify_handshake
                verify_handshake(self.c,deployment,evidence['handshake'],stage='prepared')
            else:
                db=sqlite3.connect((self.c.root/'runtime.sqlite').as_uri()+'?mode=ro',uri=True)
                try:
                    from digital_life.application.learning.bridge import protected_storage_required
                    protected=protected_storage_required(db,self.c)
                finally:db.close()
                if protected:raise Forbidden('protected storage requires the actual loaded runtime capability handshake')
        except Exception as error:
            with self.c.tx():
                self.c.db.execute("UPDATE deployments SET state='failed' WHERE id=?",(deployment,))
                self.c.db.execute("UPDATE release_switches SET phase='failed',evidence=? WHERE id=?",(dumps({'error':str(error)}),switch))
                compatible=bool(active and active['id']!=deployment and self.recoverable(active['id']))
                if active:
                    self.c.insert('rollback_runs',switch_id=switch,target_deployment_id=active['id'],reason=str(error),compatibility_result='pass' if compatible else 'fail',result='succeeded' if compatible else 'failed')
                    if not compatible:self.c.db.execute("UPDATE deployments SET state='retired' WHERE id=?",(active['id'],))
            return {'switched':False,'retained':active['id'] if compatible else None}
        with self.c.tx():
            self.c.db.execute("UPDATE deployments SET state='retired' WHERE state='active'")
            self.c.db.execute("UPDATE deployments SET state='active' WHERE id=?",(deployment,))
            self.c.db.execute("UPDATE release_switches SET phase='verified',evidence=? WHERE id=?",(dumps(evidence),switch))
        return {'switched':True,'deployment':deployment}
