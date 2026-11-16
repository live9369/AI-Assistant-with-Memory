"""Meaningful negative checks for the offline evidence aggregator and G1 materials."""
import json
from pathlib import Path
import tempfile
import unittest
from evaluation.exploration.harness import Harness
from evaluation.exploration.scenarios import material_smoke
from evaluation.exploration.aggregate import aggregate,digest

ROOT=Path(__file__).resolve().parents[1]
def write(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

class ExplorationEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.run=Path(self.temp.name)/'run'; self.run.mkdir()
        self.data=json.loads((ROOT/'evaluation/exploration/materials/cases-v1.json').read_text())
        self.trial=self.run/'trials/fixture'; self.trial.mkdir(parents=True)
        self.h=Harness(Path(self.temp.name)/'instance',self.data['cases'][0])
        material_smoke(self.h)
    def tearDown(self): self.h.close(); self.temp.cleanup()
    def seal(self):
        self.h.export(self.trial)
        result={'trial_id':'fixture','case_id':'A01','status':'pass','error':None,'recovery_scenario':False,'read_replay_opportunity':False,
                'evidence_hashes':{n:digest(self.trial/n) for n in ('snapshot.json','artifacts.json','trace.json')}}
        write(self.trial/'result.json',result)
        (self.run/'baseline.json').write_bytes((ROOT/'docs/architecture/autonomous-exploration-baseline-v1.json').read_bytes())
        write(self.run/'cases.json',self.data)
        guard={'state':'not_present','files':{}}
        manifest={'run_id':'unit-fixture','trials':[{'trial_id':'fixture'}],'g0':{'successful':True},
                  'baseline_sha256':digest(self.run/'baseline.json'),'dataset_sha256':digest(self.run/'cases.json'),'formal_instance_before':guard}
        write(self.run/'manifest.json',manifest); (self.run/'manifest.sha256').write_text(digest(self.run/'manifest.json'))
        write(self.run/'evidence-index.json',{'fixture':{'exit_code':0,'watchdog_fired':False,'result_sha256':digest(self.trial/'result.json')}})
        (self.run/'evidence-index.sha256').write_text(digest(self.run/'evidence-index.json'))
        write(self.run/'formal-instance-guard.json',{'before':guard,'after':guard,'unchanged':True})
    def test_unmeasured_quality_is_never_filled_by_scripted_success(self):
        self.seal(); report=aggregate(self.run)
        self.assertEqual(report['gates']['G1'],'pass'); self.assertEqual(report['gates']['G2'],'not_run')
        metrics={m['metric_id']:m for m in report['metrics']}
        for key in ('M01','M02','M04','M05','M06','M07','M08','M15','M16'):
            self.assertEqual(metrics[key]['status'],'not_run'); self.assertIsNone(metrics[key]['value'])
        self.assertEqual(metrics['M09']['status'],'not_applicable'); self.assertIsNone(metrics['M09']['value'])
        self.assertEqual(metrics['M12']['status'],'not_evaluable'); self.assertIsNone(metrics['M14']['components']['actual_tokens'])
    def test_stop_violation_is_recomputed_from_monotonic_trace(self):
        self.h.trace('stop_committed',control='aggregation-unit-test')
        self.h.trace('dispatch',transport='model',operation_id='new-op',request_id='new-request',activity='test')
        self.seal(); report=aggregate(self.run)
        self.assertEqual(report['gates']['G1'],'fail'); self.assertEqual(report['invariants']['post_stop_dispatches'],1)
    def test_missing_or_changed_evidence_cannot_pass(self):
        self.seal(); (self.trial/'trace.json').write_text('[]')
        report=aggregate(self.run)
        self.assertEqual(report['gates']['G1'],'not_evaluable'); self.assertEqual(len(report['evidence_missing']),1)
        m=next(m for m in report['metrics'] if m['metric_id']=='M11')
        self.assertIsNone(m['value']); self.assertEqual(m['status'],'missing')
    def test_manifest_tampering_is_rejected(self):
        self.seal(); (self.run/'manifest.json').write_text('{}')
        with self.assertRaises(ValueError): aggregate(self.run)
    def test_result_tampering_is_rejected(self):
        self.seal(); result=json.loads((self.trial/'result.json').read_text()); result['status']='fail'
        write(self.trial/'result.json',result)
        report=aggregate(self.run); self.assertNotEqual(report['gates']['G1'],'pass')
    def test_formal_instance_change_fails_gate(self):
        self.seal(); write(self.run/'formal-instance-guard.json',{'before':{},'after':{'changed':True},'unchanged':False})
        self.assertEqual(aggregate(self.run)['gates']['G1'],'fail')
    def test_material_and_scenario_coverage(self):
        self.assertEqual(len(self.data['cases']),60)
        self.assertEqual(len({c['case_id'] for c in self.data['cases']}),60)
        for group in 'ABCDEF': self.assertEqual(sum(c['stratum']==group for c in self.data['cases']),10)
        self.assertGreaterEqual(sum(c['oracle']['counterexample_opportunity'] for c in self.data['cases']),20)
        scenarios=json.loads((ROOT/'evaluation/exploration/materials/scenarios-v1.json').read_text())['scenarios']
        matrix=[s for s in scenarios if s['kind']=='stop_matrix']
        self.assertEqual(len(matrix),24)
        self.assertEqual(len({(s['control'],s['stage'],s['transport']) for s in matrix}),24)
        self.assertFalse(self.data['independent_quality_review'])

if __name__=='__main__': unittest.main()
