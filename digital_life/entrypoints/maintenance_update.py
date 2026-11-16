"""Human-confirmed update command, retaining the foreground watchdog."""
import json
import sys
import time
from pathlib import Path
from digital_life.domain.contracts import identifier
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.lifecycle.maintenance_pipeline import MaintenancePipeline
from digital_life.infrastructure.processes.locks import exclusive


def update(data, proposal, confirmation=None):
    data=Path(data).resolve();expected='UPDATE '+data.name
    if not (data/'runtime.sqlite').is_file(): raise ValueError('实例不存在；update不创建实例。')
    if confirmation is None:
        if not sys.stdin.isatty(): raise ValueError('请提供 --confirm "'+expected+'"')
        confirmation=input('确认更新请输入 '+expected+'：').strip()
    if confirmation!=expected: raise ValueError('确认不匹配，未停止或更新实例。')
    # Prevent two update orchestrators from stopping one another's lifecycle.
    with exclusive(data,'maintenance-update.lock'):
        store=Store(data);control=Control(data,store.instance_id);pipeline=MaintenancePipeline(store,control)
        try:
            preview=pipeline.preflight(proposal)
            print(json.dumps(preview,ensure_ascii=False),flush=True)
            command=control.stop(identifier())['last_stop_command_id']
            deadline=time.monotonic()+20
            while control.state()['active_process_run_id']:
                if time.monotonic()>=deadline: raise ValueError('原运行器尚未退出；保持停止，未构建或部署。')
                time.sleep(.1)
            result=pipeline.execute(proposal,command)
            print(json.dumps(result,ensure_ascii=False),flush=True)
            if pipeline.manager.active:
                print('保持此终端打开以监督当前版本；Ctrl+C停止。',flush=True)
                pipeline.manager.supervise()
            return result
        except KeyboardInterrupt:
            control.stop(identifier())
            if pipeline.manager.active:
                pipeline.manager.driver.stop(pipeline.manager.active['process']);pipeline.manager.active=None
            raise
        finally:control.close();store.close()
