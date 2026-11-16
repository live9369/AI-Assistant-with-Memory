import sqlite3
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class SystemSchemaTests(unittest.TestCase):
    def db(self,name):
        db=sqlite3.connect(':memory:')
        db.executescript((ROOT/'database/system-v2'/(name+'.sql')).read_text())
        self.addCleanup(db.close); return db
    def test_runtime_builds_and_contains_contract_fields(self):
        db=self.db('runtime')
        for table,fields in {
            'thought_requests':['prepared_activity_revision','expected_input_epoch','runtime_epoch','accepted_result_id'],
            'action_intents':['grant_id','proposal_revision','lifecycle_revision'],
            'jobs':['lease_token','lease_generation'],
            'runtime_events':['event_seq','source_event_id'],
            'consumer_receipts':['lease_token','lease_generation'],
        }.items():
            columns={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
            self.assertTrue(set(fields)<=columns,(table,columns))
        self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_control_is_independent(self):
        db=self.db('supervisor')
        names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'control_sleep_handoffs','instance_control_state','inbound_requests','wake_schedules'}<=names)
        self.assertNotIn('thought_requests',names)
    def test_model_code_import_never_starts_process(self):
        import primordial00.models
        self.assertTrue(callable(primordial00.models.resolve))

if __name__=='__main__': unittest.main(verbosity=2)
