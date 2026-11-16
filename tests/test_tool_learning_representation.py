"""IM09 synthetic M04 leases, deterministic bodies and atomic C2."""
import copy
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc
from digital_life.domain import tool_learning_contract as c
from digital_life.application.learning.representation import ToolLearningRepresentation,RepresentationAuthority
from digital_life.application.learning.eligibility import slot,ref
from digital_life.infrastructure.persistence.tool_learning_store import StorageGrant
from tests import test_tool_learning_acceptance as acceptance
from tests.test_tool_learning_invalidation import MechanicalEligibility


class Channel:
    """Intentionally opaque and non-JSON-serializable authenticated fixture."""
    pass


class MechanicalRepresentation(RepresentationAuthority):
    def __init__(self):self.channels={};self.hook=None;self.retention_hook=None
    def verify(self,entry,operation,request,instance_id,stage):
        if not isinstance(entry,Channel):raise Forbidden('no authenticated synthetic channel')
        return StorageGrant('M04',frozenset(('tl_handoff','tl_representation','tl_representation_head','tl_group','tl_dependency')))
    def project_response(self,entry,operation,request,response,instance_id,stage):return response
    def verify_handoff(self,entry,operation,request,context,stage):
        if not isinstance(entry,Channel) or self.channels.get(request['payload']['worker']['id']) is not entry:raise Forbidden('worker channel mismatch')
        if self.hook:self.hook(stage,request,context)
    def verify_read_accounting(self,*args):return None
    def verify_retention(self,*args):
        if self.retention_hook:self.retention_hook()
    def verify_group(self,*args):return None
    def resolve_stage_entry(self,entry,request,stage):
        channel=self.channels.get(stage['channel_binding']['worker']['id'])
        if channel is None:raise Forbidden('stage worker no longer authenticated')
        return channel


