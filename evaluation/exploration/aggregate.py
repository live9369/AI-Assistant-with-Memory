"""Recompute G1 metrics from hashed evidence; never substitute fixture scores for G2."""
import hashlib
from datetime import datetime,timezone
import json
from pathlib import Path

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def inspect_trial(directory):
    directory=Path(directory); result=json.loads((directory/'result.json').read_text())
    if not {'snapshot.json','artifacts.json','trace.json'}<=set(result['evidence_hashes']): raise ValueError('Required evidence hash missing')
    for name,checksum in result['evidence_hashes'].items():
        if digest(directory/name)!=checksum: raise ValueError('Evidence checksum mismatch: '+str(directory/name))
    snapshot=json.loads((directory/'snapshot.json').read_text()); artifacts=json.loads((directory/'artifacts.json').read_text()); trace=json.loads((directory/'trace.json').read_text())
    requests={r['id']:r for r in snapshot['thought_requests']}
    accepted={}; refs=0; illegal=0
    for r in snapshot['thought_results']:
        if r['acceptance']!='accepted': continue
        accepted[r['request_id']]=accepted.get(r['request_id'],0)+1
        request=requests[r['request_id']]; payload=artifacts[request['request_artifact_id']]; output=artifacts[r['response_artifact_id']]
        if 'exploration' not in output: continue
        e=output['exploration']; cited=e['evidence_refs']+[ref for c in e['candidates'] for ref in c['evidence_refs']]
        available=set(payload['exploration']['allowed_evidence_refs'])
        sources={v['id'] for v in snapshot['evidence_items']}|{v['id'] for v in snapshot['memory_revisions']}
        refs+=len(cited); illegal+=sum(ref not in available or ref not in sources for ref in cited)
    dispatches=[e for e in trace if e['kind']=='dispatch']; stops=[e for e in trace if e['kind']=='stop_committed']
    post=[e for e in dispatches if stops and e['monotonic_ns']>stops[0]['monotonic_ns']]
    duplicate=[]; seen=set()
    for e in dispatches:
        if e['transport']=='tool':
            if e['operation_id'] in seen: duplicate.append(e['operation_id'])
            seen.add(e['operation_id'])
    violations=[]
    for account in snapshot['activity_budget_accounts']:
        rows=[r for r in snapshot['budget_reservations'] if r['activity_id']==account['activity_id'] and r['state']!='released']
        used={'token_limit':sum(r['reserved_tokens'] for r in rows),'attempt_limit':len(rows),'tool_call_limit':sum(r['reserved_tool_calls'] for r in rows)}
        for key,value in used.items():
            if value>account[key]: violations.append({'kind':key,'used':value,'limit':account[key]})
    bindings=[]; configs={}
    for e in snapshot['runtime_events']:
        if e['event_type']=='exploration.configured': configs[e['id']]=artifacts[e['payload_artifact_id']]
        if e['event_type']=='exploration.bound': bindings.append(artifacts[e['payload_artifact_id']])
    for generation,cfg in configs.items():
        count=sum(b['generation']==generation for b in bindings)
        if count>cfg['max_activities']: violations.append({'kind':'activities'})
    for b in bindings:
        if sum(r['activity_id']==b['activity'] for r in requests.values())>b['max_rounds']: violations.append({'kind':'rounds'})
    for request in requests.values():
        if sum(a['request_id']==request['id'] for a in snapshot['thought_attempts'])>request['attempt_limit']: violations.append({'kind':'request-attempts'})
    for q in snapshot['questions']:
        if q['visits']>2: violations.append({'kind':'question-visits'})
    if len(snapshot['questions'])>256: violations.append({'kind':'capacity'})
    # No manual-fixture score or model self-assessment enters a quality metric.
    return dict(result=result,refs=refs,illegal=illegal,multiple_acceptance=sum(max(0,n-1) for n in accepted.values()),
                post_stop=post,duplicate_reads=duplicate,budget_violations=violations,
                model_attempts=len(snapshot['thought_attempts']),tool_attempts=len(snapshot['action_attempts']),stop_count=len(stops))

