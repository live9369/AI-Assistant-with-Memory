"""Actual Git and worker tests, no remote or model calls."""
import json
from tests.test_project_access import ProjectTests
from digital_life.domain.contracts import sha
class VersionTests(ProjectTests):
 def evidence(self,action):
  a,r=self.propose(action);result=self.e.execute(r['action_id']);self.assertEqual(result['state'],'succeeded')
  row=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE activity_id=? AND event_type='task_loop.observed' ORDER BY event_seq DESC LIMIT 1",(a,)).fetchone();receipt=self.s.read_artifact(self.s.read_artifact(row[0])['receipt']);return receipt['evidence']
 def test_save_diff_restore_keeps_new_history_and_checkpoints(self):
  self.configure();file=self.project/'sample.txt';file.write_text('first\n')
  saved=self.evidence({'tool':'project_version_save','arguments':{'paths':['sample.txt'],'message':'initial version','expected_head':''}});first=saved['version']
  edited=self.evidence({'tool':'project_edit','arguments':{'path':'sample.txt','old_text':'first','new_text':'second','expected_sha256':sha('first\n')}});self.assertNotEqual(edited['version'],first)
  diff=self.evidence({'tool':'project_version_diff','arguments':{'path':'sample.txt','version':first}});self.assertIn('+second',diff['diff'])
  status=self.evidence({'tool':'project_version_status','arguments':{'paths':['sample.txt']}});self.assertEqual(status['files'][0]['state'],'unchanged')
  restored=self.evidence({'tool':'project_version_restore','arguments':{'path':'sample.txt','version':first,'expected_sha256':sha('second\n'),'expected_head':status['head'],'message':'restore first version'}})
  self.assertEqual(file.read_text(),'first\n');self.assertNotEqual(restored['version'],first)
  history=self.evidence({'tool':'project_version_log','arguments':{'limit':10}})['history'];self.assertGreaterEqual(len(history),3);self.assertIn(first,[h['version'] for h in history]);self.assertFalse((self.project/'.git').exists())
 def test_stale_head_and_current_exclusions_are_preserved(self):
  self.configure();(self.project/'sample.txt').write_text('one')
  first=self.evidence({'tool':'project_version_save','arguments':{'paths':['sample.txt'],'message':'one','expected_head':''}})['version'];(self.project/'sample.txt').write_text('two')
  self.evidence({'tool':'project_version_save','arguments':{'paths':['sample.txt'],'message':'two','expected_head':first}})
  a,r=self.propose({'tool':'project_version_save','arguments':{'paths':['sample.txt'],'message':'stale','expected_head':first}});self.assertNotEqual(self.e.execute(r['action_id'])['state'],'succeeded')
  self.access.configure(str(self.project),self.s.config()['controller'],auto_approve=True,exclude=['sample.txt'])
  a,r=self.propose({'tool':'project_version_diff','arguments':{'path':'sample.txt','version':first}});self.assertNotEqual(self.e.execute(r['action_id'])['state'],'succeeded')
