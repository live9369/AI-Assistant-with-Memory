"""Bounded substrate maintenance; never changes identity, permissions or lifecycle."""
import json
from pathlib import Path
import shutil
import sqlite3
from digital_life.domain.contracts import utc,sha,dumps,text,ContractError,Forbidden,Conflict
from digital_life.infrastructure.processes.dispatch_gate import coordinated
from digital_life.application.memory.memory_quality import MemoryQuality,INDEX

class SelfMaintenance:
 def __init__(self,store):self.s=store
 def events(self,kind):
  result=[]
  for row in self.s.db.execute('SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type=? ORDER BY event_seq',(self.s.instance_id,'maintenance.'+kind)):
   data=self.s.read_artifact(row[1])
   if isinstance(data,dict) and 'redacted_by' not in data:result.append(dict(data,id=row[0]))
  return result
 def emit(self,kind,payload):return self.s.event('maintenance.'+kind,payload=payload,lane='control')
 def config(self):
  rows=self.events('configured');return rows[-1] if rows else {'enabled':False,'auto_repair':False,'max_repairs':0,'id':None}
 def authority(self,actor):
  if actor!=self.s.config()['controller']:raise Forbidden('controller required')
 def stopped(self):
  from digital_life.application.lifecycle.control_plane import Control
  c=Control(self.s.root,self.s.instance_id)
  try:
   state=c.state()
   if not state['user_stopped'] or state['active_process_run_id']:raise Conflict('stop before maintenance control operation')
  finally:c.close()
 @coordinated
 def configure(self,enabled,actor,auto_repair=False,max_repairs=3):
  self.authority(actor);self.stopped()
  if type(enabled) is not bool or type(auto_repair) is not bool or type(max_repairs) is not int or not 1<=max_repairs<=3:raise ContractError('invalid maintenance configuration')
  with self.s.tx():self.emit('configured',{'enabled':enabled,'auto_repair':auto_repair,'max_repairs':max_repairs,'actor':actor})
  return self.config()
 def index_state(self):
  q=MemoryQuality(self.s);p=self.s.root/INDEX
  if not q.config()['enabled']:return {'state':'not_applicable','reason':'quality index disabled'}
  if any((self.s.root/(INDEX+suffix)).is_symlink() for suffix in ('','-wal','-shm','-journal')):return {'state':'blocked','reason':'symlink'}
  if not p.exists():return {'state':'degraded','reason':'missing'}
  c=None
  try:
   c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
   if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError()
   meta=dict(c.execute('SELECT key,value FROM meta'));c.execute('SELECT count(*) FROM docs').fetchone();c.execute('SELECT count(*) FROM postings').fetchone()
   if meta.get('instance')!=self.s.instance_id:return {'state':'degraded','reason':'identity mismatch'}
   return {'state':'healthy' if meta.get('watermark')==q.watermark() else 'needs_sync','reason':'derived data; authoritative memory unchanged'}
  except (sqlite3.Error,OSError,ValueError):return {'state':'degraded','reason':'invalid'}
  finally:
   if c:c.close()
 def facts(self):
  integrity=self.s.integrity();cfg=self.s.config();workspace=self.s.root/'workspace'
  identity=self.s.db.execute('SELECT count(*) FROM identity_instances WHERE id=?',(self.s.instance_id,)).fetchone()[0]==1
  anchor=self.s.db.execute('SELECT anchor_data FROM identity_anchors WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()
  try:anchor_ok=bool(anchor) and json.loads(anchor[0]).get('instance_id')==self.s.instance_id
  except (ValueError,TypeError):anchor_ok=False
  unknown=self.s.db.execute("SELECT count(*) FROM action_intents WHERE instance_id=? AND state IN ('running','dispatching','unknown')",(self.s.instance_id,)).fetchone()[0]
  return {'storage':integrity,'identity':identity and anchor_ok,'workspace':'blocked' if workspace.is_symlink() or (workspace.exists() and not workspace.is_dir()) else 'healthy' if workspace.is_dir() else 'missing','resources':shutil.disk_usage(self.s.root).free>=64*1024*1024,'index':self.index_state(),'source_watermark':MemoryQuality(self.s).watermark(),'unknown_effects':unknown}
 def diagnose(self):
  f=self.facts();dimensions={
   'storage':{'state':'healthy' if f['storage']['integrity']=='ok' and not f['storage']['foreign_keys'] else 'degraded','repair':'controller investigation'},
   'identity':{'state':'healthy' if f['identity'] else 'degraded','repair':'controller investigation; never regenerate'},
   'workspace':{'state':'healthy' if f['workspace']=='healthy' else 'degraded','repair':'restore_workspace' if f['workspace']=='missing' else 'controller investigation'},
   'resources':{'state':'healthy' if f['resources'] else 'degraded','repair':'reduce workload / controller'},
   'memory_index':dict(f['index'],repair='rebuild_index' if f['index']['state']=='degraded' else 'none'),
   'external_effects':{'state':'degraded' if f['unknown_effects'] else 'healthy','repair':'explicit reconciliation; no replay'},
   'cognition':{'state':'unknown','repair':'independent task evaluation'},'model_quality':{'state':'unknown','repair':'not inferred from process health'}}
  state='degraded' if any(d['state'] in ('degraded','blocked') for d in dimensions.values()) else 'unknown'
  from digital_life.application.lifecycle.control_plane import Control
  from digital_life.application.lifecycle.process_checkpoints import ProcessCheckpoints
  control=Control(self.s.root,self.s.instance_id)
  try:
   manager=ProcessCheckpoints(control);cfg=manager.config()
   latest=control.db.execute("SELECT payload FROM control_commands WHERE kind='process.checkpoint' AND state='succeeded' ORDER BY rowid DESC LIMIT 1").fetchone() if cfg.get('enabled') else None
   recovery={'enabled':cfg.get('enabled',False),'checkpoint':json.loads(latest[0])['id'] if latest else None,'lifecycle_authority':'CLI/watchdog','state_policy':'preserve-current-ledger'}
  finally:control.close()
  report={'state':state,'dimensions':dimensions,'facts':f,'at':utc(),'scope':'substrate evidence; unknown is not healthy'}
  report['process_recovery']=recovery
  with self.s.tx():ref=self.emit('diagnosed',report)
  return dict(report,id=ref)
 def remaining(self):
  cfg=self.config();used=sum(r['configuration']==cfg['id'] for r in self.events('attempted'));return max(0,cfg['max_repairs']-used)
 def allowed(self,f):return f['identity'] and f['storage']['integrity']=='ok' and not f['storage']['foreign_keys'] and f['resources'] and not f['unknown_effects']
 @coordinated
 def plan(self,kind,key,actor):
  self.authority(actor);text(key,120);cfg=self.config()
  if not cfg['enabled']:raise Forbidden('maintenance disabled')
  if kind not in ('restore_workspace','rebuild_index'):raise ContractError('repair not whitelisted')
  with self.s.tx():
   old=next((p for p in self.events('planned') if p['key']==key),None)
   if old:
    if old['kind']!=kind:raise Conflict('idempotency key changed')
    return old
   f=self.facts()
   if not self.allowed(f):raise Forbidden('core health or unresolved effects block repair')
   if kind=='restore_workspace' and f['workspace']!='missing':raise Conflict('workspace is not safely missing')
   if kind=='rebuild_index' and f['index']['state']!='degraded':raise Conflict('index does not require rebuild')
   value={'kind':kind,'configuration':cfg['id'],'facts':f,'key':key,'created_at':utc(),'expires_at':utc(300),'instance':self.s.instance_id};ref=self.emit('planned',value)
  return dict(value,id=ref)
 @coordinated
 def repair(self,plan,actor,_automatic=False):
  self.authority(actor)
  if _automatic:self.s.assert_execution_allowed()
  else:self.stopped()
  with self.s.tx():
   p=next((p for p in self.events('planned') if p['id']==plan),None)
   if not p:raise ContractError('repair plan missing')
   old=next((r for r in self.events('repaired') if r['plan']==plan),None)
   if old:return old
   if any(r['plan']==plan for r in self.events('attempted')):raise Conflict('repair attempt already consumed; inspect result')
   cfg=self.config()
   if not cfg['enabled'] or p['configuration']!=cfg['id'] or p['expires_at']<=utc() or p['facts']!=self.facts():raise Conflict('repair plan superseded')
   if _automatic and not cfg['auto_repair']:raise Forbidden('automatic repair not enabled')
   if not self.remaining():raise Conflict('maintenance budget exhausted')
   self.emit('attempted',{'plan':plan,'configuration':cfg['id'],'automatic':_automatic,'at':utc()})
  # Attempt is committed before filesystem mutation, so a crash cannot retry it.
  error=None
  try:
   if p['kind']=='restore_workspace':(self.s.root/'workspace').mkdir(exist_ok=False)
   else:
    MemoryQuality.drop_index(self.s.root);MemoryQuality(self.s).rebuild(actor)
  except Exception as e:error=type(e).__name__
  after=self.diagnose();passed=after['facts']['workspace']=='healthy' if p['kind']=='restore_workspace' else after['facts']['index']['state']=='healthy'
  value={'plan':plan,'kind':p['kind'],'passed':passed and error is None,'error':error,'before':p['facts'],'after':after,'at':utc(),'scope':'target repaired only; other dimensions may remain unknown'}
  with self.s.tx():ref=self.emit('repaired',value)
  return dict(value,id=ref)
 def tick(self):
  cfg=self.config()
  if not cfg['enabled']:return None
  self.s.assert_execution_allowed();rows=self.events('tick')
  if rows and rows[-1]['next_due']>utc():return None
  with self.s.tx():self.emit('tick',{'next_due':utc(30)})
  report=self.diagnose()
  if cfg['auto_repair'] and self.remaining() and self.allowed(report['facts']):
   kind='restore_workspace' if report['facts']['workspace']=='missing' else 'rebuild_index' if report['facts']['index']['state']=='degraded' else None
   if kind:
    try:return self.repair(self.plan(kind,'auto:'+report['id'],self.s.config()['controller'])['id'],self.s.config()['controller'],_automatic=True)
    except (Forbidden,Conflict) as e:
     with self.s.tx():self.emit('deferred',{'diagnosis':report['id'],'reason':str(e)})
  return report
 def context(self):
  cfg=self.config()
  if not cfg['enabled']:return None
  rows=self.events('diagnosed');latest=rows[-1] if rows else None
  from digital_life.application.lifecycle.source_updates import SourceUpdates
  active=SourceUpdates(self.s).active()
  return {'base_deployment':active['id'] if active else None,'configuration':cfg['id'],'auto_repair':cfg['auto_repair'],'remaining_repairs':self.remaining(),'diagnosis':{'state':latest['state'],'dimensions':latest['dimensions'],'at':latest['at'],'process_recovery':latest.get('process_recovery')} if latest else None,'source_update':'Authorized project_write/project_edit of digital_life package source with a verified Git receipt can create a source proposal when the before hash matches this deployment. A working edit is not deployed. For multiple related files, write maintenance/update-KEY.json with {base_deployment,reason,changes} as one proposal. CLI validates and deploys. Never claim deployed.','lifecycle_authority':'CLI only'}
 def check(self,payload):
  expected=payload.get('self_maintenance');current=self.context()
  if (expected or {}).get('configuration')!=(current or {}).get('configuration'):raise Forbidden('maintenance configuration changed')
 def status(self):return {'configuration':self.config(),'remaining_repairs':self.remaining(),'diagnoses':self.events('diagnosed')[-3:],'plans':self.events('planned'),'repairs':self.events('repaired'),'inference_started':False}
