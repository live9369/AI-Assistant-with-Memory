"""IM19 actual outer supervision, isolated deterministic child processes only."""
import json
from pathlib import Path
import tempfile
import unittest
from evaluation.tool_learning_mechanisms import supervise, persist_result


class MechanismSupervisionTests(unittest.TestCase):
    def test_actual_process_endpoints_three_repeats_and_failure_seals(self):
        with tempfile.TemporaryDirectory(prefix='im19-evidence-test-') as folder:
            ids = set()
            for scenario in ('success', 'exception', 'crash', 'hang', 'tree_hang', 'tree_success', 'missing_result'):
                for repeat in range(3):
                    with self.subTest(scenario=scenario, repeat=repeat):
                        timeout = .3 if scenario in ('hang', 'tree_hang') else 2
                        result, path = supervise(scenario, folder, timeout=timeout)
                        persist_result('supervision', dict(result, repeat=repeat + 1))
                        self.assertEqual(result, json.loads(path.read_text()))
                        self.assertNotIn(result['attempt_id'], ids); ids.add(result['attempt_id'])
                        self.assertTrue(result['entry_observed']); self.assertTrue(result['readiness_observed'])
                        expected = 'timeout' if scenario in ('hang', 'tree_hang') else ('completed' if scenario in ('success', 'tree_success') else 'failed')
                        self.assertEqual(result['status'], expected)
                        self.assertTrue(result['temporary_scope_removed'])
                        self.assertFalse(result['late_descendant_effect'])
                        self.assertFalse(result['real_model_called']); self.assertEqual(result['retries'], 0)
                        self.assertFalse(result['external_action_replayed'])
                        if scenario.startswith('tree_'):
                            self.assertEqual(len(result['descendant_pids']), 1)
                        if expected == 'timeout':
                            self.assertLess(result['elapsed_seconds'], 1)
                            self.assertEqual(result['returncode'], -9)
                            self.assertIsNone(result['result'])
                        if expected != 'completed':
                            self.assertEqual(result['usage']['state'], 'unknown')
                            self.assertIsNone(result['usage']['provider_tokens'])
                        if scenario == 'exception':
                            self.assertIn('deterministic infrastructure failure', result['stderr'])
                        if scenario == 'crash':
                            self.assertEqual(result['returncode'], 73)
            self.assertEqual(len(list(Path(folder).glob('*.json'))), 21)

    def test_unknown_scenario_and_unbounded_deadline_rejected_before_process(self):
        with tempfile.TemporaryDirectory(prefix='im19-evidence-test-') as folder:
            for scenario, deadline in (('real-model', 1), ('success', 0), ('success', 31)):
                with self.assertRaises(ValueError):
                    supervise(scenario, folder, timeout=deadline)
            self.assertEqual(list(Path(folder).iterdir()), [])


class MechanismWriteFaultTests(unittest.TestCase):
    def test_all_42_physical_writes_three_actual_repeats(self):
        from evaluation.tool_learning_write_faults import run_write_fault, ROOT
        manifest = json.loads((ROOT / 'config/evaluation/tool-learning-mechanism-manifest-v0.1.json').read_text())
        seen = []
        for case in manifest['write_fault_branches']:
            for repeat in range(3):
                with self.subTest(case=case['id'], repeat=repeat):
                    result = run_write_fault(case)
                    persist_result('write-fault', dict(result, repeat=repeat + 1))
                    self.assertEqual(result['endpoint'], case['expected_endpoint'])
                    self.assertTrue(result['transaction_rollback_verified'])
                    self.assertTrue(result['prior_rows_preserved'])
                    self.assertTrue(result['injection_hits'])
                    self.assertEqual(result['before_digest'], result['after_digest'])
                    seen.append((case['id'], repeat))
        self.assertEqual(len(seen), 126)


