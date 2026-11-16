"""Fresh synthetic original-work recovery tests; no production authority claim."""
import copy
import unittest
from digital_life.application.learning.recovery import ToolLearningRecovery,RecoveryAuthority
from digital_life.infrastructure.persistence.tool_learning_store import StorageGrant
from digital_life.domain.contracts import Forbidden,Conflict,identifier
from tests.test_tool_learning_work import WorkTests
from tests.test_tool_learning_products import sl


class MechanicalRecovery(RecoveryAuthority):
    def verify(self,entry,operation,request,instance_id,stage):
        if entry!='mechanical-recovery':raise Forbidden('not mechanical recovery channel')
        return StorageGrant('M14',frozenset(('tl_work',)))
    def project_response(self,entry,operation,request,response,instance_id,stage):return response
    def verify_read_accounting(self,*args):pass
    def verify_reconciliation(self,*args):pass
    def verify_conditions(self,*args):pass


class RecoveryTests(WorkTests):
    # Shared setup helpers without inheriting the earlier task's test methods.
    def suspended(self,phase='assess'):
        work_id=self.work_id(self.admit());self.work.transition('synthetic-m14',self.transition_request(work_id),'processing','assess','prepare')
        row=self.s.row('tl_work',work_id)
        if phase=='decide':
            with self.s.tx():self.s.db.execute("UPDATE tl_work SET phase='decide',row_revision=row_revision+1 WHERE id=?",(work_id,))
        row=self.s.row('tl_work',work_id)
        self.work.transition('synthetic-m14',self.transition_request(work_id,'waiting',phase,'external-condition',row['row_revision']),'waiting',phase,'external-condition')
        return work_id
    def request_for(self,key,service):
        work=self.s.row('tl_work',key);request=self.new_request()
        request['work_ref']=sl(self.ref(key),'known')
        request['expected']=sl({'object':self.ref(key),'revision':work['row_revision'],'epoch':0},'known')
        import json
        request['budget']=json.loads(self.s.row('activities',work['learning_activity_id'])['budget_json'])['budget']
        record={'contract':'TL-WORK-RECONCILIATION-1','instance_id':self.s.instance_id,'work_id':key,'expected_work_revision':work['row_revision'],'phase':work['phase'],'review_round':work['review_round'],'conditions':[],'facts':service.facts(key)}
        artifact=self.s.artifact(record)
        request['payload']={'work':self.ref(key),'expected_work_revision':work['row_revision'],'conditions':[],'reconciliation':self.ref(artifact)}
        return request
    def test_resume_preserves_original_account_deadline_and_identity(self):
        key=self.suspended();service=ToolLearningRecovery(self.s,MechanicalRecovery());request=self.request_for(key,service);before=self.s.row('tl_work',key)
        result=service.resume('mechanical-recovery',request);after=self.s.row('tl_work',key)
        self.assertEqual(after['state'],'processing');self.assertEqual(after['phase'],'assess')
        for field in ('id','budget_account_id','deadline','review_round'):self.assertEqual(before[field],after[field])
        self.assertEqual(result,service.resume('mechanical-recovery',request))
    def test_default_recovery_owner_denies(self):
        key=self.suspended();service=ToolLearningRecovery(self.s);request=self.request_for(key,service)
        with self.assertRaises(Forbidden):service.resume('caller',request)
    def test_decide_new_round_keeps_original_work(self):
        key=self.suspended('decide');service=ToolLearningRecovery(self.s,MechanicalRecovery());request=self.request_for(key,service)
        service.resume('mechanical-recovery',request);self.assertEqual(self.s.row('tl_work',key)['review_round'],1)
    def test_stale_cas_refused_without_new_work(self):
        key=self.suspended();service=ToolLearningRecovery(self.s,MechanicalRecovery());request=self.request_for(key,service)
        request['payload']['expected_work_revision']+=1
        with self.assertRaises(Conflict):service.resume('mechanical-recovery',request)
        self.assertEqual(len(self.s.rows('tl_work')),1)

# Inherited tests are covered by their original suite, not recounted here.
for _name in list(vars(WorkTests)):
    if _name.startswith('test_'):setattr(RecoveryTests,_name,None)
