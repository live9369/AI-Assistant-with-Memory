"""T12 isolated health repair and source-update closure; no formal instance use."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from digital_life.infrastructure.persistence.sqlite_store import Store,PROJECT
from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
from digital_life.application.lifecycle.source_updates import SourceUpdates
from digital_life.application.memory.memory_quality import MemoryQuality,INDEX
from digital_life.application.runtime.engine import Engine
from digital_life.application.lifecycle.control_plane import Control,Releases
from digital_life.application.accounts.authorization import Policy
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,identifier,utc

class Model:
 name='maintenance-fixture'
 def __init__(self,action=None):self.inputs=[];self.action=action or {'tool':'wait','arguments':{'reason':'review'}}
 def generate(self,p):self.inputs.append(p);return {'schema_version':1,'explanation':'fixture','action':self.action}

class MaintenanceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'instance';self.s=Store.prepare(self.root);self.addCleanup(lambda:self.s.close());self.m=SelfMaintenance(self.s);self.u=SourceUpdates(self.s);self.actor=self.s.config()['controller'];self.e=Engine(self.s)
 def enable(self,**options):return self.m.configure(True,self.actor,**options)
 def unlock(self):
  (self.root/'WAKE_DISABLED').unlink(missing_ok=True);c=Control(self.root,self.s.instance_id)
  try:c.resume(identifier())
  finally:c.close()
 def missing(self):shutil.rmtree(self.root/'workspace')
 def baseline(self):
  c=Control(self.root,self.s.instance_id)
  try:
   d=Releases(c).stage(PROJECT);Releases(c).activate(d,lambda p:{'ready':True,'schema_compatible':True});return d
  finally:c.close()
 def proposal(self,base=None,**changes):
  spec={'base_deployment':base or self.baseline(),'changes':{'digital_life/t12_probe_marker.py':'VALUE = 12\n'},'reason':'isolated compatibility test','key':'test','actor':self.actor};spec.update(changes);return self.u.propose(**spec)
 def test_default_disabled_no_request_or_maintenance(self):
  self.assertIsNone(self.m.tick());self.assertIsNone(self.m.context());a=self.e.submit('hello','one');self.unlock();_,p=self.e.prepare(a,Model());self.assertNotIn('self_maintenance',p);self.assertEqual(self.m.events('diagnosed'),[])
 def test_configuration_authority_types_and_running_stop_gate(self):
  with self.assertRaises(Forbidden):self.m.configure(True,'model')
  for options in ({'max_repairs':0},{'max_repairs':True},{'auto_repair':1}):
   with self.assertRaises(ContractError):self.enable(**options)
  self.enable();self.unlock()
  with self.assertRaises(Conflict):self.m.configure(False,self.actor)
 def test_unknown_is_preserved_and_diagnosis_does_not_infer_model_quality(self):
  report=self.m.diagnose();self.assertEqual(report['state'],'unknown');self.assertEqual(report['dimensions']['cognition']['state'],'unknown');self.assertEqual(report['dimensions']['model_quality']['state'],'unknown');self.assertEqual(report['dimensions']['memory_index']['state'],'not_applicable');self.assertEqual(self.s.rows('thought_attempts'),[])
 def test_workspace_restoration_independently_verified_without_data_loss(self):
  self.enable();a=self.e.submit('preserved history','one');before=[dict(r) for r in self.s.rows('memory_revisions')];identity=self.s.instance_id;self.missing();plan=self.m.plan('restore_workspace','p',self.actor);self.assertFalse((self.root/'workspace').exists());result=self.m.repair(plan['id'],self.actor);self.assertTrue(result['passed']);self.assertTrue((self.root/'workspace').is_dir());self.assertEqual(before,[dict(r) for r in self.s.rows('memory_revisions')]);self.assertEqual(identity,self.s.instance_id);self.assertEqual(self.s.row('activities',a)['state'],'pending');self.assertEqual(self.m.repair(plan['id'],self.actor)['id'],result['id']);self.assertEqual(self.m.remaining(),2)
 def test_plan_idempotency_and_kind_key_conflict(self):
  self.enable();self.missing();p=self.m.plan('restore_workspace','same',self.actor);self.assertEqual(self.m.plan('restore_workspace','same',self.actor)['id'],p['id'])
  with self.assertRaises(Conflict):self.m.plan('rebuild_index','same',self.actor)
  with self.assertRaises(ContractError):self.m.plan('delete_memories','bad',self.actor)
 def test_symlink_and_file_workspace_not_repaired(self):
  self.enable();self.missing();target=Path(self.tmp.name)/'outside';target.mkdir();(self.root/'workspace').symlink_to(target,target_is_directory=True)
  with self.assertRaises(Conflict):self.m.plan('restore_workspace','symlink',self.actor)
  self.assertEqual(self.m.diagnose()['dimensions']['workspace']['state'],'degraded');(self.root/'workspace').unlink();(self.root/'workspace').write_text('do not replace')
  with self.assertRaises(Conflict):self.m.plan('restore_workspace','file',self.actor)
  self.assertEqual((self.root/'workspace').read_text(),'do not replace')
 def test_stale_facts_configuration_and_expiry_reject_execution(self):
  self.enable();self.missing();p=self.m.plan('restore_workspace','p',self.actor);(self.root/'workspace').mkdir()
  with self.assertRaises(Conflict):self.m.repair(p['id'],self.actor)
  self.missing();self.enable()
  with self.assertRaises(Conflict):self.m.repair(p['id'],self.actor)
  p=self.m.plan('restore_workspace','new',self.actor)
  with patch('digital_life.application.lifecycle.self_maintenance.utc',return_value=utc(600)):
   with self.assertRaises(Conflict):self.m.repair(p['id'],self.actor)
  self.assertEqual(self.m.remaining(),3)
 def test_budget_is_persistent_and_exhaustion_blocks_repairs(self):
  self.enable(max_repairs=1);self.missing();p=self.m.plan('restore_workspace','one',self.actor);self.assertTrue(self.m.repair(p['id'],self.actor)['passed']);self.missing();p=self.m.plan('restore_workspace','two',self.actor)
  with self.assertRaises(Conflict):self.m.repair(p['id'],self.actor)
  self.s.close();self.s=Store(self.root);self.m=SelfMaintenance(self.s);self.assertEqual(self.m.remaining(),0)
 def test_failed_mutation_consumes_attempt_and_does_not_retry(self):
  self.enable();self.missing();p=self.m.plan('restore_workspace','p',self.actor)
  original=Path.mkdir
  def fail(path,*a,**kw):
   if path.resolve()==self.s.root/'workspace':raise OSError('fixture')
   return original(path,*a,**kw)
  with patch.object(Path,'mkdir',fail):result=self.m.repair(p['id'],self.actor)
  self.assertFalse(result['passed']);self.assertEqual(self.m.remaining(),2);again=self.m.repair(p['id'],self.actor);self.assertEqual(result['id'],again['id']);self.assertFalse((self.root/'workspace').exists())
 def test_missing_and_corrupt_index_rebuild_preserves_memories(self):
  self.enable();q=MemoryQuality(self.s);q.configure(True,self.actor);a=self.e.submit('remember liwei','one');before=[dict(r) for r in self.s.rows('memory_revisions')];self.assertEqual(self.m.index_state()['state'],'degraded');p=self.m.plan('rebuild_index','one',self.actor);self.assertTrue(self.m.repair(p['id'],self.actor)['passed']);(self.root/INDEX).write_bytes(b'not SQLite');self.assertEqual(self.m.index_state()['state'],'degraded');p=self.m.plan('rebuild_index','two',self.actor);self.assertTrue(self.m.repair(p['id'],self.actor)['passed']);self.assertEqual(before,[dict(r) for r in self.s.rows('memory_revisions')])
 def test_index_symlink_and_source_changed_reject_repair(self):
  self.enable();MemoryQuality(self.s).configure(True,self.actor);p=self.m.plan('rebuild_index','one',self.actor);self.e.submit('new source','source')
  with self.assertRaises(Conflict):self.m.repair(p['id'],self.actor)
  target=Path(self.tmp.name)/'outside';target.write_text('untouched');(self.root/INDEX).symlink_to(target)
  with self.assertRaises(Conflict):self.m.plan('rebuild_index','two',self.actor)
  self.assertEqual(target.read_text(),'untouched')
 def test_automatic_tick_obeys_stop_interval_opt_in_and_budget(self):
  self.enable(auto_repair=True,max_repairs=1);self.missing()
  with self.assertRaises(Forbidden):self.m.tick()
  self.unlock();result=self.m.tick();self.assertTrue(result['passed']);self.assertIsNone(self.m.tick());self.missing()
  with patch('digital_life.application.lifecycle.self_maintenance.utc',side_effect=lambda seconds=0:utc(60+seconds)):self.m.tick()
  self.assertFalse((self.root/'workspace').exists());self.assertEqual(self.m.remaining(),0)
 def test_manual_mode_does_not_auto_repair_and_live_manual_operation_rejected(self):
  self.enable();self.missing();self.unlock();self.m.tick();self.assertFalse((self.root/'workspace').exists());p=self.m.plan('restore_workspace','one',self.actor)
  with self.assertRaises(Conflict):self.m.repair(p['id'],self.actor)
 def test_core_damage_blocks_repair_and_remains_degraded(self):
  self.enable();self.missing();facts=self.m.facts();facts['identity']=False
  with patch.object(self.m,'facts',return_value=facts):
   with self.assertRaises(Forbidden):self.m.plan('restore_workspace','one',self.actor)
   self.assertEqual(self.m.diagnose()['dimensions']['identity']['state'],'degraded')
 def test_thought_snapshot_and_configuration_staleness(self):
  self.enable();self.m.diagnose();a=self.e.submit('health status','one');self.unlock();_,p=self.e.prepare(a,Model());self.assertIn('self_maintenance',p);self.assertEqual(p['self_maintenance']['lifecycle_authority'],'CLI only');p['self_maintenance']['configuration']='changed'
  with self.assertRaises(Forbidden):self.m.check(p)
 def test_cli_configuration_plan_and_status(self):
  from digital_life.entrypoints.growth import parsers,handle
  parser=argparse.ArgumentParser();parsers(parser.add_subparsers(dest='command'));self.assertTrue(handle(self.s,parser.parse_args(['maintenance','enable']))['enabled']);self.missing();p=handle(self.s,parser.parse_args(['maintenance','plan','--kind','restore_workspace','--key','cli']));self.assertTrue(handle(self.s,parser.parse_args(['maintenance','repair','--plan',p['id']]))['passed']);self.assertIn('source_updates',handle(self.s,parser.parse_args(['maintenance','status'])))
 def test_proposal_validation_authority_and_stale_baseline(self):
  self.enable();base=self.baseline()
  with self.assertRaises(Forbidden):self.proposal(base,actor='model')
  with self.assertRaises(Conflict):self.proposal('missing')
  for changes in ({'../bad.py':'x=1'},{'digital_life/../../bad.py':'x=1'},{'digital_life/.hidden.py':'x=1'},{'digital_life/a.py':None},{'digital_life/a.py':'a'*70000},{'digital_life/a.txt':'x'}):
   with self.assertRaises((ContractError,Forbidden,SyntaxError)):self.proposal(base,changes=changes)
  with self.assertRaises(SyntaxError):self.proposal(base,changes={'digital_life/bad.py':'def invalid('})
 def test_proposal_idempotency_and_no_live_source_mutation(self):
  self.enable();base=self.baseline();p=self.proposal(base);self.assertEqual(self.proposal(base),p)
  with self.assertRaises(Conflict):self.proposal(base,reason='changed')
  self.assertFalse((PROJECT/'digital_life/t12_probe_marker.py').exists());self.assertFalse((self.root/'releases'/self.u.active()['release']/'digital_life/t12_probe_marker.py').exists())
 def test_build_is_frozen_idempotent_and_does_not_activate(self):
  self.enable();base=self.baseline();p=self.proposal(base);b=self.u.build(p['id'],self.actor);self.assertEqual(self.u.build(p['id'],self.actor)['deployment'],b['deployment']);self.assertEqual(self.u.active()['id'],base);self.assertTrue((self.root/'releases'/b['release']/'digital_life/t12_probe_marker.py').is_file());self.assertTrue((self.root/'WAKE_DISABLED').exists());self.assertEqual(self.s.rows('thought_requests'),[])
 def test_candidate_actual_probe_passes_without_formal_wake(self):
  self.enable();base=self.baseline();p=self.proposal(base);b=self.u.build(p['id'],self.actor);before=[dict(r) for r in self.s.rows('memory_revisions')];result=self.u.validate(p['id'],self.actor);self.assertTrue(result['passed'],result);self.assertEqual(self.u.active()['id'],base);self.assertEqual(before,[dict(r) for r in self.s.rows('memory_revisions')]);self.assertTrue((self.root/'WAKE_DISABLED').exists());self.assertEqual(self.s.rows('thought_requests'),[]);self.u.assert_deployable(b['deployment'])
 def test_candidate_runtime_import_failure_is_not_certified(self):
  self.enable();p=self.proposal(changes={'digital_life/application/autonomy/task_loop.py':"raise RuntimeError('isolated candidate failure')\n"});self.u.build(p['id'],self.actor);result=self.u.validate(p['id'],self.actor);self.assertFalse(result['passed']);self.assertEqual(self.u.active()['id'],p['base_deployment'])
 def test_candidate_timeout_and_unvalidated_deployment_gate(self):
  self.enable();p=self.proposal();b=self.u.build(p['id'],self.actor)
  with self.assertRaises(Forbidden):self.u.assert_deployable(b['deployment'])
  import subprocess
  with patch('digital_life.infrastructure.processes.candidate_sandbox.CandidateSandbox.run',side_effect=subprocess.TimeoutExpired('probe',1)):result=self.u.validate(p['id'],self.actor,timeout=1)
  self.assertFalse(result['passed']);self.assertEqual(result['error'],'TimeoutExpired')
 def test_candidate_incompatible_schema_is_rejected(self):
  self.enable();p=self.proposal(changes={'digital_life/resources/release.json':'{"schema_min":3,"schema_max":3}'});self.u.build(p['id'],self.actor)
  with self.assertRaises(Conflict):self.u.validate(p['id'],self.actor)
 def test_fake_probe_success_without_artifacts_is_rejected(self):
  self.enable();p=self.proposal();self.u.build(p['id'],self.actor)
  with patch('digital_life.infrastructure.processes.candidate_sandbox.CandidateSandbox.run',return_value=type('R',(),{'returncode':0,'stdout':b'passed','stderr':b'','isolation':{'state':'passed'}})()):result=self.u.validate(p['id'],self.actor)
  self.assertFalse(result['passed'])
 def test_real_authorized_write_note_creates_auditable_source_proposal(self):
  self.enable();base=self.baseline();self.unlock();Policy(self.s).mode('open',['write_note'],self.actor);spec={'base_deployment':base,'changes':{'digital_life/t12_probe_marker.py':'VALUE=12\n'},'reason':'model fixture proposal'};model=Model({'tool':'write_note','arguments':{'path':'maintenance/update-one.json','text':json.dumps(spec)}});a=self.e.submit('propose improvement','one');self.e.think(a,model);intent=self.s.rows('action_intents')[-1];self.e.execute(intent['id']);proposals=self.u.events('proposed');self.assertEqual(len(proposals),1);self.assertEqual(proposals[0]['source']['intent'],intent['id']);self.assertEqual(self.u.active()['id'],base);self.assertEqual(self.u.events('built'),[])
 def test_invalid_model_proposal_does_not_change_successful_tool_outcome(self):
  self.enable();base=self.baseline();self.unlock();Policy(self.s).mode('open',['write_note'],self.actor);a=self.e.submit('invalid proposal','one');self.e.think(a,Model({'tool':'write_note','arguments':{'path':'maintenance/update-invalid.json','text':'{"bad":"envelope"}'}}));intent=self.s.rows('action_intents')[-1];outcome=self.e.execute(intent['id']);self.assertEqual(outcome['state'],'succeeded');self.assertTrue(self.u.events('captured')[-1]['rejected']);self.assertEqual(self.u.events('proposed'),[])
 def test_package_file_set_and_cached_release_tampering_are_rejected(self):
  base=self.baseline();c=Control(self.root,self.s.instance_id)
  try:
   path=Releases(c).verify(base);extra=path/'digital_life/untracked.py';extra.write_text('EXTRA=1')
   with self.assertRaises(ContractError):Releases(c).verify(base)
   with self.assertRaises(ContractError):Releases(c).stage(PROJECT)
   extra.unlink();(path/'digital_life/__init__.py').write_text('TAMPERED=True')
   with self.assertRaises(ContractError):Releases(c).verify(base)
  finally:c.close()
 def test_crash_after_mutation_never_replays_attempt(self):
  self.enable();self.missing();p=self.m.plan('restore_workspace','crash',self.actor)
  with patch.object(self.m,'diagnose',side_effect=RuntimeError('simulated interruption')):
   with self.assertRaises(RuntimeError):self.m.repair(p['id'],self.actor)
  self.assertEqual(self.m.remaining(),2)
  with self.assertRaises(Conflict):self.m.repair(p['id'],self.actor)
  self.assertTrue((self.root/'workspace').is_dir())
 def test_user_stop_between_plan_and_automatic_effect_blocks_repair(self):
  self.enable(auto_repair=True);self.missing();self.unlock();p=self.m.plan('restore_workspace','pending',self.actor);c=Control(self.root,self.s.instance_id)
  try:c.stop('late-stop')
  finally:c.close()
  with self.assertRaises(Forbidden):self.m.repair(p['id'],self.actor,_automatic=True)
  self.assertFalse((self.root/'workspace').exists());self.assertEqual(self.m.remaining(),3)
 def test_model_proposal_does_not_bypass_tool_approval(self):
  self.enable();base=self.baseline();self.unlock();a=self.e.submit('request source improvement','one');spec={'base_deployment':base,'changes':{'digital_life/t12_probe_marker.py':'VALUE=12\n'},'reason':'approval required'};self.e.think(a,Model({'tool':'write_note','arguments':{'path':'maintenance/update-pending.json','text':json.dumps(spec)}}));self.assertEqual(self.u.events('proposed'),[]);intent=self.s.rows('action_intents')[-1]
  with self.assertRaises(Forbidden):self.e.execute(intent['id'])
  self.assertFalse((self.root/'workspace/maintenance/update-pending.json').exists())
 def test_candidate_baseline_change_blocks_build_and_validation(self):
  self.enable();base=self.baseline();p=self.proposal(base);self.u.build(p['id'],self.actor);c=Control(self.root,self.s.instance_id)
  try:
   other=Releases(c).stage(PROJECT);Releases(c).activate(other,lambda path:{'ready':True,'schema_compatible':True})
  finally:c.close()
  with self.assertRaises(Conflict):self.u.build(p['id'],self.actor)
  with self.assertRaises(Conflict):self.u.validate(p['id'],self.actor)
 def test_rollback_refuses_incompatible_previous_release(self):
  from digital_life.application.lifecycle.deployment import Deployment
  from digital_life.application.lifecycle.schema_migration import migrate
  base=self.baseline();c=Control(self.root,self.s.instance_id)
  try:
   migrate(self.s,self.actor)
   # Isolated metadata damage stands in for an old release lacking schema support.
   c.db.execute('UPDATE deployments SET schema_max=2 WHERE id=?',(base,))
   new=Releases(c).stage(PROJECT)
   with c.tx():switch=c.insert('release_switches',old_deployment_id=base,new_deployment_id=new,phase='prepared',evidence={})
   result=Deployment(c)._rollback(new,dict(c.db.execute('SELECT * FROM deployments WHERE id=?',(base,)).fetchone()),'fixture failure',1)
   self.assertFalse(result['restarted']);self.assertIsNone(result['retained']);self.assertEqual(c.db.execute('SELECT compatibility_result FROM rollback_runs ORDER BY rowid DESC LIMIT 1').fetchone()[0],'fail');self.assertIsNone(c.db.execute("SELECT id FROM deployments WHERE state='active'").fetchone());self.assertEqual(self.s.db.execute('PRAGMA user_version').fetchone()[0],3)
  finally:c.close()
 def test_unvalidated_candidate_is_blocked_before_process_creation(self):
  from digital_life.application.lifecycle.deployment import Deployment
  self.enable();p=self.proposal();b=self.u.build(p['id'],self.actor);self.unlock();c=Control(self.root,self.s.instance_id)
  class NeverLaunch:
   def launch(self,*args):raise AssertionError('must validate first')
  try:
   with self.assertRaises(Forbidden):Deployment(c,NeverLaunch()).launch(b['deployment'])
   self.assertEqual(self.u.active()['id'],p['base_deployment'])
  finally:c.close()
 def test_user_stop_during_running_handshake_never_rolls_back_or_restarts(self):
  from digital_life.application.lifecycle.deployment import Deployment
  base=self.baseline();c=Control(self.root,self.s.instance_id);new=Releases(c).stage(PROJECT);self.unlock();starts=[]
  # Fault belongs to the explicit handshake driver; reviewed build stays exact.
  class Driver:
   def launch(driver,*args):starts.append(args[2]);return object()
   def await_state(driver,process,ready,desired,timeout):
    if desired=='running':c.stop('during-handshake')
    return {'deployment':new,'schema_compatible':True,'state':desired}
   def confirm_stability(driver,*args):raise Forbidden('user stopped')
   def stop(driver,*args):pass
  try:
   result=Deployment(c,Driver()).launch(new);self.assertTrue(result['user_stopped']);self.assertFalse(result['rollback']);self.assertEqual(starts,[new]);self.assertEqual(c.db.execute('SELECT count(*) FROM rollback_runs').fetchone()[0],0);self.assertEqual(c.state()['user_stopped'],1)
  finally:c.close()
