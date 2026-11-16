"""Exact local file-signature leases; fresh synthetic stores and no models."""
from contextlib import contextmanager
from contextvars import copy_context
import sys
import unittest
from unittest.mock import patch

from digital_life.application.learning.eligibility import (
    EligibilityAuthority, ToolLearningEligibility,
)
from digital_life.infrastructure.persistence import tool_learning_readset as reads
from tests import test_tool_learning_certified_input as fixture


class _AuditingAuthority(EligibilityAuthority):
    def __init__(self, observe):
        self.observe = observe

    def verify_version(self, entry, principal, token, stage):
        self.observe()

    def verify(self, entry, principal, token, scope, purpose, recipient, stage):
        self.observe()


class _DerivedEligibility(ToolLearningEligibility):
    pass


class FileLeaseBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.case = fixture.CertifiedInputTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.s = self.case.s
        self.owner = self.case.e.owners
        self.service = self.owner.eligibility
        self.location = self.s.row('artifacts', self.case.token['object']['id'])['storage_ref']
        self.path = self.s.root / 'blobs' / self.location

    @contextmanager
    def boundary(self):
        with self.case.meter().installed(self.s), self.owner.source.verification_boundary():
            phase = reads.current_readset(self.s)
            # Entry probes can attest only files already tracked at entry.
            phase.track_location(self.location)
            yield phase

    def check(self, service=None):
        return (service or self.service)._check(
            self.case.entry, self.case.principal, self.case.token,
            self.case.scope, self.case.principal['purpose'],
            self.case.principal['recipient'], 'synthetic-file-lease-boundary',
        )

    @contextmanager
    def on_body(self, service, action):
        """Observe the real method without replacing a trusted method identity."""
        original = sys.getprofile()
        target = ToolLearningEligibility._check_current.__code__
        entered = False

        def profile(frame, event, arg):
            nonlocal entered
            if (not entered and event == 'call' and frame.f_code is target
                    and frame.f_locals.get('self') is service):
                entered = True
                action()

        sys.setprofile(profile)
        try:
            yield
            self.assertTrue(entered, 'real qualification body was not observed')
        finally:
            sys.setprofile(original)

    def assert_real_track(self, phase, observed):
        before = observed.call_count
        phase.track_location(self.location)
        self.assertEqual(observed.call_count, before + 1)

    def test_unknown_authority_never_borrows_local_lease(self):
        observations = []
        with self.boundary() as phase, patch.object(reads, '_signature', wraps=reads._signature) as stat:
            def observe():
                observations.append(phase.signature_check)
                self.assertIsNone(phase.signature_check)
                self.assert_real_track(phase, stat)

            unknown = ToolLearningEligibility(self.s, _AuditingAuthority(observe))
            self.assertTrue(self.check(unknown)['qualified'])
            self.assertTrue(observations)
            self.assertIsNone(phase.signature_check)
            self.assertEqual(phase.check_depth, 0)

    def test_eligibility_subclass_uses_original_signature_path(self):
        service = _DerivedEligibility(self.s, self.owner.source)
        with self.boundary() as phase, patch.object(reads, '_signature', wraps=reads._signature) as stat:
            def body():
                self.assertIsNone(phase.signature_check)
                self.assert_real_track(phase, stat)

            with self.on_body(service, body):
                self.assertTrue(self.check(service)['qualified'])

    def test_instance_method_override_cannot_mint_a_trusted_lease(self):
        original = self.service._check_current
        seen = []
        with self.boundary() as phase, patch.object(reads, '_signature', wraps=reads._signature) as stat:
            def body(*args, **kwargs):
                seen.append(phase.signature_check)
                self.assertIsNone(phase.signature_check)
                self.assert_real_track(phase, stat)
                return original(*args, **kwargs)

            with patch.object(self.service, '_check_current', new=body):
                self.assertTrue(self.check()['qualified'])
            self.assertEqual(seen, [None])
            self.assertIsNone(phase.signature_check)

    def test_unknown_nested_check_suspends_and_restores_the_outer_lease(self):
        nested_observations = []
        with self.boundary() as phase, patch.object(reads, '_signature', wraps=reads._signature) as stat:
            def unknown_body():
                nested_observations.append((phase.check_depth, phase.signature_check))
                self.assertEqual(phase.check_depth, 2)
                self.assertIsNone(phase.signature_check)
                self.assert_real_track(phase, stat)

            unknown = ToolLearningEligibility(self.s, _AuditingAuthority(unknown_body))

            def outer_body():
                lease = phase.signature_check
                self.assertIsNotNone(lease)
                self.assertEqual(phase.check_depth, 1)
                self.assertTrue(self.check(unknown)['qualified'])
                self.assertIs(phase.signature_check, lease)
                self.assertEqual(phase.check_depth, 1)
                before = stat.call_count
                phase.track_location(self.location)
                self.assertEqual(stat.call_count, before)

            with self.on_body(self.service, outer_body):
                self.assertTrue(self.check()['qualified'])
            self.assertTrue(nested_observations)
            self.assertIsNone(phase.signature_check)
            self.assertEqual(phase.check_depth, 0)

    def test_fresh_artifact_read_always_stats_inside_a_valid_local_lease(self):
        with self.boundary() as phase:
            expected = self.service.artifacts.read_artifact(self.case.token['object']['id'])
            with patch.object(reads, '_signature', wraps=reads._signature) as stat:
                def body():
                    self.assertIsNotNone(phase.signature_check)
                    before = stat.call_count
                    phase.track_location(self.location)
                    self.assertEqual(stat.call_count, before)
                    phase.track_location(self.location, fresh=True)
                    self.assertEqual(stat.call_count, before + 1)
                    before = stat.call_count
                    actual = self.service.artifacts.read_artifact(
                        self.case.token['object']['id'], fresh=True,
                    )
                    self.assertEqual(actual, expected)
                    self.assertGreater(stat.call_count, before)

                with self.on_body(self.service, body):
                    self.assertTrue(self.check()['qualified'])

    def test_copied_context_cannot_revive_a_completed_local_check(self):
        saved = []
        with self.boundary() as phase, patch.object(reads, '_signature', wraps=reads._signature) as stat:
            def body():
                self.assertIsNotNone(phase.signature_check)
                saved.append(copy_context())

            with self.on_body(self.service, body):
                self.assertTrue(self.check()['qualified'])
            self.assertIsNone(phase.signature_check)
            before = stat.call_count
            saved[0].run(phase.track_location, self.location)
            self.assertEqual(stat.call_count, before + 1)
        self.assertIsNone(saved[0].run(reads.current_readset, self.s))
        self.assertFalse(saved[0].run(phase._tracked_signature_current, self.path))


if __name__ == '__main__':
    unittest.main()
