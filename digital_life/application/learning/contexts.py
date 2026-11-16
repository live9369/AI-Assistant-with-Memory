"""Existing calculated life features, with actual row/artifact provenance capture."""
from contextlib import contextmanager
from copy import deepcopy
from types import MethodType
import re
from digital_life.domain.contracts import ContractError,Forbidden
from digital_life.application.learning.eligibility import ref
from digital_life.domain.tool_learning_sources import SNAPSHOT_KINDS,OPERATIONAL_SELECTORS


@contextmanager
def source_preparation_observer_boundary(collector):
    """Authenticate the exact application collector before sharing facts."""
    from digital_life.infrastructure.persistence.tool_learning_meter import _ACTIVE,_source_preparation_observer_boundary
    meter=_ACTIVE.get();observer=None if meter is None else getattr(meter,'row_observer',None)
    trusted=(type(collector)is DomainReadCollector and collector.busy is True
             and type(observer)is MethodType and getattr(observer,'__self__',None)is collector
             and getattr(observer,'__func__',None)is DomainReadCollector.on_row)
    if not trusted:
        yield
        return
    with _source_preparation_observer_boundary(meter,observer,collector):yield


@contextmanager
def calculation_read_boundary(engine):
    """Fixed local calculation/checks; share facts, never per-use permission.

    A caller must open a new boundary after calculation writes, before checking
    resulting material or live bindings. Existing writes and transaction ends
    invalidate facts normally; this grants no cross-write cache exemption.
    """
    from digital_life.application.learning.runtime_owners import LocalEligibility
    source=engine.owners.source
    if type(source)is not LocalEligibility:
        yield
        return
    with source.verification_boundary():
        previous=source._verified;source._verified=None
        try:yield
        finally:source._verified=previous


@contextmanager
def calculated_retention_read_boundary(engine):
    """Fresh material only, after calculation and before bundle retention."""
    if engine.runtime.eligibility.authority is not engine.owners.source:
        yield
        return
    with calculation_read_boundary(engine):yield


@contextmanager
def live_binding_read_boundary(engine):
    """Known local snapshot/assembly callbacks keep their original checks."""
    from digital_life.application.learning.runtime_owners import LocalAssembly,LocalSnapshots
    from digital_life.application.learning.source_snapshot import SourceSnapshots
    if (type(engine.owners.runtime)is not LocalAssembly
            or engine.owners.runtime.o is not engine.owners
            or type(engine.owners.snapshots)is not SourceSnapshots
            or engine.owners.snapshots.authority is not engine.owners.snapshot_authority
            or type(engine.owners.snapshots.authority)is not LocalSnapshots
            or engine.owners.snapshots.authority.o is not engine.owners
            or engine.runtime.eligibility.authority is not engine.owners.source
            or engine.owners.eligibility.authority is not engine.owners.source):
        yield
        return
    with calculation_read_boundary(engine):yield


class DomainReadCollector:
    def __init__(self,engine,entry,principal,scope,created):
        self.e=engine;self.o=engine.owners;self.s=engine.s;self.entry=entry;self.principal=principal;self.scope=scope;self.created=created
        self.tokens={};self.busy=False;self.original=None
    @contextmanager
    def _preparing_source(self):
        previous=self.busy;self.busy=True
        try:
            with source_preparation_observer_boundary(self):yield
        finally:self.busy=previous
    def observe(self,key,columns=None):
        if self.busy or key in self.created:return
        if type(key) is not str or not re.fullmatch('[0-9a-f]{32}',key):return
        with self._preparing_source():
            registered=self.s.db.execute('SELECT kind FROM object_registry WHERE instance_id=? AND id=?',(self.s.instance_id,key)).fetchone()
            if registered is None:return
            kind=registered[0]
            if kind in ('personality-root','value-root','identity-root'):return
            if kind=='evidence_items':
                row=self.s.row(kind,key);target=row['origin_object_id'] or row['artifact_id']
                if target is None:raise Forbidden('calculated feature evidence has no source')
                self.busy=False;self.observe(target);self.busy=True;return
            origin=ref(self.s,key)
            if kind in SNAPSHOT_KINDS:
                # This is the trusted M17 owner already under the active
                # calculated-context transaction/gate, never a caller flag.
                selector=sorted(set(columns or ('id',)) & self.s.columns[kind])
                if kind in OPERATIONAL_SELECTORS:selector=sorted(set(selector)&OPERATIONAL_SELECTORS[kind])
                token=self.o.snapshots._capture(self.entry,self.principal,origin,selector,self.scope)
            elif kind in self.o.STATIC or kind in self.o.NATIVE or kind in ('memory_items','cognition_beliefs','cognition_concepts'):
                token=self.o.token(origin,self.scope)
            else:raise Forbidden('calculated feature read has no actual source/version owner: '+kind)
            self.e.runtime.eligibility._check(self.entry,self.principal,token,self.scope,self.principal['purpose'],self.principal['recipient'],'calculated_context_read')
            self.tokens[(key,token['revision'])]=deepcopy(token)
    def on_row(self,row):
        if self.busy:return
        values=dict(row) if hasattr(row,'keys') else {}
        for name,value in values.items():self.observe(value,values.keys() if name=='id' else None)
    def read_artifact(self,key):
        if self.busy:return self.original(key)
        with self._preparing_source():
            owners=[]
            for table,column in (('configuration_versions','artifact_ref'),('model_versions','artifact_ref'),('runtime_events','payload_artifact_id'),('thought_requests','request_artifact_id'),('thought_results','response_artifact_id')):
                owners.extend(row[0] for row in self.s.db.execute('SELECT id FROM '+table+' WHERE instance_id=? AND '+column+'=?',(self.s.instance_id,key)))
            if not owners:owners=[key]
        for owner in owners:self.observe(owner)
        with self._preparing_source():return self.original(key)
    @contextmanager
    def installed(self,meter):
        self.original=self.s.read_artifact;previous=getattr(meter,'row_observer',None)
        self.s.read_artifact=self.read_artifact;meter.row_observer=self.on_row
        try:yield self
        finally:self.s.read_artifact=self.original;meter.row_observer=previous


