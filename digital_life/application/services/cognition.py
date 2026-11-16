"""Cognition application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Cognition:
    def __init__(self,store): self.s=store
    def belief(self,subject,predicate,literal,evidence):
        with self.s.tx():
            belief=self.s.insert('cognition_beliefs',subject_ref=subject,predicate=predicate,literal=literal,scope={})
            revision=self.s.insert('cognition_belief_revisions',belief_id=belief,revision_no=1,content=dumps(literal),acceptance_state='held',uncertainty_json={'status':'uncalibrated'},method_version='explicit-v1')
            self.s.insert('cognition_evidence_links',target_revision_id=revision,evidence_id=evidence,stance='support',strength_method='explicit-v1',assessment={'not_verified':True})
            self.s.db.execute('UPDATE cognition_beliefs SET current_revision_id=? WHERE id=?',(revision,belief))
        return belief
    def episode(self,activity,context,question):
        return self.s.insert('cognition_episodes',activity_id=activity,question=text(question),context_id=context,method_version='independent-model-v1',state='open')
    def hypothesize(self,episode,content,uncertainty):
        with self.s.tx(): return self.s.insert('cognition_hypotheses',episode_id=episode,content=text(content),state='open',uncertainty_json=uncertainty)
    def predict(self,episode,target,outcome,chance,due,rule):
        with self.s.tx(): return self.s.insert('cognition_predictions',episode_id=episode,target_ref=target,predicted_outcome=outcome,probability_kind='outcome',probability=probability(chance),due_at=due,verification_rule=rule)
    def plan(self,goal,steps):
        from digital_life.application.services.goals import Goals
        if not isinstance(steps,list) or not 1<=len(steps)<=32: raise ContractError('plan must have 1-32 steps')
        with self.s.tx():
            previous=self.s.db.execute('SELECT * FROM cognition_plans WHERE goal_id=? ORDER BY version DESC LIMIT 1',(goal,)).fetchone()
            plan=self.s.insert('cognition_plans',goal_id=goal,version=previous['version']+1 if previous else 0,state='draft',previous_plan_id=previous['id'] if previous else None)
            refs=[]
            for n,step in enumerate(steps):
                ref=self.s.insert('cognition_plan_steps',plan_id=plan,step_no=n,action_template=step['action'],preconditions=Goals(self.s).rule(),expected_outcome=step.get('expected',{})); refs.append(ref)
                for dependency in step.get('depends_on',[]):
                    if type(dependency) is not int or not 0<=dependency<n: raise ContractError('plan dependency must reference preceding step')
                    self.s.insert('cognition_plan_dependencies',step_id=ref,depends_on_step_id=refs[dependency],condition=Goals(self.s).rule('completed'))
            return {'plan':plan,'steps':refs}


    def experience_revision(self,cell):
        from digital_life.application.cognition.cognition_experience import CognitiveExperience
        return CognitiveExperience(self.s).current_revision(cell)
    def save_experience(self,proposal_ref,expected_revision):
        from digital_life.application.cognition.cognition_experience import CognitiveExperience
        return CognitiveExperience(self.s).save(proposal_ref,expected_revision)
    def experience_snapshot(self,actor):
        from digital_life.application.cognition.cognition_experience import CognitiveExperience
        return CognitiveExperience(self.s).snapshot(actor)
