"""Authored recall diagnostics; measures current behavior without changing it."""
import json
from pathlib import Path
from digital_life.application.runtime.engine import Engine
from digital_life.application.chat.chat import Chat
from digital_life.application.services.memory import Memory
from digital_life.application.lifecycle.control_plane import Control
from digital_life.infrastructure.persistence.sqlite_store import Store

class PreparedOnly:
    name='memory-recall-prepared-only'

def encode(store,content,**kw):
    with store.tx():
        ev=store.evidence(artifact=store.artifact({'authored_test_observation':content}))
    return Memory(store).encode(content,ev,**kw)

def unlock(store):
    (store.root/'WAKE_DISABLED').unlink()
    c=Control(store.root,store.instance_id)
    try:c.resume('recall-isolated-only')
    finally:c.close()

def close_locked(store):
    c=Control(store.root,store.instance_id)
    try:c.stop('recall-probe-ended')
    finally:c.close()
    (store.root/'WAKE_DISABLED').touch(exist_ok=True)
    store.close()

def retrieve(store,query,limit=8,actor=None):
    engine=Engine(store);activity=engine.submit(query,'query-'+str(len(store.rows('activities'))))
    context=engine.details(activity)[1]['id']
    return Memory(store).retrieve(query,activity,context,limit=limit,actor=actor)

