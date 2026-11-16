"""T10 source-bound consolidation, live retrieval quality and managed erasure."""
import argparse
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.memory.memory_quality import MemoryQuality,INDEX
from digital_life.application.services.memory import Memory


class Model:
    name='fixture'
    def __init__(self,reply='fixture response'):self.inputs=[];self.reply=reply
    def generate(self,p):self.inputs.append(p);return {'schema_version':1,'explanation':self.reply,'action':{'tool':'wait','arguments':{'reason':'review'}}}


class MemoryQualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'isolated'
        self.s=Store.prepare(self.root);self.addCleanup(self.s.close);self.q=MemoryQuality(self.s);self.e=Engine(self.s);self.m=Memory(self.s);self.actor=self.s.config()['controller'];self.counter=0
        self.ev=self.s.evidence(artifact=self.s.artifact({'fixture':'explicit-authored-data'}))
    def enable(self):self.q.configure(True,self.actor)
    def mem(self,content):return self.m.encode(content,self.ev)
    def unlock(self):
        (self.root/'WAKE_DISABLED').unlink(missing_ok=True)
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.root,self.s.instance_id);c.resume('isolated-t10-'+identifier());c.close()
    def activity(self,task='probe'):
        self.counter+=1;a=self.e.submit(task,'task-'+str(self.counter));return a,self.e.details(a)[1]['id']
    def recall(self,query,limit=8):
        a,c=self.activity('retrieval probe');return self.m.retrieve(query,a,c,limit)
    def parts(self,rows):return [{'revision':r['revision_id'],'start':0,'end':len(self.s.row('memory_revisions',r['revision_id'])['content'])} for r in rows]
    def consolidate(self,rows):
        p=self.q.plan(self.parts(rows),'plan-'+identifier(),self.actor);return self.q.commit(p['id'],self.actor)

    def test_default_off_retains_payload_and_legacy_recall(self):
        self.mem('liwei likes green');a,c=self.activity('liwei');self.unlock();_,p=self.e.prepare(a,Model())
        self.assertNotIn('memory_quality',p);self.assertTrue(p['selected_memories']);self.assertFalse((self.root/INDEX).exists())

    def test_extractive_plan_explicit_commit_preserves_sources_and_identity(self):
        self.enable();a=self.mem('liwei likes green');b=self.mem('liwei studies plants');identity=self.s.instance_id;before=len(self.s.rows('memory_revisions'))
        plan=self.q.plan(self.parts([a,b]),'one',self.actor);self.assertEqual(len(self.s.rows('memory_revisions')),before)
        self.assertNotIn('liwei',json.dumps(plan));summary=self.q.commit(plan['id'],self.actor)
        self.assertEqual(self.s.row('memory_revisions',summary['revision_id'])['content'],'liwei likes green\nliwei studies plants')
        self.assertEqual(self.s.instance_id,identity);self.assertEqual(self.s.row('memory_items',a['memory_id'])['state'],'active')
        recalled=self.recall('liwei');self.assertTrue(any(r['source_kind']=='extractive-summary' for r in recalled['items']))
        self.assertEqual(self.q.commit(plan['id'],self.actor)['memory_id'],summary['memory_id'])

    def test_span_validation_and_plan_idempotency(self):
        self.enable();a=self.mem('alpha');b=self.mem('beta');parts=self.parts([a,b]);p=self.q.plan(parts,'same',self.actor)
        self.assertEqual(self.q.plan(parts,'same',self.actor)['id'],p['id'])
        for bad in ([parts[0],parts[0]],[dict(parts[0],start=True),parts[1]],[dict(parts[0],end=999),parts[1]]):
            with self.assertRaises(ContractError):self.q.plan(bad,identifier(),self.actor)
        with self.assertRaises(Conflict):self.q.plan(list(reversed(parts)),'same',self.actor)
        with self.assertRaises(Forbidden):self.q.plan(parts,'bad','model')

    def test_source_revision_change_rejects_old_plan_and_old_summary(self):
        self.enable();a=self.mem('alpha old');b=self.mem('beta');plan=self.q.plan(self.parts([a,b]),'pending',self.actor);summary=self.consolidate([a,b])
        new=self.m.revise(a['memory_id'],1,'alpha corrected',self.ev)
        with self.assertRaises(Conflict):self.q.commit(plan['id'],self.actor)
        ids=[r['revision_id'] for r in self.recall('alpha')['items']]
        self.assertIn(new,ids);self.assertNotIn(a['revision_id'],ids);self.assertNotIn(summary['revision_id'],ids)
        self.assertEqual(self.s.row('memory_revisions',a['revision_id'])['content'],'alpha old')

    def test_dynamic_source_permission_intersection_after_consolidation(self):
        self.enable();a=self.mem('private alpha');b=self.mem('beta');summary=self.consolidate([a,b])
        self.m.restrict(a['memory_id'],[self.actor],self.actor)
        self.assertNotIn(self.s.config()['self_actor'],self.m.readers(summary['memory_id']))
        self.assertNotIn(summary['revision_id'],[r['revision_id'] for r in self.recall('private')['items']])

    def test_new_public_memory_does_not_inherit_unrelated_private_policy(self):
        a=self.mem('private');self.m.restrict(a['memory_id'],[self.actor],self.actor);b=self.mem('public')
        self.assertIn(self.s.config()['self_actor'],self.m.readers(b['memory_id']))

    def test_dependency_cycle_fails_closed(self):
        a=self.mem('alpha');b=self.mem('beta')
        self.s.insert('memory_relations',from_memory_id=a['memory_id'],to_memory_id=b['memory_id'],relation_type='derived_from',evidence_id=self.ev)
        self.s.insert('memory_relations',from_memory_id=b['memory_id'],to_memory_id=a['memory_id'],relation_type='derived_from',evidence_id=self.ev)
        self.assertEqual(self.m.readers(a['memory_id']),set());self.assertFalse(self.recall('alpha')['items'])

    def test_conflicts_are_labelled_and_not_resolved_as_truth(self):
        self.enable();a=self.mem('liwei likes blue');b=self.mem('liwei likes green')
        conflict=self.q.conflict(a['revision_id'],b['revision_id'],[self.ev],'controller labels differing reports','conflict',self.actor)
        items=self.recall('liwei')['items'];both=[r for r in items if r['revision_id'] in (a['revision_id'],b['revision_id'])]
        self.assertEqual(len(both),2);self.assertTrue(all(r['conflicts'][0]['assertion']==conflict['id'] for r in both))
        self.assertEqual(self.s.row('memory_revisions',a['revision_id'])['content'],'liwei likes blue')

    def test_source_conflict_propagates_to_extractive_summary(self):
        self.enable();a=self.mem('liwei likes blue');b=self.mem('liwei likes green');summary=self.consolidate([a,b])
        self.q.conflict(a['revision_id'],b['revision_id'],[self.ev],'unresolved reports','conflict',self.actor)
        self.assertTrue(self.q.annotations(summary['revision_id'],self.s.config()['self_actor']))

    def test_conflict_does_not_disclose_unreadable_counterpart(self):
        self.enable();a=self.mem('public alpha');b=self.mem('private beta');self.q.conflict(a['revision_id'],b['revision_id'],[self.ev],'private relationship','conflict',self.actor)
        self.m.restrict(b['memory_id'],[self.actor],self.actor)
        self.assertFalse(self.q.annotations(a['revision_id'],self.s.config()['self_actor']))

    def test_demote_changes_rank_without_deleting_history(self):
        self.enable();a=self.mem('topic alpha');b=self.mem('topic beta')
        self.q.retain(b['memory_id'],'demote',self.q.retention_revision(b['memory_id']),'demote','low priority',self.actor,0)
        items=self.recall('topic')['items'];self.assertEqual(items[0]['revision_id'],a['revision_id'])
        self.assertEqual(self.s.row('memory_items',b['memory_id'])['state'],'active');self.assertEqual(self.s.row('memory_revisions',b['revision_id'])['content'],'topic beta')

    def test_archive_restore_and_source_summary_visibility(self):
        self.enable();a=self.mem('alpha');b=self.mem('beta');summary=self.consolidate([a,b])
        self.q.retain(a['memory_id'],'archive',self.q.retention_revision(a['memory_id']),'archive','not default recall',self.actor)
        self.assertNotIn(summary['revision_id'],[r['revision_id'] for r in self.recall('alpha')['items']])
        self.q.retain(a['memory_id'],'restore',self.q.retention_revision(a['memory_id']),'restore','reviewed',self.actor)
        self.assertIn(summary['revision_id'],[r['revision_id'] for r in self.recall('alpha')['items']])

    def test_retention_cas_idempotency_and_no_restoring_deleted(self):
        self.enable();a=self.mem('alpha');version=self.q.retention_revision(a['memory_id'])
        first=self.q.retain(a['memory_id'],'retract',version,'one','reviewed',self.actor)
        self.assertEqual(self.q.retain(a['memory_id'],'retract',version,'one','reviewed',self.actor)['id'],first['id'])
        with self.assertRaises(Conflict):self.q.retain(a['memory_id'],'restore',version,'stale','stale',self.actor)
        self.m.redact(a['memory_id'],self.actor)
        with self.assertRaises(Forbidden):self.q.retain(a['memory_id'],'restore',self.q.retention_revision(a['memory_id']),'deleted','deleted',self.actor)

    def test_index_tracks_new_revisions_and_permissions(self):
        self.enable();a=self.mem('uniquealphatoken');self.q.rebuild(self.actor);a2=self.mem('uniquebetatoken')
        result=self.recall('uniquebetatoken');self.assertTrue(result['quality']['synced']);self.assertEqual(result['quality']['updated_memories'],2);self.assertEqual(result['items'][0]['revision_id'],a2['revision_id'])
        revised=self.m.revise(a['memory_id'],1,'uniquecorrectedtoken',self.ev)
        result=self.recall('uniquecorrectedtoken');self.assertEqual(result['items'][0]['revision_id'],revised)
        self.m.restrict(a['memory_id'],[self.actor],self.actor);self.assertNotIn(revised,[r['revision_id'] for r in self.recall('uniquecorrectedtoken')['items']])

    def test_index_transaction_rollback_cannot_hide_committed_data(self):
        self.enable();a=self.mem('committedtoken');activity,context=self.activity()
        with self.assertRaises(RuntimeError):
            with self.s.tx():
                self.mem('rollbacktoken');self.m.retrieve('rollbacktoken',activity,context);raise RuntimeError('rollback source transaction')
        result=self.m.retrieve('committedtoken',activity,context);self.assertTrue(result['quality']['rebuilt']);self.assertEqual(result['items'][0]['revision_id'],a['revision_id'])
        self.assertFalse(any('rollbacktoken' in r['content'] for r in result['items']))

    def test_index_fault_falls_back_to_real_source_scan(self):
        self.enable();a=self.mem('fallbacktoken')
        with patch.object(MemoryQuality,'_index',side_effect=sqlite3.DatabaseError('fixture failure')):result=self.recall('fallbacktoken')
        self.assertEqual(result['quality']['mode'],'scan-fallback');self.assertEqual(result['items'][0]['revision_id'],a['revision_id'])

    def test_prepared_request_checks_revised_or_revoked_memory_even_when_off(self):
        a=self.mem('liwei background');activity,_=self.activity('liwei');self.unlock();self.e.prepare(activity,Model());self.m.restrict(a['memory_id'],[self.actor],self.actor);m=Model()
        with self.assertRaises(Forbidden):self.e.think(activity,m)
        self.assertFalse(m.inputs)

    def test_new_unrelated_memory_does_not_invalidate_selected_snapshot(self):
        self.enable();self.mem('liwei background');a,_=self.activity('liwei');self.unlock();_,payload=self.e.prepare(a,Model())
        self.mem('unrelated new event');m=Model();result=self.e.think(a,m)
        self.assertTrue(result['accepted']);self.assertEqual(len(m.inputs),1);self.assertEqual(m.inputs[0],payload)

    def test_generated_response_dependencies_are_current_and_private(self):
        self.enable();a=self.mem('liwei private preference');activity,_=self.activity('liwei');self.unlock();self.e.think(activity,Model('paraphrased preference response'))
        response=next(r for r in self.s.rows('memory_revisions') if r['content']=='paraphrased preference response')
        self.assertTrue(self.q.dependencies(response['memory_id']))
        self.m.restrict(a['memory_id'],[self.actor],self.actor);self.assertNotIn(self.s.config()['self_actor'],self.m.readers(response['memory_id']))

    def test_changed_conflict_invalidates_prepared_quality_manifest(self):
        self.enable();a=self.mem('liwei blue');b=self.mem('liwei green');activity,_=self.activity('liwei');self.unlock();self.e.prepare(activity,Model())
        self.q.conflict(a['revision_id'],b['revision_id'],[self.ev],'new conflict','new',self.actor);model=Model()
        with self.assertRaises(Forbidden):self.e.think(activity,model)
        self.assertFalse(model.inputs)

    def test_managed_erasure_cleans_excerpt_dependencies_and_index(self):
        from digital_life.application.accounts.privacy import Privacy
        self.enable();a=self.mem('uniqueprivatefragment with unrelated extra text');b=self.mem('public beta')
        parts=self.parts([a,b]);parts[0]['end']=len('uniqueprivatefragment');p=self.q.plan(parts,'partial',self.actor);summary=self.q.commit(p['id'],self.actor)
        self.q.rebuild(self.actor);self.assertTrue((self.root/INDEX).exists())
        result=Privacy(self.s).erase(a['memory_id'],self.actor)
        self.assertEqual(result['state'],'verified');self.assertFalse((self.root/INDEX).exists())
        self.assertEqual(self.s.row('memory_items',summary['memory_id'])['state'],'deleted')
        self.assertFalse(any(b'uniqueprivatefragment' in path.read_bytes() for path in (self.root/'blobs').iterdir() if path.is_file()))
        self.assertFalse(b'uniqueprivatefragment' in (self.root/'runtime.sqlite').read_bytes(),'managed database still contains deleted fragment')

    def test_ten_thousand_real_memory_rows_quality_and_bounded_candidates(self):
        self.enable();start=time.perf_counter();targets=[]
        with self.s.tx():
            for i in range(10000):
                memory=self.mem('payload%05d authored corpus record'%i)
                if i in (1,9999):targets.append(memory['memory_id'])
        seed_ms=(time.perf_counter()-start)*1000
        cases=[{'query':'payload00001','relevant':[targets[0]]},{'query':'payload09999','relevant':[targets[1]]}]
        report=self.q.evaluate(cases,self.actor,k=1)
        self.assertEqual(report['mean'],{'precision':1.,'recall':1.,'mrr':1.,'ndcg':1.})
        self.assertTrue(all(r['retrieval']['checked_candidates']<=2008 for r in report['cases']))
        activity,context=self.activity();self.m.retrieve('payload00001',activity,context,1)
        start=time.perf_counter();warm=self.m.retrieve('payload00001',activity,context,1);warm_ms=(time.perf_counter()-start)*1000
        with patch.object(MemoryQuality,'candidates',return_value=(None,{'mode':'scan-reference'})):
            start=time.perf_counter();scan=self.m.retrieve('payload00001',activity,context,1);scan_ms=(time.perf_counter()-start)*1000
        self.assertEqual(warm['items'][0]['revision_id'],scan['items'][0]['revision_id'])
        self.assertNotIn(b'payload00001',(self.root/INDEX).read_bytes())
        bounded=self.m.retrieve('authored',activity,context,5)
        self.assertTrue(bounded['quality']['candidate_truncated']);self.assertLessEqual(bounded['quality']['checked_candidates'],2008)
        appended=self.mem('newlyappendedtoken');start=time.perf_counter();delta=self.m.retrieve('newlyappendedtoken',activity,context,1);delta_ms=(time.perf_counter()-start)*1000
        self.assertTrue(delta['quality']['synced']);self.assertEqual(delta['quality']['updated_memories'],1);self.assertEqual(delta['items'][0]['revision_id'],appended['revision_id'])
        self.benchmark_report={'incremental_query_ms':delta_ms,'incremental_updated_memories':delta['quality']['updated_memories'],'truncated_query':bounded['quality'],'corpus_memories':10000,'seed_ms':seed_ms,'quality':report,'warm_index_ms':warm_ms,'same_ranking_scan_ms':scan_ms,'warm_candidates':warm['quality']['checked_candidates'],'model_calls':0}

    def test_cli_status_is_pure_and_configuration_never_wakes(self):
        from digital_life.entrypoints.growth import parsers,handle
        parser=argparse.ArgumentParser();parsers(parser.add_subparsers(dest='command'))
        handle(self.s,parser.parse_args(['memory-quality','enable']));before=len(self.s.rows('runtime_events'))
        result=handle(self.s,parser.parse_args(['memory-quality','status']))
        self.assertFalse(result['inference_started']);self.assertEqual(before,len(self.s.rows('runtime_events')));self.assertTrue((self.root/'WAKE_DISABLED').exists())
        self.unlock()
        with self.assertRaises(Conflict):self.enable()

    def test_managed_backup_and_paraphrased_response_are_erased_together(self):
        from digital_life.application.accounts.privacy import Privacy
        from digital_life.application.memory.data_management import backup_bundle
        from digital_life.application.lifecycle.control_plane import Control
        self.enable();source=self.mem('liwei uniqueprivateorigin whole source text');activity,_=self.activity('liwei');self.unlock();self.e.think(activity,Model('different paraphrased sensitive detail'))
        response=next(r for r in self.s.rows('memory_revisions') if r['content']=='different paraphrased sensitive detail')
        self.q.rebuild(self.actor);backup=Path(self.tmp.name)/'registered-backup';backup_bundle(self.s,backup)
        c=Control(self.root,self.s.instance_id);c.stop('erase-isolated');c.close();report=Privacy(self.s).erase(source['memory_id'],self.actor,True)
        self.assertEqual(report['managed_backups'],1);self.assertEqual(self.s.row('memory_items',response['memory_id'])['state'],'deleted')
        self.assertFalse((self.root/INDEX).exists());copy=Store(backup)
        try:
            self.assertEqual(copy.row('memory_items',response['memory_id'])['state'],'deleted')
            self.assertFalse(any(b'different paraphrased sensitive detail' in p.read_bytes() for p in (backup/'blobs').iterdir() if p.is_file()))
        finally:copy.close()

    def test_disabled_interval_reindexes_new_content_after_reenable(self):
        self.enable();self.mem('beforetoken');self.q.rebuild(self.actor);self.q.configure(False,self.actor)
        added=self.mem('duringdisabledtoken');self.q.configure(True,self.actor)
        recalled=self.recall('duringdisabledtoken');self.assertEqual(recalled['items'][0]['revision_id'],added['revision_id']);self.assertTrue(recalled['quality']['rebuilt'])

    def test_index_symlink_does_not_touch_external_file(self):
        self.enable();a=self.mem('symlinkfallbacktoken');outside=Path(self.tmp.name)/'unrelated';outside.write_text('keep this file')
        (self.root/INDEX).symlink_to(outside);result=self.recall('symlinkfallbacktoken')
        self.assertEqual(result['quality']['mode'],'scan-fallback');self.assertEqual(result['items'][0]['revision_id'],a['revision_id'])
        self.assertEqual(outside.read_text(),'keep this file')

    def test_configuration_change_prevents_old_request_model_call(self):
        from digital_life.application.lifecycle.control_plane import Control
        self.enable();self.mem('liwei');a,_=self.activity('liwei');self.unlock();self.e.prepare(a,Model())
        c=Control(self.root,self.s.instance_id);c.stop('config');c.close();self.q.configure(False,self.actor);self.unlock();model=Model()
        with self.assertRaises(Forbidden):self.e.think(a,model)
        self.assertFalse(model.inputs)

    def test_source_revocation_during_generation_is_not_accepted(self):
        self.enable();memory=self.mem('liwei preference');a,_=self.activity('liwei');self.unlock();outer=self
        class Withdraw(Model):
            def generate(self,p):outer.m.restrict(memory['memory_id'],[outer.actor],outer.actor);return super().generate(p)
        result=self.e.think(a,Withdraw());self.assertFalse(result['accepted']);self.assertEqual(self.s.rows('thought_results')[0]['acceptance'],'stale')

    def test_long_query_records_scan_fallback_instead_of_silent_truncation(self):
        self.enable();self.mem('needle');query=' '.join('term'+str(i) for i in range(150))
        result=self.recall(query);self.assertEqual(result['quality']['mode'],'scan-fallback');self.assertEqual(result['quality']['reason'],'query-token-budget')

    def test_evaluation_rejects_invalid_gold_or_repeated_queries(self):
        self.enable();a=self.mem('alpha')
        with self.assertRaises(ContractError):self.q.evaluate([{'query':'same','relevant':[a['memory_id']]}]*2,self.actor)
        with self.assertRaises(ContractError):self.q.evaluate([{'query':'a','relevant':[]},{'query':'b','relevant':[a['memory_id']]}],self.actor)
        with self.assertRaises(Forbidden):self.q.evaluate([], 'model')

    def test_preview_is_reviewable_without_persisting_excerpt_copies(self):
        self.enable();a=self.mem('alpha text');b=self.mem('beta text');plan=self.q.plan(self.parts([a,b]),'preview',self.actor)
        events=len(self.s.rows('runtime_events'));artifacts=len(self.s.rows('artifacts'));preview=self.q.preview(plan['id'],self.actor)
        self.assertEqual(preview['content'],'alpha text\nbeta text');self.assertFalse(preview['persisted_preview'])
        self.assertEqual(events,len(self.s.rows('runtime_events')));self.assertEqual(artifacts,len(self.s.rows('artifacts')))
        self.m.revise(a['memory_id'],1,'alpha revised',self.ev)
        with self.assertRaises(Conflict):self.q.preview(plan['id'],self.actor)

    def test_chinese_bigrams_and_mixed_name_recall_use_index(self):
        self.enable();one=self.mem('陈明是植物学家');two=self.mem('liwei 喜欢绿色并研究植物')
        results=self.recall('陈明 植物');self.assertEqual(results['items'][0]['revision_id'],one['revision_id']);self.assertEqual(results['quality']['mode'],'hashed-token-index')
        results=self.recall('liwei 绿色');self.assertEqual(results['items'][0]['revision_id'],two['revision_id'])

    def test_erasure_cleans_stale_response_even_without_generated_memory(self):
        from digital_life.application.accounts.privacy import Privacy
        from digital_life.application.lifecycle.control_plane import Control
        self.enable();source=self.mem('liwei complete private source record');a,_=self.activity('liwei');self.unlock();outer=self
        class Stale(Model):
            def generate(self,p):outer.m.restrict(source['memory_id'],[outer.actor],outer.actor);return super().generate(p)
        outcome=self.e.think(a,Stale('a differently worded sensitive response'));self.assertFalse(outcome['accepted'])
        result=self.s.rows('thought_results')[0]
        self.assertFalse(any(r['content']=='a differently worded sensitive response' for r in self.s.rows('memory_revisions')))
        c=Control(self.root,self.s.instance_id);c.stop('erase-stale');c.close();Privacy(self.s).erase(source['memory_id'],self.actor)
        self.assertIn('redacted_by',self.s.read_artifact(result['response_artifact_id']))
        self.assertFalse(any(b'a differently worded sensitive response' in p.read_bytes() for p in (self.root/'blobs').iterdir() if p.is_file()))

    def test_erasure_cleans_known_cognitive_quotes_and_current_literal(self):
        from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
        from digital_life.application.lifecycle.control_plane import Control
        from digital_life.application.accounts.privacy import Privacy
        self.enable();CognitiveUpdates(self.s).configure(True,self.actor);source=self.mem('陈明是植物学家，还有其他来源上下文。');a,_=self.activity('陈明');self.unlock()
        class Cognition(Model):
            def generate(self,p):
                return {'schema_version':3,'explanation':'记录了一条待核实陈述','action':{'tool':'wait','arguments':{'reason':'review'}},'cognition':{'claims':[{'subject':'陈明','predicate':'职业','value':'植物学家','source_ref':source['revision_id'],'quote':'陈明是植物学家','kind':'reported'}],'questions':[],'predictions':[],'plan':[]}}
        self.e.think(a,Cognition());belief=self.s.rows('cognition_beliefs')[0];revision=belief['current_revision_id']
        c=Control(self.root,self.s.instance_id);c.stop('erase-cognitive');c.close();Privacy(self.s).erase(source['memory_id'],self.actor)
        self.assertIn('redacted_by',json.loads(self.s.row('cognition_belief_revisions',revision)['content']))
        self.assertIn('redacted_by',json.loads(self.s.row('cognition_beliefs',belief['id'])['literal']))
        self.assertFalse(CognitiveUpdates(self.s).snapshot())
