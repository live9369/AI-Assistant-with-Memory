"""Actual configure receipts and collector lineage, no complete think/model."""
from copy import deepcopy
import json
import tempfile
import unittest
from unittest.mock import patch
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,dumps
from digital_life.application.learning.eligibility import ref
from digital_life.application.learning.engine import source_scope,_dependency
from digital_life.application.learning.runtime import ControllerSourceAuthority,_ControllerReadSession
from digital_life.application.learning.controller_read import ControllerMaterialReader
from tests import test_tool_learning_runtime as fixture


class ControllerPrimaryConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.StrictEngineEndToEndTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.engine=self.f.strict;self.scope=source_scope(self.s)
        (self.s.root/'controller.token').write_text('synthetic-configuration-owner-token')
        self.reader=ControllerMaterialReader(self.s,'Bearer synthetic-configuration-owner-token')
        self.authority=self.reader.sources;self.principal=self.reader.principal;self.entry=self.reader.entry
        kinds=set(self.authority.PRIMARY_CONFIGURATION_REPORTS)
        self.events={row['event_type']:dict(row)for row in self.s.rows('runtime_events')if row['event_type']in kinds}
        self.assertEqual(set(self.events),kinds)
    def event(self,kind='personality_growth.configured'):return self.events[kind]
    def verify(self,key=None,scope=None,token=None):
        key=key or self.event()['id'];token=token or {'object':ref(self.s,key,'runtime_events'),'revision':0,'epoch':0}
        return self.authority.verify(self.entry,self.principal,token,scope or self.scope,'history_audit',self.principal['recipient'],'configured-history')
    def replace_payload(self,payload,kind='personality_growth.configured',hash_value=None):
        key=self.event(kind)['id'];artifact=self.s.artifact(payload)
        self.s.db.execute('UPDATE runtime_events SET payload_artifact_id=?,payload_hash=? WHERE id=?',(artifact,hash_value or __import__('digital_life.domain.tool_learning_contract',fromlist=['fingerprint']).fingerprint(payload),key))
        return key
    def test_all_eight_actual_configure_records_are_readable_without_writes(self):
        before=self.s.db.total_changes
        for row in self.events.values():
            with self.subTest(kind=row['event_type']):
                self.assertEqual(row['source'],'runtime');self.assertEqual(row['lane'],'control')
                self.assertEqual(self.s.db.execute('SELECT count(*) FROM tl_dependency WHERE consumer_ref_id=?',(row['id'],)).fetchone()[0],0)
                self.verify(row['id'])
        self.assertEqual(self.s.db.total_changes,before)
    def test_actual_all_enabled_context_collector_sources_are_primary_configuration_records(self):
        from digital_life.application.runtime.engine import Engine
        entry,principal=self.engine.owners.entry('M14','learn',self.s.config()['controller'])
        Engine(self.s,self.f.identity).transition(self.f.activity,'running','synthetic configuration event collection')
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(self.f.activity,)).fetchone()[0]
        with patch.object(self.engine.provider,'generate_fresh',side_effect=AssertionError('collector must not call model')):
            values,live,fields=self.engine._contexts(entry,principal,self.f.activity,context,'你好，我是liwei',{'items':[]},[],self.scope)
        bundle=fields[0]['dependencies'][0]['target']
        actual=self.s.db.execute("SELECT DISTINCT e.id,e.event_type FROM tl_dependency d JOIN runtime_events e ON e.instance_id=d.instance_id AND e.id=d.source_ref_id WHERE d.instance_id=? AND d.consumer_ref_id=?",(self.s.instance_id,bundle['id'])).fetchall()
        self.assertEqual({row['event_type']for row in actual},set(self.authority.PRIMARY_CONFIGURATION_REPORTS))
        before=self.s.db.total_changes
        with self.reader.boundary():self.reader.qualify(bundle,'actual-calculated-configuration-audit')
        self.assertEqual(self.s.db.total_changes,before);self.assertIn('personality',values)
    def test_real_chat_reader_traverses_eight_configuration_sources_without_model_or_writes(self):
        # Mechanical accepted result, but all configuration sources above were
        # emitted by the real configure APIs in the full-enabled fixture.
        actual=fixture.StrictActualUseTests();actual.f=self.f;actual.s=self.s;actual.activity=self.f.activity;actual.k=self.engine;actual.control=self.f.control
        request,result,intent,scope=actual.producer();thread=identifier()
        context=self.s.db.execute('SELECT id,attributes_json FROM context_snapshots WHERE activity_id=?',(self.f.activity,)).fetchone()
        value=json.loads(context['attributes_json']);value['chat']={'thread_id':thread,'text':'actual internal configuration history'}
        self.s.db.execute('UPDATE context_snapshots SET attributes_json=? WHERE id=?',(dumps(value),context['id']))
        with self.s.tx():
            for row in self.events.values():_dependency(self.s,ref(self.s,result),{'object':ref(self.s,row['id']),'revision':0,'epoch':0},scope,'read','/actual-configured/'+row['event_type'],'learn')
        before=self.s.db.total_changes
        with patch.object(self.engine.provider,'generate_fresh',side_effect=AssertionError('history reader must not invoke model')):chat=self.reader.chat(thread)
        self.assertTrue(any(message['role']=='assistant'and message['text']=='你好，liwei。'for message in chat['messages']))
        self.assertEqual(self.s.db.total_changes,before);self.assertEqual(len(self.s.rows('thought_results')),1)
    def test_unknown_configured_tag_is_not_primary(self):
        key=self.s.event('unknown_module.configured',payload=self.s.read_artifact(self.event()['payload_artifact_id']),lane='control')
        with self.assertRaisesRegex(Forbidden,'producer lineage'):self.verify(key)
    def test_forged_supported_tag_without_complete_record_is_rejected(self):
        key=self.s.event('personality_growth.configured',payload={'enabled':True},lane='control')
        with self.assertRaises(ContractError):self.verify(key)
    def test_supported_tag_with_extra_payload_is_rejected(self):
        payload=self.s.read_artifact(self.event()['payload_artifact_id']);payload['world_fact']='not allowed'
        with self.assertRaises(ContractError):self.verify(self.replace_payload(payload))
    def test_supported_tag_with_wrong_version_is_rejected(self):
        payload=self.s.read_artifact(self.event()['payload_artifact_id']);payload['version']='unknown-version'
        with self.assertRaisesRegex(Forbidden,'version'):self.verify(self.replace_payload(payload))
    def test_wrong_enabled_type_is_rejected(self):
        payload=self.s.read_artifact(self.event()['payload_artifact_id']);payload['enabled']=1
        with self.assertRaises(ContractError):self.verify(self.replace_payload(payload))
    def test_event_digest_wrong_even_for_valid_artifact_is_rejected(self):
        payload=self.s.read_artifact(self.event()['payload_artifact_id'])
        with self.assertRaisesRegex(Conflict,'event payload digest'):self.verify(self.replace_payload(payload,hash_value='0'*64))
    def test_fresh_payload_rehash_detects_same_inode_tamper_after_first_read(self):
        self.verify();row=self.s.row('artifacts',self.event()['payload_artifact_id']);path=self.s.root/'blobs'/row['storage_ref'];raw=path.read_bytes();path.write_bytes(b'x'*len(raw))
        with self.assertRaisesRegex(ContractError,'size/digest mismatch'):self.verify()
    def test_other_input_actor_cannot_become_configuration_owner(self):
        payload=self.s.read_artifact(self.event()['payload_artifact_id']);payload['actor']=self.s.config()['self_actor']
        with self.assertRaisesRegex(Forbidden,'actual controller'):self.verify(self.replace_payload(payload))
    def test_non_control_namespace_cannot_use_supported_event_tag(self):
        payload=self.s.read_artifact(self.event()['payload_artifact_id']);key=self.s.event(self.event()['event_type'],payload=payload,source='external-input',lane='control')
        with self.assertRaisesRegex(Forbidden,'producer contract'):self.verify(key)
    def test_event_binding_fields_are_all_checked(self):
        original=self.event();cases={'lane':'work','correlation_id':identifier(),'source_event_id':'not-a-generated-key','activity_id':self.f.activity,'payload_object_id':self.s.config()['controller'],'causation_event_id':original['id'],'authority_ref':self.s.config()['controller']}
        for column,value in cases.items():
            with self.subTest(column=column):
                if column=='payload_object_id':
                    self.s.db.execute('UPDATE runtime_events SET payload_object_id=?,payload_artifact_id=NULL WHERE id=?',(value,original['id']))
                else:self.s.db.execute('UPDATE runtime_events SET '+column+'=? WHERE id=?',(value,original['id']))
                with self.assertRaisesRegex(Forbidden,'producer contract'):self.verify()
                if column=='payload_object_id':
                    self.s.db.execute('UPDATE runtime_events SET payload_object_id=NULL,payload_artifact_id=? WHERE id=?',(original['payload_artifact_id'],original['id']))
                else:self.s.db.execute('UPDATE runtime_events SET '+column+'=? WHERE id=?',(original[column],original['id']))
    def test_world_claim_cannot_use_configuration_primary_exception(self):
        scope=deepcopy(self.scope);scope['claim_target']='world_claim'
        with self.assertRaisesRegex(Forbidden,'only a source report'):self.verify(scope=scope)
    def test_authoring_review_cannot_use_configuration_primary_exception(self):
        owner=ControllerSourceAuthority(self.s);owner.session=_ControllerReadSession(self.s.config()['controller'],'accept')
        principal=deepcopy(self.principal);principal.update(purpose='accept',module='M03')
        with self.assertRaisesRegex(Forbidden,'producer lineage'):owner.verify(owner.session.nonce,principal,{'object':ref(self.s,self.event()['id']),'revision':0,'epoch':0},self.scope,'accept',principal['recipient'],'configured-review')
    def test_caller_recipient_mismatch_cannot_use_new_primary_rule(self):
        with self.assertRaisesRegex(Forbidden,'producer lineage'):self.authority.verify(self.entry,self.principal,{'object':ref(self.s,self.event()['id']),'revision':0,'epoch':0},self.scope,'history_audit',ref(self.s,self.s.config()['self_actor']),'configured-history')
    def test_unknown_runtime_events_still_require_producer_lineage(self):
        key=self.s.event('synthetic.arbitrary',payload={'same':'not a configuration record'},lane='control')
        with self.assertRaisesRegex(Forbidden,'producer lineage'):self.verify(key)
    def test_tag_relabel_does_not_exempt_thought_results_or_requests(self):
        actual=fixture.StrictActualUseTests();actual.f=self.f;actual.s=self.s;actual.activity=self.f.activity;actual.k=self.engine;actual.control=self.f.control
        request,result,intent,scope=actual.producer()
        self.s.db.execute('PRAGMA foreign_keys=OFF');self.s.db.execute('DROP TRIGGER tl_dependency_delete_guard')
        self.s.db.execute('DELETE FROM tl_dependency WHERE consumer_ref_id IN (?,?)',(request,result));self.s.db.execute('PRAGMA foreign_keys=ON')
        for key in (request,result):
            with self.subTest(key=key),self.assertRaisesRegex(Forbidden,'producer lineage'):
                self.authority.verify(self.entry,self.principal,{'object':ref(self.s,key),'revision':0,'epoch':0},self.scope,'history_audit',self.principal['recipient'],'history')
    def test_missing_real_event_row_is_rejected(self):
        key=self.s.root_object('runtime_events')
        with self.assertRaises(ContractError):self.verify(key)
    def test_missing_payload_artifact_is_rejected(self):
        self.s.db.execute('PRAGMA foreign_keys=OFF');self.s.db.execute('UPDATE runtime_events SET payload_artifact_id=? WHERE id=?',(identifier(),self.event()['id']));self.s.db.execute('PRAGMA foreign_keys=ON')
        with self.assertRaises(ContractError):self.verify()
    def test_cross_instance_token_cannot_reuse_local_configuration_record(self):
        token={'object':ref(self.s,self.event()['id']),'revision':0,'epoch':0};token['object']['instance_id']=identifier()
        with self.assertRaisesRegex(Forbidden,'external source'):self.verify(token=token)
    def test_wrong_registered_event_kind_is_rejected(self):
        token={'object':ref(self.s,self.event()['id']),'revision':0,'epoch':0}
        # Only disposable corruption injection bypasses the registry guard.
        self.s.db.execute('PRAGMA foreign_keys=OFF');self.s.db.execute('DROP TRIGGER immutable_object_registry')
        self.s.db.execute("UPDATE object_registry SET kind='perception_signals' WHERE id=?",(self.event()['id'],));self.s.db.execute('PRAGMA foreign_keys=ON')
        with self.assertRaises(ContractError):self.verify(token=token)
    def test_parameter_ranges_and_full_schema_match_actual_configure(self):
        cases=[('goal_regulation.configured','min_disk_bytes',-1),('agenda.configured','version',True),('maintenance.configured','max_repairs',4),('maintenance.configured','auto_repair',1),('behavior_policy.configured','temperature',0),('behavior_policy.configured','biases',{'unknown':0}),('behavior_policy.configured','biases',{'wait':21}),('behavior_policy.configured','weights',{'wait':{}})]
        behavior=self.s.read_artifact(self.event('behavior_policy.configured')['payload_artifact_id'])
        for feature,value in (('cost',21),('unknown_feature',0)):
            weights=deepcopy(behavior['weights']);weights['wait'][feature]=value;cases.append(('behavior_policy.configured','weights',weights))
        for kind,column,value in cases:
            with self.subTest(kind=kind,column=column):
                original=self.s.read_artifact(self.event(kind)['payload_artifact_id']);payload=deepcopy(original);payload[column]=value
                with self.assertRaises((ContractError,Forbidden)):self.verify(self.replace_payload(payload,kind))
                self.replace_payload(original,kind)

if __name__=='__main__':unittest.main()
