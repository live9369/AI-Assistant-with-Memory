"""Bounded SIGPROF Python-stack sampling around unchanged counters-only scale."""
import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import signal
import sys
import threading
import time


class CPUSampler:
    def __init__(self,stages,interval=.02,max_stacks=8192,max_codes=4096,max_frames=256):
        self.stages=stages;self.interval=interval;self.max_stacks=max_stacks;self.max_codes=max_codes;self.max_frames=max_frames
        self.stacks=Counter();self.codes={};self.code_ids={};self.losses=Counter();self.samples=0;self.max_depth=0
        self.active=False;self.handling=False;self.installed=False;self.reason=None;self.started_wall=None;self.started_cpu=None
    def handler(self,signum,frame):
        if not self.active:return
        if self.handling:self.losses['reentrant']+=1;return
        self.handling=True
        try:
            stack=[];current=frame
            while current is not None:
                if len(stack)>=self.max_frames:self.losses['overlong_stack']+=1;return
                code=current.f_code;identity=id(code);index=self.code_ids.get(identity)
                if index is None:
                    if len(self.codes)>=self.max_codes:index=0;self.losses['code_catalog_limit_frames']+=1
                    else:
                        index=len(self.codes)+1;self.code_ids[identity]=index
                        # Hold code object so id cannot be recycled during run.
                        self.codes[index]=(code,code.co_filename,code.co_name,code.co_firstlineno)
                stack.append((index,current.f_lineno));current=current.f_back
            self.max_depth=max(self.max_depth,len(stack));ordinal=self.stages.phase_stack[-1]
            key=(ordinal,tuple(stack))
            if key not in self.stacks and len(self.stacks)>=self.max_stacks:self.losses['distinct_stack_limit']+=1;return
            self.stacks[key]+=1;self.samples+=1
            if not stack:self.losses['empty_frame']+=1
        except Exception:self.losses['handler_error']+=1
        finally:self.handling=False
    def install(self):
        required=('SIGPROF','ITIMER_PROF','getitimer','setitimer','pthread_sigmask','sigpending','sigwait')
        if not all(hasattr(signal,name)for name in required):self.reason='required POSIX signal interfaces unavailable';return False
        if threading.current_thread()is not threading.main_thread():self.reason='not main thread';return False
        self.old_handler=signal.getsignal(signal.SIGPROF);self.old_timer=signal.getitimer(signal.ITIMER_PROF)
        if self.old_handler is not signal.SIG_DFL and self.old_handler is not signal.SIG_IGN:self.reason='existing nonstandard SIGPROF handler';return False
        if self.old_timer!=(0.,0.):self.reason='existing active ITIMER_PROF';return False
        self.old_mask=signal.pthread_sigmask(signal.SIG_BLOCK,())
        if signal.SIGPROF in self.old_mask:self.reason='SIGPROF already blocked';return False
        self.started_wall=time.monotonic();self.started_cpu=time.process_time();self.active=True
        try:
            signal.signal(signal.SIGPROF,self.handler);signal.setitimer(signal.ITIMER_PROF,self.interval,self.interval)
        except BaseException:
            self.active=False;signal.setitimer(signal.ITIMER_PROF,0.);signal.signal(signal.SIGPROF,self.old_handler);raise
        self.installed=True;return True
    def close(self):
        if not self.installed or not self.active:return
        self.active=False
        # Keep our inactive handler while draining timer signals; never restore
        # SIG_DFL with our own timer signal still pending in the kernel.
        previous_mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGPROF})
        try:
            signal.setitimer(signal.ITIMER_PROF,0.)
            while signal.SIGPROF in signal.sigpending():signal.sigwait({signal.SIGPROF})
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous_mask)
        # Returning to Python with our handler still present processes any
        # already-tripped interpreter signal before default behavior is restored.
        signal.getsignal(signal.SIGPROF)
        signal.signal(signal.SIGPROF,self.old_handler)
        signal.setitimer(signal.ITIMER_PROF,*self.old_timer)
        self.wall_seconds=time.monotonic()-self.started_wall;self.cpu_seconds=time.process_time()-self.started_cpu
    @contextmanager
    def running(self):
        if not self.install():raise RuntimeError('CPU sampling unavailable: '+str(self.reason))
        try:yield self
        finally:self.close()
    def report(self):
        code_catalog={str(index):{'file':row[1],'function':row[2],'first_line':row[3]}for index,row in self.codes.items()}
        if self.losses['code_catalog_limit_frames']:code_catalog['0']={'file':'unknown','function':'code_catalog_limit','first_line':0}
        stages={}
        for(ordinal,stack),count in self.stacks.items():
            row=stages.setdefault(ordinal,{'ordinal':ordinal,'label':self.stages.phases[ordinal]['label'],'samples':0,'stacks':[],'leaf_counts':Counter(),'inclusive_counts':Counter()})
            row['samples']+=count;row['stacks'].append({'frames':[list(v)for v in stack],'count':count})
            if stack:row['leaf_counts'][str(stack[0][0])+':'+str(stack[0][1])]+=count
            for index,line in set(stack):row['inclusive_counts'][str(index)+':'+str(line)]+=count
        public=[]
        for ordinal,row in sorted(stages.items()):
            row['stacks'].sort(key=lambda value:-value['count']);row['leaf_counts']=dict(row['leaf_counts']);row['inclusive_counts']=dict(row['inclusive_counts']);public.append(row)
        return {'installed':self.installed,'reason':self.reason,'interval_cpu_seconds':self.interval,'samples':self.samples,'max_observed_stack_depth':self.max_depth,'unique_stack_count':len(self.stacks),'limits':{'stacks':self.max_stacks,'codes':self.max_codes,'frames':self.max_frames},'losses':dict(self.losses),'wall_seconds':getattr(self,'wall_seconds',None),'parent_process_cpu_seconds':getattr(self,'cpu_seconds',None),'code_catalog':code_catalog,'stages':public,'notes':['Approximate Python-stack CPU samples; not exact exclusive times.','ITIMER_PROF is process user+system CPU; Python handler runs main thread. Other-thread CPU and delayed/coalesced signals can bias attribution.','Native C internals are not visible; samples attach to the nearest Python frame.','Inclusive ancestor counts overlap; do not sum or claim count*interval is exact CPU time.','Sampling overhead is included in original budgets; this is not final performance timing.'],'sqlite_trace_or_row_observer_installed':False,'validator_identity_replaced':False}


