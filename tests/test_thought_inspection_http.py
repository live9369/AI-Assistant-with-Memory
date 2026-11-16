import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.entrypoints.http import create_server

class ThoughtHttpTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'instance';s=Store.prepare(self.root);(s.root/'WAKE_DISABLED').unlink()
  class Model:
   name='fixture'
   def generate(self,request):return {'schema_version':1,'explanation':'fixture response','action':{'tool':'wait','arguments':{'reason':'wait'}}}
  self.activity=Engine(s).submit('fixture input','fixture');Engine(s).think(self.activity,Model());self.ref=s.rows('thought_requests')[0]['id'];(s.root/'WAKE_DISABLED').write_text('test lock');s.close()
  self.server=create_server(self.root,0);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.token=(self.root/'controller.token').read_text().strip();self.addCleanup(self.tmp.cleanup);self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
 def get(self,path,authorized=True):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10);c.request('GET',path,headers={'Authorization':'Bearer '+self.token} if authorized else {});r=c.getresponse();data=json.loads(r.read());status=r.status;c.close();return status,data
 def test_inspection_requires_authentication_and_scopes_instance(self):
  self.assertEqual(self.get('/v1/thoughts/'+self.ref,False)[0],403);self.assertEqual(self.get('/v1/thoughts/foreign')[0],404)
  status,data=self.get('/v1/activities/'+self.activity+'/thoughts');self.assertEqual(status,200);self.assertEqual(data['items'][0]['id'],self.ref)
 def test_full_details_are_observed_without_wake_or_generation(self):
  status,data=self.get('/v1/thoughts/'+self.ref);self.assertEqual(status,200);self.assertEqual(data['input']['value']['task'],'fixture input');self.assertEqual(data['results'][0]['response']['value']['explanation'],'fixture response');self.assertTrue(data['read_only']);self.assertTrue((self.root/'WAKE_DISABLED').exists())
