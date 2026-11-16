"""IM11 fixed input assembly and authenticated content-review composition.

The module never wakes, migrates, starts a server or executes a model on import.
The process/owner-specific composition remains explicit; caller dictionaries are
not capabilities. Existing schema3 paths do not acquire these guarantees.
"""
from copy import deepcopy
from contextlib import contextmanager,nullcontext
import json
import secrets
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,dumps,identifier,utc
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.application.learning.eligibility import ToolLearningEligibility,EligibilityAuthority,slot,ref
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate


class RuntimeAuthority:
    # Opt-in only for a concrete owner whose checks are read-only while the
    # caller holds dispatch_gate. Never shared across entry/result-use stages.
    deduplicate_identical_fields=False
    def verify_health(self,entry,request,principal,stage):return None
    def verify_assembly(self,entry,request,principal,manifest,stage):raise Forbidden('actual complete packet owner is not configured')
    def verify_retention(self,entry,request,principal,manifest,stage):raise Forbidden('current derived material retention owner is not configured')
    def verify_live(self,entry,request,principal,field,stage):raise Forbidden('bound live state/current control verifier is not configured')


def _leaves(value,path=''):
    if type(value) is dict:
        if not value:yield path
        for key,item in value.items():
            yield from _leaves(item,path+'/'+key.replace('~','~0').replace('/','~1'))
    elif type(value) is list:
        if not value:yield path
        for index,item in enumerate(value):yield from _leaves(item,path+'/'+str(index))
    else:yield path


def validate_manifest(packet,manifest):
    """Every actual packet leaf is either owned fixed instruction or sourced.

    A prefix can cover a whole derived field, but its dependencies must be the
    complete provenance, not only whichever evidence the model later mentions.
    Fixed constants are still verified by the trusted assembler owner.
    """
    t.obj(manifest,('contract','packet_digest','fields'))
    if manifest['contract']!='TL-INPUT-ASSEMBLY-1' or manifest['packet_digest']!=c.fingerprint(packet):raise Conflict('fixed packet manifest differs from actual complete packet')
    if not isinstance(manifest['fields'],list) or len(manifest['fields'])>4096:raise Forbidden('bounded complete field manifest required')
    paths=set()
    for field in manifest['fields']:
        t.obj(field,('path','digest','kind','usage','dependencies','dependency_scopes','scope'))
        t.enum(field['usage'],('live_state','historical_observation','current_control','fixed_instruction'))
        t.string(field['path']);c.validate('Digest',field['digest']);t.enum(field['kind'],('fixed_instruction','source_material'))
        if field['path'] in paths:raise Conflict('duplicate assembled field path')
        paths.add(field['path']);c.validate('Scope',field['scope'])
        if (field['kind']=='fixed_instruction')!=(field['usage']=='fixed_instruction'):raise ContractError('source usage cannot be relabeled as a fixed instruction')
        value=c.resolve_locator({'kind':'json_pointer','pointer':field['path']},packet)
        if field['digest']['hex']!=c.fingerprint(value):raise Conflict('field digest does not bind actual input')
        t.array(field['dependencies'],lambda v:c.validate('Dependency',v))
        t.array(field['dependency_scopes'],lambda v:c.validate('Scope',v))
        if len(field['dependency_scopes'])!=len(field['dependencies']):raise ContractError('every source dependency needs its own exact scope')
        if field['kind']=='fixed_instruction' and field['dependencies']:raise ContractError('fixed instruction cannot hide a source dependency')
        if field['kind']=='source_material' and not any(d['relation']=='read' for d in field['dependencies']):raise Forbidden('actual source-derived input field needs a genuine read dependency')
        if any(d['relation'] not in ('read','delete') for d in field['dependencies']):raise ContractError('input manifest uses actual read/delete paths; derivations belong to their own consumers')
    for leaf in _leaves(packet):
        matches=[p for p in paths if leaf==p or leaf.startswith(p+'/')]
        if len(matches)!=1:raise Forbidden('each complete packet leaf must have exactly one owned manifest prefix')
    return manifest


