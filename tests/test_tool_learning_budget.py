"""IM05 synthetic budget records only; never enters model/tool callbacks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest

from digital_life.application.runtime.scheduling import Budget as LegacyBudget
from digital_life.application.learning.budget import (
    BudgetAuthority, ToolLearningBudget, DIMENSIONS, make_work_budget, allocation_occupancy,
)
from digital_life.domain.contracts import ContractError, Conflict, Forbidden, dumps, identifier, utc
from digital_life.infrastructure.persistence.sqlite_store import Store
from evaluation.tool_learning_fixture import SyntheticToolLearningFixture
from tests.test_tool_learning_products import budget, control, method, sl

RESOURCES=Path(__file__).resolve().parents[1]/'digital_life/resources'


class MechanicalBudgetAuthority(BudgetAuthority):
    """Explicit synthetic port: persisted test witness is not a real callback."""
    def __init__(self):self.deny=False;self.commit_hook=None;self.deny_settlement=False
    def verify_budget(self,entry,work,original_budget,request_budget,operation,stage):
        if entry!='synthetic-im05' or self.deny:raise Forbidden('synthetic budget denial')
        if stage=='commit' and self.commit_hook is not None:self.commit_hook()
    def verify_entry(self,entry,work,reservation,witness):
        if witness!={'synthetic_witness':reservation['operation']['id']}:
            raise Forbidden('sent or entered flags are not trusted actual-entry evidence')

    def verify_settlement(self,entry,work,reservation,actual):
        if self.deny_settlement:raise Forbidden('synthetic release/settlement not verified')


class ToolLearningBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.fixture=SyntheticToolLearningFixture(Path(self.temp.name).resolve()/'new',schema_version=3)
        self.f=self.fixture.__enter__();self.addCleanup(self.fixture.__exit__,None,None,None)
        self.s=self.f.store;self.s.db.executescript((RESOURCES/'tool_learning_v1.sql').read_text())
        self.now=utc();self.deadline=utc(600);self.authority=MechanicalBudgetAuthority()
        self.work,self.activity,self.account=self.seed_work()
        self.service=ToolLearningBudget(self.s,self.authority,clock=lambda:self.now)
        (self.s.root/'WAKE_DISABLED').unlink();self.f.control.resume('synthetic-budget-mechanics-only')

    def ref(self,key,kind=None):
        if kind is None:kind=self.s.row('object_registry',key)['kind']
        return {'instance_id':self.s.instance_id,'id':key,'kind':kind,'revision':sl()}

    def seed_work(self,**caps):
        with self.s.tx():
            activity=self.s.insert('activities',state='pending',budget_json={},release_id='isolated-im05',publication_state='ready',deadline=self.deadline)
            account=identifier();b=budget();b.update(deadline=self.deadline,max_input_tokens=100,max_output_tokens=100,max_attempts=5,max_tool_calls=3,max_scan=10,max_items=10,max_bytes=100);b.update(caps)
            b['account_ref']=self.ref(account,'activity_budget_accounts')
            self.s.insert('activity_budget_accounts',id=account,activity_id=activity,token_limit=b['max_input_tokens']+b['max_output_tokens'],tool_call_limit=b['max_tool_calls'],attempt_limit=b['max_attempts'],time_limit_ms=600000)
            doc=make_work_budget(b);self.s.db.execute('UPDATE activities SET budget_json=? WHERE id=?',(dumps(doc),activity))
            conditions=self.s.artifact({'budget':b,'source_budget':None,'time_limit_ms':600000});control_ref=self.s.artifact(control());method_ref=self.s.artifact(method())
            work=identifier();fields=dict(id=work,instance_id=self.s.instance_id,learning_activity_id=activity,source_activity_id=self.f.expected['activity_id'],source_artifact_id=conditions,purpose='learn',processing_identity=identifier()*2,state='admitted',phase='admit',review_round=0,conditions_artifact_id=conditions,control_artifact_id=control_ref,method_artifact_id=method_ref,deadline=self.deadline,budget_account_id=account,row_revision=0)
            self.s.db.execute('INSERT INTO tl_work ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',tuple(fields.values()))
        return work,activity,account

    def operation(self,kind='thought_attempt',activity=None):
        activity=self.activity if activity is None else activity
        with self.s.tx():
            if kind=='retrieval':
                context=self.s.db.execute('SELECT id FROM context_snapshots LIMIT 1').fetchone()[0]
                return self.ref(self.s.insert('memory_retrieval_runs',activity_id=activity,query='synthetic-only',context_id=context,retriever_version='im05-synthetic'))
            if kind=='tool_attempt':
                old=self.s.row('action_intents',self.f.expected['intent_id']);candidate=self.s.row('decision_candidates',old['candidate_id']);decision=self.s.row('decision_records',candidate['decision_id'])
                decision.update(id=identifier(),activity_id=activity,state='draft');self.s.insert('decision_records',**decision)
                candidate.update(id=identifier(),decision_id=decision['id'],selection_probability=1,selected=1,eligible=1);self.s.insert('decision_candidates',**candidate)
                self.s.db.execute("UPDATE decision_records SET state='finalized' WHERE id=?",(decision['id'],))
                old.update(id=identifier(),candidate_id=candidate['id'],idempotency_key=identifier(),state='proposed');self.s.insert('action_intents',**old)
                grant=self.s.insert('grants',subject=self.f.expected['self_actor'],capability=old['required_capability_id'],resource_scope={},version=0)
                auth=self.s.insert('action_authorization_records',intent_id=old['id'],grant_id=grant,proposal_revision=0,arguments_hash=old['arguments_hash'],scope_snapshot={},policy_epoch=0,issued_at=self.now,expires_at=self.deadline,state='valid')
                return self.ref(self.s.insert('action_attempts',intent_id=old['id'],attempt_no=0,started_at=self.now,runner_ref='synthetic-metadata',state='pending',authorization_record_id=auth,policy_epoch=0,execution_token_hash='a'*64,arguments_hash=old['arguments_hash'],runtime_epoch=0,process_run_id='synthetic-not-started'))
            step=self.s.insert('activity_steps',activity_id=activity,step_no=self.s.db.execute('SELECT count(*) FROM activity_steps WHERE activity_id=?',(activity,)).fetchone()[0],step_type='synthetic',state='pending',attempt=0,idempotency_key=identifier())
            artifact=self.s.artifact({'synthetic':True});config=self.s.db.execute('SELECT id FROM configuration_versions LIMIT 1').fetchone()[0];model=self.s.db.execute('SELECT id FROM model_versions LIMIT 1').fetchone()[0]
            request=self.s.insert('thought_requests',activity_id=activity,step_id=step,request_key=identifier(),purpose='infer',task='synthetic budget metadata only',instruction_version='im05-test',output_schema_version=1,request_artifact_id=artifact,request_hash='a'*64,input_manifest_hash='b'*64,model_config_id=config,model_version_id=model,prepared_activity_revision=0,expected_input_epoch=0,expected_policy_epoch=0,runtime_epoch=0,process_run_id='synthetic-not-started',deadline=self.deadline,token_budget=10,attempt_limit=1,retry_policy={},generation_config={},state='prepared')
            return self.ref(self.s.insert('thought_attempts',request_id=request,attempt_no=0,state='queued',queued_at=self.now,dispatch_token=identifier(),provider='synthetic-no-provider',model='none',runtime_epoch=0,process_run_id='synthetic-not-started'))

    def reserve(self,amounts=None,operation=None,kind='thought_attempt',**kwargs):
        operation=self.operation(kind) if operation is None else operation
        return self.service.reserve('synthetic-im05',self.work,operation,kind,amounts or {'attempts':1,'input_tokens':10,'output_tokens':10},**kwargs)

    def enter(self,row):
        return self.service.record_entry('synthetic-im05',self.work,row['id'],{'synthetic_witness':row['operation']['id']})

    def actual(self,**kwargs):
        return {k:kwargs.get(k,0) for k in DIMENSIONS}

    def test_original_caps_and_read_only_snapshot(self):
        before=self.s.row('activities',self.activity);snapshot=self.service.check_work(self.work)
        self.assertEqual(snapshot['remaining']['input_tokens'],100)
        self.assertEqual(snapshot['account_id'],self.account)
        self.assertEqual(before,self.s.row('activities',self.activity))
        self.assertEqual(self.f.control.state()['user_stopped'],0);self.assertIsNone(self.f.control.state()['active_process_run_id'])

    def test_default_authority_and_untrusted_witness_deny(self):
        with self.assertRaises(Forbidden):ToolLearningBudget(self.s).reserve('anything',self.work,self.operation(),'thought_attempt',{'attempts':1})
        row=self.reserve()
        with self.assertRaises(Forbidden):self.service.record_entry('synthetic-im05',self.work,row['id'],{'sent':True})
        self.assertIsNone(self.service.check_work(self.work)['charged_or_reserved'].get('entry'))

    def test_individual_input_output_caps_and_shared_limits(self):
        self.reserve({'attempts':1,'input_tokens':100})
        with self.assertRaises(Forbidden):self.reserve({'attempts':1,'input_tokens':1})
        self.reserve({'attempts':1,'output_tokens':100})
        self.assertEqual(self.service.check_work(self.work)['remaining']['tokens'],0)

    def test_local_retrieval_scan_items_bytes_are_not_attempts(self):
        op=self.operation('retrieval');row=self.reserve({'scan':10,'items':10,'bytes':100},operation=op,kind='retrieval')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM budget_reservations WHERE activity_id=?',(self.activity,)).fetchone()[0],0)
        self.assertEqual(self.service.check_work(self.work)['remaining']['attempts'],5)
        with self.assertRaises(Forbidden):self.reserve({'scan':1},operation=op,kind='retrieval',reservation_key='extra')
        self.enter(row);settled=self.service.settle('synthetic-im05',self.work,row['id'],self.actual(scan=10,items=10,bytes=100))
        self.assertEqual(settled['actual']['attempts'],0)

    def test_tool_operation_is_bound_through_real_decision_activity(self):
        op=self.operation('tool_attempt');row=self.reserve({'attempts':1,'tool_calls':1},operation=op,kind='tool_attempt')
        self.enter(row);self.service.settle('synthetic-im05',self.work,row['id'],self.actual(attempts=1,tool_calls=1))
        self.assertEqual(self.service.check_work(self.work)['remaining']['tool_calls'],2)

    def test_same_key_idempotency_and_different_meaning(self):
        op=self.operation();first=self.reserve(operation=op,reservation_key='same');second=self.reserve(operation=op,reservation_key='same')
        self.assertEqual(first,second)
        with self.assertRaises(Conflict):self.reserve({'attempts':1,'input_tokens':11},operation=op,reservation_key='same')

    def test_same_real_attempt_cannot_reenter_by_new_key(self):
        op=self.operation();self.reserve(operation=op,reservation_key='first')
        with self.assertRaises(Conflict):self.reserve(operation=op,reservation_key='different')

    def test_operation_wrong_activity_or_kind_rejected(self):
        op=self.operation(activity=self.f.expected['activity_id'])
        with self.assertRaises(ContractError):self.reserve(operation=op)
        op=self.operation('retrieval')
        with self.assertRaises(ContractError):self.reserve(operation=op)

    def test_reservation_not_actual_and_partial_actual_not_zero(self):
        row=self.reserve()
        with self.assertRaises(ContractError):self.service.settle('synthetic-im05',self.work,row['id'],{'attempts':1})
        with self.assertRaises(ContractError):self.service.settle('synthetic-im05',self.work,row['id'],self.actual(attempts=1))
        self.assertEqual(self.service.check_work(self.work)['charged_or_reserved']['attempts'],1)

    def test_unknown_usage_holds_all_dimensions_across_reopen(self):
        row=self.reserve();self.enter(row);self.service.settle('synthetic-im05',self.work,row['id'],None)
        reopened=ToolLearningBudget(self.s,self.authority,clock=lambda:self.now)
        self.assertIn('usage_unknown',reopened.check_work(self.work)['block_reasons'])
        with self.assertRaises(Forbidden):reopened.reserve('synthetic-im05',self.work,self.operation(),'thought_attempt',{'attempts':1},reservation_key='new-key')
        self.assertEqual(reopened.check_work(self.work)['remaining']['input_tokens'],90)

    def test_known_excess_is_retained_and_blocks_future(self):
        row=self.reserve();self.enter(row)
        actual=self.actual(attempts=1,input_tokens=11,output_tokens=10)
        self.service.settle('synthetic-im05',self.work,row['id'],actual)
        document=json.loads(self.s.row('activities',self.activity)['budget_json'])
        self.assertEqual(document['ledger']['reservations'][row['id']]['actual'],actual)
        self.assertTrue(document['ledger']['halted']);self.assertEqual(len(document['ledger']['violations']),1)

    def test_known_settlement_idempotent_not_overwritten(self):
        row=self.reserve();self.enter(row);actual=self.actual(attempts=1,input_tokens=5)
        first=self.service.settle('synthetic-im05',self.work,row['id'],actual)
        self.assertEqual(first,self.service.settle('synthetic-im05',self.work,row['id'],actual))
        with self.assertRaises(Conflict):self.service.settle('synthetic-im05',self.work,row['id'],None)

    def test_no_entry_zero_release_is_not_a_model_call(self):
        row=self.reserve();result=self.service.settle('synthetic-im05',self.work,row['id'],self.actual())
        self.assertEqual(result['state'],'released');self.assertIsNone(result['entry'])
        self.assertEqual(self.service.check_work(self.work)['remaining']['attempts'],5)

    def test_last_reserved_attempt_can_enter_but_no_new_attempt(self):
        self.work,self.activity,self.account=self.seed_work(max_attempts=1)
        row=self.reserve();self.assertIn('attempts_exhausted',self.service.check_work(self.work)['block_reasons'])
        self.enter(row)
        with self.assertRaises(Forbidden):self.reserve()

    def test_budget_account_revision_changes_without_activity_revision(self):
        before=self.s.row('activities',self.activity);row=self.reserve();self.enter(row)
        after=self.s.row('activities',self.activity)
        self.assertEqual(before['revision'],after['revision']);self.assertEqual(before['input_epoch'],after['input_epoch'])
        self.assertEqual(self.s.row('activity_budget_accounts',self.account)['revision'],2)

    def test_original_deadline_and_request_caps_cannot_grow(self):
        original=self.service.check_work(self.work)['budget'];changed=deepcopy(original);changed['deadline']=utc(1200)
        with self.assertRaises(Conflict):self.service.check_work(self.work,changed)
        changed=deepcopy(original);changed['max_input_tokens']+=1
        with self.assertRaises(Conflict):self.service.check_work(self.work,changed)
        self.now=self.deadline
        with self.assertRaises(Forbidden):self.reserve()

    def test_cancelled_and_stopped_work_do_not_continue(self):
        self.s.db.execute('UPDATE activities SET cancel_requested_at=? WHERE id=?',(self.now,self.activity))
        with self.assertRaises(Forbidden):self.reserve()
        self.s.db.execute('UPDATE activities SET cancel_requested_at=NULL WHERE id=?',(self.activity,))
        self.s.db.execute("UPDATE tl_work SET state='stopped',row_revision=1 WHERE id=?",(self.work,))
        with self.assertRaises(Forbidden):self.reserve()

    def test_caps_tamper_and_nested_allocations_fail_closed(self):
        original=json.loads(self.s.row('activities',self.activity)['budget_json']);changed=deepcopy(original);changed['budget']['max_input_tokens']+=1
        self.s.db.execute('UPDATE activities SET budget_json=? WHERE id=?',(dumps(changed),self.activity))
        with self.assertRaises(ContractError):self.service.check_work(self.work)
        original['tl_work_allocations']={'contract':'TL-WORK-ALLOCATIONS-1','caps':original['budget'],'allocations':{}}
        self.s.db.execute('UPDATE activities SET budget_json=? WHERE id=?',(dumps(original),self.activity))
        with self.assertRaises(Forbidden):self.service.check_work(self.work)

    def test_legacy_entry_cannot_bypass_new_child_ledger(self):
        op=self.operation()
        with self.assertRaises(ContractError):LegacyBudget(self.s).reserve(self.activity,op['id'],'thought_attempt',1)
        row=self.reserve(operation=op)
        with self.assertRaises(ContractError):LegacyBudget(self.s).settle(row['id'],usage={'tokens':0})

    def test_parent_allocation_protects_child_and_leaves_legacy_remaining(self):
        parent=self.f.expected['activity_id'];account=self.s.db.execute('SELECT * FROM activity_budget_accounts WHERE activity_id=?',(parent,)).fetchone()
        child=self.service.check_work(self.work)['budget'];doc=json.loads(self.s.row('activities',parent)['budget_json'])
        caps=deepcopy(child);caps['account_ref']=self.ref(account['id']);caps['max_input_tokens']=account['token_limit'];caps['max_output_tokens']=0;caps['max_attempts']=account['attempt_limit'];caps['max_tool_calls']=account['tool_call_limit']
        doc['tl_work_allocations']={'contract':'TL-WORK-ALLOCATIONS-1','caps':caps,'allocations':{self.work:{'activity_id':self.activity,'account_id':self.account,'budget':child}}}
        self.s.db.execute('UPDATE activities SET budget_json=? WHERE id=?',(dumps(doc),parent))
        self.assertEqual(allocation_occupancy(doc)['tokens'],200)
        remaining=account['token_limit']-200;op=self.operation(activity=parent)
        LegacyBudget(self.s).reserve(parent,op['id'],'thought_attempt',remaining)
        with self.assertRaises(ContractError):LegacyBudget(self.s).reserve(parent,self.operation(activity=parent)['id'],'thought_attempt',1)

    def test_shared_parent_unknown_consumption_blocks_new_legacy_reservation(self):
        parent=self.f.expected['activity_id'];account=self.s.db.execute('SELECT * FROM activity_budget_accounts WHERE activity_id=?',(parent,)).fetchone()
        child=self.service.check_work(self.work)['budget'];document=json.loads(self.s.row('activities',parent)['budget_json'])
        caps=deepcopy(child);caps['account_ref']=self.ref(account['id'])
        document['tl_work_allocations']={'contract':'TL-WORK-ALLOCATIONS-1','caps':caps,'allocations':{self.work:{'activity_id':self.activity,'account_id':self.account,'budget':child}}}
        self.s.db.execute('UPDATE activities SET budget_json=? WHERE id=?',(dumps(document),parent))
        legacy=LegacyBudget(self.s);first=self.operation(activity=parent)
        reservation=legacy.reserve(parent,first['id'],'thought_attempt',1);legacy.settle(reservation,unknown=True)
        with self.assertRaises(ContractError):legacy.reserve(parent,self.operation(activity=parent)['id'],'thought_attempt',1)
        self.assertEqual(self.s.row('budget_reservations',reservation)['state'],'usage_unknown')

    def test_ordinary_legacy_unknown_without_allocations_retains_old_behavior(self):
        parent=self.f.expected['activity_id'];legacy=LegacyBudget(self.s)
        reservation=legacy.reserve(parent,self.operation(activity=parent)['id'],'thought_attempt',1)
        legacy.settle(reservation,unknown=True)
        second=legacy.reserve(parent,self.operation(activity=parent)['id'],'thought_attempt',1)
        self.assertNotEqual(reservation,second)

    def test_ordinary_legacy_activity_without_allocation_is_unchanged(self):
        parent=self.f.expected['activity_id'];op=self.operation(activity=parent)
        reservation=LegacyBudget(self.s).reserve(parent,op['id'],'thought_attempt',1)
        self.assertEqual(LegacyBudget(self.s).settle(reservation,usage={'tokens':1}),'settled')

    def test_two_connections_compete_for_last_attempt_atomically(self):
        self.work,self.activity,self.account=self.seed_work(max_attempts=1)
        operations=[self.operation(),self.operation()];barrier=threading.Barrier(2);results=[]
        def competing(operation):
            store=Store(self.s.root)
            try:
                service=ToolLearningBudget(store,MechanicalBudgetAuthority(),clock=lambda:self.now)
                barrier.wait()
                try:service.reserve('synthetic-im05',self.work,operation,'thought_attempt',{'attempts':1});results.append('reserved')
                except Forbidden:results.append('denied')
            finally:store.close()
        threads=[threading.Thread(target=competing,args=(op,)) for op in operations]
        for thread in threads:thread.start()
        for thread in threads:thread.join(10);self.assertFalse(thread.is_alive())
        self.assertCountEqual(results,['reserved','denied'])

    def test_wake_lock_and_user_stop_block_new_budget_and_entry(self):
        row=self.reserve();self.f.control.stop('synthetic-stop')
        self.assertIn('instance_stopped',self.service.check_work(self.work)['block_reasons'])
        with self.assertRaises(Forbidden):self.reserve()
        with self.assertRaises(Forbidden):self.enter(row)
        self.f.control.resume('synthetic-resume');(self.s.root/'WAKE_DISABLED').write_text('test lock')
        with self.assertRaises(Forbidden):self.reserve()

    def test_commit_rechecks_authority_and_stop_rolls_back_ledger(self):
        self.authority.commit_hook=lambda:self.f.control.stop('synthetic-stop-during-verification')
        with self.assertRaises(Forbidden):self.reserve()
        document=json.loads(self.s.row('activities',self.activity)['budget_json'])
        self.assertEqual(document['ledger']['reservations'],{})
        self.assertEqual(self.s.row('activity_budget_accounts',self.account)['revision'],0)

    def test_entry_commit_rechecks_authority_and_rolls_back_witness(self):
        row=self.reserve();self.authority.commit_hook=lambda:self.f.control.stop('synthetic-stop-entry-commit')
        with self.assertRaises(Forbidden):self.enter(row)
        document=json.loads(self.s.row('activities',self.activity)['budget_json'])
        self.assertIsNone(document['ledger']['reservations'][row['id']]['entry'])

    def test_stopped_inflight_actual_can_settle_and_clock_cannot_rewind(self):
        row=self.reserve();self.enter(row);last=self.now
        self.f.control.stop('synthetic-inflight-stop');self.now='2020-01-01T00:00:00.000Z'
        result=self.service.settle('synthetic-im05',self.work,row['id'],self.actual(attempts=1,input_tokens=5))
        self.assertEqual(result['actual']['input_tokens'],5)
        doc=json.loads(self.s.row('activities',self.activity)['budget_json'])
        self.assertEqual(doc['ledger']['last_seen_at'],last)
        self.assertTrue(doc['ledger']['halted']);self.assertEqual(doc['ledger']['violations'][-1]['reason'],'clock_regressed')

    def test_release_needs_explicit_settlement_authority(self):
        row=self.reserve();self.authority.deny_settlement=True
        with self.assertRaises(Forbidden):self.service.settle('synthetic-im05',self.work,row['id'],self.actual())
        self.assertEqual(self.service.check_work(self.work)['charged_or_reserved']['attempts'],1)

    def test_fake_known_revision_and_missing_physical_row_rejected(self):
        op=self.operation();op['revision']=sl(999,'known')
        with self.assertRaises(Conflict):self.reserve(operation=op)
        fake=self.s.root_object('thought_attempts')
        with self.assertRaises(ContractError):self.reserve(operation=self.ref(fake))

    def test_time_limit_tamper_cannot_grow_budget(self):
        self.s.db.execute('UPDATE activity_budget_accounts SET time_limit_ms=time_limit_ms+1 WHERE id=?',(self.account,))
        with self.assertRaises(ContractError):self.service.check_work(self.work)


if __name__=='__main__':unittest.main()
