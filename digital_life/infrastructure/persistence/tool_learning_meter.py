"""Scoped actual primary-store reads/produced material, including M17 reads.

Counts canonical bytes actually returned by SQLite rows plus actual artifact
UTF-8 bytes, not estimated disk pages or provider billing. A bounded operation
must install this on its original prepaid slice before any material is read.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import math
import time
from digital_life.domain.contracts import Forbidden,ContractError,dumps,utc
from digital_life.domain.tool_learning_resources import DIMENSIONS
from digital_life.infrastructure.persistence.sqlite_write_monitor import callback_active

_ACTIVE=ContextVar('tl_actual_resource_meter',default=None)
_REFERENCE_BOUNDARY=ContextVar('tl_immutable_reference_boundary',default=None)
_SOURCE_PREPARATION=ContextVar('tl_source_preparation_observer_suppression',default=None)


def notify_logical_row(row):
    """Notify actual logical use of a retained row; never bill a physical read."""
    meter=_ACTIVE.get()
    observer=None if meter is None else getattr(meter,'row_observer',None)
    if row is not None and observer is not None:observer(row)
    return row


def logical_observer_required():
    """Unknown observers always need SQL-equivalent logical source delivery."""
    meter=_ACTIVE.get()
    observer=None if meter is None else getattr(meter,'row_observer',None)
    if observer is None:return False
    state=_SOURCE_PREPARATION.get()
    return not(state is not None and not state['closed'] and state['meter']is meter
               and state['observer']is observer and state['collector'].busy is True)


@contextmanager
def _source_preparation_observer_boundary(meter,observer,collector):
    """Private application-attested scope; confers no external permission.

    The composition layer owns collector type/method authentication. This
    lower layer only binds its managed state to the actual current meter,
    callback identity and busy guard, and always closes copied state.
    """
    if (_ACTIVE.get()is not meter or meter is None
            or getattr(meter,'row_observer',None)is not observer
            or getattr(collector,'busy',False)is not True):
        yield
        return
    state={'meter':meter,'observer':observer,'collector':collector,'closed':False}
    token=_SOURCE_PREPARATION.set(state)
    try:yield
    finally:state['closed']=True;_SOURCE_PREPARATION.reset(token)


@contextmanager
def immutable_reference_boundary(store):
    """IM11 internal optimization; confers no source or execution authority.

    The real gate excludes collaborating registry cleanup. Any same-connection
    write invalidates all mapped facts, including writes by a trusted callback.
    A new entry/result/external-use boundary always gets a new empty cache.
    """
    from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
    from digital_life.domain.tool_learning_types import structural_validation_boundary
    with dispatch_gate(store.root):
        token=_REFERENCE_BOUNDARY.set({'store':store,'connection':store.db,'instance':store.instance_id,'changes':store.db.total_changes,'cache':set()})
        try:
            with structural_validation_boundary():yield
        finally:_REFERENCE_BOUNDARY.reset(token)


def reference_cache_key(store,value,expected_kind,version_owner):
    if callback_active() or logical_observer_required():return None,False
    state=_REFERENCE_BOUNDARY.get()
    if state is None or state['store'] is not store or state['connection'] is not store.db or state['instance']!=store.instance_id:return None,False
    _refresh_reference_state(state,store)
    key=(dumps([value,expected_kind,version_owner]),state.get('generation',0))
    return key,key in state['cache']


def _refresh_reference_state(state,store):
    from digital_life.infrastructure.persistence.sqlite_store import managed_database
    managed=managed_database(store.db);stamp=None
    if managed is not None:
        value=managed.monitor_state();stamp=(value['configuration'],value['schema_epoch'],value['write_sequence'])
    changes=store.db.total_changes
    if changes!=state['changes'] or stamp!=state.get('monitor_stamp'):
        state['cache'].clear();state['changes']=changes;state['monitor_stamp']=stamp
        state['generation']=state.get('generation',0)+1


def remember_reference(store,key):
    if callback_active() or logical_observer_required():return
    state=_REFERENCE_BOUNDARY.get()
    if key is not None and state is not None and state['store'] is store and state['connection'] is store.db:
        _refresh_reference_state(state,store)
        if key[1]==state.get('generation',0):state['cache'].add(key)


def artifact_before(size):
    meter=_ACTIVE.get()
    if meter is not None:meter.ensure(size)

def artifact_after(size):
    meter=_ACTIVE.get()
    if meter is not None:meter.consume(size)

def artifact_failed():
    meter=_ACTIVE.get()
    if meter is not None:meter.unknown_bytes=True

def external_read_before(size):
    """Actual bounded filesystem verifier read, not a new model/tool cap."""
    meter=_ACTIVE.get()
    if meter is not None:meter.ensure(size,scan=1,items=1)

def external_read_after(size):
    meter=_ACTIVE.get()
    if meter is not None:meter.consume(size,scan=1,items=1)


def material_produced(size):
    meter=_ACTIVE.get()
    if meter is not None:meter.consume(size,scan=0,items=0)


def cached_artifact(row,*,fresh=False):
    meter=_ACTIVE.get()
    from digital_life.infrastructure.persistence.tool_learning_readset import current_readset
    phase=None if meter is None else getattr(meter,'phase_store',None)
    phase=None if phase is None else current_readset(phase)
    if phase is not None:
        phase._sync_monitor();phase.track_location(row['storage_ref'],fresh=fresh)
    if callback_active() or meter is None or phase is not None and not phase.reusable:return False,None
    key=tuple(row[k] for k in ('instance_id','id','hash','size','media_type','storage_ref'))
    return (True,meter.artifact_cache[key]) if key in meter.artifact_cache else (False,None)

def remember_artifact(row,raw,*,fresh=False):
    meter=_ACTIVE.get()
    if meter is not None:
        from digital_life.infrastructure.persistence.tool_learning_readset import current_readset
        store=getattr(meter,'phase_store',None)
        phase=None if store is None else current_readset(store)
        if phase is not None:
            phase.track_location(row['storage_ref'],fresh=fresh)
            if not phase.reusable:return
        if callback_active():return
        meter.artifact_cache[tuple(row[k] for k in ('instance_id','id','hash','size','media_type','storage_ref'))]=bytes(raw)

def cached_metadata(key,value=None):
    import json
    from digital_life.domain.tool_learning_types import json_value
    meter=_ACTIVE.get()
    if callback_active() or meter is None:return None
    from digital_life.infrastructure.persistence.tool_learning_readset import current_readset
    store=getattr(meter,'phase_store',None)
    phase=None if store is None else current_readset(store)
    if phase is not None:phase._sync_monitor()
    if phase is not None and not phase.reusable:return None
    if value is not None:
        # Only validated JSON facts, not arbitrary Python objects or authority
        # results. Keep immutable text; each caller receives an independent tree.
        json_value(value)
        meter.metadata_cache[key]=dumps(value)
    encoded=meter.metadata_cache.get(key)
    return None if encoded is None else json.loads(encoded)


class _Cursor:
    def __init__(self,actual):self.actual=actual
    def __getattr__(self,name):return getattr(self.actual,name)
    @staticmethod
    def charge(row):
        meter=_ACTIVE.get()
        if meter is not None and row is not None:
            value=dict(row) if hasattr(row,'keys') else list(row)
            meter.consume(len(dumps(value).encode('utf-8')),scan=1,items=1)
            notify_logical_row(row)
        return row
    def _before_row(self):
        meter=_ACTIVE.get()
        if meter is not None:meter.ensure(0,scan=1,items=1)
    def fetchone(self):
        self._before_row();return self.charge(self.actual.fetchone())
    def fetchall(self):
        result=[]
        while True:
            row=self.fetchone()
            if row is None:return result
            result.append(row)
    def fetchmany(self,size=None):
        result=[]
        for _ in range(self.actual.arraysize if size is None else size):
            row=self.fetchone()
            if row is None:break
            result.append(row)
        return result
    def execute(self,*args,**kwargs):self.actual.execute(*args,**kwargs);return self
    def executemany(self,*args,**kwargs):self.actual.executemany(*args,**kwargs);return self
    def __iter__(self):
        while True:
            row=self.fetchone()
            if row is None:return
            yield row
    def __next__(self):
        row=self.fetchone()
        if row is None:raise StopIteration
        return row


class _Connection:
    def __init__(self,actual):self.actual=actual
    def __getattr__(self,name):return getattr(self.actual,name)
    def execute(self,*args,**kwargs):return _Cursor(self.actual.execute(*args,**kwargs))
    def executemany(self,*args,**kwargs):return _Cursor(self.actual.executemany(*args,**kwargs))
    def cursor(self,*args,**kwargs):return _Cursor(self.actual.cursor(*args,**kwargs))


class PhysicalReadMeter:
    def __init__(self,amounts,deadline,clock=utc,monotonic=time.monotonic):
        if type(amounts) is not dict or set(amounts)!=set(DIMENSIONS):raise ContractError('real prepaid eight-dimensional slice required')
        if any(type(v) is not int or v<0 for v in amounts.values()):raise ContractError('invalid prepaid slice')
        self.limits=dict(amounts);self.deadline=deadline;self.clock=clock;self.monotonic=monotonic;self.start=monotonic()
        self.actual={k:0 for k in DIMENSIONS};self.unknown_bytes=False;self.excluded=0;self.pause_depth=0;self.paused_at=None;self.artifact_cache={};self.metadata_cache={}
    def _elapsed(self):
        # While an actual child opportunity owns elapsed time, use its fixed
        # entry endpoint. Reads inside that window still consume rows/bytes,
        # but must not write the child's duration into this meter's max.
        end=self.monotonic() if self.paused_at is None else self.paused_at
        return math.ceil((end-self.start-self.excluded)*1000)
    def time(self):
        elapsed=self._elapsed();self.actual['elapsed_ms']=max(self.actual['elapsed_ms'],elapsed)
        if self.clock()>=self.deadline or elapsed>self.limits['elapsed_ms']:raise Forbidden('original actual-read total deadline exhausted')
    def ensure(self,size,scan=0,items=0):
        self.time()
        if type(size) is not int or size<0:raise ContractError('known read/production size required')
        if self.actual['bytes']+size>self.limits['bytes'] or self.actual['scan']+scan>self.limits['scan'] or self.actual['items']+items>self.limits['items']:raise Forbidden('original actual-read slice exhausted before material read')
    def consume(self,size,scan=0,items=0):
        # Already-returned rows/bytes remain measured even when they cross a
        # bound. Artifact known sizes are prechecked before the physical read.
        if type(size) is not int or size<0:raise ContractError('invalid actual bytes')
        self.actual['bytes']+=size;self.actual['scan']+=scan;self.actual['items']+=items
        self.time()
        if any(self.actual[k]>self.limits[k] for k in ('bytes','scan','items')):raise Forbidden('actual returned material exceeds original prepaid slice')
    def usage(self):
        self.actual['elapsed_ms']=max(self.actual['elapsed_ms'],self._elapsed())
        return None if self.unknown_bytes else dict(self.actual)
    @contextmanager
    def excluding_child(self):
        if self.pause_depth==0:self.paused_at=self.monotonic()
        self.pause_depth+=1
        try:yield
        finally:
            self.pause_depth-=1
            if self.pause_depth==0:
                self.excluded+=self.monotonic()-self.paused_at;self.paused_at=None
    @contextmanager
    def installed(self,store):
        if _ACTIVE.get() is not None:raise ContractError('one actual account meter per operation; nested reset is forbidden')
        original=store.db;self.phase_store=store;token=_ACTIVE.set(self);store.db=_Connection(original)
        def progress():
            try:self.time();return 0
            except Forbidden:return 1
        from digital_life.infrastructure.persistence.sqlite_store import managed_database
        managed=managed_database(original)
        install=original.set_progress_handler if managed is None else managed._install_meter_progress_handler
        install(progress,1000)
        try:yield self
        finally:
            install(None,0);store.db=original;_ACTIVE.reset(token);self.artifact_cache.clear();self.metadata_cache.clear();self.phase_store=None
