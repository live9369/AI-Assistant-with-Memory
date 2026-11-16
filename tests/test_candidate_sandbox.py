"""Actual native isolation boundaries, using synthetic canaries only."""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
from digital_life.infrastructure.processes.candidate_sandbox import CandidateSandbox,SandboxError,OUTPUT_LIMIT

@unittest.skipUnless(sys.platform=='darwin','native Seatbelt backend is macOS-only')
class SandboxTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
  self.candidate=self.root/'candidate';self.candidate.mkdir();(self.candidate/'source.txt').write_text('SOURCE')
  self.private=self.root/'synthetic-private';self.private.mkdir();self.secret=self.private/'controller.token';self.secret.write_text('SYNTHETIC-CANARY')
  self.runner=CandidateSandbox();self.counter=0
 def run_script(self,body,args=(),timeout=5):
  self.counter+=1;probe=self.root/('probe-'+str(self.counter));probe.mkdir()
  return self.runner.run(self.candidate,probe,body,[self.candidate,probe,self.secret,*args],timeout)
 def test_files_readonly_source_and_link_boundaries(self):
  script='''import json,sys,os
from pathlib import Path
source,probe,secret=map(Path,sys.argv[1:4])
checks={'read_source':(source/'source.txt').read_text()=='SOURCE'}
(probe/'allowed.txt').write_text('OK');checks['write_probe']=(probe/'allowed.txt').read_text()=='OK'
def blocked(name,fn):
 try:fn();checks[name]=False
 except PermissionError:checks[name]=True
blocked('read_external',lambda:secret.read_text())
blocked('write_external',lambda:secret.write_text('BAD'))
blocked('write_source',lambda:(source/'source.txt').write_text('BAD'))
(probe/'link').symlink_to(secret)
blocked('symlink_external',lambda:(probe/'link').read_text())
blocked('hardlink_external',lambda:os.link(secret,probe/'hardlink'))
blocked('move_source',lambda:os.rename(source,probe/'moved-source'))
print(json.dumps(checks))
'''
  r=self.run_script(script);self.assertEqual(r.returncode,0,r.output);checks=json.loads(r.output)
  self.assertTrue(all(checks.values()),checks);self.assertEqual(self.secret.read_text(),'SYNTHETIC-CANARY');self.assertEqual((self.candidate/'source.txt').read_text(),'SOURCE')
 def test_python_child_inherits_denials_and_shell_is_not_executable(self):
  script='''import sys,subprocess,json
code="import pathlib,sys;\\ntry: pathlib.Path(sys.argv[1]).read_text(); print('LEAK')\\nexcept PermissionError: print('BLOCKED')".replace('\\\\n','\\n')
p=subprocess.run([sys.executable,'-I','-S','-c',code,sys.argv[3]],capture_output=True)
blocked=False
try:subprocess.run(['/bin/sh','-c','echo forbidden'],check=True)
except (PermissionError,subprocess.CalledProcessError):blocked=True
print(json.dumps({'child':p.returncode==0 and p.stdout.strip()==b'BLOCKED','shell':blocked}))
'''
  r=self.run_script(script);self.assertEqual(r.returncode,0,r.output);self.assertTrue(all(json.loads(r.output).values()),r.output)
 def test_tcp_and_unix_socket_connections_are_denied(self):
  tcp=socket.socket();self.addCleanup(tcp.close);tcp.bind(('127.0.0.1',0));tcp.listen()
  unix=socket.socket(socket.AF_UNIX);self.addCleanup(unix.close);path=self.private/'listener.sock';unix.bind(str(path));unix.listen()
  script='''import socket,sys,json,errno
checks={}
for name,family,address in [('tcp',socket.AF_INET,('127.0.0.1',int(sys.argv[4]))),('unix',socket.AF_UNIX,sys.argv[5])]:
 try:
  with socket.socket(family) as s:
   s.settimeout(1);code=s.connect_ex(address);checks[name]=code in (errno.EPERM,errno.EACCES)
 except PermissionError:checks[name]=True
print(json.dumps(checks))
'''
  r=self.run_script(script,[tcp.getsockname()[1],path]);self.assertEqual(r.returncode,0,r.output);self.assertTrue(all(json.loads(r.output).values()),r.output)
 def test_limits_are_set_before_candidate_and_private_env_is_not_inherited(self):
  script='''import os,resource,json
print(json.dumps({'env':'SYNTHETIC_TOKEN' not in os.environ and 'CODEX_HOME' not in os.environ,'cpu':resource.getrlimit(resource.RLIMIT_CPU)[1]==5,'fds':resource.getrlimit(resource.RLIMIT_NOFILE)[1]==256,'file':resource.getrlimit(resource.RLIMIT_FSIZE)[1]==67108864,'core':resource.getrlimit(resource.RLIMIT_CORE)[1]==0}))
'''
  with patch.dict(os.environ,{'SYNTHETIC_TOKEN':'CANARY','CODEX_HOME':'/synthetic/private'}):r=self.run_script(script)
  self.assertEqual(r.returncode,0,r.output);self.assertTrue(all(json.loads(r.output).values()),r.output)
 def test_timeout_and_output_limit_fail_closed(self):
  with self.assertRaises(SandboxError) as timeout:self.run_script('import time;time.sleep(5)',timeout=1)
  self.assertEqual(timeout.exception.isolation['state'],'timeout')
  with self.assertRaises(SandboxError) as output:self.run_script('import os;os.write(1,b"x"*200000)')
  self.assertEqual(output.exception.isolation['state'],'output-limit')

class BackendTests(unittest.TestCase):
 def test_missing_backend_never_starts_an_unsandboxed_child(self):
  with patch('digital_life.infrastructure.processes.candidate_sandbox.sys.platform','unsupported'),patch('digital_life.infrastructure.processes.candidate_sandbox.subprocess.Popen') as launch:
   with self.assertRaises(SandboxError):CandidateSandbox()
   launch.assert_not_called()
