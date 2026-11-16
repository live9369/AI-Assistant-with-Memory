"""IM14 immutable effect records and explicit, independently checked shadow adoption.

Only the old sealed classification comparison is mapped here. It measures the
registered shadow snapshot, never the truth or utility of a TL content revision.
"""
from copy import deepcopy
from contextlib import contextmanager,nullcontext
import json
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc,dumps
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.application.learning.eligibility import ToolLearningEligibility,ref,slot
from digital_life.application.learning.budget import ToolLearningBudget,BudgetAuthority,DIMENSIONS
from digital_life.application.learning.observation import unknown
from digital_life.application.learning.experience_measurement import ExperienceMeasurement,CONTRACT,MEASURER
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore,StorageAuthority,StorageGrant,command_fingerprint
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate

METRIC_CONTRACT=CONTRACT+'/'+MEASURER+'/EM03'
METRIC={'name':'EM03 policy-qualified scalar gain','formula_version':MEASURER,
        'unit':'normalized-brier-difference','denominator_rule':'mean target cases; maximum retention regression veto',
        'missing_rule':'unknown if any paired probability or actual usage missing',
        'stratification':{'contract':CONTRACT,'policy':'target-improvement-with-retention-veto-v1','splits':['target','retention'],'independent_cases':'unknown'}}


def metric_contract(store,definition):
    """Resolve actual immutable metric fields, not an arbitrary protocol label."""
    ToolLearningStore(store).validate_ref(definition,expected_kind='metric_definitions')
    row=store.row('metric_definitions',definition['id'])
    for key,value in METRIC.items():
        actual=json.loads(row[key]) if key=='stratification' else row[key]
        if actual!=value:raise Forbidden('metric definition is not the sealed EM03 quantity')
    if row['valid_to'] is not None or row['valid_from'] is not None and row['valid_from']>utc():raise Forbidden('metric definition is not currently applicable')
    return METRIC_CONTRACT


def classification_scope(store,cases,classes,label_commitment,common_context=None,training_case_ids=()):
    """Scope comes from actual registered cases/quantity, never a caller label."""
    if not isinstance(cases,list) or any(not isinstance(case,dict) or set(case)!={'case_id','input','split'} for case in cases):raise ContractError('actual registered classification cases required')
    context={} if common_context is None else common_context
    return {'subject':slot(ref(store,store.config()['self_actor'])),'subject_label':slot('this instance frozen shadow snapshot'),
        'property':'EM03 policy-qualified classification gain','claim_target':'effect_statistic',
        'temporal':{'kind':'general_candidate','start':unknown('no population time generalization','not_measured'),'end':unknown('no population time generalization','not_measured'),'bounds':'unknown'},
        'conditions':slot({'contract':CONTRACT,'classes':classes,'case_ids':[case['case_id'] for case in cases],'case_splits':[case['split'] for case in cases],
            'case_inputs_sha256':c.fingerprint(cases),'label_commitment':label_commitment,'common_context_sha256':c.fingerprint(context),'training_case_ids':list(training_case_ids),
            'scoring_policy':'target-improvement-with-retention-veto-v1'}),
        'domain':slot('registered classification cases only'),'unit':slot('normalized-brier-difference'),'granularity':slot('one sealed paired run; independent population count unknown'),
        'coverage':{'state':'complete','domain':slot('registered target and retention cases'),'scanned':len(cases),'limit':len(cases),'truncated':False,'missing':[]},'exceptions':[],
        'limitations':['Controller-attested labels; semantic case independence unknown.','No TL content fidelity, retrieval, correct-use, world-fact or actual-selection claim.']}

def registered_scope(store,registration):
    return classification_scope(store,registration['cases'],registration['classes'],registration['label_commitment'],registration['common_context'],registration['training_case_ids'])


class EffectAuthority(StorageAuthority):
    def verify_effect(self,entry,request,work,stage):raise Forbidden('current effect owner is not configured')
    def source_token(self,entry,request,work):raise Forbidden('actual admitted source owner is not configured')
    def verify_binding(self,entry,request,work,registration):raise Forbidden('actual measurement/work binding is not configured')
    def verify_read_stage(self,entry,request,work):raise Forbidden('original-account actual read stage is not configured')
    def input_token(self,entry,request,origin):raise Forbidden('actual input version owner is not configured')


class _Storage(StorageAuthority):
    def __init__(self,service):self.r=service
    def verify(self,entry,operation,request,instance_id,stage):
        grant=self.r.authority.verify(entry,operation,request,instance_id,stage);work,_=self.r._guard(entry,request,stage)
        if stage=='commit':self.r._final_inputs(entry,request,work)
        return grant
    def project_response(self,entry,operation,request,response,instance_id,stage):
        projected=self.r.authority.project_response(entry,operation,request,response,instance_id,stage)
        work,_=self.r._guard(entry,request,stage)
        if stage=='commit':self.r._final_inputs(entry,request,work)
        return projected
    def verify_metric_contract(self,entry,operation,request,contract,definition,instance_id):
        if contract!=metric_contract(self.r.s,definition):raise Conflict('stored metric string differs from actual definition')


