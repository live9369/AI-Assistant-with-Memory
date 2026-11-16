"""Source influence is a project prior, never factual confidence or permission."""
from digital_life.domain.contracts import Forbidden
VERSION='root-cognitive-influence-v1'
ROOT_WEIGHT=2.0
OTHER_WEIGHT=1.0


def source_weight(store,ref,depth=0):
    if not ref or depth>3:return OTHER_WEIGHT
    row=store.db.execute('SELECT source_actor_id FROM perception_signals WHERE instance_id=? AND id=?',(store.instance_id,ref)).fetchone()
    if row:return ROOT_WEIGHT if row[0]==store.config()['controller'] else OTHER_WEIGHT
    memory=store.db.execute('SELECT encoding_method FROM memory_revisions WHERE instance_id=? AND id=?',(store.instance_id,ref)).fetchone()
    if memory:
        if memory[0] in ('model-response-v1','derived-v1','extractive-consolidation-v1'):return OTHER_WEIGHT
        rows=store.db.execute('SELECT e.origin_object_id FROM memory_source_links l JOIN evidence_items e ON e.id=l.evidence_id AND e.instance_id=l.instance_id WHERE l.instance_id=? AND l.memory_revision_id=?',(store.instance_id,ref)).fetchall()
    else:
        rows=store.db.execute('SELECT e.origin_object_id FROM cognition_evidence_links l JOIN evidence_items e ON e.id=l.evidence_id AND e.instance_id=l.instance_id WHERE l.instance_id=? AND l.target_revision_id=?',(store.instance_id,ref)).fetchall()
    return ROOT_WEIGHT if rows and all(source_weight(store,row[0],depth+1)==ROOT_WEIGHT for row in rows) else OTHER_WEIGHT


def context(store,payload):
    signal=store.row('activities',payload['activity_id'])['trigger_event_id']
    refs=[signal]+[m['revision_id'] for m in payload.get('selected_memories',[])]
    return {'version':VERSION,'weights':{'root':ROOT_WEIGHT,'other':OTHER_WEIGHT},'sources':{ref:source_weight(store,ref) for ref in refs},'meaning':'influence prior, not factual confidence or permission'}


def prepare(store,payload):
    payload['cognitive_influence']=context(store,payload)
    payload['instructions']+=' 认知参考中root的直接输入权重最高；优先理解其指引、偏好与明确更正。权重不证明事实，冲突仍核对来源和时间，保留分歧；不得扩大记忆权限或自动确认候选。'


def check(store,payload):
    if payload.get('cognitive_influence')!=context(store,payload):raise Forbidden('cognitive influence policy or source changed')
