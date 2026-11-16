"""Actual StrictLearningCoordinator and authenticated finite reprocessing cases."""
import copy
import json
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Forbidden,utc
from digital_life.application.learning.eligibility import ref,slot
from digital_life.application.learning.reprocessing import ControllerReprocessingAuthor,SOURCE

VARIANTS=('rehearsal','substantive_method','wrong_bearer','no_policy','label_only','ordinal_outside_policy','changed_command_after_grant','stale_previous_after_grant','policy_after_grant','commit_previous_changed','expired_previous','unknown_previous','exhausted_previous','source_evidence_changed','duplicate_ordinal')


def run_reprocessing(variant):
    from tests.test_tool_learning_runtime import StrictLearningFlowTests
    fixture=StrictLearningFlowTests();fixture.setUp()
    try:
        s=fixture.s;r=fixture.r
        if variant=='unknown_previous':
            original_transport=fixture.provider.transport
            def unknown_transport(*args):
                response=original_transport(*args);response.pop('usage',None);return response
            fixture.provider.transport=unknown_transport
            signal=s.row('activities',fixture.activity)['trigger_event_id']
            work=r.admit(fixture.activity,signal,{'kind':'json_pointer','pointer':'/text'},interpret=True)
            try:r.assess(work['id'])
            except ContractError:pass
            if 'usage_unknown' not in r.budget.check_work(work['id'])['block_reasons']:raise AssertionError('actual missing provider usage was not held unknown')
        elif variant=='exhausted_previous':
            original_admit=r.work.admit
            def one_attempt(entry,request):
                request['budget']['max_attempts']=1
                return original_admit(entry,request)
            with patch.object(r.work,'admit',one_attempt):work,proposal=fixture.observe(interpret=True)
            if r.budget.check_work(work['id'])['remaining']['attempts']!=0:raise AssertionError('actual model call did not exhaust predeclared one-attempt work')
        else:
            work,proposal=fixture.observe();review=fixture.review(proposal)
            r.decide(proposal['id'],review)
            handoff=s.db.execute('SELECT id FROM tl_handoff WHERE work_id=?',(work['id'],)).fetchone()[0]
            r.publish(handoff)
        previous=dict(s.row('tl_work',work['id']));conditions=s.read_artifact(previous['conditions_artifact_id'])
        original_parent=s.row('activities',previous['source_activity_id'])
        original_parent_ledger=json.loads(original_parent['budget_json'])['tl_work_allocations']
        old_products=[dict(row) for row in s.db.execute('SELECT * FROM tl_product WHERE work_id=?',(work['id'],))]
        def current_policy(enabled=True):
            active=s.rows('policy_epochs')[0];old=s.row('policy_versions',active['policy_version_id']);scope=json.loads(old['scope'])
            scope['tool_learning_reprocessing']={'contract':'TL-REPROCESSING-POLICY-1','enabled':enabled,'kinds':['rehearsal','method_change','baseline_change'],'max_practice':2,'max_reprocess':2,'expires_at':utc(120)}
            number=s.db.execute('SELECT max(version)+1 FROM policy_versions').fetchone()[0]
            policy=s.insert('policy_versions',version=number,mode='authorization',scope=scope,effective_at=utc(-1),authority=s.config()['controller'])
            s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE instance_id=?',(policy,s.instance_id))
        if variant!='no_policy':current_policy()
        method=None;kind='method_change' if variant in ('substantive_method','label_only') else 'rehearsal'
        if variant in ('substantive_method','label_only'):
            method=s.read_artifact(previous['method_artifact_id'])
            if variant=='label_only':method['version']='2'
            else:
                plan=s.read_artifact(method['request_ref']['value']['id']);plan['interpret']=True
                method['request_ref']=slot(ref(s,s.artifact(plan)))
        captured=[];original_author=ControllerReprocessingAuthor.authorize
        def authorize(author,request,**kwargs):
            captured.append(copy.deepcopy(request));result=original_author(author,request,**kwargs)
            if variant=='changed_command_after_grant':request['command_id']='f'*32
            if variant=='source_evidence_changed':request['payload']['source']['locator']={'kind':'json_pointer','pointer':'/different'}
            if variant=='stale_previous_after_grant':s.db.execute('UPDATE tl_work SET row_revision=row_revision+1 WHERE id=?',(work['id'],))
            if variant=='policy_after_grant':current_policy(False)
            return result
        original_project=r.work.authority.project_response
        def project(*args):
            response=original_project(*args)
            if variant=='commit_previous_changed' and args[-1]=='commit' and args[1]=='admit_observation':
                s.db.execute('UPDATE tl_work SET row_revision=row_revision+1 WHERE id=?',(work['id'],))
            return response
        error=None;new=None
        def invoke():
            return r.reprocess(work['id'],'Bearer wrong' if variant=='wrong_bearer' else 'Bearer synthetic-isolated-controller-token',
                kind=kind,reason='explicit finite same-source practice' if kind=='rehearsal' else 'actual interpretation plan now requests fresh bounded explanation',
                ordinal=3 if variant=='ordinal_outside_policy' else 1,method=method)
        with patch.object(ControllerReprocessingAuthor,'authorize',authorize),patch.object(r.work.authority,'project_response',project):
            try:
                if variant=='expired_previous':
                    with patch('digital_life.application.learning.reprocessing.utc',lambda:utc(1000)):new=invoke()
                else:new=invoke()
            except ContractError as exc:error=type(exc).__name__+': '+str(exc)
        positive=variant in ('rehearsal','substantive_method','duplicate_ordinal')
        if positive:
            if new is None:raise AssertionError('actual SDK positive failed: '+str(error))
            row=s.row('tl_work',new['id']);new_conditions=s.read_artifact(row['conditions_artifact_id'])
            grant=new_conditions['reprocessing']['grant']
            if row['source_activity_id']!=previous['source_activity_id'] or new_conditions['source']!=conditions['source']:raise AssertionError('practice fabricated a new observation/source activity')
            if row['deadline']>previous['deadline'] or new_conditions['source_budget']['account_ref']!=conditions['source_budget']['account_ref']:raise AssertionError('practice renewed deadline or parent')
            for key in ('new_observation_count','independent_sample_count'):
                if grant[key]!=0:raise AssertionError('practice counted a new independent observation')
            if grant['gain']!='not_measured':raise AssertionError('practice invented gain')
            r.assess(new['id'])
            if variant=='duplicate_ordinal':
                try:invoke()
                except ContractError:pass
                else:raise AssertionError('new request id reused an already bound ordinal')
            expected=2
        else:
            if error is None or new is not None:raise AssertionError('invalid reprocessing admitted: '+variant)
            new_conditions=None;grant=None;expected=1
        if s.db.execute('SELECT count(*) FROM tl_work').fetchone()[0]!=expected:raise AssertionError('unexpected extra work')
        if old_products!=[dict(row) for row in s.db.execute('SELECT * FROM tl_product WHERE work_id=?',(work['id'],))]:raise AssertionError('prior products were changed')
        parent_after=json.loads(s.row('activities',previous['source_activity_id'])['budget_json'])['tl_work_allocations']
        if parent_after['caps']!=original_parent_ledger['caps']:raise AssertionError('original total pool caps changed')
        return {'case_ids':['Q03-A11','Q03-A15'],'variant':variant,'endpoint':'finite_authorized_reprocessing' if positive else 'blocked_no_new_work',
            'old_work':previous,'original_work_budget_snapshot':r.budget.check_work(work['id']),'original_conditions':conditions,'original_parent_allocation':original_parent_ledger,'parent_allocation_after':parent_after,
            'new_conditions':new_conditions,'grant':grant,'exact_requests':captured,'error':error,
            'authorization_events':[{'id':row['id'],'payload':s.read_artifact(row['payload_artifact_id'])} for row in s.db.execute('SELECT * FROM runtime_events WHERE source=?',(SOURCE,))],
            'work_count':expected,'prior_products_preserved':True,'real_model_called':False,
            'provider_scope':'deterministic injected transport only; actual production coordinator/owner/credential/policy paths'}
    finally:fixture.doCleanups()
