import tempfile,unittest
from pathlib import Path
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.accounts.accounts import Accounts,install,AccountError
from digital_life.entrypoints.http import Application
class SetupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();s=Store.prepare(Path(self.tmp.name)/'instance');self.root=s.root;s.close();install(self.root);self.app=Application(self.root)
 def tearDown(self):self.tmp.cleanup()
 def test_first_setup_creates_password_session_once(self):
  code,status=self.app.dispatch('GET','/v1/auth/status');self.assertTrue(status['root_setup_required'])
  code,result=self.app.dispatch('POST','/v1/auth/setup',{'new_password':'fixture-root-password'})
  self.assertEqual(result['account']['role'],'root');self.assertIn('HttpOnly',result.cookie)
  token=result.cookie.split(';')[0].split('=',1)[1]
  code,me=self.app.dispatch('GET','/v1/auth/me',controller_bearer='Bearer '+token);self.assertFalse(me['account']['bootstrap'])
  self.assertFalse(self.app.dispatch('GET','/v1/auth/status')[1]['root_setup_required'])
  with self.assertRaises(AccountError):self.app.dispatch('POST','/v1/auth/setup',{'new_password':'overwrite-root-password'})
  login=self.app.dispatch('POST','/v1/auth/login',{'username':'root','password':'fixture-root-password'})[1]
  self.assertEqual(login['account']['role'],'root')
 def test_bad_password_does_not_finish_setup(self):
  with self.assertRaises(AccountError):self.app.dispatch('POST','/v1/auth/setup',{'new_password':'short'})
  self.assertTrue(self.app.dispatch('GET','/v1/auth/status')[1]['root_setup_required'])

class HttpSetupTests(SetupTests):
 def test_first_setup_cookie_and_origin(self):
  import json,http.client,threading
  from digital_life.entrypoints.http import create_server
  server=create_server(self.root,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  def request(method,path,body=None,cookie=None,origin=None):
   conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
   headers={'Content-Type':'application/json'}
   if cookie:headers['Cookie']=cookie
   if origin:headers['Origin']=origin
   conn.request(method,path,json.dumps(body) if body else None,headers);response=conn.getresponse();value=json.loads(response.read());result=response.status,response.getheader('Set-Cookie'),value;conn.close();return result
  try:
   self.assertTrue(request('GET','/v1/auth/status')[2]['root_setup_required'])
   self.assertEqual(request('POST','/v1/auth/setup',{'new_password':'fixture-root-password'},origin='http://evil.test')[0],403)
   self.assertTrue(request('GET','/v1/auth/status')[2]['root_setup_required'])
   code,cookie,_=request('POST','/v1/auth/setup',{'new_password':'fixture-root-password'})
   self.assertEqual(code,200);self.assertIn('HttpOnly',cookie)
   cookie=cookie.split(';')[0]
   self.assertEqual(request('GET','/v1/auth/me',cookie=cookie)[0],200)
   self.assertEqual(request('GET','/v1/auth/me')[0],403)
   self.assertEqual(request('POST','/v1/auth/setup',{'new_password':'overwrite-password'})[0],409)
  finally:server.shutdown();server.server_close();thread.join()
