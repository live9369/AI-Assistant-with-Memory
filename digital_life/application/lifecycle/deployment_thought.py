"""One fresh, non-action deployment thought through the actual native Engine."""
import json,sqlite3,time
from pathlib import Path
from digital_life.domain.contracts import ContractError,Forbidden,dumps,sha,utc
PROTOCOL='deployment-single-thought-v1'

def expected(nonce):return {'tool':'wait','arguments':{'reason':'deployment-acceptance:'+nonce}}

class OneThought:
 def __init__(self,delegate,nonce):self.delegate=delegate;self.nonce=nonce;self.calls=0;self.name=delegate.name
 def __getattr__(self,name):return getattr(self.delegate,name)
 def generate(self,packet):
  if self.calls:raise Forbidden('deployment acceptance permits one inference only')
  self.calls+=1
  from digital_life.infrastructure.llm.schemas import validate
  value=validate(self.delegate.generate(packet))
  if value['action']!=expected(self.nonce) or value['explanation']!='DEPLOYMENT_OK:'+self.nonce:raise ContractError('deployment thought did not echo the current challenge as wait')
  for group in ('cognition','learning'):
   if any(value.get(group,{}).get(key) for key in ('claims','questions','predictions','plan')):raise Forbidden('deployment thought must not propose learning or actions')
  return value

def run(engine,reasoner,deployment,nonce):
 s=engine.s;started=time.monotonic();activity=None;request=None
 from digital_life.application.services.memory import Memory
 from digital_life.application.services.goals import Goals
 try:
  activity=engine.submit('系统部署验收，只进行一次独立思考。不得调用工具、提出认知候选或学习。action只能wait，reason必须为deployment-acceptance:'+nonce+'。explanation必须精确为DEPLOYMENT_OK:'+nonce+'。','deployment:'+deployment+':'+nonce,'deployment-check')
  with s.tx():
   row=s.db.execute('SELECT id,attributes_json FROM context_snapshots WHERE activity_id=?',(activity,)).fetchone();value=json.loads(row['attributes_json'])
   value['deployment_acceptance']={'protocol':PROTOCOL,'deployment':deployment,'nonce':nonce,'runtime_epoch':engine.identity.epoch,'process_run_id':engine.identity.process_id}
   s.db.execute('UPDATE context_snapshots SET attributes_json=? WHERE id=?',(dumps(value),row['id']))
   s.event('deployment.thought_started',payload=value['deployment_acceptance'],activity=activity,lane='control')
  single=OneThought(reasoner,nonce);request,packet=engine.prepare(activity,single)
  if packet['context_mode']!='fresh_request':raise Forbidden('deployment thought is not independent')
  with s.tx():s.db.execute('UPDATE thought_requests SET attempt_limit=1 WHERE id=?',(request['id'],))
  result=engine.think(activity,single)
  if single.calls!=1 or result.get('accepted') is not True:raise ContractError('deployment thought was not accepted')
  current=s.row('thought_requests',request['id']);accepted=s.row('thought_results',current['accepted_result_id'])
  selected=s.db.execute('SELECT c.action_template FROM decision_candidates c JOIN decision_records d ON d.id=c.decision_id WHERE d.activity_id=? AND c.selected=1 ORDER BY d.rowid DESC LIMIT 1',(activity,)).fetchone()
  if accepted['acceptance']!='accepted' or not selected or json.loads(selected[0])!=expected(nonce):raise ContractError('deployment wait decision was not persisted')
  if s.db.execute('SELECT 1 FROM action_intents i JOIN decision_candidates c ON c.id=i.candidate_id JOIN decision_records d ON d.id=c.decision_id WHERE d.activity_id=?',(activity,)).fetchone():raise Forbidden('deployment acceptance created a tool intent')
  engine.assert_unlocked()
  with s.tx():
   row,context,signal,goal=engine.details(activity)
   if row['state']=='waiting_input':engine.transition(activity,'running','deployment-thought-confirmed')
   Goals(s).transition(goal['id'],'completed',signal['id'],'deployment-thought-accepted')
   engine.transition(activity,'completed','deployment-thought-accepted')
   proof={'protocol':PROTOCOL,'state':'passed','deployment':deployment,'nonce':nonce,'activity':activity,'request':request['id'],'result':accepted['id'],'runtime_epoch':engine.identity.epoch,'process_run_id':engine.identity.process_id,'inference_calls':1,'elapsed_seconds':round(time.monotonic()-started,3),'provider_session':getattr(reasoner,'last_session_id',None)}
   s.event('deployment.thought_passed',payload=proof,activity=activity,lane='control')
  return proof
 except Exception as error:
  with s.tx():s.event('deployment.thought_failed',payload={'deployment':deployment,'nonce':nonce,'error':type(error).__name__,'detail':str(error)[:300],'elapsed_seconds':round(time.monotonic()-started,3)},activity=activity,lane='control')
  raise
 finally:
  if activity:
   with s.tx():
    s.db.execute("UPDATE jobs SET state='cancelled',lease_owner=NULL,lease_token=NULL,lease_expiry=NULL WHERE target_ref=? AND state='queued'",(activity,))
    row=s.row('activities',activity)
   if row['state'] not in ('completed','cancelled','failed'):
    engine.cancel(activity,s.config()['controller'])
    with s.tx():
     _,_,signal,goal=engine.details(activity)
     if goal['state'] in ('accepted','active','paused','candidate'):Goals(s).transition(goal['id'],'cancelled',signal['id'],'deployment-acceptance-failed')
   origins=[s.row('activities',activity)['trigger_event_id']]+[r[0] for r in s.db.execute('SELECT r.id FROM thought_results r JOIN thought_requests q ON q.id=r.request_id WHERE q.activity_id=?',(activity,))]
   for origin in origins:
    memories=s.db.execute("SELECT DISTINCT m.id FROM memory_items m JOIN memory_revisions r ON r.id=m.current_revision_id JOIN memory_source_links l ON l.memory_revision_id=r.id JOIN evidence_items e ON e.id=l.evidence_id WHERE m.state='active' AND e.origin_object_id=?",(origin,)).fetchall()
    for memory in memories:Memory(s).archive(memory[0],s.config()['controller'],'部署独立思考验收记录；退出日常召回，保留审计。')

