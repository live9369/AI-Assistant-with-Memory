import json
from pathlib import Path
import tempfile
import time
import sqlite3
import unittest
from primordial00.core import Life,TestReasoner
from primordial00.supervisor import once,set_stopped

class PrimordialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'life'
        self.life=Life.initialize(self.root)
    def tearDown(self): self.life.close(); self.tmp.cleanup()
    def activity(self,text='保存一次真实经历'):
        activity=self.life.emit(text); self.life.tick(); return activity
    def test_complete_durable_loop_and_repeat_wake(self):
        activity=self.activity(); self.assertFalse(list((self.root/'notes').iterdir()))
        self.life.approve(activity); self.life.tick()
        identity=self.life.instance()['id']; self.life.close(); self.life=Life(self.root)
        self.life.tick()
        self.assertEqual(self.life.instance()['id'],identity)
        self.assertEqual(len(list((self.root/'notes').iterdir())),1)
        self.assertEqual(self.life.status()['activities'][0]['state'],'completed')
        self.assertEqual(self.life.status()['memory_count'],2)
    def test_each_thought_is_fresh_and_explicit(self):
        seen=[]
        class Recorder(TestReasoner):
            def generate(self,request):
                seen.append(request)
                self_check=set(request)&{'messages','history','thread_id','previous_response_id'}
                if self_check: raise ValueError('unexpected conversation')
                return super().generate(request)
        for text in ['first','second']:
            activity=self.life.emit(text); self.life.think(activity,Recorder())
        self.assertEqual([r['task'] for r in seen],['first','second'])
        self.assertIsNot(seen[0],seen[1])
        self.assertIn('selected_memories',seen[1])
    def test_external_effect_before_receipt_reconciles_without_duplicate(self):
        activity=self.activity(); self.life.approve(activity)
        with self.assertRaises(RuntimeError): self.life.execute(activity,interrupt_after_effect=True)
        self.assertEqual(self.life.status()['pending_actions'][0]['state'],'unknown')
        self.life.close(); self.life=Life(self.root); self.life.tick()
        self.assertEqual(len(list((self.root/'notes').iterdir())),1)
        self.assertEqual(self.life.status()['activities'][0]['state'],'completed')
    def test_cancel_during_thought_rejects_result(self):
        activity=self.life.emit('cancel me'); life=self.life
        class Cancelling(TestReasoner):
            def generate(self,request): life.cancel(activity); return super().generate(request)
        self.life.think(activity,Cancelling())
        self.assertEqual(self.life.db.execute('SELECT count(*) FROM thought_results').fetchone()[0],0)
    def test_idempotency_and_parameter_approval(self):
        first=self.life.emit('one','key'); self.assertEqual(first,self.life.emit('one','key'))
        with self.assertRaises(ValueError): self.life.emit('two','key')
        self.life.tick(); self.life.approve(first)
        with self.life.tx(): self.life.db.execute('UPDATE action_intents SET arguments_json=?',(json.dumps({'text':'changed'}),))
        with self.assertRaises(ValueError): self.life.execute(first)
        self.assertFalse(list((self.root/'notes').iterdir()))
    def test_commitment_cold_process_and_persistent_user_stop(self):
        key=self.life.commit('未来责任',time.time()-1)
        set_stopped(self.root,True)
        self.assertFalse(once(self.root)['spawned'])
        self.assertIsNone(self.life.status()['commitments'][0]['activity_id'])
        set_stopped(self.root,False)
        self.assertEqual(once(self.root)['state'],'awake_then_idle')
        c=self.life.status()['commitments'][0]; self.life.approve(c['activity_id'])
        self.assertEqual(once(self.root)['state'],'awake_then_idle')
        self.assertEqual(self.life.status()['commitments'][0]['state'],'fulfilled')
    def test_health_external_repair(self):
        (self.root/'notes').rmdir()
        self.assertEqual(self.life.health()['state'],'degraded')
        self.assertEqual(once(self.root)['state'],'awake_then_idle')
        self.assertEqual(self.life.health()['state'],'healthy')
    def test_tool_conflicting_existing_output_is_not_overwritten(self):
        activity=self.activity(); self.life.approve(activity)
        path=self.root/'notes'/f'{activity}.txt'; path.write_text('different')
        with self.assertRaises(ValueError): self.life.execute(activity)
        self.assertEqual(path.read_text(),'different')

    def test_one_failed_action_does_not_block_other_tasks(self):
        a=self.activity('first'); b=self.activity('second')
        self.life.approve(a); self.life.approve(b)
        (self.root/'notes'/f'{a}.txt').write_text('conflict')
        self.life.tick()
        states={r['id']:r['state'] for r in self.life.status()['activities']}
        self.assertEqual(states[a],'failed'); self.assertEqual(states[b],'completed')
        self.assertEqual(self.life.health()['state'],'degraded')

    def test_foreign_database_is_not_reinitialized(self):
        other=Path(self.tmp.name)/'other'; other.mkdir()
        db=sqlite3.connect(str(other/'runtime.sqlite')); db.execute('CREATE TABLE user_data(value TEXT)'); db.commit(); db.close()
        with self.assertRaises(ValueError): Life.initialize(other)
        db=sqlite3.connect(str(other/'runtime.sqlite'))
        self.assertEqual(db.execute('PRAGMA application_id').fetchone()[0],0)
        self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE name='user_data'").fetchone()); db.close()

if __name__=='__main__': unittest.main(verbosity=2)
