import tempfile
from pathlib import Path
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control,Releases
from digital_life.application.lifecycle.release_inspection import release_status

class ReleaseInspectionTests(unittest.TestCase):
 def test_active_snapshot_is_compared_without_deployment(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'instance';project=Path(tmp)/'source';(project/'digital_life').mkdir(parents=True);(project/'digital_life/__init__.py').write_text('VERSION=1\n')
   s=Store.prepare(root);c=Control(root,s.instance_id)
   try:
    deployment=Releases(c).stage(project);result=Releases(c).activate(deployment,lambda _: {'ready':True,'schema_compatible':True});self.assertTrue(result['switched'])
    before=c.db.total_changes;self.assertTrue(release_status(root,project)['source_matches_deployment']);self.assertEqual(c.db.total_changes,before)
    (project/'digital_life/chat.py').write_text('CHAT=True\n');status=release_status(root,project);self.assertFalse(status['source_matches_deployment']);self.assertIn('digital_life/chat.py',status['changed_files']);self.assertEqual(status['deployment_id'],deployment);self.assertTrue((root/'WAKE_DISABLED').exists())
   finally:c.close();s.close()
