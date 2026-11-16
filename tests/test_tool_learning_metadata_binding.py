"""Negative candidate ports only; product remains unchanged."""
from copy import deepcopy
import sqlite3
import unittest
from unittest.mock import patch
from digital_life.application.learning import eligibility as eligibility
from digital_life.application.learning.eligibility import ref,slot
from digital_life.application.learning.engine import _dependency
from digital_life.domain.contracts import Conflict,ContractError
from digital_life.infrastructure.persistence.tool_learning_readset import current_readset
from tests import test_tool_learning_certified_input as fixture

class MetadataBindingTests(unittest.TestCase):
    def setUp(self):
        self.c=fixture.CertifiedInputTests();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.s=self.c.s;self.e=self.c.e
        self.key=self.e.runtime.eligibility.register_dependency(self.c.entry,self.c.principal,self.c.consumer,self.c.dep,'/binding',self.c.scope)
        self.row=self.s.row('tl_dependency',self.key)
    def boundary(self):return self.e.owners.source.verification_boundary()
    def test_caller_mutation_cannot_pollute_bound_metadata(self):
        with self.c.meter().installed(self.s),self.boundary():
            first=self.e.runtime.eligibility._metadata(self.row);expected=deepcopy(first);first['field_path']='changed'
            self.assertEqual(self.e.runtime.eligibility._metadata(self.row),expected)
    def test_replaced_validator_is_executed_and_can_reject(self):
        with self.c.meter().installed(self.s),self.boundary():
            self.e.runtime.eligibility._metadata(self.row)
            with patch.object(self.e.runtime.eligibility.artifacts,'validate_ref',side_effect=ContractError('unknown validator must run'))as validate:
                with self.assertRaisesRegex(ContractError,'unknown validator'):self.e.runtime.eligibility._metadata(self.row)
                self.assertEqual(validate.call_count,1)
    def test_registry_kind_write_cannot_reuse_binding(self):
        with self.c.meter().installed(self.s),self.boundary():
            self.e.runtime.eligibility._metadata(self.row)
            with self.s.tx():
                self.s.db.execute('DROP TRIGGER immutable_object_registry')
                self.s.db.execute("UPDATE object_registry SET kind='evidence_items' WHERE id=?",(self.c.token['object']['id'],))
            with self.assertRaises(ContractError):self.e.runtime.eligibility._metadata(self.row)
    def test_failed_validation_never_prepares_binding(self):
        broken=dict(self.row);broken['source_revision_id']='f'*32
        with self.c.meter().installed(self.s),self.boundary():
            phase=current_readset(self.s);prior=dict(phase.prepared)
            with self.assertRaises(ContractError):self.e.runtime.eligibility._metadata(broken)
            self.assertEqual(phase.prepared,prior)
    def test_metadata_blob_unchanged_but_known_ref_snapshot_blob_change_is_rejected(self):
        token=self.e.owners.snapshots.capture(self.c.entry,self.c.principal,ref(self.s,self.c.f.activity),['id'],self.c.scope)
        token=deepcopy(token);token['object']['revision']=slot(token['revision'])
        with self.s.tx():_dependency(self.s,self.c.consumer,token,self.c.scope,'read','/snapshot-binding','learn')
        row=self.s.db.execute("SELECT * FROM tl_dependency WHERE consumer_ref_id=? AND field_path='/snapshot-binding'",(self.c.consumer['id'],)).fetchone()
        event=self.s.db.execute('SELECT e.payload_artifact_id FROM object_revision_registry r JOIN runtime_events e ON e.id=r.id WHERE r.object_id=? AND r.revision_no=?',(token['object']['id'],token['revision'])).fetchone()
        artifact=self.s.row('artifacts',event[0]);path=self.s.root/'blobs'/artifact['storage_ref'];prior=path.read_bytes()
        try:
            with self.assertRaises(Conflict):
                with self.c.meter().installed(self.s),self.boundary():
                    self.e.runtime.eligibility._metadata(row)
                    self.assertIn(path,current_readset(self.s).blobs)
                    path.write_bytes(prior+b' ')
                    self.e.runtime.eligibility._metadata(row)
        finally:path.write_bytes(prior)

    def test_unknown_validator_cannot_seed_trusted_binding_after_restore(self):
        from digital_life.infrastructure.persistence import tool_learning_meter as meter
        with self.c.meter().installed(self.s),self.boundary():
            with patch.object(self.e.runtime.eligibility.artifacts,'validate_ref',side_effect=lambda value:value):
                self.e.runtime.eligibility._metadata(self.row)
            phase=current_readset(self.s)
            self.assertFalse(any(key[0]=='TL-DEPENDENCY-BINDING-1'for key in phase.prepared))
            with patch.object(meter,'reference_cache_key',wraps=meter.reference_cache_key)as reference:
                first=self.e.runtime.eligibility._metadata(self.row)
                self.assertGreaterEqual(reference.call_count,2)
            self.assertTrue(any(key[0]=='TL-DEPENDENCY-BINDING-1'for key in phase.prepared))
            with patch.object(meter,'reference_cache_key',wraps=meter.reference_cache_key)as reference:
                self.assertEqual(self.e.runtime.eligibility._metadata(self.row),first)
                self.assertEqual(reference.call_count,0)
    def test_no_actual_meter_cannot_create_trusted_binding(self):
        with self.boundary():
            self.e.runtime.eligibility._metadata(self.row)
            phase=current_readset(self.s)
            self.assertFalse(any(key[0]=='TL-DEPENDENCY-BINDING-1'for key in phase.prepared))
    def test_class_validator_replacement_does_not_match_stable_original(self):
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        with self.c.meter().installed(self.s),self.boundary():
            self.e.runtime.eligibility._metadata(self.row)
            with patch.object(ToolLearningStore,'validate_ref',side_effect=ContractError('class replacement must run')):
                with self.assertRaisesRegex(ContractError,'class replacement'):self.e.runtime.eligibility._metadata(self.row)
    def test_unknown_read_environment_does_not_create_binding(self):
        # Installing trace does not replace the original validator. It must
        # still use the complete original metadata binding checks each time.
        from digital_life.infrastructure.persistence import tool_learning_meter as meter
        trace=[];self.s.db.set_trace_callback(trace.append)
        try:
            with self.c.meter().installed(self.s),self.boundary():
                self.e.runtime.eligibility._metadata(self.row)
                self.assertFalse(any(key[0]=='TL-DEPENDENCY-BINDING-1'for key in current_readset(self.s).prepared))
                with patch.object(meter,'reference_cache_key',wraps=meter.reference_cache_key)as reference:
                    self.e.runtime.eligibility._metadata(self.row)
                    self.assertGreaterEqual(reference.call_count,2)
        finally:self.s.db.set_trace_callback(None)
    def test_unknown_read_environment_cannot_consume_previous_binding(self):
        from digital_life.infrastructure.persistence import tool_learning_meter as meter
        with self.c.meter().installed(self.s),self.boundary():
            self.e.runtime.eligibility._metadata(self.row)
            phase=current_readset(self.s);self.assertTrue(any(key[0]=='TL-DEPENDENCY-BINDING-1'for key in phase.prepared))
            self.s.db.set_trace_callback(lambda sql:None)
            try:
                with patch.object(meter,'reference_cache_key',wraps=meter.reference_cache_key)as reference:
                    self.e.runtime.eligibility._metadata(self.row)
                    self.assertGreaterEqual(reference.call_count,2)
                self.assertFalse(any(key[0]=='TL-DEPENDENCY-BINDING-1'for key in phase.prepared))
            finally:self.s.db.set_trace_callback(None)
