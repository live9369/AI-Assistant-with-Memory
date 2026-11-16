"""Cognition-owned experience projection. No selection or model calls.

Positive/negative fixtures can exercise the fold before a production measurer exists.
Callers must establish provenance; a computed Q is not a verified learning claim.
"""
import math
from digital_life.domain.contracts import ContractError,dumps,sha

class ExperienceProjection:
    @staticmethod
    def fold(assessments,invalidated=(),prior_mean=0.,kappa=2.):
        if isinstance(kappa,bool) or not isinstance(kappa,(int,float)) or not math.isfinite(kappa) or kappa<=0:raise ContractError('invalid shadow prior strength')
        if isinstance(prior_mean,bool) or not isinstance(prior_mean,(int,float)) or not math.isfinite(prior_mean) or not -1<=prior_mean<=1:raise ContractError('invalid shadow prior')
        invalidated=set(invalidated);latest={};identities={}
        for record in assessments:
            cell=record['cell']
            if not isinstance(cell,list) or len(cell)!=4 or any(not isinstance(v,str) or not v for v in cell):raise ContractError('invalid interest cell')
            exposure=record['exposure_key'];revision=record['revision']
            if not isinstance(exposure,str) or not exposure or type(revision) is not int or revision<1:raise ContractError('invalid shadow assessment identity')
            if not isinstance(record['opportunity_ref'],str) or not record['opportunity_ref']:raise ContractError('invalid opportunity reference')
            if type(record.get('source_readable')) is not bool or type(record.get('qualified')) is not bool:raise ContractError('invalid projection flags')
            gain=record['gain'];status=record['gain_status']
            if status=='unknown':
                if gain is not None:raise ContractError('unknown gain must be null')
            elif status in ('positive','negative','measured_zero'):
                if isinstance(gain,bool) or not isinstance(gain,(int,float)) or not math.isfinite(gain) or not -1<=gain<=1:raise ContractError('invalid measured gain')
                if status!=('positive' if gain>0 else 'negative' if gain<0 else 'measured_zero'):raise ContractError('gain status differs from value')
            else:raise ContractError('invalid gain status')
            identity=(tuple(cell),exposure,revision);fingerprint=sha(dumps(record))
            if identity in identities and identities[identity]!=fingerprint:raise ContractError('conflicting shadow assessment revision')
            identities[identity]=fingerprint
            key=(tuple(cell),exposure)
            if key not in latest or latest[key]['revision']<revision:latest[key]=record
        cells={}
        for (cell,exposure),record in sorted(latest.items()):
            key=sha(dumps(cell));value=cells.setdefault(key,{'cell':list(cell),'sample_count':0,'unknown_count':0,'excluded_count':0,'sum_gain':0.})
            if record['opportunity_ref'] in invalidated or not record.get('source_readable',False):value['excluded_count']+=1
            elif record['gain_status']=='unknown':value['unknown_count']+=1
            elif not record.get('qualified',False):value['excluded_count']+=1
            else:value['sample_count']+=1;value['sum_gain']+=record['gain']
        for value in cells.values():
            value['shadow_q']=(kappa*prior_mean+value['sum_gain'])/(kappa+value['sample_count'])
            value['experience_estimate']=value['shadow_q']
            value['uncertainty']='unmeasured' if not value['sample_count'] else 'uncalibrated'
        return {'mode':'shadow-only','affects_selection':False,'prior_mean':prior_mean,'kappa':kappa,'cells':list(cells.values())}


OWNER='cognition.experience'
SOURCE='cognition-experience'
CONTRACT='COGNITIVE-EXPERIENCE-SHADOW-0.3'
LEGACY_CONTRACT='COGNITIVE-EXPERIENCE-SHADOW-0.2'

def owned_payload(store,event_ref,source,event_type):
    from digital_life.domain.contracts import Forbidden
    event=store.row('runtime_events',event_ref)
    if event['source']!=source or event['event_type']!=event_type:raise Forbidden('experience record owner/type mismatch')
    payload=store.read_artifact(event['payload_artifact_id'])
    if payload.get('instance_id')!=store.instance_id:raise Forbidden('experience record instance mismatch')
    if payload.get('contract_id') not in (CONTRACT,LEGACY_CONTRACT):raise Forbidden('experience contract mismatch')
    return payload

