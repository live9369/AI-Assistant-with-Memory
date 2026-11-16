import tempfile
import unittest
from pathlib import Path
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.runtime.engine import Engine
from digital_life.application.chat.chat import Chat
from digital_life.application.services.memory import Memory
from digital_life.domain.contracts import Forbidden


class CognitionProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Store.prepare(Path(self.tmp.name)/'instance');self.addCleanup(self.s.close)
        self.c=CognitiveUpdates(self.s);self.actor=self.s.config()['controller']
        self.c.configure(True,self.actor);(self.s.root/'WAKE_DISABLED').unlink()
        control=Control(self.s.root,self.s.instance_id);control.resume('test-provenance');control.close()
    def think(self,source=None):
        class Model:
            name='fixture'
            def generate(model,request):
                ref=source or next(iter(request['cognition_sources']))
                return {'schema_version':3,'explanation':'收到。','action':{'tool':'wait','arguments':{'reason':'等待'}},'cognition':{'claims':[{'subject':'测试杯','predicate':'位置','value':'桌左','source_ref':ref,'quote':'测试杯在桌左','kind':'reported'}],'questions':[],'predictions':[],'plan':[]}}
        activity=Chat(self.s).send('test',{'text':'测试杯在桌左','idempotency_key':'one','expected_last_activity_id':None})['activity_id']
        Engine(self.s).think(activity,Model());return activity
    def test_candidate_time_does_not_replace_original_received_time(self):
        activity=self.think();signal=self.s.row('activities',activity)['trigger_event_id']
        self.s.db.execute('UPDATE perception_signals SET recorded_at=? WHERE id=?',('2020-01-01T00:00:00Z',signal))
        snapshot=self.c.snapshot();revision=snapshot[0]['current_revision_id']
        before=self.s.db.total_changes;provenance=self.c.provenance(snapshot)
        self.assertEqual(before,self.s.db.total_changes)
        self.assertEqual(provenance['sources'][signal]['recorded_at'],'2020-01-01T00:00:00Z')
        self.assertNotEqual(provenance['revisions'][revision]['recorded_at'],provenance['sources'][signal]['recorded_at'])
        self.assertEqual(self.c.snapshot(),snapshot)
    def test_revoked_memory_source_cannot_export_provenance(self):
        evidence=self.s.evidence(artifact=self.s.artifact({'fixture':'source'}))
        memory=Memory(self.s).encode('测试杯在桌左',evidence)
        self.think(memory['revision_id']);snapshot=self.c.snapshot()
        self.assertIn(memory['revision_id'],self.c.provenance(snapshot)['sources'])
        Memory(self.s).restrict(memory['memory_id'],[self.actor],self.actor)
        with self.assertRaises(Forbidden):self.c.provenance(snapshot)
    def test_model_response_memory_is_marked_as_model_output(self):
        evidence=self.s.evidence(artifact=self.s.artifact({'fixture':'model-output'}))
        memory=Memory(self.s).encode('测试杯在桌左',evidence,encoding_method='model-response-v1',source_role='inferred')
        metadata=self.c._source_metadata(memory['revision_id'])
        self.assertEqual(metadata['type'],'model-response-memory')
        self.assertEqual(metadata['time_basis'],'memory_written_not_original_event')
