"""Host-verified self configuration and explicit controller-owned names."""
import re


class Names:
    def __init__(self,store):self.s=store
    def anchor(self):return max(self.s.rows('identity_anchors'),key=lambda r:r['version'])
    def current(self):
        cfg=self.s.config();anchor=self.anchor()
        row=self.s.db.execute("SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type='identity.name_selected' ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,)).fetchone()
        if row:
            value=self.s.read_artifact(row['payload_artifact_id'])
            if value.get('anchor')==anchor['id'] and value.get('actor')==cfg['controller']:
                return dict(name=value['name'],source='controller-name-selection',event=row['id'])
        return dict(name=cfg['name'],source='current-configuration',event=None)
    @staticmethod
    def proposed(message):
        pattern=r'(?:不如|以后(?:就)?|那(?:就)?|还是)?\s*(?:叫你|称呼你为|给你(?:取名|起名)(?:为|叫)?|你的名字(?:改为|叫))\s*[“"「『]([^”"」』\n]{1,40})[”"」』]'
        match=re.search(pattern,message)
        if not match:return None
        prefix=message[:match.start()]
        if len(prefix)>80 or any(x in prefix for x in ('例如','假设','假如','转述','不要','不能','不是','分析','这句话','有人说','他说','她说')):return None
        name=match[1].strip()
        return name if name and not any(x in name for x in '<>\x00') else None
    def observe(self,activity):
        row=self.s.row('activities',activity);signal=self.s.row('perception_signals',row['trigger_event_id'])
        if signal['source_actor_id']!=self.s.config()['controller']:return None
        raw=self.s.read_artifact(signal['artifact_id']);name=self.proposed(raw.get('text',''))
        if not name:return None
        anchor=self.anchor()
        # An explicit manual identity setting made later supersedes old chat names.
        if signal['received_at']<anchor['recorded_at']:return None
        return self.s.event('identity.name_selected',payload={'name':name,'actor':self.s.config()['controller'],'source_signal':signal['id'],
            'anchor':anchor['id'],'meaning':'explicit-controller-preferred-name; not a world belief or personality update'},
            source='controller-name',key=anchor['id']+':'+signal['id'],activity=activity,lane='control')
    def adopt_existing(self):
        """Explicit CLI migration: preserve a prior direct naming request, not guesses."""
        anchor=self.anchor();count=0
        rows=self.s.db.execute("SELECT a.id FROM activities a JOIN context_snapshots c ON c.activity_id=a.id AND c.instance_id=a.instance_id JOIN perception_signals p ON p.id=a.trigger_event_id AND p.instance_id=a.instance_id WHERE a.instance_id=? AND p.source_actor_id=? AND p.received_at>=? AND json_extract(c.attributes_json,'$.chat') IS NOT NULL ORDER BY a.rowid LIMIT 1000",(self.s.instance_id,self.s.config()['controller'],anchor['recorded_at'])).fetchall()
        with self.s.tx():
            for row in rows:
                before=self.s.db.total_changes;self.observe(row[0]);count+=int(self.s.db.total_changes>before)
        return {'name':self.current()['name'],'new_records':count}


def context(store,activity,payload):
    """Small authoritative facts, never a dump of private config or credentials."""
    from digital_life.application.runtime.settings import for_activity
    from digital_life.application.runtime.scheduling import Budget
    cfg=store.config();flags={}
    kinds={'cognition':'cognition.configured','personality_growth':'personality_growth.configured',
           'habit_candidates':'habit_candidates.configured','habit_learning':'habit_learning.configured',
           'memory_quality':'memory_quality.configured','people_relations':'people_relations.configured',
           'goal_regulation':'goal_regulation.configured','behavior_policy':'behavior_policy.configured',
           'self_maintenance':'maintenance.configured','self_feedback':'self_feedback.configured',
           'autonomy_agenda':'agenda.configured','exploration':'exploration.configured'}
    for key,kind in kinds.items():
        row=store.db.execute('SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type=? ORDER BY event_seq DESC LIMIT 1',(store.instance_id,kind)).fetchone()
        value=store.read_artifact(row[1]) if row else {}
        flags[key]={'enabled':bool(value.get('enabled',False)),'source_event':row[0] if row else None}
        if key=='exploration' and value.get('expires_at'):
            from digital_life.domain.contracts import utc
            if value['expires_at']<=utc():flags[key]['enabled']=False
    options=for_activity(store,activity);remaining=Budget(store).remaining(activity)
    project=payload.get('project_access')
    return {'source':'host-verified-runtime-configuration-v1','name':Names(store).current(),
      'model':{'backend':cfg['model'].get('backend'),'route':payload['model'],'context_mode':'fresh_request',
               'continuation_used':False,'history_owner':'本地系统显式选取历史和记忆，不依赖供应商续聊',
               'mechanism':'每次独立Codex进程，未使用resume或旧会话ID' if cfg['model'].get('backend')=='codex_cli' else '本项目独立请求入口'},
      'features':flags,'budget':{'mode':remaining.get('mode','limited'),'description':'不限制本地累计预算' if remaining.get('mode')=='unlimited' else '本地累计预算已限制','remaining':remaining,
                'single_request_attempt_limit':options['request_attempts'],'attempt_meaning':'最多尝试次数包含首次，不是额外重试次数','single_request_timeout_seconds':cfg['model'].get('timeout',120)},
      'settings_page':{'available':True,'navigation':'实例配置 → 任务预算','root_account_required':True,'role_meaning':'root是最高权限账户，不是实例类型','save_requires_stopped':True,'save_and_apply_available':True,'lifecycle':'root可通过实例配置页面或CLI启动、停止、重启；禁止唤醒锁不会自动移除'},
      'project':{'available':project is not None,'meaning':'授权项目工作副本；未核对部署摘要前，不把它自动当成当前运行版本','entry_files':{
          'activity_flow':'digital_life/application/runtime/engine.py',
          'permissions':'digital_life/application/accounts/authorization.py',
          'memory':'digital_life/application/services/memory.py',
          'model_adapter':'digital_life/infrastructure/llm/codex_cli.py',
          'settings':'digital_life/application/monitoring/instance_settings.py',
          'panel':'digital_life/web/app.js'} if project else {}},
      'meaning':'当前宿主记录，不是模型自评；人格成长关闭不等于没有人格参数，开启不等于自动完成成长。'}


INSTRUCTIONS=(
 ' 公开回复用自然中文解释，不用unlimited等字段名代替“累计预算不限”；root表示最高权限账户。'
 ' self_knowledge是宿主提供的当前运行说明，回答自身配置时直接使用明确的开/关与模式，不把关闭说成未知。'
 ' 被问是否能查、设置或检查本地项目时，先理解当前对话范围；无需泛泛扩展到服务商计费。'
 ' 用户明确要求检查源码且有project_access时，先从self_knowledge.project.entry_files直接读取相关实现；不要从根目录重复列举。'
 ' 只完成本次目标所需的核对，得到证据后收束成直接结论、已确认问题和未确认项；避免每轮只有“接下来我会”。'
 ' 已知配置可直接回答；缺少但可通过已授权只读工具核对的信息，继续查询而不只说不知道。'
 ' 自身运行设置是宿主状态，不作为cognition.claims中的新用户报告重复记录。'
 ' 配置页的存在和可调整范围已在self_knowledge说明；运行中可编辑并使用保存并应用，由后台停止、保存和启动；直接保存仍要求停止。'
 ' 不把“LLM不知道”解释成宿主没实现，也不把规划或读取几行源码说成完整审查。'
)