class _LocalInputEligibility(ToolLearningEligibility):
    """Exact successful checks within one real local request-input boundary.

    Per-field metadata/row/hash validation remains in IM06. The concrete local
    owner is read-only; writes invalidate keys, stop is checked on every hit,
    and no cache survives the next context/authority callback/model boundary.
    """
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self._input_checks=None
    def _request_context(self,entry,principal,request):
        previous=self._input_checks;self._input_checks={}
        try:
            with self.authority.verification_boundary():return super()._request_context(entry,principal,request)
        finally:self._input_checks=previous
    def _check(self,entry,principal,token,scope,purpose,recipient,stage,scan_budget=None):
        from digital_life.infrastructure.persistence.tool_learning_readset import checkpoint,current_readset
        from digital_life.infrastructure.persistence.sqlite_write_monitor import callback_active
        if callback_active() or self._input_checks is None:return super()._check(entry,principal,token,scope,purpose,recipient,stage,scan_budget)
        checkpoint(self.s)
        phase=current_readset(self.s)
        key=c.fingerprint({'entry':entry,'principal':principal,'token':token,'scope':scope,'purpose':purpose,'recipient':recipient,'relation':'actual_input_read','stage':stage,'changes':self.s.db.total_changes,'generation':None if phase is None else phase.generation})
        if key in self._input_checks:
            self.s.assert_execution_allowed();return deepcopy(self._input_checks[key])
        result=super()._check(entry,principal,token,scope,purpose,recipient,stage,scan_budget)
        self._input_checks[key]=deepcopy(result);return result


