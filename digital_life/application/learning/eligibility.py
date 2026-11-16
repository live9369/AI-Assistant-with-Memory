"""IM06 durable dependency and qualification ports. No production dispatch wiring."""
from copy import deepcopy
from contextlib import contextmanager
from threading import get_ident
import json
from digital_life.domain.contracts import ContractError, Conflict, Forbidden, identifier, dumps, utc
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore,has_registered_revision
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate

# Stable provenance for narrowly prepared dependency binding data.
_DEPENDENCY_BINDING_VALIDATOR=ToolLearningStore.validate_ref


def scope_key(scope):
    return t.scope_fingerprint(scope)


def scope_overlap(left,right):
    """Only exact equality proves overlap locally; unknown is never disjoint."""
    return True if scope_key(left)==scope_key(right) else None


def same_ref(left,right):
    return all(left[k]==right[k] for k in ('instance_id','id','kind'))


def slot(value=None):
    return {'status':'known' if value is not None else 'not_applicable','value':value,
            'reason_code':'none','reason':'' if value is not None else 'no technical association','basis_refs':[]}


def ref(store,key,kind=None):
    if kind is None:
        from digital_life.infrastructure.persistence.tool_learning_readset import facts
        row=next(iter(facts(store,'source_kind',key)),None)
        if row is None:raise ContractError('unregistered local object')
        kind=row[0]
    return {'instance_id':store.instance_id,'id':key,'kind':kind,'revision':slot()}


def insert(store,table,**fields):
    """Private fixed-table writer, not an exported generic service capability."""
    if table not in ('tl_dependency','tl_input_dependency'):raise Forbidden('internal table not allowed')
    fields.setdefault('id',identifier());fields['instance_id']=store.instance_id
    store.db.execute('INSERT INTO '+table+' ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',tuple(fields.values()))
    return fields['id']


class EligibilityAuthority:
    def verify(self,entry,principal,token,scope,purpose,recipient,stage):
        raise Forbidden('current source, permission and control authority is not configured')
    def verify_version(self,entry,principal,token,stage):
        raise Forbidden('current source version resolver is not configured')
    def verify_registration(self,entry,principal,context,stage):
        raise Forbidden('consumer and input registration authority is not configured')
    def verify_callback(self,entry,principal,context,stage):
        raise Forbidden('request activity and final callback authority is not configured')
    def barrier_applies(self,entry,principal,barrier,payload,scope,purpose,recipient):
        return None
    def overlap(self,entry,principal,left,right):
        return scope_overlap(left,right)


