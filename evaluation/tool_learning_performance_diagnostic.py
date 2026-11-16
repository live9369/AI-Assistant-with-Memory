"""PF01 opt-in diagnostic; fresh synthetic fixture only, never production data.

Observers add overhead. Exclusive phase times partition observed wall time;
method inclusive times overlap and must never be added to phase totals.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import time
from unittest.mock import patch

class PhaseObserver:
    def __init__(self,clock=time.perf_counter):
        self.clock=clock;self.stack=['other'];self.last=clock();self.seconds=Counter();self.calls=Counter();self.inclusive=Counter();self.sql=Counter();self.sql_exact=Counter();self.sql_shapes=Counter();self.rows=Counter();self.bytes=Counter();self.roots=Counter();self.edges=Counter();self.metadata=Counter();self.decodes=Counter();self.copies=Counter();self.shape_cache={};self.readset=Counter();self.readset_times=Counter();self.readset_peaks=Counter();self.readset_by_phase=defaultdict(Counter)
    def tick(self):
        now=self.clock();self.seconds[self.stack[-1]]+=now-self.last;self.last=now;return now
    @contextmanager
    def phase(self,name):
        start=self.tick();self.stack.append(name);self.calls[name]+=1
        try:yield
        finally:
            end=self.tick();self.stack.pop();self.inclusive[name]+=end-start
    def trace(self,db):
        def observe(sql):
            label=(self.stack[-1],db);self.sql[label]+=1
            # Expanded query equality includes actual revision/scope parameters.
            digest=hashlib.sha256(sql.encode()).hexdigest()
            self.sql_exact[(label,digest)]+=1
            shape=self.shape_cache.get(digest)
            if shape is None:
                shape=re.sub(r"'(?:''|[^'])*'",'?',sql)
                shape=re.sub(r'\b\d+\b','?',shape)
                self.shape_cache[digest]=shape
            self.sql_shapes[(label,shape)]+=1
        return observe
    def report(self):
        self.tick()
        phases=[]
        for name in self.seconds:
            selected=[(k,v)for k,v in self.sql_exact.items()if k[0][0]==name]
            roots=[v for k,v in self.roots.items()if k[0]==name]
            phases.append({'phase':name,'exclusive_seconds':self.seconds[name],'inclusive_seconds':self.inclusive[name],'calls':self.calls[name],'sql':sum(v for k,v in self.sql.items()if k[0]==name),'distinct_exact_sql':len(selected),'repeated_exact_sql':sum(v-1 for k,v in selected),'metered_rows':self.rows[name],'metered_read_and_production_bytes':self.bytes[name],'upstream_calls':sum(roots),'distinct_full_root_contexts':len(roots),'repeated_full_root_contexts':sum(v-1 for v in roots),'returned_path_entries':self.edges[name],'metadata_calls':self.metadata[name],'json_decode_calls':self.decodes[name],'top_level_deepcopy_calls':self.copies[name]})
        return {'readset_metrics':{'counts':dict(self.readset),'method_inclusive_seconds':dict(self.readset_times),'peaks':dict(self.readset_peaks),'by_phase':{k:dict(v)for k,v in self.readset_by_phase.items()},'notes':['Method durations are inclusive and overlap phase timing; do not add them to wall time.','facts_sql_reads excludes checkpoint/control SQL and counts physical fixed-fact query entry; returned rows use original meter.','Peaks are observed encoded retention and key/blob counts; Python object overhead is not included.']},'exclusive_total_seconds':sum(self.seconds.values()),'phases':phases,'top_sql_shapes':[{'phase':k[0][0],'database':k[0][1],'sql':k[1],'calls':v}for k,v in self.sql_shapes.most_common(30)],'notes':['All phases are exclusive; inclusive method times overlap.','Exact SQL compares expanded statements, including scope/version parameters.','Meter byte observer includes row/artifact reads and produced material; not storage IO bytes.','Metadata calls are decoder/cache lookups, not necessarily actual JSON decoding.','Root identity counts source token and full scope only; they are shared-material candidates, not authorization equivalence. Purpose/recipient checks are never skipped.']}


def install_readset_observers(observer,patches):
    """Observe public phase methods without altering keys, caps or results."""
    from digital_life.infrastructure.persistence.tool_learning_readset import PhaseReadSet
    def count(name,amount=1):
        observer.readset[name]+=amount;observer.readset_by_phase[observer.stack[-1]][name]+=amount
    def peak(value):
        for name,amount in (('tracked_blobs',len(value.blobs)),('encoded_bytes',value.bytes+value.blob_bytes),('fact_keys',len(value.cache)),('graph_keys',len(value.graphs)),('all_keys',len(value.cache)+len(value.graphs))):
            observer.readset_peaks[name]=max(observer.readset_peaks[name],amount)
    def wrap(name,handler):
        original=getattr(PhaseReadSet,name)
        def observed(value,*a,**k):
            started=time.perf_counter()
            try:return handler(original,value,*a,**k)
            finally:
                observer.readset_times[name]+=time.perf_counter()-started
                peak(value)
        patches.append(patch.object(PhaseReadSet,name,observed))
    def checkpoint(original,value,include_artifacts=True):
        count('checkpoint_calls');count('checkpoint_tracked_blob_visits',len(value.blobs)if include_artifacts else 0)
        start=time.perf_counter()
        try:return original(value,include_artifacts)
        finally:observer.readset_by_phase[observer.stack[-1]]['checkpoint_inclusive_seconds']+=time.perf_counter()-start
    wrap('checkpoint',checkpoint)
    def graph(original,value,key):
        count('graph_lookups');out=original(value,key);count('graph_hits'if out is not None else 'graph_misses');return out
    wrap('graph',graph)
    def remember_graph(original,value,key,encoded,logical_rows):
        count('graph_retain_attempts')
        size=len(key.encode('utf-8'))+len(encoded.encode('utf-8'))+len(str(logical_rows))
        present=key in value.graphs
        reason=('disabled'if not value.reusable else 'already_present'if present else 'key_cap'if len(value.cache)+len(value.graphs)>=value.max_keys else 'too_large'if value.bytes+value.blob_bytes+size>value.max_bytes else None)
        out=original(value,key,encoded,logical_rows)
        count('graph_retain_'+(reason or ('retained'if key in value.graphs else 'unexpected_not_retained')))
        count('graph_encoded_attempt_bytes',size)
        return out
    wrap('remember_graph',remember_graph)
    def read(original,value,name,parameters):
        count('facts_requests');count('facts_requests:'+name)
        dirty=value.store.db.total_changes!=value.changes
        key=(name,parameters)
        hit=value.reusable and not dirty and key in value.cache
        complete=value.reusable and not dirty and name in ('consumer_dependencies','consumer_dependency_materials','source_barriers') and parameters[-1]>=0 and (name,('complete',parameters[0]))in value.cache
        count('facts_exact_hits'if hit else 'facts_complete_hits'if complete else 'facts_sql_reads')
        count(('facts_hit:'if hit or complete else 'facts_sql:')+name)
        return original(value,name,parameters)
    wrap('read',read)
    def clear(original,value,preserve_material=False):
        count('clear_preserve_material'if preserve_material else 'clear_all');return original(value,preserve_material)
    wrap('clear',clear)
    for name in ('track_artifact','track_location','evict_one'):
        def handler(original,value,*a,_name=name,**k):count(_name+'_calls');return original(value,*a,**k)
        wrap(name,handler)


def run(destination):
    import os
    os.environ['DIGITAL_LIFE_REAL_MODEL']='0'
    from tests.test_tool_learning_runtime import StrictEngineEndToEndTests
    from digital_life.application.learning.engine import StrictEngine
    from digital_life.application.learning.runtime import ToolLearningRuntime
    from digital_life.application.learning.eligibility import ToolLearningEligibility
    from digital_life.infrastructure.persistence import tool_learning_meter as meter
    from digital_life.infrastructure.llm.fresh_learning import FreshLearningProvider
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    fixture=StrictEngineEndToEndTests('test_ordinary_actual_engine_full_packet_and_real_original_account')
    result={'scope':'fresh full 8-module / 17-history synthetic fixture','observed':True,'real_models_called':False,'formal_instance_accessed':False}
    root=Path(__file__).resolve().parents[1]
    sources=lambda:{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((root/'digital_life').rglob('*.py'))}
    result['source_files_before']=sources()
    result['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (destination/'harness.py').write_text(Path(__file__).read_text())
    result['instrumentation']={'json_decode_calls':'measured','deepcopy_calls':'measured top-level calls, not unique-value copies'}
    observer=None
    try:
        fixture.setUp()
        import tempfile
        assert fixture.s.root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        observer=PhaseObserver();patches=[]
        def instrument(cls,name,label):
            old=getattr(cls,name)
            def call(*args,**kwargs):
                selected=label(*args,**kwargs)if callable(label)else label
                with observer.phase(selected):return old(*args,**kwargs)
            patches.append(patch.object(cls,name,call))
        instrument(StrictEngine,'think','lifecycle')
        instrument(StrictEngine,'prepare','assemble')
        for name in ('_primary','_recall','_conversation','_features','_contexts'):instrument(StrictEngine,name,'collect')
        instrument(StrictEngine,'_qualified_fields',lambda *a,**k:'source_check:'+str(a[5]if len(a)>5 else k.get('stage')))
        instrument(ToolLearningRuntime,'assemble','register_input')
        instrument(ToolLearningRuntime,'_qualify',lambda *a,**k:'source_check:'+str(a[5]if len(a)>5 else k.get('stage')))
        instrument(StrictEngine,'_finish','result_save')
        instrument(FreshLearningProvider,'generate_fresh','model_adapter')
        instrument(FreshLearningProvider,'_send','synthetic_transport')
        original_loads=json.loads
        def decode(*a,**k):observer.decodes[observer.stack[-1]]+=1;return original_loads(*a,**k)
        patches.append(patch.object(json,'loads',decode))
        import sys,copy
        original_copy=copy.deepcopy
        def copied(*a,**k):observer.copies[observer.stack[-1]]+=1;return original_copy(*a,**k)
        for module_name,module in list(sys.modules.items()):
            if module_name.startswith('digital_life.') and getattr(module,'deepcopy',None)is original_copy:
                patches.append(patch.object(module,'deepcopy',copied))
        install_readset_observers(observer,patches)
        old_check=ToolLearningEligibility._check
        def check(self,entry,principal,token,scope,purpose,recipient,stage,scan_budget=None):
            with observer.phase('source_check:'+stage):return old_check(self,entry,principal,token,scope,purpose,recipient,stage,scan_budget)
        patches.append(patch.object(ToolLearningEligibility,'_check',check))
        old_up=ToolLearningEligibility._upstream
        def upstream(self,token,scope,scan_budget):
            context=json.dumps([token,scope],sort_keys=True,separators=(',',':'),ensure_ascii=False)
            observer.roots[(observer.stack[-1],hashlib.sha256(context.encode()).hexdigest())]+=1
            out=old_up(self,token,scope,scan_budget);observer.edges[observer.stack[-1]]+=len(out);return out
        patches.append(patch.object(ToolLearningEligibility,'_upstream',upstream))
        old_metadata=ToolLearningEligibility._metadata
        def metadata(*a,**k):observer.metadata[observer.stack[-1]]+=1;return old_metadata(*a,**k)
        patches.append(patch.object(ToolLearningEligibility,'_metadata',metadata))
        old_charge=meter._Cursor.charge
        def charge(row):
            if row is not None and meter._ACTIVE.get()is not None:observer.rows[observer.stack[-1]]+=1
            return old_charge(row)
        patches.append(patch.object(meter._Cursor,'charge',staticmethod(charge)))
        old_consume=meter.PhysicalReadMeter.consume
        def consume(self,size,scan=0,items=0):observer.bytes[observer.stack[-1]]+=size;return old_consume(self,size,scan,items)
        patches.append(patch.object(meter.PhysicalReadMeter,'consume',consume))
        fixture.s.db.set_trace_callback(observer.trace('main'));fixture.control.db.set_trace_callback(observer.trace('control'))
        from contextlib import ExitStack
        with ExitStack() as stack:
            for entry in patches:stack.enter_context(entry)
            fixture.test_ordinary_actual_engine_full_packet_and_real_original_account()
        result.update(passed=True,diagnostic=observer.report())
    except BaseException as error:
        import traceback
        result.update(passed=False,error_type=type(error).__name__,traceback=traceback.format_exc())
        if observer:result['diagnostic']=observer.report()
    finally:
        if hasattr(fixture,'s'):fixture.s.db.set_trace_callback(None)
        if hasattr(fixture,'control'):fixture.control.db.set_trace_callback(None)
        fixture.doCleanups()
        result['source_files_after']=sources();result['source_stable']=result['source_files_before']==result['source_files_after']
        (destination/'diagnostic.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':result['passed'],'error':result.get('error_type'),'seconds':result.get('diagnostic',{}).get('exclusive_total_seconds')},ensure_ascii=False),flush=True)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    raise SystemExit(0 if run(args.output)['passed']else 1)
