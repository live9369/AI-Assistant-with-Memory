"""Explicit controller proof for finite same-source rehearsal/reprocessing.

Authoring a proof never admits work, renews a deadline, changes a source or
spends a model attempt. Normal C0 source/owner/parent-budget checks still apply.
"""
from copy import deepcopy
import json
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,utc
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.application.learning.eligibility import ref,slot
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate

KINDS=('rehearsal','method_change','baseline_change')
SOURCE='tl.reprocessing.authorization'


def _profile(s,request):
    active=s.rows('policy_epochs')[0]['policy_version_id'];policy=s.row('policy_versions',active)
    if request['principal']['authorization']['id']!=active or request['principal']['authorization']['kind']!='policy_versions':raise Forbidden('reprocessing needs the current policy identity')
    profile=json.loads(policy['scope']).get('tool_learning_reprocessing')
    t.obj(profile,('contract','enabled','kinds','max_practice','max_reprocess','expires_at'))
    if profile['contract']!='TL-REPROCESSING-POLICY-1' or profile['enabled'] is not True:raise Forbidden('reprocessing policy not enabled')
    t.array(profile['kinds'],lambda x:t.enum(x,KINDS))
    t.integer(profile['max_practice']);t.integer(profile['max_reprocess']);c.validate('UTC',profile['expires_at'])
    if not profile['kinds'] or profile['max_practice']>32 or profile['max_reprocess']>32:raise Forbidden('finite bounded reprocessing policy required')
    if profile['expires_at']<=utc() or policy['effective_at']>utc() or policy['valid_to'] is not None and policy['valid_to']<=utc():raise Forbidden('reprocessing policy expired')
    return active,profile


def _prior(s,request):
    c.validate_request('admit_observation',request)
    previous=request['payload']['previous_work']
    if previous['status']!='known' or previous['value']['kind']!='tl_work' or previous['value']['instance_id']!=s.instance_id:raise Forbidden('a real previous work is required')
    row=s.row('tl_work',previous['value']['id'])
    if row['state'] not in ('completed','no_change','rejected'):raise Forbidden('prior work must be terminal; suspended/unknown work must reconcile in place')
    conditions=s.read_artifact(row['conditions_artifact_id']);old_budget=conditions['budget']
    if row['deadline']<=utc() or request['budget']['deadline']>row['deadline']:raise Forbidden('reprocessing cannot renew the prior deadline')
    if request['payload']['source_activity']!=conditions['source_activity'] or request['budget']['account_ref']!=conditions['source_budget']['account_ref']:raise Forbidden('reprocessing cannot change original activity/parent account')
    from digital_life.application.learning.work import origin_identity,CAPS
    if request['payload']['source']!=conditions['source']:raise Forbidden('reprocessing must retain the exact immutable original evidence/locator')
    if origin_identity(request['payload']['source'])!=conditions['origin_identity']:raise Forbidden('reprocessing source observation differs')
    if any(request['budget'][key]>old_budget[key] for key in CAPS):raise Forbidden('reprocessing cannot enlarge prior stage caps')
    from digital_life.application.learning.budget import ToolLearningBudget
    snapshot=ToolLearningBudget(s).check_work(row['id'])
    if any(reason not in ('work_completed','work_no_change','work_rejected','activity_completed') for reason in snapshot['block_reasons']):raise Forbidden('original exhausted/unknown/stopped resources block reprocessing')
    for dimension,key in (('attempts','max_attempts'),('input_tokens','max_input_tokens'),('output_tokens','max_output_tokens'),('tool_calls','max_tool_calls'),('scan','max_scan'),('items','max_items'),('bytes','max_bytes')):
        if request['budget'][key]>snapshot['remaining'][dimension]:raise Forbidden('new slice exceeds original remaining resources: '+dimension)
    return row,conditions


def _substance(s,request,old,conditions,kind,ordinal,new_baseline):
    old_method=s.read_artifact(old['method_artifact_id']);new_method=request['payload']['processing_method']
    from digital_life.application.learning.observation import validate_plan
    for method in (old_method,new_method):
        if method['name']!='tl-observation' or method['version']!='1' or method['request_ref']['status']!='known' or method['request_ref']['value']['kind']!='artifacts':raise Forbidden('reprocessing requires actual fixed old/new observation plans')
        validate_plan(s.read_artifact(method['request_ref']['value']['id']))
    if kind=='method_change':
        a,b=old_method['request_ref'],new_method['request_ref']
        if a['status']!='known' or b['status']!='known' or a['value']['kind']!='artifacts' or b['value']['kind']!='artifacts':raise Forbidden('method change needs actual old/new method artifacts')
        before=s.read_artifact(a['value']['id']);after=s.read_artifact(b['value']['id'])
        if c.fingerprint(before)==c.fingerprint(after):raise Forbidden('method name/version relabeling is not a substantive change')
    elif kind=='baseline_change':
        c.validate('VersionToken',new_baseline)
        obj=new_baseline['object']
        if obj['instance_id']!=s.instance_id or obj['kind'] not in ('tl_content','cognition_beliefs','cognition_concepts'):raise Forbidden('baseline must name current M03 content')
        row=s.row(obj['kind'],obj['id']);head=row['head_revision_id'] if obj['kind']=='tl_content' else row['current_revision_id']
        version=s.db.execute('SELECT revision_no FROM object_revision_registry WHERE instance_id=? AND id=? AND object_id=?',(s.instance_id,head,obj['id'])).fetchone()
        if version is None or version[0]!=new_baseline['revision']:raise Conflict('baseline is not the actual current owner head')
        previous=[]
        for r in s.db.execute("SELECT payload_artifact_id FROM tl_product WHERE work_id=? AND product_type='ComparisonAssessment'",(old['id'],)):
            previous.extend(s.read_artifact(r[0])['body']['baselines'])
        if not previous or new_baseline in previous:raise Forbidden('baseline change needs a previously compared distinct actual version')
    else:
        if ordinal<1:raise Forbidden('rehearsal needs a positive explicit practice ordinal')
    return old_method,new_method


