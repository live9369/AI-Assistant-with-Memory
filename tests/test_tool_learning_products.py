"""Pure closed TL products and operation payloads; no instance or model calls."""
import copy
import json
import unittest
from digital_life.domain.contracts import ContractError
from digital_life.domain import tool_learning_products as p

ID='a'*32
TIME='2026-11-09T00:00:00.000Z'
def sl(value=None,status='not_applicable'):
 return {'status':status,'value':value,'reason_code':'none' if status=='known' else 'not_requested','reason':'' if status=='known' else 'not applicable to fixture','basis_refs':[]}
def ref(kind='fixture',key='existing'):
 return {'instance_id':ID,'id':key,'kind':kind,'revision':sl()}
def ver():return {'object':ref(),'revision':1,'epoch':0}
def principal(module='M14',purpose='learn'):
 return {'actor':ref(),'module':module,'recipient':ref(),'purpose':purpose,'authorization':ref()}
def method():return {'name':'deterministic-fixture','version':'1','request_ref':sl(),'model_config_ref':sl()}
def coverage():return {'state':'complete','domain':sl('fixture','known'),'scanned':1,'limit':1,'truncated':False,'missing':[]}
def check(state):return {'state':state,'checker':principal(),'method':method(),'at':TIME,'targets':[],'reason':'none','basis_refs':[]}
def digest():return {'algorithm':'sha256','hex':'b'*64}
def evidence():
 return {'source':ref(),'source_kind':'system_event','original_result':sl(),'receipt':sl(),'artifact':ref(),'source_revision':sl(),'digest':digest(),'media_type':'application/json','encoding':sl('UTF-8','known'),'view':sl(),'view_digest':sl(),'locator':{'kind':'whole_artifact','justification':'atomic fixture'},'origin_method':method(),'observed_at':sl(TIME,'known'),'reported_at':sl(),'coverage':coverage(),'derivation_refs':[],'access_dependencies':[]}
def scope():
 return {'subject':sl(ref(),'known'),'subject_label':sl('fixture','known'),'property':'count','claim_target':'source_report','temporal':{'kind':'observation','start':sl(TIME,'known'),'end':sl(TIME,'known'),'bounds':'point'},'conditions':sl({},'known'),'domain':sl('fixture','known'),'unit':sl('items','known'),'granularity':sl(),'coverage':coverage(),'exceptions':[],'limitations':[]}
def claim():return {'claim_id':ID,'form':'source_report','subject':sl(ref(),'known'),'predicate':'count','value':sl(10,'known'),'scope':scope(),'evidence':[evidence()],'derivation':method(),'limitations':[]}
def effect():return {'measurement_state':'not_measured','measurement_ref':sl(),'baseline_ref':sl(),'candidate_ref':sl(),'method_refs':[],'metric_definition':ref(),'case_scope':scope(),'gain':sl(None,'not_collected'),'retention_components':sl(),'sample_counts':sl(),'independence':sl(),'usage':sl()}
def proposal():return {'target':{'owner':'M03','mode':'new','object':sl(),'expected':sl(),'content_kind':'source_report'},'operation':'add','claims':[claim()],'rationale':'source reports a value','preserved_content':[],'unresolved_items':[],'atomic_group':sl()}
def product(kind='UpdateProposal',body=None):
 return {'contract':'TL-LOOP-0.1','schema_revision':1,'product_id':ID,'instance_id':ID,'producer':principal(),'work_ref':ref(),'purpose':'learn','method':method(),'created_at':TIME,'source_refs':[evidence()],'derivation_links':[],'limitations':[],'missing_items':[],'access_dependencies':[],'revision_links':[],'processing_identity':digest(),'downstream_refs':[],'checks':{'source_check':check('readable'),'locator_check':check('matched'),'support_check':check('supports_scoped_claim'),'readiness':check('ready_for_handoff')},'product_type':kind,'body':proposal() if body is None else body}
