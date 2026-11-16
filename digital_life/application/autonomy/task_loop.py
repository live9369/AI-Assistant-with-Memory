"""Opt-in, event-sourced finite task loops with independent workspace verification."""
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,utc,text
from digital_life.application.runtime.scheduling import Queue
from digital_life.infrastructure.tools.workspace import safe_path
from digital_life.infrastructure.processes.dispatch_gate import coordinated

class TaskLoop:
 def __init__(self,store):self.s=store
 def events(self,activity,kind):
  return [self.s.read_artifact(r[0]) for r in self.s.db.execute('SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type=? ORDER BY event_seq',(self.s.instance_id,activity,kind))]
 def config(self,activity):
  rows=self.events(activity,'task_loop.configured');return rows[-1] if rows else None
 @coordinated
 def configure(self,activity,verification,actor,max_rounds=3):
  if actor!=self.s.config()['controller']:raise Forbidden('controller required')
  row=self.s.row('activities',activity)
  if row['state']!='pending' or self.s.db.execute('SELECT 1 FROM thought_requests WHERE activity_id=?',(activity,)).fetchone():raise Conflict('configure loop before thought preparation')
  if self.config(activity):raise Conflict('loop already configured')
  from digital_life.application.autonomy.exploration import Exploration
  if Exploration(self.s).binding(activity):raise Conflict('task loop cannot mix with exploration')
  if not isinstance(verification,dict) or set(verification)!={'kind','path','text'} or verification['kind']!='file_contains':raise ContractError('unsupported goal verifier')
  safe_path(self.s.root/'workspace',verification['path']);text(verification['text'],4000)
  if type(max_rounds) is not int or not 1<=max_rounds<=3:raise ContractError('round limit must be 1-3')
  with self.s.tx():self.s.event('task_loop.configured',payload={'verification':verification,'max_rounds':max_rounds,'actor':actor},activity=activity,lane='control')
  return self.status(activity)
 def bind_project(self,activity):
  if self.config(activity):return
  from digital_life.application.lifecycle.project_access import ProjectAccess
  if ProjectAccess(self.s).context() is None:raise Forbidden('project directory not authorized')
  self.s.event('task_loop.configured',payload={'verification':{'kind':'project_task'},'max_rounds':None,'budget_control':'activity-budget-v1','actor':self.s.config()['controller']},activity=activity,lane='control')
 def project_budget(self,activity):
  cfg=self.config(activity)
  if not cfg or cfg['verification']['kind']!='project_task':return None
  from digital_life.application.runtime.scheduling import Budget
  return Budget(self.s).remaining(activity)
 def thought_tokens(self,activity):
  budget=self.project_budget(activity)
  if budget is None:return 4096
  if budget['tokens']<1024 or budget['attempts']<1 or budget['time_ms']<=0 or not budget['deadline_valid'] or budget['usage_unknown']:raise Forbidden('project task budget cannot support another thought')
  return min(4096,budget['tokens'])
 def stop_budget(self,engine,activity,budget):
  message='本任务预算不足，已暂停。已完成的工具结果和文件修改均保留；没有继续调用模型或执行新动作。'
  self.s.event('task_loop.budget_stopped',payload={'remaining':budget,'message':message,'round':self.round(activity)},activity=activity,lane='control')
  if self.s.row('activities',activity)['state']=='running':engine.transition(activity,'paused','project-budget-limit')
  return {'continued':False,'reason':'project-budget-limit','message':message,'remaining':budget}
 def finish_project(self,engine,activity):
  cfg=self.config(activity)
  if not cfg or cfg['verification']['kind']!='project_task':return False
  outcomes=self.events(activity,'task_loop.observed')
  if not outcomes or any(o['state']!='succeeded' for o in outcomes):raise Forbidden('project results are not verified')
  row,context,signal,goal=engine.details(activity)
  from digital_life.application.services import Goals
  self.s.event('task_loop.verified',payload={'passed':True,'reason':'model concluded after verified tool receipts; not independent proof of semantic correctness','round':self.round(activity)},activity=activity)
  Goals(self.s).transition(goal['id'],'completed',signal['id'],'project-tool-receipts-and-reply')
  engine.transition(activity,'completed','project-tool-receipts-and-reply');return True
 def round(self,activity):return 1+len(self.events(activity,'task_loop.advanced'))
 def status(self,activity):return {'configuration':self.config(activity),'round':self.round(activity),'observations':self.events(activity,'task_loop.observed'),'verifications':self.events(activity,'task_loop.verified'),'followups':self.events(activity,'task_loop.followup')}
 def context(self,activity):
  value=self.status(activity)
  for observation in value['observations']:
   if observation.get('receipt'):observation['receipt_snapshot']=self.s.read_artifact(observation['receipt'])
  budget=self.project_budget(activity)
  if budget is not None:value['remaining_budget']=budget
  value['public_responses']=[self.s.read_artifact(r[0])['explanation'] for r in self.s.db.execute("SELECT r.response_artifact_id FROM thought_results r JOIN thought_requests q ON q.id=r.request_id AND q.instance_id=r.instance_id WHERE q.activity_id=? AND q.instance_id=? AND r.acceptance='accepted' ORDER BY r.rowid",(activity,self.s.instance_id))]
  return value
 def verify(self,activity):
  cfg=self.config(activity);condition=cfg['verification'];path=safe_path(self.s.root/'workspace',condition['path'])
  if not path.is_file():return {'passed':False,'reason':'expected file absent'}
  if path.stat().st_size>65536:return {'passed':False,'reason':'file exceeds verification limit'}
  from digital_life.domain.contracts import sha
  from digital_life.infrastructure.persistence.tool_learning_meter import external_read_before,external_read_after,artifact_failed
  external_read_before(path.stat().st_size)
  try:
   with path.open('rb') as stream:raw=stream.read(65537)
  except OSError:
   artifact_failed();raise
  external_read_after(len(raw))
  if len(raw)>65536:return {'passed':False,'reason':'file grew beyond verification limit'}
  try:passed=condition['text'] in raw.decode('utf-8')
  except UnicodeError:passed=False
  return {'passed':passed,'reason':'independent file content check','content_hash':sha(raw)}
 def advance(self,engine,activity,reason):
  cfg=self.config(activity);row=self.s.row('activities',activity)
  if row['cancel_requested_at']:raise Forbidden('activity cancelled')
  budget=self.project_budget(activity)
  if budget is not None:
   if budget['tokens']<1024 or budget['attempts']<1 or budget['time_ms']<=0 or not budget['deadline_valid'] or budget['usage_unknown']:return self.stop_budget(engine,activity,budget)
  if (budget is None and self.round(activity)>=cfg['max_rounds']) or row['deadline']<=utc():
   if row['state']=='running':engine.transition(activity,'paused','task-loop-limit')
   return {'continued':False,'reason':'round or deadline limit'}
  self.s.event('task_loop.advanced',payload={'round':self.round(activity)+1,'reason':reason},activity=activity)
  Queue(self.s).enqueue('think',activity);return {'continued':True}
 def observed(self,engine,activity,outcome):
  with self.s.tx():
   canonical=self.s.row('action_results',outcome['result'])
   owner=self.s.db.execute('SELECT d.activity_id FROM action_attempts a JOIN action_intents i ON i.id=a.intent_id AND i.instance_id=a.instance_id JOIN decision_candidates c ON c.id=i.candidate_id AND c.instance_id=i.instance_id JOIN decision_records d ON d.id=c.decision_id AND d.instance_id=c.instance_id WHERE a.id=? AND a.instance_id=?',(canonical['attempt_id'],self.s.instance_id)).fetchone()
   if not owner or owner[0]!=activity or canonical['state']!=outcome['state'] or canonical['outcome_ref']!=outcome['evidence']:raise Forbidden('outcome does not belong to this activity')
   outcome=dict(outcome,receipt=canonical['receipt_artifact_id'])
   if any(o['result']==outcome['result'] for o in self.events(activity,'task_loop.observed')):return {'duplicate':True}
   observation={'result':outcome['result'],'state':outcome['state'],'receipt':outcome.get('receipt'),'evidence':outcome['evidence']}
   if outcome.get('source_update') is not None:observation['source_update']=outcome['source_update']
   self.s.event('task_loop.observed',payload=observation,activity=activity)
   if self.config(activity)['verification']['kind']=='project_task':
    if outcome['state']!='succeeded':engine.transition(activity,'paused','unknown-or-failed-project-effect');return {'completed':False,'paused':True,'state':outcome['state']}
    return dict(self.advance(engine,activity,'project-tool-observed'),completed=False,state=outcome['state'])
   verification=self.verify(activity);self.s.event('task_loop.verified',payload=dict(verification,round=self.round(activity)),activity=activity)
   if outcome['state']!='succeeded':engine.transition(activity,'paused','unknown-or-failed-effect');return {'completed':False,'paused':True}
   if verification['passed']:
    row,context,signal,goal=engine.details(activity)
    from digital_life.application.services import Goals
    Goals(self.s).transition(goal['id'],'completed',signal['id'],'independent-goal-verifier');engine.transition(activity,'completed','goal-verified');return {'completed':True,'verification':verification}
   return dict(self.advance(engine,activity,'goal-not-yet-met'),completed=False,verification=verification)
 @coordinated
 def resume(self,engine,activity,message,actor):
  if actor!=self.s.config()['controller']:raise Forbidden('controller required')
  engine.assert_unlocked();row=self.s.row('activities',activity)
  if not self.config(activity) or row['state'] not in ('waiting_input','paused'):raise Conflict('loop not waiting')
  if self.project_budget(activity) is None and self.round(activity)>=self.config(activity)['max_rounds']:raise Conflict('round limit exhausted')
  if row['cancel_requested_at'] or row['deadline']<=utc():raise Forbidden('activity cancelled or expired')
  # Approval waits belong to permission flow, not human-input continuation.
  from digital_life.application.monitoring.management import Management
  if Management(self.s).approvals({'activity_id':activity,'status':'pending','limit':1})['items']:raise Conflict('approval still pending')
  unresolved=self.s.db.execute("SELECT 1 FROM action_intents i JOIN decision_candidates c ON c.id=i.candidate_id AND c.instance_id=i.instance_id JOIN decision_records d ON d.id=c.decision_id AND d.instance_id=c.instance_id WHERE d.activity_id=? AND d.instance_id=? AND i.state IN ('running','unknown') LIMIT 1",(activity,self.s.instance_id)).fetchone()
  if unresolved:raise Conflict('external effect unresolved; verify before continuation')
  with self.s.tx():
   self.s.event('task_loop.followup',payload={'text':text(message,4000),'actor':actor},activity=activity)
   self.s.db.execute('UPDATE activities SET input_epoch=input_epoch+1 WHERE id=?',(activity,));engine.transition(activity,'running','explicit-followup');return self.advance(engine,activity,'explicit-followup')
