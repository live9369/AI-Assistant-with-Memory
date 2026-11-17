"""Core native chat regression: unlimited mode, real tools and explicit identity."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.runtime.engine import Engine
from digital_life.application.runtime.scheduling import Budget
from digital_life.application.chat.chat import Chat
from digital_life.application.chat.self_knowledge import Names
from digital_life.application.monitoring.instance_settings import InstanceSettings
from digital_life.domain.contracts import Forbidden

class ReadSeveralFiles:
 name='isolated-core-model'
 def __init__(self,count=6):self.count=count;self.calls=0;self.inputs=[]
 def generate(self,p):
  self.inputs.append(p);n=self.calls;self.calls+=1
  if n<self.count:return dict(schema_version=1,action=dict(tool='project_read',arguments=dict(path='part'+str(n)+'.txt',start_line=1,max_lines=20)),explanation='检查第'+str(n+1)+'份材料')
  return dict(schema_version=1,action=dict(tool='wait',arguments=dict(reason='核对完成')),explanation='已核对六份材料，结论：各文件均含预期说明。')

class ChatCoreFixes(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)/'instance';self.s=Store.prepare(self.root);self.c=Control(self.root,self.s.instance_id)
  self.addCleanup(self.t.cleanup);self.addCleanup(self.s.close);self.addCleanup(self.c.close)
 def save(self,key,**kwargs):
  m=InstanceSettings(self.s);section=next(x for x in m.read()['sections'] if x['id']==key)
  return m.save(key,dict(values=dict(section['values'],**kwargs),expected_revision=section['revision'],reason='isolated regression',confirmed=True))
 def start(self):
  (self.root/'WAKE_DISABLED').unlink(missing_ok=True);self.c.resume('fixture-start');return Engine(self.s)
 def project(self):
  from digital_life.application.lifecycle.project_access import ProjectAccess
  p=Path(self.t.name)/'project';p.mkdir()
  for i in range(6):(p/('part'+str(i)+'.txt')).write_text('verified fixture '+str(i))
  ProjectAccess(self.s).configure(str(p),self.s.config()['controller'],enabled=True,auto_approve=True,tools=['project_read'])
 def send(self,text,key='one',thread='fixture'):
  rows=Chat(self.s).rows(thread)
  return Chat(self.s).send(thread,dict(text=text,idempotency_key=key,expected_last_activity_id=rows[-1]['id'] if rows else None))['activity_id']
 def test_unlimited_six_tools_and_seven_independent_thoughts_finish(self):
  self.project();engine=self.start();activity=self.send('检查这六份材料');model=ReadSeveralFiles()
  for i in range(7):
   result=engine.think(activity,model)
   if result.get('action_id'):self.assertEqual(engine.execute(result['action_id'])['state'],'succeeded')
  self.assertEqual(self.s.row('activities',activity)['state'],'completed');self.assertEqual(model.calls,7)
  self.assertIsNone(self.s.row('activities',activity)['deadline']);remaining=Budget(self.s).remaining(activity)
  self.assertEqual(remaining['mode'],'unlimited');self.assertIsNone(remaining['tokens'])
  self.assertEqual(self.s.db.execute('select count(*) from budget_reservations where activity_id=?',(activity,)).fetchone()[0],13)
  self.assertEqual(len({r['activity_id'] for r in model.inputs}),1)
  self.assertEqual(len(self.s.rows('thought_requests')),7)
  self.assertTrue(all(p['context_mode']=='fresh_request' for p in model.inputs))
  self.assertIn('结论',Chat(self.s).detail('fixture')['messages'][-1]['text'])
  json.dumps(remaining,allow_nan=False)
 def test_recover_after_tool_receipt_without_executing_tool_twice(self):
  from digital_life.application.autonomy.task_loop import TaskLoop
  self.project();engine=self.start();activity=self.send('检查一份材料');model=ReadSeveralFiles(count=1)
  intent=engine.think(activity,model)['action_id']
  with patch.object(TaskLoop,'advance',side_effect=TypeError("'<=' not supported between instances of 'NoneType' and 'str'")):
   with self.assertRaises(TypeError):engine.execute(intent)
  self.assertEqual(self.s.row('action_intents',intent)['state'],'succeeded')
  self.assertEqual(self.s.row('activities',activity)['state'],'running')
  self.assertEqual(TaskLoop(self.s).events(activity,'task_loop.observed'),[])
  engine.execute(intent)
  self.assertEqual(len(self.s.rows('action_attempts')),1)
  self.assertEqual(len(TaskLoop(self.s).events(activity,'task_loop.observed')),1)
  engine.think(activity,model)
  self.assertEqual(self.s.row('activities',activity)['state'],'completed')
  self.assertTrue(Chat(self.s).detail('fixture')['can_send'])
 def test_limited_mode_still_stops_and_shows_partial_results(self):
  self.save('budget',budget_enabled=True,tokens=8192);self.project();engine=self.start();activity=self.send('检查材料');model=ReadSeveralFiles()
  for _ in range(2):
   result=engine.think(activity,model);engine.execute(result['action_id'])
  self.assertEqual(self.s.row('activities',activity)['state'],'paused')
  status=[x['text'] for x in Chat(self.s).detail('fixture')['messages'] if x['role']=='status']
  self.assertTrue(any('已完成2次工具操作' in x and '任务尚未完成' in x for x in status))
 def test_explicit_root_name_survives_restart_and_manual_override(self):
  self.send('我觉得阿初还是缺了点，不如叫你“霖铃”吧，更像是一个名字')
  self.assertEqual(Names(self.s).current()['name'],'霖铃');same_id=self.s.instance_id
  reopened=Store(self.root)
  try:self.assertEqual(Names(reopened).current()['name'],'霖铃')
  finally:reopened.close()
  self.save('identity',name='新称呼')
  self.assertEqual(Names(self.s).current()['name'],'新称呼');self.assertEqual(self.s.instance_id,same_id)
  self.assertEqual(Names(self.s).adopt_existing()['name'],'新称呼')
 def test_history_adoption_is_idempotent_and_not_a_personality_change(self):
  with patch.object(Names,'observe',return_value=None):self.send('不如叫你“霖铃”吧')
  self.assertEqual(Names(self.s).current()['name'],'原初00')
  Names(self.s).adopt_existing();count=len(self.s.rows('runtime_events'));Names(self.s).adopt_existing()
  self.assertEqual(len(self.s.rows('runtime_events')),count)
  self.assertEqual(Names(self.s).current()['name'],'霖铃');self.assertEqual(len(self.s.rows('personality_change_records')),0)
 def test_examples_and_negative_names_are_not_commands(self):
  for text in ('请分析这句话：叫你“霖铃”','不要叫你“霖铃”','例如叫你“霖铃”','我叫“霖铃”'):
   self.assertIsNone(Names.proposed(text),text)
 def test_self_knowledge_has_off_switches_settings_and_source_paths(self):
  self.project();engine=self.start();activity=self.send('你的人格学习开启了吗？')
  request,p=engine.prepare(activity,ReadSeveralFiles());knowledge=p['self_knowledge']
  self.assertFalse(knowledge['features']['personality_growth']['enabled'])
  self.assertEqual(knowledge['budget']['mode'],'unlimited');self.assertTrue(knowledge['settings_page']['available'])
  self.assertFalse(knowledge['model']['continuation_used'])
  self.assertTrue(knowledge['settings_page']['root_account_required'])
  self.assertEqual(knowledge['budget']['single_request_attempt_limit'],3)
  for path in knowledge['project']['entry_files'].values():self.assertTrue(Path(path).is_file(),path)
  self.assertIn('直接读取',p['instructions'])
 def test_ordinary_account_cannot_change_the_instance_name(self):
  from digital_life.application.accounts.accounts import install,Accounts,public
  from digital_life.application.accounts.account_scope import audience
  install(self.root);account_store=Store(self.root);auth=Accounts(self.root,self.s.instance_id)
  try:
   principal=dict(public(auth.row(auth.root_id())),bootstrap=True)
   member=auth.provision(account_store,principal,dict(username='member',display_name='member',role='member',password='isolated-test-password'))['account']
   with audience(account_store,member['id']):
    Chat(account_store).send(member['thread_id'],dict(text='以后叫你“冒充名称”',idempotency_key='rename',expected_last_activity_id=None))
   self.assertEqual(Names(self.s).current()['name'],'原初00')
  finally:auth.close();account_store.close()
 def test_unlimited_does_not_bypass_user_stop_or_tool_permission(self):
  self.project();engine=self.start();activity=self.send('检查材料');self.c.stop('stop')
  with self.assertRaises(Forbidden):engine.think(activity,ReadSeveralFiles())
  from digital_life.application.lifecycle.project_access import ProjectAccess
  self.assertFalse(ProjectAccess(self.s).config().get('tools')==['project_read','project_write'])
