"""Health application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Health:
    def __init__(self,store): self.s=store
    def assess(self):
        result=self.s.integrity(); workspace=self.s.root/'workspace'
        available=workspace.is_dir() and not workspace.is_symlink()
        status='healthy' if result['integrity']=='ok' and not result['foreign_keys'] and available else 'degraded'
        with self.s.tx():
            ref=self.s.insert('health_assessments',dimension='substrate',state=status,evidence_start=utc(),evidence_end=utc(),method_version='sqlite-workspace-v1')
            self.s.event('health.assessed',payload={'assessment':ref,'state':status,'workspace':available,'storage':result},lane='telemetry')
        return {'assessment':ref,'state':status,'scope':'storage and workspace; not all life functions','evidence':result}
    def restore_workspace(self,actor):
        if actor!=self.s.config()['controller']: raise Forbidden('maintenance needs controller')
        path=self.s.root/'workspace'
        if path.is_symlink(): raise Forbidden('cannot repair symlink workspace')
        path.mkdir(exist_ok=True)
        return self.assess()

