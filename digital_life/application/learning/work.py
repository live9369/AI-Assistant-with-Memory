"""C0 and forward-only work coordination. No model, queue or runtime wiring."""
from dataclasses import dataclass
import json
from datetime import datetime
from digital_life.domain.contracts import ContractError, Conflict, Forbidden, identifier, utc, dumps
from digital_life.domain import tool_learning_contract as contract
from digital_life.domain import tool_learning_types as types
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore, StorageAuthority
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.application.learning.budget import make_work_budget,ToolLearningBudget

CAPS=('max_attempts','max_input_tokens','max_output_tokens','max_tool_calls','max_scan','max_items','max_bytes')
TERMINAL={'completed','no_change','rejected'}
FORWARD={
 'admitted':{'processing','waiting','blocked','stopped'},
 'processing':{'awaiting_decision','completed','no_change','waiting','blocked','failed','stopped'},
 'awaiting_decision':{'handoff_pending','completed','no_change','waiting','blocked','rejected','stopped'},
 'handoff_pending':{'completed','waiting','blocked','failed','stopped'},
}


@dataclass(frozen=True)
class AdmissionAllocation:
    """Trusted TL allocation pool, not reconstructed legacy per-dimension usage.

    Its immutable caps bound all TL children together. Existing physical parent
    tokens/tools/attempts are additionally charged; historical legacy input vs
    output or scan/byte usage cannot be inferred from a total-token counter.
    """
    parent_budget: dict


class WorkAuthority(StorageAuthority):
    def source_lineage(self,entry,request,source):return []
    def verify_source_lineage(self,entry,request,lineage):raise Forbidden('actual C0 source lineage owner is not configured')
    def verify_source_origin(self,entry,request,source):
        raise Forbidden('authoritative source/version/receipt resolver is not configured')
    def admission_allocation(self,entry,request,source_activity,parent_account):
        raise Forbidden('source qualification and parent allocation policy are not configured')
    def verify_endpoint(self,entry,request,work,intent):
        raise Forbidden('domain endpoint proofs are not configured')


class _CurrentWorkAuthority(StorageAuthority):
    """Always re-read local control after trusted callbacks, including commit."""
    def __init__(self,service):self.service=service
    def verify(self,entry,operation,request,instance_id,stage):
        result=self.service.authority.verify(entry,operation,request,instance_id,stage)
        self.service._guard_request(request)
        if stage=='commit':self.service._recheck_reprocessing(request)
        return result
    def project_response(self,entry,operation,request,response,instance_id,stage):
        result=self.service.authority.project_response(entry,operation,request,response,instance_id,stage)
        self.service._guard_request(request)
        if stage=='commit':self.service._recheck_reprocessing(request)
        return result


def _slot(value=None):
    return {'status':'not_applicable' if value is None else 'known','value':value,
            'reason_code':'none','reason':'' if value is not None else 'no technical association','basis_refs':[]}


def _ref(instance,key,kind):
    return {'instance_id':instance,'id':key,'kind':kind,'revision':_slot()}


def _ref_identity(ref):
    revision=ref['revision']
    return {key:ref[key] for key in ('instance_id','id','kind')} | {
        'revision':revision['value'] if revision['status']=='known' else None}


def origin_identity(source):
    """Independent of notification activity and copied artifact identity."""
    def refslot(slot):return _ref_identity(slot['value']) if slot['status']=='known' else None
    return contract.fingerprint({'source':_ref_identity(source['source']),
        'source_kind':source['source_kind'],'source_revision':source['source_revision']['value'] if source['source_revision']['status']=='known' else None,
        'original_result':refslot(source['original_result']),'receipt':refslot(source['receipt'])})


def processing_identity(request):
    source=request['payload']['source']
    return contract.fingerprint({'origin':origin_identity(source),'source_activity':_ref_identity(request['payload']['source_activity']),
        'digest':source['digest'],'locator':source['locator'],'view_digest':source['view_digest'],
        'purpose':request['payload']['purpose'],'method':request['payload']['processing_method']})


