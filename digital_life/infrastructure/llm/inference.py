"""Explicitly configured stateless local models; no service or model autostart."""
from digital_life.infrastructure.llm.ollama import OllamaReasoner
import json
import time
import urllib.request
from digital_life.domain.contracts import validate_action,ContractError

from digital_life.infrastructure.llm.schemas import SCHEMA,validate,schema_for

class LlamaCppReasoner(OllamaReasoner):
    """Local llama.cpp HTTP transport; no hosted API or server-side conversation."""
    def __init__(self,model,**options):
        super().__init__(model,output_schema=SCHEMA,output_validator=validate,**options)
        self.name='llamacpp:'+model; self.last_usage=None
    def generate(self,request):
        self.last_usage=None
        base=self.payload(request)  # shares strict routing and input-size validation
        payload={'model':self.model,'messages':base['messages'],'stream':False,
          'temperature':self.temperature,'max_tokens':self.max_output_tokens,'cache_prompt':False,
          'chat_template_kwargs':{'enable_thinking':False},
          'response_format':{'type':'json_schema','json_schema':{'name':'life_action','strict':True,'schema':schema_for(request)}}}
        start=time.monotonic()
        req=urllib.request.Request(self.base_url+'/v1/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
        with self.opener.open(req,timeout=self.timeout) as response:
            raw=response.read(1024*1024+1)
        if len(raw)>1024*1024: raise ContractError('model response exceeds limit')
        result=json.loads(raw)
        if result.get('model')!=self.model: raise ContractError('model routing changed')
        choice=result['choices'][0]
        if choice.get('finish_reason')!='stop': raise ContractError('incomplete structured model response')
        output=validate(json.loads(choice['message']['content']))
        usage=result.get('usage',{})
        self.last_usage={'latency_ms':(time.monotonic()-start)*1000,'input_tokens':usage.get('prompt_tokens'),'output_tokens':usage.get('completion_tokens')}
        return output

def probe(config):
    """Check local availability without loading a model or performing inference."""
    reasoner=configured_reasoner(config)
    if config['backend'] in ('remote_chat','codex_cli'): return reasoner.probe()
    path='/api/tags' if config['backend']=='ollama' else '/v1/models'
    with reasoner.opener.open(reasoner.base_url+path,timeout=min(10,reasoner.timeout)) as response:
        raw=response.read(1024*1024+1)
    if len(raw)>1024*1024: raise ContractError('model inventory exceeds limit')
    result=json.loads(raw)
    if config['backend']=='ollama': names=[r.get('name') for r in result['models']]
    else: names=[r.get('id') for r in result['data']]
    if reasoner.model not in names: raise ContractError('configured local model is unavailable')
    return {'available':True,'model':reasoner.name,'inference_executed':False}

def configured_reasoner(config):
    if config.get('backend')=='codex_cli':
        from digital_life.infrastructure.llm.codex_cli import CodexReasoner
        return CodexReasoner(config)
    if config.get('backend')=='remote_chat':
        from digital_life.infrastructure.llm.remote_chat import RemoteChatReasoner
        return RemoteChatReasoner(config)
    if config.get('backend') not in ('ollama','llamacpp'): raise ContractError('real local model is not configured; no automatic test/cloud fallback')
    options={k:config[k] for k in ('base_url','timeout','max_output_tokens','temperature','context_window') if k in config}
    if config['backend']=='llamacpp': return LlamaCppReasoner(config['model'],**options)
    return OllamaReasoner(config['model'],output_schema=SCHEMA,output_validator=validate,**options)
