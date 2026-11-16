"""IM19 bounded local deterministic fixture supervision; never opens an instance.

The child is a fresh interpreter and all descendants must stay in its process
 group. This is a fixture boundary, not containment of hostile same-UID code.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ('success', 'exception', 'crash', 'hang', 'tree_hang', 'tree_success', 'missing_result')


def _exclusive(path, value):
    with open(path, 'x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def _event(root, kind, **fields):
    with open(root / 'events.jsonl', 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(kind=kind, pid=os.getpid(), monotonic=time.monotonic(), **fields)) + '\n')
        stream.flush(); os.fsync(stream.fileno())


def worker(root, scenario, token):
    # Parent grants only a newly created one-shot fixture root via random token.
    root = Path(root)
    marker = json.loads((root / 'scope.json').read_text())
    if marker != {'scope': 'IM19 synthetic supervised fixture', 'token': token}:
        raise ValueError('not an authorized synthetic scope')
    if scenario not in SCENARIOS:
        raise ValueError('unknown deterministic scenario')
    _event(root, 'entry', scenario=scenario)
    if scenario.startswith('tree_'):
        child = subprocess.Popen([sys.executable, '-c',
            "import time;from pathlib import Path;time.sleep(.8);Path(%r).write_text('escaped deadline')" % str(root / 'late')],
            start_new_session=False)
        _event(root, 'descendant_started', child_pid=child.pid)
    _event(root, 'ready')
    if scenario == 'exception':
        raise RuntimeError('deterministic infrastructure failure')
    if scenario == 'crash':
        os._exit(73)
    if scenario in ('hang', 'tree_hang'):
        while True:
            time.sleep(.1)
    if scenario != 'missing_result':
        _exclusive(root / 'result.json', {'endpoint': 'completed', 'scenario': scenario,
            'provider': 'deterministic', 'real_model_called': False})
    _event(root, 'returned')


def supervise(scenario, evidence_dir, *, timeout=2.0):
    """One attempt, owned process group cleanup, immutable failure evidence."""
    if scenario not in SCENARIOS or type(timeout) not in (float, int) or not 0 < timeout <= 30:
        raise ValueError('bounded allowlisted deterministic fixture required')
    evidence_dir = Path(evidence_dir)
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise ValueError('existing evidence directory required')
    attempt = uuid.uuid4().hex
    destination = evidence_dir / ('im19-supervised-' + attempt + '.json')
    with tempfile.TemporaryDirectory(prefix='im19-supervised-') as folder:
        root = Path(folder); token = uuid.uuid4().hex
        _exclusive(root / 'scope.json', {'scope': 'IM19 synthetic supervised fixture', 'token': token})
        env = dict(os.environ, DIGITAL_LIFE_REAL_MODEL='0', PYTHONDONTWRITEBYTECODE='1')
        started = time.monotonic()
        with open(root / 'stdout.txt', 'w') as stdout_file, open(root / 'stderr.txt', 'w') as stderr_file:
            child = subprocess.Popen([sys.executable, '-m', 'evaluation.tool_learning_mechanisms',
                '--worker', scenario, '--root', str(root), '--token', token],
                cwd=ROOT, env=env, stdout=stdout_file, stderr=stderr_file, text=True,
                start_new_session=True)
            timed_out = False
            try:
                # Parent exit is independent of inherited descendant pipes.
                child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=2)
        stdout = (root / 'stdout.txt').read_text()
        stderr = (root / 'stderr.txt').read_text()
        elapsed = time.monotonic() - started
        events = [json.loads(line) for line in (root / 'events.jsonl').read_text().splitlines()] if (root / 'events.jsonl').exists() else []
        result = json.loads((root / 'result.json').read_text()) if (root / 'result.json').exists() else None
        descendants = [e['child_pid'] for e in events if e['kind'] == 'descendant_started']
        # Observe past the child's planned write, proving the actual tree was
        # terminated rather than merely losing its parent's result channel.
        if descendants:
            time.sleep(.85)
        late = (root / 'late').exists()
        status = 'timeout' if timed_out else ('completed' if child.returncode == 0 and result else 'failed')
        record = {'schema': 'IM19-SUPERVISION-1', 'attempt_id': attempt, 'scenario': scenario,
            'status': status, 'pid': child.pid, 'returncode': child.returncode,
            'timeout_seconds': timeout, 'elapsed_seconds': elapsed, 'entry_observed': any(e['kind']=='entry' for e in events),
            'readiness_observed': any(e['kind']=='ready' for e in events), 'events': events,
            'stdout': stdout, 'stderr': stderr, 'result': result, 'descendant_pids': descendants,
            'late_descendant_effect': late, 'process_group_cleanup_requested': True,
            'retries': 0, 'external_action_replayed': False, 'real_model_called': False,
            'usage': {'state': 'unknown' if status != 'completed' else 'known', 'provider_tokens': None},
            'artifacts': {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in sorted(root.iterdir()) if p.is_file()},
            'temporary_scope_removed': False}
    record['temporary_scope_removed'] = not root.exists()
    _exclusive(destination, record)
    return record, destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', choices=SCENARIOS, required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--token', required=True)
    args = parser.parse_args()
    worker(args.root, args.worker, args.token)


if __name__ == '__main__':
    main()


def persist_result(category, record):
    """The public gate supplies a new run directory; every opportunity is sealed."""
    folder = os.environ.get('DIGITAL_LIFE_IM19_EVIDENCE_DIR')
    if not folder:
        return None
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / (category + '-' + uuid.uuid4().hex + '.json')
    _exclusive(destination, record)
    return str(destination)
