import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import shutil
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.learning.health import CurrentHealthEvidence
from digital_life.domain.contracts import Forbidden


class HealthCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Store.prepare(Path(self.tmp.name)/'instance');self.addCleanup(self.s.close)

    def test_long_measurement_can_be_consumed_fresh_after_completion(self):
        clock=[0.0];actual_disk=shutil.disk_usage
        def slow_disk(path):
            clock[0]+=4
            return actual_disk(path)
        with patch('digital_life.application.learning.health.time.monotonic',side_effect=lambda:clock[0]), patch('digital_life.application.learning.health.shutil.disk_usage',side_effect=slow_disk):
            evidence=CurrentHealthEvidence(self.s,'test',{'id':'test'},completion_freshness=True)
            clock[0]+=.1
            states=evidence.consume(self.s,'test')
            self.assertTrue(all(row['fresh'] for row in states.values()))
            self.assertTrue(evidence.audit()['database_unchanged'])
            self.assertEqual(evidence.audit()['measurement_elapsed_ms'],4000)
            with self.assertRaises(Forbidden):evidence.consume(self.s,'test')

    def test_completed_result_still_expires_after_one_second(self):
        clock=[0.0]
        with patch('digital_life.application.learning.health.time.monotonic',side_effect=lambda:clock[0]):
            evidence=CurrentHealthEvidence(self.s,'test',{'id':'test'},completion_freshness=True)
            clock[0]=1.1
            with self.assertRaises(Forbidden):evidence.consume(self.s,'test')

    def test_other_connection_commit_invalidates_measurement(self):
        evidence=CurrentHealthEvidence(self.s,'test',{'id':'test'},completion_freshness=True)
        other=Store(self.s.root)
        try:
            with other.tx():other.event('test.health_changed',payload={'test':True},lane='control')
        finally:other.close()
        with self.assertRaises(Forbidden):evidence.consume(self.s,'test')

    def test_default_guard_retains_start_time_semantics(self):
        clock=[0.0];actual_disk=shutil.disk_usage
        def slow_disk(path):
            clock[0]+=4
            return actual_disk(path)
        with patch('digital_life.application.learning.health.time.monotonic',side_effect=lambda:clock[0]), patch('digital_life.application.learning.health.shutil.disk_usage',side_effect=slow_disk):
            evidence=CurrentHealthEvidence(self.s,'test',{'id':'test'})
            with self.assertRaises(Forbidden):evidence.consume(self.s,'test')
