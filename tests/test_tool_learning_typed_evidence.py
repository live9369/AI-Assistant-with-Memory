"""Real PeopleRelations/Memory source lineage through typed Evidence FKs."""
import tempfile
import unittest
from unittest.mock import patch
from digital_life.application.learning.engine import source_scope
from digital_life.application.learning.eligibility import ref
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier

class TypedEvidenceSnapshotTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_runtime import StrictEngineEndToEndTests
        from evaluation.tool_learning_round2_scale import seed_shared_source
        fixture=StrictEngineEndToEndTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.f=fixture;self.s=fixture.s;self.strict=fixture.strict
        self.seed=seed_shared_source(fixture);self.scope=source_scope(self.s)
        self.context=self.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(fixture.activity,)).fetchone()[0]
        self.entry,self.principal=self.strict.owners.entry('M14','learn',self.strict._recipient(fixture.activity))
        self.task,self.primary=self.strict._primary(self.entry,self.principal,fixture.activity,self.context,self.scope)
        self.change=self.s.db.execute('SELECT * FROM social_relationship_changes WHERE instance_id=? AND reason_ref=?',(self.s.instance_id,self.seed['first_evidence'])).fetchone()
        self.assertIsNotNone(self.change)
    def dependencies(self):
        # Omit reason_ref from the projection; actual typed lineage still counts.
        snapshot={'origin':ref(self.s,self.change['id']),'selector':['id'],'scope':self.scope}
        return self.strict.owners.snapshot_authority.dependencies(self.entry,self.principal,snapshot)
    def corrupt_change_reason(self,key):
        self.s.db.execute('PRAGMA foreign_keys=OFF')
        self.s.db.execute('UPDATE social_relationship_changes SET reason_ref=? WHERE id=?',(key,self.change['id']))
    def test_real_relationship_features_keep_same_actual_memory_source(self):
        with patch.object(self.strict,'FEATURE_TABLES',{'relationships':self.strict.FEATURE_TABLES['relationships']}),patch.object(self.strict.provider,'generate_fresh',side_effect=AssertionError('feature collection must not invoke model')):
            features,fields=self.strict._features(self.entry,self.principal,self.f.activity,self.context,self.scope,self.task,self.primary)
        self.assertTrue(fields);self.assertTrue(self.seed['first_input_memories'])
        record=next(row for row in features['relationships']['records']if row['source']['id']==self.change['id'])
        token={'object':record['source'],'revision':record['observed_version'],'epoch':0}
        paths=self.strict.runtime.eligibility._upstream(token,self.scope,{'remaining':16384})
        self.assertIn(self.seed['first_signal'],{row[0]for row in paths})
        self.assertEqual(self.change['reason_ref'],self.seed['first_input_memories'][0]['evidence_id'])
        self.assertNotIn(self.seed['first_evidence'],{row[0]for row in paths})
    def test_typed_source_evidence_is_kept_even_when_not_selected(self):
        dependencies=self.dependencies()
        self.assertIn(self.seed['first_signal'],{row['dependency']['target']['id']for row in dependencies})
        self.assertNotIn(self.seed['first_evidence'],{row['dependency']['target']['id']for row in dependencies})
    def test_nullable_typed_evidence_fk_without_reference_is_skipped(self):
        from digital_life.domain.contracts import utc
        with self.s.tx():key=self.s.insert('commitment_conflicts',state='open',resolution_ref=None,detected_at=utc())
        snapshot={'origin':ref(self.s,key),'selector':['id'],'scope':self.scope}
        with patch.object(self.strict.owners.snapshot_authority,'_evidence_source',side_effect=AssertionError('NULL must not resolve a source')):
            self.assertEqual(self.strict.owners.snapshot_authority.dependencies(self.entry,self.principal,snapshot),[])
    def test_wrong_registry_kind_is_rejected(self):
        self.corrupt_change_reason(self.s.config()['controller'])
        with self.assertRaises((ContractError,Conflict,Forbidden)):self.dependencies()
    def test_missing_typed_evidence_is_rejected(self):
        self.corrupt_change_reason(identifier())
        with self.assertRaises((ContractError,Conflict,Forbidden)):self.dependencies()
    def test_evidence_from_another_fresh_instance_is_rejected(self):
        from digital_life.infrastructure.persistence.sqlite_store import Store
        with tempfile.TemporaryDirectory()as folder:
            other=Store.prepare(folder);self.addCleanup(other.close)
            artifact=other.artifact({'foreign synthetic evidence':True});evidence=other.evidence(artifact=artifact)
            self.corrupt_change_reason(evidence)
            with self.assertRaises((ContractError,Conflict,Forbidden)):self.dependencies()
    def test_evidence_registry_without_actual_evidence_row_is_rejected(self):
        self.s.db.execute('PRAGMA foreign_keys=OFF')
        self.s.db.execute('DELETE FROM evidence_items WHERE id=?',(self.seed['first_evidence'],))
        with self.assertRaises((ContractError,Conflict,Forbidden)):self.dependencies()
    def test_evidence_revision_owned_by_other_origin_is_rejected(self):
        revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id<>? LIMIT 1',(self.s.instance_id,self.seed['first_signal'])).fetchone()[0]
        # Normal writes are already rejected by this existing guard; bypass
        # only inside the disposable corruption-injection fixture.
        self.s.db.execute('DROP TRIGGER evidence_owner_update')
        self.s.db.execute('UPDATE evidence_items SET origin_revision_id=? WHERE id=?',(revision,self.seed['first_evidence']))
        with self.assertRaisesRegex((ContractError,Conflict,Forbidden),'revision.*owner'):self.dependencies()
    def test_evidence_artifact_wrong_kind_is_rejected(self):
        self.s.db.execute('PRAGMA foreign_keys=OFF')
        self.s.db.execute('UPDATE evidence_items SET artifact_id=? WHERE id=?',(self.s.config()['controller'],self.seed['first_evidence']))
        with self.assertRaises((ContractError,Conflict,Forbidden)):self.dependencies()

if __name__=='__main__':unittest.main()
