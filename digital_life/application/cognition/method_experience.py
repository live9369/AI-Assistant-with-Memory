"""Audited explicit method feedback; M03 revisions remain the method authority."""
import json
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,sha,dumps,text
from digital_life.infrastructure.processes.dispatch_gate import coordinated

class MethodExperience:
    def __init__(self,store):self.s=store
    def events(self,kind):
        return [dict(self.s.read_artifact(r['payload_artifact_id']),id=r['id']) for r in self.s.db.execute('SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type=? ORDER BY event_seq',(self.s.instance_id,'cognition.method_'+kind))]
    def method(self,revision):
        from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
        row=self.s.row('cognition_belief_revisions',revision);value=json.loads(row['content']);belief=self.s.row('cognition_beliefs',row['belief_id'])
        if value.get('kind')!='method' or not value.get('context_contains') or row['acceptance_state']!='accepted' or belief['current_revision_id']!=revision or not CognitiveUpdates(self.s).readable_revision(revision):raise Forbidden('method is not a current readable reviewed method')
        return value
    @coordinated
    def feedback(self,revision,outcome,source,reason,actor):
        if actor!=self.s.config()['controller']:raise Forbidden('controller required')
        if outcome not in ('success','failure','unknown'):raise ContractError('invalid method outcome')
        text(reason,2000);self.method(revision)
        signal=self.s.row('perception_signals',source)
        activity=self.s.db.execute('SELECT id FROM activities WHERE trigger_event_id=? AND instance_id=?',(source,self.s.instance_id)).fetchone()
        context=self.s.db.execute('SELECT attributes_json FROM context_snapshots WHERE activity_id=? ORDER BY rowid LIMIT 1',(activity[0],)).fetchone() if activity else None
        if signal['source_actor_id']!=actor or not context or not (json.loads(context[0]).get('source')=='user' or json.loads(context[0]).get('source','').startswith('chat:')):raise Forbidden('explicit external controller feedback source required')
        from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
        CognitiveUpdates(self.s).source_value(source)
        old=next((v for v in self.events('feedback') if v['revision']==revision and v['source']==source),None)
        if old:
            if old['outcome']!=outcome or old['reason']!=reason:raise Conflict('same feedback source cannot change meaning')
            return dict(old,reused=True)
        value={'revision':revision,'outcome':outcome,'source':source,'reason':reason,'actor':actor,'basis':'explicit-controller-evaluation; not independent objective proof'}
        with self.s.tx():ref=self.s.event('cognition.method_feedback',payload=value,source='method-feedback',key=sha(dumps([revision,source])),lane='control')
        return dict(value,id=ref)
    @coordinated
    def retract(self,feedback,reason,actor):
        if actor!=self.s.config()['controller']:raise Forbidden('controller required')
        text(reason,2000)
        if not any(v['id']==feedback for v in self.events('feedback')):raise ContractError('method feedback missing')
        with self.s.tx():return self.s.event('cognition.method_retracted',payload={'feedback':feedback,'reason':reason,'actor':actor},lane='control')
    def effect(self,direction):
        from digital_life.application.cognition.cognition_memory import revision_for
        from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
        from digital_life.application.accounts import account_scope as account_scope
        from digital_life.application.services.memory import Memory
        revoked={v['feedback'] for v in self.events('retracted')};feedback=self.events('feedback');methods=[]
        for ref in direction['evidence_refs']:
            memory=self.s.db.execute('SELECT memory_id FROM memory_revisions WHERE id=? AND instance_id=?',(ref,self.s.instance_id)).fetchone()
            if not memory:continue
            item=self.s.row('memory_items',memory[0])
            if item['state']!='active' or item['current_revision_id']!=ref or not account_scope.can_recall(self.s,item['id']):continue
            revision=revision_for(self.s,item['id'])
            if not revision:continue
            try:method=self.method(revision)
            except (ContractError,Forbidden):continue
            if method['context_contains'].casefold() not in (direction['title']+' '+direction.get('next_step','')).casefold():continue
            samples=[]
            for v in feedback:
                if v['revision']!=revision or v['id'] in revoked or v['outcome']=='unknown':continue
                try:CognitiveUpdates(self.s).source_value(v['source'])
                except (ContractError,OSError):continue
                samples.append(v)
            signed=sum(1 if v['outcome']=='success' else -1 for v in samples)
            methods.append({'revision':revision,'cue':method['context_contains'],'feedback_refs':[v['id'] for v in samples],'samples':len(samples),'delta':.4*signed/(len(samples)+3)})
        return {'delta':sum(m['delta'] for m in methods)/len(methods) if methods else 0.,'methods':methods,'version':'reviewed-method-effect-v1','scope':'direction selection only; engineering prior'}
