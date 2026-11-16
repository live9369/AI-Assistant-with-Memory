"""Frozen pre-queue-optimization algorithm, differential tests only; no runtime authority."""
from copy import deepcopy
from digital_life.domain.contracts import ContractError,Forbidden
from digital_life.application.learning.eligibility import scope_key

def reference_upstream(self,token,scope,scan_budget):
    result=[(token["object"]["id"],deepcopy(scope),None,())];seen=set();index=0;scanned=0
    while index<len(result):
        key,sc,expected,path=result[index];index+=1
        selected=token if expected is None else expected
        identity=(key,selected['revision'],scope_key(sc),'delete' in path)
        if identity in seen:continue
        seen.add(identity)
        if len(seen)>self.max_nodes:raise Forbidden('upstream dependency scan limit exceeded')
        consumer=key
        from digital_life.domain.tool_learning_sources import SNAPSHOT_KINDS
        bridge=selected['object']['kind'] in SNAPSHOT_KINDS and self.s.db.execute("SELECT 1 FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=? AND kind='runtime_events'",(self.s.instance_id,key,selected['revision'])).fetchone()
        if selected['object']['kind'] in ('tl_content','tl_representation_head') or bridge:
            revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.s.instance_id,key,selected['revision'])).fetchone()
            if revision is None:raise ContractError('selected native revision unavailable')
            consumer=revision[0]
        for row in self.s.db.execute('SELECT * FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? ORDER BY id LIMIT ?',(self.s.instance_id,consumer,self.max_rows-scanned+1)):
            scanned+=1;scan_budget['remaining']-=1
            if scanned>self.max_rows or scan_budget['remaining']<0:raise Forbidden('upstream row scan limit exceeded')
            meta=self._metadata(row)
            edge=(row['source_ref_id'],meta['scope'],meta['dependency']['expected'],path+(row['relation'],))
            if (edge[0],edge[2]['revision'],scope_key(edge[1]),'delete' in edge[3]) not in seen:result.append(edge)
            if len(result)>self.max_nodes*2:raise Forbidden('upstream edge scan limit exceeded')
    return result
