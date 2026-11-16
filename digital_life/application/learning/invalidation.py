"""IM06 protective F1: persist barriers before deferred propagation/cleanup."""
from copy import deepcopy
from digital_life.domain.contracts import ContractError, Conflict, Forbidden, identifier, utc, dumps
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore, StorageAuthority
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.application.learning.eligibility import ToolLearningEligibility, EligibilityAuthority, scope_key, scope_overlap, slot, ref

DOMAINS=tuple(sorted(t.MODULES))


class InvalidationAuthority(StorageAuthority):
    def verify_change(self,entry,request,stage):
        raise Forbidden('source-owner and M12 protective change authority is not configured')
    def verify_protective_budget(self,entry,request,work,account,activity,stage):
        raise Forbidden('independent current M12 protective budget owner is not configured')
    def verify_version(self,entry,request,token,stage):
        raise Forbidden('authoritative source version resolver is not configured')
    def propagation_plan(self,entry,request):
        # Missing material is a durable follow-up obligation, not permission to omit F1.
        return None
    def barrier_applies(self,entry,request,barrier,payload,context):
        return None
    def overlap(self,entry,request,left,right):
        return scope_overlap(left,right)


class _VersionAuthority(EligibilityAuthority):
    def __init__(self,service,entry,request):self.service=service;self.entry=entry;self.request=request
    def verify_version(self,entry,principal,token,stage):
        return self.service.authority.verify_version(self.entry,deepcopy(self.request),deepcopy(token),stage)


class _StorageAuthority(StorageAuthority):
    def __init__(self,service):self.service=service
    def verify(self,entry,operation,request,instance_id,stage):
        grant=self.service.authority.verify(entry,operation,deepcopy(request),instance_id,stage)
        self.service._guard(entry,request,stage)
        return grant
    def project_response(self,entry,operation,request,response,instance_id,stage):
        projected=self.service.authority.project_response(entry,operation,deepcopy(request),response,instance_id,stage)
        self.service._guard(entry,request,stage)
        return projected
    def verify_external_ref(self,*args):return self.service.authority.verify_external_ref(*args)


