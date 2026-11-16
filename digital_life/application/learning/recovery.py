"""Owner-authorized continuation of the original work; no effect replay."""
from copy import deepcopy
from datetime import datetime,timedelta
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,utc,dumps
from digital_life.domain import tool_learning_contract as c
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore,StorageAuthority
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.application.learning.work import ToolLearningWork,_CurrentWorkAuthority
from digital_life.application.learning.budget import ToolLearningBudget


class RecoveryAuthority(StorageAuthority):
    def verify_reconciliation(self,entry,request,work,record,stage):
        raise Forbidden('current original-work recovery owner is not configured')
    def verify_conditions(self,entry,request,work,conditions,stage):
        raise Forbidden('actual condition owners have not attested resolution')
    def verify_read_accounting(self,entry,request,work,stage):
        raise Forbidden('original bounded recovery read operation is not configured')


class ToolLearningRecovery(ToolLearningWork):
    def __init__(self,store,authority=None,clock=utc,max_rows=256):
        self.s=store;self.authority=authority or RecoveryAuthority();self.clock=clock
        if type(max_rows) is not int or max_rows<1:raise ContractError('finite reconciliation row limit required')
        self.max_rows=max_rows
        self.storage=ToolLearningStore(store,_CurrentWorkAuthority(self))

    def _attest(self,name,*args):
        if getattr(self.authority,name)(args[0],*deepcopy(args[1:])) is not None:
            raise Forbidden('recovery authority must attest by successful return')

    def facts(self,work_id):
        """Read-only bounded persistent evidence, never permission to retry."""
        work=self.s.row('tl_work',work_id);result={}
        for table in ('tl_command','tl_decision','tl_handoff','tl_product'):
            rows=self.s.db.execute('SELECT * FROM '+table+' WHERE instance_id=? AND work_id=? ORDER BY id LIMIT ?',(self.s.instance_id,work_id,self.max_rows+1)).fetchall()
            if len(rows)>self.max_rows:raise Forbidden('persistent reconciliation coverage is incomplete')
            result[table]=[dict(row) for row in rows]
        result['work']={key:work[key] for key in ('id','state','phase','review_round','row_revision','budget_account_id','deadline')}
        return result

    def resume(self,entry,envelope):
        c.validate_request('resume_work',envelope);request=c.loads(dumps(envelope))
        with dispatch_gate(self.s.root):
            self._guard_request(request)
            return self.storage.execute(entry,'resume_work',request,lambda tx:self._resume(tx,entry,request))

    def _resume(self,tx,entry,request):
        payload=request['payload'];reference=payload['work']
        self.storage.validate_ref(reference,expected_kind='tl_work')
        if request['work_ref']['status']!='known' or request['work_ref']['value']!=reference:raise Conflict('resume must bind the original work')
        work=self.s.row('tl_work',reference['id'])
        if payload['expected_work_revision']!=work['row_revision']:raise Conflict('work continuation CAS changed')
        if request['expected']['status']!='known' or request['expected']['value']!={'object':reference,'revision':work['row_revision'],'epoch':0}:raise Conflict('resume expected token differs')
        if work['state'] not in ('waiting','blocked','failed','stopped'):raise Forbidden('only explicitly suspended work may resume')
        if work['phase'] not in ('assess','decide','represent'):raise Forbidden('no legal persisted continuation point')
        self._attest('verify_read_accounting',entry,request,dict(work),'reconcile')
        status=ToolLearningBudget(self.s,clock=self.clock).check_work(work['id'],request['budget'])
        if any(reason!='work_'+work['state'] for reason in status['block_reasons']):raise Forbidden('original work budget/deadline is not available')
        self.storage.validate_ref(payload['reconciliation'],expected_kind='artifacts')
        record=self.storage.read_artifact(payload['reconciliation']['id'])
        required={'contract','instance_id','work_id','expected_work_revision','phase','review_round','conditions','facts'}
        if type(record) is not dict or set(record)!=required or record['contract']!='TL-WORK-RECONCILIATION-1':raise ContractError('closed reconciliation record required')
        expected={'contract':'TL-WORK-RECONCILIATION-1','instance_id':self.s.instance_id,'work_id':work['id'],'expected_work_revision':work['row_revision'],'phase':work['phase'],'review_round':work['review_round'],'conditions':payload['conditions'],'facts':self.facts(work['id'])}
        # The currently executing pending resume command is not a previously
        # uncertain operation and is excluded from the fixed evidence snapshot.
        expected['facts']['tl_command']=[row for row in expected['facts']['tl_command'] if row['id']!=request['command_id']]
        if record!=expected:raise Conflict('reconciliation differs from actual persistent state')
        if any(row['state']!='committed' for row in record['facts']['tl_command']):raise Conflict('unresolved original commit outcome')
        for condition in payload['conditions']:self.storage.validate_ref(condition)
        self._attest('verify_reconciliation',entry,request,dict(work),record,'begin')
        self._attest('verify_conditions',entry,request,dict(work),payload['conditions'],'begin')
        if work['phase']=='assess' and record['facts']['tl_product']:raise Conflict('committed assessment must be reconciled forward, not regenerated')
        if work['phase']=='represent' and not any(row['state'] not in ('published','obsolete','permanent_failure') for row in record['facts']['tl_handoff']):raise Conflict('no unfinished original representation obligation')
        condition=self.storage.read_artifact(work['conditions_artifact_id'])
        condition['resume_conditions']=[];condition['reason']='owner-reconciled-continuation'
        conditions_id=tx.put_artifact(condition)
        target='handoff_pending' if work['phase']=='represent' else 'processing'
        review=work['review_round']+(1 if work['phase']=='decide' else 0)
        tx.cas_update('tl_work',work['id'],work['row_revision'],state=target,phase=work['phase'],review_round=review,conditions_artifact_id=conditions_id)
        self._attest('verify_reconciliation',entry,request,dict(work),record,'commit')
        self._attest('verify_conditions',entry,request,dict(work),payload['conditions'],'commit')
        self._guard_request(request)
        return self._response(request,work,operation='resume_work')


