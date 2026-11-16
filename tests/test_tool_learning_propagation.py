"""New synthetic fixture only; mechanical authority is not production permission."""
import copy
import json
import tempfile
from pathlib import Path
import unittest
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,identifier,utc
from digital_life.application.learning.propagation import ToolLearningPropagation,PropagationAuthority,ManagedErasure,RestoreExclusions,MaintenanceReadAccounting
from digital_life.application.learning.eligibility import ref,slot
from digital_life.infrastructure.persistence.tool_learning_store import StorageGrant
from tests import test_tool_learning_invalidation as f1_fixture


class MechanicalPropagation(PropagationAuthority):
    def __init__(self):self.deny=False;self.actions=[];self.hook=None
    def verify(self,entry,operation,request,instance_id,stage):
        if entry!='synthetic-im12' or self.deny:raise Forbidden('synthetic owner denied')
        return StorageGrant(request['principal']['module'],frozenset(('tl_propagation',)))
    def project_response(self,entry,operation,request,response,instance_id,stage):return response
    def verify_propagation(self,entry,request,row,barrier,stage):
        if self.deny:raise Forbidden('synthetic denied')
        if self.hook:self.hook(stage)
    def apply_actions(self,transaction,entry,request,row,minimum,verification):return None
    def verify_actions(self,entry,request,row,minimum,verification,stage):
        if not verification['per_target'] and request['payload']['targets']:raise Forbidden('actual target verification missing')
        for item in verification['per_target']:
            fact=self.store.read_artifact(item['verification']['id'])
            actual=self.store.row('tl_barrier',row['barrier_id'])
            if fact!={'contract':'SYNTHETIC-M12-ACTUAL-BARRIER-FACT-1','barrier_id':row['barrier_id'],'domain':row['domain'],'source_epoch':actual['source_epoch'],'state':actual['state'],'target':item['target']}:raise Forbidden('actual mechanical barrier fact differs')
        self.actions.append(stage)
    def verify_maintenance(self,entry,plan,stage):
        if entry!='synthetic-im12' or self.deny:raise Forbidden('synthetic maintenance denied')
    def initial_usage(self,entry,plan):
        from digital_life.domain.tool_learning_resources import DIMENSIONS
        return {key:0 for key in DIMENSIONS}
    def verify_exclusion_index(self,entry,plan,directory,index,stage):return None
    def record_exclusion_index(self,entry,plan,directory,index):return None
    def current_restore_exclusions(self,entry,instance_id,max_records,max_bytes):return []
    def verify_restore(self,entry,instance_id,stage):
        if self.deny or entry!='synthetic-im12':raise Forbidden('synthetic current restore owner denied')
    def verify_inventory(self,entry,plan,stage):
        if self.deny:raise Forbidden('synthetic inventory denied')
    def verify_target(self,entry,plan,target,stage):
        if self.deny:raise Forbidden('synthetic target denied')


