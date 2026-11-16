"""IM16 bounded migration of freshly CREATED synthetic targets only.

No public API accepts an existing instance/path, no model or wake is performed,
and code rollback never restores an older database image.
"""
from pathlib import Path
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
import secrets
import sqlite3
import stat
import weakref
import zipfile
from digital_life.domain.contracts import ContractError,Forbidden,Conflict,identifier,utc,dumps,sha
from digital_life.domain.tool_learning_contract import loads
from digital_life.infrastructure.persistence.sqlite_store import Store,RESOURCES
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.application.lifecycle.control_plane import Control,Releases
from digital_life.application.lifecycle.schema_migration import V3
from digital_life.application.learning.bridge import effective_capabilities,verify_schema4_layout

_SECRET=object();_CREATED=weakref.WeakKeyDictionary();MARKER='IM16_ISOLATED_TARGET.json'
LIMITS={'input_tokens':0,'output_tokens':0,'tool_calls':0,'attempts':0,'scan':262144,'items':262144,'bytes':128*1024*1024,'elapsed_ms':60000}
APPEND={'artifacts','object_registry','policy_versions','schema_migrations','runtime_events'}


class IsolatedMigrationTarget:
    def __init__(self,secret,store,control):
        if secret is not _SECRET:raise Forbidden('only new isolated target creation can grant migration capability')
        self.store=store;self.control=control;self.closed=False
    @classmethod
    def create(cls,value,source_version=2):
        if type(source_version) is not int or source_version not in (2,3):raise ContractError('historical synthetic source must be schema2 or schema3')
        raw=Path(value).absolute()
        if '..' in raw.parts or raw.exists() or raw.is_symlink():raise Forbidden('existing or redirected migration targets are forbidden')
        for parent in (raw.parent,*raw.parent.parents):
            if parent.is_symlink():raise Forbidden('migration target ancestors cannot be symlinks')
            if any((parent/name).exists() for name in ('runtime.sqlite','control.sqlite','WAKE_DISABLED')):raise Forbidden('migration target cannot be nested in an instance')
        if not raw.parent.is_dir():raise Forbidden('isolated target parent must exist')
        raw.mkdir(mode=0o700);s=Store.prepare(raw,name='IM16 synthetic isolated identity');c=Control(raw,s.instance_id)
        token=secrets.token_urlsafe(32);marker={'contract':'IM16-ISOLATION-1','nonce':identifier(),'instance_id':s.instance_id,'scope':'new synthetic namespace only'}
        (raw/MARKER).write_text(dumps(marker));(raw/'controller.token').write_text(token);(raw/'controller.token').chmod(0o600)
        target=cls(_SECRET,s,c);root=raw.stat();database=(raw/'runtime.sqlite').stat()
        _CREATED[target]={'root':str(raw),'root_inode':(root.st_dev,root.st_ino),'db_inode':(database.st_dev,database.st_ino),'marker':marker,'controller':s.config()['controller'],'credential':sha(token),'source_version':source_version}
        if source_version==3:
            from digital_life.application.lifecycle.schema_migration import migrate
            migrate(s,s.config()['controller'],3)
        return target
    def verify(self):
        value=_CREATED.get(self)
        if value is None or self.closed:raise Forbidden('no live isolated creation capability')
        root=Path(value['root'])
        if self.store.root!=root or root.is_symlink() or root.resolve()!=root or (root.stat().st_dev,root.stat().st_ino)!=value['root_inode']:raise Forbidden('isolated target directory identity changed')
        database=root/'runtime.sqlite'
        if database.is_symlink() or (database.stat().st_dev,database.stat().st_ino)!=value['db_inode']:raise Forbidden('isolated target database identity changed')
        marker=root/MARKER
        if marker.is_symlink() or loads(marker.read_text())!=value['marker'] or self.store.instance_id!=value['marker']['instance_id']:raise Forbidden('isolated creation marker/instance changed')
        lock=root/'WAKE_DISABLED'
        if lock.is_symlink() or not lock.is_file():raise Forbidden('isolated migration/selection requires the wake lock')
        current=self.control.state()
        if not current['user_stopped'] or current['active_process_run_id'] is not None or self.control.db.execute('SELECT 1 FROM process_runs WHERE instance_ref=? AND exited_at IS NULL LIMIT 1',(self.store.instance_id,)).fetchone():raise Forbidden('stop and reconcile all process ownership before migration')
        return deepcopy(value)
    def close(self):
        if self.closed:return
        value=_CREATED.get(self)
        if value is not None:
            root=Path(value['root'])
            if root.is_symlink() or (root.stat().st_dev,root.stat().st_ino)!=value['root_inode']:raise Forbidden('do not write a replaced target')
            (root/'WAKE_DISABLED').write_text('IM16 isolated target remains stopped; no formal wake authorization.\n')
            self.control.stop('im16-close-'+value['marker']['nonce'])
        self.control.close();self.store.close();self.closed=True;_CREATED.pop(self,None)
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def _auth(target,bearer):
    if type(target) is not IsolatedMigrationTarget:raise Forbidden('existing stores/paths and caller synthetic labels cannot authorize migration')
    owned=target.verify()
    from digital_life.application.learning.runtime import authenticate_controller
    actor=authenticate_controller(target.store,bearer)
    if actor!=owned['controller']:raise Forbidden('isolated controller changed')
    return owned


