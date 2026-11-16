"""IM03 DDL exercised only in newly generated, locked synthetic databases."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from evaluation.tool_learning_fixture import SyntheticToolLearningFixture

RESOURCES = Path(__file__).resolve().parents[1] / 'digital_life' / 'resources'
UTC = '2026-11-09T00:00:00.000Z'

def uid():
    return uuid.uuid4().hex

def slot(value=None, status='known'):
    return {'status': status, 'value': value, 'reason_code': 'none' if status == 'known' else 'not_applicable', 'reason': 'synthetic'}

class RuntimeSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture = SyntheticToolLearningFixture(Path(self.tmp.name).resolve() / 'new', schema_version=3)
        self.f = self.fixture.__enter__()
        self.addCleanup(self.fixture.__exit__, None, None, None)
        self.db = self.f.store.db
        self.db.executescript((RESOURCES / 'tool_learning_v1.sql').read_text())
        self.inst = self.f.store.instance_id
        self.art = self.db.execute('SELECT id FROM artifacts LIMIT 1').fetchone()[0]
        self.activity = self.f.expected['activity_id']
        self.budget = self.db.execute('SELECT id FROM activity_budget_accounts WHERE activity_id=?',(self.activity,)).fetchone()[0]

    def insert(self, table, **values):
        values = dict(id=values.pop('id', uid()), instance_id=self.inst, **values)
        self.db.execute('INSERT INTO '+table+' ('+','.join(values)+') VALUES ('+','.join('?' for _ in values)+')', tuple(values.values()))
        return values['id']

    def work(self, **overrides):
        v = dict(learning_activity_id=self.activity, source_activity_id=self.activity, source_artifact_id=self.art, purpose='learn', processing_identity='a'*64, state='admitted', phase='admit', review_round=0, conditions_artifact_id=self.art, control_artifact_id=self.art, method_artifact_id=self.art, deadline=UTC, budget_account_id=self.budget, row_revision=0)
        v.update(overrides)
        return self.insert('tl_work', **v)

    def product(self, work, kind='UpdateProposal', **overrides):
        v = dict(work_id=work, product_type=kind, payload_artifact_id=self.art, processing_identity='b'*64, source_fingerprint='c'*64)
        v.update(overrides)
        return self.insert('tl_product', **v)

    def c1(self, reverse=False):
        w=self.work(); p=self.product(w); c=uid(); r=uid(); d=uid()
        self.insert('tl_content',id=c,content_kind='source_report',head_revision_id=r,row_revision=0)
        decision=dict(id=d,work_id=w,proposal_id=p,review_round=0,decision_artifact_id=self.art,operation='accept',content_revision_id=r,policy_ref_id=self.f.expected['policy_id'],created_at=UTC)
        revision=dict(id=r,content_id=c,revision_no=1,decision_id=d,product_id=p,payload_artifact_id=self.art,status='accepted')
        first,second=(('tl_content_revision',revision),('tl_decision',decision)) if reverse else (('tl_decision',decision),('tl_content_revision',revision))
        self.insert(first[0],**first[1]);self.insert(second[0],**second[1])
        return w,p,c,r,d

    def c2(self, c,r,d, reverse=False):
        h,p=uid(),uid()
        head=dict(id=h,content_id=c,format_version='TL-TEXT-1',representation_id=p,expected_content_revision_id=r,row_revision=0)
        rep=dict(id=p,series_id=h,content_revision_id=r,decision_id=d,format_version='TL-TEXT-1',representation_no=1,payload_artifact_id=self.art,body_artifact_id=self.art,body_digest='d'*64,state='ready')
        pairs=[('tl_representation_head',head),('tl_representation',rep)]
        if reverse:pairs.reverse()
        for table,vals in pairs:self.insert(table,**vals)
        return h,p

    def test_nineteen_tables_and_unchanged_real_schema3(self):
        names=self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'tl_*'").fetchall()
        self.assertEqual(len(names),19)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],3)
        self.assertEqual(self.f.control.state()['user_stopped'],1)
        self.assertTrue((self.f.root/'WAKE_DISABLED').is_file())

    def test_c1_c2_forward_deferred_cycles_and_separate_version_registry(self):
        with self.f.store.tx():
            _,_,c,r,d=self.c1();h,p=self.c2(c,r,d)
        rows=self.db.execute('SELECT id,object_id,revision_no FROM object_revision_registry WHERE id IN (?,?)',(r,p)).fetchall()
        self.assertEqual({tuple(x) for x in rows},{(r,c,1),(p,h,1)})
        self.assertEqual(self.f.store.integrity()['foreign_keys'],[])

    def test_c1_c2_reverse_order(self):
        with self.f.store.tx():
            _,_,c,r,d=self.c1(True);self.c2(c,r,d,True)
        self.assertEqual(self.f.store.integrity()['foreign_keys'],[])

    def test_unresolved_cycle_fails_commit(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.insert('tl_content',content_kind='world_claim',head_revision_id=uid(),row_revision=0)

    def test_wrong_head_owner_fails_deferred_fk(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():
                _,_,c,r,d=self.c1()
                self.insert('tl_content',content_kind='world_claim',head_revision_id=r,row_revision=0)

    def test_proposal_type_must_match_even_reverse_order(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():
                w=self.work();p=self.product(w,'ObservationExtract')
                self.insert('tl_decision',work_id=w,proposal_id=p,review_round=0,decision_artifact_id=self.art,operation='reject',policy_ref_id=self.f.expected['policy_id'],created_at=UTC)

    def test_duplicate_revision_and_series_number_rejected(self):
        with self.f.store.tx():
            _,p,c,r,d=self.c1();h,rep=self.c2(c,r,d)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.insert('tl_representation',series_id=h,content_revision_id=r,decision_id=d,format_version='TL-TEXT-1',representation_no=1,payload_artifact_id=self.art,body_artifact_id=self.art,body_digest='d'*64,state='ready')

    def test_cas_revision_and_terminal_transition(self):
        with self.f.store.tx():w=self.work()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.db.execute("UPDATE tl_work SET state='processing' WHERE id=?",(w,))
        with self.f.store.tx():self.db.execute("UPDATE tl_work SET state='processing',row_revision=1 WHERE id=?",(w,))
        with self.f.store.tx():self.db.execute("UPDATE tl_work SET state='completed',phase='complete',row_revision=2 WHERE id=?",(w,))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.db.execute("UPDATE tl_work SET state='processing',row_revision=3 WHERE id=?",(w,))

    def test_immutable_payload_and_registry_survive(self):
        with self.f.store.tx():w=self.work();p=self.product(w)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.db.execute("UPDATE tl_product SET source_fingerprint=? WHERE id=?",('e'*64,p))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.db.execute('DELETE FROM object_registry WHERE id=?',(p,))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.db.execute('DELETE FROM tl_product WHERE id=?',(p,))

    def test_invalid_id_hash_enum_and_timestamp(self):
        for overrides in [dict(id='bad'),dict(processing_identity='g'*64),dict(purpose='invented'),dict(recorded_at='xxxxxxxxxxxxxxxxxxxxxxxx')]:
            with self.subTest(overrides=overrides),self.assertRaises(sqlite3.IntegrityError):
                with self.f.store.tx():self.work(**overrides)

    def test_wrong_revision_owner_late_registry_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():
                rid=uid();other=uid()
                self.insert('tl_dependency',consumer_ref_id=self.activity,source_ref_id=self.activity,source_revision_id=rid,relation='read',purpose='learn',expected_epoch=0,field_path='/x',metadata_artifact_id=self.art)
                self.db.execute('INSERT INTO object_registry(id,instance_id,kind) VALUES(?,?,?)',(other,self.inst,'synthetic'))
                self.db.execute('INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind) VALUES(?,?,?,?,?)',(rid,self.inst,other,1,'synthetic'))

    def test_representation_state_only_mutable(self):
        with self.f.store.tx():_,_,c,r,d=self.c1();h,p=self.c2(c,r,d)
        with self.f.store.tx():self.db.execute("UPDATE tl_representation SET state='superseded' WHERE id=?",(p,))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.db.execute("UPDATE tl_representation SET state='ready' WHERE id=?",(p,))

    def test_input_erased_cannot_keep_digest(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.insert('tl_input_dependency',request_ref_id=self.activity,source_ref_id=self.activity,source_epoch=0,field_path='/x',purpose='learn',recipient_ref_id=self.activity,body_digest='a'*64,retention_state='erased',row_revision=0)

    def test_representation_then_candidate_revision_rejected_before_head_exists(self):
        with self.assertRaisesRegex(sqlite3.IntegrityError,'revision'):
            with self.f.store.tx():
                w=self.work();p=self.product(w);c,r,d,h=uid(),uid(),uid(),uid()
                self.insert('tl_content',id=c,content_kind='source_report',head_revision_id=r,row_revision=0)
                self.insert('tl_decision',id=d,work_id=w,proposal_id=p,review_round=0,decision_artifact_id=self.art,operation='candidate',content_revision_id=r,policy_ref_id=self.f.expected['policy_id'],created_at=UTC)
                self.insert('tl_representation',series_id=h,content_revision_id=r,decision_id=d,format_version='TL-TEXT-1',representation_no=1,payload_artifact_id=self.art,body_artifact_id=self.art,body_digest='d'*64,state='ready')
                self.insert('tl_content_revision',id=r,content_id=c,revision_no=1,decision_id=d,product_id=p,payload_artifact_id=self.art,status='candidate')

    def test_accept_cannot_claim_another_decisions_old_revision(self):
        with self.f.store.tx():w,p,c,r,d=self.c1()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.insert('tl_decision',work_id=w,proposal_id=p,review_round=1,decision_artifact_id=self.art,operation='accept',content_revision_id=r,policy_ref_id=self.f.expected['policy_id'],created_at=UTC)
        with self.f.store.tx():self.insert('tl_decision',work_id=w,proposal_id=p,review_round=1,decision_artifact_id=self.art,operation='reuse',content_revision_id=r,policy_ref_id=self.f.expected['policy_id'],created_at=UTC)

    def test_old_cleaning_without_explicit_target_cannot_purge_or_rewrite(self):
        with self.f.store.tx():
            w=self.work();p=self.product(w)
            request=self.f.store.insert('deletion_requests',subject_scope='{}',requested_at=UTC,authority_ref=self.f.expected['controller'],state='cleaning')
            self.f.store.insert('deletion_effects',request_id=request,object_ref=p,operation='purge',result='pending')
        for statement,args in [('DELETE FROM tl_product WHERE id=?',(p,)),('UPDATE tl_product SET payload_artifact_id=? WHERE id=?',(self.art,p))]:
            with self.assertRaises(sqlite3.IntegrityError):
                with self.f.store.tx():self.db.execute(statement,args)

    def test_exact_enumerated_erase_plan_allows_only_its_target_purge(self):
        with self.f.store.tx():
            w=self.work();p=self.product(w)
            request=self.f.store.insert('deletion_requests',subject_scope='{}',requested_at=UTC,authority_ref=self.f.expected['controller'],state='cleaning')
            self.f.store.insert('deletion_effects',request_id=request,object_ref=p,operation='purge',result='pending')
            change=self.insert('tl_change',change_key='erase-one',fingerprint='a'*64,payload_artifact_id=self.art,kind='erase',source_ref_id=p,expected_epoch=0,result_epoch=1)
            barrier=self.insert('tl_barrier',change_id=change,source_ref_id=p,source_epoch=1,kind='erase',scope_artifact_id=self.art,authorization_ref_id=request,state='active',row_revision=0)
            self.insert('tl_erasure_target',barrier_id=barrier,plan_ref_id=request,target_ref_id=p,location_kind='database',state='pending',row_revision=0)
        with self.f.store.tx():self.db.execute('DELETE FROM tl_product WHERE id=?',(p,))
        self.assertIsNone(self.db.execute('SELECT id FROM tl_product WHERE id=?',(p,)).fetchone())
        # The registry tombstone persists while referenced; the erased row and payload are distinct.
        self.assertIsNotNone(self.db.execute('SELECT id FROM object_registry WHERE id=?',(p,)).fetchone())

    def test_handoff_lease_and_published_completeness(self):
        with self.f.store.tx():w,_,c,r,d=self.c1()
        base=dict(work_id=w,content_revision_id=r,decision_id=d,format_version='TL-TEXT-1',input_fingerprint='e'*64,state='pending',lease_generation=0,attempts=0,deadline=UTC,budget_account_id=self.budget,row_revision=0)
        for override in [dict(state='leased'),dict(lease_worker_id=self.activity),dict(state='published')]:
            with self.assertRaises(sqlite3.IntegrityError):
                with self.f.store.tx():self.insert('tl_handoff',**(base|override))
        with self.f.store.tx():self.insert('tl_handoff',**base)

    def test_effect_assessment_type_and_measurement(self):
        with self.f.store.tx():w=self.work();p=self.product(w)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.insert('tl_effect',work_id=w,product_id=p,metric_contract='TL-EVAL-0.1',state='not_measured',payload_artifact_id=self.art)
        with self.f.store.tx():effect=self.product(w,'EffectAssessment')
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.insert('tl_effect',work_id=w,product_id=effect,metric_contract='TL-EVAL-0.1',state='measured',payload_artifact_id=self.art)

    def test_effect_state_changes_preserve_original_report_and_cannot_restore_invalidated(self):
        with self.f.store.tx():
            w=self.work();p=self.product(w,'EffectAssessment')
            effect=self.insert('tl_effect',work_id=w,product_id=p,measurement_ref_id=self.activity,metric_contract='TL-EVAL-0.1',state='measured',payload_artifact_id=self.art)
        with self.f.store.tx():self.db.execute("UPDATE tl_effect SET state='invalidated' WHERE id=?",(effect,))
        self.assertEqual(self.db.execute('SELECT payload_artifact_id FROM tl_effect WHERE id=?',(effect,)).fetchone()[0],self.art)
        for statement,args in [("UPDATE tl_effect SET state='measured' WHERE id=?",(effect,)),('UPDATE tl_effect SET measurement_ref_id=? WHERE id=?',(self.f.expected['policy_id'],effect))]:
            with self.assertRaises(sqlite3.IntegrityError):
                with self.f.store.tx():self.db.execute(statement,args)

    def test_wrong_learning_activity_budget(self):
        from digital_life.application.runtime.engine import Engine
        with self.f.store.tx():other=Engine(self.f.store).submit('synthetic second activity','second','fixture')
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.work(learning_activity_id=other)

    def test_unrecognized_command_and_invalid_deadline(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.insert('tl_command',operation='unknown',idempotency_key='key',fingerprint='a'*64,principal_artifact_id=self.art,state='pending',row_revision=0)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.f.store.tx():self.work(deadline='xxxxxxxxxxxxxxxxxxxxxxxx')


class EvaluationSchemaTests(unittest.TestCase):
    def setUp(self):
        # Separate in-memory database: no production tables, files, credentials or network.
        self.db=sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript((RESOURCES/'tool_learning_evaluation_v1.sql').read_text())
        self.seed_run()

    def put(self,table,**v):
        v=dict(contract='TL-EVAL-0.1',schema_revision=1,id=v.pop('id',uid()),run_id=v.pop('run_id','run'),created_at=UTC,**v)
        v={k:json.dumps(x,separators=(',',':')) if isinstance(x,(dict,list)) else x for k,x in v.items()}
        self.db.execute('INSERT INTO tle_'+table+' ('+','.join(v)+') VALUES ('+','.join('?' for _ in v)+')',tuple(v.values()))
        return v['id']

    def seed_run(self):
        ref={'id':'material','kind':'artifact','instance_id':'eval','revision':slot(None,'not_applicable')}
        v={x:slot(None,'not_applicable') for x in 'model_ref route materials_manifest review_roster price_evidence currency money_limit account_limits mechanism_manifest'.split()}
        v.update(protocol_ref=ref,code_digest={'algorithm':'sha256','hex':'a'*64},configuration_ref=ref,prompt_refs=[],arm_seed=20261109,analysis_seed=20261108,bootstrap_samples=10000,concurrency_limit=4,deadline=UTC,state='blocked_before_start',budget_ref=ref)
        return self.put('run',id='run',**v)

    def case(self,id='case',partition='TARGET',cluster='cluster'):
        return self.put('case',id=id,partition=partition,category='synthetic',source_cluster_id=cluster,template_family=slot(None,'not_applicable'),learning_input_ref={},truth_ref={},base_snapshot_ref={})

    def trial(self,id='trial',**overrides):
        v=dict(logical_trial_id=id,case_id='case',arm='E',repeat=1,occurrence='original',replacement_of=slot(None,'not_applicable'),snapshot_ref={},instance_ref={},phase='registered',status='registered',assigned_order=0,outcome_ref=slot(None,'not_applicable'),budget_ref={});v.update(overrides)
        return self.put('trial',id=id,**v)

    def test_ten_tables_and_independent_foreign_keys(self):
        self.assertEqual(self.db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0],10)
        self.case();self.trial();self.db.commit()
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_partition_leakage(self):
        self.case()
        with self.assertRaises(sqlite3.IntegrityError):self.case('dev','DEV')

    def test_query_partition_and_unique(self):
        self.case(partition='RETENTION')
        with self.assertRaises(sqlite3.IntegrityError):self.put('query',case_id='case',query_kind='boundary',input_ref={},truth_ref={},k=5)
        self.put('query',case_id='case',query_kind='retention',input_ref={},truth_ref={},k=5)
        with self.assertRaises(sqlite3.IntegrityError):self.put('query',case_id='case',query_kind='retention',input_ref={},truth_ref={},k=5)

    def test_formal_no_o_and_dev_one_repeat(self):
        self.case()
        with self.assertRaises(sqlite3.IntegrityError):self.trial(arm='O')
        self.case('dev','DEV','different')
        with self.assertRaises(sqlite3.IntegrityError):self.trial('devtrial',case_id='dev',repeat=2)

    def test_one_matching_replacement(self):
        self.case();self.trial()
        self.trial('replacement',logical_trial_id='trial',occurrence='replacement',replacement_of=slot({'id':'trial'}))
        with self.assertRaises(sqlite3.IntegrityError):self.trial('replacement2',logical_trial_id='trial',occurrence='replacement',replacement_of=slot({'id':'trial'}))

    def test_run_cannot_unstart_and_parameters_freeze(self):
        self.db.execute("UPDATE tle_run SET state='registered'")
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE tle_run SET code_digest='{}'")
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE tle_run SET state='blocked_before_start'")

    def test_attempt_limits_and_no_update_bypass(self):
        self.case();self.trial()
        vals=dict(trial_id='trial',logical_trial_id='trial',phase='learn',query_id=slot(None,'not_applicable'),request_ref={},reservation_ref={},actual_callback_entry=slot(None,'not_applicable'),receipt_ref=slot(None,'not_applicable'),outcome='prepared',usage_ref=slot(None,'not_applicable'))
        for _ in range(3):self.put('attempt',**vals)
        with self.assertRaises(sqlite3.IntegrityError):self.put('attempt',**vals)
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE tle_attempt SET phase='query',query_id=?",(json.dumps(slot('q')),))

    def test_case_partition_immutable(self):
        self.case()
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("UPDATE tle_case SET partition='DEV'")

    def test_label_requires_distinct_people_ids(self):
        self.case();self.put('query',id='q',case_id='case',query_kind='boundary',input_ref={},truth_ref={},k=5)
        with self.assertRaises(sqlite3.IntegrityError):self.put('label',query_id='q',claim_id='c',support='unknown',expected_scope={},expected_slots=[],relevant_refs=[],expected_terminal='blocked',major_error=0,rationale='synthetic',evidence_refs=[],author_id='same',reviewer_id='same')

if __name__=='__main__':unittest.main()
