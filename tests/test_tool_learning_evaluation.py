"""Disposable evaluation records/ACL/budget/runner tests, no models or instances."""
import copy
import json
import sqlite3
import threading
import unittest
from digital_life.domain.contracts import ContractError
from evaluation.tool_learning_records import FIELDS,validate_record,loads
from evaluation.tool_learning_store import EvaluationWorkspace
from evaluation.tool_learning_runner import BudgetLedger,DeterministicFixture,DeterministicRunner,check_launch_conditions

NOW='2026-11-09T00:00:00.000Z';LATER='2026-11-10T00:00:00.000Z';RUN='run1'
def sl(value=None,status='not_applicable'):
 return {'status':status,'value':value,'reason_code':'none' if status=='known' else 'not_requested','reason':'' if status=='known' else 'not requested in fixture','basis_refs':[]}
def ref(ident='artifact',kind='artifact'):return {'instance_id':RUN,'id':ident,'kind':kind,'revision':sl()}
def coverage():return {'state':'complete','domain':sl('fixture','known'),'scanned':1,'limit':1,'truncated':False,'missing':[]}
def method():return {'name':'deterministic','version':'1','request_ref':sl(),'model_config_ref':sl()}
def scope():return {'subject':sl(),'subject_label':sl('synthetic','known'),'property':'count','claim_target':'source_report','temporal':{'kind':'observation','start':sl(NOW,'known'),'end':sl(NOW,'known'),'bounds':'point'},'conditions':sl({},'known'),'domain':sl('fixture','known'),'unit':sl('items','known'),'granularity':sl(),'coverage':coverage(),'exceptions':[],'limitations':[]}
def record(name,**changes):
 v={'contract':'TL-EVAL-0.1','schema_revision':1,'id':name.lower(),'run_id':RUN,'created_at':NOW}
 fields={
 'Run':dict(id=RUN,protocol_ref=ref(),code_digest={'algorithm':'sha256','hex':'b'*64},configuration_ref=ref(),prompt_refs=[ref()],model_ref=sl(),route=sl(),materials_manifest=sl(),review_roster=sl(),price_evidence=sl(),currency=sl(),money_limit=sl(),account_limits=sl(),mechanism_manifest=sl(),arm_seed=20261109,analysis_seed=20261108,bootstrap_samples=10000,concurrency_limit=4,deadline=LATER,state='blocked_before_start',budget_ref=ref()),
 'Case':dict(partition='DEV',category='direct_report',source_cluster_id='cluster1',template_family=sl('family1','known'),learning_input_ref=ref(),truth_ref=ref('truth'),base_snapshot_ref=ref()),
 'Query':dict(case_id='case',query_kind='new_question',input_ref=ref(),truth_ref=ref('truth'),k=5),
 'Trial':dict(logical_trial_id='trial',case_id='case',arm='E',repeat=1,occurrence='original',replacement_of=sl(),snapshot_ref=ref(),instance_ref=ref(),phase='registered',status='registered',assigned_order=0,outcome_ref=sl(),budget_ref=ref()),
 'Attempt':dict(trial_id='trial',logical_trial_id='trial',phase='learn',query_id=sl(),request_ref=ref(),reservation_ref=ref(),actual_callback_entry=sl(),receipt_ref=sl(),outcome='prepared',usage_ref=sl()),
 'Label':dict(query_id='query',claim_id='claim1',support='supported',expected_scope=scope(),expected_slots=[sl({'status':'source_report'},'known')],relevant_refs=[ref()],expected_terminal='accepted_scoped_report',major_error=False,rationale='synthetic source scope only',evidence_refs=[],author_id='author1',reviewer_id='reviewer1'),
 'Review':dict(blind_item_id='blind1',reviewer_id='reviewer1',label_ref=ref('label','Label'),original_rating='pass',reason='source and scope retained',locator={'kind':'whole_artifact','justification':'synthetic review item'},resolution_ref=sl(),unblinding_risk=sl()),
 'Fault':dict(mechanism_case_id='mechcase',decision_refs=['Q07-A04'],metric_ids=['TL12'],fixture_ref=ref(),injection_stage='C1-handoff',planned_order_ref=ref(),actual_trace_ref=sl(),expected_terminal='atomic_rollback',actual_terminal=sl(),status='planned'),
 'Usage':dict(logical_trial_id='trial',attempt_ref=sl(ref('attempt','Attempt'),'known'),reservation_ref=ref(),input_tokens=sl(0,'known'),output_tokens=sl(0,'known'),tool_calls=sl(0,'known'),elapsed_ms=sl(1,'known'),currency_amount=sl(),evidence_refs=[ref()]),
 'Metric':dict(metric_id='TL01',metric_version='TL-EVAL-0.1',partition='DEV',arm='E',case_id=sl('case','known'),trial_id=sl('trial','known'),level='query',numerator=sl(1,'known'),denominator=sl(1,'known'),samples_ref=sl(),unit='fraction',coverage=coverage(),method=method(),source_refs=[ref()],status='measured',interval=sl(),judgment='exploratory',scope=scope()),
 }
 v.update(fields[name]);v.update(changes);return v


