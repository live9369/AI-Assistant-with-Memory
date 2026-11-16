"""PF06 fresh synthetic fault injections. No current instance or real models."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,utc
from digital_life.infrastructure.persistence.tool_learning_readset import shared_read_boundary,checkpoint,facts
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
from digital_life.domain.tool_learning_resources import DIMENSIONS
from digital_life.application.learning.eligibility import ref,ToolLearningEligibility
from tests import test_tool_learning_invalidation as f1
from tests import test_tool_learning_runtime as runtime_fixture
from tests import test_tool_learning_eligibility as eligibility_fixture
from tests import test_tool_learning_round2_graph as graph_fixture


class SharedQualificationFaultTests(unittest.TestCase):
    def setUp(self):
        self.f=f1.F1Tests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.s.db.execute('PRAGMA journal_mode=WAL')
        self.f.dependency();self.elig=self.f.elig
        self.token={'object':self.f.consumer,'revision':0,'epoch':0}
    def check(self,token=None,principal=None,scope=None):
        p=principal or self.f.query_principal
        return self.elig.check('mechanical-im06',p,token or self.token,scope or self.f.scope,p['purpose'],p['recipient'])
    def warm(self,phase):
        self.check();self.check();self.assertTrue(phase.graphs)
        with patch.object(self.elig,'_upstream_current',side_effect=AssertionError('cache hit should not retraverse')):
            self.check()
    def test_revoke_correct_erase_after_graph_hit_each_blocks(self):
        for kind in ('revoke','correct','erase'):
            # Distinct fresh mechanical fixtures preserve epoch=0 in each case.
            case=SharedQualificationFaultTests();case.setUp()
            try:
                with case.subTest(kind=kind),shared_read_boundary(case.s)as phase:
                    case.warm(phase);case.f.apply(case.f.request(kind))
                    with case.assertRaises((Conflict,Forbidden)):case.check()
            finally:case.doCleanups()
    def test_initial_revoked_source_never_gets_qualified(self):
        self.f.apply()
        with shared_read_boundary(self.s):
            with self.assertRaises((Conflict,Forbidden)):self.check()
    def test_same_connection_epoch_write_invalidates_before_next_check(self):
        with shared_read_boundary(self.s)as phase:
            self.warm(phase)
            self.f.apply();generation=phase.generation
            with self.assertRaises((Conflict,Forbidden)):self.check()
            self.assertGreaterEqual(phase.generation,generation)
    def test_stop_during_authority_read_rejects_current_check(self):
        with self.assertRaises((Conflict,Forbidden)):
            with shared_read_boundary(self.s)as phase:
                self.warm(phase);self.f.elig_auth.hook=lambda stage:self.f.f.control.stop('synthetic in-read stop')
                self.check()
    def test_source_epoch_change_during_cached_upstream_use_blocks(self):
        from digital_life.application.learning.eligibility import scope_key
        self.s.insert('tl_source_epoch',source_ref_id=self.f.source['id'],scope_key=scope_key(self.f.scope),scope_artifact_id=self.s.artifact(self.f.scope),epoch=0,row_revision=0)
        with shared_read_boundary(self.s)as phase:
            self.warm(phase);original=self.elig._upstream;injected=[]
            def mutate(*args):
                result=original(*args)
                if not injected:
                    injected.append(1)
                    self.s.db.execute('UPDATE tl_source_epoch SET epoch=epoch+1,row_revision=row_revision+1 WHERE source_ref_id=?',(self.f.source['id'],))
                return result
            with patch.object(self.elig,'_upstream',mutate):
                with self.assertRaisesRegex(Conflict,'epoch is stale'):self.check()
            self.assertEqual(injected,[1])
    def test_cancel_after_graph_hit_is_not_hidden(self):
        dep=self.s.db.execute('SELECT id FROM tl_dependency WHERE consumer_ref_id=?',(self.f.consumer['id'],)).fetchone()[0]
        self.elig.register_input('mechanical-im06',self.f.query_principal,self.f.consumer,dep)
        with shared_read_boundary(self.s)as phase:
            self.warm(phase)
            self.s.db.execute("UPDATE activities SET cancel_requested_at=? WHERE id=?",(utc(),self.f.consumer['id']))
            with self.assertRaises(Forbidden):self.elig.callback('mechanical-im06',self.f.query_principal,self.f.token,self.f.scope,'learn',self.f.query_principal['recipient'],lambda:self.fail('cancelled request entered'),request=self.f.consumer)
    def _foreign(self,method):
        path=str(self.s.root/'runtime.sqlite')
        if method=='process':
            code='import sqlite3,sys;d=sqlite3.connect(sys.argv[1]);d.execute("UPDATE activities SET revision=revision+1 WHERE id=?",(sys.argv[2],));d.commit();d.close()'
            subprocess.run([sys.executable,'-c',code,path,self.f.consumer['id']],check=True,timeout=10)
        elif method=='thread':
            errors=[]
            def run():
                try:self._foreign('connection')
                except BaseException as error:errors.append(error)
            thread=threading.Thread(target=run);thread.start();thread.join(10)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        else:
            db=sqlite3.connect(path)
            try:db.execute('UPDATE activities SET revision=revision+1 WHERE id=?',(self.f.consumer['id'],));db.commit()
            finally:db.close()
    def _foreign_case(self,method):
        with self.assertRaisesRegex(Conflict,'outside phase'):
            with shared_read_boundary(self.s)as phase:
                self.warm(phase);self.s.db.execute('BEGIN');self.s.db.execute('SELECT count(*) FROM activities').fetchone()
                try:
                    self._foreign(method)
                    p=self.f.query_principal
                    self.elig._check('mechanical-im06',p,self.token,self.f.scope,p['purpose'],p['recipient'],'fault-old-snapshot')
                finally:
                    if self.s.db.in_transaction:self.s.db.execute('ROLLBACK')
    def test_other_connection_commit_rejects_cached_graph_and_old_snapshot(self):self._foreign_case('connection')
    def test_other_thread_connection_commit_rejects_cached_graph(self):self._foreign_case('thread')
    def test_real_child_process_commit_rejects_cached_graph(self):self._foreign_case('process')
    def test_control_epoch_change_after_graph_hit_rejects(self):
        with self.assertRaisesRegex(Conflict,'control changed'):
            with shared_read_boundary(self.s)as phase:
                self.warm(phase)
                self.f.f.control.db.execute('UPDATE instance_control_state SET runtime_epoch=runtime_epoch+1 WHERE instance_ref=?',(self.s.instance_id,))
                self.check()
    def test_control_file_replacement_after_graph_hit_rejects(self):
        with self.assertRaisesRegex(Conflict,'replaced'):
            with shared_read_boundary(self.s)as phase:
                self.warm(phase);path=self.s.root/'control.sqlite';path.rename(self.s.root/'old-control.sqlite');path.write_bytes(b'synthetic replaced control')
                self.check()
    def test_blob_tamper_during_graph_hit_rejects(self):
        with self.assertRaisesRegex(Conflict,'artifact changed'):
            with shared_read_boundary(self.s)as phase:
                self.warm(phase);self.assertTrue(phase.blobs)
                path=next(iter(phase.blobs));raw=path.read_bytes();path.write_bytes(b'x'*len(raw));self.check()
    def test_blob_parent_replacement_after_graph_hit_rejects(self):
        with self.assertRaisesRegex(Conflict,'directory replaced'):
            with shared_read_boundary(self.s)as phase:
                self.warm(phase);folder=self.s.root/'blobs';folder.rename(self.s.root/'old-blobs');folder.symlink_to(self.s.root/'old-blobs',target_is_directory=True);self.check()
    def test_purpose_and_recipient_checks_still_run_after_graph_hit(self):
        with shared_read_boundary(self.s)as phase:
            self.warm(phase)
            for axis in ('purpose','recipient'):
                p=deepcopy(self.f.query_principal)
                if axis=='purpose':p['purpose']='history_audit'
                else:p['recipient']=ref(self.s,self.f.f.expected['controller'])
                with patch.object(self.f.elig_auth,'verify',side_effect=Forbidden('synthetic separate '+axis))as verify:
                    with self.assertRaisesRegex(Forbidden,'separate '+axis):self.check(principal=p)
                    self.assertTrue(verify.called)
    def test_delete_only_path_does_not_support_but_erase_still_blocks(self):
        # Existing read path remains independent from this delete-only consumer.
        consumer=ref(self.s,self.s.artifact({'delete obligation':'same original source'}))
        dep={'target':self.f.source,'relation':'delete','expected':self.f.token,'consumer_purpose':'learn'}
        self.elig.register_dependency('mechanical-im06',self.f.query_principal,consumer,dep,'/delete',self.f.scope)
        token={'object':consumer,'revision':0,'epoch':0}
        with shared_read_boundary(self.s)as phase:
            self.check(token);self.check(token);self.assertTrue(phase.graphs)
            self.f.apply();self.check(token)
            self.f.apply(self.f.request('erase',1))
            with self.assertRaises(Forbidden):self.check(token)


class SharedRuntimeInvokeFaultTests(unittest.TestCase):
    def setUp(self):
        self.f=runtime_fixture.AssemblyGateTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.phases=0;self.graph_hits=0
        # Mechanical authority is explicitly trusted only in this fixture. Each
        # qualification has its own phase; no phase spans the actual callback.
        checker=self.f.runtime.eligibility;original=checker._check
        def checked(entry,principal,token,scope,purpose,recipient,stage,scan_budget=None):
            with shared_read_boundary(self.s)as phase:
                checker._upstream(token,scope,{'remaining':checker.max_rows})
                checker._upstream(token,scope,{'remaining':checker.max_rows})
                self.assertTrue(phase.graphs);self.phases+=1
                with patch.object(checker,'_upstream_current',side_effect=AssertionError('prepared graph must hit')):
                    result=original(entry,principal,token,scope,purpose,recipient,stage,scan_budget)
                    self.graph_hits+=1
                return result
        self.patch=patch.object(checker,'_check',checked);self.patch.start();self.addCleanup(self.patch.stop)
    def test_successful_runtime_callback_has_new_shared_checks_each_side(self):
        self.f.assemble();before=self.graph_hits;calls=[]
        self.assertEqual(self.f.invoke(lambda:calls.append('fake-model')or 'result'),'result')
        self.assertEqual(calls,['fake-model']);self.assertGreater(self.graph_hits,before)
        self.assertGreater(self.phases,2)
    def _before(self,kind):
        self.f.assemble();self.assertGreater(self.graph_hits,0)
        self.f.base.apply(self.f.base.request(kind));calls=[]
        with self.assertRaises((Conflict,Forbidden)):self.f.invoke(lambda:calls.append('forbidden model'))
        self.assertEqual(calls,[]);self.assertFalse(self.s.rows('thought_results'))
    def test_source_revoke_after_assembly_before_model_blocks(self):self._before('revoke')
    def test_source_correct_after_assembly_before_model_blocks(self):self._before('correct')
    def test_source_erase_after_assembly_before_model_blocks(self):self._before('erase')
    def _after(self,kind):
        self.f.assemble();calls=[]
        def fake():
            calls.append('entered-once');self.f.base.apply(self.f.base.request(kind));return 'late withdrawn content'
        with self.assertRaises((Conflict,Forbidden)):self.f.invoke(fake)
        self.assertEqual(calls,['entered-once']);self.assertFalse(self.s.rows('thought_results'))
    def test_revoke_inside_model_callback_refuses_late_result(self):self._after('revoke')
    def test_correct_inside_model_callback_refuses_late_result(self):self._after('correct')
    def test_erase_inside_model_callback_refuses_late_result(self):self._after('erase')
    def test_control_stop_after_assembly_blocks_model(self):
        self.f.assemble();self.f.base.f.control.stop('synthetic before model');calls=[]
        with self.assertRaises(Forbidden):self.f.invoke(lambda:calls.append(1))
        self.assertEqual(calls,[]);self.assertFalse(self.s.rows('thought_results'))
    def test_control_stop_inside_model_callback_refuses_late_result(self):
        self.f.assemble();calls=[]
        def fake():calls.append(1);self.f.base.f.control.stop('synthetic during model');return 'late'
        with self.assertRaises(Forbidden):self.f.invoke(fake)
        self.assertEqual(calls,[1]);self.assertFalse(self.s.rows('thought_results'))
    def test_partial_assembly_cannot_enter_fake_model(self):
        original=self.f.runtime.eligibility.register_input;calls=[]
        def partial(*args,**kwargs):
            calls.append(1)
            if len(calls)==2:raise Forbidden('synthetic partial registration')
            return original(*args,**kwargs)
        with patch.object(self.f.runtime.eligibility,'register_input',partial):
            with self.assertRaisesRegex(Forbidden,'partial registration'):self.f.assemble()
        self.assertGreater(self.graph_hits,0)
        with self.assertRaises(Forbidden):self.f.invoke(lambda:self.fail('partial assembly model'))
        self.assertFalse(self.s.rows('thought_results'))
    def test_unknown_callback_failure_is_not_retried_or_saved(self):
        self.f.assemble();calls=[]
        def fake():calls.append(1);raise OSError('synthetic unknown model result')
        with self.assertRaisesRegex(OSError,'unknown model'):self.f.invoke(fake)
        self.assertEqual(calls,[1]);self.assertFalse(self.s.rows('thought_results'))


class SharedMaterialBudgetFaultTests(unittest.TestCase):
    def setUp(self):
        self.f=graph_fixture.SharedSourceGraphTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s
    def meter(self,**changes):
        limits={key:100000000 for key in DIMENSIONS};limits.update(changes)
        return PhysicalReadMeter(limits,utc(60))
    def _artifact_rebind(self,mode):
        from digital_life.domain.contracts import dumps,sha
        row=self.s.db.execute('SELECT * FROM tl_dependency WHERE consumer_ref_id=? ORDER BY id',(self.f.refs[0]['id'],)).fetchone()
        artifact=self.s.row('artifacts',row['metadata_artifact_id'])
        original=self.s.read_artifact(artifact['id']);changed=deepcopy(original)
        changed['scope']['conditions']['value']['interpretation']='new artifact identity must replace old JSON'
        raw=dumps(changed).encode('utf-8');checksum=sha(raw)
        (self.s.root/'blobs'/checksum).write_bytes(raw)
        meter=self.meter()
        with meter.installed(self.s),shared_read_boundary(self.s)as phase:
            first=self.f.checker._metadata(row);self.f.checker._metadata(row)
            self.assertTrue(phase.prepared)
            if mode=='hash':
                self.s.db.execute('UPDATE artifacts SET hash=? WHERE id=?',(checksum,artifact['id']))
            elif mode=='location':
                self.s.db.execute('UPDATE artifacts SET storage_ref=? WHERE id=?',(checksum,artifact['id']))
            else:
                self.s.db.execute('UPDATE artifacts SET hash=?,storage_ref=?,size=? WHERE id=?',(checksum,checksum,len(raw),artifact['id']))
            if mode in ('hash','location'):
                with self.assertRaisesRegex(ContractError,'size/digest mismatch'):self.f.checker._metadata(row)
            else:
                second=self.f.checker._metadata(row)
                self.assertNotEqual(first['scope'],second['scope']);self.assertEqual(second['scope'],changed['scope'])
    def test_same_connection_artifact_hash_change_does_not_hit_old_preparation(self):self._artifact_rebind('hash')
    def test_same_connection_artifact_location_change_does_not_hit_old_json(self):self._artifact_rebind('location')
    def test_same_connection_full_artifact_identity_rebind_uses_new_scope(self):self._artifact_rebind('full')
    def test_unknown_original_budget_hold_survives_shared_phase(self):
        case=runtime_fixture.OriginalActivityBudgetTests();case.setUp();self.addCleanup(case.doCleanups)
        with shared_read_boundary(case.s)as phase:
            list(facts(case.s,'source_kind',case.s.config()['controller']))
            self.assertTrue(phase.cache)
            case.test_unknown_actual_preserves_original_full_hold()
        snapshot=case.budget.check_activity(case.activity)
        self.assertIn('usage_unknown',snapshot['block_reasons']);self.assertEqual(snapshot['remaining']['bytes'],0)
    def test_partial_dependency_cursor_is_not_cached_as_complete(self):
        sql=[];self.s.db.set_trace_callback(sql.append)
        with shared_read_boundary(self.s)as phase:
            stream=facts(self.s,'consumer_dependencies',self.f.refs[0]['id'],100)
            next(stream);stream.close()
            self.assertFalse(any(key[0]=='consumer_dependencies' for key in phase.cache))
            rows=list(facts(self.s,'consumer_dependencies',self.f.refs[0]['id'],100))
            self.assertEqual(len(rows),3)
            self.assertEqual(sum('SELECT * FROM tl_dependency WHERE'in statement for statement in sql),2)
    def test_cached_graph_still_spends_original_logical_budget(self):
        with shared_read_boundary(self.s)as phase:
            self.f.graph();self.f.graph();self.assertTrue(phase.graphs)
            low={'remaining':0}
            with self.assertRaisesRegex(Forbidden,'row scan limit'):self.f.graph(budget=low)
            self.assertEqual(low['remaining'],-1)
    def test_meter_blocks_before_second_physical_row_and_keeps_first_charge(self):
        meter=self.meter();baseline=None
        with self.assertRaisesRegex(Forbidden,'slice exhausted'):
            with meter.installed(self.s),shared_read_boundary(self.s):
                # Phase freshness PRAGMAs are actual charged rows too. Leave
                # exactly one further row after those startup probes.
                baseline=dict(meter.actual)
                meter.limits['scan']=baseline['scan']+1;meter.limits['items']=baseline['items']+1
                rows=facts(self.s,'consumer_dependencies',self.f.refs[0]['id'],100)
                next(rows);next(rows)
        self.assertEqual(meter.actual['scan'],baseline['scan']+1);self.assertEqual(meter.actual['items'],baseline['items']+1)
        self.assertGreater(meter.actual['bytes'],baseline['bytes'])
    def test_failed_artifact_file_read_keeps_usage_unknown_inside_phase(self):
        artifact=self.s.artifact({'unknown':'must not become zero'});meter=self.meter()
        actual=Path.read_bytes
        def broken(path):
            if path.parent==self.s.root/'blobs':raise OSError('synthetic read interrupted')
            return actual(path)
        with meter.installed(self.s),shared_read_boundary(self.s),patch.object(Path,'read_bytes',broken):
            with self.assertRaisesRegex(OSError,'interrupted'):self.s.read_artifact(artifact)
            self.assertIsNone(meter.usage());self.assertTrue(meter.unknown_bytes)
    def test_store_cache_hit_tracks_file_and_detects_same_inode_tamper(self):
        artifact=self.s.artifact({'store raw':'tracked'});meter=self.meter()
        with self.assertRaisesRegex(Conflict,'artifact changed'):
            with meter.installed(self.s),shared_read_boundary(self.s)as phase:
                self.s.read_artifact(artifact);before=meter.actual['bytes'];self.s.read_artifact(artifact)
                self.assertTrue(phase.blobs);self.assertGreaterEqual(meter.actual['bytes'],before)
                path=self.s.root/'blobs'/self.s.row('artifacts',artifact)['storage_ref'];raw=path.read_bytes();path.write_bytes(b'x'*len(raw));self.s.read_artifact(artifact)
    def test_store_raw_cache_same_name_inode_replacement_is_detected(self):
        artifact=self.s.artifact({'store raw':'replaced inode'});meter=self.meter()
        with self.assertRaisesRegex(Conflict,'artifact changed'):
            with meter.installed(self.s),shared_read_boundary(self.s):
                self.s.read_artifact(artifact)
                path=self.s.root/'blobs'/self.s.row('artifacts',artifact)['storage_ref'];raw=path.read_bytes()
                replacement=self.s.root/'replacement';replacement.write_bytes(raw);replacement.replace(path)
                self.s.read_artifact(artifact)
    def test_expired_meter_cannot_return_shared_graph_material(self):
        meter=self.meter();meter.deadline=utc(-1)
        with self.assertRaisesRegex(Forbidden,'deadline exhausted'):
            with meter.installed(self.s),shared_read_boundary(self.s):self.f.graph()
    def test_identical_original_text_in_distinct_events_is_never_one_origin(self):
        from digital_life.application.learning.engine import _dependency
        with self.s.tx():
            first=ref(self.s,self.s.event('pf06.original',payload={'text':'the identical original sentence'},source='pf06',key='one'))
            second=ref(self.s,self.s.event('pf06.original',payload={'text':'the identical original sentence'},source='pf06',key='two'))
            consumer=ref(self.s,self.s.artifact({'consumer':'two identical original messages'}))
            for index,origin in enumerate((first,second)):
                _dependency(self.s,consumer,{'object':origin,'revision':0,'epoch':0},self.f.scope,'read','/same-text/'+str(index),'learn')
        token={'object':consumer,'revision':0,'epoch':0}
        with shared_read_boundary(self.s)as phase:
            original=self.f.graph(token=token);self.assertEqual(self.f.graph(token=token),original)
            self.assertTrue(phase.graphs)
            ids=[row[0]for row in original];self.assertIn(first['id'],ids);self.assertIn(second['id'],ids)
            self.assertNotEqual(first['id'],second['id'])
    def test_tracking_overflow_disables_graph_and_raw_reuse(self):
        one=self.s.artifact({'overflow':1});two=self.s.artifact({'overflow':2});meter=self.meter()
        with meter.installed(self.s),shared_read_boundary(self.s)as phase:
            phase.max_artifacts=1;self.s.read_artifact(one);self.s.read_artifact(two)
            self.assertFalse(phase.reusable);self.assertFalse(phase.graphs);self.assertFalse(phase.cache)
            before=meter.actual['bytes'];self.s.read_artifact(two);self.assertGreater(meter.actual['bytes'],before)
    def test_same_text_different_origin_scope_and_multipaths_stay_distinct(self):
        with shared_read_boundary(self.s)as phase:
            original=self.f.graph();self.f.graph();self.f.graph();self.assertTrue(phase.graphs)
            changed=deepcopy(self.f.scope);changed['conditions']['value']['interpretation']='different meaning'
            other=self.f.graph(scope=changed);self.f.graph(scope=changed)
            self.assertNotEqual(original[0][1],other[0][1]);self.assertGreaterEqual(len(phase.graphs),2)
            source_ids=[row[0]for row in original];self.assertGreater(len(source_ids),len(set(source_ids)))
            self.assertTrue(any('delete'in row[3] for row in original))
            self.assertTrue(any(row[3] and 'delete'not in row[3] for row in original))


class DirectLocalEligibilityFaultTests(unittest.TestCase):
    def setUp(self):
        self.f=runtime_fixture.StrictEngineEndToEndTests();self.f.enable_features=False
        self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
        from digital_life.application.learning.engine import source_scope
        self.scope=source_scope(self.s);self.owners=self.f.strict.owners
        self.entry,self.principal=self.owners.entry('M14','learn')
        self.origin=ref(self.s,self.s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()[0]);self.token=self.owners.token(self.origin,self.scope)
    def test_direct_verify_rechecks_foreign_commit_before_old_owner_memo(self):
        authority=self.owners.source
        with self.assertRaisesRegex(Conflict,'outside phase'):
            with authority.verification_boundary():
                authority.verify(self.entry,self.principal,self.token,self.scope,'learn',self.principal['recipient'],'direct-port')
                authority.verify(self.entry,self.principal,self.token,self.scope,'learn',self.principal['recipient'],'direct-port')
                db=sqlite3.connect(self.s.root/'runtime.sqlite')
                try:db.execute('UPDATE activities SET revision=revision+1 WHERE id=?',(self.f.activity,));db.commit()
                finally:db.close()
                authority.verify(self.entry,self.principal,self.token,self.scope,'learn',self.principal['recipient'],'direct-port')
    def test_direct_verify_version_rechecks_foreign_commit_before_memo(self):
        authority=self.owners.source
        with self.assertRaisesRegex(Conflict,'outside phase'):
            with authority.verification_boundary():
                authority.verify_version(self.entry,self.principal,self.token,'direct-port')
                authority.verify_version(self.entry,self.principal,self.token,'direct-port')
                db=sqlite3.connect(self.s.root/'runtime.sqlite')
                try:db.execute('UPDATE activities SET revision=revision+1 WHERE id=?',(self.f.activity,));db.commit()
                finally:db.close()
                authority.verify_version(self.entry,self.principal,self.token,'direct-port')


class SharedNativeRevisionFaultTests(unittest.TestCase):
    def test_native_content_selected_revision_and_revocation_with_actual_graph_hits(self):
        case=eligibility_fixture.EligibilityTests();case.setUp();self.addCleanup(case.doCleanups)
        original=case.case.check;hits=[]
        def check(*args,**kwargs):
            result=original(*args,**kwargs);self.assertEqual(result,original(*args,**kwargs))
            with patch.object(case.elig,'_upstream_current',side_effect=AssertionError('native graph must hit')):
                repeated=original(*args,**kwargs)
            hits.append(1);self.assertEqual(result,repeated);return result
        case.case.check=check
        with shared_read_boundary(case.s):case.test_selected_native_revision_keeps_independent_support_and_inputs()
        self.assertGreaterEqual(len(hits),3)
    def test_snapshot_bridge_hit_and_tampered_event_mapping_rejected(self):
        case=runtime_fixture.SourceSnapshotTests();case.setUp();self.addCleanup(case.doCleanups)
        token=case.capture();checker=ToolLearningEligibility(case.s,f1.MechanicalEligibility())
        with shared_read_boundary(case.s)as phase:
            checker._upstream(token,case.scope,{'remaining':1024})
            checker._upstream(token,case.scope,{'remaining':1024})
            with patch.object(checker,'_upstream_current',side_effect=AssertionError('snapshot bridge graph must hit')):
                checker._upstream(token,case.scope,{'remaining':1024})
            self.assertTrue(phase.graphs)
            known=deepcopy(token['object']);known['revision']=f1.slot(token['revision'])
            checker.artifacts.validate_ref(known)
            event=case.s.db.execute('SELECT id FROM object_revision_registry WHERE object_id=?',(case.origin['id'],)).fetchone()[0]
            case.s.db.execute("UPDATE runtime_events SET source='broken-mapping' WHERE id=?",(event,))
            with self.assertRaises(Conflict):checker.artifacts.validate_ref(known)

if __name__=='__main__':unittest.main()