def calculate(store,activity,context,task,recalled,conversation=None):
    """Keep the existing T1—T13 calculations; raw records are additional audit."""
    from digital_life.application.services import Personality,Values,Habits,States
    from digital_life.application.behavior.goal_regulation import GoalRegulation
    from digital_life.application.memory.memory_quality import MemoryQuality
    from digital_life.application.behavior.people_relations import PeopleRelations
    from digital_life.application.behavior.habit_learning import HabitLearning
    from digital_life.application.behavior.personality_growth import PersonalityGrowth
    from digital_life.application.behavior.behavior_policy import BehaviorPolicy
    from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
    from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
    from digital_life.application.autonomy.task_loop import TaskLoop
    from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
    from digital_life.application.autonomy.exploration import Exploration
    memories=[]
    for item in recalled['items']:
        if item['memory_revision']['status']!='known':continue
        version=item['memory_revision']['value'];revision=store.db.execute('SELECT id FROM memory_revisions WHERE instance_id=? AND memory_id=? AND revision_no=?',(store.instance_id,version['object']['id'],version['revision'])).fetchone()
        if revision is None:raise Forbidden('calculated memory feature lacks actual fixed revision')
        memories.append({'revision_id':revision[0],'content':item['body'],'source_kind':'reported-episode','selection_reason':item['selection']['reason']})
    from digital_life.application.services import Cognition
    Cognition(store).episode(activity,context,task)
    habits=Habits(store).opportunities(activity,{'source':'user','task':task})
    payload={'schema_version':1,'activity_id':activity,'task':task,'selected_memories':memories,
        'personality':Personality(store).activate(activity,context,{row['name']:1 for row in Personality(store).current()['traits']}),
        'values':Values(store).activate(activity,context),'habit_suggestions':[h for h in habits if not h.get('managed') or h['state']=='active'],'states':States(store).snapshot()}
    candidates={
        'goal_regulation':GoalRegulation(store).context(activity),'self_maintenance':SelfMaintenance(store).context(),
        'autonomy_agenda':AutonomyAgenda(store).context(activity),'memory_quality':MemoryQuality(store).context(memories,None),
        'relationships':PeopleRelations(store).context(activity),'habit_learning':HabitLearning(store).context(habits),
        'personality_growth':PersonalityGrowth(store).context()}
    for name,value in candidates.items():
        if value is not None:payload[name]=value
    if TaskLoop(store).config(activity):payload['task_loop']=TaskLoop(store).context(activity)
    if Exploration(store).binding(activity):payload['exploration']=Exploration(store).context(activity)
    cognitive=CognitiveUpdates(store)
    if cognitive.enabled():
        payload['cognition_configuration']=cognitive.generation();payload['cognition_sources']=cognitive.sources(activity,payload);payload['cognition_snapshot']=cognitive.snapshot()
        for belief in payload['cognition_snapshot']:
            belief['legacy_acceptance_state']=belief.get('acceptance_state')
            belief['acceptance_state']='candidate'
            belief['runtime_qualification']='legacy source report; native TL acceptance not established'
    if conversation is not None:payload['conversation_context']=deepcopy(conversation)
    behavior=BehaviorPolicy(store).context(activity,payload)
    if behavior is not None:payload['behavior_policy']=behavior
    return payload


def unwrapped_request_payload(store,request):
    value=store.read_artifact(request['request_artifact_id'])
    return value['input'] if type(value) is dict and value.get('contract')=='TL-ENGINE-THOUGHT-1' else value
