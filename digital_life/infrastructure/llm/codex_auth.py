"""Restricted official app-server authentication RPC. No inference or token handling."""
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time
from digital_life.domain.contracts import ContractError

VERIFY_URL='https://auth.openai.com/codex/device'

def child_env(home=None):
    env={k:v for k,v in os.environ.items() if k in ('HOME','PATH','TMPDIR','CODEX_HOME','USER','LOGNAME','LANG','LC_ALL','SSL_CERT_FILE','SSL_CERT_DIR','SYSTEMROOT')}
    if home is not None: env['CODEX_HOME']=str(home)
    return env

class AuthRPC:
    def __init__(self,executable,home=None):
        self.executable=executable;self.home=home;self.process=None;self.messages=queue.Queue(maxsize=256);self.seq=0;self.notifications=[];self.lock=threading.RLock()
    def _reader(self,process,messages):
        try:
            while True:
                line=process.stdout.readline(1024*1024+1)
                if not line:break
                if len(line)>1024*1024:break
                try:value=json.loads(line)
                except ValueError:break
                try:messages.put_nowait(value)
                except queue.Full:break
        finally:
            try:messages.put_nowait(None)
            except queue.Full:pass
    def _send(self,value):
        try:self.process.stdin.write((json.dumps(value)+'\n').encode());self.process.stdin.flush()
        except (OSError,AttributeError):raise ContractError('codex_auth_process_unavailable') from None
    def start(self):
        if self.process is not None:
            if self.process.poll() is not None:raise ContractError('codex_auth_process_exited')
            return
        if self.home:
            Path(self.home).mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(self.home,0o700)
        try:self.process=subprocess.Popen([self.executable,'app-server','--listen','stdio://','-c','cli_auth_credentials_store="file"','-c','features.apps=false','-c','mcp_servers={}'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=child_env(self.home),cwd=str(self.home or Path('/private/tmp')),start_new_session=True)
        except OSError:raise ContractError('codex_auth_executable_unavailable') from None
        threading.Thread(target=self._reader,args=(self.process,self.messages),daemon=True).start()
        self._request('initialize',{'clientInfo':{'name':'digital_life_panel','title':'Digital Life Panel','version':'0.1.0'}})
        self._send({'method':'initialized'})
    def _request(self,method,params):
        self.seq+=1;ref=self.seq;self._send({'id':ref,'method':method,'params':params});deadline=time.monotonic()+15
        while True:
            try:event=self.messages.get(timeout=max(.001,deadline-time.monotonic()))
            except queue.Empty:raise ContractError('codex_auth_timeout') from None
            if event is None:raise ContractError('codex_auth_process_exited')
            if not isinstance(event,dict):raise ContractError('codex_auth_invalid_protocol')
            if event.get('id')==ref:
                if 'error' in event:raise ContractError('codex_auth_request_failed')
                value=event.get('result')
                if not isinstance(value,dict):raise ContractError('codex_auth_invalid_protocol')
                return value
            self._notification(event)
    def _notification(self,event):
        if not isinstance(event,dict):raise ContractError('codex_auth_invalid_protocol')
        if event.get('method')=='account/login/completed' and isinstance(event.get('params'),dict):self.notifications=(self.notifications+[event.get('params',{})])[-16:]
        # Never respond to arbitrary server requests or execute requested tools.
        if 'id' in event and 'method' in event:self._send({'id':event['id'],'error':{'code':-32601,'message':'Unsupported method'}})
    def call(self,method,params):
        if method not in ('account/read','account/login/start','account/login/cancel'):raise ContractError('codex_auth_method_forbidden')
        with self.lock:
            try:self.start();return self._request(method,params)
            except Exception:self.close();raise
    def drain(self):
        with self.lock:
            while True:
                try:event=self.messages.get_nowait()
                except queue.Empty:break
                if event is None:raise ContractError('codex_auth_process_exited')
                self._notification(event)
            result=self.notifications;self.notifications=[];return result
    def close(self):
        with self.lock:
            p=self.process;self.process=None
            if p:
                if p.poll() is None:
                    try:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try:os.killpg(p.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        p.wait()
                    except ProcessLookupError:pass
                for stream in (p.stdin,p.stdout):
                    if stream:stream.close()
            self.messages=queue.Queue(maxsize=256);self.notifications=[]
