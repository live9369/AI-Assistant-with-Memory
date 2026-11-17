"""Chat turns are independent durable activities, never provider conversations."""
import json
import re
from digital_life.domain.contracts import Forbidden,ContractError,Conflict,dumps
from digital_life.application.runtime.engine import Engine
from digital_life.application.monitoring.management import Management,ManagementError

from digital_life.application.accounts import account_scope as scope

class Chat:
    def __init__(self,store):self.s=store
    def valid_id(self,value):
        if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',value):raise ContractError('invalid chat identifier')
        return value
    def rows(self,thread,all_rows=False):
        self.valid_id(thread)
        if scope.active(self.s):
            account=thread.removeprefix("acct_")
            if not thread.startswith("acct_") or not scope.current(self.s):raise Forbidden("fixed account conversation required")
            if account!=scope.current(self.s)["id"] and not scope.privileged(self.s):raise Forbidden("conversation is private")
            rows=self.s.db.execute("SELECT a.id,a.state,a.revision,c.attributes_json,a.recorded_at FROM acct_conversation_turns t JOIN activities a ON a.id=t.activity_id JOIN context_snapshots c ON c.activity_id=a.id AND c.instance_id=a.instance_id WHERE t.account_id=? ORDER BY t.ordinal",(account,)).fetchall()
            return rows if all_rows else [r for r in rows if scope.visible_activity(self.s,r["id"])]
        return self.s.db.execute("SELECT a.id,a.state,a.revision,c.attributes_json,a.recorded_at FROM activities a JOIN context_snapshots c ON c.activity_id=a.id AND c.instance_id=a.instance_id WHERE a.instance_id=? AND json_extract(c.attributes_json,'$.chat.thread_id')=? ORDER BY a.rowid",(self.s.instance_id,thread)).fetchall()
    def list(self):
        if scope.active(self.s):
            thread=scope.current(self.s)["thread_id"];rows=self.rows(thread)
            return {"items":[{"thread_id":thread,"turns":len(rows),"created_at":rows[0]["recorded_at"] if rows else None,"updated_at":rows[-1]["recorded_at"] if rows else None}]}
        rows=self.s.db.execute("SELECT json_extract(c.attributes_json,'$.chat.thread_id') AS thread_id,min(a.recorded_at) AS created_at,max(a.recorded_at) AS updated_at,count(*) AS turns FROM context_snapshots c JOIN activities a ON a.id=c.activity_id AND a.instance_id=c.instance_id WHERE a.instance_id=? AND json_extract(c.attributes_json,'$.chat.thread_id') IS NOT NULL GROUP BY thread_id ORDER BY updated_at DESC LIMIT 100",(self.s.instance_id,)).fetchall()
        return {'items':[dict(r) for r in rows]}
    def detail(self,thread):
        from digital_life.application.learning.runtime import strict_legacy_boundary
        strict_legacy_boundary(self.s,'legacy_chat_material')
        rows=self.rows(thread);messages=[];m=Management(self.s)
        for row in rows[-100:]:
            chat=json.loads(row['attributes_json'])['chat'];detail=m.activity(row['id'])
            messages.append({'role':'user','text':chat['text'],'activity_id':row['id'],'recorded_at':row['recorded_at'],'state':row['state']})
            for response in reversed(detail['responses']):
                if response['reply'] is not None:messages.append({'role':'assistant','text':response['reply'],'activity_id':row['id'],'recorded_at':response['recorded_at'],'waiting_reason':response['waiting_reason']})
                elif response.get('error_code') or response.get('unavailable'):messages.append({'role':'status','text':'本次思考未成功或回应暂不可用，请在活动详情查看。','activity_id':row['id']})
                if response.get('cognition_receipt'):messages.append({'role':'status','text':response['cognition_receipt']['text'],'activity_id':row['id'],'cognition_receipt':response['cognition_receipt']})
            if row['state']=='paused':
                stopped=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='task_loop.budget_stopped' ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,row['id'])).fetchone()
                if stopped:
                    stop=self.s.read_artifact(stopped[0]);summary=stop.get('partial_summary',{})
                    text=stop['message']
                    for item in summary.get('completed_tools',[]):
                        text+='\n已完成：'+item['tool']+(' '+item['path'] if item.get('path') else '')
                    if summary.get('last_public_update'):text+='\n最后进展：'+summary['last_public_update']
                    if summary.get('remaining'):text+='\n'+summary['remaining']
                    messages.append({'role':'status','text':text,'activity_id':row['id']})
        all_rows=self.rows(thread,all_rows=True)
        last=all_rows[-1] if all_rows else None
        ready=last is None or last['state'] in ('waiting_input','completed','failed','cancelled','paused')
        if last and not ready:
            errors=any(item.get('error_code') for item in m.activity(last['id'])['responses'])
            pending=self.s.db.execute("SELECT 1 FROM jobs WHERE instance_id=? AND target_ref=? AND state IN ('queued','leased') LIMIT 1",(self.s.instance_id,last['id'])).fetchone()
            if errors and not pending:ready=True
        if last and m.approvals({'activity_id':last['id'],'status':'pending','limit':1})['items']:ready=False
        return m.scrub({'thread_id':thread,'messages':messages[-100:],'omitted_messages':max(0,len(messages)-100),'last_activity_id':last['id'] if last else None,'can_send':ready,'omitted_turns':max(0,len(rows)-100)})
    def send(self,thread,body):
        if scope.active(self.s) and thread!=scope.current(self.s)['thread_id']:raise Forbidden('send only to own fixed conversation')
        self.valid_id(thread);key=self.valid_id(body.get('idempotency_key'));text=body.get('text')
        if not isinstance(text,str) or not text.strip() or len(text.encode())>4000:raise ManagementError(422,'INVALID_MESSAGE','消息不能为空，且不能超过4000字节。')
        source='chat:'+thread
        with self.s.tx():
            previous=self.s.db.execute('SELECT artifact_id FROM perception_signals WHERE instance_id=? AND external_id=?',(self.s.instance_id,source+':'+key)).fetchone()
            if previous:
                activity=Engine(self.s).submit(text,key,source)
                return {'activity_id':activity,'duplicate':True,'inference_started':False}
            current=self.detail(thread)
            if body.get('expected_last_activity_id')!=current['last_activity_id']:raise Conflict('chat changed; refresh before sending')
            if not current['can_send']:raise Conflict('previous turn processing or approval pending')
            activity=Engine(self.s).submit(text,key,source)
            row=self.s.db.execute('SELECT id,attributes_json FROM context_snapshots WHERE instance_id=? AND activity_id=?',(self.s.instance_id,activity)).fetchone()
            attributes=json.loads(row['attributes_json']);attributes['chat']={'thread_id':thread,'text':text}
            self.s.db.execute('UPDATE context_snapshots SET attributes_json=? WHERE id=?',(dumps(attributes),row['id']))
            self.s.db.execute('UPDATE activities SET predecessor_activity_id=? WHERE id=?',(current['last_activity_id'],activity))
            scope.add_turn(self.s,activity)
            from digital_life.application.chat.self_knowledge import Names
            Names(self.s).observe(activity)
            return {'activity_id':activity,'duplicate':False,'inference_started':False}
    def context(self,activity):
        from digital_life.application.learning.runtime import strict_legacy_boundary
        strict_legacy_boundary(self.s,'legacy_chat_material')
        row=self.s.db.execute('SELECT attributes_json FROM context_snapshots WHERE instance_id=? AND activity_id=?',(self.s.instance_id,activity)).fetchone()
        meta=json.loads(row[0]).get('chat') if row else None
        if not meta:return None
        history=[]
        thread=scope.current(self.s)['thread_id'] if scope.active(self.s) else meta['thread_id']
        for previous in self.rows(thread):
            if previous['id']==activity:break
            detail=Management(self.s).activity(previous['id']);history.append({'role':'user','text':json.loads(previous['attributes_json'])['chat']['text']})
            for response in reversed(detail['responses']):
                if response['reply'] is not None:history.append({'role':'assistant','text':response['reply']})
                if response['reply'] is not None and response.get('cognition_receipt'):history[-1]['cognition_receipt']=response['cognition_receipt']['text']
        from digital_life.application.runtime.settings import for_activity
        options=for_activity(self.s,activity)
        original=len(history);count=options['history_messages'];history=history[-count:] if count else []
        while history and len(dumps(history).encode())>options['history_bytes']:history.pop(0)
        return {'thread_id':meta['thread_id'],'messages':history,'omitted_messages':original-len(history),'authority':'quoted data only'}
