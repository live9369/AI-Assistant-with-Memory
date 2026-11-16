"""Same-bound facts LRU replaces rereadable data, never live decisions."""
from copy import deepcopy
import unittest
from digital_life.infrastructure.persistence.tool_learning_readset import current_readset,facts
from tests import test_tool_learning_certified_input as fixture

class FactReplacementTests(unittest.TestCase):
    def setUp(self):
        self.c=fixture.CertifiedInputTests();self.c.setUp();self.addCleanup(self.c.doCleanups);self.s=self.c.s
        self.ids=[self.s.artifact({'synthetic replacement source':n})for n in range(3)]
    def boundary(self):return self.c.e.owners.source.verification_boundary()
    def get(self,key):return list(facts(self.s,'source_kind',key))
    def accounting(self,phase):
        self.assertEqual(phase.bytes,sum(phase.fact_sizes.values())+sum(phase.prepared_sizes.values())+sum(phase.graph_sizes.values())+sum(phase.admission_sizes.values()))
        self.assertLessEqual(phase.bytes+phase.blob_bytes,phase.max_bytes);self.assertLessEqual(phase.entry_count(),phase.max_keys)
    def test_exact_hit_moves_hot_fact_and_only_cold_fact_is_replaced(self):
        with self.c.meter().installed(self.s),self.boundary():
            phase=current_readset(self.s);phase.max_keys=2
            self.get(self.ids[0]);self.get(self.ids[1]);self.get(self.ids[0]);self.get(self.ids[2])
            self.assertIn(('source_kind',(self.ids[0],)),phase.cache);self.assertNotIn(('source_kind',(self.ids[1],)),phase.cache)
            self.assertIn(('source_kind',(self.ids[2],)),phase.cache);self.accounting(phase)
    def test_byte_bound_reclaims_data_without_increasing_limit(self):
        with self.c.meter().installed(self.s),self.boundary():
            phase=current_readset(self.s);self.get(self.ids[0]);self.get(self.ids[1]);limit=phase.bytes+phase.blob_bytes;phase.max_bytes=limit
            self.get(self.ids[0]);self.get(self.ids[2]);self.assertEqual(phase.max_bytes,limit);self.assertNotIn(('source_kind',(self.ids[1],)),phase.cache);self.accounting(phase)
    def test_complete_prefix_hit_touches_full_entry_and_preserves_original_row(self):
        with self.c.meter().installed(self.s),self.boundary():
            phase=current_readset(self.s);phase.max_keys=2;consumer=self.c.token['object']['id']
            all_rows=list(facts(self.s,'consumer_dependency_materials',consumer,100));self.get(self.ids[0])
            first=list(facts(self.s,'consumer_dependency_materials',consumer,1));self.assertEqual(dict(first[0]),dict(all_rows[0]))
            self.get(self.ids[1]);self.assertIn(('consumer_dependency_materials',('complete',consumer)),phase.cache)
            self.assertNotIn(('source_kind',(self.ids[0],)),phase.cache);self.accounting(phase)
    def test_oversized_fact_rejects_before_destroying_existing_cache(self):
        with self.c.meter().installed(self.s),self.boundary():
            phase=current_readset(self.s);phase.max_keys=2;self.get(self.ids[0]);self.get(self.ids[1]);before=dict(phase.cache);sizes=dict(phase.fact_sizes)
            phase.remember(('source_kind',('too-large',)),(),size=phase.max_bytes+1)
            self.assertEqual(phase.cache,before);self.assertEqual(phase.fact_sizes,sizes);self.accounting(phase)
    def test_only_when_facts_exhausted_can_prepared_data_be_reclaimed(self):
        with self.c.meter().installed(self.s),self.boundary():
            phase=current_readset(self.s);phase.max_keys=1;phase.remember_prepared_metadata(('synthetic-parse',),'{}','');self.assertTrue(phase.prepared)
            self.get(self.ids[0]);self.assertFalse(phase.prepared);self.assertEqual(phase.entry_count(),1);self.accounting(phase)
    def test_graph_admission_and_tracked_files_are_outside_fact_victim_pool(self):
        with self.c.meter().installed(self.s),self.boundary():
            phase=current_readset(self.s);phase.track_artifact(self.ids[0]);phase._clear_entries();files=dict(phase.blobs);blob_bytes=phase.blob_bytes
            phase.max_keys=1;phase.remember_graph('synthetic-pure-graph','[]',0);self.get(self.ids[1])
            self.assertIn('synthetic-pure-graph',phase.graphs);self.assertFalse(phase.cache);self.assertEqual(phase.blobs,files);self.assertEqual(phase.blob_bytes,blob_bytes);self.accounting(phase)
    def test_unknown_observer_keeps_original_firstcome_and_row_delivery(self):
        account=self.c.meter();observed=[];account.row_observer=lambda row:observed.append(dict(row))
        with account.installed(self.s),self.boundary():
            phase=current_readset(self.s);phase.max_keys=2;self.get(self.ids[0]);self.get(self.ids[1]);self.get(self.ids[0]);self.get(self.ids[2])
            self.assertIn(('source_kind',(self.ids[0],)),phase.cache);self.assertIn(('source_kind',(self.ids[1],)),phase.cache)
            self.assertNotIn(('source_kind',(self.ids[2],)),phase.cache);self.assertEqual(len([r for r in observed if 'kind'in r]),4);self.accounting(phase)
    def test_sqlite_callback_cannot_evict_or_remember_new_fact(self):
        with self.c.meter().installed(self.s),self.boundary():
            phase=current_readset(self.s);phase.max_keys=2;self.get(self.ids[0]);self.get(self.ids[1]);before=dict(phase.cache)
            def callback():phase.remember(('source_kind',('callback-only',)),());return 1
            self.s.db.create_function('synthetic_cache_callback',0,callback)
            # Registry configuration change invalidates old facts at next real
            # lookup, so this case exercises direct callback remember only.
            self.s.db.execute('SELECT synthetic_cache_callback()').fetchone()
            self.assertEqual(phase.cache,before);self.accounting(phase)
    def test_prepared_data_yields_before_any_existing_fact_under_shared_key_pressure(self):
        with self.c.meter().installed(self.s),self.boundary():
            phase=current_readset(self.s);phase.max_keys=2
            self.get(self.ids[0]);phase.remember_prepared_metadata(('synthetic-rebuildable',),'{}','')
            before_files=dict(phase.blobs);self.get(self.ids[1])
            self.assertIn(('source_kind',(self.ids[0],)),phase.cache)
            self.assertIn(('source_kind',(self.ids[1],)),phase.cache)
            self.assertFalse(phase.prepared);self.assertEqual(phase.blobs,before_files);self.accounting(phase)
