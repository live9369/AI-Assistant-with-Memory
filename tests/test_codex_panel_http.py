import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from test_codex_panel import FakeRPC
from digital_life.application.monitoring.codex_management import CodexManagement
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.entrypoints.http import create_server

class CodexPanelHttpTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=(Path(self.tmp.name)/'instance').resolve();s=Store.prepare(self.root);c=Control(self.root,s.instance_id);c.close();s.close()
  self.service=CodexManagement(self.root,executable='/trusted/codex',rpc_factory=FakeRPC);self.server=create_server(self.root,0,self.service);self.port=self.server.server_port;self.token=(self.root/'controller.token').read_text().strip()
  threading.Thread(target=self.server.serve_forever,daemon=True).start();self.addCleanup(self.tmp.cleanup);self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
 def call(self,path,body=None,auth=True,origin=None):
  conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10);headers={'Content-Type':'application/json'}
  if auth:headers['Authorization']='Bearer '+self.token
  if origin:headers['Origin']=origin
  conn.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers);r=conn.getresponse();raw=r.read();status=r.status;h=dict(r.getheaders());conn.close();return status,json.loads(raw),h
 def test_auth_origin_and_invalid_scope(self):
  for path,body in [('/v1/codex/status',None),('/v1/codex/authorize',{}),('/v1/codex/authorize/cancel',{}),('/v1/codex/test',{})]:
   self.assertEqual(self.call(path,body,auth=False)[0],403);self.assertEqual(self.call(path,body,origin='https://attacker.invalid')[0],403)
  self.assertEqual(self.call('/v1/codex/status?scope=wrong')[0],422)
 def test_device_code_lifecycle_and_no_log_leak(self):
  status,value,headers=self.call('/v1/codex/authorize',{});self.assertEqual(status,200);self.assertEqual(value['user_code'],'TEST-1234');self.assertEqual(headers['Cache-Control'],'no-store')
  self.assertEqual(self.call('/v1/codex/status?scope=instance')[1]['login_state'],'pending')
  self.assertEqual(self.call('/v1/codex/authorize/cancel',{})[1]['login_state'],'cancelled')
  self.assertNotIn('TEST-1234',json.dumps(self.call('/v1/logs')[1]));self.assertNotIn('TEST-1234',json.dumps(self.call('/v1/status')[1]))
 def test_configuration_cas_and_server_paths(self):
  current=self.call('/v1/model/configuration')[1];config={'backend':'codex_cli','model':'fixture','enabled':True}
  body={'configuration':config,'codex_auth_scope':'instance','expected_configuration_id':current['configuration_id']}
  self.assertEqual(self.call('/v1/model/validate',body)[0],200);self.assertEqual(self.call('/v1/model/configuration',body)[0],200);self.assertEqual(self.call('/v1/model/configuration',body)[0],409)
  value=self.call('/v1/model/configuration')[1];self.assertEqual(value['codex_auth_scope'],'instance');self.assertNotIn('executable',value['configuration']);self.assertNotIn('auth_home',value['configuration'])
  for key in ('executable','auth_home'):
   self.assertEqual(self.call('/v1/model/validate',{'configuration':dict(config,**{key:'/attacker'})})[0],422)
 def test_test_connection_never_wakes_instance(self):
  current=self.call('/v1/model/configuration')[1];self.call('/v1/model/configuration',{'configuration':{'backend':'codex_cli','model':'fixture','enabled':True},'expected_configuration_id':current['configuration_id']})
  current=self.call('/v1/model/configuration')[1]
  class Model:
   name='codex_cli:fixture';last_usage={'input_tokens':3,'output_tokens':2,'latency_ms':1};last_session_id='fixture'
   def generate(self,request):return {'action':{'tool':'wait','arguments':{'reason':'connection-test'}}}
  with patch('digital_life.infrastructure.llm.inference.configured_reasoner',return_value=Model()):
   status,value,_=self.call('/v1/codex/test',{'expected_configuration_id':current['configuration_id'],'confirm_inference':True})
  self.assertEqual(status,200);self.assertTrue(value['available']);self.assertFalse(value['action_executed']);self.assertFalse(value['runtime_started'])
  s=Store(self.root)
  try:self.assertEqual(s.rows('thought_requests'),[]);self.assertEqual(s.rows('action_attempts'),[])
  finally:s.close()
  self.assertTrue((self.root/'WAKE_DISABLED').exists())
