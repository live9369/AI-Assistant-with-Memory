"""Strict TL-EVAL-0.1 records. Structure is not authority or independent review."""
import re
from digital_life.domain import tool_learning_types as t
from digital_life.domain.contracts import ContractError

COMMON = ('contract','schema_revision','id','run_id','created_at')
FIELDS = {
 'Run':'protocol_ref code_digest configuration_ref prompt_refs model_ref route materials_manifest review_roster price_evidence currency money_limit account_limits mechanism_manifest arm_seed analysis_seed bootstrap_samples concurrency_limit deadline state budget_ref',
 'Case':'partition category source_cluster_id template_family learning_input_ref truth_ref base_snapshot_ref',
 'Query':'case_id query_kind input_ref truth_ref k',
 'Trial':'logical_trial_id case_id arm repeat occurrence replacement_of snapshot_ref instance_ref phase status assigned_order outcome_ref budget_ref',
 'Attempt':'trial_id logical_trial_id phase query_id request_ref reservation_ref actual_callback_entry receipt_ref outcome usage_ref',
 'Label':'query_id claim_id support expected_scope expected_slots relevant_refs expected_terminal major_error rationale evidence_refs author_id reviewer_id',
 'Review':'blind_item_id reviewer_id label_ref original_rating reason locator resolution_ref unblinding_risk',
 'Fault':'mechanism_case_id decision_refs metric_ids fixture_ref injection_stage planned_order_ref actual_trace_ref expected_terminal actual_terminal status',
 'Usage':'logical_trial_id attempt_ref reservation_ref input_tokens output_tokens tool_calls elapsed_ms currency_amount evidence_refs',
 'Metric':'metric_id metric_version partition arm case_id trial_id level numerator denominator samples_ref unit coverage method source_refs status interval judgment scope',
}
PARTITIONS = ('DEV','MECH','TARGET','RETENTION')
METRICS = tuple(f'TL{i:02}' for i in range(1,17))


def fail(msg): raise ContractError(msg)
def eval_id(v):
 t.string(v)
 if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',v): fail('EvalID must be 1..128 ASCII identifier characters')
 return v

def known(v): return v['status']=='known'
def nonnegative(v):
 t.number(v)
 if v<0:fail('negative measurement or limit')
 return v

def json_object(v):
 if type(v) is not dict:fail('explicit JSON object required')
 return t.json_value(v)

def interval(v):
 t.obj(v,('method','confidence','lower','upper','resamples','seed'))
 t.enum(v['method'],('paired_case_bootstrap','wilson'))
 if type(v['confidence']) not in (int,float) or v['confidence']!=0.95:fail('95 percent interval required')
 t.number(v['lower']);t.number(v['upper'])
 if v['lower']>v['upper']:fail('interval reversed')
 t.slot(v['resamples'],t.integer);t.slot(v['seed'],t.integer)
 if v['method']=='paired_case_bootstrap':
  if not known(v['resamples']) or v['resamples']['value']!=10000 or not known(v['seed']) or v['seed']['value']!=20261108:fail('fixed bootstrap protocol')
 else:
  if any(v[k]['status']!='not_applicable' for k in ('resamples','seed')):fail('Wilson has no resampling')
  if not 0<=v['lower']<=v['upper']<=1:fail('Wilson probability interval')
 return v


def same_run_refs(v,run):
 if type(v) is dict:
  if set(v)=={'instance_id','id','kind','revision'}:
   t.validate_ref(v);eval_id(v['id'])
   if v['instance_id']!=run:fail('cross-run evaluation reference')
  for x in v.values():same_run_refs(x,run)
 elif type(v) is list:
  for x in v:same_run_refs(x,run)