class PropagationTests(unittest.TestCase):
    def setUp(self):
        self.f=f1_fixture.F1Tests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
        self.authority=MechanicalPropagation();self.authority.store=self.s;self.service=ToolLearningPropagation(self.s,self.authority)
        result=self.f.apply(self.f.request('erase'));self.barrier=result['result_refs'][0]
        self.s.root.joinpath('WAKE_DISABLED').write_text('synthetic lock')
        self.f.f.control.stop('synthetic-im12')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.exclusions=RestoreExclusions(Path(self.tmp.name)/'trusted',self.s.root,self.authority)
        self.erasure=ManagedErasure(self.s,self.authority,self.exclusions)
    def coverage(self):return {'state':'complete','domain':slot('explicit synthetic managed inventory'),'scanned':1,'limit':4096,'truncated':False,'missing':[]}
    def request(self,domain='M12'):
        old=dict(self.s.db.execute('SELECT * FROM tl_propagation WHERE barrier_id=? AND domain=? ORDER BY generation DESC LIMIT 1',(self.barrier['id'],domain)).fetchone())
        if old['generation']==0:
            maintenance=self.plan();self.erasure.prepare('synthetic-im12',maintenance)
            key=self.erasure.renew_generation('synthetic-im12',maintenance['id'],old['id'],self.f.work_id)
            self.service.accounting=MaintenanceReadAccounting(self.erasure,maintenance['id'])
            row=self.s.row('tl_propagation',key)
        else:row=old
        minimum=self.s.read_artifact(row['targets_artifact_id']);targets=minimum['targets']
        facts=[]
        for target in targets:
            with self.s.tx():fact=self.s.artifact({'contract':'SYNTHETIC-M12-ACTUAL-BARRIER-FACT-1','barrier_id':self.barrier['id'],'domain':domain,'source_epoch':1,'state':'active','target':target})
            facts.append({'target':target,'action':ref(self.s,fact,'artifacts'),'verification':ref(self.s,fact,'artifacts')})
        actions=[x['action'] for x in facts]
        v={'contract':'TL-PROPAGATION-VERIFICATION-1','barrier':self.barrier,'generation':row['generation'],'domain':domain,'source_epoch':1,
           'minimum_plan':ref(self.s,row['targets_artifact_id'],'artifacts'),'targets':targets,'actions':actions,'coverage':self.coverage(),'boundary':{'synthetic':True},'watermark':{'source_epoch':1},'unresolved':[],
           'per_target':facts}
        with self.s.tx():artifact=self.s.artifact(v)
        request=self.f.request();request['principal']['module']=domain
        request['payload']={'barrier':self.barrier,'generation':row['generation'],'domain':domain,'targets':targets,'actions':actions,'coverage':self.coverage(),'verification':ref(self.s,artifact,'artifacts')}
        account=self.s.row('activity_budget_accounts',row['budget_account_id'])
        request['budget']['account_ref']=ref(self.s,account['id'],'activity_budget_accounts')
        request['budget']['max_input_tokens']=0;request['budget']['max_output_tokens']=0;request['budget']['max_tool_calls']=0;request['budget']['max_attempts']=1
        request['budget'].update(max_scan=10000,max_items=10000,max_bytes=10000000)
        request['expected']=slot({'object':ref(self.s,row['id'],'tl_propagation'),'revision':row['row_revision'],'epoch':row['generation']})
        return request,row
    def plan(self,targets=None):
        request=self.f.request();barrier=self.s.row('tl_barrier',self.barrier['id'])
        return {'contract':'TL-MANAGED-ERASURE-1','id':identifier(),'instance_id':self.s.instance_id,'barrier_id':self.barrier['id'],'source_epoch':1,
            'scope_id':self.f.f.expected['policy_id'],'created_at':utc(),'deadline':request['budget']['deadline'],'authority_ref':self.f.principal['actor']['id'],
            'source_activity':self.f.work['learning_activity_id'],'caps':{'scan':10000,'items':10000,'bytes':10000000,'elapsed_ms':10000,'attempts':1},'targets':targets or [],'allow_control_metadata':True,'retained_metadata':['opaque_ids','control_scope','source_fingerprints','plan_expected_hashes','resource_facts','action_facts'],'coverage':self.coverage()}
    def test_default_authority_rejects(self):
        req,_=self.request()
        with self.assertRaises(Forbidden):ToolLearningPropagation(self.s).acknowledge('synthetic-im12',req)
        with self.assertRaises(Forbidden):ManagedErasure(self.s).prepare('synthetic-im12',self.plan())
    def test_f2_own_domain_verified_barrier_stays_other_domains_pending(self):
        req,row=self.request();self.service.acknowledge('synthetic-im12',req)
        self.assertEqual(self.s.row('tl_propagation',row['id'])['state'],'verified')
        self.assertEqual(self.s.row('tl_barrier',self.barrier['id'])['state'],'active')
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM tl_propagation WHERE state='pending'").fetchone()[0],9)
        self.assertTrue((self.s.root/'WAKE_DISABLED').exists());self.assertEqual(self.f.f.control.state()['user_stopped'],1)
    def test_f2_wrong_owner_and_old_cas(self):
        req,row=self.request();req['principal']['module']='M03'
        with self.assertRaises(Forbidden):self.service.acknowledge('synthetic-im12',req)
        req['principal']['module']='M12';req['expected']['value']['revision']=1
        with self.assertRaises(Conflict):self.service.acknowledge('synthetic-im12',req)
    def test_same_command_replay_and_changed_payload_reject(self):
        req,_=self.request();first=self.service.acknowledge('synthetic-im12',req)
        self.assertEqual(first,self.service.acknowledge('synthetic-im12',req))
        req['payload']['coverage']['scanned']=2
        with self.assertRaises(Conflict):self.service.acknowledge('synthetic-im12',req)
    def test_external_exclusions_actual_persistent_and_tamper(self):
        plan=self.plan();self.exclusions.write('synthetic-im12',plan)
        self.assertEqual(self.exclusions.read('synthetic-im12',plan)['source_epoch'],1)
        path=self.exclusions.directory/(plan['id']+'.json');path.write_text('{}')
        with self.assertRaises(Conflict):self.exclusions.read('synthetic-im12',plan)
    def test_exclusion_in_runtime_or_symlink_rejected(self):
        with self.assertRaises(Forbidden):RestoreExclusions(self.s.root/'exclusions',self.s.root,self.authority)
        path=Path(self.tmp.name)/'link';path.symlink_to(self.s.root,target_is_directory=True)
        with self.assertRaises(Forbidden):RestoreExclusions(path,self.s.root,self.authority)
    def test_artifact_actual_tombstone_and_idempotent(self):
        with self.s.tx():key=self.s.artifact({'secret':'synthetic-private'})
        original=self.s.row('artifacts',key)
        target={'target':ref(self.s,key,'artifacts'),'location':'database','operation':'tombstone','expected':{'hash':original['hash'],'storage_ref':original['storage_ref']}}
        plan=self.plan([target]);self.erasure.prepare('synthetic-im12',plan);result=self.erasure.run('synthetic-im12',plan['id'])
        self.assertEqual(result['state'],'verified');self.assertEqual(self.s.read_artifact(key),{'contract':'TL-ERASED-MATERIAL-1','plan_id':plan['id']})
        self.assertEqual(self.erasure.run('synthetic-im12',plan['id'])['state'],'verified')
        self.assertTrue(self.exclusions.read('synthetic-im12',plan));self.assertEqual(self.s.row('tl_barrier',self.barrier['id'])['state'],'active')
    def test_forbidden_metadata_keeps_barrier_blocked(self):
        plan=self.plan();plan['allow_control_metadata']=False;self.erasure.prepare('synthetic-im12',plan)
        result=self.erasure.run('synthetic-im12',plan['id']);self.assertEqual(result['state'],'blocked');self.assertTrue(result['missing'])
    def test_maintenance_same_id_different_plan_reject(self):
        plan=self.plan();self.erasure.prepare('synthetic-im12',plan);plan['caps']['bytes']+=1
        with self.assertRaises(Conflict):self.erasure.prepare('synthetic-im12',plan)
    def test_remote_unknown_not_deleted(self):
        target={'target':self.f.source,'location':'remote','operation':'observe','expected':{}}
        plan=self.plan([target]);self.erasure.prepare('synthetic-im12',plan);result=self.erasure.run('synthetic-im12',plan['id'])
        self.assertEqual(result['state'],'blocked');self.assertEqual(next(iter(result['targets'].values()))['state'],'unknown')

    def blob_plan(self,shared=False):
        with self.s.tx():key=self.s.artifact({'secret':'synthetic physical bytes'})
        row=self.s.row('artifacts',key);path=self.s.root/'blobs'/row['storage_ref'];st=path.stat()
        targets=[{'target':ref(self.s,key,'artifacts'),'location':'database','operation':'tombstone','expected':{'hash':row['hash'],'storage_ref':row['storage_ref']}},
            {'target':ref(self.s,key,'artifacts'),'location':'blob','operation':'unlink','expected':{'storage_ref':row['storage_ref'],'device':st.st_dev,'inode':st.st_ino}}]
        if shared:
            original=self.s.instance_id;second=identifier()
            with self.s.tx():self.s.insert('identity_instances',id=second,instance_id=second,state='active',generation=0)
            self.s.instance_id=second
            try:
                with self.s.tx():self.s.artifact({'secret':'synthetic physical bytes'})
            finally:self.s.instance_id=original
        return self.plan(targets),path
    def test_blob_real_unlink_after_database_tombstone(self):
        plan,path=self.blob_plan();self.erasure.prepare('synthetic-im12',plan)
        result=self.erasure.run('synthetic-im12',plan['id']);self.assertEqual(result['state'],'verified');self.assertFalse(path.exists())
        self.assertGreater(result['usage']['bytes'],0);self.assertGreater(result['usage']['scan'],0)
    def test_blob_other_instance_reference_blocks_unlink(self):
        plan,path=self.blob_plan(shared=True);self.erasure.prepare('synthetic-im12',plan)
        result=self.erasure.run('synthetic-im12',plan['id']);self.assertEqual(result['state'],'blocked');self.assertTrue(path.exists())
    def test_blob_replaced_inode_and_symlink_fail_closed(self):
        for symlink in (False,True):
            plan,path=self.blob_plan();self.erasure.prepare('synthetic-im12',plan)
            saved=path.with_name('synthetic-saved');path.rename(saved)
            if symlink:path.symlink_to(saved)
            else:path.write_bytes(saved.read_bytes())
            with self.assertRaises(Forbidden):self.erasure.run('synthetic-im12',plan['id'])
            self.assertTrue(path.exists());path.unlink();saved.rename(path)
    def test_unknown_entered_maintenance_keeps_hold_no_retry(self):
        plan=self.plan();self.erasure.prepare('synthetic-im12',plan)
        row,journal=self.erasure._journal(plan['id']);journal['entered']=True
        with self.s.tx():self.erasure._save(plan['id'],journal)
        with self.assertRaises(Forbidden):self.erasure.run('synthetic-im12',plan['id'])
        self.assertTrue(self.erasure.status('synthetic-im12',plan['id'])['usage_unknown'])
    def test_small_budget_records_actual_consumption_and_does_not_reset(self):
        plan,path=self.blob_plan();plan['caps']['bytes']=1;self.erasure.prepare('synthetic-im12',plan)
        with self.assertRaises(Forbidden):self.erasure.run('synthetic-im12',plan['id'])
        before=self.erasure.status('synthetic-im12',plan['id'])['usage']['bytes'];self.assertGreater(before,0)
        with self.assertRaises(Forbidden):self.erasure.run('synthetic-im12',plan['id'])
        self.assertGreaterEqual(self.erasure.status('synthetic-im12',plan['id'])['usage']['bytes'],before);self.assertTrue(path.exists())
    def test_known_target_change_not_blindly_erased(self):
        plan,path=self.blob_plan();key=plan['targets'][0]['target']['id'];self.erasure.prepare('synthetic-im12',plan)
        with self.s.tx():
            replacement=self.s.artifact({'different':'synthetic source'});row=self.s.row('artifacts',replacement)
            self.s.db.execute('UPDATE artifacts SET hash=?,size=?,media_type=?,storage_ref=? WHERE id=?',(row['hash'],row['size'],row['media_type'],row['storage_ref'],key))
        with self.assertRaises(Conflict):self.erasure.run('synthetic-im12',plan['id'])
        self.assertEqual(self.s.read_artifact(key),{'different':'synthetic source'});self.assertTrue(path.exists())
    def test_actual_index_file_adapter_and_unknown_cache_not_run(self):
        from digital_life.domain.contracts import sha
        path=self.s.root/'memory-quality-index.sqlite';path.write_bytes(b'synthetic indexed secret');st=path.stat()
        target={'target':self.f.source,'location':'index','operation':'unlink','expected':{'name':path.name,'device':st.st_dev,'inode':st.st_ino,'hash':sha(path.read_bytes())}}
        plan=self.plan([target]);self.erasure.prepare('synthetic-im12',plan);self.assertEqual(self.erasure.run('synthetic-im12',plan['id'])['state'],'verified');self.assertFalse(path.exists())
        target['location']='cache';target['expected']['name']='arbitrary-cache'
        plan=self.plan([target]);self.erasure.prepare('synthetic-im12',plan);result=self.erasure.run('synthetic-im12',plan['id']);self.assertEqual(result['state'],'blocked')
    def test_maintenance_grant_denial_and_active_process_refuse(self):
        plan=self.plan();self.authority.deny=True
        with self.assertRaises(Forbidden):self.erasure.prepare('synthetic-im12',plan)
        self.authority.deny=False
        self.f.f.control.db.execute('UPDATE instance_control_state SET user_stopped=0 WHERE instance_ref=?',(self.s.instance_id,))
        with self.assertRaises(Forbidden):self.erasure.prepare('synthetic-im12',plan)

    def test_current_restore_ledger_not_old_image_plan_list(self):
        first=self.plan();self.erasure.prepare('synthetic-im12',first)
        second=self.plan([{'target':self.f.source,'location':'remote','operation':'observe','expected':{}}]);self.erasure.prepare('synthetic-im12',second)
        result=self.exclusions.restore_constraints('synthetic-im12',self.s.instance_id)
        self.assertEqual({x['plan_id'] for x in result['exclusions']},{first['id'],second['id']});self.assertFalse(result['restore_authorized'])
        with self.assertRaises(Forbidden):self.exclusions.restore_constraints('synthetic-im12',self.s.instance_id,max_records=1)
        missing=RestoreExclusions(Path(self.tmp.name)/'missing',self.s.root,self.authority)
        with self.assertRaises(Forbidden):missing.restore_constraints('synthetic-im12',self.s.instance_id)
    def test_maintenance_attempt_cap_real_but_no_model_or_tool_budget_contract(self):
        from digital_life.application.learning.activity_budget import ActivityResourceBudget
        plan=self.plan();self.erasure.prepare('synthetic-im12',plan);_,journal=self.erasure._journal(plan['id'])
        account=self.s.row('activity_budget_accounts',journal['account_id']);self.assertEqual((account['attempt_limit'],account['token_limit'],account['tool_call_limit']),(1,0,0))
        with self.assertRaises(Forbidden):ActivityResourceBudget(self.s).check_activity(journal['activity_id'])
        self.assertEqual(journal['used']['attempts'],0)
    def test_renewal_only_one_domain_and_actual_account_with_original_work(self):
        req,row=self.request('M12');_,journal=self.erasure._journal(self.service.accounting.plan_id)
        original=self.s.db.execute('SELECT * FROM tl_propagation WHERE barrier_id=? AND domain=? AND generation=0',(self.barrier['id'],'M12')).fetchone()
        self.assertNotEqual(original['budget_account_id'],row['budget_account_id']);self.assertEqual(row['budget_account_id'],journal['account_id'])
        self.assertEqual(self.erasure.renew_generation('synthetic-im12',self.service.accounting.plan_id,original['id'],self.f.work_id),row['id'])
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM tl_propagation WHERE generation>0 AND domain<>'M12'").fetchone()[0],0)
        self.service.acknowledge('synthetic-im12',req);_,after=self.erasure._journal(self.service.accounting.plan_id)
        self.assertGreater(after['used']['bytes'],0);self.assertEqual(after['used']['attempts'],0)
    def test_inventory_actual_registered_derivatives_bounded_and_metered(self):
        from digital_life.application.learning.propagation import ManagedInventory
        plan=self.plan();self.erasure.prepare('synthetic-im12',plan)
        inventory=ManagedInventory(self.erasure,max_rows=2).discover('synthetic-im12',plan['id'],self.f.token)
        self.assertIn(inventory['coverage']['state'],('partial','unknown'));self.assertNotEqual(inventory['coverage']['state'],'complete')
        self.assertIn(self.f.source['id'],{x['id'] for x in inventory['targets']})
        _,journal=self.erasure._journal(plan['id']);self.assertGreater(journal['used']['scan'],0)
    def test_complete_claim_without_actual_target_verification_rejects_atomically(self):
        req,row=self.request();artifact=req['payload']['verification']['id'];v=self.s.read_artifact(artifact);v['per_target']=[]
        with self.s.tx():req['payload']['verification']=ref(self.s,self.s.artifact(v),'artifacts')
        with self.assertRaises(Forbidden):self.service.acknowledge('synthetic-im12',req)
        self.assertEqual(self.s.row('tl_propagation',row['id'])['state'],'pending')
    def test_partial_coverage_commits_blocked_does_not_resolve_reason(self):
        req,row=self.request();v=self.s.read_artifact(req['payload']['verification']['id']);v['unresolved']=['missing domain adapter'];v['coverage']['state']='partial';req['payload']['coverage']=v['coverage']
        with self.s.tx():req['payload']['verification']=ref(self.s,self.s.artifact(v),'artifacts')
        self.service.acknowledge('synthetic-im12',req);self.assertEqual(self.s.row('tl_propagation',row['id'])['state'],'blocked')
        self.assertEqual(self.s.row('tl_barrier',self.barrier['id'])['state'],'active')

    def test_registered_single_file_backup_actual_removal_and_unregistered_not_run(self):
        from digital_life.domain.contracts import sha
        path=Path(self.tmp.name).resolve()/'registered.sqlite';path.write_bytes(b'synthetic backup sensitive bytes');st=path.stat();control=self.f.f.control
        with control.tx():
            deployment=control.insert('deployments',release='synthetic-only',build_hash='0'*64,schema_min=4,schema_max=4,state='retired')
            registered=control.insert('backup_manifests',deployment_id=deployment,snapshot_path=str(path),hash=sha(path.read_bytes()),scope={'instance_id':self.s.instance_id,'managed_root':str(path.parent)},completed_at=utc())
        target={'target':self.f.source,'location':'managed_backup','operation':'unlink','expected':{'registration_id':registered,'path':str(path),'managed_root':str(path.parent),'hash':sha(path.read_bytes()),'device':st.st_dev,'inode':st.st_ino}}
        plan=self.plan([target]);self.erasure.prepare('synthetic-im12',plan);result=self.erasure.run('synthetic-im12',plan['id']);self.assertEqual(result['state'],'verified');self.assertFalse(path.exists())
        target['expected']['registration_id']=identifier();target['target']=ref(self.s,self.f.f.expected['self_actor']);plan=self.plan([target]);self.erasure.prepare('synthetic-im12',plan);self.assertEqual(self.erasure.run('synthetic-im12',plan['id'])['state'],'blocked')
    def test_after_actual_unlink_failure_rechecks_absence_does_not_blindly_delete(self):
        from unittest.mock import patch
        plan,path=self.blob_plan();self.erasure.prepare('synthetic-im12',plan);original=self.erasure._target;once=[]
        def failure(entry,p,target):
            result=original(entry,p,target)
            if target['location']=='blob' and not once:once.append(True);raise OSError('synthetic failure after actual unlink before acknowledgement')
            return result
        with patch.object(self.erasure,'_target',failure):
            with self.assertRaises(OSError):self.erasure.run('synthetic-im12',plan['id'])
        self.assertFalse(path.exists());self.assertEqual(self.erasure.run('synthetic-im12',plan['id'])['state'],'verified')
    def test_physical_step_failure_does_not_undo_exclusion_or_other_reason(self):
        from unittest.mock import patch
        plan,path=self.blob_plan();self.erasure.prepare('synthetic-im12',plan)
        with patch.object(self.erasure,'_unlink_blob',side_effect=OSError('synthetic local file failure')):
            with self.assertRaises(OSError):self.erasure.run('synthetic-im12',plan['id'])
        self.assertTrue(path.exists());self.assertTrue(self.exclusions.read('synthetic-im12',plan));self.assertEqual(self.s.row('tl_barrier',self.barrier['id'])['state'],'active')
    def test_caps_tamper_rejected_by_actual_initial_grant_mapping(self):
        plan=self.plan();self.erasure.prepare('synthetic-im12',plan);_,journal=self.erasure._journal(plan['id']);journal['plan']['caps']['bytes']+=1
        with self.s.tx():self.erasure._save(plan['id'],journal)
        with self.assertRaises(Conflict):self.erasure.run('synthetic-im12',plan['id'])


    def test_restored_source_permission_does_not_revive_erased_material(self):
        plan,path=self.blob_plan();self.erasure.prepare('synthetic-im12',plan);self.erasure.run('synthetic-im12',plan['id'])
        self.f.elig_auth.deny=True
        self.f.elig_auth.deny=False
        # Remove only the synthetic stop/lock so the actual source barrier,
        # rather than the control lock, is what rejects the attempted reuse.
        self.f.f.control.db.execute('UPDATE instance_control_state SET user_stopped=0 WHERE instance_ref=?',(self.s.instance_id,));self.s.root.joinpath('WAKE_DISABLED').unlink()
        token=copy.deepcopy(self.f.token);token['epoch']=1
        with self.assertRaisesRegex(Forbidden,'active source qualification barrier'):self.f.check(token=token)
        self.assertFalse(path.exists());self.assertEqual(self.s.row('tl_barrier',self.barrier['id'])['state'],'active')
    def test_source_fingerprint_retention_must_be_explicit_not_generic_metadata_flag(self):
        plan=self.plan();plan['retained_metadata'].remove('source_fingerprints');self.erasure.prepare('synthetic-im12',plan)
        self.assertEqual(self.erasure.run('synthetic-im12',plan['id'])['state'],'blocked')
    def test_cross_plan_target_rebinding_is_explicit_conflict_not_sql_error(self):
        plan,path=self.blob_plan();self.erasure.prepare('synthetic-im12',plan)
        second=copy.deepcopy(plan);second['id']=identifier()
        with self.assertRaisesRegex(Conflict,'another immutable cleanup plan'):self.erasure.prepare('synthetic-im12',second)
        self.assertTrue(path.exists())
    def test_f2_ref_known_revision_not_fabricated_by_control_token(self):
        request,row=self.request();known=ref(self.s,row['id'],'tl_propagation');known['revision']=slot(0)
        with self.assertRaises(Conflict):self.service.storage.validate_ref(known)
        self.assertFalse(self.s.db.execute('SELECT 1 FROM object_revision_registry WHERE instance_id=? AND object_id=?',(self.s.instance_id,row['id'])).fetchone())


    def test_physical_plan_completion_is_not_nine_domain_f3_completion(self):
        plan,path=self.blob_plan();self.erasure.prepare('synthetic-im12',plan);self.erasure.run('synthetic-im12',plan['id'])
        result=self.erasure.completion('synthetic-im12',plan['id'])
        self.assertEqual(result['state'],'pending');self.assertEqual(len(result['missing_domains']),9);self.assertEqual(result['physical_plan_state'],'verified')
        request,_=self.request('M12');self.service.acknowledge('synthetic-im12',request)
        result=self.erasure.completion('synthetic-im12',plan['id']);self.assertEqual(len(result['missing_domains']),8);self.assertFalse(result['barrier_resolved'])
    def test_empty_target_plan_never_claims_erasure_complete(self):
        plan=self.plan();self.erasure.prepare('synthetic-im12',plan)
        self.assertEqual(self.erasure.run('synthetic-im12',plan['id'])['state'],'blocked')


    def test_database_purge_actual_row_absent_registry_opaque_identity_retained(self):
        from digital_life.domain import tool_learning_contract as contract
        with self.s.tx():event=self.s.event('synthetic.erasable',payload={'secret':'new synthetic event'},source='synthetic-im12')
        target={'target':ref(self.s,event,'runtime_events'),'location':'database','operation':'purge','expected':{'row_digest':contract.fingerprint(self.s.row('runtime_events',event))}}
        plan=self.plan([target]);self.erasure.prepare('synthetic-im12',plan);result=self.erasure.run('synthetic-im12',plan['id'])
        self.assertEqual(result['state'],'verified');self.assertFalse(result['f3_complete']);self.assertFalse(self.s.db.execute('SELECT 1 FROM runtime_events WHERE id=?',(event,)).fetchone())
        self.assertTrue(self.s.db.execute('SELECT 1 FROM object_registry WHERE id=?',(event,)).fetchone());self.assertFalse(self.s.integrity()['foreign_keys'])
    def test_control_barrier_is_not_purged_to_fake_full_erasure(self):
        target={'target':self.barrier,'location':'database','operation':'purge','expected':{}}
        plan=self.plan([target]);self.erasure.prepare('synthetic-im12',plan);result=self.erasure.run('synthetic-im12',plan['id'])
        self.assertEqual(result['state'],'blocked');self.assertEqual(self.s.row('tl_barrier',self.barrier['id'])['state'],'active')
    def test_late_current_target_permission_denial_never_records_verified(self):
        from unittest.mock import patch
        plan,path=self.blob_plan();self.erasure.prepare('synthetic-im12',plan);original=self.authority.verify_target
        def revoked(entry,p,target,stage):
            original(entry,p,target,stage)
            if target['location']=='blob' and stage=='verified':raise Forbidden('synthetic post-side-effect owner denial')
        with patch.object(self.authority,'verify_target',revoked):
            with self.assertRaisesRegex(Forbidden,'post-side-effect'):self.erasure.run('synthetic-im12',plan['id'])
        self.assertFalse(path.exists())
        row=self.s.db.execute("SELECT state FROM tl_erasure_target WHERE plan_ref_id=? AND location_kind='blob'",(plan['id'],)).fetchone();self.assertEqual(row['state'],'pending')
        self.assertTrue(self.exclusions.read('synthetic-im12',plan));self.assertEqual(self.erasure.run('synthetic-im12',plan['id'])['state'],'verified')


    def directory_backup_plan(self):
        from digital_life.domain.contracts import dumps,sha
        folder=Path(self.tmp.name).resolve()/('backup-'+identifier());(folder/'blobs').mkdir(parents=True)
        raw=b'synthetic backup blob';name=sha(raw);(folder/'blobs'/name).write_bytes(raw);(folder/'runtime.sqlite').write_bytes(b'synthetic backup database')
        manifest={'instance_id':self.s.instance_id,'files':{'runtime.sqlite':sha((folder/'runtime.sqlite').read_bytes()),'blobs/'+name:name},'created_at':utc(),'scope':'synthetic managed files'}
        (folder/'manifest.json').write_text(dumps(manifest));manifest_hash=sha((folder/'manifest.json').read_bytes())
        with self.s.tx():event=self.s.event('backup.created',payload={'path':str(folder),'manifest_sha256':manifest_hash},lane='control')
        files={}
        for relative in list(manifest['files'])+['manifest.json']:
            path=folder/relative;st=path.stat();files[relative]={'hash':sha(path.read_bytes()),'device':st.st_dev,'inode':st.st_ino}
        target={'target':ref(self.s,event,'runtime_events'),'location':'managed_backup','operation':'unlink','expected':{'registration_event_id':event,'managed_root':str(folder.parent),'path':str(folder),'manifest_hash':manifest_hash,'files':files}}
        return self.plan([target]),folder
    def test_actual_registered_directory_backup_complete_manifest_removed(self):
        plan,folder=self.directory_backup_plan();self.erasure.prepare('synthetic-im12',plan)
        result=self.erasure.run('synthetic-im12',plan['id']);self.assertEqual(result['state'],'verified');self.assertFalse(folder.exists())
        self.assertTrue(self.exclusions.read('synthetic-im12',plan));self.assertFalse(result['f3_complete'])
    def test_backup_unknown_file_or_manifest_tamper_not_blindly_removed(self):
        plan,folder=self.directory_backup_plan();self.erasure.prepare('synthetic-im12',plan);(folder/'unregistered-private').write_text('synthetic')
        with self.assertRaisesRegex(Conflict,'unregistered'):self.erasure.run('synthetic-im12',plan['id'])
        self.assertTrue((folder/'runtime.sqlite').exists());self.assertTrue((folder/'unregistered-private').exists())


    def test_restore_missing_record_or_anchor_is_not_empty_history(self):
        plan=self.plan();self.erasure.prepare('synthetic-im12',plan)
        record=self.exclusions.directory/(plan['id']+'.json');saved=record.read_bytes();record.unlink()
        with self.assertRaisesRegex(Forbidden,'record is missing'):self.exclusions.restore_constraints('synthetic-im12',self.s.instance_id)
        record.write_bytes(saved);self.exclusions.directory.joinpath('index.json').unlink()
        with self.assertRaisesRegex(Forbidden,'anchor missing'):self.exclusions.restore_constraints('synthetic-im12',self.s.instance_id)
    def test_default_exclusion_write_denial_creates_no_directory(self):
        path=Path(self.tmp.name)/'unauthorized'
        exclusions=RestoreExclusions(path,self.s.root,PropagationAuthority())
        with self.assertRaises(Forbidden):exclusions.write('untrusted',self.plan())
        self.assertFalse(path.exists())


    def test_current_sqlite_inline_body_removed_after_real_compaction(self):
        from digital_life.domain import tool_learning_contract as contract
        secret='SYNTHETIC-INLINE-ERASURE-'+identifier()
        with self.s.tx():revision=self.s.insert('memory_revisions',memory_id=self.f.source['id'],revision_no=2,content=secret,encoding_method='synthetic-physical-test')
        self.assertIn(secret.encode(),self.s.root.joinpath('runtime.sqlite').read_bytes())
        target={'target':ref(self.s,revision,'memory_revisions'),'location':'database','operation':'purge','expected':{'row_digest':contract.fingerprint(self.s.row('memory_revisions',revision))}}
        plan=self.plan([target]);self.erasure.prepare('synthetic-im12',plan);self.erasure.run('synthetic-im12',plan['id'])
        self.assertNotIn(secret.encode(),self.s.root.joinpath('runtime.sqlite').read_bytes())
        self.assertEqual(self.s.db.execute('PRAGMA freelist_count').fetchone()[0],0);self.assertFalse(self.s.integrity()['foreign_keys'])


    def test_unreconciled_process_record_blocks_physical_cleanup_without_killing_pid(self):
        import os
        control=self.f.f.control
        with control.tx():
            deployment=control.insert('deployments',release='synthetic-orphan',build_hash='0'*64,schema_min=4,schema_max=4,state='retired')
            control.insert('process_runs',deployment_id=deployment,instance_ref=self.s.instance_id,pid=os.getpid(),started_at=utc(),user_stopped=1)
        self.assertIsNone(control.state()['active_process_run_id'])
        with self.assertRaisesRegex(Forbidden,'unreconciled managed process'):self.erasure.prepare('synthetic-im12',self.plan())


