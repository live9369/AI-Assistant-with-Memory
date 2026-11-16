"""Pure graph rows omit only unused SQL registration columns, not source facts."""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from digital_life.application.learning.eligibility import ToolLearningEligibility,scope_key
from digital_life.application.learning.engine import _dependency
from digital_life.domain.contracts import ContractError,Conflict,utc
from digital_life.domain.tool_learning_resources import DIMENSIONS
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
from digital_life.infrastructure.persistence.tool_learning_readset import dependency_materials,facts,shared_read_boundary
from evaluation.tool_learning_performance_reference import reference_upstream
from tests import test_tool_learning_round2_graph as graph_fixture


class DependencyMaterialTests(unittest.TestCase):
    def setUp(self):
        self.f=graph_fixture.SharedSourceGraphTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.c=self.f.checker;self.token=self.f.token;self.scope=self.f.scope;self.consumer=self.f.refs[0]['id']
    def meter(self):return PhysicalReadMeter({k:100000000 for k in DIMENSIONS},utc(60))
    def test_real_projection_bytes_keep_every_binding_and_row(self):
        summaries=[]
        for projected in (False,True):
            meter=self.meter()
            with meter.installed(self.s):
                rows=list(dependency_materials(self.s,self.consumer,100)if projected else facts(self.s,'consumer_dependencies',self.consumer,100))
            summaries.append({'rows':[dict(v)for v in rows],'actual':dict(meter.actual)})
        before,after=summaries
        for full,material in zip(before['rows'],after['rows']):
            self.assertEqual(set(full)-set(material),{'recorded_at','schema_revision'})
            self.assertEqual(material,{k:v for k,v in full.items()if k not in ('recorded_at','schema_revision')})
        self.assertEqual(len(before['rows']),len(after['rows']));self.assertEqual(before['actual']['scan'],after['actual']['scan'])
        self.assertLess(after['actual']['bytes'],before['actual']['bytes'])
        capture=os.environ.get('DIGITAL_LIFE_CAPTURE_DEPENDENCY_MATERIAL_DIFF')
        if capture:
            out=Path(capture);out.mkdir(parents=True,exist_ok=False)
            (out/'result.json').write_text(json.dumps({'passed':True,'summaries':summaries,'real_models_called':False,'formal_instance_accessed':False},indent=2)+'\n')
    def test_no_meter_and_original_full_api_keep_every_column(self):
        rows=list(dependency_materials(self.s,self.consumer,100));self.assertTrue(rows)
        self.assertTrue(all('recorded_at'in row.keys()and'schema_revision'in row.keys()for row in rows))
        with self.meter().installed(self.s):rows=list(facts(self.s,'consumer_dependencies',self.consumer,100))
        self.assertTrue(all('recorded_at'in row.keys()and'schema_revision'in row.keys()for row in rows))
    def test_observer_switch_uses_separate_complete_row_cache_and_sequence(self):
        original=[dict(v)for v in facts(self.s,'consumer_dependencies',self.consumer,100)]
        seen=[];meter=self.meter()
        with meter.installed(self.s),shared_read_boundary(self.s)as phase:
            material=list(dependency_materials(self.s,self.consumer,100));self.assertNotIn('recorded_at',material[0].keys())
            meter.row_observer=lambda row:seen.append(dict(row))
            rows=list(dependency_materials(self.s,self.consumer,100));again=list(dependency_materials(self.s,self.consumer,100))
            self.assertEqual([dict(v)for v in rows],original);self.assertEqual([dict(v)for v in again],original)
            self.assertEqual(seen,original*2)
            self.assertTrue(any(k[0]=='consumer_dependency_materials'for k in phase.cache));self.assertTrue(any(k[0]=='consumer_dependencies'for k in phase.cache))
    def test_graph_cycles_read_delete_paths_and_logical_budget_equal_reference(self):
        before_budget={'remaining':128};before=reference_upstream(self.c,self.token,self.scope,before_budget)
        with self.meter().installed(self.s),shared_read_boundary(self.s):
            after_budget={'remaining':128};after=self.c._upstream_current(self.token,self.scope,after_budget)
        self.assertEqual(after,before);self.assertEqual(after_budget,before_budget);self.assertTrue(any('delete'in row[3]for row in after))
    def test_logical_node_and_row_failure_still_spends_same_budget(self):
        for nodes,rows,remaining in ((2,128,128),(64,2,2),(64,128,0),(64,128,1),(64,128,4)):
            checker=ToolLearningEligibility(self.s,self.f.authority,max_nodes=nodes,max_rows=rows);outcomes=[]
            for method in (reference_upstream,ToolLearningEligibility._upstream_current):
                budget={'remaining':remaining}
                with self.meter().installed(self.s),shared_read_boundary(self.s):
                    try:method(checker,self.token,self.scope,budget)
                    except ContractError as error:outcomes.append((type(error).__name__,str(error),budget))
                    else:self.fail('logical graph cap not enforced')
            self.assertEqual(outcomes[0],outcomes[1])
    def test_metadata_scope_epoch_expected_and_row_binding_are_unchanged(self):
        full=list(facts(self.s,'consumer_dependencies',self.consumer,100))
        with self.meter().installed(self.s),shared_read_boundary(self.s):
            material=list(dependency_materials(self.s,self.consumer,100))
            for before,after in zip(full,material):self.assertEqual(self.c._metadata(before),self.c._metadata(after))
            first=self.c._metadata(material[0]);self.assertEqual(first['scope'],self.scope)
            for column,value in (('source_revision_id','f'*32),('source_ref_id',self.f.refs[0]['id']),('expected_epoch',999)):
                outcomes=[]
                for row in (full[0],material[0]):
                    bad=dict(row);bad[column]=value
                    try:self.c._metadata(bad)
                    except ContractError as error:outcomes.append((type(error).__name__,str(error)))
                    else:self.fail('wrong dependency binding accepted')
                self.assertEqual(outcomes[0],outcomes[1])
    def test_metadata_artifact_tamper_cannot_hide_behind_projected_material(self):
        path=None;prior=None
        try:
            with self.assertRaises(Conflict):
                with self.meter().installed(self.s),shared_read_boundary(self.s):
                    material=list(dependency_materials(self.s,self.consumer,100))[0];self.c._metadata(material)
                    location=self.s.row('artifacts',material['metadata_artifact_id']);path=self.s.root/'blobs'/location['storage_ref'];prior=path.read_bytes()
                    path.write_bytes(prior+b' ')
                    with self.assertRaises(ContractError):self.c._metadata(material)
        finally:
            if path is not None:path.write_bytes(prior)
    def test_complete_prefix_reuse_and_partial_iteration_are_bounded(self):
        meter=self.meter();sql=[];self.s.db.set_trace_callback(sql.append)
        with meter.installed(self.s),shared_read_boundary(self.s):
            first=list(dependency_materials(self.s,self.consumer,1));full=list(dependency_materials(self.s,self.consumer,100));before=dict(meter.actual)
            self.assertEqual(list(dependency_materials(self.s,self.consumer,2)),full[:2]);self.assertEqual(list(dependency_materials(self.s,self.consumer,101)),full)
            self.assertEqual(meter.actual,before);self.assertEqual(len(first),1)
            self.assertEqual(sum(q.startswith('SELECT id,instance_id,consumer_ref_id,')for q in sql),2)
        with self.meter().installed(self.s)as meter,shared_read_boundary(self.s):
            before=meter.actual['scan'];iterator=dependency_materials(self.s,self.consumer,100);next(iterator)
            self.assertEqual(meter.actual['scan']-before,1);iterator.close()
    def test_same_connection_append_then_rollback_does_not_retain_phantom_material(self):
        with self.meter().installed(self.s)as meter,shared_read_boundary(self.s):
            before=[dict(v)for v in dependency_materials(self.s,self.consumer,100)];usage=dict(meter.actual)
            with self.assertRaisesRegex(RuntimeError,'rollback'):
                with self.s.tx():
                    _dependency(self.s,self.f.refs[0],{'object':self.f.refs[1],'revision':0,'epoch':0},self.scope,'read','/temporary-projected-edge','learn')
                    self.assertEqual(len(list(dependency_materials(self.s,self.consumer,100))),len(before)+1);raise RuntimeError('rollback')
            self.assertEqual([dict(v)for v in dependency_materials(self.s,self.consumer,100)],before);self.assertGreater(meter.actual['scan'],usage['scan'])
    def test_current_epoch_is_rechecked_after_same_connection_change(self):
        principal=deepcopy(self.f.fixture.request['principal'])
        with self.meter().installed(self.s),shared_read_boundary(self.s):
            self.c._check('synthetic-projection',principal,self.token,self.scope,'learn',principal['recipient'],'first')
            with self.s.tx():self.s.insert('tl_source_epoch',source_ref_id=self.token['object']['id'],scope_key=scope_key(self.scope),scope_artifact_id=self.s.artifact(self.scope),epoch=1,row_revision=0)
            with self.assertRaisesRegex(Conflict,'epoch is stale'):self.c._check('synthetic-projection',principal,self.token,self.scope,'learn',principal['recipient'],'second')


if __name__=='__main__':unittest.main()
