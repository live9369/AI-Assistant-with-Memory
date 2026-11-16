"""Habits application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Habits:
    def __init__(self,store): self.s=store
    def create(self,response,rule):
        with self.s.tx():
            habit=self.s.insert('habit_items',response_template=response,state='learning')
            cue=self.s.insert('habit_cues',habit_id=habit,context_rule_id=rule,match_method='rules-v1')
            assoc=self.s.insert('habit_associations',habit_id=habit,cue_id=cue,strength=0.,uncertainty_json={'status':'unmeasured'},learning_version='ema-v1')
        return assoc
    def opportunities(self,activity,variables):
        from digital_life.domain.rules import Rules
        from digital_life.application.behavior.habit_learning import HabitLearning
        learning=HabitLearning(self.s);managed={r['cue_id'] for r in learning.registry().values()}
        results=[]
        with self.s.tx():
            for cue in self.s.rows('habit_cues'):
                from digital_life.application.accounts.account_scope import source_allowed
                if not source_allowed(self.s,cue['id']):continue
                if cue['id'] in managed or self.s.row('habit_items',cue['habit_id'])['state'] in ('inhibited','extinct'):continue
                rule=json.loads(self.s.row('rule_definitions',cue['context_rule_id'])['expression_json'])
                match=Rules().evaluate(rule,variables)
                if match is not True: continue
                ref=self.s.insert('habit_opportunities',cue_id=cue['id'],activity_id=activity,match_score=1.,action_taken=0,control_mode='unknown')
                association=self.s.db.execute('SELECT * FROM habit_associations WHERE cue_id=?',(cue['id'],)).fetchone()
                results.append({'opportunity':ref,'habit':cue['habit_id'],'strength':association['strength']})
            results.extend(learning.opportunities(activity))
        return results
    def update(self,association,outcome,evidence,actor,rate=0.1):
        if actor!=self.s.config()['controller']: raise Forbidden('habit learning requires approved feedback')
        from digital_life.application.behavior.habit_learning import HabitLearning
        if association in HabitLearning(self.s).registry():raise Forbidden('managed habit requires reviewed habit-learning feedback')
        target=probability(outcome); rate=probability(rate)
        with self.s.tx():
            row=self.s.row('habit_associations',association); self.s.row('evidence_items',evidence)
            value=row['strength']+rate*(target-row['strength'])
            self.s.db.execute('UPDATE habit_associations SET strength=? WHERE id=?',(value,association))
            self.s.event('habit.updated',payload={'association':association,'before':row['strength'],'after':value,'evidence':evidence},lane='work')
            return value

