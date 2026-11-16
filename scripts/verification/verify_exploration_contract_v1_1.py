#!/usr/bin/env python3
"""Read-only V1.1 integrity check; original V1 checker and baseline are preserved."""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[2]
BASELINE=ROOT/'docs/architecture/autonomous-exploration-baseline-v1.1.json'

def verify():
    baseline=json.loads(BASELINE.read_text()); errors=[]
    for relative,checksum in baseline['frozen_files'].items():
        p=ROOT/relative
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=checksum: errors.append('Frozen file differs or missing: '+relative)
    for spec in baseline['interfaces']:
        tree=ast.parse((ROOT/spec['path']).read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==spec['class'])
        actual={n.name:ast.unparse(n.args) for n in cls.body if isinstance(n,ast.FunctionDef)}
        if actual!=spec['signatures']: errors.append('Interface differs: '+spec['path'])
    if baseline['protocol_ids']!=['AE-RUNTIME-1.1','AE-METRICS-1.0','AE-EVAL-1.0']: errors.append('Protocol identity differs')
    if [m['id'] for m in baseline['metrics']]!=['M%02d'%i for i in range(1,17)]: errors.append('Metric dictionary differs')
    for relative in baseline['document_links_checked']:
        p=ROOT/relative
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
            if '://' not in target and not target.startswith('#') and not (p.parent/target.split('#')[0]).exists(): errors.append('Broken link: '+relative+' -> '+target)
    return {'protocol_ids':baseline['protocol_ids'],'successful':not errors,'errors':errors,'frozen_files_checked':len(baseline['frozen_files']),
            'interfaces_checked':len(baseline['interfaces']),'metric_definitions_checked':16,'scope':'G0 V1.1 integrity only','runtime_started':False,'quality_metrics_measured':False}
if __name__=='__main__':
    result=verify();print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result['successful'] else 1)
