"""T11 acceptance gate: temporary instances only; optional read-only live guard."""
import argparse
import hashlib
import io
import json
import sqlite3
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from digital_life.application.monitoring.task_plan import inspect_plan


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def sources():
    files = [p for folder in ('digital_life', 'tests') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py', '.sql', '.json', '.js', '.html', '.css')]
    files += [ROOT/'docs/architecture/development-t11-design.md', ROOT/'config/examples/autonomy-promise.json', ROOT/'config/examples/autonomy-question.json', ROOT/'config/examples/behavior-policy.json', ROOT/'config/examples/habit-learning.json', ROOT/'config/examples/relationship-condition.json', ROOT/'scripts/verification/verify_thought_inspection_ui.mjs', Path(__file__)]
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(files)}


def live_state():
    path = ROOT/'work/primordial00-first-wake/control.sqlite'
    c = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True); c.row_factory = sqlite3.Row
    try:
        return {'state': dict(c.execute('SELECT instance_ref,runtime_epoch,active_process_run_id,user_stopped FROM instance_control_state').fetchone()), 'deployment': dict(c.execute("SELECT id,release FROM deployments WHERE state='active' ORDER BY rowid DESC LIMIT 1").fetchone())}
    finally: c.close()


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.cases = []; self.benchmarks = []
    def addSuccess(self, test):
        if getattr(test,'benchmark_report',None): self.benchmarks.append({'test':test.id(),'report':test.benchmark_report})
        super().addSuccess(test)
    def startTest(self, test):
        self.cases.append(test.id()); super().startTest(test)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--live-guard', type=Path); args = parser.parse_args()
    plan_path = ROOT/'docs/plan/task-status.json'; plan = json.loads(plan_path.read_text()); task = next(t for t in plan['tasks'] if t['id']=='T11')
    inspect_plan(ROOT); before = sources()
    task['status'] = 'validating'; plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    stream = io.StringIO(); result = unittest.TextTestRunner(stream=stream, resultclass=Result, verbosity=2).run(suite)
    guard = None
    if args.live_guard:
        expected = json.loads(args.live_guard.read_text()); actual = live_state()
        guard = dict(actual, passed=expected==actual, live_updated=False, scope='read-only identity, runtime and deployment comparison; normal live history may grow')
        (ROOT/'outputs/acceptance/t11-live-guard.json').write_text(json.dumps(guard, indent=2)+'\n')
    stable = before == sources(); passed = result.wasSuccessful() and stable and (guard is None or guard['passed'])
    scope = '有限文件承诺提前执行与独立履约核验、声明兴趣排序、真实事实覆盖收益及既有休眠交接；V1工程策略'
    evidence = {'task': 'T11', 'passed': passed, 'completion_scope': scope, 'tests': result.testsRun,
        't11_tests': sum('test_autonomy_agenda.' in name for name in result.cases), 'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': [{'test': test.id(), 'reason': reason} for test, reason in result.skipped], 'source_stable_during_verification': stable,
        'source_files': before, 'method': 'temporary isolated instances; fixture reasoners; HTTP on ephemeral loopback ports; no formal wake or live model invocation',
        'benchmarks':result.benchmarks, 'live_guard': guard, 'details': stream.getvalue(), 'deployment_performed': False}
    output = ROOT/'outputs/acceptance/development-t11.json'; output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
    task.update(status='complete' if passed else 'validating', evidence=str(output.relative_to(ROOT)), evidence_sha256=digest(output), completion_scope=scope)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: evidence[k] for k in ('passed','tests','t11_tests','failures','errors','skipped','source_stable_during_verification')}, ensure_ascii=False), flush=True)
    if passed: print('Next:', inspect_plan(ROOT)['next_ready'])
    else: print(stream.getvalue())
    return 0 if passed else 1


if __name__ == '__main__': raise SystemExit(main())
