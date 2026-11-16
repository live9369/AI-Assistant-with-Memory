"""AE-RUNTIME-1.2 adversarial resource/admission trials, sealed before execution."""
from unittest.mock import patch
from digital_life.application.autonomy.exploration_evidence import ExplorationEvidence
from digital_life.application.services.memory import Memory
from digital_life.domain.contracts import Forbidden,ToolResult,utc

def run(h,name):
    ev=ExplorationEvidence(h.x);path=h.case['public']['observation_path']
    if name=='reuse_candidate_filter':
        h.enable();a=h.x.tick(h.engine)
        def proposals(req,out):
            valid=out['exploration']['candidates'][0]
            out['exploration']['candidates']=[dict(valid,question='Retrieve an internal event?',verification='Look up event/evidence/result IDs'),valid]
        h.model.mutate=proposals;h.propose(a)
        h.check(len(h.x.questions())==1,'valid-sibling-survives')
        h.check(h.x.payloads('exploration.candidate_filtered')[0]['reason']=='no-executable-verification-path','infeasible-proposal-audited');return
    if name=='reuse_conservative_identity':
        q={'id':'q','question':'所有回声是否都相隔两个 tick？','verification':'Read '+path};plans=ev.plan(q['verification'])
        h.check(ev.duplicate(dict(q,question='回声是否始终相隔两个 tick？'),plans,{'q':q})=='q','quantifier-alias')
        for text in ('所有回声是否都相隔三个 tick？','所有回声是否都不相隔两个 tick？','所有灯光是否都为蓝色？'):
            h.check(ev.duplicate(dict(q,question=text),plans,{'q':q}) is None,'distinct-claim-survives',question=text)
        return
    a=h.investigation()
    if name=='reuse_failed_receipt':
        p=h.propose(a);h.tool_outcome=ToolResult('received','failed','fail');h.execute(p)
        h.check(not ev.current(),'failed-receipt-not-cached');return
    h.finish(a);original=next(iter(h.x.questions().values()))
    if name=='reuse_resource_changed':
        (h.root/'workspace'/path).write_text('Changed synthetic measurement, new revision.')
        h.check(not ev.current(),'changed-file-invalidates-cache')
        h.check(ev.changed(original,ev.plan(original['verification'])),'change-recognized')
        with patch('digital_life.application.autonomy.exploration.utc',side_effect=lambda seconds=0:utc(7200+seconds)):
            d=h.x.tick(h.engine)
        h.propose(d);q=h.x.questions()[original['id']]
        h.check(len(h.x.questions())==1 and q['state']=='candidate' and q['resource_revision']==1 and q['visits']==0,'changed-resource-reopens-canonical-id');return
    if name=='reuse_acl_withdrawn':
        Memory(h.s).restrict(h.memory['memory_id'],[h.s.config()['controller']],h.s.config()['controller'])
        h.check(not ev.current(),'source-withdrawal-invalidates-cache');return
    with h.s.tx():h.x.record(dict(original,id='different-question',question='Which fields are recorded?',state='candidate',visits=0,assessment='Not evaluated.',activity=None))
    with patch('digital_life.application.autonomy.exploration.utc',side_effect=lambda seconds=0:utc(7200+seconds)):b=h.x.tick(h.engine)
    if name=='reuse_prepared_stale':
        _,payload=h.engine.prepare(b,h.model);(h.root/'workspace'/path).write_text('Changed after preparation.')
        h.raises(Forbidden,lambda:h.x.check_inputs(b,payload),'prepared-shared-context-rejected');return
    before=len(h.s.rows('action_attempts'))
    if name=='reuse_shared_receipt':
        h.propose(b)
        h.check(h.s.row('activities',b)['state']=='completed','shared-receipt-allows-resolution')
    elif name=='reuse_unchanged_bounded':
        h.model.always_continue=True;result=h.propose(b)
        h.check(result['evidence_reused'] and h.x.observations(b)[0]['reused'],'original-receipt-reused')
        h.propose(b);h.check(h.s.row('activities',b)['state']=='paused','repeated-unchanged-observation-paused')
    else:raise ValueError(name)
    h.check(len(h.s.rows('action_attempts'))==before,'no-extra-tool-attempt')
