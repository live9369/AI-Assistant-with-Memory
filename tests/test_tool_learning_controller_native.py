"""Controller native revision mapping; real fresh rows, no complete think."""
from copy import deepcopy
import json
import tempfile
import unittest
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,dumps
from digital_life.application.learning.eligibility import ref,slot
from digital_life.application.learning.runtime import ControllerSourceAuthority,_ControllerReadSession
from digital_life.application.learning.engine import _dependency,source_scope
from digital_life.infrastructure.persistence.sqlite_store import Store
from tests import test_tool_learning_runtime as fixtures


class ControllerNativeRevisionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.StrictActualUseTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.reader=self.f.reader();self.authority=self.reader.sources
        self.principal=self.reader.principal;self.entry=self.reader.entry;self.scope=source_scope(self.s)
        self.native={kind:self.s.rows(kind)[0]for kind in ('identity_anchors','personality_profiles','value_profiles','memory_revisions')}
    def token(self,kind='personality_profiles'):
        row=self.native[kind];number='version'if kind in ('identity_anchors','personality_profiles','value_profiles')else'revision_no'
        return {'object':ref(self.s,row['id'],kind),'revision':row[number],'epoch':0}
    def version(self,token=None):return self.authority.verify_version(self.entry,self.principal,token or self.token(),'controller-native-test')
    def qualified(self,token=None):
        token=token or self.token()
        with self.reader.boundary():
            return self.reader.audit.eligibility.check(self.entry,self.principal,token,self.scope,'history_audit',self.principal['recipient'],'controller-native-test')
    def corrupt_registry(self,**fields):
        self.s.db.execute('DROP TRIGGER immutable_object_revision_registry')
        self.s.db.execute('UPDATE object_revision_registry SET '+','.join(key+'=?'for key in fields)+' WHERE id=?',(*fields.values(),self.native['personality_profiles']['id']))
    def test_actual_native_profile_anchor_value_and_memory_revisions_are_history_readable(self):
        for kind in self.native:
            with self.subTest(kind=kind):self.version(self.token(kind));self.assertTrue(self.qualified(self.token(kind))['qualified'])
    def test_memory_root_and_native_revision_have_same_selected_version(self):
        row=self.native['memory_revisions'];root={'object':ref(self.s,row['memory_id']),'revision':row['revision_no'],'epoch':0}
        self.version(root);self.version(self.token('memory_revisions'));self.assertTrue(self.qualified(root)['qualified'])
    def test_old_native_profile_stays_historical_after_new_profile_created(self):
        old=self.token();row=deepcopy(self.native['personality_profiles']);row.update(id=identifier(),version=row['version']+1)
        self.s.insert('personality_profiles',**row)
        self.version(old);self.assertTrue(self.qualified(old)['qualified'])
    def test_wrong_object_kind_rejected(self):
        token=self.token();token['object']['kind']='identity_anchors'
        with self.assertRaises(ContractError):self.version(token)
    def test_wrong_number_rejected_even_for_native_id(self):
        token=self.token();token['revision']+=1
        with self.assertRaises(Conflict):self.version(token)
    def test_registry_wrong_kind_rejected(self):
        self.corrupt_registry(kind='value_profiles')
        with self.assertRaises(Conflict):self.version()
    def test_registry_wrong_owner_rejected_even_same_root_kind(self):
        other=self.s.root_object('personality-root');self.corrupt_registry(object_id=other)
        with self.assertRaises(Conflict):self.version()
    def test_registry_wrong_number_rejected(self):
        self.corrupt_registry(revision_no=99)
        with self.assertRaises(Conflict):self.version()
    def test_cross_instance_native_reference_rejected(self):
        token=self.token();token['object']['instance_id']=identifier()
        with self.assertRaises(Forbidden):self.version(token)
    def test_foreign_native_id_does_not_resolve_locally(self):
        with tempfile.TemporaryDirectory()as folder:
            other=Store.prepare(folder)
            try:
                row=other.rows('personality_profiles')[0];token={'object':{'instance_id':self.s.instance_id,'id':row['id'],'kind':'personality_profiles','revision':slot()},'revision':row['version'],'epoch':0}
                with self.assertRaises(ContractError):self.version(token)
            finally:other.close()
    def test_registry_without_actual_native_row_rejected(self):
        self.s.db.execute('PRAGMA foreign_keys=OFF');self.s.db.execute('DROP TRIGGER immutable_personality_profiles_delete')
        self.s.db.execute('DELETE FROM personality_profiles WHERE id=?',(self.native['personality_profiles']['id'],));self.s.db.execute('PRAGMA foreign_keys=ON')
        with self.assertRaises(ContractError):self.version()
    def test_actual_native_row_without_registry_rejected(self):
        self.s.db.execute('PRAGMA foreign_keys=OFF');self.s.db.execute('DELETE FROM object_revision_registry WHERE id=?',(self.native['personality_profiles']['id'],));self.s.db.execute('PRAGMA foreign_keys=ON')
        with self.assertRaises(Conflict):self.version()
    def test_any_registry_id_is_not_a_static_source_version(self):
        artifact=self.s.artifact({'synthetic':'not a native revision'});owner=self.s.root_object('personality-root')
        self.s.db.execute('INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind)VALUES(?,?,?,?,?)',(artifact,self.s.instance_id,owner,2,'artifacts'))
        token={'object':ref(self.s,artifact),'revision':2,'epoch':0}
        with self.assertRaises(Forbidden):self.version(token)
    def test_review_purpose_does_not_gain_internal_personality_permission(self):
        authority=ControllerSourceAuthority(self.s);controller=self.s.config()['controller'];authority.session=_ControllerReadSession(controller,'accept')
        principal=deepcopy(self.principal);principal.update(purpose='accept',module='M03')
        token=self.token();authority.verify_version(authority.session.nonce,principal,token,'native-review')
        with self.assertRaisesRegex(Forbidden,'unsupported for controller review'):
            authority.verify(authority.session.nonce,principal,token,self.scope,'accept',principal['recipient'],'native-review')
    def test_private_memory_acl_remains_denied_for_native_revision(self):
        from digital_life.application.services import Memory
        token=self.token('memory_revisions');row=self.native['memory_revisions']
        Memory(self.s).restrict(row['memory_id'],[self.s.config()['self_actor']],self.s.config()['controller'])
        with self.assertRaisesRegex(Forbidden,'ACL or retention'):self.qualified(token)
    def test_external_input_actor_remains_denied(self):
        signal=self.s.row('activities',self.f.activity)['trigger_event_id'];row=self.s.row('perception_signals',signal)
        entity=self.s.insert('world_entities',entity_type='human',canonical_name='synthetic other actor',resolution_status='resolved')
        actor=self.s.insert('social_actors',entity_id=entity,actor_type='user',identity_status='unverified')
        row.update(id=identifier(),source_actor_id=actor,external_id='other-actor-'+identifier());self.s.insert('perception_signals',**row)
        token={'object':ref(self.s,row['id']),'revision':0,'epoch':0}
        with self.assertRaisesRegex(Forbidden,'another input actor'):self.qualified(token)
    def test_authentication_session_binding_still_required(self):
        principal=deepcopy(self.principal);principal['purpose']='accept'
        with self.assertRaises(Forbidden):self.authority.verify_version(self.entry,principal,self.token(),'native-test')
    def test_snapshot_bridge_still_has_real_immutable_event_validation(self):
        entry,principal=self.f.k.owners.entry('M14','learn')
        origin=ref(self.s,self.s.rows('personality_trait_values')[0]['id'])
        token=self.f.k.owners.snapshots.capture(entry,principal,origin,['central_value'],self.scope)
        self.version(token)
        event=self.s.db.execute('SELECT id FROM object_revision_registry WHERE object_id=? AND revision_no=?',(origin['id'],token['revision'])).fetchone()[0]
        self.s.db.execute("UPDATE runtime_events SET source='synthetic invalid snapshot source' WHERE id=?",(event,))
        with self.assertRaises(Conflict):self.version(token)
    def test_observation_concept_belief_root_and_native_revision_mappings(self):
        signal=self.s.row('activities',self.f.activity)['trigger_event_id']
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(self.f.activity,)).fetchone()[0]
        with self.s.tx():
            evidence=self.s.evidence(object_id=signal,method='synthetic native mapping')
            observation=self.s.insert('perception_observations',signal_id=signal,context_id=context,state='active')
            observed=self.s.insert('perception_observation_revisions',observation_id=observation,revision_no=2,content='literal report',locator_json={},uncertainty_json={},extractor_version='synthetic-v1')
            concept=self.s.insert('cognition_concepts',name='synthetic',definition='not a world fact')
            defined=self.s.insert('cognition_concept_revisions',concept_id=concept,revision_no=3,definition='reported concept',evidence_id=evidence)
            subject=self.s.row('social_actors',self.s.config()['controller'])['entity_id']
            belief=self.s.insert('cognition_beliefs',subject_ref=subject,predicate='synthetic',literal=dumps('held report'),scope={})
            believed=self.s.insert('cognition_belief_revisions',belief_id=belief,revision_no=4,content='held report',acceptance_state='held',uncertainty_json={},method_version='synthetic-v1')
        for root,native,number in ((observation,observed,2),(concept,defined,3),(belief,believed,4)):
            self.version({'object':ref(self.s,root),'revision':number,'epoch':0})
            self.version({'object':ref(self.s,native),'revision':number,'epoch':0})
    def test_native_content_and_representation_versions_use_their_actual_owners(self):
        from tests import test_tool_learning_eligibility as original
        case=original.EligibilityTests();case.setUp();self.addCleanup(case.doCleanups)
        case.test_selected_native_revision_keeps_independent_support_and_inputs()
        authority=ControllerSourceAuthority(case.s);controller=case.s.config()['controller'];authority.session=_ControllerReadSession(controller,'history_audit')
        principal={'actor':ref(case.s,controller),'recipient':ref(case.s,controller),'module':'M04','purpose':'history_audit','authorization':ref(case.s,case.s.rows('policy_epochs')[0]['policy_version_id'])}
        for kind,column,owner_column in (('tl_content_revision','revision_no','content_id'),('tl_representation','representation_no','series_id')):
            rows=case.s.rows(kind);self.assertTrue(rows)
            for row in rows:
                for key in (row['id'],row[owner_column]):
                    authority.verify_version(authority.session.nonce,principal,{'object':ref(case.s,key),'revision':row[column],'epoch':0},'native-tl-mapping')
    def test_history_audit_source_barrier_still_blocks_resolved_native_profile(self):
        from tests import test_tool_learning_invalidation as original
        from digital_life.application.learning.eligibility import ToolLearningEligibility
        case=original.F1Tests();case.setUp();self.addCleanup(case.doCleanups)
        row=case.s.rows('personality_profiles')[0];token={'object':ref(case.s,row['id']),'revision':row['version'],'epoch':0}
        controller=case.s.config()['controller'];authority=ControllerSourceAuthority(case.s);authority.session=_ControllerReadSession(controller,'history_audit')
        principal={'actor':ref(case.s,controller),'recipient':ref(case.s,controller),'module':'M04','purpose':'history_audit','authorization':ref(case.s,case.s.rows('policy_epochs')[0]['policy_version_id'])}
        checker=ToolLearningEligibility(case.s,authority)
        checker.check(authority.session.nonce,principal,token,case.scope,'history_audit',principal['recipient'])
        request=case.request();request['payload']['source']=deepcopy(token);request['payload']['purposes']=['learn','history_audit'];case.apply(request)
        with self.assertRaises((Conflict,Forbidden)):checker.check(authority.session.nonce,principal,token,case.scope,'history_audit',principal['recipient'])
    def test_real_chat_reader_traverses_native_sources_without_think_or_writes(self):
        request,result,intent,scope=self.f.producer();thread=identifier()
        context=self.s.db.execute('SELECT id,attributes_json FROM context_snapshots WHERE activity_id=?',(self.f.activity,)).fetchone()
        attributes=json.loads(context['attributes_json']);attributes['chat']={'thread_id':thread,'text':'synthetic native history'}
        self.s.db.execute('UPDATE context_snapshots SET attributes_json=? WHERE id=?',(dumps(attributes),context['id']))
        with self.s.tx():
            for kind in self.native:
                token=self.token(kind)
                _dependency(self.s,ref(self.s,result),token,scope,'read','/synthetic-native/'+kind,'learn')
        before=self.s.db.total_changes;response=self.reader.chat(thread)
        self.assertEqual(self.s.db.total_changes,before)
        self.assertTrue(any(row['role']=='assistant'and row['text']=='你好，liwei。'for row in response['messages']))
        self.assertEqual(len(self.s.rows('thought_results')),1)

if __name__=='__main__':unittest.main()
