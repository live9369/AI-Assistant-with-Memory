"""F2 owner acknowledgements and bounded, journal-first managed erasure.

No production authority is inferred from request JSON. No instance is opened,
restored, awakened or migrated by this module. Restore callers must explicitly
consume the external exclusion ledger; it is not an automatic restore hook.
"""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import hashlib
import os
import stat
import time

from digital_life.domain.contracts import ContractError, Conflict, Forbidden, dumps, identifier, utc
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.application.learning.eligibility import ref, slot
from digital_life.application.learning.invalidation import DOMAINS
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore, StorageAuthority
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate


RETAINED_METADATA=frozenset(('opaque_ids','control_scope','source_fingerprints','plan_expected_hashes','resource_facts','action_facts'))

def _control_row(store,sql,args):
    from digital_life.infrastructure.persistence.tool_learning_meter import external_read_before,external_read_after
    external_read_before(0)
    row=store.control_reader().execute(sql,args).fetchone()
    if row is not None:external_read_after(len(dumps(dict(row)).encode()))
    return row

def _attested(value):
    if value is not None:raise Forbidden('a trusted owner must attest by None, never a caller boolean')


class PropagationAuthority(StorageAuthority):
    def verify_propagation(self,entry,request,row,barrier,stage):
        raise Forbidden('current actual domain propagation authority is not configured')
    def apply_actions(self,transaction,entry,request,row,minimum,verification):
        raise Forbidden('actual owned propagation action adapter is not configured')
    def verify_actions(self,entry,request,row,minimum,verification,stage):
        raise Forbidden('actual domain actions and coverage verification are not configured')
    def verify_maintenance(self,entry,plan,stage):
        raise Forbidden('current M12 maintenance grant is not configured')
    def verify_inventory(self,entry,plan,stage):
        raise Forbidden('explicit cleanup boundary, full target inventory and retention permission are not configured')
    def verify_origin_work(self,entry,plan,obligation,work):
        raise Forbidden('actual protective F1/source-work provenance owner is not configured')
    def initial_usage(self,entry,plan):
        raise Forbidden('actual initial maintenance review accounting is not configured')
    def verify_exclusion_index(self,entry,plan,directory,index,stage):
        raise Forbidden('current external exclusion-root/head registration is not configured')
    def record_exclusion_index(self,entry,plan,directory,index):
        raise Forbidden('current exclusion head owner is not configured')
    def current_restore_exclusions(self,entry,instance_id,max_records,max_bytes):
        raise Forbidden('current protective control exclusion owner is not configured')
    def verify_restore(self,entry,instance_id,stage):
        raise Forbidden('current external restore exclusion authority is not configured')
    def verify_target(self,entry,plan,target,stage):
        raise Forbidden('actual target owner and physical scope are not configured')


class _Storage(StorageAuthority):
    def __init__(self,service):self.service=service
    def verify(self,entry,operation,request,instance_id,stage):
        grant=self.service.authority.verify(entry,operation,deepcopy(request),instance_id,stage)
        self.service._guard(entry,request,stage)
        return grant
    def project_response(self,entry,operation,request,response,instance_id,stage):
        result=self.service.authority.project_response(entry,operation,deepcopy(request),response,instance_id,stage)
        self.service._guard(entry,request,stage)
        return result
    def verify_external_ref(self,*args):return self.service.authority.verify_external_ref(*args)


class ToolLearningPropagation:
    def __init__(self,store,authority=None,clock=utc,max_rows=4096,accounting=None):
        self.s=store;self.authority=authority or PropagationAuthority();self.clock=clock
        if not isinstance(self.authority,PropagationAuthority):raise ContractError('trusted PropagationAuthority required')
        t.integer(max_rows,1,65536);self.max_rows=max_rows
        self.storage=ToolLearningStore(store,_Storage(self));self.accounting=accounting

    def _row(self,request):
        p=request['payload'];self.storage.validate_ref(p['barrier'],expected_kind='tl_barrier')
        rows=self.s.db.execute('SELECT * FROM tl_propagation WHERE instance_id=? AND barrier_id=? AND domain=? AND generation=?',
            (self.s.instance_id,p['barrier']['id'],p['domain'],p['generation'])).fetchall()
        if len(rows)!=1:raise Conflict('exact propagation obligation/generation is unavailable')
        return dict(rows[0])

    def _guard(self,entry,request,stage):
        row=self._row(request);barrier=self.s.row('tl_barrier',row['barrier_id'])
        if request['principal']['module']!=row['domain']:raise Forbidden('one domain cannot acknowledge another owner')
        if request['control']['cancelled'] or self.clock()>=min(row['deadline'],request['budget']['deadline']):raise Forbidden('protective propagation cancelled or expired')
        budget=request['budget'];self.storage.validate_ref(budget['account_ref'],expected_kind='activity_budget_accounts')
        if budget['account_ref']['id']!=row['budget_account_id'] or budget['deadline']>row['deadline']:raise Forbidden('propagation cannot reset its account/deadline')
        account=self.s.row('activity_budget_accounts',row['budget_account_id'])
        if budget['max_input_tokens']+budget['max_output_tokens']>account['token_limit'] or budget['max_attempts']>account['attempt_limit'] or budget['max_tool_calls']>account['tool_call_limit']:raise Forbidden('F2 request exceeds its actual resource caps')
        activity=self.s.row('activities',account['activity_id'])
        if activity['cancel_requested_at'] or activity['state']=='cancelled':raise Forbidden('maintenance activity cancelled')
        if request['work_ref']['status']!='known':raise Forbidden('F2 needs its actual work binding')
        work=self.s.row('tl_work',request['work_ref']['value']['id'])
        if work['budget_account_id']!=row['budget_account_id']:
            maintenance=self.s.db.execute('SELECT * FROM deletion_requests WHERE instance_id=? AND id IN (SELECT request_id FROM deletion_effects WHERE instance_id=? AND object_ref=?)',(self.s.instance_id,self.s.instance_id,row['id'])).fetchall()
            found=False
            for record in maintenance:
                journal=c.loads(record['subject_scope'])
                binding=journal.get('generations',{}).get(row['id'])
                if binding and binding['original_work']==work['id'] and journal['account_id']==row['budget_account_id'] and journal['activity_id']==account['activity_id'] and journal['plan']['deadline']==row['deadline']:
                    _attested(self.authority.verify_maintenance(entry,deepcopy(journal['plan']),'F2_current_generation'))
                    if journal['unknown']:raise Forbidden('maintenance consumption is unresolved')
                    found=True
            if not found:raise Forbidden('F2 independent account lacks actual current maintenance generation binding')
        _attested(self.authority.verify_propagation(entry,deepcopy(request),row,barrier,stage))
        # Protective control writes remain legal under stop/WAKE_DISABLED. They
        # cannot grant ordinary execution and never change those controls.
        if self.clock()>=min(row['deadline'],budget['deadline']):raise Forbidden('propagation expired during current authority check')

    def acknowledge(self,entry,envelope):
        c.validate_request('acknowledge_propagation',envelope);request=c.loads(dumps(envelope))
        if self.s.db.in_transaction:raise Conflict('F2 needs an independent instance gate/transaction')
        with dispatch_gate(self.s.root):
            if not isinstance(self.accounting,MaintenanceReadAccounting):raise Forbidden('protective F2 has no actual maintenance accounting owner')
            with self.accounting.operation(entry,request,self._row(request)):
                return self.storage.execute(entry,'acknowledge_propagation',request,lambda tx:self._ack(tx,entry,request))

    def _ack(self,tx,entry,request):
        row=self._row(request);p=request['payload'];barrier=self.s.row('tl_barrier',row['barrier_id'])
        expected=request['expected']
        if expected['status']!='known' or expected['value']!={'object':ref(self.s,row['id'],'tl_propagation'),'revision':row['row_revision'],'epoch':row['generation']}:
            raise Conflict('F2 must bind the exact obligation CAS and generation')
        if row['state']=='verified':raise Conflict('verified obligation requires original-command replay')
        minimum=self.storage.read_artifact(row['targets_artifact_id'])
        self.storage.validate_ref(p['verification'],expected_kind='artifacts')
        verification=self.storage.read_artifact(p['verification']['id'])
        t.obj(verification,('contract','barrier','generation','domain','source_epoch','minimum_plan','targets','actions','coverage','boundary','watermark','unresolved','per_target'))
        if verification['contract']!='TL-PROPAGATION-VERIFICATION-1' or verification['barrier']!=p['barrier'] or verification['generation']!=row['generation'] or verification['domain']!=row['domain'] or verification['source_epoch']!=barrier['source_epoch'] or verification['minimum_plan']!=ref(self.s,row['targets_artifact_id'],'artifacts'):
            raise Conflict('verification is not bound to this reason/epoch/domain/minimum plan')
        for key in ('targets','actions','coverage'):
            if verification[key]!=p[key]:raise Conflict('F2 request and immutable verification differ')
        if len(p['targets'])+len(p['actions'])+len(verification['per_target'])>self.max_rows:raise Forbidden('F2 finite row bound exceeded')
        for item in verification['per_target']:
            t.obj(item,('target','action','verification'));self.storage.validate_ref(item['target']);self.storage.validate_ref(item['action']);self.storage.validate_ref(item['verification'])
            if item['action'] not in p['actions']:raise ContractError('target verification lacks its actual action binding')
        minimum_targets={dumps(r) for r in minimum['targets']}
        if not minimum_targets<={dumps(r) for r in p['targets']}:raise Conflict('F1 minimum targets were dropped')
        _attested(self.authority.apply_actions(tx,entry,deepcopy(request),row,minimum,deepcopy(verification)))
        _attested(self.authority.verify_actions(entry,deepcopy(request),row,minimum,deepcopy(verification),'execute'))
        complete=p['coverage']['state']=='complete' and not p['coverage']['truncated'] and not p['coverage']['missing'] and not verification['unresolved']
        if complete:
            if len(verification['per_target'])!=len(p['targets']) or not verification['boundary'] or not verification['watermark']:
                raise ContractError('complete coverage needs each actual target, boundary and watermark')
            if {dumps(x['target']) for x in verification['per_target']}!={dumps(r) for r in p['targets']}:
                raise ContractError('target verification set differs')
            _attested(self.authority.verify_actions(entry,deepcopy(request),row,minimum,deepcopy(verification),'verify'))
        if row['state']!='processing':
            tx.cas_update('tl_propagation',row['id'],row['row_revision'],state='processing');row['row_revision']+=1
        coverage=tx.put_artifact(p['coverage'],'Coverage')
        tx.cas_update('tl_propagation',row['id'],row['row_revision'],state='verified' if complete else 'blocked',coverage_artifact_id=coverage,verification_artifact_id=p['verification']['id'])
        self._guard(entry,request,'after_actions')
        return {'command_id':request['command_id'],'operation':'acknowledge_propagation','disposition':'applied','owner':p['domain'],
            'result_refs':[ref(self.s,row['id'],'tl_propagation')],'current':slot(),'reason':'none','error_code':'NONE','coverage':p['coverage'],
            'retry':{'allowed':False,'condition':slot(),'resume_work':slot()},'committed_at':slot(self.clock())}


