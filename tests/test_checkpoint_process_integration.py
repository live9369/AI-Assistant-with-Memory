"""Owned real-process fault injection, isolated data and local model inventory only."""
import json
from tests.test_process_integration import ProcessIntegrationTests
from digital_life.application.lifecycle.process_checkpoints import ProcessCheckpoints

class RealCheckpointTests(ProcessIntegrationTests):
 def setUp(self):
  super().setUp();ProcessCheckpoints(self.c).configure(True,self.s.config()['controller'])
 def assert_checkpoint(self):
  manager=ProcessCheckpoints(self.c);points=manager.list();self.assertTrue(points)
  point=manager.get(points[0]['id'],verify_bundle=True);self.assertEqual(point['deployment'],self.old)
  row=self.c.db.execute("SELECT payload FROM control_commands WHERE kind='process.rollback' ORDER BY rowid DESC LIMIT 1").fetchone();self.assertTrue(row)
  value=json.loads(row[0]);self.assertTrue(value['restarted']);self.assertEqual(value['checkpoint'],point['id']);self.assertFalse(value['thread_memory_restored'])
 def test_checkpoint_prepared_failure(self):
  super().test_real_failure_before_ready_retains_and_restarts_old();self.assert_checkpoint()
 def test_checkpoint_running_failure(self):
  super().test_real_failure_after_activation_rolls_back();self.assert_checkpoint()

 def test_explicit_stop_does_not_restart(self):
  self.activate_old_without_process();new=self.candidate();self.assertTrue(self.manager.launch(new,timeout=12)['switched'])
  self.c.stop('explicit-stop-fixture');self.assertEqual(self.manager.check()['state'],'user_stopped');self.assertIsNone(self.manager.active)
  self.assertFalse(self.c.db.execute("SELECT 1 FROM control_commands WHERE kind='process.rollback'").fetchone())
