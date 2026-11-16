"""Controlled slow personality updates from annotated recorded behavior episodes."""
import json
import math
from datetime import datetime
from digital_life.domain.contracts import ContractError, Conflict, Forbidden, utc, text, dumps
from digital_life.infrastructure.processes.dispatch_gate import coordinated
from digital_life.application.services.personality import Personality
from digital_life.application.services.learning import Learning

VERSION = 'personality-growth-v1'


class PersonalityGrowth:
    def __init__(self, store): self.s = store
    def authority(self, actor):
        if actor != self.s.config()['controller']: raise Forbidden('controller required')
    def events(self, kind):
        rows = self.s.db.execute('SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type=? ORDER BY event_seq', (self.s.instance_id,'personality_growth.'+kind))
        return [dict(self.s.read_artifact(r['payload_artifact_id']), id=r['id']) for r in rows]
    def event(self, ref, kind):
        row = self.s.row('runtime_events', ref)
        if row['event_type'] != 'personality_growth.'+kind: raise ContractError('incorrect growth event type')
        return dict(self.s.read_artifact(row['payload_artifact_id']), id=ref)
    def config(self):
        events = self.events('configured')
        return events[-1] if events else {'enabled':False,'id':None,'version':VERSION}
    @coordinated
    def configure(self, enabled, actor):
        self.authority(actor)
        if type(enabled) is not bool: raise ContractError('boolean required')
        from digital_life.application.lifecycle.control_plane import Control
        control = Control(self.s.root,self.s.instance_id)
        try:
            state = control.state()
            if not state['user_stopped'] or state['active_process_run_id']: raise Conflict('stop before personality growth configuration')
        finally: control.close()
        with self.s.tx(): self.s.event('personality_growth.configured',payload={'enabled':enabled,'actor':actor,'version':VERSION},lane='control')
        return self.config()
    def active(self):
        cfg = self.config()
        if not cfg['enabled']: raise Forbidden('personality growth disabled')
        return cfg
    def context(self):
        cfg = self.config()
        if not cfg['enabled']: return None
        current = Personality(self.s).current()
        return {'configuration':cfg['id'],'version':VERSION,'profile':current['profile']['id'],
                'uncertainty':{r['name']:json.loads(r['uncertainty_json']) for r in current['traits']},
                'recent_changes':[{'commit':e['commit'],'trait':e['trait'],'delta':e['delta']} for e in self.events('applied')[-5:]],
                'scope':'controller-annotated engineering growth; no psychometric validity claim'}
    def record(self, activity, request, decision, result=None):
        cfg = self.config()
        if not cfg['enabled']: return None
        req = self.s.row('thought_requests',request); payload = __import__('digital_life.application.learning.contexts',fromlist=['unwrapped_request_payload']).unwrapped_request_payload(self.s,req); pinned = payload.get('personality_growth')
        if not pinned or pinned['configuration']!=cfg['id'] or payload.get('exploration'): return None
        if req['activity_id']!=activity or not req['accepted_result_id']: raise Conflict('accepted request required')
        d = self.s.row('decision_records',decision)
        if d['activity_id']!=activity or d['state']!='finalized': raise Conflict('finalized matching decision required')
        accepted = [self.s.read_artifact(r[0]) for r in self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='thought.accepted'",(self.s.instance_id,activity))]
        if not any(e['request']==request and e['decision']==decision and e['result']==req['accepted_result_id'] for e in accepted): raise Conflict('request and decision provenance mismatch')
        candidate = self.s.db.execute('SELECT * FROM decision_candidates WHERE decision_id=? AND selected=1',(decision,)).fetchone()
        action = json.loads(candidate['action_template']); source = 'decision:'+decision
        if action['tool'] not in ('wait','ask'):
            if result is None: return None
            outcome = self.s.row('action_results',result);attempt = self.s.row('action_attempts',outcome['attempt_id']);intent = self.s.row('action_intents',attempt['intent_id'])
            if intent['candidate_id']!=candidate['id'] or outcome['state']!='succeeded': return None
            receipt = self.s.read_artifact(outcome['receipt_artifact_id'])
            if receipt.get('verification')!='pass': return None
            source = 'result:'+result
        with self.s.tx():
            return self.s.event('personality_growth.opportunity',payload={'activity':activity,'request':request,'decision':decision,'candidate':candidate['id'],
                'profile':pinned['profile'],'result':result,'action':action,'context_ref':d['context_id'],'configuration':cfg['id']},
                activity=activity,source='personality-growth',key=source)
    def record_tool(self, intent, outcome):
        if not self.config()['enabled'] or outcome.get('state')!='succeeded': return None
        candidate = self.s.row('decision_candidates',self.s.row('action_intents',intent)['candidate_id']);d = self.s.row('decision_records',candidate['decision_id'])
        for event in self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='thought.accepted' ORDER BY event_seq DESC",(self.s.instance_id,d['activity_id'])):
            value = self.s.read_artifact(event[0])
            if value['decision']==d['id']: return self.record(d['activity_id'],value['request'],d['id'],outcome['result'])
        return None
    def _valid(self, ref):
        observation = self.event(ref,'observed')
        if any(e['observation']==ref for e in self.events('invalidated')): raise Conflict('observation invalidated')
        opportunity = self.event(observation['opportunity'],'opportunity');req = self.s.row('thought_requests',opportunity['request'])
        if not req['accepted_result_id']: raise Conflict('source no longer accepted')
        result = self.s.row('thought_results',req['accepted_result_id'])
        if result['acceptance']!='accepted': raise Conflict('source not accepted')
        if opportunity['result']:
            outcome = self.s.row('action_results',opportunity['result']);receipt = self.s.read_artifact(outcome['receipt_artifact_id'])
            if outcome['state']!='succeeded' or not isinstance(receipt,dict) or receipt.get('verification')!='pass' or 'redacted_by' in receipt: raise Forbidden('verified tool source no longer available')
        activity = self.s.row('activities',opportunity['activity']); signal = self.s.row('perception_signals',activity['trigger_event_id'])
        for artifact in (req['request_artifact_id'],result['response_artifact_id'],signal['artifact_id']):
            value = self.s.read_artifact(artifact)
            if not isinstance(value,dict) or 'redacted_by' in value: raise Forbidden('source erased')
        return observation
    @coordinated
    def observe(self, opportunity, trait, value, reliability, context, reason, key, actor):
        self.authority(actor);self.active();text(context,200);text(reason,2000);text(key,200)
        if trait not in {r['name'] for r in self.s.rows('personality_dimensions')}: raise ContractError('unknown trait')
        for number,low,high in ((value,-1,1),(reliability,0,1)):
            if isinstance(number,bool) or not isinstance(number,(int,float)) or not math.isfinite(number) or not low<=number<=high: raise ContractError('finite bounded annotation required')
        if reliability<=0: raise ContractError('positive reliability required')
        source = self.event(opportunity,'opportunity')
        payload = {'opportunity':opportunity,'activity':source['activity'],'trait':trait,'value':value,'reliability':reliability,'context':context,'reason':reason,'actor':actor}
        with self.s.tx():
            old = self.s.db.execute("SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND source='personality-growth-observer' AND source_event_id=?",(self.s.instance_id,key)).fetchone()
            if old:
                if self.s.read_artifact(old['payload_artifact_id'])!=payload: raise Conflict('annotation key reused')
                return old['id']
            for prior in self.events('observed'):
                if prior['opportunity']==opportunity and prior['trait']==trait and not any(e['observation']==prior['id'] for e in self.events('invalidated')): raise Conflict('already annotated; invalidate before correction')
            ref = self.s.event('personality_growth.observed',payload=payload,activity=source['activity'],source='personality-growth-observer',key=key,lane='control')
            self._valid(ref)
            self.s.evidence(object_id=ref,method='controller-annotated-behavior-not-psychometric')
            return ref
    @coordinated
    def invalidate(self, observation, reason, actor):
        self.authority(actor);text(reason,2000);self.event(observation,'observed')
        with self.s.tx():
            prior = next((e for e in self.events('invalidated') if e['observation']==observation),None)
            if prior:return prior['id']
            return self.s.event('personality_growth.invalidated',payload={'observation':observation,'reason':reason,'actor':actor},lane='control')
    def _samples(self, refs, trait, minimum):
        if not isinstance(refs,list) or not minimum<=len(refs)<=50 or len(set(refs))!=len(refs): raise ContractError('distinct observation references required')
        samples = [self._valid(ref) for ref in refs]
        if any(s['trait']!=trait for s in samples) or len({s['activity'] for s in samples})!=len(samples): raise ContractError('distinct activities for one trait required')
        consumed = {a for e in self.events('applied') if e['trait']==trait for a in e['consumed_activities']}
        if any(s['activity'] in consumed for s in samples): raise Conflict('episode already consumed for this trait')
        return samples
    def _limits(self, trait):
        now = datetime.fromisoformat(utc().replace('Z','+00:00'));entries = [e for kind in ('applied','reverted') for e in self.events(kind) if e['trait']==trait]
        elapsed = [(now-datetime.fromisoformat(e['at'].replace('Z','+00:00'))).total_seconds() for e in entries]
        if any(t<86400 for t in elapsed): raise Conflict('personality growth cooling down')
        return max(0,.05-sum(abs(e['delta']) for e,t in zip(entries,elapsed) if t<30*86400))
    def _candidate(self, trait, refs):
        samples = self._samples(refs,trait,3)
        if len({s['context'] for s in samples})<2: raise ContractError('multiple training contexts required')
        total = sum(s['reliability'] for s in samples);mean = sum(s['value']*s['reliability'] for s in samples)/total
        variance = sum(s['reliability']*(s['value']-mean)**2 for s in samples)/total
        if total/len(samples)<.6 or variance>.25: raise Conflict('insufficient or contradictory annotation quality')
        current = Personality(self.s).current();row = next((r for r in current['traits'] if r['name']==trait),None)
        if row is None: raise ContractError('unknown trait')
        limit = min(.02,self._limits(trait));delta = max(-limit,min(limit,.05*(mean-row['central_value'])))
        value = max(-1,min(1,row['central_value']+delta));delta = value-row['central_value']
        if abs(delta)<1e-10: raise Conflict('no remaining justified growth')
        return {'trait':trait,'expected_profile':current['profile']['id'],'old_value':row['central_value'],'value':value,'delta':delta,'observations':refs,
                'statistics':{'n':len(samples),'contexts':len({s['context'] for s in samples}),'weighted_target':mean,'weighted_variance':variance,'mean_reliability':total/len(samples),'status':'controller-annotated-not-psychometrically-calibrated'}}
    @coordinated
    def propose(self, trait, observations, actor):
        self.authority(actor);cfg = self.active()
        with self.s.tx():
            change = dict(self._candidate(trait,observations),configuration=cfg['id'],version=VERSION)
            current = Personality(self.s).current()['profile'];evidence = self._evidence(observations)
            proposal = Learning(self.s).propose('personality',current['profile_object_id'],change,evidence[0],risk=.1)
            for ref in evidence[1:]:self.s.insert('learning_proposal_evidence',proposal_id=proposal,evidence_id=ref,role='support')
            self.s.event('personality_growth.proposed',payload={'proposal':proposal,'change':change},lane='control')
        return {'proposal':proposal,'change':change,'adopted':False}
    def _evidence(self, observations):
        return [self.s.db.execute('SELECT id FROM evidence_items WHERE instance_id=? AND origin_object_id=?',(self.s.instance_id,ref)).fetchone()[0] for ref in observations]
    def _proposal(self, proposal):
        p = self.s.row('learning_update_proposals',proposal);change = json.loads(p['proposed_change'])
        if p['owner_module']!='personality' or change.get('version')!=VERSION: raise ContractError('not a growth proposal')
        if change['configuration']!=self.active()['id']:raise Conflict('growth configuration changed')
        current = self._candidate(change['trait'],change['observations'])
        if any(current[key]!=change[key] for key in current):raise Conflict('baseline, source or growth allowance changed')
        return p,change
    def _measure(self, change, heldout):
        samples = self._samples(heldout,change['trait'],2);training = [self._valid(ref) for ref in change['observations']]
        if {s['activity'] for s in training}&{s['activity'] for s in samples}:raise ContractError('heldout episodes overlap training')
        if not {s['context'] for s in samples}-{s['context'] for s in training}:raise ContractError('unseen heldout context required')
        if sum(s['reliability'] for s in samples)/len(samples)<.6:raise Conflict('heldout annotations insufficient')
        rows = [{'observation':s['id'],'weight':s['reliability'],'before':(change['old_value']-s['value'])**2,'after':(change['value']-s['value'])**2} for s in samples]
        total = sum(r['weight'] for r in rows);benefit = sum(r['weight']*(r['before']-r['after']) for r in rows)/total
        regression = sum(r['after']>r['before']+1e-12 for r in rows)/len(rows)
        return {'heldout':heldout,'rows':rows,'benefit':benefit,'regression':regression,'eligible':benefit>1e-12 and regression==0,'model_calls':0,'tools_executed':0,'method':'two isolated parameter vectors; weighted heldout label loss'}
    @coordinated
    def evaluate(self, proposal, heldout, actor):
        self.authority(actor)
        with self.s.tx():
            p,change = self._proposal(proposal)
            if p['state']=='trial':
                previous = next((e for e in self.events('evaluated') if e['proposal']==proposal),None)
                if previous and previous['measurement']['heldout']==heldout:return previous
                raise Conflict('trial already evaluated')
            if p['state']!='proposed':raise Conflict('proposal consumed')
            measurement = self._measure(change,heldout);artifact = self.s.artifact(measurement)
            trial = Learning(self.s).trial(proposal,VERSION,{'measurement_artifact':artifact,'expected_profile':change['expected_profile']})
            self.s.db.execute("UPDATE evaluation_runs SET state='completed' WHERE id=?",(trial['evaluation'],))
            evaluation = Learning(self.s).evaluate(trial['trial'],trial['evaluation'],measurement['benefit'],measurement['regression'])
            self.s.db.execute('UPDATE learning_update_trials SET ended_at=? WHERE id=?',(utc(),trial['trial']))
            if not measurement['eligible']:self.s.db.execute("UPDATE learning_update_proposals SET state='rejected' WHERE id=?",(proposal,))
            result = {'proposal':proposal,'evaluation':evaluation,'measurement':measurement,'artifact':artifact,'adopted':False}
            self.s.event('personality_growth.evaluated',payload=result,lane='control')
        return result
    @coordinated
    def commit(self, proposal, evaluation, actor):
        self.authority(actor)
        with self.s.tx():
            p,change = self._proposal(proposal);ev = self.s.row('learning_update_evaluations',evaluation);trial = self.s.row('learning_update_trials',ev['trial_id'])
            if p['state']!='trial' or trial['proposal_id']!=proposal or ev['decision']!='accept':raise Conflict('matching accepted trial required')
            run = self.s.row('evaluation_runs',ev['evaluation_run_id'])
            if run['state']!='completed' or run['dataset_version']!=VERSION or trial['baseline_ref']!=run['id']:raise Conflict('measurement provenance mismatch')
            measured = self.s.read_artifact(json.loads(run['conditions'])['measurement_artifact']);rechecked = self._measure(change,measured['heldout'])
            if measured!=rechecked or not rechecked['eligible'] or ev['benefit']!=measured['benefit'] or ev['regression']!=measured['regression']:raise Conflict('heldout measurements not eligible')
            consumed = change['observations']+measured['heldout'];evidence = self._evidence(consumed)
            metadata = dict(change['statistics'],evidence_refs=evidence,heldout=measured['heldout'],evaluation=evaluation,method=VERSION)
            result = Personality(self.s).replace({change['trait']:change['value']},evidence,actor,expected_profile=change['expected_profile'],proposal=proposal,uncertainty={change['trait']:metadata})
            self.s.event('personality_growth.applied',payload=dict(result,trait=change['trait'],delta=change['delta'],at=utc(),proposal=proposal,evaluation=evaluation,observations=consumed,consumed_activities=[self._valid(ref)['activity'] for ref in consumed]),lane='control')
        return result
    @coordinated
    def rollback(self, commit, evidence, actor):
        self.authority(actor)
        original = next((e for e in self.events('applied') if e['commit']==commit),None)
        if original is None:raise ContractError('not a personality growth commit')
        origins = {self.s.row('evidence_items',ref)['origin_object_id'] for ref in evidence}
        if None in origins or len(origins)<2:raise ContractError('two distinct evidence origins required')
        with self.s.tx():
            reversal = Learning(self.s).rollback(commit,evidence,actor)
            self.s.db.execute("UPDATE learning_update_proposals SET state='reverted' WHERE id=?",(original['proposal'],))
            self.s.event('personality_growth.reverted',payload={'commit':commit,'reversal':reversal,'trait':original['trait'],'delta':-original['delta'],'at':utc()},lane='control')
        return {'reversal':reversal}
    def status(self):
        invalid = {e['observation'] for e in self.events('invalidated')};reverted = {e['commit'] for e in self.events('reverted')}
        return {'configuration':self.config(),'profile':Personality(self.s).current(),'opportunities':self.events('opportunity'),'observations':[dict(o,evidence_refs=self._evidence([o['id']])) for o in self.events('observed')],
                'invalidated_commits':[e['commit'] for e in self.events('applied') if set(e['observations'])&invalid and e['commit'] not in reverted],'inference_started':False}
