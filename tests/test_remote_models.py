"""Remote protocol tests use in-memory HTTP replies only; no provider is contacted."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from digital_life.infrastructure.llm.inference import configured_reasoner,probe
from digital_life.infrastructure.llm.remote_chat import RemoteChatReasoner
from digital_life.infrastructure.persistence.sqlite_store import Store,PROJECT
from digital_life.application.runtime.configuration import configure_model
from digital_life.domain.contracts import ContractError,Forbidden

OUTPUT={'schema_version':1,'action':{'tool':'write_note','arguments':{'path':'proof.txt','text':'remote fixture'}},'explanation':'fixture'}

class Reply(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self,*args): self.close()

class Transport:
    def __init__(self,envelope=None,error=None): self.calls=[]; self.envelope=envelope; self.error=error
    def open(self,request,timeout):
        self.calls.append(request)
        if self.error: raise self.error
        return Reply(json.dumps(self.envelope).encode())

class RemoteModelTests(unittest.TestCase):
    def config(self,**updates):
        return dict({'backend':'remote_chat','enabled':True,'model':'fixture-model','base_url':'https://provider.example/v1','api_key_env':'DIGITAL_LIFE_LLM_API_KEY'},**updates)
    def reasoner(self,**updates):
        reasoner=configured_reasoner(self.config(**updates))
        reasoner.opener=Transport({'model':'fixture-model','choices':[{'finish_reason':'stop','message':{'content':json.dumps(OUTPUT)}}],'usage':{'prompt_tokens':12,'completion_tokens':8}})
        return reasoner
    def test_templates_are_disabled_and_validate_without_credentials_or_network(self):
        for name in ('remote-chat.example.json','remote-json-object.example.json'):
            config=json.loads((PROJECT/'config/examples/llm'/name).read_text())
            model=configured_reasoner(config); model.opener=Transport(error=AssertionError('must not connect'))
            self.assertFalse(model.enabled)
            with self.assertRaises(Forbidden): model.generate({'model':model.name,'task':'fixture'})
            self.assertEqual(model.opener.calls,[])
    def test_stateless_https_request_and_environment_only_credential(self):
        model=self.reasoner()
        with patch.dict(os.environ,{'DIGITAL_LIFE_LLM_API_KEY':'fixture-only-key'}):
            self.assertEqual(model.generate({'model':model.name,'task':'first'}),OUTPUT)
            self.assertEqual(model.generate({'model':model.name,'task':'second'}),OUTPUT)
        requests=model.opener.calls; second=json.loads(requests[1].data)
        self.assertEqual(requests[0].full_url,'https://provider.example/v1/chat/completions')
        self.assertEqual(requests[0].get_header('Authorization'),'Bearer fixture-only-key')
        self.assertEqual(len(second['messages']),2); self.assertNotIn('first',second['messages'][1]['content'])
        self.assertNotIn('fixture-only-key',requests[0].data.decode())
        self.assertEqual(model.last_usage['output_tokens'],8)
    def test_continuation_fields_rejected(self):
        model=self.reasoner()
        for field in ('history','messages','thread_id','previous_response_id','conversation_id'):
            with self.assertRaises(ContractError): model.payload({'model':model.name,field:[]})
    def test_missing_credential_is_not_sent_and_no_fallback(self):
        model=self.reasoner()
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ContractError): model.generate({'model':model.name,'task':'fixture'})
        self.assertEqual(model.opener.calls,[])
    def test_http_credentials_redirectable_url_and_bad_fields_rejected(self):
        for value in ('http://provider.example/v1','https://user:key@provider.example/v1','https://provider.example/v1?key=x','https://provider.example/v1#secret'):
            with self.assertRaises(ContractError): configured_reasoner(self.config(base_url=value))
        with self.assertRaises(ContractError): configured_reasoner(self.config(api_key='forbidden-literal'))
        with self.assertRaises(ContractError): configured_reasoner(self.config(enabled='true'))
    def test_provider_errors_are_sanitized_not_retried(self):
        model=self.reasoner(); model.opener=Transport(error=urllib.error.URLError('provider-echoed-key-DO-NOT-PERSIST'))
        with patch.dict(os.environ,{'DIGITAL_LIFE_LLM_API_KEY':'fixture-only-key'}):
            with self.assertRaises(ContractError) as result: model.generate({'model':model.name,'task':'fixture'})
        self.assertNotIn('DO-NOT-PERSIST',str(result.exception)); self.assertEqual(len(model.opener.calls),1)
    def test_refused_truncated_wrong_model_and_invalid_actions_fail(self):
        for envelope in (
          {'model':'other','choices':[{'finish_reason':'stop','message':{'content':json.dumps(OUTPUT)}}]},
          {'model':'fixture-model','choices':[{'finish_reason':'length','message':{'content':json.dumps(OUTPUT)}}]},
          {'model':'fixture-model','choices':[{'finish_reason':'stop','message':{'content':'{"action":{"tool":"shell"}}'}}]},
        ):
            model=self.reasoner(); model.opener=Transport(envelope)
            with patch.dict(os.environ,{'DIGITAL_LIFE_LLM_API_KEY':'fixture-only-key'}):
                with self.assertRaises(ContractError): model.generate({'model':model.name,'task':'fixture'})
            self.assertIsNone(model.last_usage)
    def test_json_object_and_token_parameter_are_explicit(self):
        model=self.reasoner(response_format='json_object',token_parameter='max_completion_tokens')
        payload=model.payload({'model':model.name,'task':'fixture'})
        self.assertEqual(payload['response_format'],{'type':'json_object'})
        self.assertIn('max_completion_tokens',payload); self.assertNotIn('max_tokens',payload)
    def test_configuration_and_initialization_never_persist_literal_key(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'DIGITAL_LIFE_LLM_API_KEY':'unique-runtime-fixture-secret-74103'}):
            store=Store.prepare(Path(tmp)/'instance',model_config=self.config(enabled=False))
            try:
                configure_model(store,self.config(enabled=False),store.config()['controller'],check_available=False)
                for file in store.root.rglob('*'):
                    if file.is_file(): self.assertNotIn(b'unique-runtime-fixture-secret-74103',file.read_bytes())
                self.assertTrue((store.root/'WAKE_DISABLED').exists())
            finally: store.close()
            with self.assertRaises(ContractError): Store.prepare(Path(tmp)/'invalid',model_config=self.config(api_key='must-not-persist'))
    def test_probe_only_checks_model_inventory(self):
        model=self.reasoner(); model.opener=Transport({'data':[{'id':'fixture-model'}]})
        with patch.dict(os.environ,{'DIGITAL_LIFE_LLM_API_KEY':'fixture-only-key'}): result=model.probe()
        self.assertFalse(result['inference_executed']); self.assertIsNone(model.opener.calls[0].data)
    def test_prepared_thought_cannot_silently_switch_endpoint_under_same_model_name(self):
        from digital_life.application.runtime.engine import Engine
        from digital_life.application.lifecycle.control_plane import Control
        from digital_life.domain.contracts import Conflict
        with tempfile.TemporaryDirectory() as tmp:
            store=Store.prepare(Path(tmp)/'instance',model_config=self.config())
            control=Control(store.root,store.instance_id)
            try:
                (store.root/'WAKE_DISABLED').unlink(); control.resume('temporary-test-only')
                engine=Engine(store); activity=engine.submit('fixture','route-test')
                reasoner=self.reasoner(); engine.prepare(activity,reasoner)
                control.stop('configure-stop')
                configure_model(store,self.config(base_url='https://second-provider.example/v1'),store.config()['controller'],check_available=False)
                control.resume('temporary-resume')
                with self.assertRaises(Conflict): engine.prepare(activity,reasoner)
                self.assertEqual(reasoner.opener.calls,[])
            finally: control.stop('test-finished'); control.close(); store.close()
