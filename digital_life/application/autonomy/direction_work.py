"""Bounded, source-guarded replay of accepted public work within one direction."""
import re
from digital_life.domain.contracts import dumps


def assemble(continuous,direction):
    s=continuous.s;x=continuous.x
    cap=min(32768,max(1024,s.config()['model'].get('max_input_bytes',16384)//3))
    empty={'catalog':[],'items':[],'source_guard_refs':[],'omitted_count':0,'body_budget_bytes':cap,'source_kind':'model-work-not-world-observation'}
    if not direction:return empty
    steps=[v for v in continuous.values('step') if v.get('direction_id')==direction['id']]
    query=direction.get('next_step','');explicit=set(re.findall(r'work:([a-f0-9]{32})',query));checked={};records=[]
    terms=lambda text:set(re.findall(r'[a-zA-Z0-9_]+',text.casefold()))|{text[i:i+2] for i in range(len(text)-1) if all('\u4e00'<=c<='\u9fff' for c in text[i:i+2])}
    query_terms=terms(query)
    for step in steps:
        request=s.db.execute('SELECT * FROM thought_requests WHERE id=? AND instance_id=?',(step['request'],s.instance_id)).fetchone()
        if not request or request['state']!='succeeded' or not request['accepted_result_id']:continue
        binding=x.binding(request['activity_id'])
        if not binding or binding.get('direction_id')!=direction['id']:continue
        result=s.row('thought_results',request['accepted_result_id'])
        if result['acceptance']!='accepted' or result['validation_state']!='valid':continue
        output=s.read_artifact(result['parsed_artifact_id']);original=s.read_artifact(request['request_artifact_id'])
        guards=list(dict.fromkeys(output.get('reflection',{}).get('evidence_refs',[])+[m['revision_id'] for m in original.get('selected_memories',[])]+original.get('exploration',{}).get('source_guard_refs',[])))
        for ref in guards:
            if ref not in checked:checked[ref]=x.readable_refs([ref])
        if not all(checked[ref] for ref in guards):
            records.append({'request':request['id'],'available':False,'reason':'source-no-longer-readable'});continue
        sources=[]
        for ref in guards:
            row=s.db.execute('SELECT content,encoding_method FROM memory_revisions WHERE id=? AND instance_id=?',(ref,s.instance_id)).fetchone()
            if row:sources.append({'revision_id':ref,'content':row['content'],'encoding_method':row['encoding_method']})
        body={'request':request['id'],'result':result['id'],'artifact':result['parsed_artifact_id'],'citation_refs':guards,'explanation':output['explanation'],'reflection':output.get('reflection'),'inquiry':output.get('inquiry'),'source_materials':sources,'source_kind':'accepted-model-work','independently_verified':False}
        records.append({'request':request['id'],'available':True,'summary':step.get('understanding','')[:160],'body_bytes':len(dumps(body).encode()),'_body':body,'_guards':guards,'_relevance':len(query_terms&terms(output['explanation']))})
    valid=[r for r in records if r['available']]
    # Explicit retrieval first, then relevant older products and recent work.
    positions={r['request']:i for i,r in enumerate(records)}
    ranked=sorted(valid,key=lambda r:(r['request'] in explicit,r['_relevance'],positions[r['request']]),reverse=True)
    picked=[];guards=[];used=0
    for r in ranked:
        if used+r['body_bytes']>cap:continue
        picked.append(r);guards.extend(r['_guards']);used+=r['body_bytes']
    picked.sort(key=lambda r:positions[r['request']]);included={r['request'] for r in picked}
    catalog_order=sorted(records,key=lambda r:(r['request'] in explicit,r['request'] in included,positions[r['request']]),reverse=True)[:24]
    catalog=[{**{k:v for k,v in r.items() if not k.startswith('_')},'included':r['request'] in included} for r in sorted(catalog_order,key=lambda r:positions[r['request']])]
    return {**empty,'catalog':catalog,'items':[r['_body'] for r in picked],'source_guard_refs':list(dict.fromkeys(guards)),'omitted_count':len(records)-len(picked),'catalog_omitted_count':len(records)-len(catalog),'requested_not_found':sorted(explicit-{r['request'] for r in records}),'body_bytes':used}
