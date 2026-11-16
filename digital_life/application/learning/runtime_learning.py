"""Current-process composition of real C0, four products, C1 and C2.

Only scoped source reports have a local scientific owner here. Unsupported
claims remain candidates; neither an LLM nor controller approval supplies truth.
"""
from copy import deepcopy
import math
import time
from contextlib import contextmanager,nullcontext
from datetime import datetime
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,identifier,utc,dumps
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.application.learning.eligibility import ref,slot
from digital_life.application.learning.engine import source_scope,_dependency
from digital_life.application.learning.budget import ToolLearningBudget,DIMENSIONS,CAPS,BudgetAuthority
from digital_life.application.learning.work import ToolLearningWork,WorkAuthority,AdmissionAllocation
from digital_life.application.learning.observation import ToolLearningObservation,ObservationAuthority,ObservationThoughtPort,validate_plan
from digital_life.application.learning.acceptance import ToolLearningAcceptance,AcceptanceAuthority,OWNERS
from digital_life.application.learning.representation import ToolLearningRepresentation,RepresentationAuthority
from digital_life.application.learning.recovery import ToolLearningRecovery,RecoveryAuthority
from digital_life.infrastructure.persistence.tool_learning_store import StorageGrant,command_fingerprint
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.infrastructure.llm.fresh_learning import FreshLearningProvider


class _Work(WorkAuthority):
    def __init__(self,coordinator):self.r=coordinator
    def verify(self,entry,operation,request,instance_id,stage):
        self.r.check(entry,request,'M14');return StorageGrant('M14',frozenset(('tl_work','tl_dependency')))
    def project_response(self,entry,operation,request,response,instance_id,stage):self.r.check(entry,request,'M14');return response
    def verify_source_origin(self,entry,request,source):self.r.check(entry,request,'M14');self.r.verify_source(entry,request,source)
    def source_lineage(self,entry,request,source):return [{'token':self.r.verify_source(entry,request,source),'scope':deepcopy(self.r.plan(request)['scope'])}]
    def verify_source_lineage(self,entry,request,lineage):
        if lineage!=self.source_lineage(entry,request,request['payload']['source']):raise Conflict('C0 lineage differs from the actual original source')
    def admission_allocation(self,entry,request,source_activity,parent_account):
        self.r.check(entry,request,'M14');loaded=self.r.k.budget._load(source_activity['id'])
        if loaded[2]['id']!=parent_account['id']:raise Forbidden('learning allocation names another original parent account')
        return AdmissionAllocation(deepcopy(loaded[3]['budget']))
    def verify_endpoint(self,entry,request,work,intent):
        self.r.check(entry,request,'M14');target=intent['target']
        if target=='awaiting_decision':
            if not self.r.s.db.execute("SELECT 1 FROM tl_product WHERE instance_id=? AND work_id=? AND product_type='UpdateProposal'",(self.r.s.instance_id,work['id'])).fetchone():raise Forbidden('no actual proposal exists')
        elif target=='handoff_pending':
            if not self.r.s.db.execute("SELECT 1 FROM tl_handoff WHERE instance_id=? AND work_id=?",(self.r.s.instance_id,work['id'])).fetchone():raise Forbidden('no actual handoff obligation exists')
        elif target=='completed':
            rows=self.r.s.db.execute('SELECT state FROM tl_handoff WHERE instance_id=? AND work_id=?',(self.r.s.instance_id,work['id'])).fetchall()
            if not rows or any(row[0]!='published' for row in rows):raise Forbidden('not all actual representations are published')
        elif target in ('rejected','no_change'):
            operation='reject' if target=='rejected' else 'reuse'
            if not self.r.s.db.execute('SELECT 1 FROM tl_decision WHERE instance_id=? AND work_id=? AND operation=?',(self.r.s.instance_id,work['id'],operation)).fetchone():raise Forbidden('work terminal projection has no matching actual decision')
        else:raise Forbidden('unproved work endpoint')


class _Observation(ObservationAuthority):
    def __init__(self,r):self.r=r
    def verify(self,entry,operation,request,instance_id,stage):self.r.check(entry,request,'M14');return StorageGrant('M14',frozenset(('tl_work','tl_product','tl_dependency')))
    def project_response(self,entry,operation,request,response,instance_id,stage):self.r.check(entry,request,'M14');return response
    def verify_observation(self,entry,request,work,plan,stage):
        self.r.check(entry,request,'M14');self.r.stage_context(entry,request);self.r.verify_source(entry,request,request['payload']['source'])
        if plan['scope']['claim_target']!='source_report':raise Forbidden('local observation owner cannot establish world truth')
        for baseline in request['payload'].get('baseline_refs',[]):self.baseline_material(entry,request,baseline)
    def source_token(self,entry,request):return self.r.verify_source(entry,request,request['payload']['source'])
    def verify_response_retention(self,entry,request,response):self.r.qualify_request(entry,request)
    def _comparison_entry(self,entry,request):
        self.r.check(entry,request,'M14');self.r.stage_context(entry,request)
    def baseline_material(self,entry,request,token):
        self.r.check(entry,request,'M14')
        from digital_life.application.learning.comparison import AuthenticatedComparisonOwner
        return AuthenticatedComparisonOwner(self.r.s,self._comparison_entry).baseline_material(entry,request,token)
    def comparison_relation(self,entry,request,observation,baseline):
        self.r.check(entry,request,'M14')
        from digital_life.application.learning.comparison import AuthenticatedComparisonOwner
        return AuthenticatedComparisonOwner(self.r.s,self._comparison_entry).relation(entry,request,observation,baseline)
    def inference_binding(self,entry,request,packet):
        self.r.check(entry,request,'M14');provider,route,reasoner=self.r.k._route()
        return dict(route,process_run_id=self.r.k.identity.process_id)
    def read_operation_context(self,entry,request,work):
        context=self.r.stage_context(entry,request);return {'contract':'TL-ASSESS-READ-OPERATION-1','request_fingerprint':command_fingerprint(request),'work_ref':request['work_ref']['value'],'account_ref':request['budget']['account_ref'],'run':deepcopy(context['run']),'reservation_id':context['reservation']['id']}
    def verify_read_operation_context(self,entry,request,work,context):
        actual=self.r.stage_context(entry,request)
        if context['run']!=actual['run'] or context['reservation_id']!=actual['reservation']['id'] or actual.get('observation_adopted'):raise Forbidden('assessment read context is wrong or was already consumed')
        actual['observation_adopted']=True


