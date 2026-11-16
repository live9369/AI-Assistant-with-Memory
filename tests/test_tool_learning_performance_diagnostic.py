"""Observer arithmetic only; no real instance or model."""
import unittest
from evaluation.tool_learning_performance_diagnostic import PhaseObserver

class PhaseObserverTests(unittest.TestCase):
    def test_nested_exclusive_phases_conserve_wall_without_double_count(self):
        clock=[0.0];o=PhaseObserver(lambda:clock[0])
        clock[0]=1
        with o.phase('collect'):
            clock[0]=3
            with o.phase('check'):clock[0]=6
            clock[0]=7
        clock[0]=8
        r=o.report();p={p['phase']:p for p in r['phases']}
        self.assertEqual(r['exclusive_total_seconds'],8)
        self.assertEqual(p['collect']['exclusive_seconds'],3)
        self.assertEqual(p['collect']['inclusive_seconds'],6)
        self.assertEqual(p['check']['exclusive_seconds'],3)
    def test_error_closes_phase_and_sql_identity_keeps_parameter_differences(self):
        clock=[0.0];o=PhaseObserver(lambda:clock[0])
        with self.assertRaises(ValueError):
            with o.phase('check'):
                trace=o.trace('main');trace("SELECT * FROM x WHERE id='a'");trace("SELECT * FROM x WHERE id='a'");trace("SELECT * FROM x WHERE id='b'")
                clock[0]=2;raise ValueError('synthetic')
        p={p['phase']:p for p in o.report()['phases']}['check']
        self.assertEqual(o.stack,['other']);self.assertEqual(p['sql'],3)
        self.assertEqual(p['distinct_exact_sql'],2);self.assertEqual(p['repeated_exact_sql'],1)
        self.assertEqual(len(o.sql_shapes),1)

class ReadSetObserverTests(unittest.TestCase):
    def test_facts_and_graph_observers_preserve_hits_and_report_retention_limit(self):
        from contextlib import ExitStack
        from tempfile import TemporaryDirectory
        from evaluation.tool_learning_performance_diagnostic import install_readset_observers
        from digital_life.infrastructure.persistence.sqlite_store import Store
        from digital_life.infrastructure.persistence.tool_learning_readset import shared_read_boundary
        with TemporaryDirectory()as root:
            store=Store.prepare(root)
            try:
                actor=store.config()['controller'];statements=[]
                store.db.set_trace_callback(statements.append)
                with shared_read_boundary(store)as value:
                    # Real phase identity/generations and Row contract, with
                    # warmup outside the observer's one-request count window.
                    expected=tuple(value.read('source_kind',(actor,)))
                    self.assertEqual(expected[0]['kind'],'social_actors')
                    kind_reads=lambda:sum(sql.startswith('SELECT kind FROM object_registry WHERE instance_id=')for sql in statements)
                    before=kind_reads();self.assertEqual(before,1)
                    value.max_bytes=1000;value.max_keys=3
                    observer=PhaseObserver();patches=[];install_readset_observers(observer,patches)
                    with ExitStack()as stack:
                        for patch in patches:stack.enter_context(patch)
                        actual=tuple(value.read('source_kind',(actor,)))
                        self.assertEqual(actual,expected)
                        self.assertEqual(actual[0]['kind'],'social_actors')
                        self.assertEqual(kind_reads(),before)
                        self.assertIsNone(value.graph('graph-a'))
                        value.remember_graph('graph-a','[]',0)
                        self.assertEqual(value.graph('graph-a'),('[]',0))
                        value.remember_graph('oversize','x'*2000,2)
                        self.assertIsNone(value.graph('oversize'))
                    counts=observer.readset
                    self.assertEqual(counts['facts_requests'],1);self.assertEqual(counts['facts_exact_hits'],1)
                    self.assertEqual(counts['facts_sql_reads'],0);self.assertEqual(counts['graph_hits'],1)
                    self.assertEqual(counts['graph_retain_retained'],1);self.assertEqual(counts['graph_retain_too_large'],1)
                    self.assertEqual(observer.readset_peaks['graph_keys'],1)
                    self.assertGreaterEqual(observer.readset_times['read'],0)
            finally:store.close()
