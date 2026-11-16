"""Actual runtime-only admission of bounded new self-intent activities."""
from copy import deepcopy
from contextlib import contextmanager
from digital_life.domain.contracts import Forbidden,Conflict,utc,sha,dumps
from digital_life.application.learning.engine import active_profile,_create_original_input,_dependency,source_scope
from digital_life.application.learning.eligibility import ref
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter

class InternalAdmission:
    def __init__(self,strict):self.engine=strict;self.s=strict.s;self.o=strict.owners
    @contextmanager
    def _source_reads(self):
        original=self.s.read_artifact;self._observed={};busy=[False]
        entry,principal=self.o.entry('M14','learn',self.s.config()['self_actor']);scope=source_scope(self.s)
        def read(artifact):
            if not busy[0]:
                owner=self.s.db.execute("SELECT id FROM runtime_events WHERE instance_id=? AND payload_artifact_id=? UNION SELECT id FROM perception_signals WHERE instance_id=? AND artifact_id=? UNION SELECT id FROM configuration_versions WHERE instance_id=? AND artifact_ref=? UNION SELECT id FROM model_versions WHERE instance_id=? AND artifact_ref=? UNION SELECT id FROM thought_results WHERE instance_id=? AND (response_artifact_id=? OR parsed_artifact_id=?)",(self.s.instance_id,artifact,self.s.instance_id,artifact,self.s.instance_id,artifact,self.s.instance_id,artifact,self.s.instance_id,artifact,artifact)).fetchone()
                if owner is None:raise Forbidden('housekeeping artifact has no explicitly supported actual owner')
                if owner:
                    busy[0]=True
                    try:
                        token=self.o.token(ref(self.s,owner[0]),scope)
                        self.engine.runtime.eligibility._check(entry,principal,token,scope,'learn',principal['recipient'],'internal_scheduler_read')
                        self._observed[owner[0]]=token
                    finally:busy[0]=False
            return original(artifact)
        self.s.read_artifact=read
        try:yield
        finally:self.s.read_artifact=original
    def tick(self):
        self.o.control();epoch,policy,caps=active_profile(self.s)
        # This bounded scheduler inspection is not an inference or a fresh cap
        # for existing work. Existing held opportunities prevent new admission.
        limits={'input_tokens':0,'output_tokens':0,'attempts':0,'tool_calls':0,'scan':min(caps['max_scan'],16384),'items':min(caps['max_items'],16384),'bytes':min(caps['max_bytes'],8*1024*1024),'elapsed_ms':min(caps['elapsed_ms'],10000)}
        with dispatch_gate(self.s.root):
            last=self.s.db.execute("SELECT id,recorded_at FROM runtime_events WHERE instance_id=? AND source='strict.housekeeping.reserved' ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,)).fetchone()
            if last:
                settled=self.s.db.execute("SELECT id FROM runtime_events WHERE instance_id=? AND source='strict.housekeeping.settled' AND source_event_id=? LIMIT 1",(self.s.instance_id,last['id'])).fetchone()
                if settled is None or last['recorded_at']>utc(-60):return None
            with self.s.tx():opportunity=self.s.event('strict.housekeeping.reserved',payload={'contract':'TL-HOUSEKEEPING-OPPORTUNITY-1','limits':limits,'policy':policy['id'],'process':self.engine.identity.process_id,'runtime_epoch':self.engine.identity.epoch,'minimum_interval_seconds':60,'max_per_interval':1},source='strict.housekeeping.reserved')
            meter=PhysicalReadMeter(limits,utc(limits['elapsed_ms']/1000))
            try:
                with meter.installed(self.s),self.s.tx(),self._source_reads():return self._inspect(caps,epoch,policy)
            finally:
                # This fixed-size management witness is not a new activity
                # account. A crash without a known receipt leaves the durable
                # opportunity occupied across process restarts.
                actual=meter.usage()
                if actual is not None:
                    with self.s.tx():self.s.event('strict.housekeeping.settled',payload={'contract':'TL-HOUSEKEEPING-USAGE-1','opportunity':opportunity,'actual':actual,'basis':'actual bounded primary-store material and monotonic inspection duration; fixed control-witness bookkeeping separate'},source='strict.housekeeping.settled',key=opportunity)
    def _latest_config(self,event_type,default):
        row=self.s.db.execute('SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type=? ORDER BY event_seq DESC LIMIT 1',(self.s.instance_id,event_type)).fetchone()
        if row is None:return deepcopy(default)
        value=self.s.read_artifact(row['payload_artifact_id'])
        if event_type=='exploration.configured':value=dict(value,generation=row['id'])
        return value
    def _inspect(self,caps,epoch,policy):
        self.o.control()
        agenda_cfg=self._latest_config('agenda.configured',{'enabled':False})
        exploration_cfg=self._latest_config('exploration.configured',{'enabled':False})
        if not agenda_cfg.get('enabled') and not exploration_cfg.get('enabled'):return None
        if self.s.db.execute("SELECT 1 FROM activities WHERE instance_id=? AND state NOT IN ('completed','failed','cancelled','paused') LIMIT 1",(self.s.instance_id,)).fetchone():return None
        for row in self.s.db.execute('SELECT budget_json FROM activities WHERE instance_id=?',(self.s.instance_id,)):
            doc=__import__('json').loads(row[0]);ledger=doc.get('ledger',{})
            if any(r.get('state') in ('reserved','entered','usage_unknown') for r in ledger.get('reservations',{}).values()):return None
        from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
        agenda=AutonomyAgenda(self.s)
        if agenda_cfg.get('enabled'):
            for p in sorted(agenda.events('promise'),key=lambda v:(v['spec']['due_at'],v['commitment'])):
                promise=self.s.row('commitment_items',p['commitment'])
                if promise['state']!='active' or agenda.bound(p['commitment']) or p['spec']['start_at']>utc() or p['spec']['due_at']<=utc():continue
                task=p['spec']['content'];key='agenda:'+p['commitment']
                activity=self._admit('commitment',task,key,p['signal'],caps,epoch,policy,p['spec']['due_at'])
                from digital_life.application.autonomy.task_loop import TaskLoop
                TaskLoop(self.s).configure(activity,p['spec']['verification'],self.s.config()['controller'],p['spec']['max_rounds'])
                goal=self.s.db.execute('SELECT id FROM goal_items WHERE instance_id=? AND source_ref=(SELECT trigger_event_id FROM activities WHERE id=?)',(self.s.instance_id,activity)).fetchone()[0]
                self.s.insert('commitment_goal_links',commitment_id=p['commitment'],goal_id=goal,role='fulfillment');agenda.emit('bound',{'commitment':p['commitment'],'activity':activity},activity)
                self.o.control();return activity
        from digital_life.application.autonomy.exploration import Exploration
        x=Exploration(self.s);cfg=exploration_cfg
        if not cfg.get('enabled'):return None
        bindings=[b for b in x.payloads('exploration.bound') if b['generation']==cfg['generation']]
        if len(bindings)>=cfg['max_activities'] or bindings and bindings[-1]['next_due']>utc():return None
        candidates=[q for q in x.questions().values() if q['state'] in ('candidate','dormant') and q['due_at']<=utc() and q['visits']<2 and x.readable_refs(q['evidence_refs'])]
        candidates.sort(key=lambda q:(-agenda.score(q),q['id']));q=candidates[0] if candidates else None
        task=q['question'] if q else 'Review recent experiences, find a testable knowledge gap, and propose questions with evidence. Do not invent observations.'
        bounded=deepcopy(caps);bounded['max_input_tokens']=min(bounded['max_input_tokens'],cfg['max_rounds']*3*4096-bounded['max_output_tokens']);bounded['max_attempts']=min(bounded['max_attempts'],cfg['max_rounds']*4);bounded['max_tool_calls']=min(bounded['max_tool_calls'],cfg['max_rounds'])
        if bounded['max_input_tokens']<=0:raise Forbidden('exploration original token allowance unavailable')
        activity=self._admit('exploration',task,cfg['generation']+':'+str(len(bindings)),cfg['generation'],bounded,epoch,policy)
        x.s.event('exploration.bound',payload={'version':1,'activity':activity,'generation':cfg['generation'],'kind':'investigate' if q else 'discover','question_id':q['id'] if q else None,'max_rounds':cfg['max_rounds'],'next_due':utc(cfg['interval_seconds'])},activity=activity)
        if q:
            x.record(dict(q,state='investigating',visits=q['visits']+1,activity=activity))
            from digital_life.application.learning.self_feedback import SelfFeedback
            SelfFeedback(self.s).bind(activity,q)
        self.o.control();return activity
    def _admit(self,module,task,key,trigger,caps,epoch,policy,due=None):
        # Only tick selects these values from the actual module records while
        # holding the same gate; callers do not submit a module/grant JSON.
        self.o.control();current_epoch,current_policy,authorized=active_profile(self.s)
        if epoch!=current_epoch or policy!=current_policy:raise Conflict('internal policy changed')
        if module=='commitment':
            from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
            a=AutonomyAgenda(self.s);p=next((p for p in a.events('promise') if 'agenda:'+p['commitment']==key),None)
            if not a.config().get('enabled') or p is None or trigger!=p['signal'] or task!=p['spec']['content'] or due!=p['spec']['due_at'] or caps!=authorized:raise Forbidden('actual promise does not authorize this task/hash/caps')
            if a.bound(p['commitment']) or self.s.row('commitment_items',p['commitment'])['state']!='active' or p['spec']['start_at']>utc() or due<=utc():raise Forbidden('promise no longer admits new work')
        elif module=='exploration':
            from digital_life.application.autonomy.exploration import Exploration
            x=Exploration(self.s);cfg=x.config();bindings=[b for b in x.payloads('exploration.bound') if b['generation']==cfg.get('generation')]
            expected=deepcopy(authorized);expected['max_input_tokens']=min(expected['max_input_tokens'],cfg.get('max_rounds',0)*3*4096-expected['max_output_tokens']);expected['max_attempts']=min(expected['max_attempts'],cfg.get('max_rounds',0)*4);expected['max_tool_calls']=min(expected['max_tool_calls'],cfg.get('max_rounds',0))
            allowed=['Review recent experiences, find a testable knowledge gap, and propose questions with evidence. Do not invent observations.']+[q['question'] for q in x.questions().values() if q['state'] in ('candidate','dormant') and q['due_at']<=utc() and q['visits']<2 and x.readable_refs(q['evidence_refs'])]
            if not cfg.get('enabled') or trigger!=cfg['generation'] or key!=cfg['generation']+':'+str(len(bindings)) or len(bindings)>=cfg['max_activities'] or bindings and bindings[-1]['next_due']>utc() or task not in allowed or caps!=expected or due is not None:raise Forbidden('actual exploration generation does not authorize this task/hash/caps')
        else:raise Forbidden('unsupported internal admission module')
        origin=ref(self.s,trigger);scope=source_scope(self.s)
        entry,principal=self.o.entry('M14','learn',self.s.config()['self_actor'])
        token=self.o.token(origin,scope);self.engine.runtime.eligibility._check(entry,principal,token,scope,'learn',principal['recipient'],'internal_new_activity')
        identity='runtime-self:'+self.engine.identity.process_id+':'+str(self.engine.identity.epoch)+':'+module+':'+sha(dumps([key,task,trigger]))
        activity=_create_original_input(self.s,task,key,module,caps,epoch,policy,identity,self.s.config()['self_actor'],due_at=due)
        signal=self.s.row('activities',activity)['trigger_event_id']
        roots=dict(getattr(self,'_observed',{}));roots[trigger]=token
        for consumer in (ref(self.s,signal),ref(self.s,self.s.row('perception_signals',signal)['artifact_id'])):
            for source_id,source_token in roots.items():
                for relation in ('read','delete'):_dependency(self.s,consumer,source_token,scope,relation,'/self_intent_trigger/'+source_id,'learn')
        self.o.control();return activity
