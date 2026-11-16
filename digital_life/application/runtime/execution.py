"""Explicit workspace tool adapter."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from digital_life.domain.contracts import utc,identifier,dumps,sha,validate_action,Forbidden,Conflict,ContractError,ToolResult
from digital_life.application.accounts.authorization import Policy
from digital_life.application.autonomy.exploration import Exploration
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.infrastructure.tools.workspace import registry
class Executor:
    def __init__(self,store,identity): self.s=store; self.identity=identity
    def dispatch(self,intent_id,backend=None):
        from digital_life.application.learning.runtime import qualified_plane_required
        if qualified_plane_required(self.s):
            from digital_life.application.learning.execution import StrictActionExecutor
            return StrictActionExecutor(self.s,self.identity).dispatch(intent_id,backend)
        from digital_life.application.learning.runtime import strict_legacy_boundary
        strict_legacy_boundary(self.s,'legacy_actual_tool_dispatch')
        self.s.assert_execution_allowed()
        with self.s.tx():
            intent=self.s.row('action_intents',intent_id)
            if intent['state']=='succeeded': return {'duplicate':True}
            box=self.s.db.execute('SELECT * FROM outbox WHERE intent_id=?',(intent_id,)).fetchone()
            if not box: raise Forbidden('action not queued')
            auth=Policy(self.s).check(intent,box['authorization_record_id'])
            token=secrets.token_urlsafe(32); attempt_no=self.s.db.execute('SELECT count(*)+1 FROM action_attempts WHERE intent_id=?',(intent_id,)).fetchone()[0]
            if attempt_no>3: raise ContractError('execution attempt budget exhausted')
            attempt=self.s.insert('action_attempts',intent_id=intent_id,attempt_no=attempt_no,started_at=utc(),runner_ref='bounded-worker-v1',state='running',authorization_record_id=auth['id'],policy_epoch=Policy(self.s).epoch(),execution_token_hash=sha(token),arguments_hash=intent['arguments_hash'],start_gate_at=utc(),runtime_epoch=self.identity.epoch,process_run_id=self.identity.process_id)
            from digital_life.application.runtime.scheduling import Budget
            reservation=Budget(self.s).reserve(self.activity_for(intent),'%s'%attempt,'tool_attempt')
            self.s.db.execute("UPDATE action_authorization_records SET state='consumed' WHERE id=?",(auth['id'],))
            self.s.db.execute("UPDATE action_intents SET state='running',lifecycle_revision=lifecycle_revision+1 WHERE id=?",(intent_id,))
            self.s.db.execute("UPDATE outbox SET dispatch_state='sent' WHERE id=?",(box['id'],))
            tool=self.s.row('tool_definitions',intent['tool_id'])
            action={'tool':tool['name'],'arguments':json.loads(intent['arguments_json'])}
        dispatched=False
        try:
            with dispatch_gate(self.s.root):
                self.s.assert_execution_allowed()
                current=self.s.row('action_intents',intent_id)
                activity=self.s.row('activities',self.activity_for(current))
                if activity['cancel_requested_at'] or activity['state'] in ('completed','failed','cancelled'): raise Forbidden('activity no longer dispatchable')
                Policy(self.s).check(current,box['authorization_record_id'],attempt=attempt)
                exploration=Exploration(self.s); binding=exploration.binding(activity['id'])
                if binding:
                    cfg=exploration.config()
                    if not cfg['enabled'] or cfg['generation']!=binding['generation']: raise Forbidden('exploration dispatch superseded')
                dispatched=True
                from digital_life.domain.project_files import NAMES
                project=action['tool'] in NAMES
                if project and backend:raise Forbidden('project file actions require the native worker')
                if backend: result=backend(action,self.s.root/'workspace',intent['idempotency_key'])
                else:
                    env={'PATH':os.environ.get('PATH',''),'PYTHONDONTWRITEBYTECODE':'1'}
                    proc=subprocess.run([sys.executable,'-m','digital_life.entrypoints.worker'],input=dumps({'root':str(self.s.root/'workspace'),'action':action,'operation':intent['idempotency_key'],**({'project_scope':json.loads(intent['resource_scope']),'journal':str(self.s.root/'project-operations')} if project else {})}),capture_output=True,text=True,timeout=30,cwd=str(__import__('digital_life.infrastructure.persistence.sqlite_store',fromlist=['PROJECT']).PROJECT),env=env)
                    if proc.returncode or len(proc.stdout)>131072: raise ContractError('runner failed or output limit exceeded')
                    result=ToolResult(**json.loads(proc.stdout))
        except Exception as error:
            if not dispatched:
                with self.s.tx():
                    self.s.db.execute("UPDATE action_attempts SET state='failed',finished_at=? WHERE id=?",(utc(),attempt))
                    self.s.db.execute("UPDATE action_intents SET state='cancelled',lifecycle_revision=lifecycle_revision+1 WHERE id=?",(intent_id,))
                    self.s.db.execute("UPDATE outbox SET dispatch_state='cancelled' WHERE id=?",(box['id'],))
                    Budget(self.s).settle(reservation,usage={'tool_calls':0,'dispatched':False})
                    self.s.event('action.dispatch_blocked',payload={'intent':intent_id,'attempt':attempt,'reason':type(error).__name__},activity=self.activity_for(intent),lane='control')
                raise
            result=ToolResult('timeout','unknown','unknown',{},str(error)[:1024])
        with self.s.tx():
            receipt=self.s.artifact({'transport':result.transport_state,'execution':result.execution_state,'verification':result.verification_state,'evidence':result.evidence,'error':result.error})
            evidence=self.s.evidence(artifact=receipt,method='tool-verification')
            state='succeeded' if result.execution_state=='succeeded' and result.verification_state=='pass' else 'failed' if result.execution_state=='failed' else 'unknown'
            result_ref=self.s.insert('action_results',attempt_id=attempt,state=state,receipt_artifact_id=receipt,outcome_ref=evidence,error_type=result.error or None)
            self.s.insert('action_verifications',intent_id=intent_id,method_version='bounded-tool-v1',result=result.verification_state,evidence_id=evidence)
            self.s.db.execute('UPDATE action_attempts SET state=?,finished_at=? WHERE id=?',(state,utc(),attempt))
            self.s.db.execute('UPDATE action_intents SET state=?,lifecycle_revision=lifecycle_revision+1 WHERE id=?',(state,intent_id))
            self.s.db.execute('UPDATE outbox SET dispatch_state=? WHERE id=?',('completed' if state=='succeeded' else 'unknown',box['id']))
            from digital_life.application.runtime.scheduling import Budget
            Budget(self.s).settle(reservation,usage={'tool_calls':1},unknown=state=='unknown')
            event=self.s.event('action.result',payload={'intent':intent_id,'attempt':attempt,'state':state,'evidence':evidence},activity=self.activity_for(intent),lane='result')
        return {'state':state,'evidence':evidence,'event':event,'receipt':receipt,'result':result_ref}
    def activity_for(self,intent):
        candidate=self.s.row('decision_candidates',intent['candidate_id'])
        return self.s.row('decision_records',candidate['decision_id'])['activity_id']


