"""Goals application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Goals:
    def __init__(self,store): self.s=store
    def rule(self,name='always'): return next(r['id'] for r in self.s.rows('rule_definitions') if r['name']==name)
    def create(self,source,content):
        return self.s.insert('goal_items',source_ref=source,content=text(content),state='candidate',success_rule=self.rule('completed'),stop_rule=self.rule())
    def transition(self,goal,target,event,reason='explicit'):
        with self.s.tx():
            row=self.s.row('goal_items',goal)
            return self.s.insert('goal_transitions',goal_id=goal,from_state=row['state'],to_state=target,event_id=event,reason=reason,transition_no=row['state_revision']+1)
    def motivate(self,goal,activity,intensity=0.5,internal=False):
        return self.s.insert('motivation_states',goal_id=goal,activity_id=activity,intensity=probability(intensity),source_type='knowledge-gap' if internal else 'explicit-task',regulation_type='internal' if internal else 'external',persistence=0.5,satiation=0,budget={'tool_calls':1})

