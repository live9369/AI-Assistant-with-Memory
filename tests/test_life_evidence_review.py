"""Audited verifier rejects contradictory canonical data, not just bad hashes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,dumps,sha
from scripts.development.run_life_acceptance import run,verify

class LifeEvidenceReviewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)/'joint';run(cls.root,8,.1)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_actual_record_verifies_even_when_long_horizon_is_incomplete(self):
  self.assertFalse(verify(self.root)['long_horizon_passed'])
 def change_checkpoint(self,mutate):
  files=sorted((self.root/'checkpoints').glob('*.json'));original={p:p.read_text() for p in files};report=self.root/'report.json';raw=report.read_text();previous=''
  try:
   for i,p in enumerate(files):
    value=json.loads(original[p]);r=value['record'];mutate(i,r);r['previous']=previous;previous=sha(dumps(r));p.write_text(dumps({'record':r,'hash':previous}))
   value=json.loads(raw);value['checkpoint_tail']=previous;report.write_text(dumps(value))
   with self.assertRaises(ContractError):verify(self.root)
  finally:
   for p,text in original.items():p.write_text(text)
   report.write_text(raw)
 def test_forged_anchor_with_valid_hash_chain_is_rejected(self):
  self.change_checkpoint(lambda i,r:r.update(anchors='forged') if i==0 else None)
 def test_epoch_must_match_real_sleep_handoff(self):
  self.change_checkpoint(lambda i,r:r.update(epoch=r['epoch']+1000))
 def test_adaptation_summary_must_match_saved_observation(self):
  p=self.root/'adaptation.json';raw=p.read_text()
  try:
   v=json.loads(raw);v['after']=1;p.write_text(dumps(v))
   with self.assertRaises(ContractError):verify(self.root)
  finally:p.write_text(raw)
 def test_missing_restore_lock_is_rejected(self):
  p=self.root/'restore-check/RESTORE_RECONCILIATION_REQUIRED';raw=p.read_text()
  try:
   p.unlink()
   with self.assertRaises(ContractError):verify(self.root)
  finally:p.write_text(raw)
