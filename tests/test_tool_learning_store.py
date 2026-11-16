"""IM04 mechanics in new, stopped synthetic schema3 databases; no real authority."""
import copy
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from digital_life.domain.contracts import ContractError, Conflict, Forbidden, dumps, identifier, utc
from digital_life.domain.tool_learning_contract import fingerprint
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore, StorageAuthority, StorageGrant, CommitUnknown, command_fingerprint
from evaluation.tool_learning_fixture import SyntheticToolLearningFixture
from tests.test_tool_learning_products import envelope, payloads, sl, coverage, control, method, product, representation, decision, effect, evidence

RESOURCES=Path(__file__).resolve().parents[1]/'digital_life'/'resources'

class MechanicalAuthority(StorageAuthority):
    """Deterministic synthetic verifier: never production authorization evidence."""
    def __init__(self):self.stages=[];self.deny_stage=None;self.entry='synthetic-m14';self.expected_context=None;self.deny_projection=False;self.projections=[];self.owner='M14';self.tables=frozenset(('tl_work','tl_dependency','tl_product'))
    def verify(self,entry,operation,request,instance_id,stage):
        self.stages.append(stage)
        principal=request['principal']
        if entry!=self.entry or stage==self.deny_stage:raise Forbidden('synthetic denial')
        if self.expected_context is not None and any(request[key]!=self.expected_context[key] for key in ('work_ref','control','budget')):raise Forbidden('synthetic context mismatch')
        return StorageGrant(self.owner,self.tables)

    def project_response(self,entry,operation,request,response,instance_id,stage):
        self.projections.append((stage,copy.deepcopy(response)))
        if self.deny_projection:raise Forbidden('synthetic response visibility revoked')
        return response

class ToolLearningStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.fixture=SyntheticToolLearningFixture(Path(self.tmp.name).resolve()/'new',schema_version=3)
        self.f=self.fixture.__enter__();self.addCleanup(self.fixture.__exit__,None,None,None)
        self.s=self.f.store;self.db=self.s.db
        self.db.executescript((RESOURCES/'tool_learning_v1.sql').read_text())
        self.authority=MechanicalAuthority();self.adapter=ToolLearningStore(self.s,self.authority)
        self.activity=self.f.expected['activity_id'];self.art=self.db.execute('SELECT id FROM artifacts LIMIT 1').fetchone()[0]
        self.budget=self.db.execute('SELECT id FROM activity_budget_accounts WHERE activity_id=?',(self.activity,)).fetchone()[0]
        self.request=self.make_request()

    def ref(self,key,revision=None):
        row=self.db.execute('SELECT kind FROM object_registry WHERE instance_id=? AND id=?',(self.s.instance_id,key)).fetchone()
        return {'instance_id':self.s.instance_id,'id':key,'kind':row['kind'],'revision':sl() if revision is None else sl(revision,'known')}

    def make_request(self):
        req=envelope(payloads()['admit_observation']);req['instance_id']=self.s.instance_id;req['command_id']=identifier();req['work_ref']=sl()
        req['principal']={'actor':self.ref(self.f.expected['controller']),'module':'M14','recipient':self.ref(self.f.expected['self_actor']),'purpose':'learn','authorization':self.ref(self.f.expected['policy_id'])}
        # The request is structurally real, while the test authority explicitly does not
        # claim current control/budget/semantic readiness as a production verifier would.
        req['payload']['source_activity']=self.ref(self.activity)
        return req

    def response(self,request=None):
        request=self.request if request is None else request
        return {'command_id':request['command_id'],'operation':'admit_observation','disposition':'applied','owner':'M14','result_refs':[],'current':sl(),'reason':'none','error_code':'NONE','coverage':coverage(),'retry':{'allowed':False,'condition':sl(),'resume_work':sl()},'committed_at':sl(utc(),'known')}

    def execute(self,callback=None,request=None):
        request=self.request if request is None else request
        return self.adapter.execute('synthetic-m14','admit_observation',request,callback or (lambda tx:self.response(request)))

    def dependency(self,tx):
        return tx.insert('tl_dependency',consumer_ref_id=self.activity,source_ref_id=self.activity,relation='read',purpose='learn',expected_epoch=0,field_path='/synthetic',metadata_artifact_id=self.art)

    def seed_work(self):
        ctrl=control()
        for token in (ctrl['policy'],ctrl['configuration']):token['object']=self.ref(self.f.expected['memory_id'])
        with self.s.tx():
            ca=self.s.artifact(ctrl);ma=self.s.artifact(method());work=identifier()
            fields=dict(id=work,instance_id=self.s.instance_id,learning_activity_id=self.activity,source_activity_id=self.activity,source_artifact_id=self.art,purpose='learn',processing_identity='a'*64,state='admitted',phase='admit',review_round=0,conditions_artifact_id=self.art,control_artifact_id=ca,method_artifact_id=ma,deadline=utc(60),budget_account_id=self.budget,row_revision=0)
            self.raw_insert('tl_work',fields)
        return work

    def raw_insert(self,table,fields):
        self.db.execute('INSERT INTO '+table+' ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',tuple(fields.values()))

    def localize(self,value):
        if type(value) is dict:
            if set(value)=={'instance_id','id','kind','revision'}:return self.ref(self.activity)
            return {key:self.localize(child) for key,child in value.items()}
        if type(value) is list:return [self.localize(child) for child in value]
        return value

    def seed_content_chain(self):
        work=self.seed_work();proposal,content,rev,dec,head,rep,handoff=[identifier() for _ in range(7)]
        def put(table,**fields):self.raw_insert(table,dict(id=fields.pop('id'),instance_id=self.s.instance_id,**fields))
        with self.s.tx():
            put('tl_product',id=proposal,work_id=work,product_type='UpdateProposal',payload_artifact_id=self.art,processing_identity='b'*64,source_fingerprint='c'*64)
            put('tl_content',id=content,content_kind='source_report',head_revision_id=rev,row_revision=0)
            put('tl_decision',id=dec,work_id=work,proposal_id=proposal,review_round=0,decision_artifact_id=self.art,operation='accept',content_revision_id=rev,policy_ref_id=self.f.expected['policy_id'],created_at=utc())
            put('tl_content_revision',id=rev,content_id=content,revision_no=1,decision_id=dec,product_id=proposal,payload_artifact_id=self.art,status='accepted')
            put('tl_representation_head',id=head,content_id=content,format_version='TL-TEXT-1',representation_id=rep,expected_content_revision_id=rev,row_revision=0)
            body=self.s.artifact('synthetic source reports inventory 7',media_type='text/plain');body_hash=self.s.row('artifacts',body)['hash']
            put('tl_representation',id=rep,series_id=head,content_revision_id=rev,decision_id=dec,format_version='TL-TEXT-1',representation_no=1,payload_artifact_id=self.art,body_artifact_id=body,body_digest=body_hash,state='ready')
            put('tl_handoff',id=handoff,work_id=work,content_revision_id=rev,decision_id=dec,format_version='TL-TEXT-1',input_fingerprint='d'*64,state='pending',lease_generation=0,attempts=0,deadline=utc(60),budget_account_id=self.budget,row_revision=0)
        return dict(work=work,proposal=proposal,content=content,revision=rev,decision=dec,head=head,representation=rep,handoff=handoff,body=body,body_hash=body_hash)

    def test_representation_payload_body_and_series_mapping_are_checked_before_commit(self):
        chain=self.seed_content_chain()
        value=self.localize(representation())
        value.update(id=identifier(),series_ref=self.ref(chain['head']),representation_no=2,content_ref=self.ref(chain['content']),content_revision={'object':self.ref(chain['content']),'revision':1,'epoch':0},decision_ref=self.ref(chain['decision']),body_artifact=self.ref(chain['body']),body_digest={'algorithm':'sha256','hex':chain['body_hash']})
        # Evidence is local, correctly registered material, without claiming scientific support.
        def bind_evidence(node):
            if type(node) is dict:
                if 'source_kind' in node and 'artifact' in node:
                    node['artifact']=self.ref(chain['body']);node['digest']={'algorithm':'sha256','hex':chain['body_hash']};node['media_type']='text/plain'
                for child in node.values():bind_evidence(child)
            elif type(node) is list:
                for child in node:bind_evidence(child)
        bind_evidence(value)
        self.authority.owner='M04';self.authority.tables=frozenset(('tl_representation','tl_representation_head'))
        request=copy.deepcopy(self.request);request['principal']['module']='M04';request['principal']['purpose']='represent';request['work_ref']=sl(self.ref(chain['work']),'known')
        def run(candidate,key):
            req=copy.deepcopy(request);req['command_id']=identifier();req['idempotency_key']=key
            req['payload']={'handoff':self.ref(chain['handoff']),'lease_generation':1,'worker':self.ref(self.f.expected['self_actor']),'representation':candidate}
            def callback(tx):
                artifact=tx.put_artifact(candidate,'Representation')
                tx.insert('tl_representation',id=candidate['id'],series_id=chain['head'],content_revision_id=chain['revision'],decision_id=chain['decision'],format_version='TL-TEXT-1',representation_no=candidate['representation_no'],payload_artifact_id=artifact,body_artifact_id=chain['body'],body_digest=chain['body_hash'],state='ready')
                result=self.response(req);result['operation']='publish_representation';result['owner']='M04';return result
            return self.adapter.execute('synthetic-m14','publish_representation',req,callback)
        run(value,'valid-representation')
        for field,incorrect in [('series_ref',self.ref(chain['content'])),('body_digest',{'algorithm':'sha256','hex':'a'*64}),('decision_ref',self.ref(chain['proposal']))]:
            bad=copy.deepcopy(value);bad['id']=identifier();bad['representation_no']=3;bad[field]=incorrect
            with self.subTest(field=field),self.assertRaises(ContractError):run(bad,'bad-'+field)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],2)

    def test_reuse_decision_may_reference_original_handoff_without_new_obligation(self):
        chain=self.seed_content_chain();self.authority.owner='M03';self.authority.tables=frozenset(('tl_decision',))
        req=copy.deepcopy(self.request);req['principal']['module']='M03';req['principal']['purpose']='accept';req['work_ref']=sl(self.ref(chain['work']),'known');req['payload']={'proposal':self.ref(chain['proposal']),'review_round':1,'policy':self.ref(self.f.expected['policy_id']),'review':sl(),'atomic_group':sl()}
        value=self.localize(decision('reuse'));value.update(id=identifier(),work_ref=self.ref(chain['work']),proposal_ref=self.ref(chain['proposal']),review_round=1,actor=req['principal'],policy_ref=self.ref(self.f.expected['policy_id']),content_ref=sl(self.ref(chain['content']),'known'),revision_ref=sl(self.ref(chain['revision']),'known'),handoff_refs=[self.ref(chain['handoff'])])
        for chk in value['checks'].values():chk['checker']=req['principal']
        def callback(tx):
            artifact=tx.put_artifact(value,'Decision')
            tx.insert('tl_decision',id=value['id'],work_id=chain['work'],proposal_id=chain['proposal'],review_round=1,decision_artifact_id=artifact,operation='reuse',content_revision_id=chain['revision'],policy_ref_id=self.f.expected['policy_id'],created_at=value['created_at'])
            result=self.response(req);result.update(operation='decide_proposal',owner='M03');return result
        self.adapter.execute('synthetic-m14','decide_proposal',req,callback)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_handoff').fetchone()[0],1)

    def test_effect_requires_trusted_metric_binding_and_preserves_unknown_measurement_slot(self):
        work=self.seed_work()
        with self.s.tx():metric=self.s.insert('metric_definitions',name='synthetic-effect',formula_version='fixture-v1',unit='gain',denominator_rule='synthetic',missing_rule='unknown',stratification={})
        assessment=self.localize(effect());assessment['measurement_ref']=sl(None,'unknown');assessment['metric_definition']=self.ref(metric)
        value=self.localize(product('EffectAssessment',assessment));value['body']=copy.deepcopy(assessment);value.update(product_id=identifier(),instance_id=self.s.instance_id,producer=self.request['principal'],work_ref=self.ref(work),source_refs=[])
        for chk in value['checks'].values():chk['checker']=self.request['principal']
        req=copy.deepcopy(self.request);req['work_ref']=sl(self.ref(work),'known');req['payload']={'work':self.ref(work),'measurement':sl(None,'unknown'),'assessment':assessment}
        def callback(tx):
            product_artifact=tx.put_artifact(value,'Product');effect_artifact=tx.put_artifact(assessment,'EffectAssessment')
            tx.insert('tl_product',id=value['product_id'],work_id=work,product_type='EffectAssessment',payload_artifact_id=product_artifact,processing_identity=value['processing_identity']['hex'],source_fingerprint='c'*64)
            tx.insert('tl_effect',work_id=work,product_id=value['product_id'],metric_contract='synthetic-contract-v1',state='not_measured',payload_artifact_id=effect_artifact)
            result=self.response(req);result['operation']='record_effect';return result
        self.authority.tables=frozenset(('tl_product','tl_effect'))
        with self.assertRaises(Forbidden):self.adapter.execute('synthetic-m14','record_effect',req,callback)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_effect').fetchone()[0],0)
        class ResolvedAuthority(MechanicalAuthority):
            def verify_metric_contract(self,entry,operation,request,metric_contract,definition,instance_id):
                if metric_contract!='synthetic-contract-v1' or definition['id']!=metric:raise Forbidden('synthetic unresolved contract')
        self.authority=ResolvedAuthority();self.authority.tables=frozenset(('tl_product','tl_effect'));self.adapter=ToolLearningStore(self.s,self.authority)
        self.adapter.execute('synthetic-m14','record_effect',req,callback)
        stored=self.db.execute('SELECT measurement_ref_id,payload_artifact_id FROM tl_effect').fetchone()
        self.assertIsNone(stored['measurement_ref_id'])
        self.assertEqual(self.adapter.read_artifact(stored['payload_artifact_id'],'EffectAssessment')['measurement_ref']['status'],'unknown')

    def test_known_measurement_ref_cannot_be_silently_dropped_from_row(self):
        work=self.seed_work()
        assessment=self.localize(effect());assessment['measurement_ref']=sl(self.ref(self.activity),'known')
        value=self.localize(product('EffectAssessment',assessment));value['body']=copy.deepcopy(assessment);value.update(product_id=identifier(),instance_id=self.s.instance_id,producer=self.request['principal'],work_ref=self.ref(work),source_refs=[])
        for chk in value['checks'].values():chk['checker']=self.request['principal']
        req=copy.deepcopy(self.request);req['work_ref']=sl(self.ref(work),'known');req['payload']={'work':self.ref(work),'measurement':sl(self.ref(self.activity),'known'),'assessment':assessment}
        class ResolvedAuthority(MechanicalAuthority):
            def verify_metric_contract(self,*args):return None
        authority=ResolvedAuthority();authority.tables=frozenset(('tl_product','tl_effect'));adapter=ToolLearningStore(self.s,authority)
        def callback(tx):
            pa=tx.put_artifact(value,'Product');ea=tx.put_artifact(assessment,'EffectAssessment')
            tx.insert('tl_product',id=value['product_id'],work_id=work,product_type='EffectAssessment',payload_artifact_id=pa,processing_identity=value['processing_identity']['hex'],source_fingerprint='c'*64)
            tx.insert('tl_effect',work_id=work,product_id=value['product_id'],metric_contract='synthetic',state='not_measured',payload_artifact_id=ea)
            result=self.response(req);result['operation']='record_effect';return result
        with self.assertRaises(ContractError):adapter.execute('synthetic-m14','record_effect',req,callback)

    def test_ref_revision_slot_basis_cannot_hide_unregistered_reference(self):
        work=self.seed_work()
        value=self.localize(product('ObservationExtract',{'observations':[],'coverage':coverage(),'empty_reason':sl('synthetic empty','known')}))
        value.update(product_id=identifier(),instance_id=self.s.instance_id,producer=self.request['principal'],work_ref=self.ref(work),source_refs=[])
        for chk in value['checks'].values():chk['checker']=self.request['principal']
        orphan=self.ref(self.activity);orphan['id']=identifier();value['work_ref']['revision']['basis_refs']=[orphan]
        def callback(tx):
            pa=tx.put_artifact(value,'Product');tx.insert('tl_product',id=value['product_id'],work_id=work,product_type='ObservationExtract',payload_artifact_id=pa,processing_identity=value['processing_identity']['hex'],source_fingerprint='c'*64)
            return self.response()
        with self.assertRaises(ContractError):self.execute(callback)

    def test_authorized_external_source_is_kept_as_typed_material_not_fake_local_fk(self):
        work=self.seed_work();external={'instance_id':'external-domain','id':'source-7','kind':'external_event','revision':sl()}
        source=self.localize(evidence());source['source']=external;source['artifact']=self.ref(self.art);source['digest']={'algorithm':'sha256','hex':self.s.row('artifacts',self.art)['hash']}
        value=self.localize(product('ObservationExtract',{'observations':[],'coverage':coverage(),'empty_reason':sl('synthetic empty','known')}))
        value.update(product_id=identifier(),instance_id=self.s.instance_id,producer=self.request['principal'],work_ref=self.ref(work),source_refs=[source])
        for chk in value['checks'].values():chk['checker']=self.request['principal']
        def callback(tx):
            artifact=tx.put_artifact(value,'Product');tx.insert('tl_product',id=value['product_id'],work_id=work,product_type='ObservationExtract',payload_artifact_id=artifact,processing_identity=value['processing_identity']['hex'],source_fingerprint='c'*64)
            return self.response()
        with self.assertRaises(Forbidden):self.execute(callback)
        class ExternalAuthority(MechanicalAuthority):
            def verify_external_ref(self,entry,operation,request,reference,instance_id):
                if reference!=external:raise Forbidden('unknown external source')
        self.authority=ExternalAuthority();self.adapter=ToolLearningStore(self.s,self.authority)
        self.execute(callback)
        self.assertIsNone(self.db.execute('SELECT id FROM object_registry WHERE id=?',(external['id'],)).fetchone())

    def test_bool_counters_are_not_silently_converted_to_integers(self):
        def callback(tx):
            tx.insert('tl_dependency',consumer_ref_id=self.activity,source_ref_id=self.activity,relation='read',purpose='learn',expected_epoch=True,field_path='/x',metadata_artifact_id=self.art)
            return self.response()
        with self.assertRaises(ContractError):self.execute(callback)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_command').fetchone()[0],0)

    def test_cas_requires_exact_expected_revision_and_preserves_identity(self):
        work=self.seed_work()
        def callback(tx):
            self.assertEqual(tx.cas_update('tl_work',work,0,state='processing'),1)
            with self.assertRaises(Conflict):tx.cas_update('tl_work',work,0,state='waiting')
            with self.assertRaises(ContractError):tx.cas_update('tl_work',work,True,state='waiting')
            with self.assertRaises(Forbidden):tx.cas_update('tl_work',work,1,processing_identity='e'*64)
            return self.response()
        self.execute(callback)
        self.assertEqual(self.db.execute('SELECT state,row_revision FROM tl_work WHERE id=?',(work,)).fetchone()[0],'processing')

    def test_product_payload_actual_work_kind_and_row_identity_must_match(self):
        work=self.seed_work()
        value=self.localize(product('ObservationExtract',{'observations':[],'coverage':coverage(),'empty_reason':sl('synthetic empty','known')}))
        value.update(product_id=identifier(),instance_id=self.s.instance_id,producer=self.request['principal'],work_ref=self.ref(work),source_refs=[])
        for checker in value['checks'].values():checker['checker']=self.request['principal']
        def callback(tx):
            artifact=tx.put_artifact(value,'Product')
            tx.insert('tl_product',id=value['product_id'],work_id=work,product_type='ObservationExtract',payload_artifact_id=artifact,processing_identity=value['processing_identity']['hex'],source_fingerprint='c'*64)
            return self.response()
        self.execute(callback)
        changed=copy.deepcopy(self.request);changed['idempotency_key']='other';changed['command_id']=identifier()
        value['product_id']=identifier();value['work_ref']['kind']='activities';value['processing_identity']['hex']='d'*64
        with self.assertRaises(ContractError):self.execute(lambda tx:(callback(tx),self.response(changed))[1],changed)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_product').fetchone()[0],1)

    def test_default_authority_and_boolean_authority_fail_closed(self):
        adapter=ToolLearningStore(self.s)
        with self.assertRaises(Forbidden):adapter.execute('M14','admit_observation',self.request,lambda tx:self.response())
        with self.assertRaises(ContractError):ToolLearningStore(self.s,True)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_command').fetchone()[0],0)

    def test_self_reported_module_or_entry_cannot_grant_write(self):
        with self.assertRaises(Forbidden):self.adapter.execute('M14','admit_observation',self.request,lambda tx:self.response())
        req=copy.deepcopy(self.request);req['principal']['module']='M03'
        with self.assertRaises(Forbidden):self.execute(request=req)

    def test_command_and_business_registration_commit_atomically(self):
        ids=[]
        def callback(tx):ids.append(self.dependency(tx));return self.response()
        result=self.execute(callback)
        self.assertEqual(result['command_id'],self.request['command_id'])
        self.assertEqual(self.db.execute('SELECT kind FROM object_registry WHERE id=?',(ids[0],)).fetchone()[0],'tl_dependency')
        self.assertEqual(self.db.execute('SELECT state FROM tl_command').fetchone()[0],'committed')
        self.assertEqual(self.s.integrity()['foreign_keys'],[])
        self.assertTrue((self.f.root/'WAKE_DISABLED').is_file());self.assertEqual(self.f.control.state()['user_stopped'],1)

    def test_exact_replay_does_not_rerun_callback(self):
        first=self.execute()
        second=self.execute(lambda tx:self.fail('callback must not rerun'))
        self.assertEqual(first,second)
        self.assertIn('replay',self.authority.stages)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_command').fetchone()[0],1)

    def test_new_command_id_and_new_snapshots_replay_original_logical_result(self):
        original=self.execute()
        changed=copy.deepcopy(self.request);changed['command_id']=identifier()
        changed['control']['runtime_epoch']=1;changed['budget']['max_input_tokens']=99
        self.assertEqual(command_fingerprint(changed),command_fingerprint(self.request))
        result=self.execute(lambda tx:self.fail('snapshot replay must not rerun'),request=changed)
        self.assertEqual(result,original)
        self.assertEqual(result['command_id'],self.request['command_id'])

    def test_full_request_context_rechecked_on_replay_and_reconciliation(self):
        self.execute();self.authority.expected_context=copy.deepcopy(self.request)
        for field in ('control','budget'):
            changed=copy.deepcopy(self.request)
            if field=='control':changed[field]['runtime_epoch']=9
            else:changed[field]['max_scan']=9
            with self.assertRaises(Forbidden):self.execute(request=changed)
            with self.assertRaises(Forbidden):self.adapter.lookup_command('synthetic-m14','admit_observation',changed)

    def test_old_result_visibility_must_be_authorized_for_replay_and_reconcile(self):
        self.execute();self.authority.deny_projection=True
        with self.assertRaises(Forbidden):self.execute(lambda tx:self.fail('must not rerun'))
        with self.assertRaises(Forbidden):self.adapter.lookup_command('synthetic-m14','admit_observation',self.request)
        self.assertTrue(self.authority.projections)

    def test_changed_original_fingerprint_is_conflict(self):
        self.execute();changed=copy.deepcopy(self.request);changed['payload']['processing_method']['version']='2'
        with self.assertRaises(Conflict):self.execute(request=changed)
        self.assertEqual(self.db.execute('SELECT fingerprint FROM tl_command').fetchone()[0],command_fingerprint(self.request))

    def test_callback_error_rolls_back_command_business_and_registry(self):
        captured=[]
        def fail(tx):captured.append(self.dependency(tx));raise RuntimeError('synthetic callback failure')
        with self.assertRaises(RuntimeError):self.execute(fail)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_command').fetchone()[0],0)
        self.assertIsNone(self.db.execute('SELECT id FROM object_registry WHERE id=?',(captured[0],)).fetchone())

    def test_authority_revocation_at_commit_rolls_back(self):
        self.authority.deny_stage='commit'
        with self.assertRaises(Forbidden):self.execute(lambda tx:(self.dependency(tx),self.response())[1])
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_dependency').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_command').fetchone()[0],0)

    def test_unresolved_fk_commit_failure_has_no_half_command(self):
        def fail(tx):
            tx.insert('tl_dependency',consumer_ref_id=identifier(),source_ref_id=self.activity,relation='read',purpose='learn',expected_epoch=0,field_path='/missing',metadata_artifact_id=self.art)
            return self.response()
        with self.assertRaises(sqlite3.IntegrityError):self.execute(fail)
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_dependency').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_command').fetchone()[0],0)

    def test_unknown_commit_ack_is_reconciled_without_rerun(self):
        original=self.adapter._commit
        def lost_ack():original();raise sqlite3.OperationalError('synthetic lost commit acknowledgement')
        with patch.object(self.adapter,'_commit',side_effect=lost_ack):
            with self.assertRaises(CommitUnknown):self.execute()
        found=self.adapter.lookup_command('synthetic-m14','admit_observation',self.request)
        self.assertEqual(found['state'],'committed');self.assertEqual(found['result']['command_id'],self.request['command_id'])
        self.execute(lambda tx:self.fail('must reconcile, not rerun'))

    def test_lookup_absent_does_not_write_and_does_not_infer_success(self):
        before=self.db.total_changes
        request=copy.deepcopy(self.request);request['idempotency_key']='absent'
        found=self.adapter.lookup_command('synthetic-m14','admit_observation',request)
        self.assertEqual(found,{'state':'absent','result':None});self.assertEqual(before,self.db.total_changes)

    def test_owner_table_boundary_and_no_raw_connection_port(self):
        def callback(tx):
            self.assertFalse(hasattr(tx,'db'));self.assertFalse(hasattr(tx,'store'))
            with self.assertRaises(Forbidden):tx.insert('tl_content',content_kind='source_report',row_revision=0)
            with self.assertRaises(Forbidden):tx.insert('object_registry',kind='spoofed')
            with self.assertRaises(Forbidden):tx.insert('tl_dependency; DROP TABLE tl_work',x=1)
            return self.response()
        self.execute(callback)

    def test_session_cannot_be_used_after_commit_or_nested(self):
        captured=[]
        def callback(tx):
            captured.append(tx)
            with self.assertRaises(Conflict):self.execute()
            return self.response()
        self.execute(callback)
        with self.assertRaises(Forbidden):self.dependency(captured[0])

    def test_real_ref_kind_instance_and_revision_owner(self):
        ref=self.ref(self.f.expected['memory_revision_id'],1)
        self.assertIs(self.adapter.validate_ref(ref,version_owner=self.f.expected['memory_id']),ref)
        for changed in [dict(ref,instance_id=identifier()),dict(ref,kind='tl_content_revision'),dict(ref,revision=sl(2,'known'))]:
            with self.assertRaises((ContractError,Forbidden,Conflict)):self.adapter.validate_ref(changed)
        with self.assertRaises(Conflict):self.adapter.validate_ref(ref,version_owner=self.activity)

    def test_corrupt_or_missing_artifact_never_returns_empty_success(self):
        row=self.s.row('artifacts',self.art);path=self.s.root/'blobs'/row['storage_ref'];original=path.read_bytes()
        path.write_bytes(b'corruption')
        with self.assertRaises(ContractError):self.adapter.read_artifact(self.art)
        path.write_bytes(original);path.unlink()
        with self.assertRaises(ContractError):self.adapter.read_artifact(self.art)
        path.write_bytes(original)

    def test_symlink_artifact_denied_without_touching_external_file(self):
        row=self.s.row('artifacts',self.art);path=self.s.root/'blobs'/row['storage_ref'];original=path.read_bytes()
        outside=Path(self.tmp.name)/'outside';outside.write_bytes(original);path.unlink();path.symlink_to(outside)
        with self.assertRaises(ContractError):self.adapter.read_artifact(self.art)
        self.assertEqual(outside.read_bytes(),original);path.unlink();path.write_bytes(original)

    def test_strict_json_duplicate_keys_rejected_even_with_valid_digest(self):
        raw=b'{"a":1,"a":2}';digest=hashlib.sha256(raw).hexdigest();(self.s.root/'blobs'/digest).write_bytes(raw)
        with self.s.tx():key=self.s.insert('artifacts',hash=digest,size=len(raw),media_type='application/json',storage_ref=digest,retention_class='instance')
        with self.assertRaises(ContractError):self.adapter.read_artifact(key)

    def test_named_artifact_structure_rejected_before_write(self):
        def callback(tx):tx.put_artifact({},'Scope');return self.response()
        with self.assertRaises(ContractError):self.execute(callback)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_command').fetchone()[0],0)

    def test_missing_referenced_blob_rejects_whole_command(self):
        def callback(tx):
            key=tx.put_artifact({'synthetic':'temporary'});row=self.s.row('artifacts',key);(self.s.root/'blobs'/row['storage_ref']).unlink()
            tx.insert('tl_dependency',consumer_ref_id=self.activity,source_ref_id=self.activity,relation='read',purpose='learn',expected_epoch=0,field_path='/missing-blob',metadata_artifact_id=key)
            return self.response()
        with self.assertRaises(ContractError):self.execute(callback)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_dependency').fetchone()[0],0)

    def test_response_must_match_original_command(self):
        def callback(tx):result=self.response();result['command_id']=identifier();return result
        with self.assertRaises(ContractError):self.execute(callback)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_command').fetchone()[0],0)

if __name__=='__main__':unittest.main()
