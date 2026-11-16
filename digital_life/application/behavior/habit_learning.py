"""Context-bound, reviewed habit acquisition and inhibitory extinction traces."""
import json
from digital_life.domain.contracts import ContractError, Conflict, Forbidden, dumps, text, validate_action
from digital_life.infrastructure.processes.dispatch_gate import coordinated

VERSION = 'context-habit-v1'


def canonical(action):
    validate_action(action)
    return {'tool':action['tool'],'arguments':action['arguments']}


class HabitLearning:
    def __init__(self, store): self.s = store
    def authority(self, actor):
        if actor!=self.s.config()['controller']:raise Forbidden('controller required')
    def events(self, kind):
        rows=self.s.db.execute('SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type=? ORDER BY event_seq',(self.s.instance_id,'habit_learning.'+kind))
        return [dict(self.s.read_artifact(r['payload_artifact_id']),id=r['id']) for r in rows]
    def event(self, ref, kind):
        row=self.s.row('runtime_events',ref)
        if row['event_type']!='habit_learning.'+kind:raise ContractError('incorrect habit event type')
        return dict(self.s.read_artifact(row['payload_artifact_id']),id=ref)
    def config(self):
        events=self.events('configured')
        return events[-1] if events else {'enabled':False,'id':None,'version':VERSION}
    def active(self):
        cfg=self.config()
        if not cfg['enabled']:raise Forbidden('habit learning disabled')
        return cfg
    @coordinated
    def configure(self, enabled, actor):
        self.authority(actor)
        if type(enabled) is not bool:raise ContractError('boolean required')
        from digital_life.application.lifecycle.control_plane import Control
        control=Control(self.s.root,self.s.instance_id)
        try:
            state=control.state()
            if not state['user_stopped'] or state['active_process_run_id']:raise Conflict('stop before habit learning configuration')
        finally:control.close()
        with self.s.tx():self.s.event('habit_learning.configured',payload={'enabled':enabled,'actor':actor,'version':VERSION},lane='control')
        return self.config()
    def registry(self):return {e['association']:e for e in self.events('registered')}
    @coordinated
    def enroll(self, action, cue, key, actor, owner_account=None):
        self.authority(actor);self.active();text(key,200);action=canonical(action)
        if not isinstance(cue,dict) or set(cue)!={'source','task_contains'}:raise ContractError('source and task_contains cue required')
        text(cue['source'],200);text(cue['task_contains'],200)
        if cue['source']=='exploration':raise Forbidden('V2 exploration uses dedicated policy')
        from digital_life.application.behavior.behavior_policy import BehaviorPolicy
        allowed,reason=BehaviorPolicy(self.s).eligibility(action)
        if not allowed:raise Forbidden(reason)
        with self.s.tx():
            for old in self.events('registered'):
                if old['key']==key:
                    if old['action']!=action or old['cue']!=cue or old.get('owner_account')!=owner_account:raise Conflict('habit key reused with different content')
                    return self.snapshot(old['association'])
                if old['action']==action and old['cue']==cue:raise Conflict('same habit cue already enrolled')
            from digital_life.application.services.habits import Habits
            rule=self.s.insert('rule_definitions',name='habit-cue:'+key,version=1,expression_json={'op':'and','args':[{'op':'eq','left':{'var':'source'},'right':cue['source']},{'op':'in','left':cue['task_contains'],'right':{'var':'task'}}]},engine_version='rules-v1')
            association=Habits(self.s).create(action,rule);row=self.s.row('habit_associations',association)
            self.s.event('habit_learning.registered',payload={'association':association,'habit':row['habit_id'],'cue_id':row['cue_id'],'action':action,'cue':cue,'key':key,'actor':actor,'version':VERSION,'owner_account':owner_account},lane='control')
            self.s.db.execute('UPDATE habit_associations SET uncertainty_json=?,learning_version=? WHERE id=?',(dumps({'method':VERSION,'status':'unmeasured'}),VERSION,association))
        return self.snapshot(association)
    def snapshot(self, association):
        registration=self.registry().get(association)
        if registration is None:raise ContractError('habit not enrolled for reviewed learning')
        previous=[e for e in self.events('changed') if e['association']==association]
        state=dict(previous[-1]['after']) if previous else {'acquisition':0.,'inhibition':0.,'state':'learning','positive_activities':[],'negative_activities':[],'consumed_activities':[]}
        state.update(association=association,habit=registration['habit'],revision=previous[-1]['id'] if previous else registration['id'])
        row=self.s.row('habit_associations',association);item=self.s.row('habit_items',registration['habit'])
        if row['strength']!=state['acquisition'] or item['state']!=state['state']:raise Conflict('habit cache changed outside reviewed journal')
        metadata=json.loads(row['uncertainty_json'])
        if row['learning_version']!=VERSION or metadata.get('method')!=VERSION or (previous and metadata.get('inhibition')!=state['inhibition']):raise Conflict('habit uncertainty cache diverged from journal')
        state['effective']=state['acquisition']*(1-state['inhibition']);state['expression']=state['effective'] if state['state']=='active' else 0.
        return state
    def variables(self, activity):
        row=self.s.db.execute('SELECT attributes_json FROM context_snapshots WHERE instance_id=? AND activity_id=?',(self.s.instance_id,activity)).fetchone()
        attributes=json.loads(row[0]);return {'source':attributes['source'],'task':attributes['task']}
    def matches(self, association, activity):
        cue=self.registry()[association]['cue'];variables=self.variables(activity)
        return variables['source']==cue['source'] and cue['task_contains'] in variables['task']
    def opportunities(self, activity):
        if not self.config()['enabled'] or self.variables(activity)['source']=='exploration':return []
        result=[]
        for association,registration in self.registry().items():
            if registration.get('owner_account'):
                from digital_life.application.accounts import account_scope as account_scope
                if not account_scope.current(self.s) or account_scope.current(self.s)['id']!=registration['owner_account']:continue
            if not self.matches(association,activity):continue
            state=self.snapshot(association)
            ref=self.s.insert('habit_opportunities',cue_id=registration['cue_id'],activity_id=activity,match_score=1.,action_taken=0,control_mode='unknown')
            result.append({'opportunity':ref,'habit':registration['habit'],'association':association,'strength':state['expression'],'managed':True,'revision':state['revision'],'acquisition':state['acquisition'],'inhibition':state['inhibition'],'state':state['state']})
        return result
    def context(self, suggestions):
        cfg=self.config()
        if not cfg['enabled']:return None
        return {'configuration':cfg['id'],'version':VERSION,'opportunities':[s for s in suggestions if s.get('managed')],
                'scope':'context association expression, not proof of psychological automaticity; never grants permission'}
    def check(self, payload):
        cfg=self.config();pinned=payload.get('habit_learning')
        if not cfg['enabled'] and pinned is None:return
        if not pinned or not cfg['enabled'] or pinned['configuration']!=cfg['id']:raise Forbidden('habit learning configuration superseded')
        for suggestion in pinned['opportunities']:
            if self.snapshot(suggestion['association'])['revision']!=suggestion['revision']:raise Forbidden('habit influence superseded')
    def record(self, activity, request, decision, result=None):
        if not self.config()['enabled']:return []
        req=self.s.row('thought_requests',request);payload=__import__('digital_life.application.learning.contexts',fromlist=['unwrapped_request_payload']).unwrapped_request_payload(self.s,req);pinned=payload.get('habit_learning')
        if not pinned or pinned['configuration']!=self.config()['id'] or payload.get('exploration'):return []
        accepted=[self.s.read_artifact(r[0]) for r in self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='thought.accepted'",(self.s.instance_id,activity))]
        if req['activity_id']!=activity or not req['accepted_result_id'] or not any(e['request']==request and e['decision']==decision and e['result']==req['accepted_result_id'] for e in accepted):raise Conflict('habit observation provenance mismatch')
        candidate=self.s.db.execute('SELECT * FROM decision_candidates WHERE decision_id=? AND selected=1',(decision,)).fetchone();action=canonical(json.loads(candidate['action_template']))
        if action['tool'] not in ('wait','ask'):
            if result is None:return []
            outcome=self.s.row('action_results',result);attempt=self.s.row('action_attempts',outcome['attempt_id']);intent=self.s.row('action_intents',attempt['intent_id'])
            if intent['candidate_id']!=candidate['id'] or outcome['state']!='succeeded' or self.s.read_artifact(outcome['receipt_artifact_id']).get('verification')!='pass':return []
        records=[]
        with self.s.tx():
            for suggestion in pinned['opportunities']:
                association=suggestion['association'];state=self.snapshot(association)
                if state['revision']!=suggestion['revision']:continue
                matched=action==self.registry()[association]['action'];key=association+':'+request+':'+(result or decision)
                existing=self.s.db.execute("SELECT id FROM runtime_events WHERE instance_id=? AND source='habit-observer' AND source_event_id=?",(self.s.instance_id,key)).fetchone()
                if existing:records.append(existing[0]);continue
                opportunity=self.s.row('habit_opportunities',suggestion['opportunity'])
                if opportunity['activity_id']!=activity or opportunity['cue_id']!=self.registry()[association]['cue_id']:raise Conflict('incorrect cue opportunity')
                ref=self.s.event('habit_learning.observed',payload={'association':association,'activity':activity,'request':request,'decision':decision,'candidate':candidate['id'],'opportunity':opportunity['id'],'matched':matched,'result':result,'configuration':pinned['configuration'],'observed_revision':state['revision']},activity=activity,source='habit-observer',key=key)
                self.s.evidence(object_id=ref,method='recorded-context-response')
                self.s.db.execute('UPDATE habit_opportunities SET action_taken=? WHERE id=?',(int(matched),opportunity['id']))
                self.s.insert('habit_activations',opportunity_id=opportunity['id'],candidate_id=candidate['id'],triggered=int(matched),inhibited=int(state['state']!='active'),inhibition_reason=state['state'] if state['state']!='active' else None)
                records.append(ref)
        return records
    def record_tool(self, intent, outcome):
        if not self.config()['enabled'] or outcome.get('state')!='succeeded':return []
        candidate=self.s.row('decision_candidates',self.s.row('action_intents',intent)['candidate_id']);decision=self.s.row('decision_records',candidate['decision_id'])
        for event in self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='thought.accepted' ORDER BY event_seq DESC",(self.s.instance_id,decision['activity_id'])):
            value=self.s.read_artifact(event[0])
            if value['decision']==decision['id']:return self.record(decision['activity_id'],value['request'],decision['id'],outcome['result'])
        return []
    def valid(self, observation):
        source=self.event(observation,'observed');req=self.s.row('thought_requests',source['request']);activity=self.s.row('activities',source['activity']);signal=self.s.row('perception_signals',activity['trigger_event_id'])
        if not req['accepted_result_id']:raise Conflict('source no longer accepted')
        result=self.s.row('thought_results',req['accepted_result_id'])
        if result['acceptance']!='accepted':raise Conflict('source not accepted')
        for ref in (req['request_artifact_id'],result['response_artifact_id'],signal['artifact_id']):
            value=self.s.read_artifact(ref)
            if not isinstance(value,dict) or 'redacted_by' in value:raise Forbidden('habit source erased')
        if source['result']:
            outcome=self.s.row('action_results',source['result']);receipt=self.s.read_artifact(outcome['receipt_artifact_id'])
            if outcome['state']!='succeeded' or receipt.get('verification')!='pass' or 'redacted_by' in receipt:raise Forbidden('habit tool source unavailable')
        if not self.matches(source['association'],source['activity']):raise Conflict('source cue mismatch')
        return source
    def _state(self, state):return {k:state[k] for k in ('acquisition','inhibition','state','positive_activities','negative_activities','consumed_activities')}
    def classify(self, state):
        effective=state['acquisition']*(1-state['inhibition'])
        if effective<=.05 and len(state['negative_activities'])>=3:return 'extinct'
        if effective>=.3-1e-12 and len(state['positive_activities'])>=3:return 'active'
        return 'learning'
    def _change(self, association, before, after, kind, extra):
        row=self.s.row('habit_associations',association)
        self.s.db.execute('UPDATE habit_associations SET strength=?,uncertainty_json=? WHERE id=?',(after['acquisition'],dumps({'method':VERSION,'inhibition':after['inhibition'],'positive_episodes':len(after['positive_activities']),'negative_episodes':len(after['negative_activities']),'status':'reviewed-engineering-not-psychometric'}),association))
        self.s.db.execute('UPDATE habit_items SET state=? WHERE id=?',(after['state'],row['habit_id']))
        return self.s.event('habit_learning.changed',payload=dict(extra,association=association,before=self._state(before),after=after,kind=kind,previous_revision=before['revision']),lane='control')
    @coordinated
    def feedback(self, observation, outcome, reason, key, expected_revision, actor):
        self.authority(actor);cfg=self.active();text(reason,2000);text(key,200)
        if type(outcome) is not int or outcome not in (0,1):raise ContractError('integer binary outcome required')
        with self.s.tx():
            previous=next((e for e in self.events('changed') if e['kind']=='feedback' and e.get('key')==key),None)
            if previous:
                if previous['observation']!=observation or previous['outcome']!=outcome or previous['reason']!=reason or previous['previous_revision']!=expected_revision:raise Conflict('feedback key reused')
                return previous
            source=self.valid(observation);association=source['association'];state=self.snapshot(association)
            if source['configuration']!=cfg['id'] or state['revision']!=expected_revision:raise Conflict('habit configuration or revision changed')
            if state['state']=='inhibited':raise Forbidden('resume before learning')
            if source['activity'] in state['consumed_activities']:raise Conflict('habit episode already consumed')
            if outcome and not source['matched']:raise ContractError('cannot reinforce a response that was not performed')
            after=self._state(state);after['consumed_activities']=state['consumed_activities']+[source['activity']]
            if outcome:
                after['acquisition']+=min(.1,.15*(1-after['acquisition']));after['inhibition']*=.9
                after['positive_activities']=state['positive_activities']+[source['activity']]
                after['state']=self.classify(after)
            else:
                after['inhibition']+=min(.2,.25*(1-after['inhibition']));after['negative_activities']=state['negative_activities']+[source['activity']]
                after['state']=self.classify(after)
                if state['state']=='active' and after['state']=='learning' and after['acquisition']*(1-after['inhibition'])>=.15:after['state']='active'
            ref=self._change(association,state,after,'feedback',{'observation':observation,'outcome':outcome,'reason':reason,'key':key,'actor':actor})
        return self.event(ref,'changed')
    @coordinated
    def control(self, association, operation, reason, expected_revision, actor):
        self.authority(actor);text(reason,2000)
        if operation not in ('inhibit','resume'):raise ContractError('invalid habit control')
        with self.s.tx():
            state=self.snapshot(association)
            if state['revision']!=expected_revision:raise Conflict('habit revision changed')
            if operation=='resume' and state['state']!='inhibited':raise Conflict('habit is not inhibited')
            after=self._state(state);after['state']='inhibited' if operation=='inhibit' else self.classify(after)
            if after['state']==state['state']:return state
            self._change(association,state,after,operation,{'reason':reason,'actor':actor})
        return self.snapshot(association)
    @coordinated
    def rollback(self, change, evidence, actor):
        self.authority(actor);original=self.event(change,'changed')
        origins={self.s.row('evidence_items',ref)['origin_object_id'] for ref in evidence}
        if None in origins or len(origins)<2:raise ContractError('two distinct evidence origins required')
        with self.s.tx():
            state=self.snapshot(original['association'])
            if original['kind']!='feedback' or state['revision']!=change:raise Conflict('only latest feedback can be compensated')
            after=dict(original['before']);after['consumed_activities']=state['consumed_activities']
            self._change(original['association'],state,after,'rollback',{'reversal_of':change,'evidence':evidence,'actor':actor})
        return self.snapshot(original['association'])
    def status(self):
        return {'configuration':self.config(),'habits':[dict(self.snapshot(a),cue=r['cue'],action=r['action']) for a,r in self.registry().items()],
                'observations':[dict(e,evidence_refs=[r[0] for r in self.s.db.execute('SELECT id FROM evidence_items WHERE instance_id=? AND origin_object_id=?',(self.s.instance_id,e['id']))]) for e in self.events('observed')],
                'inference_started':False}
