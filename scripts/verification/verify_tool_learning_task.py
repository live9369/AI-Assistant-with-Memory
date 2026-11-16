"""Offline evidence gates for independent SQL and public material work."""
import argparse
import hashlib
import fcntl
import io
import json
import os
import subprocess
from pathlib import Path
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from digital_life.application.learning.plan import PLAN, inspect, transition

TASKS = {
    'IM03': ('test_tool_learning_schema.py', 'isolated SQL structure and constraints only; no migration, business-chain completion or current-instance access'),
    'IM04': ('test_tool_learning_store.py', 'owner-constrained technical persistence, command identity, CAS and artifact integrity on new synthetic databases only; no business approval or deployment'),
    'IM05': ('test_tool_learning_work.py', 'isolated C0 work/activity/budget/command atomicity, shared durable budget and coordination rules; no live dispatch, recovery execution, migration or current-instance access'),
    'IM06': ('test_tool_learning_invalidation.py', 'isolated F1 atomic invalidation, typed dependencies and current eligibility with deterministic callback ordering; no real provider wiring, F2/F3, physical erasure or current-instance access'),
    'IM07': ('test_tool_learning_observation.py', 'isolated bounded observation extraction/comparison/proposal/effect production and persistence; no independent scientific measurement claim, real model spending or current-instance access'),
    'IM17': ('test_tool_learning_materials.py', 'public DEV and mechanism material static integrity only; no executed mechanism trials, formal labels or model evaluation'),
    'IM18': ('test_tool_learning_evaluation*.py', 'isolated evaluation records, deterministic substitutes, accounting and statistical arithmetic; no real-model execution, formal independent labels or full protocol success'),
}

CONTINUATION = {
    'IM08': ('acceptance', 'M03 acceptance decisions and atomic C1; no independent factual truth claim'),
    'IM09': ('representation', 'fixed-version representation leases and atomic C2'),
    'IM10': ('recall', 'purpose-limited retrieval, read-only audit and legacy compatibility'),
    'IM11': ('runtime', 'isolated input/output and provider wiring with fake transports only'),
    'IM12': ('propagation', 'F2/F3 propagation and explicitly synthetic managed erasure only'),
    'IM13': ('recovery', 'same-work recovery and trusted exclusion reconciliation; no live instance'),
    'IM14': ('effect', 'measurement-bound effect recording; no formal improvement claim'),
    'IM15': ('bridge', 'isolated schema4 compatibility and release protection; synthetic fixture launches only, no formal deployment'),
    'IM16': ('migration', 'fresh synthetic 2/3 to 4 migration and compatible rollback only'),
    'IM19': ('mechanisms', 'deterministic mechanism matrix and existing regression; no real model evaluation'),
}
for task, (module, scope) in CONTINUATION.items():
    TASKS[task] = ('test_tool_learning_' + module + '.py', scope)


