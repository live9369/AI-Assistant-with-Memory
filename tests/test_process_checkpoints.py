"""Small application-checkpoint and real Git release-binding tests."""
import json,tempfile,unittest
from pathlib import Path
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control,Releases
from digital_life.application.lifecycle.process_checkpoints import ProcessCheckpoints
from digital_life.application.lifecycle.project_access import ProjectAccess
from digital_life.application.runtime.engine import Engine
from digital_life.application.lifecycle.deployment import Deployment
from digital_life.domain.contracts import ContractError,Forbidden,Conflict

class CheckpointTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.s=Store.prepare(self.root/'life');self.c=Control(self.s.root,self.s.instance_id)
  self.source=self.root/'source';(self.source/'digital_life').mkdir(parents=True);(self.source/'digital_life/__init__.py').write_text('VALUE=1\n')
  ProjectAccess(self.s).configure(str(self.source),self.s.config()['controller'],auto_approve=True)
  self.old=Releases(self.c).stage(self.source);Releases(self.c).activate(self.old,lambda _:{'ready':True,'schema_compatible':True})
  self.points=ProcessCheckpoints(self.c);self.points.configure(True,self.s.config()['controller'])
 def tearDown(self):self.c.close();self.s.close();self.tmp.cleanup()
 def test_capture_binds_git_and_backup_and_reopens(self):
  point=self.points.capture();self.assertEqual(point['deployment'],self.old);self.assertEqual(len(point['source_version']['git_version']),40)
  self.assertEqual(self.points.get(point['id'],verify_bundle=True)['instance'],self.s.instance_id)
  other=ProcessCheckpoints(self.c);self.assertEqual(other.list()[0]['id'],point['id'])
  self.assertTrue(self.s.db.execute("select 1 from runtime_events where event_type='backup.created'").fetchone())
  metadata=self.s.root/'process-checkpoints'/(point['id']+'.json');value=json.loads(metadata.read_text());value['instance']='wrong';metadata.write_text(json.dumps(value))
  with self.assertRaises(Forbidden):self.points.get(point['id'])
 def test_rollback_restarts_old_keeps_new_memory_and_budget(self):
  from digital_life.application.services.memory import Memory
  (self.s.root/'WAKE_DISABLED').unlink();self.c.resume('fixture')
  (self.source/'digital_life/__init__.py').write_text('VALUE=2\n');new=Releases(self.c).stage(self.source)
  outer=self
  class Driver:
   def launch(self,path,root,deployment,ready,gate):return type('P',(),{'deployment':deployment,'pid':0})()
   def await_state(self,p,ready,desired,timeout):
    if desired=='running' and p.deployment==new:
     with outer.s.tx():
      evidence=outer.s.evidence(artifact=outer.s.artifact({'text':'new memory after checkpoint'}));Memory(outer.s).encode('new memory after checkpoint',evidence)
     raise ContractError('candidate failed')
    return {'state':desired,'deployment':p.deployment,'schema_compatible':True}
   def stop(self,p):pass
  manager=Deployment(self.c,Driver());result=manager.launch(new)
  self.assertTrue(result['restarted']);self.assertIsNotNone(result['process_recovery']['checkpoint']);self.assertFalse(result['reconciliation']['database_restored'])
  self.assertTrue(self.s.db.execute("select 1 from memory_revisions where content='new memory after checkpoint'").fetchone());self.assertEqual(manager.active['deployment'],self.old)
 def test_reconciliation_pauses_work_without_rewinding_budget(self):
  a=Engine(self.s).submit('unfinished','unfinished')
  with self.s.tx():Engine(self.s).transition(a,'running','fixture')
  before=dict(self.s.db.execute('select * from activity_budget_accounts where activity_id=?',(a,)).fetchone())
  result=self.points.reconcile_uncertain();after=dict(self.s.db.execute('select * from activity_budget_accounts where activity_id=?',(a,)).fetchone())
  self.assertIn(a,result['paused']);self.assertFalse(result['automatic_replay']);self.assertEqual(before,after);self.assertEqual(self.s.row('activities',a)['state'],'paused')

 def test_unknown_external_effect_is_not_replayed_or_refunded(self):
  from tests.test_full_system import FakeModel
  from digital_life.application.accounts.authorization import Policy
  (self.s.root/'WAKE_DISABLED').unlink();self.c.resume('unknown-fixture');engine=Engine(self.s)
  a=engine.submit('one external action','unknown-action');proposal=engine.think(a,FakeModel());Policy(self.s).approve(proposal['approval_id'],self.s.config()['controller']);calls=[]
  def external(action,root,operation):
   calls.append(operation);(root/'external-marker.txt').write_text('effect happened');raise RuntimeError('receipt lost')
  engine.execute(proposal['action_id'],external)
  before=[tuple(r) for r in self.s.db.execute('select reserved_tokens,reserved_tool_calls,state from budget_reservations where activity_id=?',(a,))]
  result=self.points.reconcile_uncertain();after=[tuple(r) for r in self.s.db.execute('select reserved_tokens,reserved_tool_calls,state from budget_reservations where activity_id=?',(a,))]
  self.assertFalse(result['automatic_replay']);self.assertEqual(len(calls),1);self.assertEqual(before,after);self.assertEqual(self.s.row('action_intents',proposal['action_id'])['state'],'unknown')
