"""TL-LOOP-0.1 pure product contracts. Structure never grants authorization."""
import math
import re
from datetime import datetime
from digital_life.domain.contracts import ContractError
from digital_life.domain import tool_learning_types as t

MODULES=('M01','M03','M04','M12','M13','M14','M17','coordinator','evaluator')
PURPOSES=('learn','accept','represent','recall_experience','recall_episode','verify_source','evaluate','history_audit','propagate','erase','recover')
REASONS=('none','source_reported_null','not_measured','no_prior_prediction','missing_unit','ambiguous_entity','incomplete_source','unavailable_source','no_baseline','out_of_scope','not_requested','access_restricted','conflicting_support','invalid_locator','invalid_type','budget_limit','deadline','unsupported','other')
ERRORS=('NONE','CONTRACT_UNSUPPORTED','STRUCTURE_INVALID','UNAUTHORIZED','SOURCE_UNAVAILABLE','SOURCE_INVALID','SUPPORT_INSUFFICIENT','VERSION_CONFLICT','IDEMPOTENCY_CONFLICT','POLICY_MISSING','GROUP_NOT_READY','LEASE_STALE','STOPPED','CANCELLED','DEADLINE_EXCEEDED','BUDGET_EXHAUSTED','STORAGE_FAILED','COMMIT_UNKNOWN','COVERAGE_INCOMPLETE','ERASURE_BLOCKED','RESTORE_BLOCKED')
KINDS=('episode','accepted_content','source_evidence','candidate','history','shadow_statistic')

def fail(message):raise ContractError(message)
def b(name,value):return t.validate(name,value)
def fields(value,names):t.obj(value,names.split())
def arr(value,check,minimum=0):
 t.array(value,check)
 if len(value)<minimum:fail('nonempty array required')
def num(value):return t.number(value)
def boolean(value):
 if type(value) is not bool:fail('boolean required')
def uid(value):
 if not isinstance(value,str) or re.fullmatch('[0-9a-f]{32}',value) is None:fail('UUID32 required')
def utc(value):
 if not isinstance(value,str) or re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z',value) is None:fail('UTC milliseconds required')
 try:datetime.strptime(value,'%Y-%m-%dT%H:%M:%S.%fZ')
 except ValueError:fail('invalid UTC time')
def json_value(value):t.fingerprint(value)
def known(value):return value['status']=='known'
def slot(value,check,allow_null=False):t.slot(value,check,allow_null=allow_null)
def refslot(value):slot(value,t.validate_ref)
def verslot(value):slot(value,lambda x:b('VersionToken',x))
def refs(value,minimum=0):arr(value,t.validate_ref,minimum)
def same_ref(a,c):return a['instance_id']==c['instance_id'] and a['id']==c['id'] and a['kind']==c['kind']
def header(value):
 if value['contract']!='TL-LOOP-0.1':fail('unsupported contract')
 t.integer(value['schema_revision'],1,1)
def check_axes(value):
 fields(value,'source_check locator_check support_check readiness')
 for name,states in [('source_check',('readable','temporarily_unavailable','revoked','deleted','unknown')),('locator_check',('not_checked','matched','unresolved','mismatch')),('support_check',('not_assessed','supports_scoped_claim','insufficient','conflicting','not_applicable')),('readiness',('not_checked','ready_for_handoff','needs_material','blocked','not_applicable'))]:t.validate_check(value[name],states=states)

def observation_extract(v):
 fields(v,'observations coverage empty_reason');arr(v['observations'],t.validate_claim);b('Coverage',v['coverage']);slot(v['empty_reason'],t.string)
 if not v['observations'] and not known(v['empty_reason']):fail('empty extraction needs a known reason')
def comparison(v):
 fields(v,'observation baseline comparable basis difference support counterevidence limitations');t.validate_ref(v['observation']);verslot(v['baseline']);slot(v['comparable'],boolean);refs(v['basis']);refs(v['support']);refs(v['counterevidence']);arr(v['limitations'],t.string)
 t.enum(v['difference'],('temporal_add','correction','restriction','confirmation','conflict','not_comparable','no_change','insufficient','new_object','new_property'))
 comparable=known(v['comparable']) and v['comparable']['value'] is True
 if v['difference'] in ('temporal_add','correction','restriction','confirmation','conflict') and not comparable:fail('difference requires comparable scopes')
 if v['difference']=='not_comparable' and comparable:fail('comparison contradicts difference')
def comparison_assessment(v):
 fields(v,'baselines comparison_coverage comparisons outcome');arr(v['baselines'],lambda x:b('VersionToken',x));b('Coverage',v['comparison_coverage']);arr(v['comparisons'],comparison);t.enum(v['outcome'],('proposal_supported','no_change','conflict','insufficient','blocked'))
