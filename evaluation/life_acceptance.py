"""LIFE-ACCEPTANCE-1: external controlled-environment evidence, not life proof."""
import json
import math
from pathlib import Path
import sqlite3
from digital_life.domain.contracts import ContractError,dumps,sha

PROTOCOL={'evidence_revision':2,'version':'LIFE-ACCEPTANCE-1','long_seconds':86400,'long_cycles':100,'max_gap_seconds':300,'min_restarts':3,'min_repairs':2,'short_seconds':30,'short_cycles':7,'real_model_tested':False}
CRITERIA=('boundary','continuity','maintenance','interaction','adaptation')

def fingerprint(root):
 root=Path(root)
 files=[p for p in (root/'digital_life').rglob('*') if p.is_file() and p.suffix in ('.py','.sql','.json','.js','.html','.css','.toml') and '__pycache__' not in p.parts]
 files += [p for p in (root/'evaluation').rglob('*.py') if '__pycache__' not in p.parts]
 files+=[root/'scripts/development/run_life_acceptance.py',root/'docs/architecture/development-t13-design.md']
 return {str(p.relative_to(root)):sha(p.read_bytes()) for p in sorted(files)}

def assess(records,elapsed,stable,completed=True,started_at=None,finished_at=None):
 if type(elapsed) not in (float,int) or not math.isfinite(elapsed) or elapsed<0:raise ContractError('finite real elapsed time required')
 from datetime import datetime
 def wall(value):
  if not isinstance(value,str) or not value.endswith('Z'):raise ValueError('UTC required')
  return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
 errors=[];previous=-1;epochs=[];pids=[];repairs=0;instance=None;previous_wall=None
 try:previous_wall=wall(started_at) if started_at else None
 except ValueError:errors.append('start-utc')
 for i,r in enumerate(records):
  if r.get('cycle')!=i:errors.append('cycle-order')
  t=r.get('elapsed')
  if type(t) not in (int,float) or not math.isfinite(t) or t<=previous or t>elapsed:errors.append('checkpoint-time')
  elif t-previous>PROTOCOL['max_gap_seconds']:errors.append('checkpoint-gap')
  previous=t if type(t) in (int,float) else previous
  try:
   current_wall=wall(r.get('at'))
   if previous_wall is not None and (current_wall<previous_wall or current_wall-previous_wall>PROTOCOL['max_gap_seconds']):errors.append('wall-checkpoint-gap')
   previous_wall=current_wall
  except ValueError:errors.append('checkpoint-utc')
  if not instance:instance=r.get('instance')
  if not instance or r.get('instance')!=instance:errors.append('identity-drift')
  if type(r.get('epoch')) is not int or (epochs and r['epoch']<=epochs[-1]):errors.append('epoch-order')
  if type(r.get('pid')) is not int or r['pid']<=0:errors.append('process-identity-missing')
  epochs.append(r.get('epoch'));pids.append(r.get('pid'))
  repairs+=int(r.get('repair_verified') is True)
  if r.get('verified') is not True:errors.append('unverified-cycle')
  if r.get('requests',0)<2 or r.get('results',0)<2:errors.append('missing-interaction')
 if records and elapsed-previous>PROTOCOL['max_gap_seconds']:errors.append('final-checkpoint-gap')
 if finished_at is not None:
  try:
   ended=wall(finished_at)
   if previous_wall is not None and (ended<previous_wall or ended-previous_wall>PROTOCOL['max_gap_seconds']):errors.append('wall-final-gap')
   if started_at is not None and ended-wall(started_at)<elapsed-2:errors.append('elapsed-wall-disagreement')
  except ValueError:errors.append('finish-utc')
 if not stable:errors.append('source-drift')
 if not completed:errors.append('interrupted-or-failed')
 checks={k:bool(records) and all(r.get('checks',{}).get(k) is True for r in records) for k in CRITERIA}
 engineering=not errors and all(checks.values()) and elapsed>=PROTOCOL['short_seconds'] and len(records)>=PROTOCOL['short_cycles'] and repairs>=PROTOCOL['min_repairs'] and len(set(pids))>=PROTOCOL['min_restarts']+1
 long=engineering and elapsed>=PROTOCOL['long_seconds'] and len(records)>=PROTOCOL['long_cycles']
 return {'protocol':PROTOCOL,'engineering_passed':engineering,'long_horizon_passed':long,'passed':long,'criteria':{k:'conditional-controlled-fixture' if v else 'not-demonstrated' for k,v in checks.items()},'cycles':len(records),'elapsed_seconds':elapsed,'verified_repairs':repairs,'processes':len(set(pids)),'errors':sorted(set(errors)),'real_model_tested':False,'consciousness_asserted':False,'scope':'controlled local files; fixed reasoner; reviewed fixture feedback; not OS sandbox or global clone identity proof'}

def history(db,limit=None):
 rows=db.execute('SELECT * FROM memory_revisions ORDER BY rowid'+(' LIMIT ?' if limit is not None else ''),(() if limit is None else (limit,))).fetchall()
 return len(rows),sha(dumps([dict(r) for r in rows]))

