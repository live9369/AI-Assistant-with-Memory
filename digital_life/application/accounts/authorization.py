"""Explicit workspace tool adapter."""
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate,coordinated
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from digital_life.domain.contracts import utc,identifier,dumps,sha,validate_action,Forbidden,Conflict,ContractError,ToolResult
from digital_life.infrastructure.tools.workspace import registry
class Policy:
    def __init__(self,store): self.s=store
    def epoch(self): return self.s.rows('policy_epochs')[0]['epoch']
    def tool(self,name):
        found=[r for r in self.s.rows('tool_definitions') if r['name']==name]
        if not found: raise Forbidden('unknown tool')
        return found[-1]
    def propose(self,activity,candidate,action):
        validate_action(action); tool=self.tool(action['tool'])
        from digital_life.domain.project_files import NAMES
        from digital_life.application.lifecycle.project_access import ProjectAccess
        resource=ProjectAccess(self.s).resource(action['tool']) if action['tool'] in NAMES else {'root':str(self.s.root/'workspace')}
        return self.s.insert('action_intents',candidate_id=candidate,tool_id=tool['id'],arguments_json=action['arguments'],idempotency_key=identifier(),verification_rule=self.s.rows('rule_definitions')[0]['id'],state='awaiting_approval',arguments_hash=sha(dumps(action['arguments'])),required_capability_id=tool['capability_id'],resource_scope=resource,deadline=utc(600))
    def request(self,intent):
        with self.s.tx():
            row=self.s.row('action_intents',intent)
            return self.s.insert('approval_requests',action_ref=intent,requested_scope=json.loads(row['resource_scope']),decision='pending',proposal_revision=row['proposal_revision'],arguments_hash=row['arguments_hash'],tool_id=row['tool_id'],required_capability_id=row['required_capability_id'],expires_at=utc(600),requested_by=self.s.config()['self_actor'])
    def reviewable(self,request,intent):
        if request['decision']!='pending' or request['expires_at']<=utc() or intent['state']!='awaiting_approval' or intent['deadline'] and intent['deadline']<=utc(): raise Conflict('approval no longer actionable')
        candidate=self.s.row('decision_candidates',intent['candidate_id']); decision=self.s.row('decision_records',candidate['decision_id'])
        activity=self.s.row('activities',decision['activity_id'])
        if activity['cancel_requested_at'] or activity['state'] in ('completed','failed','cancelled'): raise Conflict('activity no longer actionable')
    def approve(self,approval,actor):
        if actor!=self.s.config()['controller']: raise Forbidden('controller approval required')
        with self.s.tx():
            req=self.s.row('approval_requests',approval); intent=self.s.row('action_intents',req['action_ref'])
            self.reviewable(req,intent)
            if req['decision']!='pending' or req['expires_at']<=utc(): raise Conflict('approval no longer pending')
            if req['proposal_revision']!=intent['proposal_revision'] or req['arguments_hash']!=sha(intent['arguments_json']): raise Conflict('proposal changed')
            grant=self.s.insert('grants',subject=self.s.config()['self_actor'],capability=intent['required_capability_id'],resource_scope=json.loads(intent['resource_scope']),expiry=utc(300),version=0)
            token=secrets.token_urlsafe(32)
            authorization=self.s.insert('action_authorization_records',intent_id=intent['id'],grant_id=grant,approval_request_id=approval,proposal_revision=intent['proposal_revision'],arguments_hash=intent['arguments_hash'],scope_snapshot=json.loads(intent['resource_scope']),policy_epoch=self.epoch(),issued_at=utc(),expires_at=utc(300),state='valid')
            self.s.db.execute("UPDATE approval_requests SET decision='approved',decision_by=?,revision=revision+1 WHERE id=?",(actor,approval))
            self.s.db.execute("UPDATE action_intents SET grant_id=?,state='queued',lifecycle_revision=lifecycle_revision+1 WHERE id=?",(grant,intent['id']))
            outbox=self.s.insert('outbox',intent_id=intent['id'],dispatch_state='pending',next_attempt_at=utc(),authorization_record_id=authorization)
            from digital_life.application.runtime.scheduling import Queue
            Queue(self.s).enqueue('execute',intent['id'])
            self.s.event('action.approved',payload={'action':intent['id'],'approval':approval},lane='control')
        return {'action_id':intent['id'],'authorization':authorization,'outbox':outbox}
    def deny(self,approval,actor):
        if actor!=self.s.config()['controller']: raise Forbidden('controller required')
        with self.s.tx():
            req=self.s.row('approval_requests',approval)
            self.reviewable(req,self.s.row('action_intents',req['action_ref']))
            if req['decision']!='pending': raise Conflict('approval already decided')
            self.s.db.execute("UPDATE approval_requests SET decision='rejected',decision_by=?,revision=revision+1 WHERE id=?",(actor,approval))
            self.s.db.execute("UPDATE action_intents SET state='cancelled',lifecycle_revision=lifecycle_revision+1 WHERE id=?",(req['action_ref'],))
            self.s.event('action.denied',payload={'approval':approval,'action':req['action_ref']},lane='control')
            return {'decision':'rejected','action':req['action_ref']}
    @coordinated
    def mode(self,mode,tools,actor):
        if actor!=self.s.config()['controller']: raise Forbidden('controller required')
        if mode not in ('open','authorization') or not isinstance(tools,list) or set(tools)-set(registry().entries): raise ContractError('invalid policy mode or tools')
        with self.s.tx():
            active=self.s.rows('policy_epochs')[0];previous=self.s.row('policy_versions',active['policy_version_id'])
            scope=dict(json.loads(previous['scope']),root=str(self.s.root/'workspace'),tools=tools)
            number=self.s.db.execute('SELECT max(version)+1 FROM policy_versions WHERE instance_id=?',(self.s.instance_id,)).fetchone()[0]
            ref=self.s.insert('policy_versions',version=number,mode=mode,scope=scope,effective_at=utc(),authority=actor)
            self.s.db.execute('UPDATE policy_epochs SET epoch=epoch+1,policy_version_id=?,updated_at=? WHERE instance_id=?',(ref,utc(),self.s.instance_id))
            self.s.event('policy.changed',payload={'mode':mode,'tools':tools,'policy':ref},lane='control')
            return ref
    def maybe_approve_open_mode(self,approval):
        policy=self.s.row('policy_versions',self.s.rows('policy_epochs')[0]['policy_version_id'])
        req=self.s.row('approval_requests',approval); tool=self.s.row('tool_definitions',req['tool_id'])
        scope=json.loads(policy['scope'])
        from digital_life.domain.project_files import NAMES
        from digital_life.application.lifecycle.project_access import ProjectAccess
        if tool['name'] in NAMES:
            access=ProjectAccess(self.s);access.check(tool['name'],json.loads(self.s.row('action_intents',req['action_ref'])['resource_scope']))
            if access.config()['auto_approve']:return self.approve(approval,self.s.config()['controller'])
            return None
        if policy['mode']=='open' and tool['name'] in scope.get('tools',[]) and scope.get('root')==str(self.s.root/'workspace'):
            self.s.event('approval.by_open_policy',payload={'approval':approval,'policy':policy['id']},lane='control')
            return self.approve(approval,policy['authority'])
        return None
    def check(self,intent,authorization,attempt=None):
        auth=self.s.row('action_authorization_records',authorization); grant=self.s.row('grants',auth['grant_id'])
        consumed=False
        if attempt is not None:
            issued=self.s.row('action_attempts',attempt)
            consumed=auth['state']=='consumed' and issued['intent_id']==intent['id'] and issued['authorization_record_id']==authorization and issued['state']=='running' and intent['state']=='running'
        if auth['intent_id']!=intent['id'] or not (auth['state']=='valid' if attempt is None else consumed) or auth['expires_at']<=utc() or auth['revoked_at'] or grant['revoked_at'] or (grant['expiry'] and grant['expiry']<=utc()): raise Forbidden('authorization expired, consumed, or revoked')
        if auth['policy_epoch']!=self.epoch(): raise Forbidden('authorization policy changed')
        if intent['deadline'] and intent['deadline']<=utc(): raise Forbidden('action deadline expired')
        if intent['arguments_hash']!=sha(intent['arguments_json']) or auth['arguments_hash']!=intent['arguments_hash'] or auth['proposal_revision']!=intent['proposal_revision']: raise Forbidden('parameter mismatch')
        tool=self.s.row('tool_definitions',intent['tool_id'])
        if grant['capability']!=tool['capability_id']: raise Forbidden('capability mismatch')
        from digital_life.domain.project_files import NAMES
        if tool['name'] in NAMES:
            from digital_life.application.lifecycle.project_access import ProjectAccess
            resource=json.loads(intent['resource_scope']);ProjectAccess(self.s).check(tool['name'],resource)
            if json.loads(grant['resource_scope'])!=resource or json.loads(auth['scope_snapshot'])!=resource:raise Forbidden('project grant scope mismatch')
            return auth
        expected=str(self.s.root/'workspace')
        if json.loads(grant['resource_scope']).get('root')!=expected or json.loads(auth['scope_snapshot']).get('root')!=expected: raise Forbidden('workspace scope mismatch')
        return auth
    @coordinated
    def revoke(self,grant,actor):
        if actor!=self.s.config()['controller']: raise Forbidden('controller required')
        with self.s.tx():
            self.s.row('grants',grant)
            self.s.db.execute('UPDATE grants SET revoked_at=? WHERE id=?',(utc(),grant))
            self.s.db.execute('UPDATE policy_epochs SET epoch=epoch+1,updated_at=? WHERE instance_id=?',(utc(),self.s.instance_id))
            self.s.event('grant.revoked',payload={'grant_id':grant},lane='control')


