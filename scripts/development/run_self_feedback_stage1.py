#!/usr/bin/env python3
"""Paired shadow-off/on mechanism validation in fresh, offline subprocesses.

Uses the declared 125 G1 fixtures as regression probes, without claiming a new
AE-EVAL gate. Runtime and fixture sources are copied before any worker starts.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
import uuid
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def formal_guard():
    root=ROOT/'work/primordial00'
    if not root.is_dir() or root.is_symlink() or not (root/'WAKE_DISABLED').is_file():raise RuntimeError('formal lock missing')
    return {str(p.relative_to(root)):digest(p) for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()}
def behavior(h):
    from digital_life.domain.contracts import dumps
    outputs=[e['output']['action'] for e in h.trace_events if e['kind']=='model_output']
    # Semantic signature, not bytewise equivalence: IDs, clocks and FS metadata differ.
    return {'questions':sorted([(q['question'],q['state'],q['visits'],q.get('resource_revision',0)) for q in h.x.questions().values()]),
      'model_actions':outputs,'model_input_contracts':[{'keys':sorted(p),'instructions':p['instructions'],'schema':p.get('output_schema_version'),
      'exploration_keys':sorted(p.get('exploration',{})),'exploration_instructions':p.get('exploration',{}).get('instructions')} for p in h.model.inputs],
      'dispatch_counts':dict(Counter(e.get('transport') for e in h.trace_events if e['kind']=='dispatch')),
      'activity_states':dict(Counter(r['state'] for r in h.s.rows('activities'))),
      'thought_requests':len(h.s.rows('thought_requests')),'action_attempts':len(h.s.rows('action_attempts')),'live_goals':len(h.s.rows('goal_items'))}
def worker(manifest_path,trial):
    from unittest.mock import patch
    import socket
    from evaluation.exploration.harness import Harness
    from evaluation.exploration.scenarios import material_smoke,mechanism,stop_matrix
    from digital_life.application.learning.self_feedback import SelfFeedback
    manifest_path=Path(manifest_path);run=manifest_path.parent;m=json.loads(manifest_path.read_text())
    if digest(manifest_path)!=(run/'manifest.sha256').read_text().strip():raise RuntimeError('manifest changed')
    for relative,h in m['source_hashes'].items():
        if digest(ROOT/relative)!=h:raise RuntimeError('frozen source changed: '+relative)
    spec=next(t for t in m['trials'] if t['trial_id']==trial);case=next(c for c in json.loads((ROOT/'evaluation/exploration/materials/cases-v1.json').read_text())['cases'] if c['case_id']==spec['case_id'])
    directory=run/'trials'/trial;directory.mkdir(parents=True,exist_ok=False);results={}
    for arm in ('off','on'):
        dest=directory/arm;dest.mkdir();h=None;record={'status':'pass'}
        with tempfile.TemporaryDirectory(prefix='sf-shadow-stage1-') as tmp:
            try:
                with patch.object(socket,'socket',side_effect=RuntimeError('offline stage1')):
                    h=Harness(Path(tmp)/'instance',case,trace_path=dest/'live-trace.jsonl')
                    if arm=='on':SelfFeedback(h.s).configure(h.s.config()['controller'],True)
                    if spec['kind']=='material':material_smoke(h)
                    elif spec['kind']=='mechanism':mechanism(h,spec['operation'])
                    else:stop_matrix(h,spec)
                    h.check(h.s.integrity()=={'integrity':'ok','foreign_keys':[]},'sqlite-integrity')
                    record['behavior']=behavior(h)
                    record['shadow']=SelfFeedback(h.s).status(h.s.config()['controller'])
                    if arm=='on':
                        from digital_life.application.services.learning import Learning
                        from digital_life.application.cognition.cognition_experience import CognitiveExperience
                        opportunities=SelfFeedback(h.s)._events('opportunity')
                        assessments=Learning(h.s).experience_assessments()
                        versions=CognitiveExperience(h.s).events()
                        h.check(len(assessments)==len(opportunities),'learning-assesses-each-opportunity-once')
                        h.check(len(versions)==len(opportunities),'cognition-saves-each-experience-once')
                        h.check(all(r['payload']['owner']=='cognition.experience' for r in versions),'cognitive-experience-owner')
                        h.check(not SelfFeedback(h.s)._events('assessment'),'journal-no-longer-owns-learning-assessment')
                    h.check(not SelfFeedback(h.s)._events('interest_committed'),'no-live-interest-commits')
                    h.check(not any('self_feedback' in p or 'shadow_interest' in p for p in h.model.inputs),'no-shadow-model-context')
            except BaseException as error:record.update(status='fail',error=traceback.format_exc())
            finally:
                if h:
                    try:record['audit']=h.export(dest);record['assertions']=h.assertions
                    finally:h.close()
        record['evidence_hashes']={p.name:digest(p) for p in dest.iterdir() if p.is_file()};write(dest/'result.json',record);results[arm]=record
    equal=results['off'].get('behavior')==results['on'].get('behavior') and 'behavior' in results['off'] and 'behavior' in results['on']
    result={'trial_id':trial,'scenario':spec,'passed':all(r['status']=='pass' for r in results.values()) and equal,'semantic_behavior_equal':equal,
      'arm_results':{arm:{'status':r['status'],'error':r.get('error'),'result_sha256':digest(directory/arm/'result.json')} for arm,r in results.items()}}
    write(directory/'pair.json',result);return 0 if result['passed'] else 1

def run(output):
    before=formal_guard();cases=json.loads((ROOT/'evaluation/exploration/materials/cases-v1.json').read_text())['cases']
    scenarios=json.loads((ROOT/'evaluation/exploration/materials/scenarios-v1.2.json').read_text())['scenarios']
    trials=[{'trial_id':'material-'+c['case_id'],'case_id':c['case_id'],'kind':'material'} for c in cases]+[dict(s,trial_id='scenario-'+s['scenario_id']) for s in scenarios]
    output=Path(output).resolve()
    if output==ROOT or output==ROOT/'work' or ROOT/'work' in output.parents:raise ValueError('not an instance output')
    directory=output/('sf-stage1-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);directory.mkdir(parents=True,exist_ok=False)
    sources=[p for p in (ROOT/'digital_life').rglob('*') if p.is_file() and p.suffix in ('.py','.sql','.json')]
    sources += list((ROOT/'evaluation/exploration').glob('*.py'))
    sources += [ROOT/'evaluation/__init__.py',ROOT/'evaluation/exploration/materials/cases-v1.json',ROOT/'evaluation/exploration/materials/scenarios-v1.2.json',Path(__file__).resolve()]
    hashes={}
    for p in sources:
        if not p.exists():continue
        relative=str(p.relative_to(ROOT));hashes[relative]=digest(p);target=directory/'source-snapshot'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    m={'protocol':'SF-EXPERIENCE-MEASUREMENT-REGRESSION-0.3','scope':'offline paired mechanism regression, not a new formal G1/G2 pass','trials':trials,'source_hashes':hashes,
       'formal_before':before,'arms':['off','on'],'real_model_calls':0,'snapshot_runtime':True,'planned_pairs':len(trials),'equivalence':'semantic actions/inputs shape and instructions/dispatch counts/states; not bytewise identical payloads'}
    write(directory/'manifest.json',m);(directory/'manifest.sha256').write_text(digest(directory/'manifest.json')+'\n');print(str(directory),flush=True)
    index={}
    for number,spec in enumerate(trials,1):
        try:
            p=subprocess.run([sys.executable,str(directory/'source-snapshot/scripts/development/run_self_feedback_stage1.py'),'--worker',str(directory/'manifest.json'),'--trial',spec['trial_id']],capture_output=True,text=True,timeout=60,cwd=directory/'source-snapshot')
            td=directory/'trials'/spec['trial_id'];td.mkdir(parents=True,exist_ok=True);(td/'worker.stdout').write_text(p.stdout);(td/'worker.stderr').write_text(p.stderr)
            pair=td/'pair.json';index[spec['trial_id']]={'exit_code':p.returncode,'pair_sha256':digest(pair) if pair.exists() else None,'passed':json.loads(pair.read_text())['passed'] if pair.exists() else False}
        except subprocess.TimeoutExpired:index[spec['trial_id']]={'exit_code':None,'passed':False,'watchdog':True}
        if number%20==0 or number==len(trials):print(f'{number}/{len(trials)} pairs saved',flush=True)
    after=formal_guard();write(directory/'evidence-index.json',index);(directory/'evidence-index.sha256').write_text(digest(directory/'evidence-index.json')+'\n')
    summary={'run_id':directory.name,'planned_pairs':len(trials),'passed_pairs':sum(v['passed'] for v in index.values()),'planned_arm_trials':len(trials)*2,
             'formal_unchanged':before==after,'formal_after':after,'real_model_calls':0,'failed_pairs':[k for k,v in index.items() if not v['passed']],
             'scope':m['scope'],'passed':all(v['passed'] for v in index.values()) and before==after}
    write(directory/'aggregate.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True);return 0 if summary['passed'] else 1
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker');p.add_argument('--trial');p.add_argument('--output',default=str(ROOT/'outputs/acceptance/self-feedback-stage1'));a=p.parse_args()
    raise SystemExit(worker(a.worker,a.trial) if a.worker else run(a.output))
