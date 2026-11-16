"""Profiler arithmetic/semantics and one small real receipt; no full thought."""
import builtins
from contextlib import contextmanager
from copy import deepcopy
import json
from types import SimpleNamespace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from evaluation.tool_learning_continuation_diagnostic import (ExclusiveObserver,deferred_install,product_observers,
    certificate_snapshot,file_signature_snapshot,graph_material_snapshot,CERTIFICATE_KEYS,OPTIONAL_CERTIFICATE_KEYS)


class ExclusiveContinuationDiagnosticTests(unittest.TestCase):
    def test_nested_exclusive_times_partition_wall_and_keep_return_identity(self):
        clock=[0.];observer=ExclusiveObserver(lambda:clock[0],lambda:clock[0]);value=object()
        store=SimpleNamespace(_input_certificate_stats={k:0 for k in ('attempted','issued','accepted','fallback','committed')})
        def child():clock[0]=5.;return value
        measured_child=observer.wrap('child',child)
        def parent():
            clock[0]=2.;self.assertIs(measured_child(),value);clock[0]=7.;return value
        measured_parent=observer.wrap('parent',parent)
        clock[0]=1.
        with observer.phase('assembly',store):
            self.assertIs(measured_parent(),value);clock[0]=8.
        clock[0]=10.;report=observer.report();self.assertEqual(report['wall_seconds'],10.)
        self.assertEqual(report['exclusive_seconds_sum'],10.)
        stage=report['phases'][1];methods={v['label']:v for v in stage['methods']}
        self.assertEqual(stage['exclusive_seconds'],7.);self.assertEqual(stage['parent_cpu_exclusive_seconds'],7.)
        self.assertEqual(methods['parent']['exclusive_seconds'],3.);self.assertEqual(methods['child']['exclusive_seconds'],3.)
        self.assertEqual(methods['parent']['inclusive_seconds'],6.);self.assertEqual(methods['parent']['calls'],1)
        self.assertEqual(sum(v['exclusive_seconds']for v in stage['methods']),stage['exclusive_seconds'])
        self.assertEqual(stage['certificate_delta'],{k:0 for k in store._input_certificate_stats})

    def test_context_order_exception_identity_and_unknown_label_not_recorded(self):
        clock=[0.];observer=ExclusiveObserver(lambda:clock[0],lambda:clock[0]);events=[];failure=ValueError('synthetic not recorded');value=object()
        @contextmanager
        def original(engine,*args,**kwargs):
            events.append('enter')
            try:yield value
            finally:events.append('exit')
        wrapped=observer.wrap_read_operation(original);engine=SimpleNamespace(s=SimpleNamespace())
        with self.assertRaises(ValueError)as caught:
            with wrapped(engine,'entry','activity','context','secret-raw-stage',{} )as returned:
                self.assertIs(returned,value);events.append('body');clock[0]=2.;raise failure
        self.assertIs(caught.exception,failure);self.assertEqual(events,['enter','body','exit'])
        report=observer.report();self.assertEqual(report['phases'][1]['label'],'other_read_operation')
        self.assertNotIn('secret-raw-stage',json.dumps(report));self.assertNotIn(str(failure),json.dumps(report))
        self.assertEqual(observer.methods,[]);self.assertEqual(observer.phase_stack,[0])

    def test_deferred_install_runs_only_after_original_fixture_import(self):
        events=[];module=object()
        def original(name,globals=None,locals=None,fromlist=(),level=0):events.append(('imported',name));return module
        with patch.object(builtins,'__import__',original):
            with deferred_install(lambda:events.append(('installed',)))as state:
                self.assertFalse(state['installed']);self.assertEqual(events,[])
                self.assertIs(builtins.__import__('unrelated',fromlist=('x',)),module)
                self.assertFalse(state['installed'])
                self.assertIs(builtins.__import__('tests.test_tool_learning_runtime',fromlist=('StrictEngineEndToEndTests',)),module)
                self.assertTrue(state['installed']);self.assertIs(builtins.__import__,original)
            self.assertIs(builtins.__import__,original)
        self.assertEqual(events[-2:],[('imported','tests.test_tool_learning_runtime'),('installed',)])

    def test_real_small_registration_keeps_receipt_and_original_budget_caps(self):
        from tests.test_tool_learning_certified_input import CertifiedInputTests
        from digital_life.infrastructure.persistence.sqlite_write_monitor import ManagedConnection
        original=ManagedConnection._run;observer=ExclusiveObserver();case=CertifiedInputTests()
        with product_observers(observer)as installed:
            self.assertEqual(installed['missing'],[]);self.assertFalse(installed['sqlite_trace_or_hook_installed'])
            case.setUp()
            try:
                caps=deepcopy(json.loads(case.s.row('activities',case.f.activity)['budget_json'])['budget'])
                with case.e._read_operation(case.entry,case.f.activity,case.context,'assembly',case.e._read_slice(case.f.activity,.5)),case.e.owners.source.verification_boundary():case.register()
                self.assertEqual({k:case.s._input_certificate_stats[k]for k in CERTIFICATE_KEYS},{'attempted':1,'issued':1,'accepted':1,'fallback':0,'committed':1})
                budget=json.loads(case.s.row('activities',case.f.activity)['budget_json']);self.assertEqual(budget['budget'],caps)
                self.assertTrue(all(r['state']=='settled'for r in budget['ledger']['reservations'].values()))
                changes=case.s.db.total_changes;report=observer.report();self.assertEqual(case.s.db.total_changes,changes)
            finally:case.doCleanups()
        self.assertIs(ManagedConnection._run,original)
        stage=next(v for v in report['phases']if v['label']=='assembly')
        self.assertEqual({k:stage['certificate_delta'][k]for k in CERTIFICATE_KEYS},{'attempted':1,'issued':1,'accepted':1,'fallback':0,'committed':1})
        methods={r['label']:r for r in report['method_totals']}
        for name in ('ManagedConnection._authorize','ManagedConnection._run','ManagedConnection._refresh_registry'):
            self.assertGreater(methods[name]['calls'],0)
        self.assertAlmostEqual(report['exclusive_seconds_sum'],report['wall_seconds'],places=6)

    def test_original_options_forward_unchanged_and_profile_installs_after_world(self):
        from evaluation import tool_learning_continuation_diagnostic as tool
        events=[];captured=[];old_argv=sys.argv
        @contextmanager
        def observers(observer,counters_only=False):
            self.assertFalse(counters_only)
            events.append('installed');yield {'installed':['synthetic-method'],'missing':[]}
        def original_main():
            captured.extend(sys.argv[1:]);events.append('world-fixed')
            builtins.__import__('tests.test_tool_learning_runtime',fromlist=('StrictEngineEndToEndTests',))
            events.append('fixture-set-up');return 1
        fake_module=SimpleNamespace(main=original_main)
        spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
        with tempfile.TemporaryDirectory()as directory:
            output=Path(directory)/'scale';forward=['--history','17','--source','public-source','--continuous','2','--output',str(output)]
            with patch.object(tool.importlib.util,'spec_from_file_location',return_value=spec),patch.object(tool.importlib.util,'module_from_spec',return_value=fake_module),patch.object(tool,'product_observers',observers):
                self.assertEqual(tool.main(forward),1)
            report=json.loads((output/'continuation-diagnostic.json').read_text())
        self.assertEqual(captured,forward);self.assertEqual(events,['world-fixed','installed','fixture-set-up'])
        self.assertIs(sys.argv,old_argv);self.assertTrue(report['deferred_installation']['installed'])
        self.assertEqual(report['scale_main_return'],1);self.assertIsNone(report['scale_main_error_type'])

    def test_counters_only_flag_is_consumed_without_changing_scale_options(self):
        from evaluation import tool_learning_continuation_diagnostic as tool
        captured=[];modes=[]
        @contextmanager
        def observers(observer,counters_only=False):
            modes.append(counters_only);yield {'installed':['StrictEngine._read_operation'],'missing':[]}
        def original_main():
            captured.extend(sys.argv[1:])
            builtins.__import__('tests.test_tool_learning_runtime',fromlist=('StrictEngineEndToEndTests',))
            return 0
        spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
        with tempfile.TemporaryDirectory()as directory:
            output=Path(directory)/'scale';forward=['--history','17','--source','public-source','--continuous','2','--output',str(output)]
            own=[*forward[:2],'--counters-only',*forward[2:]]
            with patch.object(tool.importlib.util,'spec_from_file_location',return_value=spec),patch.object(tool.importlib.util,'module_from_spec',return_value=SimpleNamespace(main=original_main)),patch.object(tool,'product_observers',observers):
                self.assertEqual(tool.main(own),0)
            report=json.loads((output/'continuation-diagnostic.json').read_text())
        self.assertEqual(captured,forward);self.assertEqual(modes,[True]);self.assertEqual(report['measurement_mode'],'counters-only')
        self.assertTrue(all(row['label']=='unattributed'and row['calls']==0 for row in report['method_totals']))

    def test_counters_only_has_no_method_wrappers_and_real_receipt_still_works(self):
        from tests.test_tool_learning_certified_input import CertifiedInputTests
        from digital_life.infrastructure.persistence.sqlite_write_monitor import ManagedConnection
        from digital_life.application.learning.runtime_owners import LocalRuntimeOwners
        original_run=ManagedConnection._run;original_check=LocalRuntimeOwners.check
        observer=ExclusiveObserver();case=CertifiedInputTests()
        with product_observers(observer,counters_only=True)as installed:
            self.assertEqual(installed['installed'],['StrictEngine._read_operation']);self.assertEqual(installed['mode'],'counters-only')
            self.assertIs(ManagedConnection._run,original_run);self.assertIs(LocalRuntimeOwners.check,original_check)
            case.setUp()
            try:
                with case.e._read_operation(case.entry,case.f.activity,case.context,'assembly',case.e._read_slice(case.f.activity,.5)),case.e.owners.source.verification_boundary():case.register()
                self.assertEqual({k:case.s._input_certificate_stats[k]for k in CERTIFICATE_KEYS},{'attempted':1,'issued':1,'accepted':1,'fallback':0,'committed':1})
                changes=case.s.db.total_changes;report=observer.report();self.assertEqual(case.s.db.total_changes,changes)
            finally:case.doCleanups()
        self.assertTrue(all(row['label']=='unattributed'and row['calls']==0 for row in report['method_totals']))
        stage=next(row for row in report['phases']if row['label']=='assembly')
        self.assertEqual({k:stage['certificate_delta'][k]for k in CERTIFICATE_KEYS},{'attempted':1,'issued':1,'accepted':1,'fallback':0,'committed':1})

    def test_missing_optional_strong_counters_preserve_old_observed_five_keys(self):
        counts={k:i for i,k in enumerate(CERTIFICATE_KEYS)};store=SimpleNamespace(_input_certificate_stats=dict(counts))
        self.assertEqual(certificate_snapshot(store),{'status':'observed','counts':counts})
        observer=ExclusiveObserver()
        with observer.phase('assembly',store):pass
        stage=observer.report()['phases'][1]
        self.assertEqual(stage['certificate_delta'],{k:0 for k in CERTIFICATE_KEYS})
        for key in OPTIONAL_CERTIFICATE_KEYS:
            self.assertNotIn(key,stage['certificate_before']['counts']);self.assertNotIn(key,stage['certificate_after']['counts'])
            self.assertNotIn(key,stage['certificate_delta'])

    def test_optional_strong_counters_keep_actual_values_and_only_known_deltas(self):
        counts={k:0 for k in CERTIFICATE_KEYS};counts.update(strong_material_accepted=7,strong_material_committed=5)
        store=SimpleNamespace(_input_certificate_stats=counts);observer=ExclusiveObserver()
        self.assertEqual(certificate_snapshot(store)['counts'],counts)
        with observer.phase('assembly',store):
            counts['strong_material_accepted']=9;counts['strong_material_committed']=6
        stage=observer.report()['phases'][1]
        self.assertEqual(stage['certificate_before']['counts']['strong_material_accepted'],7)
        self.assertEqual(stage['certificate_after']['counts']['strong_material_accepted'],9)
        self.assertEqual(stage['certificate_delta']['strong_material_accepted'],2)
        self.assertEqual(stage['certificate_delta']['strong_material_committed'],1)
        self.assertEqual({k:stage['certificate_delta'][k]for k in CERTIFICATE_KEYS},{k:0 for k in CERTIFICATE_KEYS})
        late_store=SimpleNamespace(_input_certificate_stats={k:0 for k in CERTIFICATE_KEYS});late_observer=ExclusiveObserver()
        with late_observer.phase('assembly',late_store):late_store._input_certificate_stats['strong_material_accepted']=4
        late_stage=late_observer.report()['phases'][1]
        self.assertEqual(late_stage['certificate_after']['counts']['strong_material_accepted'],4)
        self.assertNotIn('strong_material_accepted',late_stage['certificate_delta'])

    def test_absent_file_signature_counters_do_not_invent_zero_or_change_receipts(self):
        store=SimpleNamespace(_input_certificate_stats={k:0 for k in CERTIFICATE_KEYS})
        self.assertIsNone(file_signature_snapshot(store));observer=ExclusiveObserver()
        with observer.phase('assembly',store):pass
        stage=observer.report()['phases'][1]
        self.assertNotIn('file_signature_stats',stage)
        self.assertEqual(stage['certificate_delta'],{k:0 for k in CERTIFICATE_KEYS})
        self.assertEqual(stage['certificate_after']['status'],'observed')
        store._file_signature_stats={'minted':True,'hits':'unknown'}
        self.assertIsNone(file_signature_snapshot(store))

    def test_actual_file_signature_values_and_delta_are_stage_only(self):
        store=SimpleNamespace(_input_certificate_stats={k:0 for k in CERTIFICATE_KEYS},_file_signature_stats={'minted':3,'hits':11})
        self.assertEqual(file_signature_snapshot(store),{'minted':3,'hits':11});observer=ExclusiveObserver()
        with observer.phase('assembly',store):store._file_signature_stats.update(minted=5,hits=18)
        report=observer.report();stage=report['phases'][1]
        self.assertEqual(stage['file_signature_stats'],{'before':{'minted':3,'hits':11},'after':{'minted':5,'hits':18},'delta':{'minted':2,'hits':7}})
        self.assertTrue(all(row['label']=='unattributed'and row['calls']==0 for row in report['method_totals']))
        self.assertEqual(stage['certificate_delta'],{k:0 for k in CERTIFICATE_KEYS})
        late_store=SimpleNamespace();late_observer=ExclusiveObserver()
        with late_observer.phase('assembly',late_store):late_store._file_signature_stats={'hits':9}
        self.assertEqual(late_observer.report()['phases'][1]['file_signature_stats'],{'after':{'hits':9}})

    def test_absent_or_legacy_graph_counters_do_not_invent_used(self):
        store=SimpleNamespace();self.assertIsNone(graph_material_snapshot(store));observer=ExclusiveObserver()
        with observer.phase('assembly',store):pass
        self.assertNotIn('graph_material_stats',observer.report()['phases'][1])
        legacy={'eligible':2,'stored':1,'returned':6};store._graph_material_stats=dict(legacy)
        self.assertEqual(graph_material_snapshot(store),legacy);observer=ExclusiveObserver()
        with observer.phase('assembly',store):store._graph_material_stats['returned']=7
        stats=observer.report()['phases'][1]['graph_material_stats']
        self.assertEqual(stats['before'],legacy);self.assertEqual(stats['after'],dict(legacy,returned=7))
        self.assertEqual(stats['delta'],{'eligible':0,'stored':0,'returned':1})
        for endpoint in ('before','after','delta'):self.assertNotIn('used',stats[endpoint])

    def test_actual_graph_counters_distinguish_returned_from_used(self):
        initial={'eligible':4,'stored':2,'returned':8,'used':3};store=SimpleNamespace(_graph_material_stats=dict(initial))
        observer=ExclusiveObserver()
        with observer.phase('assembly',store):store._graph_material_stats.update(eligible=6,stored=3,returned=13,used=4)
        report=observer.report();stats=report['phases'][1]['graph_material_stats']
        self.assertEqual(stats['before'],initial);self.assertEqual(stats['after'],{'eligible':6,'stored':3,'returned':13,'used':4})
        self.assertEqual(stats['delta'],{'eligible':2,'stored':1,'returned':5,'used':1})
        self.assertTrue(all(row['label']=='unattributed'and row['calls']==0 for row in report['method_totals']))
        late_store=SimpleNamespace();late_observer=ExclusiveObserver()
        with late_observer.phase('assembly',late_store):late_store._graph_material_stats={'used':2}
        self.assertEqual(late_observer.report()['phases'][1]['graph_material_stats'],{'after':{'used':2}})