def update_proposal(v):
 fields(v,'target operation claims rationale preserved_content unresolved_items atomic_group');target=v['target'];fields(target,'owner mode object expected content_kind')
 t.enum(target['owner'],('M03',));t.enum(target['mode'],('existing','new'));refslot(target['object']);verslot(target['expected']);t.enum(target['content_kind'],('source_report','world_claim','method_claim','causal_claim'))
 if target['mode']=='existing':
  if not known(target['object']) or not known(target['expected']) or not same_ref(target['object']['value'],target['expected']['value']['object']):fail('existing target baseline mismatch')
 elif target['object']['status']!='not_applicable' or target['expected']['status']!='not_applicable':fail('new target must not invent baseline')
 t.enum(v['operation'],('add','confirm','temporal_add','correct','restrict','mark_conflict'));arr(v['claims'],t.validate_claim,1);t.string(v['rationale']);refs(v['preserved_content']);arr(v['unresolved_items'],lambda x:slot(x,t.string));refslot(v['atomic_group'])
def effect_assessment(v):
 fields(v,'measurement_state measurement_ref baseline_ref candidate_ref method_refs metric_definition case_scope gain retention_components sample_counts independence usage');t.enum(v['measurement_state'],('not_measured','incomplete','measured','invalidated','not_applicable'))
 for name in ('measurement_ref','baseline_ref','candidate_ref'):refslot(v[name])
 refs(v['method_refs']);t.validate_ref(v['metric_definition']);t.validate_scope(v['case_scope']);slot(v['gain'],num)
 for name in ('retention_components','sample_counts','independence','usage'):slot(v[name],json_value,allow_null=True)
 if known(v['gain']) and (v['measurement_state']!='measured' or not known(v['measurement_ref'])):fail('known gain requires measured evidence reference')
 if v['measurement_state']=='measured' and (not known(v['measurement_ref']) or not known(v['gain'])):fail('measured effect needs known report and gain')
BODY={'ObservationExtract':observation_extract,'ComparisonAssessment':comparison_assessment,'UpdateProposal':update_proposal,'EffectAssessment':effect_assessment}
def product(v):
 fields(v,'contract schema_revision product_id instance_id producer work_ref purpose method created_at source_refs derivation_links limitations missing_items access_dependencies revision_links processing_identity downstream_refs checks product_type body');header(v);uid(v['product_id']);uid(v['instance_id']);b('Principal',v['producer']);t.validate_ref(v['work_ref']);t.enum(v['purpose'],PURPOSES);t.validate_method(v['method']);utc(v['created_at']);arr(v['source_refs'],lambda x:b('EvidenceRef',x));arr(v['derivation_links'],lambda x:b('Dependency',x));arr(v['limitations'],t.string);arr(v['missing_items'],lambda x:slot(x,t.string));arr(v['access_dependencies'],lambda x:b('Dependency',x));arr(v['revision_links'],refslot);b('Digest',v['processing_identity']);arr(v['downstream_refs'],refslot);check_axes(v['checks']);t.enum(v['product_type'],tuple(BODY));BODY[v['product_type']](v['body'])
 if v['producer']['module']!='M14':fail('learning product producer must be M14; identity still needs authorization')
 if v['producer']['purpose']!=v['purpose']:fail('product purpose mismatch')
def decision(v):
 fields(v,'id work_ref proposal_ref review_round actor policy_ref checks operation actual_scope content_ref revision_ref previous reason coverage handoff_refs created_at');uid(v['id']);t.validate_ref(v['work_ref']);t.validate_ref(v['proposal_ref']);t.integer(v['review_round']);b('Principal',v['actor']);t.validate_ref(v['policy_ref']);fields(v['checks'],'G01 G02 G03 G04 G05 G06 G07 G08')
 for check in v['checks'].values():t.validate_check(check,states=('pass','fail','incomplete','blocked','not_applicable'))
 t.enum(v['operation'],('accept','candidate','defer','reject','conflict','reuse'));t.validate_scope(v['actual_scope']);refslot(v['content_ref']);refslot(v['revision_ref']);verslot(v['previous']);t.enum(v['reason'],REASONS);b('Coverage',v['coverage']);refs(v['handoff_refs']);utc(v['created_at'])
 if v['actor']['module']!='M03':fail('decision actor must be M03; identity still needs authorization')
 if v['operation']=='accept' and (any(x['state']!='pass' for x in v['checks'].values()) or not known(v['content_ref']) or not known(v['revision_ref'])):fail('accept requires eight passes and content revision')
 if v['operation'] in ('candidate','defer','reject','conflict') and v['handoff_refs']:fail('non-accept cannot create representation obligations')
 if v['operation']=='reuse' and (not known(v['content_ref']) or not known(v['revision_ref'])):fail('reuse requires existing references')
