"""Values application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Values:
    def __init__(self,store): self.s=store
    def activate(self,activity,context,relevance=None):
        profile=max(self.s.rows('value_profiles'),key=lambda r:r['version']); output=[]
        with self.s.tx():
            for row in self.s.db.execute('SELECT * FROM value_weights WHERE profile_id=?',(profile['id'],)).fetchall():
                value=probability(min(1,max(0,row['weight']*(relevance or {}).get(row['dimension_id'],1))))
                ref=self.s.insert('value_activations',profile_id=profile['id'],activity_id=activity,context_id=context,dimension_id=row['dimension_id'],activation=value)
                output.append({'dimension_id':row['dimension_id'],'activation':value,'ref':ref})
        return output
    def replace(self,weights,evidence_refs,actor):
        from digital_life.application.services.learning import Learning
        if actor!=self.s.config()['controller'] or len(set(evidence_refs))<2: raise Forbidden('value change requires explicit authority and repeated evidence')
        old=max(self.s.rows('value_profiles'),key=lambda r:r['version'])
        rows=self.s.db.execute('SELECT * FROM value_weights WHERE profile_id=?',(old['id'],)).fetchall()
        known={r['dimension_id'] for r in rows}
        if set(weights)!=known: raise ContractError('complete value profile required')
        if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<0 for v in weights.values()) or sum(weights.values())<=0: raise ContractError('invalid value weights')
        with self.s.tx():
            for ref in evidence_refs: self.s.row('evidence_items',ref)
            new=self.s.insert('value_profiles',version=old['version']+1,previous_id=old['id'],effective_at=utc(),profile_object_id=old['profile_object_id'],normalization_rule='sum1')
            total=sum(weights.values())
            for dimension,value in weights.items(): self.s.insert('value_weights',profile_id=new,dimension_id=dimension,weight=value/total,uncertainty_json={'evidence_refs':evidence_refs})
            proposal=Learning(self.s).propose('values',old['profile_object_id'],weights,evidence_refs[0])
            commit=self.s.insert('learning_update_commits',proposal_id=proposal,old_revision_id=old['id'],new_revision_id=new,committed_at=utc())
            self.s.insert('value_change_records',old_profile_id=old['id'],new_profile_id=new,proposal_id=proposal,reason=dumps({'evidence':evidence_refs}))
            self.s.db.execute("UPDATE learning_update_proposals SET state='accepted' WHERE id=?",(proposal,))
            return {'profile':new,'commit':commit}

