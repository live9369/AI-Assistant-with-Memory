"""Opt-in exclusive parent-process profile around the unchanged scale replay.

No SQLite tracing/hooks, raw argument recording, real model or existing instance.
Observed timing has profiler overhead and is not a final performance sample.
"""
import argparse
import builtins
from contextlib import contextmanager,ExitStack
from functools import wraps
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time

STAGES=frozenset(('primary','conversation-discovery','features','prepared-read','assembly',
    'provider-preflight','actual-entry-and-retention','actual-tool-feedback',
    'calculated-contexts','calculation-live-bindings'))
CERTIFICATE_KEYS=('attempted','issued','accepted','fallback','committed')
OPTIONAL_CERTIFICATE_KEYS=('strong_material_accepted','strong_material_committed')
FILE_SIGNATURE_KEYS=('minted','hits')
GRAPH_MATERIAL_KEYS=('eligible','stored','returned','used')


def certificate_snapshot(store):
    value=getattr(store,'_input_certificate_stats',None)
    if not isinstance(value,dict)or any(type(value.get(k))is not int for k in CERTIFICATE_KEYS):
        return {'status':'unknown','reason':'expected Python certificate counters unavailable'}
    counts={k:value[k]for k in CERTIFICATE_KEYS}
    counts.update({k:value[k]for k in OPTIONAL_CERTIFICATE_KEYS if type(value.get(k))is int})
    return {'status':'observed','counts':counts}


def file_signature_snapshot(store):
    value=getattr(store,'_file_signature_stats',None)
    if not isinstance(value,dict):return None
    observed={key:value[key]for key in FILE_SIGNATURE_KEYS if type(value.get(key))is int}
    return observed or None


def graph_material_snapshot(store):
    value=getattr(store,'_graph_material_stats',None)
    if not isinstance(value,dict):return None
    observed={key:value[key]for key in GRAPH_MATERIAL_KEYS if type(value.get(key))is int}
    return observed or None


