"""Complete-kind revision mapping facts preserve Ref checks and source capture."""
import copy
import sqlite3
import subprocess
import sys
import unittest
from digital_life.application.learning.eligibility import ref,slot
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc
from digital_life.domain.tool_learning_resources import DIMENSIONS
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
from digital_life.infrastructure.persistence.tool_learning_readset import facts,shared_read_boundary,checkpoint

class RevisionMappingMaterialTests(unittest.TestCase):
    def setUp(self):
        from tests import test_tool_learning_reference_kind as fixture
        case=fixture.ReferenceKindSharingTests();case.setUp();self.addCleanup(case.doCleanups)
        self.case=case;self.s=case.s;self.owner=case.owner;self.storage=case.storage;self.known=case.known
        self.entry=case.f.entry;self.principal=case.f.principal;self.scope=case.f.scope
    def outcome(self,value,complete=False,**options):
        meter=PhysicalReadMeter({k:10000000 for k in DIMENSIONS},utc(60));rows=[];sql=[];self.s.db.set_trace_callback(sql.append)
        if complete:meter.row_observer=lambda row:rows.append(dict(row))
        with meter.installed(self.s):
            try:result=('ok',self.storage.validate_ref(value,**options))
            except (ContractError,Conflict,Forbidden)as error:result=('error',type(error).__name__,str(error))
        self.s.db.set_trace_callback(None)
        return result,dict(meter.actual),rows,sql
    def equivalent(self,value,**options):
        small=self.outcome(value,False,**options);full=self.outcome(value,True,**options)
        self.assertEqual(small[0],full[0]);return small,full
    def test_snapshot_known_unknown_absence_and_owner_decisions_match_original_rows(self):
        for value in self.case.variants():self.equivalent(value)
        unknown=copy.deepcopy(self.case.f.origin)
        self.assertEqual(self.equivalent(unknown,version_owner=unknown['id'])[0][0][0],'error')
        wrong=copy.deepcopy(self.known);wrong['revision']=slot(999)
        self.assertEqual(self.equivalent(wrong)[0][0][0],'error')
        wrong=copy.deepcopy(self.known);wrong['kind']='artifacts';self.assertEqual(self.equivalent(wrong)[0][0][0],'error')
        wrong=copy.deepcopy(self.known);wrong['instance_id']='foreign-instance';self.assertEqual(self.equivalent(wrong)[0][0][0],'error')
        self.assertEqual(self.equivalent(self.known,version_owner=self.s.config()['controller'])[0][0][0],'error')
    def test_stable_memory_root_and_direct_native_r1_r2_remain_distinct_and_owned(self):
        from digital_life.application.services import Memory
        evidence=self.s.evidence(object_id=self.s.row('activities',self.case.f.f.activity)['trigger_event_id'],method='synthetic revision evidence')
        memory=Memory(self.s).encode('synthetic r1',evidence);r2=Memory(self.s).revise(memory['memory_id'],1,'synthetic r2',evidence)
        for number,key in ((1,memory['revision_id']),(2,r2)):
            root=ref(self.s,memory['memory_id']);root['revision']=slot(number)
            direct=ref(self.s,key);direct['revision']=slot(number)
            self.assertEqual(self.equivalent(root,version_owner=memory['memory_id'])[0][0][0],'ok')
            self.assertEqual(self.equivalent(direct,version_owner=memory['memory_id'])[0][0][0],'ok')
            wrong=copy.deepcopy(direct);wrong['revision']=slot(3-number)
            self.assertEqual(self.equivalent(wrong)[0][0][0],'error')
    def test_mapping_kind_filter_and_root_vs_revision_id_cannot_alias(self):
        origin=self.known['id'];number=self.known['revision']['value']
        with shared_read_boundary(self.s):
            good=list(facts(self.s,'revision_mapping_by_object',origin,number,'runtime_events'));self.assertEqual(len(good),1)
            self.assertEqual(list(facts(self.s,'revision_mapping_by_object',origin,number,'memory_revisions')),[])
            self.assertEqual(list(facts(self.s,'revision_mapping_by_id',origin,number,'runtime_events')),[])
            self.assertEqual(list(facts(self.s,'revision_mapping_by_id',good[0]['id'],number,'runtime_events'))[0]['object_id'],origin)
            for name in ('revision_mapping_by_object','revision_mapping_by_id'):
                with self.assertRaises(ContractError):list(facts(self.s,name,origin,number,'runtime_events','tail-instance'))
    def test_actual_observer_keeps_complete_revision_metadata_and_pure_path_returns_two_columns(self):
        small,full=self.equivalent(self.known)
        self.assertEqual(small[0][0],'ok');self.assertEqual(small[1]['scan'],full[1]['scan']);self.assertLess(small[1]['bytes'],full[1]['bytes'])
        self.assertTrue(any(sql.startswith('SELECT id,object_id FROM object_revision_registry')for sql in small[3]))
        self.assertTrue(any(sql.startswith('SELECT * FROM object_revision_registry')for sql in full[3]))
        self.assertTrue(any('revision_no'in row and 'recorded_at'in row and row.get('object_id')==self.known['id']for row in full[2]))
    def test_same_connection_new_revision_replaces_cached_absence(self):
        key=self.s.artifact({'mapping added':True})
        with shared_read_boundary(self.s):
            self.assertEqual(list(facts(self.s,'revision_mapping_by_object',key,0,'artifacts')),[])
            with self.s.tx():self.s.db.execute('INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind)VALUES(?,?,?,?,?)',(identifier(),self.s.instance_id,key,0,'artifacts'))
            self.assertEqual(list(facts(self.s,'revision_mapping_by_object',key,0,'artifacts'))[0]['object_id'],key)
    def test_nested_rollback_mapping_and_deferred_iterator_do_not_survive(self):
        key=self.s.artifact({'rolled-back mapping':True})
        with shared_read_boundary(self.s):
            with self.s.tx():
                with self.assertRaises(ValueError):
                    with self.s.tx():
                        self.s.db.execute('INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind)VALUES(?,?,?,?,?)',(identifier(),self.s.instance_id,key,0,'artifacts'))
                        list(facts(self.s,'revision_mapping_by_object',key,0,'artifacts'))
                        old=facts(self.s,'revision_mapping_by_object',key,0,'artifacts');raise ValueError('synthetic mapping rollback')
                with self.assertRaises(Conflict):next(iter(old))
                self.assertEqual(list(facts(self.s,'revision_mapping_by_object',key,0,'artifacts')),[])
    def test_foreign_revision_insert_rejects_old_transaction(self):
        key=self.s.artifact({'foreign mapping':True})
        with self.assertRaises(Conflict),shared_read_boundary(self.s):
            self.s.db.execute('BEGIN');list(facts(self.s,'revision_mapping_by_object',key,0,'artifacts'))
            db=sqlite3.connect(self.s.root/'runtime.sqlite');self.addCleanup(db.close)
            db.execute('INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind)VALUES(?,?,?,?,?)',(identifier(),self.s.instance_id,key,0,'artifacts'));db.commit();checkpoint(self.s)
        self.s.db.execute('ROLLBACK')
    def test_process_revision_insert_rejects_cached_mapping_phase(self):
        key=self.s.artifact({'process mapping':True})
        with self.assertRaises(Conflict),shared_read_boundary(self.s):
            list(facts(self.s,'revision_mapping_by_object',key,0,'artifacts'))
            script='import sqlite3,sys;d=sqlite3.connect(sys.argv[1]);d.execute("INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind)VALUES(?,?,?,?,?)",(sys.argv[2],sys.argv[3],sys.argv[4],0,"artifacts"));d.commit();d.close()'
            subprocess.run([sys.executable,'-c',script,str(self.s.root/'runtime.sqlite'),identifier(),self.s.instance_id,key],check=True,timeout=10);checkpoint(self.s)
    def test_real_dependency_registration_retains_result_and_reduces_mapping_queries(self):
        consumer=ref(self.s,self.s.artifact({'mapping consumer':True}));dependency={'target':copy.deepcopy(self.case.f.origin),'relation':'read','expected':copy.deepcopy(self.case.f.token),'consumer_purpose':'learn'}
        service=self.owner.eligibility;expected=service.register_dependency(self.entry,self.principal,consumer,dependency,'/mapping',self.scope);counts=[]
        for full in (True,False):
            meter=PhysicalReadMeter({k:10000000 for k in DIMENSIONS},utc(60));sql=[];self.s.db.set_trace_callback(sql.append)
            if full:meter.row_observer=lambda row:None
            with meter.installed(self.s),self.owner.source.verification_boundary():
                for reason in ('first known source','same revision another reason'):
                    value=copy.deepcopy(self.known);value['revision']['reason']=reason;self.storage.validate_ref(value)
                self.assertEqual(service.register_dependency(self.entry,self.principal,consumer,dependency,'/mapping',self.scope),expected)
            counts.append(sum(statement.startswith('SELECT * FROM object_revision_registry')or statement.startswith('SELECT id,object_id FROM object_revision_registry')for statement in sql))
        self.assertLess(counts[1],counts[0])

if __name__=='__main__':unittest.main()