class ToolLearningEffects:
    def __init__(self,store,authority=None,budget_authority=None,eligibility_authority=None,clock=utc):
        self.s=store;self.authority=authority or EffectAuthority();self.clock=clock
        if not isinstance(self.authority,EffectAuthority):raise ContractError('trusted effect authority required')
        self.storage=ToolLearningStore(store,_Storage(self));self.budget=ToolLearningBudget(store,budget_authority,clock)
        self.eligibility=ToolLearningEligibility(store,eligibility_authority)
    def _qualify(self,entry,request,token,scope,stage):
        (self.eligibility._check if self.s.db.in_transaction else self.eligibility.check)(entry,request['principal'],token,scope,request['principal']['purpose'],request['principal']['recipient'],stage)
    def _source_scope(self,work):
        method=self.storage.read_artifact(work['method_artifact_id'],'Method')
        if method['name']!='tl-observation' or method['request_ref']['status']!='known':raise Forbidden('original work has no fixed observation scope')
        from digital_life.application.learning.observation import validate_plan
        return validate_plan(self.storage.read_artifact(method['request_ref']['value']['id']))['scope']
    def _guard(self,entry,request,stage):
        self.s.assert_execution_allowed();self.storage.validate_ref(request['payload']['work'],expected_kind='tl_work')
        work=self.s.row('tl_work',request['payload']['work']['id'])
        if request['principal']['module']!='M14' or request['principal']['purpose']!='evaluate':raise Forbidden('record_effect needs an actual M14 evaluate channel')
        if request['control']['cancelled'] or self.clock()>=min(work['deadline'],request['budget']['deadline']):raise Forbidden('effect work cancelled or expired')
        expected=request['expected']
        if expected['status']=='known' and (expected['value']['object']!=request['payload']['work'] or expected['value']['revision']!=work['row_revision']):raise Conflict('effect expected work revision changed')
        for key in ('source_activity_id','learning_activity_id'):
            activity=self.s.row('activities',work[key])
            if activity['cancel_requested_at'] or activity['state'] in ('cancelled','failed','paused'):raise Forbidden('effect activity is not currently usable')
        snapshot=self.budget.check_work(work['id'],request['budget'])
        allowed={'attempts_exhausted','work_completed','work_no_change','work_rejected'}
        if set(snapshot['block_reasons'])-allowed:raise Forbidden('original effect budget blocked: '+','.join(snapshot['block_reasons']))
        for callback in (self.authority.verify_effect,self.authority.verify_read_stage):
            result=callback(entry,deepcopy(request),dict(work),stage) if callback==self.authority.verify_effect else callback(entry,deepcopy(request),dict(work))
            if result is not None:raise Forbidden('effect owner must attest by successful return')
        source=self.authority.source_token(entry,deepcopy(request),dict(work));c.validate('VersionToken',source)
        self._qualify(entry,request,source,self._source_scope(work),stage)
        metric_contract(self.s,request['payload']['assessment']['metric_definition'])
        self.s.assert_execution_allowed()
        return work,source
    def _report(self,entry,request,work):
        assessment=request['payload']['assessment'];state=assessment['measurement_state'];measurement=assessment['measurement_ref']
        if measurement['status']!='known':
            if state not in ('not_measured','not_applicable'):raise Forbidden('incomplete/invalidated assessment needs real report evidence')
            if any(assessment[k]['status']=='known' for k in ('gain','retention_components','sample_counts','independence','usage')):raise Forbidden('unmeasured effect cannot assert measured components')
            referenced=[assessment[name]['value'] for name in ('baseline_ref','candidate_ref') if assessment[name]['status']=='known']+list(assessment['method_refs'])
            return referenced,None
        self.storage.validate_ref(measurement['value'],expected_kind='runtime_events')
        m=ExperienceMeasurement(self.s);event=self.s.row('runtime_events',measurement['value']['id'])
        if event['source']!='experience-measurement' or event['event_type']!='learning.measurement_report':raise Forbidden('not a real sealed measurement report')
        original=self.storage.read_artifact(event['payload_artifact_id']);registration=m._registered(original['run_ref'])
        if assessment['case_scope']!=registered_scope(self.s,registration):raise Conflict('effect case scope differs from actual registered classification quantity and cases')
        if self.authority.verify_binding(entry,deepcopy(request),dict(work),deepcopy(registration)) is not None:raise Forbidden('binding owner must not return a boolean')
        invalid=m._get('invalidated',original['run_ref'])
        if state=='invalidated':
            if invalid is None or assessment['gain']['status']=='known':raise Forbidden('invalidated effect needs actual invalidation and unknown gain')
            expected=dict(m._calculate(registration),contract_id=CONTRACT,instance_id=self.s.instance_id)
            if dumps(expected)!=dumps(original):raise Forbidden('invalidated historical report differs from sealed evidence')
            report=original
        else:
            if invalid is not None:raise Forbidden('measurement has been invalidated')
            report=m.checked_report(measurement['value']['id'],True)
            expected_state='measured' if report['status']=='measured' else 'incomplete'
            if state!=expected_state:raise Conflict('assessment state differs from actual report')
        expected=assessment_from_report(self.s,measurement['value'],assessment['metric_definition'],assessment['case_scope'],invalidated=state=='invalidated')
        if dumps(expected)!=dumps(assessment):raise Conflict('assessment differs from actual sealed report projection')
        return [measurement['value'],*report_inputs(self.s,registration,report,invalid)],report
    def _final_inputs(self,entry,request,work):
        inputs,_=self._report(entry,request,work);scope=request['payload']['assessment']['case_scope']
        for origin in inputs:self._qualify(entry,request,self.authority.input_token(entry,request,origin),scope,'final_effect_inputs')
    def record_effect(self,entry,envelope):
        c.validate_request('record_effect',envelope);request=c.loads(dumps(envelope))
        if self.s.db.in_transaction:raise Conflict('record_effect requires its own transaction')
        with dispatch_gate(self.s.root):
            work,source=self._guard(entry,request,'begin');inputs,report=self._report(entry,request,work)
            scope=request['payload']['assessment']['case_scope'];tokens=[source]
            for origin in inputs:
                token=self.authority.input_token(entry,request,origin)
                # A barrier on any original input is a permanent qualification check,
                # never evaded by substituting its current epoch.
                self._qualify(entry,request,token,scope,'effect_input');tokens.append(token)
            metric=request['payload']['assessment']['metric_definition'];tokens.append({'object':metric,'revision':0,'epoch':self.eligibility.current_epoch(metric,scope)})
            identity=c.fingerprint({'work':request['payload']['work'],'assessment':request['payload']['assessment'],'contract':METRIC_CONTRACT})
            def apply(tx):
                self._guard(entry,request,'write');self._report(entry,request,work)
                for token in tokens:self._qualify(entry,request,token,scope,'effect_commit')
                old=self.s.db.execute("SELECT e.id FROM tl_effect e JOIN tl_product p ON p.instance_id=e.instance_id AND p.id=e.product_id WHERE e.instance_id=? AND p.work_id=? AND p.processing_identity=?",(self.s.instance_id,work['id'],identity)).fetchone()
                if old:ident=old[0];disposition='reused'
                else:
                    conditions=self.storage.read_artifact(work['conditions_artifact_id']);evidence=conditions['source'];method=self.storage.read_artifact(work['method_artifact_id'],'Method')
                    check=lambda state:{'state':state,'checker':deepcopy(request['principal']),'method':deepcopy(method),'at':self.clock(),'targets':[],'reason':'none','basis_refs':[]}
                    product={'contract':'TL-LOOP-0.1','schema_revision':1,'product_id':identifier(),'instance_id':self.s.instance_id,'producer':deepcopy(request['principal']),
                        'work_ref':request['payload']['work'],'purpose':'evaluate','method':method,'created_at':self.clock(),'source_refs':[evidence],
                        'derivation_links':[],'limitations':['Classification of the sealed shadow snapshot only; no TL content truth, retrieval, correct-use or selection claim.','Controller-attested labels; semantic independence is unproved.'],
                        'missing_items':[],'access_dependencies':deepcopy(evidence['access_dependencies']),'revision_links':[],'processing_identity':{'algorithm':'sha256','hex':identity},'downstream_refs':[],
                        'checks':{'source_check':check('readable'),'locator_check':check('not_checked'),'support_check':check('not_assessed'),'readiness':check('not_applicable')},'product_type':'EffectAssessment','body':deepcopy(request['payload']['assessment'])}
                    artifact=tx.put_artifact(product,'Product');product_id=tx.insert('tl_product',id=product['product_id'],work_id=work['id'],product_type='EffectAssessment',payload_artifact_id=artifact,processing_identity=identity,source_fingerprint=c.fingerprint(evidence))
                    ident=tx.insert('tl_effect',work_id=work['id'],product_id=product_id,measurement_ref_id=request['payload']['measurement']['value']['id'] if request['payload']['measurement']['status']=='known' else None,
                        metric_contract=metric_contract(self.s,metric),state=request['payload']['assessment']['measurement_state'],payload_artifact_id=tx.put_artifact(request['payload']['assessment'],'EffectAssessment'))
                    from digital_life.application.learning.observation import ToolLearningObservation
                    for consumer in (ref(self.s,ident),ref(self.s,product_id),ref(self.s,artifact),ref(self.s,self.s.row('tl_effect',ident)['payload_artifact_id'])):
                        for i,token in enumerate(tokens):
                            for relation in ('read','delete'):ToolLearningObservation._derived_dependency(self,tx,consumer,token,self._source_scope(work) if i==0 else scope,relation,'/effect_inputs/'+str(i),request)
                    disposition='applied'
                return {'command_id':request['command_id'],'operation':'record_effect','disposition':disposition,'owner':'M14','result_refs':[ref(self.s,ident)],'current':slot(),'reason':'none','error_code':'NONE',
                    'coverage':{'state':'complete','domain':slot('sealed classification effect'),'scanned':len(tokens),'limit':len(tokens),'truncated':False,'missing':[]},'retry':{'allowed':False,'condition':slot(),'resume_work':slot()},'committed_at':slot(self.clock())}
            return self.storage.execute(entry,'record_effect',request,apply)


