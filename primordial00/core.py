"""Small durable activity engine. Each model request is an independent value."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

def uid(): return uuid.uuid4().hex
def encode(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value): return hashlib.sha256(value.encode()).hexdigest()

class TestReasoner:
    """No conversation state; this verifies plumbing, not actual intelligence."""
    name='test-reasoner-v1'
    def generate(self,request):
        return {'schema_version':1,'action':{'kind':'write_note','text':request['task']},
                'explanation':'测试推理器：将当前任务写入受控笔记。'}

class Life:
    def __init__(self,root):
        self.root=Path(root).resolve()
        if not (self.root/'runtime.sqlite').exists(): raise ValueError('请先 init 初始化实例')
        self.db=sqlite3.connect(str(self.root/'runtime.sqlite'),timeout=5)
        if self.db.execute('PRAGMA application_id').fetchone()[0]!=1345335344:
            self.db.close(); raise ValueError('数据库不是原初00首版，禁止混用完整架构库')
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.execute('PRAGMA synchronous=FULL')
    def close(self): self.db.close()
    @classmethod
    def initialize(cls,root,name='原初00'):
        root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
        existed=(root/'runtime.sqlite').exists()
        db=sqlite3.connect(str(root/'runtime.sqlite'))
        if existed and db.execute('PRAGMA application_id').fetchone()[0]!=1345335344:
            db.close(); raise ValueError('已有数据库类型不同，初始化已停止')
        db.executescript((Path(__file__).resolve().parent/'resources/primordial00.sql').read_text())
        with db:
            if not db.execute('SELECT id FROM identity_instances').fetchone():
                db.execute('INSERT INTO identity_instances VALUES(?,?,?,?,?)',(uid(),name,time.time(),'active','local-user'))
        db.close(); (root/'notes').mkdir(exist_ok=True)
        return cls(root)
    def instance(self): return self.db.execute('SELECT * FROM identity_instances').fetchone()
    @contextlib.contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try: yield; self.db.commit()
        except BaseException: self.db.rollback(); raise
    def emit(self,text,key=None,source='user'):
        if not isinstance(text,str) or not text.strip() or len(text)>16000: raise ValueError('任务须为1—16000字符')
        key=key or uid(); payload=encode({'text':text})
        with self.tx():
            old=self.db.execute('SELECT id,payload FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=?',(self.instance()['id'],source,key)).fetchone()
            if old:
                if old['payload']!=payload: raise ValueError('幂等键对应不同输入')
                return self.db.execute('SELECT id FROM activities WHERE event_id=?',(old['id'],)).fetchone()[0]
            event,activity=uid(),uid()
            self.db.execute('INSERT INTO runtime_events(id,instance_id,source,source_event_id,payload,created_at) VALUES(?,?,?,?,?,?)',(event,self.instance()['id'],source,key,payload,time.time()))
            self.db.execute('INSERT INTO activities(id,event_id,state) VALUES(?,?,?)',(activity,event,'pending'))
            self.db.execute('INSERT INTO jobs(id,activity_id,due_at,state) VALUES(?,?,?,?)',(uid(),activity,time.time(),'queued'))
            self.db.execute('INSERT INTO memories VALUES(?,?,?,?,?,?)',(uid(),self.instance()['id'],event,text,'observation',time.time()))
            self.db.execute('INSERT INTO goals VALUES(?,?,?,?)',(uid(),activity,text,'active'))
        return activity
    def prepare(self,activity,model_name='test-reasoner-v1'):
        with self.tx():
            row=self.db.execute('SELECT a.*,e.payload FROM activities a JOIN runtime_events e ON e.id=a.event_id WHERE a.id=?',(activity,)).fetchone()
            if row is None or row['cancelled']: return None
            prior=self.db.execute('SELECT * FROM thought_requests WHERE activity_id=?',(activity,)).fetchone()
            if prior:
                if json.loads(prior['request_json'])['model']!=model_name: raise ValueError('已有请求固定到其他模型；请取消后创建新活动，不能透明切换模型')
                return dict(prior)
            memories=[dict(r) for r in self.db.execute('SELECT id,content,kind FROM memories ORDER BY created_at DESC LIMIT 8')]
            request={'schema_version':1,'task':json.loads(row['payload'])['text'],
                'instance':{'id':self.instance()['id'],'name':self.instance()['name']},
                'selected_memories':memories,'instructions':'只返回结构化 write_note 候选，不执行工具。',
                'model':model_name,'context_mode':'fresh_request'}
            raw=encode(request); tid=uid()
            self.db.execute('INSERT INTO thought_requests VALUES(?,?,?,?,?,?,?,NULL)',(tid,activity,raw,digest(raw),row['revision'],row['input_epoch'],'prepared'))
            self.db.execute("UPDATE activities SET state='running',revision=revision+1 WHERE id=?",(activity,))
        return dict(self.db.execute('SELECT * FROM thought_requests WHERE id=?',(tid,)).fetchone())
    def think(self,activity,reasoner):
        req=self.prepare(activity,reasoner.name)
        if req is None or req['accepted_result_id']: return
        if reasoner.name!=json.loads(req['request_json'])['model']: raise ValueError('模型不匹配；真实模型对接需独立配置版本')
        with self.tx():
            n=self.db.execute('SELECT count(*) FROM thought_attempts WHERE request_id=?',(req['id'],)).fetchone()[0]+1
            if n>3: raise ValueError('思考尝试预算已耗尽')
            attempt=uid(); self.db.execute('INSERT INTO thought_attempts VALUES(?,?,?,?,?)',(attempt,req['id'],n,'sent',time.time()))
        # No database transaction across model computation. Reconstruct a fresh object.
        try:
            from .models import validate_output
            output=validate_output(reasoner.generate(json.loads(req['request_json'])))
            action=output['action']
        except Exception:
            with self.tx(): self.db.execute("UPDATE thought_attempts SET state='failed' WHERE id=?",(attempt,))
            raise
        with self.tx():
            self.db.execute("UPDATE thought_attempts SET state='received' WHERE id=?",(attempt,))
            current=self.db.execute('SELECT * FROM activities WHERE id=?',(activity,)).fetchone()
            accepted=self.db.execute('SELECT accepted_result_id FROM thought_requests WHERE id=?',(req['id'],)).fetchone()[0]
            if accepted or current['cancelled'] or current['input_epoch']!=req['input_epoch']: return
            result=uid(); self.db.execute('INSERT INTO thought_results VALUES(?,?,?,?,?)',(result,req['id'],attempt,encode(output),time.time()))
            self.db.execute("UPDATE thought_requests SET state='succeeded',accepted_result_id=? WHERE id=?",(result,req['id']))
            arguments=encode({'text':action['text']})
            self.db.execute('INSERT INTO action_intents VALUES(?,?,?,?,?,?,?,?)',(uid(),activity,'write_note',arguments,digest(arguments),'awaiting_approval',None,activity))
            self.db.execute("UPDATE activities SET state='waiting_input',revision=revision+1 WHERE id=?",(activity,))
            self.db.execute("UPDATE jobs SET state='waiting' WHERE activity_id=?",(activity,))
    def approve(self,activity):
        with self.tx():
            a=self.db.execute('SELECT * FROM activities WHERE id=?',(activity,)).fetchone()
            if not a or a['cancelled']: raise ValueError('活动不存在或已取消')
            intent=self.db.execute('SELECT * FROM action_intents WHERE activity_id=?',(activity,)).fetchone()
            if not intent: raise ValueError('尚未形成动作提案')
            if intent['state'] not in ('awaiting_approval','authorized'): raise ValueError('当前动作不可审批')
            self.db.execute("UPDATE action_intents SET state='authorized',approved_hash=arguments_hash WHERE id=?",(intent['id'],))
            self.db.execute("UPDATE activities SET state='running',revision=revision+1 WHERE id=?",(activity,))
            self.db.execute("UPDATE jobs SET state='queued' WHERE activity_id=?",(activity,))
    def execute(self,activity,interrupt_after_effect=False):
        with self.tx():
            intent=self.db.execute('SELECT i.*,a.cancelled FROM action_intents i JOIN activities a ON a.id=i.activity_id WHERE activity_id=?',(activity,)).fetchone()
            if not intent or intent['cancelled'] or intent['state'] in ('awaiting_approval','succeeded','cancelled'): return
            if intent['approved_hash']!=digest(intent['arguments_json']): raise ValueError('动作参数未获得批准')
            attempt=uid(); n=self.db.execute('SELECT count(*) FROM action_attempts WHERE intent_id=?',(intent['id'],)).fetchone()[0]+1
            if n>5: raise ValueError('工具恢复尝试预算已耗尽')
            self.db.execute('INSERT INTO action_attempts VALUES(?,?,?,?,NULL)',(attempt,intent['id'],n,'running'))
            self.db.execute("UPDATE action_intents SET state='running' WHERE id=?",(intent['id'],))
        # Only supported tool: deterministic path, exclusive creation, verifiable content.
        if (self.root/'notes').is_symlink() or not (self.root/'notes').is_dir():
            raise ValueError('受控笔记目录不可用或为符号链接')
        target=self.root/'notes'/f'{intent["operation_key"]}.txt'
        text=json.loads(intent['arguments_json'])['text']; expected=text.encode('utf-8')
        try:
            try:
                with target.open('xb') as stream:
                    stream.write(expected); stream.flush(); os.fsync(stream.fileno())
            except FileExistsError:
                if target.is_symlink() or target.read_bytes()!=expected: raise ValueError('既有结果不匹配；暂停恢复，禁止覆盖')
            if target.is_symlink() or target.read_bytes()!=expected: raise ValueError('结果核验失败')
            if interrupt_after_effect: raise RuntimeError('故障注入：工具成功后、回执提交前中断')
        except BaseException:
            with self.tx():
                self.db.execute("UPDATE action_attempts SET state='unknown' WHERE id=?",(attempt,))
                self.db.execute("UPDATE action_intents SET state='unknown' WHERE id=?",(intent['id'],))
            raise
        with self.tx():
            receipt=encode({'path':str(target),'sha256':hashlib.sha256(expected).hexdigest(),'verified':True})
            self.db.execute("UPDATE action_attempts SET state='succeeded',receipt_json=? WHERE id=?",(receipt,attempt))
            self.db.execute('INSERT OR IGNORE INTO action_results VALUES(?,?,?,?)',(intent['id'],attempt,receipt,time.time()))
            self.db.execute("UPDATE action_intents SET state='succeeded' WHERE id=?",(intent['id'],))
            a=self.db.execute('SELECT event_id FROM activities WHERE id=?',(activity,)).fetchone()
            self.db.execute('INSERT OR IGNORE INTO memories VALUES(?,?,?,?,?,?)',(uid(),self.instance()['id'],a['event_id'],'受控笔记已写入并核验：'+receipt,'outcome',time.time()))
            self.db.execute("UPDATE goals SET state='completed' WHERE activity_id=?",(activity,))
            self.db.execute("UPDATE activities SET state='completed',revision=revision+1 WHERE id=?",(activity,))
            self.db.execute("UPDATE jobs SET state='completed' WHERE activity_id=?",(activity,))
            self.db.execute("UPDATE commitments SET state='fulfilled' WHERE activity_id=?",(activity,))
    def cancel(self,activity):
        with self.tx():
            row=self.db.execute('SELECT state FROM activities WHERE id=?',(activity,)).fetchone()
            if not row: raise ValueError('活动不存在')
            if row[0]=='completed': raise ValueError('已完成活动不能被取消为未发生')
            self.db.execute("UPDATE activities SET cancelled=1,state='cancelled',revision=revision+1,input_epoch=input_epoch+1 WHERE id=?",(activity,))
            self.db.execute("UPDATE jobs SET state='cancelled' WHERE activity_id=?",(activity,))
            self.db.execute("UPDATE goals SET state='cancelled' WHERE activity_id=?",(activity,))
    def commit(self,text,due_at):
        if not text.strip() or len(text)>16000: raise ValueError('承诺内容无效')
        with self.tx():
            key=uid(); self.db.execute('INSERT INTO commitments VALUES(?,?,?,?,NULL,?)',(key,self.instance()['id'],text,due_at,'active'))
        return key
    def due_commitments(self):
        for row in self.db.execute("SELECT * FROM commitments WHERE state='active' AND activity_id IS NULL AND due_at<=?",(time.time(),)).fetchall():
            activity=self.emit(row['content'],row['id'],'commitment')
            with self.tx(): self.db.execute('UPDATE commitments SET activity_id=? WHERE id=?',(activity,row['id']))
    def tick(self,reasoner=None):
        if (self.root/'WAKE_DISABLED').exists(): raise ValueError('用户已锁定唤醒；禁止执行生命活动')
        if reasoner is None:
            from .models import resolve
            reasoner=resolve(self.root)
        if (self.root/'control.sqlite').exists():
            db=sqlite3.connect(str(self.root/'control.sqlite'))
            try: stopped=db.execute('SELECT user_stopped FROM settings WHERE id=1').fetchone()[0]
            finally: db.close()
            if stopped: return 0
        if self.instance()['state']=='stopped': return 0
        self.due_commitments()
        jobs=self.db.execute("SELECT * FROM jobs WHERE state IN ('queued','running') AND due_at<=? ORDER BY due_at LIMIT 16",(time.time(),)).fetchall()
        for job in jobs:
            with self.tx(): self.db.execute("UPDATE jobs SET state='running',attempt=attempt+1 WHERE id=?",(job['id'],))
            try:
                self.think(job['activity_id'],reasoner)
                self.execute(job['activity_id'])
            except Exception as error:
                # Isolate failed tasks; never hide uncertain external effects.
                with self.tx():
                    self.db.execute("UPDATE jobs SET state='failed' WHERE id=?",(job['id'],))
                    self.db.execute("UPDATE activities SET state='failed',error=?,revision=revision+1 WHERE id=? AND cancelled=0",(str(error),job['activity_id']))
                    self.db.execute("UPDATE goals SET state='failed' WHERE activity_id=?",(job['activity_id'],))
        return len(jobs)
    def health(self):
        integrity=self.db.execute('PRAGMA integrity_check').fetchone()[0]
        foreign=self.db.execute('PRAGMA foreign_key_check').fetchall()
        notes_ok=(self.root/'notes').is_dir() and not (self.root/'notes').is_symlink()
        failed=self.db.execute("SELECT count(*) FROM jobs WHERE state='failed'").fetchone()[0]
        unknown=self.db.execute("SELECT count(*) FROM action_intents WHERE state='unknown'").fetchone()[0]
        state='healthy' if integrity=='ok' and not foreign and notes_ok and not failed and not unknown else 'degraded'
        from .models import inspect
        readiness=inspect(self.root)
        evidence={'integrity':integrity,'foreign_key_errors':len(foreign),'notes_directory':notes_ok,'failed_jobs':failed,'unknown_actions':unknown,'model_readiness':readiness['status'],'inference_verified':False}
        with self.tx(): self.db.execute('INSERT INTO health_checks(checked_at,state,evidence_json) VALUES(?,?,?)',(time.time(),state,encode(evidence)))
        return {'state':state,'evidence':evidence}
    def status(self):
        from .models import inspect
        return {'instance':dict(self.instance()),'model_readiness':inspect(self.root),
            'activities':[dict(r) for r in self.db.execute('SELECT * FROM activities')],
            'pending_actions':[dict(r) for r in self.db.execute("SELECT * FROM action_intents WHERE state<>'succeeded'")],
            'commitments':[dict(r) for r in self.db.execute('SELECT * FROM commitments')],
            'memory_count':self.db.execute('SELECT count(*) FROM memories').fetchone()[0]}