class ExclusiveObserver:
    def __init__(self,clock=time.perf_counter,cpu_clock=time.process_time):
        self.clock=clock;self.cpu_clock=cpu_clock;self.started=clock();self.last=self.started
        self.cpu_started=cpu_clock();self.owner_thread=threading.get_ident();self.active=True
        self.methods=[];self.phase_stack=[0]
        self.phases=[{'ordinal':0,'label':'outside','exclusive_seconds':0.,'inclusive_seconds':0.,'methods':{},'child_cpu_seconds':0.}]
    def tick(self):
        now=self.clock();phase=self.phases[self.phase_stack[-1]];label=self.methods[-1]if self.methods else 'unattributed'
        row=phase['methods'].setdefault(label,{'calls':0,'exclusive_seconds':0.,'inclusive_seconds':0.})
        delta=now-self.last;row['exclusive_seconds']+=delta;phase['exclusive_seconds']+=delta;self.last=now
        return now
    def wrap(self,label,original):
        @wraps(original)
        def measured(*args,**kwargs):
            if not self.active or threading.get_ident()!=self.owner_thread:return original(*args,**kwargs)
            began=self.tick();phase=self.phases[self.phase_stack[-1]]
            row=phase['methods'].setdefault(label,{'calls':0,'exclusive_seconds':0.,'inclusive_seconds':0.});row['calls']+=1
            self.methods.append(label)
            try:return original(*args,**kwargs)
            finally:
                end=self.tick();self.methods.pop();row['inclusive_seconds']+=end-began
        return measured
    @contextmanager
    def phase(self,label,store):
        label=label if type(label)is str and label in STAGES else 'other_read_operation'
        began=self.tick();cpu=self.cpu_clock();parent=self.phases[self.phase_stack[-1]]
        row={'ordinal':len(self.phases),'label':label,'exclusive_seconds':0.,'inclusive_seconds':0.,'methods':{},'child_cpu_seconds':0.,'certificate_before':certificate_snapshot(store)}
        file_before=file_signature_snapshot(store)
        if file_before is not None:row['file_signature_stats']={'before':file_before}
        graph_before=graph_material_snapshot(store)
        if graph_before is not None:row['graph_material_stats']={'before':graph_before}
        self.phases.append(row);self.phase_stack.append(row['ordinal'])
        try:yield
        finally:
            row['certificate_after']=certificate_snapshot(store)
            if row['certificate_before']['status']==row['certificate_after']['status']=='observed':
                before=row['certificate_before']['counts'];after=row['certificate_after']['counts']
                row['certificate_delta']={k:after[k]-before[k]for k in CERTIFICATE_KEYS+OPTIONAL_CERTIFICATE_KEYS if k in before and k in after}
            file_after=file_signature_snapshot(store)
            if file_after is not None:row.setdefault('file_signature_stats',{})['after']=file_after
            if file_before is not None and file_after is not None:
                delta={key:file_after[key]-file_before[key]for key in FILE_SIGNATURE_KEYS if key in file_before and key in file_after}
                if delta:row['file_signature_stats']['delta']=delta
            graph_after=graph_material_snapshot(store)
            if graph_after is not None:row.setdefault('graph_material_stats',{})['after']=graph_after
            if graph_before is not None and graph_after is not None:
                delta={key:graph_after[key]-graph_before[key]for key in GRAPH_MATERIAL_KEYS if key in graph_before and key in graph_after}
                if delta:row['graph_material_stats']['delta']=delta
            end=self.tick();self.phase_stack.pop();cpu_elapsed=self.cpu_clock()-cpu
            row['inclusive_seconds']=end-began;row['parent_cpu_inclusive_seconds']=cpu_elapsed
            row['parent_cpu_exclusive_seconds']=cpu_elapsed-row['child_cpu_seconds'];parent['child_cpu_seconds']+=cpu_elapsed
    def wrap_read_operation(self,original):
        @wraps(original)
        def measured(engine,*args,**kwargs):
            original_context=original(engine,*args,**kwargs)
            label=kwargs.get('key',args[3]if len(args)>3 else None)
            @contextmanager
            def entered():
                with self.phase(label,engine.s):
                    with original_context as value:yield value
            return entered()
        return measured
    def close(self):
        if not self.active:return
        end=self.tick();cpu=self.cpu_clock()-self.cpu_started;outside=self.phases[0]
        outside['inclusive_seconds']=end-self.started;outside['parent_cpu_inclusive_seconds']=cpu
        outside['parent_cpu_exclusive_seconds']=cpu-outside['child_cpu_seconds'];self.active=False
    def report(self):
        if self.active:self.close()
        phases=[];totals={}
        for row in self.phases:
            public={k:v for k,v in row.items()if k not in ('methods','child_cpu_seconds')}
            public['methods']=[dict(label=k,**v)for k,v in sorted(row['methods'].items(),key=lambda kv:-kv[1]['exclusive_seconds'])]
            phases.append(public)
            for label,value in row['methods'].items():
                target=totals.setdefault(label,{'calls':0,'exclusive_seconds':0.,'inclusive_seconds':0.})
                for key in target:target[key]+=value[key]
        return {'wall_seconds':self.last-self.started,'exclusive_seconds_sum':sum(r['exclusive_seconds']for r in self.phases),'phases':phases,'method_totals':[dict(label=k,**v)for k,v in sorted(totals.items(),key=lambda kv:-kv[1]['exclusive_seconds'])],'notes':['Exclusive method times plus unattributed partition observed parent wall; inclusive values overlap and must not be added.','Phase CPU is parent process only; provider child CPU is excluded.','Python profiling overhead can itself affect original stage deadlines. This is not a final timing sample.','Only fixed technical labels/counters are retained; no SQL, arguments, source text or business identifiers are recorded.']}