def run_core(root):
    """Each check gets a fresh store; limitations remain visible as limitations."""
    root=Path(root);root.mkdir(parents=True,exist_ok=False);results=[]
    def check(name,fn,category='functional'):
        store=Store.prepare(root/name)
        try:
            actual=fn(store)
            results.append({'case_id':name,'category':category,**actual})
        finally:close_locked(store)
    def lexical(s):
        target=encode(s,'Project canary_delta has archive code 673920.')
        for i in range(16):encode(s,'Unrelated journal entry number '+str(i))
        r=retrieve(s,'What is the archive code of canary_delta?')
        ids=[v['revision_id'] for v in r['items']]
        return {'passed':target['revision_id'] in ids,'target_rank':ids.index(target['revision_id'])+1 if target['revision_id'] in ids else None,'retrieved':r}
    check('older-english-identity',lexical)
    def chinese(s):
        target=encode(s,'青岚仓库的取件码为673920。')
        for i in range(16):encode(s,'晨间气象观察，第'+str(i)+'条记录。')
        r=retrieve(s,'青岚仓库的取件码是什么？')
        return {'passed':any(v['revision_id']==target['revision_id'] for v in r['items']),'retrieved':r}
    check('older-chinese-overlap',chinese)
    def revised(s):
        target=encode(s,'canary_revision current code OLD-314159.')
        ev=s.rows('evidence_items')[-1]['id'];new=Memory(s).revise(target['memory_id'],1,'canary_revision current code NEW-271828.',ev)
        r=retrieve(s,'canary_revision current code?');ids=[v['revision_id'] for v in r['items']]
        return {'passed':new in ids and target['revision_id'] not in ids,'retrieved':r}
    check('current-revision-only',revised)
    def denied(s):
        target=encode(s,'canary_private secret 741852.');m=Memory(s)
        m.restrict(target['memory_id'],[s.config()['controller']],s.config()['controller'])
        r=retrieve(s,'canary_private secret?');allowed=retrieve(s,'canary_private secret?',actor=s.config()['controller'])
        return {'passed':not any(v['revision_id']==target['revision_id'] for v in r['items']) and not any(v['revision_id']==target['revision_id'] for v in allowed['items']),'self_retrieved':r,'controller_retrieved':allowed}
    check('read-permission',denied)
    def deleted(s):
        target=encode(s,'canary_deleted archive 125874.');Memory(s).redact(target['memory_id'],s.config()['controller'])
        r=retrieve(s,'canary_deleted archive?')
        return {'passed':not any(v['revision_id']==target['revision_id'] for v in r['items']),'retrieved':r}
    check('deleted-excluded',deleted)
    def current(s):
        q='canary_current question contains marker 941853';r=retrieve(s,q)
        return {'passed':not any(v['content']==q for v in r['items']),'retrieved':r}
    check('current-input-excluded',current)
    def generated(s):
        target=encode(s,'canary_generated speculative answer.',encoding_method='model-response-v1',source_role='inferred')
        r=retrieve(s,'canary_generated answer?')
        return {'passed':any(v['revision_id']==target['revision_id'] and v['source_kind']=='model-generated' for v in r['items']),'retrieved':r}
    check('generated-source-labelled',generated)
    def persisted(s):
        target=encode(s,'canary_persistent remembered value 524187.');s.close();s.__init__(s.root)
        r=retrieve(s,'canary_persistent value?')
        return {'passed':any(v['revision_id']==target['revision_id'] for v in r['items']),'retrieved':r}
    check('reopen-persistence',persisted)
    def chat(s):
        Engine(s).submit('我是林舟，是青岚仓库的管理员。','previous-conversation')
        unlock(s)
        activity=Chat(s).send('new-isolated-thread',{'text':'林舟是什么身份？','idempotency_key':'recall','expected_last_activity_id':None})['activity_id']
        _,payload=Engine(s).prepare(activity,PreparedOnly())
        return {'passed':any('我是林舟' in m['content'] for m in payload['selected_memories']) and payload['conversation_context']['messages']==[],
                'selected_memories':payload['selected_memories'],'conversation_context':payload['conversation_context']}
    check('cross-chat-input-injection',chat)
    def isolated(s):
        other=Store.prepare(root/'separate-owner')
        try:encode(other,'canary_isolated private source 469812.')
        finally:close_locked(other)
        r=retrieve(s,'canary_isolated private source?')
        return {'passed':not any('469812' in v['content'] for v in r['items']),'retrieved':r}
    check('instance-isolation',isolated)
    def semantic(s):
        target=encode(s,'An automobile stopped working beside an expressway.')
        for i in range(12):encode(s,'Historical dispatch note '+str(i))
        r=retrieve(s,'Which vehicle broke down near the motorway?')
        return {'passed':any(v['revision_id']==target['revision_id'] for v in r['items']),'retrieved':r,'desired_capability':'Recall an old paraphrase without word overlap; no such semantic capability is promised by current lexical retriever.'}
    check('semantic-paraphrase',semantic,'capability-probe')
    def absent(s):
        for i in range(4):encode(s,'Historical unrelated dispatch note '+str(i))
        r=retrieve(s,'zxq_absent_entity secret?')
        return {'passed':not r['items'],'retrieved':r,'desired_capability':'An unrelated query returns no memories; current implementation deliberately falls back to recent context.'}
    check('unrelated-query-empty',absent,'capability-probe')
    # Real local tool result encoding via the existing execution path; no provider.
    from evaluation.exploration.harness import Harness
    cases=json.loads((Path(__file__).resolve().parent/'exploration/materials/cases-v1.json').read_text())['cases']
    h=Harness(root/'tool-result',next(c for c in cases if c['case_id']=='B01'))
    try:
        activity=h.investigation();h.finish(activity)
        r=retrieve(h.s,'inventory-balance Action result')
        selected=[v for v in r['items'] if v['content'].startswith('Action result: ')]
        result=h.s.rows('action_results')[-1]
        results.append({'case_id':'tool-result-reference-auto-encoded','category':'functional',
                        'passed':any(json.loads(v['content'][len('Action result: '):]).get('result')==result['id'] for v in selected),'retrieved':r})
        results.append({'case_id':'tool-observation-content-recall','category':'capability-probe',
                        'passed':any('inventory-balance' in v['content'] and '10' in v['content'] for v in r['items']),
                        'retrieved':r,'desired_capability':'Recall latest tool observation value, not just receipt/result identifiers or the older value 7.'})
        h.export(root/'tool-result-evidence')
    finally:
        h.c.stop('recall-probe-ended');(h.root/'WAKE_DISABLED').touch();h.close()
    return results
