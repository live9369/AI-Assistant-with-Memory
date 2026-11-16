"""T06 contextual action probabilities, main flow and isolated causal controls."""
import argparse
import json
import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
from digital_life.application.behavior.behavior_policy import BehaviorPolicy, sample
from digital_life.application.runtime.engine import Engine
from digital_life.application.services.decisions import Decisions
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.domain.contracts import ContractError, Conflict, Forbidden


class Model:
    name = 'fixture'
    def __init__(self, action=None):
        self.action = action or {'tool':'write_note','arguments':{'path':'answer.txt','text':'done'}}; self.inputs=[]
    def generate(self, payload):
        self.inputs.append(payload)
        return {'schema_version':1,'explanation':'original proposed response','action':self.action}


class BehaviorPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'isolated';self.s=Store.prepare(self.root);self.addCleanup(self.s.close)
        self.engine=Engine(self.s);self.b=BehaviorPolicy(self.s);self.actor=self.s.config()['controller']
    def enable(self, parameters=None, temperature=.7): return self.b.configure(True,self.actor,temperature,parameters)
    def unlock(self):
        (self.root/'WAKE_DISABLED').unlink(missing_ok=True)
        if (self.root/'control.sqlite').exists():
            from digital_life.application.lifecycle.control_plane import Control
            c=Control(self.root,self.s.instance_id);c.resume('isolated-t06');c.close()
    def prepare(self, key='test', model=None):
        a=self.engine.submit(key,key);self.unlock();request,payload=self.engine.prepare(a,model or Model())
        return a,request,payload
    def events(self):
        return [self.s.read_artifact(e['payload_artifact_id']) for e in self.s.rows('runtime_events') if e['event_type']=='behavior_policy.selected']

    def test_disabled_retains_old_actual_action(self):
        a,_,payload=self.prepare();self.assertNotIn('behavior_policy',payload)
        result=self.engine.think(a,Model());self.assertIn('approval_id',result);self.assertEqual(self.events(),[])
        self.assertEqual(self.s.rows('decision_records')[0]['strategy_type'],'deterministic')

    def test_actual_selected_wait_does_not_propose_model_tool(self):
        self.enable({'biases':{'wait':20,'write_note':-20,'ask':-20}})
        a,request,payload=self.prepare();m=Model()
        with patch('digital_life.application.behavior.behavior_policy.secrets.randbits',return_value=2**52):result=self.engine.think(a,m)
        self.assertIn('waiting',result);self.assertEqual(self.s.rows('action_intents'),[])
        decision=self.events()[0];self.assertEqual(decision['candidates'][decision['selected_index']]['action']['tool'],'wait')
        original=self.s.read_artifact(self.s.rows('thought_results')[0]['parsed_artifact_id'])
        self.assertEqual(original['action']['tool'],'write_note');self.assertEqual(self.s.row('activities',a)['state'],'waiting_input')

    def test_actual_selected_ask_does_not_create_tool_approval(self):
        self.enable({'biases':{'ask':20,'write_note':-20,'wait':-20}})
        a,_,_=self.prepare()
        with patch('digital_life.application.behavior.behavior_policy.secrets.randbits',return_value=2**52):self.engine.think(a,Model())
        e=self.events()[0];self.assertEqual(e['candidates'][e['selected_index']]['action']['tool'],'ask');self.assertEqual(self.s.rows('approval_requests'),[])

    def test_real_tool_requires_approval_and_t02_goal_verification(self):
        self.enable({'biases':{'write_note':20,'wait':-20,'ask':-20}})
        from digital_life.application.autonomy.task_loop import TaskLoop
        from digital_life.application.accounts.authorization import Policy
        a=self.engine.submit('write','write');TaskLoop(self.s).configure(a,{'kind':'file_contains','path':'answer.txt','text':'done'},self.actor);self.unlock()
        with patch('digital_life.application.behavior.behavior_policy.secrets.randbits',return_value=0):result=self.engine.process_one(Model())
        with self.assertRaises(Forbidden):self.engine.execute(result['action_id'])
        self.assertFalse((self.root/'workspace/answer.txt').exists())
        Policy(self.s).approve(result['approval_id'],self.actor);self.engine.process_one(Model())
        self.assertEqual(self.s.row('activities',a)['state'],'completed');self.assertEqual((self.root/'workspace/answer.txt').read_text(),'done')

    def test_illegal_path_gets_exact_zero_probability(self):
        self.enable({'biases':{'write_note':20}});a,_,p=self.prepare()
        bad={'tool':'write_note','arguments':{'path':'../escape.txt','text':'no'}}
        result=self.b.evaluate(p,bad,0)
        self.assertFalse(result['candidates'][0]['eligible']);self.assertEqual(result['candidates'][0]['probability'],0)
        self.assertTrue(result['candidates'][0]['blocked_reason']);self.assertNotEqual(result['selected_index'],0)

    def test_policy_scope_exclusion_cannot_be_scored_back_in(self):
        from digital_life.application.accounts.authorization import Policy
        Policy(self.s).mode('authorization',['read_file'],self.actor);self.enable({'biases':{'write_note':20}});_,_,p=self.prepare()
        e=self.b.evaluate(p,Model().action,0);self.assertEqual(e['candidates'][0]['probability'],0)

    def test_distribution_normalized_finite_and_temperature(self):
        self.enable();_,_,p=self.prepare();e=self.b.evaluate(p,Model().action,.5)
        self.assertAlmostEqual(sum(c['probability'] for c in e['candidates']),1)
        for c in e['candidates']:self.assertTrue(math.isfinite(c['score']));self.assertAlmostEqual(c['score'],sum(c['factors'].values()))
        low=Decisions(self.s).distribution([1000,-1000],[True,True],.05)
        high=Decisions(self.s).distribution([1,0],[True,True],5)
        self.assertEqual(low,[1,0]);self.assertLess(high[0],.6)

    def test_sampler_empirical_frequency_and_replay(self):
        r=random.Random(1717);expected=[.1,.3,.6];counts=[0,0,0]
        draws=[r.random() for _ in range(10000)]
        for draw in draws:counts[sample(expected,draw)]+=1
        for count,p in zip(counts,expected):self.assertLess(abs(count/10000-p),.02)
        self.assertEqual([sample(expected,d) for d in draws[:20]],[sample(expected,d) for d in draws[:20]])
        self.assertEqual(sample([0,1,0],0),1);self.assertEqual(sample([0,1,0],.999999),1)

    def test_invalid_sampling_and_configuration(self):
        for draw in (-1,1,True,float('nan'),'x'):
            with self.assertRaises(ContractError):sample([1],draw)
        for probs in ([],[0,0],[.2,.2],[float('nan'),1],[True]):
            with self.assertRaises(ContractError):sample(probs,.5)
        for params in ({'bogus':{}},{'weights':{'wait':{'fiction':1}}},{'biases':{'unknown':0}},{'biases':{'wait':float('nan')}}):
            with self.assertRaises(ContractError):self.enable(params)
        for temp in (0,True,6,float('inf')):
            with self.assertRaises(ContractError):self.enable(temperature=temp)
        with self.assertRaises(Forbidden):self.b.configure(True,'model')

    def test_configure_requires_stopped_and_never_wakes(self):
        self.enable();self.assertTrue((self.root/'WAKE_DISABLED').exists());self.unlock()
        with self.assertRaises(Conflict):self.enable()

    def test_superseded_configuration_prevents_model_call(self):
        self.enable();a,_,_=self.prepare();m=Model()
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.root,self.s.instance_id);c.stop('isolated');c.close();self.b.configure(False,self.actor)
        c=Control(self.root,self.s.instance_id);c.resume('isolated');c.close()
        with self.assertRaises(Forbidden):self.engine.think(a,m)
        self.assertEqual(m.inputs,[])

    def test_change_during_generation_cannot_accept_or_select(self):
        self.enable();a,_,_=self.prepare();outer=self
        class ChangedModel(Model):
            def generate(self,payload):
                cfg=outer.b.config();cfg.pop('event_id');cfg['enabled']=False
                with outer.s.tx():outer.s.event('behavior_policy.configured',payload=cfg,lane='control')
                return super().generate(payload)
        result=self.engine.think(a,ChangedModel());self.assertFalse(result['accepted']);self.assertEqual(self.events(),[])

    def test_feature_coverage_and_missing_are_explicit(self):
        self.enable();_,_,p=self.prepare();f=p['behavior_policy']['features']
        self.assertEqual(sum(k.startswith('personality.') for k in f),5)
        self.assertEqual(sum(k.startswith('value.') for k in f),4)
        for key in ('cognition.uncertainty','relationship.reliability','motivation.intensity','state.load'):
            self.assertTrue(f[key]['missing']);self.assertEqual(f[key]['value'],0)
        self.assertEqual(f['memory.coverage']['refs'],[]);self.assertEqual(f['memory.coverage']['value'],0);self.assertFalse(f['memory.coverage']['missing'])

    def test_controlled_each_feature_changes_configured_score(self):
        features=['personality.openness','value.accuracy','cognition.uncertainty','memory.coverage','relationship.reliability','motivation.intensity','state.load','context.chat']
        self.enable({'weights':{'write_note':{key:2 for key in features}}});_,_,p=self.prepare()
        baseline=self.b.evaluate(p,Model().action,.5)['candidates'][0]['probability']
        for key in features:
            edited=json.loads(json.dumps(p));edited['behavior_policy']['features'][key]['value']+=.2
            self.assertGreater(self.b.evaluate(edited,Model().action,.5)['candidates'][0]['probability'],baseline,key)

    def test_matching_real_habit_changes_candidate_probability(self):
        from digital_life.application.services.habits import Habits
        from digital_life.application.services.goals import Goals
        action=Model().action;association=Habits(self.s).create(action,Goals(self.s).rule())
        self.enable();_,_,p=self.prepare();before=self.b.evaluate(p,action,.5)['candidates'][0]['probability']
        evidence=self.s.evidence(artifact=self.s.artifact({'fixture':'habit'}));Habits(self.s).update(association,1,evidence,self.actor,rate=1)
        a=self.engine.submit('second','second');_,after=self.engine.prepare(a,Model())
        self.assertGreater(self.b.evaluate(after,action,.5)['candidates'][0]['probability'],before)

    def test_real_trust_is_conditional_and_has_reference(self):
        from digital_life.application.services.relationships import Relationships
        evidence=self.s.evidence(artifact=self.s.artifact({'fixture':'trust'}))
        wrong=Relationships(self.s).assess_trust(self.actor,'other-domain','reliability',1,evidence)
        self.enable();_,_,p=self.prepare();self.assertTrue(p['behavior_policy']['features']['relationship.reliability']['missing'])
        ref=Relationships(self.s).assess_trust(self.actor,'behavior','reliability',.8,evidence)
        a=self.engine.submit('next','next');_,p=self.engine.prepare(a,Model());f=p['behavior_policy']['features']['relationship.reliability']
        self.assertEqual(f['value'],.8);self.assertEqual(f['refs'],[ref]);self.assertNotIn(wrong,f['refs'])

    def test_duplicate_does_not_redraw(self):
        self.enable();a,_,_=self.prepare()
        with patch('digital_life.application.behavior.behavior_policy.secrets.randbits',return_value=0) as rng:
            self.engine.think(a,Model());self.engine.think(a,Model());self.assertEqual(rng.call_count,1)
        self.assertEqual(len(self.events()),1)

    def test_reopen_preserves_distribution_draw_and_inspection(self):
        self.enable();a,request,_=self.prepare()
        with patch('digital_life.application.behavior.behavior_policy.secrets.randbits',return_value=2**52):self.engine.think(a,Model())
        event=self.events()[0];identity=self.s.instance_id;self.s.close();self.s=Store(self.root);self.addCleanup(self.s.close)
        self.assertEqual(self.s.instance_id,identity)
        from digital_life.application.monitoring.thought_inspection import ThoughtInspection
        detail=ThoughtInspection(self.s).detail(request['id']);actual=detail['behavior_decisions'][0]['value']
        self.assertEqual(actual,event);self.assertEqual(sample([c['probability'] for c in actual['candidates']],actual['seed']/2**53),actual['selected_index'])
        self.assertEqual(self.s.integrity()['foreign_keys'],[])

    def test_wait_and_ask_candidates_not_duplicated(self):
        self.assertEqual([c['tool'] for c in self.b.candidates({'tool':'wait','arguments':{'reason':'specific'}})],['wait','ask'])
        self.assertEqual([c['tool'] for c in self.b.candidates({'tool':'ask','arguments':{'reason':'specific'}})],['ask','wait'])

    def test_cli_status_pure_and_configuration_locked(self):
        from digital_life.entrypoints.growth import parsers,handle
        parser=argparse.ArgumentParser();parsers(parser.add_subparsers(dest='command'))
        handle(self.s,parser.parse_args(['behavior-policy','enable']))
        before=len(self.s.rows('runtime_events'));status=handle(self.s,parser.parse_args(['behavior-policy','status']))
        self.assertFalse(status['inference_started']);self.assertEqual(len(self.s.rows('runtime_events')),before);self.assertTrue((self.root/'WAKE_DISABLED').exists())

    def test_real_personality_and_value_profiles_change_probabilities(self):
        from digital_life.application.services.personality import Personality
        from digital_life.application.services.values import Values
        self.enable();_,_,p=self.prepare();before=self.b.evaluate(p,Model().action,.5)['candidates'][0]['probability']
        evidence=[self.s.evidence(artifact=self.s.artifact({'fixture':i})) for i in range(2)]
        Personality(self.s).replace({'conscientiousness':.9},evidence,self.actor)
        a=self.engine.submit('next','next');_,p=self.engine.prepare(a,Model());middle=self.b.evaluate(p,Model().action,.5)['candidates'][0]['probability']
        self.assertGreater(middle,before)
        dims=self.s.rows('value_dimensions');Values(self.s).replace({d['id']:int(d['definition']=='continuity') for d in dims},evidence,self.actor)
        a=self.engine.submit('third','third');_,p=self.engine.prepare(a,Model());after=self.b.evaluate(p,Model().action,.5)['candidates'][0]['probability']
        self.assertGreater(after,middle)

    def test_withdrawn_memory_blocks_dispatch(self):
        from digital_life.application.services.memory import Memory
        ev=self.s.evidence(artifact=self.s.artifact({'source':'fixture'}));memory=Memory(self.s).encode('test prior episode',ev)
        self.enable();a,_,p=self.prepare();self.assertIn(memory['revision_id'],p['behavior_policy']['features']['memory.coverage']['refs'])
        Memory(self.s).restrict(memory['memory_id'],[self.actor],self.actor);model=Model()
        with self.assertRaises(Forbidden):self.engine.think(a,model)
        self.assertFalse(model.inputs);self.assertFalse(self.events())

    def test_memory_privacy_policy_does_not_replace_active_tool_scope(self):
        from digital_life.application.services.memory import Memory
        ev=self.s.evidence(artifact=self.s.artifact({'source':'fixture'}));memory=Memory(self.s).encode('test prior episode',ev)
        Memory(self.s).restrict(memory['memory_id'],[self.actor,self.s.config()['self_actor']],self.actor)
        self.enable();_,_,p=self.prepare();self.assertTrue(self.b.evaluate(p,Model().action,.5)['candidates'][0]['eligible'])

    def test_t05_motivation_and_fresh_load_feed_actual_context(self):
        from digital_life.application.behavior.goal_regulation import GoalRegulation
        GoalRegulation(self.s).configure(True,self.actor);self.enable();_,_,p=self.prepare()
        for key in ('motivation.intensity','state.load'):
            self.assertFalse(p['behavior_policy']['features'][key]['missing']);self.assertTrue(p['behavior_policy']['features'][key]['refs'])
        self.assertEqual(p['behavior_policy']['features']['motivation.intensity']['value'],p['goal_regulation']['intensity'])

    def test_v2_exploration_explicitly_retains_dedicated_selection(self):
        from evaluation.exploration.harness import Harness
        case=json.loads((Path(__file__).resolve().parents[1]/'evaluation/exploration/materials/cases-v1.json').read_text())['cases'][0]
        h=Harness(Path(self.tmp.name)/'exploration',case)
        try:
            BehaviorPolicy(h.s).configure(True,h.s.config()['controller'])
            activity=h.discovery()
            self.assertTrue(h.model.inputs[0]['behavior_policy']['bypass'])
            self.assertFalse(any(e['event_type']=='behavior_policy.selected' for e in h.s.rows('runtime_events')))
        finally:h.close()

    def test_real_cognitive_snapshot_uncertainty_has_source_refs(self):
        from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
        CognitiveUpdates(self.s).configure(True,self.actor);self.enable()
        a=self.engine.submit('陈明是植物学家','belief');self.unlock()
        class CognitiveModel(Model):
            def generate(self,p):
                return {'schema_version':3,'explanation':'noted','action':{'tool':'wait','arguments':{'reason':'wait'}},'cognition':{'claims':[{'subject':'陈明','predicate':'职业','value':'植物学家','source_ref':next(iter(p['cognition_sources'])),'quote':'陈明是植物学家','kind':'reported'}],'questions':[],'predictions':[],'plan':[]}}
        self.engine.think(a,CognitiveModel());a=self.engine.submit('followup','followup');_,p=self.engine.prepare(a,CognitiveModel())
        f=p['behavior_policy']['features']['cognition.uncertainty'];self.assertFalse(f['missing']);self.assertEqual(f['value'],1);self.assertTrue(f['refs'])

    def test_shipped_configuration_example_is_accepted_without_wake(self):
        root=Path(__file__).resolve().parents[1]
        parameters=json.loads((root/'config/examples/behavior-policy.json').read_text())
        config=self.enable(parameters);self.assertTrue(config['enabled']);self.assertTrue((self.root/'WAKE_DISABLED').exists())
