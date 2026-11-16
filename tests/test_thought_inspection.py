import json
import tempfile
from pathlib import Path
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.monitoring.thought_inspection import ThoughtInspection
from digital_life.application.monitoring.management import ManagementError
from digital_life.domain.contracts import sha,dumps

class ThoughtInspectionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Store.prepare(Path(self.tmp.name)/'instance');(self.s.root/'WAKE_DISABLED').unlink()
  self.addCleanup(self.tmp.cleanup);self.addCleanup(self.s.close);self.view=ThoughtInspection(self.s)
 def thought(self,reasoner=None):
  class Model:
   name='fixture';last_usage={'input_tokens':10,'output_tokens':4,'latency_ms':1}
   def generate(self,request):return {'schema_version':1,'explanation':'你好','action':{'tool':'wait','arguments':{'reason':'等待'}}}
  a=Engine(self.s).submit('hello','fixture');Engine(self.s).think(a,reasoner or Model());return a,self.view.list(a)['items'][0]['id']
 def test_input_output_features_usage_are_historical_and_read_only(self):
  a,ref=self.thought();before=self.s.db.total_changes;data=self.view.detail(ref)
  self.assertTrue(data['input']['available']);self.assertEqual(data['input']['value']['task'],'hello');self.assertEqual(data['results'][0]['response']['value']['explanation'],'你好');self.assertEqual(data['usage'][0]['input_tokens'],10)
  self.assertEqual(self.s.db.total_changes,before);self.assertEqual(data['features'][5]['items'][0]['state'],'empty')
  self.assertFalse(data['raw_provider_response_recorded'])
 def test_full_snapshot_not_truncated_and_credentials_redacted(self):
  a,ref=self.thought();row=self.s.row('thought_requests',ref);payload=self.s.read_artifact(row['request_artifact_id']);payload.update(extra='x'*6000,large=list(range(150)),api_key='never-show')
  secret='test-controller-secret';(self.s.root/'controller.token').write_text(secret);payload['quoted']=secret
  with self.s.tx():
   artifact=self.s.artifact(payload);self.s.db.execute('UPDATE thought_requests SET request_artifact_id=?,request_hash=? WHERE id=?',(artifact,sha(dumps(payload)),ref))
  data=self.view.detail(ref)['input'];self.assertEqual(len(data['value']['extra']),6000);self.assertEqual(len(data['value']['large']),150);self.assertNotIn(secret,json.dumps(data));self.assertNotIn('never-show',json.dumps(data));self.assertFalse(data['truncated'])
 def test_missing_or_mismatched_input_is_not_current_state(self):
  a,ref=self.thought()
  with self.s.tx():self.s.db.execute("UPDATE thought_requests SET request_hash='wrong' WHERE id=?",(ref,))
  value=self.view.detail(ref);self.assertFalse(value['input']['available']);self.assertEqual(value['features'][0]['items'][0]['state'],'unavailable')
  with self.assertRaises(ManagementError):self.view.detail('foreign-request')
 def test_failed_call_has_attempt_error_without_fabricated_output(self):
  class Broken:
   name='fixture'
   def generate(self,request):raise ValueError('fixture')
  a=Engine(self.s).submit('hello','failure')
  with self.assertRaises(ValueError):Engine(self.s).think(a,Broken())
  ref=self.view.list(a)['items'][0]['id'];data=self.view.detail(ref);self.assertEqual(data['attempts'][0]['state'],'failed');self.assertEqual(data['results'],[]);self.assertEqual(data['usage'],[])
