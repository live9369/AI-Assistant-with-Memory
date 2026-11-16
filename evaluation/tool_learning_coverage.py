"""Mandatory IM19 actual-execution linkage; static manifest is never execution.

The gate indexes immutable per-opportunity evidence from this one frozen run.
One execution may prove several clauses. Coverage cells, actual unique runs and
scientific samples are deliberately different quantities.
"""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'config/evaluation/tool-learning-mechanism-bindings-v0.1.json'
CATEGORIES=('reused-fixture','write-fault','g1','concurrency','semantic-source','temporal','correction','reprocessing','bounded-comparison','representation-upgrade-group','representation-upgrade','original-tool-source','derived-view','native-recall','confirmation','q10-statistics','q10-actual','frozen-proof','supervision')


def frozen_proof(case_id):
    from digital_life.application.learning.plan import inspect
    inspect(ROOT)
    plan=json.loads((ROOT/'docs/plan/tool-observation-learning-implementation-status-v0.1.json').read_text())
    manifest=json.loads((ROOT/'config/evaluation/tool-learning-mechanism-manifest-v0.1.json').read_text())
    case=next(c for c in manifest['decision_cases']if c['id']==case_id)
    if case_id not in ('Q03-D12','Q04-D12'):raise ValueError('not an explicitly static boundary proof')
    source=case['source'];path=ROOT/source['path'];raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if digest!=source['sha256']or source['quote']not in raw.decode():raise AssertionError('frozen source provenance changed')
    return {'case_id':case_id,'actual_source':source,'actual_sha256':digest,'frozen_contract':plan['frozen_contract'],'frozen_record_sha256':plan['frozen_record_sha256'],'status':'pass','scope':'Static frozen research/engineering-boundary provenance proof; not a runtime claim, future research result or empirical scientific observation.'}


