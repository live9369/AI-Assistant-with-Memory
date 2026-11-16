"""Opt-in actual local model acceptance; ALL instance writes use TemporaryDirectory."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store,PROJECT
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.runtime.engine import Engine
from digital_life.infrastructure.llm.inference import configured_reasoner,probe,validate
from digital_life.application.telemetry.metrics import Metrics
from digital_life.tools import Policy
from digital_life.infrastructure.llm.model_service import ModelService
from digital_life.application.lifecycle.control_plane import Releases
from digital_life.application.lifecycle.deployment import Deployment

ENABLED=os.environ.get('DIGITAL_LIFE_REAL_MODEL')=='1'

@unittest.skipUnless(ENABLED,'explicit local-model acceptance only')
class RealModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence=[]
        cls.temp=tempfile.TemporaryDirectory(prefix='digital-life-real-model-')
        cls.formal=PROJECT/'work/primordial00'
        cls.formal_hashes={str(p.relative_to(cls.formal)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.formal.rglob('*') if p.is_file()}
        with socket.socket() as port: port.bind(('127.0.0.1',0)); cls.port=port.getsockname()[1]
        model=PROJECT/'work/isolated-model/models/Qwen3-0.6B-Q8_0.gguf'
        digest=hashlib.sha256()
        with model.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
        if digest.hexdigest()!='9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031': raise AssertionError('official model digest mismatch')
        cls.service=ModelService(PROJECT/'work/isolated-model/assets.json',Path(cls.temp.name)/'logs',cls.port)
        cls.config=cls.service.start(); cls.process=cls.service.process
    @classmethod
    def tearDownClass(cls):
        cls.service.stop()
        after={str(p.relative_to(cls.formal)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.formal.rglob('*') if p.is_file()}
        evidence={'backend':'llamacpp','model':'Qwen3-0.6B-Q8_0.gguf','model_sha256':'9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031',
            'server_stopped':cls.process.poll() is not None,'formal_instance_unchanged':after==cls.formal_hashes,'observations':cls.evidence}
        output=PROJECT/'outputs/acceptance/local-model-acceptance.json'; output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        cls.temp.cleanup()
        if after!=cls.formal_hashes: raise AssertionError('formal instance changed during isolation test')
    def test_actual_structured_inference_and_fresh_requests(self):
        reasoner=configured_reasoner(self.config)
        request={'model':reasoner.name,'task':'请使用 write_note，把 isolated-ok 写入 notes/proof.txt。只生成候选动作，不执行工具。'}
        first=reasoner.generate(request)
        self.assertEqual(validate(first),first)
        self.assertGreater(reasoner.last_usage['input_tokens'],0)
        self.assertGreater(reasoner.last_usage['output_tokens'],0)
        self.evidence.append({'case':'structured_inference','selected_tool':first['action']['tool'],'usage':reasoner.last_usage})
        self.assertEqual(probe(self.config)['inference_executed'],False)
        with self.assertRaises(ValueError): reasoner.generate(dict(request,history=[]))
    def test_actual_model_to_tool_to_memory_to_metrics(self):
        root=Path(self.temp.name)/'instance'
        store=Store.prepare(root); control=Control(root,store.instance_id)
        try:
            from digital_life.application.runtime.configuration import configure_model
            configuration=configure_model(store,self.config,store.config()['controller'])
            self.assertFalse(configuration['inference_executed'])
            self.assertEqual(len(store.rows('configuration_versions')),2)
            (root/'WAKE_DISABLED').unlink(); control.resume('isolated-test-only')
            engine=Engine(store)
            activity=engine.submit('请用 write_note 创建 notes/local-proof.txt，内容为 isolated-ok。任务只需要写入文件，不需要询问或等待。','real-model-proof')
            thought=engine.think(activity)
            self.assertIn('approval_id',thought,'tiny model did not propose executable action')
            Policy(store).approve(thought['approval_id'],store.config()['controller'])
            outcome=engine.execute(thought['action_id'])  # actual independent tool subprocess
            self.assertEqual(outcome['state'],'succeeded')
            self.assertEqual(store.row('activities',activity)['state'],'completed')
            self.assertGreater(len(list((root/'workspace').rglob('*.txt'))),0)
            result=Metrics(store).collect()
            self.assertGreater(result['measured'],15)
            self.assertGreater(Metrics(store).operational()['model_output_tokens'][0],0)
            self.assertEqual(store.integrity()['foreign_keys'],[])
            self.evidence.append({'case':'real_model_real_tool','activity_state':store.row('activities',activity)['state'],'tool_state':outcome['state'],'metrics':result,'usage':Metrics(store).operational()['model_output_tokens'][0]})
        finally: control.stop('isolation-finish'); control.close(); store.close()
    def test_versioned_runtime_uses_real_model_and_collects_automatically(self):
        root=Path(self.temp.name)/'versioned-instance'
        store=Store.prepare(root,model_config=self.config); control=Control(root,store.instance_id); manager=Deployment(control)
        try:
            (root/'WAKE_DISABLED').unlink(); control.resume('isolated-version-test')
            Policy(store).mode('open',['write_note'],store.config()['controller'])
            activity=Engine(store).submit('使用 write_note 将 isolated-version-ok 写入 notes/version.txt，不需要等待或询问。','versioned-real-model')
            deployment=Releases(control).stage(PROJECT)
            self.assertTrue(manager.launch(deployment,timeout=15)['switched'])
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                row=store.row('activities',activity)
                if row['state']=='completed': break
                if manager.active['process'].poll() is not None: break
                time.sleep(0.1)
            self.assertEqual(store.row('activities',activity)['state'],'completed',
                (manager.active['ready'].parent/'runtime.log').read_text()[-2000:])
            self.assertGreater(len(store.rows('metric_samples')),100)
            self.assertGreater(Metrics(store).operational()['model_output_tokens'][0],0)
            self.evidence.append({'case':'versioned_runtime','activity_state':store.row('activities',activity)['state'],'metric_samples':len(store.rows('metric_samples')),'output_tokens':Metrics(store).operational()['model_output_tokens'][0]})
        finally:
            control.stop('versioned-isolation-finish')
            if manager.active: manager.driver.stop(manager.active['process'])
            control.close(); store.close()
