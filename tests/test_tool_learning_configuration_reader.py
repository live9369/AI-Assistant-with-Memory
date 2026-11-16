"""Configuration uses its initialized safe reader, not repeated DDL discovery."""
import unittest
from unittest.mock import patch
from digital_life.application.learning.engine import source_scope
from digital_life.application.learning.eligibility import ref
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc
from digital_life.domain.tool_learning_resources import DIMENSIONS
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter

class ConfigurationReaderReuseTests(unittest.TestCase):
    def setUp(self):
        from tests import test_tool_learning_control_materials as material_fixture
        fixture=material_fixture.ControlMaterialSharingTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.fixture=fixture;self.f=fixture.f;self.s=fixture.s;self.owner=fixture.owner
        self.entry=fixture.entry;self.principal=fixture.principal
    def test_ten_outside_phase_calls_do_not_repeat_schema_scan_and_meter_all_actual_rows(self):
        statements=[];self.s.db.set_trace_callback(statements.append)
        meter=PhysicalReadMeter({k:1000000 for k in DIMENSIONS},utc(30))
        with meter.installed(self.s):
            for _ in range(10):
                value=self.owner.configuration();self.assertEqual(value['self_actor'],self.s.config()['self_actor'])
            # Each owner call reads latest config, complete artifact identity,
            # and the actual artifact metadata. Store.config verification above
            # itself also reads config+artifact; none is hidden or truncated.
            self.assertGreaterEqual(meter.actual['scan'],30)
            self.assertLess(meter.actual['scan'],100)
            self.assertGreater(meter.actual['bytes'],0)
        self.assertFalse([sql for sql in statements if sql.upper().startswith('PRAGMA TABLE_INFO')])
    def test_fresh_raw_blob_tamper_still_fails_with_reused_reader(self):
        self.owner.configuration();row=self.s.row('artifacts',self.fixture.cfgrow()['artifact_ref'])
        path=self.s.root/'blobs'/row['storage_ref'];raw=path.read_bytes();path.write_bytes(b'x'*len(raw))
        with self.assertRaises((ContractError,Conflict)):self.owner.configuration()
    def test_same_meter_without_phase_still_fresh_hashes_configuration_bytes(self):
        row=self.s.row('artifacts',self.fixture.cfgrow()['artifact_ref']);path=self.s.root/'blobs'/row['storage_ref']
        meter=PhysicalReadMeter({k:1000000 for k in DIMENSIONS},utc(30))
        with meter.installed(self.s):
            self.owner.configuration();first=meter.actual['bytes'];self.owner.configuration()
            self.assertGreaterEqual(meter.actual['bytes']-first,row['size'])
            raw=path.read_bytes();path.write_bytes(b'x'*len(raw))
            with self.assertRaises((Conflict,ContractError)):self.owner.configuration()
    def test_new_unreviewed_ddl_source_still_has_no_owner_permission(self):
        key=identifier();self.s.db.execute('CREATE TABLE unreviewed_source(id TEXT,instance_id TEXT,secret TEXT)')
        self.s.db.execute('INSERT INTO object_registry(id,instance_id,kind)VALUES(?,?,?)',(key,self.s.instance_id,'unreviewed_source'))
        self.s.db.execute('INSERT INTO unreviewed_source VALUES(?,?,?)',(key,self.s.instance_id,'synthetic unreviewed material'))
        self.s.columns['unreviewed_source']={'id','instance_id','secret'}
        with self.assertRaises((ContractError,Conflict,Forbidden)):
            self.owner.source_access(self.entry,self.principal,ref(self.s,key),source_scope(self.s))
    def test_actual_calculated_contexts_entry_does_not_reinitialize_configuration_reader(self):
        from digital_life.application.runtime.engine import Engine
        Engine(self.s,self.f.identity).transition(self.f.activity,'running','synthetic calculated-contexts regression')
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(self.f.activity,)).fetchone()[0]
        statements=[];configuration_statements=[];inside=[False];original=self.owner.configuration
        def observed_configuration():
            previous=inside[0];inside[0]=True
            try:return original()
            finally:inside[0]=previous
        def observe_sql(sql):
            statements.append(sql)
            if inside[0]:configuration_statements.append(sql)
        self.s.db.set_trace_callback(observe_sql)
        with patch.object(self.owner,'configuration',observed_configuration),patch.object(self.f.strict.provider,'generate_fresh',side_effect=AssertionError('context calculation must not invoke model')):
            calculated,live,fields=self.f.strict._contexts(self.entry,self.principal,self.f.activity,context,'你好，我是liwei',{'items':[]},[],source_scope(self.s))
        self.assertIn('personality',calculated);self.assertTrue(fields)
        self.assertFalse([sql for sql in configuration_statements if sql.upper().startswith('PRAGMA TABLE_INFO')])
        # One pre-existing GoalRegulation->ActivityResourceBudget creation still
        # validates its DDL; it is independent of repeated configuration reads.
        from digital_life.infrastructure.persistence.tool_learning_store import OWNERS
        self.assertEqual(sum(sql.upper().startswith('PRAGMA TABLE_INFO')for sql in statements),2*(len(OWNERS)+1))
        self.assertTrue(self.s.db.execute("SELECT id FROM memory_retrieval_runs WHERE activity_id=? AND query='bounded strict runtime material calculated-contexts'",(self.f.activity,)).fetchone())

    def test_default_calculated_contexts_real_entry_has_zero_table_info_queries(self):
        from tests.test_tool_learning_runtime import StrictEngineEndToEndTests
        from digital_life.application.runtime.engine import Engine
        fixture=StrictEngineEndToEndTests();fixture.enable_features=False;fixture.setUp();self.addCleanup(fixture.doCleanups)
        store=fixture.s;engine=fixture.strict
        entry,principal=engine.owners.entry('M14','learn',engine._recipient(fixture.activity))
        Engine(store,fixture.identity).transition(fixture.activity,'running','synthetic default-context regression')
        context=store.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(fixture.activity,)).fetchone()[0]
        statements=[];store.db.set_trace_callback(statements.append)
        with patch.object(engine.provider,'generate_fresh',side_effect=AssertionError('default contexts do not invoke model')):
            calculated,live,fields=engine._contexts(entry,principal,fixture.activity,context,'synthetic default task',{'items':[]},[],source_scope(store))
        self.assertIn('personality',calculated);self.assertTrue(fields)
        self.assertEqual(sum(sql.upper().startswith('PRAGMA TABLE_INFO')for sql in statements),0)

if __name__=='__main__':unittest.main()
