import json
import tempfile
import unittest
from pathlib import Path
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.chat.chat import Chat
from digital_life.application.runtime.engine import Engine
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.services.personality import Personality
from digital_life.application.behavior.personality_growth import PersonalityGrowth
from digital_life.domain.contracts import Conflict, dumps, sha
from scripts.development.configure_chat_baseline import apply


class ChatExpressionTests(unittest.TestCase):
    def test_approved_baseline_reaches_each_fresh_request_and_keeps_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'instance'
            s = Store.prepare(root)
            identity = s.instance_id
            spec = {'version': 'chat-personality-v0.1', 'values': {'openness': .4, 'conscientiousness': .3, 'extraversion': -.1, 'agreeableness': .3, 'emotional_stability': .3}, 'growth_enabled': False}
            proposal = Path(tmp) / 'spec.json'; proposal.write_text(json.dumps(spec))
            approval = Path(tmp) / 'approval.json'; approval.write_text(json.dumps({'approved': True, 'approved_spec_sha256': sha(dumps(spec)), 'source': 'isolated-test-approval'}))
            s.close()
            apply(root, proposal, approval)
            apply(root, proposal, approval)
            s = Store(root)
            try:
                self.assertEqual(s.instance_id, identity)
                self.assertEqual(len(s.rows('personality_profiles')), 2)
                self.assertEqual(s.rows('personality_profiles')[0]['version'], 0)
                self.assertFalse(PersonalityGrowth(s).config()['enabled'])
                (root / 'WAKE_DISABLED').unlink()
                c = Control(root, identity); c.resume('isolated-chat-expression'); c.close()
                with self.assertRaises(Conflict): apply(root, proposal, approval)
                class Model:
                    name = 'fixture'
                    def __init__(self): self.requests = []
                    def generate(self, request):
                        self.requests.append(request)
                        return {'schema_version': 1, 'explanation': '你好，我是原初00。', 'action': {'tool': 'wait', 'arguments': {'reason': '等待交流'}}}
                model = Model(); chat = Chat(s)
                first = chat.send('test', {'text': '我是liwei', 'idempotency_key': 'one', 'expected_last_activity_id': None})['activity_id']
                Engine(s).think(first, model)
                second = chat.send('test', {'text': '我是谁？', 'idempotency_key': 'two', 'expected_last_activity_id': first})['activity_id']
                Engine(s).think(second, model)
                self.assertEqual(len(model.requests), 2)
                self.assertNotEqual(model.requests[0]['activity_id'], model.requests[1]['activity_id'])
                self.assertEqual(model.requests[1]['conversation_context']['messages'][0]['text'], '我是liwei')
                for payload in model.requests:
                    self.assertEqual(payload['chat_expression']['self']['name'], '原初00')
                    self.assertEqual(payload['chat_expression']['traits']['openness']['value'], .4)
                    for key in ('relationships', 'goal_regulation', 'behavior_policy'):
                        self.assertIn(key, payload)
                    self.assertNotIn('personality_growth', payload)
                    self.assertNotIn('previous_response_id', payload)
                self.assertTrue(chat.detail('test')['can_send'])
                self.assertEqual(s.integrity(), {'integrity': 'ok', 'foreign_keys': []})
            finally: s.close()

    def test_compact_states_preserve_values_references_and_freshness(self):
        import copy
        from digital_life.infrastructure.llm.compact_states import compact_chat_states, expand_states
        request = {'chat_expression': {'version': 'chat-expression-v1'}, 'states': {
            'state.'+str(i): {'value': i, 'fresh': bool(i % 2), 'ref': 'observation-'+str(i),
                             'source_ref': 'same-evidence-reference', 'observed_at': '2026-11-14T00:00:00Z',
                             'expires_at': '2026-11-14T00:01:00Z', 'unit': 'count'} for i in range(36)}}
        before = copy.deepcopy(request)
        wire = compact_chat_states(request)
        self.assertEqual(wire['states']['encoding'], 'columns-and-rows-v1')
        self.assertEqual(expand_states(wire['states']), request['states'])
        self.assertIs(type(expand_states(wire['states'])['state.0']['fresh']), bool)
        self.assertEqual(request, before)
        self.assertLess(len(dumps(wire)), len(dumps(request)))
        request['states']['extra'] = {'value': None}
        self.assertIs(compact_chat_states(request), request)

    def test_codex_prefers_readable_input_without_relaxing_configured_cap(self):
        from digital_life.infrastructure.llm.codex_cli import CodexReasoner
        from digital_life.domain.contracts import ContractError
        model = CodexReasoner({'model': 'fixture', 'executable': '/unused', 'context_window': 32768})
        request = {'model': model.name, 'chat_expression': {'version': 'chat-expression-v1'},
                   'states': {'state.'+str(i): {'value': i, 'fresh': True, 'source_ref': 'evidence', 'ref': 'observation-'+str(i)} for i in range(36)}}
        self.assertEqual(model.payload(request).split('本次完整输入：\n', 1)[1], dumps(request))
        model.max_input_bytes = 2048
        with self.assertRaises(ContractError):
            model.payload(dict(request, task='x'*4096))

    def test_new_request_pins_latest_config_even_when_generic_rows_are_unordered(self):
        from unittest.mock import patch
        from digital_life.application.runtime.configuration import configure_model
        with tempfile.TemporaryDirectory() as tmp:
            s = Store.prepare(Path(tmp)/'instance')
            try:
                configured = configure_model(s, {'backend': 'codex_cli', 'model': 'fixture', 'executable': '/unused', 'context_window': 32768}, s.config()['controller'], check_available=False)
                (s.root/'WAKE_DISABLED').unlink()
                c = Control(s.root, s.instance_id); c.resume('isolated-config-pinning'); c.close()
                original_rows = s.rows
                def unordered_rows(table):
                    if table in ('configuration_versions', 'model_versions'):
                        return [dict(row) for row in s.db.execute('SELECT * FROM '+table+' WHERE instance_id=? ORDER BY rowid DESC', (s.instance_id,))]
                    return original_rows(table)
                class Model: name = 'codex_cli:fixture'
                activity = Chat(s).send('pin', {'text': '你好', 'idempotency_key': 'one', 'expected_last_activity_id': None})['activity_id']
                with patch.object(s, 'rows', side_effect=unordered_rows):
                    request, payload = Engine(s).prepare(activity, Model())
                    repeated, _ = Engine(s).prepare(activity, Model())
                self.assertEqual(request['model_config_id'], configured['configuration'])
                self.assertEqual(request['model_version_id'], configured['model_version'])
                self.assertEqual(repeated['id'], request['id'])
            finally: s.close()
