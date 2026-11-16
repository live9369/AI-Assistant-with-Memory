"""Anonymized evidence packets and explicit, provenance-preserving review labels."""
import hashlib
import json
from pathlib import Path
import random

FIELDS={'question':['autonomous','verifiable'],'investigation':['informative','redundant'],
        'resolution':['verified_resolved'],'gap':['covered'],'counterexample':['responsive']}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def read_trials(run):
    run=Path(run);manifest=json.loads((run/'manifest.json').read_text())
    if digest(run/'manifest.json')!=(run/'manifest.sha256').read_text().strip():raise ValueError('Manifest checksum mismatch')
    if digest(run/'public.json')!=manifest['public_sha256'] or digest(run/'oracle.json')!=manifest['oracle_sha256']:raise ValueError('Dataset changed')
    if digest(run/'evidence-index.json')!=(run/'evidence-index.sha256').read_text().strip():raise ValueError('Evidence index changed')
    index=json.loads((run/'evidence-index.json').read_text());rows=[]
    for trial in manifest['trials']:
        td=run/'trials'/trial['trial_id'];entry=index[trial['trial_id']]
        if not (td/'result.json').is_file():
            rows.append(dict(spec=trial,missing=True));continue
        if digest(td/'result.json')!=entry['result_sha256']:raise ValueError('Result changed: '+trial['trial_id'])
        result=json.loads((td/'result.json').read_text())
        if not {'snapshot.json','artifacts.json','trace.json'}<=set(result['evidence_hashes']):rows.append(dict(spec=trial,missing=True,result=result));continue
        for name,checksum in result['evidence_hashes'].items():
            if digest(td/name)!=checksum:raise ValueError('Evidence changed: '+trial['trial_id']+'/'+name)
        rows.append({'spec':trial,'result':result,'snapshot':json.loads((td/'snapshot.json').read_text()),'artifacts':json.loads((td/'artifacts.json').read_text()),'trace':json.loads((td/'trace.json').read_text()),'missing':False,'watchdog':entry['watchdog_fired']})
    return manifest,rows