class RecordTests(unittest.TestCase):
 def test_ten_precise_records_roundtrip_unchanged(self):
  for name in FIELDS:
   v=record(name);before=copy.deepcopy(v);self.assertIs(validate_record(name,v),v);self.assertEqual(v,before);self.assertEqual(loads(json.dumps(v),name),v)
 def test_each_record_missing_extra_wrong_common(self):
  for name in FIELDS:
   for mutation in ('missing','extra','boolrevision'):
    v=record(name)
    if mutation=='missing':del v[FIELDS[name].split()[0]]
    elif mutation=='extra':v['unregistered']=True
    else:v['schema_revision']=True
    with self.assertRaises(ContractError):validate_record(name,v)
 def test_evalid_ascii_and_cross_run_ref(self):
  for changes in ({'id':'中文'},{'id':'a'*129},{'protocol_ref':{**ref(),'instance_id':'different'}}):
   with self.assertRaises(ContractError):validate_record('Run',record('Run',**changes))
 def test_actual_entry_not_sent_ledger(self):
  for change in ({'outcome':'in_flight'},{'outcome':'received','receipt_ref':sl(ref(),'known')},{'sent':NOW},{'actual_callback_entry':sl(NOW,'known')}):
   with self.assertRaises(ContractError):validate_record('Attempt',record('Attempt',**change))
 def test_original_logical_identity_and_replacement(self):
  with self.assertRaises(ContractError):validate_record('Trial',record('Trial',logical_trial_id='newbudget'))
  with self.assertRaises(ContractError):validate_record('Trial',record('Trial',occurrence='replacement'))
 def test_missing_and_zero_metrics_cannot_pass(self):
  for change in ({'numerator':sl(0,'known'),'denominator':sl(0,'known'),'judgment':'pass'},{'status':'missing','judgment':'pass'},{'numerator':sl(2,'known')},{'numerator':sl()}):
   with self.assertRaises(ContractError):validate_record('Metric',record('Metric',**change))
 def test_intervals_exact_bootstrap(self):
  interval={'method':'paired_case_bootstrap','confidence':0.95,'lower':-.2,'upper':.3,'resamples':sl(10000,'known'),'seed':sl(20261108,'known')}
  validate_record('Metric',record('Metric',interval=sl(interval,'known')))
  interval['seed']=sl(123,'known')
  with self.assertRaises(ContractError):validate_record('Metric',record('Metric',interval=sl(interval,'known')))
 def test_negative_usage_bool_and_unrun_fault(self):
  with self.assertRaises(ContractError):validate_record('Usage',record('Usage',currency_amount=sl(-1,'known')))
  with self.assertRaises(ContractError):validate_record('Usage',record('Usage',tool_calls=sl(True,'known')))
  with self.assertRaises(ContractError):validate_record('Fault',record('Fault',actual_trace_ref=sl(ref(),'known')))
 def test_json_duplicate_nonfinite_surrogate(self):
  for raw in ('{"a":1,"a":2}','{"a":NaN}','{"a":"\\ud800"}'):
   with self.assertRaises(ContractError):loads(raw,'Run')


