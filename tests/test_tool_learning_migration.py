"""IM16: newly-created synthetic namespaces only, without models or waking."""
from pathlib import Path
import tempfile
import unittest
from digital_life.application.learning.migration import IsolatedMigrationTarget,migrate_isolated,rollback_code_isolated,restore_old_migration_database
from digital_life.domain.contracts import Forbidden,Conflict,ContractError
from digital_life.application.learning.bridge import declaration,CAPABILITY
from copy import deepcopy
from digital_life.application.lifecycle.control_plane import Releases
from digital_life.infrastructure.persistence.sqlite_store import PROJECT

class MigrationTests(unittest.TestCase):
    def test_real_schema2_to4(self):
        with tempfile.TemporaryDirectory() as temporary:
            with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new') as target:
                s=target.store
                self.assertEqual(s.db.execute('PRAGMA user_version').fetchone()[0],2)
                self.assertFalse(s.db.execute("SELECT 1 FROM sqlite_master WHERE name='tl_work'").fetchone())
                identity=s.instance_id
                release=Releases(target.control).stage(PROJECT)
                bearer='Bearer '+(s.root/'controller.token').read_text()
                result=migrate_isolated(target,bearer,release,release)
                self.assertEqual(result['version'],4)
                self.assertEqual(s.instance_id,identity)
                self.assertTrue((s.root/'WAKE_DISABLED').exists())
                self.assertEqual(s.integrity(),{'integrity':'ok','foreign_keys':[]})
                self.assertTrue(result['backup']['complete'])

    def test_real_schema3_and_semantic_history_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new',3) as target:
                s=target.store
                self.assertTrue(s.db.execute("SELECT 1 FROM sqlite_master WHERE name='module_checkpoints'").fetchone())
                old=s.event('synthetic.history',payload={'identity':'liwei','value':False,'zero':0,'null':None,'legacy_shadow':'not accepted'},source='synthetic',lane='control')
                before=dict(s.row('runtime_events',old));release=Releases(target.control).stage(PROJECT)
                bearer='Bearer '+(s.root/'controller.token').read_text()
                result=migrate_isolated(target,bearer,release,release)
                self.assertEqual(s.row('runtime_events',old),before)
                self.assertEqual(s.db.execute('SELECT count(*) FROM tl_content').fetchone()[0],0)
                self.assertEqual(result['source_version'],3)
                again=migrate_isolated(target,bearer,release,release)
                self.assertTrue(again['already_applied'])
                self.assertFalse(rollback_code_isolated(target,bearer,release)['database_rewound'])
                with self.assertRaises(Forbidden):restore_old_migration_database(target,bearer,result['backup']['registration_id'])
                self.assertEqual(s.row('runtime_events',old),before)

    def test_identity_memory_promise_approval_and_original_accounts_are_preserved(self):
        from evaluation.tool_learning_fixture import SyntheticToolLearningFixture
        from digital_life.domain.contracts import dumps,sha
        for version in (2,3):
            with self.subTest(version=version),tempfile.TemporaryDirectory() as temporary:
                with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new',version) as target:
                    fixture=object.__new__(SyntheticToolLearningFixture)
                    fixture.store=target.store;fixture.control=target.control;fixture.closed=False;fixture.schema_version=version
                    fixture._seed();fixture.verify_seed()
                    accounts=sha(dumps(target.store.rows('activity_budget_accounts')))
                    release=Releases(target.control).stage(PROJECT)
                    migrate_isolated(target,'Bearer '+(target.store.root/'controller.token').read_text(),release,release)
                    fixture.schema_version=4;fixture.verify_seed()
                    self.assertEqual(sha(dumps(target.store.rows('activity_budget_accounts'))),accounts)
                    self.assertFalse(target.store.rows('tl_content'))

    def test_ack_failure_is_durable_not_a_database_rewind(self):
        with tempfile.TemporaryDirectory() as temporary:
            with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new') as target:
                release=Releases(target.control).stage(PROJECT);bearer='Bearer '+(target.store.root/'controller.token').read_text()
                def fault(point):
                    if point=='after_commit':raise RuntimeError('synthetic lost acknowledgement')
                with self.assertRaisesRegex(RuntimeError,'lost acknowledgement'):migrate_isolated(target,bearer,release,release,fault=fault)
                self.assertEqual(target.store.db.execute('PRAGMA user_version').fetchone()[0],4)
                count=target.control.db.execute('SELECT count(*) FROM backup_manifests').fetchone()[0]
                self.assertTrue(migrate_isolated(target,bearer,release,release)['already_applied'])
                self.assertEqual(target.control.db.execute('SELECT count(*) FROM backup_manifests').fetchone()[0],count)

    def test_each_transaction_failure_rolls_back_real_schema2(self):
        for point in ('v3_statement_0','tl_statement_0','ddl_complete','policy_default_off','version_recorded','before_commit'):
            with self.subTest(point=point),tempfile.TemporaryDirectory() as temporary:
                with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new') as target:
                    s=target.store;release=Releases(target.control).stage(PROJECT)
                    bearer='Bearer '+(s.root/'controller.token').read_text()
                    def fault(at):
                        if at==point:raise RuntimeError('synthetic write fault '+point)
                    with self.assertRaisesRegex(RuntimeError,'synthetic write fault'):migrate_isolated(target,bearer,release,release,fault=fault)
                    self.assertEqual(s.db.execute('PRAGMA user_version').fetchone()[0],2)
                    self.assertFalse(s.db.execute("SELECT 1 FROM sqlite_master WHERE name IN ('module_checkpoints','tl_work')").fetchone())
                    self.assertEqual(s.integrity(),{'integrity':'ok','foreign_keys':[]})
                    self.assertTrue(target.control.db.execute('SELECT 1 FROM backup_manifests').fetchone())
                    self.assertEqual(target.control.db.execute("SELECT state FROM control_commands WHERE kind='migration.isolated'").fetchone()[0],'failed')

    def test_existing_target_and_wrong_bearer_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()/'new'
            with IsolatedMigrationTarget.create(root) as target:
                with self.assertRaises(Forbidden):IsolatedMigrationTarget.create(root)
                with self.assertRaises(Forbidden):migrate_isolated(target,'Bearer fake','fake','fake')
                with self.assertRaises(Forbidden):migrate_isolated(target.store,'Bearer fake','fake','fake')
                self.assertEqual(target.store.db.execute('PRAGMA user_version').fetchone()[0],2)

    def test_migrated_idle_real_runtime_heartbeat_and_user_stop(self):
        import time
        from digital_life.application.lifecycle.deployment import Deployment
        with tempfile.TemporaryDirectory() as temporary:
            with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new') as target:
                release=Releases(target.control).stage(PROJECT);bearer='Bearer '+(target.store.root/'controller.token').read_text()
                migrate_isolated(target,bearer,release,release)
                (target.store.root/'WAKE_DISABLED').unlink();target.control.resume('im16 synthetic idle launch')
                manager=Deployment(target.control)
                try:
                    response=manager.launch(release)
                    self.assertTrue(response['switched'])
                    self.assertEqual(manager.check()['state'],'running')
                    self.assertFalse(target.store.rows('thought_requests'))
                    target.control.stop('im16 actual user stop')
                    self.assertEqual(manager.check()['state'],'user_stopped')
                    self.assertFalse(target.store.rows('thought_attempts'))
                finally:
                    if manager.active:manager.driver.stop(manager.active['process'])
                    (target.store.root/'WAKE_DISABLED').write_text('synthetic relock')

    def test_failed_replacement_restarts_verified_bridge_without_rewinding_database(self):
        from tests.test_tool_learning_bridge import InjectedBridgeDriver
        from digital_life.application.lifecycle.deployment import Deployment
        from digital_life.domain.contracts import sha
        with tempfile.TemporaryDirectory() as temporary:
            with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new') as target:
                releases=Releases(target.control);old=releases.stage(PROJECT);new=releases.stage(PROJECT)
                migrate_isolated(target,'Bearer '+(target.store.root/'controller.token').read_text(),old,old)
                driver=InjectedBridgeDriver(target.control,fail_stage='running',fail_deployment=new)
                releases.activate(old,lambda _: {'ready':True,'schema_compatible':True,'handshake':driver.handshake(old,2000,'prepared')})
                target.store.event('im16.post_migration_history',payload={'retained':True},lane='control')
                before=sha((target.store.root/'runtime.sqlite').read_bytes())
                (target.store.root/'WAKE_DISABLED').unlink();target.control.resume('synthetic rollback')
                manager=Deployment(target.control,driver)
                try:
                    response=manager.launch(new)
                    self.assertTrue(response['restarted']);self.assertEqual(manager.active['deployment'],old)
                    self.assertEqual(sha((target.store.root/'runtime.sqlite').read_bytes()),before)
                    self.assertEqual(target.store.db.execute('PRAGMA user_version').fetchone()[0],4)
                finally:
                    if manager.active:driver.stop(manager.active['process'])
                    target.control.stop('synthetic rollback cleanup');(target.store.root/'WAKE_DISABLED').write_text('synthetic relock')

    def test_native_c1_c2_history_survives_qualified_code_selection_and_old_backup_refusal(self):
        import json
        from digital_life.domain.contracts import utc,identifier,sha,dumps
        from digital_life.application.runtime.configuration import configure_model
        from digital_life.application.learning.engine import StrictEngine
        from digital_life.application.learning.runtime_learning import StrictLearningCoordinator
        from digital_life.application.runtime.engine import Engine
        from tests.test_tool_learning_runtime import StrictLearningFlowTests
        with tempfile.TemporaryDirectory() as temporary:
            with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new') as target:
                s=target.store;c=target.control;release=Releases(c).stage(PROJECT);bearer='Bearer '+(s.root/'controller.token').read_text()
                migrated=migrate_isolated(target,bearer,release,release)
                caps={'max_input_tokens':200000,'max_output_tokens':200,'max_attempts':8,'max_tool_calls':8,'max_scan':2000000,'max_items':2000000,'max_bytes':512*1024*1024,'elapsed_ms':600000}
                policy=s.insert('policy_versions',version=101,mode='authorization',scope={'tool_learning_runtime':{'contract':'TL-STRICT-RUNTIME-1','enabled':True,'ordinary_activity_caps':caps},'tool_learning_acceptance':{'contract':'TL-ACCEPT-REVIEW-1','content_kinds':['source_report'],'proposal_operations':['add'],'require_controller_review':True,'expires_at':utc(3600)}},effective_at=utc(),authority=s.config()['controller'])
                s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE instance_id=?',(policy,s.instance_id))
                configure_model(s,{'backend':'remote_chat','model':'synthetic-fixed','base_url':'https://synthetic.invalid','enabled':True,'context_window':262144,'max_output_tokens':200},s.config()['controller'],check_available=False)
                (s.root/'controller.token').write_text('synthetic-isolated-controller-token')
                from tests.test_tool_learning_bridge import InjectedBridgeDriver
                driver=InjectedBridgeDriver(c)
                Releases(c).activate(release,lambda _: {'ready':True,'schema_compatible':True,'handshake':driver.handshake(release,2000,'prepared')})
                (s.root/'WAKE_DISABLED').unlink();c.resume('synthetic native history');identity=c.begin_run(release)
                try:
                    key=identifier();c.accept_inbound('strict-fixture-controller',key,{'text':'你好，我是liwei'},s.config()['controller'])
                    activity=Engine(s,identity).submit('你好，我是liwei',key,'strict-fixture-controller')
                    kernel=StrictEngine(s,identity);flow=StrictLearningFlowTests();flow.s=s;flow.activity=activity;flow.r=StrictLearningCoordinator(kernel)
                    work,proposal=flow.observe(interpret=False);review=flow.review(proposal)
                    decision=flow.r.decide(proposal['id'],review)
                    self.assertEqual(s.row('tl_decision',decision['result_refs'][0]['id'])['operation'],'accept')
                    handoff=s.db.execute('SELECT id FROM tl_handoff WHERE work_id=?',(work['id'],)).fetchone()[0]
                    flow.r.publish(handoff)
                    self.assertEqual(s.row('tl_handoff',handoff)['state'],'published')
                    from digital_life.application.learning.invalidation import ToolLearningInvalidation
                    from tests.test_tool_learning_invalidation import MechanicalInvalidation
                    from digital_life.application.learning.eligibility import ref,slot
                    from tests.test_tool_learning_products import envelope
                    conditions=s.read_artifact(s.row('tl_work',work['id'])['conditions_artifact_id'])
                    source=conditions['source'];scope=s.read_artifact(proposal['payload_artifact_id'])['body']['claims'][0]['scope']
                    payload={'change_id':identifier(),'kind':'revoke','source':{'object':source['source'],'revision':0,'epoch':0},'replacement':slot(),'affected_scope':scope,'subjects':[],'purposes':['learn'],'expected_epoch':0,'evidence':[source],'erase_scope':slot()}
                    entry,principal=kernel.owners.entry('M12','propagate',s.config()['controller'])
                    budget=json.loads(s.row('activities',s.row('tl_work',work['id'])['learning_activity_id'])['budget_json'])['budget']
                    request=envelope(payload);request.update(instance_id=s.instance_id,command_id=identifier(),idempotency_key=identifier(),principal=principal,work_ref=slot(ref(s,work['id'])),budget=budget,control=kernel._control(activity,None,[]))
                    ToolLearningInvalidation(s,MechanicalInvalidation()).apply('mechanical-im06',request)
                    self.assertEqual(len(s.rows('tl_barrier')),1)
                    tables=('tl_work','tl_product','tl_decision','tl_content','tl_content_revision','tl_handoff','tl_representation','tl_change','tl_barrier','tl_source_epoch','tl_propagation','activity_budget_accounts')
                    before={name:sha(dumps(s.rows(name))) for name in tables}
                finally:c.finish_run(identity);c.stop('synthetic native history stopped');(s.root/'WAKE_DISABLED').write_text('synthetic relock')
                bearer='Bearer synthetic-isolated-controller-token'
                rollback_code_isolated(target,bearer,release)
                with self.assertRaises(Forbidden):restore_old_migration_database(target,bearer,migrated['backup']['registration_id'])
                self.assertEqual({name:sha(dumps(s.rows(name))) for name in tables},before)
                self.assertFalse(s.rows('thought_attempts'))

    def test_historical_missing_array_needs_preexisting_exact_control_proof(self):
        import json
        from digital_life.domain.contracts import dumps,sha
        from digital_life.application.learning.bridge import source_files,register_baseline,effective_capabilities,CONTRACT
        with tempfile.TemporaryDirectory() as temporary:
            with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new') as target:
                # Synthetic reconstruction of the already-registered IM15 format.
                # This is explicit trusted historical Control fixture creation,
                # not the public candidate enrollment path.
                files={str(path):raw for path,raw in source_files(PROJECT)}
                description=json.loads(files['digital_life/resources/release.json']);description.pop('capabilities')
                files['digital_life/resources/release.json']=dumps(description).encode()
                manifest={path:sha(raw) for path,raw in files.items()};checksum=sha(dumps(manifest));directory=target.store.root/'releases'/checksum
                directory.mkdir(parents=True)
                for name,raw in files.items():
                    path=directory/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                (directory/'manifest.json').write_text(dumps(manifest))
                deployment=target.control.insert('deployments',release=checksum,build_hash=checksum,schema_min=2,schema_max=4,state='candidate')
                with self.assertRaises(Forbidden):effective_capabilities(target.control,deployment)
                # The normal NEW stage cannot mint that missing-array proof.
                with self.assertRaises(Forbidden):Releases(target.control).stage(directory)
                proof={'contract':CONTRACT,'manifest_digest':sha(dumps(manifest)),'capability':deepcopy(CAPABILITY),'engineering_version':description['engineering_version'],'schema_min':2,'schema_max':4}
                register_baseline(target.control,checksum,proof)
                original=(directory/'digital_life/resources/release.json').read_bytes()
                result=effective_capabilities(target.control,deployment)
                self.assertEqual(result['basis'],'verified_im15_nested_projection')
                self.assertEqual((directory/'digital_life/resources/release.json').read_bytes(),original)
                (directory/'digital_life/resources/release.json').write_text(dumps(dict(description,engineering_version='tampered')))
                with self.assertRaisesRegex(ContractError,'release integrity failure'):effective_capabilities(target.control,deployment)

    def test_fake_schema3_integer_without_historical_expansion_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new') as target:
                release=Releases(target.control).stage(PROJECT);target.store.db.execute('PRAGMA user_version=3')
                with self.assertRaises(Conflict):migrate_isolated(target,'Bearer '+(target.store.root/'controller.token').read_text(),release,release)
                self.assertFalse(target.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='tl_work'").fetchone())

    def test_stop_lock_marker_and_actual_schema3_layout_are_required(self):
        from digital_life.application.learning.migration import MARKER
        for corruption in ('marker','wake_lock','v3_index'):
            with self.subTest(corruption=corruption),tempfile.TemporaryDirectory() as temporary:
                with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new',3) as target:
                    release=Releases(target.control).stage(PROJECT);bearer='Bearer '+(target.store.root/'controller.token').read_text()
                    original=(target.store.root/MARKER).read_text()
                    try:
                        if corruption=='marker':(target.store.root/MARKER).write_text('{}')
                        elif corruption=='wake_lock':(target.store.root/'WAKE_DISABLED').unlink()
                        else:target.store.db.execute('DROP INDEX ix_metrics_by_run')
                        with self.assertRaises((Forbidden,Conflict)):migrate_isolated(target,bearer,release,release)
                        self.assertEqual(target.store.db.execute('PRAGMA user_version').fetchone()[0],3)
                        self.assertFalse(target.control.db.execute("SELECT 1 FROM control_commands WHERE kind='migration.isolated'").fetchone())
                    finally:
                        (target.store.root/MARKER).write_text(original);(target.store.root/'WAKE_DISABLED').write_text('synthetic relock')

    def test_unqualified_rollback_bridge_refused_before_backup(self):
        from tests.test_tool_learning_bridge import BridgeFixture
        with tempfile.TemporaryDirectory() as temporary:
            with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new') as target:
                release=Releases(target.control).stage(PROJECT)
                source=Path(temporary)/'old-source';(source/'digital_life/resources').mkdir(parents=True)
                (source/'digital_life/__init__.py').write_text("__version__='0.5.0'\n")
                (source/'digital_life/resources/release.json').write_text('{"engineering_version":"0.5.0","schema_min":2,"schema_max":3}')
                legacy=Releases(target.control).stage(source)
                with self.assertRaises(Forbidden):migrate_isolated(target,'Bearer '+(target.store.root/'controller.token').read_text(),release,legacy)
                self.assertFalse(target.control.db.execute('SELECT 1 FROM backup_manifests').fetchone())
                self.assertEqual(target.store.db.execute('PRAGMA user_version').fetchone()[0],2)

    def test_missing_source_blob_fails_backup_and_journals_owned_paths(self):
        import json
        with tempfile.TemporaryDirectory() as temporary:
            with IsolatedMigrationTarget.create(Path(temporary).resolve()/'new') as target:
                artifact=target.store.artifact({'synthetic':'independent source not control config'})
                row=target.store.row('artifacts',artifact);(target.store.root/'blobs'/row['storage_ref']).unlink()
                release=Releases(target.control).stage(PROJECT)
                with self.assertRaises(FileNotFoundError):migrate_isolated(target,'Bearer '+(target.store.root/'controller.token').read_text(),release,release)
                command=target.control.db.execute("SELECT * FROM control_commands WHERE kind='migration.isolated'").fetchone()
                self.assertEqual(command['state'],'failed')
                self.assertEqual(len(json.loads(command['payload'])['backup_paths']),2)
                self.assertEqual(target.store.db.execute('PRAGMA user_version').fetchone()[0],2)
                self.assertFalse(target.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='tl_work'").fetchone())

    def test_capability_array_is_exact_not_truthy(self):
        description={'engineering_version':'0.5.0','schema_min':2,'schema_max':4,'tool_learning_bridge':deepcopy(CAPABILITY),'capabilities':['TL-LOOP-0.1']}
        declaration(description)
        for value in (True,False,None,[],['unknown'],['TL-LOOP-0.1','TL-LOOP-0.1'],['TL-LOOP-0.1',True]):
            with self.subTest(value=value):
                bad=deepcopy(description);bad['capabilities']=value
                with self.assertRaises((Forbidden,ValueError)):declaration(bad)

if __name__=='__main__':unittest.main()
