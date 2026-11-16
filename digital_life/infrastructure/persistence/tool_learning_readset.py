"""Bounded, phase-local source facts; never an authorization-result cache.

Only fixed same-instance queries are shareable. A separate observation handle
sees commits even while the caller's handle owns an older SQLite snapshot.
"""
from contextlib import contextmanager
from threading import get_ident
from contextvars import ContextVar
from pathlib import Path
import sqlite3
import stat
from digital_life.domain.contracts import ContractError, Conflict, dumps
from digital_life.domain.tool_learning_sources import SNAPSHOT_KINDS
from digital_life.infrastructure.persistence.sqlite_write_monitor import callback_active
from digital_life.infrastructure.persistence.tool_learning_graph_material import GraphMaterial,encode_graph,decode_graph,storage_size

_ACTIVE = ContextVar('tl_source_phase_readset', default=None)
_SCHEMA_MATERIAL_BOUNDARY = ContextVar('tl_schema_material_boundary',default=None)
OWNER_SOURCE_ROW_TABLES=SNAPSHOT_KINDS|frozenset(('personality_profiles','value_profiles','identity_anchors',
    'memory_items','memory_revisions','perception_observation_revisions','cognition_beliefs','cognition_concepts',
    'cognition_belief_revisions','cognition_concept_revisions','configuration_versions','model_versions',
    'policy_versions','perception_signals','artifacts','tl_product','context_snapshots','thought_requests',
    'thought_results','action_results','runtime_events','metric_definitions','rule_definitions',
    'memory_retrieval_runs','tl_recall_item','tl_content','tl_representation_head'))
OWNER_SOURCE_ROW_QUERIES={table:'owner_source_row_'+table for table in OWNER_SOURCE_ROW_TABLES}
_OWNER_SOURCE_ROW_NAMES=frozenset(OWNER_SOURCE_ROW_QUERIES.values())
QUERIES = {
    'revision_mapping_by_object': 'SELECT id,object_id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=? AND kind=?',
    'revision_mapping_by_id': 'SELECT id,object_id FROM object_revision_registry WHERE instance_id=? AND id=? AND revision_no=? AND kind=?',
    'registered_revision_presence': 'SELECT 1 FROM object_revision_registry WHERE instance_id=? AND object_id=? UNION ALL SELECT 1 FROM object_revision_registry WHERE instance_id=? AND id=? LIMIT 1',
    'control_policy_epochs': 'SELECT * FROM policy_epochs WHERE instance_id=?',
    'control_latest_configuration': 'SELECT id,artifact_ref,hash FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',
    'control_active_barrier': "SELECT 1 FROM tl_barrier WHERE instance_id=? AND source_ref_id IN (?,?) AND state='active' LIMIT 1",
    'snapshot_bridge': "SELECT 1 FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=? AND kind='runtime_events'",
    'selected_revision': 'SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',
    'consumer_dependencies': 'SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? ORDER BY id LIMIT ?',
    'consumer_dependency_materials': 'SELECT id,instance_id,consumer_ref_id,source_ref_id,source_revision_id,relation,purpose,expected_epoch,field_path,metadata_artifact_id FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? ORDER BY id LIMIT ?',
    'source_kind': 'SELECT kind FROM object_registry WHERE instance_id=? AND id=?',
    'storage_schema_version': 'PRAGMA user_version',
    'snapshot_reference_event': "SELECT e.event_type,e.payload_artifact_id,e.payload_hash FROM runtime_events e JOIN object_registry o ON o.instance_id=e.instance_id AND o.id=e.id AND o.kind='runtime_events' WHERE e.instance_id=? AND e.id=? AND e.source='tl.source.snapshot'",
    'static_revision_number': 'SELECT revision_no FROM object_revision_registry WHERE instance_id=? AND id=?',
    'native_revision_identity': 'SELECT id FROM object_revision_registry WHERE instance_id=? AND revision_no=? AND (object_id=? OR id=?)',
    'source_epoch': 'SELECT epoch FROM tl_source_epoch WHERE instance_id=? AND source_ref_id=? AND scope_key=?',
    'source_barriers': "SELECT b.*,ch.payload_artifact_id FROM tl_barrier b JOIN tl_change ch ON ch.instance_id=b.instance_id AND ch.id=b.change_id WHERE b.instance_id=? AND b.source_ref_id=? AND b.state='active' ORDER BY b.id LIMIT ?",
    'revision_owner': 'SELECT object_id,revision_no FROM object_revision_registry WHERE instance_id=? AND id=?',
    'artifact_location': 'SELECT instance_id,id,hash,size,media_type,storage_ref FROM artifacts WHERE instance_id=? AND id=?',
}
QUERIES.update({name:'SELECT * FROM '+table+' WHERE id=? AND instance_id=?'
                for table,name in OWNER_SOURCE_ROW_QUERIES.items()})
