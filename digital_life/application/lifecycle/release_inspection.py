"""Read-only comparison of retained deployment and current source tree."""
import hashlib
import json
from pathlib import Path
import sqlite3

def release_status(root,project):
 root=Path(root).resolve();project=Path(project).resolve();db=root/'control.sqlite'
 if not db.is_file():return {'state':'not_prepared'}
 c=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
 try:
  state=c.execute('SELECT user_stopped,active_process_run_id,runtime_epoch FROM instance_control_state').fetchone()
  active=c.execute("SELECT * FROM deployments WHERE state='active' ORDER BY rowid DESC LIMIT 1").fetchone()
  result={'user_stopped':bool(state['user_stopped']),'process_run_id':state['active_process_run_id'],'runtime_epoch':state['runtime_epoch'],'deployment_id':active['id'] if active else None}
  if not active:return dict(result,source_matches_deployment=None,reason='尚无部署版本')
  path=root/'releases'/active['release'];manifest=json.loads((path/'manifest.json').read_text());old={k:v for k,v in manifest.items() if k.startswith('digital_life/')}
  current={}
  for p in (project/'digital_life').rglob('*'):
   if '__pycache__' in p.parts or not p.is_file() or p.suffix not in ('.py','.sql','.json','.toml','.html','.css','.js'):continue
   current[str(p.relative_to(project))]=hashlib.sha256(p.read_bytes()).hexdigest()
  changed=sorted(k for k in set(old)|set(current) if old.get(k)!=current.get(k))
  return dict(result,release_hash=active['release'],source_matches_deployment=not changed,changed_file_count=len(changed),changed_files=changed)
 finally:c.close()
