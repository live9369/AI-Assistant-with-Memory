"""Core directory capability and actual worker flow only; no external model."""
import json,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.runtime.engine import Engine
from digital_life.application.accounts.authorization import Policy
from digital_life.application.lifecycle.project_access import ProjectAccess
from digital_life.domain.contracts import Forbidden,sha

class ProjectTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.project=self.root/'project';self.project.mkdir()
  self.s=Store.prepare(self.root/'instance',model_config={'backend':'fixture','model':'fixture'});self.c=Control(self.s.root,self.s.instance_id)
  (self.s.root/'WAKE_DISABLED').unlink();self.c.resume('fixture');self.e=Engine(self.s);self.access=ProjectAccess(self.s)
 def tearDown(self):self.c.close();self.s.close();self.tmp.cleanup()
 def configure(self,auto=True):self.access.configure(str(self.project),self.s.config()['controller'],auto_approve=auto)
 def propose(self,action):
  class Model:
   name='fixture'
   def generate(inner,p):return {'schema_version':1,'action':action,'explanation':'本轮工具提案'}
  a=self.e.submit('修改指定文件','probe-'+str(len(self.s.rows('activities'))));return a,self.e.think(a,Model())
 def test_actual_worker_create_read_update_then_fresh_conclusion(self):
  self.configure();target=self.project/'hello.txt';target.write_text('before\n');inputs=[]
  class Model:
   name='fixture'
   def generate(inner,p):
    inputs.append(p);observations=p.get('task_loop',{}).get('observations',[])
    if not observations:action={'tool':'project_read','arguments':{'path':'hello.txt','start_line':1,'max_lines':20}}
    elif len(observations)==1:
     evidence=observations[-1]['receipt_snapshot']['evidence'];action={'tool':'project_write','arguments':{'path':'hello.txt','text':'after\n','expected_sha256':evidence['sha256']}}
    else:action={'tool':'wait','arguments':{'reason':'done'}}
    return {'schema_version':1,'action':action,'explanation':'本次已根据工具结果处理。'}
  a=self.e.submit('将 hello.txt 改成 after','loop');model=Model()
  for _ in range(3):
   r=self.e.think(a,model)
   if 'action_id' in r:self.e.execute(r['action_id'])
  self.assertEqual(target.read_text(),'after\n');self.assertEqual(self.s.row('activities',a)['state'],'completed')
  self.assertEqual(len(inputs),3);self.assertTrue(all(p['context_mode']=='fresh_request' for p in inputs));self.assertIn('diff',inputs[2]['task_loop']['observations'][-1]['receipt_snapshot']['evidence'])
  a,r=self.propose({'tool':'project_write','arguments':{'path':'new.txt','text':'created','expected_sha256':''}});self.assertEqual(self.e.execute(r['action_id'])['state'],'succeeded');self.assertEqual((self.project/'new.txt').read_text(),'created')
 def test_external_request_uses_user_channel_even_if_internal_sorts_first(self):
  with self.s.tx():self.s.insert('perception_channels',id='0'*32,kind='internal',capabilities=['text'],verification_method='fixture',state='available')
  a=self.e.submit('明确外部输入','external-channel');signal=self.s.row('perception_signals',self.s.row('activities',a)['trigger_event_id'])
  self.assertEqual(self.s.row('perception_channels',signal['channel_id'])['kind'],'user')
 def test_four_thoughts_respect_budget_and_do_not_randomly_ask(self):
  from digital_life.application.behavior.behavior_policy import BehaviorPolicy
  self.configure();self.c.stop('behavior-setup');BehaviorPolicy(self.s).configure(True,self.s.config()['controller']);self.c.resume('behavior-test')
  (self.project/'test.py').write_text('VALUE = "before"\n');inputs=[]
  class Model:
   name='fixture'
   def generate(inner,p):
    inputs.append(p);observations=p.get('task_loop',{}).get('observations',[])
    if len(observations)==0:action={'tool':'project_read','arguments':{'path':'test.py','start_line':1,'max_lines':20}}
    elif len(observations)==1:action={'tool':'project_edit','arguments':{'path':'test.py','old_text':'before','new_text':'after','expected_sha256':observations[-1]['receipt_snapshot']['evidence']['sha256']}}
    elif len(observations)==2:action={'tool':'project_check','arguments':{'path':'test.py','check':'python_syntax'}}
    else:action={'tool':'wait','arguments':{'reason':'complete'}}
    return {'schema_version':1,'action':action,'explanation':'本轮任务结果。'}
  a=self.e.submit('读取、修改和检查 test.py，然后报告','four-rounds')
  from digital_life.application.behavior.goal_regulation import GoalRegulation
  self.c.stop('regulation-setup');GoalRegulation(self.s).configure(True,self.s.config()['controller']);self.c.resume('regulation-test')
  from digital_life.application.services.states import States
  # Existing collector prepares the actual fresh local state, not fabricated measurements.
  from digital_life.application.telemetry.states import StateCollector
  StateCollector(self.s).collect()
  with patch('digital_life.application.behavior.behavior_policy.secrets.randbits',return_value=2**53-1):
   for _ in range(4):
    result=self.e.think(a,Model())
    if 'action_id' in result:self.e.execute(result['action_id'])
  self.assertEqual(self.s.row('activities',a)['state'],'completed');self.assertEqual(len(inputs),4)
  requests=self.s.db.execute('SELECT token_budget FROM thought_requests WHERE activity_id=? ORDER BY rowid',(a,)).fetchall()
  self.assertEqual([r[0] for r in requests],[4096,4096,4096,3712])
  account=self.s.db.execute('SELECT * FROM activity_budget_accounts WHERE activity_id=?',(a,)).fetchone();self.assertEqual((account['token_limit'],account['tool_call_limit'],account['attempt_limit']),(16000,8,8))
  events=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE activity_id=? AND event_type='behavior_policy.selected'",(a,)).fetchall()
  for r in events:
   value=self.s.read_artifact(r[0]);self.assertEqual(value['execution_constraint'],'explicit-authorized-project-task-v1');self.assertEqual(value['selected_index'],0)
   self.assertTrue(value['feature_snapshot']['features']);self.assertTrue(all(not c['eligible'] for c in value['candidates'][1:]))
 def test_project_budget_exhaustion_pauses_without_new_request(self):
  from digital_life.application.autonomy.task_loop import TaskLoop
  from digital_life.application.runtime.scheduling import Budget
  self.configure();a=self.e.submit('budget probe','budget-probe')
  with self.s.tx():
   self.e.transition(a,'running','fixture');TaskLoop(self.s).bind_project(a)
   self.s.db.execute('UPDATE activity_budget_accounts SET token_limit=500 WHERE activity_id=?',(a,))
   result=TaskLoop(self.s).advance(self.e,a,'budget-check')
  self.assertFalse(result['continued']);self.assertEqual(self.s.row('activities',a)['state'],'paused');self.assertEqual(len(self.s.rows('thought_requests')),0)
  self.assertIn('预算不足',result['message'])
 def test_edit_large_file_and_mkdir_with_real_worker(self):
  self.configure();target=self.project/'large.txt';target.write_text('prefix\n'+'x'*25000+'\nold block\n')
  before=target.read_bytes();a,r=self.propose({'tool':'project_edit','arguments':{'path':'large.txt','old_text':'old block','new_text':'new block','expected_sha256':sha(before)}})
  self.assertEqual(self.e.execute(r['action_id'])['state'],'succeeded');self.assertIn('new block',target.read_text());self.assertIn('x'*25000,target.read_text())
  a,r=self.propose({'tool':'project_mkdir','arguments':{'path':'docs'}});self.assertEqual(self.e.execute(r['action_id'])['state'],'succeeded');self.assertTrue((self.project/'docs').is_dir())
 def test_stale_hash_and_outside_paths_do_not_write(self):
  self.configure();target=self.project/'hello.txt';target.write_text('new owner value')
  for path,expected in [('hello.txt',sha('old')),('../outside.txt',''),('work/private.txt','')]:
   a,r=self.propose({'tool':'project_write','arguments':{'path':path,'text':'bad','expected_sha256':expected}})
   self.assertNotEqual(self.e.execute(r['action_id'])['state'],'succeeded')
  self.assertEqual(target.read_text(),'new owner value');self.assertFalse((self.root/'outside.txt').exists())
 def test_explicit_approval_and_revoke_before_dispatch(self):
  self.configure(False);a,r=self.propose({'tool':'project_write','arguments':{'path':'new.txt','text':'created','expected_sha256':''}})
  self.assertEqual(self.s.row('approval_requests',r['approval_id'])['decision'],'pending');self.assertFalse((self.project/'new.txt').exists())
  Policy(self.s).approve(r['approval_id'],self.s.config()['controller']);self.access.configure('.',self.s.config()['controller'],enabled=False)
  with self.assertRaises(Forbidden):self.e.execute(r['action_id'])
  self.assertFalse((self.project/'new.txt').exists())
 def test_named_syntax_check_does_not_execute_project_code(self):
  self.configure();(self.project/'sample.py').write_text('raise RuntimeError("must not execute")\n')
  a,r=self.propose({'tool':'project_check','arguments':{'path':'sample.py','check':'python_syntax'}})
  self.assertEqual(self.e.execute(r['action_id'])['state'],'succeeded')
  (self.project/'sample.py').write_text('def broken(\n')
  a,r=self.propose({'tool':'project_check','arguments':{'path':'sample.py','check':'python_syntax'}})
  self.assertEqual(self.e.execute(r['action_id'])['state'],'failed')
 def test_read_only_tool_subset_and_provider_schema(self):
  self.access.configure(str(self.project),self.s.config()['controller'],tools=['project_read','project_list'])
  self.assertEqual(self.access.context()['tools'],['project_read','project_list'])
  with self.assertRaises(Forbidden):self.access.resource('project_write')
  from digital_life.infrastructure.llm.schemas import schema_for
  absent=schema_for({})['properties']['action']['anyOf']
  self.assertFalse(any(v['properties']['tool']['const'].startswith('project_') for v in absent))
  present=schema_for({'project_access':self.access.context()})['properties']['action']['anyOf']
  self.assertEqual({v['properties']['tool']['const'] for v in present if v['properties']['tool']['const'].startswith('project_')},{'project_read','project_list'})
 def test_symlink_and_search(self):
  self.configure();(self.project/'hello.txt').write_text('find-me');(self.root/'secret').write_text('secret');(self.project/'link').symlink_to(self.root/'secret')
  a,r=self.propose({'tool':'project_read','arguments':{'path':'link','start_line':1,'max_lines':20}});self.assertEqual(self.e.execute(r['action_id'])['state'],'failed')
  a,r=self.propose({'tool':'project_search','arguments':{'path':'.','query':'find-me'}});self.e.execute(r['action_id']);event=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE event_type='task_loop.observed' AND activity_id=?",(a,)).fetchone();receipt=self.s.read_artifact(self.s.read_artifact(event[0])['receipt']);self.assertEqual(receipt['evidence']['matches'][0]['path'],'hello.txt')
if __name__=='__main__':unittest.main()