_BOUNDED_FACT_NAMES=frozenset(('consumer_dependencies','consumer_dependency_materials','source_barriers'))
_FACT_TABLES={
    'revision_mapping_by_object':{'object_revision_registry'},'revision_mapping_by_id':{'object_revision_registry'},
    'registered_revision_presence':{'object_revision_registry'},'snapshot_bridge':{'object_revision_registry'},
    'selected_revision':{'object_revision_registry'},'revision_owner':{'object_revision_registry'},
    'control_policy_epochs':{'policy_epochs'},'control_latest_configuration':{'configuration_versions'},
    'control_active_barrier':{'tl_barrier'},'consumer_dependencies':{'tl_dependency'},
    'consumer_dependency_materials':{'tl_dependency'},'source_kind':{'object_registry'},
    'storage_schema_version':set(),'snapshot_reference_event':{'runtime_events','object_registry'},
    'static_revision_number':{'object_revision_registry'},'native_revision_identity':{'object_revision_registry'},
    'source_epoch':{'tl_source_epoch'},'source_barriers':{'tl_barrier','tl_change'},'artifact_location':{'artifacts'}}
_FACT_TABLES.update({name:{table}for table,name in OWNER_SOURCE_ROW_QUERIES.items()})


def _signature(path):
    try:
        value=path.lstat()
    except FileNotFoundError:return None
    if not stat.S_ISREG(value.st_mode):raise Conflict('shared source path is not a regular file')
    return value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns


def current_readset(store):
    value=_ACTIVE.get()
    if value is None or value.closed or value.store is not store or value.connection is not store.db or value.instance!=store.instance_id:return None
    return value


def checkpoint(store,include_artifacts=True):
    value=current_readset(store)
    if value is not None:value.checkpoint(include_artifacts)


def clear_reference_mappings(store):
    from digital_life.infrastructure.persistence.tool_learning_meter import _REFERENCE_BOUNDARY
    state=_REFERENCE_BOUNDARY.get()
    if state is not None and state['store']is store:
        state['cache'].clear();state['generation']=state.get('generation',0)+1


def abandon_transaction_boundary(store):
    clear_reference_mappings(store)
    value=current_readset(store)
    if value is not None:value.close()


def savepoint_rolled_back(store):
    # A rolled-back savepoint can leave phantom rows with the same monotonically
    # increasing total_changes. Invalidate material, never rebase live probes.
    clear_reference_mappings(store)
    value=current_readset(store)
    if value is not None:
        value.rollback_generation+=1
        value.clear(preserve_material=False)


def before_transaction_commit(store):
    value=current_readset(store)
    if value is not None and value.input_receipt is not None:value.checkpoint()


def transaction_ended(store,*,rolled_back=False):
    # total_changes does not decrease on rollback: transaction-local reference
    # proofs must never survive either kind of completed write boundary.
    clear_reference_mappings(store)
    value=current_readset(store)
    if value is not None:
        # A completed local UoW starts a fresh read generation. No old fact or
        # authority memo may survive COMMIT/ROLLBACK, including own WAL writes.
        version=value.observer.execute('PRAGMA data_version').fetchone()[0]
        if store.db.execute('PRAGMA data_version').fetchone()[0]!=value.primary_version:raise Conflict('shared source database changed outside phase')
        directory=(value.root/'blobs').lstat()
        if not stat.S_ISDIR(directory.st_mode) or (directory.st_dev,directory.st_ino)!=value.blob_directory:raise Conflict('shared artifact directory replaced')
        signatures=tuple(_signature(p)for p in value.paths)
        for index in (0,2):
            before=value.signatures[index];after=signatures[index]
            if (before is None)!=(after is None) or before is not None and before[:2]!=after[:2]:raise Conflict('shared source database path replaced')
        if signatures[2:]!=value.signatures[2:]:raise Conflict('shared source control changed')
        for path,prior in value.blobs.items():
            if _signature(path)!=prior:raise Conflict('shared source artifact changed')
        receipt=value.input_receipt
        preserve=(not rolled_back and receipt is not None and value.monitor is not None
                  and value.monitor.committed_receipt(receipt))
        value.transaction_generation+=1
        if rolled_back:value.rollback_generation+=1
        if preserve:
            strong=value._discard_input_affected(receipt,insert_only=value.monitor.insert_only_receipt(receipt,committed=True))
            stats=getattr(store,'_input_certificate_stats',None)
            if stats is not None:
                stats['committed']+=1
                if strong:stats['strong_material_committed']+=1
        else:value.clear(preserve_material=not rolled_back)
        value.input_receipt=None
        value.changes=store.db.total_changes
        value.signatures=signatures
        value.version=version
        value.monitor_stamp=value._monitor_stamp()


