"""Quality metrics with case-cluster uncertainty and non-negotiable review gates."""
from collections import defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path
import random
from evaluation.exploration.g2.review import read_trials,load_reviews,digest,write
from evaluation.exploration.aggregate import inspect_trial

RATIO_FIELDS={'M01':('question','autonomous',False),'M02':('question','verifiable',False),
 'M04':('investigation','informative',False),'M05':('counterexample','responsive',False),
 'M06':('resolution','verified_resolved',True),'M07':('gap','covered',False),'M08':('investigation','redundant',False)}

def cluster_ratio(rows,bootstrap=10000):
    """Rows are case/repeat numerator-denominator; repeats never become independent cases."""
    by_case=defaultdict(list)
    for row in rows:
        if row['denominator']>0:by_case[row['case_id']].append(row['numerator']/row['denominator'])
    values=[sum(v)/len(v) for _,v in sorted(by_case.items())]
    if not values:return {'value':None,'interval':None,'independent_cases':0}
    point=sum(values)/len(values);rng=random.Random(20261108)
    draws=sorted(sum(values[rng.randrange(len(values))] for _ in values)/len(values) for _ in range(bootstrap))
    return {'value':point,'interval':[draws[int(bootstrap*.025)],draws[min(bootstrap-1,int(bootstrap*.975))]],'independent_cases':len(values)}