def sources(task):
    patterns = ['digital_life/domain/tool_learning*.py',
                'tests/' + TASKS[task][0],
                'docs/architecture/tool-learning-' + task.lower() + '*.md',
                'tests/test_tool_learning_plan.py', 'tests/test_architecture.py',
                'tests/test_task_plan.py']
    if task in ('IM03', 'IM04', 'IM05', 'IM06', 'IM07'):
        patterns += ['digital_life/resources/*tool_learning*.sql',
                     'digital_life/resources/runtime.sql',
                     'evaluation/tool_learning_fixture.py',
                     'digital_life/application/lifecycle/schema_migration.py',
                     'digital_life/infrastructure/persistence/sqlite_store.py']
        if task in ('IM04', 'IM05', 'IM06', 'IM07'):
            patterns += ['digital_life/infrastructure/persistence/tool_learning*.py']
        if task in ('IM05', 'IM06', 'IM07'):
            patterns += ['digital_life/application/learning/work.py',
                         'digital_life/application/learning/budget.py',
                         'digital_life/application/runtime/scheduling.py',
                         'digital_life/infrastructure/processes/dispatch_gate.py',
                         'tests/test_tool_learning_budget.py',
                         'tests/test_tool_learning_store.py',
                         'tests/test_tool_learning_schema.py',
                         'tests/test_full_system.py', 'tests/test_fault_integration.py',
                         'tests/test_goal_regulation.py']
        if task == 'IM06':
            patterns += ['digital_life/application/learning/eligibility.py',
                         'digital_life/application/learning/invalidation.py',
                         'tests/test_tool_learning_eligibility.py',
                         'tests/test_tool_learning_work.py', 'tests/test_dispatch_gate.py']
        if task == 'IM07':
            patterns += ['digital_life/application/learning/*.py',
                         'tests/test_tool_learning*.py']
    elif task == 'IM17':
        patterns += ['config/evaluation/tool-learning*.json']
    else:
        patterns += ['config/evaluation/tool-learning*.json',
                     'evaluation/tool_learning_*.py',
                     'digital_life/resources/tool_learning_evaluation_v1.sql']
    files = {p for pattern in patterns for p in ROOT.glob(pattern)}
    if task in CONTINUATION:
        files.update(p for pattern in ('digital_life/**/*.py', 'digital_life/resources/*.sql',
            'digital_life/resources/*.json', 'tests/test_*.py', 'evaluation/tool_learning*.py',
            'scripts/verification/*tool_learning*.py', 'config/evaluation/tool-learning*.json',
            'evaluation/im20/*.py', 'evaluation/im20/*.json', 'evaluation/im20/*.md',
            'evaluation/im11/*.js', 'digital_life/web/*',
            'docs/architecture/tool-learning-' + task.lower() + '*.md') for p in ROOT.glob(pattern))
    if task == 'IM19':
        # Include the inherited evaluation engines/materials and root CLI/build
        # dependencies actually used by full regressions. This walker prunes
        # private configuration and runtime roots before visiting their files.
        from digital_life.application.learning.bridge import source_files
        files.update(ROOT / relative for relative, raw in source_files(ROOT)
                     if str(relative) != PLAN)
        # Plan state is operational metadata updated after successful evidence
        # sealing, not executable code; the frozen normative record is checked
        # independently by inspect() before and after verification.
        files.discard(ROOT / PLAN)
    files.update((Path(__file__), ROOT / 'digital_life/application/learning/plan.py'))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)}


