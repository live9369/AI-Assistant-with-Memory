"""Synthetic management data; roots must be inside the OS temporary directory."""
from pathlib import Path
import tempfile
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.runtime.engine import Engine
from digital_life.domain.contracts import utc

class PanelReasoner:
    name='isolated-panel-reasoner'
    def generate(self,request):
        return {'schema_version':1,'action':{'tool':'write_note','arguments':{'path':'notes/'+request['activity_id']+'.txt','text':'isolated panel output'}},'explanation':'isolated management fixture'}

def seed_panel(root):
    root=Path(root).resolve()
    if not root.is_relative_to(Path(tempfile.gettempdir()).resolve()): raise ValueError('panel fixtures require a temporary root')
    store=Store.prepare(root,name='原初00 · 隔离验证',model_config={'backend':'llamacpp','model':'panel-fixture','base_url':'http://127.0.0.1:9','timeout':2,'max_output_tokens':512,'context_window':8192,'temperature':0})
    control=Control(root,store.instance_id); engine=Engine(store); refs={}
    try:
        (root/'WAKE_DISABLED').unlink();control.resume('isolated-panel-seed')
        for key,title in (('approve','整理本周阅读笔记'),('reject','复核资料归档方案'),('expire','已过期的操作示例')):
            activity=engine.submit(title,key,'panel-fixture'); result=engine.think(activity,PanelReasoner())
            refs[key]={'activity':activity,'approval':result['approval_id']}
        with store.tx(): store.db.execute('UPDATE approval_requests SET expires_at=? WHERE id=?',(utc(-10),refs['expire']['approval']))
        refs['pending']=engine.submit('核对本周活动记录','pending','panel-fixture')
        refs['xss']=engine.submit('<img src=x onerror="window.panelInjected=1">','xss','panel-fixture')
        with store.tx():
            for i in range(35): store.event('fixture.record',payload={'index':i,'safe':'isolated-fixture'},source='panel-fixture',key='log-'+str(i))
            refs['error_event']=store.event('runtime.job_failed',payload={'error':'isolated-test-failure'},lane='control')
            refs['private_event']=store.event('fixture.privacy',payload={'api_key':'fixture-never-export-api-secret','Authorization':'Bearer fixture-auth-secret','task':'private task body','safe':'visible'},lane='telemetry')
        return refs
    finally:
        control.stop('isolated-panel-lock');(root/'WAKE_DISABLED').write_text('Isolated management fixture; no Runtime or tool execution permitted.\n')
        control.close();store.close()
