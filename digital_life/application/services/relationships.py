"""Relationships application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Relationships:
    def __init__(self,store): self.s=store
    def get_or_create(self,actor):
        self.s.row('social_actors',actor)
        row=self.s.db.execute('SELECT id FROM social_relationships WHERE instance_id=? AND actor_id=?',(self.s.instance_id,actor)).fetchone()
        return row[0] if row else self.s.insert('social_relationships',actor_id=actor,state='active',current_revision=0)
    def assess_trust(self,actor,domain,dimension,estimate,evidence):
        from digital_life.application.services.goals import Goals
        with self.s.tx():
            relation=self.get_or_create(actor); rule=Goals(self.s).rule()
            ref=self.s.insert('social_trust_assessments',relationship_id=relation,domain=text(domain),condition_rule=rule,dimension=dimension,estimate=probability(estimate),uncertainty_json={'status':'estimate'})
            self.s.insert('social_trust_evidence',assessment_id=ref,evidence_id=evidence,stance='support')
        return ref
    def record(self,actor,signal,activity):
        with self.s.tx(): return self.s.insert('social_interactions',relationship_id=self.get_or_create(actor),event_id=signal,activity_id=activity,interaction_role='user-task')
    def change(self,relationship,dimension,value,evidence,actor):
        if actor!=self.s.config()['controller']: raise Forbidden('relationship updates require approved evidence')
        with self.s.tx():
            self.s.row('social_relationships',relationship); self.s.row('social_relationship_dimensions',dimension); self.s.row('evidence_items',evidence)
            old=self.s.db.execute('SELECT * FROM social_relationship_values WHERE relationship_id=? AND dimension_id=?',(relationship,dimension)).fetchone()
            before=old['value'] if old else 0.
            if not isinstance(value,(int,float)) or not math.isfinite(value): raise ContractError('invalid relation value')
            if old: self.s.db.execute('UPDATE social_relationship_values SET value=?,evidence_id=? WHERE id=?',(value,evidence,old['id']))
            else: self.s.insert('social_relationship_values',relationship_id=relationship,dimension_id=dimension,value=value,evidence_id=evidence)
            return self.s.insert('social_relationship_changes',relationship_id=relationship,dimension_id=dimension,old_value=before,new_value=value,reason_ref=evidence)

