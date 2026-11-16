"""Version-selected Runtime process. Only explicit deployment launches this code."""
import argparse
import json
import os
from pathlib import Path
import signal
import time
import threading
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.runtime.engine import Engine
from digital_life.domain.contracts import dumps,ContractError
from digital_life.infrastructure.llm.inference import configured_reasoner,probe

def main():
    parser=argparse.ArgumentParser()
    for name in ('data','deployment','ready','gate'): parser.add_argument('--'+name,required=True)
    args=parser.parse_args(); root=Path(args.data).resolve()
    ready=Path(args.ready); gate=Path(args.gate)
    stopped=False
    heartbeat_stop=threading.Event();heartbeat_thread=None
    work_until=[0.]
    def stop(*_):
        nonlocal stopped
        stopped=True
        heartbeat_stop.set()
        if os.environ.get('DIGITAL_LIFE_CALL_DIAGNOSTICS')=='1':
            import traceback
            frame=_[1] if len(_)>1 else None
            output=ready.parent/'interrupted-stack.json'
            output.write_text(dumps({'signal':_[0] if _ else None,'frames':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_stack(frame)]}))
            os.chmod(output,0o600)
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    acceptance={'state':'not-required'}
    capability=None;ordinary_ready=False;control_usage={'known_scan':0,'known_bytes':0,'known_elapsed_ms':0,'unknown_checks':0}
    def publish(state):
        temporary=ready.with_suffix('.tmp')
        temporary.write_text(dumps({'state':state,'deployment':args.deployment,'schema_compatible':capability is not None,'capability':capability,'model_readiness':'unverified' if capability and capability['qualified_plane_required'] else 'independent-thought-verified' if acceptance.get('state')=='passed' else 'inventory-probed','model_access_verified':acceptance.get('state')=='passed','inference_ready':'verified' if acceptance.get('state')=='passed' else 'unknown','deployment_acceptance':acceptance,'ordinary_activity_ready':ordinary_ready,'control_usage':control_usage,'pid':os.getpid()}))
        os.replace(temporary,ready)
    store=Store(root); control=Control(root,store.instance_id); identity=None
    try:
        control.assert_startable()
        version=store.db.execute('PRAGMA user_version').fetchone()[0]
        release=control.db.execute('SELECT * FROM deployments WHERE id=?',(args.deployment,)).fetchone()
        if not release or version not in (2,3,4) or not release['schema_min']<=version<=release['schema_max']:
            raise ContractError('runtime schema compatibility check failed')
        from digital_life.application.learning.bridge import loaded_runtime
        capability=loaded_runtime(control,store,args.deployment,__file__)
        integrity=store.integrity()
        if integrity['integrity']!='ok' or integrity['foreign_keys']: raise ContractError('runtime storage not ready')
        if not capability['qualified_plane_required']:
            info=(root/'runtime.sqlite').stat()
            store._startup_integrity={'file_identity':(info.st_dev,info.st_ino),'schema_version':store.db.execute('PRAGMA schema_version').fetchone()[0],'configuration_id':store.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(store.instance_id,)).fetchone()[0]}
        # Availability probe performs no inference and never starts a model service.
        reasoner=None
        if not capability['qualified_plane_required']:
            reasoner=configured_reasoner(store.config()['model'])
            probe(store.config()['model'])
        # schema4 readiness proves the control/storage/source-gate plane only.
        # Provider capability and quota remain unverified until the actual
        # strict request route, with its original budget and source manifest.
        publish('prepared')
        deadline=time.monotonic()+60
        while not gate.exists():
            if stopped or time.monotonic()>deadline: return 1
            control.assert_startable(); time.sleep(0.05)
        if gate.read_text()!=args.deployment: raise ContractError('activation gate mismatch')
        current_capability=loaded_runtime(control,store,args.deployment,__file__)
        if current_capability!=capability:raise ContractError('loaded runtime capability changed before activation')
        from digital_life.infrastructure.processes.locks import exclusive
        with exclusive(root):
            identity=control.begin_run(args.deployment)
            if os.environ.get('DIGITAL_LIFE_CALL_DIAGNOSTICS')=='1':
                from digital_life.entrypoints.call_diagnostics import install
                install(ready.parent)
            engine=Engine(store,identity); publish('running')
            from digital_life.application.telemetry.metrics import Metrics
            last_metrics=time.monotonic()-300
            # A monotonic clock has an arbitrary origin (which may be near
            # zero). Make the first idle maintenance check due immediately.
            last_maintenance=time.monotonic()-60
            def heartbeat():
                # Process liveness is independent of a long, budgeted thought.
                # Stop refreshing if the main loop makes no progress for the
                # existing maximum activity window; never extend job budgets.
                while not heartbeat_stop.wait(1):
                    if not stopped and time.monotonic()<work_until[0]:
                        try:os.utime(ready,None)
                        except FileNotFoundError:return
            heartbeat_thread=threading.Thread(target=heartbeat,name='runtime-heartbeat',daemon=True)
            heartbeat_thread.start()
            from digital_life.application.lifecycle.process_checkpoints import ProcessCheckpoints
            acceptance_config=ProcessCheckpoints(control).config()
            if acceptance_config.get('enabled') and acceptance_config.get('verify_thought'):
                challenge=json.loads((ready.parent/'probe-challenge.json').read_text())
                if challenge.get('deployment')!=args.deployment:raise ContractError('deployment challenge identity mismatch')
                if challenge.get('mode')=='skip-rollback':
                    acceptance={'state':'skipped-known-good-rollback','reason':'previously admitted deployment; no repeat inference'}
                    publish('running')
                else:
                    if capability['qualified_plane_required']:raise ContractError('qualified deployment thought adapter is not installed')
                    acceptance={'state':'pending','nonce':challenge['nonce']};publish('running');work_until[0]=time.monotonic()+acceptance_config.get('thought_timeout',180)
                    try:
                        from digital_life.application.lifecycle.deployment_thought import run as verify_thought
                        acceptance=verify_thought(engine,reasoner,args.deployment,challenge['nonce'])
                        publish('running')
                    except Exception as error:
                        acceptance={'state':'failed','nonce':challenge['nonce'],'error':type(error).__name__,'detail':str(error)[:300]};publish('running');return 1
                    admission=ready.parent/'admitted';deadline=time.monotonic()+acceptance_config.get('thought_timeout',180)
                    while not admission.exists():
                        if stopped or time.monotonic()>deadline:return 1
                        control.assert_startable();time.sleep(.05)
                    if admission.read_text()!=args.deployment:raise ContractError('deployment admission identity mismatch')
            while not stopped:
                control.assert_startable()
                ordinary_ready=True
                if capability['qualified_plane_required']:
                    from digital_life.application.learning.engine import active_profile
                    from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
                    from digital_life.domain.contracts import utc
                    # A bounded control-plane check, not an activity budget or
                    # permission to read a job body. Missing original caps idle
                    # honestly rather than repeatedly fabricating failed work.
                    meter=PhysicalReadMeter({'input_tokens':0,'output_tokens':0,'attempts':0,'tool_calls':0,'scan':1024,'items':1024,'bytes':1048576,'elapsed_ms':1000},utc(1))
                    try:
                        with meter.installed(store):active_profile(store)
                    except ContractError:ordinary_ready=False
                    finally:
                        measured=meter.usage()
                        if measured is None:control_usage['unknown_checks']+=1;ordinary_ready=False
                        else:
                            for source,target in (('scan','known_scan'),('bytes','known_bytes'),('elapsed_ms','known_elapsed_ms')):control_usage[target]+=measured[source]
                if ordinary_ready:control.transfer_inbound(store)
                work_until[0]=time.monotonic()+600
                try: result=engine.process_one(reasoner=reasoner) if ordinary_ready else None
                except Exception as error:
                    payload={'error':type(error).__name__}
                    if not capability['qualified_plane_required']:payload['detail']=str(error)[:1024]
                    with store.tx(): store.event('runtime.job_failed',payload=payload,lane='control')
                    result=None
                from digital_life.application.learning.runtime import qualified_plane_required
                if not qualified_plane_required(store) and not result and time.monotonic()-last_maintenance>=60:
                    pending=store.db.execute("SELECT 1 FROM jobs WHERE instance_id=? AND state IN ('queued','leased') LIMIT 1",(store.instance_id,)).fetchone()
                    if not pending:
                        from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
                        SelfMaintenance(store).tick();last_maintenance=time.monotonic()
                if not qualified_plane_required(store) and not result and time.monotonic()-last_metrics>=300:
                    pending=store.db.execute("SELECT 1 FROM jobs WHERE instance_id=? AND state IN ('queued','leased') LIMIT 1",(store.instance_id,)).fetchone()
                    if not pending:
                        from digital_life.application.lifecycle.health_monitor import HealthMonitor
                        HealthMonitor(store).scan()
                        Metrics(store).collect();last_metrics=time.monotonic()
                publish('running')
                if not result: time.sleep(0.25)
        return 0
    finally:
        heartbeat_stop.set()
        if heartbeat_thread:heartbeat_thread.join(timeout=2)
        if identity: control.finish_run(identity)
        control.close(); store.close()

if __name__=='__main__': raise SystemExit(main())