class StoreTests(unittest.TestCase):
 def setUp(self):
  self.w=EvaluationWorkspace.create();self.s=self.w.session('controller')
  self.s.register_artifact(RUN,'artifact','artifact','learning',{'text':'synthetic source'})
  self.s.register_artifact(RUN,'truth','artifact','controller-truth',{'answer':'not model visible'})
  self.s.put('Run',record('Run'));self.s.put('Case',record('Case'));self.s.put('Case',record('Case',id='mechcase',partition='MECH',source_cluster_id='mechcluster'));self.s.put('Query',record('Query'));self.s.put('Trial',record('Trial'));self.s.put('Attempt',record('Attempt'))
 def tearDown(self):self.w.close()
 def test_all_ten_records_persist_in_independent_domains(self):
  self.s.register_identity('author1','author','author_group');self.s.register_identity('reviewer1','reviewer','review_group')
  for name in ('Label','Review','Fault','Usage','Metric'):
   self.s.put(name,record(name));self.assertEqual(self.s.get(name,RUN,name.lower()),record(name))
  self.assertEqual(self.w.metadata.execute("SELECT COUNT(*) FROM tle_label").fetchone()[0],1)
  self.assertIs(self.w.metadata,self.w.truth)
  self.assertEqual(self.w.metadata.execute("SELECT type FROM sqlite_master WHERE name='records'").fetchone()[0],'view')
  self.assertEqual(self.w.truth.execute("SELECT COUNT(*) FROM records WHERE type='Label'").fetchone()[0],1)
 def test_actor_only_explicit_input_projection(self):
  actor=self.w.session('actor');self.assertEqual(actor.artifact(ref())['text'],'synthetic source')
  with self.assertRaises(ContractError):actor.artifact(ref('truth'))
  with self.assertRaises(ContractError):actor.get('Trial',RUN,'trial')
 def test_reviewer_cannot_see_arm_or_unblinded_truth(self):
  reviewer=self.w.session('reviewer')
  for action in (lambda:reviewer.get('Trial',RUN,'trial'),lambda:reviewer.artifact(ref('truth')),lambda:reviewer.put('Metric',record('Metric'))):
   with self.assertRaises(ContractError):action()
 def test_evaluator_cannot_write_truth_artifact(self):
  with self.assertRaises(ContractError):self.w.session('evaluator').register_artifact(RUN,'secret','artifact','controller-truth',{})
 def test_unregistered_and_orphan_relationships_rejected(self):
  for name,v in [('Case',record('Case',id='other',learning_input_ref=ref('absent'))),('Query',record('Query',id='orphan',case_id='absent')),('Usage',record('Usage',id='orphan',logical_trial_id='absent',attempt_ref=sl())),('Metric',record('Metric',id='orphan',case_id=sl('absent','known'))),('Fault',record('Fault',mechanism_case_id='absent'))]:
   with self.assertRaises(ContractError):self.s.put(name,v)
 def test_source_cluster_cannot_cross_dev_target(self):
  with self.assertRaises(ContractError):self.s.put('Case',record('Case',id='formal',partition='TARGET'))
 def test_occurrence_unique_and_shared_budget(self):
  with self.assertRaises((ContractError,sqlite3.IntegrityError)):self.s.put('Trial',record('Trial',id='duplicate',logical_trial_id='duplicate'))
  with self.assertRaises(ContractError):self.s.put('Trial',record('Trial',id='replacement',occurrence='replacement',replacement_of=sl(ref('trial','Trial'),'known')))
 def test_replacement_exactly_once_with_independent_fault(self):
  self.s.transition('Trial',RUN,'trial',{'status':'infrastructure_invalid'})
  self.s.put('Fault',record('Fault',status='completed',actual_trace_ref=sl(ref(),'known'),actual_terminal=sl('infrastructure_invalid','known')))
  self.s.register_identity('assessor','independent_evaluator','external_group')
  self.s.authorize_replacement(RUN,'trial','fault','assessor')
  v=record('Trial',id='replacement',occurrence='replacement',replacement_of=sl(ref('trial','Trial'),'known'))
  self.s.put('Trial',v)
  v['id']='replacement2'
  with self.assertRaises((ContractError,sqlite3.IntegrityError)):self.s.put('Trial',v)
 def test_replacement_cannot_change_allocation_budget(self):
  self.s.transition('Trial',RUN,'trial',{'status':'infrastructure_invalid'})
  v=record('Trial',id='replacement',occurrence='replacement',replacement_of=sl(ref('trial','Trial'),'known'),budget_ref=ref('truth'))
  with self.assertRaises(ContractError):self.s.put('Trial',v)
 def test_lifecycle_preserves_history_and_frozen_configuration(self):
  self.s.transition('Attempt',RUN,'attempt',{'outcome':'in_flight','actual_callback_entry':sl(NOW,'known')})
  self.s.transition('Attempt',RUN,'attempt',{'outcome':'received','receipt_ref':sl(ref(),'known')})
  self.assertEqual(self.w.metadata.execute("SELECT COUNT(*) FROM lifecycle_history WHERE id='attempt'").fetchone()[0],2)
  with self.assertRaises(ContractError):self.s.transition('Run',RUN,RUN,{'arm_seed':0})
  with self.assertRaises(ContractError):self.s.transition('Run',RUN,RUN,{'state':'formal'})
  self.s.transition('Run',RUN,RUN,{'state':'mechanism'},deterministic_only=True)
 def test_no_usage_double_count_by_new_id(self):
  self.s.put('Usage',record('Usage'))
  with self.assertRaises(ContractError):self.s.put('Usage',record('Usage',id='usage-copy'))
 def test_same_identity_role_not_independence(self):
  self.s.register_identity('author1','author','same_group');self.s.register_identity('reviewer1','reviewer','same_group')
  with self.assertRaises(ContractError):self.s.put('Label',record('Label'))
 def test_admission_incomplete_remains_blocked(self):
  self.assertEqual(self.s.validate_admission(RUN,'TARGET')['state'],'blocked_before_start')
 def test_temp_permissions_and_cleanup(self):
  self.assertEqual(self.w.root.stat().st_mode&0o777,0o700)
  self.assertEqual((self.w.root/'controller-truth'/'evaluation.sqlite').stat().st_mode&0o777,0o600)