class _LearningThought(ObservationThoughtPort):
    def __init__(self,r,provider):self.r=r;self.provider=provider
    def __getattr__(self,name):return getattr(self.provider,name)
    def configured_binding(self):return self.provider.configured_binding()
    def preflight(self,packet):return self.provider.preflight(packet)
    def generate_fresh(self,packet):
        context=self.r.active
        if context is None or packet['work_ref']!=context['request']['work_ref']['value']:raise Forbidden('fresh learning call lacks this actual assessment owner')
        # A pre-transport binding/deadline failure belongs to this opportunity,
        # never to the previous provider call's ephemeral measurement cache.
        self.provider.last_usage=None;self.provider.last_measurements=None;self.provider.last_observed_route=None;self.provider.last_transport_entered=False
        # IM07 measures this whole port call as the model opportunity, including
        # its parent-side binding/source checks. Rows/bytes still debit the
        # physical read slice; elapsed has only this one owner.
        started=time.monotonic()
        with context['meter'].excluding_child():
            request=context['request'];entry=context['entry'];work=self.r.s.row('tl_work',packet['work_ref']['id'])
            request_row=self.r.s.row('thought_requests',packet['request_id'])
            if request_row['request_hash']!=c.fingerprint(packet) or request_row['activity_id']!=work['learning_activity_id']:raise Conflict('learning provider packet does not equal the actual immutable thought request')
            def guard():self.r.qualify_request(entry,request)
            attempt=self.r.s.db.execute('SELECT id FROM thought_attempts WHERE instance_id=? AND request_id=? ORDER BY attempt_no DESC LIMIT 1',(self.r.s.instance_id,packet['request_id'])).fetchone()
            ledger=self.r.budget._load(work['id'])[3]['ledger']
            own=[v for v in ledger['reservations'].values() if attempt and v['operation']['id']==attempt[0] and v['kind']=='thought_attempt' and v['state']=='reserved' and v['entry'] is not None]
            if len(own)!=1:raise Forbidden('fresh call lacks its actual entered model slice')
            configured=self.r.k._route()[2]
            remaining=min(context['model_timeout_ms'],own[0]['reserved']['elapsed_ms'],int(configured.timeout*1000))-math.ceil((time.monotonic()-started)*1000)
            if remaining<=0:raise Forbidden('actual model opportunity elapsed before transport')
            return self.provider.generate_fresh(packet,execution_timeout_ms=remaining,execution_max_bytes=own[0]['reserved']['bytes'],before_transport=guard)


class _LearningBudget(BudgetAuthority):
    def __init__(self,r):self.r=r
    def verify_representation_read(self,entry,work,operation,binding,stage):
        from digital_life.application.learning.representation_upgrade import UpgradeSession
        session=self.r.representation_session
        if type(session) is not UpgradeSession or session.r is not self.r:raise Forbidden('actual closed representation session required')
        return session.verify_read(entry,work,operation,binding,stage)
    def verify_recovery_read(self,entry,work,operation,binding,stage):
        self.r.o.check(entry)
        actual=getattr(self.r,'recovery_binding',None)
        if actual is None or actual['entry']!=entry or actual['binding']!=binding or binding['work_id']!=work['id'] or binding['operation']!=operation or binding['account_id']!=work['budget_account_id']:raise Forbidden('no actual coordinator recovery read operation')
        if self.r.s.row('tl_work',work['id'])['row_revision'] not in (binding['work_revision'],binding['work_revision']+1):raise Conflict('recovery work revision changed')
    def verify_budget(self,entry,work,original,requested,operation,stage):self.r.o.budget.verify_budget(entry,work,original,requested,operation,stage)
    def verify_entry(self,entry,work,reservation,witness):
        if witness.get('contract')=='TL-RECOVERY-READ-ENTRY-1':
            actual=self.r.recovery_binding
            if actual is None or witness!={'contract':'TL-RECOVERY-READ-ENTRY-1','operation':reservation['operation']} or reservation['kind']!='retrieval':raise Forbidden('not an actual recovery read entry')
            return self.verify_recovery_read(entry,work,reservation['operation'],actual['binding'],'entry')
        self.r.o.budget.verify_entry(entry,work,reservation,witness)
    def verify_settlement(self,entry,work,reservation,actual):
        self.r.o.check(entry,allow_stopped=True)
        if reservation['id'] in self.r.o.settlements:return self.r.o.budget.verify_settlement(entry,work,reservation,actual)
        active=self.r.active
        if active is None or active['entry']!=entry or active['request']['work_ref']['value']['id']!=work['id'] or reservation['kind']!='thought_attempt':raise Forbidden('no actual fresh learning measurement owner')
        provider=self.r.thought.provider;measured=provider.last_usage
        if actual is None:
            if measured is not None:raise Conflict('known provider use cannot be relabelled unknown')
            return
        if measured is None:raise Forbidden('unmeasured provider usage cannot be settled as known')
        for key in DIMENSIONS:
            if key=='elapsed_ms':
                if actual[key]<measured[key]:raise Conflict('learning callback elapsed cannot be below measured provider time')
            elif actual[key]<measured[key] or (key not in ('bytes',) and actual[key]!=measured[key]):raise Conflict('learning actual usage differs from the trusted provider measurement')


