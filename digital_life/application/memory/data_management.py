"""Explicit, non-destructive legacy import and consistent backup bundles."""
import json
from pathlib import Path
import shutil
import sqlite3
from digital_life.domain.contracts import utc,identifier,dumps,sha,ContractError,Conflict,Forbidden
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine

def import_legacy(source,target):
    source=Path(source).resolve(); target=Path(target).resolve()
    if source==target or target.exists(): raise Conflict('import requires a new distinct target directory')
    path=source/'runtime.sqlite'
    if not path.is_file() or path.is_symlink(): raise ContractError('legacy source missing')
    old=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True); old.row_factory=sqlite3.Row
    try:
        if old.execute('PRAGMA application_id').fetchone()[0]!=1345335344: raise ContractError('source is not primordial00 legacy')
        tables={r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        export={table:[dict(r) for r in old.execute('SELECT * FROM '+table)] for table in tables if table.replace('_','').isalnum()}
    finally: old.close()
    store=Store.prepare(target,name='原初00 · 导入后继')
    try:
        with store.tx():
            artifact=store.artifact({'legacy_path':str(source),'export':export,'imported_at':utc()})
            run=store.insert('import_runs',source_artifact_id=artifact,authority_ref=store.config()['controller'],mode='import',state='started',started_at=utc())
            activity_by_event={a['event_id']:a for a in export.get('activities',[])}
            mapping={}
            for event in export.get('runtime_events',[]):
                content=json.loads(event['payload'])['text']
                activity=Engine(store).submit(content,event['id'],'legacy-import'); mapping[event['id']]=activity
                original=activity_by_event.get(event['id'])
                if original and original['state'] in ('completed','cancelled','failed'):
                    engine=Engine(store)
                    if original['state']=='completed':
                        engine.transition(activity,'running','legacy-history'); engine.transition(activity,'completed','legacy-history-not-reexecuted')
                    elif original['state']=='cancelled': engine.cancel(activity,store.config()['controller'])
                    else: engine.transition(activity,'running','legacy-history'); engine.transition(activity,'failed','legacy-history')
                    store.db.execute("UPDATE jobs SET state='cancelled',lease_owner=NULL,lease_expiry=NULL,lease_token=NULL WHERE target_ref=?",(activity,))
                store.event('legacy.activity.imported',payload={'legacy_event':event['id'],'activity':activity,'historical_state':original['state'] if original else None,'not_reexecuted':True},lane='control')
            store.db.execute("UPDATE import_runs SET state='committed',completed_at=? WHERE id=?",(utc(),run))
            store.event('legacy.import.completed',payload={'run':run,'source_identity':export.get('identity_instances',[]),'mapped_activities':mapping,'continuity':'successor-import; no identity-transfer claim'},lane='control')
        return {'run':run,'new_instance':store.instance_id,'wake_disabled':True,'legacy_preserved':True,'legacy_full_history_artifact':artifact}
    finally: store.close()

def backup_bundle(store,destination):
    from digital_life.application.learning.runtime import legacy_protection_present
    if legacy_protection_present(store):raise Forbidden('protected source state requires qualified managed backup; legacy export is blocked')
    destination=Path(destination).resolve()
    if destination.exists(): raise Conflict('backup destination must be new')
    if destination==store.root or store.root in destination.parents: raise Forbidden('backup must be outside live instance directory')
    destination.mkdir(parents=True)
    # Writer transaction freezes the referenced blob manifest while backup uses a separate read connection.
    with store.tx():
        reader=sqlite3.connect(str(store.root/'runtime.sqlite')); target=sqlite3.connect(str(destination/'runtime.sqlite'))
        try: reader.backup(target)
        finally: target.close(); reader.close()
        manifest={}
        for row in store.rows('artifacts'):
            source=store.root/'blobs'/row['storage_ref']
            if source.is_symlink() or source.parent!=store.root/'blobs': raise Forbidden('invalid artifact path')
            raw=source.read_bytes()
            if sha(raw)!=row['hash']: raise ContractError('blob integrity failure during backup')
            out=destination/'blobs'/row['storage_ref']; out.parent.mkdir(exist_ok=True)
            if not out.exists(): out.write_bytes(raw)
            manifest[str(out.relative_to(destination))]=row['hash']
        manifest['runtime.sqlite']=sha((destination/'runtime.sqlite').read_bytes())
    (destination/'manifest.json').write_text(dumps({'instance_id':store.instance_id,'files':manifest,'created_at':utc(),'scope':'database and referenced artifacts; no external actions rewound'}))
    with store.tx(): store.event('backup.created',payload={'path':str(destination),'manifest_sha256':sha((destination/'manifest.json').read_bytes())},lane='control')
    return {'path':str(destination),'files':len(manifest)}

def restore_bundle(source,target):
    source=Path(source).resolve(); target=Path(target).resolve()
    if target.exists(): raise Conflict('restore requires a new target')
    manifest=json.loads((source/'manifest.json').read_text())
    for name,checksum in manifest['files'].items():
        path=source/name
        if source not in path.resolve().parents or path.is_symlink() or sha(path.read_bytes())!=checksum: raise ContractError('invalid backup manifest or content')
    database=source/'runtime.sqlite'
    if database.is_symlink() or not database.is_file():raise Forbidden('backup database missing or unsafe')
    reader=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    try:
        if reader.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tl_work'").fetchone():raise Forbidden('RESTORE_BLOCKED: TL image requires current outside-image recovery authority')
    finally:reader.close()
    target.mkdir(parents=True)
    for name in manifest['files']:
        path=target/name; path.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source/name,path)
    (target/'workspace').mkdir(); (target/'snapshots').mkdir()
    (target/'WAKE_DISABLED').write_text('Restored snapshot: continuity and external effects must be reconciled before any wake.\n')
    # A restored copy must not run concurrently under the source instance identity.
    (target/'RESTORE_RECONCILIATION_REQUIRED').write_text(dumps({'source':str(source),'instance':manifest['instance_id'],'external_effects_not_rewound':True}))
    store=Store(target)
    try: return {'integrity':store.integrity(),'wake_disabled':True,'reconciliation_required':True}
    finally: store.close()