del WorkTests


class CurrentPlanContinuationTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_propagation import ControllerMaintenanceIntegrationTests
        self.f=ControllerMaintenanceIntegrationTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.authorized();self.s=self.f.s
        from digital_life.application.learning.recovery import ContinuedErasure
        self.service=ContinuedErasure(self.f.erasure)
    def test_actual_bearer_continuation_preserves_old_plan_targets_and_ledger(self):
        from digital_life.domain.contracts import utc
        old=copy.deepcopy(self.f.erasure._journal(self.f.plan['id'])[1]);deadline=utc(50)
        grant=self.service.authorize(self.f.token,self.f.plan['id'],self.f.caps,deadline,'fixed-new-maintenance-generation')
        repeated=self.service.authorize(self.f.token,self.f.plan['id'],self.f.caps,deadline,'fixed-new-maintenance-generation')
        self.assertEqual(grant['grant_ref'],repeated['grant_ref'])
        result=self.service.run(grant['entries']['M12'],self.f.plan['id'],'fixed-new-maintenance-generation')
        new=self.f.erasure._journal(self.f.plan['id'])[1]
        self.assertTrue(result['local_verified']);self.assertFalse(result['f3_complete']);self.assertFalse(self.f.path.exists())
        for key in ('plan','used','account_id','activity_id','unknown','entered'):self.assertEqual(old[key],new[key])
        targets=self.s.db.execute('SELECT DISTINCT plan_ref_id FROM tl_erasure_target WHERE instance_id=?',(self.s.instance_id,)).fetchall()
        self.assertEqual([r[0] for r in targets],[self.f.plan['id']])
    def test_current_grant_can_continue_expired_old_plan_without_extending_it(self):
        from digital_life.domain.contracts import utc
        old=copy.deepcopy(self.f.plan);future=utc(61);self.f.authority.clock=lambda:future
        grant=self.service.authorize(self.f.token,self.f.plan['id'],self.f.caps,utc(110),'after-old-deadline')
        self.assertTrue(self.service.run(grant['entries']['M12'],self.f.plan['id'],'after-old-deadline')['local_verified'])
        self.assertEqual(self.f.erasure._journal(self.f.plan['id'])[1]['plan'],old)

    def test_real_f1_lost_commit_ack_is_read_only_reconciled_without_epoch_replay(self):
        from unittest.mock import patch
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore,CommitUnknown
        source=copy.deepcopy(self.f.protective_request['payload']['source']);source['epoch']=1
        request=self.f.authority.protective_request(self.f.token,self.f.f.work_id,source,self.f.f.scope)
        entry=self.f.authority.authorize_invalidation(self.f.token,request);commit=ToolLearningStore._commit
        def lost_ack(storage):
            operation=storage._ToolLearningStore__context[1];commit(storage)
            if operation=='apply_invalidation':raise RuntimeError('synthetic lost F1 commit acknowledgement')
        with patch.object(ToolLearningStore,'_commit',lost_ack):
            with self.assertRaises(CommitUnknown):self.f.authority.apply_protective(entry,request)
        count=len(self.s.rows('tl_barrier'));result=self.f.authority.reconcile_protective_commit(self.f.token,request['command_id'])
        self.assertEqual(result['source_epoch'],2);self.assertFalse(result['reexecuted']);self.assertFalse(result['restore_exclusion_complete']);self.assertFalse(result['unknown_consumption_released'])
        self.assertEqual(len(self.s.rows('tl_barrier')),count)
        with self.assertRaises(Forbidden):self.f.exclusions.restore_constraints(self.f.entry,self.s.instance_id)

    def test_forged_token_and_same_key_changed_caps_refused(self):
        from digital_life.domain.contracts import utc
        deadline=utc(50)
        with self.assertRaises(Forbidden):self.service.authorize('Bearer wrong',self.f.plan['id'],self.f.caps,deadline,'continuation')
        self.service.authorize(self.f.token,self.f.plan['id'],self.f.caps,deadline,'continuation')
        changed=copy.deepcopy(self.f.caps);changed['scan']-=1
        with self.assertRaises(Conflict):self.service.authorize(self.f.token,self.f.plan['id'],changed,deadline,'continuation')


class ActualCoordinatorRecoveryTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_runtime import StrictLearningFlowTests
        self.f=StrictLearningFlowTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.r=self.f.r
    def test_actual_candidate_review_resumes_original_work_and_accepts_next_round(self):
        from digital_life.application.learning.runtime import ControllerReviewAuthor
        from digital_life.application.learning.eligibility import ref,slot
        from digital_life.domain import tool_learning_contract as c
        from digital_life.domain.contracts import utc
        work,proposal=self.f.observe();self.r.decide(proposal['id']);row=self.s.row('tl_work',work['id'])
        self.assertEqual(row['state'],'waiting');old_id=row['id'];old_account=row['budget_account_id'];old_deadline=row['deadline']
        product=self.s.read_artifact(proposal['payload_artifact_id']);content=self.s.rows('tl_content')[0];revision=self.s.row('tl_content_revision',content['head_revision_id']);policy=self.s.rows('policy_epochs')[0]['policy_version_id']
        review={'contract':'TL-CONTROLLER-CONTENT-REVIEW-1','proposal':ref(self.s,proposal['id']),'proposal_digest':c.fingerprint(product),'review_round':1,'expected':copy.deepcopy(product['body']['target']['expected']),'native_expected':slot({'object':ref(self.s,content['id']),'revision':revision['revision_no'],'epoch':0}),'actual_scope':copy.deepcopy(product['body']['claims'][0]['scope']),'policy':ref(self.s,policy),'atomic_group':slot(),'verdict':'accept','expires_at':utc(120)}
        condition=ControllerReviewAuthor(self.s).author('Bearer synthetic-isolated-controller-token',review)['review']
        self.r.resume_work(work['id'],[condition]);current=self.s.row('tl_work',work['id'])
        self.assertEqual((current['id'],current['budget_account_id'],current['deadline']),(old_id,old_account,old_deadline));self.assertEqual(current['review_round'],1)
        result=self.r.decide(proposal['id'],condition);self.assertEqual(self.s.row('tl_decision',result['result_refs'][0]['id'])['operation'],'accept')
        self.assertEqual(len(self.s.rows('tl_work')),1);self.assertEqual(len(self.s.rows('tl_product')),4)
    def test_actual_missing_condition_owner_does_not_increment_round(self):
        work,proposal=self.f.observe();self.r.decide(proposal['id'])
        with self.assertRaises(Forbidden):self.r.resume_work(work['id'],[])
        self.assertEqual(self.s.row('tl_work',work['id'])['review_round'],0)


class CurrentImageRestoreTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_propagation import ControllerMaintenanceIntegrationTests
        self.f=ControllerMaintenanceIntegrationTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.f.authorized();self.s=self.f.s
        from pathlib import Path
        import tempfile,sqlite3,shutil
        from digital_life.domain.contracts import dumps,sha
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.backup=self.root/'registered-synthetic-image';self.backup.mkdir()
        out=sqlite3.connect(str(self.backup/'runtime.sqlite'));self.s.db.backup(out);out.close()
        (self.backup/'blobs').mkdir();files={'runtime.sqlite':sha((self.backup/'runtime.sqlite').read_bytes())}
        for row in self.s.rows('artifacts'):
            source=self.s.root/'blobs'/row['storage_ref'];shutil.copyfile(source,self.backup/'blobs'/row['storage_ref']);files['blobs/'+row['storage_ref']]=row['hash']
        (self.backup/'manifest.json').write_text(dumps({'instance_id':self.s.instance_id,'files':files}))
        self.permit('locked-candidate')
    def permit(self,name):
        from digital_life.domain.contracts import utc,identifier
        from digital_life.application.learning.recovery import ContinuedErasure
        self.f.authority.configure_restore_candidate(self.f.token,self.backup,self.root/name)
        grant=ContinuedErasure(self.f.erasure).authorize(self.f.token,self.f.plan['id'],self.f.caps,utc(50),identifier())
        self.f.entry=grant['entries']['M12']
    def test_current_history_and_erased_material_preserved_in_locked_candidate(self):
        from digital_life.application.memory.data_management import restore_current_bundle
        from digital_life.infrastructure.persistence.sqlite_store import Store
        self.f.erasure.run(self.f.entry,self.f.plan['id'])
        before=[dict(x) for x in self.s.db.execute('SELECT * FROM tl_barrier ORDER BY id')]
        target=self.root/'locked-candidate';result=restore_current_bundle(self.s,self.backup,target,authority=self.f.authority,entry=self.f.entry,bearer=self.f.token,exclusions=self.f.exclusions,limits=self.f.caps)
        self.assertFalse(result['wake_authorized']);self.assertFalse(result['historical_database_used'])
        self.assertTrue((target/'WAKE_DISABLED').exists());self.assertTrue((target/'RESTORE_RECONCILIATION_REQUIRED').exists())
        candidate=Store(target)
        try:
            self.assertEqual(before,[dict(x) for x in candidate.db.execute('SELECT * FROM tl_barrier ORDER BY id')])
            self.assertEqual(candidate.read_artifact(self.f.signal['artifact_id']),{'contract':'TL-ERASED-MATERIAL-1','plan_id':self.f.plan['id']})
            with self.assertRaises(Forbidden):candidate.assert_execution_allowed()
        finally:candidate.close()
    def test_legacy_restore_of_tl_image_without_current_owner_is_blocked(self):
        from digital_life.application.memory.data_management import restore_bundle
        with self.assertRaises(Forbidden):restore_bundle(self.backup,self.root/'unqualified')
        self.assertFalse((self.root/'unqualified').exists())
    def test_pending_current_f1_never_uses_older_exclusion_head(self):
        from digital_life.application.memory.data_management import restore_current_bundle
        self.permit('blocked')
        # A second legitimate source change has not yet reached its external
        # head. The previous completed exclusion index cannot cover it.
        self.f.erasure.run(self.f.entry,self.f.plan['id'])
        source=copy.deepcopy(self.f.protective_request['payload']['source']);source['epoch']=1
        pending=self.f.authority.protective_request(self.f.token,self.f.f.work_id,source,self.f.f.scope,kind='unavailable')
        entry=self.f.authority.authorize_invalidation(self.f.token,pending)
        self.f.authority.apply_protective(entry,pending)
        with self.assertRaises(Forbidden):restore_current_bundle(self.s,self.backup,self.root/'blocked',authority=self.f.authority,entry=self.f.entry,bearer=self.f.token,exclusions=self.f.exclusions,limits=self.f.caps)
        self.assertFalse((self.root/'blocked').exists())


    def test_backup_blob_directory_symlink_is_rejected_with_failed_settlement(self):
        from digital_life.application.memory.data_management import restore_current_bundle
        import shutil
        self.permit('symlink-candidate')
        from digital_life.domain.contracts import sha,dumps
        # Select the explicitly created, unused synthetic inventory body, not
        # an unordered artifact that might be the live authentication config.
        row=self.s.db.execute('SELECT * FROM artifacts WHERE instance_id=? AND hash=?',(self.s.instance_id,sha(dumps({'inventory':7})))).fetchone()
        self.assertIsNotNone(row);self.assertNotEqual(row['id'],self.f.signal['artifact_id'])
        self.assertFalse(self.s.db.execute('SELECT 1 FROM configuration_versions WHERE instance_id=? AND artifact_ref=?',(self.s.instance_id,row['id'])).fetchone())
        (self.s.root/'blobs'/row['storage_ref']).unlink()
        original=self.root/'outside-backup-blobs';(self.backup/'blobs').rename(original);(self.backup/'blobs').symlink_to(original,target_is_directory=True)
        with self.assertRaises(Forbidden):restore_current_bundle(self.s,self.backup,self.root/'symlink-candidate',authority=self.f.authority,entry=self.f.entry,bearer=self.f.token,exclusions=self.f.exclusions,limits=self.f.caps)
        settled=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='tl.recovery.restore.settlement'").fetchone()
        self.assertIsNotNone(settled);self.assertEqual(self.s.read_artifact(settled[0])['outcome'],'failed')
        self.assertTrue((self.root/'symlink-candidate'/'WAKE_DISABLED').exists())
    def test_manifest_failure_after_real_grant_has_failed_consumption_fact(self):
        from digital_life.application.memory.data_management import restore_current_bundle
        self.permit('bad-manifest')
        (self.backup/'manifest.json').write_text('{}')
        with self.assertRaises(Conflict):restore_current_bundle(self.s,self.backup,self.root/'bad-manifest',authority=self.f.authority,entry=self.f.entry,bearer=self.f.token,exclusions=self.f.exclusions,limits=self.f.caps)
        settled=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='tl.recovery.restore.settlement'").fetchone()
        result=self.s.read_artifact(settled[0]);self.assertEqual(result['outcome'],'failed');self.assertGreater(result['usage']['bytes'],0)


    def test_only_single_source_maintenance_policy_cannot_authorize_whole_restore(self):
        from tests.test_tool_learning_propagation import ControllerMaintenanceIntegrationTests
        from digital_life.application.memory.data_management import restore_current_bundle
        other=ControllerMaintenanceIntegrationTests();other.setUp();self.addCleanup(other.doCleanups);other.authorized()
        with self.assertRaisesRegex(Forbidden,'whole-instance locked restore policy'):
            restore_current_bundle(other.s,self.backup,self.root/'not-opted-in',authority=other.authority,entry=other.entry,bearer=other.token,exclusions=other.exclusions,limits=other.caps)
        self.assertFalse((self.root/'not-opted-in').exists())
    def test_current_full_restore_policy_does_not_cover_another_target(self):
        from digital_life.application.memory.data_management import restore_current_bundle
        with self.assertRaisesRegex(Forbidden,'policy/path scope'):
            restore_current_bundle(self.s,self.backup,self.root/'wrong-target',authority=self.f.authority,entry=self.f.entry,bearer=self.f.token,exclusions=self.f.exclusions,limits=self.f.caps)
        self.assertFalse((self.root/'wrong-target').exists())
    def test_full_restore_policy_cannot_override_private_original_source_acl(self):
        from digital_life.application.memory.data_management import restore_current_bundle
        from digital_life.domain.contracts import utc
        memory=self.s.rows('memory_items')[0]
        private=self.s.insert('policy_versions',version=999,mode='authorization',scope={'memory_readers':[self.s.config()['self_actor']]},effective_at=utc(),authority=self.s.config()['controller'])
        self.s.db.execute('UPDATE memory_items SET access_policy_ref=? WHERE id=?',(private,memory['id']))
        with self.assertRaises(Forbidden):restore_current_bundle(self.s,self.backup,self.root/'locked-candidate',authority=self.f.authority,entry=self.f.entry,bearer=self.f.token,exclusions=self.f.exclusions,limits=self.f.caps)
        self.assertFalse((self.root/'locked-candidate').exists())


