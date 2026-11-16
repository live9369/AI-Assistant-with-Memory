"""Actual fixed input writes preserve pure material, never authorization."""
from unittest.mock import patch
import unittest
from digital_life.infrastructure.persistence.tool_learning_readset import current_readset,facts
from digital_life.infrastructure.persistence.sqlite_store import managed_database
from tests import test_tool_learning_certified_input as fixture

class InsertOnlyRetentionTests(unittest.TestCase):
    def setUp(self):
        self.case=fixture.CertifiedInputTests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.s=self.case.s;self.e=self.case.e
    def _registration(self,strong=True):
        c=self.case;original=self.s._insert_input_registration;observed={};new_id='f'*32
        def insert(fields):
            phase=current_readset(self.s)
            positive=('source_kind',(c.token['object']['id'],));negative=('source_kind',(new_id,))
            self.assertEqual(next(iter(facts(self.s,'source_kind',new_id)),None),None)
            self.assertEqual(next(iter(facts(self.s,'source_kind',c.token['object']['id'])))[0],c.token['object']['kind'])
            before_budget={'remaining':4096}
            before_graph=self.e.runtime.eligibility._upstream(c.token,c.scope,before_budget)
            self.e.runtime.eligibility._upstream(c.token,c.scope,{'remaining':4096})
            graphs=dict(phase.graphs);prepared={key:value for key,value in phase.prepared.items()if key and key[0]in ('TL-DEPENDENCY-1','TL-DEPENDENCY-BINDING-1')};generation=phase.generation
            self.assertTrue(graphs);self.assertTrue(prepared)
            with patch('digital_life.infrastructure.persistence.sqlite_store.identifier',return_value=new_id):result=original(fields)
            self.assertEqual(result,new_id);self.assertNotIn(negative,phase.cache)
            self.assertEqual(positive in phase.cache,strong)
            self.assertEqual(bool(phase.graphs),strong);self.assertEqual(bool(phase.prepared),strong)
            if strong:
                self.assertEqual(phase.graphs,graphs);self.assertEqual(phase.prepared,prepared)
            self.assertEqual(bool(phase.admissions),strong);self.assertGreater(phase.generation,generation)
            after_budget={'remaining':4096}
            self.assertEqual(self.e.runtime.eligibility._upstream(c.token,c.scope,after_budget),before_graph)
            self.assertEqual(after_budget,before_budget)
            self.assertEqual(next(iter(facts(self.s,'source_kind',new_id)))[0],'tl_input_dependency')
            observed['phase']=phase;return result
        with c.meter().installed(self.s),self.e.owners.source.verification_boundary():
            with patch.object(self.s,'_insert_input_registration',side_effect=insert):c.register('/insert-only')
            phase=observed['phase']
            if strong:self.assertTrue(phase.graphs);self.assertTrue(phase.prepared)
        self.assertEqual(self.s._input_certificate_stats['issued'],1)
        self.assertEqual(self.s._input_certificate_stats['accepted'],1)
        self.assertEqual(self.s._input_certificate_stats['committed'],1)
        self.assertEqual(self.s._input_certificate_stats['strong_material_accepted'],int(strong))
        self.assertEqual(self.s._input_certificate_stats['strong_material_committed'],int(strong))
    def test_positive_kind_and_real_graph_metadata_survive_negative_kind_becomes_positive(self):
        self._registration()
    def test_weaker_table_receipt_does_not_preserve_positive_or_prepared_material(self):
        managed=managed_database(self.s.db)
        with patch.object(managed,'insert_only_receipt',return_value=False):self._registration(False)
    def test_custom_collation_keeps_ordinary_registration_but_disables_strong_retention(self):
        self.s.db.create_collation('synthetic_order',lambda left,right:(left>right)-(left<right))
        self._registration(False)
    def test_prepared_metadata_rechecks_ref_and_revision_instead_of_reusing_verdict(self):
        c=self.case;eligibility=self.e.runtime.eligibility
        with c.meter().installed(self.s),self.e.owners.source.verification_boundary():
            key=eligibility.register_dependency(c.entry,c.principal,c.consumer,c.dep,'/prepared-ref',c.scope)
            row=self.s.row('tl_dependency',key)
            first=eligibility._metadata(row);phase=current_readset(self.s)
            self.assertTrue(phase.prepared)
            with patch.object(eligibility.artifacts,'validate_ref',wraps=eligibility.artifacts.validate_ref)as validate:
                self.assertEqual(eligibility._metadata(row),first)
                self.assertGreaterEqual(validate.call_count,2)