class MechanismInheritedG1Tests(unittest.TestCase):
    def test_65_scenarios_and_60_materials_three_actual_repeats(self):
        from evaluation.tool_learning_g1 import run_g1, ROOT
        manifest = json.loads((ROOT / 'config/evaluation/tool-learning-mechanism-manifest-v0.1.json').read_text())
        completed = []
        for case in manifest['g1_scenarios'] + manifest['g1_materials']:
            for repeat in range(3):
                with self.subTest(case=case['id'], repeat=repeat):
                    result = run_g1(case)
                    persist_result('g1', dict(result, repeat=repeat + 1))
                    self.assertEqual(result['status'], 'pass', result['error'])
                    self.assertTrue(result['assertions'])
                    self.assertTrue(all(a['passed'] for a in result['assertions']))
                    self.assertTrue(result['temporary_scope_removed'])
                    self.assertEqual(result['endpoint'], case['expected_endpoint'])
                    completed.append((case['id'], repeat))
        self.assertEqual(len(completed), 375)


class MechanismConcurrencyTests(unittest.TestCase):
    def test_24_thread_and_24_process_branches_three_actual_repeats(self):
        from evaluation.tool_learning_concurrency import run_concurrency
        root=Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'config/evaluation/tool-learning-mechanism-manifest-v0.1.json').read_text())
        completed=[]
        for case in manifest['concurrency_branches']:
            for repeat in range(3):
                with self.subTest(case=case['id'],repeat=repeat):
                    result=run_concurrency(case)
                    persist_result('concurrency',dict(result,repeat=repeat+1))
                    self.assertEqual(result['endpoint'],case['expected_endpoint'])
                    self.assertTrue(result['actual_transport'])
                    self.assertEqual(result['post_control_entry_count'],0)
                    if case['mode']=='process':
                        self.assertEqual(result['control_exitcode'],0)
                        control_pid=next(e['pid'] for e in result['events'] if e['kind']=='control_ready')
                        import os
                        self.assertNotEqual(control_pid,os.getpid())
                    completed.append((case['id'],repeat))
        self.assertEqual(len(completed),144)


class MechanismSemanticTests(unittest.TestCase):
    def test_distinct_source_and_unsupported_candidate_cases_three_repeats(self):
        from evaluation.tool_learning_semantic_cases import run_semantic_case,SOURCE_VARIANTS,UNSUPPORTED_CANDIDATES
        for case_id in sorted(set(SOURCE_VARIANTS)|set(UNSUPPORTED_CANDIDATES)):
            for repeat in range(3):
                with self.subTest(case=case_id,repeat=repeat):
                    result=run_semantic_case(case_id)
                    persist_result('semantic-source',dict(result,repeat=repeat+1))
                    self.assertEqual(result['status'],'pass')
                    self.assertTrue(result['observations'] or result['decisions'])

    def test_actual_temporal_supplement_and_review_boundaries_three_repeats(self):
        from evaluation.tool_learning_semantic_cases import temporal_material
        variants=('later_point','unknown_time','overlapping_interval','old_arrives_late','unit_changed','domain_changed','subject_changed','old_source_revoked','new_source_revoked')
        for variant in variants:
            for repeat in range(3):
                with self.subTest(variant=variant,repeat=repeat):
                    result=temporal_material(variant,acceptance=variant=='later_point')
                    persist_result('temporal',dict(result,repeat=repeat+1))
                    if variant=='later_point':
                        self.assertEqual(result['actual_operation'],'temporal_add')
                        self.assertNotEqual(result['old_source']['object']['id'],result['new_source']['object']['id'])
                        self.assertEqual(result['products'][2]['body']['target']['mode'],'new')
                        self.assertEqual(result['candidate_decision']['operation'],'candidate')
                        self.assertEqual(result['reviewed_decision']['operation'],'accept')
                        self.assertTrue(result['old_history_preserved'])
                    elif variant.endswith('revoked'):
                        self.assertEqual(result['endpoint'],'blocked_current_source')
                    else:
                        self.assertNotEqual(result['actual_operation'],'temporal_add')