def decision(operation='accept'):
 return {'id':ID,'work_ref':ref(),'proposal_ref':ref(),'review_round':0,'actor':principal('M03','accept'),'policy_ref':ref(),'checks':{'G%02d'%i:check('pass') for i in range(1,9)},'operation':operation,'actual_scope':scope(),'content_ref':sl(ref(),'known'),'revision_ref':sl(ref(),'known'),'previous':sl(),'reason':'none','coverage':coverage(),'handoff_refs':[],'created_at':TIME}
def representation():
 return {'id':ID,'series_ref':ref(),'representation_no':1,'content_ref':ref(),'content_revision':ver(),'decision_ref':ref(),'format_version':'TL-TEXT-1','body_artifact':ref(),'body_digest':digest(),'claims':[claim()],'source_refs':[evidence()],'scope':scope(),'limitations':[],'dependencies':[],'group':sl(),'published_at':TIME}
def control():return {'policy':ver(),'configuration':ver(),'source_epochs':[],'runtime_epoch':0,'input_epoch':0,'cancelled':False}
def budget():return {'account_ref':ref(),'deadline':TIME,'max_attempts':3,'max_input_tokens':100,'max_output_tokens':100,'max_tool_calls':2,'max_scan':10,'max_items':2,'max_bytes':1000}
def envelope(payload=None):return {'contract':'TL-LOOP-0.1','schema_revision':1,'command_id':ID,'instance_id':ID,'principal':principal(),'work_ref':sl(ref(),'known'),'idempotency_key':'key','expected':sl(),'control':control(),'budget':budget(),'payload':payload or {}}
def recall_request():return {'contract':'TL-LOOP-0.1','schema_revision':1,'request_id':ID,'instance_id':ID,'activity_ref':sl(),'context_ref':sl(),'principal':principal('M04','recall_experience'),'entry':'execution','query':'count','target_scope':scope(),'exact_refs':[],'version_mode':'current','as_of':sl(),'group_required':False,'allowed_kinds':['accepted_content'],'control':control(),'budget':budget(),'index_fallback':'deny'}
def item():return {'id':ID,'kind':'accepted_content','memory_ref':sl(),'memory_revision':sl(),'representation_ref':sl(ref(),'known'),'representation_revision':sl(ver(),'known'),'content_ref':sl(ref(),'known'),'content_revision':sl(ver(),'known'),'decision_ref':sl(ref(),'known'),'body':'source reports count=10','body_digest':digest(),'origin_kind':'system_event','processing':'extract','source_refs':[evidence()],'scope':scope(),'limitations':[],'value_slots':[sl(10,'known')],'usage_state':'current','group_ready':sl(),'relations':[],'selection':{'method':method(),'score':sl(),'reason':'match'},'control':control(),'dependencies':[]}
def recall_result():return {'request_id':ID,'retrieval_run':sl(),'purpose':'recall_experience','method':method(),'checked_at':TIME,'coverage':coverage(),'completion':'complete','empty_reason':sl(),'items':[item()],'gaps':[],'dependencies':[]}
def payloads():
 return {'admit_observation':{'source':evidence(),'purpose':'learn','source_activity':ref(),'processing_method':method(),'previous_work':sl()},'assess_observation':{'source':evidence(),'baseline_refs':[],'baseline_coverage':coverage(),'method':method()},'decide_proposal':{'proposal':ref(),'review_round':0,'policy':ref(),'review':sl(),'atomic_group':sl()},'claim_representation':{'handoff':ref(),'expected_generation':0,'worker':ref(),'lease_seconds':30},'publish_representation':{'handoff':ref(),'lease_generation':1,'worker':ref(),'representation':representation()},'recall':recall_request(),'apply_invalidation':{'change_id':ID,'kind':'revoke','source':ver(),'replacement':sl(),'affected_scope':scope(),'subjects':[],'purposes':['learn'],'expected_epoch':0,'evidence':[evidence()],'erase_scope':sl()},'acknowledge_propagation':{'barrier':ref(),'generation':1,'domain':'M04','targets':[],'coverage':coverage(),'actions':[],'verification':ref()},'resume_work':{'work':ref(),'expected_work_revision':0,'conditions':[],'reconciliation':ref()},'record_effect':{'work':ref(),'measurement':sl(),'assessment':effect()}}

