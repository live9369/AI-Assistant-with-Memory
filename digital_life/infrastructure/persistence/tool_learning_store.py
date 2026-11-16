"""IM04 storage mechanics. No business authorization is inferred from JSON.

StorageAuthority is a trusted composition-root port. Its default denies every
operation; deterministic test implementations are not production authorization.
This module never opens an instance, migrates a schema, or calls a model.
"""
from dataclasses import dataclass
import hashlib
import os
import sqlite3
import stat

from digital_life.domain.contracts import ContractError, Conflict, Forbidden, identifier, dumps, utc
from digital_life.domain import tool_learning_contract as contract
from digital_life.domain import tool_learning_types as types


def has_registered_revision(store, object_id):
    """Indexed existence only, never a version/owner/permission assertion.

    UNION avoids SQLite choosing an instance-wide index scan for OR+LIMIT.
    Both branches retain the original instance predicate and share LIMIT 1.
    """
    types.string(object_id)
    from digital_life.infrastructure.persistence.tool_learning_readset import facts
    return next(iter(facts(store,'registered_revision_presence',object_id)),None)is not None


def _validation_columns(projected,complete):
    """Keep whole rows whenever actual computation provenance observes them.

    This is an internal choice, never an external source-projection option.
    """
    from digital_life.infrastructure.persistence.tool_learning_meter import _ACTIVE
    meter=_ACTIVE.get()
    return complete if meter is not None and getattr(meter,'row_observer',None)is not None else projected


class CommitUnknown(ContractError):
    """Reconcile by original command key/fingerprint; never rerun blindly."""


@dataclass(frozen=True)
class StorageGrant:
    owner: str
    tables: frozenset


class StorageAuthority:
    def verify(self, entry, operation, request, instance_id, stage):
        raise Forbidden('trusted current authorization service is not configured')

    def project_response(self, entry, operation, request, response, instance_id, stage):
        raise Forbidden('current result visibility/projection service is not configured')

    def verify_metric_contract(self, entry, operation, request, metric_contract, definition, instance_id):
        raise Forbidden('trusted metric-contract/version resolver is not configured')

    def verify_external_ref(self, entry, operation, request, reference, instance_id):
        raise Forbidden('authorized external-source material resolver is not configured')


OWNERS = {
    'tl_work': frozenset(('M14', 'coordinator')),
    'tl_product': frozenset(('M14',)),
    'tl_content': frozenset(('M03',)),
    'tl_content_revision': frozenset(('M03',)),
    'tl_decision': frozenset(('M03',)),
    'tl_group': frozenset(('M03', 'M04')),
    'tl_handoff': frozenset(('M03', 'M04')),
    'tl_representation': frozenset(('M04',)),
    'tl_representation_head': frozenset(('M04',)),
    'tl_dependency': types.MODULES,
    'tl_source_epoch': frozenset(('M01', 'M03', 'M12', 'M13', 'M14', 'M17')),
    'tl_barrier': frozenset(('M01', 'M03', 'M12', 'M13', 'M14', 'M17')),
    'tl_change': frozenset(('M01', 'M03', 'M12', 'M13', 'M14', 'M17')),
    'tl_propagation': types.MODULES,
    'tl_erasure_target': frozenset(('M12',)),
    'tl_input_dependency': types.MODULES,
    'tl_effect': frozenset(('M14',)),
    'tl_recall_item': frozenset(('M04',)),
}
OPERATORS = {
    'admit_observation': ('M14',), 'assess_observation': ('M14',),
    'decide_proposal': ('M03',), 'claim_representation': ('M04',),
    'publish_representation': ('M04',), 'recall': ('M04',),
    'apply_invalidation': ('M01','M03','M12','M13','M14','M17'),
    'acknowledge_propagation': tuple(types.MODULES),
    'resume_work': tuple(types.MODULES), 'record_effect': ('M14',),
}
MUTABLE = {
    'tl_work': {'state','phase','review_round','conditions_artifact_id'},
    'tl_content': {'head_revision_id'},
    'tl_group': {'state'},
    'tl_handoff': {'state','lease_worker_id','lease_generation','lease_expires_at','attempts','representation_id','receipt_artifact_id'},
    'tl_representation_head': {'representation_id','expected_content_revision_id'},
    'tl_source_epoch': {'epoch'},
    'tl_barrier': {'state','resolution_artifact_id'},
    'tl_propagation': {'state','coverage_artifact_id','verification_artifact_id'},
    'tl_erasure_target': {'state','verification_artifact_id'},
    'tl_input_dependency': {'body_digest','retention_state'},
}
ARTIFACT_TYPES = {
    ('tl_work','control_artifact_id'): 'Control',
    ('tl_work','method_artifact_id'): 'Method',
    ('tl_product','payload_artifact_id'): 'Product',
    ('tl_decision','decision_artifact_id'): 'Decision',
    ('tl_representation','payload_artifact_id'): 'Representation',
    ('tl_source_epoch','scope_artifact_id'): 'Scope',
    ('tl_barrier','scope_artifact_id'): 'Scope',
    ('tl_propagation','coverage_artifact_id'): 'Coverage',
    ('tl_effect','payload_artifact_id'): 'EffectAssessment',
    ('tl_recall_item','payload_artifact_id'): 'RecallItem',
    ('tl_recall_item','control_artifact_id'): 'Control',
}
STABLE_REVISIONS = {'tl_content':'tl_content_revision','tl_representation_head':'tl_representation',
                    'memory_items':'memory_revisions','perception_observations':'perception_observation_revisions',
                    'cognition_concepts':'cognition_concept_revisions','cognition_beliefs':'cognition_belief_revisions'}
