"""Strict ordinary Engine composition, fixed packets and original accounts."""
from copy import deepcopy
import json
import sqlite3
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,identifier,utc,dumps,sha,text
from digital_life.domain import tool_learning_contract as c
from digital_life.application.learning.eligibility import ref,slot,insert,ToolLearningEligibility
from digital_life.application.learning.activity_budget import ActivityResourceBudget,ActivityBudgetAuthority
from digital_life.application.learning.budget import DIMENSIONS
from digital_life.application.learning.runtime import ToolLearningRuntime
from digital_life.application.learning.runtime_owners import LocalRuntimeOwners
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.infrastructure.llm.inference import configured_reasoner
from digital_life.infrastructure.llm.fresh_learning import FreshActionProvider


def source_scope(store,property='runtime_source_report'):
    return {'subject':slot(ref(store,store.config()['self_actor'])),'subject_label':slot(),'property':property,'claim_target':'source_report',
        'temporal':{'kind':'observation','start':slot(),'end':slot(),'bounds':'unknown'},'conditions':slot({'interpretation':'reported source contents, not established world truth'}),
        'domain':slot('digital_life_runtime'),'unit':slot(),'granularity':slot('one fixed observed source field'),
        'coverage':{'state':'partial','domain':slot('bounded supplied sources'),'scanned':0,'limit':0,'truncated':False,'missing':[]},'exceptions':[],
        'limitations':['Reports stored observations only; missing or unsupported material remains unknown.']}


def active_profile(store):
    epoch=store.rows('policy_epochs')[0];row=store.row('policy_versions',epoch['policy_version_id']);scope=c.loads(row['scope'])
    feature=scope.get('tool_learning_runtime',{})
    from digital_life.application.learning.runtime import qualified_plane_required,strict_feature_enabled
    strict_feature_enabled(store)  # Validate the closed learning policy even when the qualified plane is mandatory.
    if feature.get('contract')!='TL-STRICT-RUNTIME-1' or not qualified_plane_required(store):raise Forbidden('qualified runtime not enabled by current policy')
    caps=deepcopy(feature.get('ordinary_activity_caps'))
    if not isinstance(caps,dict) or set(caps)!={'max_input_tokens','max_output_tokens','max_attempts','max_tool_calls','max_scan','max_items','max_bytes','elapsed_ms'}:raise Forbidden('original ordinary-activity eight-dimensional policy caps missing')
    if any(type(v) is not int or v<0 for v in caps.values()) or not caps['elapsed_ms']:raise ContractError('invalid original activity policy caps')
    return epoch,row,caps


def _dependency(store,consumer,token,scope,relation,path,purpose):
    dep={'target':deepcopy(token['object']),'relation':relation,'expected':deepcopy(token),'consumer_purpose':purpose}
    metadata={'contract':'TL-DEPENDENCY-1','consumer':deepcopy(consumer),'dependency':dep,'field_path':path,'scope':deepcopy(scope)}
    version=store.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(store.instance_id,token['object']['id'],token['revision'])).fetchone()
    insert(store,'tl_dependency',consumer_ref_id=consumer['id'],source_ref_id=token['object']['id'],source_revision_id=version[0] if version else None,relation=relation,purpose=purpose,expected_epoch=token['epoch'],field_path=path,metadata_artifact_id=store.artifact(metadata))



def _retain_output_lineage(store,request_id,result_id,artifact_id,manifest):
    """A result is an occurrence; a deduplicated body retains their union."""
    result=store.row('thought_results',result_id)
    if (result['request_id']!=request_id or result['response_artifact_id']!=artifact_id
            or result['parsed_artifact_id']!=artifact_id):
        raise Conflict('response lineage does not bind the actual result/request/body')
    prefix='/_strict_response_occurrences/v1/'+result_id
    for field in manifest['fields']:
        for index,dependency in enumerate(field['dependencies']):
            original_path=field['path']+'/'+str(index)
            for consumer in (ref(store,result_id),ref(store,artifact_id)):
                path=prefix+original_path if consumer['kind']=='artifacts'else original_path
                _dependency(store,consumer,dependency['expected'],field['dependency_scopes'][index],dependency['relation'],path,'learn')


def submit_inbound(store,task,key,source):
    """Only an already-authenticated real control-plane receipt creates input."""
    text(task);text(key,240);epoch,policy,caps=active_profile(store)
    path=store.root/'control.sqlite'
    if path.is_symlink() or not path.exists():raise Forbidden('authenticated input receipt missing')
    control=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);control.row_factory=sqlite3.Row
    try:
        receipt=control.execute("SELECT * FROM inbound_requests WHERE instance_ref=? AND source=? AND source_event_id=? AND state IN ('received','transferring','delivered')",(store.instance_id,source,key)).fetchone()
        if receipt is None or receipt['authority_ref']!=store.config()['controller'] or receipt['expires_at']<=utc() or receipt['payload_hash']!=sha(dumps({'text':task})):raise Forbidden('actual controller receipt does not bind this new input')
        receipt_id=receipt['id']
    finally:control.close()
    return _create_original_input(store,task,key,source,caps,epoch,policy,receipt_id,store.config()['controller'])

def _create_original_input(store,task,key,source,caps,epoch,policy,receipt_id,actor,*,due_at=None):
    # Private creation helper; callers must complete their distinct real authority checks.
    with dispatch_gate(store.root),store.tx():
        old=store.db.execute('SELECT * FROM perception_signals WHERE instance_id=? AND external_id=?',(store.instance_id,source+':'+key)).fetchone()
        if old:
            if store.read_artifact(old['artifact_id'])!={'text':task}:raise Conflict('same input identity has different contents')
            activity=store.db.execute('SELECT id FROM activities WHERE instance_id=? AND trigger_event_id=?',(store.instance_id,old['id'])).fetchone()
            if activity is None:raise Conflict('existing input has no original activity')
            return activity[0]
        cfg=store.config();channel=store.rows('perception_channels')[0]['id']
        if actor==cfg['self_actor']:
            row=store.db.execute("SELECT id FROM perception_channels WHERE instance_id=? AND kind='internal' LIMIT 1",(store.instance_id,)).fetchone()
            channel=row[0] if row else store.insert('perception_channels',kind='internal',capabilities=['thought-trigger'],verification_method='runtime-generated',state='available')
        artifact=store.artifact({'text':task})
        signal=store.insert('perception_signals',channel_id=channel,source_actor_id=actor,external_id=source+':'+key,artifact_id=artifact,received_at=utc())
        activity=store.insert('activities',trigger_event_id=signal,state='pending',budget_json={'tokens':caps['max_input_tokens']+caps['max_output_tokens'],'tool_calls':caps['max_tool_calls']},release_id='UNBOUND:awaiting-real-runtime',publication_state='ready',deadline=min(utc(caps['elapsed_ms']/1000),due_at) if due_at else utc(caps['elapsed_ms']/1000))
        account=store.insert('activity_budget_accounts',activity_id=activity,token_limit=caps['max_input_tokens']+caps['max_output_tokens'],tool_call_limit=caps['max_tool_calls'],attempt_limit=caps['max_attempts'],time_limit_ms=caps['elapsed_ms'])
        budget={k:v for k,v in caps.items() if k!='elapsed_ms'};budget.update(account_ref=ref(store,account),deadline=store.row('activities',activity)['deadline'])
        policy_token={'object':ref(store,policy['id']),'revision':0,'epoch':epoch['epoch']}
        class InitialReceiptAuthority(ActivityBudgetAuthority):
            def verify_initial_caps(self,entry,actual_activity,actual_account,actual_caps,actual_policy):
                if entry!=receipt_id or actual_activity['id']!=activity or actual_account['id']!=account or actual_caps!=budget or actual_policy!=policy_token:raise Forbidden('initial caps are not this authenticated creation')
        ActivityResourceBudget.initialize(store,receipt_id,activity,budget,policy_token,InitialReceiptAuthority())
        context=store.insert('context_snapshots',activity_id=activity,context_schema='strict-source-context-1',attributes_json={'task':task,'source':source,('control_receipt' if actor==cfg['controller'] else 'self_intent_admission'):receipt_id})
        from digital_life.application.services import Memory,Goals,Relationships
        evidence=store.evidence(object_id=signal,method='authenticated-controller-input' if actor==cfg['controller'] else 'derived-self-intent')
        memory=Memory(store).encode(task,evidence,source_role='observed' if actor==cfg['controller'] else 'inferred');goal=Goals(store).create(signal,task)
        Goals(store).transition(goal,'accepted',signal);Goals(store).transition(goal,'active',signal);Goals(store).motivate(goal,activity,internal=actor==cfg['self_actor'])
        interaction=Relationships(store).record(actor,signal,activity) if actor==cfg['controller'] else None
        scope=source_scope(store);token={'object':ref(store,signal),'revision':0,'epoch':0}
        consumers=[ref(store,artifact),ref(store,context),ref(store,memory['memory_id']),ref(store,memory['revision_id']),ref(store,goal)]
        if interaction:consumers.append(ref(store,interaction))
        for consumer in consumers:
            _dependency(store,consumer,token,scope,'read','/original_input','recall_episode')
            _dependency(store,consumer,token,scope,'delete','/original_input','recall_episode')
        event=store.event('activity.created',payload={'task':task,'goal':goal,'context':context,('control_receipt' if actor==cfg['controller'] else 'self_intent_admission'):receipt_id,'strict':True,'source_role':'external_statement' if actor==cfg['controller'] else 'derived_self_intent'},source=source,key=key,activity=activity)
        _dependency(store,ref(store,event),token,scope,'read','/original_input','recall_episode')
        _dependency(store,ref(store,store.row('runtime_events',event)['payload_artifact_id']),token,scope,'delete','/original_input','recall_episode')
        from digital_life.application.runtime.scheduling import Queue
        Queue(store).enqueue('think',activity)
        return activity


