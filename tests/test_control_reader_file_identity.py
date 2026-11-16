"""Control-reader identity checks on disposable databases only."""
import errno
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError, Forbidden
from digital_life.infrastructure.persistence.sqlite_store import Store

class ControlReaderFileIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'control.sqlite'
        self.store=Store.__new__(Store);self.store.root=self.root;self.store.instance_id='instance'
        self.addCleanup(self.close_reader)
    def close_reader(self):
        reader=getattr(self.store,'_control_reader',None)
        if reader is not None:reader.close();self.store._control_reader=None
    def prepare(self,path=None,stopped=0,appid=1345335351):
        db=sqlite3.connect(str(path or self.path),isolation_level=None)
        db.execute('PRAGMA application_id='+str(appid))
        db.execute('CREATE TABLE instance_control_state(instance_ref TEXT,user_stopped INTEGER)')
        db.execute('INSERT INTO instance_control_state VALUES (?,?)',('instance',stopped))
        db.execute('CREATE TABLE process_runs(id TEXT,user_stopped INTEGER)')
        db.execute("INSERT INTO process_runs VALUES ('process',0)");db.close()
    def test_regular_file_one_lstat_per_call_and_same_identity_reuses_reader(self):
        self.prepare();original=Path.lstat;seen=[]
        def tracked(path,*a,**kw):seen.append(path);return original(path,*a,**kw)
        with patch.object(Path,'lstat',tracked):
            first=self.store.control_reader();second=self.store.control_reader()
        self.assertIs(first,second);self.assertEqual(seen,[self.path,self.path])
        info=self.path.lstat();self.assertEqual(self.store._control_reader_key,(info.st_dev,info.st_ino))
    def test_all_terminal_symlinks_rejected_with_original_contract(self):
        file=self.root/'target.sqlite';self.prepare(file)
        directory=self.root/'directory';directory.mkdir()
        for target in (file,directory,self.root/'missing'):
            with self.subTest(target=target):
                self.path.symlink_to(target)
                with self.assertRaisesRegex(ContractError,'^control database cannot be a symlink$'):
                    self.store.control_reader()
                self.path.unlink()
    def test_missing_non_directory_permission_and_loop_errors_not_swallowed(self):
        with self.assertRaises(FileNotFoundError):self.store.control_reader()
        blocked=self.root/'not-directory';blocked.write_text('file')
        self.store.root=blocked
        with self.assertRaises(NotADirectoryError):self.store.control_reader()
        self.store.root=self.root
        for code in (errno.EACCES,errno.ELOOP):
            with self.subTest(errno=code),patch.object(Path,'lstat',side_effect=OSError(code,'injected')):
                with self.assertRaises(OSError)as caught:self.store.control_reader()
                self.assertEqual(caught.exception.errno,code)
    def test_real_directory_retains_sqlite_open_failure(self):
        self.path.mkdir()
        with self.assertRaises(sqlite3.OperationalError):self.store.control_reader()
    def test_inode_replacement_reopens_and_invalid_identity_still_rejected(self):
        self.prepare();first=self.store.control_reader();before=self.store._control_reader_key
        replacement=self.root/'replacement.sqlite';self.prepare(replacement,stopped=1)
        os.replace(replacement,self.path)
        second=self.store.control_reader();self.assertIsNot(first,second)
        self.assertNotEqual(before,self.store._control_reader_key)
        self.assertEqual(second.execute('SELECT user_stopped FROM instance_control_state').fetchone()[0],1)
        with self.assertRaises(sqlite3.ProgrammingError):first.execute('SELECT 1')
        wrong=self.root/'wrong.sqlite';self.prepare(wrong,appid=123);os.replace(wrong,self.path)
        with self.assertRaisesRegex(ContractError,'invalid control database identity'):self.store.control_reader()
    def test_same_inode_reads_latest_stop_and_process_each_time(self):
        self.prepare();reader=self.store.control_reader();key=self.store._control_reader_key
        self.store.assert_execution_allowed()
        writer=sqlite3.connect(str(self.path),isolation_level=None)
        self.addCleanup(writer.close)
        writer.execute('UPDATE instance_control_state SET user_stopped=1')
        writer.execute('UPDATE process_runs SET user_stopped=1')
        self.assertIs(self.store.control_reader(),reader);self.assertEqual(self.store._control_reader_key,key)
        with self.assertRaisesRegex(Forbidden,'user stopped runtime'):self.store.assert_execution_allowed()
        self.assertEqual(self.store.control_reader().execute("SELECT user_stopped FROM process_runs WHERE id='process'").fetchone()[0],1)
        writer.execute('UPDATE instance_control_state SET user_stopped=0')
        self.store.assert_execution_allowed()

if __name__=='__main__':unittest.main()
