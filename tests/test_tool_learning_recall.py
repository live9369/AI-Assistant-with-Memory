"""IM10 exact provenance, bounded resources and zero-write controller audit."""
import copy
from contextlib import contextmanager
import math
import time
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc,sha,dumps
from digital_life.domain import tool_learning_contract as c
from digital_life.application.learning.recall import ToolLearningRecall,RecallAuthority
from digital_life.application.learning.eligibility import slot,ref
from tests import test_tool_learning_representation as representation
from tests.test_tool_learning_invalidation import MechanicalEligibility


class MechanicalRecall(RecallAuthority):
    def __init__(self,case):self.case=case;self.hook=None;self.retention_hook=None;self.reader=None;self.scope=True;self.tokens=1;self.legacy_source=None;self.reservation=slot();self.forced_reservation=False;self.last_usage=None
    def verify_request(self,entry,request,stage):
        if entry!='synthetic-recall':raise Forbidden('no actual synthetic recall channel')
        if self.hook:self.hook(stage)
    def verify_audit(self,*args):return None
    def verify_candidate_access(self,*args):return None
    def verify_retention(self,entry,request,item,stage):
        if self.retention_hook:self.retention_hook(stage)
    def execution_reservation(self,*args):return copy.deepcopy(self.reservation)
    def verify_execution_accounting(self,*args):return None
    def verify_trace(self,*args):return None
    def verify_input_binding(self,*args):return None
    def verify_fallback(self,*args):return None
    def scope_matches(self,*args):return self.scope
    def count_tokens(self,*args):return self.tokens
    @contextmanager
    def read_boundary(self,entry,request,reader):
        previous=self.reader;self.reader=reader
        try:yield
        finally:
            meter=self.case.service._meter
            if meter is not None:
                from digital_life.application.learning.budget import DIMENSIONS
                usage={key:0 for key in DIMENSIONS};usage.update(bytes=meter['read_bytes'],items=meter['material_items'],scan=max(0,meter.get('scan_limit',self.case.request['budget']['max_scan'])-meter['scan']['remaining']),elapsed_ms=max(0,math.ceil((self.case.service.monotonic()-meter['started'])*1000)));self.last_usage=None if meter['usage_unknown'] else usage
            self.reader=previous
    def source_token(self,entry,request,evidence):return {'object':copy.deepcopy(evidence['source']),'revision':1 if evidence['source']['kind']=='memory_items' else 0,'epoch':0}
    def legacy_material(self,entry,request,target,row):
        return {'kind':'episode' if request['principal']['purpose']=='recall_episode' else 'source_evidence','scope':copy.deepcopy(self.case.scope),'source_refs':[copy.deepcopy(self.legacy_source or self.case.case.case.product['body']['claims'][0]['evidence'][0])],'origin_kind':'user_statement','processing':'raw','values':[],'limitations':['user statement is not independently confirmed world truth']}


