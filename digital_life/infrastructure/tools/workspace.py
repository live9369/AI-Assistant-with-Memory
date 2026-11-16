"""Explicit workspace tool adapter."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from digital_life.domain.contracts import utc,identifier,dumps,sha,validate_action,Forbidden,Conflict,ContractError,ToolResult
class ToolRegistry:
    def __init__(self): self.entries={}
    def register(self,name,handler,description,queryable=True,idempotent=False):
        if name in self.entries: raise Conflict('duplicate tool registration')
        self.entries[name]={'handler':handler,'description':description,'queryable':queryable,'idempotent':idempotent}
    def describe(self): return [{k:v for k,v in entry.items() if k!='handler'}|{'name':name} for name,entry in self.entries.items()]
    def invoke(self,action,root,operation):
        validate_action(action)
        if action['tool'] not in self.entries: raise Forbidden('tool not registered')
        return self.entries[action['tool']]['handler'](Path(root),action['arguments'],operation)



def safe_path(root,relative):
    if not isinstance(relative,str) or not relative or Path(relative).is_absolute(): raise Forbidden('relative workspace path required')
    parts=Path(relative).parts
    if '..' in parts or any(p.startswith('.') for p in parts): raise Forbidden('hidden or parent paths denied')
    path=root.joinpath(*parts)
    current=root
    if root.is_symlink() or not root.is_dir(): raise Forbidden('workspace unavailable')
    for part in parts:
        current=current/part
        if current.is_symlink(): raise Forbidden('symlink path denied')
    if not path.resolve().is_relative_to(root.resolve()): raise Forbidden('outside workspace')
    return path



def write_note(root,args,operation):
    path=safe_path(root,args['path']); path.parent.mkdir(parents=True,exist_ok=True)
    raw=args['text'].encode()
    try:
        with path.open('xb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    except FileExistsError:
        if path.is_symlink() or path.read_bytes()!=raw: return ToolResult('received','unknown','fail',{},'existing content differs')
    matched=path.read_bytes()==raw
    return ToolResult('received','succeeded' if matched else 'unknown','pass' if matched else 'fail',{'path':args['path'],'sha256':sha(raw),'operation':operation})



def resource_signature(path):
    stat=path.stat()
    return [stat.st_dev,stat.st_ino,stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size]


def read_file(root,args,operation):
    path=safe_path(root,args['path'])
    if not path.is_file() or path.stat().st_size>65536: raise ContractError('file unavailable or exceeds 64KB')
    before=resource_signature(path);raw=path.read_bytes();after=resource_signature(path)
    return ToolResult('received','succeeded','pass',{'path':args['path'],'text':raw.decode('utf-8'),'sha256':sha(raw),'resource_signature':after if before==after else None})



def list_files(root,args,operation):
    path=safe_path(root,args.get('path') or 'notes')
    if not path.is_dir(): raise ContractError('directory unavailable')
    before=resource_signature(path)
    items=[p.name for p in path.iterdir() if not p.is_symlink() and not p.name.startswith('.')][:100]
    return ToolResult('received','succeeded','pass',{'path':str(path.relative_to(root)),'entries':sorted(items),'resource_signature':before if before==resource_signature(path) else None})



def registry(project=False):
    result=ToolRegistry()
    result.register('write_note',write_note,'Create or reconcile an exact workspace note',idempotent=True)
    result.register('read_file',read_file,'Read bounded UTF-8 workspace file',idempotent=True)
    result.register('list_files',list_files,'List bounded workspace directory',idempotent=True)
    if project:
        from digital_life.domain.project_files import NAMES
        def denied(*args):raise Forbidden('project tools require explicit project scope')
        descriptions={'project_version_status':'Inspect head and selected file changes; paths list required', 'project_version_log':'List latest saved versions; limit 1..20', 'project_version_save':'Save selected paths as a new Git version; message and expected_head from status required (empty head initially)', 'project_version_diff':'Compare a saved version with one current path', 'project_version_restore':'Restore one path from a saved version; current expected_sha256, expected_head and message required; appends history, never deploys', 'project_check':'Run named python_syntax check on one .py file without executing code (path,check)', 'project_edit':'Replace exactly one old_text with new_text; expected_sha256 from project_read required', 'project_mkdir':'Create an authorized project subdirectory', 'project_list':'List authorized project directory (path: . for root)', 'project_read':'Read project UTF-8 file by start_line,max_lines; returns full-file sha256', 'project_search':'Search literal query under a project path', 'project_write':'Create or replace UTF-8 file using expected_sha256 from project_read; empty hash only creates a new file; parent directory must exist'}
        for name in NAMES:result.register(name,denied,descriptions[name],idempotent=name=='project_write')
    return result


