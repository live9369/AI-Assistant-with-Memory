"""Opt-in sidecar journal for exploration; does not change prompts or choices.

Stage 1 never invents predictions or measured gains. Existing V2 observations
produce unknown learning records. Numerical projection is a read-only fold;
production measurement and interest commits are deliberately not implemented.
"""
import json
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,dumps,sha,text
from digital_life.infrastructure.processes.dispatch_gate import coordinated

CONTRACT='AE-SELF-FEEDBACK-SHADOW-0.1'
SOURCE='self-feedback'

class SelfFeedback:
    def __init__(self,store):self.s=store
    def configuration(self):
        events=self._events('configured')
        return dict(events[-1]['payload'],generation=events[-1]['id']) if events else {'enabled':False,'mode':'shadow-only','generation':None}
    def _events(self,kind):
        return [dict(id=row['id'],activity=row['activity_id'],seq=row['event_seq'],payload=self.s.read_artifact(row['payload_artifact_id'])) for row in self.s.db.execute('SELECT * FROM runtime_events WHERE instance_id=? AND source=? AND event_type=? ORDER BY event_seq',(self.s.instance_id,SOURCE,'self_feedback.'+kind))]
    def _existing(self,kind,key):
        row=self.s.db.execute('SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=?',(self.s.instance_id,SOURCE,kind+':'+key)).fetchone()
        return self.s.read_artifact(row[0]) if row else None
    def _write(self,kind,key,value,activity=None):
        payload=dict(value,contract_id=CONTRACT,instance_id=self.s.instance_id)
        self.s.event('self_feedback.'+kind,payload=payload,source=SOURCE,key=kind+':'+key,activity=activity,lane='telemetry')
        return payload
    def _controller(self,actor):
        if actor!=self.s.config()['controller']:raise Forbidden('controller required for shadow journal inspection/configuration')
    @coordinated
    def configure(self,actor,enabled):
        self._controller(actor)
        if type(enabled) is not bool:raise ContractError('enabled must be boolean')
        if enabled:
            from digital_life.application.lifecycle.control_plane import Control
            control=Control(self.s.root,self.s.instance_id)
            try:
                state=control.state()
                if not state['user_stopped'] or state['active_process_run_id']:raise Conflict('stop before enabling shadow recording')
            finally:control.close()
        with self.s.tx():
            self.s.event('self_feedback.configured',payload={'enabled':enabled,'mode':'shadow-only','affects_selection':False,'contract_id':CONTRACT},source=SOURCE,lane='control')
        return self.configuration()
    def prepared_thought(self,activity,request_ref,payload):
        if not self.configuration()['enabled'] or not payload.get('exploration'):return None
        from digital_life.application.services.personality import Personality
        request=self.s.row('thought_requests',request_ref);values=self.s.rows('value_profiles')
        return self._write('request_context',request_ref,{'request_ref':request_ref,'request_artifact_ref':request['request_artifact_id'],
            'personality_revision':Personality(self.s).current()['profile']['id'],'personality_states':payload['personality'],
            'value_revision':max(values,key=lambda v:v['version'])['id'] if values else None,'states':payload['states'],
            'memory_revision_refs':[m['revision_id'] for m in payload['selected_memories']],
            'context_timing':'captured-with-original-request'},activity)
    def register_intent(self,question,request_ref=None):
        if not self.configuration()['enabled']:return None
        key=sha(dumps([self.s.instance_id,question['id'],question.get('resource_revision',0)]))
        prior=self._existing('intent',key)
        if prior:return prior
        from digital_life.application.services.personality import Personality
        profile=Personality(self.s).current();values=self.s.rows('value_profiles')
        previous=[e['payload']['intent_ref'] for e in self._events('intent') if e['payload']['question_ref']==question['id']]
        prepared=self._existing('request_context',request_ref) if request_ref else None
        snapshot=self._write('snapshot',key,{'snapshot_ref':key,'personality_revision':prepared['personality_revision'] if prepared else None,
            'request_context_ref':request_ref if prepared else None,'context_timing':'captured-with-original-request' if prepared else 'late-registration-original-context-unknown',
            'current_profile_at_registration':profile['profile']['id'],
            'traits_at_registration':{r['name']:r['central_value'] for r in profile['traits']},'value_revision':prepared['value_revision'] if prepared else None,
            'source_refs':list(question['evidence_refs']),'relevance_status':'not_computed_stage1','experience_snapshot_ref':None,'experience_owner':'cognition.experience',
            'configuration_generation':self.configuration()['generation']})
        return self._write('intent',key,{'intent_ref':key,'question_ref':question['id'],'question_revision':question.get('resource_revision',0),
            'question':question['question'],'verification':question['verification'],'source_refs':list(question['evidence_refs']),
            'snapshot_ref':snapshot['snapshot_ref'],'origin_request_ref':request_ref,'root_goal_ref':None,'identity_mode':'shadow-sidecar-not-live-goal',
            'predecessor_intent_ref':previous[-1] if previous else None,'state':'recorded','cell':['knowledge-gap','workspace-observation','unclassified','unmeasured-v1'],
            'model_expected_gain_diagnostic':question['expected_gain'],'model_cost_diagnostic':question['cost']})
    def bind(self,activity,question):
        if not self.configuration()['enabled'] or not question:return None
        intent=self.register_intent(question)
        goal=self.s.db.execute('SELECT g.id FROM goal_items g JOIN activities a ON a.trigger_event_id=g.source_ref WHERE a.id=? AND a.instance_id=?',(activity,self.s.instance_id)).fetchone()
        return self._write('binding',activity,{'activity_ref':activity,'intent_ref':intent['intent_ref'],'question_ref':question['id'],
            'question_revision':question.get('resource_revision',0),'activity_goal_ref':goal[0] if goal else None,
            'configuration_generation':self.configuration()['generation']},activity)
    @coordinated
    def prepare_observation(self,activity,action_intent):
        if not self.configuration()['enabled']:return None
        from digital_life.application.autonomy.exploration import Exploration
        exploration=Exploration(self.s);binding=exploration.binding(activity)
        if not binding or not binding['question_id']:return None
        self.s.assert_execution_allowed()
        with self.s.tx():
            prior=self._existing('expectation',action_intent)
            if prior:return prior
            q=exploration.questions()[binding['question_id']];linked=self._existing('binding',activity) or self.bind(activity,q)
            row=self.s.row('action_intents',action_intent)
            candidate=self.s.row('decision_candidates',row['candidate_id'])
            if self.s.row('decision_records',candidate['decision_id'])['activity_id']!=activity:raise Conflict('shadow expectation action/activity mismatch')
            attempted=self.s.db.execute('SELECT 1 FROM action_attempts WHERE intent_id=? LIMIT 1',(action_intent,)).fetchone()
            return self._write('expectation',action_intent,{'expectation_ref':action_intent,'action_intent_ref':action_intent,
                'intent_ref':linked['intent_ref'],'question_ref':q['id'],'question_revision':q.get('resource_revision',0),
                'verification_rule':q['verification'],'prediction_distribution':None,'gain_status':'unknown',
                'reason':'legacy-output-has-no-measurable-prediction','prepared_before_dispatch':not bool(attempted),
                'timing':'before-first-attempt' if not attempted else 'late-recovery-not-a-prior-prediction',
                'source_refs':list(q['evidence_refs']),'arguments':json.loads(row['arguments_json'])},activity)
    def observe(self,activity,outcome):
        if not self.configuration()['enabled']:return None
        from digital_life.application.autonomy.exploration import Exploration
        exploration=Exploration(self.s);binding=exploration.binding(activity)
        if not binding or not binding['question_id']:return None
        linked=self._existing('binding',activity) or self.bind(activity,exploration.questions()[binding['question_id']])
        result=self.s.row('action_results',outcome['result'])
        if result['receipt_artifact_id']!=outcome['receipt'] or result['outcome_ref']!=outcome['evidence']:raise Conflict('shadow result provenance mismatch')
        attempt=self.s.row('action_attempts',result['attempt_id'])
        original_intent=self.s.row('action_intents',attempt['intent_id'])
        candidate=self.s.row('decision_candidates',original_intent['candidate_id'])
        original_activity=self.s.row('decision_records',candidate['decision_id'])['activity_id']
        if original_activity!=activity and not any(e.get('original_result')==outcome['result'] for e in exploration.payloads('exploration.evidence_reused',activity)):raise Forbidden('unrelated shadow observation')
        expectation=self._existing('expectation',attempt['intent_id'])
        exposure=sha(dumps([outcome['result'],'original-tool-result']))
        observation_key=sha(dumps([activity,outcome['result']]))
        observation=self._write('observation',observation_key,{'observation_ref':observation_key,'intent_ref':linked['intent_ref'],
            'expectation_ref':expectation['expectation_ref'] if expectation else None,'original_result_ref':outcome['result'],
            'original_evidence_ref':outcome['evidence'],'receipt_ref':outcome['receipt'],'reused':bool(outcome.get('reused')),
            'exposure_key':exposure,'execution_state':result['state']},activity)
        if not self._existing('opportunity',exposure):
            intent=self._existing('intent',linked['intent_ref'])
            opportunity=self._write('opportunity',exposure,{'opportunity_ref':exposure,'exposure_key':exposure,
                'expectation_ref':expectation['expectation_ref'] if expectation else None,'intent_ref':linked['intent_ref'],
                'source_refs':intent['source_refs'],'original_result_ref':outcome['result'],'original_evidence_ref':outcome['evidence'],
                'cell':intent['cell'],'state':'unmeasurable'},activity)
        self._save_experience(exposure)
        return observation
    def interpretation(self,activity,request_ref,assessment):
        if not self.configuration()['enabled']:return None
        return self._write('interpretation',request_ref,{'request_ref':request_ref,'model_assessment':assessment,
            'assurance':'unverified-model-interpretation','gain':None,'gain_status':'unknown'},activity)
    def _save_experience(self,opportunity_ref):
        from digital_life.application.services.learning import Learning
        from digital_life.application.services.cognition import Cognition
        opportunity=self._existing('opportunity',opportunity_ref)
        learning=Learning(self.s);cognition=Cognition(self.s)
        assessment=learning.assess_experience(opportunity_ref)
        from digital_life.application.cognition.cognition_experience import CognitiveExperience
        old=next((r for r in CognitiveExperience(self.s).events() if r['payload'].get('assessment_ref')==assessment),None)
        if old:return old['id']
        revision=cognition.experience_revision(opportunity['cell'])
        proposal=learning.propose_experience(assessment,revision)
        return cognition.save_experience(proposal,revision)
    @coordinated
    def invalidate(self,opportunity_ref,reason,actor):
        self._controller(actor);text(reason,1000)
        from digital_life.application.services.learning import Learning
        from digital_life.application.services.cognition import Cognition
        opportunity=self._existing('opportunity',opportunity_ref)
        if not opportunity:raise ContractError('unknown shadow opportunity')
        with self.s.tx():
            cognition=Cognition(self.s);learning=Learning(self.s)
            revision=cognition.experience_revision(opportunity['cell'])
            proposal=learning.propose_experience_invalidation(opportunity_ref,reason,revision,actor)
            p=self.s.read_artifact(self.s.row('runtime_events',proposal)['payload_artifact_id'])
            return cognition.save_experience(proposal,p['expected_revision'])
    def shadow_interest(self,actor):
        # Historical API name; Cognition owns the view and every persisted revision.
        from digital_life.application.services.cognition import Cognition
        return Cognition(self.s).experience_snapshot(actor)
    @coordinated
    def reconcile_experiences(self,actor):
        self._controller(actor)
        if not self.configuration()['enabled']:raise Forbidden('enable shadow recording before explicit legacy adoption')
        with self.s.tx():return [self._save_experience(r['payload']['opportunity_ref']) for r in self._events('opportunity')]

    def status(self,actor):
        self._controller(actor)
        from digital_life.application.services.learning import Learning
        from digital_life.application.cognition.cognition_experience import CognitiveExperience
        return {'configuration':self.configuration(),'projection_owner':'cognition.experience','learning_assessment_count':len(Learning(self.s).experience_assessments()),'experience_version_count':len(CognitiveExperience(self.s).events()),'record_counts':{k:len(self._events(k)) for k in ('request_context','intent','snapshot','binding','expectation','observation','opportunity','assessment','interpretation','invalidation')},'shadow_interest':self.shadow_interest(actor),'inference_started':False}