def report_inputs(store,registration,report,invalid=None):
    """All actual registered/prediction/label/dispatch and snapshot ancestry."""
    m=ExperienceMeasurement(store);keys=[m._get('registered',registration['run_ref'])['id'],*report['prediction_refs'],report['labels_ref']]
    bound=store.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='tl.effect.binding' AND source_event_id=? AND event_type='effect.measurement_bound'",(store.instance_id,registration['run_ref'])).fetchone()
    if bound:
        binding=store.read_artifact(bound['payload_artifact_id']);keys.extend([bound['id'],binding['baseline']['id'],binding['candidate']['id']])
    if invalid:keys.append(invalid['id'])
    for prediction in report['prediction_refs']:
        value=store.read_artifact(store.row('runtime_events',prediction)['payload_artifact_id']);keys.append(value['dispatch_ref'])
        if value.get('strict_result_ref'):
            result=store.row('thought_results',value['strict_result_ref']['id']);thought=store.row('thought_requests',result['request_id'])
            keys.extend([result['id'],result['response_artifact_id'],thought['id'],thought['request_artifact_id']])
            invocation=store.db.execute("SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND source='strict.provider.invocation' AND source_event_id=? AND event_type='strict.provider.invocation'",(store.instance_id,result['attempt_id'])).fetchone()
            if invocation:keys.extend([invocation['id'],invocation['payload_artifact_id']])
    from digital_life.application.services.learning import Learning
    opportunity,result=Learning(store)._experience_opportunity(registration['opportunity_ref'])
    keys.extend(opportunity['source_refs']);keys.extend([result['id'],result['receipt_artifact_id'],result['outcome_ref']])
    # Each stored shadow head carries its assessment and source ancestry.
    pending=[v['revision_ref'] for v in registration['experience_snapshot'].get('experience_versions',{}).values()]
    seen=set()
    while pending:
        key=pending.pop()
        if key in seen:continue
        seen.add(key)
        if len(seen)>256:raise Forbidden('measurement snapshot ancestry exceeds bounded verifier')
        event=store.row('runtime_events',key);value=store.read_artifact(event['payload_artifact_id']);keys.append(key)
        keys.extend(value.get('source_refs',[]))
        for field in ('assessment_ref','proposal_ref'):
            if value.get(field):pending.append(value[field])
        if value.get('measurement_ref'):
            prior=m.checked_report(value['measurement_ref']);r=m._registered(prior['run_ref'])
            keys.extend([value['measurement_ref'],*prior['prediction_refs'],prior['labels_ref'],m._get('registered',r['run_ref'])['id']])
            pending.extend(v['revision_ref'] for v in r['experience_snapshot'].get('experience_versions',{}).values())
    return [ref(store,key) for key in dict.fromkeys(keys) if key is not None]