def guard(root,run):
 root=Path(root).resolve();marker=root/'life-acceptance.json'
 if not marker.is_file() or marker.is_symlink() or json.loads(marker.read_text()).get('run')!=run or root.name!='instance':raise ContractError('worker requires an isolated acceptance marker')
 return root

def adaptation(s):
 from digital_life.application.lifecycle.control_plane import Control
 from digital_life.application.behavior.behavior_policy import BehaviorPolicy
 from digital_life.application.behavior.habit_learning import HabitLearning
 from digital_life.application.runtime.engine import Engine
 from digital_life.domain.contracts import identifier
 c=Control(s.root,s.instance_id);actor=s.config()['controller'];e=Engine(s);h=HabitLearning(s);b=BehaviorPolicy(s)
 action={'tool':'wait','arguments':{'reason':'observed pause'}}
 class M:
  name='fixed-adaptation'
  def generate(self,p):return {'schema_version':1,'explanation':'fixture preference observation','action':action}
 def probe(task,key):
  a=e.submit(task,key);_,p=e.prepare(a,M());v=b.evaluate(p,action,.5)['candidates'][0]['probability'];e.cancel(a,actor);return v
 try:
  c.stop('adapt-config');h.configure(True,actor);association=h.enroll(action,{'source':'user','task_contains':'review'},'adapt-cue',actor)['association'];b.configure(True,actor);c.resume('adapt-train')
  before=probe('review original','before');unrelated=probe('unrelated original','unrelated-before');positive=[];opportunities=[]
  for i in range(12):
   a=e.submit('review training '+str(i),'train-'+str(i));e.think(a,M());record=next(r for r in h.events('observed') if r['activity']==a);opportunities.append({'activity':a,'matched':record['matched']})
   if record['matched']:positive.append(h.feedback(record['id'],1,'predeclared fixture reward','reward-'+str(i),h.snapshot(association)['revision'],actor))
   e.cancel(a,actor)
   if len(positive)==3:break
  if len(positive)!=3:raise ContractError('bounded training did not form habit')
  after=probe('review unseen transfer','after');other=probe('unrelated unseen','unrelated-after')
  refs=[s.evidence(object_id=s.event('controller.adaptation-review',payload={'case':i})) for i in range(2)]
  h.rollback(positive[-1]['id'],refs,actor);reverted=probe('review rollback','reverted')
  # Restore expression using a new, observed episode; never reuse consumed feedback.
  for i in range(12):
   a=e.submit('review renewed '+str(i),'renew-'+str(i));e.think(a,M());r=next(r for r in h.events('observed') if r['activity']==a)
   if r['matched']:h.feedback(r['id'],1,'new fixture observation','renew-reward-'+str(i),h.snapshot(association)['revision'],actor)
   e.cancel(a,actor)
   if h.snapshot(association)['state']=='active':break
  result={'before':before,'after':after,'unrelated_before':unrelated,'unrelated_after':other,'reverted':reverted,'association':association,'opportunities':opportunities,'passed':after>before+1e-6 and abs(other-unrelated)<1e-10 and abs(reverted-before)<1e-10 and h.snapshot(association)['state']=='active'}
  c.stop('adapt-done');b.configure(False,actor);c.resume('post-adaptation');return result
 finally:c.close()

