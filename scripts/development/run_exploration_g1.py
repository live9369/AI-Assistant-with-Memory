#!/usr/bin/env python3
"""Run AE-EVAL G1 in subprocesses with fresh temporary instances and no networking."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

def checksum(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value): Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def baseline_path(version): return ROOT/('docs/architecture/autonomous-exploration-baseline-'+version+'.json')

def g0(version='v1.2'):
    checker='verify_exploration_contract.py' if version=='v1' else 'verify_exploration_contract_'+version.replace('.','_')+'.py'
    spec=importlib.util.spec_from_file_location('ae_g0',ROOT/'scripts'/checker)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); raw=module.verify()
    if raw['successful']: return dict(raw,evaluated_runtime='current-workspace',workspace_g0=raw)
    if version!='v1': return raw
    expected=json.loads((ROOT/'docs/architecture/autonomous-exploration-baseline-v1.json').read_text())['frozen_files']['digital_life/application/runtime/engine.py']
    overlay=ROOT/'evaluation/exploration/frozen_engine_v1.py'
    if raw['errors']==['Frozen file differs or missing: digital_life/application/runtime/engine.py'] and overlay.is_file() and checksum(overlay)==expected:
        return dict(raw,successful=True,errors=[],evaluated_runtime='frozen-engine-overlay',workspace_g0=raw,overlay_sha256=expected)
    return raw
def formal_guard():
    root=ROOT/'work/primordial00'
    if not root.exists(): return {'state':'not_present','files':{}}
    if root.is_symlink(): raise RuntimeError('Formal instance root is a symlink')
    if not (root/'WAKE_DISABLED').is_file(): raise RuntimeError('Formal instance lock is not present; refusing evaluation')
    files={str(p.relative_to(root)):checksum(p) for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()}
    return {'state':'locked','files':files}

def worker(manifest_path,trial_id):
    from unittest.mock import patch
    manifest_path=Path(manifest_path).resolve(); run=manifest_path.parent
    if checksum(manifest_path)!=(run/'manifest.sha256').read_text().strip(): raise RuntimeError('Unsealed manifest')
    manifest=json.loads(manifest_path.read_text()); spec=next(t for t in manifest['trials'] if t['trial_id']==trial_id)
    frozen=json.loads((run/'baseline.json').read_text())
    for relative,expected in frozen['frozen_files'].items():
        source=run/'frozen-engine.py' if relative=='digital_life/application/runtime/engine.py' and manifest['g0'].get('evaluated_runtime')=='frozen-engine-overlay' else ROOT/relative
        if checksum(source)!=expected: raise RuntimeError('Frozen source changed before trial: '+relative)
    for relative,expected in manifest['runtime_dependency_hashes'].items():
        source=run/'frozen-engine.py' if relative=='digital_life/application/runtime/engine.py' and manifest['g0'].get('evaluated_runtime')=='frozen-engine-overlay' else ROOT/relative
        if checksum(source)!=expected: raise RuntimeError('Runtime dependency changed: '+relative)
    if manifest['g0'].get('evaluated_runtime')=='frozen-engine-overlay':
        source=run/'frozen-engine.py'
        if checksum(source)!=manifest['g0']['overlay_sha256']: raise RuntimeError('Frozen overlay mismatch')
        module_spec=importlib.util.spec_from_file_location('digital_life.application.runtime.engine',source)
        module=importlib.util.module_from_spec(module_spec); sys.modules[module_spec.name]=module; module_spec.loader.exec_module(module)
    from evaluation.exploration.harness import Harness
    from evaluation.exploration.scenarios import material_smoke,mechanism,stop_matrix,RECOVERY_SCENARIOS
    case=next(c for c in json.loads((run/'cases.json').read_text())['cases'] if c['case_id']==spec['case_id'])
    for relative,digest in manifest['inputs'].items():
        if checksum(ROOT/relative)!=digest: raise RuntimeError('Changed evaluation input '+relative)
    directory=run/'trials'/trial_id; directory.mkdir(parents=True,exist_ok=False)
    h=None; started=time.monotonic_ns(); error=None; status='pass'; evidence={}; audit=None
    def expired(*args): raise TimeoutError('G1 worker watchdog requested termination')
    signal.signal(signal.SIGTERM,expired)
    # No existing work/ instance can be supplied. The only instance root comes from tempfile.
    with tempfile.TemporaryDirectory(prefix='ae-g1-') as temporary:
        root=Path(temporary)/'instance'
        try:
            with patch.object(socket,'socket',side_effect=RuntimeError('Network disabled for G1')):
                h=Harness(root,case,trace_path=directory/'live-trace.jsonl')
                if spec['kind']=='material': material_smoke(h)
                elif spec['kind']=='mechanism': mechanism(h,spec['operation'])
                else: stop_matrix(h,spec)
                h.check(h.s.integrity()=={'integrity':'ok','foreign_keys':[]},'sqlite-integrity')
        except BaseException as exception:
            status='fail'; error={'type':type(exception).__name__,'message':str(exception),'traceback':traceback.format_exc()}
        finally:
            if h:
                try: audit=h.export(directory)
                except BaseException as exception:
                    status='error'; error={'type':type(exception).__name__,'message':'Evidence export: '+str(exception)}
                finally: h.close()
            for filename in ('snapshot.json','artifacts.json','trace.json','live-trace.jsonl'):
                if (directory/filename).exists(): evidence[filename]=checksum(directory/filename)
    result={'trial_id':trial_id,'case_id':case['case_id'],'kind':spec['kind'],'scenario':spec,'status':status,'error':error,
      'duration_ns':time.monotonic_ns()-started,'assertions':h.assertions if h else [],'audit':audit,'evidence_hashes':evidence,
      'recovery_scenario':spec.get('operation') in RECOVERY_SCENARIOS,
      'read_replay_opportunity':spec.get('operation') in ('receipt_dedup','receipt_crash','unknown_result','failed_tool'),
      'model':'ae-g1-scripted-v1','real_model_used':False}
    write(directory/'result.json',result)
    return 0 if status=='pass' else 1

def run(output,timeout,version):
    from evaluation.exploration.aggregate import aggregate
    before=formal_guard(); baseline=g0(version)
    if not baseline['successful']: raise RuntimeError('Frozen baseline differs: '+str(baseline['errors']))
    # Explicitly separate G1 fixtures from the future blinded G2 data set.
    materials=ROOT/'evaluation/exploration/materials/cases-v1.json'; scenarios=ROOT/('evaluation/exploration/materials/scenarios-'+version+'.json')
    data=json.loads(materials.read_text()); scenario_data=json.loads(scenarios.read_text())
    run_id='g1-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    base=Path(output).resolve()
    if base==ROOT or (ROOT/'work').resolve()==base or (ROOT/'work').resolve() in base.parents: raise ValueError('Evaluation output cannot be an instance directory')
    directory=base/run_id; directory.mkdir(parents=True,exist_ok=False)
    inputs=[materials,scenarios,Path(__file__).resolve(),*sorted((ROOT/'evaluation/exploration').glob('*.py')),ROOT/('scripts/verification/verify_exploration_contract.py' if version=='v1' else 'scripts/verify_exploration_contract_'+version.replace('.','_')+'.py'),baseline_path(version)]
    runtime_sources=[p for p in (ROOT/'digital_life').rglob('*') if p.is_file() and p.suffix in ('.py','.sql','.json')]
    runtime_hashes={}
    for path in runtime_sources:
        relative=str(path.relative_to(ROOT)); source=ROOT/'evaluation/exploration/frozen_engine_v1.py' if relative=='digital_life/application/runtime/engine.py' and baseline.get('evaluated_runtime')=='frozen-engine-overlay' else path
        runtime_hashes[relative]=checksum(source)
        archive=directory/'source-snapshot'/relative; archive.parent.mkdir(parents=True,exist_ok=True); archive.write_bytes(source.read_bytes())
    for path in inputs:
        archive=directory/'source-snapshot'/path.relative_to(ROOT); archive.parent.mkdir(parents=True,exist_ok=True); archive.write_bytes(path.read_bytes())
    trials=[{'trial_id':'material-'+c['case_id'],'case_id':c['case_id'],'kind':'material'} for c in data['cases']]
    trials += [dict(s,trial_id='scenario-'+s['scenario_id']) for s in scenario_data['scenarios']]
    manifest={'run_id':run_id,'protocol_id':'AE-EVAL-1.0','metrics_protocol':'AE-METRICS-1.0','runtime_protocol':'AE-RUNTIME-'+('1.0' if version=='v1' else version[1:]),
     'baseline_sha256':checksum(baseline_path(version)),
     'protocol_sha256':checksum(ROOT/'docs/research/autonomous-exploration-evaluation-v1.md'),
     'dataset_id':data['dataset_id'],'dataset_sha256':checksum(materials),'split':'G1-authored-mechanism-fixtures-only','quality_data_registered':False,
     'inputs':{str(p.relative_to(ROOT)):checksum(p) for p in inputs},'runtime_dependency_hashes':runtime_hashes,'g0':baseline,'trials':trials,
     'model':{'backend':'injected-fixture','version':'ae-g1-scripted-v1','network':False,'generation':'deterministic Python responses','temperature':None,'output_schema_version':2,'instruction_version':'exploration-v2' if version=='v1.2' else 'exploration-v1'},
     'tool':{'implementation':'registry.invoke injected through existing executor','permissions':['read_file','list_files'],'workspace':'fresh TemporaryDirectory per trial'},
     'configuration':{'max_activities':12,'max_rounds':3,'interval_seconds':300,'overrides':'explicit scenario budget probes in preregistered scenario source'},
     'arm':'g1-scripted','repeat':1,'seed':20261108,'time_source':'time.monotonic_ns in worker; UTC for logs; forced due-time only at explicit tick fixture',
     'review':{'mode':'machine assertions; no quality labels','blind_review':'not_applicable_G1'},
     'allowed_events':'fixture files and scenarios are sealed above; no human prompts after fixture initialization',
     'fault_policy':'retain every failure and continue independent trials; no rerun replacement','trial_watchdog_seconds':timeout,
     'fees':0,'real_model_calls_limit':0,'threshold_policy':'AE-EVAL-1.0 section 4 workspace-read',
     'formal_instance_before':before,'started_utc':datetime.now(timezone.utc).isoformat()}
    if baseline.get('evaluated_runtime')=='frozen-engine-overlay':
        (directory/'frozen-engine.py').write_bytes((ROOT/'evaluation/exploration/frozen_engine_v1.py').read_bytes())
    write(directory/'cases.json',data)
    (directory/'baseline.json').write_bytes(baseline_path(version).read_bytes())
    write(directory/'manifest.json',manifest); (directory/'manifest.sha256').write_text(checksum(directory/'manifest.json')+'\n')
    index={}; print(str(directory),flush=True)
    for number,trial in enumerate(trials,1):
        command=[sys.executable,str(Path(__file__).resolve()),'--worker',str(directory/'manifest.json'),'--trial',trial['trial_id']]
        process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        timeout_hit=False
        try: stdout,stderr=process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timeout_hit=True; process.terminate()
            try: stdout,stderr=process.communicate(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); stdout,stderr=process.communicate()
        td=directory/'trials'/trial['trial_id']; td.mkdir(parents=True,exist_ok=True)
        (td/'worker.stdout').write_text(stdout); (td/'worker.stderr').write_text(stderr)
        result=td/'result.json'
        index[trial['trial_id']]={'exit_code':process.returncode,'watchdog_fired':timeout_hit,'result_sha256':checksum(result) if result.exists() else None}
        if number%10==0 or number==len(trials): print(f'{number}/{len(trials)} trials saved',flush=True)
    write(directory/'evidence-index.json',index)
    (directory/'evidence-index.sha256').write_text(checksum(directory/'evidence-index.json')+'\n')
    after=formal_guard(); unchanged=before==after
    write(directory/'formal-instance-guard.json',{'before':before,'after':after,'unchanged':unchanged,'opened_for_execution':False})
    write(directory/'completion.json',{'finished_utc':datetime.now(timezone.utc).isoformat(),'trials_completed':len(index),'watchdogs':sum(e['watchdog_fired'] for e in index.values())})
    summary=aggregate(directory)
    if not unchanged: summary['gates']['G1']='fail'; summary['formal_instance_changed']=True
    summary['formal_instance_unchanged']=unchanged
    summary['finished_utc']=datetime.now(timezone.utc).isoformat(); write(directory/'aggregate.json',summary)
    print(json.dumps({'run_directory':str(directory),'gates':summary['gates'],'passed':summary['passed'],'planned':len(trials),'invariants':summary['invariants'],'evidence_missing':len(summary['evidence_missing']),'formal_instance_unchanged':unchanged},ensure_ascii=False),flush=True)
    return 0 if summary['gates']['G1']=='pass' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default=str(ROOT/'outputs/acceptance/ae-g1'));parser.add_argument('--timeout',type=int,default=30)
    parser.add_argument('--baseline',choices=['v1','v1.1','v1.2'],default='v1.2');parser.add_argument('--worker');parser.add_argument('--trial');args=parser.parse_args()
    if not 1<=args.timeout<=120: parser.error('timeout must be 1..120 seconds')
    raise SystemExit(worker(args.worker,args.trial) if args.worker else run(args.output,args.timeout,args.baseline))
