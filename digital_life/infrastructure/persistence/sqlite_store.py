"""M17: full-schema storage, atomic commands, artifacts, initialization and snapshots."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import stat
import hashlib
from digital_life.domain.contracts import identifier,utc,dumps,sha,Conflict,ContractError
from digital_life.infrastructure.persistence.sqlite_write_monitor import ManagedConnection,managed_connection_factory,callback_active

PACKAGE_ROOT=Path(__file__).resolve().parents[2]
PROJECT=PACKAGE_ROOT.parent
RESOURCES=PACKAGE_ROOT/'resources'
APPLICATION_ID=1345335350
_INPUT_COLUMNS=('request_ref_id','source_ref_id','source_epoch','source_revision_ref_id','field_path','purpose',
    'recipient_ref_id','body_digest','retention_state','row_revision','id','instance_id')
_INPUT_SQL='INSERT INTO tl_input_dependency ('+','.join(_INPUT_COLUMNS)+') VALUES ('+','.join('?'for _ in _INPUT_COLUMNS)+')'
_INPUT_SCHEMA_QUERY="SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name IN ('tl_input_dependency','object_registry') ORDER BY type,name"
_INPUT_TEMP_QUERY="SELECT type,name,tbl_name,sql FROM sqlite_temp_master WHERE tbl_name IN ('tl_input_dependency','object_registry') ORDER BY type,name"
# Generated from the reviewed runtime.sql + tool_learning_v1.sql schema on a
# fresh empty SQLite database. Includes both tables, all indexes and triggers.
_INPUT_SCHEMA_DIGEST='1690f9bffed11b05738e491a621da4a50913e41694e846b4c7895878145d007d'


def managed_database(connection):
    from digital_life.infrastructure.persistence.tool_learning_meter import _Connection
    if type(connection)is _Connection:connection=connection.actual
    return connection if type(connection)is ManagedConnection else None

class Store:
    def __init__(self,root):
        self.root=Path(root).resolve(); path=self.root/'runtime.sqlite'
        if not path.is_file() or path.is_symlink(): raise ContractError('full runtime database not prepared')
        self.db=sqlite3.connect(str(path),isolation_level=None,timeout=5,factory=managed_connection_factory)
        self._input_contract_cache=None
        self._file_signature_stats={'minted':0,'hits':0}
        self._graph_material_stats={'eligible':0,'stored':0,'returned':0,'used':0}
        self._input_certificate_stats={'attempted':0,'issued':0,'accepted':0,'fallback':0,'committed':0,'strong_material_accepted':0,'strong_material_committed':0}
        self.db.row_factory=sqlite3.Row
        if self.db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID:
            self.db.close(); raise ContractError('database belongs to another runtime; automatic migration refused')
        self.db.execute('PRAGMA foreign_keys=ON'); self.db.execute('PRAGMA busy_timeout=15000')
        self.db.execute('PRAGMA synchronous=FULL'); self.depth=0;self._blob_frames=[]
        row=self.db.execute('SELECT id FROM identity_instances').fetchone()
        self.instance_id=row[0] if row else None
        self.columns={r[0]:{c[1] for c in self.db.execute('PRAGMA table_info('+r[0]+')')} for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}
    def _approved_input_contract(self,managed):
        state=managed.monitor_state()
        if not state['can_certify']:return None
        version=self.db.execute('PRAGMA data_version').fetchone()[0]
        key=(state['configuration'],state['schema_epoch'],version)
        prior=self._input_contract_cache
        if prior is not None and prior[0]==key:return prior[1]
        rows=[list(row)for row in self.db.execute(_INPUT_SCHEMA_QUERY)]
        if hashlib.sha256(dumps(rows).encode()).hexdigest()!=_INPUT_SCHEMA_DIGEST:return None
        if self.db.execute(_INPUT_TEMP_QUERY).fetchone()is not None:return None
        after=managed.monitor_state()
        if (state['configuration'],state['schema_epoch'])!=(after['configuration'],after['schema_epoch']):return None
        try:contract=managed.bind_insert(_INPUT_SQL,'tl_input_dependency',frozenset((('main','tl_input_dependency'),('main','object_registry'))),_INPUT_SCHEMA_DIGEST)
        except ValueError:return None
        self._input_contract_cache=(key,contract)
        return contract
    def _insert_input_registration(self,fields):
        from digital_life.infrastructure.persistence.tool_learning_meter import _ACTIVE
        from digital_life.infrastructure.persistence.tool_learning_readset import current_readset
        fields=dict(fields);fields.setdefault('id',identifier());fields['instance_id']=self.instance_id
        if set(fields)!=set(_INPUT_COLUMNS):raise ContractError('fixed input registration fields required')
        parameters=tuple(fields[column]for column in _INPUT_COLUMNS)
        stats=self._input_certificate_stats;stats['attempted']+=1
        phase=current_readset(self);managed=managed_database(self.db);meter=_ACTIVE.get()
        eligible=(not callback_active() and phase is not None and managed is not None
                  and meter is not None and getattr(meter,'row_observer',None)is None
                  and managed.monitor_state()['can_certify']
                  and not any((type(value),sqlite3.PrepareProtocol)in sqlite3.adapters for value in parameters))
        contract=None
        if eligible:
            phase.checkpoint();contract=self._approved_input_contract(managed)
        if contract is None:
            stats['fallback']+=1;self.db.execute(_INPUT_SQL,parameters)
            return fields['id']
        _,receipt=managed.certified_insert(contract,parameters,phase.stamp)
        if receipt is None:stats['fallback']+=1;phase.checkpoint()
        else:
            stats['issued']+=1
            if phase.accept_input_receipt(managed,receipt):stats['accepted']+=1
            else:stats['fallback']+=1;phase.checkpoint()
        return fields['id']
    def close(self):
        control=getattr(self,'_control_reader',None)
        if control is not None:control.close();self._control_reader=None
        self.db.close()
    def control_reader(self):
        path=self.root/'control.sqlite'
        info=path.lstat()
        if stat.S_ISLNK(info.st_mode):raise ContractError('control database cannot be a symlink')
        key=(info.st_dev,info.st_ino)
        if getattr(self,'_control_reader_key',None)!=key or getattr(self,'_control_reader',None) is None:
            previous=getattr(self,'_control_reader',None)
            if previous is not None:previous.close()
            self._control_reader=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None);self._control_reader.row_factory=sqlite3.Row;self._control_reader_key=key
            if self._control_reader.execute('PRAGMA application_id').fetchone()[0]!=1345335351:raise ContractError('invalid control database identity')
        return self._control_reader
    def assert_execution_allowed(self):
        from digital_life.domain.contracts import Forbidden
        if (self.root/'MODEL_USAGE_REVIEW_REQUIRED').exists():raise Forbidden('model usage requires explicit review before further inference')
        if (self.root/'WAKE_DISABLED').exists():raise Forbidden('user disabled wake')
        if (self.root/'RESTORE_RECONCILIATION_REQUIRED').exists():raise Forbidden('restore must reconcile identity and external effects')
        if (self.root/'control.sqlite').exists():
            state=self.control_reader().execute('SELECT user_stopped FROM instance_control_state WHERE instance_ref=?',(self.instance_id,)).fetchone()
            if state and state[0]:raise Forbidden('user stopped runtime')
    @classmethod
    def prepare(cls,root,name='原初00',model_config=None):
        root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
        if root.is_symlink(): raise ContractError('root must be a real directory')
        path=root/'runtime.sqlite'
        if path.exists():
            existing=cls(root)
            if existing.instance_id is None: existing.bootstrap(name,model_config)
            return existing
        db=sqlite3.connect(str(path))
        try:
            db.executescript((RESOURCES/'runtime.sql').read_text())
            db.execute('PRAGMA application_id='+str(APPLICATION_ID)); db.execute('PRAGMA user_version=2'); db.commit()
        finally: db.close()
        for directory in ('blobs','workspace','snapshots'): (root/directory).mkdir(exist_ok=True)
        (root/'WAKE_DISABLED').write_text('Explicit user authorization is required before running this instance.\n')
        store=cls(root); store.bootstrap(name,model_config); return store
    @contextmanager
    def tx(self):
        level=self.depth
        from digital_life.infrastructure.persistence.tool_learning_readset import checkpoint
        checkpoint(self)
        self.db.execute('BEGIN IMMEDIATE' if level==0 else 'SAVEPOINT uow_'+str(level))
        self.depth+=1;self._blob_frames.append([]);committing=False;uncertain=False;rolled_back=False
        try:
            yield self
            committing=True
            if level==0:
                from digital_life.infrastructure.persistence.tool_learning_readset import before_transaction_commit
                before_transaction_commit(self)
            self.db.execute('COMMIT' if level==0 else 'RELEASE uow_'+str(level))
        except BaseException:
            uncertain=committing
            try:
                if self.db.in_transaction:
                    self.db.execute('ROLLBACK' if level==0 else 'ROLLBACK TO uow_'+str(level));rolled_back=True
                    if level:self.db.execute('RELEASE uow_'+str(level))
            except BaseException:
                uncertain=True;raise
            raise
        finally:
            self.depth-=1;created=self._blob_frames.pop()
            if level:
                from digital_life.infrastructure.persistence.tool_learning_readset import savepoint_rolled_back,abandon_transaction_boundary
                if uncertain:abandon_transaction_boundary(self)
                elif rolled_back:savepoint_rolled_back(self)
            if level==0:
                from digital_life.infrastructure.persistence.tool_learning_readset import transaction_ended,abandon_transaction_boundary
                import sys
                if uncertain:abandon_transaction_boundary(self)
                elif sys.exc_info()[0] is None:
                    try:transaction_ended(self,rolled_back=rolled_back)
                    except BaseException:abandon_transaction_boundary(self);raise
                else:
                    try:transaction_ended(self,rolled_back=rolled_back)
                    except BaseException:abandon_transaction_boundary(self)
            # Never acquire the process gate while an outer SQLite writer is
            # held. Nested rollback files are reconciled after the outer end,
            # including an outer success; unknown commit files remain intact.
            if not uncertain:
                if self._blob_frames:self._blob_frames[-1].extend(created)
                else:self._discard_unregistered_blobs(created)
            if level==0:
                import sys
                if sys.exc_info()[0] is None:checkpoint(self)
    def _discard_unregistered_blobs(self,created):
        try:return self._discard_unregistered_blobs_guarded(created)
        except Exception:return None  # Unknown gate/DB/filesystem status retains files.
    def _discard_unregistered_blobs_guarded(self,created):
        # Only our exact new regular inode, with no reference from ANY instance
        # sharing this blob root, may be unlinked. A fresh exclusive writer
        # boundary prevents a new reference between that proof and unlink.
        if not created:return
        db=self.db;raw_db=db
        while hasattr(raw_db,'actual'):raw_db=raw_db.actual
        if raw_db.in_transaction:return
        from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
        with dispatch_gate(self.root):
            if db.in_transaction:return
            begun=False
            try:
                db.execute('BEGIN IMMEDIATE');begun=True
                for name,device,inode in created:
                    if db.execute('SELECT 1 FROM artifacts WHERE storage_ref=? LIMIT 1',(name,)).fetchone():continue
                    path=self.root/'blobs'/name
                    try:actual=os.stat(path,follow_symlinks=False)
                    except OSError:continue
                    if stat.S_ISREG(actual.st_mode) and (actual.st_dev,actual.st_ino)==(device,inode):
                        try:path.unlink()
                        except OSError:pass
                db.execute('COMMIT');begun=False
            except Exception:
                # Cleanup uncertainty never turns into permission to delete,
                # and never masks the original transaction failure.
                if begun and raw_db.in_transaction:
                    try:raw_db.execute('ROLLBACK')
                    except sqlite3.Error:pass
    def insert(self,table,**fields):
        if table not in self.columns: raise ContractError('unknown table')
        fields.setdefault('id',identifier())
        if 'instance_id' in self.columns[table]: fields.setdefault('instance_id',self.instance_id)
        if set(fields)-self.columns[table]: raise ContractError('unknown columns: '+str(set(fields)-self.columns[table]))
        values=[dumps(v) if isinstance(v,(dict,list)) else v for v in fields.values()]
        self.db.execute('INSERT INTO '+table+' ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',values)
        return fields['id']
    def row(self,table,key):
        if table not in self.columns: raise ContractError('unknown table')
        row=self.db.execute('SELECT * FROM '+table+' WHERE id=? AND instance_id=?',(key,self.instance_id)).fetchone()
        if row is None: raise ContractError('object not found in instance: '+table)
        return dict(row)
    def rows(self,table):
        if table not in self.columns: raise ContractError('unknown table')
        return [dict(r) for r in self.db.execute('SELECT * FROM '+table+' WHERE instance_id=?',(self.instance_id,))]
    def artifact(self,value,media_type='application/json'):
        raw=dumps(value).encode() if media_type=='application/json' else str(value).encode()
        from digital_life.infrastructure.persistence.tool_learning_meter import material_produced
        material_produced(len(raw))
        checksum=sha(raw); folder=self.root/'blobs'
        if folder.is_symlink(): raise ContractError('artifact directory cannot be symlink')
        path=folder/checksum
        found=self.db.execute('SELECT * FROM artifacts WHERE instance_id=? AND hash=? AND media_type=?',(self.instance_id,checksum,media_type)).fetchone()
        created=[]
        def write_new():
            with path.open('xb') as stream:
                observed=os.fstat(stream.fileno());item=(checksum,observed.st_dev,observed.st_ino);created.append(item)
                if self._blob_frames:self._blob_frames[-1].append(item)
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
        try:
            write_new()
        except FileExistsError:
            if path.is_symlink():raise ContractError('artifact integrity failure')
            from digital_life.infrastructure.persistence.tool_learning_meter import cached_artifact,artifact_before,artifact_after
            cached,existing=cached_artifact(found) if found else (False,None)
            if not cached:
                artifact_before(len(raw))
                with path.open('rb') as stream:existing=stream.read(len(raw)+1)
                artifact_after(len(existing))
            if len(existing)!=len(raw) or sha(existing)!=checksum:raise ContractError('artifact integrity failure')
        except BaseException:
            if not self._blob_frames:self._discard_unregistered_blobs(created)
            raise
        try:
            ident=found['id'] if found else self.insert('artifacts',hash=checksum,size=len(raw),media_type=media_type,storage_ref=checksum,retention_class='instance')
            # A concurrent uncommitted creator may have rolled back while this
            # writer waited for SQLite. Once our row is owned, restore only its
            # exact serialized bytes if that old unregistered file disappeared.
            if not path.exists():write_new()
            return ident
        except BaseException:
            if not self._blob_frames:self._discard_unregistered_blobs(created)
            raise
    def read_artifact(self,key):
        row=self.row('artifacts',key); path=self.root/'blobs'/row['storage_ref']
        if path.parent!=self.root/'blobs' or path.is_symlink(): raise ContractError('invalid artifact path')
        from digital_life.infrastructure.persistence.tool_learning_meter import artifact_before,artifact_after,artifact_failed
        from digital_life.infrastructure.persistence.tool_learning_meter import cached_artifact,remember_artifact
        cached,raw=cached_artifact(row)
        if not cached:
            artifact_before(row['size'])
            try:raw=path.read_bytes()
            except BaseException:artifact_failed();raise
            artifact_after(len(raw))
            if sha(raw)!=row['hash']:raise ContractError('artifact hash mismatch')
            remember_artifact(row,raw)
        return json.loads(raw) if row['media_type']=='application/json' else raw.decode()
    def root_object(self,kind): return self.insert('object_registry',kind=kind)
    def event(self,event_type,payload_object_id=None,payload=None,source='runtime',key=None,activity=None,lane='work',cause=None):
        key=key or identifier()
        artifact=self.artifact(payload) if payload is not None else None
        checksum=sha(dumps(payload)) if payload is not None else sha(payload_object_id)
        prior=self.db.execute('SELECT * FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=?',(self.instance_id,source,key)).fetchone()
        if prior:
            if prior['payload_hash']!=checksum: raise Conflict('event key reused with different payload')
            return prior['id']
        seq=self.db.execute('SELECT coalesce(max(event_seq),0)+1 FROM runtime_events WHERE instance_id=?',(self.instance_id,)).fetchone()[0]
        return self.insert('runtime_events',event_seq=seq,event_type=event_type,source=source,source_event_id=key,correlation_id=activity or key,
            causation_event_id=cause,activity_id=activity,lane=lane,payload_object_id=payload_object_id,payload_artifact_id=artifact,payload_hash=checksum,received_at=utc(),authority_ref=None)
    def evidence(self,object_id=None,artifact=None,method='observed'):
        return self.insert('evidence_items',origin_object_id=object_id,artifact_id=artifact,method=method)
    def config(self):
        row=self.db.execute('SELECT * FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.instance_id,)).fetchone()
        return self.read_artifact(row['artifact_ref'])
    def bootstrap(self,name,model_config):
        if model_config and model_config.get('backend')=='remote_chat':
            from digital_life.infrastructure.llm.remote_chat import RemoteChatReasoner
            RemoteChatReasoner(model_config)  # validates structure only; never reads the key or contacts a provider
        if model_config and model_config.get('backend')=='codex_cli':
            from digital_life.infrastructure.llm.codex_cli import CodexReasoner
            CodexReasoner(model_config)
        with self.tx():
            self.instance_id=identifier()
            self.insert('identity_instances',id=self.instance_id,state='active',generation=0,controller_ref=None,created_event_id=None)
            entity=self.insert('world_entities',entity_type='human',canonical_name='local-controller',resolution_status='resolved')
            controller=self.insert('social_actors',entity_id=entity,actor_type='controller',identity_status='verified')
            self.db.execute('UPDATE identity_instances SET controller_ref=? WHERE id=?',(controller,self.instance_id))
            me=self.insert('world_entities',entity_type='digital-life',canonical_name=name,resolution_status='resolved')
            self_actor=self.insert('social_actors',entity_id=me,actor_type='self',identity_status='verified')
            cfg={'name':name,'model':model_config or {'backend':'unconfigured','model':'unconfigured'},'controller':controller,'self_actor':self_actor,'auto_learning':False}
            art=self.artifact(cfg)
            configuration=self.insert('configuration_versions',version='initial',artifact_ref=art,hash=self.row('artifacts',art)['hash'],compatibility={'schema':2})
            self.insert('model_versions',version=cfg['model']['model'],artifact_ref=art,hash=self.row('artifacts',art)['hash'],compatibility={'fresh_request':True})
            policy=self.insert('policy_versions',version=0,mode='authorization',scope={'root':str(self.root/'workspace')},effective_at=utc(),authority=controller)
            self.insert('policy_epochs',epoch=0,policy_version_id=policy,updated_at=utc())
            rule=self.insert('rule_definitions',name='always',version=1,expression_json={'op':'literal','value':True},engine_version='rules-v1')
            self.insert('rule_definitions',name='completed',version=1,expression_json={'op':'eq','left':{'var':'verified'},'right':True},engine_version='rules-v1')
            for name_ in ('write_note','read_file','list_files'):
                cap=self.insert('capability_definitions',name=name_,description='workspace-only '+name_)
                self.insert('tool_definitions',name=name_,version=1,input_schema={'type':'object'},capability_id=cap,supports_idempotency=int(name_=='write_note'),supports_query=1)
            self.insert('perception_channels',kind='user',capabilities=['text'],verification_method='local-token',state='available')
            profile=self.insert('personality_profiles',version=0,effective_at=utc(),profile_object_id=self.root_object('personality-root'))
            for dim in ('openness','conscientiousness','extraversion','agreeableness','emotional_stability'):
                d=self.insert('personality_dimensions',name=dim,definition=dim,scale_min=-1,scale_max=1,direction='positive',theory_version='BigFive-project-v1')
                self.insert('personality_trait_values',profile_id=profile,dimension_id=d,central_value=0.,uncertainty_json={'status':'uncalibrated'})
            values=self.insert('value_profiles',version=0,effective_at=utc(),profile_object_id=self.root_object('value-root'),normalization_rule='sum1')
            for dim in ('accuracy','care','continuity','exploration'):
                d=self.insert('value_dimensions',definition=dim,scale={'min':0,'max':1},theory_version='project-functional-v1')
                self.insert('value_weights',profile_id=values,dimension_id=d,weight=0.25,uncertainty_json={'status':'uncalibrated'})
            self.insert('identity_anchors',version=0,anchor_data={'name':name,'instance_id':self.instance_id},authority_ref=controller,anchor_object_id=self.root_object('identity-root'))
            self.insert('initialization_runs',bootstrap_key='initial',schema_migration_version=2,configuration_id=configuration,phase='complete',state='committed',completed_at=utc())
            self.insert('instance_wake_state',desired_generation=0,acknowledged_generation=0)
            self.event('instance.prepared',payload={'name':name,'wake_disabled':True},lane='control')
    def snapshot(self,destination):
        dest=Path(destination)
        if dest.exists(): raise Conflict('snapshot destination exists')
        db=sqlite3.connect(str(dest))
        try: self.db.backup(db)
        finally: db.close()
        return {'path':str(dest),'sha256':sha(dest.read_bytes()),'scope':'database-only; blobs require separate manifest'}
    def integrity(self):
        return {'integrity':self.db.execute('PRAGMA integrity_check').fetchone()[0],
                'foreign_keys':[tuple(r) for r in self.db.execute('PRAGMA foreign_key_check')]}
