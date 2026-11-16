import json,unittest
from tests.test_account_management import Boundary,Fixture
from digital_life.application.accounts import account_scope as scope
from digital_life.application.chat.chat import Chat
from digital_life.application.runtime.engine import Engine
from digital_life.application.services.memory import Memory
from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
from digital_life.application.accounts.account_memory import change
from digital_life.domain.contracts import Forbidden

class RootInfluence(Boundary):
 def submit(self,user,text,key='weight',previous=None):
  with scope.audience(self.s,user['id']):return Chat(self.s).send(user['thread_id'],dict(text=text,idempotency_key=key,expected_last_activity_id=previous))['activity_id']
 def memory(self,activity):
  signal=self.s.row('activities',activity)['trigger_event_id']
  return self.s.db.execute('SELECT r.memory_id,r.id FROM memory_source_links l JOIN evidence_items e ON e.id=l.evidence_id JOIN memory_revisions r ON r.id=l.memory_revision_id WHERE e.origin_object_id=?',(signal,)).fetchone()
 def test_direct_root_weight_not_model_or_unverified_origin(self):
  from digital_life.application.accounts.cognitive_influence import source_weight
  root_act=self.submit(self.root,'root influence');Engine(self.s).think(root_act,self.model)
  member_act=self.submit(self.users[0],'member influence');Engine(self.s).think(member_act,self.model)
  self.assertEqual(source_weight(self.s,self.memory(root_act)[1]),2)
  self.assertEqual(source_weight(self.s,self.memory(member_act)[1]),1)
  self.assertEqual(source_weight(self.s,'unknown'),1)
  reply=self.s.db.execute("SELECT id FROM memory_revisions WHERE encoding_method='model-response-v1' LIMIT 1").fetchone()[0]
  self.assertEqual(source_weight(self.s,reply),1)
 def test_weighted_recall_still_obeys_private_domains(self):
  root_act=self.submit(self.root,'same-topic');Engine(self.s).think(root_act,self.model)
  member_act=self.submit(self.users[0],'same-topic');Engine(self.s).think(member_act,self.model)
  root_memory=self.memory(root_act);member_memory=self.memory(member_act)
  request=self.submit(self.root,'same-topic','query',root_act)
  req,payload=Engine(self.s).prepare(request,self.model)
  selected=[m['revision_id'] for m in payload['selected_memories']]
  self.assertLess(selected.index(root_memory[1]),selected.index(member_memory[1]))
  self.assertEqual(payload['cognitive_influence']['sources'][root_memory[1]],2)
  private_query=self.submit(self.users[1],'same-topic')
  _,private_payload=Engine(self.s).prepare(private_query,self.model)
  self.assertNotIn(root_memory[1],[m['revision_id'] for m in private_payload['selected_memories']])
  from digital_life.application.accounts.cognitive_influence import check
  payload['cognitive_influence']['weights']['root']=1
  with self.assertRaises(Forbidden):check(self.s,payload)
 def test_root_candidate_weight_is_still_held(self):
  from digital_life.application.lifecycle.control_plane import Control
  c=Control(self.s.root,self.s.instance_id);c.stop('cfg');CognitiveUpdates(self.s).configure(True,self.root['id']);c.resume('cfg-done');c.close()
  class Claims(Fixture):
   def generate(self,p):
    out=super().generate(p);out['schema_version']=3
    signal=next(iter(p['cognition_sources']))
    out['cognition']=dict(claims=[dict(subject='cup',predicate='position',value='window',kind='reported',source_ref=signal,quote=p['observation']['text'])],questions=[],predictions=[],plan=[])
    return out
  Engine(self.s).think(self.submit(self.root,'cup at window'),Claims())
  row=self.s.rows('cognition_belief_revisions')[-1]
  self.assertEqual(row['acceptance_state'],'held')
  self.assertEqual(json.loads(row['uncertainty_json'])['influence_weight'],2)
if __name__=='__main__':unittest.main()
