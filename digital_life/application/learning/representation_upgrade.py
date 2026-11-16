"""Explicit finite header-language upgrade of an already accepted TL-TEXT-1.

Source JSON is never translated. No new cognitive decision, learning product,
model/tool call, work, account, deadline or atomic-group weakening is created.
"""
from copy import deepcopy
import json
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,identifier,utc
from digital_life.application.learning.eligibility import ref,slot
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore,StorageAuthority,StorageGrant
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate

SOURCE='tl.representation.upgrade'
LANGUAGES=('zh','en')


def policy(s):
    key=s.rows('policy_epochs')[0]['policy_version_id'];row=s.row('policy_versions',key)
    value=json.loads(row['scope']).get('tool_learning_representation_upgrade')
    t.obj(value,('contract','enabled','languages','max_upgrades','expires_at'))
    if value['contract']!='TL-HEADER-LANGUAGE-UPGRADE-1' or value['enabled'] is not True or row['authority']!=s.config()['controller']:raise Forbidden('current header-language upgrade policy is not enabled')
    t.array(value['languages'],lambda v:t.enum(v,LANGUAGES));t.integer(value['max_upgrades'],1,8);c.validate('UTC',value['expires_at'])
    if value['expires_at']<=utc() or row['effective_at']>utc() or row['valid_to'] is not None and row['valid_to']<=utc():raise Forbidden('header-language upgrade policy expired')
    return key,value


def grant_for_handoff(s,handoff):
    row=s.db.execute('SELECT * FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=?',(s.instance_id,SOURCE,handoff['id'])).fetchone()
    if row is None:return None
    if s.row('artifacts',row['payload_artifact_id'])['size']>65536:raise Forbidden('bounded upgrade proof required')
    body=s.read_artifact(row['payload_artifact_id'])
    active,profile=policy(s)
    if body['policy']!=ref(s,active) or body['controller']!=ref(s,s.config()['controller']) or body['expires_at']<=utc() or body['language'] not in profile['languages'] or not 1<=body['ordinal']<=profile['max_upgrades']:raise Forbidden('current format policy/authority/finite ordinal changed')
    if body['new_handoff_id']!=handoff['id'] or body['work_id']!=handoff['work_id'] or body['content_revision_id']!=handoff['content_revision_id'] or body['decision_id']!=handoff['decision_id'] or body['input_fingerprint']!=handoff['input_fingerprint'] or handoff['group_id'] is not None:raise Conflict('upgrade handoff differs from exact authenticated intent')
    return row,body


def language(s,handoff):
    proof=grant_for_handoff(s,handoff)
    return 'zh' if proof is None else proof[1]['language']


