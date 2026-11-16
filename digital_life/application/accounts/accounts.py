"""Independent local account authentication; no model credentials or inference."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from digital_life.domain.contracts import ContractError, Forbidden, Conflict, identifier

APPLICATION_ID = 0x41434354
SESSION_SECONDS = 8 * 3600
IDLE_SECONDS = 30 * 60
PASSWORD_WORKERS = threading.BoundedSemaphore(2)
PUBLIC_FIELDS = ('id','username','display_name','role','status','revision','created_at')

class AccountError(ContractError):
    def __init__(self,status,code,message):
        super().__init__(message); self.status=status; self.code=code

class CookieReply(dict):
    def __init__(self,value,cookie): super().__init__(value); self.cookie=cookie

def enabled(root):
    path=Path(root)/'accounts.sqlite'
    if path.is_symlink(): raise Forbidden('account database cannot be a symlink')
    if not path.exists(): return False
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        if db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID: raise Forbidden('account database identity mismatch')
        row=db.execute("SELECT value FROM settings WHERE key='enabled'").fetchone()
        return bool(row and row[0]=='1')
    finally: db.close()

def password_hash(value):
    if not isinstance(value,str) or not 12<=len(value)<=256 or len(value.encode())>1024:
        raise AccountError(422,'PASSWORD_POLICY','密码需要12至256个字符。')
    salt=secrets.token_bytes(16)
    result=hashlib.pbkdf2_hmac('sha256',value.encode(),salt,600000)
    return 'pbkdf2-sha256$600000$'+salt.hex()+'$'+result.hex()

def password_ok(value,stored):
    valid=False; salt=b'\0'*16; expected=b'\0'*32
    try:
        algorithm,iterations,salt_hex,digest_hex=stored.split('$')
        if algorithm=='pbkdf2-sha256' and iterations=='600000':
            salt=bytes.fromhex(salt_hex);expected=bytes.fromhex(digest_hex)
            valid=len(salt)==16 and len(expected)==32
    except (AttributeError,ValueError): pass
    text=value if isinstance(value,str) and len(value)<=256 and len(value.encode())<=1024 else ''
    actual=hashlib.pbkdf2_hmac('sha256',text.encode(),salt,600000)
    return valid and secrets.compare_digest(actual,expected)

def public(row):
    result={key:row[key] for key in PUBLIC_FIELDS}
    result['password_configured']=bool(row['password_hash'])
    result['thread_id']='acct_'+row['id']
    return result

class Accounts:
    def __init__(self,root,instance_id=None,*,create=False,clock=None):
        self.root=Path(root).resolve();self.path=self.root/'accounts.sqlite';self.clock=clock or time.time
        if self.path.is_symlink():raise Forbidden('account database cannot be a symlink')
        if not self.path.exists():
            if not create:raise Forbidden('accounts not installed')
            fd=os.open(str(self.path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
        self.db=sqlite3.connect(str(self.path),isolation_level=None,timeout=5);self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        app=self.db.execute('PRAGMA application_id').fetchone()[0]
        if app==0 and create:
            self.db.executescript((Path(__file__).resolve().parents[2]/'resources/accounts.sql').read_text())
            self.db.execute('PRAGMA application_id='+str(APPLICATION_ID))
        elif app!=APPLICATION_ID:
            self.db.close();raise Forbidden('account database identity mismatch')
        if instance_id is not None:
            row=self.db.execute("SELECT value FROM settings WHERE key='instance_id'").fetchone()
            if row and row[0]!=instance_id:self.db.close();raise Forbidden('accounts belong to another instance')
    def close(self):self.db.close()
    @contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:yield;self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise
    def audit(self,actor,action,target=None,details=None):
        self.db.execute('INSERT INTO audit(at,actor_id,action,target_id,details) VALUES(?,?,?,?,?)',(self.clock(),actor,action,target,json.dumps(details or {},ensure_ascii=False)))
    def root_id(self):
        row=self.db.execute("SELECT id FROM accounts WHERE role='root'").fetchone()
        if not row:raise Forbidden('root account missing')
        return row[0]
    def row(self,account):
        row=self.db.execute('SELECT * FROM accounts WHERE id=?',(account,)).fetchone()
        if not row:raise AccountError(404,'ACCOUNT_NOT_FOUND','账户不存在。')
        return dict(row)
    def active_actor_ids(self):
        return [r[0] for r in self.db.execute("SELECT id FROM accounts WHERE status='active'")]
    def authenticate(self,bearer):
        if not isinstance(bearer,str) or not bearer.startswith('Bearer '):raise AccountError(403,'INVALID_TOKEN','请登录账户。')
        token=bearer[7:]
        if not token or len(token)>256 or not token.isascii():raise AccountError(403,'INVALID_TOKEN','登录已失效，请重新登录。')
        path=self.root/'controller.token'
        if path.is_symlink():raise Forbidden('invalid controller credential')
        if path.is_file() and secrets.compare_digest(token,path.read_text().strip()):
            row=self.row(self.root_id())
            if row['status']!='active':raise Forbidden('root is not active')
            return dict(public(row),bootstrap=True)
        digest=hashlib.sha256(token.encode()).hexdigest();now=self.clock()
        session=self.db.execute('SELECT * FROM sessions WHERE token_hash=?',(digest,)).fetchone()
        if not session:raise AccountError(403,'INVALID_TOKEN','登录已失效，请重新登录。')
        account=self.row(session['account_id'])
        if session['revoked'] or account['status']!='active' or session['account_revision']!=account['revision'] or now<session['created_at'] or now<session['last_seen'] or now>=session['expires_at'] or now-session['last_seen']>=IDLE_SECONDS:
            raise AccountError(403,'INVALID_TOKEN','登录已失效，请重新登录。')
        if now-session['last_seen']>=60:self.db.execute('UPDATE sessions SET last_seen=? WHERE token_hash=? AND revoked=0',(now,digest))
        return dict(public(account),bootstrap=False)
    def setup_required(self):
        root=self.row(self.root_id())
        return root['status']=='active' and root['password_hash'] is None and self.db.execute('SELECT count(*) FROM accounts').fetchone()[0]==1
    def setup_root(self,new_password):
        if not self.setup_required():raise AccountError(409,'SETUP_COMPLETE','Root setup is unavailable; use account login or local CLI recovery.')
        if not PASSWORD_WORKERS.acquire(blocking=False):raise AccountError(429,'LOGIN_BUSY','Please try again shortly.')
        try:
            encoded=password_hash(new_password)
            with self.tx():
                if not self.setup_required():raise AccountError(409,'SETUP_COMPLETE','Root setup is already complete.')
                account=self.root_id()
                changed=self.db.execute('UPDATE accounts SET password_hash=?,revision=revision+1 WHERE id=? AND password_hash IS NULL',(encoded,account)).rowcount
                if changed!=1:raise Conflict('root setup changed')
                self.db.execute('UPDATE sessions SET revoked=1 WHERE account_id=?',(account,))
                row=self.row(account);now=self.clock();token=secrets.token_urlsafe(32)
                self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,0)',(hashlib.sha256(token.encode()).hexdigest(),account,row['revision'],now,now,now+SESSION_SECONDS))
                self.audit(account,'root_initialized')
            return CookieReply({'account':public(row)},'digital_life_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age='+str(SESSION_SECONDS))
        finally:PASSWORD_WORKERS.release()
    def login(self,username,password):
        name=username.strip().casefold() if isinstance(username,str) else ''
        bucket=hashlib.sha256(name.encode()).hexdigest();now=self.clock()
        if not PASSWORD_WORKERS.acquire(blocking=False):raise AccountError(429,'LOGIN_BUSY','登录繁忙，请稍后重试。')
        try:
            with self.tx():
                self.db.execute('DELETE FROM login_attempts WHERE at<?',(now-900,))
                count=self.db.execute('SELECT count(*) FROM login_attempts WHERE bucket=?',(bucket,)).fetchone()[0]
                total=self.db.execute('SELECT count(*) FROM login_attempts').fetchone()[0]
                if count>=5 or total>=100:raise AccountError(429,'LOGIN_THROTTLED','登录尝试过多，请稍后重试。')
                row=self.db.execute('SELECT * FROM accounts WHERE username=?',(name,)).fetchone()
                ok=password_ok(password,row['password_hash'] if row else None)
                if not ok or not row or row['status']!='active':
                    self.db.execute('INSERT INTO login_attempts VALUES(?,?)',(bucket,now));self.audit(None,'login_failed')
                    failure=True
                else:
                    token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
                    self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,0)',(digest,row['id'],row['revision'],now,now,now+SESSION_SECONDS))
                    self.db.execute('DELETE FROM login_attempts WHERE bucket=?',(bucket,));self.audit(row['id'],'login');failure=False
            if failure:raise AccountError(403,'LOGIN_FAILED','账户或密码不正确，或账户暂不可用。')
            return CookieReply({'account':public(row)},'digital_life_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age='+str(SESSION_SECONDS))
        finally:PASSWORD_WORKERS.release()
    def logout(self,bearer):
        if isinstance(bearer,str) and bearer.startswith('Bearer '):
            digest=hashlib.sha256(bearer[7:].encode()).hexdigest();self.db.execute('UPDATE sessions SET revoked=1 WHERE token_hash=?',(digest,))
        return CookieReply({'logged_out':True},'digital_life_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
    def require_manager(self,principal,target_role=None):
        if principal['role'] not in ('root','admin'):raise Forbidden('account manager required')
        if principal['role']=='admin' and target_role not in (None,'member','guest'):raise Forbidden('only root manages administrators')
    def list(self,principal):
        self.require_manager(principal)
        return {'items':[public(r) for r in self.db.execute('SELECT * FROM accounts ORDER BY created_at,id')]}
    def provision(self,store,principal,body):
        if set(body)!={'username','display_name','role','password'}:raise AccountError(422,'INVALID_ACCOUNT','需要用户名、显示名、类型和密码。')
        name=body['username'];role=body['role'];display=body['display_name']
        if not isinstance(name,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,31}',name) or name=='root':raise AccountError(422,'INVALID_USERNAME','用户名需为3至32位小写字母、数字或._-，root为保留名称。')
        if role not in ('admin','member','guest'):raise Forbidden('cannot create another root')
        self.require_manager(principal,role)
        if not isinstance(display,str) or not display.strip() or len(display)>80 or any(ord(c)<32 for c in display):raise AccountError(422,'INVALID_DISPLAY_NAME','显示名不能为空或包含控制字符。')
        encoded=password_hash(body['password'])
        with self.tx():
            existing=self.db.execute('SELECT * FROM accounts WHERE username=?',(name,)).fetchone()
            if existing:
                if existing['status']!='provisioning' or existing['role']!=role or existing['display_name']!=display or not password_ok(body['password'],existing['password_hash']):raise AccountError(409,'USERNAME_EXISTS','用户名已存在。')
                account=existing['id']
            else:
                account=identifier();self.db.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,0,?)',(account,name,display,role,'provisioning',encoded,self.clock()))
                self.audit(principal['id'],'account_provisioning',account,{'role':role})
        # The identity projection is committed before authentication becomes active.
        with store.tx():
            old=store.db.execute('SELECT id FROM social_actors WHERE id=? AND instance_id=?',(account,store.instance_id)).fetchone()
            if not old:
                entity=store.insert('world_entities',entity_type='account',canonical_name=display,resolution_status='resolved')
                store.insert('social_actors',id=account,entity_id=entity,actor_type='account',identity_status='unverified')
                store.event('account.actor_created',payload={'account_id':account,'actor_ref':account,'real_world_identity_verified':False},source='accounts',key='account:'+account,lane='control')
        with self.tx():
            self.db.execute("UPDATE accounts SET status='active' WHERE id=? AND status='provisioning'",(account,));self.audit(principal['id'],'account_created',account,{'role':role})
        return {'account':public(self.row(account))}
    def update(self,principal,account,body):
        target=self.row(account);self.require_manager(principal,target['role'])
        if set(body)-{'expected_revision','role','status','display_name'} or body.get('expected_revision')!=target['revision']:raise Conflict('account revision changed or invalid fields')
        role=body.get('role',target['role']);status=body.get('status',target['status']);display=body.get('display_name',target['display_name'])
        if target['role']=='root' and (role!='root' or status!='active'):raise Forbidden('unique root cannot be disabled or demoted')
        if target['role']!='root' and role=='root':raise Forbidden('cannot create another root')
        if role not in ('root','admin','member','guest') or status not in ('active','disabled'):raise ContractError('invalid role or status')
        self.require_manager(principal,role)
        if not isinstance(display,str) or not display.strip() or len(display)>80 or any(ord(c)<32 for c in display):raise ContractError('invalid display name')
        with self.tx():
            changed=self.db.execute('UPDATE accounts SET role=?,status=?,display_name=?,revision=revision+1 WHERE id=? AND revision=?',(role,status,display,account,target['revision'])).rowcount
            if changed!=1:raise Conflict('account changed')
            self.db.execute('UPDATE sessions SET revoked=1 WHERE account_id=?',(account,));self.audit(principal['id'],'account_updated',account,{'role':role,'status':status})
        return {'account':public(self.row(account))}
    def change_password(self,principal,account,new_password,current_password=None):
        target=self.row(account)
        if account==principal['id']:
            if not principal.get('bootstrap') and not password_ok(current_password,target['password_hash']):raise AccountError(403,'PASSWORD_MISMATCH','当前密码不正确。')
        else:self.require_manager(principal,target['role'])
        encoded=password_hash(new_password)
        with self.tx():
            self.db.execute('UPDATE accounts SET password_hash=?,revision=revision+1 WHERE id=?',(encoded,account));self.db.execute('UPDATE sessions SET revoked=1 WHERE account_id=?',(account,));self.audit(principal['id'],'password_changed',account)
        return CookieReply({'changed':True,'reauthenticate':account==principal['id']},'digital_life_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0') if account==principal['id'] else {'changed':True}


def install(root):
    """Explicit stopped-instance migration, preserving native records and identity."""
    from digital_life.infrastructure.persistence.sqlite_store import Store
    from digital_life.application.lifecycle.control_plane import Control
    from digital_life.application.learning.runtime import qualified_plane_required
    from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
    root=Path(root).resolve()
    with dispatch_gate(root):
        store=Store(root)
        try:
            if qualified_plane_required(store) or store.db.execute('PRAGMA user_version').fetchone()[0] not in (2,3):raise Forbidden('account migration requires native schema2/3; protected migration is not implemented')
            control=Control(root,store.instance_id)
            try:
                state=control.state()
                if not state['user_stopped'] or state['active_process_run_id']:raise Conflict('stop before account installation')
            finally:control.close()
            instance=store.instance_id;controller=store.config()['controller']
        finally:store.close()
        db=sqlite3.connect(str(root/'runtime.sqlite'))
        try:db.executescript('BEGIN IMMEDIATE;\n'+(Path(__file__).resolve().parents[2]/'resources/account_runtime.sql').read_text()+'\nCOMMIT;')
        finally:db.close()
        auth=Accounts(root,instance,create=True)
        try:
            with auth.tx():
                auth.db.execute("INSERT OR IGNORE INTO settings VALUES('instance_id',?)",(instance,));auth.db.execute("INSERT OR IGNORE INTO settings VALUES('enabled','0')")
                existing=auth.db.execute("SELECT id FROM accounts WHERE role='root'").fetchone()
                if existing and existing[0]!=controller:raise Conflict('root binding differs')
                auth.db.execute("INSERT OR IGNORE INTO accounts VALUES(?,?,?,'root','provisioning',NULL,0,?)",(controller,'root','root',auth.clock()))
            store=Store(root)
            try:
                with store.tx():
                    store.db.execute("INSERT OR IGNORE INTO acct_activity_owners SELECT id,?,'privileged' FROM activities WHERE instance_id=?",(controller,instance))
                    store.db.execute("INSERT OR IGNORE INTO acct_conversation_turns(account_id,activity_id) SELECT ?,a.id FROM activities a JOIN context_snapshots c ON c.activity_id=a.id AND c.instance_id=a.instance_id WHERE a.instance_id=? AND json_extract(c.attributes_json,'$.chat.thread_id') IS NOT NULL ORDER BY a.rowid",(controller,instance))
            finally:store.close()
            with auth.tx():
                auth.db.execute("UPDATE accounts SET status='active' WHERE id=? AND role='root'",(controller,));auth.db.execute("UPDATE settings SET value='1' WHERE key='enabled'");auth.audit(controller,'accounts_installed',controller,{'history_domain':'root-private','one_conversation_per_account':True})
            return {'instance_id':instance,'root_account':public(auth.row(controller)),'inference_started':False}
        finally:auth.close()
