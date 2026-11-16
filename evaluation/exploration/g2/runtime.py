"""Real-model trials over public-only material; no scripted answers or oracle access."""
import copy
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from unittest.mock import patch
from digital_life.application.runtime.engine import Engine
from digital_life.application.autonomy.exploration import Exploration
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.accounts.authorization import Policy
from digital_life.application.services.memory import Memory
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.infrastructure.llm.inference import configured_reasoner
from digital_life.infrastructure.tools.workspace import registry,safe_path
from digital_life.domain.contracts import RuntimeIdentity,ToolResult,utc,ContractError

class TrialBudget(ContractError): pass

class RealObserver:
    def __init__(self,env,config):
        self.env=env;self.base=configured_reasoner(config);self.name=self.base.name;self.last_usage=None;self.last_session_id=None
        self.calls=0;self.observed_tokens=0;self.unknown_usage=0;self.processes=[]
    def generate(self,request):
        env=self.env;remaining=env.deadline-time.monotonic()
        if self.calls>=env.limits['model_calls'] or remaining<=1: raise TrialBudget('real-model call or wall-clock budget exhausted')
        if self.observed_tokens>=env.limits['observed_tokens']: raise TrialBudget('observed token budget exhausted')
        if self.unknown_usage: raise TrialBudget('previous real call had unknown usage; no further unmetered call')
        self.calls+=1;self.last_usage=None;self.last_session_id=None
        self.base.timeout=min(env.model_config['timeout'],max(1,remaining-0.5))
        attempt=dict(env.s.db.execute('SELECT * FROM thought_attempts ORDER BY rowid DESC LIMIT 1').fetchone())
        env.trace('dispatch',transport='model',operation_id=attempt['id'],request_id=attempt['request_id'],activity=request['activity_id'])
        # Every process created by this synchronous Codex call remains owned through interruption.
        original=subprocess.Popen; owned=[]
        def tracked(*args,**kwargs):
            process=original(*args,**kwargs);owned.append(process);self.processes.append(process.pid);return process
        try:
            if env.model_config['backend']=='codex_cli':
                with patch.object(subprocess,'Popen',side_effect=tracked): output=self.base.generate(copy.deepcopy(request))
            else: output=self.base.generate(copy.deepcopy(request))
            self.last_usage=copy.deepcopy(getattr(self.base,'last_usage',None));self.last_session_id=getattr(self.base,'last_session_id',None)
            if self.last_usage and all(type(self.last_usage.get(k)) is int for k in ('input_tokens','output_tokens')):
                self.observed_tokens+=self.last_usage['input_tokens']+self.last_usage['output_tokens']
            else:self.unknown_usage+=1
            env.trace('model_output',request_id=attempt['request_id'],output=output,usage=self.last_usage)
            return output
        except BaseException as error:
            if owned:self.unknown_usage+=1
            env.trace('model_error',request_id=attempt['request_id'],error_type=type(error).__name__)
            raise
        finally:
            for process in owned:
                if process.poll() is None:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait(timeout=5)

