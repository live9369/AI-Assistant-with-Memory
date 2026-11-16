"""Explicit versioned model routing; never mutates an existing thought request."""
from digital_life.domain.contracts import Forbidden,ContractError,utc,sha,dumps,identifier
from digital_life.infrastructure.llm.inference import configured_reasoner,probe

def validate_model_config(config):
    if not isinstance(config,dict): raise ContractError('model configuration must be an object')
    allowed={'backend','model','base_url','timeout','max_output_tokens','temperature','context_window'}
    if config.get('backend')=='remote_chat':
        from digital_life.infrastructure.llm.remote_chat import REMOTE_FIELDS
        allowed=REMOTE_FIELDS
    if config.get('backend')=='codex_cli':
        from digital_life.infrastructure.llm.codex_cli import CODEX_FIELDS
        allowed=CODEX_FIELDS
    if set(config)-allowed: raise ContractError('unknown model configuration fields; literal credentials are forbidden')
    return configured_reasoner(config)

def configure_model(store,config,actor,check_available=True):
    if actor!=store.config()['controller']: raise Forbidden('controller required')
    validate_model_config(config)
    if config.get('backend')=='codex_cli':
        from digital_life.infrastructure.llm.codex_cli import normalize_codex_config
        config=normalize_codex_config(config)
    from digital_life.application.lifecycle.control_plane import Control
    control=Control(store.root,store.instance_id)
    try:
        state=control.state()
        if not state['user_stopped'] or state['active_process_run_id']: raise Forbidden('stop runtime before changing model routing')
    finally: control.close()
    availability=probe(config) if check_available else {'available':None,'reason':'explicit-offline-configuration'}
    with store.tx():
        previous=store.config(); updated=dict(previous,model=dict(config))
        artifact=store.artifact(updated); digest=store.row('artifacts',artifact)['hash']
        number=len(store.rows('configuration_versions'))
        from digital_life.application.learning.runtime import qualified_plane_required
        strict=qualified_plane_required(store)
        model_id=identifier()
        compatibility={'schema_min':2,'schema_max':4 if strict else 3}
        if strict:compatibility['model_version_id']=model_id
        version=store.insert('configuration_versions',version='model-config-'+str(number),artifact_ref=artifact,hash=digest,compatibility=compatibility)
        model=store.insert('model_versions',id=model_id,version=config['backend']+':'+config['model'],artifact_ref=artifact,hash=digest,compatibility={'fresh_request':True,'strict_packet_contracts':['TL-ENGINE-THOUGHT-1','TL-OBSERVATION-THOUGHT-1']} if strict else {'fresh_request':True})
        store.event('model.configured',payload={'configuration':version,'model_version':model,'availability':availability,'existing_requests_rewritten':False},lane='control')
    return {'configuration':version,'model_version':model,'availability':availability,'inference_executed':False}
