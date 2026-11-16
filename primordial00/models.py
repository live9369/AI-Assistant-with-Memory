from digital_life.infrastructure.llm.ollama import OllamaReasoner,OUTPUT_SCHEMA,validate_output
"""Stateless local inference transport. Import/configuration never loads a model."""
import json
import math
import time
from pathlib import Path
import shutil
import urllib.error
import urllib.parse
import urllib.request



def config(root):
    path=Path(root)/'model.json'
    if not path.exists(): return {'backend':'test','model':'test-reasoner-v1'}
    value=json.loads(path.read_text())
    if not isinstance(value,dict): raise ValueError('模型配置必须是对象')
    if value.get('backend') not in ('test','ollama'): raise ValueError('尚不支持该模型后端')
    if not isinstance(value.get('model'),str) or not value['model'].strip(): raise ValueError('缺少模型名称')
    if value['backend']=='test' and value['model']!='test-reasoner-v1': raise ValueError('测试模型名称不符')
    return value


def resolve(root):
    value=config(root)
    if value['backend']=='test':
        from .core import TestReasoner
        return TestReasoner()
    options={k:value[k] for k in ('base_url','timeout','max_output_tokens','temperature','context_window') if k in value}
    return OllamaReasoner(value['model'],**options)

def inspect(root):
    """Read-only readiness inspection: no HTTP, inference, pull, or server startup."""
    value=config(root); reasoner=resolve(root)
    return {'configuration':value,'reasoner':reasoner.name,'ollama_executable':shutil.which('ollama'),
            'inference_executed':False,'service_started':False,'download_executed':False,
            'status':'test_only' if value['backend']=='test' else 'configured_not_connected'}
