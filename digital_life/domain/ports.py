"""Provider-independent interfaces used by application orchestration."""
from typing import Protocol,Any
from digital_life.domain.contracts import ToolResult,Forbidden

class Reasoner(Protocol):
    name:str
    def generate(self,request:dict)->dict: ...

class ToolRunner(Protocol):
    def __call__(self,action:dict,root:Any,operation:str)->ToolResult: ...


class ObservationThoughtPort:
    """One complete clean invocation per call; never an action-schema provider."""
    def configured_binding(self):
        raise Forbidden('fresh learning route identity is not configured')
    def preflight(self,packet):
        raise Forbidden('fresh provider input token count/output cap enforcement is not configured')
    def generate_fresh(self,packet):
        raise Forbidden('fresh structured learning provider is not configured')