class ToolLearningWork:
    def __init__(self,store,authority=None,clock=utc):
        self.s=store;self.authority=WorkAuthority() if authority is None else authority
        if not isinstance(self.authority,WorkAuthority):raise ContractError('trusted WorkAuthority port required')
        self.clock=clock;self.storage=ToolLearningStore(store,_CurrentWorkAuthority(self))

    def _ref(self,key,kind):return _ref(self.s.instance_id,key,kind)

    def _local_gate(self,request,activity=None):
        self.s.assert_execution_allowed()
        now=self.clock();contract.validate('UTC',now)
        if request['control']['cancelled']:raise Forbidden('cancelled control snapshot')
        if request['budget']['deadline']<=now:raise Forbidden('request deadline exhausted')
        if activity is not None:
            activity=self.s.row('activities',activity['id'])
            if activity['cancel_requested_at'] or activity['state']=='cancelled':raise Forbidden('source or work activity cancelled')
            if activity['deadline'] and activity['deadline']<=now:raise Forbidden('activity deadline exhausted')

    def _guard_request(self,request):
        self._local_gate(request)
        if request['work_ref']['status']=='known':
            work=self.s.row('tl_work',request['work_ref']['value']['id'])
            for key in ('source_activity_id','learning_activity_id'):
                self._local_gate(request,self.s.row('activities',work[key]))
        elif 'source_activity' in request['payload']:
            self._local_gate(request,self.s.row('activities',request['payload']['source_activity']['id']))

    def _response(self,request,work,disposition='applied',error='NONE',reason='none',operation='admit_observation'):
        return {'command_id':request['command_id'],'operation':operation,'disposition':disposition,'owner':'M14',
            'result_refs':[self._ref(work['id'],'tl_work')],'current':_slot(),
            'reason':reason,'error_code':error,'coverage':{'state':'complete','domain':_slot('one registered work'),
                'scanned':1,'limit':1,'truncated':False,'missing':[]},
            'retry':{'allowed':False,'condition':_slot(),'resume_work':_slot()},'committed_at':_slot(self.clock())}

    def _recheck_reprocessing(self,request):
        if getattr(self,'_pending_reprocessing',None) is None:return
        from digital_life.application.learning.reprocessing import current_reprocessing_grant
        previous=self.s.row('tl_work',request['payload']['previous_work']['value']['id'])
        if current_reprocessing_grant(self.s,request,previous)!=self._pending_reprocessing:
            raise Forbidden('current reprocessing proof changed before commit')

    def admit(self,entry,envelope):
        contract.validate_request('admit_observation',envelope)
        request=contract.loads(dumps(envelope))
        with dispatch_gate(self.s.root):
            self._local_gate(request)
            self._pending_reprocessing=None
            try:return self.storage.execute(entry,'admit_observation',request,lambda tx:self._admit(tx,entry,request))
            finally:self._pending_reprocessing=None

    def _admit(self,tx,entry,request):
        source=request['payload']['source'];source_ref=request['payload']['source_activity']
        self.storage.validate_ref(source_ref,expected_kind='activities')
        activity=self.s.row('activities',source_ref['id']);self._local_gate(request,activity)
        if json.loads(activity['budget_json']).get('contract')=='TL-WORK-BUDGET-1':
            raise Forbidden('nested TL parent allocation is not enabled')
        self.storage.validate_ref(source['source']);self.storage.validate_ref(source['artifact'],expected_kind='artifacts')
        for field in ('original_result','receipt'):
            if source[field]['status']=='known':self.storage.validate_ref(source[field]['value'])
        verified=self.authority.verify_source_origin(entry,contract.loads(dumps(request)),contract.loads(dumps(source)))
        if verified is not None:raise Forbidden('source resolver must attest by successful return')
        artifact=self.s.row('artifacts',source['artifact']['id'])
        if artifact['size']>request['budget']['max_bytes']:raise Forbidden('source material exceeds byte bound')
        self.storage.read_artifact(source['artifact']['id'])
        if artifact['hash']!=source['digest']['hex'] or artifact['media_type']!=source['media_type']:
            raise ContractError('source material digest/media mismatch')
        parent_ref=request['budget']['account_ref'];self.storage.validate_ref(parent_ref,expected_kind='activity_budget_accounts')
        parent=self.s.row('activity_budget_accounts',parent_ref['id'])
        if parent['activity_id']!=activity['id']:raise Forbidden('source budget belongs to another activity')
        resolved=self.authority.admission_allocation(entry,contract.loads(dumps(request)),dict(activity),dict(parent))
        if type(resolved) is not AdmissionAllocation:raise Forbidden('trusted admission allocation required')
        parent_budget=contract.loads(dumps(resolved.parent_budget));contract.validate('Budget',parent_budget)
        if parent_budget['account_ref']!=parent_ref:raise Forbidden('resolved parent account differs from request')
        for key in CAPS:
            if request['budget'][key]>parent_budget[key]:raise Forbidden('request exceeds resolved parent caps')
        identity=processing_identity(request);origin=origin_identity(source)
        rows=self.s.db.execute('SELECT * FROM tl_work WHERE instance_id=? ORDER BY recorded_at,id',(self.s.instance_id,)).fetchall()
        same_origin=[]
        for row in rows:
            condition=self.storage.read_artifact(row['conditions_artifact_id'])
            if type(condition) is dict and condition.get('origin_identity')==origin:same_origin.append(dict(row))
        prior=request['payload']['previous_work'];reprocessing=None
        if prior['status']=='known':
            self.storage.validate_ref(prior['value'],expected_kind='tl_work')
            previous=self.s.row('tl_work',prior['value']['id'])
            condition=self.storage.read_artifact(previous['conditions_artifact_id'])
            if condition.get('origin_identity')!=origin:raise Conflict('previous_work has different source identity')
            from digital_life.application.learning.reprocessing import current_reprocessing_grant
            try:reprocessing=current_reprocessing_grant(self.s,request,previous)
            except ContractError:return self._response(request,previous,'blocked','RESTORE_BLOCKED','other')
            self._pending_reprocessing=reprocessing
            identity=contract.fingerprint({'processing':identity,'reprocessing_grant':reprocessing['grant_ref']})
        for existing in same_origin:
            if existing['processing_identity']==identity:
                return self._response(request,existing,'reused')
        if same_origin and reprocessing is None:
            return self._response(request,same_origin[0],'blocked','RESTORE_BLOCKED','other')
        work_id,activity_id,account_id=identifier(),identifier(),identifier()
        budget=contract.loads(dumps(request['budget']))
        budget['account_ref']=self._ref(account_id,'activity_budget_accounts')
        budget['deadline']=min(t for t in (budget['deadline'],parent_budget['deadline'],activity['deadline']) if t is not None)
        if budget['deadline']<=self.clock():raise Forbidden('allocated deadline exhausted')
        self._allocate_parent(activity,parent,parent_budget,work_id,activity_id,account_id,budget)
        document=make_work_budget(budget,source_budget=request['budget'])
        binding=tx.create_learning_activity(activity_id=activity_id,account_id=account_id,work_id=work_id,
            source_activity=source_ref,producer=request['principal'],source=source,budget_document=document,deadline=budget['deadline'])
        conditions={'contract':'TL-WORK-CONDITIONS-1','origin_identity':origin,'processing_identity':identity,
            'budget':budget,'source_budget':request['budget'],'reason':'admitted','resume_conditions':[],
            'source':source,'source_activity':source_ref,'time_limit_ms':binding['time_limit_ms']}
        if reprocessing is not None:conditions['reprocessing']=reprocessing
        fields={'id':work_id,'learning_activity_id':activity_id,'source_activity_id':activity['id'],
            'source_artifact_id':source['artifact']['id'],'purpose':request['payload']['purpose'],'processing_identity':identity,
            'state':'admitted','phase':'admit','review_round':0,'conditions_artifact_id':tx.put_artifact(conditions),
            'control_artifact_id':tx.put_artifact(request['control'],'Control'),
            'method_artifact_id':tx.put_artifact(request['payload']['processing_method'],'Method'),
            'deadline':budget['deadline'],'budget_account_id':account_id,'row_revision':0}
        tx.insert('tl_work',**fields)
        lineage=self.authority.source_lineage(entry,contract.loads(dumps(request)),contract.loads(dumps(source)))
        if type(lineage) is not list or len(lineage)>128:raise ContractError('bounded C0 lineage required')
        if lineage:
            if self.authority.verify_source_lineage(entry,contract.loads(dumps(request)),contract.loads(dumps(lineage))) is not None:raise Forbidden('C0 lineage owner must attest with None')
            child=self.s.row('activities',activity_id);signal=self.s.row('perception_signals',child['trigger_event_id'])
            consumers=[self._ref(work_id,'tl_work'),self._ref(activity_id,'activities'),self._ref(signal['id'],'perception_signals'),self._ref(signal['artifact_id'],'artifacts')]+[self._ref(fields[name],'artifacts') for name in ('conditions_artifact_id','control_artifact_id','method_artifact_id')]
            for index,item in enumerate(lineage):
                types.obj(item,('token','scope'));contract.validate('VersionToken',item['token']);contract.validate('Scope',item['scope'])
                token=item['token'];revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.s.instance_id,token['object']['id'],token['revision'])).fetchone()
                for consumer in consumers:
                    for relation in ('read','delete'):
                        path='/c0/'+work_id+'/'+str(index);dependency={'target':token['object'],'expected':token,'relation':relation,'consumer_purpose':request['principal']['purpose']}
                        metadata={'contract':'TL-DEPENDENCY-1','consumer':consumer,'dependency':dependency,'field_path':path,'scope':item['scope']}
                        tx.insert('tl_dependency',id=identifier(),consumer_ref_id=consumer['id'],source_ref_id=token['object']['id'],source_revision_id=revision[0] if revision else None,relation=relation,purpose=request['principal']['purpose'],expected_epoch=token['epoch'],field_path=path,metadata_artifact_id=tx.put_artifact(metadata))
        if reprocessing is not None:
            self.s.event('tool_learning.reprocessing_admitted',payload={'work_id':work_id,'previous_work':prior['value'],'grant_ref':reprocessing['grant_ref'],'origin_identity':origin,'new_observation_count':0,'independent_sample_count':0,'gain':'not_measured'},source='tl.reprocessing.admitted',key=reprocessing['grant_ref']['id'],activity=activity_id)
        self._local_gate(request,activity)
        return self._response(request,fields)

    def _allocate_parent(self,activity,parent,caps,work_id,activity_id,account_id,budget):
        data=json.loads(activity['budget_json']);ledger=data.get('tl_work_allocations')
        if ledger is None:ledger={'contract':'TL-WORK-ALLOCATIONS-1','caps':caps,'allocations':{}}
        if ledger.get('contract')!='TL-WORK-ALLOCATIONS-1' or ledger.get('caps')!=caps or type(ledger.get('allocations')) is not dict:
            raise Conflict('parent allocation ledger/caps mismatch')
        allocated=[v['budget'] for v in ledger['allocations'].values()]
        own_usage={key:0 for key in CAPS}
        if data.get('contract')=='TL-ACTIVITY-BUDGET-1':
            from digital_life.application.learning.activity_budget import usage_occupancy
            occupancy=usage_occupancy(data)
            from digital_life.application.learning.budget import CAPS as RESOURCE_CAPS
            for dimension,field in RESOURCE_CAPS.items():own_usage[field]=occupancy[dimension]
        for key in CAPS:
            if own_usage[key]+sum(b[key] for b in allocated)+budget[key]>caps[key]:raise Forbidden('parent allocation exhausted: '+key)
        reservations=self.s.db.execute("SELECT * FROM budget_reservations WHERE instance_id=? AND activity_id=? AND state<>'released'",(self.s.instance_id,activity['id'])).fetchall()
        if any(row['state']=='usage_unknown' for row in reservations):
            raise Forbidden('parent usage remains unknown; new allocation is blocked')
        if sum(r['reserved_tokens'] for r in reservations)+sum(b['max_input_tokens']+b['max_output_tokens'] for b in allocated)+budget['max_input_tokens']+budget['max_output_tokens']>parent['token_limit']:
            raise Forbidden('parent token allocation exhausted')
        for cap,column,limit in (('max_attempts','reserved_attempts','attempt_limit'),('max_tool_calls','reserved_tool_calls','tool_call_limit')):
            if sum(r[column] for r in reservations)+sum(b[cap] for b in allocated)+budget[cap]>parent[limit]:raise Forbidden('parent allocation exhausted: '+cap)
        ledger['allocations'][work_id]={'activity_id':activity_id,'account_id':account_id,'budget':budget}
        data['tl_work_allocations']=ledger
        cur=self.s.db.execute('UPDATE activity_budget_accounts SET revision=revision+1 WHERE id=? AND instance_id=? AND revision=?',(parent['id'],self.s.instance_id,parent['revision']))
        if cur.rowcount!=1:raise Conflict('parent account changed')
        self.s.db.execute('UPDATE activities SET budget_json=? WHERE id=? AND instance_id=?',(dumps(data),activity['id'],self.s.instance_id))

    def transition(self,entry,envelope,target,phase,reason):
        """Forward local states only. Resume/review execution belongs to IM13."""
        operation='assess_observation';contract.validate_request(operation,envelope)
        if type(reason) is not str or not reason:raise ContractError('transition reason required')
        request=contract.loads(dumps(envelope))
        method=request['payload']['method']
        if method['name']!='tl-work-transition' or method['version']!='1' or method['request_ref']['status']!='known':
            raise ContractError('transition requires a fingerprint-bound intent artifact')
        self.storage.validate_ref(method['request_ref']['value'],expected_kind='artifacts')
        intent=self.storage.read_artifact(method['request_ref']['value']['id'])
        expected=request['expected']
        wanted={'contract':'TL-WORK-TRANSITION-1','work_id':request['work_ref']['value']['id'],
                'expected_revision':expected['value']['revision'] if expected['status']=='known' else None,
                'target':target,'phase':phase,'reason':reason}
        if intent!=wanted:raise Conflict('transition differs from fixed intent artifact')
        with dispatch_gate(self.s.root):
            self._local_gate(request)
            def apply(tx):
                ref=request['work_ref']['value'];self.storage.validate_ref(ref,expected_kind='tl_work')
                work=self.s.row('tl_work',ref['id']);activity=self.s.row('activities',work['learning_activity_id'])
                self._local_gate(request,activity)
                if target not in FORWARD.get(work['state'],set()):raise Forbidden('ordinary transition cannot resume or change terminal work')
                if phase not in ('admit','assess','decide','represent','complete'):raise ContractError('invalid work phase')
                expected_phase=('complete' if target in TERMINAL else 'assess' if target=='processing'
                    else 'decide' if target=='awaiting_decision' else 'represent' if target=='handoff_pending' else work['phase'])
                if phase!=expected_phase:raise Forbidden('state/phase combination is not a legal continuation point')
                expected=request['expected']
                if expected['status']!='known' or expected['value']['object']['id']!=work['id'] or expected['value']['revision']!=work['row_revision']:
                    raise Conflict('expected work CAS revision required')
                self.storage.validate_ref(expected['value']['object'],expected_kind='tl_work')
                if request['budget']['account_ref']['id']!=work['budget_account_id'] or request['budget']['deadline']>work['deadline']:
                    raise Forbidden('transition cannot replace budget or extend deadline')
                budget_status=ToolLearningBudget(self.s,clock=self.clock).check_work(work['id'],request['budget'])
                # Recording a zero-cost coordination fact consumes no new model
                # attempt. It cannot remove any other blocking condition.
                if any(reason!='attempts_exhausted' for reason in budget_status['block_reasons']):
                    raise Forbidden('work budget or state is blocked')
                if target in TERMINAL or target in ('awaiting_decision','handoff_pending'):
                    value=self.authority.verify_endpoint(entry,contract.loads(dumps(request)),dict(work),dict(intent))
                    if value is not None:raise Forbidden('endpoint verifier must attest by successful return')
                condition=self.storage.read_artifact(work['conditions_artifact_id']);condition['reason']=reason
                condition['resume_conditions']=[reason] if target in ('waiting','blocked','failed','stopped') else []
                new_condition=tx.put_artifact(condition)
                tx.cas_update('tl_work',work['id'],work['row_revision'],state=target,phase=phase,conditions_artifact_id=new_condition)
                work.update(state=target,phase=phase)
                return self._response(request,work,operation=operation)
            return self.storage.execute(entry,operation,request,apply)

    def snapshot(self,work_id):
        row=self.s.row('tl_work',work_id)
        budget=ToolLearningBudget(self.s,clock=self.clock).check_work(work_id)
        try:self.s.assert_execution_allowed();control_block=None
        except Forbidden as error:control_block=str(error)
        return {**row,'conditions':self.storage.read_artifact(row['conditions_artifact_id']),
                'budget':budget,'effective_blocked':budget['blocked'] or control_block is not None,
                'control_block_reason':control_block}
