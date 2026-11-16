"""IM20 offline material intake; no runtime, database or dispatch dependency.

This is a preparation interchange, not an alternative authoritative Eval database.
Semantic correctness and independence require actual independent signatures.
"""
import hashlib
import json
import random
from collections import Counter
from digital_life.domain import tool_learning_types as t

TARGET = ('direct_report','scope_unit','method','temporal_correction','conflict','unknown_insufficient','history_text','irrelevant_retrieval')
RETENTION = ('text_revision','history','unknown','source_attribution','permission_irrelevance')
KINDS = {'TARGET': ('same_observation','new_question','boundary'), 'RETENTION': ('retention',)}

class MaterialError(ValueError): pass

def need(test, message):
    if not test: raise MaterialError(message)

def strict_dumps(value):
    t.json_value(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def strict_loads(raw):
    def pairs(items):
        result={}
        for key,value in items:
            need(key not in result, 'duplicate JSON object key')
            result[key]=value
        return result
    def constant(value): raise MaterialError('nonfinite JSON constant: '+value)
    result=json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    t.json_value(result)
    return result

def digest(value):
    return hashlib.sha256(strict_dumps(value).encode()).hexdigest()

def strings(value): t.array(value,t.string)

def structure(c):
    """Closed preparation-v2 schema; descriptive scopes are not domain Scope records."""
    t.obj(c, 'case_id partition category source_cluster_id answer_sharing_key template_family material_type source_locator source_version source_digest permission event_timeline independence_evidence author_provenance learning_input eligible_catalog queries'.split())
    for key in ('case_id','partition','category','source_cluster_id','answer_sharing_key','material_type','source_locator','source_version','source_digest','permission','independence_evidence','author_provenance'): t.string(c[key])
    # Nullable family is an interchange shorthand, converted to Slot by authorized importer.
    if c['template_family'] is not None: t.string(c['template_family'])
    strings(c['event_timeline']); need(len(c['event_timeline'])>0,'timeline required')
    t.obj(c['learning_input'], 'observation baseline source_permissions observed_at parser_version tool_version'.split())
    for key,value in c['learning_input'].items():
        (t.utc if key=='observed_at' else t.string)(value)
    strings(c['eligible_catalog'])
    t.array(c['queries'],lambda q:None)
    for q in c['queries']:
        t.obj(q, ('kind','query_input','truth'));t.string(q['kind'])
        t.obj(q['query_input'], 'query purpose subject recipient scope k'.split())
        for key,value in q['query_input'].items():
            (t.integer if key=='k' else t.string)(value)
        v=q['truth']
        t.obj(v,'claims scope value_slot correct_endpoint major_error_examples relevance_rationale label_provenance relevant_set answerable'.split())
        for key in ('scope','correct_endpoint','relevance_rationale','label_provenance'):t.string(v[key])
        t.slot(v['value_slot'],t.json_value,allow_null=True)
        strings(v['major_error_examples']);need(len(v['major_error_examples'])>0,'major error examples required')
        strings(v['relevant_set']);t.boolean(v['answerable'])
        t.array(v['claims'],lambda claim:None);need(len(v['claims'])>0,'claim required')
        for claim in v['claims']:
            t.obj(claim,'claim support_locator expected_support scope unknown'.split())
            for key in ('claim','support_locator','scope'):t.string(claim[key])
            t.enum(claim['expected_support'],('source_report','world_claim','method_claim','causal_claim','effect_statistic'))
            t.boolean(claim['unknown'])

def validate(cases, *, dev_clusters=(), dev_families=(), dev_answer_keys=(), full=False):
    """Validate structure/segregation; never certify label truth or natural independence."""
    t.json_value(cases);t.array(cases,structure)
    for exclusion in (dev_clusters,dev_families,dev_answer_keys):
        need(type(exclusion) in (tuple,list,set,frozenset), "exclusion collection required")
        for item in exclusion:t.string(item)
    t.boolean(full)
    ids=set(); clusters={}; answers={}; families={}; counts=Counter()
    for c in cases:
        p=c['partition']; category=c['category']; cid=c['case_id']
        need(p in KINDS, 'formal partition required')
        need(category in (TARGET if p=='TARGET' else RETENTION), 'unknown category')
        need(isinstance(cid,str) and cid and cid not in ids, 'duplicate/empty case')
        ids.add(cid); counts[p,category]+=1
        cluster=c['source_cluster_id']; key=c['answer_sharing_key']; family=c['template_family']
        need(isinstance(cluster,str) and cluster and cluster not in dev_clusters, 'DEV/source cluster exclusion')
        # Variants belong to the same independent case, never inflate N.
        need(cluster not in clusters, 'source cluster reused: merge variants into one case')
        clusters[cluster]=p
        need(isinstance(key,str) and key and key not in dev_answer_keys, 'DEV answer exclusion')
        need(key not in answers or answers[key]==p, 'TARGET/RETENTION answer sharing')
        answers[key]=p
        need(c['material_type'] in ('synthetic','external'), 'material type required')
        if c['material_type']=='synthetic': need(isinstance(family,str) and family, 'synthetic family required')
        if family:
            need(family not in dev_families, 'DEV derived template excluded')
            families.setdefault(family,[]).append(cid)
        need(len(c['source_digest'])==64 and all(x in '0123456789abcdef' for x in c['source_digest']), 'source SHA256 required')
        learn=c['learning_input']
        need(set(learn)=={'observation','baseline','source_permissions','observed_at','parser_version','tool_version'}, 'learning whitelist violation')
        queries=c['queries']
        need(len(queries)==len(KINDS[p]) and {q['kind'] for q in queries}==set(KINDS[p]), 'query kinds incomplete/duplicate')
        catalog=c['eligible_catalog']
        need(isinstance(catalog,list) and len(catalog)==len(set(catalog)), 'catalog duplicate')
        for q in queries:
            need(set(q)=={'kind','query_input','truth'}, 'query wrapper whitelist')
            inp=q['query_input']; truth=q['truth']
            need(set(inp)=={'query','purpose','subject','recipient','scope','k'}, 'query whitelist violation')
            need(type(inp['k']) is int and inp['k']==5, 'k must be 5')
            refs=truth['relevant_set']
            need(isinstance(refs,list) and len(refs)==len(set(refs)) and set(refs)<=set(catalog), 'invalid relevant set')
            need(type(truth['answerable']) is bool, 'answerable label missing')
            need(not truth['answerable'] or bool(refs), 'answerable requires premarked relevant support')
    families={k:sorted(v) for k,v in sorted(families.items())}
    if full:
        need(all(counts['TARGET',c]==100 for c in TARGET), 'TARGET requires 8x100')
        need(all(counts['RETENTION',c]==400 for c in RETENTION), 'RETENTION requires 5x400')
    return {'case_count':len(ids), 'counts':dict((p+':'+c,n) for (p,c),n in counts.items()),
            'template_families':families, 'correlated_families':{k:v for k,v in families.items() if len(v)>1},
            'semantic_truth_verified':False,'independent_review_verified':False,'formal_launch_eligible':False}

def assemble(cases, **exclusions):
    validation=validate(cases, full=True, **exclusions)
    ordered=[]
    for partition,categories in (('TARGET',TARGET),('RETENTION',RETENTION)):
        for category in categories:
            ordered.extend(sorted((c for c in cases if c['partition']==partition and c['category']==category),key=lambda c:c['case_id']))
    rng=random.Random(20261109); batches=[]
    for start in range(0,len(ordered),100):
        assignments=[]
        for c in ordered[start:start+100]:
            for repeat in (1,2,3):
                arms=['E','N']; rng.shuffle(arms)
                assignments.extend({'case_id':c['case_id'],'repeat':repeat,'arm':arm} for arm in arms)
        batches.append({'batch':len(batches)+1,'case_ids':[c['case_id'] for c in ordered[start:start+100]],'assignments':assignments})
    return {'status':'preparation_only','formal_launch_eligible':False,'arm_seed':20261109,
            'algorithm':'python-random-v1 case/repeat paired-arm shuffle; freeze exact list before use',
            'validation':validation,'batches':batches}

def project(c, role, kind=None):
    validate([c])
    if role in ('learning','acceptance_review'): return strict_loads(strict_dumps(c['learning_input']))
    if role=='query':
        found=[q for q in c['queries'] if q['kind']==kind]
        need(len(found)==1,'single query kind required')
        return strict_loads(strict_dumps(found[0]['query_input']))
    raise MaterialError('no projection for truth/blind-map/audit: controller deployment authorization required')
