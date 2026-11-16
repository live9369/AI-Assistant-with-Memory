"""Read-only, credential-free preview for the explicit launcher."""
import json,os,sqlite3,stat
from pathlib import Path

def configuration(data,port,wake=True):
    root=Path(data).resolve()
    with sqlite3.connect((root/'runtime.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        instance=db.execute('SELECT id FROM identity_instances').fetchone()[0]
        row=db.execute('SELECT a.storage_ref,a.hash FROM configuration_versions c JOIN artifacts a ON a.id=c.artifact_ref AND a.instance_id=c.instance_id WHERE c.instance_id=? ORDER BY c.rowid DESC LIMIT 1',(instance,)).fetchone()
        key=row['storage_ref']
        if type(key)is not str or len(key)!=64 or any(c not in '0123456789abcdef'for c in key):raise ValueError('invalid configuration location')
        fd=os.open(str(root/'blobs'/key),os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb')as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError('invalid configuration file')
            raw=f.read(1048577)
        import hashlib
        if len(raw)>1048576 or hashlib.sha256(raw).hexdigest()!=row['hash']:raise ValueError('configuration integrity check failed')
        cfg=json.loads(raw);schema=db.execute('PRAGMA user_version').fetchone()[0]
    with sqlite3.connect((root/'control.sqlite').as_uri()+'?mode=ro',uri=True)as c:
        c.row_factory=sqlite3.Row
        row=c.execute('SELECT c.user_stopped,p.pid,p.exited_at FROM instance_control_state c LEFT JOIN process_runs p ON p.id=c.active_process_run_id WHERE c.instance_ref=?',(instance,)).fetchone()
        running=False
        if row and not row['user_stopped'] and row['pid'] and row['exited_at']is None:
            try:os.kill(row['pid'],0);running=True
            except ProcessLookupError:pass
            except PermissionError:pass
    from digital_life import __version__
    model=cfg.get('model',{})
    return {'实例目录':str(root),'实例身份':instance,'当前源码版本':__version__,'数据库版本':schema,
            '当前唤醒状态':'已唤醒'if running else'未唤醒','本次是否唤醒':'是'if wake else'否（只开面板）',
            '模型':model.get('model','未配置'),'接入方式':model.get('backend','未配置'),
            '核账模式':model.get('budget_mode','hard_limits'),'面板地址':'http://127.0.0.1:'+str(port)+'/'}

def show(data,port,wake=True):
    print('启动配置（不会显示登录令牌或密钥）',flush=True)
    for key,value in configuration(data,port,wake).items():print(key+'：'+json.dumps(value,ensure_ascii=False),flush=True)
