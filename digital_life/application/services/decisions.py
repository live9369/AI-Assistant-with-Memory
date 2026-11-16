"""Decisions application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Decisions:
    def __init__(self,store): self.s=store
    def finalize(self,activity,goal,context,candidates,selected=0):
        if not candidates or not 0<=selected<len(candidates): raise ContractError('invalid candidates')
        with self.s.tx():
            decision=self.s.insert('decision_records',activity_id=activity,goal_id=goal,context_id=context,strategy_type='deterministic',strategy_version='allowed-max-v1',state='draft')
            refs=[]
            for i,candidate in enumerate(candidates):
                refs.append(self.s.insert('decision_candidates',decision_id=decision,action_template=candidate,eligible=1,score=float(i==selected),selection_probability=float(i==selected),selected=int(i==selected)))
            self.s.db.execute("UPDATE decision_records SET state='finalized' WHERE id=?",(decision,))
        return {'decision':decision,'selected':refs[selected]}
    def distribution(self,scores,eligible,temperature=1.):
        if len(scores)!=len(eligible) or not scores or not math.isfinite(temperature) or temperature<=0: raise ContractError('invalid decision distribution')
        valid=[v for v,allowed in zip(scores,eligible) if allowed]
        if not valid or any(not math.isfinite(v) for v in scores): raise ContractError('no legal finite candidate')
        top=max(valid); weights=[math.exp((v-top)/temperature) if allowed else 0. for v,allowed in zip(scores,eligible)]; total=sum(weights)
        return [w/total for w in weights]