class RecallTests(unittest.TestCase):
    def setUp(self):
        self.case=representation.RepresentationTests()
        original=representation.acceptance.observation.ObservationTests.prepare
        def larger_source_budget(obs):
            obs.base.auth.parent['max_bytes']=300000
            obs.request['budget']['max_bytes']=300000;obs.request['budget']['max_scan']=100;return original(obs)
        with patch.object(representation.acceptance.observation.ObservationTests,'prepare',larger_source_budget):self.case.setUp()
        self.addCleanup(self.case.doCleanups);pub=self.case.publish_request();self.case.service.publish(self.case.entry,pub)
        self.s=self.case.s;self.db=self.s.db;self.scope=copy.deepcopy(self.case.case.product['body']['claims'][0]['scope']);work=self.s.row('tl_work',self.case.case.obs.work['id'])
        context=self.s.insert('context_snapshots',activity_id=work['learning_activity_id'],context_schema='synthetic-recall-1',attributes_json={})
        self.authority=MechanicalRecall(self);self.eligibility=MechanicalEligibility();self.service=ToolLearningRecall(self.s,self.authority,self.eligibility)
        self.request={'contract':'TL-LOOP-0.1','schema_revision':1,'request_id':identifier(),'instance_id':self.s.instance_id,'activity_ref':slot(ref(self.s,work['learning_activity_id'])),'context_ref':slot(ref(self.s,context)),'principal':copy.deepcopy(self.case.request['principal']),'entry':'execution','query':'inventory','target_scope':copy.deepcopy(self.scope),'exact_refs':[ref(self.s,self.case.representation['id'])],'version_mode':'current','as_of':slot(),'group_required':True,'allowed_kinds':['accepted_content'],'control':copy.deepcopy(self.case.request['control']),'budget':copy.deepcopy(self.case.request['budget']),'index_fallback':'bounded_primary'}
        self.request['principal'].update(module='M04',purpose='recall_experience')
    def recall(self,begin=True):
        if self.request['entry']=='controller_audit':return self.service.recall('synthetic-recall',self.request)
        if begin:self.service.begin('synthetic-recall',self.request)
        event=self.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='tl.recall.begin' AND source_event_id=?",(self.request['request_id'],)).fetchone()
        if event is None or self.authority.forced_reservation:return self.service.recall('synthetic-recall',self.request)
        from digital_life.application.learning.budget import ToolLearningBudget,BudgetAuthority,DIMENSIONS
        class B(BudgetAuthority):
            def verify_budget(self,*args):return None
            def verify_entry(self,*args):return None
            def verify_settlement(self,*args):return None
        run=self.s.read_artifact(event[0])['run'];work=self.db.execute('SELECT id FROM tl_work WHERE learning_activity_id=?',(self.request['activity_ref']['value']['id'],)).fetchone()[0];budget=ToolLearningBudget(self.s,B());remaining=budget.check_work(work)['remaining'];amounts={key:0 for key in DIMENSIONS}
        for key in ('bytes','scan','items','elapsed_ms'):amounts[key]=remaining[key]
        if not amounts['bytes'] or not amounts['scan'] or not amounts['items']:
            self.authority.reservation=slot()
            return self.service.recall('synthetic-recall',self.request)
        reservation=budget.reserve('synthetic-recall',work,run,'retrieval',amounts,request_budget=self.request['budget'],reservation_key='im10-test:'+identifier());budget.record_entry('synthetic-recall',work,reservation['id'],{'contract':'SYNTHETIC-RECALL-ENTRY-1','request_id':self.request['request_id']});self.authority.reservation=slot(reservation['id']);self.authority.last_usage=None
        try:return self.service.recall('synthetic-recall',self.request)
        finally:
            usage=self.authority.last_usage
            budget.settle('synthetic-recall',work,reservation['id'],usage)
    def audit(self,purpose='history_audit',kinds=None):
        self.request.update(entry='controller_audit',request_id=identifier());self.request['principal'].update(actor=ref(self.s,self.case.case.obs.base.f.expected['controller']),purpose=purpose);self.request['allowed_kinds']=kinds or ['accepted_content','history'];return self.request
    def test_execution_returns_typed_ready_current_item_and_real_trace(self):
        result=self.recall();c.validate('RecallResult',result);self.assertEqual(len(result['items']),1);self.assertEqual(result['items'][0]['kind'],'accepted_content');self.assertEqual(result['items'][0]['usage_state'],'current');self.assertEqual(self.db.execute('SELECT count(*) FROM tl_recall_item').fetchone()[0],1)
    def test_audit_is_zero_write_even_stopped_and_wake_locked(self):
        self.audit();self.case.case.obs.base.f.control.stop('audit while stopped');(self.s.root/'WAKE_DISABLED').write_text('synthetic audit lock');before=self.db.total_changes;counts={t:self.db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('artifacts','runtime_events','memory_retrieval_runs','tl_recall_item','memory_access_records')};result=self.recall();self.assertEqual(len(result['items']),1);self.assertEqual(result['retrieval_run']['status'],'not_applicable');self.assertEqual(self.db.total_changes,before)
        for table,count in counts.items():self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],count)
    def test_default_authority_rejects_without_writes(self):
        before=self.db.total_changes
        with self.assertRaises(Forbidden):ToolLearningRecall(self.s).recall('x',self.request)
        self.assertEqual(before,self.db.total_changes)
    def revoke(self,purposes=None,kind='revoke'):
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        from tests.test_tool_learning_invalidation import MechanicalInvalidation
        request=copy.deepcopy(self.case.request);request.update(command_id=identifier(),idempotency_key=identifier());request['principal'].update(module='M12',purpose='erase' if kind=='erase' else 'propagate');source=copy.deepcopy(self.case.case.product['body']['claims'][0]['evidence'][0]['source'])
        request['payload']={'change_id':identifier(),'kind':kind,'source':{'object':source,'revision':1,'epoch':0},'replacement':slot(),'affected_scope':copy.deepcopy(self.scope),'subjects':[],'purposes':purposes or ['recall_experience','recall_episode','verify_source','history_audit','learn'],'expected_epoch':0,'evidence':copy.deepcopy(self.case.case.product['body']['claims'][0]['evidence']),'erase_scope':slot(ref(self.s,self.case.case.obs.base.f.expected['policy_id'])) if kind=='erase' else slot()}
        ToolLearningInvalidation(self.s,MechanicalInvalidation()).apply('mechanical-im06',request)
    def legacy(self):
        from digital_life.application.services.memory import Memory
        memory=Memory(self.s).encode('source inventory seven',self.case.case.obs.base.f.expected['source_evidence_id']);self.request['principal']['purpose']='recall_episode';self.request['allowed_kinds']=['episode'];self.request['exact_refs']=[ref(self.s,memory['revision_id'])];return memory
    def target(self,result):
        activity=self.s.row('activities',self.request['activity_ref']['value']['id']);packet={'recall':copy.deepcopy(result['items'])};artifact=self.s.artifact(packet)
        step=self.s.insert('activity_steps',activity_id=activity['id'],step_no=500,step_type='synthetic-input-proof',state='pending',attempt=0,idempotency_key=identifier())
        request=self.s.insert('thought_requests',activity_id=activity['id'],step_id=step,request_key=identifier(),purpose='infer',task='synthetic input assembly only',instruction_version='im10-test',output_schema_version=0,request_artifact_id=artifact,request_hash=sha(dumps(packet)),input_manifest_hash=sha(dumps(packet)),model_config_id=self.db.execute('SELECT id FROM configuration_versions LIMIT 1').fetchone()[0],model_version_id=self.db.execute('SELECT id FROM model_versions LIMIT 1').fetchone()[0],prepared_activity_revision=activity['revision'],expected_input_epoch=activity['input_epoch'],expected_policy_epoch=0,runtime_epoch=0,process_run_id='synthetic-no-runtime',deadline=self.request['budget']['deadline'],token_budget=10,attempt_limit=1,retry_policy={},generation_config={},state='prepared')
        return ref(self.s,request)
    def test_execution_requires_real_context_and_admitted_run(self):
        with self.assertRaises(Forbidden):self.recall(begin=False)
        self.request['context_ref']=slot()
        with self.assertRaises(Forbidden):self.recall()
    def test_ordinary_recall_cannot_run_while_stopped(self):
        self.case.case.obs.base.f.control.stop('ordinary recall stopped')
        with self.assertRaises(Forbidden):self.recall()
    def test_audit_wrong_controller_or_purpose_is_rejected(self):
        self.audit();self.request['principal']['actor']=ref(self.s,self.case.case.obs.base.f.expected['self_actor'])
        with self.assertRaises(Forbidden):self.recall()
        self.request['principal']['purpose']='learn'
        with self.assertRaises(ContractError):self.recall()
    def test_unknown_scope_never_becomes_a_match(self):
        self.audit();self.authority.scope=None;result=self.recall();self.assertEqual(result['items'],[]);self.assertIn(result['completion'],('not_ready','partial'))
    def test_c1_head_without_c2_is_not_directly_read_as_experience(self):
        self.case.case.replace_product(lambda p:p['body'].update(rationale='second source report'));self.case.case.request.update(command_id=identifier(),idempotency_key=identifier());self.case.case.review();decision=self.case.case.decision();self.request['exact_refs']=[decision['content_ref']['value']];result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(result['completion'],'not_ready')
    def test_recall_episode_uses_actual_legacy_version_not_tl_acceptance(self):
        memory=self.legacy();result=self.recall();item=result['items'][0];self.assertEqual(item['kind'],'episode');self.assertEqual(item['body'],'source inventory seven');self.assertEqual(item['memory_revision']['value']['revision'],1);self.assertEqual(item['decision_ref']['status'],'not_applicable');self.assertEqual(self.db.execute('SELECT count(*) FROM memory_access_records WHERE memory_revision_id=?',(memory['revision_id'],)).fetchone()[0],1)
    def test_legacy_original_source_a_revocation_blocks_trace_replay_and_actual_callback(self):
        self.legacy();result=self.recall();self.assertGreaterEqual(len(result['items'][0]['dependencies']),2);target=self.target(result);principal=copy.deepcopy(self.request['principal']);principal['purpose']='learn'
        inputs=self.service.register_inputs('synthetic-recall',self.request,result,target,principal);self.assertGreaterEqual(len(inputs),2)
        from digital_life.application.learning.eligibility import ToolLearningEligibility
        gate=ToolLearningEligibility(self.s,MechanicalEligibility());memory_token=result['items'][0]['memory_revision']['value'];self.revoke();entered=[]
        with self.assertRaises((Forbidden,Conflict)):gate.callback('synthetic-input',principal,memory_token,self.scope,'learn',principal['recipient'],lambda:entered.append(1),request=target)
        self.assertEqual(entered,[])
        with self.assertRaises((Forbidden,Conflict)):self.recall()
        self.assertTrue(any(self.s.row('tl_input_dependency',key)['retention_state']=='blocked' for key in inputs))
    def test_readonly_audit_does_not_bypass_source_erase(self):
        self.audit();self.revoke(kind='erase');self.case.case.obs.base.f.control.stop('audit stopped after erase');before=self.db.total_changes;result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(self.db.total_changes,before)
    def test_audit_local_scan_one_cannot_walk_deep_support(self):
        self.audit();self.request['budget']['max_scan']=1;before=self.db.total_changes;result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(result['completion'],'partial');self.assertEqual(self.db.total_changes,before)
    def test_audit_byte_limit_includes_dependency_metadata(self):
        self.audit();self.request['budget']['max_bytes']=10;result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(result['completion'],'partial')
    def test_scope_callback_deadline_prevents_further_material(self):
        self.audit();deadline=self.request['budget']['deadline']
        def expire(*args):self.service.clock=lambda:deadline;return True
        self.authority.scope_matches=expire;before=self.db.total_changes;result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(result['completion'],'partial');self.assertEqual(self.db.total_changes,before)
    def test_whole_item_token_bound_never_strips_limitations(self):
        self.audit();self.authority.tokens=self.request['budget']['max_input_tokens']+1;result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(result['completion'],'partial')
    def test_no_recent_irrelevant_fill_when_no_lexical_match(self):
        self.audit();self.request.update(exact_refs=[],query='unrelated_zebra_unicorn');result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(result['empty_reason']['status'],'known')
    def test_no_index_fallback_permission_cannot_repair_or_read(self):
        self.audit();self.request.update(exact_refs=[],index_fallback='deny');before=self.db.total_changes;result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(self.db.total_changes,before)
    def test_trace_retention_revocation_cannot_persist_result(self):
        self.service.begin('synthetic-recall',self.request);before=self.db.execute('SELECT count(*) FROM artifacts').fetchone()[0]
        self.authority.retention_hook=lambda stage:setattr(self.eligibility,'deny',True) if stage=='trace_write' else None
        with self.assertRaises(Forbidden):self.recall(begin=False)
        self.assertEqual(self.db.execute('SELECT count(*) FROM artifacts').fetchone()[0],before+1);entry=self.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='tl.recall.read_entry'").fetchone()[0];self.assertEqual(self.s.read_artifact(entry)['contract'],'TL-RECALL-READ-ENTRY-1');self.assertEqual(self.db.execute('SELECT count(*) FROM tl_recall_item').fetchone()[0],0)
    def test_replay_always_rechecks_current_retention(self):
        self.recall();self.authority.retention_hook=lambda stage:setattr(self.eligibility,'deny',True) if stage=='replay' else None
        with self.assertRaises(Forbidden):self.recall()
    def test_audit_results_cannot_register_model_inputs(self):
        self.audit();result=self.recall()
        with self.assertRaises(Forbidden):self.service.register_inputs('synthetic-recall',self.request,result,ref(self.s,self.case.case.obs.work['id']),self.request['principal'])
    def test_specified_revision_never_ignores_registered_number(self):
        self.audit();self.request['version_mode']='specified';self.request['exact_refs'][0]['revision']=slot(999);result=self.recall();self.assertEqual(result['items'],[])

    def second_version(self):
        old=copy.deepcopy(self.case.representation);cutoff=self.s.row('tl_representation',old['id'])['recorded_at'];token={'object':self.case.decision['content_ref']['value'],'revision':1,'epoch':0}
        self.case.case.existing(token);self.case.case.request.update(command_id=identifier(),idempotency_key=identifier());self.case.case.review(native=token);decision=self.case.case.decision();self.case.request.update(command_id=identifier(),idempotency_key=identifier());self.case.request['payload']['handoff']=decision['handoff_refs'][0];self.case.claimed=self.case.claim();self.case.representation=self.case.service.build(self.case.entry,self.case.request,self.case.claimed);self.case.service.publish(self.case.entry,self.case.publish_request());return old,cutoff
    def adopt_group(self):
        original=representation.acceptance.observation.ObservationTests.prepare
        def large(obs):
            obs.base.auth.parent['max_bytes']=500000;obs.base.auth.parent['max_scan']=512
            obs.request['budget']['max_bytes']=500000;obs.request['budget']['max_scan']=512
            return original(obs)
        with patch.object(representation.acceptance.observation.ObservationTests,'prepare',large):self.case.group_setup()
        first=self.case.group_publish_request(0);self.case.service.publish(self.case.entries[0],first);second=self.case.group_publish_request(1);self.case.service.publish(self.case.entries[1],second);self.s=self.case.s;self.db=self.case.db;self.scope=copy.deepcopy(self.case.case.product['body']['claims'][0]['scope']);activity=self.case.group_claims[0]['work_ref']['value']['id'];work=self.s.row('tl_work',activity);context=self.s.insert('context_snapshots',activity_id=work['learning_activity_id'],context_schema='synthetic-group-query',attributes_json={})
        self.authority=MechanicalRecall(self);self.eligibility=MechanicalEligibility();self.service=ToolLearningRecall(self.s,self.authority,self.eligibility);self.request.update(request_id=identifier(),instance_id=self.s.instance_id,activity_ref=slot(ref(self.s,work['learning_activity_id'])),context_ref=slot(ref(self.s,context)),principal=copy.deepcopy(first['principal']),control=copy.deepcopy(first['control']),budget=copy.deepcopy(first['budget']),target_scope=copy.deepcopy(self.scope),exact_refs=[ref(self.s,first['payload']['representation']['id'])]);self.request['principal']['purpose']='recall_experience';return first,second
    def test_as_of_selects_real_earlier_version_once_not_current_or_all_history(self):
        old,cutoff=self.second_version();self.audit(kinds=['history','accepted_content']);self.request.update(version_mode='as_of',as_of=slot(cutoff),exact_refs=[copy.deepcopy(old['series_ref'])]);result=self.recall();self.assertEqual(len(result['items']),1);self.assertEqual(result['items'][0]['representation_revision']['value']['revision'],1);self.assertEqual(result['items'][0]['usage_state'],'historical')
        self.request['exact_refs']=[old['content_ref']];result=self.recall();self.assertEqual(len(result['items']),1);self.assertEqual(result['items'][0]['content_revision']['value']['revision'],1)
        self.request.update(exact_refs=[],query='inventory');result=self.recall();self.assertEqual(len(result['items']),1);self.assertEqual(result['items'][0]['representation_revision']['value']['revision'],1)
    def test_ordinary_experience_as_of_cannot_upgrade_historical_version(self):
        old,cutoff=self.second_version();self.request.update(version_mode='as_of',as_of=slot(cutoff),exact_refs=[old['series_ref']]);result=self.recall();self.assertEqual(result['items'],[])
    def test_specified_content_revision_returns_exact_history_only_for_audit(self):
        old,_=self.second_version();self.audit(kinds=['history']);target=copy.deepcopy(old['content_ref']);target['revision']=slot(1);self.request.update(version_mode='specified',exact_refs=[target]);result=self.recall();self.assertEqual(len(result['items']),1);self.assertEqual(result['items'][0]['content_revision']['value']['revision'],1)
    def test_group_ready_flag_does_not_survive_other_member_f1(self):
        first,second=self.adopt_group();initial=self.recall();self.assertEqual(len(initial['items']),1);self.assertGreaterEqual(len(initial['items'][0]['dependencies']),2)
        target=self.target(initial);registered=self.service.register_inputs('synthetic-recall',self.request,initial,target,self.request['principal'])
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        from tests.test_tool_learning_invalidation import MechanicalInvalidation
        request=copy.deepcopy(second);request.update(command_id=identifier(),idempotency_key=identifier());request['principal'].update(module='M12',purpose='propagate');request['payload']={'change_id':identifier(),'kind':'revoke','source':{'object':second['payload']['representation']['series_ref'],'revision':1,'epoch':0},'replacement':slot(),'affected_scope':copy.deepcopy(self.scope),'subjects':[],'purposes':['recall_experience'],'expected_epoch':0,'evidence':copy.deepcopy(second['payload']['representation']['source_refs']),'erase_scope':slot()};ToolLearningInvalidation(self.s,MechanicalInvalidation()).apply('mechanical-im06',request)
        self.assertEqual(self.db.execute('SELECT state FROM tl_group').fetchone()[0],'ready');self.request['request_id']=identifier();result=self.recall();self.assertEqual(result['items'],[])
        from digital_life.application.learning.eligibility import ToolLearningEligibility
        with self.assertRaises((Forbidden,Conflict)):ToolLearningEligibility(self.s,MechanicalEligibility()).callback('synthetic',self.request['principal'],initial['items'][0]['representation_revision']['value'],self.scope,'recall_experience',self.request['principal']['recipient'],lambda:'must not enter',request=target)
        self.assertTrue(any(self.s.row('tl_input_dependency',key)['retention_state']=='blocked' for key in registered))
    def test_group_whole_current_mapping_is_checked_under_same_meter(self):
        first,second=self.adopt_group();self.audit();self.request['budget']['max_scan']=2;result=self.recall();self.assertEqual(result['items'],[]);self.assertIn(result['completion'],('partial','not_ready'))
    def test_input_all_precheck_rejects_wrong_second_item_before_any_registration(self):
        result=self.recall();target=self.target(result);bad=copy.deepcopy(result);bad['items'].append(copy.deepcopy(result['items'][0]));bad['items'][-1]['id']=identifier()
        with self.assertRaises(ContractError):self.service.register_inputs('synthetic-recall',self.request,bad,target,self.request['principal'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_input_dependency WHERE request_ref_id=?',(target['id'],)).fetchone()[0],0)
    def test_partial_input_failure_has_no_completion_or_default_callback_permission(self):
        self.legacy();result=self.recall();target=self.target(result);principal=copy.deepcopy(self.request['principal']);principal['purpose']='learn';original=self.service.eligibility.register_input;calls=[]
        def fail_second(*args,**kwargs):
            calls.append(1)
            if len(calls)==2:raise OSError('synthetic second input registration failed')
            return original(*args,**kwargs)
        with patch.object(self.service.eligibility,'register_input',fail_second):
            with self.assertRaises(OSError):self.service.register_inputs('synthetic-recall',self.request,result,target,principal)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_input_dependency WHERE request_ref_id=?',(target['id'],)).fetchone()[0],1)
        from digital_life.application.learning.eligibility import ToolLearningEligibility,EligibilityAuthority
        class NoAssembly(MechanicalEligibility):verify_callback=EligibilityAuthority.verify_callback
        with self.assertRaises(Forbidden):ToolLearningEligibility(self.s,NoAssembly()).callback('synthetic',principal,result['items'][0]['memory_revision']['value'],self.scope,'learn',principal['recipient'],lambda:'must not enter',request=target)
    def test_qualification_callback_deadline_and_metadata_reader_are_metered(self):
        self.audit();self.eligibility.hook=lambda stage:setattr(self.service,'clock',lambda:self.request['budget']['deadline']);before=self.db.total_changes;result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(result['completion'],'partial');self.assertEqual(before,self.db.total_changes)
    def test_hidden_rejections_do_not_disclose_ids_or_candidate_counts(self):
        self.audit();hidden=self.request['exact_refs'][0]['id'];self.authority.verify_candidate_access=lambda *args:(_ for _ in ()).throw(Forbidden('private target'))
        result=self.recall();encoded=dumps(result);self.assertNotIn(hidden,encoded);self.assertEqual(result['coverage']['scanned'],0);self.assertEqual(result['items'],[])

    def test_large_dependency_metadata_is_not_read_past_audit_byte_limit(self):
        from digital_life.application.learning.eligibility import ToolLearningEligibility
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        principal=copy.deepcopy(self.request['principal']);large_scope=copy.deepcopy(self.scope);large_scope['limitations']=['synthetic bounded metadata '*100000];source=copy.deepcopy(self.case.case.product['body']['claims'][0]['evidence'][0]['source']);dependency={'target':source,'relation':'read','expected':{'object':source,'revision':1,'epoch':0},'consumer_purpose':principal['purpose']}
        ident=ToolLearningEligibility(self.s,MechanicalEligibility()).register_dependency('synthetic',principal,ref(self.s,self.case.representation['id']),dependency,'/large-scope-metadata',large_scope);large=self.s.row('tl_dependency',ident)['metadata_artifact_id'];read=[];original=ToolLearningStore.read_artifact
        def tracked(adapter,key,type_name=None):read.append(key);return original(adapter,key,type_name)
        self.audit();before=self.db.total_changes
        with patch.object(ToolLearningStore,'read_artifact',tracked):result=self.recall()
        self.assertEqual(result['items'],[]);self.assertEqual(result['completion'],'partial');self.assertNotIn(large,read);self.assertEqual(before,self.db.total_changes)
    def test_semantic_port_must_use_same_bounded_reader(self):
        self.audit();large=self.s.artifact('synthetic metadata '*100000,media_type='text/plain')
        def scope(*args):self.authority.reader(large);return True
        self.authority.scope_matches=scope;result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(result['completion'],'partial')
    def test_raw_legacy_slots_keep_unknown_false_zero_and_known_null_distinct(self):
        self.legacy();original=self.authority.legacy_material
        slots=[slot(False),slot(0),{'status':'known','value':None,'reason_code':'source_reported_null','reason':'reported null','basis_refs':[]},{'status':'unknown','value':None,'reason_code':'not_measured','reason':'not measured','basis_refs':[]}]
        def values(*args):material=original(*args);material['values']=copy.deepcopy(slots);return material
        self.authority.legacy_material=values;result=self.recall();actual=result['items'][0]['value_slots'];self.assertIs(type(actual[0]['value']),bool);self.assertIs(type(actual[1]['value']),int);self.assertEqual(actual[2]['status'],'known');self.assertEqual(actual[3]['status'],'unknown')
    def test_partial_input_is_not_promoted_to_actual_context_use(self):
        before={table:self.db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('tl_input_dependency','thought_requests')};self.recall()
        for table,count in before.items():self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],count)
    def test_shared_original_byte_account_is_not_reset_for_new_retrieval(self):
        from digital_life.application.learning.budget import ToolLearningBudget,BudgetAuthority,DIMENSIONS
        class B(BudgetAuthority):
            def verify_budget(self,*args):return None
            def verify_entry(self,*args):return None
            def verify_settlement(self,*args):return None
        result=self.recall();budget=ToolLearningBudget(self.s,B());work=self.case.case.obs.work['id'];remaining=budget.check_work(work)['remaining']['bytes'];artifact=self.s.artifact('x'*remaining,media_type='text/plain');amounts={k:0 for k in DIMENSIONS};amounts.update(bytes=remaining,scan=1,items=1)
        reservation=budget.reserve('synthetic',work,result['retrieval_run']['value'],'retrieval',amounts,request_budget=self.request['budget']);budget.record_entry('synthetic',work,reservation['id'],{'contract':'SYNTHETIC-READ-ENTRY-1'});actual=self.s.read_artifact(artifact);self.assertEqual(len(actual),remaining);budget.settle('synthetic',work,reservation['id'],amounts)
        account=copy.deepcopy(self.request['budget']['account_ref']);self.request['request_id']=identifier()
        with self.assertRaises(Forbidden):self.recall()
        event=self.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='tl.recall.begin' AND source_event_id=?",(self.request['request_id'],)).fetchone();new_run=self.s.read_artifact(event[0])['run'];extra={key:0 for key in DIMENSIONS};extra['bytes']=1
        with self.assertRaises(Forbidden):budget.reserve('synthetic',work,new_run,'retrieval',extra,request_budget=self.request['budget'])
        self.assertEqual(self.request['budget']['account_ref'],account);self.assertEqual(budget.check_work(work)['remaining']['bytes'],0)

    def test_unmapped_native_candidate_is_audit_only_temporary_projection(self):
        self.case.case.replace_product(lambda p:p['body'].update(rationale='unreviewed second proposal'));self.case.case.request.update(command_id=identifier(),idempotency_key=identifier());self.case.case.request['payload']['review']=slot();decision=self.case.case.decision();target=decision['content_ref']['value'];self.audit(kinds=['candidate']);self.request['exact_refs']=[target]
        def candidate(entry,request,reference,row):
            item=self.service._base(request,'candidate','unreviewed temporary projection',self.scope,self.case.case.product['body']['claims'][0]['evidence'],'user_statement','extract',[{'status':'unknown','value':None,'reason_code':'not_measured','reason':'not measured','basis_refs':[]}],['not an accepted current fact']);item.update(content_ref=slot(target),content_revision=slot({'object':target,'revision':1,'epoch':0}),decision_ref=slot(ref(self.s,decision['id'])));return item
        self.authority.legacy_material=candidate;self.authority.candidate_token=lambda entry,request,reference,row:{'object':copy.deepcopy(target),'revision':1,'epoch':0};before=self.db.total_changes;result=self.recall();self.assertEqual(len(result['items']),1);self.assertEqual(result['items'][0]['usage_state'],'candidate');self.assertEqual(result['retrieval_run']['status'],'not_applicable');self.assertEqual(self.db.total_changes,before)
        self.request.update(entry='execution',request_id=identifier());result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(result['completion'],'not_ready')
    def test_wrong_original_account_is_not_replaced_by_new_retrieval(self):
        self.request['budget']['account_ref']=ref(self.s,self.db.execute('SELECT id FROM activity_budget_accounts WHERE activity_id<>? LIMIT 1',(self.request['activity_ref']['value']['id'],)).fetchone()[0])
        with self.assertRaises(Forbidden):self.recall()

    def test_hidden_and_absent_queries_have_same_public_empty_projection(self):
        cases=[]
        try:
            for hidden in (False,True):
                case=RecallTests();case.setUp();cases.append(case);case.audit();case.request.update(exact_refs=[],query='opaque_private_needle')
                if hidden:
                    from digital_life.application.services.memory import Memory
                    private=Memory(case.s).encode('opaque_private_needle',case.case.case.obs.base.f.expected['source_evidence_id']);candidate=ref(case.s,private['revision_id'])
                else:candidate=ref(case.s,identifier(),'memory_revisions')
                case.authority.index_candidates=lambda entry,request,limit,candidate=candidate,hidden=hidden:[candidate] if hidden else []
                case.authority.verify_candidate_access=lambda *args:(_ for _ in ()).throw(Forbidden('metadata unavailable'))
            outputs=[case.recall() for case in cases]
            for output in outputs:
                output.pop('request_id');output.pop('checked_at')
            self.assertEqual(outputs[0],outputs[1])
            # The exact missing Ref path must not expose an unavailable-vs-hidden split.
            for case in cases:case.request['exact_refs']=[{'instance_id':case.s.instance_id,'id':identifier(),'kind':'tl_representation','revision':slot()}]
            a,b=[case.recall() for case in cases]
            for output in (a,b):output.pop('request_id');output.pop('checked_at')
            self.assertEqual(a,b)
        finally:
            for case in cases:case.doCleanups()
    def test_delete_only_source_relation_is_not_support_but_erase_blocks_copied_metadata(self):
        from digital_life.application.services.memory import Memory
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        from tests.test_tool_learning_invalidation import MechanicalInvalidation
        self.legacy();other=Memory(self.s).encode('managed deletion reference only',self.case.case.obs.base.f.expected['source_evidence_id']);source=ref(self.s,other['memory_id']);evidence=copy.deepcopy(self.case.case.product['body']['claims'][0]['evidence'][0]);evidence['access_dependencies']=[{'target':source,'relation':'delete','expected':{'object':source,'revision':1,'epoch':0},'consumer_purpose':'recall_episode'}];self.authority.legacy_source=evidence;first=self.recall();self.assertEqual(len(first['items']),1);self.assertTrue(any(d['relation']=='delete' for d in first['items'][0]['relations']));self.assertFalse(any(d['relation']=='delete' for d in first['items'][0]['dependencies']))
        target=self.target(first);principal=copy.deepcopy(self.request['principal']);principal['purpose']='learn';inputs=self.service.register_inputs('synthetic-recall',self.request,first,target,principal)
        def invalidate(kind,epoch):
            request=copy.deepcopy(self.case.request);request.update(command_id=identifier(),idempotency_key=identifier());request['principal'].update(module='M12',purpose='erase' if kind=='erase' else 'propagate');request['payload']={'change_id':identifier(),'kind':kind,'source':{'object':source,'revision':1,'epoch':epoch},'replacement':slot(),'affected_scope':copy.deepcopy(self.scope),'subjects':[],'purposes':['recall_episode','learn'],'expected_epoch':epoch,'evidence':[copy.deepcopy(evidence)],'erase_scope':slot(ref(self.s,self.case.case.obs.base.f.expected['policy_id'])) if kind=='erase' else slot()};ToolLearningInvalidation(self.s,MechanicalInvalidation()).apply('mechanical-im06',request)
        invalidate('revoke',0);self.assertEqual(len(self.recall()['items']),1)
        invalidate('erase',1)
        with self.assertRaises((Forbidden,Conflict)):self.recall()
        from digital_life.application.learning.eligibility import ToolLearningEligibility
        with self.assertRaises((Forbidden,Conflict)):ToolLearningEligibility(self.s,MechanicalEligibility()).callback('synthetic',principal,first['items'][0]['memory_revision']['value'],self.scope,'learn',principal['recipient'],lambda:'must not enter',request=target)
        self.assertTrue(any(self.s.row('tl_input_dependency',key)['retention_state']=='erase_pending' for key in inputs))

    def owned_slice(self,run):
        from digital_life.application.learning.budget import ToolLearningBudget,BudgetAuthority,DIMENSIONS
        class B(BudgetAuthority):
            def verify_budget(self,*args):return None
            def verify_entry(self,*args):return None
            def verify_settlement(self,*args):return None
        work=self.db.execute('SELECT id FROM tl_work WHERE learning_activity_id=?',(self.request['activity_ref']['value']['id'],)).fetchone()[0];budget=ToolLearningBudget(self.s,B());remaining=budget.check_work(work)['remaining'];amounts={key:0 for key in DIMENSIONS}
        for key in ('scan','items','bytes','elapsed_ms'):amounts[key]=remaining[key]
        reservation=budget.reserve('synthetic',work,run,'retrieval',amounts,request_budget=self.request['budget'],reservation_key=identifier());budget.record_entry('synthetic',work,reservation['id'],{'contract':'SYNTHETIC-READ-ENTRY-1'});self.authority.reservation=slot(reservation['id']);self.authority.forced_reservation=True;return budget,work,reservation
    def test_own_full_reserved_slice_is_usable_once_without_returning_other_credit(self):
        run=self.service.begin('synthetic-recall',self.request);budget,work,reservation=self.owned_slice(run);self.assertEqual(budget.check_work(work)['remaining']['bytes'],0)
        result=self.recall(begin=False);self.assertEqual(len(result['items']),1);usage=copy.deepcopy(self.authority.last_usage)
        with self.assertRaisesRegex(Conflict,'already entered once'):self.recall(begin=False)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_recall_item').fetchone()[0],1);budget.settle('synthetic',work,reservation['id'],usage)
    def test_other_run_reserved_slice_and_missing_slice_never_authorize_read(self):
        self.service.begin('synthetic-recall',self.request);other=copy.deepcopy(self.request);other['request_id']=identifier();run=self.service.begin('synthetic-recall',other);self.owned_slice(run)
        with self.assertRaisesRegex(Forbidden,'not this entered original run'):self.recall(begin=False)
        self.authority.reservation=slot()
        with self.assertRaisesRegex(Forbidden,'actual entered reservation'):self.recall(begin=False)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tl_recall_item').fetchone()[0],0)
    def test_replay_cannot_return_old_current_head_after_real_c1_c2_update(self):
        first=self.recall();self.assertEqual(len(first['items']),1);self.second_version();result=self.recall();self.assertEqual(result['items'],[]);self.assertEqual(result['completion'],'not_ready')


if __name__=='__main__':unittest.main()
