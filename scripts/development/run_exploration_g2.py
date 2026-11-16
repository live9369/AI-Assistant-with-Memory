#!/usr/bin/env python3
"""Bounded real G2 pilot or full-group registration. Never accepts an instance path."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import uuid
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))

def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def check_prior(version='v1.1'):
    checker=load_module('aecheck',ROOT/('scripts/verify_exploration_contract_'+version.replace('.','_')+'.py'));workspace=checker.verify()
    pointer=json.loads((ROOT/('outputs/acceptance/autonomous-exploration-g1-'+version+'-latest.json')).read_text())
    source_run=ROOT/pointer['run_directory'];aggregate=source_run/'aggregate.json'
    if digest(aggregate)!=pointer['aggregate_sha256'] or pointer['gates']['G1']!='pass':raise ValueError('G1 pass evidence invalid')
    runtime_manifest=json.loads((source_run/'manifest.json').read_text());baseline=json.loads((source_run/'baseline.json').read_text())
    if digest(source_run/'baseline.json')!=runtime_manifest['baseline_sha256']:raise ValueError('Archived G1 baseline changed')
    for relative,expected in baseline['frozen_files'].items():
        source=source_run/'source-snapshot'/relative if relative.startswith('digital_life/') else ROOT/relative
        if digest(source)!=expected:raise ValueError('Validated runtime or non-runtime baseline changed: '+relative)
    for relative,expected in runtime_manifest['runtime_dependency_hashes'].items():
        if digest(source_run/'source-snapshot'/relative)!=expected:raise ValueError('G1 runtime archive changed: '+relative)
    g0=dict(workspace,successful=True,errors=[],evaluated_runtime='G1-validated complete runtime archive',workspace_g0=workspace)
    return g0,pointer,source_run,runtime_manifest['runtime_dependency_hashes']

def worker(manifest_file,trial_id):
    manifest_file=Path(manifest_file).resolve();run=manifest_file.parent
    if digest(manifest_file)!=(run/'manifest.sha256').read_text().strip():raise ValueError('Manifest changed')
    manifest=json.loads(manifest_file.read_text());spec=next(t for t in manifest['trials'] if t['trial_id']==trial_id)
    for relative,expected in manifest['source_hashes'].items():
        source=run/'validated-runtime'/relative if relative.startswith('digital_life/') else ROOT/relative
        if digest(source)!=expected:raise ValueError('Source changed during run: '+relative)
    sys.path.insert(0,str(run/'validated-runtime'))
    from evaluation.exploration.g2.runtime import RealTrial
    if digest(run/'actor-config.json')!=manifest['actor_config_sha256']:raise ValueError('Actor configuration changed')
    if digest(run/'public.json')!=manifest['public_sha256']:raise ValueError('Public materials changed')
    public=json.loads((run/'public.json').read_text());case=next(c for c in public['cases'] if c['case_id']==spec['case_id'])
    config=json.loads((run/'actor-config.json').read_text());directory=run/'trials'/trial_id;directory.mkdir(parents=True,exist_ok=False)
    env=None;summary=None;error=None
    def timeout(*_):raise TimeoutError('G2 worker watchdog')
    signal.signal(signal.SIGTERM,timeout)
    with tempfile.TemporaryDirectory(prefix='ae-g2-real-') as tmp:
        try:
            env=RealTrial(Path(tmp)/'instance',case,config,manifest['trial_limits'],directory)
            summary=env.run()
        except BaseException as exc:error={'type':type(exc).__name__,'message':str(exc)}
        finally:
            if env:
                try:env.close()
                except BaseException as exc:error=error or {'type':type(exc).__name__,'message':'Cleanup: '+str(exc)}
    evidence={name:digest(directory/name) for name in ('snapshot.json','artifacts.json','trace.json','live-trace.jsonl') if (directory/name).is_file()}
    result={'trial_id':trial_id,'case_id':case['case_id'],'stratum':case['stratum'],'arm':'full','repeat':spec['repeat'],
      'status':'completed' if error is None and summary and not summary['errors'] else 'failed','error':error,'summary':summary,'evidence_hashes':evidence,
      'real_model_used':True,'oracle_exposed_to_actor':False,'actor_model':config['model']}
    write(directory/'result.json',result)
    return 0 if result['status']=='completed' else 1

def run(args):
    from digital_life.application.runtime.configuration import validate_model_config
    g1=load_module('g1utilities',ROOT/'scripts/development/run_exploration_g1.py')
    before=g1.formal_guard();g0,prior,source_run,runtime_hashes=check_prior(args.baseline)
    config=json.loads(Path(args.config).read_text());validate_model_config(config)
    if config['backend'] not in ('codex_cli','ollama','llamacpp'):raise ValueError('G2 runner permits subscription CLI or local model only; no paid remote API fallback')
    config.setdefault('timeout',120)
    if config.get('enabled',True) is not True:raise ValueError('Configured actor is disabled')
    split='development' if args.mode=='pilot' else 'formal-candidate'
    source=ROOT/'evaluation/exploration/g2/materials'
    public=json.loads((source/(split+'-public.json')).read_text());oracle=json.loads((source/(split+'-oracle.json')).read_text())
    run_id='g2-'+args.mode+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    output=Path(args.output).resolve()
    if output==ROOT or output==ROOT/'work' or ROOT/'work' in output.parents:raise ValueError('Output must not be an instance directory')
    directory=output/run_id;directory.mkdir(parents=True,exist_ok=False)
    repeats=1 if args.mode=='pilot' else 3
    limits={'activities':3 if args.mode=='pilot' else 12,'model_calls':6 if args.mode=='pilot' else 36,
      'wall_seconds':300 if args.mode=='pilot' else 900,'observed_tokens':1000000}
    trials=[{'trial_id':'trial-'+uuid.uuid4().hex[:12],'case_id':c['case_id'],'stratum':c['stratum'],'arm':'full','repeat':repeat} for c in public['cases'] for repeat in range(1,repeats+1)]
    source_files = [p for p in (ROOT/'evaluation/exploration/g2').rglob('*') if p.is_file() and p.suffix in ('.py','.json')]
    source_files += [Path(__file__).resolve(),ROOT/'scripts/development/review_exploration_g2.py',ROOT/'scripts/development/aggregate_exploration_g2.py',ROOT/('docs/architecture/autonomous-exploration-baseline-'+args.baseline+'.json'),ROOT/'docs/research/autonomous-exploration-evaluation-v1.md',ROOT/'docs/research/autonomous-exploration-metrics-v1.md',ROOT/'docs/research/autonomous-exploration-g2-review-rubric.md']
    hashes={str(p.relative_to(ROOT)):digest(p) for p in source_files}
    for relative,expected in runtime_hashes.items():
        source=source_run/'source-snapshot'/relative
        target=directory/'validated-runtime'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
        hashes[relative]=expected
    write(directory/'public.json',public);write(directory/'oracle.json',oracle);write(directory/'actor-config.json',config)
    manifest={'run_id':run_id,'protocol_id':'AE-EVAL-1.0','metrics_protocol':'AE-METRICS-1.0','runtime_protocol':'AE-RUNTIME-'+args.baseline[1:],
      'runtime_baseline_sha256':digest(ROOT/('docs/architecture/autonomous-exploration-baseline-'+args.baseline+'.json')),'protocol_sha256':digest(ROOT/'docs/research/autonomous-exploration-evaluation-v1.md'),
      'g0':g0,'g1':prior,'mode':args.mode,'split':split,'dataset_id':public['dataset_id'],'public_sha256':digest(directory/'public.json'),'oracle_sha256':digest(directory/'oracle.json'),
      'actor_config_sha256':digest(directory/'actor-config.json'),'actor':{'backend':config['backend'],'model':config['model'],'executable_sha256':digest(config['executable']) if config['backend']=='codex_cli' else None,'alias_revision':'provider alias; response revision not separately exposed','temperature':'provider default for Codex; frozen config for local','auth':'existing CLI login; no credentials copied'},
      'sampling':{'repeats':repeats,'seed':20261108,'provider_seed':'not exposed by frozen Codex adapter'},'trials':trials,'trial_limits':limits,
      'run_limits':{'max_model_port_calls':len(trials)*limits['model_calls'],'max_wall_seconds':len(trials)*(limits['wall_seconds']+30),'paid_api_calls':0,'token_limit_semantics':'observed post-call ceiling only; unknown usage halts subsequent calls; Codex output cap not exposed'},
      'scheduler':'evaluation-only virtual 300-second steps; real model I/O and wall watchdog unchanged','world_events':'pre-registered public environment changes; no human messages after seeding',
      'review_policy':{'requested':'science-informed author single review for pilot with anonymized packets','formal_requires':'two independent blind reviews and third adjudication','material_independent_review':'pending'},
      'failure_policy':'retain failures, no fallback, no trial replacement; continue independent cases unless run budget exhausted',
      'source_hashes':hashes,'formal_before':before,'started_utc':datetime.now(timezone.utc).isoformat()}
    for relative in hashes:
        p=directory/'source-snapshot'/relative;p.parent.mkdir(parents=True,exist_ok=True)
        source=directory/'validated-runtime'/relative if relative.startswith('digital_life/') else ROOT/relative
        p.write_bytes(source.read_bytes())
    write(directory/'manifest.json',manifest);(directory/'manifest.sha256').write_text(digest(directory/'manifest.json')+'\n')
    print(str(directory),flush=True)
    index={};total_calls=0
    for i,trial in enumerate(trials,1):
        command=[sys.executable,str(Path(__file__).resolve()),'--worker',str(directory/'manifest.json'),'--trial',trial['trial_id']]
        process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        watchdog=False
        try:stdout,stderr=process.communicate(timeout=limits['wall_seconds']+30)
        except subprocess.TimeoutExpired:
            watchdog=True;process.terminate()
            try:stdout,stderr=process.communicate(timeout=10)
            except subprocess.TimeoutExpired:process.kill();stdout,stderr=process.communicate()
        td=directory/'trials'/trial['trial_id'];td.mkdir(parents=True,exist_ok=True)
        (td/'worker.stdout').write_text(stdout);(td/'worker.stderr').write_text(stderr)
        result_file=td/'result.json'
        result=json.loads(result_file.read_text()) if result_file.is_file() else {}
        summary=result.get('summary') or {};total_calls+=summary.get('real_model_calls',0)
        index[trial['trial_id']]={'exit_code':process.returncode,'watchdog_fired':watchdog,'result_sha256':digest(result_file) if result_file.is_file() else None}
        print(json.dumps({'finished':i,'total':len(trials),'case':trial['case_id'],'status':result.get('status','missing'),'calls':summary.get('real_model_calls'),'error':result.get('error') or summary.get('errors')},ensure_ascii=False),flush=True)
        if total_calls>manifest['run_limits']['max_model_port_calls']:raise RuntimeError('Global call budget exceeded')
    write(directory/'evidence-index.json',index);(directory/'evidence-index.sha256').write_text(digest(directory/'evidence-index.json')+'\n')
    after=g1.formal_guard();write(directory/'formal-instance-guard.json',{'before':before,'after':after,'unchanged':before==after})
    write(directory/'completion.json',{'finished_utc':datetime.now(timezone.utc).isoformat(),'trials_completed':len(index),'model_port_calls':total_calls})
    print('Real trials saved; export review packets before quality aggregation.',flush=True)
    return 0 if before==after else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',default=str(ROOT/'config/local/codex.json'));parser.add_argument('--mode',choices=['pilot','full'],default='pilot')
    parser.add_argument('--baseline',choices=['v1.1','v1.2'],default='v1.2');parser.add_argument('--output',default=str(ROOT/'outputs/acceptance/ae-g2'));parser.add_argument('--worker');parser.add_argument('--trial');args=parser.parse_args()
    raise SystemExit(worker(args.worker,args.trial) if args.worker else run(args))
