"""Explicit CLI-owned source update lifecycle; never called by a model tool."""
from digital_life.domain.contracts import ContractError, Conflict, Forbidden, identifier
from digital_life.application.lifecycle.control_plane import Releases
from digital_life.application.lifecycle.source_updates import SourceUpdates
from digital_life.application.lifecycle.deployment import Deployment


class MaintenancePipeline:
    def __init__(self, store, control, manager=None):
        self.s=store; self.c=control; self.u=SourceUpdates(store)
        self.manager=manager or Deployment(control)

    def preflight(self, proposal):
        p=self.u.proposal(proposal)
        if not self.u.m.config()['enabled']: raise Forbidden('maintenance disabled')
        active=self.u.active()
        if not active or active['id']!=p['base_deployment']: raise Conflict('update baseline is no longer active')
        for name in ('WAKE_DISABLED','RESTORE_RECONCILIATION_REQUIRED','MODEL_USAGE_REVIEW_REQUIRED'):
            if (self.s.root/name).exists() or (self.s.root/name).is_symlink(): raise Forbidden('update blocked by '+name)
        if self.s.db.execute("SELECT 1 FROM jobs WHERE instance_id=? AND state IN ('queued','leased') LIMIT 1",(self.s.instance_id,)).fetchone(): raise Conflict('pending work; finish or explicitly cancel before update')
        return {'proposal':proposal,'base_deployment':p['base_deployment'],'files':list(p['changes']),
                'scope':'execute candidate code only by explicit CLI; temporary probe is not an OS sandbox'}

    def owned_stop(self, stop_command):
        state=self.c.state()
        return state['user_stopped'] and not state['active_process_run_id'] and state['last_stop_command_id']==stop_command

    def execute(self, proposal, stop_command, timeout=30):
        p=self.u.proposal(proposal); base=p['base_deployment']; actor=self.s.config()['controller']
        result={'proposal':proposal,'base_deployment':base,'updated':False,'stage':'build'}
        try:
            self.preflight(proposal)
            if not self.owned_stop(stop_command): raise Conflict('update stop superseded')
            built=self.u.build(proposal,actor);result['deployment']=built['deployment'];result['stage']='validate'
            proof=self.u.validate(proposal,actor,timeout)
            result['validation']=proof['id']
            if not proof['passed']: raise ContractError('candidate business probe failed: '+proof.get('reason',proof.get('error','unknown')))
            result['stage']='deploy'
            self.c.resume(identifier(),expected_stop=stop_command)
            outcome=self.manager.launch(built['deployment'])
            result.update(updated=outcome.get('switched') is True, outcome=outcome, stage='running' if outcome.get('switched') else 'deployment-failed')
        except (ContractError,OSError,ValueError,SyntaxError) as error:
            result.update(error=type(error).__name__,reason=str(error)[:300])
            # Restore only our own maintenance stop; a new user stop always wins.
            active=self.u.active()
            if self.owned_stop(stop_command) and active and active['id']==base and Releases(self.c).recoverable(base):
                try:
                    self.c.resume(identifier(),expected_stop=stop_command)
                    recovery=self.manager.launch(base,_recover=False)
                    result.update(recovery=recovery,restored=recovery.get('switched') is True)
                except (ContractError,OSError,ValueError) as recovery_error:
                    result['recovery_error']=type(recovery_error).__name__
            else: result['restored']=False
        with self.s.tx(): self.u.emit('pipeline_result',result)
        return result
