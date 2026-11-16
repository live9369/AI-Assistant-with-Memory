import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.domain.contracts import Forbidden,utc
from digital_life.application.learning.eligibility import slot
from digital_life.infrastructure.llm.codex_cli import CodexReasoner
from digital_life.infrastructure.llm.codex_post_usage import CodexPostUsageProvider

class PostUsageTests(unittest.TestCase):
    def setup_port(self,mode='post_usage'):
        ref=lambda key,kind:{'instance_id':'isolated','id':key,'kind':kind,'revision':slot()}
        route={'configuration':ref('c','configuration_versions'),'model':ref('m','model_versions'),'provider':'codex_cli'}
        r=CodexReasoner({'model':'fixed','enabled':True,'executable':'/not-used/codex','context_window':262144,'budget_mode':mode})
        p=CodexPostUsageProvider(r,route)
        packet={'contract':'TL-ENGINE-THOUGHT-1','request_id':'q','activity_ref':ref('a','activities'),
            'input':{'task':'你好','features':{'personality':{'openness':.5}}},'binding':dict(route,process_run_id='p'),
            'output_schema_version':1,'limits':{'max_input_tokens':20000,'max_output_tokens':100,'max_attempts':1,'max_tool_calls':0,'max_scan':0,'max_items':0,'max_bytes':100000,'deadline':utc(60)}}
        return p,packet
    def envelope(self,usage=None):
        return json.dumps({'model':'fixed','session_id':'new-session','usage':usage if usage is not None else {'input_tokens':12000,'output_tokens':20},
            'body':{'schema_version':1,'explanation':'你好！','action':{'tool':'wait','arguments':{'reason':'聊天'}}}})
    def invoke(self,p,packet,raw):
        with patch('digital_life.infrastructure.llm.fresh_learning.supervised',return_value=raw):
            return p.generate_fresh(packet,before_transport=lambda:None)
    def test_full_reservation_fresh_wire_and_real_usage(self):
        p,q=self.setup_port();self.assertEqual(p.preflight(q),20000)
        out=self.invoke(p,q,self.envelope());self.assertEqual(out['usage']['input_tokens'],12000)
        self.assertFalse(p.accounting_hold);self.assertEqual(p.last_invocation['provider_session_id'],'new-session')
        wire=p.last_invocation['wire'];self.assertFalse(wire['resume']);self.assertFalse(wire['fork'])
        self.assertIn('personality',wire['prompt']);self.assertEqual(wire['packet'],q)
    def test_over_budget_never_returns_body_and_holds(self):
        for usage in ({'input_tokens':20001,'output_tokens':20},{'input_tokens':10,'output_tokens':101}):
            p,q=self.setup_port()
            with self.assertRaises(Forbidden):self.invoke(p,q,self.envelope(usage))
            self.assertTrue(p.accounting_hold);self.assertEqual(p.last_usage['input_tokens'],usage['input_tokens'])
    def test_unknown_usage_hold_without_zero(self):
        p,q=self.setup_port()
        with self.assertRaises(Forbidden):self.invoke(p,q,self.envelope({'output_tokens':20}))
        self.assertTrue(p.accounting_hold);self.assertIsNone(p.last_usage)
        self.assertEqual(p.last_measurements['dimensions']['input_tokens']['status'],'unknown')
    def test_explicit_optin_and_actual_source_guard_required(self):
        p,q=self.setup_port('hard_limits')
        with self.assertRaises(Forbidden):p.preflight(q)
        p,q=self.setup_port()
        with self.assertRaises(Forbidden):p.generate_fresh(q)
        self.assertFalse(p.last_transport_entered)
    def test_timeout_unknown_hold(self):
        p,q=self.setup_port()
        with patch('digital_life.infrastructure.llm.fresh_learning.supervised',side_effect=Forbidden('timeout')):
            with self.assertRaises(Forbidden):p.generate_fresh(q,before_transport=lambda:None)
        self.assertTrue(p.accounting_hold)
    def test_persistent_hold_blocks_execution_and_restart(self):
        from digital_life.infrastructure.persistence.sqlite_store import Store
        from digital_life.application.lifecycle.control_plane import Control
        from digital_life.application.learning.engine import StrictEngine
        with tempfile.TemporaryDirectory() as d:
            s=Store.prepare(d);engine=object.__new__(StrictEngine);engine.s=s
            provider=type('P',(),{'accounting_hold':True})()
            try:
                engine._record_failure({'id':'isolated-request'},None,Forbidden('budget'),provider,None,None)
                self.assertTrue((Path(d)/'MODEL_USAGE_REVIEW_REQUIRED').exists())
                with self.assertRaises(Forbidden):s.assert_execution_allowed()
                c=Control(d,s.instance_id)
                try:
                    self.assertEqual(c.state()['user_stopped'],1)
                    with self.assertRaises(Forbidden):c.assert_startable()
                finally:c.close()
            finally:s.close()
