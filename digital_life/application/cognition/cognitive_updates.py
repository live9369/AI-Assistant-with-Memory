"""Opt-in structured cognition. Model statements remain held interpretations."""
import json
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,dumps,utc
from digital_life.application.services.cognition import Cognition
from digital_life.application.services.goals import Goals
from digital_life.infrastructure.processes.dispatch_gate import coordinated

CORRECTION_INSTRUCTIONS = (' 结合cognition_provenance区分候选入库时间、原始信息接收时间与记忆写入时间；这些都不自动等于事件发生时间。'
 '重复整理旧话或模型回复不构成新的独立证据。仅在对方明确指向同一对象并表示更新或更正时，将新说法转述为最新报告，保留旧说法和来源。'
 '无明确更正、对象或时间不清时保留分歧并澄清，不凭时间新旧断言真伪；held候选仍未确认。')

from digital_life.application.accounts import account_scope as scope

class CognitiveUpdates:
 def __init__(self,store):self.s=store
 def generation(self):
  row=self.s.db.execute("SELECT id FROM runtime_events WHERE instance_id=? AND event_type='cognition.configured' ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,)).fetchone()
  return row[0] if row else None
 def enabled(self):
  row=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type='cognition.configured' ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,)).fetchone()
  return bool(row and self.s.read_artifact(row[0])['enabled'])
 @coordinated
 def configure(self,enabled,actor):
  if actor!=self.s.config()['controller'] or type(enabled) is not bool:raise Forbidden('controller and boolean required')
  from digital_life.application.lifecycle.control_plane import Control
  c=Control(self.s.root,self.s.instance_id)
  try:
   state=c.state()
   if not state['user_stopped'] or state['active_process_run_id']:raise Conflict('stop before cognition configuration')
  finally:c.close()
  with self.s.tx():self.s.event('cognition.configured',payload={'enabled':enabled,'actor':actor},lane='control')
 def source_text(self,value):
  if isinstance(value,dict):
   if isinstance(value.get('text'),str):return value['text']
   if isinstance(value.get('evidence'),dict) and isinstance(value['evidence'].get('text'),str):return value['evidence']['text']
  return dumps(value)
 def sources(self,activity,payload):
  signal=self.s.row('activities',activity)['trigger_event_id'];source={signal:payload['observation']['text']}
  for m in payload['selected_memories']:source[m['revision_id']]=m['content']
  for observation in payload.get('task_loop',{}).get('observations',[]):
   if observation.get('receipt') and 'receipt_snapshot' in observation:source[observation['receipt']]=self.source_text(observation['receipt_snapshot'])
  return source
 def learning_sources(self,activity,payload):
  sources=self.sources(activity,payload)
  for item in payload.get('exploration',{}).get('work_history',{}).get('items',[]):sources[item['result']]=item['explanation']
  for item in payload.get('exploration',{}).get('observations',[]):
   if item.get('receipt') and item.get('receipt_snapshot'):sources[item['receipt']]=self.source_text(item['receipt_snapshot'])
  return sources
 def source_value(self,ref):
  if not scope.source_allowed(self.s,ref):raise Forbidden('source not visible to account')
  from digital_life.application.cognition.cognition_memory import source_memories
  for parent in source_memories(self.s,ref):
   if self.s.row('memory_items',parent)['state']!='active' or not scope.can_recall(self.s,parent):raise Forbidden('source memory dependency unavailable')
  memory=self.s.db.execute('SELECT memory_id,content FROM memory_revisions WHERE id=? AND instance_id=?',(ref,self.s.instance_id)).fetchone()
  if memory:
   item=self.s.row('memory_items',memory['memory_id'])
   if item['state']!='active' or item['current_revision_id']!=ref or not scope.can_recall(self.s,item['id']):raise Forbidden('memory source unavailable')
   return memory['content']
  signal=self.s.db.execute('SELECT artifact_id FROM perception_signals WHERE id=? AND instance_id=?',(ref,self.s.instance_id)).fetchone()
  result=self.s.db.execute('SELECT acceptance,response_artifact_id FROM thought_results WHERE id=? AND instance_id=?',(ref,self.s.instance_id)).fetchone()
  if result:
   if result['acceptance']!='accepted':raise Forbidden('model work is not accepted')
   value=self.s.read_artifact(result['response_artifact_id'])
   if not isinstance(value,dict) or 'redacted_by' in value:raise Forbidden('model work erased')
   return value['explanation']
  value=self.s.read_artifact(signal[0] if signal else ref)
  if not isinstance(value,dict) or 'redacted_by' in value:raise Forbidden('source erased')
  return self.source_text(value)
 def check(self,activity,payload,output):
  version=payload.get('output_schema_version')
  if version not in (3,6):
   if output['schema_version'] in (3,6):raise ContractError('unexpected cognition output')
   return
  if not self.enabled() or payload.get('cognition_configuration')!=self.generation():raise Forbidden('cognition disabled or superseded')
  if output['schema_version']!=version:raise ContractError('cognition output version differs')
  source=payload.get('learning_sources',{}) if version==6 else self.sources(activity,payload)
  claims=output['learning']['claims'] if version==6 else output['cognition']['claims']
  for claim in claims:
   ref=claim['source_ref']
   if ref not in source or claim['quote'] not in source[ref]:raise Forbidden('claim lacks exact quoted source')
   if self.source_value(ref)!=source[ref]:raise Forbidden('claim source changed')
 def readable_revision(self,revision):
  if not scope.source_allowed(self.s,revision):return False
  links=self.s.db.execute('SELECT e.origin_object_id,e.method FROM cognition_evidence_links l JOIN evidence_items e ON e.id=l.evidence_id AND e.instance_id=l.instance_id WHERE l.instance_id=? AND l.target_revision_id=?',(self.s.instance_id,revision)).fetchall()
  if not links:return False
  try:
   quote=json.loads(self.s.row('cognition_belief_revisions',revision)['content']).get('quote','')
   for link in links:
    value=self.source_value(link['origin_object_id'])
    if link['method']!='learning-source-guard' and quote not in value:return False
  except (OSError,ValueError,KeyError,ContractError):return False
  return True
 def snapshot(self):
  rows=self.s.db.execute('SELECT b.id,b.predicate,b.current_revision_id,r.content,r.acceptance_state FROM cognition_beliefs b JOIN cognition_belief_revisions r ON r.id=b.current_revision_id AND r.instance_id=b.instance_id WHERE b.instance_id=? ORDER BY b.rowid DESC',(self.s.instance_id,))
  values=[]
  for row in rows:
   if not self.readable_revision(row['current_revision_id']):continue
   if len(values)>=20:break
   value=dict(row);value['candidates']=[dict(r) for r in self.s.db.execute("SELECT id,content,acceptance_state FROM cognition_belief_revisions WHERE instance_id=? AND belief_id=? AND acceptance_state='held' ORDER BY revision_no DESC LIMIT 3",(self.s.instance_id,row['id'])) if self.readable_revision(r['id'])];values.append(value)
  return values
 def _source_metadata(self,ref,follow_memory=True):
  if not scope.source_allowed(self.s,ref):return {"type":"restricted"}
  row=self.s.db.execute('SELECT id,recorded_at,source_actor_id FROM perception_signals WHERE instance_id=? AND id=?',(self.s.instance_id,ref)).fetchone()
  if row:return {'type':'received-information','recorded_at':row['recorded_at'],'actor_ref':row['source_actor_id'],'time_basis':'information_received_not_event_occurrence'}
  row=self.s.db.execute('SELECT id,recorded_at,encoding_method FROM memory_revisions WHERE instance_id=? AND id=?',(self.s.instance_id,ref)).fetchone()
  if row:
   value={'type':'model-response-memory' if row['encoding_method']=='model-response-v1' else 'memory','recorded_at':row['recorded_at'],'encoding_method':row['encoding_method'],'time_basis':'memory_written_not_original_event'}
   if follow_memory:
    origins=[]
    for link in self.s.db.execute('SELECT e.origin_object_id,e.artifact_id,e.method,l.role FROM memory_source_links l JOIN evidence_items e ON e.id=l.evidence_id AND e.instance_id=l.instance_id WHERE l.instance_id=? AND l.memory_revision_id=? ORDER BY l.rowid',(self.s.instance_id,ref)):
     origin=link['origin_object_id'] or link['artifact_id']
     origins.append({'ref':origin,'method':link['method'],'role':link['role'],'metadata':self._source_metadata(origin,False) if origin else {'type':'unknown'}})
    value['direct_origins']=origins
   else:value['upstream_metadata']='not_expanded'
   return value
  for table,kind in (('thought_results','model-response'),('runtime_events','runtime-event'),('artifacts','artifact')):
   row=self.s.db.execute('SELECT recorded_at FROM '+table+' WHERE instance_id=? AND id=?',(self.s.instance_id,ref)).fetchone()
   if row:return {'type':kind,'recorded_at':row['recorded_at'],'time_basis':'record_written_not_external_event'}
  return {'type':'unknown','recorded_at':None,'time_basis':'unknown'}
 def provenance(self,snapshot):
  revisions={};sources={}
  for belief in snapshot:
   refs=[belief['current_revision_id']]+[candidate['id'] for candidate in belief.get('candidates',[])]
   for ref in refs:
    if ref in revisions:continue
    if not self.readable_revision(ref):raise Forbidden('cognition provenance source revoked or stale')
    revision=self.s.row('cognition_belief_revisions',ref)
    source_refs=list(dict.fromkeys((row['origin_object_id'] or row['artifact_id']) for row in self.s.db.execute('SELECT e.origin_object_id,e.artifact_id FROM cognition_evidence_links l JOIN evidence_items e ON e.id=l.evidence_id AND e.instance_id=l.instance_id WHERE l.instance_id=? AND l.target_revision_id=? ORDER BY l.rowid',(self.s.instance_id,ref)) if row['origin_object_id'] or row['artifact_id']))
    revisions[ref]={'recorded_at':revision['recorded_at'],'time_basis':'candidate_written_not_new_evidence','source_refs':source_refs}
    for source in source_refs:
     if source not in sources:sources[source]=self._source_metadata(source)
  return {'version':'cognition-provenance-v1','revisions':revisions,'sources':sources,'scope':'source chronology, not fact verification or entity merging'}
 def record(self,engine,activity,payload,output,request):
  if output['schema_version'] not in (3,6):return
  self.check(activity,payload,output)
  if self.s.db.execute("SELECT 1 FROM runtime_events WHERE instance_id=? AND event_type='cognition.output_recorded' AND source_event_id=?",(self.s.instance_id,request)).fetchone():return
  episode=self.s.db.execute('SELECT id FROM cognition_episodes WHERE activity_id=? ORDER BY rowid DESC LIMIT 1',(activity,)).fetchone()[0]
  with self.s.tx():
   refs=[];created=[];reused=[];suppressed=[]
   claims=output['learning']['claims'] if output['schema_version']==6 else output['cognition']['claims']
   for claim in claims:
    # A recalled representation is not a new independent observation. Preserve
    # the proposal in the raw output, without manufacturing a belief from it.
    if claim['kind']=='reported':
     from digital_life.application.cognition.cognition_memory import revision_for,ENCODING
     memory=self.s.db.execute('SELECT memory_id FROM memory_revisions WHERE instance_id=? AND id=? AND encoding_method=?',(self.s.instance_id,claim['source_ref'],ENCODING)).fetchone()
     origin=revision_for(self.s,memory[0]) if memory else None
     if origin and self.readable_revision(origin):
      suppressed.append({'claim_index':len(created)+len(reused)+len(suppressed),'source_ref':claim['source_ref'],'origin_revision':origin,'reason':'recalled-representation-not-new-observation'})
      continue
    # Label resolution is scoped and provisional, never a verified real-world identity merge.
    from digital_life.application.behavior.people_relations import PeopleRelations
    subject=PeopleRelations(self.s).subject(claim['subject'],activity)
    subject_label=(scope.current(self.s)['id']+':'+claim['subject']) if scope.active(self.s) else claim['subject']
    if scope.active(self.s) and not scope.privileged(self.s):subject=None
    if subject is None:
     found=self.s.db.execute("SELECT id FROM world_entities WHERE instance_id=? AND entity_type='claim-subject' AND canonical_name=?",(self.s.instance_id,subject_label)).fetchone()
     subject=found[0] if found else self.s.insert('world_entities',entity_type='claim-subject',canonical_name=subject_label,resolution_status='unresolved')
    old=self.s.db.execute('SELECT * FROM cognition_beliefs WHERE instance_id=? AND subject_ref=? AND predicate=?',(self.s.instance_id,subject,claim['predicate'])).fetchone()
    belief=old['id'] if old else self.s.insert('cognition_beliefs',subject_ref=subject,predicate=claim['predicate'],literal={'value':claim['value']},scope={'resolution':'provisional label'})
    n=self.s.db.execute('SELECT coalesce(max(revision_no),0)+1 FROM cognition_belief_revisions WHERE belief_id=?',(belief,)).fetchone()[0]
    influence={}
    if scope.active(self.s):
     from digital_life.application.accounts.cognitive_influence import source_weight,VERSION
     influence={'influence_weight':source_weight(self.s,claim['source_ref']),'influence_policy':VERSION}
    content={'value':claim['value'],'kind':claim['kind'],'quote':claim['quote']}
    if output['schema_version']==6:content.update(valid_at=claim['valid_at'],context_contains=claim['context_contains'])
    prior=None
    candidates=self.s.db.execute("SELECT * FROM cognition_belief_revisions WHERE instance_id=? AND belief_id=? AND json_extract(content,'$.value')=? AND json_extract(content,'$.kind')=? AND coalesce(json_extract(content,'$.valid_at'),'')=? AND coalesce(json_extract(content,'$.context_contains'),'')=? ORDER BY revision_no DESC",(self.s.instance_id,belief,claim['value'],claim['kind'],content.get('valid_at',''),content.get('context_contains','')))
    for candidate in candidates:
     prior_source=json.loads(candidate['uncertainty_json']).get('source_ref')
     if not prior_source:
      link=self.s.db.execute("SELECT e.origin_object_id FROM cognition_evidence_links l JOIN evidence_items e ON e.id=l.evidence_id WHERE l.target_revision_id=? AND e.method='quoted-source' LIMIT 1",(candidate['id'],)).fetchone()
      prior_source=link[0] if link else None
     if prior_source==claim['source_ref'] and self.readable_revision(candidate['id']):
      prior=candidate;break
    if prior:
     from digital_life.application.cognition.cognition_memory import publish
     publish(self.s,prior['id']);refs.append(prior['id']);reused.append(prior['id']);continue
    revision=self.s.insert('cognition_belief_revisions',belief_id=belief,revision_no=n,content=dumps(content),acceptance_state='held',uncertainty_json=dict(status='unverified-model-interpretation',source_ref=claim['source_ref'],**influence),method_version='cognition-v6' if output['schema_version']==6 else 'cognition-v3')
    scope.tag_object(self.s,revision,activity)
    evidence=self.s.evidence(object_id=claim['source_ref'],method='quoted-source')
    self.s.insert('cognition_evidence_links',target_revision_id=revision,evidence_id=evidence,stance='support',strength_method='quote-match-not-entailment',assessment=dict(not_verified=True,**influence))
    if not old:self.s.db.execute('UPDATE cognition_beliefs SET current_revision_id=? WHERE id=?',(revision,belief))
    if output['schema_version']==6:
     work=next((w for w in payload.get('exploration',{}).get('work_history',{}).get('items',[]) if w['result']==claim['source_ref']),{})
     for guard in work.get('citation_refs',[]):
      if guard==claim['source_ref']:continue
      if not self.s.db.execute('SELECT 1 FROM memory_revisions WHERE id=? AND instance_id=?',(guard,self.s.instance_id)).fetchone():continue
      self.source_value(guard)
      dependency=self.s.evidence(object_id=guard,method='learning-source-guard')
      self.s.insert('cognition_evidence_links',target_revision_id=revision,evidence_id=dependency,stance='support',strength_method='input-source-dependency',assessment={'not_independent_support':True})
    from digital_life.application.cognition.cognition_memory import publish
    publish(self.s,revision)
    refs.append(revision)
    created.append(revision)
   cognition=output.get('cognition',{'questions':[],'predictions':[],'plan':[]})
   for q in cognition['questions']:Cognition(self.s).hypothesize(episode,q,{'kind':'question','not_verified':True})
   goal=engine.details(activity)[3]
   for prediction in cognition['predictions']:Cognition(self.s).predict(episode,self.s.config()['self_actor'],{'text':prediction['outcome']},prediction['probability'],utc(prediction['due_seconds']),Goals(self.s).rule('completed'))
   if cognition['plan']:Cognition(self.s).plan(goal['id'],[dict(action=p['action'],expected={'text':p['expected']},depends_on=p['depends_on']) for p in cognition['plan']])
   self.s.event('cognition.output_recorded',payload={'request':request,'revisions':refs,'receipt_version':1,'created':created,'reused':reused,'suppressed_recall':suppressed},activity=activity,source='cognition',key=request)
 @coordinated
 def confirm(self,revision,expected_current,actor):
  if actor!=self.s.config()['controller']:raise Forbidden('controller required')
  with self.s.tx():
   candidate=self.s.row('cognition_belief_revisions',revision);belief=self.s.row('cognition_beliefs',candidate['belief_id'])
   if belief['current_revision_id']!=expected_current:raise Conflict('belief changed')
   if candidate['method_version'] not in ('cognition-v3','cognition-v6'):raise Conflict('not an unreviewed candidate')
   if self.s.db.execute("SELECT 1 FROM runtime_events WHERE instance_id=? AND event_type='cognition.confirmed' AND source_event_id=?",(self.s.instance_id,revision)).fetchone():raise Conflict('candidate already confirmed')
   if not self.readable_revision(revision):raise Forbidden('candidate source revoked or stale')
   links=list(self.s.db.execute('SELECT * FROM cognition_evidence_links WHERE target_revision_id=?',(revision,)))
   for link in links:
    evidence=self.s.row('evidence_items',link['evidence_id']);origin=evidence['origin_object_id']
    m=self.s.db.execute('SELECT memory_id FROM memory_revisions WHERE id=? AND instance_id=?',(origin,self.s.instance_id)).fetchone()
    if m and self.s.row('memory_items',m[0])['state']!='active':raise Forbidden('source removed')
   n=self.s.db.execute('SELECT max(revision_no)+1 FROM cognition_belief_revisions WHERE belief_id=?',(belief['id'],)).fetchone()[0]
   new=self.s.insert('cognition_belief_revisions',belief_id=belief['id'],revision_no=n,content=candidate['content'],acceptance_state='accepted',uncertainty_json={'authority':actor,'scope':'controller-reviewed statement, not external proof'},method_version='controller-reviewed-v1')
   if scope.active(self.s):
    ownership=self.s.db.execute('SELECT activity_id FROM acct_object_owners WHERE object_id=?',(revision,)).fetchone()
    if ownership:scope.tag_object(self.s,new,ownership[0])
   for link in links:self.s.insert('cognition_evidence_links',target_revision_id=new,evidence_id=link['evidence_id'],stance='support',strength_method='controller-review',assessment={'authority':actor})
   self.s.db.execute('UPDATE cognition_beliefs SET current_revision_id=?,literal=? WHERE id=?',(new,dumps({'value':json.loads(candidate['content'])['value']}),belief['id']))
   from digital_life.application.cognition.cognition_memory import publish
   publish(self.s,new)
   self.s.event('cognition.confirmed',payload={'candidate':revision,'old':expected_current,'new':new},source='cognition',key=revision,lane='control');return new
