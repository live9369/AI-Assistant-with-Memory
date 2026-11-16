"""Explicit source-owner whitelist for immutable M17 observation bridges."""
from digital_life.domain import tool_learning_types as t

SNAPSHOT_KINDS=frozenset('perception_channels jobs budget_reservations value_conflicts commitment_conflicts activity_budget_accounts policy_epochs world_entities activities identity_instances personality_dimensions value_dimensions state_definitions personality_change_records value_change_records habit_cues habit_activations habit_learning_records social_relationship_dimensions social_relationship_changes learning_feedback learning_attributions goal_relations goal_evaluations goal_activation_records health_requirements health_observations health_assessments health_incidents maintenance_plans cognition_assessments cognition_episodes personality_trait_values personality_states personality_context_effects value_weights value_activations goal_items motivation_states habit_items habit_associations habit_opportunities social_actors social_relationships social_relationship_values social_trust_assessments social_expectations commitment_items state_observations cognition_hypotheses cognition_predictions cognition_plans cognition_plan_steps cognition_attention_allocations'.split())


CAS_FIELDS={'jobs':'lease_generation','activity_budget_accounts':'revision','policy_epochs':'epoch','activities':'revision','goal_items':'state_revision','commitment_items':'state_revision','cognition_plans':'version'}

# Operational secrets and source hashes are not needed to compute queue depth,
# pressure or reservation counts. They are not copied into observation bodies.
OPERATIONAL_SELECTORS={
    'jobs':frozenset(('id','kind','target_ref','state','due_at','attempt','lease_generation')),
    'activities':frozenset(('id','trigger_event_id','state','deadline','revision','input_epoch','cancel_requested_at','publication_state','release_id')),
    'budget_reservations':frozenset(('id','activity_id','operation_kind','reserved_tokens','reserved_tool_calls','reserved_attempts','state','reserved_at','settled_at')),
}

def validate_snapshot(value):
    t.obj(value,('contract','origin','selector','digest','value','observed_at','native_revision','snapshot_revision','scope'))
    if value['contract']!='TL-SOURCE-SNAPSHOT-1':raise t.ContractError('unsupported source snapshot')
    t.validate_ref(value['origin'])
    if value['origin']['kind'] not in SNAPSHOT_KINDS or value['origin']['revision']['status']!='not_applicable':raise t.ContractError('snapshot origin is not an eligible unversioned owner')
    t.array(value['selector'],t.string)
    if not value['selector'] or sorted(set(value['selector']))!=value['selector']:raise t.ContractError('canonical unique source field selector required')
    t.validate_digest(value['digest']);t.json_value(value['value']);t.utc(value['observed_at']);t.integer(value['snapshot_revision'],1);t.validate_scope(value['scope'])
    t.slot(value['native_revision'],t.integer)
    expected_status='known' if value['origin']['kind'] in CAS_FIELDS else 'not_applicable'
    if value['native_revision']['status']!=expected_status:raise t.ContractError('snapshot native CAS presence differs from the actual owner kind')
    if type(value['value']) is not dict or sorted(value['value'])!=value['selector'] or value['digest']['hex']!=t.fingerprint(value['value']):raise t.ContractError('snapshot selector/digest/value mismatch')
    return value
