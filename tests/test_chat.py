import tempfile
from pathlib import Path
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.chat.chat import Chat
from digital_life.application.runtime.engine import Engine
from digital_life.domain.contracts import Conflict

class Reasoner:
 name='fixture'
 def __init__(self):self.requests=[]
 def generate(self,request):
  self.requests.append(request)
  return {'schema_version':1,'explanation':'你好，第'+str(len(self.requests))+'次回应','action':{'tool':'wait','arguments':{'reason':'等待交流'}}}
class ChatTests(unittest.TestCase):
 def test_turns_are_new_requests_with_explicit_context(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store.prepare(Path(tmp)/'instance');chat=Chat(s);reasoner=Reasoner()
   try:
    body={'text':'你好','idempotency_key':'first','expected_last_activity_id':None}
    first=chat.send('thread',body)['activity_id'];self.assertEqual(chat.send('thread',body)['activity_id'],first)
    self.assertFalse(chat.detail('thread')['can_send'])
    with self.assertRaises(Conflict):chat.send('thread',dict(body,idempotency_key='second'))
    (s.root/'WAKE_DISABLED').unlink();Engine(s).think(first,reasoner)
    second=chat.send('thread',{'text':'还记得我吗','idempotency_key':'second','expected_last_activity_id':first})['activity_id'];Engine(s).think(second,reasoner)
    self.assertNotEqual(first,second);self.assertEqual(len(s.rows('thought_requests')),2)
    self.assertEqual(reasoner.requests[0]['conversation_context']['messages'],[])
    self.assertEqual(reasoner.requests[1]['conversation_context']['messages'][0]['text'],'你好')
    self.assertEqual(len(chat.detail('thread')['messages']),4)
    self.assertEqual(chat.context(second)['thread_id'],'thread')
    self.assertEqual(chat.detail('other')['messages'],[])
    self.assertEqual(s.rows('action_attempts'),[])
    for activity in (first,second):
     self.assertEqual(s.row('activities',activity)['state'],'completed')
     self.assertEqual(Engine(s).details(activity)[3]['state'],'completed')
     self.assertEqual(s.db.execute("SELECT count(*) FROM runtime_events WHERE activity_id=? AND event_type='chat.turn_completed'",(activity,)).fetchone()[0],1)
    self.assertTrue(chat.detail('thread')['can_send'])
    self.assertEqual(chat.send('thread',body)['activity_id'],first)
    self.assertEqual(s.db.execute("SELECT count(*) FROM runtime_events WHERE event_type='chat.turn_completed'").fetchone()[0],2)

   finally:s.close()
 def test_different_text_cannot_reuse_key_and_read_is_pure(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store.prepare(Path(tmp)/'instance');chat=Chat(s)
   try:
    body={'text':'one','idempotency_key':'key','expected_last_activity_id':None};chat.send('thread',body)
    with self.assertRaises(Conflict):chat.send('thread',dict(body,text='two'))
    before=s.db.total_changes;chat.list();chat.detail('thread');self.assertEqual(s.db.total_changes,before);self.assertTrue((s.root/'WAKE_DISABLED').exists())
   finally:s.close()

 def test_failed_processing_displays_error_and_allows_new_turn(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store.prepare(Path(tmp)/'instance');chat=Chat(s)
   try:
    first=chat.send('thread',{'text':'hello','idempotency_key':'one','expected_last_activity_id':None})['activity_id'];(s.root/'WAKE_DISABLED').unlink()
    class Broken:
     name='fixture'
     def generate(self,request):raise ValueError('fixture failure')
    with self.assertRaises(ValueError):Engine(s).process_one(reasoner=Broken())
    detail=chat.detail('thread');self.assertTrue(detail['can_send']);self.assertEqual(detail['messages'][-1]['role'],'status')
    self.assertNotEqual(chat.send('thread',{'text':'retry','idempotency_key':'two','expected_last_activity_id':first})['activity_id'],first)
   finally:s.close()

 def test_clarification_and_tool_request_do_not_finish_goal(self):
  for tool,arguments in [('ask',{'reason':'请补充文件名'}),('write_note',{'path':'note.txt','text':'fixture'})]:
   with self.subTest(tool=tool),tempfile.TemporaryDirectory() as tmp:
    s=Store.prepare(Path(tmp)/'instance');chat=Chat(s)
    try:
     activity=chat.send('thread',{'text':'请处理任务','idempotency_key':'one','expected_last_activity_id':None})['activity_id']
     class Pending:
      name='fixture'
      def generate(self,request):return {'schema_version':1,'explanation':'需要继续处理','action':{'tool':tool,'arguments':arguments}}
     (s.root/'WAKE_DISABLED').unlink();Engine(s).think(activity,Pending())
     self.assertEqual(s.row('activities',activity)['state'],'waiting_input')
     self.assertEqual(Engine(s).details(activity)[3]['state'],'active')
     self.assertEqual(s.db.execute("SELECT count(*) FROM runtime_events WHERE event_type='chat.turn_completed'").fetchone()[0],0)
    finally:s.close()
