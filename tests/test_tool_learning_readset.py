"""Fresh synthetic phase-readset correctness, invalidation and accounting."""
from contextvars import copy_context
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from digital_life.domain.contracts import Conflict,ContractError,utc
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.infrastructure.persistence.tool_learning_readset import shared_read_boundary,facts,checkpoint,current_readset,track_artifact

class PhaseReadSetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.s=Store.prepare(self.temp.name);self.addCleanup(self.s.close)
        self.s.db.execute('PRAGMA journal_mode=WAL')
        self.s.db.execute('CREATE TABLE pf04_probe(value INTEGER)');self.s.db.execute('INSERT INTO pf04_probe VALUES(0)')
        self.actor=self.s.config()['controller'];self.sql=[];self.s.db.set_trace_callback(self.sql.append)
    def read(self,key=None):return list(facts(self.s,'source_kind',key or self.actor))
    def selects(self):return sum(sql.startswith('SELECT kind FROM object_registry')for sql in self.sql)
    def test_identical_demand_reads_once_without_aliasing_authority(self):
        with shared_read_boundary(self.s):
            first=self.read();second=self.read()
            self.assertEqual(first,second);self.assertEqual(self.selects(),1)
            self.assertEqual(first[0]['kind'],'social_actors');self.assertEqual(first[0][0],'social_actors')
        self.read();self.assertEqual(self.selects(),2)
    def test_instances_and_full_parameters_are_separate_and_unknown_query_rejected(self):
        with shared_read_boundary(self.s):
            self.read();self.assertEqual(self.read('missing'),[])
            with self.assertRaises(ContractError):facts(self.s,'SELECT anything')
            self.assertEqual(self.selects(),2)
    def test_same_connection_write_clears_facts(self):
        with shared_read_boundary(self.s):
            self.read();self.s.db.execute('UPDATE pf04_probe SET value=value+1')
            checkpoint(self.s);self.read();self.assertEqual(self.selects(),2)
    def test_local_commit_starts_new_generation_not_false_external_change(self):
        with shared_read_boundary(self.s)as phase:
            self.read();before=phase.generation
            with self.s.tx():
                self.s.db.execute('UPDATE pf04_probe SET value=value+1')
                checkpoint(self.s)
            checkpoint(self.s);self.read()
            self.assertGreater(phase.generation,before)
            self.assertEqual(self.selects(),2)
    def test_artifact_parent_directory_symlink_rejected(self):
        key=self.s.artifact({'source':'parent-directory'})
        with self.assertRaisesRegex(Conflict,'directory replaced'):
            with shared_read_boundary(self.s):
                track_artifact(self.s,key)
                folder=self.s.root/'blobs';folder.rename(self.s.root/'old-blobs');folder.symlink_to(self.s.root/'old-blobs',target_is_directory=True)
                checkpoint(self.s)

    def test_external_connection_commit_rejects_old_read_transaction(self):
        with self.assertRaisesRegex(Conflict,'outside phase'):
            with shared_read_boundary(self.s):
                self.s.db.execute('BEGIN');self.read()
                other=sqlite3.connect(self.s.root/'runtime.sqlite');self.addCleanup(other.close)
                other.execute('UPDATE pf04_probe SET value=value+1');other.commit()
                checkpoint(self.s)
        self.s.db.execute('ROLLBACK')
    def test_true_child_process_commit_invalidates(self):
        with self.assertRaisesRegex(Conflict,'outside phase'):
            with shared_read_boundary(self.s):
                self.read()
                subprocess.run([sys.executable,'-c','import sqlite3,sys; d=sqlite3.connect(sys.argv[1]);d.execute("UPDATE pf04_probe SET value=value+1");d.commit();d.close()',str(self.s.root/'runtime.sqlite')],check=True,timeout=10)
                checkpoint(self.s)
    def test_database_replacement_rejects_open_old_handle(self):
        with self.assertRaisesRegex(Conflict,'replaced'):
            with shared_read_boundary(self.s):
                self.read();path=self.s.root/'runtime.sqlite';path.rename(self.s.root/'old.sqlite');path.write_bytes(b'replacement')
                checkpoint(self.s)
    def test_control_file_creation_or_change_invalidates(self):
        path=self.s.root/'control.sqlite';path.write_bytes(b'synthetic-control')
        with self.assertRaisesRegex(Conflict,'control changed'):
            with shared_read_boundary(self.s):
                self.read();path.write_bytes(b'changed-synthetic-control');checkpoint(self.s)
    def test_artifact_same_inode_write_and_symlink_rejected(self):
        key=self.s.artifact({'source':'original'});row=self.s.row('artifacts',key);path=self.s.root/'blobs'/row['storage_ref'];original=path.read_bytes()
        with self.assertRaisesRegex(Conflict,'artifact changed'):
            with shared_read_boundary(self.s):
                track_artifact(self.s,key);path.write_bytes(b'x'*len(original));checkpoint(self.s)
        path.write_bytes(original)
        with self.assertRaisesRegex(Conflict,'regular file'):
            with shared_read_boundary(self.s):
                track_artifact(self.s,key);path.unlink();path.symlink_to(self.s.root/'runtime.sqlite');checkpoint(self.s)
    def test_error_nested_and_copied_context_cannot_revive_closed_phase(self):
        with shared_read_boundary(self.s)as outer:
            self.read();saved=copy_context()
            with shared_read_boundary(self.s)as inner:
                self.read();self.assertIs(current_readset(self.s),inner)
            self.assertTrue(inner.closed);self.assertIs(current_readset(self.s),outer)
        self.assertIsNone(saved.run(current_readset,self.s));self.assertFalse(outer.cache)
        with self.assertRaises(RuntimeError):
            with shared_read_boundary(self.s)as failed:raise RuntimeError('fixture')
        self.assertTrue(failed.closed)
    def test_capacity_falls_back_and_actual_meter_only_charges_returned_rows(self):
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
        from digital_life.domain.tool_learning_resources import DIMENSIONS
        meter=PhysicalReadMeter({k:1000000 for k in DIMENSIONS},utc(30))
        with meter.installed(self.s),shared_read_boundary(self.s)as phase:
            phase.max_keys=1
            self.read();before=dict(meter.actual);self.read()
            self.assertEqual(meter.actual['scan'],before['scan']);self.assertEqual(meter.actual['bytes'],before['bytes'])
            self.read('missing');self.read('missing');self.assertEqual(self.selects(),3)
        self.assertLessEqual(len(phase.cache),1)

if __name__=='__main__':unittest.main()
