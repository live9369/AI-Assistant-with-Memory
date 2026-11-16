"""Only core experience-return, source-domain and bounded method-effect cases."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.chat.chat import Chat
from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
from digital_life.application.cognition.cognition_memory import publish,ENCODING,available
from digital_life.application.services.memory import Memory
from digital_life.application.autonomy.exploration import Exploration
from digital_life.application.autonomy.continuous_exploration import ContinuousExploration
from digital_life.application.cognition.method_experience import MethodExperience
from digital_life.domain.contracts import utc,Forbidden

class Model:
 name='fixture'
 def __init__(self,value='南侧架子',kind='reported',cue=''):self.value=value;self.kind=kind;self.cue=cue;self.inputs=[]
 def generate(self,p):
  self.inputs.append(p);ref=next(ref for ref,value in p['cognition_sources'].items() if value==p['observation']['text'])
  return {'schema_version':3,'action':{'tool':'wait','arguments':{'reason':'reply'}},'explanation':'记录来源，但不确认现实真值。','cognition':{'claims':[{'subject':'纸灯','predicate':'位置','value':self.value,'kind':self.kind,'source_ref':ref,'quote':p['cognition_sources'][ref]}],'questions':[],'predictions':[],'plan':[]}}

class ReturnTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'life';self.s=Store.prepare(self.root)
  (self.root/'WAKE_DISABLED').unlink();CognitiveUpdates(self.s).configure(True,self.s.config()['controller'])
  from digital_life.application.lifecycle.control_plane import Control
  c=Control(self.root,self.s.instance_id);c.resume('fixture');c.close();self.engine=Engine(self.s)
 def tearDown(self):self.s.close();self.tmp.cleanup()
 def turn(self,message,model=None,key='one',session='first'):
  r=Chat(self.s).send(session,{'text':message,'idempotency_key':key,'expected_last_activity_id':None});a=r['activity_id']
  self.engine.process_one(model or Model());return a
 def latest(self):return self.s.db.execute('SELECT * FROM cognition_belief_revisions ORDER BY rowid DESC LIMIT 1').fetchone()
 def learned(self):return [dict(r) for r in self.s.db.execute('SELECT m.id,r.id revision,r.content FROM memory_items m JOIN memory_revisions r ON r.id=m.current_revision_id WHERE r.encoding_method=? ORDER BY m.rowid',(ENCODING,))]
 def test_chat_new_session_retrieves_labeled_candidate_and_publishes_once(self):
  self.turn('纸灯放在南侧架子。');revision=self.latest()['id'];before=len(self.learned());publish(self.s,revision)
  self.assertEqual(len(self.learned()),before)
  a=Chat(self.s).send('second',{'text':'纸灯的位置是什么？','idempotency_key':'two','expected_last_activity_id':None})['activity_id']
  packet=self.engine.prepare(a,Model())[1];items=[m for m in packet['selected_memories'] if m['source_kind']=='cognition-representation']
  self.assertTrue(items);self.assertIn('未核实候选',items[0]['content']);self.assertIn('南侧架子',items[0]['content']);self.assertEqual(packet['context_mode'],'fresh_request')
 def test_confirmation_correction_and_withdrawal_keep_history(self):
  self.turn('纸灯放在南侧架子。');first=self.latest();c=CognitiveUpdates(self.s)
  accepted=c.confirm(first['id'],first['id'],self.s.config()['controller']);self.assertEqual(self.s.row('cognition_beliefs',first['belief_id'])['current_revision_id'],accepted)
  self.assertFalse(available(self.s,self.learned()[0]['id'],current_only=True))
  second_activity=self.turn('更正：纸灯现在移到窗边。',Model('窗边'),key='two',session='second');second=self.latest()
  self.assertEqual(self.s.row('cognition_beliefs',first['belief_id'])['current_revision_id'],accepted)
  c.confirm(second['id'],accepted,self.s.config()['controller'])
  old_memory=next(r for r in self.learned() if accepted in r['content']);self.assertFalse(available(self.s,old_memory['id'],current_only=True))
  new_memory=self.learned()[-1];self.assertIn('窗边',new_memory['content'])
  probe=self.engine.submit('纸灯以前放在哪里？','historical-probe');context=self.engine.details(probe)[1]['id']
  old_items=Memory(self.s).retrieve('纸灯以前放在哪里？',probe,context)['items']
  self.assertTrue(any(v.get('temporal_status','').startswith('historical') and '南侧架子' in v['content'] for v in old_items))
  current_items=Memory(self.s).retrieve('纸灯的位置是什么？',probe,context)['items']
  self.assertFalse(any(v.get('temporal_status','').startswith('historical') for v in current_items))
  signal=self.s.row('activities',second_activity)['trigger_event_id']
  parent=self.s.db.execute('SELECT r.memory_id FROM memory_source_links l JOIN evidence_items e ON e.id=l.evidence_id JOIN memory_revisions r ON r.id=l.memory_revision_id WHERE e.origin_object_id=?',(signal,)).fetchone()[0]
  Memory(self.s).archive(parent,self.s.config()['controller'],'撤回来源')
  self.assertEqual(Memory(self.s).readers(new_memory['id']),set());self.assertIn('南侧架子',self.s.row('cognition_belief_revisions',first['id'])['content'])
 def exploration_method(self):
  from digital_life.application.lifecycle.control_plane import Control
  control=Control(self.root,self.s.instance_id);control.stop('configure-exploration');control.close()
  Exploration(self.s).configure(self.s.config()['controller'],True,6,3,60,mode='continuous')
  control=Control(self.root,self.s.instance_id);control.resume('resume');control.close()
  class Explore:
   name='fixture'
   def generate(inner,p):
    self.assertEqual(p['output_schema_version'],6);self.assertIn('learning_sources',p)
    ref=next(iter(p['learning_sources']));quote=p['learning_sources'][ref]
    return {'schema_version':6,'action':{'tool':'wait','arguments':{'reason':'step done'}},'explanation':'这只是本次方法建议。','reflection':{'directions':[],'decision':'finish','understanding':'本轮提案已完成','next_step':'结束','reason':'资料足够','reopen_condition':'新信息','evidence_refs':p['exploration']['allowed_evidence_refs'][:1]},'inquiry':{'prediction':'无需额外扩题','observation':'无工具观察','revision':'保留有来源提案','remaining_questions':[],'next_attempts':[],'direction_status':'finished','finish_basis':'goal_achieved'},'learning':{'claims':[{'subject':'资料比较','predicate':'方法','value':'先读规则再对照任务','kind':'method','source_ref':ref,'quote':quote,'valid_at':'','context_contains':'资料比较'}]}}
  # A normal recorded input provides experience; process its chat first.
  self.turn('纸灯放在南侧架子。')
  with patch('digital_life.application.autonomy.continuous_exploration.secrets.randbits',return_value=0):self.engine.process_one(Explore())
  row=self.latest();self.assertEqual(json.loads(row['content'])['kind'],'method');self.assertEqual(row['acceptance_state'],'held');self.assertTrue(any('方法建议' in r['content'] for r in self.learned()))
  return row
 def test_v6_exploration_returns_into_same_cognition_memory(self):
  self.exploration_method()
 def test_method_feedback_changes_only_applicable_direction_and_can_retract(self):
  row=self.exploration_method();c=CognitiveUpdates(self.s);accepted=c.confirm(row['id'],row['id'],self.s.config()['controller'])
  memory=next(r for r in self.learned() if accepted in r['content']);direction={'title':'资料比较该怎么做','next_step':'先核对规则','evidence_refs':[memory['revision']]};m=MethodExperience(self.s)
  self.assertEqual(m.effect(direction)['delta'],0)
  feedback_activity=self.engine.submit('这次资料比较采用先读规则的方法，结果有效。','feedback')
  signal=self.s.row('activities',feedback_activity)['trigger_event_id'];f=m.feedback(accepted,'success',signal,'明确的控制者方法评价',self.s.config()['controller'])
  again=m.feedback(accepted,'success',signal,'明确的控制者方法评价',self.s.config()['controller']);self.assertTrue(again['reused'])
  self.assertGreater(m.effect(direction)['delta'],0);self.assertEqual(m.effect(dict(direction,title='聊聊天',next_step='回应问候'))['delta'],0)
  self.engine.process_one(Model())
  c=ContinuousExploration(Exploration(self.s));key='c'*64
  with self.s.tx():c.emit('direction',dict(direction,id=key,kind='explore',expected_gain=.8,cost=.1,state='ready',understanding='',no_progress=0,steps=0,due_at=utc(),parent_id=None,reopen_condition=''))
  with patch('digital_life.application.autonomy.continuous_exploration.utc',side_effect=lambda seconds=0:utc(120+seconds)),patch('digital_life.application.autonomy.continuous_exploration.secrets.randbits',return_value=0):
   c.tick(self.engine,Exploration(self.s).config(),Exploration(self.s).payloads('exploration.bound'))
  selected=c.values('selection')[-1];option=next(v for v in selected['candidates'] if v.get('direction')==key)
  self.assertGreater(option['features']['method_experience'],0);self.assertEqual(option['method_effect']['methods'][0]['samples'],1)
  self.assertAlmostEqual(sum(v['probability'] for v in selected['candidates']),1)
  m.retract(f['id'],'这条评价需要撤回',self.s.config()['controller']);self.assertEqual(m.effect(direction)['delta'],0)
 def test_private_derived_candidate_is_not_recalled_by_other_account(self):
  from digital_life.application.accounts.accounts import install,Accounts,public
  from digital_life.application.accounts import account_scope as scope
  from digital_life.application.lifecycle.control_plane import Control
  c=Control(self.root,self.s.instance_id);c.stop('install-accounts');c.close();self.s.close();install(self.root);self.s=Store(self.root);self.engine=Engine(self.s)
  auth=Accounts(self.root,self.s.instance_id)
  try:
   root=dict(public(auth.row(auth.root_id())),bootstrap=True)
   alice,bob=[auth.provision(self.s,root,dict(username=name,display_name=name,role='member',password='long-test-password'))['account'] for name in ('alice','bob')]
   c=Control(self.root,self.s.instance_id);c.resume('account-fixture');c.close()
   with scope.audience(self.s,alice['id']):a=Chat(self.s).send(alice['thread_id'],dict(text='纸灯是ALICE_PRIVATE，放在南侧架子。',idempotency_key='one',expected_last_activity_id=None))['activity_id']
   self.engine.think(a,Model());memory=self.learned()[-1]
   with scope.audience(self.s,bob['id']):
    self.assertFalse(scope.can_recall(self.s,memory['id']))
    b=Chat(self.s).send(bob['thread_id'],dict(text='纸灯的位置？',idempotency_key='one',expected_last_activity_id=None))['activity_id']
   _,packet=self.engine.prepare(b,Model());self.assertNotIn('ALICE_PRIVATE',str(packet))
   with scope.audience(self.s,root['id']):self.assertTrue(scope.can_recall(self.s,memory['id']))
  finally:auth.close()
 def test_invalid_learning_quote_is_rejected(self):
  from digital_life.infrastructure.llm.schemas import schema_for
  schema=schema_for({'output_schema_version':6,'exploration':{'mode':'continuous','allowed_evidence_refs':['a'*32]},'learning_sources':{'a'*32:'原文'}})
  self.assertEqual(schema['properties']['learning']['properties']['claims']['items']['properties']['source_ref']['enum'],['a'*32])
  a=self.engine.submit('纸灯在南侧架子','badquote');_,p=self.engine.prepare(a,Model());out=Model().generate(p);out['cognition']['claims'][0]['quote']='不存在的原文'
  with self.assertRaises(Forbidden):CognitiveUpdates(self.s).check(a,p,out)

 def test_withdrawn_shared_ancestor_does_not_expand_every_branch(self):
  memory=Memory(self.s);actor=self.s.config()['self_actor'];controller=self.s.config()['controller']
  with self.s.tx():
   evidence=self.s.evidence(artifact=self.s.artifact({'fixture':'source'}),method='fixture')
   base=memory.encode('共享原始依据',evidence)['memory_id'];parents=[base]
   for level in range(10):
    parents=[memory.derive('派生记录'+str(level),parents,evidence,actor)['memory_id'] for _ in range(2)]
   head=memory.derive('最终记录',parents,evidence,actor)['memory_id']
  memory.archive(base,controller,'来源撤回')
  with patch.object(self.s,'row',wraps=self.s.row) as reads:
   self.assertEqual(memory.readers(head),set())
   self.assertLess(sum(call.args[0]=='memory_items' for call in reads.call_args_list),80)

 def test_ranked_retrieval_skips_denied_and_checks_only_needed_records(self):
  memory=Memory(self.s);actor=self.s.config()['self_actor'];controller=self.s.config()['controller']
  with self.s.tx():
   evidence=self.s.evidence(artifact=self.s.artifact({'fixture':'source'}),method='fixture')
   for _ in range(8):memory.encode('alpha target',evidence)
   denied=memory.encode('alpha target alpha',evidence)['memory_id']
  memory.restrict(denied,[],controller)
  a=self.engine.submit('alpha target','ranked');context=self.engine.details(a)[1]['id']
  result=memory.retrieve('alpha target',a,context,limit=2,actor=actor)
  self.assertEqual(len(result['items']),2)
  self.assertNotIn(self.s.row('memory_items',denied)['current_revision_id'],[r['revision_id'] for r in result['items']])
  event=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE event_type='memory.retrieval_timing' ORDER BY event_seq DESC LIMIT 1").fetchone()
  self.assertEqual(self.s.read_artifact(event[0])['checked_candidates'],3)

if __name__=='__main__':unittest.main()
