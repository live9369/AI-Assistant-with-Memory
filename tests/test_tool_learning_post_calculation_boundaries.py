"""Fresh calculation-result/live material checks on synthetic stores only."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
import sqlite3
import unittest
from unittest.mock import patch

from digital_life.application.learning.contexts import (
    calculation_read_boundary,calculated_retention_read_boundary,live_binding_read_boundary)
from digital_life.application.learning.engine import source_scope
from digital_life.application.learning.eligibility import ref
from digital_life.domain.contracts import Conflict,Forbidden
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter,logical_observer_required
from digital_life.infrastructure.persistence.tool_learning_readset import current_readset,facts
from tests import test_tool_learning_runtime as fixture


class PostCalculationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.StrictEngineEndToEndTests();self.f.enable_features=False;self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.e=self.f.strict;self.scope=source_scope(self.s)
        self.entry,self.principal=self.e.owners.entry('M14','learn')
        self.config=self.s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()[0]
    def meter(self):
        return PhysicalReadMeter(self.e._read_slice(self.f.activity,.5),self.s.row('activities',self.f.activity)['deadline'])
    def check(self):
        token={'object':ref(self.s,self.config),'revision':0,'epoch':0}
        return self.e.runtime.eligibility._check(self.entry,self.principal,token,self.scope,'learn',self.principal['recipient'],'post-calculation-per-use')
    def capture(self):
        return self.e.owners.snapshots.capture(self.entry,self.principal,ref(self.s,self.f.activity),['id'],self.scope)
    def test_each_post_boundary_is_fresh_and_closes_before_next_boundary(self):
        source=self.e.owners.source;prior={'outer marker'};source._verified=prior;phases=[]
        try:
            with self.meter().installed(self.s):
                for boundary in (calculation_read_boundary,calculated_retention_read_boundary,live_binding_read_boundary):
                    with boundary(self.e):
                        phase=current_readset(self.s);self.assertIsNotNone(phase);phases.append(phase)
                        self.assertIsNone(source._verified);list(facts(self.s,'source_kind',self.config))
                    self.assertTrue(phase.closed);self.assertIsNone(current_readset(self.s));self.assertIs(source._verified,prior)
            self.assertEqual(len({id(v.stamp)for v in phases}),3)
        finally:source._verified=None
    def test_permissions_versions_and_unknown_observer_still_run_on_every_use(self):
        source=self.e.owners.source
        for boundary in (calculated_retention_read_boundary,live_binding_read_boundary):
            meter=self.meter();seen=[]
            with meter.installed(self.s),boundary(self.e):
                meter.row_observer=seen.append;self.assertTrue(logical_observer_required())
                with patch.object(self.e.owners,'source_access',wraps=self.e.owners.source_access)as access,patch.object(source,'verify_version',wraps=source.verify_version)as versions:
                    self.check();self.check()
                self.assertEqual(len([v for v in access.call_args_list if v.args[2]['id']==self.config]),2)
                self.assertEqual(len([v for v in versions.call_args_list if v.args[2]['object']['id']==self.config]),2)
                self.assertTrue(seen);self.assertTrue(logical_observer_required())
    def test_unknown_snapshot_or_assembly_authority_does_not_share(self):
        owners=self.e.owners
        for name in ('snapshot_authority','runtime'):
            prior=getattr(owners,name);setattr(owners,name,SimpleNamespace())
            try:
                with self.meter().installed(self.s),live_binding_read_boundary(self.e):self.assertIsNone(current_readset(self.s))
            finally:setattr(owners,name,prior)
    def test_exception_restores_outer_state(self):
        source=self.e.owners.source;prior={'outer marker'};source._verified=prior
        try:
            for boundary in (calculated_retention_read_boundary,live_binding_read_boundary):
                with self.assertRaisesRegex(RuntimeError,'synthetic'):
                    with self.meter().installed(self.s),boundary(self.e):
                        phase=current_readset(self.s);raise RuntimeError('synthetic')
                self.assertTrue(phase.closed);self.assertIsNone(current_readset(self.s));self.assertIs(source._verified,prior)
        finally:source._verified=None
    def test_actual_snapshot_authority_replaced_without_owner_marker_does_not_share(self):
        snapshots=self.e.owners.snapshots;prior=snapshots.authority
        snapshots.authority=SimpleNamespace()
        try:
            with self.meter().installed(self.s),live_binding_read_boundary(self.e):self.assertIsNone(current_readset(self.s))
        finally:snapshots.authority=prior
    def test_actual_runtime_eligibility_authority_replaced_does_not_share(self):
        eligibility=self.e.runtime.eligibility;prior=eligibility.authority;eligibility.authority=SimpleNamespace()
        try:
            for boundary in (calculated_retention_read_boundary,live_binding_read_boundary):
                with self.meter().installed(self.s),boundary(self.e):self.assertIsNone(current_readset(self.s))
        finally:eligibility.authority=prior
    def test_same_connection_write_invalidates_facts_without_budget_refund(self):
        with self.meter().installed(self.s)as meter,live_binding_read_boundary(self.e):
            phase=current_readset(self.s);before=list(facts(self.s,'source_kind',self.config));generation=phase.generation;usage=dict(meter.actual)
            with self.s.tx():self.s.db.execute('UPDATE activities SET revision=revision+1 WHERE instance_id=? AND id=?',(self.s.instance_id,self.f.activity))
            self.assertEqual(list(facts(self.s,'source_kind',self.config)),before)
            self.assertGreater(phase.generation,generation);self.assertGreater(meter.actual['scan'],usage['scan'])
    def test_foreign_commit_rejected_in_both_post_boundaries(self):
        self.s.db.execute('PRAGMA journal_mode=WAL')
        for boundary in (calculated_retention_read_boundary,live_binding_read_boundary):
            with self.assertRaisesRegex(Conflict,'outside phase'):
                with self.meter().installed(self.s),boundary(self.e):
                    self.check();other=sqlite3.connect(self.s.root/'runtime.sqlite')
                    try:other.execute('UPDATE activities SET revision=revision+1 WHERE id=?',(self.f.activity,));other.commit()
                    finally:other.close()
                    self.check()
    def test_capture_commit_source_change_rejects_and_rolls_back_snapshot(self):
        original=self.e.owners.snapshot_authority.verify_capture
        revision=self.s.row('activities',self.f.activity)['revision'];count=len(self.s.rows('object_revision_registry'));called=[]
        def verify(entry,principal,snapshot,stage):
            if stage=='commit':
                called.append(stage);self.s.db.execute('UPDATE activities SET revision=revision+1 WHERE id=?',(self.f.activity,))
            return original(entry,principal,snapshot,stage)
        with patch.object(self.e.owners.snapshot_authority,'verify_capture',verify),self.assertRaises(Conflict):
            with self.meter().installed(self.s),live_binding_read_boundary(self.e):self.capture()
        self.assertEqual(called,['commit']);self.assertEqual(self.s.row('activities',self.f.activity)['revision'],revision)
        self.assertEqual(len(self.s.rows('object_revision_registry')),count)
    def test_capture_commit_stop_rejects_before_snapshot_commit(self):
        original=self.e.owners.snapshot_authority.verify_capture;count=len(self.s.rows('object_revision_registry'));called=[]
        def verify(entry,principal,snapshot,stage):
            if stage=='commit':called.append(stage);self.f.control.stop('synthetic live binding stop')
            return original(entry,principal,snapshot,stage)
        with patch.object(self.e.owners.snapshot_authority,'verify_capture',verify),self.assertRaises((Conflict,Forbidden)):
            with self.meter().installed(self.s),live_binding_read_boundary(self.e):self.capture()
        self.assertEqual(called,['commit']);self.assertEqual(len(self.s.rows('object_revision_registry')),count)
    def test_capture_commit_configuration_file_change_rejects_before_commit(self):
        cfg=self.s.row('configuration_versions',self.config);artifact=self.s.row('artifacts',cfg['artifact_ref'])
        path=self.s.root/'blobs'/artifact['storage_ref'];prior=path.read_bytes();count=len(self.s.rows('object_revision_registry'));called=[]
        original=self.e.owners.snapshot_authority.verify_capture
        def verify(entry,principal,snapshot,stage):
            if stage=='commit':called.append(stage);path.write_bytes(prior+b' ')
            return original(entry,principal,snapshot,stage)
        try:
            with patch.object(self.e.owners.snapshot_authority,'verify_capture',verify),self.assertRaises((Conflict,Forbidden)):
                with self.meter().installed(self.s),live_binding_read_boundary(self.e):self.capture()
            self.assertEqual(called,['commit']);self.assertEqual(len(self.s.rows('object_revision_registry')),count)
        finally:path.write_bytes(prior)


if __name__=='__main__':unittest.main()
