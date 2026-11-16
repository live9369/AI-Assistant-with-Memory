"""IM01: locked, newly created synthetic fixtures; never opens existing data."""
import json
import os
from pathlib import Path

from digital_life.domain.contracts import ContractError, Conflict, Forbidden, dumps, identifier, sha, utc
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.runtime.engine import Engine
from digital_life.application.accounts.authorization import Policy
from digital_life.application.services.commitments import Commitments
from digital_life.application.services.decisions import Decisions
from digital_life.application.services.memory import Memory

MEMORY_TEXT = 'IM01 synthetic observation: source S reported inventory 7.'
TASK_TEXT = 'IM01 synthetic controller request: retain source and history.'
PROMISE_TEXT = 'IM01 synthetic future commitment: verify inventory later.'
MARKER = 'IM01_FIXTURE.json'


def new_root(value):
    """Validate before resolve/open: existing or redirected roots are forbidden."""
    raw = Path(value)
    if '..' in raw.parts:
        raise Forbidden('fixture parent traversal denied')
    root = Path(os.path.abspath(os.fspath(raw)))
    if root.exists() or root.is_symlink():
        raise Conflict('fixture requires a new, nonexistent root')
    if not root.parent.is_dir():
        raise ContractError('fixture parent directory must already exist')
    for parent in (root.parent, *root.parent.parents):
        if parent.is_symlink():
            raise Forbidden('fixture ancestors must not be symbolic links')
        if any((parent / name).exists() or (parent / name).is_symlink() for name in ('runtime.sqlite', 'control.sqlite', 'WAKE_DISABLED')):
            raise Forbidden('fixture cannot be nested inside an instance directory')
    return root


