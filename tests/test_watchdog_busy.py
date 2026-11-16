import json,sqlite3,tempfile,unittest,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from digital_life.application.lifecycle.deployment import Deployment
class WatchdogBusyTests(unittest.TestCase):
 def test_busy_probe_retries_without_stopping_and_then_verifies(self):
  with tempfile.TemporaryDirectory() as d:
   ready=Path(d)/'ready.json';ready.write_text('{}');control=SimpleNamespace(root=Path(d),assert_startable=lambda:None);driver=Mock();manager=Deployment(control,driver);process=Mock();process.poll.return_value=None
   manager.active={'process':process,'ready':ready,'deployment':'test','old':None}
   with patch('digital_life.application.learning.bridge.read_readiness',return_value={'state':'running'}),patch('digital_life.application.learning.bridge.verify_handshake',side_effect=[sqlite3.OperationalError('database is locked'),None]) as verify:
    self.assertEqual(manager.check()['state'],'verification_pending');driver.stop.assert_not_called()
    self.assertEqual(manager.check()['state'],'running');self.assertEqual(verify.call_count,2);driver.stop.assert_not_called()
   self.assertTrue((ready.parent/'watchdog-busy.json').exists())
 def test_persistent_busy_still_expires(self):
  with tempfile.TemporaryDirectory() as d:
   ready=Path(d)/'ready.json';ready.write_text('{}');control=SimpleNamespace(root=Path(d),assert_startable=lambda:None);driver=Mock();manager=Deployment(control,driver);process=Mock();process.poll.return_value=None
   manager.active={'process':process,'ready':ready,'deployment':'test','old':None,'verification_pending_since':time.monotonic()-10}
   with patch('digital_life.application.learning.bridge.read_readiness',return_value={'state':'running'}),patch('digital_life.application.learning.bridge.verify_handshake',side_effect=sqlite3.OperationalError('database is locked')),patch.object(manager,'_rollback',return_value={'restarted':False}) as rollback:
    self.assertEqual(manager.check(heartbeat_timeout=5)['state'],'failed');driver.stop.assert_called_once();self.assertEqual(rollback.call_args.args[2],'heartbeat-verification-timeout')
