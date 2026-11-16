"""Bounded native prepare measurement on a formal-data snapshot; no inference."""
import importlib.util,json,shutil,sqlite3,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.services.memory import Memory
from digital_life.application.runtime.engine import Engine
from digital_life.application.accounts import account_scope as scope

formal=Path('work/primordial00-first-wake').resolve();out=Path('outputs/memory-latency-fix');out.mkdir(exist_ok=True)
root=out/'snapshot'
if root.exists():raise RuntimeError('measurement snapshot already exists')
root.mkdir();(root/'WAKE_DISABLED').write_text('snapshot only; never start a runner')
for name in ('runtime.sqlite','accounts.sqlite','control.sqlite'):
 src=sqlite3.connect((formal/name).as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(root/name);src.backup(dst);dst.close();src.close()
shutil.copytree(formal/'blobs',root/'blobs');(root/'workspace').mkdir();(root/'snapshots').mkdir()
oldfile=formal/'releases/146063c467fc427a57416fc493bf0d48a74341e5a6cf5a6d0d3516d19aff796b/digital_life/application/services/memory.py'
spec=importlib.util.spec_from_file_location('latency_baseline_memory',oldfile);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
s=Store(root);report={'model_calls':0,'formal_data_modified':False,'root':str(root)}
try:
 memory='e3261fa5530a4687ba84c22748b7874b';results=[]
 for label,cls in [('before',old.Memory),('after',Memory)]:
  t=time.perf_counter();readers=cls(s).readers(memory);results.append({'version':label,'seconds':time.perf_counter()-t,'readers':sorted(readers)})
 report['same_memory']=results;assert results[0]['readers']==results[1]['readers']
 # Match the native runtime's actual startup integrity check before timing prepare.
 t=time.perf_counter();integrity=s.integrity()
 report['startup_integrity_seconds']=time.perf_counter()-t
 assert integrity['integrity']=='ok' and not integrity['foreign_keys']
 info=(root/'runtime.sqlite').stat()
 s._startup_integrity={'file_identity':(info.st_dev,info.st_ino),'schema_version':s.db.execute('PRAGMA schema_version').fetchone()[0],'configuration_id':s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(s.instance_id,)).fetchone()[0]}
 # This only permits input preparation in this process; no runtime/model is started.
 (root/'WAKE_DISABLED').unlink()
 packet=json.loads(Path('outputs/experience-return-formal-2b6d6342/input-3.json').read_text())
 class NoModel:
  name=packet['model']
  def generate(self,*args):raise AssertionError('model must never be called')
 with scope.audience(s,scope.principal(s)['id']):
  engine=Engine(s);a=engine.submit(packet['task'],'memory-latency-measurement','evaluation')
  t=time.perf_counter();_,prepared=engine.prepare(a,NoModel());report['prepare_seconds']=time.perf_counter()-t
  context=engine.details(a)[1]['id'];t=time.perf_counter()
  # Original scoring/selection order, with fixed readers used by account guards.
  prior=old.Memory(s).retrieve(packet['task'],a,context)
  report['legacy_selection_with_fixed_guards_seconds']=time.perf_counter()-t
  report['same_selected_revisions']=[v['revision_id'] for v in prior['items']]==[v['revision_id'] for v in prepared['selected_memories']]
  assert report['same_selected_revisions']
  report['selected_count']=len(prepared['selected_memories']);report['context_mode']=prepared['context_mode']
  report['timings']=[s.read_artifact(r[0]) for r in s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE activity_id=? AND event_type='memory.retrieval_timing'",(a,))]
finally:
 (root/'WAKE_DISABLED').write_text('measurement ended; never start a runner')
 s.close();(out/'measurement.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
