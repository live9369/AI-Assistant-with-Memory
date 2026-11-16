"""Real entry/exit probes remain; only fixed readonly interior reuses stat."""
from collections import Counter
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import Conflict,Forbidden
from digital_life.application.learning import eligibility as eligibility
from digital_life.infrastructure.persistence import tool_learning_readset as readset
from tests import test_tool_learning_certified_input as fixture

class CheckFileSignatureTests(unittest.TestCase):
    def setUp(self):
        self.c=fixture.CertifiedInputTests();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.s=self.c.s;self.e=self.c.e;self.service=self.e.runtime.eligibility
        self.row=self.s.rows('tl_dependency')[0];artifact=self.s.row('artifacts',self.row['metadata_artifact_id'])
        self.path=self.s.root/'blobs'/artifact['storage_ref']
    def boundary(self):return self.e.owners.source.verification_boundary()
    def check(self):return self.service._check(self.c.entry,self.c.principal,self.c.token,self.c.scope,'learn',self.c.principal['recipient'],'file-signature-check')
    def warm(self):
        for row in self.s.rows('tl_dependency'):self.service._metadata(row)
    def test_entry_and_exit_each_really_stat_while_known_interior_reuses_tracked_path(self):
        counts=Counter();original=readset._signature;mint=eligibility._mint_signature_check;leases=[]
        def signature(path):counts[Path(path)]+=1;return original(path)
        def minted(service,phase):value=mint(service,phase);leases.append(value is not None);return value
        with self.c.meter().installed(self.s),self.boundary(),patch.object(readset,'_signature',new=signature),patch.object(eligibility,'_mint_signature_check',new=minted):
            self.warm();counts.clear();result=self.check()
            self.assertTrue(result['qualified']);self.assertEqual(counts[self.path],2);self.assertEqual(leases,[True])
            phase=readset.current_readset(self.s);self.assertIsNone(phase.signature_check);self.assertEqual(phase.check_depth,0)
    def test_middle_file_change_is_rejected_by_real_exit_probe_before_qualified_return(self):
        original=readset.PhaseReadSet._tracked_signature_current;prior=self.path.read_bytes();changed=[]
        def current(phase,path):
            value=original(phase,path)
            if type(path)is str:path=phase.root/'blobs'/path
            if value and not changed:
                changed.append((path,path.read_bytes()));path.write_bytes(changed[0][1]+b' ')
            return value
        try:
            with self.assertRaises(Conflict):
                with self.c.meter().installed(self.s),self.boundary():
                    self.warm()
                    with patch.object(readset.PhaseReadSet,'_tracked_signature_current',new=current):self.check()
            self.assertEqual(len(changed),1)
        finally:
            for path,raw in changed:path.write_bytes(raw)
    def test_foreign_commit_during_known_body_is_rejected_at_exit(self):
        foreign=sqlite3.connect(self.s.root/'runtime.sqlite',isolation_level=None);foreign.execute('PRAGMA journal_mode=WAL')
        original=readset.PhaseReadSet._tracked_signature_current;changed=[]
        def current(phase,path):
            value=original(phase,path)
            if type(path)is str:path=phase.root/'blobs'/path
            if value and not changed:
                changed.append(True);foreign.execute('UPDATE activities SET revision=revision+1 WHERE id=?',(self.c.f.activity,))
            return value
        try:
            with self.assertRaises(Conflict):
                with self.c.meter().installed(self.s),self.boundary():
                    self.warm()
                    with patch.object(readset.PhaseReadSet,'_tracked_signature_current',new=current):self.check()
            self.assertEqual(changed,[True])
        finally:foreign.close()
    def test_zero_row_write_config_and_rollback_each_break_existing_signature_lease(self):
        for action in ('zero_write','configuration','rollback'):
            with self.subTest(action=action),self.c.meter().installed(self.s),self.boundary():
                self.warm();phase=readset.current_readset(self.s);phase.checkpoint();phase.check_depth=1
                phase.signature_check=eligibility._mint_signature_check(self.service,phase)
                self.assertIsNotNone(phase.signature_check);self.assertTrue(phase._tracked_signature_current(self.path))
                try:
                    if action=='zero_write':self.s.db.execute('UPDATE activities SET revision=revision WHERE id=?',('f'*32,))
                    elif action=='configuration':self.s.db.create_function('synthetic_signature_config',0,lambda:1)
                    else:self.s.db.execute('BEGIN');self.s.db.rollback()
                    self.assertFalse(phase._tracked_signature_current(self.path))
                finally:phase.signature_check=None;phase.check_depth=0
    def test_native_callback_inside_live_check_never_uses_signature_lease(self):
        from digital_life.application.learning.eligibility import ToolLearningEligibility
        import sys
        observed=[];entered=[False];target=ToolLearningEligibility._check_current.__code__;prior=sys.getprofile()
        def callback():
            phase=readset.current_readset(self.s);observed.append(phase._tracked_signature_current(self.path));return 1
        self.s.db.create_function('signature_callback_test',0,callback)
        def profile(frame,event,arg):
            if event=='call'and frame.f_code is target and not entered[0]:
                entered[0]=True;phase=readset.current_readset(self.s);self.assertIsNotNone(phase.signature_check)
                self.s.db.execute('SELECT signature_callback_test()').fetchone()
        with self.c.meter().installed(self.s),self.boundary():
            self.warm();sys.setprofile(profile)
            try:self.check()
            finally:sys.setprofile(prior)
        self.assertEqual(observed,[False])
    def test_early_location_membership_never_accepts_invalid_unknown_or_new_paths(self):
        from digital_life.domain.contracts import ContractError
        with self.s.tx():key=self.s.artifact({'new untracked location':True})
        location=self.s.row('artifacts',key)['storage_ref'];original=readset._signature;calls=[]
        def signature(path):calls.append(path);return original(path)
        with self.c.meter().installed(self.s),self.boundary():
            self.warm();phase=readset.current_readset(self.s);phase.checkpoint();phase.check_depth=1
            phase.signature_check=eligibility._mint_signature_check(self.service,phase)
            self.assertIsNotNone(phase.signature_check)
            try:
                for invalid in ('../outside','a'*63,'z'*64,123):
                    with self.assertRaises(ContractError):phase.track_location(invalid)
                class StringSubclass(str):pass
                with self.assertRaises(ContractError):phase.track_location(StringSubclass(self.path.name))
                with patch.object(readset,'_signature',new=signature):
                    phase.track_location(location);phase.track_location(location)
                self.assertEqual(calls,[self.s.root/'blobs'/location]*2)
            finally:phase.signature_check=None;phase.check_depth=0
    def test_exception_and_mint_failure_restore_signature_scope_and_depth(self):
        with self.c.meter().installed(self.s),self.boundary():
            phase=readset.current_readset(self.s)
            with self.assertRaises(Forbidden):self.service._check(self.c.entry,self.c.principal,self.c.token,self.c.scope,'history_audit',self.c.principal['recipient'],'invalid-purpose')
            self.assertIsNone(phase.signature_check);self.assertEqual(phase.check_depth,0)
            with patch.object(eligibility,'_mint_signature_check',side_effect=RuntimeError('synthetic mint error')):
                with self.assertRaisesRegex(RuntimeError,'synthetic mint error'):self.check()
            self.assertIsNone(phase.signature_check);self.assertEqual(phase.check_depth,0)
