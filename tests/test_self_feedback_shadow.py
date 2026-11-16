"""Stage 1: immutable sidecar records and arithmetic without choice changes."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.application.learning.self_feedback import SelfFeedback
from digital_life.application.behavior.interest_model import InterestModel
from digital_life.application.services.memory import Memory
from digital_life.domain.contracts import ContractError,Forbidden,utc
from evaluation.exploration.harness import Harness

ROOT=Path(__file__).resolve().parents[1]

class ShadowJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();cases=json.loads((ROOT/'evaluation/exploration/materials/cases-v1.json').read_text())['cases']
        self.h=Harness(Path(self.tmp.name)/'instance',next(c for c in cases if c['case_id']=='B01'))
        self.sf=SelfFeedback(self.h.s);self.actor=self.h.s.config()['controller']
    def tearDown(self):self.h.close();self.tmp.cleanup()
    def enable(self):self.sf.configure(self.actor,True)
    def records(self,kind):
        if kind=='assessment':
            from digital_life.application.services.learning import Learning
            return Learning(self.h.s).experience_assessments()
        return self.sf._events(kind)
    def finish(self):a=self.h.investigation();p,out=self.h.finish(a);return a,p,out
    def test_default_off_records_nothing(self):
        self.finish();self.assertFalse(self.sf.configuration()['enabled']);self.assertEqual(self.sf._events('intent'),[])
    def test_configuration_and_projection_require_controller(self):
        for fn in (lambda:self.sf.configure('other',True),lambda:self.sf.shadow_interest('other')):
            with self.assertRaises(Forbidden):fn()
        with self.assertRaises(ContractError):self.sf.configure(self.actor,1)
    def test_real_temporary_observation_has_full_chain_and_unknown_gain(self):
        self.enable();a,p,out=self.finish()
        for kind in ('snapshot','intent','binding','expectation','observation','opportunity','assessment'):self.assertEqual(len(self.records(kind)),1,kind)
        expectation=self.sf._events('expectation')[0];observation=self.sf._events('observation')[0]
        self.assertLess(expectation['seq'],observation['seq']);self.assertTrue(expectation['payload']['prepared_before_dispatch'])
        self.assertIsNone(expectation['payload']['prediction_distribution'])
        self.assertEqual(observation['payload']['original_result_ref'],out['result'])
        self.assertEqual(observation['payload']['expectation_ref'],p['action_id'])
        self.assertIsNone(self.records('assessment')[0]['payload']['gain'])
        projection=self.sf.shadow_interest(self.actor);cell=projection['cells'][0]
        self.assertEqual((cell['sample_count'],cell['unknown_count'],cell['shadow_q']),(0,1,0))
        self.assertFalse(projection['affects_selection'])
        self.assertEqual(len(self.h.s.rows('thought_requests')),3)
    def test_no_predictions_fabricated_on_recovery(self):
        self.enable();a=self.h.investigation();p=self.h.propose(a)
        from digital_life.application.runtime.execution import Executor
        Executor(self.h.s,self.h.engine.identity).dispatch(p['action_id'],self.h.backend)
        self.h.execute(p)
        e=self.sf._events('expectation')[0]['payload'];self.assertFalse(e['prepared_before_dispatch']);self.assertIsNone(e['prediction_distribution'])
    def test_repeat_acceptance_and_result_replay_do_not_duplicate_records(self):
        self.enable();a,p,out=self.finish();before={k:len(self.records(k)) for k in ('intent','expectation','observation','assessment')}
        self.h.execute(p)
        with self.h.s.tx():self.sf.observe(a,out)
        self.assertEqual(before,{k:len(self.records(k)) for k in before})
    def test_failed_tool_records_unknown_not_negative(self):
        self.enable();a=self.h.investigation();p=self.h.propose(a)
        from digital_life.domain.contracts import ToolResult
        self.h.tool_outcome=ToolResult('received','failed','fail');self.h.execute(p)
        r=self.records('assessment')[0]['payload'];self.assertEqual(r['gain_status'],'unknown');self.assertIsNone(r['gain'])
    def test_source_withdrawal_excludes_shadow_evidence(self):
        self.enable();self.finish()
        Memory(self.h.s).restrict(self.h.memory['memory_id'],[self.actor],self.actor)
        p=self.sf.shadow_interest(self.actor)['cells'][0]
        self.assertEqual((p['excluded_count'],p['unknown_count']),(1,0))
    def test_explicit_invalidation_is_idempotent(self):
        self.enable();self.finish();ref=self.sf._events('opportunity')[0]['payload']['opportunity_ref']
        self.sf.invalidate(ref,'test independent label withdrawn',self.actor);self.sf.invalidate(ref,'test independent label withdrawn',self.actor)
        from digital_life.application.cognition.cognition_experience import CognitiveExperience
        self.assertEqual(sum(e['payload']['kind']=='invalidation' for e in CognitiveExperience(self.h.s).events()),1)
        self.assertEqual(self.sf.shadow_interest(self.actor)['cells'][0]['excluded_count'],1)
    def test_restart_rebuilds_identical_shadow(self):
        self.enable();self.finish();before=self.sf.shadow_interest(self.actor)
        from digital_life.infrastructure.persistence.sqlite_store import Store
        store=Store(self.h.root)
        try:self.assertEqual(SelfFeedback(store).shadow_interest(self.actor),before)
        finally:store.close()
    def test_stop_blocks_new_expectation_and_no_interest_commit_exists(self):
        self.enable();a=self.h.investigation();p=self.h.propose(a);self.h.stop('user_stop')
        with self.assertRaises(Forbidden):self.h.execute(p)
        self.assertEqual(self.sf._events('expectation'),[])
        self.assertEqual(self.sf._events('interest_committed'),[])
    def test_shadow_does_not_enter_model_inputs_or_change_ordering(self):
        self.enable();a=self.h.investigation();self.h.finish(a)
        for payload in self.h.model.inputs:
            self.assertNotIn('self_feedback',payload);self.assertNotIn('shadow_interest',payload)
        # A very high supplied diagnostic still has the legacy effect; shadow Q is not consulted.
        q=next(iter(self.h.x.questions().values()))
        with self.h.s.tx():
            for name,gain in (('lower',.1),('higher',.9)):
                self.h.x.record(dict(q,id=name,question=name,state='candidate',visits=0,activity=None,expected_gain=gain,cost=.1))
        with patch('digital_life.application.autonomy.exploration.utc',side_effect=lambda seconds=0:utc(7200+seconds)):b=self.h.x.tick(self.h.engine)
        self.assertEqual(self.h.x.binding(b)['question_id'],'higher')
    def test_reused_receipt_is_one_learning_exposure(self):
        self.enable();a,p,out=self.finish();q=next(iter(self.h.x.questions().values()))
        with self.h.s.tx():self.h.x.record(dict(q,id='other',question='Other claim about same file',state='candidate',visits=0,activity=None))
        with patch('digital_life.application.autonomy.exploration.utc',side_effect=lambda seconds=0:utc(7200+seconds)):b=self.h.x.tick(self.h.engine)
        self.h.model.always_continue=True;self.h.propose(b)
        self.assertEqual(len(self.sf._events('observation')),2)
        self.assertEqual(len(self.sf._events('opportunity')),1)
        self.assertEqual(len(self.records('assessment')),1)
        self.assertEqual(self.sf._events('observation')[-1]['payload']['original_result_ref'],out['result'])
    def test_post_receipt_rollback_recovers_without_second_tool_dispatch(self):
        self.enable();a=self.h.investigation();p=self.h.propose(a)
        original=SelfFeedback.observe
        def failed(service,*args):
            original(service,*args);raise RuntimeError('injected journal transaction failure')
        with patch.object(SelfFeedback,'observe',failed):
            with self.assertRaises(RuntimeError):self.h.execute(p)
        self.assertEqual(self.sf._events('observation'),[])
        self.h.execute(p)
        self.assertEqual(len(self.h.s.rows('action_attempts')),1)
        self.assertEqual(len(self.sf._events('observation')),1)
    def test_enabling_requires_stopped_runtime(self):
        self.h.enable()
        from digital_life.domain.contracts import Conflict
        with self.assertRaises(Conflict):self.enable()
    def test_cli_inspection_never_unlocks_or_calls_model(self):
        import io
        from contextlib import redirect_stdout
        from digital_life.entrypoints.cli import main
        for operation in ('status','enable','projection','disable'):
            with patch('sys.argv',['life','--data',str(self.h.root),'self-feedback',operation]),redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(main(),0)
            self.assertFalse(json.loads(stream.getvalue()).get('inference_started',False))
            self.assertTrue((self.h.root/'WAKE_DISABLED').exists())
        self.assertEqual(len(self.h.s.rows('thought_requests')),0)
    def test_intent_keeps_original_request_profile_not_acceptance_profile(self):
        self.enable()
        from digital_life.application.services.personality import Personality
        original=Personality(self.h.s).current()['profile']['id']
        def change_profile():
            with self.h.s.tx():
                refs=[self.h.s.evidence(artifact=self.h.s.artifact({'fixture':i})) for i in (1,2)]
                Personality(self.h.s).replace({},refs,self.actor)
        self.h.model.on_dispatch=change_profile;self.h.discovery()
        self.assertNotEqual(Personality(self.h.s).current()['profile']['id'],original)
        snapshot=self.sf._events('snapshot')[0]['payload']
        self.assertEqual(snapshot['personality_revision'],original)
        self.assertEqual(snapshot['context_timing'],'captured-with-original-request')
    def test_no_live_root_goal_is_created_by_sidecar(self):
        self.enable();a=self.h.discovery()
        self.assertEqual(len(self.h.s.rows('goal_items')),1)
        self.assertIsNone(self.sf._events('intent')[0]['payload']['root_goal_ref'])

class ShadowFoldTests(unittest.TestCase):
    def record(self,gain=None,revision=1,exposure='one'):
        return {'cell':['fixture','read','fixed','fixture-v1'],'exposure_key':exposure,'opportunity_ref':exposure,'revision':revision,
                'gain':gain,'gain_status':'unknown' if gain is None else 'positive' if gain>0 else 'negative' if gain<0 else 'measured_zero',
                'qualified':True,'source_readable':True}
    def cell(self,rows,invalid=()):return InterestModel.fold(rows,invalid)['cells'][0]
    def test_positive_negative_zero_unknown_are_distinct(self):
        self.assertAlmostEqual(self.cell([self.record(.9)])['shadow_q'],.3)
        self.assertAlmostEqual(self.cell([self.record(-.9)])['shadow_q'],-.3)
        self.assertEqual(self.cell([self.record(0)])['sample_count'],1)
        self.assertEqual(self.cell([self.record()])['sample_count'],0)
        self.assertEqual(self.cell([self.record()])['unknown_count'],1)
    def test_duplicate_fixture_counts_once(self):
        r=self.record(.9);self.assertEqual(self.cell([r,r])['sample_count'],1)
    def test_revision_replaces_old_gain_and_replays_in_any_order(self):
        a=self.record(.9);b=self.record(-.9,revision=2)
        self.assertAlmostEqual(self.cell([a,b])['shadow_q'],-.3)
        self.assertEqual(self.cell([a,b]),self.cell([b,a]))
    def test_same_revision_different_payload_rejected(self):
        with self.assertRaises(ContractError):self.cell([self.record(.9),self.record(-.9)])
    def test_invalidation_and_permission_withdrawal_rebuild(self):
        a=self.record(.9);b=self.record(-.6,exposure='two');result=self.cell([a,b],['one'])
        self.assertAlmostEqual(result['shadow_q'],-.2)
        a['source_readable']=False;self.assertEqual(self.cell([a,b])['shadow_q'],result['shadow_q'])
    def test_invalid_gain_and_unqualified_measurement(self):
        for gain in (True,float('nan'),float('inf'),2):
            with self.assertRaises(ContractError):self.cell([self.record(gain)])
        a=self.record(.9);a['qualified']=False;self.assertEqual(self.cell([a])['sample_count'],0)
    def test_unknown_revision_removes_previous_contribution(self):
        self.assertEqual(self.cell([self.record(.9),self.record(revision=2)])['sample_count'],0)

if __name__=='__main__':unittest.main()
