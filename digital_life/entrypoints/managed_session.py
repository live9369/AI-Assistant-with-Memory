"""Foreground CLI session; never creates an instance or installs a service."""
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser


def active_pid(data):
    """Read existing registration without creating or migrating a database."""
    try:
        with sqlite3.connect((Path(data)/'control.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            row=db.execute('SELECT p.pid FROM instance_control_state c LEFT JOIN process_runs p '
                           'ON p.id=c.active_process_run_id WHERE c.active_process_run_id IS NOT NULL').fetchone()
    except sqlite3.Error as error:raise ValueError('无法只读检查运行登记；未创建或迁移实例。') from error
    if row is None:return None
    if row[0] is None:raise ValueError('运行登记不完整；请先检查并显式停止旧运行器。')
    return row[0]


def confirm(data,value):
    expected='WAKE '+data.name
    print('目标实例：'+str(data)+'\nstart 将部署并唤醒既有实例，同时打开管理面板；Ctrl+C 停止本次启动。')
    if value is None:
        if not sys.stdin.isatty():raise ValueError('请提供 --confirm "'+expected+'"')
        value=input('确认请输入 '+expected+'：').strip()
    if value!=expected:raise ValueError('确认不匹配，未启动。')
    return expected


def stop_child(child):
    """Signal only our new session/process group, including deployment descendants."""
    for sig,timeout in ((signal.SIGINT,12),(signal.SIGTERM,5),(signal.SIGKILL,5)):
        try:os.killpg(child.pid,sig)
        except ProcessLookupError:break
        try:child.wait(timeout=timeout);break
        except subprocess.TimeoutExpired:continue


def start(data,project,run,*,port=8765,confirmation=None,open_browser=False):
    from digital_life.infrastructure.processes.locks import exclusive
    from digital_life.entrypoints.http import create_server
    data=Path(data).resolve();project=Path(project).resolve()
    if not (data/'runtime.sqlite').is_file() or not (data/'control.sqlite').is_file():
        raise ValueError('既有实例不存在；start 不创建实例。')
    if (data/'MODEL_USAGE_REVIEW_REQUIRED').exists() or (data/'MODEL_USAGE_REVIEW_REQUIRED').is_symlink():
        raise ValueError('模型用量需要核对（MODEL_USAGE_REVIEW_REQUIRED）；未启动或解除保护，请先完成用量复核。')
    if not 1<=port<=65535:raise ValueError('面板端口必须在 1—65535 之间。')
    if (data/'WAKE_DISABLED').is_symlink():raise ValueError('唤醒锁路径异常。')
    with exclusive(data,'start-session.lock'):
        inspection=run(data,'inspect',capture=True)
        model=inspection.get('configuration',{}).get('model',{})
        if model.get('backend')=='codex_cli' and model.get('budget_mode')=='post_usage':
            try:
                with sqlite3.connect((data/'runtime.sqlite').as_uri()+'?mode=ro',uri=True) as db:
                    schema=db.execute('PRAGMA user_version').fetchone()[0]
            except sqlite3.Error as error:raise ValueError('无法只读确认严格实例版本；未启动。') from error
            if schema!=4:
                raise ValueError('Codex post_usage 需要严格实例（schema 4）；start 不自动升级，请先显式准备/升级严格实例。')
        pid=active_pid(data)
        if pid is not None:
            try:os.kill(pid,0)
            except ProcessLookupError:raise ValueError('旧运行器已退出但登记仍存在；请先显式 stop 并检查。')
            if (data/'WAKE_DISABLED').exists():raise ValueError('运行登记与禁止唤醒锁并存；请先检查并显式停止。')
            print('既有运行器 PID '+str(pid)+'；仅启动面板，不重复部署或唤醒。')
        else:confirmation=confirm(data,confirmation)
        try:server=create_server(data,port)
        except OSError as error:raise ValueError('面板端口 '+str(port)+' 无法使用；未启动运行器，请检查端口占用。') from error
        child=None;thread=None;serving=False
        try:
            thread=threading.Thread(target=server.serve_forever,name='management-panel',daemon=True)
            thread.start()
            serving=True
            if pid is None:
                child=subprocess.Popen([sys.executable,str(project/'manage.py'),'--data',str(data),
                    'wake','--confirm',confirmation],cwd=str(project),start_new_session=True)
            url='http://127.0.0.1:'+str(port)+'/'
            print('管理面板：'+url+'\n使用账户登录，首次打开可直接设置 root 密码。'+
                  '\n保持此终端打开；Ctrl+C 关闭本次面板'+('和运行器。' if child else '，既有运行器保持运行。'),flush=True)
            if open_browser:webbrowser.open(url)
            while child is None or child.poll() is None:time.sleep(.2)
            if child.returncode:raise ValueError('运行器启动或运行失败；请查看上方输出。')
        finally:
            try:
                if child is not None:
                    stop_child(child)
                    # Existing wake owns stop/control cleanup. Also restore its wake
                    # lock after a normal stop, never lock an unrelated runtime.
                    current=active_pid(data)
                    owned=current is None
                    if current is not None:
                        try:owned=os.getpgid(current)==child.pid
                        except ProcessLookupError:owned=True
                    if owned:
                        lock=data/'WAKE_DISABLED'
                        try:run(data,'stop',capture=True)
                        finally:
                            if lock.is_symlink():raise ValueError('唤醒锁路径异常。')
                            if not lock.exists():lock.write_text('foreground start ended; explicit wake required\n')
            finally:
                if serving:server.shutdown()
                server.server_close()
                if serving:thread.join(timeout=5)
