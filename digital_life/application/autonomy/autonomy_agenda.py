"""T11 bounded commitments and declared exploration interest; no wake authority."""
import json
from datetime import datetime,timezone
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,utc,text,dumps,sha,identifier
from digital_life.infrastructure.processes.dispatch_gate import coordinated
from digital_life.infrastructure.tools.workspace import safe_path

class AutonomyAgenda:
 def __init__(self,store):self.s=store
 def events(self,kind):
  values=[]
  for row in self.s.db.execute('SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type=? ORDER BY event_seq',(self.s.instance_id,'agenda.'+kind)):
   value=self.s.read_artifact(row[0])
   if isinstance(value,dict) and 'redacted_by' not in value:values.append(value)
  return values
 def emit(self,kind,value,activity=None):return self.s.event('agenda.'+kind,payload=value,activity=activity,lane='control')
 def authority(self,actor):
  if actor!=self.s.config()['controller']:raise Forbidden('controller required')
 def config(self):
  rows=self.events('configured');return rows[-1] if rows else {'enabled':False,'version':1}
 @coordinated
 def configure(self,enabled,actor):
  self.authority(actor)
  if type(enabled) is not bool:raise ContractError('boolean required')
  from digital_life.application.lifecycle.control_plane import Control
  c=Control(self.s.root,self.s.instance_id)
  try:
   state=c.state()
   if not state['user_stopped'] or state['active_process_run_id']:raise Conflict('stop before agenda configuration')
  finally:c.close()
  with self.s.tx():self.emit('configured',{'enabled':enabled,'version':1,'actor':actor})
  return self.config()
 def active(self):
  if not self.config()['enabled']:raise Forbidden('agenda disabled')
 def managed(self,ref):return next((r for r in self.events('promise') if r['commitment']==ref),None)
 def bound(self,ref):return next((r for r in self.events('bound') if r['commitment']==ref),None)
 def signal(self,key,content):
  return self.s.insert('perception_signals',channel_id=self.s.rows('perception_channels')[0]['id'],source_actor_id=self.s.config()['controller'],external_id='agenda:'+key,artifact_id=self.s.artifact({'text':content}),received_at=utc())
 @staticmethod
 def timestamp(value):
  try:
   parsed=datetime.strptime(value,'%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
   if len(value)!=24:raise ValueError()
   return parsed
  except (ValueError,TypeError):raise ContractError('UTC timestamp YYYY-MM-DDTHH:MM:SS.sssZ required')
 def verification(self,spec):
  if not isinstance(spec,dict) or set(spec)!={'kind','path','text'} or spec['kind']!='file_contains':raise ContractError('file_contains verifier required')
  safe_path(self.s.root/'workspace',spec['path']);text(spec['text'],4000)
 @coordinated
 def promise(self,content,start_at,due_at,verification,key,actor,max_rounds=3):
  self.authority(actor);self.active();text(content);text(key,120);self.verification(verification)
  if type(max_rounds) is not int or not 1<=max_rounds<=3:raise ContractError('round limit 1-3')
  if self.timestamp(start_at)>self.timestamp(due_at):raise ContractError('start after deadline')
  spec={'content':content,'start_at':start_at,'due_at':due_at,'verification':verification,'max_rounds':max_rounds,'key':key}
  from digital_life.application.services.commitments import Commitments
  from digital_life.application.runtime.scheduling import Queue
  with self.s.tx():
   old=next((r for r in self.events('promise') if r['key']==key),None)
   if old:
    if old['spec']!=spec:raise Conflict('idempotency key changed')
    return old
   if due_at<=utc():raise ContractError('new deadline must be future')
   signal=self.signal(key,content);service=Commitments(self.s);ref=service.propose(actor,content,due_at)
   value={'commitment':ref,'signal':signal,'spec':spec,'key':key};self.emit('promise',value)
   service.transition(ref,'confirmed',signal);service.transition(ref,'active',signal)
   Queue(self.s).enqueue('commitment_due',ref,start_at)
   return value
 @coordinated
 def settle(self,engine):
  """Audit all registered obligations even when new exploration is disabled."""
  from digital_life.application.autonomy.task_loop import TaskLoop
  from digital_life.application.services.commitments import Commitments
  with self.s.tx():
   for p in self.events('promise'):
    ref=p['commitment'];row=self.s.row('commitment_items',ref)
    if row['state'] not in ('active','performing','paused'):continue
    b=self.bound(ref);passed=False
    if b:
     a=self.s.row('activities',b['activity']);checks=TaskLoop(self.s).events(a['id'],'task_loop.verified')
     passed=a['state']=='completed' and bool(checks) and checks[-1]['passed']
    # Time of verification is committed in the same transaction as completion.
    if passed and utc()<=p['spec']['due_at']:
     proof=self.s.evidence(artifact=self.s.artifact({'commitment':ref,'activity':b['activity'],'verification':checks[-1]}),method='independent-goal-verifier')
     self.emit('fulfilled',{'commitment':ref,'activity':b['activity'],'evidence':proof,'at':utc()},b['activity'])
     Commitments(self.s).transition(ref,'fulfilled',p['signal'],proof)
    elif utc()>p['spec']['due_at']:
     Commitments(self.s).transition(ref,'violated',p['signal'])
     self.emit('violated',{'commitment':ref,'at':utc(),'reason':'deadline without timely verified fulfillment'})
     if b and self.s.row('activities',b['activity'])['state'] not in ('completed','cancelled','failed'):engine.cancel(b['activity'],self.s.config()['controller'])
 def fulfillment_allowed(self,ref,evidence):
  from digital_life.application.autonomy.task_loop import TaskLoop
  p=self.managed(ref);b=self.bound(ref)
  if not p:return True
  if not b or utc()>p['spec']['due_at']:return False
  rows=self.events('fulfilled');checks=TaskLoop(self.s).events(b['activity'],'task_loop.verified')
  return bool(checks and checks[-1]['passed'] and self.s.row('activities',b['activity'])['state']=='completed' and any(r['commitment']==ref and r['evidence']==evidence for r in rows))
 @coordinated
 def tick(self,engine):
  self.s.assert_execution_allowed();self.settle(engine)
  with self.s.tx():
   if self.s.db.execute("SELECT 1 FROM activities WHERE instance_id=? AND state NOT IN ('completed','failed','cancelled','paused') LIMIT 1",(self.s.instance_id,)).fetchone():return None
   for p in sorted(self.events('promise'),key=lambda r:(r['spec']['due_at'],r['commitment'])):
    ref=p['commitment']
    if self.s.row('commitment_items',ref)['state']!='active' or self.bound(ref) or p['spec']['start_at']>utc():continue
    activity=engine.submit(p['spec']['content'],'agenda:'+ref,source='commitment')
    from digital_life.application.autonomy.task_loop import TaskLoop
    TaskLoop(self.s).configure(activity,p['spec']['verification'],self.s.config()['controller'],p['spec']['max_rounds'])
    self.s.db.execute('UPDATE activities SET deadline=? WHERE id=?',(min(self.s.row('activities',activity)['deadline'],p['spec']['due_at']),activity))
    goal=engine.details(activity)[3];self.s.insert('commitment_goal_links',commitment_id=ref,goal_id=goal['id'],role='fulfillment')
    self.emit('bound',{'commitment':ref,'activity':activity},activity);return activity
 @coordinated
 def release(self,ref,actor):
  self.authority(actor)
  from digital_life.application.runtime.engine import Engine
  from digital_life.application.services.commitments import Commitments
  with self.s.tx():
   p=self.managed(ref)
   if not p:raise ContractError('unmanaged commitment')
   state=self.s.row('commitment_items',ref)['state']
   if state=='released':return {'commitment':ref,'state':state}
   if state not in ('active','performing','paused'):raise Conflict('terminal commitment')
   b=self.bound(ref)
   if b and self.s.row('activities',b['activity'])['state'] not in ('completed','failed','cancelled'):Engine(self.s).cancel(b['activity'],actor)
   Commitments(self.s).transition(ref,'released',p['signal']);self.emit('released',{'commitment':ref,'at':utc()})
   self.s.db.execute("UPDATE jobs SET state='cancelled' WHERE instance_id=? AND target_ref=? AND state='queued'",(self.s.instance_id,ref))
   return {'commitment':ref,'state':'released'}
 @coordinated
 def question(self,question_id,topic,affinity,path,contains,key,actor):
  self.authority(actor);self.active();text(topic,120);text(key,120);text(contains,4000)
  if type(affinity) not in (int,float) or not 0<=affinity<=1:raise ContractError('affinity 0-1')
  from digital_life.application.autonomy.exploration import Exploration
  if question_id not in Exploration(self.s).questions():raise ContractError('unknown exploration question')
  file=safe_path(self.s.root/'workspace',path)
  if not file.is_file() or file.stat().st_size>65536:raise ContractError('bounded existing file required')
  value={'question':question_id,'topic':topic,'affinity':affinity,'path':path,'contains':contains,'key':key,'fact':sha(dumps([path,contains]))}
  with self.s.tx():
   old=next((r for r in self.events('interest') if r['key']==key),None)
   if old and old!=value:raise Conflict('idempotency key changed')
   if not old:self.emit('interest',value)
  return value
 def interests(self):return {r['question']:r for r in self.events('interest')}
 def score(self,q):
  base=q['expected_gain']-q['cost']
  if not self.config()['enabled']:return base
  i=self.interests().get(q['id'])
  if not i:return base
  count=sum(r['fact']==i['fact'] and r['gain'] is not None for r in self.events('measured'))
  return base+.25*i['affinity']-.25*min(1,count)
 def observe(self,activity,outcome):
  from digital_life.application.autonomy.exploration import Exploration
  from digital_life.application.autonomy.exploration_evidence import ExplorationEvidence
  x=Exploration(self.s);binding=x.binding(activity)
  if not self.config()['enabled'] or not binding:return
  interest=self.interests().get(binding['question_id'])
  if not interest or any(r['result']==outcome['result'] for r in self.events('measured')):return
  canonical=self.s.row('action_results',outcome['result'])
  owner=self.s.db.execute('SELECT d.activity_id FROM action_attempts a JOIN action_intents i ON i.id=a.intent_id AND i.instance_id=a.instance_id JOIN decision_candidates c ON c.id=i.candidate_id AND c.instance_id=i.instance_id JOIN decision_records d ON d.id=c.decision_id AND d.instance_id=c.instance_id WHERE a.id=? AND a.instance_id=?',(canonical['attempt_id'],self.s.instance_id)).fetchone()
  if not owner or owner[0]!=activity or canonical['state']!=outcome['state'] or canonical['outcome_ref']!=outcome['evidence']:raise Forbidden('measurement requires canonical activity outcome')
  record={'question':binding['question_id'],'activity':activity,'result':outcome['result'],'fact':interest['fact'],'gain':None,'value':None,'reason':'no matching fresh verified observation'}
  # Consume only resource publications checked against Executor receipts by V2.
  for r in ExplorationEvidence(x).current():
   if r['activity']!=activity or r['result']!=outcome['result'] or r['action']!={'tool':'read_file','arguments':{'path':interest['path']}}:continue
   receipt=self.s.read_artifact(r['receipt']);data=receipt['evidence'];content=data.get('text')
   if not isinstance(content,str) or sha(content.encode())!=data.get('sha256'):continue
   previous=any(m['fact']==interest['fact'] and m.get('content_hash')==data['sha256'] and m['gain'] is not None for m in self.events('measured'))
   record.update(gain=0 if previous else 1,value=interest['contains'] in content,content_hash=data['sha256'],evidence=r['evidence'],receipt=r['receipt'],reason='verified local fact coverage')
   break
  self.emit('measured',record,activity)
 def context(self,activity):
  if not self.config()['enabled'] and not self.events('promise'):return None
  from digital_life.application.autonomy.exploration import Exploration
  b=Exploration(self.s).binding(activity);p=next((p for p in self.events('promise') if self.bound(p['commitment']) and self.bound(p['commitment'])['activity']==activity),None)
  return {'version':1,'commitment':dict(p,state=self.s.row('commitment_items',p['commitment'])['state']) if p else None,'declared_interest':self.interests().get(b['question_id']) if b else None,'measurement_kind':'local-fact-coverage; not psychological learning','policy_enabled':self.config()['enabled']}
 def check(self,payload,activity):
  if payload.get('autonomy_agenda')!=self.context(activity):raise Forbidden('agenda context changed')
 def status(self):
  from digital_life.application.autonomy.exploration import Exploration
  pending=[dict(p,state=self.s.row('commitment_items',p['commitment'])['state'],binding=self.bound(p['commitment'])) for p in self.events('promise')]
  times=[p['spec'][k] for p in pending if p['state'] in ('active','performing','paused') for k in ('start_at','due_at') if p['spec'][k]>utc()]
  busy=self.s.db.execute("SELECT 1 FROM activities WHERE instance_id=? AND state NOT IN ('completed','failed','cancelled','paused') LIMIT 1",(self.s.instance_id,)).fetchone()
  x=Exploration(self.s).status();bindings=Exploration(self.s).payloads('exploration.bound')
  if x['configuration']['enabled'] and x['remaining_activities']>0 and bindings and bindings[-1]['next_due']>utc():times.append(bindings[-1]['next_due'])
  state='waiting-work' if busy else 'waiting-deadline' if times else x['scheduler_state'] if x['configuration']['enabled'] else 'idle'
  return {'configuration':self.config(),'commitments':pending,'interests':list(self.interests().values()),'measurements':self.events('measured'),'wait_state':state,'next_due':min(times) if times else None,'sleep_authority':'existing control_plane handoff only','inference_started':False}
