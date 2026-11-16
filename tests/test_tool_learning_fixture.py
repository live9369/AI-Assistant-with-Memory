"""IM01 genuine schema2/schema3 synthetic fixtures, locked from creation to exit."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from digital_life.domain.contracts import ContractError, Conflict, Forbidden
from evaluation.tool_learning_fixture import (
    MEMORY_TEXT, SyntheticToolLearningFixture, new_root,
)


class ToolLearningFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name).resolve()

    def test_real_schema2_materials_are_synthetic_stopped_and_unexecuted(self):
        with SyntheticToolLearningFixture(self.parent / 'schema2') as fixture:
            expected = fixture.verify_seed()
            self.assertEqual(expected['schema_version'], 2)
            self.assertTrue(expected['synthetic'])
            self.assertFalse(expected['inference_executed'])
            self.assertFalse(expected['tool_executed'])
            self.assertEqual(fixture.store.config()['model']['backend'], 'unconfigured')
            self.assertEqual(fixture.store.rows('schema_migrations'), [])
            self.assertEqual(fixture.store.row('memory_revisions', expected['memory_revision_id'])['content'], MEMORY_TEXT)
            self.assertEqual(fixture.control.state()['runtime_epoch'], 0)
            self.assertEqual(fixture.control.db.execute('SELECT count(*) FROM process_runs').fetchone()[0], 0)
            with self.assertRaises(Forbidden):
                fixture.store.assert_execution_allowed()
            with self.assertRaises(Forbidden):
                fixture.control.resume('must-not-unlock')
        self.assertTrue(fixture.closed)
        self.assertTrue((fixture.root / 'WAKE_DISABLED').exists())
        report = json.loads((fixture.root / 'fixture-lifecycle.json').read_text())
        self.assertFalse(report['failed'])
        self.assertEqual(report['recorded_attempt_counts'], {'thought_attempts': 0, 'action_attempts': 0})
        with self.assertRaises(sqlite3.ProgrammingError):
            fixture.store.db.execute('SELECT 1')
        with self.assertRaises(sqlite3.ProgrammingError):
            fixture.control.db.execute('SELECT 1')

    def test_schema3_uses_real_migration_and_preserves_seed(self):
        with SyntheticToolLearningFixture(self.parent / 'schema3', schema_version=3) as fixture:
            self.assertEqual(fixture.verify_seed()['schema_version'], 3)
            migration = fixture.store.rows('schema_migrations')
            self.assertEqual(len(migration), 1)
            self.assertEqual(migration[0]['version'], 3)
            self.assertEqual(fixture.store.db.execute('SELECT count(*) FROM module_checkpoints').fetchone()[0], 0)
            self.assertEqual(len(list((fixture.root / 'snapshots').glob('pre-schema-3-*.sqlite'))), 1)
            self.assertEqual(fixture.control.state()['user_stopped'], 1)
            fixture.store.integrity()

    def test_new_instances_have_distinct_identity_and_root_specific_permissions(self):
        with SyntheticToolLearningFixture(self.parent / 'first') as first, SyntheticToolLearningFixture(self.parent / 'second') as second:
            self.assertNotEqual(first.store.instance_id, second.store.instance_id)
            self.assertNotEqual(first.expected['controller'], second.expected['controller'])
            self.assertNotEqual(first.expected['policy_id'], second.expected['policy_id'])
            self.assertEqual(first.verify_seed()['memory_text'], second.verify_seed()['memory_text'])

    def test_existing_root_is_rejected_without_opening_store_or_control(self):
        root = self.parent / 'existing'
        root.mkdir()
        sentinel = root / 'runtime.sqlite'
        sentinel.write_bytes(b'existing protected bytes')
        with patch('evaluation.tool_learning_fixture.Store.prepare', side_effect=AssertionError('must not open')), patch('evaluation.tool_learning_fixture.Control', side_effect=AssertionError('must not open')):
            with self.assertRaises(Conflict):
                SyntheticToolLearningFixture(root)
        self.assertEqual(sentinel.read_bytes(), b'existing protected bytes')
        self.assertEqual(sorted(p.name for p in root.iterdir()), ['runtime.sqlite'])

    def test_existing_file_and_dangling_or_normal_symlink_roots_rejected(self):
        file = self.parent / 'file'
        file.write_text('untouched')
        target = self.parent / 'real'
        target.mkdir()
        link = self.parent / 'link'
        link.symlink_to(target, target_is_directory=True)
        dangling = self.parent / 'dangling'
        dangling.symlink_to(self.parent / 'missing')
        for root in (file, link, dangling):
            with self.subTest(root=root.name), self.assertRaises(Conflict):
                SyntheticToolLearningFixture(root)
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(file.read_text(), 'untouched')

    def test_symlink_ancestor_and_parent_traversal_are_rejected(self):
        target = self.parent / 'real'
        target.mkdir()
        alias = self.parent / 'alias'
        alias.symlink_to(target, target_is_directory=True)
        with self.assertRaises(Forbidden):
            SyntheticToolLearningFixture(alias / 'child')
        with self.assertRaises(Forbidden):
            new_root(self.parent / 'unused' / '..' / 'child')
        self.assertEqual(list(target.iterdir()), [])

    def test_missing_parent_and_invalid_schema_are_rejected_before_creation(self):
        with self.assertRaises(ContractError):
            SyntheticToolLearningFixture(self.parent / 'missing' / 'root')
        for version in (True, 1, 4, '3', None):
            with self.subTest(version=version), self.assertRaises(ContractError):
                SyntheticToolLearningFixture(self.parent / 'bad', schema_version=version)
        self.assertFalse((self.parent / 'bad').exists())

    def test_root_created_after_construction_is_not_reused(self):
        fixture = SyntheticToolLearningFixture(self.parent / 'race')
        fixture.root.mkdir()
        (fixture.root / 'sentinel').write_text('keep')
        with self.assertRaises(Conflict):
            fixture.__enter__()
        self.assertEqual((fixture.root / 'sentinel').read_text(), 'keep')
        self.assertFalse((fixture.root / 'WAKE_DISABLED').exists())

    def test_context_exception_keeps_failure_evidence_and_closes_connections(self):
        with self.assertRaisesRegex(RuntimeError, 'fixture body failure'):
            with SyntheticToolLearningFixture(self.parent / 'failed') as fixture:
                raise RuntimeError('fixture body failure')
        report = json.loads((fixture.root / 'fixture-lifecycle.json').read_text())
        self.assertTrue(report['failed'])
        self.assertEqual(report['error_type'], 'RuntimeError')
        self.assertTrue((fixture.root / 'WAKE_DISABLED').exists())
        with self.assertRaises(sqlite3.ProgrammingError):
            fixture.control.state()
        raw = sqlite3.connect((fixture.root / 'control.sqlite').as_uri() + '?mode=ro', uri=True)
        try:
            self.assertEqual(raw.execute('SELECT user_stopped,active_process_run_id FROM instance_control_state').fetchone(), (1, None))
        finally:
            raw.close()

    def test_initialization_failure_closes_owned_state_without_suppressing_error(self):
        fixture = SyntheticToolLearningFixture(self.parent / 'init-failed')
        with patch.object(fixture, '_seed', side_effect=RuntimeError('seed failure')):
            with self.assertRaisesRegex(RuntimeError, 'seed failure'):
                fixture.__enter__()
        self.assertTrue(fixture.closed)
        self.assertTrue((fixture.root / 'WAKE_DISABLED').exists())
        report = json.loads((fixture.root / 'fixture-lifecycle.json').read_text())
        self.assertTrue(report['failed'])
        self.assertEqual(report['phase'], 'seed')
        with self.assertRaises(sqlite3.ProgrammingError):
            fixture.store.db.execute('SELECT 1')

    def test_prepare_failure_still_locks_new_owned_directory(self):
        fixture = SyntheticToolLearningFixture(self.parent / 'prepare-failed')
        with patch('evaluation.tool_learning_fixture.Store.prepare', side_effect=RuntimeError('prepare failed')):
            with self.assertRaises(RuntimeError):
                fixture.__enter__()
        self.assertTrue(fixture.closed)
        self.assertTrue((fixture.root / 'WAKE_DISABLED').is_file())
        self.assertEqual(json.loads((fixture.root / 'fixture-lifecycle.json').read_text())['phase'], 'prepare')

    def test_fixture_never_silently_reopens_a_completed_root(self):
        fixture = SyntheticToolLearningFixture(self.parent / 'single')
        with fixture:
            fixture.verify_seed()
        with self.assertRaises(Conflict):
            fixture.__enter__()
        with self.assertRaises(Conflict):
            SyntheticToolLearningFixture(fixture.root)
        fixture.close()  # cleanup itself is idempotent

    def test_exit_relocks_even_if_test_removed_lock_and_resumed(self):
        with SyntheticToolLearningFixture(self.parent / 'mutated') as fixture:
            (fixture.root / 'WAKE_DISABLED').unlink()
            fixture.control.resume('test-removed-lock')
            self.assertEqual(fixture.control.state()['user_stopped'], 0)
        self.assertTrue((fixture.root / 'WAKE_DISABLED').is_file())
        raw = sqlite3.connect((fixture.root / 'control.sqlite').as_uri() + '?mode=ro', uri=True)
        try:
            self.assertEqual(raw.execute('SELECT user_stopped,active_process_run_id FROM instance_control_state').fetchone(), (1, None))
        finally:
            raw.close()

    def test_seed_verifier_rejects_contradictory_permission_or_material(self):
        with SyntheticToolLearningFixture(self.parent / 'check') as fixture:
            fixture.expected['memory_revision_id'] = 'invented'
            with self.assertRaises(ContractError):
                fixture.verify_seed()

class ToolLearningFixtureRedirectTests(unittest.TestCase):
    def test_redirected_stop_lock_never_overwrites_external_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp).resolve()
            outside = parent / 'outside.txt'
            outside.write_text('keep outside bytes')
            with SyntheticToolLearningFixture(parent / 'instance') as fixture:
                lock = fixture.root / 'WAKE_DISABLED'
                lock.unlink()
                lock.symlink_to(outside)
                with self.assertRaises(ContractError):
                    fixture.verify_seed()
            self.assertEqual(outside.read_text(), 'keep outside bytes')
            self.assertFalse(lock.is_symlink())
            self.assertTrue(lock.is_file())
            self.assertTrue(fixture.closed)

    def test_incorrect_migration_checksum_is_not_schema3_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            with SyntheticToolLearningFixture(Path(tmp).resolve() / 'instance', 3) as fixture:
                fixture.store.db.execute("UPDATE schema_migrations SET checksum='forged' WHERE version=3")
                with self.assertRaises(ContractError):
                    fixture.verify_seed()

    def test_new_leaf_inside_an_existing_instance_is_rejected_before_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp).resolve()
            instance = parent / 'existing-instance'
            instance.mkdir()
            (instance / 'runtime.sqlite').write_bytes(b'protected instance')
            with patch('evaluation.tool_learning_fixture.Store.prepare', side_effect=AssertionError('must not open')):
                with self.assertRaises(Forbidden):
                    SyntheticToolLearningFixture(instance / 'new-child')
            self.assertEqual((instance / 'runtime.sqlite').read_bytes(), b'protected instance')
            self.assertFalse((instance / 'new-child').exists())


if __name__ == '__main__':
    unittest.main()
