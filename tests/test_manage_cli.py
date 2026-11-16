import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from digital_life.entrypoints import manage

class ManageCliTests(unittest.TestCase):
 def test_setup_config_does_not_overwrite_or_create_instance(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'config.json'
   with patch.object(manage,'codex_path',return_value='/trusted/codex'),contextlib.redirect_stdout(io.StringIO()):manage.setup_codex(p,'fixture')
   self.assertEqual(json.loads(p.read_text())['executable'],'/trusted/codex')
   with self.assertRaises(ValueError):manage.setup_codex(p,'other')
   self.assertFalse((Path(tmp)/'runtime.sqlite').exists())
 def test_rejected_wake_keeps_lock(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'runtime.sqlite').touch();lock=root/'WAKE_DISABLED';lock.write_text('keep')
   with patch.object(manage,'run',return_value={}) as run,contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaises(ValueError):manage.wake(root,'wrong')
   self.assertEqual(lock.read_text(),'keep');self.assertEqual(run.call_count,1)
 def test_probe_failure_cannot_unlock(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'runtime.sqlite').touch();lock=root/'WAKE_DISABLED';lock.write_text('keep')
   def run(data,*args,**kw):
    if args[0]=='model-probe':raise ValueError('offline')
    return {}
   with patch.object(manage,'run',side_effect=run),contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaises(ValueError):manage.wake(root,'WAKE '+root.name)
   self.assertEqual(lock.read_text(),'keep')
 def test_launch_failure_stops_and_relocks_fixture_only(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'runtime.sqlite').touch();lock=root/'WAKE_DISABLED';lock.write_text('keep');calls=[]
   def run(data,*args,**kw):
    calls.append(args[0])
    if args[0]=='stage-release':return {'deployment':'fixture'}
    if args[0]=='deploy':
     self.assertFalse(lock.exists());raise ValueError('failed')
    return {}
   with patch.object(manage,'run',side_effect=run),contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaises(ValueError):manage.wake(root,'WAKE '+root.name)
   self.assertTrue(lock.exists());self.assertEqual(calls[-1],'stop')
 def test_submit_generates_unique_key_and_does_not_run(self):
  with patch.object(manage,'run') as run:
   self.assertEqual(manage.main(['submit','fixture task']),0)
  args=run.call_args.args;self.assertEqual(args[1],'submit');self.assertTrue(args[-1].startswith('cli-'))
 def test_real_prepare_and_offline_config_in_temporary_instance(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'instance';cfg=Path(tmp)/'config.json';cfg.write_text(json.dumps({'backend':'codex_cli','model':'fixture','executable':'/trusted/codex','enabled':False}))
   self.assertEqual(manage.main(['--data',str(root),'prepare','--config',str(cfg)]),0)
   self.assertTrue((root/'WAKE_DISABLED').exists())
   with contextlib.redirect_stderr(io.StringIO()):self.assertEqual(manage.main(['--data',str(root),'prepare','--config',str(cfg)]),1)
   self.assertEqual(manage.main(['--data',str(root),'configure','--config',str(cfg)]),0)

 def test_failed_deployment_json_also_relocks(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'runtime.sqlite').touch();lock=root/'WAKE_DISABLED';lock.write_text('keep')
   def run(data,*args,**kw):
    if args[0]=='stage-release':return {'deployment':'fixture'}
    if args[0]=='deploy':return {'switched':False}
    return {}
   with patch.object(manage,'run',side_effect=run),contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaises(ValueError):manage.wake(root,'WAKE '+root.name)
   self.assertTrue(lock.exists())