class StrictEngine:
    def __init__(self,store,identity,provider=None):
        self.s=store;self.identity=identity;self.owners=LocalRuntimeOwners(store,identity)
        self.runtime=ToolLearningRuntime(store,self.owners.runtime,self.owners.source,eligibility_limits={'max_nodes':4096,'max_rows':65536})
        self.budget=ActivityResourceBudget(store,self.owners.budget)
        self.provider=provider
        self.control_metrics={'queue_polls':0,'known_scan':0,'known_bytes':0,'known_elapsed_ms':0,'unknown_polls':0}
    def process_one(self,reasoner=None,backend=None):
        # Branch before all legacy schedulers/StateCollector. Internal new
        # work is separately authenticated; phase recovery is not implicit.
        from digital_life.application.learning.admission import InternalAdmission
        from digital_life.application.runtime.scheduling import Queue
        self.owners.control();InternalAdmission(self).tick()
        _,_,caps=active_profile(self.s)
        limits={k:min(caps[v],n) for k,v,n in (('scan','max_scan',1024),('items','max_items',1024),('bytes','max_bytes',1048576))};limits['elapsed_ms']=min(caps['elapsed_ms'],1000);limits.update(input_tokens=0,output_tokens=0,attempts=0,tool_calls=0)
        poll=PhysicalReadMeter(limits,utc(limits['elapsed_ms']/1000))
        try:
            with dispatch_gate(self.s.root),poll.installed(self.s):
                self.owners.control()
                candidate=self.s.db.execute("SELECT id FROM jobs WHERE instance_id=? AND kind IN ('think','execute') AND due_at<=? AND (state='queued' OR (state='leased' AND lease_expiry<=?)) ORDER BY due_at,id LIMIT 1",(self.s.instance_id,utc(),utc())).fetchone()
                job=Queue(self.s).claim(self.identity.process_id,seconds=3600,preferred_job=candidate[0]) if candidate else None
        finally:
            actual=poll.usage();self.control_metrics['queue_polls']+=1
            if actual is None:self.control_metrics['unknown_polls']+=1
            else:
                for key in ('scan','bytes','elapsed_ms'):self.control_metrics['known_'+key]+=actual[key]
        if not job:return None
        try:
            result=self.think(job['target_ref'],reasoner) if job['kind']=='think' else self.execute(job['target_ref'],backend)
            self.owners.control();Queue(self.s).finish(job);return result
        except BaseException as error:
            with self.s.tx():
                Queue(self.s).finish(job,False)
                if job['kind']=='think':
                    activity=self.s.row('activities',job['target_ref'])
                    if activity['state'] in ('running','waiting_input','waiting_tool','paused'):
                        from digital_life.application.runtime.engine import Engine
                        Engine(self.s,self.identity).transition(activity['id'],'failed','strict-thought-failed:'+type(error).__name__)
            raise
    def _recipient(self,activity):
        signal=self.s.row('perception_signals',self.s.row('activities',activity)['trigger_event_id'])
        return signal['source_actor_id']
    def _current_health(self,activity,request,producer,scope,stage):
        from digital_life.application.behavior.goal_regulation import GoalRegulation
        from digital_life.application.learning.health import CurrentHealthProbe
        regulation=GoalRegulation(self.s);cfg=regulation.config()
        if not cfg['enabled']:return
        self.owners.control();health=CurrentHealthProbe(self.s,activity,request);failure=None
        try:result=regulation.assess(activity,required_tokens=0,required_attempts=0,current_health=health)
        except Forbidden as error:result={'eligible':False,'reasons':['current_probe_unknown']};failure=error
        with self.s.tx():
            event=self.s.event('strict.health.guard',payload=dict(health.audit(),stage=stage,eligible=result['eligible'],configuration=cfg['event_id']),source='strict.health.guard',activity=activity,lane='control')
            for consumer in (ref(self.s,event),ref(self.s,self.s.row('runtime_events',event)['payload_artifact_id'])):_dependency(self.s,consumer,producer,scope,'delete','/actual_use','learn')
        self.owners.control()
        if failure is not None:raise failure
        if not result['eligible'] or self.s.row('activities',activity)['deadline']<=utc():raise Forbidden('actual use current health/goal admission blocked')
    def _settle(self,entry,activity,reservation,actual):
        self.owners.settlements[reservation['id']]={'actual':deepcopy(actual)}
        return self.budget.settle(entry,activity,reservation['id'],actual)
    def _route(self):
        configuration=self.s.db.execute('SELECT * FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()
        compatibility=c.loads(configuration['compatibility'])
        if not compatibility.get('schema_min',4)<=4<=compatibility.get('schema_max',compatibility.get('schema',0)):raise Forbidden('actual configured model route has no declared schema4 compatibility')
        if type(compatibility.get('model_version_id')) is not str:raise Forbidden('strict configuration lacks an explicit immutable model version binding')
        model=self.s.row('model_versions',compatibility['model_version_id'])
        if model['artifact_ref']!=configuration['artifact_ref'] or model['hash']!=configuration['hash']:raise Conflict('explicit model/configuration payload binding differs')
        config=self.s.config()['model'];reasoner=configured_reasoner(config)
        route={'configuration':ref(self.s,configuration['id']),'model':ref(self.s,model['id']),'provider':config['backend']}
        if self.provider is not None:provider=self.provider
        elif route['provider']=='codex_cli' and getattr(reasoner,'budget_mode',None)=='post_usage':
            from digital_life.infrastructure.llm.codex_post_usage import CodexPostUsageProvider
            provider=CodexPostUsageProvider(reasoner,route)
        else:provider=FreshActionProvider(reasoner,route)
        if provider.configured_binding()!=route:raise Conflict('strict provider differs from actual fixed configuration/model')
        return provider,route,reasoner
    def _control(self,activity,scope,source_tokens=()):
        epoch=self.s.rows('policy_epochs')[0];config=self.s.db.execute('SELECT * FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone();row=self.s.row('activities',activity)
        return {'policy':{'object':ref(self.s,epoch['policy_version_id']),'revision':0,'epoch':epoch['epoch']},
                'configuration':{'object':ref(self.s,config['id']),'revision':0,'epoch':0},'source_epochs':deepcopy(list(source_tokens)),
                'runtime_epoch':self.identity.epoch,'input_epoch':row['input_epoch'],'cancelled':bool(row['cancel_requested_at'])}
    def _caps(self,activity):return self.budget.check_activity(activity)['budget']
    def _read_slice(self,activity,fraction=1):
        snapshot=self.budget.check_activity(activity)
        hard=[r for r in snapshot['block_reasons'] if r!='attempts_exhausted']
        if hard:raise Forbidden(','.join(hard))
        # Complete current-source verification is not a 5%-time operation just
        # because a preflight returns few rows. Its temporary time opportunity
        # can use half the still-owned allowance; actual measured consumption
        # is settled, and neither the original cap nor deadline is extended.
        return {k:(max(1,int(snapshot['remaining'][k]*(max(.5,fraction) if k=='elapsed_ms' else fraction))) if k in ('scan','items','bytes','elapsed_ms') else 0) for k in DIMENSIONS}
    def _read_operation(self,entry,activity,context,key,amounts):
        from contextlib import contextmanager
        @contextmanager
        def operation():
            with self.s.tx():run=self.s.insert('memory_retrieval_runs',activity_id=activity,context_id=context,query='bounded strict runtime material '+key,retriever_version='strict-runtime-1')
            reservation=self.budget.reserve(entry,activity,ref(self.s,run),'retrieval',amounts,request_budget=self._caps(activity),reservation_key='strict-read:'+run)
            self.budget.record_entry(entry,activity,reservation['id'],{'contract':'TL-ENGINE-READ-ENTRY-1','operation':ref(self.s,run),'stage':key})
            meter=PhysicalReadMeter(reservation['reserved'],self.s.row('activities',activity)['deadline'])
            try:
                with meter.installed(self.s):yield meter
            finally:self._settle(entry,activity,reservation,meter.usage())
        return operation()
    def _primary(self,entry,principal,activity,context,scope):
        with self._read_operation(entry,activity,context,'primary',self._read_slice(activity,.05)):
            row=self.s.row('activities',activity);origin=ref(self.s,row['trigger_event_id']);token=self.owners.token(origin,scope)
            self.runtime.eligibility.check(entry,principal,token,scope,principal['purpose'],principal['recipient'],'primary_input')
            signal=self.s.row('perception_signals',origin['id']);body=ToolLearningStore(self.s).read_artifact(signal['artifact_id'])
            if type(body) is not dict or set(body)!={'text'} or type(body['text']) is not str:raise ContractError('strict primary input is not the authenticated text receipt')
            return body['text'],token
    def _recall(self,activity,context,query,primary,scope,exact_refs=None):
        from digital_life.application.learning.runtime_owners import LocalRecall
        from digital_life.application.learning.recall import ToolLearningRecall
        entry,principal=self.owners.entry('M04','recall_episode',self._recipient(activity));authority=LocalRecall(self.owners)
        recall=ToolLearningRecall(self.s,authority,self.owners.source)
        caps=self._caps(activity);slice=self._read_slice(activity,.3)
        request={'contract':'TL-LOOP-0.1','schema_revision':1,'request_id':identifier(),'instance_id':self.s.instance_id,'activity_ref':slot(ref(self.s,activity)),
            'context_ref':slot(ref(self.s,context)),'principal':principal,'entry':'execution','query':query,'target_scope':deepcopy(scope),'exact_refs':deepcopy(exact_refs or []),
            'version_mode':'current','as_of':slot(),'group_required':True,'allowed_kinds':['accepted_content','episode'],'control':self._control(activity,scope,[primary]),
            'budget':dict(caps,max_scan=min(caps['max_scan'],slice['scan']),max_items=min(caps['max_items'],slice['items']),max_bytes=min(caps['max_bytes'],slice['bytes'])),'index_fallback':'bounded_primary'}
        run=recall.begin(entry,request)
        reservation=self.budget.reserve(entry,activity,run,'retrieval',slice,request_budget=request['budget'],reservation_key='strict-recall:'+run['id'])
        self.budget.record_entry(entry,activity,reservation['id'],{'contract':'TL-ENGINE-READ-ENTRY-1','operation':run,'stage':'recall'})
        authority.reservation=self.budget._load(activity)[3]['ledger']['reservations'][reservation['id']]
        meter=PhysicalReadMeter(reservation['reserved'],caps['deadline'])
        try:
            with meter.installed(self.s):result=recall.recall(entry,request)
        finally:self._settle(entry,activity,reservation,meter.usage())
        return result
    def _conversation(self,entry,principal,activity,context,primary,scope):
        with self._read_operation(entry,activity,context,'conversation-discovery',self._read_slice(activity,.05)),self.owners.source.verification_boundary(),dispatch_gate(self.s.root):
            self.runtime.eligibility.check(entry,principal,primary,scope,'learn',principal['recipient'],'conversation_query')
            row=self.s.db.execute("SELECT json_extract(attributes_json,'$.chat.thread_id') FROM context_snapshots WHERE instance_id=? AND id=?",(self.s.instance_id,context)).fetchone()
            thread=row[0] if row else None
            if thread is None:return None
            prior=self.s.row('activities',activity)['predecessor_activity_id'];seen={activity};sources=[]
            for _ in range(4):
                if prior is None:break
                if prior in seen:raise Conflict('conversation predecessor cycle')
                seen.add(prior);previous=self.s.row('activities',prior)
                chat=self.s.db.execute("SELECT json_extract(attributes_json,'$.chat.thread_id') FROM context_snapshots WHERE instance_id=? AND activity_id=? ORDER BY rowid LIMIT 1",(self.s.instance_id,prior)).fetchone()
                if chat is None or chat[0]!=thread:raise Forbidden('conversation predecessor crosses its actual thread binding')
                sources.append(previous['trigger_event_id'])
                sources.extend(r[0] for r in self.s.db.execute('SELECT accepted_result_id FROM thought_requests WHERE instance_id=? AND activity_id=? AND accepted_result_id IS NOT NULL ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,prior)))
                prior=previous['predecessor_activity_id']
            if not sources:return {'thread_id':thread,'messages':[],'authority':'bounded quoted historical reports; no provider session','coverage':'no predecessor selected'}
            marks=','.join('?' for _ in sources)
            rows=self.s.db.execute('SELECT DISTINCT r.id FROM memory_revisions r JOIN memory_items m ON m.instance_id=r.instance_id AND m.id=r.memory_id JOIN memory_source_links l ON l.instance_id=r.instance_id AND l.memory_revision_id=r.id JOIN evidence_items e ON e.instance_id=l.instance_id AND e.id=l.evidence_id WHERE r.instance_id=? AND m.current_revision_id=r.id AND m.state=\'active\' AND e.origin_object_id IN ('+marks+') ORDER BY r.recorded_at,r.id LIMIT 8',(self.s.instance_id,*sources)).fetchall()
            candidates=[ref(self.s,row[0],'memory_revisions') for row in rows]
        result=self._recall(activity,context,'bounded exact predecessor dialogue',primary,scope,exact_refs=candidates) if candidates else None
        messages=[]
        if result:
            for item in result['items']:
                role='assistant' if item['origin_kind']=='model_output' else 'user' if item['origin_kind']=='user_statement' else 'reported'
                messages.append({'role':role,'text':item['body'],'memory_revision':deepcopy(item['memory_revision']),'recall_item':ref(self.s,item['id'],'tl_recall_item')})
        return {'thread_id':thread,'messages':messages,'authority':'bounded quoted historical reports; no provider session','retrieval':result,'coverage':'at most four actual predecessor turns/eight authorized current memory revisions; other history not assessed'}
    FEATURE_TABLES={
        'identity':('identity_instances','identity_anchors'),
        'personality':('personality_dimensions','personality_profiles','personality_trait_values','personality_states','personality_change_records'),
        'values':('value_dimensions','value_profiles','value_weights','value_activations','value_change_records'),
        'cognition_candidates':('cognition_beliefs','cognition_concepts','cognition_hypotheses','cognition_predictions','cognition_plans','cognition_plan_steps','cognition_assessments'),
        'goals_and_motivation':('goal_items','goal_relations','goal_evaluations','goal_activation_records','motivation_states'),
        'habits':('habit_items','habit_cues','habit_associations','habit_opportunities','habit_activations','habit_learning_records'),
        'relationships':('social_actors','social_relationships','social_relationship_dimensions','social_relationship_values','social_trust_assessments','social_expectations','social_relationship_changes'),
        'internal_state':('state_definitions','state_observations'),
        'health_and_maintenance':('health_requirements','health_observations','health_assessments','health_incidents','maintenance_plans'),
        'commitments':('commitment_items',),
        'learning_feedback':('learning_feedback','learning_attributions'),
    }
    @staticmethod
    def _field(path,value,scope,dependencies=(),usage='historical_observation',dependency_scopes=None):
        return {'path':path,'digest':{'algorithm':'sha256','hex':c.fingerprint(value)},'kind':'source_material' if dependencies else 'fixed_instruction',
                'usage':usage if dependencies else 'fixed_instruction','dependencies':deepcopy(list(dependencies)),'dependency_scopes':deepcopy(list(dependency_scopes)) if dependency_scopes is not None else [deepcopy(scope) for _ in dependencies],'scope':deepcopy(scope)}
    @staticmethod
    def _read_dep(token,purpose='learn'):
        return {'target':deepcopy(token['object']),'relation':'read','expected':deepcopy(token),'consumer_purpose':purpose}
    def _feature_selection(self,table,activity,task):
        columns=self.s.columns[table];where='';params=[self.s.instance_id]
        current={'personality_dimensions','personality_profiles','personality_trait_values','value_dimensions','value_profiles','value_weights','identity_instances','identity_anchors','state_definitions','health_requirements','social_relationship_dimensions'}
        if table in ('personality_profiles','value_profiles','identity_anchors'):
            where=' AND version=(SELECT max(version) FROM '+table+' WHERE instance_id=?)';params.append(self.s.instance_id)
        elif table=='identity_instances':where=' AND id=?';params.append(self.s.instance_id)
        elif table=='personality_trait_values':where=' AND profile_id=(SELECT id FROM personality_profiles WHERE instance_id=? ORDER BY version DESC LIMIT 1)';params.append(self.s.instance_id)
        elif table=='value_weights':where=' AND profile_id=(SELECT id FROM value_profiles WHERE instance_id=? ORDER BY version DESC LIMIT 1)';params.append(self.s.instance_id)
        elif table=='goal_items':
            where=' AND source_ref=(SELECT trigger_event_id FROM activities WHERE instance_id=? AND id=?)';params.extend([self.s.instance_id,activity]);current.add(table)
        elif table in ('commitment_items','habit_items'):
            where=" AND state NOT IN ('completed','cancelled','expired','failed')" if table!='habit_items' else '';current.add(table)
        elif table=='social_actors':
            where=" AND (actor_type IN ('self','controller'))";current.add(table)
        elif table in ('cognition_beliefs','cognition_concepts'):
            terms=[key for key in ('predicate','literal','canonical_label','name','definition') if key in columns]
            if not terms:where=' AND 0'
            else:
                where=' AND ('+' OR '.join('instr(lower(coalesce('+key+",'')),lower(?))>0" for key in terms)+')';params.extend([task]*len(terms))
        elif table=='state_observations':
            where=' AND rowid IN (SELECT max(rowid) FROM state_observations WHERE instance_id=? GROUP BY definition_id)';params.append(self.s.instance_id);current.add(table)
        elif 'activity_id' in columns:where=' AND activity_id=?';params.append(activity)
        elif 'episode_id' in columns:
            where=' AND episode_id IN (SELECT id FROM cognition_episodes WHERE instance_id=? AND activity_id=?)';params.extend([self.s.instance_id,activity])
        # Histories without a direct activity key are bounded by a declared
        # chronology slice; they never replace the complete current vectors.
        mode='current_complete' if table in current else 'bounded_context_history'
        limit='' if mode=='current_complete' else ' LIMIT 8'
        ids=self.s.db.execute('SELECT id FROM '+table+' WHERE instance_id=?'+where+' ORDER BY rowid DESC'+limit,tuple(params)).fetchall()
        return ids,{'table':table,'mode':mode,'predicate':where or 'this instance','parameters':[str(x) for x in params[1:]],'limit':None if mode=='current_complete' else 8,'order':'recorded row order descending; not world event time','scope':'explicit current profile/vector or declared context/history slice'}
    def _features(self,entry,principal,activity,context,scope,task,primary):
        from digital_life.domain.tool_learning_sources import SNAPSHOT_KINDS
        features={};fields=[]
        with self._read_operation(entry,activity,context,'features',self._read_slice(activity,.8)),self.owners.source.verification_boundary():
            for module,tables in self.FEATURE_TABLES.items():
                values=[];selections=[]
                for table in tables:
                    if table not in self.s.columns:raise Forbidden('required feature source table absent: '+table)
                    ids,selection=self._feature_selection(table,activity,task);selections.append(selection)
                    for record in ids:
                        origin=ref(self.s,record[0]);selector=sorted(self.s.columns[table]);path='/input/features/'+module+'/records/'+str(len(values))
                        if table in SNAPSHOT_KINDS:
                            token=self.owners.snapshots.capture(entry,principal,origin,selector,scope)
                            snapshot=self.owners.snapshots.fixed(entry,principal,token,scope);raw=snapshot['value'];usage='historical_observation' if table=='state_observations' else 'live_state'
                        else:
                            token=self.owners.token(origin,scope);self.owners.source_access(entry,principal,origin,scope);raw=self.s.row(table,origin['id']);usage='live_state' if table in ('personality_profiles','value_profiles','identity_anchors') else 'historical_observation'
                        self.runtime.eligibility.check(entry,principal,token,scope,principal['purpose'],principal['recipient'],'feature_read')
                        value={'source':origin,'observed_version':token['revision'],'report':deepcopy(raw),'meaning':'stored system state report; cognition entries remain candidates'}
                        if table=='state_observations':value['meaning']='historical state observation at report.observed_at; TTL unchanged; not current substrate health'
                        values.append(value);fields.append(self._field(path,value,scope,[self._read_dep(token)],usage))
                coverage={'state':'partial','domain':slot(module),'scanned':len(values),'limit':len(values),'truncated':False,'missing':[{'status':'not_collected','value':None,'reason_code':'not_requested','reason':'history outside the declared context selection is not assessed','basis_refs':[]}]}
                # Coverage.missing is an internal explanatory string list here,
                # not the frozen typed Coverage field; no hidden total emitted.
                missing=[] if values else [{'status':'not_collected','value':None,'reason_code':'not_measured','reason':'no report selected under the declared authorized context; not evidence that the state does not exist','basis_refs':[]}]
                features[module]={'records':values,'selection':selections,'coverage':coverage,'missing':missing}
                if not values:fields.append(self._field('/input/features/'+module+'/records',values,scope,[self._read_dep(primary)]))
                for name in ('selection','coverage','missing'):fields.append(self._field('/input/features/'+module+'/'+name,features[module][name],scope,[self._read_dep(primary)]))
        return features,fields
    def _deployment(self):
        self.owners.control();path=self.s.root/'control.sqlite';db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        try:
            row=db.execute('SELECT d.* FROM process_runs p JOIN deployments d ON d.id=p.deployment_id WHERE p.id=? AND p.instance_ref=?',(self.identity.process_id,self.s.instance_id)).fetchone()
            if row is None or row['state']!='active':raise Forbidden('actual current registered deployment missing')
            return dict(row)
        finally:db.close()
    def _qualified_fields(self,entry,principal,request,fields,stage):
        with self.owners.source.verification_boundary():
            return self._qualified_fields_in_boundary(entry,principal,request,fields,stage)
    def _qualified_fields_in_boundary(self,entry,principal,request,fields,stage):
        for field in fields:
            if field['usage'] in ('live_state','current_control'):self.owners.runtime.verify_live(entry,request,principal,field,stage)
        seen=set()
        for field in fields:
            for index,dependency in enumerate(field['dependencies']):
                if dependency['relation']!='delete':
                    scope=field['dependency_scopes'][index]
                    key=c.fingerprint({'principal':principal,'expected':dependency['expected'],'scope':scope,'relation':dependency['relation'],'stage':stage})
                    if key not in seen:
                        self.runtime.eligibility.check(entry,principal,dependency['expected'],scope,principal['purpose'],principal['recipient'],stage)
                        seen.add(key)
        self.owners.control()
        if request['kind']=='thought_requests':self.owners.runtime.verify_health(entry,request,principal,stage)
        self.owners.control()
    def prepare(self,activity):
        self.owners.control();release=self._deployment();entry,principal=self.owners.entry('M14','learn',self._recipient(activity))
        if self.s.db.in_transaction:raise Conflict('strict preparation needs the original account outside a main transaction')
        scope=source_scope(self.s);row=self.s.row('activities',activity)
        if row['publication_state']!='ready' or row['cancel_requested_at'] or row['state'] in ('completed','failed','cancelled'):raise Forbidden('strict activity is not currently prepareable')
        self._caps(activity)
        existing=self.s.db.execute("SELECT * FROM thought_requests WHERE instance_id=? AND activity_id=? AND instruction_version='strict-complete-packet-1' AND expected_input_epoch=? ORDER BY rowid DESC LIMIT 1",(self.s.instance_id,activity,row['input_epoch'])).fetchone()
        if existing:
            if existing['process_run_id']!=self.identity.process_id or existing['runtime_epoch']!=self.identity.epoch:raise Conflict('old process preparation requires explicit recovery, no hidden session resume')
            request=ref(self.s,existing['id']);token={'object':request,'revision':0,'epoch':0}
            self.runtime.eligibility.check(entry,principal,token,scope,'learn',principal['recipient'],'prepared_packet_read')
            with self._read_operation(entry,activity,self.s.row('activity_steps',existing['step_id'])['context_id'] if 'context_id' in self.s.row('activity_steps',existing['step_id']) else self.s.db.execute('SELECT id FROM context_snapshots WHERE instance_id=? AND activity_id=? ORDER BY rowid LIMIT 1',(self.s.instance_id,activity)).fetchone()[0],'prepared-read',self._read_slice(activity,.1)):
                packet=self.runtime.storage.read_artifact(existing['request_artifact_id']);proof=self.runtime._proof(request)
            if proof is None:raise Conflict('partial prepared assembly requires reconciliation, not a fresh body under its identity')
            self.owners.read_opportunities['assembly:'+request['id']]={'manifest':deepcopy(proof['manifest']),'input':deepcopy(packet['input']),'activity_ref':deepcopy(packet['activity_ref']),'deadline':packet['limits']['deadline']}
            return dict(existing),packet,proof['manifest'],entry,principal
        with dispatch_gate(self.s.root),self.s.tx():
            actual=self.s.row('activities',activity)
            if actual['release_id']=='UNBOUND:awaiting-real-runtime':self.s.db.execute('UPDATE activities SET release_id=? WHERE instance_id=? AND id=? AND release_id=?',(release['release'],self.s.instance_id,activity,'UNBOUND:awaiting-real-runtime'))
            elif actual['release_id']!=release['release']:raise Conflict('activity release lineage requires explicit cross-release recovery')
            if actual['state']=='pending':
                from digital_life.application.runtime.engine import Engine
                Engine(self.s,self.identity).transition(activity,'running','strict-prepare')
            context=self.s.db.execute('SELECT id FROM context_snapshots WHERE instance_id=? AND activity_id=? ORDER BY rowid LIMIT 1',(self.s.instance_id,activity)).fetchone()
            if context is None:raise Forbidden('actual original activity context missing')
            context=context[0]
        task,primary=self._primary(entry,principal,activity,context,scope)
        recalled=self._recall(activity,context,task,primary,scope)
        conversation=self._conversation(entry,principal,activity,context,primary,scope)
        features,fields=self._features(entry,principal,activity,context,scope,task,primary)
        fields.append(self._field('/input/task',task,scope,[self._read_dep(primary)]))
        calculated,live_bindings,computed_fields=self._contexts(entry,principal,activity,context,task,recalled,fields,scope,conversation)
        # Local regulation may create/update state as part of calculation. The
        # final packet samples the resulting current vectors, not stale inputs
        # from before that legitimate preparation step.
        features,fields=self._features(entry,principal,activity,context,scope,task,primary)
        fields.extend(computed_fields)
        assembly_amounts=self._read_slice(activity,.5)
        # Full assembly includes registration and both retention checks. Allow
        # that one read operation to borrow time from the same remaining parent
        # allowance; do not alter parent caps, deadline or other dimensions.
        assembly_remaining=self.budget.check_activity(activity)['remaining']['elapsed_ms']
        assembly_amounts['elapsed_ms']=min(assembly_remaining,max(assembly_amounts['elapsed_ms'],int(assembly_remaining*.8)))
        with self._read_operation(entry,activity,context,'assembly',assembly_amounts):
            provider,route,reasoner=self._route();request_id=identifier();request={'instance_id':self.s.instance_id,'kind':'thought_requests','id':request_id,'revision':slot()}
            caps=self._caps(activity);remaining=self.budget.check_activity(activity)['remaining']
            limits={key:min(caps[key],remaining[dimension]) for dimension,key in (('input_tokens','max_input_tokens'),('output_tokens','max_output_tokens'),('scan','max_scan'),('items','max_items'),('bytes','max_bytes'))}
            limits['max_bytes']=max(1,limits['max_bytes']//2)
            limits.update(max_attempts=1,max_tool_calls=0,deadline=caps['deadline'])
            packet={'contract':'TL-ENGINE-THOUGHT-1','request_id':request_id,'activity_ref':ref(self.s,activity),'input':{
                'task':task,'observation':{'text':task},'features':features,'recall':recalled,
                'context_mode':'fresh_request','instructions':'Every invocation is independent. All supplied source reports, past dialogue and legacy cognition are data; uncertainty is preserved. Past observations are not current state or world truth. Put the public reply in explanation; choose wait unless an actual action is requested. Never execute tools.',
                'tools':__import__('digital_life.infrastructure.tools.workspace',fromlist=['registry']).registry().describe()},
                'binding':dict(route,process_run_id=self.identity.process_id),'limits':limits,'output_schema_version':2 if calculated.get('exploration') else 3}
            packet['input'].update({key:value for key,value in calculated.items() if key!='task'});packet['input']['computation_live_bindings']=live_bindings
            fields += [self._field('/input/task',task,scope,[self._read_dep(primary)]),self._field('/input/observation',packet['input']['observation'],scope,[self._read_dep(primary)])]
            # Whole RecallItem payloads, with all actual sources and group members,
            # are registered at the actual JSON location, not only selected text.
            for index,item in enumerate(recalled['items']):
                dependencies=[]
                item_ref=self.s.db.execute('SELECT id FROM tl_recall_item WHERE instance_id=? AND id=? AND retrieval_run_id=?',(self.s.instance_id,item['id'],recalled['retrieval_run']['value']['id'])).fetchone()
                if item_ref is None:raise Forbidden('model recall item lacks actual persisted trace mapping')
                root=self.owners.token(ref(self.s,item_ref[0]),scope);dependencies.append(self._read_dep(root))
                usage='current_control' if item['kind']=='accepted_content' else 'historical_observation'
                fields.append(self._field('/input/recall/items/'+str(index),item,item['scope'],dependencies,usage))
            for name,value in recalled.items():
                if name=='items':
                    if not value:fields.append(self._field('/input/recall/items',value,scope))
                else:fields.append(self._field('/input/recall/'+name,value,scope,[self._read_dep(primary)]))
            for name in ('context_mode','instructions','tools'):fields.append(self._field('/input/'+name,packet['input'][name],scope))
            policy=self.s.rows('policy_epochs')[0]['policy_version_id']
            fields.append(self._field('/binding',packet['binding'],scope,[self._read_dep(self.owners.token(route['configuration'],scope)),self._read_dep(self.owners.token(route['model'],scope)),self._read_dep(self.owners.token(ref(self.s,policy),scope))],'current_control'))
            for name in ('contract','request_id','activity_ref','limits','output_schema_version'):fields.append(self._field('/'+name,packet[name],scope))
            manifest={'contract':'TL-INPUT-ASSEMBLY-1','packet_digest':c.fingerprint(packet),'fields':fields}
            from digital_life.application.learning.runtime import validate_manifest
            validate_manifest(packet,manifest)
            self.owners.read_opportunities['assembly:'+request_id]={'manifest':deepcopy(manifest),'input':deepcopy(packet['input']),'activity_ref':deepcopy(packet['activity_ref']),'deadline':packet['limits']['deadline']}
            with dispatch_gate(self.s.root):
                self._qualified_fields(entry,principal,request,fields,'before_complete_packet_retention')
                with self.s.tx():
                    current=self.s.row('activities',activity)
                    if current['cancel_requested_at'] or current['state']!='running':raise Forbidden('actual activity changed before fixed packet commit')
                    artifact=self.s.artifact(packet)
                    step=self.s.insert('activity_steps',activity_id=activity,step_no=self.s.db.execute('SELECT count(*) FROM activity_steps WHERE instance_id=? AND activity_id=?',(self.s.instance_id,activity)).fetchone()[0],step_type='strict-thought',state='pending',attempt=0,idempotency_key='strict-thought:'+request_id)
                    self.s.insert('thought_requests',id=request_id,activity_id=activity,step_id=step,request_key='strict-thought:'+activity+':'+str(current['input_epoch']),purpose='plan',task=task,instruction_version='strict-complete-packet-1',output_schema_version=packet['output_schema_version'],request_artifact_id=artifact,request_hash=c.fingerprint(packet),input_manifest_hash=c.fingerprint(manifest),model_config_id=route['configuration']['id'],model_version_id=route['model']['id'],prepared_activity_revision=current['revision'],expected_input_epoch=current['input_epoch'],expected_policy_epoch=self.s.rows('policy_epochs')[0]['epoch'],runtime_epoch=self.identity.epoch,process_run_id=self.identity.process_id,deadline=caps['deadline'],token_budget=limits['max_input_tokens']+limits['max_output_tokens'],attempt_limit=1,retry_policy={'max_attempts':1},generation_config={'fresh':True,'deployment_id':release['id'],'release':release['release'],'build_hash':release['build_hash']},state='prepared')
                    # Register the real immutable request/payload provenance in its
                    # creation transaction, before another F1 can see the object.
                    request_paths={}
                    for field in fields:
                        for index,dep in enumerate(field['dependencies']):
                            scope_for_source=field['dependency_scopes'][index]
                            key=(dep['target']['id'],dep['relation'],field['path'],dep['expected']['epoch'])
                            meaning=c.fingerprint({'dependency':dep,'scope':scope_for_source})
                            if key in request_paths:
                                if request_paths[key]!=meaning:raise Conflict('request source path has different meaning')
                            else:
                                # Use the same actual JSON path that the public
                                # registration API validates. Only the path of
                                # the already-owned lineage row changes; inputs
                                # are still registered solely by that public API.
                                _dependency(self.s,request,dep['expected'],scope_for_source,dep['relation'],field['path'],'learn')
                                request_paths[key]=meaning
                            _dependency(self.s,ref(self.s,artifact),dep['expected'],scope_for_source,dep['relation'],field['path']+'/'+str(index),'learn')
                self.runtime.assemble(entry,request,principal,packet,manifest)
        return self.s.row('thought_requests',request_id),packet,manifest,entry,principal
    def _record_failure(self,request,attempt,error,provider,usage,measurements):
        # Safe factual call status only; no late source body, secret raw error,
        # input hash or provider reply is persisted on a failed retention gate.
        with self.s.tx():
            if attempt:self.s.db.execute("UPDATE thought_attempts SET state='failed',finished_at=?,error_code=?,usage_json=? WHERE instance_id=? AND id=?",(utc(),type(error).__name__,dumps({'known':usage is not None,'actual':usage,'measurements':measurements,'observed_route':deepcopy(getattr(provider,'last_observed_route',None)),'transport_entered':getattr(provider,'last_transport_entered',None)}),self.s.instance_id,attempt))
            self.s.db.execute("UPDATE thought_requests SET state='failed' WHERE instance_id=? AND id=? AND state<>'succeeded'",(self.s.instance_id,request['id']))
        if getattr(provider,'accounting_hold',False):
            from digital_life.application.lifecycle.control_plane import Control
            marker=self.s.root/'MODEL_USAGE_REVIEW_REQUIRED'
            if marker.is_symlink():raise Forbidden('invalid model usage review marker')
            marker.write_text(dumps({'request_id':request['id'],'attempt_id':attempt,
                'reason':'Codex actual usage unknown or exceeds original allowance; explicit review required'}))
            control=Control(self.s.root,self.s.instance_id)
            try:control.stop('model-usage-review:'+request['id'])
            finally:control.close()
    def think(self,activity,reasoner=None):
        from contextlib import contextmanager
        import time,math
        row,packet,manifest,entry,principal=self.prepare(activity);request=ref(self.s,row['id'])
        if row['state']=='succeeded':return {'accepted':True,'duplicate':True,'request_id':row['id']}
        if row['state']!='prepared':raise Conflict('strict thought state requires explicit reconciliation')
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE instance_id=? AND activity_id=? ORDER BY rowid LIMIT 1',(self.s.instance_id,activity)).fetchone()[0]
        provider,route,configured=self._route()
        if reasoner is not None and reasoner.name!=configured.name:raise Conflict('caller reasoner cannot replace the fixed actual configuration')
        with self.s.tx():
            attempt=self.s.insert('thought_attempts',request_id=row['id'],attempt_no=1,state='queued',queued_at=utc(),dispatch_token=identifier(),provider=route['provider'],model=self.s.row('model_versions',route['model']['id'])['version'],runtime_epoch=self.identity.epoch,process_run_id=self.identity.process_id)
        provider.last_transport_entered=False;provider.last_observed_route=None;provider.last_usage=None;provider.last_measurements=None
        try:
            with self._read_operation(entry,activity,context,'provider-preflight',self._read_slice(activity,.5)):
                self._qualified_fields(entry,principal,request,manifest['fields'],'preflight')
                input_tokens=provider.preflight(deepcopy(packet))
        except BaseException as error:
            # A planned attempt was refused before inference entry. Its zero
            # model use is distinct from the actually settled preflight reads.
            actual={key:0 for key in DIMENSIONS}
            measured={'contract':'TL-INFERENCE-MEASUREMENTS-1','dimensions':{key:{'status':'known','value':0,'basis':'inference opportunity was not entered; preflight reads accounted separately'} for key in DIMENSIONS},'observed_route':None}
            self._record_failure(row,attempt,error,provider,actual,measured)
            raise
        entered=False;transport=None;usage=None;measurements=None;reservation=None
        try:
            # Gate reads are separately prepaid before spending the final model
            # attempt. Their own slice remains valid while globally reserved.
            gate_amounts=self._read_slice(activity,.65)
            with self._read_operation(entry,activity,context,'actual-entry-and-retention',gate_amounts) as gate_meter:
                remaining=self.budget.check_activity(activity)['remaining']
                model_amounts={k:0 for k in DIMENSIONS};model_amounts.update(attempts=1,input_tokens=input_tokens,output_tokens=min(packet['limits']['max_output_tokens'],configured.max_output_tokens if hasattr(configured,'max_output_tokens') else packet['limits']['max_output_tokens']),bytes=min(packet['limits']['max_bytes'],remaining['bytes']),elapsed_ms=remaining['elapsed_ms'])
                reservation=self.budget.reserve(entry,activity,ref(self.s,attempt),'thought_attempt',model_amounts,request_budget=self._caps(activity),reservation_key='strict-thought:'+attempt)
                def invoke():
                    nonlocal entered,transport,usage,measurements
                    self.budget.record_entry(entry,activity,reservation['id'],{'contract':'TL-ENGINE-THOUGHT-ENTRY-1','operation':ref(self.s,attempt),'request':request,'execution_timeout_ms':reservation['reserved']['elapsed_ms']})
                    with self.s.tx():
                        self.s.db.execute("UPDATE thought_attempts SET state='sent',sent_at=? WHERE id=?",(utc(),attempt))
                        self.s.db.execute("UPDATE thought_requests SET state='running' WHERE id=?",(row['id'],))
                    entered=True;started=time.monotonic()
                    try:
                        with gate_meter.excluding_child():transport=provider.generate_fresh(deepcopy(packet),execution_timeout_ms=reservation['reserved']['elapsed_ms'],execution_max_bytes=reservation['reserved']['bytes'],before_transport=lambda:self._qualified_fields(entry,principal,request,manifest['fields'],'immediately_before_transport'))
                        return deepcopy(transport['body'])
                    finally:
                        usage=deepcopy(transport['usage']) if isinstance(transport,dict) else deepcopy(getattr(provider,'last_usage',None))
                        measurements=deepcopy(getattr(provider,'last_measurements',None))
                        elapsed=math.ceil((time.monotonic()-started)*1000)
                        if not getattr(provider,'last_transport_entered',True):
                            # The actual local reasoner attempt entered, but its
                            # final source/capability guard proved no transport
                            # process was started. No remote tokens are guessed.
                            usage={key:0 for key in DIMENSIONS};usage.update(attempts=1,bytes=getattr(provider,'last_local_request_bytes',0),elapsed_ms=elapsed)
                            measurements={'contract':'TL-INFERENCE-MEASUREMENTS-1','dimensions':{key:{'status':'known','value':value,'basis':'local entered attempt; transport proved not started'} for key,value in usage.items()},'observed_route':None}
                        if usage is not None:usage['elapsed_ms']=elapsed
                        if measurements is not None:measurements['dimensions']['elapsed_ms']={'status':'known','value':elapsed,'basis':'actual runtime inference callback monotonic duration'}
                with dispatch_gate(self.s.root):
                    output=self.runtime.invoke(entry,request,principal,packet,manifest,invoke)
                    self._settle(entry,activity,reservation,usage)
                    bad=[r for r in self.budget.check_activity(activity)['block_reasons'] if r not in ('attempts_exhausted',)]
                    if bad:raise Forbidden('actual original resource use prevents publication: '+','.join(bad))
                    self.owners.runtime.verify_retention(entry,request,principal,manifest,'response_retention')
                    self._qualified_fields(entry,principal,request,manifest['fields'],'response_retention')
                    current=self.s.row('activities',activity)
                    if current['cancel_requested_at'] or current['input_epoch']!=row['expected_input_epoch'] or current['state']!='running':raise Conflict('actual activity changed before response retention')
                    if packet['input'].get('exploration'):
                        from digital_life.application.autonomy.exploration import Exploration
                        Exploration(self.s).validate_output(activity,packet['input'],output)
                    with self.s.tx():
                        artifact=self.s.artifact(output)
                        result=self.s.insert('thought_results',request_id=row['id'],attempt_id=attempt,response_artifact_id=artifact,response_hash=c.fingerprint(output),received_at=utc(),parsed_artifact_id=artifact,validation_errors=[],validation_state='valid',acceptance='accepted',accepted_at=utc())
                        invocation=getattr(provider,'last_invocation',None)
                        if type(invocation) is not dict:raise Conflict('accepted strict result lacks actual provider invocation proof')
                        invoked=self.s.event('strict.provider.invocation',payload=deepcopy(invocation),source='strict.provider.invocation',key=attempt,activity=activity)
                        result_token={'object':ref(self.s,result),'revision':0,'epoch':0}
                        for consumer in (ref(self.s,invoked),ref(self.s,self.s.row('runtime_events',invoked)['payload_artifact_id'])):
                            for relation in ('read','delete'):_dependency(self.s,consumer,result_token,manifest['fields'][0]['scope'],relation,'/actual_provider_input','learn')
                        self.s.db.execute("UPDATE thought_attempts SET state='received',finished_at=?,usage_json=? WHERE id=?",(utc(),dumps({'known':True,'actual':usage,'measurements':measurements,'observed_route':provider.last_observed_route,'transport_entered':provider.last_transport_entered}),attempt))
                        self.s.db.execute("UPDATE thought_requests SET state='succeeded',accepted_result_id=? WHERE id=?",(result,row['id']))
                        # The output and its actual body both retain the whole
                        # input lineage; no selected-memory-only shortcut.
                        _retain_output_lineage(self.s,row['id'],result,artifact,manifest)
                        accepted=self._finish(activity,context,row['id'],result,output,packet,manifest)
                    return accepted
        except BaseException as error:
            if reservation is not None:
                actual=usage if entered else {k:0 for k in DIMENSIONS}
                # Known settlement is immutable; don't overwrite it while
                # reporting a later retention/stop failure.
                state=self.budget._load(activity)[3]['ledger']['reservations'][reservation['id']]['state']
                if state not in ('settled','released'):self._settle(entry,activity,reservation,actual)
            self._record_failure(row,attempt,error,provider,usage,measurements)
            raise
    def _finish(self,activity,context,request_id,result,output,packet,manifest):
        from digital_life.application.services import Memory,Decisions
        from digital_life.application.accounts.authorization import Policy
        from digital_life.application.runtime.engine import Engine
        from digital_life.application.behavior.personality_growth import PersonalityGrowth
        from digital_life.application.behavior.habit_learning import HabitLearning
        # New business objects are tracked as actual derived consumers. The
        # strict branch does not call legacy cognition's world-accept side path.
        changed_before=self._mutable_fingerprints()
        created=[];original=self.s.insert
        def recording(table,**fields):
            key=original(table,**fields)
            if table not in ('object_registry','object_revision_registry','tl_dependency','tl_input_dependency'):created.append((table,key))
            return key
        self.s.insert=recording
        try:
            if output.get('cognition'):
                self.s.event('strict.cognition.candidate',payload={'request':request_id,'result':result,'cognition':deepcopy(output['cognition']),'acceptance':'candidate','world_truth_established':False},activity=activity)
            if output.get('explanation'):
                evidence=self.s.evidence(object_id=result,method='strict-model-reported-response')
                Memory(self.s).encode(output['explanation'],evidence,labels=[('content','conversational-response')],encoding_method='model-response-v1',source_role='inferred')
            goal=self.s.db.execute('SELECT id FROM goal_items WHERE instance_id=? AND source_ref=(SELECT trigger_event_id FROM activities WHERE instance_id=? AND id=?) ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,self.s.instance_id,activity)).fetchone()
            if goal is None:raise Forbidden('actual activity goal missing')
            action=output['action']
            if packet['input'].get('behavior_policy') and not packet['input']['behavior_policy'].get('bypass'):
                from digital_life.application.behavior.behavior_policy import BehaviorPolicy
                decision=BehaviorPolicy(self.s).select(activity,goal[0],context,packet['input'],action,request_id);action=decision['action']
            else:decision=Decisions(self.s).finalize(activity,goal[0],context,[action,{'tool':'wait','arguments':{'reason':'bounded alternative'}}])
            self.s.event('thought.accepted',payload={'request':request_id,'result':result,'decision':decision['decision'],'strict':True},activity=activity)
            PersonalityGrowth(self.s).record(activity,request_id,decision['decision']);HabitLearning(self.s).record(activity,request_id,decision['decision'])
            from digital_life.application.autonomy.exploration import Exploration
            exploration=Exploration(self.s)
            exploration_answer=exploration.accept(Engine(self.s,self.identity),activity,packet['input'],output,request_id) if exploration.binding(activity) else None
            if exploration_answer is not None:
                answer=dict(exploration_answer,request_id=request_id)
            elif action['tool'] in ('wait','ask'):
                Engine(self.s,self.identity).transition(activity,'waiting_input',action['tool']);answer={'accepted':True,'waiting':action['arguments']['reason'],'request_id':request_id}
            else:
                intent=Policy(self.s).propose(activity,decision['selected'],action);approval=Policy(self.s).request(intent)
                Engine(self.s,self.identity).transition(activity,'waiting_input','approval-required');Policy(self.s).maybe_approve_open_mode(approval)
                answer={'accepted':True,'action_id':intent,'approval_id':approval,'request_id':request_id}
        finally:self.s.insert=original
        token={'object':ref(self.s,result),'revision':0,'epoch':0};scope=manifest['fields'][0]['scope']
        created.extend(self._changed_mutable(changed_before))
        for table,key in created:
            if table not in self.s.columns or 'id' not in self.s.columns[table]:continue
            for relation in ('read','delete'):_dependency(self.s,ref(self.s,key),token,scope,relation,'/model_derivation','learn')
        return answer
    def _mutable_fingerprints(self):
        # Current life vectors can be updated by the existing observers rather
        # than inserted. Preserve those actual targets as derived consumers.
        tables=('personality_trait_values','habit_opportunities','habit_associations','goal_items','commitment_items','motivation_states','social_relationship_values')
        return {(table,row['id']):c.fingerprint(dict(row)) for table in tables for row in self.s.db.execute('SELECT * FROM '+table+' WHERE instance_id=?',(self.s.instance_id,))}
    def _changed_mutable(self,before):
        changed=[]
        for table,key in before:
            row=self.s.row(table,key)
            if c.fingerprint(row)!=before[(table,key)]:changed.append((table,key))
        return changed
    def execute(self,intent,backend=None):
        from digital_life.application.learning.execution import StrictActionExecutor
        from digital_life.application.learning.runtime_learning import StrictLearningCoordinator
        executor=StrictActionExecutor(self.s,self.identity,self);outcome=executor.dispatch(intent,backend)
        if outcome.get('duplicate'):return outcome
        activity=executor.activity_for(self.s.row('action_intents',intent));learning=StrictLearningCoordinator(self)
        try:
            work=learning.admit(activity,outcome['result'],{'kind':'json_pointer','pointer':'/execution'},interpret=False)
            learning.assess(work['id'])
            proposal=self.s.db.execute("SELECT id FROM tl_product WHERE instance_id=? AND work_id=? AND product_type='UpdateProposal'",(self.s.instance_id,work['id'])).fetchone()
            if proposal:learning.decide(proposal[0])
            outcome['learning_work']=work['id']
        except (Forbidden,Conflict,ContractError):
            # The actual tool result is already a committed fact. Missing
            # learning permission/resources never rewrites it as unexecuted.
            outcome['learning_state']='blocked'
        entry,principal=self.owners.entry('M14','learn',self._recipient(activity));scope=source_scope(self.s)
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE instance_id=? AND activity_id=? ORDER BY rowid LIMIT 1',(self.s.instance_id,activity)).fetchone()[0]
        token=self.owners.token(ref(self.s,outcome['result']),scope)
        with self._read_operation(entry,activity,context,'actual-tool-feedback',self._read_slice(activity,.5)) as meter,dispatch_gate(self.s.root):
            self.runtime.eligibility.check(entry,principal,token,scope,'learn',principal['recipient'],'tool_feedback')
            with self.s.tx():
                from digital_life.application.learning.contexts import DomainReadCollector
                from digital_life.application.behavior.personality_growth import PersonalityGrowth
                from digital_life.application.behavior.habit_learning import HabitLearning
                from digital_life.application.services import Memory,Goals,Commitments,Health
                from digital_life.application.runtime.engine import Engine
                from digital_life.application.autonomy.task_loop import TaskLoop
                from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
                current=self.s.row('action_intents',intent);candidate=self.s.row('decision_candidates',current['candidate_id']);decision=self.s.row('decision_records',candidate['decision_id'])
                root=self.s.row('action_results',outcome['result']);attempt=self.s.row('action_attempts',root['attempt_id'])
                known={intent,candidate['id'],decision['id'],root['id'],attempt['id'],root['receipt_artifact_id'],root['outcome_ref']}
                created=[];created_ids=set(known);original=self.s.insert;before=self._mutable_fingerprints()
                collector=DomainReadCollector(self,entry,principal,scope,created_ids)
                def recording(table,**fields):
                    key=original(table,**fields)
                    if not collector.busy and table not in ('object_registry','object_revision_registry','tl_dependency','tl_input_dependency'):created.append((table,key));created_ids.add(key)
                    return key
                self.s.insert=recording
                try:
                    with collector.installed(meter):
                        PersonalityGrowth(self.s).record_tool(intent,outcome);HabitLearning(self.s).record_tool(intent,outcome)
                        Memory(self.s).encode('Action result: '+dumps(outcome),outcome['evidence'])
                        self.s.insert('learning_feedback',result_ref=outcome['result'],signal_type='task',description='observed execution state: '+outcome['state'],source_ref=outcome['evidence'])
                        engine=Engine(self.s,self.identity,strict_runtime=self)
                        from digital_life.application.autonomy.exploration import Exploration
                        if Exploration(self.s).binding(activity):
                            Exploration(self.s).observed(engine,activity,outcome);AutonomyAgenda(self.s).observe(activity,outcome)
                        elif TaskLoop(self.s).config(activity):
                            TaskLoop(self.s).observed(engine,activity,outcome);AutonomyAgenda(self.s).settle(engine)
                        elif outcome['state']=='succeeded':
                            goal=self.s.row('goal_items',decision['goal_id']);Goals(self.s).transition(goal['id'],'completed',self.s.row('activities',activity)['trigger_event_id'],'strict-verified-tool-result')
                            engine.transition(activity,'completed','verified')
                            for link in self.s.db.execute('SELECT commitment_id FROM commitment_goal_links WHERE instance_id=? AND goal_id=?',(self.s.instance_id,goal['id'])):
                                promise=self.s.row('commitment_items',link[0])
                                if promise['state'] in ('active','performing'):Commitments(self.s).transition(promise['id'],'fulfilled',self.s.row('activities',activity)['trigger_event_id'],outcome['evidence'])
                        else:engine.transition(activity,'paused','result-'+outcome['state'])
                        Health(self.s).assess()
                finally:self.s.insert=original
                sources=[(token,scope)]+[(value,scope) for value in collector.tokens.values()]
                for expected,sc in sources:self.runtime.eligibility._check(entry,principal,expected,sc,'learn',principal['recipient'],'feedback_retention')
                created.extend(self._changed_mutable(before))
                for table,key in set(created):
                    for index,(expected,sc) in enumerate(sources):
                        for relation in ('read','delete'):_dependency(self.s,ref(self.s,key),expected,sc,relation,'/tool_feedback/'+str(index),'learn')
        return outcome
    def _contexts(self,entry,principal,activity,context,task,recalled,fields,scope,conversation=None):
        from digital_life.application.learning.contexts import (DomainReadCollector,calculate,calculation_read_boundary,
            calculated_retention_read_boundary,live_binding_read_boundary)
        created=[];created_ids=set();original=self.s.insert
        collector=DomainReadCollector(self,entry,principal,scope,created_ids)
        def recording(table,**values):
            key=original(table,**values)
            if not collector.busy and table not in ('object_registry','object_revision_registry','tl_dependency','tl_input_dependency'):
                created.append((table,key));created_ids.add(key)
            return key
        dependencies=[]
        for field in fields:
            for index,dependency in enumerate(field['dependencies']):
                if dependency['relation']!='delete':dependencies.append((deepcopy(dependency['expected']),deepcopy(field['dependency_scopes'][index])))
        for item in recalled['items']:
            dependencies.append((self.owners.token(ref(self.s,item['id']),item['scope']),deepcopy(item['scope'])))
        for item in (conversation or {}).get('retrieval',{}).get('items',[]) if (conversation or {}).get('retrieval') else []:
            dependencies.append((self.owners.token(ref(self.s,item['id']),item['scope']),deepcopy(item['scope'])))
        unique={(token['object']['id'],token['revision'],c.fingerprint(sc)):(token,sc) for token,sc in dependencies}
        with self._read_operation(entry,activity,context,'calculated-contexts',self._read_slice(activity,.5)) as meter,dispatch_gate(self.s.root):
            self._qualified_fields(entry,principal,ref(self.s,activity),fields,'before_context_calculation')
            with self.s.tx():
                self.s.insert=recording
                try:
                    with collector.installed(meter),calculation_read_boundary(self):
                        calculated=calculate(self.s,activity,context,task,recalled,conversation)
                finally:self.s.insert=original
                for token in collector.tokens.values():unique[(token['object']['id'],token['revision'],c.fingerprint(scope))]=(token,deepcopy(scope))
                # Calculation may write state. Start fresh material preparation
                # only after it ends; every token still receives its own live
                # qualification, without sharing an authorization verdict.
                with calculated_retention_read_boundary(self):
                    for token,sc in unique.values():self.runtime.eligibility._check(entry,principal,token,sc,principal['purpose'],principal['recipient'],'before_calculated_material_retention')
                self.owners.control()
                bundle=self.s.artifact({'contract':'TL-CALCULATED-CONTEXT-1','activity':ref(self.s,activity),'values':deepcopy(calculated),'scope':deepcopy(scope),'observed_at':utc()})
                for index,(token,sc) in enumerate(unique.values()):
                    for relation in ('read','delete'):_dependency(self.s,ref(self.s,bundle),token,sc,relation,'/calculation_sources/'+str(index),'learn')
                bundle_token={'object':ref(self.s,bundle),'revision':0,'epoch':0}
                for table,key in created:
                    for relation in ('read','delete'):_dependency(self.s,ref(self.s,key),bundle_token,scope,relation,'/calculation_bundle','learn')
        # Actual newly calculated state rows have their own immutable observed
        # versions; these are bound as live inputs rather than guessed defaults.
        live=[]
        from digital_life.domain.tool_learning_sources import SNAPSHOT_KINDS
        with self._read_operation(entry,activity,context,'calculation-live-bindings',self._read_slice(activity,.25)),live_binding_read_boundary(self):
            for field in fields:
                if field['usage']!='live_state':continue
                # Preserve the exact sources used by the calculation as live
                # bindings. A later resample cannot silently repair its body.
                self.owners.runtime.verify_live(entry,ref(self.s,activity),principal,field,'calculation_binding')
                for index,dependency in enumerate(field['dependencies']):
                    if dependency['relation']!='delete':live.append({'origin':dependency['target'],'snapshot':dependency['expected'],'scope':field['dependency_scopes'][index],'meaning':'live input actually used by this calculation'})
            for table,key in created:
                if table not in SNAPSHOT_KINDS or table in ('activities','activity_budget_accounts','policy_epochs','state_observations'):continue
                origin=ref(self.s,key);token=self.owners.snapshots.capture(entry,principal,origin,sorted(self.s.columns[table]),scope)
                live.append({'origin':origin,'snapshot':token,'scope':deepcopy(scope),'meaning':'calculated state observed during preparation'})
        basis=[self._read_dep(bundle_token)]
        new_fields=[]
        for name,value in calculated.items():
            if name=='task':continue
            new_fields.append(self._field('/input/'+name,value,scope,basis,dependency_scopes=[scope]))
        for index,value in enumerate(live):new_fields.append(self._field('/input/computation_live_bindings/'+str(index),value,value['scope'],[self._read_dep(value['snapshot'])],'live_state'))
        if not live:new_fields.append(self._field('/input/computation_live_bindings',live,scope))
        return calculated,live,new_fields
