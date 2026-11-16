"""Pilot orchestration tests with fake provider; never consume Codex quota."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.development.run_experience_codex_pilot import worker,write,digest

class FakeReasoner:
    name='codex_cli:mock-pilot'
    timeout=120
    def __init__(self,mode):self.mode=mode;self.calls=0
    def generate(self,payload):
        self.calls+=1
        if self.mode=='failure':raise RuntimeError('injected-provider-failure')
        case=payload['measurement_input']['case_id']
        p=[.5,.5] if case.startswith('T') else [0.,1.] if case=='R01' else [1.,0.]
        self.last_usage={'input_tokens':40000 if self.mode=='overage' else 11000,'output_tokens':50}
        self.last_session_id='mock-independent-'+str(self.calls)
        return {'schema_version':1,'action':{'tool':'wait','arguments':{'reason':'measurement'}},'explanation':json.dumps({'probabilities':p})}

class ExperienceCodexPilotTests(unittest.TestCase):
    def run_fake(self,mode):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);p=Path(tmp.name)
        write(p/'manifest.json',{'source_hashes':{},'model_config':{},'tokens_per_call':32768,'parent_token_limit':300000})
        (p/'manifest.sha256').write_text(digest(p/'manifest.json')+'\n')
        with patch('digital_life.infrastructure.llm.inference.configured_reasoner',return_value=FakeReasoner(mode)):
            code=worker(p)
        return p,code,json.loads((p/'result.json').read_text())
    def test_complete_run_measures_actual_snapshot_without_invented_gain(self):
        p,code,r=self.run_fake('normal')
        self.assertEqual(code,0);self.assertEqual(r['real_model_completed'],8)
        self.assertEqual(r['measurement']['gain'],0.)
        self.assertTrue(r['independent_sessions']);self.assertTrue(r['isolated_end_locked'])
        calls=json.loads((p/'evidence/model-calls.json').read_text())
        self.assertTrue(all('model_payload' in c and 'model_output' in c for c in calls))
        self.assertFalse(r['audit']['budget_violations'])
    def test_provider_failure_is_not_retried_and_instance_ends_locked(self):
        p,code,r=self.run_fake('failure')
        self.assertEqual(code,1);self.assertEqual(r['real_model_attempts'],1)
        self.assertEqual(r['real_model_completed'],0);self.assertNotIn('measurement',r)
        self.assertTrue((p/'isolated-instance/WAKE_DISABLED').exists())
        self.assertTrue((p/'evidence/artifacts.json').exists())
    def test_overage_preserves_actual_cost_and_stops_next_dispatch(self):
        _,code,r=self.run_fake('overage')
        self.assertEqual(code,1);self.assertEqual(r['real_model_attempts'],1)
        self.assertEqual(r['known_actual_tokens'],40050)
        self.assertEqual(r['prediction_state']['reason'],'observed-token-overage')
        self.assertTrue(r['isolated_end_locked'])