def _statements(raw):
    current=''
    for line in raw.splitlines(True):
        current+=line
        if sqlite3.complete_statement(current):yield current;current=''
    if any(line.strip() and not line.lstrip().startswith('--') for line in current.splitlines()):raise ContractError('incomplete frozen DDL statement')


def _inventory(s):
    result={}
    tables=s.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'memory_search%' ORDER BY name").fetchall()
    for item in tables:
        name=item[0]
        if not name.replace('_','').isalnum():raise Forbidden('unknown legacy table identifier')
        columns={r[1] for r in s.db.execute('PRAGMA table_info('+name+')')}
        if 'instance_id' not in columns:continue
        rows=[dict(r) for r in s.db.execute('SELECT * FROM '+name+' WHERE instance_id=?',(s.instance_id,))]
        result[name]=rows
    return result


def _preserved(s,before,new_policy=None):
    after=_inventory(s)
    for table,rows in before.items():
        if table=='policy_epochs' and new_policy is not None:
            for row in rows:
                now=s.row(table,row['id'])
                if now['epoch']!=row['epoch']+1 or now['policy_version_id']!=new_policy or any(now[k]!=v for k,v in row.items() if k not in ('epoch','policy_version_id','updated_at')):raise Conflict('policy projection changed more than the explicit default-off head')
            continue
        from collections import Counter
        old=Counter(dumps(r) for r in rows);current=Counter(dumps(r) for r in after.get(table,[]))
        if old-current:raise Conflict('migration altered existing '+table+' history')
        if table not in APPEND and old!=current:raise Conflict('migration invented legacy '+table+' rows')
    return True


def _verify_v3(db):
    expected={'module_checkpoints':('table',V3[2]),'ix_metrics_by_run':('index',V3[0]),'ix_events_by_type':('index',V3[1])}
    def normalized(sql):
        import re
        # The write monitor appends an inert prepare marker to persisted DDL.
        # Strip only that exact trailing comment; verify every DDL token below.
        sql=re.sub(r'\n/\*tl-managed:[0-9a-f]+:[0-9]+\*/\Z','',sql)
        return ' '.join(sql.split()).rstrip(';').lower()
    for name,(kind,sql) in expected.items():
        row=db.execute('SELECT type,sql FROM sqlite_master WHERE name=?',(name,)).fetchone()
        if row is None or row['type']!=kind or normalized(row['sql'])!=normalized(sql):raise Conflict('recorded schema3 does not match actual historical DDL: '+name)


def _bridge(target,deployment):
    c=target.control;s=target.store;releases=Releases(c);path=releases.verify(deployment)
    row=c.db.execute('SELECT * FROM deployments WHERE id=?',(deployment,)).fetchone()
    if row['schema_max']!=4 or not row['schema_min']<=4:raise Forbidden('no verified schema4 rollback bridge')
    actual=effective_capabilities(c,deployment)
    if actual['capabilities']!=['TL-LOOP-0.1']:raise Forbidden('bridge does not enforce the frozen source gate')
    return {'deployment':deployment,'build_hash':row['build_hash'],'path':str(path),'effective_capabilities':actual}


