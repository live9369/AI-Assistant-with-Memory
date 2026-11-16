"""Known F1/Store write endings invalidate facts; unknown raw endings never rebase."""
import sqlite3
import unittest
from unittest.mock import patch
from digital_life.application.learning.eligibility import ref
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,utc
from digital_life.domain.tool_learning_resources import DIMENSIONS
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter,immutable_reference_boundary,_REFERENCE_BOUNDARY
from digital_life.infrastructure.persistence.tool_learning_readset import shared_read_boundary,checkpoint
from digital_life.infrastructure.persistence.tool_learning_store import CommitUnknown

class OwnedTransactionBoundaryTests(unittest.TestCase):
    def setUp(self):
        from tests import test_tool_learning_invalidation as f1
        fixture=f1.F1Tests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.f=fixture;self.s=fixture.s;self.adapter=fixture.service.storage
        self.s.db.execute('PRAGMA journal_mode=WAL')
        self.s.db.execute('CREATE TABLE owned_boundary_probe(value INTEGER)');self.s.db.execute('INSERT INTO owned_boundary_probe VALUES(0)')
    def meter(self):return PhysicalReadMeter({k:100000000 for k in DIMENSIONS},utc(60))
    def external_write(self):
        db=sqlite3.connect(self.s.root/'runtime.sqlite')
        try:db.execute('UPDATE owned_boundary_probe SET value=value+1');db.commit()
        finally:db.close()
    def test_real_f1_commit_rebases_only_acknowledged_boundary_and_legal_refs_continue(self):
        with immutable_reference_boundary(self.s),shared_read_boundary(self.s)as phase:
            self.adapter.validate_ref(self.f.source);generation=phase.generation
            result=self.f.apply();self.assertEqual(result['disposition'],'applied')
            self.assertGreater(phase.generation,generation);checkpoint(self.s)
            self.adapter.validate_ref(ref(self.s,self.f.f.expected['controller']))
    def test_real_f1_rollback_removes_new_ref_proofs_and_tracked_material_without_refunding_usage(self):
        meter=self.meter();created=[];before=[];original=self.f.service._apply
        def fail(tx,entry,request):
            original(tx,entry,request)
            key=self.s.artifact({'new uncommitted artifact':True});created.append(ref(self.s,key))
            self.adapter.read_artifact(key);self.adapter.validate_ref(created[0]);before.append(dict(meter.actual))
            self.assertTrue(_REFERENCE_BOUNDARY.get()['cache'])
            raise ValueError('original synthetic F1 rollback')
        with meter.installed(self.s),immutable_reference_boundary(self.s),shared_read_boundary(self.s)as phase:
            with patch.object(self.f.service,'_apply',fail),self.assertRaisesRegex(ValueError,'original synthetic F1 rollback'):self.f.apply()
            self.assertFalse(_REFERENCE_BOUNDARY.get()['cache']);self.assertFalse(phase.blobs)
            with self.assertRaises(ContractError):self.adapter.validate_ref(created[0])
            self.assertGreaterEqual(meter.actual['bytes'],before[0]['bytes']);self.assertGreaterEqual(meter.actual['scan'],before[0]['scan'])
            self.adapter.validate_ref(ref(self.s,self.f.f.expected['controller']));checkpoint(self.s)
    def test_plain_store_rollback_clears_transaction_local_reference_proof(self):
        created=[]
        with immutable_reference_boundary(self.s),shared_read_boundary(self.s)as phase:
            with self.assertRaisesRegex(ValueError,'plain rollback'):
                with self.s.tx():
                    key=self.s.artifact({'plain new uncommitted artifact':True});created.append(ref(self.s,key))
                    self.adapter.read_artifact(key);self.adapter.validate_ref(created[0]);raise ValueError('plain rollback')
            self.assertFalse(_REFERENCE_BOUNDARY.get()['cache']);self.assertFalse(phase.blobs)
            with self.assertRaises(ContractError):self.adapter.validate_ref(created[0])
            checkpoint(self.s)
    def test_old_cached_iterator_cannot_cross_known_outer_commit(self):
        from digital_life.infrastructure.persistence.tool_learning_readset import facts
        with shared_read_boundary(self.s)as phase:
            list(facts(self.s,'source_kind',self.f.source['id']))
            old=facts(self.s,'source_kind',self.f.source['id']);before=phase.transaction_generation
            self.f.apply();self.assertGreater(phase.transaction_generation,before)
            with self.assertRaisesRegex(Conflict,'transaction ended'):next(iter(old))
    def test_old_absence_iterator_cannot_cross_known_outer_rollback(self):
        from digital_life.infrastructure.persistence.tool_learning_readset import facts
        with shared_read_boundary(self.s):
            list(facts(self.s,'source_kind','f'*32));old=facts(self.s,'source_kind','f'*32)
            with self.assertRaises(ValueError):
                with self.s.tx():raise ValueError('synthetic rollback')
            with self.assertRaisesRegex(Conflict,'transaction ended'):next(iter(old),None)
    def test_nested_successful_snapshot_style_savepoint_does_not_end_outer_iterator(self):
        from digital_life.infrastructure.persistence.tool_learning_readset import facts
        with shared_read_boundary(self.s)as phase:
            with self.s.tx():
                list(facts(self.s,'source_kind',self.f.source['id']));old=facts(self.s,'source_kind',self.f.source['id']);before=phase.transaction_generation
                with self.s.tx():self.s.db.execute('UPDATE owned_boundary_probe SET value=value+1')
                self.assertEqual(phase.transaction_generation,before)
                self.assertEqual(next(iter(old))['kind'],self.f.source['kind'])
    def test_nested_savepoint_rollback_clears_new_ref_proof_before_outer_end(self):
        with immutable_reference_boundary(self.s),shared_read_boundary(self.s)as phase:
            with self.s.tx():
                before=phase.transaction_generation
                with self.assertRaises(ValueError):
                    with self.s.tx():
                        key=self.s.artifact({'nested new ref':True});value=ref(self.s,key)
                        self.adapter.validate_ref(value);raise ValueError('nested rollback')
                self.assertEqual(phase.transaction_generation,before)
                with self.assertRaises(ContractError):self.adapter.validate_ref(value)
    def test_nested_rollback_discards_phantom_dependency_metadata_and_lazy_rows_without_rebasing(self):
        from digital_life.application.learning.engine import _dependency
        from digital_life.infrastructure.persistence.tool_learning_readset import facts
        meter=self.meter();phantom=[];old=[]
        with meter.installed(self.s),immutable_reference_boundary(self.s),shared_read_boundary(self.s)as phase:
            with self.s.tx():
                before_tx=phase.transaction_generation;before_version=phase.primary_version
                with self.assertRaises(ValueError):
                    with self.s.tx():
                        consumer=ref(self.s,self.s.artifact({'phantom consumer':True}))
                        source=ref(self.s,self.s.artifact({'phantom source':True}));token={'object':source,'revision':0,'epoch':0}
                        _dependency(self.s,consumer,token,self.f.scope,'read','/phantom','learn')
                        rows=list(facts(self.s,'consumer_dependencies',consumer['id'],128));phantom.append((consumer,rows[0]))
                        self.f.elig._metadata(rows[0]);self.assertTrue(phase.prepared)
                        old.append(facts(self.s,'consumer_dependencies',consumer['id'],128));raise ValueError('nested phantom rollback')
                self.assertEqual(phase.transaction_generation,before_tx);self.assertEqual(phase.primary_version,before_version)
                self.assertFalse(phase.prepared);self.assertFalse(phase.blobs)
                with self.assertRaisesRegex(Conflict,'rolled back'):next(iter(old[0]))
                self.assertEqual(list(facts(self.s,'consumer_dependencies',phantom[0][0]['id'],128)),[])
                with self.assertRaises(ContractError):self.f.elig._metadata(phantom[0][1])
            checkpoint(self.s)
    def test_foreign_commit_during_blob_cleanup_is_not_hidden_by_owned_commit(self):
        original=self.s._discard_unregistered_blobs
        def cleanup_then_foreign(created):
            result=original(created);self.external_write();return result
        with self.assertRaises(Conflict),shared_read_boundary(self.s):
            with patch.object(self.s,'_discard_unregistered_blobs',cleanup_then_foreign):self.f.apply()
    def test_unknown_commit_ack_closes_phase_and_never_revives_reference_cache(self):
        original=self.adapter._commit;phase=None
        def lost_ack():original();raise sqlite3.OperationalError('synthetic lost ack')
        with self.assertRaises(CommitUnknown),immutable_reference_boundary(self.s),shared_read_boundary(self.s)as phase:
            self.adapter.validate_ref(self.f.source)
            with patch.object(self.adapter,'_commit',lost_ack):self.f.apply()
        self.assertTrue(phase.closed);self.assertFalse(phase.cache)
    def test_failed_rollback_unknown_outcome_closes_phase_and_preserves_original_protocol(self):
        meter=self.meter();phase=None
        with meter.installed(self.s):
            original=self.s.db.execute
            def failing_rollback(sql,*args,**kwargs):
                if sql=='ROLLBACK':raise sqlite3.OperationalError('synthetic rollback acknowledgement lost')
                return original(sql,*args,**kwargs)
            try:
                with self.assertRaises(CommitUnknown),immutable_reference_boundary(self.s),shared_read_boundary(self.s)as phase:
                    with patch.object(self.f.service,'_apply',side_effect=ValueError('original body')),patch.object(self.s.db,'execute',failing_rollback):self.f.apply()
                self.assertTrue(phase.closed);self.assertTrue(self.s.db.in_transaction)
            finally:
                if self.s.db.in_transaction:self.s.db.execute('ROLLBACK')
    def test_foreign_write_before_owned_begin_is_not_rebased(self):
        with self.assertRaises(Conflict),shared_read_boundary(self.s):
            self.external_write();self.f.apply()
    def test_foreign_write_in_postcommit_gap_is_rejected(self):
        original=self.adapter._commit
        def commit_then_foreign():original();self.external_write()
        with self.assertRaises(Conflict),shared_read_boundary(self.s):
            with patch.object(self.adapter,'_commit',commit_then_foreign):self.f.apply()
    def test_foreign_write_after_rollback_does_not_replace_original_body_exception(self):
        meter=self.meter();phase=None
        with meter.installed(self.s):
            original=self.s.db.execute
            def rollback_then_foreign(sql,*args,**kwargs):
                result=original(sql,*args,**kwargs)
                if sql=='ROLLBACK':self.external_write()
                return result
            with self.assertRaisesRegex(ValueError,'original synthetic body'),shared_read_boundary(self.s)as phase:
                with patch.object(self.s.db,'execute',rollback_then_foreign),patch.object(self.f.service,'_apply',side_effect=ValueError('original synthetic body')):self.f.apply()
            self.assertTrue(phase.closed)

if __name__=='__main__':unittest.main()
