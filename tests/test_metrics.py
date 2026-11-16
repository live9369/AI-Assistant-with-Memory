import json
from pathlib import Path
import tempfile
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.telemetry.metrics import Metrics,catalog,reduce_samples
from digital_life.application.runtime.engine import Engine
from digital_life.domain.contracts import ContractError,Forbidden

class MetricTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.s=Store.prepare(Path(self.tmp.name)/'instance')
        self.addCleanup(self.tmp.cleanup); self.addCleanup(self.s.close)
    def test_catalog_covers_every_module_and_collects_missing_explicitly(self):
        definitions=catalog()
        self.assertEqual({r['module'] for r in definitions},{'M%02d'%i for i in range(1,18)})
        result=Metrics(self.s).collect()
        self.assertEqual(result['definitions'],len(definitions))
        self.assertGreater(result['missing'],0)
        self.assertTrue((self.s.root/'WAKE_DISABLED').exists())
        samples=self.s.rows('metric_samples')
        self.assertEqual(len(samples),len(definitions))
        for sample in samples:
            if json.loads(sample['uncertainty'])['status']=='missing': self.assertIsNone(sample['value'])
        self.assertEqual(self.s.integrity()['foreign_keys'],[])
    def test_all_baseline_metrics_accept_evidence_and_reduce_automatically(self):
        metrics=Metrics(self.s); actor=self.s.config()['controller']
        source=self.s.rows('identity_anchors')[0]['id']
        for metric in catalog():
            if metric['requires']=='runtime': continue
            kind=metric['reducer']
            data={'probability':0.8,'outcome':1} if kind=='ece' else {'ranked':['a','b'],'relevant':['a'],'k':2} if kind in ('precision','recall','mrr','ndcg') else {'value':0.75}
            metrics.observe(metric['key'],data,source,'fixture',actor,dataset='fixture-all')
        result=metrics.collect('fixture-all')
        self.assertLess(result['missing'],25)  # only unobserved operational denominators may remain absent
        self.assertEqual(self.s.integrity()['foreign_keys'],[])
    def test_duplicate_observation_not_double_counted_or_relabelled(self):
        metrics=Metrics(self.s); definition=next(r for r in catalog() if r['reducer']=='mean' and r['requires']!='runtime')
        args=(definition['key'],{'value':1},self.s.rows('identity_anchors')[0]['id'],'case',self.s.config()['controller'])
        self.assertEqual(metrics.observe(*args),metrics.observe(*args))
        with self.assertRaises(Forbidden): metrics.observe(*args[:-1],'model-self-report')
        with self.assertRaises(ContractError): metrics.observe(definition['key'],{'value':float('nan')},args[2],'bad',args[4])
    def test_operational_values_use_actual_rows(self):
        Engine(self.s).submit('input','key')
        values=Metrics(self.s).operational()
        self.assertEqual(values['queue_depth'][0],1)
        self.assertEqual(values['memory_source_coverage'][0],1)
        self.assertIsNone(values['tool_success_rate'][0])
        self.assertIsNone(values['model_input_tokens'][0])
    def test_state_vector_collects_observables_without_inventing_trust(self):
        from digital_life.application.telemetry.states import StateCollector
        from digital_life.application.services import States
        result=StateCollector(self.s).collect()
        self.assertEqual(set(result['groups']),set('RWUCTDF'))
        self.assertIn('U',result['missing_groups']); self.assertIn('T',result['missing_groups'])
        self.assertGreater(States(self.s).snapshot()['R.disk_free_bytes']['value'],0)
        self.assertEqual(States(self.s).snapshot()['W.queue_depth']['value'],0)
        self.assertTrue((self.s.root/'WAKE_DISABLED').exists())
    def test_ranking_and_calibration_exact_numbers(self):
        sample={'ranked':['wrong','right','right'],'relevant':['right'],'k':2}
        self.assertEqual(reduce_samples('precision',[sample])[0],0.5)
        self.assertEqual(reduce_samples('recall',[sample])[0],1)
        self.assertEqual(reduce_samples('mrr',[sample])[0],0.5)
        self.assertAlmostEqual(reduce_samples('ece',[{'probability':0.8,'outcome':1}])[0],0.2)
        self.assertIsNone(reduce_samples('recall',[dict(sample,relevant=[])])[0])