class MechanismReprocessingTests(unittest.TestCase):
    def test_actual_coordinator_authenticated_reprocessing_three_repeats(self):
        from evaluation.tool_learning_reprocessing_cases import run_reprocessing,VARIANTS
        completed=[]
        for variant in VARIANTS:
            for repeat in range(3):
                with self.subTest(variant=variant,repeat=repeat):
                    result=run_reprocessing(variant)
                    persist_result('reprocessing',dict(result,repeat=repeat+1))
                    self.assertTrue(result['prior_products_preserved'])
                    self.assertFalse(result['real_model_called'])
                    if result['endpoint']=='finite_authorized_reprocessing':
                        self.assertEqual(result['work_count'],2)
                        self.assertEqual(result['grant']['new_observation_count'],0)
                        self.assertEqual(result['grant']['independent_sample_count'],0)
                        self.assertEqual(result['grant']['gain'],'not_measured')
                    else:
                        self.assertEqual(result['work_count'],1)
                        self.assertIsNotNone(result['error'])
                    completed.append((variant,repeat))
        self.assertEqual(len(completed),45)


class MechanismComparisonTests(unittest.TestCase):
    def test_same_source_local_correction_three_repeats(self):
        from evaluation.tool_learning_semantic_cases import corrected_interpretation
        for variant in ('same_original','independent_source','unknown_old_value','unit_changed','multiple_old_supports'):
            for repeat in range(3):
                with self.subTest(variant=variant,repeat=repeat):
                    result=corrected_interpretation(variant)
                    persist_result('correction',dict(result,repeat=repeat+1))
                    self.assertTrue(result['old_history_preserved'])
                    if variant=='same_original':self.assertEqual(result['actual_operation'],'correct')

    def test_actual_bounded_counterexample_owner_three_repeats(self):
        from evaluation.tool_learning_comparison_cases import run_comparison,VARIANTS
        completed=[]
        for variant in VARIANTS:
            for repeat in range(3):
                with self.subTest(variant=variant,repeat=repeat):
                    result=run_comparison(variant)
                    persist_result('bounded-comparison',dict(result,repeat=repeat+1))
                    self.assertFalse(result['real_model_called'])
                    if variant=='actual_restrict_candidate':
                        self.assertEqual(result['actual_candidate_operation'],'candidate')
                        self.assertEqual(result['actual_product_count'],4)
                        self.assertFalse(result['proof_body']['replacement_universal'])
                        self.assertEqual(result['proof_body']['remaining_valid_subset'],'unknown')
                    else:
                        self.assertEqual(result['actual_product_count'],0)
                        self.assertIsNotNone(result['actual_error'])
                    completed.append((variant,repeat))
        self.assertEqual(len(completed),54)


