"""Core receipt-to-proposal and CLI pipeline cases; synthetic temporary data."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.infrastructure.persistence.sqlite_store import Store,PROJECT
from digital_life.application.lifecycle.control_plane import Control,Releases
from digital_life.application.runtime.engine import Engine
from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
from digital_life.application.lifecycle.source_updates import SourceUpdates
from digital_life.application.lifecycle.project_access import ProjectAccess
from digital_life.application.lifecycle.maintenance_pipeline import MaintenancePipeline
from digital_life.entrypoints.maintenance_update import update
from digital_life.domain.contracts import sha,Conflict

class FlowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.s=Store.prepare(self.root/'life');self.addCleanup(self.s.close);self.c=Control(self.s.root,self.s.instance_id);self.addCleanup(self.c.close)
  self.actor=self.s.config()['controller'];SelfMaintenance(self.s).configure(True,self.actor)
  self.old=Releases(self.c).stage(PROJECT);Releases(self.c).activate(self.old,lambda p:{'ready':True,'schema_compatible':True})
  self.project=self.root/'project';(self.project/'digital_life').mkdir(parents=True)
  self.path='digital_life/__init__.py';self.original=(PROJECT/self.path).read_text();(self.project/self.path).write_text(self.original)
  ProjectAccess(self.s).configure(str(self.project),self.actor,auto_approve=True)
  (self.s.root/'WAKE_DISABLED').unlink();self.c.resume('fixture');self.e=Engine(self.s);self.u=SourceUpdates(self.s)
 def edit(self,path=None,before=None):
  path=path or self.path;before=(self.project/path).read_text() if before is None else before
  action={'tool':'project_write','arguments':{'path':path,'text':before+'\n# candidate marker\n','expected_sha256':sha(before.encode())}}
  class Model:
   name='fixture'
   def generate(inner,p):return {'schema_version':1,'explanation':'propose edit','action':action}
  a=self.e.submit('update test file','edit-'+str(len(self.s.rows('activities'))));r=self.e.think(a,Model());self.e.execute(r['action_id']);return a,r
 def test_real_worker_edit_creates_pinned_proposal_and_next_fresh_input_receipt(self):
  a,r=self.edit();p=self.u.events('proposed')[0]
  self.assertEqual(p['base_deployment'],self.old);self.assertTrue(p['source']['project_version']);self.assertEqual(p['source']['before_sha256'],sha(self.original.encode()))
  self.assertEqual(p['changes'][self.path],self.original+'\n# candidate marker\n')
  class Model:name='fixture'
  packet=self.e.prepare(a,Model())[1]
  self.assertEqual(packet['task_loop']['observations'][-1]['source_update'],{'proposal':p['id'],'deployed':False})
  result=self.s.db.execute('SELECT r.* FROM action_results r JOIN action_attempts a ON a.id=r.attempt_id WHERE a.intent_id=?',(r['action_id'],)).fetchone()
  self.u.capture(r['action_id'],{'state':'succeeded','result':result['id'],'receipt':result['receipt_artifact_id'],'evidence':result['outcome_ref']})
  self.assertEqual(len(self.u.events('proposed')),1)
 def test_existing_draft_baseline_mismatch_is_logged_without_undoing_edit(self):
  (self.project/self.path).write_text(self.original+'\n# unreviewed draft\n');a,_=self.edit()
  self.assertFalse(self.u.events('proposed'));self.assertTrue(self.u.events('captured')[-1]['rejected'])
  self.assertIn('candidate marker',(self.project/self.path).read_text())
 def test_non_source_document_is_not_a_deployment_proposal(self):
  (self.project/'notes.txt').write_text('notes');self.edit('notes.txt')
  self.assertFalse(self.u.events('proposed'));self.assertFalse(self.u.events('captured'))
 def test_wrong_version_receipt_cannot_become_source_proposal(self):
  with patch.object(SourceUpdates,'capture',return_value=None):a,r=self.edit()
  row=self.s.db.execute('SELECT r.* FROM action_results r JOIN action_attempts a ON a.id=r.attempt_id WHERE a.intent_id=?',(r['action_id'],)).fetchone()
  receipt=self.s.read_artifact(row['receipt_artifact_id']);receipt['evidence']['version']='f'*40
  with self.s.tx():
   artifact=self.s.artifact(receipt);self.s.db.execute('UPDATE action_results SET receipt_artifact_id=? WHERE id=?',(artifact,row['id']))
  result=self.u.capture(r['action_id'],{'state':'succeeded','result':row['id'],'receipt':artifact,'evidence':row['outcome_ref']})
  self.assertTrue(result['rejected']);self.assertFalse(self.u.events('proposed'))
 def proposal(self):return self.u.propose(self.old,{'digital_life/update_flow_marker.py':'VALUE=1\n'},'fixture','manual',self.actor)['id']
 def stopped(self):
  with self.s.tx():self.s.db.execute("UPDATE jobs SET state='cancelled' WHERE state='queued'")
  return self.c.stop('maintenance-stop')['last_stop_command_id']
 def test_pipeline_validates_before_launch_and_new_stop_wins(self):
  proposal=self.proposal();stop=self.stopped()
  class Manager:
   active=None
   def launch(inner,*args,**kwargs):raise AssertionError('must not launch after new user stop')
  pipeline=MaintenancePipeline(self.s,self.c,Manager())
  def validate(*args):self.c.stop('new-user-stop');return {'id':'proof','passed':True}
  with patch.object(pipeline.u,'build',return_value={'deployment':'candidate'}),patch.object(pipeline.u,'validate',side_effect=validate):r=pipeline.execute(proposal,stop)
  self.assertFalse(r['updated']);self.assertFalse(r['restored']);self.assertTrue(self.c.state()['user_stopped'])
 def test_probe_failure_restores_base_without_repeating_model_gate(self):
  proposal=self.proposal();stop=self.stopped();calls=[]
  class Manager:
   active=None
   def launch(inner,*args,**kwargs):calls.append((args,kwargs));return {'switched':True}
  pipeline=MaintenancePipeline(self.s,self.c,Manager())
  with patch.object(pipeline.u,'build',return_value={'deployment':'candidate'}),patch.object(pipeline.u,'validate',return_value={'id':'proof','passed':False,'error':'fixture'}):r=pipeline.execute(proposal,stop)
  self.assertFalse(r['updated']);self.assertTrue(r['restored']);self.assertEqual(calls,[((self.old,),{'_recover':False})])
 def test_update_confirmation_and_busy_preflight_do_not_stop_instance(self):
  with self.assertRaises(ValueError):update(self.s.root,'unused','wrong')
  p=self.proposal();self.e.submit('pending real work','pending')
  revision=self.c.state()['control_revision']
  with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(Conflict):update(self.s.root,p,'UPDATE '+self.s.root.name)
  self.assertEqual(self.c.state()['control_revision'],revision)
 def test_resume_compare_and_set_preserves_newer_stop(self):
  stop=self.stopped();self.c.stop('newer')
  with self.assertRaises(Conflict):self.c.resume('stale-resume',expected_stop=stop)
  self.assertTrue(self.c.state()['user_stopped'])
 def test_unavailable_isolation_and_old_proof_cannot_admit_candidate(self):
  from digital_life.infrastructure.processes.candidate_sandbox import SandboxError
  from digital_life.application.lifecycle.source_updates import PROBE_VERSION
  from digital_life.domain.contracts import Forbidden
  p=self.proposal();self.stopped();built=self.u.build(p,self.actor)
  with patch('digital_life.infrastructure.processes.candidate_sandbox.CandidateSandbox',side_effect=SandboxError('unavailable fixture',{'required':True,'state':'unavailable'})),patch('subprocess.Popen') as launch:
   proof=self.u.validate(p,self.actor)
   self.assertFalse(proof['passed']);self.assertEqual(proof['isolation']['state'],'unavailable');launch.assert_not_called()
  with self.s.tx():
   self.u.emit('validated',{'proposal':p,'deployment':built['deployment'],'release':built['release'],'base_deployment':self.old,'schema':self.s.db.execute('pragma user_version').fetchone()[0],'probe_version':PROBE_VERSION,'passed':True})
  with self.assertRaises(Forbidden):self.u.assert_deployable(built['deployment'])
