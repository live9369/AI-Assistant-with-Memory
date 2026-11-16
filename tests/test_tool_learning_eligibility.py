"""IM06 qualification mechanics and real local callback entry ordering."""
import copy
import json
import multiprocessing
import os
import time
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.learning.eligibility import ToolLearningEligibility,EligibilityAuthority,scope_key,slot,ref
from digital_life.application.learning.invalidation import ToolLearningInvalidation
from tests import test_tool_learning_invalidation as fixture


def process_callback(root,context,entered,release,finished,trace,ready=None):
    s=None;started=time.monotonic()
    with open(trace+'.diagnostic','a') as f:f.write('callback child_started pid='+str(os.getpid())+'\n')
    try:
        s=Store(root)
        with open(trace+'.diagnostic','a') as f:f.write('callback store_opened elapsed='+str(time.monotonic()-started)+'\n')
        if ready is not None:ready.set()
        e=ToolLearningEligibility(s,fixture.MechanicalEligibility())
        def callback():
            with open(trace,'a') as f:f.write('entry\n')
            with open(trace+'.diagnostic','a') as f:f.write('callback actual_entry elapsed='+str(time.monotonic()-started)+'\n')
            entered.set()
            if not release.wait(8):raise RuntimeError('test release timeout')
            with open(trace,'a') as f:f.write('exit\n')
            return 'synthetic-result'
        e.callback('mechanical-im06',context['principal'],context['token'],context['scope'],'learn',context['principal']['recipient'],callback)
    except (Forbidden,Conflict) as error:
        with open(trace+'.diagnostic','a') as f:f.write(type(error).__name__+': '+str(error)+'\n')
        with open(trace,'a') as f:f.write('blocked\n')
    except BaseException as error:
        with open(trace+'.diagnostic','a') as f:f.write(type(error).__name__+': '+str(error)+'\n')
        raise
    finally:
        if s is not None:s.close()
        finished.set()