# Immutable payload-row technical tokens have no native child revision. This
# list is deliberately separate from Ref.known and mutable observation bridges.
STATIC_TOKEN_PAYLOADS={
    'configuration_versions':('artifact_ref','hash'),
    'model_versions':('artifact_ref','hash'),
    'perception_signals':('artifact_id',None),
    'thought_requests':('request_artifact_id','request_hash'),
    'thought_results':('response_artifact_id','response_hash'),
    'action_results':('receipt_artifact_id',None),
    'runtime_events':('payload_artifact_id','payload_hash'),
    'tl_product':('payload_artifact_id',None),
}


def command_fingerprint(envelope):
    """Frozen logical semantics, excluding command IDs and execution snapshots."""
    return contract.fingerprint({key:envelope[key] for key in (
        'contract','schema_revision','instance_id','principal','work_ref','expected','payload')})


class ToolLearningStore:
    def __init__(self, store, authority=None):
        self.__store = store
        self.__authority = StorageAuthority() if authority is None else authority
        if not isinstance(self.__authority, StorageAuthority):
            raise ContractError('trusted StorageAuthority port required, not a boolean/callback')
        db = store.db
        if not store.instance_id or not db.execute('PRAGMA foreign_keys').fetchone()[0]:
            raise ContractError('instance and enabled foreign keys required')
        required = set(OWNERS) | {'tl_command'}
        self.__columns = {}
        self.__types = {}
        for table in required:
            cols = {r[1] for r in db.execute('PRAGMA table_info('+table+')')}
            if not {'id','instance_id','schema_revision'} <= cols:
                raise ContractError('TL DDL capability is not installed')
            self.__columns[table] = cols
            self.__types[table]={r[1]:r[2] for r in db.execute('PRAGMA table_info('+table+')')}
        self.instance_id = store.instance_id
        self.__active = False

    def __grant(self, entry, operation, request, stage):
        principal=request['principal']
        types.string(entry); types.enum(operation, OPERATORS)
        contract.validate('Principal', principal)
        for key in ('actor','recipient','authorization'):
            self.validate_ref(principal[key])
        grant = self.__authority.verify(entry, operation, contract.loads(dumps(request)), self.instance_id, stage)
        if (type(grant) is not StorageGrant or grant.owner != principal['module']
                or grant.owner not in OPERATORS[operation]
                or type(grant.tables) is not frozenset or not grant.tables <= set(OWNERS)):
            raise Forbidden('invalid trusted storage grant')
        return grant

    def validate_ref(self, value, *, expected_kind=None, version_owner=None):
        contract.validate('Ref', value)
        if value['instance_id'] != self.instance_id:
            raise Forbidden('external Ref cannot be used as a local database reference')
        from digital_life.infrastructure.persistence.tool_learning_meter import reference_cache_key,remember_reference
        cache_key,cached=reference_cache_key(self.__store,value,expected_kind,version_owner)
        if cached:return value
        db = self.__store.db
        from digital_life.infrastructure.persistence.tool_learning_meter import logical_observer_required
        if logical_observer_required():
            # Full registry rows carry actual computation source identities.
            row=db.execute('SELECT * FROM object_registry WHERE instance_id=? AND id=?',
                           (self.instance_id,value['id'])).fetchone()
        else:
            from digital_life.infrastructure.persistence.tool_learning_readset import facts
            row=next(iter(facts(self.__store,'source_kind',value['id'])),None)
        if row is None or row['kind'] != value['kind'] or (expected_kind is not None and row['kind'] != expected_kind):
            raise ContractError('registered Ref kind/identity mismatch')
        revision = value['revision']
        if revision['status'] == 'known':
            from digital_life.infrastructure.persistence.tool_learning_readset import facts
            if value['kind'] in STABLE_REVISIONS:
                if logical_observer_required():
                    rev=db.execute('SELECT * FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=? AND kind=?',
                        (self.instance_id,value['id'],revision['value'],STABLE_REVISIONS[value['kind']])).fetchone()
                else:rev=next(iter(facts(self.__store,'revision_mapping_by_object',value['id'],revision['value'],STABLE_REVISIONS[value['kind']])),None)
            else:
                if logical_observer_required():
                    rev=db.execute('SELECT * FROM object_revision_registry WHERE instance_id=? AND id=? AND revision_no=? AND kind=?',
                        (self.instance_id,value['id'],revision['value'],value['kind'])).fetchone()
                else:rev=next(iter(facts(self.__store,'revision_mapping_by_id',value['id'],revision['value'],value['kind'])),None)
            from digital_life.domain.tool_learning_sources import SNAPSHOT_KINDS,validate_snapshot
            if rev is None and value['kind'] in SNAPSHOT_KINDS:
                if logical_observer_required():
                    rev=db.execute("SELECT * FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=? AND kind='runtime_events'",(self.instance_id,value['id'],revision['value'])).fetchone()
                else:rev=next(iter(facts(self.__store,'revision_mapping_by_object',value['id'],revision['value'],'runtime_events')),None)
                if rev is not None:
                    event_columns=_validation_columns('e.event_type,e.payload_artifact_id,e.payload_hash','e.*')
                    from digital_life.infrastructure.persistence.tool_learning_readset import can_share_material_facts
                    if type(self)is ToolLearningStore and can_share_material_facts(self.__store):
                        event=next(iter(facts(self.__store,'snapshot_reference_event',rev['id'])),None)
                    else:
                        event=db.execute("SELECT "+event_columns+" FROM runtime_events e JOIN object_registry o ON o.instance_id=e.instance_id AND o.id=e.id AND o.kind='runtime_events' WHERE e.instance_id=? AND e.id=? AND e.source='tl.source.snapshot'",(self.instance_id,rev['id'])).fetchone()
                    if event is None or event['event_type']!='source.observed_snapshot':raise Conflict('snapshot revision has no real immutable event')
                    snapshot=validate_snapshot(self.read_artifact(event['payload_artifact_id']))
                    if event['payload_hash']!=contract.fingerprint(snapshot) or snapshot['origin']['id']!=value['id'] or snapshot['origin']['kind']!=value['kind'] or snapshot['origin']['instance_id']!=self.instance_id or snapshot['snapshot_revision']!=revision['value'] or snapshot['digest']['hex']!=contract.fingerprint(snapshot['value']):raise Conflict('snapshot revision owner/payload mapping mismatch')
            if rev is None or (version_owner is not None and rev['object_id'] != version_owner):
                raise Conflict('registered revision number/owner mismatch')
        elif version_owner is not None:
            raise ContractError('version owner check requires known revision')
        remember_reference(self.__store,cache_key)
        return value

    def read_artifact(self, key, type_name=None, *, fresh=False):
        if type(fresh)is not bool:raise ContractError('fresh artifact read flag must be boolean')
        types.string(key)
        columns=_validation_columns('instance_id,id,hash,size,media_type,storage_ref','*')
        from digital_life.infrastructure.persistence.tool_learning_readset import facts,can_share_material_facts
        if not fresh and type(self)is ToolLearningStore and can_share_material_facts(self.__store):
            row=next(iter(facts(self.__store,'artifact_location',key)),None)
        else:
            row = self.__store.db.execute('SELECT '+columns+' FROM artifacts WHERE instance_id=? AND id=?',
                                          (self.instance_id,key)).fetchone()
        if row is None:
            raise ContractError('artifact is not registered in this instance')
        location = row['storage_ref']
        if (type(location) is not str or '/' in location or '\\' in location or location in ('','.','..')
                or len(location) != 64 or any(c not in '0123456789abcdef' for c in location)):
            raise ContractError('invalid artifact location')
        from digital_life.infrastructure.persistence.tool_learning_meter import artifact_before,artifact_after,artifact_failed,cached_artifact,remember_artifact
        cached,raw=cached_artifact(row,fresh=fresh)
        if fresh:cached=False;raw=None
        if not cached:
            artifact_before(row['size'])
            folder = self.__store.root / 'blobs'
            try:
                directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    fd = os.open(location, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                    with os.fdopen(fd,'rb') as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ContractError('artifact is not a regular file')
                        raw = stream.read()
                finally:os.close(directory)
            except OSError as exc:
                artifact_failed();raise ContractError('artifact bytes unavailable or unsafe') from exc
            artifact_after(len(raw))
            if len(raw)!=row['size'] or hashlib.sha256(raw).hexdigest()!=row['hash'] or location!=row['hash']:raise ContractError('artifact size/digest mismatch')
            remember_artifact(row,raw,fresh=fresh)
        if type_name is not None and row['media_type'] != 'application/json':
            raise ContractError('named structured artifact must be JSON')
        value = contract.loads(raw,type_name) if row['media_type']=='application/json' else raw
        return value

    def __static_token(self,token):
        obj=token['object'];kind=obj['kind']
        if kind not in STATIC_TOKEN_PAYLOADS and kind!='policy_versions':return False
        if token['revision']!=0:return False
        # A known Ref is always a real registry assertion, even when nested in
        # a technical token. Existing native/snapshot registrations never fall
        # back to an unregistered static interpretation.
        self.validate_ref(obj)
        db=self.__store.db
        if has_registered_revision(self.__store,obj['id']):return False
        row=self.__store.row(kind,obj['id'])
        if kind=='policy_versions':
            if type(contract.loads(row['scope'])) is not dict or row['mode'] not in ('open','authorization'):raise ContractError('static policy inline payload is invalid')
            self.validate_ref({'instance_id':self.instance_id,'id':row['authority'],'kind':'social_actors','revision':{'status':'not_applicable','value':None,'reason_code':'none','reason':'technical owner identity','basis_refs':[]}})
            return True
        column,digest=STATIC_TOKEN_PAYLOADS[kind];key=row[column]
        if key is None:raise ContractError('static payload row lacks its actual immutable artifact')
        material=self.__store.row('artifacts',key);value=self.read_artifact(key)
        if digest is not None and row[digest]!=material['hash']:raise Conflict('static row payload digest/owner mapping differs')
        if kind in ('configuration_versions','model_versions'):
            if type(value) is not dict or type(value.get('model')) is not dict or type(contract.loads(row['compatibility'])) is not dict:raise ContractError('static configuration/model payload mapping invalid')
        if kind=='tl_product':
            contract.validate('Product',value)
            if value['product_id']!=row['id'] or value['work_ref']['id']!=row['work_id'] or value['product_type']!=row['product_type']:raise Conflict('static Product payload mapping differs')
        if kind=='thought_results' and row['parsed_artifact_id'] is not None:self.read_artifact(row['parsed_artifact_id'])
        return True

    def __put_artifact(self, value, type_name=None):
        if type_name is not None: contract.validate(type_name,value)
        else: types.json_value(value)
        key = self.__store.artifact(value)
        self.read_artifact(key,type_name)
        return key

    def __read_command(self, operation, key, fingerprint):
        row = self.__store.db.execute('SELECT * FROM tl_command WHERE instance_id=? AND operation=? AND idempotency_key=?',
                                      (self.instance_id,operation,key)).fetchone()
        if row is None: return {'state':'absent','result':None}
        if row['fingerprint'] != fingerprint: raise Conflict('idempotency key has different original fingerprint')
        if row['state']=='committed':
            result = self.read_artifact(row['result_artifact_id'],'Response')
            if result['command_id'] != row['id'] or result['operation'] != operation:
                raise ContractError('stored command response mapping mismatch')
        else: result = None
        return {'state':row['state'],'command_id':row['id'],'result':result}

    def lookup_command(self, entry, operation, envelope):
        contract.validate_request(operation,envelope)
        if envelope['instance_id']!=self.instance_id:raise Forbidden('command belongs to another instance')
        request=contract.loads(dumps(envelope))
        self.__grant(entry,operation,request,'reconcile')
        found=self.__read_command(operation,request['idempotency_key'],command_fingerprint(request))
        if found['state']=='committed':
            found['result']=self.__project(entry,operation,request,found['result'],'reconcile')
        return found

    def execute(self, entry, operation, envelope, callback):
        if operation=='recall': raise Forbidden('read/audit recall is not a generic write command')
        contract.validate_request(operation,envelope)
        if envelope['instance_id'] != self.instance_id: raise Forbidden('command belongs to another instance')
        # Snapshot input: callbacks and authorization code cannot mutate the command being fingerprinted.
        request = contract.loads(dumps(envelope))
        digest = command_fingerprint(request)
        if self.__active or self.__store.db.in_transaction or self.__store.depth:
            raise Conflict('owned command requires an independent outer transaction')
        self.__grant(entry,operation,request,'preflight')
        db=self.__store.db; committing=False; begun=False; session=None;blob_frame=False;finished=False;uncertain_commit=False;rolled_back=False
        try:
            from digital_life.infrastructure.persistence.tool_learning_readset import checkpoint
            checkpoint(self.__store)
            db.execute('BEGIN IMMEDIATE'); begun=True; self.__active=True
            self.__store._blob_frames.append([]);blob_frame=True
            self.__pending=set();self.__context=(entry,operation,request)
            grant=self.__grant(entry,operation,request,'begin')
            prior=self.__read_command(operation,request['idempotency_key'],digest)
            if prior['state']!='absent':
                if prior['state']!='committed': raise CommitUnknown('existing noncommitted command requires owner reconciliation')
                self.__grant(entry,operation,request,'replay')
                projected=self.__project(entry,operation,request,prior['result'],'replay')
                committing=True; self._commit();finished=True; return projected
            principal_id=self.__put_artifact(request['principal'],'Principal')
            work=request['work_ref']['value']['id'] if request['work_ref']['status']=='known' else None
            if work is not None:self.validate_ref(request['work_ref']['value'],expected_kind='tl_work')
            db.execute('INSERT INTO tl_command(id,instance_id,operation,idempotency_key,fingerprint,principal_artifact_id,work_id,state,row_revision) VALUES(?,?,?,?,?,?,?,?,0)',
                       (request['command_id'],self.instance_id,operation,request['idempotency_key'],digest,principal_id,work,'pending'))
            session=OwnedTransaction(self,grant)
            result=callback(session)
            contract.validate('Response',result)
            if result['command_id']!=request['command_id'] or result['operation']!=operation or result['owner']!=grant.owner:
                raise ContractError('response does not belong to command/owner')
            result_id=self.__put_artifact(result,'Response')
            self.__validate_pending()
            self.__walk_refs(result)
            renewed=self.__grant(entry,operation,request,'commit')
            if renewed != grant: raise Forbidden('storage authority changed during transaction')
            db.execute("UPDATE tl_command SET state='committed',result_artifact_id=?,row_revision=1 WHERE id=? AND instance_id=? AND state='pending' AND row_revision=0",
                       (result_id,request['command_id'],self.instance_id))
            projected=self.__project(entry,operation,request,result,'commit')
            committing=True; self._commit();finished=True
            return projected
        except BaseException as exc:
            if begun and db.in_transaction:
                try:db.execute('ROLLBACK');rolled_back=True
                except sqlite3.Error as rollback_error:
                    uncertain_commit=True
                    raise CommitUnknown('rollback outcome unknown; reconcile original command') from rollback_error
            elif begun and committing:
                uncertain_commit=True
                raise CommitUnknown('commit acknowledgement unknown; reconcile original command') from exc
            raise
        finally:
            if begun:
                self.__active=False
                self.__pending=set();self.__context=None
            if session is not None:session._close()
            # Only this adapter's acknowledged COMMIT/ROLLBACK can rebase a
            # shared phase. Never infer ownership of an arbitrary raw COMMIT.
            # Notify before blob cleanup; its own failure must not skip cleanup
            # or replace the original business/unknown-outcome exception.
            try:
                if begun:
                    from digital_life.infrastructure.persistence.tool_learning_readset import transaction_ended,abandon_transaction_boundary
                    import sys
                    if uncertain_commit or not(finished or rolled_back):abandon_transaction_boundary(self.__store)
                    elif sys.exc_info()[0] is None:transaction_ended(self.__store,rolled_back=rolled_back)
                    else:
                        try:transaction_ended(self.__store,rolled_back=rolled_back)
                        except BaseException:abandon_transaction_boundary(self.__store)
            finally:
                if blob_frame:
                    created=self.__store._blob_frames.pop()
                    if not uncertain_commit:
                        if self.__store._blob_frames:self.__store._blob_frames[-1].extend(created)
                        else:self.__store._discard_unregistered_blobs(created)
                if begun:
                    import sys
                    if sys.exc_info()[0] is None:checkpoint(self.__store)

    def __project(self, entry, operation, request, result, stage):
        projected=self.__authority.project_response(entry,operation,contract.loads(dumps(request)),
            contract.loads(dumps(result)),self.instance_id,stage)
        contract.validate('Response',projected)
        if any(projected[key]!=result[key] for key in ('command_id','operation','owner')):
            raise Forbidden('projection changed command identity')
        return contract.loads(dumps(projected))

    def _commit(self):
        """Separate mechanical boundary permits deterministic fault injection in tests."""
        self.__store.db.execute('COMMIT')

    def _insert(self, grant, table, values):
        self.__check_access(grant,table)
        fields=dict(values)
        if set(fields)-self.__columns[table] or 'instance_id' in fields or 'schema_revision' in fields:
            raise ContractError('unknown or reserved storage fields')
        fields.setdefault('id',identifier());fields['instance_id']=self.instance_id
        if table=='tl_handoff' and (grant.owner!='M03' or fields.get('state')!='pending'):
            raise Forbidden('only M03 creates pending representation obligations')
        if table=='tl_group' and (grant.owner!='M03' or fields.get('state')!='pending'):
            raise Forbidden('only M03 creates fixed pending groups')
        self.__check_scalars(table,fields)
        self.__check_artifacts(table,fields)
        keys=tuple(fields)
        self.__store.db.execute('INSERT INTO '+table+' ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',tuple(fields[k] for k in keys))
        self.__pending.add((table,fields['id']))
        return fields['id']

    def __check_access(self, grant, table):
        if not self.__active:raise Forbidden('owned transaction has ended')
        if table not in OWNERS or table not in grant.tables or grant.owner not in OWNERS[table]:
            raise Forbidden('table is outside trusted owner grant')

    def __check_scalars(self, table, fields):
        for key,value in fields.items():
            if value is None:continue  # SQL nullability remains authoritative.
            if self.__types[table][key]=='INTEGER':types.integer(value)
            else:types.string(value,nonempty=False)

    def __check_artifacts(self, table, fields):
        for key,value in fields.items():
            if key.endswith('_artifact_id') and value is not None:
                self.read_artifact(value,ARTIFACT_TYPES.get((table,key)))
    def __check_reference(self, value, expected_kind=None, version_owner=None):
        contract.validate('Ref',value)
        if value['instance_id']!=self.instance_id:
            if expected_kind is not None or version_owner is not None:
                raise Forbidden('external source cannot bind a local row')
            entry,operation,request=self.__context
            verified=self.__authority.verify_external_ref(entry,operation,contract.loads(dumps(request)),
                contract.loads(dumps(value)),self.instance_id)
            if verified is not None:raise Forbidden('external verifier must attest by successful return, not a boolean')
            return value
        return self.validate_ref(value,expected_kind=expected_kind,version_owner=version_owner)

    def __walk_refs(self, value):
        if type(value) is dict:
            if {'source_kind','original_result','receipt','artifact','digest','locator'} <= set(value):
                # Binding a source checksum is a byte fact, not a scientific support claim.
                artifact=value['artifact']
                if artifact['instance_id']==self.instance_id:
                    self.__check_reference(artifact,expected_kind='artifacts')
                    self.read_artifact(artifact['id'])
                    material=self.__store.db.execute('SELECT hash,media_type FROM artifacts WHERE instance_id=? AND id=?',(self.instance_id,artifact['id'])).fetchone()
                    if material is None or material['hash']!=value['digest']['hex'] or material['media_type']!=value['media_type']:
                        raise ContractError('evidence artifact digest/media mapping mismatch')
                if value['view']['status']=='known' and value['view_digest']['status']=='known':
                    view=value['view']['value']
                    if view['instance_id']==self.instance_id and view['kind']=='artifacts':
                        self.read_artifact(view['id'])
                        digest=self.__store.db.execute('SELECT hash FROM artifacts WHERE instance_id=? AND id=?',(self.instance_id,view['id'])).fetchone()
                        if digest is None or digest['hash']!=value['view_digest']['value']['hex']:raise ContractError('bound view digest mismatch')
            if set(value)=={'instance_id','id','kind','revision'}:
                self.__check_reference(value)
                self.__walk_refs(value['revision']['basis_refs'])
                return
            if set(value)=={'object','revision','epoch'}:
                contract.validate('VersionToken',value)
                obj=contract.loads(dumps(value['object']))
                if obj['kind']=='tl_handoff':
                    # Mutable control CAS is not an immutable content revision.
                    # Ref.revision itself remains strict registry semantics.
                    self.__check_reference(obj)
                    control=self.__store.db.execute('SELECT row_revision,lease_generation FROM tl_handoff WHERE instance_id=? AND id=?',(self.instance_id,obj['id'])).fetchone()
                    if control is None or value['revision']!=control['row_revision'] or value['epoch']!=control['lease_generation']:
                        raise Conflict('handoff control revision/generation mismatch')
                elif obj['kind']=='tl_propagation':
                    # F2 CAS/generation names mutable obligation control, not
                    # an immutable content revision. Ref.known remains strict.
                    self.__check_reference(obj)
                    control=self.__store.db.execute('SELECT row_revision,generation FROM tl_propagation WHERE instance_id=? AND id=?',(self.instance_id,obj['id'])).fetchone()
                    if control is None or value['revision']!=control['row_revision'] or value['epoch']!=control['generation']:
                        raise Conflict('propagation control revision/generation mismatch')
                elif self.__static_token(value):pass
                else:
                    obj['revision']={'status':'known','value':value['revision'],'reason_code':'none','reason':'','basis_refs':[]}
                    self.__check_reference(obj)
                self.__walk_refs(value['object']['revision']['basis_refs'])
                return
            for child in value.values():self.__walk_refs(child)
        elif type(value) is list:
            for child in value:self.__walk_refs(child)

    def __validate_pending(self):
        for table,key in self.__pending:
            row=self.__store.db.execute('SELECT * FROM '+table+' WHERE instance_id=? AND id=?',(self.instance_id,key)).fetchone()
            if row is None:raise ContractError('owned row disappeared before commit')
            row=dict(row);self.__check_artifacts(table,row)
            for field in row:
                type_name=ARTIFACT_TYPES.get((table,field))
                if type_name and row[field] is not None:self.__walk_refs(self.read_artifact(row[field],type_name))
            self.__check_mapping(table,row)

    def __check_mapping(self, table, row):
        payload_key={'tl_product':'payload_artifact_id','tl_decision':'decision_artifact_id',
                     'tl_representation':'payload_artifact_id','tl_recall_item':'payload_artifact_id',
                     'tl_effect':'payload_artifact_id'}.get(table)
        if payload_key is None:return
        value=self.read_artifact(row[payload_key],ARTIFACT_TYPES[(table,payload_key)])
        def equal(actual,expected):
            if actual!=expected:raise ContractError('artifact and authoritative row mapping mismatch')
        def binding(reference,key,kind):
            self.__check_reference(reference,expected_kind=kind);equal(reference['id'],key)
        def optional_binding(slot,key,kind):
            if key is None:
                if slot['status']=='known':raise ContractError('known Ref cannot be discarded from a persisted association')
            else:
                if slot['status']!='known':raise ContractError('persisted association requires known Ref')
                binding(slot['value'],key,kind)
        if table=='tl_product':
            for field,target in [('product_id','id'),('product_type','product_type'),('instance_id','instance_id')]:equal(value[field],row[target])
            binding(value['work_ref'],row['work_id'],'tl_work')
            equal(value['processing_identity']['hex'],row['processing_identity'])
            equal(value['producer'],self.__context[2]['principal'])
        elif table=='tl_decision':
            for field in ('id','review_round','operation','created_at'):equal(value[field],row[field])
            binding(value['work_ref'],row['work_id'],'tl_work');binding(value['proposal_ref'],row['proposal_id'],'tl_product')
            equal(value['actor'],self.__context[2]['principal'])
            binding(value['policy_ref'],row['policy_ref_id'],value['policy_ref']['kind'])
            optional_binding(value['revision_ref'],row['content_revision_id'],'tl_content_revision')
            if row['content_revision_id'] is not None:
                rev=self.__store.db.execute('SELECT content_id FROM tl_content_revision WHERE instance_id=? AND id=?',(self.instance_id,row['content_revision_id'])).fetchone()
                if rev is None:raise ContractError('decision revision is unavailable')
                optional_binding(value['content_ref'],rev['content_id'],'tl_content')
            elif value['content_ref']['status']=='known':self.__check_reference(value['content_ref']['value'],expected_kind='tl_content')
            for ref in value['handoff_refs']:
                self.__check_reference(ref,expected_kind='tl_handoff')
                handoff=self.__store.db.execute('SELECT h.decision_id,h.content_revision_id,h.work_id,d.work_id AS owning_work,r.decision_id AS revision_decision FROM tl_handoff h JOIN tl_decision d ON d.instance_id=h.instance_id AND d.id=h.decision_id JOIN tl_content_revision r ON r.instance_id=h.instance_id AND r.id=h.content_revision_id WHERE h.instance_id=? AND h.id=?',(self.instance_id,ref['id'])).fetchone()
                if handoff is None or handoff['content_revision_id']!=row['content_revision_id'] or handoff['work_id']!=handoff['owning_work']:
                    raise ContractError('decision handoff mapping mismatch')
                if row['operation']=='reuse':
                    if handoff['decision_id']!=handoff['revision_decision']:raise ContractError('reuse must reference original handoff')
                elif handoff['decision_id']!=row['id'] or handoff['work_id']!=row['work_id']:
                    raise ContractError('new obligation must belong to accepting decision')
        elif table=='tl_representation':
            for field in ('id','representation_no','format_version'):equal(value[field],row[field])
            binding(value['series_ref'],row['series_id'],'tl_representation_head')
            binding(value['decision_ref'],row['decision_id'],'tl_decision')
            binding(value['body_artifact'],row['body_artifact_id'],'artifacts')
            equal(value['body_digest']['hex'],row['body_digest'])
            optional_binding(value['group'],row['group_id'],'tl_group')
            rev=self.__store.db.execute('SELECT content_id,revision_no FROM tl_content_revision WHERE instance_id=? AND id=?',(self.instance_id,row['content_revision_id'])).fetchone()
            if rev is None:raise ContractError('representation content revision unavailable')
            binding(value['content_ref'],rev['content_id'],'tl_content')
            binding(value['content_revision']['object'],rev['content_id'],'tl_content')
            equal(value['content_revision']['revision'],rev['revision_no'])
            artifact=self.__store.db.execute('SELECT hash FROM artifacts WHERE instance_id=? AND id=?',(self.instance_id,row['body_artifact_id'])).fetchone()
            self.read_artifact(row['body_artifact_id'])
            if artifact is None:raise ContractError('representation body missing')
            equal(artifact['hash'],row['body_digest'])
        elif table=='tl_effect':
            equal(value['measurement_state'],row['state'])
            product=self.__store.db.execute('SELECT work_id,product_type,payload_artifact_id FROM tl_product WHERE instance_id=? AND id=?',(self.instance_id,row['product_id'])).fetchone()
            if product is None or product['work_id']!=row['work_id'] or product['product_type']!='EffectAssessment':raise ContractError('effect product/work mismatch')
            original=self.read_artifact(product['payload_artifact_id'],'Product')
            equal(original['body'],value)
            entry,operation,request=self.__context
            resolved=self.__authority.verify_metric_contract(entry,operation,contract.loads(dumps(request)),row['metric_contract'],contract.loads(dumps(value['metric_definition'])),self.instance_id)
            if resolved is not None:raise Forbidden('metric-contract resolver must attest by successful return, not a boolean')
            optional_binding(value['measurement_ref'],row['measurement_ref_id'],value['measurement_ref']['value']['kind'] if value['measurement_ref']['status']=='known' else '')
        elif table=='tl_recall_item':
            equal(value['id'],row['id']);equal(value['kind'],row['kind'])
            if value['representation_ref']['status']=='known':
                binding(value['representation_ref']['value'],row['target_ref_id'],'tl_representation')
                actual=self.__store.db.execute('SELECT p.series_id,p.representation_no,p.content_revision_id,p.decision_id,r.content_id,r.revision_no FROM tl_representation p JOIN tl_content_revision r ON r.instance_id=p.instance_id AND r.id=p.content_revision_id WHERE p.instance_id=? AND p.id=?',(self.instance_id,row['target_ref_id'])).fetchone()
                if actual is None:raise ContractError('recall representation unavailable')
                optional_binding(value['content_ref'],actual['content_id'],'tl_content')
                optional_binding(value['decision_ref'],actual['decision_id'],'tl_decision')
                for name,kind,key,number in [('content_revision','tl_content',actual['content_id'],actual['revision_no']),('representation_revision','tl_representation_head',actual['series_id'],actual['representation_no'])]:
                    if value[name]['status']!='known':raise ContractError('recall representation requires version bindings')
                    token=value[name]['value'];binding(token['object'],key,kind);equal(token['revision'],number)
            elif value['memory_revision']['status']=='known':
                version=value['memory_revision']['value']
                self.__check_reference(version['object'],expected_kind='memory_items')
                registered=self.__store.db.execute('SELECT object_id,revision_no FROM object_revision_registry WHERE instance_id=? AND id=?',(self.instance_id,row['target_ref_id'])).fetchone()
                if registered is None:raise ContractError('recall memory revision unavailable')
                equal(registered['object_id'],version['object']['id']);equal(registered['revision_no'],version['revision'])
            else:raise ContractError('recall target lacks actual memory/representation binding')

    def _cas(self, grant, table, key, expected_revision, changes):
        self.__check_access(grant,table); types.string(key); types.integer(expected_revision)
        if table not in MUTABLE or not changes or set(changes)-MUTABLE[table]:raise Forbidden('CAS fields are not mutable for this table')
        if table in ('tl_handoff','tl_group') and grant.owner!='M04':raise Forbidden('only M04 updates representation obligations/groups')
        self.__check_scalars(table,changes)
        self.__check_artifacts(table,changes)
        values=dict(changes);values['row_revision']=expected_revision+1
        cursor=self.__store.db.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in values)+' WHERE instance_id=? AND id=? AND row_revision=?',
                                       (*values.values(),self.instance_id,key,expected_revision))
        if cursor.rowcount!=1:raise Conflict('CAS revision is stale or object is absent')
        self.__pending.add((table,key))
        return expected_revision+1

    def _representation_state(self,grant,key,expected_state,state):
        self.__check_access(grant,'tl_representation')
        if grant.owner!='M04':raise Forbidden('only M04 owns representation state')
        types.enum(expected_state,('ready','superseded'));types.enum(state,('superseded','withdrawn'))
        changed=self.__store.db.execute('UPDATE tl_representation SET state=? WHERE instance_id=? AND id=? AND state=?',(state,self.instance_id,key,expected_state)).rowcount
        if changed!=1:raise Conflict('representation state is stale')
        self.__pending.add(('tl_representation',key))

    def _artifact(self,grant,value,type_name):
        if not self.__active:raise Forbidden('owned transaction has ended')
        return self.__put_artifact(value,type_name)

    def _learning_activity(self,grant,*,activity_id,account_id,work_id,source_activity,
                           producer,source,budget_document,deadline):
        """C0-only old-table assembly, never a general-purpose SQL escape hatch."""
        self.__check_access(grant,'tl_work')
        entry,operation,request=self.__context
        if operation!='admit_observation' or grant.owner!='M14':
            raise Forbidden('learning activity assembly is restricted to C0/M14')
        for key in (activity_id,account_id,work_id):contract.validate('ID',key)
        if producer!=request['principal'] or source_activity!=request['payload']['source_activity'] or source!=request['payload']['source']:
            raise Forbidden('C0 producer/source differs from authenticated command')
        self.validate_ref(source_activity,expected_kind='activities')
        self.validate_ref(producer['actor'])
        contract.validate('UTC',deadline)
        types.obj(budget_document,('contract','budget','source_budget','ledger'))
        if budget_document['contract']!='TL-WORK-BUDGET-1':raise ContractError('unknown work budget document')
        budget=budget_document['budget'];contract.validate('Budget',budget)
        if budget['account_ref']['instance_id']!=self.instance_id or budget['account_ref']['id']!=account_id or budget['account_ref']['kind']!='activity_budget_accounts' or budget['deadline']!=deadline:
            raise ContractError('new activity budget binding mismatch')
        if budget_document['source_budget']!=request['budget']:raise ContractError('C0 must preserve original source budget')
        parent=self.__store.row('activities',source_activity['id'])
        # The immutable trigger retains the actual service producer and typed origin.
        trigger=self.__put_artifact({'contract':'TL-LEARNING-TRIGGER-1','producer':producer,
            'source':source,'source_activity':source_activity,'work_id':work_id})
        channel=self.__store.insert('perception_channels',kind='internal',capabilities=['tool-learning-trigger'],verification_method='authenticated-service',state='available')
        actor=self.__store.db.execute('SELECT id FROM social_actors WHERE instance_id=? AND id=?',(self.instance_id,producer['actor']['id'])).fetchone()
        signal=self.__store.insert('perception_signals',channel_id=channel,source_actor_id=actor['id'] if actor else None,
            external_id='tl-learning:'+work_id,artifact_id=trigger,received_at=utc())
        self.__store.insert('activities',id=activity_id,trigger_event_id=signal,state='pending',budget_json=budget_document,
            release_id=parent['release_id'],publication_state='ready',deadline=deadline)
        from datetime import datetime
        milliseconds=max(0,int((datetime.fromisoformat(deadline.replace('Z','+00:00'))-datetime.fromisoformat(utc().replace('Z','+00:00'))).total_seconds()*1000))
        self.__store.insert('activity_budget_accounts',id=account_id,activity_id=activity_id,
            token_limit=budget['max_input_tokens']+budget['max_output_tokens'],tool_call_limit=budget['max_tool_calls'],
            attempt_limit=budget['max_attempts'],time_limit_ms=milliseconds)
        return {'activity_id':activity_id,'account_id':account_id,'time_limit_ms':milliseconds}


class OwnedTransaction:
    """Narrow service port: no raw SQL, connection, Store, or authorization flag."""
    def __init__(self, adapter, grant):
        self.__adapter=adapter;self.__grant=grant;self.__open=True
    def _close(self):self.__open=False
    def __check(self):
        if not self.__open:raise Forbidden('owned transaction has ended')
    def insert(self,table,**fields):
        self.__check();return self.__adapter._insert(self.__grant,table,fields)
    def cas_update(self,table,key,expected_revision,**changes):
        self.__check();return self.__adapter._cas(self.__grant,table,key,expected_revision,changes)
    def update_representation_state(self,key,state,expected_state='ready'):
        self.__check();return self.__adapter._representation_state(self.__grant,key,expected_state,state)
    def put_artifact(self,value,type_name=None):
        self.__check();return self.__adapter._artifact(self.__grant,value,type_name)
    def create_learning_activity(self,**fields):
        self.__check();return self.__adapter._learning_activity(self.__grant,**fields)
