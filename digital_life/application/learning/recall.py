"""IM10 purpose-limited reads and a separate fixed execution trace writer."""
from copy import deepcopy
from contextlib import contextmanager
import json
import re
import time
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc,dumps,sha
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.application.learning.eligibility import ToolLearningEligibility,EligibilityAuthority,slot,ref,same_ref,insert
from digital_life.application.learning.budget import ToolLearningBudget
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate


class RecallAuthority:
    def verify_request(self,entry,request,stage):raise Forbidden('current recall entry/purpose/recipient authority is not configured')
    def verify_audit(self,entry,request,stage):raise Forbidden('actual controller read-only authority is not configured')
    def verify_candidate_access(self,entry,request,candidate,stage):raise Forbidden('candidate metadata/retention authority is not configured')
    def verify_retention(self,entry,request,item,stage):raise Forbidden('current recall material retention authority is not configured')
    def execution_reservation(self,entry,request,run):raise Forbidden('actual original-run read reservation is not configured')
    def verify_execution_accounting(self,entry,request,context,read_context,stage):raise Forbidden('original-account retrieval opportunity is not configured')
    def verify_trace(self,entry,request,result,stage):raise Forbidden('fixed M04 recall audit write authority is not configured')
    def verify_input_binding(self,entry,request,result,target,principal,assembly,stage):raise Forbidden('actual input assembler authority is not configured')
    def index_candidates(self,entry,request,limit):raise NotImplementedError('index unavailable')
    def verify_fallback(self,entry,request):raise Forbidden('bounded primary fallback is not authorized')
    def scope_matches(self,entry,request,scope):return None
    def count_tokens(self,entry,request,whole_item):raise Forbidden('trusted tokenizer/upper bound is not configured')
    def legacy_material(self,entry,request,target,row):raise Forbidden('legacy memory/cognition domain material is not configured')
    def source_token(self,entry,request,evidence):raise Forbidden('actual source owner version resolver is not configured')
    def candidate_token(self,entry,request,target,row):raise Forbidden('actual audit candidate version owner is not configured')
    def read_boundary(self,entry,request,reader):raise Forbidden('source/Scope/index ports must bind the controlled reader')


class _Eligibility(EligibilityAuthority):
    def __init__(self,service,actual):self.service=service;self.actual=actual
    def verify(self,entry,*args):return self.actual.verify(self.service._entry,*args)
    def verify_version(self,entry,*args):return self.actual.verify_version(self.service._entry,*args)
    def verify_registration(self,entry,*args):return self.actual.verify_registration(self.service._entry,*args)
    def verify_callback(self,entry,*args):return self.actual.verify_callback(self.service._entry,*args)
    def barrier_applies(self,entry,*args):return self.actual.barrier_applies(self.service._entry,*args)
    def overlap(self,entry,*args):return self.actual.overlap(self.service._entry,*args)


class _ControlledReader:
    def __init__(self,service):self.__service=service
    def __call__(self,key,type_name=None):return self.__service.storage.read_artifact(key,type_name)
    def row(self,kind,key):
        if kind not in ('memory_revisions','cognition_beliefs','cognition_concepts','cognition_belief_revisions','cognition_concept_revisions','tl_content','tl_content_revision'):raise Forbidden('controlled domain row kind unavailable')
        self.__service._check_time();self.__service._meter['scan']['remaining']-=1
        if self.__service._meter['scan']['remaining']<0:raise _NotReady('controlled row scan exhausted')
        # Logical UTF-8 field bytes, not physical SQLite page/cache traffic.
        columns=sorted(self.__service.s.columns[kind]);expression='+'.join('coalesce(length(CAST("'+column+'" AS BLOB)),0)' for column in columns)
        value=self.__service.s.db.execute('SELECT '+expression+' FROM '+kind+' WHERE instance_id=? AND id=?',(self.__service.s.instance_id,key)).fetchone()
        if value is None:raise ContractError('controlled domain row unavailable')
        self.__service._charge_bytes(value[0]);row=self.__service.s.row(kind,key);self.__service._check_time();return row


class _MeteredStore(ToolLearningStore):
    def __init__(self,store,service):super().__init__(store);self.service=service
    def read_artifact(self,key,type_name=None):
        self.service._check_time()
        size=self.service.s.row('artifacts',key)['size'];self.service._charge_bytes(size)
        try:value=super().read_artifact(key,type_name)
        except BaseException:
            self.service._meter['usage_unknown']=True
            raise
        self.service._check_time();return value


class _MeteredEligibility(ToolLearningEligibility):
    def __init__(self,store,authority,service):super().__init__(store,authority);self.service=service
    def _check(self,entry,principal,token,scope,purpose,recipient,stage,scan_budget=None):
        shared=self.service._meter['scan'] if self.service._meter is not None else scan_budget
        return super()._check(entry,principal,token,scope,purpose,recipient,stage,scan_budget=shared)


class _NotReady(ContractError):pass
class _Hidden(ContractError):pass


