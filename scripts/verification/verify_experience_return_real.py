"""Three independent real calls in a new synthetic instance; never wakes the formal instance."""
import json,sqlite3,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.configuration import configure_model
from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
from digital_life.application.autonomy.exploration import Exploration
from digital_life.application.autonomy.continuous_exploration import ContinuousExploration
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.accounts.accounts import install,Accounts
from digital_life.application.accounts.account_scope import audience
from digital_life.application.services.memory import Memory
from digital_life.application.runtime.engine import Engine
from digital_life.application.chat.chat import Chat
from digital_life.application.accounts.authorization import Policy
from digital_life.application.monitoring.management import Management
from digital_life.infrastructure.llm.inference import configured_reasoner
from digital_life.domain.contracts import utc,sha,dumps

project=Path(__file__).resolve().parents[2];out=project/'outputs/experience-return-real';out.mkdir(parents=True,exist_ok=True)
root=project/'work'/('experience-return-real-'+uuid.uuid4().hex[:8]);formal=project/'work/primordial00-first-wake'
db=sqlite3.connect((formal/'runtime.sqlite').as_uri()+'?mode=ro',uri=True)
try:
 ref=db.execute('SELECT artifact_ref FROM configuration_versions ORDER BY rowid DESC LIMIT 1').fetchone()[0];storage=db.execute('SELECT storage_ref FROM artifacts WHERE id=?',(ref,)).fetchone()[0];model_config=json.loads((formal/'blobs'/storage).read_text())['model']
finally:db.close()
s=Store.prepare(root,name='经验回流·合成验收');s.close();install(root);s=Store(root);result={'formal_instance_used':False,'data':str(root),'passed':False};calls=[]
try:
 configure_model(s,model_config,s.config()['controller'],check_available=False);CognitiveUpdates(s).configure(True,s.config()['controller']);x=Exploration(s);x.configure(s.config()['controller'],True,3,3,60,600,mode='continuous')
 token='ER-'+uuid.uuid4().hex[:8];content='这是合成验收资料，不代表现实生活。\n测试对象：青帆盒。\n测试代号：'+token+'。\n有效范围：本次隔离验收。\n';(root/'workspace/learning-case.txt').write_text(content)
 with s.tx():
  event=s.event('acceptance.experience_fixture',payload={'synthetic':True,'goal':'读取learning-case.txt并保存青帆盒的测试代号，随后结束；不得提前猜测代号。'},source='synthetic-acceptance',key='source')
  ev=s.evidence(object_id=event,method='synthetic-fixture');memory=Memory(s).encode('合成验收：资料位于learning-case.txt，需要读取后学习青帆盒测试代号。',ev)
  direction={'id':sha(str(root)),'title':'从合成资料学习青帆盒测试代号','kind':'explore','next_step':'先提出read_file读取learning-case.txt，尚未读到时learning.claims留空；读取后将测试代号保存为reported学习提案，引用实际正文，然后结束，不扩题。','expected_gain':.8,'cost':.1,'evidence_refs':[memory['revision_id']],'state':'ready','parent_id':None,'understanding':'尚未读取资料','no_progress':0,'steps':0,'due_at':utc(),'reopen_condition':''}
  ContinuousExploration(x).emit('direction',direction)
 (root/'WAKE_DISABLED').unlink();control=Control(root,s.instance_id);control.resume('user-authorized-synthetic-real-test');control.close()
 model=configured_reasoner(model_config)
 class Capture:
  name=model.name
  def __getattr__(self,key):return getattr(model,key)
  def generate(self,p):
   index=len(calls)+1;(out/f'input-{index}.json').write_text(json.dumps(p,ensure_ascii=False,indent=2))
   value=model.generate(p);(out/f'output-{index}.json').write_text(json.dumps(value,ensure_ascii=False,indent=2));calls.append({'session':getattr(model,'last_session_id',None),'schema':p['output_schema_version'],'context_mode':p['context_mode'],'memory_representations':[m['revision_id'] for m in p['selected_memories'] if m.get('source_kind')=='cognition-representation']});print(json.dumps({'call':index,'schema':p['output_schema_version'],'status':'returned'}),flush=True);return value
 engine=Engine(s);capture=Capture()
 for step in range(2):
  d=ContinuousExploration(x).directions()[direction['id']]
  a=engine.submit(d['title']+'\n'+d['next_step'],'real-learning-'+str(step),'exploration')
  with s.tx():s.event('exploration.bound',payload={'version':2,'mode':'continuous','activity':a,'generation':x.config()['generation'],'kind':'continuous','question_id':None,'direction_id':direction['id'],'max_rounds':3,'next_due':utc(),'output_schema_version':6},activity=a)
  answer=engine.process_one(capture)
  if step==0:
   assert 'approval_id' in answer,answer
   approval=Management(s).approval(answer['approval_id']);assert approval['tool']=='read_file' and approval['arguments']=={'path':'learning-case.txt'}
   Policy(s).approve(answer['approval_id'],s.config()['controller']);observed=engine.process_one(capture);assert observed['state']=='succeeded',observed
  else:
   assert answer.get('accepted'),answer
   assert ContinuousExploration(x).directions()[direction['id']]['state']=='finished'
 x.configure(s.config()['controller'],False)
 learned=s.db.execute("SELECT r.* FROM memory_revisions r JOIN memory_items m ON m.current_revision_id=r.id WHERE r.encoding_method='cognition-representation-v1' AND instr(r.content,?)>0",(token,)).fetchall();assert learned,'real proposal did not publish learned content'
 auth=Accounts(root,s.instance_id)
 try:root_account=auth.root_id()
 finally:auth.close()
 with audience(s,root_account):
  thread='acct_'+root_account
  assert not Chat(s).rows(thread)
  Chat(s).send(thread,{'text':'青帆盒的测试代号是什么？请按已有记录回答，并说明来源性质，不编造。','idempotency_key':'fresh-question','expected_last_activity_id':None})
 answer=engine.process_one(capture);assert answer.get('accepted'),answer
 last=json.loads((out/'output-3.json').read_text());assert token in last['explanation'];assert calls[-1]['memory_representations'],'new call did not retrieve a cognition representation'
 packet=json.loads((out/'input-3.json').read_text());assert packet['conversation_context']['messages']==[]
 assert len(calls)==3 and len({v['session'] for v in calls})==3 and all(v['context_mode']=='fresh_request' for v in calls)
 result.update(passed=True,calls=calls,learned_representations=len(learned),answer=last['explanation'],conversation_history_empty=True)
except Exception as exc:
 result.update(error=type(exc).__name__,detail=str(exc),calls=calls);raise
finally:
 (root/'WAKE_DISABLED').write_text('Synthetic real-model verification ended. No formal identity used.\n');c=Control(root,s.instance_id);c.stop('real-experience-test-ended');c.close();s.close();(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
