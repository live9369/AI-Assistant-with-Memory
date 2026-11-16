"""Real isolated Runtime subprocesses; model inventory fixture, never formal data."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store,PROJECT
from digital_life.application.lifecycle.control_plane import Control,Releases
from digital_life.application.lifecycle.deployment import Deployment,ProcessDriver
from digital_life.domain.contracts import ContractError

class Inventory(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        body=json.dumps({'data':[{'id':'isolated-model'}]}).encode()
        self.send_response(200); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)

class OwnedFailureDriver(ProcessDriver):
    """Kill only the owned real candidate process, outside its reviewed source."""
    def __init__(self,control,deployment,phase):
        self.control=control;self.deployment=deployment;self.phase=phase;self.events=[];self.injected=False
    def launch(self,path,root,deployment,ready,gate):
        process=super().launch(path,root,deployment,ready,gate)
        process.fixture_deployment=deployment
        self.events.append({'kind':'real_process_started','deployment':deployment,'pid':process.pid})
        return process
    def await_state(self,process,ready,desired,timeout):
        if process.fixture_deployment!=self.deployment or desired!=self.phase or self.injected:
            return super().await_state(process,ready,desired,timeout)
        self.injected=True
        if desired=='running':
            witness=super().await_state(process,ready,desired,timeout)
            active=self.control.db.execute('SELECT state FROM deployments WHERE id=?',(self.deployment,)).fetchone()[0]
            if active!='active' or witness['pid']!=process.pid:raise AssertionError('real activated candidate witness missing')
            self.events.append({'kind':'actual_running_before_owned_failure','witness':witness,'active_state':active})
        process.kill();returncode=process.wait(timeout=5)
        self.events.append({'kind':'owned_process_killed','phase':desired,'pid':process.pid,'returncode':returncode})
        if desired=='prepared':return super().await_state(process,ready,desired,timeout)
        raise ContractError('fixture driver killed owned real candidate after actual activation/running')

class ProcessIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'instance'
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Inventory)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.s=Store.prepare(self.root,model_config={'backend':'llamacpp','model':'isolated-model','base_url':'http://127.0.0.1:'+str(self.server.server_port)})
        self.c=Control(self.root,self.s.instance_id); self.addCleanup(self.s.close); self.addCleanup(self.c.close)
        (self.root/'WAKE_DISABLED').unlink(); self.c.resume('fixture-unlock')
        self.manager=Deployment(self.c)
        self.addCleanup(self.stop_process)
        self.old=Releases(self.c).stage(PROJECT)
    def stop_process(self):
        if self.manager.active:
            self.manager.driver.stop(self.manager.active['process']); self.manager.active=None
    def candidate(self,fault_phase=None):
        # Stage the exact reviewed executable build. The distinct deployment
        # identity exercises switching; no shadow module or source mutation.
        candidate=Releases(self.c).stage(PROJECT)
        if fault_phase:self.manager.driver=OwnedFailureDriver(self.c,candidate,fault_phase)
        return candidate
    def activate_old_without_process(self):
        Releases(self.c).activate(self.old,lambda path:{'ready':True,'schema_compatible':True})
    def test_real_process_heartbeat_metrics_and_user_stop(self):
        result=self.manager.launch(self.old,timeout=12)
        self.assertTrue(result['switched'])
        self.assertNotEqual(result['pid'],os.getpid())
        self.assertEqual(self.manager.check()['state'],'running')
        deadline=time.monotonic()+5
        while not self.s.rows('metric_samples') and time.monotonic()<deadline: time.sleep(0.05)
        self.assertGreater(len(self.s.rows('metric_samples')),100,
            (self.manager.active['ready'].parent/'runtime.log').read_text()[-2000:])
        self.c.stop('fixture-stop')
        self.assertEqual(self.manager.check()['state'],'user_stopped')
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM rollback_runs').fetchone()[0],0)
    def test_real_failure_before_ready_retains_and_restarts_old(self):
        self.activate_old_without_process()
        new=self.candidate('prepared')
        result=self.manager.launch(new,timeout=12)
        self.assertFalse(result['switched']); self.assertTrue(result['restarted'])
        killed=[e for e in self.manager.driver.events if e['kind']=='owned_process_killed'];self.assertEqual(len(killed),1);self.assertEqual(killed[0]['returncode'],-9);self.assertNotEqual(killed[0]['pid'],os.getpid())
        self.assertEqual(self.manager.check()['deployment'],self.old)
    def test_real_failure_after_activation_rolls_back(self):
        from digital_life.application.lifecycle.schema_migration import migrate
        self.c.stop('schema-fixture-stop'); migrate(self.s,self.s.config()['controller']); self.c.resume('schema-fixture-resume')
        self.activate_old_without_process()
        new=self.candidate('running')
        result=self.manager.launch(new,timeout=12)
        self.assertFalse(result['switched']); self.assertTrue(result['restarted'])
        killed=[e for e in self.manager.driver.events if e['kind']=='owned_process_killed'];self.assertEqual(len(killed),1);self.assertEqual(killed[0]['returncode'],-9);self.assertNotEqual(killed[0]['pid'],os.getpid())
        self.assertEqual(self.manager.check()['deployment'],self.old)
        self.assertEqual(self.c.db.execute('SELECT result FROM rollback_runs ORDER BY rowid DESC LIMIT 1').fetchone()[0],'succeeded')
        self.assertTrue(any(e['kind']=='actual_running_before_owned_failure' for e in self.manager.driver.events))
        self.assertEqual(self.s.db.execute('PRAGMA user_version').fetchone()[0],3)
        self.assertEqual(len(self.s.rows('schema_migrations')),1)
    def test_watchdog_recovers_post_ready_process_death(self):
        self.activate_old_without_process()
        new=self.candidate()
        self.assertTrue(self.manager.launch(new,timeout=12)['switched'])
        process=self.manager.active['process'];self.assertNotEqual(process.pid,os.getpid())
        process.kill();self.assertEqual(process.wait(timeout=6),-9)
        result=self.manager.check(timeout=12)
        self.assertEqual(result['state'],'recovered')
        self.assertEqual(self.manager.check()['deployment'],self.old)
