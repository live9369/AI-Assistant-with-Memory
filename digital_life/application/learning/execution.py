"""Strict ordinary action callback: original account and actual source gate.

The tool grant and source-use permission are separate requirements. A timeout
after entry records an unknown side effect; it never retries that operation.
"""
from copy import deepcopy
from dataclasses import asdict
import math
import secrets
import time
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,ToolResult,dumps,sha,utc
from digital_life.domain import tool_learning_contract as c
from digital_life.application.accounts.authorization import Policy
from digital_life.application.learning.budget import DIMENSIONS
from digital_life.application.learning.eligibility import ref
from digital_life.application.learning.engine import StrictEngine,source_scope,_dependency
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.infrastructure.llm.fresh_learning import supervised
from digital_life.infrastructure.tools.workspace import registry


class StrictActionExecutor:
    def __init__(self,store,identity,kernel=None):
        self.s=store;self.identity=identity;self.k=kernel or StrictEngine(store,identity)
    def activity_for(self,intent):
        candidate=self.s.row('decision_candidates',intent['candidate_id'])
        return self.s.row('decision_records',candidate['decision_id'])['activity_id']
    def dispatch(self,intent_id,backend=None):
        self.k.owners.control()
        entry,principal=self.k.owners.entry('M14','learn',self.s.config()['controller'])
        intent=self.s.row('action_intents',intent_id);activity=self.activity_for(intent)
        self.k._caps(activity)
        if intent['state']=='succeeded':return {'duplicate':True}
        if intent['state'] in ('running','unknown'):raise Conflict('entered action requires explicit reconciliation, never automatic retry')
        box=self.s.db.execute('SELECT * FROM outbox WHERE instance_id=? AND intent_id=?',(self.s.instance_id,intent_id)).fetchone()
        if box is None or box['dispatch_state']!='pending':raise Forbidden('action has no pending authorized outbox')
        # An action from an untracked legacy decision cannot enter the strict
        # executor merely because it acquired a tool approval.
        ancestry=self.s.db.execute("SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? AND relation='read' AND field_path='/model_derivation' LIMIT 2",(self.s.instance_id,intent_id)).fetchall()
        if len(ancestry)!=1:raise Forbidden('action has no exact complete producer lineage')
        metadata=self.k.runtime.eligibility._metadata(ancestry[0]);token=deepcopy(metadata['dependency']['expected']);scope=deepcopy(metadata['scope'])
        if token['object']['kind']!='thought_results':raise Forbidden('ordinary planned action must bind its actual accepted thought result')
        thought=self.s.row('thought_results',token['object']['id']);request=self.s.row('thought_requests',thought['request_id'])
        if thought['acceptance']!='accepted' or request['accepted_result_id']!=thought['id'] or request['activity_id']!=activity:raise Forbidden('action producer was not the accepted result of this activity')
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE instance_id=? AND activity_id=? ORDER BY rowid LIMIT 1',(self.s.instance_id,activity)).fetchone()
        if context is None:raise Forbidden('action context missing')
        scope_token=deepcopy(token);attempt=None;reservation=None;entered=False;usage=None
        with self.k._read_operation(entry,activity,context[0],'tool-entry-and-retention',self.k._read_slice(activity,.5)) as meter,dispatch_gate(self.s.root):
            self.k.runtime.eligibility.check(entry,principal,token,scope,'learn',principal['recipient'],'tool_prepare')
            with self.s.tx():
                current=self.s.row('action_intents',intent_id);auth=Policy(self.s).check(current,box['authorization_record_id'])
                number=self.s.db.execute('SELECT count(*)+1 FROM action_attempts WHERE instance_id=? AND intent_id=?',(self.s.instance_id,intent_id)).fetchone()[0]
                attempt=self.s.insert('action_attempts',intent_id=intent_id,attempt_no=number,started_at=utc(),runner_ref='strict-managed-tool-v1',state='running',authorization_record_id=auth['id'],policy_epoch=Policy(self.s).epoch(),execution_token_hash=sha(secrets.token_urlsafe(32)),arguments_hash=current['arguments_hash'],start_gate_at=utc(),runtime_epoch=self.identity.epoch,process_run_id=self.identity.process_id)
            remaining=self.k.budget.check_activity(activity)['remaining'];amounts={key:0 for key in DIMENSIONS}
            amounts.update(attempts=1,tool_calls=1,bytes=min(131072,remaining['bytes']),elapsed_ms=min(30000,remaining['elapsed_ms']))
            try:reservation=self.k.budget.reserve(entry,activity,ref(self.s,attempt),'tool_attempt',amounts,request_budget=self.k._caps(activity),reservation_key='strict-tool:'+attempt)
            except BaseException:
                with self.s.tx():self.s.db.execute("UPDATE action_attempts SET state='failed',finished_at=? WHERE instance_id=? AND id=?",(utc(),self.s.instance_id,attempt))
                raise
            bound={'arguments_hash':intent['arguments_hash'],'proposal_revision':intent['proposal_revision'],'tool_id':intent['tool_id'],'authorization':box['authorization_record_id']}
            def guard(consumed=False):
                self.k.owners.control();row=self.s.row('action_intents',intent_id);actual=self.s.row('activities',activity)
                if any(row[k]!=bound[k] for k in ('arguments_hash','proposal_revision','tool_id')) or sha(row['arguments_json'])!=bound['arguments_hash']:raise Conflict('actual tool arguments changed')
                if actual['cancel_requested_at'] or actual['state'] in ('completed','failed','cancelled') or actual['deadline']<=utc():raise Forbidden('actual tool activity is no longer executable')
                Policy(self.s).check(row,bound['authorization'],attempt=attempt if consumed else None)
            def invoke():
                nonlocal entered,usage
                guard()
                self.k._current_health(activity,ref(self.s,intent_id),token,scope,'immediately_before_actual_tool')
                guard()
                self.k.budget.record_entry(entry,activity,reservation['id'],{'contract':'TL-ENGINE-TOOL-ENTRY-1','operation':ref(self.s,attempt)})
                with self.s.tx():
                    self.s.db.execute("UPDATE action_authorization_records SET state='consumed' WHERE instance_id=? AND id=?",(self.s.instance_id,bound['authorization']))
                    self.s.db.execute("UPDATE action_intents SET state='running',lifecycle_revision=lifecycle_revision+1 WHERE instance_id=? AND id=?",(self.s.instance_id,intent_id))
                    self.s.db.execute("UPDATE outbox SET dispatch_state='sent' WHERE instance_id=? AND id=?",(self.s.instance_id,box['id']))
                    self.s.db.execute("UPDATE activities SET state='running',revision=revision+1 WHERE instance_id=? AND id=?",(self.s.instance_id,activity))
                guard(True)
                action={'tool':self.s.row('tool_definitions',bound['tool_id'])['name'],'arguments':c.loads(self.s.row('action_intents',intent_id)['arguments_json'])}
                wire_size=len(dumps(action).encode())
                if wire_size>reservation['reserved']['bytes']:raise Forbidden('tool input exceeds original byte opportunity')
                entered=True;started=time.monotonic()
                def call():
                    result=(backend(action,self.s.root/'workspace',intent['idempotency_key']) if backend else registry().invoke(action,self.s.root/'workspace',intent['idempotency_key']))
                    if not isinstance(result,ToolResult):raise ContractError('typed tool result required')
                    return asdict(result)
                try:
                    with meter.excluding_child():raw=supervised(call,reservation['reserved']['elapsed_ms']/1000,reservation['reserved']['bytes'])
                    usage={key:0 for key in DIMENSIONS};usage.update(attempts=1,tool_calls=1,bytes=wire_size+len(dumps(raw).encode()),elapsed_ms=math.ceil((time.monotonic()-started)*1000))
                    return raw
                except BaseException:
                    # The callback entered. Cancellation of our local worker
                    # does not prove whether an external effect occurred.
                    usage=None;raise
            try:
                raw=self.k.runtime.eligibility.callback(entry,principal,scope_token,scope,'learn',principal['recipient'],invoke,request=ref(self.s,intent_id))
                guard(True)
                self.k.runtime.eligibility.check(entry,principal,token,scope,'learn',principal['recipient'],'tool_result_retention')
                self.k._settle(entry,activity,reservation,usage)
                if usage is None or any(reason!='attempts_exhausted' for reason in self.k.budget.check_activity(activity)['block_reasons']):raise Forbidden('tool actual usage does not allow result publication')
                with self.s.tx():
                    guard(True)
                    receipt=self.s.artifact({'transport':raw['transport_state'],'execution':raw['execution_state'],'verification':raw['verification_state'],'evidence':raw['evidence'],'error':raw['error']});evidence=self.s.evidence(artifact=receipt,method='strict-tool-verification')
                    state='succeeded' if raw['execution_state']=='succeeded' and raw['verification_state']=='pass' else 'failed' if raw['execution_state']=='failed' else 'unknown'
                    result=self.s.insert('action_results',attempt_id=attempt,state=state,receipt_artifact_id=receipt,outcome_ref=evidence,error_type=None)
                    self.s.insert('action_verifications',intent_id=intent_id,method_version='strict-managed-tool-v1',result=raw['verification_state'],evidence_id=evidence)
                    for consumer in (ref(self.s,result),ref(self.s,receipt),ref(self.s,evidence)):
                        for relation in ('read','delete'):_dependency(self.s,consumer,token,scope,relation,'/actual_tool_input','learn')
                    self.s.db.execute('UPDATE action_attempts SET state=?,finished_at=? WHERE instance_id=? AND id=?',(state,utc(),self.s.instance_id,attempt))
                    self.s.db.execute('UPDATE action_intents SET state=?,lifecycle_revision=lifecycle_revision+1 WHERE instance_id=? AND id=?',(state,self.s.instance_id,intent_id))
                    self.s.db.execute('UPDATE outbox SET dispatch_state=? WHERE instance_id=? AND id=?',('completed' if state=='succeeded' else 'unknown',self.s.instance_id,box['id']))
                    event=self.s.event('action.result',payload={'intent':intent_id,'attempt':attempt,'state':state,'evidence':evidence},activity=activity,lane='result')
                    for relation in ('read','delete'):_dependency(self.s,ref(self.s,event),token,scope,relation,'/actual_tool_input','learn')
                return {'state':state,'evidence':evidence,'event':event,'receipt':receipt,'result':result}
            except BaseException as error:
                state=self.k.budget._load(activity)[3]['ledger']['reservations'][reservation['id']]['state']
                if state not in ('settled','released'):self.k._settle(entry,activity,reservation,usage if entered else {key:0 for key in DIMENSIONS})
                with self.s.tx():
                    self.s.db.execute('UPDATE action_attempts SET state=?,finished_at=? WHERE instance_id=? AND id=?',('unknown' if entered else 'failed',utc(),self.s.instance_id,attempt))
                    self.s.db.execute('UPDATE action_intents SET state=?,lifecycle_revision=lifecycle_revision+1 WHERE instance_id=? AND id=?',('unknown' if entered else 'cancelled',self.s.instance_id,intent_id))
                    self.s.db.execute('UPDATE outbox SET dispatch_state=? WHERE instance_id=? AND id=?',('unknown' if entered else 'cancelled',self.s.instance_id,box['id']))
                    self.s.event('strict.action.blocked',payload={'attempt':attempt,'entered':entered,'error_type':type(error).__name__},activity=activity,lane='control')
                raise
