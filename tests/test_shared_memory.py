import tempfile
from pathlib import Path
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.chat.chat import Chat
from digital_life.application.services.memory import Memory

class Model:
 name='fixture'
 def generate(self,request):return {'schema_version':1,'explanation':'liwei曾介绍自己为父亲。','action':{'tool':'wait','arguments':{'reason':'等待'}}}
class SharedMemoryTests(unittest.TestCase):
 def test_cross_thread_name_recall_excludes_current_question_and_records_reply(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store.prepare(Path(tmp)/'instance');chat=Chat(s)
   try:
    greeting=Engine(s).submit('你好，我是liwei，是你的父亲。','greeting');(s.root/'WAKE_DISABLED').unlink();Engine(s).think(greeting,Model())
    next_=chat.send('new-thread',{'text':'liwei你认识吗？','idempotency_key':'new','expected_last_activity_id':None})['activity_id']
    request,payload=Engine(s).prepare(next_,Model());memories=payload['selected_memories']
    self.assertTrue(any('我是liwei' in m['content'] for m in memories));self.assertFalse(any(m['content']=='liwei你认识吗？' for m in memories));self.assertEqual(payload['conversation_context']['messages'],[])
    self.assertTrue(any(m['source_kind']=='model-generated' for m in memories))
    count=len(s.rows('memory_items'));self.assertEqual(Memory(s).remember_public_responses(),0);self.assertEqual(len(s.rows('memory_items')),count)
   finally:s.close()
 def test_access_policy_still_applies_to_name_match(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store.prepare(Path(tmp)/'instance')
   try:
    engine=Engine(s);first=engine.submit('我是liwei，是你的父亲。','one');memory=s.rows('memory_items')[0]['id'];Memory(s).restrict(memory,[s.config()['controller']],s.config()['controller'])
    second=engine.submit('liwei是谁','two');context=engine.details(second)[1]['id'];items=Memory(s).retrieve('liwei是谁',second,context)['items'];self.assertFalse(any('父亲' in m['content'] for m in items))
   finally:s.close()
