"""Heldout measurement protocol, budget/stop boundaries and cognition ownership."""
import json
from pathlib import Path
import tempfile
import unittest
from digital_life.domain.contracts import ContractError,Conflict,Forbidden
from digital_life.application.learning.self_feedback import SelfFeedback
from digital_life.application.learning.experience_measurement import ExperienceMeasurement
from digital_life.application.services.cognition import Cognition
from digital_life.application.services.learning import Learning
from digital_life.application.cognition.cognition_experience import CognitiveExperience
from evaluation.exploration.harness import Harness

ROOT=Path(__file__).resolve().parents[1]
class FixturePredictor:
    name='deterministic-prediction-fixture-v1'
    def __init__(self,target=(.2,.8),retention=(.8,.8),unknown=False):
        self.target=target;self.retention=retention;self.unknown=unknown;self.requests=[];self.callback=None
    def predict(self,request):
        self.requests.append(request)
        if self.callback:self.callback()
        has_experience='cognitive_experience' in request['context'];pair=self.target if request['case_id']=='target' else self.retention
        p=pair[int(has_experience)]
        return {'probabilities':None if self.unknown and request['case_id']=='target' else [1-p,p],'actual_tokens':0}

class ExperienceMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();cases=json.loads((ROOT/'evaluation/exploration/materials/cases-v1.json').read_text())['cases']
        self.h=Harness(Path(self.tmp.name)/'instance',next(c for c in cases if c['case_id']=='B01'));self.actor=self.h.s.config()['controller']
        self.sf=SelfFeedback(self.h.s);self.sf.configure(self.actor,True);self.m=ExperienceMeasurement(self.h.s);self.m.configure(True,self.actor)
        a=self.h.investigation();self.h.finish(a);self.activity=a;self.op=self.sf._events('opportunity')[0]['payload']['opportunity_ref']
        self.cases=[{'case_id':'target','input':'heldout new task','split':'target'},{'case_id':'retention','input':'heldout old task','split':'retention'}]
        self.labels={'target':1,'retention':1};self.nonce='private-test-oracle-nonce-not-passed-to-predictor'
    def tearDown(self):self.h.close();self.tmp.cleanup()
    def register(self,**kwargs):return self.m.register(self.op,self.cases,2,self.m.commitment(self.labels,self.nonce),self.actor,**kwargs)
    def measure(self,predictor=None):
        run=self.register();port=predictor or FixturePredictor();self.m.run_predictions(run,port,self.actor)
        self.m.reveal_labels(run,self.labels,self.nonce,self.actor);ref=self.m.evaluate(run,self.actor)
        return run,ref,self.m.checked_report(ref),port
    def test_positive_measurement_computed_from_sealed_predictions(self):
        run,ref,report,port=self.measure()
        self.assertAlmostEqual(report['gain'],.6);self.assertEqual(report['status'],'measured');self.assertEqual(report['model_port_calls'],4)
        self.assertEqual(report['actual_tokens'],0);self.assertIsNone(report['independent_cases'])
        labels=self.m._get('labels',run);labels_seq=self.h.s.row('runtime_events',labels['id'])['event_seq']
        self.assertTrue(all(self.h.s.row('runtime_events',p)['event_seq']<labels_seq for p in report['prediction_refs']))
    def test_negative_zero_and_unknown_are_distinct(self):
        for port,status in ((FixturePredictor(target=(.8,.2)),'negative'),(FixturePredictor(target=(.5,.5)),'measured_zero')):
            # Both runs share the parent's remaining budget; exactly eight port calls total.
            _,_,r,_=self.measure(port);self.assertEqual(r['gain_status'],status)
    def test_unknown_prediction_is_null_not_zero(self):
        _,ref,r,_=self.measure(FixturePredictor(unknown=True));self.assertIsNone(r['gain']);self.assertEqual(r['status'],'unknown')
        self.m.adopt_shadow(ref,self.actor)
        rows=Learning(self.h.s).experience_assessments();self.assertIsNone(rows[-1]['payload']['gain'])
    def test_retention_regression_vetoes_positive_target_improvement(self):
        _,_,r,_=self.measure(FixturePredictor(retention=(.8,.2)))
        self.assertGreater(r['target_gain'],0);self.assertGreater(r['retention_regression'],0);self.assertLess(r['gain'],0)
    def test_label_reveal_requires_both_arms(self):
        run=self.register()
        with self.assertRaises(Conflict):self.m.reveal_labels(run,self.labels,self.nonce,self.actor)
    def test_commitment_rejects_changed_answers(self):
        run=self.register();self.m.run_predictions(run,FixturePredictor(),self.actor)
        with self.assertRaises(Forbidden):self.m.reveal_labels(run,{'target':0,'retention':1},self.nonce,self.actor)
    def test_actor_never_gets_oracle_or_nonce(self):
        _,_,_,port=self.measure()
        for request in port.requests:
            self.assertNotIn('labels',request);self.assertNotIn(self.nonce,json.dumps(request));self.assertNotIn('oracle',request['context'])
    def test_known_oracle_keys_in_common_context_rejected(self):
        with self.assertRaises(Forbidden):self.register(common_context={'labels':self.labels})
        with self.assertRaises(Forbidden):self.register(common_context={'cognitive_experience':{}})
    def test_training_overlap_and_missing_retention_rejected(self):
        with self.assertRaises(ContractError):self.register(training_case_ids=['target'])
        old=self.cases;self.cases=[dict(c,split='target') for c in old]
        with self.assertRaises(ContractError):self.register()
    def test_invalid_prediction_distribution_never_becomes_score(self):
        run=self.register();port=FixturePredictor();port.predict=lambda request:{'probabilities':[.8,.8],'actual_tokens':0}
        with self.assertRaises(ContractError):self.m.run_predictions(run,port,self.actor)
        with self.assertRaises(Conflict):self.m.evaluate(run,self.actor)
    def test_parent_budget_is_shared_and_not_reset_per_measurement(self):
        self.measure();self.measure();run=self.register();port=FixturePredictor()
        with self.assertRaises(ContractError):self.m.run_predictions(run,port,self.actor)
        self.assertEqual(len(port.requests),0)
        self.assertEqual(len(self.h.s.rows('budget_reservations')),12)
    def test_completed_predictions_are_not_called_again(self):
        run=self.register();port=FixturePredictor();self.m.run_predictions(run,port,self.actor);self.m.run_predictions(run,port,self.actor)
        self.assertEqual(len(port.requests),4)
    def test_no_predictions_after_labels_are_revealed(self):
        run,_,_,_=self.measure()
        with self.assertRaises(Forbidden):self.m.run_predictions(run,FixturePredictor(),self.actor)
    def test_failed_call_is_not_automatically_replayed(self):
        run=self.register();port=FixturePredictor()
        def fail(request):port.requests.append(request);raise RuntimeError('injected model failure')
        port.predict=fail
        with self.assertRaises(RuntimeError):self.m.run_predictions(run,port,self.actor)
        result=self.m.run_predictions(run,port,self.actor);self.assertEqual(result['reason'],'unreconciled-prior-dispatch');self.assertEqual(len(port.requests),1)
    def test_usage_unknown_halts_next_dispatch(self):
        run=self.register();port=FixturePredictor();base=port.predict
        def unknown(request):r=base(request);r.pop('actual_tokens');return r
        port.predict=unknown;result=self.m.run_predictions(run,port,self.actor)
        self.assertEqual(result['reason'],'unknown-usage');self.assertEqual(len(port.requests),1)
    def test_stop_in_callback_prevents_next_dispatch_and_adoption(self):
        run=self.register();port=FixturePredictor();port.callback=lambda:self.h.c.stop('measurement-stop')
        with self.assertRaises(Forbidden):self.m.run_predictions(run,port,self.actor)
        self.assertEqual(len(port.requests),1)
    def test_disable_and_new_configuration_reject_old_run(self):
        run=self.register();self.m.configure(False,self.actor)
        with self.assertRaises(Forbidden):self.m.run_predictions(run,FixturePredictor(),self.actor)
    def test_measurements_require_controller(self):
        with self.assertRaises(Forbidden):self.m.register(self.op,self.cases,2,'0'*64,'other')
        run=self.register()
        with self.assertRaises(Forbidden):self.m.run_predictions(run,FixturePredictor(),'other')
    def test_source_withdrawal_blocks_calls(self):
        run=self.register()
        from digital_life.application.services.memory import Memory
        Memory(self.h.s).restrict(self.h.memory['memory_id'],[self.actor],self.actor)
        with self.assertRaises(Forbidden):self.m.run_predictions(run,FixturePredictor(),self.actor)
    def test_learning_proposes_cognition_saves_measured_shadow_version(self):
        _,ref,_,_=self.measure();before=len(CognitiveExperience(self.h.s).events())
        assessment=Learning(self.h.s).assess_measured_experience(self.op,ref)
        self.assertEqual(len(CognitiveExperience(self.h.s).events()),before)
        saved=self.m.adopt_shadow(ref,self.actor);self.assertEqual(len(CognitiveExperience(self.h.s).events()),before+1)
        value=self.h.s.read_artifact(self.h.s.row('runtime_events',saved)['payload_artifact_id']);self.assertEqual(value['owner'],'cognition.experience')
        snapshot=Cognition(self.h.s).experience_snapshot(self.actor);cell=next(c for c in snapshot['cells'] if c['cell'][-1]=='prediction_brier_v1')
        self.assertAlmostEqual(cell['experience_estimate'],.2);self.assertEqual(cell['sample_count'],1);self.assertFalse(snapshot['affects_selection'])
        self.assertEqual(self.m.adopt_shadow(ref,self.actor),saved)
    def test_report_invalidation_removes_contribution_without_rewriting_history(self):
        run,ref,_,_=self.measure();self.m.adopt_shadow(ref,self.actor);before=CognitiveExperience(self.h.s).events()
        self.m.invalidate(run,'label source withdrawn',self.actor)
        snapshot=Cognition(self.h.s).experience_snapshot(self.actor);cell=next(c for c in snapshot['cells'] if c['cell'][-1]=='prediction_brier_v1')
        self.assertEqual(cell['sample_count'],0);self.assertEqual(before,CognitiveExperience(self.h.s).events())
    def test_forged_assessment_cannot_change_measured_gain(self):
        _,ref,_,_=self.measure();learning=Learning(self.h.s);a_ref=learning.assess_measured_experience(self.op,ref)
        a=self.h.s.read_artifact(self.h.s.row('runtime_events',a_ref)['payload_artifact_id']);a['gain']=1.
        with self.h.s.tx():bad=self.h.s.event('learning.experience_assessed',payload=a,source='learning-experience',key='forged-measured-fixture')
        p=learning.propose_experience(bad,0)
        with self.assertRaises(Forbidden):Cognition(self.h.s).save_experience(p,0)
    def test_codex_overhead_reservation_requires_sufficient_parent_budget(self):
        run=self.register(tokens_per_call=32768)
        self.assertEqual(self.m._registered(run)['tokens_per_call'],32768)
        port=FixturePredictor()
        with self.assertRaises(ContractError):self.m.run_predictions(run,port,self.actor)
        self.assertEqual(port.requests,[])
        for invalid in (32769,0,True):
            with self.assertRaises(ContractError):self.register(tokens_per_call=invalid)

    def test_multiclass_brier_is_normalized(self):
        self.assertEqual(self.m.brier([0,0,1],0),1.);self.assertEqual(self.m.brier([1,0,0],0),0.)
    def test_collector_disable_blocks_measurement(self):
        run=self.register();self.sf.configure(self.actor,False)
        with self.assertRaises(Forbidden):self.m.run_predictions(run,FixturePredictor(),self.actor)
    def test_model_identity_change_is_not_silently_accepted(self):
        run=self.register();port=FixturePredictor();port.callback=lambda:setattr(port,'name','another-model')
        with self.assertRaises(Conflict):self.m.run_predictions(run,port,self.actor)
        self.assertEqual(len(port.requests),1)
    def test_cli_status_disable_does_not_unlock_or_infer(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from digital_life.entrypoints.cli import main
        self.h.c.stop('administrative-inspection');(self.h.root/'WAKE_DISABLED').write_text('test remains locked')
        for op in ('status','disable','enable'):
            with patch('sys.argv',['life','--data',str(self.h.root),'experience-measurement',op]),redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(main(),0)
            self.assertFalse(json.loads(stream.getvalue())['inference_started']);self.assertTrue((self.h.root/'WAKE_DISABLED').exists())
    def test_parent_exploration_disable_rejects_registered_run(self):
        run=self.register();self.h.x.configure(self.actor,False)
        with self.assertRaises(Forbidden):self.m.run_predictions(run,FixturePredictor(),self.actor)
    def test_parent_cancel_flag_rejects_new_measurement_calls(self):
        run=self.register()
        with self.h.s.tx():self.h.s.db.execute("UPDATE activities SET cancel_requested_at=? WHERE id=?",('fixture-cancel',self.activity))
        with self.assertRaises(Forbidden):self.m.run_predictions(run,FixturePredictor(),self.actor)
    def test_token_overage_does_not_start_next_call(self):
        run=self.register();port=FixturePredictor();original=port.predict
        def over(request):response=original(request);response['actual_tokens']=513;return response
        port.predict=over;result=self.m.run_predictions(run,port,self.actor)
        self.assertEqual(result['reason'],'observed-token-overage');self.assertEqual(len(port.requests),1)
    def test_competing_stop_can_commit_between_prediction_callbacks(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
        run=self.register();port=FixturePredictor()
        port.callback=lambda:self.h.stop('dispatch_competition',defer=True)
        @contextmanager
        def release_then_observe_stop(root):
            with dispatch_gate(root):yield
            self.h.await_stops()
        with patch('digital_life.application.learning.experience_measurement.dispatch_gate',release_then_observe_stop):
            with self.assertRaises(Forbidden):self.m.run_predictions(run,port,self.actor)
        self.assertEqual(len(port.requests),1)
    def test_configured_reasoner_adapter_uses_fresh_wait_wrapper_and_records_usage(self):
        from digital_life.infrastructure.llm.experience_prediction import ExperiencePredictionPort
        class Reasoner:
            name='mock-probability-model';timeout=30;max_output_tokens=2048;last_usage=None
            def __init__(self):self.requests=[]
            def generate(self,request):
                self.requests.append(request);self.last_usage={'input_tokens':10,'output_tokens':5}
                return {'schema_version':1,'action':{'tool':'wait','arguments':{'reason':'measurement-only'}},'explanation':'{"probabilities":[0.2,0.8]}'}
        reasoner=Reasoner();run=self.register();self.m.run_predictions(run,ExperiencePredictionPort(reasoner),self.actor)
        self.m.reveal_labels(run,self.labels,self.nonce,self.actor);report=self.m.checked_report(self.m.evaluate(run,self.actor))
        self.assertEqual(report['actual_tokens'],60);self.assertEqual(report['gain_status'],'measured_zero')
        self.assertEqual((reasoner.timeout,reasoner.max_output_tokens),(30,2048))
        for request in reasoner.requests:
            self.assertEqual(request['context_mode'],'fresh_request');self.assertNotIn('history',request);self.assertNotIn('messages',request);self.assertNotIn('remaining_seconds',request['measurement_input'])
    def test_prediction_adapter_rejects_tool_action(self):
        from digital_life.infrastructure.llm.experience_prediction import ExperiencePredictionPort
        class Reasoner:
            name='mock-unsafe-output'
            def generate(self,request):return {'schema_version':1,'action':{'tool':'read_file','arguments':{'path':'notes/private'}},'explanation':'{"probabilities":[0.2,0.8]}'}
        run=self.register()
        with self.assertRaises(ContractError):self.m.run_predictions(run,ExperiencePredictionPort(Reasoner()),self.actor)
    def test_prediction_adapter_rejects_invalid_probability_wrapper(self):
        from digital_life.infrastructure.llm.experience_prediction import ExperiencePredictionPort
        class Reasoner:
            name='mock-bad-probability-wrapper'
            def generate(self,request):return {'schema_version':1,'action':{'tool':'wait','arguments':{'reason':'measurement'}},'explanation':'not JSON'}
        run=self.register()
        with self.assertRaises(ContractError):self.m.run_predictions(run,ExperiencePredictionPort(Reasoner()),self.actor)
    def test_no_promotion_to_facts_or_live_choice(self):
        before=len(self.h.s.rows('cognition_beliefs'));_,ref,_,_=self.measure();self.m.adopt_shadow(ref,self.actor)
        self.assertEqual(len(self.h.s.rows('cognition_beliefs')),before)
        for payload in self.h.model.inputs:self.assertNotIn('experience_snapshot',payload)
        self.assertEqual(len(self.h.s.rows('thought_requests')),3)

if __name__=='__main__':unittest.main()
