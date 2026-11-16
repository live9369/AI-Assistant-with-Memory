"""This batch's offline checks; does not replace IM19 or start any life instance."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from digital_life.application.learning.plan import inspect


def snapshot():
    files = {p for pattern in (
        'digital_life/domain/tool_learning*.py',
        'digital_life/application/learning/*.py',
        'digital_life/application/runtime/scheduling.py',
        'digital_life/infrastructure/persistence/*store.py',
        'digital_life/resources/*tool_learning*.sql',
        'digital_life/resources/runtime.sql',
        'evaluation/tool_learning*.py', 'tests/test_tool_learning*.py',
        'tests/test_architecture.py', 'tests/test_task_plan.py',
        'scripts/verification/*tool_learning*.py', 'config/evaluation/tool-learning*.json',
        'docs/architecture/tool-learning-im*design.md',
    ) for p in ROOT.glob(pattern)}
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    def startTest(self, test):
        self.cases.append(test.id())
        super().startTest(test)


def main():
    inspect(ROOT)
    before = snapshot()
    suite = unittest.TestSuite()
    counts = {}
    for pattern in ('test_tool_learning*.py', 'test_architecture.py', 'test_task_plan.py'):
        found = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=pattern)
        counts[pattern] = found.countTestCases()
        suite.addTests(found)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, resultclass=Result, verbosity=2).run(suite)
    inspect(ROOT)
    stable = before == snapshot()
    passed = result.wasSuccessful() and not result.skipped and stable and len(result.cases) == len(set(result.cases))
    report = dict(passed=passed, tests=result.testsRun, failures=len(result.failures),
                  errors=len(result.errors), skipped=len(result.skipped), suite_counts=counts,
                  cases=result.cases, source_stable_during_verification=stable,
                  source_files=before, details=stream.getvalue(),
                  scope='implemented tool-learning batch checks only; not IM19 complete mechanism/G1 or full-system acceptance',
                  models_called=False, current_instance_opened=False,
                  deployment_performed=False, formal_evaluation_executed=False)
    folder = ROOT / 'outputs/acceptance/tool-learning'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ('batch-' + uuid.uuid4().hex + '.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('passed', 'tests', 'failures', 'errors', 'skipped', 'source_stable_during_verification', 'suite_counts')}))
    print(path.relative_to(ROOT))
    if not passed:
        print(stream.getvalue())
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
