"""Automatic seven-part state observations; unobserved mental variables stay missing."""
from datetime import datetime,timezone
import math
import shutil
from digital_life.domain.contracts import utc
from digital_life.application.services import States

class StateCollector:
    def __init__(self,store): self.s=store
    def collect(self):
        s=self.s; groups={name:[] for name in ('R','W','U','C','T','D','F')}
        def add(group,name,value,unit): groups[group].append({'name':group+'.'+name,'value':value,'unit':unit})
        add('R','disk_free_bytes',shutil.disk_usage(s.root).free,'bytes')
        # State telemetry consumes job state, never lease credentials. This is
        # also the exact projection captured by strict observation lineage.
        add('W','queue_depth',sum(r['state'] in ('queued','leased') for r in s.db.execute('SELECT id,state FROM jobs WHERE instance_id=?',(s.instance_id,))),'count')
        activities=[r for r in s.rows('activities') if r['state'] not in ('completed','failed','cancelled')]
        add('W','active_activities',len(activities),'count')
        for prediction in s.rows('cognition_predictions'):
            p=prediction['probability']
            if p is not None:
                entropy=-(p*math.log2(p) if p else 0)-((1-p)*math.log2(1-p) if p<1 else 0)
                add('U','prediction_entropy:'+prediction['id'],entropy,'bits')
        conflicts=[r for table in ('value_conflicts','commitment_conflicts') for r in s.rows(table)]
        add('C','recorded_unresolved',sum(r['state']!='resolved' for r in conflicts),'count')
        # Trust remains conditional; do not collapse distinct domains into one score.
        latest={}
        for assessment in s.rows('social_trust_assessments'):
            latest[(assessment['relationship_id'],assessment['domain'],assessment['dimension'])]=assessment
        for assessment in latest.values(): add('T','assessment:'+assessment['id'],assessment['estimate'],'probability')
        for activity in activities:
            if activity['deadline']:
                seconds=(datetime.fromisoformat(activity['deadline'].replace('Z','+00:00'))-datetime.now(timezone.utc)).total_seconds()
                add('D','deadline_remaining:'+activity['id'],seconds,'seconds')
        from digital_life.application.learning.health import startup_integrity_matches
        integrity={'integrity':'ok','foreign_keys':[]} if startup_integrity_matches(s) else s.integrity()
        add('F','sqlite_integrity',int(integrity['integrity']=='ok' and not integrity['foreign_keys']),'boolean')
        add('F','restore_reconciliation_required',int((s.root/'RESTORE_RECONCILIATION_REQUIRED').exists()),'boolean')
        with s.tx():
            artifact=s.artifact({'observed_at':utc(),'groups':groups,'scope':'recorded observations, not unobserved psychological truth'})
            evidence=s.evidence(artifact=artifact,method='automatic-state-probes-v1')
        for entries in groups.values():
            for entry in entries:
                if hasattr(s,"_yield_to_dialogue"):s._yield_to_dialogue()
                with s.tx():States(s).observe(entry['name'],entry['value'],entry['unit'],evidence,ttl=30)
        with s.tx():
            s.event('state.collected',payload={'artifact':artifact,'evidence':evidence,'missing_groups':[name for name,entries in groups.items() if not entries]},lane='telemetry')
        return {'groups':groups,'missing_groups':[name for name,entries in groups.items() if not entries],'evidence':evidence}
