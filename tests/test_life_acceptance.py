"""T13 protocol honesty and externally verified controlled evidence."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from evaluation.life_acceptance import PROTOCOL,assess,guard,CRITERIA
from digital_life.domain.contracts import ContractError

class LifeProtocolTests(unittest.TestCase):
 def records(self,n=300,duration=86400):
  from datetime import datetime,timezone,timedelta
  base=datetime(2026,1,1,tzinfo=timezone.utc)
  return [{'at':(base+timedelta(seconds=(i+1)*duration/n)).isoformat().replace('+00:00','Z'),'cycle':i,'elapsed':(i+1)*duration/n,'instance':'one','pid':100+i,'epoch':i+1,'requests':2,'results':2,'repair_verified':i in (2,6),'verified':True,'checks':{k:True for k in CRITERIA}} for i in range(n)]
 def test_short_pass_does_not_become_long_term_proof(self):
  r=assess(self.records(30,30),30,True);self.assertTrue(r['engineering_passed']);self.assertFalse(r['passed']);self.assertFalse(r['real_model_tested']);self.assertFalse(r['consciousness_asserted'])
 def test_predeclared_long_policy_allows_only_bounded_conditional_scope(self):
  r=assess(self.records(),86400,True);self.assertTrue(r['long_horizon_passed']);self.assertTrue(all(v=='conditional-controlled-fixture' for v in r['criteria'].values()))
 def test_cycles_cannot_replace_real_elapsed_time(self):
  r=assess(self.records(1000,30),30,True);self.assertFalse(r['passed'])
 def test_empty_missing_and_false_feature_cannot_be_compensated(self):
  self.assertFalse(assess([],86400,True)['engineering_passed'])
  for k in CRITERIA:
   rows=self.records();rows[0]['checks'][k]=False;self.assertFalse(assess(rows,86400,True)['passed'])
 def test_clock_spoof_nonfinite_gaps_and_disordered_epochs_fail(self):
  for value in (float('nan'),float('inf'),-1,True):
   with self.assertRaises(ContractError):assess([],value,True)
  for mutation in ({'elapsed':float('nan')},{'epoch':0},{'instance':'other'},{'verified':False},{'requests':0},{'pid':None}):
   rows=self.records();rows[2].update(mutation);self.assertFalse(assess(rows,86400,True)['passed'])
  self.assertFalse(assess(self.records(100),86400,True)['passed'])
 def test_source_change_and_interruption_never_pass(self):
  self.assertFalse(assess(self.records(),86400,False)['passed']);self.assertFalse(assess(self.records(),86400,True,False)['passed'])
 def test_worker_rejects_unmarked_formal_or_arbitrary_directory(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'instance';root.mkdir()
   with self.assertRaises(ContractError):guard(root,'expected')
   (root/'life-acceptance.json').write_text('{"run":"other"}')
   with self.assertRaises(ContractError):guard(root,'expected')
 def test_final_gap_and_missing_repairs_fail(self):
  rows=self.records();self.assertFalse(assess(rows,87000,True)['passed'])
  for r in rows:r['repair_verified']=False
  self.assertFalse(assess(rows,86400,True)['passed'])
 def test_bootstrap_failure_stops_and_locks_isolated_instance(self):
  from unittest.mock import patch
  from scripts.development.run_life_acceptance import run
  from digital_life.application.lifecycle.control_plane import Control
  from digital_life.infrastructure.persistence.sqlite_store import Store
  with tempfile.TemporaryDirectory() as tmp:
   output=Path(tmp)/'failed'
   with patch('scripts.development.run_life_acceptance.adaptation',side_effect=RuntimeError('controlled setup failure')):
    with self.assertRaises(RuntimeError):run(output,.1,.1)
   self.assertTrue((output/'instance/WAKE_DISABLED').exists());s=Store(output/'instance');c=Control(s.root,s.instance_id)
   try:self.assertEqual(c.state()['user_stopped'],1);self.assertIsNone(c.state()['active_process_run_id'])
   finally:c.close();s.close()
 def test_tampered_checkpoint_hash_is_rejected(self):
  from scripts.development.run_life_acceptance import verify
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp);(out/'checkpoints').mkdir();(out/'report.json').write_text('{"checkpoint_tail":"wrong"}');(out/'protocol.json').write_text(json.dumps(PROTOCOL));(out/'checkpoints/000000.json').write_text('{"record":{"previous":""},"hash":"fake"}')
   with self.assertRaises(ContractError):verify(out)
 def test_source_freeze_includes_schema_and_resource_configuration(self):
  from evaluation.life_acceptance import fingerprint
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for folder in ('digital_life/resources','evaluation','scripts/development','docs/architecture'):(root/folder).mkdir(parents=True)
   (root/'scripts/development/run_life_acceptance.py').write_text('');(root/'docs/architecture/development-t13-design.md').write_text('');resource=root/'digital_life/resources/config.json';resource.write_text('{"value":1}');schema=root/'digital_life/resources/runtime.sql';schema.write_text('SELECT 1;');before=fingerprint(root);resource.write_text('{"value":2}');self.assertNotEqual(before,fingerprint(root));self.assertIn('digital_life/resources/runtime.sql',before)

 def test_suspended_machine_wall_gap_cannot_hide_behind_monotonic_clock(self):
  rows=self.records(30,30);rows[15]['at']='2026-01-01T02:00:00Z';self.assertFalse(assess(rows,30,True)['engineering_passed'])
  rows=self.records(30,30);result=assess(rows,30,True,True,'2025-12-31T22:00:00Z','2026-01-01T00:00:31Z');self.assertFalse(result['engineering_passed'])
 def test_corrupt_runtime_reopen_cannot_prevent_stop_lock(self):
  from unittest.mock import patch
  import sqlite3
  from scripts.development.run_life_acceptance import run
  from digital_life.infrastructure.persistence.sqlite_store import Store
  original=Store.__init__
  with tempfile.TemporaryDirectory() as tmp:
   output=Path(tmp)/'interrupted'
   def reopen(store,root):
    path=Path(root)
    if (path/'life-acceptance.json').exists() and (path/'WAKE_DISABLED').exists():raise RuntimeError('controlled corrupt reopen')
    return original(store,root)
   with patch.object(Store,'__init__',reopen):
    with self.assertRaises(RuntimeError):run(output,.1,.1)
   self.assertTrue((output/'instance/WAKE_DISABLED').exists())
   c=sqlite3.connect((output/'instance/control.sqlite').as_uri()+'?mode=ro',uri=True)
   try:self.assertEqual(c.execute('SELECT user_stopped FROM instance_control_state').fetchone()[0],1)
   finally:c.close()
