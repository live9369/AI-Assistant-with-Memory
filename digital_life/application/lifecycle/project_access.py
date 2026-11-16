"""Explicit controller-owned project grants; no implicit filesystem expansion."""
import json,os
from pathlib import Path
from digital_life.domain.contracts import Forbidden,ContractError,Conflict,utc
from digital_life.domain.project_files import NAMES,PROPERTIES
from digital_life.infrastructure.processes.dispatch_gate import coordinated
from digital_life.application.accounts import account_scope as account_scope

class ProjectAccess:
 def __init__(self,store):self.s=store
 def config(self):
  row=self.s.db.execute("SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type='project_access.configured' ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,)).fetchone()
  return dict(self.s.read_artifact(row[1]),generation=row[0]) if row else {'enabled':False}
 @coordinated
 def configure(self,root,actor,*,enabled=True,auto_approve=False,exclude=(),tools=None):
  from digital_life.application.learning.runtime import strict_legacy_boundary
  strict_legacy_boundary(self.s,'project_directory_configuration')
  if actor!=self.s.config()['controller']:raise Forbidden('controller required')
  if type(enabled)is not bool or type(auto_approve)is not bool:raise ContractError('boolean options required')
  if not enabled:
   with self.s.tx():
    self.s.event('project_access.configured',payload={'enabled':False,'actor':actor},lane='control')
    self.s.db.execute('UPDATE policy_epochs SET epoch=epoch+1,updated_at=? WHERE instance_id=?',(utc(),self.s.instance_id))
   return self.config()
  tools=list(NAMES) if tools is None else list(tools)
  if not tools or len(set(tools))!=len(tools) or set(tools)-set(NAMES):raise ContractError('explicit supported project tools required')
  p=Path(root).expanduser()
  if not p.is_absolute() or not p.is_dir() or p.is_symlink() or p.resolve()==Path('/'):raise ContractError('real absolute project directory required')
  p=p.resolve();denied={'work','releases','snapshots','account-backups','node_modules','__pycache__'}
  if p==self.s.root or self.s.root in p.parents:raise Forbidden('instance data cannot be a project root')
  if p in self.s.root.parents:denied.add(str(self.s.root.relative_to(p)).split('/')[0])
  for value in exclude:
   if not isinstance(value,str) or not value or Path(value).is_absolute() or '..' in Path(value).parts:raise ContractError('relative exclusions required')
   denied.add(value.rstrip('/'))
  info=p.stat()
  with self.s.tx():
   for name in NAMES:
    if not self.s.db.execute('SELECT 1 FROM tool_definitions WHERE instance_id=? AND name=?',(self.s.instance_id,name)).fetchone():
     cap=self.s.insert('capability_definitions',name=name,description='explicit project-directory '+name)
     self.s.insert('tool_definitions',name=name,version=1,input_schema={'type':'object','properties':PROPERTIES[name]},capability_id=cap,supports_idempotency=int(name in ('project_write','project_edit')),supports_query=1)
   self.s.event('project_access.configured',payload={'enabled':True,'root':str(p),'root_identity':[info.st_dev,info.st_ino],'exclude':sorted(denied),'tools':tools,'auto_approve':auto_approve,'actor':actor},lane='control')
   self.s.db.execute('UPDATE policy_epochs SET epoch=epoch+1,updated_at=? WHERE instance_id=?',(utc(),self.s.instance_id))
  return self.config()
 def resource(self,tool):
  cfg=self.config()
  if not cfg.get('enabled') or tool not in cfg['tools']:raise Forbidden('project directory not authorized')
  if account_scope.active(self.s) and (account_scope.current(self.s) or {}).get('role')!='root':raise Forbidden('only root can operate project files')
  info=Path(cfg['root']).stat()
  if [info.st_dev,info.st_ino]!=cfg['root_identity']:raise Forbidden('authorized directory was replaced')
  return {'kind':'project-files','root':cfg['root'],'root_identity':cfg['root_identity'],'exclude':cfg['exclude'],'generation':cfg['generation'],'tools':cfg['tools']}
 def check(self,tool,scope):
  if self.resource(tool)!=scope:raise Forbidden('project authorization changed')
 def context(self):
  cfg=self.config()
  if not cfg.get('enabled'):return None
  if account_scope.active(self.s) and (account_scope.current(self.s) or {}).get('role')!='root':return None
  return {**self.resource(cfg['tools'][0]),'auto_approve':cfg['auto_approve'],'instructions':'Use project_read to obtain a file hash before project_write; empty expected_sha256 only creates new files. Paths are relative to this root. Tool receipts are actual observations; do not claim edits before execution. Version tools use a private Git repository: status returns expected_head; save only selected paths; restore requires current file hash and appends a new version. Edits automatically checkpoint before/after when project_version_save is allowed. No shell or deployment permission is implied.'}
