"""T08 temporary cue-response learning with verified records and reviewed feedback."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,ToolResult,identifier
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.behavior.habit_learning import HabitLearning
from digital_life.application.behavior.behavior_policy import BehaviorPolicy
from digital_life.application.services.habits import Habits


ACTION={'tool':'wait','arguments':{'reason':'observed pause'}}
class Model:
    name='fixture'
    def __init__(self,action=None):self.action=action or ACTION;self.inputs=[]
    def generate(self,p):self.inputs.append(p);return {'schema_version':1,'explanation':'recorded fixture action','action':self.action}


class HabitLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'isolated'
        self.s=Store.prepare(self.root);self.addCleanup(self.s.close);self.e=Engine(self.s);self.h=HabitLearning(self.s);self.actor=self.s.config()['controller'];self.counter=0
    def enable(self):self.h.configure(True,self.actor)
    def enroll(self,action=None):
        self.enable();return self.h.enroll(action or ACTION,{'source':'user','task_contains':'review'},'review-habit',self.actor)['association']
    def unlock(self):
        (self.root/'WAKE_DISABLED').unlink(missing_ok=True)
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.root,self.s.instance_id);c.resume('isolated-t08-'+identifier());c.close()
    def episode(self,association,outcome=None,action=None,task='review task',source='user'):
        self.counter+=1;key='episode-'+str(self.counter);a=self.e.submit(task,key,source);self.unlock();m=Model(action)
        with patch('digital_life.application.behavior.behavior_policy.secrets.randbits',return_value=0):self.e.think(a,m)
        records=[o for o in self.h.events('observed') if o['activity']==a and o['association']==association]
        if outcome is not None:
            self.assertEqual(len(records),1)
            changed=self.h.feedback(records[0]['id'],outcome,'controller assessed reinforcement',key,self.h.snapshot(association)['revision'],self.actor)
            return changed,m.inputs[0]
        return records,m.inputs[0]
    def form(self,association):
        for _ in range(3):self.episode(association,1)
        return self.h.snapshot(association)
    def evidence(self):return [self.s.evidence(object_id=self.s.event('controller.habit-review',payload={'case':i})) for i in range(2)]

    def test_default_off_and_legacy_compatibility(self):
        from digital_life.application.services.goals import Goals
        association=Habits(self.s).create(ACTION,Goals(self.s).rule());ev=self.s.evidence(artifact=self.s.artifact({'fixture':True}))
        self.assertAlmostEqual(Habits(self.s).update(association,1,ev,self.actor),.1)
        a=self.e.submit('review','legacy');self.unlock();_,p=self.e.prepare(a,Model())
        self.assertNotIn('habit_learning',p);self.assertEqual(len(p['habit_suggestions']),1)

    def test_formation_needs_three_distinct_reviewed_episodes(self):
        a=self.enroll();_,p=self.episode(a,1);self.assertEqual(self.h.snapshot(a)['state'],'learning');self.assertFalse(p['habit_suggestions'])
        self.episode(a,1);self.assertEqual(self.h.snapshot(a)['state'],'learning')
        self.episode(a,1);state=self.h.snapshot(a);self.assertEqual(state['state'],'active');self.assertAlmostEqual(state['expression'],.3)
        _,p=self.episode(a);self.assertEqual(len(p['habit_suggestions']),1);self.assertGreater(p['habit_suggestions'][0]['strength'],0)

    def test_no_feedback_does_not_automatically_reinforce(self):
        a=self.enroll()
        for _ in range(4):self.episode(a)
        self.assertEqual(self.h.snapshot(a)['acquisition'],0);self.assertEqual(self.h.snapshot(a)['state'],'learning')

    def test_cue_is_specific_to_source_and_task(self):
        a=self.enroll();self.form(a)
        records,p=self.episode(a,task='unrelated');self.assertFalse(records);self.assertFalse(p['habit_suggestions'])
        records,p=self.episode(a,source='evaluation');self.assertFalse(records);self.assertFalse(p['habit_suggestions'])
        records,p=self.episode(a);self.assertEqual(len(records),1);self.assertEqual(len(p['habit_suggestions']),1)

    def test_extinction_preserves_acquisition_and_history(self):
        a=self.enroll();self.form(a);acquired=self.h.snapshot(a)['acquisition']
        for _ in range(9):self.episode(a,0)
        state=self.h.snapshot(a);self.assertEqual(state['state'],'extinct');self.assertEqual(state['expression'],0)
        self.assertEqual(state['acquisition'],acquired);self.assertGreater(state['inhibition'],.8)
        _,p=self.episode(a);self.assertFalse(p['habit_suggestions']);self.assertTrue(p['habit_learning']['opportunities'])
        self.assertGreater(len(self.h.events('changed')),3)

    def test_reacquisition_uses_new_experiences_without_erasing_old(self):
        a=self.enroll();self.form(a)
        for _ in range(9):self.episode(a,0)
        old=len(self.h.snapshot(a)['consumed_activities'])
        for _ in range(6):self.episode(a,1)
        state=self.h.snapshot(a);self.assertEqual(state['state'],'active');self.assertGreater(state['expression'],.3)
        self.assertEqual(len(state['consumed_activities']),old+6);self.assertGreater(state['inhibition'],0)

    def test_inhibit_is_immediate_retains_traces_and_resume_is_explicit(self):
        a=self.enroll();state=self.form(a)
        inhibited=self.h.control(a,'inhibit','controller stop habit influence',state['revision'],self.actor)
        self.assertEqual(inhibited['expression'],0);self.assertEqual(inhibited['acquisition'],state['acquisition'])
        records,p=self.episode(a);self.assertFalse(p['habit_suggestions']);self.assertTrue(records)
        with self.assertRaises(Forbidden):self.h.feedback(records[0]['id'],1,'not allowed','blocked',inhibited['revision'],self.actor)
        resumed=self.h.control(a,'resume','reviewed',inhibited['revision'],self.actor);self.assertEqual(resumed['state'],'active')

    def test_inhibition_after_prepare_blocks_model_dispatch(self):
        a=self.enroll();self.form(a);activity=self.e.submit('review prepared','prepared');_,p=self.e.prepare(activity,Model())
        self.h.control(a,'inhibit','changed',self.h.snapshot(a)['revision'],self.actor);model=Model()
        with self.assertRaises(Forbidden):self.e.think(activity,model)
        self.assertFalse(model.inputs)

    def test_change_during_generation_blocks_acceptance(self):
        a=self.enroll();self.form(a);activity=self.e.submit('review change','change');outer=self
        class Changed(Model):
            def generate(self,p):
                outer.h.control(a,'inhibit','during generation',outer.h.snapshot(a)['revision'],outer.actor)
                return super().generate(p)
        result=self.e.think(activity,Changed());self.assertFalse(result['accepted'])

    def test_feedback_idempotent_cas_and_no_duplicate_episode(self):
        a=self.enroll();records,_=self.episode(a);ref=records[0]['id'];revision=self.h.snapshot(a)['revision']
        first=self.h.feedback(ref,1,'same','feedback-key',revision,self.actor)
        again=self.h.feedback(ref,1,'same','feedback-key',revision,self.actor);self.assertEqual(first['id'],again['id'])
        with self.assertRaises(Conflict):self.h.feedback(ref,0,'same','feedback-key',revision,self.actor)
        with self.assertRaises(Conflict):self.h.feedback(ref,1,'same','new-key',self.h.snapshot(a)['revision'],self.actor)
        self.assertAlmostEqual(self.h.snapshot(a)['acquisition'],.1)

    def test_selected_alternative_only_allows_negative_feedback(self):
        a=self.enroll();other={'tool':'ask','arguments':{'reason':'different response'}}
        records,_=self.episode(a,action=other);self.assertFalse(records[0]['matched']);revision=self.h.snapshot(a)['revision']
        with self.assertRaises(ContractError):self.h.feedback(records[0]['id'],1,'not performed','bad',revision,self.actor)
        self.h.feedback(records[0]['id'],0,'no longer reinforce old response','good',revision,self.actor)
        self.assertGreater(self.h.snapshot(a)['inhibition'],0)

    def test_t06_probability_increases_after_formation_and_zeroes_when_inhibited(self):
        a=self.enroll();b=BehaviorPolicy(self.s);b.configure(True,self.actor)
        self.unlock();activity=self.e.submit('review baseline','baseline');_,p=self.e.prepare(activity,Model())
        before=b.evaluate(p,ACTION,.5)['candidates'][0]['probability']
        self.form(a);activity=self.e.submit('review formed','formed');_,p=self.e.prepare(activity,Model())
        after=b.evaluate(p,ACTION,.5)['candidates'][0]['probability'];self.assertGreater(after,before)
        self.h.control(a,'inhibit','review',self.h.snapshot(a)['revision'],self.actor)
        activity=self.e.submit('review inhibited','inhibited');_,p=self.e.prepare(activity,Model());evaluation=b.evaluate(p,ACTION,.5)
        self.assertEqual(evaluation['candidates'][0]['features']['habit'],0);self.assertFalse(p['habit_suggestions'])

    def test_legacy_update_cannot_bypass_managed_feedback(self):
        a=self.enroll();ev=self.s.evidence(artifact=self.s.artifact({'fixture':True}))
        with self.assertRaises(Forbidden):Habits(self.s).update(a,1,ev,self.actor,rate=1)
        self.assertEqual(self.h.snapshot(a)['acquisition'],0)

    def test_direct_cache_tampering_detected(self):
        a=self.enroll();self.s.db.execute('UPDATE habit_associations SET strength=.9 WHERE id=?',(a,))
        with self.assertRaises(Conflict):self.h.snapshot(a)

    def test_enrollment_validation_dedup_and_permissions(self):
        self.enable();cue={'source':'user','task_contains':'review'};state=self.h.enroll(ACTION,cue,'one',self.actor)
        self.assertEqual(self.h.enroll(ACTION,cue,'one',self.actor)['revision'],state['revision'])
        with self.assertRaises(Conflict):self.h.enroll(ACTION,cue,'two',self.actor)
        with self.assertRaises(ContractError):self.h.enroll(ACTION,{'source':'user','task_contains':''},'bad',self.actor)
        with self.assertRaises(ContractError):self.h.enroll(ACTION,{'source':'user','task_contains':'r','script':'x'},'bad',self.actor)
        with self.assertRaises(Forbidden):self.h.enroll(ACTION,cue,'bad','model')
        with self.assertRaises(Forbidden):self.h.enroll({'tool':'write_note','arguments':{'path':'../escape','text':'bad'}},cue,'bad',self.actor)

    def test_verified_tool_only_after_approval_and_receipt(self):
        from digital_life.application.accounts.authorization import Policy
        action={'tool':'write_note','arguments':{'path':'review.txt','text':'done'}};a=self.enroll(action)
        activity=self.e.submit('review file','write');self.unlock();result=self.e.think(activity,Model(action));self.assertFalse(self.h.events('observed'))
        with self.assertRaises(Forbidden):self.e.execute(result['action_id'])
        Policy(self.s).approve(result['approval_id'],self.actor);outcome=self.e.execute(result['action_id'])
        source=self.h.events('observed')[0];self.assertTrue(source['matched']);self.assertEqual(source['result'],outcome['result'])
        self.h.record_tool(result['action_id'],outcome);self.assertEqual(len(self.h.events('observed')),1)
        self.assertEqual(self.s.rows('habit_opportunities')[0]['action_taken'],1);self.assertEqual(self.s.rows('habit_opportunities')[0]['control_mode'],'unknown')
        self.assertEqual(self.s.integrity()['foreign_keys'],[])

    def test_unknown_tool_outcome_not_negative_evidence(self):
        from digital_life.application.accounts.authorization import Policy
        action={'tool':'write_note','arguments':{'path':'review.txt','text':'done'}};a=self.enroll(action)
        activity=self.e.submit('review unknown','unknown');self.unlock();result=self.e.think(activity,Model(action));Policy(self.s).approve(result['approval_id'],self.actor)
        self.e.execute(result['action_id'],backend=lambda *args:ToolResult('received','unknown','unknown',{'fixture':'unknown'}))
        self.assertFalse(self.h.events('observed'));self.assertEqual(self.h.snapshot(a)['inhibition'],0)

    def test_compensation_preserves_consumption_and_rejects_intervening_state(self):
        a=self.enroll();changed,_=self.episode(a,1);self.h.rollback(changed['id'],self.evidence(),self.actor)
        state=self.h.snapshot(a);self.assertEqual(state['acquisition'],0);self.assertEqual(len(state['consumed_activities']),1)
        with self.assertRaises(Conflict):self.h.feedback(changed['observation'],1,'again','again',state['revision'],self.actor)
        with self.assertRaises(Conflict):self.h.rollback(changed['id'],self.evidence(),self.actor)
        changed,_=self.episode(a,1);self.h.control(a,'inhibit','later',self.h.snapshot(a)['revision'],self.actor)
        with self.assertRaises(Conflict):self.h.rollback(changed['id'],self.evidence(),self.actor)

    def test_source_erasure_prevents_feedback(self):
        a=self.enroll();records,_=self.episode(a);request=self.s.row('thought_requests',records[0]['request'])
        ref=self.s.artifact({'redacted_by':'controller'});self.s.db.execute('UPDATE thought_requests SET request_artifact_id=? WHERE id=?',(ref,request['id']))
        with self.assertRaises(Forbidden):self.h.feedback(records[0]['id'],1,'erased','erased',self.h.snapshot(a)['revision'],self.actor)

    def test_disabled_managed_habit_does_not_fall_back_to_legacy(self):
        a=self.enroll();self.form(a)
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.root,self.s.instance_id);c.stop('test');c.close();self.h.configure(False,self.actor)
        records,p=self.episode(a);self.assertFalse(p['habit_suggestions']);self.assertNotIn('habit_learning',p)
        self.assertFalse(records);self.assertGreater(self.h.snapshot(a)['acquisition'],0)

    def test_legacy_inhibited_and_extinct_not_suggested(self):
        from digital_life.application.services.goals import Goals
        a=Habits(self.s).create(ACTION,Goals(self.s).rule());row=self.s.row('habit_associations',a);activity=self.e.submit('review legacy','legacy')
        for state in ('inhibited','extinct'):
            self.s.db.execute('UPDATE habit_items SET state=? WHERE id=?',(state,row['habit_id']))
            self.assertFalse(Habits(self.s).opportunities(activity,{}))

    def test_reopen_preserves_identity_memories_traces_and_old_request(self):
        a=self.enroll();records,p=self.episode(a,1);identity=self.s.instance_id;memories=len(self.s.rows('memory_revisions'));request=self.s.rows('thought_requests')[0]
        self.s.close();self.s=Store(self.root);self.addCleanup(self.s.close);self.h=HabitLearning(self.s)
        self.assertEqual(self.s.instance_id,identity);self.assertEqual(len(self.s.rows('memory_revisions')),memories)
        self.assertAlmostEqual(self.h.snapshot(a)['acquisition'],.1);self.assertEqual(self.s.read_artifact(request['request_artifact_id']),p)
        self.assertEqual(self.s.integrity()['foreign_keys'],[])

    def test_cli_status_is_pure_and_enable_does_not_wake(self):
        from digital_life.entrypoints.growth import parsers,handle
        parser=argparse.ArgumentParser();parsers(parser.add_subparsers(dest='command'))
        handle(self.s,parser.parse_args(['habit-learning','enable']));before=len(self.s.rows('runtime_events'))
        result=handle(self.s,parser.parse_args(['habit-learning','status']))
        self.assertFalse(result['inference_started']);self.assertEqual(len(self.s.rows('runtime_events')),before);self.assertTrue((self.root/'WAKE_DISABLED').exists())
        self.unlock()
        with self.assertRaises(Conflict):self.enable()

    def test_multiple_rounds_same_activity_cannot_repeat_reinforcement(self):
        from digital_life.application.autonomy.task_loop import TaskLoop
        a=self.enroll();activity=self.e.submit('review rounds','rounds');loop=TaskLoop(self.s)
        loop.configure(activity,{'kind':'file_contains','path':'missing.txt','text':'done'},self.actor,max_rounds=3);self.unlock();self.e.think(activity,Model())
        first=self.h.events('observed')[-1];self.h.feedback(first['id'],1,'first','first',self.h.snapshot(a)['revision'],self.actor)
        loop.resume(self.e,activity,'review again',self.actor);self.e.think(activity,Model());second=self.h.events('observed')[-1]
        self.assertNotEqual(first['id'],second['id'])
        with self.assertRaises(Conflict):self.h.feedback(second['id'],1,'second','second',self.h.snapshot(a)['revision'],self.actor)

    def test_strong_habit_does_not_override_policy_exclusion(self):
        from digital_life.application.accounts.authorization import Policy
        action={'tool':'write_note','arguments':{'path':'review.txt','text':'done'}};a=self.enroll(action)
        # Use real verified actions and feedback to form the tool habit.
        self.unlock()
        for i in range(3):
            activity=self.e.submit('review file','tool-'+str(i));proposal=self.e.think(activity,Model(action))
            Policy(self.s).approve(proposal['approval_id'],self.actor);self.e.execute(proposal['action_id'])
            record=self.h.events('observed')[-1];self.h.feedback(record['id'],1,'desired','tool-feedback-'+str(i),self.h.snapshot(a)['revision'],self.actor)
        self.assertEqual(self.h.snapshot(a)['state'],'active')
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.root,self.s.instance_id);c.stop('configure');c.close();BehaviorPolicy(self.s).configure(True,self.actor)
        Policy(self.s).mode('authorization',['read_file'],self.actor);self.unlock();activity=self.e.submit('review excluded','excluded');_,p=self.e.prepare(activity,Model(action))
        evaluation=BehaviorPolicy(self.s).evaluate(p,action,0)
        self.assertGreater(evaluation['candidates'][0]['features']['habit'],0)
        self.assertFalse(evaluation['candidates'][0]['eligible']);self.assertEqual(evaluation['candidates'][0]['probability'],0)

    def test_feedback_changes_make_earlier_unaccepted_request_stale(self):
        a=self.enroll();records,_=self.episode(a);activity=self.e.submit('review prepared','prepared');self.e.prepare(activity,Model())
        self.h.feedback(records[0]['id'],1,'new information','new',self.h.snapshot(a)['revision'],self.actor)
        model=Model()
        with self.assertRaises(Forbidden):self.e.think(activity,model)
        self.assertFalse(model.inputs)

    def test_configuration_change_rejects_prepared_input(self):
        a=self.enroll();self.unlock();activity=self.e.submit('review old config','old');self.e.prepare(activity,Model())
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.root,self.s.instance_id);c.stop('disable');c.close();self.h.configure(False,self.actor);self.unlock();m=Model()
        with self.assertRaises(Forbidden):self.e.think(activity,m)
        self.assertFalse(m.inputs)

    def test_erased_tool_receipt_is_not_learning_evidence(self):
        from digital_life.application.accounts.authorization import Policy
        action={'tool':'write_note','arguments':{'path':'review.txt','text':'done'}};a=self.enroll(action);activity=self.e.submit('review receipt','receipt');self.unlock()
        proposal=self.e.think(activity,Model(action));Policy(self.s).approve(proposal['approval_id'],self.actor);self.e.execute(proposal['action_id'])
        record=self.h.events('observed')[-1];artifact=self.s.artifact({'redacted_by':'controller'})
        self.s.db.execute('UPDATE action_results SET receipt_artifact_id=? WHERE id=?',(artifact,record['result']))
        with self.assertRaises(Forbidden):self.h.feedback(record['id'],1,'withdrawn','withdrawn',self.h.snapshot(a)['revision'],self.actor)

    def test_compensation_rejects_two_evidence_wrappers_for_one_origin(self):
        a=self.enroll();changed,_=self.episode(a,1);origin=self.s.event('controller.review',payload={'same':'source'});refs=[self.s.evidence(object_id=origin) for _ in range(2)]
        with self.assertRaises(ContractError):self.h.rollback(changed['id'],refs,self.actor)

    def test_legacy_cannot_tamper_with_inhibitory_cache(self):
        a=self.enroll();self.episode(a,1)
        self.s.db.execute('UPDATE habit_associations SET uncertainty_json=? WHERE id=?',(json.dumps({'method':'context-habit-v1','inhibition':1}),a))
        with self.assertRaises(Conflict):self.h.snapshot(a)

    def test_inhibited_tool_can_still_be_explicit_goal_directed_action(self):
        from digital_life.application.accounts.authorization import Policy
        action={'tool':'write_note','arguments':{'path':'review.txt','text':'done'}};a=self.enroll(action)
        self.h.control(a,'inhibit','disable bias',self.h.snapshot(a)['revision'],self.actor)
        activity=self.e.submit('review explicit action','explicit');self.unlock();m=Model(action);proposal=self.e.think(activity,m)
        self.assertFalse(m.inputs[0]['habit_suggestions']);self.assertIn('approval_id',proposal)
        Policy(self.s).approve(proposal['approval_id'],self.actor);self.e.execute(proposal['action_id'])
        self.assertTrue((self.root/'workspace/review.txt').exists());self.assertEqual(self.h.snapshot(a)['state'],'inhibited')

    def test_shipped_definition_and_invalid_feedback_parameters(self):
        self.enable();definition=json.loads((Path(__file__).resolve().parents[1]/'config/examples/habit-learning.json').read_text())
        state=self.h.enroll(definition['action'],definition['cue'],'template',self.actor)
        self.assertEqual(state['state'],'learning');self.assertTrue((self.root/'WAKE_DISABLED').exists())
        # Binary reinforcement is a controller annotation, never a model probability.
        a=self.h.enroll(ACTION,{'source':'user','task_contains':'review'},'wait-template',self.actor)['association'];records,_=self.episode(a)
        for value in (True,.5,2,-1):
            with self.assertRaises(ContractError):self.h.feedback(records[0]['id'],value,'invalid','invalid-'+str(value),self.h.snapshot(a)['revision'],self.actor)
        with self.assertRaises(Forbidden):self.h.feedback(records[0]['id'],1,'not controller','bad',self.h.snapshot(a)['revision'],'model')