class MechanismUpgradeTests(unittest.TestCase):
    def test_actual_finite_upgrade_and_closed_context_three_repeats(self):
        from evaluation.tool_learning_upgrade_cases import run_upgrade,VARIANTS
        completed=[]
        for variant in VARIANTS:
            for repeat in range(3):
                with self.subTest(variant=variant,repeat=repeat):
                    result=run_upgrade(variant)
                    persist_result('representation-upgrade',dict(result,repeat=repeat+1))
                    self.assertEqual(result['learning_counts_before'],result['learning_counts_after'])
                    self.assertEqual(result['original_work']['state'],result['work_after']['state'])
                    if result['endpoint']=='authorized_same_content_header_parameter_upgrade':
                        self.assertEqual(len(result['representations_after']),2)
                    else:self.assertTrue(result['actual_errors'])
                    completed.append((variant,repeat))
        self.assertEqual(len(completed),48)

    def test_actual_native_atomic_group_upgrade_is_explicitly_blocked(self):
        from tests.test_tool_learning_representation import RepresentationTests
        from digital_life.application.learning.runtime_learning import StrictLearningCoordinator
        from digital_life.application.learning.representation_upgrade import UpgradeSession,SOURCE
        from digital_life.domain.contracts import Forbidden,utc
        for repeat in range(3):
            f=RepresentationTests();f.setUp()
            try:
                f.group_setup()
                for index in (0,1):f.service.publish(f.entries[index],f.group_publish_request(index))
                s=f.s;(s.root/'controller.token').write_text('synthetic-group-upgrade-token')
                scope={'tool_learning_runtime':{'contract':'TL-STRICT-RUNTIME-1','enabled':True},'tool_learning_representation_upgrade':{'contract':'TL-HEADER-LANGUAGE-UPGRADE-1','enabled':True,'languages':['zh','en'],'max_upgrades':2,'expires_at':utc(120)}}
                version=s.db.execute('SELECT max(version)+1 FROM policy_versions').fetchone()[0]
                policy=s.insert('policy_versions',version=version,mode='authorization',scope=scope,effective_at=utc(-1),authority=s.config()['controller'])
                s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE instance_id=?',(policy,s.instance_id))
                h=dict(s.db.execute('SELECT * FROM tl_handoff WHERE group_id IS NOT NULL LIMIT 1').fetchone())
                # Constructor guard runs before any runtime read/capability. A
                # real class method checks current policy, not a True callback.
                r=StrictLearningCoordinator.__new__(StrictLearningCoordinator);r.s=s
                before=s.db.execute('SELECT count(*) FROM tl_handoff').fetchone()[0]
                with self.assertRaisesRegex(Forbidden,'atomic group'):
                    UpgradeSession(r,h['id'],'Bearer synthetic-group-upgrade-token','en',1)
                after=s.db.execute('SELECT count(*) FROM tl_handoff').fetchone()[0]
                self.assertEqual(before,after)
                self.assertEqual(s.db.execute('SELECT count(*) FROM runtime_events WHERE source=?',(SOURCE,)).fetchone()[0],0)
                persist_result('representation-upgrade-group',{'case_id':'Q07-A11','repeat':repeat+1,'endpoint':'blocked_atomic_group_upgrade_unimplemented','actual_group_handoff':h,'handoffs_before':before,'handoffs_after':after,'new_authorization_events':0,'scope':'actual native C1/C2 group fixture and authenticated constructor guard; group upgrade not supported','real_model_called':False})
            finally:f.doCleanups()


class MechanismOriginalSourceTests(unittest.TestCase):
    def test_actual_tool_original_artifact_wait_failure_and_partial_three_repeats(self):
        from evaluation.tool_learning_source_cases import original_tool_receipt
        for variant in ('body_available','receipt_only','failed','partial'):
            for repeat in range(3):
                with self.subTest(variant=variant,repeat=repeat):
                    result=original_tool_receipt(variant)
                    persist_result('original-tool-source',dict(result,repeat=repeat+1))
                    self.assertEqual(len(result['actual_tool_entry_witnesses']),1)
                    self.assertFalse(result['original_action_replayed'])

    def test_actual_two_level_views_and_codepoint_locations_three_repeats(self):
        from evaluation.tool_learning_source_cases import derived_view
        for variant in ('json_nested','text_location','wrong_view_digest','wrong_view_locator'):
            for repeat in range(3):
                with self.subTest(variant=variant,repeat=repeat):
                    result=derived_view(variant)
                    persist_result('derived-view',dict(result,repeat=repeat+1))
                    if variant in ('json_nested','text_location'):
                        self.assertEqual(len(result['actual_products']),4)
                        self.assertTrue(result['view_dependency_rows'])
                    else:self.assertFalse(result['actual_products'])


