"""Trace-free, opt-in SQL charge and bounded material-cache diagnostics."""
import argparse
from collections import Counter
from contextlib import contextmanager,ExitStack
from functools import wraps
import hashlib
import json
from pathlib import Path
import re
import sys
import threading
import weakref


class MaterialObserver:
    def __init__(self,stages,sample_limit=8):
        self.stages=stages;self.owner=threading.get_ident();self.sample_limit=sample_limit
        self.sql_stack=[];self.charge_depth=0;self.material_stack=[]
        self.query_catalog={};self.query_ids={};self.query_aliases={};self.stage_rows={}
        self.phases=[];self.phase_ids={};self.lookup_codes={};self.active=True;self.bounded_names=()
    def own(self):return self.active and threading.get_ident()==self.owner
    def stage(self):return self.stages.phase_stack[-1]
    def group(self):
        key=self.stage()
        value=self.stage_rows.get(key)
        if value is None:value={'sql':{},'non_sql':{},'cache':Counter()};self.stage_rows[key]=value
        return value
    def query(self,sql):
        if type(sql)is not str:return 'unknown_cursor'
        sql=re.sub(r'\n/\*tl-managed:[0-9a-f]+:[0-9]+\*/\Z','',sql)
        if sql in self.query_ids:return self.query_ids[sql]
        # Normalization is diagnostic only. Original execute sees untouched SQL.
        shape=re.sub(r'/\*\s*managed[^*]*\*/',' ',sql,flags=re.I)
        shape=' '.join(shape.split());shape=re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"",'?',shape)
        shape=re.sub(r'\b[0-9]+\b','?',shape)
        label=self.query_aliases.get(' '.join(sql.split()))
        digest=hashlib.sha256(shape.encode()).hexdigest()[:16];key=label or'sql:'+digest
        self.query_ids[sql]=key;self.query_catalog.setdefault(key,{'label':label,'sql_shape':shape[:1200]})
        return key
    def charge(self,size,scan,items):
        group=self.group();sql=self.charge_depth and bool(self.sql_stack)and not self.material_stack
        key=self.sql_stack[-1]if sql else(self.material_stack[-1]if self.material_stack else'other_material')
        target=group['sql'if sql else'non_sql'].setdefault(key,{'rows':0,'items':0,'bytes':0,'charges':0})
        target['rows']+=scan;target['items']+=items;target['bytes']+=size;target['charges']+=1
    def phase(self,phase):
        key=id(phase);prior=self.phase_ids.get(key)
        if prior is not None and prior[0]()is phase:return prior[1]
        row={'ordinal':len(self.phases),'stage_ordinal':self.stage(),'max_keys':0,'max_material_bytes':0,'max_blob_bytes':0,'max_total_bytes':0,'max_tracked_files':0,'reuse_disabled_observed':False,'namespaces':{},'events':Counter(),'samples':{},'current':{}}
        self.phases.append(row);self.phase_ids[key]=(weakref.ref(phase),row);return row
    @staticmethod
    def namespace(category,key=None):
        if category=='facts':return 'facts:'+str(key[0])
        if category=='prepared':
            tag=key[0]if key and type(key[0])is str else(key[1]if len(key)>1 and type(key[1])is str else'opaque_tag')
            return 'prepared:'+tag if tag in ('TL-DEPENDENCY-1','TL-DEPENDENCY-BINDING-1','TL-CONTROL-CONFIGURATION-1')else'prepared:other'
        return category
    def observe(self,phase,reconcile=False):
        row=self.phase(phase);keys=phase.entry_count();total=phase.bytes+phase.blob_bytes
        row['max_keys']=max(row['max_keys'],keys);row['max_material_bytes']=max(row['max_material_bytes'],phase.bytes)
        row['max_blob_bytes']=max(row['max_blob_bytes'],phase.blob_bytes);row['max_total_bytes']=max(row['max_total_bytes'],total)
        row['max_tracked_files']=max(row['max_tracked_files'],len(phase.blobs));row['reuse_disabled_observed']|=not phase.reusable
        if reconcile:
            current={}
            for category,values in (('facts',phase.fact_sizes),('prepared',phase.prepared_sizes),('graph',phase.graph_sizes),('admission',phase.admission_sizes)):
                for key,size in values.items():
                    ns=self.namespace(category,key);v=current.setdefault(ns,{'keys':0,'bytes':0});v['keys']+=1;v['bytes']+=size
            row['current']=current
        for ns,value in (row['current'].items()if reconcile else()):
            record=row['namespaces'].setdefault(ns,{'max_keys':0,'max_bytes':0})
            record['max_keys']=max(record['max_keys'],value['keys']);record['max_bytes']=max(record['max_bytes'],value['bytes'])
        return row
    def event(self,phase,name):
        self.phase(phase)['events'][name]+=1;self.group()['cache'][name]+=1
    def accepted(self,phase,category,key,size,reconcile=False):
        row=self.phase(phase);ns=self.namespace(category,key)
        if reconcile:self.observe(phase,reconcile=True)
        else:
            value=row['current'].setdefault(ns,{'keys':0,'bytes':0});value['keys']+=1;value['bytes']+=size
            peak=row['namespaces'].setdefault(ns,{'max_keys':0,'max_bytes':0});peak['max_keys']=max(peak['max_keys'],value['keys']);peak['max_bytes']=max(peak['max_bytes'],value['bytes'])
        self.event(phase,ns+':accepted');self.observe(phase)
        sample=row['samples'].setdefault(ns,{'accepted_count':0,'accepted_bytes':0,'accepted_max_bytes':0,'rejected_samples':[],'rejected_unsampled_count':0})
        sample['accepted_count']+=1;sample['accepted_bytes']+=size;sample['accepted_max_bytes']=max(sample['accepted_max_bytes'],size)
    def rejected(self,phase,category,key,reason,size_fn):
        ns=self.namespace(category,key);self.event(phase,ns+':'+reason);row=self.observe(phase)
        sample=row['samples'].setdefault(ns,{'accepted_count':0,'accepted_bytes':0,'accepted_max_bytes':0,'rejected_samples':[],'rejected_unsampled_count':0})
        if reason not in ('key_limit','byte_limit'):return
        if len(sample['rejected_samples'])>=self.sample_limit:sample['rejected_unsampled_count']+=1;return
        try:size=size_fn()
        except BaseException:sample['rejected_samples'].append({'reason':reason,'size_status':'unavailable'});return
        sample['rejected_samples'].append({'reason':reason,'requested_bytes':size,'keys_at_rejection':phase.entry_count(),'material_bytes':phase.bytes,'blob_bytes':phase.blob_bytes})
    def remember(self,category,original):
        @wraps(original)
        def wrapped(phase,key,*args,**kwargs):
            if not self.own():return original(phase,key,*args,**kwargs)
            from digital_life.infrastructure.persistence.sqlite_write_monitor import callback_active
            from digital_life.infrastructure.persistence.tool_learning_meter import logical_observer_required
            values={'facts':phase.fact_sizes,'prepared':phase.prepared_sizes,'graph':phase.graph_sizes}[category]
            existed=key in values;before_keys=phase.entry_count();before_bytes=phase.bytes
            try:result=original(phase,key,*args,**kwargs)
            except BaseException:self.event(phase,self.namespace(category,key)+':exception');raise
            if not existed and key in values:
                evicted=phase.entry_count()!=before_keys+1 or phase.bytes!=before_bytes+values[key]
                self.accepted(phase,category,key,values[key],reconcile=evicted);return result
            if existed:self.event(phase,self.namespace(category,key)+':duplicate');return result
            reason=('callback_bypass'if callback_active()else'observer_bypass'if category!='facts'and logical_observer_required()else'reuse_disabled'if not phase.reusable else'key_limit'if phase.entry_count()>=phase.max_keys else'byte_limit')
            def size():
                from digital_life.domain.contracts import dumps
                if category=='facts':
                    provided=kwargs.get('size',args[1]if len(args)>1 else None)
                    base=sum(len(dumps(dict(r)).encode())for r in args[0])if provided is None else provided
                    return base+len(dumps([key[0],list(key[1])]).encode())
                if category=='graph':return len(key.encode())+len(args[0].encode())+len(str(args[1]))
                stamped=bool(key)and key[0]is phase.stamp;sized=key[1:]if stamped else key
                return len(dumps(sized).encode())+int(stamped)+len(args[0].encode())+len(args[1].encode())
            self.rejected(phase,category,key,reason,size);return result
        return wrapped
    def report(self):
        stages=[]
        for ordinal,value in sorted(self.stage_rows.items()):
            phase=self.stages.phases[ordinal];sql=[dict(query=k,**v)for k,v in value['sql'].items()]
            stages.append({'ordinal':ordinal,'label':phase['label'],'sql_totals':{k:sum(r[k]for r in sql)for k in ('rows','items','bytes','charges')},'top_sql_by_bytes':sorted(sql,key=lambda r:-r['bytes'])[:40],'top_sql_by_rows':sorted(sql,key=lambda r:-r['rows'])[:40],'all_sql':sql,'non_sql':value['non_sql'],'cache':dict(value['cache'])})
        for phase in self.phases:
            unresolved={}
            for name in self.bounded_names:
                prefix='facts:'+name+':'
                misses=phase['events'][prefix+'miss_or_bypass']
                attempts=sum(v for k,v in phase['events'].items()if k.startswith(prefix)and k[len(prefix):]not in ('hit','miss_or_bypass'))
                if misses>attempts:unresolved[name]=misses-attempts
            phase['bounded_misses_without_completed_remember_partial_size_exception_or_callback']=unresolved
        return {'scope':'Trace-free material diagnostic; measured timing includes wrappers and is not final performance','query_catalog':self.query_catalog,'stages':stages,'phase_readsets':self.phases,'rejected_size_sample_limit_per_namespace_per_phase':self.sample_limit,'rejected_sizes_are_sampled_not_total':True,'validator_identity_replaced':False,'sqlite_trace_or_row_observer_installed':False}


