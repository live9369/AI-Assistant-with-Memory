"""Complete local source facts share bytes, never permissions or ACL verdicts."""
from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from digital_life.application.learning.eligibility import ref
from digital_life.application.learning.engine import source_scope
from digital_life.application.services import Memory
from digital_life.domain.contracts import ContractError,Conflict,Forbidden
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
from digital_life.infrastructure.persistence.tool_learning_readset import OWNER_SOURCE_ROW_QUERIES,owner_source_row,current_readset
from tests import test_tool_learning_runtime as fixture


class OwnerSourceRowTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.StrictEngineEndToEndTests();self.f.enable_features=False;self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.e=self.f.strict;self.o=self.e.owners;self.scope=source_scope(self.s)
        self.entry,self.principal=self.o.entry('M14','learn')
        self.config=self.s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()[0]
        self.origin=ref(self.s,self.config);self.memory=self.f.base.f.expected['memory_id']
    def meter(self):return PhysicalReadMeter(self.e._read_slice(self.f.activity,.5),self.s.row('activities',self.f.activity)['deadline'])
    def access(self,origin=None):return self.o.source_access(self.entry,self.principal,self.origin if origin is None else origin,self.scope)
    def boundary(self):return self.o.source.verification_boundary()
    def test_complete_rows_repeat_permissions_but_reduce_actual_bytes_and_rows(self):
        summaries=[]
        for shared in (False,True):
            meter=self.meter();sql=[];self.s.db.set_trace_callback(sql.append)
            fallback=lambda kind,key:self.s.row(kind,key)
            with meter.installed(self.s),self.boundary(),patch.object(self.o,'_source_row',wraps=self.o._source_row)if shared else patch.object(self.o,'_source_row',side_effect=fallback):
                with patch.object(self.o,'check',wraps=self.o.check)as checks:
                    rows=[self.access()for _ in range(4)]
                    self.assertEqual(checks.call_count,4)
            self.s.db.set_trace_callback(None)
            summaries.append({'rows':rows,'actual':dict(meter.actual),'source_queries':[q for q in sql if q.startswith('SELECT * FROM configuration_versions WHERE id=')]})
        before,after=summaries;self.assertEqual(before['rows'],after['rows'])
        self.assertEqual(len(before['source_queries']),4);self.assertEqual(len(after['source_queries']),1)
        self.assertEqual(after['rows'][0],self.s.row('configuration_versions',self.config))
        self.assertLess(after['actual']['bytes'],before['actual']['bytes']);self.assertLess(after['actual']['scan'],before['actual']['scan'])
        capture=__import__('os').environ.get('DIGITAL_LIFE_CAPTURE_OWNER_ROW_DIFF')
        if capture:
            out=Path(capture);out.mkdir(parents=True,exist_ok=False)
            (out/'result.json').write_text(json.dumps({'passed':True,'summaries':summaries,'real_models_called':False,'formal_instance_accessed':False},indent=2)+'\n')
    def test_returned_dictionary_mutation_does_not_poison_complete_cached_row(self):
        with self.meter().installed(self.s),self.boundary():
            first=self.access();expected=dict(first);first['compatibility']='caller mutation';first['extra']='not a database column'
            second=self.access();self.assertEqual(second,expected);self.assertIsNot(first,second)
    def test_unknown_observer_sees_identical_complete_rows_and_sequence(self):
        results=[]
        for shared in (False,True):
            seen=[];meter=self.meter();fallback=lambda kind,key:self.s.row(kind,key)
            with meter.installed(self.s),self.boundary(),patch.object(self.o,'_source_row',wraps=self.o._source_row)if shared else patch.object(self.o,'_source_row',side_effect=fallback):
                meter.row_observer=lambda row:seen.append(dict(row))
                rows=[self.access()for _ in range(3)]
            results.append((rows,seen))
        self.assertEqual(results[0],results[1]);complete=[v for v in results[1][1]if v.get('id')==self.config and 'compatibility'in v]
        self.assertEqual(len(complete),3);self.assertEqual(set(complete[0]),set(self.s.columns['configuration_versions']))
    def test_reentrant_observer_write_is_refreshed_on_next_access(self):
        with self.meter().installed(self.s)as meter,self.boundary():
            before=self.access();changed=[]
            def observer(row):
                value=dict(row)
                if not changed and value.get('id')==self.config and 'compatibility'in value:
                    changed.append(True);self.s.db.execute('UPDATE configuration_versions SET compatibility=? WHERE id=?',(json.dumps('synthetic observer mutation'),self.config))
            meter.row_observer=observer
            self.assertEqual(self.access(),before);self.assertEqual(changed,[True])
            self.assertEqual(self.access()['compatibility'],json.dumps('synthetic observer mutation'))
    def test_memory_state_and_acl_are_checked_on_every_use(self):
        origin=ref(self.s,self.memory);readers=Memory.readers
        with self.meter().installed(self.s),self.boundary(),patch.object(Memory,'readers',autospec=True,side_effect=readers)as calls:
            self.access(origin);self.access(origin);self.assertEqual(calls.call_count,2)
            self.s.db.execute("UPDATE memory_items SET state='archived' WHERE id=?",(self.memory,))
            with self.assertRaisesRegex(Forbidden,'retention'):self.access(origin)
    def test_memory_policy_restriction_cannot_use_old_authorization(self):
        origin=ref(self.s,self.memory)
        with self.meter().installed(self.s),self.boundary():
            self.access(origin);Memory(self.s).restrict(self.memory,[self.s.config()['controller']],self.s.config()['controller'])
            with self.assertRaisesRegex(Forbidden,'ACL'):self.access(origin)
    def test_same_connection_source_update_and_rollback_refresh_complete_row(self):
        with self.meter().installed(self.s),self.boundary():
            before=self.access()
            with self.assertRaisesRegex(RuntimeError,'rollback'):
                with self.s.tx():
                    self.s.db.execute('UPDATE configuration_versions SET compatibility=? WHERE id=?',(json.dumps('temporary'),self.config))
                    self.assertEqual(self.access()['compatibility'],json.dumps('temporary'));raise RuntimeError('rollback')
            self.assertEqual(self.access(),before)
    def test_foreign_source_update_rejected_even_inside_old_read_transaction(self):
        self.s.db.execute('PRAGMA journal_mode=WAL')
        with self.assertRaises(Conflict):
            with self.meter().installed(self.s),self.boundary():
                self.s.db.execute('BEGIN')
                try:
                    self.access();other=sqlite3.connect(self.s.root/'runtime.sqlite')
                    try:other.execute('UPDATE configuration_versions SET compatibility=? WHERE id=?',(json.dumps('foreign'),self.config));other.commit()
                    finally:other.close()
                    self.access()
                finally:
                    if self.s.db.in_transaction:self.s.db.execute('ROLLBACK')
    def test_stop_and_configuration_file_change_block_before_cached_source_use(self):
        with self.assertRaises((Conflict,Forbidden)):
            with self.meter().installed(self.s),self.boundary():self.access();self.f.control.stop('synthetic source cache stop');self.access()
        self.f.control.resume('synthetic source cache resume')
        cfg=self.s.row('configuration_versions',self.config);artifact=self.s.row('artifacts',cfg['artifact_ref']);path=self.s.root/'blobs'/artifact['storage_ref'];prior=path.read_bytes()
        try:
            with self.assertRaises((Conflict,Forbidden)):
                with self.meter().installed(self.s),self.boundary():self.access();path.write_bytes(prior+b' ');self.access()
        finally:path.write_bytes(prior)
    def test_fixed_query_catalog_filters_id_and_current_instance(self):
        foreign=deepcopy(self.origin);foreign['id']='f'*32
        for shared in (False,True):
            fallback=lambda kind,key:self.s.row(kind,key)
            with self.meter().installed(self.s),self.boundary(),patch.object(self.o,'_source_row',wraps=self.o._source_row)if shared else patch.object(self.o,'_source_row',side_effect=fallback):
                with self.assertRaisesRegex(ContractError,'object not found in instance: configuration_versions'):self.access(foreign)
        with self.assertRaises(ContractError):owner_source_row(self.s,'configuration_versions WHERE 1=1--',self.config)
        from digital_life.application.learning.runtime_owners import LocalRuntimeOwners
        expected=LocalRuntimeOwners.NATIVE|LocalRuntimeOwners.STATIC|__import__('digital_life.domain.tool_learning_sources',fromlist=['SNAPSHOT_KINDS']).SNAPSHOT_KINDS|{'memory_items','cognition_beliefs','cognition_concepts','tl_content','tl_representation_head'}
        self.assertEqual(set(OWNER_SOURCE_ROW_QUERIES),expected)
    def test_no_phase_does_not_retain_source_rows(self):
        sql=[];self.s.db.set_trace_callback(sql.append)
        self.access();self.access();self.assertIsNone(current_readset(self.s))
        self.assertEqual(sum(q.startswith('SELECT * FROM configuration_versions WHERE id=')for q in sql),2)


if __name__=='__main__':unittest.main()
