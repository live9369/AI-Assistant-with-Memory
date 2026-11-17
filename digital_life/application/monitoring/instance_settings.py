"""Root-owned, versioned native settings. Saving never starts or calls a model."""
import json
import math
from digital_life.domain.contracts import ContractError, Conflict, Forbidden, dumps, sha, utc
from digital_life.infrastructure.processes.dispatch_gate import coordinated
from digital_life.application.runtime.settings import current

TRAITS = {'openness':'开放性','conscientiousness':'尽责性','extraversion':'外向性',
          'agreeableness':'宜人性','emotional_stability':'情绪稳定性'}
VALUE_NAMES = {'accuracy':'准确','care':'体谅','continuity':'连续性','exploration':'探索'}
TOOL_NAMES = {'read_file':'读取工作区文件','write_note':'写入工作区笔记','list_files':'列出工作区文件',
              'wait':'回复或等待','ask':'询问澄清','project_list':'查看项目目录','project_read':'读取项目文件',
              'project_search':'搜索项目','project_write':'写入项目文件','project_edit':'编辑项目文件',
              'project_check':'运行项目检查','project_version_status':'查看版本状态','project_version_log':'查看版本记录',
              'project_version_save':'保存源码版本','project_version_restore':'恢复源码文件'}
FEATURE_NAMES = {'proposed':'模型提出','cost':'成本','habit':'习惯','memory.coverage':'记忆覆盖',
 'cognition.uncertainty':'认知不确定性','relationship.reliability':'关系可靠性','motivation.intensity':'动机强度',
 'state.load':'运行负载','context.chat':'聊天情境','context.task_loop':'连续任务','context.internal':'内部活动'}


def field(key, label, kind='bool', **kwargs):
    return dict(key=key, label=label, type=kind, **kwargs)


