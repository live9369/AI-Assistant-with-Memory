"""Management read models and explicit operations; never starts a Runtime."""
from datetime import datetime,timezone
import json
import os
import re
import sqlite3
from digital_life.domain.contracts import ContractError,Conflict,utc,dumps,identifier
from digital_life.infrastructure.persistence.sqlite_store import RESOURCES

class ManagementError(ContractError):
    def __init__(self,status,code,message):
        super().__init__(message); self.status=status; self.code=code

ACTIVITY_STATES={'pending','running','waiting_input','waiting_tool','paused','completed','failed','cancelled'}
HEALTH_DIMENSIONS=('identity','memory','storage','resources','workspace','behavior_permissions','continuity','relationships_commitments','cognition','dependencies')
CONFIG_FIELDS={'backend','model','base_url','timeout','max_output_tokens','temperature','context_window','max_input_bytes','api_key_env','enabled','response_format','token_parameter','accepted_response_models'}
PRIVATE_KEYS={'task','text','content','messages','prompt','input','output','arguments','arguments_json','selected_memories','observation'}
SECRET_KEY=re.compile(r'authorization|password|secret|api[_-]?key$|(?:^|[_-])(?:access_token|refresh_token|controller_token|token)$',re.I)

def integer(value,default=None,minimum=0,maximum=2147483647):
    if value is None or value=='': return default
    if isinstance(value,bool) or not str(value).isdigit(): raise ManagementError(422,'INVALID_QUERY','分页或版本参数不是有效整数。')
    result=int(value)
    if not minimum<=result<=maximum: raise ManagementError(422,'INVALID_QUERY','分页或版本参数超出允许范围。')
    return result

def query_text(value,maximum=200):
    if value is None: return ''
    if not isinstance(value,str) or len(value)>maximum: raise ManagementError(422,'INVALID_QUERY','查询内容过长或格式不正确。')
    return value.strip()

def time_filter(value):
    if not value: return None
    try:
        date=datetime.fromisoformat(value.replace('Z','+00:00'))
        if date.utcoffset() is None: raise ValueError()
        return date.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
    except (ValueError,AttributeError): raise ManagementError(422,'INVALID_TIME','时间必须包含时区。') from None

def severity(event_type):
    name=event_type.lower()
    return 'error' if any(s in name for s in ('failed','error','critical')) else 'warning' if any(s in name for s in ('denied','revoked','cancel','unknown','rejected','stale')) else 'info'

def event_title(name):
    known={'http.request_failed':'接口请求失败','http.request_failed_diagnosed':'历史提交失败：排查结果','model.inference_failed':'思考失败：查看具体原因与输入容量','instance.prepared':'实例已准备','activity.created':'任务已保存','activity.state':'活动状态变化','action.approved':'操作已批准',
      'action.denied':'操作已拒绝','action.result':'工具结果已记录','model.configured':'模型配置已保存','model.usage':'模型用量已记录',
      'health.multidimensional':'健康检查已完成','metrics.collected':'指标已采集','management.model_probed':'模型清单检查',
      'management.approval_decided':'审批决定已记录','management.activity_cancelled':'活动已取消','management.stopped':'用户保持停止'}
    return known.get(name,'系统记录：'+name)

