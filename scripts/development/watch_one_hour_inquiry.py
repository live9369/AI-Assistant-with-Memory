"""Bounded observation only: no topic injection, automatic tool approval or forced continuation."""
import json
import sys
import time
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.autonomy.exploration import Exploration
from digital_life.application.autonomy.continuous_exploration import ContinuousExploration
from digital_life.domain.contracts import utc
p=Path('outputs/open-inquiry-one-hour');case=json.loads((p/'manifest.json').read_text());deadline=datetime.fromisoformat(case['expires_at'].replace('Z','+00:00'));seen=set();summary={};snap={}
try:
    while datetime.now(timezone.utc)<deadline:
        s=Store(case['data'])
        try:
            x=Exploration(s);c=ContinuousExploration(x);cfg=x.config()
            bound=[b for b in x.payloads('exploration.bound') if b['generation']==case['generation']];outputs=[];activities=[]
            for b in bound:
                a=s.row('activities',b['activity']);activities.append({k:a[k] for k in ('id','state','recorded_at')})
                for r in s.db.execute('SELECT id,accepted_result_id,state FROM thought_requests WHERE activity_id=?',(b['activity'],)):
                    if not r['accepted_result_id']:continue
                    result=s.row('thought_results',r['accepted_result_id']);out=s.read_artifact(result['parsed_artifact_id']);v={'request':r['id'],'activity':b['activity'],'output':out};outputs.append(v)
                    if r['id'] not in seen:print(json.dumps(v,ensure_ascii=False),flush=True);seen.add(r['id'])
            directions=[d for d in c.directions().values() if d['id'] not in case['baseline_directions']]
            selections=[v for v in c.values('selection') if v.get('generation')==case['generation']]
            errors=[]
            for r in s.db.execute("SELECT event_type,recorded_at,activity_id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_seq>? AND (event_type LIKE '%failed%' OR event_type LIKE '%error%') ORDER BY event_seq",(s.instance_id,case['baseline_seq'])):
                v=dict(r);v['payload']=s.read_artifact(v.pop('payload_artifact_id')) if r['payload_artifact_id'] else None;errors.append(v)
            snap={'observed_at':utc(),'configuration':cfg,'bindings':bound,'activities':activities,'outputs':outputs,'directions':directions,'selections':selections,'errors':errors}
            (p/'latest.json').write_text(json.dumps(snap,ensure_ascii=False,indent=2))
            if cfg['generation']!=case['generation']:summary={'stop_reason':'configuration-changed'};break
            if not cfg['enabled']:summary={'stop_reason':'expired' if cfg.get('expired') else 'disabled'};break
        finally:s.close()
        time.sleep(5)
    else:summary={'stop_reason':'one-hour-window-completed'}
finally:
    s=Store(case['data'])
    try:
        x=Exploration(s)
        # Never overwrite a new user configuration after this test was superseded.
        if x.config()['generation']==case['generation']:x.configure(s.config()['controller'],False)
        summary.update(finished_at=utc(),exploration_disabled=not x.config()['enabled'],calls=len(seen),directions=len(snap.get('directions',[])))
    finally:s.close()
    (p/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary),flush=True)
