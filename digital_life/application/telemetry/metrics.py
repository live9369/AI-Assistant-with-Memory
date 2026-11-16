"""Versioned metric collection. Missing ground truth is NULL, never success.

Operational probes read authoritative rows. Semantic metrics consume independently
labelled, evidence-linked observations through the same reproducible pipeline.
"""
from datetime import datetime,timezone
import json
import math
import resource
import shutil
import statistics
import sys
from digital_life.domain.contracts import dumps,sha,utc,text,ContractError,Forbidden,Conflict
from digital_life.infrastructure.persistence.sqlite_store import RESOURCES

def catalog(): return json.loads((RESOURCES/'metrics.json').read_text())

def reduce_samples(kind,records):
    if not records: return None,0,'no_observations'
    if kind in ('precision','recall','mrr','ndcg'):
        values=[]
        for record in records:
            ranked=list(dict.fromkeys(record['ranked']))[:record.get('k',10)]; relevant=set(record['relevant'])
            if not relevant: continue
            hits=[int(item in relevant) for item in ranked]
            if kind=='precision': values.append(sum(hits)/record.get('k',10))
            elif kind=='recall': values.append(sum(hits)/len(relevant))
            elif kind=='mrr': values.append(next((1/(i+1) for i,v in enumerate(hits) if v),0))
            else:
                dcg=sum(v/math.log2(i+2) for i,v in enumerate(hits))
                ideal=sum(1/math.log2(i+2) for i in range(min(len(relevant),record.get('k',10))))
                values.append(dcg/ideal if ideal else 0)
        return (statistics.mean(values),len(values),None) if values else (None,0,'no_relevant_truth')
    if kind=='ece':
        bins=[[] for _ in range(10)]
        for record in records: bins[min(9,int(record['probability']*10))].append(record)
        value=sum(len(b)/len(records)*abs(statistics.mean(r['probability'] for r in b)-statistics.mean(r['outcome'] for r in b)) for b in bins if b)
        return value,len(records),None
    values=[r['value'] if 'value' in r else r['after']-r['before'] for r in records]
    return statistics.mean(values),len(values),None

