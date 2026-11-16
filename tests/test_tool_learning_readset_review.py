"""Independent PF04 review: local transactions cannot hide external changes."""
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import Conflict
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.infrastructure.persistence.tool_learning_readset import shared_read_boundary,facts,checkpoint,track_artifact

class PhaseTransactionReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.s=Store.prepare(self.temp.name);self.addCleanup(self.s.close)
        self.s.db.execute('PRAGMA journal_mode=WAL')
        self.s.db.execute('CREATE TABLE pf04_review_probe(value INTEGER)')
        self.s.db.execute('INSERT INTO pf04_review_probe VALUES(0)')
        self.actor=self.s.config()['controller']
    def external_write(self):
        db=sqlite3.connect(self.s.root/'runtime.sqlite')
        try:db.execute('UPDATE pf04_review_probe SET value=value+1');db.commit()
        finally:db.close()
    def test_normal_store_uow_changes_generation_and_remains_usable(self):
        with shared_read_boundary(self.s)as phase:
            list(facts(self.s,'source_kind',self.actor));before=phase.generation
            with self.s.tx():self.s.db.execute('UPDATE pf04_review_probe SET value=value+1')
            self.assertGreater(phase.generation,before);checkpoint(self.s)
            self.assertEqual(list(facts(self.s,'source_kind',self.actor))[0][0],'social_actors')
    def test_raw_commit_after_checkpoint_is_conservatively_rejected(self):
        with self.assertRaises(Conflict):
            with shared_read_boundary(self.s):
                self.s.db.execute('BEGIN IMMEDIATE')
                self.s.db.execute('UPDATE pf04_review_probe SET value=value+1')
                checkpoint(self.s)
                self.s.db.execute('COMMIT')
                checkpoint(self.s)
    def test_external_commit_before_local_uow_cannot_be_hidden(self):
        with self.assertRaises(Conflict):
            with shared_read_boundary(self.s):
                list(facts(self.s,'source_kind',self.actor));self.external_write()
                with self.s.tx():self.s.db.execute('UPDATE pf04_review_probe SET value=value+1')
                checkpoint(self.s)
    def test_external_commit_in_postcommit_cleanup_gap_cannot_be_hidden(self):
        original=self.s._discard_unregistered_blobs
        def cleanup(created):
            result=original(created);self.external_write();return result
        with self.assertRaises(Conflict):
            with shared_read_boundary(self.s):
                with patch.object(self.s,'_discard_unregistered_blobs',cleanup):
                    with self.s.tx():self.s.db.execute('UPDATE pf04_review_probe SET value=value+1')
                checkpoint(self.s)
    def test_transaction_cleanup_does_not_replace_original_exception(self):
        path=self.s.root/'control.sqlite';path.write_bytes(b'synthetic control')
        with self.assertRaisesRegex(ValueError,'original synthetic failure'):
            with shared_read_boundary(self.s):
                with self.s.tx():
                    path.write_bytes(b'changed synthetic control')
                    raise ValueError('original synthetic failure')
    def test_file_tracking_survives_a_successful_local_uow(self):
        key=self.s.artifact({'source':'synthetic original'});row=self.s.row('artifacts',key)
        with self.assertRaisesRegex(Conflict,'artifact changed'):
            with shared_read_boundary(self.s):
                track_artifact(self.s,key)
                with self.s.tx():self.s.db.execute('UPDATE pf04_review_probe SET value=value+1')
                path=self.s.root/'blobs'/row['storage_ref'];raw=path.read_bytes();path.write_bytes(b'x'*len(raw))
                checkpoint(self.s)

if __name__=='__main__':unittest.main()
