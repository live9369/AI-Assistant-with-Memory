"""Shared facts replay consumed logical rows without false physical charges."""
import unittest
from digital_life.application.learning.eligibility import ref
from digital_life.domain.contracts import utc
from digital_life.domain.tool_learning_resources import DIMENSIONS
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter,logical_observer_required
from digital_life.application.learning.contexts import source_preparation_observer_boundary
from digital_life.infrastructure.persistence.tool_learning_readset import shared_read_boundary,facts

class CachedLogicalRowTests(unittest.TestCase):
    def setUp(self):
        from tests import test_tool_learning_revision_existence as existence_fixture
        fixture=existence_fixture.RevisionExistenceSharingTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.f=fixture;self.s=fixture.s;self.owner=fixture.owner;self.scope=fixture.scope;self.token=fixture.token
    def meter(self):return PhysicalReadMeter({k:10000000 for k in DIMENSIONS},utc(60))
    def test_single_cached_row_notifies_only_on_consumption_without_rebilling(self):
        meter=self.meter();observed=[]
        with meter.installed(self.s),shared_read_boundary(self.s):
            first=list(facts(self.s,'selected_revision',self.token['object']['id'],self.token['revision']))
            before=dict(meter.actual);meter.row_observer=lambda row:observed.append(dict(row))
            cached=facts(self.s,'selected_revision',self.token['object']['id'],self.token['revision'])
            self.assertEqual(observed,[]);actual=next(iter(cached))
            self.assertEqual(actual,first[0]);self.assertEqual(observed,[dict(first[0])])
            for key in ('bytes','scan','items'):self.assertEqual(meter.actual[key],before[key])
    def test_complete_prefix_replays_only_consumed_rows_not_unused_tail(self):
        consumer=ref(self.s,self.s.artifact({'synthetic logical cache consumer':True}))
        for index in range(3):
            target=ref(self.s,self.s.artifact({'synthetic original':index}));token={'object':target,'revision':0,'epoch':0}
            dependency={'target':target,'expected':token,'relation':'read','consumer_purpose':'learn'}
            self.owner.eligibility.register_dependency(self.f.entry,self.f.principal,consumer,dependency,'/field/'+str(index),self.scope)
        meter=self.meter();observed=[]
        with meter.installed(self.s),shared_read_boundary(self.s):
            original=list(facts(self.s,'consumer_dependencies',consumer['id'],64));self.assertEqual(len(original),3)
            before=dict(meter.actual);meter.row_observer=lambda row:observed.append(dict(row))
            cached=facts(self.s,'consumer_dependencies',consumer['id'],2);self.assertFalse(observed)
            next(iter(cached));self.assertEqual(len(observed),1)
            self.assertEqual(list(facts(self.s,'consumer_dependencies',consumer['id'],0)),[]);self.assertEqual(len(observed),1)
            for key in ('bytes','scan','items'):self.assertEqual(meter.actual[key],before[key])
    def test_cached_iterator_cannot_deliver_old_rows_after_phase_exit(self):
        from digital_life.domain.contracts import Conflict
        with shared_read_boundary(self.s):
            list(facts(self.s,'selected_revision',self.token['object']['id'],self.token['revision']))
            old=facts(self.s,'selected_revision',self.token['object']['id'],self.token['revision'])
        with self.assertRaises(Conflict):next(iter(old))
    def test_unknown_observer_cannot_reuse_prepared_or_graph_even_with_busy_attribute(self):
        meter=self.meter()
        with meter.installed(self.s),shared_read_boundary(self.s)as phase:
            graph_key='synthetic fixed graph key';phase.graph_admitted(graph_key);phase.graph_admitted(graph_key);phase.remember_graph(graph_key,'[]',0)
            metadata_key=('synthetic metadata',);phase.remember_prepared_metadata(metadata_key,'{}','fixed-scope')
            self.assertIsNotNone(phase.graph(graph_key));self.assertIsNotNone(phase.prepared_metadata(metadata_key))
            def observer(row):pass
            observer.busy=True;meter.row_observer=observer
            self.assertTrue(logical_observer_required());self.assertIsNone(phase.graph(graph_key));self.assertIsNone(phase.prepared_metadata(metadata_key));self.assertFalse(phase.graph_admitted('new key'))
    def test_only_exact_busy_collector_scope_can_reuse_pure_preparation(self):
        from digital_life.application.learning.contexts import DomainReadCollector
        collector=DomainReadCollector(self.f.f.strict,self.f.entry,self.f.principal,self.scope,set());meter=self.meter()
        with meter.installed(self.s),shared_read_boundary(self.s)as phase:
            phase.remember_prepared_metadata(('fixed',),'{}','scope')
            meter.row_observer=collector.on_row;collector.busy=True
            self.assertTrue(logical_observer_required())
            with source_preparation_observer_boundary(collector):
                self.assertFalse(logical_observer_required());self.assertIsNotNone(phase.prepared_metadata(('fixed',)))
                meter.row_observer=lambda row:None
                self.assertTrue(logical_observer_required());self.assertIsNone(phase.prepared_metadata(('fixed',)))
            self.assertTrue(logical_observer_required())

if __name__=='__main__':unittest.main()
