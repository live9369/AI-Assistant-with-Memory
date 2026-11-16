"""Explicit bounded formal-instance test via the existing inbound/runtime route.
No manual model calls, approval widening, forced belief confirmation or new conversation.
"""
import json,sqlite3,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from digital_life.application.lifecycle.control_plane import Control
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.services.memory import Memory
from digital_life.application.runtime.engine import Engine
from digital_life.application.services.goals import Goals
from digital_life.domain.contracts import utc

root=Path('work/primordial00-first-wake').resolve();trial=uuid.uuid4().hex[:8];out=Path('outputs')/('experience-return-formal-'+trial);out.mkdir(parents=True,exist_ok=False)

def db():
 c=sqlite3.connect((root/'runtime.sqlite').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c

def artifact(c,ref):
 r=c.execute('SELECT storage_ref FROM artifacts WHERE id=?',(ref,)).fetchone();return json.loads((root/'blobs'/r[0]).read_text())

c=db();identity=c.execute('SELECT id FROM identity_instances').fetchone()[0];cfg=artifact(c,c.execute('SELECT artifact_ref FROM configuration_versions ORDER BY rowid DESC LIMIT 1').fetchone()[0]);c.close();control=Control(root,identity)
assert control.state()['active_process_run_id'] and not control.state()['user_stopped'],'existing runtime is not running'
actor=cfg['controller'];source='acceptance-experience-'+trial;name='雾杉盒-'+trial;token='FG-'+uuid.uuid4().hex[:6];old='银色架子左格';new='蓝色柜子右格';activities=[];turns=[];summary={'trial':trial,'started_at':utc(),'formal_instance_used':True,'out':str(out),'completed':False}
messages=[
 f'这是明确标注的合成验收资料，不代表真实生活，只适用于本轮测试。测试对象叫{name}，测试代号是{token}，本次报告位置为{old}。请只保存关于这个测试对象的、有原文来源的认知候选，不确认现实事实，不执行工具，简短回应。',
 f'这是同一轮合成验收的明确更正。针对同一个{name}，此前位置是旧记录；现在报告的位置改为{new}。代号未变。请保留旧记录及来源，把新位置记为尚未核实的候选，不执行工具，简短回应。',
 f'请仅根据已有记录回答：{name}现在报告的位置在哪里，以前报告在哪里，测试代号是什么？请说明来源和核实状态；不知道就直说，不执行工具。'
]
(out/'manifest.json').write_text(json.dumps({'trial':trial,'source':source,'name':name,'expected_code':token,'expected_old':old,'expected_new':new,'max_calls':3,'messages':messages},ensure_ascii=False,indent=2))
try:
 for index,message in enumerate(messages,1):
  key=trial+'-'+str(index);started=time.monotonic();control.accept_inbound(source,key,{'text':message},actor);print(json.dumps({'turn':index,'state':'submitted'}),flush=True)
  answer=None
  for _ in range(420):
   c=db()
   try:
    a=c.execute('SELECT a.id,a.state,a.trigger_event_id FROM perception_signals p JOIN activities a ON a.trigger_event_id=p.id WHERE p.instance_id=? AND p.external_id=?',(identity,source+':'+key)).fetchone()
    if a:
     if a['id'] not in activities:activities.append(a['id'])
     q=c.execute('SELECT * FROM thought_requests WHERE activity_id=? ORDER BY rowid DESC LIMIT 1',(a['id'],)).fetchone()
     if q:
      packet=artifact(c,q['request_artifact_id']);(out/f'input-{index}.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2))
      if q['accepted_result_id']:
       r=c.execute('SELECT * FROM thought_results WHERE id=?',(q['accepted_result_id'],)).fetchone();value=artifact(c,r['parsed_artifact_id']);assert r['acceptance']=='accepted'
       claims=[]
       for e in c.execute("SELECT payload_artifact_id FROM runtime_events WHERE activity_id=? AND event_type='cognition.output_recorded'",(a['id'],)):
        for ref in artifact(c,e[0])['revisions']:
         row=c.execute('SELECT * FROM cognition_belief_revisions WHERE id=?',(ref,)).fetchone();claims.append({'id':ref,'content':json.loads(row['content']),'state':row['acceptance_state']})
       answer={'turn':index,'activity':a['id'],'request':q['id'],'accepted':True,'elapsed_seconds':round(time.monotonic()-started,2),'reply':value['explanation'],'cognition':claims,'context_mode':packet['context_mode'],'conversation_context_present':bool(packet.get('conversation_context')),'recalled_representations':[m for m in packet['selected_memories'] if m.get('source_kind')=='cognition-representation']}
       (out/f'output-{index}.json').write_text(json.dumps(value,ensure_ascii=False,indent=2));break
     if a['state'] in ('failed','paused','cancelled'):raise RuntimeError('test activity stopped before an accepted result: '+a['state'])
   finally:c.close()
   time.sleep(1)
  if not answer:raise TimeoutError('bounded formal turn did not complete')
  turns.append(answer);(out/'turns.json').write_text(json.dumps(turns,ensure_ascii=False,indent=2));print(json.dumps(answer,ensure_ascii=False),flush=True)
 summary.update(completed=True,turns=turns)
finally:
 control.close()
 # Do not race active provider use. At a normal completion all three test requests are settled.
 s=Store(root)
 try:
  busy=[a for a in activities if s.db.execute("SELECT 1 FROM jobs WHERE target_ref=? AND state='leased'",(a,)).fetchone()]
  if busy:
   summary['cleanup_pending']='active test job; retained for explicit follow-up';summary['active_test_activities']=busy
  else:
   origins=set();cgrefs=[]
   for a in activities:
    origins.add(s.row('activities',a)['trigger_event_id']);origins.update(r[0] for r in s.db.execute('SELECT r.id FROM thought_results r JOIN thought_requests q ON q.id=r.request_id WHERE q.activity_id=?',(a,)))
    for e in s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE activity_id=? AND event_type='cognition.output_recorded'",(a,)):cgrefs+=s.read_artifact(e[0])['revisions']
   origins.update(cgrefs);memories={}
   for ref in origins:
    for r in s.db.execute("SELECT DISTINCT m.id,r.id revision,r.content FROM memory_items m JOIN memory_revisions r ON r.id=m.current_revision_id JOIN memory_source_links l ON l.memory_revision_id=r.id JOIN evidence_items e ON e.id=l.evidence_id WHERE m.instance_id=? AND m.state='active' AND e.origin_object_id=?",(identity,ref)):memories[r['id']]=dict(r)
   (out/'cleanup.json').write_text(json.dumps({'purpose':'archive only this synthetic trial; keep original evidence','records':list(memories.values())},ensure_ascii=False,indent=2))
   for ref in memories:Memory(s).archive(ref,actor,'本轮合成验收结束，移出日常召回，保留原文及审计。')
   for a in activities:
    row,_,signal,goal=Engine(s).details(a)
    if row['state'] not in ('completed','cancelled','failed'):Engine(s).cancel(a,actor)
    if goal['state'] in ('candidate','accepted','active','paused'):
     with s.tx():Goals(s).transition(goal['id'],'cancelled',signal['id'],'synthetic-acceptance-ended')
   summary['archived_memories']=len(memories);summary['cleanup_pending']=False
  summary['finished_at']=utc()
 finally:s.close()
 (out/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps({'completed':summary['completed'],'out':str(out),'archived_memories':summary.get('archived_memories'),'cleanup_pending':summary.get('cleanup_pending')}),flush=True)
