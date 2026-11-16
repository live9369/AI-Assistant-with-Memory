"""Actual local dependency/input registration, isolated stores and no models."""
from contextlib import nullcontext,contextmanager
from copy import deepcopy
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid
from digital_life.application.learning.engine import StrictEngine,source_scope,_dependency
from digital_life.application.learning.eligibility import ref,insert
from digital_life.domain import contracts
from digital_life.domain.contracts import Conflict,ContractError,Forbidden
from digital_life.infrastructure.persistence.sqlite_store import Store,managed_database
from digital_life.infrastructure.persistence.tool_learning_meter import (PhysicalReadMeter,cached_artifact,remember_artifact,cached_metadata)
from digital_life.infrastructure.persistence.tool_learning_readset import current_readset,facts,PhaseReadSet
from digital_life.infrastructure.persistence.sqlite_write_monitor import callback_active
from tests import test_tool_learning_runtime as fixture


class CertifiedInputTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.StrictEngineEndToEndTests();self.f.enable_features=False;self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.e=self.f.strict;self.scope=source_scope(self.s)
        self.entry,self.principal=self.e.owners.entry('M14','learn')
        self.context=self.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(self.f.activity,)).fetchone()[0]
        with self.s.tx():
            self.consumer=ref(self.s,self.s.insert('memory_retrieval_runs',activity_id=self.f.activity,context_id=self.context,query='synthetic registration consumer',retriever_version='synthetic-certificate'))
            nodes=[ref(self.s,self.s.artifact({'synthetic graph source':index}))for index in range(4)]
            for index,(left,right,relation)in enumerate(((0,1,'read'),(0,2,'read'),(0,1,'delete'),(1,3,'read'),(2,3,'read'),(3,0,'delete'))):
                _dependency(self.s,nodes[left],{'object':nodes[right],'revision':0,'epoch':0},self.scope,relation,'/source/'+str(index),'learn')
        self.token={'object':nodes[0],'revision':0,'epoch':0}
        self.dep={'target':self.token['object'],'expected':self.token,'relation':'read','consumer_purpose':'learn'}
    def meter(self):return PhysicalReadMeter(self.e._read_slice(self.f.activity,.5),self.s.row('activities',self.f.activity)['deadline'])
    def register(self,path='/field',digest=None):
        key=self.e.runtime.eligibility.register_dependency(self.entry,self.principal,self.consumer,self.dep,path,self.scope)
        value=self.e.runtime.eligibility.register_input(self.entry,self.principal,self.consumer,key,digest)
        return key,value
    def test_query_only_roundtrip_invalidates_configuration_without_ending_schema_approval(self):
        managed=managed_database(self.s.db)
        with self.meter().installed(self.s),self.e.owners.source.verification_boundary():self.register('/before-query-only')
        before=managed.monitor_state();version=self.s.db.execute('PRAGMA schema_version').fetchone()[0]
        self.s.db.execute('PRAGMA query_only=ON')
        self.s.db.execute('BEGIN');self.s.db.execute('SELECT count(*) FROM tl_input_dependency').fetchone();self.s.db.execute('COMMIT')
        self.s.db.execute('PRAGMA query_only=0')
        after=managed.monitor_state()
        self.assertEqual(after['schema_epoch'],before['schema_epoch']);self.assertGreater(after['configuration'],before['configuration'])
        self.assertEqual(self.s.db.execute('PRAGMA schema_version').fetchone()[0],version)
        with self.meter().installed(self.s),self.e.owners.source.verification_boundary():self.register('/after-query-only')
        self.assertEqual(self.s._input_certificate_stats,dict(attempted=2,issued=2,accepted=2,fallback=0,committed=2,strong_material_accepted=2,strong_material_committed=2))
    def test_controller_chat_and_real_execution_recall_keep_next_registration_certified(self):
        from digital_life.application.learning.controller_read import ControllerMaterialReader
        managed=managed_database(self.s.db)
        (self.s.root/'controller.token').write_text('synthetic-query-only-controller')
        reader=ControllerMaterialReader(self.s,'Bearer synthetic-query-only-controller')
        with self.meter().installed(self.s),self.e.owners.source.verification_boundary():self.register('/before-controller-recall')
        epoch=managed.monitor_state()['schema_epoch']
        with patch.object(self.e.provider,'generate_fresh',side_effect=AssertionError('recall cannot call a model')):
            self.assertEqual(reader.chat('query-only-certificate')['messages'],[])
            result=self.e._recall(self.f.activity,self.context,'synthetic empty execution recall',self.token,self.scope)
        self.assertIn('items',result);self.assertEqual(managed.monitor_state()['schema_epoch'],epoch)
        with self.meter().installed(self.s),self.e.owners.source.verification_boundary():self.register('/after-controller-recall')
        self.assertEqual(self.s._input_certificate_stats,dict(attempted=2,issued=2,accepted=2,fallback=0,committed=2,strong_material_accepted=2,strong_material_committed=2))
    def test_real_registration_same_library_native_legacy_and_certified_are_exact(self):
        self._compare_registration(4)
    def test_deep_shared_graph_eight_fields_keeps_registration_and_permissions_exact(self):
        with self.s.tx():
            nodes=[ref(self.s,self.s.artifact({'synthetic deep graph source':index}))for index in range(12)]
            edges=[(self.token['object'],nodes[0],'read'),(self.token['object'],nodes[1],'read')]
            for level in range(5):
                for left in nodes[level*2:level*2+2]:
                    for right in nodes[level*2+2:level*2+4]:edges.append((left,right,'read'))
            edges.extend((left,self.token['object'],'delete')for left in nodes[-2:])
            for index,(left,right,relation)in enumerate(edges):
                _dependency(self.s,left,{'object':right,'revision':0,'epoch':0},self.scope,relation,'/deep-source/'+str(index),'learn')
        self._compare_registration(8)
    def test_original_permission_methods_keep_fast_file_lease_and_registration_exact(self):
        self._compare_registration(4,preserve_methods=True)
    def _compare_registration(self,field_count,preserve_methods=False):
        original_time=datetime.datetime;instant=original_time.now(datetime.timezone.utc);instant=instant.replace(microsecond=instant.microsecond//1000*1000)
        fixed=instant.isoformat(timespec='milliseconds').replace('+00:00','Z')
        class FrozenDateTime(original_time):
            @classmethod
            def now(cls,tz=None):return instant.replace(tzinfo=None)if tz is None else instant.astimezone(tz)
        summaries=[]
        for mode in ('native_legacy','managed_legacy','certified_tables','certified'):
            with tempfile.TemporaryDirectory()as directory:
                root=Path(directory)
                for folder in ('blobs','workspace','snapshots'):shutil.copytree(self.s.root/folder,root/folder)
                for source,name in ((self.s.db,'runtime.sqlite'),(self.f.control.db,'control.sqlite')):
                    destination=sqlite3.connect(root/name)
                    try:source.backup(destination)
                    finally:destination.close()
                clone=Store(root);clock=sqlite3.connect(':memory:');sequence=[0]
                if mode=='native_legacy':
                    clone.db.close();clone.db=sqlite3.connect(root/'runtime.sqlite',isolation_level=None);clone.db.row_factory=sqlite3.Row;clone.db.execute('PRAGMA foreign_keys=ON')
                def strftime(*values):
                    values=list(values)
                    if len(values)>1 and values[1]=='now':values[1]=fixed
                    return clock.execute('SELECT strftime('+','.join('?'for _ in values)+')',values).fetchone()[0]
                clone.db.create_function('strftime',-1,strftime)
                def next_uuid():sequence[0]+=1;return uuid.UUID(int=2**120+sequence[0])
                try:
                    engine=StrictEngine(clone,self.f.identity,self.e.provider);permissions=[];versions=[];registrations=[]
                    material_stats=dict(graph_lookups=0,graph_hits=0,admission_requests=0,admission_hits=0)
                    original_graph=PhaseReadSet.graph;original_admitted=PhaseReadSet.graph_admitted
                    def graph(phase,key):
                        material_stats['graph_lookups']+=1;result=original_graph(phase,key)
                        material_stats['graph_hits']+=int(result is not None);return result
                    def admitted(phase,key):
                        material_stats['admission_requests']+=1;result=original_admitted(phase,key)
                        material_stats['admission_hits']+=int(result);return result
                    access=engine.owners.source_access;version=engine.owners.source.verify_version;registration=engine.owners.source.verify_registration
                    def source_access(*args):permissions.append(deepcopy(args));return access(*args)
                    def verify_version(*args):versions.append(deepcopy(args));return version(*args)
                    def verify_registration(*args):registrations.append(deepcopy(args));return registration(*args)
                    @contextmanager
                    def observed_permissions():
                        if not preserve_methods:
                            with patch.object(engine.owners,'source_access',source_access),patch.object(engine.owners.source,'verify_version',verify_version),patch.object(engine.owners.source,'verify_registration',verify_registration):yield
                            return
                        prior=sys.getprofile()
                        targets={access.__func__.__code__:(permissions,('entry','principal','origin','scope')),version.__func__.__code__:(versions,('entry','principal','token','stage')),registration.__func__.__code__:(registrations,('entry','principal','context','stage'))}
                        def profile(frame,event,arg):
                            if event=='call'and frame.f_code in targets:
                                output,names=targets[frame.f_code];output.append(deepcopy(tuple(frame.f_locals[name]for name in names)))
                        sys.setprofile(profile)
                        try:yield
                        finally:sys.setprofile(prior)
                    signature_hits=[0];signature_current=PhaseReadSet._tracked_signature_current
                    def tracked_signature(phase,path):
                        value=signature_current(phase,path);signature_hits[0]+=bool(value);return value
                    legacy=lambda fields:insert(clone,'tl_input_dependency',**fields)
                    with patch.object(contracts,'datetime',FrozenDateTime),patch.object(uuid,'uuid4',next_uuid):
                        entry,principal=engine.owners.entry('M14','learn')
                        alternate=(nullcontext()if mode=='certified'else patch.object(managed_database(clone.db),'insert_only_receipt',return_value=False))if mode.startswith('certified')else patch.object(clone,'_insert_input_registration',side_effect=legacy)
                        started=time.monotonic()
                        with alternate,patch.object(PhaseReadSet,'graph',new=graph),patch.object(PhaseReadSet,'graph_admitted',new=admitted),observed_permissions(),patch.object(PhaseReadSet,'_tracked_signature_current',new=tracked_signature),patch.object(engine.provider,'generate_fresh',side_effect=AssertionError('registration cannot call a model')):
                            with engine._read_operation(entry,self.f.activity,self.context,'synthetic-registration-probe',engine._read_slice(self.f.activity,.5))as meter,engine.owners.source.verification_boundary():
                                returned=[]
                                for index in range(field_count):
                                    path='/field/'+str(index);digest={'algorithm':'sha256','hex':hashlib.sha256(path.encode()).hexdigest()}
                                    dep=engine.runtime.eligibility.register_dependency(entry,principal,self.consumer,self.dep,path,self.scope)
                                    result=engine.runtime.eligibility.register_input(entry,principal,self.consumer,dep,digest);returned.append((dep,result))
                                repeated=engine.runtime.eligibility.register_input(entry,principal,self.consumer,returned[-1][0],digest)
                                self.assertEqual(repeated,returned[-1][1])
                                try:engine.runtime.eligibility.register_input(entry,principal,self.consumer,returned[-1][0],{'algorithm':'sha256','hex':'e'*64})
                                except ContractError as error:failure=(type(error).__name__,str(error))
                                else:self.fail('different digest accepted')
                        wall=time.monotonic()-started
                        inputs=[dict(v)for v in clone.db.execute('SELECT * FROM tl_input_dependency WHERE request_ref_id=? ORDER BY id',(self.consumer['id'],))]
                        deps=[dict(v)for v in clone.db.execute('SELECT * FROM tl_dependency WHERE consumer_ref_id=? ORDER BY id',(self.consumer['id'],))]
                        metadata=[engine.runtime.eligibility._metadata(v)for v in deps]
                        budget=json.loads(clone.row('activities',self.f.activity)['budget_json'])
                        summaries.append({'signature_hits':signature_hits[0],'mode':mode,'returned':returned,'inputs':inputs,'dependencies':deps,'metadata':metadata,'permission_uses':permissions,'version_uses':versions,'registration_uses':registrations,'uuid_calls':sequence[0],'caps':budget['budget'],'ledger':budget['ledger'],'failure':failure,'actual':dict(meter.actual),'stats':dict(clone._input_certificate_stats),'material_stats':material_stats,'wall_seconds':wall})
                finally:clone.close();clock.close()
        if preserve_methods:self.assertGreater(summaries[-1]['signature_hits'],0)
        keys=('returned','inputs','dependencies','metadata','permission_uses','version_uses','registration_uses','uuid_calls','caps','failure')
        differences=[item['mode']+':'+key for item in summaries[1:]for key in keys if item[key]!=summaries[0][key]]
        self.assertEqual(differences,[])
        self.assertEqual(summaries[-1]['stats']['issued'],field_count);self.assertEqual(summaries[-1]['stats']['accepted'],field_count);self.assertEqual(summaries[-1]['stats']['committed'],field_count)
        self.assertEqual(summaries[-1]['stats']['fallback'],0)
        for item in summaries:
            expected=field_count if item['mode']=='certified'else 0
            self.assertEqual(item['stats']['strong_material_accepted'],expected)
            self.assertEqual(item['stats']['strong_material_committed'],expected)
        self.assertLess(summaries[-1]['actual']['bytes'],summaries[1]['actual']['bytes'])
        self.assertLess(summaries[-1]['actual']['scan'],summaries[1]['actual']['scan'])
        capture=os.environ.get('DIGITAL_LIFE_CAPTURE_CERTIFIED_INPUT')
        if capture:
            out=Path(capture)/('deep-8'if field_count==8 else'shared-4');out.mkdir(parents=True,exist_ok=False)
            for item in summaries:(out/(item['mode']+'.json')).write_text(json.dumps(item,ensure_ascii=False,indent=2)+'\n')
            (out/'result.json').write_text(json.dumps({'passed':not differences,'differences':differences,'real_models_called':False,'formal_instance_accessed':False,'source':'same synthetic SQLite backups, original caps/transactions/parameterized insert, fixed clock/UUID; actual resource ledger differences retained','stats':summaries[-1]['stats'],'actuals':{item['mode']:item['actual']for item in summaries}},indent=2)+'\n')
    def test_unknown_trigger_is_original_insert_without_certificate(self):
        self.s.db.execute('CREATE TRIGGER synthetic_unknown_input AFTER INSERT ON tl_input_dependency BEGIN SELECT 1; END;')
        with self.meter().installed(self.s),self.e.owners.source.verification_boundary():self.register()
        self.assertEqual(self.s._input_certificate_stats['issued'],0);self.assertEqual(self.s._input_certificate_stats['fallback'],1)
        self.assertEqual(len(self.s.rows('tl_input_dependency')),1)
    def test_actual_single_table_footprint_is_not_the_approved_two_table_write(self):
        from digital_life.infrastructure.persistence.sqlite_store import _INPUT_COLUMNS,_INPUT_SQL
        # The lower-level monitor can witness another reviewed schema. It is
        # not this application's fixed two-table input registration contract.
        self.s.db.execute('DROP TRIGGER tl_input_dependency_register')
        with self.s.tx():key=self.s.insert('object_registry',kind='tl_input_dependency')
        values=dict(request_ref_id=self.consumer['id'],source_ref_id=self.token['object']['id'],source_epoch=0,
                    source_revision_ref_id=None,field_path='/single-table-witness',purpose='learn',
                    recipient_ref_id=self.principal['recipient']['id'],body_digest=None,retention_state='allowed',
                    row_revision=0,id=key,instance_id=self.s.instance_id)
        with self.meter().installed(self.s),self.e.owners.source.verification_boundary():
            phase=current_readset(self.s);managed=managed_database(self.s.db)
            with self.s.tx():
                phase.checkpoint()
                contract=managed.bind_insert(_INPUT_SQL,'tl_input_dependency',frozenset((('main','tl_input_dependency'),('main','object_registry'))),'synthetic-alternative-no-register-trigger')
                _,receipt=managed.certified_insert(contract,tuple(values[k]for k in _INPUT_COLUMNS),phase.stamp)
                self.assertIsNotNone(receipt);self.assertTrue(managed.receipt_current(receipt))
                self.assertEqual(receipt.tables,frozenset((('main','tl_input_dependency'),)))
                self.assertFalse(phase.accept_input_receipt(managed,receipt))
                self.assertIsNone(phase.input_receipt)
    def test_unknown_progress_uses_original_insert_without_certificate(self):
        with self.meter().installed(self.s),self.e.owners.source.verification_boundary():
            managed_database(self.s.db).set_progress_handler(lambda:0,1000)
            self.register()
        self.assertEqual(self.s._input_certificate_stats['issued'],0)
    def test_callback_caches_are_paused_without_disabling_file_tracking(self):
        key=self.s.artifact({'synthetic payload':'x'*10000});origin=ref(self.s,key,'artifacts');row=self.s.row('artifacts',key);storage=self.e.runtime.storage;observed=[]
        def callback():
            self.assertTrue(callback_active());before=dict(meter.actual)
            self.assertTrue(list(facts(self.s,'source_kind',key)));storage.validate_ref(origin)
            self.assertEqual(cached_artifact(row),(False,None));self.assertIsNone(cached_metadata(('synthetic',)))
            remember_artifact(row,b'not admitted');cached_metadata(('synthetic',),{'wrong':'not admitted'})
            self.assertEqual(storage.read_artifact(key),{'synthetic payload':'x'*10000})
            observed.append({'scan':meter.actual['scan']-before['scan'],'bytes':meter.actual['bytes']-before['bytes']})
            return 1
        self.s.db.create_function('synthetic_cache_probe',0,callback)
        with self.meter().installed(self.s)as meter,self.e.owners.source.verification_boundary():
            list(facts(self.s,'source_kind',key));storage.validate_ref(origin);storage.read_artifact(key);cached_metadata(('synthetic',),{'original':True})
            self.assertEqual(self.s.db.execute('SELECT synthetic_cache_probe()').fetchone()[0],1)
            self.assertTrue(current_readset(self.s).blobs);self.assertEqual(cached_metadata(('synthetic',)),{'original':True})
            hit,raw=cached_artifact(row);self.assertTrue(hit);self.assertNotEqual(raw,b'not admitted')
        self.assertGreaterEqual(observed[0]['scan'],3);self.assertGreaterEqual(observed[0]['bytes'],row['size'])
    def test_same_connection_zero_row_write_invalidates_materials(self):
        with self.meter().installed(self.s),self.e.owners.source.verification_boundary():
            phase=current_readset(self.s);list(facts(self.s,'source_kind',self.token['object']['id']));generation=phase.generation
            changes=self.s.db.total_changes;self.s.db.execute("UPDATE activities SET revision=revision WHERE id='not-an-object'")
            self.assertEqual(self.s.db.total_changes,changes);list(facts(self.s,'source_kind',self.token['object']['id']))
            self.assertGreater(phase.generation,generation)
    def test_commit_gap_control_change_is_detected_after_sqlite_commit(self):
        with self.assertRaises(Conflict):
            with self.meter().installed(self.s),self.e.owners.source.verification_boundary():
                key=self.e.runtime.eligibility.register_dependency(self.entry,self.principal,self.consumer,self.dep,'/gap',self.scope)
                managed=managed_database(self.s.db);execute=managed.execute;called=[]
                def changed(sql,*args):
                    if sql=='COMMIT'and managed.monitor_state()['accepted']is not None:
                        called.append(True);self.f.control.stop('synthetic post-probe commit gap')
                    return execute(sql,*args)
                with patch.object(managed,'execute',changed),self.assertRaises(Conflict):self.e.runtime.eligibility.register_input(self.entry,self.principal,self.consumer,key)
                self.assertEqual(called,[True]);self.assertIsNone(current_readset(self.s))
        # This is a post-COMMIT external-effect rejection, not a false rollback
        # claim: the technical input row may already exist; no model was called.
        self.assertEqual(len(self.s.rows('tl_input_dependency')),1)
    def test_version_probe_external_control_change_is_sampled_before_accept(self):
        called=[]
        with self.assertRaises(Conflict):
            with self.meter().installed(self.s),self.e.owners.source.verification_boundary():
                key=self.e.runtime.eligibility.register_dependency(self.entry,self.principal,self.consumer,self.dep,'/probe',self.scope)
                managed=managed_database(self.s.db);execute=managed.execute
                def changed(sql,*args):
                    if sql=='PRAGMA data_version'and not called and managed.monitor_state()['pending']is not None:
                        called.append(True);self.f.control.stop('synthetic version probe external effect')
                    return execute(sql,*args)
                with patch.object(managed,'execute',changed):self.e.runtime.eligibility.register_input(self.entry,self.principal,self.consumer,key)
        self.assertEqual(called,[True]);self.assertEqual(len(self.s.rows('tl_input_dependency')),0)
        self.assertEqual(self.s._input_certificate_stats['accepted'],0)
    def test_unknown_authority_and_connection_do_not_receive_write_receipt(self):
        from digital_life.application.learning.runtime_owners import LocalEligibility
        class Unknown(LocalEligibility):pass
        old=self.e.runtime.eligibility.authority;self.e.runtime.eligibility.authority=Unknown(self.e.owners)
        try:
            with self.meter().installed(self.s),self.e.owners.source.verification_boundary():self.register('/unknown-authority')
        finally:self.e.runtime.eligibility.authority=old
        self.assertEqual(self.s._input_certificate_stats['issued'],0)
        class Proxy:
            def __init__(self,actual):self.actual=actual
            def __getattr__(self,name):return getattr(self.actual,name)
        original=self.s.db;self.s.db=Proxy(original)
        try:
            with self.meter().installed(self.s),self.e.owners.source.verification_boundary():self.register('/unknown-connection')
        finally:self.s.db=original
        self.assertEqual(self.s._input_certificate_stats['issued'],0);self.assertEqual(len(self.s.rows('tl_input_dependency')),2)


if __name__=='__main__':unittest.main()