def representation(v):
 fields(v,'id series_ref representation_no content_ref content_revision decision_ref format_version body_artifact body_digest claims source_refs scope limitations dependencies group published_at');uid(v['id']);t.validate_ref(v['series_ref']);t.integer(v['representation_no'],1);t.validate_ref(v['content_ref']);b('VersionToken',v['content_revision']);t.validate_ref(v['decision_ref']);t.enum(v['format_version'],('TL-TEXT-1',));t.validate_ref(v['body_artifact']);b('Digest',v['body_digest']);arr(v['claims'],t.validate_claim,1);arr(v['source_refs'],lambda x:b('EvidenceRef',x),1);t.validate_scope(v['scope']);arr(v['limitations'],t.string);arr(v['dependencies'],lambda x:b('Dependency',x));refslot(v['group']);utc(v['published_at'])
 if not same_ref(v['content_ref'],v['content_revision']['object']):fail('content revision belongs to different object')
def validate_envelope(v,operation=None):
 t.fingerprint(v)
 if operation=='recall':recall_request(v);return v
 fields(v,'contract schema_revision command_id instance_id principal work_ref idempotency_key expected control budget payload');header(v);uid(v['command_id']);uid(v['instance_id']);b('Principal',v['principal']);refslot(v['work_ref']);t.string(v['idempotency_key'])
 if len(v['idempotency_key'])>240:fail('idempotency key too long')
 verslot(v['expected']);b('Control',v['control']);b('Budget',v['budget']);json_value(v['payload'])
 if operation is not None:
  from digital_life.domain.tool_learning_operations import validate_payload
  validate_payload(operation,v['payload'])
  if operation=='admit_observation':
   if v['work_ref']['status']!='not_applicable':fail('admission cannot preallocate work')
  elif not known(v['work_ref']):fail('operation requires known work')
  if operation in ('resume_work','record_effect') and not same_ref(v['work_ref']['value'],v['payload']['work']):fail('payload differs from envelope work')
  if operation=='admit_observation' and v['principal']['purpose']!=v['payload']['purpose']:fail('admission purpose differs from envelope principal')
 return v

def response(v):
 fields(v,'command_id operation disposition owner result_refs current reason error_code coverage retry committed_at');uid(v['command_id']);t.enum(v['operation'],OPERATIONS);t.enum(v['disposition'],('applied','reused','deferred','rejected','blocked','stopped','failed'));t.enum(v['owner'],MODULES);refs(v['result_refs']);verslot(v['current']);t.enum(v['reason'],REASONS);t.enum(v['error_code'],ERRORS);b('Coverage',v['coverage']);fields(v['retry'],'allowed condition resume_work');boolean(v['retry']['allowed']);slot(v['retry']['condition'],t.string);refslot(v['retry']['resume_work']);slot(v['committed_at'],utc)
 if v['retry']['allowed'] and (not known(v['retry']['condition']) or not known(v['retry']['resume_work'])):fail('retry requires explicit condition and original work')
 if v['operation']!='recall' and v['disposition'] in ('applied','reused') and not known(v['committed_at']):fail('committed result needs commit timestamp')
 if v['error_code']=='COMMIT_UNKNOWN' and known(v['committed_at']):fail('unknown commit cannot assert time')

def recall_request(v):
 fields(v,'contract schema_revision request_id instance_id activity_ref context_ref principal entry query target_scope exact_refs version_mode as_of group_required allowed_kinds control budget index_fallback');header(v);uid(v['request_id']);uid(v['instance_id']);refslot(v['activity_ref']);refslot(v['context_ref']);b('Principal',v['principal']);t.enum(v['entry'],('execution','controller_audit'));t.string(v['query']);t.validate_scope(v['target_scope']);refs(v['exact_refs']);t.enum(v['version_mode'],('current','specified','as_of'));slot(v['as_of'],utc);boolean(v['group_required']);arr(v['allowed_kinds'],lambda x:t.enum(x,KINDS));b('Control',v['control']);b('Budget',v['budget']);t.enum(v['index_fallback'],('deny','bounded_primary'))
 if v['version_mode']=='specified' and not v['exact_refs']:fail('specified version needs references')
 if v['version_mode']=='as_of' and not known(v['as_of']):fail('as_of needs known time')
 if v['entry']=='controller_audit' and v['principal']['purpose'] not in ('history_audit','verify_source','evaluate'):fail('audit cannot execute learning')
 if v['principal']['purpose']=='recall_experience' and any(x!='accepted_content' for x in v['allowed_kinds']):fail('experience recall cannot request unaccepted data')
