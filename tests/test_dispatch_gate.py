"""Stop/dispatch mutual exclusion across threads/processes, temporary instances only."""
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.domain.contracts import Forbidden,utc
from evaluation.exploration.harness import Harness
from evaluation.exploration.scenarios import stop_matrix
import json
ROOT=Path(__file__).resolve().parents[1]

class DispatchGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'instance';self.s=Store.prepare(self.root)
        self.c=Control(self.root,self.s.instance_id)
        (self.root/'WAKE_DISABLED').unlink(); self.c.resume('temporary-only')
    def tearDown(self): self.c.close(); self.s.close(); self.tmp.cleanup()
    def test_callback_can_stop_reentrantly_and_new_work_is_blocked(self):
        with dispatch_gate(self.root):
            self.c.stop('in-flight-reentrant-stop')
            with self.assertRaises(Forbidden): self.s.assert_execution_allowed()
        self.assertEqual(self.c.state()['user_stopped'],1)
    def test_thread_stop_waits_for_entered_callback_and_returns_after_release(self):
        attempted=threading.Event(); committed=threading.Event(); errors=[]
        def stopper():
            c=Control(self.root,self.s.instance_id)
            try: attempted.set(); c.stop('thread-stop'); committed.set()
            except BaseException as e: errors.append(e)
            finally:c.close()
        with dispatch_gate(self.root):
            t=threading.Thread(target=stopper);t.start();self.assertTrue(attempted.wait(2))
            self.assertFalse(committed.wait(0.05));self.assertEqual(self.c.state()['user_stopped'],0)
        t.join(3);self.assertFalse(t.is_alive());self.assertFalse(errors);self.assertTrue(committed.is_set())
    def test_process_stop_waits_for_gate_and_process_death_releases_it(self):
        code='''import sys
from digital_life.application.lifecycle.control_plane import Control
c=Control(sys.argv[1],sys.argv[2]); print('attempting',flush=True);c.stop('process-stop');print('committed',flush=True);c.close()
'''
        with dispatch_gate(self.root):
            p=subprocess.Popen([sys.executable,'-c',code,str(self.root),self.s.instance_id],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            self.assertEqual(p.stdout.readline().strip(),'attempting');time.sleep(0.05)
            self.assertIsNone(p.poll());self.assertEqual(self.c.state()['user_stopped'],0)
        out,err=p.communicate(timeout=5);self.assertEqual(p.returncode,0,err);self.assertIn('committed',out)
        code='''import sys,time
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
with dispatch_gate(sys.argv[1]):
 print('held',flush=True); time.sleep(10)
'''
        p=subprocess.Popen([sys.executable,'-c',code,str(self.root)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.assertEqual(p.stdout.readline().strip(),'held');p.kill();p.communicate(timeout=5)
        with dispatch_gate(self.root): pass
    def test_gate_before_sqlite_order_is_enforced(self):
        from digital_life.application.autonomy.exploration import Exploration
        with self.s.tx():
            with self.assertRaises(ValueError): Exploration(self.s).configure(self.s.config()['controller'],False)
    def test_all_original_stop_matrix_cells(self):
        data=json.loads((ROOT/'evaluation/exploration/materials/cases-v1.json').read_text())
        case=next(c for c in data['cases'] if c['case_id']=='B01')
        for control in ['disable','user_stop','dispatch_competition']:
            for stage in ['before_prepare','authorized_before_dispatch','in_flight','after_commit']:
                for transport in ['model','tool']:
                    with self.subTest(control=control,stage=stage,transport=transport):
                        root=Path(self.tmp.name)/(control+'-'+stage+'-'+transport)
                        h=Harness(root,case)
                        try: stop_matrix(h,dict(control=control,stage=stage,transport=transport))
                        finally:h.close()

if __name__=='__main__': unittest.main()
