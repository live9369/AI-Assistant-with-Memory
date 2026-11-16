"""Only synthetic inference and temporary workspace tools. No service startup."""
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import time
from unittest.mock import patch

from digital_life.application.runtime.engine import Engine
from digital_life.application.autonomy.exploration import Exploration
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.accounts.authorization import Policy
from digital_life.application.services.memory import Memory
from digital_life.application.runtime.scheduling import Budget
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.infrastructure.tools.workspace import registry
from digital_life.domain.contracts import ContractError,Forbidden,RuntimeIdentity,ToolResult,utc,sha,dumps

class FixtureModel:
    name='ae-g1-scripted-v1'
    def __init__(self,harness):
        self.h=harness; self.inputs=[]; self.mutate=None; self.on_dispatch=None; self.always_continue=False; self.fail=False
    def generate(self,request):
        h=self.h; ctx=request.get('exploration')
        attempt=h.latest_attempt('thought_attempts')
        h.trace('dispatch',transport='model',operation_id=attempt['id'],request_id=attempt['request_id'],activity=request['activity_id'])
        self.inputs.append(copy.deepcopy(request))
        if self.on_dispatch:
            callback=self.on_dispatch; self.on_dispatch=None; callback()
        if self.fail: raise ContractError('injected-model-failure')
        if ctx is None:
            return {'schema_version':1,'action':{'tool':'wait','arguments':{'reason':'legacy fixture'}},'explanation':'isolated V1'}
        e={'candidates':[],'disposition':'dormant','assessment':'Synthetic mechanism fixture; no quality claim.','evidence_refs':[]}
        action={'tool':'wait','arguments':{'reason':'fixture pause'}}
        if ctx['kind']=='discover' and ctx['allowed_evidence_refs']:
            question='What does the latest local record show for '+h.case['topic']+'?'
            e['candidates']=[{'question':question,'verification':'Read '+h.case['public']['observation_path']+' and compare its observed value with the recorded experience.',
                'expected_gain':0.8,'cost':0.1,'evidence_refs':[ctx['allowed_evidence_refs'][0]]}]
        elif ctx['kind']=='investigate' and (not ctx['observations'] or self.always_continue):
            e['disposition']='continue'; action={'tool':'read_file','arguments':{'path':h.case['public']['observation_path']}}
        elif ctx['kind']=='investigate':
            if h.case['fixture_behavior']!='dormant': e['disposition']='resolved'
            e['assessment']='Fixture observed receipt: '+str(ctx['observations'][-1]['receipt']['evidence'])
            e['evidence_refs']=[ctx['observations'][-1]['evidence_ref']]
        output={'schema_version':2,'action':action,'explanation':'Synthetic inference, not a quality evaluator.','exploration':e}
        if self.mutate: self.mutate(request,output)
        h.trace('model_output',request_id=attempt['request_id'],output=copy.deepcopy(output))
        return output

