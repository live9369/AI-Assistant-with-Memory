"""Panel auth uses simulated RPC; no real accounts, tokens, or model requests."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from digital_life.application.monitoring.codex_management import CodexManagement
from digital_life.application.monitoring.management import Management,ManagementError
from digital_life.application.lifecycle.control_plane import Control
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.domain.contracts import ContractError,Conflict
from digital_life.infrastructure.llm.codex_auth import VERIFY_URL,AuthRPC

class FakeRPC:
 def __init__(self,exe,home=None):self.home=home;self.calls=[];self.notifications=[];self.account=None;self.fail=False;self.closed=False
 def call(self,method,params):
  self.calls.append((method,params))
  if self.fail:raise ContractError('secret-provider-error')
  if method=='account/read':return {'account':self.account}
  if method=='account/login/start':return {'verificationUrl':VERIFY_URL,'userCode':'TEST-1234','loginId':'fixture-login'}
  return {}
 def drain(self):result=self.notifications;self.notifications=[];return result
 def close(self):self.closed=True
class CodexPanelTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=(Path(self.tmp.name)/'panel').resolve();self.s=Store.prepare(self.root);self.control=Control(self.root,self.s.instance_id)
  self.service=CodexManagement(self.root,executable='/trusted/codex',rpc_factory=FakeRPC);self.m=Management(self.s,self.service)
  self.addCleanup(self.tmp.cleanup);self.addCleanup(self.s.close);self.addCleanup(self.control.close);self.addCleanup(self.service.close)
 def body(self,scope='local'):
  return {'configuration':{'backend':'codex_cli','model':'fixture','enabled':True,'timeout':10,'context_window':8192},'codex_auth_scope':scope,'expected_configuration_id':self.m.config_row()['id']}
 def test_status_does_not_start_login_or_inference(self):
  c=self.service.client('local');c.account={'type':'chatgpt','email':'private@example.com','planType':'pro'}
  value=self.service.status('local');self.assertTrue(value['logged_in']);self.assertEqual(value['plan'],'pro');self.assertNotIn('private@',json.dumps(value));self.assertEqual(c.calls,[('account/read',{'refreshToken':False})])
  c.fail=True;self.assertNotIn('secret',json.dumps(self.service.status('local')))
 def test_authorize_repeat_cancel_and_no_persistence(self):
  first=self.service.authorize(self.m);self.assertEqual(first['user_code'],'TEST-1234');self.service.authorize(self.m)
  c=self.service.client('instance');self.assertEqual(sum(m=='account/login/start' for m,p in c.calls),1);self.assertEqual(c.home,self.root/'codex-auth')
  self.assertEqual(self.service.cancel(self.m)['login_state'],'cancelled');self.assertIsNone(self.service.pending)
  for file in self.root.rglob('*'):
   if file.is_file():self.assertNotIn(b'TEST-1234',file.read_bytes())
 def test_completion_failure_expiry_and_late_notification(self):
  self.service.authorize(self.m);c=self.service.client('instance');c.notifications=[{'loginId':'fixture-login','success':True}];c.account={'type':'chatgpt','planType':'pro'}
  value=self.service.status('instance');self.assertEqual(value['login_state'],'completed');self.assertNotIn('user_code',value)
  c.account=None;self.service.authorize(self.m);c.notifications=[{'loginId':'fixture-login','success':False,'error':'private-error'}];self.assertEqual(self.service.status('instance')['login_state'],'failed')
  self.service.authorize(self.m);self.service.pending['deadline']=time.monotonic()-1;self.service._expire();self.assertEqual(self.service.last_state,'expired')
  c.notifications=[{'loginId':'fixture-login','success':True}];self.assertEqual(self.service.status('instance')['login_state'],'expired')
 def test_config_paths_are_server_managed_and_versioned(self):
  body=self.body('instance');self.m.validate_model(body);self.m.save_model(body);config=self.s.config()['model'];self.assertEqual(config['executable'],'/trusted/codex');self.assertEqual(config['auth_home'],str(self.root/'codex-auth'));self.assertEqual(self.m.model()['codex_auth_scope'],'instance')
  with self.assertRaises(Conflict):self.m.save_model(body)
  for key in ('executable','auth_home'):
   body=self.body();body['configuration'][key]='/attacker/value'
   with self.assertRaises(ManagementError):self.m.validate_model(body)
  with self.assertRaises(ManagementError):self.service.status('wrong')
 def test_test_requires_confirmation_revision_stop_and_sanitizes(self):
  self.m.save_model(self.body());body={'expected_configuration_id':self.m.config_row()['id'],'confirm_inference':True}
  with self.assertRaises(ManagementError):self.service.test(self.m,{})
  with self.assertRaises(Conflict):self.service.test(self.m,dict(body,expected_configuration_id='old'))
  class Model:
   name='codex_cli:fixture';last_usage={'input_tokens':1,'output_tokens':1,'latency_ms':1};last_session_id='test-session'
   def generate(self,request):
    assert 'selected_memories' not in request
    return {'action':{'tool':'wait','arguments':{'reason':'connection-test'}}}
  with patch('digital_life.infrastructure.llm.inference.configured_reasoner',return_value=Model()):self.assertTrue(self.service.test(self.m,body)['available'])
  self.service.test_lock.acquire()
  try:
   with self.assertRaises(Conflict):self.service.test(self.m,body)
  finally:self.service.test_lock.release()
  with patch('digital_life.infrastructure.llm.inference.configured_reasoner',side_effect=ContractError('private-error')):
   value=self.service.test(self.m,body);self.assertFalse(value['available']);self.assertNotIn('private-error',json.dumps(value))
  self.assertTrue((self.root/'WAKE_DISABLED').exists());self.assertEqual(self.s.rows('thought_requests'),[]);self.assertEqual(self.s.rows('action_attempts'),[])
 def test_bad_authorization_url_and_process_failure(self):
  c=self.service.client('instance');original=c.call
  c.call=lambda m,p:dict(original(m,p),verificationUrl='https://attacker.invalid') if m=='account/login/start' else original(m,p)
  with self.assertRaises(ContractError):self.service.authorize(self.m)
  self.assertTrue(c.closed)
  c.call=original;self.service.authorize(self.m);c.fail=True;self.assertFalse(self.service.status('instance')['available']);self.assertIsNone(self.service.pending)
 def test_only_auth_rpc_methods_permitted(self):
  rpc=AuthRPC('/missing/codex')
  with self.assertRaises(ContractError):rpc.call('turn/start',{})
  with self.assertRaises(ContractError):rpc.call('account/read',{})

 def test_real_rpc_process_handshake_and_close(self):
  import sys
  exe=self.root/'fake-codex'
  exe.write_text('#!'+sys.executable+'\n'+"import sys,json\nfor line in sys.stdin:\n e=json.loads(line)\n if 'id' in e: print(json.dumps({'id':e['id'],'result':{'account':None}}),flush=True)\n")
  exe.chmod(0o700);rpc=AuthRPC(str(exe),self.root/'rpc-home')
  try:
   self.assertEqual(rpc.call('account/read',{'refreshToken':False}),{'account':None});proc=rpc.process
  finally:rpc.close()
  self.assertIsNotNone(proc.poll());self.assertEqual((self.root/'rpc-home').stat().st_mode&0o777,0o700)
