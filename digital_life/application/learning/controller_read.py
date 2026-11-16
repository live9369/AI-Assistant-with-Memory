"""Authenticated, bounded, read-only historical material for strict panels.

This is an audit use, not an execution grant. Stop and wake locks remain intact;
current source permissions/retention and all active barriers still apply.
"""
from copy import deepcopy
from contextlib import contextmanager
import re
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,identifier,utc,dumps
from digital_life.domain import tool_learning_contract as c
from digital_life.application.learning.eligibility import ref,slot
from digital_life.application.learning.recall import ToolLearningRecall,RecallAuthority
from digital_life.application.learning.runtime import authenticate_controller,_ControllerReadSession,ControllerSourceAuthority
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter,immutable_reference_boundary
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate


class _AuditOwner(RecallAuthority):
    def __init__(self,reader):self.r=reader
    def verify_audit(self,entry,request,stage):
        self.r.sources._session(entry,request['principal'])


class ControllerMaterialReader:
    def __init__(self,store,bearer):
        self.s=store;controller=authenticate_controller(store,bearer)
        self.sources=ControllerSourceAuthority(store);self.sources.session=_ControllerReadSession(controller,'history_audit');self.entry=self.sources.session.nonce
        policy=store.rows('policy_epochs')[0]['policy_version_id']
        self.principal={'actor':ref(store,controller),'recipient':ref(store,controller),'module':'M04','purpose':'history_audit','authorization':ref(store,policy)}
        self.audit=ToolLearningRecall(store,_AuditOwner(self),self.sources)
        self.audit.eligibility.max_nodes=4096;self.audit.eligibility.max_rows=65536
        self.depth=0
    @contextmanager
    def boundary(self):
        if self.depth:yield;return
        self.depth+=1
        deadline=utc(30);amounts={'input_tokens':0,'output_tokens':0,'attempts':0,'tool_calls':0,'scan':262144,'items':262144,'bytes':64*1024*1024,'elapsed_ms':30000}
        # The same physical reader covers SQL rows, hidden ancestor metadata,
        # snapshot bodies and source-authority reads. No shared account write.
        meter=PhysicalReadMeter(amounts,deadline)
        self.audit._meter={'material_items':0,'item_limit':100,'usage_unknown':False,'read_bytes':0,'byte_limit':amounts['bytes'],'scan':{'remaining':65536},'started':self.audit.monotonic(),'max_seconds':30,'deadline':deadline}
        try:
            with dispatch_gate(self.s.root),meter.installed(self.s),immutable_reference_boundary(self.s),self.audit._bound(self.entry):yield
        finally:self.depth-=1;self.audit._meter=None
    def _scope(self,origin):
        row=self.s.db.execute('SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? ORDER BY id LIMIT 1',(self.s.instance_id,origin['id'])).fetchone()
        if row:return deepcopy(self.audit.eligibility._metadata(row)['scope'])
        if origin['kind'] not in ('perception_signals','configuration_versions','model_versions','policy_versions'):raise Forbidden('historical material lacks actual producer lineage')
        from digital_life.application.learning.engine import source_scope
        return source_scope(self.s)
    def qualify(self,origin,stage='controller_material_read'):
        if not self.depth:raise Forbidden('controller material requires a bounded audit boundary')
        scope=self._scope(origin);revision=origin['revision']['value'] if origin['revision']['status']=='known' else 0
        token={'object':deepcopy(origin),'revision':revision,'epoch':self.audit.eligibility.current_epoch(origin,scope)}
        request={'entry':'controller_audit','principal':deepcopy(self.principal)}
        self.audit._qualified(self.entry,request,token,scope,stage)
        return token,scope
    def material(self,origin,key,expected=None):
        with self.boundary():
            owner=self.s.row(origin['kind'],origin['id'])
            fields={'thought_requests':('request_artifact_id',),'thought_results':('response_artifact_id','parsed_artifact_id'),'perception_signals':('artifact_id',),'action_results':('receipt_artifact_id',),'runtime_events':('payload_artifact_id',),'artifacts':('id',),'configuration_versions':('artifact_ref',),'model_versions':('artifact_ref',)}.get(origin['kind'],())
            if key not in {owner[field] for field in fields}:raise Forbidden('artifact is not an actual material field of this source owner')
            self.qualify(origin);row=self.s.row('artifacts',key)
            if expected is not None and row['hash']!=expected:raise Conflict('historical material digest differs')
            value=self.audit.storage.read_artifact(key)
            self.qualify(origin,'controller_material_return');self.audit._check_time()
            return {'available':True,'artifact_id':key,'hash':row['hash'],'value':value,'credential_redaction':True,'truncated':False}
    def thought(self,key):
        from digital_life.application.monitoring.thought_inspection import ThoughtInspection,FEATURES
        with self.boundary():
            origin=ref(self.s,key,'thought_requests');self.qualify(origin)
            row=self.s.row('thought_requests',key);snapshot=self.material(origin,row['request_artifact_id'],row['request_hash'])
            packet=snapshot['value'];payload=packet.get('input',packet) if type(packet) is dict else {}
            results=[]
            for result in self.s.db.execute('SELECT * FROM thought_results WHERE instance_id=? AND request_id=? ORDER BY rowid LIMIT 101',(self.s.instance_id,key)):
                if len(results)>=100:raise Forbidden('historical thought results exceed bounded panel request')
                result=dict(result);root=ref(self.s,result['id'],'thought_results')
                result['response']=self.material(root,result['response_artifact_id'],result['response_hash']);result['parsed_output']=self.material(root,result['parsed_artifact_id']);results.append(result)
            attempts=[dict(r) for r in self.s.db.execute('SELECT * FROM thought_attempts WHERE instance_id=? AND request_id=? ORDER BY attempt_no LIMIT 101',(self.s.instance_id,key))]
            if len(attempts)>100:raise Forbidden('historical attempts exceed bounded panel request')
            invocations=[];audit_roots=[]
            for attempt in attempts:
                event=self.s.db.execute("SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND source='strict.provider.invocation' AND source_event_id=?",(self.s.instance_id,attempt['id'])).fetchone()
                if event:
                    event_origin=ref(self.s,event['id'],'runtime_events')
                    invocations.append(self.material(event_origin,event['payload_artifact_id']));audit_roots.append(event_origin)
            behavior=[]
            events=self.s.db.execute("SELECT e.id,e.payload_artifact_id FROM runtime_events e WHERE e.instance_id=? AND e.activity_id=? AND e.event_type='behavior_policy.selected' AND EXISTS (SELECT 1 FROM tl_dependency d JOIN thought_results r ON r.instance_id=d.instance_id AND r.id=d.source_ref_id WHERE d.instance_id=e.instance_id AND d.consumer_ref_id=e.id AND d.relation='read' AND d.field_path='/model_derivation' AND r.request_id=?) ORDER BY e.event_seq LIMIT 101",(self.s.instance_id,row['activity_id'],key)).fetchall()
            if len(events)>100:raise Forbidden('request behavior records exceed bounded panel audit')
            for event in events:
                event_origin=ref(self.s,event['id'],'runtime_events');material=self.material(event_origin,event['payload_artifact_id'])
                data=material['value']
                if type(data) is not dict or data.get('request')!=key:raise Conflict('actual behavior event and request producer mapping differ')
                decision=self.s.row('decision_records',data['decision'])
                if decision['activity_id']!=row['activity_id'] or decision['strategy_type']!='probabilistic' or decision['state']!='finalized':raise Conflict('behavior event is not this actual finalized probabilistic selection')
                behavior.append(material);audit_roots.append(event_origin)
            features=[{'name':name,'items':[{'field':field,'state':'provided' if field in payload else 'not_in_request','value':payload.get(field)} for field in keys]} for name,keys in FEATURES.items()]
            # Recheck each source-bearing root after all reads/callbacks; no
            # source hash/body is returned merely because an earlier read passed.
            self.qualify(origin,'controller_final_return')
            for item in results:self.qualify(ref(self.s,item['id'],'thought_results'),'controller_final_return')
            self.audit._check_time()
            config=self.s.row('configuration_versions',row['model_config_id']);pinned=self.material(ref(self.s,config['id'],'configuration_versions'),config['artifact_ref'],config['hash'])['value'].get('model')
            self.qualify(origin,'controller_final_return');self.qualify(ref(self.s,config['id'],'configuration_versions'),'controller_final_return')
            for audit_root in audit_roots:self.qualify(audit_root,'controller_final_return')
            for item in results:self.qualify(ref(self.s,item['id'],'thought_results'),'controller_final_return')
            self.audit._check_time()
            return ThoughtInspection(self.s).clean({'request':row,'input':snapshot,'features':features,'attempts':attempts,'results':results,'provider_invocations':invocations,'usage':[c.loads(a['usage_json']) for a in attempts if a.get('usage_json')],'behavior_decisions':behavior,'pinned_model_configuration':pinned,'scope':'实际持久化的独立输入包与输出；当前来源权限核验；不含隐藏推理。','raw_provider_response_recorded':False,'read_only':True})
    def chat(self,thread):
        from digital_life.application.chat.chat import Chat
        with self.boundary():
            Chat(self.s).valid_id(thread)
            args=(self.s.instance_id,thread)
            total=self.s.db.execute("SELECT count(*) FROM activities a JOIN context_snapshots c ON c.activity_id=a.id AND c.instance_id=a.instance_id WHERE a.instance_id=? AND json_extract(c.attributes_json,'$.chat.thread_id')=?",args).fetchone()[0]
            rows=list(reversed(self.s.db.execute("SELECT a.id,a.state,a.revision,a.recorded_at FROM activities a JOIN context_snapshots c ON c.activity_id=a.id AND c.instance_id=a.instance_id WHERE a.instance_id=? AND json_extract(c.attributes_json,'$.chat.thread_id')=? ORDER BY a.rowid DESC LIMIT 100",args).fetchall()));messages=[];roots=[]
            for row in rows:
                context=self.s.db.execute('SELECT id FROM context_snapshots WHERE instance_id=? AND activity_id=? AND json_extract(attributes_json,\'$.chat.thread_id\')=?',(self.s.instance_id,row['id'],thread)).fetchone()
                if context is None:continue
                root=ref(self.s,context[0],'context_snapshots');self.qualify(root);roots.append(root)
                chat=c.loads(self.s.row('context_snapshots',context[0])['attributes_json'])['chat'];messages.append({'role':'user','text':chat['text'],'activity_id':row['id'],'recorded_at':row['recorded_at'],'state':row['state']})
                for result in self.s.db.execute("SELECT r.* FROM thought_results r JOIN thought_requests q ON q.instance_id=r.instance_id AND q.id=r.request_id WHERE r.instance_id=? AND q.activity_id=? AND r.acceptance='accepted' ORDER BY r.rowid LIMIT 10",(self.s.instance_id,row['id'])):
                    result=dict(result);root=ref(self.s,result['id'],'thought_results');body=self.material(root,result['parsed_artifact_id'])['value'];roots.append(root)
                    if body.get('explanation'):messages.append({'role':'assistant','text':body['explanation'],'activity_id':row['id'],'recorded_at':result['recorded_at'],'waiting_reason':None})
            for root in roots:self.qualify(root,'controller_chat_final_return')
            self.audit._check_time();last=rows[-1] if rows else None
            ready=last is None or last['state'] in ('waiting_input','completed','failed','cancelled','paused')
            if last and not ready:
                failed=self.s.db.execute("SELECT 1 FROM thought_requests WHERE instance_id=? AND activity_id=? AND state='failed' LIMIT 1",(self.s.instance_id,last['id'])).fetchone()
                pending=self.s.db.execute("SELECT 1 FROM jobs WHERE instance_id=? AND target_ref=? AND state IN ('queued','leased') LIMIT 1",(self.s.instance_id,last['id'])).fetchone()
                if failed and not pending:ready=True
            if last and self.s.db.execute("SELECT 1 FROM approval_requests p JOIN action_intents i ON i.instance_id=p.instance_id AND i.id=p.action_ref JOIN decision_candidates c ON c.instance_id=i.instance_id AND c.id=i.candidate_id JOIN decision_records d ON d.instance_id=c.instance_id AND d.id=c.decision_id WHERE p.instance_id=? AND d.activity_id=? AND p.decision='pending' LIMIT 1",(self.s.instance_id,last['id'])).fetchone():ready=False
            from digital_life.application.monitoring.thought_inspection import ThoughtInspection
            return ThoughtInspection(self.s).clean({'thread_id':thread,'messages':messages,'last_activity_id':last['id'] if last else None,'can_send':ready,'omitted_turns':max(0,total-100)})
    def cancel(self,activity,body):
        # Authenticated protective control mutation, separate from read-only
        # material audit. No source body is read or revealed to cancel work.
        from digital_life.application.monitoring.management import Management
        with dispatch_gate(self.s.root):
            if self.sources.session.controller!=self.s.config()['controller']:raise Forbidden('current controller authority changed')
            return Management(self.s).cancel(activity,body)
    def send(self,thread,body):
        from digital_life.application.chat.chat import Chat
        from digital_life.application.lifecycle.control_plane import Control
        from digital_life.application.learning.engine import submit_inbound
        valid=Chat(self.s);valid.valid_id(thread);key=valid.valid_id(body.get('idempotency_key'));text=body.get('text')
        if type(text) is not str or not text.strip() or len(text.encode())>4000:raise ContractError('bounded nonempty chat message required')
        source='chat:'+thread
        with dispatch_gate(self.s.root):
            prior=self.s.db.execute('SELECT id FROM perception_signals WHERE instance_id=? AND external_id=?',(self.s.instance_id,source+':'+key)).fetchone()
            current=self.chat(thread)
            if prior is None and (body.get('expected_last_activity_id')!=current['last_activity_id'] or not current['can_send']):raise Conflict('chat changed or previous turn awaits action approval')
            control=Control(self.s.root,self.s.instance_id)
            try:control.accept_inbound(source,key,{'text':text},self.sources.session.controller)
            finally:control.close()
            activity=submit_inbound(self.s,text,key,source)
            if prior is None:
                with self.s.tx():
                    row=self.s.db.execute('SELECT id,attributes_json FROM context_snapshots WHERE instance_id=? AND activity_id=?',(self.s.instance_id,activity)).fetchone()
                    attributes=c.loads(row['attributes_json']);attributes['chat']={'thread_id':thread,'text':text}
                    self.s.db.execute('UPDATE context_snapshots SET attributes_json=? WHERE instance_id=? AND id=?',(dumps(attributes),self.s.instance_id,row['id']))
                    self.s.db.execute('UPDATE activities SET predecessor_activity_id=? WHERE instance_id=? AND id=?',(current['last_activity_id'],self.s.instance_id,activity))
            return {'activity_id':activity,'duplicate':prior is not None,'inference_started':False}
    def chats(self):
        from digital_life.application.chat.chat import Chat
        with self.boundary():
            result=[]
            for candidate in Chat(self.s).list()['items']:
                # This controller's list is derived only from material that
                # the same authenticated source owner can presently inspect.
                try:self.chat(candidate['thread_id'])
                except (Forbidden,Conflict,ContractError):continue
                result.append(candidate)
            return {'items':result}
    def thoughts(self,activity):
        with self.boundary():
            rows=[]
            for row in self.s.db.execute('SELECT id,state,purpose,recorded_at,model_config_id,accepted_result_id FROM thought_requests WHERE instance_id=? AND activity_id=? ORDER BY rowid LIMIT 101',(self.s.instance_id,activity)):
                if len(rows)>=100:raise Forbidden('thought list exceeds bounded audit request')
                self.qualify(ref(self.s,row['id'],'thought_requests'));rows.append(dict(row))
            return {'items':rows}
    def action(self,intent_id):
        with self.boundary():
            ancestry=self.s.db.execute("SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? AND relation='read' AND field_path='/model_derivation' LIMIT 2",(self.s.instance_id,intent_id)).fetchall()
            if len(ancestry)!=1:raise Forbidden('action has no exact original producer lineage')
            meta=self.audit.eligibility._metadata(ancestry[0]);origin=meta['dependency']['expected']['object']
            if origin['kind']!='thought_results':raise Forbidden('action does not have a recognized ordinary producer')
            self.qualify(origin,'controller_action_use')
            return origin
    def activity(self,key):
        from digital_life.application.monitoring.management import Management
        with self.boundary():
            row=self.s.row('activities',key);origin=ref(self.s,row['trigger_event_id'],'perception_signals');self.qualify(origin)
            signal=self.s.row('perception_signals',origin['id']);body=self.material(origin,signal['artifact_id'])['value']
            result={name:row[name] for name in ('id','state','recorded_at','revision','deadline','cancel_requested_at')};result['task']=body.get('text','原生观察学习活动') if type(body) is dict else '历史活动'
            result['thoughts']=[dict(value) for value in self.s.db.execute('SELECT id,state,recorded_at,purpose,accepted_result_id FROM thought_requests WHERE instance_id=? AND activity_id=? ORDER BY rowid DESC LIMIT 50',(self.s.instance_id,key))];responses=[];roots=[origin]
            for request in result['thoughts']:
                response={'request_id':request['id'],'recorded_at':request['recorded_at'],'state':request['state'],'reply':None,'waiting_reason':None,'error_code':None}
                if request['accepted_result_id']:
                    try:
                        output=self.s.row('thought_results',request['accepted_result_id']);root=ref(self.s,output['id'],'thought_results');value=self.material(root,output['parsed_artifact_id'])['value'];roots.append(root)
                        response['reply']=value.get('explanation');response['recorded_at']=output['received_at']
                        action=value.get('action',{})
                        if action.get('tool') in ('wait','ask'):response['waiting_reason']=action['arguments']['reason']
                    except (Forbidden,Conflict,ContractError):response['unavailable']=True
                attempt=self.s.db.execute('SELECT error_code FROM thought_attempts WHERE instance_id=? AND request_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,request['id'])).fetchone()
                if attempt:response['error_code']=attempt[0]
                responses.append(response)
            result['responses']=responses;result['steps']=[dict(r) for r in self.s.db.execute('SELECT step_no,step_type,state,started_at,finished_at FROM activity_steps WHERE instance_id=? AND activity_id=? ORDER BY step_no LIMIT 100',(self.s.instance_id,key))]
            result['transitions']=[dict(r) for r in self.s.db.execute('SELECT recorded_at,from_state,to_state,reason_code FROM activity_state_events WHERE instance_id=? AND activity_id=? ORDER BY transition_no LIMIT 100',(self.s.instance_id,key))]
            result['approvals']=self.approvals({'activity_id':key})['items'];result['can_cancel']=row['state'] not in ('completed','failed','cancelled')
            for root in roots:self.qualify(root,'controller_activity_return')
            return Management(self.s).scrub(result)
    def activities(self,query):
        from digital_life.application.monitoring.management import Management,integer,ACTIVITY_STATES
        with self.boundary():
            limit=integer(query.get('limit'),20,1,100);cursor=integer(query.get('cursor'));state=query.get('state');clauses=['instance_id=?'];params=[self.s.instance_id]
            if state:
                if state not in ACTIVITY_STATES:raise ContractError('invalid activity state')
                clauses.append('state=?');params.append(state)
            if cursor is not None:clauses.append('rowid<?');params.append(cursor)
            rows=self.s.db.execute('SELECT rowid AS position,id,trigger_event_id,state,recorded_at,revision,deadline,cancel_requested_at FROM activities WHERE '+' AND '.join(clauses)+' ORDER BY rowid DESC LIMIT ?',(*params,limit+1)).fetchall();items=[]
            for raw in rows[:limit]:
                row=dict(raw);origin=ref(self.s,row['trigger_event_id'],'perception_signals')
                try:
                    self.qualify(origin);signal=self.s.row('perception_signals',origin['id']);body=self.material(origin,signal['artifact_id'])['value']
                except (Forbidden,Conflict,ContractError):continue
                task=body.get('text','原生观察学习活动') if type(body) is dict else '历史活动'
                if query.get('q') and query['q'].casefold() not in (task+row['id']).casefold():continue
                row.pop('trigger_event_id');row.pop('position');row.update(task=task[:320],can_cancel=row['state'] not in ('completed','failed','cancelled'))
                items.append(row)
            return Management(self.s).scrub({'items':items,'limit':limit,'next_cursor':str(rows[limit-1]['position']) if len(rows)>limit else None,'has_more':len(rows)>limit,'coverage':'bounded page of operational metadata; material checked before reading'})
    def approvals(self,query):
        from digital_life.application.monitoring.management import Management,integer
        with self.boundary():
            limit=integer(query.get('limit'),20,1,100);rows=self.s.db.execute('SELECT id,action_ref FROM approval_requests WHERE instance_id=? ORDER BY rowid DESC LIMIT ?',(self.s.instance_id,limit)).fetchall();items=[];roots=[]
            management=Management(self.s)
            for row in rows:
                try:root=self.action(row['action_ref'])
                except (Forbidden,Conflict,ContractError):continue
                value=management.approval(row['id'])
                if query.get('activity_id') and value.get('activity_id')!=query['activity_id']:continue
                if query.get('status') and value.get('status')!=query['status']:continue
                items.append(value);roots.append(root)
            for root in roots:self.qualify(root,'controller_approvals_return')
            return {'items':items,'limit':limit,'next_cursor':None,'has_more':False,'coverage':'bounded current authorized approvals'}
    def model(self):
        from digital_life.application.monitoring.management import Management
        with self.boundary():
            row=Management(self.s).config_row();origin=ref(self.s,row['id'],'configuration_versions');self.qualify(origin)
            result=Management(self.s).model();self.qualify(origin,'controller_model_return');return result
    def health(self):
        from digital_life.application.monitoring.management import HEALTH_DIMENSIONS
        from digital_life.application.learning.health import CurrentHealthEvidence
        with self.boundary():
            evidence=CurrentHealthEvidence(self.s,None,None);probes=evidence.probes
            dimensions={name:{'state':'unknown','reason':'该维度没有在本次只读检查中确认。'} for name in HEALTH_DIMENSIONS}
            integrity=probes['F.sqlite_integrity'];dimensions['storage']={'state':'unknown' if integrity['status']!='known' else 'healthy' if integrity['value']==1 else 'critical','reason':'当前实际SQLite完整性与外键检查。'}
            return {'state':'unknown','dimensions':dimensions,'checked_at':evidence.at,'stale':False,'ttl_seconds':30,'current_probes':probes,'read_only':True}
    def logs(self,query,detail=None):
        from digital_life.application.monitoring.management import Management
        with self.boundary():
            management=Management(self.s)
            if detail is not None:
                row=self.s.db.execute('SELECT * FROM runtime_events WHERE instance_id=? AND event_seq=?',(self.s.instance_id,detail)).fetchone()
                if row is None:raise ContractError('historical log unavailable')
                origin=ref(self.s,row['id'],'runtime_events');self.qualify(origin)
                result={key:row[key] for key in ('id','event_seq','event_type','recorded_at','source','activity_id','lane')}
                result['payload']=self.material(origin,row['payload_artifact_id'])['value'] if row['payload_artifact_id'] else {'available':False}
                self.qualify(origin,'controller_log_return');return management.scrub(result,private=True)
            result=management.logs(query);visible=[]
            for row in result['items']:
                try:self.qualify(ref(self.s,row['id'],'runtime_events'))
                except (Forbidden,Conflict,ContractError):continue
                visible.append(row)
            result['items']=visible;return result
    def overview(self):
        from digital_life.application.monitoring.management import Management
        with self.boundary():
            management=Management(self.s);control=management.control();locked=(self.s.root/'WAKE_DISABLED').exists();restore=(self.s.root/'RESTORE_RECONCILIATION_REQUIRED').exists()
            counts={row['state']:row['n'] for row in self.s.db.execute('SELECT state,count(*) n FROM activities WHERE instance_id=? GROUP BY state',(self.s.instance_id,))};health=self.health()
            return {'instance_id':self.s.instance_id,'name':self.s.config().get('name','原初00'),'wake_disabled':locked,'restore_reconciliation_required':restore,'runtime_status':'locked' if locked or restore else 'stopped' if control['user_stopped'] else 'registered' if control['active_process_run_id'] else 'idle','control':control,'activity_counts':counts,'active_activities':sum(n for key,n in counts.items() if key not in ('completed','failed','cancelled')),'pending_approvals':len(self.approvals({'status':'pending'})['items']),'model':self.model(),'health':{'state':health['state'],'stale':health['stale'],'checked_at':health['checked_at']},'recent_events':self.logs({'limit':5})['items'],'read_only':True}
