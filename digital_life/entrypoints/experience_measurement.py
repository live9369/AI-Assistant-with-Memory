"""Explicit controller operations for sealed prediction measurement. Never wakes."""
import json
from pathlib import Path
from digital_life.domain.contracts import ContractError
from digital_life.application.learning.experience_measurement import ExperienceMeasurement

def required(value,name):
    if not value:raise ContractError('required '+name)
    return value

def handle(store,args):
    m=ExperienceMeasurement(store);actor=store.config()['controller'];op=args.operation
    if op=='status':return m.status(actor)
    if op in ('enable','disable'):
        from digital_life.entrypoints.growth import check_running_feature
        check_running_feature(store,'experience_measurement.py')
        m.configure(op=='enable',actor);return m.status(actor)
    if op=='register':
        data=json.loads(Path(required(args.input,'--input')).read_text())
        keys={'opportunity_ref','cases','classes','label_commitment','common_context','training_case_ids','tokens_per_call','wall_seconds'}
        if not isinstance(data,dict) or set(data)-keys or not {'opportunity_ref','cases','classes','label_commitment'}<=set(data):raise ContractError('invalid measurement registration fields')
        return {'run_ref':m.register(actor=actor,**data),'inference_started':False}
    if op=='predict':
        from digital_life.infrastructure.llm.inference import configured_reasoner
        from digital_life.infrastructure.llm.experience_prediction import ExperiencePredictionPort
        config=json.loads(Path(required(args.config,'--config')).read_text())
        port=ExperiencePredictionPort(configured_reasoner(config))
        return m.run_predictions(required(args.run,'--run'),port,actor)
    if op=='reveal':
        data=json.loads(Path(required(args.input,'--input')).read_text())
        if not isinstance(data,dict) or set(data)!={'labels','nonce'}:raise ContractError('label file needs labels and nonce')
        return {'labels_ref':m.reveal_labels(required(args.run,'--run'),data['labels'],data['nonce'],actor),'inference_started':False}
    if op=='evaluate':return {'report_ref':m.evaluate(required(args.run,'--run'),actor),'inference_started':False}
    if op=='adopt':return {'experience_revision_ref':m.adopt_shadow(required(args.report,'--report'),actor),'inference_started':False}
    if op=='invalidate':return {'invalidation_ref':m.invalidate(required(args.run,'--run'),required(args.reason,'--reason'),actor),'inference_started':False}
    raise ContractError('unknown measurement operation')