def recall_item(v):
 fields(v,'id kind memory_ref memory_revision representation_ref representation_revision content_ref content_revision decision_ref body body_digest origin_kind processing source_refs scope limitations value_slots usage_state group_ready relations selection control dependencies');uid(v['id']);t.enum(v['kind'],KINDS)
 for name in ('memory_ref','representation_ref','content_ref','decision_ref'):refslot(v[name])
 for name in ('memory_revision','representation_revision','content_revision'):verslot(v[name])
 t.string(v['body'],nonempty=False);b('Digest',v['body_digest']);t.enum(v['origin_kind'],('tool_result','user_statement','system_event','model_output'));t.enum(v['processing'],('raw','extract','transform','infer'));arr(v['source_refs'],lambda x:b('EvidenceRef',x));t.validate_scope(v['scope']);arr(v['limitations'],t.string);arr(v['value_slots'],lambda x:slot(x,json_value,allow_null=True));t.enum(v['usage_state'],('current','candidate','historical','conflicted','blocked'));slot(v['group_ready'],boolean);arr(v['relations'],lambda x:b('Dependency',x));fields(v['selection'],'method score reason');t.validate_method(v['selection']['method']);slot(v['selection']['score'],num);t.string(v['selection']['reason']);b('Control',v['control']);arr(v['dependencies'],lambda x:b('Dependency',x))
 for object_key,version_key in (('memory_ref','memory_revision'),('content_ref','content_revision')):
  if known(v[object_key]) and known(v[version_key]) and not same_ref(v[object_key]['value'],v[version_key]['value']['object']):fail('recall object/version mismatch')
 if v['kind']=='accepted_content':
  if not all(known(v[n]) for n in ('representation_ref','representation_revision','content_ref','content_revision','decision_ref')) or not v['source_refs']:fail('accepted content requires provenance and representation')
  if v['usage_state']=='current' and v['group_ready']['status']!='not_applicable' and (not known(v['group_ready']) or v['group_ready']['value'] is not True):fail('current accepted content requires ready group')
 if v['kind'] in ('candidate','history','shadow_statistic') and v['usage_state']=='current':fail('candidate/history/shadow cannot masquerade as current fact')
 if v['kind'] in ('episode','source_evidence') and (v['decision_ref']['status']!='not_applicable' or v['content_ref']['status']!='not_applicable' or v['content_revision']['status']!='not_applicable'):fail('raw source must not invent cognition acceptance')
def recall_result(v):
 fields(v,'request_id retrieval_run purpose method checked_at coverage completion empty_reason items gaps dependencies');uid(v['request_id']);refslot(v['retrieval_run']);t.enum(v['purpose'],PURPOSES);t.validate_method(v['method']);utc(v['checked_at']);b('Coverage',v['coverage']);t.enum(v['completion'],('complete','partial','not_ready','blocked','unavailable','stopped'));slot(v['empty_reason'],lambda x:t.enum(x,REASONS));arr(v['items'],recall_item);arr(v['gaps'],lambda x:slot(x,t.string));arr(v['dependencies'],lambda x:b('Dependency',x))
 if v['completion']=='complete' and not v['items'] and not known(v['empty_reason']):fail('empty completed search requires reason')
 if v['purpose']=='recall_experience' and any(x['kind']!='accepted_content' or x['usage_state']!='current' for x in v['items']):fail('experience result cannot contain unqualified items')
OPERATIONS=('admit_observation','assess_observation','decide_proposal','claim_representation','publish_representation','recall','apply_invalidation','acknowledge_propagation','resume_work','record_effect')
VALIDATORS={'Product':product,'ObservationExtract':observation_extract,'ComparisonAssessment':comparison_assessment,'UpdateProposal':update_proposal,'EffectAssessment':effect_assessment,'Comparison':comparison,'Decision':decision,'Representation':representation,'Envelope':validate_envelope,'Response':response,'RecallRequest':recall_request,'RecallResult':recall_result,'RecallItem':recall_item}
def validate(name,value):
 t.string(name)
 t.fingerprint(value)
 if name.endswith('.request') and name[:-8] in OPERATIONS:return validate_envelope(value,name[:-8])
 validator=VALIDATORS.get(name)
 if validator is None:return t.validate(name,value)
 validator(value);return value
def loads(raw,type_name=None):
 value=t.loads(raw)
 return validate(type_name,value) if type_name else value
