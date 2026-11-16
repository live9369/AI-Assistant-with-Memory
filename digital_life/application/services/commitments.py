"""Commitments application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Commitments:
    def __init__(self,store): self.s=store
    def propose(self,creditor,content,due):
        from digital_life.application.services.goals import Goals
        with self.s.tx():
            rule=Goals(self.s).rule()
            # Consequent is data-specific, not a universal true rule.
            success=self.s.insert('rule_definitions',name='commitment:'+identifier(),version=1,expression_json={'op':'eq','left':{'var':'verified'},'right':True},engine_version='rules-v1')
            ref=self.s.insert('commitment_items',debtor_actor_id=self.s.config()['self_actor'],creditor_actor_id=creditor,kind='achievement',antecedent_rule=rule,consequent_rule=success,state='proposed',due_at=due)
            self.s.event('commitment.proposed',payload={'commitment':ref,'content':text(content)},lane='control')
        return ref
    def transition(self,ref,target,event,evidence=None):
        with self.s.tx():
            row=self.s.row('commitment_items',ref)
            if target=='fulfilled':
                from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
                if not evidence or not AutonomyAgenda(self.s).fulfillment_allowed(ref,evidence):raise ContractError('fulfillment needs verified evidence')
            transition=self.s.insert('commitment_transitions',commitment_id=ref,from_state=row['state'],to_state=target,event_id=event,reason=dumps({'evidence':evidence}),transition_no=row['state_revision']+1)
            if target=='active':
                from digital_life.application.runtime.scheduling import Queue
                Queue(self.s).enqueue('commitment_due',ref,row['due_at'])
            return transition

