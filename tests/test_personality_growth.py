"""T07: temporary instances, recorded episodes and controlled slow updates."""
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.domain.contracts import ContractError, Conflict, Forbidden, utc
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.behavior.personality_growth import PersonalityGrowth
from digital_life.application.services.personality import Personality


class Model:
    name='fixture'
    def __init__(self,action=None):self.action=action or {'tool':'wait','arguments':{'reason':'observed wait'}};self.inputs=[]
    def generate(self,p):self.inputs.append(p);return {'schema_version':1,'explanation':'observed fixture','action':self.action}


class PersonalityGrowthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'isolated'
        self.s=Store.prepare(self.root);self.addCleanup(self.s.close);self.e=Engine(self.s);self.g=PersonalityGrowth(self.s);self.actor=self.s.config()['controller'];self.sequence=0
    def enable(self):self.g.configure(True,self.actor)
    def unlock(self):
        (self.root/'WAKE_DISABLED').unlink(missing_ok=True)
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.root,self.s.instance_id);c.resume('isolated-t07');c.close()
    def value(self,trait='openness'):return next(r['central_value'] for r in Personality(self.s).current()['traits'] if r['name']==trait)
    def episode(self,value=.8,context='work',trait='openness',reliability=1):
        self.sequence+=1;key='episode-'+str(self.sequence);a=self.e.submit(key,key);self.unlock();self.e.think(a,Model())
        opportunity=next(o['id'] for o in self.g.events('opportunity') if o['activity']==a)
        return self.g.observe(opportunity,trait,value,reliability,context,'controller fixture assessment',key,self.actor)
    def batch(self,trait='openness',value=.8):
        refs=[self.episode(value,context,trait) for context in ('work','social','work','unseen','unseen')]
        return refs[:3],refs[3:]
    def adopt(self,train,holdout,trait='openness'):
        p=self.g.propose(trait,train,self.actor);v=self.g.evaluate(p['proposal'],holdout,self.actor)
        result=self.g.commit(p['proposal'],v['evaluation'],self.actor);return p,v,result
    def repair_evidence(self):return [self.s.evidence(object_id=self.s.event('controller.review',payload={'case':i})) for i in range(2)]

    def test_default_off_and_single_episode_do_not_grow(self):
        self.e.submit('old','old');self.unlock();self.e.think(self.s.rows('activities')[0]['id'],Model())
        self.assertFalse(self.g.events('opportunity'));self.assertEqual(len(self.s.rows('personality_profiles')),1)

    def test_enabled_single_episode_only_records_source(self):
        self.enable();ref=self.episode();self.assertEqual(self.value(),0);self.assertEqual(len(self.s.rows('personality_profiles')),1)
        with self.assertRaises(ContractError):self.g.propose('openness',[ref],self.actor)
        observation=self.g.event(ref,'observed');source=self.g.event(observation['opportunity'],'opportunity')
        self.assertEqual(source['profile'],Personality(self.s).current()['profile']['id']);self.assertIsNone(source['result'])

    def test_controlled_update_bounded_and_unmodified_traits_keep_uncertainty(self):
        self.enable();before=Personality(self.s).current();train,heldout=self.batch();p,v,result=self.adopt(train,heldout)
        self.assertAlmostEqual(self.value(),.02);self.assertGreater(v['measurement']['benefit'],0)
        now=Personality(self.s).current();self.assertEqual(now['profile']['previous_profile_id'],before['profile']['id'])
        for old,new in zip(before['traits'],now['traits']):
            if old['name']!='openness':self.assertEqual(old['central_value'],new['central_value']);self.assertEqual(old['uncertainty_json'],new['uncertainty_json'])
            else:self.assertEqual(json.loads(new['uncertainty_json'])['n'],3)
        self.assertEqual(self.s.integrity()['foreign_keys'],[])

    def test_proposal_and_evaluation_do_not_change_profile_or_run_model(self):
        self.enable();train,holdout=self.batch();profile=Personality(self.s).current()['profile']['id'];calls=len(self.s.rows('thought_attempts'))
        proposal=self.g.propose('openness',train,self.actor);ev=self.g.evaluate(proposal['proposal'],holdout,self.actor)
        self.assertEqual(Personality(self.s).current()['profile']['id'],profile);self.assertEqual(len(self.s.rows('thought_attempts')),calls)
        self.assertEqual(ev['measurement']['model_calls'],0);self.assertEqual(ev['measurement']['tools_executed'],0)

    def test_distinct_activities_and_contexts_required(self):
        self.enable();refs=[self.episode(context='same') for _ in range(3)]
        with self.assertRaises(ContractError):self.g.propose('openness',refs,self.actor)
        with self.assertRaises(ContractError):self.g.propose('openness',[refs[0]]*3,self.actor)
        first=self.g.event(refs[0],'observed');opportunity=first['opportunity'];self.g.invalidate(refs[0],'correction',self.actor)
        replacement=self.g.observe(opportunity,'openness',.8,1,'other','corrected','replacement',self.actor)
        with self.assertRaises(Conflict):self.g.propose('openness',[refs[0],replacement,refs[1]],self.actor)

    def test_contradictory_and_low_quality_training_rejected(self):
        self.enable();refs=[self.episode(v,c) for v,c in ((-1,'a'),(1,'b'),(1,'a'))]
        with self.assertRaises(Conflict):self.g.propose('openness',refs,self.actor)
        refs=[self.episode(.8,c,reliability=.2) for c in ('a','b','a')]
        with self.assertRaises(Conflict):self.g.propose('openness',refs,self.actor)
        self.assertEqual(self.value(),0)

    def test_holdout_overlap_or_seen_context_rejected(self):
        self.enable();train,heldout=self.batch();p=self.g.propose('openness',train,self.actor)
        with self.assertRaises(ContractError):self.g.evaluate(p['proposal'],train[:2],self.actor)
        seen=[self.episode(context='work') for _ in range(2)]
        with self.assertRaises(ContractError):self.g.evaluate(p['proposal'],seen,self.actor)

    def test_no_improvement_or_regression_is_not_committed(self):
        self.enable();train,_=self.batch();holdout=[self.episode(-.8,'unseen') for _ in range(2)]
        p=self.g.propose('openness',train,self.actor);ev=self.g.evaluate(p['proposal'],holdout,self.actor)
        self.assertFalse(ev['measurement']['eligible'])
        with self.assertRaises(Conflict):self.g.commit(p['proposal'],ev['evaluation'],self.actor)
        self.assertEqual(self.value(),0)

    def test_invalidation_idempotent_and_blocks_commit(self):
        self.enable();train,heldout=self.batch();p=self.g.propose('openness',train,self.actor);ev=self.g.evaluate(p['proposal'],heldout,self.actor)
        first=self.g.invalidate(heldout[0],'wrong label',self.actor);second=self.g.invalidate(heldout[0],'again',self.actor);self.assertEqual(first,second)
        with self.assertRaises(Conflict):self.g.commit(p['proposal'],ev['evaluation'],self.actor)
        self.assertEqual(self.value(),0)

    def test_cas_detects_manual_profile_revision(self):
        self.enable();train,heldout=self.batch();p=self.g.propose('openness',train,self.actor);ev=self.g.evaluate(p['proposal'],heldout,self.actor)
        Personality(self.s).replace({'openness':.1},self.g._evidence(train[:2]),self.actor)
        with self.assertRaises(Conflict):self.g.commit(p['proposal'],ev['evaluation'],self.actor)
        self.assertEqual(self.value(),.1)

    def test_config_change_invalidates_old_proposal(self):
        self.enable();train,heldout=self.batch();p=self.g.propose('openness',train,self.actor)
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.root,self.s.instance_id);c.stop('test');c.close();self.g.configure(False,self.actor)
        with self.assertRaises(Forbidden):self.g.evaluate(p['proposal'],heldout,self.actor)

    def test_cooldown_and_consumed_sources_cannot_be_reused(self):
        self.enable();train,heldout=self.batch();self.adopt(train,heldout)
        other,_=self.batch()
        with self.assertRaises(Conflict):self.g.propose('openness',other,self.actor)
        with patch('digital_life.application.behavior.personality_growth.utc',side_effect=lambda seconds=0:utc(86410+seconds)):
            with self.assertRaises(Conflict):self.g.propose('openness',train,self.actor)

    def test_rolling_absolute_budget_limits_multiple_days(self):
        self.enable();train,heldout=self.batch();self.adopt(train,heldout)
        for day,expected in ((1,.04),(2,.05)):
            train,heldout=self.batch()
            with patch('digital_life.application.behavior.personality_growth.utc',side_effect=lambda seconds=0,day=day:utc(day*86410+seconds)):
                self.adopt(train,heldout)
            self.assertAlmostEqual(self.value(),expected)
        train,_=self.batch()
        with patch('digital_life.application.behavior.personality_growth.utc',side_effect=lambda seconds=0:utc(3*86410+seconds)):
            with self.assertRaises(Conflict):self.g.propose('openness',train,self.actor)

    def test_rollback_appends_compensation_and_retains_consumption(self):
        self.enable();train,heldout=self.batch();_,_,result=self.adopt(train,heldout);current=result['profile']
        reversal=self.g.rollback(result['commit'],self.repair_evidence(),self.actor)
        self.assertEqual(self.value(),0);self.assertEqual(len(self.s.rows('personality_profiles')),3)
        self.assertEqual(Personality(self.s).current()['profile']['previous_profile_id'],current)
        self.assertEqual(self.s.row('learning_update_commits',reversal['reversal'])['reversal_of'],result['commit'])
        with self.assertRaises(Conflict):self.g.rollback(result['commit'],self.repair_evidence(),self.actor)
        with patch('digital_life.application.behavior.personality_growth.utc',side_effect=lambda seconds=0:utc(86410+seconds)):
            with self.assertRaises(Conflict):self.g.propose('openness',train,self.actor)

    def test_rollback_rejects_intervening_revision(self):
        self.enable();train,heldout=self.batch();_,_,result=self.adopt(train,heldout)
        Personality(self.s).replace({},self.g._evidence(train[:2]),self.actor)
        with self.assertRaises(Conflict):self.g.rollback(result['commit'],self.repair_evidence(),self.actor)

    def test_invalidated_committed_support_is_visible_not_auto_reverted(self):
        self.enable();train,heldout=self.batch();_,_,result=self.adopt(train,heldout)
        self.g.invalidate(train[0],'review needed',self.actor)
        self.assertIn(result['commit'],self.g.status()['invalidated_commits']);self.assertEqual(self.value(),.02)

    def test_annotation_dedup_validation_and_controller_authority(self):
        self.enable();ref=self.episode();o=self.g.event(ref,'observed')
        self.assertEqual(self.g.observe(o['opportunity'],o['trait'],o['value'],o['reliability'],o['context'],o['reason'],'episode-1',self.actor),ref)
        with self.assertRaises(Conflict):self.g.observe(o['opportunity'],o['trait'],.2,1,'new','changed','episode-1',self.actor)
        with self.assertRaises(Conflict):self.g.observe(o['opportunity'],o['trait'],.2,1,'new','changed','another-key',self.actor)
        with self.assertRaises(Forbidden):self.g.propose('openness',[ref]*3,'model')
        for value in (True,float('nan'),2):
            with self.assertRaises(ContractError):self.g.observe(o['opportunity'],'openness',value,1,'c','bad','bad-'+str(value),self.actor)

    def test_evaluation_replay_is_idempotent_and_tampering_is_blocked(self):
        self.enable();train,heldout=self.batch();p=self.g.propose('openness',train,self.actor);ev=self.g.evaluate(p['proposal'],heldout,self.actor)
        again=self.g.evaluate(p['proposal'],heldout,self.actor);self.assertEqual(ev['evaluation'],again['evaluation']);self.assertEqual(len(self.s.rows('learning_update_evaluations')),1)
        self.s.db.execute('UPDATE learning_update_evaluations SET benefit=benefit+1 WHERE id=?',(ev['evaluation'],))
        with self.assertRaises(Conflict):self.g.commit(p['proposal'],ev['evaluation'],self.actor)

    def test_later_requests_and_t06_probability_use_grown_profile(self):
        from digital_life.application.behavior.behavior_policy import BehaviorPolicy
        self.enable();b=BehaviorPolicy(self.s);b.configure(True,self.actor)
        self.sequence+=1;a=self.e.submit('baseline','baseline');self.unlock();req,before=self.e.prepare(a,Model())
        # These history sources are accepted decisions, rather than constructed feature vectors.
        train,heldout=self.batch();self.adopt(train,heldout)
        a2=self.e.submit('after','after');_,after=self.e.prepare(a2,Model())
        action={'tool':'read_file','arguments':{'path':'source.txt'}}
        # Hold other policy inputs constant to isolate the changed personality activation.
        isolated=json.loads(json.dumps(before));isolated['behavior_policy']['features']['personality.openness']=after['behavior_policy']['features']['personality.openness']
        self.assertGreater(b.evaluate(isolated,action,.5)['candidates'][0]['probability'],b.evaluate(before,action,.5)['candidates'][0]['probability'])
        self.assertEqual(after['personality']['openness']['value'],.02)
        self.assertNotEqual(before['personality_growth']['profile'],after['personality_growth']['profile'])
        self.assertEqual(self.s.read_artifact(req['request_artifact_id']),before)

    def test_tool_intention_is_not_observation_until_verified(self):
        from digital_life.application.accounts.authorization import Policy
        self.enable();self.unlock();a=self.e.submit('write','write');m=Model({'tool':'write_note','arguments':{'path':'out.txt','text':'done'}})
        proposal=self.e.think(a,m);self.assertFalse(self.g.events('opportunity'))
        Policy(self.s).approve(proposal['approval_id'],self.actor);self.e.execute(proposal['action_id'])
        source=self.g.events('opportunity')[0];self.assertTrue(source['result']);self.assertEqual(source['activity'],a)
        self.assertIsNotNone(self.g.record_tool(proposal['action_id'],{'state':'succeeded','result':source['result']}))
        self.assertEqual(len(self.g.events('opportunity')),1)

    def test_reopen_preserves_identity_history_and_growth_metadata(self):
        self.enable();train,heldout=self.batch();self.adopt(train,heldout);identity=self.s.instance_id;count=len(self.s.rows('memory_revisions'))
        self.s.close();self.s=Store(self.root);self.addCleanup(self.s.close);self.g=PersonalityGrowth(self.s)
        self.assertEqual(self.s.instance_id,identity);self.assertEqual(self.value(),.02);self.assertEqual(len(self.s.rows('memory_revisions')),count)
        self.assertEqual(len(self.g.events('applied')),1);self.assertEqual(self.s.integrity()['foreign_keys'],[])

    def test_cli_status_is_pure_and_configuration_does_not_wake(self):
        from digital_life.entrypoints.growth import parsers,handle
        parser=argparse.ArgumentParser();parsers(parser.add_subparsers(dest='command'))
        handle(self.s,parser.parse_args(['personality-growth','enable']));before=len(self.s.rows('runtime_events'))
        result=handle(self.s,parser.parse_args(['personality-growth','status']))
        self.assertFalse(result['inference_started']);self.assertEqual(before,len(self.s.rows('runtime_events')));self.assertTrue((self.root/'WAKE_DISABLED').exists())
        self.unlock()
        with self.assertRaises(Conflict):self.enable()

    def test_multiple_rounds_of_same_activity_are_not_independent_training(self):
        from digital_life.application.autonomy.task_loop import TaskLoop
        self.enable();a=self.e.submit('multi','multi');loop=TaskLoop(self.s)
        loop.configure(a,{'kind':'file_contains','path':'missing.txt','text':'done'},self.actor,max_rounds=3);self.unlock();self.e.think(a,Model())
        first=self.g.events('opportunity')[-1]['id'];one=self.g.observe(first,'openness',.8,1,'work','first','round-one',self.actor)
        loop.resume(self.e,a,'continue',self.actor);self.e.think(a,Model())
        second=self.g.events('opportunity')[-1]['id'];two=self.g.observe(second,'openness',.8,1,'social','second','round-two',self.actor)
        third=self.episode(context='social')
        with self.assertRaises(ContractError):self.g.propose('openness',[one,two,third],self.actor)

    def test_unknown_tool_effect_does_not_become_growth_source(self):
        from digital_life.application.accounts.authorization import Policy
        from digital_life.domain.contracts import ToolResult
        self.enable();a=self.e.submit('unknown','unknown');self.unlock()
        result=self.e.think(a,Model({'tool':'write_note','arguments':{'path':'unknown.txt','text':'done'}}))
        Policy(self.s).approve(result['approval_id'],self.actor)
        outcome=self.e.execute(result['action_id'],backend=lambda *args:ToolResult('received','unknown','unknown',{'fixture':'unknown'}))
        self.assertEqual(outcome['state'],'unknown');self.assertFalse(self.g.events('opportunity'))

    def test_rollback_absolute_movement_reduces_next_growth_budget(self):
        self.enable();train,heldout=self.batch();_,_,result=self.adopt(train,heldout)
        self.g.rollback(result['commit'],self.repair_evidence(),self.actor);train,heldout=self.batch()
        with patch('digital_life.application.behavior.personality_growth.utc',side_effect=lambda seconds=0:utc(86410+seconds)):
            self.adopt(train,heldout)
        self.assertAlmostEqual(self.value(),.01)

    def test_negative_growth_and_expired_window(self):
        self.enable();train,heldout=self.batch(value=-.8);self.adopt(train,heldout);self.assertAlmostEqual(self.value(),-.02)
        train,heldout=self.batch(value=-.8)
        with patch('digital_life.application.behavior.personality_growth.utc',side_effect=lambda seconds=0:utc(31*86410+seconds)):
            self.adopt(train,heldout)
        self.assertAlmostEqual(self.value(),-.04)

    def test_source_erasure_prevents_proposal(self):
        self.enable();train,_=self.batch();o=self.g.event(train[0],'observed');source=self.g.event(o['opportunity'],'opportunity');req=self.s.row('thought_requests',source['request'])
        # Replace the source reference with an actual redaction artifact, as an erasure would do.
        artifact=self.s.artifact({'redacted_by':'controller'})
        self.s.db.execute('UPDATE thought_requests SET request_artifact_id=? WHERE id=?',(artifact,req['id']))
        with self.assertRaises(Forbidden):self.g.propose('openness',train,self.actor)

    def test_original_request_profile_is_retained_when_current_profile_changes(self):
        self.enable();a=self.e.submit('snapshot','snapshot');self.unlock();_,p=self.e.prepare(a,Model());old=p['personality_growth']['profile']
        evidence=self.repair_evidence();Personality(self.s).replace({'openness':.1},evidence,self.actor)
        self.e.think(a,Model());self.assertEqual(self.g.events('opportunity')[0]['profile'],old)
        self.assertNotEqual(Personality(self.s).current()['profile']['id'],old)

    def test_correction_appends_and_preserves_invalid_original(self):
        self.enable();ref=self.episode();old=self.g.event(ref,'observed');self.g.invalidate(ref,'mislabelled',self.actor)
        new=self.g.observe(old['opportunity'],'openness',.2,1,'corrected-context','corrected','corrected-key',self.actor)
        self.assertEqual(self.g._valid(new)['value'],.2)
        with self.assertRaises(Conflict):self.g._valid(ref)
        self.assertEqual(len(self.g.events('observed')),2);self.assertEqual(len(self.s.rows('personality_profiles')),1)

    def test_rollback_rejects_two_wrappers_for_one_origin(self):
        self.enable();train,heldout=self.batch();_,_,result=self.adopt(train,heldout)
        origin=self.s.event('controller.review',payload={'one':'origin'});refs=[self.s.evidence(object_id=origin) for _ in range(2)]
        with self.assertRaises(ContractError):self.g.rollback(result['commit'],refs,self.actor)
        self.assertEqual(self.value(),.02)

    def test_erased_tool_receipt_invalidates_annotation_source(self):
        from digital_life.application.accounts.authorization import Policy
        self.enable();a=self.e.submit('verified','verified');self.unlock()
        proposal=self.e.think(a,Model({'tool':'write_note','arguments':{'path':'receipt.txt','text':'done'}}))
        Policy(self.s).approve(proposal['approval_id'],self.actor);self.e.execute(proposal['action_id'])
        source=self.g.events('opportunity')[0];ref=self.g.observe(source['id'],'openness',.8,1,'work','fixture','receipt-source',self.actor)
        artifact=self.s.artifact({'redacted_by':'controller'});self.s.db.execute('UPDATE action_results SET receipt_artifact_id=? WHERE id=?',(artifact,source['result']))
        with self.assertRaises(Forbidden):self.g._valid(ref)