def main(argv=None):
    from evaluation import tool_learning_continuation_diagnostic as diagnostic
    parser=argparse.ArgumentParser(add_help=False,allow_abbrev=False);parser.add_argument('--sampling-output')
    known,forward=parser.parse_known_args(sys.argv[1:]if argv is None else argv)
    locations=argparse.ArgumentParser(add_help=False,allow_abbrev=False);locations.add_argument('--output',required=True);location,_=locations.parse_known_args(forward)
    path=Path(known.sampling_output)if known.sampling_output else Path(location.output)/'statistical-cpu-samples.json'
    original=diagnostic.product_observers;holder={};error=None
    @contextmanager
    def installed(observer,counters_only=False):
        if not counters_only:raise ValueError('CPU sampling requires counters-only stages')
        sampler=CPUSampler(observer);holder['sampler']=sampler
        with original(observer,counters_only=True)as stages:
            with sampler.running():yield dict(stages,statistical_cpu_sampling=True)
    diagnostic.product_observers=installed
    try:return diagnostic.main(['--counters-only',*forward])
    except BaseException as exc:error=type(exc).__name__;raise
    finally:
        diagnostic.product_observers=original
        sampler=holder.get('sampler')
        if sampler is not None:sampler.close()
        report=sampler.report()if sampler is not None else{'installed':False,'reason':'deferred installation not reached'}
        report.update(main_error_type=error,real_models_called=False,formal_instance_accessed=False,diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x')as stream:json.dump(report,stream,indent=2);stream.write('\n')

if __name__=='__main__':raise SystemExit(main())
