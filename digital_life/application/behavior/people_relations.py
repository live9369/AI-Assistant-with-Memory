"""Curated person candidates, scoped aliases and evidence-bound conditional trust."""
import json
import re
import unicodedata
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,text,utc,dumps,sha
from digital_life.infrastructure.processes.dispatch_gate import coordinated
from digital_life.application.services.relationships import Relationships

VERSION='people-relations-v1'
MUTATIONS=('registered','aliased','labelled','trusted','repaired','invalidated')


def normalize(value):
    text(value,200)
    return ' '.join(unicodedata.normalize('NFKC',value).casefold().split())


from digital_life.application.accounts import account_scope as scope

class PeopleRelations:
    def __init__(self,store):self.s=store
    def authority(self,actor):
        if actor!=self.s.config()['controller']:raise Forbidden('controller required')
    def events(self,kind):
        return [dict(self.s.read_artifact(r['payload_artifact_id']),id=r['id'],sequence=r['event_seq']) for r in self.s.db.execute('SELECT id,payload_artifact_id,event_seq FROM runtime_events WHERE instance_id=? AND event_type=? ORDER BY event_seq',(self.s.instance_id,'people_relations.'+kind)) if kind=='configured' or scope.source_allowed(self.s,r['id'])]
    def event(self,ref):
        row=self.s.row('runtime_events',ref)
        if not row['event_type'].startswith('people_relations.'):raise ContractError('not a people-relations event')
        return dict(self.s.read_artifact(row['payload_artifact_id']),id=ref,sequence=row['event_seq'],kind=row['event_type'].split('.')[-1])
    def config(self):
        events=self.events('configured');return events[-1] if events else {'enabled':False,'id':None,'version':VERSION}
    def active(self):
        cfg=self.config()
        if not cfg['enabled']:raise Forbidden('people relations disabled')
        return cfg
    def revision(self):
        rows=[e for kind in MUTATIONS for e in self.events(kind)]
        return max(rows,key=lambda e:e['sequence'])['id'] if rows else None
    def prior(self,kind,key,arguments):
        text(key,200)
        old=next((e for e in self.events(kind) if e['key']==key),None)
        if old and old['arguments']!=arguments:raise Conflict('people-relations key reused')
        return self.event(old['id']) if old else None
    def emit(self,kind,key,arguments,**result):
        return self.s.event('people_relations.'+kind,payload=dict(result,key=key,arguments=arguments),source='people-relations',key=kind+':'+key,lane='control')
    @coordinated
    def configure(self,enabled,actor):
        self.authority(actor)
        if type(enabled) is not bool:raise ContractError('boolean required')
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.s.root,self.s.instance_id)
        try:
            state=c.state()
            if not state['user_stopped'] or state['active_process_run_id']:raise Conflict('stop before people-relations configuration')
        finally:c.close()
        with self.s.tx():self.s.event('people_relations.configured',payload={'enabled':enabled,'actor':actor,'version':VERSION},lane='control')
        return self.config()
    def evidence_info(self,ref):
        evidence=self.s.row('evidence_items',ref);origin=evidence['origin_object_id'];artifacts=[]
        if origin:
            if not scope.source_allowed(self.s,origin):raise Forbidden('relationship source outside account domain')
            self.s.row('object_registry',origin)
            memory=self.s.db.execute('SELECT * FROM memory_revisions WHERE instance_id=? AND id=?',(self.s.instance_id,origin)).fetchone()
            if memory:
                from digital_life.application.services.memory import Memory
                item=self.s.row('memory_items',memory['memory_id'])
                if item['state']!='active' or item['current_revision_id']!=origin or not scope.can_recall(self.s,item['id']):raise Forbidden('relationship memory source withdrawn')
            for table,column in (('perception_signals','artifact_id'),('runtime_events','payload_artifact_id')):
                row=self.s.db.execute('SELECT '+column+' FROM '+table+' WHERE instance_id=? AND id=?',(self.s.instance_id,origin)).fetchone()
                if row and row[0]:artifacts.append(row[0])
            fingerprint='object:'+origin
        elif evidence['artifact_id']:fingerprint='artifact:'+self.s.row('artifacts',evidence['artifact_id'])['hash']
        else:raise ContractError('evidence has no real source')
        if evidence['artifact_id']:artifacts.append(evidence['artifact_id'])
        for ref_artifact in artifacts:
            value=self.s.read_artifact(ref_artifact)
            if isinstance(value,dict) and 'redacted_by' in value:raise Forbidden('relationship source erased')
        return {'evidence':ref,'fingerprint':fingerprint,'method':evidence['method']}
    def evidence(self,refs,minimum=1):
        if not isinstance(refs,list) or not minimum<=len(refs)<=20 or len(set(refs))!=len(refs):raise ContractError('distinct evidence references required')
        infos=[self.evidence_info(ref) for ref in refs]
        if len({i['fingerprint'] for i in infos})<minimum:raise ContractError('distinct evidence sources required')
        return infos
    def valid(self,event):
        if any(i['target']==event['id'] for i in self.events('invalidated')):return False
        try:self.evidence(event['evidence']);return True
        except (ContractError,OSError):return False
    def actors(self):
        cfg=self.s.config();ids={cfg['controller'],cfg['self_actor']}
        if scope.active(self.s) and not scope.privileged(self.s):ids={scope.current(self.s)['id'],cfg['self_actor']}
        ids.update(e['actor'] for e in self.events('registered') if self.valid(e))
        return sorted(ids)
    def actor(self,actor):
        if actor not in self.actors():raise Forbidden('person not in current curated registry')
        return self.s.row('social_actors',actor)
    @coordinated
    def register(self,name,evidence,key,controller):
        self.authority(controller);self.active();text(name,200);arguments={'name':name,'evidence':evidence}
        with self.s.tx():
            old=self.prior('registered',key,arguments)
            if old:return old
            self.evidence(evidence)
            entity=self.s.insert('world_entities',entity_type='person',canonical_name=name,resolution_status='unresolved')
            actor=self.s.insert('social_actors',entity_id=entity,actor_type='person',identity_status='unverified');relation=Relationships(self.s).get_or_create(actor)
            ref=self.emit('registered',key,arguments,entity=entity,actor=actor,relationship=relation,evidence=evidence)
        return self.event(ref)
    @coordinated
    def alias(self,actor,alias,scope,evidence,key,controller):
        self.authority(controller);self.active();normalize(alias);text(scope,200);arguments={'actor':actor,'alias':alias,'scope':scope,'evidence':evidence}
        with self.s.tx():
            old=self.prior('aliased',key,arguments)
            if old:return old
            person=self.actor(actor);self.evidence(evidence,2)
            oldrow=self.s.db.execute('SELECT id FROM world_entity_aliases WHERE instance_id=? AND entity_id=? AND alias=?',(self.s.instance_id,person['entity_id'],alias)).fetchone()
            row=oldrow[0] if oldrow else self.s.insert('world_entity_aliases',entity_id=person['entity_id'],alias=alias,source_ref=evidence[0])
            ref=self.emit('aliased',key,arguments,actor=actor,alias=alias,scope=scope,alias_ref=row,evidence=evidence)
        return self.event(ref)
    def resolve(self,label,scope='global'):
        value=normalize(label);text(scope,200);actors=self.actors();bindings=[e for e in self.events('aliased') if e['actor'] in actors and normalize(e['alias'])==value and self.valid(e)]
        scoped=[e for e in bindings if e['scope']==scope] if scope!='global' else []
        if scoped:matches={e['actor'] for e in scoped}
        else:
            matches={a for a in actors if normalize(self.s.row('world_entities',self.s.row('social_actors',a)['entity_id'])['canonical_name'])==value}
            matches.update(e['actor'] for e in bindings if e['scope']=='global')
        return {'label':label,'scope':scope,'status':'ambiguous' if len(matches)>1 else 'unique_candidate' if matches else 'unknown','candidates':[self.describe(a,trust=False) for a in sorted(matches)],'identity_verified':False}
    @coordinated
    def relate(self,actor,label,evidence,key,controller):
        self.authority(controller);self.active();text(label,200);arguments={'actor':actor,'label':label,'evidence':evidence}
        with self.s.tx():
            old=self.prior('labelled',key,arguments)
            if old:return old
            self.actor(actor);self.evidence(evidence,2);relation=Relationships(self.s).get_or_create(actor)
            dimension=self.s.db.execute('SELECT id FROM social_relationship_dimensions WHERE instance_id=? AND definition=?',(self.s.instance_id,'role:'+label)).fetchone()
            dimension=dimension[0] if dimension else self.s.insert('social_relationship_dimensions',definition='role:'+label,scale={'min':0,'max':1},method=VERSION)
            Relationships(self.s).change(relation,dimension,1,evidence[0],controller)
            ref=self.emit('labelled',key,arguments,actor=actor,label=label,evidence=evidence)
        return self.event(ref)
    def condition(self,condition):
        if not isinstance(condition,dict) or set(condition)-{'source','task_contains'}:raise ContractError('unsupported trust condition')
        for value in condition.values():text(value,200)
        return condition
    def cell_key(self,actor,domain,dimension,condition):return dumps([actor,domain,dimension,condition])
    def cells(self,actor):
        grouped={}
        for e in self.events('trusted'):
            if e['actor']==actor and self.valid(e):grouped.setdefault(e['cell'],[]).append(e)
        result=[]
        for key,observations in sorted(grouped.items()):
            latest=observations[-1];positive=sum(e['outcome'] for e in observations);negative=len(observations)-positive
            bad=max((e['sequence'] for e in observations if not e['outcome']),default=0)
            repairs=[]
            for repair in self.events('repaired'):
                if repair['cell']!=key or repair['sequence']<=bad or not self.valid(repair):continue
                supporters=[e for e in observations if e['id'] in repair['supports'] and e['outcome'] and e['sequence']>bad]
                if len(supporters)>=2:repairs.append(repair)
            result.append({'cell':key,'actor':actor,'domain':latest['domain'],'dimension':latest['dimension'],'condition':latest['condition'],
                           'alpha':1+positive,'beta':1+negative,'estimate':(1+positive)/(2+len(observations)),'n':len(observations),'missing':False,
                           'unresolved':bool(bad and not repairs),'observations':[e['id'] for e in observations],'evidence':[r for e in observations for r in e['evidence']],
                           'last_sequence':latest['sequence'],'repairs':[e['id'] for e in repairs],'status':'controller-annotated-smoothed-frequency-not-psychometric'})
        return result
    def projected_state(self,actor):
        row=self.s.db.execute('SELECT state FROM social_relationships WHERE instance_id=? AND actor_id=?',(self.s.instance_id,actor)).fetchone()
        if row and row[0] in ('ended','dormant'):return row[0]
        return 'disputed' if any(c['unresolved'] for c in self.cells(actor)) else 'active'
    def sync_state(self,actor):
        self.s.db.execute('UPDATE social_relationships SET state=?,current_revision=current_revision+1 WHERE instance_id=? AND actor_id=?',(self.projected_state(actor),self.s.instance_id,actor))
    @coordinated
    def trust(self,actor,domain,dimension,condition,outcome,evidence,reason,key,expected_revision,controller):
        self.authority(controller);self.active();text(domain,100);text(reason,2000);self.condition(condition)
        if dimension not in ('reliability','ability','benevolence','integrity') or type(outcome) is not int or outcome not in (0,1):raise ContractError('known trust dimension and integer binary outcome required')
        arguments={'actor':actor,'domain':domain,'dimension':dimension,'condition':condition,'outcome':outcome,'evidence':evidence,'reason':reason,'expected_revision':expected_revision}
        with self.s.tx():
            old=self.prior('trusted',key,arguments)
            if old:return old
            self.actor(actor);infos=self.evidence(evidence)
            if self.revision()!=expected_revision:raise Conflict('relationship registry revision changed')
            cell=self.cell_key(actor,domain,dimension,condition);fingerprints={i['fingerprint'] for i in infos}
            if any(fingerprints&set(e['fingerprints']) for e in self.events('trusted') if e['cell']==cell):raise Conflict('trust source already consumed in this cell')
            ref=self.emit('trusted',key,arguments,actor=actor,domain=domain,dimension=dimension,condition=condition,outcome=outcome,evidence=evidence,fingerprints=sorted(fingerprints),cell=cell,reason=reason)
            projection=next(c for c in self.cells(actor) if c['cell']==cell)
            expression={'op':'and','args':[]}
            if 'source' in condition:expression['args'].append({'op':'eq','left':{'var':'source'},'right':condition['source']})
            if 'task_contains' in condition:expression['args'].append({'op':'in','left':condition['task_contains'],'right':{'var':'task'}})
            rule=self.s.insert('rule_definitions',name='trust-condition:'+ref,version=1,expression_json=expression,engine_version='rules-v1')
            relation=Relationships(self.s).get_or_create(actor)
            assessment=self.s.insert('social_trust_assessments',relationship_id=relation,domain=domain,condition_rule=rule,dimension=dimension,estimate=projection['estimate'],uncertainty_json={'method':VERSION,'alpha':projection['alpha'],'beta':projection['beta'],'n':projection['n'],'observation':ref,'status':projection['status']})
            for item in infos:self.s.insert('social_trust_evidence',assessment_id=assessment,evidence_id=item['evidence'],stance='support' if outcome else 'oppose')
            self.sync_state(actor)
        return self.event(ref)
    @coordinated
    def repair(self,actor,domain,dimension,condition,reason,key,expected_revision,controller):
        self.authority(controller);self.active();text(reason,2000);self.condition(condition)
        arguments={'actor':actor,'domain':domain,'dimension':dimension,'condition':condition,'reason':reason,'expected_revision':expected_revision}
        with self.s.tx():
            old=self.prior('repaired',key,arguments)
            if old:return old
            self.actor(actor)
            if self.revision()!=expected_revision:raise Conflict('relationship registry revision changed')
            cell=self.cell_key(actor,domain,dimension,condition);observations=[e for e in self.events('trusted') if e['cell']==cell and self.valid(e)]
            bad=max((e['sequence'] for e in observations if not e['outcome']),default=0);supports=[e for e in observations if e['outcome'] and e['sequence']>bad]
            if not bad or len(supports)<2:raise Conflict('two new positive sources after a negative observation required')
            current=next(c for c in self.cells(actor) if c['cell']==cell)
            if not current['unresolved']:raise Conflict('cell already repaired')
            evidence=[ref for e in supports[-2:] for ref in e['evidence']];self.evidence(evidence,2)
            ref=self.emit('repaired',key,arguments,actor=actor,cell=cell,supports=[e['id'] for e in supports[-2:]],evidence=evidence,reason=reason)
            self.sync_state(actor)
        return self.event(ref)
    @coordinated
    def invalidate(self,target,reason,key,controller):
        self.authority(controller);text(reason,2000);event=self.event(target)
        if event['kind'] not in ('registered','aliased','labelled','trusted','repaired'):raise ContractError('event is not a revocable assertion')
        arguments={'target':target,'reason':reason}
        with self.s.tx():
            old=self.prior('invalidated',key,arguments)
            if old:return old
            if any(e['target']==target for e in self.events('invalidated')):raise Conflict('assertion already invalidated')
            ref=self.emit('invalidated',key,arguments,target=target,reason=reason)
            for actor in self.actors():
                if self.s.db.execute('SELECT 1 FROM social_relationships WHERE instance_id=? AND actor_id=?',(self.s.instance_id,actor)).fetchone():self.sync_state(actor)
        return self.event(ref)
    def describe(self,actor,trust=True):
        row=self.s.row('social_actors',actor);entity=self.s.row('world_entities',row['entity_id']);cfg=self.s.config()
        result={'actor':actor,'entity':entity['id'],'name':entity['canonical_name'],'identity_status':row['identity_status'],'is_controller':actor==cfg['controller'],'is_self':actor==cfg['self_actor'],
                'registration_sources':[{'assertion':e['id'],'evidence':e['evidence']} for e in self.events('registered') if e['actor']==actor and self.valid(e)],
                'aliases':[{'alias':e['alias'],'scope':e['scope'],'assertion':e['id'],'evidence':e['evidence']} for e in self.events('aliased') if e['actor']==actor and self.valid(e)],
                'labels':[{'label':e['label'],'evidence':e['evidence'],'assertion':e['id']} for e in self.events('labelled') if e['actor']==actor and self.valid(e)],'relationship_state':self.projected_state(actor)}
        if trust:result['trust']=self.cells(actor)
        return result
    def variables(self,activity):
        row=self.s.db.execute('SELECT attributes_json FROM context_snapshots WHERE instance_id=? AND activity_id=?',(self.s.instance_id,activity)).fetchone();return json.loads(row[0])
    def applies(self,condition,variables):return ('source' not in condition or condition['source']==variables['source']) and ('task_contains' not in condition or condition['task_contains'] in variables['task'])
    def context(self,activity):
        cfg=self.config()
        if not cfg['enabled']:return None
        variables=self.variables(activity);scope=variables['source'];signal=self.s.row('perception_signals',self.s.row('activities',activity)['trigger_event_id']);actor=signal['source_actor_id']
        labels={self.s.row('world_entities',self.s.row('social_actors',a)['entity_id'])['canonical_name'] for a in self.actors()}
        labels.update(e['alias'] for e in self.events('aliased') if self.valid(e))
        mentions=[];task=normalize(variables['task'][:200]) if len(variables['task'])<=200 else ' '.join(unicodedata.normalize('NFKC',variables['task']).casefold().split())
        for label in sorted(labels,key=lambda s:(-len(s),s)):
            if re.search(r'(?<![a-z0-9_])'+re.escape(normalize(label))+r'(?![a-z0-9_])',task):mentions.append(self.resolve(label,scope))
            if len(mentions)>=20:break
        trust=[c for c in self.cells(actor) if c['domain']=='behavior' and c['dimension']=='reliability' and self.applies(c['condition'],variables)]
        selected=max(trust,key=lambda c:(len(c['condition']),len(c['condition'].get('task_contains','')),c['last_sequence'])) if trust else None
        return {'configuration':cfg['id'],'registry_revision':self.revision(),'version':VERSION,'scope':scope,'trigger_actor':self.describe(actor),'mentions':mentions,
                'behavior_reliability':selected,'identity_resolution':'local candidates, never authentication or permission'}
    def check(self,activity,payload):
        pinned=payload.get('relationships');cfg=self.config()
        if not cfg['enabled'] and pinned is None:return
        if not pinned or pinned!=self.context(activity):raise Forbidden('people or relationship context superseded or source withdrawn')
    def subject(self,label,activity):
        if not self.config()['enabled']:return None
        key=activity+':'+sha(normalize(label));prior=next((e for e in self.events('subject_bound') if e['binding_key']==key),None)
        if prior:return prior['entity']
        scope=self.variables(activity)['source'];resolution=self.resolve(label,scope)
        aliases=[e for e in self.events('aliased') if normalize(e['alias'])==normalize(label) and self.valid(e)]
        scoped=[e for e in aliases if e['scope']==scope] if scope!='global' else []
        reviewed={e['actor'] for e in (scoped or [e for e in aliases if e['scope']=='global'])}
        bound=resolution['status']=='unique_candidate' and resolution['candidates'][0]['actor'] in reviewed
        entity=resolution['candidates'][0]['entity'] if bound else self.s.insert('world_entities',entity_type='claim-subject',canonical_name=label,resolution_status='ambiguous' if resolution['status']=='ambiguous' else 'unresolved')
        self.s.event('people_relations.subject_bound',payload={'binding_key':key,'activity':activity,'label':label,'entity':entity,'status':'reviewed-local-binding' if bound else resolution['status'],'reviewed_binding':bound,'scope':scope},activity=activity,source='people-subject',key=key)
        return entity
    def status(self):return {'configuration':self.config(),'revision':self.revision(),'people':[self.describe(a) for a in self.actors()],'inference_started':False}
