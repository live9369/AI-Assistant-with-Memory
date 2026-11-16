"""G1 adversarial scenarios; failures are results, never hidden by a wrapper gate."""
import copy
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Forbidden,Stale,ToolResult,utc
from digital_life.application.runtime.execution import Executor
from digital_life.application.lifecycle.recovery import Recovery
from digital_life.application.services.memory import Memory
from digital_life.application.accounts.authorization import Policy
from digital_life.application.runtime.scheduling import Budget
from digital_life.application.runtime.engine import Engine
from digital_life.domain.contracts import RuntimeIdentity
from digital_life.infrastructure.llm.schemas import validate

RECOVERY_SCENARIOS={'committed_new_epoch','prepared_crash','receipt_crash'}

def material_smoke(h):
    activity=h.investigation(); _,outcome=h.finish(activity)
    receipt=h.s.read_artifact(outcome['receipt'])
    expected=h.case['public']['files'][h.case['public']['observation_path']]
    if h.case['world_events']: expected=h.case['world_events'][0]['replacement']
    h.check(receipt['evidence']['text']==expected,'fixture-observed-bytes-match')
    state=h.s.row('activities',activity)['state']
    h.check(state==('paused' if h.case['fixture_behavior']=='dormant' else 'completed'),'fixture-disposition',state=state)

