"""Concrete local owner composition for strict runtime process and sources.

Authorization is bound to a current control-plane process, never to a caller's
module label. Scientific interpretation beyond scoped source reports is not
provided by this local owner.
"""
from copy import deepcopy
from contextlib import contextmanager,nullcontext
import json
import os
import sqlite3
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc,dumps
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.domain.tool_learning_sources import SNAPSHOT_KINDS
from digital_life.application.learning.eligibility import EligibilityAuthority,ToolLearningEligibility,slot,ref
from digital_life.application.learning.source_snapshot import SourceSnapshots,SnapshotAuthority
from digital_life.application.learning.budget import BudgetAuthority
from digital_life.application.learning.activity_budget import ActivityBudgetAuthority
from digital_life.application.learning.runtime import RuntimeAuthority,qualified_plane_required
from digital_life.infrastructure.persistence.sqlite_write_monitor import callback_active


class LocalRuntimeOwners:
    NATIVE=frozenset(('personality_profiles','value_profiles','identity_anchors','memory_revisions','perception_observation_revisions','cognition_belief_revisions','cognition_concept_revisions'))
    STATIC=frozenset(('configuration_versions','model_versions','policy_versions','perception_signals','artifacts','tl_product','context_snapshots','thought_requests','thought_results','action_results','runtime_events','metric_definitions','rule_definitions','memory_retrieval_runs','tl_recall_item'))
    def __init__(self,store,identity):
        self.s=store;self.identity=identity;self.entries={};self.initializing={};self.read_opportunities={};self.settlements={}
        self.source=LocalEligibility(self);self.eligibility=ToolLearningEligibility(store,self.source,max_nodes=4096,max_rows=16384);self.snapshot_authority=LocalSnapshots(self);self.snapshots=SourceSnapshots(store,self.snapshot_authority)
        self.budget=LocalBudget(self);self.initial=LocalInitialBudget(self);self.runtime=LocalAssembly(self)
    def _material_boundary(self):
        from digital_life.infrastructure.persistence.tool_learning_readset import current_readset
        phase=current_readset(self.s)
        if phase is not None and not phase.check_depth:phase.checkpoint(include_artifacts=False)
        return phase
    def _policy_material(self):
        from digital_life.infrastructure.persistence.tool_learning_readset import facts
        # Preserve the original complete-row read and first-row semantics.
        return list(facts(self.s,'control_policy_epochs'))[0]
    def control(self,allow_stopped=False):
        from digital_life.infrastructure.persistence.tool_learning_readset import facts
        self._material_boundary()
        path=self.s.root/'control.sqlite'
        if path.is_symlink() or not path.exists():raise Forbidden('existing actual runtime control is required')
        db=self.s.control_reader()
        try:
            row=db.execute('SELECT * FROM instance_control_state WHERE instance_ref=?',(self.s.instance_id,)).fetchone()
            process=db.execute('SELECT * FROM process_runs WHERE id=? AND instance_ref=?',(self.identity.process_id,self.s.instance_id)).fetchone()
            if row is None or process is None or row['active_process_run_id']!=process['id'] or row['runtime_epoch']!=self.identity.epoch or process['pid']!=os.getpid() or process['exited_at'] is not None or (not allow_stopped and (process['user_stopped'] or row['user_stopped'])):raise Forbidden('current live process ownership/epoch does not match')
            if not allow_stopped:
                self.s.assert_execution_allowed()
                from digital_life.infrastructure.persistence.tool_learning_readset import schema_material_boundary
                with schema_material_boundary(self.s):
                    if not qualified_plane_required(self.s):raise Forbidden('strict runtime policy is no longer enabled')
                cfg=next(iter(facts(self.s,'control_latest_configuration')),None)
                if cfg is None:raise Forbidden('current immutable configuration missing')
                policy=self._policy_material()['policy_version_id']
                if next(iter(facts(self.s,'control_active_barrier',cfg['id'],policy)),None):raise Forbidden('active current-control source barrier prevents ordinary runtime use')
            return dict(row)
        finally:pass
    def configuration(self):
        from digital_life.infrastructure.persistence.tool_learning_readset import facts,track_artifact
        phase=self._material_boundary()
        row=next(iter(facts(self.s,'control_latest_configuration')),None)
        if row is None:raise Forbidden('current immutable configuration missing')
        identity=track_artifact(self.s,row['artifact_ref'])
        if identity[2]!=row['hash'] or identity[4]!='application/json':raise Conflict('current configuration artifact identity differs')
        key=(None if phase is None else phase.stamp,'TL-CONTROL-CONFIGURATION-1',tuple(row),identity,None if phase is None else phase.generation)
        prior=None if phase is None else phase.prepared_metadata(key)
        if prior is not None:return json.loads(prior[0])
        # A new phase must hash-check actual material, never reuse a process
        # global dictionary as proof of this phase's file/configuration state.
        value=self.eligibility.artifacts.read_artifact(row['artifact_ref'],fresh=phase is None)
        if phase is not None:phase.remember_prepared_metadata(key,dumps(value),'')
        return value
    def entry(self,module,purpose,recipient=None):
        self.control();t.enum(module,t.MODULES);t.enum(purpose,t.PURPOSES)
        recipient=recipient or self.configuration()['self_actor'];self.s.row('social_actors',recipient)
        entry=identifier();self.entries[entry]={'module':module,'purpose':purpose,'recipient':recipient}
        return entry,self.principal(entry)
    def principal(self,entry):
        self._material_boundary()
        binding=self.entries.get(entry)
        if binding is None:raise Forbidden('unknown trusted runtime channel')
        policy=self._policy_material()['policy_version_id'];actor=self.configuration()['self_actor']
        return {'actor':ref(self.s,actor,'social_actors'),'module':binding['module'],'recipient':ref(self.s,binding['recipient'],'social_actors'),'purpose':binding['purpose'],'authorization':ref(self.s,policy,'policy_versions')}
    def check(self,entry,principal=None,allow_stopped=False):
        self.control(allow_stopped=allow_stopped)
        if entry not in self.entries:raise Forbidden('actual runtime entry capability missing')
        if principal is not None and principal!=self.principal(entry):raise Forbidden('principal does not match the actual channel, purpose, recipient and current policy')
        return self.entries[entry]
    def token(self,origin,scope):
        self.s.row('object_registry',origin['id']);kind=origin['kind']
        revisions=self.s.db.execute('SELECT * FROM object_revision_registry WHERE instance_id=? AND id=?',(self.s.instance_id,origin['id'])).fetchone()
        if revisions:revision=revisions['revision_no']
        elif kind in ('memory_items','perception_observations','cognition_beliefs','cognition_concepts','tl_content','tl_representation_head'):
            row=self.s.db.execute('SELECT max(revision_no) FROM object_revision_registry WHERE instance_id=? AND object_id=?',(self.s.instance_id,origin['id'])).fetchone()
            if row is None or row[0] is None:raise Forbidden('actual native source revision missing')
            revision=row[0]
        elif kind in SNAPSHOT_KINDS:
            observed=self.s.db.execute("SELECT max(revision_no) FROM object_revision_registry WHERE instance_id=? AND object_id=? AND kind='runtime_events'",(self.s.instance_id,origin['id'])).fetchone()
            if observed is None or observed[0] is None:raise Forbidden('mutable source needs an actual authorized observed snapshot')
            revision=observed[0]
        elif kind in self.STATIC:revision=0
        else:raise Forbidden('source owner is not implemented')
        return {'object':deepcopy(origin),'revision':revision,'epoch':self.eligibility.current_epoch(origin,scope)}
    def _source_row(self,kind,key):
        from digital_life.infrastructure.persistence.tool_learning_readset import owner_source_row,OWNER_SOURCE_ROW_QUERIES
        if kind not in OWNER_SOURCE_ROW_QUERIES:return self.s.row(kind,key)
        return owner_source_row(self.s,kind,key)
    def source_access(self,entry,principal,origin,scope):
        self.check(entry,principal);kind=origin['kind'];row=self._source_row(kind,origin['id'])
        if kind in ('memory_items','memory_revisions'):
            from digital_life.application.services import Memory
            key=row['memory_id'] if kind=='memory_revisions' else row['id']
            if self._source_row('memory_items',key)['state']!='active':raise Forbidden('memory retention no longer permits this source')
            allowed=Memory(self.s).readers(key)
            if principal['actor']['id'] not in allowed or principal['recipient']['id'] not in allowed:raise Forbidden('actual source actor/recipient ACL denies use')
        elif kind=='perception_signals':
            allowed={self.configuration()['self_actor'],self.configuration()['controller']}
            if row['source_actor_id'] not in allowed:raise Forbidden('external source actor has no configured current use permission')
        elif kind in ('cognition_beliefs','cognition_concepts','cognition_belief_revisions','cognition_concept_revisions'):
            # Ordinary legacy cognition is a candidate source report, never a
            # substitute for native TL accepted experience.
            if principal['purpose'] in ('recall_experience','represent'):raise Forbidden('legacy cognition is not TL accepted experience')
        elif kind in SNAPSHOT_KINDS or kind in self.NATIVE or kind in self.STATIC or kind in ('tl_content','tl_content_revision','tl_representation_head','tl_representation'):pass
        else:raise Forbidden('unsupported actual source owner')
        return row


