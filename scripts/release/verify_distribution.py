"""Install-free wheel smoke test in a fresh directory, outside the source tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from digital_life import __version__
CODE='''import json,sys,pathlib
import digital_life
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.telemetry.metrics import Metrics
from digital_life.entrypoints.http import Application
from digital_life.infrastructure.persistence.sqlite_store import PACKAGE_ROOT
from primordial00.core import Life
root=pathlib.Path(sys.argv[1])
assert pathlib.Path(digital_life.__file__).is_relative_to(root/'package')
store=Store.prepare(root/'instance'); control=Control(store.root,store.instance_id)
try:
    assert (store.root/'WAKE_DISABLED').exists()
    assert control.state()['user_stopped']==1
    result=Metrics(store).collect()
    assert result['definitions']>=188
    assert Application(store.root).dispatch('GET','/v1/status')[0]==200
    assert Application(store.root).dispatch('GET','/v1/overview')[0]==200
    assert len(Application(store.root).dispatch('GET','/v1/model/templates')[1]['items'])==4
    assert all((PACKAGE_ROOT/'web'/name).is_file() for name in ('index.html','app.js','styles.css'))
    assert store.integrity()['foreign_keys']==[]
    legacy=Life.initialize(root/'legacy'); legacy.close()
    print(json.dumps({'version':digital_life.__version__,'metrics':result['definitions'],'wake_disabled':True,'source_tree_required':False}))
finally: control.close(); store.close()
'''

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('wheel'); args=parser.parse_args()
    wheel=Path(args.wheel).resolve()
    with tempfile.TemporaryDirectory(prefix='digital-life-wheel-') as directory:
        root=Path(directory); target=root/'package'
        with zipfile.ZipFile(wheel) as archive:
            files=archive.namelist()
            assert all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in files)
            archive.extractall(target)
            metadata=archive.read(next(n for n in files if n.endswith('.dist-info/METADATA'))).decode()
            assert 'Name: ai-assistant-with-memory' in metadata and ('Version: '+__version__) in metadata
        env=dict(os.environ,PYTHONPATH=str(target),PYTHONDONTWRITEBYTECODE='1')
        result=subprocess.run([sys.executable,'-c',CODE,str(root)],cwd=root,env=env,capture_output=True,text=True,timeout=20)
        if result.returncode: raise RuntimeError(result.stderr)
        report=dict(json.loads(result.stdout),wheel=str(wheel),wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),successful=True)
    output=ROOT/'outputs/acceptance/distribution-acceptance.json'; output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__': main()
