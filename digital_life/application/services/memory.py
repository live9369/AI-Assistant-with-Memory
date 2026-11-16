"""Memory application service."""
import json
import math
import re
import time
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

from digital_life.application.accounts import account_scope as scope

class Memory:
    def __init__(self,store): self.s=store
    def readers(self,memory,_seen=None,_depth=0,_memo=None):
        seen=set() if _seen is None else set(_seen)
        if memory in seen or _depth>64:return set()
        memo={} if _memo is None else _memo
        if (memory,_depth) in memo:return set(memo[(memory,_depth)])
        seen.add(memory);item=self.s.row('memory_items',memory);policy=self.s.row('policy_versions',item['access_policy_ref'])
        from digital_life.application.cognition.cognition_memory import available
        if not available(self.s,memory):
            memo[(memory,_depth)]=frozenset();return set()
        readers=set(json.loads(policy['scope']).get('memory_readers',[self.s.config()['self_actor'],self.s.config()['controller']]))
        readers=scope.memory_readers(self.s,memory,readers,'memory_readers' in json.loads(policy['scope']))
        from digital_life.application.memory.memory_quality import MemoryQuality,DEPENDENCIES
        captured=MemoryQuality(self.s).dependencies(memory)
        parents=self.s.db.execute("SELECT to_memory_id FROM memory_relations WHERE instance_id=? AND from_memory_id=? AND relation_type IN ('derived_from','summary_of','consolidated_from')",(self.s.instance_id,memory)).fetchall()
        versions={p['memory']:p['revision'] for p in captured} if captured is not None else None
        for parent in parents:
            source=self.s.row('memory_items',parent[0])
            if source['state']!='active' or (versions is not None and versions.get(parent[0])!=source['current_revision_id']):
                memo[(memory,_depth)]=frozenset();return set()
            readers &= self.readers(parent[0],seen,_depth+1,memo)
            if not readers:
                memo[(memory,_depth)]=frozenset();return set()
        memo[(memory,_depth)]=set(readers)
        return readers
    def restrict(self,memory,readers,actor):
        if actor!=self.s.config()['controller']: raise Forbidden('controller required')
        with self.s.tx():
            for reader in readers: self.s.row('social_actors',reader)
            old=self.s.row('memory_items',memory)
            ref=self.s.insert('policy_versions',version=max(r['version'] for r in self.s.rows('policy_versions'))+1,mode='authorization',scope={'memory_readers':list(readers)},effective_at=utc(),authority=actor)
            self.s.db.execute('UPDATE memory_items SET access_policy_ref=? WHERE id=?',(ref,memory))
            self.s.event('memory.policy_changed',payload={'memory':memory,'old':old['access_policy_ref'],'policy':ref},lane='control')
            from digital_life.application.memory.memory_quality import MemoryQuality
            MemoryQuality(self.s).dirty(memory)
            return ref
    def derive(self,content,sources,evidence,actor,encoding_method="derived-v1"):
        if not sources: raise ContractError('derivation needs sources')
        readers=None
        with self.s.tx():
            for source in sources:
                if self.s.row('memory_items',source)['state']!='active': raise Forbidden('source memory is no longer active')
                allowed=self.readers(source)
                if actor not in allowed: raise Forbidden('source memory not readable')
                readers=allowed if readers is None else readers & allowed
            result=self.encode(content,evidence,encoding_method=encoding_method,source_role="summarized")
            self.restrict(result['memory_id'],sorted(readers),self.s.config()['controller'])
            for source in sources: self.s.insert('memory_relations',from_memory_id=result['memory_id'],to_memory_id=source,relation_type='derived_from',evidence_id=evidence)
            from digital_life.application.memory.memory_quality import MemoryQuality
            MemoryQuality(self.s).capture(result['memory_id'],sources);MemoryQuality(self.s).dirty(result['memory_id'])
            return result
    def encode(self,content,evidence,labels=None,policy=None,encoding_method="explicit-v1",source_role="observed"):
        with self.s.tx():
            policy=policy or self.s.rows('policy_epochs')[0]['policy_version_id']
            mem=self.s.insert('memory_items',state='active',salience=0.5,access_policy_ref=policy)
            rev=self.s.insert('memory_revisions',memory_id=mem,revision_no=1,content=text(content),encoding_method=encoding_method)
            self.s.insert('memory_source_links',memory_revision_id=rev,evidence_id=evidence,role=source_role)
            for axis,label in (labels or [('content','episodic')]): self.s.insert('memory_classifications',memory_id=mem,axis=axis,label=label,method_version='explicit-v1')
            self.s.db.execute('UPDATE memory_items SET current_revision_id=? WHERE id=?',(rev,mem))
            scope.tag_memory(self.s,mem,evidence)
            from digital_life.application.memory.memory_quality import MemoryQuality
            quality=MemoryQuality(self.s);quality.dirty(mem)
            if encoding_method=='model-response-v1':
                source=self.s.row('evidence_items',evidence)['origin_object_id']
                if source and self.s.db.execute('SELECT 1 FROM thought_results WHERE instance_id=? AND id=?',(self.s.instance_id,source)).fetchone():quality.link_response(mem,source)
            return {'memory_id':mem,'revision_id':rev}
    def remember_public_responses(self):
        """Append missing historical public replies; never rewrite prior episodes."""
        created=0
        with self.s.tx():
            rows=self.s.db.execute("SELECT r.id,r.response_artifact_id FROM thought_results r WHERE r.instance_id=? AND r.validation_state='valid' AND r.acceptance='accepted' AND NOT EXISTS (SELECT 1 FROM evidence_items e JOIN memory_source_links l ON l.evidence_id=e.id AND l.instance_id=e.instance_id WHERE e.instance_id=r.instance_id AND e.origin_object_id=r.id AND e.method='model-response')",(self.s.instance_id,)).fetchall()
            for row in rows:
                if not scope.source_allowed(self.s,row["id"]):continue
                try:output=self.s.read_artifact(row['response_artifact_id'])
                except (OSError,ValueError,ContractError):continue
                if not isinstance(output,dict) or not isinstance(output.get('explanation'),str) or not output['explanation'] or 'redacted_by' in output:continue
                evidence=self.s.evidence(object_id=row['id'],method='model-response')
                self.encode(output['explanation'],evidence,labels=[('content','conversational-response')],encoding_method='model-response-v1',source_role='inferred');created+=1
        return created
    def retrieve(self,query,activity,context,limit=8,actor=None):
        from digital_life.application.learning.runtime import strict_legacy_boundary
        strict_legacy_boundary(self.s,'legacy_memory_retrieval')
        if not 1<=limit<=50: raise ContractError('retrieval limit')
        started=time.perf_counter()
        with self.s.tx():
            run=self.s.insert('memory_retrieval_runs',activity_id=activity,context_id=context,query=query,retriever_version='shared-hybrid-v2')
            actor=actor or scope.effective_reader(self.s);self.s.row('social_actors',actor)
            query=query.casefold()
            historical=bool(re.search(r'以前|此前|过去|曾经|原来|旧(?:的|说法|位置|记录)|history|previous|before',query))
            terms=set(re.findall(r'[a-z0-9_]+',query))
            def grams(value):
                return {word[i:i+2] for word in re.findall(r'[\u4e00-\u9fff]+',value) for i in range(len(word)-1)}
            query_grams=grams(query)
            trigger=self.s.row('activities',activity)['trigger_event_id']
            from digital_life.application.memory.memory_quality import MemoryQuality
            quality=MemoryQuality(self.s);quality_enabled=quality.config()['enabled'];ids,diagnostics=quality.candidates(query)
            rows=quality.load_rows(ids) if ids is not None else self.s.db.execute("SELECT r.*,m.salience FROM memory_revisions r JOIN memory_items m ON m.current_revision_id=r.id AND m.instance_id=r.instance_id WHERE r.instance_id=? AND m.state='active' ORDER BY r.rowid DESC",(self.s.instance_id,)).fetchall()
            if diagnostics is not None:diagnostics['checked_candidates']=len(rows)
            candidates=[]
            for index,row in enumerate(rows):
                # The just-received input is already in task/observation, not evidence of a prior memory.
                same=self.s.db.execute('SELECT 1 FROM memory_source_links l JOIN evidence_items e ON e.id=l.evidence_id AND e.instance_id=l.instance_id WHERE l.memory_revision_id=? AND l.instance_id=? AND e.origin_object_id=? LIMIT 1',(row['id'],self.s.instance_id,trigger)).fetchone()
                if same:continue
                content=row['content'].casefold();names=set(re.findall(r'[a-z0-9_]+',content))
                overlap=terms & names;score=8*len(overlap)+min(12,len(query_grams & grams(content)))*.5
                autobiographic=bool(re.search(r'我(?:是|叫)|我的名字|称呼我|父亲|母亲',content))
                memory_question=bool(re.search(r'记忆|记得|认识|是谁|名字|哪些人',query))
                if autobiographic and (score or memory_question):score+=4
                if '?' in content or '？' in content:score*=.5
                generated=row['encoding_method']=='model-response-v1'
                if generated:score*=.7
                recent=(row['id'] in quality.last_recent) if ids is not None else index<8
                if not score and recent:score=.05/(index+1)
                if not score:continue
                if quality_enabled:score*=.2+1.6*row['salience']
                if scope.active(self.s):
                    from digital_life.application.accounts.cognitive_influence import source_weight
                    score*=source_weight(self.s,row['id'])
                candidates.append((score,index,row,'name-match' if overlap else 'character-overlap' if query_grams & grams(content) else 'autobiographic-cue' if autobiographic else 'recent-context'))
            candidates.sort(key=lambda item:(-item[0],item[1]));items=[];checked=0
            for score,index,row,reason in candidates:
                if len(items)>=limit:break
                checked+=1
                if row['encoding_method']=='cognition-representation-v1':
                    from digital_life.application.cognition.cognition_memory import available
                    if not historical and not available(self.s,row['memory_id'],current_only=True):continue
                if not scope.can_recall(self.s,row['memory_id'],actor):
                    self.s.event('memory.access_denied',payload={'memory':row['memory_id'],'actor':actor},activity=activity,lane='control');continue
                rank=len(items)+1
                self.s.insert('memory_retrieval_results',run_id=run,memory_revision_id=row['id'],rank=rank,score=score,selection_reason=reason)
                self.s.insert('memory_access_records',memory_revision_id=row['id'],activity_id=activity,operation='retrieved')
                kind='cognition-representation' if row['encoding_method']=='cognition-representation-v1' else 'model-generated' if row['encoding_method']=='model-response-v1' else 'extractive-summary' if row['encoding_method']=='extractive-consolidation-v1' else 'derived-record' if row['encoding_method']=='derived-v1' else 'corrected-record' if row['encoding_method']=='correction-v1' else 'recorded-experience'
                item={'revision_id':row['id'],'content':row['content'],'source_kind':kind,'selection_reason':reason}
                if row['encoding_method']=='cognition-representation-v1':
                    from digital_life.application.cognition.cognition_memory import available
                    item['temporal_status']='current' if available(self.s,row['memory_id'],current_only=True) else 'historical; not the current version'
                if quality_enabled:item['conflicts']=quality.annotations(row['id'],actor)
                items.append(item)
            result={'run_id':run,'items':items,'coverage':'instance-wide authorized lexical/name/character/recency recall; not general semantic understanding'}
            if diagnostics is not None:result['quality']=diagnostics
            self.s.event('memory.retrieval_timing',payload={'run':run,'loaded_candidates':len(rows),'scored_candidates':len(candidates),'checked_candidates':checked,'selected':len(items),'elapsed_ms':round((time.perf_counter()-started)*1000,3)},activity=activity,lane='control')
            return result
    def revise(self,memory,expected_revision,content,evidence):
        with self.s.tx():
            old=self.s.row('memory_items',memory)
            current=self.s.row('memory_revisions',old['current_revision_id'])
            if current['revision_no']!=expected_revision: raise Conflict('memory revision changed')
            rev=self.s.insert('memory_revisions',memory_id=memory,revision_no=expected_revision+1,content=text(content),encoding_method='correction-v1',correction_reason='explicit-evidence')
            self.s.insert('memory_source_links',memory_revision_id=rev,evidence_id=evidence,role='inferred')
            self.s.db.execute('UPDATE memory_items SET current_revision_id=? WHERE id=?',(rev,memory))
            from digital_life.application.memory.memory_quality import MemoryQuality
            MemoryQuality(self.s).dirty(memory)
            return rev
    def archive(self,memory,actor,reason):
        """Retain the original record while removing it from active recall."""
        if actor!=self.s.config()['controller']:raise Forbidden('controller required')
        text(reason,1000)
        with self.s.tx():
            old=self.s.row('memory_items',memory)
            if old['state']=='archived':return {'memory':memory,'duplicate':True}
            if old['state']!='active':raise Conflict('only active memory can be archived')
            self.s.db.execute("UPDATE memory_items SET state='archived' WHERE id=? AND instance_id=?",(memory,self.s.instance_id))
            self.s.event('memory.archived',payload={'memory':memory,'revision':old['current_revision_id'],'authority':actor,'reason':reason,'content_preserved':True},lane='control')
            from digital_life.application.memory.memory_quality import MemoryQuality
            MemoryQuality(self.s).dirty(memory)
            return {'memory':memory,'state':'archived','content_preserved':True}
    def redact(self,memory,actor):
        if actor!=self.s.config()['controller']: raise Forbidden('controller required')
        with self.s.tx():
            self.s.row('memory_items',memory)
            request=self.s.insert('deletion_requests',subject_scope={'memory':memory},requested_at=utc(),authority_ref=actor,state='cleaning')
            for row in self.s.db.execute('SELECT id FROM memory_revisions WHERE memory_id=?',(memory,)).fetchall():
                self.s.insert('deletion_effects',request_id=request,object_ref=row[0],operation='redact',result='pending')
                self.s.db.execute("UPDATE memory_revisions SET content='[redacted]' WHERE id=?",(row[0],))
            self.s.db.execute("UPDATE memory_items SET state='deleted' WHERE id=?",(memory,))
            # Keep cleaning: request/response artifacts, backups and derived summaries need dependency traversal.
            from digital_life.application.memory.memory_quality import MemoryQuality
            MemoryQuality(self.s).dirty(memory)
            self.s.event('memory.redacted',payload={'memory_id':memory,'request_id':request,'complete_erasure':False},lane='control')
            return request

