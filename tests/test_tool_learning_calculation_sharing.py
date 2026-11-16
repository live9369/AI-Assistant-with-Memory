"""Calculation facts are shared without dropping logical domain sources."""
from contextlib import nullcontext
from contextvars import copy_context
from copy import deepcopy
import sqlite3
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import Conflict,Forbidden
from digital_life.application.learning.contexts import DomainReadCollector,calculation_read_boundary,source_preparation_observer_boundary
from digital_life.application.learning.engine import source_scope
from digital_life.application.learning.eligibility import ref
from digital_life.infrastructure.persistence.tool_learning_meter import (PhysicalReadMeter,immutable_reference_boundary,notify_logical_row,logical_observer_required)
from digital_life.infrastructure.persistence.tool_learning_readset import current_readset,facts,shared_read_boundary
from tests import test_tool_learning_runtime as fixture


class CalculationSourcePreparationTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.StrictEngineEndToEndTests();self.f.enable_features=False;self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.engine=self.f.strict;self.scope=source_scope(self.s)
        self.entry,self.principal=self.engine.owners.entry('M14','learn')
        self.collector=DomainReadCollector(self.engine,self.entry,self.principal,self.scope,set())
        self.config=self.s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()[0]
    def meter(self):
        return PhysicalReadMeter(self.engine._read_slice(self.f.activity,.5),self.s.row('activities',self.f.activity)['deadline'])
    def check(self):
        token={'object':ref(self.s,self.config),'revision':0,'epoch':0}
        return self.engine.runtime.eligibility._check(self.entry,self.principal,token,self.scope,'learn',self.principal['recipient'],'calculation-per-use-test')
    def test_logical_notification_does_not_claim_a_physical_read(self):
        meter=self.meter();seen=[]
        with meter.installed(self.s):
            meter.row_observer=seen.append;before=dict(meter.actual)
            row={'id':self.config};self.assertIs(notify_logical_row(row),row)
            self.assertEqual(meter.actual,before);self.assertEqual(seen,[row]);self.assertTrue(logical_observer_required())
    def test_unknown_observer_reference_validation_is_never_memoized(self):
        meter=self.meter();seen=[];sql=[];self.s.db.set_trace_callback(sql.append)
        with meter.installed(self.s),immutable_reference_boundary(self.s):
            meter.row_observer=seen.append
            value=ref(self.s,self.config,'configuration_versions')
            self.engine.runtime.storage.validate_ref(value);self.engine.runtime.storage.validate_ref(value)
        matches=[q for q in sql if 'FROM object_registry WHERE instance_id='in q and self.config in q]
        self.assertEqual(len(matches),2);self.assertGreaterEqual(len(seen),2)
    def test_exact_busy_collector_can_share_reference_mapping_but_domain_use_is_observed(self):
        meter=self.meter();sql=[];self.s.db.set_trace_callback(sql.append)
        with meter.installed(self.s),self.collector.installed(meter),calculation_read_boundary(self.engine):
            value=ref(self.s,self.config,'configuration_versions')
            with self.collector._preparing_source():
                self.assertFalse(logical_observer_required())
                self.engine.runtime.storage.validate_ref(value);before=len(sql)
                self.engine.runtime.storage.validate_ref(value)
                self.assertEqual(len(sql),before);self.assertFalse(self.collector.tokens)
            self.assertTrue(logical_observer_required())
            self.engine.runtime.storage.validate_ref(value)
            self.assertIn(self.config,{key[0]for key in self.collector.tokens})
    def test_copied_context_and_nested_exception_cannot_revive_suppression(self):
        meter=self.meter()
        with meter.installed(self.s),self.collector.installed(meter):
            with self.collector._preparing_source():
                with self.collector._preparing_source():self.assertFalse(logical_observer_required())
                saved=copy_context();self.assertFalse(logical_observer_required())
            self.collector.busy=True
            try:self.assertTrue(saved.run(logical_observer_required))
            finally:self.collector.busy=False
            with self.assertRaisesRegex(RuntimeError,'synthetic'):
                with self.collector._preparing_source():raise RuntimeError('synthetic')
            self.assertFalse(self.collector.busy);self.assertTrue(logical_observer_required())
    def test_replaced_and_forged_unknown_observer_cannot_claim_trusted_suppression(self):
        meter=self.meter()
        class Fake:
            def __call__(_,row):pass
        with meter.installed(self.s),self.collector.installed(meter):
            original=meter.row_observer
            with self.collector._preparing_source():
                meter.row_observer=lambda row:None;self.assertTrue(logical_observer_required())
                meter.row_observer=original
            fake=Fake();fake.__self__=self.collector;fake.__func__=DomainReadCollector.on_row
            meter.row_observer=fake;self.collector.busy=True
            try:
                with source_preparation_observer_boundary(self.collector):self.assertTrue(logical_observer_required())
            finally:self.collector.busy=False;meter.row_observer=original
    def test_unknown_collector_and_subclass_cannot_open_application_trusted_scope(self):
        from types import MethodType, SimpleNamespace
        meter=self.meter()
        class Subclass(DomainReadCollector):pass
        unknown=SimpleNamespace(busy=True)
        child=Subclass(self.engine,self.entry,self.principal,self.scope,set());child.busy=True
        with meter.installed(self.s),self.collector.installed(meter):
            original=meter.row_observer
            try:
                for value in (unknown,child):
                    meter.row_observer=MethodType(DomainReadCollector.on_row,value)
                    with source_preparation_observer_boundary(value):self.assertTrue(logical_observer_required())
            finally:meter.row_observer=original
    def test_calculation_boundary_disables_owner_permission_memo_and_keeps_every_use_check(self):
        meter=self.meter();source=self.engine.owners.source;original=source._verified
        with meter.installed(self.s),self.collector.installed(meter),calculation_read_boundary(self.engine):
            self.assertIsNone(source._verified);self.assertIsNotNone(current_readset(self.s))
            with patch.object(self.engine.owners,'source_access',wraps=self.engine.owners.source_access)as access,patch.object(source,'verify_version',wraps=source.verify_version)as versions:
                with self.collector._preparing_source():
                    self.check();self.check();self.check()
                selected=[call for call in access.call_args_list if call.args[2]['id']==self.config]
                self.assertEqual(len(selected),3)
                selected_versions=[call for call in versions.call_args_list if call.args[2]['object']['id']==self.config]
                self.assertEqual(len(selected_versions),3)
        self.assertIs(source._verified,original);self.assertIsNone(current_readset(self.s))
    def test_calculation_boundary_exception_restores_outer_owner_state_and_closes_phase(self):
        meter=self.meter();source=self.engine.owners.source;prior={'outer technical marker'};source._verified=prior
        try:
            with self.assertRaisesRegex(RuntimeError,'calculation failure'):
                with meter.installed(self.s),self.collector.installed(meter),calculation_read_boundary(self.engine):
                    self.assertIsNone(source._verified);self.assertIsNotNone(current_readset(self.s))
                    raise RuntimeError('calculation failure')
            self.assertIs(source._verified,prior);self.assertIsNone(current_readset(self.s));self.assertFalse(self.collector.busy)
        finally:source._verified=None
    def test_cached_fixed_row_from_technical_preparation_still_captures_domain_source(self):
        meter=self.meter();memory=self.f.base.f.expected['memory_id']
        with meter.installed(self.s),self.collector.installed(meter),calculation_read_boundary(self.engine):
            with self.collector._preparing_source():
                rows=list(facts(self.s,'selected_revision',memory,1));self.assertEqual(len(rows),1)
            self.assertFalse(self.collector.tokens)
            rows_again=list(facts(self.s,'selected_revision',memory,1))
            self.assertEqual(rows_again,rows)
            self.assertIn(rows[0][0],{key[0]for key in self.collector.tokens})
    def test_fixed_fact_logical_hit_calls_unknown_observer_without_physical_charge(self):
        meter=self.meter();seen=[]
        with meter.installed(self.s),shared_read_boundary(self.s):
            meter.row_observer=seen.append
            list(facts(self.s,'source_kind',self.config));seen.clear();before=dict(meter.actual)
            list(facts(self.s,'source_kind',self.config))
            self.assertEqual(meter.actual,before);self.assertEqual(len(seen),1)
    def test_current_selector_and_native_version_are_not_deduplicated_by_id(self):
        meter=self.meter();key=self.f.activity
        with meter.installed(self.s),self.collector.installed(meter),calculation_read_boundary(self.engine):
            self.collector.observe(key,['id']);self.collector.observe(key,['id','revision'])
            self.s.db.execute('UPDATE activities SET revision=revision+1 WHERE id=?',(key,))
            self.collector.observe(key,['id','revision'])
            versions=[token['revision']for token in self.collector.tokens.values()if token['object']['id']==key]
            self.assertGreaterEqual(len(set(versions)),3)
            snapshots=[]
            with self.collector._preparing_source():
                for row in self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND source='tl.source.snapshot' ORDER BY event_seq",(self.s.instance_id,)):
                    body=self.s.read_artifact(row[0])
                    if body['origin']['id']==key:snapshots.append(body)
            self.assertTrue(any(v['selector']==['id']for v in snapshots))
            self.assertTrue(any(v['selector']==['id','revision']for v in snapshots))
            self.assertNotEqual(snapshots[-1]['native_revision'],snapshots[0]['native_revision'])
    def test_foreign_commit_and_stop_still_reject_inside_shared_calculation(self):
        self.s.db.execute('PRAGMA journal_mode=WAL');meter=self.meter()
        with self.assertRaisesRegex(Conflict,'outside phase'):
            with meter.installed(self.s),self.collector.installed(meter),calculation_read_boundary(self.engine):
                with self.collector._preparing_source():self.check()
                other=sqlite3.connect(self.s.root/'runtime.sqlite')
                try:other.execute('UPDATE activities SET revision=revision+1 WHERE id=?',(self.f.activity,));other.commit()
                finally:other.close()
                with self.collector._preparing_source():self.check()
        meter=self.meter()
        with self.assertRaises((Conflict,Forbidden)):
            with meter.installed(self.s),self.collector.installed(meter),calculation_read_boundary(self.engine):
                with self.collector._preparing_source():self.check()
                self.f.control.stop('synthetic calculation stop')
                with self.collector._preparing_source():self.check()

