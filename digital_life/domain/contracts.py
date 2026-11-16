"""Dependency-free validated contracts for the runtime and control plane."""
from dataclasses import dataclass,field
from datetime import datetime,timezone,timedelta
import hashlib
import json
import math
import uuid

class ContractError(ValueError): pass
class Conflict(ContractError): pass
class Forbidden(ContractError): pass
class Stale(ContractError): pass

def identifier(): return uuid.uuid4().hex
def utc(seconds=0): return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat(timespec='milliseconds').replace('+00:00','Z')
def dumps(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(value): return hashlib.sha256(value if isinstance(value,bytes) else value.encode()).hexdigest()
def probability(value):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not 0<=value<=1: raise ContractError('probability outside [0,1]')
    return float(value)
def text(value,limit=16000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit: raise ContractError('invalid text')
    return value

@dataclass(frozen=True)
class Scope:
    root:str
    tools:tuple=('write_note','read_file','list_files')
    def as_json(self): return {'root':self.root,'tools':list(self.tools)}

@dataclass(frozen=True)
class ToolResult:
    transport_state:str
    execution_state:str
    verification_state:str
    evidence:dict=field(default_factory=dict)
    error:str=''

@dataclass(frozen=True)
class RuntimeIdentity:
    epoch:int
    process_id:str

def validate_action(value):
    if not isinstance(value,dict) or set(value)-{'tool','arguments','explanation'}: raise ContractError('invalid action fields')
    tool=value.get('tool'); args=value.get('arguments')
    from digital_life.domain.project_files import NAMES,validate as validate_project
    if tool in NAMES:
        validate_project(tool,args);return value
    if tool not in ('write_note','read_file','list_files','wait','ask'): raise ContractError('unsupported tool')
    if not isinstance(args,dict): raise ContractError('arguments must be object')
    if tool=='write_note':
        if set(args)!={'path','text'}: raise ContractError('write_note requires path,text')
        text(args['path'],240); text(args['text'],16000)
    elif tool=='read_file':
        if set(args)!={'path'}: raise ContractError('read_file requires path')
        text(args['path'],240)
    elif tool=='list_files':
        if set(args)-{'path'}: raise ContractError('unexpected directory argument')
    elif tool in ('wait','ask'):
        if set(args)!={'reason'}: raise ContractError('wait/ask requires reason')
        text(args['reason'])
    return value