class _Acceptance(AcceptanceAuthority):
    def __init__(self,r):self.r=r
    def verify(self,entry,operation,request,instance_id,stage):self.r.check(entry,request,'M03');return StorageGrant('M03',frozenset(('tl_decision','tl_content','tl_content_revision','tl_handoff','tl_group','tl_dependency')))
    def project_response(self,entry,operation,request,response,instance_id,stage):self.r.check(entry,request,'M03');return response
    def verify_proposal_access(self,entry,request,row,stage):
        self.r.check(entry,request,'M03')
        if row['work_id']!=request['work_ref']['value']['id']:raise Forbidden('proposal is not owned by this work')
    def source_token(self,entry,request,evidence):return self.r.verify_source(entry,request,evidence)
    def _preserved_entry(self,entry,request):
        self.r.check(entry,request,'M03');self.r.stage_context(entry,request)
    def preserved_token(self,entry,request,preserved):
        self.r.check(entry,request,'M03')
        from digital_life.application.learning.comparison import AuthenticatedComparisonOwner
        return AuthenticatedComparisonOwner(self.r.s,self._preserved_entry).preserved_token(entry,request,preserved)
    def verify_target_metadata(self,entry,request,token,scope,stage):
        self.r.check(entry,request,'M03');self.r.o.source_access(entry,request['principal'],token['object'],scope)
    def read_byte_limit(self,entry,request,snapshot):return self.r.read_limit(entry,request)
    def verify_read_accounting(self,entry,request,work,snapshot,context,stage):self.r.verify_stage_read(entry,request,context)
    def verify_policy(self,entry,request,policy,stage):
        self.r.check(entry,request,'M03');active=self.r.s.rows('policy_epochs')[0]
        if policy['row']['id']!=active['policy_version_id'] or policy['row']['authority']!=self.r.s.config()['controller']:raise Forbidden('acceptance policy lacks current controller ownership')
    def verify_review(self,entry,request,review,stage):
        self.r.check(entry,request,'M03');signal=review['signal'];body=review['body']
        event=self.r.s.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='tl.controller.review' AND source_event_id=? AND event_type='controller.content_review_authored'",(self.r.s.instance_id,signal['id'])).fetchone()
        if event is None:raise Forbidden('review was not authored by the authenticated control channel')
        actual=self.r.acceptance.storage.read_artifact(event['payload_artifact_id'])
        if actual.get('review')!=ref(self.r.s,signal['id']) or actual.get('proposal')!=request['payload']['proposal'] or actual.get('review_digest')!=c.fingerprint(body) or actual.get('controller')!=ref(self.r.s,self.r.s.config()['controller']):raise Conflict('authenticated review event does not bind this exact review')
    def verify_group(self,entry,request,contexts,stage):
        for context in contexts:self.r.check(entry,context['request'],'M03')
    def verify_projection(self,entry,principal,context):self.r.o.check(entry,principal)
    def evaluate_gate(self,entry,request,context,gate,stage):
        self.r.check(entry,request,'M03');product=context['product'];body=product['body'];state='pass';basis=[ref(self.r.s,context['row']['id'])]
        method={'name':'local-scoped-report-'+gate.lower(),'version':'1','request_ref':slot(),'model_config_ref':slot()}
        claims=body['claims'];scope=context['scope'];target=body['target']
        if gate=='G01':self.r.verify_stage_read(entry,request,{'request_fingerprint':command_fingerprint(request),'account_ref':request['budget']['account_ref']})
        elif gate=='G02':
            c.validate('Product',product)
            if not claims or any(claim['value']['status']!='known' for claim in claims):state='incomplete'
        elif gate=='G03':
            for claim in claims:
                for source in claim['evidence']:self.r.verify_source(entry,request,source)
        elif gate=='G04':
            if target['content_kind']!='source_report' or any(claim['form']!='source_report' or claim['scope']['claim_target']!='source_report' or not claim['limitations'] for claim in claims):state='incomplete'
            # Literal equality is separately recomputed by C1. This owner only
            # authorizes the finite report interpretation, never world truth.
        elif gate=='G05':
            required=('subject','domain','unit','granularity','conditions')
            if target['mode']!='new' or any(scope[key]['status']!='known' or scope[key]['value'] is None for key in required):state='incomplete'
        elif gate=='G06':
            # Our supported addition is one unique receipt-scoped report, not
            # a world-state merge or a claim that no other reports exist.
            sources={source['source']['id'] for claim in claims for source in claim['evidence']}
            if len(sources)!=1 or body['preserved_content'] or body['unresolved_items'] or scope['property']!='reported:'+next(iter(sources), ''):state='incomplete'
        elif gate=='G07':
            policy=self.r.s.row('policy_versions',request['payload']['policy']['id']);profile=c.loads(policy['scope']).get('tool_learning_acceptance')
            if not isinstance(profile,dict) or request['payload']['review']['status']!='known':state='incomplete'
            else:self.verify_review(entry,request,{'signal':self.r.s.row('perception_signals',request['payload']['review']['value']['id']),'body':self.r.acceptance.storage.read_artifact(self.r.s.row('perception_signals',request['payload']['review']['value']['id'])['artifact_id'])},stage)
        elif gate=='G08':
            if any(claim['scope']!=scope for claim in claims) or target['content_kind']!=scope['claim_target']:state='fail'
        checker_entry,checker=self.r.o.entry(OWNERS[gate][0],'accept',request['principal']['recipient']['id'])
        self.r.o.check(checker_entry,checker)
        return {'state':state,'checker':checker,'method':method,'at':utc(),'targets':[],'reason':'none' if state=='pass' else 'unsupported','basis_refs':basis}


class _Representation(RepresentationAuthority):
    def __init__(self,r):self.r=r
    def verify(self,entry,operation,request,instance_id,stage):self.r.check(entry,request,'M04');return StorageGrant('M04',frozenset(('tl_handoff','tl_representation','tl_representation_head','tl_group','tl_dependency')))
    def project_response(self,entry,operation,request,response,instance_id,stage):self.r.check(entry,request,'M04');return response
    def verify_handoff(self,entry,operation,request,context,stage):
        self.r.check(entry,request,'M04')
        if request['payload']['worker']['id']!=request['principal']['actor']['id'] or context['work']['id']!=request['work_ref']['value']['id']:raise Forbidden('representation worker is not this actual local process actor')
    def read_byte_limit(self,entry,request,snapshot):return self.r.read_limit(entry,request)
    def verify_read_accounting(self,entry,request,context,read_context,stage):self.r.verify_stage_read(entry,request,read_context)
    def verify_retention(self,entry,request,context,stage):self.r.check(entry,request,'M04')
    def verify_group(self,entry,request,contexts,stage):
        for member in contexts:self.r.check(member['entry'],member['request'],'M04')
    def resolve_stage_entry(self,entry,request,stage_material):
        bound=stage_material['channel_binding']['principal']
        for key in self.r.o.entries:
            if self.r.o.principal(key)==bound:return key
        raise Forbidden('persisted member has no current authenticated local channel')


