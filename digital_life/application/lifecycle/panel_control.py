"""Durable, explicit native lifecycle operations, shared by HTTP and CLI."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
import uuid
from digital_life.domain.contracts import Conflict, ContractError, Forbidden, utc
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control, Releases
from digital_life.application.monitoring.instance_settings import InstanceSettings

PROJECT=Path(__file__).resolve().parents[3]
TERMINAL={'succeeded','failed','recovered','interrupted','cancelled'}


def folder(root):
    path=Path(root)/'panel-control'
    if path.is_symlink():raise Forbidden('控制记录目录不能是链接。')
    path.mkdir(mode=0o700,exist_ok=True)
    return path


def write(path,value):
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,ensure_ascii=False)
    os.replace(temp,path)


def read(path):
    if path.is_symlink():raise Forbidden('控制记录不能是链接。')
    return json.loads(path.read_text()) if path.exists() else None


class PanelControl:
    def __init__(self,store):self.s=store;self.root=store.root
    def status(self):
        InstanceSettings(self.s).native()
        control=InstanceSettings(self.s).control()
        path=self.root/'panel-control'
        operation=read(path/'operation.json') if path.exists() else None
        if operation and operation['state'] not in TERMINAL:
            fd=os.open(path/'operation.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
            try:
                try:
                    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    operation=dict(operation,state='interrupted',message='控制进程已退出；请检查状态后重试。')
                except BlockingIOError:pass
            finally:os.close(fd)
        return {'control':control,'wake_disabled':(self.root/'WAKE_DISABLED').exists(),'operation':operation}
    def submit(self,action,body,section=None):
        service=InstanceSettings(self.s);service.native()
        if action not in ('start','stop','restart','apply'):raise ContractError('未知进程操作。')
        if not isinstance(body,dict) or body.get('confirmed') is not True:raise ContractError('需要明确确认操作。')
        if action!='apply' and set(body)!={'confirmed'}:raise ContractError('进程操作只接受确认字段。')
        if not service.control()['prepared']:raise Conflict('请先准备实例控制记录。')
        if action!='stop' and (self.root/'WAKE_DISABLED').exists():raise Forbidden('禁止唤醒锁仍在；请通过 CLI 明确解除后再启动。')
        before=None
        if action=='apply':
            if set(body)!={'values','expected_revision','reason','confirmed'} or not isinstance(body.get('reason'),str) or not body['reason'].strip() or len(body['reason'])>2000:raise ContractError('请填写修改原因并确认。')
            before=next((s for s in service.sections() if s['id']==section),None)
            if before is None:raise ContractError('未知配置分组。')
            if body.get('expected_revision')!=before['revision']:raise Conflict('配置已变化，请重新读取。')
            service._validate(before,body.get('values'))
        path=folder(self.root)
        fd=os.open(path/'operation.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise Conflict('已有控制操作正在进行，请等待完成。')
            operation={'id':uuid.uuid4().hex,'action':action,'section':section,'state':'queued','message':'等待处理','started_at':utc(),'finished_at':None}
            write(path/'request.json',dict(operation=operation,body=body,before=before))
            write(path/'operation.json',operation)
            with (path/'worker.log').open('ab') as log:
                process=subprocess.Popen([sys.executable,'-m','digital_life.application.lifecycle.panel_control',str(self.root),'--worker',str(fd)],cwd=PROJECT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,pass_fds=(fd,))
            threading.Thread(target=process.wait,daemon=True).start()
            return operation
        finally:os.close(fd) # child retains the same flock until completion


class Operation:
    def __init__(self,root):
        self.root=Path(root);self.path=folder(root);self.request=read(self.path/'request.json');self.value=self.request['operation']
        self.s=Store(root);self.c=Control(root,self.s.instance_id);self.saved=False;self.stop_id=None
    def phase(self,state,message,**extra):
        self.value.update(state=state,message=message,**extra)
        if state in TERMINAL:self.value['finished_at']=utc()
        write(self.path/'operation.json',self.value)
    def wait_stopped(self,timeout=180):
        deadline=time.monotonic()+timeout
        while self.c.state()['active_process_run_id']:
            if time.monotonic()>deadline:raise Conflict('等待实例停止超时；未强制结束进程，请稍后查看。')
            time.sleep(.2)
    def unchanged_stop(self):
        if self.c.state()['last_stop_command_id']!=self.stop_id:raise Conflict('有新的停止命令，本次启动已取消。')
    def launch(self,deployment,recovery=False):
        self.unchanged_stop()
        self.c.resume(self.value['id']+'-resume-'+uuid.uuid4().hex,expected_stop=self.stop_id)
        receipt=self.path/('launch-'+uuid.uuid4().hex+'.json')
        with (self.path/'supervisor.log').open('ab') as log:
            process=subprocess.Popen([sys.executable,'-m','digital_life.application.lifecycle.panel_control',str(self.root),'--supervise',deployment,str(receipt),'rollback' if recovery else 'normal'],cwd=PROJECT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        deadline=time.monotonic()+660
        while time.monotonic()<deadline:
            result=read(receipt)
            if result is not None:
                if result.get('switched') is True:return result
                raise Conflict(result.get('error') or result.get('reason') or '部署未就绪，请查看部署日志。')
            if process.poll() is not None:raise Conflict('部署监督进程提前退出。')
            if self.c.state()['last_stop_command_id']!=self.stop_id:raise Conflict('有新的停止命令，启动已取消。')
            time.sleep(.2)
        self.c.stop(self.value['id']+'-launch-timeout')
        raise Conflict('启动等待超时，已记录停止。')
    def run(self):
        action=self.value['action'];old=None
        row=self.c.db.execute("SELECT id FROM deployments WHERE state='active' ORDER BY rowid DESC LIMIT 1").fetchone()
        deployment=row['id'] if row else None
        try:
            InstanceSettings(self.s).native()
            if action=='start' and self.c.state()['active_process_run_id'] and not self.c.state()['user_stopped']:
                self.phase('succeeded','实例已在运行。');return
            if action=='apply':
                old=next(s for s in InstanceSettings(self.s).sections() if s['id']==self.value['section'])
                if old['revision']!=self.request['body']['expected_revision']:raise Conflict('配置版本已变化，未停止或保存。')
            self.phase('stopping','正在等待实例停止，面板保持可用。')
            self.stop_id=self.c.stop(self.value['id']+'-stop')['last_stop_command_id']
            self.wait_stopped()
            self.unchanged_stop()
            if action=='stop':self.phase('succeeded','实例已停止。');return
            if action=='apply':
                self.phase('saving','正在保存本组配置。')
                InstanceSettings(self.s).save(self.value['section'],self.request['body']);self.saved=True
            if not deployment:
                self.phase('staging','首次启动：正在准备部署版本。')
                deployment=Releases(self.c).stage(PROJECT)
            self.phase('starting','正在启动原有部署并等待就绪。')
            result=self.launch(deployment)
            self.phase('succeeded','设置已应用，实例已运行。' if action=='apply' else '实例已运行。',deployment=deployment,pid=result.get('pid'))
        except Exception as error:
            failure=str(error)
            try:
                if self.saved:
                    self.phase('restoring','启动失败，正在恢复上一组配置。',error=failure)
                    # An external stop always wins; restore config but never resume it.
                    external=self.c.state()['last_stop_command_id']!=self.stop_id
                    if not external:self.stop_id=self.c.stop(self.value['id']+'-recovery-stop')['last_stop_command_id']
                    self.wait_stopped()
                    section=next(s for s in InstanceSettings(self.s).sections() if s['id']==old['id'])
                    if section['values']!=self.request['body']['values']:raise Conflict('配置已被其他操作修改，未覆盖。')
                    InstanceSettings(self.s).save(old['id'],dict(values=old['values'],expected_revision=section['revision'],reason='面板应用失败，恢复原配置：'+failure[:500],confirmed=True))
                    if not external:
                        self.phase('starting','旧配置已恢复，正在启动原部署。',error=failure)
                        self.launch(deployment,recovery=True)
                    self.phase('recovered','新配置未生效；已恢复旧配置。'+('实例保持停止。' if external else '原部署已运行。'),error=failure)
                else:self.phase('failed','操作未完成：'+failure,error=failure)
            except Exception as recovery:
                self.c.stop(self.value['id']+'-recovery-failed')
                self.phase('failed','恢复未完成，实例保持停止。',error=failure,recovery_error=str(recovery))
        finally:
            try:
                with self.s.tx():self.s.event('lifecycle.operation',payload=self.value,lane='control')
            finally:self.c.close();self.s.close()


def supervise(root,deployment,receipt,recovery=False):
    from digital_life.application.lifecycle.deployment import Deployment
    store=Store(root);control=Control(root,store.instance_id);manager=Deployment(control)
    try:
        # Normal launches preserve deployment checks; confirmed recovery skips a second model call.
        result=manager.launch(deployment,_recover=not recovery)
        if not result.get('switched') and not result.get('error'):
            row=control.db.execute('SELECT evidence FROM release_switches WHERE new_deployment_id=? ORDER BY rowid DESC LIMIT 1',(deployment,)).fetchone()
            if row:
                result['error']=json.loads(row['evidence']).get('error','部署未通过就绪检查。')
        write(Path(receipt),result)
        if manager.active:manager.supervise()
    except Exception as error:write(Path(receipt),{'switched':False,'error':str(error)})
    finally:control.close();store.close()


if __name__=='__main__':
    root=sys.argv[1]
    if sys.argv[2]=='--worker':
        try:Operation(root).run()
        finally:os.close(int(sys.argv[3]))
    elif sys.argv[2]=='--supervise':supervise(root,sys.argv[3],sys.argv[4],len(sys.argv)>5 and sys.argv[5]=='rollback')