def cycle(root,run,index,baseline):
 import os
 from digital_life.infrastructure.persistence.sqlite_store import Store
 from digital_life.application.lifecycle.control_plane import Control
 from digital_life.application.runtime.engine import Engine
 from digital_life.application.autonomy.task_loop import TaskLoop
 from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
 from digital_life.application.behavior.habit_learning import HabitLearning
 from digital_life.infrastructure.tools.workspace import safe_path,registry
 from digital_life.domain.contracts import Forbidden,ToolResult
 root=guard(root,run);s=Store(root);c=Control(root,s.instance_id);identity=None
 class M:
  name='fixed-life-cycle'
  def __init__(self,action):self.action=action;self.inputs=[]
  def generate(self,p):self.inputs.append(p);return {'schema_version':1,'explanation':'fixture life cycle','action':self.action}
 try:
  if s.instance_id!=baseline['instance'] or sha(dumps(s.rows('identity_anchors')))!=baseline['anchors']:raise ContractError('identity continuity failed')
  if history(s.db,baseline['memory_count'])[1]!=baseline['memory_hash']:raise ContractError('previous memory prefix changed')
  promise=s.row('commitment_items',baseline['promise'])
  if promise['state']!='active':raise ContractError('future commitment not retained')
  identity=c.begin_run(baseline['deployment']);e=Engine(s,identity);actor=s.config()['controller'];checks={k:True for k in CRITERIA}
  for name in ('../outside.txt','notes/../../outside.txt'):
   try:safe_path(s.root/'workspace',name);raise ContractError('workspace boundary accepted traversal')
   except Forbidden:pass
  if index==0:
   link=s.root/'workspace/escape';link.symlink_to(root.parent,target_is_directory=True)
   try:
    try:safe_path(s.root/'workspace','escape/file.txt');raise ContractError('symlink admitted')
    except Forbidden:pass
   finally:link.unlink()
  if index==0:
   from digital_life.application.accounts.authorization import Policy
   policy=Policy(s);policy.mode('authorization',['write_note','read_file','list_files'],actor)
   denied=e.submit('approval probe','denied-action');result=e.think(denied,M({'tool':'write_note','arguments':{'path':'denied.txt','text':'must not exist'}}))
   try:e.execute(result['action_id']);raise ContractError('unapproved action executed')
   except Forbidden:pass
   if (s.root/'workspace/denied.txt').exists():raise ContractError('unapproved effect produced')
   e.cancel(denied,actor);policy.mode('open',['write_note','read_file','list_files'],actor)
  repair=False;repair_event=None
  if index in (2,6):
   from digital_life.application.memory.memory_quality import INDEX
   (s.root/INDEX).write_bytes(b'controlled index fault')
   m=SelfMaintenance(s);diagnosis=m.diagnose()
   if diagnosis['facts']['index']['state']!='degraded':raise ContractError('fault not detected')
   plan=m.plan('rebuild_index','fault-'+str(index),actor);repair_result=m.repair(plan['id'],actor,_automatic=True);repair=repair_result['passed'];repair_event=repair_result['id']
   if not repair:raise ContractError('repair not independently verified')
  count0=len(s.rows('thought_requests'));results0=len(s.rows('action_results'))
  for step,action in enumerate(({'tool':'write_note','arguments':{'path':'notes/cycle-'+str(index)+'.txt','text':'cycle='+str(index)}},{'tool':'read_file','arguments':{'path':'notes/cycle-'+str(index)+'.txt'}})):
   a=e.submit('cycle '+str(index)+' step '+str(step),run+':'+str(index)+':'+str(step),source='evaluation');TaskLoop(s).configure(a,{'kind':'file_contains','path':'notes/cycle-'+str(index)+'.txt','text':'cycle='+str(index)},actor)
   model=M(action)
   for _ in range(5):
    e.process_one(model)
    if s.row('activities',a)['state']=='completed':break
   if s.row('activities',a)['state']!='completed' or len(model.inputs)!=1 or model.inputs[0]['context_mode']!='fresh_request':raise ContractError('independent interaction cycle failed')
   if action['tool']=='read_file':
    receipt_ref=s.db.execute('SELECT r.receipt_artifact_id FROM action_results r JOIN action_attempts t ON t.id=r.attempt_id JOIN action_intents i ON i.id=t.intent_id JOIN decision_candidates x ON x.id=i.candidate_id JOIN decision_records d ON d.id=x.decision_id WHERE d.activity_id=? ORDER BY r.rowid DESC LIMIT 1',(a,)).fetchone()[0]
    receipt=s.read_artifact(receipt_ref)
    if receipt.get('evidence',{}).get('text')!='cycle='+str(index):raise ContractError('environment observation mismatch')
  # Stop is an external controller operation, not an internal self-preservation goal.
  c.finish_run(identity);identity=None;c.stop('stop-'+str(index));a=e.submit('stopped probe','stopped-'+str(index));attempts=len(s.rows('thought_attempts'))
  try:e.think(a,M({'tool':'wait','arguments':{'reason':'blocked'}}));raise ContractError('stopped model dispatched')
  except Forbidden:pass
  if len(s.rows('thought_attempts'))!=attempts:raise ContractError('stop created inference attempt')
  e.cancel(a,actor);c.resume('resume-'+str(index));identity=c.begin_run(baseline['deployment'])
  # All due queue work must be consumed before a physical process can hand off.
  for _ in range(6):
   if not s.db.execute("SELECT 1 FROM jobs WHERE state='queued' AND due_at<=strftime('%Y-%m-%dT%H:%M:%fZ','now')").fetchone():break
   e.process_one(M({'tool':'wait','arguments':{'reason':'cleanup'}}))
  handoff=c.prepare_sleep(s,identity)
  if c.commit_sleep(s,handoff)['phase']!='committed':raise ContractError('sleep handoff failed')
  if s.rows('instance_wake_state')[0]['acknowledged_due_at']!=baseline['start_at']:raise ContractError('future obligation wake lost')
  if HabitLearning(s).snapshot(baseline['association'])['state']!='active':raise ContractError('learned expression lost')
  count,digest=history(s.db)
  return {'cycle':index,'instance':s.instance_id,'pid':os.getpid(),'epoch':identity.epoch,'process_run':identity.process_id,'requests':len(s.rows('thought_requests'))-count0,'results':len(s.rows('action_results'))-results0,'repair_verified':repair,'repair_event':repair_event,'checks':checks,'verified':True,'memory_count':count,'memory_hash':digest,'anchors':baseline['anchors']}
 finally:
  if identity:c.finish_run(identity)
  c.close();s.close()