class ToolLearningRuntime:
    def __init__(self,store,authority=None,eligibility_authority=None,clock=utc,eligibility_limits=None):
        self.s=store;self.authority=RuntimeAuthority() if authority is None else authority
        if not isinstance(self.authority,RuntimeAuthority):raise ContractError('trusted RuntimeAuthority required')
        from digital_life.application.learning.runtime_owners import LocalEligibility
        eligibility_class=_LocalInputEligibility if type(eligibility_authority) is LocalEligibility else ToolLearningEligibility
        self.eligibility=eligibility_class(store,eligibility_authority,**(eligibility_limits or {}));self.storage=ToolLearningStore(store);self.clock=clock
    @staticmethod
    def _attest(value):
        if value is not None:raise Forbidden('runtime owner must attest by successful None return')
    def _local(self,request):
        self.s.assert_execution_allowed();row=self.s.row('thought_requests',request['id'])
        activity=self.s.row('activities',row['activity_id'])
        if row['state'] not in ('prepared','running') or self.clock()>=row['deadline'] or activity['cancel_requested_at'] or activity['state'] in ('cancelled','failed'):raise Forbidden('actual thought request is no longer dispatchable')
        return row
    def _proof(self,request):
        row=self.s.db.execute('SELECT * FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=?',(self.s.instance_id,'tl.input.assembly',request['id'])).fetchone()
        return self.storage.read_artifact(row['payload_artifact_id']) if row else None
    def _qualify(self,entry,request,principal,manifest,stage):
        boundary=getattr(self.eligibility.authority,'verification_boundary',None)
        with boundary() if self.authority.deduplicate_identical_fields and boundary else nullcontext():
            return self._qualify_in_boundary(entry,request,principal,manifest,stage)
    def _qualify_in_boundary(self,entry,request,principal,manifest,stage):
        seen=set()
        for field in manifest['fields']:
            if field['usage'] in ('live_state','current_control'):self._attest(self.authority.verify_live(entry,deepcopy(request),deepcopy(principal),deepcopy(field),stage))
        for field in manifest['fields']:
            for index,dependency in enumerate(field['dependencies']):
                source_scope=field['dependency_scopes'][index]
                if dependency['consumer_purpose']!=principal['purpose']:raise Forbidden('input dependency purpose differs from actual inference use')
                if dependency['relation'] in ('support','read','derive','representation','group'):
                    key=c.fingerprint({'principal':principal,'expected':dependency['expected'],'scope':source_scope,'relation':dependency['relation'],'stage':stage})
                    if self.authority.deduplicate_identical_fields and key in seen:continue
                    self.eligibility.check(entry,principal,dependency['expected'],source_scope,principal['purpose'],principal['recipient'],stage)
                    seen.add(key)
                elif dependency['relation']!='delete':raise Forbidden('unhandled input relation')
        self._local(request)
        self._attest(self.authority.verify_health(entry,deepcopy(request),deepcopy(principal),stage))
        self._local(request)
    def assemble(self,entry,request,principal,packet,manifest):
        request,principal,packet,manifest=map(deepcopy,(request,principal,packet,manifest))
        c.validate('Ref',request);c.validate('Principal',principal);validate_manifest(packet,manifest)
        if request['kind']!='thought_requests':raise ContractError('fixed thought request consumer required')
        if self.s.db.in_transaction:raise Conflict('input assembly starts outside a main transaction')
        with dispatch_gate(self.s.root):
            row=self._local(request)
            if row['request_hash']!=c.fingerprint(packet):raise Conflict('actual thought packet differs from immutable request')
            self._attest(self.authority.verify_assembly(entry,deepcopy(request),deepcopy(principal),deepcopy(manifest),'prepare'))
            self._attest(self.authority.verify_retention(entry,deepcopy(request),deepcopy(principal),deepcopy(manifest),'prepare'))
            self._qualify(entry,request,principal,manifest,'before_assembly_retention')
            prior=self._proof(request)
            if prior:
                if prior['manifest']!=manifest or prior['principal']!=principal:raise Conflict('immutable request cannot change assembly')
                return prior
            boundary=getattr(self.eligibility.authority,'verification_boundary',None)
            with boundary() if self.authority.deduplicate_identical_fields and boundary else nullcontext():
                registered=[];pending_inputs=[]
                from digital_life.application.learning.runtime_owners import LocalEligibility
                grouped=type(self.eligibility.authority)is LocalEligibility and self.authority.deduplicate_identical_fields
                for field in manifest['fields']:
                    for index,dependency in enumerate(field['dependencies']):
                        dep=self.eligibility.register_dependency(entry,principal,request,dependency,field['path'],field['dependency_scopes'][index])
                        # Preserve both public registration operations and all
                        # their begin/commit checks. Complete graph writes first
                        # so approved input inserts do not lose their read facts
                        # to the following unrelated graph write on every field.
                        if dependency['relation']!='delete':
                            if grouped:pending_inputs.append((dep,field['digest']))
                            else:registered.append(self.eligibility.register_input(entry,principal,request,dep,field['digest']))
                for dep,digest in pending_inputs:
                    registered.append(self.eligibility.register_input(entry,principal,request,dep,digest))
            self._attest(self.authority.verify_assembly(entry,deepcopy(request),deepcopy(principal),deepcopy(manifest),'commit'))
            self._attest(self.authority.verify_retention(entry,deepcopy(request),deepcopy(principal),deepcopy(manifest),'commit'))
            self._qualify(entry,request,principal,manifest,'assembly_complete')
            proof={'contract':'TL-INPUT-ASSEMBLY-COMPLETE-1','request':request,'packet_digest':c.fingerprint(packet),'manifest':manifest,'principal':principal,'inputs':registered}
            with self.s.tx():
                event=self.s.event('input.assembly_complete',payload=proof,source='tl.input.assembly',key=request['id'],activity=row['activity_id'])
                from digital_life.application.learning.engine import _dependency
                token={'object':deepcopy(request),'revision':0,'epoch':0}
                for consumer in (ref(self.s,event),ref(self.s,self.s.row('runtime_events',event)['payload_artifact_id'])):
                    for relation in ('read','delete'):_dependency(self.s,consumer,token,manifest['fields'][0]['scope'],relation,'/assembly',principal['purpose'])
            return deepcopy(proof)
    def invoke(self,entry,request,principal,packet,manifest,callback):
        request,principal,packet,manifest=map(deepcopy,(request,principal,packet,manifest));validate_manifest(packet,manifest)
        with dispatch_gate(self.s.root):
            proof=self._proof(request)
            if proof is None or proof['manifest']!=manifest or proof['principal']!=principal or proof['packet_digest']!=c.fingerprint(packet):raise Forbidden('complete fixed packet assembly proof absent')
            self._attest(self.authority.verify_assembly(entry,deepcopy(request),deepcopy(principal),deepcopy(manifest),'actual_entry'))
            self._qualify(entry,request,principal,manifest,'actual_entry')
            # IM06 binds the actual request and all its input dependencies.
            fields=[(f,d,f['dependency_scopes'][index]) for f in manifest['fields'] for index,d in enumerate(f['dependencies']) if d['relation'] in ('support','read','derive','representation','group')]
            if not fields:raise Forbidden('actual inference has no qualified source material')
            field,dependency,source_scope=fields[0]
            output=self.eligibility.callback(entry,principal,dependency['expected'],source_scope,principal['purpose'],principal['recipient'],callback,request=request)
            self._attest(self.authority.verify_assembly(entry,deepcopy(request),deepcopy(principal),deepcopy(manifest),'result_use'))
            self._qualify(entry,request,principal,manifest,'result_use')
            return output


