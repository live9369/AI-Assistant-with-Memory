"""One-shot acceptance through native Engine; no external provider."""
import tempfile,unittest
from pathlib import Path
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.runtime.engine import Engine
from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
from digital_life.application.behavior.behavior_policy import BehaviorPolicy
from digital_life.application.lifecycle.deployment_thought import run,verify,expected
from digital_life.domain.contracts import ContractError
class Echo:
 name='fixture'
 def __init__(self,bad=False):self.calls=0;self.bad=bad
 def generate(self,p):
  self.calls+=1;nonce=p['deployment_acceptance']['nonce']
  return {'schema_version':3,'action':{'tool':'ask','arguments':{'reason':'bad'}} if self.bad else expected(nonce),'explanation':'DEPLOYMENT_OK:'+nonce,'cognition':{'claims':[],'questions':[],'predictions':[],'plan':[]}}
class ThoughtGateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Store.prepare(Path(self.tmp.name)/'life',model_config={'backend':'fixture','model':'fixture'});self.c=Control(self.s.root,self.s.instance_id)
  CognitiveUpdates(self.s).configure(True,self.s.config()['controller']);BehaviorPolicy(self.s).configure(True,self.s.config()['controller'])
  (self.s.root/'WAKE_DISABLED').unlink();self.c.resume('fixture');self.e=Engine(self.s)
 def tearDown(self):self.c.close();self.s.close();self.tmp.cleanup()
 def test_one_real_engine_thought_accepted_archived_and_verified(self):
  model=Echo();proof=run(self.e,model,'test-deployment','a'*32);self.assertEqual(model.calls,1);verify(self.s.root,'test-deployment',proof,'a'*32)
  self.assertEqual(proof['state'],'passed');self.assertEqual(len(self.s.rows('action_intents')),0)
  self.assertFalse(self.s.db.execute("select 1 from jobs where state in ('queued','leased')").fetchone())
  self.assertFalse(self.s.db.execute("select 1 from memory_items where state='active'").fetchone())
  with self.assertRaises(ContractError):verify(self.s.root,'test-deployment',proof,'b'*32)
 def test_wrong_action_fails_once_without_tool_intent(self):
  model=Echo(True)
  with self.assertRaises(ContractError):run(self.e,model,'test-deployment','a'*32)
  self.assertEqual(model.calls,1);self.assertEqual(len(self.s.rows('action_intents')),0)
  self.assertFalse(self.s.db.execute("select 1 from jobs where state in ('queued','leased')").fetchone())
  self.assertTrue(self.s.db.execute("select 1 from runtime_events where event_type='deployment.thought_failed'").fetchone())