class LocalEligibility(EligibilityAuthority):
    def __init__(self,owner):self.o=owner;self._verified=None
    @contextmanager
    def verification_boundary(self):
        """Read-only local-owner memo, never spanning an actual callback.

        The caller holds dispatch_gate; all local checks below are pure reads.
        Core IM06 still walks current epochs/barriers. No generic authority or
        process/model callback is memoized, and each boundary starts empty.
        """
        from digital_life.infrastructure.persistence.tool_learning_meter import immutable_reference_boundary
        from digital_life.infrastructure.persistence.tool_learning_readset import shared_read_boundary
        previous=self._verified;self._verified=set()
        try:
            with immutable_reference_boundary(self.o.s),shared_read_boundary(self.o.s) if type(self) is LocalEligibility else nullcontext():yield
        finally:self._verified=previous
    def _already(self,kind,value):
        from digital_life.infrastructure.persistence.tool_learning_readset import current_readset
        phase=current_readset(self.o.s)
        if phase is not None:phase._sync_monitor()
        if phase is not None and not getattr(phase,'check_depth',0):phase.checkpoint(include_artifacts=False)
        key=c.fingerprint({'kind':kind,'value':value,'changes':self.o.s.db.total_changes,'generation':None if phase is None else phase.generation})
        key=(key,None if phase is None else phase.generation,self.o.s.db.total_changes)
        return key,not callback_active() and self._verified is not None and key in self._verified
    def _remember(self,key):
        if callback_active() or self._verified is None:return
        from digital_life.infrastructure.persistence.tool_learning_readset import current_readset
        phase=current_readset(self.o.s)
        if phase is not None:phase._sync_monitor()
        if key[1:]==(None if phase is None else phase.generation,self.o.s.db.total_changes):self._verified.add(key)
    def verify_version(self,entry,principal,token,stage):
        key,seen=self._already('version',[entry,principal,token,stage])
        if seen:return
        self.o.check(entry,principal);origin=token['object'];kind=origin['kind']
        if kind in SNAPSHOT_KINDS:
            from digital_life.infrastructure.persistence.tool_learning_readset import facts
            from digital_life.infrastructure.persistence.tool_learning_meter import logical_observer_required
            if logical_observer_required():
                # Existing computation collectors observe returned UUIDs; retain
                # their original event-id row rather than projecting it to 1.
                row=self.o.s.db.execute("SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=? AND kind='runtime_events'",(self.o.s.instance_id,origin['id'],token['revision'])).fetchone()
            else:row=next(iter(facts(self.o.s,'snapshot_bridge',origin['id'],token['revision'])),None)
            if row is None:raise Conflict('actual observed source snapshot version missing')
        elif kind in self.o.STATIC:
            from digital_life.infrastructure.persistence.tool_learning_readset import facts,can_share_material_facts
            actual=(next(iter(facts(self.o.s,'static_revision_number',origin['id'])),None)if can_share_material_facts(self.o.s)
                    else self.o.s.db.execute('SELECT revision_no FROM object_revision_registry WHERE instance_id=? AND id=?',(self.o.s.instance_id,origin['id'])).fetchone())
            if token['revision']!=(actual[0] if actual else 0):raise Conflict('actual immutable/static row version differs')
        else:
            from digital_life.infrastructure.persistence.tool_learning_readset import facts,can_share_material_facts
            actual=(next(iter(facts(self.o.s,'native_revision_identity',token['revision'],origin['id'],origin['id'])),None)if can_share_material_facts(self.o.s)
                    else self.o.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND revision_no=? AND (object_id=? OR id=?)',(self.o.s.instance_id,token['revision'],origin['id'],origin['id'])).fetchone())
            if actual is None:raise Conflict('actual native source revision missing')
        self._remember(key)
    def verify(self,entry,principal,token,scope,purpose,recipient,stage):
        key,seen=self._already('source',[entry,principal,token,scope,purpose,recipient,stage])
        if seen:return
        self.o.source_access(entry,principal,token['object'],scope)
        self._remember(key)
        # Immutable historical observations retain their original meaning.
        # Fresh equality for current live fields is a separately bound
        # complete-manifest obligation, not inferred from a stage string.
    def verify_registration(self,entry,principal,context,stage):
        self.o.check(entry,principal)
        meta=context.get('metadata',context);consumer=meta['consumer']
        row=self.o.s.row(consumer['kind'],consumer['id'])
        if consumer['kind'] in ('thought_requests','memory_retrieval_runs'):
            activity=self.o.s.row('activities',row['activity_id'])
            if activity['cancel_requested_at'] or activity['state'] in ('completed','failed','cancelled'):raise Forbidden('actual input consumer activity is no longer active')
        elif consumer['kind'] not in ('artifacts','runtime_events','thought_results','context_snapshots'):raise Forbidden('runtime is not this dependency consumer owner')
        if meta['dependency']['consumer_purpose']!=principal['purpose']:raise Forbidden('registered field purpose differs from channel')
        if consumer['kind']=='thought_requests':self._input_mapping(row,meta,context.get('body_digest'),require_digest='body_digest' in context)
    def _input_mapping(self,row,meta,digest=None,require_digest=False):
        fixed=self.o.read_opportunities.get('assembly:'+row['id'])
        if fixed is not None:
            matches=[field for field in fixed['manifest']['fields'] if field['path']==meta['field_path'] and any(dep==meta['dependency'] and field['dependency_scopes'][index]==meta['scope'] for index,dep in enumerate(field['dependencies']))]
            if len(matches)!=1 or require_digest and digest!=matches[0]['digest']:raise Conflict('registered input does not match its sealed actual field/source/scope/digest')
            return
        if row['output_schema_version']!=70 or row['instruction_version']!='tl-observation-1':raise Forbidden('thought input has no actual sealed assembly owner')
        packet=self.o.s.read_artifact(row['request_artifact_id'])
        if c.fingerprint(packet)!=row['request_hash']:raise Conflict('native observation packet digest differs')
        path=meta['field_path'];token=None;value=None
        if path=='/observation':token=packet['source_token'];value=packet['observation']
        elif path.startswith('/baselines/'):
            try:
                index=int(path.split('/')[-1])
                if index<0 or path!='/baselines/'+str(index):raise ValueError('noncanonical field index')
                value=packet['baselines'][index];token=value['token']
            except (ValueError,IndexError,KeyError):raise Forbidden('unknown native baseline input field')
        if token is None or meta['dependency']['expected']!=token or meta['dependency']['relation']!='read' or meta['scope']!=packet['scope']:raise Conflict('native observation field source/scope mapping differs')
        if require_digest and digest!={'algorithm':'sha256','hex':c.fingerprint(value)}:raise Conflict('native observation field body digest differs')
    def verify_callback(self,entry,principal,context,stage):
        self.o.check(entry,principal)
        if context['request'] is None:raise Forbidden('real runtime requires actual bound request')
        request=context['request'];row=self.o.s.row(request['kind'],request['id'])
        if request['kind']=='thought_requests':
            if row['runtime_epoch']!=self.o.identity.epoch or row['process_run_id']!=self.o.identity.process_id or row['expected_policy_epoch']!=self.o.s.rows('policy_epochs')[0]['epoch'] or row['deadline']<=utc():raise Conflict('actual thought control/configuration binding is stale')
            packet=self.o.s.read_artifact(row['request_artifact_id']);binding=packet.get('binding',{})
            if c.fingerprint(packet)!=row['request_hash'] or binding.get('configuration',{}).get('id')!=row['model_config_id'] or binding.get('model',{}).get('id')!=row['model_version_id'] or binding.get('process_run_id')!=row['process_run_id']:raise Conflict('actual thought packet and persisted route/process mapping differ')
            for item in context['inputs']:
                value=item['row']['body_digest'];digest={'algorithm':'sha256','hex':value} if value is not None else None
                self._input_mapping(row,item['metadata'],digest,require_digest=True)
        elif request['kind'] not in ('action_intents','memory_retrieval_runs','activities'):raise Forbidden('unsupported actual callback owner')
    def barrier_applies(self,*args):return None


class LocalSnapshots(SnapshotAuthority):
    def __init__(self,owner):self.o=owner
    def verify_source(self,entry,principal,origin,selector,scope,stage):self.o.source_access(entry,principal,origin,scope)
    def verify_capture(self,entry,principal,snapshot,stage):
        self.o.check(entry,principal)
        if snapshot['scope']['claim_target']!='source_report':raise Forbidden('observed internal state is only a source report')
    def _evidence_source(self,key):
        """Resolve a same-instance typed wrapper, never an independent fact."""
        store=self.o.s;storage=self.o.eligibility.artifacts
        evidence_ref=ref(store,key)
        storage.validate_ref(evidence_ref,expected_kind='evidence_items')
        evidence=store.row('evidence_items',key)
        target=evidence['origin_object_id'] or evidence['artifact_id']
        if target is None:raise Forbidden('state evidence has no actual source')
        origin=ref(store,target);storage.validate_ref(origin)
        if evidence['artifact_id'] is not None:
            artifact=ref(store,evidence['artifact_id'])
            storage.validate_ref(artifact,expected_kind='artifacts')
        if evidence['origin_revision_id'] is not None:
            revision=store.db.execute('SELECT object_id FROM object_revision_registry WHERE instance_id=? AND id=?',(store.instance_id,evidence['origin_revision_id'])).fetchone()
            if revision is None or evidence['origin_object_id'] is None or revision[0]!=evidence['origin_object_id']:
                raise Forbidden('state evidence revision has wrong source owner')
        return origin

    def dependencies(self,entry,principal,snapshot):
        self.o.check(entry,principal);result=[]
        # Explicit source/evidence columns are actual data lineage. Dimension,
        # profile and association IDs are technical identity, not a second
        # independent empirical source.
        from digital_life.application.learning.eligibility import ref
        from digital_life.application.learning.source_snapshot import SourceSnapshots
        snapshots=self.o.snapshots
        value=(snapshots._complete_origin_row(snapshot['origin'])
               if type(snapshots)is SourceSnapshots and snapshots.authority is self
               else self.o.s.row(snapshot['origin']['kind'],snapshot['origin']['id']));keys=[]
        for name in ('source_ref','evidence_id','source_evidence_id'):
            key=value.get(name)
            if type(key) is str:keys.append(key)
        for name in ('uncertainty_json','reason','metadata_json'):
            if type(value.get(name)) is not str:continue
            try:metadata=c.loads(value[name])
            except ContractError:continue
            if type(metadata) is dict:
                for field in ('evidence_refs','source_refs'):
                    for source in metadata.get(field,[]):
                        if type(source) is str:keys.append(source)
                        elif type(source) is dict and type(source.get('id')) is str:keys.append(source['id'])
                        else:raise Forbidden('state ancestry is not a typed actual source')
        table=snapshot['origin']['kind']
        for fk in self.o.s.db.execute('PRAGMA foreign_key_list('+table+')'):
            column=fk['from']
            if column in ('id','instance_id','activity_id','context_id') or column not in value:continue
            if fk['table']=='evidence_items' and fk['to']=='id':
                if value[column] is None:continue
                if type(value[column]) is not str:raise Forbidden('typed evidence reference must be an ID')
                # A typed source FK is lineage even when a computation does
                # not copy the evidence column into its projected selector.
                self._evidence_source(value[column]);keys.append(value[column]);continue
            if type(value[column]) is not str:continue
            if column not in snapshot['selector'] and column not in ('source_ref','evidence_id','source_evidence_id'):continue
            key=value[column]
            registered=self.o.s.db.execute('SELECT kind FROM object_registry WHERE instance_id=? AND id=?',(self.o.s.instance_id,key)).fetchone()
            if registered is None:continue
            kind=registered[0]
            if kind in ('personality-root','value-root','identity-root'):continue
            if kind in SNAPSHOT_KINDS:
                origin=ref(self.o.s,key)
                token=self.o.snapshots.capture_identity(entry,principal,origin,snapshot['scope'])
                result.append({'dependency':{'target':origin,'expected':token,'relation':'read','consumer_purpose':principal['purpose']},'scope':deepcopy(snapshot['scope'])})
            elif kind in self.o.NATIVE or kind in self.o.STATIC or kind in ('memory_items','cognition_beliefs','cognition_concepts'):
                keys.append(key)
            elif column in ('source_ref','evidence_id','source_evidence_id'):keys.append(key)
            else:raise Forbidden('copied state association has no actual source identity owner')
        for key in sorted(set(keys)):
            registered=self.o.s.db.execute('SELECT kind FROM object_registry WHERE instance_id=? AND id=?',(self.o.s.instance_id,key)).fetchone()
            if registered is None:raise Forbidden('state source reference has no real owner')
            origin=ref(self.o.s,key)
            if registered[0]=='evidence_items':origin=self._evidence_source(key)
            token=self.o.token(origin,snapshot['scope'])
            result.append({'dependency':{'target':origin,'expected':token,'relation':'read','consumer_purpose':principal['purpose']},'scope':deepcopy(snapshot['scope'])})
        # Persisted producer lineage is authoritative ancestry of this actual
        # mutable row, independent of which projected fields the computation
        # reads. Do not invent another source from its original Evidence.
        for row in self.o.s.db.execute('SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? ORDER BY id LIMIT 1025',(self.o.s.instance_id,snapshot['origin']['id'])):
            if len(result)>1024:raise Forbidden('mutable state lineage exceeds bounded source closure')
            meta=self.o.eligibility._metadata(row);dependency=deepcopy(meta['dependency']);dependency['consumer_purpose']=principal['purpose']
            result.append({'dependency':dependency,'scope':deepcopy(meta['scope'])})
        return result
    def verify_dependencies(self,entry,principal,snapshot,dependencies,stage):
        eligibility=self.o.eligibility
        for context in dependencies:
            dependency=context['dependency']
            if dependency['relation']!='delete':eligibility._check(entry,principal,dependency['expected'],context['scope'],principal['purpose'],principal['recipient'],'snapshot_retention')


class LocalBudget(BudgetAuthority):
    def __init__(self,owner):self.o=owner
    def verify_budget(self,entry,work,original_budget,request_budget,operation,stage):
        self.o.check(entry,allow_stopped=stage=='settle');activity=work['id'] if work.get('owner_kind')=='activities' else work['learning_activity_id']
        row=self.o.s.row('activities',activity)
        if stage!='settle' and (row['cancel_requested_at'] or row['deadline']<=utc()):raise Forbidden('actual resource owner is cancelled or expired')
    def verify_entry(self,entry,work,reservation,witness):
        self.o.check(entry)
        if witness.get('contract') not in ('TL-ENGINE-READ-ENTRY-1','TL-ENGINE-THOUGHT-ENTRY-1','TL-ENGINE-TOOL-ENTRY-1','TL-OBSERVATION-READ-ENTRY-1','TL-OBSERVATION-THOUGHT-ENTRY-1','TL-RUNTIME-STAGE-READ-ENTRY-1'):raise Forbidden('unknown actual callback witness')
        if witness.get('operation') is not None and witness['operation']!=reservation['operation']:raise Conflict('actual callback witness names another operation')
        operation=reservation['operation'];s=self.o.s;consumer=s.row(operation['kind'],operation['id']);source=None;scope=None
        if operation['kind']=='thought_attempts':
            origin=ref(s,consumer['request_id'],'thought_requests')
            ancestry=s.db.execute("SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? AND relation='read' ORDER BY id LIMIT 1",(s.instance_id,origin['id'])).fetchone()
            if ancestry is not None:
                scope=self.o.eligibility._metadata(ancestry)['scope'];source={'object':origin,'revision':0,'epoch':self.o.eligibility.current_epoch(origin,scope)}
        elif operation['kind']=='action_attempts':
            ancestry=s.db.execute("SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? AND relation='read' AND field_path='/model_derivation' LIMIT 1",(s.instance_id,consumer['intent_id'])).fetchone()
            if ancestry is not None:
                metadata=self.o.eligibility._metadata(ancestry);scope=metadata['scope'];source=metadata['dependency']['expected']
        elif operation['kind']=='memory_retrieval_runs':
            ancestry=s.db.execute("SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? AND relation='read' ORDER BY id LIMIT 1",(s.instance_id,operation['id'])).fetchone()
            if ancestry is not None:
                metadata=self.o.eligibility._metadata(ancestry);scope=metadata['scope'];source=metadata['dependency']['expected']
        if source is not None:
            from digital_life.application.learning.engine import _dependency
            for relation in ('read','delete'):_dependency(s,operation,source,scope,relation,'/entered_operation',self.o.principal(entry)['purpose'])
            activity=work['id'] if work.get('owner_kind')=='activities' else work['learning_activity_id']
            # The ledger retains billing facts, but its entry witness/source
            # hash is an actual erasable copy, not an untracked audit escape.
            _dependency(s,ref(s,activity,'activities'),source,scope,'delete','/budget_json/ledger/reservations/'+reservation['id']+'/entry',self.o.principal(entry)['purpose'])
            if reservation['kind']!='retrieval':_dependency(s,ref(s,reservation['id'],'budget_reservations'),source,scope,'delete','/actual_usage/entry',self.o.principal(entry)['purpose'])
    def verify_settlement(self,entry,work,reservation,actual):
        self.o.check(entry,allow_stopped=True)
        # Values must originate in this composition's controlled operation,
        # never in a model-produced or caller-reported JSON ledger.
        record=self.o.settlements.get(reservation['id'])
        if record is None or record['actual']!=actual:raise Forbidden('actual bounded operation measurement missing')


class LocalInitialBudget(ActivityBudgetAuthority):
    def __init__(self,owner):self.o=owner
    def verify_initial_caps(self,entry,activity,account,caps,policy):
        self.o.check(entry)
        if self.o.initializing.get(activity['id'])!={'account':account['id'],'caps':caps,'policy':policy}:raise Forbidden('only this actual new-activity creation can initialize original caps')
        active=self.o.s.rows('policy_epochs')[0]
        if policy['object']['id']!=active['policy_version_id'] or policy['revision']!=0 or policy['epoch']!=active['epoch']:raise Conflict('initial resource policy is not current')


class LocalAssembly(RuntimeAuthority):
    deduplicate_identical_fields=True
    def __init__(self,owner):self.o=owner
    def verify_assembly(self,entry,request,principal,manifest,stage):
        self.o.check(entry,principal)
        fixed=self.o.read_opportunities.get('assembly:'+request['id'])
        if fixed is None or fixed['manifest']!=manifest:raise Forbidden('complete actual owner-generated assembly manifest missing')
        row=self.o.s.row('thought_requests',request['id'])
        if row['runtime_epoch']!=self.o.identity.epoch or row['process_run_id']!=self.o.identity.process_id:raise Conflict('thought belongs to another process epoch')
        payload=fixed.get('input')
        if payload is not None:
            from digital_life.application.behavior.behavior_policy import BehaviorPolicy
            from digital_life.application.behavior.goal_regulation import GoalRegulation
            from digital_life.application.behavior.habit_learning import HabitLearning
            from digital_life.application.behavior.people_relations import PeopleRelations
            from digital_life.application.memory.memory_quality import MemoryQuality
            from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
            from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
            BehaviorPolicy(self.o.s).check(payload);GoalRegulation(self.o.s).check_binding(payload)
            HabitLearning(self.o.s).check(payload);PeopleRelations(self.o.s).check(row['activity_id'],payload);MemoryQuality(self.o.s).check(payload)
            AutonomyAgenda(self.o.s).check(payload,row['activity_id']);SelfMaintenance(self.o.s).check(payload)
    def verify_retention(self,entry,request,principal,manifest,stage):self.verify_assembly(entry,request,principal,manifest,stage)
    def verify_health(self,entry,request,principal,stage):
        from digital_life.application.behavior.goal_regulation import GoalRegulation
        from digital_life.application.learning.health import CurrentHealthProbe
        self.o.check(entry,principal);s=self.o.s;fixed=self.o.read_opportunities.get('assembly:'+request['id'])
        if fixed is None:return
        payload=fixed['input'];regulation=GoalRegulation(s)
        if not regulation.check_binding(payload):return
        found=s.db.execute('SELECT * FROM thought_requests WHERE instance_id=? AND id=?',(s.instance_id,request['id'])).fetchone()
        # Retaining a newly prepared packet precedes insertion of its request.
        # Only our sealed original activity binding can be used in that phase;
        # actual callback paths additionally require the persisted request in
        # Runtime._local, so this is not a missing-row execution grant.
        if found is None:
            activity=fixed.get('activity_ref');deadline=fixed.get('deadline')
            if not isinstance(activity,dict) or activity.get('kind')!='activities' or activity.get('instance_id')!=s.instance_id or deadline is None:raise Forbidden('preparation lacks a sealed real activity/deadline')
            actual=s.row('activities',activity['id'])
            if actual['state']!='running' or actual['cancel_requested_at']:raise Forbidden('sealed preparation activity is no longer running')
            row={'activity_id':activity['id'],'deadline':deadline}
        else:row=dict(found)
        health=CurrentHealthProbe(s,row['activity_id'],deepcopy(request))
        result=regulation.assess(row['activity_id'],required_tokens=0,required_attempts=0,current_health=health)
        self.o.check(entry,principal)
        if row['deadline']<=utc() or not result['eligible']:raise Forbidden('current health/goal admission blocked: '+','.join(result['reasons']))
        if found is not None:
            from digital_life.application.learning.engine import _dependency
            with s.tx():
                event=s.event('strict.health.guard',payload=dict(health.audit(),stage=stage,eligible=True,configuration=payload['goal_regulation']['configuration']),source='strict.health.guard',key=None,activity=row['activity_id'],lane='control')
                token={'object':deepcopy(request),'revision':0,'epoch':0};scope=fixed['manifest']['fields'][0]['scope']
                for consumer in (ref(s,event),ref(s,s.row('runtime_events',event)['payload_artifact_id'])):_dependency(s,consumer,token,scope,'delete','/request','learn')
        self.o.check(entry,principal)
        if row['deadline']<=utc():raise Forbidden('current health check crossed request deadline')
    def verify_live(self,entry,request,principal,field,stage):
        self.o.check(entry,principal)
        for index,dependency in enumerate(field['dependencies']):
            if dependency['relation']=='delete':continue
            token=dependency['expected'];source_scope=field['dependency_scopes'][index]
            if field['usage']=='live_state':
                if token['object']['kind'] in SNAPSHOT_KINDS:self.o.snapshots.fixed(entry,principal,token,source_scope)
                elif token['object']['kind'] in ('personality_profiles','value_profiles','identity_anchors'):
                    table=token['object']['kind'];actual=self.o.s.db.execute('SELECT id FROM '+table+' WHERE instance_id=? ORDER BY version DESC LIMIT 1',(self.o.s.instance_id,)).fetchone()
                    if actual is None or actual[0]!=token['object']['id']:raise Conflict('live native profile changed after fixed preparation')
                else:raise Forbidden('current-state native owner has no explicit live resolver')
            elif field['usage']=='current_control':
                self.o.source_access(entry,principal,token['object'],source_scope)
                kind=token['object']['kind'];key=token['object']['id']
                if kind=='tl_recall_item':
                    self._current_item(entry,principal,token,source_scope)
                elif kind in ('configuration_versions','model_versions'):
                    latest=self.o.s.db.execute('SELECT id FROM '+kind+' WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.o.s.instance_id,)).fetchone()
                    if latest is None or latest[0]!=key:raise Conflict('actual current model/configuration binding changed')
                elif kind=='policy_versions':
                    if self.o.s.rows('policy_epochs')[0]['policy_version_id']!=key:raise Conflict('actual current runtime policy changed')
                elif kind in ('tl_content','tl_representation_head'):
                    owner=self.o.s.row(kind,key);column='head_revision_id' if kind=='tl_content' else 'representation_id'
                    actual=self.o.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.o.s.instance_id,key,token['revision'])).fetchone()
                    if actual is None or owner[column]!=actual[0]:raise Conflict('selected current accepted/group member head changed')
                elif kind in self.o.STATIC or kind in self.o.NATIVE or kind in SNAPSHOT_KINDS:
                    # Immutable supporting observations of an accepted item
                    # remain historical; its actual current native heads and
                    # every fixed group member above are separately mandatory.
                    if not field['path'].startswith('/input/recall/items/'):raise Forbidden('non-control source cannot impersonate current control')
                else:raise Forbidden('current-control source kind has no actual current resolver')
    def _current_item(self,entry,principal,token,scope):
        self.o.eligibility._check(entry,principal,token,scope,principal['purpose'],principal['recipient'],'current_accepted_item')
        s=self.o.s;row=s.row('tl_recall_item',token['object']['id'])
        if row['kind']!='accepted_content':raise Forbidden('current accepted input cannot be a legacy/candidate item')
        body=self.o.eligibility.artifacts.read_artifact(row['payload_artifact_id'],'RecallItem')
        if body['usage_state']!='current' or body['representation_ref']['status']!='known':raise Forbidden('accepted current item mapping unavailable')
        representation=s.row('tl_representation',body['representation_ref']['value']['id']);series=s.row('tl_representation_head',representation['series_id']);content=s.row('tl_content',series['content_id'])
        if representation['state']!='ready' or series['representation_id']!=representation['id'] or content['head_revision_id']!=representation['content_revision_id']:raise Conflict('accepted input is no longer an actual ready current head')
        if representation['group_id']:
            group=s.row('tl_group',representation['group_id'])
            if group['state']!='ready':raise Forbidden('fixed atomic group is not currently ready')
        # Every fixed group/content/representation member in the canonical
        # trace is checked, not just this displayed member or old ready bool.
        for key,sc,expected,path in self.o.eligibility._upstream(token,scope,{'remaining':self.o.eligibility.max_rows}):
            if expected is None or 'delete' in path:continue
            kind=expected['object']['kind']
            if kind not in ('tl_content','tl_representation_head'):continue
            current=s.row(kind,key);column='head_revision_id' if kind=='tl_content' else 'representation_id'
            fixed=s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(s.instance_id,key,expected['revision'])).fetchone()
            if fixed is None or current[column]!=fixed[0]:raise Conflict('another required current group member changed')



