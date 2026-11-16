"""Sequential T01-T04 gates with immutable evidence hashes. No live-instance access."""
import sys,json,io,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from digital_life.domain.contracts import sha
from digital_life.application.monitoring.task_plan import inspect_plan
ROOT=Path(__file__).resolve().parents[2]
GROUPS=[('T01',['tests.test_task_plan.TaskPlanTests'],'冻结源码与部署基线、11项回归题面和任务门控'),('T02',['tests.test_development_steps.TaskLoopTests','tests.test_development_steps.IntegratedLoopTests','tests.test_development_steps.UnresolvedLoopTests'],'显式有限文件目标、多轮独立请求、真实受限工具和等待继续'),('T03',['tests.test_development_steps.CognitionTests','tests.test_development_steps.CognitionRevisionTests','tests.test_development_steps.CognitiveToolSourceTests'],'V3结构化认知候选、证据核验、修订及控制者确认'),('T04',['tests.test_development_steps.LearningPipelineTests','tests.test_development_steps.LearningGateTests'],'控制者记忆反馈、隔离检索对照、审批采用、CAS及补偿回退')]
def main():
 path=ROOT/'docs/plan/task-status.json';plan=json.loads(path.read_text());all_passed=True
 for task_id,classes,scope in GROUPS:
  task=next(t for t in plan['tasks'] if t['id']==task_id);task['status']='complete' if task['status']=='complete' else 'validating';path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n');inspect_plan(ROOT)
  suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in classes);stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
  evidence={'task':task_id,'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'scope':scope,'method':'isolated temporary instances; fixture reasoners; real bounded tools for T02; no cloud calls','details':stream.getvalue(),'live_instance_updated':False}
  output=ROOT/'outputs/acceptance'/('development-'+task_id.lower()+'.json');output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n');task.update(evidence=str(output.relative_to(ROOT)),evidence_sha256=sha(output.read_bytes()),completion_scope=scope)
  if result.wasSuccessful():task['status']='complete'
  else:
   all_passed=False;task['status']='validating'
   for later in plan['tasks']:
    if int(later['id'][1:])>int(task_id[1:]):later['status']='pending'
  path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n');print(task_id,'PASS' if result.wasSuccessful() else 'FAIL',result.testsRun,flush=True)
  if not all_passed:print(stream.getvalue());break
 if all_passed:print('Next:',inspect_plan(ROOT)['next_ready'])
 return 0 if all_passed else 1
if __name__=='__main__':raise SystemExit(main())
