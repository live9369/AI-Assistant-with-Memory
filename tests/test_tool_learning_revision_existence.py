"""Exact revision existence facts never become owner or permission verdicts."""
import copy
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from digital_life.application.learning.engine import source_scope
from digital_life.application.learning.eligibility import ref,slot
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier
from digital_life.infrastructure.persistence.tool_learning_readset import facts,shared_read_boundary,checkpoint,QUERIES
from digital_life.infrastructure.persistence.tool_learning_store import has_registered_revision

def old_presence(store,key):
    return store.db.execute('SELECT 1 FROM object_revision_registry WHERE instance_id=? AND object_id=? UNION ALL SELECT 1 FROM object_revision_registry WHERE instance_id=? AND id=? LIMIT 1',(store.instance_id,key,store.instance_id,key)).fetchone()is not None

class RevisionExistenceSharingTests(unittest.TestCase):
    def setUp(self):
        from tests import test_tool_learning_control_materials as control_fixture
        fixture=control_fixture.ControlMaterialSharingTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.f=fixture.f;self.s=fixture.s;self.owner=fixture.owner;self.entry=fixture.entry;self.principal=fixture.principal
        self.scope=source_scope(self.s);self.origin=ref(self.s,self.s.rows('personality_trait_values')[0]['id'])
        self.token=self.owner.snapshots.capture(self.entry,self.principal,self.origin,['central_value'],self.scope)
        self.revision=self.s.db.execute('SELECT * FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.s.instance_id,self.origin['id'],self.token['revision'])).fetchone()
    def test_same_database_old_union_truth_table_and_exact_index_plans(self):
        objects=[self.origin['id'],self.revision['id'],self.s.config()['controller'],'f'*32]
        for active in (False,True):
            from contextlib import nullcontext
            with shared_read_boundary(self.s)if active else nullcontext():
                for key in objects:self.assertEqual(has_registered_revision(self.s,key),old_presence(self.s,key))
                other=SimpleNamespace(db=self.s.db,instance_id='other-instance')
                for key in objects:self.assertFalse(has_registered_revision(other,key))
        plan=[row[3]for row in self.s.db.execute('EXPLAIN QUERY PLAN '+QUERIES['registered_revision_presence'],(self.s.instance_id,self.origin['id'],self.s.instance_id,self.origin['id']))]
        self.assertTrue(any('object_id=?'in row and 'SEARCH'in row for row in plan))
        self.assertTrue(any('AND id=?'in row and 'SEARCH'in row for row in plan))
    def test_presence_repeated_reads_are_one_physical_query_per_phase(self):
        sql=[];self.s.db.set_trace_callback(sql.append)
        with shared_read_boundary(self.s):
            for _ in range(10):self.assertTrue(has_registered_revision(self.s,self.origin['id']))
        self.assertEqual(sum('UNION ALL SELECT 1 FROM object_revision_registry'in row for row in sql),1)
        has_registered_revision(self.s,self.origin['id'])
        self.assertEqual(sum('UNION ALL SELECT 1 FROM object_revision_registry'in row for row in sql),2)
    def test_presence_query_rejects_caller_supplied_tail_instance(self):
        for parameters in ((),(self.origin['id'],'foreign-instance'),(self.origin['id'],self.s.instance_id,self.origin['id'])):
            with self.assertRaises(ContractError):list(facts(self.s,'registered_revision_presence',*parameters))
        with shared_read_boundary(self.s):
            with self.assertRaises(ContractError):list(facts(self.s,'registered_revision_presence',self.origin['id'],'foreign-instance'))
    def test_absence_after_real_same_connection_added_revision_becomes_present(self):
        key=self.s.artifact({'synthetic new owner':True})
        with shared_read_boundary(self.s):
            self.assertFalse(has_registered_revision(self.s,key))
            with self.s.tx():self.s.db.execute('INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind)VALUES(?,?,?,?,?)',(identifier(),self.s.instance_id,key,0,'artifacts'))
            self.assertTrue(has_registered_revision(self.s,key))
    def test_version_owner_and_upstream_use_the_same_snapshot_existence_fact(self):
        sql=[];self.s.db.set_trace_callback(sql.append)
        with self.owner.source.verification_boundary(),patch.object(self.owner,'check',wraps=self.owner.check)as check:
            self.owner.source.verify_version(self.entry,self.principal,self.token,'first-use')
            self.owner.source.verify_version(self.entry,self.principal,self.token,'second-use')
            self.assertGreaterEqual(check.call_count,2)
            self.owner.eligibility._upstream(self.token,self.scope,{'remaining':16384})
        matching=[row for row in sql if row.startswith('SELECT 1 FROM object_revision_registry WHERE instance_id=')and "kind='runtime_events'"in row]
        self.assertEqual(len(matching),1)
    def test_version_id_rows_are_preserved_for_observers_and_shared_only_in_trusted_busy_scope(self):
        from digital_life.application.learning.contexts import DomainReadCollector
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
        from digital_life.application.learning.contexts import source_preparation_observer_boundary
        from digital_life.domain.tool_learning_resources import DIMENSIONS
        from digital_life.domain.contracts import utc
        meter=PhysicalReadMeter({k:10000000 for k in DIMENSIONS},utc(60));observed=[];sql=[];self.s.db.set_trace_callback(sql.append)
        with meter.installed(self.s),self.owner.source.verification_boundary():
            list(facts(self.s,'snapshot_bridge',self.origin['id'],self.token['revision']))
            meter.row_observer=lambda row:observed.append(dict(row))
            self.owner.source.verify_version(self.entry,self.principal,self.token,'observable-id')
            self.assertIn({'id':self.revision['id']},observed)
            count=sum(statement.startswith('SELECT id FROM object_revision_registry')and "kind='runtime_events'"in statement for statement in sql)
            collector=DomainReadCollector(self.f.strict,self.entry,self.principal,self.scope,set());collector.busy=True;meter.row_observer=collector.on_row
            with source_preparation_observer_boundary(collector):
                self.owner.source.verify_version(self.entry,self.principal,self.token,'trusted-busy')
            self.assertEqual(sum(statement.startswith('SELECT id FROM object_revision_registry')and "kind='runtime_events'"in statement for statement in sql),count)
    def test_presence_does_not_allow_wrong_ref_revision_scope_or_principal(self):
        self.assertTrue(has_registered_revision(self.s,self.origin['id']))
        with self.owner.source.verification_boundary():
            wrong=copy.deepcopy(self.origin);wrong['kind']='artifacts'
            with self.assertRaises(ContractError):self.owner.eligibility.artifacts.validate_ref(wrong)
            wrong_token=copy.deepcopy(self.token);wrong_token['revision']+=100
            with self.assertRaises(Conflict):self.owner.source.verify_version(self.entry,self.principal,wrong_token,'wrong-revision')
            wrong_scope=copy.deepcopy(self.scope);wrong_scope['coverage']['scanned']=True
            with self.assertRaises(ContractError):self.owner.eligibility.check(self.entry,self.principal,self.token,wrong_scope,'learn',self.principal['recipient'])
            wrong_principal=copy.deepcopy(self.principal);wrong_principal['purpose']='represent'
            with self.assertRaises(Forbidden):self.owner.check(self.entry,wrong_principal)
    def test_actual_dependency_registration_reuses_existence_material_without_skipping_checks(self):
        consumer=ref(self.s,self.s.artifact({'real synthetic registration consumer':True}))
        dependency={'target':copy.deepcopy(self.origin),'relation':'read','expected':copy.deepcopy(self.token),'consumer_purpose':'learn'}
        service=self.owner.eligibility
        expected=service.register_dependency(self.entry,self.principal,consumer,dependency,'/same-source',self.scope)
        counts=[]
        from contextlib import nullcontext
        for shared in (False,True):
            sql=[];self.s.db.set_trace_callback(sql.append)
            with self.owner.source.verification_boundary()if shared else nullcontext(),patch.object(self.owner,'check',wraps=self.owner.check)as check:
                for _ in range(2):self.assertEqual(service.register_dependency(self.entry,self.principal,consumer,dependency,'/same-source',self.scope),expected)
                self.assertGreaterEqual(check.call_count,4)
            counts.append(sum('UNION ALL SELECT 1 FROM object_revision_registry'in statement or (statement.startswith('SELECT ')and "kind='runtime_events'"in statement and 'object_revision_registry WHERE'in statement and ('SELECT id FROM'in statement or 'SELECT 1 FROM'in statement))for statement in sql))
        self.assertLess(counts[1],counts[0])
    def test_foreign_added_revision_cannot_hide_inside_old_read_transaction(self):
        key=self.s.artifact({'foreign synthetic revision owner':True})
        with self.assertRaises(Conflict):
            with shared_read_boundary(self.s):
                self.s.db.execute('BEGIN');self.assertFalse(has_registered_revision(self.s,key))
                db=sqlite3.connect(self.s.root/'runtime.sqlite');self.addCleanup(db.close)
                db.execute('INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind)VALUES(?,?,?,?,?)',(identifier(),self.s.instance_id,key,0,'artifacts'));db.commit()
                checkpoint(self.s)
        self.s.db.execute('ROLLBACK')
    def test_process_added_revision_invalidates_old_phase(self):
        key=self.s.artifact({'process synthetic revision owner':True});revision=identifier()
        with self.assertRaises(Conflict):
            with shared_read_boundary(self.s):
                self.assertFalse(has_registered_revision(self.s,key))
                script='import sqlite3,sys; d=sqlite3.connect(sys.argv[1]);d.execute("INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind)VALUES(?,?,?,?,?)",(sys.argv[2],sys.argv[3],sys.argv[4],0,"artifacts"));d.commit();d.close()'
                subprocess.run([sys.executable,'-c',script,str(self.s.root/'runtime.sqlite'),revision,self.s.instance_id,key],check=True,timeout=10)
                checkpoint(self.s)

if __name__=='__main__':unittest.main()
