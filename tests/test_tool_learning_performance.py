"""Pure-equivalence and cache-boundary protection for full-packet optimization."""
import copy
import unittest
from unittest.mock import patch
from digital_life.domain import tool_learning_types as t
from digital_life.domain.contracts import ContractError,sha,dumps
from tests.test_tool_learning_types import scope,known


def original_string(value,nonempty=True):
    if type(value)is not str or (nonempty and not value.strip()):raise ContractError('string required')
    if any(0xD800<=ord(c)<=0xDFFF for c in value):raise ContractError('invalid Unicode surrogate')
    return value


class StructuralPerformanceTests(unittest.TestCase):
    def test_every_unicode_codepoint_preserves_original_string_acceptance(self):
        # All 1,114,112 Unicode codepoints, including every surrogate. Compare
        # the original predicate directly, without logging invalid raw strings.
        for number in range(0x110000):
            value=chr(number)
            expected=not (0xD800<=number<=0xDFFF)
            try:result=t.string(value,nonempty=False)
            except ContractError:actual=False
            else:actual=result is value
            if actual!=expected:self.fail('different Unicode acceptance at '+hex(number))
        for value in ('',' ','\n','\x00','ascii','父亲liwei','😀','x\ud800y','\udfff','a'*100000+'\ud800'):
            for nonempty in (True,False):
                outcomes=[]
                for function in (original_string,t.string):
                    try:outcomes.append(('ok',function(value,nonempty)))
                    except ContractError as error:outcomes.append(('error',str(error)))
                self.assertEqual(outcomes[0],outcomes[1])
        for value in (None,True,0,[],{},b'x'):
            with self.assertRaises(ContractError):t.string(value)

    def reference(self,value):
        t.validate_scope(value)
        return t.fingerprint(value)

    def test_same_exact_scope_returns_original_digest_and_runs_full_proof_once(self):
        value=scope();expected=self.reference(value)
        with patch.object(t,'validate_scope',wraps=t.validate_scope)as check:
            with t.structural_validation_boundary():
                for _ in range(8):self.assertEqual(t.scope_fingerprint(copy.deepcopy(value)),expected)
            self.assertEqual(check.call_count,1)
            self.assertEqual(t.scope_fingerprint(value),expected)
            self.assertEqual(check.call_count,2)

    def test_mutation_false_zero_null_and_scope_revision_never_alias(self):
        base=scope()
        with t.structural_validation_boundary():
            values=[]
            for content in (0,False,None,{'x':[]},{'x':{}},'','中文'):
                value=copy.deepcopy(base);value['conditions']=known(content)
                expected=self.reference(value);values.append(t.scope_fingerprint(value));self.assertEqual(values[-1],expected)
            self.assertEqual(len(set(values)),len(values))
            value=copy.deepcopy(base);t.scope_fingerprint(value)
            value['temporal']['start']['value']='2026-02-30T12:00:00.000Z'
            with self.assertRaises(ContractError):t.scope_fingerprint(value)
            value=copy.deepcopy(base);value['coverage']['scanned']=False
            with self.assertRaises(ContractError):t.scope_fingerprint(value)

    def test_json_coercion_duplicate_keys_invalid_unicode_and_cycles_never_hit(self):
        value=scope()
        with t.structural_validation_boundary():
            t.scope_fingerprint(value)
            bad=copy.deepcopy(value);bad['exceptions']=()
            with self.assertRaises(ContractError):t.scope_fingerprint(bad)
            bad=copy.deepcopy(value);bad['conditions']['value']={'x':float('nan')}
            with self.assertRaises(ContractError):t.scope_fingerprint(bad)
            bad=copy.deepcopy(value);bad['subject_label']['value']='bad\udfff'
            with self.assertRaises(ContractError):t.scope_fingerprint(bad)
            bad=copy.deepcopy(value);bad['conditions']['value']={1:'nonstring'}
            with self.assertRaises(ContractError):t.scope_fingerprint(bad)
            bad=copy.deepcopy(value);bad['conditions']['value']={'cycle':bad}
            with self.assertRaises(ContractError):t.scope_fingerprint(bad)
            with self.assertRaises(ContractError):t.loads('{"a":1,"a":1}')

    def test_nested_and_exception_boundaries_do_not_reuse_parent_proofs(self):
        value=scope()
        with patch.object(t,'validate_scope',wraps=t.validate_scope)as check:
            with t.structural_validation_boundary():
                t.scope_fingerprint(value)
                with self.assertRaisesRegex(RuntimeError,'fixture'):
                    with t.structural_validation_boundary():
                        t.scope_fingerprint(value);raise RuntimeError('fixture')
                t.scope_fingerprint(value)
            self.assertEqual(check.call_count,2)
            with t.structural_validation_boundary():t.scope_fingerprint(value)
            self.assertEqual(check.call_count,3)

    def test_large_scopes_are_validated_without_retention_and_cache_is_bounded(self):
        value=scope();value['conditions']=known({'text':'x'*9000})
        with patch.object(t,'validate_scope',wraps=t.validate_scope)as check:
            with t.structural_validation_boundary():
                t.scope_fingerprint(value);t.scope_fingerprint(value)
            self.assertEqual(check.call_count,2)
        with t.structural_validation_boundary():
            for index in range(300):
                v=scope();v['subject_label']=known('subject '+str(index));self.assertEqual(t.scope_fingerprint(v),self.reference(v))

    def test_copied_context_cannot_retain_proofs_after_parent_exit(self):
        from contextvars import copy_context
        value=scope()
        with patch.object(t,'validate_scope',wraps=t.validate_scope)as check:
            with t.structural_validation_boundary():
                t.scope_fingerprint(value);child=copy_context()
            child.run(t.scope_fingerprint,value)
            self.assertEqual(check.call_count,2)

    def test_recursive_reference_basis_is_a_contract_error_in_both_modes(self):
        from contextlib import nullcontext
        value=scope();reference=value['subject']['value']
        reference['revision']['basis_refs'].append(reference)
        for boundary in (nullcontext,t.structural_validation_boundary):
            with boundary(),self.assertRaises(ContractError):t.scope_fingerprint(value)


