"""Phase-shared control materials do not cache permission or live control."""
import copy
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from digital_life.application.learning.engine import source_scope
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc
from digital_life.infrastructure.persistence.tool_learning_readset import current_readset

class ControlMaterialSharingTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_runtime import StrictEngineEndToEndTests
        f=StrictEngineEndToEndTests();f.setUp();self.addCleanup(f.doCleanups)
        self.f=f;self.s=f.s;self.owner=f.strict.owners
        self.s.db.execute('PRAGMA journal_mode=WAL')
        self.entry,self.principal=self.owner.entry('M14','learn',self.s.config()['controller'])
    def boundary(self):return self.owner.source.verification_boundary()
    def cfgrow(self):return self.s.db.execute('SELECT * FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()
    def new_config(self,actor_change=False):
        old=self.cfgrow();body=self.s.read_artifact(old['artifact_ref'])
        if actor_change:body['self_actor']=body['controller']
        with self.s.tx():
            artifact=self.s.artifact(body)
            key=self.s.insert('configuration_versions',version='synthetic-'+identifier(),artifact_ref=artifact,hash=self.s.row('artifacts',artifact)['hash'],compatibility=old['compatibility'])
        return key
    def barrier(self,target,state='active'):
        with self.s.tx():
            artifact=self.s.artifact({'synthetic control barrier':True});scope=self.s.artifact(source_scope(self.s))
            change=self.s.insert('tl_change',change_key=identifier(),fingerprint='0'*64,payload_artifact_id=artifact,kind='revoke',source_ref_id=target,expected_epoch=0,result_epoch=1)
            return self.s.insert('tl_barrier',change_id=change,source_ref_id=target,source_epoch=1,kind='revoke',scope_artifact_id=scope,authorization_ref_id=self.principal['authorization']['id'],state=state,resolution_artifact_id=artifact if state=='resolved' else None,row_revision=0)
    def test_primary_materials_are_shared_while_real_control_and_pragmas_repeat(self):
        primary=[];control=[]
        self.s.db.set_trace_callback(primary.append);self.s.control_reader().set_trace_callback(control.append)
        with self.boundary(),patch.object(self.s,'assert_execution_allowed',wraps=self.s.assert_execution_allowed)as allowed:
            for _ in range(3):self.owner.check(self.entry,self.principal)
            self.assertGreaterEqual(allowed.call_count,3)
        self.assertEqual(sum(sql.startswith('SELECT * FROM policy_epochs WHERE')for sql in primary),1)
        self.assertEqual(sum(sql.startswith('SELECT id,artifact_ref,hash FROM configuration_versions')for sql in primary),1)
        self.assertEqual(sum(sql.startswith('SELECT 1 FROM tl_barrier WHERE')and 'source_ref_id IN'in sql for sql in primary),1)
        self.assertGreaterEqual(sum(sql=='PRAGMA user_version'for sql in primary),3)
        self.assertEqual(sum(sql.startswith('SELECT * FROM process_runs WHERE')for sql in control),3)
        self.assertGreaterEqual(sum(sql.startswith('SELECT * FROM instance_control_state WHERE')for sql in control),3)
    def test_principal_predicates_are_not_memoized(self):
        with self.boundary():
            self.owner.check(self.entry,self.principal)
            for field,value in (('purpose','represent'),('module','M04')):
                changed=copy.deepcopy(self.principal);changed[field]=value
                with self.assertRaises(Forbidden):self.owner.check(self.entry,changed)
            changed=copy.deepcopy(self.principal);changed['actor']=copy.deepcopy(self.principal['recipient'])
            with self.assertRaises(Forbidden):self.owner.check(self.entry,changed)
            self.owner.entries[self.entry]['recipient']=self.s.config()['self_actor']
            with self.assertRaises(Forbidden):self.owner.check(self.entry,self.principal)
    def test_same_connection_policy_rebinding_rechecks_old_principal(self):
        old=self.principal['authorization']['id'];other=self.s.db.execute('SELECT id FROM policy_versions WHERE instance_id=? AND id<>? LIMIT 1',(self.s.instance_id,old)).fetchone()[0]
        with self.boundary():
            self.owner.check(self.entry,self.principal)
            self.s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE instance_id=?',(other,self.s.instance_id))
            with self.assertRaises(Forbidden):self.owner.check(self.entry,self.principal)
    def test_same_connection_new_configuration_rechecks_current_actor(self):
        with self.boundary():
            self.owner.check(self.entry,self.principal);new=self.new_config(actor_change=True)
            self.assertEqual(self.cfgrow()['id'],new)
            with self.assertRaises(Forbidden):self.owner.check(self.entry,self.principal)
    def test_same_connection_active_barrier_is_rechecked_for_config_and_policy(self):
        for target in (self.cfgrow()['id'],self.principal['authorization']['id']):
            with self.boundary():
                # Previous iteration barrier was resolved through a real write.
                self.owner.check(self.entry,self.principal);barrier=self.barrier(target)
                with self.assertRaises(Forbidden):self.owner.control()
                art=self.s.artifact({'synthetic resolution':True})
                self.s.db.execute("UPDATE tl_barrier SET state='resolved',resolution_artifact_id=?,row_revision=row_revision+1 WHERE id=?",(art,barrier))
    def test_foreign_policy_write_is_rejected_even_inside_old_read_transaction(self):
        with self.assertRaises(Conflict):
            with self.boundary():
                self.s.db.execute('BEGIN');self.owner.check(self.entry,self.principal)
                other=sqlite3.connect(self.s.root/'runtime.sqlite');self.addCleanup(other.close)
                other.execute('UPDATE policy_epochs SET epoch=epoch+1 WHERE instance_id=?',(self.s.instance_id,));other.commit()
                self.owner.control()
        if self.s.db.in_transaction:self.s.db.execute('ROLLBACK')
    def test_true_process_policy_write_is_rejected(self):
        with self.assertRaises(Conflict):
            with self.boundary():
                self.owner.check(self.entry,self.principal)
                subprocess.run([sys.executable,'-c','import sqlite3,sys; d=sqlite3.connect(sys.argv[1]);d.execute("UPDATE policy_epochs SET epoch=epoch+1");d.commit();d.close()',str(self.s.root/'runtime.sqlite')],check=True,timeout=10)
                self.owner.control()
    def test_foreign_configuration_and_barrier_change_invalidate_materials(self):
        barrier=self.barrier(self.cfgrow()['id'],state='active')
        resolution=self.s.artifact({'synthetic foreign resolution':True})
        for sql,args in (("UPDATE tl_barrier SET state='resolved',resolution_artifact_id=?,row_revision=row_revision+1 WHERE id=?",(resolution,barrier)),('UPDATE configuration_versions SET hash=? WHERE id=?',('f'*64,self.cfgrow()['id']))):
            with self.assertRaises(Conflict):
                with self.boundary():
                    self.owner.principal(self.entry)
                    other=sqlite3.connect(self.s.root/'runtime.sqlite');self.addCleanup(other.close)
                    other.execute(sql,args);other.commit();self.owner.control()
    def test_control_stop_epoch_pid_and_execution_locks_are_live(self):
        with self.assertRaises((Conflict,Forbidden)),self.boundary():
            self.owner.control();self.f.control.stop('synthetic stop');self.owner.control()
        self.f.control.resume('synthetic resume')
        for lock in ('WAKE_DISABLED','RESTORE_RECONCILIATION_REQUIRED'):
            with self.assertRaises((Conflict,Forbidden)),self.boundary():
                self.owner.control();path=self.s.root/lock;path.write_text('synthetic lock')
                try:self.owner.control()
                finally:path.unlink()
        with self.assertRaises((Conflict,Forbidden)),self.boundary():
            self.owner.control();self.f.control.db.execute('UPDATE instance_control_state SET runtime_epoch=runtime_epoch+1 WHERE instance_ref=?',(self.s.instance_id,));self.owner.control()
    def test_current_process_pid_is_still_checked_without_shared_permission_result(self):
        self.owner.control()
        self.f.control.db.execute('UPDATE process_runs SET pid=pid+1000000 WHERE id=?',(self.f.identity.process_id,))
        with self.assertRaises(Forbidden):self.owner.control()
    def test_missing_configuration_denies_instead_of_reusing_old_material(self):
        self.owner.configuration();self.s.db.execute('PRAGMA foreign_keys=OFF')
        self.s.db.execute('DELETE FROM configuration_versions WHERE instance_id=?',(self.s.instance_id,))
        with self.assertRaises(Forbidden):self.owner.configuration()
    def test_missing_policy_retains_original_empty_first_row_failure(self):
        self.owner.principal(self.entry);self.s.db.execute('DELETE FROM policy_epochs WHERE instance_id=?',(self.s.instance_id,))
        with self.assertRaises(IndexError):self.owner.principal(self.entry)
    def test_midphase_configuration_file_change_cannot_use_old_decoded_body(self):
        row=self.s.row('artifacts',self.cfgrow()['artifact_ref']);path=self.s.root/'blobs'/row['storage_ref']
        with self.assertRaises((Conflict,ContractError)),self.boundary():
            self.owner.configuration();raw=path.read_bytes();path.write_bytes(b'x'*len(raw));self.owner.configuration()
    def test_uncommitted_same_connection_schema_pragma_is_read_live(self):
        with self.boundary():
            self.owner.control();self.s.db.execute('BEGIN IMMEDIATE');self.s.db.execute('PRAGMA user_version=999')
            try:
                with self.assertRaises(Forbidden):self.owner.control()
            finally:self.s.db.execute('ROLLBACK')
    def test_configuration_is_independent_and_new_phase_hashes_the_file_again(self):
        with self.boundary()as _:
            first=self.owner.configuration();expected=first['self_actor'];first['self_actor']='caller mutation'
            self.assertEqual(self.owner.configuration()['self_actor'],expected)
            stamp=current_readset(self.s).stamp
        row=self.s.row('artifacts',self.cfgrow()['artifact_ref']);path=self.s.root/'blobs'/row['storage_ref'];raw=path.read_bytes()
        with self.boundary():self.assertIsNot(current_readset(self.s).stamp,stamp)
        path.write_bytes(b'x'*len(raw))
        with self.assertRaises((ContractError,Conflict,Forbidden)):
            with self.boundary():self.owner.configuration()
    def test_config_artifact_mapping_and_midphase_file_changes_are_rejected(self):
        with self.boundary():
            self.owner.configuration();cfg=self.cfgrow();replacement=self.s.artifact({'synthetic wrong config':True});mapping=self.s.row('artifacts',replacement)
            self.s.db.execute('UPDATE artifacts SET hash=?,size=?,storage_ref=? WHERE id=?',(mapping['hash'],mapping['size'],mapping['storage_ref'],cfg['artifact_ref']))
            with self.assertRaises(Conflict):self.owner.configuration()
    def test_outside_phase_uses_safe_fresh_material_and_missing_config_denies(self):
        self.owner.configuration();row=self.s.row('artifacts',self.cfgrow()['artifact_ref']);path=self.s.root/'blobs'/row['storage_ref'];raw=path.read_bytes();path.write_bytes(b'x'*len(raw))
        with self.assertRaises((ContractError,Conflict)):self.owner.configuration()

if __name__=='__main__':unittest.main()