class ActualCrashClassificationTests(ActualCoordinatorRecoveryTests):
    def stop_actual_process(self):
        self.f.f.control.finish_run(self.f.f.f.identity);self.f.f.control.stop('synthetic crash-recovery')
    def test_real_c1_commit_ack_unknown_reconciles_original_handoff_without_replay(self):
        from unittest.mock import patch
        from digital_life.infrastructure.persistence.tool_learning_store import CommitUnknown
        from digital_life.application.learning.recovery import reconcile_stopped_work
        work,proposal=self.f.observe();review=self.f.review(proposal);commit=self.r.acceptance.storage._commit
        def lost_ack():commit();raise RuntimeError('synthetic lost C1 commit acknowledgement')
        with patch.object(self.r.acceptance.storage,'_commit',side_effect=lost_ack):
            with self.assertRaises(CommitUnknown):self.r.decide(proposal['id'],review)
        self.assertEqual(len(self.s.rows('tl_decision')),1);self.assertEqual(len(self.s.rows('tl_handoff')),1)
        self.stop_actual_process();result=reconcile_stopped_work(self.s,'Bearer synthetic-isolated-controller-token')
        row=self.s.row('tl_work',work['id']);self.assertEqual((row['state'],row['phase']),('blocked','represent'));self.assertFalse(result['automatic_replay'])
        self.assertEqual(len(self.s.rows('tl_decision')),1)
    def test_actual_c1_recovery_restarts_only_original_representation_stage(self):
        from digital_life.application.learning.recovery import reconcile_stopped_work
        from digital_life.application.learning.runtime_learning import StrictLearningCoordinator
        from digital_life.application.learning.engine import StrictEngine
        from digital_life.application.learning.eligibility import ref
        work,proposal=self.f.observe();review=self.f.review(proposal);self.r.decide(proposal['id'],review)
        self.stop_actual_process();reconcile_stopped_work(self.s,'Bearer synthetic-isolated-controller-token')
        handoff=self.s.rows('tl_handoff')[0];control=self.f.f.control
        deployment=control.db.execute('SELECT deployment_id FROM process_runs WHERE id=?',(self.f.f.f.identity.process_id,)).fetchone()[0]
        control.resume('synthetic original-work continuation');identity=control.begin_run(deployment);self.addCleanup(control.finish_run,identity)
        coordinator=StrictLearningCoordinator(StrictEngine(self.s,identity,self.f.k.provider),self.f.provider)
        coordinator.resume_work(work['id'],[ref(self.s,handoff['id'])]);coordinator.publish(handoff['id'])
        self.assertEqual(self.s.row('tl_work',work['id'])['state'],'completed');self.assertEqual(len(self.s.rows('tl_product')),4);self.assertEqual(len(self.s.rows('tl_decision')),1)

    def test_expired_original_lease_gets_new_generation_and_late_publish_is_denied(self):
        from unittest.mock import patch
        from digital_life.application.learning.recovery import reconcile_stopped_work
        from digital_life.application.learning.runtime_learning import StrictLearningCoordinator
        from digital_life.application.learning.engine import StrictEngine
        from digital_life.application.learning.eligibility import ref,slot
        from digital_life.domain.contracts import utc,identifier
        work,proposal=self.f.observe();review=self.f.review(proposal);self.r.decide(proposal['id'],review);handoff=self.s.rows('tl_handoff')[0]
        fixed={};build=self.r.representation.build
        def crash_after_build(entry,request,claim):
            fixed.update(request=copy.deepcopy(request),claim=copy.deepcopy(claim),representation=build(entry,request,claim))
            raise RuntimeError('synthetic crash after real build before C2')
        with patch.object(self.r.representation,'build',side_effect=crash_after_build):
            with self.assertRaisesRegex(RuntimeError,'real build'):self.r.publish(handoff['id'])
        self.assertEqual(self.s.row('tl_handoff',handoff['id'])['lease_generation'],1)
        self.stop_actual_process();reconcile_stopped_work(self.s,'Bearer synthetic-isolated-controller-token')
        control=self.f.f.control;deployment=control.db.execute('SELECT deployment_id FROM process_runs WHERE id=?',(self.f.f.f.identity.process_id,)).fetchone()[0]
        control.resume('synthetic original lease recovery');identity=control.begin_run(deployment);self.addCleanup(control.finish_run,identity)
        coordinator=StrictLearningCoordinator(StrictEngine(self.s,identity,self.f.k.provider),self.f.provider)
        with self.assertRaises(Forbidden):coordinator.resume_work(work['id'],[ref(self.s,handoff['id'])])
        later=utc(31);coordinator.recovery.clock=lambda:later;coordinator.representation.clock=lambda:later
        coordinator.resume_work(work['id'],[ref(self.s,handoff['id'])])
        entry,principal=coordinator.o.entry('M04','represent',self.s.config()['controller']);original=self.s.row('tl_work',work['id'])
        payload={'handoff':ref(self.s,handoff['id']),'worker':principal['actor'],'lease_generation':1,'representation':fixed['representation']}
        request=coordinator._envelope(entry,original['learning_activity_id'],payload,work['id'],coordinator.budget.check_work(work['id'])['budget']);request['expected']=fixed['claim']['current']
        with self.assertRaises(Conflict):
            with coordinator.read_stage(entry,request):coordinator.representation.publish(entry,request)
        coordinator.publish(handoff['id'])
        self.assertEqual(self.s.row('tl_handoff',handoff['id'])['lease_generation'],2);self.assertEqual(self.s.row('tl_work',work['id'])['state'],'completed')

    def test_committed_observation_stage_resumes_without_reproducing_or_model_retry(self):
        from unittest.mock import patch
        from digital_life.application.learning.recovery import reconcile_stopped_work
        from digital_life.application.learning.runtime_learning import StrictLearningCoordinator
        from digital_life.application.learning.engine import StrictEngine
        from digital_life.application.learning.eligibility import ref
        signal=self.s.row('activities',self.f.activity)['trigger_event_id'];work=self.r.admit(self.f.activity,signal,{'kind':'json_pointer','pointer':'/text'})
        with patch.object(self.r.observation,'_publish',side_effect=RuntimeError('synthetic crash before product publication')):
            with self.assertRaisesRegex(RuntimeError,'before product'):self.r.assess(work['id'])
        self.assertEqual(len(self.s.rows('tl_product')),0);stage=self.s.db.execute("SELECT id FROM runtime_events WHERE source='tl.observation.material' AND source_event_id=?",(work['id'],)).fetchone()[0]
        self.stop_actual_process();reconcile_stopped_work(self.s,'Bearer synthetic-isolated-controller-token');control=self.f.f.control
        deployment=control.db.execute('SELECT deployment_id FROM process_runs WHERE id=?',(self.f.f.f.identity.process_id,)).fetchone()[0]
        control.resume('synthetic durable material continuation');identity=control.begin_run(deployment);self.addCleanup(control.finish_run,identity)
        coordinator=StrictLearningCoordinator(StrictEngine(self.s,identity,self.f.k.provider),self.f.provider)
        coordinator.resume_work(work['id'],[ref(self.s,stage)])
        with patch.object(coordinator.observation,'_produce',side_effect=AssertionError('must reuse actual durable material')):coordinator.assess(work['id'])
        self.assertEqual(len(self.s.rows('tl_product')),4);self.assertEqual(self.s.row('tl_work',work['id'])['state'],'awaiting_decision')

    def test_cli_missing_token_rejects_tl_recovery_in_synthetic_directory(self):
        import subprocess,sys
        from pathlib import Path
        work,proposal=self.f.observe();self.stop_actual_process();self.s.root.joinpath('controller.token').unlink()
        command=[sys.executable,'-m','digital_life','--data',str(self.s.root),'reconcile']
        result=subprocess.run(command,cwd=str(Path(__file__).resolve().parents[1]),capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0);self.assertIn('authenticated controller',result.stdout+result.stderr)
        self.assertEqual(self.s.row('tl_work',work['id'])['review_round'],0)
    def test_control_scope_policy_scan_bound_rolls_back_classification(self):
        from digital_life.application.learning.recovery import reconcile_stopped_work
        from digital_life.domain import tool_learning_contract as c
        from digital_life.domain.contracts import utc
        work,proposal=self.f.observe();self.stop_actual_process();before=self.s.row('tl_work',work['id'])
        active=self.s.rows('policy_epochs')[0];old=self.s.row('policy_versions',active['policy_version_id']);profile=c.loads(old['scope']);profile['recovery_control_limits']={'scan':1,'items':1,'bytes':1048576,'elapsed_ms':1000}
        policy=self.s.insert('policy_versions',version=103,mode='authorization',scope=profile,effective_at=utc(),authority=self.s.config()['controller'])
        self.s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE id=?',(policy,active['id']))
        with self.assertRaises(Forbidden):reconcile_stopped_work(self.s,'Bearer synthetic-isolated-controller-token')
        self.assertEqual(self.s.row('tl_work',work['id']),before)
        event=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='tl.recovery.control' ORDER BY rowid DESC LIMIT 1").fetchone()
        value=self.s.read_artifact(event[0]);self.assertFalse(value['full_coverage']);self.assertFalse(value['business_resume']);self.assertEqual(value['outcome'],'failed')

    def test_real_c2_commit_ack_unknown_projects_complete_without_republish(self):
        from unittest.mock import patch
        from digital_life.infrastructure.persistence.tool_learning_store import CommitUnknown
        from digital_life.application.learning.recovery import reconcile_stopped_work
        work,proposal=self.f.observe();review=self.f.review(proposal);self.r.decide(proposal['id'],review);handoff=self.s.rows('tl_handoff')[0]
        commit=self.r.representation.storage._commit
        def lost_ack():commit();raise RuntimeError('synthetic lost C2 acknowledgement')
        # Claim commits through the same store. Inject only publication.
        def selective():
            operation=self.r.representation.storage._ToolLearningStore__context[1]
            commit()
            if operation=='publish_representation':raise RuntimeError('synthetic lost C2 publication acknowledgement')
        with patch.object(self.r.representation.storage,'_commit',side_effect=selective):
            with self.assertRaises(CommitUnknown):self.r.publish(handoff['id'])
        self.stop_actual_process();reconcile_stopped_work(self.s,'Bearer synthetic-isolated-controller-token')
        self.assertEqual(self.s.row('tl_work',work['id'])['state'],'completed');self.assertEqual(len(self.s.rows('tl_representation')),1)

