"""Resource reuse must reduce I/O without merging distinct claims or hiding changes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import utc,Forbidden
from digital_life.application.autonomy.exploration_evidence import ExplorationEvidence
from digital_life.application.services.memory import Memory
from evaluation.exploration.harness import Harness

ROOT=Path(__file__).resolve().parents[1]
class ExplorationReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();data=json.loads((ROOT/'evaluation/exploration/materials/cases-v1.json').read_text());self.h=Harness(Path(self.tmp.name)/'instance',data['cases'][10]);self.x=self.h.x;self.ev=ExplorationEvidence(self.x)
    def tearDown(self):self.h.close();self.tmp.cleanup()
    def run_first(self):
        a=self.h.investigation();self.h.finish(a);return a
    def new_problem(self):
        original=next(iter(self.x.questions().values()))
        with self.h.s.tx():self.x.record(dict(original,id='different-question',question='Which fields exist in the local file?',state='candidate',visits=0,assessment='Not evaluated.',activity=None))
        with patch('digital_life.application.autonomy.exploration.utc',side_effect=lambda seconds=0:utc(7200+seconds)):return self.x.tick(self.h.engine)
    def test_admit_only_concrete_tool_paths(self):
        path=self.h.case['public']['observation_path']
        self.assertEqual(self.ev.plan('Read '+path)[0]['tool'],'read_file')
        for text in ('Retrieve original records by event/evidence/result ID','Read ../../runtime.sqlite','Read /etc/passwd','Search the web for a receipt'):
            self.assertEqual(self.ev.plan(text),[])
        self.assertEqual(self.ev.plan('列举 notes 目录')[0]['tool'],'list_files')
    def test_shared_receipt_across_different_questions(self):
        self.run_first();a=self.new_problem();_,payload=self.h.engine.prepare(a,self.h.model)
        self.assertTrue(payload['exploration']['observations']);self.assertTrue(payload['exploration']['known_questions'])
        before=self.h.tool_calls if hasattr(self.h,'tool_calls') else len(self.h.s.rows('action_attempts'))
        self.h.propose(a)
        self.assertEqual(len(self.h.s.rows('action_attempts')),before)
        self.assertEqual(self.h.s.row('activities',a)['state'],'completed')
    def test_cache_cannot_survive_file_change_or_source_withdrawal(self):
        self.run_first();self.assertEqual(len(self.ev.current()),1)
        path=self.h.root/'workspace'/self.h.case['public']['observation_path'];path.write_text('changed and longer')
        self.assertEqual(self.ev.current(),[])
    def test_changed_receipt_is_historical_and_cannot_resolve(self):
        a=self.run_first();(self.h.root/'workspace'/self.h.case['public']['observation_path']).write_text('Changed new revision.')
        ctx=self.x.context(a)
        self.assertEqual(ctx['observations'],[])
        self.assertTrue(ctx['historical_observations'])
    def test_directory_membership_invalidates_receipt(self):
        action={'tool':'list_files','arguments':{'path':'notes'}};before=self.ev.signature(action)
        (self.h.root/'workspace/notes/new-entry.txt').write_text('new')
        self.assertNotEqual(self.ev.signature(action),before)
    def test_source_permission_withdrawal_blocks_reuse(self):
        self.run_first();Memory(self.h.s).restrict(self.h.memory['memory_id'],[self.h.s.config()['controller']],self.h.s.config()['controller'])
        self.assertEqual(self.ev.current(),[])
    def test_prepared_shared_context_invalidates_on_change(self):
        self.run_first();a=self.new_problem();_,payload=self.h.engine.prepare(a,self.h.model)
        (self.h.root/'workspace'/self.h.case['public']['observation_path']).write_text('new longer version')
        with self.assertRaises(Forbidden):self.x.check_inputs(a,payload)
    def test_unchanged_action_uses_receipt_without_dispatch(self):
        self.run_first();a=self.new_problem();self.h.model.always_continue=True
        count=len(self.h.s.rows('action_attempts'));result=self.h.propose(a)
        self.assertTrue(result['evidence_reused']);self.assertEqual(len(self.h.s.rows('action_attempts')),count)
        self.assertTrue(self.x.observations(a)[0]['reused'])
        self.h.propose(a);self.assertEqual(self.h.s.row('activities',a)['state'],'paused')
    def test_near_duplicates_merge_but_distinct_claim_is_kept(self):
        q={'id':'q','question':'更多测量中的相邻回声是否始终相隔两个 tick？','verification':'Read '+self.h.case['public']['observation_path']}
        plans=self.ev.plan(q['verification'])
        self.assertEqual(self.ev.duplicate(dict(q,question='更多测量中的所有相邻回声是否都相隔两个 tick？'),plans,{'q':q}),'q')
        self.assertIsNone(self.ev.duplicate(dict(q,question='是否包含蓝色之外的颜色？'),plans,{'q':q}))
    def test_unstable_or_failed_receipt_is_not_published(self):
        a=self.h.investigation();p=self.h.propose(a)
        from digital_life.domain.contracts import ToolResult
        self.h.tool_outcome=ToolResult('received','failed','fail');self.h.execute(p)
        self.assertEqual(self.ev.current(),[])

if __name__=='__main__':unittest.main()