def assessment_from_report(store,measurement,definition,scope,invalidated=False):
    """Exact old-scale projection. Unknown independent count stays unknown."""
    m=ExperienceMeasurement(store);event=store.row('runtime_events',measurement['id']);report=store.read_artifact(event['payload_artifact_id']);r=m._registered(report['run_ref'])
    if event['source']!='experience-measurement' or event['event_type']!='learning.measurement_report':raise Forbidden('effect projection needs a real measurement report')
    if invalidated:
        if m._get('invalidated',r['run_ref']) is None or dumps(report)!=dumps(dict(m._calculate(r),contract_id=CONTRACT,instance_id=store.instance_id)):raise Forbidden('invalidated projection has no matching historical sealed report')
    else:report=m.checked_report(measurement['id'])
    if scope!=registered_scope(store,r):raise Conflict('effect projection cannot relabel actual classification case scope')
    registration=ref(store,m._get('registered',r['run_ref'])['id'])
    bound=store.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='tl.effect.binding' AND source_event_id=? AND event_type='effect.measurement_bound'",(store.instance_id,r['run_ref'])).fetchone()
    binding=store.read_artifact(bound['payload_artifact_id']) if bound else {}
    state='invalidated' if invalidated else 'measured' if report['status']=='measured' else 'incomplete'
    gain=slot(report['gain']) if state=='measured' else unknown('measurement invalidated' if invalidated else 'measurement incomplete','not_measured',status='unknown')
    result={'measurement_state':state,'measurement_ref':slot(measurement),'baseline_ref':slot(binding.get('baseline',registration)),'candidate_ref':slot(binding.get('candidate',registration)),'method_refs':[registration],
        'metric_definition':deepcopy(definition),'case_scope':deepcopy(scope),'gain':gain,
        'retention_components':slot({'target_gain':report['target_gain'],'retention_regression':report['retention_regression'],'scoring_policy':report['scoring_policy']}),
        'sample_counts':slot({'registered_cases':report['case_count'],'measurable_cases':report['case_count']-len(report['unknown_case_ids']),'unknown_case_ids':report['unknown_case_ids']}),
        'independence':slot({'independent_cases':report['independent_cases'],'label_authority':report['label_authority'],'semantic_independence':'unknown'}),
        'usage':slot({'actual_tokens':report['actual_tokens'],'model_port_calls':report['model_port_calls'],'elapsed_seconds':sum(store.read_artifact(store.row('runtime_events',p)['payload_artifact_id'])['elapsed_seconds'] for p in report['prediction_refs']),'scope':'registered paired predictions only; record validation billed separately'})}
    c.validate('EffectAssessment',result);return result