@contextmanager
def product_observers(observer,counters_only=False):
    # Called only after original scale fixes its world and imports its fixture.
    from digital_life.application.learning.engine import StrictEngine
    from digital_life.application.learning.runtime_owners import LocalRuntimeOwners,LocalEligibility
    from digital_life.application.learning.eligibility import ToolLearningEligibility
    from digital_life.infrastructure.persistence.tool_learning_readset import PhaseReadSet
    from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
    from digital_life.infrastructure.persistence.sqlite_write_monitor import ManagedConnection
    targets=((LocalRuntimeOwners,('check','control','configuration','principal','source_access')),
             (LocalEligibility,('_already',)),(ToolLearningEligibility,('_metadata','_upstream','_check')),
             (PhaseReadSet,('checkpoint','_probe','_sync_monitor')),
             (ToolLearningStore,('validate_ref','read_artifact')),
             (ManagedConnection,('_run','_authorize','_refresh_registry')))
    originals=[];installed=[];missing=[]
    try:
        for cls,names in (()if counters_only else targets):
            for name in names:
                label=cls.__name__+'.'+name;original=getattr(cls,name,None)
                if not callable(original):missing.append(label);continue
                originals.append((cls,name,original));setattr(cls,name,observer.wrap(label,original));installed.append(label)
        original=StrictEngine._read_operation;originals.append((StrictEngine,'_read_operation',original))
        StrictEngine._read_operation=observer.wrap_read_operation(original);installed.append('StrictEngine._read_operation')
        yield {'installed':installed,'missing':missing,'sqlite_trace_or_hook_installed':False,'mode':'counters-only'if counters_only else 'exclusive-methods'}
    finally:
        for cls,name,original in reversed(originals):setattr(cls,name,original)


@contextmanager
def deferred_install(install):
    """Do not pre-import products before original scale's frozen world setup."""
    original=builtins.__import__;state={'installed':False}
    def imported(name,globals=None,locals=None,fromlist=(),level=0):
        value=original(name,globals,locals,fromlist,level)
        if name=='tests.test_tool_learning_runtime'and 'StrictEngineEndToEndTests'in (fromlist or())and not state['installed']:
            builtins.__import__=original;state['installed']=True;install()
        return value
    builtins.__import__=imported
    try:yield state
    finally:
        if builtins.__import__ is imported:builtins.__import__=original


def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False,allow_abbrev=False)
    parser.add_argument('--diagnostic-output');parser.add_argument('--counters-only',action='store_true')
    known,forward=parser.parse_known_args(sys.argv[1:]if argv is None else argv)
    locations=argparse.ArgumentParser(add_help=False,allow_abbrev=False)
    locations.add_argument('--source',required=True);locations.add_argument('--output',required=True)
    location,_=locations.parse_known_args(forward)
    report_path=Path(known.diagnostic_output)if known.diagnostic_output else Path(location.output)/'continuation-diagnostic.json'
    scale_path=Path(__file__).with_name('tool_learning_round2_scale.py')
    spec=importlib.util.spec_from_file_location('_unchanged_continuation_scale',scale_path);scale=importlib.util.module_from_spec(spec);spec.loader.exec_module(scale)
    observer=ExclusiveObserver();patches=ExitStack();installation={};state={};code=None;error_type=None;original_argv=sys.argv
    try:
        def install():installation.update(patches.enter_context(product_observers(observer,counters_only=known.counters_only)))
        with deferred_install(install)as state:
            sys.argv=[str(scale_path),*forward];code=scale.main()
        return code
    except BaseException as exc:
        error_type=type(exc).__name__;raise
    finally:
        sys.argv=original_argv;observer.close();patches.close()
        report=observer.report();report.update(scope='Profile around original scale.main; original result.json remains the business result',measurement_mode='counters-only'if known.counters_only else 'exclusive-methods',scale_main_return=code,scale_main_error_type=error_type,installation=installation,deferred_installation=state,scale_sha256=hashlib.sha256(scale_path.read_bytes()).hexdigest(),diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),formal_instance_accessed=False,real_models_called=False)
        try:
            report_path.parent.mkdir(parents=True,exist_ok=True)
            with report_path.open('x')as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
        except BaseException:
            if error_type is None:raise


if __name__=='__main__':raise SystemExit(main())