class RestoreExclusions:
    """Actual external-to-runtime durable deny ledger, not a restore integration.

    The composition owner supplies a trusted directory outside runtime/backup
    roots. No self-signed caller receipt authorizes deletion or restoring.
    """
    def __init__(self,directory,runtime_root,authority):
        self.directory=Path(directory);self.runtime=Path(runtime_root).resolve();self.authority=authority
        if not isinstance(authority,PropagationAuthority):raise ContractError('trusted exclusion authority required')
        if self.directory.is_symlink():raise Forbidden('exclusion directory cannot be symlink')
        resolved=self.directory.resolve()
        if resolved==self.runtime or self.runtime in resolved.parents:raise Forbidden('exclusions must live outside the runtime image')

    def write(self,entry,plan):
        with dispatch_gate(self.runtime):
            _attested(self.authority.verify_maintenance(entry,deepcopy(plan),'exclusion_write'))
            self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
            with dispatch_gate(self.directory):return self._write(entry,plan)

    def _write(self,entry,plan):
        _attested(self.authority.verify_maintenance(entry,deepcopy(plan),'exclusion_write'))
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.directory.is_symlink():raise Forbidden('exclusion directory changed')
        value={'contract':'TL-RESTORE-EXCLUSION-1','instance_id':plan['instance_id'],'barrier_id':plan['barrier_id'],
            'plan_id':plan['id'],'source_epoch':plan['source_epoch'],'scope_id':plan['scope_id'],'recorded_at':plan['created_at']}
        for key in ('id','instance_id','barrier_id','scope_id'):c.validate('ID',plan[key])
        t.integer(plan['source_epoch']);c.validate('UTC',plan['created_at'])
        value['targets']=[{'id':x['target']['id'],'kind':x['target']['kind'],'location':x['location']} for x in plan['targets']]
        raw=dumps(value).encode();path=self.directory/(plan['id']+'.json')
        try:
            fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            if self._read_record(entry,plan)!=value:raise Conflict('restore exclusion idempotency conflict')
            self._publish_index(entry,plan,value)
            return value
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        directory=os.open(str(self.directory),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
        self._publish_index(entry,plan,value)
        return value

    def read(self,entry,plan):
        _attested(self.authority.verify_maintenance(entry,deepcopy(plan),'exclusion_read'))
        if not self.directory.is_dir():raise Forbidden('current exclusion directory missing')
        with dispatch_gate(self.runtime),dispatch_gate(self.directory):
            value=self._read_record(entry,plan);index=self._index()
            if index['entries'].get(plan['id'])!={'instance_id':plan['instance_id'],'digest':c.fingerprint(value)}:raise Forbidden('exclusion is absent from current trusted ledger index')
            return value

    def _read_record(self,entry,plan):
        _attested(self.authority.verify_maintenance(entry,deepcopy(plan),'exclusion_read'))
        c.validate('ID',plan['id'])
        path=self.directory/(plan['id']+'.json')
        try:
            fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd,'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise Forbidden('unsafe exclusion file')
                raw=stream.read(65537)
        except OSError as exc:raise Forbidden('current restore exclusion unavailable') from exc
        if len(raw)>65536:raise Forbidden('exclusion is oversized')
        value=c.loads(raw)
        expected={'contract':'TL-RESTORE-EXCLUSION-1','instance_id':plan['instance_id'],'barrier_id':plan['barrier_id'],'plan_id':plan['id'],
            'source_epoch':plan['source_epoch'],'scope_id':plan['scope_id'],'recorded_at':plan['created_at'],'targets':[{'id':x['target']['id'],'kind':x['target']['kind'],'location':x['location']} for x in plan['targets']]}
        if value!=expected:raise Conflict('restore exclusion identity or epoch mismatch')
        return value


    def _index(self,max_bytes=1048576):
        t.integer(max_bytes,1,1048576)
        path=self.directory/'index.json'
        try:
            fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd,'rb') as stream:raw=stream.read(max_bytes+1)
        except OSError as exc:raise Forbidden('current exclusion ledger anchor missing') from exc
        if len(raw)>max_bytes:raise Forbidden('exclusion index bound exceeded')
        self._last_index_bytes=len(raw)
        value=c.loads(raw);t.obj(value,('contract','generation','entries'))
        if value['contract']!='TL-EXCLUSION-INDEX-1':raise Forbidden('unknown exclusion anchor')
        t.integer(value['generation']);t.obj(value['entries'],tuple(value['entries']))
        for key,record in value['entries'].items():
            c.validate('ID',key);t.obj(record,('instance_id','digest'));c.validate('ID',record['instance_id'])
            if type(record['digest']) is not str or len(record['digest'])!=64 or any(x not in '0123456789abcdef' for x in record['digest']):raise Forbidden('invalid exclusion index digest')
        return value

    def _publish_index(self,entry,plan,value):
        path=self.directory/'index.json'
        if path.exists() or path.is_symlink():index=self._index()
        else:
            # A missing anchor cannot silently reset an existing ledger. The
            # sole current record may be an interrupted authenticated first
            # write, and only that exact current plan can finish it.
            allowed={'dispatch.lock',plan['id']+'.json'}
            if any(p.name not in allowed for p in self.directory.iterdir()):raise Forbidden('missing index cannot reset prior exclusion history')
            index={'contract':'TL-EXCLUSION-INDEX-1','generation':0,'entries':{}}
        fact={'instance_id':plan['instance_id'],'digest':c.fingerprint(value)}
        prior=index['entries'].get(plan['id'])
        if prior is not None and prior!=fact:raise Conflict('exclusion anchor idempotency conflict')
        if prior==fact:
            _attested(self.authority.verify_exclusion_index(entry,deepcopy(plan),str(self.directory.resolve()),deepcopy(index),'resume_append'))
            _attested(self.authority.record_exclusion_index(entry,deepcopy(plan),str(self.directory.resolve()),deepcopy(index)))
            return
        _attested(self.authority.verify_exclusion_index(entry,deepcopy(plan),str(self.directory.resolve()),deepcopy(index),'before_append'))
        index['entries'][plan['id']]=fact;index['generation']+=1
        temporary=self.directory/(identifier()+'.pending')
        fd=os.open(str(temporary),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(dumps(index).encode());stream.flush();os.fsync(stream.fileno())
        os.replace(str(temporary),str(path));directory=os.open(str(self.directory),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
        _attested(self.authority.record_exclusion_index(entry,deepcopy(plan),str(self.directory.resolve()),deepcopy(index)))

    def restore_constraints(self,entry,instance_id,max_records=1024,max_bytes=1048576):
        _attested(self.authority.verify_restore(entry,instance_id,'read_current_ledger'))
        if not self.directory.is_dir():raise Forbidden('current exclusion ledger missing')
        with dispatch_gate(self.runtime),dispatch_gate(self.directory):return self._restore_constraints(entry,instance_id,max_records,max_bytes)

    def _restore_constraints(self,entry,instance_id,max_records=1024,max_bytes=1048576):
        """Read current trusted ledger, NEVER a plan list from the old image.

        A missing directory is not an empty erasure history. This supplies
        exact opaque targets and epoch floors; actual restore must apply all
        exclusions before any content becomes available (IM13/16).
        """
        c.validate('ID',instance_id);t.integer(max_records,1,65536);t.integer(max_bytes,1,2**53-1)
        _attested(self.authority.verify_restore(entry,instance_id,'read_current_ledger'))
        if not self.directory.is_dir() or self.directory.is_symlink():raise Forbidden('current exclusion ledger missing or unsafe')
        index=self._index(min(max_bytes,1048576))
        index_size=self._last_index_bytes
        _attested(self.authority.verify_exclusion_index(entry,None,str(self.directory.resolve()),deepcopy(index),'restore_current_head'))
        if not any(x['instance_id']==instance_id for x in index['entries'].values()):raise Forbidden('current instance exclusion history is not anchored')
        result=[];size=index_size;count=0;seen=set()
        for path in self.directory.iterdir():
            if path.name in ('dispatch.lock','index.json'):continue
            count+=1
            if count>max_records:raise Forbidden('restore exclusion coverage incomplete')
            if path.is_symlink() or not path.is_file() or path.suffix!='.json':raise Forbidden('unknown exclusion ledger entry')
            fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd,'rb') as stream:raw=stream.read(max_bytes-size+1)
            size+=len(raw)
            if size>max_bytes:raise Forbidden('restore exclusion byte coverage incomplete')
            value=c.loads(raw);t.obj(value,('contract','instance_id','barrier_id','plan_id','source_epoch','scope_id','recorded_at','targets'))
            if value['contract']!='TL-RESTORE-EXCLUSION-1':raise Forbidden('unknown exclusion contract')
            for key in ('instance_id','barrier_id','plan_id','scope_id'):c.validate('ID',value[key])
            t.integer(value['source_epoch']);c.validate('UTC',value['recorded_at'])
            if path.name!=value['plan_id']+'.json':raise Conflict('exclusion identity/file mapping differs')
            for target in value['targets']:
                t.obj(target,('id','kind','location'));c.validate('ID',target['id']);t.string(target['kind']);t.enum(target['location'],('database','blob','index','cache','managed_backup','remote'))
            if index['entries'].get(value['plan_id'])!={'instance_id':value['instance_id'],'digest':c.fingerprint(value)}:raise Forbidden('unanchored or changed exclusion record')
            seen.add(value['plan_id'])
            if value['instance_id']==instance_id:result.append(value)
        if seen!=set(index['entries']):raise Forbidden('anchored exclusion record is missing')
        _attested(self.authority.verify_restore(entry,instance_id,'after_read_current_ledger'))
        control=self.authority.current_restore_exclusions(entry,instance_id,max_records,max_bytes-size)
        return {'contract':'TL-CURRENT-RESTORE-EXCLUSIONS-1','instance_id':instance_id,'exclusions':result,'control_exclusions':control,'complete_current_ledger':True,'restore_authorized':False}


# Explicit adapters; unknown tables never acquire a deletion capability from a
# caller-provided identifier. Registry identities and F1 control remain opaque.
PURGE_KINDS=frozenset(('tl_command','tl_product','tl_content','tl_content_revision','tl_decision','tl_group','tl_handoff',
    'tl_representation','tl_representation_head','tl_dependency','tl_input_dependency','tl_effect','tl_recall_item',
    'thought_requests','thought_results','thought_attempts','context_snapshots','runtime_events','memory_revisions',
    'cognition_belief_revisions','cognition_concept_revisions','working_memory_items','retrieval_items',
    'context_entity_links','activity_context_refs','thought_request_inputs','thought_state_events',
    'memory_retrieval_runs','memory_retrieval_results','memory_recall_products','memory_recall_sources','memory_access_records',
    'memory_source_links','memory_relations','memory_classifications','memory_episode_details','memory_participants',
    'memory_semantic_details','memory_procedure_details','memory_autobiographical_details','memory_prospective_details',
    'working_memory_activations','personality_behavior_measurements','personality_change_records',
    'habit_items','habit_cues','habit_associations','habit_opportunities','habit_activations','habit_learning_records',
    'decision_records','decision_candidates','decision_factor_contributions','value_behavior_measurements','state_activity_snapshots'))
CORE_KINDS=frozenset(('tl_change','tl_barrier','tl_source_epoch','tl_propagation','tl_erasure_target','object_registry','object_revision_registry','deletion_requests','deletion_effects','activity_budget_accounts'))


class ManagedErasure:
    """Actual local adapters; caller scope is checked by a default-deny M12 port.

    Plans are narrow target inventories, not a claim that all world copies are
    enumerable. Unsupported surfaces remain blocked/unknown in their journal.
    """
    def __init__(self,store,authority=None,exclusions=None,clock=utc):
        self.s=store;self.authority=authority or PropagationAuthority();self.clock=clock;self.exclusions=exclusions
        if not isinstance(self.authority,PropagationAuthority):raise ContractError('trusted maintenance authority required')
        self.storage=ToolLearningStore(store)

    def _guard(self,entry,plan,stage):
        if plan['instance_id']!=self.s.instance_id:raise Forbidden('maintenance instance differs')
        if self.clock()>=plan['deadline']:raise Forbidden('fixed maintenance deadline exhausted')
        state=_control_row(self.s,'SELECT * FROM instance_control_state WHERE instance_ref=?',(self.s.instance_id,))
        if state is None or not state['user_stopped'] or state['active_process_run_id'] is not None:
            raise Forbidden('physical maintenance requires stopped instance with no managed process')
        orphan=_control_row(self.s,'SELECT id FROM process_runs WHERE instance_ref=? AND exited_at IS NULL LIMIT 1',(self.s.instance_id,))
        if orphan is not None:raise Forbidden('unreconciled managed process record prevents physical maintenance')
        barrier=self.s.row('tl_barrier',plan['barrier_id'])
        if barrier['kind']!='erase' or barrier['source_epoch']!=plan['source_epoch']:raise Conflict('maintenance reason/epoch differs')
        change=self.s.row('tl_change',barrier['change_id']);payload=self.storage.read_artifact(change['payload_artifact_id'])
        if payload['erase_scope']['status']!='known' or payload['erase_scope']['value']['id']!=plan['scope_id']:raise Forbidden('maintenance scope is not bound to original authorized erase scope')
        _attested(self.authority.verify_maintenance(entry,deepcopy(plan),stage))
        if self.clock()>=plan['deadline']:raise Forbidden('maintenance authority crossed fixed deadline')

    def _plan(self,plan):
        t.obj(plan,('contract','id','instance_id','barrier_id','source_epoch','scope_id','created_at','deadline','authority_ref','source_activity','caps','targets','allow_control_metadata','retained_metadata','coverage'))
        if plan['contract']!='TL-MANAGED-ERASURE-1':raise ContractError('unknown maintenance contract')
        for key in ('id','instance_id','barrier_id','scope_id','authority_ref','source_activity'):c.validate('ID',plan[key])
        c.validate('UTC',plan['created_at']);c.validate('UTC',plan['deadline']);t.integer(plan['source_epoch']);t.boolean(plan['allow_control_metadata']);t.array(plan['retained_metadata'],lambda x:t.enum(x,RETAINED_METADATA))
        t.obj(plan['caps'],('scan','items','bytes','elapsed_ms','attempts'))
        if plan['caps']['attempts']!=1:raise ContractError('maintenance has one finite attempt cap but no model/tool authority')
        for value in plan['caps'].values():t.integer(value,1,2**53-1)
        if len(plan['targets'])>min(65536,plan['caps']['items']):raise Forbidden('maintenance target bound exceeded')
        seen=set()
        for target in plan['targets']:
            t.obj(target,('target','location','operation','expected'))
            self.storage.validate_ref(target['target']);t.enum(target['location'],('database','blob','index','cache','managed_backup','remote'))
            t.enum(target['operation'],('purge','tombstone','unlink','invalidate','observe'))
            expected=target['expected'];kind=target['target']['kind'];location=target['location'];operation=target['operation']
            def digest(value):c.validate('Digest',{'algorithm':'sha256','hex':value})
            def identity(value):
                t.integer(value['device']);t.integer(value['inode'])
                if 'hash' in value:digest(value['hash'])
            if location=='database' and kind=='artifacts' and operation=='tombstone':
                t.obj(expected,('hash','storage_ref'));digest(expected['hash']);digest(expected['storage_ref'])
            elif location=='database' and kind in PURGE_KINDS and operation=='purge':
                t.obj(expected,('row_digest',));digest(expected['row_digest'])
            elif location=='blob' and operation=='unlink':
                t.obj(expected,('storage_ref','device','inode'));digest(expected['storage_ref']);identity(expected)
            elif location in ('cache','index') and operation=='unlink':
                t.obj(expected,('name','device','inode','hash'));t.string(expected['name']);identity(expected)
            elif location=='managed_backup' and operation=='unlink':
                if 'registration_event_id' in expected:
                    t.obj(expected,('registration_event_id','managed_root','path','manifest_hash','files'));c.validate('ID',expected['registration_event_id']);digest(expected['manifest_hash'])
                    if type(expected['files']) is not dict or len(expected['files'])>65536:raise Forbidden('backup file inventory bound exceeded')
                    for name,fact in expected['files'].items():t.string(name);t.obj(fact,('hash','device','inode'));identity(fact)
                else:
                    t.obj(expected,('registration_id','managed_root','path','hash','device','inode'));c.validate('ID',expected['registration_id']);identity(expected)
                t.string(expected['managed_root']);t.string(expected['path'])
            else:t.json_value(expected)
            key=(target['target']['id'],target['location'])
            if key in seen:raise Conflict('duplicate cleanup target/location')
            seen.add(key)
        c.validate('Coverage',plan['coverage'])
        return plan

    def prepare(self,entry,value):
        plan=self._plan(c.loads(dumps(value)))
        if self.s.db.in_transaction:raise Conflict('maintenance requires independent transaction')
        with dispatch_gate(self.s.root):
            self._guard(entry,plan,'prepare')
            prior=self.s.db.execute('SELECT * FROM deletion_requests WHERE instance_id=? AND id=?',(self.s.instance_id,plan['id'])).fetchone()
            if prior:
                if c.loads(prior['subject_scope'])['plan']!=plan:raise Conflict('maintenance idempotency conflict')
                return plan['id']
            _attested(self.authority.verify_inventory(entry,deepcopy(plan),'prepare'))
            for target in plan['targets']:
                _attested(self.authority.verify_target(entry,deepcopy(plan),deepcopy(target),'prepare'))
                prior_target=self.s.db.execute('SELECT plan_ref_id FROM tl_erasure_target WHERE instance_id=? AND barrier_id=? AND target_ref_id=? AND location_kind=?',(self.s.instance_id,plan['barrier_id'],target['target']['id'],target['location'])).fetchone()
                if prior_target:raise Conflict('target is already bound to another immutable cleanup plan; explicit owner reconciliation required')
            if self.exclusions is None:raise Forbidden('current external restore exclusion storage is required')
            self.exclusions.write(entry,plan)
            with self.s.tx():
                source=self.s.row('activities',plan['source_activity']);activity=identifier();account=identifier()
                # A real stopped maintenance activity, with zero inference/tool
                # opportunities. This is separate from the old learning ledger.
                self.s.insert('activities',id=activity,trigger_event_id=source['trigger_event_id'],state='pending',release_id=source['release_id'],publication_state='ready',deadline=plan['deadline'],budget_json={'contract':'TL-MAINTENANCE-BUDGET-1','plan_id':plan['id'],'caps':plan['caps']})
                self.s.insert('activity_budget_accounts',id=account,activity_id=activity,token_limit=0,tool_call_limit=0,attempt_limit=plan['caps']['attempts'],time_limit_ms=plan['caps']['elapsed_ms'])
                grant_event=self.s.event('maintenance.authorized',payload={'contract':'TL-MAINTENANCE-GRANT-1','plan':plan,'activity_id':activity,'account_id':account},source='tl.maintenance',key=plan['id'],activity=activity,lane='control')
                journal={'contract':'TL-ERASURE-JOURNAL-1','plan':plan,'activity_id':activity,'account_id':account,'grant_event_id':grant_event,'used':{'scan':0,'items':0,'bytes':0,'elapsed_ms':0,'attempts':0},'unknown':False,'entered':False,'steps':{}}
                initial=self.authority.initial_usage(entry,deepcopy(plan))
                from digital_life.domain.tool_learning_resources import DIMENSIONS
                if type(initial) is not dict or set(initial)!=set(DIMENSIONS) or any(type(value) is not int or value<0 for value in initial.values()) or any(initial[key] for key in ('input_tokens','output_tokens','tool_calls','attempts')):raise Forbidden('invalid actual local maintenance bootstrap usage')
                for key in plan['caps']:
                    if initial[key]>plan['caps'][key]:raise Forbidden('maintenance review already exhausted its original cap')
                    journal['used'][key]=initial[key]
                self.s.insert('deletion_requests',id=plan['id'],subject_scope=journal,requested_at=plan['created_at'],authority_ref=plan['authority_ref'],state='cleaning')
                for target in plan['targets']:
                    self.s.insert('tl_erasure_target',barrier_id=plan['barrier_id'],plan_ref_id=plan['id'],target_ref_id=target['target']['id'],location_kind=target['location'],state='pending',row_revision=0)
                    self.s.insert('deletion_effects',request_id=plan['id'],object_ref=target['target']['id'],artifact_ref=target['target']['id'] if target['target']['kind']=='artifacts' else None,operation=target['operation'],result='pending')
                self._guard(entry,plan,'prepared')
            return plan['id']

    def renew_generation(self,entry,plan_id,obligation_id,original_work):
        """Explicit current M12 grant; no new tl_work or ordinary opportunity."""
        if self.s.db.in_transaction:raise Conflict('generation renewal needs independent gate')
        with dispatch_gate(self.s.root):
            _,journal=self._journal(plan_id);plan=journal['plan'];self._guard(entry,plan,'renew_generation')
            if journal['unknown'] or journal['entered']:raise Forbidden('maintenance consumption unresolved')
            old=self.s.row('tl_propagation',obligation_id);work=self.s.row('tl_work',original_work)
            if old['barrier_id']!=plan['barrier_id'] or work['learning_activity_id']!=plan['source_activity']:raise Forbidden('maintenance grant does not bind original barrier/work')
            if work['budget_account_id']!=old['budget_account_id']:
                _attested(self.authority.verify_origin_work(entry,deepcopy(plan),old,work))
            existing=[(key,value) for key,value in journal.get('generations',{}).items() if value['supersedes']==obligation_id]
            if existing:return existing[0][0]
            with self.s.tx():
                generation=self.s.db.execute('SELECT max(generation) FROM tl_propagation WHERE instance_id=? AND barrier_id=? AND domain=?',(self.s.instance_id,old['barrier_id'],old['domain'])).fetchone()[0]+1
                key=self.s.insert('tl_propagation',barrier_id=old['barrier_id'],domain=old['domain'],targets_artifact_id=old['targets_artifact_id'],coverage_artifact_id=old['coverage_artifact_id'],state='pending',generation=generation,deadline=plan['deadline'],budget_account_id=journal['account_id'],row_revision=0)
                journal.setdefault('generations',{})[key]={'original_work':original_work,'supersedes':obligation_id,'domain':old['domain'],'generation':generation}
                self.s.insert('deletion_effects',request_id=plan_id,object_ref=key,operation='generation_authorized',result='done',verified_at=self.clock())
                self._save(plan_id,journal);self._guard(entry,plan,'generation_committed')
            return key

    def _journal(self,plan_id):
        row=self.s.row('deletion_requests',plan_id);journal=c.loads(row['subject_scope'])
        if journal.get('contract')!='TL-ERASURE-JOURNAL-1':raise ContractError('not a managed cleanup journal')
        self._plan(journal['plan'])
        t.obj(journal['used'],tuple(journal['plan']['caps']));t.boolean(journal['entered']);t.boolean(journal['unknown'])
        for amount in journal['used'].values():t.integer(amount)
        event=self.s.row('runtime_events',journal['grant_event_id']);grant=self.storage.read_artifact(event['payload_artifact_id'])
        if event['source']!='tl.maintenance' or event['event_type']!='maintenance.authorized' or event['payload_hash']!=c.fingerprint(grant) or grant!={'contract':'TL-MAINTENANCE-GRANT-1','plan':journal['plan'],'activity_id':journal['activity_id'],'account_id':journal['account_id']}:raise Conflict('maintenance initial grant mapping changed')
        account=self.s.row('activity_budget_accounts',journal['account_id']);activity=self.s.row('activities',journal['activity_id'])
        if account['activity_id']!=journal['activity_id'] or (account['token_limit'],account['tool_call_limit'],account['attempt_limit'],account['time_limit_ms'])!=(0,0,journal['plan']['caps']['attempts'],journal['plan']['caps']['elapsed_ms']):raise Conflict('maintenance actual account caps changed')
        if activity['deadline']!=journal['plan']['deadline'] or c.loads(activity['budget_json'])!={'contract':'TL-MAINTENANCE-BUDGET-1','plan_id':journal['plan']['id'],'caps':journal['plan']['caps']}:raise Conflict('maintenance original activity budget binding changed')
        return row,journal

    def _save(self,plan_id,journal,state=None):
        fields='subject_scope=?'+(',state=?' if state else '')
        args=[dumps(journal)]+([state] if state else [])+[self.s.instance_id,plan_id]
        self.s.db.execute('UPDATE deletion_requests SET '+fields+' WHERE instance_id=? AND id=?',args)

    def run(self,entry,plan_id):
        if self.s.db.in_transaction:raise Conflict('cleanup requires independent gate/transaction')
        with dispatch_gate(self.s.root):
            row,journal=self._journal(plan_id);plan=journal['plan'];self._guard(entry,plan,'run')
            if journal['unknown'] or journal['entered']:raise Forbidden('unknown prior maintenance consumption must be reconciled, not reset')
            self.exclusions.read(entry,plan)
            _attested(self.authority.verify_inventory(entry,deepcopy(plan),'run'))
            if not plan['allow_control_metadata'] or not RETAINED_METADATA<=set(plan['retained_metadata']):
                with self.s.tx():self._save(plan_id,journal,'blocked')
                return self.status(entry,plan_id)
            from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
            amounts={'input_tokens':0,'output_tokens':0,'attempts':0,'tool_calls':0,**{key:max(0,plan['caps'][key]-journal['used'][key]) for key in plan['caps']}}
            meter=PhysicalReadMeter(amounts,plan['deadline'],clock=self.clock)
            with self.s.tx():journal['entered']=True;self._save(plan_id,journal)
            failed=None;final_verified=False;database_dirty=False
            try:
                with meter.installed(self.s):
                    secure=self.s.db.execute('PRAGMA secure_delete=ON').fetchone()
                    if secure is None or secure[0]!=1:raise Forbidden('SQLite secure deletion unavailable')
                    for target in plan['targets']:
                        key=target['target']['id']+':'+target['location']
                        if journal['steps'].get(key,{}).get('state')=='verified' and self._verify_target(plan,target):continue
                        self._guard(entry,plan,'target_before')
                        _attested(self.authority.verify_target(entry,deepcopy(plan),deepcopy(target),'execute'))
                        if target['location']=='database':
                            journal['database_compaction_verified']=False
                            with self.s.tx():self._save(plan_id,journal)
                        result=self._target(entry,plan,target)
                        if target['location']=='database' and result['state']=='verified':database_dirty=True
                        self._guard(entry,plan,'target_after')
                        _attested(self.authority.verify_target(entry,deepcopy(plan),deepcopy(target),'verified'))
                        with self.s.tx():
                            current=self.s.db.execute('SELECT * FROM tl_erasure_target WHERE instance_id=? AND plan_ref_id=? AND target_ref_id=? AND location_kind=?',(self.s.instance_id,plan_id,target['target']['id'],target['location'])).fetchone()
                            proof=self.s.artifact({'contract':'TL-ERASURE-TARGET-VERIFICATION-1','plan_id':plan_id,'barrier_id':plan['barrier_id'],'target_id':target['target']['id'],'location':target['location'],'result':result,'verified_at':self.clock()})
                            self.s.db.execute('UPDATE tl_erasure_target SET state=?,verification_artifact_id=?,row_revision=row_revision+1 WHERE instance_id=? AND id=? AND row_revision=?',(result['state'],proof,self.s.instance_id,current['id'],current['row_revision']))
                            self.s.db.execute('UPDATE deletion_effects SET result=?,verified_at=? WHERE instance_id=? AND request_id=? AND object_ref=? AND operation=?',('done' if result['state']=='verified' else 'failed',self.clock(),self.s.instance_id,plan_id,target['target']['id'],target['operation']))
                            journal['steps'][key]=result;self._save(plan_id,journal)
                    if database_dirty or (any(target['location']=='database' for target in plan['targets']) and not journal.get('database_compaction_verified',False)):
                        self._compact_database();journal['database_compaction_verified']=True
                        with self.s.tx():self._save(plan_id,journal)
                    _attested(self.authority.verify_inventory(entry,deepcopy(plan),'final_verify'))
                    self._guard(entry,plan,'final_verify')
                    final_verified=all(self._verify_target(plan,target) for target in plan['targets'])
                    meter.time()
            except BaseException as exc:failed=exc
            finally:
                usage=meter.usage()
                measured=meter.actual if usage is None else usage
                with self.s.tx():
                    # A crashed process leaves entered=True, conservatively
                    # refusing a new resource opportunity on restart.
                    for key in plan['caps']:journal['used'][key]+=measured[key]
                    journal['entered']=False;journal['unknown']=bool(meter.unknown_bytes)
                    all_done=len(journal['steps'])==len(plan['targets']) and all(x['state']=='verified' for x in journal['steps'].values())
                    complete=bool(plan['targets']) and all_done and final_verified and plan['coverage']['state']=='complete' and not plan['coverage']['missing'] and not plan['coverage']['truncated']
                    self._save(plan_id,journal,'verified' if complete and failed is None else 'blocked')
            if failed:raise failed
            return self.status(entry,plan_id)

    def _target(self,entry,plan,target):
        obj=target['target'];kind=obj['kind'];key=obj['id'];location=target['location'];operation=target['operation']
        if location=='remote':return {'state':'unknown','reason':'remote outcome and already delivered world effects are not reversible'}
        if location in ('cache','index'):return self._local_index(target)
        if location=='managed_backup':return self._registered_backup(target)
        if location=='blob':return self._unlink_blob(plan,target)
        if location!='database':raise ContractError('unsupported cleanup location')
        if kind=='runtime_events':
            event=self.s.db.execute('SELECT source FROM runtime_events WHERE instance_id=? AND id=?',(self.s.instance_id,key)).fetchone()
            if event and event['source'] in ('tl.maintenance.F1','tl.maintenance.F1.prepared','tl.maintenance.controller','tl.maintenance'):
                return {'state':'blocked','reason':'minimum actual authorization/exclusion provenance cannot be purged'}
        if kind=='tl_command':
            command=self.s.db.execute('SELECT operation FROM tl_command WHERE instance_id=? AND id=?',(self.s.instance_id,key)).fetchone()
            if command and command['operation']=='apply_invalidation':return {'state':'blocked','reason':'minimum F1 authorization provenance is retained'}
        if kind in CORE_KINDS:return {'state':'blocked','reason':'immutable control/exclusion metadata cannot be purged by this adapter'}
        if operation=='tombstone' and kind=='artifacts':
            if not self._artifact_consumers_in_scope(plan,key):return {'state':'blocked','reason':'shared artifact has a registered consumer outside the fixed source/authorized purge closure'}
            with self.s.tx():
                row=self.s.row('artifacts',key)
                expected=target['expected']
                if row['hash']!=expected['hash'] or row['storage_ref']!=expected['storage_ref']:
                    # Recovery only accepts this plan's actual tombstone, not
                    # any different artifact or an old version's secret hash.
                    tombstone={'contract':'TL-ERASED-MATERIAL-1','plan_id':plan['id']}
                    if self.storage.read_artifact(key)!=tombstone:raise Conflict('artifact changed before cleanup')
                else:
                    tomb=self.s.artifact({'contract':'TL-ERASED-MATERIAL-1','plan_id':plan['id']});new=self.s.row('artifacts',tomb)
                    self.s.db.execute('UPDATE artifacts SET hash=?,size=?,media_type=?,storage_ref=? WHERE instance_id=? AND id=?',(new['hash'],new['size'],new['media_type'],new['storage_ref'],self.s.instance_id,key))
                if self.storage.read_artifact(key)!={'contract':'TL-ERASED-MATERIAL-1','plan_id':plan['id']}:raise Conflict('artifact redaction verification failed')
            return {'state':'verified','reason':'actual artifact bytes now equal the authorized opaque tombstone'}
        if operation=='purge' and kind in PURGE_KINDS and kind in self.s.columns:
            with self.s.tx():
                row=self.s.db.execute('SELECT * FROM '+kind+' WHERE instance_id=? AND id=?',(self.s.instance_id,key)).fetchone()
                if row is not None:
                    if c.fingerprint(dict(row))!=target['expected']['row_digest']:raise Conflict('target row changed after authorized inventory')
                    self.s.db.execute('DELETE FROM '+kind+' WHERE instance_id=? AND id=?',(self.s.instance_id,key))
                if self.s.db.execute('SELECT 1 FROM '+kind+' WHERE instance_id=? AND id=?',(self.s.instance_id,key)).fetchone():raise Conflict('purge readback failed')
            return {'state':'verified','reason':'actual registered business row absent; minimal opaque registry retained'}
        return {'state':'blocked','reason':'unknown target owner/operation adapter; not_run'}

    def _artifact_consumers_in_scope(self,plan,key):
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        barrier=self.s.row('tl_barrier',plan['barrier_id']);change=self.s.row('tl_change',barrier['change_id']);source=self.storage.read_artifact(change['payload_artifact_id'])['source']
        # Reuse the exact-version closure semantics; never treat an unrelated
        # source with identical bytes as another derivative of this source.
        closure=ToolLearningInvalidation(self.s,max_nodes=4096,max_rows=65536)
        nodes,truncated=closure._closure(source,'erase')
        if truncated:return False
        allowed={node[0] for node in nodes}|{node[1] for node in nodes if node[1] is not None}
        allowed|={item['target']['id'] for item in plan['targets'] if item['location']=='database' and item['operation']=='purge'}
        frames=set()
        for work in self.s.db.execute('SELECT id,learning_activity_id,source_activity_id FROM tl_work WHERE instance_id=? AND learning_activity_id=? LIMIT 2',(self.s.instance_id,plan['source_activity'])):
            if work['id'] in allowed or source['object']['kind']=='perception_signals' and self.s.row('activities',work['source_activity_id'])['trigger_event_id']==source['object']['id']:
                allowed.add(work['id']);frames.update((work['learning_activity_id'],work['source_activity_id']))
        scanned=0
        for table,columns in sorted(self.s.columns.items()):
            if table in ('artifacts','deletion_effects') or 'instance_id' not in columns or 'id' not in columns:continue
            for column in sorted(columns):
                if not (column.endswith('_artifact_id') or column.endswith('_artifact_ref') or column in ('artifact_id','artifact_ref')):continue
                scanned+=1
                if scanned>65536:return False
                selected='id'+(',activity_id' if 'activity_id' in columns else '')
                for row in self.s.db.execute('SELECT '+selected+' FROM '+table+' WHERE instance_id=? AND '+column+'=? LIMIT ?',(self.s.instance_id,key,65537-scanned)):
                    scanned+=1
                    if scanned>65536:return False
                    if row['id'] not in allowed and not ('activity_id' in row.keys() and row['activity_id'] in frames):return False
        return True

    def _unlink_blob(self,plan,target):
        expected=target['expected'];name=expected['storage_ref']
        if type(name) is not str or len(name)!=64 or any(x not in '0123456789abcdef' for x in name):raise Forbidden('unsafe blob location')
        folder=self.s.root/'blobs'
        if folder.is_symlink():raise Forbidden('blob root is a symlink')
        fd=os.open(str(folder),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            # BEGIN IMMEDIATE serializes every instance sharing this database;
            # the instance gate covers cooperating same-root file operations.
            with self.s.tx():
                if self.s.db.execute('SELECT 1 FROM artifacts WHERE storage_ref=? LIMIT 1',(name,)).fetchone():
                    return {'state':'blocked','reason':'same blob root still has a registered reference (all instances checked)'}
                try:current=os.stat(name,dir_fd=fd,follow_symlinks=False)
                except FileNotFoundError:return {'state':'verified','reason':'physical target absent; all-root references absent'}
                if not stat.S_ISREG(current.st_mode) or (current.st_dev,current.st_ino)!=(expected['device'],expected['inode']):raise Forbidden('blob inode changed or is not a regular file')
                stream=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
                try:
                    opened=os.fstat(stream)
                    if (opened.st_dev,opened.st_ino)!=(current.st_dev,current.st_ino):raise Conflict('blob replaced during verification')
                    from digital_life.infrastructure.persistence.tool_learning_meter import external_read_before,external_read_after
                    external_read_before(opened.st_size);digest=hashlib.sha256();read=0
                    while True:
                        piece=os.read(stream,65536)
                        if not piece:break
                        read+=len(piece);external_read_after(len(piece));digest.update(piece)
                    if digest.hexdigest()!=name or read!=opened.st_size:raise Conflict('blob identity/content differs')
                finally:os.close(stream)
                # No callback or transaction release between reference query
                # and actual unlink. A failed/unknown commit leaves exclusion
                # and journal; retry inspects absence instead of blind unlink.
                final=os.stat(name,dir_fd=fd,follow_symlinks=False)
                if (final.st_dev,final.st_ino)!=(current.st_dev,current.st_ino):raise Conflict('blob changed before unlink')
                os.unlink(name,dir_fd=fd);os.fsync(fd)
                try:os.stat(name,dir_fd=fd,follow_symlinks=False)
                except FileNotFoundError:return {'state':'verified','reason':'same authorized inode unlinked and absence verified'}
                raise Conflict('blob remains after unlink')
        finally:os.close(fd)

    def _compact_database(self):
        """Current managed SQLite, not OS snapshots/SSD forensic erasure."""
        if self.s.db.in_transaction:raise Conflict('database compaction needs committed target changes')
        checkpoint=self.s.db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if checkpoint is None or checkpoint[0]!=0:raise Forbidden('live reader prevents managed WAL truncation')
        self.s.db.execute('VACUUM')
        checkpoint=self.s.db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if checkpoint is None or checkpoint[0]!=0:raise Forbidden('post-compaction WAL remains busy')
        free=self.s.db.execute('PRAGMA freelist_count').fetchone()
        integrity=self.s.db.execute('PRAGMA integrity_check(1)').fetchone()
        if free is None or free[0]!=0 or integrity is None or integrity[0]!='ok' or self.s.db.execute('PRAGMA foreign_key_check').fetchone() is not None:raise Conflict('managed database compaction/integrity not verified')
        from digital_life.infrastructure.persistence.tool_learning_meter import external_read_before,external_read_after
        path=self.s.root/'runtime.sqlite'
        if path.is_symlink():raise Forbidden('runtime database path changed')
        fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):raise Forbidden('runtime database not regular')
            external_read_before(info.st_size);first=True
            while True:
                raw=os.read(fd,65536)
                if not raw:break
                external_read_after(len(raw))
                if first and raw[:16]!=b'SQLite format 3\0':raise Conflict('compacted database header invalid')
                first=False
        finally:os.close(fd)
        for suffix in ('-wal','-journal'):
            journal=self.s.root/('runtime.sqlite'+suffix)
            if journal.is_symlink() or (journal.exists() and journal.stat().st_size):raise Forbidden('managed SQLite journal not empty after checkpoint')

    def _safe_file(self,folder,name,expected):
        if type(name) is not str or Path(name).name!=name or name in ('','.','..'):raise Forbidden('unsafe managed file name')
        if folder.is_symlink():raise Forbidden('managed folder symlink denied')
        directory=os.open(str(folder),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            try:before=os.stat(name,dir_fd=directory,follow_symlinks=False)
            except FileNotFoundError:return {'state':'verified','reason':'authorized managed file absent'}
            if not stat.S_ISREG(before.st_mode) or (before.st_dev,before.st_ino)!=(expected['device'],expected['inode']):raise Forbidden('managed file inode or type mismatch')
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            try:
                from digital_life.infrastructure.persistence.tool_learning_meter import external_read_before,external_read_after
                external_read_before(before.st_size);digest=hashlib.sha256()
                while True:
                    raw=os.read(fd,65536)
                    if not raw:break
                    external_read_after(len(raw));digest.update(raw)
                if digest.hexdigest()!=expected['hash']:raise Conflict('registered managed file digest mismatch')
            finally:os.close(fd)
            after=os.stat(name,dir_fd=directory,follow_symlinks=False)
            if (after.st_dev,after.st_ino,after.st_size)!=(before.st_dev,before.st_ino,before.st_size):raise Conflict('managed file changed before removal')
            os.unlink(name,dir_fd=directory);os.fsync(directory)
            try:os.stat(name,dir_fd=directory,follow_symlinks=False)
            except FileNotFoundError:return {'state':'verified','reason':'registered inode removed and absence checked'}
            raise Conflict('managed file remains')
        finally:os.close(directory)

    def _local_index(self,target):
        expected=target['expected'];name=expected.get('name')
        allowed={'memory-quality-index.sqlite'+suffix for suffix in ('','-wal','-shm','-journal')}
        if name not in allowed or target['operation']!='unlink':return {'state':'blocked','reason':'unknown cache/index adapter; not_run'}
        return self._safe_file(self.s.root,name,expected)

    def _registered_backup(self,target):
        expected=target['expected']
        if expected.get('registration_event_id'):return self._directory_backup(target)
        if target['operation']!='unlink':return {'state':'blocked','reason':'backup operation not_run'}
        registration=_control_row(self.s,'SELECT * FROM backup_manifests WHERE id=?',(expected.get('registration_id'),))
        if registration is None:return {'state':'blocked','reason':'backup is not registered; not_run'}
        path=Path(registration['snapshot_path'])
        if not path.is_absolute() or path.is_symlink() or registration['hash']!=expected.get('hash') or str(path)!=expected.get('path'):raise Forbidden('registered snapshot identity differs')
        scope=c.loads(registration['scope'])
        if scope.get('instance_id')!=self.s.instance_id:raise Forbidden('backup registration instance scope differs')
        managed=scope.get('managed_root')
        if type(managed) is not str or not Path(managed).is_absolute():raise Forbidden('backup has no explicit managed root')
        root=Path(managed)
        if root.is_symlink() or root.resolve()!=root or path.parent!=root or path.resolve()!=path or expected.get('managed_root')!=managed:raise Forbidden('backup path escaped its registered canonical managed root')
        # This adapter is deliberately a registered single-file snapshot. A
        # directory backup requires its own complete manifest owner adapter.
        if path.is_dir():return {'state':'blocked','reason':'directory backup needs complete manifest adapter; not_run'}
        return self._safe_file(path.parent,path.name,expected)

    def _directory_backup(self,target):
        expected=target['expected']
        if target['operation']!='unlink':return {'state':'blocked','reason':'backup directory operation not_run'}
        event=self.s.row('runtime_events',expected['registration_event_id'])
        if event['event_type']!='backup.created':raise Forbidden('not an actual registered backup event')
        registration=self.storage.read_artifact(event['payload_artifact_id'])
        root=Path(expected['managed_root']);path=Path(expected['path'])
        if not root.is_absolute() or root.is_symlink() or root.resolve()!=root or path.parent!=root or path.is_symlink() or path.resolve()!=path or registration.get('path')!=str(path) or registration.get('manifest_sha256')!=expected['manifest_hash']:
            raise Forbidden('backup path/manifest escaped its explicit registered managed root')
        if not path.exists():return {'state':'verified','reason':'registered backup directory absent'}
        manifest_path=path/'manifest.json'
        if manifest_path.is_symlink():raise Forbidden('backup manifest symlink denied')
        from digital_life.infrastructure.persistence.tool_learning_meter import external_read_before,external_read_after
        if manifest_path.exists():
            size=manifest_path.stat().st_size;external_read_before(size)
            fd=os.open(str(manifest_path),os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd,'rb') as stream:raw=stream.read(1048577)
            external_read_after(len(raw))
            if len(raw)>1048576 or hashlib.sha256(raw).hexdigest()!=expected['manifest_hash']:raise Conflict('registered backup manifest changed')
            manifest=c.loads(raw)
            if manifest['instance_id']!=self.s.instance_id:raise Forbidden('backup manifest instance differs')
            actual_files=dict(manifest['files']);actual_files['manifest.json']=expected['manifest_hash']
            if {name:fact['hash'] for name,fact in expected['files'].items()}!=actual_files:raise Conflict('authorized backup file inventory differs from registered manifest')
        else:
            # Only a previous authorized per-file pass may remove manifest;
            # the fixed expected inventory still comes from the current plan.
            if any((path/name).exists() for name in expected['files']):raise Conflict('backup manifest missing while body files remain')
        allowed=set(expected['files'])
        if len(allowed)>65536:raise Forbidden('backup manifest finite target bound exceeded')
        actual=set()
        for entry in path.iterdir():
            if entry.is_symlink():raise Forbidden('backup symlink denied')
            if entry.name=='blobs' and entry.is_dir():
                for blob in entry.iterdir():
                    if blob.is_symlink() or not blob.is_file():raise Forbidden('unknown backup blob entry')
                    actual.add('blobs/'+blob.name)
                    if len(actual)>len(allowed):raise Conflict('unregistered backup files present')
            elif entry.is_file():actual.add(entry.name)
            else:raise Forbidden('unknown backup directory entry')
            if len(actual)>len(allowed):raise Conflict('unregistered backup files present')
        if not actual<=allowed:raise Conflict('unregistered backup files present')
        for name in sorted(allowed,key=lambda x:(x=='manifest.json',x)):
            parts=Path(name).parts
            if name in ('runtime.sqlite','manifest.json'):folder=path;file_name=name
            elif len(parts)==2 and parts[0]=='blobs' and len(parts[1])==64 and all(x in '0123456789abcdef' for x in parts[1]):folder=path/'blobs';file_name=parts[1]
            else:raise Forbidden('unsafe registered backup relative path')
            if folder.exists():self._safe_file(folder,file_name,expected['files'][name])
        blobs=path/'blobs'
        if blobs.exists():blobs.rmdir()
        path.rmdir()
        if path.exists() or path.is_symlink():raise Conflict('backup directory remains')
        return {'state':'verified','reason':'complete registered file inventory removed and directory absence verified'}

    def _verify_target(self,plan,target):
        kind=target['target']['kind'];key=target['target']['id'];location=target['location']
        if location=='database' and kind=='artifacts' and target['operation']=='tombstone':
            return self.storage.read_artifact(key)=={'contract':'TL-ERASED-MATERIAL-1','plan_id':plan['id']}
        if location=='database' and kind in PURGE_KINDS and target['operation']=='purge':
            return self.s.db.execute('SELECT 1 FROM '+kind+' WHERE instance_id=? AND id=?',(self.s.instance_id,key)).fetchone() is None
        if location=='blob':
            name=target['expected']['storage_ref'];path=self.s.root/'blobs'/name
            return not path.exists() and not path.is_symlink() and self.s.db.execute('SELECT 1 FROM artifacts WHERE storage_ref=? LIMIT 1',(name,)).fetchone() is None
        if location in ('index','cache'):
            name=target['expected'].get('name');allowed={'memory-quality-index.sqlite'+suffix for suffix in ('','-wal','-shm','-journal')}
            if name not in allowed:return False
            path=self.s.root/name;return not path.exists() and not path.is_symlink()
        if location=='managed_backup':
            if target['expected'].get('registration_event_id'):
                event=self.s.row('runtime_events',target['expected']['registration_event_id'])
                registration=self.storage.read_artifact(event['payload_artifact_id'])
                path=Path(target['expected']['path'])
                return registration.get('path')==str(path) and registration.get('manifest_sha256')==target['expected']['manifest_hash'] and not path.exists() and not path.is_symlink()
            row=_control_row(self.s,'SELECT * FROM backup_manifests WHERE id=?',(target['expected'].get('registration_id'),))
            if row is None or row['snapshot_path']!=target['expected'].get('path'):return False
            path=Path(row['snapshot_path']);return not path.exists() and not path.is_symlink()
        return False

    @contextmanager
    def _local_read(self,entry,plan_id,operation):
        if operation not in ('F3_aggregate',):raise Forbidden('maintenance read cannot authorize a model/tool/external operation')
        if self.s.db.in_transaction:raise Conflict('maintenance read needs an independent opportunity')
        with dispatch_gate(self.s.root):
            _,journal=self._journal(plan_id);plan=journal['plan'];self._guard(entry,plan,operation)
            if journal['unknown'] or journal['entered']:raise Forbidden('maintenance budget unresolved')
            from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
            remaining={k:max(0,plan['caps'][k]-journal['used'][k]) for k in plan['caps']}
            meter=PhysicalReadMeter({'input_tokens':0,'output_tokens':0,'attempts':0,'tool_calls':0,**remaining},plan['deadline'],clock=self.clock)
            with self.s.tx():journal['entered']=True;self._save(plan_id,journal)
            try:
                with meter.installed(self.s):yield
            finally:
                usage=meter.usage();measured=meter.actual if usage is None else usage
                with self.s.tx():
                    _,latest=self._journal(plan_id)
                    for key in plan['caps']:latest['used'][key]+=measured[key]
                    latest['entered']=False;latest['unknown']=usage is None;self._save(plan_id,latest)

    def completion(self,entry,plan_id):
        with self._local_read(entry,plan_id,'F3_aggregate'):
            return self._completion(entry,plan_id)

    def _completion(self,entry,plan_id):
        """F3 aggregation is separate from physical target-plan verification.

        Only an explicit same-domain supersession binding can cover an older
        obligation. Neither a latest-row shortcut nor one domain can stand in
        for all nine. This endpoint grants no source use or barrier resolution.
        """
        with dispatch_gate(self.s.root):
            _,journal=self._journal(plan_id);plan=journal['plan'];self._guard(entry,plan,'F3_aggregate')
            rows=self.s.db.execute('SELECT * FROM tl_propagation WHERE instance_id=? AND barrier_id=? ORDER BY domain,generation LIMIT 1025',(self.s.instance_id,plan['barrier_id'])).fetchall()
            if len(rows)>1024:raise Forbidden('F3 obligation coverage bound exceeded')
            obligations={row['id']:dict(row) for row in rows};covered=set();supersedes={}
            for row in rows:
                if row['state']=='verified' and row['verification_artifact_id'] is not None:covered.add(row['id'])
                if row['generation']==0:continue
                bindings=self.s.db.execute("SELECT request_id FROM deletion_effects WHERE instance_id=? AND object_ref=? AND operation='generation_authorized' LIMIT 2",(self.s.instance_id,row['id'])).fetchall()
                if len(bindings)!=1:continue
                _,authorization=self._journal(bindings[0]['request_id']);binding=authorization.get('generations',{}).get(row['id'])
                if binding and binding['domain']==row['domain'] and binding['supersedes'] in obligations:
                    prior=obligations[binding['supersedes']]
                    if prior['domain']==row['domain'] and prior['barrier_id']==row['barrier_id'] and row['budget_account_id']==authorization['account_id']:
                        supersedes[row['id']]=binding['supersedes']
            changed=True
            while changed:
                changed=False
                for newer,older in supersedes.items():
                    if newer in covered and older not in covered:covered.add(older);changed=True
            missing=[domain for domain in DOMAINS if not any(row['domain']==domain and row['generation']==0 and row['id'] in covered for row in rows)]
            physical=self.status(entry,plan_id)
            return {'contract':'TL-F3-COMPLETION-1','barrier_id':plan['barrier_id'],'state':'verified' if not missing and physical['state']=='verified' else 'pending',
                'physical_plan_state':physical['state'],'missing_domains':missing,'scope':'explicit currently authorized managed inventory',
                'barrier_resolved':False,'permissions_restored':False,'remote_erasure_claimed':False,'restore_integrated':False}

    def status(self,entry,plan_id):
        row,journal=self._journal(plan_id);self._guard(entry,journal['plan'],'status')
        state=row['state']
        return {'plan_id':plan_id,'state':state,'scope':'managed-local explicit target inventory','targets':deepcopy(journal['steps']),
            'usage':deepcopy(journal['used']),'usage_unknown':journal['unknown'] or journal['entered'],'barrier_remains':True,
            'missing':['immutable control metadata is not permitted by this plan'] if not journal['plan']['allow_control_metadata'] or not RETAINED_METADATA<=set(journal['plan']['retained_metadata']) else [],
            'restoration_integrated':False,'f3_complete':False,'state_basis':'last completed maintenance verification, not a new read or authorization'}


class MaintenanceReadAccounting:
    """Actual bounded F2 read slice from one genuine M12 maintenance ledger.

    Never usable for models/tools; original-generation accounts cannot be
    silently swapped for it. A crashed entered marker is an unknown hold.
    """
    def __init__(self,erasure,plan_id):
        if not isinstance(erasure,ManagedErasure):raise ContractError('actual maintenance owner required')
        self.erasure=erasure;self.plan_id=plan_id
    @contextmanager
    def operation(self,entry,request,obligation):
        service=self.erasure;s=service.s
        _,journal=service._journal(self.plan_id);plan=journal['plan'];service._guard(entry,plan,'F2_resource_entry')
        binding=journal.get('generations',{}).get(obligation['id'])
        if not binding or binding['domain']!=request['payload']['domain'] or binding['original_work']!=request['work_ref']['value']['id'] or obligation['budget_account_id']!=journal['account_id'] or request['budget']['account_ref']['id']!=journal['account_id']:
            raise Forbidden('F2 resource grant does not bind this exact domain/work/account')
        if journal['unknown'] or journal['entered']:raise Forbidden('maintenance prior opportunity unresolved')
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
        remaining={k:max(0,plan['caps'][k]-journal['used'][k]) for k in plan['caps']}
        for dimension,field in (('scan','max_scan'),('items','max_items'),('bytes','max_bytes')):remaining[dimension]=min(remaining[dimension],request['budget'][field])
        meter=PhysicalReadMeter({'input_tokens':0,'output_tokens':0,'attempts':0,'tool_calls':0,**remaining},plan['deadline'],clock=service.clock)
        with s.tx():journal['entered']=True;service._save(self.plan_id,journal)
        try:
            with meter.installed(s):yield
        finally:
            usage=meter.usage();measured=meter.actual if usage is None else usage
            with s.tx():
                # Preserve the latest generation bindings and any owner facts
                # committed by the protected F2 transaction.
                _,latest=service._journal(self.plan_id)
                for key in plan['caps']:latest['used'][key]+=measured[key]
                latest['entered']=False;latest['unknown']=usage is None
                service._save(self.plan_id,latest)


class ManagedInventory:
    """Bounded actual registered derivative and material inventory.

    This never equates a graph walk with complete world coverage. Missing
    legacy manifests, unknown owner kinds, cycles and bounds are explicit gaps.
    The current owner must additionally certify the chosen maintenance scope.
    """
    def __init__(self,erasure,max_rows=4096):
        if not isinstance(erasure,ManagedErasure):raise ContractError('actual M12 maintenance owner required')
        self.erasure=erasure;self.s=erasure.s;self.storage=ToolLearningStore(self.s);t.integer(max_rows,1,65536);self.max_rows=max_rows
    def discover(self,entry,plan_id,source):
        if self.s.db.in_transaction:raise Conflict('inventory needs independent actual maintenance opportunity')
        with dispatch_gate(self.s.root):
            _,journal=self.erasure._journal(plan_id);plan=journal['plan'];self.erasure._guard(entry,plan,'inventory')
            barrier=self.s.row('tl_barrier',plan['barrier_id'])
            if source['object']['id']!=barrier['source_ref_id']:raise Forbidden('inventory source is outside actual maintenance barrier')
            if journal['unknown'] or journal['entered']:raise Forbidden('maintenance inventory budget unresolved')
            from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
            amounts={'input_tokens':0,'output_tokens':0,'attempts':0,'tool_calls':0,**{key:max(0,plan['caps'][key]-journal['used'][key]) for key in plan['caps']}}
            meter=PhysicalReadMeter(amounts,plan['deadline'],clock=self.erasure.clock)
            with self.s.tx():journal['entered']=True;self.erasure._save(plan_id,journal)
            try:
                with meter.installed(self.s):return self._discover(source)
            finally:
                usage=meter.usage();measured=meter.actual if usage is None else usage
                with self.s.tx():
                    for key in plan['caps']:journal['used'][key]+=measured[key]
                    journal['entered']=False;journal['unknown']=usage is None;self.erasure._save(plan_id,journal)
    def _discover(self,source):
        c.validate('VersionToken',source);self.storage.validate_ref(source['object'])
        revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.s.instance_id,source['object']['id'],source['revision'])).fetchone()
        queue=[(source['object']['id'],revision[0] if revision else None)];seen=set();refs={};scanned=0;gaps=[];edges=set()
        while queue:
            key,fixed=queue.pop(0)
            if (key,fixed) in seen:continue
            if scanned>=self.max_rows:gaps.append('finite_inventory_bound');break
            seen.add((key,fixed))
            identity=self.s.db.execute('SELECT * FROM object_registry WHERE instance_id=? AND id=?',(self.s.instance_id,key)).fetchone();scanned+=1
            if identity is None:gaps.append('missing_registered_identity');continue
            kind=identity['kind'];refs[key]=ref(self.s,key,kind)
            if kind not in self.s.columns:gaps.append('unknown_owner_kind:'+kind);continue
            row=self.s.db.execute('SELECT * FROM '+kind+' WHERE instance_id=? AND id=?',(self.s.instance_id,key)).fetchone();scanned+=1
            if row is None:gaps.append('missing_registered_object');continue
            # Include every real outbound artifact FK, not only a caller's
            # preferred body. Body copies, measurements and stage events are
            # also separate consumers through the producer's TL lineage.
            for column in row.keys():
                value=row[column]
                if value is not None and (column.endswith('_artifact_id') or column.endswith('_artifact_ref') or column in ('artifact_id','artifact_ref')):
                    if scanned>=self.max_rows:gaps.append('finite_inventory_bound');break
                    artifact=self.s.db.execute("SELECT id FROM artifacts WHERE instance_id=? AND id=?",(self.s.instance_id,value)).fetchone();scanned+=1
                    if artifact:queue.append((value,None))
                    else:gaps.append('missing_artifact_mapping')
            if kind=='artifacts':
                # Copies such as command results are reachable via their real
                # artifact FK even when they are not independent evidence or
                # semantic support. Never infer erasure from a text match.
                for table in sorted(PURGE_KINDS | CORE_KINDS | frozenset(('configuration_versions','model_versions','perception_signals'))):
                    columns=self.s.columns.get(table,())
                    if 'instance_id' not in columns or 'id' not in columns:continue
                    for column in sorted(columns):
                        if not (column.endswith('_artifact_id') or column.endswith('_artifact_ref') or column in ('artifact_id','artifact_ref')):continue
                        if scanned>=self.max_rows:gaps.append('finite_inventory_bound');break
                        scanned+=1
                        rows=self.s.db.execute('SELECT id FROM '+table+' WHERE instance_id=? AND '+column+'=? ORDER BY id LIMIT ?',(self.s.instance_id,key,self.max_rows-scanned+1))
                        for inbound in rows:
                            scanned+=1
                            if scanned>self.max_rows:gaps.append('finite_inventory_bound');break
                            queue.append((inbound['id'],None))
                    if scanned>=self.max_rows:break
                continue
            remaining=max(0,self.max_rows-scanned)
            rows=self.s.db.execute('SELECT id,consumer_ref_id,relation,source_revision_id FROM tl_dependency WHERE instance_id=? AND (source_ref_id=? OR source_revision_id=?) AND (source_revision_id=? OR source_revision_id IS NULL OR ? IS NULL) ORDER BY id LIMIT ?',
                (self.s.instance_id,key,fixed,fixed,fixed,remaining+1))
            for edge in rows:
                scanned+=1
                if scanned>self.max_rows:gaps.append('finite_inventory_bound');break
                consumer=edge['consumer_ref_id'];edge_key=(key,fixed,consumer,edge['relation'])
                if edge_key in edges:continue
                edges.add(edge_key)
                if consumer==key or any(n[0]==consumer for n in seen):gaps.append('cycle_or_back_edge')
                native=self.s.db.execute('SELECT object_id FROM object_revision_registry WHERE instance_id=? AND id=?',(self.s.instance_id,consumer)).fetchone();scanned+=1
                queue.append((consumer,None))
                if native:queue.append((native[0],consumer))
        return {'contract':'TL-MANAGED-INVENTORY-1','source':deepcopy(source),'targets':[refs[k] for k in sorted(refs)],
            'coverage':{'state':'partial' if gaps else 'unknown','domain':slot('registered typed dependencies and actual outbound material references'),
                'scanned':scanned,'limit':self.max_rows,'truncated':'finite_inventory_bound' in gaps,
                'missing':[{'status':'unknown','value':None,'reason_code':'not_measured','reason':g,'basis_refs':[]} for g in sorted(set(gaps))]+[{'status':'unknown','value':None,'reason_code':'not_measured','reason':'owner scope and legacy-manifest coverage require current verification','basis_refs':[]}]},
            'relations':[{'source_id':x[0],'source_revision_id':x[1],'consumer_id':x[2],'relation':x[3]} for x in sorted(edges,key=dumps)]}


