from digital_life.application.accounts import account_scope as scope
from digital_life.application.accounts.account_memory import change,listing
from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
import tempfile,unittest,sqlite3
from pathlib import Path
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.accounts.accounts import Accounts,install,AccountError,public
from digital_life.domain.contracts import Forbidden
class AccountsTest(unittest.TestCase):
 def test_roles_sessions_and_unique_root(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store.prepare(Path(tmp)/'instance');root=s.root;s.close();install(root)
   s=Store(root);a=Accounts(root,s.instance_id);p=dict(public(a.row(a.root_id())),bootstrap=True)
   try:
    admin=a.provision(s,p,dict(username='admin',display_name='管理员',role='admin',password='test-password-long'))['account']
    member=a.provision(s,admin,dict(username='member',display_name='用户',role='member',password='test-password-long'))['account']
    with self.assertRaises(Forbidden):a.provision(s,admin,dict(username='other',display_name='越权',role='admin',password='test-password-long'))
    with self.assertRaises(Forbidden):a.update(admin,p['id'],dict(expected_revision=p['revision'],status='disabled'))
    with self.assertRaises(Forbidden):a.update(p,member['id'],dict(expected_revision=0,role='root'))
    login=a.login('member','test-password-long');cookie=login.cookie.split(';')[0].split('=',1)[1]
    self.assertEqual(a.authenticate('Bearer '+cookie)['id'],member['id'])
    a.update(p,member['id'],dict(expected_revision=0,status='disabled'))
    with self.assertRaises(AccountError):a.authenticate('Bearer '+cookie)
    self.assertEqual(s.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    self.assertEqual(s.db.execute('PRAGMA foreign_key_check').fetchall(),[])
   finally:a.close();s.close()

import unittest,tempfile
from pathlib import Path
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.accounts.accounts import install,Accounts,public,AccountError
from digital_life.application.accounts.account_scope import audience
from digital_life.application.chat.chat import Chat
from digital_life.application.runtime.engine import Engine
from digital_life.application.services.memory import Memory
from digital_life.domain.contracts import Forbidden
class Fixture:
 name='fixture'
 def __init__(self):self.requests=[]
 def generate(self,p):
  self.requests.append(p)
  return dict(schema_version=1,explanation='fixture reply',action=dict(tool='wait',arguments=dict(reason='next')))
class Boundary(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Store.prepare(Path(self.tmp.name)/'instance');root=self.s.root;self.s.close();install(root);self.s=Store(root);self.auth=Accounts(root,self.s.instance_id);self.root=dict(public(self.auth.row(self.auth.root_id())),bootstrap=True)
  self.users=[self.auth.provision(self.s,self.root,dict(username=n,display_name=n,role='member',password='long-test-password'))['account'] for n in ('alice','bob')]
  (root/'WAKE_DISABLED').unlink()
  from digital_life.application.lifecycle.control_plane import Control
  c=Control(root,self.s.instance_id);c.resume('fixture-only');c.close();self.model=Fixture()
 def tearDown(self):self.auth.close();self.s.close();self.tmp.cleanup()
 def test_private_payload_and_fixed_conversation(self):
  alice,bob=self.users
  with audience(self.s,alice['id']):
   act=Chat(self.s).send(alice['thread_id'],dict(text='ALICE_PRIVATE_SECRET',idempotency_key='first',expected_last_activity_id=None))['activity_id']
   with self.assertRaises(Forbidden):Chat(self.s).send('arbitrary',{})
  Engine(self.s).think(act,self.model)
  with audience(self.s,bob['id']):
   with self.assertRaises(Forbidden):Chat(self.s).detail(alice['thread_id'])
   act2=Chat(self.s).send(bob['thread_id'],dict(text='hello',idempotency_key='first',expected_last_activity_id=None))['activity_id']
  Engine(self.s).think(act2,self.model)
  self.assertNotIn('ALICE_PRIVATE_SECRET',str(self.model.requests[-1]))
  self.assertEqual(self.model.requests[-1]['account_context']['id'],bob['id'])
 def test_direct_http_requires_auth_and_old_routes_fail_closed(self):
  from digital_life.entrypoints.http import Application
  app=Application(self.s.root)
  with self.assertRaises(AccountError):app.dispatch('GET','/v1/overview')
  login=self.auth.login('bob','long-test-password');token=login.cookie.split(';')[0].split('=',1)[1];bearer='Bearer '+token
  code,me=app.dispatch('GET','/v1/auth/me',controller_bearer=bearer);self.assertEqual(code,200)
  for route in ('/v1/overview','/v1/activities','/v1/logs','/v1/model/configuration'):
   with self.assertRaises(Forbidden):app.dispatch('GET',route,controller_bearer=bearer)
  with self.assertRaises(Forbidden):app.dispatch('GET','/v1/chats/'+self.users[0]['thread_id'],controller_bearer=bearer)
  self.assertEqual(app.dispatch('GET','/v1/conversation',controller_bearer=bearer)[0],200)

class Domains(Boundary):
 def send(self,user,text,key='first',previous=None):
  with scope.audience(self.s,user['id']):return Chat(self.s).send(user['thread_id'],dict(text=text,idempotency_key=key,expected_last_activity_id=previous))['activity_id']
 def test_share_revoke_admin_and_guest(self):
  alice,bob=self.users;act=self.send(alice,'DOMAIN_SECRET');Engine(self.s).think(act,self.model)
  signal=self.s.row('activities',act)['trigger_event_id']
  memory=self.s.db.execute('SELECT r.memory_id FROM memory_source_links l JOIN evidence_items e ON e.id=l.evidence_id JOIN memory_revisions r ON r.id=l.memory_revision_id WHERE e.origin_object_id=?',(signal,)).fetchone()[0]
  admin=self.auth.provision(self.s,self.root,dict(username='admin',display_name='admin',role='admin',password='long-test-password'))['account']
  guest=self.auth.provision(self.s,self.root,dict(username='guest',display_name='guest',role='guest',password='long-test-password'))['account']
  for user in (bob,guest):
   with scope.audience(self.s,user['id']):self.assertFalse(scope.can_recall(self.s,memory))
  with scope.audience(self.s,admin['id']):self.assertTrue(scope.can_recall(self.s,memory))
  with scope.audience(self.s,self.root['id']):change(self.s,self.root,dict(memory_id=memory,domain='shared',expected_revision=0))
  for user in (bob,guest):
   with scope.audience(self.s,user['id']):self.assertTrue(scope.can_recall(self.s,memory))
  with scope.audience(self.s,bob['id']):
   with self.assertRaises(Forbidden):change(self.s,bob,dict(memory_id=memory,domain='private',expected_revision=1))
  with scope.audience(self.s,self.root['id']):change(self.s,self.root,dict(memory_id=memory,domain='private',expected_revision=1))
  with scope.audience(self.s,bob['id']):self.assertFalse(scope.can_recall(self.s,memory))
 def test_role_downgrade_hides_privileged_history(self):
  admin=self.auth.provision(self.s,self.root,dict(username='admin',display_name='admin',role='admin',password='long-test-password'))['account']
  act=self.send(admin,'PRIVILEGED_TURN');Engine(self.s).think(act,self.model)
  self.auth.update(self.root,admin['id'],dict(expected_revision=0,role='member'))
  with scope.audience(self.s,admin['id']):
   self.assertEqual(Chat(self.s).detail(admin['thread_id'])['messages'],[])
   self.assertFalse(scope.visible_activity(self.s,act))
  act2=self.send(admin,'now member','second',act);Engine(self.s).think(act2,self.model)
  self.assertNotIn('PRIVILEGED_TURN',str(self.model.requests[-1]))
 def test_cognition_and_relationship_context_is_scoped(self):
  from digital_life.application.lifecycle.control_plane import Control
  from digital_life.application.behavior.people_relations import PeopleRelations
  from digital_life.application.behavior.behavior_policy import BehaviorPolicy
  c=Control(self.s.root,self.s.instance_id);c.stop('configure')
  CognitiveUpdates(self.s).configure(True,self.root['id']);PeopleRelations(self.s).configure(True,self.root['id']);BehaviorPolicy(self.s).configure(True,self.root['id']);c.resume('configured');c.close()
  class Cognition(Fixture):
   def generate(self,p):
    out=super().generate(p);out['schema_version']=3
    signal=next(iter(p['cognition_sources']))
    out['cognition']=dict(claims=[dict(subject='same-subject',predicate='location',value=p['observation']['text'],kind='reported',source_ref=signal,quote=p['observation']['text'])],questions=[],predictions=[],plan=[])
    return out
  model=Cognition();alice,bob=self.users
  Engine(self.s).think(self.send(alice,'COGNITION_PRIVATE'),model)
  Engine(self.s).think(self.send(bob,'bob information'),model)
  self.assertNotIn('COGNITION_PRIVATE',str(model.requests[-1]))
  with scope.audience(self.s,bob['id']):self.assertTrue(CognitiveUpdates(self.s).snapshot())

import threading,http.client,json
from digital_life.entrypoints.http import create_server
class CookieBoundary(Boundary):
 def test_cookie_login_logout_and_cross_origin(self):
  server=create_server(self.s.root,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  port=server.server_port
  def call(method,path,body=None,cookie=None,origin=None):
   c=http.client.HTTPConnection('127.0.0.1',port);h={'Content-Type':'application/json'}
   if cookie:h['Cookie']=cookie
   if origin:h['Origin']=origin
   c.request(method,path,json.dumps(body) if body is not None else None,h);r=c.getresponse();data=json.loads(r.read());out=r.status,r.getheader('Set-Cookie'),data;c.close();return out
  try:
   code,cookie,result=call('POST','/v1/auth/login',dict(username='bob',password='long-test-password'));self.assertEqual(code,200)
   self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
   cookie=cookie.split(';')[0]
   self.assertEqual(call('GET','/v1/auth/me',cookie=cookie)[0],200)
   self.assertEqual(call('GET','/v1/overview',cookie=cookie)[0],403)
   self.assertEqual(call('POST','/v1/conversation',dict(text='hello',idempotency_key='one',expected_last_activity_id=None),cookie=cookie,origin='http://evil.test')[0],403)
   self.assertEqual(call('POST','/v1/auth/logout',{},cookie=cookie)[0],200)
   self.assertEqual(call('GET','/v1/auth/me',cookie=cookie)[0],403)
  finally:server.shutdown();server.server_close();thread.join()

class MigrationTests(unittest.TestCase):
 def test_legacy_identity_memory_and_chat_are_retained(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store.prepare(Path(tmp)/'instance');root=s.root;identity=s.instance_id
   activity=Chat(s).send('legacy-thread',dict(text='legacy identity memory',idempotency_key='legacy',expected_last_activity_id=None))['activity_id']
   original=s.db.execute('SELECT attributes_json FROM context_snapshots WHERE activity_id=?',(activity,)).fetchone()[0]
   memory_count=len(s.rows('memory_items'));s.close();install(root);s=Store(root)
   auth=Accounts(root,s.instance_id)
   try:
    self.assertEqual(s.instance_id,identity);self.assertEqual(len(s.rows('memory_items')),memory_count)
    self.assertEqual(s.db.execute('SELECT attributes_json FROM context_snapshots WHERE activity_id=?',(activity,)).fetchone()[0],original)
    with audience(s,auth.root_id()):self.assertEqual(Chat(s).detail('acct_'+auth.root_id())['messages'][0]['text'],'legacy identity memory')
    self.assertEqual(s.db.execute('PRAGMA foreign_key_check').fetchall(),[])
   finally:auth.close();s.close()

class RevocationTests(Boundary):
 def test_role_revocation_during_model_call_rejects_result(self):
  user=self.users[0]
  with audience(self.s,user['id']):activity=Chat(self.s).send(user['thread_id'],dict(text='hello',idempotency_key='revocation',expected_last_activity_id=None))['activity_id']
  parent=self
  class Revoking(Fixture):
   def generate(self,p):
    result=super().generate(p);parent.auth.update(parent.root,user['id'],dict(expected_revision=0,status='disabled'));return result
  outcome=Engine(self.s).think(activity,Revoking())
  self.assertFalse(outcome['accepted']);self.assertEqual(outcome['reason'],'stale')