class RevisionProbeTests(unittest.TestCase):
    def test_union_preserves_original_presence_for_both_owners_and_instances(self):
        # SQL truth-table/query-plan test, not a runtime authority fixture.
        import sqlite3
        from types import SimpleNamespace
        from pathlib import Path
        from digital_life.infrastructure.persistence.tool_learning_store import has_registered_revision
        from digital_life.infrastructure.persistence.sqlite_store import RESOURCES
        db=sqlite3.connect(':memory:');self.addCleanup(db.close)
        for name in ('runtime.sql','tool_learning_v1.sql'):db.executescript((RESOURCES/name).read_text())
        for index in range(1000):
            db.execute('INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind)VALUES(?,?,?,?,?)',('revision-'+str(index),'A'if index<900 else 'B','object-'+str(index//3),index%3,'synthetic-native'))
        for instance in ('A','B','missing-instance'):
            store=SimpleNamespace(db=db,instance_id=instance)
            for key in ('object-0','object-300','revision-0','revision-999','missing','object-299'):
                old=db.execute('SELECT 1 FROM object_revision_registry WHERE instance_id=? AND (object_id=? OR id=?) LIMIT 1',(instance,key,key)).fetchone()is not None
                self.assertEqual(has_registered_revision(store,key),old)
        sql='SELECT 1 FROM object_revision_registry WHERE instance_id=? AND object_id=? UNION ALL SELECT 1 FROM object_revision_registry WHERE instance_id=? AND id=? LIMIT 1'
        plan=[row[3]for row in db.execute('EXPLAIN QUERY PLAN '+sql,('A','object-0','A','object-0'))]
        self.assertTrue(any('object_id=?'in row and 'SEARCH'in row for row in plan))
        self.assertTrue(any('AND id=?'in row and 'SEARCH'in row for row in plan))


class MetadataCopyTests(unittest.TestCase):
    def test_immutable_json_copy_preserves_values_and_leaves_actual_meter_intact(self):
        import tempfile
        import math
        from digital_life.infrastructure.persistence.sqlite_store import Store
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter,cached_metadata
        from digital_life.domain.tool_learning_resources import DIMENSIONS
        from digital_life.domain.contracts import utc
        with tempfile.TemporaryDirectory()as folder:
            s=Store.prepare(folder);self.addCleanup(s.close)
            meter=PhysicalReadMeter({k:1000000 for k in DIMENSIONS},utc(30))
            value={'values':[0,False,None,-0.0,10**80,'中文😀'],'nested':{'x':[]}}
            with meter.installed(s):
                s.db.execute('SELECT 1').fetchone();before=dict(meter.actual)
                copied=cached_metadata('key',value);copied['nested']['x'].append('changed')
                value['nested']['x'].append('caller mutation')
                restored=cached_metadata('key')
                self.assertEqual(restored['nested']['x'],[])
                self.assertIs(type(restored['values'][0]),int);self.assertIs(type(restored['values'][1]),bool)
                self.assertIsNone(restored['values'][2]);self.assertEqual(math.copysign(1,restored['values'][3]),-1)
                self.assertEqual(restored['values'][4],10**80)
                self.assertEqual(meter.actual,before)
                for bad in ({'x':float('nan')},{'x':()},{'x':'\ud800'}):
                    with self.assertRaises(ContractError):cached_metadata('bad',bad)
            self.assertFalse(meter.metadata_cache)


class UpstreamQueueEquivalenceTests(unittest.TestCase):
    def test_exact_paths_duplicates_cycles_and_limits_match_preoptimization(self):
        import digital_life.application.learning.eligibility as module
        import evaluation.tool_learning_performance_reference as reference
        from digital_life.application.learning.engine import _dependency,source_scope
        from digital_life.infrastructure.persistence.tool_learning_meter import immutable_reference_boundary
        from tests.test_tool_learning_work import WorkTests
        fixture=WorkTests();fixture.setUp();self.addCleanup(fixture.doCleanups);s=fixture.s
        with s.tx():
            ids=[s.artifact({'queue_equivalence':i})for i in range(4)]
            refs=[module.ref(s,k)for k in ids];sc=source_scope(s)
            for index,(left,right,relation)in enumerate(((0,1,'read'),(0,2,'read'),(0,1,'delete'),(1,3,'read'),(2,3,'read'),(3,0,'delete'))):
                _dependency(s,refs[left],{'object':refs[right],'revision':0,'epoch':0},sc,relation,'/edge/'+str(index),'learn')
        token={'object':refs[0],'revision':0,'epoch':0}
        checker=module.ToolLearningEligibility(s,max_nodes=64,max_rows=128)
        with immutable_reference_boundary(s),patch.object(reference,'scope_key',wraps=module.scope_key)as counted:
            old_budget={'remaining':128};old=reference.reference_upstream(checker,token,sc,old_budget);old_calls=counted.call_count
        with immutable_reference_boundary(s),patch.object(module,'scope_key',wraps=module.scope_key)as counted:
            new_budget={'remaining':128};new=checker._upstream(token,sc,new_budget);new_calls=counted.call_count
        self.assertEqual(new,old);self.assertEqual(new_budget,old_budget)
        self.assertLess(new_calls,old_calls)
        self.assertTrue(any('delete'in row[3]for row in new))
        for nodes,rows in ((2,128),(64,2)):
            limited=module.ToolLearningEligibility(s,max_nodes=nodes,max_rows=rows)
            outcomes=[]
            for algorithm in (reference.reference_upstream,module.ToolLearningEligibility._upstream):
                try:algorithm(limited,token,sc,{'remaining':rows})
                except ContractError as error:outcomes.append((type(error).__name__,str(error)))
                else:self.fail('declared traversal limit was not enforced')
            self.assertEqual(outcomes[0],outcomes[1])
