"""Post-failure diagnostic facts on real new stores; no model or full thought."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from evaluation.tool_learning_round2_scale import budget_snapshot,failure_registration_progress


class FailureRegistrationSnapshotTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_runtime import AssemblyGateTests
        self.f=AssemblyGateTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.activity=self.s.row('thought_requests',self.f.request['id'])['activity_id']
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)/'diagnostic'
        field=self.f.manifest['fields'][0];dependency=field['dependencies'][0]
        self.dep=self.f.runtime.eligibility.register_dependency('synthetic-runtime',self.f.principal,self.f.request,dependency,field['path'],field['dependency_scopes'][0])
        self.input=self.f.runtime.eligibility.register_input('synthetic-runtime',self.f.principal,self.f.request,self.dep,field['digest'])
        # Creation lineage at field/index is a real separate row, not assembly
        # progress for the exact manifest field path.
        self.lineage=self.f.runtime.eligibility.register_dependency('synthetic-runtime',self.f.principal,self.f.request,dependency,field['path']+'/0',field['dependency_scopes'][0])

    def test_actual_packet_manifest_and_partial_rows_without_budget_or_store_write(self):
        before=deepcopy(budget_snapshot(self.s,self.activity));changes=self.s.db.total_changes
        opportunities={'assembly:'+self.f.request['id']:{'manifest':deepcopy(self.f.manifest)}}
        result=failure_registration_progress(self.s,self.activity,self.folder,opportunities)
        self.assertEqual(self.s.db.total_changes,changes);self.assertEqual(budget_snapshot(self.s,self.activity),before)
        self.assertEqual(result['status'],'observed');item=result['requests'][0]
        self.assertFalse(item['assembly_complete']);self.assertEqual(item['packet']['status'],'observed')
        self.assertEqual(json.loads(Path(item['packet']['file']).read_bytes()),self.f.packet)
        artifact=self.s.row('artifacts',self.s.row('thought_requests',self.f.request['id'])['request_artifact_id'])
        self.assertEqual(Path(item['packet']['file']).read_bytes(),(self.s.root/'blobs'/artifact['storage_ref']).read_bytes())
        self.assertEqual(item['manifest']['origin'],'actual_owner_read_opportunity')
        self.assertEqual(json.loads(Path(item['manifest']['file']).read_text()),self.f.manifest)
        self.assertEqual(item['expected_field_count'],3);self.assertEqual(item['remaining_field_count'],2)
        self.assertEqual(item['actual_dependency_rows'],2);self.assertEqual(item['actual_input_rows'],1)
        self.assertEqual(item['missing_dependency_expectations'],2);self.assertEqual(item['missing_input_expectations'],2)
        fields=item['fields'];self.assertEqual(fields[0]['status'],'all_expected_rows_observed')
        self.assertEqual([f['status']for f in fields[1:]],['not_started','not_started'])
        self.assertEqual(fields[0]['expectations'][0]['expected'],self.f.manifest['fields'][0]['dependencies'][0])
        self.assertEqual(len(fields[0]['expectations'][0]['matching_dependency_rowids']),1)
        self.assertEqual(item['by_raw_field_path']['/task/0']['dependency_count'],1)
        self.assertEqual(item['by_raw_field_path']['/task']['input_count'],1)
        self.assertEqual([d['row']['diagnostic_rowid']for d in item['dependencies']],sorted(d['row']['diagnostic_rowid']for d in item['dependencies']))
        self.assertEqual(item['dependencies'][0]['metadata']['dependency']['expected'],self.f.manifest['fields'][0]['dependencies'][0]['expected'])

    def test_missing_manifest_is_unknown_and_does_not_invent_expected_fields(self):
        before=budget_snapshot(self.s,self.activity);changes=self.s.db.total_changes
        result=failure_registration_progress(self.s,self.activity,self.folder)
        self.assertEqual(self.s.db.total_changes,changes);self.assertEqual(budget_snapshot(self.s,self.activity),before)
        item=result['requests'][0];self.assertEqual(item['packet']['status'],'observed')
        self.assertEqual(item['manifest']['status'],'unknown');self.assertIsNone(item['fields'])
        self.assertIsNone(item['expected_field_count']);self.assertIsNone(item['remaining_field_count'])
        self.assertEqual(item['actual_dependency_rows'],2);self.assertEqual(item['actual_input_rows'],1)
        self.assertFalse(item['assembly_complete']);self.assertFalse((self.folder/'request-0/manifest.json').exists())

    def test_actual_persisted_manifest_is_observed_without_owner_memory(self):
        self.f.assemble();before=budget_snapshot(self.s,self.activity);changes=self.s.db.total_changes
        result=failure_registration_progress(self.s,self.activity,self.folder)
        self.assertEqual(self.s.db.total_changes,changes);self.assertEqual(budget_snapshot(self.s,self.activity),before)
        item=result['requests'][0];self.assertEqual(item['manifest']['origin'],'persisted_assembly_event')
        self.assertTrue(item['assembly_complete']);self.assertEqual(item['remaining_field_count'],0)
        self.assertEqual(item['actual_input_rows'],3)

    def test_active_meter_is_not_used_for_post_failure_diagnostics(self):
        from digital_life.infrastructure.persistence.tool_learning_meter import _ACTIVE
        changes=self.s.db.total_changes;token=_ACTIVE.set(object())
        try:result=failure_registration_progress(self.s,self.activity,self.folder)
        finally:_ACTIVE.reset(token)
        self.assertEqual(result['status'],'unknown');self.assertIn('still active',result['reason'])
        self.assertFalse(self.folder.exists());self.assertEqual(self.s.db.total_changes,changes)
