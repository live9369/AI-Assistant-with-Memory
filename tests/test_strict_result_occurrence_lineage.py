"""Repeated model body keeps independent actual result occurrence lineage."""
from copy import deepcopy
import sqlite3
import unittest
from unittest.mock import patch
from tests import test_tool_learning_certified_input as fixture
from digital_life.application.learning.engine import _dependency,_retain_output_lineage
from digital_life.application.learning.eligibility import ref
from digital_life.application.services import Memory
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc
from digital_life.domain import tool_learning_contract as c

class OccurrenceLineageTests(unittest.TestCase):
    def setUp(self):
        self.case=fixture.CertifiedInputTests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.s=self.case.s;self.scope=self.case.scope
        evidence=self.s.evidence(object_id=self.s.row('activities',self.case.f.activity)['trigger_event_id'],method='isolated occurrence source')
        first=Memory(self.s).encode('source version one',evidence);Memory(self.s).revise(first['memory_id'],1,'source version two',evidence)
        self.memory=ref(self.s,first['memory_id']);self.tokens=[{'object':deepcopy(self.memory),'revision':n,'epoch':0}for n in (1,2)]
    def result(self):
        s=self.s;f=self.case.f;output=f.output;packet={'isolated':'actual occurrence fixture'}
        artifact=s.artifact(output);request_artifact=s.artifact(packet)
        step_no=s.db.execute('SELECT COALESCE(MAX(step_no),-1)+1 FROM activity_steps WHERE activity_id=?',(f.activity,)).fetchone()[0]
        step=s.insert('activity_steps',activity_id=f.activity,step_no=step_no,step_type='isolated-occurrence',state='pending',attempt=0,idempotency_key=identifier())
        cfg=s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(s.instance_id,)).fetchone()[0];model=s.db.execute('SELECT id FROM model_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(s.instance_id,)).fetchone()[0]
        request=s.insert('thought_requests',activity_id=f.activity,step_id=step,request_key=identifier(),purpose='plan',task='isolated occurrence',instruction_version='isolated-occurrence',output_schema_version=3,request_artifact_id=request_artifact,request_hash=c.fingerprint(packet),input_manifest_hash=c.fingerprint(packet),model_config_id=cfg,model_version_id=model,prepared_activity_revision=0,expected_input_epoch=0,expected_policy_epoch=s.rows('policy_epochs')[0]['epoch'],runtime_epoch=f.identity.epoch,process_run_id=f.identity.process_id,deadline=utc(300),token_budget=100,attempt_limit=1,retry_policy={'max_attempts':1},generation_config={},state='running')
        attempt=s.insert('thought_attempts',request_id=request,attempt_no=1,state='received',queued_at=utc(),dispatch_token=identifier(),provider='isolated-no-model',model='synthetic',runtime_epoch=f.identity.epoch,process_run_id=f.identity.process_id)
        result=s.insert('thought_results',request_id=request,attempt_id=attempt,response_artifact_id=artifact,response_hash=c.fingerprint(output),received_at=utc(),parsed_artifact_id=artifact,validation_errors=[],validation_state='valid',acceptance='accepted',accepted_at=utc())
        s.db.execute("UPDATE thought_requests SET state='succeeded',accepted_result_id=? WHERE id=?",(result,request));return request,result,artifact
    def manifest(self,token,scope=None):
        return {'fields':[{'path':'/input/source','dependencies':[{'target':deepcopy(token['object']),'expected':deepcopy(token),'relation':relation,'consumer_purpose':'learn'}for relation in ('read','delete')],'dependency_scopes':[deepcopy(scope or self.scope)]*2}]}
    def retain(self,request,result,artifact,token,scope=None):_retain_output_lineage(self.s,request,result,artifact,self.manifest(token,scope))
    def edges(self,consumer):return [dict(row)for row in self.s.db.execute('SELECT * FROM tl_dependency WHERE consumer_ref_id=? ORDER BY field_path,relation',(consumer,))]
    def check_sources(self,result,artifact,token,scope):
        own=self.edges(result);body=[row for row in self.edges(artifact)if row['field_path'].startswith('/_strict_response_occurrences/v1/'+result+'/')]
        self.assertEqual(len(own),2);self.assertEqual(len(body),2)
        revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE object_id=? AND revision_no=?',(token['object']['id'],token['revision'])).fetchone()[0]
        for rows,prefix in ((own,''),(body,'/_strict_response_occurrences/v1/'+result)):
            for index,relation in enumerate(('read','delete')):
                row=next(v for v in rows if v['relation']==relation)
                self.assertEqual(row['field_path'],prefix+'/input/source/'+str(index));self.assertEqual(row['source_revision_id'],revision)
                meta=self.s.read_artifact(row['metadata_artifact_id']);self.assertEqual(meta['scope'],scope);self.assertEqual(meta['dependency']['expected'],token)
    def test_same_body_two_results_have_complete_independent_occurrence_sources(self):
        with self.s.tx():
            a=self.result();self.retain(*a,self.tokens[0]);b=self.result();self.retain(*b,self.tokens[0])
        self.assertNotEqual(a[1],b[1]);self.assertNotEqual(a[0],b[0]);self.assertEqual(a[2],b[2])
        self.check_sources(a[1],a[2],self.tokens[0],self.scope);self.check_sources(b[1],b[2],self.tokens[0],self.scope)
        self.assertEqual(len(self.edges(a[2])),4)
        self.assertEqual(self.s.db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(self.s.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_same_owner_epoch_different_revisions_and_scopes_do_not_alias(self):
        scope=deepcopy(self.scope);scope['property']='different exact occurrence scope'
        with self.s.tx():
            a=self.result();self.retain(*a,self.tokens[0]);b=self.result();self.retain(*b,self.tokens[1],scope)
        self.assertEqual(a[2],b[2]);self.check_sources(a[1],a[2],self.tokens[0],self.scope);self.check_sources(b[1],b[2],self.tokens[1],scope)
    def test_existing_legacy_edges_and_metadata_remain_unchanged(self):
        with self.s.tx():
            a=self.result()
            for index,relation in enumerate(('read','delete')):_dependency(self.s,ref(self.s,a[2]),self.tokens[0],self.scope,relation,'/input/source/'+str(index),'learn')
            old=self.edges(a[2]);b=self.result();self.retain(*b,self.tokens[1])
        current=self.edges(a[2])
        self.assertTrue(all(row in current for row in old));self.assertEqual(len(current),4)
        self.check_sources(b[1],b[2],self.tokens[1],self.scope)
    def test_wrong_actual_result_request_or_artifact_fails_before_any_edge(self):
        with self.s.tx():a=self.result();b=self.result();other=self.s.artifact({'different':'body'})
        for request,result,artifact in ((b[0],a[1],a[2]),(a[0],a[1],other),(a[0],'f'*32,a[2])):
            with self.subTest(result=result),self.assertRaises((Conflict,ContractError)):
                with self.s.tx():self.retain(request,result,artifact,self.tokens[0])
        self.assertEqual(self.edges(a[1]),[]);self.assertEqual(self.edges(a[2]),[])
    def test_same_occurrence_collision_is_not_ignored_or_relabelled(self):
        with self.s.tx():a=self.result();self.retain(*a,self.tokens[0])
        old=self.edges(a[1])+self.edges(a[2])
        with self.assertRaises(sqlite3.IntegrityError):
            with self.s.tx():self.retain(*a,self.tokens[1])
        self.assertEqual(self.edges(a[1])+self.edges(a[2]),old)
    def test_failure_halfway_rolls_back_result_and_all_occurrence_edges(self):
        original=_dependency;count=[0];created=[]
        def fail(*args,**kwargs):
            count[0]+=1
            if count[0]==3:raise Conflict('isolated occurrence write failure')
            return original(*args,**kwargs)
        with self.assertRaisesRegex(Conflict,'occurrence write failure'):
            with self.s.tx(),patch('digital_life.application.learning.engine._dependency',new=fail):
                a=self.result();created.append(a);self.retain(*a,self.tokens[0])
        a=created[0];self.assertIsNone(self.s.db.execute('SELECT 1 FROM thought_results WHERE id=?',(a[1],)).fetchone())
        self.assertEqual(self.edges(a[1]),[]);self.assertEqual(self.edges(a[2]),[])
    def test_shared_body_self_source_remains_bounded_and_original_scan_limit_applies(self):
        with self.s.tx():
            a=self.result();self.retain(*a,self.tokens[0]);b=self.result()
            token={'object':ref(self.s,a[2]),'revision':0,'epoch':0};self.retain(*b,token)
        self.assertEqual(a[2],b[2])
        service=self.case.e.owners.eligibility
        reached=service._upstream_current(token,self.scope,{'remaining':service.max_rows})
        self.assertLessEqual(len(reached),service.max_nodes*2)
        self.assertIn(self.memory['id'],[row[0]for row in reached])
        with self.assertRaisesRegex(Forbidden,'row scan limit'):
            service._upstream_current(token,self.scope,{'remaining':0})
    def test_no_caps_models_or_manifest_values_are_changed(self):
        old=self.s.row('activities',self.case.f.activity)['budget_json'];manifest=self.manifest(self.tokens[0]);prior=deepcopy(manifest)
        with self.s.tx():a=self.result();_retain_output_lineage(self.s,*a,manifest)
        self.assertEqual(manifest,prior);self.assertEqual(self.s.row('activities',self.case.f.activity)['budget_json'],old)