class ContinuedErasure:
    """A new M12 resource grant for the same immutable plan and target rows.

    Old consumption and unknown outcomes are never overwritten. No dispatch or
    restore authority is conveyed by this local maintenance opportunity.
    """
    def __init__(self,erasure):self.e=erasure;self.s=erasure.s

    def authorize(self,bearer,plan_id,caps,deadline,continuation_id):
        from digital_life.application.learning.maintenance import ControllerMaintenanceAuthority
        from digital_life.application.learning.propagation import ManagedErasure
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
        from digital_life.domain import tool_learning_types as t
        from digital_life.domain.contracts import identifier
        a=self.e.authority
        if not isinstance(a,ControllerMaintenanceAuthority):raise Forbidden('real current controller maintenance authority required')
        caps=deepcopy(caps);t.obj(caps,('scan','items','bytes','elapsed_ms','attempts'))
        for value in caps.values():t.integer(value,1,2**53-1)
        if caps['attempts']!=1:raise Forbidden('continuation has no model/tool authorization')
        c.validate('UTC',deadline);t.string(continuation_id)
        with dispatch_gate(self.s.root):
            actor=a._controller(bearer);active,policy,control=a._current();root=a._registered_root()
            limits=c.loads(policy['scope']).get('tool_learning_maintenance_limits')
            if policy['authority']!=actor or not isinstance(limits,dict) or set(limits)!=set(caps) or any(caps[k]>limits[k] for k in caps):raise Forbidden('current explicit maintenance limits do not cover continuation')
            if deadline<=a.clock() or deadline>(datetime.fromisoformat(a.clock().replace('Z','+00:00'))+timedelta(milliseconds=caps['elapsed_ms'])).isoformat(timespec='milliseconds').replace('+00:00','Z'):raise Forbidden('continuation deadline exceeds current finite grant')
            row,journal=self.e._journal(plan_id);plan=journal['plan']
            if journal['unknown'] or journal['entered']:raise Forbidden('old unknown physical outcome requires reconciliation before continuation')
            prior=journal.get('continuations',{}).get(continuation_id)
            if prior:
                if prior['caps']!=caps or prior['deadline']!=deadline:raise Conflict('continuation key has different resource semantics')
                event=self.s.row('runtime_events',prior['grant_id']);body=a.storage.read_artifact(event['payload_artifact_id'])
                grant=a._mint(event['id'],body,plan);a._session(grant['entries']['M12'],plan)
                return grant
            # The original controller plan authoring is required, not merely
            # a caller-constructed physical journal with similar target names.
            original=self.s.db.execute("SELECT * FROM runtime_events WHERE instance_id=? AND source='tl.maintenance.controller' AND source_event_id=?",(self.s.instance_id,plan_id)).fetchone()
            if original is None:raise Forbidden('original authenticated plan provenance missing')
            old=a.storage.read_artifact(original['payload_artifact_id'])
            if old['plan_digest']!=c.fingerprint(plan) or original['payload_hash']!=c.fingerprint(old):raise Conflict('original plan authorization changed')
            meter=PhysicalReadMeter({'input_tokens':0,'output_tokens':0,'tool_calls':0,**caps},deadline,clock=a.clock)
            with meter.installed(self.s):
                source=a._source_owner(plan,actor);a._actual_f1_provenance(plan['barrier_id'])
                targets=self.s.db.execute('SELECT target_ref_id,location_kind FROM tl_erasure_target WHERE instance_id=? AND plan_ref_id=? ORDER BY id LIMIT ?',(self.s.instance_id,plan_id,len(plan['targets'])+1)).fetchall()
                if {(x['target_ref_id'],x['location_kind']) for x in targets}!={(x['target']['id'],x['location']) for x in plan['targets']}:raise Conflict('immutable original target set differs')
                meter.time()
            usage=meter.usage()
            if usage is None:raise Forbidden('continuation authorization usage is unknown')
            body={'contract':'TL-CONTROLLER-MAINTENANCE-GRANT-1','plan_id':plan_id,'plan_digest':c.fingerprint(plan),'barrier_id':plan['barrier_id'],'source_epoch':plan['source_epoch'],'controller_id':actor,'policy_id':policy['id'],'policy_epoch':active['epoch'],'control_revision':control['control_revision'],'runtime_epoch':control['runtime_epoch'],'exclusion_root':str(a.exclusion_root),'root_registration_id':root['id'],'deadline':deadline,'domains':['M12'],'actions':{},'inventory_ids':old['inventory_ids'],'bootstrap_usage':usage}
            with self.s.tx():
                now,_,current=a._current()
                if now!=active or current!=control:raise Conflict('continuation authorization changed during review')
                source_activity=self.s.row('activities',plan['source_activity']);activity=identifier();account=identifier()
                self.s.insert('activities',id=activity,trigger_event_id=source_activity['trigger_event_id'],state='pending',release_id=source_activity['release_id'],publication_state='ready',deadline=deadline,budget_json={'contract':'TL-MAINTENANCE-BUDGET-1','plan_id':plan_id,'caps':caps})
                self.s.insert('activity_budget_accounts',id=account,activity_id=activity,token_limit=0,tool_call_limit=0,attempt_limit=1,time_limit_ms=caps['elapsed_ms'])
                grant_id=self.s.event('maintenance.controller_authorized',payload=body,source='tl.maintenance.controller',key='continuation:'+continuation_id,lane='control')
                record={'grant_id':grant_id,'activity_id':activity,'account_id':account,'caps':caps,'deadline':deadline,'used':{key:usage[key] for key in caps},'unknown':False,'entered':False}
                journal.setdefault('continuations',{})[continuation_id]=record;self.e._save(plan_id,journal)
            return a._mint(grant_id,body,plan)

    def run(self,entry,plan_id,continuation_id):
        from digital_life.application.learning.propagation import RETAINED_METADATA
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
        a=self.e.authority
        with dispatch_gate(self.s.root):
            row,journal=self.e._journal(plan_id);plan=journal['plan'];record=journal.get('continuations',{}).get(continuation_id)
            if record is None:raise Forbidden('no fixed original-plan continuation ledger')
            binding=a._session(entry,plan)
            if binding['module']!='M12' or binding['grant_id']!=record['grant_id']:raise Forbidden('continuation uses another current grant')
            if record['unknown'] or record['entered'] or journal['unknown'] or journal['entered']:raise Forbidden('unknown maintenance consumption cannot be retried')
            account=self.s.row('activity_budget_accounts',record['account_id']);activity=self.s.row('activities',record['activity_id'])
            if account['activity_id']!=activity['id'] or (account['token_limit'],account['tool_call_limit'],account['attempt_limit'],account['time_limit_ms'])!=(0,0,1,record['caps']['elapsed_ms']) or activity['deadline']!=record['deadline'] or c.loads(activity['budget_json'])!={'contract':'TL-MAINTENANCE-BUDGET-1','plan_id':plan_id,'caps':record['caps']}:raise Conflict('continuation actual resource mapping differs')
            if not plan['allow_control_metadata'] or not RETAINED_METADATA<=set(plan['retained_metadata']):raise Forbidden('plan does not permit necessary fixed metadata')
            amounts={'input_tokens':0,'output_tokens':0,'tool_calls':0,**{key:max(0,record['caps'][key]-record['used'][key]) for key in record['caps']}}
            meter=PhysicalReadMeter(amounts,record['deadline'],clock=a.clock)
            with self.s.tx():record['entered']=True;self.e._save(plan_id,journal)
            failure=None;verified=False
            try:
                with meter.installed(self.s):
                    self.e.exclusions.read(entry,plan)
                    secure=self.s.db.execute('PRAGMA secure_delete=ON').fetchone()
                    if secure is None or secure[0]!=1:raise Forbidden('secure SQLite deletion unavailable')
                    for target in plan['targets']:
                        a.verify_target(entry,plan,target,'continuation_execute')
                        if a.clock()>=record['deadline']:raise Forbidden('continuation deadline exhausted')
                        result=self.e._target(entry,plan,target)
                        a.verify_target(entry,plan,target,'continuation_verified')
                        with self.s.tx():
                            target_row=self.s.db.execute('SELECT * FROM tl_erasure_target WHERE instance_id=? AND plan_ref_id=? AND target_ref_id=? AND location_kind=?',(self.s.instance_id,plan_id,target['target']['id'],target['location'])).fetchone()
                            proof=self.s.artifact({'contract':'TL-ERASURE-TARGET-VERIFICATION-1','plan_id':plan_id,'barrier_id':plan['barrier_id'],'target_id':target['target']['id'],'location':target['location'],'result':result,'verified_at':a.clock()})
                            changed=self.s.db.execute('UPDATE tl_erasure_target SET state=?,verification_artifact_id=?,row_revision=row_revision+1 WHERE instance_id=? AND id=? AND row_revision=?',(result['state'],proof,self.s.instance_id,target_row['id'],target_row['row_revision'])).rowcount
                            if changed!=1:raise Conflict('original cleanup target CAS changed')
                            journal['steps'][target['target']['id']+':'+target['location']]=result;self.e._save(plan_id,journal)
                    if any(t['location']=='database' for t in plan['targets']):
                        self.e._compact_database();journal['database_compaction_verified']=True
                    a.verify_inventory(entry,plan,'continuation_final');meter.time()
                    verified=all(self.e._verify_target(plan,t) for t in plan['targets'])
                    a._session(entry,plan)
                    if a.clock()>=record['deadline']:raise Forbidden('continuation expired after verification')
            except BaseException as exc:failure=exc
            finally:
                usage=meter.usage();actual=meter.actual if usage is None else usage
                with self.s.tx():
                    for key in record['caps']:record['used'][key]+=actual[key]
                    record['entered']=False;record['unknown']=usage is None
                    complete=bool(plan['targets']) and verified and plan['coverage']['state']=='complete' and not plan['coverage']['missing'] and not plan['coverage']['truncated']
                    self.e._save(plan_id,journal,'verified' if complete and failure is None else 'blocked')
            if failure:raise failure
            return {'plan_id':plan_id,'continuation_id':continuation_id,'local_verified':verified,'f3_complete':False,'original_resources_unchanged':True}


