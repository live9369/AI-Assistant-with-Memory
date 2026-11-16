"""Core direction lifecycle using isolated SQLite and a replacement reasoner."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.chat.chat import Chat
from digital_life.application.autonomy.exploration import Exploration
from digital_life.application.autonomy.continuous_exploration import ContinuousExploration
from digital_life.domain.contracts import utc,Forbidden

class Seed:
    name='fixture'
    def generate(self,p):return {'schema_version':1,'action':{'tool':'wait','arguments':{'reason':'reply'}},'explanation':'记录这段经历'}
class Reflect:
    name='fixture'
    def __init__(self,decision='continue',understanding='区分故事设定与外部事实',directions=True):self.inputs=[];self.decision=decision;self.understanding=understanding;self.create=directions
    def generate(self,p):
        self.inputs.append(p);x=p['exploration'];refs=x['allowed_evidence_refs'][:1]
        return {'schema_version':4,'action':{'tool':'wait','arguments':{'reason':'reflect'}},'explanation':'本轮留下一个待确认的理解',
            'reflection':{'directions':[{'title':t,'kind':'reflect','next_step':'比较两种解释','expected_gain':.8,'cost':.1,'evidence_refs':refs} for t in ['怎样区分故事与事实','如何理解对方的关注点']] if self.create else [],
            'decision':self.decision,'understanding':self.understanding,'next_step':'比较新的解释','reason':'推进已有理解','reopen_condition':'收到新的信息','evidence_refs':refs}}
class ContinuousTests(unittest.TestCase):
    def test_provider_citations_are_exact_current_source_choices(self):
        from digital_life.infrastructure.llm.schemas import schema_for
        first='a'*32;second='b'*32
        def packet(ref):return {'output_schema_version':5,'exploration':{'mode':'continuous','allowed_evidence_refs':[ref]}}
        schema=schema_for(packet(first));fields=schema['properties']['reflection']['properties']
        self.assertEqual(fields['evidence_refs']['items']['enum'],[first])
        self.assertEqual(fields['directions']['items']['properties']['evidence_refs']['items']['enum'],[first])
        self.assertEqual(schema_for(packet(second))['properties']['reflection']['properties']['evidence_refs']['items']['enum'],[second])
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'life';self.s=Store.prepare(self.root);(self.root/'WAKE_DISABLED').unlink();self.engine=Engine(self.s);self.offset=0
        Chat(self.s).send('thread',{'text':'这是虚构故事：园丁把水壶放在架子上','idempotency_key':'seed','expected_last_activity_id':None});self.engine.process_one(Seed())
        Exploration(self.s).configure(self.s.config()['controller'],True,12,3,60,mode='continuous')
        from digital_life.application.lifecycle.control_plane import Control
        control=Control(self.root,self.s.instance_id)
        try:control.resume('isolated-fixture-resume')
        finally:control.close()
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def step(self,r):
        self.offset+=61
        with patch('digital_life.application.autonomy.exploration.utc',side_effect=lambda seconds=0:utc(self.offset+seconds)),patch('digital_life.application.autonomy.continuous_exploration.utc',side_effect=lambda seconds=0:utc(self.offset+seconds)),patch('digital_life.application.autonomy.continuous_exploration.secrets.randbits',return_value=0):return self.engine.process_one(r)
    def test_multi_direction_continuation_finish_and_persistence(self):
        r=Reflect();self.step(r);c=ContinuousExploration(Exploration(self.s));self.assertEqual(len(c.directions()),2)
        self.step(Reflect(directions=False));d=list(c.directions().values())[0];self.assertEqual(d['steps'],1);self.assertEqual(d['state'],'ready')
        finish=Reflect(decision='finish',understanding='已形成阶段理解，尚未核实',directions=False);self.step(finish)
        d=c.directions()[d['id']];self.assertEqual(d['state'],'finished')
        self.assertEqual(finish.inputs[0]['context_mode'],'fresh_request');self.assertEqual(finish.inputs[0]['exploration']['direction']['steps'],1)
        self.s.close();self.s=Store(self.root);self.engine=Engine(self.s);self.assertEqual(ContinuousExploration(Exploration(self.s)).directions()[d['id']]['state'],'finished')
        self.assertFalse(ContinuousExploration(Exploration(self.s)).values('step')[-1]['independently_verified'])
    def test_repetition_pauses_and_duplicate_does_not_reopen(self):
        self.step(Reflect());c=ContinuousExploration(Exploration(self.s))
        for _ in range(3):self.step(Reflect(directions=False))
        d=list(c.directions().values())[0];self.assertEqual(d['state'],'paused');self.assertEqual(d['no_progress'],2)
        self.step(Reflect());self.assertEqual(len(c.directions()),2);self.assertEqual(c.directions()[d['id']]['state'],'paused')
    def test_source_revocation_blocks_recall(self):
        r=Reflect();self.step(r);refs=r.inputs[0]['exploration']['allowed_evidence_refs']
        with patch.object(Exploration,'readable_refs',return_value=False):
            with self.assertRaises(Forbidden):ContinuousExploration(Exploration(self.s)).check(r.inputs[0]['activity_id'],r.inputs[0],r.generate(r.inputs[0]))

    def test_wait_has_cooldown_and_probabilities_are_recorded(self):
        x=Exploration(self.s);c=ContinuousExploration(x);cfg=x.config()
        with patch('digital_life.application.autonomy.continuous_exploration.secrets.randbits',return_value=2**53-1):
            self.assertIsNone(c.tick(self.engine,cfg,[]));self.assertIsNone(c.tick(self.engine,cfg,[]))
        self.assertEqual(len(c.values('selection')),1)
        self.assertAlmostEqual(sum(v['probability'] for v in c.values('selection')[0]['candidates']),1)
        self.assertEqual(len(c.values('step')),0)
    def test_tool_uses_existing_approval_and_receipt(self):
        self.step(Reflect());c=ContinuousExploration(Exploration(self.s))
        class Tool(Reflect):
            def generate(self,p):
                v=super().generate(p);v['action']={'tool':'read_file','arguments':{'path':'fact.txt'}};return v
        (self.root/'workspace'/'fact.txt').write_text('observed fixture')
        result=self.step(Tool(directions=False));self.assertIn('approval_id',result)
        d=list(c.directions().values())[0];self.assertEqual(d['state'],'waiting_tool')
        from digital_life.application.accounts.authorization import Policy
        Policy(self.s).approve(result['approval_id'],self.s.config()['controller'])
        outcome=self.engine.execute(result['action_id']);self.assertEqual(outcome['state'],'succeeded')
        self.assertEqual(c.directions()[d['id']]['state'],'ready');self.assertEqual(len(c.values('tool_result')),1)
        self.assertEqual(self.s.row('activities',d['activity'])['state'],'completed')
    def test_branch_and_switch_keep_parent_and_children(self):
        self.step(Reflect());c=ContinuousExploration(Exploration(self.s))
        class Branch(Reflect):
            def generate(self,p):
                v=super().generate(p);v['reflection']['decision']='branch';v['reflection']['directions'][0]['title']='故事信息如何影响一次具体回应';return v
        self.step(Branch());children=[d for d in c.directions().values() if d['parent_id']]
        self.assertEqual(len(children),1)
        self.step(Reflect(decision='switch',directions=False));self.assertTrue(any(d['state']=='ready' for d in c.directions().values()))
        switched=Reflect(directions=False);self.step(switched)
        self.assertNotEqual(switched.inputs[0]['exploration']['direction']['id'],children[0]['parent_id'])

    def test_reopen_requires_new_sources_and_explicit_reason(self):
        self.step(Reflect());self.step(Reflect(decision='finish',directions=False))
        c=ContinuousExploration(Exploration(self.s));d=next(v for v in c.directions().values() if v['state']=='finished')
        with self.assertRaises(Forbidden):c.reopen(d['id'],d['evidence_refs'],'try again',self.s.config()['controller'])
        from digital_life.application.services.memory import Memory
        signal=self.s.db.execute('SELECT id FROM perception_signals ORDER BY rowid LIMIT 1').fetchone()[0]
        with self.s.tx():
            ev=self.s.evidence(object_id=signal,method='fixture-new-information');m=Memory(self.s).encode('新的外部信息',ev)
        reopened=c.reopen(d['id'],[m['revision_id']],'有了新的信息',self.s.config()['controller'])
        self.assertEqual(reopened['state'],'ready');self.assertEqual(reopened['no_progress'],0)

    def test_no_progress_does_not_dispatch_another_tool(self):
        self.step(Reflect());self.step(Reflect(directions=False));self.step(Reflect(directions=False))
        class RepeatTool(Reflect):
            def generate(self,p):
                value=super().generate(p);value['action']={'tool':'read_file','arguments':{'path':'fact.txt'}};return value
        result=self.step(RepeatTool(directions=False))
        self.assertTrue(result['paused']);self.assertEqual(self.s.rows('action_intents'),[])

    def test_v5_step_finish_does_not_finish_direction(self):
        self.step(Reflect())
        class V5(Reflect):
            def generate(self,p):
                v=super().generate(p);v['schema_version']=5
                v['inquiry']={'prediction':'两种解释可能不同','observation':'没有新的工具观察','revision':'目前只是解释，尚需比较','remaining_questions':['哪个解释适合现有经历'],'next_attempts':['比较另一次已有交流'],'direction_status':'finished','finish_basis':'goal_achieved'}
                return v
        result=self.step(V5(decision='finish',directions=False));c=ContinuousExploration(Exploration(self.s))
        d=next(d for d in c.directions().values() if d.get('steps'))
        self.assertEqual(d['state'],'ready');self.assertEqual(d['next_step'],'比较另一次已有交流')
        self.assertEqual(len(c.values('inquiry')),1)

    def test_work_replay_retains_original_products_and_scope(self):
        self.step(Reflect())
        class Product(Reflect):
            def generate(self,p):
                v=super().generate(p);v['explanation']='完整案例：A与B不能混淆，结论仍为模型解释。'
                return v
        self.step(Product(directions=False))
        final=Reflect(decision='finish',directions=False);self.step(final)
        context=final.inputs[0]['exploration'];work=context['work_history']
        self.assertEqual(work['items'][0]['explanation'],'完整案例：A与B不能混淆，结论仍为模型解释。')
        self.assertFalse(work['items'][0]['independently_verified'])
        self.assertTrue(work['items'][0]['source_materials'])
        self.assertEqual(context['scope']['initial_plan'],'比较两种解释')
        self.assertTrue(context['source_guard_refs'])
        self.s.close();self.s=Store(self.root);self.engine=Engine(self.s)
        c=ContinuousExploration(Exploration(self.s));d=next(d for d in c.directions().values() if d['state']=='finished')
        from digital_life.application.autonomy.direction_work import assemble
        self.assertEqual(len(assemble(c,d)['items']),2)

    def test_work_replay_honors_withdrawal_before_send(self):
        self.step(Reflect());reasoner=Reflect(directions=False);self.step(reasoner)
        c=ContinuousExploration(Exploration(self.s));d=next(d for d in c.directions().values() if d.get('steps'))
        payload=reasoner.inputs[0]
        from digital_life.application.autonomy.direction_work import assemble
        work=assemble(c,d);self.assertTrue(work['items'])
        payload['exploration']['source_guard_refs']=work['source_guard_refs']
        ref=work['source_guard_refs'][0];row=self.s.row('memory_revisions',ref)
        from digital_life.application.services.memory import Memory
        Memory(self.s).archive(row['memory_id'],self.s.config()['controller'],'撤回测试来源')
        self.assertEqual(assemble(c,d)['items'],[])
        with self.assertRaises(Forbidden):Exploration(self.s).check_inputs(d['activity'],payload)

    def test_explicit_old_work_is_prioritized_with_bounded_body(self):
        self.step(Reflect())
        class Product(Reflect):
            def generate(self,p):
                v=super().generate(p);v['explanation']=self.understanding+('正文内容'*80)
                v['reflection']['next_step']='继续处理'+self.understanding
                return v
        for i in range(3):self.step(Product(understanding='案例'+str(i),directions=False))
        c=ContinuousExploration(Exploration(self.s));d=next(d for d in c.directions().values() if d.get('steps'))
        from digital_life.application.autonomy.direction_work import assemble
        catalog=assemble(c,d)['catalog'];first=catalog[0]['request']
        cap=max(v['body_bytes'] for v in catalog)+128
        d=dict(d,next_step='回取 work:'+first)
        original=self.s.config
        with patch.object(self.s,'config',side_effect=lambda:{**original(),'model':{'max_input_bytes':cap*3}}):
            work=assemble(c,d)
        self.assertIn(first,[v['request'] for v in work['items']])
        self.assertLessEqual(work['body_bytes'],cap)
        self.assertGreater(work['omitted_count'],0)