@contextmanager
def material_observers(observer,material):
    from digital_life.infrastructure.persistence import tool_learning_meter as meter
    from digital_life.infrastructure.persistence import tool_learning_readset as readset
    patches=ExitStack();originals=[]
    def install(cls,name,function):
        original=getattr(cls,name);originals.append((cls,name,original));setattr(cls,name,function);return original
    material.query_aliases={' '.join(sql.split()):'fact:'+name for name,sql in readset.QUERIES.items()};material.bounded_names=readset._BOUNDED_FACT_NAMES
    execute=meter._Connection.execute
    @wraps(execute)
    def tagged(connection,*args,**kwargs):
        result=execute(connection,*args,**kwargs)
        if material.own():result._material_query=material.query(args[0])
        return result
    install(meter._Connection,'execute',tagged)
    cursor_execute=meter._Cursor.execute
    @wraps(cursor_execute)
    def cursor_tagged(cursor,*args,**kwargs):
        result=cursor_execute(cursor,*args,**kwargs)
        if material.own():cursor._material_query=material.query(args[0])
        return result
    install(meter._Cursor,'execute',cursor_tagged)
    fetch=meter._Cursor.fetchone
    @wraps(fetch)
    def fetching(cursor):
        if not material.own():return fetch(cursor)
        material.sql_stack.append(getattr(cursor,'_material_query','unknown_cursor'))
        try:return fetch(cursor)
        finally:material.sql_stack.pop()
    install(meter._Cursor,'fetchone',fetching)
    charge=meter._Cursor.charge
    def charging(row):
        if not material.own():return charge(row)
        material.charge_depth+=1
        try:return charge(row)
        finally:material.charge_depth-=1
    install(meter._Cursor,'charge',staticmethod(charging))
    consume=meter.PhysicalReadMeter.consume
    @wraps(consume)
    def consuming(account,size,scan=0,items=0):
        if not material.own():return consume(account,size,scan=scan,items=items)
        try:return consume(account,size,scan=scan,items=items)
        finally:
            if type(size)is int and size>=0 and type(scan)is int and type(items)is int:material.charge(size,scan,items)
    install(meter.PhysicalReadMeter,'consume',consuming)
    for name,label in (('artifact_after','artifact_body'),('external_read_after','external_material'),('material_produced','produced_material')):
        original=getattr(meter,name)
        def tagged_material(*args,_original=original,_label=label,**kwargs):
            if not material.own():return _original(*args,**kwargs)
            material.material_stack.append(_label)
            try:return _original(*args,**kwargs)
            finally:material.material_stack.pop()
        install(meter,name,tagged_material)
    cls=readset.PhaseReadSet
    for name,category in (('remember','facts'),('remember_graph','graph'),('remember_prepared_metadata','prepared')):install(cls,name,material.remember(category,getattr(cls,name)))
    read=cls.read;logical_code=cls._logical_rows.__code__
    @wraps(read)
    def reading(phase,name,parameters):
        result=read(phase,name,parameters)
        if material.own():
            hit=getattr(result,'gi_code',None)is logical_code
            material.event(phase,'facts:'+name+(':hit'if hit else':miss_or_bypass'))
        return result
    install(cls,'read',reading)
    for name,category in (('graph','graph'),('prepared_metadata','prepared')):
        original=getattr(cls,name)
        def lookup(phase,key,_original=original,_category=category):
            result=_original(phase,key)
            if material.own():material.event(phase,material.namespace(_category,key)+(':hit'if result is not None else':miss_or_bypass'))
            return result
        install(cls,name,lookup)
    admitted=cls.graph_admitted
    @wraps(admitted)
    def admitting(phase,key):
        existed=key in phase.admission_sizes;result=admitted(phase,key)
        if material.own():
            material.event(phase,'admission:repeat_demand'if result else'admission:first_or_denied')
            if not existed and key in phase.admission_sizes:material.accepted(phase,'admission',key,phase.admission_sizes[key])
            elif not existed and key not in phase.admission_sizes:
                from digital_life.infrastructure.persistence.sqlite_write_monitor import callback_active
                from digital_life.infrastructure.persistence.tool_learning_meter import logical_observer_required
                reason=('callback_bypass'if callback_active()else'observer_bypass'if logical_observer_required()else'reuse_disabled'if not phase.reusable else'key_limit'if phase.entry_count()>=phase.max_keys else'byte_limit')
                material.rejected(phase,'admission',key,reason,lambda:len(key.encode())+1)
        return result
    install(cls,'graph_admitted',admitting)
    for name in ('_clear_entries','_discard_input_affected','evict_one','track_location','close'):
        original=getattr(cls,name)
        def state_change(phase,*args,_original=original,_name=name,**kwargs):
            before=None
            if material.own():
                before=(phase.bytes,phase.blob_bytes,phase.entry_count(),len(phase.blobs),phase.reusable)
                if _name=='close':material.observe(phase);material.phase(phase)['before_close']={'keys':phase.entry_count(),'material_bytes':phase.bytes,'blob_bytes':phase.blob_bytes,'tracked_files':len(phase.blobs),'reusable':phase.reusable,'namespaces':dict(material.phase(phase)['current'])}
            try:return _original(phase,*args,**kwargs)
            finally:
                if material.own():
                    material.event(phase,'state:'+_name)
                    after=(phase.bytes,phase.blob_bytes,phase.entry_count(),len(phase.blobs),phase.reusable)
                    if _name!='track_location'or before!=after:material.observe(phase,reconcile=True)
        install(cls,name,state_change)
    try:yield {'installed':len(originals),'sqlite_trace_or_row_observer_installed':False,'validator_identity_replaced':False}
    finally:
        for target,name,original in reversed(originals):
            # Preserve staticmethod descriptor semantics after restoration.
            setattr(target,name,staticmethod(original)if target is meter._Cursor and name=='charge'else original)
        patches.close()


