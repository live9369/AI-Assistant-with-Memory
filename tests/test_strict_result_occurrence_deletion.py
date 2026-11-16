"""Occurrence paths preserve versioned closure and the existing shared-body guard.

These are isolated lineage/adapter-boundary tests, not a public maintenance
authorization or deletion run. No model or formal-instance access is involved.
"""
from copy import deepcopy
import unittest

from digital_life.application.learning.eligibility import ref
from digital_life.application.learning.invalidation import ToolLearningInvalidation
from digital_life.application.learning.propagation import ManagedErasure
from digital_life.domain import tool_learning_contract as contract
from digital_life.domain.contracts import identifier
from tests import test_strict_result_occurrence_lineage as fixture


class ResultOccurrenceDeletionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.OccurrenceLineageTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.s = self.fixture.s
        with self.s.tx():
            self.first = self.fixture.result()
            self.fixture.retain(*self.first, self.fixture.tokens[0])
            self.second = self.fixture.result()
            self.fixture.retain(*self.second, self.fixture.tokens[1])
        self.assertNotEqual(self.first[0], self.second[0])
        self.assertNotEqual(self.first[1], self.second[1])
        self.assertEqual(self.first[2], self.second[2])

    def test_occurrence_prefix_preserves_revoke_and_erase_exact_revision_closure(self):
        resolver = ToolLearningInvalidation(self.s)
        artifact = self.first[2]
        for operation in ('revoke', 'erase'):
            with self.subTest(operation=operation):
                first, truncated = resolver._closure(self.fixture.tokens[0], operation)
                second, second_truncated = resolver._closure(self.fixture.tokens[1], operation)
                self.assertFalse(truncated)
                self.assertFalse(second_truncated)
                self.assertIn((self.first[1], None), first)
                self.assertIn((artifact, None), first)
                self.assertNotIn((self.second[1], None), first)
                self.assertIn((self.second[1], None), second)
                self.assertIn((artifact, None), second)
                self.assertNotIn((self.first[1], None), second)
        # The shared artifact retains each occurrence, not one edge chosen by
        # body equality. Each result also retains its original field paths.
        self.assertEqual(len(self.fixture.edges(artifact)), 4)
        self.assertEqual(len(self.fixture.edges(self.first[1])), 2)
        self.assertEqual(len(self.fixture.edges(self.second[1])), 2)
        self.assertEqual(self.s.db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def _guard_plan(self):
        """Seed real FK context for the guard; confer no maintenance grant."""
        source = deepcopy(self.fixture.tokens[0])
        payload = {'source': source}
        with self.s.tx():
            change = self.s.insert(
                'tl_change', change_key=identifier(),
                fingerprint=contract.fingerprint(payload),
                payload_artifact_id=self.s.artifact(payload), kind='erase',
                source_ref_id=source['object']['id'], expected_epoch=0, result_epoch=1,
            )
            barrier = self.s.insert(
                'tl_barrier', change_id=change, source_ref_id=source['object']['id'],
                source_epoch=1, kind='erase',
                scope_artifact_id=self.s.artifact(self.fixture.scope),
                authorization_ref_id=self.fixture.case.principal['authorization']['id'],
                state='active', row_revision=0,
            )
        return {
            'id': identifier(), 'barrier_id': barrier,
            'source_activity': self.fixture.case.f.activity,
            'targets': [self._result_target(self.first[1])],
        }

    def _result_target(self, result):
        return {
            'target': ref(self.s, result), 'location': 'database', 'operation': 'purge',
            'expected': {'row_digest': contract.fingerprint(self.s.row('thought_results', result))},
        }

    def test_first_occurrence_scope_cannot_redact_or_unlink_second_occurrence_body(self):
        erasure = ManagedErasure(self.s)
        plan = self._guard_plan()
        artifact = self.first[2]
        before = self.s.row('artifacts', artifact)
        path = self.s.root / 'blobs' / before['storage_ref']
        original_bytes = path.read_bytes()
        self.assertFalse(erasure._artifact_consumers_in_scope(plan, artifact))
        complete_cohort = deepcopy(plan)
        complete_cohort['targets'].append(self._result_target(self.second[1]))
        self.assertTrue(erasure._artifact_consumers_in_scope(complete_cohort, artifact))

        body_target = {
            'target': ref(self.s, artifact), 'location': 'database', 'operation': 'tombstone',
            'expected': {'hash': before['hash'], 'storage_ref': before['storage_ref']},
        }
        verdict = erasure._target('synthetic-no-maintenance-grant', plan, body_target)
        self.assertEqual(verdict['state'], 'blocked')
        self.assertIn('outside', verdict['reason'])

        stat = path.stat()
        blob_target = {
            'target': ref(self.s, artifact), 'location': 'blob', 'operation': 'unlink',
            'expected': {'storage_ref': before['storage_ref'], 'device': stat.st_dev,
                         'inode': stat.st_ino, 'hash': before['hash']},
        }
        verdict = erasure._target('synthetic-no-maintenance-grant', plan, blob_target)
        self.assertEqual(verdict['state'], 'blocked')
        self.assertIn('registered reference', verdict['reason'])
        self.assertEqual(self.s.row('artifacts', artifact), before)
        self.assertEqual(path.read_bytes(), original_bytes)
        for request, result, body in (self.first, self.second):
            stored = self.s.row('thought_results', result)
            self.assertEqual(stored['request_id'], request)
            self.assertEqual(stored['response_artifact_id'], artifact)
            self.assertEqual(stored['parsed_artifact_id'], artifact)
        self.assertEqual(self.s.db.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
