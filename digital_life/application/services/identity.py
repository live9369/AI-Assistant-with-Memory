"""Identity application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Identity:
    def __init__(self,store): self.s=store
    def inspect(self):
        anchors=self.s.rows('identity_anchors'); integrity=self.s.integrity()
        return {'instance_id':self.s.instance_id,'anchors':anchors,'storage':integrity,'same_subject_consciousness':'not_asserted'}
    def capability(self,capability,estimate,condition=None):
        from digital_life.application.services.goals import Goals
        with self.s.tx(): return self.s.insert('self_capability_models',capability=capability,conditions=condition or Goals(self.s).rule(),estimated_performance=probability(estimate),uncertainty_json={'status':'unverified'})

