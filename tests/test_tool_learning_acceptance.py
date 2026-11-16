"""IM08 synthetic C1 acceptance; mechanical ports are not real authority."""
import copy
import json
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc
from digital_life.domain import tool_learning_contract as c
from digital_life.application.learning.acceptance import ToolLearningAcceptance,AcceptanceAuthority,OWNERS
from digital_life.application.learning.eligibility import slot,ref
from digital_life.infrastructure.persistence.tool_learning_store import StorageGrant,command_fingerprint
from tests import test_tool_learning_observation as observation
from tests.test_tool_learning_invalidation import MechanicalEligibility
from tests.test_tool_learning_products import method


class MechanicalAcceptance(AcceptanceAuthority):
    def __init__(self,case):self.case=case;self.states={};self.deny=None;self.hook=None
    def verify(self,entry,operation,request,instance_id,stage):
        if entry!='synthetic-acceptance':raise Forbidden('unknown synthetic entry')
        return StorageGrant('M03',frozenset(('tl_decision','tl_content','tl_content_revision','tl_handoff','tl_group','tl_dependency')))
    def project_response(self,entry,operation,request,response,instance_id,stage):return response
    def verify_proposal_access(self,entry,request,row,stage):
        if self.deny==row['id']:raise Forbidden('member access denied')
        if self.hook:self.hook(stage)
    def source_token(self,entry,request,evidence):return {'object':copy.deepcopy(evidence['source']),'revision':1 if evidence['source']['kind']=='memory_items' else 0,'epoch':0}
    def evaluate_gate(self,entry,request,context,gate,stage):
        p=copy.deepcopy(request['principal']);p['module']=OWNERS[gate][0]
        return {'state':self.states.get(gate,'pass'),'checker':p,'method':method(),'at':utc(),'targets':[],'reason':'none','basis_refs':[]}
    def verify_read_accounting(self,*args):return None
    def verify_target_metadata(self,*args):return None
    def preserved_token(self,entry,request,preserved):return {'object':copy.deepcopy(preserved),'revision':1,'epoch':0}
    def verify_policy(self,*args):return None
    def verify_review(self,*args):return None
    def verify_group(self,*args):return None
    def verify_projection(self,*args):return None


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.obs=observation.ObservationTests();self.obs.setUp();self.addCleanup(self.obs.doCleanups)
        self.obs.assess();self.s=self.obs.s;self.db=self.s.db
        self.proposal=dict(self.db.execute("SELECT * FROM tl_product WHERE product_type='UpdateProposal'").fetchone())
        self.product=self.s.read_artifact(self.proposal['payload_artifact_id'])
        self.authority=MechanicalAcceptance(self);self.service=ToolLearningAcceptance(self.s,self.authority,MechanicalEligibility())
        self.request=copy.deepcopy(self.obs.assessment);self.request.update(command_id=identifier(),idempotency_key=identifier())
        self.request['principal'].update(module='M03',purpose='accept')
        self.request['payload']={'proposal':ref(self.s,self.proposal['id']),'review_round':0,'policy':ref(self.s,self.obs.base.f.expected['policy_id']),'review':slot(),'atomic_group':slot()}
    def policy(self):
        controller=self.s.config()['controller'];version=self.db.execute('SELECT max(version)+1 FROM policy_versions').fetchone()[0]
        profile={'contract':'TL-ACCEPT-REVIEW-1','content_kinds':['source_report'],'proposal_operations':['add','confirm','temporal_add','correct','restrict','mark_conflict'],'require_controller_review':True,'expires_at':utc(3600)}
        ident=self.s.insert('policy_versions',version=version,mode='authorization',scope={'tool_learning_acceptance':profile},effective_at=utc(-1),authority=controller)
        self.request['payload']['policy']=ref(self.s,ident);return ident
    def review(self,verdict='accept',native=None,request=None,product=None):
        request=self.request if request is None else request;product=self.product if product is None else product
        body={'contract':'TL-CONTROLLER-CONTENT-REVIEW-1','proposal':copy.deepcopy(request['payload']['proposal']),'proposal_digest':c.fingerprint(product),'review_round':request['payload']['review_round'],
            'expected':copy.deepcopy(product['body']['target']['expected']),'native_expected':slot(native),'actual_scope':copy.deepcopy(product['body']['claims'][0]['scope']),
            'policy':copy.deepcopy(request['payload']['policy']),'atomic_group':copy.deepcopy(request['payload']['atomic_group']),'verdict':verdict,'expires_at':utc(3600)}
        signal=self.s.insert('perception_signals',channel_id=self.db.execute('SELECT id FROM perception_channels LIMIT 1').fetchone()[0],source_actor_id=self.s.config()['controller'],artifact_id=self.s.artifact(body),received_at=utc())
        request['payload']['review']=slot(ref(self.s,signal));return body
    def decide(self):return self.service.decide('synthetic-acceptance',self.request)
    def decision(self,response=None):
        response=response or self.decide();row=self.s.row('tl_decision',response['result_refs'][0]['id']);return self.s.read_artifact(row['decision_artifact_id'])
    def replace_product(self,mutate):
        product=copy.deepcopy(self.product);mutate(product);c.validate('Product',product)
        # Product immutability is respected: create a different proposal.
        product['product_id']=identifier();product['processing_identity']['hex']=identifier()*2
        row=copy.deepcopy(self.proposal);row.update(id=product['product_id'],payload_artifact_id=self.s.artifact(product),processing_identity=product['processing_identity']['hex'])
        self.s.insert('tl_product',**row);self.proposal=row;self.product=product;self.request['payload']['proposal']=ref(self.s,row['id'])
    def advance_round(self):
        work=self.s.row('tl_work',self.obs.work['id'])
        self.db.execute("UPDATE tl_work SET state='awaiting_decision',phase='decide',review_round=review_round+1,row_revision=row_revision+1 WHERE id=?",(work['id'],))
        self.request.update(command_id=identifier(),idempotency_key=identifier());self.request['payload']['review_round']+=1;self.request['payload']['review']=slot()

    def test_default_authority_rejects(self):
        with self.assertRaises(Forbidden):ToolLearningAcceptance(self.s).decide('x',self.request)
    def test_missing_policy_and_review_only_candidate_no_handoff(self):
        decision=self.decision();self.assertEqual(decision['operation'],'candidate');self.assertEqual(self.db.execute('SELECT count(*) FROM tl_handoff').fetchone()[0],0)
        projection=self.service.work_projection('synthetic-acceptance',dict(self.request['principal'],module='M14'),self.request['work_ref']['value'])
        self.assertEqual((projection['target'],projection['phase']),('waiting','decide'))
        self.assertEqual(self.s.row('tl_work',self.obs.work['id'])['state'],'awaiting_decision')
    def test_accept_typed_version_handoff_and_revision_dependencies(self):
        self.policy();self.review();decision=self.decision();self.assertEqual(decision['operation'],'accept');c.validate('Decision',decision)
        revision=decision['revision_ref']['value']['id'];deps=self.db.execute('SELECT * FROM tl_dependency WHERE consumer_ref_id=?',(revision,)).fetchall()
        self.assertTrue(deps);self.assertTrue(all(self.s.read_artifact(r['metadata_artifact_id'])['consumer']['kind']=='tl_content_revision' for r in deps))
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_handoff').fetchone()[0],1)
    def test_candidate_then_new_round_accept_binds_real_native(self):
        first=self.decision();native=first['content_ref']['value'];revision=first['revision_ref']['value']['id'];self.advance_round();self.policy()
        self.review(native={'object':native,'revision':1,'epoch':0});second=self.decision()
        self.assertEqual(second['operation'],'accept');self.assertEqual(second['content_ref']['value']['id'],native['id']);self.assertEqual(second['previous']['value']['revision'],1)
        rows=self.db.execute('SELECT consumer_ref_id,relation,field_path,source_ref_id,metadata_artifact_id FROM tl_dependency WHERE consumer_ref_id IN (?,?)',(revision,second['revision_ref']['value']['id'])).fetchall()
        self.assertEqual({r['consumer_ref_id'] for r in rows},{revision,second['revision_ref']['value']['id']})
        for current in (revision,second['revision_ref']['value']['id']):
            actual=[r for r in rows if r['consumer_ref_id']==current]
            self.assertEqual({(r['relation'],r['field_path']) for r in actual},{('read','/sources/0'),('derive','/actual_proposal')})
            proposal=self.db.execute('SELECT proposal_id FROM tl_decision WHERE content_revision_id=?',(current,)).fetchone()[0]
            self.assertEqual(next(r['source_ref_id'] for r in actual if r['relation']=='derive'),proposal)
            original=self.obs.assessment['payload']['source']['source']
            read=next(r for r in actual if r['relation']=='read');self.assertEqual(read['source_ref_id'],original['id'])
            metadata=self.s.read_artifact(read['metadata_artifact_id']);self.assertEqual(metadata['consumer']['id'],current);self.assertEqual(metadata['consumer']['kind'],'tl_content_revision');self.assertEqual(metadata['dependency']['expected']['object'],original)
            self.assertFalse(any(r['source_ref_id'] in (revision,second['revision_ref']['value']['id']) for r in actual))
        self.assertEqual({r['source_ref_id'] for r in rows if r['relation']=='read'},{self.obs.assessment['payload']['source']['source']['id']})
    def test_candidate_new_round_missing_or_stale_native_binding_rejected(self):
        first=self.decision();self.advance_round();self.policy();self.review()
        with self.assertRaises(Conflict):self.decide()
        self.review(native={'object':first['content_ref']['value'],'revision':2,'epoch':0})
        with self.assertRaises(Conflict):self.decide()
    def test_each_round_once_and_changed_context_conflicts(self):
        first=self.decide();self.request.update(command_id=identifier(),idempotency_key=identifier());second=self.decide();self.assertEqual(first['result_refs'],second['result_refs'])
        self.policy()
        with self.assertRaises(Conflict):self.decide()
    def test_owner_fail_not_hidden_by_missing_review(self):
        self.authority.states['G07']='fail';d=self.decision();self.assertEqual(d['operation'],'reject');self.assertEqual(d['checks']['G07']['state'],'fail')
    def test_owner_block_not_hidden_by_missing_review(self):
        self.authority.states['G07']='blocked'
        with self.assertRaises(Forbidden):self.decide()
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_decision').fetchone()[0],0)
    def test_category_literal_match_cannot_accept_world_truth(self):
        self.replace_product(lambda p:p['body']['target'].update(content_kind='world_claim'))
        self.assertEqual(self.decision()['operation'],'reject')
    def test_explicit_local_unknown_cannot_downgrade_fail(self):
        self.replace_product(lambda p:p['body']['claims'][0].update(value={'status':'unknown','value':None,'reason_code':'not_measured','reason':'unknown','basis_refs':[]}))
        self.authority.states['G04']='fail';d=self.decision();self.assertEqual(d['checks']['G04']['state'],'fail');self.assertEqual(d['operation'],'reject')
    def test_wrong_review_scope_and_round_rejected(self):
        self.policy();self.review();self.request['payload']['review_round']=1
        with self.assertRaises(Conflict):self.decide()
    def test_no_product_read_after_source_revocation(self):
        self.authority.deny=self.proposal['id']
        with self.assertRaises(Forbidden):self.decide()
    def test_transaction_fault_rolls_back_c1(self):
        self.policy();self.review();original=self.service._dependency
        def fault(*args,**kwargs):original(*args,**kwargs);raise OSError('after dependency')
        with patch.object(self.service,'_dependency',fault):
            with self.assertRaises(OSError):self.decide()
        for table in ('tl_decision','tl_content','tl_content_revision','tl_handoff'):self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
    def existing(self,token):
        self.replace_product(lambda p:p['body']['target'].update(mode='existing',object=slot(token['object']),expected=slot(token)))
    def group(self,second_review=True,native=None):
        self.policy();first_request=copy.deepcopy(self.request);first_product=copy.deepcopy(self.product)
        self.replace_product(lambda p:p['body'].update(rationale='second independent proposal'))
        second_request=copy.deepcopy(self.request);second_product=copy.deepcopy(self.product)
        group_id=identifier();group_ref={'instance_id':self.s.instance_id,'id':group_id,'kind':'artifacts','revision':slot()}
        for req in (first_request,second_request):req['payload']['atomic_group']=slot(group_ref)
        self.review(request=first_request,product=first_product,native=native)
        if second_review:self.review(request=second_request,product=second_product,native=native)
        body={'contract':'TL-ACCEPTANCE-GROUP-1','group_key':identifier(),'members':[]}
        for req in (first_request,second_request):body['members'].append({'proposal':req['payload']['proposal'],'work':req['work_ref']['value'],'review_round':req['payload']['review_round'],'policy':req['payload']['policy'],'review':req['payload']['review'],'expected':req['expected'],'control':req['control'],'budget':req['budget']})
        # Preallocated immutable artifact identity resolves review/group refs;
        # no existing artifact payload is changed.
        with patch('digital_life.infrastructure.persistence.sqlite_store.identifier',return_value=group_id):self.assertEqual(self.s.artifact(body),group_id)
        self.request=first_request;self.product=first_product;return second_request
    def test_native_existing_cas_update_and_reuse_do_not_duplicate_obligations(self):
        self.policy();self.review();first=self.decision();native=first['content_ref']['value'];token={'object':native,'revision':1,'epoch':0}
        self.request.update(command_id=identifier(),idempotency_key=identifier());self.existing(token);self.review(native=token);second=self.decision();self.assertEqual(second['operation'],'accept')
        self.assertEqual(self.s.row('tl_content',native['id'])['head_revision_id'],second['revision_ref']['value']['id'])
        token['revision']=2;self.request.update(command_id=identifier(),idempotency_key=identifier());self.existing(token);self.review('reuse',native=token)
        counts=[self.db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('tl_content_revision','tl_handoff')]
        reused=self.decision();self.assertEqual(reused['operation'],'reuse');self.assertEqual(reused['revision_ref'],second['revision_ref']);self.assertEqual(counts,[self.db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('tl_content_revision','tl_handoff')])
    def test_stale_native_expected_cannot_overwrite_head(self):
        self.policy();self.review();first=self.decision();token={'object':first['content_ref']['value'],'revision':0,'epoch':0}
        self.existing(token);self.review(native=dict(token,revision=1))
        with self.assertRaises(ContractError):self.decide()
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_content_revision').fetchone()[0],1)
    def test_legacy_new_version_and_real_native_head_review_evolve_independently(self):
        _,legacy=self.obs.baseline();self.existing(legacy);self.policy();self.review();first=self.decision();self.assertEqual(first['operation'],'accept')
        with self.s.tx():
            revision=self.s.insert('cognition_belief_revisions',belief_id=legacy['object']['id'],revision_no=2,content='new controller-reviewed source report',acceptance_state='held',uncertainty_json={},method_version='synthetic-2')
            self.db.execute('UPDATE cognition_beliefs SET current_revision_id=? WHERE id=?',(revision,legacy['object']['id']))
        legacy['revision']=2;self.request.update(command_id=identifier(),idempotency_key=identifier());self.existing(legacy)
        native={'object':first['content_ref']['value'],'revision':1,'epoch':0};self.review(native=native);second=self.decision()
        self.assertEqual(second['operation'],'accept');self.assertEqual(first['content_ref'],second['content_ref'])
        bridges=self.db.execute("SELECT d.consumer_ref_id,d.metadata_artifact_id FROM tl_dependency d WHERE field_path='/_bridges/TL-LEGACY-COGNITION-BRIDGE-1'").fetchall();self.assertEqual(len(bridges),2)
        for row in bridges:self.assertEqual(set(self.s.read_artifact(row['metadata_artifact_id'])),{'contract','consumer','dependency','field_path','scope'})
    def test_group_duplicate_native_target_preflight_rejects(self):
        self.policy();self.review();first=self.decision();token={'object':first['content_ref']['value'],'revision':1,'epoch':0}
        self.request.update(command_id=identifier(),idempotency_key=identifier());self.existing(token);self.group(native=token)
        with self.assertRaises(Conflict):self.decide()
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_decision').fetchone()[0],1)

    def revoke_a(self):
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        from tests.test_tool_learning_invalidation import MechanicalInvalidation
        request=copy.deepcopy(self.request);request.update(command_id=identifier(),idempotency_key=identifier());request['principal'].update(module='M12',purpose='propagate')
        request['payload']={'change_id':identifier(),'kind':'revoke','source':{'object':copy.deepcopy(self.product['body']['claims'][0]['evidence'][0]['source']),'revision':1,'epoch':0},'replacement':slot(),'affected_scope':copy.deepcopy(self.product['body']['claims'][0]['scope']),'subjects':[],'purposes':['accept'],'expected_epoch':0,'evidence':copy.deepcopy(self.product['body']['claims'][0]['evidence']),'erase_scope':slot()}
        ToolLearningInvalidation(self.s,MechanicalInvalidation()).apply('mechanical-im06',request)
    def test_independent_source_can_repair_old_revoked_head_without_using_old_claims(self):
        self.policy();self.review();first=self.decision();self.revoke_a();token={'object':first['content_ref']['value'],'revision':1,'epoch':0}
        original=copy.deepcopy(self.product['body']['claims'][0]['evidence'][0]);actual=self.s.read_artifact(original['artifact']['id'])
        independent=self.s.insert('perception_signals',channel_id=self.db.execute('SELECT id FROM perception_channels LIMIT 1').fetchone()[0],source_actor_id=self.s.config()['controller'],artifact_id=self.s.artifact(actual),received_at=utc())
        b=ref(self.s,independent);original['source']=b
        self.assertEqual(self.s.read_artifact(self.s.row('perception_signals',independent)['artifact_id']),actual)
        def mutate(p):
            p['source_refs']=[copy.deepcopy(original)]
            p['body']['target'].update(mode='existing',object=slot(token['object']),expected=slot(token));p['body']['claims'][0]['evidence']=[copy.deepcopy(original)]
        self.replace_product(mutate);self.request.update(command_id=identifier(),idempotency_key=identifier());self.review(native=token);second=self.decision();self.assertEqual(second['operation'],'accept')
        current={'object':token['object'],'revision':2,'epoch':0};self.assertTrue(self.service.eligibility.check('synthetic-acceptance',self.request['principal'],current,self.product['body']['claims'][0]['scope'],'accept',self.request['principal']['recipient'])['qualified'])
    def test_old_revoked_support_cannot_be_reused_or_reintroduced(self):
        self.policy();self.review();first=self.decision();self.revoke_a();token={'object':first['content_ref']['value'],'revision':1,'epoch':0}
        self.existing(token);self.request.update(command_id=identifier(),idempotency_key=identifier());self.review(native=token)
        with self.assertRaises((Forbidden,Conflict)):self.decide()
    def test_read_accounting_port_and_target_metadata_port_default_deny(self):
        class Unmetered(MechanicalAcceptance):verify_read_accounting=AcceptanceAuthority.verify_read_accounting
        with self.assertRaises(Forbidden):ToolLearningAcceptance(self.s,Unmetered(self),MechanicalEligibility()).decide('synthetic-acceptance',self.request)
        first=self.decision();self.advance_round();self.policy();self.review(native={'object':first['content_ref']['value'],'revision':1,'epoch':0})
        class NoCAS(MechanicalAcceptance):verify_target_metadata=AcceptanceAuthority.verify_target_metadata
        with self.assertRaises(Forbidden):ToolLearningAcceptance(self.s,NoCAS(self),MechanicalEligibility()).decide('synthetic-acceptance',self.request)

    def test_group_all_accept_commits_two_versions_and_fixed_obligations(self):
        self.group();response=self.decide();self.assertEqual(len(response['result_refs']),2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_group').fetchone()[0],1);self.assertEqual(self.db.execute('SELECT count(*) FROM tl_handoff').fetchone()[0],2)
    def test_group_incomplete_review_cannot_half_accept(self):
        self.group(False);response=self.decide();operations=[self.s.row('tl_decision',r['id'])['operation'] for r in response['result_refs']]
        self.assertEqual(operations,['candidate','candidate']);self.assertEqual(self.db.execute('SELECT count(*) FROM tl_handoff').fetchone()[0],0)
    def test_group_each_member_permission_is_current(self):
        second=self.group();self.authority.deny=second['payload']['proposal']['id']
        with self.assertRaises(Forbidden):self.decide()
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_decision').fetchone()[0],0)
    def test_group_failure_second_member_rolls_back_first(self):
        self.group();original=self.service._write;calls=[]
        def fault(*args):
            original(*args);calls.append(1)
            if len(calls)==2:raise OSError('synthetic second member failure')
        with patch.object(self.service,'_write',fault):
            with self.assertRaises(OSError):self.decide()
        for table in ('tl_group','tl_decision','tl_content_revision','tl_handoff'):self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
    def test_literal_missing_first_locator_does_not_hide_second_actual_support(self):
        def mutate(p):
            bad=copy.deepcopy(p['body']['claims'][0]['evidence'][0]);bad['locator']['pointer']='/missing';p['body']['claims'][0]['evidence'].insert(0,bad)
        self.replace_product(mutate);self.policy();self.review();d=self.decision();self.assertEqual(d['operation'],'accept');self.assertEqual(d['checks']['G03']['state'],'pass')
    def test_byte_scan_limit_and_corrupt_digest_reject_without_c1(self):
        self.request['budget']['max_bytes']=1
        with self.assertRaises((Forbidden,Conflict)):self.decide()
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_decision').fetchone()[0],0)
    def test_current_authority_stop_during_prepare_rejects(self):
                # Actual source permission checks may change local control synchronously.
        self.authority.hook=lambda stage:self.obs.base.f.control.stop('within acceptance authority')
        with self.assertRaises(Forbidden):self.decide()
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_decision').fetchone()[0],0)

    def test_review_defer_reject_conflict_candidate_have_no_handoff(self):
        for verdict in ('defer','reject','conflict','candidate'):
            case=AcceptanceTests();case.setUp()
            try:
                case.policy();case.review(verdict);d=case.decision();self.assertEqual(d['operation'],verdict);self.assertEqual(d['handoff_refs'],[])
            finally:case.doCleanups()
    def test_read_opportunities_unique_and_bound_to_original_account(self):
        contexts=[]
        self.authority.verify_read_accounting=lambda entry,request,work,snapshot,context,stage:contexts.append(copy.deepcopy(context))
        self.policy();self.review();self.decide();self.assertGreater(len(contexts),1);self.assertEqual(len({x['occurrence_id'] for x in contexts}),len(contexts))
        for x in contexts:
            self.assertEqual(x['account_ref'],self.request['budget']['account_ref']);self.assertEqual(x['work_ref'],self.request['work_ref']['value']);self.assertEqual(x['request_fingerprint'],command_fingerprint(self.request))
    def test_gate_false_owner_or_boolean_cannot_self_authorize(self):
        original=self.authority.evaluate_gate
        def wrong(entry,request,context,gate,stage):
            check=original(entry,request,context,gate,stage);check['checker']['module']='M14';return check
        self.authority.evaluate_gate=wrong
        with self.assertRaises(Forbidden):self.decide()
        self.authority.evaluate_gate=lambda *args:True
        with self.assertRaises(ContractError):self.decide()
    def test_review_digest_scope_and_authenticated_origin_bound(self):
        self.policy();body=self.review();body['proposal_digest']='0'*64
        row=self.s.row('perception_signals',self.request['payload']['review']['value']['id']);row.update(id=identifier(),artifact_id=self.s.artifact(body));self.s.insert('perception_signals',**row);self.request['payload']['review']=slot(ref(self.s,row['id']))
        with self.assertRaises(Conflict):self.decide()
    def test_commit_current_owner_denial_rolls_back_everything(self):
        self.policy();self.review();original=self.authority.verify_proposal_access
        def deny(entry,request,row,stage):
            if stage=='commit':raise Forbidden('revoked at final commit')
            return original(entry,request,row,stage)
        self.authority.verify_proposal_access=deny
        with self.assertRaises(Forbidden):self.decide()
        for table in ('tl_decision','tl_content','tl_content_revision','tl_handoff'):self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_final_g08_callback_crossing_deadline_rolls_back(self):
        self.policy();self.review();original=self.authority.evaluate_gate
        def late(entry,request,context,gate,stage):
            check=original(entry,request,context,gate,stage)
            if stage=='commit' and gate=='G08':
                deadline=min(context['work']['deadline'],request['budget']['deadline']);self.service.clock=lambda:deadline
            return check
        self.authority.evaluate_gate=late
        with self.assertRaises(Forbidden):self.decide()
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_decision').fetchone()[0],0)
    def test_bridge_metadata_consumer_and_source_projection_are_not_labels(self):
        for mismatch in ('consumer','source'):
            case=AcceptanceTests();case.setUp()
            try:
                case.policy();case.review();first=case.decision();_,legacy=case.obs.baseline();consumer=first['revision_ref']['value']
                dependency={'target':copy.deepcopy(legacy['object']),'relation':'derive','expected':copy.deepcopy(legacy),'consumer_purpose':'accept'}
                metadata={'contract':'TL-DEPENDENCY-1','consumer':copy.deepcopy(consumer),'dependency':dependency,'field_path':'/_bridges/TL-LEGACY-COGNITION-BRIDGE-1','scope':copy.deepcopy(case.product['body']['claims'][0]['scope'])}
                if mismatch=='consumer':metadata['consumer']=copy.deepcopy(case.request['work_ref']['value'])
                else:
                    metadata['dependency']['target']=copy.deepcopy(case.product['body']['claims'][0]['evidence'][0]['source']);metadata['dependency']['expected']={'object':copy.deepcopy(metadata['dependency']['target']),'revision':1,'epoch':0}
                revision=case.db.execute('SELECT id FROM object_revision_registry WHERE object_id=? AND revision_no=1',(legacy['object']['id'],)).fetchone()[0]
                case.s.insert('tl_dependency',consumer_ref_id=consumer['id'],source_ref_id=legacy['object']['id'],source_revision_id=revision,relation='derive',purpose='accept',expected_epoch=0,field_path=metadata['field_path'],metadata_artifact_id=case.s.artifact(metadata))
                case.existing(legacy);case.request.update(command_id=identifier(),idempotency_key=identifier());case.review(native={'object':first['content_ref']['value'],'revision':1,'epoch':0})
                with self.assertRaisesRegex(ContractError,'row and immutable metadata differ'):case.decide()
                self.assertEqual(case.db.execute('SELECT count(*) FROM tl_content_revision').fetchone()[0],1)
            finally:case.doCleanups()

    def test_known_false_zero_null_preserved(self):
        for value in (False,0,None):
            case=AcceptanceTests();case.setUp()
            try:
                case.obs.value(value)
                def mutate(p):
                    p['body']['claims'][0].update(value={'status':'known','value':value,'reason_code':'source_reported_null' if value is None else 'none','reason':'source reports null' if value is None else '','basis_refs':[]},evidence=[copy.deepcopy(case.obs.source)])
                case.replace_product(mutate);case.policy();case.review();d=case.decision()
                self.assertEqual(d['operation'],'accept')
                payload=case.s.read_artifact(case.s.row('tl_content_revision',d['revision_ref']['value']['id'])['payload_artifact_id'])
                actual=payload['claims'][0]['value'];self.assertEqual(actual['status'],'known');self.assertIs(type(actual['value']),type(value));self.assertEqual(actual['value'],value)
            finally:case.doCleanups()

if __name__=='__main__':unittest.main()