class Metrics:
    def __init__(self,store): self.s=store
    def observe(self,key,record,source,case,actor,dataset='evaluation-v1'):
        if actor!=self.s.config()['controller']: raise Forbidden('independent evaluator authority required')
        definition=next((r for r in catalog() if r['key']==key),None)
        if not definition: raise ContractError('unknown metric')
        if definition['requires']=='runtime': raise Forbidden('runtime probes cannot be overwritten by evaluator observations')
        self.s.row('object_registry',source); text(case,240); text(dataset,240)
        if not isinstance(record,dict): raise ContractError('metric record must be object')
        kind=definition['reducer']
        if kind in ('precision','recall','mrr','ndcg'):
            if not all(isinstance(record.get(k),list) for k in ('ranked','relevant')): raise ContractError('ranking and truth lists required')
            if any(not isinstance(v,str) for v in record['ranked']+record['relevant']): raise ContractError('ranking IDs must be strings')
            if type(record.get('k',10)) is not int or not 1<=record.get('k',10)<=1000: raise ContractError('invalid k')
        else:
            fields=('probability','outcome') if kind=='ece' else ('value',) if 'value' in record else ('before','after')
            for field in fields:
                value=record.get(field)
                if not isinstance(value,(float,int)) or not math.isfinite(value): raise ContractError('finite observation required')
                if kind=='ece' and not 0<=value<=1: raise ContractError('calibration observation outside range')
        # Precompute once to validate the observation's complete schema.
        reduce_samples(kind,[record])
        with self.s.tx():
            return self.s.event('metrics.observation',payload={'metric':key,'record':record,'source':source,'case':case,'dataset':dataset,'evaluator':actor},
                source='metric-evaluator',key=key+':'+dataset+':'+case,lane='telemetry')
    def operational(self):
        s=self.s
        def rows(table): return s.rows(table)
        def rate(n,d): return (n/d if d else None,d)
        activities=rows('activities'); jobs=rows('jobs'); actions=rows('action_attempts'); intents=rows('action_intents'); memories=rows('memory_items')
        integrity=s.integrity(); goals={r['id']:r for r in rows('goal_items')}
        terminal=[r for r in activities if r['state'] in ('completed','failed','cancelled')]
        promises=[r for r in rows('commitment_items') if r['state'] not in ('proposed','confirmed')]
        fulfilled=[r for r in promises if r['state']=='fulfilled']
        due=[r for r in promises if r['due_at'] and r['due_at']<=utc()]
        transitions=rows('commitment_transitions')
        ontime=sum(any(t['commitment_id']==r['id'] and t['to_state']=='fulfilled' and t['recorded_at']<=r['due_at'] for t in transitions) for r in due)
        pending=[r for r in jobs if r['state'] in ('queued','leased')]
        age=max((max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(r['due_at'].replace('Z','+00:00'))).total_seconds()) for r in pending),default=0)
        from digital_life.application.services import States
        states=list(States(s).snapshot().values())
        latency=[(datetime.fromisoformat(r['finished_at'].replace('Z','+00:00'))-datetime.fromisoformat(r['started_at'].replace('Z','+00:00'))).total_seconds()*1000 for r in actions if r['finished_at']]
        model_records=[]
        for event in s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type='model.usage'",(s.instance_id,)):
            model_records.append(s.read_artifact(event[0]))
        artifact_ok=0
        for artifact in rows('artifacts'):
            try: s.read_artifact(artifact['id']); artifact_ok+=1
            except (OSError,ValueError): pass
        anchors=rows('identity_anchors')
        return {
          'activity_completion_rate':rate(sum(r['state']=='completed' for r in terminal),len(terminal)),
          'queue_depth':(len(pending),1),'oldest_job_age_seconds':(age,1),
          'memory_revision_integrity':rate(sum(bool(r['current_revision_id']) and s.db.execute('SELECT count(*) FROM memory_revisions WHERE id=? AND memory_id=?',(r['current_revision_id'],r['id'])).fetchone()[0] for r in memories),len(memories)),
          'memory_source_coverage':rate(sum(bool(s.db.execute('SELECT 1 FROM memory_source_links WHERE memory_revision_id=? LIMIT 1',(r['current_revision_id'],)).fetchone()) for r in memories),len(memories)),
          'relationship_evidence_coverage':rate(sum(bool(s.db.execute('SELECT 1 FROM social_trust_evidence WHERE assessment_id=? LIMIT 1',(r['id'],)).fetchone()) for r in rows('social_trust_assessments')),len(rows('social_trust_assessments'))),
          'commitment_fulfillment_rate':rate(len(fulfilled),len(promises)), 'commitment_on_time_rate':rate(ontime,len(due)),
          'state_freshness':rate(sum(r['fresh'] for r in states),len(states)),
          'disk_free_bytes':(shutil.disk_usage(s.root).free,1),
          'process_max_rss_bytes':(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),1),
          'authorization_coverage':rate(sum(bool(r['authorization_record_id']) for r in actions),len(actions)),
          'revoked_grants':(sum(bool(r['revoked_at']) for r in rows('grants')),1),
          'tool_success_rate':rate(sum(r['state']=='succeeded' for r in actions),len(actions)),
          'tool_unknown_rate':rate(sum(r['state']=='unknown' for r in actions),len(actions)),
          'tool_latency_ms':(statistics.mean(latency) if latency else None,len(latency)),
          'identity_anchor_integrity':(int(bool(anchors) and json.loads(anchors[-1]['anchor_data']).get('instance_id')==s.instance_id),1),
          'restore_reconciliation_required':(int((s.root/'RESTORE_RECONCILIATION_REQUIRED').exists()),1),
          'storage_integrity':(int(integrity['integrity']=='ok'),1),'foreign_key_violations':(len(integrity['foreign_keys']),1),
          'workspace_available':(int((s.root/'workspace').is_dir() and not (s.root/'workspace').is_symlink()),1),
          'model_latency_ms':(statistics.mean(r['latency_ms'] for r in model_records) if model_records else None,len(model_records)),
          'model_input_tokens':(sum(r['input_tokens'] for r in model_records if r.get('input_tokens') is not None) if any(r.get('input_tokens') is not None for r in model_records) else None,sum(r.get('input_tokens') is not None for r in model_records)),
          'model_output_tokens':(sum(r['output_tokens'] for r in model_records if r.get('output_tokens') is not None) if any(r.get('output_tokens') is not None for r in model_records) else None,sum(r.get('output_tokens') is not None for r in model_records)),
          'artifact_integrity':rate(artifact_ok,len(rows('artifacts'))),
        }
    def collect(self,dataset='runtime-v1',force=False):
        from digital_life.application.telemetry.states import StateCollector
        StateCollector(self.s).collect()
        definitions=catalog(); observations=[]
        for event in self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type='metrics.observation' ORDER BY event_seq",(self.s.instance_id,)):
            record=self.s.read_artifact(event[0])
            if record['dataset']==dataset: observations.append(record)
        values=self.operational()
        with self.s.tx():
            # Time-varying probes are sampled on explicit collection / runtime interval.
            manifest={'operational':values,'observations':observations,'dataset':dataset,'catalog':sha(dumps(definitions))}
            fingerprint=sha(dumps(manifest)); key='collection:'+fingerprint
            existing=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND source='metrics' AND source_event_id=?",(self.s.instance_id,key)).fetchone()
            if existing and not force: return self.s.read_artifact(existing[0])
            source=self.s.artifact(manifest)
            run=self.s.insert('evaluation_runs',dataset_version=dataset,model_version=self.s.rows('model_versions')[-1]['id'],conditions={'collector':'metrics-v1','source_artifact':source,'catalog_sha256':manifest['catalog']},state='running')
        measured=0
        for definition in definitions:
            if hasattr(self.s,"_yield_to_dialogue"):self.s._yield_to_dialogue()
            with self.s.tx():
                prior=self.s.db.execute('SELECT id FROM metric_definitions WHERE instance_id=? AND name=? AND formula_version=?',(self.s.instance_id,definition['key'],definition['formula_version'])).fetchone()
                ref=prior[0] if prior else self.s.insert('metric_definitions',name=definition['key'],formula_version=definition['formula_version'],unit=definition['unit'],denominator_rule='eligible observed cases; no synthetic successes',missing_rule=definition['missing_rule'],stratification=definition)
                selected=[r['record'] for r in observations if r['metric']==definition['key']]
                if definition['requires']=='runtime':
                    value,n=values[definition['label']]; reason=None if value is not None else 'no_eligible_runtime_observations'
                else: value,n,reason=reduce_samples(definition['reducer'],selected)
                measured+=int(value is not None)
                denominator=1 if value is not None and definition['requires']=='runtime' and definition['unit'] in ('tokens','bytes','count','seconds') else n
                self.s.insert('metric_samples',run_id=run,definition_id=ref,source_ref=source,numerator=value*denominator if value is not None else None,denominator=denominator,value=value,
                    uncertainty={'status':'observed' if value is not None else 'missing','reason':reason,'sample_size':n,'definition':definition,'scientific_validity':'not_established_by_collection'})
        with self.s.tx():
            self.s.db.execute("UPDATE evaluation_runs SET state='completed' WHERE id=?",(run,))
            if self.s.db.execute('PRAGMA user_version').fetchone()[0]>=3:
                cursor=self.s.db.execute('SELECT coalesce(max(event_seq),0) FROM runtime_events WHERE instance_id=?',(self.s.instance_id,)).fetchone()[0]
                self.s.db.execute('INSERT INTO module_checkpoints(instance_id,module_name,cursor,updated_at) VALUES(?,?,?,?) ON CONFLICT(instance_id,module_name) DO UPDATE SET cursor=excluded.cursor,updated_at=excluded.updated_at',(self.s.instance_id,'metrics-v1',cursor,utc()))
            result={'run':run,'definitions':len(definitions),'measured':measured,'missing':len(definitions)-measured,'dataset':dataset,'manifest':source}
            self.s.event('metrics.collected',payload=result,source='metrics',key=key if not force else key+':'+run,lane='telemetry')
            return result
