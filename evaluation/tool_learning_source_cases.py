"""Actual original tool receipts and derived-view/input identity fixtures."""
import copy
import json
from pathlib import Path
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,ToolResult,identifier,utc
from digital_life.application.learning.eligibility import ref,slot


def original_tool_receipt(variant):
    from tests.test_tool_learning_runtime import StrictActualUseTests
    from digital_life.application.learning.execution import StrictActionExecutor
    from digital_life.application.learning.runtime_learning import StrictLearningCoordinator
    f=StrictActualUseTests();f.setUp()
    try:
        s=f.s;request,result,intent,scope=f.producer({'tool':'read_file','arguments':{'path':'synthetic-original.txt'}})
        marker=s.root/'workspace'/'im19-actual-tool-entries.jsonl'
        def backend(action,root,key):
            with open(marker,'a') as stream:stream.write(json.dumps({'action':action,'original_key':key})+'\n')
            if variant=='body_available':return ToolResult('received','succeeded','pass',{'inventory':10})
            if variant=='failed':return ToolResult('received','failed','fail',{},'permission denied; no inventory reading')
            if variant=='partial':return ToolResult('received','unknown','fail',{'received_pages':[1],'missing_pages':[2],'receipt_id':'partial-original-call'})
            return ToolResult('received','succeeded','pass',{'receipt_id':'opaque-original-call-only'})
        executor=StrictActionExecutor(s,f.f.identity,f.k)
        original=executor.dispatch(intent,backend)
        coordinator=StrictLearningCoordinator(f.k)
        locator={'kind':'json_pointer','pointer':'/error' if variant=='failed' else '/evidence/inventory' if variant!='partial' else '/evidence/page2/inventory'}
        work=coordinator.admit(f.activity,original['result'],locator,interpret=False)
        before=s.row('tl_work',work['id']);response=coordinator.assess(work['id'])
        products=[s.read_artifact(row[0]) for row in s.db.execute('SELECT payload_artifact_id FROM tl_product WHERE work_id=?',(work['id'],))]
        receipt=s.read_artifact(original['receipt'])
        entries=[json.loads(line) for line in marker.read_text().splitlines()]
        if len(entries)!=1:raise AssertionError('source learning redispatched the original tool')
        if variant in ('body_available','failed'):
            extract=next(p for p in products if p['product_type']=='ObservationExtract')['body']['observations'][0]
            expected='permission denied; no inventory reading' if variant=='failed' else 10
            if extract['value']['value']!=expected:raise AssertionError('did not read the actual original artifact field')
            if extract['evidence'][0]['original_result']!=slot(ref(s,original['result'])) or extract['evidence'][0]['receipt']!=slot(ref(s,original['receipt'])):raise AssertionError('original result/receipt identity lost')
        else:
            if products or response['disposition']!='deferred' or s.row('tl_work',work['id'])['state']!='waiting':raise AssertionError('missing original content was invented or not finite waiting')
            if before['deadline']!=s.row('tl_work',work['id'])['deadline']:raise AssertionError('wait renewed original deadline')
        repeat=executor.dispatch(intent,backend) if variant in ('body_available','receipt_only') else None
        if variant in ('failed','partial'):
            try:executor.dispatch(intent,backend)
            except ContractError:pass
            else:raise AssertionError('failed/unknown original action was eligible for automatic replay')
        if variant in ('body_available','receipt_only') and not repeat.get('duplicate'):raise AssertionError('original successful receipt reissued')
        if len(marker.read_text().splitlines())!=1:raise AssertionError('same original external action was replayed')
        return {'case_ids':['Q04-A02','Q03-A05' if variant=='failed' else 'Q03-A06' if variant=='partial' else 'Q05-A02'],
            'variant':variant,'endpoint':'actual_original_field_extracted' if products else 'finite_wait_missing_original_field',
            'original_action':original,'actual_receipt':receipt,'actual_tool_entry_witnesses':entries,'actual_response':response,'actual_products':products,
            'work_before':before,'work_after':s.row('tl_work',work['id']),'original_attempts':[dict(row) for row in s.db.execute('SELECT * FROM action_attempts WHERE intent_id=?',(intent,))],
            'original_action_replayed':False,'real_model_called':False}
    finally:f.doCleanups()


