"""Management read/write contract tests; no HTTP, inference or formal instance."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from panel_fixtures import seed_panel
from digital_life.application.monitoring.management import Management,ManagementError
from digital_life.infrastructure.persistence.sqlite_store import Store,PROJECT,RESOURCES
from digital_life.application.runtime.engine import Engine
from digital_life.application.accounts.authorization import Policy
from digital_life.entrypoints.http import Application
from digital_life.domain.contracts import Conflict,Forbidden,utc,ContractError

class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'panel';self.refs=seed_panel(self.root);self.s=Store(self.root);self.m=Management(self.s)
        self.addCleanup(self.tmp.cleanup);self.addCleanup(self.s.close)
    def test_read_pages_do_not_write_or_probe(self):
        before=self.s.db.total_changes; events=len(self.s.rows('runtime_events'))
        with patch('digital_life.infrastructure.llm.inference.probe',side_effect=AssertionError('network forbidden')):
            self.m.overview();self.m.activities({});self.m.approvals({});self.m.model();self.m.templates();self.m.health();self.m.logs({})
        self.assertEqual(self.s.db.total_changes,before);self.assertEqual(len(self.s.rows('runtime_events')),events)
        self.assertTrue((self.root/'WAKE_DISABLED').exists());self.assertEqual(len(self.s.rows('action_attempts')),0)
    def test_overview_does_not_create_a_missing_control_database(self):
        fresh=Store.prepare(Path(self.tmp.name)/'fresh')
        try:
            result=Management(fresh).overview();self.assertFalse(result['control']['prepared'])
            self.assertFalse((fresh.root/'control.sqlite').exists())
        finally:fresh.close()
    def test_overview_distinguishes_lock_and_pending_approvals(self):
        result=self.m.overview();self.assertTrue(result['wake_disabled']);self.assertEqual(result['runtime_status'],'locked');self.assertEqual(result['pending_approvals'],2)
        self.assertEqual(result['health']['state'],'unknown')
    def test_activity_filter_cursor_and_detail(self):
        first=self.m.activities({'limit':'2'});second=self.m.activities({'limit':'2','cursor':first['next_cursor']})
        self.assertFalse({r['id'] for r in first['items']} & {r['id'] for r in second['items']})
        self.assertEqual(len(self.m.activities({'q':'阅读笔记'})['items']),1)
        detail=self.m.activity(self.refs['approve']['activity']);self.assertEqual(len(detail['thoughts']),1);self.assertNotIn('request_artifact_id',detail['thoughts'][0])
        with self.assertRaises(ManagementError):self.m.activity('missing')
    def test_query_validation_and_literal_search(self):
        for query in ({'limit':'0'},{'limit':'101'},{'cursor':'-1'},{'state':'other'},{'q':'x'*201}):
            with self.assertRaises(ManagementError):self.m.activities(query)
        self.assertEqual(self.m.activities({'q':"' OR 1=1 --"})['items'],[])
    def test_approval_snapshot_cas_and_no_execution(self):
        row=self.m.approval(self.refs['approve']['approval']);self.assertTrue(row['can_decide']);self.assertEqual(row['arguments']['text'],'isolated panel output')
        body={'decision':'approved','expected_revision':row['revision'],'expected_arguments_hash':row['arguments_hash']}
        result=self.m.decide(row['id'],body);self.assertFalse(result['runtime_started']);self.assertEqual(len(self.s.rows('action_attempts')),0)
        with self.assertRaises(Conflict):self.m.decide(row['id'],body)
        self.assertEqual(len(self.s.rows('grants')),1)
    def test_stale_hash_and_expired_approval_are_blocked(self):
        row=self.m.approval(self.refs['approve']['approval'])
        with self.assertRaises(Conflict):self.m.decide(row['id'],{'decision':'approved','expected_revision':row['revision'],'expected_arguments_hash':'wrong'})
        expired=self.m.approval(self.refs['expire']['approval']);self.assertEqual(expired['status'],'expired');self.assertFalse(expired['can_decide'])
        with self.assertRaises(Conflict):Policy(self.s).approve(expired['id'],self.s.config()['controller'])
    def test_cancelled_activity_cannot_be_approved_at_core_or_panel(self):
        activity=self.refs['approve']['activity'];row=self.m.approval(self.refs['approve']['approval'])
        self.m.cancel(activity,{'expected_revision':self.s.row('activities',activity)['revision']})
        self.assertEqual(self.m.approval(row['id'])['status'],'cancelled')
        with self.assertRaises(Conflict):Policy(self.s).approve(row['id'],self.s.config()['controller'])
        self.assertEqual(len(self.s.rows('grants')),0)
    def test_rejection_and_cancellation_stale_revision(self):
        row=self.m.approval(self.refs['reject']['approval'])
        self.m.decide(row['id'],{'decision':'rejected','expected_revision':row['revision'],'expected_arguments_hash':row['arguments_hash'],'reason':'isolated review'})
        self.assertEqual(self.s.row('approval_requests',row['id'])['decision'],'rejected')
        with self.assertRaises(Conflict):self.m.cancel(self.refs['pending'],{'expected_revision':999})
    def test_offline_model_validation_save_and_conflict(self):
        current=self.m.model();config={'backend':'ollama','model':'offline-new','base_url':'http://127.0.0.1:11434'}
        before=len(self.s.rows('configuration_versions'))
        with patch('digital_life.infrastructure.llm.inference.probe',side_effect=AssertionError('must be offline')):
            self.assertFalse(self.m.validate_model({'configuration':config})['network_requested'])
            self.assertEqual(len(self.s.rows('configuration_versions')),before)
            result=self.m.save_model({'configuration':config,'expected_configuration_id':current['configuration_id']})
        self.assertFalse(result['network_requested']);self.assertEqual(self.m.model()['configuration']['model'],'offline-new')
        with self.assertRaises(Conflict):self.m.save_model({'configuration':config,'expected_configuration_id':current['configuration_id']})
        self.assertEqual(len(self.s.rows('configuration_versions')),before+1)
    def test_explicit_probe_records_inventory_result_not_generation(self):
        current=self.m.model();seen=[]
        result=self.m.probe_model({'expected_configuration_id':current['configuration_id']},lambda config:seen.append(config) or {'available':True})
        self.assertEqual(len(seen),1);self.assertFalse(result['inference_executed']);self.assertIsNotNone(self.m.model()['last_probe'])
        with self.assertRaises(Conflict):self.m.probe_model({'expected_configuration_id':'old'},lambda _:self.fail('must not probe'))
    def test_health_get_is_snapshot_and_check_is_explicit(self):
        self.assertIsNone(self.m.health()['checked_at']);result=self.m.check_health();self.assertIsNotNone(result['checked_at'])
        self.assertEqual(result['dimensions']['cognition']['state'],'unknown')
        events=len(self.s.rows('runtime_events'));self.m.health();self.assertEqual(len(self.s.rows('runtime_events')),events)
    def test_log_filters_export_and_redaction(self):
        errors=self.m.logs({'level':'error'});self.assertEqual(len(errors['items']),1)
        seq=self.s.row('runtime_events',self.refs['private_event'])['event_seq'];detail=self.m.log(seq)
        self.assertEqual(detail['payload']['api_key'],'[已隐藏]');self.assertEqual(detail['payload']['task'],'[已隐藏]');self.assertEqual(detail['payload']['safe'],'visible')
        exported=json.dumps(self.m.export_logs({'event_type':'fixture.privacy'}),ensure_ascii=False)
        self.assertNotIn('fixture-never-export-api-secret',exported);self.assertNotIn('private task body',exported)
        first=self.m.logs({'limit':'5'});second=self.m.logs({'limit':'5','cursor':first['next_cursor']});self.assertFalse({r['id'] for r in first['items']} & {r['id'] for r in second['items']})
        for query in ({'from':'not-a-date'},{'from':'2026-01-02T00:00:00Z','to':'2026-01-01T00:00:00Z'},{'level':'other'},{'cursor':'abc'}):
            with self.assertRaises(ManagementError):self.m.logs(query)
    def test_known_controller_token_is_redacted_inside_free_text(self):
        token='isolated-secret-token-147118';(self.root/'controller.token').write_text(token)
        with self.s.tx():ref=self.s.event('fixture.token',payload={'message':'prefix '+token+' suffix'})
        seq=self.s.row('runtime_events',ref)['event_seq'];self.assertNotIn(token,json.dumps(self.m.log(seq)))
    def test_packaged_templates_match_canonical_examples(self):
        for item in self.m.templates()['items']:
            self.assertEqual(item['configuration'],json.loads((PROJECT/'config/examples/llm'/item['id']).read_text()))
    def test_invalid_config_cannot_store_literal_secret(self):
        current=self.m.model()
        with self.assertRaises(ContractError):self.m.save_model({'configuration':{'backend':'remote_chat','model':'x','enabled':False,'base_url':'https://invalid.example/v1','api_key':'literal-secret'},'expected_configuration_id':current['configuration_id']})
    def test_api_new_pages_and_idempotent_input_keep_lock(self):
        app=Application(self.root);before=len(self.s.rows('activities'))
        body={'text':'new management task','idempotency_key':'same-key'}
        one=app.dispatch('POST','/v1/events',body)[1];two=app.dispatch('POST','/v1/events',body)[1]
        self.assertEqual(one['activity_id'],two['activity_id']);self.assertEqual(len(self.s.rows('activities')),before+1)
        for path in ('/v1/overview','/v1/activities','/v1/approvals','/v1/model/configuration','/v1/model/templates','/v1/health','/v1/logs'):
            self.assertEqual(app.dispatch('GET',path)[0],200)
        self.assertTrue((self.root/'WAKE_DISABLED').exists())


    def test_activity_displays_only_accepted_reply_and_is_read_only(self):
        activity=self.refs['approve']['activity'];before=self.s.db.total_changes
        detail=self.m.activity(activity)
        self.assertEqual(detail['responses'][0]['reply'],'isolated management fixture')
        self.assertIsNone(detail['responses'][0]['waiting_reason'])
        self.assertEqual(self.s.db.total_changes,before)
        thought=detail['thoughts'][0]
        with self.s.tx():self.s.db.execute("UPDATE thought_results SET acceptance='stale' WHERE id=?",(thought['accepted_result_id'],))
        self.assertIsNone(self.m.activity(activity)['responses'][0]['reply'])

    def test_activity_wait_reason_and_secret_redaction(self):
        activity=self.refs['approve']['activity'];thought=self.m.activity(activity)['thoughts'][0]
        secret='reply-fixture-controller-secret';(self.root/'controller.token').write_text(secret)
        output={'schema_version':1,'explanation':'Hello '+secret,'action':{'tool':'wait','arguments':{'reason':'等待交流'}}}
        with self.s.tx():
            artifact=self.s.artifact(output)
            self.s.db.execute('UPDATE thought_results SET parsed_artifact_id=? WHERE id=?',(artifact,thought['accepted_result_id']))
        response=self.m.activity(activity)['responses'][0]
        self.assertEqual(response['waiting_reason'],'等待交流');self.assertNotIn(secret,response['reply'])