class _Recovery(RecoveryAuthority):
    def __init__(self,r):self.r=r
    def verify(self,entry,operation,request,instance_id,stage):
        self.r.check(entry,request,'M14')
        if operation!='resume_work':raise Forbidden('not a recovery operation')
        return StorageGrant('M14',frozenset(('tl_work',)))
    def project_response(self,entry,operation,request,response,instance_id,stage):
        self.r.qualify_request(entry,request)
        original=self.r.recovery.storage.read_artifact(request['payload']['reconciliation']['id'])
        work=self.r.s.row('tl_work',request['payload']['work']['id']);work.update(phase=original['phase'],review_round=original['review_round'])
        self.verify_conditions(entry,request,work,request['payload']['conditions'],'last_projection')
        return response
    def verify_read_accounting(self,entry,request,work,stage):self.r.stage_context(entry,request)
    def verify_reconciliation(self,entry,request,work,record,stage):self.r.qualify_request(entry,request)
    def verify_conditions(self,entry,request,work,conditions,stage):
        self.r.check(entry,request,'M14')
        if work['phase']=='assess':
            if len(conditions)!=1 or conditions[0]['kind']!='runtime_events':raise Forbidden('assessment continuation needs its actual durable material stage')
            event=self.r.s.row('runtime_events',conditions[0]['id'])
            if conditions[0]!=ref(self.r.s,event['id']) or event['source']!='tl.observation.material' or event['source_event_id']!=work['id'] or event['activity_id']!=work['learning_activity_id']:raise Forbidden('material stage does not belong to this original assessment')
            staged=self.r.observation.storage.read_artifact(event['payload_artifact_id'])
            if event['payload_hash']!=c.fingerprint(staged) or staged!=self.r.observation._stage(work['id'],'material'):raise Conflict('persisted assessment material identity differs')
            if staged.get('contract')!='TL-OBSERVATION-MATERIAL-1' or not any(p['product_type']=='UpdateProposal' for p in staged.get('products',[])):raise Forbidden('assessment material lacks a resolved publishable proposal')
            for product in staged['products']:c.validate('Product',product)
            for token in [staged['source_token']]+staged['baseline_tokens']+([staged['interpretation_token']] if staged.get('interpretation_token') else []):
                self.r.o.eligibility._check(entry,request['principal'],token,staged['scope'],request['principal']['purpose'],request['principal']['recipient'],'recovery_persisted_material')
            return
        if work['phase']=='represent':
            obligations=self.r.s.db.execute("SELECT * FROM tl_handoff WHERE instance_id=? AND work_id=? AND state NOT IN ('published','obsolete','permanent_failure') ORDER BY id LIMIT 257",(self.r.s.instance_id,work['id'])).fetchall()
            if not obligations or len(obligations)>256 or sorted(conditions,key=lambda x:x['id'])!=[ref(self.r.s,h['id']) for h in obligations]:raise Forbidden('recovery must bind every fixed unfinished handoff')
            for handoff in obligations:
                if handoff['state'] not in ('pending','retryable','leased') or handoff['state']=='leased' and handoff['lease_expires_at']>self.r.recovery.clock():raise Forbidden('original representation condition has not expired/resolved')
                revision=self.r.s.row('tl_content_revision',handoff['content_revision_id']);content=self.r.s.row('tl_content',revision['content_id'])
                if content['head_revision_id']!=revision['id'] or revision['status']!='accepted':raise Conflict('handoff no longer names accepted current content')
                token=self.r.o.token(ref(self.r.s,content['id']),self.r.plan(request)['scope'])
                self.r.o.eligibility._check(entry,request['principal'],token,self.r.plan(request)['scope'],request['principal']['purpose'],request['principal']['recipient'],'recovery_fixed_content')
            return
        if work['phase']!='decide' or len(conditions)!=1:raise Forbidden('local recovery has no owner for this condition')
        signal=self.r.s.row('perception_signals',conditions[0]['id'])
        if conditions[0]!=ref(self.r.s,signal['id']) or signal['source_actor_id']!=self.r.s.config()['controller']:raise Forbidden('not a current controller review condition')
        body=self.r.recovery.storage.read_artifact(signal['artifact_id'])
        if body.get('contract')!='TL-CONTROLLER-CONTENT-REVIEW-1' or body['review_round']!=work['review_round']+1 or body['expires_at']<=utc():raise Forbidden('review is not the next live round')
        product=self.r.s.row('tl_product',body['proposal']['id'])
        if product['work_id']!=work['id']:raise Forbidden('review belongs to another work')
        checker,principal=self.r.o.entry('M03','accept',request['principal']['recipient']['id'])
        bound=deepcopy(request);bound['principal']=principal;bound['payload']={'proposal':body['proposal'],'review_round':body['review_round'],'policy':body['policy'],'review':slot(conditions[0]),'atomic_group':body['atomic_group']}
        _Acceptance(self.r).verify_review(checker,bound,{'signal':signal,'body':body},stage)
        if body['policy']['id']!=self.r.s.rows('policy_epochs')[0]['policy_version_id']:raise Conflict('resolved review binds stale policy')
        native=body['native_expected']
        if native['status']=='known':
            content=self.r.s.row('tl_content',native['value']['object']['id']);revision=self.r.s.row('tl_content_revision',content['head_revision_id'])
            if native['value']['revision']!=revision['revision_no']:raise Conflict('resolved review binds stale native head')
        if body['expires_at']<=utc():raise Forbidden('resolved review expired at final condition boundary')


