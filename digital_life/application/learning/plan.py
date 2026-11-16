"""Explicit IM plan inspection and evidence gates; never executes a life task."""
import json
import os
import tempfile
import fcntl
from pathlib import Path
from digital_life.domain.contracts import ContractError,sha

PLAN='docs/plan/tool-observation-learning-implementation-status-v0.1.json'
STATES={'pending','designing','implementing','validating','complete','blocked'}

def _safe_path(root,name,prefix):
 if not isinstance(name,str) or Path(name).is_absolute() or '..' in Path(name).parts:raise ContractError('relative project path required')
 allowed=root/prefix;p=root/name
 if not p.is_relative_to(allowed):raise ContractError('file outside permitted project directory')
 for candidate in (allowed,p):
  current=root
  for part in candidate.relative_to(root).parts:
   current=current/part
   if current.is_symlink():raise ContractError('symlink plan path denied')
 return p

def _file(root,name,prefix):
 p=_safe_path(root,name,prefix)
 if not p.is_file():raise ContractError('plan file missing')
 return p

def _authorized(plan,task):
 gate=task['authorization_gate']
 if gate=='isolated_implementation_authorization':return plan.get('implementation_authorized') is True and plan.get('runtime_tests_authorized') is True
 if gate=='evaluation_material_preparation_authorization':return plan.get('material_preparation_authorized') is True
 # Dedicated model/role/instance permission is deliberately not inferred from ordinary coding permission.
 return plan.get('specific_authorizations',{}).get(gate) is True

def inspect(project):
 root=Path(project).resolve();path=_file(root,PLAN,'docs/plan')
 return _inspect(root,json.loads(path.read_text()))

def _inspect(root,plan):
 freeze=_file(root,plan['frozen_record'],'docs/architecture')
 if sha(freeze.read_bytes())!=plan['frozen_record_sha256']:raise ContractError('frozen design record changed; review required')
 baseline=json.loads(freeze.read_text())
 if baseline['status']!='frozen_design' or baseline['contract_id']!=plan['frozen_contract']:raise ContractError('frozen design mismatch')
 for group in ('normative_documents','decision_sources'):
  for name,digest in baseline[group].items():
   if sha(_file(root,name,'docs/architecture').read_bytes())!=digest:raise ContractError('frozen source or normative document changed')
 drift=[]
 for name,digest in baseline['code_snapshot'].items():
  p=root/name
  if not p.is_file() or sha(p.read_bytes())!=digest:drift.append(name)
 seen={};ready=[];blocked=[]
 for task in plan['tasks']:
  id=task['id']
  if id in seen or task['status'] not in STATES:raise ContractError('invalid task identifier or status')
  if any(dep not in seen for dep in task['depends_on']):raise ContractError('dependencies must precede task')
  deps=all(seen[d]['status']=='complete' for d in task['depends_on'])
  if task['status'] not in ('pending','blocked') and not deps:raise ContractError('task advanced before dependency completion')
  if task['status'] in ('designing','implementing','validating','complete') and not task.get('design'):raise ContractError('task design required before work')
  if task.get('design'):_file(root,task['design'],'docs')
  if task['status']=='complete':
   evidence=_file(root,task.get('evidence'),'outputs/acceptance/tool-learning')
   if sha(evidence.read_bytes())!=task.get('evidence_sha256'):raise ContractError('task evidence hash mismatch')
   result=json.loads(evidence.read_text())
   if result.get('task')!=id or result.get('passed') is not True or result.get('source_stable_during_verification') is not True or result.get('frozen_record_sha256')!=plan['frozen_record_sha256'] or result.get('contract')!=plan['frozen_contract'] or not result.get('completion_scope'):raise ContractError('task evidence not a matching passed stable verification')
  elif deps:
   (ready if _authorized(plan,task) else blocked).append(id)
  seen[id]=task
 return {'tasks':plan['tasks'],'ready':ready,'authorization_blocked':blocked,'historical_code_drift':drift,'execution_performed':False,'runner_implemented':False}

def transition(project,task_id,status,*,design=None,evidence=None,reason=None):
 root=Path(project).resolve();_file(root,PLAN,'docs/plan')
 lock=_safe_path(root,'docs/plan/.tool-learning-plan.lock','docs/plan')
 fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
 try:
  fcntl.flock(fd,fcntl.LOCK_EX)
  return _transition(root,task_id,status,design,evidence,reason)
 finally:
  fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

def _transition(root,task_id,status,design,evidence,reason):
 path=_file(root,PLAN,'docs/plan');plan=json.loads(path.read_text());_inspect(root,plan);task=next((t for t in plan['tasks'] if t['id']==task_id),None)
 if not task or status not in STATES:raise ContractError('unknown task or state')
 if task['status']=='complete':raise ContractError('completed history cannot be overwritten; explicit revalidation record required')
 if not _authorized(plan,task):raise ContractError('task requires separate authorization')
 allowed={'pending':{'designing','blocked'},'designing':{'implementing','blocked'},'implementing':{'validating','blocked'},'validating':{'complete','implementing','blocked'},'blocked':{'designing'}}
 if status not in allowed[task['status']]:raise ContractError('invalid plan transition')
 if not all(next(t for t in plan['tasks'] if t['id']==d)['status']=='complete' for d in task['depends_on']):raise ContractError('task dependencies incomplete')
 task['status']=status
 if design is not None:task['design']=design
 if evidence is not None:
  file=_file(root,evidence,'outputs/acceptance/tool-learning');task['evidence']=evidence;task['evidence_sha256']=sha(file.read_bytes())
 if status=='blocked' and not reason:raise ContractError('blocked condition required')
 task['status_reason']=reason
 # Validate in memory, then atomically replace; readers never see an unverified completion.
 result=_inspect(root,plan)
 fd,name=tempfile.mkstemp(prefix='.im-plan-',dir=path.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as stream:
   stream.write(json.dumps(plan,ensure_ascii=False,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
  os.replace(name,path)
 finally:
  if os.path.exists(name):os.unlink(name)
 return result
