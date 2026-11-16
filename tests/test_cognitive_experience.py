"""Ownership, source lineage, version CAS, compatibility and shadow-only authority."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from digital_life.application.learning.self_feedback import SelfFeedback
from digital_life.application.services.cognition import Cognition
from digital_life.application.services.learning import Learning
from digital_life.application.cognition.cognition_experience import CognitiveExperience,CONTRACT
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,utc
from evaluation.exploration.harness import Harness

ROOT=Path(__file__).resolve().parents[1]
class CognitiveExperienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();cases=json.loads((ROOT/'evaluation/exploration/materials/cases-v1.json').read_text())['cases']
        self.h=Harness(Path(self.tmp.name)/'instance',next(c for c in cases if c['case_id']=='B01'))
        self.sf=SelfFeedback(self.h.s);self.actor=self.h.s.config()['controller'];self.sf.configure(self.actor,True)
        self.learning=Learning(self.h.s);self.cognition=Cognition(self.h.s);self.experience=CognitiveExperience(self.h.s)
    def tearDown(self):self.h.close();self.tmp.cleanup()
    def finish(self):
        a=self.h.investigation();self.h.finish(a);return a
    def opportunity(self):return self.sf._events('opportunity')[-1]['payload']
    def pending(self):
        with patch.object(Cognition,'save_experience',return_value=None):self.finish()
        return self.learning.experience_assessments()[0]['id']
    def proposal(self,assessment,revision=0):return self.learning.propose_experience(assessment,revision)
    def second_observation(self):
        q=next(iter(self.h.x.questions().values()))
        with self.h.s.tx():self.h.x.record(dict(q,id='second',question='Check changed source',state='candidate',visits=0,activity=None))
        (self.h.root/'workspace'/self.h.case['public']['observation_path']).write_text('new actual source')
        with patch('digital_life.application.autonomy.exploration.utc',side_effect=lambda seconds=0:utc(7200+seconds)):a=self.h.x.tick(self.h.engine)
        self.h.finish(a);return a
    def test_learning_assesses_and_proposes_cognition_alone_saves(self):
        self.finish();history=self.experience.events();self.assertEqual(len(history),1)
        revision=history[0]['payload'];self.assertEqual(revision['owner'],'cognition.experience')
        p=self.h.s.row('runtime_events',revision['proposal_ref']);a=self.h.s.row('runtime_events',revision['assessment_ref'])
        self.assertEqual((p['source'],a['source']),('learning-experience','learning-experience'))
        self.assertEqual((p['event_type'],a['event_type']),('learning.experience_proposed','learning.experience_assessed'))
        self.assertEqual(self.sf._events('assessment'),[])
        self.assertEqual(revision['acceptance_state'],'shadow-not-world-fact')
    def test_learning_proposal_is_not_a_saved_experience(self):
        assessment=self.pending();p=self.proposal(assessment)
        self.assertEqual(self.experience.events(),[])
        self.cognition.save_experience(p,0);self.assertEqual(len(self.experience.events()),1)
    def test_only_learning_proposal_events_are_accepted(self):
        self.finish();op=self.sf._events('opportunity')[0]['id']
        with self.assertRaises(Forbidden):self.cognition.save_experience(op,0)
    def test_numeric_gain_cannot_be_smuggled_into_shadow_version(self):
        assessment=self.pending();a=dict(self.learning.experience_assessments()[0]['payload']);a.update(gain=.8,gain_status='positive',qualified=True)
        with self.h.s.tx():bad=self.h.s.event('learning.experience_assessed',payload=a,source='learning-experience',key='bad-fixture-only')
        p=self.proposal(bad)
        with self.assertRaises(Forbidden):self.cognition.save_experience(p,0)
        self.assertEqual(self.experience.events(),[])
    def test_cas_conflict_and_explicit_rebase(self):
        first=self.pending()
        with patch.object(Cognition,'save_experience',return_value=None):self.second_observation()
        second=self.learning.experience_assessments()[-1]['id']
        p1=self.proposal(first,0);p2=self.proposal(second,0)
        first_saved=self.cognition.save_experience(p1,0)
        with self.assertRaises(Conflict):self.cognition.save_experience(p2,0)
        p2_rebased=self.proposal(second,1);second_saved=self.cognition.save_experience(p2_rebased,1)
        self.assertEqual(self.experience.events()[-1]['payload']['previous_revision_ref'],first_saved)
        self.assertNotEqual(first_saved,second_saved)
        self.assertEqual(self.experience.events()[-1]['payload']['revision'],2)
    def test_replay_saved_assessment_does_not_create_version(self):
        self.finish();first=self.experience.events()[0]
        p=self.proposal(first['payload']['assessment_ref'],1)
        self.assertEqual(self.cognition.save_experience(p,1),first['id']);self.assertEqual(len(self.experience.events()),1)
    def test_invalidation_is_learning_proposal_and_cognitive_version(self):
        self.finish();op=self.opportunity()['opportunity_ref'];self.sf.invalidate(op,'source corrected',self.actor)
        self.sf.invalidate(op,'source corrected',self.actor)
        history=self.experience.events();self.assertEqual(len(history),2)
        self.assertEqual(history[-1]['payload']['kind'],'invalidation')
        p=self.h.s.row('runtime_events',history[-1]['payload']['proposal_ref']);self.assertEqual(p['source'],'learning-experience')
        snapshot=self.cognition.experience_snapshot(self.actor);self.assertEqual(snapshot['cells'][0]['excluded_count'],1)
    def test_stale_invalidation_can_be_rebased_without_overwrite(self):
        a=self.pending();op=self.opportunity()['opportunity_ref']
        stale=self.learning.propose_experience_invalidation(op,'later invalid',0,self.actor)
        self.cognition.save_experience(self.proposal(a),0)
        with self.assertRaises(Conflict):self.cognition.save_experience(stale,0)
        rebased=self.learning.propose_experience_invalidation(op,'later invalid',1,self.actor)
        self.cognition.save_experience(rebased,1)
        self.assertEqual(len(self.experience.events()),2)
        self.assertEqual(self.cognition.experience_snapshot(self.actor)['cells'][0]['excluded_count'],1)
    def test_invalidating_unknown_source_or_wrong_actor_rejected(self):
        with self.assertRaises(ContractError):self.sf.invalidate('missing','reason',self.actor)
        self.finish()
        with self.assertRaises(Forbidden):self.sf.invalidate(self.opportunity()['opportunity_ref'],'reason','other')
    def test_permission_withdrawal_changes_view_not_historical_version(self):
        self.finish();before=self.cognition.experience_snapshot(self.actor);history=self.experience.events()
        from digital_life.application.services.memory import Memory
        Memory(self.h.s).restrict(self.h.memory['memory_id'],[self.actor],self.actor)
        after=self.cognition.experience_snapshot(self.actor)
        self.assertEqual(history,self.experience.events());self.assertEqual(after['cells'][0]['excluded_count'],1)
        self.assertNotEqual(before['snapshot_revision'],after['snapshot_revision'])
    def test_restart_reads_identical_cognitive_versions(self):
        self.finish();before=self.cognition.experience_snapshot(self.actor)
        from digital_life.infrastructure.persistence.sqlite_store import Store
        s=Store(self.h.root)
        try:self.assertEqual(Cognition(s).experience_snapshot(self.actor),before)
        finally:s.close()
    def test_legacy_read_is_not_migration_and_explicit_adoption_is_idempotent(self):
        with patch.object(SelfFeedback,'_save_experience',return_value=None):self.finish()
        op=self.opportunity();legacy=dict(op,revision=1,gain=None,gain_status='unknown',qualified=False)
        with self.h.s.tx():self.sf._write('assessment',op['opportunity_ref']+':1',legacy)
        original=self.sf._events('assessment')[0];snapshot=self.cognition.experience_snapshot(self.actor)
        self.assertEqual(snapshot['legacy_unadopted_count'],1);self.assertEqual(self.experience.events(),[])
        self.sf.reconcile_experiences(self.actor);self.sf.reconcile_experiences(self.actor)
        self.assertEqual(len(self.experience.events()),1);self.assertEqual(self.sf._events('assessment')[0],original)
        snapshot=self.cognition.experience_snapshot(self.actor)
        self.assertEqual(snapshot['legacy_unadopted_count'],0);self.assertEqual(snapshot['cells'][0]['unknown_count'],1)
    def test_legacy_adoption_requires_enabled_and_controller(self):
        with self.assertRaises(Forbidden):self.sf.reconcile_experiences('other')
        self.sf.configure(self.actor,False)
        with self.assertRaises(Forbidden):self.sf.reconcile_experiences(self.actor)
    def test_experience_does_not_promote_beliefs_or_enter_model_context(self):
        before=len(self.h.s.rows('cognition_beliefs'));self.finish()
        self.assertEqual(len(self.h.s.rows('cognition_beliefs')),before)
        for payload in self.h.model.inputs:self.assertNotIn('experience_snapshot',payload)
        self.assertFalse(self.cognition.experience_snapshot(self.actor)['affects_selection'])
    def test_cognitive_view_requires_controller_and_old_alias_delegates(self):
        self.finish()
        with self.assertRaises(Forbidden):self.cognition.experience_snapshot('other')
        self.assertEqual(self.cognition.experience_snapshot(self.actor),self.sf.shadow_interest(self.actor))
    def test_stale_expected_revision_and_boolean_revision_rejected(self):
        assessment=self.pending();p=self.proposal(assessment,0)
        for wrong in (True,1):
            with self.assertRaises(Conflict):self.cognition.save_experience(p,wrong)
    def test_cross_instance_proposal_rejected(self):
        assessment=self.pending();p=self.proposal(assessment)
        from digital_life.infrastructure.persistence.sqlite_store import Store
        s=Store.prepare(Path(self.tmp.name)/'other')
        try:
            with self.assertRaises(ContractError):Cognition(s).save_experience(p,0)
        finally:s.close()

if __name__=='__main__':unittest.main()
