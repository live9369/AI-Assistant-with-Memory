"""IM19 physical write fault matrix against actual C1/C2/F1 owner paths.

Only TEMP triggers on a newly seeded synthetic database are changed. Production
DDL is untouched. SQLite user-function fault markers survive transaction rollback
in the external runner so injection firing cannot be inferred from an exception.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def snapshot(db):
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {t: sorted([list(row) for row in db.execute('SELECT * FROM "' + t + '"')], key=repr) for t in tables}


def physical_target(phase, logical):
    if logical in ('object_registry', 'object_revision_registry'):
        kind = 'tl_content_revision' if phase == 'C1' else 'tl_representation'
        return logical, 'INSERT', "NEW.kind='" + kind + "'"
    return {
        ('C1', 'tl_decision'): ('tl_decision', 'INSERT', '1'),
        ('C1', 'tl_content_revision'): ('tl_content_revision', 'INSERT', '1'),
        ('C1', 'tl_content-head'): ('tl_content', 'UPDATE', 'NEW.head_revision_id IS NOT NULL'),
        ('C1', 'tl_acceptance_group-member'): ('tl_group', 'INSERT', '1'),
        ('C1', 'tl_handoff'): ('tl_handoff', 'INSERT', '1'),
        ('C2', 'tl_representation'): ('tl_representation', 'INSERT', '1'),
        ('C2', 'tl_representation_head'): ('tl_representation_head', 'INSERT', '1'),
        ('C2', 'tl_handoff-consumer_receipt'): ('tl_handoff', 'UPDATE', "NEW.state='published'"),
        ('C2', 'tl_acceptance_group-ready'): ('tl_group', 'UPDATE', "NEW.state='ready'"),
        ('F1', 'tl_change'): ('tl_change', 'INSERT', '1'),
        ('F1', 'source_epoch'): ('tl_source_epoch', 'INSERT', '1'),
        ('F1', 'tl_barrier'): ('tl_barrier', 'INSERT', '1'),
        ('F1', 'tl_propagation-required_obligation'): ('tl_propagation', 'INSERT', '1'),
        ('F1', 'tl_input_dependency-invalidation'): ('tl_input_dependency', 'UPDATE', "NEW.retention_state='blocked'"),
    }.get((phase, logical), ('tl_command', 'UPDATE', "NEW.state='committed'"))


def run_write_fault(case):
    ident = case['id']; stem = ident.removeprefix('MECH-WRITE-')
    phase, rest = stem.split('-', 1)
    boundary = 'after_write_before_commit' if rest.endswith('-after_write_before_commit') else 'before_write'
    logical = rest[:-(len(boundary)+1)]
    from tests.test_tool_learning_acceptance import AcceptanceTests
    from tests.test_tool_learning_representation import RepresentationTests
    from tests.test_tool_learning_invalidation import F1Tests
    fixture = {'C1': AcceptanceTests, 'C2': RepresentationTests, 'F1': F1Tests}[phase]()
    fixture.setUp()
    try:
        if phase == 'C1':
            if logical == 'tl_acceptance_group-member':
                fixture.group()
            else:
                fixture.policy(); fixture.review()
            action = fixture.decide
            payload = fixture.request
        elif phase == 'C2':
            if logical == 'tl_acceptance_group-ready':
                fixture.group_setup()
                first = fixture.group_publish_request(0)
                fixture.service.publish(fixture.entries[0], first)
                payload = fixture.group_publish_request(1)
                action = lambda: fixture.service.publish(fixture.entries[1], payload)
            else:
                payload = fixture.publish_request()
                action = lambda: fixture.service.publish(fixture.entry, payload)
        else:
            dependency = fixture.dependency()
            fixture.elig.register_input('mechanical-im06', fixture.query_principal, fixture.consumer, dependency)
            payload = fixture.request()
            action = lambda: fixture.apply(payload)
        s = fixture.s; db = s.db
        shared = s.artifact({'im19': 'preexisting-shared-body', 'payload': 'x'*8192})
        if s.artifact({'im19': 'preexisting-shared-body', 'payload': 'x'*8192}) != shared:
            raise AssertionError('shared blob was not actually deduplicated')
        from digital_life.domain.contracts import dumps
        shared_second=s.artifact(dumps({'im19':'preexisting-shared-body','payload':'x'*8192}),media_type='text/plain')
        if shared_second==shared or s.row('artifacts',shared_second)['storage_ref']!=s.row('artifacts',shared)['storage_ref']:
            raise AssertionError('two real artifact references did not share the actual blob')
        blob_state = lambda: {p.name: {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(), 'inode':p.stat().st_ino, 'bytes':p.stat().st_size} for p in (s.root/'blobs').iterdir() if p.is_file()}
        blobs_before = blob_state()
        before = snapshot(db)
        table, operation, condition = physical_target(phase, logical)
        hits = []
        def injected(row_id):
            hits.append({'row_id': row_id, 'table': table, 'operation': operation, 'boundary': boundary})
            raise RuntimeError('IM19 deterministic physical write failure')
        db.create_function('im19_fault', 1, injected)
        when = 'BEFORE' if boundary == 'before_write' else 'AFTER'
        db.execute('CREATE TEMP TRIGGER im19_injection ' + when + ' ' + operation + ' ON main.' + table +
            ' WHEN ' + condition + ' BEGIN SELECT im19_fault(NEW.id); END')
        error = None
        try:
            action()
        except sqlite3.OperationalError as exc:
            error = str(exc)
        finally:
            db.execute('DROP TRIGGER im19_injection')
        after = snapshot(db)
        if not hits or error is None:
            raise AssertionError('physical injection not reached: ' + ident)
        if before != after:
            changed = [t for t in before if before[t] != after[t]]
            raise AssertionError('transaction not fully rolled back: ' + repr(changed))
        blobs_after = blob_state()
        if any(blobs_after.get(name) != state for name,state in blobs_before.items()):
            raise AssertionError('preexisting/shared blob removed or changed by rollback')
        new_blobs = {name:state for name,state in blobs_after.items() if name not in blobs_before}
        referenced = {r[0] for r in db.execute('SELECT storage_ref FROM artifacts')}
        orphans = {name:state for name,state in new_blobs.items() if name not in referenced}
        if new_blobs:
            raise AssertionError('rollback left new blobs; retain and reconcile orphan evidence: '+repr(orphans))
        integrity = s.integrity()
        if integrity != {'integrity': 'ok', 'foreign_keys': []}:
            raise AssertionError('integrity failure: ' + repr(integrity))
        digest = lambda v: hashlib.sha256(json.dumps(v, sort_keys=True, default=lambda x: {"bytes_hex": x.hex()} if isinstance(x, bytes) else str(x)).encode()).hexdigest()
        return {'case_id': ident, 'fixture': phase + '-actual-owner-service',
            'logical_write': logical, 'physical_table': table, 'physical_operation': operation,
            'trigger_boundary': when, 'trigger_condition': condition,
            'request': payload, 'injection_hits': hits, 'exception': error,
            'before_digest': digest(before), 'after_digest': digest(after),
            'table_rows_before': {t: len(rows) for t, rows in before.items()},
            'transaction_rollback_verified': True, 'prior_rows_preserved': True,
            'blob_state_before':blobs_before, 'blob_state_after':blobs_after,
            'preexisting_shared_blob_preserved':True, 'new_blobs_after_rollback':new_blobs,
            'unregistered_orphans_after_rollback':orphans, 'filesystem_claim_scope':'managed blob directory only; no indexes touched by C1/C2/F1',
            'integrity': integrity, 'endpoint': 'atomic_rollback_no_partial_' + phase,
            'real_model_called': False, 'external_action_replayed': False}
    finally:
        fixture.doCleanups()