class LocalEffectAuthority(EffectAuthority):
    """Current-process capability composition; constructed from actual owners."""
    def __init__(self,sdk):self.r=sdk
    def verify(self,entry,operation,request,instance_id,stage):
        self.r.check(entry,request);return StorageGrant('M14',frozenset(('tl_product','tl_effect','tl_dependency')))
    def project_response(self,entry,operation,request,response,instance_id,stage):self.r.check(entry,request);return response
    def verify_effect(self,entry,request,work,stage):
        self.r.check(entry,request)
        if request['payload']['assessment']['measurement_state']=='not_applicable':raise Forbidden('EM03 applicability exemption has no configured independent owner')
    def verify_read_stage(self,entry,request,work):
        active=self.r.active
        if active is None or active['entry']!=entry or active['fingerprint']!=command_fingerprint(request):raise Forbidden('effect lacks its exact entered original-account read occurrence')
    def source_token(self,entry,request,work):
        self.r.check(entry,request);source=self.r.storage.read_artifact(work['conditions_artifact_id'])['source']
        if source['source_kind']!='tool_result' or source['source']['kind']!='action_results':raise Forbidden('classification adapter requires the actual original tool result')
        result=self.r.s.row('action_results',source['source']['id'])
        if result['receipt_artifact_id']!=source['artifact']['id'] or source['original_result']!=slot(source['source']):raise Conflict('effect source is not its actual original receipt')
        if self.r.s.row('artifacts',source['artifact']['id'])['hash']!=source['digest']['hex']:raise Conflict('admitted effect source digest differs')
        self.r.storage.read_artifact(source['artifact']['id'])
        original=self.r.storage.read_artifact(work['control_artifact_id'],'Control')
        fixed=[token for token in original['source_epochs'] if token['object']==source['source']]
        if len(fixed)!=1:raise Forbidden('original work has no unique fixed source epoch')
        return deepcopy(fixed[0])
    def input_token(self,entry,request,origin):
        measurement=request['payload']['measurement']
        if measurement['status']=='known':
            report=self.r.storage.read_artifact(self.r.s.row('runtime_events',measurement['value']['id'])['payload_artifact_id']);binding=self.r.binding(report['run_ref'])
            for token in binding['input_tokens']:
                if token['object']==origin:return token
        return self.r.token(origin,request['payload']['assessment']['case_scope'])
    def verify_binding(self,entry,request,work,registration):
        self.r.check(entry,request);binding=self.r.binding(registration['run_ref'])
        assessment=request['payload']['assessment']
        if binding['work']!=request['payload']['work'] or binding['scope']!=assessment['case_scope'] or registration['parent_activity_ref']!=work['source_activity_id']:raise Conflict('measurement is not this work/parent/case scope')
        for arm,key in (('without_experience','baseline'),('with_experience','candidate')):
            context=dict(registration['common_context'])
            if arm=='with_experience':context['cognitive_experience']=registration['experience_snapshot']
            self.r.storage.validate_ref(binding[key],expected_kind='artifacts')
            if self.r.storage.read_artifact(binding[key]['id'])!={'arm':arm,'context':context,'classes':registration['classes']}:raise Conflict('actual registered comparison arm differs from baseline/candidate artifact')
        conditions=self.r.storage.read_artifact(work['conditions_artifact_id'])
        if binding['source']!=conditions['source']:raise Conflict('measurement source differs from original work')
        m=ExperienceMeasurement(self.r.s);registered=m._get('registered',registration['run_ref']);event=self.r.s.row('runtime_events',binding['event'])
        for prediction in m._predictions(registration).values():
            dispatch=self.r.s.row('runtime_events',prediction['payload']['dispatch_ref'])
            if not self.r.s.row('runtime_events',registered['id'])['event_seq']<event['event_seq']<dispatch['event_seq']:raise Forbidden('work binding must precede every actual prediction')
        from digital_life.application.services.learning import Learning
        opportunity,result=Learning(self.r.s)._experience_opportunity(registration['opportunity_ref'])
        if result['id']!=conditions['source']['source']['id']:raise Conflict('registered opportunity does not measure the admitted original tool result')
        for token in binding['input_tokens']:
            self.r.service._qualify(entry,request,token,binding['source_scope'] if token==binding['input_tokens'][0] else binding['scope'],'effect_bound_original_input')