class ProductTests(unittest.TestCase):
 def reject(self,name,v):
  with self.assertRaises(ContractError):p.validate(name,v)
 def test_four_products_and_input_unchanged(self):
  bodies={'ObservationExtract':{'observations':[claim()],'coverage':coverage(),'empty_reason':sl()},'ComparisonAssessment':{'baselines':[],'comparison_coverage':coverage(),'comparisons':[],'outcome':'insufficient'},'UpdateProposal':proposal(),'EffectAssessment':effect()}
  for kind,body in bodies.items():
   v=product(kind,body);before=copy.deepcopy(v);self.assertIs(p.validate('Product',v),v);self.assertEqual(v,before)
 def test_product_missing_unknown_fields_and_wrong_producer(self):
  for change in ('missing','extra','owner'):
   v=product()
   if change=='missing':del v['checks']
   elif change=='extra':v['accepted']=True
   else:v['producer']['module']='M03'
   self.reject('Product',v)
 def test_new_and_existing_targets_are_explicit(self):
  v=proposal();p.validate('UpdateProposal',v);v['target']['object']=sl(ref(),'known');self.reject('UpdateProposal',v)
  v=proposal();v['target'].update(mode='existing',object=sl(ref(),'known'),expected=sl(ver(),'known'));p.validate('UpdateProposal',v)
  v['target']['expected']['value']['object']['kind']='different';self.reject('UpdateProposal',v)
 def test_existing_target_mismatch_id_and_missing_baseline(self):
  v=proposal();v['target'].update(mode='existing',object=sl(ref(),'known'),expected=sl(ver(),'known'));v['target']['expected']['value']['object']['id']='different';self.reject('UpdateProposal',v)
  v['target']['expected']=sl();self.reject('UpdateProposal',v)
 def test_comparison_cannot_claim_conflict_without_comparability(self):
  v={'observation':ref(),'baseline':sl(),'comparable':sl(),'basis':[],'difference':'conflict','support':[],'counterevidence':[],'limitations':[]};self.reject('Comparison',v);v['difference']='insufficient';p.validate('Comparison',v)
 def test_measured_gain_zero_and_negative_are_valid(self):
  for n in (0,-.25,1):
   v=effect();v.update(measurement_state='measured',measurement_ref=sl(ref(),'known'),gain=sl(n,'known'));p.validate('EffectAssessment',v)
 def test_known_gain_needs_measurement_and_reference(self):
  v=effect();v['gain']=sl(0,'known');self.reject('EffectAssessment',v);v['measurement_state']='measured';self.reject('EffectAssessment',v)
  v['gain']=sl(True,'known');v['measurement_ref']=sl(ref(),'known');self.reject('EffectAssessment',v)
 def test_accept_requires_all_eight_checks_pass(self):
  p.validate('Decision',decision())
  for key in ('G01','G04','G08'):
   v=decision();v['checks'][key]['state']='incomplete';self.reject('Decision',v)
 def test_nonaccept_does_not_publish_and_reuse_has_existing_refs(self):
  for operation in ('candidate','reject','defer','conflict'):
   v=decision(operation);v['handoff_refs']=[ref()];self.reject('Decision',v)
  v=decision('reuse');v['content_ref']=sl();self.reject('Decision',v)
 def test_representation_content_object_and_nonempty_sources(self):
  v=representation();p.validate('Representation',v);v['content_revision']['object']['id']='other';self.reject('Representation',v)
  v=representation();v['source_refs']=[];self.reject('Representation',v)
 def test_envelope_unknown_fields_and_json_errors(self):
  v=envelope();p.validate('Envelope',v);v['operation']='admit_observation';self.reject('Envelope',v)
  for raw in ('{"a":1,"a":2}','{"a":NaN}','{"a":"\\ud800"}'):
   with self.assertRaises(ContractError):p.loads(raw)
 def test_all_ten_payloads_and_nested_extras(self):
  for operation,payload in payloads().items():
   v=payload if operation=='recall' else envelope(payload)
   if operation=='admit_observation':v['work_ref']=sl()
   p.validate(operation+'.request',v)
   if operation=='recall':v['surprise']=True
   else:v['payload']['surprise']=True
   self.reject(operation+'.request',v)
 def test_operation_work_ref_and_limits(self):
  v=envelope(payloads()['admit_observation']);self.reject('admit_observation.request',v)
  v=envelope(payloads()['claim_representation']);v['payload']['lease_seconds']=301;self.reject('claim_representation.request',v)
  v=envelope(payloads()['resume_work']);v['work_ref']=sl();self.reject('resume_work.request',v)
 def test_erasure_and_record_effect_reference_consistency(self):
  v=envelope(payloads()['apply_invalidation']);v['payload']['kind']='erase';self.reject('apply_invalidation.request',v)
  v=envelope(payloads()['record_effect']);v['payload']['measurement']=sl(ref(),'known');self.reject('record_effect.request',v)
 def test_recall_request_purpose_and_versions(self):
  v=recall_request();p.validate('RecallRequest',v);v['allowed_kinds']=['shadow_statistic'];self.reject('RecallRequest',v)
  v=recall_request();v['entry']='controller_audit';self.reject('RecallRequest',v)
  for mode in ('specified','as_of'):
   v=recall_request();v['version_mode']=mode;self.reject('RecallRequest',v)
 def test_recall_current_content_requires_references_not_candidate(self):
  v=item();p.validate('RecallItem',v);v['kind']='candidate';self.reject('RecallItem',v)
  v=item();v['decision_ref']=sl();self.reject('RecallItem',v)
 def test_complete_empty_recall_needs_reason(self):
  v=recall_result();p.validate('RecallResult',v);v['items']=[];self.reject('RecallResult',v);v['empty_reason']=sl('out_of_scope','known');p.validate('RecallResult',v)
 def test_response_retry_and_unknown_commit(self):
  v={'command_id':ID,'operation':'decide_proposal','disposition':'failed','owner':'M03','result_refs':[],'current':sl(),'reason':'other','error_code':'COMMIT_UNKNOWN','coverage':coverage(),'retry':{'allowed':False,'condition':sl(),'resume_work':sl()},'committed_at':sl()};p.validate('Response',v);v['committed_at']=sl(TIME,'known');self.reject('Response',v)
  v['committed_at']=sl();v['retry']['allowed']=True;self.reject('Response',v)
 def test_decoded_type_validation_and_surrogate_python_values(self):
  v=product();self.assertEqual(p.loads(json.dumps(v),'Product'),v);v['body']['rationale']='\ud800';self.reject('Product',v)

 def test_recall_direct_request_not_an_extra_write_envelope(self):
  v=recall_request();self.assertIs(p.validate('recall.request',v),v);self.assertIs(p.validate_envelope(v,'recall'),v)
  self.reject('recall.request',envelope(v))
 def test_recall_content_and_memory_ref_match_version_object(self):
  v=item();v['content_revision']['value']['object']['kind']='different';self.reject('RecallItem',v)
  v=item();v['memory_ref']=sl(ref('memory'),'known');v['memory_revision']=sl(ver(),'known');self.reject('RecallItem',v)
 def test_representation_version_and_series_are_distinct_valid_ids(self):
  v=item();v['representation_ref']=sl(ref('tl_representation','version-id'),'known');v['representation_revision']=sl({'object':ref('tl_representation_head','series-id'),'revision':3,'epoch':1},'known');p.validate('RecallItem',v)
 def test_reuse_may_reference_existing_representation_obligation(self):
  v=decision('reuse');v['handoff_refs']=[ref('tl_handoff')];p.validate('Decision',v)

 def test_large_integer_gain_keeps_its_exact_value(self):
  n=10**1000;v=effect();v.update(measurement_state='measured',measurement_ref=sl(ref(),'known'),gain=sl(n,'known'));self.assertIs(p.validate('EffectAssessment',v),v);self.assertEqual(v['gain']['value'],n)
 def test_direct_request_api_rejects_surrogate_in_plain_json_payload(self):
  v=envelope({'quoted':'\ud800'})
  with self.assertRaises(ContractError):p.validate_envelope(v)
