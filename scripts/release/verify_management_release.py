"""One final management release check: backend, browser, distribution, formal guard."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from digital_life import __version__
from verify_isolated import hashes

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip-real-model',action='store_true');args=parser.parse_args()
    output=ROOT/'outputs/acceptance';output.mkdir(parents=True,exist_ok=True)
    before=hashes(ROOT/'work/primordial00')
    if 'WAKE_DISABLED' not in before: raise RuntimeError('formal wake lock missing; no checks started')
    steps=[];error=None
    commands=[('backend',[sys.executable,'scripts/verification/verify_isolated.py']+([] if args.skip_real_model else ['--real-model'])),
      ('browser',['node','scripts/verification/verify_dashboard_browser.mjs']),
      ('wheel',[sys.executable,'-m','pip','wheel','.','--no-deps','--no-build-isolation','--no-cache-dir','--wheel-dir','work/distributions']),
      ('distribution',[sys.executable,'scripts/release/verify_distribution.py','work/distributions/ai_assistant_with_memory-'+__version__+'-py3-none-any.whl'])]
    try:
        for name,command in commands:
            print('Checking '+name+'...',flush=True)
            result=subprocess.run(command,cwd=ROOT,timeout=240)
            steps.append({'name':name,'returncode':result.returncode})
            if result.returncode: raise RuntimeError(name+' did not pass')
    except Exception as exc: error=str(exc)
    after=hashes(ROOT/'work/primordial00')
    reports={}
    for name,path in [('backend','isolated-acceptance.json'),('browser','dashboard-browser-acceptance.json'),('distribution','distribution-acceptance.json')]:
        if (output/path).exists(): reports[name]=json.loads((output/path).read_text())
    successful=error is None and before==after and len(steps)==4 and all(reports.get(name,{}).get('successful') for name in ('backend','browser','distribution'))
    report={'version':__version__,'successful':successful,'error':error,'steps':steps,'real_model_requested':not args.skip_real_model,
      'backend_tests':reports.get('backend',{}).get('tests_run'),'browser_checks':len(reports.get('browser',{}).get('checks',[])),
      'formal_instance_unchanged':before==after,'formal_wake_lock_unchanged':before.get('WAKE_DISABLED')==after.get('WAKE_DISABLED'),
      'panel_started_runtime':reports.get('browser',{}).get('runtime_started'),'remote_api_contacted':reports.get('browser',{}).get('remote_api_contacted')}
    (output/'management-release-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False));return 0 if successful else 1

if __name__=='__main__':raise SystemExit(main())