def derived_view(variant):
    from tests.test_tool_learning_observation import ObservationTests
    from digital_life.domain import tool_learning_contract as c
    f=ObservationTests();f.setUp()
    try:
        s=f.s;inner={'inventory':10,'note':'中文😀不是无条件结论'}
        outer={'evidence':{'text':json.dumps(inner,ensure_ascii=False)}}
        artifact=s.artifact(outer)
        signal=s.insert('perception_signals',channel_id=s.db.execute('SELECT id FROM perception_channels LIMIT 1').fetchone()[0],source_actor_id=s.config()['controller'],artifact_id=artifact,received_at=utc())
        decoded=c.loads(c.resolve_locator({'kind':'json_pointer','pointer':'/evidence/text'},outer))
        if decoded!=inner:raise AssertionError('actual strict two-level decode changed source values')
        view=s.artifact(decoded if variant!='text_location' else '来源报告：中文😀不是无条件结论')
        proof=s.event('im19.actual_view_transformation',payload={'original':ref(s,artifact),'original_locator':{'kind':'json_pointer','pointer':'/evidence/text'},'decoder':'strict-json-then-identity-text' if variant=='text_location' else 'strict-json','view':ref(s,view),'view_digest':s.row('artifacts',view)['hash']})
        f.source.update(source=ref(s,signal),artifact=ref(s,artifact),digest={'algorithm':'sha256','hex':s.row('artifacts',artifact)['hash']},view=slot(ref(s,view)),view_digest=slot({'algorithm':'sha256','hex':s.row('artifacts',view)['hash']}),derivation_refs=[ref(s,proof)])
        f.source['origin_method'].update(name='im19-strict-json-view',version='1',request_ref=slot(ref(s,proof)))
        if variant=='text_location':
            # JSON string decoding yields a real str; offsets are codepoints of
            # that explicit view, not the original wrapper or UTF-8 byte offset.
            f.source['locator']={'kind':'text_range','start':5,'end':len('来源报告：中文😀不是无条件结论'),'quote':slot('中文😀不是无条件结论')}
        else:f.source['locator']={'kind':'json_pointer','pointer':'/inventory'}
        if variant=='wrong_view_digest':f.source['view_digest']['value']['hex']='f'*64
        if variant=='wrong_view_locator':f.source['locator']={'kind':'json_pointer','pointer':'/evidence/text/inventory'}
        f.authority.source_token=lambda entry,request:{'object':copy.deepcopy(request['payload']['source']['source']),'revision':0,'epoch':0}
        f.request['budget'].update(max_bytes=90000,max_scan=100,max_items=100)
        f.prepare();source=copy.deepcopy(f.source)
        from digital_life.application.learning.engine import _dependency
        token={'object':ref(s,signal),'revision':0,'epoch':0}
        for consumer in (ref(s,view),ref(s,proof)):
            for edge in ('read','delete'):_dependency(s,consumer,token,f.plan['scope'],edge,'/actual_view_conversion','learn')
        error=None;response=None
        try:response=f.assess()
        except ContractError as exc:error=type(exc).__name__+': '+str(exc)
        products=f.products()
        if variant in ('json_nested','text_location'):
            claim=next(p for p in products if p['product_type']=='ObservationExtract')['body']['observations'][0]
            expected='中文😀不是无条件结论' if variant=='text_location' else 10
            if claim['value']['value']!=expected or claim['evidence'][0]!=source:raise AssertionError('view position/original transformation linkage lost')
            if claim['evidence'][0]['source']!=ref(s,signal) or claim['evidence'][0]['view']['value']!=ref(s,view):raise AssertionError('derived view masqueraded as the original top-level object')
        elif products or error is None and response['disposition']!='deferred':raise AssertionError('bad view digest/location was silently accepted')
        return {'case_ids':['Q05-A14','Q05-A15','Q05-A12'],'variant':variant,'source':source,'actual_outer':outer,'actual_decoded':decoded,'transformation_proof':s.read_artifact(s.row('runtime_events',proof)['payload_artifact_id']),
            'view_dependency_rows':[dict(row) for row in s.db.execute('SELECT * FROM tl_dependency WHERE consumer_ref_id IN (?,?)',(view,proof))],
            'actual_response':response,'actual_products':products,'error':error,'real_model_called':False,
            'scope':'actual qualified synthetic source/view port and M14 parser; real strict coordinator still rejects unregistered parsed-view owners'}
    finally:f.doCleanups()