# The two base-case tests already run in their own class.
ActualCrashClassificationTests.test_actual_candidate_review_resumes_original_work_and_accepts_next_round=None
ActualCrashClassificationTests.test_actual_missing_condition_owner_does_not_increment_round=None


class OriginalAccountRecoveryReadTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_budget import ToolLearningBudgetTests,MechanicalBudgetAuthority
        from digital_life.application.learning.budget import ToolLearningBudget
        self.f=ToolLearningBudgetTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
        self.s.db.execute("UPDATE tl_work SET state='waiting',phase='assess',row_revision=row_revision+1 WHERE id=?",(self.f.work,))
        self.operation=self.f.operation('retrieval');self.binding={'operation':self.operation,'work_id':self.f.work,'account_id':self.f.account}
        outer=self
        class Owner(MechanicalBudgetAuthority):
            def verify_recovery_read(self,entry,work,operation,binding,stage):
                if entry!='synthetic-im05' or work['id']!=outer.f.work or operation!=outer.operation or binding!=outer.binding:raise Forbidden('wrong synthetic recovery binding')
        self.authority=Owner();self.budget=ToolLearningBudget(self.s,self.authority,clock=lambda:self.f.now)
    def scope(self,binding=None):return self.budget.recovery_read_context('synthetic-im05',self.f.work,self.operation,self.binding if binding is None else binding)
    def test_only_owner_bound_retrieval_can_spend_existing_original_account(self):
        with self.assertRaises(Forbidden):self.budget.reserve('synthetic-im05',self.f.work,self.operation,'retrieval',{'scan':1})
        with self.scope():
            reserved=self.budget.reserve('synthetic-im05',self.f.work,self.operation,'retrieval',{'scan':1,'bytes':1})
            self.budget.record_entry('synthetic-im05',self.f.work,reserved['id'],{'synthetic_witness':self.operation['id']})
            with self.assertRaises(Forbidden):self.budget.reserve('synthetic-im05',self.f.work,self.operation,'thought_attempt',{'attempts':1})
        self.assertIn('work_waiting',self.budget.check_work(self.f.work)['block_reasons'])
    def test_wrong_binding_and_stopped_control_remain_denied(self):
        with self.assertRaises(Forbidden):
            with self.scope({'caller_bool':True}):pass
        self.f.f.control.stop('synthetic stop')
        with self.assertRaises(Forbidden):
            with self.scope():pass
    def test_unknown_consumption_is_not_reset_by_recovery_scope(self):
        with self.scope():
            row=self.budget.reserve('synthetic-im05',self.f.work,self.operation,'retrieval',{'scan':1})
            self.budget.record_entry('synthetic-im05',self.f.work,row['id'],{'synthetic_witness':self.operation['id']})
            self.budget.settle('synthetic-im05',self.f.work,row['id'],None)
        with self.assertRaises(Forbidden):
            with self.scope():pass
        self.assertEqual(self.budget.check_work(self.f.work)['charged_or_reserved']['scan'],1)

    