class LocalEffects:
    """Explicit M14 SDK for recording and M03's existing independent entry.

    Registration does not claim that a TL content revision was in the measured
    arm. Both arms are exactly the legacy frozen shadow snapshot experiment.
    """
    def __init__(self,owners):
        from digital_life.application.learning.runtime_owners import LocalRuntimeOwners
        if not isinstance(owners,LocalRuntimeOwners):raise ContractError('actual LocalRuntimeOwners required')
        self.o=owners;self.s=owners.s;self.active=None;self.storage=ToolLearningStore(self.s)
        self.active_evaluation=None;self.budget_authority=EffectBudget(self);self.budget=ToolLearningBudget(self.s,self.budget_authority)
        self.service=ToolLearningEffects(self.s,LocalEffectAuthority(self),self.budget_authority,EffectEligibility(owners))
        self.service.eligibility.max_nodes=4096;self.service.eligibility.max_rows=65536
    def token(self,origin,scope):
        if origin['kind']=='evidence_items':return {'object':origin,'revision':0,'epoch':self.service.eligibility.current_epoch(origin,scope)}
        return self.o.token(origin,scope)
    def check(self,entry,request):
        self.o.check(entry,request['principal'])
        active=self.s.rows('policy_epochs')[0]
        if request['instance_id']!=self.s.instance_id or request['control']['runtime_epoch']!=self.o.identity.epoch or request['control']['policy']['object']['id']!=active['policy_version_id'] or request['control']['policy']['epoch']!=active['epoch']:raise Conflict('effect current control binding changed')
    @contextmanager
    def read_stage(self,entry,request):
        if self.active is not None:raise Conflict('effect read occurrences cannot nest')
        with dispatch_gate(self.s.root):
            self.check(entry,request);work=self.s.row('tl_work',request['payload']['work']['id']);snapshot=self.budget.check_work(work['id'],request['budget'])
            amounts={key:0 for key in DIMENSIONS}
            for key in ('scan','items','bytes','elapsed_ms'):amounts[key]=snapshot['remaining'][key]
            with self.s.tx():
                context=self.s.insert('context_snapshots',activity_id=work['learning_activity_id'],context_schema='tl-effect-read-1',attributes_json={})
                run=self.s.insert('memory_retrieval_runs',activity_id=work['learning_activity_id'],context_id=context,query='sealed effect validation',retriever_version='tl-effect-1')
            operation=ref(self.s,run);binding={'contract':'TL-EFFECT-READ-OCCURRENCE-1','request_fingerprint':command_fingerprint(request),'account_ref':deepcopy(request['budget']['account_ref']),'occurrence_id':identifier()}
            self.active_evaluation={'entry':entry,'work_id':work['id'],'operation':operation,'binding':deepcopy(binding),'request':deepcopy(request)}
            try:
                with self.budget.evaluation_read_context(entry,work['id'],operation,binding) if work['state'] in ('completed','no_change','rejected') else nullcontext():
                    reservation=self.budget.reserve(entry,work['id'],operation,'retrieval',amounts,request_budget=request['budget'],reservation_key='effect-read:'+run)
                    self.budget.record_entry(entry,work['id'],reservation['id'],{'contract':'TL-RUNTIME-STAGE-READ-ENTRY-1','operation':operation,'occurrence_id':binding['occurrence_id']})
            finally:self.active_evaluation=None
            meter=PhysicalReadMeter(reservation['reserved'],min(work['deadline'],request['budget']['deadline']))
            self.active={'entry':entry,'fingerprint':command_fingerprint(request),'meter':meter}
            try:
                with meter.installed(self.s):yield
            finally:
                self.active=None;actual=meter.usage();self.o.settlements[reservation['id']]={'actual':deepcopy(actual)}
                self.budget.settle(entry,work['id'],reservation['id'],actual)
    def record_effect(self,entry,request):
        with self.read_stage(entry,request):return self.service.record_effect(entry,request)
    def binding(self,run):
        row=self.s.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='tl.effect.binding' AND source_event_id=? AND event_type='effect.measurement_bound'",(self.s.instance_id,run)).fetchone()
        if row is None:raise Forbidden('measurement has no actual pre-dispatch TL binding')
        value=self.storage.read_artifact(row['payload_artifact_id'])
        if value.get('contract')!='TL-EFFECT-BINDING-1' or value.get('run')!=run:raise Conflict('measurement binding payload mismatch')
        value['event']=row['id'];return value
    def register(self,entry,request,opportunity_ref,cases,classes,label_commitment,**kwargs):
        """Bind a new real registration before any prediction; never dispatches."""
        with self.read_stage(entry,request),dispatch_gate(self.s.root):
            work,token=self.service._guard(entry,request,'register')
            expected_scope=classification_scope(self.s,cases,classes,label_commitment,kwargs.get('common_context'),kwargs.get('training_case_ids',()))
            if request['payload']['assessment']['case_scope']!=expected_scope:raise Conflict('measurement registration requires its actual canonical classification scope')
            source=self.storage.read_artifact(work['conditions_artifact_id'])['source']
            from digital_life.application.services.learning import Learning
            opportunity,result=Learning(self.s)._experience_opportunity(opportunity_ref)
            if result['id']!=source['source']['id']:raise Forbidden('measurement opportunity differs from admitted result')
            m=ExperienceMeasurement(self.s)
            with self.s.tx():
                run=m.register(opportunity_ref,cases,classes,label_commitment,self.s.config()['controller'],**kwargs);registration=m._registered(run)
                if registration['parent_activity_ref']!=work['source_activity_id']:raise Conflict('measurement is not charged to original source activity')
                scope=request['payload']['assessment']['case_scope'];tokens=[token]
                keys=list(opportunity['source_refs'])
                # Snapshot dependencies are fixed before the first paired call.
                for head in registration['experience_snapshot'].get('experience_versions',{}).values():
                    event=self.s.row('runtime_events',head['revision_ref']);payload=self.storage.read_artifact(event['payload_artifact_id']);keys.append(event['id'])
                    if payload.get('assessment_ref'):
                        assessment=self.s.row('runtime_events',payload['assessment_ref']);a=self.storage.read_artifact(assessment['payload_artifact_id']);keys.extend([assessment['id'],*a['source_refs']])
                        if a.get('measurement_ref'):keys.append(a['measurement_ref'])
                for key in dict.fromkeys(keys):
                    value=self.token(ref(self.s,key),scope);self.service._qualify(entry,request,value,scope,'effect_registration_input');tokens.append(value)
                baseline=ref(self.s,self.s.artifact({'arm':'without_experience','context':registration['common_context'],'classes':registration['classes']}))
                candidate=ref(self.s,self.s.artifact({'arm':'with_experience','context':dict(registration['common_context'],cognitive_experience=registration['experience_snapshot']),'classes':registration['classes']}))
                event=self.s.event('effect.measurement_bound',payload={'contract':'TL-EFFECT-BINDING-1','run':run,'work':request['payload']['work'],'source':source,'source_scope':self.service._source_scope(work),'scope':scope,'principal':deepcopy(request['principal']),'baseline':baseline,'candidate':candidate,'input_tokens':tokens,
                    'measured_candidate':'registered shadow experience_snapshot; no TL content revision'},source='tl.effect.binding',key=run,activity=work['learning_activity_id'])
                from digital_life.application.learning.engine import _dependency
                for consumer in (ref(self.s,event),ref(self.s,self.s.row('runtime_events',event)['payload_artifact_id']),ref(self.s,m._get('registered',run)['id']),baseline,candidate):
                    for index,value in enumerate(tokens):
                        for relation in ('read','delete'):_dependency(self.s,consumer,value,self.service._source_scope(work) if index==0 else scope,relation,'/effect_registration/'+str(index),'evaluate')
            return run
    def adopt_shadow(self,entry,request,effect_ref,actor):
        """M03 explicit independent validation; held under the same final gate."""
        with self.read_stage(entry,request),dispatch_gate(self.s.root):
            self.o.check(entry,request['principal'])
            if request['principal']['module']!='M03' or actor!=self.s.config()['controller']:raise Forbidden('explicit M03 channel and controller required')
            row=self.s.row('tl_effect',effect_ref['id']);self.storage.validate_ref(effect_ref,expected_kind='tl_effect')
            if row['work_id']!=request['payload']['work']['id'] or row['measurement_ref_id'] is None:raise Forbidden('effect has no measured report for this work')
            assessment=self.storage.read_artifact(row['payload_artifact_id'],'EffectAssessment')
            metric_contract(self.s,assessment['metric_definition'])
            if assessment!=request['payload']['assessment'] or row['state'] not in ('measured','incomplete'):raise Conflict('shadow adoption does not match effect')
            token=self.o.token(ref(self.s,row['product_id']),assessment['case_scope'])
            self.service._qualify(entry,request,token,assessment['case_scope'],'M03_shadow_adoption')
            # Existing M03 validator recomputes the report and writes its own
            # CAS version. Neither TL content nor selection rights are written.
            return ExperienceMeasurement(self.s).adopt_shadow(row['measurement_ref_id'],actor)


