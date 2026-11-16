"""Foreground orchestration with isolated files and stub processes only."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from digital_life.entrypoints import managed_session as session
from digital_life.entrypoints import manage
from digital_life.infrastructure.processes.locks import exclusive


class ManagedSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in ('runtime.sqlite','control.sqlite'):(self.root/name).write_bytes(b'unchanged')
        self.run=Mock(return_value={});self.server=Mock();self.child=Mock(pid=12345,returncode=0)
        self.child.poll.return_value=0
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.pid=self.stack.enter_context(patch.object(session,'active_pid',return_value=None))
        self.create=self.stack.enter_context(patch('digital_life.entrypoints.http.create_server',return_value=self.server))
        self.spawn=self.stack.enter_context(patch.object(session.subprocess,'Popen',return_value=self.child))
        self.stop=self.stack.enter_context(patch.object(session,'stop_child'))
        self.stack.enter_context(patch.object(session.threading,'Thread'))

    def start(self,**kw):
        return session.start(self.root,self.root,self.run,confirmation='WAKE '+self.root.name,**kw)

    def test_confirmed_existing_instance_uses_original_wake_and_relocks(self):
        self.start()
        args=self.spawn.call_args.args[0]
        self.assertEqual(args[-3:],['wake','--confirm','WAKE '+self.root.name])
        self.assertTrue(self.spawn.call_args.kwargs['start_new_session'])
        self.stop.assert_called_once_with(self.child)
        self.assertEqual([x.args[1] for x in self.run.call_args_list],['inspect','stop'])
        self.assertTrue((self.root/'WAKE_DISABLED').exists())
        self.assertEqual((self.root/'runtime.sqlite').read_bytes(),b'unchanged')
        self.server.shutdown.assert_called_once();self.server.server_close.assert_called_once()

    def test_invalid_confirmation_never_binds_or_starts(self):
        with self.assertRaises(ValueError):session.start(self.root,self.root,self.run,confirmation='no')
        self.create.assert_not_called();self.spawn.assert_not_called()

    def test_missing_instance_does_not_create(self):
        (self.root/'runtime.sqlite').unlink()
        with self.assertRaises(ValueError):self.start()
        self.run.assert_not_called();self.spawn.assert_not_called()
        self.assertFalse((self.root/'runtime.sqlite').exists())

    def test_usage_review_marker_blocks_before_inspect_and_keeps_lock(self):
        marker=self.root/'MODEL_USAGE_REVIEW_REQUIRED';marker.write_text('unknown usage')
        lock=self.root/'WAKE_DISABLED';lock.write_text('keep')
        with self.assertRaisesRegex(ValueError,'MODEL_USAGE_REVIEW_REQUIRED'):self.start()
        self.run.assert_not_called();self.create.assert_not_called();self.spawn.assert_not_called()
        self.assertEqual(marker.read_text(),'unknown usage');self.assertEqual(lock.read_text(),'keep')

    def test_new_codex_config_uses_post_usage_without_overwriting_existing(self):
        import json
        config=self.root/'new-codex.json'
        with patch.object(manage,'codex_path',return_value='/fixture/codex'):
            manage.setup_codex(config,'fixture')
        body=json.loads(config.read_text())
        self.assertEqual(body['budget_mode'],'post_usage')
        self.assertEqual(body['max_input_bytes'],262144)
        with self.assertRaises(ValueError):manage.setup_codex(config,'other')
        self.assertEqual(json.loads(config.read_text()),body)

    def test_codex_post_usage_rejects_old_schema_before_panel_or_runtime(self):
        (self.root/'runtime.sqlite').unlink()
        with session.sqlite3.connect(self.root/'runtime.sqlite') as db:db.execute('PRAGMA user_version=2')
        self.run.return_value={'configuration':{'model':{'backend':'codex_cli','budget_mode':'post_usage'}}}
        with self.assertRaisesRegex(ValueError,'start 不自动升级'):self.start()
        self.create.assert_not_called();self.spawn.assert_not_called();self.pid.assert_not_called()
        with session.sqlite3.connect(self.root/'runtime.sqlite') as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)

    def test_codex_post_usage_accepts_strict_schema_without_migration(self):
        (self.root/'runtime.sqlite').unlink()
        with session.sqlite3.connect(self.root/'runtime.sqlite') as db:db.execute('PRAGMA user_version=4')
        self.run.return_value={'configuration':{'model':{'backend':'codex_cli','budget_mode':'post_usage'}}}
        self.start();self.spawn.assert_called_once()
        with session.sqlite3.connect(self.root/'runtime.sqlite') as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)

    def test_port_conflict_never_starts_runtime(self):
        self.create.side_effect=OSError('in use')
        with self.assertRaisesRegex(ValueError,'端口'):self.start()
        self.spawn.assert_not_called()
        self.assertEqual(self.run.call_count,1)

    def test_existing_runtime_only_panel_and_ctrl_c_keeps_it(self):
        self.pid.return_value=222
        with patch.object(session.os,'kill'),patch.object(session.time,'sleep',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.start()
        self.spawn.assert_not_called();self.stop.assert_not_called()
        self.assertEqual(self.run.call_count,1)
        self.assertFalse((self.root/'WAKE_DISABLED').exists())
        self.server.server_close.assert_called_once()

    def test_ctrl_c_cleans_owned_child(self):
        self.child.poll.return_value=None
        with patch.object(session.time,'sleep',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.start()
        self.stop.assert_called_once_with(self.child)
        self.assertTrue((self.root/'WAKE_DISABLED').exists())
        self.server.server_close.assert_called_once()

    def test_failure_cleanup_also_when_stop_command_fails(self):
        self.child.returncode=1
        def run(data,command,**kw):
            if command=='stop':raise ValueError('stop failed')
            return {}
        with self.assertRaises(ValueError):session.start(self.root,self.root,run,confirmation='WAKE '+self.root.name)
        self.assertTrue((self.root/'WAKE_DISABLED').exists())
        self.server.server_close.assert_called_once()

    def test_duplicate_foreground_session_cannot_spawn(self):
        with exclusive(self.root,'start-session.lock'):
            with self.assertRaises(ValueError):self.start()
        self.spawn.assert_not_called();self.create.assert_not_called()

    def test_spawn_failure_preserves_lock_and_closes_panel(self):
        lock=self.root/'WAKE_DISABLED';lock.write_text('original')
        self.spawn.side_effect=OSError('cannot spawn')
        with self.assertRaises(OSError):self.start()
        self.assertEqual(lock.read_text(),'original')
        self.assertEqual(self.run.call_count,1)
        self.server.server_close.assert_called_once()

    def test_cleanup_cannot_stop_unrelated_runtime(self):
        self.pid.side_effect=[None,999]
        with patch.object(session.os,'getpgid',return_value=888):self.start()
        self.assertEqual(self.run.call_count,1)
        self.assertFalse((self.root/'WAKE_DISABLED').exists())

    def test_failed_panel_thread_does_not_wait_for_unstarted_server(self):
        with patch.object(session.threading,'Thread') as thread:
            thread.return_value.start.side_effect=RuntimeError('cannot start thread')
            with self.assertRaises(RuntimeError):self.start()
        self.server.shutdown.assert_not_called();self.server.server_close.assert_called_once()

    def test_open_browser_and_main_options(self):
        with patch.object(session.webbrowser,'open') as browser:self.start(open_browser=True,port=8766)
        browser.assert_called_once_with('http://127.0.0.1:8766/')
        with patch.object(session,'start') as start:
            self.assertEqual(manage.main(['--data',str(self.root),'start','--confirm','WAKE '+self.root.name,'--open','--port','8766']),0)
        self.assertEqual(start.call_args.kwargs['port'],8766)
        self.assertTrue(start.call_args.kwargs['open_browser'])


class ManagedSessionProcessTests(unittest.TestCase):
    def test_owned_real_stub_process_receives_group_interrupt(self):
        # No application runtime, database, provider or model is involved.
        child=session.subprocess.Popen([session.sys.executable,'-c',
            'import signal,time; signal.signal(signal.SIGINT,lambda *args:exit(0)); '
            'print("ready",flush=True); time.sleep(30)'],start_new_session=True,
            stdout=session.subprocess.PIPE,stderr=session.subprocess.DEVNULL,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'ready')
            session.stop_child(child)
            self.assertEqual(child.poll(),0)
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)
            child.stdout.close()
