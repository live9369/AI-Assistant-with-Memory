"""Unified acceptance with formal-instance content guard and machine-readable results."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

def hashes(folder):
    return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}

class Result(unittest.TextTestResult):
    def startTest(self,test):
        super().startTest(test); self.started=time.monotonic()
    def note(self,test,state,detail=None):
        self.records.append({'test':test.id(),'state':state,'seconds':round(time.monotonic()-getattr(self,'started',time.monotonic()),4),'detail':detail})
    def addSuccess(self,test): super().addSuccess(test); self.note(test,'passed')
    def addError(self,test,error): super().addError(test,error); self.note(test,'error',self._exc_info_to_string(error,test))
    def addFailure(self,test,error): super().addFailure(test,error); self.note(test,'failed',self._exc_info_to_string(error,test))
    def addSkip(self,test,reason): super().addSkip(test,reason); self.note(test,'skipped',reason)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--real-model',action='store_true'); parser.add_argument('--output',default=str(ROOT/'outputs/acceptance/isolated-acceptance.json'))
    args=parser.parse_args()
    formal=ROOT/'work/primordial00'; before=hashes(formal)
    if 'WAKE_DISABLED' not in before: raise RuntimeError('formal instance wake lock missing; no tests executed')
    if args.real_model: os.environ['DIGITAL_LIFE_REAL_MODEL']='1'
    else: os.environ.pop('DIGITAL_LIFE_REAL_MODEL',None)
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    Result.records=[]
    result=unittest.TextTestRunner(resultclass=Result,verbosity=1).run(suite)
    after=hashes(formal); unchanged=before==after
    from digital_life.application.telemetry.metrics import catalog
    from digital_life import __version__
    report={'engineering_version':__version__,'python':platform.python_version(),'platform':platform.platform(),
      'real_model_requested':args.real_model,'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
      'successful':result.wasSuccessful() and unchanged,'formal_instance_unchanged':unchanged,'formal_wake_lock_unchanged':before.get('WAKE_DISABLED')==after.get('WAKE_DISABLED'),
      'formal_file_hashes':before,'metric_catalog_entries':len(catalog()),'tests':Result.records}
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Saved acceptance:',output)
    return 0 if report['successful'] else 1

if __name__=='__main__': raise SystemExit(main())