class LocalOwnerActions:
    """Narrow actual state adapters usable by an authenticated domain owner.

    These helpers confer no grant. OwnedTransaction checks the real module and
    table grant for every write. M03 keeps history; review/restore remains a
    future explicit decision, never a source of fabricated scientific truth.
    """
    @staticmethod
    def apply(transaction,store,domain,target,action,expected):
        c.validate('Ref',target)
        if target['instance_id']!=store.instance_id:raise Forbidden('domain action cannot cross instances')
        key=target['id'];kind=target['kind'];row=store.row(kind,key)
        if domain=='M04' and kind=='tl_representation' and action=='withdraw':
            if row['state']=='withdrawn':return {'target':target,'state':'withdrawn','historical_payload_unchanged':True}
            if row['state']!='ready':raise Conflict('representation withdrawal expected ready')
            transaction.update_representation_state(key,'withdrawn',expected_state='ready')
            if store.row(kind,key)['state']!='withdrawn':raise Conflict('withdrawal readback failed')
            return {'target':target,'state':'withdrawn','historical_payload_unchanged':True}
        if domain=='M04' and kind=='tl_representation_head' and action=='withdraw_head':
            if row['row_revision']!=expected:raise Conflict('representation head CAS differs')
            representation=store.row('tl_representation',row['representation_id'])
            if representation['state']=='ready':transaction.update_representation_state(representation['id'],'withdrawn',expected_state='ready')
            if store.row('tl_representation',representation['id'])['state']=='ready':raise Conflict('head representation remains ready')
            # The frozen head pointer is NOT NULL. Keep the historical pointer;
            # current recall independently requires the pointed row ready.
            return {'target':target,'state':'head_representation_withdrawn','representation_id':representation['id']}
        if domain in ('M03','M04') and kind=='tl_group' and action=='obsolete':
            if row['row_revision']!=expected:raise Conflict('group CAS differs')
            if row['state']!='obsolete':transaction.cas_update(kind,key,expected,state='obsolete')
            if store.row(kind,key)['state']!='obsolete':raise Conflict('group withdrawal failed')
            return {'target':target,'state':'obsolete'}
        if domain=='M04' and kind=='tl_handoff' and action=='obsolete':
            if row['row_revision']!=expected:raise Conflict('handoff CAS differs')
            if row['state']=='published':return {'target':target,'state':'published_historical_fact','undo_delivery':False}
            if row['state'] not in ('obsolete','permanent_failure'):
                transaction.cas_update(kind,key,expected,state='obsolete',lease_worker_id=None,lease_expires_at=None)
            return {'target':target,'state':store.row(kind,key)['state'],'old_lease_unusable':True}
        if kind=='tl_input_dependency' and action=='block_input' and domain in DOMAINS:
            if row['row_revision']!=expected:raise Conflict('input CAS differs')
            if row['retention_state'] not in ('erased','erase_pending'):
                transaction.cas_update(kind,key,expected,retention_state='blocked')
            return {'target':target,'state':store.row(kind,key)['retention_state']}
        raise Forbidden('this domain has no actual adapter for requested action')
