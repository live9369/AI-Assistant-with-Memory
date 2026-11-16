"""Observe one user-authorized, bounded native-system trial without choosing topics or approving tools."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.autonomy.exploration import Exploration
from digital_life.application.autonomy.continuous_exploration import ContinuousExploration
from digital_life.domain.contracts import utc
p=Path('outputs/open-inquiry-system-trial');case=json.loads((p/'manifest.json').read_text());seen=set();summary={}
try:
    for _ in range(900):
        s=Store(case['data'])
        try:
            x=Exploration(s);c=ContinuousExploration(x)
            bound=[b for b in x.payloads('exploration.bound') if b['generation']==case['generation']]
            activities={b['activity'] for b in bound};requests=[];outputs=[]
            for activity in activities:
                for r in s.db.execute('SELECT id,state,accepted_result_id,recorded_at FROM thought_requests WHERE activity_id=?',(activity,)):
                    requests.append(dict(r))
                    if r['accepted_result_id']:
                        result=s.row('thought_results',r['accepted_result_id']);out=s.read_artifact(result['parsed_artifact_id']);outputs.append({'request':r['id'],'activity':activity,'output':out})
                        if r['id'] not in seen:
                            print(json.dumps(outputs[-1],ensure_ascii=False),flush=True);seen.add(r['id'])
            directions=[d for d in c.directions().values() if d['id'] not in case['baseline_directions']]
            selections=[v for v in c.values('selection') if v.get('generation')==case['generation']]
            pending=[]
            for activity in activities:
                for r in s.db.execute("SELECT id,state FROM activities WHERE id=?",(activity,)):
                    if r['state'] not in ('completed','failed','cancelled','paused'):pending.append(dict(r))
            snapshot={'observed_at':utc(),'configuration':x.config(),'bindings':bound,'requests':requests,'outputs':outputs,'directions':directions,'selections':selections,'pending':pending}
            (p/'latest.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
            if any(r['state']=='waiting_input' for r in pending):summary={'stop_reason':'approval-or-input-required'};break
            if len(bound)>=case['max_activities'] and not pending:summary={'stop_reason':'activity-limit'};break
            if not x.config()['enabled']:summary={'stop_reason':'disabled-or-expired'};break
        finally:s.close()
        time.sleep(1)
    else:summary={'stop_reason':'observer-time-limit'}
finally:
    s=Store(case['data'])
    try:Exploration(s).configure(s.config()['controller'],False)
    finally:s.close()
    summary['finished_at']=utc();summary['exploration_disabled']=True
    (p/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary),flush=True)