class StrictLearningCoordinator:
    def __init__(self,kernel,thought_provider=None):
        self.k=kernel;self.s=kernel.s;self.o=kernel.owners;self.active=None
        self.work=ToolLearningWork(self.s,_Work(self));self.budget=ToolLearningBudget(self.s,_LearningBudget(self))
        provider,route,reasoner=kernel._route()
        self.thought=_LearningThought(self,thought_provider or FreshLearningProvider(reasoner,route))
        self.observation=ToolLearningObservation(self.s,_Observation(self),self.budget.authority,self.o.source,self.thought)
        self.acceptance=ToolLearningAcceptance(self.s,_Acceptance(self),self.o.source)
        self.representation=ToolLearningRepresentation(self.s,_Representation(self),self.o.source)
        self.recovery=ToolLearningRecovery(self.s,_Recovery(self));self.recovery_binding=None;self.representation_session=None
        for service in (self.observation,self.acceptance,self.representation):service.eligibility.max_nodes=4096;service.eligibility.max_rows=65536
    def require_learning(self):
        from digital_life.application.learning.runtime import strict_feature_enabled
        if not strict_feature_enabled(self.s):raise Forbidden('new tool-observation learning is disabled by current policy')
    def check(self,entry,request,module=None):
        self.require_learning()
        self.o.check(entry,request['principal'])
        if request['instance_id']!=self.s.instance_id or module is not None and request['principal']['module']!=module:raise Forbidden('actual module/instance channel differs')
        if request['control']['runtime_epoch']!=self.k.identity.epoch or request['control']['policy']['object']['id']!=self.s.rows('policy_epochs')[0]['policy_version_id'] or request['control']['policy']['epoch']!=self.s.rows('policy_epochs')[0]['epoch']:raise Conflict('learning control ownership/epoch changed')
    def verify_source(self,entry,request,source):
        self.o.check(entry,request['principal']);origin=source['source'];kind=origin['kind'];row=self.s.row(kind,origin['id'])
        if kind=='perception_signals':artifact=row['artifact_id'];activity=self.s.db.execute('SELECT id FROM activities WHERE instance_id=? AND trigger_event_id=?',(self.s.instance_id,row['id'])).fetchone()
        elif kind=='action_results':
            artifact=row['receipt_artifact_id'];attempt=self.s.row('action_attempts',row['attempt_id']);intent=self.s.row('action_intents',attempt['intent_id']);candidate=self.s.row('decision_candidates',intent['candidate_id']);activity={'id':self.s.row('decision_records',candidate['decision_id'])['activity_id']}
            if source['original_result']!=slot(origin) or source['receipt']!=slot(ref(self.s,artifact)) or source['source_kind']!='tool_result':raise Forbidden('tool report does not bind its actual original result/receipt')
        else:raise Forbidden('local learning source owner supports only original user signals and actual tool results')
        if activity is None:raise Forbidden('learning source has no actual original activity')
        if request['work_ref']['status']=='known':
            work=self.s.row('tl_work',request['work_ref']['value']['id'])
            if work['source_activity_id']!=activity['id']:raise Forbidden('learning source belongs to another original activity')
        elif request['payload']['source_activity']['id']!=activity['id']:raise Forbidden('source activity mapping differs')
        actual=self.s.row('artifacts',artifact)
        if source['artifact']!=ref(self.s,artifact) or source['digest']['hex']!=actual['hash'] or source['media_type']!=actual['media_type'] or source['source_revision']['status']!='not_applicable' or source['view']['status']!='not_applicable' or source['view_digest']['status']!='not_applicable':raise Conflict('learning source revision/actual artifact/view mapping differs')
        scope=self.plan(request)['scope'];token=self.o.token(origin,scope)
        self.o.eligibility._check(entry,request['principal'],token,scope,request['principal']['purpose'],request['principal']['recipient'],'learning_actual_source') if self.s.db.in_transaction else self.o.eligibility.check(entry,request['principal'],token,scope,request['principal']['purpose'],request['principal']['recipient'],'learning_actual_source')
        return token
    def plan(self,request):
        method=request['payload'].get('processing_method',request['payload'].get('method'))
        if method is None or method['name']!='tl-observation' or method['request_ref']['status']!='known':
            work=self.s.row('tl_work',request['work_ref']['value']['id']);method=self.observation.storage.read_artifact(work['method_artifact_id'])
        return validate_plan(self.observation.storage.read_artifact(method['request_ref']['value']['id']))
    def qualify_request(self,entry,request):
        self.check(entry,request);work=self.s.row('tl_work',request['work_ref']['value']['id']);condition=self.observation.storage.read_artifact(work['conditions_artifact_id'])
        self.verify_source(entry,request,condition['source'])
        for token in request['payload'].get('baseline_refs',[]):self.o.eligibility.check(entry,request['principal'],token,self.plan(request)['scope'],request['principal']['purpose'],request['principal']['recipient'],'learning_baseline_use')
    def stage_context(self,entry,request):
        current=self.active
        if current is None or current['request'] is None or current['entry']!=entry or current['fingerprint']!=command_fingerprint(request) or current['request']['work_ref']!=request['work_ref'] or current['account_ref']!=request['budget']['account_ref']:raise Forbidden('no unique entered original-account read stage for this request')
        actual=self.budget._load(request['work_ref']['value']['id'])[3]['ledger']['reservations'].get(current['reservation']['id'])
        if actual is None or actual['state']!='reserved' or actual['entry'] is None or actual['operation']!=current['run']:raise Forbidden('read stage was consumed, released, or belongs to another run')
        return current
    def read_limit(self,entry,request):
        context=self.stage_context(entry,request);meter=context['meter'];meter.time()
        return min(1048576,max(0,meter.limits['bytes']-meter.actual['bytes']))
    def verify_stage_read(self,entry,request,context):
        actual=self.stage_context(entry,request);self.check(entry,request)
        if context['request_fingerprint']!=actual['fingerprint'] or context['account_ref']!=actual['account_ref']:raise Conflict('read receipt differs from exact operation/account')
    def _envelope(self,entry,activity,payload,work=None,budget=None):
        principal=self.o.principal(entry);scope=self.plan_scope(payload) if work is None else None
        control=self.k._control(activity,scope,[])
        return {'contract':'TL-LOOP-0.1','schema_revision':1,'command_id':identifier(),'instance_id':self.s.instance_id,'principal':principal,'work_ref':slot(ref(self.s,work)) if work else slot(),'idempotency_key':identifier(),'expected':slot(),'control':control,'budget':deepcopy(budget or self.k._caps(activity)),'payload':deepcopy(payload)}
    def plan_scope(self,payload):return validate_plan(self.observation.storage.read_artifact(payload['processing_method']['request_ref']['value']['id']))['scope']
    @contextmanager
    def read_stage(self,entry,request=None,fraction=.7,work_id=None):
        self.require_learning()
        if self.active is not None:raise Conflict('learning read stages cannot nest or reset their meter')
        work=self.s.row('tl_work',request['work_ref']['value']['id'] if request is not None else work_id);snapshot=self.budget.check_work(work['id'],request['budget'] if request is not None else None);amounts={key:0 for key in DIMENSIONS}
        budget=deepcopy(request['budget'] if request is not None else snapshot['budget'])
        for key in ('scan','items','bytes','elapsed_ms'):amounts[key]=max(1,int(snapshot['remaining'][key]*fraction))
        with dispatch_gate(self.s.root):
            self.o.check(entry)
            with self.s.tx():
                context=self.s.insert('context_snapshots',activity_id=work['learning_activity_id'],context_schema='strict-learning-stage-1',attributes_json={})
                run=self.s.insert('memory_retrieval_runs',activity_id=work['learning_activity_id'],context_id=context,query='fixed native learning stage',retriever_version='strict-learning-stage-1')
            session=self.representation_session
            rendering=session is not None and self.o.principal(entry)['module'] in ('M03','M04')
            binding={'work_id':work['id'],'authorization_id':session.nonce} if rendering else None
            with self.budget.representation_read_context(entry,work['id'],ref(self.s,run),binding) if rendering else nullcontext():
                reservation=self.budget.reserve(entry,work['id'],ref(self.s,run),'retrieval',amounts,request_budget=budget,reservation_key='learning-stage:'+run)
                self.budget.record_entry(entry,work['id'],reservation['id'],{'contract':'TL-RUNTIME-STAGE-READ-ENTRY-1','operation':ref(self.s,run),'occurrence_id':identifier()})
                meter=PhysicalReadMeter(reservation['reserved'],work['deadline'])
                self.active={'entry':entry,'request':None,'fingerprint':None,'work_id':work['id'],'account_ref':deepcopy(budget['account_ref']),'run':ref(self.s,run),'reservation':reservation,'meter':meter,'model_timeout_ms':max(1,self.budget.check_work(work['id'])['remaining']['elapsed_ms'])}
                try:
                    with meter.installed(self.s):
                        if request is not None:self.bind_stage_request(entry,request)
                        yield self.active
                finally:
                    self.active=None;actual=meter.usage();self.o.settlements[reservation['id']]={'actual':deepcopy(actual)}
                    self.budget.settle(entry,work['id'],reservation['id'],actual)
    def bind_stage_request(self,entry,request):
        current=self.active
        if current is None or current['entry']!=entry or current['request'] is not None:raise Forbidden('read occurrence must be bound exactly once')
        if request['work_ref']!=slot(ref(self.s,current['work_id'])) or request['budget']['account_ref']!=current['account_ref']:raise Conflict('read occurrence cannot bind another work or account')
        self.check(entry,request)
        current['request']=deepcopy(request);current['fingerprint']=command_fingerprint(request)
        self.qualify_request(entry,request)
    def admit(self,activity,source_id,locator,*,interpret=False):
        """Create only a new native work from an already existing real source.

        This explicit process method does not execute/re-execute that source.
        Child caps are allocated once from this original activity's remaining
        eight-dimensional account, after reserving admission bookkeeping reads.
        """
        from digital_life.application.learning.runtime import strict_feature_enabled
        if not strict_feature_enabled(self.s):raise Forbidden('new tool-observation learning is disabled by current policy')
        t.boolean(interpret);t.validate_locator(locator)
        entry,principal=self.o.entry('M14','learn',self.s.config()['controller'])
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE instance_id=? AND activity_id=? ORDER BY rowid LIMIT 1',(self.s.instance_id,activity)).fetchone()
        if context is None:raise Forbidden('original source activity context is missing')
        with self.k._read_operation(entry,activity,context[0],'native-learning-admission',self.k._read_slice(activity,.2)),dispatch_gate(self.s.root):
            origin=ref(self.s,source_id);row=self.s.row(origin['kind'],source_id)
            if origin['kind']=='perception_signals':artifact=row['artifact_id'];kind='user_statement' if row['source_actor_id']==self.s.config()['controller'] else 'system_event';result=slot();receipt=slot();observed=row['received_at']
            elif origin['kind']=='action_results':artifact=row['receipt_artifact_id'];kind='tool_result';result=slot(origin);receipt=slot(ref(self.s,artifact));observed=row['recorded_at']
            else:raise Forbidden('unsupported original observation owner')
            actual=self.s.row('artifacts',artifact);coverage={'state':'complete','domain':slot('one fixed original artifact locator'),'scanned':1,'limit':1,'truncated':False,'missing':[]}
            scope=source_scope(self.s,'reported:'+source_id);scope.update(domain=slot('digital_life.fixed_source_report'),unit=slot('reported_value'),granularity=slot(dumps(locator)),conditions=slot({'original_source':source_id,'locator':deepcopy(locator)}),coverage=deepcopy(coverage))
            scope['temporal']={'kind':'observation','start':slot(observed),'end':slot(observed),'bounds':'point'}
            token=self.o.token(origin,scope)
            self.o.eligibility.check(entry,principal,token,scope,'learn',principal['recipient'],'before_learning_plan_retention')
            source={'source':origin,'source_kind':kind,'original_result':result,'receipt':receipt,'artifact':ref(self.s,artifact),'source_revision':slot(),'digest':{'algorithm':'sha256','hex':actual['hash']},'media_type':actual['media_type'],'encoding':slot('UTF-8'),'view':slot(),'view_digest':slot(),'locator':deepcopy(locator),'origin_method':{'name':'actual-existing-source','version':'1','request_ref':slot(),'model_config_ref':slot()},'observed_at':slot(observed),'reported_at':slot(),'coverage':deepcopy(coverage),'derivation_refs':[],'access_dependencies':[]}
            with self.s.tx():
                metric=self.s.db.execute("SELECT id FROM metric_definitions WHERE instance_id=? AND name='tool_learning_gain' ORDER BY rowid LIMIT 1",(self.s.instance_id,)).fetchone()
                metric_id=metric[0] if metric else self.s.insert('metric_definitions',name='tool_learning_gain',formula_version='requires-independent-measurement-1',unit='score',denominator_rule='explicit-future-baseline',missing_rule='unknown',stratification={})
                plan={'contract':'TL-OBSERVATION-PLAN-1','subject':deepcopy(scope['subject']),'scope':scope,'predicate':'reported_original_value','outputs':['ObservationExtract','ComparisonAssessment','UpdateProposal','EffectAssessment'],'effect_metric':slot(ref(self.s,metric_id)),'interpret':interpret}
                plan_id=self.s.artifact(plan)
                token=self.o.token(origin,scope)
                for relation in ('read','delete'):_dependency(self.s,ref(self.s,plan_id),token,scope,relation,'/planned_original_source','learn')
            method={'name':'tl-observation','version':'1','request_ref':slot(ref(self.s,plan_id)),'model_config_ref':slot()}
            remaining=self.k.budget.check_activity(activity)['remaining'];caps=self.k._caps(activity)
            child=dict(caps)
            for dimension,name in CAPS.items():child[name]=max(0,int(remaining[dimension]*.5))
            child['max_tool_calls']=0
            if child['max_attempts']<1 or min(child['max_scan'],child['max_items'],child['max_bytes'])<1:raise Forbidden('original activity has no finite native-learning allocation remaining')
            payload={'source':source,'purpose':'learn','source_activity':ref(self.s,activity),'processing_method':method,'previous_work':slot()}
            request=self._envelope(entry,activity,payload,budget=child);request['control']['source_epochs']=[token]
            response=self.work.admit(entry,request)
            return response['result_refs'][0]
    def reprocess(self,previous_work_id,bearer,*,kind,reason,ordinal,method=None,budget=None,new_baseline=None):
        """Explicit authenticated same-source practice; never automatically runs.

        A new slice is charged to the same pre-existing parent allocation pool.
        Prior terminal records, observations and consumed/unknown costs survive.
        """
        from digital_life.application.learning.runtime import authenticate_controller
        from digital_life.application.learning.reprocessing import ControllerReprocessingAuthor
        authenticate_controller(self.s,bearer);self.require_learning()
        previous=self.s.row('tl_work',previous_work_id);activity=previous['source_activity_id']
        entry,principal=self.o.entry('M14','learn',self.s.config()['controller'])
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE instance_id=? AND activity_id=? ORDER BY rowid LIMIT 1',(self.s.instance_id,activity)).fetchone()
        if context is None:raise Forbidden('original source context missing')
        with self.k._read_operation(entry,activity,context[0],'explicit-learning-reprocessing',self.k._read_slice(activity,.2)),dispatch_gate(self.s.root):
            conditions=self.observation.storage.read_artifact(previous['conditions_artifact_id'])
            old_method=self.observation.storage.read_artifact(previous['method_artifact_id'])
            snapshot=self.budget.check_work(previous_work_id)
            if snapshot['remaining']['attempts']<1:raise Forbidden('original attempt budget exhausted; reprocessing cannot renew it')
            child=deepcopy(conditions['budget'])
            child['account_ref']=deepcopy(conditions['source_budget']['account_ref'])
            if budget is None:
                for dimension,name in CAPS.items():child[name]=min(child[name],max(0,int(snapshot['remaining'][dimension]*.25)))
                if child['max_attempts']<1 and snapshot['remaining']['attempts']>0:child['max_attempts']=1
            else:child=deepcopy(budget)
            payload={'source':deepcopy(conditions['source']),'purpose':'learn','source_activity':deepcopy(conditions['source_activity']),
                'processing_method':deepcopy(method or old_method),'previous_work':slot(ref(self.s,previous_work_id))}
            request=self._envelope(entry,activity,payload,budget=child)
            self.verify_source(entry,request,payload['source'])
            ControllerReprocessingAuthor(self.s,bearer).authorize(request,kind=kind,reason=reason,ordinal=ordinal,new_baseline=new_baseline)
            response=self.work.admit(entry,request)
            if response['disposition'] not in ('applied','reused'):raise Forbidden('current reprocessing admission was blocked')
            return response['result_refs'][0]

    def assessment_request(self,work_id,entry=None,baseline_refs=None):
        work=self.s.row('tl_work',work_id);conditions=self.observation.storage.read_artifact(work['conditions_artifact_id']);method=self.observation.storage.read_artifact(work['method_artifact_id'])
        if entry is None:entry,principal=self.o.entry('M14','learn',self.s.config()['controller'])
        budget=self.budget.check_work(work_id)['budget']
        coverage={'state':'partial','domain':slot('explicit new source report; no external baseline search'),'scanned':0,'limit':0,'truncated':False,'missing':[{'status':'not_collected','value':None,'reason_code':'no_baseline','reason':'No independent baseline was searched or asserted.','basis_refs':[]}]}
        request=self._envelope(entry,work['learning_activity_id'],{'source':conditions['source'],'baseline_refs':deepcopy(baseline_refs or []),'baseline_coverage':coverage,'method':method},work_id,budget)
        request['expected']=slot({'object':ref(self.s,work_id),'revision':work['row_revision'],'epoch':0})
        request['control']['source_epochs']=[self.o.token(conditions['source']['source'],self.plan(request)['scope'])]
        return entry,request
    def resume_work(self,work_id,conditions):
        """Continue this original work after actual owner condition resolution."""
        self.require_learning()
        if self.active is not None or self.recovery_binding is not None:raise Conflict('recovery cannot nest an execution stage')
        entry,principal=self.o.entry('M14','learn',self.s.config()['controller'])
        with dispatch_gate(self.s.root):
            self.o.check(entry);work=self.s.row('tl_work',work_id)
            original=self.budget.check_work(work_id)
            if any(reason!='work_'+work['state'] for reason in original['block_reasons']):raise Forbidden('original recovery resources unavailable')
            with self.s.tx():
                context=self.s.insert('context_snapshots',activity_id=work['learning_activity_id'],context_schema='strict-recovery-read-1',attributes_json={})
                run=self.s.insert('memory_retrieval_runs',activity_id=work['learning_activity_id'],context_id=context,query='original-work persistent reconciliation',retriever_version='strict-recovery-read-1')
            operation=ref(self.s,run);binding={'work_id':work_id,'work_revision':work['row_revision'],'account_id':work['budget_account_id'],'operation':operation}
            self.recovery_binding={'entry':entry,'binding':binding}
            try:
                with self.budget.recovery_read_context(entry,work_id,operation,binding):
                    amounts={key:0 for key in DIMENSIONS}
                    for key in ('scan','items','bytes','elapsed_ms'):amounts[key]=max(1,int(original['remaining'][key]*.7))
                    reservation=self.budget.reserve(entry,work_id,operation,'retrieval',amounts,reservation_key='recovery:'+run)
                    self.budget.record_entry(entry,work_id,reservation['id'],{'contract':'TL-RECOVERY-READ-ENTRY-1','operation':operation})
                    meter=PhysicalReadMeter(reservation['reserved'],work['deadline'])
                    self.active={'entry':entry,'request':None,'fingerprint':None,'work_id':work_id,'account_ref':original['budget']['account_ref'],'run':operation,'reservation':reservation,'meter':meter}
                    try:
                        with meter.installed(self.s):
                            provisional=self._envelope(entry,work['learning_activity_id'],{},work_id,original['budget'])
                            self.qualify_request(entry,provisional)
                            facts=self.recovery.facts(work_id)
                            record={'contract':'TL-WORK-RECONCILIATION-1','instance_id':self.s.instance_id,'work_id':work_id,'expected_work_revision':work['row_revision'],'phase':work['phase'],'review_round':work['review_round'],'conditions':deepcopy(conditions),'facts':facts}
                            with self.s.tx():artifact=self.s.artifact(record)
                            payload={'work':ref(self.s,work_id),'expected_work_revision':work['row_revision'],'conditions':deepcopy(conditions),'reconciliation':ref(self.s,artifact)}
                            request=self._envelope(entry,work['learning_activity_id'],payload,work_id,original['budget']);request['expected']=slot({'object':ref(self.s,work_id),'revision':work['row_revision'],'epoch':0})
                            self.bind_stage_request(entry,request)
                            return self.recovery.resume(entry,request)
                    finally:
                        actual=meter.usage();self.o.settlements[reservation['id']]={'actual':deepcopy(actual)}
                        self.budget.settle(entry,work_id,reservation['id'],actual);self.active=None
            finally:self.recovery_binding=None

    def assess(self,work_id,*,baseline_refs=None):
        self.require_learning()
        entry,principal=self.o.entry('M14','learn',self.s.config()['controller'])
        with self.read_stage(entry,work_id=work_id,fraction=.45):
            entry,request=self.assessment_request(work_id,entry,baseline_refs=baseline_refs);self.bind_stage_request(entry,request)
            return self.observation.assess(entry,request)
    def decide(self,proposal_id,review=None):
        self.require_learning()
        product=self.s.row('tl_product',proposal_id);work=self.s.row('tl_work',product['work_id'])
        if work['state']=='processing' and work['phase']=='decide':
            coordinator,coordinator_principal=self.o.entry('M14','learn',self.s.config()['controller'])
            with self.read_stage(coordinator,work_id=work['id']):self._transition_in_stage(coordinator,work,'awaiting_decision','decide','resumed-persisted-proposal')
            work=self.s.row('tl_work',work['id'])
        entry,principal=self.o.entry('M03','accept',self.s.config()['controller'])
        payload={'proposal':ref(self.s,proposal_id),'review_round':work['review_round'],'policy':deepcopy(principal['authorization']),'review':slot(deepcopy(review)) if review is not None else slot(),'atomic_group':slot()}
        request=self._envelope(entry,work['learning_activity_id'],payload,work['id'],self.budget.check_work(work['id'])['budget'])
        with self.read_stage(entry,request):response=self.acceptance.decide(entry,request)
        self.project(work['id'])
        return response
    def project(self,work_id):
        self.require_learning()
        entry,principal=self.o.entry('M14','learn',self.s.config()['controller'])
        with self.read_stage(entry,work_id=work_id):
            work=self.s.row('tl_work',work_id)
            projection=self.acceptance.work_projection(entry,principal,ref(self.s,work_id));target=projection['target']
            if target is None or target==work['state']:return projection
            phase=projection.get('phase','represent' if target=='handoff_pending' else 'complete')
            return self._transition_in_stage(entry,work,target,phase,'persisted-content-decision')
    def _transition_in_stage(self,entry,work,target,phase,reason):
        artifact=self.s.artifact({'contract':'TL-WORK-TRANSITION-1','work_id':work['id'],'expected_revision':work['row_revision'],'target':target,'phase':phase,'reason':reason})
        source=self.observation.storage.read_artifact(work['conditions_artifact_id'])['source']
        method={'name':'tl-work-transition','version':'1','request_ref':slot(ref(self.s,artifact)),'model_config_ref':slot()}
        payload={'source':source,'baseline_refs':[],'baseline_coverage':{'state':'partial','domain':slot('fixed persisted endpoint projection'),'scanned':0,'limit':0,'truncated':False,'missing':[]},'method':method}
        request=self._envelope(entry,work['learning_activity_id'],payload,work['id'],self.budget.check_work(work['id'])['budget']);request['expected']=slot({'object':ref(self.s,work['id']),'revision':work['row_revision'],'epoch':0})
        self.bind_stage_request(entry,request)
        return self.work.transition(entry,request,target,phase,reason)
    def upgrade_representation(self,old_handoff_id,bearer,*,language,ordinal):
        """Explicit finite header localization; never reopens learning work."""
        from digital_life.application.learning.representation_upgrade import UpgradeSession
        if self.active is not None or self.representation_session is not None:raise Conflict('representation upgrade cannot nest or reuse another read')
        session=UpgradeSession(self,old_handoff_id,bearer,language,ordinal)
        self.representation_session=session
        try:
            session.prepare()
            handoff=session.create_handoff();row=self.s.row('tl_handoff',handoff)
            if row['state']!='published':return self.publish(handoff)
            entry,principal=self.o.entry('M04','represent',self.s.config()['controller'])
            work=self.s.row('tl_work',row['work_id'])
            payload={'handoff':ref(self.s,handoff),'worker':deepcopy(principal['actor']),'expected_generation':row['lease_generation'],'lease_seconds':30}
            request=self._envelope(entry,work['learning_activity_id'],payload,work['id'],self.budget.check_work(work['id'])['budget'])
            with self.read_stage(entry,request):
                session.verify(entry,request)
                return self.representation._response(request,'publish_representation',row,'reused',[ref(self.s,row['representation_id'])])
        finally:self.representation_session=None

    def publish(self,handoff_id):
        self.require_learning()
        handoff=self.s.row('tl_handoff',handoff_id);work=self.s.row('tl_work',handoff['work_id']);entry,principal=self.o.entry('M04','represent',self.s.config()['controller'])
        payload={'handoff':ref(self.s,handoff_id),'worker':deepcopy(principal['actor']),'expected_generation':handoff['lease_generation'],'lease_seconds':30}
        request=self._envelope(entry,work['learning_activity_id'],payload,work['id'],self.budget.check_work(work['id'])['budget'])
        request['expected']=slot({'object':ref(self.s,handoff_id),'revision':handoff['row_revision'],'epoch':handoff['lease_generation']})
        with self.read_stage(entry,request):claim=self.representation.claim(entry,request)
        build_request=deepcopy(request);build_request['payload']={'handoff':ref(self.s,handoff_id),'worker':deepcopy(principal['actor']),'lease_generation':claim['current']['value']['epoch']}
        with self.read_stage(entry,build_request):representation=self.representation.build(entry,request,claim)
        request.update(command_id=identifier(),idempotency_key=identifier(),expected=deepcopy(claim['current']),payload={'handoff':ref(self.s,handoff_id),'worker':deepcopy(principal['actor']),'lease_generation':claim['current']['value']['epoch'],'representation':representation})
        with self.read_stage(entry,request):response=self.representation.publish(entry,request)
        # C2 receipt is the actual endpoint proof. Reuse the coordinator's
        # forward transition contract instead of M04 writing M14-owned work.
        current=self.s.row('tl_work',work['id'])
        if current['state']=='handoff_pending':
            projection_entry,projection_principal=self.o.entry('M14','learn',self.s.config()['controller'])
            with self.read_stage(projection_entry,work_id=work['id']):
                current=self.s.row('tl_work',work['id'])
                self._transition_in_stage(projection_entry,current,'completed','complete','all-fixed-representations-published')
        return response
