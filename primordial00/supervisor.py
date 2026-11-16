from digital_life.infrastructure.processes.locks import exclusive
"""External process supervisor; persistent stop survives all runtime restarts."""
import contextlib
import fcntl
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from .core import Life, encode


def control(root):
    root=Path(root).resolve()
    if not (root/'runtime.sqlite').exists(): raise ValueError('请先初始化实例')
    existed=(root/'control.sqlite').exists()
    db=sqlite3.connect(str(root/'control.sqlite'))
    if existed and db.execute('PRAGMA application_id').fetchone()[0]!=1345335345:
        db.close(); raise ValueError('控制库类型不符，禁止覆盖')
    db.executescript('''
    PRAGMA application_id=1345335345;
    CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),user_stopped INTEGER NOT NULL CHECK(user_stopped IN(0,1)),epoch INTEGER NOT NULL);
    INSERT OR IGNORE INTO settings VALUES(1,0,0);
    CREATE TABLE IF NOT EXISTS process_runs(id INTEGER PRIMARY KEY,epoch INTEGER NOT NULL,started_at REAL NOT NULL,ended_at REAL,result TEXT,output TEXT);
    CREATE TABLE IF NOT EXISTS wake_plans(id INTEGER PRIMARY KEY CHECK(id=1),next_due_at REAL,updated_at REAL NOT NULL);
    ''')
    return db

def set_stopped(root,stopped):
    # Runtime lock is also an execution-start serialization boundary for this tiny CLI.
    with exclusive(root):
        db=control(root)
        with db: db.execute('UPDATE settings SET user_stopped=? WHERE id=1',(int(stopped),))
        db.close()

def once(root):
    root=Path(root).resolve()
    if (root/'WAKE_DISABLED').exists():
        return {'state':'wake_disabled_by_user','spawned':False}
    with exclusive(root,'supervisor.lock'):
        db=control(root)
        if db.execute('SELECT user_stopped FROM settings WHERE id=1').fetchone()[0]:
            db.close(); return {'state':'user_stopped','spawned':False}
        # Bounded self-maintenance: restore a missing output directory, never overwrite files.
        notes=root/'notes'
        if not notes.exists(): notes.mkdir()
        if notes.is_symlink(): db.close(); raise ValueError('笔记目录不能是符号链接')
        with db:
            db.execute('UPDATE settings SET epoch=epoch+1 WHERE id=1')
            epoch=db.execute('SELECT epoch FROM settings WHERE id=1').fetchone()[0]
            run=db.execute('INSERT INTO process_runs(epoch,started_at) VALUES(?,?)',(epoch,time.time())).lastrowid
        try:
            from .models import resolve
            reasoner=resolve(root)
            # Tick may process up to 16 activities; each thought has a bounded timeout.
            runtime_timeout=16*getattr(reasoner,'timeout',0)+30
            process=subprocess.run([sys.executable,'-m','primordial00','--data',str(root),'_tick'],cwd=str(Path(__file__).resolve().parents[1]),capture_output=True,text=True,timeout=runtime_timeout)
            result='succeeded' if process.returncode==0 else 'failed'
            output=(process.stdout+process.stderr)[-16000:]
        except subprocess.TimeoutExpired:
            result='timeout'; output='Runtime timeout; external action status must be reconciled on next wake.'
        with db: db.execute('UPDATE process_runs SET ended_at=?,result=?,output=? WHERE id=?',(time.time(),result,output,run))
        if result!='succeeded': db.close(); return {'state':result,'spawned':True,'epoch':epoch,'detail':output}
        with exclusive(root):
            life=Life(root)
            next_due=life.db.execute("SELECT min(due_at) FROM commitments WHERE state='active' AND activity_id IS NULL").fetchone()[0]
            life.close()
            with db: db.execute('INSERT OR REPLACE INTO wake_plans VALUES(1,?,?)',(next_due,time.time()))
        db.close()
        return {'state':'awake_then_idle','spawned':True,'epoch':epoch,'next_due_at':next_due,'runtime':output.strip()}

def watch(root,cycles,interval):
    if cycles<1 or not 0.05<=interval<=60: raise ValueError('cycles>=1，interval须在0.05—60秒之间')
    results=[]
    for i in range(cycles):
        results.append(once(root))
        if i+1<cycles: time.sleep(interval)
    return results