class BudgetRunnerTests(unittest.TestCase):
 def setUp(self):
  self.w=EvaluationWorkspace.create();self.b=BudgetLedger(self.w)
  self.b.account('run','run',dict(attempts=6,tokens=196608,tools=4))
  self.b.account('batch','batch',dict(attempts=6,tokens=196608,tools=4),'run')
  self.b.account('trial','trial',dict(attempts=6,tokens=196608,tools=4),'batch')
 def tearDown(self):self.b.close();self.w.close()
 def reserve(self,ident,**kw):return self.b.reserve(ident,'trial','batch','run',**kw)
 def test_three_levels_atomically_charge_and_rollback(self):
  self.reserve('a');before=self.b.balances('run')
  with self.assertRaises(ContractError):self.b.reserve('b','trial','wrongbatch','run')
  self.assertEqual(self.b.balances('run'),before)
  self.assertEqual(self.b.balances('trial')['charged_or_reserved'],self.b.balances('run')['charged_or_reserved'])
 def test_learning_three_limit_and_query_model_once(self):
  for i in range(3):self.reserve('l'+str(i))
  with self.assertRaises(ContractError):self.reserve('four')
  self.reserve('q',phase='query',query_id='q1')
  with self.assertRaises(sqlite3.IntegrityError):self.reserve('qagain',phase='query',query_id='q1')
 def test_tool_same_query_does_not_block_model_or_second_tool(self):
  self.reserve('tool1',phase='query',query_id='q1',transport='tool')
  self.reserve('tool2',phase='query',query_id='q1',transport='tool')
  self.reserve('model',phase='query',query_id='q1')
 def test_callback_entrance_required_actual_and_unknown_blocks(self):
  self.reserve('prepared')
  with self.assertRaises(ContractError):self.b.settle('prepared',{'attempts':1,'tokens':1,'tools':0})
  self.b.enter('prepared');self.b.settle('prepared',None)
  self.assertEqual(self.b.state()['reason'],'usage_unknown')
  with self.assertRaises(ContractError):self.reserve('next')
 def test_not_dispatched_known_zero_release(self):
  self.reserve('prepared');self.b.settle('prepared',dict(attempts=0,tokens=0,tools=0))
  self.assertEqual(self.b.balances('trial')['charged_or_reserved'],dict(attempts=0,tokens=0,tools=0))
 def test_distinct_connections_compete_on_last_available_budget(self):
  # Separate SQLite connections/locks, so RLock cannot make this assertion pass.
  other=BudgetLedger(self.w)
  self.b.db.execute('UPDATE accounts SET attempts=1 WHERE id=\'run\'')
  barrier=threading.Barrier(2);out=[]
  def reserve(ledger,key):
   barrier.wait()
   try:ledger.reserve(key,'trial','batch','run');out.append('reserved')
   except ContractError:out.append('blocked')
  threads=[threading.Thread(target=reserve,args=(b,key)) for b,key in ((self.b,'a'),(other,'b'))]
  for th in threads:th.start()
  for th in threads:th.join()
  other.close();self.assertCountEqual(out,['reserved','blocked']);self.assertEqual(self.b.balances('run')['charged_or_reserved']['attempts'],1)
 def test_ledger_format_tamper_not_reopened(self):
  self.b.db.execute('UPDATE ledger_format SET revision=9')
  with self.assertRaises(ContractError):BudgetLedger(self.w)
 def test_deterministic_runner_preserves_actual_entry_and_opportunity(self):
  runner=DeterministicRunner(self.b);fixture=DeterministicFixture('f',lambda:dict(passed=True,output_tokens=2,evidence={'assertion':'observed'}),'test-only',input_tokens=3)
  out=runner.run(fixture,'a','trial','batch','run')
  self.assertEqual(out['observation']['value'],True);self.assertFalse(out['real_model_called']);self.assertEqual([x['kind'] for x in runner.events],['prepared','actual_callback_entry','actual_callback_exit'])
  self.assertEqual(self.b.balances('run')['charged_or_reserved']['tokens'],5)
  self.assertEqual(runner.run(fixture,'a','trial','batch','run'),out)
  with self.assertRaises(ContractError):runner.run(fixture,'a','trial','batch','run',phase='query',query_id='q')
 def test_failed_opportunity_retained_and_stops_all_new_dispatch(self):
  runner=DeterministicRunner(self.b);fixture=DeterministicFixture('f',lambda:dict(passed=False,output_tokens=0,evidence={'violation':'observed'}),'test-only')
  self.assertFalse(runner.run(fixture,'a','trial','batch','run')['observation']['value'])
  with self.assertRaises(ContractError):runner.run(fixture,'b','trial','batch','run')
 def test_callback_exception_unknown_not_zero(self):
  def fail():raise RuntimeError('synthetic provider failure')
  runner=DeterministicRunner(self.b)
  with self.assertRaises(RuntimeError):runner.run(DeterministicFixture('f',fail,'test-only'),'a','trial','batch','run')
  self.assertEqual(self.b.state()['reason'],'usage_unknown');self.assertTrue(runner.events[-1]['actual_callback_entry'])
 def test_input_cap_checked_before_callback(self):
  with self.assertRaises(ContractError):DeterministicFixture('f',lambda:None,'test-only',input_tokens=24001)
 def test_no_real_launch_even_when_self_reported_conditions_supplied(self):
  for partition in ('DEV','TARGET','RETENTION'):
   out=check_launch_conditions(partition,{})
   self.assertEqual(out['state'],'blocked_before_start');self.assertTrue(out['missing']);self.assertFalse(out['transport_available'])