def restore_current_bundle(store,source,target,*,authority,entry,bearer,exclusions,limits):
    """Build a LOCKED continuity candidate using the CURRENT authoritative DB.

    A historical bundle can supply only exact currently registered, non-erased
    missing blobs. It never replaces newer work/decision/barrier history. This
    deliberately cannot recover a lost authoritative DB or grant a wake.
    """
    from digital_life.application.learning.maintenance import ControllerMaintenanceAuthority
    from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
    from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
    from digital_life.domain import tool_learning_contract as c
    from digital_life.domain import tool_learning_types as t
    import os
    import stat
    from copy import deepcopy
    if not isinstance(authority,ControllerMaintenanceAuthority) or authority.s is not store:raise Forbidden('actual current controller restore owner required')
    limits=deepcopy(limits);t.obj(limits,('scan','items','bytes','elapsed_ms','attempts'))
    for value in limits.values():t.integer(value,1,2**53-1)
    if limits['attempts']!=1:raise Forbidden('restore is local maintenance, never model/tool authorization')
    source=Path(source).absolute();target=Path(target).absolute()
    if source.is_symlink() or not source.is_dir() or source.resolve()!=source:raise Forbidden('backup source must be a real canonical directory')
    if target.exists() or target.is_symlink() or target.parent.resolve()!=target.parent or target==store.root or store.root in target.parents:raise Conflict('restore candidate needs a new independent canonical directory')
    deadline=utc(limits['elapsed_ms']/1000)
    meter=PhysicalReadMeter({'input_tokens':0,'output_tokens':0,'tool_calls':0,**limits},deadline)
    with dispatch_gate(store.root):
        actor=authority._controller(bearer);session=authority._session(entry)
        if session['module']!='M12':raise Forbidden('restore needs the current M12 control channel')
        active,policy,control=authority._current();configured=c.loads(policy['scope']).get('tool_learning_maintenance_limits')
        if policy['authority']!=actor or not isinstance(configured,dict) or set(configured)!=set(limits) or any(limits[k]>configured[k] for k in limits):raise Forbidden('restore exceeds current actual maintenance limits')
        profile=c.loads(policy['scope']).get('tool_learning_restore_candidate')
        required={'contract':'TL-RESTORE-CANDIDATE-POLICY-1','purpose':'restore_locked_candidate','instance_id':store.instance_id,'source_bundle':str(source),'target':str(target),'scope':'whole_current_database_and_registered_artifacts','retain_control_metadata':True,'external_material_use':False,'wake_authorized':False}
        if profile!=required:raise Forbidden('explicit current whole-instance locked restore policy/path scope is missing')
        if len(store.rows('identity_instances'))!=1:raise Forbidden('multi-identity image needs its own explicit recovery owner')
        def read_current_exclusions():
            with dispatch_gate(exclusions.directory):
                total=0;count=0
                for path in exclusions.directory.iterdir():
                    if path.name=='dispatch.lock':continue
                    count+=1
                    if count>min(65536,limits['scan']):raise Forbidden('current exclusion file coverage exhausted')
                    status=path.lstat()
                    if not stat.S_ISREG(status.st_mode):raise Forbidden('current exclusion file is unsafe')
                    total+=status.st_size
                    meter.ensure(total,scan=count,items=count)
                try:
                    result=exclusions.restore_constraints(entry,store.instance_id,max_records=max(1,min(65536,limits['scan']-meter.actual['scan'])),max_bytes=max(1,limits['bytes']-meter.actual['bytes']))
                except BaseException:
                    meter.unknown_bytes=True
                    raise
                meter.consume(total,scan=count,items=count)
                return result
        with meter.installed(store):
            # A whole-image policy cannot manufacture someone else's source
            # authority. Every supported original root must be actually owned.
            for kind in ('memory_items','perception_signals'):
                roots=store.db.execute('SELECT id FROM '+kind+' WHERE instance_id=? ORDER BY id LIMIT ?',(store.instance_id,limits['scan']+1)).fetchall()
                if len(roots)>limits['scan']:raise Forbidden('restore source-owner coverage incomplete')
                for row in roots:
                    from digital_life.application.learning.eligibility import ref
                    authority._owned_source(ref(store,row['id'],kind),policy['id'],actor)
            works=store.db.execute('SELECT conditions_artifact_id FROM tl_work WHERE instance_id=? ORDER BY id LIMIT ?',(store.instance_id,limits['scan']+1)).fetchall()
            if len(works)>limits['scan']:raise Forbidden('restore work-source ownership coverage incomplete')
            for work in works:
                condition=authority.storage.read_artifact(work['conditions_artifact_id'])
                evidence=condition.get('source') if isinstance(condition,dict) else None
                if not isinstance(evidence,dict) or not isinstance(evidence.get('source'),dict):raise Forbidden('restore has no actual original-work source owner')
                authority._owned_source(evidence['source'],policy['id'],actor)
            constraints=read_current_exclusions()
            if not constraints['complete_current_ledger']:raise Forbidden('RESTORE_BLOCKED: current exclusions incomplete')
            # This is a fresh explicitly authenticated local maintenance account,
            # not a reset of any activity/work budget or an old cleanup grant.
            with store.tx():
                original=store.row('activities',session['plan']['source_activity']);restore_activity=identifier();restore_account=identifier()
                store.insert('activities',id=restore_activity,trigger_event_id=original['trigger_event_id'],state='pending',release_id=original['release_id'],publication_state='ready',deadline=deadline,budget_json={'contract':'TL-MAINTENANCE-BUDGET-1','plan_id':restore_activity,'caps':limits})
                store.insert('activity_budget_accounts',id=restore_account,activity_id=restore_activity,token_limit=0,tool_call_limit=0,attempt_limit=1,time_limit_ms=limits['elapsed_ms'])
                grant=store.event('recovery.restore_candidate_authorized',payload={'contract':'TL-CURRENT-RESTORE-GRANT-1','target':str(target),'source_bundle':str(source),'instance_id':store.instance_id,'controller_id':actor,'policy_id':policy['id'],'policy_epoch':active['epoch'],'control_revision':control['control_revision'],'root_registration_id':session['body']['root_registration_id'],'constraints_digest':c.fingerprint(constraints),'caps':limits,'deadline':deadline,'external_effect_replay':False,'activity_id':restore_activity,'account_id':restore_account,'entered':True},source='tl.recovery.restore',lane='control')
            outcome='failed'
            try:
                excluded={x['id'] for record in constraints['exclusions'] for x in record['targets'] if x['kind']=='artifacts'}
                # Current SQLite is authoritative even when it already contains a
                # tombstone. The old database file is never copied or executed.
                manifest_path=source/'manifest.json'
                if manifest_path.is_symlink() or not manifest_path.is_file():raise Forbidden('backup manifest missing')
                meter.ensure(manifest_path.stat().st_size,scan=1,items=1)
                with manifest_path.open('rb') as stream:raw=stream.read(min(limits['bytes'],1048576)+1)
                meter.consume(len(raw),items=1);manifest=c.loads(raw)
                if not isinstance(manifest,dict) or manifest.get('instance_id')!=store.instance_id or not isinstance(manifest.get('files'),dict):raise Conflict('backup identity/manifest mapping differs')
                target.mkdir(mode=0o700)
                (target/'WAKE_DISABLED').write_text('Locked continuity candidate; no wake authorization.\n')
                lock={'contract':'TL-CURRENT-RESTORE-CANDIDATE-1','instance_id':store.instance_id,'current_root':str(store.root),'grant_id':grant,'constraints_digest':c.fingerprint(constraints),'external_effects_not_rewound':True,'reconciliation_required':True}
                (target/'RESTORE_RECONCILIATION_REQUIRED').write_text(dumps(lock))
                (target/'blobs').mkdir();(target/'workspace').mkdir();(target/'snapshots').mkdir()
                with store.tx():
                    reader=sqlite3.connect(str(store.root/'runtime.sqlite'));output=sqlite3.connect(str(target/'runtime.sqlite'))
                    try:
                        page_size=reader.execute('PRAGMA page_size').fetchone()[0]
                        if type(page_size) is not int or page_size<=0:raise Forbidden('unknown actual SQLite page size')
                        def progress(status,remaining,total):
                            meter.time()
                            meter.ensure(total*page_size,items=1)
                        reader.backup(output,pages=32,progress=progress,sleep=0)
                    finally:output.close();reader.close()
                    meter.consume((target/'runtime.sqlite').stat().st_size,items=1)
                    rows=store.db.execute('SELECT * FROM artifacts WHERE instance_id=? ORDER BY id LIMIT ?',(store.instance_id,limits['items']+1)).fetchall()
                    if len(rows)>limits['items']:raise Forbidden('restore artifact coverage exceeds original cap')
                    for row in rows:
                        name=row['storage_ref']
                        if len(name)!=64 or any(ch not in '0123456789abcdef' for ch in name):raise Forbidden('unknown artifact path')
                        path=store.root/'blobs'/name
                        if not path.exists():
                            if row['id'] in excluded or manifest['files'].get('blobs/'+name)!=row['hash']:raise Forbidden('excluded or unregistered historical material cannot be restored')
                            path=source/'blobs'/name
                        meter.ensure(row['size'],scan=1,items=1)
                        parent=path.parent
                        if parent.is_symlink() or parent.resolve()!=parent:raise Forbidden('restore blob directory escapes its managed root')
                        directory=os.open(str(parent),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                        try:fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
                        finally:os.close(directory)
                        with os.fdopen(fd,'rb') as stream:
                            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise Forbidden('restore blob is not regular')
                            blob=stream.read(min(row['size'],max(0,limits['bytes']-meter.actual['bytes']))+1)
                        meter.consume(len(blob),items=1)
                        if len(blob)!=row['size'] or sha(blob)!=row['hash']:raise Conflict('current immutable artifact bytes differ')
                        destination=target/'blobs'/name
                        if not destination.exists():
                            descriptor=os.open(str(destination),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
                            with os.fdopen(descriptor,'wb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
                        authority._session(entry)
                    fresh=read_current_exclusions()
                    if fresh!=constraints:raise Conflict('current exclusion history changed while building candidate')
                    authority._session(entry);meter.time()
                candidate=Store(target)
                try:
                    if candidate.instance_id!=store.instance_id or candidate.integrity()!={'foreign_keys':[],'integrity':'ok'}:raise Conflict('restored candidate integrity differs')
                finally:candidate.close()
                outcome='candidate_locked'
                return {'path':str(target),'instance_id':store.instance_id,'wake_disabled':True,'reconciliation_required':True,'current_history_preserved':True,'historical_database_used':False,'restore_authorized':True,'wake_authorized':False,'usage':meter.usage()}
            finally:
                with store.tx():store.event('recovery.restore_candidate_settled',payload={'grant_id':grant,'activity_id':restore_activity,'account_id':restore_account,'usage':meter.usage(),'measured':dict(meter.actual),'unknown':meter.usage() is None,'outcome':outcome},source='tl.recovery.restore.settlement',key=grant,lane='control')
