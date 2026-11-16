import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.application.runtime.engine import Engine
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.behavior.habit_candidates import HabitCandidates
from digital_life.application.behavior.habit_learning import HabitLearning
from digital_life.application.behavior.behavior_policy import BehaviorPolicy
from digital_life.application.services.memory import Memory
from digital_life.domain.contracts import Forbidden, Conflict
from digital_life.infrastructure.persistence.sqlite_store import Store

ACTION={'tool':'wait','arguments':{'reason':'review complete'}}
class Model:
 name='fixture'
 def generate(self,p):return {'schema_version':1,'explanation':'reviewed','action':ACTION}

class CandidateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.s=Store.prepare(Path(self.tmp.name)/'life');self.addCleanup(self.s.close)
  self.actor=self.s.config()['controller'];self.h=HabitLearning(self.s);self.c=HabitCandidates(self.s);self.e=Engine(self.s)
  self.c.configure(True,self.actor);BehaviorPolicy(self.s).configure(True,self.actor)
  (self.s.root/'WAKE_DISABLED').unlink();self.control=Control(self.s.root,self.s.instance_id);self.addCleanup(self.control.close);self.control.resume('fixture');self.n=0
 def episode(self,task='review brief',source='user'):
  self.n+=1;a=self.e.submit(task,'turn-'+str(self.n),source)
  with patch('digital_life.application.behavior.behavior_policy.secrets.randbits',return_value=0):self.e.think(a,Model())
  return a
 def pending(self):
  for _ in range(3):self.episode()
  return self.c.status()['items'][0]
 def enable_habits_stopped(self):
  self.control.stop('review');self.h.configure(True,self.actor)
 def test_repetition_is_pending_without_behavior_influence_and_replay_is_idempotent(self):
  v=self.pending();self.assertEqual(v['state'],'pending');self.assertEqual(len(v['samples']),3)
  self.assertFalse(self.h.config()['enabled']);self.assertEqual(self.h.registry(),{})
  s=v['samples'][0];self.c.capture(s['activity'],s['request'],s['decision'])
  self.assertEqual(self.c.get(v['candidate'])['revision'],v['revision'])
 def test_confirmation_then_inhibition_changes_real_probability(self):
  v=self.pending();self.enable_habits_stopped()
  done=self.c.decide(v['candidate'],v['revision'],True,'reviewed suitable','approve',self.actor)
  assoc=done['association'];self.assertEqual(self.h.snapshot(assoc)['state'],'active')
  self.assertAlmostEqual(self.h.snapshot(assoc)['expression'],.3)
  self.assertEqual(self.c.decide(v['candidate'],v['revision'],True,'reviewed suitable','approve',self.actor)['revision'],done['revision'])
  self.control.resume('next');a=self.e.submit('review brief','next');_,p=self.e.prepare(a,Model())
  before=BehaviorPolicy(self.s).evaluate(p,ACTION,0)['candidates'][0]['probability']
  self.assertEqual(len(p['habit_suggestions']),1)
  self.h.control(assoc,'inhibit','stop tendency',self.h.snapshot(assoc)['revision'],self.actor)
  b=self.e.submit('review brief','after-inhibit');_,p2=self.e.prepare(b,Model())
  after=BehaviorPolicy(self.s).evaluate(p2,ACTION,0)['candidates'][0]['probability']
  self.assertGreater(before,after);self.assertFalse(p2['habit_suggestions'])
 def test_rejection_and_stale_revision_do_not_activate(self):
  self.episode();first=self.c.status()['items'][0];self.episode()
  self.control.stop('review')
  with self.assertRaises(Conflict):self.c.decide(first['candidate'],first['revision'],False,'reject','stale',self.actor)
  current=self.c.get(first['candidate']);self.c.decide(current['candidate'],current['revision'],False,'reject','reject',self.actor)
  self.control.resume('next');self.episode();self.assertEqual(self.c.get(first['candidate'])['state'],'rejected');self.assertFalse(self.h.registry())
 def test_contexts_do_not_merge_and_non_user_source_is_not_collected(self):
  self.episode();self.episode('another task');self.episode(source='exploration-test')
  self.assertEqual(len(self.c.status()['items']),2)
  self.assertTrue(all(len(x['samples'])==1 for x in self.c.status()['items']))
 def test_source_withdrawal_blocks_confirmation(self):
  v=self.pending();signal=v['samples'][0]['signal']
  row=self.s.db.execute('SELECT r.memory_id FROM memory_revisions r JOIN memory_source_links l ON l.memory_revision_id=r.id JOIN evidence_items e ON e.id=l.evidence_id WHERE e.origin_object_id=?',(signal,)).fetchone()
  Memory(self.s).archive(row[0],self.actor,'withdraw fixture')
  self.enable_habits_stopped()
  with self.assertRaises(Forbidden):self.c.decide(v['candidate'],v['revision'],True,'approve','blocked',self.actor)
  self.assertFalse(self.h.registry());self.assertEqual(self.c.get(v['candidate'])['state'],'pending')
 def test_non_root_and_missing_tool_result_are_not_collected(self):
  a=self.episode();v=self.c.status()['items'][0];s=v['samples'][0]
  with patch('digital_life.application.behavior.habit_candidates.scope.active',return_value=True),patch('digital_life.application.behavior.habit_candidates.scope.current',return_value={'role':'member'}):
   self.assertIsNone(self.c.capture(a,s['request'],s['decision']))
  # A proposed tool has no actual outcome yet, even if its thought was accepted.
  other=self.e.submit('read brief','tool')
  class ToolModel:
   name='fixture'
   def generate(self,p):return {'schema_version':1,'explanation':'read proposal','action':{'tool':'read_file','arguments':{'path':'brief.txt'}}}
  with patch('digital_life.application.behavior.behavior_policy.secrets.randbits',return_value=0):self.e.think(other,ToolModel())
  self.assertEqual(len(self.c.status()['items']),1)
 def test_confirmation_requires_explicit_learning_enable_and_stopped_runtime(self):
  v=self.pending()
  with self.assertRaises(Conflict):self.c.decide(v['candidate'],v['revision'],True,'approve','live',self.actor)
  self.control.stop('review')
  with self.assertRaises(Forbidden):self.c.decide(v['candidate'],v['revision'],True,'approve','disabled',self.actor)
  self.assertFalse(self.h.registry())
 def test_real_tool_receipt_is_collected_but_unknown_is_not(self):
  from digital_life.application.accounts.authorization import Policy
  from digital_life.domain.contracts import ToolResult
  class Write:
   name='fixture'
   def generate(self,p):return {'schema_version':1,'explanation':'write','action':{'tool':'write_note','arguments':{'path':'brief.txt','text':'done'}}}
  for key,unknown in [('ok',False),('unknown',True)]:
   a=self.e.submit('write brief',key)
   with patch('digital_life.application.behavior.behavior_policy.secrets.randbits',return_value=0):r=self.e.think(a,Write())
   self.assertEqual(len(self.c.status()['items']),0 if not unknown else 1)
   Policy(self.s).approve(r['approval_id'],self.actor)
   if unknown:self.e.execute(r['action_id'],backend=lambda *args:ToolResult('received','unknown','unknown',{'fixture':'unknown'}))
   else:self.e.execute(r['action_id'])
  items=self.c.status()['items'];self.assertEqual(len(items),1);self.assertEqual(len(items[0]['samples']),1)
 def test_unusable_learning_source_does_not_discard_core_reply(self):
  with patch.object(HabitCandidates,'capture',side_effect=Forbidden('fixture revoked')):
   a=self.episode()
  self.assertEqual(self.s.row('activities',a)['state'],'waiting_input')
  self.assertTrue(self.s.db.execute('select accepted_result_id from thought_requests where activity_id=?',(a,)).fetchone()[0])
  self.assertFalse(self.c.status()['items'])
  self.assertEqual(self.s.db.execute("select count(*) from runtime_events where activity_id=? and event_type='habit_candidates.skipped'",(a,)).fetchone()[0],1)
