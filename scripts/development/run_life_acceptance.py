"""Foreground isolated LIFE-ACCEPTANCE-1 experiment; no existing-instance option."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from evaluation.life_acceptance import PROTOCOL,fingerprint,assess,cycle,history,adaptation
from digital_life.domain.contracts import dumps,sha,utc,identifier,ContractError,Forbidden

def run(output,duration=30,interval=1):
 from digital_life.infrastructure.persistence.sqlite_store import Store
 from digital_life.application.lifecycle.control_plane import Control,Releases
 from digital_life.application.accounts.authorization import Policy
 from digital_life.application.memory.memory_quality import MemoryQuality
 from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
 from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
 from digital_life.application.memory.data_management import backup_bundle,restore_bundle
 output=Path(output).resolve()
 if output.exists():raise ContractError('experiment output must be new')
 if type(duration) not in (int,float) or not 0<duration<=172800 or type(interval) not in (int,float) or not .1<=interval<=240:raise ContractError('bounded experiment timing required')
 output.mkdir(parents=True);root=output/'instance';run_id=identifier();source=fingerprint(ROOT);records=[];error=None;completed=False;restored_locked=False
 s=Store.prepare(root);c=Control(root,s.instance_id)
 try:
  (root/'life-acceptance.json').write_text(dumps({'run':run_id,'scope':'isolated fixture only'}))
  SelfMaintenance(s).configure(True,s.config()['controller'],auto_repair=True,max_repairs=3);MemoryQuality(s).configure(True,s.config()['controller']);MemoryQuality(s).rebuild(s.config()['controller']);AutonomyAgenda(s).configure(True,s.config()['controller'])
  deployment=Releases(c).stage(ROOT);Releases(c).activate(deployment,lambda p:{'ready':True,'schema_compatible':True});start_at=utc(duration+3600)
  promise=AutonomyAgenda(s).promise('future obligation retained',start_at,utc(duration+7200),{'kind':'file_contains','path':'notes/future.txt','text':'future'},'future',s.config()['controller'])
  (root/'WAKE_DISABLED').unlink();c.resume('experiment-start');trained=adaptation(s)
  if not trained['passed']:raise ContractError('controlled adaptation check failed')
  Policy(s).mode('open',['write_note','read_file','list_files'],s.config()['controller']);count,digest=history(s.db)
  baseline={'instance':s.instance_id,'anchors':sha(dumps(s.rows('identity_anchors'))),'memory_count':count,'memory_hash':digest,'promise':promise['commitment'],'start_at':start_at,'deployment':deployment,'association':trained['association']}
  (output/'adaptation.json').write_text(dumps(trained));(output/'protocol.json').write_text(dumps(PROTOCOL));(output/'source-start.json').write_text(dumps(source));(output/'checkpoints').mkdir()
 except BaseException:
  c.stop('experiment-bootstrap-failed');(root/'WAKE_DISABLED').write_text('Failed acceptance setup; do not wake.\n');raise
 finally:c.close();s.close()
 started=time.monotonic();began=utc();previous='';last_started=started
 try:
  while time.monotonic()-started<duration:
   n=len(records);basefile=output/'worker-baseline.json';basefile.write_text(dumps(baseline))
   last_started=time.monotonic()
   proc=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',str(root),'--run',run_id,'--cycle',str(n),'--baseline',str(basefile)],capture_output=True,text=True,timeout=120,env={'PATH':__import__('os').environ.get('PATH',''),'PYTHONDONTWRITEBYTECODE':'1'})
   if proc.returncode:raise ContractError('cycle worker failed: '+proc.stderr[-1000:])
   row=json.loads(proc.stdout);row['elapsed']=time.monotonic()-started;row['at']=utc();row['previous']=previous
   # Parent verifies the same identity, history prefix and immutable source independently.
   db=sqlite3.connect((root/'runtime.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
   try:
    if db.execute('SELECT id FROM identity_instances').fetchone()[0]!=baseline['instance'] or history(db,baseline['memory_count'])[1]!=baseline['memory_hash'] or history(db)!=(row['memory_count'],row['memory_hash']):raise ContractError('parent continuity check failed')
    requests=db.execute('SELECT count(*) FROM thought_requests').fetchone()[0];results=db.execute("SELECT count(*) FROM action_results WHERE state='succeeded'").fetchone()[0]
    if requests<2*(n+1) or results<2*(n+1):raise ContractError('parent interaction check failed')
   finally:db.close()
   if (root/'workspace/notes'/('cycle-'+str(n)+'.txt')).read_text()!='cycle='+str(n):raise ContractError('parent environment check failed')
   if fingerprint(ROOT)!=source:raise ContractError('source changed during experiment')
   previous=sha(dumps(row));(output/'checkpoints'/('%06d.json'%n)).write_text(dumps({'record':row,'hash':previous}));records.append(row);baseline.update(memory_count=row['memory_count'],memory_hash=row['memory_hash'])
   print(dumps({'cycle':n,'elapsed':row['elapsed'],'repair':row['repair_verified']}),file=sys.stderr,flush=True)
   # Short waits permit foreground interruption and prevent hidden background work.
   until=min(started+duration,last_started+interval)
   while time.monotonic()<until:time.sleep(min(.25,until-time.monotonic()))
  completed=True
 except (Exception,KeyboardInterrupt) as e:error=type(e).__name__+': '+str(e)
 elapsed=time.monotonic()-started
 # Fail closed before opening possibly damaged runtime storage.
 (root/'WAKE_DISABLED').write_text('Acceptance evidence only; do not wake.\n')
 stop_control=Control(root,baseline['instance'])
 try:stop_control.stop('experiment-finished')
 finally:stop_control.close()
 s=Store(root);c=Control(root,s.instance_id)
 try:
  c.stop('experiment-finished');(root/'WAKE_DISABLED').write_text('Acceptance evidence only; do not wake.\n')
  # A supported restore cannot silently create a runnable concurrent identity.
  backup_bundle(s,output/'backup');restore_bundle(output/'backup',output/'restore-check');copy=Store(output/'restore-check')
  try:
   try:copy.assert_execution_allowed()
   except Forbidden:restored_locked=True
  finally:copy.close()
  if not restored_locked:completed=False;error='restore identity lock not enforced'
  (root/'EVIDENCE_ONLY').write_text('Isolated fixture; not a deployment or formal identity.\n')
 finally:c.close();s.close()
 stable=source==fingerprint(ROOT);finished=utc();report=assess(records,elapsed,stable,completed,began,finished)
 report.update(run=run_id,started_at=began,finished_at=finished,source_stable=stable,error=error,restored_copy_locked=restored_locked,adaptation=trained,checkpoint_tail=previous,instance=baseline['instance'])
 (output/'source-end.json').write_text(dumps(fingerprint(ROOT)));(output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');return report

def verify(output):
 output=Path(output);report=json.loads((output/'report.json').read_text());records=[];previous=''
 if json.loads((output/'protocol.json').read_text())!=PROTOCOL:raise ContractError('protocol mismatch')
 for file in sorted((output/'checkpoints').glob('*.json')):
  entry=json.loads(file.read_text());r=entry['record']
  if r['previous']!=previous or sha(dumps(r))!=entry['hash']:raise ContractError('checkpoint chain invalid')
  previous=entry['hash'];records.append(r)
 if previous!=report['checkpoint_tail']:raise ContractError('checkpoint tail missing')
 stable=json.loads((output/'source-start.json').read_text())==json.loads((output/'source-end.json').read_text())
 recomputed=assess(records,report['elapsed_seconds'],stable,report.get('error') is None,report['started_at'],report['finished_at'])
 if any(recomputed[k]!=report[k] for k in ('passed','engineering_passed','long_horizon_passed','cycles','verified_repairs','processes','errors')):raise ContractError('reported verdict does not match evidence')
 db=sqlite3.connect((output/'instance/runtime.sqlite').resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 control=sqlite3.connect((output/'instance/control.sqlite').resolve().as_uri()+'?mode=ro',uri=True);control.row_factory=sqlite3.Row
 try:
  if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():raise ContractError('evidence database integrity')
  if db.execute('SELECT id FROM identity_instances').fetchone()[0]!=report['instance']:raise ContractError('evidence identity mismatch')
  if records and history(db)!=(records[-1]['memory_count'],records[-1]['memory_hash']):raise ContractError('evidence memory prefix mismatch')
  anchors=sha(dumps([dict(r) for r in db.execute('SELECT * FROM identity_anchors WHERE instance_id=?',(report['instance'],))]))
  repairs=set()
  def artifact(ref):
   row=db.execute('SELECT hash,storage_ref FROM artifacts WHERE id=?',(ref,)).fetchone()
   if not row:raise ContractError('missing evidence artifact')
   path=output/'instance/blobs'/row['storage_ref']
   if path.is_symlink() or path.resolve().parent!=(output/'instance/blobs').resolve():raise ContractError('invalid evidence artifact path')
   raw=path.read_bytes()
   if sha(raw)!=row['hash']:raise ContractError('evidence artifact hash mismatch')
   return json.loads(raw)
  def event(ref,kind):
   row=db.execute('SELECT payload_artifact_id FROM runtime_events WHERE id=? AND event_type=?',(ref,kind)).fetchone()
   if not row:raise ContractError('missing canonical event')
   return artifact(row[0])
  adaptation=json.loads((output/'adaptation.json').read_text())
  if adaptation!=report['adaptation'] or adaptation.get('passed') is not True:raise ContractError('adaptation evidence mismatch')
  a=adaptation
  fields=('before','after','reverted','unrelated_before','unrelated_after')
  import math
  if any(type(a.get(k)) not in (int,float) or not math.isfinite(a[k]) or not 0<=a[k]<=1 for k in fields) or not(a['after']>a['before']+1e-6 and abs(a['reverted']-a['before'])<1e-10 and abs(a['unrelated_after']-a['unrelated_before'])<1e-10):raise ContractError('adaptation numeric contract failed')
  habit_events=[artifact(x[0]) for x in db.execute("SELECT payload_artifact_id FROM runtime_events WHERE event_type='habit_learning.changed'")]
  related=[v for v in habit_events if v.get('association')==a['association']]
  if not related or related[-1]['after']['state']!='active' or not any(v['kind']=='rollback' for v in related):raise ContractError('adaptation lifecycle evidence missing')
  for r in records:
   if r['instance']!=report['instance'] or r['anchors']!=anchors:raise ContractError('checkpoint identity anchor mismatch')
   if r['repair_verified']:
    if not r.get('repair_event') or r['repair_event'] in repairs:raise ContractError('repair evidence missing or reused')
    repair=event(r['repair_event'],'maintenance.repaired');repairs.add(r['repair_event'])
    if repair.get('passed') is not True or repair['kind']!='rebuild_index' or repair['before']['index']['state']!='degraded' or repair['after']['facts']['index']['state']!='healthy':raise ContractError('repair canonical result mismatch')
   process=control.execute('SELECT pid,exited_at FROM process_runs WHERE id=?',(r['process_run'],)).fetchone()
   if not process or process['pid']!=r['pid'] or not process['exited_at']:raise ContractError('missing actual process evidence')
   handoff=control.execute("SELECT 1 FROM control_sleep_handoffs WHERE process_run_id=? AND runtime_epoch=? AND phase='committed'",(r['process_run'],r['epoch'])).fetchone()
   if not handoff:raise ContractError('missing sleep continuity evidence')
   path=output/'instance/workspace/notes'/('cycle-'+str(r['cycle'])+'.txt')
   if path.read_text()!='cycle='+str(r['cycle']):raise ContractError('environment evidence missing')
   for step,tool in enumerate(('write_note','read_file')):
    key='evaluation:'+report['run']+':'+str(r['cycle'])+':'+str(step)
    activity=db.execute('SELECT a.id,a.state FROM activities a JOIN perception_signals p ON p.id=a.trigger_event_id WHERE p.external_id=?',(key,)).fetchone()
    if not activity or activity['state']!='completed':raise ContractError('cycle activity missing or incomplete')
    req=db.execute("SELECT q.*,r.acceptance FROM thought_requests q JOIN thought_results r ON r.id=q.accepted_result_id WHERE q.activity_id=?",(activity['id'],)).fetchall()
    if len(req)!=1 or req[0]['acceptance']!='accepted' or artifact(req[0]['request_artifact_id']).get('context_mode')!='fresh_request':raise ContractError('fresh accepted request evidence missing')
    receipts=db.execute('SELECT r.*,t.name FROM action_results r JOIN action_attempts x ON x.id=r.attempt_id JOIN action_intents i ON i.id=x.intent_id JOIN tool_definitions t ON t.id=i.tool_id JOIN decision_candidates c ON c.id=i.candidate_id JOIN decision_records d ON d.id=c.decision_id WHERE d.activity_id=?',(activity['id'],)).fetchall()
    if len(receipts)!=1 or receipts[0]['state']!='succeeded' or receipts[0]['name']!=tool:raise ContractError('cycle canonical tool result mismatch')
    receipt=artifact(receipts[0]['receipt_artifact_id']);data=receipt.get('evidence',{})
    if receipt.get('verification')!='pass' or data.get('path')!='notes/cycle-'+str(r['cycle'])+'.txt' or data.get('sha256')!=sha(('cycle='+str(r['cycle'])).encode()):raise ContractError('cycle receipt content mismatch')
    if tool=='read_file' and data.get('text')!='cycle='+str(r['cycle']):raise ContractError('read observation mismatch')
  actual_results=db.execute("SELECT count(*) FROM action_results WHERE state='succeeded'").fetchone()[0]
  if actual_results<2*len(records):raise ContractError('insufficient actual results')
  state=control.execute('SELECT user_stopped,active_process_run_id FROM instance_control_state').fetchone()
  if not state['user_stopped'] or state['active_process_run_id']:raise ContractError('experiment not stopped')
 finally:control.close();db.close()
 if not report['restored_copy_locked'] or not (output/'instance/WAKE_DISABLED').is_file() or not (output/'restore-check/RESTORE_RECONCILIATION_REQUIRED').is_file():raise ContractError('evidence lock missing')
 return recomputed

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--duration-seconds',type=float,default=30);p.add_argument('--interval-seconds',type=float,default=1);p.add_argument('--verify',type=Path);p.add_argument('--worker',type=Path);p.add_argument('--run');p.add_argument('--cycle',type=int);p.add_argument('--baseline',type=Path);args=p.parse_args()
 if args.worker:
  print(dumps(cycle(args.worker,args.run,args.cycle,json.loads(args.baseline.read_text()))));return 0
 if args.verify:print(dumps(verify(args.verify)));return 0
 if not args.output:args.output=ROOT/'outputs/acceptance'/('t13-run-'+identifier())
 result=run(args.output,args.duration_seconds,args.interval_seconds);print(dumps(result));return 0 if result['engineering_passed'] else 1
if __name__=='__main__':raise SystemExit(main())