def verify(root,deployment,proof,nonce):
 if not isinstance(proof,dict) or proof.get('protocol')!=PROTOCOL or proof.get('state')!='passed' or proof.get('nonce')!=nonce or proof.get('deployment')!=deployment or proof.get('inference_calls')!=1:raise ContractError('deployment thought proof missing or misbound')
 root=Path(root);db=sqlite3.connect((root/'runtime.sqlite').as_uri()+'?mode=ro',uri=True,timeout=5);db.row_factory=sqlite3.Row
 try:
  row=db.execute('SELECT q.request_artifact_id,q.runtime_epoch,q.process_run_id,q.accepted_result_id,r.acceptance,r.validation_state,r.response_artifact_id,a.state FROM thought_requests q JOIN thought_results r ON r.id=q.accepted_result_id JOIN activities a ON a.id=q.activity_id WHERE q.id=? AND q.activity_id=? AND r.id=?',(proof['request'],proof['activity'],proof['result'])).fetchone()
  if not row or row['acceptance']!='accepted' or row['validation_state']!='valid' or row['state']!='completed' or row['process_run_id']!=proof['process_run_id'] or row['runtime_epoch']!=proof['runtime_epoch']:raise ContractError('deployment thought not accepted in actual ledger')
  def artifact(ref):
   r=db.execute('SELECT storage_ref,hash FROM artifacts WHERE id=?',(ref,)).fetchone();path=root/'blobs'/r[0]
   if path.is_symlink() or path.parent!=root/'blobs':raise Forbidden('unsafe deployment proof artifact')
   raw=path.read_bytes()
   if sha(raw)!=r[1]:raise ContractError('deployment proof artifact changed')
   return json.loads(raw)
  packet=artifact(row['request_artifact_id']);value=artifact(row['response_artifact_id'])
  if packet.get('context_mode')!='fresh_request' or packet.get('deployment_acceptance',{}).get('nonce')!=nonce or value['action']!=expected(nonce) or value['explanation']!='DEPLOYMENT_OK:'+nonce:raise ContractError('deployment thought content mismatch')
  if db.execute('SELECT count(*) FROM thought_attempts WHERE request_id=?',(proof['request'],)).fetchone()[0]!=1:raise ContractError('deployment acceptance was retried')
 finally:db.close()
