"""Isolated diagnostic invariants; no complete thought or real model."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from evaluation.tool_learning_continuation_diagnostic import ExclusiveObserver
from evaluation.tool_learning_material_cache_diagnostic import MaterialObserver,material_observers
from digital_life.domain.contracts import Forbidden,ContractError

class MaterialCacheDiagnosticTests(unittest.TestCase):
    def test_known_nonce_shapes_and_literals_do_not_produce_unique_or_raw_labels(self):
        stages=ExclusiveObserver();observer=MaterialObserver(stages)
        first=observer.query("SELECT 'synthetic-secret' AS label\n/*tl-managed:abcdef:1*/")
        second=observer.query("SELECT 'synthetic-secret' AS label\n/*tl-managed:abcdef:2*/")
        self.assertEqual(first,second);self.assertEqual(len(observer.query_ids),1)
        self.assertNotIn('synthetic-secret',json.dumps(observer.report()));self.assertNotIn('abcdef',json.dumps(observer.report()))
    def test_actual_sql_byte_charge_and_over_limit_row_are_counted_without_reserialization(self):
        from digital_life.infrastructure.persistence import tool_learning_meter as meter
        from digital_life.domain.contracts import utc
        stages=ExclusiveObserver();observer=MaterialObserver(stages)
        limits={k:100000 for k in meter.DIMENSIONS};limits['bytes']=1;limits['elapsed_ms']=30000
        account=meter.PhysicalReadMeter(limits,utc(30))
        with material_observers(stages,observer):
            observer.sql_stack.append('synthetic-query');observer.charge_depth=1
            with self.assertRaises(Forbidden):account.consume(5,scan=1,items=1)
            observer.charge_depth=0;observer.sql_stack.pop()
            with self.assertRaises(ContractError):account.consume('invalid')
        row=observer.report()['stages'][0];self.assertEqual(row['sql_totals'],dict(rows=1,items=1,bytes=5,charges=1));self.assertEqual(account.actual['bytes'],5)
    def test_real_registration_preserves_validator_identity_known_environment_and_strong_receipts(self):
        from tests.test_tool_learning_certified_input import CertifiedInputTests
        from digital_life.infrastructure.persistence.sqlite_store import managed_database
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        from digital_life.infrastructure.persistence import tool_learning_meter as meter
        original=ToolLearningStore.validate_ref;stages=ExclusiveObserver();observer=MaterialObserver(stages);case=CertifiedInputTests();case.setUp()
        try:
            caps=deepcopy(json.loads(case.s.row('activities',case.f.activity)['budget_json'])['budget'])
            with material_observers(stages,observer):
                self.assertIs(ToolLearningStore.validate_ref,original);self.assertTrue(managed_database(case.s.db).known_read_environment())
                with stages.phase('assembly',case.s),case.meter().installed(case.s),case.e.owners.source.verification_boundary():case.register('/diagnostic-source')
                self.assertIs(ToolLearningStore.validate_ref,original)
            self.assertEqual(case.s._input_certificate_stats,dict(attempted=1,issued=1,accepted=1,fallback=0,committed=1,strong_material_accepted=1,strong_material_committed=1))
            self.assertEqual(json.loads(case.s.row('activities',case.f.activity)['budget_json'])['budget'],caps)
            report=observer.report();stage=next(r for r in report['stages']if r['label']=='assembly')
            self.assertGreater(stage['sql_totals']['rows'],0);self.assertGreater(stage['sql_totals']['bytes'],0)
            self.assertTrue(report['phase_readsets']);self.assertTrue(any(r['max_total_bytes']>0 for r in report['phase_readsets']))
            self.assertFalse(report['validator_identity_replaced']);self.assertFalse(report['sqlite_trace_or_row_observer_installed'])
        finally:case.doCleanups()
        self.assertIs(ToolLearningStore.validate_ref,original)
    def test_cache_hits_byte_rejections_samples_and_highwater_are_observed_after_original_logic(self):
        from tests.test_tool_learning_certified_input import CertifiedInputTests
        from digital_life.infrastructure.persistence.tool_learning_readset import current_readset,facts
        stages=ExclusiveObserver();observer=MaterialObserver(stages,sample_limit=1);case=CertifiedInputTests();case.setUp()
        try:
            with material_observers(stages,observer),case.meter().installed(case.s),case.e.owners.source.verification_boundary():
                phase=current_readset(case.s);list(facts(case.s,'source_kind',case.token['object']['id']));list(facts(case.s,'source_kind',case.token['object']['id']))
                old=phase.max_bytes;phase.max_bytes=phase.bytes+phase.blob_bytes
                try:
                    phase.remember_graph('synthetic-key','[]',0);phase.remember_graph('synthetic-key2','[]',0)
                finally:phase.max_bytes=old
            report=observer.report();events=report['phase_readsets'][0]['events'];self.assertGreater(events['facts:source_kind:hit'],0);self.assertEqual(events['graph:byte_limit'],2)
            sample=report['phase_readsets'][0]['samples']['graph'];self.assertEqual(len(sample['rejected_samples']),1);self.assertEqual(sample['rejected_unsampled_count'],1)
            self.assertEqual(sample['rejected_samples'][0]['requested_bytes'],len('synthetic-key')+len('[]')+1)
        finally:case.doCleanups()
    def test_main_preserves_forward_options_and_writes_material_report_on_failure(self):
        from evaluation import tool_learning_material_cache_diagnostic as tool
        from evaluation import tool_learning_continuation_diagnostic as original
        forwarded=[]
        def failed(argv):forwarded.extend(argv);raise RuntimeError('synthetic main failure')
        with tempfile.TemporaryDirectory()as directory,patch.object(original,'main',side_effect=failed):
            with self.assertRaisesRegex(RuntimeError,'synthetic main failure'):tool.main(['--source','synthetic','--output',directory,'--run-count','2'])
            result=json.loads((Path(directory)/'material-cache-diagnostic.json').read_text());self.assertEqual(result['main_error_type'],'RuntimeError')
        self.assertEqual(forwarded,['--counters-only','--source','synthetic','--output',directory,'--run-count','2'])
    def test_nested_original_row_observer_material_is_not_attributed_to_outer_sql(self):
        import sqlite3
        from digital_life.infrastructure.persistence import tool_learning_meter as meter
        from digital_life.domain.contracts import utc
        stages=ExclusiveObserver();observer=MaterialObserver(stages)
        limits={key:100000 for key in meter.DIMENSIONS};limits['elapsed_ms']=30000
        account=meter.PhysicalReadMeter(limits,utc(30));store=SimpleNamespace(db=sqlite3.connect(':memory:'))
        account.row_observer=lambda row:(meter.artifact_after(5),meter.material_produced(7))
        try:
            with material_observers(stages,observer),account.installed(store):self.assertEqual(store.db.execute('SELECT 1').fetchone(),(1,))
        finally:store.db.close()
        stage=observer.report()['stages'][0]
        self.assertEqual(stage['sql_totals']['bytes'],3)
        self.assertEqual(stage['non_sql']['artifact_body']['bytes'],5)
        self.assertEqual(stage['non_sql']['produced_material']['bytes'],7)
        self.assertEqual(account.actual['bytes'],15)
    def test_inline_fact_lru_eviction_reconciles_namespace_instead_of_accumulating_phantom_keys(self):
        from tests.test_tool_learning_certified_input import CertifiedInputTests
        from digital_life.infrastructure.persistence.tool_learning_readset import current_readset,facts
        stages=ExclusiveObserver();observer=MaterialObserver(stages);case=CertifiedInputTests();case.setUp()
        try:
            other=case.s.artifact({'synthetic diagnostic replacement':True})
            with material_observers(stages,observer),case.meter().installed(case.s),case.e.owners.source.verification_boundary():
                phase=current_readset(case.s);phase.max_keys=1
                list(facts(case.s,'source_kind',case.token['object']['id']));list(facts(case.s,'source_kind',other))
                record=observer.phase(phase)
                self.assertEqual(record['current']['facts:source_kind']['keys'],1)
                self.assertEqual(record['namespaces']['facts:source_kind']['max_keys'],1)
        finally:case.doCleanups()
