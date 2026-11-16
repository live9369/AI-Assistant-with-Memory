"""Complete snapshot origin/CAS facts, after real callback freshness checks."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch
from digital_life.application.learning.contexts import live_binding_read_boundary
from digital_life.application.learning.eligibility import ref
from digital_life.application.learning.engine import source_scope
from digital_life.application.learning.source_snapshot import SourceSnapshots,SnapshotAuthority
from digital_life.domain.contracts import Conflict,Forbidden
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
from digital_life.infrastructure.persistence.tool_learning_readset import current_readset
from tests import test_tool_learning_runtime as fixture


class SnapshotSourceRowTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.StrictEngineEndToEndTests();self.f.enable_features=False;self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.e=self.f.strict;self.o=self.e.owners;self.snapshots=self.o.snapshots;self.scope=source_scope(self.s)
        self.entry,self.principal=self.o.entry('M14','learn');self.origin=ref(self.s,self.f.activity)
    def meter(self):return PhysicalReadMeter(self.e._read_slice(self.f.activity,.5),self.s.row('activities',self.f.activity)['deadline'])
    def boundary(self):return live_binding_read_boundary(self.e)
    def values(self,selector=None):
        selector=sorted(self.s.columns['activities'])if selector is None else selector
        return (self.snapshots._origin(self.entry,self.principal,self.origin,selector,self.scope,'synthetic-source-row-probe'),self.snapshots._native(self.origin))
    def capture(self):return self.snapshots.capture(self.entry,self.principal,self.origin,['id'],self.scope)
    def test_identity_projection_does_not_force_duplicate_full_projection(self):
        with self.meter().installed(self.s),self.boundary():
            first=self.snapshots.capture(self.entry,self.principal,self.origin,['id','input_epoch'],self.scope)
            identity=self.capture()
            count=len(self.s.rows('object_revision_registry'))
            again=self.snapshots.capture(self.entry,self.principal,self.origin,['id','input_epoch'],self.scope)
            self.assertEqual(again,first)
            self.assertNotEqual(identity['revision'],first['revision'])
            self.assertEqual(len(self.s.rows('object_revision_registry')),count)
            self.snapshots.fixed(self.entry,self.principal,again,self.scope)
    def test_projection_reuse_does_not_hide_value_change_and_reversion(self):
        with self.meter().installed(self.s),self.boundary():
            selector=['id','input_epoch']
            first=self.snapshots.capture(self.entry,self.principal,self.origin,selector,self.scope)
            self.capture()
            self.s.db.execute('UPDATE activities SET input_epoch=input_epoch+1 WHERE id=?',(self.f.activity,))
            second=self.snapshots.capture(self.entry,self.principal,self.origin,selector,self.scope)
            self.capture()
            self.s.db.execute('UPDATE activities SET input_epoch=input_epoch-1 WHERE id=?',(self.f.activity,))
            reverted=self.snapshots.capture(self.entry,self.principal,self.origin,selector,self.scope)
            self.assertGreater(second['revision'],first['revision'])
            self.assertGreater(reverted['revision'],second['revision'])
    def test_origin_native_probe_keeps_values_and_callbacks_while_reducing_bytes(self):
        summaries=[];read=self.snapshots._complete_origin_row
        for shared in (False,True):
            meter=self.meter();sql=[];self.s.db.set_trace_callback(sql.append)
            reader=read if shared else lambda origin:self.s.row(origin['kind'],origin['id'])
            with meter.installed(self.s),self.boundary(),patch.object(self.snapshots,'_complete_origin_row',reader),patch.object(self.o.snapshot_authority,'verify_source',wraps=self.o.snapshot_authority.verify_source)as verify:
                started=time.monotonic();values=[self.values()for _ in range(32)];elapsed=time.monotonic()-started
                self.assertEqual(verify.call_count,32)
            self.s.db.set_trace_callback(None)
            summaries.append({'shared':shared,'values':values,'actual':dict(meter.actual),'observed_seconds':elapsed,'source_queries':sum(q.startswith('SELECT * FROM activities WHERE id=')for q in sql)})
        self.assertEqual(summaries[0]['values'],summaries[1]['values']);self.assertLess(summaries[1]['actual']['bytes'],summaries[0]['actual']['bytes'])
        self.assertLess(summaries[1]['source_queries'],summaries[0]['source_queries'])
        capture=os.environ.get('DIGITAL_LIFE_CAPTURE_SNAPSHOT_ROW_DIFF')
        if capture:
            out=Path(capture);out.mkdir(parents=True,exist_ok=False)
            (out/'result.json').write_text(json.dumps({'passed':True,'summaries':summaries,'real_models_called':False,'formal_instance_accessed':False},indent=2)+'\n')
    def test_unknown_observer_keeps_original_sql_row_callback_sequence(self):
        summaries=[];read=self.snapshots._complete_origin_row
        for shared in (False,True):
            seen=[];meter=self.meter();reader=read if shared else lambda origin:self.s.row(origin['kind'],origin['id'])
            with meter.installed(self.s),self.boundary(),patch.object(self.snapshots,'_complete_origin_row',reader):
                meter.row_observer=lambda row:seen.append(dict(row));values=[self.values(['id'])for _ in range(3)]
            summaries.append((values,seen))
        self.assertEqual(summaries[0],summaries[1])
    def test_return_dict_is_fresh_and_native_value_is_not_mutable_alias(self):
        with self.meter().installed(self.s),self.boundary():
            first=self.snapshots._complete_origin_row(self.origin);expected=dict(first);first['revision']=-999
            self.assertEqual(self.snapshots._complete_origin_row(self.origin),expected)
            self.assertEqual(self.snapshots._native(self.origin)['value'],expected['revision'])
    def test_no_phase_uses_original_row_sql(self):
        with patch.object(self.o,'_source_row',wraps=self.o._source_row)as reader:
            self.snapshots._complete_origin_row(self.origin);self.snapshots._native(self.origin)
        self.assertEqual(reader.call_count,0);self.assertIsNone(current_readset(self.s))
    def test_actual_authority_owner_alias_mismatch_falls_back(self):
        prior=self.o.snapshot_authority
        with self.meter().installed(self.s),self.boundary():
            self.o.snapshot_authority=SnapshotAuthority()
            try:
                with patch.object(self.o,'_source_row',wraps=self.o._source_row)as reader:self.snapshots._complete_origin_row(self.origin)
                self.assertEqual(reader.call_count,0)
            finally:self.o.snapshot_authority=prior
    def test_unknown_authority_and_source_snapshots_subclass_use_original_sql(self):
        class Child(SourceSnapshots):pass
        child=Child(self.s,self.o.snapshot_authority)
        for target,authority in ((self.snapshots,SnapshotAuthority()),(child,self.o.snapshot_authority)):
            prior=target.authority;target.authority=authority
            try:
                with self.meter().installed(self.s),self.o.source.verification_boundary(),patch.object(self.o,'_source_row',wraps=self.o._source_row)as reader:
                    target._complete_origin_row(self.origin);self.assertEqual(reader.call_count,0)
            finally:target.authority=prior
    def test_dependencies_reuse_complete_row_without_changing_lineage(self):
        snapshot={'origin':self.origin,'selector':['id'],'scope':self.scope};results=[];read=self.snapshots._complete_origin_row
        for shared in (False,True):
            reader=read if shared else lambda origin:self.s.row(origin['kind'],origin['id'])
            with self.meter().installed(self.s),self.boundary(),patch.object(self.snapshots,'_complete_origin_row',reader):
                results.append(self.o.snapshot_authority.dependencies(self.entry,self.principal,snapshot))
        self.assertEqual(results[0],results[1])
    def test_final_source_callback_change_is_seen_before_capture_commit(self):
        original=self.o.snapshot_authority.verify_source;before=self.s.row('activities',self.f.activity)['revision'];count=len(self.s.rows('object_revision_registry'));called=[]
        def verify(entry,principal,origin,selector,scope,stage):
            result=original(entry,principal,origin,selector,scope,stage)
            if stage=='final':called.append(stage);self.s.db.execute('UPDATE activities SET revision=revision+1 WHERE id=?',(self.f.activity,))
            return result
        with patch.object(self.o.snapshot_authority,'verify_source',verify),self.assertRaises(Conflict):
            with self.meter().installed(self.s),self.boundary():self.capture()
        self.assertEqual(called,['final']);self.assertEqual(self.s.row('activities',self.f.activity)['revision'],before);self.assertEqual(len(self.s.rows('object_revision_registry')),count)
    def test_final_source_callback_tracked_file_tamper_rejects_before_commit(self):
        key=self.s.artifact({'synthetic tracked dependency':'payload'});row=self.s.row('artifacts',key);path=self.s.root/'blobs'/row['storage_ref'];prior=path.read_bytes();original=self.o.snapshot_authority.verify_source;count=len(self.s.rows('object_revision_registry'));called=[]
        def verify(entry,principal,origin,selector,scope,stage):
            result=original(entry,principal,origin,selector,scope,stage)
            if stage=='final':called.append(stage);path.write_bytes(prior+b' ')
            return result
        try:
            with patch.object(self.o.snapshot_authority,'verify_source',verify),self.assertRaises(Conflict):
                with self.meter().installed(self.s),self.boundary():self.s.read_artifact(key);self.capture()
            self.assertEqual(called,['final']);self.assertEqual(len(self.s.rows('object_revision_registry')),count)
        finally:path.write_bytes(prior)
    def test_fixed_source_callback_foreign_commit_rejected_inside_old_read_snapshot(self):
        self.s.db.execute('PRAGMA journal_mode=WAL');token=self.capture();original=self.o.snapshot_authority.verify_source;called=[];count=len(self.s.rows('object_revision_registry'))
        def verify(entry,principal,origin,selector,scope,stage):
            result=original(entry,principal,origin,selector,scope,stage)
            if stage=='current':
                called.append(stage);other=sqlite3.connect(self.s.root/'runtime.sqlite')
                try:other.execute('UPDATE activities SET revision=revision+1 WHERE id=?',(self.f.activity,));other.commit()
                finally:other.close()
            return result
        with patch.object(self.o.snapshot_authority,'verify_source',verify),self.assertRaises(Conflict):
            with self.meter().installed(self.s),self.boundary():
                self.s.db.execute('BEGIN')
                try:self.snapshots.fixed(self.entry,self.principal,token,self.scope)
                finally:
                    if self.s.db.in_transaction:self.s.db.execute('ROLLBACK')
        self.assertEqual(called,['current']);self.assertEqual(len(self.s.rows('object_revision_registry')),count)


if __name__=='__main__':unittest.main()
