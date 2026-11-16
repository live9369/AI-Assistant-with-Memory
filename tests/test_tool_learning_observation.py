"""IM07 bounded learning on new synthetic stores; no real provider or tool."""
import copy
import json
from pathlib import Path
import unittest
import threading
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc,dumps
from digital_life.domain import tool_learning_contract as c
from digital_life.application.learning.observation import ToolLearningObservation,ObservationAuthority,ObservationThoughtPort
from digital_life.application.learning.eligibility import slot,ref
from digital_life.application.learning.budget import BudgetAuthority,DIMENSIONS
from digital_life.infrastructure.persistence.tool_learning_store import StorageGrant
from tests import test_tool_learning_invalidation as six
from tests.test_tool_learning_products import scope,method,sl,coverage,claim


class MechanicalBudget(BudgetAuthority):
    def verify_budget(self,*args):return None
    def verify_entry(self,entry,work,reservation,witness):
        if witness.get('contract') not in ('TL-OBSERVATION-READ-ENTRY-1','TL-OBSERVATION-THOUGHT-ENTRY-1'):raise Forbidden('unrecognized mechanical witness')
    def verify_settlement(self,*args):return None


class MechanicalObservation(ObservationAuthority):
    def __init__(self,case):self.case=case;self.baselines={};self.deny=False;self.retention_hook=None
    def verify(self,entry,operation,request,instance_id,stage):
        if self.deny:raise Forbidden('test authority revoked')
        return StorageGrant('M14',frozenset(('tl_work','tl_product','tl_dependency')))
    def project_response(self,entry,operation,request,response,instance_id,stage):return response
    def verify_observation(self,*args):
        if self.deny:raise Forbidden('test observation denial')
    def source_token(self,entry,request):return {'object':copy.deepcopy(request['payload']['source']['source']),'revision':1,'epoch':0}
    def baseline_material(self,entry,request,token):return copy.deepcopy(self.baselines[token['object']['id']])
    def inference_binding(self,entry,request,packet):return dict(self.case.route,process_run_id='synthetic-no-runtime-process')
    def verify_response_retention(self,*args):
        if self.retention_hook:self.retention_hook()


class FreshFixture(ObservationThoughtPort):
    def __init__(self,route):self.route=route;self.calls=[];self.hook=None;self.usage_known=True;self.invalid=False;self.error=False
    def configured_binding(self):return copy.deepcopy(self.route)
    def preflight(self,packet):return 5
    def generate_fresh(self,packet):
        self.calls.append(copy.deepcopy(packet))
        if self.hook:self.hook()
        if self.error:raise OSError('synthetic transport failure')
        usage={k:0 for k in DIMENSIONS};usage.update(attempts=1,input_tokens=5,output_tokens=5)
        body={'contract':'TL-OBSERVATION-INTERPRETATION-1','rationale':'bounded explanation only','limitations':['not a world fact'],'missing_items':[]}
        if self.invalid:body['world_truth']=True
        return {'body':body,'usage':usage if self.usage_known else None,'route':copy.deepcopy(self.route)}


class ObservationTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_work import WorkTests
        self.base=WorkTests();self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.s=self.base.s;self.db=self.s.db
        self.metric=self.s.insert('metric_definitions',name='synthetic-effect',formula_version='1',unit='score',denominator_rule='predeclared',missing_rule='unknown',stratification={})
        self.plan={'contract':'TL-OBSERVATION-PLAN-1','subject':slot(ref(self.s,self.base.f.expected['self_actor'])),'scope':scope(),'predicate':'reported_inventory',
                   'outputs':['ObservationExtract','ComparisonAssessment','UpdateProposal','EffectAssessment'],'effect_metric':slot(ref(self.s,self.metric)),'interpret':False}
        self.plan['scope']['subject']=copy.deepcopy(self.plan['subject']);self.plan['scope']['subject_label']=slot('synthetic individual');self.plan['scope']['granularity']=slot('one exact reported inventory count')
        self.request=copy.deepcopy(self.base.request)
        self.request['budget'].update(max_bytes=20000)
        self.source=self.request['payload']['source'];self.source['source']=ref(self.s,self.base.f.expected['memory_id']);self.source['locator']={'kind':'json_pointer','pointer':'/inventory'}
        self.route={'configuration':ref(self.s,self.db.execute('SELECT id FROM configuration_versions LIMIT 1').fetchone()[0]),
            'model':ref(self.s,self.db.execute('SELECT id FROM model_versions LIMIT 1').fetchone()[0]),'provider':'synthetic-fresh-fixture'}
        self.authority=MechanicalObservation(self);self.thought=FreshFixture(self.route)
        self.service=ToolLearningObservation(self.s,self.authority,MechanicalBudget(),six.MechanicalEligibility(),self.thought)
        self.work=None;self.assessment=None

    def prepare(self):
        artifact=self.s.artifact(self.plan);self.request['payload']['processing_method']={'name':'tl-observation','version':'1','request_ref':slot(ref(self.s,artifact)),'model_config_ref':sl()}
        response=self.base.admit(self.request);self.work=self.s.row('tl_work',response['result_refs'][0]['id'])
        request=copy.deepcopy(self.request);request.update(command_id=identifier(),idempotency_key=identifier(),work_ref=slot(ref(self.s,self.work['id'])))
        request['budget']=json.loads(self.s.row('activities',self.work['learning_activity_id'])['budget_json'])['budget']
        request['payload']={'source':copy.deepcopy(self.source),'baseline_refs':[],'baseline_coverage':coverage(),'method':copy.deepcopy(self.request['payload']['processing_method'])}
        self.assessment=request;return request
    def assess(self):
        if self.assessment is None:self.prepare()
        return self.service.assess('synthetic-observation',self.assessment)
    def products(self):return [self.s.read_artifact(r['payload_artifact_id']) for r in self.db.execute('SELECT * FROM tl_product ORDER BY rowid')]
    def value(self,value):
        artifact=self.s.artifact({'inventory':value});row=self.s.row('artifacts',artifact)
        self.source.update(artifact=ref(self.s,artifact),digest={'algorithm':'sha256','hex':row['hash']})
    def baseline(self,value=7,unknown_scope=False):
        if self.assessment is None:self.prepare()
        baseline_scope=copy.deepcopy(self.plan['scope'])
        if unknown_scope:baseline_scope['unit']=sl(None,'unknown')
        with self.s.tx():
            entity=self.db.execute('SELECT id FROM world_entities LIMIT 1').fetchone()
            if entity is None:
                entity_id=self.s.insert('world_entities',entity_type='person',identity_state='provisional')
            else:entity_id=entity[0]
            belief=self.s.insert('cognition_beliefs',subject_ref=entity_id,predicate='reported_inventory',literal=dumps(value),scope=baseline_scope)
            revision=self.s.insert('cognition_belief_revisions',belief_id=belief,revision_no=1,content='typed synthetic source report',acceptance_state='held',uncertainty_json={},method_version='synthetic-1')
            self.db.execute('UPDATE cognition_beliefs SET current_revision_id=? WHERE id=?',(revision,belief))
        token={'object':ref(self.s,belief),'revision':1,'epoch':0}
        item=claim();item.update(claim_id=identifier(),subject=copy.deepcopy(self.plan['subject']),predicate=self.plan['predicate'],value=slot(value),scope=copy.deepcopy(baseline_scope),evidence=[copy.deepcopy(self.source)],derivation=method())
        if value is None:item['value']={'status':'known','value':None,'reason_code':'source_reported_null','reason':'source reports null','basis_refs':[]}
        if unknown_scope:item['scope']['unit']=sl(None,'unknown')
        body={'contract':'TL-OBSERVATION-BASELINE-1','token':token,'claims':[item]};artifact=self.s.artifact(body)
        self.authority.baselines[token['object']['id']]={'token':token,'artifact':ref(self.s,artifact)}
        self.assessment['payload']['baseline_refs']=[token]
        return item,token

    def test_four_products_are_typed_scoped_and_not_accepted_content(self):
        response=self.assess();products=self.products();self.assertEqual({p['product_type'] for p in products},set(self.plan['outputs']))
        for p in products:c.validate('Product',p)
        extracted=next(p for p in products if p['product_type']=='ObservationExtract')['body']['observations'][0]
        self.assertEqual(extracted['value']['value'],7);self.assertEqual(extracted['scope']['claim_target'],'source_report')
        effect=next(p for p in products if p['product_type']=='EffectAssessment')['body'];self.assertEqual(effect['gain']['status'],'not_collected');self.assertIsNone(effect['gain']['value'])
        self.assertEqual(self.s.row('tl_work',self.work['id'])['state'],'awaiting_decision')
        for table in ('tl_decision','tl_content_revision','tl_representation'):self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        self.assertEqual(self.thought.calls,[]);self.assertEqual(len(response['result_refs']),4)

    def test_zero_preserved_in_all_claim_bodies(self):
        self.value(0);self.assess()
        for p in self.products():
            for item in p['body'].get('claims',p['body'].get('observations',[])):
                self.assertEqual(item['value']['status'],'known');self.assertEqual(type(item['value']['value']),int);self.assertEqual(item['value']['value'],0)
    def test_false_preserved(self):
        self.value(False);self.assess()
        for p in self.products():
            for item in p['body'].get('claims',p['body'].get('observations',[])):self.assertEqual(item['value']['status'],'known');self.assertIs(item['value']['value'],False)
    def test_explicit_null_preserved(self):
        self.value(None);self.assess()
        for p in self.products():
            for item in p['body'].get('claims',p['body'].get('observations',[])):
                self.assertEqual(item['value']['status'],'known');self.assertIsNone(item['value']['value']);self.assertEqual(item['value']['reason_code'],'source_reported_null')

    def test_false_is_not_numeric_zero_in_comparison(self):
        self.value(False);self.prepare();item,token=self.baseline(0)
        # An independent actual source reports zero. Reusing the very same
        # False receipt while interpreting it as zero would instead be a
        # correctable parsing error, not disagreement between two reports.
        event=self.s.event('synthetic.independent.zero',payload={'inventory':0})
        artifact=self.s.row('runtime_events',event)['payload_artifact_id']
        source=copy.deepcopy(self.source);source.update(source=ref(self.s,event),artifact=ref(self.s,artifact),digest={'algorithm':'sha256','hex':self.s.row('artifacts',artifact)['hash']})
        item['evidence']=[source]
        body={'contract':'TL-OBSERVATION-BASELINE-1','token':token,'claims':[item]}
        self.authority.baselines[token['object']['id']]['artifact']=ref(self.s,self.s.artifact(body))
        self.assess()
        compared=next(p for p in self.products() if p['product_type']=='ComparisonAssessment');self.assertEqual(compared['body']['outcome'],'conflict')
        proposal=next(p for p in self.products() if p['product_type']=='UpdateProposal');self.assertEqual(proposal['body']['operation'],'mark_conflict')

    def test_unknown_scope_and_ambiguous_subject_do_not_become_comparable(self):
        self.plan['subject']=sl(None,'unknown');self.plan['scope']['subject']=copy.deepcopy(self.plan['subject']);self.prepare();self.baseline(7,unknown_scope=True);self.assess()
        compared=next(p for p in self.products() if p['product_type']=='ComparisonAssessment');self.assertEqual(compared['body']['outcome'],'insufficient');self.assertNotEqual(compared['body']['comparisons'][0]['comparable']['status'],'known')
        self.assertFalse(any(p['product_type']=='UpdateProposal' for p in self.products()))

    def test_known_null_not_confused_with_unknown(self):
        self.value(None);self.prepare();item,token=self.baseline(None);item['value']=sl(None,'unknown')
        artifact=self.s.artifact({'contract':'TL-OBSERVATION-BASELINE-1','token':token,'claims':[item]});self.authority.baselines[token['object']['id']]['artifact']=ref(self.s,artifact)
        self.assess();comparison=next(p for p in self.products() if p['product_type']=='ComparisonAssessment');self.assertEqual(comparison['body']['comparisons'][0]['difference'],'insufficient')

    def test_same_command_and_new_key_reuse_without_read_or_inference_again(self):
        self.plan['interpret']=True;first=self.assess();before=self.budget_rows()
        self.assertEqual(self.assess(),first)
        second=copy.deepcopy(self.assessment);second.update(command_id=identifier(),idempotency_key=identifier())
        result=self.service.assess('synthetic-observation',second);self.assertEqual(result['disposition'],'reused');self.assertEqual(self.budget_rows(),before);self.assertEqual(len(self.thought.calls),1)
    def budget_rows(self):return self.db.execute('SELECT count(*) FROM budget_reservations').fetchone()[0]

    def test_missing_locator_is_finite_wait_not_known_null(self):
        self.source['locator']={'kind':'json_pointer','pointer':'/not-there'};result=self.assess();self.assertEqual(result['disposition'],'deferred');self.assertEqual(self.products(),[])
        self.assertEqual(self.s.row('tl_work',self.work['id'])['state'],'waiting');self.assertEqual(len(self.thought.calls),0)

    def erase_request(self):
        self.prepare() if self.work is None else None
        payload={'change_id':identifier(),'kind':'erase','source':self.authority.source_token('x',self.assessment),'replacement':slot(),
            'affected_scope':copy.deepcopy(self.plan['scope']),'subjects':[],'purposes':['learn'],'expected_epoch':0,'evidence':[copy.deepcopy(self.source)],'erase_scope':slot(ref(self.s,self.base.f.expected['policy_id']))}
        request=copy.deepcopy(self.assessment);request.update(command_id=identifier(),idempotency_key=identifier(),payload=payload)
        request['principal']=copy.deepcopy(request['principal']);request['principal'].update(module='M12',purpose='erase')
        return request

    def apply_erase(self,request):
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        return ToolLearningInvalidation(self.s,six.MechanicalInvalidation()).apply('mechanical-im06',request)

    def test_view_unknown_does_not_silently_use_original_pointer(self):
        self.source['view']=sl(None,'unknown');response=self.assess()
        self.assertEqual(response['disposition'],'deferred');self.assertEqual(self.products(),[])

    def test_large_view_is_checked_before_bytes_read(self):
        view=self.s.artifact({'inventory':7,'padding':'x'*25000});row=self.s.row('artifacts',view)
        self.source.update(view=slot(ref(self.s,view)),view_digest=slot({'algorithm':'sha256','hex':row['hash']}))
        result=self.assess();self.assertEqual(result['disposition'],'stopped')
        ledger=json.loads(self.s.row('activities',self.work['learning_activity_id'])['budget_json'])['ledger']
        actual=next(iter(ledger['reservations'].values()))['actual']
        self.assertEqual(actual['bytes'],self.s.row('artifacts',self.source['artifact']['id'])['size']);self.assertEqual(actual['items'],1)

    def test_missing_source_bytes_keep_unknown_consumption(self):
        self.prepare();row=self.s.row('artifacts',self.source['artifact']['id']);(self.s.root/'blobs'/row['storage_ref']).unlink()
        with self.assertRaises(ContractError):self.assess()
        ledger=json.loads(self.s.row('activities',self.work['learning_activity_id'])['budget_json'])['ledger']
        self.assertEqual(next(iter(ledger['reservations'].values()))['state'],'usage_unknown')
        self.assertEqual(self.products(),[])

    def test_second_baseline_failure_keeps_all_confirmed_reads(self):
        self.prepare();_,first=self.baseline(7);_,second=self.baseline(8)
        artifact=self.s.artifact({'contract':'bad','token':second,'claims':[]});self.authority.baselines[second['object']['id']]['artifact']=ref(self.s,artifact)
        self.assessment['payload']['baseline_refs']=[first,second]
        expected=sum(self.s.row('artifacts',key)['size'] for key in (self.source['artifact']['id'],self.authority.baselines[first['object']['id']]['artifact']['id'],artifact))
        with self.assertRaises(ContractError):self.assess()
        ledger=json.loads(self.s.row('activities',self.work['learning_activity_id'])['budget_json'])['ledger']
        actual=next(iter(ledger['reservations'].values()))['actual'];self.assertEqual(actual['bytes'],expected);self.assertEqual(actual['scan'],3)

    def test_same_exact_observation_is_no_change_not_new_gain(self):
        self.prepare();self.baseline(7);result=self.assess()
        compared=next(p for p in self.products() if p['product_type']=='ComparisonAssessment')
        self.assertEqual(compared['body']['outcome'],'no_change');self.assertFalse(any(p['product_type']=='UpdateProposal' for p in self.products()))
        self.assertEqual(self.s.row('tl_work',self.work['id'])['state'],'no_change')

    def test_matching_second_baseline_is_target_not_first_unrelated_one(self):
        self.prepare();_,first=self.baseline(7,unknown_scope=True);_,second=self.baseline(8)
        self.assessment['payload']['baseline_refs']=[first,second];self.assess()
        proposal=next(p for p in self.products() if p['product_type']=='UpdateProposal')
        self.assertEqual(proposal['body']['target']['object']['value']['id'],second['object']['id'])
        comparison=next(p for p in self.products() if p['product_type']=='ComparisonAssessment');self.assertEqual(len(comparison['body']['comparisons']),2)

    def test_multiple_real_targets_wait_instead_of_choosing_arbitrary_one(self):
        self.prepare();_,first=self.baseline(8);_,second=self.baseline(9)
        self.assessment['payload']['baseline_refs']=[first,second];self.assess()
        self.assertFalse(any(p['product_type']=='UpdateProposal' for p in self.products()))
        self.assertEqual(self.s.row('tl_work',self.work['id'])['state'],'waiting')

    def test_f1_first_prevents_any_new_sensitive_preparation(self):
        erase=self.erase_request();self.apply_erase(erase)
        before=self.db.execute('SELECT count(*) FROM artifacts').fetchone()[0]
        with self.assertRaises((Forbidden,Conflict)):self.assess()
        self.assertEqual(self.db.execute('SELECT count(*) FROM artifacts').fetchone()[0],before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM runtime_events WHERE source='tl.observation.prepare'").fetchone()[0],0)

    def test_erase_inside_fresh_call_does_not_store_late_response(self):
        self.plan['interpret']=True;erase=self.erase_request();self.thought.hook=lambda:self.apply_erase(erase)
        with self.assertRaises((Forbidden,Conflict)):self.assess()
        self.assertEqual(self.db.execute('SELECT count(*) FROM thought_results').fetchone()[0],0);self.assertEqual(self.products(),[])
        self.assertEqual(self.db.execute("SELECT count(*) FROM runtime_events WHERE source='tl.observation.material'").fetchone()[0],0)
        self.assertEqual(len(self.thought.calls),1)

    def test_retention_write_gate_precedes_competing_f1(self):
        self.plan['interpret']=True;erase=self.erase_request();started=threading.Event();committed=threading.Event();events=[];errors=[];threads=[]
        def invalidate():
            from digital_life.infrastructure.persistence.sqlite_store import Store
            from digital_life.application.learning.invalidation import ToolLearningInvalidation
            store=Store(self.s.root)
            try:
                started.set();ToolLearningInvalidation(store,six.MechanicalInvalidation()).apply('mechanical-im06',erase);events.append('f1');committed.set()
            except BaseException as error:errors.append(error)
            finally:store.close()
        def retention():
            thread=threading.Thread(target=invalidate);threads.append(thread);thread.start();self.assertTrue(started.wait(5));self.assertFalse(committed.wait(.05));events.append('retention')
        self.authority.retention_hook=retention
        original=self.s.artifact
        def observe(value,*args,**kwargs):
            if isinstance(value,dict) and value.get('contract')=='TL-OBSERVATION-INTERPRETATION-1':events.append('response_write')
            return original(value,*args,**kwargs)
        with patch.object(self.s,'artifact',observe):
            try:self.assess()
            except (Forbidden,Conflict):pass
        for thread in threads:thread.join(5)
        self.assertEqual(errors,[]);self.assertTrue(committed.is_set());self.assertEqual(events[:3],['retention','response_write','f1'])

    def test_fresh_configured_route_mismatch_refuses_before_call(self):
        self.plan['interpret']=True;self.thought.route=dict(self.route,provider='other')
        with self.assertRaises(Forbidden):self.assess()
        self.assertEqual(self.thought.calls,[]);self.assertEqual(self.db.execute('SELECT count(*) FROM thought_requests').fetchone()[0],0)

    def test_stale_expected_work_revision_is_not_silently_ignored(self):
        self.prepare();self.assessment['expected']=slot({'object':ref(self.s,self.work['id']),'revision':9,'epoch':0})
        with self.assertRaises(Conflict):self.assess()
        self.assertEqual(self.db.execute("SELECT count(*) FROM runtime_events WHERE source='tl.observation.prepare'").fetchone()[0],0)

    def test_default_authority_and_world_scope_refused(self):
        self.prepare()
        with self.assertRaises(Forbidden):ToolLearningObservation(self.s).assess('x',self.assessment)
    def test_world_fact_plan_never_admitted_to_extraction(self):
        self.plan['scope']['claim_target']='world_claim';self.prepare()
        with self.assertRaises(Forbidden):self.assess()

    def test_fresh_packet_and_full_output_are_persisted(self):
        self.plan['interpret']=True;self.assess();packet=self.thought.calls[0]
        self.assertNotIn('history',packet);self.assertNotIn('session',packet);self.assertEqual(packet['binding']['provider'],self.route['provider'])
        row=self.db.execute('SELECT * FROM thought_requests').fetchone();self.assertEqual(self.s.read_artifact(row['request_artifact_id']),packet);self.assertEqual(row['id'],packet['request_id']);self.assertEqual(packet['work_ref']['id'],self.work['id']);self.assertLessEqual(packet['limits']['max_bytes'],self.assessment['budget']['max_bytes']);self.assertEqual(packet['limits']['deadline'],self.work['deadline'])
        result=self.db.execute('SELECT * FROM thought_results').fetchone();self.assertEqual(self.s.read_artifact(result['response_artifact_id'])['contract'],'TL-OBSERVATION-INTERPRETATION-1')
        self.assertEqual(self.budget_rows(),1)

    def test_unknown_inference_usage_kept_and_no_products_published(self):
        self.plan['interpret']=True;self.thought.usage_known=False
        with self.assertRaises(Forbidden):self.assess()
        row=self.db.execute('SELECT * FROM budget_reservations').fetchone();self.assertEqual(row['state'],'usage_unknown');self.assertEqual(self.products(),[])
        with self.assertRaises((Forbidden,Conflict)):self.assess()
        self.assertEqual(len(self.thought.calls),1)

    def test_exception_does_not_retry_or_claim_zero_consumption(self):
        self.plan['interpret']=True;self.thought.error=True
        with self.assertRaises(OSError):self.assess()
        self.assertEqual(self.db.execute('SELECT state FROM budget_reservations').fetchone()[0],'usage_unknown')
        self.assertEqual(self.products(),[])

    def test_invalid_structured_output_saved_as_invalid_not_products(self):
        self.plan['interpret']=True;self.thought.invalid=True
        with self.assertRaises(ContractError):self.assess()
        self.assertEqual(self.db.execute('SELECT validation_state FROM thought_results').fetchone()[0],'invalid')
        self.assertEqual(self.products(),[])

    def test_unknown_domain_and_granularity_do_not_prove_comparable(self):
        self.plan['scope']['domain']=sl(None,'unknown');self.plan['scope']['granularity']=sl(None,'unknown')
        self.prepare();self.baseline(7);self.assess()
        comparison=next(p for p in self.products() if p['product_type']=='ComparisonAssessment')
        self.assertEqual(comparison['body']['outcome'],'insufficient');self.assertNotEqual(comparison['body']['comparisons'][0]['comparable']['status'],'known')

    def test_missing_effect_metric_waits_without_model_or_fake_definition(self):
        self.plan['effect_metric']=sl(None,'unknown');self.plan['interpret']=True
        result=self.assess();self.assertEqual(result['disposition'],'deferred');self.assertEqual(self.thought.calls,[]);self.assertEqual(self.products(),[])

    def test_static_unversioned_source_is_supported_without_faking_revision(self):
        signal=self.s.row('activities',self.base.source_activity)['trigger_event_id'];self.source['source']=ref(self.s,signal)
        original=self.authority.source_token
        self.authority.source_token=lambda entry,request:{'object':copy.deepcopy(request['payload']['source']['source']),'revision':0,'epoch':0}
        self.plan['interpret']=True;erase=self.erase_request();self.apply_erase(erase)
        with self.assertRaises((Forbidden,Conflict)):self.assess()
        self.assertEqual(self.db.execute('SELECT count(*) FROM object_revision_registry WHERE object_id=?',(signal,)).fetchone()[0],0)
        self.assertEqual(self.thought.calls,[])

    def test_static_source_zero_can_produce_auditable_fresh_products(self):
        signal=self.s.row('activities',self.base.source_activity)['trigger_event_id'];self.source['source']=ref(self.s,signal)
        self.authority.source_token=lambda entry,request:{'object':copy.deepcopy(request['payload']['source']['source']),'revision':0,'epoch':0}
        self.plan['interpret']=True;self.assess()
        self.assertEqual(self.thought.calls[0]['source_token']['revision'],0)
        self.assertEqual(len(self.products()),4)
        self.assertEqual(self.db.execute('SELECT count(*) FROM object_revision_registry WHERE object_id=?',(signal,)).fetchone()[0],0)

    def test_known_null_conditions_do_not_mean_unconditional_comparability(self):
        self.plan['scope']['conditions']={'status':'known','value':None,'reason_code':'source_reported_null','reason':'source explicitly reports no condition data','basis_refs':[]}
        self.prepare();self.baseline(7);self.assess()
        comparison=next(p for p in self.products() if p['product_type']=='ComparisonAssessment')
        self.assertEqual(comparison['body']['outcome'],'insufficient')

    def test_remaining_byte_envelope_blocks_fresh_call_before_dispatch(self):
        self.plan['interpret']=True;self.value('x'*15000)
        with self.assertRaises(Forbidden):self.assess()
        self.assertEqual(self.thought.calls,[])

    def test_preflight_excess_input_refuses_before_model_call(self):
        self.plan['interpret']=True;self.thought.preflight=lambda packet:101
        with self.assertRaises(Forbidden):self.assess()
        self.assertEqual(self.thought.calls,[]);self.assertEqual(self.budget_rows(),0)

    def test_reported_route_mismatch_keeps_cost_but_rejects_output(self):
        self.plan['interpret']=True;original=self.thought.generate_fresh
        def wrong(packet):
            result=original(packet);result['route']['provider']='unexpected';return result
        self.thought.generate_fresh=wrong
        with self.assertRaises(Forbidden):self.assess()
        self.assertEqual(self.db.execute('SELECT state FROM budget_reservations').fetchone()[0],'settled')
        self.assertEqual(self.db.execute('SELECT count(*) FROM thought_results').fetchone()[0],0);self.assertEqual(self.products(),[])

    def test_partial_provider_usage_becomes_unknown_not_zero(self):
        self.plan['interpret']=True;original=self.thought.generate_fresh
        def partial(packet):
            result=original(packet);result['usage']={'input_tokens':5};return result
        self.thought.generate_fresh=partial
        with self.assertRaises(Forbidden):self.assess()
        self.assertEqual(self.db.execute('SELECT state FROM budget_reservations').fetchone()[0],'usage_unknown')
        self.assertEqual(self.products(),[])

    def test_actual_overrun_is_saved_and_never_publishes(self):
        self.plan['interpret']=True;original=self.thought.generate_fresh
        def overrun(packet):
            result=original(packet);result['usage']['output_tokens']=51;return result
        self.thought.generate_fresh=overrun
        with self.assertRaises(Forbidden):self.assess()
        row=self.db.execute('SELECT * FROM budget_reservations').fetchone();actual=json.loads(row['actual_usage'])['actual']
        self.assertEqual(actual['output_tokens'],51);self.assertEqual(row['state'],'settled');self.assertEqual(self.products(),[])
        self.assertEqual(self.db.execute('SELECT acceptance FROM thought_results').fetchone()[0],'rejected')

    def test_fresh_calls_for_two_work_items_do_not_share_history(self):
        self.plan['interpret']=True;self.assess();old_packet=copy.deepcopy(self.thought.calls[0])
        old_memory=self.s.row('memory_items',self.base.f.expected['memory_id']);old_revision=self.s.row('memory_revisions',self.base.f.expected['memory_revision_id'])
        with self.s.tx():
            old_memory.update(id=identifier(),current_revision_id=None);self.s.insert('memory_items',**old_memory)
            old_revision.update(id=identifier(),memory_id=old_memory['id']);self.s.insert('memory_revisions',**old_revision)
            self.db.execute('UPDATE memory_items SET current_revision_id=? WHERE id=?',(old_revision['id'],old_memory['id']))
        self.request=copy.deepcopy(self.request);self.request.update(command_id=identifier(),idempotency_key=identifier())
        self.source=self.request['payload']['source'];self.source['source']=ref(self.s,old_memory['id']);self.work=None;self.assessment=None
        self.assess();self.assertEqual(len(self.thought.calls),2);new_packet=self.thought.calls[1]
        self.assertNotEqual(old_packet['request_id'],new_packet['request_id']);self.assertNotEqual(old_packet['source_token'],new_packet['source_token'])
        for packet in self.thought.calls:self.assertNotIn('history',packet);self.assertNotIn('session',packet)

    def test_nonprocessing_staged_work_does_not_publish_new_product(self):
        self.plan['interpret']=True
        from digital_life.infrastructure.persistence.tool_learning_store import OwnedTransaction
        original=OwnedTransaction.insert
        def fail(tx,table,**fields):
            if table=='tl_product':raise RuntimeError('injected product write')
            return original(tx,table,**fields)
        with patch.object(OwnedTransaction,'insert',fail):
            with self.assertRaises(RuntimeError):self.assess()
        self.db.execute("UPDATE tl_work SET state='stopped',row_revision=row_revision+1 WHERE id=?",(self.work['id'],))
        with self.assertRaises(Forbidden):self.assess()
        self.assertEqual(self.products(),[]);self.assertEqual(len(self.thought.calls),1)

if __name__=='__main__':unittest.main()