def aggregate(run,review_files=(),adjudication=None):
    run=Path(run);manifest,rows=read_trials(run)
    packets=json.loads((run/'review/packets.json').read_text());mapping=json.loads((run/'review/private-unit-map.json').read_text())
    reviews=load_reviews(run,review_files,adjudication);labels=reviews['consensus'];units={u['unit_id']:u for u in packets['units']}
    trial_meta={s['trial_id']:s for s in manifest['trials']};metrics=[];per_trial={};unmeasured=[]
    def base(mid,unit='ratio'):
        return {'protocol_id':'AE-EVAL-1.0','metric_id':mid,'run_id':manifest['run_id'],'arm':'full','scope':manifest['split'],'unit':unit,
          'numerator':None,'denominator':None,'value':None,'status':'not_run','missing_count':0,'independent_cases':0,'interval':None,
          'method':'case-equal macro, trial ratios averaged within case; 10000 case-cluster bootstrap, seed20261108; no IID-repeat assumption',
          'evidence_refs':['manifest.json','review/packets.json'],'review_version':reviews['mode']}
    computed={}
    for mid,(kind,field,inverse) in RATIO_FIELDS.items():
        metric=base(mid);counts={tid:{'case_id':meta['case_id'],'stratum':meta['stratum'],'repeat':meta['repeat'],'numerator':0,'denominator':0,'missing':0} for tid,meta in trial_meta.items()}
        for uid,info in mapping.items():
            if info['kind']!=kind:continue
            count=counts[info['trial_id']];count['denominator']+=1
            if uid not in labels or field not in labels[uid]:count['missing']+=1
            else:count['numerator']+=int(not labels[uid][field] if inverse else labels[uid][field])
        missing=sum(c['missing'] for c in counts.values());denominator=sum(c['denominator'] for c in counts.values());numerator=sum(c['numerator'] for c in counts.values())
        metric.update(denominator=denominator,missing_count=missing,numerator=None if missing else numerator)
        if missing:metric['status']='missing'
        elif denominator==0:metric['status']='not_applicable'
        else:
            result=cluster_ratio(list(counts.values()));metric.update(result)
            metric['status']='insufficient_sample' if result['independent_cases']<20 else 'measured'
            metric['micro_value']=numerator/denominator
        metric['strata']={g:cluster_ratio([v for v in counts.values() if v['stratum']==g]) for g in 'ABCDEF'} if not missing else None
        metric['single_review_not_formal']=reviews['mode']!='independent_double'
        if mid=='M05':metric['opportunity_rule']='one pre-registered main-gap counterexample per eligible case; reviewer binds to generated question in evidence references; unacquired opportunity remains denominator'
        per_trial[mid]=counts;computed[mid]=metric
    audits=[];evidence_missing=[]
    for row in rows:
        if row['missing']:evidence_missing.append(row['spec']['trial_id']);continue
        audits.append(inspect_trial(run/'trials'/row['spec']['trial_id']))
    for mid in ['M03','M11','M13']:
        metric=base(mid,'ratio' if mid=='M03' else 'count')
        metric['independent_cases']=len({r['spec']['case_id'] for r in rows if not r['missing']});metric['missing_count']=len(evidence_missing)
        if evidence_missing:metric['status']='missing'
        elif mid=='M03':
            d=sum(a['refs'] for a in audits);n=sum(a['refs']-a['illegal'] for a in audits)
            metric.update(numerator=n,denominator=d,value=n/d if d else None,status='measured' if d else 'not_applicable',method='accepted reference membership and source existence from recorded requests')
        else:
            count=sum(len(a['post_stop']) if mid=='M11' else len(a['budget_violations']) for a in audits)
            metric.update(value=count,status='measured',method='raw dispatch trace / reservation and activity budget audit')
        computed[mid]=metric
    public={c['case_id']:c for c in json.loads((run/'public.json').read_text())['cases']}
    restart_denominator=0;restart_numerator=0;restart_missing=0;restart_cases=set()
    for row in rows:
        planned=[e for e in public[row['spec']['case_id']]['world_events'] if e.get('operation')=='restart']
        if not planned:continue
        restart_denominator+=len(planned);restart_cases.add(row['spec']['case_id'])
        if row['missing']:restart_missing+=len(planned);continue
        gap_count=per_trial['M07'][row['spec']['trial_id']]
        if gap_count['missing']:restart_missing+=len(planned);continue
        restarts=[e for e in row['trace'] if e['kind']=='restart']
        observations=[row['artifacts'][e['payload_artifact_id']] for e in sorted(row['snapshot']['runtime_events'],key=lambda e:e['event_seq']) if e['event_type']=='exploration.observed']
        for restart in restarts[:len(planned)]:
            prior_refs={o['evidence'] for o in observations[:restart['observed_count']]}
            resumed=any(q['runtime_epoch']>=restart['epoch'] and prior_refs&{o['evidence_ref'] for o in row['artifacts'][q['request_artifact_id']].get('exploration',{}).get('observations',[])} for q in row['snapshot']['thought_requests'])
            if restart['problem_identity_preserved'] and resumed and gap_count['numerator']==gap_count['denominator'] and gap_count['denominator']>0:restart_numerator+=1
    m9=base('M09');m9.update(numerator=None if restart_missing else restart_numerator,denominator=restart_denominator,value=restart_numerator/restart_denominator if restart_denominator and not restart_missing else None,
        status='missing' if restart_missing else 'insufficient_sample' if restart_denominator else 'not_applicable',independent_cases=len(restart_cases),missing_count=restart_missing,
        method='pre-registered G2 restart, H identity record + resumed request evidence + reviewed gap resolution; small real-behavior diagnostic, not pooled with G1')
    computed['M09']=m9
    m14=base('M14','cost_components');effective=computed['M04']['numerator'];summary=[r['result'].get('summary') or {} for r in rows if not r['missing']]
    calls=sum(s.get('real_model_calls',0) for s in summary);known_tokens=sum(s.get('observed_tokens',0) for s in summary)
    unknown=sum(s.get('unknown_usage_calls',0) for s in summary);tool_calls=sum(s.get('tool_calls',0) for s in summary)
    m14.update(status='missing' if effective is None else 'not_applicable' if effective==0 else 'measured',denominator=effective,
      components={'model_port_calls':calls,'tool_calls':tool_calls,'known_actual_tokens':known_tokens,'actual_tokens':None if unknown or evidence_missing else known_tokens,'unknown_usage_calls':unknown,
      'wall_seconds':sum(s.get('wall_seconds',0) for s in summary),'per_effective_model_calls':calls/effective if effective else None,
      'per_effective_tool_calls':tool_calls/effective if effective else None,'per_effective_tokens':known_tokens/effective if effective and not unknown and not evidence_missing else None})
    computed['M14']=m14
    m15=base('M15','brier_diagnostic');brier=[]
    first_question_investigation=set()
    snapshots={r['spec']['trial_id']:r for r in rows if not r['missing']}
    for uid,info in mapping.items():
        if info['kind']!='investigation' or uid not in labels:continue
        row=snapshots.get(info['trial_id'])
        if not row:continue
        events=row['snapshot']['runtime_events'];arts=row['artifacts']
        binding=next((arts[e['payload_artifact_id']] for e in events if e['event_type']=='exploration.bound' and arts[e['payload_artifact_id']]['activity']==info['object_key']),None)
        if not binding:continue
        key=(info['trial_id'],binding['question_id'])
        if key in first_question_investigation:continue
        first_question_investigation.add(key)
        q=next(q for q in row['snapshot']['questions'] if q['id']==binding['question_id'])
        brier.append((q['expected_gain']-int(labels[uid]['informative']))**2)
    m15.update(value=sum(brier)/len(brier) if brier else None,status='diagnostic' if brier else 'missing',denominator=len(brier),method='selected-candidate-only Brier diagnostic; expected_gain is not a validated probability')
    computed['M15']=m15
    for i in range(1,17):
        mid=f'M{i:02}';metric=computed.get(mid,base(mid))
        if mid=='M12':metric.update(unit='milliseconds',status='not_evaluable',method='no unified stop-confirmation interface')
        if mid=='M10':metric.update(status='not_applicable',method='no G2 pre-registered replay-fault denominator; G1 provenance reported separately')
        metrics.append(metric)
    blockers=[]
    if not manifest['g0']['successful'] or manifest['g1']['gates']['G1']!='pass':blockers.append('G0/G1 prerequisite not passed')
    if manifest.get('actor',{}).get('backend') not in ('codex_cli','ollama','llamacpp') or any(not r.get('result',{}).get('real_model_used') for r in rows if not r['missing']):blockers.append('real actor provenance absent or fixture outputs')
    if manifest['mode']!='full':blockers.append('pilot development cases, not formal sample')
    if len({t['case_id'] for t in manifest['trials']})<60:blockers.append('fewer than 60 formal cases')
    if manifest['sampling']['repeats']!=3:blockers.append('not three formal repetitions')
    if reviews['independent_reviewers']<2:blockers.append('fewer than two independent blind reviewers')
    if reviews['conflicts']:blockers.append('unresolved reviewer disagreements')
    if evidence_missing:blockers.append('missing raw evidence')
    if any(m['status'] in ('missing','insufficient_sample','not_applicable') for m in metrics if m['metric_id'] in RATIO_FIELDS):blockers.append('quality gate metrics missing, undefined or fewer than 20 independent cases')
    formal_guard=json.loads((run/'formal-instance-guard.json').read_text())
    if not formal_guard['unchanged']:blockers.append('formal instance changed')
    baseline_version=manifest.get('runtime_protocol','AE-RUNTIME-1.1').split('AE-RUNTIME-')[-1]
    baseline=json.loads((run/('source-snapshot/docs/architecture/autonomous-exploration-baseline-v'+baseline_version+'.json')).read_text())
    threshold_results={}
    for mid,policy in baseline['quality_policy'].items():
        metric=next((m for m in metrics if m['metric_id']==mid),None)
        if mid not in RATIO_FIELDS or metric is None:continue
        if metric['status']!='measured':threshold_results[mid]='not_evaluable';continue
        value=metric['value'];lower,upper=metric['interval'];ok=True
        if 'point_min' in policy:ok &= value>=policy['point_min']
        if 'point_max' in policy:ok &= value<=policy['point_max']
        if 'ci_lower_min' in policy:ok &= lower>=policy['ci_lower_min']
        if 'ci_upper_max' in policy:ok &= upper<=policy['ci_upper_max']
        threshold_results[mid]='pass' if ok else 'fail'
    if any(a['illegal'] or a['multiple_acceptance'] or a['post_stop'] or a['duplicate_reads'] or a['budget_violations'] for a in audits):blockers.append('engineering invariant violation')
    gate='not_evaluable' if blockers else 'fail' if 'fail' in threshold_results.values() else 'pass'
    mechanism={'raw_candidate_proposals':0,'filtered_candidates':0,'filter_reasons':{},'evidence_reuses':0,'reopened_questions':0,'admitted_question_ids':0}
    for row in rows:
        if row['missing']:continue
        mechanism['admitted_question_ids']+=len(row['snapshot'].get('questions',[]))
        for result in row['snapshot'].get('thought_results',[]):
            if result['acceptance']=='accepted':mechanism['raw_candidate_proposals']+=len(row['artifacts'][result['response_artifact_id']].get('exploration',{}).get('candidates',[]))
        for event in row['snapshot'].get('runtime_events',[]):
            kind=event['event_type'];content=row['artifacts'].get(event['payload_artifact_id'],{})
            if kind=='exploration.candidate_filtered':
                mechanism['filtered_candidates']+=1;reason=content['reason'];mechanism['filter_reasons'][reason]=mechanism['filter_reasons'].get(reason,0)+1
            if kind=='exploration.evidence_reused':mechanism['evidence_reuses']+=1
            if kind=='exploration.question_reopened':mechanism['reopened_questions']+=1
    report={'mechanism_diagnostics':mechanism,'analysis_version':'AE-G2-ANALYSIS-1.2','analysis_sources':{'aggregate.py':digest(Path(__file__)),'review.py':digest(Path(__file__).with_name('review.py'))},'run_id':manifest['run_id'],'protocol_id':'AE-EVAL-1.0','runtime_protocol':manifest.get('runtime_protocol','AE-RUNTIME-1.1'),'mode':manifest['mode'],
      'gates':{'G0':'pass' if manifest['g0']['successful'] else 'fail','G1':manifest['g1']['gates']['G1'],'G2':gate,'G3':'not_run'},
      'quality_blockers':blockers,'threshold_results':threshold_results,'metrics':metrics,'review':{k:v for k,v in reviews.items() if k!='consensus'},
      'trials_planned':len(manifest['trials']),'trials_completed_without_runtime_error':sum(not r['missing'] and r['result']['status']=='completed' for r in rows),
      'failed_trials':[{'trial_id':r['spec']['trial_id'],'result':r.get('result')} for r in rows if r['missing'] or r['result']['status']!='completed'],
      'evidence_missing':evidence_missing,'formal_instance_unchanged':formal_guard['unchanged'],'aggregated_utc':datetime.now(timezone.utc).isoformat(),
      'measurement_scope':'pilot exploratory only' if manifest['mode']=='pilot' else 'full group; G3 ablations not run'}
    write(run/'quality-per-trial.json',per_trial);write(run/'quality-aggregate.json',report)
    return report
