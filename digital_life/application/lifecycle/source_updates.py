"""Source proposals, immutable candidate builds and fixed independent probes."""
import ast
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from digital_life.domain.contracts import utc,sha,dumps,text,identifier,ContractError,Forbidden,Conflict
from digital_life.infrastructure.processes.dispatch_gate import coordinated
from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
from digital_life.application.lifecycle.control_plane import Control,Releases

PROBE_VERSION='t12-file-goal-isolated-v2'
PROBE=r'''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.autonomy.task_loop import TaskLoop
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.accounts.authorization import Policy
class Model:
 name='fixed-independent-probe'
 def __init__(self):self.inputs=[]
 def generate(self,p):
  self.inputs.append(p)
  return {'schema_version':1,'explanation':'fixed candidate probe','action':{'tool':'write_note','arguments':{'path':'notes/probe.txt','text':'t12-independent-success'}}}
s=Store.prepare(sys.argv[2]);c=Control(s.root,s.instance_id)
try:
 (s.root/'WAKE_DISABLED').unlink();c.resume('fixed-probe');Policy(s).mode('open',['write_note'],s.config()['controller'])
 e=Engine(s);m=Model()
 for i in range(2):
  a=e.submit('fixed file goal',str(i));TaskLoop(s).configure(a,{'kind':'file_contains','path':'notes/probe.txt','text':'t12-independent-success'},s.config()['controller'])
  e.think(a,m);intent=s.rows('action_intents')[-1];e.execute(intent['id'])
 if len(m.inputs)!=2 or m.inputs[0]['context_mode']!='fresh_request' or m.inputs[1]['context_mode']!='fresh_request':raise RuntimeError('fresh request contract failed')
finally:c.close();s.close()
'''