def authenticate_controller(store,bearer):
    """Validate the existing local credential before any review-source lookup."""
    path=store.root/'controller.token'
    if path.is_symlink() or not path.is_file():raise Forbidden('controller credential unavailable')
    expected=path.read_text().strip()
    if not expected or type(bearer) is not str or not bearer.isascii() or not secrets.compare_digest(bearer,'Bearer '+expected):raise Forbidden('actual controller credential required')
    return store.config()['controller']


class _ControllerReadSession:
    def __init__(self,controller,purpose='accept'):self.controller=controller;self.purpose=purpose;self.nonce=identifier()


class ControllerSourceAuthority(EligibilityAuthority):
    """Existing memory ACL and immutable local-source owner for review reads.

    Only a successfully authenticated authoring call can mint this private
    session. Unsupported owners fail closed; this is not a generic admin grant.
    """
    IMMUTABLE=frozenset(('perception_signals','artifacts','tl_product','policy_versions','configuration_versions','model_versions','context_snapshots','thought_requests','thought_results','action_results','runtime_events','memory_retrieval_runs','tl_recall_item','metric_definitions','rule_definitions'))
    def __init__(self,store):self.s=store;self.session=None;self._revision_storage=None
    def _session(self,entry,principal):
        if not isinstance(self.session,_ControllerReadSession) or type(entry) is not str or not secrets.compare_digest(entry,self.session.nonce):raise Forbidden('authenticated controller review session required')
        controller=self.s.config()['controller']
        if self.session.controller!=controller or principal['actor']['id']!=controller or principal['recipient']['id']!=controller or principal['purpose']!=self.session.purpose:raise Forbidden('review session cannot authorize another actor, recipient or use')
    # A native revision has its own registry ID; these are actual owner/number
    # columns, not an expansion of the static source permission whitelist.
    NATIVE_REVISIONS={
        'personality_profiles':('profile_object_id','version','personality-root'),
        'value_profiles':('profile_object_id','version','value-root'),
        'identity_anchors':('anchor_object_id','version','identity-root'),
        'memory_revisions':('memory_id','revision_no','memory_items'),
        'perception_observation_revisions':('observation_id','revision_no','perception_observations'),
        'cognition_belief_revisions':('belief_id','revision_no','cognition_beliefs'),
        'cognition_concept_revisions':('concept_id','revision_no','cognition_concepts'),
        'tl_content_revision':('content_id','revision_no','tl_content'),
        'tl_representation':('series_id','representation_no','tl_representation_head'),
    }
    def _native_version(self,storage,kind,key,revision,owner=None):
        owner_column,number_column,owner_kind=self.NATIVE_REVISIONS[kind]
        actual=self.s.row(kind,key)
        expected_owner=actual[owner_column]
        if actual[number_column]!=revision or owner is not None and owner!=expected_owner:
            raise Conflict('review native source revision number/owner mismatch')
        owner_ref=ref(self.s,expected_owner)
        storage.validate_ref(owner_ref,expected_kind=owner_kind)
        if owner_kind not in ('personality-root','value-root','identity-root'):
            self.s.row(owner_kind,expected_owner)
        known=ref(self.s,key,kind);known['revision']=slot(revision)
        storage.validate_ref(known,expected_kind=kind,version_owner=expected_owner)
    def verify_version(self,entry,principal,token,stage):
        self._session(entry,principal);c.validate('VersionToken',token)
        obj=token['object']
        if self._revision_storage is None:self._revision_storage=ToolLearningStore(self.s)
        storage=self._revision_storage
        storage.validate_ref(obj);self.s.row(obj['kind'],obj['id'])
        if obj['kind'] in self.NATIVE_REVISIONS:
            self._native_version(storage,obj['kind'],obj['id'],token['revision']);return
        from digital_life.infrastructure.persistence.tool_learning_store import STABLE_REVISIONS
        if obj['kind'] in STABLE_REVISIONS:
            kind=STABLE_REVISIONS[obj['kind']]
            row=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=? AND kind=?',
                (self.s.instance_id,obj['id'],token['revision'],kind)).fetchone()
            if row is None:raise Conflict('review source immutable version missing')
            self._native_version(storage,kind,row[0],token['revision'],obj['id']);return
        revisions=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=?',(self.s.instance_id,obj['id'])).fetchall()
        if revisions:
            # Mutable observation bridges must retain their real immutable
            # event and digest validation, never just a registry row existence.
            known=deepcopy(obj);known['revision']=slot(token['revision'])
            storage.validate_ref(known)
        elif token['revision']!=0 or obj['kind'] not in self.IMMUTABLE:
            raise Forbidden('source owner has no proven immutable/static version')
    PRIMARY_CONFIGURATION_REPORTS={
        'behavior_policy.configured':('enabled','temperature','biases','weights','version','actor'),
        'goal_regulation.configured':('enabled','min_disk_bytes','actor'),
        'personality_growth.configured':('enabled','actor','version'),
        'habit_learning.configured':('enabled','actor','version'),
        'people_relations.configured':('enabled','actor','version'),
        'memory_quality.configured':('enabled','actor','version'),
        'agenda.configured':('enabled','actor','version'),
        'maintenance.configured':('enabled','auto_repair','max_repairs','actor'),
    }
    def _primary_configuration_report(self,row,scope,purpose,recipient,principal):
        # These exact legacy configure APIs persist their primary report as an
        # event+artifact, without a derived producer. This is local history,
        # never independent scientific support or an authoring grant.
        kind=row['event_type']
        if (self.session.purpose!='history_audit' or purpose!='history_audit'
                or recipient!=principal['recipient'] or kind not in self.PRIMARY_CONFIGURATION_REPORTS):
            raise Forbidden('derived source has no actual producer lineage')
        c.validate('Scope',scope)
        if scope['claim_target']!='source_report':raise Forbidden('internal configuration is only a source report')
        if (row['source']!='runtime' or row['lane']!='control'
                or any(row[key] is not None for key in ('activity_id','payload_object_id','causation_event_id','authority_ref'))
                or type(row['source_event_id'])is not str or len(row['source_event_id'])!=32
                or any(ch not in '0123456789abcdef'for ch in row['source_event_id'])
                or row['correlation_id']!=row['source_event_id']):
            raise Forbidden('internal configuration event binding differs from its producer contract')
        c.validate('UTC',row['received_at'])
        if self.s.row('identity_instances',self.s.instance_id)['controller_ref']!=self.session.controller:
            raise Forbidden('controller is not this configuration report owner')
        if self._revision_storage is None:self._revision_storage=ToolLearningStore(self.s)
        storage=self._revision_storage
        storage.validate_ref(ref(self.s,row['id']),expected_kind='runtime_events')
        if row['payload_artifact_id']is None:raise Forbidden('internal configuration has no actual payload artifact')
        storage.validate_ref(ref(self.s,row['payload_artifact_id']),expected_kind='artifacts')
        artifact=self.s.row('artifacts',row['payload_artifact_id'])
        if artifact['media_type']!='application/json':raise Forbidden('internal configuration payload must be JSON')
        payload=storage.read_artifact(row['payload_artifact_id'],fresh=True)
        if row['payload_hash']!=c.fingerprint(payload):raise Conflict('internal configuration event payload digest differs')
        t.obj(payload,self.PRIMARY_CONFIGURATION_REPORTS[kind]);t.boolean(payload['enabled'])
        if payload['actor']!=self.session.controller:raise Forbidden('internal configuration actor is not the actual controller')
        storage.validate_ref(ref(self.s,payload['actor']),expected_kind='social_actors')
        self.s.row('social_actors',payload['actor'])
        versions={'personality_growth.configured':'personality-growth-v1','habit_learning.configured':'context-habit-v1',
                  'people_relations.configured':'people-relations-v1','memory_quality.configured':'memory-quality-v1',
                  'behavior_policy.configured':'contextual-softmax-v1'}
        if kind in versions and (type(payload['version'])is not str or payload['version']!=versions[kind]):
            raise Forbidden('unsupported internal configuration version')
        if kind=='agenda.configured'and(type(payload['version'])is not int or payload['version']!=1):
            raise Forbidden('unsupported internal configuration version')
        if kind=='goal_regulation.configured':t.integer(payload['min_disk_bytes'])
        if kind=='maintenance.configured':t.boolean(payload['auto_repair']);t.integer(payload['max_repairs'],1,3)
        if kind=='behavior_policy.configured':
            from digital_life.application.behavior.behavior_policy import TOOLS,BASE
            def bounded(value,low,high):
                t.number(value)
                if not low<=value<=high:raise ContractError('internal configuration parameter outside producer range')
            bounded(payload['temperature'],.05,5)
            features=set(BASE)|{'personality.'+row['name']for row in self.s.rows('personality_dimensions')}|{'value.'+row['definition']for row in self.s.rows('value_dimensions')}
            if type(payload['biases'])is not dict or set(payload['biases'])-set(TOOLS):raise ContractError('unknown configured behavior bias tool')
            if type(payload['weights'])is not dict or set(payload['weights'])!=set(TOOLS):raise ContractError('configured behavior tool coverage differs')
            for value in payload['biases'].values():bounded(value,-20,20)
            for weights in payload['weights'].values():
                if type(weights)is not dict or set(weights)-features:raise ContractError('unknown configured behavior feature')
                for value in weights.values():bounded(value,-20,20)
    def verify(self,entry,principal,token,scope,purpose,recipient,stage):
        self._session(entry,principal);kind=token['object']['kind'];key=token['object']['id']
        if token['object']['instance_id']!=self.s.instance_id:raise Forbidden('external source cannot use local controller authority')
        if kind in ('memory_items','memory_revisions'):
            from digital_life.application.services import Memory
            row=self.s.row(kind,key);memory=key if kind=='memory_items' else row['memory_id']
            if self.s.row('memory_items',memory)['state']!='active' or self.session.controller not in Memory(self.s).readers(memory):raise Forbidden('current source ACL or retention denies review')
        elif kind=='perception_signals':
            allowed={self.session.controller}
            if self.session.purpose=='history_audit':allowed.add(self.s.config()['self_actor'])
            if self.s.row(kind,key)['source_actor_id'] not in allowed:raise Forbidden('another input actor source requires its own authority')
        elif kind=='tl_product':
            row=self.s.row(kind,key);self.s.row('tl_work',row['work_id'])
        elif kind in ('policy_versions','configuration_versions','model_versions'):self.s.row(kind,key)
        elif kind in ('thought_results','thought_requests','runtime_events'):
            row=self.s.row(kind,key)
            if self.s.db.execute('SELECT 1 FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? LIMIT 1',(self.s.instance_id,key)).fetchone() is None:
                if kind!='runtime_events':raise Forbidden('derived source has no actual producer lineage')
                self._primary_configuration_report(row,scope,purpose,recipient,principal)
        elif self.session.purpose=='history_audit':
            from digital_life.domain.tool_learning_sources import SNAPSHOT_KINDS
            internal=frozenset(('personality_profiles','value_profiles','identity_anchors','perception_observation_revisions','cognition_belief_revisions','cognition_concept_revisions','tl_content','tl_content_revision','tl_representation_head','tl_representation'))
            if kind not in SNAPSHOT_KINDS|internal|self.IMMUTABLE:raise Forbidden('source owner unsupported for controller history audit')
            # Internal life state belongs to this configured instance's actual
            # controller. Memory and external author ACLs above stay separate.
            if self.s.row('identity_instances',self.s.instance_id)['controller_ref']!=self.session.controller:raise Forbidden('controller is not this internal state owner')
            self.s.row(kind,key)
        else:raise Forbidden('source owner unsupported for controller review')