class ExactDDLAndEvidenceTests(unittest.TestCase):
 def test_actual_authority_is_im03_ten_exact_tables(self):
  from evaluation.tool_learning_records import COMMON
  with EvaluationWorkspace.create() as workspace:
   for name,fields in FIELDS.items():
    cols={r['name'] for r in workspace.metadata.execute('PRAGMA table_info(tle_'+name.lower()+')')}
    self.assertEqual(cols,set(COMMON)|set(fields.split()))
   with self.assertRaises(sqlite3.OperationalError):workspace.metadata.execute("INSERT INTO records(run_id,id,type) VALUES('fake','fake','Run')")
 def test_explicit_export_survives_close_and_omits_truth_by_default(self):
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory(prefix='tl-evidence-test-') as parent:
   target=Path(parent).resolve()/'new-evidence'
   with EvaluationWorkspace.create() as workspace:
    s=workspace.session('controller');s.register_artifact(RUN,'artifact','artifact','learning',{});s.put('Run',record('Run'))
    manifest=s.export_evidence(target)
    self.assertFalse(manifest['includes_truth']);self.assertFalse((target/'controller-truth').exists())
    with self.assertRaises(ContractError):s.export_evidence(target)
    with self.assertRaises(ContractError):workspace.session('actor').export_evidence(Path(parent).resolve()/'actor')
   self.assertTrue((target/'evaluation-records.json').is_file())
   self.assertEqual(json.loads((target/'evaluation-records.json').read_text())[0]['type'],'Run')
 def test_export_symlink_rejected(self):
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as parent,EvaluationWorkspace.create() as workspace:
   alias=Path(parent)/'alias';alias.symlink_to(workspace.root,target_is_directory=True)
   with self.assertRaises(ContractError):workspace.session('controller').export_evidence(alias/'new')
 def test_consumption_slot_reason_variation_cannot_duplicate_event(self):
  with EvaluationWorkspace.create() as workspace:
   s=workspace.session('controller');s.register_artifact(RUN,'artifact','artifact','learning',{});s.register_artifact(RUN,'truth','artifact','controller-truth',{});s.put('Run',record('Run'));s.put('Case',record('Case'));s.put('Trial',record('Trial'));s.put('Attempt',record('Attempt'));s.put('Usage',record('Usage'))
   v=record('Usage',id='usage-replay');v['attempt_ref']['value']['revision']=sl(0,'known')
   with self.assertRaises(ContractError):s.put('Usage',v)
 def test_replacement_shares_original_budget_but_has_one_query_occurrence(self):
  with EvaluationWorkspace.create() as workspace:
   s=workspace.session('controller');s.register_artifact(RUN,'artifact','artifact','learning',{});s.register_artifact(RUN,'truth','artifact','controller-truth',{});s.put('Run',record('Run'));s.put('Case',record('Case'));s.put('Case',record('Case',id='mechcase',partition='MECH',source_cluster_id='mech'));s.put('Trial',record('Trial'));s.transition('Trial',RUN,'trial',{'status':'infrastructure_invalid'});s.put('Fault',record('Fault',status='completed',actual_trace_ref=sl(ref(),'known'),actual_terminal=sl('infrastructure_invalid','known')));s.register_identity('assessor','independent_evaluator','independent');s.authorize_replacement(RUN,'trial','fault','assessor');s.put('Trial',record('Trial',id='replacement',occurrence='replacement',replacement_of=sl(ref('trial','Trial'),'known')))
   ledger=BudgetLedger(workspace)
   try:
    for ident,level,parent in [('run','run',None),('batch','batch','run'),('trial','trial','batch')]:ledger.account(ident,level,dict(attempts=6,tokens=196608,tools=4),parent)
    ledger.reserve('original-query','trial','batch','run',phase='query',query_id='q')
    with self.assertRaises(ContractError):ledger.reserve('before-approval','trial','batch','run',phase='query',query_id='q',occurrence='replacement')
    ledger.authorize_replacement(s,RUN,'replacement')
    ledger.reserve('replacement-query','trial','batch','run',phase='query',query_id='q',occurrence='replacement')
    self.assertEqual(ledger.balances('trial')['charged_or_reserved']['attempts'],2)
    with self.assertRaises(sqlite3.IntegrityError):ledger.reserve('extra-replacement','trial','batch','run',phase='query',query_id='q',occurrence='replacement')
   finally:ledger.close()
 def test_known_overrun_is_retained_and_blocks_dispatch(self):
  with EvaluationWorkspace.create() as workspace:
   ledger=BudgetLedger(workspace)
   try:
    for ident,level,parent in [('run','run',None),('batch','batch','run'),('trial','trial','batch')]:ledger.account(ident,level,dict(attempts=6,tokens=196608,tools=4),parent)
    ledger.reserve('a','trial','batch','run');ledger.enter('a');ledger.settle('a',dict(attempts=1,tokens=40000,tools=0));ledger.settle('a',None)
    row=ledger.db.execute("SELECT * FROM reservations WHERE id='a'").fetchone()
    self.assertEqual(row['state'],'violated');self.assertEqual(json.loads(row['actual'])['tokens'],40000)
    self.assertEqual(ledger.balances('run')['charged_or_reserved']['tokens'],40000)
    self.assertEqual(ledger.db.execute('SELECT count(*) FROM budget_violations').fetchone()[0],1)
    with self.assertRaises(ContractError):ledger.reserve('b','trial','batch','run')
   finally:ledger.close()
 def test_deadline_does_not_reset_when_runner_is_recreated(self):
  with EvaluationWorkspace.create() as workspace:
   ledger=BudgetLedger(workspace)
   try:
    for ident,level,parent in [('run','run',None),('batch','batch','run'),('trial','trial','batch')]:ledger.account(ident,level,dict(attempts=6,tokens=196608,tools=4),parent)
    fixture=DeterministicFixture('f',lambda:dict(passed=True,output_tokens=0,evidence={}), 'synthetic')
    DeterministicRunner(ledger,wall_clock=lambda:1000).run(fixture,'a','trial','batch','run')
    with self.assertRaises(ContractError):DeterministicRunner(ledger,wall_clock=lambda:2201).run(fixture,'b','trial','batch','run')
   finally:ledger.close()


