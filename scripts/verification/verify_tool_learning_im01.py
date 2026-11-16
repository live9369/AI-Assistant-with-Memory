"""Offline IM01 gate: synthetic fixtures and plan metadata only; no live reads."""
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

TRACE='docs/architecture/tool-learning-im01-traceability.json'
DESIGN='docs/architecture/tool-learning-im01-design.md'
FILES=['digital_life/application/learning/plan.py','evaluation/tool_learning_fixture.py','tests/test_tool_learning_fixture.py','tests/test_tool_learning_plan.py',DESIGN,'docs/architecture/tool-learning-im01-fixture-design.md','docs/architecture/tool-learning-im01-traceability.md',TRACE,'scripts/verification/verify_tool_learning_im01.py']

def sources():return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}

def trace_check():
 plan=json.loads((ROOT/PLAN).read_text());freeze=json.loads((ROOT/plan['frozen_record']).read_text());trace=json.loads((ROOT/TRACE).read_text());ids={t['id'] for t in plan['tasks']}
 if trace['freeze_record_sha256']!=plan['frozen_record_sha256']:raise ValueError('trace freeze binding mismatch')
 expected={'table_mappings':set(freeze['planned_storage']['new_tables']),'operation_mappings':set(freeze['operations']),'state_mappings':set(freeze['state_axes'])}
 catalog={r['id']:r for r in trace['acceptance_catalog']}
 if len(catalog)!=len(trace['acceptance_catalog']):raise ValueError('duplicate trace acceptance ids')
 for section,names in expected.items():
  rows=trace[section]
  if {r['name'] for r in rows}!=names or len(rows)!=len(names):raise ValueError('trace coverage mismatch')
  for r in rows:
   if not set(r['implementation_tasks'])<=ids:raise ValueError('unknown implementation dependency')
   for ref in r['normative_refs']:
    if ref['term'] not in (ROOT/ref['path']).read_text():raise ValueError('missing normative term')
   for name in r['existing_modules']:
    if not (ROOT/name).is_file():raise ValueError('existing module not found')
   for key in ('positive_acceptance_ids','negative_acceptance_ids'):
    if not r[key] or not set(r[key])<=set(catalog):raise ValueError('missing acceptance obligation')
 if any(r['execution_status']!='not_run' or r['evidence'] is not None for r in catalog.values()):raise ValueError('future trace obligations incorrectly marked verified')
 return {'tables':len(expected['table_mappings']),'operations':len(expected['operation_mappings']),'state_axes':len(expected['state_mappings']),'future_obligations':len(catalog),'future_obligations_executed':False}

class Result(unittest.TextTestResult):
 def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.cases=[]
 def startTest(self,test):self.cases.append(test.id());super().startTest(test)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--complete',action='store_true');args=parser.parse_args();inspect(ROOT)
 plan=json.loads((ROOT/PLAN).read_text());task=next(t for t in plan['tasks'] if t['id']=='IM01')
 if task['status']=='implementing':transition(ROOT,'IM01','validating')
 elif task['status'] not in ('validating','complete'):raise ValueError('IM01 design and implementation must precede gate')
 before=sources();trace=trace_check();suite=unittest.TestSuite()
 for pattern in ('test_tool_learning_fixture.py','test_tool_learning_plan.py','test_architecture.py','test_task_plan.py'):suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=pattern))
 stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,resultclass=Result,verbosity=2).run(suite)
 stable=before==sources();passed=result.wasSuccessful() and stable
 scope='IM01 synthetic schema2/3 locked fixtures, 19/10/9 traceability and explicit IM dependency/evidence gates; no TL business-chain acceptance'
 evidence={'task':'IM01','contract':plan['frozen_contract'],'passed':passed,'completion_scope':scope,'frozen_record_sha256':plan['frozen_record_sha256'],'source_stable_during_verification':stable,'source_files':before,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':[{'test':t.id(),'reason':reason} for t,reason in result.skipped],'cases':result.cases,'trace':trace,'details':stream.getvalue(),'current_instance_opened':False,'model_calls':False,'network_services_started':False,'deployment_performed':False}
 directory=ROOT/'outputs/acceptance/tool-learning';directory.mkdir(parents=True,exist_ok=True)
 path=directory/'im01.json'
 if task['status']=='complete':
  # Keep the original completion proof intact; subsequent runs are separate evidence.
  from digital_life.domain.contracts import identifier
  path=directory/('im01-recheck-'+identifier()+'.json')
 path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
 if passed and args.complete and task['status']!='complete':transition(ROOT,'IM01','complete',evidence=str(path.relative_to(ROOT)))
 print(json.dumps({k:evidence[k] for k in ('passed','tests','failures','errors','source_stable_during_verification','trace')},ensure_ascii=False))
 print('Next:',inspect(ROOT)['ready'])
 if not passed:print(stream.getvalue())
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
