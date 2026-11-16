"""T11 temporary instances; real workspace tools and independent verifiers."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
from digital_life.application.autonomy.exploration import Exploration
from digital_life.application.accounts.authorization import Policy
from digital_life.application.services.commitments import Commitments
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.autonomy.task_loop import TaskLoop
from digital_life.domain.contracts import utc,identifier,ContractError,Forbidden,Conflict,ToolResult
from digital_life.infrastructure.tools.workspace import registry

class Model:
 name='isolated-agenda'
 def __init__(self,action=None):self.inputs=[];self.action=action or {'tool':'write_note','arguments':{'path':'notes/result.txt','text':'delivered'}}
 def generate(self,p):self.inputs.append(copy.deepcopy(p));return {'schema_version':1,'explanation':'fixture','action':self.action}

class AgendaTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'isolated';self.s=Store.prepare(self.root);self.addCleanup(lambda:self.s.close());self.e=Engine(self.s);self.a=AutonomyAgenda(self.s);self.actor=self.s.config()['controller'];self.x=Exploration(self.s)
  (self.root/'workspace/notes').mkdir();(self.root/'workspace/notes/count.txt').write_text('count=2')
 def enable(self):self.a.configure(True,self.actor)
 def unlock(self):
  (self.root/'WAKE_DISABLED').unlink(missing_ok=True);c=Control(self.root,self.s.instance_id);c.resume(identifier());c.close();Policy(self.s).mode('open',['write_note','read_file','list_files'],self.actor)
 def promise(self,**changes):
  spec={'content':'deliver a note','start_at':utc(-2),'due_at':utc(600),'verification':{'kind':'file_contains','path':'notes/result.txt','text':'delivered'},'key':'promise','actor':self.actor};spec.update(changes);return self.a.promise(**spec)
 def start(self):
  self.enable();p=self.promise();self.unlock();activity=self.a.tick(self.e);return p,activity
 def execute(self,activity,model=None,backend=None):
  self.e.think(activity,model or Model());intent=self.s.rows('action_intents')[-1];return self.e.execute(intent['id'],backend or (lambda a,r,o:registry().invoke(a,r,o)))
 def state(self,p):return self.s.row('commitment_items',p['commitment'])['state']
 def question(self,qid='q',**changes):
  ev=self.s.evidence(artifact=self.s.artifact({'authored':'source'}))
  q={'id':qid,'question':'What does notes/count.txt say?','verification':'read notes/count.txt','expected_gain':.5,'cost':.1,'evidence_refs':[ev],'state':'candidate','due_at':utc(-1),'visits':0};q.update(changes);self.x.record(q);return q
 def interest(self,qid='q',**changes):
  spec={'question_id':qid,'topic':'counts','affinity':1.,'path':'notes/count.txt','contains':'count=2','key':qid,'actor':self.actor};spec.update(changes);return self.a.question(**spec)
 def explore(self,qid='q'):
  self.x.configure(self.actor,True,max_activities=2);self.question(qid);self.interest(qid);self.unlock();return self.x.tick(self.e)
 def read(self,activity):
  from test_exploration import ExploringModel
  return self.execute(activity,ExploringModel())
 def test_default_disabled_and_no_added_context(self):
  self.assertFalse(self.a.config()['enabled']);activity=self.e.submit('hello','one');self.assertIsNone(self.a.context(activity))
  with self.assertRaises(Forbidden):self.promise()
 def test_authority_and_stop_configuration_gate(self):
  with self.assertRaises(Forbidden):self.a.configure(True,'model')
  with self.assertRaises(ContractError):self.a.configure(1,self.actor)
  self.enable();self.unlock()
  with self.assertRaises(Conflict):self.a.configure(False,self.actor)
  with self.assertRaises(Forbidden):self.promise(actor='model')
 def test_invalid_timestamps_and_verifier(self):
  self.enable()
  for changes in ({'start_at':'tomorrow'},{'due_at':'2026-01-01T00:00:00.000Z'},{'start_at':utc(900)},{'verification':{'kind':'true'}},{'verification':{'kind':'file_contains','path':'../secret','text':'x'}},{'max_rounds':True},{'max_rounds':4}):
   with self.assertRaises((ContractError,Forbidden)):self.promise(**changes)
 def test_idempotency_and_changed_key_content(self):
  self.enable();p=self.promise();spec=p['spec'];self.assertEqual(self.a.promise(**{k:v for k,v in spec.items() if k!='key'},key='promise',actor=self.actor),p)
  with self.assertRaises(Conflict):self.promise(content='different',start_at=spec['start_at'],due_at=spec['due_at'])
  self.assertEqual(len(self.s.rows('commitment_items')),1)
 def test_future_start_and_persistent_queue(self):
  self.enable();p=self.promise(start_at=utc(60));self.unlock();self.assertIsNone(self.a.tick(self.e));self.assertEqual(self.state(p),'active');self.assertEqual(self.a.status()['wait_state'],'waiting-deadline');self.assertEqual(self.a.status()['next_due'],p['spec']['start_at'])
  jobs=[r for r in self.s.rows('jobs') if r['target_ref']==p['commitment']];self.assertEqual(sorted(r['due_at'] for r in jobs),sorted([p['spec']['start_at'],p['spec']['due_at']]))
 def test_locked_runtime_never_starts(self):
  self.enable();self.promise()
  with self.assertRaises(Forbidden):self.a.tick(self.e)
  self.assertEqual(self.s.rows('thought_requests'),[])
 def test_user_work_has_priority(self):
  self.enable();p=self.promise();self.e.submit('user task','user');self.unlock();self.assertIsNone(self.a.tick(self.e));self.assertIsNone(self.a.bound(p['commitment']))
 def test_starts_before_deadline_once_and_restart(self):
  p,activity=self.start();self.assertTrue(activity);self.assertEqual(self.a.bound(p['commitment'])['activity'],activity);self.assertIsNone(self.a.tick(self.e));self.s.close();self.s=Store(self.root);self.a=AutonomyAgenda(self.s);self.e=Engine(self.s);self.assertIsNone(self.a.tick(self.e));self.assertEqual(len(self.s.rows('commitment_goal_links')),1);self.assertEqual(self.s.integrity()['foreign_keys'],[])
 def test_success_requires_independent_verification(self):
  p,activity=self.start();model=Model();result=self.execute(activity,model);self.assertTrue(result['completed']);self.assertEqual(self.state(p),'fulfilled');self.assertEqual(model.inputs[0]['autonomy_agenda']['commitment']['commitment'],p['commitment']);self.assertEqual(len(self.a.events('fulfilled')),1);self.a.settle(self.e);self.assertEqual(len(self.a.events('fulfilled')),1)
 def test_tool_success_without_goal_is_not_fulfillment(self):
  p,activity=self.start();result=self.execute(activity,Model({'tool':'read_file','arguments':{'path':'notes/count.txt'}}));self.assertFalse(result['completed']);self.assertEqual(self.state(p),'active')
 def test_unknown_effect_pauses_not_fulfills(self):
  p,activity=self.start();self.execute(activity,backend=lambda a,r,o:ToolResult('received','unknown','fail',{},'unknown'));self.assertEqual(self.state(p),'active');self.assertEqual(self.s.row('activities',activity)['state'],'paused')
 def test_manual_fulfillment_cannot_bypass_verifier(self):
  p,activity=self.start();proof=self.s.evidence(artifact=self.s.artifact({'claim':'done'}))
  with self.assertRaises(ContractError):Commitments(self.s).transition(p['commitment'],'fulfilled',p['signal'],proof)
 def test_deadline_marks_violation_and_cancels_activity(self):
  p,activity=self.start()
  with patch('digital_life.application.autonomy.autonomy_agenda.utc',return_value=utc(1200)):self.a.settle(self.e)
  self.assertEqual(self.state(p),'violated');self.assertEqual(self.s.row('activities',activity)['state'],'cancelled')
  self.assertEqual(len(self.a.events('violated')),1)
 def test_late_completed_goal_is_not_timely_fulfillment(self):
  p,activity=self.start()
  with patch('digital_life.application.autonomy.autonomy_agenda.utc',return_value=utc(1200)):self.execute(activity)
  self.assertEqual(self.state(p),'violated');self.assertEqual(self.a.events('fulfilled'),[])
 def test_release_cancels_work_and_is_idempotent(self):
  p,activity=self.start();self.a.release(p['commitment'],self.actor);self.a.release(p['commitment'],self.actor);self.assertEqual(self.state(p),'released');self.assertEqual(self.s.row('activities',activity)['state'],'cancelled');self.assertFalse(any(j['state']=='queued' and j['target_ref']==p['commitment'] for j in self.s.rows('jobs')))
 def test_release_before_start_and_terminal_protection(self):
  self.enable();p=self.promise(start_at=utc(60));self.a.release(p['commitment'],self.actor);self.unlock();self.assertIsNone(self.a.tick(self.e));self.assertEqual(self.state(p),'released')
 def test_disable_does_not_erase_existing_obligations(self):
  self.enable();p=self.promise();self.a.configure(False,self.actor);self.unlock();activity=self.a.tick(self.e);self.execute(activity);self.assertEqual(self.state(p),'fulfilled')
 def test_managed_due_job_does_not_create_second_activity(self):
  p,activity=self.start()
  for _ in range(5):self.e.process_one(Model(),lambda a,r,o:registry().invoke(a,r,o))
  self.assertEqual(len(self.s.rows('commitment_goal_links')),1);self.assertEqual(self.state(p),'fulfilled')
 def test_interests_validation_idempotency_and_authority(self):
  self.enable();self.question();i=self.interest();self.assertEqual(self.interest(),i)
  for change in ({'affinity':float('nan')},{'affinity':True},{'path':'../secret'},{'path':'missing.txt'},{'question_id':'missing'}):
   with self.assertRaises((ContractError,Forbidden)):self.interest(**change)
  with self.assertRaises(Conflict):self.interest(topic='changed')
  with self.assertRaises(Forbidden):self.interest(actor='model')
 def test_interest_changes_legal_candidate_ranking(self):
  self.enable();q=self.question('a');other=self.question('z');self.interest('z');self.assertGreater(self.a.score(other),self.a.score(q));self.x.configure(self.actor,True);self.unlock();activity=self.x.tick(self.e);self.assertEqual(self.x.binding(activity)['question_id'],'z')
 def test_disabled_interest_leaves_original_scoring(self):
  self.enable();q=self.question();self.interest();self.a.configure(False,self.actor);self.assertEqual(self.a.score(q),q['expected_gain']-q['cost'])
 def test_real_read_measures_gain_and_duplicate_result(self):
  self.enable();activity=self.explore();self.read(activity);rows=self.a.events('measured');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['gain'],1);self.assertTrue(rows[0]['value']);self.assertEqual(self.a.context(activity)['declared_interest']['topic'],'counts');outcome=self.x.observations(activity)[0];self.a.observe(activity,outcome);self.assertEqual(len(self.a.events('measured')),1)
 def test_unknown_or_unmatched_measurement_is_null(self):
  self.enable();activity=self.explore();from test_exploration import ExploringModel
  self.execute(activity,ExploringModel(),lambda a,r,o:ToolResult('received','unknown','fail',{},'unknown'));self.assertIsNone(self.a.events('measured')[-1]['gain'])
 def test_changed_resource_does_not_count_as_current_observation(self):
  self.enable();activity=self.explore();self.read(activity);outcome=self.x.observations(activity)[0];original=self.a.events
  self.a.events=lambda kind:[] if kind=='measured' else original(kind)
  # Test projection against an old receipt after a source change.
  (self.root/'workspace/notes/count.txt').write_text('count=3');self.a.observe(activity,outcome);self.assertIsNone(original('measured')[-1]['gain'])
 def test_thought_context_change_is_rejected(self):
  p,activity=self.start();_,payload=self.e.prepare(activity,Model());payload['autonomy_agenda']['policy_enabled']=False
  with self.assertRaises(Forbidden):self.a.check(payload,activity)
 def test_wait_status_starts_no_inference(self):
  self.assertEqual(self.a.status()['wait_state'],'idle');self.assertFalse(self.a.status()['inference_started']);self.assertEqual(self.s.rows('thought_requests'),[])

 def test_cross_question_same_content_gain_zero_and_new_content_gain_one(self):
  from test_exploration import ExploringModel
  self.enable();activity=self.explore();self.read(activity);self.e.think(activity,ExploringModel())
  self.question('second');self.interest('second');(self.root/'workspace/notes/count.txt').write_text('count=2')
  with patch('digital_life.application.autonomy.exploration.utc',side_effect=lambda seconds=0:utc(2000+seconds)):second=self.x.tick(self.e)
  self.read(second);self.assertEqual(self.a.events('measured')[-1]['gain'],0);self.e.think(second,ExploringModel())
  # A new authorized generation resets only activity budget, not measurement history.
  self.x.configure(self.actor,True,max_activities=1);self.question('third');self.interest('third');(self.root/'workspace/notes/count.txt').write_text('count=3');third=self.x.tick(self.e);self.read(third)
  self.assertEqual(self.a.events('measured')[-1]['gain'],1);self.assertFalse(self.a.events('measured')[-1]['value']);self.assertEqual([m['gain'] for m in self.a.events('measured')],[1,0,1])
 def test_foreign_outcome_cannot_be_used_as_measurement(self):
  self.enable();activity=self.explore()
  with self.assertRaises(ContractError):self.a.observe(activity,{'result':'invented','state':'succeeded','evidence':'invented'})
 def test_agenda_does_not_extend_exploration_budget(self):
  from test_exploration import ExploringModel
  self.enable();self.x.configure(self.actor,True,max_activities=1);self.question();self.interest();self.unlock();activity=self.x.tick(self.e);self.read(activity);self.e.think(activity,ExploringModel());self.assertIsNone(self.x.tick(self.e));self.assertEqual(self.a.status()['wait_state'],'budget-exhausted')
 def test_cli_configuration_and_spec_registration(self):
  import argparse
  from digital_life.entrypoints.growth import parsers,handle
  parser=argparse.ArgumentParser();parsers(parser.add_subparsers(dest='command'))
  result=handle(self.s,parser.parse_args(['autonomy-agenda','enable']));self.assertTrue(result['enabled'])
  spec={'content':'deliver','start_at':utc(60),'due_at':utc(120),'verification':{'kind':'file_contains','path':'notes/result.txt','text':'delivered'}};path=self.root/'spec.json';path.write_text(json.dumps(spec))
  result=handle(self.s,parser.parse_args(['autonomy-agenda','promise','--spec',str(path),'--key','cli']));self.assertEqual(self.state(result),'active')
  status=handle(self.s,parser.parse_args(['autonomy-agenda','status']));self.assertEqual(len(status['commitments']),1)
 def test_expired_unstarted_obligation_never_executes(self):
  self.enable();p=self.promise(start_at=utc(30));self.unlock()
  with patch('digital_life.application.autonomy.autonomy_agenda.utc',return_value=utc(1200)):self.assertIsNone(self.a.tick(self.e))
  self.assertEqual(self.state(p),'violated');self.assertIsNone(self.a.bound(p['commitment']));self.assertEqual(self.s.rows('thought_requests'),[])
 def test_sleep_handoff_retains_future_promise_and_aborts_on_input(self):
  self.enable();p=self.promise(start_at=utc(60));self.unlock();c=Control(self.root,self.s.instance_id)
  try:
   with c.tx():deployment=c.insert('deployments',release='fixture',build_hash='fixture',schema_min=2,schema_max=2,state='active')
   identity=c.begin_run(deployment);handoff=c.prepare_sleep(self.s,identity)
   wake=self.s.rows('instance_wake_state')[0];self.assertEqual(wake['acknowledged_due_at'],p['spec']['start_at']);self.assertEqual(c.commit_sleep(self.s,handoff)['phase'],'committed')
   handoff=c.prepare_sleep(self.s,identity);c.accept_inbound('fixture','new',{'text':'user arrived'},'controller');self.assertEqual(c.commit_sleep(self.s,handoff)['phase'],'aborted');c.finish_run(identity)
  finally:c.close()
 def test_ready_work_blocks_sleep_handoff(self):
  p,activity=self.start();c=Control(self.root,self.s.instance_id)
  try:
   with c.tx():deployment=c.insert('deployments',release='fixture',build_hash='fixture',schema_min=2,schema_max=2,state='active')
   identity=c.begin_run(deployment)
   with self.assertRaises(Conflict):c.prepare_sleep(self.s,identity)
   c.finish_run(identity)
  finally:c.close()
 def test_historical_thought_panel_exposes_commitment_snapshot(self):
  from digital_life.application.monitoring.thought_inspection import ThoughtInspection
  p,activity=self.start();request,payload=self.e.prepare(activity,Model());detail=ThoughtInspection(self.s).detail(request['id']);items=[i for f in detail['features'] for i in f['items'] if i['field']=='autonomy_agenda'];self.assertEqual(items[0]['state'],'provided');self.assertEqual(items[0]['value'],payload['autonomy_agenda']);self.assertTrue(detail['read_only'])
 def test_fulfilled_obligation_cannot_be_released_or_rewritten(self):
  p,activity=self.start();self.execute(activity)
  with self.assertRaises(Conflict):self.a.release(p['commitment'],self.actor)
  self.assertEqual(self.state(p),'fulfilled');self.assertEqual(len(self.s.rows('commitment_goal_links')),1)
