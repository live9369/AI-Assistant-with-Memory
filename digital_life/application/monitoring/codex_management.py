"""Panel-owned Codex auth/config/test operations; never wakes a life runtime."""
import re
import shutil
import threading
import time
from pathlib import Path
from digital_life.domain.contracts import ContractError,Conflict,utc
from digital_life.application.monitoring.management import ManagementError
from digital_life.infrastructure.llm.codex_auth import AuthRPC,VERIFY_URL

class CodexManagement:
    def __init__(self,root,executable=None,rpc_factory=AuthRPC):
        self.root=Path(root).resolve();self.executable=executable or shutil.which('codex');self.home=self.root/'codex-auth';self.rpc_factory=rpc_factory
        self.clients={};self.pending=None;self.last_state='idle';self.auth_lock=threading.RLock();self.test_lock=threading.Lock();self.expiry_timer=None
    def client(self,scope):
        if scope not in ('local','instance'):raise ManagementError(422,'INVALID_SCOPE','授权来源无效。')
        if not self.executable:raise ManagementError(503,'CODEX_MISSING','未发现本机Codex CLI。')
        if scope=='instance' and self.home.is_symlink():raise ContractError('invalid Codex auth directory')
        if scope not in self.clients:self.clients[scope]=self.rpc_factory(self.executable,self.home if scope=='instance' else None)
        return self.clients[scope]
    def config(self,value,scope):
        if not isinstance(value,dict):raise ContractError('invalid Codex config')
        if set(value)&{'executable','auth_home'}:raise ManagementError(422,'SERVER_MANAGED_PATH','Codex程序和授权目录由服务端管理。')
        self.client(scope)
        result=dict(value,executable=self.executable)
        if scope=='instance':result['auth_home']=str(self.home)
        return result
    def stopped(self,management):
        state=management.control()
        if not state['user_stopped'] or state['active_process_run_id']:raise Conflict('stop runtime before Codex management')
    def _settle(self):
        if not self.pending:return
        client=self.client('instance')
        for event in client.drain():
            if event.get('loginId')==self.pending['login_id']:
                self.last_state='completed' if event.get('success') is True else 'failed';self.pending=None;return
        if time.monotonic()>=self.pending['deadline']:
            try:client.call('account/login/cancel',{'loginId':self.pending['login_id']})
            finally:self.pending=None;self.last_state='expired'
    def status(self,scope='local'):
        if scope not in ('local','instance'):raise ManagementError(422,'INVALID_SCOPE','授权来源无效。')
        with self.auth_lock:
            try:
                if scope=='instance':self._settle()
                value=self.client(scope).call('account/read',{'refreshToken':False})
                if scope=='instance':self._settle()
                account=value.get('account') or {};kind=account.get('type');logged=kind=='chatgpt'
                result={'available':True,'logged_in':logged,'auth_type':kind or 'none','plan':account.get('planType') if logged else None,'scope':scope,'login_state':self.last_state if scope=='instance' else 'idle','inference_executed':False}
                if self.pending and scope=='instance':result.update(login_state='pending',verification_url=VERIFY_URL,user_code=self.pending['user_code'],expires_in=max(0,int(self.pending['deadline']-time.monotonic())))
                return result
            except ContractError:
                if scope=='instance':self.pending=None;self.last_state='failed'
                return {'available':False,'logged_in':False,'scope':scope,'login_state':'failed','reason':'无法检查Codex授权，请检查CLI、网络或稍后重试。','inference_executed':False}
    def authorize(self,management):
        self.stopped(management)
        with self.auth_lock:
            self._settle()
            if self.pending:return self.status('instance')
            if self.status('instance').get('logged_in'):return self.status('instance')
            value=self.client('instance').call('account/login/start',{'type':'chatgptDeviceCode'})
            code=value.get('userCode');ref=value.get('loginId')
            if value.get('verificationUrl')!=VERIFY_URL or not isinstance(code,str) or not re.fullmatch(r'[A-Za-z0-9-]{4,32}',code) or not isinstance(ref,str) or not ref:
                self.client('instance').close();raise ContractError('invalid device authorization response')
            if self.expiry_timer:self.expiry_timer.cancel()
            self.pending={'login_id':ref,'user_code':code,'deadline':time.monotonic()+300};self.last_state='pending'
            self.expiry_timer=threading.Timer(300,self._expire);self.expiry_timer.daemon=True;self.expiry_timer.start()
            return self.status('instance')
    def _expire(self):
        with self.auth_lock:
            try:self._settle()
            except Exception:
                self.pending=None;self.last_state='failed'
                if 'instance' in self.clients:self.clients['instance'].close()
    def cancel(self,management):
        self.stopped(management)
        with self.auth_lock:
            self._settle()
            if self.pending:
                try:self.client('instance').call('account/login/cancel',{'loginId':self.pending['login_id']})
                finally:
                    self.pending=None;self.last_state='cancelled'
                    if self.expiry_timer:self.expiry_timer.cancel()
            return self.status('instance')
    def test(self,management,body):
        self.stopped(management)
        if body.get('confirm_inference') is not True:raise ManagementError(422,'CONFIRM_TEST','请明确确认测试会消耗Codex额度。')
        row=management.config_row()
        if body.get('expected_configuration_id')!=row['id']:raise Conflict('configuration changed')
        config=management.s.config()['model']
        if config.get('backend')!='codex_cli':raise ContractError('Codex is not configured')
        # Only the server-discovered executable and managed isolated home may run via HTTP.
        if config.get('executable')!=self.executable or config.get('auth_home') not in (None,str(self.home)):raise ContractError('untrusted Codex route')
        if not self.test_lock.acquire(blocking=False):raise Conflict('Codex test already in progress')
        try:
            from digital_life.infrastructure.llm.inference import configured_reasoner
            result={'available':False,'configuration_id':row['id'],'checked_at':utc(),'inference_executed':False,'runtime_started':False,'action_executed':False}
            try:
                model=configured_reasoner(config)
                output=model.generate({'model':model.name,'task':'这是独立连接测试。只返回wait行动候选，reason为connection-test，不执行任何工具。'})
                if output['action']!={'tool':'wait','arguments':{'reason':'connection-test'}}:raise ContractError('unexpected test action')
                result.update(available=True,inference_executed=True,usage=model.last_usage,session_id=model.last_session_id)
            except Exception:result.update(reason='连接测试未通过，请检查授权、模型名称、启用状态、网络或额度。',inference_executed=None)
            result['configuration_current']=management.config_row()['id']==row['id']
            with management.s.tx():management.s.event('management.codex_tested',payload=result,lane='telemetry')
            return result
        finally:self.test_lock.release()
    def close(self):
        if self.expiry_timer:self.expiry_timer.cancel()
        for client in self.clients.values():client.close()
        self.pending=None
