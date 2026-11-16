"""IM02 pure contract gate; no data store, model or life process startup."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from digital_life.application.learning.plan import inspect,transition,PLAN

def sources():
 files=[p for p in (ROOT/'digital_life/domain').glob('tool_learning*.py')]
 files += [p for p in (ROOT/'tests').glob('test_tool_learning*.py')]
 files += [p for p in (ROOT/'docs/architecture').glob('tool-learning-im02*-design.md')]
 files += [ROOT/'digital_life/application/learning/plan.py',Path(__file__)]
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}

class Result(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.cases=[]
 def startTest(self,test):self.cases.append(test.id());super().startTest(test)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--complete',action='store_true');args=parser.parse_args();inspect(ROOT)
 plan=json.loads((ROOT/PLAN).read_text());task=next(t for t in plan['tasks'] if t['id']=='IM02')
 if task['status']=='implementing':transition(ROOT,'IM02','validating')
 elif task['status'] not in ('validating','complete'):raise ValueError('IM02 implementation must precede validation')
 before=sources();suite=unittest.TestSuite();counts={}
 for pattern in ('test_tool_learning_types.py','test_tool_learning_products.py','test_tool_learning_operations.py','test_tool_learning_contract.py','test_tool_learning_plan.py','test_architecture.py','test_task_plan.py'):
  found=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=pattern);counts[pattern]=found.countTestCases();suite.addTests(found)
 if any(counts[p]==0 for p in ('test_tool_learning_types.py','test_tool_learning_products.py','test_tool_learning_operations.py','test_tool_learning_contract.py')):raise ValueError('required validator suites missing')
 from digital_life.domain.tool_learning_products import OPERATIONS
 freeze=json.loads((ROOT/plan['frozen_record']).read_text())
 if set(OPERATIONS)!=set(freeze['operations']):raise ValueError('operation registry differs from frozen design')
 stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,resultclass=Result,verbosity=2).run(suite)
 stable=before==sources();passed=result.wasSuccessful() and stable and not result.skipped
 evidence={'task':'IM02','contract':plan['frozen_contract'],'passed':passed,'completion_scope':'pure TL structural/JSON/locator/product/operation validation; no authority, fact, storage, policy or TL business-chain proof','frozen_record_sha256':plan['frozen_record_sha256'],'source_stable_during_verification':stable,'source_files':before,'tests':result.testsRun,'suite_counts':counts,'cases':result.cases,'failures':len(result.failures),'errors':len(result.errors),'skipped':[{'test':t.id(),'reason':r} for t,r in result.skipped],'details':stream.getvalue(),'frozen_operations_covered':list(OPERATIONS),'current_instance_opened':False,'models_called':False,'business_database_opened':False,'deployment_performed':False}
 folder=ROOT/'outputs/acceptance/tool-learning';folder.mkdir(parents=True,exist_ok=True);path=folder/'im02.json'
 if task['status']=='complete':
  from digital_life.domain.contracts import identifier
  path=folder/('im02-recheck-'+identifier()+'.json')
 path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
 if passed and args.complete and task['status']!='complete':transition(ROOT,'IM02','complete',evidence=str(path.relative_to(ROOT)))
 print(json.dumps({k:evidence[k] for k in ('passed','tests','failures','errors','source_stable_during_verification','suite_counts')}))
 print('Next:',inspect(ROOT)['ready'])
 if not passed:print(stream.getvalue())
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
