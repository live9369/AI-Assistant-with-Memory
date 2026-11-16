"""TL-EVAL-0.1 offline statistics. Inputs are assessed facts, never self-labels."""
import math
import random
from statistics import mean, median

STATUSES = {'measured', 'not_run', 'missing', 'not_applicable',
            'insufficient_sample', 'not_evaluable'}
COUNT_IDS = {'TL01', 'TL02', 'TL03', 'TL04', 'TL06', 'TL07',
             'TL08', 'TL09', 'TL11', 'TL12', 'TL16'}
THRESHOLDS = {'TL01': 1, 'TL02': 1, 'TL03': .95, 'TL04': .9,
              'TL06': .9, 'TL07': 1, 'TL11': 1, 'TL12': 1, 'TL16': 1}


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('nonnegative integer required')
    return value


def _number(value, low=None, high=None):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError('finite number required')
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError('number outside bounds')
    return value


def wilson(successes, total):
    _integer(total)
    _integer(successes)
    if successes > total:
        raise ValueError('success count exceeds denominator')
    if total == 0:
        return None
    z = 1.959963984540054
    p = successes / total
    factor = 1 + z * z / total
    center = (p + z * z / (2 * total)) / factor
    radius = z * math.sqrt(p * (1-p) / total + z*z / (4*total*total)) / factor
    return [max(0., center-radius), min(1., center+radius)]