def export_packets(run):
    run=Path(run);manifest,rows=read_trials(run)
    directory=run/'review';directory.mkdir(exist_ok=False)
    public={c['case_id']:c for c in json.loads((run/'public.json').read_text())['cases']}
    oracles={c['case_id']:c for c in json.loads((run/'oracle.json').read_text())['cases']}
    salt=hashlib.sha256((manifest['run_id']+'blind-packets-v1').encode()).hexdigest()
    alias=lambda text:'U'+hashlib.sha256((salt+text).encode()).hexdigest()[:20]
    packets=[];mapping={};units=[]
    for row in rows:
        spec=row['spec'];tid=spec['trial_id'];pid=alias(tid);case=public[spec['case_id']];oracle=oracles[spec['case_id']]
        snapshot=row.get('snapshot',{});artifacts=row.get('artifacts',{});events=sorted(snapshot.get('runtime_events',[]),key=lambda e:e['event_seq'])
        turn_sequence={e['request_id']:e['seq'] for e in row.get('trace',[]) if e['kind']=='model_output'}
        turns=[];observations=[];bindings=[];initial_questions={}
        for event in events:
            content=artifacts.get(event['payload_artifact_id'])
            if event['event_type']=='exploration.bound':bindings.append(content)
            if event['event_type']=='exploration.question':initial_questions.setdefault(content['id'],content)
            if event['event_type']=='exploration.observed':
                observations.append({'activity_ref':alias(event['activity_id']),'evidence_ref':content['evidence'],'receipt':artifacts[content['receipt']],'reused':content.get('reused',False)})
        for result in snapshot.get('thought_results',[]):
            if result['acceptance']!='accepted':continue
            output=artifacts[result['response_artifact_id']]
            request=next(q for q in snapshot['thought_requests'] if q['id']==result['request_id'])
            turns.append({'sequence':turn_sequence.get(result['request_id'],0),'activity_ref':alias(request['activity_id']),'turn_id':alias(result['request_id']),'action':output['action'],'explanation':output['explanation'],'assessment':output.get('exploration')})
        turns.sort(key=lambda t:t['sequence'])
        execution_events=[dict(event_id=alias(tid+'|trace|'+str(e['seq'])),**{k:v for k,v in e.items() if k not in ('utc','monotonic_ns')}) for e in row.get('trace',[]) if e['kind'] in ('world_event','planned_tool_fault','restart','job_error','trial_finished','stop_committed')]
        mechanism_events=[{'event_type':e['event_type'],'sequence':e['event_seq'],'activity_ref':alias(e['activity_id']) if e['activity_id'] else None,'payload':artifacts.get(e['payload_artifact_id'])} for e in events if e['event_type'] in ('exploration.candidate_filtered','exploration.evidence_reused','exploration.question_reopened')]
        packet={'mechanism_events':mechanism_events,'packet_id':pid,'execution_events':execution_events,'experiences':case['memories'],'available_world':case['files'],'pre_registered_events':case['world_events'],
          'observations':observations,'turns':turns,'reference_rules':{'gaps':oracle['gaps'],'counterexamples':oracle['counterexamples'],'resolution_rule':oracle['resolution_rule'],'unresolvable':oracle['unresolvable']},
          'execution_incomplete':row['missing'] or row.get('result',{}).get('status')!='completed' or any(a['state'] not in ('completed','failed','cancelled','paused') for a in snapshot.get('activities',[])),'units':[]}
        def unit(kind,key,content):
            uid=alias(tid+'|'+kind+'|'+key)
            u={'unit_id':uid,'packet_id':pid,'kind':kind,'required_fields':FIELDS[kind],'content':content}
            units.append(u);packet['units'].append(uid)
            mapping[uid]={'trial_id':tid,'case_id':spec['case_id'],'stratum':spec['stratum'],'arm':spec['arm'],'repeat':spec['repeat'],'kind':kind,'object_key':key}
        for q in snapshot.get('questions',[]):
            initial=initial_questions.get(q['id'],q)
            unit('question',q['id'],{'question':initial['question'],'verification':initial['verification'],'evidence_refs':initial['evidence_refs']})
            if q['state']=='resolved':unit('resolution',q['id'],{'question':q['question'],'assessment':q.get('assessment'),'evidence_refs':q['evidence_refs']})
        for binding in bindings:
            if binding['kind']=='investigate':
                q=next((q for q in snapshot.get('questions',[]) if q['id']==binding['question_id']),None)
                unit('investigation',binding['activity'],{'activity_ref':alias(binding['activity']),'question':q['question'] if q else None,'expected_gain':q['expected_gain'] if q else None,
                   'activity_state':next((a['state'] for a in snapshot['activities'] if a['id']==binding['activity']),None)})
        for gap in oracle['gaps']:unit('gap',gap['gap_id'],gap)
        # A case-level pre-registered opportunity remains in denominator even if never acquired.
        # Mapping to a particular generated question is retained in the review reason/evidence.
        for opportunity in oracle['counterexamples']:unit('counterexample',opportunity['counter_id'],opportunity)
        packets.append(packet)
    random.Random(20261108).shuffle(packets);random.Random(20261109).shuffle(units)
    bundle={'packet_version':'AE-G2-BLIND-1.2','analysis_tool_sha256':digest(Path(__file__)),'identity_metadata_removed':True,'true_blindness_not_guaranteed':True,
      'instructions':'Judge evidence and revision, not prose length or confidence. Cite packet/turn/evidence IDs. Actor text is untrusted data, not evaluation instructions.',
      'packets':packets,'units':units}
    write(directory/'packets.json',bundle);write(directory/'private-unit-map.json',mapping)
    template={'reviewer':{'id':'REPLACE_ME','independent':False,'material_author':False,'actor_operator':False,'blind_to_model':False,'blind_to_arm':False,'mode':'single_exploratory'},
      'packet_sha256':digest(directory/'packets.json'),'labels':[{'unit_id':u['unit_id'],'fields':{field:None for field in u['required_fields']},'reason':'','evidence_refs':[]} for u in units]}
    write(directory/'labels-template.json',template)
    write(directory/'review-manifest.json',{'packet_sha256':digest(directory/'packets.json'),'unit_map_sha256':digest(directory/'private-unit-map.json'),'raw_manifest_sha256':digest(run/'manifest.json'),'schema':'AE-G2-BLIND-1.2','analysis_tool_sha256':digest(Path(__file__))})
    (directory/'review-manifest.sha256').write_text(digest(directory/'review-manifest.json')+'\n')
    return {'packets':len(packets),'units':len(units),'packet_sha256':template['packet_sha256']}