class MechanismExistingFixtureTests(unittest.TestCase):
    def test_unique_existing_fixtures_three_repeats_with_actual_assertions(self):
        from evaluation.tool_learning_reuse import run_fixture,ROOT
        catalog=json.loads((ROOT/'config/evaluation/tool-learning-mechanism-bindings-v0.1.json').read_text())
        seen=set()
        for spec in catalog['reused_fixture_specs']:
            self.assertNotIn(spec['id'],seen);seen.add(spec['id'])
            for repeat in range(1,4):
                with self.subTest(fixture=spec['id'],repeat=repeat):
                    result=run_fixture(spec)
                    persist_result('reused-fixture',dict(result,repeat=repeat))
                    self.assertEqual(result['status'],'pass',result['failures']+result['errors'])
                    self.assertTrue(result['assertion_execution_trace'])
                    self.assertFalse(result['formal_instance_opened'])


class MechanismFinalRecallTests(unittest.TestCase):
    def test_actual_native_provenance_and_scoped_queries_three_repeats(self):
        from evaluation.tool_learning_recall_cases import strict_legacy,strict_scoped_reports,bounded_conflicting_reports
        groups=((strict_legacy,('same_source_summaries','model_instruction','current_and_independent_same_text','partial_original','unknown_method','mixed_roles')),(strict_scoped_reports,('different_scopes','ambiguous_alias')),(bounded_conflicting_reports,('both_legal_counterreports','reject_does_not_reconfirm_old')))
        for function,variants in groups:
            for variant in variants:
                for repeat in range(1,4):
                    with self.subTest(variant=variant,repeat=repeat):
                        result=function(variant);persist_result('native-recall',dict(result,repeat=repeat))
                        self.assertFalse(result['real_model_called'])

    def test_new_actual_observation_can_confirm_without_a_prediction(self):
        from evaluation.tool_learning_semantic_cases import corrected_interpretation
        for repeat in range(1,4):
            result=corrected_interpretation('independent_same_value');persist_result('confirmation',dict(result,repeat=repeat))
            self.assertEqual(result['actual_difference'],'confirmation');self.assertEqual(result['actual_operation'],'confirm')


class MechanismQ10Tests(unittest.TestCase):
    def test_case_specific_aggregation_boundaries_three_repeats(self):
        from evaluation.tool_learning_q10_cases import run_arithmetic
        for number in (1,2,3,4,5,6,7,8,9,15,18,20):
            for repeat in range(1,4):
                with self.subTest(case=number,repeat=repeat):
                    result=run_arithmetic('Q10-C%02d'%number);persist_result('q10-statistics',dict(result,repeat=repeat))
                    self.assertTrue(result['assertions']);self.assertTrue(all(x['passed']for x in result['assertions']))


class MechanismQ10ActualTests(unittest.TestCase):
    def test_actual_retention_partial_cleanup_cost_and_review_three_repeats(self):
        from evaluation.tool_learning_q10_cases import run_actual
        for case in ('Q10-C12','Q10-C13','Q10-C16','Q10-C17'):
            for repeat in range(1,4):
                with self.subTest(case=case,repeat=repeat):
                    result=run_actual(case);persist_result('q10-actual',dict(result,repeat=repeat))
                    self.assertFalse(result['real_model_called'])


class MechanismFrozenBoundaryProofTests(unittest.TestCase):
    def test_research_and_preimplementation_boundary_provenance_three_repeats(self):
        from evaluation.tool_learning_coverage import frozen_proof
        for case in ('Q03-D12','Q04-D12'):
            for repeat in range(1,4):
                result=frozen_proof(case);persist_result('frozen-proof',dict(result,repeat=repeat))
                self.assertEqual(result['status'],'pass')


class MechanismCoverageGateTests(unittest.TestCase):
    def test_empty_execution_directory_cannot_complete_static_catalog(self):
        from evaluation.tool_learning_coverage import collect
        with tempfile.TemporaryDirectory(prefix='im19-missing-executions-')as folder:
            target=Path(folder)/'mechanisms';target.mkdir();result=collect(target)
            self.assertFalse(result['passed']);self.assertEqual(result['covered_obligations'],0)
            self.assertEqual(result['obligation_denominator'],438);self.assertEqual(result['covered_decisions'],0)
            self.assertTrue((Path(folder)/'coverage.json').is_file())