@contextmanager
def schema_material_boundary(store):
    # Only the fixed owner.control caller enters after its existing freshness
    # boundary. This is raw schema data admission, never a gate verdict.
    phase=current_readset(store)
    value=None if phase is None else(phase,phase.generation,phase.transaction_generation)
    token=_SCHEMA_MATERIAL_BOUNDARY.set(value)
    try:yield
    finally:_SCHEMA_MATERIAL_BOUNDARY.reset(token)


def can_share_schema_material(store):
    phase=current_readset(store);value=_SCHEMA_MATERIAL_BOUNDARY.get()
    return (phase is not None and value is not None and value[0]is phase
            and value[1:]==(phase.generation,phase.transaction_generation)
            and can_share_material_facts(store))


def can_share_material_facts(store):
    from digital_life.infrastructure.persistence.tool_learning_meter import _ACTIVE as meter_active,logical_observer_required
    phase=current_readset(store);meter=meter_active.get()
    return (not callback_active() and not logical_observer_required()
            and phase is not None and phase.reusable and phase.monitor is not None
            and meter is not None and getattr(meter,'phase_store',None)is store
            and getattr(meter,'row_observer',None)is None
            and phase.monitor.known_read_environment())


def _query_parameters(instance,name,parameters):
    if name=='storage_schema_version':
        if parameters:raise ContractError('schema version fact accepts no parameters')
        return ()
    if name in _OWNER_SOURCE_ROW_NAMES:
        if len(parameters)!=1:raise ContractError('owner source row requires one object ID')
        return parameters[0],instance
    if name in ('revision_mapping_by_object','revision_mapping_by_id'):
        from digital_life.domain.tool_learning_types import string,integer
        if len(parameters)!=3:raise ContractError('revision mapping requires ID, revision and exact kind')
        string(parameters[0]);integer(parameters[1]);string(parameters[2])
        return instance,*parameters
    if name=='registered_revision_presence':
        from digital_life.domain.tool_learning_types import string
        if len(parameters)!=1:raise ContractError('revision presence accepts exactly one object ID')
        string(parameters[0])
        return instance,parameters[0],instance,parameters[0]
    return instance,*parameters


def facts(store,name,*parameters):
    """Return immutable sqlite.Row facts, demand-read with original row metering."""
    if name not in QUERIES:raise ContractError('unregistered shared fact query')
    bound=_query_parameters(store.instance_id,name,parameters)
    value=current_readset(store)
    if value is not None:return value.read(name,parameters)
    return store.db.execute(QUERIES[name],bound)


def owner_source_row(store,kind,key):
    """Complete fixed-table material, never a source-use authorization result."""
    name=OWNER_SOURCE_ROW_QUERIES.get(kind)
    if name is None:raise ContractError('unknown owner source row query')
    row=next(iter(facts(store,name,key)),None)
    if row is None:raise ContractError('object not found in instance: '+kind)
    return dict(row)


def dependency_materials(store,consumer,limit):
    """Internal graph material; observers keep the original complete-row SQL."""
    from digital_life.infrastructure.persistence.tool_learning_meter import _ACTIVE as meter_active
    meter=meter_active.get()
    name=('consumer_dependency_materials'if meter is not None and getattr(meter,'row_observer',None)is None
          else 'consumer_dependencies')
    return facts(store,name,consumer,limit)


def track_artifact(store,key):
    value=current_readset(store)
    if value is not None:return value.track_artifact(key)
    row=store.db.execute(QUERIES['artifact_location'],(store.instance_id,key)).fetchone()
    if row is None:raise ContractError('artifact is not registered in this instance')
    return tuple(row)


def track_location(store,location):
    value=current_readset(store)
    if value is not None:value.track_location(location)


