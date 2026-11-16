"""Actual strict coordinator counterexample proof and failure-boundary cases."""
import copy
import json
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Forbidden,identifier,utc,dumps
from digital_life.application.learning.eligibility import ref,slot
from digital_life.application.learning.comparison import ControllerComparisonAuthor,AuthenticatedComparisonOwner,VerifiedComparisonRelation

VARIANTS=('actual_restrict_candidate','wrong_bearer','no_policy','unknown_member','unauthored_membership','equal_value','unknown_unit','unknown_time','membership_not_yet_valid','head_changed_after_proof','membership_changed_after_proof','policy_changed_after_proof','new_source_revoked','old_source_revoked','late_head_at_commit','late_membership_at_commit','forged_relation_object','unentered_owner')


def run_comparison(variant):
    from tests.test_tool_learning_runtime import StrictLearningFlowTests
    from tests.test_tool_learning_products import claim as new_claim
    from digital_life.application.runtime.engine import Engine
    f=StrictLearningFlowTests();f.setUp()
    try:
        s=f.s;controller=s.config()['controller'];key=identifier()
        f.f.control.accept_inbound('strict-fixture-controller',key,{'text':'10'},controller)
        activity=Engine(s,f.f.f.identity).submit('10',key,'strict-fixture-controller')
        signal=s.row('activities',activity)['trigger_event_id']
        work=f.r.admit(activity,signal,{'kind':'json_pointer','pointer':'/text'})
        work_row=s.row('tl_work',work['id']);conditions=s.read_artifact(work_row['conditions_artifact_id'])
        method=s.read_artifact(work_row['method_artifact_id']);plan=s.read_artifact(method['request_ref']['value']['id']);point=plan['scope']['temporal']['start']['value']
        domain=s.insert('world_entities',entity_type='finite-source-record-registry',canonical_name='IM19 exact finite domain',resolution_status='resolved')
        member=s.insert('world_entities',entity_type='source-record',canonical_name=signal,resolution_status='ambiguous' if variant=='unknown_member' else 'resolved')
        def policy(enabled=True):
            old=s.row('policy_versions',s.rows('policy_epochs')[0]['policy_version_id']);scope=json.loads(old['scope'])
            scope['tool_learning_comparison']={'contract':'TL-BOUNDED-COMPARISON-POLICY-1','enabled':enabled,'domain_ids':[domain],'expires_at':utc(120)}
            version=s.db.execute('SELECT max(version)+1 FROM policy_versions').fetchone()[0]
            ident=s.insert('policy_versions',version=version,mode='authorization',scope=scope,effective_at=utc(-1),authority=controller)
            s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE instance_id=?',(ident,s.instance_id))
        if variant!='no_policy':policy()
        author=ControllerComparisonAuthor(s,'Bearer wrong' if variant=='wrong_bearer' else 'Bearer synthetic-isolated-controller-token')
        error=None;proof=None;membership=None;products=[];candidate=None;injections=[];baseline=None;body=None;old_source=None;response=None
        try:
            membership=author.membership(domain,member,ref(s,signal),valid_from=utc(50) if variant=='membership_not_yet_valid' else point)
            if variant=='unauthored_membership':
                relation=s.row('world_entity_relations',membership['id'])
                membership=ref(s,s.insert('world_entity_relations',subject_id=member,relation_type='member_of',object_id=domain,evidence_id=relation['evidence_id'],valid_from=point))
            expression={'contract':'TL-EXPLICIT-UNIVERSAL-1','quantifier':'all','domain_ref':ref(s,domain),'property':plan['predicate'],'value':slot('10' if variant=='equal_value' else '7')}
            old_scope=copy.deepcopy(plan['scope']);old_scope.update(subject=slot(ref(s,domain)),domain=slot('registered-source-domain:'+domain),conditions=slot({'domain_registry':domain,'quantifier':'all','as_of':point}),property=plan['predicate'],granularity=slot('every registered source record'))
            if variant=='unknown_unit':old_scope['unit']={'status':'unknown','value':None,'reason_code':'not_measured','reason':'old unit unknown','basis_refs':[]}
            if variant=='unknown_time':old_scope['temporal'].update(start={'status':'unknown','value':None,'reason_code':'not_measured','reason':'old point unknown','basis_refs':[]},end={'status':'unknown','value':None,'reason_code':'not_measured','reason':'old point unknown','basis_refs':[]},bounds='unknown')
            belief=s.insert('cognition_beliefs',subject_ref=domain,predicate=plan['predicate'],literal=expression,scope=old_scope)
            revision=s.insert('cognition_belief_revisions',belief_id=belief,revision_no=1,content=dumps(expression),acceptance_state='held',uncertainty_json={},method_version='explicit-authored-IM19-initial-universal')
            s.db.execute('UPDATE cognition_beliefs SET current_revision_id=? WHERE id=?',(revision,belief))
            baseline={'object':ref(s,belief),'revision':1,'epoch':0}
            old_signal=s.insert('perception_signals',channel_id=s.row('perception_signals',signal)['channel_id'],source_actor_id=controller,artifact_id=s.artifact({'text':'7'}),received_at=point)
            old_source=copy.deepcopy(conditions['source']);artifact=s.row('perception_signals',old_signal)['artifact_id'];old_source.update(source=ref(s,old_signal),artifact=ref(s,artifact),digest={'algorithm':'sha256','hex':s.row('artifacts',artifact)['hash']})
            claim=new_claim();claim.update(subject=slot(ref(s,domain)),predicate=plan['predicate'],scope=old_scope,value=slot(expression),evidence=[old_source])
            body={'contract':'TL-OBSERVATION-BASELINE-1','token':baseline,'claims':[claim]};artifact=ref(s,s.artifact(body))
            proof=author.restriction(work['id'],artifact,membership,'Registered member record has exact text value 10, refuting this explicit all-records-text-equal-7 proposition only')
            def change_head():
                number=s.db.execute('SELECT max(revision_no)+1 FROM cognition_belief_revisions WHERE belief_id=?',(belief,)).fetchone()[0]
                new=s.insert('cognition_belief_revisions',belief_id=belief,revision_no=number,content='explicit newer owner revision',acceptance_state='held',uncertainty_json={},method_version='IM19-boundary-injection')
                s.db.execute('UPDATE cognition_beliefs SET current_revision_id=? WHERE id=?',(new,belief));injections.append('native-head-changed')
            def change_membership():
                s.db.execute('UPDATE world_entity_relations SET valid_to=? WHERE id=?',(point,membership['id']));injections.append('native-membership-changed')
            if variant=='head_changed_after_proof':change_head()
            if variant=='membership_changed_after_proof':change_membership()
            if variant=='policy_changed_after_proof':policy(False)
            if variant in ('new_source_revoked','old_source_revoked'):
                from digital_life.application.learning.invalidation import ToolLearningInvalidation
                from tests.test_tool_learning_invalidation import MechanicalInvalidation
                entry,request=f.r.assessment_request(work['id'])
                source=conditions['source'] if variant=='new_source_revoked' else old_source
                request.update(command_id=identifier(),idempotency_key=identifier())
                request['principal'].update(module='M12',purpose='propagate')
                request['payload']={'change_id':identifier(),'kind':'revoke','source':{'object':source['source'],'revision':0,'epoch':0},'replacement':slot(),'affected_scope':plan['scope'] if variant=='new_source_revoked' else old_scope,'subjects':[],'purposes':['learn','accept'],'expected_epoch':0,'evidence':[source],'erase_scope':slot()}
                ToolLearningInvalidation(s,MechanicalInvalidation()).apply('mechanical-im06',request);injections.append('actual-F1-committed')
            original=f.r.observation.authority.verify_observation
            def verify(entry,request,work_state,actual_plan,stage):
                if stage=='commit' and not injections and variant in ('late_head_at_commit','late_membership_at_commit'):
                    change_head() if variant=='late_head_at_commit' else change_membership()
                return original(entry,request,work_state,actual_plan,stage)
            if variant=='unentered_owner':
                entry,request=f.r.assessment_request(work['id'])
                AuthenticatedComparisonOwner(s).baseline_material(entry,request,baseline)
            with patch.object(f.r.observation.authority,'verify_observation',verify):
                if variant=='forged_relation_object':
                    fake=VerifiedComparisonRelation('restriction',[],{'object':proof,'revision':0,'epoch':0},'unverified JSON-style assertion')
                    with patch.object(f.r.observation.authority,'comparison_relation',return_value=fake):response=f.r.assess(work['id'],baseline_refs=[baseline])
                else:response=f.r.assess(work['id'],baseline_refs=[baseline])
            products=[s.read_artifact(row['payload_artifact_id']) for row in s.db.execute('SELECT * FROM tl_product WHERE work_id=?',(work['id'],))]
            proposal=next(p for p in products if p['product_type']=='UpdateProposal')
            if proposal['body']['operation']!='restrict' or proposal['body']['claims'][0]['value']['value']!='10':raise AssertionError('actual scoped counterexample did not produce restrict')
            if not proposal['body']['unresolved_items'] or proposal['body']['unresolved_items'][0]['status']=='known' or 'replacement universal' not in proposal['body']['rationale']:raise AssertionError('restriction invented a known remaining domain/rule')
            if not proposal['derivation_links'] or proposal['derivation_links'][0]['target']!=proof:raise AssertionError('proposal lost real semantic proof lineage')
            result=f.r.decide(proposal['product_id']);candidate=s.row('tl_decision',result['result_refs'][0]['id'])['operation']
            if candidate!='candidate' or s.db.execute('SELECT count(*) FROM tl_handoff WHERE work_id=?',(work['id'],)).fetchone()[0]:raise AssertionError('restriction self-promoted without independent M03 qualification')
        except ContractError as exc:error=type(exc).__name__+': '+str(exc)
        positive=variant=='actual_restrict_candidate'
        if positive and (error is not None or candidate!='candidate'):raise AssertionError('real restriction positive failed: '+str(error))
        count=s.db.execute('SELECT count(*) FROM tl_product WHERE work_id=?',(work['id'],)).fetchone()[0]
        if not positive and (error is None or count):raise AssertionError('invalid semantic basis produced actual products: '+variant+' '+str(error))
        return {'case_id':'Q04-A15','variant':variant,'endpoint':'restrict_proposal_independent_candidate' if positive else 'blocked_invalid_or_stale_basis',
            'work':work,'actual_source':conditions['source'],'baseline_material':body,'old_source':old_source,'membership':membership,'proof_ref':proof,
            'proof_body':s.read_artifact(s.row('runtime_events',proof['id'])['payload_artifact_id']) if proof else None,
            'actual_response':response,'actual_products':products,'actual_candidate_operation':candidate,'actual_product_count':count,'actual_error':error,'injections':injections,
            'basis_counts':{'native_domain':1,'native_membership':int(membership is not None),'actual_original_source_records':2 if old_source else 1},
            'value_semantics':'Exact typed text values 7 and 10 from actual controller source records; no numeric conversion or world-inventory truth claim.',
            'real_model_called':False,'independent_scientific_sample':False}
    finally:f.doCleanups()
