"""T12 real temporary Runtime processes; only a loopback inventory fixture."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store,PROJECT
from digital_life.application.lifecycle.control_plane import Control,Releases
from digital_life.application.lifecycle.deployment import Deployment
from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
from digital_life.application.lifecycle.source_updates import SourceUpdates
from test_process_integration import Inventory

class MaintenanceProcessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'instance';self.server=ThreadingHTTPServer(('127.0.0.1',0),Inventory);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
  self.s=Store.prepare(self.root,model_config={'backend':'llamacpp','model':'isolated-model','base_url':'http://127.0.0.1:'+str(self.server.server_port)});self.addCleanup(self.s.close);self.c=Control(self.root,self.s.instance_id);self.addCleanup(self.c.close);self.manager=Deployment(self.c);self.addCleanup(self.stop)
  self.m=SelfMaintenance(self.s);self.m.configure(True,self.s.config()['controller'],auto_repair=True,max_repairs=1);self.old=Releases(self.c).stage(PROJECT);Releases(self.c).activate(self.old,lambda p:{'ready':True,'schema_compatible':True})
 def stop(self):
  if self.manager.active:self.manager.driver.stop(self.manager.active['process']);self.manager.active=None
 def unlock(self):(self.root/'WAKE_DISABLED').unlink();self.c.resume('isolated-authorization')
 def test_authorized_runtime_repairs_missing_workspace_and_user_stop_wins(self):
  import shutil
  shutil.rmtree(self.root/'workspace');identity=self.s.instance_id;self.unlock();result=self.manager.launch(self.old,timeout=12);self.assertTrue(result['switched']);deadline=time.monotonic()+8
  while not self.m.events('repaired') and time.monotonic()<deadline:time.sleep(.05)
  self.assertTrue(self.m.events('repaired')[-1]['passed']);self.assertTrue((self.root/'workspace').is_dir());self.assertEqual(self.s.instance_id,identity);self.assertEqual(self.m.remaining(),0);self.c.stop('user-test-stop');self.assertEqual(self.manager.check()['state'],'user_stopped');self.assertEqual(self.c.db.execute('SELECT count(*) FROM rollback_runs').fetchone()[0],0)
 def test_validated_source_candidate_can_launch_without_replacing_identity(self):
  self.s.event('fixture.history',payload={'must':'remain'});history=[dict(r) for r in self.s.rows('identity_anchors')];u=SourceUpdates(self.s);p=u.propose(self.old,{'digital_life/t12_probe_marker.py':'VALUE=12\n'},'isolated process test','one',self.s.config()['controller']);b=u.build(p['id'],self.s.config()['controller']);proof=u.validate(p['id'],self.s.config()['controller']);self.assertTrue(proof['passed'],proof);self.unlock();result=self.manager.launch(b['deployment'],timeout=12);self.assertTrue(result['switched']);self.assertEqual(self.manager.check()['state'],'running');self.assertEqual(history,[dict(r) for r in self.s.rows('identity_anchors')]);self.assertEqual(len([e for e in self.s.rows('runtime_events') if e['event_type']=='fixture.history']),1)
 def test_update_pipeline_builds_probes_and_starts_actual_runtime(self):
  from digital_life.application.lifecycle.maintenance_pipeline import MaintenancePipeline
  u=SourceUpdates(self.s);p=u.propose(self.old,{'digital_life/pipeline_probe_marker.py':'VALUE=1\n'},'pipeline fixture','pipeline',self.s.config()['controller'])
  (self.root/'WAKE_DISABLED').unlink();command=self.c.stop('pipeline-update')['last_stop_command_id']
  anchors=[dict(r) for r in self.s.rows('identity_anchors')]
  result=MaintenancePipeline(self.s,self.c,self.manager).execute(p['id'],command)
  self.assertTrue(result['updated'],result);self.assertEqual(self.manager.check()['state'],'running')
  self.assertEqual(anchors,[dict(r) for r in self.s.rows('identity_anchors')]);self.assertTrue(u.events('validated')[-1]['passed'])
