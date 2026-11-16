"""Private managed SQLite write-footprint witnesses, never authorization.

The native handle is intentionally not part of the public API.  This boundary
does not defend against Python code that reads private attributes or replaces
authorization functions.  It does cover every exposed SQLite execution port.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import re
import sqlite3
import weakref


_CALLBACK = ContextVar('tl_managed_sqlite_callback', default=False)


def callback_active():
    """Python reached from a native SQLite execute/fetch must not use caches."""
    return _CALLBACK.get()


@contextmanager
def _native_callback_scope():
    token = _CALLBACK.set(True)
    try:
        yield
    finally:
        _CALLBACK.reset(token)


def _adapter_signature():
    # Identity only: do not invoke arbitrary adapter repr/hash callbacks.
    return tuple(sorted((id(k[0]), id(k[1]), id(v))
                        for k, v in list(sqlite3.adapters.items())))


def _registry_signature():
    return (_adapter_signature(), tuple(sorted((id(k), id(v))
            for k, v in list(sqlite3.converters.items()))))


def _has_adapter(parameters):
    return any((type(value), sqlite3.PrepareProtocol) in sqlite3.adapters
               for value in parameters)


_NATIVE_BINDING_TYPE_IDS = frozenset(id(kind) for kind in
    (str, int, float, bytes, bytearray, memoryview, bool, type(None)))


def _native_adapter_present(adapter_signature):
    # The complete signature has already observed every adapter identity.
    # Reuse that same observation instead of scanning the global map twice.
    return any(row[0] in _NATIVE_BINDING_TYPE_IDS for row in adapter_signature)


_WRITE_ACTIONS = frozenset((sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE,
                            sqlite3.SQLITE_DELETE))
_SCHEMA_ACTIONS = frozenset(getattr(sqlite3, name) for name in (
    'SQLITE_CREATE_INDEX', 'SQLITE_CREATE_TABLE', 'SQLITE_CREATE_TEMP_INDEX',
    'SQLITE_CREATE_TEMP_TABLE', 'SQLITE_CREATE_TEMP_TRIGGER',
    'SQLITE_CREATE_TEMP_VIEW', 'SQLITE_CREATE_TRIGGER', 'SQLITE_CREATE_VIEW',
    'SQLITE_DROP_INDEX', 'SQLITE_DROP_TABLE', 'SQLITE_DROP_TEMP_INDEX',
    'SQLITE_DROP_TEMP_TABLE', 'SQLITE_DROP_TEMP_TRIGGER', 'SQLITE_DROP_TEMP_VIEW',
    'SQLITE_DROP_TRIGGER', 'SQLITE_DROP_VIEW', 'SQLITE_ALTER_TABLE',
    'SQLITE_CREATE_VTABLE', 'SQLITE_DROP_VTABLE', 'SQLITE_REINDEX',
    'SQLITE_ANALYZE', 'SQLITE_ATTACH', 'SQLITE_DETACH'))
_READ_PRAGMAS = frozenset(('application_id', 'user_version', 'schema_version',
    'data_version', 'foreign_keys', 'synchronous', 'busy_timeout', 'journal_mode',
    'table_info', 'table_xinfo', 'foreign_key_list', 'index_list', 'index_info',
    'index_xinfo', 'integrity_check', 'quick_check', 'foreign_key_check',
    'compile_options', 'database_list', 'function_list', 'collation_list', 'query_only'))
_CONNECTION_SETTING_PRAGMAS = frozenset(('query_only',))
_ARGUMENT_READ_PRAGMAS = frozenset(('table_info', 'table_xinfo',
    'foreign_key_list', 'index_list', 'index_info', 'index_xinfo',
    'integrity_check', 'quick_check', 'foreign_key_check'))
_INSERT = re.compile(r'INSERT\s+INTO\s+([a-z_][a-z_0-9]*)\s*'
                     r'\(\s*([a-z_0-9,\s]+)\s*\)\s*VALUES\s*'
                     r'\(\s*([?,\s]+)\s*\)\s*', re.ASCII | re.IGNORECASE)


@dataclass(frozen=True, eq=False)
class InsertContract:
    sql: str
    target: str
    allowed_tables: frozenset
    schema_signature: str
    parameter_count: int
    _owner: object = field(repr=False)
    _configuration: int = field(repr=False)


@dataclass(frozen=True, eq=False)
class WriteReceipt:
    tables: frozenset
    footprint: tuple
    schema_signature: str
    transaction: int
    write_sequence: int
    total_changes: int
    context_token: object = field(repr=False)
    contract: InsertContract = field(repr=False)
    _owner: object = field(repr=False)
    _configuration: int = field(repr=False)


@dataclass
class _Statement:
    effects: list = field(default_factory=list)
    unsafe: bool = False
    transaction_action: str = None
    schema_change: bool = False
    ledger_unsafe: bool = False


@dataclass
class _Window:
    effects: list = field(default_factory=list)
    unsafe: bool = False
    mutations: int = 0


class ManagedCursor:
    """Explicit cursor surface; connection never exposes the native handle."""
    def __init__(self, connection, native):
        self.__connection = connection
        self.__native = native
        self.__factory = connection.row_factory
        connection._remember_cursor(native, self)

    @property
    def connection(self): return self.__connection
    @property
    def description(self): return self.__native.description
    @property
    def rowcount(self): return self.__native.rowcount
    @property
    def lastrowid(self): return self.__native.lastrowid
    @property
    def arraysize(self): return self.__native.arraysize
    @arraysize.setter
    def arraysize(self, value): self.__native.arraysize = value
    @property
    def row_factory(self): return self.__factory
    @row_factory.setter
    def row_factory(self, value):
        self.__connection._configuration_changed()
        self.__factory = value
        if value is not None and value is not sqlite3.Row:
            self.__connection._opaque_cursor_factory = True
            self.__connection._strong_opaque_seen = True
        self.__native.row_factory = self.__connection._row_factory(value)

    def execute(self, sql, parameters=()):
        self.__connection._run(lambda: self.__native.execute(
            self.__connection._prepare_sql(sql), parameters))
        return self
    def executemany(self, sql, parameters):
        self.__connection._opaque_call()
        self.__connection._run(lambda: self.__native.executemany(
            self.__connection._prepare_sql(sql), parameters))
        return self
    def executescript(self, sql):
        self.__connection._opaque_call()
        self.__connection._run(lambda: self.__native.executescript(
            self.__connection._prepare_sql(sql)))
        return self
    def fetchone(self):
        return self.__connection._run(self.__native.fetchone, fetch=True)
    def fetchmany(self, size=None):
        return self.__connection._run(lambda: self.__native.fetchmany(
            self.__native.arraysize if size is None else size), fetch=True)
    def fetchall(self):
        return self.__connection._run(self.__native.fetchall, fetch=True)
    def close(self): return self.__native.close()
    def setinputsizes(self, sizes): return self.__native.setinputsizes(sizes)
    def setoutputsize(self, size, column=None):
        return self.__native.setoutputsize(size) if column is None else self.__native.setoutputsize(size, column)
    def __iter__(self): return self
    def __next__(self):
        row = self.fetchone()
        if row is None: raise StopIteration
        return row


class ManagedConnection:
    """Composition proxy with an always-installed prepare-time authorizer."""
    def __init__(self, native):
        self.__native = native
        self.__cursors = weakref.WeakValueDictionary()
        self._statements = []
        self._window = None
        self._configuration = 0
        self._schema_epoch = 0
        self._approved_schema = None
        self._write_sequence = 0
        self._transaction = 0
        self._ledger = None
        self._last_commit = None
        self._contracts = set()
        self._contract_keys = {}
        self._receipts = set()
        self._foreign_authorizer = None
        self._trace = None
        self._unknown_progress = False
        self._row_factory_value = None
        self._text_factory_value = str
        self._opaque_cursor_factory = False
        self._extension_loaded = False
        self._strong_opaque_seen = False
        self._closed = False
        self._prepare_sequence = 0
        self._prepare_nonce = format(id(self), 'x')
        self._registry = _registry_signature()
        self._strong_opaque_seen = _native_adapter_present(self._registry[0])
        native.set_authorizer(self._authorize)

    def _prepare_sql(self, sql):
        # cache=0 alone is not sufficient on every supported host build.  A
        # never-reused exact SQL string also forces a new native preparation.
        # This marker is technical only: no business UUID, parameter or secret.
        self._prepare_sequence += 1
        # Keep the original leading token.  Python 3.9's sqlite wrapper uses it
        # to classify DML for rowcount / implicit-transaction semantics.
        # A newline also ends an original trailing -- comment before our mark.
        return sql + '\n/*tl-managed:' + self._prepare_nonce + ':' + str(self._prepare_sequence) + '*/'

    def _remember_cursor(self, native, managed):
        self.__cursors[id(native)] = managed

    def _row_factory(self, value):
        if value is None or value is sqlite3.Row: return value
        def wrapped(native, row):
            managed = self.__cursors.get(id(native))
            if managed is None:
                self._opaque_call()
                raise sqlite3.ProgrammingError('unmanaged cursor factory entry')
            return value(managed, row)
        return wrapped

    @property
    def in_transaction(self): return self.__native.in_transaction
    @property
    def total_changes(self): return self.__native.total_changes
    @property
    def row_factory(self): return self._row_factory_value
    @row_factory.setter
    def row_factory(self, value):
        self._configuration_changed()
        if value is not None and value is not sqlite3.Row: self._strong_opaque_seen = True
        self._row_factory_value = value
        self.__native.row_factory = self._row_factory(value)
    @property
    def text_factory(self): return self._text_factory_value
    @text_factory.setter
    def text_factory(self, value):
        self._configuration_changed()
        if value is not str and value is not bytes: self._strong_opaque_seen = True
        self._text_factory_value = value
        self.__native.text_factory = value
    @property
    def isolation_level(self): return self.__native.isolation_level
    @isolation_level.setter
    def isolation_level(self, value):
        self._opaque_call()
        self.__native.isolation_level = value
    @property
    def autocommit(self): return self.__native.autocommit
    @autocommit.setter
    def autocommit(self, value):
        self._opaque_call()
        self.__native.autocommit = value

    def _configuration_changed(self):
        self._configuration += 1
        self._last_commit = None
        if self._ledger is not None: self._ledger['tainted'] = True
        if self._window is not None: self._window.unsafe = True

    def _opaque_call(self): self._configuration_changed()

    def _refresh_registry(self):
        signature = _registry_signature()
        if _native_adapter_present(signature[0]): self._strong_opaque_seen = True
        if signature != self._registry:
            self._registry = signature
            self._configuration_changed()

    def _authorize(self, action, first, second, database, trigger):
        if self._statements:
            statement = self._statements[-1]
            if action in _WRITE_ACTIONS:
                effect = (action, database, first, trigger)
                statement.effects.append(effect)
                if first in ('sqlite_master', 'sqlite_schema', 'sqlite_temp_master'):
                    statement.unsafe = True
            if action in _SCHEMA_ACTIONS:
                statement.unsafe = True
                statement.schema_change = True
            if action == sqlite3.SQLITE_PRAGMA:
                pragma = first.lower() if type(first) is str else first
                if (pragma not in _READ_PRAGMAS or second is not None
                        and pragma not in _ARGUMENT_READ_PRAGMAS):
                    statement.unsafe = True
                    if pragma not in _CONNECTION_SETTING_PRAGMAS:
                        statement.schema_change = True
            if action == sqlite3.SQLITE_SAVEPOINT:
                # SAVEPOINT/RELEASE alone does not alter any source material.
                # It still crosses the narrowly certified transaction shape.
                statement.ledger_unsafe = True
                if first not in ('BEGIN', 'RELEASE'): statement.unsafe = True
            if action == sqlite3.SQLITE_TRANSACTION:
                statement.transaction_action = first
        else:
            # A native public execution port must always install a statement.
            self._opaque_call()
        if self._foreign_authorizer is not None:
            return self._foreign_authorizer(action, first, second, database, trigger)
        return sqlite3.SQLITE_OK

    def _run(self, operation, *, fetch=False, transaction_action=None):
        if self._closed: raise sqlite3.ProgrammingError('Cannot operate on a closed database.')
        self._refresh_registry()
        before = self.in_transaction
        statement = _Statement(transaction_action=transaction_action)
        nested = bool(self._statements)
        self._statements.append(statement)
        succeeded = False
        try:
            with _native_callback_scope():
                result = operation()
            succeeded = True
            return result
        finally:
            self._statements.pop()
            self._refresh_registry()
            after = False if self._closed else self.in_transaction
            if statement.unsafe:
                self._configuration_changed()
            if statement.ledger_unsafe:
                if self._ledger is not None: self._ledger['tainted'] = True
                if self._window is not None: self._window.unsafe = True
            if statement.schema_change: self._schema_epoch += 1
            if statement.effects:
                self._write_sequence += 1
                if self._window is not None:
                    self._window.effects.extend(statement.effects)
                    self._window.mutations += 1
                    if nested: self._window.unsafe = True
                elif self._ledger is not None:
                    self._ledger['tainted'] = True
            if not succeeded:
                if self._ledger is not None: self._ledger['tainted'] = True
                if self._window is not None: self._window.unsafe = True
            if not before and after:
                self._transaction += 1
                self._last_commit = None
                self._receipts.clear()
                self._ledger = {'transaction': self._transaction,
                                'tainted': bool(statement.effects or statement.unsafe or statement.ledger_unsafe or not succeeded), 'accepted': None,
                                'pending': None}
            elif before and not after:
                committed = succeeded and statement.transaction_action == 'COMMIT'
                self._end_transaction(committed)

    def _end_transaction(self, committed):
        ledger = self._ledger
        accepted = None if ledger is None else ledger['accepted']
        current = (committed and ledger is not None and not ledger['tainted']
                   and accepted is not None and self._receipt_state_matches(accepted))
        self._last_commit = accepted if current else None
        self._ledger = None
        self._transaction += 1

    def execute(self, sql, parameters=()):
        native = self._run(lambda: self.__native.execute(self._prepare_sql(sql), parameters))
        return ManagedCursor(self, native)
    def executemany(self, sql, parameters):
        self._opaque_call()
        native = self._run(lambda: self.__native.executemany(self._prepare_sql(sql), parameters))
        return ManagedCursor(self, native)
    def executescript(self, sql):
        self._opaque_call()
        native = self._run(lambda: self.__native.executescript(self._prepare_sql(sql)))
        return ManagedCursor(self, native)
    def cursor(self, factory=None):
        if factory not in (None, sqlite3.Cursor):
            self._opaque_cursor_factory = True
            self._opaque_call()
            raise sqlite3.ProgrammingError('unmanaged cursor factory is not supported')
        return ManagedCursor(self, self.__native.cursor())

    def commit(self):
        return self._run(self.__native.commit, transaction_action='COMMIT')
    def rollback(self):
        self._opaque_call()
        return self._run(self.__native.rollback, transaction_action='ROLLBACK')
    def close(self):
        self._opaque_call()
        self._closed = True
        self.__cursors.clear()
        self._contracts.clear()
        self._contract_keys.clear()
        self._receipts.clear()
        self._ledger = None
        return self.__native.close()
    def __enter__(self): return self
    def __exit__(self, kind, value, traceback):
        if kind is None: self.commit()
        else: self.rollback()
        return False

    def set_authorizer(self, callback):
        self._configuration_changed()
        self._foreign_authorizer = callback
        # The managed hook remains installed; unknown policy is delegated.
        self.__native.set_authorizer(self._authorize)
    def set_trace_callback(self, callback):
        self._configuration_changed()
        self._trace = callback
        if callback is None:
            self.__native.set_trace_callback(None)
        else:
            suffix = re.compile(r'\n/\*tl-managed:' + re.escape(self._prepare_nonce) + r':[0-9]+\*/\Z')
            def traced(sql):
                return callback(suffix.sub('', sql, count=1))
            self.__native.set_trace_callback(traced)
    def set_progress_handler(self, callback, instructions):
        self._configuration_changed()
        self._unknown_progress = callback is not None
        self.__native.set_progress_handler(callback, instructions)
    def _install_meter_progress_handler(self, callback, instructions):
        """Private composition port for the existing resource meter only."""
        self._configuration_changed()
        self._unknown_progress = False
        self.__native.set_progress_handler(callback, instructions)
    def create_function(self, name, narg, function, *, deterministic=False):
        self._configuration_changed()
        # All invocation occurs inside a native execute/fetch callback scope.
        self.__native.create_function(name, narg, function, deterministic=deterministic)
    def create_aggregate(self, name, narg, aggregate_class):
        self._configuration_changed()
        self.__native.create_aggregate(name, narg, aggregate_class)
    def create_window_function(self, name, narg, aggregate_class):
        self._configuration_changed()
        self.__native.create_window_function(name, narg, aggregate_class)
    def create_collation(self, name, callback):
        # Even a later deletion cannot establish that default BINARY matching
        # and old UNIQUE/index semantics have been restored on this handle.
        self._strong_opaque_seen = True
        self._configuration_changed()
        self.__native.create_collation(name, callback)
    def interrupt(self):
        self._opaque_call()
        return self.__native.interrupt()
    def enable_load_extension(self, enabled):
        self._opaque_call()
        if enabled: self._extension_loaded = True
        return self.__native.enable_load_extension(enabled)
    def load_extension(self, path, **kwargs):
        self._opaque_call()
        self._extension_loaded = True
        return self.__native.load_extension(path, **kwargs)
    def blobopen(self, *args, **kwargs):
        self._opaque_call()
        # A blob handle would expose writes outside the execution ledger.
        raise sqlite3.ProgrammingError('managed connection does not expose blob handles')
    def serialize(self, *args, **kwargs):
        self._opaque_call()
        return self.__native.serialize(*args, **kwargs)
    def deserialize(self, *args, **kwargs):
        self._opaque_call()
        return self.__native.deserialize(*args, **kwargs)
    def backup(self, target, *args, **kwargs):
        self._opaque_call()
        if isinstance(target, ManagedConnection):
            target._opaque_call()
            target = target.__native
        with _native_callback_scope():
            return self.__native.backup(target, *args, **kwargs)
    def iterdump(self, *args, **kwargs):
        self._opaque_call()
        iterator = self.__native.iterdump(*args, **kwargs)
        def observed():
            while True:
                self._opaque_call()
                with _native_callback_scope():
                    try: value = next(iterator)
                    except StopIteration: return
                yield value
        return observed()
    def getlimit(self, category): return self.__native.getlimit(category)
    def setlimit(self, category, limit):
        self._opaque_call()
        return self.__native.setlimit(category, limit)
    def getconfig(self, option): return self.__native.getconfig(option)
    def setconfig(self, option, value=True):
        self._opaque_call()
        return self.__native.setconfig(option, value)

    def bind_insert(self, sql, target, allowed_tables, schema_signature):
        match = _INSERT.fullmatch(sql) if type(sql) is str else None
        if match is None or match[1] != target:
            raise ValueError('fixed ordinary INSERT statement required')
        columns = [v.strip() for v in match[2].split(',')]
        placeholders = [v.strip() for v in match[3].split(',')]
        if (not columns or len(set(columns)) != len(columns)
                or any(not re.fullmatch('[a-z_][a-z_0-9]*', v, re.ASCII) for v in columns)
                or placeholders != ['?'] * len(columns)):
            raise ValueError('fixed columns and one binding per value required')
        allowed = frozenset(allowed_tables)
        if ('main', target) not in allowed or any(
                type(v) is not tuple or len(v) != 2 or v[0] != 'main'
                or type(v[1]) is not str for v in allowed):
            raise ValueError('bounded main-database table set required')
        if type(schema_signature) is not str or not schema_signature:
            raise ValueError('reviewed schema signature required')
        if self._approved_schema is None:
            self._approved_schema = (schema_signature, self._schema_epoch)
        if self._approved_schema != (schema_signature, self._schema_epoch):
            raise ValueError('schema approval ended; use a newly reviewed connection')
        key = (sql, target, allowed, schema_signature, self._schema_epoch)
        if key in self._contract_keys: return self._contract_keys[key]
        contract = InsertContract(sql, target, allowed, schema_signature,
                                  len(columns), self, self._schema_epoch)
        self._contracts.add(contract)
        self._contract_keys[key] = contract
        return contract

    def certified_insert(self, contract, parameters, context_token):
        self._refresh_registry()
        if type(contract) is not InsertContract or contract._owner is not self:
            raise ValueError('this managed connection owns the insert contract')
        eligible = (not callback_active() and contract in self._contracts and contract._owner is self
                    and contract._configuration == self._schema_epoch
                    and self.in_transaction and self._ledger is not None
                    and not self._ledger['tainted'] and self._window is None
                    and self._ledger['accepted'] is None and self._ledger['pending'] is None
                    and self._foreign_authorizer is None and self._trace is None
                    and not self._unknown_progress
                    and (self._row_factory_value is None or self._row_factory_value is sqlite3.Row)
                    and (self._text_factory_value is str or self._text_factory_value is bytes)
                    and not self._opaque_cursor_factory and not self._extension_loaded
                    and type(parameters) in (tuple, list)
                    and len(parameters) == contract.parameter_count
                    and all(type(v) in (str, int, bytes, type(None)) for v in parameters)
                    and not _has_adapter(parameters))
        if not eligible:
            return self.execute(contract.sql, parameters), None
        adapters = _adapter_signature()
        window = _Window()
        self._window = window
        configuration = self._configuration
        try:
            cursor = self.execute(contract.sql, parameters)
        except BaseException:
            window.unsafe = True
            raise
        finally:
            self._window = None
        tables = frozenset((event[1], event[2]) for event in window.effects)
        valid = (not window.unsafe and window.mutations == 1
                 and self._configuration == configuration
                 and adapters == _adapter_signature() and not _has_adapter(parameters)
                 and tables <= contract.allowed_tables and ('main', contract.target) in tables
                 and all(event[0] == sqlite3.SQLITE_INSERT for event in window.effects)
                 and self.in_transaction and self._ledger is not None
                 and not self._ledger['tainted'])
        if not valid:
            if self._ledger is not None: self._ledger['tainted'] = True
            return cursor, None
        receipt = WriteReceipt(tables, tuple(window.effects), contract.schema_signature,
                               self._transaction, self._write_sequence, self.total_changes,
                               context_token, contract, self, self._configuration)
        self._receipts.add(receipt)
        self._ledger['pending'] = receipt
        return cursor, receipt

    def _receipt_state_matches(self, receipt):
        return (type(receipt) is WriteReceipt and receipt in self._receipts and receipt._owner is self
                and receipt._configuration == self._configuration
                and receipt.write_sequence == self._write_sequence
                and receipt.total_changes == self.total_changes)
    def receipt_current(self, receipt):
        return (type(receipt) is WriteReceipt and not self._closed and self.in_transaction and self._ledger is not None
                and not self._ledger['tainted']
                and receipt.transaction == self._transaction
                and self._receipt_state_matches(receipt))
    def accept_receipt(self, receipt):
        if (not self.receipt_current(receipt)
                or self._ledger['pending'] is not receipt
                or self._ledger['accepted'] is not None): return False
        self._ledger['accepted'] = receipt
        self._ledger['pending'] = None
        return True
    def committed_receipt(self, receipt):
        return (not self._closed and not self.in_transaction
                and self._last_commit is receipt and self._receipt_state_matches(receipt))

    def insert_only_receipt(self, receipt, *, committed=False):
        """Necessary witness for an additionally reviewed plain INSERT schema.

        Authorizer INSERT alone does not distinguish SQL REPLACE. The caller
        must still verify its exact plain SQL, real approved schema and tables.
        This method grants no authority and does not prove arbitrary UDFs pure.
        """
        self._refresh_registry()
        valid = self.committed_receipt(receipt) if committed else self.receipt_current(receipt)
        return (valid and not self._strong_opaque_seen and not self._extension_loaded
                and not self._opaque_cursor_factory
                and bool(receipt.footprint)
                and all(effect[0] == sqlite3.SQLITE_INSERT for effect in receipt.footprint))

    def known_read_environment(self):
        """Necessary environment only; no SQL, source version or permission proof.

        Fixed binding consumers must still perform their current projections
        and freshness checks. Transaction/receipt state is intentionally absent.
        """
        self._refresh_registry()
        return (not callback_active() and not self._closed
                and self._foreign_authorizer is None and self._trace is None
                and not self._unknown_progress
                and (self._row_factory_value is None or self._row_factory_value is sqlite3.Row)
                and (self._text_factory_value is str or self._text_factory_value is bytes)
                and not self._opaque_cursor_factory and not self._extension_loaded
                and not self._strong_opaque_seen)

    def observed_stamp(self):
        """Small observation for material leases, never a mutation certificate.

        Registry changes remain observed on every call. Consumers still need
        their full environment, source and permission checks at boundaries.
        """
        self._refresh_registry()
        return self.observed_material_revision()

    def material_revision(self):
        """Registry-refreshing observation; same contract as observed_stamp."""
        return self.observed_stamp()

    def observed_material_revision(self):
        """Already-observed fields ONLY for a constrained file-boundary lease.

        No registry refresh. Never use for Ref, metadata, facts, permissions,
        receipts or a known-environment check. Their full refreshes remain.
        """
        return (self._configuration, self._schema_epoch, self._write_sequence, self._closed)

    def monitor_state(self):
        """No SQL or callbacks; an observation, never a mutation certificate."""
        self._refresh_registry()
        can_certify = (not callback_active() and not self._closed and self.in_transaction
            and self._ledger is not None and not self._ledger['tainted']
            and self._ledger['accepted'] is None and self._ledger['pending'] is None
            and self._window is None and self._foreign_authorizer is None and self._trace is None
            and not self._unknown_progress
            and (self._row_factory_value is None or self._row_factory_value is sqlite3.Row)
            and (self._text_factory_value is str or self._text_factory_value is bytes)
            and not self._opaque_cursor_factory and not self._extension_loaded)
        return {'connection': self, 'configuration': self._configuration,
                'schema_epoch': self._schema_epoch, 'transaction': self._transaction,
                'write_sequence': self._write_sequence,
                'total_changes': None if self._closed else self.total_changes,
                'in_transaction': False if self._closed else self.in_transaction,
                'tainted': self._ledger is not None and self._ledger['tainted'],
                'accepted': None if self._ledger is None else self._ledger['accepted'],
                'pending': None if self._ledger is None else self._ledger['pending'],
                'last_commit': self._last_commit, 'closed': self._closed,
                'can_certify': can_certify}


def managed_connection_factory(*args, **kwargs):
    """sqlite3.connect factory; native statement reuse is explicitly disabled."""
    kwargs.pop('factory', None)
    if len(args) > 6:
        # cached_statements is positional index 6 in sqlite3.connect's legacy API.
        args = list(args)
        args[6] = 0
        kwargs.pop('cached_statements', None)
    else:
        kwargs['cached_statements'] = 0
    return ManagedConnection(sqlite3.Connection(*args, **kwargs))
