#!/usr/bin/env python3
"""Freeze sources, run offline constructed measurement controls, retain evidence."""
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import secrets
import subprocess,sys,tempfile,traceback
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def formal_guard():
 p=ROOT/'work/primordial00'
 if not p.is_dir() or p.is_symlink() or not (p/'WAKE_DISABLED').is_file():raise RuntimeError('formal instance lock missing')
 return {str(f.relative_to(p)):digest(f) for f in sorted(p.rglob('*')) if f.is_file()}
def worker(manifest_path,condition):
 from unittest.mock import patch
 import socket
 from evaluation.exploration.harness import Harness
 from evaluation.experience_measurement import FixturePredictor
 from digital_life.application.learning.self_feedback import SelfFeedback
 from digital_life.application.learning.experience_measurement import ExperienceMeasurement
 from digital_life.application.services.cognition import Cognition
 from digital_life.domain.contracts import ContractError,Conflict,Forbidden
 manifest_path=Path(manifest_path);run=manifest_path.parent;m=json.loads(manifest_path.read_text())
 if digest(manifest_path)!=(run/'manifest.sha256').read_text().strip():raise RuntimeError('unsealed manifest')
 for relative,expected in m['source_hashes'].items():
  if digest(ROOT/relative)!=expected:raise RuntimeError('source snapshot changed')
 dest=run/'trials'/condition;dest.mkdir(parents=True,exist_ok=False);h=None;out={'condition':condition,'status':'pass'}
 case=next(c for c in json.loads((ROOT/'evaluation/exploration/materials/cases-v1.json').read_text())['cases'] if c['case_id']=='B01')
 with tempfile.TemporaryDirectory(prefix='experience-measurement-control-') as tmp:
  try:
   with patch.object(socket,'socket',side_effect=RuntimeError('offline control')):
    h=Harness(Path(tmp)/'instance',case,trace_path=dest/'live-trace.jsonl');actor=h.s.config()['controller']
    sf=SelfFeedback(h.s);sf.configure(actor,True);measure=ExperienceMeasurement(h.s);measure.configure(True,actor)
    activity=h.investigation();h.finish(activity);op=sf._events('opportunity')[0]['payload']['opportunity_ref']
    cases=[{'case_id':'new','input':'synthetic heldout new-task control','split':'target'},{'case_id':'old','input':'synthetic heldout retention control','split':'retention'}]
    labels={'new':1,'old':1};nonce=secrets.token_hex(32)
    r=measure.register(op,cases,2,measure.commitment(labels,nonce),actor);port=FixturePredictor(condition)
    if condition=='stop':
     port.on_call=lambda:h.c.stop('measurement-control-stop')
     h.raises(Forbidden,lambda:measure.run_predictions(r,port,actor),'stop-blocks-next-measurement-dispatch')
     h.check(len(port.requests)==1,'only-inflight-call-retained')
    elif condition=='budget':
     with h.s.tx():h.s.db.execute('UPDATE activity_budget_accounts SET attempt_limit=3 WHERE activity_id=?',(activity,))
     h.raises(ContractError,lambda:measure.run_predictions(r,port,actor),'parent-budget-refuses-whole-pair')
     h.check(not port.requests,'no-hidden-budget-call')
    else:
     measure.run_predictions(r,port,actor)
     if condition=='changed-labels':
      h.raises(Forbidden,lambda:measure.reveal_labels(r,{'new':0,'old':1},nonce,actor),'changed-label-commitment-rejected')
     else:
      measure.reveal_labels(r,labels,nonce,actor);report_ref=measure.evaluate(r,actor);report=measure.checked_report(report_ref)
      expected={'positive':'positive','negative':'negative','zero':'measured_zero','retention-regression':'negative','unknown':'unknown','invalidation':'positive','replay':'positive'}[condition]
      h.check(report['gain_status']==expected,'score-condition-correct',report=report)
      version=measure.adopt_shadow(report_ref,actor);out['report_ref']=report_ref;out['measurement']=report;out['experience_revision_ref']=version
      if condition=='retention-regression':h.check(report['target_gain']>0 and report['retention_regression']>0 and report['gain']<0,'retention-veto-is-effective')
      if condition=='invalidation':
       measure.invalidate(r,'constructed label source invalidation',actor)
       cell=next(c for c in Cognition(h.s).experience_snapshot(actor)['cells'] if c['cell'][-1]=='prediction_brier_v1')
       h.check(cell['sample_count']==0,'invalidated-report-excluded')
      if condition=='replay':h.check(measure.adopt_shadow(report_ref,actor)==version,'same-measurement-not-counted-twice')
    out['measurement_port_calls']=len(port.requests)
    for request in port.requests:h.check(nonce not in json.dumps(request) and 'labels' not in request,'oracle-not-in-prediction-request')
    h.check(len(h.s.rows('thought_requests'))==3,'live-actor-thoughts-not-increased')
    h.check(not Cognition(h.s).experience_snapshot(actor)['affects_selection'],'shadow-only')
    h.check(h.s.integrity()=={'integrity':'ok','foreign_keys':[]},'sqlite-integrity')
  except BaseException:out.update(status='fail',error=traceback.format_exc())
  finally:
   if h:
    try:out['audit']=h.export(dest);out['assertions']=h.assertions
    finally:h.close()
 out['evidence_hashes']={p.name:digest(p) for p in dest.iterdir() if p.is_file()};write(dest/'result.json',out)
 return 0 if out['status']=='pass' else 1

