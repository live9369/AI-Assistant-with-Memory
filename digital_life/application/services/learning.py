"""Learning application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Learning:
    def __init__(self,store): self.s=store
    def rollback(self,commit,evidence_refs,actor):
        from digital_life.application.services.personality import Personality
        from digital_life.application.services.values import Values
        if actor!=self.s.config()['controller']: raise Forbidden('controller required')
        if len(set(evidence_refs))<2: raise ContractError('rollback requires repeated independent evidence references')
        with self.s.tx():
            for evidence in evidence_refs: self.s.row('evidence_items',evidence)
            original=self.s.row('learning_update_commits',commit)
            if self.s.db.execute('SELECT 1 FROM learning_update_commits WHERE instance_id=? AND reversal_of=?',(self.s.instance_id,commit)).fetchone(): raise Conflict('update already reversed')
            proposal=self.s.row('learning_update_proposals',original['proposal_id'])
            owner=proposal['owner_module']
            if owner=='memory':
                memory=self.s.row('memory_items',proposal['target_object_id'])
                if memory['current_revision_id']!=original['new_revision_id']: raise Conflict('memory changed after update')
                old=self.s.row('memory_revisions',original['old_revision_id']); current=self.s.row('memory_revisions',memory['current_revision_id'])
                candidate=self.propose('memory',memory['id'],{'reversal_of':commit},evidence_refs[0])
                result=self.commit_memory(candidate,current['revision_no'],old['content'],evidence_refs[0],actor)
            elif owner=='personality':
                if Personality(self.s).current()['profile']['id']!=original['new_revision_id']: raise Conflict('personality changed after update')
                dimensions={r['id']:r['name'] for r in self.s.rows('personality_dimensions')}
                values={dimensions[r['dimension_id']]:r['central_value'] for r in self.s.db.execute('SELECT * FROM personality_trait_values WHERE profile_id=?',(original['old_revision_id'],))}
                result=Personality(self.s).replace(values,evidence_refs,actor)['commit']
            elif owner=='values':
                if max(self.s.rows('value_profiles'),key=lambda r:r['version'])['id']!=original['new_revision_id']: raise Conflict('values changed after update')
                weights={r['dimension_id']:r['weight'] for r in self.s.db.execute('SELECT * FROM value_weights WHERE profile_id=?',(original['old_revision_id'],))}
                result=Values(self.s).replace(weights,evidence_refs,actor)['commit']
            else: raise ContractError('owner has no versioned update commit')
            self.s.db.execute('UPDATE learning_update_commits SET reversal_of=? WHERE id=?',(commit,result))
            self.s.event('learning.reversed',payload={'original':commit,'reversal':result,'owner':owner,'evidence':evidence_refs},lane='control')
            return result
    def propose(self,owner,target,change,evidence,risk=0.5):
        with self.s.tx():
            ref=self.s.insert('learning_update_proposals',owner_module=owner,target_object_id=target,mechanism_version='evidence-gated-v1',proposed_change=change,scope={'instance':self.s.instance_id},risk=probability(risk),state='proposed')
            self.s.insert('learning_proposal_evidence',proposal_id=ref,evidence_id=evidence,role='support')
        return ref
    def trial(self,proposal,dataset,conditions):
        with self.s.tx():
            p=self.s.row('learning_update_proposals',proposal)
            if p['state']!='proposed': raise Conflict('proposal not available for trial')
            model=self.s.rows('model_versions')[-1]['id']
            run=self.s.insert('evaluation_runs',dataset_version=dataset,model_version=model,conditions=conditions,state='planned')
            trial=self.s.insert('learning_update_trials',proposal_id=proposal,baseline_ref=run,trial_version='candidate:'+proposal,scope=json.loads(p['scope']),started_at=utc())
            self.s.db.execute("UPDATE learning_update_proposals SET state='trial' WHERE id=?",(proposal,))
            return {'trial':trial,'evaluation':run}
    def evaluate(self,trial,run,benefit,regression):
        if not math.isfinite(benefit) or not math.isfinite(regression) or regression<0: raise ContractError('invalid measured benefit')
        with self.s.tx():
            evaluation=self.s.row('evaluation_runs',run)
            if evaluation['state']!='completed': raise ContractError('evaluation run must contain completed measurements')
            decision='accept' if benefit>0 and regression==0 else 'reject'
            return self.s.insert('learning_update_evaluations',trial_id=trial,evaluation_run_id=run,benefit=benefit,regression=regression,decision=decision)
    def commit_memory(self,proposal,expected_revision,content,evidence,actor):
        from digital_life.application.services.memory import Memory
        if actor!=self.s.config()['controller']: raise Forbidden('learning acceptance needs controller in initial release')
        with self.s.tx():
            p=self.s.row('learning_update_proposals',proposal)
            if p['state']!='proposed' or p['owner_module']!='memory': raise ContractError('unsupported or consumed learning proposal')
            memory=self.s.row('memory_items',p['target_object_id']); old=memory['current_revision_id']
            new=Memory(self.s).revise(memory['id'],expected_revision,content,evidence)
            ref=self.s.insert('learning_update_commits',proposal_id=proposal,old_revision_id=old,new_revision_id=new,committed_at=utc())
            self.s.db.execute("UPDATE learning_update_proposals SET state='accepted' WHERE id=?",(proposal,))
        return ref


    def experience_assessments(self):
        return [dict(id=r['id'],payload=self.s.read_artifact(r['payload_artifact_id'])) for r in self.s.db.execute(
            "SELECT * FROM runtime_events WHERE instance_id=? AND source='learning-experience' AND event_type='learning.experience_assessed' ORDER BY event_seq",(self.s.instance_id,))]
    def _experience_opportunity(self,opportunity_ref):
        row=self.s.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='self-feedback' AND source_event_id=? AND event_type='self_feedback.opportunity'",(self.s.instance_id,'opportunity:'+opportunity_ref)).fetchone()
        if not row:raise ContractError('unknown experience opportunity')
        value=self.s.read_artifact(row['payload_artifact_id'])
        if value.get('instance_id')!=self.s.instance_id:raise Forbidden('experience source instance mismatch')
        result=self.s.row('action_results',value['original_result_ref'])
        if result['outcome_ref']!=value['original_evidence_ref']:raise Forbidden('experience source result mismatch')
        return value,result
    def assess_experience(self,opportunity_ref):
        """Evaluate existing observation only. No independent predictor exists in stage1."""
        with self.s.tx():
            opportunity,result=self._experience_opportunity(opportunity_ref)
            value={'contract_id':'COGNITIVE-EXPERIENCE-SHADOW-0.2','instance_id':self.s.instance_id,'opportunity_ref':opportunity_ref,
                'exposure_key':opportunity['exposure_key'],'revision':1,'cell':opportunity['cell'],'gain':None,'gain_status':'unknown','qualified':False,
                'reason':'failed-observation' if result['state']!='succeeded' else 'no-independent-before-after-measurement',
                'source_refs':opportunity['source_refs'],'measurement_origin':'none','affects_selection':False,'target_owner':'cognition.experience'}
            return self.s.event('learning.experience_assessed',payload=value,source='learning-experience',key='assessment:'+opportunity_ref+':1',lane='telemetry')
    def propose_experience(self,assessment_ref,expected_revision):
        from digital_life.application.cognition.cognition_experience import owned_payload
        if type(expected_revision) is not int or expected_revision<0:raise ContractError('invalid experience base revision')
        a=owned_payload(self.s,assessment_ref,'learning-experience','learning.experience_assessed')
        with self.s.tx():
            value={'contract_id':a['contract_id'],'instance_id':self.s.instance_id,'owner':'cognition.experience','mode':'shadow-only',
                'kind':'assessment','assessment_ref':assessment_ref,'opportunity_ref':a['opportunity_ref'],'cell':a['cell'],
                'expected_revision':expected_revision,'affects_selection':False}
            return self.s.event('learning.experience_proposed',payload=value,source='learning-experience',key='proposal:'+assessment_ref+':'+str(expected_revision),lane='telemetry')
    def propose_experience_invalidation(self,opportunity_ref,reason,expected_revision,actor):
        if actor!=self.s.config()['controller']:raise Forbidden('controller required')
        text(reason,1000)
        if type(expected_revision) is not int or expected_revision<0:raise ContractError('invalid experience base revision')
        opportunity,_=self._experience_opportunity(opportunity_ref)
        with self.s.tx():
            old=self.s.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='learning-experience' AND source_event_id=?",(self.s.instance_id,'invalidate:'+opportunity_ref+':'+str(expected_revision))).fetchone()
            if old:
                p=self.s.read_artifact(old['payload_artifact_id'])
                if p['reason']!=reason:raise Conflict('invalidation already proposed with different reason')
                return old['id']
            value={'contract_id':'COGNITIVE-EXPERIENCE-SHADOW-0.2','instance_id':self.s.instance_id,'owner':'cognition.experience','mode':'shadow-only',
                'kind':'invalidation','assessment_ref':None,'opportunity_ref':opportunity_ref,'cell':opportunity['cell'],
                'expected_revision':expected_revision,'reason':reason,'actor':actor,'affects_selection':False}
            return self.s.event('learning.experience_proposed',payload=value,source='learning-experience',key='invalidate:'+opportunity_ref+':'+str(expected_revision),lane='control')

    def assess_measured_experience(self,opportunity_ref,measurement_ref):
        """Assess a sealed heldout comparison; this never writes a cognition version."""
        from digital_life.application.learning.experience_measurement import ExperienceMeasurement
        report=ExperienceMeasurement(self.s).checked_report(measurement_ref,True)
        if report['opportunity_ref']!=opportunity_ref:raise Forbidden('measurement belongs to another opportunity')
        opportunity,_=self._experience_opportunity(opportunity_ref)
        with self.s.tx():
            old=self.s.db.execute("SELECT id FROM runtime_events WHERE instance_id=? AND source='learning-experience' AND source_event_id=?",(self.s.instance_id,'measured:'+measurement_ref)).fetchone()
            if old:return old[0]
            revision=max((r['payload']['revision'] for r in self.experience_assessments() if r['payload']['opportunity_ref']==opportunity_ref),default=0)+1
            value={'contract_id':'COGNITIVE-EXPERIENCE-SHADOW-0.3','instance_id':self.s.instance_id,'opportunity_ref':opportunity_ref,
                'exposure_key':opportunity['exposure_key'],'revision':revision,'cell':opportunity['cell'][:3]+[report['measurer_version']],
                'gain':report['gain'],'gain_status':report['gain_status'],'qualified':report['status']=='measured',
                'reason':'sealed-before-after-prediction-comparison','source_refs':opportunity['source_refs'],
                'measurement_origin':'sealed-prediction-comparison','measurement_ref':measurement_ref,
                'affects_selection':False,'target_owner':'cognition.experience'}
            return self.s.event('learning.experience_assessed',payload=value,source='learning-experience',key='measured:'+measurement_ref,lane='telemetry')
    def validate_measured_experience(self,assessment,require_live=False):
        from digital_life.application.learning.experience_measurement import ExperienceMeasurement
        report=ExperienceMeasurement(self.s).checked_report(assessment['measurement_ref'],require_live)
        opportunity,_=self._experience_opportunity(assessment['opportunity_ref'])
        expected={'cell':opportunity['cell'][:3]+[report['measurer_version']],'opportunity_ref':report['opportunity_ref'],
            'source_refs':opportunity['source_refs'],'exposure_key':opportunity['exposure_key'],'gain':report['gain'],
            'gain_status':report['gain_status'],'qualified':report['status']=='measured','measurement_origin':'sealed-prediction-comparison'}
        if any(assessment.get(k)!=v for k,v in expected.items()):raise Forbidden('experience assessment differs from sealed measurement')
        return report