class RealTrial:
    def __init__(self,root,case,config,limits,directory):
        self.root=Path(root);self.case=case;self.directory=Path(directory);self.model_config=dict(config);self.limits=limits
        self.trace_events=[];self.deadline=time.monotonic()+limits['wall_seconds'];self.start=time.monotonic();self.virtual=datetime.now(timezone.utc)
        self.s=Store.prepare(self.root,model_config=config);self.c=Control(self.root,self.s.instance_id);self.epoch=0
        self.engine=Engine(self.s,RuntimeIdentity(self.epoch,'g2-isolated-0'));self.x=Exploration(self.s)
        self.model=RealObserver(self,config);self.applied_events=set();self.tool_calls=0;self.observations=0;self.faults=0;self.errors=[]
        for relative,content in case['files'].items():
            path=safe_path(self.root/'workspace',relative);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
        with self.s.tx():
            for memory in case['memories']:
                evidence=self.s.evidence(artifact=self.s.artifact({'source':'public-experience','content':memory}))
                Memory(self.s).encode(memory,evidence)
        self.x.configure(self.s.config()['controller'],True,max_activities=limits['activities'],max_rounds=3,interval_seconds=300)
        (self.root/'WAKE_DISABLED').unlink();self.c.resume('g2-temporary-instance-only')
        Policy(self.s).mode('open',['read_file','list_files'],self.s.config()['controller'])
        self.trace('initialized',scope='temporary public-only workspace')
    def trace(self,kind,**fields):
        value={'kind':kind,'seq':len(self.trace_events)+1,'monotonic_ns':time.monotonic_ns(),'utc':utc(),**fields}
        self.trace_events.append(value)
        with (self.directory/'live-trace.jsonl').open('a') as stream:stream.write(json.dumps(value,ensure_ascii=False)+'\n')
    def clock(self,seconds=0):return (self.virtual+timedelta(seconds=seconds)).isoformat(timespec='milliseconds').replace('+00:00','Z')
    def backend(self,action,root,operation):
        if time.monotonic()>=self.deadline:raise TrialBudget('tool wall-clock budget exhausted')
        self.tool_calls+=1;self.trace('dispatch',transport='tool',operation_id=operation,action=action)
        for i,event in enumerate(self.case['world_events']):
            if i not in self.applied_events and event['when']=='before_first_tool_dispatch':
                safe_path(self.root/'workspace',event['path']).write_text(event['replacement']);self.applied_events.add(i);self.trace('world_event',event=event)
        fault=self.case.get('fault')
        if fault and self.faults<fault['count']:
            self.faults+=1;kind=fault['kind'];self.trace('planned_tool_fault',fault=kind)
            return ToolResult('timeout' if kind=='unknown' else 'received',kind,'unknown' if kind=='unknown' else 'fail',{},'pre-registered synthetic environmental fault')
        return registry().invoke(action,root,operation)
    def restart_if_due(self):
        observed=len(self.x.payloads('exploration.observed'))
        if observed==0:return
        for i,event in enumerate(self.case['world_events']):
            if i in self.applied_events or event['when']!='after_first_observation' or event.get('operation')!='restart':continue
            self.applied_events.add(i);before=self.x.questions();self.c.close();self.s.close();self.epoch+=1
            self.s=Store(self.root);self.c=Control(self.root,self.s.instance_id);self.x=Exploration(self.s);self.engine=Engine(self.s,RuntimeIdentity(self.epoch,'g2-isolated-'+str(self.epoch)))
            self.trace('restart',epoch=self.epoch,problem_identity_preserved=set(before)==set(self.x.questions()),observed_count=observed)
    def run(self):
        stop_reason='completed-budget'
        for _ in range(self.limits['activities']*10+10):
            if time.monotonic()>=self.deadline:stop_reason='wall-budget';break
            if self.model.calls>=self.limits['model_calls']:stop_reason='call-budget';break
            self.virtual+=timedelta(seconds=300)
            try:
                with patch('digital_life.application.autonomy.exploration.utc',side_effect=self.clock):
                    result=self.engine.process_one(self.model,self.backend)
            except Exception as error:
                self.errors.append({'type':type(error).__name__,'message':str(error)});self.trace('job_error',error_type=type(error).__name__,message=str(error))
                if isinstance(error,TrialBudget):stop_reason='model-budget';break
                # Preserve the failed trial and its observed model error. Do not select a fallback.
                stop_reason='model-or-runtime-error';break
            self.restart_if_due()
            status=self.x.status()
            pending=self.s.db.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','leased')").fetchone()[0]
            if status['remaining_activities']==0 and pending==0:break
            if result is None and pending==0 and status['remaining_activities']==0:break
        self.trace('trial_finished',reason=stop_reason)
        return {'stop_reason':stop_reason,'errors':self.errors,'real_model_calls':self.model.calls,'tool_calls':self.tool_calls,
                'observed_tokens':self.model.observed_tokens,'unknown_usage_calls':self.model.unknown_usage,'wall_seconds':time.monotonic()-self.start}
    def export(self):
        tables=['runtime_events','activities','activity_steps','thought_requests','thought_results','thought_attempts','action_attempts','action_results','activity_budget_accounts','budget_reservations','goal_items','evidence_items','memory_revisions','thought_request_inputs','action_intents','outbox']
        snapshot={name:self.s.rows(name) for name in tables};snapshot['questions']=list(self.x.questions().values());snapshot['instance_id']=self.s.instance_id
        artifacts={r['id']:self.s.read_artifact(r['id']) for r in self.s.rows('artifacts')}
        for name,value in [('snapshot.json',snapshot),('artifacts.json',artifacts),('trace.json',self.trace_events)]:
            (self.directory/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    def close(self):
        self.c.stop('g2-trial-final-stop');self.trace('stop_committed',control='trial cleanup')
        self.export();self.c.close();self.s.close()
