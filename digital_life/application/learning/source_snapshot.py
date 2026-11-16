"""Real immutable M17 snapshots for explicitly unversioned mutable owners."""
from copy import deepcopy
from contextlib import contextmanager
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.domain.tool_learning_sources import SNAPSHOT_KINDS,CAS_FIELDS,validate_snapshot
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,identifier,utc
from digital_life.application.learning.eligibility import ToolLearningEligibility,slot,ref,insert,scope_key
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate


class SnapshotAuthority:
    def verify_source(self,entry,principal,origin,selector,scope,stage):raise Forbidden('actual mutable source owner is not configured')
    def verify_capture(self,entry,principal,snapshot,stage):raise Forbidden('source capture retention/selection authority is not configured')
    def dependencies(self,entry,principal,snapshot):raise Forbidden('complete mutable-state source lineage is not configured')
    def verify_dependencies(self,entry,principal,snapshot,dependencies,stage):
        if dependencies:raise Forbidden('actual snapshot support/retention verifier is not configured')


class SourceSnapshots:
    def __init__(self,store,authority=None,clock=utc):
        self.s=store;self.authority=SnapshotAuthority() if authority is None else authority
        if not isinstance(self.authority,SnapshotAuthority):raise ContractError('trusted SnapshotAuthority required')
        self.storage=ToolLearningStore(store);self.clock=clock;self._capture_depth=0
    @staticmethod
    def _attest(value):
        if value is not None:raise Forbidden('snapshot authority must attest by None')
    def _complete_origin_row(self,origin):
        """Reuse complete material only for the actually bound local owner."""
        from digital_life.application.learning.runtime_owners import LocalRuntimeOwners,LocalSnapshots
        from digital_life.infrastructure.persistence.tool_learning_readset import current_readset,checkpoint
        from digital_life.infrastructure.persistence.tool_learning_meter import logical_observer_required
        if type(self)is SourceSnapshots and type(self.authority)is LocalSnapshots:
            owner=self.authority.o
            if (type(owner)is LocalRuntimeOwners and owner.s is self.s
                    and owner.snapshots is self and owner.snapshot_authority is self.authority
                    and current_readset(self.s)is not None and not logical_observer_required()):
                # This entry may follow an authority callback. Recheck actual
                # DB/control/file state before using any retained full row.
                checkpoint(self.s)
                return owner._source_row(origin['kind'],origin['id'])
        return self.s.row(origin['kind'],origin['id'])
    def _origin(self,entry,principal,origin,selector,scope,stage):
        c.validate('Ref',origin);c.validate('Principal',principal);c.validate('Scope',scope)
        if origin['kind'] not in SNAPSHOT_KINDS or origin['revision']['status']!='not_applicable':raise Forbidden('native-versioned or unsupported source cannot use a snapshot bridge')
        self.storage.validate_ref(origin);t.array(selector,t.string)
        if not selector or selector!=sorted(set(selector)):raise ContractError('canonical source selector required')
        if any(column not in self.s.columns[origin['kind']] for column in selector):raise ContractError('unknown source column selector')
        native=self.s.db.execute("SELECT 1 FROM object_revision_registry WHERE instance_id=? AND object_id=? AND kind<>'runtime_events' LIMIT 1",(self.s.instance_id,origin['id'])).fetchone()
        if native:raise Forbidden('real native revisions must be used directly')
        self._attest(self.authority.verify_source(entry,deepcopy(principal),deepcopy(origin),list(selector),deepcopy(scope),stage))
        if self.s.db.execute("SELECT 1 FROM tl_barrier WHERE instance_id=? AND source_ref_id=? AND state='active' LIMIT 1",(self.s.instance_id,origin['id'])).fetchone():raise Forbidden('active origin barrier blocks new/read snapshot; no implicit repair')
        row=self._complete_origin_row(origin);return {key:row[key] for key in selector}
    def _epoch(self,origin,scope):
        row=self.s.db.execute('SELECT epoch FROM tl_source_epoch WHERE instance_id=? AND source_ref_id=? AND scope_key=?',(self.s.instance_id,origin['id'],scope_key(scope))).fetchone()
        return row[0] if row else 0
    def _native(self,origin):
        field=CAS_FIELDS.get(origin['kind'])
        return slot(self._complete_origin_row(origin)[field]) if field else slot()
    def capture(self,entry,principal,origin,selector,scope,*,audit=False):
        principal,origin,selector,scope=deepcopy((principal,origin,selector,scope))
        if audit:raise Forbidden('read-only audit never creates or repairs source snapshots')
        if self.s.db.in_transaction:raise Conflict('snapshot capture requires gate before its transaction')
        return self._capture(entry,principal,origin,selector,scope)
    @contextmanager
    def _capture_owner(self):
        if self._capture_depth>=32:raise Forbidden('source identity association cycle/depth exceeds the bounded observation owner')
        self._capture_depth+=1
        try:yield
        finally:self._capture_depth-=1
    def capture_identity(self,entry,principal,origin,scope):
        if not self.s.db.in_transaction or not self._capture_depth:raise Forbidden('identity observation joins only this active M17 capture')
        return self._capture(entry,deepcopy(principal),deepcopy(origin),['id'],deepcopy(scope))
    def _capture(self,entry,principal,origin,selector,scope):
        with self._capture_owner(),dispatch_gate(self.s.root),self.s.tx():
            self.s.assert_execution_allowed()
            value=self._origin(entry,principal,origin,selector,scope,'capture');native=self._native(origin)
            rows=self.s.db.execute("SELECT r.*,e.payload_artifact_id FROM object_revision_registry r JOIN runtime_events e ON e.id=r.id AND e.instance_id=r.instance_id WHERE r.instance_id=? AND r.object_id=? AND r.kind='runtime_events' AND e.source='tl.source.snapshot' ORDER BY r.revision_no DESC LIMIT 1",(self.s.instance_id,origin['id'])).fetchone()
            previous=validate_snapshot(self.storage.read_artifact(rows['payload_artifact_id'])) if rows else None
            reused_row=rows
            from digital_life.application.learning.runtime_owners import LocalSnapshots
            if (type(self)is SourceSnapshots and type(self.authority)is LocalSnapshots
                    and self.authority.o.snapshots is self and self.authority.o.s is self.s
                    and self.authority.o.snapshot_authority is self.authority and previous and previous['selector']!=selector):
                # An identity-only observation must not evict the most recent
                # observation of another exact projection. Inspect only that
                # projection's latest version, never an older matching value.
                # This preserves A->B->A changes and every existing final guard.
                older=self.s.db.execute("SELECT r.*,e.payload_artifact_id FROM object_revision_registry r JOIN runtime_events e ON e.id=r.id AND e.instance_id=r.instance_id WHERE r.instance_id=? AND r.object_id=? AND r.kind='runtime_events' AND e.source='tl.source.snapshot' AND r.revision_no<? ORDER BY r.revision_no DESC LIMIT 32",(self.s.instance_id,origin['id'],rows['revision_no']))
                for candidate in older:
                    snapshot=validate_snapshot(self.storage.read_artifact(candidate['payload_artifact_id']))
                    if snapshot['selector']==selector:
                        previous=snapshot;reused_row=candidate;break
            if previous and previous['origin']==origin and previous['selector']==selector and previous['digest']['hex']==c.fingerprint(value) and previous['scope']==scope and previous['native_revision']==native:
                self._attest(self.authority.verify_capture(entry,deepcopy(principal),deepcopy(previous),'reuse'))
                if self._origin(entry,principal,origin,selector,scope,'reuse_final')!=value or self._native(origin)!=native:raise Conflict('source changed in final snapshot reuse authority')
                self.s.assert_execution_allowed()
                return {'object':origin,'revision':reused_row['revision_no'],'epoch':self._epoch(origin,scope)}
            number=(rows['revision_no']+1) if rows else 1
            snapshot={'contract':'TL-SOURCE-SNAPSHOT-1','origin':origin,'selector':selector,'digest':{'algorithm':'sha256','hex':c.fingerprint(value)},'value':value,'observed_at':self.clock(),'native_revision':native,'snapshot_revision':number,'scope':scope}
            validate_snapshot(snapshot);self._attest(self.authority.verify_capture(entry,deepcopy(principal),deepcopy(snapshot),'prepare'))
            dependencies=self.authority.dependencies(entry,deepcopy(principal),deepcopy(snapshot))
            def scoped_dependency(value):
                t.obj(value,('dependency','scope'));c.validate('Dependency',value['dependency']);c.validate('Scope',value['scope'])
            t.array(dependencies,scoped_dependency)
            self._attest(self.authority.verify_dependencies(entry,deepcopy(principal),deepcopy(snapshot),deepcopy(dependencies),'before_retention'))
            if self._origin(entry,principal,origin,selector,scope,'commit')!=value or self._native(origin)!=native:raise Conflict('mutable source changed before immutable snapshot commit')
            event=self.s.event('source.observed_snapshot',payload=snapshot,source='tl.source.snapshot',key=origin['id']+':'+str(number))
            self.s.insert('object_revision_registry',id=event,object_id=origin['id'],revision_no=number,kind='runtime_events')
            token={'object':origin,'revision':number,'epoch':self._epoch(origin,scope)}
            # Root identity remains the origin; the real event and its actual
            # payload are both reachable retention/erase targets.
            self._dependency(ref(self.s,event),token,scope,'read','/origin',principal)
            self._dependency(ref(self.s,self.s.row('runtime_events',event)['payload_artifact_id']),token,scope,'read','/origin',principal)
            self._dependency(ref(self.s,self.s.row('runtime_events',event)['payload_artifact_id']),token,scope,'delete','/origin',principal)
            for index,context in enumerate(dependencies):
                dependency=context['dependency']
                if dependency['consumer_purpose']!=principal['purpose']:raise Forbidden('snapshot provenance purpose differs')
                self._dependency(ref(self.s,event),dependency['expected'],context['scope'],dependency['relation'],'/sources/'+str(index),principal)
            self._attest(self.authority.verify_capture(entry,deepcopy(principal),deepcopy(snapshot),'commit'))
            if self._origin(entry,principal,origin,selector,scope,'final')!=value or self._native(origin)!=native:raise Conflict('source changed in final snapshot authority callback')
            self.s.assert_execution_allowed();return token
    def _dependency(self,consumer,token,scope,relation,path,principal):
        dependency={'target':deepcopy(token['object']),'relation':relation,'expected':deepcopy(token),'consumer_purpose':principal['purpose']}
        metadata={'contract':'TL-DEPENDENCY-1','consumer':consumer,'dependency':dependency,'field_path':path,'scope':deepcopy(scope)}
        revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.s.instance_id,token['object']['id'],token['revision'])).fetchone()
        insert(self.s,'tl_dependency',consumer_ref_id=consumer['id'],source_ref_id=token['object']['id'],source_revision_id=revision[0] if revision else None,relation=relation,purpose=principal['purpose'],expected_epoch=token['epoch'],field_path=path,metadata_artifact_id=self.s.artifact(metadata))
    def fixed(self,entry,principal,token,scope):
        """Current-source check only: never write a new snapshot on mismatch."""
        token,scope=deepcopy((token,scope));c.validate('VersionToken',token)
        known=deepcopy(token['object']);known['revision']=slot(token['revision']);self.storage.validate_ref(known)
        row=self.s.db.execute("SELECT e.* FROM object_revision_registry r JOIN runtime_events e ON e.id=r.id AND e.instance_id=r.instance_id WHERE r.instance_id=? AND r.object_id=? AND r.revision_no=? AND r.kind='runtime_events'",(self.s.instance_id,token['object']['id'],token['revision'])).fetchone()
        if row is None:raise Conflict('real source snapshot revision missing')
        snapshot=validate_snapshot(self.storage.read_artifact(row['payload_artifact_id']))
        if snapshot['scope']!=scope or snapshot['origin']!=token['object']:raise Conflict('snapshot origin/scope mapping differs')
        current=self._origin(entry,principal,token['object'],snapshot['selector'],scope,'current')
        if c.fingerprint(current)!=snapshot['digest']['hex'] or self._native(token['object'])!=snapshot['native_revision']:raise Conflict('mutable source changed after the fixed observed version')
        return deepcopy(snapshot)
