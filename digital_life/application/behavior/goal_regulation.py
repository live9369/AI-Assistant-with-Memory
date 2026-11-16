"""Opt-in, explainable goal scheduling; scores are engineering estimates."""
import math
import json
from datetime import datetime,timedelta
from digital_life.domain.contracts import ContractError, Conflict, Forbidden, utc
from digital_life.infrastructure.processes.dispatch_gate import coordinated
from digital_life.application.services.states import States
from digital_life.application.runtime.scheduling import Queue


class GoalRegulation:
    def __init__(self, store): self.s = store

    def latest(self, kind, activity=None):
        sql = 'SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type=?'
        args = [self.s.instance_id, 'goal_regulation.' + kind]
        if activity is not None:
            sql += ' AND activity_id=?'; args.append(activity)
        row = self.s.db.execute(sql + ' ORDER BY event_seq DESC LIMIT 1', args).fetchone()
        return dict(self.s.read_artifact(row['payload_artifact_id']), event_id=row['id']) if row else None

    def config(self):
        return self.latest('configured') or {'enabled': False, 'min_disk_bytes': 67108864, 'event_id': None}

    @coordinated
    def configure(self, enabled, actor, min_disk_bytes=67108864):
        if actor != self.s.config()['controller']: raise Forbidden('controller required')
        if type(enabled) is not bool or type(min_disk_bytes) is not int or min_disk_bytes < 0:
            raise ContractError('boolean enabled and nonnegative integer disk floor required')
        from digital_life.application.lifecycle.control_plane import Control
        c = Control(self.s.root, self.s.instance_id)
        try:
            state = c.state()
            if not state['user_stopped'] or state['active_process_run_id']: raise Conflict('stop before regulation configuration')
        finally: c.close()
        with self.s.tx():
            self.s.event('goal_regulation.configured', payload={'enabled': enabled, 'min_disk_bytes': min_disk_bytes, 'actor': actor}, lane='control')
        return self.config()

    @coordinated
    def prioritize(self, activity, features, actor):
        if actor != self.s.config()['controller']: raise Forbidden('controller required')
        allowed = {'importance', 'expectancy', 'cost', 'risk', 'alignment'}
        if not isinstance(features, dict) or set(features) - allowed: raise ContractError('unknown goal features')
        clean = {'importance': .5, 'expectancy': .5, 'cost': .5, 'risk': 0., 'alignment': {}}
        clean.update(features)
        def number(v):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1:
                raise ContractError('features must be finite numbers in [0,1]')
        for key in allowed - {'alignment'}: number(clean[key])
        if not isinstance(clean['alignment'], dict): raise ContractError('alignment mapping required')
        known = {r['id'] for r in self.s.rows('value_dimensions')}
        for key, value in clean['alignment'].items():
            if key not in known: raise ContractError('unknown value dimension')
            number(value)
        with self.s.tx():
            row = self.s.row('activities', activity)
            if row['state'] != 'pending' or row['cancel_requested_at'] or self.s.db.execute('SELECT 1 FROM thought_requests WHERE activity_id=?', (activity,)).fetchone():
                raise Conflict('prioritize only before thought preparation')
            self.s.event('goal_regulation.prioritized', payload={'features': clean, 'actor': actor}, activity=activity, lane='control')
        return clean

    def assess(self, activity, required_tokens=4096, required_attempts=1, current_health=None):
        cfg = self.config(); row = self.s.row('activities', activity)
        features = self.latest('prioritized', activity)
        f = features['features'] if features else {'importance': .5, 'expectancy': .5, 'cost': .5, 'risk': 0., 'alignment': {}}
        if current_health is not None:
            from digital_life.application.learning.health import CurrentHealthEvidence,CurrentHealthProbe
            if type(current_health)is CurrentHealthProbe:
                current_health=current_health.measure(self.s,activity)
            if current_health is CurrentHealthEvidence:
                current_health=CurrentHealthEvidence(self.s,activity,{'kind':'activities','id':activity})
            if type(current_health) is not CurrentHealthEvidence:raise Forbidden('actual current health evidence required')
            states=current_health.consume(self.s,activity)
        else:states=States(self.s).snapshot()
        reasons = []
        required = ('R.disk_free_bytes', 'F.sqlite_integrity', 'F.restore_reconciliation_required', 'W.queue_depth')
        for name in required:
            if name not in states or not states[name]['fresh']: reasons.append('state_missing_or_stale:' + name)
        if not reasons:
            if states[required[0]]['value'] < cfg['min_disk_bytes']: reasons.append('disk_floor')
            if states[required[1]]['value'] != 1: reasons.append('database_unhealthy')
            if states[required[2]]['value'] != 0: reasons.append('restore_required')
        if row['state'] not in ('pending', 'running'): reasons.append('activity_not_startable')
        if row['cancel_requested_at']: reasons.append('cancel_requested')
        goal = self.s.db.execute('SELECT id,state,due_at FROM goal_items WHERE source_ref=? AND instance_id=?', (row['trigger_event_id'], self.s.instance_id)).fetchone()
        if not goal or goal['state'] not in ('accepted', 'active'): reasons.append('goal_not_active')
        if goal and goal['due_at'] and goal['due_at'] <= utc(): reasons.append('goal_deadline')
        remaining = (datetime.fromisoformat(row['deadline'].replace('Z', '+00:00')) - datetime.fromisoformat(utc().replace('Z', '+00:00'))).total_seconds() if row['deadline'] else 600
        if remaining <= 0: reasons.append('deadline')
        if goal and goal['due_at']:
            remaining = min(remaining, (datetime.fromisoformat(goal['due_at'].replace('Z', '+00:00')) - datetime.fromisoformat(utc().replace('Z', '+00:00'))).total_seconds())
        account = self.s.db.execute('SELECT * FROM activity_budget_accounts WHERE activity_id=?', (activity,)).fetchone()
        reservations = self.s.db.execute("SELECT * FROM budget_reservations WHERE activity_id=? AND state<>'released'", (activity,)).fetchall()
        tokens = account['token_limit'] - sum(r['reserved_tokens'] for r in reservations) if account else 0
        attempts = account['attempt_limit'] - len(reservations) if account else 0
        document=json.loads(row['budget_json'])
        if document.get('contract')=='TL-ACTIVITY-BUDGET-1':
            from digital_life.application.learning.activity_budget import ActivityResourceBudget
            actual=ActivityResourceBudget(self.s).check_activity(activity)
            tokens=actual['remaining']['tokens'];attempts=actual['remaining']['attempts']
            reasons.extend(reason for reason in actual['block_reasons'] if reason!='attempts_exhausted')
        if account:
            elapsed = (datetime.fromisoformat(utc().replace('Z', '+00:00')) - datetime.fromisoformat(row['recorded_at'].replace('Z', '+00:00'))).total_seconds()*1000
            if elapsed >= account['time_limit_ms']: reasons.append('time_budget_exhausted')
        if not account or tokens < required_tokens or attempts < required_attempts: reasons.append('budget_exhausted')
        budget_fraction = max(0, min(tokens / max(1, account['token_limit']), attempts / max(1, account['attempt_limit']))) if account else 0
        profile = max(self.s.rows('value_profiles'), key=lambda r: r['version'])
        weights = [dict(r) for r in self.s.db.execute('SELECT id,dimension_id,weight FROM value_weights WHERE profile_id=?', (profile['id'],))]
        alignment = sum(w['weight'] * f['alignment'].get(w['dimension_id'], .5) for w in weights)
        depth = max(0, states.get('W.queue_depth', {}).get('value', 0)); load = depth / (depth + 10)
        factors = {'importance': .35*f['importance'], 'value_alignment': .25*alignment, 'expectancy': .25*f['expectancy'], 'urgency': .15*max(0, min(1, 1-remaining/600)), 'cost': -.20*f['cost'], 'risk': -.20*f['risk'], 'load': -.10*load}
        score = max(0, min(1, sum(factors.values())))
        return {'strategy': 'goal-regulation-v1', 'configuration': cfg['event_id'], 'activity': activity, 'goal': goal['id'] if goal else None, 'eligible': not reasons, 'reasons': reasons,
                'features': f, 'feature_source': features['event_id'] if features else 'engineering-defaults-v1', 'states': {n: states.get(n) for n in required},
                'value_profile': profile['id'], 'value_weights': weights, 'factors': factors, 'score': score,
                'budget': {'remaining_reserved_tokens': tokens, 'remaining_attempts': attempts, 'fraction': budget_fraction},
                'intensity': score*budget_fraction if not reasons else 0, 'persistence': budget_fraction, 'satiation': 0}

    def refresh(self, force=False):
        required = ('R.disk_free_bytes', 'F.sqlite_integrity', 'F.restore_reconciliation_required', 'W.queue_depth')
        snapshot = States(self.s).snapshot(required)
        if not force and all(n in snapshot and snapshot[n]['fresh'] and snapshot[n]['expires_at'] > utc(5) for n in required): return
        from digital_life.application.telemetry.states import StateCollector
        StateCollector(self.s).collect()

    def _native_assess(self,activity,stage,required_tokens=4096,required_attempts=1):
        from digital_life.application.learning.runtime import qualified_plane_required
        from digital_life.application.learning.health import CurrentHealthProbe
        if qualified_plane_required(self.s):raise Forbidden('native health assessment cannot serve strict activities')
        if stage in ('claim','context') and required_tokens==4096:
            from digital_life.application.autonomy.task_loop import TaskLoop
            budget=TaskLoop(self.s).project_budget(activity)
            if budget is not None:required_tokens=max(1024,min(4096,budget['tokens']))
        probe=CurrentHealthProbe(self.s,activity,{'kind':'activities','id':activity},completion_freshness=True)
        result=self.assess(activity,required_tokens=required_tokens,required_attempts=required_attempts,current_health=probe)
        with self.s.tx():
            event=self.s.event('goal_regulation.'+stage+'_health',payload=dict(probe.audit(),eligible=result['eligible'],reasons=result['reasons'],state_observations_written=True),activity=activity,lane='control')
            evidence=self.s.evidence(object_id=event,method='actual-current-health-probe')
            units={'R.disk_free_bytes':'bytes','F.sqlite_integrity':'boolean','F.restore_reconciliation_required':'boolean','W.queue_depth':'count'}
            for name,state in result['states'].items():
                ref=States(self.s).observe(name,state['value'],units[name],evidence,ttl=30)
                observation=self.s.row('state_observations',ref);definition=self.s.row('state_definitions',observation['definition_id'])
                expires=(datetime.fromisoformat(observation['observed_at'].replace('Z','+00:00'))+timedelta(seconds=definition['ttl'])).isoformat().replace('+00:00','Z')
                result['states'][name]={'value':state['value'],'fresh':expires>utc(),'ref':ref,'source_ref':evidence,'observed_at':observation['observed_at'],'expires_at':expires,'unit':definition['unit']}
        return result

    def context(self, activity):
        if not self.config()['enabled']: return None
        from digital_life.application.learning.runtime import qualified_plane_required
        from digital_life.application.learning.health import CurrentHealthEvidence
        strict=qualified_plane_required(self.s)
        if not strict:self.refresh()
        with self.s.tx():
            result = self.assess(activity,current_health=CurrentHealthEvidence) if strict else self._native_assess(activity,'context')
            if result['eligible']:
                trigger = self.s.row('activities', activity)['trigger_event_id']
                goal = self.s.db.execute('SELECT id FROM goal_items WHERE source_ref=? AND instance_id=?', (trigger, self.s.instance_id)).fetchone()
                result['motivation_ref'] = self.s.insert('motivation_states', goal_id=goal['id'], activity_id=activity,
                    intensity=result['intensity'], source_type='goal-regulation-v1', regulation_type='resource-aware',
                    persistence=result['persistence'], satiation=0, budget=result['budget'])
            self.s.event('goal_regulation.assessed', payload=result, activity=activity)
        if not result['eligible']: raise Forbidden('goal deferred: ' + ','.join(result['reasons']))
        return result

    def check(self, activity, payload):
        if not self.check_binding(payload):return
        from digital_life.application.learning.runtime import qualified_plane_required
        if not qualified_plane_required(self.s):result=self._native_assess(activity,'dispatch',required_tokens=0,required_attempts=0)
        else:result = self.assess(activity, required_tokens=0, required_attempts=0)
        if not result['eligible']: raise Forbidden('goal dispatch deferred: ' + ','.join(result['reasons']))

    def check_binding(self,payload):
        pinned = payload.get('goal_regulation'); cfg = self.config()
        if not cfg['enabled'] and pinned is None: return False
        if not pinned or not cfg['enabled'] or pinned['configuration'] != cfg['event_id']:
            raise Forbidden('goal regulation configuration superseded')
        return True

    def claim(self, worker, seconds=360):
        if not self.config()['enabled']: return Queue(self.s).claim(worker, seconds)
        from contextlib import nullcontext
        from digital_life.application.learning.runtime import qualified_plane_required
        strict=qualified_plane_required(self.s)
        with self.s.tx() if strict else nullcontext():
            jobs = self.s.db.execute("SELECT * FROM jobs WHERE instance_id=? AND due_at<=? AND (state='queued' OR (state='leased' AND lease_expiry<=?)) ORDER BY due_at,id", (self.s.instance_id, utc(), utc())).fetchall()
            if not jobs: return None
            self.refresh()
            other = next((r for r in jobs if r['kind'] != 'think'), None)
            if other: return Queue(self.s).claim(worker, seconds, preferred_job=other['id'])
            from digital_life.application.learning.runtime import qualified_plane_required
            strict=qualified_plane_required(self.s)
            candidates = [(r, self.assess(r['target_ref']) if strict else self._native_assess(r['target_ref'],'claim')) for r in jobs]
            eligible = [(r, a) for r, a in candidates if a['eligible']]
            selected = min(eligible, key=lambda pair: (-pair[1]['intensity'], pair[0]['due_at'], pair[0]['id'])) if eligible else None
            previous = self.latest('competition')
            signature = [(a['activity'], a['reasons']) for r, a in candidates]
            previous_signature = [(a['activity'], a['reasons']) for a in previous['candidates']] if previous else None
            if candidates and (selected or signature != previous_signature):
                payload={'candidates': [a for r, a in candidates], 'selected_job': selected[0]['id'] if selected else None}
                if strict:self.s.event('goal_regulation.competition',payload=payload)
                else:
                    with self.s.tx():self.s.event('goal_regulation.competition',payload=payload)
            return Queue(self.s).claim(worker, seconds, preferred_job=selected[0]['id']) if selected else None

    def status(self):
        return {'config': self.config(), 'latest_competition': self.latest('competition'), 'latest_assessment': self.latest('assessed'), 'inference_started': False}