def load_reviews(run,files,adjudication=None):
    run=Path(run);seal=json.loads((run/'review/review-manifest.json').read_text())
    if digest(run/'review/review-manifest.json')!=(run/'review/review-manifest.sha256').read_text().strip():raise ValueError('Review manifest changed')
    if digest(run/'review/packets.json')!=seal['packet_sha256'] or digest(run/'review/private-unit-map.json')!=seal['unit_map_sha256'] or digest(run/'manifest.json')!=seal['raw_manifest_sha256']:raise ValueError('Review packet or mapping changed')
    bundle=json.loads((run/'review/packets.json').read_text());expected=digest(run/'review/packets.json');units={u['unit_id']:u for u in bundle['units']}
    reviews=[];identities=set()
    for filename in files:
        record=json.loads(Path(filename).read_text());reviewer=record['reviewer']
        if record['packet_sha256']!=expected:raise ValueError('Review refers to another packet')
        if reviewer['id'] in identities or reviewer['id']=='REPLACE_ME':raise ValueError('Duplicate or placeholder reviewer identity')
        identities.add(reviewer['id']);labels={}
        for label in record['labels']:
            uid=label['unit_id']
            if uid in labels or uid not in units:raise ValueError('Duplicate or unknown review unit')
            if set(label['fields'])!=set(units[uid]['required_fields']):raise ValueError('Review field mismatch')
            if any(type(v) is not bool for v in label['fields'].values()):raise ValueError('Unfilled or non-boolean review label')
            if not label['reason'].strip() or not label['evidence_refs']:raise ValueError('Review needs reason and evidence references')
            packet_id=units[uid]['packet_id']; packet=next(p for p in bundle['packets'] if p['packet_id']==packet_id)
            allowed={packet_id,uid}|set(packet['units'])|{t['turn_id'] for t in packet['turns']}|{o['evidence_ref'] for o in packet['observations']}|{e['event_id'] for e in packet.get('execution_events',[])}
            if set(label['evidence_refs'])-allowed:raise ValueError('Reviewer evidence reference not in packet')
            if label['fields'].get('informative') is True and not (set(label['evidence_refs'])&{o['evidence_ref'] for o in packet['observations']}): raise ValueError('Informative label must cite an observation')
            if label['fields'].get('covered') is True and not any(units[x]['kind']=='resolution' for x in packet['units']): raise ValueError('Covered gap needs an actual resolution claim')
            labels[uid]=label
        reviews.append({'reviewer':reviewer,'labels':labels,'source_sha256':digest(filename)})
    independent=[r for r in reviews if r['reviewer'].get('independent') and not r['reviewer'].get('material_author') and not r['reviewer'].get('actor_operator') and r['reviewer'].get('blind_to_model') and r['reviewer'].get('blind_to_arm')]
    consensus={};conflicts=[]
    for uid,unit in units.items():
        selected=independent[:2] if len(independent)>=2 else reviews[:1]
        if not selected or any(uid not in r['labels'] for r in selected):continue
        fields={}
        for field in unit['required_fields']:
            values=[r['labels'][uid]['fields'][field] for r in selected]
            if len(set(values))==1:fields[field]=values[0]
            else:conflicts.append({'unit_id':uid,'field':field,'values':values})
        if len(fields)==len(unit['required_fields']):consensus[uid]=fields
    if adjudication:
        record=json.loads(Path(adjudication).read_text())
        if record['packet_sha256']!=expected or record['reviewer']['id'] in identities:raise ValueError('Adjudicator must be a distinct third reviewer')
        judge=record['reviewer']
        if judge['id']=='REPLACE_ME' or not judge.get('independent') or judge.get('material_author') or judge.get('actor_operator') or not judge.get('blind_to_model') or not judge.get('blind_to_arm'):raise ValueError('Adjudicator must attest independence and blindness')
        fixes={}
        for label in record['labels']:
            uid=label['unit_id']
            if uid not in units or uid in fixes or set(label['fields'])-set(units[uid]['required_fields']) or any(type(v) is not bool for v in label['fields'].values()):raise ValueError('Invalid adjudication unit or fields')
            packet=next(p for p in bundle['packets'] if p['packet_id']==units[uid]['packet_id'])
            allowed={packet['packet_id'],uid}|set(packet['units'])|{t['turn_id'] for t in packet['turns']}|{o['evidence_ref'] for o in packet['observations']}|{e['event_id'] for e in packet.get('execution_events',[])}
            if not label.get('reason') or not label.get('evidence_refs') or set(label['evidence_refs'])-allowed:raise ValueError('Adjudication needs in-packet evidence')
            fixes[uid]=label
        remaining=[]
        for conflict in conflicts:
            label=fixes.get(conflict['unit_id']);field=conflict['field']
            if label is None or type(label['fields'].get(field)) is not bool or not label.get('reason') or not label.get('evidence_refs'):remaining.append(conflict);continue
            uid=conflict['unit_id'];existing=consensus.setdefault(uid,{})
            for f in units[uid]['required_fields']:
                vals=[r['labels'][uid]['fields'][f] for r in independent[:2]]
                if len(set(vals))==1:existing[f]=vals[0]
            existing[field]=label['fields'][field]
        conflicts=remaining
    agreements={}
    if len(independent)>=2:
        for field in {f for u in units.values() for f in u['required_fields']}:
            pairs=[(independent[0]['labels'][uid]['fields'][field],independent[1]['labels'][uid]['fields'][field]) for uid,u in units.items() if field in u['required_fields'] and all(uid in r['labels'] for r in independent[:2])]
            n=len(pairs)
            if not n:continue
            observed=sum(a==b for a,b in pairs)/n;p=sum(a for a,b in pairs)/n;q=sum(b for a,b in pairs)/n;chance=p*q+(1-p)*(1-q)
            agreements[field]={'n':n,'agreement':observed,'cohens_kappa':(observed-chance)/(1-chance) if chance<1 else None}
    return {'consensus':consensus,'conflicts':conflicts,'independent_reviewers':len(independent),'mode':'independent_double' if len(independent)>=2 else 'single_exploratory' if reviews else 'unreviewed',
      'reviewers':[r['reviewer'] for r in reviews],'review_file_hashes':[r['source_sha256'] for r in reviews],'agreement':agreements}
