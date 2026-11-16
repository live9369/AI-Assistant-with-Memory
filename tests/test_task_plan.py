import json,tempfile
from pathlib import Path
import unittest
from digital_life.application.monitoring.task_plan import inspect_plan
from digital_life.domain.contracts import sha,ContractError

class TaskPlanTests(unittest.TestCase):
 def test_evidence_gate_and_dependencies(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'docs/plan').mkdir(parents=True);(root/'design.md').write_text('design');evidence=root/'result.json';evidence.write_text(json.dumps({'task':'T01','passed':True}))
   plan={'tasks':[{'id':'T01','status':'complete','depends_on':[],'design':'design.md','evidence':'result.json','evidence_sha256':sha(evidence.read_bytes()),'completion_scope':'bounded test'},{'id':'T02','status':'pending','depends_on':['T01']}]};p=root/'docs/plan/task-status.json';p.write_text(json.dumps(plan));self.assertEqual(inspect_plan(root)['next_ready'],['T02'])
   evidence.write_text(json.dumps({'task':'T01','passed':False}))
   with self.assertRaises(ContractError):inspect_plan(root)
   plan['tasks'][0]['status']='pending';plan['tasks'][1]['status']='implementing';p.write_text(json.dumps(plan))
   with self.assertRaises(ContractError):inspect_plan(root)
 def test_frozen_baseline_and_explicit_regression_cases_exist(self):
  root=Path(__file__).resolve().parents[1];baseline=json.loads((root/'outputs/acceptance/development-baseline.json').read_text());self.assertTrue(baseline['files']);self.assertTrue(baseline['deployment']['id'])
  cases=json.loads((root/'config/evaluation/cognitive-baseline.json').read_text())['cases'];self.assertEqual(len(cases),11);self.assertEqual(len({x['id'] for x in cases}),11);self.assertTrue(all(x['input'] and x['required_concepts'] for x in cases))
 def test_t13_complete_requires_independent_long_and_current_source_gates(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'docs/plan').mkdir(parents=True);(root/'design.md').write_text('design');e=root/'result.json';p=root/'docs/plan/task-status.json'
   for field in ('engineering_passed','long_horizon_passed','joint_matches_current_source'):
    value={'task':'T13','passed':True,'engineering_passed':True,'long_horizon_passed':True,'joint_matches_current_source':True};value[field]=False;e.write_text(json.dumps(value));p.write_text(json.dumps({'tasks':[{'id':'T13','status':'complete','depends_on':[],'design':'design.md','evidence':'result.json','evidence_sha256':sha(e.read_bytes()),'completion_scope':'bounded'}]}))
    with self.assertRaises(ContractError):inspect_plan(root)