def _reconcile_stopped_work(store,bearer,max_rows=256):
    """Authenticated existing crash-recovery entry; no resume or effect replay.

    Classifies committed stage facts before any new lease/round is possible.
    Incomplete or uncertain outcomes remain blocked on the original work.
    """
    from digital_life.application.learning.runtime import authenticate_controller
    from digital_life.application.lifecycle.control_plane import Control
    from digital_life.application.learning.eligibility import slot
    if type(max_rows) is not int or not 1<=max_rows<=65536:raise ContractError('bounded recovery coverage required')
    with dispatch_gate(store.root):
        controller=authenticate_controller(store,bearer)
        control=Control(store.root,store.instance_id)
        try:
            current=control.state()
            if not current['user_stopped'] or current['active_process_run_id'] is not None or control.db.execute('SELECT 1 FROM process_runs WHERE instance_ref=? AND exited_at IS NULL LIMIT 1',(store.instance_id,)).fetchone():raise Forbidden('stop and reconcile actual process ownership before work crash classification')
            rows=store.db.execute("SELECT * FROM tl_work WHERE instance_id=? AND state IN ('processing','awaiting_decision','handoff_pending') ORDER BY id LIMIT ?",(store.instance_id,max_rows+1)).fetchall()
            if len(rows)>max_rows:raise Forbidden('work crash reconciliation coverage incomplete')
            service=ToolLearningRecovery(store,max_rows=max_rows);results=[]
            with store.tx():
                for row in rows:
                    work=dict(row);facts=service.facts(work['id']);uncertain=any(c['state']!='committed' for c in facts['tl_command'])
                    handoffs=facts['tl_handoff'];decisions=facts['tl_decision'];products=facts['tl_product']
                    state='blocked';phase=work['phase'];reason='crash-owner-recheck-required'
                    if uncertain:reason='original-commit-outcome-unresolved'
                    elif handoffs:
                        if all(h['state']=='published' and h['receipt_artifact_id'] and h['representation_id'] for h in handoffs):
                            # Verify actual immutable C2 receipt mappings before
                            # projecting completion; a state label is not proof.
                            for handoff in handoffs:
                                representation=store.row('tl_representation',handoff['representation_id'])
                                receipt=service.storage.read_artifact(handoff['receipt_artifact_id'])
                                if representation['content_revision_id']!=handoff['content_revision_id'] or receipt.get('contract')!='TL-C2-RECEIPT-1' or receipt['handoff']['id']!=handoff['id'] or receipt['representation']['id']!=representation['id'] or receipt['lease_generation']!=handoff['lease_generation']:raise Conflict('published receipt belongs to another obligation')
                            state='completed';phase='complete';reason='persistent-c2-published-no-replay'
                        else:phase='represent';reason='persistent-c1-unfinished-original-handoff'
                    elif decisions:
                        latest=[d for d in decisions if d['review_round']==work['review_round']]
                        if latest and all(d['operation'] in ('reject','reuse') for d in latest):
                            state='rejected' if any(d['operation']=='reject' for d in latest) else 'no_change';phase='complete';reason='persistent-c1-terminal-no-replay'
                        else:phase='decide';reason='persistent-c1-needs-owner-condition'
                    elif products:
                        if {p['product_type'] for p in products}=={'ObservationExtract','ComparisonAssessment','UpdateProposal','EffectAssessment'}:phase='decide';reason='persistent-assessment-no-regeneration'
                        else:reason='partial-assessment-requires-owner-reconciliation'
                    # Reuse the existing condition reference. Crash control
                    # must not copy source metadata/body after a protective F1.
                    artifact=work['conditions_artifact_id']
                    changed=store.db.execute('UPDATE tl_work SET state=?,phase=?,conditions_artifact_id=?,row_revision=row_revision+1 WHERE instance_id=? AND id=? AND row_revision=?',(state,phase,artifact,store.instance_id,work['id'],work['row_revision'])).rowcount
                    if changed!=1:raise Conflict('work crash classification CAS changed')
                    results.append({'work_id':work['id'],'before_revision':work['row_revision'],'state':state,'phase':phase,'reason':reason,'automatic_replay':False})
                fresh=control.state()
                if fresh!=current:raise Conflict('current crash-recovery control changed')
                event=store.event('recovery.tl_work_reconciled',payload={'controller_id':controller,'control_revision':current['control_revision'],'work_results':results,'automatic_replay':False,'budget_reset':False},source='tl.recovery.classification',lane='control')
            return {'event_id':event,'works':results,'automatic_replay':False}
        finally:control.close()