class PhaseReadSet:
    max_keys=4096
    max_bytes=4*1024*1024
    max_artifacts=4096
    def __init__(self,store):
        self.store=store;self.connection=store.db;self.instance=store.instance_id
        self.closed=False;self.stamp=object();self.check_depth=0;self.transaction_generation=0;self.rollback_generation=0;self.cache={};self.graphs={};self.prepared={};self.admissions={};self.fact_sizes={};self.graph_sizes={};self.prepared_sizes={};self.admission_sizes={};self.bytes=0;self.blobs={};self.blob_bytes=0;self.generation=0;self.reusable=True
        self.root=Path(store.root)
        directory=(self.root/'blobs').lstat()
        if not stat.S_ISDIR(directory.st_mode):raise Conflict('shared artifact directory is unsafe')
        self.blob_directory=(directory.st_dev,directory.st_ino)
        self.paths=tuple(self.root/name for name in ('runtime.sqlite','runtime.sqlite-wal','control.sqlite','control.sqlite-wal'))
        self.signatures=tuple(_signature(p)for p in self.paths)
        if self.signatures[0] is None:raise Conflict('shared source database unavailable')
        self.observer=sqlite3.connect((self.root/'runtime.sqlite').as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=5)
        self.version=self.observer.execute('PRAGMA data_version').fetchone()[0]
        self.primary_version=store.db.execute('PRAGMA data_version').fetchone()[0]
        self.changes=store.db.total_changes
        from digital_life.infrastructure.persistence.sqlite_store import managed_database
        self.monitor=managed_database(store.db);self.monitor_stamp=self._monitor_stamp();self.input_receipt=None;self.signature_check=None
        self._clear_material()
    def _monitor_stamp(self):
        if self.monitor is None:return None
        value=self.monitor.monitor_state()
        return value['configuration'],value['schema_epoch'],value['write_sequence']
    def _sync_monitor(self):
        stamp=self._monitor_stamp()
        if stamp!=self.monitor_stamp:
            clear_reference_mappings(self.store)
            self.clear(preserve_material=True);self.monitor_stamp=stamp
    def _discard_input_affected(self,receipt,*,insert_only=False):
        from digital_life.infrastructure.persistence.sqlite_store import _INPUT_SQL,_INPUT_SCHEMA_DIGEST
        changed={table for database,table in receipt.tables}
        # Only the reviewed ordinary INSERT can preserve successful registry
        # lookups and pure graph material. A receipt is not an authority result.
        insert_only=(insert_only and receipt.contract.sql==_INPUT_SQL and receipt.schema_signature==_INPUT_SCHEMA_DIGEST
                     and receipt.tables==frozenset((('main','tl_input_dependency'),('main','object_registry')))
                     and bool(receipt.footprint)
                     and all(event[0]==sqlite3.SQLITE_INSERT for event in receipt.footprint))
        for key in list(self.cache):
            source_tables=_FACT_TABLES.get(key[0])
            positive_kind=insert_only and key[0]in ('source_kind','snapshot_reference_event') and len(self.cache[key])==1
            if not positive_kind and (source_tables is None or source_tables&changed or key[0]=='storage_schema_version'and not insert_only):
                self.cache.pop(key);self.bytes-=self.fact_sizes.pop(key)
        if not insert_only:
            self.bytes-=sum(self.graph_sizes.values())+sum(self.prepared_sizes.values())
            self.graphs.clear();self.prepared.clear();self.graph_sizes.clear();self.prepared_sizes.clear()
        else:
            for key in list(self.prepared):
                if not key or key[0]not in ('TL-DEPENDENCY-1','TL-DEPENDENCY-BINDING-1'):
                    self.prepared.pop(key);self.bytes-=self.prepared_sizes.pop(key)
        if not insert_only:
            self.bytes-=sum(self.admission_sizes.values())
            self.admissions.clear();self.admission_sizes.clear()
        self.generation+=1;clear_reference_mappings(self.store)
        return insert_only
    def accept_input_receipt(self,managed,receipt):
        allowed=frozenset((('main','tl_input_dependency'),('main','object_registry')))
        if (self.closed or current_readset(self.store)is not self or managed is not self.monitor
                or receipt.context_token is not self.stamp or receipt.tables!=allowed
                or not managed.receipt_current(receipt)):return False
        stamp=self._monitor_stamp()
        if (self.monitor_stamp is None or stamp[:2]!=self.monitor_stamp[:2]
                or stamp[2]!=self.monitor_stamp[2]+1):return False
        # Full real probes precede consumption; own changes are explained only
        # by this actual monitored statement, not by total_changes arithmetic.
        signatures,version=self._probe(True)
        insert_only=managed.insert_only_receipt(receipt)
        if not managed.accept_receipt(receipt):return False
        strong=self._discard_input_affected(receipt,insert_only=insert_only)
        if strong:self.store._input_certificate_stats['strong_material_accepted']+=1
        self.changes=self.store.db.total_changes;self.signatures=signatures;self.version=version
        self.monitor_stamp=self._monitor_stamp();self.input_receipt=receipt
        return True
    def _clear_material(self):
        # Existing operation caches otherwise outlive this stricter phase.
        from digital_life.infrastructure.persistence.tool_learning_meter import _ACTIVE as meter_active,_REFERENCE_BOUNDARY
        reference=_REFERENCE_BOUNDARY.get()
        if reference is not None and reference['store'] is self.store:reference['cache'].clear()
        meter=meter_active.get()
        if meter is not None:meter.artifact_cache.clear();meter.metadata_cache.clear()
    def clear(self,preserve_material=False):
        self._clear_entries();self.generation+=1;self.reusable=True
        self.input_receipt=None
        if not preserve_material:self.blobs.clear();self.blob_bytes=0;self._clear_material()
        # Reference mapping proofs still use total_changes. The primary-handle
        # data_version excludes own commits, detecting foreign commits even in
        # the small observer rebase window; no stale proof is rebased as current.
    def _probe(self,include_artifacts=True):
        if self.closed:raise Conflict('shared source phase has ended')
        if self.connection is not self.store.db or self.instance!=self.store.instance_id:raise Conflict('shared source connection changed')
        # Run callback-capable SQLite probes first. Files/control are sampled
        # only afterwards, with no later callback SQL before receipt acceptance.
        try:version=self.observer.execute('PRAGMA data_version').fetchone()[0]
        except sqlite3.Error as error:raise Conflict('shared source database unavailable or replaced') from error
        if self.connection.execute('PRAGMA data_version').fetchone()[0]!=self.primary_version:raise Conflict('shared source database changed outside phase')
        directory=(self.root/'blobs').lstat()
        if not stat.S_ISDIR(directory.st_mode) or (directory.st_dev,directory.st_ino)!=self.blob_directory:raise Conflict('shared artifact directory replaced')
        signatures=tuple(_signature(p)for p in self.paths)
        # A path identity change cannot be repaired by reading the old open fd.
        for index in (0,2):
            before=self.signatures[index];after=signatures[index]
            if (before is None)!=(after is None) or before is not None and before[:2]!=after[:2]:raise Conflict('shared source database path replaced')
        own=self.store.db.total_changes!=self.changes
        if signatures[2:]!=self.signatures[2:]:raise Conflict('shared source control changed')
        if not own and (version!=self.version or signatures[:2]!=self.signatures[:2]):raise Conflict('shared source database changed outside phase')
        if include_artifacts:
            for path,prior in self.blobs.items():
                if _signature(path)!=prior:raise Conflict('shared source artifact changed')
        return signatures,version
    def checkpoint(self,include_artifacts=True):
        self._sync_monitor()
        signatures,version=self._probe(include_artifacts)
        own=self.store.db.total_changes!=self.changes
        if own:
            self.clear(preserve_material=True);self.changes=self.store.db.total_changes
        self.signatures=signatures;self.version=version
        self.monitor_stamp=self._monitor_stamp()
    def _assert_current(self,transaction_generation=None,rollback_generation=None):
        if self.closed or current_readset(self.store)is not self:raise Conflict('shared source phase ended before row consumption')
        if transaction_generation is not None and self.transaction_generation!=transaction_generation:raise Conflict('shared source transaction ended before row consumption')
        if rollback_generation is not None and self.rollback_generation!=rollback_generation:raise Conflict('shared source material rolled back before row consumption')
    def read(self,name,parameters):
        self._assert_current()
        # The trusted local owner checks phase freshness at every check/callback
        # boundary. No callbacks or arbitrary SQL run while gathering these rows.
        bound=_query_parameters(self.instance,name,parameters)
        if callback_active():return self.store.db.execute(QUERIES[name],bound)
        self._sync_monitor()
        if self.store.db.total_changes!=self.changes:self.checkpoint()
        transaction_generation=self.transaction_generation;rollback_generation=self.rollback_generation
        key=(name,parameters)
        if self.reusable and key in self.cache:
            rows=self.cache[key]
            if can_share_material_facts(self.store):self.cache.pop(key);self.cache[key]=rows
            return self._logical_rows(rows,transaction_generation,rollback_generation)
        if name in _BOUNDED_FACT_NAMES and parameters[-1]>=0:
            complete=(name,('complete',parameters[0]))
            if self.reusable and complete in self.cache:
                rows=self.cache[complete]
                if can_share_material_facts(self.store):self.cache.pop(complete);self.cache[complete]=rows
                return self._logical_rows(rows[:parameters[-1]],transaction_generation,rollback_generation)
        cursor=self.store.db.execute(QUERIES[name],bound)
        if name not in _BOUNDED_FACT_NAMES and name!='control_policy_epochs':
            row=cursor.fetchone();rows=()if row is None else (row,)
            self.remember(key,rows)
            return rows
        def consume():
            rows=[];retain=True;size=0;iterator=iter(cursor)
            # Yield only after the original per-row meter charges. A caller
            # stopping at a logical limit cannot accidentally pre-read 64 rows.
            while True:
                self._assert_current(transaction_generation,rollback_generation)
                row=next(iterator,None)
                if row is None:break
                if retain:
                    size+=len(dumps(dict(row)).encode('utf-8'))
                    if self.bytes+self.blob_bytes+size<=self.max_bytes:rows.append(row)
                    else:retain=False;rows.clear()
                yield row
            if retain:
                retained_key=(name,('complete',parameters[0]))if name in _BOUNDED_FACT_NAMES and len(rows)<parameters[-1] else key
                self.remember(retained_key,tuple(rows),size)
        return consume()
    def _logical_rows(self,rows,transaction_generation,rollback_generation):
        from digital_life.infrastructure.persistence.tool_learning_meter import notify_logical_row
        self._assert_current(transaction_generation,rollback_generation)
        for row in rows:
            if callback_active():raise Conflict('retained source iterator cannot enter a SQLite callback')
            self._assert_current(transaction_generation,rollback_generation)
            # A cached fact is not a second physical read. The real consumer
            # still observes each row it actually consumes, preserving lineage.
            notify_logical_row(row)
            yield row
    def remember(self,key,rows,size=None):
        if callback_active():return
        if size is None:size=sum(len(dumps(dict(row)).encode('utf-8'))for row in rows)
        size+=len(dumps([key[0],list(key[1])]).encode('utf-8'))
        if key in self.cache:return
        if (self.reusable and can_share_material_facts(self.store)
                and (self.entry_count()>=self.max_keys or self.bytes+self.blob_bytes+size>self.max_bytes)):
            needed_keys=max(0,self.entry_count()+1-self.max_keys)
            needed_bytes=max(0,self.bytes+self.blob_bytes+size-self.max_bytes)
            # Preflight before deleting anything: graphs/admissions and all
            # tracked files are outside this fact replacement victim pool.
            reclaimable=self.bytes-sum(self.graph_sizes.values())-sum(self.admission_sizes.values())
            if needed_keys<=len(self.cache)+len(self.prepared) and needed_bytes<=reclaimable:
                while (self.cache or self.prepared) and (self.entry_count()>=self.max_keys or self.bytes+self.blob_bytes+size>self.max_bytes):
                    if self.prepared:
                        victim,_=self.prepared.popitem();self.bytes-=self.prepared_sizes.pop(victim)
                    else:
                        victim=next(iter(self.cache));self.cache.pop(victim);self.bytes-=self.fact_sizes.pop(victim)
        if self.reusable and self.entry_count()<self.max_keys and self.bytes+self.blob_bytes+size<=self.max_bytes:
            self.cache[key]=rows;self.fact_sizes[key]=size;self.bytes+=size
    def entry_count(self):
        return len(self.cache)+len(self.graphs)+len(self.prepared)+len(self.admissions)
    def _clear_entries(self):
        self.cache.clear();self.graphs.clear();self.prepared.clear();self.admissions.clear()
        self.fact_sizes.clear();self.graph_sizes.clear();self.prepared_sizes.clear();self.admission_sizes.clear();self.bytes=0
    def evict_one(self):
        if self.admissions:
            key,_=self.admissions.popitem();self.bytes-=self.admission_sizes.pop(key)
        elif self.prepared:
            key,_=self.prepared.popitem();self.bytes-=self.prepared_sizes.pop(key)
        else:self._evict_material()
    def _evict_material(self):
        if self.graphs:
            key,_=self.graphs.popitem();self.bytes-=self.graph_sizes.pop(key)
        elif self.cache:
            if can_share_material_facts(self.store):
                key=next(iter(self.cache));self.cache.pop(key)
            else:key,_=self.cache.popitem()
            self.bytes-=self.fact_sizes.pop(key)
    def _trusted_graph_material(self):
        lease=self.signature_check
        return (lease is not None and can_share_material_facts(self.store)
                and lease['phase']is self and lease['thread']==get_ident()
                and lease['service'].authority is lease['authority']
                and lease['owner'].source is lease['authority']and lease['authority'].o is lease['owner']
                and lease['owner'].s is self.store and self.check_depth==lease['depth']
                and self.generation==lease['generation']
                and self.transaction_generation==lease['transaction']
                and self.rollback_generation==lease['rollback']
                and self._monitor_stamp()==lease['monitor_stamp'][:3])
    def graph_admitted(self,key):
        from digital_life.infrastructure.persistence.tool_learning_meter import logical_observer_required
        if callback_active() or not self.reusable or logical_observer_required():return False
        self._sync_monitor()
        if self._trusted_graph_material():
            self.store._graph_material_stats['eligible']+=1;return True
        if key in self.admissions:return True
        size=len(key.encode('utf-8'))+1
        if self.entry_count()<self.max_keys and self.bytes+self.blob_bytes+size<=self.max_bytes:
            self.admissions[key]=True;self.admission_sizes[key]=size;self.bytes+=size
        return False
    def prepared_metadata(self,key):
        from digital_life.infrastructure.persistence.tool_learning_meter import logical_observer_required
        if not callback_active():self._sync_monitor()
        return self.prepared.get(key)if self.reusable and not callback_active() and not logical_observer_required() else None
    def remember_prepared_metadata(self,key,encoded,scope_key):
        from digital_life.infrastructure.persistence.tool_learning_meter import logical_observer_required
        if callback_active() or logical_observer_required():return
        # The phase stamp is an opaque Python identity, never a business ID
        # or serialized material. Account its fixed key marker; all data parts
        # retain their exact encoded byte size.
        stamped=bool(key) and key[0] is self.stamp
        sized_key=key[1:]if stamped else key
        size=len(dumps(sized_key).encode('utf-8'))+int(stamped)+len(encoded.encode('utf-8'))+len(scope_key.encode('utf-8'))
        if self.reusable and key not in self.prepared and self.entry_count()<self.max_keys and self.bytes+self.blob_bytes+size<=self.max_bytes:
            self.prepared[key]=(encoded,scope_key);self.prepared_sizes[key]=size;self.bytes+=size
    def graph(self,key):
        from digital_life.infrastructure.persistence.tool_learning_meter import logical_observer_required
        if callback_active() or not self.reusable or logical_observer_required():return None
        self._sync_monitor()
        value=self.graphs.get(key)
        if value is not None and type(value[0])is GraphMaterial:
            if not self._trusted_graph_material():return None
            self.graphs.pop(key);self.graphs[key]=value
            encoded=decode_graph(value[0],self.max_bytes)
            self.store._graph_material_stats['returned']+=1
            return encoded,value[1]
        return value
    def remember_graph(self,key,encoded,logical_rows):
        from digital_life.infrastructure.persistence.tool_learning_meter import logical_observer_required
        if callback_active() or logical_observer_required():return
        generation=self.generation;self._sync_monitor()
        if generation!=self.generation:return
        if self._trusted_graph_material():
            self._remember_graph_material(key,encoded,logical_rows);return
        size=len(key.encode('utf-8'))+len(encoded.encode('utf-8'))+len(str(logical_rows))
        if (not self.reusable or key in self.graphs or
            self.entry_count()>=self.max_keys or
            self.bytes+self.blob_bytes+size>self.max_bytes):return
        self.graphs[key]=(encoded,logical_rows);self.graph_sizes[key]=size;self.bytes+=size
    def _remember_graph_material(self,key,encoded,logical_rows):
        if type(logical_rows)is not int or logical_rows<0:return
        material=encode_graph(encoded,self.max_bytes)
        if material is None:return
        size=len(key.encode('utf-8'))+storage_size(material)+len(str(logical_rows))
        if not self.reusable or key in self.graphs or size+self.blob_bytes>self.max_bytes:return
        keys=max(0,self.entry_count()+1-self.max_keys)
        space=max(0,self.bytes+self.blob_bytes+size-self.max_bytes)
        victims=[];reclaimed=0
        for namespace,sizes,items in (('prepared',self.prepared_sizes,reversed(self.prepared)),
                                      ('cache',self.fact_sizes,iter(self.cache)),
                                      ('graphs',self.graph_sizes,iter(self.graphs))):
            for old in items:
                if len(victims)>=keys and reclaimed>=space:break
                victims.append((namespace,old,sizes[old]));reclaimed+=sizes[old]
            if len(victims)>=keys and reclaimed>=space:break
        if len(victims)<keys or reclaimed<space:return
        for namespace,old,amount in victims:
            values={'prepared':self.prepared,'cache':self.cache,'graphs':self.graphs}[namespace]
            sizes={'prepared':self.prepared_sizes,'cache':self.fact_sizes,'graphs':self.graph_sizes}[namespace]
            values.pop(old);sizes.pop(old);self.bytes-=amount
            if namespace=='graphs':self.store._graph_material_stats['evicted']=self.store._graph_material_stats.get('evicted',0)+1
        self.graphs[key]=(material,logical_rows);self.graph_sizes[key]=size;self.bytes+=size
        self.store._graph_material_stats['stored']+=1
    def track_artifact(self,key):
        rows=self.read('artifact_location',(key,))
        row=next(iter(rows),None)
        if row is None:raise ContractError('artifact is not registered in this instance')
        self.track_location(row['storage_ref'])
        return tuple(row)
    def _tracked_signature_current(self,path):
        lease=self.signature_check
        if lease is None or callback_active() or self.closed:return False
        if lease['thread']!=get_ident():return False
        if type(path)is str:
            path=lease['locations'].get(path)
            if path is None:return False
        from digital_life.infrastructure.persistence.tool_learning_meter import _ACTIVE as meter_active
        meter=meter_active.get()
        if (current_readset(self.store)is not self or lease['phase']is not self
                or meter is not lease['meter'] or getattr(meter,'phase_store',None)is not self.store
                or getattr(meter,'row_observer',None)is not None or not self.reusable
                or self.check_depth!=lease['depth'] or self.generation!=lease['generation']
                or self.transaction_generation!=lease['transaction'] or self.rollback_generation!=lease['rollback']
                or lease['service'].authority is not lease['authority']
                or lease['owner'].source is not lease['authority'] or lease['authority'].o is not lease['owner']
                or lease['owner'].s is not self.store or path not in lease['paths'] or path not in self.blobs):return False
        return self.monitor.observed_material_revision()==lease['monitor_stamp']
    def track_location(self,location,*,fresh=False):
        if type(location)is str and not fresh and self._tracked_signature_current(location):
            self.store._file_signature_stats['hits']+=1;return
        if type(location)is not str or len(location)!=64 or any(c not in '0123456789abcdef'for c in location):raise ContractError('invalid artifact location')
        path=self.root/'blobs'/location
        signature=_signature(path)
        if signature is None:raise ContractError('artifact bytes unavailable or unsafe')
        if path in self.blobs and self.blobs[path]!=signature:raise Conflict('shared source artifact changed')
        # Tracking is bounded too. Overflow disables retention rather than
        # admitting an unbounded graph/file manifest.
        if path not in self.blobs:
            size=len(dumps([str(path.relative_to(self.root)),signature]).encode('utf-8'))
            # File integrity tracking takes priority over re-readable SQL facts.
            # Evict facts, never the tracked-file proof, to stay in one bound.
            while self.entry_count() and self.bytes+self.blob_bytes+size>self.max_bytes:
                self.evict_one()
            if len(self.blobs)>=self.max_artifacts or self.bytes+self.blob_bytes+size>self.max_bytes:
                # End reuse when tracking cannot remain bounded. Existing
                # retained files are still checked; subsequent SQL stays live.
                if self.reusable:
                    self._clear_entries();self.reusable=False;self.generation+=1;self._clear_material()
                return
            self.blobs[path]=signature;self.blob_bytes+=size
    def close(self):
        if not self.closed:
            self.closed=True;self.clear();self.observer.close()


@contextmanager
def shared_read_boundary(store):
    phase=PhaseReadSet(store);token=_ACTIVE.set(phase)
    try:
        yield phase
        phase.checkpoint()
    finally:
        phase.close();_ACTIVE.reset(token)