class ControllerReviewAuthor:
    """Authenticated authoring only; its record is not a scientific support grant.

    Material permission remains an actual M12 source-owner capability. The
    credential is never included in the record, event, hash or return value.
    """
    def __init__(self,store,eligibility_authority=None,clock=utc):
        self.s=store;self.source_authority=ControllerSourceAuthority(store) if eligibility_authority is None else eligibility_authority;self.eligibility=ToolLearningEligibility(store,self.source_authority);self.storage=ToolLearningStore(store);self.clock=clock
    def author(self,bearer,body,entry=None):
        body=deepcopy(body);controller=authenticate_controller(self.s,bearer)
        if isinstance(self.source_authority,ControllerSourceAuthority):
            self.source_authority.session=_ControllerReadSession(controller);entry=self.source_authority.session.nonce
        t.obj(body,('contract','proposal','proposal_digest','review_round','expected','native_expected','actual_scope','policy','atomic_group','verdict','expires_at'))
        if body['contract']!='TL-CONTROLLER-CONTENT-REVIEW-1':raise ContractError('not a controller content review')
        c.validate('Ref',body['proposal']);c.validate('Ref',body['policy']);c.validate('Scope',body['actual_scope'])
        for key in ('expected','native_expected'):t.slot(body[key],lambda v:c.validate('VersionToken',v))
        t.slot(body['atomic_group'],lambda v:c.validate('Ref',v));t.integer(body['review_round'])
        t.enum(body['verdict'],('accept','candidate','defer','reject','conflict','reuse'));c.validate('UTC',body['expires_at'])
        if body['expires_at']<=self.clock():raise Forbidden('controller review already expired')
        policy=self.s.row('policy_epochs',self.s.rows('policy_epochs')[0]['id'])
        if body['policy']['id']!=policy['policy_version_id']:raise Conflict('controller review binds stale active policy')
        principal={'actor':ref(self.s,controller),'module':'M03','recipient':ref(self.s,controller),'purpose':'accept','authorization':deepcopy(body['policy'])}
        token={'object':deepcopy(body['proposal']),'revision':0,'epoch':self.eligibility.current_epoch(body['proposal'],body['actual_scope'])}
        with dispatch_gate(self.s.root):
            self.eligibility.check(entry,principal,token,body['actual_scope'],'accept',principal['recipient'],'controller_review_read')
            row=self.s.row('tl_product',body['proposal']['id'])
            if row['product_type']!='UpdateProposal':raise ContractError('controller review must name an update proposal')
            product=self.storage.read_artifact(row['payload_artifact_id'],'Product')
            if body['proposal_digest']!=c.fingerprint(product) or body['expected']!=product['body']['target']['expected']:raise Conflict('review baseline/proposal digest mismatch')
            claims=product['body']['claims']
            if not claims or any(claim['scope']!=body['actual_scope'] for claim in claims):raise Conflict('review actual scope differs from all proposed claims')
            # Product ancestry must already be registered by the producing
            # runtime. Review authoring cannot invent provenance from a label.
            deps=self.s.db.execute('SELECT count(*) FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=?',(self.s.instance_id,row['id'])).fetchone()[0]
            if not deps:raise Forbidden('proposal source lineage is not registered')
            self.eligibility.check(entry,principal,token,body['actual_scope'],'accept',principal['recipient'],'controller_review_commit')
            if self.clock()>=body['expires_at']:raise Forbidden('review expired before authoring commit')
            with self.s.tx():
                channel=self.s.db.execute("SELECT id FROM perception_channels WHERE instance_id=? AND kind='user' ORDER BY rowid LIMIT 1",(self.s.instance_id,)).fetchone()
                if channel is None:channel=self.s.db.execute('SELECT id FROM perception_channels WHERE instance_id=? ORDER BY rowid LIMIT 1',(self.s.instance_id,)).fetchone()
                if channel is None:raise Forbidden('controller input channel missing')
                artifact=self.s.artifact(body)
                signal=self.s.insert('perception_signals',channel_id=channel[0],source_actor_id=controller,external_id='tl-content-review:'+identifier(),artifact_id=artifact,received_at=self.clock())
                authored=self.s.event('controller.content_review_authored',payload={'review':ref(self.s,signal),'proposal':deepcopy(body['proposal']),'round':body['review_round'],'review_digest':c.fingerprint(body),'controller':ref(self.s,controller)},source='tl.controller.review',key=signal,lane='control')
                from digital_life.application.learning.engine import _dependency
                for consumer in (ref(self.s,signal),ref(self.s,artifact),ref(self.s,authored),ref(self.s,self.s.row('runtime_events',authored)['payload_artifact_id'])):
                    for relation in ('read','delete'):_dependency(self.s,consumer,token,body['actual_scope'],relation,'/reviewed_proposal','accept')
            return {'review':ref(self.s,signal),'inference_started':False,'scientific_support_granted':False}