def _check_measurement_protection(store,report_ref,registration,report):
    """Read-only conservative F1 guard used by the real legacy M03 validator.

    No tables/old schema -> original behavior. An intersecting registered input
    barrier excludes the sample, preserving its historical value. This does not
    restore permissions or infer scientific invalidity from an exclusion.
    """
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tl_barrier'").fetchone() is None:return
    # Gather bounded concrete inputs, then walk all actual read/support/derive
    # ancestry regardless of a caller purpose. Conservative scope exclusion is
    # deliberate for legacy records lacking field-level usage manifests.
    origins=report_inputs(store,registration,report)
    from digital_life.application.services.memory import Memory
    for origin in origins:
        if origin['kind'] in ('memory_items','memory_revisions'):
            row=store.row(origin['kind'],origin['id']);memory=origin['id'] if origin['kind']=='memory_items' else row['memory_id']
            allowed=Memory(store).readers(memory)
            if store.row('memory_items',memory)['state']!='active' or store.config()['self_actor'] not in allowed or store.config()['controller'] not in allowed:raise Forbidden('measurement original input permission no longer allows shadow inspection')
    pending=[report_ref,*[v['id'] for v in origins]];seen=set()
    binding=store.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='tl.effect.binding' AND source_event_id=?",(store.instance_id,registration['run_ref'])).fetchone()
    if binding:
        pending.append(binding['id']);fixed=store.read_artifact(binding['payload_artifact_id'])
        eligibility=ToolLearningEligibility(store)
        for token in fixed['input_tokens']:
            if eligibility.current_epoch(token['object'],fixed['source_scope'] if token==fixed['input_tokens'][0] else fixed['scope'])!=token['epoch']:raise Forbidden('measurement original input epoch changed')
    while pending:
        key=pending.pop()
        if key in seen:continue
        seen.add(key)
        if len(seen)>4096:raise Forbidden('measurement protection ancestry is incomplete')
        if store.db.execute("SELECT 1 FROM tl_barrier WHERE instance_id=? AND source_ref_id=? AND state='active' LIMIT 1",(store.instance_id,key)).fetchone():raise Forbidden('measurement original input has an active protection barrier')
        rows=store.db.execute("SELECT source_ref_id FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? AND relation IN ('read','support','derive') LIMIT 4097",(store.instance_id,key)).fetchall()
        if len(rows)>4096:raise Forbidden('measurement protection dependency bound exceeded')
        pending.extend(v[0] for v in rows)


