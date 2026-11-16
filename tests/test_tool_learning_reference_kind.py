"""Source-kind facts are shared; each Ref/revision/permission is still checked."""
import copy
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from digital_life.application.learning.eligibility import ref,slot
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc
from digital_life.domain.tool_learning_resources import DIMENSIONS
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
from digital_life.infrastructure.persistence.tool_learning_readset import shared_read_boundary,checkpoint

class ReferenceKindSharingTests(unittest.TestCase):
    def setUp(self):
        from tests import test_tool_learning_revision_existence as f
        case=f.RevisionExistenceSharingTests();case.setUp();self.addCleanup(case.doCleanups)
        self.f=case;self.s=case.s;self.owner=case.owner;self.storage=case.owner.eligibility.artifacts
        self.known=copy.deepcopy(case.origin);self.known['revision']=slot(case.token['revision'])
    def variants(self):
        one=copy.deepcopy(self.f.origin)
        two=copy.deepcopy(one);two['revision']['reason']='second independent technical reason'
        three=copy.deepcopy(one);three['revision'].update(status='unknown',reason_code='not_measured',reason='revision explicitly unknown')
        return [one,two,three,copy.deepcopy(self.known)]
    def outcome(self,value,full=False,**kwargs):
        meter=PhysicalReadMeter({k:10000000 for k in DIMENSIONS},utc(60));rows=[]
        if full:meter.row_observer=lambda row:rows.append(dict(row))
        with meter.installed(self.s):
            try:result=('ok',self.storage.validate_ref(value,**kwargs))
            except (ContractError,Conflict,Forbidden)as error:result=('error',type(error).__name__,str(error))
        return result,meter.actual,rows
    def test_same_database_old_full_row_and_fact_paths_have_same_ref_and_failure_results(self):
        cases=[(value,{})for value in self.variants()]
        wrong=copy.deepcopy(self.known);wrong['kind']='artifacts';cases.append((wrong,{}))
        wrong=copy.deepcopy(self.known);wrong['instance_id']='another-instance';cases.append((wrong,{}))
        wrong=copy.deepcopy(self.known);wrong['revision']=slot(999);cases.append((wrong,{}))
        cases.extend(((self.known,{'expected_kind':'artifacts'}),(self.known,{'version_owner':self.s.config()['controller']})))
        for value,options in cases:self.assertEqual(self.outcome(value,False,**options)[0],self.outcome(value,True,**options)[0])
    def test_ref_lookup_unknown_known_and_distinct_reasons_share_only_kind_material(self):
        sql=[];self.s.db.set_trace_callback(sql.append)
        with shared_read_boundary(self.s):
            ref(self.s,self.f.origin['id'])
            for value in self.variants():self.assertEqual(self.storage.validate_ref(value),value)
            with self.assertRaises(ContractError):self.storage.validate_ref(self.known,expected_kind='artifacts')
        matches=[row for row in sql if row.startswith('SELECT kind FROM object_registry')and self.f.origin['id']in row]
        self.assertEqual(len(matches),1)
        self.assertTrue(any('object_revision_registry'in row for row in sql));self.assertTrue(any('runtime_events e JOIN'in row for row in sql))
    def test_registry_actual_columns_and_meter_bytes_are_reduced_only_without_observer(self):
        projected=self.outcome(self.f.origin,False);complete=self.outcome(self.f.origin,True)
        self.assertEqual(projected[0],complete[0]);self.assertEqual(projected[1]['scan'],complete[1]['scan'])
        self.assertLess(projected[1]['bytes'],complete[1]['bytes'])
        self.assertTrue(any(row.get('id')==self.f.origin['id']and 'recorded_at'in row and 'instance_id'in row for row in complete[2]))
    def test_missing_kind_after_same_connection_registration_is_not_cached_absent(self):
        source=self.s.artifact({'new same-instance source':True});artifact=self.s.row('artifacts',source);key=identifier();value=ref(self.s,source);value['id']=key
        with shared_read_boundary(self.s):
            with self.assertRaises(ContractError):self.storage.validate_ref(value)
            with self.s.tx():self.s.insert('artifacts',id=key,hash=artifact['hash'],size=artifact['size'],media_type=artifact['media_type'],storage_ref=artifact['storage_ref'],retention_class=artifact['retention_class'])
            self.assertEqual(self.storage.validate_ref(value),value)
    def test_foreign_insert_does_not_rebase_old_transaction_or_kind_absence(self):
        key=identifier();value=copy.deepcopy(self.f.origin);value['id']=key
        with self.assertRaises(Conflict),shared_read_boundary(self.s):
            self.s.db.execute('BEGIN')
            with self.assertRaises(ContractError):self.storage.validate_ref(value)
            db=sqlite3.connect(self.s.root/'runtime.sqlite');self.addCleanup(db.close)
            db.execute('INSERT INTO object_registry(id,instance_id,kind)VALUES(?,?,?)',(key,self.s.instance_id,value['kind']));db.commit();checkpoint(self.s)
        self.s.db.execute('ROLLBACK')
    def test_true_process_registry_insert_invalidates_old_kind_phase(self):
        key=identifier()
        with self.assertRaises(Conflict),shared_read_boundary(self.s):
            self.storage.validate_ref(self.f.origin)
            script='import sqlite3,sys;d=sqlite3.connect(sys.argv[1]);d.execute("INSERT INTO object_registry(id,instance_id,kind)VALUES(?,?,?)",(sys.argv[2],sys.argv[3],"artifacts"));d.commit();d.close()'
            subprocess.run([sys.executable,'-c',script,str(self.s.root/'runtime.sqlite'),key,self.s.instance_id],check=True,timeout=10);checkpoint(self.s)
    def test_nested_rollback_registered_ref_does_not_survive_shared_kind(self):
        with shared_read_boundary(self.s):
            with self.s.tx():
                with self.assertRaises(ValueError):
                    with self.s.tx():
                        key=self.s.artifact({'phantom kind':True});value=ref(self.s,key);self.storage.validate_ref(value);raise ValueError('synthetic rollback')
                with self.assertRaises(ContractError):self.storage.validate_ref(value)
    def test_actual_registration_matches_full_registry_with_known_and_reason_variants(self):
        consumer=ref(self.s,self.s.artifact({'shared registration kind':True}));dep={'target':copy.deepcopy(self.f.origin),'relation':'read','expected':copy.deepcopy(self.f.token),'consumer_purpose':'learn'}
        expected=self.owner.eligibility.register_dependency(self.f.entry,self.f.principal,consumer,dep,'/kind-proof',self.f.scope)
        counts=[]
        for full in (True,False):
            sql=[];self.s.db.set_trace_callback(sql.append)
            # A real observer selects the preserved full-row branch; the
            # validation and registration themselves are never mocked.
            meter=PhysicalReadMeter({k:10000000 for k in DIMENSIONS},utc(60))
            if full:meter.row_observer=lambda row:None
            with meter.installed(self.s),self.owner.source.verification_boundary():
                for value in self.variants():self.storage.validate_ref(value)
                self.assertEqual(self.owner.eligibility.register_dependency(self.f.entry,self.f.principal,consumer,dep,'/kind-proof',self.f.scope),expected)
            counts.append(sum(('SELECT * FROM object_registry WHERE'in row or 'SELECT kind FROM object_registry WHERE'in row)and self.f.origin['id']in row for row in sql))
        self.assertLess(counts[1],counts[0])

if __name__=='__main__':unittest.main()