def main(argv=None):
    from evaluation import tool_learning_continuation_diagnostic as diagnostic
    parser=argparse.ArgumentParser(add_help=False,allow_abbrev=False);parser.add_argument('--material-output');parser.add_argument('--rejection-size-samples',type=int,default=8)
    known,forward=parser.parse_known_args(sys.argv[1:]if argv is None else argv)
    if not 0<=known.rejection_size_samples<=32:raise ValueError('rejection sample limit must be between 0 and32')
    locations=argparse.ArgumentParser(add_help=False,allow_abbrev=False);locations.add_argument('--output',required=True);location,_=locations.parse_known_args(forward)
    path=Path(known.material_output)if known.material_output else Path(location.output)/'material-cache-diagnostic.json'
    original=diagnostic.product_observers;holder={};error=None
    @contextmanager
    def installed(observer,counters_only=False):
        if not counters_only:raise ValueError('material diagnostic requires counters-only stages')
        material=MaterialObserver(observer,known.rejection_size_samples);holder['material']=material
        with original(observer,counters_only=True)as stages:
            with material_observers(observer,material)as details:yield dict(stages,material=details)
    diagnostic.product_observers=installed
    try:return diagnostic.main(['--counters-only',*forward])
    except BaseException as exc:error=type(exc).__name__;raise
    finally:
        diagnostic.product_observers=original
        report=holder['material'].report()if 'material'in holder else{'installation':'not reached'}
        report.update(main_error_type=error,real_models_called=False,formal_instance_accessed=False,diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x')as stream:json.dump(report,stream,indent=2);stream.write('\n')

if __name__=='__main__':raise SystemExit(main())
