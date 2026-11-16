"""Explicit Codex ordinary-thought opt-in; no claim of server hard token caps."""
from copy import deepcopy
from digital_life.domain.contracts import ContractError,Forbidden,dumps
from digital_life.infrastructure.llm.codex_cli import CodexReasoner
from digital_life.infrastructure.llm.fresh_learning import FreshActionProvider,FreshCapability

class CodexPostUsageCapability(FreshCapability):
    def verify(self,reasoner,packet):
        if type(reasoner)is not CodexReasoner or reasoner.enabled is not True or reasoner.budget_mode!='post_usage':
            raise Forbidden('explicit Codex post_usage configuration required')
        if packet.get('contract')!='TL-ENGINE-THOUGHT-1' or packet['binding']['provider']!='codex_cli':
            raise Forbidden('Codex post_usage is ordinary thought only')
    def input_tokens(self,reasoner,wire):
        # Reserve the ENTIRE original input allowance. This is a reservation,
        # not a tokenizer measurement; final CLI usage is mandatory.
        return wire['packet']['limits']['max_input_tokens']

class CodexPostUsageProvider(FreshActionProvider):
    def __init__(self,reasoner,binding):
        super().__init__(reasoner,binding,CodexPostUsageCapability(),self._transport)
        self.accounting_hold=False
        self.last_transport_entered=False
    def _request(self,packet):
        limit=packet['limits']['max_output_tokens']
        return {'model':self.reasoner.name,'output_schema_version':packet['output_schema_version'],
                'task':self.instructions+'\n这是聊天系统的独立思考。explanation用于向用户直接回应。不要执行工具；只聊天时使用wait。'
                +'输出务必简短，尽量不超过'+str(limit)+'个输出token；这只是提示，不是服务端硬限制。\n完整输入：\n'+dumps(packet)}
    def _wire(self,packet):
        path,wire=super()._wire(packet)
        wire['model_request']=self._request(packet)
        wire['prompt']=self.reasoner.payload(wire['model_request'])
        wire['accounting_mode']='post_usage'
        return path,wire
    def _transport(self,path,wire,timeout,max_bytes):
        if path!='codex_exec':raise Forbidden('Codex route changed')
        reasoner=self.reasoner
        reasoner.timeout=min(reasoner.timeout,timeout)
        reasoner.managed_process_group=True
        body=reasoner.generate(wire['model_request'])
        return {'model':reasoner.model,'usage':deepcopy(reasoner.last_usage),
                'session_id':reasoner.last_session_id,'body':body}
    def generate_fresh(self,packet,*,execution_timeout_ms=None,execution_max_bytes=None,before_transport=None):
        self.accounting_hold=False
        if not callable(before_transport):raise Forbidden('actual runtime source boundary required')
        try:
            result=super().generate_fresh(packet,execution_timeout_ms=execution_timeout_ms,
                execution_max_bytes=execution_max_bytes,before_transport=before_transport)
            if self.last_usage is None:raise Forbidden('Codex usage unknown; review required')
            for dimension,actual in self.last_usage.items():
                limit=packet['limits'].get('max_'+dimension)
                if limit is not None and actual>limit:
                    raise Forbidden('Codex original '+dimension+' allowance exceeded; result rejected')
            # Include the measured CLI session without using it for continuation.
            return result
        except BaseException:
            usage=self.last_usage
            self.accounting_hold=bool(self.last_transport_entered and
                (usage is None or any(usage.get(k,0)>packet['limits'][limit]
                    for k,limit in (('input_tokens','max_input_tokens'),('output_tokens','max_output_tokens')))))
            raise
