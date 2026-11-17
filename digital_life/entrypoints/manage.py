"""Human-facing CLI orchestration. Nothing starts without an explicit command."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from digital_life.domain.contracts import ContractError

PROJECT=Path(__file__).resolve().parents[2]
DEFAULT_DATA=PROJECT/'work/primordial00-first-wake'

def codex_path():
    found=shutil.which('codex')
    bundled=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
    if found:return found
    if bundled.is_file():return str(bundled)
    raise ValueError('未找到Codex程序，请先安装官方CLI。')

def run(data,*arguments,capture=False):
    command=[sys.executable,'-m','digital_life','--data',str(data),*map(str,arguments)]
    result=subprocess.run(command,cwd=str(PROJECT),stdout=subprocess.PIPE if capture else None,stderr=None if arguments and arguments[0]=='deploy' else subprocess.PIPE if capture else None,text=True)
    if result.returncode:
        if capture:print((result.stderr or '').strip() or '操作未完成。',file=sys.stderr)
        raise ValueError('操作失败，后续步骤未执行。')
    return json.loads(result.stdout) if capture else None

def setup_codex(path,model):
    path=Path(path).resolve()
    if path.exists():raise ValueError('配置文件已存在，未覆盖。请编辑现有文件或另选路径。')
    config={'backend':'codex_cli','enabled':True,'model':model,'executable':codex_path(),'timeout':120,'max_input_bytes':262144,'budget_mode':'post_usage'}
    from digital_life.application.runtime.configuration import validate_model_config
    validate_model_config(config);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:stream.write(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    print('已生成配置：'+str(path)+'\n未创建实例、未登录、未推理。')

def wake(data,confirmation=None):
    data=Path(data).resolve()
    if not (data/'runtime.sqlite').is_file():raise ValueError('实例不存在，请先准备实例。')
    # A read-only inspection rejects legacy/incompatible instances before changing locks.
    run(data,'inspect',capture=True)
    from digital_life.application.lifecycle.release_inspection import release_status
    version=release_status(data,PROJECT)
    if version.get('process_run_id'):raise ValueError('仍有运行进程，请先stop并等待退出，再部署新版本。')
    expected='WAKE '+data.name
    print('目标实例：'+str(data)+'\n这将解除禁止唤醒锁、允许运行并部署当前代码。无任务时等待，有待办时会开始处理。')
    if confirmation is None:
        if not sys.stdin.isatty():raise ValueError('非交互唤醒必须用 --confirm 提供明确确认短语：'+expected)
        confirmation=input('确认请输入 '+expected+'：').strip()
    if confirmation!=expected:raise ValueError('确认不匹配，未唤醒。')
    run(data,'check',capture=True)
    run(data,'model-probe',capture=True)
    result=run(data,'stage-release',PROJECT,capture=True)
    deployment=result['deployment']
    lock=data/'WAKE_DISABLED'
    if lock.is_symlink():raise ValueError('唤醒锁路径异常。')
    if lock.exists():lock.unlink()
    try:
        run(data,'resume',capture=True)
        print('正在启动版本 '+deployment+'；请保持此终端打开。Ctrl+C 停止。',flush=True)
        outcome=run(data,'deploy',deployment,capture=True)
        print(json.dumps(outcome,ensure_ascii=False,indent=2))
        if outcome.get('switched') is not True:raise ValueError('部署未成功，已恢复禁止唤醒状态。')
    except BaseException:
        # Best effort persistent stop; never auto-resume after a failed launch.
        try:run(data,'stop',capture=True)
        except Exception:pass
        if not lock.exists():lock.write_text('wake interrupted or failed; explicit wake required\n')
        raise

def menu(data):
    choices={'1':'status','2':'prepare','3':'check','4':'configure','5':'submit','6':'stage','7':'wake','8':'stop','9':'panel','10':'setup-codex','11':'login-status','12':'login','13':'lock','14':'exploration-status'}
    while True:
        print('\n实例：'+str(data)+'\n1 状态  2 准备实例  3 检查与模型探针  4 保存模型配置\n5 输入任务  6 准备版本（不启动）  7 唤醒并运行\n8 停止  9 管理面板  10 生成Codex配置\n11 Codex登录状态  12 设备码登录  13 停止并加锁  14 自主探索状态\n0 退出')
        selection=input('选择：').strip()
        if selection=='0':return 0
        operation=choices.get(selection)
        if not operation:print('请输入菜单编号。');continue
        args=['--data',str(data),operation]
        if operation in ('prepare','configure'):
            path=input('模型配置路径 [config/local/codex.json]：').strip() or 'config/local/codex.json';args+=['--config',path]
        if operation=='submit':
            task=input('任务内容：').strip()
            if not task:print('未输入任务，未提交。');continue
            args+=[task]
        main(args)

def main(argv=None):
    parser=argparse.ArgumentParser(description='有记忆的 AI 助手 CLI 管理；默认不启动、不唤醒。')
    parser.add_argument('--data',type=Path,default=DEFAULT_DATA,help='实例目录；默认首次唤醒专用目录')
    sub=parser.add_subparsers(dest='operation')
    for name in ('status','check','stage','stop','lock','login-status','login','exploration-status','roadmap'):sub.add_parser(name)
    for name in ('prepare','configure'):
        p=sub.add_parser(name);p.add_argument('--config',type=Path,default=PROJECT/'config/local/codex.json')
    p=sub.add_parser('setup-codex');p.add_argument('--config',type=Path,default=PROJECT/'config/local/codex.json');p.add_argument('--model',default='gpt-6.1-sol')
    p=sub.add_parser('submit');p.add_argument('text');p.add_argument('--key',default=None)
    p=sub.add_parser('wake');p.add_argument('--confirm',help='明确确认短语：WAKE 实例目录名')
    p=sub.add_parser('update',help='从已有源码提案检查、更新并监督既有实例；失败恢复旧版')
    p.add_argument('--proposal',required=True);p.add_argument('--confirm',help='明确确认短语：UPDATE 实例目录名')
    p=sub.add_parser('instance',help='与面板共用的后台进程控制');p.add_argument('action',choices=['status','start','stop','restart']);p.add_argument('--confirm',action='store_true')
    p=sub.add_parser('panel');p.add_argument('--port',type=int,default=8765)
    p=sub.add_parser('start',help='部署并唤醒既有实例，同时运行管理面板；保持终端打开')
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--open',action='store_true',help='打开浏览器')
    p.add_argument('--confirm',help='明确确认短语：WAKE 实例目录名')
    args=parser.parse_args(argv);data=args.data.expanduser()
    if not data.is_absolute():data=PROJECT/data
    data=data.resolve()
    try:
        op=args.operation
        if op is None:
            if sys.stdin.isatty():return menu(data)
            parser.print_help();return 0
        if op=='roadmap':
            from digital_life.application.monitoring.task_plan import inspect_plan
            print(json.dumps(inspect_plan(PROJECT),ensure_ascii=False,indent=2))
        elif op=='setup-codex':setup_codex(args.config,args.model)
        elif op in ('login','login-status'):
            command=[codex_path(),'login']+(['--device-auth'] if op=='login' else ['status'])
            return subprocess.run(command).returncode
        elif op=='wake':wake(data,args.confirm)
        elif op=='update':
            from digital_life.entrypoints.maintenance_update import update
            result=update(data,args.proposal,args.confirm)
            if not result.get('updated'):return 1
        elif op=='start':
            from digital_life.entrypoints.managed_session import start
            start(data,PROJECT,run,port=args.port,confirmation=args.confirm,open_browser=args.open)
        elif op=='prepare':
            config=args.config.resolve()
            if not config.is_file():raise ValueError('配置文件不存在，请先用 setup-codex 生成：'+str(config))
            if (data/'runtime.sqlite').exists():raise ValueError('实例已存在，未重复准备；请查看status或使用configure。')
            run(data,'prepare','--model-config',config)
        elif op=='configure':run(data,'configure-model',args.config.resolve(),'--offline')
        elif op=='status':
            from digital_life.application.lifecycle.release_inspection import release_status
            result=run(data,'inspect',capture=True);config=result['configuration']['model'];version=release_status(data,PROJECT)
            print(json.dumps({'实例':result['instance'],'目录':str(data),'禁止唤醒':result['wake_disabled'],'模型':config.get('model'),'后端':config.get('backend'),'数据检查':result['integrity'],'运行版本':version,'版本提示':'源码有更新，需通过CLI部署才能生效。' if version.get('source_matches_deployment') is False else '以运行版本信息为准。'},ensure_ascii=False,indent=2))
        elif op=='check':run(data,'check');run(data,'model-probe')
        elif op=='stage':run(data,'stage-release',PROJECT)
        elif op=='submit':run(data,'submit',args.text,'--key',args.key or 'cli-'+uuid.uuid4().hex)
        elif op=='instance':
            from digital_life.application.lifecycle.panel_control import PanelControl
            from digital_life.infrastructure.persistence.sqlite_store import Store
            store=Store(data)
            try:
                service=PanelControl(store)
                result=service.status() if args.action=='status' else service.submit(args.action,{'confirmed':args.confirm})
                print(json.dumps(result,ensure_ascii=False,indent=2))
            finally:store.close()
        elif op=='panel':run(data,'serve','--port',args.port)
        elif op=='exploration-status':run(data,'exploration','status')
        elif op in ('stop','lock'):
            run(data,'stop')
            if op=='lock':
                lock=data/'WAKE_DISABLED'
                if lock.is_symlink():raise ValueError('唤醒锁路径异常。')
                if not lock.exists():lock.write_text('explicit CLI user lock\n')
                print('已记录停止并加禁止唤醒锁；运行进程收到停止后退出。')
        return 0
    except KeyboardInterrupt:print('\n操作已中断。');return 130
    except (ValueError,OSError,ContractError) as error:print('未完成：'+str(error),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
