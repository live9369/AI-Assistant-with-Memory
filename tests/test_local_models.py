"""Offline transport contract tests; never contact a real model or wake an instance."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from primordial00.models import OllamaReasoner,inspect,resolve,validate_output

class Reply(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self,*args): self.close()

class LocalModelTests(unittest.TestCase):
    def test_fresh_request_and_no_history(self):
        model=OllamaReasoner('example')
        a=model.payload({'task':'first','model':model.name})
        b=model.payload({'task':'second','model':model.name})
        self.assertEqual(len(a['messages']),2); self.assertEqual(len(b['messages']),2)
        self.assertNotIn('first',b['messages'][1]['content'])
        self.assertEqual(a['keep_alive'],0)
        with self.assertRaises(ValueError): model.payload({'model':model.name,'history':[]})
    def test_mock_transport_validates_exact_model_and_json(self):
        model=OllamaReasoner('example'); observed=[]
        result={'schema_version':1,'action':{'kind':'write_note','text':'output'},'explanation':'test'}
        class Offline:
            def open(self,request,timeout):
                observed.append(json.loads(request.data))
                return Reply(json.dumps({'model':'example','done':True,'message':{'content':json.dumps(result)}}).encode())
        model.opener=Offline()
        self.assertEqual(model.generate({'task':'only-current','model':model.name}),result)
        self.assertEqual(observed[0]['model'],'example')
    def test_remote_and_redirecting_routes_rejected(self):
        for url in ('https://example.com','http://example.com','http://user@localhost:11434','http://localhost:11434/other'):
            with self.assertRaises(ValueError): OllamaReasoner('example',url)
    def test_unknown_tools_and_invalid_outputs_rejected(self):
        for result in ({'schema_version':True,'action':{},'explanation':''},
            {'schema_version':1,'action':{'kind':'shell','text':'x'},'explanation':'x'}):
            with self.assertRaises(ValueError): validate_output(result)
    def test_config_check_does_not_initialize_or_connect(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp); (path/'model.json').write_text(json.dumps({'backend':'ollama','model':'example'}))
            report=inspect(path)
            self.assertFalse(report['inference_executed']); self.assertFalse(report['service_started'])
            self.assertEqual(report['status'],'configured_not_connected')
            self.assertFalse((path/'runtime.sqlite').exists())
    def test_invalid_config_never_silently_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'model.json').write_text(json.dumps({'backend':'ollama','model':'example','base_url':'https://external.invalid'}))
            with self.assertRaises(ValueError): resolve(tmp)

if __name__=='__main__': unittest.main(verbosity=2)
