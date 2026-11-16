"""T09 conservative identity and evidence-bound conditional relationships."""
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.behavior.people_relations import PeopleRelations
from digital_life.application.behavior.behavior_policy import BehaviorPolicy
from digital_life.application.cognition.cognitive_updates import CognitiveUpdates


class Model:
    name='fixture'
    def __init__(self):self.inputs=[]
    def generate(self,p):self.inputs.append(p);return {'schema_version':1,'explanation':'fixture reply','action':{'tool':'ask','arguments':{'reason':'question'}}}


class CognitiveModel(Model):
    def generate(self,p):
        self.inputs.append(p)
        return {'schema_version':3,'explanation':'candidate statement','action':{'tool':'wait','arguments':{'reason':'review'}},'cognition':{'claims':[{'subject':'陈明','predicate':'职业','value':'植物学家','source_ref':next(k for k,v in p['cognition_sources'].items() if '陈明是植物学家' in v and k not in {m['revision_id'] for m in p['selected_memories']}),'quote':'陈明是植物学家','kind':'reported'}],'questions':[],'predictions':[],'plan':[]}}


class PeopleRelationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'isolated'
        self.s=Store.prepare(self.root);self.addCleanup(self.s.close);self.e=Engine(self.s);self.p=PeopleRelations(self.s);self.actor=self.s.config()['controller'];self.sequence=0
    def enable(self):self.p.configure(True,self.actor)
    def evidence(self,n=1):
        result=[]
        for _ in range(n):
            self.sequence+=1;a=self.e.submit('recorded source '+str(self.sequence),'source-'+str(self.sequence));signal=self.e.details(a)[2]['id'];result.append(self.s.evidence(object_id=signal,method='actual-received-statement'))
        return result
    def register(self,name='陈明'):
        self.sequence+=1;return self.p.register(name,self.evidence(),'person-'+str(self.sequence),self.actor)
    def unlock(self):
        (self.root/'WAKE_DISABLED').unlink(missing_ok=True)
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.root,self.s.instance_id);c.resume('isolated-t09-'+identifier());c.close()
    def trust(self,who=None,outcome=1,domain='behavior',dimension='reliability',condition=None):
        evidence=self.evidence();return self.p.trust(who or self.actor,domain,dimension,condition or {},outcome,evidence,'controller annotation','trust-'+identifier(),self.p.revision(),self.actor)
    def repair(self,who=None,domain='behavior',dimension='reliability',condition=None):
        return self.p.repair(who or self.actor,domain,dimension,condition or {},'two new observed sources','repair-'+identifier(),self.p.revision(),self.actor)
    def prepare(self,task='review',model=None,source='user'):
        self.sequence+=1;a=self.e.submit(task,'thought-'+str(self.sequence),source);self.unlock();request,payload=self.e.prepare(a,model or Model());return a,request,payload

    def test_default_off_preserves_old_payload(self):
        _,_,payload=self.prepare();self.assertNotIn('relationships',payload)

    def test_same_name_never_merges_people(self):
        self.enable();first=self.register();second=self.register()
        self.assertNotEqual(first['actor'],second['actor']);self.assertNotEqual(first['entity'],second['entity'])
        resolved=self.p.resolve('陈明');self.assertEqual(resolved['status'],'ambiguous');self.assertEqual(len(resolved['candidates']),2)
        self.assertFalse(resolved['identity_verified'])

    def test_registration_idempotency_and_normalization_retains_ambiguity(self):
        self.enable();evidence=self.evidence();one=self.p.register('LiWei',evidence,'one',self.actor)
        again=self.p.register('LiWei',evidence,'one',self.actor);self.assertEqual(one,again)
        with self.assertRaises(Conflict):self.p.register('Other',evidence,'one',self.actor)
        self.register('ＬＩＷＥＩ');self.assertEqual(self.p.resolve(' liwei ')['status'],'ambiguous')

    def test_alias_collision_scopes_and_invalidation(self):
        self.enable();one=self.register('陈明甲');two=self.register('陈明乙')
        a=self.p.alias(one['actor'],'小陈','global',self.evidence(2),'a',self.actor)
        self.p.alias(two['actor'],'小陈','global',self.evidence(2),'b',self.actor)
        self.assertEqual(self.p.resolve('小陈')['status'],'ambiguous')
        self.p.alias(one['actor'],'小陈','chat:work',self.evidence(2),'c',self.actor)
        scoped=self.p.resolve('小陈','chat:work');self.assertEqual(scoped['status'],'unique_candidate');self.assertEqual(scoped['candidates'][0]['actor'],one['actor'])
        self.p.invalidate(a['id'],'incorrect alias claim','invalidate',self.actor)
        self.assertEqual(self.p.resolve('小陈')['candidates'][0]['actor'],two['actor'])
        self.assertEqual(len(self.s.rows('world_entity_aliases')),2)

    def test_alias_requires_distinct_origins_not_evidence_wrappers(self):
        self.enable();one=self.register();ref=self.evidence()[0];origin=self.s.row('evidence_items',ref)['origin_object_id'];wrapper=self.s.evidence(object_id=origin)
        with self.assertRaises(ContractError):self.p.alias(one['actor'],'teacher','global',[ref,wrapper],'bad',self.actor)

    def test_roles_and_names_never_grant_authentication_or_permissions(self):
        self.enable();original=dict(self.s.config());identity=self.s.instance_id;anchors=self.s.rows('identity_anchors')
        person=self.register('controller');self.p.relate(person['actor'],'父亲',self.evidence(2),'father',self.actor)
        self.p.alias(person['actor'],'liwei','global',self.evidence(2),'liwei',self.actor)
        self.assertEqual(self.s.config(),original);self.assertEqual(self.s.instance_id,identity);self.assertEqual(self.s.rows('identity_anchors'),anchors)
        self.assertFalse(self.s.rows('grants'));self.assertEqual(self.s.row('social_actors',person['actor'])['identity_status'],'unverified')
        self.assertFalse(self.p.describe(person['actor'])['is_controller'])

    def test_conditional_trust_has_counts_and_domain_separation(self):
        self.enable();self.trust(outcome=1,domain='coding',dimension='ability');self.trust(outcome=0,domain='behavior')
        cells=self.p.cells(self.actor);self.assertEqual(len(cells),2)
        by_domain={c['domain']:c for c in cells};self.assertAlmostEqual(by_domain['coding']['estimate'],2/3);self.assertAlmostEqual(by_domain['behavior']['estimate'],1/3)
        self.assertEqual(by_domain['coding']['n'],1);self.assertTrue(by_domain['behavior']['unresolved'])

    def test_most_specific_matching_condition_prevents_global_override(self):
        self.enable();self.trust(outcome=1);self.trust(outcome=0,condition={'source':'user','task_contains':'review'})
        _,_,specific=self.prepare('review critical');_,_,other=self.prepare('unrelated')
        self.assertAlmostEqual(specific['relationships']['behavior_reliability']['estimate'],1/3)
        self.assertAlmostEqual(other['relationships']['behavior_reliability']['estimate'],2/3)

    def test_only_actual_trigger_actor_affects_t06_signal(self):
        self.enable();b=BehaviorPolicy(self.s);b.configure(True,self.actor);person=self.register('liwei');self.trust(person['actor'],1)
        _,_,payload=self.prepare('liwei can help');self.assertTrue(payload['relationships']['mentions'])
        feature=payload['behavior_policy']['features']['relationship.reliability'];self.assertTrue(feature['missing']);self.assertEqual(feature['value'],0)
        self.assertEqual(payload['relationships']['trigger_actor']['actor'],self.actor)

    def test_t06_uses_actual_conditional_projection_and_changes_probability(self):
        self.enable();b=BehaviorPolicy(self.s);b.configure(True,self.actor)
        _,_,payload=self.prepare();action={'tool':'ask','arguments':{'reason':'question'}};before=b.evaluate(payload,action,.5)['candidates'][0]['probability']
        self.trust(outcome=1);_,_,after=self.prepare();value=after['behavior_policy']['features']['relationship.reliability']
        self.assertFalse(value['missing']);self.assertAlmostEqual(value['value'],2/3);self.assertTrue(value['refs'])
        self.assertGreater(b.evaluate(after,action,.5)['candidates'][0]['probability'],before)

    def test_duplicate_trust_source_and_stale_revision_rejected(self):
        self.enable();refs=self.evidence();revision=self.p.revision();first=self.p.trust(self.actor,'behavior','reliability',{},1,refs,'one','one',revision,self.actor)
        self.assertEqual(first,self.p.trust(self.actor,'behavior','reliability',{},1,refs,'one','one',revision,self.actor))
        wrapper=self.s.evidence(object_id=self.s.row('evidence_items',refs[0])['origin_object_id'])
        with self.assertRaises(Conflict):self.p.trust(self.actor,'behavior','reliability',{},1,[wrapper],'duplicate','two',self.p.revision(),self.actor)
        with self.assertRaises(Conflict):self.p.trust(self.actor,'behavior','reliability',{},1,self.evidence(),'stale','three',revision,self.actor)

    def test_repair_needs_two_new_positive_sources_and_retains_negative(self):
        self.enable();self.trust(outcome=0);self.trust(outcome=1)
        with self.assertRaises(Conflict):self.repair()
        self.trust(outcome=1);self.assertEqual(self.p.projected_state(self.actor),'disputed');repair=self.repair()
        cell=self.p.cells(self.actor)[0];self.assertFalse(cell['unresolved']);self.assertEqual(cell['beta'],2);self.assertAlmostEqual(cell['estimate'],.6)
        self.assertEqual(self.p.projected_state(self.actor),'active');self.assertEqual(len(repair['supports']),2)

    def test_other_unresolved_domain_remains_disputed(self):
        self.enable();self.trust(outcome=0);self.trust(outcome=0,domain='coding',dimension='ability');self.trust(outcome=1);self.trust(outcome=1);self.repair()
        self.assertEqual(self.p.projected_state(self.actor),'disputed');self.assertEqual(sum(c['unresolved'] for c in self.p.cells(self.actor)),1)

    def test_new_negative_reopens_and_invalid_repair_support_is_not_used(self):
        self.enable();self.trust(outcome=0);one=self.trust(outcome=1);self.trust(outcome=1);self.repair()
        self.p.invalidate(one['id'],'wrong support','withdraw-support',self.actor)
        self.assertTrue(self.p.cells(self.actor)[0]['unresolved']);self.assertEqual(self.p.projected_state(self.actor),'disputed')
        self.trust(outcome=0);self.assertTrue(self.p.cells(self.actor)[0]['unresolved'])

    def test_dormant_or_ended_relation_not_reactivated_by_repair(self):
        self.enable();self.trust(outcome=0);self.trust(outcome=1);self.trust(outcome=1)
        self.s.db.execute("UPDATE social_relationships SET state='ended' WHERE actor_id=?",(self.actor,));self.repair()
        self.assertEqual(self.p.projected_state(self.actor),'ended')

    def test_alias_change_after_prepare_prevents_model_dispatch(self):
        self.enable();person=self.register();a,_,_=self.prepare('陈明')
        self.p.alias(person['actor'],'小陈','global',self.evidence(2),'alias-new',self.actor);model=Model()
        with self.assertRaises(Forbidden):self.e.think(a,model)
        self.assertFalse(model.inputs)

    def test_change_during_generation_cannot_be_accepted(self):
        self.enable();a,_,_=self.prepare();outer=self
        class Changed(Model):
            def generate(self,p):outer.trust(outcome=0);return super().generate(p)
        result=self.e.think(a,Changed());self.assertFalse(result['accepted'])

    def test_memory_permission_withdrawal_removes_trust_and_invalidates_input(self):
        from digital_life.application.services.memory import Memory
        self.enable();evidence=self.evidence()[0];memory=Memory(self.s).encode('private relation evidence',evidence);ref=self.s.evidence(object_id=memory['revision_id'])
        self.p.trust(self.actor,'behavior','reliability',{},1,[ref],'reported','private',self.p.revision(),self.actor)
        a,_,_=self.prepare();Memory(self.s).restrict(memory['memory_id'],[self.actor],self.actor)
        self.assertFalse(self.p.cells(self.actor));model=Model()
        with self.assertRaises(Forbidden):self.e.think(a,model)
        self.assertFalse(model.inputs)

    def test_erased_signal_hides_alias_without_deleting_history(self):
        self.enable();person=self.register();refs=self.evidence(2);self.p.alias(person['actor'],'小陈','global',refs,'alias',self.actor)
        signal=self.s.row('evidence_items',refs[0])['origin_object_id'];artifact=self.s.artifact({'redacted_by':'controller'})
        self.s.db.execute('UPDATE perception_signals SET artifact_id=? WHERE id=?',(artifact,signal))
        self.assertEqual(self.p.resolve('小陈')['status'],'unknown');self.assertEqual(len(self.s.rows('world_entity_aliases')),1)

    def test_unique_name_alone_does_not_bind_cognitive_subject(self):
        CognitiveUpdates(self.s).configure(True,self.actor);self.enable();person=self.register();a,_,_=self.prepare('陈明是植物学家',CognitiveModel());self.e.think(a,CognitiveModel())
        belief=self.s.rows('cognition_beliefs')[0];self.assertNotEqual(belief['subject_ref'],person['entity'])
        self.assertEqual(self.s.row('world_entities',belief['subject_ref'])['resolution_status'],'unresolved')

    def test_reviewed_scoped_alias_binds_real_cognitive_output(self):
        CognitiveUpdates(self.s).configure(True,self.actor);self.enable();person=self.register()
        self.p.alias(person['actor'],'陈明','user',self.evidence(2),'reviewed-name',self.actor)
        a,_,_=self.prepare('陈明是植物学家',CognitiveModel());self.e.think(a,CognitiveModel())
        self.assertEqual(self.s.rows('cognition_beliefs')[0]['subject_ref'],person['entity'])
        self.assertEqual(self.s.rows('cognition_belief_revisions')[0]['acceptance_state'],'held')

    def test_ambiguous_and_unknown_claims_do_not_merge_across_activities(self):
        CognitiveUpdates(self.s).configure(True,self.actor);self.enable();self.register();self.register()
        entities=[]
        for _ in range(2):
            a,_,_=self.prepare('陈明是植物学家',CognitiveModel());self.e.think(a,CognitiveModel())
            bound=self.p.events('subject_bound')[-1];entities.append(bound['entity']);self.assertFalse(bound['reviewed_binding'])
        self.assertNotEqual(*entities);self.assertEqual(len(self.s.rows('cognition_beliefs')),2)

    def test_reopen_preserves_identity_memory_graph_and_snapshots(self):
        self.enable();person=self.register();self.p.alias(person['actor'],'小陈','global',self.evidence(2),'alias',self.actor);a,request,p=self.prepare('小陈')
        self.e.think(a,Model());identity=self.s.instance_id;memories=len(self.s.rows('memory_revisions'));self.s.close();self.s=Store(self.root);self.addCleanup(self.s.close);self.p=PeopleRelations(self.s)
        self.assertEqual(self.s.instance_id,identity);self.assertEqual(len(self.s.rows('memory_revisions')),memories);self.assertEqual(self.p.resolve('小陈')['status'],'unique_candidate')
        self.assertEqual(self.s.read_artifact(request['request_artifact_id']),p);self.assertEqual(self.s.integrity()['foreign_keys'],[])

    def test_cli_status_resolve_are_pure_and_configure_does_not_wake(self):
        from digital_life.entrypoints.growth import parsers,handle
        parser=argparse.ArgumentParser();parsers(parser.add_subparsers(dest='command'))
        handle(self.s,parser.parse_args(['people-relations','enable']));before=len(self.s.rows('runtime_events'))
        result=handle(self.s,parser.parse_args(['people-relations','status']));handle(self.s,parser.parse_args(['people-relations','resolve','--name','unknown']))
        self.assertFalse(result['inference_started']);self.assertEqual(before,len(self.s.rows('runtime_events')));self.assertTrue((self.root/'WAKE_DISABLED').exists())
        self.unlock()
        with self.assertRaises(Conflict):self.enable()

    def test_authority_invalid_conditions_and_binary_outcomes(self):
        self.enable()
        with self.assertRaises(Forbidden):self.p.register('spoof',self.evidence(),'spoof','model')
        for condition in ({'script':'arbitrary code'},{'source':''},{'task_contains':True}):
            with self.assertRaises(ContractError):self.p.trust(self.actor,'behavior','reliability',condition,1,self.evidence(),'invalid','bad-'+identifier(),self.p.revision(),self.actor)
        for outcome in (True,.5,2):
            with self.assertRaises(ContractError):self.p.trust(self.actor,'behavior','reliability',{},outcome,self.evidence(),'invalid','bad-'+identifier(),self.p.revision(),self.actor)

    def test_same_named_people_are_disambiguated_only_in_reviewed_scope(self):
        CognitiveUpdates(self.s).configure(True,self.actor);self.enable();one=self.register();two=self.register()
        self.p.alias(one['actor'],'陈明','chat:work',self.evidence(2),'work-binding',self.actor)
        self.assertEqual(self.p.resolve('陈明')['status'],'ambiguous')
        a,_,_=self.prepare('陈明是植物学家',CognitiveModel(),source='chat:work');self.e.think(a,CognitiveModel())
        self.assertEqual(self.s.rows('cognition_beliefs')[0]['subject_ref'],one['entity'])
        self.assertNotEqual(one['entity'],two['entity'])

    def test_unknown_subjects_are_activity_local(self):
        CognitiveUpdates(self.s).configure(True,self.actor);self.enable()
        for _ in range(2):
            a,_,_=self.prepare('陈明是植物学家',CognitiveModel());self.e.think(a,CognitiveModel())
        subjects={b['subject_ref'] for b in self.s.rows('cognition_beliefs')};self.assertEqual(len(subjects),2)
        self.assertTrue(all(self.s.row('world_entities',s)['resolution_status']=='unresolved' for s in subjects))

    def test_invalidated_source_cannot_be_rewrapped_and_counted_again(self):
        self.enable();event=self.trust(outcome=0);self.p.invalidate(event['id'],'correction','correct',self.actor)
        self.assertFalse(self.p.cells(self.actor))
        with self.assertRaises(Conflict):self.p.trust(self.actor,'behavior','reliability',{},1,event['evidence'],'reuse','reuse',self.p.revision(),self.actor)

    def test_pre_negative_positive_records_do_not_justify_repair(self):
        self.enable();self.trust(outcome=1);self.trust(outcome=1);self.trust(outcome=0)
        with self.assertRaises(Conflict):self.repair()
        self.trust(outcome=1)
        with self.assertRaises(Conflict):self.repair()
        self.assertEqual(self.p.projected_state(self.actor),'disputed')

    def test_invalidated_labels_are_not_current_but_history_remains(self):
        self.enable();person=self.register();label=self.p.relate(person['actor'],'朋友',self.evidence(2),'friend',self.actor)
        self.assertTrue(self.p.describe(person['actor'])['labels'])
        self.p.invalidate(label['id'],'incorrect label','no-friend',self.actor)
        self.assertFalse(self.p.describe(person['actor'])['labels']);self.assertEqual(len(self.s.rows('social_relationship_changes')),1)

    def test_legacy_scalar_is_preserved_not_misused_as_observation_counts(self):
        from digital_life.application.services.relationships import Relationships
        old=Relationships(self.s).assess_trust(self.actor,'behavior','reliability',.99,self.evidence()[0])
        self.enable();BehaviorPolicy(self.s).configure(True,self.actor);_,_,p=self.prepare()
        self.assertIsNone(p['relationships']['behavior_reliability']);self.assertTrue(p['behavior_policy']['features']['relationship.reliability']['missing'])
        self.assertEqual(self.s.row('social_trust_assessments',old)['estimate'],.99)

    def test_two_identical_artifact_sources_are_not_independent_alias_evidence(self):
        self.enable();person=self.register();artifact=self.s.artifact({'same':'source'})
        refs=[self.s.evidence(artifact=artifact) for _ in range(2)]
        with self.assertRaises(ContractError):self.p.alias(person['actor'],'alias','global',refs,'same-artifact',self.actor)

    def test_disabled_managed_trust_does_not_leak_into_legacy_policy(self):
        self.enable();BehaviorPolicy(self.s).configure(True,self.actor);self.trust(outcome=1)
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.root,self.s.instance_id);c.stop('disable');c.close();self.p.configure(False,self.actor)
        _,_,payload=self.prepare();self.assertNotIn('relationships',payload)
        self.assertTrue(payload['behavior_policy']['features']['relationship.reliability']['missing'])
        self.assertEqual(len(self.s.rows('social_trust_assessments')),1)

    def test_shipped_condition_and_cli_initial_revision(self):
        from digital_life.entrypoints.growth import parsers,handle
        parser=argparse.ArgumentParser();parsers(parser.add_subparsers(dest='command'))
        handle(self.s,parser.parse_args(['people-relations','enable']))
        file=Path(__file__).resolve().parents[1]/'config/examples/relationship-condition.json'
        result=handle(self.s,parser.parse_args(['people-relations','trust','--person',self.actor,'--domain','behavior','--condition',str(file),'--outcome','1','--evidence',self.evidence()[0],'--reason','fixture annotation','--key','first','--expected-revision','none']))
        self.assertEqual(result['condition'],json.loads(file.read_text()));self.assertTrue((self.root/'WAKE_DISABLED').exists())
        self.assertTrue(self.p.applies(result['condition'],{'source':'user','task':'review file'}))
        self.assertFalse(self.p.applies(result['condition'],{'source':'user','task':'Review file'}))

    def test_revoked_registration_hides_candidate_and_retains_entity(self):
        self.enable();person=self.register();self.p.invalidate(person['id'],'wrong person record','withdraw-person',self.actor)
        self.assertEqual(self.p.resolve('陈明')['status'],'unknown');self.assertEqual(self.s.row('world_entities',person['entity'])['canonical_name'],'陈明')
        self.assertIn(self.actor,self.p.actors());self.assertIn(self.s.config()['self_actor'],self.p.actors())

    def test_candidate_context_exposes_identity_claim_provenance(self):
        self.enable();person=self.register();refs=self.evidence(2);alias=self.p.alias(person['actor'],'小陈','user',refs,'alias-provenance',self.actor)
        _,_,payload=self.prepare('请询问小陈');candidate=payload['relationships']['mentions'][0]['candidates'][0]
        self.assertEqual(candidate['registration_sources'][0]['assertion'],person['id'])
        self.assertEqual(candidate['aliases'][0]['assertion'],alias['id']);self.assertEqual(candidate['aliases'][0]['evidence'],refs)
