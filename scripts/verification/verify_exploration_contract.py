#!/usr/bin/env python3
"""Read-only AE V1 freeze verification. Never imports the runtime or opens an instance."""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
BASELINE=ROOT/'docs/architecture/autonomous-exploration-baseline-v1.json'

def signatures(path,class_name):
    tree=ast.parse(path.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
    return {n.name:ast.unparse(n.args) for n in cls.body if isinstance(n,ast.FunctionDef)}

def verify():
    baseline=json.loads(BASELINE.read_text()); errors=[]
    for relative,checksum in baseline['frozen_files'].items():
        path=ROOT/relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=checksum:
            errors.append('Frozen file differs or missing: '+relative)
    for spec in baseline['interfaces']:
        try: actual=signatures(ROOT/spec['path'],spec['class'])
        except (OSError,SyntaxError,StopIteration) as error:
            errors.append('Cannot inspect interface: '+spec['path']); continue
        if actual!=spec['signatures']: errors.append('Interface differs: '+spec['path'])
    ids=[m['id'] for m in baseline['metrics']]
    if ids!=['M%02d'%n for n in range(1,17)]: errors.append('Metric identifiers incomplete or duplicated')
    for metric in baseline['metrics']:
        required={'id','name','definition','unit','sources','availability','gate','current_status','value'}
        if not required<=set(metric) or metric.get('current_status')!='not_run' or metric.get('value') is not None:
            errors.append('Invalid unmeasured metric: '+metric.get('id','unknown'))
    for relative in baseline['document_links_checked']:
        path=ROOT/relative
        if not path.is_file(): errors.append('Missing document: '+relative); continue
        for target in re.findall(r'\]\(([^)]+)\)',path.read_text()):
            if '://' in target or target.startswith('#'): continue
            if not (path.parent/target.split('#')[0]).exists(): errors.append('Broken link: '+relative+' -> '+target)
    if baseline.get('protocol_ids')!=['AE-RUNTIME-1.0','AE-METRICS-1.0','AE-EVAL-1.0']: errors.append('Protocol identity differs')
    return {'protocol_ids':baseline.get('protocol_ids'),'successful':not errors,'errors':errors,
            'frozen_files_checked':len(baseline['frozen_files']),'interfaces_checked':len(baseline['interfaces']),
            'metric_definitions_checked':len(ids),'scope':'G0 integrity only; no behavioral evaluation',
            'runtime_started':False,'production_files_modified':False,'quality_metrics_measured':False}

if __name__=='__main__':
    result=verify(); print(json.dumps(result,ensure_ascii=False,indent=2)); sys.exit(0 if result['successful'] else 1)