class ToolLearningRecall:
    def __init__(self,store,authority=None,eligibility_authority=None,clock=utc,monotonic=time.monotonic):
        self.s=store;self.authority=RecallAuthority() if authority is None else authority
        if not isinstance(self.authority,RecallAuthority):raise ContractError('trusted RecallAuthority required')
        actual=EligibilityAuthority() if eligibility_authority is None else eligibility_authority
        if not isinstance(actual,EligibilityAuthority):raise ContractError('trusted eligibility authority required')
        self._entry=None;self._meter=None;self._scope_cache={};self._group_cache={};self._body_cache={};self.reader=_ControlledReader(self);self.clock=clock;self.monotonic=monotonic;self.storage=_MeteredStore(store,self);self.eligibility=_MeteredEligibility(store,_Eligibility(self,actual),self);self.eligibility.artifacts=_MeteredStore(store,self);self.budget=ToolLearningBudget(store);self.budget.artifacts=_MeteredStore(store,self)
    def _attest(self,value):
        if value is not None:raise Forbidden('trusted authority must attest, not return a boolean')
    @contextmanager
    def _bound(self,entry):
        if self._entry is not None:raise Conflict('recall entry reentry is not allowed')
        self._entry=entry
        try:yield
        finally:self._entry=None
    def _guard(self,entry,request,stage):
        self._attest(self.authority.verify_request(entry,deepcopy(request),stage))
        if request['instance_id']!=self.s.instance_id:raise Forbidden('recall instance differs')
        for key in ('actor','recipient','authorization'):self.storage.validate_ref(request['principal'][key])
        if request['principal']['module']!='M04':raise Forbidden('actual M04 recall service required')
        audit=request['entry']=='controller_audit'
        if audit:
            if request['principal']['actor']['id']!=self.s.row('identity_instances',self.s.instance_id)['controller_ref']:raise Forbidden('actual current controller required for read-only audit')
            self._attest(self.authority.verify_audit(entry,deepcopy(request),stage))
        else:
            self.s.assert_execution_allowed()
            if request['control']['cancelled']:raise Forbidden('recall cancelled')
            if request['activity_ref']['status']!='known' or request['context_ref']['status']!='known':raise Forbidden('execution requires real activity and context')
            self.storage.validate_ref(request['activity_ref']['value'],expected_kind='activities');self.storage.validate_ref(request['context_ref']['value'],expected_kind='context_snapshots')
            activity=self.s.row('activities',request['activity_ref']['value']['id']);context=self.s.row('context_snapshots',request['context_ref']['value']['id'])
            if context['activity_id']!=activity['id']:raise Forbidden('context belongs to another activity')
            if activity['cancel_requested_at'] or activity['state']=='cancelled':raise Forbidden('recall activity cancelled')
            account=self.s.row('activity_budget_accounts',request['budget']['account_ref']['id'])
            if account['activity_id']!=activity['id']:raise Forbidden('recall cannot replace original activity account')
        if self.clock()>=request['budget']['deadline']:raise Forbidden('recall deadline exhausted')
        return audit
    def _limits(self,entry,request,audit,run=None,reservation_slot=None):
        budget=request['budget'];limits={'scan':min(budget['max_scan'],1024),'items':min(budget['max_items'],128),'bytes':min(budget['max_bytes'],1048576),'tokens':budget['max_input_tokens']}
        if not audit:
            activity=self.s.row('activities',request['activity_ref']['value']['id']);account=self.s.row('activity_budget_accounts',budget['account_ref']['id'])
            work=self.s.db.execute('SELECT id FROM tl_work WHERE instance_id=? AND learning_activity_id=?',(self.s.instance_id,activity['id'])).fetchone()
            owner=work[0] if work else activity['id'];accounting=self.budget
            if work is None:
                from digital_life.application.learning.activity_budget import ActivityResourceBudget
                accounting=ActivityResourceBudget(self.s,clock=self.clock);accounting.artifacts=self.storage
            snapshot=accounting.check_work(owner,budget)
            reasons=[x for x in snapshot['block_reasons'] if x not in ('attempts_exhausted','work_waiting','work_blocked','work_failed','work_stopped','work_completed','work_no_change','work_rejected')]
            if reasons:raise Forbidden(','.join(reasons))
            reservation_slot=self.authority.execution_reservation(entry,deepcopy(request),deepcopy(run)) if reservation_slot is None else reservation_slot;t.slot(reservation_slot,lambda value:c.validate('ID',value))
            if reservation_slot['status']!='known':raise Forbidden('execution requires an actual entered reservation, not a reported cap')
            loaded=accounting._load(owner);reservation=loaded[3]['ledger']['reservations'].get(reservation_slot['value'])
            if reservation is None or reservation['kind']!='retrieval' or reservation['state']!='reserved' or reservation['entry'] is None or not same_ref(reservation['operation'],run):raise Forbidden('read reservation is not this entered original run')
            accounting._operation(run,'retrieval',activity['id'])
            for name in ('scan','items','bytes'):limits[name]=min(limits[name],reservation['reserved'][name])
            # Retrieval does not spend model tokens; this only bounds packaging.
            limits['tokens']=min(limits['tokens'],snapshot['remaining']['input_tokens'],snapshot['remaining']['tokens'])
            self._meter['max_seconds']=min(self._meter['max_seconds'],reservation['reserved']['elapsed_ms']/1000)
            context={'activity':dict(activity),'account':dict(account),'snapshot':snapshot,'reservation':deepcopy(reservation)}
            read={'occurrence_id':identifier(),'request_fingerprint':c.fingerprint(request),'account_ref':deepcopy(budget['account_ref']),'activity_ref':deepcopy(request['activity_ref']),'run':deepcopy(run),'reservation_id':reservation['id'],'limits':deepcopy(limits),'deadline':budget['deadline']}
            self._attest(self.authority.verify_execution_accounting(entry,deepcopy(request),context,read,'recall'))
        return limits
    def _check_time(self):
        if self._meter is None:raise Forbidden('a bounded recall read context is required')
        if self.clock()>=self._meter['deadline'] or self.monotonic()-self._meter['started']>=self._meter['max_seconds']:raise _NotReady('bounded recall deadline exhausted')
    def _charge_bytes(self,size):
        self._check_time()
        if self._meter['read_bytes']+size>self._meter['byte_limit']:raise _NotReady('bounded recall byte budget exhausted')
        self._meter['read_bytes']+=size
    def _read(self,key,meter,limit,type_name=None):return self.storage.read_artifact(key,type_name)
    def _qualified(self,entry,request,token,scope,stage):
        principal=request['principal'];audit=request['entry']=='controller_audit'
        if not audit:return self.eligibility._check('tl.recall.execution',principal,token,scope,principal['purpose'],principal['recipient'],stage,scan_budget=self._meter['scan'])
        # Separate read-only source check: stopped/WAKE_DISABLED is deliberately
        # not ordinary execution permission, and never removes source barriers.
        self._attest(self.authority.verify_audit(entry,deepcopy(request),stage))
        scan=self._meter['scan'];self.eligibility.validate_token('tl.recall.audit',principal,token,stage)
        paths=self.eligibility._upstream(token,scope,scan)
        for key,dep_scope,expected,path in paths:
            selected=token if expected is None else expected;source=ref(self.s,key)
            if 'delete' not in path:
                self.eligibility.validate_token('tl.recall.audit',principal,selected,stage)
                self._attest(self.eligibility.authority.verify('tl.recall.audit',deepcopy(principal),deepcopy(selected),deepcopy(dep_scope),principal['purpose'],deepcopy(principal['recipient']),stage))
                if self.eligibility.current_epoch(source,dep_scope)!=selected['epoch']:raise Conflict('audit source epoch is stale')
            rows=self.s.db.execute("SELECT b.*,ch.payload_artifact_id FROM tl_barrier b JOIN tl_change ch ON ch.instance_id=b.instance_id AND ch.id=b.change_id WHERE b.instance_id=? AND b.source_ref_id=? AND b.state='active' ORDER BY b.id LIMIT ?",(self.s.instance_id,key,scan['remaining']+1)).fetchall()
            scan['remaining']-=len(rows)
            if scan['remaining']<0:raise Forbidden('audit barrier scan limit exceeded')
            for row in rows:
                if 'delete' in path and row['kind']!='erase':continue
                payload=self.storage.read_artifact(row['payload_artifact_id'])
                if payload['purposes'] and principal['purpose'] not in payload['purposes']:continue
                applies=self.eligibility.authority.barrier_applies('tl.recall.audit',deepcopy(principal),dict(row,dependency_path=list(path)),deepcopy(payload),deepcopy(dep_scope),principal['purpose'],deepcopy(principal['recipient']))
                if applies is not None and type(applies) is not bool:raise ContractError('invalid audit barrier applicability')
                if applies is not False and self.eligibility.overlaps('tl.recall.audit',principal,self.storage.read_artifact(row['scope_artifact_id'],'Scope'),dep_scope):raise Forbidden('audit source barrier')
        self._check_time();return True
    def _discover(self,entry,request,limits):
        if request['exact_refs']:return deepcopy(request['exact_refs'][:limits['scan']+1]),False
        try:
            values=self.authority.index_candidates(entry,deepcopy(request),limits['scan'])
            if not isinstance(values,list) or len(values)>limits['scan']+1:raise ContractError('index must return a bounded Ref list')
            for value in values:c.validate('Ref',value)
            return deepcopy(values),False
        except (NotImplementedError,OSError):
            if request['index_fallback']!='bounded_primary':raise _NotReady('index unavailable without authorized fallback')
            self._attest(self.authority.verify_fallback(entry,deepcopy(request)))
        values=[]
        if set(request['allowed_kinds']) & {'accepted_content','history'}:
            states="('ready')" if request['version_mode']=='current' else "('ready','superseded')"
            for row in self.s.db.execute('SELECT id FROM tl_representation WHERE instance_id=? AND state IN '+states+' ORDER BY recorded_at DESC,id LIMIT ?',(self.s.instance_id,limits['scan']+1)):values.append(ref(self.s,row[0]))
        if len(values)<=limits['scan'] and set(request['allowed_kinds']) & {'episode','source_evidence','candidate','shadow_statistic'}:
            remaining=limits['scan']+1-len(values)
            for row in self.s.db.execute("SELECT r.id FROM memory_revisions r JOIN memory_items m ON m.instance_id=r.instance_id AND m.id=r.memory_id WHERE r.instance_id=? AND m.state='active' AND (?<>'current' OR m.current_revision_id=r.id) ORDER BY r.recorded_at DESC,r.id LIMIT ?",(self.s.instance_id,request['version_mode'],remaining)):values.append(ref(self.s,row[0]))
        return values,True
    def _base(self,request,kind,body,scope,evidence,origin,processing,values,limitations):
        return {'id':identifier(),'kind':kind,'memory_ref':slot(),'memory_revision':slot(),'representation_ref':slot(),'representation_revision':slot(),'content_ref':slot(),'content_revision':slot(),'decision_ref':slot(),'body':body,'body_digest':{'algorithm':'sha256','hex':sha(body.encode())},'origin_kind':origin,'processing':processing,'source_refs':deepcopy(evidence),'scope':deepcopy(scope),'limitations':deepcopy(limitations),'value_slots':deepcopy(values),'usage_state':'current' if kind in ('accepted_content','episode','source_evidence') else 'candidate' if kind in ('candidate','shadow_statistic') else 'historical','group_ready':slot(),'relations':[],'selection':{'method':{'name':'tl-bounded-lexical','version':'1','request_ref':slot(),'model_config_ref':slot()},'score':slot(),'reason':'explicit reference or scoped lexical match'},'control':deepcopy(request['control']),'dependencies':[]}
    def _group_qualified(self,entry,request,group_id,meter,limits):
        dependencies=[]
        group=self.s.row('tl_group',group_id)
        if group['state']!='ready':raise _NotReady('fixed group not ready')
        if group['members_artifact_id'] not in self._group_cache:self._group_cache[group['members_artifact_id']]=self._read(group['members_artifact_id'],meter,limits['bytes'])
        body=self._group_cache[group['members_artifact_id']];t.obj(body,('contract','intent','members'))
        if body['contract']!='TL-C1-GROUP-MEMBERS-1' or not 1<=len(body['members'])<=32:raise ContractError('fixed group material invalid')
        for member in body['members']:
            self._meter['scan']['remaining']-=1
            if self._meter['scan']['remaining']<0:raise _NotReady('group scan budget exhausted')
            handoff=self.s.row('tl_handoff',member['handoff_id']);revision=self.s.row('tl_content_revision',member['content_revision_id']);content=self.s.row('tl_content',revision['content_id'])
            if handoff['group_id']!=group_id or handoff['state']!='published' or handoff['content_revision_id']!=revision['id'] or content['head_revision_id']!=revision['id'] or revision['content_id']!=member['content']['id'] or revision['revision_no']!=member['revision_no'] or revision['product_id']!=member['proposal']['id']:raise _NotReady('fixed group current mapping not ready')
            rep=self.s.row('tl_representation',handoff['representation_id']);series=self.s.row('tl_representation_head',rep['series_id'])
            if rep['state']!='ready' or rep['content_revision_id']!=revision['id'] or series['representation_id']!=rep['id'] or rep['group_id']!=group_id or rep['format_version']!=member['format_version']:raise _NotReady('fixed group representation not ready')
            self._attest(self.authority.verify_candidate_access(entry,deepcopy(request),ref(self.s,rep['id']),'group_member'))
            key=(series['id'],rep['representation_no'])
            if key not in self._scope_cache:self._scope_cache[key]=deepcopy(self._read(rep['payload_artifact_id'],meter,limits['bytes'],'Representation')['scope'])
            scope=self._scope_cache[key];token={'object':ref(self.s,series['id']),'revision':rep['representation_no'],'epoch':self.eligibility.current_epoch(ref(self.s,series['id']),scope)}
            self._scope_cache[(token['object']['id'],token['revision'])]=deepcopy(scope)
            self._qualified(entry,request,token,scope,'group_member')
            dependencies.append({'target':deepcopy(token['object']),'relation':'group','expected':deepcopy(token),'consumer_purpose':request['principal']['purpose']})
        self._check_time();return dependencies

    def _representation(self,entry,request,candidate,meter,limits):
        kind=candidate['kind'];row=None
        if kind=='tl_representation':
            row=self.s.row(kind,candidate['id'])
            if request['version_mode']=='as_of' and not request['exact_refs']:
                row=self.s.db.execute('SELECT * FROM tl_representation WHERE instance_id=? AND series_id=? AND recorded_at<=? ORDER BY representation_no DESC LIMIT 1',(self.s.instance_id,row['series_id'],request['as_of']['value'])).fetchone()
        elif kind=='tl_representation_head':
            series=self.s.row(kind,candidate['id'])
            if candidate['revision']['status']=='known':row=self.s.db.execute('SELECT * FROM tl_representation WHERE instance_id=? AND series_id=? AND representation_no=?',(self.s.instance_id,series['id'],candidate['revision']['value'])).fetchone()
            elif request['version_mode']=='as_of':row=self.s.db.execute('SELECT * FROM tl_representation WHERE instance_id=? AND series_id=? AND recorded_at<=? ORDER BY representation_no DESC LIMIT 1',(self.s.instance_id,series['id'],request['as_of']['value'])).fetchone()
            else:row=self.s.row('tl_representation',series['representation_id'])
        elif kind in ('tl_content','tl_content_revision'):
            if kind=='tl_content':
                content=self.s.row(kind,candidate['id']);revision_id=content['head_revision_id']
                if candidate['revision']['status']=='known':
                    revision=self.s.db.execute('SELECT id FROM tl_content_revision WHERE instance_id=? AND content_id=? AND revision_no=?',(self.s.instance_id,content['id'],candidate['revision']['value'])).fetchone();revision_id=revision[0] if revision else None
            else:revision_id=candidate['id']
            if kind=='tl_content' and request['version_mode']=='as_of' and candidate['revision']['status']!='known':
                row=self.s.db.execute("SELECT p.* FROM tl_representation p JOIN tl_content_revision r ON r.instance_id=p.instance_id AND r.id=p.content_revision_id JOIN tl_decision d ON d.instance_id=r.instance_id AND d.id=r.decision_id WHERE p.instance_id=? AND r.content_id=? AND p.recorded_at<=? AND r.recorded_at<=? AND d.created_at<=? AND p.state IN ('ready','superseded') ORDER BY p.recorded_at DESC,p.representation_no DESC LIMIT 1",(self.s.instance_id,content['id'],request['as_of']['value'],request['as_of']['value'],request['as_of']['value'])).fetchone()
            elif revision_id:row=self.s.db.execute("SELECT * FROM tl_representation WHERE instance_id=? AND content_revision_id=? AND state IN ('ready','superseded') AND (?<>'as_of' OR recorded_at<=?) ORDER BY representation_no DESC LIMIT 1",(self.s.instance_id,revision_id,request['version_mode'],request['as_of']['value'])).fetchone()
        if row is None:raise _NotReady('fixed representation not ready')
        row=dict(row);content_revision=self.s.row('tl_content_revision',row['content_revision_id']);content=self.s.row('tl_content',content_revision['content_id']);decision=self.s.row('tl_decision',row['decision_id']);series=self.s.row('tl_representation_head',row['series_id'])
        current=content['head_revision_id']==content_revision['id'] and series['representation_id']==row['id'] and row['state']=='ready'
        if request['version_mode']=='current' and not current:raise _NotReady('current representation not ready')
        if row['state']=='withdrawn' or content_revision['status']!='accepted' or decision['operation']!='accept' or decision['content_revision_id']!=content_revision['id'] or content_revision['decision_id']!=decision['id']:raise _NotReady('accepted representation mapping invalid')
        if request['version_mode']=='as_of' and max(row['recorded_at'],content_revision['recorded_at'],decision['created_at'])>request['as_of']['value']:raise _NotReady('representation outside requested time')
        ready=True;group_dependencies=[]
        if row['group_id']:
            group_dependencies=self._group_qualified(entry,request,row['group_id'],meter,limits)
        value=self._read(row['payload_artifact_id'],meter,limits['bytes'],'Representation');scope=value['scope']
        if value['id']!=row['id'] or value['content_ref']['id']!=content['id'] or value['content_revision']['revision']!=content_revision['revision_no'] or value['series_ref']['id']!=series['id'] or value['representation_no']!=row['representation_no'] or value['decision_ref']['id']!=decision['id'] or value['body_artifact']['id']!=row['body_artifact_id'] or value['body_digest']['hex']!=row['body_digest']:raise ContractError('representation immutable row projection differs')
        if self.authority.scope_matches(entry,deepcopy(request),deepcopy(scope)) is not True:raise _NotReady('scope compatibility unknown')
        token={'object':ref(self.s,series['id']),'revision':row['representation_no'],'epoch':self.eligibility.current_epoch(ref(self.s,series['id']),scope)}
        self._scope_cache[(token['object']['id'],token['revision'])]=deepcopy(scope)
        self._qualified(entry,request,token,scope,'recall_read')
        raw=self._read(row['body_artifact_id'],meter,limits['bytes'])
        if not isinstance(raw,bytes) or sha(raw)!=row['body_digest']:raise ContractError('representation body digest differs')
        self._body_cache[row['body_artifact_id']]=raw
        body=raw.decode('utf-8');result_kind='accepted_content' if current else 'history'
        if result_kind not in request['allowed_kinds']:raise _NotReady('requested use excludes this representation')
        item=self._base(request,result_kind,body,scope,value['source_refs'],value['source_refs'][0]['source_kind'],'transform',[claim['value'] for claim in value['claims']],value['limitations'])
        item.update(representation_ref=slot(ref(self.s,row['id'])),representation_revision=slot(token),content_ref=slot(ref(self.s,content['id'])),content_revision=slot(deepcopy(value['content_revision'])),decision_ref=slot(ref(self.s,decision['id'])),group_ready=slot(ready) if row['group_id'] else slot(),relations=deepcopy(value['dependencies'])+group_dependencies,dependencies=[{'target':deepcopy(token['object']),'relation':'read','expected':deepcopy(token),'consumer_purpose':request['principal']['purpose']}]+[dict(deepcopy(d),relation='read') for d in group_dependencies if d['target']['id']!=token['object']['id']])
        return item,ref(self.s,row['id'])
    def _evidence_dependencies(self,entry,request,evidences,scope):
        dependencies=[];relations=[]
        if len(evidences)>128 or sum(len(x['access_dependencies']) for x in evidences)>128:raise _NotReady('source dependency local bounds exceeded')
        for evidence in evidences:
            c.validate('EvidenceRef',evidence);token=self.authority.source_token(entry,deepcopy(request),deepcopy(evidence));c.validate('VersionToken',token)
            if not same_ref(token['object'],evidence['source']):raise ContractError('source resolver changed identity')
            self._qualified(entry,request,token,scope,'recall_original_source')
            dependency={'target':deepcopy(token['object']),'relation':'read','expected':deepcopy(token),'consumer_purpose':request['principal']['purpose']}
            if dependency not in dependencies:dependencies.append(dependency)
            for inherited in evidence['access_dependencies']:
                inherited=deepcopy(inherited);inherited['consumer_purpose']=request['principal']['purpose']
                if inherited['relation']=='delete':self.eligibility.validate_token('tl.recall.source',request['principal'],inherited['expected'],'delete_retention')
                else:self._qualified(entry,request,inherited['expected'],scope,'recall_access_source');dependencies.append(inherited)
                relations.append(inherited)
        return dependencies,relations

    def _legacy(self,entry,request,candidate,meter,limits):
        if candidate['kind'] in ('memory_items','memory_revisions'):
            owner=candidate['id'] if candidate['kind']=='memory_items' else self.s.db.execute('SELECT memory_id FROM memory_revisions WHERE instance_id=? AND id=?',(self.s.instance_id,candidate['id'])).fetchone()[0]
            memory=self.s.row('memory_items',owner)
            if memory['state']!='active':raise Forbidden('memory unavailable')
            selected=memory['current_revision_id'] if candidate['kind']=='memory_items' else candidate['id']
            if candidate['kind']=='memory_items' and candidate['revision']['status']=='known':
                r=self.s.db.execute('SELECT id FROM memory_revisions WHERE instance_id=? AND memory_id=? AND revision_no=?',(self.s.instance_id,owner,candidate['revision']['value'])).fetchone();selected=r[0] if r else None
            elif request['version_mode']=='as_of' and candidate['revision']['status']!='known':
                r=self.s.db.execute('SELECT id FROM memory_revisions WHERE instance_id=? AND memory_id=? AND recorded_at<=? ORDER BY revision_no DESC LIMIT 1',(self.s.instance_id,owner,request['as_of']['value'])).fetchone();selected=r[0] if r else None
            if selected is None:raise _NotReady('memory version unavailable')
            meta=self.s.db.execute('SELECT memory_id,revision_no,recorded_at,length(CAST(content AS BLOB)) AS bytes FROM memory_revisions WHERE instance_id=? AND id=?',(self.s.instance_id,selected)).fetchone()
            if request['version_mode']=='current' and selected!=memory['current_revision_id']:raise _NotReady('not current memory version')
            if request['version_mode']=='as_of' and meta['recorded_at']>request['as_of']['value']:raise _NotReady('memory outside requested time')
            row=self.reader.row('memory_revisions',selected)
            material=self.authority.legacy_material(entry,deepcopy(request),ref(self.s,selected),dict(row));self._check_time()
            t.obj(material,('kind','scope','source_refs','origin_kind','processing','values','limitations'))
            if len(material['source_refs'])>128 or len(material['values'])>128:raise _NotReady('legacy material exceeds local bounds')
            if material['kind'] not in request['allowed_kinds'] or material['kind']=='accepted_content':raise _NotReady('legacy material cannot substitute accepted TL content')
            if self.authority.scope_matches(entry,deepcopy(request),deepcopy(material['scope'])) is not True:raise _NotReady('legacy scope not established')
            token={'object':ref(self.s,owner),'revision':row['revision_no'],'epoch':self.eligibility.current_epoch(ref(self.s,owner),material['scope'])};self._qualified(entry,request,token,material['scope'],'legacy_recall')
            source_dependencies,relations=self._evidence_dependencies(entry,request,material['source_refs'],material['scope'])
            item=self._base(request,material['kind'],row['content'],material['scope'],material['source_refs'],material['origin_kind'],material['processing'],material['values'],material['limitations'])
            if selected!=memory['current_revision_id']:item['usage_state']='historical'
            item.update(memory_ref=slot(ref(self.s,owner)),memory_revision=slot(token),relations=relations,dependencies=[{'target':deepcopy(token['object']),'relation':'read','expected':deepcopy(token),'consumer_purpose':request['principal']['purpose']}]+source_dependencies)
            return item,ref(self.s,selected)
        if request['entry']!='controller_audit':raise _NotReady('no traceable target mapping for execution')
        # Authorized temporary projection only; no wrapper or false persistence.
        row=self.reader.row(candidate['kind'],candidate['id']);material=self.authority.legacy_material(entry,deepcopy(request),deepcopy(candidate),dict(row));self._check_time()
        c.validate('RecallItem',material)
        if material['kind'] not in ('candidate','history','shadow_statistic','source_evidence') or material['kind'] not in request['allowed_kinds'] :raise Forbidden('audit-only source cannot become a current fact')
        if self.authority.scope_matches(entry,deepcopy(request),deepcopy(material['scope'])) is not True:raise _NotReady('audit material scope unknown')
        self._charge_bytes(len(dumps(material).encode()))
        token=self.authority.candidate_token(entry,deepcopy(request),deepcopy(candidate),dict(row));c.validate('VersionToken',token)
        if candidate['kind']=='tl_content_revision':
            if token['object']['kind']!='tl_content' or token['object']['id']!=row['content_id'] or token['revision']!=row['revision_no']:raise Conflict('audit candidate token does not bind its real revision owner')
        elif not same_ref(token['object'],candidate):raise Conflict('audit candidate token changed object')
        if candidate['revision']['status']=='known' and token['revision']!=candidate['revision']['value']:raise Conflict('audit candidate requested version differs')
        for name in ('memory_ref','representation_ref','content_ref','decision_ref'):
            if material[name]['status']=='known':self.storage.validate_ref(material[name]['value'])
        self._qualified(entry,request,token,material['scope'],'audit_candidate')
        for dependency in material['dependencies']:self._qualified(entry,request,dependency['expected'],material['scope'],'audit_material')
        source_dependencies,relations=self._evidence_dependencies(entry,request,material['source_refs'],material['scope'])
        material=deepcopy(material);material['dependencies'] += [{'target':deepcopy(token['object']),'relation':'read','expected':deepcopy(token),'consumer_purpose':request['principal']['purpose']}]+source_dependencies;material['relations']+=relations
        if material['control']!=request['control']:raise Conflict('audit material control differs from request')
        return material,None
    def _material(self,entry,request,candidate,meter,limits):
        self._attest(self.authority.verify_candidate_access(entry,deepcopy(request),deepcopy(candidate),'candidate'))
        try:self.storage.validate_ref(candidate)
        except (ContractError,Conflict,Forbidden) as exc:raise _Hidden('candidate not publicly available') from exc
        self._check_time()
        if self._meter['material_items']>=self._meter['item_limit']:raise _NotReady('candidate material item budget exhausted')
        self._meter['material_items']+=1
        if candidate['kind'] in ('tl_representation','tl_representation_head','tl_content','tl_content_revision'):
            try:return self._representation(entry,request,candidate,meter,limits)
            except _NotReady:
                if request['entry']=='controller_audit' and candidate['kind'] in ('tl_content','tl_content_revision') and set(request['allowed_kinds']) & {'candidate','history','shadow_statistic'}:return self._legacy(entry,request,candidate,meter,limits)
                raise
        if candidate['kind'] not in ('memory_items','memory_revisions','cognition_beliefs','cognition_concepts'):raise _NotReady('unsupported source type')
        return self._legacy(entry,request,candidate,meter,limits)
    @staticmethod
    def _score(query,item,exact):
        if exact:return 1.0
        def terms(value):
            words=set(re.findall(r'[a-z0-9_]+',value.casefold()))
            for part in re.findall(r'[\u4e00-\u9fff]+',value):words.update(part[n:n+2] for n in range(max(1,len(part)-1)))
            return words
        wanted=terms(query);matched=wanted & terms(item['body']);return len(matched)/len(wanted) if wanted else 0.0
    def _initialize_meter(self,request):
        from datetime import datetime
        seconds=max(0,(datetime.fromisoformat(request['budget']['deadline'].replace('Z','+00:00'))-datetime.fromisoformat(self.clock().replace('Z','+00:00'))).total_seconds())
        self._scope_cache={};self._group_cache={};self._body_cache={}
        self._meter={'material_items':0,'item_limit':min(request['budget']['max_items'],128),'usage_unknown':False,'read_bytes':0,'byte_limit':min(request['budget']['max_bytes'],1048576),'scan':{'remaining':min(request['budget']['max_scan'],1024)},'started':self.monotonic(),'max_seconds':seconds,'deadline':request['budget']['deadline']}
    def begin(self,entry,request):
        """Fixed execution trace admission; IM11 reserves its real run before reads."""
        c.validate('RecallRequest',request);request=c.loads(dumps(request))
        if request['entry']!='execution':raise Forbidden('controller audit never creates a retrieval run')
        if self.s.db.in_transaction:raise Conflict('trace admission requires an independent transaction')
        with self._bound(entry),dispatch_gate(self.s.root),self.s.tx():
            self._initialize_meter(request)
            try:
                with self.authority.read_boundary(entry,deepcopy(request),self.reader):
                    self._guard(entry,request,'begin');self._attest(self.authority.verify_trace(entry,deepcopy(request),None,'begin'))
                    existing=self.s.db.execute("SELECT payload_artifact_id,payload_object_id,payload_hash FROM runtime_events WHERE instance_id=? AND source='tl.recall.begin' AND source_event_id=?",(self.s.instance_id,request['request_id'])).fetchone()
                    if existing:
                        material=self.storage.read_artifact(existing['payload_artifact_id'])
                        if material['request_fingerprint']!=c.fingerprint(request):raise Conflict('retrieval request id changed semantics')
                        return material['run']
                    run=self.s.insert('memory_retrieval_runs',activity_id=request['activity_ref']['value']['id'],context_id=request['context_ref']['value']['id'],query=request['query'],retriever_version='tl-purpose-recall-1')
                    result=ref(self.s,run);event=self.s.event('recall.begin',payload={'contract':'TL-RECALL-BEGIN-1','request_fingerprint':c.fingerprint(request),'run':result},source='tl.recall.begin',key=request['request_id'],activity=request['activity_ref']['value']['id'])
                    # Actual source-derived query and its fingerprint become
                    # reachable in the same creation transaction, before F1 can
                    # interleave. No model/input permission is granted here.
                    for source in request['control']['source_epochs']:
                        for consumer in (result,ref(self.s,event),ref(self.s,self.s.row('runtime_events',event)['payload_artifact_id'])):
                            for relation in ('read','delete'):
                                dependency={'target':deepcopy(source['object']),'relation':relation,'expected':deepcopy(source),'consumer_purpose':request['principal']['purpose']}
                                self._persist_dependency(consumer,dependency,request['target_scope'],'/query')
                    self._guard(entry,request,'begin_commit');return result
            finally:self._meter=None;self._scope_cache={};self._group_cache={};self._body_cache={};self._body_cache={}
    def _run(self,request):
        row=self.s.db.execute("SELECT payload_artifact_id,payload_object_id,payload_hash FROM runtime_events WHERE instance_id=? AND source='tl.recall.begin' AND source_event_id=?",(self.s.instance_id,request['request_id'])).fetchone()
        if row is None:raise Forbidden('execution requires an admitted real retrieval run and original-account opportunity')
        material=self.storage.read_artifact(row['payload_artifact_id'])
        if material['request_fingerprint']!=c.fingerprint(request):raise Conflict('retrieval request id changed semantics')
        self.storage.validate_ref(material['run'],expected_kind='memory_retrieval_runs');run=self.s.row('memory_retrieval_runs',material['run']['id'])
        if run['activity_id']!=request['activity_ref']['value']['id'] or run['context_id']!=request['context_ref']['value']['id'] or run['query']!=request['query']:raise Conflict('real retrieval run binding differs')
        return material['run']
    def recall(self,entry,request):
        c.validate('RecallRequest',request);request=c.loads(dumps(request))
        if len(request['query'])>4096 or len(request['exact_refs'])>128 or len(dumps(request['target_scope']).encode())>65536:raise ContractError('recall request exceeds finite local bounds')
        if self.s.db.in_transaction:raise Conflict('recall requires its own gate and transaction')
        audit=request['entry']=='controller_audit';previous_readonly=self.s.db.execute('PRAGMA query_only').fetchone()[0]
        with self._bound(entry),dispatch_gate(self.s.root):
            if audit:self.s.db.execute('PRAGMA query_only=ON')
            self.s.db.execute('BEGIN' if audit else 'BEGIN IMMEDIATE');self._initialize_meter(request)
            try:
                with self.authority.read_boundary(entry,deepcopy(request),self.reader):
                    self._guard(entry,request,'read');run=slot() if audit else slot(self._run(request));reservation_hint=None
                    if not audit:
                        reservation_hint=self.authority.execution_reservation(entry,deepcopy(request),deepcopy(run['value']));t.slot(reservation_hint,lambda value:c.validate('ID',value))
                        if reservation_hint['status']!='known':raise Forbidden('execution requires actual entered reservation')
                        entered=self.s.db.execute("SELECT 1 FROM runtime_events WHERE instance_id=? AND source='tl.recall.read_entry' AND source_event_id=?",(self.s.instance_id,reservation_hint['value'])).fetchone()
                        if entered:raise Conflict('read reservation has already entered once; settle/reconcile and obtain a new opportunity')
                    limits=self._limits(entry,request,audit,None if audit else run['value'],reservation_hint);self._meter['byte_limit']=limits['bytes'];self._meter['scan']['remaining']=limits['scan'];self._meter['scan_limit']=limits['scan'];self._meter['item_limit']=limits['items']
                    if not audit:
                        self._attest(self.authority.verify_trace(entry,deepcopy(request),{'run':run['value'],'reservation_id':reservation_hint['value']},'read_entry'))
                        self._local_control(request)
                        self.s.event('recall.read_entry',payload={'contract':'TL-RECALL-READ-ENTRY-1','request_id':request['request_id'],'run':run['value'],'reservation_id':reservation_hint['value']},source='tl.recall.read_entry',key=reservation_hint['value'],activity=request['activity_ref']['value']['id'])
                        # The actual local read opportunity survives a later query
                        # rollback. Its entered slice can never be reused as free IO.
                        self.s.db.execute('COMMIT');self.s.db.execute('BEGIN IMMEDIATE');self._guard(entry,request,'entered_read');self._check_time()
                    prior=None if audit else self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND source='tl.recall.result' AND source_event_id=?",(self.s.instance_id,request['request_id'])).fetchone()
                    if prior:
                        cached={'object':ref(self.s,prior[0]),'revision':0,'epoch':self.eligibility.current_epoch(ref(self.s,prior[0]),request['target_scope'])}
                        self._qualified(entry,request,cached,request['target_scope'],'replay_material')
                        stored=self.storage.read_artifact(prior[0]);result=stored['result'];c.validate('RecallResult',result)
                        count=len(result['items'])
                        if count>self._meter['item_limit']:raise _NotReady('replay material item budget exhausted')
                        self._meter['material_items']=count
                        if stored['request_fingerprint']!=c.fingerprint(request):raise Conflict('retrieval replay changed request')
                        self._final_items(entry,request,result['items'],'replay');self.s.db.execute('COMMIT');return result
                    candidates,fallback=self._discover(entry,request,limits);items=[];targets={};seen=set();partial=len(candidates)>limits['scan'];gaps=[];not_ready=False;unavailable=False;hidden=False;output_bytes=0;tokens=0;output_truncated=False
                    for candidate in candidates:
                        if self._meter['scan']['remaining']<=0:partial=True;break
                        self._meter['scan']['remaining']-=1
                        try:
                            self._check_time();item,target=self._material(entry,request,candidate,self._meter,limits);c.validate('RecallItem',item);self._check_time()
                            identity=item['representation_revision']['value']['object']['id'] if item['representation_revision']['status']=='known' else item['memory_ref']['value']['id'] if item['memory_ref']['status']=='known' else candidate['id']
                            if identity in seen:continue
                            score=self._score(request['query'],item,bool(request['exact_refs']))
                            if score<=0:continue
                            item['selection']['score']=slot(score);self._attest(self.authority.verify_retention(entry,deepcopy(request),deepcopy(item),'read'));self._check_time()
                            packet=dumps(item);cost=self.authority.count_tokens(entry,deepcopy(request),packet);t.integer(cost);self._check_time();size=len(packet.encode())
                            if output_bytes+size>limits['bytes'] or tokens+cost>limits['tokens'] or len(items)>=limits['items']:partial=True;output_truncated=True;continue
                            output_bytes+=size;tokens+=cost;seen.add(identity);items.append(item);targets[item['id']]=target
                        except (_Hidden,Forbidden,Conflict):
                            hidden=True
                            if self._meter['scan']['remaining']<0:partial=True
                        except _NotReady as exc:
                            if any(word in str(exc) for word in ('budget','bounded','exhausted')):raise
                            not_ready=True;partial=True
                        except (ContractError,OSError,UnicodeError):unavailable=True;partial=True
                    items.sort(key=lambda x:(-x['selection']['score']['value'],x['id']))
                    completion='unavailable' if unavailable and not items else 'not_ready' if not_ready and not items else 'partial'
                    # Public counts describe disclosed qualified items, not hidden
                    # candidates or physical scan totals; actual meter is internal.
                    result={'request_id':request['request_id'],'retrieval_run':run,'purpose':request['principal']['purpose'],'method':{'name':'tl-bounded-primary' if fallback else 'tl-index-or-exact','version':'1','request_ref':slot(),'model_config_ref':slot()},'checked_at':self.clock(),'coverage':{'state':'partial','domain':slot('disclosed qualified recall items'),'scanned':len(items),'limit':limits['items'],'truncated':output_truncated,'missing':[{'status':'unknown','value':None,'reason_code':'incomplete_source','reason':'finite disclosed coverage does not establish catalog exhaustion','basis_refs':[]}]},'completion':completion,'empty_reason':slot('other') if not items else slot(),'items':items,'gaps':[slot('bounded recall did not establish complete coverage')],'dependencies':[deepcopy(d) for item in items for d in item['dependencies']]}
                    c.validate('RecallResult',result)
                    self._final_items(entry,request,items,'result_use')
                    if not audit:self._trace(entry,request,result,targets)
                    self._final_items(entry,request,items,'return');self.s.db.execute('COMMIT');return result
            except _NotReady as exc:
                if self.s.db.in_transaction:self.s.db.execute('ROLLBACK')
                reason='deadline' if 'deadline' in str(exc) else 'unavailable_source' if 'index unavailable' in str(exc) else 'budget_limit' if any(word in str(exc) for word in ('budget','bounded','exhausted')) else 'incomplete_source'
                return {'request_id':request['request_id'],'retrieval_run':slot(),'purpose':request['principal']['purpose'],'method':{'name':'tl-bounded-recall','version':'1','request_ref':slot(),'model_config_ref':slot()},'checked_at':self.clock(),'coverage':{'state':'partial','domain':slot('disclosed qualified recall items'),'scanned':0,'limit':min(request['budget']['max_items'],128),'truncated':True,'missing':[]},'completion':'unavailable' if reason=='unavailable_source' else 'not_ready' if reason=='incomplete_source' else 'partial','empty_reason':slot(reason),'items':[],'gaps':[slot('bounded recall could not complete')],'dependencies':[]}
            except BaseException:
                if self.s.db.in_transaction:self.s.db.execute('ROLLBACK')
                raise
            finally:
                self._meter=None;self._scope_cache={};self._group_cache={};self._body_cache={}
                if audit:self.s.db.execute('PRAGMA query_only='+str(previous_readonly))
    def _persist_dependency(self,consumer,dependency,scope,path):
        dependency=deepcopy(dependency);c.validate('Dependency',dependency)
        metadata={'contract':'TL-DEPENDENCY-1','consumer':deepcopy(consumer),'dependency':dependency,'field_path':path,'scope':deepcopy(scope)}
        revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.s.instance_id,dependency['target']['id'],dependency['expected']['revision'])).fetchone()
        return insert(self.s,'tl_dependency',consumer_ref_id=consumer['id'],source_ref_id=dependency['target']['id'],source_revision_id=revision[0] if revision else None,relation=dependency['relation'],purpose=dependency['consumer_purpose'],expected_epoch=dependency['expected']['epoch'],field_path=path,metadata_artifact_id=self.s.artifact(metadata))
    def _dependency_scope(self,entry,request,dependency,fallback):
        token=dependency['expected'];key=(token['object']['id'],token['revision'])
        if token['object']['kind']!='tl_representation_head':return fallback
        if key not in self._scope_cache:
            row=self.s.db.execute('SELECT id,payload_artifact_id FROM tl_representation WHERE instance_id=? AND series_id=? AND representation_no=?',(self.s.instance_id,key[0],key[1])).fetchone()
            if row is None:raise ContractError('source representation version unavailable')
            self._attest(self.authority.verify_candidate_access(entry,deepcopy(request),ref(self.s,row['id']),'dependency_scope'))
            value=self.storage.read_artifact(row['payload_artifact_id'],'Representation');self._scope_cache[key]=deepcopy(value['scope'])
        return self._scope_cache[key]

    def _erase_retention(self,entry,request,dependency,scope):
        # A delete-only relation is not factual support. Only erase barriers
        # affect retention here; unavailability/revoke are not reinterpreted.
        token=dependency['expected'];principal=request['principal'];self.eligibility.validate_token('tl.recall.retention',principal,token,'delete_retention')
        for key,source_scope,expected,path in self.eligibility._upstream(token,scope,self._meter['scan']):
            rows=self.s.db.execute("SELECT b.*,ch.payload_artifact_id FROM tl_barrier b JOIN tl_change ch ON ch.instance_id=b.instance_id AND ch.id=b.change_id WHERE b.instance_id=? AND b.source_ref_id=? AND b.state='active' AND b.kind='erase' ORDER BY b.id LIMIT ?",(self.s.instance_id,key,self._meter['scan']['remaining']+1)).fetchall()
            self._meter['scan']['remaining']-=len(rows)
            if self._meter['scan']['remaining']<0:raise _NotReady('retention scan budget exhausted')
            for row in rows:
                payload=self.storage.read_artifact(row['payload_artifact_id'])
                if payload['purposes'] and principal['purpose'] not in payload['purposes']:continue
                applies=self.eligibility.authority.barrier_applies('tl.recall.retention',deepcopy(principal),dict(row,dependency_path=['delete']+list(path)),deepcopy(payload),deepcopy(source_scope),principal['purpose'],deepcopy(principal['recipient']))
                if applies is not None and type(applies) is not bool:raise ContractError('invalid retention applicability')
                if applies is not False and self.eligibility.overlaps('tl.recall.retention',principal,self.storage.read_artifact(row['scope_artifact_id'],'Scope'),source_scope):raise Forbidden('erase blocks retained relation')
        self._check_time()

    def _return_identity(self,request,item):
        if item['representation_ref']['status']=='known':
            row=self.s.row('tl_representation',item['representation_ref']['value']['id']);series=self.s.row('tl_representation_head',row['series_id']);revision=self.s.row('tl_content_revision',row['content_revision_id']);content=self.s.row('tl_content',revision['content_id'])
            if row['state']=='withdrawn' or row['body_digest']!=item['body_digest']['hex'] or item['representation_revision']['value']['revision']!=row['representation_no'] or item['representation_revision']['value']['object']['id']!=row['series_id'] or item['content_revision']['value']['revision']!=revision['revision_no'] or item['content_ref']['value']['id']!=revision['content_id']:raise _NotReady('return representation identity changed')
            if item['usage_state']=='current' and (row['state']!='ready' or series['representation_id']!=row['id'] or content['head_revision_id']!=revision['id'] or revision['status']!='accepted'):raise _NotReady('current return head changed')
            key=row['body_artifact_id']
            if key not in self._body_cache:self._body_cache[key]=self.storage.read_artifact(key)
            raw=self._body_cache[key]
            if not isinstance(raw,bytes) or sha(raw)!=row['body_digest'] or raw.decode('utf-8')!=item['body']:raise ContractError('return body does not match actual committed representation')
        elif item['memory_revision']['status']=='known':
            version=item['memory_revision']['value'];row=self.s.db.execute('SELECT id,memory_id FROM memory_revisions WHERE instance_id=? AND memory_id=? AND revision_no=?',(self.s.instance_id,version['object']['id'],version['revision'])).fetchone()
            if row is None or sha(item['body'])!=item['body_digest']['hex']:raise _NotReady('return memory revision changed')
            memory=self.s.row('memory_items',row['memory_id'])
            if memory['state']!='active' or request['version_mode']=='current' and memory['current_revision_id']!=row['id']:raise _NotReady('return memory is no longer current')

    def _final_items(self,entry,request,items,stage):
        self._check_time();self._guard(entry,request,stage)
        for item in items:
            for dependency in item['dependencies']+item['relations']:self._dependency_scope(entry,request,dependency,item['scope'])
        for item in items:
            self._attest(self.authority.verify_retention(entry,deepcopy(request),deepcopy(item),stage));self._check_time()
        # No further retention/request callbacks after this source pass.
        for item in items:
            for dependency in item['dependencies']:self._qualified(entry,request,dependency['expected'],self._dependency_scope(entry,request,dependency,item['scope']),stage+'_source')
            self._return_identity(request,item)
            for dependency in item['relations']:
                if dependency['relation']=='delete':self._erase_retention(entry,request,dependency,self._dependency_scope(entry,request,dependency,item['scope']))
            if item['representation_ref']['status']=='known':
                row=self.s.row('tl_representation',item['representation_ref']['value']['id'])
                if row['group_id']:self._group_qualified(entry,request,row['group_id'],self._meter,{'bytes':self._meter['byte_limit']})
        self._local_control(request)
    def _local_control(self,request):
        self._check_time()
        if request['entry']=='execution':
            self.s.assert_execution_allowed()
            if request['control']['cancelled']:raise Forbidden('recall cancelled before use')
            activity=self.s.row('activities',request['activity_ref']['value']['id'])
            if activity['cancel_requested_at'] or activity['state']=='cancelled':raise Forbidden('recall activity cancelled before use')
        elif request['principal']['actor']['id']!=self.s.row('identity_instances',self.s.instance_id)['controller_ref']:raise Forbidden('audit controller changed')

    def _trace(self,entry,request,result,targets):
        self._attest(self.authority.verify_trace(entry,deepcopy(request),deepcopy(result),'write'))
        self._final_items(entry,request,result['items'],'trace_write');control=self.s.artifact(request['control']);run=result['retrieval_run']['value']['id']
        for rank,item in enumerate(result['items']):
            target=targets[item['id']]
            if target is None or target['kind'] not in ('memory_revisions','tl_representation'):raise Forbidden('execution result lacks actual traceable target')
            self.storage.validate_ref(target);origin=None
            if target['kind']=='memory_revisions':
                if item['memory_revision']['status']!='known':raise ContractError('memory trace lacks actual version')
                version=item['memory_revision']['value'];row=self.s.row('memory_revisions',target['id'])
                if row['memory_id']!=version['object']['id'] or row['revision_no']!=version['revision']:raise ContractError('memory trace version mapping differs')
                origin=self.s.insert('memory_retrieval_results',run_id=run,memory_revision_id=target['id'],rank=rank,score=item['selection']['score']['value'],selection_reason=item['selection']['reason'])
                self.s.insert('memory_access_records',memory_revision_id=target['id'],activity_id=request['activity_ref']['value']['id'],operation='retrieved')
            artifact=self.s.artifact(item);self.s.insert('tl_recall_item',id=item['id'],retrieval_run_id=run,rank=rank,kind=item['kind'],target_ref_id=target['id'],payload_artifact_id=artifact,origin_result_id=origin,control_artifact_id=control)
            dependencies=item['dependencies']+[d for d in item['relations'] if d not in item['dependencies']]
            for index,dependency in enumerate(dependencies):
                dependency=deepcopy(dependency);dependency['consumer_purpose']=request['principal']['purpose']
                self._persist_dependency(ref(self.s,item['id']),dependency,self._dependency_scope(entry,request,dependency,item['scope']),'/recall/'+str(index))
                self._persist_dependency(ref(self.s,artifact),dependency,self._dependency_scope(entry,request,dependency,item['scope']),'/material/'+str(index))
        event=self.s.event('recall.result',payload={'request_fingerprint':c.fingerprint(request),'result':deepcopy(result)},source='tl.recall.result',key=request['request_id'],activity=request['activity_ref']['value']['id'])
        result_artifact=self.s.row('runtime_events',event)['payload_artifact_id']
        for item in result['items']:
            for index,dependency in enumerate(item['dependencies']+[d for d in item['relations'] if d not in item['dependencies']]):self._persist_dependency(ref(self.s,result_artifact),dependency,self._dependency_scope(entry,request,dependency,item['scope']),'/items/'+item['id']+'/'+str(index))
    def register_inputs(self,entry,request,result,target_request,final_principal,field_prefix='/recall'):
        c.validate('RecallRequest',request);c.validate('RecallResult',result);c.validate('Principal',final_principal);t.string(field_prefix)
        if request['entry']!='execution':raise Forbidden('read-only audit cannot register model inputs')
        request,result,target_request,final_principal=deepcopy((request,result,target_request,final_principal))
        if result['request_id']!=request['request_id'] or result['retrieval_run']['status']!='known':raise Conflict('input requires actual completed execution trace')
        if self.s.db.in_transaction:raise Conflict('input registration requires independent gate before transactions')
        with self._bound(entry),dispatch_gate(self.s.root):
            self._initialize_meter(request)
            try:
                with self.authority.read_boundary(entry,deepcopy(request),self.reader):
                    self._guard(entry,request,'register_inputs');self.storage.validate_ref(target_request,expected_kind='thought_requests')
                    actual_target=self.s.row('thought_requests',target_request['id'])
                    if actual_target['state']!='prepared' or actual_target['deadline']<=self.clock() or actual_target['activity_id']!=request['activity_ref']['value']['id']:raise Forbidden('input target is not the current prepared request for this activity')
                    assembly={'field_prefix':field_prefix,'target_hash':actual_target['request_hash'],'target_state_revision':actual_target['state_revision'],'recall_run':deepcopy(result['retrieval_run']),'items':[{'id':item['id'],'body_digest':deepcopy(item['body_digest']),'dependencies':deepcopy(item['dependencies'])} for item in result['items']]}
                    assembly['manifest_fingerprint']=c.fingerprint(assembly)
                    self._attest(self.authority.verify_input_binding(entry,deepcopy(request),deepcopy(result),deepcopy(target_request),deepcopy(final_principal),deepcopy(assembly),'register_inputs'))
                    ids=[];final_request=deepcopy(request);final_request['principal']=deepcopy(final_principal);prepared=[]
                    for index,item in enumerate(result['items']):
                        row=self.s.row('tl_recall_item',item['id'])
                        trace_token={'object':ref(self.s,row['id']),'revision':0,'epoch':self.eligibility.current_epoch(ref(self.s,row['id']),item['scope'])}
                        self._qualified(entry,final_request,trace_token,item['scope'],'input_trace_material')
                        if row['retrieval_run_id']!=result['retrieval_run']['value']['id'] or self.storage.read_artifact(row['payload_artifact_id'],'RecallItem')!=item:raise Conflict('input item is not its exact durable recall result')
                        trace_dependency={'target':deepcopy(trace_token['object']),'relation':'read','expected':deepcopy(trace_token),'consumer_purpose':final_principal['purpose']}
                        prepared.append((trace_dependency,field_prefix+'/'+str(index),item['scope'],{'algorithm':'sha256','hex':sha(dumps(item))}))
                        for dependency in item['dependencies']:
                            if dependency['relation']=='delete':raise ContractError('delete-only relation cannot become model input support')
                            dependency_scope=self._dependency_scope(entry,final_request,dependency,item['scope'])
                            self._qualified(entry,final_request,dependency['expected'],dependency_scope,'input_qualification')
                            bound=deepcopy(dependency);bound['relation']='read';bound['consumer_purpose']=final_principal['purpose'];prepared.append((bound,field_prefix+'/'+str(index)+'/body',dependency_scope,item['body_digest']))
                    self._attest(self.authority.verify_input_binding(entry,deepcopy(request),deepcopy(result),deepcopy(target_request),deepcopy(final_principal),deepcopy(assembly),'all_inputs_prechecked'))
                    for bound,path,scope,digest in prepared:
                        dep=self.eligibility.register_dependency('tl.recall.input',final_principal,target_request,bound,path,scope)
                        ids.append(self.eligibility.register_input('tl.recall.input',final_principal,target_request,dep,body_digest=digest))
                    return ids
            finally:self._meter=None;self._scope_cache={};self._group_cache={};self._body_cache={};self._body_cache={}