class UpgradeSession:
    """Non-JSON closed runtime capability, held only during explicit SDK call."""
    def __init__(self,coordinator,old_handoff,bearer,requested_language,ordinal):
        from digital_life.application.learning.runtime import authenticate_controller
        self.r=coordinator;self.s=coordinator.s;self.old_id=old_handoff;self.new_id=identifier();self.proof=None;self.nonce=identifier()
        self.actor=authenticate_controller(self.s,bearer);self.r.require_learning()
        t.enum(requested_language,LANGUAGES);t.integer(ordinal,1)
        self.requested_language=requested_language;self.ordinal=ordinal
        self.initial_policy,self.initial_profile=policy(self.s)
        if requested_language not in self.initial_profile['languages'] or ordinal>self.initial_profile['max_upgrades']:raise Forbidden('language/ordinal outside finite current policy')
        old=self.s.row('tl_handoff',old_handoff);work=self.s.row('tl_work',old['work_id'])
        if old['group_id'] is not None:raise Forbidden('atomic group representation upgrades require an independent group design')
        if old['state']!='published':raise Forbidden('language upgrade requires an actual published original representation')
        self._base(old,work,material=False)
    def request(self,entry):
        old=self.s.row('tl_handoff',self.old_id);work=self.s.row('tl_work',old['work_id']);decision=self.s.row('tl_decision',old['decision_id'])
        principal=self.r.o.principal(entry)
        payload={'proposal':ref(self.s,decision['proposal_id']),'review_round':decision['review_round'],'policy':deepcopy(principal['authorization']),'review':slot(),'atomic_group':slot()}
        return self.r._envelope(entry,work['learning_activity_id'],payload,work['id'],self.r.budget.check_work(work['id'])['budget'])
    def prepare(self):
        entry,_=self.r.o.entry('M03','accept',self.s.config()['controller']);request=self.request(entry)
        with self.r.read_stage(entry,request),dispatch_gate(self.s.root),self.s.tx():
            self.verify(entry,request)
            old=self.s.row('tl_handoff',self.old_id);work=self.s.row('tl_work',old['work_id'])
            existing=self.s.db.execute('SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=?',(self.s.instance_id,SOURCE,old['id'])).fetchone()
            old_language='zh' if existing is None else self.s.read_artifact(existing[0])['language']
            if old_language==self.requested_language:raise Forbidden('same language is not a new rendering change')
            method_artifact=self.s.artifact({'contract':'TL-HEADER-LABEL-METHOD-1','language':self.requested_language,'renderer':'five-fixed-labels/source-json-identity','version':'1'})
            method={'name':'tl-header-label-localization','version':'1','request_ref':slot(ref(self.s,method_artifact)),'model_config_ref':slot()}
            semantic={'old_handoff_id':self.old_id,'work_id':work['id'],'content_revision_id':old['content_revision_id'],'decision_id':old['decision_id'],
                'language':self.requested_language,'ordinal':self.ordinal,'method':method,'policy':ref(self.s,self.initial_policy),'controller':ref(self.s,self.actor),
                'original_account_id':work['budget_account_id'],'original_deadline':work['deadline'],'format_version':'TL-TEXT-1'}
            prior=self.s.db.execute('SELECT * FROM runtime_events WHERE instance_id=? AND source=? ORDER BY event_seq LIMIT 65',(self.s.instance_id,SOURCE)).fetchall()
            if len(prior)>64:raise Forbidden('bounded explicit upgrade proof inventory exhausted')
            for record in prior:
                body=self.s.read_artifact(record['payload_artifact_id'])
                if body['content_revision_id']==old['content_revision_id'] and body['ordinal']==self.ordinal:
                    if any(body[k]!=v for k,v in semantic.items()):raise Conflict('upgrade ordinal already bound to another immutable intent')
                    self.new_id=body['new_handoff_id'];self.proof=ref(self.s,record['id']);return
            body=dict(semantic,new_handoff_id=self.new_id,expires_at=min(self.initial_profile['expires_at'],work['deadline']))
            body['input_fingerprint']=c.fingerprint(semantic)
            event=self.s.event('controller.header_language_upgrade_authored',payload=body,source=SOURCE,key=self.new_id,lane='control')
            self.proof=ref(self.s,event)
            revision=self.s.row('tl_content_revision',old['content_revision_id']);content=ref(self.s,revision['content_id'])
            payload=ToolLearningStore(self.s).read_artifact(revision['payload_artifact_id'])
            token={'object':content,'revision':revision['revision_no'],'epoch':self.r.o.eligibility.current_epoch(content,payload['scope'])}
            from digital_life.application.learning.engine import _dependency
            for edge in ('read','delete'):_dependency(self.s,self.proof,token,payload['scope'],edge,'/fixed_accepted_rendering_source','represent')
            event_row=self.s.row('runtime_events',event);proof_token={'object':self.proof,'revision':0,'epoch':0}
            for edge in ('read','delete'):_dependency(self.s,ref(self.s,event_row['payload_artifact_id']),proof_token,payload['scope'],edge,'/rendering_intent','represent')
    def _base(self,old,work,material):
        self.s.assert_execution_allowed()
        if old['group_id'] is not None or work['state'] not in ('completed','handoff_pending'):raise Forbidden('upgrade cannot reopen suspended, failed or unaccepted work/group')
        for key in ('source_activity_id','learning_activity_id'):
            activity=self.s.row('activities',work[key])
            if activity['cancel_requested_at'] or activity['state'] in ('completed','failed','cancelled','paused'):raise Forbidden('original activity state forbids a new rendering read')
        parent=self.r.k.budget.check_activity(work['source_activity_id'])
        if parent['blocked']:raise Forbidden('original parent resources/control remain blocked')
        snapshot=self.r.budget.check_work(work['id'])
        if any(v!='work_completed' for v in snapshot['block_reasons']):raise Forbidden('original rendering resource/control limits remain blocked')
        if any(snapshot['remaining'][k]<1 for k in ('scan','items','bytes','elapsed_ms')):raise Forbidden('original local rendering resources exhausted')
        revision=self.s.row('tl_content_revision',old['content_revision_id']);content=self.s.row('tl_content',revision['content_id']);decision=self.s.row('tl_decision',old['decision_id'])
        if revision['status']!='accepted' or decision['operation']!='accept' or content['head_revision_id']!=revision['id'] or decision['content_revision_id']!=revision['id']:raise Conflict('original accepted native content/decision changed')
        if material:
            if self.s.row('artifacts',revision['payload_artifact_id'])['size']>1048576:raise Forbidden('bounded complete accepted rendering source required')
            payload=ToolLearningStore(self.s).read_artifact(revision['payload_artifact_id'])
            entry,principal=self.r.o.entry('M03','accept',self.s.config()['controller'])
            token={'object':ref(self.s,content['id']),'revision':revision['revision_no'],'epoch':self.r.o.eligibility.current_epoch(ref(self.s,content['id']),payload['scope'])}
            if self.s.db.in_transaction:self.r.o.eligibility._check(entry,principal,token,payload['scope'],'accept',principal['recipient'],'upgrade_current_source')
            else:self.r.o.eligibility.check(entry,principal,token,payload['scope'],'accept',principal['recipient'],'upgrade_current_source')
        return snapshot
    def verify(self,entry,request=None):
        self.r.o.check(entry,request['principal'] if request is not None else None)
        principal=self.r.o.principal(entry)
        if principal['module'] not in ('M03','M04') or principal['purpose'] not in ('accept','represent'):raise Forbidden('upgrade capability is only M03/M04 original local rendering')
        active,profile=policy(self.s)
        if active!=self.initial_policy or self.actor!=self.s.config()['controller'] or self.requested_language not in profile['languages'] or self.ordinal>profile['max_upgrades']:raise Forbidden('upgrade current authority/policy/ordinal changed')
        if self.proof is None:
            old=self.s.row('tl_handoff',self.old_id);work=self.s.row('tl_work',old['work_id'])
            self._base(old,work,material=request is not None)
            return {'work_id':work['id']}
        event=self.s.row('runtime_events',self.proof['id']);body=self.s.read_artifact(event['payload_artifact_id'])
        if body['policy']!=ref(self.s,active) or body['controller']!=ref(self.s,self.s.config()['controller']) or body['expires_at']<=utc():raise Forbidden('upgrade current policy/authority expired or changed')
        old=self.s.row('tl_handoff',self.old_id);work=self.s.row('tl_work',old['work_id'])
        self._base(old,work,material=request is not None)
        if body['old_handoff_id']!=old['id'] or body['work_id']!=work['id'] or body['content_revision_id']!=old['content_revision_id'] or body['original_account_id']!=work['budget_account_id'] or body['original_deadline']!=work['deadline']:raise Conflict('upgrade original ownership/account/deadline changed')
        return body
    def verify_read(self,entry,work,operation,binding,stage):
        body=self.verify(entry)
        if self.r.representation_session is not self or binding!={'work_id':work['id'],'authorization_id':self.nonce} or work['id']!=body['work_id'] or operation['kind']!='memory_retrieval_runs':raise Forbidden('terminal rendering capability is not this exact original local read')
        if self.s.row('memory_retrieval_runs',operation['id'])['activity_id']!=work['learning_activity_id']:raise Forbidden('terminal rendering read belongs to another activity')
    def create_handoff(self):
        r=self.r;old=self.s.row('tl_handoff',self.old_id);work=self.s.row('tl_work',old['work_id']);decision=self.s.row('tl_decision',old['decision_id'])
        entry,principal=r.o.entry('M03','accept',self.s.config()['controller'])
        payload={'proposal':ref(self.s,decision['proposal_id']),'review_round':decision['review_round'],'policy':deepcopy(principal['authorization']),'review':slot(),'atomic_group':slot()}
        request=r._envelope(entry,work['learning_activity_id'],payload,work['id'],r.budget.check_work(work['id'])['budget'])
        session=self
        class Owner(StorageAuthority):
            def verify(_,actual_entry,operation,actual_request,instance,stage):
                if operation!='decide_proposal':raise Forbidden('upgrade owner has no other business operation')
                session.verify(actual_entry,actual_request);r.stage_context(actual_entry,actual_request)
                return StorageGrant('M03',frozenset(('tl_handoff','tl_dependency')))
            def project_response(_,actual_entry,operation,actual_request,response,instance,stage):
                session.verify(actual_entry,actual_request);r.stage_context(actual_entry,actual_request);return response
        storage=ToolLearningStore(self.s,Owner())
        def create(tx):
            body=self.verify(entry,request)
            present=self.s.db.execute('SELECT * FROM tl_handoff WHERE instance_id=? AND id=?',(self.s.instance_id,self.new_id)).fetchone()
            if present is None:
                tx.insert('tl_handoff',id=self.new_id,work_id=work['id'],content_revision_id=old['content_revision_id'],decision_id=old['decision_id'],group_id=None,format_version='TL-TEXT-1',input_fingerprint=body['input_fingerprint'],state='pending',lease_generation=0,attempts=0,deadline=old['deadline'],budget_account_id=old['budget_account_id'],row_revision=0)
                from digital_life.application.learning.engine import _dependency
                revision=self.s.row('tl_content_revision',old['content_revision_id']);payload=ToolLearningStore(self.s).read_artifact(revision['payload_artifact_id'])
                token={'object':self.proof,'revision':0,'epoch':0}
                for edge in ('read','delete'):_dependency(self.s,ref(self.s,self.new_id),token,payload['scope'],edge,'/authorized_rendering_method','represent')
            else:grant_for_handoff(self.s,dict(present))
            return {'command_id':request['command_id'],'operation':'decide_proposal','disposition':'applied' if present is None else 'reused','owner':'M03','result_refs':[ref(self.s,self.new_id)],'current':slot(),'reason':'none','error_code':'NONE','coverage':{'state':'complete','domain':slot('one same-content authorized rendering obligation'),'scanned':1,'limit':1,'truncated':False,'missing':[]},'retry':{'allowed':False,'condition':slot(),'resume_work':slot()},'committed_at':slot(utc())}
        with r.read_stage(entry,request):storage.execute(entry,'decide_proposal',request,create)
        return self.new_id
