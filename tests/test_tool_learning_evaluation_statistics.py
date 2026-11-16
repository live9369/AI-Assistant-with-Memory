"""Independent deterministic arithmetic fixtures; no model or instance imports."""
import math
import unittest
from evaluation.tool_learning_statistics import (
    count_metric, cost_summary, latency_summary, paired_bootstrap, paired_effect,
    retrieval_metrics, wilson,
)


class StatisticsTests(unittest.TestCase):
    def observation(self, i, value=True, status='measured', category='basic', case=None):
        return dict(id=str(i), case_id=case or str(i), category=category, status=status, value=value)

    def paired(self, cases=('a', 'b'), e=1., n=0.):
        return [dict(case_id=case, arm=arm, repeat=r, status='measured', score=e if arm == 'E' else n)
                for case in cases for arm in ('E', 'N') for r in (1, 2, 3)]

    def test_wilson_known_reference_and_zero(self):
        self.assertIsNone(wilson(0, 0))
        lo, hi = wilson(5, 10)
        self.assertAlmostEqual(lo, .236593090512564, places=12)
        self.assertAlmostEqual(hi, .763406909487436, places=12)
        self.assertAlmostEqual(wilson(0, 10)[1], .277532799862889, places=12)

    def test_invalid_counts_and_nonfinite_samples(self):
        for args in ((True, 1), (2, 1), (-1, 2), (1, 1.)):
            with self.assertRaises(ValueError): wilson(*args)
        for v in (math.nan, math.inf, True, 2):
            with self.assertRaises(ValueError): paired_bootstrap([v])

    def test_bootstrap_constant_exact_and_reproducible(self):
        result = paired_bootstrap([.25]*4)
        self.assertEqual(result['samples'], 10000)
        self.assertEqual(result['interval95'], [.25, .25])
        self.assertEqual(paired_bootstrap([-1, 0, 1]), paired_bootstrap([-1, 0, 1]))
        self.assertEqual(paired_bootstrap([])['status'], 'not_applicable')

    def test_preregistered_missing_not_zero_and_bounds(self):
        result = count_metric('TL06', [self.observation(1), self.observation(2, None, 'missing')])
        self.assertEqual(result['denominator'], 2)
        self.assertEqual(result['bounds'], [.5, 1])
        self.assertIsNone(result['rate'])
        self.assertEqual(result['decision'], 'incomplete')
        self.assertEqual(result['observed_subset_rate'], 1)

    def test_observed_violation_takes_priority_over_missing(self):
        for name in ('TL08', 'TL09'):
            result = count_metric(name, [self.observation(1), self.observation(2, None, 'not_run')])
            self.assertEqual(result['decision'], 'fail')
        self.assertEqual(count_metric('TL11', [self.observation(1)], unresolved_targets=1)['decision'], 'fail')

    def test_missing_cannot_hide_demonstrated_failure(self):
        rows = [self.observation(i, False) for i in range(9)] + [self.observation(9, None, 'missing')]
        self.assertEqual(count_metric('TL03', rows)['decision'], 'fail')

    def test_all_unknown_or_rejected_cannot_pass_coverage(self):
        self.assertEqual(count_metric('TL04', [self.observation(1, False)])['decision'], 'fail')
        self.assertEqual(count_metric('TL06', [self.observation(1, None, 'missing')])['decision'], 'incomplete')
        self.assertEqual(count_metric('TL02', [])['decision'], 'not_applicable')

    def test_category_sample_is_independent_cases(self):
        rows = [self.observation(i, case='same') for i in range(100)]
        result = count_metric('TL03', rows, required_categories=['basic'], formal=True)
        self.assertEqual(result['decision'], 'insufficient_sample')
        self.assertEqual(result['independent_cases_by_required_category'], {'basic': 1})
        with self.assertRaises(ValueError): count_metric('TL03', rows, formal=True)

    def test_micro_and_case_macro_reported_separately(self):
        rows = [self.observation(i, case='large') for i in range(9)] + [self.observation(9, False, case='small')]
        result = count_metric('TL06', rows)
        self.assertEqual(result['rate'], .9)
        self.assertEqual(result['case_macro_rate'], .5)

    def test_duplicate_and_invalid_measurement_rejected(self):
        row = self.observation(1)
        with self.assertRaises(ValueError): count_metric('TL01', [row, row])
        with self.assertRaises(ValueError): count_metric('TL01', [self.observation(1, 1)])
        with self.assertRaises(ValueError): count_metric('TL01', [self.observation(1, False, 'missing')])

    def test_registered_opportunities_cannot_be_removed_as_na(self):
        with self.assertRaises(ValueError):
            count_metric('TL06', [self.observation(1), self.observation(2, None, 'not_applicable')])

    def test_formal_unregistered_category_cannot_pass(self):
        rows = [self.observation(i) for i in range(20)] + [self.observation(20, category='unregistered')]
        with self.assertRaises(ValueError): count_metric('TL03', rows, formal=True, required_categories=['basic'])

    def test_formal_unknown_retention_descriptive_not_mechanism_gate(self):
        rows = [self.observation(i, i != 0) for i in range(20)]
        self.assertEqual(count_metric('TL07', rows)['decision'], 'fail')
        self.assertEqual(count_metric('TL07', rows, formal=True, required_categories=['basic'])['decision'], 'descriptive')

    def test_paired_three_repeats_case_means_then_equal_weights(self):
        rows = self.paired()
        for row in rows:
            if row['case_id'] == 'b': row['score'] = 0
        result = paired_effect(rows, metric_id='TL13', expected_cases=['a', 'b'], query_kind='new_question')
        self.assertEqual(result['case_count'], 2)
        self.assertEqual(result['trial_denominator'], 12)
        self.assertEqual(result['case_differences'], [1, 0])
        self.assertEqual(result['statistics']['mean'], .5)

    def test_missing_repeat_preserves_entire_assignment(self):
        rows = self.paired()[:-1]
        result = paired_effect(rows, metric_id='TL13', expected_cases=['a', 'b'], query_kind='new_question')
        self.assertEqual(result['trial_denominator'], 12)
        self.assertEqual(result['missing_trial_count'], 1)
        self.assertEqual(result['decision'], 'incomplete')
        self.assertIsNone(result['statistics'])
        self.assertEqual(result['bounds'], [5/6, 1])

    def test_wrong_stratum_repeat_and_duplicate_cannot_create_sample(self):
        rows = self.paired()
        with self.assertRaises(ValueError): paired_effect(rows, metric_id='TL13', expected_cases=['a','b'], query_kind='same_observation')
        with self.assertRaises(ValueError): paired_effect(rows+[rows[0]], metric_id='TL13', expected_cases=['a','b'], query_kind='new_question')
        result = paired_effect(rows, metric_id='TL13', expected_cases=['a','b'], query_kind='new_question', formal=True)
        self.assertEqual(result['decision'], 'insufficient_sample')

    def test_noninferiority_boundary_and_improvement_strict(self):
        result = paired_effect(self.paired(e=0, n=0), metric_id='TL13', expected_cases=['a','b'], query_kind='new_question')
        self.assertEqual(result['decision'], 'not_demonstrated')
        result = paired_effect(self.paired(e=.98, n=1), metric_id='TL14', expected_cases=['a','b'], query_kind='retention')
        # Binary floating point represents .98-1 slightly below -.02: do not
        # round a failed lower bound upward into the preregistered acceptance.
        self.assertEqual(result['decision'], 'not_demonstrated')
        result = paired_effect(self.paired(e=1, n=1), metric_id='TL14', expected_cases=['a','b'], query_kind='retention')
        self.assertEqual(result['decision'], 'pass')

    def test_retrieval_fixed_prelabelled_sets_and_empty_queries(self):
        result = retrieval_metrics([dict(id='a', case_id='a', relevant_ids=['x','y'], returned_ids=['z','x']), dict(id='b', case_id='b', relevant_ids=[], returned_ids=[])])
        self.assertEqual(result['macro_recall'], .5)
        self.assertEqual(result['mrr'], .5)
        self.assertIsNone(result['queries'][1]['precision'])
        self.assertIsNone(result['queries'][1]['recall'])
        with self.assertRaises(ValueError): retrieval_metrics([], k=10)

    def test_retrieval_missing_keeps_query_denominator(self):
        result = retrieval_metrics([dict(id='a', case_id='a', relevant_ids=['x'], returned_ids=['x']), dict(id='b', case_id='b', relevant_ids=['y'], returned_ids=None)])
        self.assertEqual(result['query_denominator'], 2)
        self.assertIsNone(result['macro_recall'])
        self.assertEqual(result['decision'], 'incomplete')
        self.assertEqual(result['macro_recall_bounds'], [.5, 1])

    def test_retrieval_case_equal_weights_not_query_weights(self):
        rows = [dict(id=str(i), case_id='large', relevant_ids=['x'], returned_ids=['x']) for i in range(9)]
        rows.append(dict(id='small', case_id='small', relevant_ids=['x'], returned_ids=[]))
        result = retrieval_metrics(rows)
        self.assertEqual(result['macro_recall'], .5)
        self.assertEqual(result['observed_subset_macro_recall'], .9)
        self.assertEqual(result['decision'], 'not_demonstrated')

    def test_retrieval_formal_category_minimum_uses_cases(self):
        rows = [dict(id=str(i), case_id='one', category='basic', relevant_ids=['x'], returned_ids=['x']) for i in range(20)]
        result = retrieval_metrics(rows, formal=True, required_categories=['basic'])
        self.assertEqual(result['decision'], 'insufficient_sample')
        with self.assertRaises(ValueError): retrieval_metrics(rows, formal=True)

    def test_latency_censoring_does_not_become_completed_zero(self):
        result = latency_summary([dict(completed=True, observed_ms=10), dict(completed=True, observed_ms=20), dict(completed=False, observed_ms=100)])
        self.assertEqual(result['completed_median_ms'], 15)
        self.assertEqual(result['completed_p95_ms'], 20)
        self.assertEqual(result['right_censored_observation_ms'], [100])
        self.assertEqual(result['completed_fraction'], 2/3)

    def test_cost_unknown_is_not_free_and_zero_correct_not_infinite(self):
        result = cost_summary([dict(attempt_id='a', transport='model', input_tokens=0, output_tokens=2, tool_calls=0, elapsed_ms=1, money=None)], correct_queries=0)
        self.assertEqual(result['components']['input_tokens']['total'], 0)
        self.assertIsNone(result['components']['money']['total'])
        self.assertIsNone(result['components']['elapsed_ms']['per_correct_query'])

    def test_cost_duplicate_actual_attempt_rejected(self):
        row = dict(attempt_id='a', transport='model', input_tokens=0, output_tokens=2, tool_calls=0, elapsed_ms=1, money=0)
        with self.assertRaises(ValueError): cost_summary([row, row], correct_queries=1, currency='USD')

    def test_known_money_needs_currency_and_call_counts_are_separate(self):
        row = dict(attempt_id='a', transport='model', input_tokens=1, output_tokens=2, tool_calls=0, elapsed_ms=1, money=.1)
        with self.assertRaises(ValueError): cost_summary([row], correct_queries=1)
        result = cost_summary([row], correct_queries=1, currency='USD')
        self.assertEqual(result['actual_model_call_count'], 1)
        self.assertEqual(result['components']['money']['total'], .1)


if __name__ == '__main__': unittest.main()
