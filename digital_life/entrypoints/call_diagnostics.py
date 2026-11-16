"""Opt-in local stage timings; never records arguments or model bodies."""
import functools
import json
import os
import time

def install(directory):
    from digital_life.application.learning.engine import StrictEngine
    output=directory/'stages.jsonl'
    def record(value):
        fd=os.open(output,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
        with os.fdopen(fd,'w') as handle:handle.write(json.dumps(value,separators=(',',':'))+'\n')
    targets=[(StrictEngine,name) for name in ('process_one','prepare','_primary','_recall','_conversation','_features','_contexts','_qualified_fields','think','_finish')]
    from digital_life.application.behavior.goal_regulation import GoalRegulation
    from digital_life.application.telemetry.states import StateCollector
    from digital_life.application.services.states import States
    targets += [(GoalRegulation,'refresh'),(GoalRegulation,'assess'),(StateCollector,'collect'),(States,'snapshot')]
    for owner,name in targets:
        original=getattr(owner,name)
        def make(function,label):
            @functools.wraps(function)
            def timed(*args,**kwargs):
                start=time.monotonic();record({'stage':label,'state':'start','wall_time':time.time()})
                try:return function(*args,**kwargs)
                except BaseException as error:
                    import traceback
                    record({'stage':label,'state':'error','type':type(error).__name__,'message':str(error)[:512],'elapsed_seconds':time.monotonic()-start,'frames':[{'file':os.path.basename(f.filename),'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)]})
                    raise
                finally:
                    value={'stage':label,'state':'end','elapsed_seconds':time.monotonic()-start}
                    if label=='StrictEngine.prepare':
                        store=args[0].s
                        value['graph_material']=dict(store._graph_material_stats)
                        value['file_signatures']=dict(store._file_signature_stats)
                        value['input_certificates']=dict(store._input_certificate_stats)
                    record(value)
            return timed
        setattr(owner,name,make(original,owner.__name__+'.'+name))