def write_status(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


class ProgressStream(io.StringIO):
    def __init__(self, path):
        super().__init__()
        self.progress = path.open('a', encoding='utf-8', buffering=1)

    def write(self, value):
        self.progress.write(value)
        self.progress.flush()
        return super().write(value)


class Result(unittest.TextTestResult):
    current = None
    status_path = None
    status = None
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []
        Result.current = self

    def startTest(self, test):
        self.cases.append(test.id())
        super().startTest(test)
        if Result.status_path:
            Result.status.update(active_test=test.id(), started_tests=self.testsRun)
            write_status(Result.status_path, Result.status)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', choices=sorted(TASKS), required=True)
    parser.add_argument('--complete', action='store_true')
    args = parser.parse_args()
    run_folder = ROOT / 'outputs/acceptance/tool-learning/runs' / (args.task.lower() + '-' + uuid.uuid4().hex)
    run_folder.mkdir(parents=True, mode=0o700)
    run_lock = (run_folder.parent / '.global-verification.lock').open('a+')
    try:
        fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('another global verification is still running; inspect its run status before starting another') from None
    # Offline verification never enables opt-in real-model tests, including children.
    os.environ['DIGITAL_LIFE_REAL_MODEL'] = '0'
    inspect(ROOT)
    plan = json.loads((ROOT / PLAN).read_text())
    task = next(t for t in plan['tasks'] if t['id'] == args.task)
    if task['status'] == 'implementing':
        transition(ROOT, args.task, 'validating')
    elif task['status'] not in ('validating', 'complete'):
        raise ValueError('implementation must precede verification')
    pattern, scope = TASKS[args.task]
    before = sources(args.task)
    write_status(run_folder / 'before.json', {'task': args.task, 'pid': os.getpid(),
        'command': [sys.executable, *sys.argv], 'source_files': before})
    run_status = {'task': args.task, 'pid': os.getpid(), 'status': 'collecting',
                  'started_tests': 0, 'active_test': None, 'full_result_available': False}
    Result.current = None
    Result.status_path = run_folder / 'status.json'
    Result.status = run_status
    write_status(Result.status_path, run_status)
    suite = unittest.TestSuite()
    counts = {}
    patterns = [pattern, 'test_tool_learning_plan.py', 'test_architecture.py', 'test_task_plan.py']
    if args.task in CONTINUATION:
        patterns = ['test_tool_learning*.py', 'test_architecture.py', 'test_task_plan.py']
        required = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=pattern)
        if not required.countTestCases():
            raise ValueError('required continuation task suite missing')
    if args.task == 'IM05':
        patterns += ['test_tool_learning_budget.py', 'test_tool_learning_store.py', 'test_tool_learning_schema.py',
                     'test_full_system.py', 'test_fault_integration.py', 'test_goal_regulation.py']
    if args.task == 'IM06':
        patterns += ['test_tool_learning_eligibility.py', 'test_tool_learning_work.py',
                     'test_tool_learning_budget.py', 'test_tool_learning_store.py',
                     'test_tool_learning_schema.py', 'test_dispatch_gate.py',
                     'test_fault_integration.py']
    if args.task == 'IM07':
        patterns += ['test_tool_learning_work.py', 'test_tool_learning_budget.py',
                     'test_tool_learning_eligibility.py', 'test_tool_learning_invalidation.py',
                     'test_tool_learning_store.py', 'test_tool_learning_contract.py',
                     'test_tool_learning_products.py', 'test_tool_learning_types.py',
                     'test_dispatch_gate.py']
    excluded_suites = []
    if args.task in ('IM11', 'IM12', 'IM19'):
        # Engine, execution, model, management and all high-dimensional contexts
        # changed together. Include their real offline regression suites.
        excluded_suites = [{'path': 'tests/test_real_model.py',
                            'reason': 'real model/current-instance opt-in forbidden by user'}]
        already = {'test_architecture.py', 'test_task_plan.py', 'test_real_model.py'}
        patterns += [p.name for p in sorted((ROOT / 'tests').glob('test_*.py'))
                     if not p.name.startswith('test_tool_learning') and p.name not in already]
    for name in patterns:
        found = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=name)
        counts[name] = found.countTestCases()
        suite.addTests(found)
    if args.task == 'IM19':
        os.environ['DIGITAL_LIFE_IM19_EVIDENCE_DIR'] = str(run_folder / 'mechanisms')
        prepared = unittest.defaultTestLoader.loadTestsFromName('evaluation.im20.test_preparation')
        counts['evaluation.im20.test_preparation'] = prepared.countTestCases()
        suite.addTests(prepared)
    if args.task not in CONTINUATION and not counts[pattern]:
        raise ValueError('required task suite missing')
    if args.task == 'IM05' and any(not counts[name] for name in (
            'test_tool_learning_budget.py', 'test_tool_learning_store.py', 'test_tool_learning_schema.py')):
        raise ValueError('IM05 budget and storage regression suites required')
    if args.task == 'IM06' and any(not counts[name] for name in (
            'test_tool_learning_eligibility.py', 'test_dispatch_gate.py')):
        raise ValueError('IM06 eligibility and dispatch suites required')
    stream = ProgressStream(run_folder / 'progress.log')
    run_status['status'] = 'running'
    write_status(Result.status_path, run_status)
    try:
        result = unittest.TextTestRunner(stream=stream, resultclass=Result, verbosity=2).run(suite)
    except BaseException as error:
        run_status.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed_to_finish',
                          error_type=type(error).__name__, full_result_available=False,
                          source_stable_at_exit=before == sources(args.task))
        write_status(Result.status_path, run_status)
        raise
    finally:
        stream.progress.flush()
        stream.progress.close()
    web_checks = []
    if args.task in ('IM11', 'IM12', 'IM19'):
        for command in (['node', '--check', 'digital_life/web/app.js'],
                        ['node', 'evaluation/im11/ui_check.js']):
            try:
                checked = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
                web_checks.append({'command': command, 'exit_code': checked.returncode,
                                   'stdout': checked.stdout, 'stderr': checked.stderr})
            except (OSError, subprocess.TimeoutExpired) as error:
                web_checks.append({'command': command, 'exit_code': None, 'error': type(error).__name__})
    inspect(ROOT)
    stable = before == sources(args.task)
    mechanism_coverage = None
    if args.task == 'IM19':
        from evaluation.tool_learning_coverage import collect
        try:
            mechanism_coverage = collect(run_folder / 'mechanisms')
        except Exception as error:
            mechanism_coverage = {'passed': False, 'obligation_denominator': 438, 'covered_obligations': 0,
                'obligation_repeat_denominator': 1314, 'covered_obligation_repeat_cells': 0,
                'decision_denominator': 107, 'covered_decisions': 0, 'unique_execution_records_in_run': None,
                'unique_referenced_execution_records': None, 'independent_scientific_sample_count': None,
                'collection_error': {'type': type(error).__name__, 'message': str(error)}}
            error_path = run_folder / 'coverage-collection-error.json'
            error_path.write_text(json.dumps(mechanism_coverage, ensure_ascii=False, indent=2) + '\n')
    passed = result.wasSuccessful() and stable and not result.skipped and all(c.get('exit_code') == 0 for c in web_checks) and (mechanism_coverage is None or mechanism_coverage['passed'])
    evidence = {
        'task': args.task, 'contract': plan['frozen_contract'], 'passed': passed,
        'run_record': str(run_folder.relative_to(ROOT)),
        'completion_scope': scope, 'frozen_record_sha256': plan['frozen_record_sha256'],
        'source_stable_during_verification': stable, 'source_files': before,
        'tests': result.testsRun, 'suite_counts': counts, 'cases': result.cases,
        'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': [{'test': t.id(), 'reason': r} for t, r in result.skipped],
        'details': stream.getvalue(), 'current_instance_opened': False,
        'models_called': False, 'deployment_performed': args.task in ('IM11', 'IM12', 'IM15', 'IM16', 'IM19'),
        'deployment_scope': 'synthetic_fixture_only' if args.task in ('IM11', 'IM12', 'IM15', 'IM16', 'IM19') else 'none',
        'formal_evaluation_executed': False,
        'real_models_called': False,
        'excluded_suites': excluded_suites,
        'real_model_opt_in_disabled': True,
        'public_build_dependency_scope_included': args.task == 'IM19',
        'operational_metadata_excluded_from_source_snapshot': [PLAN] if args.task == 'IM19' else [],
        'web_checks': web_checks, 'browser_layout_verified': False,
        'mechanism_coverage': None if mechanism_coverage is None else {k:mechanism_coverage[k] for k in ('passed','obligation_denominator','covered_obligations','obligation_repeat_denominator','covered_obligation_repeat_cells','decision_denominator','covered_decisions','unique_execution_records_in_run','unique_referenced_execution_records','independent_scientific_sample_count')},
        'mechanism_coverage_evidence': str((run_folder / 'coverage.json').relative_to(ROOT)) if mechanism_coverage is not None else None,
        'formal_deployment_performed': False,
        'isolated_fixture_deployment_checks_included': args.task in ('IM11', 'IM12', 'IM15', 'IM16', 'IM19'),
        'synthetic_fixture_control_temporarily_enabled': args.task in ('IM05', 'IM06', 'IM07') or args.task in CONTINUATION,
    }
    folder = ROOT / 'outputs/acceptance/tool-learning'
    folder.mkdir(parents=True, exist_ok=True)
    name = args.task.lower()
    if task['status'] == 'complete' or (folder / (name + '.json')).exists():
        name += '-recheck-' + uuid.uuid4().hex
    path = folder / (name + '.json')
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    if passed and args.complete and task['status'] != 'complete':
        transition(ROOT, args.task, 'complete', evidence=str(path.relative_to(ROOT)))
    run_status.update(status='verification_completed', passed=passed, active_test=None, full_result_available=True,
                      tests=result.testsRun, source_stable_during_verification=stable, evidence=str(path.relative_to(ROOT)))
    write_status(Result.status_path, run_status)
    print(json.dumps({k: evidence[k] for k in ('task', 'passed', 'tests', 'failures', 'errors', 'source_stable_during_verification', 'suite_counts')}))
    if not passed:
        print(stream.getvalue())
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
