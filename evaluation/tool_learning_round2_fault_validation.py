"""Named-main PF06 runner: required for genuine spawn-process regressions."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import unittest

NAMES=['tests.test_sqlite_write_monitor','tests.test_tool_learning_certified_input','tests.test_tool_learning_dependency_materials','tests.test_tool_learning_snapshot_source_rows','tests.test_tool_learning_scale_failure_snapshot','tests.test_tool_learning_owner_source_rows','tests.test_tool_learning_post_calculation_boundaries','tests.test_architecture','tests.test_tool_learning_performance_diagnostic','tests.test_tool_learning_round2_faults','tests.test_tool_learning_readset','tests.test_tool_learning_readset_review','tests.test_tool_learning_round2_graph','tests.test_tool_learning_round2_collection','tests.test_tool_learning_typed_evidence','tests.test_tool_learning_control_materials','tests.test_tool_learning_configuration_reader','tests.test_tool_learning_validation_projection','tests.test_tool_learning_controller_events','tests.test_tool_learning_controller_native','tests.test_tool_learning_calculation_sharing','tests.test_tool_learning_revision_existence','tests.test_tool_learning_cached_logical_rows','tests.test_tool_learning_owned_transaction_boundaries','tests.test_tool_learning_reference_kind','tests.test_tool_learning_revision_mapping','tests.test_tool_learning_round2_compare','tests.test_tool_learning_eligibility','tests.test_tool_learning_runtime.AssemblyGateTests','tests.test_tool_learning_runtime.ImmutableReferenceBoundaryTests','tests.test_tool_learning_runtime.OriginalActivityBudgetTests','tests.test_tool_learning_runtime.PhysicalMeterTests']
ROOT=Path(__file__).resolve().parents[1]
POST_SAVEPOINT_NAMES=['tests.test_sqlite_write_monitor','tests.test_tool_learning_certified_input',
    'tests.test_tool_learning_owned_transaction_boundaries',
    'tests.test_tool_learning_calculation_sharing.CalculationSourcePreparationTests',
    'tests.test_tool_learning_calculation_sharing.FullCalculationDifferentialTests.test_native_and_managed_full_contexts_keep_values_sources_and_stage_read_counts',
    'tests.test_tool_learning_readset','tests.test_tool_learning_readset_review','tests.test_tool_learning_round2_collection',
    'tests.test_tool_learning_cached_logical_rows','tests.test_tool_learning_post_calculation_boundaries',
    'tests.test_tool_learning_round2_faults','tests.test_architecture','tests.test_tool_learning_continuation_diagnostic']
NAMES.extend(('tests.test_tool_learning_continuation_diagnostic','tests.test_tool_learning_insert_only_retention'))
POST_SAVEPOINT_NAMES.append('tests.test_tool_learning_insert_only_retention')
POST_SAVEPOINT_NAMES.append('tests.test_tool_learning_round2_graph')
NAMES.append('tests.test_tool_learning_metadata_binding')
POST_SAVEPOINT_NAMES.append('tests.test_tool_learning_metadata_binding')
NAMES.append('tests.test_tool_learning_exact_material_facts')
POST_SAVEPOINT_NAMES.append('tests.test_tool_learning_exact_material_facts')
NAMES.append('tests.test_tool_learning_material_cache_diagnostic')
POST_SAVEPOINT_NAMES.append('tests.test_tool_learning_material_cache_diagnostic')
NAMES.append('tests.test_tool_learning_cache_replacement')
POST_SAVEPOINT_NAMES.append('tests.test_tool_learning_cache_replacement')
NAMES.append('tests.test_tool_learning_statistical_cpu_diagnostic')
POST_SAVEPOINT_NAMES.append('tests.test_tool_learning_statistical_cpu_diagnostic')
for name in ('tests.test_tool_learning_check_file_signatures','tests.test_tool_learning_file_lease_boundaries'):
    NAMES.append(name);POST_SAVEPOINT_NAMES.append(name)

for name in ('tests.test_tool_learning_graph_material','tests.test_control_reader_file_identity'):
    NAMES.append(name);POST_SAVEPOINT_NAMES.append(name)

for name in ('tests.test_strict_result_occurrence_lineage','tests.test_strict_result_occurrence_deletion'):
    NAMES.append(name);POST_SAVEPOINT_NAMES.append(name)

def snapshot():
    paths=[ROOT/'tests/test_architecture.py',ROOT/'tests/test_sqlite_write_monitor.py',ROOT/'tests/test_control_reader_file_identity.py']+list((ROOT/'digital_life').rglob('*.py'))+list((ROOT/'tests').glob('test_tool_learning*.py'))+list((ROOT/'tests').glob('test_strict_result_occurrence*.py'))+list((ROOT/'evaluation').glob('tool_learning*.py'))
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted(paths)}

def ids(suite):
    result=[]
    for item in suite:result.extend(ids(item)if isinstance(item,unittest.TestSuite)else[item.id()])
    return result

FILE_SIGNATURE_NAMES=['tests.test_sqlite_write_monitor','tests.test_tool_learning_check_file_signatures',
    'tests.test_tool_learning_file_lease_boundaries','tests.test_tool_learning_certified_input',
    'tests.test_architecture','tests.test_tool_learning_readset','tests.test_tool_learning_readset_review',
    'tests.test_tool_learning_owned_transaction_boundaries','tests.test_tool_learning_round2_faults',
    'tests.test_tool_learning_continuation_diagnostic','tests.test_tool_learning_graph_material',
    'tests.test_control_reader_file_identity']

RESULT_OCCURRENCE_NAMES=['tests.test_strict_result_occurrence_lineage','tests.test_strict_result_occurrence_deletion',
    'tests.test_tool_learning_runtime.StrictActualUseTests','tests.test_tool_learning_runtime.ProductLineageTests',
    'tests.test_tool_learning_runtime.RollbackBlobTests','tests.test_tool_learning_runtime.CrossInstanceRollbackBlobTests',
    'tests.test_tool_learning_invalidation','tests.test_tool_learning_propagation','tests.test_architecture']

def run(output,post_savepoint=False,file_signatures=False,result_occurrences=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    before=snapshot();suite=unittest.defaultTestLoader.loadTestsFromNames(RESULT_OCCURRENCE_NAMES if result_occurrences else FILE_SIGNATURE_NAMES if file_signatures else POST_SAVEPOINT_NAMES if post_savepoint else NAMES);test_ids=ids(suite)
    expected=115 if result_occurrences else 199 if file_signatures else 305 if post_savepoint else 509
    assert len(test_ids)==expected and len(set(test_ids))==expected, len(test_ids)
    started=time.monotonic()
    with (output/'tests.log').open('w')as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    elapsed=time.monotonic()-started;after=snapshot()
    summary={'scope':'Strict response occurrence lineage, actual use, revocation/erasure/cohort, rollback and architecture; not full suite'if result_occurrences else'Trusted check file signatures and necessary original write/foreign/rollback faults; not full suite'if file_signatures else'Post-calculation/input-material corrections and necessary scoped regressions; not the complete509 suite'if post_savepoint else'PF06 targeted synthetic faults and necessary original regressions; no complete Engine','real_models_called':False,'formal_instance_accessed':False,'tests':test_ids,'run':result.testsRun,'passed':result.wasSuccessful(),'failures':[(t.id(),s)for t,s in result.failures],'errors':[(t.id(),s)for t,s in result.errors],'skipped':[(t.id(),s)for t,s in result.skipped],'wall_seconds':elapsed,'source_before':before,'source_after':after,'source_stable':before==after}
    (output/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:summary[k]for k in ('run','passed','wall_seconds','source_stable')},ensure_ascii=False),flush=True)
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--post-savepoint',action='store_true');parser.add_argument('--file-signatures',action='store_true');parser.add_argument('--result-occurrences',action='store_true');args=parser.parse_args()
    raise SystemExit(0 if run(args.output,args.post_savepoint,args.file_signatures,args.result_occurrences)['passed']else 1)
