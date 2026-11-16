"""IM09 deterministic fixed-version representation and atomic C2 only."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc,dumps,sha
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore,StorageAuthority,command_fingerprint
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.application.learning.eligibility import ToolLearningEligibility,EligibilityAuthority,slot,ref,same_ref,insert
from digital_life.application.learning.budget import ToolLearningBudget


class RepresentationAuthority(StorageAuthority):
    def read_byte_limit(self,entry,request,snapshot):return min(snapshot['remaining']['bytes'],1048576)
    def verify_handoff(self,entry,operation,request,context,stage):raise Forbidden('actual M04/worker authority is not configured')
    def verify_read_accounting(self,entry,request,context,read_context,stage):raise Forbidden('metered representation opportunity is not configured')
    def verify_group(self,entry,request,contexts,stage):raise Forbidden('actual group member authority is not configured')
    def verify_retention(self,entry,request,context,stage):raise Forbidden('current construction/stage retention authority is not configured')
    def resolve_stage_entry(self,entry,request,stage_material):raise Forbidden('current authenticated stage member channel is not configured')


class _Authority(StorageAuthority):
    def __init__(self,service):self.service=service
    def verify(self,entry,operation,request,instance_id,stage):
        actual=self.service._entry
        grant=self.service.authority.verify(actual,operation,deepcopy(request),instance_id,stage)
        self.service._guard(actual,operation,request,stage);return grant
    def project_response(self,entry,operation,request,response,instance_id,stage):
        actual=self.service._entry
        result=self.service.authority.project_response(actual,operation,deepcopy(request),response,instance_id,stage)
        self.service._guard(actual,operation,request,stage);return result


class _Eligibility(EligibilityAuthority):
    def __init__(self,service,authority):self.service=service;self.authority=authority
    def verify(self,entry,*args):return self.authority.verify(self.service._qualification_entry,*args)
    def verify_version(self,entry,*args):return self.authority.verify_version(self.service._qualification_entry,*args)
    def barrier_applies(self,entry,*args):return self.authority.barrier_applies(self.service._qualification_entry,*args)
    def overlap(self,entry,*args):return self.authority.overlap(self.service._qualification_entry,*args)


class ToolLearningRepresentation:
    def __init__(self,store,authority=None,eligibility_authority=None,clock=utc,max_members=32):
        self.s=store;self.authority=RepresentationAuthority() if authority is None else authority
        if not isinstance(self.authority,RepresentationAuthority):raise ContractError('trusted RepresentationAuthority required')
        t.integer(max_members,1,128);self.max_members=max_members;self.clock=clock
        self._qualification_entry=None
        actual_eligibility=EligibilityAuthority() if eligibility_authority is None else eligibility_authority
        if not isinstance(actual_eligibility,EligibilityAuthority):raise ContractError('trusted eligibility authority required')
        self.storage=ToolLearningStore(store,_Authority(self));self.eligibility=ToolLearningEligibility(store,_Eligibility(self,actual_eligibility));self.budget=ToolLearningBudget(store)
        self._committing=[];self._entry=None;self._written={};self._claimed_token=None
    def _attest(self,value):
        if value is not None:raise Forbidden('authority must attest, not return a boolean')
    def _read(self,key,type_name=None,cap=1048576):
        if self.s.row('artifacts',key)['size']>cap:raise Forbidden('representation artifact byte cap exceeded')
        return self.storage.read_artifact(key,type_name)
    def _qualify(self,entry,request,token,scope,stage):
        p=request['principal'];previous=self._qualification_entry;self._qualification_entry=entry
        try:
            if self.s.db.in_transaction:return self.eligibility._check('tl.representation.qualification',p,token,scope,p['purpose'],p['recipient'],stage)
            return self.eligibility.check('tl.representation.qualification',p,token,scope,p['purpose'],p['recipient'],stage)
        finally:self._qualification_entry=previous
    def _context(self,entry,operation,request,stage):
        if request['principal']['module']!='M04' or request['principal']['purpose']!='represent':raise Forbidden('actual representation principal required')
        self.storage.validate_ref(request['payload']['handoff'],expected_kind='tl_handoff');self.storage.validate_ref(request['payload']['worker'])
        handoff=self.s.row('tl_handoff',request['payload']['handoff']['id']);work=self.s.row('tl_work',handoff['work_id'])
        if request['work_ref']['status']!='known' or request['work_ref']['value']['id']!=work['id']:raise Forbidden('handoff belongs to another work')
        snapshot=self.budget.check_work(work['id'],request['budget'])
        read_limit=self.authority.read_byte_limit(entry,deepcopy(request),deepcopy(snapshot));t.integer(read_limit,0,min(request['budget']['max_bytes'],1048576))
        hard=[x for x in snapshot['block_reasons'] if x not in ('attempts_exhausted','work_waiting','work_blocked','work_failed','work_stopped','work_completed','work_no_change','work_rejected')]
        if hard:raise Forbidden(','.join(hard))
        context={'handoff':dict(handoff),'work':dict(work),'budget':snapshot,'read_byte_limit':read_limit}
        self._attest(self.authority.verify_handoff(entry,operation,deepcopy(request),deepcopy(context),stage))
        self._fresh(request,context)
        read_context={'occurrence_id':identifier(),'request_fingerprint':command_fingerprint(request),'work_ref':request['work_ref']['value'],'account_ref':request['budget']['account_ref'],'stage':stage,'byte_cap':read_limit,'scan_cap':128}
        self._attest(self.authority.verify_read_accounting(entry,deepcopy(request),deepcopy(context),deepcopy(read_context),stage))
        revision=self.s.row('tl_content_revision',handoff['content_revision_id']);decision=self.s.row('tl_decision',handoff['decision_id']);content=self.s.row('tl_content',revision['content_id'])
        if revision['decision_id']!=decision['id'] or revision['status']!='accepted' or decision['operation']!='accept' or decision['content_revision_id']!=revision['id'] or decision['work_id']!=work['id']:raise Conflict('handoff is not an actual accepted version/decision')
        if content['head_revision_id']!=revision['id']:raise Conflict('handoff content version is no longer the current head')
        payload=self._read(revision['payload_artifact_id'],cap=read_context['byte_cap'])
        if payload.get('contract')!='TL-CONTENT-1':raise ContractError('fixed content material unavailable')
        if not 1<=len(payload['claims'])<=64 or sum(len(x['evidence']) for x in payload['claims'])>128:raise Forbidden('representation claim/evidence scan cap exceeded')
        for claim in payload['claims']:c.validate('Claim',claim)
        c.validate('Scope',payload['scope'])
        token={'object':ref(self.s,content['id']),'revision':revision['revision_no'],'epoch':self.eligibility.current_epoch(ref(self.s,content['id']),payload['scope'])}
        self._qualify(entry,request,token,payload['scope'],stage)
        dependencies=self.s.db.execute('SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? ORDER BY id LIMIT 129',(self.s.instance_id,revision['id'])).fetchall()
        if len(dependencies)>128:raise Forbidden('representation dependency scan cap exceeded')
        fixed=[{'target':deepcopy(token['object']),'relation':'representation','expected':deepcopy(token),'consumer_purpose':'represent'}]
        for row in dependencies:
            meta=self.eligibility._metadata(row);dependency=deepcopy(meta['dependency']);dependency['consumer_purpose']='represent';fixed.append(dependency)
        from digital_life.application.learning.representation_upgrade import language
        context['language']=language(self.s,context['handoff'])
        from digital_life.application.learning.representation_upgrade import grant_for_handoff
        upgrade=grant_for_handoff(self.s,context['handoff'])
        if upgrade is not None:
            grant_token={'object':ref(self.s,upgrade[0]['id']),'revision':0,'epoch':0}
            self._qualify(entry,request,grant_token,payload['scope'],stage+'_rendering_authorization')
            fixed.append({'target':grant_token['object'],'relation':'read','expected':grant_token,'consumer_purpose':'represent'})
        context.update(revision=dict(revision),decision=dict(decision),content=dict(content),payload=payload,token=token,dependencies=fixed)
        self._fresh(request,context);return context
    def _fresh(self,request,context):
        self.s.assert_execution_allowed()
        if request['control']['cancelled']:raise Forbidden('representation request cancelled')
        if self.clock()>=min(context['handoff']['deadline'],context['work']['deadline'],request['budget']['deadline']):raise Forbidden('representation deadline exhausted')
        for key in ('source_activity_id','learning_activity_id'):
            activity=self.s.row('activities',context['work'][key])
            if activity['cancel_requested_at'] or activity['state']=='cancelled':raise Forbidden('representation activity cancelled')
    def _guard(self,entry,operation,request,stage):
        context=self._context(entry,operation,request,stage)
        for original_entry,bound,expiry in self._committing:
            other=self._context(original_entry,'publish_representation',bound,stage+'_member')
            self._fresh(bound,other)
            if self.clock()>=expiry:raise Conflict('C2 member lease expired before commit')
            row=self.s.row('tl_handoff',other['handoff']['id'])
            if row['state']=='published':
                if row['representation_id']!=bound['payload']['representation']['id']:raise Conflict('C2 member changed after publication')
            else:self._lease(bound,other)
        self._fresh(request,context)
        if stage=='commit' and context['handoff']['state']=='leased':
            if operation=='publish_representation':self._lease(request,context)
            elif self.clock()>=context['handoff']['lease_expires_at']:raise Conflict('new claim expired before commit')
        # No authority callback after this pass. Later member callbacks cannot
        # silently expire an earlier lease or mutate its consumed receipt.
        deadlines=[]
        for original_entry,bound,expiry in self._committing:
            row=self.s.row('tl_handoff',bound['payload']['handoff']['id']);work=self.s.row('tl_work',row['work_id'])
            deadlines.append(min(expiry,row['deadline'],work['deadline'],bound['budget']['deadline']))
            if row['lease_generation']!=bound['payload']['lease_generation']:raise Conflict('C2 consumed generation changed')
            if row['state']=='published':
                written=self._written.get(row['id'])
                if written is None or (row['receipt_artifact_id'],row['row_revision'],row['representation_id'])!=written:raise Conflict('C2 consumed receipt changed')
                receipt=self._read(row['receipt_artifact_id'])
                if (receipt['worker']!=bound['payload']['worker'] or receipt['lease_generation']!=bound['payload']['lease_generation'] or receipt['lease_expires_at']!=expiry or receipt['representation']['id']!=bound['payload']['representation']['id'] or receipt['request_fingerprint']!=command_fingerprint(bound)):raise Conflict('C2 receipt does not bind actual lease')
            for key in ('source_activity_id','learning_activity_id'):
                activity=self.s.row('activities',work[key])
                if activity['cancel_requested_at'] or activity['state']=='cancelled':raise Forbidden('C2 member cancelled before commit')
        if self._claimed_token is not None and stage=='commit':
            claimed=self.s.row('tl_handoff',self._claimed_token['id'])
            if any(claimed[key]!=value for key,value in self._claimed_token.items()):raise Conflict('new claim control changed before commit')
            deadlines.append(claimed['lease_expires_at'])
        self.s.assert_execution_allowed()
        if any(self.clock()>=deadline for deadline in deadlines):raise Conflict('C2/claim lease or member deadline expired after final callback')
        return context
    def _lease(self,request,context):
        row=self.s.row('tl_handoff',context['handoff']['id']);payload=request['payload']
        if row['state']!='leased' or row['lease_generation']!=payload['lease_generation'] or row['lease_worker_id']!=payload['worker']['id'] or self.clock()>=row['lease_expires_at']:raise Conflict('current representation lease/worker is not valid')
        return row
    def _response(self,request,operation,row,disposition='applied',refs=None):
        return {'command_id':request['command_id'],'operation':operation,'disposition':disposition,'owner':'M04','result_refs':refs or [ref(self.s,row['id'])],
            'current':slot({'object':ref(self.s,row['id']),'revision':row['row_revision'],'epoch':row['lease_generation']}),'reason':'none','error_code':'NONE',
            'coverage':{'state':'complete' if disposition!='deferred' else 'partial','domain':slot('fixed C2 representation obligations'),'scanned':1,'limit':self.max_members,'truncated':False,'missing':[]},
            'retry':{'allowed':False,'condition':slot('await fixed group members') if disposition=='deferred' else slot(),'resume_work':slot()},'committed_at':slot(self.clock())}
    def claim(self,entry,envelope):return self._execute(entry,'claim_representation',envelope,self._claim)
    def publish(self,entry,envelope):return self._execute(entry,'publish_representation',envelope,self._publish)
    def _execute(self,entry,operation,envelope,callback):
        c.validate_request(operation,envelope);request=c.loads(dumps(envelope))
        if self.s.db.in_transaction:raise Conflict('representation operation requires own gate/transaction')
        with dispatch_gate(self.s.root):
            if self._entry is not None:raise Conflict('representation command reentry is not allowed')
            self._committing=[];self._written={};self._claimed_token=None;self._entry=entry
            try:return self.storage.execute('tl.representation.port',operation,request,lambda tx:callback(tx,entry,request))
            finally:self._committing=[];self._written={};self._claimed_token=None;self._entry=None
    def _claim(self,tx,entry,request):
        context=self._context(entry,'claim_representation',request,'claim');row=context['handoff'];p=request['payload']
        if row['lease_generation']!=p['expected_generation']:raise Conflict('claim generation is stale')
        if request['expected']['status']=='known' and request['expected']['value']!={'object':request['payload']['handoff'],'revision':row['row_revision'],'epoch':row['lease_generation']}:raise Conflict('claim CAS token differs')
        if row['state'] not in ('pending','retryable','leased') or row['state']=='leased' and self.clock()<row['lease_expires_at']:raise Conflict('handoff is not claimable')
        if row['attempts']>=context['budget']['limits']['attempts']:raise Forbidden('original representation attempt cap exhausted')
        expiry=(datetime.fromisoformat(self.clock().replace('Z','+00:00'))+timedelta(seconds=p['lease_seconds'])).isoformat(timespec='milliseconds').replace('+00:00','Z')
        expiry=min(expiry,row['deadline'],request['budget']['deadline'],context['work']['deadline'])
        tx.cas_update('tl_handoff',row['id'],row['row_revision'],state='leased',lease_worker_id=p['worker']['id'],lease_generation=row['lease_generation']+1,lease_expires_at=expiry,attempts=row['attempts']+1)
        self._claimed_token={key:self.s.row('tl_handoff',row['id'])[key] for key in ('id','row_revision','lease_generation','lease_worker_id','lease_expires_at','state')}
        self.s.event('representation.claim',payload={'handoff':row['id'],'generation':row['lease_generation']+1,'worker':p['worker'],'previous_generation':row['lease_generation']},source='tl.representation.claim',key=request['command_id'],activity=context['work']['learning_activity_id'])
        return self._response(request,'claim_representation',self.s.row('tl_handoff',row['id']))
    @staticmethod
    def render(payload,language='zh'):
        claims=payload['claims']
        labels={'zh':('来源性质','有限主张','时间/单位/条件','未知/冲突','证据定位'),'en':('Source nature','Scoped claims','Time/unit/conditions','Unknown/conflict','Evidence locators')}
        if language not in labels:raise Forbidden('no verified literal header mapping for this language')
        values=([[e['source_kind'] for e in claim['evidence']] for claim in claims],claims,payload['scope'],{'preserved_content':payload['preserved_content'],'unresolved_items':payload['unresolved_items']},[e for claim in claims for e in claim['evidence']])
        return '\n'.join(label+'：'+dumps(value) for label,value in zip(labels[language],values))
    def build(self,entry,envelope,claim_response):
        c.validate_request('claim_representation',envelope);c.validate('Response',claim_response)
        if claim_response['operation']!='claim_representation' or claim_response['command_id']!=envelope['command_id'] or claim_response['current']['status']!='known':raise ContractError('build requires the actual claim result')
        request=c.loads(dumps(envelope));token=claim_response['current']['value']
        if not same_ref(token['object'],request['payload']['handoff']):raise Conflict('claim result belongs to another handoff')
        request['payload']={'handoff':request['payload']['handoff'],'worker':request['payload']['worker'],'lease_generation':token['epoch']}
        actual=self.s.row('tl_handoff',token['object']['id'])
        if token['revision']!=actual['row_revision'] or token['epoch']!=actual['lease_generation']:raise Conflict('claim result is stale')
        if self.s.db.in_transaction:raise Conflict('build requires own read gate')
        with dispatch_gate(self.s.root),self.s.tx():
            context=self._context(entry,'build_representation',request,'build');self._lease(request,context)
            self._attest(self.authority.verify_retention(entry,deepcopy(request),deepcopy(context),'build'))
            # Recheck after authority callbacks before any source-derived write.
            context=self._context(entry,'build_representation',request,'build_write');self._lease(request,context)
            text=self.render(context['payload'],context['language'])
            if len(text.encode())>context['read_byte_limit']:raise Forbidden('complete representation exceeds byte cap')
            body=self.s.artifact(text,media_type='text/plain')
            self._body_delete_binding(context,ref(self.s,body))
            series=self.s.db.execute('SELECT * FROM tl_representation_head WHERE instance_id=? AND content_id=? AND format_version=?',(self.s.instance_id,context['content']['id'],'TL-TEXT-1')).fetchone()
            series_id=series['id'] if series else identifier();number=self.s.db.execute('SELECT coalesce(max(representation_no),0)+1 FROM tl_representation WHERE instance_id=? AND series_id=?',(self.s.instance_id,series_id)).fetchone()[0]
            source_refs=[]
            for claim in context['payload']['claims']:
                for evidence in claim['evidence']:
                    if evidence not in source_refs:source_refs.append(deepcopy(evidence))
            return {'id':identifier(),'series_ref':{'instance_id':self.s.instance_id,'id':series_id,'kind':'tl_representation_head','revision':slot()},'representation_no':number,'content_ref':ref(self.s,context['content']['id']),'content_revision':deepcopy(context['token']),'decision_ref':ref(self.s,context['decision']['id']),'format_version':'TL-TEXT-1','body_artifact':ref(self.s,body),'body_digest':{'algorithm':'sha256','hex':self.s.row('artifacts',body)['hash']},'claims':deepcopy(context['payload']['claims']),'source_refs':source_refs,'scope':deepcopy(context['payload']['scope']),'limitations':list(dict.fromkeys([v for claim in context['payload']['claims'] for v in claim['limitations']]+context['payload']['scope']['limitations'])),'dependencies':deepcopy(context['dependencies']),'group':slot(ref(self.s,context['handoff']['group_id'])) if context['handoff']['group_id'] else slot(),'published_at':self.clock()}
    def read_built(self,entry,envelope,claim_response,body_artifact):
        """Authorized draft read; raw M17 blob methods are internal machinery."""
        c.validate_request('claim_representation',envelope);c.validate('Response',claim_response)
        if claim_response['command_id']!=envelope['command_id'] or claim_response['operation']!='claim_representation' or claim_response['current']['status']!='known':raise ContractError('actual claim result required')
        request=c.loads(dumps(envelope));token=claim_response['current']['value']
        if not same_ref(token['object'],request['payload']['handoff']):raise Conflict('claim result owner differs')
        request['payload']={'handoff':request['payload']['handoff'],'worker':request['payload']['worker'],'lease_generation':token['epoch']}
        with dispatch_gate(self.s.root),self.s.tx():
            context=self._context(entry,'read_representation_draft',request,'draft_read');row=self._lease(request,context)
            if row['row_revision']!=token['revision']:raise Conflict('draft claim result is stale')
            self._attest(self.authority.verify_retention(entry,deepcopy(request),deepcopy(context),'draft_read'))
            context=self._context(entry,'read_representation_draft',request,'draft_read_use');self._lease(request,context)
            self.storage.validate_ref(body_artifact,expected_kind='artifacts')
            if self.s.row('artifacts',body_artifact['id'])['hash']!=sha(self.render(context['payload'],context['language']).encode()):raise Forbidden('body is not this fixed draft')
            return self._read(body_artifact['id'],cap=context['read_byte_limit'])

    def _body_delete_binding(self,context,body):
        dependency=deepcopy(context['dependencies'][0]);dependency['relation']='delete';path='/constructed/delete/'+context['revision']['id']
        metadata={'contract':'TL-DEPENDENCY-1','consumer':deepcopy(body),'dependency':dependency,'field_path':path,'scope':deepcopy(context['payload']['scope'])}
        old=self.s.db.execute("SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? AND source_ref_id=? AND relation='delete' AND purpose='represent' AND field_path=? AND expected_epoch=?",(self.s.instance_id,body['id'],dependency['target']['id'],path,dependency['expected']['epoch'])).fetchone()
        if old:
            if self.eligibility._metadata(old)!=metadata:raise Conflict('constructed body dependency changed meaning')
            return
        insert(self.s,'tl_dependency',consumer_ref_id=body['id'],source_ref_id=dependency['target']['id'],source_revision_id=context['revision']['id'],relation='delete',purpose='represent',expected_epoch=dependency['expected']['epoch'],field_path=path,metadata_artifact_id=self.s.artifact(metadata))

    def _validate_representation(self,entry,request,context):
        value=request['payload']['representation'];c.validate('Representation',value);h=context['handoff']
        expected={'content_ref':ref(self.s,context['content']['id']),'content_revision':context['token'],'decision_ref':ref(self.s,h['decision_id']),'format_version':h['format_version'],'claims':context['payload']['claims'],'scope':context['payload']['scope'],'dependencies':context['dependencies'],'group':slot(ref(self.s,h['group_id'])) if h['group_id'] else slot()}
        for key,item in expected.items():
            if value[key]!=item:raise Conflict('representation changes fixed '+key)
        evidence=[]
        for claim in context['payload']['claims']:
            for source in claim['evidence']:
                if source not in evidence:evidence.append(source)
        limitations=list(dict.fromkeys([v for claim in context['payload']['claims'] for v in claim['limitations']]+context['payload']['scope']['limitations']))
        if value['source_refs']!=evidence or value['limitations']!=limitations:raise Conflict('representation removes source or limitations')
        self.storage.validate_ref(value['body_artifact'],expected_kind='artifacts');body=self._read(value['body_artifact']['id'],cap=context['read_byte_limit'])
        if not isinstance(body,bytes) or body!=self.render(context['payload'],context['language']).encode() or self.s.row('artifacts',value['body_artifact']['id'])['hash']!=value['body_digest']['hex']:raise ContractError('representation body is not the fixed TL-TEXT-1 construction')
        if value['published_at']>self.clock():raise ContractError('representation claims a future publication time')
        self._attest(self.authority.verify_retention(entry,deepcopy(request),deepcopy(context),'publish_material'))
        self._fresh(request,context);return value
    def _dependency(self,tx,consumer,dependency,scope,path):
        metadata={'contract':'TL-DEPENDENCY-1','consumer':deepcopy(consumer),'dependency':deepcopy(dependency),'field_path':path,'scope':deepcopy(scope)}
        revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.s.instance_id,dependency['target']['id'],dependency['expected']['revision'])).fetchone()
        old=self.s.db.execute('SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? AND source_ref_id=? AND relation=? AND purpose=? AND field_path=? AND expected_epoch=?',(self.s.instance_id,consumer['id'],dependency['target']['id'],dependency['relation'],'represent',path,dependency['expected']['epoch'])).fetchone()
        if old:
            if self.eligibility._metadata(old)!=metadata:raise Conflict('representation dependency key changed meaning')
            return
        tx.insert('tl_dependency',consumer_ref_id=consumer['id'],source_ref_id=dependency['target']['id'],source_revision_id=revision[0] if revision else None,relation=dependency['relation'],purpose='represent',expected_epoch=dependency['expected']['epoch'],field_path=path,metadata_artifact_id=tx.put_artifact(metadata))
    def _members(self,context):
        group=self.s.row('tl_group',context['handoff']['group_id']);body=self._read(group['members_artifact_id'])
        t.obj(body,('contract','intent','members'))
        if body['contract']!='TL-C1-GROUP-MEMBERS-1' or not isinstance(body['members'],list) or not 1<=len(body['members'])<=self.max_members:raise ContractError('fixed group members unavailable')
        seen=set()
        for member in body['members']:
            t.obj(member,('proposal','content','content_revision_id','revision_no','format_version','handoff_id'))
            if member['handoff_id'] in seen:raise ContractError('duplicate fixed group handoff')
            seen.add(member['handoff_id']);row=self.s.row('tl_handoff',member['handoff_id']);revision=self.s.row('tl_content_revision',row['content_revision_id'])
            if row['group_id']!=group['id'] or row['content_revision_id']!=member['content_revision_id'] or revision['content_id']!=member['content']['id'] or revision['revision_no']!=member['revision_no'] or row['format_version']!=member['format_version'] or revision['product_id']!=member['proposal']['id']:raise Conflict('fixed group member mapping differs')
        if context['handoff']['id'] not in seen:raise Conflict('requested handoff not in fixed group')
        return dict(group),body['members']
    def _stage(self,tx,entry,request,context):
        h=context['handoff'];key=h['id']+':'+str(h['lease_generation']);prior=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND source='tl.representation.stage' AND source_event_id=?",(self.s.instance_id,key)).fetchone()
        if prior:
            material=self._read(prior[0])
            if material['fingerprint']!=command_fingerprint(request):raise Conflict('lease stage already binds another representation')
            return prior[0]
        artifact=tx.put_artifact({'contract':'TL-C2-STAGE-1','channel_binding':{'worker':deepcopy(request['payload']['worker']),'principal':deepcopy(request['principal'])},'request':deepcopy(request),'fingerprint':command_fingerprint(request)})
        consumer=ref(self.s,artifact)
        for index,dependency in enumerate(context['dependencies']):self._dependency(tx,consumer,dependency,context['payload']['scope'],'/stage/'+str(index))
        # Shared content-addressed body is a managed delete dependency, never
        # treated as independent support for every historical content version.
        deletion=deepcopy(context['dependencies'][0]);deletion['relation']='delete'
        self._dependency(tx,request['payload']['representation']['body_artifact'],deletion,context['payload']['scope'],'/stage/delete/'+context['revision']['id'])
        self.s.event('representation.stage',payload=self._read(artifact),source='tl.representation.stage',key=key,activity=context['work']['learning_activity_id'])
        return artifact
    def _publish(self,tx,entry,request):
        context=self._context(entry,'publish_representation',request,'publish');h=context['handoff']
        if h['state']=='published':
            receipt=self._read(h['receipt_artifact_id'])
            if receipt['request_fingerprint']!=command_fingerprint(request):raise Conflict('published handoff already consumed different input')
            return self._response(request,'publish_representation',h,'reused',[ref(self.s,h['representation_id'])])
        self._lease(request,context);self._validate_representation(entry,request,context)
        # Repeat qualification after retention callbacks before stage/body refs persist.
        context=self._context(entry,'publish_representation',request,'stage_write');self._lease(request,context)
        pending=[(entry,request,context)]
        group=None
        if h['group_id']:
            group,members=self._members(context)
            if group['state']!='pending':raise Conflict('group is not pending')
            self._stage(tx,entry,request,context);pending=[]
            for member in members:
                row=self.s.row('tl_handoff',member['handoff_id']);key=row['id']+':'+str(row['lease_generation'])
                stage=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND source='tl.representation.stage' AND source_event_id=?",(self.s.instance_id,key)).fetchone()
                if stage is None:return self._response(request,'publish_representation',self.s.row('tl_handoff',h['id']),'deferred')
                stage_token={'object':ref(self.s,stage[0]),'revision':0,'epoch':self.eligibility.current_epoch(ref(self.s,stage[0]),context['payload']['scope'])}
                self._qualify(entry,request,stage_token,context['payload']['scope'],'stage_read')
                material=self._read(stage[0]);t.obj(material,('contract','channel_binding','request','fingerprint'))
                bound=material['request'];c.validate_request('publish_representation',bound)
                if material['contract']!='TL-C2-STAGE-1' or material['fingerprint']!=command_fingerprint(bound) or bound['payload']['handoff']['id']!=row['id']:raise ContractError('stage immutable binding differs')
                binding=material['channel_binding'];t.obj(binding,('worker','principal'))
                if binding['worker']!=bound['payload']['worker'] or binding['principal']!=bound['principal']:raise ContractError('stage identity binding differs')
                actual_entry=self.authority.resolve_stage_entry(entry,deepcopy(request),deepcopy(material))
                other=self._context(actual_entry,'publish_representation',bound,'group_member');self._lease(bound,other);self._validate_representation(actual_entry,bound,other);pending.append((actual_entry,bound,other))
            self._attest(self.authority.verify_group(entry,deepcopy(request),[{'entry':x,'request':deepcopy(y),'context':deepcopy(z)} for x,y,z in pending],'C2_group'))
        self._committing=[(original_entry,deepcopy(bound),member_context['handoff']['lease_expires_at']) for original_entry,bound,member_context in pending]
        refs=[]
        for member_entry,bound,member_context in pending:
            # Last callback may stop/revoke/expire: fresh source and lease before writes.
            member_context=self._context(member_entry,'publish_representation',bound,'C2_write');self._lease(bound,member_context);self._validate_representation(member_entry,bound,member_context)
            member_context=self._context(member_entry,'publish_representation',bound,'C2_after_retention');self._lease(bound,member_context)
            self._write(tx,bound,member_context);refs.append(ref(self.s,bound['payload']['representation']['id']))
        if group:tx.cas_update('tl_group',group['id'],group['row_revision'],state='ready')
        return self._response(request,'publish_representation',self.s.row('tl_handoff',h['id']),refs=refs)
    def _write(self,tx,request,context):
        value=request['payload']['representation'];h=self.s.row('tl_handoff',context['handoff']['id']);series=self.s.db.execute('SELECT * FROM tl_representation_head WHERE instance_id=? AND content_id=? AND format_version=?',(self.s.instance_id,context['content']['id'],value['format_version'])).fetchone()
        if series and value['series_ref']['id']!=series['id']:raise Conflict('fixed series changed')
        if not series:tx.insert('tl_representation_head',id=value['series_ref']['id'],content_id=context['content']['id'],format_version=value['format_version'],representation_id=value['id'],expected_content_revision_id=context['revision']['id'],row_revision=0)
        number=self.s.db.execute('SELECT coalesce(max(representation_no),0)+1 FROM tl_representation WHERE instance_id=? AND series_id=?',(self.s.instance_id,value['series_ref']['id'])).fetchone()[0]
        if value['representation_no']!=number:raise Conflict('representation series version is stale')
        tx.insert('tl_representation',id=value['id'],series_id=value['series_ref']['id'],content_revision_id=context['revision']['id'],decision_id=h['decision_id'],format_version=value['format_version'],representation_no=number,payload_artifact_id=tx.put_artifact(value,'Representation'),body_artifact_id=value['body_artifact']['id'],body_digest=value['body_digest']['hex'],group_id=h['group_id'],state='ready')
        if series and series['representation_id']:tx.cas_update('tl_representation_head',series['id'],series['row_revision'],representation_id=value['id'],expected_content_revision_id=context['revision']['id'])
        elif series:tx.cas_update('tl_representation_head',value['series_ref']['id'],series['row_revision'],representation_id=value['id'],expected_content_revision_id=context['revision']['id'])
        if series and series['representation_id']:
            # Representation state is deliberately mutable, its payload is not.
            tx.update_representation_state(series['representation_id'],'superseded')
        for index,dependency in enumerate(context['dependencies']):self._dependency(tx,{'instance_id':self.s.instance_id,'id':value['id'],'kind':'tl_representation','revision':slot()},dependency,context['payload']['scope'],'/representation/'+str(index))
        receipt=tx.put_artifact({'contract':'TL-C2-RECEIPT-1','request_fingerprint':command_fingerprint(request),'handoff':request['payload']['handoff'],'lease_generation':h['lease_generation'],'worker':request['payload']['worker'],'lease_expires_at':h['lease_expires_at'],'representation':{'instance_id':self.s.instance_id,'id':value['id'],'kind':'tl_representation','revision':slot()}})
        tx.cas_update('tl_handoff',h['id'],h['row_revision'],state='published',lease_worker_id=None,lease_expires_at=None,representation_id=value['id'],receipt_artifact_id=receipt)
        self._written[h['id']]=(receipt,h['row_revision']+1,value['id'])