class Harness:
    def __init__(self,root,case,trace_path=None):
        self.root=Path(root); self.case=case; self.trace_path=Path(trace_path) if trace_path else None; self.trace_events=[]; self.trace_lock=threading.Lock(); self.assertions=[]
        self.s=Store.prepare(self.root,model_config={'backend':'fixture','model':'ae-g1-scripted-v1'})
        self.c=Control(self.root,self.s.instance_id); self.x=Exploration(self.s); self.engine=Engine(self.s,RuntimeIdentity(0,'ae-g1-offline'))
        self.pending_stops=[]; self.model=FixtureModel(self); self.on_tool_dispatch=None; self.tool_outcome=None; self.world_applied=False
        for relative,content in case['public']['files'].items():
            path=self.root/'workspace'/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content)
        with self.s.tx():
            ev=self.s.evidence(artifact=self.s.artifact({'source':'authored-fixture','case_id':case['case_id']}))
            self.memory=Memory(self.s).encode(case['public']['memory'],ev)
        self.trace('fixture_ready',case_id=case['case_id'])
    def close(self): self.c.close(); self.s.close()
    def trace(self,kind,**fields):
        with self.trace_lock:
            event=dict(kind=kind,seq=len(self.trace_events)+1,monotonic_ns=time.monotonic_ns(),utc=utc(),**fields)
            self.trace_events.append(event)
            if self.trace_path:
                with self.trace_path.open('a') as stream: stream.write(json.dumps(event,ensure_ascii=False)+'\n')
            return event
    def check(self,condition,label,**details):
        self.assertions.append({'label':label,'passed':bool(condition),'details':details})
        if not condition: raise AssertionError(label+': '+str(details))
    def raises(self,exception,fn,label):
        try: fn()
        except exception as error:
            self.trace('expected_rejection',exception=type(error).__name__,label=label); self.check(True,label); return
        self.check(False,label)
    def latest_attempt(self,table):
        return dict(self.s.db.execute('SELECT * FROM '+table+' WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone())
    def enable(self,**options):
        self.x.configure(self.s.config()['controller'],True,**options)
        # This path is only ever created under the runner's TemporaryDirectory.
        (self.root/'WAKE_DISABLED').unlink(); self.c.resume('g1-isolated-resume')
        Policy(self.s).mode('open',['read_file','list_files'],self.s.config()['controller'])
        self.trace('fixture_unlocked',scope='temporary-instance-only')
    def tick_due(self):
        with patch('digital_life.application.autonomy.exploration.utc',side_effect=lambda seconds=0:utc(3600+seconds)):
            return self.x.tick(self.engine)
    def discovery(self):
        self.enable(); activity=self.x.tick(self.engine); self.engine.think(activity,self.model)
        return activity
    def investigation(self):
        self.discovery(); activity=self.tick_due(); self.check(activity is not None,'investigation-created'); return activity
    def propose(self,activity): return self.engine.think(activity,self.model)
    def backend(self,action,root,operation):
        attempt=self.latest_attempt('action_attempts')
        self.trace('dispatch',transport='tool',operation_id=operation,attempt_id=attempt['id'],intent_id=attempt['intent_id'],tool=action['tool'])
        if self.on_tool_dispatch:
            callback=self.on_tool_dispatch; self.on_tool_dispatch=None; callback()
        if not self.world_applied:
            for event in self.case['world_events']:
                path=self.root/'workspace'/event['path']; path.write_text(event['replacement'])
                self.trace('world_event',event=event)
            self.world_applied=True
        if self.tool_outcome is not None: return self.tool_outcome
        return registry().invoke(action,root,operation)
    def execute(self,proposal): return self.engine.execute(proposal['action_id'],self.backend)
    def finish(self,activity):
        proposal=self.propose(activity); outcome=self.execute(proposal)
        self.check(self.s.row('activities',activity)['state']=='running','read-is-not-resolution')
        result=self.engine.think(activity,self.model)
        self.trace('assessment_complete',result=result)
        return proposal,outcome
    def stop(self,control,defer=False):
        self.trace('stop_requested',control=control)
        if control=='disable': self.x.configure(self.s.config()['controller'],False)
        elif control=='user_stop': self.c.stop('g1-stop-'+str(len(self.trace_events)))
        else:
            # Actual second connection/thread commits a user stop at a deterministic interleaving.
            failures=[]
            def competitor():
                c=Control(self.root,self.s.instance_id)
                try:
                    c.stop('g1-competing-stop')
                    self.trace('stop_committed',control=control)
                except BaseException as e: failures.append(e)
                finally: c.close()
            t=threading.Thread(target=competitor); t.start()
            self.pending_stops.append((t,failures))
            if not defer: self.await_stops()
            return
        self.trace('stop_committed',control=control)
    def await_stops(self):
        for thread,failures in self.pending_stops:
            thread.join(5)
            if thread.is_alive(): raise RuntimeError('stop competitor timeout')
            if failures: raise failures[0]
        self.pending_stops=[]
    @contextmanager
    def after_send_commit(self,transport,callback):
        original=self.s.tx; table='thought_attempts' if transport=='model' else 'action_attempts'
        before=len(self.s.rows(table)); armed=[True]
        @contextmanager
        def intercept():
            with original(): yield self.s
            if armed[0] and self.s.depth==0 and len(self.s.rows(table))>before:
                armed[0]=False
                self.trace('send_transaction_committed',transport=transport)
                callback()
        with patch.object(self.s,'tx',new=intercept): yield
        self.check(not armed[0],'pre-dispatch-injection-fired')
    def safe_call(self,fn):
        try: return fn()
        except (ContractError,Forbidden) as error:
            self.trace('rejected',exception=type(error).__name__,reason=str(error)); return None
    def audit(self):
        accepted=self.s.db.execute("SELECT request_id,count(*) n FROM thought_results WHERE acceptance='accepted' GROUP BY request_id").fetchall()
        over_accept=sum(max(0,r['n']-1) for r in accepted)
        illegal_refs=0; total_refs=0
        for r in self.s.rows('thought_results'):
            if r['acceptance']!='accepted': continue
            request=self.s.row('thought_requests',r['request_id']); payload=self.s.read_artifact(request['request_artifact_id'])
            output=self.s.read_artifact(r['response_artifact_id'])
            if 'exploration' not in output: continue
            e=output['exploration']; refs=e['evidence_refs']+[ref for c in e['candidates'] for ref in c['evidence_refs']]
            total_refs+=len(refs); illegal_refs+=sum(ref not in payload['exploration']['allowed_evidence_refs'] for ref in refs)
        violations=[]
        for account in self.s.rows('activity_budget_accounts'):
            reservations=[r for r in self.s.rows('budget_reservations') if r['activity_id']==account['activity_id'] and r['state']!='released']
            used={'token_limit':sum(r['reserved_tokens'] for r in reservations),'attempt_limit':len(reservations),'tool_call_limit':sum(r['reserved_tool_calls'] for r in reservations)}
            for key,value in used.items():
                if value>account[key]: violations.append({'kind':key,'used':value,'limit':account[key]})
        bound=self.x.payloads('exploration.bound'); cfgs={e['id']:self.s.read_artifact(e['payload_artifact_id']) for e in self.x.events('exploration.configured')}
        for generation,cfg in cfgs.items():
            count=sum(b['generation']==generation for b in bound)
            if count>cfg['max_activities']: violations.append({'kind':'activities','used':count,'limit':cfg['max_activities']})
        for b in bound:
            requests=[r for r in self.s.rows('thought_requests') if r['activity_id']==b['activity']]
            if len(requests)>b['max_rounds']: violations.append({'kind':'rounds'})
        for q in self.x.questions().values():
            if q['visits']>2: violations.append({'kind':'visits'})
        stops=[e for e in self.trace_events if e['kind']=='stop_committed']
        dispatches=[e for e in self.trace_events if e['kind']=='dispatch']
        post=[d for d in dispatches if stops and d['monotonic_ns']>stops[0]['monotonic_ns']]
        tools=[e for e in dispatches if e['transport']=='tool']; seen=set(); duplicates=[]
        for e in tools:
            if e['operation_id'] in seen: duplicates.append(e['operation_id'])
            seen.add(e['operation_id'])
        counts={'model_attempts':len(self.s.rows('thought_attempts')),'tool_attempts':len(self.s.rows('action_attempts'))}
        return dict(accepted_reference_count=total_refs,illegal_accepted_references=illegal_refs,
            multiple_acceptance_count=over_accept,budget_violations=violations,post_stop_dispatches=post,
            stop_boundaries=len(stops),dispatch_count=len(dispatches),duplicate_read_dispatches=duplicates,cost=counts,
            recovery_check=next((a['passed'] for a in self.assertions if a['label']=='recovery-continuity'),None))
    def export(self,directory):
        directory=Path(directory); directory.mkdir(exist_ok=True,parents=True)
        tables=['runtime_events','activities','activity_steps','thought_requests','thought_results','thought_attempts','action_attempts','action_results','activity_budget_accounts','budget_reservations','goal_items','evidence_items','memory_revisions','thought_request_inputs']
        snapshot={name:self.s.rows(name) for name in tables}
        snapshot['questions']=list(self.x.questions().values()); snapshot['instance_id']=self.s.instance_id
        (directory/'snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n')
        artifacts={r['id']:self.s.read_artifact(r['id']) for r in self.s.rows('artifacts')}
        (directory/'artifacts.json').write_text(json.dumps(artifacts,ensure_ascii=False,indent=2)+'\n')
        (directory/'trace.json').write_text(json.dumps(self.trace_events,ensure_ascii=False,indent=2)+'\n')
        return self.audit()
