"""PF05 source preparation sharing retains exact paths and live checks."""
import copy
import unittest
from unittest.mock import patch
from digital_life.application.learning.eligibility import ToolLearningEligibility,EligibilityAuthority,ref
from digital_life.application.learning.engine import _dependency,source_scope
from digital_life.domain.contracts import ContractError,Conflict
from digital_life.infrastructure.persistence.tool_learning_readset import shared_read_boundary,facts,checkpoint
from evaluation.tool_learning_performance_reference import reference_upstream

class CountingAuthority(EligibilityAuthority):
    def __init__(self):self.calls=[]
    def verify_version(self,*args):self.calls.append(('version',copy.deepcopy(args)))
    def verify(self,*args):self.calls.append(('source',copy.deepcopy(args)))

class SharedSourceGraphTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_work import WorkTests
        fixture=WorkTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.fixture=fixture;self.s=fixture.s;self.scope=source_scope(self.s)
        with self.s.tx():
            ids=[self.s.artifact({'shared original':'identical text','object':i})for i in range(4)]
            self.refs=[ref(self.s,key)for key in ids]
            for index,(left,right,relation)in enumerate(((0,1,'read'),(0,2,'read'),(0,1,'delete'),(1,3,'read'),(2,3,'read'),(3,0,'delete'))):
                _dependency(self.s,self.refs[left],{'object':self.refs[right],'revision':0,'epoch':0},self.scope,relation,'/edge/'+str(index),'learn')
        self.token={'object':self.refs[0],'revision':0,'epoch':0}
        self.authority=CountingAuthority();self.checker=ToolLearningEligibility(self.s,self.authority,max_nodes=64,max_rows=128)
    def graph(self,checker=None,token=None,scope=None,budget=None):
        return (checker or self.checker)._upstream(token or self.token,scope or self.scope,budget if budget is not None else {'remaining':128})
    def test_same_library_exact_reference_paths_cycles_and_logical_budget_on_hit(self):
        old_budget={'remaining':128};old=reference_upstream(self.checker,self.token,self.scope,old_budget)
        with shared_read_boundary(self.s)as phase,patch.object(self.checker,'_upstream_current',wraps=self.checker._upstream_current)as actual:
            for _ in range(3):
                budget={'remaining':128};new=self.graph(budget=budget)
                self.assertEqual(new,old);self.assertEqual(budget,old_budget)
            self.assertEqual(actual.call_count,2);self.assertEqual(len(phase.graphs),1)
            self.assertTrue(any('delete'in row[3]for row in new))
            self.assertTrue(all(type(row)is tuple and type(row[3])is tuple for row in new))
    def test_mutating_caller_tree_does_not_mutate_prepared_graph(self):
        with shared_read_boundary(self.s):
            expected=self.graph();out=self.graph()
            out[0][1]['conditions']['value']['interpretation']='mutated caller'
            out[-1][2]['object']['kind']='mutated caller kind'
            out.append(('extra',{},None,()))
            self.assertEqual(self.graph(),expected)
    def test_full_token_scope_and_checker_limits_do_not_alias(self):
        with shared_read_boundary(self.s)as phase:
            self.graph();self.graph()
            different_scope=copy.deepcopy(self.scope);different_scope['property']='other source property'
            self.graph(scope=different_scope);self.graph(scope=different_scope)
            different_version=copy.deepcopy(self.token);different_version['revision']=1
            self.graph(token=different_version);self.graph(token=different_version)
            alternate=ToolLearningEligibility(self.s,self.authority,max_nodes=65,max_rows=128);self.graph(checker=alternate);self.graph(checker=alternate)
            self.assertEqual(len(phase.graphs),4)
    def test_undersized_budget_falls_back_and_matches_old_error_and_spending(self):
        with shared_read_boundary(self.s):
            self.graph()
            for remaining in (0,1,2,4):
                outcomes=[]
                for method in (reference_upstream,ToolLearningEligibility._upstream):
                    budget={'remaining':remaining}
                    try:method(self.checker,self.token,self.scope,budget)
                    except ContractError as error:outcomes.append((type(error).__name__,str(error),dict(budget)))
                    else:self.fail('original logical row cap not enforced')
                self.assertEqual(outcomes[0],outcomes[1])
    def test_node_and_row_failure_categories_are_unchanged_and_not_memoized(self):
        for nodes,rows in ((2,128),(64,2)):
            checker=ToolLearningEligibility(self.s,self.authority,max_nodes=nodes,max_rows=rows)
            with shared_read_boundary(self.s)as phase:
                outcomes=[]
                for method in (reference_upstream,ToolLearningEligibility._upstream):
                    budget={'remaining':rows}
                    try:method(checker,self.token,self.scope,budget)
                    except ContractError as error:outcomes.append((type(error).__name__,str(error),dict(budget)))
                    else:self.fail('bounded graph accepted unexpectedly')
                self.assertEqual(outcomes[0],outcomes[1]);self.assertFalse(phase.graphs)
    def test_graph_hit_keeps_every_authority_check_and_consumer_identity(self):
        principal=copy.deepcopy(self.fixture.request['principal'])
        with shared_read_boundary(self.s)as phase:
            self.checker.check('synthetic-source',principal,self.token,self.scope,'learn',principal['recipient'],'same-stage')
            first=len(self.authority.calls)
            self.checker.check('synthetic-source',principal,self.token,self.scope,'learn',principal['recipient'],'same-stage')
            self.assertEqual(len(self.authority.calls),first*2)
            self.assertTrue(phase.graphs)
            other=copy.deepcopy(principal);other['recipient']=ref(self.s,self.fixture.f.expected['controller'])
            self.checker.check('synthetic-source',other,self.token,self.scope,'learn',other['recipient'],'same-stage')
            self.assertEqual(len(self.authority.calls),first*3)
            self.assertEqual(self.authority.calls[-1][1][1]['recipient'],other['recipient'])
    def test_own_write_clears_graph_generation_and_preserves_valid_file_tracking(self):
        with shared_read_boundary(self.s)as phase:
            self.graph();self.graph();self.assertTrue(phase.graphs);generation=phase.generation
            with self.s.tx():self.s.db.execute('UPDATE activities SET state=state WHERE id=?',(self.fixture.source_activity,))
            self.assertGreater(phase.generation,generation);self.assertFalse(phase.graphs)
            self.assertTrue(phase.blobs);self.graph();self.graph();self.assertTrue(phase.graphs)
        self.assertFalse(phase.graphs);self.assertEqual(phase.bytes,0)
    def test_failure_during_metadata_never_saves_partial_graph(self):
        with shared_read_boundary(self.s)as phase:
            with patch.object(self.checker,'_metadata',side_effect=ContractError('synthetic partial failure')):
                with self.assertRaisesRegex(ContractError,'partial failure'):self.graph()
            self.assertFalse(phase.graphs)
            self.graph();self.graph();self.assertTrue(phase.graphs)
    def test_graph_and_fact_encoded_storage_share_one_bounded_account(self):
        with shared_read_boundary(self.s)as phase:
            self.graph()
            self.assertEqual(phase.bytes,sum(phase.fact_sizes.values())+sum(phase.graph_sizes.values())+sum(phase.prepared_sizes.values())+sum(phase.admission_sizes.values()))
            self.assertLessEqual(phase.bytes+phase.blob_bytes,phase.max_bytes)
            self.assertLessEqual(phase.entry_count(),phase.max_keys)
            while phase.entry_count():phase.evict_one()
            self.assertEqual(phase.bytes,0)
    def test_invalid_json_scope_cannot_alias_prepared_graph(self):
        valid=copy.deepcopy(self.scope);valid['conditions']['value']={'1':'same serialized key'}
        with shared_read_boundary(self.s):
            self.graph(scope=valid)
            invalid=copy.deepcopy(valid);invalid['conditions']['value']={1:'same serialized key'}
            with self.assertRaises(ContractError):self.graph(scope=invalid)
    def test_metadata_cache_after_same_connection_revision_insert_is_rechecked_in_and_outside_phase(self):
        from contextlib import nullcontext
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
        from digital_life.domain.tool_learning_resources import DIMENSIONS
        from digital_life.domain.contracts import utc,identifier
        for inside_phase in (False,True):
            # Distinct rows preserve the untouched original graph fixture.
            with self.s.tx():
                left=ref(self.s,self.s.artifact({'consumer':inside_phase}))
                right=ref(self.s,self.s.artifact({'source':inside_phase}))
                _dependency(self.s,left,{'object':right,'revision':0,'epoch':0},self.scope,'read','/dynamic-proof','learn')
            row=self.s.db.execute('SELECT * FROM tl_dependency WHERE consumer_ref_id=?',(left['id'],)).fetchone()
            meter=PhysicalReadMeter({k:100000000 for k in DIMENSIONS},utc(60))
            with meter.installed(self.s),shared_read_boundary(self.s)if inside_phase else nullcontext():
                self.checker._metadata(row)
                with self.s.tx():
                    self.s.db.execute('INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind)VALUES(?,?,?,?,?)',(identifier(),self.s.instance_id,right['id'],0,'artifacts'))
                with self.assertRaisesRegex(ContractError,'projection mismatch'):self.checker._metadata(row)
    def test_metadata_hit_rechecks_current_reference_and_revision_projection(self):
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
        from digital_life.domain.tool_learning_resources import DIMENSIONS
        from digital_life.domain.contracts import utc
        import digital_life.infrastructure.persistence.tool_learning_readset as readset
        row=self.s.db.execute('SELECT * FROM tl_dependency WHERE consumer_ref_id=? ORDER BY id',(self.refs[0]['id'],)).fetchone()
        meter=PhysicalReadMeter({k:100000000 for k in DIMENSIONS},utc(60))
        with meter.installed(self.s),shared_read_boundary(self.s):
            self.checker._metadata(row)
            with self.s.tx():self.s.db.execute('UPDATE activities SET state=state WHERE id=?',(self.fixture.source_activity,))
            with patch.object(self.checker.artifacts,'validate_ref',side_effect=ContractError('synthetic changed reference')):
                with self.assertRaisesRegex(ContractError,'changed reference'):self.checker._metadata(row)
            original=readset.facts
            def changed_projection(store,name,*parameters):
                if name=='selected_revision':return [('synthetic wrong revision projection',)]
                return original(store,name,*parameters)
            with patch.object(readset,'facts',changed_projection):
                with self.assertRaisesRegex(ContractError,'projection mismatch'):self.checker._metadata(row)
    def test_first_root_demand_does_not_encode_whole_graph(self):
        with shared_read_boundary(self.s)as phase,patch.object(phase,'remember_graph',wraps=phase.remember_graph)as save:
            self.graph();self.assertEqual(save.call_count,0);self.assertFalse(phase.graphs);self.assertTrue(phase.admissions)
            self.graph();self.assertEqual(save.call_count,1);self.assertTrue(phase.graphs)
    def test_shared_node_preparation_reuses_mapping_and_scope_key_not_authorization(self):
        import digital_life.application.learning.eligibility as eligibility
        row=self.s.db.execute('SELECT * FROM tl_dependency WHERE consumer_ref_id=? ORDER BY id',(self.refs[0]['id'],)).fetchone()
        with shared_read_boundary(self.s)as phase,patch.object(self.checker.artifacts,'validate_ref',wraps=self.checker.artifacts.validate_ref)as mapping,patch.object(eligibility,'scope_key',wraps=eligibility.scope_key)as scope:
            first,first_key=self.checker._metadata(row,True);calls=mapping.call_count;keys=scope.call_count
            second,second_key=self.checker._metadata(row,True)
            self.assertEqual(first,second);self.assertEqual(first_key,second_key)
            # Prepared JSON/Scope is shared; consumer and target references
            # remain current checks on every use, including a prepared hit.
            self.assertEqual(calls,2)
            self.assertEqual(mapping.call_count,2*calls);self.assertEqual(scope.call_count,keys)
            second['scope']['property']='caller mutated'
            self.assertEqual(self.checker._metadata(row)['scope'],first['scope'])
            self.assertTrue(phase.prepared)
            with patch.object(self.checker.artifacts,'validate_ref',side_effect=ContractError('current prepared reference rejected')):
                with self.assertRaisesRegex(ContractError,'current prepared reference rejected'):
                    self.checker._metadata(row,True)
            current_calls=mapping.call_count
            with self.s.tx():self.s.db.execute('UPDATE activities SET state=state WHERE id=?',(self.fixture.source_activity,))
            self.checker._metadata(row,True);self.assertEqual(mapping.call_count,current_calls+calls);self.assertGreater(scope.call_count,keys)
    def test_same_connection_artifact_mapping_change_cannot_reuse_old_json(self):
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
        from digital_life.domain.tool_learning_resources import DIMENSIONS
        from digital_life.domain.contracts import utc
        row=self.s.db.execute('SELECT * FROM tl_dependency WHERE consumer_ref_id=? ORDER BY id',(self.refs[0]['id'],)).fetchone()
        meter=PhysicalReadMeter({k:100000000 for k in DIMENSIONS},utc(60))
        with meter.installed(self.s),shared_read_boundary(self.s):
            original=self.checker._metadata(row)
            changed=copy.deepcopy(original);changed['scope']['property']='new hash new source scope'
            for value in (changed,{'contract':'invalid changed metadata'}):
                replacement=self.s.artifact(value);mapping=self.s.row('artifacts',replacement)
                with self.s.tx():
                    self.s.db.execute('UPDATE artifacts SET hash=?,size=?,media_type=?,storage_ref=? WHERE id=?',(mapping['hash'],mapping['size'],mapping['media_type'],mapping['storage_ref'],row['metadata_artifact_id']))
                if value is changed:self.assertEqual(self.checker._metadata(row)['scope']['property'],'new hash new source scope')
                else:
                    with self.assertRaises(ContractError):self.checker._metadata(row)
    def test_complete_relation_rows_can_serve_other_limits_but_truncated_rows_cannot(self):
        sql=[];self.s.db.set_trace_callback(sql.append)
        with shared_read_boundary(self.s):
            first=list(facts(self.s,'consumer_dependencies',self.refs[0]['id'],1))
            second=list(facts(self.s,'consumer_dependencies',self.refs[0]['id'],100))
            count=sum('SELECT * FROM tl_dependency WHERE'in statement for statement in sql)
            self.assertEqual(count,2);self.assertEqual(len(first),1);self.assertGreater(len(second),1)
            self.assertEqual(list(facts(self.s,'consumer_dependencies',self.refs[0]['id'],2)),second[:2])
            self.assertEqual(list(facts(self.s,'consumer_dependencies',self.refs[0]['id'],101)),second)
            self.assertEqual(sum('SELECT * FROM tl_dependency WHERE'in statement for statement in sql),2)

if __name__=='__main__':unittest.main()
