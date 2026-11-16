"""IM19 real fresh-provider / workspace-tool concurrency against actual TL gates.

The original work ledger, source dependencies and control owner paths are real.
Transport responses are deterministic and no model/network/backend service runs.
"""
import copy
import json
import multiprocessing
import os
from pathlib import Path
import threading
import time
import traceback


def event(root, kind, **fields):
    record = dict(kind=kind, pid=os.getpid(), thread=threading.get_ident(), **fields)
    with open(Path(root) / 'im19-order.jsonl', 'a') as stream:
        stream.write(json.dumps(record) + '\n'); stream.flush(); os.fsync(stream.fileno())
    (Path(root) / ('im19-' + kind)).touch()


def await_marker(root, kind, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (Path(root) / 'im19-abort').exists():
            raise RuntimeError('parent aborted synthetic fixture')
        if (Path(root) / ('im19-' + kind)).exists():
            return
        time.sleep(.005)
    raise TimeoutError('missing rendezvous ' + kind)


def controller_worker(root, change, request, activity, wait_for):
    from digital_life.infrastructure.persistence.sqlite_store import Store
    from digital_life.application.lifecycle.control_plane import Control
    from digital_life.application.monitoring.management import Management
    from digital_life.application.learning.invalidation import ToolLearningInvalidation
    from tests.test_tool_learning_invalidation import MechanicalInvalidation
    store = None
    try:
        # A fresh connection is opened before readiness in both modes.
        if not (Path(root) / 'IM01_FIXTURE.json').is_file():
            raise ValueError('synthetic fixture marker missing')
        store = Store(root)
        event(root, 'control_ready')
        await_marker(root, wait_for)
        event(root, 'control_requested')
        if change == 'stop':
            control = Control(root, store.instance_id)
            try: control.stop('IM19 isolated concurrency')
            finally: control.close()
        elif change == 'source_revocation':
            ToolLearningInvalidation(store, MechanicalInvalidation()).apply('mechanical-im06', request)
        else:
            revision = store.row('activities', activity)['revision']
            Management(store).cancel(activity, {'expected_revision': revision})
        event(root, 'control_committed')
    except BaseException:
        event(root, 'control_error', error=traceback.format_exc())
    finally:
        if store is not None: store.close()


def run_concurrency(case):
    from tests.test_tool_learning_invalidation import F1Tests
    from tests.test_tool_learning_budget import ToolLearningBudgetTests, MechanicalBudgetAuthority
    from tests.test_tool_learning_runtime import FreshProviderTests
    from digital_life.application.learning.budget import ToolLearningBudget, DIMENSIONS
    from digital_life.domain.contracts import Forbidden, Conflict, utc
    from digital_life.infrastructure.tools.workspace import registry
    fixture = F1Tests(); fixture.setUp()
    competitor = None
    try:
        root = fixture.s.root
        (root / 'workspace' / 'im19-input.txt').write_text('synthetic source reports 10')
        dependency = fixture.dependency()
        fixture.elig.register_input('mechanical-im06', fixture.query_principal, fixture.consumer, dependency)
        helper = ToolLearningBudgetTests()
        helper.s=fixture.s; helper.f=fixture.f; helper.now=utc(); helper.deadline=fixture.work['deadline']
        helper.work=fixture.work_id; helper.activity=fixture.work['learning_activity_id']; helper.account=fixture.work['budget_account_id']
        helper.service=ToolLearningBudget(fixture.s, MechanicalBudgetAuthority())
        transport=case['transport']; change=case['control']; stage=case['stage']; mode=case['mode']
        operation=helper.operation('thought_attempt' if transport=='model' else 'tool_attempt')
        request=fixture.request()
        wait_for='callback_entered' if stage=='callback_in_flight' else 'result_observed' if stage=='after_result' else 'control_go'
        args=(str(root),change,request,helper.activity,wait_for)
        competitor = multiprocessing.get_context('spawn').Process(target=controller_worker,args=args) if mode=='process' else threading.Thread(target=controller_worker,args=args)
        competitor.start(); await_marker(root,'control_ready')
        if stage=='before_reservation':
            event(root,'control_go'); await_marker(root,'control_committed')
        row=None; errors=[]; output=None
        amounts={'attempts':1,'input_tokens':20,'output_tokens':20} if transport=='model' else {'attempts':1,'tool_calls':1}
        try:
            row=helper.service.reserve('synthetic-im05',helper.work,operation,'thought_attempt' if transport=='model' else 'tool_attempt',amounts)
            event(root,'reserved', reservation_id=row['id'])
            if stage=='reserved_before_callback':
                if transport=='model':
                    fixture.s.db.execute("UPDATE thought_attempts SET state='sent',sent_at=? WHERE id=?",(utc(),operation['id']))
                    event(root,'ledger_sent_without_entry',operation_id=operation['id'])
                event(root,'control_go'); await_marker(root,'control_committed')
            def actual_transport():
                event(root,'callback_entered',transport=transport,operation_id=operation['id'])
                if stage=='callback_in_flight':
                    await_marker(root,'control_requested')
                    time.sleep(.08)
                    if (root / 'im19-control_committed').exists():
                        raise AssertionError('competing control committed before actual callback exit')
                if transport=='tool':
                    result=registry().invoke({'tool':'read_file','arguments':{'path':'im19-input.txt'}},root/'workspace','im19-synthetic-read')
                    if result.evidence['text']!='synthetic source reports 10':
                        raise AssertionError('real workspace read did not return actual bytes')
                    value={'text':result.evidence['text']}
                else:
                    value=None
                event(root,'callback_exited',transport=transport)
                return value
            def invoke():
                helper.service.record_entry('synthetic-im05',helper.work,row['id'],{'synthetic_witness':operation['id']})
                if transport=='tool':return actual_transport()
                provider_fixture=FreshProviderTests()
                def fresh_transport(path,wire,*unused):
                    actual_transport()
                    return provider_fixture.envelope('remote_chat',wire)
                port,packet=provider_fixture.port('remote_chat',fresh_transport)
                from digital_life.application.learning.eligibility import ref
                packet['request_id']=fixture.s.row('thought_attempts',operation['id'])['request_id']
                packet['work_ref']=ref(fixture.s,fixture.work_id)
                packet['source_token']=copy.deepcopy(fixture.token)
                return port.generate_fresh(packet)
            output=fixture.elig.callback('mechanical-im06',fixture.query_principal,fixture.token,fixture.scope,'learn',fixture.query_principal['recipient'],invoke,request=fixture.consumer)
            event(root,'result_observed')
        except (Forbidden,Conflict) as error:
            errors.append(type(error).__name__+': '+str(error));event(root,'blocked')
        if stage in ('callback_in_flight','after_result'):
            await_marker(root,'control_committed')
        competitor.join(10)
        if competitor.is_alive():raise AssertionError('control worker did not terminate')
        events=[json.loads(line) for line in (root/'im19-order.jsonl').read_text().splitlines()]
        control_errors=[e for e in events if e['kind']=='control_error']
        if control_errors:raise AssertionError(control_errors)
        names=[e['kind'] for e in events]
        entries=[e for e in events if e['kind']=='callback_entered']
        if stage in ('before_reservation','reserved_before_callback'):
            if entries:raise AssertionError('actual transport entered after prior control')
            if not errors:raise AssertionError('prior control did not block')
        else:
            if len(entries)!=1:raise AssertionError('actual transport did not enter exactly once')
            if names.index('callback_entered')>=names.index('callback_exited') or names.index('callback_exited')>=names.index('control_committed'):
                raise AssertionError('invalid real callback/control order')
        # All late use/new callbacks must be denied. This is a second attempted
        # gate check, not an automatic replay of the entered external action.
        try:
            fixture.elig.callback('mechanical-im06',fixture.query_principal,fixture.token,fixture.scope,'learn',fixture.query_principal['recipient'],lambda: (_ for _ in ()).throw(AssertionError('late transport entered')),request=fixture.consumer)
        except (Forbidden,Conflict):pass
        else:raise AssertionError('post-control callback was allowed')
        actual={k:0 for k in DIMENSIONS}
        if entries:
            actual.update(attempts=1)
            actual.update(input_tokens=10,output_tokens=5) if transport=='model' else actual.update(tool_calls=1)
        if row is not None:
            helper.service.settle('synthetic-im05',helper.work,row['id'],actual)
        ledger=json.loads(fixture.s.row('activities',helper.activity)['budget_json'])
        return {'case_id':case['id'],'mode':mode,'transport':transport,'control':change,'stage':stage,
            'input':{'source':fixture.token,'scope':fixture.scope,'request':request,'operation':operation},
            'events':events,'entry_count':len(entries),'errors':errors,'original_budget_ledger':ledger,
            'result_observed':output is not None,'endpoint':case['expected_endpoint'],
            'post_control_entry_count':0,'actual_source_gate':True,'actual_transport':True,
            'real_model_called':False,'scope':'fresh deterministic provider and real workspace registry under TL eligibility + original work budget; not strict Engine assembly',
            'independent_control_store':True,'control_exitcode':competitor.exitcode if mode=='process' else None}
    finally:
        if competitor is not None and competitor.is_alive():
            (fixture.s.root/'im19-abort').touch()
            if hasattr(competitor,'terminate'):competitor.terminate()
            competitor.join(3)
        fixture.doCleanups()
