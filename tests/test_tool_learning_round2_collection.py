"""Actual StrictEngine collection ports share only their local read phase."""
import unittest
from unittest.mock import patch
from digital_life.application.learning.engine import source_scope
from digital_life.domain.contracts import ContractError,Conflict,Forbidden
from digital_life.infrastructure.persistence.tool_learning_readset import current_readset

class CollectionReadBoundaryTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_runtime import StrictEngineEndToEndTests
        fixture=StrictEngineEndToEndTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.f=fixture;self.s=fixture.s;self.strict=fixture.strict;self.scope=source_scope(self.s)
        self.context=self.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(fixture.activity,)).fetchone()[0]
        self.entry,self.principal=self.strict.owners.entry('M14','learn',self.strict._recipient(fixture.activity))
        self.task,self.primary=self.strict._primary(self.entry,self.principal,fixture.activity,self.context,self.scope)
    def features(self):
        # Selection is narrowed only for this port-level test; production
        # FEATURE_TABLES and its complete-input acceptance remain unchanged.
        with patch.object(self.strict,'FEATURE_TABLES',{'identity':('identity_instances',)}):
            return self.strict._features(self.entry,self.principal,self.f.activity,self.context,self.scope,self.task,self.primary)
    def test_actual_features_enters_shared_phase_and_cleans_it_before_return(self):
        phases=[];original=self.strict.runtime.eligibility.check
        def checked(*args,**kwargs):
            phase=current_readset(self.s);self.assertIsNotNone(phase);phases.append(phase)
            return original(*args,**kwargs)
        with patch.object(self.strict.runtime.eligibility,'check',checked),patch.object(self.strict.provider,'generate_fresh',side_effect=AssertionError('collection must not invoke model')):
            features,fields=self.features()
        self.assertTrue(phases);self.assertTrue(features['identity']['records']);self.assertTrue(fields)
        self.assertTrue(all(phase.closed for phase in phases));self.assertIsNone(current_readset(self.s))
    def test_actual_conversation_discovery_enters_and_exits_its_own_phase(self):
        phases=[];original=self.strict.runtime.eligibility.check
        def checked(*args,**kwargs):
            phase=current_readset(self.s);self.assertIsNotNone(phase);phases.append(phase)
            return original(*args,**kwargs)
        with patch.object(self.strict.runtime.eligibility,'check',checked),patch.object(self.strict.provider,'generate_fresh',side_effect=AssertionError('discovery must not invoke model')):
            result=self.strict._conversation(self.entry,self.principal,self.f.activity,self.context,self.primary,self.scope)
        self.assertIsNone(result);self.assertTrue(phases)
        self.assertTrue(all(phase.closed for phase in phases));self.assertIsNone(current_readset(self.s))
    def test_same_connection_change_before_fixed_snapshot_still_blocks_collection(self):
        original=self.strict.owners.snapshots.fixed;phases=[]
        def changed(entry,principal,token,scope):
            phases.append(current_readset(self.s))
            self.s.db.execute('UPDATE identity_instances SET generation=generation+1 WHERE id=?',(self.s.instance_id,))
            return original(entry,principal,token,scope)
        with patch.object(self.strict.owners.snapshots,'fixed',changed),self.assertRaises((Conflict,Forbidden)):
            self.features()
        self.assertTrue(phases);self.assertTrue(all(phase.closed for phase in phases));self.assertIsNone(current_readset(self.s))
    def test_control_stop_during_feature_selection_still_blocks_and_cleans_phase(self):
        original=self.strict._feature_selection;phases=[]
        def stopped(*args,**kwargs):
            phases.append(current_readset(self.s));self.f.control.stop('synthetic collection stop')
            return original(*args,**kwargs)
        with patch.object(self.strict,'_feature_selection',stopped),self.assertRaises((Conflict,Forbidden)):
            self.features()
        self.assertTrue(phases);self.assertTrue(all(phase.closed for phase in phases));self.assertIsNone(current_readset(self.s))

if __name__=='__main__':unittest.main()