def collect(folder):
    folder=Path(folder);catalog=json.loads(CATALOG.read_text());manifest=json.loads((ROOT/'config/evaluation/tool-learning-mechanism-manifest-v0.1.json').read_text())
    index=[];issues=[]
    expected={c['id']for group in ('future_cases','q10_checks','concurrency_branches','write_fault_branches','g1_scenarios','g1_materials')for c in manifest[group]}|{c['id']for c in manifest['decision_cases']if not c['proof_case_ids']}
    actual=[c['id']for c in catalog['obligations']]
    if len(actual)!=438 or len(set(actual))!=438 or set(actual)!=expected:issues.append({'reason':'catalog does not equal the exact frozen 438 unique obligation identities'})
    if catalog['status']!='frozen_for_execution':issues.append({'reason':'catalog is not frozen for actual execution'})
    for obligation in catalog['obligations']:
        for selector in obligation['selectors']:
            implementation=selector.get('implementation',{})
            if implementation.get('source_sha256') and hashlib.sha256((ROOT/implementation['path']).read_bytes()).hexdigest()!=implementation['source_sha256']:issues.append({'id':obligation['id'],'reason':'fixture implementation differs from reviewed catalog source'})
    for path in sorted(folder.glob('*.json')):
        raw=path.read_bytes();value=json.loads(raw)
        category=next((c for c in sorted(CATEGORIES,key=len,reverse=True)if path.name.startswith(c+'-')),None)
        if category is None:issues.append({'file':path.name,'reason':'unrecognized execution category'});continue
        if value.get('repeat')not in (1,2,3):issues.append({'file':path.name,'reason':'actual repeat identity absent'});continue
        valid=True
        if category=='reused-fixture':
            spec=value['fixture_source'];current=ROOT/spec['path']
            valid=value['status']=='pass'and bool(value['assertion_execution_trace'])and not value['failures']and not value['errors']and not value['skipped']and hashlib.sha256(current.read_bytes()).hexdigest()==spec['source_file_sha256']
            valid=valid and all('observation_error'not in s for s in value['synthetic_committed_snapshots'])
        elif category=='g1':valid=value['status']=='pass'and bool(value['assertions'])and all(a['passed']for a in value['assertions'])
        elif category=='write-fault':valid=value['transaction_rollback_verified']and value['prior_rows_preserved']and bool(value['injection_hits'])and value['before_digest']==value['after_digest']
        elif category=='concurrency':valid=value['actual_transport']and value['post_control_entry_count']==0 and (value['mode']!='process'or value['control_exitcode']==0)
        elif category in ('semantic-source','frozen-proof'):valid=value['status']=='pass'
        elif category=='q10-statistics':valid=bool(value['assertions'])and all(a['passed']for a in value['assertions'])
        if value.get('real_model_called',False):valid=False
        if not valid:issues.append({'file':path.name,'reason':'failed/invalid actual execution evidence'})
        index.append({'id':path.stem,'path':str(path.relative_to(ROOT))if path.is_relative_to(ROOT)else str(path),'sha256':hashlib.sha256(raw).hexdigest(),'category':category,'repeat':value['repeat'],'value':{k:value[k]for k in ('case_id','variant','mode','transport','control','stage','fixture_id','endpoint','scope')if k in value},'valid':valid})
    rows=[];by_id={};unique_referenced=set()
    for obligation in catalog['obligations']:
        evidence={str(r):[]for r in (1,2,3)};failures=[];details=[]
        for selector in obligation['selectors']:
            selected=[r for r in index if r['category']==selector['category']and all(r['value'].get(k)==v for k,v in selector['where'].items())]
            for repeat in (1,2,3):
                found=[r for r in selected if r['repeat']==repeat]
                if len(found)!=1 or not all(r['valid']for r in found):failures.append({'selector':selector,'repeat':repeat,'actual_execution_ids':[r['id']for r in found],'reason':'requires exactly one valid actual execution per unique fixture repeat'})
                for record in found:
                    ref={k:record[k]for k in ('id','path','sha256','category','repeat')}
                    evidence[str(repeat)].append(ref);unique_referenced.add(record['id'])
                    if record['category']=='reused-fixture':
                        details.append({'execution_id':record['id'],'assertion_trace_locator':'/assertion_execution_trace','committed_snapshot_locator':'/synthetic_committed_snapshots','sql_trace_locator':'/physical_sql_sample','fixture_id':record['value']['fixture_id']})
                    else:details.append({'execution_id':record['id'],'actual_domain_output_locator':'/','scope':record['value'].get('scope')})
        expected=obligation['expected_endpoint']
        if obligation['kind']in ('concurrency_branches','write_fault_branches','g1_scenarios','g1_materials'):
            for record in index:
                if record['value'].get('case_id')==obligation['id']and record['value'].get('endpoint')!=expected:failures.append({'execution_id':record['id'],'reason':'actual endpoint differs from frozen case endpoint'})
        passed=not failures and all(evidence[str(r)]for r in (1,2,3)) and obligation['mechanism_clause_review']=='reviewed_with_explicit_fixture_scope'
        row={'id':obligation['id'],'passed':passed,'source':obligation['source'],'expected_endpoint':expected,'repeats':evidence,'actual_assertion_and_domain_trace_locators':details,'gaps':failures};rows.append(row);by_id[row['id']]=row
    projected=[]
    for decision in catalog['decision_projections']:
        proofs=[by_id.get(k)for k in decision['proof_case_ids']]
        projected.append({'id':decision['id'],'source':decision['source'],'proof_case_ids':decision['proof_case_ids'],'passed':bool(proofs)and all(p is not None and p['passed']for p in proofs),'repeats':{str(r):list({e['id']:e for p in proofs if p for e in p['repeats'][str(r)]}.values())for r in (1,2,3)}})
    passed=len(rows)==438 and all(r['passed']for r in rows)and len(projected)==88 and all(r['passed']for r in projected)and not issues
    summary={'contract':'TL-IM19-ACTUAL-COVERAGE-1','passed':passed,'catalog_sha256':hashlib.sha256(CATALOG.read_bytes()).hexdigest(),'obligation_denominator':438,'covered_obligations':sum(r['passed']for r in rows),'obligation_repeat_denominator':1314,'covered_obligation_repeat_cells':sum(bool(row['repeats'][str(r)])and row['passed']for row in rows for r in (1,2,3)),'decision_denominator':107,'covered_decisions':sum(r['passed']for r in rows if r['id'].startswith(('Q01-D','Q02-D','Q03-D','Q04-D')))+sum(r['passed']for r in projected),'unique_execution_records_in_run':len(index),'unique_referenced_execution_records':len(unique_referenced),'independent_scientific_sample_count':None,'science_claim':'No real-model quality, world-truth accuracy, semantic contamination certification or statistical independent sample count is inferred from mechanism repetitions.','issues':issues,'obligations':rows,'decision_projections':projected}
    destination=folder.parent/'coverage.json'
    with destination.open('x')as stream:json.dump(summary,stream,ensure_ascii=False,indent=2);stream.write('\n')
    return summary