class ControllerReprocessingAuthor:
    def __init__(self,store,bearer):self.s=store;self.bearer=bearer
    def authorize(self,request,*,kind,reason,ordinal,new_baseline=None):
        from digital_life.application.learning.runtime import authenticate_controller
        from digital_life.application.learning.work import origin_identity
        t.enum(kind,KINDS);t.string(reason);t.integer(ordinal)
        if not reason.strip() or len(reason)>2000:raise ContractError('bounded substantive reprocessing reason required')
        fixed=deepcopy(request)
        with dispatch_gate(self.s.root),self.s.tx():
            actor=authenticate_controller(self.s,self.bearer)
            self.s.assert_execution_allowed();policy,profile=_profile(self.s,fixed);old,conditions=_prior(self.s,fixed)
            if kind not in profile['kinds'] or not 1<=ordinal<=(profile['max_practice'] if kind=='rehearsal' else profile['max_reprocess']):raise Forbidden('kind/ordinal outside current finite policy')
            before,after=_substance(self.s,fixed,old,conditions,kind,ordinal,new_baseline)
            body={'contract':'TL-REPROCESSING-GRANT-1','request_digest':c.fingerprint(fixed),'previous_work_id':old['id'],'previous_work_row_revision':old['row_revision'],
                'origin_identity':origin_identity(fixed['payload']['source']),'source_activity':conditions['source_activity'],'parent_account':conditions['source_budget']['account_ref'],
                'kind':kind,'reason':reason,'ordinal':ordinal,'old_method':before,'new_method':after,
                'scope':deepcopy(self.s.read_artifact(after['request_ref']['value']['id'])['scope']),'new_baseline':slot(new_baseline),
                'current_policy':ref(self.s,policy),'issued_by':actor,'expires_at':min(profile['expires_at'],old['deadline']),
                'new_observation_count':0,'independent_sample_count':0,'gain':'not_measured'}
            key=body['origin_identity']+':'+kind+':'+str(ordinal)
            existing=self.s.db.execute('SELECT payload_artifact_id,id FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=?',(self.s.instance_id,SOURCE,key)).fetchone()
            if existing:
                if self.s.read_artifact(existing[0])!=body:raise Conflict('practice/reprocessing ordinal already bound to a different immutable request')
                return ref(self.s,existing[1])
            event=self.s.event('tool_learning.reprocessing_authorized',payload=body,source=SOURCE,key=key,lane='control')
            return ref(self.s,event)


def current_reprocessing_grant(s,request,previous):
    policy,profile=_profile(s,request);old,conditions=_prior(s,request)
    if old['id']!=previous['id']:raise Conflict('previous work differs')
    rows=s.db.execute('SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND source=? ORDER BY event_seq DESC LIMIT 257',(s.instance_id,SOURCE)).fetchall()
    if len(rows)>256:raise Forbidden('bounded reprocessing proof lookup exceeded')
    digest=c.fingerprint(request)
    for row in rows:
        body=s.read_artifact(row['payload_artifact_id'])
        if body.get('request_digest')!=digest:continue
        if body['previous_work_id']!=old['id'] or body['previous_work_row_revision']!=old['row_revision']:raise Conflict('prior final revision changed after authorization')
        if body['current_policy']!=ref(s,policy) or body['issued_by']!=s.config()['controller'] or body['expires_at']<=utc():raise Forbidden('current reprocessing authority changed or expired')
        kind=body['kind'];ordinal=body['ordinal']
        if kind not in profile['kinds'] or not 1<=ordinal<=(profile['max_practice'] if kind=='rehearsal' else profile['max_reprocess']):raise Forbidden('reprocessing proof exceeds current policy')
        _substance(s,request,old,conditions,kind,ordinal,body['new_baseline']['value'] if body['new_baseline']['status']=='known' else None)
        return {'grant_ref':ref(s,row['id']),'grant':body}
    raise Forbidden('no actual controller-authenticated reprocessing proof for this exact request')
