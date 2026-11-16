"""T02-T04 isolated functionality, no live data or cloud calls."""
import json
import tempfile
from pathlib import Path
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.autonomy.task_loop import TaskLoop
from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
from digital_life.application.learning.learning_pipeline import LearningPipeline
from digital_life.application.services.memory import Memory
from digital_life.domain.contracts import ContractError,Forbidden,Conflict

class StepFixture(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'instance';self.s=Store.prepare(self.root);self.actor=self.s.config()['controller'];self.engine=Engine(self.s)
  self.addCleanup(self.tmp.cleanup);self.addCleanup(self.s.close)
 def unlock(self):
  (self.root/'WAKE_DISABLED').unlink()
  if (self.root/'control.sqlite').exists():
   from digital_life.application.lifecycle.control_plane import Control
   c=Control(self.root,self.s.instance_id);c.resume('isolated-test');c.close()
 def outcome(self,activity,name,content,state='succeeded'):
  from digital_life.application.services.decisions import Decisions
  from digital_life.application.accounts.authorization import Policy
  from digital_life.application.runtime.execution import Executor
  from digital_life.domain.contracts import ToolResult
  row,context,signal,goal=self.engine.details(activity);action={'tool':'read_file','arguments':{'path':'fixture.txt'}}
  decision=Decisions(self.s).finalize(activity,goal['id'],context['id'],[action]);intent=Policy(self.s).propose(activity,decision['selected'],action);approval=Policy(self.s).request(intent);Policy(self.s).approve(approval,self.actor)
  return Executor(self.s,self.engine.identity).dispatch(intent,backend=lambda *args:ToolResult('received',state,'pass' if state=='succeeded' else 'unknown',{'fixture':name,'text':content}))

class TaskLoopTests(StepFixture):
 def test_multiround_independent_goal_verification_and_reopen(self):
  a=self.engine.submit('two steps','two');loop=TaskLoop(self.s);loop.configure(a,{'kind':'file_contains','path':'answer.txt','text':'done'},self.actor);self.unlock()
  class Model:
   name='fixture'
   def generate(self,request):return {'schema_version':1,'explanation':'waiting','action':{'tool':'wait','arguments':{'reason':'wait'}}}
  self.engine.think(a,Model());loop.resume(self.engine,a,'continue',self.actor);request,payload=self.engine.prepare(a,Model());self.assertEqual(loop.round(a),2);self.assertTrue(request['request_parent_id']);self.assertEqual(payload['task_loop']['followups'][0]['text'],'continue')
  result=loop.observed(self.engine,a,self.outcome(a,'one','x'));self.assertTrue(result['continued']);self.assertEqual(loop.round(a),3)
  self.s.close();self.s=Store(self.root);self.addCleanup(self.s.close);self.engine=Engine(self.s);loop=TaskLoop(self.s);self.assertEqual(loop.round(a),3)
  (self.root/'workspace/answer.txt').write_text('done');result=loop.observed(self.engine,a,self.outcome(a,'two','done'));self.assertTrue(result['completed']);self.assertEqual(self.s.row('activities',a)['state'],'completed')
 def test_unknown_effect_limits_and_paths(self):
  a=self.engine.submit('task','one');loop=TaskLoop(self.s)
  with self.assertRaises(Forbidden):loop.configure(a,{'kind':'file_contains','path':'../bad','text':'x'},self.actor)
  loop.configure(a,{'kind':'file_contains','path':'a','text':'done'},self.actor,max_rounds=1);self.unlock();self.engine.transition(a,'running','test');(self.root/'workspace/a').write_text('done')
  result=loop.observed(self.engine,a,self.outcome(a,'unknown','done',state='unknown'));self.assertTrue(result['paused']);self.assertNotEqual(self.s.row('activities',a)['state'],'completed')
  with self.assertRaises(Conflict):loop.resume(self.engine,a,'again',self.actor)

class CognitionTests(StepFixture):
 def model(self,forged=False):
  class Model:
   name='fixture'
   def generate(inner,request):
    source=next(iter(request['cognition_sources']))
    return {'schema_version':3,'explanation':'noted','action':{'tool':'wait','arguments':{'reason':'wait'}},'cognition':{'claims':[{'subject':'陈明','predicate':'职业','value':'植物学家','source_ref':'forged' if forged else source,'quote':'陈明是植物学家','kind':'reported'}],'questions':['在哪里研究？'],'predictions':[{'outcome':'稍后得到回答','probability':.5,'due_seconds':60}],'plan':[{'action':{'tool':'wait','arguments':{'reason':'等待证据'}},'expected':'得到证据','depends_on':[]}]}}
  return Model()
 def test_structured_candidate_then_review_and_revision(self):
  c=CognitiveUpdates(self.s);c.configure(True,self.actor);a=self.engine.submit('陈明是植物学家','one');self.unlock();self.engine.think(a,self.model());self.assertEqual(len(self.s.rows('cognition_beliefs')),1);self.assertEqual(len(self.s.rows('cognition_predictions')),1);self.assertEqual(len(self.s.rows('cognition_plans')),1)
  candidate=self.s.rows('cognition_belief_revisions')[0];self.assertEqual(candidate['acceptance_state'],'held');new=c.confirm(candidate['id'],candidate['id'],self.actor);self.assertEqual(self.s.row('cognition_belief_revisions',new)['acceptance_state'],'accepted');self.assertEqual(len(self.s.rows('cognition_belief_revisions')),2)
  with self.assertRaises(Conflict):c.confirm(candidate['id'],new,self.actor)
 def test_forged_source_fails_without_knowledge_commit(self):
  c=CognitiveUpdates(self.s);c.configure(True,self.actor);a=self.engine.submit('陈明是植物学家','one');self.unlock()
  with self.assertRaises(Forbidden):self.engine.think(a,self.model(forged=True))
  self.assertEqual(self.s.rows('cognition_beliefs'),[])

class LearningPipelineTests(StepFixture):
 def make_memory(self):
  a=self.engine.submit('资料：liwei喜欢蓝色','origin');return self.s.rows('memory_items')[0]['id']
 def cases(self):return [{'query':'liwei喜欢什么颜色','contains':'liwei喜欢绿色','not_contains':'liwei喜欢蓝色'},{'query':'liwei偏好颜色','contains':'liwei喜欢绿色','not_contains':'liwei喜欢蓝色'}]
 def test_measured_learning_commit_and_compensating_rollback(self):
  memory=self.make_memory();p=LearningPipeline(self.s);feedback=p.feedback(memory,'资料：liwei喜欢绿色','控制者明确更正颜色',self.actor);evaluation=p.evaluate(feedback['proposal'],self.cases(),self.actor);self.assertTrue(evaluation['eligible']);self.assertFalse(evaluation['adopted'])
  commit=p.commit(feedback['proposal'],evaluation['evaluation'],self.actor);self.assertIn('绿色',self.s.row('memory_revisions',self.s.row('memory_items',memory)['current_revision_id'])['content'])
  with self.assertRaises(Conflict):p.commit(feedback['proposal'],evaluation['evaluation'],self.actor)
  e=self.s.event('fixture.rollback_evidence',payload={'reason':'独立复核'},lane='control');evidence=self.s.evidence(object_id=e,method='review');p.rollback(commit,[feedback['evidence'],evidence],self.actor);self.assertIn('蓝色',self.s.row('memory_revisions',self.s.row('memory_items',memory)['current_revision_id'])['content']);self.assertEqual(len(self.s.rows('memory_revisions')),3);self.assertEqual(self.s.row('learning_update_proposals',feedback['proposal'])['state'],'reverted')
 def test_no_gain_rejects_and_no_trial_cannot_commit(self):
  memory=self.make_memory();p=LearningPipeline(self.s);feedback=p.feedback(memory,'资料：liwei喜欢蓝色','保持原内容',self.actor)
  cases=[dict(x,contains='蓝色',not_contains='') for x in self.cases()];result=p.evaluate(feedback['proposal'],cases,self.actor);self.assertFalse(result['eligible']);self.assertEqual(self.s.row('learning_update_proposals',feedback['proposal'])['state'],'rejected')
  with self.assertRaises(Conflict):p.commit(feedback['proposal'],result['evaluation'],self.actor)
  self.assertEqual(len(self.s.rows('memory_revisions')),1)

class IntegratedLoopTests(StepFixture):
 def test_real_approved_tools_goal_checked_after_two_distinct_thoughts(self):
  from digital_life.application.accounts.authorization import Policy
  a=self.engine.submit('read source then write answer','integration');TaskLoop(self.s).configure(a,{'kind':'file_contains','path':'answer.txt','text':'done'},self.actor);(self.root/'workspace/source.txt').write_text('source data');self.unlock()
  class Model:
   name='fixture'
   def generate(inner,request):
    action={'tool':'read_file','arguments':{'path':'source.txt'}} if request['task_loop']['round']==1 else {'tool':'write_note','arguments':{'path':'answer.txt','text':'done'}}
    return {'schema_version':1,'explanation':'step','action':action}
  first=self.engine.process_one(reasoner=Model());Policy(self.s).approve(first['approval_id'],self.actor)
  observation=self.engine.process_one(reasoner=Model());self.assertFalse(observation['completed']);self.assertNotEqual(self.s.row('activities',a)['state'],'completed')
  second=self.engine.process_one(reasoner=Model());Policy(self.s).approve(second['approval_id'],self.actor);final=self.engine.process_one(reasoner=Model());self.assertTrue(final['completed']);self.assertEqual(len(self.s.rows('thought_requests')),2);self.assertEqual(len(self.s.rows('action_results')),2)
  loops=TaskLoop(self.s);before=loops.round(a);record=loops.events(a,'task_loop.observed')[-1];self.assertTrue(loops.observed(self.engine,a,record)['duplicate']);self.assertEqual(loops.round(a),before)
 def test_round_limit_pauses_without_completion(self):
  a=self.engine.submit('limited','limited');loop=TaskLoop(self.s);loop.configure(a,{'kind':'file_contains','path':'missing.txt','text':'done'},self.actor,max_rounds=1);self.unlock();self.engine.transition(a,'running','test');out=loop.observed(self.engine,a,self.outcome(a,'wrong','not done'));self.assertFalse(out['continued']);self.assertEqual(self.s.row('activities',a)['state'],'paused')

class LearningGateTests(StepFixture):
 make_memory=LearningPipelineTests.make_memory
 cases=LearningPipelineTests.cases
 def test_regression_rejected_and_stale_version_cannot_commit(self):
  memory=self.make_memory();pipeline=LearningPipeline(self.s);feedback=pipeline.feedback(memory,'资料：liwei喜欢绿色','更正',self.actor)
  cases=[self.cases()[0],{'query':'liwei原始颜色','contains':'蓝色','not_contains':''}];result=pipeline.evaluate(feedback['proposal'],cases,self.actor);self.assertGreater(result['regression'],0)
  with self.assertRaises(Conflict):pipeline.commit(feedback['proposal'],result['evaluation'],self.actor)
  second=pipeline.feedback(memory,'资料：liwei喜欢绿色','更正2',self.actor);result=pipeline.evaluate(second['proposal'],self.cases(),self.actor);e=self.s.evidence(artifact=self.s.artifact({'another':'change'}));Memory(self.s).revise(memory,1,'其他更正',e)
  with self.assertRaises(Conflict):pipeline.commit(second['proposal'],result['evaluation'],self.actor)
 def test_wrong_actor_and_duplicate_cases_rejected(self):
  memory=self.make_memory();pipeline=LearningPipeline(self.s)
  with self.assertRaises(Forbidden):pipeline.feedback(memory,'candidate','reason','not-controller')
  f=pipeline.feedback(memory,'candidate','reason',self.actor)
  with self.assertRaises(ContractError):pipeline.evaluate(f['proposal'],[self.cases()[0]]*2,self.actor)

class CognitionRevisionTests(StepFixture):
 model=CognitionTests.model
 def test_counter_statement_stays_candidate_until_review(self):
  c=CognitiveUpdates(self.s);c.configure(True,self.actor);a=self.engine.submit('陈明是植物学家','first');self.unlock();self.engine.think(a,self.model());initial=self.s.rows('cognition_belief_revisions')[0];accepted=c.confirm(initial['id'],initial['id'],self.actor)
  class Corrector:
   name='fixture'
   def generate(inner,payload):return {'schema_version':3,'explanation':'更正候选','action':{'tool':'wait','arguments':{'reason':'待审阅'}},'cognition':{'claims':[{'subject':'陈明','predicate':'职业','value':'地质学家','source_ref':next(k for k,v in payload['cognition_sources'].items() if '陈明是地质学家' in v),'quote':'陈明是地质学家','kind':'reported'}],'questions':[],'predictions':[],'plan':[]}}
  a=self.engine.submit('更正：陈明是地质学家','second');self.engine.think(a,Corrector());belief=self.s.rows('cognition_beliefs')[0];self.assertEqual(belief['current_revision_id'],accepted);candidate=self.s.rows('cognition_belief_revisions')[-1];new=c.confirm(candidate['id'],accepted,self.actor);self.assertIn('地质学家',self.s.row('cognition_belief_revisions',new)['content']);self.assertIn('植物学家',self.s.row('cognition_belief_revisions',accepted)['content'])

class UnresolvedLoopTests(StepFixture):
 def test_unresolved_effect_cannot_resume_even_with_remaining_rounds(self):
  a=self.engine.submit('unknown effect','unknown');loop=TaskLoop(self.s);loop.configure(a,{'kind':'file_contains','path':'answer.txt','text':'done'},self.actor,max_rounds=3);self.unlock();self.engine.transition(a,'running','test');loop.observed(self.engine,a,self.outcome(a,'unknown','data',state='unknown'))
  with self.assertRaises(Conflict):loop.resume(self.engine,a,'try again',self.actor)

class CognitiveToolSourceTests(StepFixture):
 def test_v3_claim_can_quote_verified_tool_observation(self):
  from digital_life.application.accounts.authorization import Policy
  CognitiveUpdates(self.s).configure(True,self.actor);a=self.engine.submit('读取source.txt后写入answer.txt','source-loop');TaskLoop(self.s).configure(a,{'kind':'file_contains','path':'answer.txt','text':'done'},self.actor);(self.root/'workspace/source.txt').write_text('陈明是植物学家');self.unlock()
  class Model:
   name='fixture'
   def generate(inner,payload):
    first=payload['task_loop']['round']==1;claims=[]
    if not first:
     source=next(k for k,v in payload['cognition_sources'].items() if '陈明是植物学家' in v);claims=[{'subject':'陈明','predicate':'职业','value':'植物学家','source_ref':source,'quote':'陈明是植物学家','kind':'reported'}]
    return {'schema_version':3,'explanation':'step','action':{'tool':'read_file','arguments':{'path':'source.txt'}} if first else {'tool':'write_note','arguments':{'path':'answer.txt','text':'done'}},'cognition':{'claims':claims,'questions':[],'predictions':[],'plan':[]}}
  for i in range(2):
   step=self.engine.process_one(reasoner=Model());Policy(self.s).approve(step['approval_id'],self.actor);self.engine.process_one(reasoner=Model())
  self.assertEqual(self.s.row('activities',a)['state'],'completed');self.assertEqual(len(self.s.rows('cognition_beliefs')),1);self.assertEqual(self.s.rows('cognition_belief_revisions')[0]['acceptance_state'],'held')
