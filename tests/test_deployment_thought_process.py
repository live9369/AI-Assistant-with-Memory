"""Real Runtime process, local HTTP substitute; never calls a real model."""
import json,tempfile,threading,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from tests.test_process_integration import Inventory
from digital_life.infrastructure.persistence.sqlite_store import Store,PROJECT
from digital_life.application.lifecycle.control_plane import Control,Releases
from digital_life.application.lifecycle.deployment import Deployment
from digital_life.application.lifecycle.process_checkpoints import ProcessCheckpoints
class ModelEndpoint(Inventory):
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.requests.append(body)
  if self.server.fail:
   self.send_response(503);self.end_headers();self.wfile.write(b'model unavailable');return
  schema=body['response_format']['json_schema']['schema'];props=schema['properties'];reason=props['action']['anyOf'][0]['properties']['arguments']['properties']['reason']['enum'][0]
  result={'schema_version':props['schema_version']['const'],'action':{'tool':'wait','arguments':{'reason':reason}},'explanation':props['explanation']['enum'][0]}
  raw=json.dumps({'model':'isolated-model','choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}],'usage':{'prompt_tokens':100,'completion_tokens':30}}).encode()
  self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
class ThoughtProcessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'life';self.server=ThreadingHTTPServer(('127.0.0.1',0),ModelEndpoint);self.server.requests=[];self.server.fail=False
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.s=Store.prepare(self.root,model_config={'backend':'llamacpp','model':'isolated-model','base_url':'http://127.0.0.1:'+str(self.server.server_port),'timeout':2});self.c=Control(self.root,self.s.instance_id)
  (self.root/'WAKE_DISABLED').unlink();self.c.resume('fixture');ProcessCheckpoints(self.c).configure(True,self.s.config()['controller'],verify_thought=True,thought_timeout=10)
  self.manager=Deployment(self.c);self.old=Releases(self.c).stage(PROJECT);Releases(self.c).activate(self.old,lambda _:{'ready':True,'schema_compatible':True})
 def tearDown(self):
  if self.manager.active:self.manager.driver.stop(self.manager.active['process'])
  self.c.close();self.s.close();self.server.shutdown();self.server.server_close();self.tmp.cleanup()
 def test_one_fresh_thought_required_before_admission(self):
  new=Releases(self.c).stage(PROJECT);result=self.manager.launch(new,timeout=12)
  self.assertTrue(result['switched']);proof=result['handshake']['deployment_acceptance'];self.assertEqual(proof['state'],'passed');self.assertEqual(proof['inference_calls'],1);self.assertEqual(len(self.server.requests),1)
  self.assertTrue((self.manager.active['ready'].parent/'admitted').exists());self.assertEqual(result['handshake']['inference_ready'],'verified')
  self.assertTrue(self.c.db.execute("select 1 from control_commands where kind='process.deployment_thought' and state='succeeded'").fetchone())
 def test_unavailable_model_rolls_back_without_second_model_call(self):
  self.server.fail=True;new=Releases(self.c).stage(PROJECT);result=self.manager.launch(new,timeout=12)
  self.assertFalse(result['switched']);self.assertTrue(result['restarted']);self.assertEqual(self.manager.active['deployment'],self.old);self.assertEqual(len(self.server.requests),1)
  ready=json.loads(self.manager.active['ready'].read_text());self.assertEqual(ready['deployment_acceptance']['state'],'skipped-known-good-rollback')
  self.assertFalse(self.c.db.execute("select 1 from control_commands where kind='process.deployment_thought' and state='succeeded'").fetchone())
