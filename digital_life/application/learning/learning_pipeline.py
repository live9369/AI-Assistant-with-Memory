"""Controller feedback -> isolated retrieval trial -> reviewed CAS update -> compensation."""
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,dumps,sha,text,utc
from digital_life.application.services.learning import Learning
from digital_life.application.services.memory import Memory
from digital_life.infrastructure.processes.dispatch_gate import coordinated

class LearningPipeline:
 def __init__(self,store):self.s=store
 def authority(self,actor):
  if actor!=self.s.config()['controller']:raise Forbidden('controller required')
 @coordinated
 def feedback(self,memory,new_content,reason,actor):
  self.authority(actor);text(new_content);text(reason,4000)
  with self.s.tx():
   item=self.s.row('memory_items',memory)
   if item['state']!='active':raise Forbidden('inactive memory')
   old=self.s.row('memory_revisions',item['current_revision_id'])
   event=self.s.event('learning.explicit_feedback',payload={'memory':memory,'reason':reason,'actor':actor},lane='control');evidence=self.s.evidence(object_id=event,method='controller-feedback')
   change={'content':new_content,'expected_revision':old['revision_no'],'expected_revision_id':old['id'],'old_content_hash':sha(old['content']),'feedback_event':event}
   proposal=Learning(self.s).propose('memory',memory,change,evidence,risk=.25)
   return {'proposal':proposal,'evidence':evidence,'state':'proposed','adopted':False}
 def _trial(self,folder,memory,new_content,cases,evidence):
  from digital_life.infrastructure.persistence.sqlite_store import Store
  from digital_life.application.runtime.engine import Engine
  store=Store(folder)
  try:
   if new_content is not None:
    item=store.row('memory_items',memory);old=store.row('memory_revisions',item['current_revision_id']);Memory(store).revise(memory,old['revision_no'],new_content,evidence)
   results=[]
   for i,case in enumerate(cases):
    activity=Engine(store).submit(case['query'],'learning-trial-'+str(i),'evaluation');context=Engine(store).details(activity)[1]['id']
    recalled=Memory(store).retrieve(case['query'],activity,context)['items'];contents='\n'.join(r['content'] for r in recalled)
    passed=case['contains'] in contents and (not case['not_contains'] or case['not_contains'] not in contents)
    results.append({'query':case['query'],'passed':passed,'revisions':[r['revision_id'] for r in recalled]})
   return results
  finally:store.close()
 @coordinated
 def evaluate(self,proposal,cases,actor):
  self.authority(actor)
  if not isinstance(cases,list) or not 2<=len(cases)<=20:raise ContractError('two to twenty evaluation cases required')
  for case in cases:
   if not isinstance(case,dict) or set(case)!={'query','contains','not_contains'}:raise ContractError('invalid evaluation case')
   text(case['query'],1000);text(case['contains'],4000)
   if not isinstance(case['not_contains'],str) or len(case['not_contains'])>4000:raise ContractError('invalid negative condition')
  if len({case['query'] for case in cases})!=len(cases):raise ContractError('distinct evaluation questions required')
  p=self.s.row('learning_update_proposals',proposal);change=json.loads(p['proposed_change']);item=self.s.row('memory_items',p['target_object_id'])
  if p['owner_module']!='memory' or p['state']!='proposed' or item['current_revision_id']!=change['expected_revision_id']:raise Conflict('proposal consumed or target changed')
  evidence=self.s.db.execute('SELECT evidence_id FROM learning_proposal_evidence WHERE proposal_id=? LIMIT 1',(proposal,)).fetchone()[0]
  with tempfile.TemporaryDirectory(prefix='life-learning-') as tmp:
   root=Path(tmp);frozen=root/'frozen';frozen.mkdir();(frozen/'workspace').mkdir();(frozen/'blobs').mkdir();(frozen/'WAKE_DISABLED').write_text('offline evaluation only\n')
   reader=sqlite3.connect((self.s.root/'runtime.sqlite').as_uri()+'?mode=ro',uri=True);dest=sqlite3.connect(str(frozen/'runtime.sqlite'))
   try:reader.backup(dest)
   finally:dest.close();reader.close()
   baseline_hash=sha((frozen/'runtime.sqlite').read_bytes())
   db=sqlite3.connect(str(frozen/'runtime.sqlite'))
   try:
    for ref,storage,digest in db.execute('SELECT id,storage_ref,hash FROM artifacts'):
     source=self.s.root/'blobs'/storage
     if source.is_symlink() or source.parent!=self.s.root/'blobs':raise Forbidden('invalid artifact path')
     raw=source.read_bytes()
     if sha(raw)!=digest:raise ContractError('artifact changed during trial')
     (frozen/'blobs'/storage).write_bytes(raw)
   finally:db.close()
   candidate=root/'candidate';shutil.copytree(frozen,candidate)
   before=self._trial(frozen,item['id'],None,cases,evidence);after=self._trial(candidate,item['id'],change['content'],cases,evidence)
  benefit=(sum(x['passed'] for x in after)-sum(x['passed'] for x in before))/len(cases)
  regression=sum(a['passed'] and not b['passed'] for a,b in zip(before,after))/len(cases)
  with self.s.tx():
   # CAS again after isolated work; no stale candidate may become eligible.
   if self.s.row('memory_items',item['id'])['current_revision_id']!=change['expected_revision_id']:raise Conflict('target changed during trial')
   artifact=self.s.artifact({'cases':cases,'before':before,'after':after,'frozen_database_hash':baseline_hash,'model_calls':0,'tools_executed':0})
   trial=Learning(self.s).trial(proposal,'memory-recall-controlled-v1',{'measurement_artifact':artifact,'method':'two isolated database variants'})
   self.s.db.execute("UPDATE evaluation_runs SET state='completed' WHERE id=?",(trial['evaluation'],))
   evaluation=Learning(self.s).evaluate(trial['trial'],trial['evaluation'],benefit,regression)
   self.s.db.execute('UPDATE learning_update_trials SET ended_at=? WHERE id=?',(utc(),trial['trial']))
   if benefit<=0 or regression:self.s.db.execute("UPDATE learning_update_proposals SET state='rejected' WHERE id=?",(proposal,))
   self.s.event('learning.trial_measured',payload={'proposal':proposal,'evaluation':evaluation,'measurement':artifact,'benefit':benefit,'regression':regression},lane='control')
  return {'evaluation':evaluation,'benefit':benefit,'regression':regression,'eligible':benefit>0 and regression==0,'measurement':artifact,'adopted':False}
 @coordinated
 def commit(self,proposal,evaluation,actor):
  self.authority(actor)
  with self.s.tx():
   p=self.s.row('learning_update_proposals',proposal);ev=self.s.row('learning_update_evaluations',evaluation);trial=self.s.row('learning_update_trials',ev['trial_id'])
   if trial['proposal_id']!=proposal or trial['baseline_ref']!=ev['evaluation_run_id'] or ev['decision']!='accept' or p['state']!='trial' or p['owner_module']!='memory':raise Conflict('not an approved matching trial')
   run=self.s.row('evaluation_runs',ev['evaluation_run_id']);conditions=json.loads(run['conditions'])
   if run['state']!='completed' or run['dataset_version']!='memory-recall-controlled-v1' or 'measurement_artifact' not in conditions:raise Conflict('missing independent measurements')
   measured=self.s.read_artifact(conditions['measurement_artifact']);before=measured['before'];after=measured['after']
   benefit=(sum(x['passed'] for x in after)-sum(x['passed'] for x in before))/len(before);regression=sum(a['passed'] and not b['passed'] for a,b in zip(before,after))/len(before)
   if benefit<=0 or regression or benefit!=ev['benefit'] or regression!=ev['regression']:raise Conflict('measurement does not justify update')
   change=json.loads(p['proposed_change']);memory=self.s.row('memory_items',p['target_object_id'])
   if memory['state']!='active' or memory['current_revision_id']!=change['expected_revision_id']:raise Conflict('target revision changed')
   old=self.s.row('memory_revisions',memory['current_revision_id'])
   if sha(old['content'])!=change['old_content_hash']:raise Conflict('baseline mismatch')
   evidence=self.s.db.execute('SELECT evidence_id FROM learning_proposal_evidence WHERE proposal_id=? LIMIT 1',(proposal,)).fetchone()[0]
   new=Memory(self.s).revise(memory['id'],change['expected_revision'],change['content'],evidence)
   commit=self.s.insert('learning_update_commits',proposal_id=proposal,old_revision_id=old['id'],new_revision_id=new,committed_at=utc())
   self.s.db.execute("UPDATE learning_update_proposals SET state='accepted' WHERE id=?",(proposal,));self.s.event('learning.measured_update_committed',payload={'commit':commit,'evaluation':evaluation},lane='control');return commit
 @coordinated
 def rollback(self,commit,evidence_refs,actor):
  self.authority(actor)
  origins={self.s.row('evidence_items',ref)['origin_object_id'] for ref in evidence_refs}
  if None in origins or len(origins)<2:raise ContractError('two distinct evidence origins required')
  with self.s.tx():
   original=self.s.row('learning_update_commits',commit)
   reversal=Learning(self.s).rollback(commit,evidence_refs,actor)
   self.s.db.execute("UPDATE learning_update_proposals SET state='reverted' WHERE id=?",(original['proposal_id'],))
   return reversal