class SourceUpdates:
 def __init__(self,store):self.s=store;self.m=SelfMaintenance(store)
 def events(self,kind):
  result=[]
  for row in self.s.db.execute('SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type=? ORDER BY event_seq',(self.s.instance_id,'source_update.'+kind)):
   data=self.s.read_artifact(row[1])
   if isinstance(data,dict) and 'redacted_by' not in data:result.append(dict(data,id=row[0]))
  return result
 def emit(self,kind,value,activity=None):return self.s.event('source_update.'+kind,payload=value,activity=activity,lane='control')
 def active(self):
  path=self.s.root/'control.sqlite'
  if path.is_symlink():raise Forbidden('control database symlink')
  if not path.is_file():return None
  c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
  try:
   row=c.execute("SELECT id,release FROM deployments WHERE state='active' ORDER BY rowid DESC LIMIT 1").fetchone();return dict(row) if row else None
  finally:c.close()
 def validate_changes(self,changes):
  if not isinstance(changes,dict) or not 1<=len(changes)<=5:raise ContractError('1-5 source changes required')
  size=0
  for name,content in changes.items():
   if not isinstance(name,str):raise ContractError('source path string required')
   path=Path(name)
   if path.is_absolute() or len(path.parts)<2 or path.parts[0]!='digital_life' or any(p.startswith('.') for p in path.parts) or str(path)!=name:raise Forbidden('relative package path required')
   if path.suffix not in ('.py','.json','.sql','.html','.css','.js'):raise ContractError('unsupported source type')
   if not isinstance(content,str) or len(content.encode())>65536:raise ContractError('bounded UTF-8 source required')
   size+=len(content.encode())
   if size>131072:raise ContractError('source proposal exceeds 128KB')
   if path.suffix=='.py':ast.parse(content,filename=name)
   if path.suffix=='.json':json.loads(content)
 @coordinated
 def propose(self,base_deployment,changes,reason,key,actor,source=None):
  self.m.authority(actor);text(reason,1000);text(key,120);self.validate_changes(changes)
  if not self.m.config()['enabled']:raise Forbidden('maintenance disabled')
  spec={'base_deployment':base_deployment,'changes':changes,'reason':reason,'key':key,'source':source}
  with self.s.tx():
   old=next((p for p in self.events('proposed') if p['key']==key),None)
   if old:
    if any(old[k]!=v for k,v in spec.items()):raise Conflict('proposal key changed')
    return old
   active=self.active()
   if not active or active['id']!=base_deployment:raise Conflict('source baseline is not current deployment')
   value=dict(spec,at=utc());ref=self.emit('proposed',value)
  return dict(value,id=ref)
 def capture(self,intent,outcome):
  """Called only after a canonical, already authorized write_note result."""
  if not self.m.config()['enabled'] or outcome['state']!='succeeded':return None
  row=self.s.row('action_intents',intent);tool=self.s.row('tool_definitions',row['tool_id']);args=json.loads(row['arguments_json'])
  if tool['name'] in ('project_write','project_edit'):
   from digital_life.application.lifecycle.project_source_updates import capture
   return capture(self,intent,outcome)
  path=args.get('path','')
  if tool['name']!='write_note' or not path.startswith('maintenance/update-') or not path.endswith('.json'):return None
  if any(p.get('result')==outcome['result'] for p in self.events('captured')):return None
  try:
   canonical=self.s.row('action_results',outcome['result']);attempt=self.s.row('action_attempts',canonical['attempt_id'])
   if attempt['intent_id']!=intent or canonical['state']!='succeeded' or canonical['receipt_artifact_id']!=outcome['receipt'] or canonical['outcome_ref']!=outcome['evidence']:raise Forbidden('source receipt mismatch')
   receipt=self.s.read_artifact(canonical['receipt_artifact_id']);data=receipt.get('evidence',{})
   if data.get('path')!=path or data.get('sha256')!=sha(args['text'].encode()):raise Forbidden('source content not verified')
   spec=json.loads(args['text'])
   if not isinstance(spec,dict) or set(spec)!={'base_deployment','changes','reason'}:raise ContractError('invalid source proposal envelope')
   decision=self.s.row('decision_candidates',row['candidate_id'])['decision_id']
   lineage=None
   for event in self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type='thought.accepted' ORDER BY event_seq DESC",(self.s.instance_id,)):
    value=self.s.read_artifact(event[0])
    if value.get('decision')==decision:lineage=value;break
   if not lineage:raise Forbidden('source proposal lacks accepted thought provenance')
   thought=self.s.row('thought_results',lineage['result'])
   if thought['acceptance']!='accepted' or thought['request_id']!=lineage['request']:raise Forbidden('source thought not accepted')
   proposal=self.propose(**spec,key='action:'+intent,actor=self.s.config()['controller'],source={'request':lineage['request'],'thought_result':lineage['result'],'intent':intent,'result':outcome['result'],'evidence':outcome['evidence']})
   self.emit('captured',{'result':outcome['result'],'proposal':proposal['id']});return proposal
  except (ContractError,ValueError,TypeError,SyntaxError) as e:
   self.emit('captured',{'result':outcome['result'],'rejected':True,'reason':type(e).__name__});return {'rejected':True}
 def proposal(self,ref):
  p=next((p for p in self.events('proposed') if p['id']==ref),None)
  if not p:raise ContractError('source proposal missing')
  return p
 @coordinated
 def build(self,ref,actor):
  self.m.authority(actor);self.m.stopped();p=self.proposal(ref)
  if not self.m.config()['enabled']:raise Forbidden('maintenance disabled')
  active=self.active()
  if not active or active['id']!=p['base_deployment']:raise Conflict('source baseline superseded')
  c=Control(self.s.root,self.s.instance_id)
  try:
   releases=Releases(c);base=releases.verify(p['base_deployment'])
   old=next((r for r in self.events('built') if r['proposal']==ref),None)
   if old:releases.verify(old['deployment']);return old
   # A temporary source tree avoids modifying either the host checkout or live release.
   with tempfile.TemporaryDirectory(prefix='digital-life-candidate-') as temp:
    source=Path(temp)/'source';shutil.copytree(base,source);(source/'manifest.json').unlink()
    for name,content in p['changes'].items():
     file=source/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(content)
    # Legacy unprotected stores retain their existing source-update path,
    # but changed code cannot inherit a reviewed schema4 bridge declaration.
    from digital_life.application.learning.bridge import declaration,protected_storage_required
    from digital_life.application.learning.runtime import legacy_protection_present
    schema=self.s.db.execute('PRAGMA user_version').fetchone()[0]
    if type(schema) is not int or schema not in (2,3,4):raise Forbidden('unknown schema cannot narrow release capabilities')
    declaration_file=source/'digital_life/resources/release.json'
    bounds=declaration(json.loads(declaration_file.read_text())) if declaration_file.is_file() else {'schema_min':2,'schema_max':2}
    if schema<=3 and bounds['schema_max']==4:
     if protected_storage_required(self.s.db,c):raise Forbidden('protected storage cannot narrow to an unqualified old release')
     if bounds['schema_min']>schema:raise Forbidden('source release does not support this legacy schema')
     narrowed=dict(bounds,schema_max=3);narrowed.pop('tool_learning_bridge',None);narrowed.pop('capabilities',None);declaration_file.write_text(dumps(narrowed))
     with self.s.tx():self.emit('capability_narrowed',{'proposal':ref,'schema':schema,'from_max':4,'to_max':3,'bridge_capability':False,'reason':'unprotected legacy source update only'})
    deployment=releases.stage(source)
   row=c.db.execute('SELECT release FROM deployments WHERE id=?',(deployment,)).fetchone()
   value={'proposal':ref,'deployment':deployment,'release':row[0],'base_deployment':p['base_deployment'],'at':utc()}
   with self.s.tx():record=self.emit('built',value)
   return dict(value,id=record)
  finally:c.close()
 @coordinated
 def validate(self,ref,actor,timeout=30):
  self.m.authority(actor);self.m.stopped()
  if not self.m.config()['enabled']:raise Forbidden('maintenance disabled')
  if type(timeout) not in (int,float) or not 1<=timeout<=60:raise ContractError('probe timeout 1-60 seconds')
  p=self.proposal(ref);built=next((r for r in self.events('built') if r['proposal']==ref),None)
  if not built:raise Conflict('build candidate first')
  if not self.active() or self.active()['id']!=p['base_deployment']:raise Conflict('source baseline superseded')
  c=Control(self.s.root,self.s.instance_id)
  try:
   releases=Releases(c);releases.verify(p['base_deployment']);candidate=releases.verify(built['deployment']);row=c.db.execute('SELECT * FROM deployments WHERE id=?',(built['deployment'],)).fetchone();schema=self.s.db.execute('PRAGMA user_version').fetchone()[0]
   if not row['schema_min']<=schema<=row['schema_max']:raise Conflict('candidate incompatible with current schema')
   result={'proposal':ref,'deployment':built['deployment'],'release':built['release'],'base_deployment':p['base_deployment'],'schema':schema,'probe_version':PROBE_VERSION,'passed':False,'at':utc(),'model_calls':'fixture only','formal_instance_used':False}
   try:
    with tempfile.TemporaryDirectory(prefix='digital-life-probe-') as temp:
     root=Path(temp)/'probe';root.mkdir()
     isolated=Path(temp)/'candidate';shutil.copytree(candidate,isolated)
     from digital_life.infrastructure.processes.candidate_sandbox import CandidateSandbox,SandboxError,VERSION
     result['isolation']={'backend':VERSION,'required':True,'state':'not-started'}
     try:proc=CandidateSandbox().run(isolated,root,PROBE,[isolated,root],timeout)
     except SandboxError as error:
      result['isolation']=error.isolation;raise
     result['isolation']=proc.isolation
     if proc.returncode!=0:raise ContractError('candidate sandbox probe process failed')
     # Host-side verification does not trust candidate stdout or return code alone.
     if (root/'workspace/notes/probe.txt').read_bytes()!=b't12-independent-success':raise ContractError('candidate goal artifact missing')
     db=sqlite3.connect((root/'runtime.sqlite').as_uri()+'?mode=ro',uri=True)
     try:
      if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():raise ContractError('candidate probe storage invalid')
      if db.execute("SELECT count(*) FROM activities WHERE state='completed'").fetchone()[0]!=2 or db.execute("SELECT count(*) FROM thought_requests WHERE state='succeeded'").fetchone()[0]!=2:raise ContractError('candidate lifecycle probe incomplete')
      requests=db.execute('SELECT request_key,request_parent_id FROM thought_requests').fetchall()
      if len({r[0] for r in requests})!=2 or any(r[1] for r in requests):raise ContractError('candidate independent calls invalid')
     finally:db.close()
    releases.verify(built['deployment'])
    if not self.active() or self.active()['id']!=p['base_deployment'] or self.s.db.execute('PRAGMA user_version').fetchone()[0]!=schema:raise Conflict('source validation baseline changed')
    result['passed']=True
   except (ContractError,subprocess.TimeoutExpired,OSError,sqlite3.Error,ValueError) as e:result['error']=type(e).__name__;result['reason']=str(e)[:256] if isinstance(e,ContractError) else 'candidate probe did not complete'
   with self.s.tx():record=self.emit('validated',result)
   return dict(result,id=record)
  finally:c.close()
 def status(self):return {'proposals':self.events('proposed'),'candidates':self.events('built'),'validations':self.events('validated'),'service_started_runtime':False,'active_deployment':self.active(),'lifecycle_authority':'existing explicit CLI deploy; never invoked here'}
 def assert_deployable(self,deployment):
  built=next((r for r in self.events('built') if r['deployment']==deployment),None)
  if not built:return
  if not self.m.config()['enabled']:raise Forbidden('maintenance disabled')
  proofs=[r for r in self.events('validated') if r['deployment']==deployment]
  schema=self.s.db.execute('PRAGMA user_version').fetchone()[0];active=self.active()
  if not proofs or not proofs[-1]['passed'] or proofs[-1]['release']!=built['release'] or proofs[-1]['schema']!=schema or proofs[-1]['probe_version']!=PROBE_VERSION or not active or active['id']!=built['base_deployment']:raise Forbidden('source candidate requires current independent validation')
  from digital_life.infrastructure.processes.candidate_sandbox import VERSION,POLICY,BOOTSTRAP
  isolation=proofs[-1].get('isolation',{})
  if isolation.get('backend')!=VERSION or isolation.get('required') is not True or isolation.get('state')!='exited' or isolation.get('returncode')!=0:raise Forbidden('source candidate requires current OS-isolated validation')
  if isolation.get('policy_sha256')!=sha(POLICY) or isolation.get('bootstrap_sha256')!=sha(BOOTSTRAP):raise Forbidden('candidate isolation policy changed; revalidate before deploying')