class ToolLearningEligibility:
    def __init__(self,store,authority=None,max_nodes=256,max_rows=1024):
        self.s=store;self.authority=EligibilityAuthority() if authority is None else authority
        if not isinstance(self.authority,EligibilityAuthority):raise ContractError('trusted EligibilityAuthority required')
        t.integer(max_nodes,1,100000);t.integer(max_rows,1,100000);self.max_nodes=max_nodes;self.max_rows=max_rows;self.artifacts=ToolLearningStore(store)

    def _principal(self,principal):
        c.validate('Principal',principal)
        for key in ('actor','recipient','authorization'):self.artifacts.validate_ref(principal[key])

    def validate_token(self,entry,principal,token,stage):
        c.validate('VersionToken',token);self.artifacts.validate_ref(token['object'])
        obj=token['object']
        if has_registered_revision(self.s,obj['id']):
            known=deepcopy(obj);known['revision']=slot(token['revision']);self.artifacts.validate_ref(known)
        result=self.authority.verify_version(entry,deepcopy(principal),deepcopy(token),stage)
        if result is not None:raise Forbidden('version resolver must attest by successful return, not a boolean')

    def current_epoch(self,source,scope):
        self.artifacts.validate_ref(source);key=scope_key(scope)
        from digital_life.infrastructure.persistence.tool_learning_readset import facts
        row=next(iter(facts(self.s,'source_epoch',source['id'],key)),None)
        return row[0] if row else 0

    def overlaps(self,entry,principal,left,right):
        result=self.authority.overlap(entry,deepcopy(principal),deepcopy(left),deepcopy(right))
        if result is not None and type(result) is not bool:raise ContractError('overlap must be true/false/unknown')
        return result is not False

    def closure(self,source_id):
        """Durable downstream closure; all relation axes remain recorded, not equated."""
        seen={source_id};queue=[source_id];scanned=0
        while queue:
            key=queue.pop(0)
            for row in self.s.db.execute('SELECT consumer_ref_id FROM tl_dependency WHERE instance_id=? AND source_ref_id=? ORDER BY id LIMIT ?',(self.s.instance_id,key,self.max_rows-scanned+1)):
                scanned+=1
                if scanned>self.max_rows:raise Forbidden('dependency row scan limit exceeded')
                if row[0] not in seen:
                    if len(seen)>=self.max_nodes:raise Forbidden('dependency closure exceeds declared scan limit')
                    seen.add(row[0]);queue.append(row[0])
        return seen

    def _metadata(self,row,include_scope_key=False):
        from digital_life.infrastructure.persistence.tool_learning_meter import cached_metadata
        from digital_life.infrastructure.persistence.tool_learning_readset import track_artifact,current_readset
        identity=track_artifact(self.s,row['metadata_artifact_id'])
        phase=current_readset(self.s)
        from digital_life.infrastructure.persistence.tool_learning_meter import _ACTIVE
        active=_ACTIVE.get();binding=False
        if (phase is not None and phase.reusable and phase.monitor is not None
                and active is not None and getattr(active,'phase_store',None)is self.s
                and type(self.artifacts)is ToolLearningStore
                and phase.monitor.known_read_environment()):
            validator=self.artifacts.validate_ref
            binding=(getattr(validator,'__func__',None)is _DEPENDENCY_BINDING_VALIDATOR
                     and getattr(validator,'__self__',None)is self.artifacts
                     and self.artifacts._ToolLearningStore__store is self.s)
        # An unknown validator cannot populate this binding namespace, even
        # if a later call restores the original validator on the same phase.
        cache_key=('TL-DEPENDENCY-BINDING-1'if binding else'TL-DEPENDENCY-1',tuple(sorted(dict(row).items())),identity)
        prepared=None if phase is None else phase.prepared_metadata(cache_key)
        if binding and prepared is not None:
            # Previously checked row/identity/revision binding data only.
            # Root/node tokens and live source authorization remain separate.
            meta=json.loads(prepared[0])
            return (meta,prepared[1])if include_scope_key else meta
        # Untrusted/standalone paths still execute the original Ref/projection
        # checks. Parsed JSON alone never implies a checked binding.
        prior=cached_metadata(cache_key)
        meta=json.loads(prepared[0])if prepared is not None else prior
        if meta is None:
            meta=self.artifacts.read_artifact(row['metadata_artifact_id'])
            t.obj(meta,('contract','consumer','dependency','field_path','scope'))
            if meta['contract']!='TL-DEPENDENCY-1':raise ContractError('dependency metadata unavailable')
            c.validate('Dependency',meta['dependency']);c.validate('Scope',meta['scope'])
            dep=meta['dependency']
            if not same_ref(dep['target'],dep['expected']['object']):raise ContractError('dependency expected object mismatch')
            if (meta['consumer']['id']!=row['consumer_ref_id'] or dep['target']['id']!=row['source_ref_id'] or
                dep['relation']!=row['relation'] or dep['consumer_purpose']!=row['purpose'] or
                dep['expected']['epoch']!=row['expected_epoch'] or meta['field_path']!=row['field_path']):
                raise ContractError('dependency row and immutable metadata differ')
        # A first trusted binding is prepared only after these exact checks.
        # Unknown validators always execute them again on every call.
        self.artifacts.validate_ref(meta['consumer']);self.artifacts.validate_ref(meta['dependency']['target'])
        dep=meta['dependency']
        expected=dep['expected']
        from digital_life.infrastructure.persistence.tool_learning_readset import facts
        registered=next(iter(facts(self.s,'selected_revision',row['source_ref_id'],expected['revision'])),None)
        if registered is not None and row['source_revision_id']!=registered[0]:raise ContractError('dependency revision projection mismatch')
        if row['source_revision_id'] is not None:
            actual=next(iter(facts(self.s,'revision_owner',row['source_revision_id'])),None)
            if actual is None or actual['object_id']!=row['source_ref_id'] or actual['revision_no']!=expected['revision']:
                raise ContractError('dependency projected revision has wrong owner or number')
        if prior is None:cached_metadata(cache_key,meta)
        selected_scope_key=prepared[1]if prepared is not None else scope_key(meta['scope'])
        if phase is not None:phase.remember_prepared_metadata(cache_key,dumps(meta),selected_scope_key)
        return (meta,selected_scope_key)if include_scope_key else meta

    def _upstream(self,token,scope,scan_budget):
        from digital_life.infrastructure.persistence.tool_learning_readset import current_readset,checkpoint
        phase=current_readset(self.s)
        if phase is None:return self._upstream_current(token,scope,scan_budget)
        direct=not phase.check_depth
        if direct:checkpoint(self.s)
        # Exact JSON types must be checked before serialization: integer keys,
        # tuples, surrogates or cycles must not alias an earlier valid graph.
        t.json_value([token,scope])
        key=dumps([self.s.instance_id,token,scope,self.max_nodes,self.max_rows])
        admitted=phase.graph_admitted(key)
        cached=phase.graph(key)
        if cached is not None and scan_budget['remaining']>=cached[1]:
            # These are prepared source facts, never a qualified verdict. Every
            # consumer still performs all current checks and spends its exact
            # original logical traversal row budget, even on a physical hit.
            values=json.loads(cached[0])
            result=[(row[0],row[1],row[2],tuple(row[3]))for row in values]
            scan_budget['remaining']-=cached[1]
            stats=getattr(self.s,'_graph_material_stats',None)
            if stats is not None:stats['used']+=1
            if direct:checkpoint(self.s)
            return result
        initial=scan_budget['remaining'];generation=phase.generation
        result=self._upstream_current(token,scope,scan_budget)
        if direct:checkpoint(self.s)
        if admitted and phase.generation==generation:
            phase.remember_graph(key,dumps(result),initial-scan_budget['remaining'])
        return result

    def _upstream_current(self,token,scope,scan_budget):
        from digital_life.infrastructure.persistence.tool_learning_readset import facts,dependency_materials
        result=[(token["object"]["id"],deepcopy(scope),None,())];seen=set();index=0;scanned=0
        # A queue item owns its decoded scope, with no authority callback while
        # this graph is built. Carry its already computed key; retain every
        # original item/path and all subsequent live qualification checks.
        scope_keys=[scope_key(result[0][1])]
        while index<len(result):
            key,sc,expected,path=result[index];selected_scope_key=scope_keys[index];index+=1
            selected=token if expected is None else expected
            identity=(key,selected['revision'],selected_scope_key,'delete' in path)
            if identity in seen:continue
            seen.add(identity)
            if len(seen)>self.max_nodes:raise Forbidden('upstream dependency scan limit exceeded')
            consumer=key
            from digital_life.domain.tool_learning_sources import SNAPSHOT_KINDS
            bridge=selected['object']['kind'] in SNAPSHOT_KINDS and next(iter(facts(self.s,'snapshot_bridge',key,selected['revision'])),None)
            if selected['object']['kind'] in ('tl_content','tl_representation_head') or bridge:
                revision=next(iter(facts(self.s,'selected_revision',key,selected['revision'])),None)
                if revision is None:raise ContractError('selected native revision unavailable')
                consumer=revision[0]
            for row in dependency_materials(self.s,consumer,self.max_rows-scanned+1):
                scanned+=1;scan_budget['remaining']-=1
                if scanned>self.max_rows or scan_budget['remaining']<0:raise Forbidden('upstream row scan limit exceeded')
                meta,edge_scope_key=self._metadata(row,True)
                edge=(row['source_ref_id'],meta['scope'],meta['dependency']['expected'],path+(row['relation'],))
                if (edge[0],edge[2]['revision'],edge_scope_key,'delete' in edge[3]) not in seen:
                    result.append(edge);scope_keys.append(edge_scope_key)
                if len(result)>self.max_nodes*2:raise Forbidden('upstream edge scan limit exceeded')
        return result

    def _check(self,entry,principal,token,scope,purpose,recipient,stage,scan_budget=None):
        from digital_life.infrastructure.persistence.tool_learning_readset import checkpoint,current_readset
        checkpoint(self.s)
        phase=current_readset(self.s)
        previous=None
        if phase is not None:
            phase.check_depth+=1;previous=phase.signature_check
        try:
            if phase is not None:phase.signature_check=_mint_signature_check(self,phase)
            result=self._check_current(entry,principal,token,scope,purpose,recipient,stage,scan_budget)
            checkpoint(self.s)
            return result
        finally:
            if phase is not None:phase.signature_check=previous;phase.check_depth-=1

    def _check_current(self,entry,principal,token,scope,purpose,recipient,stage,scan_budget=None):
        if scan_budget is None:scan_budget={'remaining':self.max_rows}
        t.string(entry);self._principal(principal);c.validate('Scope',scope)
        t.enum(purpose,t.PURPOSES);self.artifacts.validate_ref(recipient)
        if purpose!=principal['purpose'] or not same_ref(recipient,principal['recipient']):raise Forbidden('qualification principal purpose/recipient mismatch')
        self.s.assert_execution_allowed()
        self.validate_token(entry,principal,token,stage)
        value=self.authority.verify(entry,deepcopy(principal),deepcopy(token),deepcopy(scope),purpose,deepcopy(recipient),stage)
        if value is not None:raise Forbidden('qualification verifier must not return a boolean')
        self.s.assert_execution_allowed()
        if self.current_epoch(token['object'],scope)!=token['epoch']:raise Conflict('source scope epoch is stale')
        from digital_life.infrastructure.persistence.tool_learning_readset import facts
        barrier_scanned=0
        for key,dep_scope,expected,path in self._upstream(token,scope,scan_budget):
            source=ref(self.s,key)
            if expected is not None and 'delete' not in path:
                self.validate_token(entry,principal,expected,stage)
                result=self.authority.verify(entry,deepcopy(principal),deepcopy(expected),deepcopy(dep_scope),purpose,deepcopy(recipient),stage)
                if result is not None:raise Forbidden('upstream verifier must not return a boolean')
                if self.current_epoch(source,dep_scope)!=expected['epoch']:raise Conflict('upstream source epoch is stale')
            for row in facts(self.s,'source_barriers',key,self.max_rows-barrier_scanned+1):
                barrier_scanned+=1;scan_budget['remaining']-=1
                if barrier_scanned>self.max_rows or scan_budget['remaining']<0:raise Forbidden('barrier row scan limit exceeded')
                if 'delete' in path and row['kind']!='erase':continue
                payload=self.artifacts.read_artifact(row['payload_artifact_id'])
                if not isinstance(payload,dict) or not isinstance(payload.get('purposes'),list):raise ContractError('barrier payload unavailable')
                selected=token if expected is None else expected
                if source['kind'] in ('tl_content','tl_representation_head') and payload['source']['revision']!=selected['revision']:continue
                if payload['purposes'] and purpose not in payload['purposes']:continue
                applies=self.authority.barrier_applies(entry,deepcopy(principal),dict(row,dependency_path=list(path)),deepcopy(payload),deepcopy(dep_scope),purpose,deepcopy(recipient))
                if applies is not None and type(applies) is not bool:raise ContractError('barrier applicability must be true/false/unknown')
                self.s.assert_execution_allowed()
                if applies is False:continue
                affected=self.artifacts.read_artifact(row['scope_artifact_id'],'Scope')
                if self.overlaps(entry,principal,affected,dep_scope):raise Forbidden('active source qualification barrier')
        self.s.assert_execution_allowed()
        return {'qualified':True,'source':deepcopy(token),'scope_key':scope_key(scope),'stage':stage}

    def check(self,entry,principal,token,scope,purpose,recipient,stage='read'):
        principal,token,scope,recipient=deepcopy((principal,token,scope,recipient))
        if self.s.db.in_transaction:raise Conflict('public qualification check requires gate before its own read transaction')
        with dispatch_gate(self.s.root):
            self.s.db.execute('BEGIN')
            try:
                result=self._check(entry,principal,token,scope,purpose,recipient,stage)
                self.s.db.execute('COMMIT');return result
            except BaseException:
                self.s.db.execute('ROLLBACK');raise

    def register_dependency(self,entry,principal,consumer,dependency,field_path,scope):
        principal,consumer,dependency,scope=deepcopy((principal,consumer,dependency,scope))
        c.validate('Dependency',dependency);t.string(field_path)
        if not same_ref(dependency['target'],dependency['expected']['object']):raise ContractError('dependency target and expected source mismatch')
        if dependency['consumer_purpose']!=principal['purpose']:raise Forbidden('dependency purpose mismatch')
        self.artifacts.validate_ref(consumer)
        if self.s.db.in_transaction:raise Conflict('dependency registration requires independent transaction')
        from digital_life.application.learning.runtime_owners import LocalEligibility
        if type(self.authority)is LocalEligibility:
            # Existing rows need no write UoW. Use the same read-transaction
            # pattern as check(), while retaining every begin/commit gate.
            # New registrations and arbitrary authorities keep the write path.
            with dispatch_gate(self.s.root):
                lookup='SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? AND source_ref_id=? AND relation=? AND purpose=? AND field_path=? AND expected_epoch=?'
                args=(self.s.instance_id,consumer['id'],dependency['target']['id'],dependency['relation'],dependency['consumer_purpose'],field_path,dependency['expected']['epoch'])
                if self.s.db.execute(lookup,args).fetchone() is not None:
                    before=self.s.db.total_changes
                    self.s.db.execute('BEGIN')
                    try:
                        self._check(entry,principal,dependency['expected'],scope,principal['purpose'],principal['recipient'],'register_dependency')
                        metadata={'contract':'TL-DEPENDENCY-1','consumer':consumer,'dependency':dependency,'field_path':field_path,'scope':scope}
                        self._registration(entry,principal,metadata,'begin')
                        old=self.s.db.execute(lookup,args).fetchone()
                        if old is None or self.artifacts.read_artifact(old['metadata_artifact_id'])!=metadata:raise Conflict('dependency key has different meaning')
                        self._registration(entry,principal,metadata,'commit')
                        self._check(entry,principal,dependency['expected'],scope,principal['purpose'],principal['recipient'],'commit')
                        if self.s.db.total_changes!=before:raise Conflict('read-only dependency verification changed storage')
                        self.s.db.execute('COMMIT')
                        return old['id']
                    except BaseException:
                        self.s.db.execute('ROLLBACK')
                        from digital_life.infrastructure.persistence.tool_learning_readset import savepoint_rolled_back
                        savepoint_rolled_back(self.s)
                        raise
        with dispatch_gate(self.s.root),self.s.tx():
            self._check(entry,principal,dependency['expected'],scope,principal['purpose'],principal['recipient'],'register_dependency')
            metadata={'contract':'TL-DEPENDENCY-1','consumer':consumer,'dependency':dependency,'field_path':field_path,'scope':scope}
            self._registration(entry,principal,metadata,'begin')
            old=self.s.db.execute('SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? AND source_ref_id=? AND relation=? AND purpose=? AND field_path=? AND expected_epoch=?',(self.s.instance_id,consumer['id'],dependency['target']['id'],dependency['relation'],dependency['consumer_purpose'],field_path,dependency['expected']['epoch'])).fetchone()
            if old:
                if self.artifacts.read_artifact(old['metadata_artifact_id'])!=metadata:raise Conflict('dependency key has different meaning')
                self._registration(entry,principal,metadata,'commit')
                self._check(entry,principal,dependency['expected'],scope,principal['purpose'],principal['recipient'],'commit')
                return old['id']
            revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.s.instance_id,dependency['target']['id'],dependency['expected']['revision'])).fetchone()
            ident=insert(self.s,'tl_dependency',consumer_ref_id=consumer['id'],source_ref_id=dependency['target']['id'],source_revision_id=revision[0] if revision else None,relation=dependency['relation'],purpose=dependency['consumer_purpose'],expected_epoch=dependency['expected']['epoch'],field_path=field_path,metadata_artifact_id=self.s.artifact(metadata))
            self._registration(entry,principal,metadata,'commit')
            self._check(entry,principal,dependency['expected'],scope,principal['purpose'],principal['recipient'],'commit')
            return ident

    def register_input(self,entry,principal,request,dependency_id,body_digest=None):
        principal,request,body_digest=deepcopy((principal,request,body_digest))
        self.artifacts.validate_ref(request)
        if body_digest is not None:c.validate('Digest',body_digest)
        if self.s.db.in_transaction:raise Conflict('input registration requires independent transaction')
        with dispatch_gate(self.s.root),self.s.tx():
            row=self.s.db.execute('SELECT * FROM tl_dependency WHERE instance_id=? AND id=?',(self.s.instance_id,dependency_id)).fetchone()
            if row is None or row['consumer_ref_id']!=request['id'] or row['relation']!='read':raise ContractError('input must bind a registered request dependency')
            meta=self._metadata(row);dep=meta['dependency']
            if row['purpose']!=principal['purpose']:raise Forbidden('input purpose differs from registered dependency')
            context={'contract':'TL-INPUT-REGISTRATION-1','request':request,'dependency_id':dependency_id,'metadata':meta,'recipient':principal['recipient'],'body_digest':body_digest}
            self._registration(entry,principal,context,'begin')
            self._check(entry,principal,dep['expected'],meta['scope'],principal['purpose'],principal['recipient'],'register_input')
            old=self.s.db.execute('SELECT * FROM tl_input_dependency WHERE instance_id=? AND request_ref_id=? AND source_ref_id=? AND field_path=? AND purpose=? AND recipient_ref_id=?',(self.s.instance_id,request['id'],row['source_ref_id'],row['field_path'],row['purpose'],principal['recipient']['id'])).fetchone()
            digest=body_digest['hex'] if body_digest is not None else None
            if old:
                if old['source_epoch']!=row['expected_epoch'] or old['body_digest']!=digest or old['retention_state']!='allowed':raise Conflict('input registration is stale or has different meaning')
                self._registration(entry,principal,context,'commit')
                self._check(entry,principal,dep['expected'],meta['scope'],principal['purpose'],principal['recipient'],'commit')
                return old['id']
            fields=dict(request_ref_id=request['id'],source_ref_id=row['source_ref_id'],source_epoch=row['expected_epoch'],source_revision_ref_id=row['source_revision_id'],field_path=row['field_path'],purpose=row['purpose'],recipient_ref_id=principal['recipient']['id'],body_digest=digest,retention_state='allowed',row_revision=0)
            from digital_life.application.learning.runtime_owners import LocalEligibility
            if type(self.authority)is LocalEligibility and self.authority.o.s is self.s:
                ident=self.s._insert_input_registration(fields)
            else:ident=insert(self.s,'tl_input_dependency',**fields)
            self._registration(entry,principal,context,'commit')
            self._check(entry,principal,dep['expected'],meta['scope'],principal['purpose'],principal['recipient'],'commit')
            return ident

    def _registration(self,entry,principal,context,stage):
        result=self.authority.verify_registration(entry,deepcopy(principal),deepcopy(context),stage)
        if result is not None:raise Forbidden('registration verifier must not return a boolean')
        self.s.assert_execution_allowed()

    def _request_context(self,entry,principal,request):
        self.artifacts.validate_ref(request)
        kind=request['kind']
        if kind not in ('activities','thought_requests','action_intents','memory_retrieval_runs'):
            raise ContractError('unsupported callback request owner')
        actual=self.s.row(kind,request['id'])
        if kind=='activities':activity=actual
        elif kind=='action_intents':
            candidate=self.s.row('decision_candidates',actual['candidate_id'])
            decision=self.s.row('decision_records',candidate['decision_id'])
            activity=self.s.row('activities',decision['activity_id'])
        else:activity=self.s.row('activities',actual['activity_id'])
        if activity['cancel_requested_at'] or activity['state'] in ('cancelled','paused','failed','completed'):
            raise Forbidden('request activity is not executable')
        if activity['deadline'] and activity['deadline']<=utc():raise Forbidden('request activity deadline exhausted')
        inputs=[];scan_budget={'remaining':self.max_rows}
        for index,row in enumerate(self.s.db.execute('SELECT * FROM tl_input_dependency WHERE instance_id=? AND request_ref_id=? ORDER BY id LIMIT ?',(self.s.instance_id,request['id'],self.max_rows+1))):
            scan_budget['remaining']-=1
            if index>=self.max_rows or scan_budget['remaining']<0:raise Forbidden('request input scan limit exceeded')
            if row['purpose']!=principal['purpose'] or row['recipient_ref_id']!=principal['recipient']['id'] or row['retention_state']!='allowed':
                raise Forbidden('request input purpose, recipient or retention is blocked')
            dep=self.s.db.execute("SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? AND source_ref_id=? AND purpose=? AND field_path=? AND expected_epoch=? AND relation='read'",
                (self.s.instance_id,request['id'],row['source_ref_id'],row['purpose'],row['field_path'],row['source_epoch'])).fetchone()
            if dep is None or dep['source_revision_id']!=row['source_revision_ref_id']:raise ContractError('input has no matching durable dependency')
            metadata=self._metadata(dep)
            self._check(entry,principal,metadata['dependency']['expected'],metadata['scope'],principal['purpose'],principal['recipient'],'input_use',scan_budget)
            inputs.append({'row':dict(row),'metadata':metadata})
        return {'contract':'TL-CALLBACK-CONTEXT-1','request':deepcopy(request),'record':actual,'activity':activity,'inputs':inputs}

    def callback(self,entry,principal,token,scope,purpose,recipient,callback,request=None):
        """Trusted synchronous callback only; no network or model adapter is supplied."""
        principal,token,scope,recipient,request=deepcopy((principal,token,scope,recipient,request))
        if not callable(callback):raise ContractError('trusted callback required')
        if self.s.db.in_transaction:raise Conflict('callback must not hold a main database transaction')
        with dispatch_gate(self.s.root):
            self.check(entry,principal,token,scope,purpose,recipient,'callback_entry')
            context=self._request_context(entry,principal,request) if request is not None else {'contract':'TL-CALLBACK-CONTEXT-1','request':None,'inputs':[]}
            if self.authority.verify_callback(entry,deepcopy(principal),deepcopy(context),'callback_entry') is not None:raise Forbidden('callback verifier must not return a boolean')
            # Re-read after every authority callback; a same-thread control change
            # cannot hide behind an earlier successful snapshot.
            self.check(entry,principal,token,scope,purpose,recipient,'final_entry')
            if request is not None:self._request_context(entry,principal,request)
            self.s.assert_execution_allowed()
            result=callback()
            self.check(entry,principal,token,scope,purpose,recipient,'result_use')
            context=self._request_context(entry,principal,request) if request is not None else context
            if self.authority.verify_callback(entry,deepcopy(principal),deepcopy(context),'result_use') is not None:raise Forbidden('callback result verifier must not return a boolean')
            self.check(entry,principal,token,scope,purpose,recipient,'final_result_use')
            if request is not None:self._request_context(entry,principal,request)
            self.s.assert_execution_allowed()
            return result


