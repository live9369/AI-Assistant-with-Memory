"""Exact physical material sharing; all live gate/Ref code still executes."""
from copy import deepcopy
from contextlib import nullcontext
import sqlite3
import unittest
from unittest.mock import patch
from digital_life.application.learning.eligibility import ref,slot
from digital_life.application.learning.runtime import qualified_plane_required
from digital_life.domain.contracts import Conflict,ContractError,Forbidden
from digital_life.infrastructure.persistence import tool_learning_meter as meter
from digital_life.infrastructure.persistence import tool_learning_readset as readset
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
from tests import test_tool_learning_certified_input as fixture

class ExactMaterialFactsTests(unittest.TestCase):
    def setUp(self):
        self.c=fixture.CertifiedInputTests();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.s=self.c.s;self.e=self.c.e;self.storage=ToolLearningStore(self.s)
    def boundary(self):return self.e.owners.source.verification_boundary()
    def queries(self):
        calls=[];original=meter._Connection.execute
        def execute(connection,*args,**kwargs):calls.append(args[0]);return original(connection,*args,**kwargs)
        return calls,patch.object(meter._Connection,'execute',new=execute)
    def test_artifact_location_exact_rows_reduce_physical_reads_without_changing_body(self):
        key=self.s.artifact({'bounded':'material'});summaries=[]
        for shared in (False,True):
            current=self.c.meter();alternate=nullcontext()if shared else patch.object(readset,'can_share_material_facts',return_value=False)
            with current.installed(self.s),self.boundary(),alternate:
                values=[self.storage.read_artifact(key)for _ in range(8)]
            summaries.append((values,dict(current.actual)))
        self.assertEqual(summaries[0][0],summaries[1][0]);self.assertLess(summaries[1][1]['scan'],summaries[0][1]['scan'])
    def test_fresh_artifact_and_unknown_environment_use_original_sql_each_time(self):
        key=self.s.artifact({'fresh':'material'})
        for fresh,trace in ((True,False),(False,True)):
            if trace:self.s.db.set_trace_callback(lambda sql:None)
            try:
                calls,record=self.queries()
                with self.c.meter().installed(self.s),self.boundary(),record:
                    for _ in range(4):self.storage.read_artifact(key,fresh=fresh)
                self.assertEqual(sum(sql.startswith('SELECT instance_id,id,hash,size,media_type,storage_ref FROM artifacts')for sql in calls),4)
            finally:
                if trace:self.s.db.set_trace_callback(None)
    def test_snapshot_ref_event_projection_reuses_rows_but_validates_payload(self):
        token=self.e.owners.snapshots.capture(self.c.entry,self.c.principal,ref(self.s,self.c.f.activity),['id'],self.c.scope)
        known=deepcopy(token['object']);known['revision']=slot(token['revision']);summaries=[]
        for shared in (False,True):
            current=self.c.meter();alternate=nullcontext()if shared else patch.object(readset,'can_share_material_facts',return_value=False)
            calls,record=self.queries()
            with current.installed(self.s),self.boundary(),alternate,record:
                for _ in range(8):readset.clear_reference_mappings(self.s);self.assertEqual(self.storage.validate_ref(known),known)
            summaries.append((dict(current.actual),sum('SELECT e.event_type,e.payload_artifact_id,e.payload_hash' in sql for sql in calls)))
        self.assertEqual(summaries[1][1],1);self.assertEqual(summaries[0][1],8);self.assertLess(summaries[1][0]['scan'],summaries[0][0]['scan'])
    def test_snapshot_negative_event_fact_is_not_preserved_by_strong_input(self):
        original=self.s._insert_input_registration;key=('snapshot_reference_event',('f'*32,))
        def insert(fields):
            phase=readset.current_readset(self.s);self.assertEqual(list(readset.facts(self.s,'snapshot_reference_event','f'*32)),[])
            result=original(fields);self.assertNotIn(key,phase.cache);return result
        with self.c.meter().installed(self.s),self.boundary(),patch.object(self.s,'_insert_input_registration',side_effect=insert):self.c.register('/negative-snapshot-event')
    def test_owner_schema_integer_shares_but_public_gate_without_token_reads_each_time(self):
        calls,record=self.queries()
        with self.c.meter().installed(self.s),self.boundary(),record:
            for _ in range(8):self.e.owners.control()
            self.assertEqual(sum(sql=='PRAGMA user_version'for sql in calls),1)
            calls.clear()
            for _ in range(4):self.assertTrue(qualified_plane_required(self.s))
            self.assertEqual(sum(sql=='PRAGMA user_version'for sql in calls),4)
    def test_schema_header_changes_without_total_changes_never_reuse_integer(self):
        old=self.s.db.execute('PRAGMA user_version').fetchone()[0];changes=self.s.db.total_changes
        # Header changes are real phase conflicts even when total_changes stays
        # constant. The local monitor must discard the old raw integer first.
        with self.assertRaises(Conflict):
            with self.c.meter().installed(self.s),self.boundary():
                with readset.schema_material_boundary(self.s):self.assertTrue(qualified_plane_required(self.s))
                self.s.db.execute('PRAGMA user_version=5');self.assertEqual(self.s.db.total_changes,changes)
                with readset.schema_material_boundary(self.s):
                    with self.assertRaises(Forbidden):qualified_plane_required(self.s)
                self.s.db.execute('PRAGMA user_version='+str(old))
                with readset.schema_material_boundary(self.s):self.assertTrue(qualified_plane_required(self.s))
    def test_schema_observer_preserves_original_integer_rows(self):
        calls,record=self.queries();rows=[];current=self.c.meter();current.row_observer=lambda row:rows.append(dict(row))
        with current.installed(self.s),self.boundary(),record:
            with readset.schema_material_boundary(self.s):
                for _ in range(4):self.assertTrue(qualified_plane_required(self.s))
        self.assertEqual(sum(sql=='PRAGMA user_version'for sql in calls),4)
        self.assertEqual([r for r in rows if 'user_version'in r],[{'user_version':4}]*4)
    def test_schema_foreign_header_commit_in_old_read_snapshot_is_rejected(self):
        self.s.db.execute('PRAGMA journal_mode=WAL');foreign=sqlite3.connect(self.s.root/'runtime.sqlite',isolation_level=None)
        try:
            with self.assertRaises(Conflict):
                with self.c.meter().installed(self.s),self.boundary():
                    self.s.db.execute('BEGIN');self.s.db.execute('SELECT id FROM identity_instances').fetchone()
                    with readset.schema_material_boundary(self.s):self.assertTrue(qualified_plane_required(self.s))
                    foreign.execute('PRAGMA user_version=5')
                    self.e.owners.control()
        finally:
            if self.s.db.in_transaction:self.s.db.rollback()
            foreign.close()
    def test_schema_fact_rejects_arguments_and_static_version_gate_still_executes(self):
        with self.assertRaises(ContractError):list(readset.facts(self.s,'storage_schema_version','unexpected'))
        with self.c.meter().installed(self.s),self.boundary(),patch.object(self.e.owners,'check',wraps=self.e.owners.check)as check:
            for _ in range(4):
                self.e.owners.source._verified=None
                self.e.owners.source.verify_version(self.c.entry,self.c.principal,self.c.token,'exact-static-version')
            self.assertEqual(check.call_count,4)
    def test_same_value_schema_assignment_discards_fact_even_when_value_and_total_changes_match(self):
        old=self.s.db.execute('PRAGMA user_version').fetchone()[0];changes=self.s.db.total_changes
        calls,record=self.queries();observed=False
        try:
            with self.c.meter().installed(self.s),self.boundary(),record:
                with readset.schema_material_boundary(self.s):self.assertTrue(qualified_plane_required(self.s))
                phase=readset.current_readset(self.s);generation=phase.generation
                self.s.db.execute('PRAGMA user_version='+str(old))
                with readset.schema_material_boundary(self.s):self.assertTrue(qualified_plane_required(self.s))
                self.assertGreater(phase.generation,generation);self.assertEqual(self.s.db.total_changes,changes)
                self.assertEqual(sum(sql=='PRAGMA user_version'for sql in calls),2);observed=True
        except Conflict:
            # A real committed header write may also terminate the whole phase.
            self.assertTrue(observed)
    def test_rollback_of_header_change_restores_original_integer_without_old_fact_reuse(self):
        with self.c.meter().installed(self.s),self.boundary():
            with readset.schema_material_boundary(self.s):self.assertTrue(qualified_plane_required(self.s))
            with self.assertRaisesRegex(RuntimeError,'synthetic header rollback'):
                with self.s.tx():
                    self.s.db.execute('PRAGMA user_version=5')
                    with readset.schema_material_boundary(self.s):
                        with self.assertRaises(Forbidden):qualified_plane_required(self.s)
                    raise RuntimeError('synthetic header rollback')
            with readset.schema_material_boundary(self.s):self.assertTrue(qualified_plane_required(self.s))
