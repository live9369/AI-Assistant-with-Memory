"""IM06 F1 mechanics on new synthetic fixtures, never real authorization."""
import copy
import json
import threading
import time
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc
from digital_life.infrastructure.persistence.tool_learning_store import StorageGrant,CommitUnknown
from digital_life.application.learning.invalidation import ToolLearningInvalidation,InvalidationAuthority,DOMAINS
from digital_life.application.learning.eligibility import ToolLearningEligibility,EligibilityAuthority,scope_key,slot,ref
from tests.test_tool_learning_products import scope,envelope


class MechanicalInvalidation(InvalidationAuthority):
    def __init__(self):self.deny=False;self.plan=None;self.hook=None
    def verify(self,entry,operation,request,instance_id,stage):
        if entry!='mechanical-im06' or self.deny:raise Forbidden('synthetic authority denial')
        return StorageGrant('M12',frozenset(('tl_change','tl_source_epoch','tl_barrier','tl_propagation','tl_input_dependency')))
    def project_response(self,entry,operation,request,response,instance_id,stage):return response
    def verify_change(self,entry,request,stage):
        if self.deny:raise Forbidden('synthetic M12 denial')
        if self.hook:self.hook(stage)
    def verify_version(self,entry,request,token,stage):return None
    def propagation_plan(self,entry,request):return self.plan


class MechanicalEligibility(EligibilityAuthority):
    def __init__(self):self.deny=False;self.hook=None;self.exempt_recipient=None
    def verify(self,entry,principal,token,scope,purpose,recipient,stage):
        if self.deny:raise Forbidden('synthetic qualification denial')
        if self.hook:self.hook(stage)
    def verify_version(self,*args):return None
    def verify_registration(self,*args):return None
    def verify_callback(self,*args):return None
    def barrier_applies(self,entry,principal,barrier,payload,scope,purpose,recipient):
        return False if recipient['id']==self.exempt_recipient else None