class SyntheticToolLearningFixture:
    def __init__(self, root, schema_version=2):
        if type(schema_version) is not int or schema_version not in (2, 3):
            raise ContractError('IM01 fixture schema must be 2 or 3')
        self.root = new_root(root)
        self.schema_version = schema_version
        self.store = None
        self.control = None
        self.expected = None
        self.closed = False
        self._owned = False
        self._token = identifier()
        self._phase = 'not_started'

    def __enter__(self):
        if self._owned or self.closed:
            raise Conflict('fixture contexts are single use')
        new_root(self.root)
        self.root.mkdir(mode=0o700, exist_ok=False)
        self._owned = True
        try:
            (self.root / MARKER).write_text(dumps({'token': self._token, 'scope': 'IM01 synthetic only'}))
            self._phase = 'prepare'
            self.store = Store.prepare(self.root, name='IM01 synthetic identity')
            self.control = Control(self.root, self.store.instance_id)
            self._phase = 'seed'
            self._seed()
            self._phase = 'schema'
            if self.schema_version == 3:
                from digital_life.application.lifecycle.schema_migration import migrate
                migrate(self.store, self.store.config()['controller'], target=3)
            self._phase = 'verify'
            self.verify_seed()
            (self.root / 'fixture-seed.json').write_text(dumps(self.expected))
            self._phase = 'ready'
            return self
        except BaseException as error:
            self.close(error)
            raise

    def _seed(self):
        s = self.store
        actor = s.config()['controller']
        with s.tx():
            original = s.event('fixture.im01.original', payload={'synthetic': True, 'source': 'S', 'reported_value': 7})
            evidence = s.evidence(object_id=original, method='explicit-synthetic-fixture')
            memory = Memory(s).encode(MEMORY_TEXT, evidence)
            activity = Engine(s).submit(TASK_TEXT, 'im01-synthetic-input', source='fixture')
            signal = Engine(s).details(activity)[2]['id']
            promise = Commitments(s).propose(actor, PROMISE_TEXT, utc(86400))
            Commitments(s).transition(promise, 'confirmed', signal)
            Commitments(s).transition(promise, 'active', signal)
            _, context, _, goal = Engine(s).details(activity)
            action = {'tool': 'read_file', 'arguments': {'path': 'fixture-input.txt'}}
            decision = Decisions(s).finalize(activity, goal['id'], context['id'], [action])
            intent = Policy(s).propose(activity, decision['selected'], action)
            approval = Policy(s).request(intent)
            history = s.event('fixture.im01.history', payload={'synthetic': True, 'activity': activity, 'promise': promise}, activity=activity)
        (s.root / 'workspace' / 'fixture-input.txt').write_text('synthetic inventory=7\n')
        self.expected = {
            'schema_version': self.schema_version, 'instance_id': s.instance_id,
            'controller': actor, 'self_actor': s.config()['self_actor'],
            'anchor_digest': sha(dumps(s.rows('identity_anchors'))),
            'memory_id': memory['memory_id'], 'memory_revision_id': memory['revision_id'],
            'memory_text': MEMORY_TEXT, 'source_event_id': original, 'source_evidence_id': evidence,
            'activity_id': activity, 'signal_id': signal, 'history_event_id': history,
            'promise_id': promise, 'promise_content': PROMISE_TEXT,
            'due_at': s.row('commitment_items', promise)['due_at'],
            'intent_id': intent, 'approval_id': approval,
            'policy_id': s.rows('policy_epochs')[0]['policy_version_id'],
            'synthetic': True, 'inference_executed': False, 'tool_executed': False,
        }

    def verify_seed(self):
        if self.closed or self.store is None or self.expected is None:
            raise Conflict('fixture is not open and seeded')
        s = self.store
        e = self.expected
        if s.db.execute('PRAGMA user_version').fetchone()[0] != self.schema_version:
            raise ContractError('fixture schema mismatch')
        if s.integrity() != {'integrity': 'ok', 'foreign_keys': []}:
            raise ContractError('fixture storage integrity failed')
        if s.instance_id != e['instance_id'] or sha(dumps(s.rows('identity_anchors'))) != e['anchor_digest']:
            raise ContractError('fixture identity changed')
        if s.row('memory_revisions', e['memory_revision_id'])['content'] != MEMORY_TEXT:
            raise ContractError('fixture original memory changed')
        if s.row('memory_items', e['memory_id'])['current_revision_id'] != e['memory_revision_id']:
            raise ContractError('fixture memory revision changed')
        if s.row('evidence_items', e['source_evidence_id'])['origin_object_id'] != e['source_event_id']:
            raise ContractError('fixture memory evidence ownership changed')
        history = s.row('runtime_events', e['history_event_id'])
        if s.read_artifact(history['payload_artifact_id'])['promise'] != e['promise_id']:
            raise ContractError('fixture history association changed')
        promise = s.row('commitment_items', e['promise_id'])
        if promise['state'] != 'active' or promise['creditor_actor_id'] != e['controller'] or promise['debtor_actor_id'] != e['self_actor'] or promise['due_at'] != e['due_at'] or promise['due_at'] <= utc():
            raise ContractError('fixture future commitment changed')
        policy = s.row('policy_versions', e['policy_id'])
        if policy['mode'] != 'authorization' or json.loads(policy['scope'])['root'] != str(s.root / 'workspace'):
            raise ContractError('fixture policy changed')
        if s.row('action_intents', e['intent_id'])['state'] != 'awaiting_approval' or s.row('approval_requests', e['approval_id'])['decision'] != 'pending':
            raise ContractError('fixture approval changed')
        if (s.root / 'WAKE_DISABLED').is_symlink() or not (s.root / 'WAKE_DISABLED').is_file() or self.control.state()['user_stopped'] != 1 or self.control.state()['active_process_run_id'] is not None:
            raise ContractError('fixture is not locked and stopped')
        if s.rows('thought_requests') or s.rows('thought_attempts') or s.rows('action_attempts') or s.rows('action_results'):
            raise ContractError('IM01 fixture unexpectedly executed inference or tools')
        if self.schema_version == 3:
            migration = s.db.execute('SELECT checksum FROM schema_migrations WHERE version=3 AND instance_id=?', (s.instance_id,)).fetchone()
            from digital_life.application.lifecycle.schema_migration import V3
            if not migration or migration['checksum'] != sha(dumps(V3)) or not s.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='module_checkpoints'").fetchone():
                raise ContractError('fixture schema3 lacks real migration evidence')
        return dict(e, integrity='ok', locked=True)

    def close(self, error=None):
        if self.closed:
            return
        failure = None
        try:
            if self._owned:
                if self.root.is_symlink() or not self.root.is_dir():
                    raise Forbidden('owned fixture directory was replaced')
                marker = self.root / MARKER
                if not marker.is_file() or marker.is_symlink() or json.loads(marker.read_text())['token'] != self._token:
                    raise Forbidden('owned fixture marker changed')
                lock_error = None
                temporary_lock = self.root / ('.im01-lock-' + self._token)
                try:
                    with temporary_lock.open('x') as stream:
                        stream.write('IM01 synthetic evidence only; do not wake.\n')
                    # Replace the leaf itself, never follow a redirected stop-lock.
                    temporary_lock.replace(self.root / 'WAKE_DISABLED')
                except BaseException as problem:
                    lock_error = problem
                finally:
                    temporary_lock.unlink(missing_ok=True)
                if self.control is not None:
                    self.control.stop('im01-fixture-close-' + self._token)
                if lock_error is not None:
                    raise lock_error
                counts = {'thought_attempts': None, 'action_attempts': None}
                if self.store is not None:
                    try:
                        counts = {name: self.store.db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in counts}
                    except Exception:
                        pass
                (self.root / 'fixture-lifecycle.json').write_text(dumps({
                    'synthetic': True, 'phase': self._phase, 'closed': True,
                    'failed': error is not None, 'error_type': type(error).__name__ if error else None,
                    'schema_version': self.schema_version,
                    'instance_id': self.expected['instance_id'] if self.expected else None,
                    'fixture_initiated_inference': False, 'fixture_initiated_tools': False,
                    'recorded_attempt_counts': counts,
                }))
        except BaseException as cleanup_error:
            failure = cleanup_error
        finally:
            if self.control is not None:
                self.control.close()
            if self.store is not None:
                self.store.close()
            self.closed = True
        if failure is not None and error is None:
            raise failure

    def __exit__(self, kind, error, traceback):
        self.close(error)
        return False
