"""Process concurrency and abrupt-exit checks, exclusively on temporary instances."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store,PROJECT
from digital_life.application.runtime.engine import Engine
from digital_life.application.runtime.scheduling import Queue
from digital_life.domain.contracts import utc
from digital_life.application.lifecycle.control_plane import Control
from digital_life.tools import Policy

class FaultIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.s=Store.prepare(Path(self.tmp.name)/'instance')
        self.addCleanup(self.tmp.cleanup); self.addCleanup(self.s.close)
    def launch(self,code,*args):
        return subprocess.Popen([sys.executable,'-c',code,str(self.s.root),*args],cwd=str(PROJECT),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def test_four_real_processes_never_claim_same_job(self):
        with self.s.tx():
            for i in range(12): Queue(self.s).enqueue('fixture',self.s.root_object('fixture-job-target'))
        code='''import sys,json
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.scheduling import Queue
s=Store(sys.argv[1]); claimed=[]
while True:
    job=Queue(s).claim(str(__import__('os').getpid()))
    if job is None: break
    claimed.append(job['id']); Queue(s).finish(job)
s.close(); print(json.dumps(claimed))
'''
        children=[self.launch(code) for _ in range(4)]; claimed=[]
        for child in children:
            out,err=child.communicate(timeout=15); self.assertEqual(child.returncode,0,err); claimed+=json.loads(out)
        self.assertEqual(len(claimed),12); self.assertEqual(len(set(claimed)),12)
        self.assertTrue((self.s.root/'WAKE_DISABLED').exists())
    def test_abrupt_process_death_rolls_back_transaction(self):
        before=len(self.s.rows('runtime_events'))
        code='''import sys,os
from digital_life.infrastructure.persistence.sqlite_store import Store
s=Store(sys.argv[1])
with s.tx():
    s.event('crash.before.commit',payload={'not_committed':True})
    os._exit(7)
'''
        child=self.launch(code); out,err=child.communicate(timeout=10)
        self.assertEqual(child.returncode,7); self.assertEqual(len(self.s.rows('runtime_events')),before)
        self.assertEqual(self.s.integrity(),{'integrity':'ok','foreign_keys':[]})
    def test_simultaneous_tool_dispatch_consumes_authorization_once(self):
        root=self.s.root; control=Control(root,self.s.instance_id)
        try:
            (root/'WAKE_DISABLED').unlink(); control.resume('fixture-only')
            class Model:
                name='fixture'
                def generate(self,request): return {'schema_version':1,'action':{'tool':'write_note','arguments':{'path':'proof.txt','text':'exactly-once'}},'explanation':'isolated fixture'}
            activity=Engine(self.s).submit('test','race'); thought=Engine(self.s).think(activity,Model())
            Policy(self.s).approve(thought['approval_id'],self.s.config()['controller'])
            code='''import sys,json
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.tools import Executor
from digital_life.domain.contracts import RuntimeIdentity
s=Store(sys.argv[1])
try: print(json.dumps(Executor(s,RuntimeIdentity(0,'race-fixture')).dispatch(sys.argv[2])))
except Exception as error: print(json.dumps({'blocked':type(error).__name__}))
finally: s.close()
'''
            children=[self.launch(code,thought['action_id']) for _ in range(2)]
            results=[]
            for child in children:
                out,err=child.communicate(timeout=15); self.assertEqual(child.returncode,0,err); results.append(json.loads(out))
            self.assertEqual(len(self.s.rows('action_attempts')),1)
            self.assertEqual((root/'workspace/proof.txt').read_text(),'exactly-once')
            self.assertEqual(sum(r.get('state')=='succeeded' for r in results),1)
        finally: control.stop('fixture-finished'); control.close()
