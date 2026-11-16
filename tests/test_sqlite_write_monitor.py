"""Managed write-footprint mechanics only, on new synthetic SQLite stores."""
import dataclasses
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from digital_life.infrastructure.persistence.sqlite_write_monitor import (
    ManagedConnection, callback_active, managed_connection_factory)
from digital_life.infrastructure.persistence import sqlite_write_monitor as monitor_module


class ManagedWriteMonitorTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:', factory=managed_connection_factory,
                                  isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE inputs(id TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE registry(id TEXT PRIMARY KEY);
            CREATE TABLE sources(id TEXT PRIMARY KEY, value TEXT);
            INSERT INTO sources VALUES('source', 'original');
            CREATE TRIGGER register_input AFTER INSERT ON inputs BEGIN
                INSERT INTO registry VALUES(NEW.id);
            END;
        ''')
        self._contract = None

    @property
    def contract(self):
        if self._contract is None: self._contract = self.bind()
        return self._contract

    @contract.setter
    def contract(self, value): self._contract = value

    def bind(self):
        return self.db.bind_insert('INSERT INTO inputs (id,value) VALUES (?,?)',
            'inputs', {('main', 'inputs'), ('main', 'registry')}, 'reviewed-schema')

    def insert(self, key='one'):
        self.db.execute('BEGIN')
        return self.db.certified_insert(self.contract, (key, 'body'), self)

    def test_trigger_footprint_receipt_is_bound_and_consumed_once(self):
        for _ in range(20): self.assertIs(self.bind(), self.contract)
        self.assertFalse(self.db.monitor_state()['can_certify'])
        self.db.execute('BEGIN')
        self.assertTrue(self.db.monitor_state()['can_certify'])
        cursor, receipt = self.db.certified_insert(self.contract, ('one', 'body'), self)
        self.assertFalse(self.db.monitor_state()['can_certify'])
        self.assertIs(cursor.connection, self.db)
        self.assertEqual(receipt.tables, frozenset((('main', 'inputs'), ('main', 'registry'))))
        self.assertIn((sqlite3.SQLITE_INSERT, 'main', 'registry', 'register_input'), receipt.footprint)
        self.assertIs(receipt.context_token, self)
        self.assertTrue(self.db.receipt_current(receipt))
        self.assertTrue(self.db.accept_receipt(receipt))
        self.assertFalse(self.db.accept_receipt(receipt))
        self.db.execute('SELECT * FROM sources').fetchall()
        self.assertTrue(self.db.receipt_current(receipt))
        self.db.execute('COMMIT')
        self.assertTrue(self.db.committed_receipt(receipt))
        self.db.execute('BEGIN')
        self.assertFalse(self.db.committed_receipt(receipt))
        self.db.rollback()

    def test_native_base_execute_cannot_bypass_composition(self):
        self.assertIsInstance(self.db, ManagedConnection)
        self.assertFalse(hasattr(self.db, 'actual'))
        self.assertFalse(hasattr(self.db.cursor(), 'actual'))
        with self.assertRaises(TypeError):
            sqlite3.Connection.execute(self.db, 'SELECT 1')

    def test_repeated_statement_preparation_keeps_real_trigger_footprints(self):
        footprints = []
        for key in ('one', 'two', 'three'):
            _, receipt = self.insert(key)
            self.assertIsNotNone(receipt)
            footprints.append(receipt.footprint)
            self.assertTrue(self.db.accept_receipt(receipt))
            self.db.commit()
            self.assertTrue(self.db.committed_receipt(receipt))
        self.assertEqual(footprints, [footprints[0]] * 3)

    def test_cursor_execution_is_managed_and_extra_write_invalidates(self):
        _, receipt = self.insert()
        self.assertTrue(self.db.accept_receipt(receipt))
        cursor = self.db.cursor()
        self.assertIs(cursor.connection, self.db)
        cursor.execute("UPDATE sources SET value='changed' WHERE id='source'")
        self.assertFalse(self.db.receipt_current(receipt))
        self.db.commit()
        self.assertFalse(self.db.committed_receipt(receipt))

    def test_trigger_source_update_never_receives_insert_certificate(self):
        other = sqlite3.connect(':memory:', factory=managed_connection_factory, isolation_level=None)
        self.addCleanup(other.close)
        other.executescript('''CREATE TABLE inputs(id TEXT,value TEXT);
            CREATE TABLE registry(id TEXT); CREATE TABLE sources(value TEXT);
            INSERT INTO sources VALUES('original');
            CREATE TRIGGER bad AFTER INSERT ON inputs BEGIN UPDATE sources SET value='changed'; END;''')
        contract = other.bind_insert(self.contract.sql, 'inputs',
            {('main', 'inputs'), ('main', 'registry')}, 'reviewed-other-schema')
        other.execute('BEGIN')
        _, receipt = other.certified_insert(contract, ('one', 'body'), self)
        self.assertIsNone(receipt)
        self.assertEqual(other.execute('SELECT value FROM sources').fetchone()[0], 'changed')

    def test_schema_change_after_binding_disables_proof_without_suppressing_sql(self):
        self.contract
        self.db.execute('CREATE TRIGGER extra AFTER INSERT ON inputs BEGIN SELECT 1; END')
        _, receipt = self.insert()
        self.assertIsNone(receipt)
        self.assertEqual(self.db.execute('SELECT id FROM inputs').fetchone()[0], 'one')
        with self.assertRaises(ValueError): self.bind()

    def test_udf_clock_read_only_is_not_authenticated_by_function_name(self):
        clock = sqlite3.connect(':memory:')
        self.addCleanup(clock.close)
        seen = []
        def clock_function(value):
            seen.append(callback_active())
            return clock.execute('SELECT upper(?)', (value,)).fetchone()[0]
        self.db.create_function('unknown_clock', 1, clock_function)
        self.db.execute('CREATE TRIGGER udf AFTER INSERT ON inputs BEGIN SELECT unknown_clock(NEW.value); END')
        self.contract = self.bind()
        _, receipt = self.insert()
        self.assertIsNotNone(receipt)
        self.assertEqual(seen, [True])
        self.assertFalse(callback_active())

    def test_udf_reentrant_cursor_write_is_recorded_and_not_certified(self):
        seen = []
        def function(value):
            seen.append(callback_active())
            self.db.cursor().connection.execute("UPDATE sources SET value='changed'")
            return value
        self.db.create_function('effect', 1, function)
        self.db.execute('CREATE TRIGGER udf AFTER INSERT ON inputs BEGIN SELECT effect(NEW.value); END')
        self.contract = self.bind()
        _, receipt = self.insert()
        self.assertIsNone(receipt)
        self.assertEqual(seen, [True])
        self.assertEqual(self.db.execute('SELECT value FROM sources').fetchone()[0], 'changed')

    def test_udf_exception_keeps_original_business_error_and_no_commit_proof(self):
        def broken(value): raise ValueError('synthetic callback failure')
        self.db.create_function('broken', 1, broken)
        self.db.execute('CREATE TRIGGER udf AFTER INSERT ON inputs BEGIN SELECT broken(NEW.value); END')
        self.contract = self.bind()
        self.db.execute('BEGIN')
        with self.assertRaises(sqlite3.OperationalError):
            self.db.certified_insert(self.contract, ('one', 'body'), self)
        self.assertTrue(self.db.monitor_state()['tainted'])
        self.assertFalse(callback_active())

    def test_foreign_authorizer_and_trace_never_issue_receipts(self):
        for setter, callback in ((self.db.set_authorizer, lambda *a: sqlite3.SQLITE_OK),
                                 (self.db.set_trace_callback, lambda *a: None)):
            setter(callback)
            self.db.execute('BEGIN')
            self.assertFalse(self.db.monitor_state()['can_certify'])
            self.db.rollback()
            _, receipt = self.insert(str(id(setter)))
            self.assertIsNone(receipt)
            self.db.rollback()
            setter(None)

    def test_progress_callback_is_scoped_and_abort_never_certifies(self):
        seen = []
        def progress(): seen.append(callback_active()); return 0
        self.db._install_meter_progress_handler(progress, 1)
        _, receipt = self.insert()
        self.assertIsNotNone(receipt)
        self.assertTrue(seen and all(seen))
        self.assertTrue(self.db.accept_receipt(receipt))
        self.db.commit()
        self.assertTrue(self.db.committed_receipt(receipt))
        self.db.set_progress_handler(lambda: 1, 1)
        with self.assertRaises(sqlite3.OperationalError): self.db.execute('BEGIN')
        self.assertFalse(callback_active())

    def test_unknown_row_factory_receives_managed_cursor_and_blocks_proof(self):
        seen = []
        def factory(cursor, row):
            seen.append((cursor.connection is self.db, callback_active()))
            return row
        self.db.row_factory = factory
        self.db.execute('SELECT 1').fetchone()
        _, receipt = self.insert()
        self.assertIsNone(receipt)
        self.assertEqual(seen, [(True, True)])

    def test_global_adapter_keeps_parameterized_semantics_and_blocks_receipt(self):
        key = (str, sqlite3.PrepareProtocol)
        prior = sqlite3.adapters.get(key)
        try:
            sqlite3.register_adapter(str, lambda value: value + '-adapted')
            _, receipt = self.insert()
            self.assertIsNone(receipt)
        finally:
            if prior is None: sqlite3.adapters.pop(key, None)
            else: sqlite3.adapters[key] = prior
        self.assertEqual(self.db.execute('SELECT id,value FROM inputs').fetchone()[:],
                         ('one-adapted', 'body-adapted'))

    def test_adapter_reentry_uses_callback_scope_and_invalidates_ledger(self):
        seen = []
        owner = self
        class Value:
            def __conform__(self, protocol):
                seen.append(callback_active())
                owner.db.execute("UPDATE sources SET value='adapted'")
                return 'adapted'
        self.db.execute('BEGIN')
        _, receipt = self.db.certified_insert(self.contract, (Value(), 'body'), self)
        self.assertIsNone(receipt)
        self.assertEqual(seen, [True])
        self.assertTrue(self.db.monitor_state()['tainted'])

    def test_lazy_udf_during_fetch_invalidates_already_accepted_receipt(self):
        self.db.executescript('CREATE TABLE seq(n INTEGER); INSERT INTO seq VALUES(1),(2);')
        def effect(n):
            if n == 2: self.db.execute("UPDATE sources SET value='lazy'")
            return n
        self.db.create_function('lazy', 1, effect)
        self.contract = self.bind()
        cursor = self.db.execute('SELECT lazy(n) FROM seq')
        _, receipt = self.insert()
        self.assertTrue(self.db.accept_receipt(receipt))
        cursor.fetchall()
        self.assertFalse(self.db.receipt_current(receipt))
        self.db.commit()
        self.assertFalse(self.db.committed_receipt(receipt))

    def test_rollback_savepoint_and_unaccepted_receipt_never_commit_proof(self):
        _, receipt = self.insert()
        self.assertTrue(self.db.accept_receipt(receipt))
        self.db.execute('SAVEPOINT nested')
        self.db.execute('ROLLBACK TO nested')
        self.db.execute('RELEASE nested')
        self.db.commit()
        self.assertFalse(self.db.committed_receipt(receipt))
        _, receipt = self.insert('two')
        self.db.rollback()
        self.assertFalse(self.db.committed_receipt(receipt))
        _, receipt = self.insert('three')
        self.db.commit()
        self.assertFalse(self.db.committed_receipt(receipt))

    def test_foreign_and_copied_receipts_do_not_validate(self):
        _, receipt = self.insert()
        self.assertFalse(self.db.receipt_current(dataclasses.replace(receipt)))
        self.assertFalse(self.db.receipt_current(None))
        self.assertFalse(self.db.accept_receipt({}))

    def test_opaque_ports_and_configuration_change_invalidate_current_receipt(self):
        _, receipt = self.insert()
        self.assertTrue(self.db.accept_receipt(receipt))
        self.db.set_trace_callback(lambda sql: None)
        self.assertFalse(self.db.receipt_current(receipt))
        with self.assertRaises(sqlite3.ProgrammingError):
            self.db.blobopen('inputs', 'value', 1)
        self.assertFalse(self.db.receipt_current(receipt))

    def test_executescript_and_executemany_are_not_hidden_write_paths(self):
        _, receipt = self.insert()
        self.assertTrue(self.db.accept_receipt(receipt))
        self.db.cursor().executemany('UPDATE sources SET value=?', [('many',)])
        self.assertFalse(self.db.receipt_current(receipt))
        self.db.execute('COMMIT')
        self.assertFalse(self.db.committed_receipt(receipt))
        self.db.executescript("UPDATE sources SET value='script';")
        self.assertEqual(self.db.execute('SELECT value FROM sources').fetchone()[0], 'script')

    def test_failure_retains_sqlite_exception_and_database_constraints(self):
        _, receipt = self.insert()
        self.db.commit()
        self.db.execute('BEGIN')
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.certified_insert(self.contract, ('one', 'different'), self)
        self.assertTrue(self.db.monitor_state()['tainted'])
        self.assertFalse(self.db.committed_receipt(receipt))

    def test_root_savepoint_is_not_a_certifiable_outer_transaction(self):
        self.db.execute('SAVEPOINT root')
        _, receipt = self.db.certified_insert(self.contract, ('one', 'body'), self)
        self.assertIsNone(receipt)
        self.db.execute('RELEASE root')

    def test_trace_omits_only_own_technical_marker(self):
        statements = []
        self.db.set_trace_callback(statements.append)
        self.db.execute('SELECT ?', ('synthetic',)).fetchone()
        self.db.cursor().execute('/*original user comment*/ SELECT 2').fetchone()
        self.assertEqual(statements, ["SELECT 'synthetic'", '/*original user comment*/ SELECT 2'])

    def test_unknown_text_and_cursor_factories_do_not_certify(self):
        self.db.text_factory = lambda value: value.decode('utf-8')
        _, receipt = self.insert()
        self.assertIsNone(receipt)
        self.db.rollback()
        self.db.text_factory = str
        class Cursor(sqlite3.Cursor): pass
        with self.assertRaises(sqlite3.ProgrammingError): self.db.cursor(factory=Cursor)
        _, receipt = self.insert('two')
        self.assertIsNone(receipt)

    def test_callback_configuration_change_is_not_hidden(self):
        def function(value):
            self.db.create_function('new_function', 0, lambda: 1)
            return value
        self.db.create_function('configure', 1, function)
        self.db.execute('CREATE TRIGGER udf AFTER INSERT ON inputs BEGIN SELECT configure(NEW.value); END')
        self.contract = self.bind()
        _, receipt = self.insert()
        self.assertIsNone(receipt)
        self.assertEqual(self.db.execute('SELECT new_function()').fetchone()[0], 1)

    def test_transient_adapter_inside_callback_is_cache_suspended_and_observed(self):
        seen = []
        key = (str, sqlite3.PrepareProtocol)
        prior = sqlite3.adapters.get(key)
        def function(value):
            try:
                sqlite3.register_adapter(str, lambda item: item + '-temporary')
                seen.append(callback_active())
                seen.append(self.db.execute('SELECT ?', ('inside',)).fetchone()[0])
            finally:
                if prior is None: sqlite3.adapters.pop(key, None)
                else: sqlite3.adapters[key] = prior
            return value
        self.db.create_function('temporary_adapter', 1, function)
        self.db.execute('CREATE TRIGGER udf AFTER INSERT ON inputs BEGIN SELECT temporary_adapter(NEW.value); END')
        self.contract = self.bind()
        _, receipt = self.insert()
        self.assertIsNone(receipt)
        self.assertEqual(seen, [True, 'inside-temporary'])
        self.assertFalse(callback_active())

    def test_global_registry_change_is_reflected_by_no_sql_monitor_state(self):
        _, receipt = self.insert()
        self.assertTrue(self.db.accept_receipt(receipt))
        before = self.db.monitor_state()['configuration']
        class Value: pass
        key = (Value, sqlite3.PrepareProtocol)
        try:
            sqlite3.register_adapter(Value, lambda value: 'value')
            self.assertGreater(self.db.monitor_state()['configuration'], before)
            self.assertFalse(self.db.receipt_current(receipt))
        finally: sqlite3.adapters.pop(key, None)

    def test_receipt_does_not_claim_control_file_or_foreign_database_purity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            control = sqlite3.connect(str(path/'control.sqlite'), isolation_level=None)
            try:
                control.execute('CREATE TABLE state(value TEXT)')
                control.execute("INSERT INTO state VALUES('before')")
                original = path/'original';original.write_text('before')
                def function(value):
                    control.execute("UPDATE state SET value='after'")
                    original.write_text('after')
                    return value
                self.db.create_function('external_effect', 1, function)
                self.db.execute('CREATE TRIGGER udf AFTER INSERT ON inputs BEGIN SELECT external_effect(NEW.value); END')
                self.contract = self.bind()
                _, receipt = self.insert()
                # Deliberately only a same-connection table-footprint witness.
                # The readset MUST reject using it after its external probes.
                self.assertIsNotNone(receipt)
                self.assertEqual(receipt.tables, frozenset((('main','inputs'),('main','registry'))))
                self.assertEqual(control.execute('SELECT value FROM state').fetchone()[0], 'after')
                self.assertEqual(original.read_text(), 'after')
            finally: control.close()

    def test_backup_and_blob_ports_invalidate_existing_receipt(self):
        _, receipt = self.insert()
        self.assertTrue(self.db.accept_receipt(receipt))
        with self.assertRaises(sqlite3.ProgrammingError):
            self.db.blobopen('inputs', 'value', 1)
        self.assertFalse(self.db.receipt_current(receipt))
        self.db.rollback()
        self.db.execute("INSERT INTO inputs VALUES('kept','body')")
        target = sqlite3.connect(':memory:')
        try:
            progress = []
            self.db.backup(target, progress=lambda *args: progress.append(callback_active()))
            self.assertTrue(progress and all(progress))
            self.assertEqual(target.execute('SELECT id FROM inputs').fetchone()[0], 'kept')
        finally: target.close()

    def test_dml_rowcount_lastrowid_and_implicit_transactions_match_native(self):
        for isolation in (None, ''):
            native = sqlite3.connect(':memory:', isolation_level=isolation)
            managed = sqlite3.connect(':memory:', factory=managed_connection_factory,
                                      isolation_level=isolation)
            try:
                for db in (native, managed): db.execute('CREATE TABLE t(id INTEGER PRIMARY KEY,value TEXT)')
                pairs = [
                    ('execute', 'INSERT INTO t (value) VALUES (?)', ('one',)),
                    ('execute', 'INSERT INTO t (value) VALUES (?); -- original tail', ('two',)),
                    ('execute', 'UPDATE t SET value=? WHERE id=?', ('updated', 1)),
                    ('execute', 'DELETE FROM t WHERE id=?', (900,)),
                    ('executemany', 'INSERT INTO t (value) VALUES (?)', [('three',), ('four',)]),
                    ('execute', 'DELETE FROM t WHERE id=?', (2,)),
                ]
                for method, sql, parameters in pairs:
                    before = getattr(native, method)(sql, parameters)
                    after = getattr(managed, method)(sql, parameters)
                    self.assertEqual((after.rowcount, after.lastrowid, managed.in_transaction, managed.total_changes),
                                     (before.rowcount, before.lastrowid, native.in_transaction, native.total_changes))
                left = native.cursor();right = managed.cursor()
                for method, sql, parameters in pairs:
                    before = getattr(left, method)(sql, parameters)
                    after = getattr(right, method)(sql, parameters)
                    self.assertEqual((after.rowcount, after.lastrowid, managed.in_transaction, managed.total_changes),
                                     (before.rowcount, before.lastrowid, native.in_transaction, native.total_changes))
                native.commit();managed.commit()
                self.assertEqual(native.execute('SELECT * FROM t ORDER BY id').fetchall(),
                                 managed.execute('SELECT * FROM t ORDER BY id').fetchall())
            finally: native.close();managed.close()

    def test_suffix_marker_reprepares_semicolon_and_original_line_comment(self):
        for tail in (';', ' -- original line comment'):
            before = self.db.monitor_state()['write_sequence']
            cursor = self.db.cursor()
            for index in range(3):
                sql = 'INSERT INTO inputs (id,value) VALUES (?,?)' + tail
                cursor.execute(sql, (tail+str(index), 'body'))
                self.assertEqual(cursor.rowcount, 1)
            self.assertEqual(self.db.monitor_state()['write_sequence'] - before, 3)

    def test_suffix_trace_matches_native_for_semicolon_and_line_comment(self):
        native = sqlite3.connect(':memory:', isolation_level=None)
        try:
            left=[];right=[]
            native.set_trace_callback(left.append);self.db.set_trace_callback(right.append)
            for sql in ('SELECT ?', 'SELECT ?;', 'SELECT ? -- original tail',
                        '/* original prefix */ SELECT ?; -- original tail'):
                native.execute(sql, ('literal',)).fetchone()
                self.db.execute(sql, ('literal',)).fetchone()
            self.assertEqual(left, right)
        finally: native.close()

    def test_public_unknown_progress_blocks_new_receipt_but_sql_is_unchanged(self):
        seen = []
        self.db.set_progress_handler(lambda: (seen.append(callback_active()), 0)[1], 1)
        self.db.execute('BEGIN')
        self.assertFalse(self.db.monitor_state()['can_certify'])
        _, receipt = self.db.certified_insert(self.contract, ('one', 'body'), self)
        self.assertIsNone(receipt)
        self.db.commit()
        self.assertTrue(seen and all(seen))
        self.assertEqual(self.db.execute('SELECT id FROM inputs').fetchone()[0], 'one')
        self.db.set_progress_handler(None, 0)
        _, receipt = self.insert('two')
        self.assertIsNotNone(receipt)

    def test_private_meter_progress_reentrant_write_does_not_certify(self):
        armed = [False]
        seen = []
        def progress():
            if armed[0]:
                armed[0] = False
                seen.append(callback_active())
                self.db.execute("UPDATE sources SET value='progress-write'")
            return 0
        self.db._install_meter_progress_handler(progress, 1)
        self.db.execute('BEGIN');armed[0] = True
        _, receipt = self.db.certified_insert(self.contract, ('one', 'body'), self)
        self.assertIsNone(receipt)
        self.assertEqual(seen, [True])
        self.assertEqual(self.db.execute('SELECT value FROM sources').fetchone()[0], 'progress-write')

    def test_normal_savepoint_and_release_do_not_advance_material_configuration(self):
        self.db.execute('BEGIN IMMEDIATE')
        before = self.db.monitor_state()
        cursor = self.db.cursor()
        for execute in (self.db.execute, cursor.execute):
            execute('SAVEPOINT outer_read')
            execute('SAVEPOINT inner_read')
            execute('RELEASE inner_read')
            execute('RELEASE outer_read')
        after = self.db.monitor_state()
        for key in ('configuration', 'schema_epoch', 'write_sequence', 'total_changes'):
            self.assertEqual(after[key], before[key])
        self.assertTrue(after['tainted'])
        self.assertFalse(after['can_certify'])

    def test_normal_savepoint_still_invalidates_accepted_transaction_receipt(self):
        _, receipt = self.insert()
        self.assertTrue(self.db.accept_receipt(receipt))
        before = self.db.monitor_state()['configuration']
        self.db.execute('SAVEPOINT read_scope')
        self.db.execute('RELEASE read_scope')
        self.assertEqual(self.db.monitor_state()['configuration'], before)
        self.assertFalse(self.db.receipt_current(receipt))
        self.db.commit()
        self.assertFalse(self.db.committed_receipt(receipt))

    def test_savepoint_attempt_inside_protected_insert_window_never_certifies(self):
        attempts = []
        def function(value):
            try:
                self.db.execute('SAVEPOINT callback_scope')
                self.db.execute('RELEASE callback_scope')
            except sqlite3.OperationalError as error:
                # SQLite may forbid opening a savepoint in an active statement.
                attempts.append(type(error).__name__)
            else: attempts.append('executed')
            return value
        self.db.create_function('savepoint_effect', 1, function)
        self.db.execute('CREATE TRIGGER udf AFTER INSERT ON inputs BEGIN SELECT savepoint_effect(NEW.value); END')
        self.contract = self.bind()
        _, receipt = self.insert()
        self.assertIsNone(receipt)
        self.assertEqual(len(attempts), 1)
        self.assertTrue(self.db.monitor_state()['tainted'])

    def test_rollback_to_savepoint_still_advances_configuration_and_restores_rows(self):
        self.db.execute('BEGIN IMMEDIATE')
        self.db.execute('SAVEPOINT change_scope')
        self.db.execute("UPDATE sources SET value='temporary'")
        before = self.db.monitor_state()
        self.db.execute('ROLLBACK TO change_scope')
        after = self.db.monitor_state()
        self.assertGreater(after['configuration'], before['configuration'])
        for key in ('schema_epoch', 'write_sequence', 'total_changes'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(self.db.execute('SELECT value FROM sources').fetchone()[0], 'original')
        self.db.execute('RELEASE change_scope')
        self.assertEqual(self.db.monitor_state()['configuration'], after['configuration'])
        self.assertFalse(self.db.monitor_state()['can_certify'])

    def test_savepoint_dml_rowcount_lastrowid_and_results_match_native(self):
        native = sqlite3.connect(':memory:', isolation_level=None)
        managed = sqlite3.connect(':memory:', factory=managed_connection_factory, isolation_level=None)
        try:
            for db in (native, managed):
                db.execute('CREATE TABLE t(id INTEGER PRIMARY KEY,value TEXT)')
                db.execute("INSERT INTO t VALUES(1,'original')")
            commands = ('BEGIN IMMEDIATE', 'SAVEPOINT change_scope',
                        "UPDATE t SET value='temporary' WHERE id=1", 'ROLLBACK TO change_scope',
                        'RELEASE change_scope', 'SAVEPOINT keep_scope',
                        "UPDATE t SET value='kept' WHERE id=1", 'RELEASE keep_scope', 'COMMIT')
            for sql in commands:
                left = native.execute(sql);right = managed.execute(sql)
                self.assertEqual((left.rowcount, left.lastrowid, native.in_transaction, native.total_changes),
                                 (right.rowcount, right.lastrowid, managed.in_transaction, managed.total_changes))
            self.assertEqual(native.execute('SELECT * FROM t').fetchall(),
                             managed.execute('SELECT * FROM t').fetchall())
        finally: native.close();managed.close()

    def test_query_only_read_is_material_and_schema_generation_neutral(self):
        self.contract
        before = self.db.monitor_state()
        for sql in ('PRAGMA query_only', 'PRAGMA QUERY_ONLY'):
            self.assertEqual(self.db.execute(sql).fetchone()[0], 0)
        after = self.db.monitor_state()
        for key in ('configuration', 'schema_epoch', 'write_sequence', 'total_changes'):
            self.assertEqual(after[key], before[key])

    def test_query_only_round_trip_keeps_same_schema_contract_for_new_receipt(self):
        contract = self.contract
        _, first = self.insert()
        self.assertTrue(self.db.accept_receipt(first));self.db.commit()
        self.assertTrue(self.db.committed_receipt(first))
        before = self.db.monitor_state()
        self.db.execute('PRAGMA query_only=ON')
        on = self.db.monitor_state()
        self.assertEqual(self.db.execute('PRAGMA query_only').fetchone()[0], 1)
        self.db.execute('PRAGMA query_only=OFF')
        after = self.db.monitor_state()
        self.assertEqual(after['schema_epoch'], before['schema_epoch'])
        self.assertGreater(on['configuration'], before['configuration'])
        self.assertGreater(after['configuration'], on['configuration'])
        self.assertFalse(self.db.committed_receipt(first))
        self.assertIs(self.bind(), contract)
        _, second = self.insert('two')
        self.assertIsNotNone(second)
        self.assertTrue(self.db.accept_receipt(second));self.db.commit()
        self.assertTrue(self.db.committed_receipt(second))

    def test_query_only_native_read_only_error_and_data_semantics_are_preserved(self):
        native = sqlite3.connect(':memory:', isolation_level=None)
        try:
            native.execute('CREATE TABLE inputs(id TEXT PRIMARY KEY,value TEXT)')
            self.contract
            for db in (native, self.db):
                db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            errors = []
            for call in (lambda: native.execute(self.contract.sql, ('one','body')),
                         lambda: self.db.certified_insert(self.contract, ('one','body'), self)):
                with self.assertRaises(sqlite3.OperationalError) as caught: call()
                errors.append(str(caught.exception))
            self.assertEqual(errors[0], errors[1])
            self.assertEqual(native.in_transaction, self.db.in_transaction)
            for db in (native, self.db):
                db.rollback();db.execute('PRAGMA query_only=OFF')
                db.execute('INSERT INTO inputs (id,value) VALUES (?,?)', ('after','body'))
            self.assertEqual(native.execute('SELECT * FROM inputs').fetchall(),
                             [tuple(row) for row in self.db.execute('SELECT * FROM inputs')])
        finally: native.close()

    def test_query_only_setting_still_taints_active_receipt_without_schema_change(self):
        _, receipt = self.insert()
        self.assertTrue(self.db.accept_receipt(receipt))
        before = self.db.monitor_state()
        self.db.execute('PRAGMA query_only=ON')
        after = self.db.monitor_state()
        self.assertEqual(after['schema_epoch'], before['schema_epoch'])
        self.assertGreater(after['configuration'], before['configuration'])
        self.assertTrue(after['tainted'])
        self.assertFalse(self.db.receipt_current(receipt))

    def test_true_schema_ddl_and_schema_pragmas_still_end_approval(self):
        for sql in ('CREATE TABLE extra(id TEXT)', 'PRAGMA writable_schema=ON',
                    'PRAGMA schema_version=99', 'PRAGMA user_version=99',
                    'PRAGMA unknown_mode=ON'):
            db = sqlite3.connect(':memory:', factory=managed_connection_factory, isolation_level=None)
            try:
                db.execute('CREATE TABLE inputs(id TEXT)')
                statement = 'INSERT INTO inputs (id) VALUES (?)'
                db.bind_insert(statement, 'inputs', {('main','inputs')}, 'reviewed')
                before = db.monitor_state()['schema_epoch']
                db.execute(sql)
                self.assertGreater(db.monitor_state()['schema_epoch'], before)
                with self.assertRaises(ValueError):
                    db.bind_insert(statement, 'inputs', {('main','inputs')}, 'reviewed')
            finally: db.close()

    def test_insert_action_witness_tracks_identity_and_native_clock_callback(self):
        seen = []
        self.db.create_function('clock_report', 1, lambda value: (seen.append(callback_active()), value)[1])
        self.db.execute('CREATE TRIGGER clock BEFORE INSERT ON inputs BEGIN SELECT clock_report(NEW.value); END')
        self.contract = self.bind()
        _, receipt = self.insert()
        # Necessary INSERT-action witness only; actual schema approval remains
        # the caller's separate obligation, not inferred from this True.
        self.assertTrue(self.db.insert_only_receipt(receipt))
        self.assertFalse(self.db.insert_only_receipt(dataclasses.replace(receipt)))
        self.assertEqual(seen, [True])
        self.assertTrue(self.db.accept_receipt(receipt));self.db.commit()
        self.assertTrue(self.db.insert_only_receipt(receipt, committed=True))
        self.assertFalse(self.db.insert_only_receipt(receipt))
        self.db.execute('BEGIN')
        self.assertFalse(self.db.insert_only_receipt(receipt, committed=True))

    def test_collation_removal_keeps_strong_opaque_history_but_ordinary_receipt_works(self):
        self.db.create_collation('custom_order', lambda left,right: (left > right) - (left < right))
        self.db.create_collation('custom_order', None)
        _, receipt = self.insert()
        self.assertTrue(self.db.receipt_current(receipt))
        self.assertFalse(self.db.insert_only_receipt(receipt))
        self.assertTrue(self.db.accept_receipt(receipt));self.db.commit()
        self.assertTrue(self.db.committed_receipt(receipt))
        self.assertFalse(self.db.insert_only_receipt(receipt, committed=True))

    def test_binary_collation_override_has_no_strong_witness(self):
        self.db.create_collation('BINARY', lambda left,right: (left > right) - (left < right))
        _, receipt = self.insert()
        self.assertTrue(self.db.receipt_current(receipt))
        self.assertFalse(self.db.insert_only_receipt(receipt))

    def test_native_adapter_history_has_no_strong_witness(self):
        key = (str, sqlite3.PrepareProtocol);prior = sqlite3.adapters.get(key)
        try:
            sqlite3.register_adapter(str, lambda value: value)
            self.db.monitor_state()
        finally:
            if prior is None: sqlite3.adapters.pop(key, None)
            else: sqlite3.adapters[key] = prior
        _, receipt = self.insert()
        self.assertTrue(self.db.receipt_current(receipt))
        self.assertFalse(self.db.insert_only_receipt(receipt))

    def test_factory_history_has_no_strong_witness(self):
        for name, unknown, normal in (
                ('row_factory', lambda cursor,row: row, sqlite3.Row),
                ('text_factory', lambda value: value.decode('utf-8'), str)):
            db = sqlite3.connect(':memory:', factory=managed_connection_factory, isolation_level=None)
            try:
                db.execute('CREATE TABLE inputs(id TEXT)')
                contract = db.bind_insert('INSERT INTO inputs (id) VALUES (?)', 'inputs', {('main','inputs')}, 'reviewed')
                setattr(db, name, unknown);setattr(db, name, normal)
                db.execute('BEGIN')
                _, receipt = db.certified_insert(contract, ('one',), self)
                self.assertTrue(db.receipt_current(receipt))
                self.assertFalse(db.insert_only_receipt(receipt))
            finally: db.close()

    def test_replace_syntax_and_new_unknown_trigger_cannot_claim_strong_witness(self):
        for sql in ('REPLACE INTO inputs (id,value) VALUES (?,?)',
                    'INSERT OR REPLACE INTO inputs (id,value) VALUES (?,?)'):
            with self.assertRaises(ValueError):
                self.db.bind_insert(sql, 'inputs', {('main','inputs')}, 'reviewed-schema')
        self.db.execute("INSERT INTO registry VALUES('other')")
        self.contract
        self.db.execute("CREATE TRIGGER unknown AFTER INSERT ON inputs BEGIN INSERT OR REPLACE INTO registry VALUES('other'); END")
        _, receipt = self.insert()
        self.assertIsNone(receipt)
        self.assertFalse(self.db.insert_only_receipt(receipt))

    def test_update_and_delete_trigger_footprints_have_no_strong_witness(self):
        for mutation in ("UPDATE sources SET value='changed'", 'DELETE FROM sources'):
            db = sqlite3.connect(':memory:', factory=managed_connection_factory, isolation_level=None)
            try:
                db.executescript('CREATE TABLE inputs(id TEXT);CREATE TABLE sources(value TEXT);INSERT INTO sources VALUES(\'original\');'
                    +'CREATE TRIGGER effect AFTER INSERT ON inputs BEGIN '+mutation+'; END;')
                contract = db.bind_insert('INSERT INTO inputs (id) VALUES (?)', 'inputs',
                    {('main','inputs'),('main','sources')}, 'separately-reviewed')
                db.execute('BEGIN');_, receipt = db.certified_insert(contract, ('one',), self)
                self.assertIsNone(receipt)
                self.assertFalse(db.insert_only_receipt(receipt))
            finally: db.close()

    def test_shared_adapter_signature_matches_original_identity_classification(self):
        original = dict(sqlite3.adapters)
        class Custom: pass
        class StringSubclass(str): pass
        native = (str, int, float, bytes, bytearray, memoryview, bool, type(None))
        try:
            for kind in (Custom, StringSubclass) + native:
                sqlite3.adapters.clear();sqlite3.adapters.update(original)
                callback = lambda value: value
                sqlite3.adapters[(kind, sqlite3.PrepareProtocol)] = callback
                # The old classification inspected every type regardless of
                # protocol identity; this conservative scope is unchanged.
                alternate_protocol = object()
                sqlite3.adapters[(kind, alternate_protocol)] = callback
                expected = any(any(key[0] is item for item in native) for key in list(sqlite3.adapters))
                signature = monitor_module._registry_signature()
                expected_signature = (tuple(sorted((id(k[0]), id(k[1]), id(v)) for k,v in list(sqlite3.adapters.items()))),
                    tuple(sorted((id(k), id(v)) for k,v in list(sqlite3.converters.items()))))
                self.assertEqual(signature, expected_signature)
                self.assertEqual(monitor_module._native_adapter_present(signature[0]), expected)
        finally:
            sqlite3.adapters.clear();sqlite3.adapters.update(original)

    def test_registry_refresh_observes_complete_maps_once_without_extra_adapter_scan(self):
        class ObservedDict(dict):
            def __init__(self, source): super().__init__(source);self.items_calls=0;self.iter_calls=0
            def items(self): self.items_calls += 1;return super().items()
            def __iter__(self): self.iter_calls += 1;return super().__iter__()
        adapters = ObservedDict(sqlite3.adapters);converters = ObservedDict(sqlite3.converters)
        with patch.object(sqlite3, 'adapters', adapters), patch.object(sqlite3, 'converters', converters):
            for _ in range(3): self.db._refresh_registry()
        self.assertEqual((adapters.items_calls, converters.items_calls), (3,3))
        self.assertEqual(adapters.iter_calls, 0)

    def test_registry_refresh_frequency_still_wraps_every_native_operation(self):
        with patch.object(monitor_module, '_registry_signature', wraps=monitor_module._registry_signature) as signature:
            cursor = self.db.execute('SELECT 1')
            self.assertEqual(signature.call_count, 2)
            cursor.fetchone()
            self.assertEqual(signature.call_count, 4)
            self.db.monitor_state()
            self.assertEqual(signature.call_count, 5)
            for _ in range(3): self.db._refresh_registry()
            self.assertEqual(signature.call_count, 8)

    def test_converter_identity_changes_and_native_opaque_history_remain_detected(self):
        adapters = dict(sqlite3.adapters);converters = dict(sqlite3.converters)
        try:
            before = self.db.monitor_state()['configuration']
            sqlite3.converters['TL_REFRESH_SYNTHETIC'] = lambda value: value
            first = self.db.monitor_state()['configuration']
            self.assertGreater(first, before)
            sqlite3.converters['TL_REFRESH_SYNTHETIC'] = lambda value: value
            second = self.db.monitor_state()['configuration']
            self.assertGreater(second, first)
            sqlite3.adapters[(str, sqlite3.PrepareProtocol)] = lambda value: value
            self.db.monitor_state()
            sqlite3.adapters.clear();sqlite3.adapters.update(adapters)
            sqlite3.converters.clear();sqlite3.converters.update(converters)
            _, receipt = self.insert()
            self.assertTrue(self.db.receipt_current(receipt))
            self.assertFalse(self.db.insert_only_receipt(receipt))
        finally:
            sqlite3.adapters.clear();sqlite3.adapters.update(adapters)
            sqlite3.converters.clear();sqlite3.converters.update(converters)

    def test_known_read_environment_does_not_depend_on_transaction_or_receipt(self):
        self.assertTrue(self.db.known_read_environment())
        self.db.execute('BEGIN')
        self.assertTrue(self.db.known_read_environment())
        _, receipt = self.db.certified_insert(self.contract, ('one','body'), self)
        self.assertTrue(self.db.known_read_environment())
        self.assertTrue(self.db.accept_receipt(receipt))
        self.assertTrue(self.db.known_read_environment())
        self.db.commit()
        self.assertTrue(self.db.known_read_environment())
        self.db.execute('BEGIN');self.db.execute('SAVEPOINT ordinary_read')
        self.assertTrue(self.db.monitor_state()['tainted'])
        self.assertTrue(self.db.known_read_environment())
        self.db.rollback()
        self.assertTrue(self.db.known_read_environment())

    def test_known_read_environment_rejects_each_existing_unknown_flag(self):
        def cursor_factory(db):
            class Cursor(sqlite3.Cursor): pass
            db.cursor(factory=Cursor)
        def removed_collation(db):
            db.create_collation('temporary_order', lambda left,right: 0)
            db.create_collation('temporary_order', None)
        changes = (
            lambda db: db.set_authorizer(lambda *args: sqlite3.SQLITE_OK),
            lambda db: db.set_trace_callback(lambda sql: None),
            lambda db: db.set_progress_handler(lambda: 0, 1000),
            lambda db: setattr(db,'row_factory',lambda cursor,row:row),
            lambda db: setattr(db,'text_factory',lambda value:value.decode('utf-8')),
            removed_collation, cursor_factory,
            lambda db: db.enable_load_extension(True),
        )
        for change in changes:
            db = sqlite3.connect(':memory:', factory=managed_connection_factory, isolation_level=None)
            try:
                self.assertTrue(db.known_read_environment())
                try: change(db)
                except (sqlite3.Error, AttributeError): pass
                self.assertFalse(db.known_read_environment())
            finally: db.close()

    def test_known_read_environment_rejects_sqlite_callbacks_but_allows_private_meter_outside(self):
        seen = []
        def read_environment(value):
            seen.append(self.db.known_read_environment())
            return value
        self.db.create_function('read_environment',1,read_environment)
        self.assertEqual(self.db.execute('SELECT read_environment(1)').fetchone()[0],1)
        self.assertEqual(seen,[False])
        seen.clear()
        self.db._install_meter_progress_handler(lambda:(seen.append(self.db.known_read_environment()),0)[1],1)
        self.assertTrue(self.db.known_read_environment())
        self.db.execute('SELECT 1').fetchone()
        self.assertTrue(seen and all(value is False for value in seen))
        self.assertTrue(self.db.known_read_environment())

    def test_known_read_environment_refreshes_native_adapter_history_without_sql(self):
        statements = []
        self.db.set_trace_callback(statements.append)
        for _ in range(5): self.assertFalse(self.db.known_read_environment())
        self.assertEqual(statements,[])
        self.db.set_trace_callback(None)
        self.assertTrue(self.db.known_read_environment())
        key = (str,sqlite3.PrepareProtocol);prior=sqlite3.adapters.get(key)
        try:
            sqlite3.register_adapter(str,lambda value:value)
            self.assertFalse(self.db.known_read_environment())
        finally:
            if prior is None:sqlite3.adapters.pop(key,None)
            else:sqlite3.adapters[key]=prior
        self.assertFalse(self.db.known_read_environment())


    def assert_observed_stamp_matches(self):
        stamp = self.db.observed_stamp()
        state = self.db.monitor_state()
        self.assertEqual(stamp, tuple(state[key] for key in
            ('configuration', 'schema_epoch', 'write_sequence', 'closed')))
        return stamp

    def test_observed_stamp_tracks_config_schema_write_and_close(self):
        initial = self.assert_observed_stamp_matches()
        self.db.execute('UPDATE sources SET value=?', ('changed',))
        written = self.assert_observed_stamp_matches()
        self.assertGreater(written[2], initial[2])
        self.db.set_trace_callback(lambda sql: None)
        configured = self.assert_observed_stamp_matches()
        self.assertGreater(configured[0], written[0])
        self.db.execute('CREATE TABLE stamp_schema(id)')
        schema = self.assert_observed_stamp_matches()
        self.assertGreater(schema[1], configured[1])
        self.db.close()
        self.assertTrue(self.assert_observed_stamp_matches()[3])

    def test_observed_stamp_refreshes_registry_and_executes_no_sql(self):
        statements = []
        self.db.set_trace_callback(statements.append)
        before = self.assert_observed_stamp_matches()
        key = (str, sqlite3.PrepareProtocol)
        prior = sqlite3.adapters.get(key)
        try:
            sqlite3.register_adapter(str, lambda value: value)
            after = self.assert_observed_stamp_matches()
            self.assertGreater(after[0], before[0])
        finally:
            if prior is None: sqlite3.adapters.pop(key, None)
            else: sqlite3.adapters[key] = prior
        self.assert_observed_stamp_matches()
        self.assertEqual(statements, [])

    def test_observed_material_revision_is_only_existing_fields(self):
        before = self.db.material_revision()
        key = (str, sqlite3.PrepareProtocol)
        prior = sqlite3.adapters.get(key)
        try:
            sqlite3.register_adapter(str, lambda value: value)
            self.assertEqual(self.db.observed_material_revision(), before)
            refreshed = self.db.material_revision()
            self.assertGreater(refreshed[0], before[0])
            self.assertEqual(self.db.observed_material_revision(), refreshed)
            self.db.set_trace_callback(lambda sql: None)
            self.assertGreater(self.db.observed_material_revision()[0], refreshed[0])
        finally:
            if prior is None: sqlite3.adapters.pop(key, None)
            else: sqlite3.adapters[key] = prior
        self.db.close()
        self.assertTrue(self.db.observed_material_revision()[3])


if __name__ == '__main__': unittest.main()
