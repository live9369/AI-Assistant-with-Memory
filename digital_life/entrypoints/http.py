"""Authenticated local HTTP management entry point; no background life execution."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from http.cookies import SimpleCookie
from contextlib import ExitStack
from digital_life.application.accounts.accounts import Accounts,AccountError,enabled as accounts_enabled
from digital_life.application.accounts import account_scope as account_scope
from pathlib import Path
import re
import secrets
import time
import urllib.parse
from digital_life.domain.contracts import dumps,ContractError,Conflict,Forbidden,identifier
from digital_life.infrastructure.persistence.sqlite_store import Store,PACKAGE_ROOT
from digital_life.application.monitoring.management import Management,ManagementError,query_text
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.runtime.engine import Engine
from digital_life.application.services import Memory
from digital_life.application.accounts.authorization import Policy

STATIC={'/':('index.html','text/html; charset=utf-8'),'/assets/styles.css':('styles.css','text/css; charset=utf-8'),
        '/assets/app.js':('app.js','text/javascript; charset=utf-8')}
CSP="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"

def material_response_route(method,route):
    """Finite material dispatch/send, excluding control/authentication waits."""
    if not route.startswith('/v1/'):return False
    if route.startswith(('/v1/codex/','/v1/auth/')) or route in ('/v1/control/stop','/v1/model/templates'):return False
    return method in ('GET','POST')


class Application:
    def __init__(self,root,codex=None):
        self.root=Path(root).resolve()
        from digital_life.application.monitoring.codex_management import CodexManagement
        self.codex=codex or CodexManagement(self.root)
    def send_material(self,method,path,payload,controller_bearer,sender):
        """Hold actual instance gate through qualification, encoding and send.

        A completed local send is only an in-flight delivery fact. It does not
        prove remote viewing/deletion. Sender must enforce its finite deadline.
        """
        from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
        with dispatch_gate(self.root):
            code,value=self.dispatch(method,path,payload,controller_bearer=controller_bearer)
            return sender(code,value)

    def dispatch(self,method,path,payload=None,controller_bearer=None):
        body={} if payload is None else payload
        if not isinstance(body,dict): raise ManagementError(422,'INVALID_BODY','请求必须是JSON对象。')
        parsed=urllib.parse.urlsplit(path); route=parsed.path
        raw=urllib.parse.parse_qs(parsed.query,keep_blank_values=True)
        if any(len(value)!=1 for value in raw.values()): raise ManagementError(422,'INVALID_QUERY','查询参数不能重复。')
        query={key:value[0] for key,value in raw.items()}
        store=Store(self.root);account_stack=ExitStack()
        try:
            if account_scope.active(store):
                auth=Accounts(store.root,store.instance_id);account_stack.callback(auth.close)
                if route=='/v1/auth/status' and method=='GET':return 200,{'accounts_enabled':True,'root_setup_required':auth.setup_required()}
                if route=='/v1/auth/setup' and method=='POST':
                    if set(body)!={'new_password'}:raise AccountError(422,'INVALID_SETUP','Only new_password is accepted.')
                    return 200,auth.setup_root(body['new_password'])
                if route=='/v1/auth/login' and method=='POST':return 200,auth.login(body.get('username'),body.get('password'))
                principal=auth.authenticate(controller_bearer)
                account_stack.enter_context(account_scope.audience(store,principal['id']))
                if route=='/v1/auth/me' and method=='GET':return 200,{'account':principal,'accounts_enabled':True}
                from digital_life.application.accounts.account_http import dispatch as account_dispatch
                result=account_dispatch(store,auth,principal,method,route,body,query,controller_bearer)
                if result is not None:return result
            if route=='/v1/auth/status' and method=='GET':return 200,{'accounts_enabled':False,'root_setup_required':False}
            management=Management(store,self.codex); controller=store.config()['controller']
            from digital_life.application.learning.runtime import qualified_plane_required
            if qualified_plane_required(store):
                from digital_life.application.learning.controller_read import ControllerMaterialReader
                # Strict material routes authenticate again at their actual
                # source-use boundary, independent of HTTP handler plumbing.
                reader=ControllerMaterialReader(store,controller_bearer) if route.startswith('/v1/') else None
                thought=re.fullmatch(r'/v1/thoughts/([A-Za-z0-9_-]{1,128})',route)
                thoughts=re.fullmatch(r'/v1/activities/([A-Za-z0-9_-]{1,128})/thoughts',route)
                chat=re.fullmatch(r'/v1/chats/([A-Za-z0-9_-]{1,64})(/messages)?',route)
                if method=='GET' and thought:return 200,reader.thought(thought[1])
                if method=='GET' and thoughts:return 200,reader.thoughts(thoughts[1])
                if method=='GET' and route=='/v1/chats':return 200,reader.chats()
                if chat and method=='GET' and not chat[2]:return 200,reader.chat(chat[1])
                if chat and method=='POST' and chat[2]:return 202,reader.send(chat[1],body)
                if method=='GET' and route=='/v1/overview':return 200,reader.overview()
                if method=='GET' and route=='/v1/activities':return 200,reader.activities(query)
                activity=re.fullmatch(r'/v1/activities/([A-Za-z0-9_-]{1,128})',route)
                if method=='GET' and activity:return 200,reader.activity(activity[1])
                cancel=re.fullmatch(r'/v1/activities/([A-Za-z0-9_-]{1,128})/cancel',route)
                if method=='POST' and cancel:return 200,reader.cancel(cancel[1],body)
                if method=='GET' and route=='/v1/approvals':return 200,reader.approvals(query)
                if method=='GET' and route=='/v1/model/configuration':return 200,reader.model()
                if method=='GET' and route=='/v1/model/templates':return 200,management.templates()
                if method=='GET' and route=='/v1/health':return 200,reader.health()
                if method=='POST' and route=='/v1/health/check':return 200,reader.health()
                if method=='GET' and route in ('/v1/logs','/v1/logs/export'):return 200,reader.logs(query)
                log=re.fullmatch(r'/v1/logs/(\d+)',route)
                if method=='GET' and log:return 200,reader.logs(query,int(log[1]))
                if method=='POST' and route=='/v1/events':
                    from digital_life.application.learning.engine import submit_inbound
                    control=Control(self.root,store.instance_id)
                    try:
                        inbound=control.accept_inbound('http-controller',body['idempotency_key'],{'text':body['text']},controller)
                        activity_id=submit_inbound(store,body['text'],body['idempotency_key'],'http-controller')
                        return 202,{'activity_id':activity_id,'inbound_id':inbound,'inference_started':False}
                    finally:control.close()
                if method=='POST' and route in ('/v1/model/validate','/v1/model/configuration'):
                    reader.model()
                    return 200,management.validate_model(body) if route.endswith('/validate') else management.save_model(body)
                if method=='POST' and route=='/v1/codex/test':return 200,{'available':False,'inference_executed':False,'scope':'strict independent inference','reason':'No verified Codex clean-context and output-token-cap contract is configured.'}
                if route in ('/v1/codex/status','/v1/codex/authorize','/v1/codex/authorize/cancel'):
                    reader.model()
                    if method=='GET' and route.endswith('/status'):return 200,self.codex.status(query.get('scope','local'))
                    if method=='POST' and route.endswith('/cancel'):return 200,self.codex.cancel(management)
                    if method=='POST' and route.endswith('/authorize'):return 200,self.codex.authorize(management)
                approval=re.fullmatch(r'/v1/approvals/([A-Za-z0-9_-]{1,128})(/decision)?',route)
                if approval:
                    with reader.boundary():
                        row=store.row('approval_requests',approval[1]);origin=reader.action(row['action_ref'])
                        if method=='GET' and not approval[2]:result=management.approval(approval[1])
                        elif method=='POST' and approval[2]:result=management.decide(approval[1],body)
                        else:raise Forbidden('unsupported approval operation')
                        reader.qualify(origin,'controller_approval_return');return 200,result
            if route not in ('/v1/learning/content-reviews','/v1/control/stop','/internal/live','/internal/ready'):
                from digital_life.application.learning.runtime import strict_legacy_boundary
                strict_legacy_boundary(store,'controller_legacy_material_surface',route)
            if method=='POST' and route=='/v1/learning/content-reviews':
                from digital_life.application.learning.runtime import ControllerReviewAuthor
                return 201,ControllerReviewAuthor(store).author(controller_bearer,body)
            if method=='GET' and route=='/v1/codex/status': return 200,self.codex.status(query.get('scope','local'))
            if method=='POST' and route=='/v1/codex/authorize': return 200,self.codex.authorize(management)
            if method=='POST' and route=='/v1/codex/authorize/cancel': return 200,self.codex.cancel(management)
            if method=='POST' and route=='/v1/codex/test': return 200,self.codex.test(management,body)
            from digital_life.application.monitoring.thought_inspection import ThoughtInspection
            thought_match=re.fullmatch(r'/v1/thoughts/([A-Za-z0-9_-]{1,128})',route)
            if method=='GET' and thought_match:return 200,ThoughtInspection(store).detail(thought_match[1])
            thought_list=re.fullmatch(r'/v1/activities/([A-Za-z0-9_-]{1,128})/thoughts',route)
            if method=='GET' and thought_list:return 200,ThoughtInspection(store).list(thought_list[1])
            from digital_life.application.chat.chat import Chat
            if method=='GET' and route=='/v1/chats': return 200,Chat(store).list()
            chat_match=re.fullmatch(r'/v1/chats/([A-Za-z0-9_-]{1,64})(/messages)?',route)
            if chat_match and method=='GET' and not chat_match[2]: return 200,Chat(store).detail(chat_match[1])
            if chat_match and method=='POST' and chat_match[2]: return 202,Chat(store).send(chat_match[1],body)
            if route=='/v1/instance/lifecycle' and method=='GET':
                from digital_life.application.lifecycle.panel_control import PanelControl
                return 200,PanelControl(store).status()
            lifecycle=re.fullmatch(r'/v1/instance/lifecycle/(start|stop|restart)',route)
            apply_settings=re.fullmatch(r'/v1/instance/settings/([a-z_]+)/apply',route)
            if method=='POST' and (lifecycle or apply_settings):
                from digital_life.application.lifecycle.panel_control import PanelControl
                return 202,PanelControl(store).submit('apply' if apply_settings else lifecycle[1],body,apply_settings[1] if apply_settings else None)
            if route=='/v1/instance/settings' and method=='GET':
                from digital_life.application.monitoring.instance_settings import InstanceSettings
                return 200,InstanceSettings(store).read()
            setting_match=re.fullmatch(r'/v1/instance/settings/([a-z_]+)',route)
            if setting_match and method=='POST':
                from digital_life.application.monitoring.instance_settings import InstanceSettings
                return 200,InstanceSettings(store).save(setting_match[1],body)
            if method=='GET' and route=='/v1/overview': return 200,management.overview()
            if method=='GET' and route=='/v1/activities': return 200,management.activities(query)
            match=re.fullmatch(r'/v1/activities/([A-Za-z0-9_-]{1,128})',route)
            if method=='GET' and match: return 200,management.activity(match[1])
            match=re.fullmatch(r'/v1/activities/([A-Za-z0-9_-]{1,128})/cancel',route)
            if method=='POST' and match: return 200,management.cancel(match[1],body)
            if method=='GET' and route=='/v1/approvals': return 200,management.approvals(query)
            match=re.fullmatch(r'/v1/approvals/([A-Za-z0-9_-]{1,128})',route)
            if method=='GET' and match: return 200,management.approval(match[1])
            match=re.fullmatch(r'/v1/approvals/([A-Za-z0-9_-]{1,128})/decision',route)
            if method=='POST' and match: return 200,management.decide(match[1],body)
            if method=='GET' and route=='/v1/model/configuration': return 200,management.model()
            if method=='GET' and route=='/v1/model/templates': return 200,management.templates()
            if method=='POST' and route=='/v1/model/validate': return 200,management.validate_model(body)
            if method=='POST' and route=='/v1/model/configuration': return 200,management.save_model(body)
            if method=='POST' and route=='/v1/model/probe': return 200,management.probe_model(body)
            if method=='GET' and route=='/v1/health': return 200,management.health()
            if method=='POST' and route=='/v1/health/check': return 200,management.check_health()
            if method=='GET' and route=='/v1/logs/export': return 200,management.export_logs(query)
            if method=='GET' and route=='/v1/logs': return 200,management.logs(query)
            match=re.fullmatch(r'/v1/logs/(\d+)',route)
            if method=='GET' and match: return 200,management.log(match[1])
            if method=='GET' and route=='/v1/status':
                return 200,management.scrub({'instance_id':store.instance_id,'wake_disabled':(self.root/'WAKE_DISABLED').exists(),
                    'activities':store.rows('activities'),'approvals':store.rows('approval_requests'),
                    'commitments':store.rows('commitment_items'),'model':management.model()['configuration'],'integrity':store.integrity()})
            if method=='GET' and route=='/internal/live': return 200,{'alive':True,'scope':'HTTP only'}
            if method=='GET' and route=='/internal/ready':
                integrity=store.integrity(); ready=integrity['integrity']=='ok' and not integrity['foreign_keys']
                return 200 if ready else 503,{'storage_ready':ready,'model_configured':store.config()['model'].get('backend') in ('ollama','llamacpp','remote_chat','codex_cli'),'wake_disabled':(self.root/'WAKE_DISABLED').exists()}
            if method=='GET' and route=='/v1/commitments': return 200,store.rows('commitment_items')
            if method=='GET' and route=='/v1/metrics': return 200,{'definitions':store.rows('metric_definitions'),'samples':store.rows('metric_samples')}
            if method=='POST' and route=='/v1/metrics/collect':
                from digital_life.application.telemetry.metrics import Metrics
                return 200,Metrics(store).collect(body.get('dataset','runtime-v1'))
            if method=='POST' and route=='/v1/metrics/observations':
                from digital_life.application.telemetry.metrics import Metrics
                return 201,{'event':Metrics(store).observe(body['metric'],body['record'],body['source'],body['case'],controller,body.get('dataset','evaluation-v1'))}
            if method=='GET' and route=='/v1/events/stream':
                after=query.get('after','0')
                from digital_life.application.monitoring.management import integer
                after=integer(after,0)
                rows=[dict(r) for r in store.db.execute('SELECT event_seq,event_type,recorded_at FROM runtime_events WHERE instance_id=? AND event_seq>? ORDER BY event_seq LIMIT 100',(store.instance_id,after))]
                return 200,{'events':rows,'cursor':rows[-1]['event_seq'] if rows else after,'plane':'runtime'}
            if method=='POST' and route=='/v1/events':
                task=body['text']; key=body['idempotency_key']
                control=Control(self.root,store.instance_id)
                try:
                    inbound=control.accept_inbound('http-controller',key,{'text':task},controller); control.transfer_inbound(store)
                    ack=control.db.execute('SELECT runtime_ack_event_id FROM inbound_requests WHERE id=?',(inbound,)).fetchone()[0]
                    if not ack: return 202,{'inbound_id':inbound,'inference_started':False}
                    return 202,{'activity_id':store.row('runtime_events',ack)['activity_id'],'inbound_id':inbound,'inference_started':False}
                finally: control.close()
            if method=='POST' and route=='/v1/policy/mode': return 200,{'policy':Policy(store).mode(body['mode'],body['tools'],controller)}
            if method=='POST' and route=='/v1/control/stop':
                key=query_text(body.get('idempotency_key'),240)
                if not key: raise ManagementError(422,'INVALID_BODY','停止操作需要幂等标识。')
                control=Control(self.root,store.instance_id)
                try:
                    result=control.stop(key)
                    with store.tx(): store.event('management.stopped',payload={'user_stopped':True},source='management',key='stop:'+key,lane='control')
                    return 200,result
                finally: control.close()
            if method=='POST' and route=='/v1/memory/delete': return 202,{'request':Memory(store).redact(body['memory_id'],controller),'complete_erasure':False}
            if method=='POST' and route=='/v1/memory/purge':
                from digital_life.application.accounts.privacy import Privacy
                return 200,Privacy(store).erase(body['memory_id'],controller,body.get('include_registered_backups',False))
            return 404,{'error':{'code':'NOT_FOUND','message':'找不到该接口。'}}
        finally: account_stack.close();store.close()

def create_server(root,port=8765,codex=None):
    root=Path(root).resolve(); check=Store(root); check.close()
    token_path=root/'controller.token'
    if token_path.is_symlink(): raise Forbidden('invalid credential file')
    if not token_path.exists():
        import os
        fd=os.open(str(token_path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream: stream.write(secrets.token_urlsafe(32))
    token=token_path.read_text().strip()
    if not token: raise Forbidden('empty controller credential')
    app=Application(root,codex)
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args): pass
        def do_GET(self): self.handle_request()
        def do_POST(self): self.handle_request()
        def do_PUT(self): self.handle_request()
        def do_PATCH(self): self.handle_request()
        def do_DELETE(self): self.handle_request()
        def do_HEAD(self): self.handle_request()
        def headers_for(self,code,content_type,length):
            self.send_response(code); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(length))
            self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY'); self.send_header('Content-Security-Policy',CSP); self.send_header('Referrer-Policy','no-referrer')
            cookie=getattr(self,'_response_cookie',None)
            if cookie:self.send_header('Set-Cookie',cookie)
            self._response_cookie=None;self.end_headers()
        def send_data(self,code,value,content_type='application/json; charset=utf-8'):
            self._response_cookie=getattr(value,'cookie',None)
            data=value if isinstance(value,bytes) else dumps(value).encode()
            deadline=getattr(self,'_material_send_deadline',None)
            def remaining():
                if deadline is not None:
                    seconds=deadline-time.monotonic()
                    if seconds<=0:raise TimeoutError('material response total deadline exhausted')
                    self.connection.settimeout(min(2.0,seconds))
            remaining();self.headers_for(code,content_type,len(data))
            if self.command!='HEAD':remaining();self.wfile.write(data)
        def error_json(self,status,code,message):
            self.send_data(status,{'error':{'code':code,'message':message},'request_id':identifier()})
        def handle_request(self):
            try: self.respond()
            except (BrokenPipeError,ConnectionResetError,TimeoutError):self.close_connection=True
        def respond(self):
            port=self.server.server_port; hosts=('127.0.0.1:'+str(port),'localhost:'+str(port))
            if self.headers.get('Host') not in hosts:
                self.close_connection=True; self.error_json(403,'INVALID_HOST','请求来源不允许。'); return
            origin=self.headers.get('Origin')
            if origin and origin not in ('http://'+hosts[0],'http://'+hosts[1]):
                self.close_connection=True; self.error_json(403,'INVALID_ORIGIN','请求来源不允许。'); return
            parsed=urllib.parse.urlsplit(self.path); route=parsed.path
            if self.command in ('GET','HEAD') and route in STATIC and not parsed.query:
                name,content_type=STATIC[route]; self.send_data(200,(PACKAGE_ROOT/'web'/name).read_bytes(),content_type); return
            if self.command=='GET' and route=='/favicon.ico': self.send_data(204,b''); return
            provided=self.headers.get('Authorization','')
            if accounts_enabled(root):
                if not provided:
                    cookie=SimpleCookie()
                    try:cookie.load(self.headers.get('Cookie',''))
                    except Exception:cookie=SimpleCookie()
                    if 'digital_life_session' in cookie:provided='Bearer '+cookie['digital_life_session'].value
            elif not (self.command=='GET' and route=='/v1/auth/status') and (not provided.isascii() or not secrets.compare_digest(provided,'Bearer '+token)):
                self.close_connection=True; self.error_json(403,'INVALID_TOKEN','控制令牌无效，请重新连接。'); return
            if self.command not in ('GET','POST'):
                self.close_connection=True; self.error_json(405,'METHOD_NOT_ALLOWED','该操作方式不受支持。'); return
            try:
                if self.headers.get('Transfer-Encoding'): raise ManagementError(422,'INVALID_BODY','不支持该请求编码。')
                raw_length=self.headers.get('Content-Length','0')
                if not raw_length.isdigit(): raise ManagementError(422,'INVALID_BODY','载荷长度无效。')
                length=int(raw_length)
                if length>65536: self.close_connection=True; raise ManagementError(413,'PAYLOAD_TOO_LARGE','请求内容过长。')
                raw_body=self.rfile.read(length) if length else b'{}'
                if route=='/v1/learning/content-reviews':
                    from digital_life.domain.tool_learning_contract import loads
                    payload=loads(raw_body)
                else:payload=json.loads(raw_body)
                def emit(code,value):
                    if route=='/v1/logs/export' and code==200:
                        data=('\n'.join(dumps(row) for row in value['items'])+('\n' if value['items'] else '')).encode()
                        self.send_data(code,data,'application/x-ndjson; charset=utf-8');return
                    if route=='/v1/events/stream' and code==200:
                        content=''.join('id: '+str(event['event_seq'])+'\ndata: '+dumps(event)+'\n\n' for event in value['events'])+': reconnect to read more\n\n'
                        self.send_data(code,content.encode(),'text/event-stream');return
                    self.send_data(code,value)
                if material_response_route(self.command,route):
                    previous_timeout=self.connection.gettimeout();self._material_send_deadline=time.monotonic()+35.0
                    try:app.send_material(self.command,self.path,payload,provided,emit)
                    finally:
                        self._material_send_deadline=None;self.connection.settimeout(previous_timeout)
                else:
                    code,value=app.dispatch(self.command,self.path,payload,controller_bearer=provided);emit(code,value)
            except (BrokenPipeError,ConnectionResetError,TimeoutError):self.close_connection=True
            except AccountError as error: self.error_json(error.status,error.code,str(error))
            except ManagementError as error: self.error_json(error.status,error.code,str(error))
            except Forbidden: self.error_json(403,'FORBIDDEN','当前权限或运行状态不允许此操作。')
            except Conflict: self.error_json(409,'CONFLICT','记录已变化、过期或当前状态不允许此操作，请刷新后重试。')
            except (ContractError,ValueError,KeyError,TypeError,UnicodeError): self.error_json(422,'INVALID_REQUEST','参数或配置不符合要求，请核对后重试。')
            except Exception as error:
                import traceback,sqlite3
                traceback.print_exc()
                diagnostic=None
                try:
                    diagnostic=Store(root)
                    with diagnostic.tx():diagnostic.event('http.request_failed',payload={'method':self.command,'route':route,'error_type':type(error).__name__,'reason':str(error)[:240] if isinstance(error,sqlite3.Error) else type(error).__name__},source='http',lane='control')
                except Exception:pass
                finally:
                    if diagnostic is not None:diagnostic.close()
                self.error_json(503,'INTERNAL_FAILURE','服务暂时无法完成请求，请稍后重试。')
    class ManagedServer(ThreadingHTTPServer):
        def server_close(self):
            app.codex.close()
            super().server_close()
    server=ManagedServer(('127.0.0.1',port),Handler); server.daemon_threads=True
    return server

def serve(root,port=8765):
    server=create_server(root,port)
    try: server.serve_forever()
    finally: server.server_close()