def process_f1(root,request,attempted,finished,trace):
    with open(trace+'.diagnostic','a') as f:f.write('f1 child_started pid='+str(os.getpid())+'\n')
    s=None
    try:
        s=Store(root)
        with open(trace+'.diagnostic','a') as f:f.write('f1 store_opened\n')
        attempted.set();ToolLearningInvalidation(s,fixture.MechanicalInvalidation()).apply('mechanical-im06',request)
        with open(trace,'a') as f:f.write('f1\n')
    except BaseException as error:
        with open(trace+'.diagnostic','a') as f:f.write('f1 '+type(error).__name__+': '+str(error)+'\n')
        raise
    finally:
        if s is not None:s.close()
        finished.set()


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        case=fixture.F1Tests();case.setUp();self.addCleanup(case.doCleanups)
        self.case=case;self.s=case.s;self.elig=case.elig;self.principal=case.query_principal;self.token=case.token;self.scope=case.scope
    def callback(self,fn,request=None):
        return self.elig.callback('mechanical-im06',self.principal,self.token,self.scope,'learn',self.principal['recipient'],fn,request=request)

    def test_selected_native_revision_keeps_independent_support_and_inputs(self):
        from digital_life.domain.contracts import utc
        c=self.case;s=self.s;content=identifier();revisions=[];decisions=[]
        def put(table,**fields):
            fields.setdefault('id',identifier());fields['instance_id']=s.instance_id
            s.insert(table,**fields);return fields['id']
        with s.tx():
            art=s.artifact({'synthetic':'revision-specific support'})
            put('tl_content',id=content,content_kind='source_report',row_revision=0)
            for n in (1,2):
                product=put('tl_product',work_id=c.work_id,product_type='UpdateProposal',payload_artifact_id=art,processing_identity=str(n)*64,source_fingerprint=str(n)*64)
                revision=identifier();decision=put('tl_decision',work_id=c.work_id,proposal_id=product,review_round=n,decision_artifact_id=art,operation='accept',content_revision_id=revision,policy_ref_id=c.f.expected['policy_id'],created_at=utc())
                put('tl_content_revision',id=revision,content_id=content,revision_no=n,decision_id=decision,product_id=product,payload_artifact_id=art,status='accepted',previous_revision_id=revisions[-1] if revisions else None)
                revisions.append(revision);decisions.append(decision)
            # A concrete r1 representation consumes stable content at r1.
            head=identifier();rep=identifier()
            put('tl_representation_head',id=head,content_id=content,format_version='TL-TEXT-1',representation_id=rep,expected_content_revision_id=revisions[0],row_revision=0)
            put('tl_representation',id=rep,series_id=head,content_revision_id=revisions[0],decision_id=decisions[0],format_version='TL-TEXT-1',representation_no=1,payload_artifact_id=art,body_artifact_id=art,body_digest=s.row('artifacts',art)['hash'],state='ready')
        owner=ref(s,content);r1={'object':owner,'revision':1,'epoch':0};r2={'object':owner,'revision':2,'epoch':0}
        # r1 supports A; r2 has an independent static source B.
        c.dependency(consumer=ref(s,revisions[0]),field='/support/a')
        b=ref(s,s.row('activities',c.base.source_activity)['trigger_event_id']);bt={'object':b,'revision':0,'epoch':0}
        c.dependency(consumer=ref(s,revisions[1]),source=b,token=bt,field='/support/b')
        c.dependency(consumer=ref(s,rep),source=owner,token=r1,field='/content')
        d1=c.dependency(source=owner,token=r1,field='/input/r1');d2=c.dependency(source=owner,token=r2,field='/input/r2')
        i1=self.elig.register_input('mechanical-im06',self.principal,c.consumer,d1)
        i2=self.elig.register_input('mechanical-im06',self.principal,c.consumer,d2)
        c.check(token=r1);c.check(token=r2)
        c.apply()
        with self.assertRaises((Forbidden,Conflict)):c.check(token=r1)
        with self.assertRaises((Forbidden,Conflict)):c.check(token={'object':ref(s,head),'revision':1,'epoch':0})
        self.assertTrue(c.check(token=r2)['qualified'])
        self.assertEqual(s.row('tl_input_dependency',i1)['retention_state'],'blocked')
        self.assertEqual(s.row('tl_input_dependency',i2)['retention_state'],'allowed')
        # Stable owner barriers are still inspected for the selected version.
        request=c.request();request['payload']['source']=r2
        c.apply(request)
        with self.assertRaises((Forbidden,Conflict)):c.check(token=dict(r2,epoch=1))

    def test_public_check_does_not_invert_lock_order_inside_transaction(self):
        with self.s.tx():
            with self.assertRaises(Conflict):self.case.check()

    def test_default_permission_and_entry_port_reject(self):
        service=ToolLearningEligibility(self.s)
        with self.assertRaises(Forbidden):service.check('x',self.principal,self.token,self.scope,'learn',self.principal['recipient'])
        class OnlyRead(fixture.MechanicalEligibility):
            verify_callback=EligibilityAuthority.verify_callback
        with self.assertRaises(Forbidden):ToolLearningEligibility(self.s,OnlyRead()).callback('x',self.principal,self.token,self.scope,'learn',self.principal['recipient'],lambda:True)

    def test_dependency_and_input_registration_are_idempotent(self):
        first=self.case.dependency();self.assertEqual(first,self.case.dependency())
        one=self.elig.register_input('mechanical-im06',self.principal,self.case.consumer,first)
        self.assertEqual(one,self.elig.register_input('mechanical-im06',self.principal,self.case.consumer,first))
        self.assertEqual(self.callback(lambda:'local',self.case.consumer),'local')

    def test_registration_requires_full_consumer_authority(self):
        class NoRegistration(fixture.MechanicalEligibility):
            verify_registration=EligibilityAuthority.verify_registration
        self.case.elig=ToolLearningEligibility(self.s,NoRegistration())
        with self.assertRaises(Forbidden):self.case.dependency()
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM tl_dependency').fetchone()[0],0)

    def test_input_purpose_cannot_differ_from_dependency(self):
        dep=self.case.dependency();p=copy.deepcopy(self.principal);p['purpose']='evaluate'
        with self.assertRaises(Forbidden):self.elig.register_input('mechanical-im06',p,self.case.consumer,dep)

    def test_same_owner_wrong_revision_projection_is_rejected(self):
        first=self.case.dependency();row=self.s.row('tl_dependency',first)
        memory=self.s.row('memory_revisions',self.case.f.expected['memory_revision_id'])
        memory.update(id=identifier(),revision_no=2)
        with self.s.tx():self.s.insert('memory_revisions',**memory)
        revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=2',(self.s.instance_id,self.case.source['id'])).fetchone()[0]
        metadata=self.s.read_artifact(row['metadata_artifact_id']);metadata['field_path']='/wrong-revision'
        bad=identifier()
        with self.s.tx():
            self.s.insert('tl_dependency',id=bad,consumer_ref_id=row['consumer_ref_id'],source_ref_id=row['source_ref_id'],source_revision_id=revision,relation='read',purpose='learn',expected_epoch=0,field_path='/wrong-revision',metadata_artifact_id=self.s.artifact(metadata))
        with self.assertRaises(ContractError):self.elig.register_input('x',self.principal,self.case.consumer,bad)

    def test_dependency_metadata_mismatch_fails_closed(self):
        dep=self.case.dependency();row=self.s.row('tl_dependency',dep)
        # A raw corrupted metadata artifact is not accepted as a valid edge.
        original=self.elig.artifacts.read_artifact
        def corrupt(key,*args):
            value=original(key,*args)
            if key==row['metadata_artifact_id']:value['dependency']['relation']='support'
            return value
        with patch.object(self.elig.artifacts,'read_artifact',corrupt):
            with self.assertRaises(ContractError):self.elig.register_input('mechanical-im06',self.principal,self.case.consumer,dep)

    def test_ordinary_stop_and_wake_lock_refuse_actual_callback(self):
        calls=[];self.case.f.control.stop('test stop')
        with self.assertRaises(Forbidden):self.callback(lambda:calls.append(1))
        self.assertEqual(calls,[])
        self.case.f.control.resume('test resume');(self.s.root/'WAKE_DISABLED').write_text('locked')
        with self.assertRaises(Forbidden):self.callback(lambda:calls.append(1))
        self.assertEqual(calls,[])

    def test_authority_callback_stop_is_rechecked_at_entry(self):
        class Stop(fixture.MechanicalEligibility):
            def verify_callback(_,entry,principal,context,stage):self.case.f.control.stop('within authority')
        self.elig=ToolLearningEligibility(self.s,Stop());calls=[]
        with self.assertRaises(Forbidden):self.callback(lambda:calls.append(1))
        self.assertEqual(calls,[])

    def test_active_barrier_prevents_prepared_from_becoming_callback(self):
        prepared=True;self.case.apply();calls=[]
        with self.assertRaises((Forbidden,Conflict)):self.callback(lambda:calls.append(1))
        self.assertTrue(prepared);self.assertEqual(calls,[])

    def test_same_thread_f1_preserves_entry_but_refuses_result_use(self):
        calls=[]
        def callback():
            calls.append('entered');self.case.apply();calls.append('still-in-flight');return 'not-accepted'
        with self.assertRaises((Forbidden,Conflict)):self.callback(callback)
        self.assertEqual(calls,['entered','still-in-flight'])

    def test_caller_mutation_does_not_rebind_result_to_other_source(self):
        def callback():
            self.case.apply();self.token['epoch']=1;self.scope['limitations'].append('changed')
            self.principal['purpose']='history_audit';return 'not-accepted'
        with self.assertRaises((Forbidden,Conflict)):self.callback(callback)

    def test_all_registered_inputs_checked_not_just_supplied_token(self):
        dep=self.case.dependency();self.elig.register_input('mechanical-im06',self.principal,self.case.consumer,dep)
        self.case.apply();other=ref(self.s,self.case.f.expected['activity_id']);token={'object':other,'revision':0,'epoch':0}
        with self.assertRaises((Forbidden,Conflict)):
            self.elig.callback('mechanical-im06',self.principal,token,self.scope,'learn',self.principal['recipient'],lambda:'not-entered',request=self.case.consumer)

    def test_cancelled_request_activity_cannot_enter(self):
        self.s.db.execute("UPDATE activities SET cancel_requested_at='2026-11-09T00:00:00.000Z' WHERE id=?",(self.case.consumer['id'],))
        with self.assertRaises(Forbidden):self.callback(lambda:True,self.case.consumer)

    def test_upstream_source_barrier_blocks_derived_consumer(self):
        self.case.dependency();self.case.apply();token={'object':self.case.consumer,'revision':0,'epoch':0}
        with self.assertRaises((Forbidden,Conflict)):self.elig.check('x',self.principal,token,self.scope,'learn',self.principal['recipient'])

    def test_delete_only_edge_does_not_become_support_failure(self):
        dep={'target':self.case.source,'relation':'delete','expected':self.token,'consumer_purpose':'learn'}
        self.elig.register_dependency('x',self.principal,self.case.consumer,dep,'/retention',self.scope)
        self.case.apply();token={'object':self.case.consumer,'revision':0,'epoch':0}
        self.elig.check('x',self.principal,token,self.scope,'learn',self.principal['recipient'])
        self.case.apply(self.case.request('erase',1))
        with self.assertRaises(Forbidden):self.elig.check('x',self.principal,token,self.scope,'learn',self.principal['recipient'])

    def test_dependency_cycle_is_bounded_and_not_a_missing_barrier(self):
        self.case.dependency()
        back={'target':self.case.consumer,'relation':'derive','expected':{'object':self.case.consumer,'revision':0,'epoch':0},'consumer_purpose':'learn'}
        self.elig.register_dependency('x',self.principal,self.case.source,back,'/back',self.scope)
        self.case.check()
        self.case.apply()
        with self.assertRaises((Forbidden,Conflict)):self.case.check()

    def test_barrier_scan_limit_blocks_even_if_purpose_filter_might_skip(self):
        self.case.apply();self.case.apply(self.case.request('conflict',1))
        p=copy.deepcopy(self.principal);p['purpose']='history_audit';token=copy.deepcopy(self.token);token['epoch']=2
        limited=ToolLearningEligibility(self.s,self.case.elig_auth,max_rows=1)
        with self.assertRaises(Forbidden):limited.check('x',p,token,self.scope,'history_audit',p['recipient'])

    def test_registration_commit_revocation_rolls_back_new_dependency(self):
        class Revoke(fixture.MechanicalEligibility):
            def verify_registration(_,entry,principal,context,stage):
                if stage=='commit':raise Forbidden('revoked before commit')
        self.case.elig=ToolLearningEligibility(self.s,Revoke())
        with self.assertRaises(Forbidden):self.case.dependency()
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM tl_dependency').fetchone()[0],0)

    def test_many_duplicate_node_edges_are_bounded(self):
        for n in range(3):self.case.dependency(field='/'+str(n))
        bounded=ToolLearningEligibility(self.s,self.case.elig_auth,max_rows=2)
        with self.assertRaises(Forbidden):bounded.check('x',self.principal,{'object':self.case.consumer,'revision':0,'epoch':0},self.scope,'learn',self.principal['recipient'])
        f1=ToolLearningInvalidation(self.s,self.case.authority,max_rows=2);f1.apply('mechanical-im06',self.case.request())
        self.assertTrue(all(self.s.read_artifact(r[0])['truncated'] for r in self.s.db.execute('SELECT coverage_artifact_id FROM tl_propagation')))

    def test_many_input_rows_do_not_delay_or_omit_root_barrier(self):
        for n in range(3):
            dep=self.case.dependency(field='/'+str(n));self.elig.register_input('x',self.principal,self.case.consumer,dep)
        ToolLearningInvalidation(self.s,self.case.authority,max_rows=1).apply('mechanical-im06',self.case.request())
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM tl_barrier').fetchone()[0],1)
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM tl_input_dependency WHERE retention_state='blocked'").fetchone()[0],1)
        self.assertTrue(all(self.s.read_artifact(r[0])['truncated'] for r in self.s.db.execute('SELECT coverage_artifact_id FROM tl_propagation')))

    def test_thread_callback_first_f1_waits_for_real_exit(self):
        entered=threading.Event();release=threading.Event();committed=threading.Event();errors=[];events=[]
        def callback_worker():
            s=Store(self.s.root)
            try:
                def callback():
                    events.append('entry');entered.set()
                    if not release.wait(5):raise RuntimeError('release timeout')
                    events.append('exit')
                ToolLearningEligibility(s,fixture.MechanicalEligibility()).callback('x',self.principal,self.token,self.scope,'learn',self.principal['recipient'],callback)
            except BaseException as e:errors.append(e)
            finally:s.close()
        change_request=self.case.request()
        def f1_worker():
            s=Store(self.s.root)
            try:ToolLearningInvalidation(s,fixture.MechanicalInvalidation()).apply('mechanical-im06',change_request);events.append('f1');committed.set()
            except BaseException as e:errors.append(e)
            finally:s.close()
        a=threading.Thread(target=callback_worker);b=threading.Thread(target=f1_worker)
        a.start();self.assertTrue(entered.wait(5));b.start();self.assertFalse(committed.wait(.1));release.set();a.join(5);b.join(5)
        self.assertFalse(a.is_alive() or b.is_alive());self.assertEqual(errors,[]);self.assertEqual(events,['entry','exit','f1'])

    def test_process_callback_first_f1_waits_and_process_f1_first_blocks(self):
        # Independent production workers start fresh; do not fork a live SQLite/
        # thread-bearing test interpreter (03 observed SIGSEGV before Store opened).
        ctx=multiprocessing.get_context('spawn');trace=str(self.s.root/'order.log')
        context={'principal':self.principal,'token':self.token,'scope':self.scope}
        entered,release,finished,attempted,committed,ready=[ctx.Event() for _ in range(6)]
        callback=ctx.Process(target=process_callback,args=(str(self.s.root),context,entered,release,finished,trace,ready))
        change=ctx.Process(target=process_f1,args=(str(self.s.root),self.case.request(),attempted,committed,trace))
        processes=[callback,change]
        try:
            def diagnostic():
                path=Path(trace+'.diagnostic');return 'exit='+str(callback.exitcode)+' trace='+str(Path(trace).read_text() if Path(trace).exists() else '')+' diagnostic='+(path.read_text() if path.exists() else '')
            callback.start();self.assertTrue(ready.wait(10),diagnostic());self.assertTrue(entered.wait(5),diagnostic());change.start();self.assertTrue(attempted.wait(5));self.assertFalse(committed.wait(.1));release.set()
            for p in processes:p.join(8);self.assertEqual(p.exitcode,0,diagnostic())
            self.assertEqual(Path(trace).read_text().splitlines(),['entry','exit','f1'])
            entered2,release2,finished2=[ctx.Event() for _ in range(3)];release2.set()
            blocked=ctx.Process(target=process_callback,args=(str(self.s.root),context,entered2,release2,finished2,trace));processes.append(blocked)
            blocked.start();blocked.join(8);self.assertEqual(blocked.exitcode,0);self.assertFalse(entered2.is_set())
            self.assertEqual(Path(trace).read_text().splitlines()[-1],'blocked')
        finally:
            release.set()
            for p in processes:
                if p.pid is not None and p.is_alive():p.terminate();p.join(3)

if __name__=='__main__':unittest.main()
