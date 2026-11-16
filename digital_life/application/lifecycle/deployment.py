"""Versioned process deployment and explicit watchdog. No import-time startup."""
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import time
from digital_life.domain.contracts import identifier,utc,Conflict,ContractError,Forbidden
from digital_life.application.lifecycle.control_plane import Releases

class ProcessDriver:
    def launch(self,path,root,deployment,ready,gate):
        env=dict(os.environ); env['PYTHONPATH']=str(path); env['PYTHONDONTWRITEBYTECODE']='1'
        log=(ready.parent/'runtime.log').open('ab')
        try:
            return subprocess.Popen([sys.executable,'-m','digital_life.entrypoints.runtime',
                '--data',str(root),'--deployment',deployment,'--ready',str(ready),'--gate',str(gate)],
                cwd=str(path),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
        finally: log.close()
    def await_state(self,process,ready,desired,timeout):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if process.poll() is not None: raise ContractError('runtime exited before '+desired)
            try:
                from digital_life.application.learning.bridge import read_readiness
                value=read_readiness(ready)
                if value.get('state')==desired: return value
            except (FileNotFoundError,ValueError): pass
            time.sleep(0.05)
        raise ContractError('runtime readiness timeout: '+desired)
    def await_deployment_thought(self,process,ready,root,deployment,nonce,timeout):
        from digital_life.application.learning.bridge import read_readiness
        from digital_life.application.lifecycle.deployment_thought import verify
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            response=read_readiness(ready);proof=response.get('deployment_acceptance',{})
            if proof.get('state')=='passed':
                if process.poll() is not None:raise ContractError('runtime exited after deployment thought')
                verify(root,deployment,proof,nonce)
                return response
            if proof.get('state')=='failed':raise ContractError('deployment independent thought failed: '+proof.get('error','unknown'))
            if process.poll() is not None:raise ContractError('runtime exited before independent thought acceptance')
            time.sleep(.1)
        raise ContractError('deployment independent thought timed out')
    def confirm_stability(self,process,ready,seconds=0.5):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if process.poll() is not None: raise ContractError('runtime exited during readiness stability window')
            time.sleep(0.05)
    def stop(self,process):
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)

