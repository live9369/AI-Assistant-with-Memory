"""Exact-context repetition candidates. Collection never reinforces behavior."""
import json
from digital_life.domain.contracts import Forbidden, Conflict, ContractError, dumps, sha, text
from digital_life.infrastructure.processes.dispatch_gate import coordinated
from digital_life.application.accounts import account_scope as scope
from digital_life.application.behavior.habit_learning import HabitLearning, canonical


class HabitCandidates:
    def __init__(self, store): self.s = store

    def _latest(self, source, kind=None):
        sql = 'SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND source=?'
        args = [self.s.instance_id, source]
        if kind: sql += ' AND event_type=?'; args.append('habit_candidates.'+kind)
        row = self.s.db.execute(sql+' ORDER BY event_seq DESC LIMIT 1', args).fetchone()
        return dict(self.s.read_artifact(row[1]), revision=row[0]) if row else None

    def config(self):
        return self._latest('habit-candidates', 'configured') or {'enabled': False, 'revision': None}

    def _authority(self, actor):
        if actor != self.s.config()['controller']: raise Forbidden('controller required')

    def _stopped(self):
        from digital_life.application.lifecycle.control_plane import Control
        c = Control(self.s.root, self.s.instance_id)
        try:
            state = c.state()
            if not state['user_stopped'] or state['active_process_run_id']: raise Conflict('stop before habit candidate configuration or decision')
        finally: c.close()

    @coordinated
    def configure(self, enabled, actor):
        self._authority(actor); self._stopped()
        if type(enabled) is not bool: raise ContractError('boolean required')
        with self.s.tx(): self.s.event('habit_candidates.configured', payload={'enabled': enabled, 'actor': actor}, source='habit-candidates', lane='control')
        return self.config()

    def get(self, candidate):
        text(candidate, 64)
        value = self._latest('habit-candidate:'+candidate)
        if value is None: raise ContractError('habit candidate not found')
        return value

    def _sample(self, activity, request, decision, result=None):
        row = self.s.row('activities', activity)
        signal = self.s.row('perception_signals', row['trigger_event_id'])
        if self.s.row('perception_channels', signal['channel_id'])['kind'] != 'user': return None
        attrs = json.loads(self.s.db.execute('SELECT attributes_json FROM context_snapshots WHERE activity_id=?', (activity,)).fetchone()[0])
        if attrs.get('deployment_acceptance') or attrs.get('habit_candidate_excluded') or attrs['source'] not in ('user', 'chat:'+scope.current(self.s)['thread_id'] if scope.active(self.s) else 'user'): return None
        task = attrs['task']
        if not task.strip() or len(task)>200: return None
        req = self.s.row('thought_requests', request)
        if req['activity_id'] != activity or not req['accepted_result_id']: raise Conflict('habit candidate request not accepted')
        accepted = self.s.row('thought_results', req['accepted_result_id'])
        if accepted['acceptance'] != 'accepted': raise Conflict('habit candidate result not accepted')
        links = self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='thought.accepted'", (self.s.instance_id,activity))
        if not any((lambda e: e['request']==request and e['decision']==decision and e['result']==accepted['id'])(self.s.read_artifact(r[0])) for r in links): raise Conflict('habit candidate thought/decision binding mismatch')
        d = self.s.row('decision_records', decision)
        if d['activity_id'] != activity or d['state'] != 'finalized': raise Conflict('habit candidate decision mismatch')
        selected = self.s.db.execute('SELECT * FROM decision_candidates WHERE decision_id=? AND selected=1', (decision,)).fetchone()
        action = canonical(json.loads(selected['action_template']))
        # Check actual input/result artifacts, not a model's account of its action.
        for ref in (req['request_artifact_id'], accepted['response_artifact_id'], signal['artifact_id']):
            value = self.s.read_artifact(ref)
            if not isinstance(value, dict) or 'redacted_by' in value: raise Forbidden('habit candidate source erased')
        if action['tool'] not in ('wait', 'ask'):
            if result is None: return None
            outcome = self.s.row('action_results', result)
            intent = self.s.row('action_intents', self.s.row('action_attempts', outcome['attempt_id'])['intent_id'])
            if intent['candidate_id'] != selected['id'] or outcome['state'] != 'succeeded': return None
            receipt = self.s.read_artifact(outcome['receipt_artifact_id'])
            if receipt.get('verification') != 'pass' or 'redacted_by' in receipt: return None
        from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
        CognitiveUpdates(self.s).source_value(signal['id'])
        return {'activity': activity, 'request': request, 'decision': decision, 'result': result,
                'signal': signal['id'], 'action': action, 'cue': {'source': attrs['source'], 'task_contains': task}}

    def capture(self, activity, request, decision, result=None):
        if not self.config()['enabled']: return None
        if scope.active(self.s):
            owner = scope.current(self.s)
            if not owner or owner['role'] != 'root': return None
            account = owner['id']
        else:
            signal = self.s.row('perception_signals', self.s.row('activities', activity)['trigger_event_id'])
            if signal['source_actor_id'] != self.s.config()['controller']: return None
            account = None
        sample = self._sample(activity, request, decision, result)
        if sample is None: return None
        candidate = sha(dumps({'owner': account, 'cue': sample['cue'], 'action': sample['action']}))
        with self.s.tx():
            old = self._latest('habit-candidate:'+candidate)
            if old and (old['state'] != 'collecting' or any(s['activity']==activity for s in old['samples'])): return old
            samples = (old['samples'] if old else []) + [sample]
            value = {'candidate': candidate, 'owner_account': account, 'cue': sample['cue'], 'action': sample['action'],
                     'samples': samples, 'state': 'pending' if len(samples)>=3 else 'collecting'}
            if old is None:
                self.s.event('habit_candidates.created', payload={'candidate': candidate}, source='habit-candidates', key='candidate:'+candidate, lane='control')
            self.s.event('habit_candidates.sampled', payload=value, source='habit-candidate:'+candidate, key=activity, activity=activity)
        return self.get(candidate)

    def observe(self, activity, request, decision, result=None):
        # Optional learning must not discard an already verified business reply
        # or tool receipt just because its learning source is no longer usable.
        try:
            return self.capture(activity, request, decision, result)
        except (ContractError, OSError, ValueError) as error:
            self.s.event('habit_candidates.skipped', payload={'request': request, 'decision': decision,
                         'reason': type(error).__name__, 'scope': 'candidate collection only'}, activity=activity, lane='telemetry')
            return None

    @coordinated
    def decide(self, candidate, expected_revision, approved, reason, key, actor):
        self._authority(actor); self._stopped(); text(reason, 2000); text(key, 200)
        if type(approved) is not bool: raise ContractError('boolean required')
        with self.s.tx():
            value = self.get(candidate)
            previous = self.s.db.execute('SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=?', (self.s.instance_id, 'habit-candidate:'+candidate, 'decision:'+key)).fetchone()
            if previous:
                prior = self.s.read_artifact(previous[0])
                if prior['approved']!=approved or prior['reason']!=reason or prior['expected_revision']!=expected_revision: raise Conflict('candidate decision key reused')
                return self.get(candidate)
            if value['revision'] != expected_revision or value['state'] not in ('collecting','pending'): raise Conflict('candidate changed or already decided')
            association = None
            if approved:
                if not self.config()['enabled'] or value['state']!='pending' or len({s['activity'] for s in value['samples']})<3: raise Conflict('three distinct current samples required')
                habits = HabitLearning(self.s); habits.active()
                for sample in value['samples']:
                    if scope.active(self.s):
                        owner, _ = scope.activity_owner(self.s, sample['activity'])
                        if owner != value['owner_account'] or scope.principal(self.s,owner)['role']!='root': raise Forbidden('candidate owner changed')
                        with scope.audience(self.s, owner): verified = self._sample(sample['activity'],sample['request'],sample['decision'],sample['result'])
                    else: verified = self._sample(sample['activity'],sample['request'],sample['decision'],sample['result'])
                    if verified != sample: raise Forbidden('candidate source changed or unavailable')
                state = habits.enroll(value['action'], value['cue'], 'candidate:'+candidate, actor, owner_account=value['owner_account'])
                association = state['association']
                if state['consumed_activities']: raise Conflict('candidate habit already has learning history')
                after = habits._state(state)
                after.update(acquisition=.3, state='active', positive_activities=[s['activity'] for s in value['samples']], consumed_activities=[s['activity'] for s in value['samples']])
                habits._change(association,state,after,'reviewed-adoption',{'candidate':candidate,'actor':actor,'reason':reason,'samples':value['samples'],'not_automatic_reward':True})
            value = {k:v for k,v in value.items() if k!='revision'}
            value.update(state='confirmed' if approved else 'rejected', approved=approved, reason=reason, expected_revision=expected_revision, association=association, actor=actor)
            self.s.event('habit_candidates.decided', payload=value, source='habit-candidate:'+candidate, key='decision:'+key, lane='control')
        return self.get(candidate)

    def status(self):
        rows = self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND source='habit-candidates' AND event_type='habit_candidates.created' ORDER BY event_seq DESC LIMIT 100", (self.s.instance_id,))
        return {'configuration': self.config(), 'items': [self.get(self.s.read_artifact(r[0])['candidate']) for r in rows],
                'limit': 100, 'scope': 'root exact-context action candidates; no automatic activation', 'inference_started': False}
