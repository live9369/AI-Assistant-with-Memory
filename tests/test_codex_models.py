"""Isolated protocol and process fault injection; no provider requests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.infrastructure.llm.inference import configured_reasoner
from digital_life.application.runtime.configuration import validate_model_config,configure_model
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.domain.contracts import ContractError,Forbidden

OUTPUT={'schema_version':1,'action':{'tool':'wait','arguments':{'reason':'fixture'}},'explanation':'fixture'}
def events(output=OUTPUT):
 return [{'type':'thread.started','thread_id':'fixture-session'},{'type':'item.completed','item':{'type':'agent_message','text':json.dumps(output)}},{'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':5}}]
def wire(items):return '\n'.join(json.dumps(i) for i in items)
class CodexTests(unittest.TestCase):
 def config(self,**kw):return dict({'backend':'codex_cli','model':'fixture','enabled':True,'executable':'/fixture/codex'},**kw)
 def model(self,**kw):return configured_reasoner(self.config(**kw))
 def test_offline_validation_and_opt_in(self):
  m=validate_model_config(self.config(enabled=False))
  with self.assertRaises(Forbidden):m.generate({'model':m.name})
  for kw in ({'executable':'codex'},{'timeout':True},{'timeout':float('nan')},{'enabled':'true'},{'context_window':0},{'api_key':'secret'}):
   with self.assertRaises(ContractError):self.model(**kw)
 def test_byte_limit_name_and_legacy_migration(self):
  self.assertEqual(self.model(max_input_bytes=32768).max_input_bytes,32768)
  self.assertEqual(self.model(context_window=32768).max_input_bytes,32768)
  self.assertEqual(self.model(max_input_bytes=32768,context_window=32768).max_input_bytes,32768)
  for kw in ({'max_input_bytes':True},{'max_input_bytes':0},{'max_input_bytes':262145},{'max_input_bytes':32768,'context_window':16384}):
   with self.assertRaises(ContractError):self.model(**kw)
  with tempfile.TemporaryDirectory() as tmp:
   s=Store.prepare(Path(tmp)/'instance')
   try:
    configure_model(s,self.config(context_window=32768),s.config()['controller'],check_available=False)
    saved=s.config()['model']
    self.assertEqual(saved['max_input_bytes'],32768);self.assertNotIn('context_window',saved)
   finally:s.close()
 def test_independent_payload_and_process_flags(self):
  m=self.model()
  with patch.object(m,'run',return_value=wire(events())) as run:
   m.generate({'model':m.name,'task':'private-one'});m.generate({'model':m.name,'task':'second'})
   args=run.call_args.args[0];self.assertIn('--ephemeral',args);self.assertIn('--ignore-user-config',args);self.assertIn('read-only',args);self.assertIn('--output-schema',args)
   self.assertNotIn('private-one',run.call_args.args[2]);self.assertNotIn('resume',args);self.assertNotIn('fork',args)
   self.assertEqual(m.last_usage['output_tokens'],5)
 def test_continuation_size_and_routing(self):
  m=self.model(context_window=2048)
  for k in ('history','messages','thread_id','previous_response_id','conversation_id'):
   with self.assertRaises(ContractError):m.payload({'model':m.name,k:[]})
  with self.assertRaises(ContractError):m.payload({'model':'wrong'})
  with self.assertRaises(ContractError):m.payload({'model':m.name,'task':'x'*3000})
 def test_failure_events_and_bad_outputs(self):
  m=self.model()
  cases=[[],events()[:-1],[{'type':'turn.failed','error':'credential-secret'}],events({'schema_version':1,'action':{'tool':'shell','arguments':{}},'explanation':'bad'}),events()+[{'type':'item.completed','item':{'type':'command_execution'}}],events()+[{'type':'turn.completed','usage':{'input_tokens':-1}}]]
  for case in cases:
   with patch.object(m,'run',return_value=wire(case)):
    with self.assertRaises(ContractError) as caught:m.generate({'model':m.name})
    self.assertNotIn('credential-secret',str(caught.exception));self.assertIsNone(m.last_usage)
  with patch.object(m,'run',return_value='not json'):
   with self.assertRaises(ContractError):m.generate({'model':m.name})
 def test_login_probe_never_generates(self):
  m=self.model()
  def login(args,root,stdin=''):
   self.assertEqual(args,['login','status']);(root/'stderr').write_text('Logged in using ChatGPT');return ''
  with patch.object(m,'run',side_effect=login):self.assertFalse(m.probe()['inference_executed'])
  def api_login(args,root,stdin=''):
   (root/'stderr').write_text('Logged in using API key');return ''
  with patch.object(m,'run',side_effect=api_login):
   with self.assertRaises(ContractError):m.probe()
 def test_real_process_failure_and_timeout_are_sanitized(self):
  import sys
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);m=self.model(executable=sys.executable,timeout=.1)
   with self.assertRaisesRegex(ContractError,'codex_timeout'):m.run(['-c','import time; time.sleep(3)'],root)
   with self.assertRaisesRegex(ContractError,'codex_process_failed') as caught:m.run(['-c','import sys; print("secret",file=sys.stderr);sys.exit(1)'],root)
   self.assertNotIn('secret',str(caught.exception))
   m.executable='/missing/codex'
   with self.assertRaisesRegex(ContractError,'unavailable'):m.run([],root)
 def test_versioned_configuration_keeps_wake_lock(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store.prepare(Path(tmp)/'instance',model_config=self.config(enabled=False))
   try:
    configure_model(s,self.config(enabled=True),s.config()['controller'],check_available=False)
    self.assertEqual(s.config()['model']['backend'],'codex_cli');self.assertTrue((s.root/'WAKE_DISABLED').exists())
   finally:s.close()

 def test_management_cannot_execute_arbitrary_program(self):
  from digital_life.application.monitoring.management import Management,ManagementError
  with tempfile.TemporaryDirectory() as tmp:
   s=Store.prepare(Path(tmp)/'instance')
   try:
    with self.assertRaises(ManagementError):Management(s).validate_model({'configuration':self.config()})
   finally:s.close()
 def test_wire_schema_requires_optional_domain_path(self):
  m=self.model()
  def inspect(args,root,stdin=''):
   schema=json.loads(Path(args[args.index('--output-schema')+1]).read_text())
   for item in schema['properties']['action']['anyOf']:
    obj=item['properties']['arguments'];self.assertEqual(set(obj['required']),set(obj['properties']))
   return wire(events())
  with patch.object(m,'run',side_effect=inspect):m.generate({'model':m.name})
