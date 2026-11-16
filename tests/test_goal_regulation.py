"""T05 isolated goal competition, resource guards and explicit thought context."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.behavior.goal_regulation import GoalRegulation
from digital_life.application.services.states import States
from digital_life.application.runtime.scheduling import Queue
from digital_life.domain.contracts import Forbidden, Conflict, ContractError, utc


class Model:
    name = 'fixture'
    def __init__(self): self.inputs = []
    def generate(self, payload):
        self.inputs.append(payload)
        return {'schema_version': 1, 'explanation': 'test reply', 'action': {'tool': 'wait', 'arguments': {'reason': 'wait'}}}


class GoalRegulationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'isolated'
        self.s = Store.prepare(self.root); self.addCleanup(self.s.close)
        self.engine = Engine(self.s); self.g = GoalRegulation(self.s); self.actor = self.s.config()['controller']

    def unlock(self):
        (self.root/'WAKE_DISABLED').unlink(missing_ok=True)
        if (self.root/'control.sqlite').exists():
            from digital_life.application.lifecycle.control_plane import Control
            c = Control(self.root, self.s.instance_id); c.resume('isolated-t05'); c.close()

    def enable(self): self.g.configure(True, self.actor)
    def submit(self, key): return self.engine.submit(key, key)
    def healthy(self): self.g.refresh(force=True)
    def observe(self, name, value):
        evidence = self.s.evidence(artifact=self.s.artifact({'fixture': name, 'value': value}), method='isolated-fixture')
        States(self.s).observe(name, value, 'fixture', evidence)

    def test_disabled_keeps_fifo_and_old_payload(self):
        first = self.submit('first'); self.submit('second'); self.unlock(); m = Model()
        self.engine.process_one(m)
        self.assertEqual(m.inputs[0]['activity_id'], first)
        self.assertNotIn('goal_regulation', m.inputs[0])

    def test_priority_changes_actual_first_independent_call(self):
        self.enable(); first = self.submit('first'); second = self.submit('second')
        self.g.prioritize(first, {'importance': 0, 'expectancy': 0, 'cost': 1}, self.actor)
        self.g.prioritize(second, {'importance': 1, 'expectancy': 1, 'cost': 0}, self.actor)
        self.unlock(); m = Model(); self.engine.process_one(m); self.engine.process_one(m)
        self.assertEqual([p['activity_id'] for p in m.inputs], [second, first])
        self.assertEqual(len({p['activity_id'] for p in m.inputs}), 2)
        p = m.inputs[0]['goal_regulation']; self.assertTrue(p['eligible']); self.assertTrue(p['motivation_ref'])
        self.assertGreaterEqual(p['score'],0);self.assertLessEqual(p['score'],1)
        self.assertAlmostEqual(p['score'], max(0, min(1, sum(p['factors'].values()))),places=12)
        self.assertTrue(all(v['ref'] and v['source_ref'] and v['fresh'] for v in p['states'].values()))
        self.assertEqual(self.s.integrity(), {'integrity': 'ok', 'foreign_keys': []})

    def test_missing_state_is_not_health(self):
        self.enable(); a = self.submit('a')
        r = self.g.assess(a); self.assertFalse(r['eligible']); self.assertEqual(len(r['reasons']), 4)
        self.assertEqual(r['intensity'], 0)

    def test_stale_and_invalid_quality_are_blocking(self):
        self.enable(); a = self.submit('a'); self.healthy()
        self.s.db.execute("UPDATE state_observations SET observed_at=?", (utc(-120),))
        self.assertFalse(self.g.assess(a)['eligible'])
        self.healthy(); self.s.db.execute("UPDATE state_observations SET quality='missing'")
        self.assertFalse(self.g.assess(a)['eligible'])

    def test_low_disk_prevents_model_and_retains_queue(self):
        self.g.configure(True, self.actor, min_disk_bytes=10**18); self.submit('a'); self.unlock(); m = Model()
        self.assertIsNone(self.engine.process_one(m)); self.assertEqual(m.inputs, [])
        self.assertEqual(self.s.rows('jobs')[0]['state'], 'queued')
        self.assertIn('disk_floor', self.g.latest('competition')['candidates'][0]['reasons'])
        self.engine.process_one(m)
        self.assertEqual(sum(e['event_type']=='goal_regulation.competition' for e in self.s.rows('runtime_events')), 1)

    def test_database_and_restore_state_guards(self):
        self.enable(); a = self.submit('a'); self.healthy()
        self.observe('F.sqlite_integrity', 0); self.assertIn('database_unhealthy', self.g.assess(a)['reasons'])
        self.healthy(); self.observe('F.restore_reconciliation_required', 1)
        self.assertIn('restore_required', self.g.assess(a)['reasons'])

    def test_deadline_and_cancel_block_thought(self):
        self.enable(); a = self.submit('a'); self.s.db.execute('UPDATE activities SET deadline=? WHERE id=?', (utc(-1), a))
        self.unlock(); m = Model(); self.assertIsNone(self.engine.process_one(m)); self.assertFalse(m.inputs)
        self.engine.cancel(a, self.actor); self.assertIn('cancel_requested', self.g.assess(a)['reasons'])

    def test_token_and_attempt_limits_block_before_dispatch(self):
        self.enable(); a = self.submit('a'); self.unlock(); m = Model()
        self.s.db.execute('UPDATE activity_budget_accounts SET token_limit=4000 WHERE activity_id=?', (a,))
        self.assertIsNone(self.engine.process_one(m)); self.assertFalse(m.inputs)
        self.s.db.execute('UPDATE activity_budget_accounts SET token_limit=16000,attempt_limit=0 WHERE activity_id=?', (a,))
        self.assertIn('budget_exhausted', self.g.assess(a)['reasons'])

    def test_cost_and_load_reduce_score_without_deadlock(self):
        self.enable(); a = self.submit('a'); b = self.submit('b')
        self.g.prioritize(a, {'cost': 0}, self.actor); self.g.prioritize(b, {'cost': 1}, self.actor); self.healthy()
        self.assertGreater(self.g.assess(a)['score'], self.g.assess(b)['score'])
        before = self.g.assess(a)['score']; self.observe('W.queue_depth', 10000)
        self.assertLess(self.g.assess(a)['score'], before); self.assertTrue(self.g.assess(a)['eligible'])

    def test_value_alignment_uses_current_profile(self):
        self.enable(); a = self.submit('a'); dims = self.s.rows('value_dimensions')
        self.g.prioritize(a, {'alignment': {dims[0]['id']: 1}}, self.actor); self.healthy()
        result = self.g.assess(a)
        expected = sum(r['weight']*(1 if r['dimension_id']==dims[0]['id'] else .5) for r in result['value_weights'])
        self.assertAlmostEqual(result['factors']['value_alignment'], .25*expected)
        from digital_life.application.services.values import Values
        refs = [self.s.evidence(artifact=self.s.artifact({'case': i})) for i in range(2)]
        Values(self.s).replace({d['id']: int(d['id']==dims[0]['id']) for d in dims}, refs, self.actor)
        self.assertAlmostEqual(self.g.assess(a)['factors']['value_alignment'], .25)

    def test_authority_validation_and_configuration_stop_guard(self):
        with self.assertRaises(Forbidden): self.g.configure(True, 'not-controller')
        for value in (True, float('nan'), -1, 2, '1'):
            a = self.submit(str(value))
            with self.assertRaises(ContractError): self.g.prioritize(a, {'importance': value}, self.actor)
        with self.assertRaises(ContractError): self.g.configure(True, self.actor, -1)
        self.enable(); self.unlock()
        with self.assertRaises(Conflict): self.g.configure(False, self.actor)

    def test_prepared_request_immutable_and_features_cannot_change(self):
        self.enable(); a = self.submit('a'); self.unlock(); m = Model()
        request, payload = self.engine.prepare(a, m)
        with self.assertRaises(Conflict): self.g.prioritize(a, {'importance': 1}, self.actor)
        again, snapshot = self.engine.prepare(a, m)
        self.assertEqual(request['id'], again['id']); self.assertEqual(payload, snapshot)

    def test_superseded_configuration_rejected_before_model(self):
        self.enable(); a = self.submit('a'); self.unlock(); m = Model(); self.engine.prepare(a, m)
        from digital_life.application.lifecycle.control_plane import Control
        c = Control(self.root, self.s.instance_id); c.stop('isolated'); c.close()
        self.g.configure(False, self.actor)
        c = Control(self.root, self.s.instance_id); c.resume('isolated'); c.close()
        with self.assertRaises(Forbidden): self.engine.think(a, m)
        self.assertFalse(m.inputs)

    def test_freshness_rechecked_at_dispatch(self):
        self.enable(); a = self.submit('a'); self.unlock(); m = Model(); self.engine.prepare(a, m)
        self.s.db.execute('UPDATE state_observations SET observed_at=?', (utc(-120),))
        old_count=len(self.s.rows('state_observations'))
        self.engine.think(a, m)
        self.assertEqual(len(m.inputs),1)
        self.assertGreater(len(self.s.rows('state_observations')),old_count)
        evidence=self.g.latest('dispatch_health',a)
        self.assertTrue(evidence['eligible'])
        for name in ('R.disk_free_bytes','F.sqlite_integrity','F.restore_reconciliation_required','W.queue_depth'):
            self.assertEqual(evidence['probes'][name]['status'],'known')

    def test_stale_health_still_blocks_when_refresh_produces_no_current_evidence(self):
        self.enable(); a = self.submit('a'); self.unlock(); m = Model(); self.engine.prepare(a, m)
        self.s.db.execute('UPDATE state_observations SET observed_at=?', (utc(-120),))
        with patch('digital_life.application.learning.health.shutil.disk_usage',side_effect=OSError('probe unavailable')):
            with self.assertRaises(Forbidden): self.engine.think(a, m)
        self.assertFalse(m.inputs)

    def test_non_think_jobs_keep_lease_and_approval_boundary(self):
        self.enable(); a = self.submit('a'); job_id = Queue(self.s).enqueue('execute', a)
        claimed = self.g.claim('isolated-worker')
        self.assertEqual(claimed['id'], job_id); self.assertEqual(claimed['lease_generation'], 1)
        Queue(self.s).finish(claimed)
        with self.assertRaises(Conflict): Queue(self.s).finish(claimed)

    def test_persistent_context_reopen_and_thought_inspection(self):
        self.enable(); a = self.submit('a'); self.unlock(); m = Model(); self.engine.think(a, m)
        request = self.s.rows('thought_requests')[0]['id']; identity = self.s.instance_id
        self.s.close(); self.s = Store(self.root); self.addCleanup(self.s.close)
        self.assertEqual(self.s.instance_id, identity); self.assertTrue(GoalRegulation(self.s).config()['enabled'])
        from digital_life.application.monitoring.thought_inspection import ThoughtInspection
        details = ThoughtInspection(self.s).detail(request)
        self.assertIn('goal_regulation', details['input']['value'])
        self.assertTrue(any(i['field']=='goal_regulation' and i['state']=='provided' for f in details['features'] for i in f['items']))
        self.assertEqual(self.s.integrity()['foreign_keys'], [])

    def test_time_budget_and_goal_terminal_state(self):
        self.enable(); a = self.submit('a'); self.healthy()
        self.s.db.execute('UPDATE activity_budget_accounts SET time_limit_ms=0 WHERE activity_id=?', (a,))
        self.assertIn('time_budget_exhausted', self.g.assess(a)['reasons'])
        self.s.db.execute('UPDATE activity_budget_accounts SET time_limit_ms=600000 WHERE activity_id=?', (a,))
        from digital_life.application.services.goals import Goals
        goal = self.engine.details(a)[3]
        Goals(self.s).transition(goal['id'], 'completed', self.s.row('activities', a)['trigger_event_id'])
        self.assertIn('goal_not_active', self.g.assess(a)['reasons'])

    def test_remaining_budget_reduces_motivation_and_changes_selection(self):
        self.enable(); a = self.submit('a'); b = self.submit('b'); self.healthy()
        self.g.prioritize(a, {'importance': 1}, self.actor)
        self.g.prioritize(b, {'importance': .8}, self.actor)
        self.assertGreater(self.g.assess(a)['intensity'], self.g.assess(b)['intensity'])
        # Actual reservation on a registered operation; not an invented consumption observation.
        from digital_life.application.runtime.scheduling import Budget
        Budget(self.s).reserve(a, a, 'thought_attempt', 11000)
        self.assertTrue(self.g.assess(a)['eligible'])
        self.assertLess(self.g.assess(a)['intensity'], self.g.assess(b)['intensity'])
        self.assertEqual(self.g.claim('worker')['target_ref'], b)

    def test_idle_poll_does_not_grow_state_history(self):
        self.enable(); self.assertIsNone(self.g.claim('worker'))
        self.assertEqual(self.s.rows('state_observations'), [])

    def test_preferred_queue_claim_never_steals_active_lease(self):
        a = self.submit('a'); job = Queue(self.s).claim('first')
        self.assertIsNone(Queue(self.s).claim('second', preferred_job=job['id']))
        self.assertEqual(job['target_ref'], a)

    def test_final_available_budget_can_dispatch_once(self):
        self.enable(); a = self.submit('a'); self.unlock(); m = Model()
        self.s.db.execute('UPDATE activity_budget_accounts SET token_limit=4096,attempt_limit=1 WHERE activity_id=?', (a,))
        self.engine.process_one(m); self.assertEqual(len(m.inputs), 1)
        self.assertIn('budget_exhausted', self.g.assess(a)['reasons'])
        self.assertEqual(self.g.latest('assessed', a)['motivation_ref'], m.inputs[0]['goal_regulation']['motivation_ref'])

    def test_unknown_features_and_alignment_never_mutate_goal(self):
        a = self.submit('a')
        for features in ({'invented': 1}, {'alignment': {'unknown': 1}}, {'alignment': []}):
            with self.assertRaises(ContractError): self.g.prioritize(a, features, self.actor)
        self.assertIsNone(self.g.latest('prioritized', a))

    def test_cli_configuration_and_status_do_not_wake(self):
        import argparse
        from digital_life.entrypoints.growth import parsers, handle
        parser = argparse.ArgumentParser(); parsers(parser.add_subparsers(dest='command'))
        result = handle(self.s, parser.parse_args(['goal-regulation', 'enable']))
        self.assertTrue(result['enabled']); self.assertTrue((self.root/'WAKE_DISABLED').exists())
        before = len(self.s.rows('runtime_events'))
        result = handle(self.s, parser.parse_args(['goal-regulation', 'status']))
        self.assertFalse(result['inference_started']); self.assertEqual(before, len(self.s.rows('runtime_events')))

    def test_backdated_observation_does_not_replace_latest(self):
        self.enable(); a = self.submit('a'); self.healthy()
        self.observe('R.disk_free_bytes', 0)
        ref = self.s.db.execute('SELECT id FROM state_observations ORDER BY rowid DESC LIMIT 1').fetchone()[0]
        self.s.db.execute('UPDATE state_observations SET observed_at=? WHERE id=?', (utc(-300), ref))
        self.assertTrue(self.g.assess(a)['eligible'])

    def test_enabled_policy_preserves_multiround_tool_approval_and_goal_verification(self):
        from digital_life.application.autonomy.task_loop import TaskLoop
        from digital_life.application.accounts.authorization import Policy
        self.enable(); a = self.submit('read then write')
        TaskLoop(self.s).configure(a, {'kind': 'file_contains', 'path': 'answer.txt', 'text': 'done'}, self.actor)
        (self.root/'workspace/source.txt').write_text('source material'); self.unlock()
        class ToolModel(Model):
            def generate(inner, payload):
                inner.inputs.append(payload)
                action = {'tool': 'read_file', 'arguments': {'path': 'source.txt'}} if len(inner.inputs)==1 else {'tool': 'write_note', 'arguments': {'path': 'answer.txt', 'text': 'done'}}
                return {'schema_version': 1, 'explanation': 'next bounded step', 'action': action}
        m = ToolModel()
        for _ in range(2):
            proposal = self.engine.process_one(m)
            with self.assertRaises(Forbidden): self.engine.execute(proposal['action_id'])
            Policy(self.s).approve(proposal['approval_id'], self.actor)
            self.engine.process_one(m)
        self.assertEqual(self.s.row('activities', a)['state'], 'completed')
        self.assertEqual(len(m.inputs), 2)
        self.assertEqual([p['task_loop']['round'] for p in m.inputs], [1, 2])
        self.assertGreater(m.inputs[0]['goal_regulation']['intensity'], m.inputs[1]['goal_regulation']['intensity'])
        self.assertEqual(self.s.integrity()['foreign_keys'], [])

    def test_claim_and_context_use_current_measurement_when_history_is_stale(self):
        self.enable();activity=self.submit('current-health');self.healthy()
        self.s.db.execute('UPDATE state_observations SET observed_at=?',(utc(-120),))
        self.assertFalse(self.g.assess(activity)['eligible'])
        with patch.object(self.g,'refresh',return_value=None):
            claimed=self.g.claim('current-health-worker')
            context=self.g.context(activity)
        self.assertIsNotNone(claimed)
        self.assertTrue(context['eligible'])
        for stage in ('claim','context'):
            evidence=self.g.latest(stage+'_health',activity)
            self.assertTrue(evidence['database_unchanged'])
            self.assertEqual(evidence['freshness_basis'],'measurement_completed')

    def test_native_claim_does_not_hold_write_transaction_during_health_checks(self):
        self.enable();self.submit('unlocked-health')
        refresh=self.g.refresh;assess=self.g._native_assess
        def checked_refresh(*args,**kwargs):
            self.assertFalse(self.s.db.in_transaction)
            return refresh(*args,**kwargs)
        def checked_assess(*args,**kwargs):
            self.assertFalse(self.s.db.in_transaction)
            return assess(*args,**kwargs)
        with patch.object(self.g,'refresh',side_effect=checked_refresh),patch.object(self.g,'_native_assess',side_effect=checked_assess):
            self.assertIsNotNone(self.g.claim('unlocked-worker'))
    def test_cancel_between_scheduling_assessment_and_lease_is_not_resurrected(self):
        self.enable();activity=self.submit('cancel-during-selection');assess=self.g._native_assess
        def cancelled_after_assessment(*args,**kwargs):
            result=assess(*args,**kwargs)
            self.engine.cancel(activity,self.actor)
            return result
        with patch.object(self.g,'_native_assess',side_effect=cancelled_after_assessment):
            self.assertIsNone(self.g.claim('cancelled-worker'))
        self.assertEqual(self.s.row('activities',activity)['state'],'cancelled')
        self.assertEqual(self.s.rows('jobs')[0]['state'],'cancelled')
