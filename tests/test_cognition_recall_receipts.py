"""Focused native write/reuse/recall and committed chat-receipt cases."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.application.chat.chat import Chat
from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
from digital_life.application.cognition.cognition_receipts import for_request
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.runtime.engine import Engine
from digital_life.application.services.memory import Memory
from digital_life.domain.contracts import Forbidden
from digital_life.infrastructure.persistence.sqlite_store import Store


class Model:
    name = 'fixture'
    def __init__(self, claims): self.claims = claims
    def generate(self, p):
        return {'schema_version': 3, 'explanation': '收到这条信息。',
                'action': {'tool': 'wait', 'arguments': {'reason': 'reply'}},
                'cognition': {'claims': self.claims(p), 'questions': [], 'predictions': [], 'plan': []}}


def claim(p, **changes):
    value = dict(subject='纸灯', predicate='位置', value='南侧架子', kind='reported',
                 source_ref=next(ref for ref, text in p['cognition_sources'].items() if text == p['observation']['text']), quote=p['observation']['text'])
    value.update(changes)
    return value


class RecallReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.s = Store.prepare(Path(self.tmp.name)/'instance'); self.addCleanup(self.s.close)
        CognitiveUpdates(self.s).configure(True, self.s.config()['controller'])
        (self.s.root/'WAKE_DISABLED').unlink()
        c = Control(self.s.root, self.s.instance_id); c.resume('fixture'); c.close()
        self.e = Engine(self.s); self.chat = Chat(self.s)

    def turn(self, text, claims, key='one', thread='test'):
        a = self.chat.send(thread, dict(text=text, idempotency_key=key, expected_last_activity_id=None))['activity_id']
        self.e.think(a, Model(claims))
        return a

    def count(self):
        return self.s.db.execute('SELECT count(*) FROM cognition_belief_revisions').fetchone()[0]

    def receipt(self, a):
        return self.chat.detail('test')['messages'][-1]['cognition_receipt']

    def test_same_source_different_quotes_reuses_without_losing_raw_output(self):
        a = self.turn('纸灯放在南侧架子。', lambda p: [claim(p), claim(p, quote='南侧架子')])
        self.assertEqual(self.count(), 1)
        receipt = self.receipt(a)
        self.assertEqual((receipt['created'], receipt['reused']), (1, 1))
        request = self.s.db.execute('SELECT * FROM thought_requests WHERE activity_id=?', (a,)).fetchone()
        result = self.s.row('thought_results', request['accepted_result_id'])
        self.assertEqual(len(self.s.read_artifact(result['parsed_artifact_id'])['cognition']['claims']), 2)
        before = self.s.db.total_changes
        self.chat.detail('test')
        self.assertEqual(self.s.db.total_changes, before)

    def recall_claims(self, p, kind='reported'):
        m = next(m for m in p['selected_memories'] if m.get('source_kind') == 'cognition-representation')
        return [claim(p, source_ref=m['revision_id'], quote='南侧架子', predicate='摆放地点', kind=kind)]

    def test_recall_paraphrase_does_not_create_belief_and_receipt_enters_history(self):
        self.turn('纸灯放在南侧架子。', lambda p: [claim(p)])
        a = self.turn('纸灯放在哪里？', self.recall_claims, key='two', thread='other')
        self.assertEqual(self.count(), 1)
        msgs = self.chat.detail('other')['messages']
        self.assertEqual(msgs[-1]['cognition_receipt']['suppressed_recall'], 1)
        b = self.chat.send('other', dict(text='继续', idempotency_key='three', expected_last_activity_id=a))['activity_id']
        packet = self.e.prepare(b, Model(lambda p: []))[1]
        self.assertTrue(any('未重复新增' in m.get('cognition_receipt', '') for m in packet['conversation_context']['messages']))
        self.assertEqual(packet['context_mode'], 'fresh_request')

    def test_new_hypothesis_from_recall_is_retained(self):
        self.turn('纸灯放在南侧架子。', lambda p: [claim(p)])
        self.turn('纸灯放在哪里？', lambda p: self.recall_claims(p, 'hypothesis'), key='two', thread='other')
        self.assertEqual(self.count(), 2)

    def test_correction_and_independent_source_are_not_merged(self):
        self.turn('纸灯放在南侧架子。', lambda p: [claim(p)])
        self.turn('纸灯放在南侧架子。', lambda p: [claim(p)], key='two', thread='other')
        self.assertEqual(self.count(), 2)
        self.turn('更正：纸灯在窗边。', lambda p: [claim(p, value='窗边')], key='three', thread='third')
        self.assertEqual(self.count(), 3)
        self.assertEqual({r[0] for r in self.s.db.execute('SELECT acceptance_state FROM cognition_belief_revisions')}, {'held'})

    def test_revoked_recall_source_is_rejected_before_suppression(self):
        self.turn('纸灯放在南侧架子。', lambda p: [claim(p)])
        a = self.chat.send('other', dict(text='纸灯位置？', idempotency_key='two', expected_last_activity_id=None))['activity_id']
        _, packet = self.e.prepare(a, Model(lambda p: []))
        claims = self.recall_claims(packet)
        m = self.s.row('memory_revisions', claims[0]['source_ref'])['memory_id']
        Memory(self.s).archive(m, self.s.config()['controller'], 'fixture revoke')
        output = Model(lambda p: claims).generate(packet)
        with self.assertRaises(Forbidden): CognitiveUpdates(self.s).check(a, packet, output)
        self.assertEqual(self.count(), 1)

    def test_failed_write_has_no_successful_receipt_or_accepted_reply(self):
        a = self.chat.send('test', dict(text='纸灯在南侧架子。', idempotency_key='one', expected_last_activity_id=None))['activity_id']
        with patch('digital_life.application.cognition.cognition_memory.publish', side_effect=RuntimeError('fixture failure')):
            with self.assertRaises(RuntimeError): self.e.think(a, Model(lambda p: [claim(p)]))
        request = self.s.db.execute('SELECT * FROM thought_requests WHERE activity_id=?', (a,)).fetchone()
        self.assertIsNone(request['accepted_result_id'])
        self.assertIsNone(for_request(self.s, a, request['id']))
        self.assertEqual(self.count(), 0)
        self.assertFalse(any(m.get('cognition_receipt') for m in self.chat.detail('test')['messages']))

    def test_repeated_thought_does_not_write_again(self):
        a = self.turn('纸灯在南侧架子。', lambda p: [claim(p)])
        request = self.s.db.execute('SELECT * FROM thought_requests WHERE activity_id=?', (a,)).fetchone()
        result = self.s.row('thought_results', request['accepted_result_id'])
        CognitiveUpdates(self.s).record(self.e, a, self.s.read_artifact(request['request_artifact_id']), self.s.read_artifact(result['parsed_artifact_id']), request['id'])
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.receipt(a)['created'], 1)

    def test_empty_or_historical_event_does_not_invent_write_counts(self):
        a = self.turn('你好。', lambda p: [])
        request = self.s.db.execute('SELECT * FROM thought_requests WHERE activity_id=?', (a,)).fetchone()
        self.assertIsNone(for_request(self.s, a, request['id']))
        with self.s.tx():
            self.s.event('cognition.output_recorded', payload={'request': 'legacy', 'revisions': ['old']}, activity=a, source='cognition', key='legacy')
        self.assertIsNone(for_request(self.s, a, 'legacy'))