def _quantile(values, fraction):
    ordered = sorted(values)
    index = (len(ordered)-1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    return ordered[lower] + (ordered[upper]-ordered[lower]) * (index-lower)


def paired_bootstrap(case_differences, *, seed=20261108, samples=10000):
    differences = list(case_differences)
    for value in differences:
        _number(value, -1, 1)
    _integer(samples, 1)
    _integer(seed)
    if not differences:
        return {'status': 'not_applicable', 'mean': None, 'interval95': None,
                'case_count': 0, 'samples': samples, 'seed': seed}
    rng = random.Random(seed)
    n = len(differences)
    # Repeats have already been reduced within each case; resample whole cases.
    estimates = [sum(differences[rng.randrange(n)] for _ in range(n))/n
                 for _ in range(samples)]
    return {'status': 'measured', 'mean': mean(differences),
            'interval95': [_quantile(estimates, .025), _quantile(estimates, .975)],
            'case_count': n, 'samples': samples, 'seed': seed,
            'method': 'paired_case_percentile_linear_quantile_v1'}


def _observations(rows):
    rows = list(rows)
    seen = set()
    for row in rows:
        for key in ('id', 'case_id', 'category'):
            if not isinstance(row[key], str) or not row[key]:
                raise ValueError('opportunity identity/category required')
        if row['id'] in seen:
            raise ValueError('duplicate opportunity')
        seen.add(row['id'])
        if row['status'] not in STATUSES:
            raise ValueError('unknown measurement status')
        if row['status'] == 'not_applicable':
            raise ValueError('a preregistered opportunity cannot be removed as not applicable')
        if row['status'] == 'measured':
            if type(row['value']) is not bool:
                raise ValueError('assessed boolean required')
        elif row['value'] is not None:
            raise ValueError('unmeasured observation cannot have a value')
    return rows


def count_metric(metric_id, observations, *, required_categories=(), formal=False,
                 hard_violations=0, unresolved_targets=0):
    if metric_id not in COUNT_IDS:
        raise ValueError('use the metric-specific aggregator')
    if formal and metric_id in ('TL03', 'TL04', 'TL06', 'TL07', 'TL16') and not required_categories:
        raise ValueError('formal quality requires preregistered categories')
    rows = _observations(observations)
    if formal and required_categories and any(r['category'] not in required_categories for r in rows):
        raise ValueError('category outside preregistered set')
    _integer(hard_violations)
    _integer(unresolved_targets)
    eligible = [r for r in rows if r['status'] != 'not_applicable']
    known = [r for r in eligible if r['status'] == 'measured']
    missing = len(eligible)-len(known)
    yes = sum(r['value'] for r in known)
    n = len(eligible)
    violations = metric_id in ('TL08', 'TL09')
    threshold = 0 if violations else THRESHOLDS[metric_id]
    failures_observed = yes if violations else len(known)-yes
    categories = {name: len({r['case_id'] for r in eligible if r['category'] == name})
                  for name in required_categories}
    insufficient = formal and any(value < 20 for value in categories.values())
    if hard_violations or (violations and yes) or (metric_id == 'TL11' and unresolved_targets):
        decision = 'fail'
    elif not n:
        decision = 'not_applicable'
    elif not violations and not (formal and metric_id == 'TL07') and (yes + missing)/n < threshold:
        decision = 'fail'
    elif missing:
        decision = 'incomplete'
    elif insufficient:
        decision = 'insufficient_sample'
    elif formal and metric_id == 'TL07':
        decision = 'descriptive'
    else:
        decision = 'pass' if (yes/n <= threshold if violations else yes/n >= threshold) else 'fail'
    strata = {}
    case_rates = []
    for category in sorted({r['category'] for r in eligible}):
        subset = [r for r in eligible if r['category'] == category]
        measured = [r for r in subset if r['status'] == 'measured']
        strata[category] = {'numerator': sum(r['value'] for r in measured),
                            'denominator': len(subset), 'missing_count': len(subset)-len(measured)}
    for case in {r['case_id'] for r in eligible}:
        subset = [r for r in eligible if r['case_id'] == case]
        if all(r['status'] == 'measured' for r in subset):
            case_rates.append(sum(r['value'] for r in subset)/len(subset))
    return {'metric_id': metric_id, 'numerator': yes, 'denominator': n,
            'measured_count': len(known), 'missing_count': missing,
            'not_run_count': sum(r['status'] == 'not_run' for r in rows),
            'not_applicable_count': len(rows)-n, 'observed_failures': failures_observed,
            'rate': yes/n if n and not missing else None,
            'observed_subset_rate': yes/len(known) if known else None,
            'bounds': [yes/n, (yes+missing)/n] if n else None,
            'wilson95_observed_subset': wilson(yes, len(known)),
            'independent_cases_by_required_category': categories,
            'hard_violations': hard_violations, 'unresolved_targets': unresolved_targets,
            'category_counts': strata, 'case_macro_rate': mean(case_rates) if case_rates and not missing else None,
            'decision': decision, 'scope': 'single metric; not full protocol approval'}


def paired_effect(records, *, metric_id, expected_cases, query_kind,
                  formal=False, repeats=3):
    if metric_id not in ('TL13', 'TL14'):
        raise ValueError('paired metric must be TL13 or TL14')
    if query_kind != ('new_question' if metric_id == 'TL13' else 'retention'):
        raise ValueError('wrong primary query stratum')
    _integer(repeats, 1)
    if formal and repeats != 3:
        raise ValueError('formal protocol requires three repeats')
    cases = list(expected_cases)
    if not cases or len(set(cases)) != len(cases) or any(not isinstance(c, str) or not c for c in cases):
        raise ValueError('unique preregistered case identities required')
    indexed = {}
    for row in records:
        key = (row['case_id'], row['arm'], row['repeat'])
        if key in indexed or key[0] not in cases or key[1] not in ('E', 'N'):
            raise ValueError('duplicate or unassigned paired record')
        if type(key[2]) is not int or not 1 <= key[2] <= repeats:
            raise ValueError('unassigned repeat')
        if row['status'] not in STATUSES - {'not_applicable'}:
            raise ValueError('invalid assigned trial measurement status')
        score = row['score']
        if row['status'] == 'measured':
            _number(score, 0, 1)
        elif score is not None:
            raise ValueError('missing score cannot be imputed')
        indexed[key] = score
    differences = []
    complete = []
    lower, upper, missing = [], [], 0
    for case in cases:
        values = {arm: [indexed.get((case, arm, r)) for r in range(1, repeats+1)] for arm in ('E', 'N')}
        missing += sum(v is None for vs in values.values() for v in vs)
        lo = mean(v if v is not None else 0 for v in values['E']) - mean(v if v is not None else 1 for v in values['N'])
        hi = mean(v if v is not None else 1 for v in values['E']) - mean(v if v is not None else 0 for v in values['N'])
        lower.append(lo)
        upper.append(hi)
        if all(v is not None for vs in values.values() for v in vs):
            differences.append(mean(values['E'])-mean(values['N']))
            complete.append(case)
    # No complete-case-only claim when preregistered observations are missing.
    statistics = paired_bootstrap(differences) if not missing else None
    required_n = 800 if metric_id == 'TL13' else 2000
    if missing:
        decision = 'incomplete'
    elif formal and len(cases) != required_n:
        decision = 'insufficient_sample'
    else:
        low = statistics['interval95'][0]
        decision = 'pass' if (low > 0 if metric_id == 'TL13' else low >= -.02) else 'not_demonstrated'
    return {'metric_id': metric_id, 'query_kind': query_kind, 'case_count': len(cases),
            'trial_denominator': len(cases)*2*repeats, 'missing_trial_count': missing,
            'complete_case_count': len(complete), 'complete_case_ids': complete,
            'case_differences': differences, 'bounds': [mean(lower), mean(upper)],
            'statistics': statistics, 'decision': decision,
            'scope': 'paired endpoint only; requires separate mechanism and quality gates'}


def retrieval_metrics(queries, *, k=5, formal=False, required_categories=()):
    if type(k) is not int or k != 5:
        raise ValueError('frozen k is five')
    rows = list(queries)
    if formal and not required_categories:
        raise ValueError('formal retrieval requires preregistered categories')
    if formal and any(r.get('category') not in required_categories for r in rows):
        raise ValueError('unregistered retrieval category')
    seen, recalls, precisions, reciprocal, details = set(), [], [], [], []
    case_values = {}
    missing = 0
    total_hits = total_returned = total_relevant = 0
    for row in rows:
        if not isinstance(row['case_id'], str) or not row['case_id']:
            raise ValueError('preregistered case identity required')
        if row['id'] in seen:
            raise ValueError('duplicate registered query')
        seen.add(row['id'])
        relevant, returned = row['relevant_ids'], row['returned_ids']
        if relevant is None or returned is None:
            missing += 1
            # Eligibility unknown is retained conservatively as a potential
            # answerable opportunity, rather than removed from the case.
            if relevant is None or relevant:
                case_values.setdefault(row['case_id'], []).append(None)
            details.append({'id': row['id'], 'case_id': row['case_id'], 'status': 'missing', 'precision': None, 'recall': None, 'mrr': None})
            continue
        if len(returned) > k or len(set(returned)) != len(returned) or len(set(relevant)) != len(relevant):
            raise ValueError('invalid retrieval allocation or duplicate items')
        hits = sum(item in relevant for item in returned)
        total_hits += hits
        total_returned += len(returned)
        total_relevant += len(relevant)
        precision = hits/len(returned) if returned else None
        recall = hits/len(relevant) if relevant else None
        rank = next((i for i, item in enumerate(returned, 1) if item in relevant), None)
        rr = 1/rank if rank else 0
        if relevant:
            recalls.append(recall)
            reciprocal.append(rr)
            case_values.setdefault(row['case_id'], []).append(recall)
        if precision is not None:
            precisions.append(precision)
        details.append({'id': row['id'], 'case_id': row['case_id'], 'status': 'measured', 'precision': precision,
                        'recall': recall, 'mrr': rr if relevant else None,
                        'irrelevant_return_count': len(returned)-hits,
                        'answerable': bool(relevant)})
    lower = [mean(v if v is not None else 0 for v in vs) for vs in case_values.values()]
    upper = [mean(v if v is not None else 1 for v in vs) for vs in case_values.values()]
    macro = mean(lower) if lower and not missing else None
    category_cases = {category: len({r['case_id'] for r in rows if r.get('category') == category})
                      for category in required_categories}
    sufficient = not formal or all(n >= 20 for n in category_cases.values())
    return {'metric_id': 'TL05', 'k': k, 'query_denominator': len(rows),
            'missing_count': missing, 'answerable_measured_count': len(recalls),
            'macro_recall': macro, 'case_denominator': len(case_values),
            'macro_recall_bounds': [mean(lower), mean(upper)] if lower else None,
            'independent_cases_by_required_category': category_cases,
            'measured_micro_counts': {'hits': total_hits, 'returned': total_returned, 'relevant': total_relevant},
            'observed_subset_macro_recall': mean(recalls) if recalls else None,
            'observed_subset_macro_precision': mean(precisions) if precisions else None,
            'mrr': mean(reciprocal) if reciprocal and not missing else None,
            'decision': 'incomplete' if missing else 'insufficient_sample' if not sufficient else ('pass' if macro is not None and macro >= .9 else 'not_demonstrated'),
            'queries': details}


def latency_summary(samples):
    rows = list(samples)
    complete, censored = [], []
    for row in rows:
        _number(row['observed_ms'], 0)
        if type(row['completed']) is not bool:
            raise ValueError('completed boolean required')
        (complete if row['completed'] else censored).append(row['observed_ms'])
    return {'metric_id': 'TL10', 'sample_count': len(rows), 'completed_count': len(complete),
            'censored_count': len(censored), 'completed_fraction': len(complete)/len(rows) if rows else None,
            'completed_median_ms': median(complete) if complete else None,
            'completed_p95_ms': sorted(complete)[math.ceil(.95*len(complete))-1] if complete else None,
            'completed_max_ms': max(complete) if complete else None,
            'right_censored_observation_ms': censored, 'decision': 'descriptive'}


def cost_summary(attempts, *, correct_queries, currency=None):
    _integer(correct_queries)
    rows = list(attempts)
    ids = [r['attempt_id'] for r in rows]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('unique actual attempt identities required')
    if any(r['transport'] not in ('model', 'tool') for r in rows):
        raise ValueError('actual transport required')
    if any(r['money'] is not None for r in rows) and (not isinstance(currency, str) or not currency):
        raise ValueError('a single verified currency is required for monetary totals')
    fields = ('input_tokens', 'output_tokens', 'tool_calls', 'elapsed_ms', 'money')
    result = {}
    for name in fields:
        values = [r[name] for r in rows]
        for v in values:
            if v is not None:
                _number(v, 0)
        missing = sum(v is None for v in values)
        subtotal = sum(v for v in values if v is not None)
        result[name] = {'known_subtotal': subtotal, 'unknown_attempt_count': missing,
                        'total': None if missing else subtotal,
                        'per_correct_query': subtotal/correct_queries if correct_queries and not missing else None}
    return {'metric_id': 'TL15', 'actual_attempt_count': len(rows),
            'actual_model_call_count': sum(r['transport'] == 'model' for r in rows),
            'currency': currency,
            'correct_query_denominator': correct_queries, 'components': result,
            'decision': 'descriptive'}
