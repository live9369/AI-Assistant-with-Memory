"""Repository task gates, separate from life-instance state and deployment."""
import json
from pathlib import Path
from digital_life.domain.contracts import ContractError,sha

STATES={'pending','designing','implementing','validating','complete'}
def inspect_plan(project):
 project=Path(project).resolve();plan=json.loads((project/'docs/plan/task-status.json').read_text());tasks=plan['tasks'];seen={};ready=[]
 def file(name):
  if not isinstance(name,str):raise ContractError('missing evidence/design path')
  p=(project/name).resolve()
  if not p.is_relative_to(project) or not p.is_file():raise ContractError('plan file missing or outside project: '+name)
  return p
 for task in tasks:
  if task['id'] in seen or task['status'] not in STATES:raise ContractError('invalid task identifier/state')
  if any(dep not in seen for dep in task['depends_on']):raise ContractError('dependencies must precede task')
  dependencies=all(seen[dep]['status']=='complete' for dep in task['depends_on'])
  if task['status']!='pending' and not dependencies:raise ContractError('task advanced before dependency completion: '+task['id'])
  if task['status']=='complete':
   file(task['design']);evidence=file(task['evidence']);value=json.loads(evidence.read_text())
   if task.get('evidence_sha256')!=sha(evidence.read_bytes()) or value.get('task')!=task['id'] or value.get('passed') is not True or not task.get('completion_scope'):raise ContractError('task lacks matching passed evidence: '+task['id'])
   if task['id']=='T13' and (value.get('engineering_passed') is not True or value.get('long_horizon_passed') is not True or value.get('joint_matches_current_source') is not True):raise ContractError('T13 requires engineering, long-horizon and matching-source evidence')
  elif dependencies:ready.append(task['id'])
  seen[task['id']]=task
 return {'tasks':tasks,'next_ready':ready,'deployment_performed':False,'scope':'repository workflow only'}
