"""IM05 C0 in new synthetic instances only. No model/tool/runtime start."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from digital_life.domain.contracts import ContractError, Conflict, Forbidden, identifier, utc, dumps
from digital_life.application.learning.work import ToolLearningWork, WorkAuthority, AdmissionAllocation,origin_identity
from digital_life.infrastructure.persistence.tool_learning_store import StorageGrant
from digital_life.infrastructure.persistence.sqlite_store import Store
from evaluation.tool_learning_fixture import SyntheticToolLearningFixture
from tests.test_tool_learning_products import envelope,payloads,evidence,sl,control,method

ROOT=Path(__file__).resolve().parents[1]


class SyntheticWorkAuthority(WorkAuthority):
    def __init__(self,parent_budget):self.parent=copy.deepcopy(parent_budget);self.reject_stage=None
    def verify(self,entry,operation,request,instance_id,stage):
        if entry!='synthetic-m14' or stage==self.reject_stage:raise Forbidden('synthetic trusted-port rejection')
        return StorageGrant('M14',frozenset(('tl_work',)))
    def project_response(self,entry,operation,request,response,instance_id,stage):return response
    def verify_source_origin(self,entry,request,source):
        if source['source_kind']!='user_statement' or source['source_revision']['status']=='known' or source['source']['revision']['status']=='known':
            raise Forbidden('synthetic immutable source has no registered new version')
    def admission_allocation(self,entry,request,source_activity,parent_account):return AdmissionAllocation(copy.deepcopy(self.parent))


class WorkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.fixture=SyntheticToolLearningFixture(Path(self.tmp.name).resolve()/'new',schema_version=3)
        self.f=self.fixture.__enter__();self.addCleanup(self.fixture.__exit__,None,None,None)
        self.s=self.f.store;self.db=self.s.db
        self.db.executescript((ROOT/'digital_life/resources/tool_learning_v1.sql').read_text())
        for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'tl_%'").fetchall():
            self.s.columns[row[0]]={c[1] for c in self.db.execute('PRAGMA table_info('+row[0]+')')}
        # Only this fresh synthetic fixture is unblocked, with zero execution calls.
        (self.s.root/'WAKE_DISABLED').unlink();self.f.control.resume('im05-test-only')
        self.source_activity=self.f.expected['activity_id']
        self.parent=self.db.execute('SELECT * FROM activity_budget_accounts WHERE activity_id=?',(self.source_activity,)).fetchone()
        self.request=self.make_request()
        self.parent_caps=copy.deepcopy(self.request['budget'])
        self.parent_caps.update(max_input_tokens=8000,max_output_tokens=8000,max_attempts=8,max_tool_calls=8,max_scan=100,max_items=100,max_bytes=100000,deadline=utc(500))
        self.auth=SyntheticWorkAuthority(self.parent_caps)
        self.work=ToolLearningWork(self.s,self.auth)

    def ref(self,key,kind=None):
        if kind is None:kind=self.s.row('object_registry',key)['kind']
        return {'instance_id':self.s.instance_id,'id':key,'kind':kind,'revision':sl()}

    def make_request(self):
        req=envelope(payloads()['admit_observation']);req.update(instance_id=self.s.instance_id,command_id=identifier(),idempotency_key=identifier(),work_ref=sl())
        req['principal']={'actor':self.ref(self.f.expected['self_actor']),'module':'M14','recipient':self.ref(self.f.expected['self_actor']),'purpose':'learn','authorization':self.ref(self.f.expected['policy_id'])}
        art=self.s.artifact({'inventory':7});a=self.s.row('artifacts',art)
        ev=evidence();ev.update(source=self.ref(self.f.expected['controller']),source_kind='user_statement',original_result=sl(),receipt=sl(),artifact=self.ref(art),source_revision=sl(),digest={'algorithm':'sha256','hex':a['hash']},media_type='application/json',view=sl(),view_digest=sl(),locator={'kind':'whole_artifact','justification':'single atomic inventory report'},access_dependencies=[])
        req['payload']={'source':ev,'purpose':'learn','source_activity':self.ref(self.source_activity),'processing_method':method(),'previous_work':sl()}
        req['control']=control()
        for key in ('policy','configuration'):
            obj=self.ref(self.f.expected['memory_id']);obj['revision']=sl(1,'known')
            req['control'][key]={'object':obj,'revision':1,'epoch':0}
        req['control'].update(source_epochs=[],cancelled=False)
        req['budget']={'account_ref':self.ref(self.parent['id']),'deadline':utc(120),'max_attempts':1,'max_input_tokens':100,'max_output_tokens':50,'max_tool_calls':1,'max_scan':10,'max_items':10,'max_bytes':1000}
        return req

    def admit(self,request=None):return self.work.admit('synthetic-m14',request or self.request)
    def work_id(self,response):return response['result_refs'][0]['id']
    def new_request(self):
        r=copy.deepcopy(self.request);r['command_id']=identifier();r['idempotency_key']=identifier();return r

    def transition_request(self,work_id,target='processing',phase='assess',reason='prepare',revision=0):
        row=self.s.row('tl_work',work_id);req=self.new_request()
        intent={'contract':'TL-WORK-TRANSITION-1','work_id':work_id,'expected_revision':revision,'target':target,'phase':phase,'reason':reason}
        artifact=self.s.artifact(intent)
        req['work_ref']=sl(self.ref(work_id),'known');req['expected']=sl({'object':self.ref(work_id),'revision':revision,'epoch':0},'known')
        req['budget']=json.loads(self.s.row('activities',row['learning_activity_id'])['budget_json'])['budget']
        req['payload']={'source':self.request['payload']['source'],'baseline_refs':[],'baseline_coverage':{'state':'complete','domain':sl('synthetic','known'),'scanned':0,'limit':0,'truncated':False,'missing':[]},'method':{'name':'tl-work-transition','version':'1','request_ref':sl(self.ref(artifact),'known'),'model_config_ref':sl()}}
        return req

    def test_c0_atomic_internal_producer_and_bound_original_budget(self):
        memories=len(self.s.rows('memory_revisions'));jobs=len(self.s.rows('jobs'))
        response=self.admit();work=self.s.row('tl_work',self.work_id(response));activity=self.s.row('activities',work['learning_activity_id'])
        signal=self.s.row('perception_signals',activity['trigger_event_id']);channel=self.s.row('perception_channels',signal['channel_id'])
        self.assertEqual(channel['kind'],'internal');self.assertEqual(signal['source_actor_id'],self.f.expected['self_actor'])
        self.assertEqual(self.s.read_artifact(signal['artifact_id'])['producer'],self.request['principal'])
        self.assertNotEqual(work['learning_activity_id'],self.source_activity)
        budget=json.loads(activity['budget_json']);self.assertEqual(budget['budget']['account_ref']['id'],work['budget_account_id'])
        self.assertEqual(budget['source_budget'],self.request['budget']);self.assertEqual(work['deadline'],activity['deadline'])
        self.assertEqual((len(self.s.rows('memory_revisions')),len(self.s.rows('jobs'))),(memories,jobs))
        self.assertEqual(self.s.row('tl_command',self.request['command_id'])['state'],'committed')

    def test_same_command_and_new_key_duplicate_do_not_allocate_again(self):
        first=self.admit();parentrev=self.s.row('activity_budget_accounts',self.parent['id'])['revision']
        changed=self.new_request();changed['control']['input_epoch']+=1
        second=self.admit(changed);third=self.admit()
        self.assertEqual(self.work_id(first),self.work_id(second));self.assertEqual(first,third)
        self.assertEqual(second['disposition'],'reused');self.assertEqual(len(self.s.rows('tl_work')),1)
        self.assertEqual(self.s.row('activity_budget_accounts',self.parent['id'])['revision'],parentrev)

    def test_same_key_different_logical_payload_conflicts(self):
        self.admit();changed=copy.deepcopy(self.request);changed['payload']['processing_method']['version']='other'
        with self.assertRaises(Conflict):self.admit(changed)

    def test_reprocessing_and_notification_change_cannot_reset_budget(self):
        first=self.admit();changed=self.new_request();changed['payload']['processing_method']['version']='new-method'
        result=self.admit(changed);self.assertEqual(result['disposition'],'blocked');self.assertEqual(len(self.s.rows('tl_work')),1)
        changed=self.new_request();changed['payload']['previous_work']=sl(self.ref(self.work_id(first)),'known')
        self.assertEqual(self.admit(changed)['disposition'],'blocked')

    def test_origin_ignores_slot_explanation_and_basis_metadata(self):
        source=copy.deepcopy(self.request['payload']['source']);new=copy.deepcopy(source)
        new['source_revision']['reason']='different explanation';new['original_result']['reason']='changed';new['receipt']['status']='unknown'
        self.assertEqual(origin_identity(source),origin_identity(new))

    def test_self_reported_new_source_revision_cannot_allocate_again(self):
        self.admit();changed=self.new_request();changed['payload']['source']['source_revision']=sl(1,'known')
        with self.assertRaises(Forbidden):self.admit(changed)
        self.assertEqual(len(self.s.rows('tl_work')),1)

    def test_same_bytes_different_real_source_is_distinct(self):
        self.admit();changed=self.new_request();changed['payload']['source']['source']=self.ref(self.f.expected['self_actor'])
        second=self.admit(changed);self.assertEqual(second['disposition'],'applied');self.assertEqual(len(self.s.rows('tl_work')),2)

    def test_same_observation_with_new_notification_parent_is_not_new_work(self):
        first=self.admit();request=self.new_request()
        with self.s.tx():
            new_activity=self.s.insert('activities',state='pending',budget_json={'tokens':16000,'tool_calls':8},release_id='synthetic',publication_state='ready',deadline=utc(400))
            new_account=self.s.insert('activity_budget_accounts',activity_id=new_activity,token_limit=16000,tool_call_limit=8,attempt_limit=8,time_limit_ms=400000)
        request['payload']['source_activity']=self.ref(new_activity);request['budget']['account_ref']=self.ref(new_account)
        self.auth.parent['account_ref']=self.ref(new_account)
        result=self.admit(request)
        self.assertEqual(result['disposition'],'blocked');self.assertEqual(self.work_id(result),self.work_id(first))
        self.assertNotIn('tl_work_allocations',json.loads(self.s.row('activities',new_activity)['budget_json']))

    def test_parent_allocations_bound_distinct_observations_and_rollback(self):
        self.auth.parent['max_attempts']=1
        self.admit();changed=self.new_request();changed['payload']['source']['source']=self.ref(self.f.expected['self_actor'])
        before=self.s.row('activities',self.source_activity)['budget_json']
        with self.assertRaises(Forbidden):self.admit(changed)
        self.assertEqual(len(self.s.rows('tl_work')),1)
        self.assertEqual(self.s.row('activities',self.source_activity)['budget_json'],before)

    def test_unknown_parent_consumption_blocks_new_allocation_but_not_exact_reuse(self):
        first=self.admit()
        with self.s.tx():
            self.s.insert('budget_reservations',activity_id=self.source_activity,operation_ref=self.f.expected['intent_id'],operation_kind='tool_attempt',reservation_key='synthetic-unknown-parent',reserved_tokens=1,reserved_tool_calls=1,reserved_attempts=1,state='usage_unknown',reserved_at=utc())
        duplicate=self.admit(self.new_request());self.assertEqual(self.work_id(duplicate),self.work_id(first))
        changed=self.new_request();changed['payload']['source']['source']=self.ref(self.f.expected['self_actor'])
        with self.assertRaises(Forbidden):self.admit(changed)
        self.assertEqual(len(self.s.rows('tl_work')),1)

    def test_nested_work_activity_cannot_be_used_as_fresh_parent(self):
        work=self.s.row('tl_work',self.work_id(self.admit()));request=self.new_request()
        request['payload']['source_activity']=self.ref(work['learning_activity_id'])
        request['budget']['account_ref']=self.ref(work['budget_account_id'])
        with self.assertRaises(Forbidden):self.admit(request)
        self.assertEqual(len(self.s.rows('tl_work')),1)

    def test_parent_and_source_activity_budget_account_cannot_be_swapped(self):
        work=self.s.row('tl_work',self.work_id(self.admit()));request=self.new_request()
        request['budget']['account_ref']=self.ref(work['budget_account_id'])
        with self.assertRaises(Forbidden):self.admit(request)

    def test_parent_wrong_account_and_exhaustion_do_not_create_work(self):
        request=copy.deepcopy(self.request);request['budget']['max_input_tokens']=9000
        with self.assertRaises(Forbidden):self.admit(request)
        self.assertEqual(self.s.rows('tl_work'),[])

    def test_source_bytes_bound_rejects_before_material_read(self):
        request=copy.deepcopy(self.request);request['budget']['max_bytes']=0
        with self.assertRaises(Forbidden):self.admit(request)
        self.assertEqual(self.s.rows('tl_work'),[])

    def test_source_cancelled_inside_admission_callback_is_rechecked(self):
        original=self.auth.admission_allocation
        def cancel(*args):
            result=original(*args)
            self.db.execute('UPDATE activities SET cancel_requested_at=? WHERE id=?',(utc(),self.source_activity))
            return result
        with patch.object(self.auth,'admission_allocation',side_effect=cancel):
            with self.assertRaises(Forbidden):self.admit()
        self.assertEqual(self.s.rows('tl_work'),[]);self.assertEqual(self.s.rows('tl_command'),[])

    def test_stop_or_cancel_during_commit_authority_rolls_back_c0(self):
        original=self.auth.verify
        for event in ('cancel','stop'):
            def interrupt(entry,operation,request,instance_id,stage):
                grant=original(entry,operation,request,instance_id,stage)
                if stage=='commit':
                    if event=='cancel':self.db.execute('UPDATE activities SET cancel_requested_at=? WHERE id=?',(utc(),self.source_activity))
                    else:self.f.control.stop('im05-authority-stop')
                return grant
            with patch.object(self.auth,'verify',side_effect=interrupt):
                with self.assertRaises(Forbidden):self.admit()
            self.assertEqual(self.s.rows('tl_work'),[]);self.assertEqual(self.s.rows('tl_command'),[])
            self.assertNotIn('tl_work_allocations',json.loads(self.s.row('activities',self.source_activity)['budget_json']))

    def test_source_resolver_missing_is_a_closed_gate(self):
        with patch.object(self.auth,'verify_source_origin',side_effect=Forbidden('source resolver missing')):
            with self.assertRaises(Forbidden):self.admit()
        self.assertEqual(self.s.rows('tl_work'),[])

    def test_source_completed_is_valid_but_cancelled_is_not(self):
        self.db.execute("UPDATE activities SET state='completed' WHERE id=?",(self.source_activity,))
        self.assertEqual(self.admit()['disposition'],'applied')
        changed=self.new_request();changed['payload']['source']['source']=self.ref(self.f.expected['self_actor'])
        self.db.execute("UPDATE activities SET cancel_requested_at=? WHERE id=?",(utc(),self.source_activity))
        with self.assertRaises(Forbidden):self.admit(changed)

    def test_stopped_locked_cancelled_and_expired_never_create(self):
        self.f.control.stop('im05-stop')
        with self.assertRaises(Forbidden):self.admit()
        self.f.control.resume('im05-resume')
        request=copy.deepcopy(self.request);request['control']['cancelled']=True
        with self.assertRaises(Forbidden):self.admit(request)
        request=copy.deepcopy(self.request);request['budget']['deadline']=utc(-1)
        with self.assertRaises(Forbidden):self.admit(request)
        self.assertEqual(self.s.rows('tl_work'),[])

    def test_failure_at_each_old_table_write_rolls_back_parent_and_everything(self):
        counts={name:len(self.s.rows(name)) for name in ('activities','activity_budget_accounts','perception_signals','perception_channels','tl_work','tl_command')}
        original_parent=self.s.row('activities',self.source_activity)['budget_json']
        original=self.s.insert
        for table in ('perception_channels','perception_signals','activities','activity_budget_accounts'):
            def failing(name,**fields):
                if name==table:raise RuntimeError('injected '+table)
                return original(name,**fields)
            with patch.object(self.s,'insert',side_effect=failing):
                with self.assertRaises(RuntimeError):self.admit()
            self.assertEqual({name:len(self.s.rows(name)) for name in counts},counts)
            self.assertEqual(self.s.row('activities',self.source_activity)['budget_json'],original_parent)

    def test_work_write_and_commit_failure_roll_back_parent_allocation(self):
        original=self.work.storage._insert
        def failing(grant,table,values):
            if table=='tl_work':raise RuntimeError('work write')
            return original(grant,table,values)
        before=self.s.row('activities',self.source_activity)['budget_json']
        with patch.object(self.work.storage,'_insert',side_effect=failing):
            with self.assertRaises(RuntimeError):self.admit()
        with patch.object(self.work.storage,'_commit',side_effect=RuntimeError('commit before durable')):
            with self.assertRaises(RuntimeError):self.admit()
        self.assertEqual(self.s.rows('tl_work'),[]);self.assertEqual(self.s.rows('tl_command'),[])
        self.assertEqual(self.s.row('activities',self.source_activity)['budget_json'],before)

    def test_forward_state_and_fixed_intent_with_cas(self):
        work_id=self.work_id(self.admit());request=self.transition_request(work_id)
        self.work.transition('synthetic-m14',request,'processing','assess','prepare')
        row=self.s.row('tl_work',work_id);self.assertEqual((row['state'],row['phase'],row['review_round'],row['row_revision']),('processing','assess',0,1))
        with self.assertRaises(Conflict):self.work.transition('synthetic-m14',request,'waiting','assess','prepare')
        stale=self.transition_request(work_id,'waiting','assess','missing',revision=0)
        with self.assertRaises(Conflict):self.work.transition('synthetic-m14',stale,'waiting','assess','missing')

    def test_waiting_does_not_resume_and_endpoint_default_rejects(self):
        work_id=self.work_id(self.admit());request=self.transition_request(work_id,'waiting','admit','missing')
        self.work.transition('synthetic-m14',request,'waiting','admit','missing')
        request=self.transition_request(work_id,revision=1)
        with self.assertRaises(Forbidden):self.work.transition('synthetic-m14',request,'processing','assess','prepare')
        self.assertEqual(self.s.row('tl_work',work_id)['state'],'waiting')

    def test_invalid_state_phase_and_caps_increase_rejected(self):
        work_id=self.work_id(self.admit());request=self.transition_request(work_id,'processing','complete','bad-phase')
        with self.assertRaises(Forbidden):self.work.transition('synthetic-m14',request,'processing','complete','bad-phase')
        request=self.transition_request(work_id);request['budget']['max_attempts']+=1
        with self.assertRaises(Conflict):self.work.transition('synthetic-m14',request,'processing','assess','prepare')

    def test_domain_endpoint_without_real_proof_is_not_completed(self):
        work_id=self.work_id(self.admit());request=self.transition_request(work_id)
        self.work.transition('synthetic-m14',request,'processing','assess','prepare')
        request=self.transition_request(work_id,'completed','complete','claimed-complete',revision=1)
        with self.assertRaises(Forbidden):self.work.transition('synthetic-m14',request,'completed','complete','claimed-complete')
        self.assertEqual(self.s.row('tl_work',work_id)['state'],'processing')

    def test_last_settled_attempt_can_record_zero_cost_fact_but_not_dispatch(self):
        from tests.test_tool_learning_budget import ToolLearningBudgetTests,MechanicalBudgetAuthority
        from digital_life.application.learning.budget import ToolLearningBudget,DIMENSIONS
        work_id=self.work_id(self.admit());work=self.s.row('tl_work',work_id)
        request=self.transition_request(work_id)
        self.work.transition('synthetic-m14',request,'processing','assess','prepare')
        # Reuse only the metadata fixture builder; no model callback is invoked.
        builder=ToolLearningBudgetTests('test_original_caps_and_read_only_snapshot')
        builder.s=self.s;builder.f=self.f;builder.activity=work['learning_activity_id'];builder.now=utc();builder.deadline=work['deadline'];builder.ref=self.ref
        operation=builder.operation()
        budget=ToolLearningBudget(self.s,MechanicalBudgetAuthority())
        reservation=budget.reserve('synthetic-im05',work_id,operation,'thought_attempt',{'attempts':1})
        budget.record_entry('synthetic-im05',work_id,reservation['id'],{'synthetic_witness':operation['id']})
        budget.settle('synthetic-im05',work_id,reservation['id'],{key:int(key=='attempts') for key in DIMENSIONS})
        self.assertEqual(budget.check_work(work_id)['remaining']['attempts'],0)
        proof=self.s.artifact({'contract':'SYNTHETIC-ENDPOINT-1','work_id':work_id,'fact':'proposal-saved'})
        def verify(entry,request,work,intent):
            self.assertEqual(intent['target'],'awaiting_decision')
            self.assertEqual(self.s.read_artifact(proof)['work_id'],work['id'])
        request=self.transition_request(work_id,'awaiting_decision','decide','synthetic-saved-proposal',revision=1)
        with patch.object(self.auth,'verify_endpoint',side_effect=verify):
            self.work.transition('synthetic-m14',request,'awaiting_decision','decide','synthetic-saved-proposal')
        self.assertEqual(self.s.row('tl_work',work_id)['state'],'awaiting_decision')
        with self.assertRaises(Forbidden):budget.reserve('synthetic-im05',work_id,builder.operation(),'thought_attempt',{'attempts':1})
        self.assertTrue(self.work.snapshot(work_id)['effective_blocked'])

    def test_snapshot_reports_effective_stop_without_mutating_persistent_state(self):
        work_id=self.work_id(self.admit());before=self.s.row('tl_work',work_id)
        self.f.control.stop('im05-snapshot-stop');snapshot=self.work.snapshot(work_id)
        self.assertTrue(snapshot['effective_blocked']);self.assertEqual(self.s.row('tl_work',work_id),before)

    def test_default_authority_rejects_even_unlocked_synthetic_instance(self):
        with self.assertRaises(Forbidden):ToolLearningWork(self.s).admit('synthetic-m14',self.request)

    def test_two_independent_connections_admit_one_logical_work(self):
        barrier=threading.Barrier(2);out=[];errors=[]
        def worker():
            store=Store(self.s.root)
            try:
                service=ToolLearningWork(store,SyntheticWorkAuthority(self.parent_caps));request=self.new_request()
                barrier.wait(timeout=5);out.append(service.admit('synthetic-m14',request))
            except BaseException as error:errors.append(error)
            finally:store.close()
        threads=[threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=10)
        self.assertFalse(any(t.is_alive() for t in threads));self.assertEqual(errors,[])
        self.assertEqual(len({self.work_id(r) for r in out}),1);self.assertEqual(len(self.s.rows('tl_work')),1)


if __name__=='__main__':unittest.main()