from digital_life.application.learning.runtime_owners import LocalEligibility
class EffectEligibility(LocalEligibility):
    """Evidence owner restricted to actual original tool-result evidence."""
    def verify_version(self,entry,principal,token,stage):
        if token['object']['kind']=='evidence_items':
            self.o.check(entry,principal)
            if token['revision']!=0:raise Conflict('immutable tool evidence has no such revision')
            self.o.s.row('evidence_items',token['object']['id']);return
        return super().verify_version(entry,principal,token,stage)
    def verify(self,entry,principal,token,scope,purpose,recipient,stage):
        if token['object']['kind']=='evidence_items':
            self.o.check(entry,principal);e=self.o.s.row('evidence_items',token['object']['id'])
            row=self.o.s.db.execute('SELECT * FROM action_results WHERE instance_id=? AND outcome_ref=? LIMIT 2',(self.o.s.instance_id,e['id'])).fetchall()
            if len(row)!=1 or e['artifact_id']!=row[0]['receipt_artifact_id']:raise Forbidden('evidence is not the unique actual tool-result receipt')
            self.o.source_access(entry,principal,ref(self.o.s,row[0]['id']),scope);return
        return super().verify(entry,principal,token,scope,purpose,recipient,stage)


class EffectBudget(BudgetAuthority):
    def __init__(self,sdk):self.r=sdk
    def verify_budget(self,*args):return self.r.o.budget.verify_budget(*args)
    def verify_entry(self,*args):return self.r.o.budget.verify_entry(*args)
    def verify_settlement(self,*args):return self.r.o.budget.verify_settlement(*args)
    def verify_evaluation_read(self,entry,work,operation,binding,stage):
        active=self.r.active_evaluation
        if active is None or active['entry']!=entry or active['work_id']!=work['id'] or active['operation']!=operation or active['binding']!=binding:raise Forbidden('no actual sealed effect read occurrence')
        request=active['request'];self.r.check(entry,request)
        c.validate_request('record_effect',request)
        if request['principal']['module'] not in ('M14','M03') or request['principal']['purpose']!='evaluate' or request['payload']['work']['id']!=work['id'] or request['budget']['account_ref']['id']!=work['budget_account_id'] or binding['request_fingerprint']!=command_fingerprint(request):raise Forbidden('effect read occurrence does not match original module/work/account')
        if self.r.s.row('memory_retrieval_runs',operation['id'])['activity_id']!=work['learning_activity_id']:raise Forbidden('effect read run belongs to another activity')


from contextvars import ContextVar
_MEASUREMENT_STACK=ContextVar('tl_measurement_protection_stack',default=())
def check_measurement_protection(store,report_ref,registration,report):
    stack=_MEASUREMENT_STACK.get();key=(str(store.root),store.instance_id,report_ref)
    if key in stack or len(stack)>=16:raise Forbidden('measurement snapshot ancestry is cyclic or exceeds the verifier bound')
    token=_MEASUREMENT_STACK.set(stack+(key,))
    try:return _check_measurement_protection(store,report_ref,registration,report)
    finally:_MEASUREMENT_STACK.reset(token)
