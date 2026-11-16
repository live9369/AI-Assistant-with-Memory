"""Damaged joint evidence must replace stale success with a failed current gate."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.verification import verify_life_acceptance as gate

class LifeGateFailureTests(unittest.TestCase):
 def test_missing_joint_replaces_previous_success_and_keeps_validating(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'docs/plan').mkdir(parents=True);(root/'outputs/acceptance').mkdir(parents=True)
   plan=root/'docs/plan/task-status.json';plan.write_text(json.dumps({'tasks':[{'id':'T13','status':'complete'}]}));out=root/'outputs/acceptance/development-t13.json';out.write_text('{"passed":true}')
   with patch.object(gate,'ROOT',root),patch.object(gate,'sources',return_value={}),patch.object(gate,'inspect_plan',return_value={'next_ready':['T13']}),patch.object(gate.unittest.defaultTestLoader,'discover',return_value=unittest.TestSuite()),patch('sys.argv',['gate','--joint',str(root/'missing')]),contextlib.redirect_stdout(io.StringIO()):code=gate.main()
   result=json.loads(out.read_text());self.assertEqual(code,1);self.assertFalse(result['passed']);self.assertIn('FileNotFoundError',result['joint_error']);self.assertEqual(json.loads(plan.read_text())['tasks'][0]['status'],'validating')