class ActualM04PropagationTests(unittest.TestCase):
    def native_scenario(self,reject_commit=False):
        from tests import test_tool_learning_representation as representation
        from digital_life.application.learning.propagation import LocalOwnerActions
        fixture=representation.RepresentationTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        publish=fixture.publish_request();fixture.service.publish(fixture.entry,publish);s=fixture.s;obs=fixture.case.obs
        representation_id=s.row('tl_handoff',publish['payload']['handoff']['id'])['representation_id'];before=s.row('tl_representation',representation_id)
        request=copy.deepcopy(obs.assessment);request.update(command_id=identifier(),idempotency_key=identifier());request['principal'].update(module='M12',purpose='erase')
        request['payload']={'change_id':identifier(),'kind':'erase','source':{'object':ref(s,obs.base.f.expected['memory_id']),'revision':1,'epoch':0},'replacement':slot(),'affected_scope':obs.plan['scope'],'subjects':[],'purposes':['represent'],'expected_epoch':0,'evidence':[obs.source],'erase_scope':slot(ref(s,obs.base.f.expected['policy_id']))}
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        invalidation=ToolLearningInvalidation(s,f1_fixture.MechanicalInvalidation());barrier=invalidation.apply('mechanical-im06',request)['result_refs'][0]
        obs.base.f.control.stop('synthetic-M04-F2');s.root.joinpath('WAKE_DISABLED').write_text('synthetic')
        class Owner(MechanicalPropagation):
            def verify(self,entry,operation,request,instance_id,stage):
                super().verify(entry,operation,request,instance_id,stage)
                return StorageGrant('M04',frozenset(('tl_propagation','tl_representation')))
            def apply_actions(self,transaction,entry,request,row,minimum,verification):
                LocalOwnerActions.apply(transaction,s,'M04',ref(s,representation_id,'tl_representation'),'withdraw',0)
            def verify_actions(self,entry,request,row,minimum,verification,stage):
                if s.row('tl_representation',representation_id)['state']!='withdrawn':raise Forbidden('actual state not withdrawn')
        authority=Owner();temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        exclusions=RestoreExclusions(Path(temp.name)/'trusted',s.root,authority);erasure=ManagedErasure(s,authority,exclusions)
        plan={'contract':'TL-MANAGED-ERASURE-1','id':identifier(),'instance_id':s.instance_id,'barrier_id':barrier['id'],'source_epoch':1,'scope_id':obs.base.f.expected['policy_id'],'created_at':utc(),'deadline':request['budget']['deadline'],'authority_ref':request['principal']['actor']['id'],'source_activity':obs.work['learning_activity_id'],'caps':{'scan':10000,'items':10000,'bytes':10000000,'elapsed_ms':10000,'attempts':1},'targets':[],'allow_control_metadata':True,'retained_metadata':['opaque_ids','control_scope','source_fingerprints','plan_expected_hashes','resource_facts','action_facts'],'coverage':{'state':'unknown','domain':slot('synthetic owner domain'),'scanned':0,'limit':10000,'truncated':False,'missing':[]}}
        erasure.prepare('synthetic-im12',plan);old=s.db.execute("SELECT id FROM tl_propagation WHERE barrier_id=? AND domain='M04'",(barrier['id'],)).fetchone()[0];key=erasure.renew_generation('synthetic-im12',plan['id'],old,obs.work['id']);row=s.row('tl_propagation',key)
        minimum=s.read_artifact(row['targets_artifact_id']);coverage=copy.deepcopy(plan['coverage']);coverage['state']='partial'
        v={'contract':'TL-PROPAGATION-VERIFICATION-1','barrier':barrier,'generation':row['generation'],'domain':'M04','source_epoch':1,'minimum_plan':ref(s,row['targets_artifact_id'],'artifacts'),'targets':minimum['targets'],'actions':[],'coverage':coverage,'boundary':{'actual':'M04 representation withdrawal'},'watermark':{'epoch':1},'unresolved':['other domain targets pending'],'per_target':[]}
        artifact=s.artifact(v);request.update(command_id=identifier(),idempotency_key=identifier());request['principal'].update(module='M04',purpose='propagate');request['budget'].update(account_ref=ref(s,row['budget_account_id'],'activity_budget_accounts'),max_attempts=1,max_input_tokens=0,max_output_tokens=0,max_tool_calls=0,max_scan=10000,max_items=10000,max_bytes=10000000)
        request['expected']=slot({'object':ref(s,key,'tl_propagation'),'revision':0,'epoch':row['generation']});request['payload']={'barrier':barrier,'generation':row['generation'],'domain':'M04','targets':minimum['targets'],'coverage':coverage,'actions':[],'verification':ref(s,artifact,'artifacts')}
        service=ToolLearningPropagation(s,authority,accounting=MaintenanceReadAccounting(erasure,plan['id']))
        if reject_commit:
            def reject(stage):
                if stage=='commit':raise Forbidden('synthetic final owner revocation')
            authority.hook=reject
            with self.assertRaises(Forbidden):service.acknowledge('synthetic-im12',request)
            self.assertEqual(s.row('tl_representation',representation_id)['state'],'ready');self.assertEqual(s.row('tl_propagation',key)['state'],'pending')
            self.assertFalse(s.db.execute('SELECT 1 FROM tl_command WHERE id=?',(request['command_id'],)).fetchone())
            return
        service.acknowledge('synthetic-im12',request)
        after=s.row('tl_representation',representation_id);self.assertEqual(after['state'],'withdrawn');self.assertEqual(after['body_digest'],before['body_digest']);self.assertEqual(after['body_artifact_id'],before['body_artifact_id'])
        self.assertEqual(s.row('tl_handoff',publish['payload']['handoff']['id'])['state'],'published');self.assertEqual(s.row('tl_propagation',key)['state'],'blocked');self.assertEqual(s.row('tl_barrier',barrier['id'])['state'],'active')
        from digital_life.application.learning.propagation import ManagedInventory
        inventory=ManagedInventory(erasure,max_rows=65536).discover('synthetic-im12',plan['id'],{'object':ref(s,obs.base.f.expected['memory_id']),'revision':1,'epoch':0})
        discovered={r['id'] for r in inventory['targets']}
        self.assertIn(representation_id,discovered);self.assertIn(before['body_artifact_id'],discovered);self.assertIn(fixture.case.proposal['id'],discovered)
        self.assertNotEqual(inventory['coverage']['state'],'complete')

    def test_f2_real_withdrawal_same_transaction_and_history_retained(self):self.native_scenario()
    def test_final_owner_denial_rolls_back_real_withdrawal_and_command(self):self.native_scenario(reject_commit=True)