def mechanism(h,name):
    if name.startswith('reuse_'):
        from evaluation.exploration.reuse_scenarios import run
        return run(h,name)
    actor=h.s.config()['controller']
    if name=='cross_process_gate':
        import subprocess,sys
        from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
        h.enable()
        code="import sys; from digital_life.application.lifecycle.control_plane import Control; c=Control(sys.argv[1],sys.argv[2]); print('attempting',flush=True); c.stop('g1-cross-process'); print('committed',flush=True); c.close()"
        with dispatch_gate(h.root):
            child=subprocess.Popen([sys.executable,'-c',code,str(h.root),h.s.instance_id],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            h.check(child.stdout.readline().strip()=='attempting','cross-process-request-seen')
            import select
            ready,_,_=select.select([child.stdout],[],[],0.05)
            h.check(not ready and h.c.state()['user_stopped']==0,'cross-process-stop-waits')
        out,err=child.communicate(timeout=5)
        h.check(child.returncode==0 and 'committed' in out and h.c.state()['user_stopped']==1,'cross-process-stop-commits',stderr=err)
        h.trace('cross_process_stop_observed',clock_scope='parent observation only, not child timestamp')
        return
    if name in ('late_policy_model','late_policy_tool','late_cancel_model','late_cancel_tool','blocked_attempt_audit'):
        a=h.investigation(); transport='model' if name.endswith('model') else 'tool'
        proposal=h.propose(a) if transport=='tool' else None
        def change():
            if name=='blocked_attempt_audit': h.stop('disable')
            elif 'cancel' in name: h.engine.cancel(a,actor)
            elif transport=='model': Policy(h.s).mode('authorization',[],actor)
            else:
                intent=h.s.row('action_intents',proposal['action_id']); Policy(h.s).revoke(intent['grant_id'],actor)
        before=len([e for e in h.trace_events if e['kind']=='dispatch'])
        with h.after_send_commit(transport,change):
            h.raises(Forbidden,lambda:h.propose(a) if transport=='model' else h.execute(proposal),'late-control-blocked')
        h.check(len([e for e in h.trace_events if e['kind']=='dispatch'])==before,'late-control-no-callback')
        if name=='blocked_attempt_audit':
            attempt=h.latest_attempt('action_attempts')
            h.check(attempt['state']=='failed','blocked-attempt-failed')
            h.check(not any(r['attempt_id']==attempt['id'] for r in h.s.rows('action_results')),'no-fabricated-unknown-result')
            budget=h.s.db.execute('SELECT * FROM budget_reservations WHERE operation_ref=?',(attempt['id'],)).fetchone()
            import json
            usage=json.loads(budget['actual_usage'])
            h.check(budget['state']=='settled' and usage['tool_calls']==0,'blocked-zero-tools-settled')
        return
    if name=='default_disabled_lock':
        h.check(not h.x.config()['enabled'] and h.x.tick(h.engine) is None,'default-disabled')
        h.x.configure(actor,True); h.raises(Forbidden,lambda:h.x.tick(h.engine),'locked-opt-in')
        h.check((h.root/'WAKE_DISABLED').exists(),'lock-remains'); return
    if name=='legacy_contract':
        h.enable(); activity=h.engine.submit('legacy fixture','legacy')
        h.engine.think(activity,h.model)
        request=h.s.rows('thought_requests')[-1]
        h.check(request['output_schema_version']==1,'legacy-V1'); return
    if name=='activity_budget':
        h.enable(max_activities=1); a=h.x.tick(h.engine); h.engine.think(a,h.model)
        h.check(h.tick_due() is None and h.x.status()['remaining_activities']==0,'activity-budget'); return
    if name=='user_priority':
        h.enable(); a=h.engine.submit('pending human work','user')
        h.check(h.x.tick(h.engine) is None,'user-priority')
        h.engine.cancel(a,actor); h.check(h.x.tick(h.engine) is not None,'priority-cleared'); return
    if name=='attempt_budget':
        h.enable(); a=h.x.tick(h.engine); h.model.fail=True
        for _ in range(3): h.raises(ContractError,lambda:h.engine.think(a,h.model),'injected-attempt-failure')
        before=len(h.model.inputs); h.raises(ContractError,lambda:h.engine.think(a,h.model),'fourth-attempt-blocked')
        h.check(len(h.model.inputs)==before,'no-fourth-model-dispatch'); return
    if name in ('tool_budget','token_budget'):
        h.enable(); a=h.x.tick(h.engine)
        kind='tool_attempt' if name=='tool_budget' else 'thought_attempt'
        with h.s.tx():
            if name=='tool_budget': h.s.db.execute('UPDATE activity_budget_accounts SET tool_call_limit=1 WHERE activity_id=?',(a,))
            else: h.s.db.execute('UPDATE activity_budget_accounts SET token_limit=4096 WHERE activity_id=?',(a,))
            op=h.s.root_object('g1-budget-probe'); Budget(h.s).reserve(a,op,kind,tokens=0 if name=='tool_budget' else 4096)
        h.raises(ContractError,lambda:Budget(h.s).reserve(a,'over-budget',kind,tokens=0 if name=='tool_budget' else 1),'budget-reservation-blocked'); return
    a=h.investigation()
    if name=='internal_source':
        signal=h.engine.details(a)[2]; channel=h.s.row('perception_channels',signal['channel_id'])
        h.check(channel['kind']=='internal' and signal['source_actor_id']==h.s.config()['self_actor'],'internal-provenance')
        motivations=[r for r in h.s.rows('motivation_states') if r['activity_id']==a]
        h.check(all(r['regulation_type']=='internal' for r in motivations),'internal-motivation'); return
    if name in ('forged_reference','exploration_contract'):
        def mutate(req,out):
            if name=='forged_reference': out['exploration']['evidence_refs']=['forged-evidence']
            else: out['schema_version']=1
        h.model.mutate=mutate; before=len(h.s.rows('action_intents'))
        h.raises(ContractError,lambda:h.propose(a),'invalid-output-rejected')
        h.check(len(h.s.rows('action_intents'))==before,'invalid-output-no-action'); return
    if name in ('revoke_reference','revise_reference'):
        h.engine.prepare(a,h.model)
        if name=='revoke_reference': Memory(h.s).restrict(h.memory['memory_id'],[actor],actor)
        else:
            with h.s.tx():
                ev=h.s.evidence(artifact=h.s.artifact({'corrected':True}))
                Memory(h.s).revise(h.memory['memory_id'],1,'Corrected fixture memory.',ev)
        count=len(h.model.inputs)
        h.raises(Forbidden,lambda:h.propose(a),'changed-source-rejected')
        h.check(len(h.model.inputs)==count,'source-block-before-dispatch'); return
    if name=='reconfigure':
        p=h.propose(a); old=h.x.config()['generation']; h.x.configure(actor,True)
        h.check(h.x.config()['generation']!=old,'new-generation')
        h.raises(Forbidden,lambda:h.execute(p),'old-generation-blocked'); return
    if name in ('unknown_result','failed_tool'):
        h.tool_outcome=ToolResult('timeout','unknown','unknown') if name=='unknown_result' else ToolResult('received','failed','fail')
        p=h.propose(a); h.execute(p)
        h.check(h.s.row('activities',a)['state']=='paused','bad-observation-pauses')
        h.raises(Forbidden,lambda:h.execute(p),'uncertain-result-not-replayed'); return
    if name=='model_failure':
        h.model.fail=True
        # Use a real queued job: discovery's direct call left its think job queued.
        with h.s.tx(): h.s.db.execute("UPDATE jobs SET state='cancelled' WHERE target_ref<>?",(a,))
        h.raises(ContractError,lambda:h.engine.process_one(h.model,h.backend),'model-job-failed')
        h.check(h.s.row('activities',a)['state']=='paused','failed-model-paused'); return
    if name=='prepared_crash':
        req,_=h.engine.prepare(a,h.model); h.engine=Engine(h.s,RuntimeIdentity(1,'post-crash'))
        before=len(h.model.inputs); h.raises(Stale,lambda:h.propose(a),'old-epoch-blocked')
        h.c.stop('recovery-stop'); result=Recovery(h.s).reconcile(actor)
        h.check(a in result['paused'] and len(h.model.inputs)==before,'recovery-continuity')
        h.check(h.s.row('thought_requests',req['id'])['accepted_result_id'] is None,'old-request-not-accepted'); return
    if name=='text_boundary':
        _,payload=h.engine.prepare(a,h.model); output=h.model.generate(payload)
        candidate=copy.deepcopy(h.x.questions()[h.x.binding(a)['question_id']]); candidate={k:candidate[k] for k in ('question','verification','expected_gain','cost','evidence_refs')}
        candidate['question']='q'*1000; output['exploration']['candidates']=[candidate]*4
        validate(output); h.check(True,'text-1000-and-four-candidates-valid')
        output['exploration']['candidates'][0]['question']='q'*1001
        h.raises(ContractError,lambda:validate(output),'text-1001-rejected')
        output['exploration']['candidates']=[dict(candidate,question='q') for _ in range(5)]
        h.raises(ContractError,lambda:validate(output),'five-candidates-rejected'); return
    if name in ('depth_boundary','capacity_boundary'):
        q=h.x.questions()[h.x.binding(a)['question_id']]
        with h.s.tx():
            if name=='depth_boundary': h.x.record(dict(q,depth=3))
            else:
                for i in range(255): h.x.record(dict(q,id='capacity-'+str(i),question='Reserved fixture '+str(i),state='resolved'))
        def candidate(req,out):
            out['exploration']['candidates']=[{'question':'A fresh child question','verification':'Read '+h.case['public']['observation_path'],'expected_gain':1,'cost':0,'evidence_refs':req['exploration']['allowed_evidence_refs'][:1]}]
        h.model.mutate=candidate; before=len(h.x.questions()); h.propose(a)
        h.check(len(h.x.questions())==before,'question-boundary-enforced',boundary=name); return
    if name=='question_dedup':
        q=h.x.questions()[h.x.binding(a)['question_id']]
        def duplicate(req,out):
            out['exploration']['candidates']=[{k:q[k] for k in ('question','verification','expected_gain','cost','evidence_refs')}]
        h.model.mutate=duplicate; h.propose(a)
        h.check(len(h.x.questions())==1,'question-dedup'); return
    if name=='single_acceptance':
        p=h.propose(a); count=len(h.model.inputs); result=h.propose(a)
        h.check(result['duplicate'] and len(h.model.inputs)==count,'single-acceptance'); return
    if name=='round_budget':
        h.model.always_continue=True
        for iteration in range(2):
            if iteration: (h.root/'workspace'/h.case['public']['observation_path']).write_text(h.case['public']['files'][h.case['public']['observation_path']]+'\n')
            h.execute(h.propose(a))
        h.propose(a)
        h.check(h.s.row('activities',a)['state']=='paused' and len(h.x.observations(a))==2,'round-budget'); return
    if name=='receipt_crash':
        p=h.propose(a); outcome=Executor(h.s,h.engine.identity).dispatch(p['action_id'],h.backend)
        count=len([e for e in h.trace_events if e['kind']=='dispatch' and e['transport']=='tool'])
        h.execute(p)
        after=len([e for e in h.trace_events if e['kind']=='dispatch' and e['transport']=='tool'])
        h.check(count==after and h.x.observations(a)[0]['result']==outcome['result'],'recovery-continuity'); return
    p=h.propose(a); outcome=h.execute(p)
    if name=='read_not_resolved':
        h.check(h.s.row('activities',a)['state']=='running','read-not-completed')
        h.check(h.engine.details(a)[3]['state']=='active','goal-not-completed'); return
    if name=='receipt_dedup':
        count=len(h.x.observations(a)); result=h.execute(p)
        h.check(result['duplicate'] and len(h.x.observations(a))==count,'receipt-dedup'); return
    if name=='committed_new_epoch':
        h.engine=Engine(h.s,RuntimeIdentity(1,'post-observation'))
        h.propose(a)
        h.check(h.s.row('activities',a)['state']=='completed','recovery-continuity')
        h.check(any(o['evidence_ref']==outcome['evidence'] for o in h.model.inputs[-1]['exploration']['observations']),'evidence-retained'); return
    raise ValueError('Unknown mechanism '+name)

def stop_matrix(h,spec):
    a=h.investigation(); control=spec['control']; stage=spec['stage']; transport=spec['transport']
    stop=lambda:h.stop(control,defer=stage=='in_flight' and control=='dispatch_competition')
    if transport=='model':
        if stage=='before_prepare': stop(); h.safe_call(lambda:h.propose(a))
        elif stage=='authorized_before_dispatch':
            # Model calls have no tool approval; boundary is the committed send reservation.
            h.engine.prepare(a,h.model)
            with h.after_send_commit('model',stop): h.safe_call(lambda:h.propose(a))
        elif stage=='in_flight': h.model.on_dispatch=stop; h.safe_call(lambda:h.propose(a)); h.await_stops()
        else: h.propose(a); stop()
        h.safe_call(lambda:h.propose(a))
    else:
        p=h.propose(a)
        if stage=='before_prepare': stop(); h.safe_call(lambda:h.execute(p))
        elif stage=='authorized_before_dispatch':
            with h.after_send_commit('tool',stop): h.safe_call(lambda:h.execute(p))
        elif stage=='in_flight': h.on_tool_dispatch=stop; h.safe_call(lambda:h.execute(p)); h.await_stops()
        else: h.execute(p); stop()
        h.safe_call(lambda:h.execute(p))
    audit=h.audit()
    h.check(audit['stop_boundaries']==1,'stop-boundary-observed')
    h.check(not audit['post_stop_dispatches'],'zero-post-stop-dispatch',violations=audit['post_stop_dispatches'])