def aggregate(run_directory):
    root=Path(run_directory); manifest=json.loads((root/'manifest.json').read_text())
    if digest(root/'manifest.json')!=(root/'manifest.sha256').read_text().strip(): raise ValueError('Run manifest checksum mismatch')
    if digest(root/'baseline.json')!=manifest['baseline_sha256']: raise ValueError('Baseline checksum mismatch')
    if digest(root/'cases.json')!=manifest['dataset_sha256']: raise ValueError('Material checksum mismatch')
    if digest(root/'evidence-index.json')!=(root/'evidence-index.sha256').read_text().strip(): raise ValueError('Evidence index checksum mismatch')
    index=json.loads((root/'evidence-index.json').read_text())
    guard=json.loads((root/'formal-instance-guard.json').read_text())
    formal_unchanged=guard['unchanged'] and guard['before']==guard['after'] and guard['before']==manifest['formal_instance_before']
    rows=[]; evidence_missing=[]
    execution_failures=[]
    for trial in manifest['trials']:
        directory=root/'trials'/trial['trial_id']
        try:
            entry=index[trial['trial_id']]
            if entry['watchdog_fired'] or entry['exit_code']!=0: execution_failures.append(trial['trial_id'])
            if digest(directory/'result.json')!=entry['result_sha256']: raise ValueError('Trial result checksum mismatch')
            row=inspect_trial(directory)
            if row['result']['trial_id']!=trial['trial_id']: raise ValueError('Trial identity mismatch')
            rows.append(row)
        except (OSError,KeyError,ValueError) as error: evidence_missing.append({'trial_id':trial['trial_id'],'error':str(error)})
    baseline=json.loads((root/'baseline.json').read_text())
    metrics=[]
    def measured(identifier,n,d=None,unit='count',components=None,status='measured'):
        metric={'protocol_id':'AE-EVAL-1.0','metric_id':identifier,'run_id':manifest['run_id'],'arm':'g1-scripted',
         'scope':'workspace-read','unit':unit,'numerator':n if d is not None else None,'denominator':d,
         'value':(n/d if d else None) if d is not None else n,'status':status if d is None or d else 'not_applicable',
         'missing_count':len(evidence_missing),'independent_cases':len({r['result']['case_id'] for r in rows}),
         'interval':None,'method':'exact isolated-engineering counts; no population inference',
         'evidence_refs':['manifest.json']+['trials/'+r['result']['trial_id']+'/result.json' for r in rows],
         'review_version':'g1-machine-audit-v1','components':components}
        if evidence_missing: metric['status']='missing'; metric['value']=None
        return metric
    recovery=[r for r in rows if r['result'].get('recovery_scenario')]
    recovery_pass=sum(r['result']['status']=='pass' for r in recovery)
    replay=[r for r in rows if r['result'].get('read_replay_opportunity')]
    compute={
      'M03':measured('M03',sum(r['refs']-r['illegal'] for r in rows),sum(r['refs'] for r in rows),'ratio'),
      'M09':measured('M09',recovery_pass,len(recovery),'ratio'),
      'M10':measured('M10',sum(len(r['duplicate_reads']) for r in replay),len(replay),'ratio',components={'scope':'read dispatch replay only','write_side_effect_status':'not_evaluable'}),
      'M11':measured('M11',sum(len(r['post_stop']) for r in rows),components={'stop_boundaries':sum(r['stop_count'] for r in rows),'violations':[{'trial_id':r['result']['trial_id'],'dispatch':d} for r in rows for d in r['post_stop']]}),
      'M13':measured('M13',sum(len(r['budget_violations']) for r in rows),components={'violations':[{'trial_id':r['result']['trial_id'],'violation':v} for r in rows for v in r['budget_violations']]})}
    compute['M09']['independent_cases']=len({r['result']['case_id'] for r in recovery})
    compute['M10']['independent_cases']=len({r['result']['case_id'] for r in replay})
    compute['M11']['independent_cases']=len({r['result']['case_id'] for r in rows if r['stop_count']})
    for definition in baseline['metrics']:
        identifier=definition['id']
        if identifier in compute: metrics.append(compute[identifier]); continue
        m=measured(identifier,None,status='not_run',unit=definition['unit'])
        m.update(numerator=None,denominator=None,value=None,independent_cases=0)
        if identifier=='M12': m.update(status='not_evaluable',method='No runtime stop-confirmation interface; no fixed-latency claim.')
        if identifier=='M14':
            m.update(status='not_evaluable',method='Effective-exploration denominator requires independent labels; raw mechanism costs only.',components={'raw_model_attempts':sum(r['model_attempts'] for r in rows),'raw_tool_attempts':sum(r['tool_attempts'] for r in rows),'actual_tokens':None,'per_effective_investigation':None})
        metrics.append(m)
    failures=[{'trial_id':r['result']['trial_id'],'status':r['result']['status'],'error':r['result'].get('error')} for r in rows if r['result']['status']!='pass']
    invariants={'illegal_accepted_references':sum(r['illegal'] for r in rows),'multiple_acceptances':sum(r['multiple_acceptance'] for r in rows),
     'post_stop_dispatches':sum(len(r['post_stop']) for r in rows),'duplicate_read_dispatches':sum(len(r['duplicate_reads']) for r in rows),'budget_violations':sum(len(r['budget_violations']) for r in rows)}
    g1='fail' if failures or execution_failures or not formal_unchanged or any(invariants.values()) else 'not_evaluable' if evidence_missing else 'pass'
    if not manifest['g0']['successful']: g1='not_evaluable'
    completion=json.loads((root/'completion.json').read_text()) if (root/'completion.json').is_file() else {'status':'missing_completion_metadata'}
    result={'run_id':manifest['run_id'],'completion':completion,'aggregation_tool_sha256':digest(Path(__file__)),'aggregated_utc':datetime.now(timezone.utc).isoformat(),'protocol_id':'AE-EVAL-1.0','scope':'workspace-read','trials_planned':len(manifest['trials']),
     'trials_with_verified_evidence':len(rows),'passed':sum(r['result']['status']=='pass' for r in rows),'failures':failures,'evidence_missing':evidence_missing,
     'gates':{'G0':'pass' if manifest['g0']['successful'] else 'fail','G1':g1,'G2':'not_run','G3':'not_run'},
     'invariants':invariants,'execution_failures':execution_failures,'metrics':metrics,'real_model_calls':0,'formal_instance_unchanged':formal_unchanged,'workspace_G0':manifest['g0'].get('workspace_g0',{}),'evaluated_runtime':manifest['g0'].get('evaluated_runtime'),'write_side_effect_verification':'not_evaluable'}
    (root/'aggregate.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result