class ActualHTTPMaterialBoundaryTests(unittest.TestCase):
    def setUp(self):
        import threading
        self.f=f1_fixture.F1Tests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
        self.f.f.control.db.execute('UPDATE instance_control_state SET user_stopped=0 WHERE instance_ref=?',(self.s.instance_id,));self.s.root.joinpath('WAKE_DISABLED').unlink(missing_ok=True)
        self.threading=threading
    def server(self):
        from digital_life.entrypoints.http import create_server
        server=create_server(self.s.root,0);thread=self.threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(lambda:thread.join(2));self.addCleanup(server.shutdown)
        return server
    def qualified_dispatch(self,app,method,path,payload=None,controller_bearer=None):
        from digital_life.infrastructure.persistence.sqlite_store import Store
        from digital_life.application.learning.eligibility import ToolLearningEligibility
        store=Store(app.root)
        try:
            service=ToolLearningEligibility(store,f1_fixture.MechanicalEligibility())
            service.check('synthetic-http',self.f.query_principal,self.f.token,self.f.scope,'learn',self.f.query_principal['recipient'])
            return 200,{'secret':'synthetic current qualified panel material'}
        finally:store.close()
    def get(self,server):
        import http.client
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        try:
            connection.request('GET','/v1/logs',headers={'Authorization':'Bearer '+self.s.root.joinpath('controller.token').read_text().strip()})
            response=connection.getresponse();return response.status,response.read()
        finally:connection.close()
    def invalidate(self,request,finished,errors):
        from digital_life.infrastructure.persistence.sqlite_store import Store
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        store=Store(self.s.root)
        try:ToolLearningInvalidation(store,f1_fixture.MechanicalInvalidation()).apply('mechanical-im06',request)
        except BaseException as exc:errors.append(repr(exc))
        finally:store.close();finished.set()
    def test_f1_before_real_http_material_send_no_source_body(self):
        from unittest.mock import patch
        from digital_life.entrypoints.http import Application
        self.f.apply();server=self.server()
        with patch.object(Application,'dispatch',lambda app,*args,**kwargs:self.qualified_dispatch(app,*args,**kwargs)):
            status,body=self.get(server)
        self.assertEqual(status,409);self.assertNotIn(b'synthetic current qualified panel material',body)
    def test_real_http_send_first_f1_waits_through_actual_write(self):
        from unittest.mock import patch
        from digital_life.entrypoints.http import Application
        server=self.server();entered=self.threading.Event();release=self.threading.Event();finished=self.threading.Event();errors=[];received=[]
        original=server.RequestHandlerClass.send_data
        def held(handler,code,value,content_type='application/json; charset=utf-8'):
            if code==200 and isinstance(value,dict) and 'secret' in value:
                entered.set()
                if not release.wait(2):raise AssertionError('synthetic send release not received')
            return original(handler,code,value,content_type)
        with patch.object(Application,'dispatch',lambda app,*args,**kwargs:self.qualified_dispatch(app,*args,**kwargs)),patch.object(server.RequestHandlerClass,'send_data',held):
            client=self.threading.Thread(target=lambda:received.append(self.get(server)));client.start();self.assertTrue(entered.wait(2))
            change=self.threading.Thread(target=self.invalidate,args=(self.f.request(),finished,errors));change.start()
            self.assertFalse(finished.wait(.05));release.set();client.join(3);change.join(3)
        self.assertFalse(errors);self.assertTrue(finished.is_set());self.assertEqual(received[0][0],200);self.assertIn(b'synthetic current qualified panel material',received[0][1])
        with patch.object(Application,'dispatch',lambda app,*args,**kwargs:self.qualified_dispatch(app,*args,**kwargs)):
            self.assertEqual(self.get(server)[0],409)
    def test_static_auth_wait_and_protective_stop_are_not_material_routes(self):
        from digital_life.entrypoints.http import material_response_route
        for route in ('/','/assets/app.js','/v1/codex/status','/v1/codex/authorize','/v1/control/stop'):
            self.assertFalse(material_response_route('GET',route))
        for route in ('/v1/chats/a','/v1/thoughts/a','/v1/approvals/a/decision','/v1/logs/export'):
            self.assertTrue(material_response_route('POST',route))

    def test_slow_actual_http_client_releases_material_gate_with_finite_timeout(self):
        import socket,time
        from unittest.mock import patch
        from digital_life.entrypoints.http import Application
        server=self.server();sending=self.threading.Event();finished=self.threading.Event();errors=[]
        original_setup=server.RequestHandlerClass.setup;original_send=server.RequestHandlerClass.send_data
        def setup(handler):
            original_setup(handler);handler.connection.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,4096)
        def material(app,*args,**kwargs):
            self.qualified_dispatch(app,*args,**kwargs)
            return 200,b'SYNTHETIC-LOCAL-ONLY-'*(1024*1024)
        def send(handler,code,value,content_type='application/json; charset=utf-8'):
            if code==200:sending.set()
            return original_send(handler,code,value,content_type)
        with patch.object(Application,'dispatch',material),patch.object(server.RequestHandlerClass,'setup',setup),patch.object(server.RequestHandlerClass,'send_data',send):
            client=socket.create_connection(('127.0.0.1',server.server_port),timeout=3)
            try:
                client.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4096)
                token=self.s.root.joinpath('controller.token').read_text().strip()
                client.sendall(('GET /v1/logs HTTP/1.1\r\nHost: 127.0.0.1:'+str(server.server_port)+'\r\nAuthorization: Bearer '+token+'\r\n\r\n').encode())
                self.assertTrue(sending.wait(2));started=time.monotonic()
                change=self.threading.Thread(target=self.invalidate,args=(self.f.request(),finished,errors));change.start()
                self.assertTrue(finished.wait(5));change.join(1);self.assertLess(time.monotonic()-started,5)
            finally:client.close()
        self.assertFalse(errors)