class FullCalculationDifferentialTests(unittest.TestCase):
    def test_full_eight_module_values_sources_selectors_and_versions_match_without_budget_growth(self):
        self._compare_contexts(False)
    def test_native_and_managed_full_contexts_keep_values_sources_and_stage_read_counts(self):
        self._compare_contexts(True)
    def _compare_contexts(self,native_comparison):
        import datetime
        import hashlib
        import json
        import os
        from pathlib import Path
        import shutil
        import tempfile
        import time
        import uuid
        from digital_life.application.runtime.engine import Engine
        from digital_life.application.services import States
        from digital_life.application.learning.engine import StrictEngine
        from digital_life.application.lifecycle.control_plane import Control
        from digital_life.infrastructure.persistence.sqlite_store import Store
        from digital_life.domain import contracts
        from digital_life.infrastructure.persistence.tool_learning_meter import _Cursor
        from digital_life.application.learning import contexts as contexts_module
        from digital_life.infrastructure.persistence import tool_learning_readset as readset_module
        base=fixture.StrictEngineEndToEndTests();base.setUp();self.addCleanup(base.doCleanups)
        store=base.s
        actual=fixture.StrictActualUseTests();actual.f=base;actual.s=store;actual.activity=base.activity;actual.k=base.strict;actual.control=base.control
        request,result,intent,scope=actual.producer()
        evidence=store.evidence(object_id=result,method='synthetic prior accepted reply for state lineage')
        for index in range(4):States(store).observe('F.shared_reply_'+str(index),index,'count',evidence,ttl=300)
        Engine(store,base.identity).transition(base.activity,'running','synthetic full calculation comparison')
        real_datetime=datetime.datetime;instant=real_datetime.now(datetime.timezone.utc)
        instant=instant.replace(microsecond=(instant.microsecond//1000)*1000)
        fixed=instant.isoformat(timespec='milliseconds').replace('+00:00','Z')
        class FrozenDateTime(real_datetime):
            @classmethod
            def now(cls,tz=None):return instant.replace(tzinfo=None)if tz is None else instant.astimezone(tz)
        fixed_disk=shutil.disk_usage(store.root)
        summaries=[]
        retention_boundary=contexts_module.calculated_retention_read_boundary
        live_boundary=contexts_module.live_binding_read_boundary
        cases=(('unshared',False,False,False,True,True,True),('calculation_only',True,False,False,True,True,True),
               ('retention_only',True,True,False,True,True,True),('live_only',True,False,True,True,True,True),
               ('source_rows_off',True,True,True,False,True,True),('snapshot_rows_off',True,True,True,True,False,True),
               ('dependency_projection_off',True,True,True,True,True,False),('both',True,True,True,True,True,True))
        if native_comparison:cases=(('native',True,True,True,True,True,True),('managed',True,True,True,True,True,True))
        for label,shared,retention_shared,live_shared,source_rows_shared,snapshot_rows_shared,dependency_projected in cases:
            with tempfile.TemporaryDirectory()as directory:
                root=Path(directory)
                # Exact synthetic starting identities/content, isolated writable
                # copies. SQLite backup includes committed WAL contents.
                for name in ('blobs','workspace','snapshots'):shutil.copytree(store.root/name,root/name)
                for source,name in ((store.db,'runtime.sqlite'),(base.control.db,'control.sqlite')):
                    destination=sqlite3.connect(root/name)
                    try:source.backup(destination)
                    finally:destination.close()
                clone=Store(root);control=Control(root,clone.instance_id)
                if label=='native':
                    clone.db.close();clone.db=sqlite3.connect(root/'runtime.sqlite',isolation_level=None)
                    clone.db.row_factory=sqlite3.Row;clone.db.execute('PRAGMA foreign_keys=ON')
                clock=sqlite3.connect(':memory:')
                def strftime(*values):
                    values=list(values)
                    if len(values)>1 and values[1]=='now':values[1]=fixed
                    return clock.execute('SELECT strftime('+','.join('?'for _ in values)+')',values).fetchone()[0]
                clone.db.create_function('strftime',-1,strftime)
                sequence=[0]
                def next_uuid():
                    sequence[0]+=1
                    return uuid.UUID(int=2**120+sequence[0])
                try:
                    engine=StrictEngine(clone,base.identity,base.strict.provider)
                    context=clone.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(base.activity,)).fetchone()[0]
                    with patch.object(contracts,'datetime',FrozenDateTime),patch.object(uuid,'uuid4',next_uuid),patch.object(shutil,'disk_usage',return_value=fixed_disk):
                        entry,principal=engine.owners.entry('M14','learn',clone.config()['controller'])
                        features,fields=engine._features(entry,principal,base.activity,context,scope,'你好，我是liwei',{'object':ref(clone,clone.row('activities',base.activity)['trigger_event_id']),'revision':0,'epoch':0})
                        before_events={row['id']for row in clone.rows('runtime_events')}
                        captures=[];permissions=[];meters=[];phase_at_retention=[]
                        original_capture=DomainReadCollector.observe
                        original_access=engine.owners.source_access
                        original_installed=PhysicalReadMeter.installed
                        original_check=engine.runtime.eligibility._check
                        def observed(collector,key,columns=None):
                            if not collector.busy and type(key)is str and __import__('re').fullmatch('[0-9a-f]{32}',key) and key not in collector.created:
                                captures.append({'id':key,'columns':None if columns is None else sorted(columns)})
                            return original_capture(collector,key,columns)
                        def access(*args,**kwargs):
                            permissions.append({'entry':args[0],'principal':deepcopy(args[1]),'origin':deepcopy(args[2]),'scope':deepcopy(args[3])})
                            return original_access(*args,**kwargs)
                        def installed(meter,s):
                            meters.append(meter);return original_installed(meter,s)
                        def checked(*args,**kwargs):
                            stage=args[6]if len(args)>6 else kwargs.get('stage')
                            if stage=='before_calculated_material_retention':phase_at_retention.append(current_readset(clone)is None)
                            return original_check(*args,**kwargs)
                        boundary=contexts_module.calculation_read_boundary if shared else lambda engine:nullcontext()
                        row_reader=engine.owners._source_row
                        def source_row(kind,key):return row_reader(kind,key)if source_rows_shared else clone.row(kind,key)
                        snapshot_reader=engine.owners.snapshots._complete_origin_row
                        def snapshot_row(origin):return snapshot_reader(origin)if snapshot_rows_shared else clone.row(origin['kind'],origin['id'])
                        dependency_reader=readset_module.dependency_materials
                        def dependencies(store,consumer,limit):return dependency_reader(store,consumer,limit)if dependency_projected else readset_module.facts(store,'consumer_dependencies',consumer,limit)
                        started=time.monotonic()
                        with patch.object(contexts_module,'calculation_read_boundary',boundary),patch.object(contexts_module,'calculated_retention_read_boundary',retention_boundary if retention_shared else lambda engine:nullcontext()),patch.object(contexts_module,'live_binding_read_boundary',live_boundary if live_shared else lambda engine:nullcontext()),patch.object(engine.owners,'_source_row',source_row),patch.object(engine.owners.snapshots,'_complete_origin_row',snapshot_row),patch.object(readset_module,'dependency_materials',dependencies),patch.object(DomainReadCollector,'observe',observed),patch.object(engine.owners,'source_access',access),patch.object(PhysicalReadMeter,'installed',installed),patch.object(engine.runtime.eligibility,'_check',checked),patch.object(engine.provider,'generate_fresh',side_effect=AssertionError('calculation must not invoke model')):
                            values,live,new_fields=engine._contexts(entry,principal,base.activity,context,'你好，我是liwei',{'items':[]},fields,scope)
                        elapsed=time.monotonic()-started
                        snapshots=[]
                        for row in clone.rows('runtime_events'):
                            if row['id']not in before_events and row['source']=='tl.source.snapshot':snapshots.append(clone.read_artifact(row['payload_artifact_id']))
                        bundle=new_fields[0]['dependencies'][0]['target']['id']
                        dependencies=[]
                        for row in clone.db.execute('SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? ORDER BY field_path,relation',(clone.instance_id,bundle)):
                            dependencies.append(engine.runtime.eligibility._metadata(row))
                        ledger=json.loads(clone.row('activities',base.activity)['budget_json'])
                        summary={'case':label,'shared':shared,'retention_shared':retention_shared,'live_shared':live_shared,'source_rows_shared':source_rows_shared,'snapshot_rows_shared':snapshot_rows_shared,'dependency_projected':dependency_projected,'values':values,'features':features,'fields':fields,'live':live,'new_fields':new_fields,'bundle_dependencies':dependencies,'capture_uses':captures,'permission_uses':permissions,'snapshots':snapshots,'caps':ledger['budget'],'uuid_calls':sequence[0],
                                 'meter_actuals':[dict(meter.actual)for meter in meters],
                                 'wall_seconds':elapsed,'retention_checks_outside_shared_phase':phase_at_retention}
                        summaries.append(summary)
                finally:clone.close();control.close();clock.close()
        before=summaries[0];after=summaries[-1]
        expected={'goal_regulation','self_maintenance','autonomy_agenda','memory_quality','relationships','habit_learning','personality_growth','behavior_policy'}
        self.assertTrue(expected<=set(before['values']));self.assertTrue(expected<=set(after['values']))
        semantic=('values','features','fields','live','new_fields','bundle_dependencies','capture_uses','permission_uses','snapshots','caps','uuid_calls')
        differences=[summary['case']+':'+key for summary in summaries[1:] for key in semantic if before[key]!=summary[key]]
        captured=os.environ.get('DIGITAL_LIFE_CAPTURE_NATIVE_CALCULATION_DIFF'if native_comparison else'DIGITAL_LIFE_CAPTURE_CALCULATION_DIFF')
        if captured:
            destination=Path(captured);destination.mkdir(parents=True,exist_ok=False)
            for summary in summaries:(destination/(summary['case']+'.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
            (destination/'result.json').write_text(json.dumps({'passed':not differences,'differences':differences,'source':'independent copies of same fresh synthetic fixture, fixed clock/UUID; no semantic stripping','real_models_called':False,'formal_instance_accessed':False,'before_scan':sum(v['scan']for v in before['meter_actuals']),'after_scan':sum(v['scan']for v in after['meter_actuals']),'case_meter_actuals':{summary['case']:summary['meter_actuals']for summary in summaries}},indent=2)+'\n')
        self.assertEqual(differences,[])
        for summary in summaries:
            self.assertTrue(summary['retention_checks_outside_shared_phase'])
            self.assertTrue(all(value is not summary['retention_shared'] for value in summary['retention_checks_outside_shared_phase']))
        if native_comparison:
            # New exact projections/schema raw facts apply only to known
            # Managed phases; Native intentionally keeps its original SQL.
            # Retain the no-backend-regression check at every stage while all
            # business/source/authority/UUID comparisons above remain exact.
            for native,managed in zip(before['meter_actuals'],after['meter_actuals']):
                self.assertLessEqual(managed['scan'],native['scan'])
            self.assertLess(sum(v['scan']for v in after['meter_actuals']),sum(v['scan']for v in before['meter_actuals']))
            return
        baseline=summaries[1]
        self.assertLess(sum(v['scan']for v in summaries[2]['meter_actuals']),sum(v['scan']for v in baseline['meter_actuals']))
        self.assertLess(sum(v['scan']for v in summaries[3]['meter_actuals']),sum(v['scan']for v in baseline['meter_actuals']))
        self.assertLess(sum(v['bytes']for v in after['meter_actuals']),sum(v['bytes']for v in summaries[4]['meter_actuals']))
        self.assertLess(sum(v['bytes']for v in after['meter_actuals']),sum(v['bytes']for v in summaries[5]['meter_actuals']))
        self.assertLess(sum(v['bytes']for v in after['meter_actuals']),sum(v['bytes']for v in summaries[6]['meter_actuals']))
        self.assertLess(sum(v['scan']for v in after['meter_actuals']),sum(v['scan']for v in before['meter_actuals']))


if __name__=='__main__':unittest.main()
