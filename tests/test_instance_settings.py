"""Core configuration paths on temporary instances, no model or formal data."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.monitoring.instance_settings import InstanceSettings
from digital_life.application.runtime.engine import Engine
from digital_life.application.runtime.scheduling import Budget
from digital_life.domain.contracts import ContractError, Conflict, Forbidden


class FixtureModel:
    name='settings-offline-fixture'
    def generate(self,payload):
        return dict(schema_version=1,action=dict(tool='wait',arguments=dict(reason='fixture complete')),explanation='offline reply')


class InstanceSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'instance'
        self.s=Store.prepare(self.root);self.c=Control(self.root,self.s.instance_id);self.service=InstanceSettings(self.s)
        self.addCleanup(self.temp.cleanup);self.addCleanup(self.s.close);self.addCleanup(self.c.close)

    def section(self,key):return next(x for x in self.service.read()['sections'] if x['id']==key)
    def save(self,key,**changes):
        section=self.section(key);values=dict(section['values'],**changes)
        return self.service.save(key,dict(values=values,expected_revision=section['revision'],reason='isolated human configuration',confirmed=True))

    def test_read_only_and_complete_catalog(self):
        before=self.s.db.total_changes;control=self.c.db.total_changes
        with patch('digital_life.infrastructure.llm.inference.probe',side_effect=AssertionError('network')):
            data=self.service.read()
        self.assertEqual(len(data['sections']),21);self.assertTrue(data['can_edit'])
        self.assertEqual(self.s.db.total_changes,before);self.assertEqual(self.c.db.total_changes,control)
        self.assertTrue((self.root/'WAKE_DISABLED').exists());self.assertFalse((self.root/'process-manager.json').exists())

    def test_all_groups_save_through_real_services(self):
        from digital_life.application.behavior.personality_growth import PersonalityGrowth
        from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
        project=Path(self.temp.name)/'source';project.mkdir()
        for section in self.service.read()['sections']:
            key=section['id'];changes={}
            if key in ('cognition','personality_growth','habit_candidates','habit_learning','memory_quality','people_relations','autonomy_agenda','self_feedback','experience_measurement','goal_regulation','maintenance','behavior_policy','recovery'):changes['enabled']=True
            if key=='identity':changes.update(name='临时实例',reply_guidance='先给直接答案')
            if key=='project_access':changes.update(enabled=True,root=str(project),auto_approve=False)
            if key=='personality':changes.update(openness=.4)
            result=self.save(key,**changes);self.assertTrue(result['saved'],key)
            self.assertFalse(result['runtime_started']);self.assertFalse(result['inference_executed'])
        self.assertTrue(PersonalityGrowth(self.s).config()['enabled']);self.assertTrue(AutonomyAgenda(self.s).config()['enabled'])
        self.assertEqual(self.s.config()['name'],'临时实例');self.assertEqual(self.s.integrity(),dict(integrity='ok',foreign_keys=[]))
        self.assertTrue((self.root/'WAKE_DISABLED').exists());self.assertEqual(len(self.s.rows('thought_requests')),0)

    def test_stale_revision_running_and_unknown_fields_rejected(self):
        section=self.section('identity');self.save('identity',name='new')
        body=dict(values=section['values'],expected_revision=section['revision'],reason='old',confirmed=True)
        with self.assertRaises(Conflict):self.service.save('identity',body)
        (self.root/'WAKE_DISABLED').unlink();self.c.resume('test-running-control')
        self.assertFalse(self.service.read()['can_edit'])
        with self.assertRaises(Conflict):self.save('cognition',enabled=True)
        self.c.stop('test-stopped-control')
        section=self.section('budget');body=dict(values=dict(section['values'],unlimited=True),expected_revision=section['revision'],reason='test',confirmed=True)
        with self.assertRaises(ContractError):self.service.save('budget',body)

    def test_invalid_fields_and_service_failure_leave_no_changes(self):
        self.save('budget',budget_enabled=True)
        before=len(self.s.rows('runtime_events'));cfg=len(self.s.rows('configuration_versions'))
        for values in (dict(tokens=True),dict(tokens=float('nan')),dict(tokens=10),dict(request_attempts=9),dict(duration_seconds=60),dict(thought_tokens=20000)):
            with self.assertRaises(ContractError):self.save('budget',**values)
        with self.assertRaises(ContractError):self.save('context',recall_items=51)
        with self.assertRaises(ContractError):self.save('influence',root_weight=1,other_weight=2)
        with self.assertRaises(ContractError):self.save('project_access',enabled=True,root='/')
        self.assertEqual(len(self.s.rows('runtime_events')),before);self.assertEqual(len(self.s.rows('configuration_versions')),cfg)

    def test_new_budget_is_used_old_budget_never_grows(self):
        self.save('budget',budget_enabled=True)
        engine=Engine(self.s);old=engine.submit('old','old')
        self.save('budget',tokens=24000,tool_calls=12,attempts=20,duration_seconds=900,thought_tokens=6000,request_attempts=2,request_seconds=200)
        new=engine.submit('new','new')
        self.assertEqual(Budget(self.s).remaining(old)['tokens'],16000);self.assertEqual(Budget(self.s).remaining(new)['tokens'],24000)
        self.assertEqual(Budget(self.s).remaining(new)['attempts'],20)
        (self.root/'WAKE_DISABLED').unlink();self.c.resume('fixture')
        old_request,old_input=engine.prepare(old,FixtureModel())
        new_request,new_input=engine.prepare(new,FixtureModel())
        self.assertEqual(old_request['token_budget'],4096);self.assertEqual(old_request['attempt_limit'],3)
        self.assertEqual(new_request['token_budget'],6000);self.assertEqual(new_request['attempt_limit'],2)
        self.assertEqual(new_input['context_mode'],'fresh_request')

    def test_history_and_source_weights_are_consumed(self):
        from digital_life.application.chat.chat import Chat
        from digital_life.application.accounts.cognitive_influence import context
        self.save('context',history_messages=0,recall_items=2)
        self.save('influence',root_weight=3,other_weight=.5)
        activity=Chat(self.s).send('isolated-thread',dict(text='hello',idempotency_key='first',expected_last_activity_id=None))['activity_id']
        self.assertEqual(Chat(self.s).context(activity)['messages'],[])
        self.assertEqual(context(self.s,dict(activity_id=activity,selected_memories=[]))['weights'],dict(root=3,other=.5))

    def test_identity_and_manual_profiles_preserve_history(self):
        from digital_life.application.services.personality import Personality
        original=self.s.instance_id;old=Personality(self.s).current()['profile']['id']
        self.save('identity',name='霖铃');self.save('personality',openness=.6)
        self.assertEqual(self.s.instance_id,original);self.assertEqual(len(self.s.rows('identity_anchors')),2)
        self.assertEqual(Personality(self.s).current()['profile']['previous_profile_id'],old)
        self.assertEqual(len(self.s.rows('personality_change_records')),1)
        self.assertFalse(self.section('personality_growth')['values']['enabled'])

    def test_http_only_root_can_read_or_write(self):
        from digital_life.application.accounts.accounts import install,Accounts,public
        from digital_life.entrypoints.http import Application
        install(self.root);auth=Accounts(self.root,self.s.instance_id)
        try:
            root=dict(public(auth.row(auth.root_id())),bootstrap=True)
            auth.setup_root('root-settings-password')
            user=auth.provision(self.s,root,dict(username='member',display_name='member',role='member',password='settings-test-password'))['account']
            login=auth.login('member','settings-test-password');bearer='Bearer '+login.cookie.split(';')[0].split('=',1)[1]
            app=Application(self.root)
            with self.assertRaises(Forbidden):app.dispatch('GET','/v1/instance/settings',controller_bearer=bearer)
            with self.assertRaises(Forbidden):app.dispatch('POST','/v1/instance/settings/cognition',{},controller_bearer=bearer)
            with self.assertRaises(Forbidden):app.dispatch('GET','/v1/instance/lifecycle',controller_bearer=bearer)
            with self.assertRaises(Forbidden):app.dispatch('POST','/v1/instance/lifecycle/restart',{'confirmed':True},controller_bearer=bearer)
            with self.assertRaises(Forbidden):app.dispatch('POST','/v1/instance/settings/cognition/apply',{},controller_bearer=bearer)
            # A real authenticated root login, not a fabricated role claim.
            login=auth.login('root','root-settings-password')
            bearer='Bearer '+login.cookie.split(';')[0].split('=',1)[1]
            code,data=app.dispatch('GET','/v1/instance/settings',controller_bearer=bearer);self.assertEqual(code,200)
            section=next(x for x in data['sections'] if x['id']=='cognition')
            code,data=app.dispatch('POST','/v1/instance/settings/cognition',dict(values={'enabled':True},expected_revision=section['revision'],reason='root test',confirmed=True),controller_bearer=bearer)
            self.assertEqual(code,200);self.assertTrue(data['saved'])
        finally:auth.close()

    def test_protected_storage_remains_blocked(self):
        with patch('digital_life.application.learning.runtime.legacy_protection_present',return_value=True):
            with self.assertRaises(Forbidden):self.service.read()
            with self.assertRaises(Forbidden):self.save('cognition',enabled=True)
