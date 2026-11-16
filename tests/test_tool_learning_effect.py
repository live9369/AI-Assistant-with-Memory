"""IM14 real isolated sealed-report and strict-budget paths; no real model."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc,dumps
from digital_life.application.learning.eligibility import slot,ref
from digital_life.application.learning.effects import LocalEffects,METRIC,metric_contract,assessment_from_report,ToolLearningEffects,classification_scope
from digital_life.application.learning.effect_measurement import FreshMeasurementProvider,StrictMeasurementExecution
from digital_life.application.learning.experience_measurement import ExperienceMeasurement
from digital_life.application.learning.self_feedback import SelfFeedback
from digital_life.application.autonomy.exploration import Exploration
from digital_life.application.learning.runtime_learning import StrictLearningCoordinator
from digital_life.application.learning.engine import StrictEngine
from digital_life.application.learning.execution import StrictActionExecutor
from tests import test_tool_learning_runtime as rt

class FixedCapability(rt.SyntheticCapability):
    def input_tokens(self,provider,wire):return 100

class EffectTests(unittest.TestCase):
    def setUp(self):
        self.f=rt.StrictActualUseTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.control=self.f.control;self.actor=self.s.config()['controller']
        old=self.f.f.identity;deployment=self.control.db.execute('SELECT deployment_id FROM process_runs WHERE id=?',(old.process_id,)).fetchone()[0]
        self.control.stop('synthetic effect opt-in');self.control.finish_run(old)
        SelfFeedback(self.s).configure(self.actor,True);self.m=ExperienceMeasurement(self.s);self.m.configure(True,self.actor)
        self.x=Exploration(self.s);self.x.configure(self.actor,True)
        self.control.resume('synthetic effect resume');identity=self.control.begin_run(deployment);self.addCleanup(self.control.finish_run,identity)
        self.f.f.identity=identity;self.f.k=StrictEngine(self.s,identity,self.f.k.provider);self.k=self.f.k
        _,_,intent,_=self.f.producer();self.activity=self.f.activity
        self.outcome=StrictActionExecutor(self.s,identity,self.k).dispatch(intent)
        memory=self.s.rows('memory_items')[0]['current_revision_id'];q={'id':identifier(),'resource_revision':0,'question':'synthetic classification opportunity','verification':'controlled paired holdout','evidence_refs':[memory],'expected_gain':0.1,'cost':0.1,'state':'investigating'}
        self.x.record(q);self.s.event('exploration.bound',payload={'activity':self.activity,'question_id':q['id'],'generation':self.x.config()['generation'],'max_rounds':3},activity=self.activity)
        self.sf=SelfFeedback(self.s);self.sf.bind(self.activity,q);self.sf.observe(self.activity,self.outcome);self.op=self.sf._events('opportunity')[0]['payload']['opportunity_ref']
        self.r=StrictLearningCoordinator(self.k);self.work=self.r.admit(self.activity,self.outcome['result'],{'kind':'json_pointer','pointer':'/execution'})
        self.sdk=LocalEffects(self.k.owners);self.entry,self.principal=self.k.owners.entry('M14','evaluate',self.actor)
        metric=self.s.insert('metric_definitions',**METRIC);self.metric=ref(self.s,metric)
        self.cases=[{'case_id':'target','input':'target task','split':'target'},{'case_id':'retention','input':'retention task','split':'retention'}];self.labels={'target':1,'retention':1};self.nonce='private-synthetic-nonce-for-label-sealing'
        self.scope=classification_scope(self.s,self.cases,2,self.m.commitment(self.labels,self.nonce))
        self.assessment={'measurement_state':'not_measured','measurement_ref':self.unknown(),'baseline_ref':slot(),'candidate_ref':slot(),'method_refs':[],'metric_definition':self.metric,'case_scope':self.scope,'gain':self.unknown(),'retention_components':self.unknown(),'sample_counts':self.unknown(),'independence':self.unknown(),'usage':self.unknown()}
        self.request=self.envelope(self.entry,self.assessment)
        self.cases=[{'case_id':'target','input':'target task','split':'target'},{'case_id':'retention','input':'retention task','split':'retention'}];self.labels={'target':1,'retention':1};self.nonce='private-synthetic-nonce-for-label-sealing'
        self.calls=0;self.mode='positive'
    def unknown(self):return {'status':'not_collected','value':None,'reason_code':'not_measured','reason':'no measurement','basis_refs':[]}
    def envelope(self,entry,assessment):
        work=self.s.row('tl_work',self.work['id']);return self.r._envelope(entry,work['learning_activity_id'],{'work':self.work,'measurement':deepcopy(assessment['measurement_ref']),'assessment':deepcopy(assessment)},self.work['id'],self.r.budget.check_work(self.work['id'])['budget'])
    def execution(self):
        _,route,reasoner=self.k._route()
        mode=self.mode
        def transport(path,wire,*args):
            packet=json.loads(wire['messages'][1]['content']);request=packet['input'];with_exp='cognitive_experience' in request['context'];p=.8
            if request['case_id']=='target':p=(.8 if with_exp else .2) if mode in ('positive','retention-regression') else (.2 if with_exp else .8) if mode=='negative' else .5
            if mode=='retention-regression' and request['case_id']=='retention':p=.2 if with_exp else .8
            probabilities=None if mode=='incomplete' and request['case_id']=='target' else [1-p,p]
            output={'schema_version':1,'action':{'tool':'wait','arguments':{'reason':'prediction only'}},'explanation':json.dumps({'probabilities':probabilities})}
            return {'model':'synthetic-fixed','choices':[{'finish_reason':'stop','message':{'content':json.dumps(output)}}],'usage':{'prompt_tokens':100,'completion_tokens':20}}
        provider=FreshMeasurementProvider(reasoner,route,FixedCapability(),transport)
        return StrictMeasurementExecution(self.k,provider)
    def measure(self):
        self.run=self.sdk.register(self.entry,self.request,self.op,self.cases,2,self.m.commitment(self.labels,self.nonce),tokens_per_call=512,wall_seconds=120)
        self.execution_owner=self.execution();self.m.run_predictions(self.run,None,self.actor,strict_execution=self.execution_owner,entry=self.entry)
        self.m.reveal_labels(self.run,self.labels,self.nonce,self.actor);self.report=self.m.evaluate(self.run,self.actor)
        a=assessment_from_report(self.s,ref(self.s,self.report),self.metric,self.scope);self.request=self.envelope(self.entry,a)
        return self.sdk.record_effect(self.entry,self.request)
    def test_real_strict_sealed_record_and_independent_shadow_adoption(self):
        result=self.measure();row=self.s.row('tl_effect',result['result_refs'][0]['id']);a=self.s.read_artifact(row['payload_artifact_id'])
        self.assertAlmostEqual(a['gain']['value'],.6);self.assertEqual(row['metric_contract'],metric_contract(self.s,self.metric))
        self.assertIsNone(a['independence']['value']['independent_cases']);self.assertEqual(a['usage']['value']['model_port_calls'],4)
        parent=self.s.row('activities',self.activity);doc=json.loads(parent['budget_json']);pred=[r for r in doc['ledger']['reservations'].values() if r['kind']=='thought_attempt']
        self.assertEqual(len(pred),4);self.assertTrue(all(r['actual']['input_tokens']==100 and r['actual']['output_tokens']==20 for r in pred))
        self.assertEqual(len(self.s.rows('tl_content_revision')),0);self.assertEqual(len(self.s.rows('tl_representation')),0)
        entry,_=self.k.owners.entry('M03','evaluate',self.actor);request=self.envelope(entry,a)
        version=self.sdk.adopt_shadow(entry,request,result['result_refs'][0],self.actor)
        payload=self.s.read_artifact(self.s.row('runtime_events',version)['payload_artifact_id']);self.assertFalse(payload['affects_selection']);self.assertEqual(payload['acceptance_state'],'shadow-not-world-fact')
    def test_unmeasured_record_never_has_zero_or_content_authority(self):
        result=self.sdk.record_effect(self.entry,self.request);self.assertEqual(self.s.row('tl_effect',result['result_refs'][0]['id'])['state'],'not_measured')
        self.assertEqual(len(self.s.rows('tl_content')),0);self.assertEqual(len(self.s.rows('thought_results')),1)
    def test_zero_is_measured(self):
        self.mode='zero';result=self.measure();a=self.s.read_artifact(self.s.row('tl_effect',result['result_refs'][0]['id'])['payload_artifact_id']);self.assertEqual(a['measurement_state'],'measured');self.assertEqual(a['gain']['value'],0)
    def test_negative_is_measured(self):
        self.mode='negative';result=self.measure();a=self.s.read_artifact(self.s.row('tl_effect',result['result_refs'][0]['id'])['payload_artifact_id']);self.assertLess(a['gain']['value'],0)
    def test_incomplete_is_unknown(self):
        self.mode='incomplete';result=self.measure();a=self.s.read_artifact(self.s.row('tl_effect',result['result_refs'][0]['id'])['payload_artifact_id']);self.assertEqual(a['measurement_state'],'incomplete');self.assertIsNone(a['gain']['value'])
    def test_metric_string_is_resolved_from_actual_definition(self):
        self.s.db.execute("UPDATE metric_definitions SET unit='retrieval-hit-rate' WHERE id=?",(self.metric['id'],))
        with self.assertRaises(Forbidden):self.sdk.record_effect(self.entry,self.request)
    def test_default_authority_and_forged_entry_deny(self):
        with self.assertRaises(Forbidden):ToolLearningEffects(self.s).record_effect(self.entry,self.request)
        with self.assertRaises(Forbidden):self.sdk.record_effect('M14',self.request)
    def test_retry_has_no_new_effect_or_prediction(self):
        first=self.measure();again=self.sdk.record_effect(self.entry,self.request);self.assertEqual(first,again)
        request=deepcopy(self.request);request.update(command_id=identifier(),idempotency_key=identifier());second=self.sdk.record_effect(self.entry,request)
        self.assertEqual(second['disposition'],'reused');self.assertEqual(first['result_refs'],second['result_refs']);self.assertEqual(len(self.s.rows('tl_effect')),1)
    def test_stop_blocks_record(self):
        self.control.stop('synthetic stop')
        with self.assertRaises(Forbidden):self.sdk.record_effect(self.entry,self.request)
    def test_original_caps_cannot_be_enlarged(self):
        self.request['budget']['max_bytes']+=1
        with self.assertRaises(Conflict):self.sdk.record_effect(self.entry,self.request)
    def invalidate_source(self):
        from tests import test_tool_learning_invalidation as six
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        request=deepcopy(self.request);request.update(command_id=identifier(),idempotency_key=identifier())
        source=self.s.read_artifact(self.s.row('tl_work',self.work['id'])['conditions_artifact_id'])['source'];request['principal'].update(module='M12',purpose='propagate')
        request['payload']={'change_id':identifier(),'kind':'revoke','source':{'object':source['source'],'revision':0,'epoch':0},'replacement':slot(),'affected_scope':self.scope,'subjects':[],'purposes':[],'expected_epoch':0,'evidence':[source],'erase_scope':slot()}
        return ToolLearningInvalidation(self.s,six.MechanicalInvalidation()).apply('mechanical-im06',request)
    def test_actual_F1_excludes_previously_adopted_shadow_sample(self):
        result=self.measure();entry,_=self.k.owners.entry('M03','evaluate',self.actor);request=self.envelope(entry,self.request['payload']['assessment'])
        self.sdk.adopt_shadow(entry,request,result['result_refs'][0],self.actor)
        from digital_life.application.cognition.cognition_experience import CognitiveExperience
        before=CognitiveExperience(self.s).snapshot(self.actor);self.assertEqual(sum(c['sample_count'] for c in before['cells']),1)
        self.invalidate_source();after=CognitiveExperience(self.s).snapshot(self.actor)
        self.assertEqual(sum(c['sample_count'] for c in after['cells']),0);self.assertGreater(sum(c['excluded_count'] for c in after['cells']),0);self.assertFalse(after['affects_selection'])
        with self.assertRaises((Forbidden,Conflict)):self.sdk.adopt_shadow(entry,request,result['result_refs'][0],self.actor)
        with self.assertRaises((Forbidden,Conflict)):self.sdk.record_effect(self.entry,self.request)
    def test_actual_report_invalidation_is_unknown_not_zero(self):
        self.measure();self.m.invalidate(self.run,'synthetic invalidated labels',self.actor)
        assessment=assessment_from_report(self.s,ref(self.s,self.report),self.metric,self.scope,invalidated=True);request=self.envelope(self.entry,assessment)
        result=self.sdk.record_effect(self.entry,request);row=self.s.row('tl_effect',result['result_refs'][0]['id']);self.assertEqual(row['state'],'invalidated');self.assertIsNone(assessment['gain']['value'])
        self.assertEqual(len(self.s.rows('tl_effect')),2)
        with self.assertRaises(Forbidden):self.sdk.record_effect(self.entry,self.request)
    def test_effect_components_cannot_be_substituted(self):
        self.measure()
        for key,value in (('gain',slot(.99)),('candidate_ref',slot(self.work)),('baseline_ref',slot(self.work)),('method_refs',[self.work]),('sample_counts',slot({'registered_cases':999})),('usage',slot({'actual_tokens':0}))):
            request=deepcopy(self.request);request.update(command_id=identifier(),idempotency_key=identifier());request['payload']['assessment'][key]=value
            with self.subTest(key=key):
                with self.assertRaises((Forbidden,Conflict,ContractError)):self.sdk.record_effect(self.entry,request)
        self.assertEqual(len(self.s.rows('tl_effect')),1)
    def test_case_scope_cannot_be_relabelled_as_content_quality(self):
        self.measure();request=deepcopy(self.request);request.update(command_id=identifier(),idempotency_key=identifier());request['payload']['assessment']['case_scope']['property']='retrieval accuracy'
        with self.assertRaises(Conflict):self.sdk.record_effect(self.entry,request)
    def test_strict_requires_explicit_execution_owner_and_capability(self):
        run=self.sdk.register(self.entry,self.request,self.op,self.cases,2,self.m.commitment(self.labels,self.nonce))
        with self.assertRaises(Forbidden):self.m.run_predictions(run,None,self.actor)
        owner=StrictMeasurementExecution(self.k)
        with self.assertRaises(Forbidden):self.m.run_predictions(run,None,self.actor,strict_execution=owner,entry=self.entry)
        self.assertIsNone(self.m._get('dispatch',run+'|target|without_experience'))
    def test_completed_work_allows_only_original_account_effect_read(self):
        self.s.db.execute("UPDATE tl_work SET state='processing',phase='assess',row_revision=row_revision+1 WHERE id=?",(self.work['id'],))
        self.s.db.execute("UPDATE tl_work SET state='completed',phase='complete',row_revision=row_revision+1 WHERE id=?",(self.work['id'],))
        result=self.sdk.record_effect(self.entry,self.request);self.assertEqual(self.s.row('tl_effect',result['result_refs'][0]['id'])['state'],'not_measured')
        ledger=json.loads(self.s.row('activities',self.s.row('tl_work',self.work['id'])['learning_activity_id'])['budget_json'])['ledger']
        self.assertTrue(all(r['kind']=='retrieval' for r in ledger['reservations'].values()))
    def test_actual_finished_activity_is_not_reopened_for_effect(self):
        activity=self.s.row('tl_work',self.work['id'])['learning_activity_id'];self.s.db.execute("UPDATE activities SET state='completed' WHERE id=?",(activity,))
        with self.assertRaises(Forbidden):self.sdk.record_effect(self.entry,self.request)
    def test_record_transaction_rolls_back_every_effect_write(self):
        from digital_life.infrastructure.persistence.tool_learning_store import OwnedTransaction
        original=OwnedTransaction.insert
        def fail(tx,table,**values):
            result=original(tx,table,**values)
            if table=='tl_effect':raise OSError('synthetic post effect-write failure')
            return result
        with patch.object(OwnedTransaction,'insert',fail):
            with self.assertRaises(OSError):self.sdk.record_effect(self.entry,self.request)
        self.assertEqual(len(self.s.rows('tl_effect')),0);self.assertEqual(len(self.s.rows('tl_product')),0)
    def test_strict_actual_usage_unknown_halts_without_reissue(self):
        run=self.sdk.register(self.entry,self.request,self.op,self.cases,2,self.m.commitment(self.labels,self.nonce));owner=self.execution();original=owner.provider.transport
        def missing(*args):
            response=original(*args);del response['usage']['completion_tokens'];return response
        owner.provider.transport=missing
        result=self.m.run_predictions(run,None,self.actor,strict_execution=owner,entry=self.entry);self.assertEqual(result['reason'],'unknown-usage')
        doc=json.loads(self.s.row('activities',self.activity)['budget_json']);self.assertTrue(doc['ledger']['halted']);self.assertEqual(len([r for r in doc['ledger']['reservations'].values() if r['kind']=='thought_attempt']),1)
        with self.assertRaises(Forbidden):self.m.run_predictions(run,None,self.actor,strict_execution=owner,entry=self.entry)
    def test_checker_rejects_changed_actual_strict_input(self):
        self.measure();sent=self.m._get('dispatch',self.run+'|target|without_experience');request=self.s.row('thought_requests',self.s.row('thought_attempts',sent['payload']['strict_attempt_ref']['id'])['request_id'])
        packet=self.s.read_artifact(request['request_artifact_id']);packet['input']['context']['unregistered']='changed';artifact=self.s.artifact(packet)
        self.s.db.execute('UPDATE thought_requests SET request_artifact_id=?,request_hash=? WHERE id=?',(artifact,__import__('digital_life.domain.tool_learning_contract',fromlist=['fingerprint']).fingerprint(packet),request['id']))
        with self.assertRaises(Forbidden):self.m.checked_report(self.report)
    def test_false_not_applicable_is_not_an_unknown_measurement_shortcut(self):
        request=deepcopy(self.request);request['payload']['assessment']['measurement_state']='not_applicable'
        with self.assertRaises(Forbidden):self.sdk.record_effect(self.entry,request)
    def test_current_memory_permission_loss_excludes_shadow_sample(self):
        result=self.measure();entry,_=self.k.owners.entry('M03','evaluate',self.actor);request=self.envelope(entry,self.request['payload']['assessment']);self.sdk.adopt_shadow(entry,request,result['result_refs'][0],self.actor)
        policy=self.s.insert('policy_versions',version=9123,mode='authorization',scope={'memory_readers':[self.s.config()['self_actor']]},effective_at=utc(),authority=self.actor)
        memory=self.s.rows('memory_items')[0];self.s.db.execute('UPDATE memory_items SET access_policy_ref=? WHERE id=?',(policy,memory['id']))
        from digital_life.application.cognition.cognition_experience import CognitiveExperience
        view=CognitiveExperience(self.s).snapshot(self.actor);self.assertEqual(sum(c['sample_count'] for c in view['cells']),0)
        with self.assertRaises(Forbidden):self.sdk.adopt_shadow(entry,request,result['result_refs'][0],self.actor)
    def test_F1_at_actual_provider_boundary_retains_no_late_prediction(self):
        run=self.sdk.register(self.entry,self.request,self.op,self.cases,2,self.m.commitment(self.labels,self.nonce));owner=self.execution();original=owner.provider.generate_fresh
        def changed(packet,**kwargs):
            self.invalidate_source();return original(packet,**kwargs)
        owner.provider.generate_fresh=changed
        with self.assertRaises((Forbidden,Conflict)):self.m.run_predictions(run,None,self.actor,strict_execution=owner,entry=self.entry)
        self.assertIsNone(self.m._get('prediction',run+'|target|without_experience'))
        doc=json.loads(self.s.row('activities',self.activity)['budget_json']);self.assertTrue(doc['ledger']['halted'])
    def test_other_work_cannot_borrow_report_or_binding(self):
        self.measure();request=deepcopy(self.request);request.update(command_id=identifier(),idempotency_key=identifier());binding=self.sdk.binding(self.run)
        with patch.object(self.sdk,'binding',return_value=dict(binding,work=ref(self.s,self.activity))):
            with self.assertRaises(Conflict):self.sdk.record_effect(self.entry,request)
    def test_partial_provider_usage_is_preserved_without_zero_total(self):
        run=self.sdk.register(self.entry,self.request,self.op,self.cases,2,self.m.commitment(self.labels,self.nonce));owner=self.execution();original=owner.provider.transport
        def partial(*args):
            response=original(*args);del response['usage']['completion_tokens'];return response
        owner.provider.transport=partial;self.m.run_predictions(run,None,self.actor,strict_execution=owner,entry=self.entry)
        prediction=self.m._get('prediction',run+'|target|without_experience')['payload'];self.assertIsNone(prediction['actual_tokens']);self.assertFalse(prediction['usage_known'])
        attempt=self.s.row('thought_attempts',self.m._get('dispatch',run+'|target|without_experience')['payload']['strict_attempt_ref']['id']);facts=json.loads(attempt['usage_json'])['measurements']['dimensions'];self.assertEqual(facts['input_tokens']['value'],100);self.assertEqual(facts['output_tokens']['status'],'unknown')

    def test_actual_retention_veto_keeps_negative_gain(self):
        self.mode='retention-regression';result=self.measure();a=self.s.read_artifact(self.s.row('tl_effect',result['result_refs'][0]['id'])['payload_artifact_id'])
        self.assertGreater(a['retention_components']['value']['target_gain'],0);self.assertGreater(a['retention_components']['value']['retention_regression'],0);self.assertLess(a['gain']['value'],0)
    def test_F1_before_real_M03_save_prevents_new_shadow_version(self):
        result=self.measure();entry,_=self.k.owners.entry('M03','evaluate',self.actor);request=self.envelope(entry,self.request['payload']['assessment'])
        from digital_life.application.cognition.cognition_experience import CognitiveExperience
        original=CognitiveExperience.save
        before=len(CognitiveExperience(self.s).events())
        def revoked(service,*args):
            self.invalidate_source();return original(service,*args)
        with patch.object(CognitiveExperience,'save',revoked):
            with self.assertRaises((Forbidden,Conflict)):self.sdk.adopt_shadow(entry,request,result['result_refs'][0],self.actor)
        self.assertEqual(len(CognitiveExperience(self.s).events()),before)

    def test_missing_original_receipt_blocks_effect_and_keeps_unknown_read(self):
        source=self.s.read_artifact(self.s.row('tl_work',self.work['id'])['conditions_artifact_id'])['source'];artifact=self.s.row('artifacts',source['artifact']['id']);(self.s.root/'blobs'/artifact['storage_ref']).unlink()
        with self.assertRaises(ContractError):self.sdk.record_effect(self.entry,self.request)
        self.assertEqual(len(self.s.rows('tl_effect')),0)
        activity=self.s.row('tl_work',self.work['id'])['learning_activity_id'];doc=json.loads(self.s.row('activities',activity)['budget_json']);self.assertTrue(doc['ledger']['halted'])

    def test_initial_scope_cannot_masquerade_as_content_or_retrieval(self):
        for property,kind,unit in (('retrieval hit rate','effect_statistic','percent'),('source fidelity','source_report','matched words'),('world correctness','world_claim','probability')):
            request=deepcopy(self.request);request['payload']['assessment']['case_scope'].update(property=property,claim_target=kind,unit=slot(unit))
            with self.subTest(property=property):
                with self.assertRaises(Conflict):self.sdk.register(self.entry,request,self.op,self.cases,2,self.m.commitment(self.labels,self.nonce))
        self.assertEqual(self.m._events('registered'),[])
    def test_initial_scope_cases_cannot_differ_from_actual_measurement(self):
        cases=deepcopy(self.cases);cases[0]['input']='different actual target input'
        with self.assertRaises(Conflict):self.sdk.register(self.entry,self.request,self.op,cases,2,self.m.commitment(self.labels,self.nonce))
        self.assertEqual(self.m._events('registered'),[])