from contextlib import contextmanager
from digital_life.application.learning.recall import RecallAuthority

class LocalRecall(RecallAuthority):
    """Actual purpose/source/account binding for normal execution recall."""
    def __init__(self,owner):self.o=owner;self.reader=None;self.reservation=None
    def verify_request(self,entry,request,stage):
        self.o.check(entry,request['principal'])
        if request['entry']!='execution':raise Forbidden('runtime entry cannot impersonate controller audit')
        control=request['control'];actual=self.o.s.rows('policy_epochs')[0]
        if control['runtime_epoch']!=self.o.identity.epoch or control['policy']['object']['id']!=actual['policy_version_id'] or control['policy']['epoch']!=actual['epoch']:raise Conflict('recall current runtime/policy binding changed')
        eligibility=self.o.eligibility
        for token in control['source_epochs']:
            eligibility._check(entry,request['principal'],token,request['target_scope'],request['principal']['purpose'],request['principal']['recipient'],'recall_query_source')
    def verify_candidate_access(self,entry,request,candidate,stage):self.o.source_access(entry,request['principal'],candidate,request['target_scope'])
    def verify_retention(self,entry,request,item,stage):self.o.check(entry,request['principal'])
    def execution_reservation(self,entry,request,run):
        self.o.check(entry,request['principal'])
        if self.reservation is None or self.reservation['operation']!=run:raise Forbidden('this actual recall run has no original entered slice')
        return slot(self.reservation['id'])
    def verify_execution_accounting(self,entry,request,context,read_context,stage):
        self.o.check(entry,request['principal'])
        if self.reservation is None or read_context['reservation_id']!=self.reservation['id'] or context['reservation']['operation']!=self.reservation['operation']:raise Forbidden('read accounting is not this original run')
    def verify_trace(self,entry,request,result,stage):self.o.check(entry,request['principal'])
    def verify_fallback(self,entry,request):self.o.check(entry,request['principal'])
    def scope_matches(self,entry,request,scope):
        self.o.check(entry,request['principal'])
        if request['principal']['purpose']=='recall_episode' and request['target_scope']['property']=='runtime_source_report' and scope['claim_target']=='source_report':return True
        return c.fingerprint(scope)==c.fingerprint(request['target_scope'])
    def count_tokens(self,entry,request,item):
        self.o.check(entry,request['principal'])
        # Packaging cap is bytes, not a provider tokenizer claim. Actual model
        # preflight separately counts the complete final wire under its owner.
        return len(c.fingerprint(item)) + len(__import__('digital_life.domain.contracts',fromlist=['dumps']).dumps(item).encode('utf-8'))
    @contextmanager
    def read_boundary(self,entry,request,reader):
        previous=self.reader;self.reader=reader
        try:yield
        finally:self.reader=previous
    def source_token(self,entry,request,evidence):
        self.o.check(entry,request['principal']);return self.o.token(evidence['source'],request['target_scope'])
    def legacy_material(self,entry,request,target,row):
        self.o.check(entry,request['principal'])
        if target['kind']!='memory_revisions':raise Forbidden('unmapped cognition cannot replace normal tracked memory')
        sources=[];roles=set();s=self.o.s
        for link in s.db.execute('SELECT * FROM memory_source_links WHERE instance_id=? AND memory_revision_id=? ORDER BY id LIMIT 129',(s.instance_id,row['id'])):
            if len(sources)>=128:raise Forbidden('memory source closure exceeds declared local bound')
            roles.add(link['role'])
            evidence=s.row('evidence_items',link['evidence_id']);key=evidence['origin_object_id'];artifact=evidence['artifact_id'];source_kind='system_event'
            if key:
                origin=ref(s,key);kind=origin['kind'];original=s.row(kind,key)
                if kind=='perception_signals':
                    if request['entry']=='execution' and request['principal']['purpose']=='recall_episode' and request['activity_ref']['status']=='known' and key==s.row('activities',request['activity_ref']['value']['id'])['trigger_event_id']:
                        raise Forbidden('current trigger remains primary input, not an old memory hit')
                    artifact=original['artifact_id'];source_kind='user_statement'
                elif kind=='runtime_events':artifact=original['payload_artifact_id'];source_kind='system_event'
                elif kind=='thought_results':artifact=original['response_artifact_id'];source_kind='model_output'
                elif kind=='action_results':artifact=original['receipt_artifact_id'];source_kind='tool_result'
                else:raise Forbidden('memory has an unsupported original evidence owner')
            elif artifact:origin=ref(s,artifact)
            else:raise Forbidden('memory original source is unavailable')
            if not artifact:raise Forbidden('original source bytes are not mapped')
            material=s.row('artifacts',artifact)
            sources.append({'source':origin,'source_kind':source_kind,'original_result':slot(ref(s,key)) if key and origin['kind']=='action_results' else slot(),
                'receipt':slot(ref(s,artifact)) if source_kind=='tool_result' else slot(),'artifact':ref(s,artifact),'source_revision':slot(),'digest':{'algorithm':'sha256','hex':material['hash']},'media_type':material['media_type'],
                'encoding':slot('utf-8'),'view':slot(),'view_digest':slot(),'locator':{'kind':'whole_artifact','justification':'one actual original report artifact; not independent world evidence'},'observed_at':slot(original['recorded_at']) if key else slot(),
                'reported_at':slot(original['recorded_at']) if key else slot(),'origin_method':{'name':'original-source-receipt','version':'1','request_ref':slot(),'model_config_ref':slot()},'coverage':{'state':'partial','domain':slot('one original source artifact'),'scanned':1,'limit':1,'truncated':False,'missing':[]},'derivation_refs':[],'access_dependencies':[]})
        if not sources:raise Forbidden('unproven legacy memory cannot enter a normal model packet')
        encoding=row['encoding_method']
        if roles=={'observed'} and encoding=='explicit-v1':processing='raw'
        elif roles=={'summarized'} and encoding in ('derived-v1','extractive-consolidation-v1'):processing='transform'
        elif roles=={'inferred'} and encoding=='model-response-v1':processing='infer'
        elif roles=={'observed'} and encoding=='correction-v1':processing='transform'
        else:raise Forbidden('unknown or mixed native encoding/provenance cannot masquerade as raw original')
        return {'kind':'episode','scope':deepcopy(request['target_scope']),'source_refs':sources,'origin_kind':sources[0]['source_kind'],'processing':processing,'values':[],
                'limitations':['Historical reported text, not a current state or accepted world fact.']}


from digital_life.application.learning.eligibility import _signature_method_spec
_SIGNATURE_SOURCE_METHODS=_signature_method_spec(LocalEligibility)
_SIGNATURE_OWNER_METHODS=_signature_method_spec(LocalRuntimeOwners)