class ToolLearningInvalidation:
    def __init__(self,store,authority=None,clock=utc,max_nodes=256,max_rows=1024):
        self.s=store;self.authority=InvalidationAuthority() if authority is None else authority
        if not isinstance(self.authority,InvalidationAuthority):raise ContractError('trusted InvalidationAuthority required')
        self.clock=clock;t.integer(max_nodes,1,100000);t.integer(max_rows,1,100000);self.max_nodes=max_nodes;self.max_rows=max_rows
        self.storage=ToolLearningStore(store,_StorageAuthority(self))

    def _guard(self,entry,request,stage):
        now=self.clock();c.validate('UTC',now)
        if request['control']['cancelled']:raise Forbidden('protective command cancelled')
        if request['budget']['deadline']<=now:raise Forbidden('protective command deadline exhausted')
        work=request['work_ref']['value'];self.storage.validate_ref(work,expected_kind='tl_work')
        row=self.s.db.execute('SELECT * FROM tl_work WHERE instance_id=? AND id=?',(self.s.instance_id,work['id'])).fetchone()
        if row is None:raise ContractError('protective work is unavailable')
        budget=request['budget'];self.storage.validate_ref(budget['account_ref'],expected_kind='activity_budget_accounts')
        independent=budget['account_ref']['id']!=row['budget_account_id']
        if independent:
            if request['principal']['module']!='M12':raise Forbidden('only actual M12 protective owner may use independent current resources')
            account=self.s.row('activity_budget_accounts',budget['account_ref']['id']);activity=self.s.row('activities',account['activity_id'])
            if account['activity_id']==row['learning_activity_id']:raise Forbidden('protective grant cannot relabel the old learning account')
            value=self.authority.verify_protective_budget(entry,deepcopy(request),row,account,activity,stage)
            if value is not None:raise Forbidden('protective resource owner must attest by None')
        else:
            if budget['deadline']>row['deadline']:raise Forbidden('protective command cannot reset original work deadline')
            activity=self.s.row('activities',row['learning_activity_id']);account=self.s.row('activity_budget_accounts',row['budget_account_id'])
            if account['activity_id']!=row['learning_activity_id']:raise ContractError('protective budget binding mismatch')
        if activity['cancel_requested_at'] or activity['state']=='cancelled':raise Forbidden('protective command activity cancelled')
        if budget['max_input_tokens']+budget['max_output_tokens']>account['token_limit'] or budget['max_tool_calls']>account['tool_call_limit'] or budget['max_attempts']>account['attempt_limit']:
            raise Forbidden('protective command exceeds bound account')
        value=self.authority.verify_change(entry,deepcopy(request),stage)
        if value is not None:raise Forbidden('change authority must not be a boolean')
        if self.clock()>=request['budget']['deadline']:raise Forbidden('protective deadline changed during verification')
        resolver=ToolLearningEligibility(self.s,_VersionAuthority(self,entry,request),self.max_nodes)
        resolver.validate_token(entry,request['principal'],request['payload']['source'],stage)
        if request['payload']['replacement']['status']=='known':resolver.validate_token(entry,request['principal'],request['payload']['replacement']['value'],stage)
        for subject in request['payload']['subjects']:self.storage.validate_ref(subject)
        for evidence in request['payload']['evidence']:
            self.storage.validate_ref(evidence['source'])
            self.storage.validate_ref(evidence['artifact'],expected_kind='artifacts')
            actual=self.s.row('artifacts',evidence['artifact']['id'])
            self.storage.read_artifact(evidence['artifact']['id'])
            if actual['hash']!=evidence['digest']['hex'] or actual['media_type']!=evidence['media_type']:
                raise ContractError('change evidence bytes and digest/media mismatch')
            for key in ('original_result','receipt'):
                if evidence[key]['status']=='known':self.storage.validate_ref(evidence[key]['value'])
        if request['payload']['kind']=='erase':self.storage.validate_ref(request['payload']['erase_scope']['value'])
        # No ordinary assert_execution_allowed here: authorized protective writes
        # remain possible under stop/WAKE_DISABLED without starting anything.

    def apply(self,entry,envelope):
        c.validate_request('apply_invalidation',envelope);request=c.loads(dumps(envelope))
        if request['payload']['kind']=='erase' and request['principal']['purpose']!='erase':raise Forbidden('erase requires explicit erasure purpose')
        if self.s.db.in_transaction:raise Conflict('F1 requires independent transaction after the instance gate')
        with dispatch_gate(self.s.root):
            return self.storage.execute(entry,'apply_invalidation',request,lambda tx:self._apply(tx,entry,request))

    def _response(self,request,barrier,epoch):
        current=slot();current['reason']='F1 commits qualification epochs and barriers, not a new content/source revision; inspect the barrier and immutable change payload'
        return {'command_id':request['command_id'],'operation':'apply_invalidation','disposition':'applied','owner':request['principal']['module'],
                'result_refs':[ref(self.s,barrier,'tl_barrier')],'current':current,'reason':'none','error_code':'NONE',
                'coverage':{'state':'unknown','domain':slot('F1 root barrier and deferred propagation'),'scanned':0,'limit':self.max_nodes,'truncated':False,'missing':[{'status':'not_collected','value':None,'reason_code':'not_measured','reason':'propagation and cleanup remain pending','basis_refs':[]}]},
                'retry':{'allowed':False,'condition':slot(),'resume_work':slot()},'committed_at':slot(self.clock())}

    def _closure(self,token,kind):
        # A native revision is a separate consumer. Stable owner aliases retain
        # the exact revision, never a wildcard that contaminates newer heads.
        registered=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.s.instance_id,token['object']['id'],token['revision'])).fetchone()
        root=(token['object']['id'],registered[0] if registered else None)
        seen={root};queue=[root];truncated=False;scanned=0
        while queue:
            node,revision=queue.pop(0)
            rows=self.s.db.execute('SELECT consumer_ref_id,relation FROM tl_dependency WHERE instance_id=? AND source_ref_id=? AND (source_revision_id=? OR source_revision_id IS NULL OR ? IS NULL) ORDER BY id LIMIT ?',(self.s.instance_id,node,revision,revision,self.max_rows-scanned+1))
            for row in rows:
                scanned+=1
                if scanned>self.max_rows:return seen,True
                if row['relation']=='delete' and kind!='erase':continue
                consumer=row['consumer_ref_id']
                projected=self.s.db.execute('SELECT object_id FROM object_revision_registry WHERE instance_id=? AND id=?',(self.s.instance_id,consumer)).fetchone()
                edge=(projected[0],consumer) if projected else (consumer,None)
                if edge in seen:continue
                if len(seen)>=self.max_nodes:
                    truncated=True;continue
                seen.add(edge);queue.append(edge)
                # Some technical consumers point at the revision Ref itself.
                if projected and (consumer,None) not in seen:
                    if len(seen)>=self.max_nodes:truncated=True
                    else:seen.add((consumer,None));queue.append((consumer,None))
        return seen,truncated

    def _apply(self,tx,entry,request):
        payload=request['payload'];source=payload['source']['object'];fingerprint=c.fingerprint(payload)
        # Stable event identity is independent of command transport identity.
        prior=self.s.db.execute('SELECT * FROM tl_change WHERE instance_id=? AND change_key=?',(self.s.instance_id,payload['change_id'])).fetchone()
        if prior:
            if prior['fingerprint']!=fingerprint:raise Conflict('change identity has different substantive payload')
            barrier=self.s.db.execute('SELECT id FROM tl_barrier WHERE instance_id=? AND change_id=?',(self.s.instance_id,prior['id'])).fetchone()
            if barrier is None:raise ContractError('committed change has no durable root barrier')
            result=self._response(request,barrier[0],prior['result_epoch']);result['disposition']='reused';return result
        sk=scope_key(payload['affected_scope'])
        row=self.s.db.execute('SELECT * FROM tl_source_epoch WHERE instance_id=? AND source_ref_id=? AND scope_key=?',(self.s.instance_id,source['id'],sk)).fetchone()
        old=row['epoch'] if row else 0
        if old!=payload['expected_epoch']:raise Conflict('F1 expected scope epoch is stale')
        scope_artifact=tx.put_artifact(payload['affected_scope'],'Scope')
        change_id=payload['change_id'];new=old+1
        tx.insert('tl_change',id=change_id,change_key=payload['change_id'],fingerprint=fingerprint,payload_artifact_id=tx.put_artifact(payload),kind=payload['kind'],source_ref_id=source['id'],expected_epoch=old,result_epoch=new)
        if row:
            tx.cas_update('tl_source_epoch',row['id'],row['row_revision'],epoch=new)
        else:
            tx.insert('tl_source_epoch',source_ref_id=source['id'],scope_key=sk,scope_artifact_id=scope_artifact,epoch=new,row_revision=0)
        barrier=tx.insert('tl_barrier',change_id=change_id,source_ref_id=source['id'],source_epoch=new,kind=payload['kind'],scope_artifact_id=scope_artifact,authorization_ref_id=request['principal']['authorization']['id'],state='active',row_revision=0)
        discovered,truncated=self._closure(payload['source'],payload['kind'])
        try:plan=deepcopy(self.authority.propagation_plan(entry,deepcopy(request)))
        except (OSError,NotImplementedError):plan=None
        if plan is not None:
            if not isinstance(plan,dict) or len(plan)>len(DOMAINS) or set(plan)-set(DOMAINS):raise ContractError('propagation plan contains undeclared domains')
            remaining=self.max_rows
            bounded_plan={}
            for domain,targets in plan.items():
                if not isinstance(targets,list):raise ContractError('domain targets must be an explicit list')
                bounded_plan[domain]=targets[:remaining]
                if len(targets)>remaining:truncated=True
                remaining-=len(bounded_plan[domain])
                for target in bounded_plan[domain]:self.storage.validate_ref(target)
            plan=bounded_plan
        # Every domain receives the known closure and a pending scan obligation.
        # Missing plans, incomplete scans and empty targets never mean complete.
        inputs=self.s.db.execute('SELECT * FROM tl_input_dependency WHERE instance_id=? ORDER BY id LIMIT ?',(self.s.instance_id,self.max_rows+1)).fetchall()
        if len(inputs)>self.max_rows:truncated=True
        for domain in DOMAINS:
            targets={key:ref(self.s,key) for key,revision in discovered}
            for target in (plan or {}).get(domain,[]):targets[target['id']]=target
            material={'contract':'TL-PROPAGATION-TARGETS-1','change_id':change_id,'source':payload['source'],
                      'affected_scope':payload['affected_scope'],'subjects':payload['subjects'],'purposes':payload['purposes'],
                      'targets':list(targets.values()),'scan_pending':True,'scan_truncated':truncated,'required_domain':domain}
            coverage={'state':'partial' if truncated else 'unknown','domain':slot(domain),'scanned':len(discovered),'limit':self.max_nodes,
                      'truncated':truncated,'missing':[{'status':'not_collected','value':None,'reason_code':'not_measured','reason':'owner-domain dependency and managed-copy scan remains pending','basis_refs':[]}]}
            tx.insert('tl_propagation',barrier_id=barrier,domain=domain,targets_artifact_id=tx.put_artifact(material),coverage_artifact_id=tx.put_artifact(coverage,'Coverage'),state='pending',generation=0,deadline=request['budget']['deadline'],budget_account_id=request['budget']['account_ref']['id'],row_revision=0)
        for row in inputs[:self.max_rows]:
            if not any(key==row['source_ref_id'] and (revision is None or row['source_revision_ref_id'] is None or revision==row['source_revision_ref_id']) for key,revision in discovered):continue
            if payload['purposes'] and row['purpose'] not in payload['purposes']:continue
            if row['retention_state']=='erased':continue
            # No per-row Scope column exists: unknown applicability is conservative.
            context={'input':dict(row),'recipient':ref(self.s,row['recipient_ref_id']),'purpose':row['purpose'],'request':ref(self.s,row['request_ref_id'])}
            applies=self.authority.barrier_applies(entry,deepcopy(request),{'id':barrier,'source_epoch':new},deepcopy(payload),context)
            if applies is not None and type(applies) is not bool:raise ContractError('barrier applicability must be true/false/unknown')
            if applies is False:continue
            state='erase_pending' if payload['kind']=='erase' or row['retention_state']=='erase_pending' else 'blocked'
            tx.cas_update('tl_input_dependency',row['id'],row['row_revision'],retention_state=state)
        self._guard(entry,request,'f1_before_result')
        return self._response(request,barrier,new)
