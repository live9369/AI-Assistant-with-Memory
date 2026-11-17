"""Core lifecycle checks only: temporary state, no model calls."""
import json
import fcntl
import os
import tempfile
import time
import unittest
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from digital_life.application.lifecycle.panel_control import PanelControl, Operation, write, folder, TERMINAL
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.monitoring.instance_settings import InstanceSettings
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.domain.contracts import Conflict, Forbidden


class PanelControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'instance'
        self.s=Store.prepare(self.root);self.c=Control(self.root,self.s.instance_id)
        self.addCleanup(self.temp.cleanup);self.addCleanup(self.s.close);self.addCleanup(self.c.close)
    def section(self):return next(s for s in InstanceSettings(self.s).sections() if s['id']=='identity')
    def request(self):
        section=self.section()
        return dict(values=dict(section['values'],name='新名字'),expected_revision=section['revision'],reason='临时配置验收',confirmed=True)
    def wait(self,timeout=60):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            status=PanelControl(self.s).status()
            if status['operation'] and status['operation']['state'] in TERMINAL:return status['operation']
            time.sleep(.1)
        self.fail('operation timeout')
    def test_lock_and_stale_configuration_do_not_stop(self):
        with self.assertRaises(Forbidden):PanelControl(self.s).submit('start',{'confirmed':True})
        (self.root/'WAKE_DISABLED').unlink()
        body=self.request();body['expected_revision']='old'
        with self.assertRaises(Conflict):PanelControl(self.s).submit('apply',body,'identity')
        self.assertEqual(self.c.state()['control_revision'],0)
    def test_failed_start_restores_only_configuration(self):
        (self.root/'WAKE_DISABLED').unlink();body=self.request();old=self.section()['values']
        value=dict(id='failure-test',action='apply',section='identity',state='queued',started_at='test')
        write(folder(self.root)/'request.json',dict(operation=value,body=body,before=self.section()))
        before=self.s.instance_id
        with patch('digital_life.application.lifecycle.panel_control.Releases.stage',return_value='fixture-release'),patch.object(Operation,'launch',side_effect=[Conflict('fixture failed'),{'switched':True}]):
            Operation(self.root).run()
        result=PanelControl(self.s).status()['operation']
        self.assertEqual(result['state'],'recovered');self.assertIn('fixture failed',result['error'])
        self.assertEqual(self.section()['values'],old);self.assertEqual(self.s.instance_id,before)
        self.assertEqual(len(self.s.rows('thought_requests')),0)
    def test_concurrent_operation_rejected(self):
        fd=os.open(folder(self.root)/'operation.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(Conflict):PanelControl(self.s).submit('stop',{'confirmed':True})
        finally:os.close(fd)
    def test_external_stop_cancels_resume_and_restores_config(self):
        (self.root/'WAKE_DISABLED').unlink();old=self.section()['values']
        value=dict(id='stop-wins',action='apply',section='identity',state='queued',started_at='test')
        write(folder(self.root)/'request.json',dict(operation=value,body=self.request(),before=self.section()))
        def stop_then_fail(operation,deployment,recovery=False):
            operation.c.stop('external-user-stop');raise Conflict('user stopped')
        with patch('digital_life.application.lifecycle.panel_control.Releases.stage',return_value='fixture-release'),patch.object(Operation,'launch',stop_then_fail):Operation(self.root).run()
        self.assertEqual(PanelControl(self.s).status()['operation']['state'],'recovered')
        self.assertTrue(self.c.state()['user_stopped']);self.assertEqual(self.section()['values'],old)

    def test_real_process_start_apply_stop_preserves_data(self):
        class Inventory(BaseHTTPRequestHandler):
            def do_GET(handler):
                raw=b'{"models":[{"name":"offline-fixture"}]}'
                handler.send_response(200);handler.send_header('Content-Length',str(len(raw)));handler.end_headers();handler.wfile.write(raw)
            def log_message(*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Inventory)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        with self.s.tx():InstanceSettings(self.s)._config(model={'backend':'ollama','model':'offline-fixture','base_url':'http://127.0.0.1:'+str(server.server_port)})
        (self.root/'WAKE_DISABLED').unlink()
        try:
            PanelControl(self.s).submit('start',{'confirmed':True})
            result=self.wait();self.assertEqual(result['state'],'succeeded',result)
            first=self.c.state()['active_process_run_id'];self.assertTrue(first)
            PanelControl(self.s).submit('apply',self.request(),'identity')
            result=self.wait();self.assertEqual(result['state'],'succeeded',result)
            self.assertEqual(self.section()['values']['name'],'新名字')
            second=self.c.state()['active_process_run_id'];self.assertTrue(second);self.assertNotEqual(first,second)
            self.assertEqual(len(self.s.rows('thought_requests')),0)
            PanelControl(self.s).submit('stop',{'confirmed':True})
            result=self.wait();self.assertEqual(result['state'],'succeeded',result)
            self.assertIsNone(self.c.state()['active_process_run_id'])
        finally:
            self.c.stop('test-cleanup')
            deadline=time.monotonic()+8
            while self.c.state()['active_process_run_id'] and time.monotonic()<deadline:time.sleep(.1)

if __name__=='__main__':unittest.main()
