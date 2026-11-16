"""Application recovery points bound to immutable releases, not OS thread images."""
import json,os,shutil,sqlite3
from contextlib import nullcontext
from pathlib import Path
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,identifier,utc,dumps,sha
from digital_life.application.lifecycle.control_plane import Releases
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate

class ProcessCheckpoints:
 def __init__(self,control):self.c=control;self.root=control.root
 def config(self):
  path=self.root/'process-manager.json'
  if path.is_symlink():raise Forbidden('process manager config symlink')
  return json.loads(path.read_text()) if path.exists() else {'enabled':False}
 def configure(self,enabled,actor,*,verify_thought=None,thought_timeout=180):
  with dispatch_gate(self.root):
   if self.c.state()['active_process_run_id']:raise Conflict('stop runtime before process manager configuration')
   s=Store(self.root)
   try:
    from digital_life.application.learning.runtime import legacy_protection_present
    if legacy_protection_present(s):raise Forbidden('protected storage needs a qualified checkpoint adapter')
    if actor!=s.config()['controller'] or type(enabled)is not bool:raise Forbidden('controller and boolean required')
   finally:s.close()
   if verify_thought is None:verify_thought=self.config().get('verify_thought',False)
   if type(verify_thought)is not bool or type(thought_timeout)is not int or not 1<=thought_timeout<=600:raise ContractError('invalid deployment thought gate configuration')
   value={'enabled':enabled,'verify_thought':verify_thought,'thought_timeout':thought_timeout,'verify_rollback':False,'configured_at':utc(),'actor':actor,'state_policy':'preserve-current-ledger','checkpoint_kind':'application-consistent-backup'}
   path=self.root/'process-manager.json';temporary=path.with_suffix('.tmp');temporary.write_text(dumps(value));os.chmod(temporary,0o600);os.replace(temporary,path)
   self.record('configured',identifier(),value);return value
 def record(self,kind,key,value):
  with self.c.tx():
   command,duplicate=self.c.command('process.'+kind,'process:'+kind+':'+key,value,authority='process-manager')
   if not duplicate:self.c.db.execute("UPDATE control_commands SET state='succeeded',finished_at=? WHERE id=?",(utc(),command))
   return command
 def version(self,deployment):
  row=self.c.db.execute('SELECT release FROM deployments WHERE id=?',(deployment,)).fetchone()
  if row is None:raise ContractError('checkpoint deployment missing')
  existing=self.c.db.execute("SELECT payload FROM control_commands WHERE command_key=? AND kind='process.release_version' AND state='succeeded'",('process:release_version:'+deployment,)).fetchone()
  if existing:return json.loads(existing[0])
  path=Releases(self.c).verify(deployment);s=Store(self.root)
  try:
   from digital_life.application.lifecycle.project_access import ProjectAccess
   from digital_life.application.accounts import account_scope as account_scope
   cfg=ProjectAccess(s).config()
   value={'deployment':deployment,'release_hash':row['release'],'git_version':None,'binding':'release-manifest-only'}
   if cfg.get('enabled') and 'project_version_save' in cfg['tools']:
    from digital_life.infrastructure.tools.project_versions import Versions
    with account_scope.audience(s,account_scope.principal(s)['id']) if account_scope.active(s) else nullcontext():resource=ProjectAccess(s).resource('project_version_save')
    files=[];manifest=json.loads((path/'manifest.json').read_text())
    for relative,digest in manifest.items():
     raw=(path/relative).read_bytes()
     if sha(raw)!=digest:raise ContractError('release changed during Git binding')
     files.append((Path(relative),raw))
    repo=Versions(resource,self.root/'project-operations')
    with repo.locked():commit=repo.save_release(files,'Deployment source '+deployment,'deployment'+deployment)
    value.update(git_version=commit,project_root=cfg['root'],binding='verified-release-files-in-git-plus-release-manifest')
   self.record('release_version',deployment,value);return value
  finally:s.close()
 def capture(self,deployment=None,*,target=None,reason='manual'):
  if not self.config().get('enabled'):raise Forbidden('process manager disabled')
  with dispatch_gate(self.root):
   state=self.c.state()
   if state['active_process_run_id']:raise Conflict('checkpoint requires a stopped runtime')
   if deployment is None:
    row=self.c.db.execute("SELECT id FROM deployments WHERE state='active' ORDER BY rowid DESC LIMIT 1").fetchone()
    if row is None:raise ContractError('no deployment to checkpoint')
    deployment=row[0]
   if not Releases(self.c).recoverable(deployment):raise Forbidden('checkpoint release is not currently recoverable')
   binding=self.version(deployment);checkpoint=identifier();base=self.root.parent/'process-snapshots'/self.c.instance
   if base.is_symlink() or base.parent.is_symlink():raise Forbidden('unsafe checkpoint storage')
   base.mkdir(mode=0o700,parents=True,exist_ok=True);folder=base/checkpoint;folder.mkdir(mode=0o700)
   s=Store(self.root)
   try:
    from digital_life.application.memory.data_management import backup_bundle
    backup_bundle(s,folder/'data')
    db=sqlite3.connect((folder/'data/runtime.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:
     configuration=db.execute('SELECT id FROM configuration_versions ORDER BY rowid DESC LIMIT 1').fetchone()[0]
     seq=db.execute('SELECT coalesce(max(event_seq),0) FROM runtime_events').fetchone()[0]
     queues=[dict(r) for r in db.execute('SELECT kind,state,count(*) count FROM jobs WHERE instance_id=? GROUP BY kind,state',(s.instance_id,))]
     pending=db.execute("SELECT count(*) FROM action_attempts WHERE instance_id=? AND state='running'",(s.instance_id,)).fetchone()[0]
     schema=db.execute('PRAGMA user_version').fetchone()[0]
    finally:db.close()
    last=self.c.db.execute('SELECT id,pid,started_at,exited_at FROM process_runs WHERE deployment_id=? ORDER BY rowid DESC LIMIT 1',(deployment,)).fetchone()
    value={'id':checkpoint,'instance':s.instance_id,'created_at':utc(),'deployment':deployment,'target_deployment':target,'source_version':binding,'schema':schema,'configuration':configuration,'event_seq':seq,'queue_summary':queues,'uncertain_actions':pending,'previous_process':dict(last) if last else None,'bundle':str(folder/'data'),'bundle_manifest_sha256':sha((folder/'data/manifest.json').read_bytes()),'reason':reason,'checkpoint_kind':'application-consistent-backup','state_policy':'preserve-current-ledger','thread_memory_restored':False}
    metadata=self.root/'process-checkpoints'
    if metadata.is_symlink():raise Forbidden('unsafe checkpoint metadata')
    metadata.mkdir(mode=0o700,exist_ok=True);temporary=metadata/(checkpoint+'.tmp');temporary.write_text(dumps(value));os.chmod(temporary,0o600);os.replace(temporary,metadata/(checkpoint+'.json'))
    self.record('checkpoint',checkpoint,dict(value,metadata_sha256=sha(dumps(value))))
    return value
   except BaseException:
    # A registered backup is retained for the existing privacy/backup registry.
    if not (folder/'data/manifest.json').exists():shutil.rmtree(folder)
    raise
   finally:s.close()
 def get(self,checkpoint,*,verify_bundle=False):
  if not isinstance(checkpoint,str) or len(checkpoint)!=32 or any(c not in '0123456789abcdef' for c in checkpoint):raise ContractError('invalid checkpoint id')
  path=self.root/'process-checkpoints'/(checkpoint+'.json')
  if path.is_symlink():raise Forbidden('checkpoint symlink')
  value=json.loads(path.read_text());record=self.c.db.execute("SELECT payload FROM control_commands WHERE kind='process.checkpoint' AND command_key=? AND state='succeeded'",('process:checkpoint:'+checkpoint,)).fetchone()
  if record is None or value.get('instance')!=self.c.instance or json.loads(record[0]).get('metadata_sha256')!=sha(dumps(value)):raise Forbidden('checkpoint metadata identity/integrity mismatch')
  if not Releases(self.c).recoverable(value['deployment']):raise Forbidden('checkpoint code incompatible with current data')
  if verify_bundle:
   folder=Path(value['bundle']);manifest=folder/'manifest.json'
   if folder.is_symlink() or manifest.is_symlink() or sha(manifest.read_bytes())!=value['bundle_manifest_sha256']:raise Forbidden('checkpoint backup changed or was redacted')
   data=json.loads(manifest.read_text())
   if data['instance_id']!=self.c.instance:raise Forbidden('backup belongs to another instance')
   for name,digest in data['files'].items():
    file=folder/name
    if file.is_symlink() or folder.resolve() not in file.resolve().parents or sha(file.read_bytes())!=digest:raise Forbidden('checkpoint backup integrity mismatch')
  return value
 def list(self):
  folder=self.root/'process-checkpoints';items=[]
  if folder.is_symlink():raise Forbidden('checkpoint folder symlink')
  if folder.exists():
   for file in sorted(folder.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:30]:
    try:
     value=self.get(file.stem);items.append({'id':value['id'],'deployment':value['deployment'],'created_at':value['created_at'],'git_version':value['source_version'].get('git_version'),'target_deployment':value['target_deployment'],'recoverable':True})
    except (ValueError,OSError):items.append({'id':file.stem,'recoverable':False})
  return items
 def status(self):
  return {'configuration':self.config(),'control':self.c.state(),'checkpoints':self.list(),'thread_memory_restored':False,'recovery_policy':'old compatible code plus current durable ledger; uncertain effects never replayed'}
 def reconcile_uncertain(self):
  if self.c.state()['active_process_run_id']:raise Conflict('stop owned process before recovery reconciliation')
  s=Store(self.root)
  try:
   from digital_life.application.learning.runtime import legacy_protection_present
   if legacy_protection_present(s):return {'required':'qualified existing recovery','automatic_replay':False}
   from digital_life.application.runtime.engine import Engine
   paused=[]
   with s.tx():
    for row in s.db.execute("SELECT id FROM activities WHERE instance_id=? AND state IN ('running','waiting_tool')",(s.instance_id,)).fetchall():
     Engine(s).transition(row[0],'paused','process-checkpoint-reconciliation');paused.append(row[0])
     s.db.execute("UPDATE jobs SET state='cancelled',lease_owner=NULL,lease_token=NULL,lease_expiry=NULL WHERE target_ref=? AND state='queued'",(row[0],))
    attempts=s.db.execute("SELECT id,intent_id FROM action_attempts WHERE instance_id=? AND state='running'",(s.instance_id,)).fetchall()
    for row in attempts:
     s.db.execute("UPDATE action_attempts SET state='unknown',finished_at=? WHERE id=?",(utc(),row[0]))
     s.db.execute("UPDATE action_intents SET state='unknown',lifecycle_revision=lifecycle_revision+1 WHERE id=?",(row[1],))
     s.db.execute("UPDATE outbox SET dispatch_state='unknown' WHERE intent_id=? AND dispatch_state='sent'",(row[1],))
    s.db.execute("UPDATE budget_reservations SET state='usage_unknown',settled_at=? WHERE instance_id=? AND state='reserved'",(utc(),s.instance_id))
    s.db.execute("UPDATE jobs SET state='failed',lease_owner=NULL,lease_token=NULL,lease_expiry=NULL WHERE instance_id=? AND state='leased'",(s.instance_id,))
    value={'paused':paused,'uncertain_actions':len(attempts),'automatic_replay':False,'database_restored':False,'budgets_reset':False}
    s.event('process.recovery_reconciled',payload=value,lane='control')
   return value
  finally:s.close()
 def rollback_record(self,failed,previous,restarted):
  match=next((v for v in self.list() if v.get('target_deployment')==failed and v.get('deployment')==previous),None)
  value={'failed_deployment':failed,'restored_deployment':previous,'restarted':restarted,'checkpoint':match['id'] if match else None,'state_policy':'preserve-current-ledger','thread_memory_restored':False}
  self.record('rollback',identifier(),value);return value