class CognitiveExperience:
    """Single version writer under Cognition. All current revisions are shadow-only."""
    def __init__(self,store):self.s=store
    def events(self):
        return [dict(id=r['id'],payload=self.s.read_artifact(r['payload_artifact_id'])) for r in self.s.db.execute(
            "SELECT * FROM runtime_events WHERE instance_id=? AND source=? AND event_type='cognition.experience_saved' ORDER BY event_seq",(self.s.instance_id,SOURCE))]
    def current_revision(self,cell):
        key=sha(dumps(cell))
        return max((r['payload']['revision'] for r in self.events() if r['payload']['experience_ref']==key),default=0)
    def save(self,proposal_ref,expected_revision):
        from digital_life.domain.contracts import Conflict,Forbidden
        p=owned_payload(self.s,proposal_ref,'learning-experience','learning.experience_proposed')
        if type(expected_revision) is not int or expected_revision<0 or p['expected_revision']!=expected_revision:raise Conflict('experience expected revision mismatch')
        if p.get('owner')!=OWNER or p.get('mode')!='shadow-only':raise Forbidden('only shadow cognitive experience proposals accepted')
        # Own the write transaction. Nested calls share the existing observation unit of work.
        with self.s.tx():
            history=self.events()
            prior=next((r for r in history if r['payload']['proposal_ref']==proposal_ref or p['kind']=='assessment' and r['payload'].get('assessment_ref')==p.get('assessment_ref')),None)
            if prior:return prior['id']
            invalidated=next((r for r in history if p['kind']=='invalidation' and r['payload']['kind']=='invalidation' and r['payload']['opportunity_ref']==p['opportunity_ref']),None)
            if invalidated:
                old=owned_payload(self.s,invalidated['payload']['proposal_ref'],'learning-experience','learning.experience_proposed')
                if old['reason']!=p['reason']:raise Conflict('experience already invalidated for different reason')
                return invalidated['id']
            current=self.current_revision(p['cell'])
            if current!=expected_revision:raise Conflict('cognitive experience revision changed')
            from digital_life.application.services.learning import Learning
            opportunity,_=Learning(self.s)._experience_opportunity(p['opportunity_ref'])
            assessment_ref=p.get('assessment_ref')
            if p['kind']=='assessment':
                a=owned_payload(self.s,assessment_ref,'learning-experience','learning.experience_assessed')
                if a.get('measurement_ref'):
                    if a['contract_id']!=CONTRACT:raise Forbidden('measured experience needs the measurement-capable contract')
                    report=Learning(self.s).validate_measured_experience(a,require_live=True)
                    expected_cell=opportunity['cell'][:3]+[report['measurer_version']]
                else:
                    expected_cell=opportunity['cell']
                    if a['gain'] is not None or a['gain_status']!='unknown' or a['qualified'] is not False:raise Forbidden('numeric gain requires sealed measurement evidence')
                if p['cell']!=expected_cell:raise Forbidden('experience cell differs from registered measurement')
                if a['cell']!=p['cell'] or a['opportunity_ref']!=p['opportunity_ref'] or a['exposure_key']!=opportunity['exposure_key']:raise Forbidden('proposal differs from learning assessment')
            elif p['kind']=='invalidation':
                if p['cell']!=opportunity['cell']:raise Forbidden('invalidation cell differs from original opportunity')
                if p.get('actor')!=self.s.config()['controller']:raise Forbidden('experience invalidation needs controller')
            else:raise ContractError('unsupported experience proposal')
            previous=next((r['id'] for r in reversed(history) if r['payload']['experience_ref']==sha(dumps(p['cell']))),None)
            value={'contract_id':CONTRACT,'instance_id':self.s.instance_id,'owner':OWNER,'experience_ref':sha(dumps(p['cell'])),
                'cell':p['cell'],'revision':current+1,'previous_revision_ref':previous,'proposal_ref':proposal_ref,
                'assessment_ref':assessment_ref,'kind':p['kind'],'opportunity_ref':p['opportunity_ref'],
                'mode':'shadow-only','affects_selection':False,'acceptance_state':'shadow-not-world-fact'}
            return self.s.event('cognition.experience_saved',payload=value,source=SOURCE,key='save:'+proposal_ref,lane='telemetry')
    def snapshot(self,actor):
        from digital_life.domain.contracts import Forbidden
        from digital_life.application.autonomy.exploration import Exploration
        if actor!=self.s.config()['controller']:raise Forbidden('controller required for cognitive experience inspection')
        with self.s.tx():
            history=self.events();rows=[];heads={};adopted=set();invalid=set();legacy_refs=[]
            for record in history:
                value=record['payload'];heads[value['experience_ref']]={'revision':value['revision'],'revision_ref':record['id']}
                if value['kind']=='invalidation':invalid.add(value['opportunity_ref']);continue
                a=dict(owned_payload(self.s,value['assessment_ref'],'learning-experience','learning.experience_assessed'))
                a['source_readable']=Exploration(self.s).readable_refs(a['source_refs'])
                if a.get('measurement_ref'):
                    from digital_life.application.services.learning import Learning
                    try:Learning(self.s).validate_measured_experience(a)
                    except ContractError:a['source_readable']=False
                rows.append(a);adopted.add(a['opportunity_ref'])
            # Read-only compatibility: old journal entries are not rewritten or silently adopted.
            for event in self.s.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='self-feedback' AND event_type IN ('self_feedback.assessment','self_feedback.invalidation') ORDER BY event_seq",(self.s.instance_id,)):
                value=self.s.read_artifact(event['payload_artifact_id'])
                if event['event_type']=='self_feedback.invalidation':invalid.add(value['opportunity_ref']);continue
                if value['opportunity_ref'] in adopted:continue
                row=dict(value);row['qualified']=False;row['source_readable']=Exploration(self.s).readable_refs(row['source_refs'])
                rows.append(row);legacy_refs.append(event['id'])
            result=ExperienceProjection.fold(rows,invalid)
            result.update(owner=OWNER,contract_id=CONTRACT,experience_versions=heads,legacy_unadopted_count=len(legacy_refs),
                snapshot_revision=sha(dumps({'heads':heads,'legacy_refs':legacy_refs,'invalid':sorted(invalid),'readable':[(r['exposure_key'],r['source_readable']) for r in rows]})))
            return result