def reconcile_stopped_work(store,bearer,max_rows=256):
    """One authenticated bounded control command, never a free business stage."""
    from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
    from digital_life.application.learning.runtime import authenticate_controller
    from digital_life.domain.contracts import identifier
    from digital_life.domain.tool_learning_resources import DIMENSIONS
    command_id=identifier();amounts={key:0 for key in DIMENSIONS};amounts.update(scan=1024,items=1024,bytes=1048576,elapsed_ms=1000)
    meter=PhysicalReadMeter(amounts,utc(1));outcome='failed';result=None
    with dispatch_gate(store.root):
        controller=authenticate_controller(store,bearer)
        try:
            with meter.installed(store):
                active=store.db.execute('SELECT policy_version_id FROM policy_epochs WHERE instance_id=?',(store.instance_id,)).fetchone()
                if active:
                    policy=store.row('policy_versions',active['policy_version_id']);profile=c.loads(policy['scope']).get('recovery_control_limits')
                    if profile is not None:
                        if not isinstance(profile,dict) or set(profile)!={'scan','items','bytes','elapsed_ms'}:raise ContractError('invalid recovery control limits')
                        for key,value in profile.items():
                            if type(value) is not int or value<1 or value>amounts[key]:raise Forbidden('current recovery policy may only tighten fixed control caps')
                            meter.limits[key]=value
                result=_reconcile_stopped_work(store,bearer,max_rows);meter.time();outcome='classified'
                return dict(result,control_command_id=command_id)
        finally:
            # Scope consumption is control metadata only. Failure/unknown is
            # not a business opportunity, resume authorization or retry grant.
            with store.tx():store.event('recovery.control_scope_settled',payload={'command_id':command_id,'controller_id':controller,'caps':dict(meter.limits),'usage':meter.usage(),'measured':dict(meter.actual),'unknown':meter.usage() is None,'outcome':outcome,'full_coverage':result is not None,'business_resume':False},source='tl.recovery.control',key=command_id,lane='control')