class Management:
    def __init__(self,store,codex=None): self.codex=codex; self.s=store; self.actor=store.config()['controller']
    def control(self):
        path=self.s.root/'control.sqlite'
        if not path.exists(): return {'user_stopped':True,'active_process_run_id':None,'runtime_epoch':0,'prepared':False}
        if path.is_symlink(): raise ContractError('invalid control database')
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True); db.row_factory=sqlite3.Row
        try:
            if db.execute('PRAGMA application_id').fetchone()[0]!=1345335351: raise ContractError('invalid control schema')
            row=db.execute('SELECT * FROM instance_control_state WHERE instance_ref=?',(self.s.instance_id,)).fetchone()
            return dict(row,prepared=True) if row else {'user_stopped':True,'active_process_run_id':None,'runtime_epoch':0,'prepared':False}
        finally: db.close()
    def config_row(self):
        return dict(self.s.db.execute('SELECT * FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone())
    def scrub(self,value,private=False):
        config=self.s.config()['model']; secrets=[]
        variable=config.get('api_key_env')
        if isinstance(variable,str) and os.environ.get(variable): secrets.append(os.environ[variable])
        token=self.s.root/'controller.token'
        if token.is_file() and not token.is_symlink():
            secret=token.read_text().strip()
            if secret: secrets.append(secret)
        def visit(item,depth=0):
            if depth>12: return '[过深内容已隐藏]'
            if isinstance(item,dict): return {str(k):'[已隐藏]' if SECRET_KEY.search(str(k)) or private and str(k).lower() in PRIVATE_KEYS else visit(v,depth+1) for k,v in list(item.items())[:100]}
            if isinstance(item,list): return [visit(v,depth+1) for v in item[:100]]
            if isinstance(item,str):
                for secret in secrets: item=item.replace(secret,'[已隐藏]')
                return item[:4000]
            return item
        return visit(value)
    def paged(self,base,params,query,clauses=(),arguments=(),maximum=100):
        limit=integer(query.get('limit'),20,1,maximum); before=integer(query.get('cursor'))
        where=list(clauses); values=list(params)+list(arguments)
        if before is not None: where.append('_cursor<?'); values.append(before)
        sql='SELECT * FROM ('+base+')'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY _cursor DESC LIMIT ?'
        rows=[dict(row) for row in self.s.db.execute(sql,(*values,limit+1))]
        more=len(rows)>limit; rows=rows[:limit]
        cursor=str(rows[-1]['_cursor']) if more and rows else None
        for row in rows: row.pop('_cursor',None)
        return {'items':rows,'limit':limit,'next_cursor':cursor,'has_more':more}
    def activity_row(self,ref):
        row=self.s.db.execute('SELECT * FROM activities WHERE id=? AND instance_id=?',(ref,self.s.instance_id)).fetchone()
        if row is None: raise ManagementError(404,'NOT_FOUND','找不到该活动。')
        return dict(row)
    def activities(self,query):
        state=query_text(query.get('state')); search=query_text(query.get('q')); clauses=[]; values=[]
        if state:
            if state not in ACTIVITY_STATES: raise ManagementError(422,'INVALID_STATE','活动状态无效。')
            clauses.append('state=?'); values.append(state)
        if search: clauses.append('instr(lower(coalesce(task,\'\')||id),lower(?))>0'); values.append(search)
        base="""SELECT a.rowid AS _cursor,a.id,a.state,a.recorded_at,a.revision,a.deadline,a.cancel_requested_at,
          (SELECT json_extract(c.attributes_json,'$.task') FROM context_snapshots c WHERE c.activity_id=a.id AND c.instance_id=a.instance_id ORDER BY c.rowid DESC LIMIT 1) AS task
          FROM activities a WHERE a.instance_id=?"""
        result=self.paged(base,[self.s.instance_id],query,clauses,values)
        for row in result['items']: row['task']=(row['task'] or '')[:320]; row['can_cancel']=row['state'] not in ('completed','failed','cancelled')
        return self.scrub(result)
    def activity(self,ref):
        activity=self.activity_row(ref)
        contexts=self.s.db.execute('SELECT attributes_json FROM context_snapshots WHERE instance_id=? AND activity_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,ref)).fetchone()
        task=json.loads(contexts[0]).get('task','') if contexts else ''
        steps=[dict(r) for r in self.s.db.execute('SELECT step_no,step_type,state,started_at,finished_at FROM activity_steps WHERE instance_id=? AND activity_id=? ORDER BY step_no LIMIT 100',(self.s.instance_id,ref))]
        thoughts=[dict(r) for r in self.s.db.execute('SELECT id,state,recorded_at,purpose,accepted_result_id FROM thought_requests WHERE instance_id=? AND activity_id=? ORDER BY rowid DESC LIMIT 50',(self.s.instance_id,ref))]
        responses=[]
        for thought in thoughts:
            response={'request_id':thought['id'],'recorded_at':thought['recorded_at'],'state':thought['state'],'reply':None,'waiting_reason':None,'error_code':None}
            result=self.s.db.execute("SELECT r.* FROM thought_results r WHERE r.id=? AND r.request_id=? AND r.instance_id=? AND r.validation_state='valid' AND r.acceptance='accepted'",(thought['accepted_result_id'],thought['id'],self.s.instance_id)).fetchone()
            if result:
                try:
                    output=self.s.read_artifact(result['parsed_artifact_id'])
                    from digital_life.infrastructure.llm.schemas import validate
                    validate(output)
                    response['reply']=output['explanation']
                    from digital_life.application.cognition.cognition_receipts import for_request
                    receipt=for_request(self.s,ref,thought['id'])
                    if receipt is not None:response['cognition_receipt']=receipt
                    response['recorded_at']=result['received_at']
                    if output['action']['tool'] in ('wait','ask'):response['waiting_reason']=output['action']['arguments']['reason']
                except (ContractError,OSError,ValueError,TypeError,KeyError):response['unavailable']=True
            attempt=self.s.db.execute('SELECT error_code FROM thought_attempts WHERE request_id=? AND instance_id=? ORDER BY rowid DESC LIMIT 1',(thought['id'],self.s.instance_id)).fetchone()
            if attempt and attempt['error_code']:response['error_code']=attempt['error_code']
            responses.append(response)
        transitions=[dict(r) for r in self.s.db.execute('SELECT recorded_at,from_state,to_state,reason_code FROM activity_state_events WHERE instance_id=? AND activity_id=? ORDER BY transition_no LIMIT 100',(self.s.instance_id,ref))]
        approvals=self.approvals({'activity_id':ref,'limit':100})['items']
        return self.scrub(dict(activity,task=task,steps=steps,thoughts=thoughts,responses=responses,transitions=transitions,approvals=approvals,can_cancel=activity['state'] not in ('completed','failed','cancelled')))
    def approval_base(self):
        now=utc()
        sql="""SELECT r.rowid AS _cursor,r.*,i.arguments_json,i.deadline AS action_deadline,i.state AS action_state,
          i.proposal_revision AS current_proposal_revision,i.arguments_hash AS current_arguments_hash,t.name AS tool,
          a.id AS activity_id,a.state AS activity_state,a.cancel_requested_at,
          (SELECT json_extract(c.attributes_json,'$.task') FROM context_snapshots c WHERE c.activity_id=a.id AND c.instance_id=a.instance_id ORDER BY c.rowid DESC LIMIT 1) AS task,
          CASE WHEN r.decision<>'pending' THEN r.decision
            WHEN a.cancel_requested_at IS NOT NULL OR a.state IN ('completed','failed','cancelled') OR i.state<>'awaiting_approval' THEN 'cancelled'
            WHEN r.expires_at<=? OR i.deadline<=? THEN 'expired' ELSE 'pending' END AS status
          FROM approval_requests r JOIN action_intents i ON i.id=r.action_ref AND i.instance_id=r.instance_id
          JOIN tool_definitions t ON t.id=r.tool_id AND t.instance_id=r.instance_id
          JOIN decision_candidates c ON c.id=i.candidate_id AND c.instance_id=r.instance_id
          JOIN decision_records d ON d.id=c.decision_id AND d.instance_id=r.instance_id
          JOIN activities a ON a.id=d.activity_id AND a.instance_id=r.instance_id WHERE r.instance_id=?"""
        return sql,[now,now,self.s.instance_id]
    def approvals(self,query):
        base,params=self.approval_base(); clauses=[]; args=[]
        status=query_text(query.get('status') or query.get('decision'))
        if status:
            if status not in ('pending','approved','rejected','expired','cancelled'): raise ManagementError(422,'INVALID_STATE','审批状态无效。')
            clauses.append('status=?'); args.append(status)
        activity=query_text(query.get('activity_id'))
        if activity: clauses.append('activity_id=?'); args.append(activity)
        search=query_text(query.get('q'))
        if search: clauses.append('instr(lower(tool||coalesce(task,\'\')||id),lower(?))>0'); args.append(search)
        result=self.paged(base,params,query,clauses,args)
        for row in result['items']:
            row.pop('arguments_json',None); row['task']=(row.get('task') or '')[:240]; row['can_decide']=row['status']=='pending'
        return self.scrub(result)
    def approval(self,ref):
        base,params=self.approval_base()
        row=self.s.db.execute('SELECT * FROM ('+base+') WHERE id=?',(*params,ref)).fetchone()
        if row is None: raise ManagementError(404,'NOT_FOUND','找不到该审批。')
        result=dict(row); result.pop('_cursor',None)
        result['arguments']=json.loads(result.pop('arguments_json')); result['scope']=json.loads(result.pop('requested_scope'))
        result['can_decide']=result['status']=='pending'
        return self.scrub(result)
    def decide(self,ref,body):
        from digital_life.application.accounts.authorization import Policy
        decision=body.get('decision')
        if decision not in ('approved','rejected'): raise ManagementError(422,'INVALID_DECISION','请选择批准或拒绝。')
        with self.s.tx():
            row=self.approval(ref)
            expected=integer(body.get('expected_revision'))
            if expected is None or expected!=row['revision'] or body.get('expected_arguments_hash')!=row['arguments_hash']: raise Conflict('approval snapshot changed')
            if not row['can_decide']: raise Conflict('approval no longer actionable')
            reason=query_text(body.get('reason'),1000)
            result=Policy(self.s).approve(ref,self.actor) if decision=='approved' else Policy(self.s).deny(ref,self.actor)
            self.s.event('management.approval_decided',payload={'approval':ref,'decision':decision,'activity':row['activity_id'],'reason':reason},activity=row['activity_id'],lane='control')
            return dict(result,decision=decision,inference_started=False,runtime_started=False)
    def cancel(self,ref,body):
        from digital_life.application.runtime.engine import Engine
        from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
        with dispatch_gate(self.s.root),self.s.tx():
            row=self.activity_row(ref); expected=integer(body.get('expected_revision'))
            if expected is None or expected!=row['revision']: raise Conflict('activity revision changed')
            Engine(self.s).cancel(ref,self.actor)
            self.s.event('management.activity_cancelled',payload={'activity':ref},activity=ref,lane='control')
            return {'cancelled':ref,'runtime_started':False}
    def model(self):
        config=self.s.config()['model']; row=self.config_row(); control=self.control()
        clean={k:v for k,v in config.items() if k in CONFIG_FIELDS}
        variable=config.get('api_key_env'); key_present=bool(os.environ.get(variable)) if isinstance(variable,str) else False
        latest_probe=None
        for event in self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type='management.model_probed' ORDER BY event_seq DESC LIMIT 50",(self.s.instance_id,)):
            payload=self.s.read_artifact(event[0])
            if payload.get('configuration_id')==row['id']: latest_probe=payload; break
        return self.scrub({'configuration':clean,'configuration_id':row['id'],'version':row['version'],'recorded_at':row['recorded_at'],
          'can_edit':bool(control['user_stopped']) and not control['active_process_run_id'],'credential_present':key_present,'last_probe':latest_probe,'codex_auth_scope':'instance' if config.get('auth_home') else 'local'})
    def templates(self): return json.loads((RESOURCES/'model-templates.json').read_text())
    def validate_model(self,body):
        from digital_life.application.runtime.configuration import validate_model_config
        config=body.get('configuration')
        if not isinstance(config,dict): raise ManagementError(422,'INVALID_CONFIGURATION','请提供模型配置对象。')
        if config.get('backend')=='codex_cli':
            if self.codex is None: raise ManagementError(422,'CLI_CONFIGURATION_REQUIRED','请通过面板服务配置Codex。')
            config=self.codex.config(config,body.get('codex_auth_scope','local'))
        reasoner=validate_model_config(config)
        return {'valid':True,'route':reasoner.name,'network_requested':False,'inference_executed':False}
    def save_model(self,body):
        from digital_life.application.runtime.configuration import configure_model
        self.validate_model(body)
        with self.s.tx():
            if body.get('expected_configuration_id')!=self.config_row()['id']: raise Conflict('model configuration changed')
            config=body['configuration']
            if config.get('backend')=='codex_cli': config=self.codex.config(config,body.get('codex_auth_scope','local'))
            result=configure_model(self.s,config,self.actor,check_available=False)
            return dict(result,network_requested=False,runtime_started=False)
    def probe_model(self,body,probe_fn=None):
        from digital_life.infrastructure.llm.inference import probe
        row=self.config_row()
        if body.get('expected_configuration_id')!=row['id']: raise Conflict('model configuration changed')
        config=dict(self.s.config()['model']); config['timeout']=min(config.get('timeout',120),10)
        try:
            result=(probe_fn or probe)(config)
            result={'available':result.get('available') is True,'scope':'模型清单；尚未验证生成质量'}
        except Exception:
            result={'available':False,'scope':'模型清单','reason':'清单检查未通过。请检查服务、启用状态、环境变量或供应商接口支持。'}
        result.update(configuration_id=row['id'],checked_at=utc(),inference_executed=False)
        with self.s.tx(): self.s.event('management.model_probed',payload=result,lane='telemetry')
        return result
    def health(self):
        event=self.s.db.execute("SELECT payload_artifact_id,recorded_at FROM runtime_events WHERE instance_id=? AND event_type='health.multidimensional' ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,)).fetchone()
        if event:
            dimensions=self.s.read_artifact(event[0]); checked=event['recorded_at']
            if not isinstance(dimensions,dict) or 'redacted_by' in dimensions: dimensions={}
        else: dimensions={}; checked=None
        complete={name:dimensions.get(name,{'state':'unknown','reason':'尚无该维度的检查证据。'}) for name in HEALTH_DIMENSIONS}
        states={r.get('state','unknown') for r in complete.values()}
        state=next((v for v in ('critical','degraded','stressed','recovering','unknown') if v in states),'healthy')
        stale=checked is None or (datetime.now(timezone.utc)-datetime.fromisoformat(checked.replace('Z','+00:00'))).total_seconds()>30
        return self.scrub({'state':state,'dimensions':complete,'checked_at':checked,'stale':stale,'ttl_seconds':30})
    def check_health(self):
        from digital_life.application.lifecycle.health_monitor import HealthMonitor
        HealthMonitor(self.s).scan(connect_model=False)
        return self.health()
    def overview(self):
        counts={row['state']:row['n'] for row in self.s.db.execute('SELECT state,count(*) n FROM activities WHERE instance_id=? GROUP BY state',(self.s.instance_id,))}
        base,args=self.approval_base()
        pending=self.s.db.execute("SELECT count(*) FROM ("+base+") WHERE status='pending'",args).fetchone()[0]
        control=self.control(); locked=(self.s.root/'WAKE_DISABLED').exists(); restore=(self.s.root/'RESTORE_RECONCILIATION_REQUIRED').exists()
        model=self.model(); health=self.health()
        return {'instance_id':self.s.instance_id,'name':self.s.config().get('name','原初00'),'wake_disabled':locked,'restore_reconciliation_required':restore,
          'runtime_status':'locked' if locked or restore else 'stopped' if control['user_stopped'] else 'registered' if control['active_process_run_id'] else 'idle',
          'control':control,'activity_counts':counts,'active_activities':sum(v for k,v in counts.items() if k not in ('completed','failed','cancelled')),
          'pending_approvals':pending,'model':model,'health':{'state':health['state'],'stale':health['stale'],'checked_at':health['checked_at']},
          'recent_events':self.logs({'limit':5})['items'],'read_only':True}
    def log_query(self,query,maximum=100):
        clauses=[]; args=[]
        level=query_text(query.get('level')); category=query_text(query.get('event_type')); activity=query_text(query.get('activity_id')); q=query_text(query.get('q'))
        if level:
            if level not in ('info','warning','error'): raise ManagementError(422,'INVALID_LEVEL','日志等级无效。')
            clauses.append('level=?'); args.append(level)
        if category: clauses.append('event_type=?'); args.append(category)
        if activity: clauses.append('activity_id=?'); args.append(activity)
        if q: clauses.append('instr(lower(event_type||source),lower(?))>0'); args.append(q)
        start=time_filter(query.get('from')); end=time_filter(query.get('to'))
        if start and end and start>end: raise ManagementError(422,'INVALID_TIME','开始时间不能晚于结束时间。')
        if start: clauses.append('recorded_at>=?'); args.append(start)
        if end: clauses.append('recorded_at<=?'); args.append(end)
        since=integer(query.get('since_seq'))
        if since is not None: clauses.append('event_seq>?'); args.append(since)
        base="""SELECT event_seq AS _cursor,event_seq,id,event_type,source,recorded_at,activity_id,lane,
          CASE WHEN event_type LIKE '%failed%' OR event_type LIKE '%error%' OR event_type LIKE '%critical%' THEN 'error'
            WHEN event_type LIKE '%denied%' OR event_type LIKE '%revoked%' OR event_type LIKE '%cancel%' OR event_type LIKE '%unknown%' OR event_type LIKE '%rejected%' OR event_type LIKE '%stale%' THEN 'warning' ELSE 'info' END AS level
          FROM runtime_events WHERE instance_id=?"""
        return self.paged(base,[self.s.instance_id],query,clauses,args,maximum)
    def logs(self,query):
        result=self.log_query(query)
        for row in result['items']: row['title']=event_title(row['event_type'])
        return self.scrub(result)
    def log(self,seq):
        from digital_life.application.learning.runtime import strict_legacy_boundary
        strict_legacy_boundary(self.s,'legacy_management_export')
        seq=integer(seq,minimum=1)
        row=self.s.db.execute('SELECT * FROM runtime_events WHERE instance_id=? AND event_seq=?',(self.s.instance_id,seq)).fetchone()
        if row is None: raise ManagementError(404,'NOT_FOUND','找不到该日志。')
        item=dict(row); item['level']=severity(item['event_type']); item['title']=event_title(item['event_type'])
        item['payload']=self.scrub(self.s.read_artifact(item['payload_artifact_id']),private=True) if item['payload_artifact_id'] else {'object':item['payload_object_id']}
        return self.scrub(item)
    def export_logs(self,query):
        from digital_life.application.learning.runtime import strict_legacy_boundary
        strict_legacy_boundary(self.s,'legacy_management_export')
        query=dict(query); query['limit']=integer(query.get('limit'),500,1,500)
        result=self.log_query(query,500)
        return {'items':[self.log(row['event_seq']) for row in result['items']],'truncated':result['has_more'],'limit':query['limit']}