def strict_feature_enabled(store):
    """Current policy enables new native TL learning; schema4 gates are separate."""
    row=store.db.execute('SELECT p.scope FROM policy_epochs e JOIN policy_versions p ON p.id=e.policy_version_id AND p.instance_id=e.instance_id WHERE e.instance_id=?',(store.instance_id,)).fetchone()
    if row is None:raise Forbidden('current active policy unavailable')
    policy=c.loads(row[0]);feature=policy.get('tool_learning_runtime')
    if feature is None:return False
    t.obj(feature,('contract','enabled'),('ordinary_activity_caps',))
    if feature['contract']!='TL-STRICT-RUNTIME-1':raise Forbidden('unknown strict runtime capability profile')
    t.boolean(feature['enabled']);return feature['enabled']


def qualified_plane_required(store):
    # schema4 never downgrades source/control/actual-use gates when learning is
    # switched off. Current runtime process identity is still checked by owner.
    from digital_life.infrastructure.persistence.tool_learning_readset import facts,can_share_schema_material
    version=(next(iter(facts(store,'storage_schema_version')))[0]if can_share_schema_material(store)
             else store.db.execute('PRAGMA user_version').fetchone()[0])
    if type(version) is not int or version not in (2,3,4):raise Forbidden('unsupported storage schema cannot fall back to legacy execution')
    return version==4 or strict_feature_enabled(store) or legacy_protection_present(store)