def validate_record(name,v):
 t.string(name)
 if name not in FIELDS:fail('unknown evaluation record type')
 t.json_value(v);t.obj(v,COMMON+tuple(FIELDS[name].split()))
 t.enum(v['contract'],('TL-EVAL-0.1',));t.integer(v['schema_revision'],1,1)
 eval_id(v['id']);eval_id(v['run_id']);t.utc(v['created_at'])
 same_run_refs(v,v['run_id'])
 ref=t.validate_ref;slot=t.slot
 if name=='Run':
  if v['id']!=v['run_id']:fail('Run id must equal run_id')
  for k in ('protocol_ref','configuration_ref','budget_ref'):ref(v[k])
  t.validate_digest(v['code_digest']);t.array(v['prompt_refs'],ref)
  for k in ('model_ref','materials_manifest','review_roster','price_evidence','mechanism_manifest'):slot(v[k],ref)
  for k in ('route','currency'):slot(v[k],t.string)
  slot(v['money_limit'],nonnegative);slot(v['account_limits'],json_object)
  for k,n in [('arm_seed',20261109),('analysis_seed',20261108),('bootstrap_samples',10000),('concurrency_limit',4)]:t.integer(v[k],n,n)
  t.utc(v['deadline'])
  if v['deadline']<=v['created_at']:fail('run deadline must follow registration')
  t.enum(v['state'],('blocked_before_start','registered','mechanism','dev','formal','stopped','completed','incomplete','failed'))
 elif name=='Case':
  t.enum(v['partition'],PARTITIONS);t.string(v['category']);eval_id(v['source_cluster_id']);slot(v['template_family'],t.string)
  for k in ('learning_input_ref','truth_ref','base_snapshot_ref'):ref(v[k])
 elif name=='Query':
  eval_id(v['case_id']);t.enum(v['query_kind'],('same_observation','new_question','boundary','retention'))
  ref(v['input_ref']);ref(v['truth_ref']);t.integer(v['k'],5,5)
 elif name=='Trial':
  for k in ('logical_trial_id','case_id'):eval_id(v[k])
  t.enum(v['arm'],('E','N','O'));t.integer(v['repeat'],1,3);t.enum(v['occurrence'],('original','replacement'))
  slot(v['replacement_of'],ref)
  if v['occurrence']=='original' and v['replacement_of']['status']!='not_applicable':fail('original cannot replace a trial')
  if v['occurrence']=='original' and v['logical_trial_id']!=v['id']:fail('original logical trial id is its allocation id')
  if v['occurrence']=='replacement' and not known(v['replacement_of']):fail('replacement requires original reference')
  for k in ('snapshot_ref','instance_ref','budget_ref'):ref(v[k])
  t.enum(v['phase'],('registered','learning','querying','finished'))
  t.enum(v['status'],('registered','running','completed','failed','stopped','not_run','infrastructure_invalid','incomplete'))
  t.integer(v['assigned_order']);slot(v['outcome_ref'],ref)
  if v['status']=='completed' and (v['phase']!='finished' or not known(v['outcome_ref'])):fail('completed trial requires finished durable outcome')
 elif name=='Attempt':
  eval_id(v['trial_id']);eval_id(v['logical_trial_id']);t.enum(v['phase'],('learn','query'))
  slot(v['query_id'],eval_id)
  if v['phase']=='learn' and v['query_id']['status']!='not_applicable':fail('learn query not applicable')
  if v['phase']=='query' and not known(v['query_id']):fail('query attempt requires query id')
  for k in ('request_ref','reservation_ref'):ref(v[k])
  slot(v['actual_callback_entry'],t.utc)
  for k in ('receipt_ref','usage_ref'):slot(v[k],ref)
  t.enum(v['outcome'],('prepared','in_flight','received','failed','unknown','stopped'))
  if v['outcome']=='prepared' and known(v['actual_callback_entry']):fail('prepared is not actual callback entry')
  if v['outcome'] in ('in_flight','received') and not known(v['actual_callback_entry']):fail('actual callback required, sent is insufficient')
  if v['outcome']=='received' and not known(v['receipt_ref']):fail('received needs receipt')
 elif name=='Label':
  for k in ('query_id','claim_id','author_id','reviewer_id'):eval_id(v[k])
  if v['author_id']==v['reviewer_id']:fail('same identity cannot be independent author and reviewer')
  t.enum(v['support'],('supported','unsupported','conflicting','unknown'));t.validate_scope(v['expected_scope'])
  t.array(v['expected_slots'],lambda x:slot(x,json_object));t.array(v['relevant_refs'],ref)
  t.string(v['expected_terminal']);t.boolean(v['major_error']);t.string(v['rationale']);t.array(v['evidence_refs'],t.validate_evidence)
 elif name=='Review':
  eval_id(v['blind_item_id']);eval_id(v['reviewer_id']);ref(v['label_ref'])
  t.enum(v['original_rating'],('pass','fail','not_evaluable'));t.string(v['reason']);t.validate_locator(v['locator'])
  slot(v['resolution_ref'],ref);slot(v['unblinding_risk'],t.string)
 elif name=='Fault':
  eval_id(v['mechanism_case_id']);t.array(v['decision_refs'],t.string);t.array(v['metric_ids'],lambda x:t.enum(x,METRICS))
  if not v['decision_refs'] or not v['metric_ids']:fail('fault must retain adjudication and metric mapping')
  for k in ('fixture_ref','planned_order_ref'):ref(v[k])
  t.string(v['injection_stage']);slot(v['actual_trace_ref'],ref);t.string(v['expected_terminal']);slot(v['actual_terminal'],t.string)
  t.enum(v['status'],('planned','running','completed','not_run','failed'))
  if v['status']=='completed' and not all(known(v[k]) for k in ('actual_trace_ref','actual_terminal')):fail('fault completion requires actual evidence')
  if v['status'] in ('planned','not_run') and any(known(v[k]) for k in ('actual_trace_ref','actual_terminal')):fail('unrun fault has no actual trace')
 elif name=='Usage':
  eval_id(v['logical_trial_id']);slot(v['attempt_ref'],ref);ref(v['reservation_ref'])
  for k in ('input_tokens','output_tokens','tool_calls'):slot(v[k],t.integer)
  for k in ('elapsed_ms','currency_amount'):slot(v[k],nonnegative)
  t.array(v['evidence_refs'],ref)
 elif name=='Metric':
  t.enum(v['metric_id'],METRICS);t.string(v['metric_version']);t.enum(v['partition'],PARTITIONS);t.enum(v['arm'],('E','N','O','paired'))
  for k in ('case_id','trial_id'):slot(v[k],eval_id)
  t.enum(v['level'],('claim','work','query','trial','case','partition','run'))
  for k in ('numerator','denominator'):slot(v[k],t.integer)
  slot(v['samples_ref'],ref);t.string(v['unit']);t.validate_coverage(v['coverage']);t.validate_method(v['method']);t.array(v['source_refs'],ref)
  t.enum(v['status'],('not_run','missing','not_applicable','insufficient_sample','not_evaluable','measured'))
  slot(v['interval'],interval);t.enum(v['judgment'],('pass','fail','incomplete','not_evaluable','exploratory'));t.validate_scope(v['scope'])
  n,d=v['numerator'],v['denominator']
  if known(n)!=known(d):fail('rate numerator and denominator must both be known')
  if known(n):
   if n['value']>d['value']:fail('numerator exceeds denominator')
   if d['value']==0 and (v['status']!='not_applicable' or v['judgment']=='pass'):fail('zero denominator is not applicable, never pass')
  elif v['status']=='measured' and not known(v['samples_ref']):fail('continuous measurement needs samples')
  if v['judgment']=='pass' and v['status']!='measured':fail('missing or unrun metric cannot pass')
 return v


def loads(raw,type_name):return validate_record(type_name,t.loads(raw))
