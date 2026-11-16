#!/usr/bin/env python3
"""Explicit, bounded real-Codex pilot; frozen source and persistent audit only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def guard(formal):
    formal=Path(formal)
    if formal.is_symlink() or not (formal/'WAKE_DISABLED').is_file():raise RuntimeError('formal lock missing')
    return {str(p.relative_to(formal)):digest(p) for p in sorted(formal.rglob('*')) if p.is_file()}

def worker(directory):
    from evaluation.exploration.harness import Harness
    from evaluation.experience_codex_pilot import CASES,CONTEXT,private_labels
    from digital_life.application.learning.self_feedback import SelfFeedback
    from digital_life.application.learning.experience_measurement import ExperienceMeasurement
    from digital_life.application.services.cognition import Cognition
    from digital_life.infrastructure.llm.inference import configured_reasoner
    from digital_life.infrastructure.llm.experience_prediction import ExperiencePredictionPort
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text())
    assert digest(directory/'manifest.json')==(directory/'manifest.sha256').read_text().strip()
    for name,h in manifest['source_hashes'].items():assert digest(ROOT/name)==h,name
    case=next(c for c in json.loads((ROOT/'evaluation/exploration/materials/cases-v1.json').read_text())['cases'] if c['case_id']=='B01')
    h=None;out={'status':'incomplete','real_model_attempts':0,'real_model_completed':0,'actual_selection_changed':False}
    evidence=directory/'evidence';evidence.mkdir()
    calls=[]
    try:
        h=Harness(directory/'isolated-instance',case,trace_path=evidence/'live-trace.jsonl')
        actor=h.s.config()['controller'];sf=SelfFeedback(h.s);sf.configure(actor,True)
        measure=ExperienceMeasurement(h.s);measure.configure(True,actor)
        activity=h.investigation()
        # Explicit fixture-only budget profile, fixed before observation and all
        # real calls. This is never applied to an existing/formal instance.
        with h.s.tx():
            h.s.db.execute('UPDATE activity_budget_accounts SET token_limit=?,attempt_limit=? WHERE activity_id=?',(manifest['parent_token_limit'],12,activity))
        h.finish(activity)
        opportunity=sf._events('opportunity')[0]['payload']['opportunity_ref']
        snapshot=Cognition(h.s).experience_snapshot(actor)
        write(evidence/'experience-before.json',snapshot)
        value=json.loads((h.root/'workspace/notes/reading.json').read_text())['value']
        labels=private_labels(value);nonce=secrets.token_hex(32)
        write(evidence/'controller-private-labels.json',{'labels':labels,'nonce':nonce,'observation_value':value,'label_authority':'controller checks receipt against authored B01; no independent review'})
        run=measure.register(opportunity,CASES,2,measure.commitment(labels,nonce),actor,common_context=CONTEXT,
                             training_case_ids=['B01-observation'],tokens_per_call=manifest['tokens_per_call'],wall_seconds=300)
        out.update(run_ref=run,opportunity_ref=opportunity)
        reasoner=configured_reasoner(manifest['model_config']);port=ExperiencePredictionPort(reasoner)
        original_generate=reasoner.generate
        def recorded_generate(payload):
            calls[-1]['model_payload']=payload
            write(evidence/'model-calls.json',calls)
            output=original_generate(payload)
            calls[-1]['model_output']=output
            return output
        reasoner.generate=recorded_generate
        class RecordingPort:
            name=port.name
            def predict(self,request):
                call={'ordinal':len(calls)+1,'request':request,'state':'sent','started_utc':datetime.now(timezone.utc).isoformat()}
                calls.append(call);out['real_model_attempts']+=1
                write(evidence/'model-calls.json',calls)
                start=time.monotonic()
                try:
                    response=port.predict(request)
                    call.update(state='completed',response=response,session_id=reasoner.last_session_id,usage=reasoner.last_usage)
                    out['real_model_completed']+=1
                    return response
                except BaseException as error:
                    call.update(state='failed',error_type=type(error).__name__,error=str(error));raise
                finally:
                    call['elapsed_seconds']=time.monotonic()-start
                    write(evidence/'model-calls.json',calls)
                    print('model call',call['ordinal'],call['state'],round(call['elapsed_seconds'],2),flush=True)
        out['prediction_state']=measure.run_predictions(run,RecordingPort(),actor)
        if out['prediction_state']['state']!='predictions_sealed':raise RuntimeError('prediction batch stopped: '+str(out['prediction_state']))
        measure.reveal_labels(run,labels,nonce,actor)
        report_ref=measure.evaluate(run,actor);report=measure.checked_report(report_ref)
        out.update(status='measured',report_ref=report_ref,measurement=report)
        out['shadow_revision_ref']=measure.adopt_shadow(report_ref,actor)
        write(evidence/'experience-after.json',Cognition(h.s).experience_snapshot(actor))
        sessions=[c['session_id'] for c in calls]
        assert len(sessions)==len(set(sessions))==8,'independent sessions required'
        assert len(h.s.rows('thought_requests'))==3,'measurement changed actor calls'
        assert not Cognition(h.s).experience_snapshot(actor)['affects_selection']
        assert all(nonce not in json.dumps(c['request']) for c in calls)
        out['independent_sessions']=True
        out['sqlite_integrity']=h.s.integrity()
    except BaseException:
        out.update(status='failed-or-incomplete',error=traceback.format_exc())
    finally:
        if h:
            # End every isolated branch locked/stopped, including provider failure.
            try:
                h.c.stop('experience-codex-pilot-finished')
                (h.root/'WAKE_DISABLED').touch(exist_ok=True)
                out['isolated_end_locked']=True
                out['audit']=h.export(evidence)
            except BaseException:out['close_error']=traceback.format_exc()
            finally:h.close()
        out['known_actual_tokens']=sum((c.get('usage') or {}).get('input_tokens',0)+(c.get('usage') or {}).get('output_tokens',0) for c in calls if c['state']=='completed')
        out['evidence_hashes']={str(p.relative_to(evidence)):digest(p) for p in evidence.rglob('*') if p.is_file()}
        write(directory/'result.json',out)
    return 0 if out['status']=='measured' else 1

def run(config_path,output):
    from evaluation.experience_codex_pilot import PROTOCOL,CASES,CONTEXT
    formal=ROOT/'work/primordial00';before=guard(formal)
    config=json.loads(Path(config_path).read_text())
    if config.get('backend')!='codex_cli' or config.get('enabled') is not True:raise ValueError('explicit enabled Codex configuration required')
    output=Path(output).resolve()
    if output==ROOT or output==ROOT/'work' or ROOT/'work' in output.parents:raise ValueError('output must not be an instance directory')
    directory=output/('experience-codex-pilot-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4))
    directory.mkdir(parents=True,exist_ok=False)
    sources=[p for p in (ROOT/'digital_life').rglob('*') if p.is_file() and p.suffix in ('.py','.sql','.json')]
    sources+=list((ROOT/'evaluation/exploration').glob('*.py'))+[ROOT/'evaluation/exploration/materials/cases-v1.json',ROOT/'evaluation/experience_codex_pilot.py',Path(__file__).resolve()]
    hashes={}
    for p in sources:
        name=str(p.relative_to(ROOT));target=directory/'source-snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes());hashes[name]=digest(p)
    manifest={'protocol':PROTOCOL,'source_hashes':hashes,'model_config':config,'formal_before':before,
              'tokens_per_call':32768,'parent_token_limit':300000,'maximum_real_calls':8,'cases':CASES,'common_context':CONTEXT,
              'decision_rule':'Descriptive paired Brier only. No significance or general learning claim; target gain alone does not override retention regression.',
              'experience_source':'Unmodified Cognition.experience_snapshot after one synthetic local observation. No injected factual experience.',
              'limitations':['Single repeat per case, fixed model alias not immutable provider revision','Target truth derives from authored observation; no independent reviewer','Current snapshot has statistics and references, not observation content','Provider tokens checked after return; no hard total token guarantee'],
              'actual_selection_changed':False,'retry_policy':'none; preserve failed or partial run'}
    write(directory/'manifest.json',manifest);(directory/'manifest.sha256').write_text(digest(directory/'manifest.json')+'\n')
    print(directory,flush=True)
    try:
        with (directory/'worker.stdout').open('w') as out,(directory/'worker.stderr').open('w') as err:
            child=subprocess.run([sys.executable,str(directory/'source-snapshot/scripts/development/run_experience_codex_pilot.py'),'--worker',str(directory)],cwd=directory/'source-snapshot',stdout=out,stderr=err,timeout=420)
            exit_code=child.returncode
    except subprocess.TimeoutExpired:exit_code=124
    finally:
        after=guard(formal)
        result=json.loads((directory/'result.json').read_text()) if (directory/'result.json').exists() else {'status':'missing-result'}
        write(directory/'aggregate.json',{'protocol':PROTOCOL,'run_id':directory.name,'exit_code':locals().get('exit_code'),
              'status':result['status'],'formal_unchanged':before==after,'formal_after':after,'result_sha256':digest(directory/'result.json') if (directory/'result.json').exists() else None,
              'actual_selection_changed':False,'real_model_completed':result.get('real_model_completed'),
              'scope':'Small diagnostic pilot of the current statistical snapshot; not formal G2 or proof of learning'})
        index={str(p.relative_to(directory)):digest(p) for p in directory.rglob('*') if p.is_file() and 'isolated-instance' not in p.relative_to(directory).parts}
        write(directory/'evidence-index.json',index);(directory/'evidence-index.sha256').write_text(digest(directory/'evidence-index.json')+'\n')
    return exit_code if before==after else 2

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config');parser.add_argument('--output',default=str(ROOT/'outputs/acceptance/experience-codex-pilot'));parser.add_argument('--worker')
    args=parser.parse_args()
    if not args.worker and not args.config:parser.error('--config required for explicit real-model execution')
    raise SystemExit(worker(args.worker) if args.worker else run(args.config,args.output))