class RepresentationTests(unittest.TestCase):
    def setUp(self):
        self.case=acceptance.AcceptanceTests()
        original_prepare=acceptance.observation.ObservationTests.prepare
        def prepare_three_attempts(obs):
            obs.request['budget']['max_attempts']=3
            return original_prepare(obs)
        # Predeclare the synthetic source cap before C0, never enlarge a live account.
        with patch.object(acceptance.observation.ObservationTests,'prepare',prepare_three_attempts):self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.policy();self.case.review();self.decision=self.case.decision();self.s=self.case.s;self.db=self.s.db
        self.authority=MechanicalRepresentation();self.entry=Channel();self.worker=copy.deepcopy(self.case.request['principal']['actor']);self.authority.channels[self.worker['id']]=self.entry
        self.service=ToolLearningRepresentation(self.s,self.authority,MechanicalEligibility())
        self.request=copy.deepcopy(self.case.request);self.request.update(command_id=identifier(),idempotency_key=identifier());self.request['principal'].update(module='M04',purpose='represent')
        self.request['payload']={'handoff':copy.deepcopy(self.decision['handoff_refs'][0]),'expected_generation':0,'worker':self.worker,'lease_seconds':120}
    def claim(self):return self.service.claim(self.entry,self.request)
    def build(self):
        self.claimed=self.claim();self.representation=self.service.build(self.entry,self.request,self.claimed);return self.representation
    def publish_request(self):
        if not hasattr(self,'representation'):self.build()
        request=copy.deepcopy(self.request);request.update(command_id=identifier(),idempotency_key=identifier());request['payload']={'handoff':self.request['payload']['handoff'],'lease_generation':self.claimed['current']['value']['epoch'],'worker':self.worker,'representation':copy.deepcopy(self.representation)};return request
    def test_claim_build_publish_fixed_version(self):
        request=self.publish_request();response=self.service.publish(self.entry,request);self.assertEqual(response['disposition'],'applied')
        row=self.s.row('tl_handoff',request['payload']['handoff']['id']);self.assertEqual(row['state'],'published');self.assertIsNone(row['lease_worker_id']);self.assertIsNone(row['lease_expires_at'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],1)
        c.validate('Representation',self.representation)
    def revoke(self,kind='revoke'):
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        from tests.test_tool_learning_invalidation import MechanicalInvalidation
        request=copy.deepcopy(self.request);request.update(command_id=identifier(),idempotency_key=identifier());request['principal'].update(module='M12',purpose='erase' if kind=='erase' else 'propagate')
        source=copy.deepcopy(self.case.product['body']['claims'][0]['evidence'][0]['source']);scope=copy.deepcopy(self.case.product['body']['claims'][0]['scope'])
        request['payload']={'change_id':identifier(),'kind':kind,'source':{'object':source,'revision':1,'epoch':0},'replacement':slot(),'affected_scope':scope,'subjects':[],'purposes':['represent'],'expected_epoch':0,'evidence':copy.deepcopy(self.case.product['body']['claims'][0]['evidence']),'erase_scope':slot(ref(self.s,self.case.obs.base.f.expected['policy_id'])) if kind=='erase' else slot()}
        ToolLearningInvalidation(self.s,MechanicalInvalidation()).apply('mechanical-im06',request)
    def group_setup(self):
        case=acceptance.AcceptanceTests();case.setUp();self.addCleanup(case.doCleanups);case.group();response=case.decide();self.case=case;self.s=case.s;self.db=case.db
        self.authority=MechanicalRepresentation();self.service=ToolLearningRepresentation(self.s,self.authority,MechanicalEligibility());self.entries=[Channel(),Channel()]
        actors=[ref(self.s,self.s.config()['self_actor']),ref(self.s,self.s.config()['controller'])];self.group_claims=[]
        for index,item in enumerate(response['result_refs']):
            decision=self.s.read_artifact(self.s.row('tl_decision',item['id'])['decision_artifact_id']);request=copy.deepcopy(case.request);request.update(command_id=identifier(),idempotency_key=identifier());request['principal'].update(module='M04',purpose='represent');request['payload']={'handoff':decision['handoff_refs'][0],'expected_generation':0,'worker':actors[index],'lease_seconds':120};self.group_claims.append(request);self.authority.channels[actors[index]['id']]=self.entries[index]
        self.request=self.group_claims[0];self.entry=self.entries[0];return response
    def group_publish_request(self,index):
        request=self.group_claims[index];channel=self.entries[index];claimed=self.service.claim(channel,request);representation=self.service.build(channel,request,claimed)
        result=copy.deepcopy(request);result.update(command_id=identifier(),idempotency_key=identifier());result['payload']={'handoff':request['payload']['handoff'],'worker':request['payload']['worker'],'lease_generation':claimed['current']['value']['epoch'],'representation':representation};return result
    def test_default_authority_and_unknown_worker_channel_reject(self):
        with self.assertRaises(Forbidden):ToolLearningRepresentation(self.s).claim(self.entry,self.request)
        with self.assertRaises(Forbidden):self.service.claim(Channel(),self.request)
    def test_mutable_response_token_does_not_fake_immutable_registry(self):
        before=self.db.execute('SELECT count(*) FROM object_revision_registry').fetchone()[0];response=self.claim();token=response['current']['value'];self.assertEqual((token['revision'],token['epoch']),(1,1))
        self.assertEqual(before,self.db.execute('SELECT count(*) FROM object_revision_registry').fetchone()[0])
        bound=copy.deepcopy(token['object']);bound['revision']=slot(1)
        with self.assertRaises(Conflict):self.service.storage.validate_ref(bound)
    def test_claim_generation_and_active_lease_are_exact(self):
        response=self.claim();self.request.update(command_id=identifier(),idempotency_key=identifier())
        with self.assertRaises(Conflict):self.claim()
        self.request['payload']['expected_generation']=1
        with self.assertRaises(Conflict):self.claim()
        self.assertEqual(self.s.row('tl_handoff',self.request['payload']['handoff']['id'])['attempts'],1)
    def test_expired_lease_reclaim_changes_generation_and_rejects_old_worker(self):
        self.request['payload']['lease_seconds']=1;first=self.claim();old=self.service.build(self.entry,self.request,first)
        row=self.s.row('tl_handoff',self.request['payload']['handoff']['id']);self.service.clock=lambda:row['lease_expires_at']
        original=copy.deepcopy(self.request);self.request.update(command_id=identifier(),idempotency_key=identifier());self.request['payload'].update(expected_generation=1,lease_seconds=120);second=self.claim();self.assertEqual(second['current']['value']['epoch'],2)
        bad=copy.deepcopy(original);bad.update(command_id=identifier(),idempotency_key=identifier());bad['payload']={'handoff':original['payload']['handoff'],'worker':self.worker,'lease_generation':1,'representation':old}
        with self.assertRaises(Conflict):self.service.publish(self.entry,bad)
    def test_claim_replay_and_publish_replay_do_not_add_versions(self):
        response=self.claim();self.assertEqual(response,self.claim());self.representation=self.service.build(self.entry,self.request,response);self.claimed=response
        request=self.publish_request();first=self.service.publish(self.entry,request);self.assertEqual(first,self.service.publish(self.entry,request));self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],1)
    def test_changed_stage_or_command_meaning_conflicts(self):
        request=self.publish_request();self.service.publish(self.entry,request);request['payload']['representation']['limitations'].append('caller adds a new statement')
        with self.assertRaises(Conflict):self.service.publish(self.entry,request)
    def test_claim_final_callback_crossing_new_lease_refuses(self):
        self.request['payload']['lease_seconds']=1
        def cross(stage,request,context):
            if stage=='commit':self.service.clock=lambda:context['handoff']['lease_expires_at']
        self.authority.hook=cross
        with self.assertRaises(Conflict):self.claim()
        self.assertEqual(self.s.row('tl_handoff',self.request['payload']['handoff']['id'])['state'],'pending')
    def test_publish_final_callback_crossing_lease_rolls_back(self):
        self.request['payload']['lease_seconds']=1;request=self.publish_request();expiry=self.s.row('tl_handoff',request['payload']['handoff']['id'])['lease_expires_at']
        self.authority.hook=lambda stage,request,context:setattr(self.service,'clock',lambda:expiry) if stage=='commit' else None
        with self.assertRaises(Conflict):self.service.publish(self.entry,request)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],0);self.assertEqual(self.s.row('tl_handoff',request['payload']['handoff']['id'])['state'],'leased')
    def test_semantically_stronger_claim_and_changed_scope_rejected(self):
        request=self.publish_request();request['payload']['representation']['claims'][0]['value']=slot(999)
        with self.assertRaises(Conflict):self.service.publish(self.entry,request)
        request=self.publish_request();request['payload']['representation']['scope']['unit']=slot('other')
        with self.assertRaises(Conflict):self.service.publish(self.entry,request)
    def test_body_digest_and_rendered_bytes_both_required(self):
        request=self.publish_request();artifact=self.s.artifact('world inventory is always999',media_type='text/plain');request['payload']['representation'].update(body_artifact=ref(self.s,artifact),body_digest={'algorithm':'sha256','hex':self.s.row('artifacts',artifact)['hash']})
        with self.assertRaises(ContractError):self.service.publish(self.entry,request)
    def test_build_only_body_is_reachable_for_erasure(self):
        body=self.build()['body_artifact']['id'];self.assertTrue(self.service.read_built(self.entry,self.request,self.claimed,ref(self.s,body)));deps=self.db.execute("SELECT * FROM tl_dependency WHERE consumer_ref_id=? AND relation='delete'",(body,)).fetchall();self.assertTrue(deps)
        self.revoke('erase');targets=[self.s.read_artifact(row['targets_artifact_id']) for row in self.db.execute('SELECT * FROM tl_propagation')];self.assertTrue(all(body in [x['id'] for x in target['targets']] for target in targets))
        with self.assertRaises((Forbidden,Conflict)):self.service.build(self.entry,self.request,self.claimed)
        with self.assertRaises((Forbidden,Conflict)):self.service.read_built(self.entry,self.request,self.claimed,ref(self.s,body))
    def test_f1_after_build_blocks_publish_and_no_ready_artifact(self):
        request=self.publish_request();self.revoke()
        with self.assertRaises((Forbidden,Conflict)):self.service.publish(self.entry,request)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],0)
    def test_retention_callback_nested_control_change_rejects_without_stage(self):
        request=self.publish_request();once=[]
        def invalidate():
            if not once:once.append(1);self.revoke('erase')
        self.authority.retention_hook=invalidate
        with self.assertRaises((Forbidden,Conflict)):self.service.publish(self.entry,request)
        self.assertEqual(self.db.execute("SELECT count(*) FROM runtime_events WHERE source='tl.representation.stage'").fetchone()[0],0)
    def test_c2_fault_rolls_back_representation_head_receipt_and_command(self):
        request=self.publish_request();original=self.service._dependency
        def fault(*args):original(*args);raise OSError('synthetic after dependency')
        with patch.object(self.service,'_dependency',fault):
            with self.assertRaises(OSError):self.service.publish(self.entry,request)
        for table in ('tl_representation','tl_representation_head'):self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        self.assertEqual(self.s.row('tl_handoff',request['payload']['handoff']['id'])['state'],'leased')
    def test_group_two_opaque_worker_channels_publish_only_complete_group(self):
        self.group_setup();first=self.group_publish_request(0);response=self.service.publish(self.entries[0],first);self.assertEqual(response['disposition'],'deferred');self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],0)
        stage=self.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='tl.representation.stage'").fetchone()[0];self.assertNotIn('entry',self.s.read_artifact(stage));self.assertTrue(self.db.execute('SELECT count(*) FROM tl_dependency WHERE consumer_ref_id=?',(stage,)).fetchone()[0])
        second=self.group_publish_request(1);response=self.service.publish(self.entries[1],second);self.assertEqual(len(response['result_refs']),2);self.assertEqual(self.db.execute('SELECT state FROM tl_group').fetchone()[0],'ready');self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],2)
    def test_group_stage_then_f1_cannot_read_or_publish_remaining(self):
        self.group_setup();first=self.group_publish_request(0);self.service.publish(self.entries[0],first);stage=self.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='tl.representation.stage'").fetchone()[0]
        second=self.group_publish_request(1);self.revoke('erase')
        with self.assertRaises((Forbidden,Conflict)):self.service.publish(self.entries[1],second)
        context_scope=self.case.product['body']['claims'][0]['scope'];token={'object':ref(self.s,stage),'revision':0,'epoch':0}
        with self.assertRaises((Forbidden,Conflict)):self.service._qualify(self.entries[0],first,token,context_scope,'stage_read')
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],0);self.assertEqual(self.db.execute('SELECT state FROM tl_group').fetchone()[0],'pending')
    def test_group_second_write_fault_cannot_half_publish(self):
        self.group_setup();first=self.group_publish_request(0);self.service.publish(self.entries[0],first);second=self.group_publish_request(1);original=self.service._write;calls=[]
        # Fail after one real member was written, while still in the same C2.
        def fail_second(*args):
            original(*args);calls.append(1)
            if len(calls)==2:raise OSError('second C2 member failed')
        with patch.object(self.service,'_write',fail_second):
            with self.assertRaises(OSError):self.service.publish(self.entries[1],second)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],0);self.assertEqual(self.db.execute('SELECT state FROM tl_group').fetchone()[0],'pending')

    def test_stopped_instance_and_cancelled_request_never_claim(self):
        self.request['control']['cancelled']=True
        with self.assertRaises(Forbidden):self.claim()
        self.request['control']['cancelled']=False;self.case.obs.base.f.control.stop('synthetic IM09 stop')
        with self.assertRaises(Forbidden):self.claim()
        self.assertEqual(self.s.row('tl_handoff',self.request['payload']['handoff']['id'])['state'],'pending')
    def test_obsolete_content_head_cannot_publish_late_representation(self):
        request=self.publish_request();token={'object':self.decision['content_ref']['value'],'revision':1,'epoch':0}
        self.case.existing(token);self.case.request.update(command_id=identifier(),idempotency_key=identifier());self.case.review(native=token);self.case.decision()
        with self.assertRaises(Conflict):self.service.publish(self.entry,request)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],0)
    def test_mutable_token_wrong_current_row_or_generation_is_rejected(self):
        original=self.service._response
        def forged(*args,**kwargs):
            result=original(*args,**kwargs);result['current']['value']['revision']=999;return result
        with patch.object(self.service,'_response',forged):
            with self.assertRaises(Conflict):self.claim()
        self.assertEqual(self.s.row('tl_handoff',self.request['payload']['handoff']['id'])['state'],'pending')
    def test_group_uses_reauthenticated_current_member_channels(self):
        self.group_setup();first=self.group_publish_request(0);self.service.publish(self.entries[0],first);second=self.group_publish_request(1);del self.authority.channels[self.group_claims[0]['payload']['worker']['id']]
        with self.assertRaises(Forbidden):self.service.publish(self.entries[1],second)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],0)
    def test_group_expired_first_stage_cannot_use_newer_final_worker_lease(self):
        self.group_setup();self.group_claims[0]['payload']['lease_seconds']=1;first=self.group_publish_request(0);self.service.publish(self.entries[0],first);expiry=self.s.row('tl_handoff',first['payload']['handoff']['id'])['lease_expires_at'];second=self.group_publish_request(1);self.service.clock=lambda:expiry
        with self.assertRaises(Conflict):self.service.publish(self.entries[1],second)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],0)
    def test_known_false_zero_null_and_unknown_slots_are_rendered_in_full(self):
        for value in (False,0,None):
            case=RepresentationTests();case.setUp()
            try:
                case.case.obs.value(value)
                def mutate(product):product['body']['claims'][0].update(value={'status':'known','value':value,'reason_code':'source_reported_null' if value is None else 'none','reason':'source reports null' if value is None else '','basis_refs':[]},evidence=[copy.deepcopy(case.case.obs.source)])
                case.case.replace_product(mutate);case.case.request.update(command_id=identifier(),idempotency_key=identifier());case.case.review();decision=case.case.decision();case.request['payload']['handoff']=decision['handoff_refs'][0]
                representation=case.build();actual=representation['claims'][0]['value'];self.assertIs(type(actual['value']),type(value));self.assertEqual(actual['status'],'known')
                body=case.service.storage.read_artifact(representation['body_artifact']['id']);self.assertIn('未知/冲突：'.encode(),body);self.assertIn('证据定位：'.encode(),body)
            finally:case.doCleanups()
    def test_series_revision_registration_is_separate_from_content_revision(self):
        request=self.publish_request();self.service.publish(self.entry,request);row=self.s.row('tl_representation',self.representation['id']);registered=self.db.execute('SELECT object_id,revision_no FROM object_revision_registry WHERE id=?',(row['id'],)).fetchone();self.assertEqual((registered['object_id'],registered['revision_no']),(row['series_id'],1));self.assertNotEqual(registered['object_id'],self.representation['content_ref']['id'])
    def test_build_and_stage_require_real_retention_and_meter_ports(self):
        class NoRead(MechanicalRepresentation):verify_read_accounting=RepresentationAuthority.verify_read_accounting
        authority=NoRead();authority.channels=self.authority.channels
        with self.assertRaises(Forbidden):ToolLearningRepresentation(self.s,authority,MechanicalEligibility()).claim(self.entry,self.request)
        response=self.claim();self.authority.verify_retention=lambda *args:True
        with self.assertRaises(Forbidden):self.service.build(self.entry,self.request,response)

    def test_new_content_version_advances_same_series_without_reaccepting_old(self):
        first_request=self.publish_request();self.service.publish(self.entry,first_request);old=copy.deepcopy(self.representation);token={'object':self.decision['content_ref']['value'],'revision':1,'epoch':0}
        self.case.existing(token);self.case.request.update(command_id=identifier(),idempotency_key=identifier());self.case.review(native=token);second=self.case.decision()
        self.request.update(command_id=identifier(),idempotency_key=identifier());self.request['payload']['handoff']=second['handoff_refs'][0];self.claimed=self.claim();self.representation=self.service.build(self.entry,self.request,self.claimed);request=self.publish_request();self.service.publish(self.entry,request)
        self.assertEqual(self.representation['series_ref'],old['series_ref']);self.assertEqual(self.representation['representation_no'],2);self.assertEqual(self.representation['content_revision']['revision'],2);self.assertEqual(self.s.row('tl_representation',old['id'])['state'],'superseded');self.assertEqual(self.db.execute('SELECT count(*) FROM tl_decision').fetchone()[0],2)

    def test_later_member_callback_cannot_expire_already_checked_first_member(self):
        self.group_setup();self.group_claims[0]['payload']['lease_seconds']=1;first=self.group_publish_request(0);self.service.publish(self.entries[0],first);expiry=self.s.row('tl_handoff',first['payload']['handoff']['id'])['lease_expires_at'];second=self.group_publish_request(1)
        def cross(stage,request,context):
            if stage=='commit_member' and context['handoff']['id']==second['payload']['handoff']['id']:self.service.clock=lambda:expiry
        self.authority.hook=cross
        with self.assertRaises(Conflict):self.service.publish(self.entries[1],second)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],0);self.assertEqual(self.db.execute('SELECT state FROM tl_group').fetchone()[0],'pending')
    def test_final_callback_cannot_rebind_consumed_generation_or_receipt(self):
        request=self.publish_request();done=[]
        def mutate(stage,request,context):
            if stage=='commit' and not done:
                done.append(1);self.db.execute('UPDATE tl_handoff SET lease_generation=lease_generation+1,row_revision=row_revision+1 WHERE id=?',(context['handoff']['id'],))
        self.authority.hook=mutate
        with self.assertRaises(Conflict):self.service.publish(self.entry,request)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_representation').fetchone()[0],0);self.assertEqual(self.s.row('tl_handoff',request['payload']['handoff']['id'])['lease_generation'],1)


if __name__=='__main__':unittest.main()
