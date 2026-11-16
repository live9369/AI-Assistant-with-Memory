"""IM dependency and evidence gates without opening any life instance."""
import json
from pathlib import Path
import tempfile
import unittest
from digital_life.application.learning.plan import inspect,transition,PLAN
from digital_life.domain.contracts import ContractError,sha

class ImplementationPlanTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  for folder in ('docs/plan','docs/architecture','outputs/acceptance/tool-learning','digital_life'):(self.root/folder).mkdir(parents=True,exist_ok=True)
  (self.root/'docs/architecture/design.md').write_text('immutable design')
  self.design='docs/architecture/design.md';self.freeze='docs/architecture/freeze.json'
  (self.root/self.freeze).write_text(json.dumps({'contract_id':'TL-LOOP-0.1','status':'frozen_design','normative_documents':{self.design:sha(b'immutable design')},'decision_sources':{},'code_snapshot':{'digital_life/changed.py':'historical'}}))
  self.plan={'frozen_contract':'TL-LOOP-0.1','frozen_record':self.freeze,'frozen_record_sha256':sha((self.root/self.freeze).read_bytes()),'implementation_authorized':True,'runtime_tests_authorized':True,'specific_authorizations':{},'tasks':[self.task('IM01',[]),self.task('IM02',['IM01']),self.task('IM21',['IM01'],'explicit_DEV_model_and_money_authorization')]}
  self.write()
 def task(self,id,deps,gate='isolated_implementation_authorization'):return {'id':id,'status':'pending','depends_on':deps,'authorization_gate':gate,'evidence':None}
 def write(self):(self.root/PLAN).write_text(json.dumps(self.plan))
 def progress(self):
  for state in ('designing','implementing','validating'):transition(self.root,'IM01',state,design=self.design)
 def evidence(self,**changes):
  result={'task':'IM01','contract':'TL-LOOP-0.1','passed':True,'completion_scope':'fixture-only evidence','source_stable_during_verification':True,'frozen_record_sha256':self.plan['frozen_record_sha256']};result.update(changes);p=self.root/'outputs/acceptance/tool-learning/im01.json';p.write_text(json.dumps(result));return str(p.relative_to(self.root))
 def test_normal_code_drift_is_reported_not_mistaken_for_design_drift(self):
  r=inspect(self.root);self.assertEqual(r['ready'],['IM01']);self.assertEqual(r['historical_code_drift'],['digital_life/changed.py']);self.assertFalse(r['execution_performed'])
 def test_cannot_skip_dependency_or_start_without_design(self):
  with self.assertRaises(ContractError):transition(self.root,'IM02','designing',design=self.design)
  with self.assertRaises(ContractError):transition(self.root,'IM01','designing')
  self.assertEqual(inspect(self.root)['ready'],['IM01'])
 def test_matching_evidence_unlocks_only_authorized_successors(self):
  self.progress();r=transition(self.root,'IM01','complete',evidence=self.evidence());self.assertEqual(r['ready'],['IM02']);self.assertEqual(r['authorization_blocked'],['IM21'])
  with self.assertRaises(ContractError):transition(self.root,'IM21','designing',design=self.design)
 def test_bad_evidence_never_replaces_plan(self):
  self.progress();before=(self.root/PLAN).read_bytes()
  for bad in ({'passed':False},{'task':'IM02'},{'contract':'other'},{'completion_scope':''},{'source_stable_during_verification':False},{'frozen_record_sha256':'other'}):
   with self.assertRaises(ContractError):transition(self.root,'IM01','complete',evidence=self.evidence(**bad))
   self.assertEqual((self.root/PLAN).read_bytes(),before)
 def test_tampered_passed_evidence_blocks_following_tasks(self):
  self.progress();e=self.evidence();transition(self.root,'IM01','complete',evidence=e);(self.root/e).write_text('{"passed":true}')
  with self.assertRaises(ContractError):inspect(self.root)
 def test_frozen_record_and_normative_changes_require_review(self):
  (self.root/self.design).write_text('changed')
  with self.assertRaises(ContractError):inspect(self.root)
 def test_completed_history_cannot_be_overwritten(self):
  self.progress();transition(self.root,'IM01','complete',evidence=self.evidence())
  with self.assertRaises(ContractError):transition(self.root,'IM01','designing')
 def test_outside_or_symlink_evidence_not_opened(self):
  self.progress();p=self.root/'outside.json';p.write_text('{}');link=self.root/'outputs/acceptance/tool-learning/link.json';link.symlink_to(p)
  for name in ('outside.json','outputs/acceptance/tool-learning/link.json'):
   with self.assertRaises(ContractError):transition(self.root,'IM01','complete',evidence=name)
 def test_authorization_and_blocked_reason_are_explicit(self):
  self.plan['implementation_authorized']=False;self.write();self.assertEqual(inspect(self.root)['ready'],[])
  with self.assertRaises(ContractError):transition(self.root,'IM01','designing',design=self.design)
  self.plan['implementation_authorized']=True;self.write()
  with self.assertRaises(ContractError):transition(self.root,'IM01','blocked')
  transition(self.root,'IM01','blocked',reason='fixture dependency missing');self.assertEqual(inspect(self.root)['ready'],['IM01'])
 def test_symlink_directory_cannot_redefine_permitted_root(self):
  import shutil
  folder=self.root/'docs/architecture';outside=self.root/'external';folder.rename(outside);folder.symlink_to(outside,target_is_directory=True)
  with self.assertRaises(ContractError):inspect(self.root)
 def test_parallel_independent_transitions_do_not_lose_updates(self):
  from concurrent.futures import ThreadPoolExecutor
  from unittest.mock import patch
  import time
  import digital_life.application.learning.plan as module
  self.progress();transition(self.root,'IM01','complete',evidence=self.evidence())
  plan=json.loads((self.root/PLAN).read_text());plan['tasks'].append(self.task('IM03',['IM01']));(self.root/PLAN).write_text(json.dumps(plan));original=module._inspect
  def delayed(*args):time.sleep(.02);return original(*args)
  with patch.object(module,'_inspect',delayed),ThreadPoolExecutor(max_workers=2) as pool:
   jobs=[pool.submit(transition,self.root,id,'designing',design=self.design) for id in ('IM02','IM03')]
   for job in jobs:job.result()
  states={t['id']:t['status'] for t in inspect(self.root)['tasks']};self.assertEqual((states['IM02'],states['IM03']),('designing','designing'))
