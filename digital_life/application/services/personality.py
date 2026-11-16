"""Personality application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Personality:
    def __init__(self,store): self.s=store
    def current(self):
        profiles=self.s.rows('personality_profiles'); p=max(profiles,key=lambda x:x['version'])
        return {'profile':p,'traits':[dict(r) for r in self.s.db.execute('SELECT v.*,d.name FROM personality_trait_values v JOIN personality_dimensions d ON d.id=v.dimension_id WHERE v.profile_id=?',(p['id'],))]}
    def activate(self,activity,context,relevance=None):
        relevance=relevance or {}; result={}
        with self.s.tx():
            for trait in self.current()['traits']:
                value=trait['central_value']*probability(relevance.get(trait['name'],0))
                ref=self.s.insert('personality_states',activity_id=activity,context_id=context,dimension_id=trait['dimension_id'],value=value,value_origin='derived',method_version='trait-context-v1')
                result[trait['name']]={'value':value,'state_ref':ref,'path':'cognition-only'}
        return result
    def replace(self,values,evidence_refs,actor,*,expected_profile=None,proposal=None,uncertainty=None):
        from digital_life.application.services.learning import Learning
        if actor!=self.s.config()['controller'] or len(set(evidence_refs))<2: raise Forbidden('long-term change needs controller and multiple evidence items')
        with self.s.tx():
            for ref in evidence_refs: self.s.row('evidence_items',ref)
            old=self.current()
            if expected_profile is not None and old['profile']['id']!=expected_profile: raise Conflict('personality baseline changed')
            if set(values)-{r['name'] for r in old['traits']}: raise ContractError('unknown personality dimension')
            if proposal is not None:
                p=self.s.row('learning_update_proposals',proposal)
                if p['owner_module']!='personality' or p['state']!='trial' or p['target_object_id']!=old['profile']['profile_object_id']: raise Conflict('not a matching personality trial')
            new=self.s.insert('personality_profiles',version=old['profile']['version']+1,effective_at=utc(),previous_profile_id=old['profile']['id'],profile_object_id=old['profile']['profile_object_id'])
            for row in old['traits']:
                value=values.get(row['name'],row['central_value'])
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not -1<=value<=1: raise ContractError('trait scale')
                metadata=(uncertainty or {}).get(row['name'])
                if metadata is None: metadata=json.loads(row['uncertainty_json']) if value==row['central_value'] else {'evidence_refs':evidence_refs,'status':'controller-approved-not-empirically-calibrated'}
                self.s.insert('personality_trait_values',profile_id=new,dimension_id=row['dimension_id'],central_value=value,uncertainty_json=metadata)
            proposal=proposal or Learning(self.s).propose('personality',old['profile']['profile_object_id'],values,evidence_refs[0])
            commit=self.s.insert('learning_update_commits',proposal_id=proposal,old_revision_id=old['profile']['id'],new_revision_id=new,committed_at=utc())
            self.s.insert('personality_change_records',old_profile_id=old['profile']['id'],new_profile_id=new,proposal_id=proposal,reason=dumps({'evidence':evidence_refs,'controller':actor}))
            self.s.db.execute("UPDATE learning_update_proposals SET state='accepted' WHERE id=?",(proposal,))
            return {'profile':new,'commit':commit}