class InstanceSettings:
    def __init__(self, store):
        self.s=store;self.actor=store.config()['controller']

    def native(self):
        from digital_life.application.learning.runtime import legacy_protection_present
        if legacy_protection_present(self.s):
            raise Forbidden('受保护实例暂不支持原生配置页，请使用对应的受保护配置流程。')

    def control(self):
        from digital_life.application.monitoring.management import Management
        return Management(self.s).control()

    def _event_config(self, kind):
        row=self.s.db.execute('SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type=? ORDER BY event_seq DESC LIMIT 1',(self.s.instance_id,kind)).fetchone()
        return (self.s.read_artifact(row[1]),row[0]) if row else ({},None)

    def sections(self):
        self.native()
        from digital_life.application.services.personality import Personality
        from digital_life.application.behavior.behavior_policy import BehaviorPolicy, TOOLS
        from digital_life.application.autonomy.exploration import Exploration
        from digital_life.application.lifecycle.project_access import ProjectAccess
        from digital_life.application.lifecycle.process_checkpoints import ProcessCheckpoints
        from digital_life.domain.project_files import NAMES
        from digital_life.application.chat.self_knowledge import Names
        cfg=self.s.config();effective_name=Names(self.s).current()['name'];version=self.s.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()[0]
        settings=current(self.s);result=[]
        def add(key,title,description,values,fields,source=None,group='功能开关'):
            result.append(dict(id=key,title=title,description=description,values=values,fields=fields,
                               revision=sha(dumps([key,values,source])),group=group,effect='停止后保存；后续活动使用新设置，已有请求与预算不改写。'))
        add('identity','身份与交流','修改称呼与交流偏好，不更换实例身份、账户或历史。',
            {'name':effective_name,'reply_guidance':cfg.get('reply_guidance','')},
            [field('name','实例称呼','text',max_length=80),field('reply_guidance','补充交流偏好','textarea',max_length=2000,hint='例如先直接回答、少用术语。不会赋予权限或取代系统规则。')],version,'基本设置')
        personality=Personality(self.s).current()
        add('personality','人格参数','人工设定五项稳定倾向，不代表测评结果；人格成长开关独立控制。',
            {r['name']:r['central_value'] for r in personality['traits']},
            [field(k,v,'number',min=-1,max=1,step=.05) for k,v in TRAITS.items()],personality['profile']['id'],'基本设置')
        profile=max(self.s.rows('value_profiles'),key=lambda r:r['version'])
        rows=self.s.db.execute('SELECT w.dimension_id,w.weight,d.definition FROM value_weights w JOIN value_dimensions d ON d.id=w.dimension_id WHERE w.profile_id=?',(profile['id'],)).fetchall()
        add('values','价值权重','相对权重保存时归一化，总和必须大于零；不代表道德优劣。',
            {r['dimension_id']:r['weight'] for r in rows},[field(r['dimension_id'],VALUE_NAMES.get(r['definition'],r['definition']),'number',min=0,max=100,step=.05) for r in rows],profile['id'],'基本设置')
        budget=[('tokens','每项活动总 token 额度',1024,1048576),('tool_calls','每项活动工具调用次数',0,256),
                ('attempts','每项活动总尝试次数',1,512),('duration_seconds','每项活动最长时长（秒）',30,86400),
                ('thought_tokens','每次思考预留 token',1024,131072),('request_attempts','单请求最多尝试次数',1,10),('request_seconds','单请求有效时长（秒）',1,3600)]
        add('budget','任务预算','默认不限制本地活动累计预算；可按需开启限制。仍记录用量，不会提高服务商额度。只影响新活动。',
            {'budget_enabled':settings['budget_enabled'],**{k:settings[k] for k,*_ in budget}},[field('budget_enabled','限制本地活动累计预算',hint='默认关闭：不限制累计token、工具次数、总尝试数和整体时长。下方累计额度仅在开启后生效；单请求超时与重试边界仍保留。')]+[field(k,l,'integer',min=lo,max=hi,step=1) for k,l,lo,hi in budget],version,'基本设置')
        memory=[('history_messages','近期消息条数（含双方）',0,100),('history_bytes','近期交流材料上限（字节）',256,262144),
                ('recall_items','普通对话最多召回条数',1,50),('exploration_recall_items','探索最多召回条数',1,50)]
        add('context','对话与记忆','控制显式提供的近期交流与召回数量；不是模型 token 窗口，也不会扩大读取权限。',
            {k:settings[k] for k,*_ in memory},[field(k,l,'integer',min=lo,max=hi,step=1) for k,l,lo,hi in memory],version,'基本设置')
        add('influence','来源影响权重','root权重必须严格高于其他来源；影响权重不等于事实可信度或权限。',
            {k:settings[k] for k in ('root_weight','other_weight')},[field('root_weight','root来源权重','number',min=.01,max=100,step=.1),field('other_weight','其他来源权重','number',min=.01,max=100,step=.1)],version,'基本设置')
        modules=[('cognition','认知候选记录','保存带来源的认知候选，不自动确认为事实。','cognition.configured'),
                 ('personality_growth','人格成长','开启后记录成长机会；仍需既有人工标注、评估和提交，不会立即自动改人格。','personality_growth.configured'),
                 ('habit_candidates','习惯候选收集','重复经历形成候选，确认后才生效，不自动确认。','habit_candidates.configured'),
                 ('habit_learning','已审阅习惯学习','使用既有受控习惯机制，不跳过候选确认与反馈规则。','habit_learning.configured'),
                 ('people_relations','人物与关系','启用有来源的人物关系认知，不改变账户权限。','people_relations.configured'),
                 ('memory_quality','记忆质量','启用增强检索与来源维护，不自动删除记忆。','memory_quality.configured'),
                 ('autonomy_agenda','承诺与自主安排','启用已有承诺与议程流程；保存不创建任何承诺。','agenda.configured'),
                 ('self_feedback','自反馈记录','影子记录，不把自评当作收益，也不直接改变选择。','self_feedback.configured'),
                 ('experience_measurement','受控经验测量','仅启用测量能力；不运行评测、不调用模型。','learning.measurement_configured')]
        for key,title,description,event in modules:
            data,ref=self._event_config(event)
            add(key,title,description,{'enabled':bool(data.get('enabled',False))},[field('enabled','启用'+title)],ref)
        data,ref=self._event_config('goal_regulation.configured')
        add('goal_regulation','目标与动机','按目标与当前资源安排工作。',{'enabled':bool(data.get('enabled',False)),'min_disk_bytes':data.get('min_disk_bytes',67108864)},
            [field('enabled','启用目标调节'),field('min_disk_bytes','最低保留磁盘空间（字节）','integer',min=0,max=1099511627776,step=1)],ref)
        behavior=BehaviorPolicy(self.s);data=behavior.config();values={'enabled':data['enabled'],'temperature':data['temperature']}
        fields=[field('enabled','启用行为概率'),field('temperature','选择温度','number',min=.05,max=5,step=.05)]
        for tool in TOOLS:
            values['bias:'+tool]=data.get('biases',{}).get(tool,0)
            fields.append(field('bias:'+tool,TOOL_NAMES[tool]+' · 基础偏好','number',min=-20,max=20,step=.1,advanced='行为基础偏好'))
            for dimension in behavior.dimensions():
                key='weight:'+tool+':'+dimension;values[key]=data.get('weights',{}).get(tool,{}).get(dimension,0)
                label=FEATURE_NAMES.get(dimension,TRAITS.get(dimension.removeprefix('personality.'),VALUE_NAMES.get(dimension.removeprefix('value.'),dimension)))
                fields.append(field(key,label,'number',min=-20,max=20,step=.1,advanced=TOOL_NAMES[tool]+' · 特征系数'))
        add('behavior_policy','行为概率','先过滤不允许的行为，再按分数选择；高级系数不改变工具权限。',values,fields,data.get('event_id'))
        data=Exploration(self.s).config()
        values=dict(enabled=bool(data.get('enabled',False)),mode=data.get('mode','legacy'),interval_seconds=data.get('interval_seconds',300),max_activities=data.get('max_activities',12),max_rounds=data.get('max_rounds',3),duration_seconds=data.get('duration_seconds') or 0)
        add('exploration','自主探索','保存只改变探索配置；不会启动或唤醒实例。0秒表示不设额外到期时间，仍受活动数和预算限制。',values,
            [field('enabled','启用自主探索'),field('mode','探索模式','choice',choices=[['legacy','基础模式'],['continuous','持续方向探索']]),
             field('interval_seconds','活动间隔（秒）','integer',min=60,max=86400,step=1),field('max_activities','最多探索活动数','integer',min=1,max=180,step=1),
             field('max_rounds','每项探索最多轮数','integer',min=2,max=3,step=1),field('duration_seconds','配置有效时长（秒；0为不设额外期限）','integer',min=0,max=10800,step=1)],data.get('generation'),'自主与维护')
        data,ref=self._event_config('maintenance.configured')
        add('maintenance','自我维护','只使用已有的受限修复方式；源码部署仍由CLI处理。',
            dict(enabled=bool(data.get('enabled',False)),auto_repair=bool(data.get('auto_repair',False)),max_repairs=data.get('max_repairs') or 3),
            [field('enabled','启用自我维护'),field('auto_repair','允许自动执行受限修复'),field('max_repairs','本配置最多修复次数','integer',min=1,max=3,step=1)],ref,'自主与维护')
        data=ProjectAccess(self.s).config()
        add('project_access','项目目录权限','额外排除不会取消系统强制排除。自动审批仅适用于已授权目录与工具，不代表允许部署。',
            dict(enabled=bool(data.get('enabled',False)),root=data.get('root',''),auto_approve=bool(data.get('auto_approve',False)),exclude=data.get('exclude',[]),tools=data.get('tools',list(NAMES))),
            [field('enabled','允许访问指定项目目录'),field('root','项目绝对路径','text',max_length=2000),field('auto_approve','自动审批范围内的项目操作'),
             field('exclude','额外排除路径','lines',hint='每行一个相对路径；系统强制排除即使移除仍会生效。'),field('tools','允许的工具','multi',choices=[[n,TOOL_NAMES.get(n,n)] for n in NAMES])],data.get('generation'),'自主与维护')
        # Read only: visiting the page must not create the control database.
        file=self.s.root/'process-manager.json'
        if file.is_symlink():raise Forbidden('invalid process configuration path')
        data=json.loads(file.read_text()) if file.exists() else {}
        add('recovery','版本恢复设置','仅配置恢复机制；不会部署、制作检查点、回退或启动进程。独立思考验收仅在后续部署时运行。',
            dict(enabled=bool(data.get('enabled',False)),verify_thought=bool(data.get('verify_thought',False)),thought_timeout=data.get('thought_timeout',180)),
            [field('enabled','启用应用检查点恢复'),field('verify_thought','新版本必须通过一次独立思考'),field('thought_timeout','部署思考验收超时（秒）','integer',min=1,max=600,step=1)],data,'自主与维护')
        return result

    def read(self):
        control=self.control();editable=bool(control['user_stopped']) and not control['active_process_run_id']
        return {'instance_id':self.s.instance_id,'can_edit':editable,'can_apply':bool(control['prepared']),'edit_reason':None if editable else '实例运行中，可修改后选择保存并应用，由后台完成重启。',
                'sections':self.sections(),'related_pages':[{'view':'model','label':'模型与授权'},{'view':'accounts','label':'账户管理'},{'view':'memories','label':'记忆域'},{'view':'activities','label':'活动与审批'}],
                'protected_rules':['每次独立模型调用','来源与权限校验','用户停止保护','已有活动预算不追加','部署与进程控制仅限root明确授权']}

    def _validate(self, section, values):
        if not isinstance(values,dict) or set(values)!=set(section['values']):raise ContractError('字段不完整或包含未支持的配置项。')
        for f in section['fields']:
            value=values[f['key']];kind=f['type'];label=f['label']
            if kind=='bool':valid=type(value)is bool
            elif kind in ('integer','number'):
                valid=type(value) in ((int,) if kind=='integer' else (int,float)) and f['min']<=value<=f['max'] and math.isfinite(value)
            elif kind in ('text','textarea'):valid=isinstance(value,str) and len(value)<=f.get('max_length',2000) and '\x00' not in value
            elif kind in ('multi','lines'):
                valid=isinstance(value,list) and len(value)<=100 and all(isinstance(v,str) and 0<len(v)<=1000 for v in value)
                if valid:valid=len(set(value))==len(value)
                if valid and kind=='multi':valid=set(value)<=set(x[0] for x in f['choices'])
            else:valid=value in [v[0] for v in f['choices']] if isinstance(value,str) else False
            if not valid:raise ContractError(label+'：值、类型或范围不正确。')
        key=section['id']
        if key=='identity' and not values['name'].strip():raise ContractError('实例称呼不能为空。')
        if key=='values' and sum(values.values())<=0:raise ContractError('价值权重总和必须大于零。')
        if key=='influence' and values['root_weight']<=values['other_weight']:raise ContractError('root来源权重必须高于其他来源。')
        if key=='budget' and values['budget_enabled']:
            if values['thought_tokens']>values['tokens'] or values['request_attempts']>values['attempts']:raise ContractError('单请求额度不能超过活动总额度。')
            if values['request_seconds']>values['duration_seconds']:raise ContractError('单请求期限不能超过活动总时长。')
        if key=='exploration':
            d=values['duration_seconds']
            if d and d<60:raise ContractError('探索有效时长为0或至少60秒。')
            if not d and values['max_activities']>100:raise ContractError('未设置有效时长时，探索活动数最多100。')

    def _config(self, **updates):
        cfg=dict(self.s.config(),**updates);art=self.s.artifact(cfg)
        return self.s.insert('configuration_versions',version='instance-settings-'+str(len(self.s.rows('configuration_versions'))),artifact_ref=art,hash=self.s.row('artifacts',art)['hash'],compatibility={'schema_min':2,'schema_max':3})

    def _evidence(self, section, values, reason):
        # Two real control records, explicitly NOT independent empirical samples.
        proposal=self.s.event('settings.manual_proposal',payload={'section':section,'values':values,'actor':self.actor,'kind':'human-configuration-not-observation'},lane='control')
        approval=self.s.event('settings.manual_confirmation',payload={'proposal':proposal,'reason':reason,'actor':self.actor,'kind':'explicit-human-confirmation-not-measurement'},lane='control')
        return [self.s.evidence(object_id=proposal,method='controller-configuration-proposal'),self.s.evidence(object_id=approval,method='controller-configuration-confirmation')]

    @coordinated
    def save(self, key, body):
        self.native()
        if not isinstance(body,dict) or set(body)!={'values','expected_revision','reason','confirmed'}:raise ContractError('保存需要完整字段、版本、修改原因和明确确认。')
        reason=body['reason']
        if body['confirmed'] is not True or not isinstance(reason,str) or not reason.strip() or len(reason)>2000:raise ContractError('请填写修改原因并确认人工配置。')
        control=self.control()
        if not control['prepared'] or not control['user_stopped'] or control['active_process_run_id']:raise Conflict('请先停止实例并等待运行器退出，或使用保存并应用。')
        # BEGIN IMMEDIATE serializes configuration changes from other connections.
        with self.s.tx():
            section=next((s for s in self.sections() if s['id']==key),None)
            if section is None:raise ContractError('未知配置分组。')
            if body['expected_revision']!=section['revision']:raise Conflict('配置已被修改，请重新读取后再保存。')
            values=body['values'];self._validate(section,values)
            if key=='recovery':
                # Its existing atomic file + control DB journal is the authoritative
                # write path; no lifecycle command is exposed here.
                from digital_life.application.lifecycle.control_plane import Control
                from digital_life.application.lifecycle.process_checkpoints import ProcessCheckpoints
                from digital_life.infrastructure.processes.locks import exclusive
                c=Control(self.s.root,self.s.instance_id)
                try:
                    with exclusive(self.s.root,'deployment.lock'):
                        ProcessCheckpoints(c).configure(values['enabled'],self.actor,verify_thought=values['verify_thought'],thought_timeout=values['thought_timeout'])
                finally:c.close()
            else:
                self._apply(key,values,reason)
            self.s.event('settings.changed',payload={'section':key,'before':section['values'],'after':values,'actor':self.actor,'reason':reason,'manual':True,'inference_executed':False},lane='control')
        updated=next(s for s in self.sections() if s['id']==key)
        return {'section':updated,'saved':True,'runtime_started':False,'inference_executed':False}

    def _apply(self, key, values, reason):
        if key in ('budget','context','influence'):
            self._config(runtime_settings=dict(current(self.s),**values));return
        if key=='identity':
            old=max(self.s.rows('identity_anchors'),key=lambda r:r['version'])
            name=values['name'].strip();anchor=dict(json.loads(old['anchor_data']),name=name)
            self._config(name=name,reply_guidance=values['reply_guidance'])
            self.s.insert('identity_anchors',version=old['version']+1,anchor_data=anchor,previous_id=old['id'],authority_ref=self.actor,anchor_object_id=old['anchor_object_id'])
            return
        if key in ('personality','values'):
            refs=self._evidence(key,values,reason)
            if key=='personality':
                from digital_life.application.services.personality import Personality
                service=Personality(self.s);old=service.current()
                service.replace(values,refs,self.actor,expected_profile=old['profile']['id'])
            else:
                from digital_life.application.services.values import Values
                Values(self.s).replace(values,refs,self.actor)
            return
        from importlib import import_module
        specs={
          'cognition':('cognition.cognitive_updates','CognitiveUpdates'),
          'personality_growth':('behavior.personality_growth','PersonalityGrowth'),
          'habit_candidates':('behavior.habit_candidates','HabitCandidates'),
          'habit_learning':('behavior.habit_learning','HabitLearning'),
          'people_relations':('behavior.people_relations','PeopleRelations'),
          'memory_quality':('memory.memory_quality','MemoryQuality'),
          'autonomy_agenda':('autonomy.autonomy_agenda','AutonomyAgenda'),
          'self_feedback':('learning.self_feedback','SelfFeedback'),
          'experience_measurement':('learning.experience_measurement','ExperienceMeasurement'),
          'goal_regulation':('behavior.goal_regulation','GoalRegulation'),
          'maintenance':('lifecycle.self_maintenance','SelfMaintenance'),
          'behavior_policy':('behavior.behavior_policy','BehaviorPolicy'),
          'exploration':('autonomy.exploration','Exploration'),
          'project_access':('lifecycle.project_access','ProjectAccess')}
        module,name=specs[key];service=getattr(import_module('digital_life.application.'+module),name)(self.s)
        if key=='self_feedback':service.configure(self.actor,values['enabled'])
        elif key=='goal_regulation':service.configure(values['enabled'],self.actor,values['min_disk_bytes'])
        elif key=='maintenance':service.configure(values['enabled'],self.actor,values['auto_repair'],values['max_repairs'])
        elif key=='behavior_policy':
            parameters={'biases':{},'weights':{}}
            for k,v in values.items():
                if k.startswith('bias:'):parameters['biases'][k.split(':')[1]]=v
                elif k.startswith('weight:'):
                    _,tool,dimension=k.split(':',2);parameters['weights'].setdefault(tool,{})[dimension]=v
            service.configure(values['enabled'],self.actor,values['temperature'],parameters)
        elif key=='exploration':
            service.configure(self.actor,**dict(values,duration_seconds=values['duration_seconds'] or None))
        elif key=='project_access':
            service.configure(values['root'],self.actor,enabled=values['enabled'],auto_approve=values['auto_approve'],exclude=values['exclude'],tools=values['tools'])
        else:service.configure(values['enabled'],self.actor)