class ObservationBoundaryTests(unittest.TestCase):
 def test_late_return_is_not_evaluable_and_stops_next_dispatch(self):
  with EvaluationWorkspace.create() as workspace:
   ledger=BudgetLedger(workspace)
   try:
    for ident,level,parent in [('run','run',None),('batch','batch','run'),('trial','trial','batch')]:ledger.account(ident,level,dict(attempts=6,tokens=196608,tools=4),parent)
    tick=[0]
    def late():
     tick[0]=181
     return dict(passed=True,output_tokens=0,evidence={'returned_late':True})
    runner=DeterministicRunner(ledger,clock=lambda:tick[0],wall_clock=lambda:1000)
    output=runner.run(DeterministicFixture('late',late,'trusted synthetic callback'),'a','trial','batch','run')
    self.assertEqual(output['observation']['status'],'not_evaluable');self.assertIsNone(output['observation']['value'])
    self.assertEqual(ledger.state()['reason'],'observation_deadline')
    with self.assertRaises(ContractError):runner.run(DeterministicFixture('unused',late,'trusted'),'b','trial','batch','run')
   finally:ledger.close()
 def test_failure_evidence_snapshot_survives_temporary_cleanup(self):
  with EvaluationWorkspace.create() as workspace:
   ledger=BudgetLedger(workspace)
   try:
    for ident,level,parent in [('run','run',None),('batch','batch','run'),('trial','trial','batch')]:ledger.account(ident,level,dict(attempts=6,tokens=196608,tools=4),parent)
    def fail():raise RuntimeError('synthetic exception')
    runner=DeterministicRunner(ledger)
    with self.assertRaises(RuntimeError):runner.run(DeterministicFixture('f',fail,'synthetic'),'a','trial','batch','run')
    snapshot=runner.evidence_json()
   finally:ledger.close()
  evidence=json.loads(snapshot)
  self.assertFalse(evidence['results']['a']['observation']['value'])
  self.assertTrue(evidence['results']['a']['actual_callback_entry'])
  self.assertEqual(evidence['events'][-1]['kind'],'failed')
