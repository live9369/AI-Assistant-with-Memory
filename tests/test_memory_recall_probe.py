"""Isolated recall runner tests; fake transport, no provider or tool actions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from digital_life.infrastructure.llm.codex_cli import CodexReasoner
from scripts.development.run_memory_recall_probe import worker,write,digest

class FakeCodex(CodexReasoner):
    def __init__(self,invalid=False):
        super().__init__({'model':'mock','executable':'/not-used/codex','enabled':True})
        self.calls=0;self.invalid=invalid
    def run(self,args,root,stdin=''):
        import re
        self.calls+=1;payload=json.loads(stdin[stdin.index('{'):]);answer='UNKNOWN'
        body='\n'.join(m['content'] for m in payload['selected_memories'])
        pattern='取件码是 ([0-9a-f]{12})' if '青岚仓库' in payload['task'] else '维护口令是 ([0-9a-f]{12})'
        match=re.search(pattern,body)
        if match:answer=match[1]
        output={'schema_version':1,'action':{'tool':'wait','arguments':{'reason':'recall diagnostic'}},'explanation':7 if self.invalid else json.dumps({'answer':answer})}
        return '\n'.join(json.dumps(e) for e in [
            {'type':'thread.started','thread_id':'mock-session-'+str(self.calls)},
            {'type':'item.completed','item':{'type':'agent_message','text':json.dumps(output)}},
            {'type':'turn.completed','usage':{'input_tokens':12000,'output_tokens':50}}])

class MemoryRecallProbeTests(unittest.TestCase):
    def run_fake(self,real=True,invalid=False):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);p=Path(tmp.name)
        write(p/'manifest.json',{'source_hashes':{},'real_codex':real,'model_config':{'backend':'codex_cli','model':'mock','executable':'/not-used/codex','enabled':True,'timeout':120},'tokens_per_call':32768,'total_reserved_tokens':196608})
        (p/'manifest.sha256').write_text(digest(p/'manifest.json')+'\n')
        with patch('digital_life.infrastructure.llm.inference.configured_reasoner',return_value=FakeCodex(invalid)) as factory:
            status=worker(p)
        return p,status,json.loads((p/'result.json').read_text()),factory.call_count
    def test_actual_recall_path_and_paired_inputs(self):
        p,status,r,_=self.run_fake()
        self.assertEqual(status,0);self.assertEqual(r['functional_checks'],{'passed':11,'total':11})
        self.assertEqual(r['real_model_completed'],6)
        self.assertEqual(r['with_recall_correct'],2);self.assertEqual(r['without_recall_correct'],0)
        calls=json.loads((p/'model-calls.json').read_text())
        self.assertTrue(all('transport_observation' in c for c in calls))
        self.assertTrue((p/'model-instance/WAKE_DISABLED').exists())
        self.assertEqual(r['thought_results_accepted'],0)
    def test_invalid_output_preserves_transport_usage_and_stops_without_retry(self):
        p,status,r,_=self.run_fake(invalid=True)
        self.assertEqual(status,1);self.assertEqual(r['real_model_attempts'],1)
        self.assertEqual(r['actual_tokens'],12050);self.assertEqual(r['unknown_usage_attempts'],0)
        calls=json.loads((p/'model-calls.json').read_text())
        self.assertEqual(calls[0]['state'],'failed')
        self.assertIn('final_text',calls[0]['transport_observation'])
        self.assertTrue((p/'model-instance/WAKE_DISABLED').exists())
    def test_offline_probe_never_constructs_a_reasoner(self):
        _,status,r,count=self.run_fake(real=False)
        self.assertEqual(status,0);self.assertEqual(count,0)
        self.assertEqual(r['real_model_attempts'],0)