def _backup(target,operation,bridge,meter):
    s=target.store;c=target.control;parent=s.root.parent;archive=parent/('im16-backup-'+operation+'.zip');temporary=parent/('im16-backup-'+operation+'.sqlite')
    if archive.exists() or temporary.exists():raise Conflict('backup artifacts already exist; reconcile original operation')
    reader=sqlite3.connect(str(s.root/'runtime.sqlite'));out=sqlite3.connect(str(temporary))
    try:
        page_size=reader.execute('PRAGMA page_size').fetchone()[0]
        reader.backup(out,pages=32,progress=lambda status,remaining,total:meter.ensure(total*page_size,items=1),sleep=0)
    finally:out.close();reader.close()
    temporary.chmod(0o600);meter.ensure(temporary.stat().st_size,items=1);database=temporary.read_bytes();meter.consume(len(database),items=1);files={'runtime.sqlite':sha(database)}
    with archive.open('xb') as output:
        archive.chmod(0o600)
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('runtime.sqlite',database)
            rows=s.db.execute('SELECT * FROM artifacts WHERE instance_id=? ORDER BY id',(s.instance_id,)).fetchall()
            for row in rows:
                name=row['storage_ref']
                if len(name)!=64 or any(ch not in '0123456789abcdef' for ch in name):raise Forbidden('invalid artifact path in backup')
                meter.ensure(row['size'],items=1);directory=os.open(str(s.root/'blobs'),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
                finally:os.close(directory)
                with os.fdopen(fd,'rb') as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise Forbidden('backup source blob is not regular')
                    raw=stream.read(row['size']+1)
                meter.consume(len(raw),items=1)
                if len(raw)!=row['size'] or sha(raw)!=row['hash']:raise Conflict('backup current artifact integrity failed')
                key='blobs/'+name
                if key not in files:bundle.writestr(key,raw);files[key]=row['hash']
            manifest={'contract':'IM16-BACKUP-1','instance_id':s.instance_id,'source_version':s.db.execute('PRAGMA user_version').fetchone()[0],'migration_id':operation,'files':files,'database_restore_allowed':False}
            bundle.writestr('manifest.json',dumps(manifest))
        output.flush();os.fsync(output.fileno())
    meter.ensure(archive.stat().st_size);raw=archive.read_bytes();meter.consume(len(raw));digest=sha(raw)
    with zipfile.ZipFile(archive) as bundle:
        if set(bundle.namelist())!=set(files)|{'manifest.json'} or len(bundle.namelist())!=len(set(bundle.namelist())):raise Conflict('backup archive inventory differs')
        for name,digest_expected in files.items():
            meter.ensure(bundle.getinfo(name).file_size);data=bundle.read(name);meter.consume(len(data))
            if sha(data)!=digest_expected:raise Conflict('backup readback hash mismatch')
    with c.tx():registration=c.insert('backup_manifests',deployment_id=bridge['deployment'],snapshot_path=str(archive),hash=digest,scope={'instance_id':s.instance_id,'managed_root':str(parent),'kind':'IM16 registered single-file complete bundle','migration_id':operation},completed_at=utc())
    # The temporary database is an independently registered private snapshot,
    # never an unregistered runnable directory or a blind rollback source.
    with c.tx():c.insert('backup_manifests',deployment_id=bridge['deployment'],snapshot_path=str(temporary),hash=sha(database),scope={'instance_id':s.instance_id,'managed_root':str(parent),'kind':'IM16 database-only staging snapshot','migration_id':operation},completed_at=utc())
    return {'registration_id':registration,'path':str(archive),'hash':digest,'manifest_digest':sha(dumps(manifest)),'database_snapshot':str(temporary),'complete':True,'restore_authorized':False}


def migrate_isolated(target,bearer,forward_deployment,rollback_deployment,*,fault=None):
    owned=_auth(target,bearer);s=target.store;c=target.control;operation=identifier();meter=PhysicalReadMeter(dict(LIMITS),utc(60));backup=None;outcome='failed';committed=False
    def inject(point):
        if fault is not None:fault(point)
    with dispatch_gate(s.root):
        target.verify();forward=_bridge(target,forward_deployment);rollback=_bridge(target,rollback_deployment);version=s.db.execute('PRAGMA user_version').fetchone()[0]
        ddl=(RESOURCES/'tool_learning_v1.sql').read_text();checksum=sha(ddl)
        if version==4:
            row=s.db.execute('SELECT * FROM schema_migrations WHERE instance_id=? AND version=4',(s.instance_id,)).fetchone()
            if row is None or row['checksum']!=checksum:raise Conflict('existing schema4 migration has no matching durable record')
            verify_schema4_layout(s.db)
            s.columns={row[0]:{col[1] for col in s.db.execute('PRAGMA table_info('+row[0]+')')} for row in s.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            return {'version':4,'already_applied':True,'data_rewound':False,'wake_disabled':True}
        if version not in (2,3):raise Forbidden('no approved isolated migration path')
        if s.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name GLOB 'tl_*' LIMIT 1").fetchone():raise Forbidden('pre-expanded experimental source requires explicit reconciliation, not blind migration')
        if version==3:
            previous=s.db.execute('SELECT checksum FROM schema_migrations WHERE instance_id=? AND version=3',(s.instance_id,)).fetchone()
            if previous is None or previous['checksum']!=sha(dumps(V3)):raise Conflict('source3 is not the actual recorded historical expansion')
            _verify_v3(s.db)
        with c.tx():command,_=c.command('migration.isolated','migration:'+operation,{'instance_id':s.instance_id,'root':str(s.root),'source_version':version,'forward':forward,'rollback':rollback,'caps':LIMITS,'deadline':meter.deadline,'isolation_nonce':owned['marker']['nonce'],'backup_paths':[str(s.root.parent/('im16-backup-'+operation+suffix)) for suffix in ('.zip','.sqlite')]},authority='isolated-migration-owner')
        try:
            with meter.installed(s):
                before=_inventory(s);inject('before_backup')
                with s.tx():backup=_backup(target,operation,rollback,meter)
                inject('backup_verified')
                with s.tx():
                    if version==2:
                        for index,statement in enumerate(V3):s.db.execute(statement);inject('v3_statement_'+str(index))
                        s.insert('schema_migrations',version=3,checksum=sha(dumps(V3)),applied_at=utc(),release_id='schema-expand-v3')
                    for index,statement in enumerate(_statements(ddl)):s.db.execute(statement);inject('tl_statement_'+str(index))
                    inject('ddl_complete')
                    old_epoch=s.rows('policy_epochs')[0];previous=s.row('policy_versions',old_epoch['policy_version_id']);scope=loads(previous['scope']);feature=scope.get('tool_learning_runtime')
                    if feature is not None:
                        from digital_life.application.learning.runtime import strict_feature_enabled
                        strict_feature_enabled(s)
                    profile=deepcopy(feature) if feature is not None else {'contract':'TL-STRICT-RUNTIME-1','enabled':False};profile['enabled']=False;scope['tool_learning_runtime']=profile
                    number=s.db.execute('SELECT coalesce(max(version),0)+1 FROM policy_versions WHERE instance_id=?',(s.instance_id,)).fetchone()[0]
                    policy=s.insert('policy_versions',version=number,mode=previous['mode'],scope=scope,effective_at=utc(),authority=owned['controller'])
                    changed=s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1,updated_at=? WHERE instance_id=? AND id=? AND epoch=?',(policy,utc(),s.instance_id,old_epoch['id'],old_epoch['epoch'])).rowcount
                    if changed!=1:raise Conflict('migration current policy CAS changed')
                    inject('policy_default_off')
                    s.insert('schema_migrations',version=4,checksum=checksum,applied_at=utc(),release_id=forward['build_hash']);s.db.execute('PRAGMA user_version=4');inject('version_recorded')
                    verify_schema4_layout(s.db)
                    if s.integrity()!={'integrity':'ok','foreign_keys':[]}:raise Conflict('migration integrity check failed')
                    _preserved(s,before,policy);inject('old_rows_verified')
                    s.event('schema.expanded',payload={'from':version,'to':4,'migration_id':operation,'checksum':checksum,'backup':backup,'rollback_bridge':rollback,'new_learning_enabled':False,'old_shadow_adopted':False,'original_budgets_rewritten':False},source='schema4-isolated-migration',lane='control')
                    target.verify();meter.time();inject('before_commit')
                committed=True;outcome='committed_ack_pending';inject('after_commit');outcome='committed'
                s.columns={row[0]:{col[1] for col in s.db.execute('PRAGMA table_info('+row[0]+')')} for row in s.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                return {'version':4,'source_version':version,'migration_id':operation,'backup':backup,'forward':forward,'rollback':rollback,'wake_disabled':True,'data_rewound':False,'old_shadow_adopted':False}
        finally:
            with c.tx():c.db.execute('UPDATE control_commands SET state=?,result_json=?,finished_at=? WHERE id=?',('succeeded' if outcome=='committed' else 'failed',dumps({'migration_id':operation,'outcome':outcome,'commit_acknowledged':committed,'current_version':s.db.execute('PRAGMA user_version').fetchone()[0],'backup':backup,'usage':meter.usage(),'measured':dict(meter.actual),'unknown':meter.usage() is None,'restore_old_database':False}),utc(),command))


def rollback_code_isolated(target,bearer,deployment):
    _auth(target,bearer);s=target.store;c=target.control
    with dispatch_gate(s.root):
        target.verify();before=s.db.execute('PRAGMA user_version').fetchone()[0]
        if before!=4:raise Forbidden('isolated code rollback requires migrated schema4')
        bridge=_bridge(target,deployment);verify_schema4_layout(s.db)
        # Offline selection is deliberately not an activation/wake receipt.
        with c.tx():key,_=c.command('migration.rollback_selected',identifier(),{'instance_id':s.instance_id,'bridge':bridge,'schema_version':4,'database_rewound':False,'activated':False},authority='isolated-migration-owner')
        return {'command_id':key,'selected_deployment':deployment,'activated':False,'wake_disabled':True,'database_rewound':False}


def restore_old_migration_database(target,bearer,backup_registration):
    _auth(target,bearer)
    raise Forbidden('database downgrade/history rollback is forbidden; current trusted exclusions and qualified current-state recovery are required')
