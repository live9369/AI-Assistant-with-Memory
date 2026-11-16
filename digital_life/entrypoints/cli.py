"""Administrative entry points: no default wake or automatic model startup."""
import argparse
import json
from pathlib import Path
import sys
from digital_life.domain.contracts import dumps,ContractError,Forbidden,identifier,RuntimeIdentity
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control

def main():
    parser=argparse.ArgumentParser(description='有记忆的 AI 助手；默认禁止唤醒')
    parser.add_argument('--data',default='work/full-system')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare'); p.add_argument('--model-config'); p.add_argument('--strict',action='store_true',help='仅为新目录初始化严格 schema4；保持禁止唤醒')
    sub.add_parser('inspect'); sub.add_parser('check')
    p=sub.add_parser('process-manager');p.add_argument('operation',choices=['enable','disable','status','checkpoint','list','rollback']);p.add_argument('--checkpoint');p.add_argument('--verify-bundle',action='store_true');p.add_argument('--start',action='store_true');p.add_argument('--monitor-seconds',type=float);p.add_argument('--verify-thought',action=argparse.BooleanOptionalAction,default=None);p.add_argument('--thought-timeout',type=int,default=180)
    p=sub.add_parser('project-access'); p.add_argument('operation',choices=['status','enable','disable']);p.add_argument('--root');p.add_argument('--auto-approve',action='store_true');p.add_argument('--exclude',nargs='*',default=[]);p.add_argument('--tools',nargs='+')
    p=sub.add_parser('serve'); p.add_argument('--port',type=int,default=8765)
    p=sub.add_parser('submit'); p.add_argument('text'); p.add_argument('--key',required=True)
    sub.add_parser('stop')
    sub.add_parser('resume')
    sub.add_parser('reconcile')
    sub.add_parser('collect-metrics')
    sub.add_parser('model-probe')
    p=sub.add_parser('exploration'); p.add_argument('operation',choices=['status','enable','disable','reopen']); p.add_argument('--max-activities',type=int,default=12); p.add_argument('--max-rounds',type=int,default=3); p.add_argument('--interval-seconds',type=int,default=300); p.add_argument('--duration-seconds',type=int); p.add_argument('--mode',choices=['legacy','continuous'],default='legacy'); p.add_argument('--direction'); p.add_argument('--sources',nargs='+'); p.add_argument('--reason')
    p=sub.add_parser('self-feedback'); p.add_argument('operation',choices=['status','enable','disable','projection','experience','reconcile-experience'])
    p=sub.add_parser('experience-measurement'); p.add_argument('operation',choices=['status','enable','disable','register','predict','reveal','evaluate','adopt','invalidate']); p.add_argument('--input'); p.add_argument('--run'); p.add_argument('--report'); p.add_argument('--reason'); p.add_argument('--config')
    p=sub.add_parser('configure-model'); p.add_argument('config'); p.add_argument('--offline',action='store_true',help='仅校验并保存配置，不请求模型清单')
    sub.add_parser('migrate-schema')
    p=sub.add_parser('serve-model'); p.add_argument('--assets',required=True); p.add_argument('--port',type=int,default=18081); p.add_argument('--logs',required=True)
    p=sub.add_parser('backup'); p.add_argument('destination')
    p=sub.add_parser('restore'); p.add_argument('source'); p.add_argument('target')
    p=sub.add_parser('import-legacy'); p.add_argument('source'); p.add_argument('target')
    p=sub.add_parser('stage-release'); p.add_argument('source')
    p=sub.add_parser('deploy'); p.add_argument('deployment'); p.add_argument('--monitor-seconds',type=float)
    # Explicit worker command exists but remains blocked by the user's persistent lock.
    p=sub.add_parser('run-one'); p.add_argument('--deployment',required=True)
    from digital_life.entrypoints.growth import parsers as growth_parsers
    growth_parsers(sub)
    args=parser.parse_args()
    try:
        if args.command=='serve-model':
            from digital_life.infrastructure.llm.model_service import ModelService
            import time
            service=ModelService(args.assets,args.logs,args.port)
            try:
                print(dumps({'configuration':service.start(),'scope':'model service only; no life instance started'}),flush=True)
                while service.process.poll() is None: time.sleep(0.25)
                return 1
            except KeyboardInterrupt: return 0
            finally: service.stop()
        elif args.command=='roadmap':
            from digital_life.application.monitoring.task_plan import inspect_plan
            from digital_life.infrastructure.persistence.sqlite_store import PROJECT
            result=inspect_plan(PROJECT)
        elif args.command=='prepare':
            cfg=json.loads(Path(args.model_config).read_text()) if args.model_config else None
            if args.strict:
                from digital_life.application.runtime.strict_initialization import prepare_new_strict
                store=prepare_new_strict(args.data,model_config=cfg)
            else:store=Store.prepare(args.data,model_config=cfg)
            control=Control(args.data,store.instance_id)
            try: result={'instance':store.instance_id,'wake_disabled':True,'control':control.state(),'inference_started':False}
            finally: control.close(); store.close()
        elif args.command in ('restore','import-legacy'):
            from digital_life.application.memory.data_management import restore_bundle,import_legacy
            result=(restore_bundle if args.command=='restore' else import_legacy)(args.source,args.target)
        elif args.command=='serve':
            from digital_life.entrypoints.http import serve
            serve(args.data,args.port); return 0
        else:
            store=Store(args.data)
            try:
                if args.command=='process-manager':
                    from digital_life.application.lifecycle.process_checkpoints import ProcessCheckpoints
                    from digital_life.infrastructure.processes.locks import exclusive
                    control=Control(store.root,store.instance_id)
                    try:
                        manager=ProcessCheckpoints(control)
                        if args.operation=='status':result=manager.status()
                        elif args.operation=='list':result={'checkpoints':manager.list()}
                        elif args.operation in ('enable','disable'):
                            with exclusive(store.root,'deployment.lock'):result=manager.configure(args.operation=='enable',store.config()['controller'],verify_thought=args.verify_thought,thought_timeout=args.thought_timeout)
                        elif args.operation=='checkpoint':
                            with exclusive(store.root,'deployment.lock'):result=manager.capture(reason='explicit-cli')
                        else:
                            if not args.checkpoint:raise ContractError('--checkpoint required')
                            if control.state()['active_process_run_id']:raise Forbidden('stop runtime before rollback')
                            point=manager.get(args.checkpoint,verify_bundle=args.verify_bundle)
                            result={'checkpoint':point['id'],'target_deployment':point['deployment'],'source_version':point['source_version'],'state_policy':'preserve-current-ledger','started':False}
                            if args.start:
                                from digital_life.application.lifecycle.deployment import Deployment
                                control.resume(identifier());result['reconciliation']=manager.reconcile_uncertain()
                                deployment=Deployment(control);result['deployment']=deployment.launch(point['deployment']);result['started']=bool(result['deployment'].get('switched'))
                                print(dumps(result),flush=True)
                                if deployment.active:result['monitor']=deployment.supervise(args.monitor_seconds)
                    finally:control.close()
                elif args.command=='project-access':
                    from digital_life.application.lifecycle.project_access import ProjectAccess
                    access=ProjectAccess(store)
                    if args.operation!='status':
                        from digital_life.entrypoints.growth import check_running_feature
                        check_running_feature(store,'project_access.py')
                    result=access.config() if args.operation=='status' else access.configure(args.root or '.',store.config()['controller'],enabled=args.operation=='enable',auto_approve=args.auto_approve,exclude=args.exclude,tools=args.tools)
                elif args.command=='inspect': result={'instance':store.instance_id,'wake_disabled':(store.root/'WAKE_DISABLED').exists(),'configuration':store.config(),'integrity':store.integrity()}
                elif args.command=='check': result=store.integrity()
                elif args.command=='collect-metrics':
                    from digital_life.application.telemetry.metrics import Metrics
                    result=Metrics(store).collect()
                elif args.command=='exploration':
                    from digital_life.application.autonomy.exploration import Exploration
                    exploration=Exploration(store)
                    if args.operation=='reopen':
                        from digital_life.application.autonomy.continuous_exploration import ContinuousExploration
                        with store.tx():result=ContinuousExploration(exploration).reopen(args.direction,args.sources,args.reason,store.config()['controller'])
                    else:result=exploration.status() if args.operation=='status' else exploration.configure(store.config()['controller'],args.operation=='enable',args.max_activities,args.max_rounds,args.interval_seconds,args.duration_seconds,args.mode)
                elif args.command=='self-feedback':
                    from digital_life.application.learning.self_feedback import SelfFeedback
                    feedback=SelfFeedback(store); actor=store.config()['controller']
                    if args.operation in ('enable','disable'):
                        from digital_life.entrypoints.growth import check_running_feature
                        check_running_feature(store,'self_feedback.py')
                        result=feedback.configure(actor,args.operation=='enable')
                    elif args.operation=='reconcile-experience':result={'experience_revision_refs':feedback.reconcile_experiences(actor),'inference_started':False}
                    else: result=feedback.shadow_interest(actor) if args.operation in ('projection','experience') else feedback.status(actor)
                elif args.command=='experience-measurement':
                    from digital_life.entrypoints.experience_measurement import handle
                    result=handle(store,args)
                elif args.command=='model-probe':
                    from digital_life.infrastructure.llm.inference import probe
                    result=probe(store.config()['model'])
                elif args.command=='configure-model':
                    from digital_life.application.runtime.configuration import configure_model
                    result=configure_model(store,json.loads(Path(args.config).read_text()),store.config()['controller'],check_available=not args.offline)
                elif args.command in ('task-loop','cognition','memory-feedback','goal-regulation','behavior-policy','personality-growth','habit-learning','people-relations','memory-quality','autonomy-agenda','maintenance'):
                    from digital_life.entrypoints.growth import handle
                    result=handle(store,args)
                elif args.command=='migrate-schema':
                    from digital_life.application.lifecycle.schema_migration import migrate
                    result=migrate(store,store.config()['controller'])
                elif args.command=='reconcile':
                    from digital_life.application.lifecycle.recovery import Recovery
                    credential=store.root/'controller.token'
                    bearer=('Bearer '+credential.read_text().strip()) if credential.is_file() and not credential.is_symlink() else None
                    result=Recovery(store).reconcile(store.config()['controller'],bearer=bearer)
                elif args.command=='backup':
                    from digital_life.application.memory.data_management import backup_bundle
                    result=backup_bundle(store,args.destination)
                elif args.command=='submit':
                    from digital_life.application.runtime.engine import Engine
                    result={'activity':Engine(store).submit(args.text,args.key),'inference_started':False}
                else:
                    control=Control(args.data,store.instance_id)
                    try:
                        if args.command=='stop': result=control.stop(identifier())
                        elif args.command=='resume': result=control.resume(identifier())
                        elif args.command=='stage-release':
                            from digital_life.application.lifecycle.control_plane import Releases
                            result={'deployment':Releases(control).stage(args.source),'activated':False}
                        elif args.command=='deploy':
                            from digital_life.application.lifecycle.deployment import Deployment
                            manager=Deployment(control); result=manager.launch(args.deployment)
                            print(dumps({'deployment_started':result.get('switched') is True,'deployment':args.deployment,'pid':result.get('pid'),'error':result.get('error')}),file=sys.stderr,flush=True)
                            if manager.active: result['monitor']=manager.supervise(args.monitor_seconds)
                        else:
                            control.assert_startable()
                            # The lock excludes another CLI Runtime; no implicit service installation.
                            from digital_life.infrastructure.processes.locks import exclusive
                            from digital_life.application.runtime.engine import Engine
                            with exclusive(args.data):
                                identity=control.begin_run(args.deployment)
                                try: result=Engine(store,identity).process_one()
                                finally: control.finish_run(identity)
                    finally: control.close()
            finally: store.close()
        print(dumps(result)); return 0
    except Exception as error:
        print(dumps({'error':type(error).__name__,'detail':str(error)}),file=sys.stderr); return 1

if __name__=='__main__': sys.exit(main())
