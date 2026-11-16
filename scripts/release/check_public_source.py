#!/usr/bin/env python3
"""Read-only inventory and best-effort publication checks; never uploads files."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_FILES = {'.gitignore', 'README.md', 'README.zh-CN.md', 'LICENSE', 'CONTRIBUTING.md',
                'SECURITY.md', 'pyproject.toml', 'setup.py', 'manage.py', 'start-chat.command', 'codegraph.json'}
PUBLIC_DIRS = {'.github', 'digital_life', 'primordial00', 'database', 'docs', 'tests', 'evaluation', 'scripts'}
PRIVATE_PARTS = {'work', 'outputs', '.git', '.codegraph', '__pycache__', '.venv', 'build', 'dist',
                 '.pytest_cache', '.mypy_cache', '.ruff_cache'}
PRIVATE_NAMES = {'controller.token', 'auth.json', 'credentials.json', 'tokens.json', 'token.json', '.DS_Store'}
PATTERNS = {
    'github-token-literal': re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b'),
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'api-key-literal': re.compile(r'\bsk-[A-Za-z0-9_-]{40,}\b'),
    'embedded-home-path': re.compile(r'/Users/(?!you(?:/|\b)|example(?:/|\b)|test(?:/|\b))[^/\s\x27\x22]+/(?:Documents|Desktop)/'),
}

def private(path):
    return (any(part in PRIVATE_PARTS or part.endswith('.egg-info') for part in path.parts)
            or path.parts[:2] == ('config', 'local') or path.name in PRIVATE_NAMES
            or path.name in {'.env', '.env.local'} or path.name.startswith('.env.') and path.name != '.env.example'
            or any(path.name.endswith(suffix) for suffix in ('.sqlite', '.sqlite-wal', '.sqlite-shm', '.db', '.pem', '.key')))

def candidates(root):
    for name in sorted(PUBLIC_FILES):
        if (root / name).is_file(): yield root / name
    for folder in sorted(PUBLIC_DIRS | {'config/examples', 'config/evaluation'}):
        base = root / folder
        if not base.exists(): continue
        pending = [base]
        while pending:
            current = pending.pop()
            if current.is_symlink():
                yield current
            elif current.is_dir():
                pending.extend(p for p in current.iterdir() if not private(p.relative_to(root)))
            elif current.is_file(): yield current
    if (root / 'config/README.md').is_file(): yield root / 'config/README.md'

def inspect(root):
    findings = []; manifest = []
    for path in sorted(set(candidates(root))):
        relative = path.relative_to(root)
        if path.is_symlink():
            findings.append({'path':str(relative), 'category':'symlink-requires-review'});continue
        if private(relative):
            findings.append({'path':str(relative), 'category':'private-candidate'});continue
        raw = path.read_bytes()
        manifest.append({'path':str(relative), 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()})
        try: text = raw.decode('utf-8')
        except UnicodeError: continue
        for category, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append({'path':str(relative), 'line':text.count('\n',0,match.start())+1, 'category':category})
    staged_checked = False
    if (root / '.git').exists():
        result = subprocess.run(['git','-C',str(root),'ls-files','--cached','-z'],capture_output=True,check=True)
        staged_checked = True
        for name in result.stdout.decode().split('\0'):
            if name and private(Path(name)):
                findings.append({'path':name, 'category':'private-file-in-git-index'})
    return {'scope':'public candidate inventory; not a complete secret scanner or Git-history audit',
            'staged_index_checked':staged_checked, 'candidate_count':len(manifest),
            'findings':findings, 'files':manifest}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, help='Save inventory to a new JSON file; use outputs/ locally.')
    args = parser.parse_args(); report = inspect(ROOT)
    if args.manifest:
        # Refuse overwrite or a path that could itself enter the public candidate set.
        destination=args.manifest.absolute()
        if destination.parent.resolve() != (ROOT/'outputs').resolve() and (ROOT/'outputs').resolve() not in destination.parent.resolve().parents:
            parser.error('manifest must be under the private outputs/ directory')
        destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    summary={key:report[key] for key in ('scope','staged_index_checked','candidate_count','findings')}
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 1 if report['findings'] else 0

if __name__ == '__main__': sys.exit(main())