def strict_legacy_boundary(store,surface,target=None):
    """Actual old entrypoints must never bypass strict-mode assembly.

    These legacy entrypoints cannot prove their historical packet assembly.
    Their explicit rejection is a capability boundary, not an implementation of
    strict Engine composition; the latter must be wired before IM11 completes.
    """
    if qualified_plane_required(store) or legacy_protection_present(store):raise Forbidden('protected runtime requires qualified '+surface+' composition; legacy entry is blocked')


PERSISTENT_TL_MATERIAL_TABLES=('tl_dependency','tl_input_dependency','tl_content_revision','tl_representation','tl_product','tl_recall_item')


def managed_material_tables(db):
    from digital_life.infrastructure.persistence.tool_learning_store import OWNERS
    found={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'tl_*'")}
    if found and found!=set(OWNERS)|{'tl_command'}:raise Forbidden('partial or unknown TL table layout cannot be treated as unprotected legacy storage')
    return found


def legacy_protection_present(store):
    """Actual persistent protection survives a feature switch/code fallback.

    This is a negative legacy boundary, not a grant or a complete bridge.
    Metadata-only existence probes never read old source bodies. Ordinary
    schema3 without new protection remains unchanged.
    """
    tables=managed_material_tables(store.db)
    for table in PERSISTENT_TL_MATERIAL_TABLES:
        if table in tables and store.db.execute('SELECT 1 FROM '+table+' WHERE instance_id=? LIMIT 1',(store.instance_id,)).fetchone():return True
    if 'tl_barrier' in tables and store.db.execute("SELECT 1 FROM tl_barrier WHERE instance_id=? AND (state='active' OR kind='erase') LIMIT 1",(store.instance_id,)).fetchone():return True
    if 'tl_erasure_target' in tables and store.db.execute('SELECT 1 FROM tl_erasure_target WHERE instance_id=? LIMIT 1',(store.instance_id,)).fetchone():return True
    path=store.root/'control.sqlite'
    if path.exists() or path.is_symlink():
        control=store.control_reader()
        if control.execute("SELECT 1 FROM control_commands WHERE instance_ref=? AND source='maintenance-controller' AND ((kind='maintenance.protective_change_pending' AND state<>'rejected') OR (kind='maintenance.exclusion_head' AND state='succeeded')) LIMIT 1",(store.instance_id,)).fetchone():return True
    return False


from digital_life.application.learning.eligibility import _signature_method_spec
_SIGNATURE_INPUT_METHODS=_signature_method_spec(_LocalInputEligibility)
