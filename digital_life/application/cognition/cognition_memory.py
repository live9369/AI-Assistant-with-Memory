"""M04 representations of M03 revisions: no second authoritative belief store."""
import json
from contextvars import ContextVar
from digital_life.domain.contracts import ContractError,dumps

ENCODING='cognition-representation-v1'
_checking=ContextVar('cognition_representation_checks',default=())

def source_memories(store,ref):
    rows=store.db.execute('SELECT memory_id FROM memory_revisions WHERE id=? AND instance_id=?',(ref,store.instance_id)).fetchall()
    rows+=store.db.execute('SELECT DISTINCT r.memory_id FROM memory_source_links l JOIN evidence_items e ON e.id=l.evidence_id JOIN memory_revisions r ON r.id=l.memory_revision_id WHERE l.instance_id=? AND (e.origin_object_id=? OR e.artifact_id=? OR e.id IN (SELECT outcome_ref FROM action_results WHERE instance_id=? AND receipt_artifact_id=?))',(store.instance_id,ref,ref,store.instance_id,ref)).fetchall()
    return list(dict.fromkeys(r[0] for r in rows))

def revision_for(store,memory):
    row=store.db.execute("SELECT e.origin_object_id FROM memory_items m JOIN memory_revisions r ON r.id=m.current_revision_id JOIN memory_source_links l ON l.memory_revision_id=r.id JOIN evidence_items e ON e.id=l.evidence_id WHERE m.id=? AND m.instance_id=? AND r.encoding_method=? AND e.method='cognition-representation'",(memory,store.instance_id,ENCODING)).fetchone()
    return row[0] if row else None

def available(store,memory,current_only=False):
    revision=revision_for(store,memory)
    if not revision:return True
    stack=_checking.get()
    if revision in stack or len(stack)>=32:return False
    token=_checking.set(stack+(revision,))
    try:
        from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
        if not CognitiveUpdates(store).readable_revision(revision):return False
        row=store.row('cognition_belief_revisions',revision);belief=store.row('cognition_beliefs',row['belief_id'])
        if not current_only:return row['acceptance_state'] in ('held','accepted')
        if row['acceptance_state']=='accepted':return belief['current_revision_id']==revision
        if row['acceptance_state']!='held':return False
        head=store.row('cognition_belief_revisions',belief['current_revision_id'])
        if head['acceptance_state']=='accepted' and head['revision_no']>row['revision_no']:return False
        return not store.db.execute("SELECT 1 FROM cognition_belief_revisions WHERE belief_id=? AND instance_id=? AND acceptance_state='held' AND revision_no>? LIMIT 1",(row['belief_id'],store.instance_id,row['revision_no'])).fetchone()
    except (ContractError,OSError,ValueError):return False
    finally:_checking.reset(token)

def publish(store,revision):
    from digital_life.application.services.memory import Memory
    from digital_life.application.accounts import account_scope as scope
    old=store.db.execute("SELECT r.id,r.memory_id FROM memory_source_links l JOIN evidence_items e ON e.id=l.evidence_id JOIN memory_revisions r ON r.id=l.memory_revision_id WHERE e.instance_id=? AND e.origin_object_id=? AND e.method='cognition-representation' LIMIT 1",(store.instance_id,revision)).fetchone()
    if old:return {'memory_id':old['memory_id'],'revision_id':old['id'],'reused':True}
    row=store.row('cognition_belief_revisions',revision);belief=store.row('cognition_beliefs',row['belief_id']);value=json.loads(row['content'])
    subject=store.row('world_entities',belief['subject_ref'])['canonical_name']
    kind=value.get('kind','reported')
    label={'reported':'来源陈述','hypothesis':'推断','method':'方法建议'}.get(kind,'候选')
    state='经控制者确认；并非外部真值证明' if row['acceptance_state']=='accepted' else '未核实候选'
    content=f"[{label}｜{state}] 对象：{subject}；事项：{belief['predicate']}；内容：{value['value']}。原文：{value.get('quote','')}。"
    content+='有效时间：'+(value.get('valid_at') or '未知')+'；记录时间：'+row['recorded_at']+'。'
    from digital_life.application.cognition.cognitive_updates import CognitiveUpdates
    source=store.db.execute("SELECT e.origin_object_id FROM cognition_evidence_links l JOIN evidence_items e ON e.id=l.evidence_id WHERE l.target_revision_id=? AND e.method='quoted-source' LIMIT 1",(revision,)).fetchone()
    if source:
        metadata=CognitiveUpdates(store)._source_metadata(source[0])
        content+='来源性质：'+metadata['type']+(' / '+metadata.get('encoding_method','') if metadata.get('encoding_method') else '')+'；来源编号：'+source[0]+'。'
    if value.get('context_contains'):content+='方法适用线索：'+value['context_contains']+'。'
    content+='认知修订：'+revision+'；此表示不覆盖旧来源，也不把模型总结提升为事实。'
    parents=[]
    for link in store.db.execute('SELECT e.origin_object_id FROM cognition_evidence_links l JOIN evidence_items e ON e.id=l.evidence_id WHERE l.target_revision_id=? AND l.instance_id=?',(revision,store.instance_id)):
        for parent in source_memories(store,link[0]):
            if parent not in parents:parents.append(parent)
    with store.tx():
        evidence=store.evidence(object_id=revision,method='cognition-representation')
        memory=Memory(store)
        result=memory.derive(content,parents,evidence,scope.effective_reader(store),encoding_method=ENCODING) if parents else memory.encode(content,evidence,encoding_method=ENCODING,source_role='inferred')
        store.event('cognition.representation_published',payload={'cognition_revision':revision,**result,'acceptance_state':row['acceptance_state'],'source_kind':kind},lane='control')
        return result