class ControllerMaintenanceIntegrationTests(unittest.TestCase):
    def setUp(self):
        import secrets
        from digital_life.application.learning.maintenance import ControllerMaintenanceAuthority
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        from unittest.mock import patch
        from tests import test_tool_learning_work as work_fixture
        original_admit=work_fixture.WorkTests.admit
        def real_input(case,request=None):
            actual=case.s.row('activities',case.source_activity);signal=case.s.row('perception_signals',actual['trigger_event_id']);material=case.s.row('artifacts',signal['artifact_id'])
            command=case.request if request is None else request
            command['payload']['source'].update(source=ref(case.s,signal['id'],'perception_signals'),artifact=ref(case.s,material['id'],'artifacts'),digest={'algorithm':'sha256','hex':material['hash']},media_type=material['media_type'],view=slot(),view_digest=slot())
            return original_admit(case,command)
        self.f=f1_fixture.F1Tests()
        with patch.object(work_fixture.WorkTests,'admit',real_input):self.f.setUp()
        self.addCleanup(self.f.doCleanups);self.s=self.f.s
        self.token='Bearer '+secrets.token_urlsafe(32);self.s.root.joinpath('controller.token').write_text(self.token[7:]);self.s.root.joinpath('controller.token').chmod(0o600)
        self.f.f.control.stop('genuine-M12-fixture');self.s.root.joinpath('WAKE_DISABLED').write_text('synthetic lock')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()/'current-control-ledger'
        self.authority=ControllerMaintenanceAuthority(self.s,self.root)
        self.caps={'scan':65536,'items':65536,'bytes':64*1024*1024,'elapsed_ms':60000,'attempts':1}
        self.authority.configure(self.token,self.caps)
        original=self.s.row('activities',self.f.base.source_activity);signal=self.s.row('perception_signals',original['trigger_event_id']);self.signal=signal
        source={'object':ref(self.s,signal['id'],'perception_signals'),'revision':0,'epoch':0}
        request=self.authority.protective_request(self.token,self.f.work_id,source,self.f.scope)
        self.protective_request=request;self.protective_entry=self.authority.authorize_invalidation(self.token,request)
        self.barrier=self.authority.apply_protective(self.protective_entry,request)['result_refs'][0]
        material=self.s.row('artifacts',signal['artifact_id']);path=self.s.root/'blobs'/material['storage_ref'];st=path.stat();self.path=path
        targets=[{'target':ref(self.s,material['id'],'artifacts'),'location':'database','operation':'tombstone','expected':{'hash':material['hash'],'storage_ref':material['storage_ref']}},
                 {'target':ref(self.s,material['id'],'artifacts'),'location':'blob','operation':'unlink','expected':{'storage_ref':material['storage_ref'],'device':st.st_dev,'inode':st.st_ino}}]
        self.plan={'contract':'TL-MANAGED-ERASURE-1','id':identifier(),'instance_id':self.s.instance_id,'barrier_id':self.barrier['id'],'source_epoch':1,'scope_id':request['payload']['erase_scope']['value']['id'],'created_at':utc(),'deadline':request['budget']['deadline'],'authority_ref':self.s.config()['controller'],'source_activity':self.f.work['learning_activity_id'],'caps':copy.deepcopy(self.caps),'targets':targets,'allow_control_metadata':True,'retained_metadata':['opaque_ids','control_scope','source_fingerprints','plan_expected_hashes','resource_facts','action_facts'],'coverage':{'state':'complete','domain':slot('explicit signal artifact/database+blob managed scope'),'scanned':2,'limit':65536,'truncated':False,'missing':[]}}
    def authorized(self):
        grant=self.authority.authorize(self.token,self.plan);self.entry=grant['entries']['M12'];self.grant=grant
        self.exclusions=RestoreExclusions(self.root,self.s.root,self.authority);self.erasure=ManagedErasure(self.s,self.authority,self.exclusions)
        self.erasure.prepare(self.entry,self.plan)
        return grant
    def test_actual_bearer_current_policy_domain_f2_and_physical_f3(self):
        grant=self.authorized();old=self.s.db.execute("SELECT id FROM tl_propagation WHERE barrier_id=? AND domain='M12' AND generation=0",(self.barrier['id'],)).fetchone()[0]
        key=self.erasure.renew_generation(self.entry,self.plan['id'],old,self.f.work_id)
        request=self.authority.prepare_acknowledgement(self.entry,key,self.f.work_id)
        service=ToolLearningPropagation(self.s,self.authority,accounting=MaintenanceReadAccounting(self.erasure,self.plan['id']))
        service.acknowledge(self.entry,request);self.assertEqual(self.s.row('tl_propagation',key)['state'],'verified')
        result=self.erasure.run(self.entry,self.plan['id']);self.assertEqual(result['state'],'verified');self.assertFalse(self.path.exists())
        self.assertEqual(self.s.read_artifact(self.signal['artifact_id']),{'contract':'TL-ERASED-MATERIAL-1','plan_id':self.plan['id']})
        constraints=self.exclusions.restore_constraints(self.entry,self.s.instance_id);self.assertFalse(constraints['restore_authorized']);self.assertEqual(len(constraints['exclusions']),1)
        self.assertEqual(self.erasure.completion(self.entry,self.plan['id'])['state'],'pending') # eight real owners still unconfirmed
        self.assertTrue(self.s.root.joinpath('WAKE_DISABLED').exists());self.assertTrue(self.f.f.control.state()['user_stopped']);self.assertGreater(result['usage']['bytes'],grant['bootstrap_usage']['bytes'])
        self.assertEqual(result['usage']['attempts'],0)
    def test_forged_bearer_module_handle_or_expanded_target_refused(self):
        with self.assertRaises(Forbidden):self.authority.authorize('Bearer wrong',self.plan)
        self.authorized()
        with self.assertRaises(Forbidden):self.erasure.run('M12',self.plan['id'])
        changed=copy.deepcopy(self.plan);changed['caps']['bytes']+=1
        with self.assertRaises(Forbidden):self.authority.verify_maintenance(self.entry,changed,'run')
        changed=copy.deepcopy(self.plan);changed['targets']=[]
        with self.assertRaises(Forbidden):self.authority.verify_maintenance(self.entry,changed,'run')
        self.assertTrue(self.path.exists())
    def test_current_policy_change_or_expired_grant_refuses(self):
        self.authorized();self.authority.configure(self.token,self.caps)
        with self.assertRaisesRegex(Forbidden,'stale'):self.erasure.run(self.entry,self.plan['id'])
        self.assertTrue(self.path.exists())
    def test_registered_current_root_and_head_reject_empty_or_old_replacement(self):
        self.authorized();index=self.root.joinpath('index.json');original=index.read_bytes();index.write_text('{"contract":"TL-EXCLUSION-INDEX-1","generation":0,"entries":{}}')
        with self.assertRaisesRegex(Forbidden,'old/replaced'):self.exclusions.restore_constraints(self.entry,self.s.instance_id)
        index.write_bytes(original)
        other=RestoreExclusions(Path(self.tmp.name)/'new-empty-directory',self.s.root,self.authority);other.directory.mkdir()
        with self.assertRaises(Forbidden):other.restore_constraints(self.entry,self.s.instance_id)
        from digital_life.application.learning.maintenance import ControllerMaintenanceAuthority
        alternate=ControllerMaintenanceAuthority(self.s,other.directory)
        with self.assertRaises(Conflict):alternate.configure(self.token,self.caps)

    def test_genuine_grant_replay_preserves_account_caps_and_initial_usage(self):
        first=self.authorized();_,before=self.erasure._journal(self.plan['id'])
        second=self.authority.authorize(self.token,self.plan)
        self.assertEqual(first['grant_ref'],second['grant_ref']);self.assertEqual(first['bootstrap_usage'],second['bootstrap_usage'])
        self.erasure.prepare(second['entries']['M12'],self.plan);_,after=self.erasure._journal(self.plan['id'])
        self.assertEqual(before['account_id'],after['account_id']);self.assertEqual(before['used'],after['used'])
    def test_genuine_expiry_and_different_module_are_actual_denials(self):
        self.authorized();old=self.s.db.execute("SELECT id FROM tl_propagation WHERE barrier_id=? AND domain='M12' AND generation=0",(self.barrier['id'],)).fetchone()[0]
        key=self.erasure.renew_generation(self.entry,self.plan['id'],old,self.f.work_id);request=self.authority.prepare_acknowledgement(self.entry,key,self.f.work_id)
        wrong=copy.deepcopy(request);wrong['principal']['module']='M04'
        service=ToolLearningPropagation(self.s,self.authority,accounting=MaintenanceReadAccounting(self.erasure,self.plan['id']))
        with self.assertRaises(Forbidden):service.acknowledge(self.entry,wrong)
        self.authority.clock=lambda:self.plan['deadline']
        with self.assertRaisesRegex(Forbidden,'expired'):self.erasure.run(self.entry,self.plan['id'])
        self.assertTrue(self.path.exists())

    def test_real_f1_independent_resources_survive_expired_halted_original_work(self):
        from datetime import datetime,timedelta
        old_work=self.s.row('tl_work',self.f.work_id);old_account=self.s.row('activity_budget_accounts',old_work['budget_account_id'])
        activity=self.s.row('activities',old_work['learning_activity_id']);document=json.loads(activity['budget_json']);document['ledger']['halted']=True
        with self.s.tx():self.s.db.execute('UPDATE activities SET budget_json=? WHERE id=?',(json.dumps(document),activity['id']))
        future=(datetime.fromisoformat(old_work['deadline'].replace('Z','+00:00'))+timedelta(seconds=1)).isoformat(timespec='milliseconds').replace('+00:00','Z');self.authority.clock=lambda:future
        source={'object':ref(self.s,self.signal['id'],'perception_signals'),'revision':0,'epoch':1}
        request=self.authority.protective_request(self.token,self.f.work_id,source,self.f.scope);entry=self.authority.authorize_invalidation(self.token,request)
        result=self.authority.apply_protective(entry,request);self.assertEqual(result['disposition'],'applied')
        self.assertNotEqual(request['budget']['account_ref']['id'],old_account['id']);self.assertEqual(self.s.row('tl_work',self.f.work_id),old_work);self.assertEqual(self.s.row('activity_budget_accounts',old_account['id']),old_account)
        self.assertTrue(json.loads(self.s.row('activities',activity['id'])['budget_json'])['ledger']['halted'])
        prepared,maintenance,account,ledger=self.authority._prepared_f1(request);self.assertEqual((account['token_limit'],account['tool_call_limit'],account['attempt_limit']),(0,0,1));self.assertEqual(ledger['used']['attempts'],0)
    def test_real_f1_wrong_token_scope_epoch_or_ungranted_account_rejected(self):
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        source={'object':ref(self.s,self.signal['id'],'perception_signals'),'revision':0,'epoch':1}
        with self.assertRaises(Forbidden):self.authority.protective_request('Bearer wrong',self.f.work_id,source,self.f.scope)
        stale=copy.deepcopy(source);stale['epoch']=0
        with self.assertRaisesRegex(Conflict,'stale source epoch'):self.authority.protective_request(self.token,self.f.work_id,stale,self.f.scope)
        request=self.authority.protective_request(self.token,self.f.work_id,source,self.f.scope);entry=self.authority.authorize_invalidation(self.token,request)
        wrong=copy.deepcopy(request);wrong['payload']['affected_scope']['property']='different scope'
        with self.assertRaises(Forbidden):self.authority.apply_protective(entry,wrong)
        with self.assertRaises(Forbidden):ToolLearningInvalidation(self.s,f1_fixture.MechanicalInvalidation()).apply('mechanical-im06',request)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM tl_barrier').fetchone()[0],1)
    def test_real_f1_unknown_hold_and_ordinary_engine_cannot_use_attempt_cap(self):
        from digital_life.application.runtime.engine import Engine
        source={'object':ref(self.s,self.signal['id'],'perception_signals'),'revision':0,'epoch':1}
        request=self.authority.protective_request(self.token,self.f.work_id,source,self.f.scope);entry=self.authority.authorize_invalidation(self.token,request)
        prepared,activity,account,ledger=self.authority._prepared_f1(request)
        class NeverReasoner:
            name='must-not-enter';calls=0
            def generate(self,*args,**kwargs):self.calls+=1;raise AssertionError('model entry forbidden')
        reasoner=NeverReasoner()
        with self.assertRaisesRegex(Forbidden,'control-only'):Engine(self.s).think(activity['id'],reasoner)
        self.assertEqual(reasoner.calls,0)
        ledger['unknown']=True
        with self.s.tx():self.s.db.execute('UPDATE activities SET budget_json=? WHERE id=?',(json.dumps(ledger),activity['id']))
        with self.assertRaisesRegex(Forbidden,'unknown'):self.authority.apply_protective(entry,request)
        again=self.authority.protective_request(self.token,self.f.work_id,source,self.f.scope,change_id=request['payload']['change_id'],idempotency_key=request['idempotency_key'])
        self.assertEqual(again['budget']['account_ref'],request['budget']['account_ref'])
        self.assertTrue(self.authority._prepared_f1(again)[3]['unknown'])

    def test_same_instance_independent_signal_with_same_artifact_is_not_destroyed(self):
        self.authorized()
        with self.s.tx():other=self.s.insert('perception_signals',channel_id=self.signal['channel_id'],source_actor_id=self.s.config()['controller'],external_id='independent-synthetic-source',artifact_id=self.signal['artifact_id'],received_at=utc())
        original=self.s.read_artifact(self.signal['artifact_id']);result=self.erasure.run(self.entry,self.plan['id'])
        self.assertEqual(result['state'],'blocked');self.assertEqual(self.s.read_artifact(self.s.row('perception_signals',other)['artifact_id']),original);self.assertTrue(self.path.exists())

    def test_new_f1_before_f3_cannot_restore_using_previous_external_head(self):
        self.authorized();before=self.root.joinpath('index.json').read_bytes()
        source={'object':ref(self.s,self.signal['id'],'perception_signals'),'revision':0,'epoch':1}
        request=self.authority.protective_request(self.token,self.f.work_id,source,self.f.scope);entry=self.authority.authorize_invalidation(self.token,request)
        self.authority.apply_protective(entry,request)
        self.assertEqual(self.root.joinpath('index.json').read_bytes(),before)
        with self.assertRaisesRegex(Forbidden,'has not reached an external exclusion head'):self.exclusions.restore_constraints(self.entry,self.s.instance_id)
        pending=self.s.control_reader().execute("SELECT count(*) FROM control_commands WHERE kind='maintenance.protective_change_pending' AND state='running'").fetchone()[0]
        self.assertEqual(pending,1)

    def test_conservative_inventory_does_not_authorize_independent_shared_owner(self):
        with self.s.tx():other=self.s.insert('perception_signals',channel_id=self.signal['channel_id'],source_actor_id=self.s.config()['controller'],external_id='independent-before-grant',artifact_id=self.signal['artifact_id'],received_at=utc())
        expanded=copy.deepcopy(self.plan);expanded['targets'].append({'target':ref(self.s,other,'perception_signals'),'location':'database','operation':'purge','expected':{}})
        with self.assertRaisesRegex(Forbidden,'independent owner outside the fixed source scope'):self.authority.authorize(self.token,expanded)
        self.assertTrue(self.path.exists());self.assertTrue(self.s.row('perception_signals',other))

    def test_featureoff_with_committed_f1_has_no_legacy_body_or_model_entry(self):
        from digital_life.application.runtime.engine import Engine
        from digital_life.application.services import Memory
        from digital_life.application.runtime.execution import Executor
        from digital_life.application.monitoring.management import Management
        from digital_life.application.memory.data_management import backup_bundle
        from digital_life.application.learning.runtime import strict_feature_enabled
        from digital_life.application.learning.controller_read import ControllerMaterialReader
        from digital_life.domain.contracts import RuntimeIdentity
        self.assertFalse(strict_feature_enabled(self.s))
        class NeverReasoner:
            calls=0;name='synthetic-never'
            def generate(self,*args,**kwargs):self.calls+=1;raise AssertionError('must not enter')
        # No live runtime identity is provided here. Qualified dispatch now
        # rejects that exact identity defect before doing any source work.
        # The separately authenticated audit below proves the F1 source veto.
        reasoner=NeverReasoner();before=self.s.db.execute('SELECT count(*) FROM memory_retrieval_runs').fetchone()[0]
        with self.assertRaisesRegex(Forbidden,'current live process ownership/epoch'):Engine(self.s).think(self.f.work['learning_activity_id'],reasoner)
        with self.assertRaisesRegex(Forbidden,'current live process ownership/epoch'):Engine(self.s).process_one(reasoner)
        with self.assertRaisesRegex(Forbidden,'protected runtime'):Memory(self.s).retrieve('synthetic',self.f.base.source_activity,None)
        with self.assertRaisesRegex(Forbidden,'current live process ownership/epoch'):Executor(self.s,RuntimeIdentity(0,'unstarted')).dispatch(self.f.f.expected['intent_id'])
        with self.assertRaisesRegex(Forbidden,'protected runtime'):Management(self.s).export_logs({})
        with self.assertRaisesRegex(Forbidden,'qualified managed backup'):backup_bundle(self.s,Path(self.tmp.name)/'must-not-export')
        self.assertEqual(reasoner.calls,0);self.assertEqual(before,self.s.db.execute('SELECT count(*) FROM memory_retrieval_runs').fetchone()[0])
        self.assertFalse((Path(self.tmp.name)/'must-not-export').exists())
        # Named, authenticated and qualified read-only audit is still usable
        # under stop/lock for an independent current configuration source.
        result=ControllerMaterialReader(self.s,self.token).model();self.assertIn('configuration',result)
        reader=ControllerMaterialReader(self.s,self.token)
        with reader.boundary():
            with self.assertRaisesRegex(Forbidden,'audit source barrier'):reader.material(ref(self.s,self.signal['id']),self.signal['artifact_id'])
    def test_featureoff_permission_restore_does_not_clear_erasure_guard(self):
        from digital_life.application.learning.runtime import strict_legacy_boundary
        self.authorized();self.erasure.run(self.entry,self.plan['id'])
        # A new current policy authoring operation does not resolve old erasure
        # barriers or make unqualified historical export a new permission.
        self.authority.configure(self.token,self.caps)
        with self.assertRaisesRegex(Forbidden,'protected runtime'):strict_legacy_boundary(self.s,'legacy_body_export')
        self.assertEqual(self.s.row('tl_barrier',self.barrier['id'])['state'],'active')


class LegacyWithoutProtectionTests(unittest.TestCase):
    def test_real_schema3_without_tl_tables_keeps_existing_memory_retrieval(self):
        from evaluation.tool_learning_fixture import SyntheticToolLearningFixture
        from digital_life.application.learning.runtime import legacy_protection_present,strict_legacy_boundary
        from digital_life.application.services import Memory
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        manager=SyntheticToolLearningFixture(Path(temporary.name).resolve()/'new',schema_version=3);fixture=manager.__enter__();self.addCleanup(manager.__exit__,None,None,None)
        store=fixture.store
        self.assertFalse(store.db.execute("SELECT 1 FROM sqlite_master WHERE name='tl_barrier'").fetchone());self.assertFalse(legacy_protection_present(store));strict_legacy_boundary(store,'legacy_memory_retrieval')
        context=store.db.execute('SELECT id FROM context_snapshots WHERE activity_id=? LIMIT 1',(fixture.expected['activity_id'],)).fetchone()[0]
        result=Memory(store).retrieve(fixture.expected['memory_text'],fixture.expected['activity_id'],context)
        self.assertTrue(result['run_id']);self.assertTrue(any(item['content']==fixture.expected['memory_text'] for item in result['items']))
