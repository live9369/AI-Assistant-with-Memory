"""Actual same-work header upgrade positive and closed-capability failures."""
import copy
import json
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Forbidden,Conflict,identifier,utc
from digital_life.application.learning.representation_upgrade import UpgradeSession,SOURCE
from digital_life.application.learning.eligibility import ref,slot

VARIANTS=('upgrade_and_replay','wrong_bearer','no_policy','unknown_language','ordinal_outside_policy','same_language','current_policy_after_intent','stop_after_intent','source_cancelled','content_changed_after_intent','new_source_F1_after_intent','missing_fixed_payload_unknown_hold','C2_after_actual_write_failure','late_policy_before_C2_commit','fake_terminal_context','terminal_context_cannot_reserve_model_or_tool')


def run_upgrade(variant):
    from tests.test_tool_learning_runtime import StrictLearningFlowTests
    f=StrictLearningFlowTests();f.setUp()
    try:
        s=f.s;r=f.r
        work,proposal=f.observe();review=f.review(proposal);r.decide(proposal['id'],review)
        handoff=s.db.execute('SELECT id FROM tl_handoff WHERE work_id=?',(work['id'],)).fetchone()[0];r.publish(handoff)
        original_work=dict(s.row('tl_work',work['id']));original_handoff=s.row('tl_handoff',handoff)
        original_rep=s.row('tl_representation',original_handoff['representation_id'])
        old_body=s.read_artifact(original_rep['body_artifact_id'])
        conditions=s.read_artifact(original_work['conditions_artifact_id'])
        before={table:len(s.rows(table)) for table in ('tl_work','tl_product','tl_decision','tl_content_revision')}
        before_budget=json.loads(s.row('activities',original_work['learning_activity_id'])['budget_json'])['budget']
        def current_policy(enabled=True):
            row=s.row('policy_versions',s.rows('policy_epochs')[0]['policy_version_id']);scope=json.loads(row['scope'])
            scope['tool_learning_representation_upgrade']={'contract':'TL-HEADER-LANGUAGE-UPGRADE-1','enabled':enabled,'languages':['zh','en'],'max_upgrades':2,'expires_at':utc(120)}
            version=s.db.execute('SELECT max(version)+1 FROM policy_versions').fetchone()[0]
            key=s.insert('policy_versions',version=version,mode='authorization',scope=scope,effective_at=utc(-1),authority=s.config()['controller'])
            s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE instance_id=?',(key,s.instance_id))
        if variant!='no_policy':current_policy()
        if variant=='source_cancelled':
            from digital_life.application.learning.controller_read import ControllerMaterialReader
            actor=ControllerMaterialReader(s,'Bearer synthetic-isolated-controller-token');activity=s.row('activities',original_work['source_activity_id'])
            actor.cancel(activity['id'],{'expected_revision':activity['revision']})
        if variant=='missing_fixed_payload_unknown_hold':
            revision=s.row('tl_content_revision',original_handoff['content_revision_id']);artifact=s.row('artifacts',revision['payload_artifact_id']);(s.root/'blobs'/artifact['storage_ref']).unlink()
        observed=[];errors=[];result=None
        original_prepare=UpgradeSession.prepare
        def prepare(session):
            value=original_prepare(session);observed.append('actual-intent-prepared')
            if variant=='current_policy_after_intent':current_policy(False)
            if variant=='stop_after_intent':f.f.control.stop('IM19 explicit upgrade stop')
            if variant=='content_changed_after_intent':
                revision=s.row('tl_content_revision',original_handoff['content_revision_id'])
                s.db.execute('UPDATE tl_content SET head_revision_id=NULL,row_revision=row_revision+1 WHERE id=?',(revision['content_id'],));observed.append('native-head-invalidated')
            if variant=='new_source_F1_after_intent':
                from digital_life.application.learning.invalidation import ToolLearningInvalidation
                from tests.test_tool_learning_invalidation import MechanicalInvalidation
                entry,request=r.assessment_request(work['id'])
                request.update(command_id=identifier(),idempotency_key=identifier());request['principal'].update(module='M12',purpose='propagate')
                source=conditions['source'];plan=s.read_artifact(s.read_artifact(original_work['method_artifact_id'])['request_ref']['value']['id'])
                request['payload']={'change_id':identifier(),'kind':'revoke','source':{'object':source['source'],'revision':0,'epoch':0},'replacement':slot(),'affected_scope':plan['scope'],'subjects':[],'purposes':['learn','accept','represent'],'expected_epoch':0,'evidence':[source],'erase_scope':slot()}
                ToolLearningInvalidation(s,MechanicalInvalidation()).apply('mechanical-im06',request);observed.append('actual-F1-committed')
            return value
        original_write=r.representation._write
        def write(*args):
            value=original_write(*args);observed.append('actual-C2-writes-before-commit')
            if variant=='C2_after_actual_write_failure':raise OSError('IM19 actual C2 write fault')
            return value
        original_handoff_verify=r.representation.authority.verify_handoff
        def verify_handoff(entry,operation,request,context,stage):
            if variant=='late_policy_before_C2_commit' and stage=='commit' and operation=='publish_representation' and 'late-policy-changed' not in observed:
                current_policy(False);observed.append('late-policy-changed')
            return original_handoff_verify(entry,operation,request,context,stage)
        original_read=UpgradeSession.verify_read
        def verify_read(session,entry,work_state,operation,binding,stage):
            value=original_read(session,entry,work_state,operation,binding,stage)
            return value
        if variant=='fake_terminal_context':r.representation_session=True
        try:
            with patch.object(UpgradeSession,'prepare',prepare),patch.object(r.representation,'_write',write),patch.object(r.representation.authority,'verify_handoff',verify_handoff):
                if variant=='terminal_context_cannot_reserve_model_or_tool':
                    original_reserve=r.budget.reserve
                    def reserve(entry,work_id,operation,kind,amounts,**kwargs):
                        if r.representation_session is not None and kind=='retrieval' and 'closed-scope-probed' not in observed:
                            observed.append('closed-scope-probed')
                            for other in ('thought_attempt','tool_attempt'):
                                try:original_reserve(entry,work_id,operation,other,{'attempts':1,'tool_calls':int(other=='tool_attempt')})
                                except Forbidden:observed.append('denied-'+other)
                                else:raise AssertionError('terminal rendering context authorized a model/tool opportunity')
                        return original_reserve(entry,work_id,operation,kind,amounts,**kwargs)
                    with patch.object(r.budget,'reserve',reserve):result=r.upgrade_representation(handoff,'Bearer synthetic-isolated-controller-token',language='en',ordinal=1)
                else:
                    result=r.upgrade_representation(handoff,'Bearer wrong' if variant=='wrong_bearer' else 'Bearer synthetic-isolated-controller-token',language='fr' if variant=='unknown_language' else 'zh' if variant=='same_language' else 'en',ordinal=3 if variant=='ordinal_outside_policy' else 1)
        except (ContractError,OSError) as exc:errors.append(type(exc).__name__+': '+str(exc))
        finally:
            if variant=='fake_terminal_context':r.representation_session=None
        positive=variant in ('upgrade_and_replay','terminal_context_cannot_reserve_model_or_tool')
        reps=s.rows('tl_representation')
        if positive:
            if result is None or errors or len(reps)!=2:raise AssertionError('actual upgrade positive failed: '+str(errors))
            new=next(row for row in reps if row['id']!=original_rep['id']);body=s.read_artifact(new['body_artifact_id'])
            if [line.split('：',1)[1] for line in body.splitlines()]!=[line.split('：',1)[1] for line in old_body.splitlines()]:raise AssertionError('header localization changed actual source JSON/limitations/order')
            if new['content_revision_id']!=original_rep['content_revision_id'] or new['series_id']!=original_rep['series_id'] or new['representation_no']!=original_rep['representation_no']+1:raise AssertionError('render upgrade changed cognitive identity or reset representation series')
            if variant=='upgrade_and_replay':
                replay=r.upgrade_representation(handoff,'Bearer synthetic-isolated-controller-token',language='en',ordinal=1)
                if replay['disposition']!='reused' or len(s.rows('tl_representation'))!=2:raise AssertionError('same ordinal/new command allocated another rendering')
            if variant=='terminal_context_cannot_reserve_model_or_tool' and not all('denied-'+kind in observed for kind in ('thought_attempt','tool_attempt')):raise AssertionError('closed terminal read guard was not exercised')
        else:
            if not errors or len(reps)!=1:raise AssertionError('invalid or failed upgrade produced a new visible representation: '+variant+' '+str(errors))
            if s.row('tl_representation',original_rep['id'])['state']!='ready':raise AssertionError('failed C2 displaced the original ready representation')
        after={table:len(s.rows(table)) for table in before}
        if before!=after:raise AssertionError('format change created learning work/products/decisions/content versions')
        if variant=='missing_fixed_payload_unknown_hold':
            ledger=json.loads(s.row('activities',original_work['learning_activity_id'])['budget_json'])['ledger']
            if not ledger['halted'] or not any(v['state']=='usage_unknown' for v in ledger['reservations'].values()):raise AssertionError('actual missing fixed body read lost unknown hold')
        current=s.row('tl_work',work['id'])
        if current['state']!=original_work['state'] or current['deadline']!=original_work['deadline'] or current['budget_account_id']!=original_work['budget_account_id']:raise AssertionError('upgrade reopened work or renewed original deadline/account')
        if json.loads(s.row('activities',current['learning_activity_id'])['budget_json'])['budget']!=before_budget:raise AssertionError('format upgrade enlarged original caps')
        return {'case_id':'Q07-A11','variant':variant,'endpoint':'authorized_same_content_header_parameter_upgrade' if positive else 'blocked_or_atomic_failure_no_new_representation',
            'actual_result':result,'actual_errors':errors,'observations':observed,'original_representation':original_rep,'representations_after':reps,
            'old_body':old_body,'new_body':s.read_artifact(next(row for row in reps if row['id']!=original_rep['id'])['body_artifact_id']) if positive else None,
            'learning_counts_before':before,'learning_counts_after':after,'original_work':original_work,'work_after':current,
            'original_caps':before_budget,'ledger_after':json.loads(s.row('activities',current['learning_activity_id'])['budget_json']),
            'authorization_events':[s.read_artifact(row[0]) for row in s.db.execute('SELECT payload_artifact_id FROM runtime_events WHERE source=?',(SOURCE,))],
            'handoffs_after':[dict(row) for row in s.db.execute('SELECT * FROM tl_handoff WHERE work_id=?',(work['id'],))],
            'real_model_called':False,'scope':'verified zh/en fixed label mapping only; original claims/scope/evidence JSON never translated; atomic group upgrades blocked'}
    finally:f.doCleanups()
