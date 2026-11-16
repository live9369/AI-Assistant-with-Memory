"""Unified offline integration checks. Temp databases and fake inference/tools only.

No formal instance is opened; no wake/watch/LLM service/HTTP server is started.
"""
import json
from pathlib import Path
import tempfile
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,RuntimeIdentity,utc,ToolResult
from digital_life.application.runtime.engine import Engine
from digital_life.tools import Policy,registry,safe_path
from digital_life.application.services import Memory,Personality,Values,Habits,Relationships,Commitments,States,Cognition,Learning,Health,Rules,Goals
from digital_life.application.runtime.scheduling import Queue
from digital_life.application.lifecycle.control_plane import Control,Releases
from digital_life.entrypoints.http import Application

class FakeModel:
    name='offline-fixture'
    def __init__(self): self.inputs=[]
    def generate(self,request):
        self.inputs.append(request)
        return {'schema_version':1,'action':{'tool':'write_note','arguments':{'path':'notes/'+request['activity_id']+'.txt','text':request['task']}},'explanation':'isolated fixture'}

class FullSystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'instance'
        self.s=Store.prepare(self.root,model_config={'backend':'fixture','model':'offline-fixture'})
        self.c=Control(self.root,self.s.instance_id)
        self.engine=Engine(self.s,RuntimeIdentity(0,'offline-test'))
    def tearDown(self): self.c.close(); self.s.close(); self.tmp.cleanup()
    def offline_test_only_unlock(self):
        # Only this fresh TemporaryDirectory fixture is unlocked, never work/ instances.
        self.assertTrue(str(self.root).startswith(self.tmp.name)); (self.root/'WAKE_DISABLED').unlink()
        self.c.resume('isolated-fixture-resume')
    def fake_tool(self,action,root,operation):
        return ToolResult('received','succeeded','pass',{'fixture':True,'operation':operation})
    def test_bootstrap_full_schema_without_wake(self):
        self.assertTrue((self.root/'WAKE_DISABLED').exists())
        self.assertEqual(self.c.state()['user_stopped'],1)
        self.assertEqual(self.s.integrity(),{'integrity':'ok','foreign_keys':[]})
        self.assertEqual(len(Personality(self.s).current()['traits']),5)
    def test_legacy_import_preserves_source_and_creates_locked_successor(self):
        from primordial00.core import Life
        from digital_life.application.memory.data_management import import_legacy
        from digital_life.domain.contracts import sha
        source=Path(self.tmp.name)/'legacy'
        old=Life.initialize(source)
        old.emit('historical input','legacy-key')
        old.close()
        before=sha((source/'runtime.sqlite').read_bytes())
        target=Path(self.tmp.name)/'imported'
        result=import_legacy(source,target)
        self.assertEqual(before,sha((source/'runtime.sqlite').read_bytes()))
        self.assertTrue(result['wake_disabled'])
        imported=Store(target)
        try:
            self.assertEqual(len(imported.rows('activities')),1)
            self.assertEqual(imported.rows('activities')[0]['state'],'pending')
            self.assertEqual(imported.integrity(),{'integrity':'ok','foreign_keys':[]})
            self.assertNotEqual(imported.instance_id,self.s.instance_id)
        finally: imported.close()
    def test_packaged_schema_matches_generated_baseline(self):
        from digital_life.infrastructure.persistence.sqlite_store import PROJECT,RESOURCES
        for name in ('runtime.sql','supervisor.sql'):
            self.assertEqual((RESOURCES/name).read_bytes(),(PROJECT/'database/system-v2'/name).read_bytes())
    def test_recovery_pauses_without_replaying_or_waking(self):
        from digital_life.application.lifecycle.recovery import Recovery
        activity=self.engine.submit('interrupted','recovery')
        with self.s.tx(): self.engine.transition(activity,'running','fixture-interruption')
        result=Recovery(self.s).reconcile(self.s.config()['controller'])
        self.assertEqual(result['paused'],[activity])
        self.assertFalse(result['automatic_replay'])
        self.assertEqual(self.s.row('activities',activity)['state'],'paused')
        self.assertTrue((self.root/'WAKE_DISABLED').exists())
    def test_deployment_is_blocked_before_process_launch(self):
        from digital_life.application.lifecycle.deployment import Deployment
        class NeverLaunch:
            def launch(self,*args): raise AssertionError('must not launch')
        with self.assertRaises(Forbidden): Deployment(self.c,NeverLaunch()).launch('missing')
    def test_deployment_failed_start_restores_old_with_fake_driver(self):
        from digital_life.application.lifecycle.deployment import Deployment
        source=Path(self.tmp.name)/'release-src'; (source/'digital_life').mkdir(parents=True)
        (source/'digital_life/__init__.py').write_text('VALUE=1\n')
        releases=Releases(self.c); old=releases.stage(source)
        releases.activate(old,lambda _: {'ready':True,'schema_compatible':True})
        (source/'digital_life/__init__.py').write_text('VALUE=2\n'); new=releases.stage(source)
        self.offline_test_only_unlock()
        class FakeDriver:
            def launch(self,path,root,deployment,ready,gate):
                return type('Process',(),{'deployment':deployment,'pid':0})()
            def await_state(self,process,ready,desired,timeout):
                if desired=='running' and process.deployment==new: raise ContractError('fixture startup failure')
                return {'state':desired,'deployment':process.deployment,'schema_compatible':True}
            def stop(self,process): pass
        result=Deployment(self.c,FakeDriver()).launch(new)
        self.assertFalse(result['switched']); self.assertTrue(result['restarted'])
        active=self.c.db.execute("SELECT id FROM deployments WHERE state='active'").fetchone()[0]
        self.assertEqual(active,old)
    def test_locked_instance_can_receive_but_not_think_or_execute(self):
        activity=self.engine.submit('task','key')
        with self.assertRaises(Forbidden): self.engine.think(activity,FakeModel())
        with self.assertRaises(Forbidden): self.c.assert_startable()
    def test_complete_full_schema_pipeline_with_mocked_external_boundaries(self):
        self.offline_test_only_unlock()
        activity=self.engine.submit('persist a reviewed observation','key')
        model=FakeModel(); proposed=self.engine.think(activity,model)
        self.assertTrue(proposed['accepted'])
        self.assertEqual(self.s.row('activities',activity)['state'],'waiting_input')
        Policy(self.s).approve(proposed['approval_id'],self.s.config()['controller'])
        result=self.engine.execute(proposed['action_id'],self.fake_tool)
        self.assertEqual(result['state'],'succeeded')
        self.assertEqual(self.s.row('activities',activity)['state'],'completed')
        self.assertEqual(self.s.integrity()['foreign_keys'],[])
    def test_idempotent_input_and_single_accepted_thought(self):
        self.offline_test_only_unlock(); model=FakeModel()
        activity=self.engine.submit('one','key'); self.assertEqual(activity,self.engine.submit('one','key'))
        with self.assertRaises(Conflict): self.engine.submit('two','key')
        self.engine.think(activity,model); repeated=self.engine.think(activity,model)
        self.assertTrue(repeated['duplicate']); self.assertEqual(len(model.inputs),1)
    def test_parameter_tampering_and_revocation(self):
        self.offline_test_only_unlock()
        activity=self.engine.submit('one','key'); proposal=self.engine.think(activity,FakeModel())
        authorized=Policy(self.s).approve(proposal['approval_id'],self.s.config()['controller'])
        auth=self.s.row('action_authorization_records',authorized['authorization'])
        Policy(self.s).revoke(auth['grant_id'],self.s.config()['controller'])
        with self.assertRaises(Forbidden): self.engine.execute(proposal['action_id'],self.fake_tool)
    def test_cancelled_model_result_not_accepted(self):
        self.offline_test_only_unlock(); activity=self.engine.submit('cancel','key'); outer=self
        class Cancelling(FakeModel):
            def generate(self,request):
                outer.engine.cancel(activity,outer.s.config()['controller']); return super().generate(request)
        result=self.engine.think(activity,Cancelling())
        self.assertFalse(result['accepted']); self.assertEqual(result['reason'],'stale')
    def test_memory_revision_learning_and_redaction(self):
        with self.s.tx():
            artifact=self.s.artifact({'observed':'fact'}); evidence=self.s.evidence(artifact=artifact)
            memory=Memory(self.s).encode('secretword',evidence)
        proposal=Learning(self.s).propose('memory',memory['memory_id'],{'content':'corrected'},evidence)
        Learning(self.s).commit_memory(proposal,1,'corrected',evidence,self.s.config()['controller'])
        self.assertEqual(self.s.row('memory_revisions',self.s.row('memory_items',memory['memory_id'])['current_revision_id'])['revision_no'],2)
        Memory(self.s).redact(memory['memory_id'],self.s.config()['controller'])
        self.assertEqual(self.s.row('memory_items',memory['memory_id'])['state'],'deleted')
    def test_habits_relationships_states_beliefs(self):
        activity=self.engine.submit('evidence','key'); row,context,signal,goal=self.engine.details(activity)
        with self.s.tx(): evidence=self.s.evidence(object_id=signal['id'])
        habit=Habits(self.s).create({'tool':'read_file'},Goals(self.s).rule())
        self.assertEqual(len(Habits(self.s).opportunities(activity,{})),1)
        trust=Relationships(self.s).assess_trust(self.s.config()['controller'],'documents','ability',0.7,evidence)
        self.assertEqual(self.s.row('social_trust_assessments',trust)['estimate'],0.7)
        States(self.s).observe('load',0.2,'ratio',evidence)
        self.assertTrue(States(self.s).snapshot()['load']['fresh'])
        entity=self.s.rows('world_entities')[0]['id']
        belief=Cognition(self.s).belief(entity,'says',{'value':'evidence'},evidence)
        self.assertIsNotNone(self.s.row('cognition_beliefs',belief)['current_revision_id'])
    def test_commitment_requires_evidence(self):
        activity=self.engine.submit('promise','key'); signal=self.engine.details(activity)[2]['id']
        promise=Commitments(self.s).propose(self.s.config()['controller'],'promise',utc(60))
        Commitments(self.s).transition(promise,'confirmed',signal)
        Commitments(self.s).transition(promise,'active',signal)
        with self.assertRaises(ContractError): Commitments(self.s).transition(promise,'fulfilled',signal)
        with self.s.tx(): evidence=self.s.evidence(object_id=signal)
        Commitments(self.s).transition(promise,'fulfilled',signal,evidence)
    def test_lease_fencing_and_consumer_dedup(self):
        activity=self.engine.submit('one','key'); queue=Queue(self.s); job=queue.claim('worker')
        stale=dict(job); stale['lease_token']='wrong'
        with self.assertRaises(Conflict): queue.finish(stale)
        queue.finish(job)
        event=self.s.rows('runtime_events')[0]['id']; calls=[]
        queue.receipt('fixture',event,lambda:calls.append(1)); queue.receipt('fixture',event,lambda:calls.append(2))
        self.assertEqual(calls,[1])
    def test_control_wake_generations_and_stop_survive(self):
        self.c.set_wake('new',2,utc(-1)); self.assertTrue(self.c.set_wake('old',1,utc(60))['stale'])
        refs=self.c.due_wakes(); self.assertEqual(len(refs),1)
        self.assertEqual(self.c.db.execute('SELECT state FROM wake_firings WHERE id=?',(refs[0],)).fetchone()[0],'suppressed')
        self.assertEqual(self.c.due_wakes(),[])
        with self.assertRaises(Forbidden): self.c.resume('resume')
    def test_inbound_handoff_idempotent_without_wake(self):
        inbound=self.c.accept_inbound('fixture','key',{'text':'offline input'},'controller')
        transferred=self.c.transfer_inbound(self.s)
        self.assertEqual(len(transferred),1); self.assertEqual(self.c.transfer_inbound(self.s),[])
        self.assertTrue((self.root/'WAKE_DISABLED').exists())
    def test_api_submission_does_not_execute_inference(self):
        status,result=Application(self.root).dispatch('POST','/v1/events',{'text':'from api','idempotency_key':'key'})
        self.assertEqual(status,202); self.assertFalse(result['inference_started'])
        status,result=Application(self.root).dispatch('GET','/v1/status')
        self.assertTrue(result['wake_disabled']); self.assertEqual(len(self.s.rows('thought_requests')),0)
    def test_rules_three_values_and_path_boundaries(self):
        self.assertIsNone(Rules().evaluate({'op':'eq','left':{'var':'missing'},'right':1},{}))
        self.assertFalse(Rules().evaluate({'op':'and','args':[False,{'var':'missing'}]},{}))
        with self.assertRaises(Forbidden): safe_path(self.root/'workspace','../secret')
    def test_bounded_tools_direct_in_temporary_workspace_only(self):
        tools=registry(); root=self.root/'workspace'
        action={'tool':'write_note','arguments':{'path':'notes/test.txt','text':'hello'}}
        self.assertEqual(tools.invoke(action,root,'op').verification_state,'pass')
        self.assertEqual(tools.invoke(action,root,'op').verification_state,'pass')
        action['arguments']['text']='changed'
        self.assertEqual(tools.invoke(action,root,'op').execution_state,'unknown')
    def test_storage_backup_and_health(self):
        snapshot=self.s.snapshot(self.root/'snapshots'/'test.sqlite')
        self.assertTrue(Path(snapshot['path']).is_file())
        self.assertEqual(Health(self.s).assess()['state'],'healthy')
        (self.root/'workspace').rmdir(); self.assertEqual(Health(self.s).assess()['state'],'degraded')
        self.assertEqual(Health(self.s).restore_workspace(self.s.config()['controller'])['state'],'healthy')

    def evidence_pair(self):
        with self.s.tx():
            a=self.s.evidence(artifact=self.s.artifact({'sample':1}))
            b=self.s.evidence(artifact=self.s.artifact({'sample':2}))
            return [a,b]
    def test_long_term_parameters_are_versioned_and_authorized(self):
        evidence=self.evidence_pair(); actor=self.s.config()['controller']
        update=Personality(self.s).replace({'openness':0.3},evidence,actor)
        self.assertEqual(Personality(self.s).current()['profile']['version'],1)
        with self.assertRaises(Forbidden): Personality(self.s).replace({},evidence[:1],actor)
        current=max(self.s.rows('value_profiles'),key=lambda r:r['version'])
        weights={r['dimension_id']:1 for r in self.s.db.execute('SELECT * FROM value_weights WHERE profile_id=?',(current['id'],))}
        Values(self.s).replace(weights,evidence,actor)
        self.assertEqual(max(r['version'] for r in self.s.rows('value_profiles')),1)
        self.assertEqual(self.s.integrity()['foreign_keys'],[])
    def test_habit_learning_and_cognition_plan(self):
        activity=self.engine.submit('plan','key'); row,context,signal,goal=self.engine.details(activity)
        evidence=self.evidence_pair()[0]
        association=Habits(self.s).create({'tool':'read_file'},Goals(self.s).rule())
        strength=Habits(self.s).update(association,1,evidence,self.s.config()['controller'])
        self.assertAlmostEqual(strength,0.1)
        plan=Cognition(self.s).plan(goal['id'],[{'action':{'tool':'read_file'}},{'action':{'tool':'write_note'},'depends_on':[0]}])
        self.assertEqual(len(plan['steps']),2)
    def test_open_mode_is_explicit_and_scoped(self):
        self.offline_test_only_unlock()
        Policy(self.s).mode('open',['write_note'],self.s.config()['controller'])
        activity=self.engine.submit('policy','key'); result=self.engine.think(activity,FakeModel())
        self.assertEqual(self.s.row('approval_requests',result['approval_id'])['decision'],'approved')
        self.assertEqual(self.s.row('action_intents',result['action_id'])['state'],'queued')
    def test_approval_rejection(self):
        self.offline_test_only_unlock()
        activity=self.engine.submit('reject','key'); result=self.engine.think(activity,FakeModel())
        Policy(self.s).deny(result['approval_id'],self.s.config()['controller'])
        self.assertEqual(self.s.row('action_intents',result['action_id'])['state'],'cancelled')
    def test_atomic_queue_pipeline_and_due_commitment(self):
        self.offline_test_only_unlock()
        activity=self.engine.submit('commit source','key'); signal=self.engine.details(activity)[2]['id']
        promise=Commitments(self.s).propose(self.s.config()['controller'],'deliver reminder',utc(-1))
        Commitments(self.s).transition(promise,'confirmed',signal); Commitments(self.s).transition(promise,'active',signal)
        # Process fixture tasks without creating a Runtime process or calling wake/watch.
        for _ in range(3):
            result=self.engine.process_one(FakeModel(),self.fake_tool)
        links=[r for r in self.s.rows('commitment_goal_links') if r['commitment_id']==promise]
        self.assertEqual(len(links),1)
    def test_backup_restore_remains_locked_and_detects_tampering(self):
        from digital_life.application.memory.data_management import backup_bundle,restore_bundle
        backup=Path(self.tmp.name)/'bundle'; restored=Path(self.tmp.name)/'restored'
        backup_bundle(self.s,backup)
        result=restore_bundle(backup,restored)
        self.assertTrue(result['wake_disabled']); self.assertTrue(result['reconciliation_required'])
        content=next((backup/'blobs').iterdir()); content.write_text('tampered')
        with self.assertRaises(ContractError): restore_bundle(backup,Path(self.tmp.name)/'bad-restored')
    def test_release_failed_verification_retains_old_release(self):
        src=Path(self.tmp.name)/'source'; (src/'digital_life').mkdir(parents=True)
        (src/'digital_life/__init__.py').write_text('VALUE=1\n')
        releases=Releases(self.c); first=releases.stage(src)
        self.assertTrue(releases.activate(first,lambda path:{'ready':True,'schema_compatible':True})['switched'])
        (src/'digital_life/__init__.py').write_text('VALUE=2\n'); second=releases.stage(src)
        result=releases.activate(second,lambda path:{'ready':False,'schema_compatible':True})
        self.assertFalse(result['switched']); self.assertEqual(result['retained'],first)
    def test_sleep_handoff_aborts_on_new_input(self):
        self.offline_test_only_unlock()
        with self.c.tx(): deployment=self.c.insert('deployments',release='fixture',build_hash='fixture',schema_min=2,schema_max=2,state='active')
        identity=self.c.begin_run(deployment)
        handoff=self.c.prepare_sleep(self.s,identity)
        self.c.accept_inbound('fixture','late',{'text':'new input'},'controller')
        self.assertEqual(self.c.commit_sleep(self.s,handoff)['phase'],'aborted')
        self.c.finish_run(identity)

if __name__=='__main__': unittest.main(verbosity=2)
