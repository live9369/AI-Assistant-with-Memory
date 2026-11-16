"""IM17 static material integrity tests. Never imports runtime or runs any fixture."""
import copy
import hashlib
import json
import re
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV = 'config/evaluation/tool-learning-dev-v0.1.json'
MECH = 'config/evaluation/tool-learning-mechanism-manifest-v0.1.json'
CATEGORIES = ('direct_report', 'scope_unit_conversion', 'method_experience',
              'temporal_correction', 'conflict', 'unknown_insufficient',
              'history_text_episode', 'irrelevant_retrieval')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pointer(document, path):
    for part in path.split('/')[1:]:
        part = part.replace('~1', '/').replace('~0', '~')
        document = document[int(part)] if isinstance(document, list) else document[part]
    return document


def validate_materials(dev, mech, root=ROOT):
    """Validate a loaded material copy without modifying it or executing its plans."""
    require(dev['launch_state'] == mech['launch_state'] == 'blocked_before_start', 'launch gate')
    require(dev['label_policy']['formal_truth'] is False, 'DEV is not formal truth')
    require(dev['label_policy']['independent_review'] is False, 'no independent reviewer')
    require(dev['groups'] == ['E', 'N', 'O'] and dev['repeats'] == 1, 'DEV groups/repeats')
    cases = dev['cases']
    require(len(cases) == 24 and len({c['case_id'] for c in cases}) == 24, 'DEV24')
    require(Counter(c['category'] for c in cases) == Counter({x: 3 for x in CATEGORIES}), '8x3 categories')
    require(dev['trial_count_planned'] == 72, '72 DEV trials planned only')
    for c in cases:
        require(c['partition'] == 'DEV' and c['permanent_formal_exclusion'] is True, 'DEV exclusion')
        require(c['public_synthetic'] is True, 'public synthetic source')
        require(c['source_cluster'] and c['template_family'], 'family dependence declared')
        require(c['fixture_status'] == 'planned' and c['run_status'] == 'not_run', 'DEV unexecuted')
        require(c['actual_trace'] is None and c['actual_result'] is None, 'no invented results')
        qs = c['query_input']
        require(len(qs) == 3 and {q['kind'] for q in qs} == {'same_observation','new_question','boundary_unknown'}, 'three fixed queries')
        qids = {q['query_id'] for q in qs}
        labels = c['developer_labels']
        require(labels['visibility'] == 'public_development_only' and labels['independent_review'] is False, 'DEV labels visible')
        require(set(labels['answers']) == qids and all(labels['answers'].values()), 'complete DEV answer labels')
        require(set(labels['eligible_relevant_sets']) == qids, 'prelabel all relevant sets')
        catalog = {r['ref_id'] for r in c['expected_reference_catalog']}
        require(all(set(rs) <= catalog for rs in labels['eligible_relevant_sets'].values()), 'relevant refs registered in expected catalog')
        require(all(r['not_actual_db_object'] and r['fixture_status'] == 'planned' for r in c['expected_reference_catalog']), 'expected refs not actual DB evidence')
        require(labels['correct_endpoint'] and labels['major_errors'] and labels['required_limitations'], 'endpoint/errors/limits')
        require('developer_labels' not in c['learning_input'] and 'answers' not in c['learning_input'], 'label runtime isolation')
        require(all(q['k'] == 5 and q['text'] for q in qs), 'fixed k and prompts')
        for s in c['source_refs']:
            require((root / s['path']).is_file(), 'DEV source exists')
    # Exact source files, quotes and pointers, not inferred broad coverage counts.
    def source_check(v):
        if isinstance(v, dict):
            if 'path' in v and 'sha256' in v:
                p = root / v['path']
                require(p.is_file(), 'source missing: ' + v['path'])
                require(hashlib.sha256(p.read_bytes()).hexdigest() == v['sha256'], 'source digest: ' + v['path'])
                if 'quote' in v:
                    require(p.read_text().splitlines()[v['line'] - 1] == v['quote'], 'source quote')
                if 'json_pointer' in v:
                    pointer(json.loads(p.read_text()), v['json_pointer'])
                if 'oracle_source' in v:
                    lines = p.read_text().splitlines()
                    n = len(v['oracle_source'].splitlines())
                    require('\n'.join(lines[v['line']-1:v['line']-1+n]) == v['oracle_source'], 'oracle code text')
            for x in v.values():
                source_check(x)
        elif isinstance(v, list):
            for x in v:
                source_check(x)
    source_check(dev)
    source_check(mech)
    decision_ids, future_ids = set(), set()
    expected_future_by_q = {}
    for q in range(1,10):
        p = root / f'docs/architecture/tool-observation-learning-q{q:02}-decision-v0.1.md'
        future_count = 0
        for line in p.read_text().splitlines():
            cols = [x.strip() for x in line.split('|')[1:-1]] if line.startswith('|') else []
            if cols and re.fullmatch(r'(?:Q\d\d-)?D\d\d', cols[0]):
                decision_ids.add(cols[0] if cols[0].startswith('Q') else f'Q{q:02}-{cols[0]}')
            if cols and re.fullmatch(r'A\d\d', cols[0]):
                future_ids.add(f'Q{q:02}-{cols[0]}')
                future_count += 1
        expected_future_by_q[f'Q{q:02}'] = future_count
    ds, fs = mech['decision_cases'], mech['future_cases']
    require(len(ds) == len(decision_ids) == 107 and {x['id'] for x in ds} == decision_ids, '107 exact decisions')
    require(len(fs) == len(future_ids) == 184 and {x['id'] for x in fs} == future_ids, '184 exact future prompts')
    require(mech['summary']['future_by_q'] == expected_future_by_q, 'future counts by Q')
    for d in ds:
        require(d['requirement'] == d['source']['quote'].split('|')[2].strip(), 'decision exact requirement')
        require(set(d['proof_case_ids']) <= future_ids, 'decision proof links')
        if not d['proof_case_ids']:
            pp = d['proof_plan']
            require(pp['positive_input'] and pp['negative_input'] and pp['expected_endpoint'], 'explicit positive/negative proof')
    for f in fs:
        cols = [x.strip() for x in f['source']['quote'].split('|')[1:-1]]
        require([f['prompt'], f['expected_endpoint']] == cols[1:3], 'future exact prompt/endpoint')
        require(f['fixture_requirements']['mutation'] == f['prompt'], 'future fixture mutation')
    checks = mech['q10_checks']
    require(len(checks) == 20 and {x['id'] for x in checks} == {f'Q10-C{i:02}' for i in range(1,21)}, 'Q10 twenty checks')
    raw = next(l for l in (root/'docs/architecture/tool-observation-learning-q10-decision-v0.1.md').read_text().splitlines() if l.startswith('Q11需至少覆盖：'))
    require([x['clause'] for x in checks] == raw.removeprefix('Q11需至少覆盖：').rstrip('。').split('；'), 'Q10 exact clauses')
    cons = mech['concurrency_branches']
    expected = {(mode,t,c,s) for mode in ('thread','process') for t in ('model','tool') for c in ('stop','source_revocation','activity_cancel') for s in ('before_reservation','reserved_before_callback','callback_in_flight','after_result')}
    require(len(cons) == 48 and {(x['mode'],x['transport'],x['control'],x['stage']) for x in cons} == expected, '48 separate concurrency branches')
    # Historical and inherited G1 manifests must all be retained, including the six old failures.
    expected_g = set()
    for version in ('1','1.1','1.2'):
        path = f'evaluation/exploration/materials/scenarios-v{version}.json'
        specs = json.loads((root/path).read_text())['scenarios']
        expected_g |= {'G1-S-'+s['scenario_id'] for s in specs}
        for i,s in enumerate(specs):
            item = next((g for g in mech['g1_scenarios'] if g['id'] == 'G1-S-'+s['scenario_id']), None)
            require(item is not None and item['legacy_spec'] == s, 'G1 inherited exact spec')
            require(any(r['path'] == path and r['json_pointer'] == f'/scenarios/{i}' for r in item['source_versions']), 'G1 version provenance')
    require(len(mech['g1_scenarios']) == 65 and {x['id'] for x in mech['g1_scenarios']} == expected_g, 'G1 union65')
    originals = json.loads((root/'evaluation/exploration/materials/cases-v1.json').read_text())['cases']
    require(len(mech['g1_materials']) == 60 and {x['legacy_case_id'] for x in mech['g1_materials']} == {c['case_id'] for c in originals}, 'G1 all60 materials')
    hist = mech['g1_baseline']['original_historical_result']
    require(hist['state'] == 'fail' and hist['failed'] == 6 and len(hist['failure_scenario_ids']) == 6, 'old failures preserved')
    require(set(hist['failure_scenario_ids']) <= expected_g and mech['g1_baseline']['current_revalidation'] == 'not_run', 'no retrospective pass')
    writes = mech['write_fault_branches']
    require(len(writes) == 42 and all(len(x['covers']) == 1 and set(x['covers']) <= future_ids for x in writes), 'explicit write fault map')
    executions = fs + checks + cons + mech['g1_scenarios'] + mech['g1_materials'] + writes
    repeat_ids = []
    for x in ds + executions:
        require(x['fixture_status'] == 'planned' and x['run_status'] == 'not_run', 'planned fixture not execution coverage')
        require(x['actual_trace'] is None and x['actual_result'] is None, 'no generated trace/result')
        require(x['metric_ids'] and set(x['metric_ids']) <= {f'TL{i:02}' for i in range(1,17)}, 'TL mapping')
        f = x.get('fixture_requirements', x.get('proof_plan'))
        require(f is not None and f['handler'] is None, 'no implemented fixture claim')
        if x in executions:
            require(f['mutation'] and f['injection_point'] and x['expected_endpoint'], 'concrete fixture/endpoint')
            require(len(x['repeat_ids']) == 3, 'three repeats each execution')
            repeat_ids.extend(x['repeat_ids'])
        elif not x['proof_case_ids']:
            require(len(x['proof_plan']['repeat_ids']) == 3, 'proof three repeats')
            repeat_ids.extend(x['proof_plan']['repeat_ids'])
    count = len(executions) + sum(not d['proof_case_ids'] for d in ds)
    require(count == mech['summary']['execution_item_count'] == 438, '438 planned execution items')
    require(len(repeat_ids) == len(set(repeat_ids)) == mech['summary']['planned_repeat_count'] == 1314, '1314 distinct planned repeats')
    require(mech['summary']['models_called'] == mech['summary']['independent_formal_labels_created'] == 0, 'no model/formal truth')
    require(mech['execution_blockers'] and dev['missing_launch_requirements'], 'explicit startup blockers')
    return {'decisions':len(ds),'future_cases':len(fs),'execution_items':count,'planned_repeats':len(repeat_ids)}


class ToolLearningMaterialsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev = json.loads((ROOT/DEV).read_text())
        cls.mech = json.loads((ROOT/MECH).read_text())

    def check_bad(self, change):
        d,m = copy.deepcopy(self.dev),copy.deepcopy(self.mech)
        change(d,m)
        with self.assertRaises((ValueError, KeyError, StopIteration)):
            validate_materials(d,m)

    def test_complete_static_material_package(self):
        before = json.dumps([self.dev,self.mech],sort_keys=True)
        self.assertEqual(validate_materials(self.dev,self.mech)['planned_repeats'],1314)
        self.assertEqual(before,json.dumps([self.dev,self.mech],sort_keys=True))

    def test_missing_dev_category(self):
        self.check_bad(lambda d,m:d['cases'].pop())

    def test_dev_cannot_be_formal_truth(self):
        self.check_bad(lambda d,m:d['label_policy'].update(formal_truth=True))

    def test_missing_query_label(self):
        self.check_bad(lambda d,m:d['cases'][0]['developer_labels']['answers'].pop(next(iter(d['cases'][0]['developer_labels']['answers']))))

    def test_unregistered_relevant_ref(self):
        self.check_bad(lambda d,m:d['cases'][0]['developer_labels']['eligible_relevant_sets'].update({'DEV-01-01:new':['invented']}))

    def test_missing_decision(self):
        self.check_bad(lambda d,m:m['decision_cases'].pop())

    def test_missing_future_case(self):
        self.check_bad(lambda d,m:m['future_cases'].pop())

    def test_changed_expected_endpoint(self):
        self.check_bad(lambda d,m:m['future_cases'][0].update(expected_endpoint='all accepted'))

    def test_missing_q10_type(self):
        self.check_bad(lambda d,m:m['q10_checks'].pop())

    def test_duplicate_process_branch(self):
        self.check_bad(lambda d,m:m['concurrency_branches'].__setitem__(24,copy.deepcopy(m['concurrency_branches'][0])))

    def test_missing_repeat(self):
        self.check_bad(lambda d,m:m['concurrency_branches'][0]['repeat_ids'].pop())

    def test_no_fake_execution_success(self):
        self.check_bad(lambda d,m:m['future_cases'][0].update(run_status='passed',actual_result={'pass':True}))

    def test_no_implemented_handler_claim(self):
        self.check_bad(lambda d,m:m['concurrency_branches'][0]['fixture_requirements'].update(handler='pretend.run'))

    def test_missing_inherited_g1(self):
        self.check_bad(lambda d,m:m['g1_scenarios'].pop())

    def test_old_failures_not_overwritten(self):
        self.check_bad(lambda d,m:m['g1_baseline']['original_historical_result'].update(state='pass'))

    def test_source_digest_tamper(self):
        self.check_bad(lambda d,m:m['sources'][0].update(sha256='0'*64))

    def test_launch_remains_blocked(self):
        self.check_bad(lambda d,m:m.update(launch_state='ready'))

    def test_no_labels_in_learning_projection(self):
        self.check_bad(lambda d,m:d['cases'][0]['learning_input'].update(answers={'hidden':'answer'}))


if __name__ == '__main__':
    unittest.main()
