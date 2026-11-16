"""Separate health dimensions; unknown never counts as healthy."""
import json
import shutil
from digital_life.domain.contracts import utc
from digital_life.application.telemetry.metrics import Metrics
from digital_life.infrastructure.llm.inference import probe

class HealthMonitor:
    def __init__(self,store): self.s=store
    def scan(self,connect_model=False):
        values=Metrics(self.s).operational(); dimensions={}
        def mark(name,value,reason):
            dimensions[name]={'state':'unknown' if value is None else 'healthy' if value else 'degraded','reason':reason}
        mark('identity',bool(values['identity_anchor_integrity'][0]),'identity anchor and instance agreement')
        memory=values['memory_revision_integrity'][0]
        mark('memory',memory==1 if memory is not None else None,'current revision integrity; not semantic truth')
        mark('storage',values['storage_integrity'][0]==1 and values['foreign_key_violations'][0]==0,'SQLite integrity and foreign keys')
        if dimensions['storage']['state']!='healthy':self.s._startup_integrity=None
        mark('resources',shutil.disk_usage(self.s.root).free>64*1024*1024,'minimum 64 MiB storage reserve; CPU/memory pressure not inferred')
        mark('workspace',bool(values['workspace_available'][0]),'bounded tool workspace')
        attempts=self.s.rows('action_attempts')
        mark('behavior_permissions',all(r['authorization_record_id'] and r['state']!='unknown' for r in attempts) if attempts else None,'actual recorded authorization and known outcomes')
        mark('continuity',not bool(values['restore_reconciliation_required'][0]),'restore reconciliation lock')
        promises=self.s.rows('commitment_items')
        mark('relationships_commitments',not any(r['due_at'] and r['due_at']<utc() and r['state'] in ('active','performing') for r in promises) if promises else None,'overdue active commitments')
        mark('cognition',None,'correctness requires independent task evaluation')
        mark('dependencies',None,'local model probe not requested')
        if connect_model:
            try: probe(self.s.config()['model']); mark('dependencies',True,'local model inventory confirmed without inference')
            except Exception as error: mark('dependencies',False,str(error)[:256])
        with self.s.tx():
            for name,result in dimensions.items():
                result['assessment']=self.s.insert('health_assessments',dimension=name,state=result['state'],evidence_start=utc(),evidence_end=utc(),method_version='multidimensional-v1')
            event=self.s.event('health.multidimensional',payload=dimensions,lane='telemetry')
        status='degraded' if any(r['state']=='degraded' for r in dimensions.values()) else 'unknown' if any(r['state']=='unknown' for r in dimensions.values()) else 'healthy'
        return {'state':status,'dimensions':dimensions,'event':event,'ttl_seconds':30}