class F1Tests(unittest.TestCase):
    def setUp(self):
        # Reuse the already tested C0 constructor, not another runtime path.
        from tests.test_tool_learning_work import WorkTests
        self.base=WorkTests();self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.s=self.base.s;self.db=self.s.db;self.f=self.base.f
        admitted=self.base.admit();self.work_id=self.base.work_id(admitted)
        self.work=self.s.row('tl_work',self.work_id)
        self.budget=json.loads(self.s.row('activities',self.work['learning_activity_id'])['budget_json'])['budget']
        self.principal=copy.deepcopy(self.base.request['principal']);self.principal.update(module='M12',purpose='propagate')
        self.source=ref(self.s,self.f.expected['memory_id'])
        self.token={'object':self.source,'revision':1,'epoch':0}
        self.scope=scope();self.scope['subject']=slot(ref(self.s,self.f.expected['self_actor']))
        self.authority=MechanicalInvalidation();self.service=ToolLearningInvalidation(self.s,self.authority)
        self.elig_auth=MechanicalEligibility();self.elig=ToolLearningEligibility(self.s,self.elig_auth)
        self.consumer=ref(self.s,self.work['learning_activity_id'])
        self.query_principal=copy.deepcopy(self.principal);self.query_principal['purpose']='learn'

    def request(self,kind='revoke',expected=0):
        payload={'change_id':identifier(),'kind':kind,'source':copy.deepcopy(self.token),'replacement':slot(),
                 'affected_scope':copy.deepcopy(self.scope),'subjects':[],'purposes':['learn'],'expected_epoch':expected,
                 'evidence':[copy.deepcopy(self.base.request['payload']['source'])],'erase_scope':slot()}
        payload['source']['epoch']=expected
        req=envelope(payload);req.update(instance_id=self.s.instance_id,command_id=identifier(),idempotency_key=identifier(),principal=copy.deepcopy(self.principal),work_ref=slot(ref(self.s,self.work_id)),budget=copy.deepcopy(self.budget),control=copy.deepcopy(self.base.request['control']))
        if kind=='erase':req['principal']['purpose']='erase';req['payload']['erase_scope']=slot(ref(self.s,self.f.expected['policy_id']))
        return req
    def apply(self,request=None):return self.service.apply('mechanical-im06',request or self.request())
    def check(self,token=None,scope_value=None,principal=None):
        p=principal or self.query_principal
        return self.elig.check('mechanical-im06',p,token or self.token,scope_value or self.scope,p['purpose'],p['recipient'])
    def dependency(self,consumer=None,source=None,token=None,scope_value=None,field='/test'):
        consumer=consumer or self.consumer;source=source or self.source
        dep={'target':source,'relation':'read','expected':token or self.token,'consumer_purpose':'learn'}
        return self.elig.register_dependency('mechanical-im06',self.query_principal,consumer,dep,field,scope_value or self.scope)

    def test_f1_atomic_nine_pending_obligations_and_epoch(self):
        self.apply();self.assertEqual(self.elig.current_epoch(self.source,self.scope),1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_change').fetchone()[0],1)
        rows=self.db.execute('SELECT * FROM tl_propagation').fetchall()
        self.assertEqual({r['domain'] for r in rows},set(DOMAINS));self.assertEqual(len(rows),9)
        self.assertTrue(all(r['state']=='pending' for r in rows))
        self.assertTrue(all(self.s.read_artifact(r['coverage_artifact_id'])['state']=='unknown' for r in rows))
        self.assertTrue(all(self.s.read_artifact(r['targets_artifact_id'])['scan_pending'] for r in rows))

    def test_static_source_zero_is_preserved_without_fake_revision_registration(self):
        request=self.request()
        source_activity=self.s.row('activities',self.base.source_activity)
        static=ref(self.s,source_activity['trigger_event_id'])
        request['payload']['source']={'object':static,'revision':0,'epoch':0}
        before=self.db.execute('SELECT count(*) FROM object_revision_registry WHERE instance_id=? AND object_id=?',(self.s.instance_id,static['id'])).fetchone()[0]
        self.assertEqual(before,0)
        response=self.apply(request)
        self.assertEqual(response['current']['status'],'not_applicable')
        self.assertIn('qualification epochs',response['current']['reason'])
        change=self.db.execute('SELECT * FROM tl_change WHERE id=?',(request['payload']['change_id'],)).fetchone()
        payload=self.s.read_artifact(change['payload_artifact_id'])
        self.assertEqual(payload['source']['revision'],0)
        self.assertEqual(payload['source']['object'],static)
        self.assertEqual(self.elig.current_epoch(static,self.scope),1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM object_revision_registry WHERE instance_id=? AND object_id=?',(self.s.instance_id,static['id'])).fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT source_epoch FROM tl_barrier WHERE change_id=?',(change['id'],)).fetchone()[0],1)

    def test_default_authority_and_untrusted_change_are_denied(self):
        with self.assertRaises(Forbidden):ToolLearningInvalidation(self.s).apply('x',self.request())
        self.authority.deny=True
        with self.assertRaises(Forbidden):self.apply()
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_barrier').fetchone()[0],0)

    def test_same_event_new_command_reuses_without_epoch_increment(self):
        request=self.request();first=self.apply(request);second=copy.deepcopy(request);second.update(command_id=identifier(),idempotency_key=identifier())
        result=self.apply(second);self.assertEqual(result['disposition'],'reused');self.assertEqual(first['result_refs'],result['result_refs'])
        self.assertEqual(self.elig.current_epoch(self.source,self.scope),1)

    def test_changed_event_payload_and_old_epoch_rejected(self):
        request=self.request();self.apply(request)
        altered=copy.deepcopy(request);altered.update(command_id=identifier(),idempotency_key=identifier());altered['payload']['purposes']=['represent']
        with self.assertRaises(Conflict):self.apply(altered)
        with self.assertRaises(Conflict):self.apply(self.request())

    def test_multiple_reasons_never_resolve_each_other(self):
        self.apply();self.apply(self.request('conflict',1))
        self.assertEqual({r['kind'] for r in self.db.execute('SELECT * FROM tl_barrier')},{'revoke','conflict'})
        self.assertTrue(all(r['state']=='active' for r in self.db.execute('SELECT * FROM tl_barrier')))
        self.assertEqual(self.elig.current_epoch(self.source,self.scope),2)

    def test_authorized_protective_f1_under_stop_and_wake_lock(self):
        self.f.control.stop('protective-test');(self.s.root/'WAKE_DISABLED').write_text('test-only lock')
        self.apply();self.assertEqual(self.db.execute('SELECT count(*) FROM tl_barrier').fetchone()[0],1)
        with self.assertRaises(Forbidden):self.check()
        self.assertTrue((self.s.root/'WAKE_DISABLED').exists())

    def test_input_qualification_is_invalidated_with_root_barrier(self):
        dep=self.dependency();ident=self.elig.register_input('mechanical-im06',self.query_principal,self.consumer,dep)
        self.apply();self.assertEqual(self.s.row('tl_input_dependency',ident)['retention_state'],'blocked')

    def test_erase_marks_pending_without_clearing_bytes_or_other_states(self):
        dep=self.dependency();ident=self.elig.register_input('mechanical-im06',self.query_principal,self.consumer,dep,{'algorithm':'sha256','hex':'a'*64})
        self.apply(self.request('erase'))
        row=self.s.row('tl_input_dependency',ident);self.assertEqual(row['retention_state'],'erase_pending');self.assertEqual(row['body_digest'],'a'*64)
        self.apply(self.request('correct',1));self.assertEqual(self.s.row('tl_input_dependency',ident)['retention_state'],'erase_pending')

    def test_failure_each_f1_table_rolls_back_entire_change(self):
        from digital_life.infrastructure.persistence.tool_learning_store import OwnedTransaction
        original=OwnedTransaction.insert
        for table in ('tl_change','tl_source_epoch','tl_barrier','tl_propagation'):
            def fail(tx,target,**fields):
                if target==table:raise RuntimeError('injected '+table)
                return original(tx,target,**fields)
            with self.subTest(table=table),patch.object(OwnedTransaction,'insert',fail):
                with self.assertRaises(RuntimeError):self.apply()
            self.assertEqual(self.db.execute('SELECT count(*) FROM tl_change').fetchone()[0],0)
            self.assertEqual(self.db.execute('SELECT count(*) FROM tl_source_epoch').fetchone()[0],0)
            self.assertEqual(self.db.execute('SELECT count(*) FROM tl_barrier').fetchone()[0],0)
            self.assertEqual(self.db.execute('SELECT count(*) FROM tl_propagation').fetchone()[0],0)

    def test_partial_scan_still_persists_protective_barrier(self):
        self.dependency();self.service=ToolLearningInvalidation(self.s,self.authority,max_nodes=1)
        self.apply();self.assertEqual(self.db.execute('SELECT count(*) FROM tl_barrier').fetchone()[0],1)
        self.assertTrue(all(self.s.read_artifact(r[0])['state']=='partial' for r in self.db.execute('SELECT coverage_artifact_id FROM tl_propagation')))
        current=copy.deepcopy(self.token);current['epoch']=1
        with self.assertRaises(Forbidden):self.check(current)

    def test_commit_ack_unknown_is_reconciled_not_redispatched(self):
        request=self.request();original=self.service.storage._commit
        def ambiguous():original();raise OSError('ack lost')
        with patch.object(self.service.storage,'_commit',ambiguous):
            with self.assertRaises(CommitUnknown):self.apply(request)
        result=self.service.storage.lookup_command('mechanical-im06','apply_invalidation',request)
        self.assertEqual(result['state'],'committed');self.assertEqual(self.elig.current_epoch(self.source,self.scope),1)

    def test_scope_hash_change_cannot_bypass_active_barrier(self):
        self.apply();other=copy.deepcopy(self.scope);other['limitations'].append('another serialized scope')
        with self.assertRaises(Forbidden):self.check(scope_value=other)

    def test_unrelated_purpose_and_explicit_recipient_exemption(self):
        request=self.request();request['payload']['subjects']=[self.query_principal['recipient']];self.apply(request)
        current=copy.deepcopy(self.token);current['epoch']=1
        p=copy.deepcopy(self.query_principal);p['purpose']='history_audit'
        self.check(current,principal=p)
        p=copy.deepcopy(self.query_principal);p['recipient']=ref(self.s,self.f.expected['controller'])
        self.elig_auth.exempt_recipient=p['recipient']['id'];self.check(current,principal=p)
        with self.assertRaises(Forbidden):self.check(current)

    def test_input_recipient_exemption_is_explicit_not_inferred_from_label(self):
        dep=self.dependency();a=self.elig.register_input('x',self.query_principal,self.consumer,dep)
        principal=copy.deepcopy(self.query_principal);principal['recipient']=ref(self.s,self.f.expected['controller'])
        b=self.elig.register_input('x',principal,self.consumer,dep)
        exempt=principal['recipient']['id']
        class Specific(MechanicalInvalidation):
            def barrier_applies(_,entry,request,barrier,payload,context):return False if context['recipient']['id']==exempt else None
        self.service=ToolLearningInvalidation(self.s,Specific());self.apply()
        self.assertEqual(self.s.row('tl_input_dependency',a)['retention_state'],'blocked')
        self.assertEqual(self.s.row('tl_input_dependency',b)['retention_state'],'allowed')

    def test_oversized_target_plan_is_partial_not_root_failure(self):
        self.authority.plan={'M04':[self.source,self.source,self.source]}
        self.service=ToolLearningInvalidation(self.s,self.authority,max_rows=1);self.apply()
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_barrier').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_propagation').fetchone()[0],9)
        self.assertTrue(all(self.s.read_artifact(r[0])['state']=='partial' for r in self.db.execute('SELECT coverage_artifact_id FROM tl_propagation')))

    def test_unavailable_plan_does_not_prevent_root_protection(self):
        def unavailable(*args):raise OSError('deferred owner scan unavailable')
        self.authority.propagation_plan=unavailable
        self.apply();self.assertEqual(self.db.execute('SELECT count(*) FROM tl_barrier').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_propagation').fetchone()[0],9)

    def test_authority_revoked_at_commit_rolls_back(self):
        def revoke(stage):
            if stage=='commit':self.authority.deny=True;raise Forbidden('revoked during commit')
        self.authority.hook=revoke
        with self.assertRaises(Forbidden):self.apply()
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_barrier').fetchone()[0],0)
        self.assertEqual(self.elig.current_epoch(self.source,self.scope),0)

    def test_input_update_failure_rolls_back_root_and_obligations(self):
        dep=self.dependency();ident=self.elig.register_input('x',self.query_principal,self.consumer,dep)
        from digital_life.infrastructure.persistence.tool_learning_store import OwnedTransaction
        original=OwnedTransaction.cas_update
        def fail(tx,table,*args,**kwargs):
            if table=='tl_input_dependency':raise RuntimeError('injected input write failure')
            return original(tx,table,*args,**kwargs)
        with patch.object(OwnedTransaction,'cas_update',fail):
            with self.assertRaises(RuntimeError):self.apply()
        self.assertEqual(self.s.row('tl_input_dependency',ident)['retention_state'],'allowed')
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_barrier').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_propagation').fetchone()[0],0)

    def test_invalid_evidence_and_forged_source_revision_do_not_write(self):
        request=self.request();request['payload']['evidence'][0]['digest']['hex']='a'*64
        with self.assertRaises(ContractError):self.apply(request)
        request=self.request();request['payload']['source']['revision']=99
        with self.assertRaises((ContractError,Conflict)):self.apply(request)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_change').fetchone()[0],0)

if __name__=='__main__':unittest.main()