# Fixed local code, captured at import rather than trusting later replacements.
def _signature_method_spec(cls):
    result={}
    for base in reversed(cls.__mro__):
        for name,value in vars(base).items():
            if not name.startswith('__') and callable(value):result[name]=value
    return tuple(result.items())


def _signature_original_methods(value,spec):
    own=vars(value)
    for name,original in spec:
        if name in own:return False
        for base in type(value).__mro__:
            if name in vars(base):
                if vars(base)[name]is not original:return False
                break
    return True


_SIGNATURE_ELIGIBILITY_METHODS=_signature_method_spec(ToolLearningEligibility)
_SIGNATURE_ARTIFACT_METHODS=_signature_method_spec(ToolLearningStore)


def _mint_signature_check(service,phase):
    from digital_life.infrastructure.persistence.tool_learning_readset import can_share_material_facts
    if not can_share_material_facts(service.s):return None
    from digital_life.domain.contracts import RuntimeIdentity
    from digital_life.application.learning.runtime_owners import (LocalEligibility,LocalRuntimeOwners,
        _SIGNATURE_SOURCE_METHODS,_SIGNATURE_OWNER_METHODS)
    from digital_life.application.learning.runtime import _LocalInputEligibility,_SIGNATURE_INPUT_METHODS
    authority=service.authority
    if type(authority)is not LocalEligibility:return None
    owner=authority.o
    if (type(owner)is not LocalRuntimeOwners or owner.s is not service.s or owner.source is not authority
            or type(owner.identity)is not RuntimeIdentity or type(owner.eligibility)is not ToolLearningEligibility
            or owner.eligibility.authority is not authority):return None
    if type(service)is ToolLearningEligibility:spec=_SIGNATURE_ELIGIBILITY_METHODS
    elif type(service)is _LocalInputEligibility:spec=_SIGNATURE_INPUT_METHODS
    else:return None
    objects=((service,spec),(owner,_SIGNATURE_OWNER_METHODS),(authority,_SIGNATURE_SOURCE_METHODS),
             (owner.eligibility,_SIGNATURE_ELIGIBILITY_METHODS))
    for value,methods in objects:
        if not _signature_original_methods(value,methods):return None
    artifacts=(service.artifacts,owner.eligibility.artifacts)
    for value in artifacts:
        if (type(value)is not ToolLearningStore or value._ToolLearningStore__store is not service.s
                or not _signature_original_methods(value,_SIGNATURE_ARTIFACT_METHODS)):return None
    from digital_life.infrastructure.persistence.tool_learning_meter import _ACTIVE
    service.s._file_signature_stats['minted']+=1
    return {'phase':phase,'service':service,'owner':owner,'authority':authority,'meter':_ACTIVE.get(),
            'thread':get_ident(),'depth':phase.check_depth,'generation':phase.generation,'transaction':phase.transaction_generation,
            'rollback':phase.rollback_generation,'monitor_stamp':phase.monitor.observed_material_revision(),
            'paths':frozenset(phase.blobs),'locations':{path.name:path for path in phase.blobs}}