class Deployment:
    def __init__(self,control,driver=None):
        self.c=control; self.driver=driver or ProcessDriver(); self.active=None
    def launch(self,deployment,timeout=30,_recover=True):
        from digital_life.infrastructure.processes.locks import exclusive
        with exclusive(self.c.root,'deployment.lock'):
            return self._launch(deployment,timeout,_recover)
    def _launch(self,deployment,timeout,recover):
        self.c.assert_startable()
        if self.c.state()['active_process_run_id']: raise Conflict('stop existing runtime before deploying')
        old=self.c.db.execute("SELECT * FROM deployments WHERE state='active'").fetchone()
        row=self.c.db.execute('SELECT * FROM deployments WHERE id=?',(deployment,)).fetchone()
        if not row: raise ContractError('deployment missing')
        if row['state'] not in ('active','retired'):
            from digital_life.infrastructure.persistence.sqlite_store import Store
            from digital_life.application.lifecycle.source_updates import SourceUpdates
            store=Store(self.c.root)
            try:SourceUpdates(store).assert_deployable(deployment)
            finally:store.close()
        from digital_life.application.lifecycle.process_checkpoints import ProcessCheckpoints
        checkpoints=ProcessCheckpoints(self.c);checkpoint=None
        if checkpoints.config().get('enabled') and old and old['id']!=deployment:
            checkpoint=checkpoints.capture(old['id'],target=deployment,reason='before-deployment')
        session=self.c.root/'launches'/identifier(); session.mkdir(parents=True)
        ready=session/'ready.json'; gate=session/'activate'; process=None
        gate_config=checkpoints.config();verify_thought=bool(gate_config.get('enabled') and gate_config.get('verify_thought') and recover)
        challenge={'nonce':identifier(),'deployment':deployment,'mode':'required' if recover else 'skip-rollback'}
        (session/'probe-challenge.json').write_text(json.dumps(challenge));os.chmod(session/'probe-challenge.json',0o600)
        def verify(path):
            nonlocal process
            process=self.driver.launch(path,self.c.root,deployment,ready,gate)
            response=self.driver.await_state(process,ready,'prepared',timeout)
            if response.get('deployment')!=deployment: raise ContractError('wrong deployment readiness')
            if isinstance(response.get('capability'),dict) and response['capability'].get('qualified_plane_required') is True and response.get('pid')!=getattr(process,'pid',None):raise ContractError('prepared runtime PID does not match owned process')
            return {'ready':True,'schema_compatible':response.get('schema_compatible') is True,'handshake':response}
        result=Releases(self.c).activate(deployment,verify)
        if not result['switched']:
            if process: self.driver.stop(process)
            if old and recover and old['id']!=deployment:
                if not Releases(self.c).recoverable(old['id']):
                    with self.c.tx():self.c.db.execute("UPDATE deployments SET state='retired' WHERE id=?",(old['id'],))
                    return dict(result,retained=None,restarted=False,error='previous release incompatible; no restart')
                try:
                    if checkpoints.config().get('enabled'):checkpoints.reconcile_uncertain()
                    restore=self._launch(old['id'],timeout,False)
                    result['restarted']=restore.get('switched') is True
                except Exception: result['restarted']=False
            if checkpoint:
                result['checkpoint']=checkpoint['id']
                checkpoints.rollback_record(deployment,old['id'],result.get('restarted',False))
            return result
        try:
            self.c.assert_startable()
            if checkpoints.config().get('enabled'):checkpoints.version(deployment)
            gate.write_text(deployment)
            response=self.driver.await_state(process,ready,'running',timeout)
            if response.get('deployment')!=deployment: raise ContractError('wrong running deployment')
            from digital_life.application.learning.bridge import verify_handshake
            verify_handshake(self.c,deployment,response,stage='running')
            if isinstance(response.get('capability'),dict) and response['capability'].get('qualified_plane_required') is True and response.get('pid')!=getattr(process,'pid',None):raise ContractError('running PID differs from owned process')
            if verify_thought:
                if not hasattr(self.driver,'await_deployment_thought'):raise ContractError('driver lacks deployment thought verification')
                response=self.driver.await_deployment_thought(process,ready,self.c.root,deployment,challenge['nonce'],gate_config.get('thought_timeout',180))
                proof=response['deployment_acceptance']
                state=self.c.state()
                if state['active_process_run_id']!=proof['process_run_id'] or state['runtime_epoch']!=proof['runtime_epoch']:raise ContractError('deployment proof is from another process run')
                checks={'deployment':deployment,'passed':True,'request':proof['request'],'result':proof['result'],'nonce':challenge['nonce'],'inference_calls':1}
                checkpoints.record('deployment_thought',deployment,checks)
            if hasattr(self.driver,'confirm_stability'): self.driver.confirm_stability(process,ready)
            if verify_thought:(session/'admitted').write_text(deployment)
            self.active={'process':process,'ready':ready,'deployment':deployment,'old':dict(old) if old and old['id']!=deployment else None,'checkpoint':checkpoint['id'] if checkpoint else None}
            return {'switched':True,'deployment':deployment,'pid':getattr(process,'pid',None),'handshake':response,'checkpoint':checkpoint['id'] if checkpoint else None}
        except Exception as error:
            if process: self.driver.stop(process)
            try:self.c.assert_startable()
            except Forbidden:
                self.active=None
                return {'switched':False,'user_stopped':True,'rollback':False,'restarted':False}
            return self._rollback(deployment,dict(old) if old and old['id']!=deployment else None,str(error),timeout,recover)
    def _rollback(self,deployment,old,reason,timeout,recover=True):
        compatible=bool(old and Releases(self.c).recoverable(old['id']))
        with self.c.tx():
            state=self.c.state()
            if state['active_process_run_id']:
                self.c.db.execute('UPDATE process_runs SET exited_at=? WHERE id=?',(utc(),state['active_process_run_id']))
                self.c.db.execute('UPDATE instance_control_state SET active_process_run_id=NULL WHERE instance_ref=?',(self.c.instance,))
            self.c.db.execute("UPDATE deployments SET state='failed' WHERE id=?",(deployment,))
            if old:self.c.db.execute("UPDATE deployments SET state=? WHERE id=?",('active' if compatible else 'retired',old['id']))
            switch=self.c.db.execute('SELECT id FROM release_switches WHERE new_deployment_id=? ORDER BY rowid DESC LIMIT 1',(deployment,)).fetchone()
            rollback=self.c.insert('rollback_runs',switch_id=switch['id'],target_deployment_id=old['id'] if old else deployment,
                reason=reason,compatibility_result='pass' if compatible else 'fail',result='pending')
        from digital_life.application.lifecycle.process_checkpoints import ProcessCheckpoints
        checkpoints=ProcessCheckpoints(self.c);reconciliation=None
        if checkpoints.config().get('enabled'):reconciliation=checkpoints.reconcile_uncertain()
        restarted=False; self.active=None
        if old and compatible and recover:
            try: restarted=self._launch(old['id'],timeout,False).get('switched') is True
            except Exception: pass
        with self.c.tx():
            self.c.db.execute('UPDATE rollback_runs SET result=? WHERE id=?',('succeeded' if restarted else 'failed',rollback))
        result={'switched':False,'retained':old['id'] if compatible else None,'restarted':restarted,'error':reason,'rollback':rollback}
        if checkpoints.config().get('enabled'):
            result['reconciliation']=reconciliation
            result['process_recovery']=checkpoints.rollback_record(deployment,old['id'] if old else None,restarted)
        return result
    def check(self,heartbeat_timeout=180,timeout=30):
        """One watchdog iteration, owned process only; user stop never triggers rollback."""
        if not self.active: return {'state':'not_running'}
        active=self.active; process=active['process']
        try: self.c.assert_startable()
        except Forbidden:
            self.driver.stop(process); self.active=None
            return {'state':'user_stopped','rollback':False}
        reason=None
        if process.poll() is not None: reason='runtime-exited'
        else:
            try:
                age=time.time()-active['ready'].stat().st_mtime
                if age < -1:reason='heartbeat-clock-invalid'
                elif age>heartbeat_timeout: reason='heartbeat-expired'
                else:
                    from digital_life.application.learning.bridge import read_readiness
                    heartbeat=read_readiness(active['ready'])
                    if not isinstance(heartbeat,dict):raise ContractError('heartbeat must be an object')
                    if heartbeat.get('state')!='running':reason='heartbeat-state-invalid'
                    else:
                        from digital_life.application.learning.bridge import verify_handshake
                        verify_handshake(self.c,active['deployment'],heartbeat,stage='running')
                        if isinstance(heartbeat.get('capability'),dict) and heartbeat['capability'].get('qualified_plane_required') is True and heartbeat.get('pid')!=getattr(process,'pid',None):raise ContractError('heartbeat PID differs from owned process')
            except sqlite3.OperationalError as error:
                if str(error).lower() not in ('database is locked','database table is locked','database schema is locked'):raise
                # A busy read cannot certify a handshake, but is not process death.
                # Keep the existing deadline and retry; never accept stale readiness.
                since=active.setdefault('verification_pending_since',time.monotonic())
                if time.monotonic()-since>=heartbeat_timeout:reason='heartbeat-verification-timeout'
                else:
                    status={'state':'verification_pending','deployment':active['deployment'],'reason':'database-busy','elapsed_seconds':time.monotonic()-since}
                    diagnostic=active['ready'].parent/'watchdog-busy.json'
                    temporary=diagnostic.with_suffix('.tmp');temporary.write_text(json.dumps(status));os.replace(temporary,diagnostic)
                    return status
            except FileNotFoundError: reason='heartbeat-missing'
            except (ContractError,ValueError,OSError): reason='heartbeat-capability-invalid'
        if reason:
            self.driver.stop(process)
            from digital_life.infrastructure.processes.locks import exclusive
            with exclusive(self.c.root,'deployment.lock'):
                result=self._rollback(active['deployment'],active['old'],reason,timeout)
            return dict(result,state='recovered' if result['restarted'] else 'failed')
        active.pop('verification_pending_since',None)
        return {'state':'running','deployment':active['deployment']}
    def supervise(self,seconds=None,interval=0.25):
        """Explicit foreground owner. It never installs an OS background service."""
        start=time.monotonic()
        try:
            while seconds is None or time.monotonic()-start<seconds:
                result=self.check()
                if result['state'] in ('failed','not_running','user_stopped'): return result
                time.sleep(interval)
            return {'state':'monitor_window_completed'}
        except KeyboardInterrupt:
            self.c.stop(identifier())
            return {'state':'user_stopped','rollback':False}
        finally:
            if self.active: self.driver.stop(self.active['process']); self.active=None
