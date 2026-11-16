"""Real localhost HTTP acceptance on synthetic, locked TemporaryDirectory data."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from panel_fixtures import seed_panel
from digital_life.entrypoints.http import create_server

class ManagementHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'panel';self.refs=seed_panel(self.root)
        self.server=create_server(self.root,0);self.port=self.server.server_port
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.token=(self.root/'controller.token').read_text().strip()
        self.addCleanup(self.tmp.cleanup);self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
    def call(self,path,body=None,method=None,authorized=True,headers=None):
        request_headers={'Authorization':'Bearer '+self.token} if authorized else {}
        request_headers.update(headers or {})
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        raw=json.dumps(body).encode() if body is not None else None
        conn.request(method or ('POST' if body is not None else 'GET'),path,body=raw,headers=request_headers)
        response=conn.getresponse();data=response.read();result=(response.status,dict(response.getheaders()),data);conn.close();return result
    def test_static_assets_and_csp_without_credential(self):
        for path,kind in (('/','text/html'),('/assets/app.js','text/javascript'),('/assets/styles.css','text/css')):
            status,headers,body=self.call(path,authorized=False)
            self.assertEqual(status,200);self.assertIn(kind,headers['Content-Type']);self.assertGreater(len(body),100)
            self.assertIn("script-src 'self'",headers['Content-Security-Policy']);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertTrue((self.root/'WAKE_DISABLED').exists())
    def test_authentication_origin_and_host(self):
        self.assertEqual(self.call('/v1/overview',authorized=False)[0],403)
        self.assertEqual(self.call('/v1/overview',headers={'Authorization':'Bearer é'})[0],403)
        self.assertEqual(self.call('/v1/overview',headers={'Origin':'https://attacker.invalid'})[0],403)
        self.assertEqual(self.call('/v1/overview',headers={'Host':'attacker.invalid'})[0],403)
        self.assertEqual(self.call('/v1/overview',headers={'Origin':'http://127.0.0.1:'+str(self.port)})[0],200)
    def test_list_validation_missing_object_and_invalid_method(self):
        self.assertEqual(self.call('/v1/activities?limit=999')[0],422)
        self.assertEqual(self.call('/v1/activities?limit=1&limit=2')[0],422)
        self.assertEqual(self.call('/v1/activities/missing')[0],404)
        self.assertEqual(self.call('/v1/overview',method='DELETE')[0],405)
        self.assertNotEqual(self.call('/assets/../../controller.token')[0],200)
    def test_approval_decision_is_guarded_and_does_not_execute(self):
        ref=self.refs['approve']['approval'];_,_,raw=self.call('/v1/approvals/'+ref);row=json.loads(raw)
        body={'decision':'approved','expected_revision':row['revision'],'expected_arguments_hash':row['arguments_hash']}
        status,_,raw=self.call('/v1/approvals/'+ref+'/decision',body)
        self.assertEqual(status,200);self.assertFalse(json.loads(raw)['runtime_started'])
        self.assertEqual(self.call('/v1/approvals/'+ref+'/decision',body)[0],409)
        self.assertEqual(list((self.root/'workspace').rglob('*.txt')),[])
    def test_offline_configuration_and_explicit_health(self):
        _,_,raw=self.call('/v1/model/configuration');current=json.loads(raw)
        config={'backend':'remote_chat','enabled':False,'model':'fixture','base_url':'https://not-contacted.invalid/v1','api_key_env':'DIGITAL_LIFE_TEST_ONLY_KEY'}
        body={'configuration':config,'expected_configuration_id':current['configuration_id']}
        self.assertEqual(self.call('/v1/model/validate',{'configuration':config})[0],200)
        status,_,raw=self.call('/v1/model/configuration',body);self.assertEqual(status,200);self.assertFalse(json.loads(raw)['network_requested'])
        self.assertEqual(self.call('/v1/model/configuration',body)[0],409)
        self.assertEqual(self.call('/v1/health/check',{})[0],200)
        _,_,raw=self.call('/v1/health');self.assertEqual(json.loads(raw)['dimensions']['cognition']['state'],'unknown')
    def test_export_redaction_and_body_limit(self):
        status,headers,raw=self.call('/v1/logs/export?event_type=fixture.privacy')
        self.assertEqual(status,200);self.assertIn('ndjson',headers['Content-Type']);self.assertNotIn(b'fixture-never-export-api-secret',raw)
        records=[json.loads(line) for line in raw.splitlines() if line];self.assertEqual(len(records),1);self.assertEqual(records[0]['payload']['safe'],'visible')
        self.assertEqual(self.call('/v1/events',{'text':'x'*70000})[0],413)
    def test_stop_idempotence_and_no_unlock_endpoint(self):
        one=self.call('/v1/control/stop',{'idempotency_key':'same-stop'});two=self.call('/v1/control/stop',{'idempotency_key':'same-stop'})
        self.assertEqual(one[0],200);self.assertEqual(two[0],200);self.assertTrue(json.loads(two[2])['user_stopped'])
        self.assertEqual(self.call('/v1/control/resume',{})[0],404)
        self.assertTrue((self.root/'WAKE_DISABLED').exists())