def run(output):
 from evaluation.experience_measurement import CONDITIONS
 before=formal_guard();output=Path(output).resolve()
 if output==ROOT or output==ROOT/'work' or ROOT/'work' in output.parents:raise ValueError('not an instance output')
 directory=output/('experience-measurement-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4));directory.mkdir(parents=True,exist_ok=False)
 sources=[p for p in (ROOT/'digital_life').rglob('*') if p.is_file() and p.suffix in ('.py','.sql','.json')]
 sources += list((ROOT/'evaluation/exploration').glob('*.py'))+[ROOT/'evaluation/experience_measurement.py',ROOT/'evaluation/exploration/materials/cases-v1.json',Path(__file__).resolve()]
 hashes={}
 for p in sources:
  rel=str(p.relative_to(ROOT));hashes[rel]=digest(p);target=directory/'source-snapshot'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
 manifest={'protocol':'EXPERIENCE-MEASUREMENT-CONTROLS-0.1','source_hashes':hashes,'conditions':CONDITIONS,'formal_before':before,'scope':'constructed offline prediction-port controls, not evidence of real-model learning','real_model_calls':0}
 write(directory/'manifest.json',manifest);(directory/'manifest.sha256').write_text(digest(directory/'manifest.json')+'\n');print(str(directory),flush=True)
 index={}
 for condition in CONDITIONS:
  td=directory/'trials'/condition
  try:
   p=subprocess.run([sys.executable,str(directory/'source-snapshot/scripts/development/run_experience_measurement.py'),'--worker',str(directory/'manifest.json'),'--condition',condition],cwd=directory/'source-snapshot',capture_output=True,text=True,timeout=60)
   td.mkdir(parents=True,exist_ok=True);(td/'worker.stdout').write_text(p.stdout);(td/'worker.stderr').write_text(p.stderr)
   result=td/'result.json';index[condition]={'exit_code':p.returncode,'result_sha256':digest(result) if result.exists() else None,'passed':json.loads(result.read_text())['status']=='pass' if result.exists() else False}
  except subprocess.TimeoutExpired:index[condition]={'passed':False,'watchdog':True}
  print(condition,index[condition]['passed'],flush=True)
 after=formal_guard();write(directory/'evidence-index.json',index);(directory/'evidence-index.sha256').write_text(digest(directory/'evidence-index.json')+'\n')
 summary={'run_id':directory.name,'planned':len(CONDITIONS),'passed':sum(v['passed'] for v in index.values()),'failed':[k for k,v in index.items() if not v['passed']],
          'formal_unchanged':before==after,'formal_after':after,'real_model_calls':0,'scope':manifest['scope']}
 write(directory/'aggregate.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True);return 0 if summary['passed']==summary['planned'] and before==after else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',default=str(ROOT/'outputs/acceptance/experience-measurement'));p.add_argument('--worker');p.add_argument('--condition');a=p.parse_args()
 raise SystemExit(worker(a.worker,a.condition) if a.worker else run(a.output))
