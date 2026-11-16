"""IM15 only new synthetic releases/instances; no model or formal deployment."""
from pathlib import Path
import copy
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Forbidden,utc,identifier,dumps,sha
from digital_life.infrastructure.persistence.sqlite_store import Store,PROJECT
from digital_life.application.lifecycle.control_plane import Control,Releases
from digital_life.application.lifecycle.deployment import Deployment
from digital_life.application.learning.bridge import CAPABILITY,source_files,loaded_runtime,verify_handshake


class BridgeFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()/'synthetic-instance'
        self.s=Store.prepare(self.root);self.addCleanup(self.s.close)
        self.s.db.executescript((PROJECT/'digital_life/resources/tool_learning_v1.sql').read_text());self.s.db.execute('PRAGMA user_version=4')
        self.s.columns={row[0]:{c[1] for c in self.s.db.execute('PRAGMA table_info('+row[0]+')')} for row in self.s.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.c=Control(self.root,self.s.instance_id);self.addCleanup(self.c.close);self.releases=Releases(self.c)
    def unlock(self):
        self.assertTrue(self.root.is_relative_to(Path(self.tmp.name).resolve()));(self.root/'WAKE_DISABLED').unlink();self.c.resume('explicit-synthetic-unlock')
    def stage(self):return self.releases.stage(PROJECT)
    def fake_source(self,high=3):
        source=Path(self.tmp.name)/identifier();(source/'digital_life/resources').mkdir(parents=True)
        (source/'digital_life/__init__.py').write_text("__version__='0.5.0'\n")
        description={'schema_min':2,'schema_max':high,'engineering_version':'0.5.0'}
        if high==4:description.update(tool_learning_bridge=copy.deepcopy(CAPABILITY),capabilities=['TL-LOOP-0.1'])
        (source/'digital_life/resources/release.json').write_text(dumps(description));return source


class BaselineTests(BridgeFixture):
    def test_current_baseline_is_registered_and_verified_not_a_boolean(self):
        deployment=self.stage();path=self.releases.verify(deployment)
        record=self.c.db.execute("SELECT payload FROM control_commands WHERE kind='bridge.baseline_verified'").fetchone()
        self.assertIsNotNone(record);proof=json.loads(record[0]);self.assertEqual(proof['build_hash'],self.c.db.execute('SELECT build_hash FROM deployments WHERE id=?',(deployment,)).fetchone()[0]);self.assertEqual(proof['capability'],CAPABILITY)
        with self.assertRaises(Forbidden):loaded_runtime(self.c,self.s,deployment,PROJECT/'digital_life/entrypoints/runtime.py')
        # Passing a path string cannot pretend our already-imported parent
        # modules came from that release. The real child below is the positive.
        with self.assertRaises(Forbidden):loaded_runtime(self.c,self.s,deployment,path/'digital_life/entrypoints/runtime.py')
    def test_schema4_self_declaration_is_not_reviewed_executable_baseline(self):
        with self.assertRaises(Forbidden):self.releases.stage(self.fake_source(4))
        self.assertFalse(self.c.db.execute('SELECT 1 FROM deployments').fetchone())
    def test_private_directories_are_pruned_without_read_or_descent_but_public_config_remains(self):
        source=self.fake_source(3);private=[]
        for name in ('config/local','.codex','.agents','.aws','workspace','inbound','launches'):
            directory=source/name;directory.mkdir(parents=True,exist_ok=True);(directory/'sentinel.json').write_text('{"secret":"synthetic sentinel must never be opened"}');private.append(directory)
        public=source/'config/examples';public.mkdir(parents=True);(public/'remote-template.json').write_text('{"key_env":"EXAMPLE_ONLY"}')
        actual_scan=os.scandir;actual_read=Path.read_bytes
        def forbidden(path):
            if type(path) is int:return False  # shutil cleanup uses its own directory fd.
            path=Path(path)
            return any(path==directory or directory in path.parents for directory in private)
        def scan(path):
            if forbidden(path):raise AssertionError('private directory was traversed')
            return actual_scan(path)
        def read(path):
            if forbidden(path):raise AssertionError('private file bytes were read')
            return actual_read(path)
        with patch('os.scandir',side_effect=scan),patch.object(Path,'read_bytes',read):
            found={str(name):raw for name,raw in source_files(source)};deployment=self.releases.stage(source)
        self.assertIn('config/examples/remote-template.json',found);self.assertFalse(any(any(part in path.split('/') for part in ('.codex','.agents','.aws','workspace','inbound','launches')) or path.startswith('config/local/') for path in found))
        manifest=json.loads((self.releases.verify(deployment)/'manifest.json').read_text());self.assertEqual(set(manifest),set(found))

    def test_old2_and3_cannot_activate_or_recover_schema4(self):
        for version in (2,3):
            deployment=self.releases.stage(self.fake_source(version));self.assertFalse(self.releases.compatible(deployment));self.assertFalse(self.releases.recoverable(deployment))
            result=self.releases.activate(deployment,lambda _:self.fail('incompatible code cannot be launched'));self.assertFalse(result['switched'])
    def test_tampered_staged_code_and_missing_capability_record_rejected(self):
        deployment=self.stage();path=self.releases.verify(deployment);file=path/'digital_life/entrypoints/runtime.py';file.write_text(file.read_text()+'\n# modified after stage\n')
        with self.assertRaises(ContractError):self.releases.verify(deployment)
        self.assertFalse(self.releases.recoverable(deployment))
    def test_schema4_activation_rejects_bool_only_readiness(self):
        deployment=self.stage();result=self.releases.activate(deployment,lambda _: {'ready':True,'schema_compatible':True})
        self.assertFalse(result['switched']);self.assertFalse(self.c.db.execute("SELECT 1 FROM deployments WHERE state='active'").fetchone())
    def test_unregistered_source_shadow_module_cannot_receive_bridge_capability(self):
        files=source_files(PROJECT);source=Path(self.tmp.name)/'copied-baseline';source.mkdir()
        for name,raw in files:
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        (source/'json.py').write_text('raise RuntimeError("untrusted import shadow")\n')
        with self.assertRaises(Forbidden):self.releases.stage(source)


class ActualRuntimeBridgeTests(BridgeFixture):
    def test_actual_idle_process_featureoff_prepares_runs_heartbeats_and_user_stops(self):
        deployment=self.stage();before=self.s.db.total_changes;self.unlock();manager=Deployment(self.c);self.addCleanup(lambda:manager.driver.stop(manager.active['process']) if manager.active else None)
        result=manager.launch(deployment,timeout=10);self.assertTrue(result['switched']);self.assertEqual(result['handshake']['capability']['schema_version'],4)
        self.assertFalse(result['handshake']['model_access_verified']);self.assertEqual(result['handshake']['inference_ready'],'unknown')
        self.assertEqual(manager.check()['state'],'running');self.assertFalse(self.s.rows('thought_requests'));self.assertFalse(self.s.rows('tl_work'))
        self.c.stop('explicit-synthetic-user-stop');status=manager.check();self.assertEqual(status['state'],'user_stopped');self.assertFalse(status['rollback'])
        self.assertFalse(self.c.db.execute('SELECT 1 FROM process_runs WHERE instance_ref=? AND exited_at IS NULL',(self.s.instance_id,)).fetchone())
    def test_no_caps_inbound_body_is_not_read_and_idle_runtime_stays_alive(self):
        source='im15-controller';key=identifier();receipt=self.c.accept_inbound(source,key,{'text':'synthetic input requires original resource authorization'},self.s.config()['controller'])
        row=self.c.db.execute('SELECT * FROM inbound_requests WHERE id=?',(receipt,)).fetchone();path=self.root/'inbound'/row['payload_path']
        # This controlled corrupt body would make transfer exit immediately if
        # it were read. The cap guard must precede access to this file.
        path.write_text('{"unread_synthetic_marker":true}')
        deployment=self.stage();self.unlock();manager=Deployment(self.c);self.addCleanup(lambda:manager.driver.stop(manager.active['process']) if manager.active else None)
        self.assertTrue(manager.launch(deployment,timeout=10)['switched']);time.sleep(.35)
        self.assertEqual(manager.check()['state'],'running');heartbeat=json.loads(manager.active['ready'].read_text());self.assertFalse(heartbeat['ordinary_activity_ready'])
        self.assertEqual(self.c.db.execute('SELECT state FROM inbound_requests WHERE id=?',(receipt,)).fetchone()[0],'received')
        self.assertFalse(self.s.rows('activities'));self.assertFalse(self.s.rows('thought_requests'));self.c.stop('synthetic nocap test stop');manager.check()
    def test_unprotected_schema3_transfer_still_reads_and_acknowledges_real_controller_input(self):
        from digital_life.application.runtime.configuration import configure_model
        # No task processing or provider is needed to verify the old explicit
        # transfer entrypoint. It reads the genuine receipt and preserves key.
        self.s.db.execute('PRAGMA user_version=3');receipt=self.c.accept_inbound('im15-legacy-controller','legacy-key',{'text':'synthetic legacy input'},self.s.config()['controller'])
        activities=self.c.transfer_inbound(self.s);self.assertEqual(len(activities),1)
        state=self.c.db.execute('SELECT state FROM inbound_requests WHERE id=?',(receipt,)).fetchone()[0];self.assertEqual(state,'delivered')
        again=self.c.transfer_inbound(self.s);self.assertEqual(again,[]);self.assertFalse(self.s.rows('thought_requests'))

    def test_prepared_loaded_capability_mismatch_is_rejected_without_activation(self):
        deployment=self.stage();self.unlock()
        class Process:
            pid=444
            def poll(self):return None
        class WrongDriver:
            def launch(self,*args):return Process()
            def await_state(self,process,ready,desired,timeout):return {'state':desired,'deployment':deployment,'schema_compatible':True,'pid':444,'capability':{'schema_version':4}}
            def stop(self,process):self.stopped=True
        driver=WrongDriver();manager=Deployment(self.c,driver);result=manager.launch(deployment)
        self.assertFalse(result['switched']);self.assertTrue(driver.stopped);self.assertFalse(self.c.db.execute("SELECT 1 FROM deployments WHERE state='active'").fetchone())


class FeatureOffPlaneTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_runtime import StrictActualUseTests
        self.f=StrictActualUseTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
        self.k=self.f.k;active=self.s.rows('policy_epochs')[0];old=self.s.row('policy_versions',active['policy_version_id']);scope=json.loads(old['scope']);scope['tool_learning_runtime']['enabled']=False
        policy=self.s.insert('policy_versions',version=800,mode=old['mode'],scope=scope,effective_at=utc(),authority=self.s.config()['controller'])
        self.s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE id=?',(policy,active['id']))
    def test_schema4_featureoff_still_selects_qualified_runtime_and_blocks_new_learning(self):
        from digital_life.application.learning.runtime import qualified_plane_required,strict_feature_enabled
        from digital_life.application.learning.runtime_learning import StrictLearningCoordinator
        from digital_life.application.runtime.engine import Engine
        self.assertTrue(qualified_plane_required(self.s));self.assertFalse(strict_feature_enabled(self.s))
        coordinator=StrictLearningCoordinator(self.k)
        signal=self.s.row('activities',self.f.activity)['trigger_event_id']
        with self.assertRaisesRegex(Forbidden,'learning is disabled'):coordinator.admit(self.f.activity,signal,{'kind':'json_pointer','pointer':'/text'})
        self.assertFalse(self.s.rows('tl_work'))
        before=self.s.db.total_changes
        for call in (lambda:coordinator.assess('absent-work'),lambda:coordinator.decide('absent-proposal'),lambda:coordinator.publish('absent-handoff'),lambda:coordinator.project('absent-work'),lambda:coordinator.resume_work('absent-work',[])):
            with self.assertRaisesRegex(Forbidden,'learning is disabled'):call()
        self.assertEqual(self.s.db.total_changes,before)
        with patch.object(self.k,'prepare',side_effect=Forbidden('actual qualified preparation reached')):
            with self.assertRaisesRegex(Forbidden,'qualified preparation'):Engine(self.s,self.f.f.identity,strict_runtime=self.k).prepare(self.f.activity,None)
    def test_schema3_managed_material_still_requires_qualified_plane_when_learning_off(self):
        from digital_life.application.learning.runtime import qualified_plane_required
        from digital_life.application.services import Memory
        self.f.producer();self.s.db.execute('PRAGMA user_version=3')
        self.assertFalse(self.s.rows('tl_barrier'));self.assertTrue(qualified_plane_required(self.s))
        context=self.s.rows('context_snapshots')[0]['id']
        with self.assertRaises(Forbidden):Memory(self.s).retrieve('private historical input',self.f.activity,context)

    def test_old_pending_without_original_eight_dimensional_ledger_is_not_re_admitted(self):
        from digital_life.application.runtime.engine import Engine
        old_activity=self.f.f.base.source_activity;old=self.s.row('activities',old_activity)
        with self.assertRaises((ContractError,Forbidden)):Engine(self.s,self.f.f.identity,strict_runtime=self.k).prepare(old_activity,None)
        current=self.s.row('activities',old_activity);self.assertEqual(current['budget_json'],old['budget_json']);self.assertEqual(current['deadline'],old['deadline']);self.assertFalse(self.s.rows('thought_requests'))
    def test_actual_fake_model_round_remains_qualified_without_creating_learning_work(self):
        from digital_life.application.runtime.engine import Engine
        result=Engine(self.s,self.f.f.identity,strict_runtime=self.k).think(self.f.activity)
        self.assertTrue(result['accepted']);self.assertFalse(self.s.rows('tl_work'))
        row=self.s.row('thought_requests',result['request_id']);packet=self.s.read_artifact(row['request_artifact_id'])
        self.assertEqual(packet['request_id'],row['id']);self.assertGreater(len(self.s.rows('tl_input_dependency')),0)
        self.assertEqual(json.loads(self.s.row('activities',self.f.activity)['budget_json'])['contract'],'TL-ACTIVITY-BUDGET-1')


class ProtectedFeatureOffAuditTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_propagation import ControllerMaintenanceIntegrationTests
        self.f=ControllerMaintenanceIntegrationTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
        self.s.db.execute('PRAGMA user_version=4')
    def test_featureoff_keeps_real_f1_barrier_and_qualified_stopped_audit(self):
        from digital_life.application.learning.runtime import qualified_plane_required,strict_feature_enabled
        from digital_life.application.learning.controller_read import ControllerMaterialReader
        from digital_life.application.services import Memory
        from digital_life.application.learning.eligibility import ref
        self.assertTrue(qualified_plane_required(self.s));self.assertFalse(strict_feature_enabled(self.s))
        before=self.s.db.total_changes;config=self.s.rows('configuration_versions')[0]
        reader=ControllerMaterialReader(self.s,self.f.token)
        with reader.boundary():allowed=reader.material(ref(self.s,config['id']),config['artifact_ref'],config['hash'])
        self.assertIsInstance(allowed['value'],dict);self.assertEqual(self.s.db.total_changes,before)
        with reader.boundary():
            with self.assertRaisesRegex(Forbidden,'audit source barrier'):reader.material(ref(self.s,self.f.signal['id']),self.f.signal['artifact_id'])
        with self.assertRaises(Forbidden):Memory(self.s).retrieve('previous source',self.f.f.work['learning_activity_id'],self.s.rows('context_snapshots')[0]['id'])
        self.assertEqual(self.s.row('tl_barrier',self.f.barrier['id'])['state'],'active');self.assertTrue((self.s.root/'WAKE_DISABLED').exists())


    def test_real_schema3_f1_cannot_start_unqualified_old_release(self):
        self.s.db.execute('PRAGMA user_version=3');extra=tempfile.TemporaryDirectory();self.addCleanup(extra.cleanup);source=Path(extra.name)/'legacy-source';(source/'digital_life/resources').mkdir(parents=True)
        (source/'digital_life/__init__.py').write_text('VERSION=3\n');(source/'digital_life/resources/release.json').write_text('{"schema_min":2,"schema_max":3}')
        control=Control(self.s.root,self.s.instance_id)
        try:
            releases=Releases(control);deployment=releases.stage(source);self.assertFalse(releases.compatible(deployment));self.assertFalse(releases.activate(deployment,lambda _:self.fail('old code must not launch'))['switched'])
            self.assertEqual(self.s.row('tl_barrier',self.f.barrier['id'])['state'],'active')
        finally:control.close()


class MechanicalProcess:
    def __init__(self,deployment,pid):self.deployment=deployment;self.pid=pid;self.stopped=False
    def poll(self):return -15 if self.stopped else None


class InjectedBridgeDriver:
    """Deterministic failure injection; never presented as an actual process."""
    def __init__(self,control,fail_stage=None,fail_deployment=None):self.c=control;self.fail_stage=fail_stage;self.fail_deployment=fail_deployment;self.processes=[];self.ready={}
    def handshake(self,deployment,pid,state):
        release=self.c.db.execute('SELECT * FROM deployments WHERE id=?',(deployment,)).fetchone();path=Releases(self.c).verify(deployment);manifest=json.loads((path/'manifest.json').read_text())
        return {'state':state,'deployment':deployment,'pid':pid,'schema_compatible':True,'capability':{'instance_id':self.c.instance,'schema_version':4,'build_hash':release['build_hash'],'bridge_contract':CAPABILITY['contract'],'manifest_digest':sha(dumps(manifest)),'engineering_version':'0.5.0','qualified_plane_required':True},'model_readiness':'unverified','model_access_verified':False,'inference_ready':'unknown'}
    def launch(self,path,root,deployment,ready,gate):
        process=MechanicalProcess(deployment,3000+len(self.processes));self.processes.append(process);self.ready[process.pid]=ready;return process
    def await_state(self,process,ready,desired,timeout):
        if process.deployment==self.fail_deployment and desired==self.fail_stage:raise ContractError('synthetic '+desired+' failure')
        value=self.handshake(process.deployment,process.pid,desired);ready.write_text(dumps(value));return value
    def stop(self,process):process.stopped=True
    def confirm_stability(self,*args):pass


class FailureAndRollbackTests(BridgeFixture):
    def setup_pair(self):
        old=self.stage();driver=InjectedBridgeDriver(self.c)
        self.releases.activate(old,lambda _: {'ready':True,'schema_compatible':True,'handshake':driver.handshake(old,2000,'prepared')})
        new=self.stage();self.unlock();driver.fail_deployment=new;return old,new,driver
    def test_prepare_failure_can_only_restart_verified_schema4_bridge(self):
        old,new,driver=self.setup_pair();driver.fail_stage='prepared';before=sha((self.root/'runtime.sqlite').read_bytes())
        manager=Deployment(self.c,driver);result=manager.launch(new)
        self.assertFalse(result['switched']);self.assertTrue(result['restarted']);self.assertEqual(manager.active['deployment'],old)
        self.assertEqual(sha((self.root/'runtime.sqlite').read_bytes()),before);self.assertTrue(driver.processes[0].stopped)
    def test_running_failure_rolls_code_only_and_never_changes_current_database(self):
        old,new,driver=self.setup_pair();driver.fail_stage='running';before=sha((self.root/'runtime.sqlite').read_bytes());manager=Deployment(self.c,driver)
        result=manager.launch(new);self.assertTrue(result['restarted']);self.assertEqual(manager.active['deployment'],old);self.assertEqual(sha((self.root/'runtime.sqlite').read_bytes()),before)
        self.assertEqual(self.c.db.execute('SELECT state FROM deployments WHERE id=?',(new,)).fetchone()[0],'failed')
    def test_heartbeat_wrong_capability_or_missing_file_fails_closed(self):
        deployment=self.stage();self.unlock();driver=InjectedBridgeDriver(self.c);manager=Deployment(self.c,driver);self.assertTrue(manager.launch(deployment)['switched'])
        path=manager.active['ready'];value=json.loads(path.read_text());value['capability']['build_hash']='0'*64;path.write_text(dumps(value))
        result=manager.check();self.assertEqual(result['state'],'failed');self.assertFalse(result['restarted']);self.assertTrue(driver.processes[0].stopped)
    def test_heartbeat_timeout_never_restarts_after_user_stop(self):
        deployment=self.stage();self.unlock();driver=InjectedBridgeDriver(self.c);manager=Deployment(self.c,driver);manager.launch(deployment)
        path=manager.active['ready'];os.utime(path,(time.time()-1000,time.time()-1000));self.c.stop('synthetic stop before heartbeat fallback')
        result=manager.check(heartbeat_timeout=1);self.assertEqual(result['state'],'user_stopped');self.assertFalse(result['rollback']);self.assertEqual(len(driver.processes),1)
    def test_restore_lock_blocks_before_any_process_launch(self):
        deployment=self.stage();self.unlock();(self.root/'RESTORE_RECONCILIATION_REQUIRED').write_text('synthetic current exclusion/identity reconciliation still required')
        driver=InjectedBridgeDriver(self.c)
        with self.assertRaises(Forbidden):Deployment(self.c,driver).launch(deployment)
        self.assertFalse(driver.processes)


class BridgeProtocolTests(BridgeFixture):
    def test_actual_protective_ddl_cannot_be_replaced_by_schema_integer(self):
        from digital_life.application.learning.bridge import verify_schema4_layout
        self.assertIsInstance(verify_schema4_layout(self.s.db),str)
        self.s.db.execute('DROP TRIGGER tl_barrier_update_guard')
        with self.assertRaises(Forbidden):verify_schema4_layout(self.s.db)
        deployment=self.stage();self.assertFalse(self.releases.compatible(deployment))
        self.assertFalse(self.releases.activate(deployment,lambda _:self.fail('invalid protective DDL cannot launch'))['switched'])
    def test_partial_TL_layout_is_not_a_legacy_downgrade_permission(self):
        from digital_life.application.learning.runtime import qualified_plane_required
        self.s.db.execute('PRAGMA user_version=3');self.s.db.execute('DROP TABLE tl_effect')
        with self.assertRaises(Forbidden):qualified_plane_required(self.s)
    def test_unknown_schema_never_uses_legacy_fallback(self):
        from digital_life.application.learning.runtime import qualified_plane_required
        self.s.db.execute('PRAGMA user_version=5')
        with self.assertRaises(Forbidden):qualified_plane_required(self.s)
    def test_bad_types_duplicate_json_and_oversized_readiness_rejected(self):
        from digital_life.application.learning.bridge import declaration,read_readiness
        bad={'schema_min':2,'schema_max':4,'engineering_version':'0.5.0','tool_learning_bridge':dict(CAPABILITY,new_learning_default=0),'capabilities':['TL-LOOP-0.1']}
        with self.assertRaises(Forbidden):declaration(bad)
        path=Path(self.tmp.name)/'readiness.json'
        for value in ('{"state":"prepared","state":"running"}','{"state":NaN}','[]','x'*65537):
            path.write_text(value)
            with self.assertRaises((ContractError,ValueError)):read_readiness(path)
    def test_heartbeat_missing_and_expired_are_actual_stop_conditions(self):
        deployment=self.stage();self.unlock();driver=InjectedBridgeDriver(self.c);manager=Deployment(self.c,driver);manager.launch(deployment);manager.active['ready'].unlink()
        result=manager.check();self.assertEqual(result['state'],'failed');self.assertTrue(driver.processes[0].stopped)
        # A distinct explicit controller launch, not an automatic retry.
        newer=self.stage();driver=InjectedBridgeDriver(self.c);manager=Deployment(self.c,driver);manager.launch(newer)
        os.utime(manager.active['ready'],(time.time()-1000,time.time()-1000));self.assertEqual(manager.check(heartbeat_timeout=1)['state'],'failed');self.assertTrue(driver.processes[0].stopped)


class SourceCapabilityNarrowingTests(BridgeFixture):
    def source_proposal(self):
        from digital_life.application.lifecycle.source_updates import SourceUpdates
        from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
        actor=self.s.config()['controller'];SelfMaintenance(self.s).configure(True,actor);old=self.stage();driver=InjectedBridgeDriver(self.c)
        verifier={'ready':True,'schema_compatible':True}
        if self.s.db.execute('PRAGMA user_version').fetchone()[0]==4:verifier['handshake']=driver.handshake(old,3001,'prepared')
        self.assertTrue(self.releases.activate(old,lambda _:verifier)['switched'])
        updates=SourceUpdates(self.s);proposal=updates.propose(old,{'digital_life/im15_isolated_marker.py':'SYNTHETIC_MARKER=True\n'},'isolated compatibility check',identifier(),actor)
        return updates,proposal,actor
    def test_unprotected_old_schema_source_update_is_explicitly_narrowed(self):
        self.s.db.execute('PRAGMA user_version=3');updates,proposal,actor=self.source_proposal();built=updates.build(proposal['id'],actor)
        row=self.c.db.execute('SELECT * FROM deployments WHERE id=?',(built['deployment'],)).fetchone();self.assertEqual(row['schema_max'],3)
        description=json.loads((self.releases.verify(row['id'])/'digital_life/resources/release.json').read_text());self.assertNotIn('tool_learning_bridge',description)
        audit=updates.events('capability_narrowed');self.assertEqual(len(audit),1);self.assertEqual((audit[0]['from_max'],audit[0]['to_max']),(4,3))
    def test_schema4_changed_source_cannot_inherit_reviewed_bridge(self):
        updates,proposal,actor=self.source_proposal()
        with self.assertRaisesRegex(Forbidden,'reviewed executable source baseline'):updates.build(proposal['id'],actor)
        self.assertFalse(updates.events('capability_narrowed'));self.assertFalse(updates.events('built'))
