"""Source-bound extractive consolidation and measurable bounded lexical retrieval."""
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,text,dumps,sha,identifier
from digital_life.infrastructure.processes.dispatch_gate import coordinated

VERSION='memory-quality-v1'
INDEX='memory-quality-index.sqlite'
DEPENDENCIES=('derived_from','summary_of','consolidated_from')


def terms(value):
    value=value.casefold();words=set(re.findall(r'[a-z0-9_]+',value));grams={s[i:i+2] for s in re.findall(r'[\u4e00-\u9fff]+',value) for i in range(len(s)-1)}
    return words,grams


class MemoryQuality:
    def __init__(self,store):self.s=store;self.last_recent=[]
    def authority(self,actor):
        if actor!=self.s.config()['controller']:raise Forbidden('controller required')
    def events(self,kind):
        result=[]
        for row in self.s.db.execute('SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type=? ORDER BY event_seq',(self.s.instance_id,'memory_quality.'+kind)):
            value=self.s.read_artifact(row[1])
            if isinstance(value,dict) and 'redacted_by' not in value:result.append(dict(value,id=row[0]))
        return result
    def config(self):
        row=self.s.db.execute("SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type='memory_quality.configured' ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,)).fetchone()
        value=self.s.read_artifact(row[1]) if row else {}
        return {'enabled':bool(value.get('enabled',False)),'id':row[0] if row else None,'version':VERSION}
    def active(self):
        cfg=self.config()
        if not cfg['enabled']:raise Forbidden('memory quality disabled')
        return cfg
    @coordinated
    def configure(self,enabled,actor):
        self.authority(actor)
        if type(enabled) is not bool:raise ContractError('boolean required')
        from digital_life.application.lifecycle.control_plane import Control
        c=Control(self.s.root,self.s.instance_id)
        try:
            state=c.state()
            if not state['user_stopped'] or state['active_process_run_id']:raise Conflict('stop before memory quality configuration')
        finally:c.close()
        with self.s.tx():self.s.event('memory_quality.configured',payload={'enabled':enabled,'actor':actor,'version':VERSION},lane='control')
        return self.config()
    def dirty(self,memory):
        if self.config()['enabled']:self.s.event('memory_quality.source_changed',payload_object_id=memory,lane='control')
    def watermark(self):
        row=self.s.db.execute("SELECT id FROM runtime_events WHERE instance_id=? AND event_type='memory_quality.source_changed' ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,)).fetchone()
        return sha(dumps([self.config()['id'],row[0] if row else '']))
    @staticmethod
    def drop_index(root):
        for suffix in ('','-wal','-shm','-journal'):
            path=Path(root)/(INDEX+suffix)
            if path.is_symlink():raise Forbidden('index symlink denied')
            path.unlink(missing_ok=True)
    def _index(self):
        path=self.s.root/INDEX
        if any((self.s.root/(INDEX+suffix)).is_symlink() for suffix in ('','-wal','-shm','-journal')):raise Forbidden('index symlink denied')
        c=sqlite3.connect(str(path));c.row_factory=sqlite3.Row
        try:c.executescript('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS docs(revision TEXT PRIMARY KEY,memory TEXT,ordinal INTEGER,hash TEXT); CREATE TABLE IF NOT EXISTS postings(token TEXT,revision TEXT,PRIMARY KEY(token,revision));')
        except Exception:
            c.close();raise
        return c
    def _tokens(self,content):
        words,grams=terms(content);tokens={sha('w:'+w) for w in words}|{sha('c:'+g) for g in grams}
        if re.search(r'我(?:是|叫)|我的名字|称呼我|父亲|母亲',content):tokens.add(sha('a:autobiographic'))
        return tokens
    def build(self):
        c=self._index()
        try:
            with c:
                c.execute('DELETE FROM postings');c.execute('DELETE FROM docs')
                for row in self.s.db.execute("SELECT r.*,r.rowid AS ordinal FROM memory_revisions r JOIN memory_items m ON m.current_revision_id=r.id AND m.instance_id=r.instance_id WHERE r.instance_id=? AND m.state='active'",(self.s.instance_id,)):
                    c.execute('INSERT INTO docs VALUES(?,?,?,?)',(row['id'],row['memory_id'],row['ordinal'],sha(row['content'])))
                    c.executemany('INSERT INTO postings VALUES(?,?)',((token,row['id']) for token in self._tokens(row['content'])))
                self.stamp(c)
            return {'indexed':c.execute('SELECT count(*) FROM docs').fetchone()[0],'watermark':self.watermark()}
        finally:c.close()
    def stamp(self,c):
        row=self.s.db.execute("SELECT id,event_seq FROM runtime_events WHERE instance_id=? AND event_type='memory_quality.source_changed' ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,)).fetchone()
        for key,value in (('watermark',self.watermark()),('instance',self.s.instance_id),('version',VERSION),('configuration',self.config()['id'] or ''),('source_ref',row[0] if row else ''),('source_seq',str(row[1]) if row else '0')):
            c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,value))
    def synchronize(self,c,meta):
        if meta.get('instance')!=self.s.instance_id or meta.get('version')!=VERSION or meta.get('configuration')!=(self.config()['id'] or ''):return None
        previous=meta.get('source_ref','');seq=int(meta.get('source_seq','0'))
        if previous and not self.s.db.execute("SELECT 1 FROM runtime_events WHERE instance_id=? AND id=? AND event_seq=? AND event_type='memory_quality.source_changed'",(self.s.instance_id,previous,seq)).fetchone():return None
        changed={r[0] for r in self.s.db.execute("SELECT payload_object_id FROM runtime_events WHERE instance_id=? AND event_seq>? AND event_type='memory_quality.source_changed'",(self.s.instance_id,seq))}
        with c:
            for memory in changed:
                c.execute('DELETE FROM postings WHERE revision IN (SELECT revision FROM docs WHERE memory=?)',(memory,));c.execute('DELETE FROM docs WHERE memory=?',(memory,))
                row=self.s.db.execute("SELECT r.*,r.rowid AS ordinal FROM memory_revisions r JOIN memory_items m ON m.current_revision_id=r.id AND m.instance_id=r.instance_id WHERE r.instance_id=? AND m.id=? AND m.state='active'",(self.s.instance_id,memory)).fetchone()
                if row:
                    c.execute('INSERT INTO docs VALUES(?,?,?,?)',(row['id'],memory,row['ordinal'],sha(row['content'])))
                    c.executemany('INSERT INTO postings VALUES(?,?)',((token,row['id']) for token in self._tokens(row['content'])))
            self.stamp(c)
        return len(changed)
    @coordinated
    def rebuild(self,actor):
        self.authority(actor);self.active()
        with self.s.tx():return self.build()
    def candidates(self,query):
        if not self.config()['enabled']:return None,None
        words,grams=terms(query);weighted={sha('w:'+w):8. for w in words};weighted.update({sha('c:'+g):.5 for g in grams})
        if re.search(r'记忆|记得|认识|是谁|名字|哪些人',query):weighted[sha('a:autobiographic')]=4.
        if len(weighted)>128:return None,{'mode':'scan-fallback','reason':'query-token-budget'}
        started=time.perf_counter();rebuilt=False;updated=0;c=None
        try:
            c=self._index();meta=dict(c.execute('SELECT key,value FROM meta'))
            if meta.get('watermark')!=self.watermark() or meta.get('instance')!=self.s.instance_id or meta.get('version')!=VERSION:
                updated=self.synchronize(c,meta)
                if updated is None:
                    c.close();c=None;self.build();rebuilt=True;updated=0;c=self._index()
            count=c.execute('SELECT count(*) FROM docs').fetchone()[0];ranked=[]
            if weighted:
                sql='WITH q(token,weight) AS (VALUES '+','.join('(?,?)' for _ in weighted)+') SELECT p.revision,sum(q.weight) score FROM q JOIN postings p ON p.token=q.token JOIN docs d ON d.revision=p.revision GROUP BY p.revision ORDER BY score DESC,d.ordinal DESC LIMIT 2001'
                ranked=[r[0] for r in c.execute(sql,tuple(x for pair in weighted.items() for x in pair))]
            truncated=len(ranked)>2000;ranked=ranked[:2000];self.last_recent=[r[0] for r in c.execute('SELECT revision FROM docs ORDER BY ordinal DESC LIMIT 8')]
            ids=list(dict.fromkeys(ranked+self.last_recent))
            return ids,{'mode':'hashed-token-index','indexed':count,'candidate_count':len(ids),'candidate_truncated':truncated,'rebuilt':rebuilt,'synced':updated>0,'updated_memories':updated,'index_ms':(time.perf_counter()-started)*1000}
        except (sqlite3.Error,OSError,ContractError,ValueError,TypeError) as error:return None,{'mode':'scan-fallback','reason':type(error).__name__}
        finally:
            if c is not None:c.close()
    def load_rows(self,ids):
        rows=[]
        for start in range(0,len(ids),400):
            chunk=ids[start:start+400]
            rows.extend(self.s.db.execute("SELECT r.*,m.salience,r.rowid AS ordinal FROM memory_revisions r JOIN memory_items m ON m.current_revision_id=r.id AND m.instance_id=r.instance_id WHERE r.instance_id=? AND m.state='active' AND r.id IN ("+','.join('?' for _ in chunk)+')',(self.s.instance_id,*chunk)).fetchall())
        return sorted(rows,key=lambda r:r['ordinal'],reverse=True)
    def capture(self,memory,parents):
        sources=[{'memory':p,'revision':self.s.row('memory_items',p)['current_revision_id']} for p in dict.fromkeys(parents)]
        self.s.event('memory.dependencies',payload={'memory':memory,'parents':sources},source='memory-dependencies',key=memory,lane='control')
    def dependencies(self,memory):
        row=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type='memory.dependencies' AND source='memory-dependencies' AND source_event_id=? ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,memory)).fetchone()
        if not row:return None
        value=self.s.read_artifact(row[0]);return value.get('parents',[]) if isinstance(value,dict) and 'redacted_by' not in value else []
    def link_response(self,memory,result):
        from digital_life.application.accounts.account_scope import active
        if not self.config()['enabled'] and not active(self.s):return
        row=self.s.row('thought_results',result);req=self.s.row('thought_requests',row['request_id']);payload=__import__('digital_life.application.learning.contexts',fromlist=['unwrapped_request_payload']).unwrapped_request_payload(self.s,req)
        if not isinstance(payload,dict) or 'redacted_by' in payload:return
        parents=[]
        for item in payload.get('selected_memories',[]):
            revision=self.s.row('memory_revisions',item['revision_id']);parents.append({'memory':revision['memory_id'],'revision':revision['id']})
        activity=self.s.row('activities',req['activity_id'])
        for r in self.s.db.execute('SELECT r.memory_id,r.id FROM memory_source_links l JOIN evidence_items e ON e.id=l.evidence_id AND e.instance_id=l.instance_id JOIN memory_revisions r ON r.id=l.memory_revision_id AND r.instance_id=l.instance_id WHERE l.instance_id=? AND e.origin_object_id=?',(self.s.instance_id,activity['trigger_event_id'])):parents.append({'memory':r[0],'revision':r[1]})
        from digital_life.application.services.memory import Memory
        evidence=self.s.evidence(object_id=result,method='conservative-response-dependency')
        for parent in parents:
            if parent['memory']==memory:continue
            self.s.insert('memory_relations',from_memory_id=memory,to_memory_id=parent['memory'],relation_type='derived_from',evidence_id=evidence)
        if parents:
            self.s.event('memory.dependencies',payload={'memory':memory,'parents':parents},source='memory-dependencies',key=memory,lane='control')
            self.dirty(memory)
    def available(self,memory,actor):
        from digital_life.application.services.memory import Memory
        row=self.s.row('memory_items',memory)
        return row['state']=='active' and actor in Memory(self.s).readers(memory)
    def parts(self,parts,actor):
        from digital_life.application.learning.runtime import strict_legacy_boundary
        strict_legacy_boundary(self.s,'legacy_memory_quality_material')
        if not isinstance(parts,list) or not 2<=len(parts)<=20:raise ContractError('two to twenty source spans required')
        content=[];sources=[]
        for part in parts:
            if not isinstance(part,dict) or set(part)!={'revision','start','end'}:raise ContractError('revision and exact source offsets required')
            text(part['revision'],200)
            row=self.s.row('memory_revisions',part['revision']);item=self.s.row('memory_items',row['memory_id'])
            if not self.available(item['id'],actor) or item['current_revision_id']!=row['id']:raise Conflict('consolidation source stale or unreadable')
            if type(part['start']) is not int or type(part['end']) is not int or not 0<=part['start']<part['end']<=len(row['content']):raise ContractError('invalid character range')
            content.append(row['content'][part['start']:part['end']]);sources.append({'memory':item['id'],'revision':row['id'],'hash':sha(row['content'])})
        if len({s['memory'] for s in sources})<2:raise ContractError('multiple distinct source memories required')
        value='\n'.join(content);text(value,8000);return value,sources
    @coordinated
    def plan(self,parts,key,actor):
        self.authority(actor);self.active();text(key,200)
        with self.s.tx():
            old=next((e for e in self.events('planned') if e['key']==key),None)
            if old:
                if old['parts']!=parts:raise Conflict('consolidation key reused')
                return old
            value,sources=self.parts(parts,actor)
            ref=self.s.event('memory_quality.planned',payload={'parts':parts,'sources':sources,'content_hash':sha(value),'key':key,'configuration':self.config()['id'],'method':VERSION},lane='control')
        return next(e for e in self.events('planned') if e['id']==ref)
    def preview(self,plan,actor):
        self.authority(actor);cfg=self.active();proposed=next((e for e in self.events('planned') if e['id']==plan),None)
        if not proposed or proposed['configuration']!=cfg['id']:raise Conflict('consolidation plan missing or superseded')
        content,sources=self.parts(proposed['parts'],actor)
        if sources!=proposed['sources'] or sha(content)!=proposed['content_hash']:raise Conflict('consolidation source changed')
        return {'plan':plan,'content':content,'sources':sources,'source_kind':'extractive-summary','persisted_preview':False,'inference_started':False}
    @coordinated
    def commit(self,plan,actor):
        self.authority(actor);cfg=self.active()
        with self.s.tx():
            old=next((e for e in self.events('committed') if e['plan']==plan),None)
            if old:return old
            proposed=next((e for e in self.events('planned') if e['id']==plan),None)
            if not proposed or proposed['configuration']!=cfg['id']:raise Conflict('consolidation plan missing or superseded')
            content,sources=self.parts(proposed['parts'],actor)
            if sources!=proposed['sources'] or sha(content)!=proposed['content_hash']:raise Conflict('consolidation source changed')
            from digital_life.application.services.memory import Memory
            evidence=self.s.evidence(object_id=plan,method='reviewed-extractive-spans')
            result=Memory(self.s).derive(content,list(dict.fromkeys(s['memory'] for s in sources)),evidence,actor,encoding_method='extractive-consolidation-v1')
            ref=self.s.event('memory_quality.committed',payload=dict(result,plan=plan,sources=sources,method=VERSION),lane='control')
        return next(e for e in self.events('committed') if e['id']==ref)
    def retention_revision(self,memory):
        row=self.s.row('memory_items',memory);events=[e for e in self.events('retained') if e['memory']==memory]
        return sha(dumps([row['current_revision_id'],row['state'],row['salience'],events[-1]['id'] if events else None]))
    @coordinated
    def retain(self,memory,operation,expected_revision,key,reason,actor,salience=.1):
        self.authority(actor);self.active();text(key,200);text(reason,2000)
        if operation not in ('demote','archive','retract','restore'):raise ContractError('unknown retention operation')
        with self.s.tx():
            arguments={'memory':memory,'operation':operation,'expected_revision':expected_revision,'key':key,'reason':reason,'salience':salience}
            old=next((e for e in self.events('retained') if e['key']==key),None)
            if old:
                if old['arguments']!=arguments:raise Conflict('retention key reused')
                return old
            row=self.s.row('memory_items',memory)
            from digital_life.application.services.memory import Memory
            if actor not in Memory(self.s).readers(memory) or row['state']=='deleted':raise Forbidden('memory unavailable for retention')
            if self.retention_revision(memory)!=expected_revision:raise Conflict('memory retention state changed')
            if operation=='demote':
                if isinstance(salience,bool) or not isinstance(salience,(int,float)) or not math.isfinite(salience) or not 0<=salience<=row['salience']:raise ContractError('salience must decrease within [0,1]')
                self.s.db.execute('UPDATE memory_items SET salience=? WHERE id=?',(salience,memory))
            else:self.s.db.execute('UPDATE memory_items SET state=? WHERE id=?',({'archive':'archived','retract':'retracted','restore':'active'}[operation],memory))
            ref=self.s.event('memory_quality.retained',payload={'memory':memory,'arguments':arguments,'key':key,'before':{'state':row['state'],'salience':row['salience']}},lane='control');self.dirty(memory)
        return next(e for e in self.events('retained') if e['id']==ref)
    @coordinated
    def conflict(self,left,right,evidence,reason,key,actor):
        self.authority(actor);self.active();text(reason,2000);text(key,200)
        from digital_life.application.behavior.people_relations import PeopleRelations
        PeopleRelations(self.s).evidence(evidence)
        with self.s.tx():
            args={'left':left,'right':right,'evidence':evidence,'reason':reason,'key':key};old=next((e for e in self.events('conflicted') if e['key']==key),None)
            if old:
                if old['arguments']!=args:raise Conflict('conflict key reused')
                return old
            a=self.s.row('memory_revisions',left);b=self.s.row('memory_revisions',right)
            if a['memory_id']==b['memory_id'] or not all(self.available(r['memory_id'],actor) and self.s.row('memory_items',r['memory_id'])['current_revision_id']==r['id'] for r in (a,b)):raise Conflict('two distinct current readable memories required')
            self.s.insert('memory_relations',from_memory_id=a['memory_id'],to_memory_id=b['memory_id'],relation_type='contradicts',evidence_id=evidence[0])
            ref=self.s.event('memory_quality.conflicted',payload=dict(args,arguments=args),lane='control')
        return next(e for e in self.events('conflicted') if e['id']==ref)
    def annotations(self,revision,actor):
        related={revision};frontier=[revision]
        for _ in range(64):
            next_frontier=[]
            for current in frontier:
                memory=self.s.row('memory_revisions',current)['memory_id']
                for row in self.s.db.execute("SELECT to_memory_id FROM memory_relations WHERE instance_id=? AND from_memory_id=? AND relation_type IN ('derived_from','summary_of','consolidated_from')",(self.s.instance_id,memory)):
                    parent=self.s.row('memory_items',row[0])
                    if parent['current_revision_id'] not in related and self.available(parent['id'],actor):related.add(parent['current_revision_id']);next_frontier.append(parent['current_revision_id'])
            frontier=next_frontier
            if not frontier:break
        result=[]
        from digital_life.application.behavior.people_relations import PeopleRelations
        for e in self.events('conflicted'):
            if not related.intersection((e['left'],e['right'])):continue
            try:
                PeopleRelations(self.s).evidence(e['evidence'])
                rows=[self.s.row('memory_revisions',e[key]) for key in ('left','right')]
                if all(self.available(r['memory_id'],actor) and self.s.row('memory_items',r['memory_id'])['current_revision_id']==r['id'] for r in rows):result.append({'assertion':e['id'],'left':e['left'],'right':e['right'],'reason':e['reason'],'evidence':e['evidence'],'status':'controller-labelled-unresolved'})
            except (ContractError,OSError):continue
        return result
    def selected(self,items):
        result=[];actor=self.s.config()['self_actor']
        for item in items:
            row=self.s.row('memory_revisions',item['revision_id']);memory=self.s.row('memory_items',row['memory_id'])
            result.append({'revision':row['id'],'memory':memory['id'],'content_hash':sha(row['content']),'salience':memory['salience'],'parents':self.dependencies(memory['id']),'conflicts':self.annotations(row['id'],actor)})
        return result
    def context(self,items,diagnostics):
        cfg=self.config()
        if not cfg['enabled']:return None
        return {'configuration':cfg['id'],'method':VERSION,'selected':self.selected(items),'retrieval':diagnostics,'scope':'retrieval quality and source provenance, not fact truth'}
    def check(self,payload):
        actor=self.s.config()['self_actor'];items=payload.get('selected_memories',[])
        for item in items:
            row=self.s.row('memory_revisions',item['revision_id']);m=self.s.row('memory_items',row['memory_id'])
            if m['current_revision_id']!=row['id'] or not self.available(m['id'],actor) or row['content']!=item['content']:raise Forbidden('selected memory stale, withdrawn or source unavailable')
        cfg=self.config();pinned=payload.get('memory_quality')
        if not cfg['enabled'] and pinned is None:return
        if not pinned or not cfg['enabled'] or pinned['configuration']!=cfg['id'] or pinned['selected']!=self.selected(items):raise Forbidden('memory quality context superseded')
    @coordinated
    def evaluate(self,cases,actor,k=5):
        self.authority(actor);self.active()
        if type(k) is not int or not 1<=k<=50 or not isinstance(cases,list) or not 2<=len(cases)<=100:raise ContractError('two to 100 cases and bounded k required')
        if any(not isinstance(c,dict) or set(c)!={'query','relevant'} for c in cases):raise ContractError('query and relevant memory IDs required')
        for case in cases:text(case['query'],4000)
        if len({c['query'] for c in cases})!=len(cases):raise ContractError('distinct queries required')
        for c in cases:
            text(c['query'],4000)
            if not isinstance(c['relevant'],list) or not c['relevant'] or not all(isinstance(m,str) for m in c['relevant']) or len(set(c['relevant']))!=len(c['relevant']) or not all(self.available(m,self.s.config()['self_actor']) for m in c['relevant']):raise ContractError('current readable relevance labels required')
        from digital_life.application.runtime.engine import Engine
        from digital_life.application.services.memory import Memory
        from digital_life.application.telemetry.metrics import reduce_samples
        with self.s.tx():
            a=Engine(self.s).submit('isolated memory retrieval evaluation',identifier(),'evaluation');context=Engine(self.s).details(a)[1]['id'];results=[]
            for case in cases:
                started=time.perf_counter();recalled=Memory(self.s).retrieve(case['query'],a,context,k);ranked=[self.s.row('memory_revisions',r['revision_id'])['memory_id'] for r in recalled['items']]
                record={'ranked':ranked,'relevant':case['relevant'],'k':k};metrics={name:reduce_samples(name,[record])[0] for name in ('precision','recall','mrr','ndcg')}
                results.append({'query':case['query'],'ranked':ranked,'relevant':case['relevant'],'metrics':metrics,'elapsed_ms':(time.perf_counter()-started)*1000,'retrieval':recalled.get('quality')})
            report={'cases':results,'mean':{name:sum(r['metrics'][name] for r in results)/len(results) for name in ('precision','recall','mrr','ndcg')},'model_calls':0,'tools_executed':0,'scope':'manual finite relevance labels; not semantic generalization'}
            self.s.event('memory_quality.evaluated',payload=report,lane='control')
        return report
    def status(self,memory=None):
        from digital_life.application.learning.runtime import strict_legacy_boundary
        strict_legacy_boundary(self.s,'legacy_memory_quality_material')
        ids=[memory] if memory else [r[0] for r in self.s.db.execute('SELECT id FROM memory_items WHERE instance_id=? ORDER BY rowid DESC LIMIT 20',(self.s.instance_id,))]
        return {'configuration':self.config(),'memories':[dict(self.s.row('memory_items',m),retention_revision=self.retention_revision(m),available_to_self=self.available(m,self.s.config()['self_actor']),parents=self.dependencies(m)) for m in ids],'index_exists':(self.s.root/INDEX).is_file(),'plans':self.events('planned'),'inference_started':False}
