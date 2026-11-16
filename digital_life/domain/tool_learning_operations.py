"""Closed payloads for the ten frozen TL operations; no execution or authority."""
from digital_life.domain import tool_learning_types as t
from digital_life.domain.tool_learning_products import fields,refs,slot,refslot,verslot,known,uid,arr,b,PURPOSES,MODULES,fail,same_ref,representation,effect_assessment,recall_request

def validate_payload(operation,v):
 t.string(operation);t.fingerprint(v)
 if operation=='admit_observation':
  fields(v,'source purpose source_activity processing_method previous_work');b('EvidenceRef',v['source']);t.enum(v['purpose'],('learn','evaluate'));t.validate_ref(v['source_activity']);t.validate_method(v['processing_method']);refslot(v['previous_work'])
 elif operation=='assess_observation':
  fields(v,'source baseline_refs baseline_coverage method');b('EvidenceRef',v['source']);arr(v['baseline_refs'],lambda x:b('VersionToken',x));b('Coverage',v['baseline_coverage']);t.validate_method(v['method'])
 elif operation=='decide_proposal':
  fields(v,'proposal review_round policy review atomic_group');t.validate_ref(v['proposal']);t.integer(v['review_round']);t.validate_ref(v['policy']);refslot(v['review']);refslot(v['atomic_group'])
 elif operation=='claim_representation':
  fields(v,'handoff expected_generation worker lease_seconds');t.validate_ref(v['handoff']);t.integer(v['expected_generation']);t.validate_ref(v['worker']);t.integer(v['lease_seconds'],1,300)
 elif operation=='publish_representation':
  fields(v,'handoff lease_generation worker representation');t.validate_ref(v['handoff']);t.integer(v['lease_generation']);t.validate_ref(v['worker']);representation(v['representation'])
 elif operation=='recall':recall_request(v)
 elif operation=='apply_invalidation':
  fields(v,'change_id kind source replacement affected_scope subjects purposes expected_epoch evidence erase_scope');uid(v['change_id']);t.enum(v['kind'],('correct','revoke','erase','conflict','unavailable'));b('VersionToken',v['source']);verslot(v['replacement']);t.validate_scope(v['affected_scope']);refs(v['subjects']);arr(v['purposes'],lambda x:t.enum(x,PURPOSES));t.integer(v['expected_epoch']);arr(v['evidence'],lambda x:b('EvidenceRef',x));refslot(v['erase_scope'])
  if v['source']['epoch']!=v['expected_epoch']:fail('source epoch differs from expected epoch')
  if v['kind']=='erase' and not known(v['erase_scope']):fail('erasure requires known authorized scope reference')
 elif operation=='acknowledge_propagation':
  fields(v,'barrier generation domain targets coverage actions verification');t.validate_ref(v['barrier']);t.integer(v['generation']);t.enum(v['domain'],MODULES);refs(v['targets']);b('Coverage',v['coverage']);refs(v['actions']);t.validate_ref(v['verification'])
 elif operation=='resume_work':
  fields(v,'work expected_work_revision conditions reconciliation');t.validate_ref(v['work']);t.integer(v['expected_work_revision']);refs(v['conditions']);t.validate_ref(v['reconciliation'])
 elif operation=='record_effect':
  fields(v,'work measurement assessment');t.validate_ref(v['work']);refslot(v['measurement']);effect_assessment(v['assessment'])
  inner=v['assessment']['measurement_ref']
  if known(v['measurement'])!=known(inner) or known(inner) and not same_ref(v['measurement']['value'],inner['value']):fail('measurement reference mismatch')
 else:fail('unsupported operation')
 return v
