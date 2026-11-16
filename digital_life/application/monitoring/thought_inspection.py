"""Read-only historical thought snapshots, not a reconstruction of hidden prompts."""
import os
from digital_life.application.monitoring.management import ManagementError,SECRET_KEY
from digital_life.domain.contracts import ContractError

FEATURES={
 '认知与感知':['task','observation','instructions','conversation_context'],
 '人格':['personality','personality_growth'],'价值取向':['values'],'选中记忆':['selected_memories','memory_quality'],
 '行为概率':['behavior_policy'],'习惯':['habit_suggestions','habit_learning'],'内部状态':['states'],'可用行为':['tools'],
 '动机':['motivation','goal_regulation'],'关系':['relationships'],'学习反馈':['learning_feedback'],
 '健康':['health','self_maintenance'],'身份':['identity'],'探索':['exploration','autonomy_agenda'],'结构化认知':['cognition_snapshot','cognition_sources'],'目标闭环':['task_loop'],'认知影响权重':['cognitive_influence']}
class ThoughtInspection:
 def __init__(self,store):self.s=store
 def clean(self,value):
  secrets=[]
  token=self.s.root/'controller.token'
  if token.is_file() and not token.is_symlink():secrets.append(token.read_text().strip())
  names={'OPENAI_API_KEY','DIGITAL_LIFE_LLM_API_KEY'}
  variable=self.s.config()['model'].get('api_key_env')
  if isinstance(variable,str):names.add(variable)
  secrets.extend(os.environ.get(name,'') for name in names)
  def visit(item):
   if isinstance(item,dict):return {k:'[已隐藏凭据]' if SECRET_KEY.search(str(k)) else visit(v) for k,v in item.items()}
   if isinstance(item,list):return [visit(v) for v in item]
   if isinstance(item,str):
    for secret in secrets:
     if secret:item=item.replace(secret,'[已隐藏凭据]')
   return item
  return visit(value)
 def artifact(self,ref,expected=None):
  from digital_life.application.learning.runtime import strict_legacy_boundary
  strict_legacy_boundary(self.s,'legacy_thought_inspection')
  if not ref:return {'available':False,'reason':'未保存该内容'}
  try:
   row=self.s.row('artifacts',ref)
   if expected and row['hash']!=expected:raise ContractError('snapshot hash mismatch')
   value=self.s.read_artifact(ref)
   if isinstance(value,dict) and 'redacted_by' in value:return {'available':False,'reason':'内容已按隐私请求擦除'}
   return {'available':True,'artifact_id':ref,'hash':row['hash'],'value':self.clean(value),'credential_redaction':True,'truncated':False}
  except (OSError,ValueError,TypeError,ContractError):return {'available':False,'reason':'内容缺失、已擦除或完整性校验未通过'}
 def list(self,activity):
  if not self.s.db.execute('SELECT 1 FROM activities WHERE id=? AND instance_id=?',(activity,self.s.instance_id)).fetchone():raise ManagementError(404,'NOT_FOUND','找不到活动。')
  rows=self.s.db.execute('SELECT id,state,purpose,recorded_at,model_config_id,accepted_result_id FROM thought_requests WHERE instance_id=? AND activity_id=? ORDER BY rowid',(self.s.instance_id,activity))
  return {'items':[dict(r) for r in rows]}
 def detail(self,ref):
  from digital_life.application.learning.runtime import strict_legacy_boundary
  strict_legacy_boundary(self.s,'legacy_thought_inspection')
  row=self.s.db.execute('SELECT * FROM thought_requests WHERE id=? AND instance_id=?',(ref,self.s.instance_id)).fetchone()
  if row is None:raise ManagementError(404,'NOT_FOUND','找不到本实例的思考请求。')
  request=dict(row);snapshot=self.artifact(row['request_artifact_id'],row['request_hash']);value=snapshot.get('value')
  features=[]
  for name,keys in FEATURES.items():
   items=[]
   for key in keys:
    present=isinstance(value,dict) and key in value
    state='unavailable' if not snapshot['available'] else 'provided' if present and value[key] not in (None,{},[],"") else 'empty' if present else 'not_in_request'
    items.append({'field':key,'state':state,'value':value[key] if present else None})
   features.append({'name':name,'items':items})
  attempts=[dict(r) for r in self.s.db.execute('SELECT * FROM thought_attempts WHERE instance_id=? AND request_id=? ORDER BY attempt_no',(self.s.instance_id,ref))]
  results=[]
  for r in self.s.db.execute('SELECT * FROM thought_results WHERE instance_id=? AND request_id=? ORDER BY rowid',(self.s.instance_id,ref)):
   item=dict(r);item['response']=self.artifact(r['response_artifact_id'],r['response_hash']);item['parsed_output']=self.artifact(r['parsed_artifact_id']);results.append(item)
  usage=[]
  for e in self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='model.usage' ORDER BY rowid",(self.s.instance_id,row['activity_id'])):
   data=self.artifact(e[0]);v=data.get('value')
   if isinstance(v,dict) and v.get('request')==ref:usage.append(v)
  config=self.s.db.execute('SELECT artifact_ref FROM configuration_versions WHERE id=? AND instance_id=?',(row['model_config_id'],self.s.instance_id)).fetchone()
  cfg=self.artifact(config[0]) if config else {'available':False}
  model=cfg.get('value',{}).get('model') if isinstance(cfg.get('value'),dict) else None
  behavior=[]
  for event in self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='behavior_policy.selected' ORDER BY event_seq",(self.s.instance_id,row['activity_id'])):
   behavior_snapshot=self.artifact(event[0]);data=behavior_snapshot.get('value')
   if isinstance(data,dict) and data.get('request')==ref:behavior.append(behavior_snapshot)
  return self.clean({'behavior_decisions':behavior,'request':request,'input':snapshot,'features':features,'attempts':attempts,'results':results,'usage':usage,'pinned_model_configuration':model,
   'scope':'项目持久化的输入输出；凭据脱敏，不截断。非云端最终完整上下文，不包含隐藏推理。','raw_provider_response_recorded':False,'read_only':True})
