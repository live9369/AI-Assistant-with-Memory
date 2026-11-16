"""IM11 synthetic transports only: no network, CLI, account or current instance."""
from copy import deepcopy
from datetime import datetime,timezone
import json
import os
import tempfile
import time
import unittest
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,utc
from digital_life.application.learning.eligibility import slot
from tests.test_tool_learning_products import scope
from digital_life.infrastructure.llm.fresh_learning import FreshLearningProvider,FreshCapability,supervised,validate_learning,CONTRACT,OUTPUT
from digital_life.infrastructure.llm.inference import configured_reasoner

BODY={'contract':OUTPUT,'rationale':'literal scoped source report','limitations':['not a world fact'],'missing_items':[]}

class SyntheticCapability(FreshCapability):
    """Only proves the mechanical test protocol, not an installed provider."""
    def verify(self,provider,packet):return None
    def input_tokens(self,provider,wire):return len(json.dumps(wire).encode())

class FreshProviderTests(unittest.TestCase):
    def packet(self,provider):
        def ref(key,kind):return {'instance_id':'synthetic','id':key,'kind':kind,'revision':slot()}
        self.route={'configuration':ref('cfg','configuration_versions'),'model':ref('model','model_versions'),'provider':provider}
        return {'contract':CONTRACT,'request_id':'actual-thought-row','work_ref':ref('work','tl_work'),
            'binding':dict(deepcopy(self.route),process_run_id='synthetic-process'),
            'instruction':'fixed independent interpretation','source_token':{'object':ref('source','memory_items'),'revision':1,'epoch':0},
            'observation':{'value':False},'baselines':[],'scope':scope(),'output_contract':{'contract':OUTPUT,'rationale':'string','limitations':'string[]','missing_items':'Slot<string>[]'},
            'limits':{'max_input_tokens':30000,'max_output_tokens':200,'max_attempts':1,'max_tool_calls':0,'max_scan':1,'max_items':1,'max_bytes':30000,'deadline':utc(30)}}
    def reasoner(self,provider):
        config={'backend':provider,'model':'synthetic-fixed'}
        if provider=='remote_chat':config.update(base_url='https://synthetic.invalid',enabled=True)
        if provider=='codex_cli':config.update(executable='/synthetic/no-cli',enabled=True)
        return configured_reasoner(config)
    def port(self,provider,transport):
        packet=self.packet(provider)
        return FreshLearningProvider(self.reasoner(provider),self.route,SyntheticCapability(),transport),packet
    @staticmethod
    def envelope(provider,wire,body=BODY):
        if provider=='ollama':return {'done':True,'model':wire['model'],'message':{'content':json.dumps(body)},'prompt_eval_count':10,'eval_count':5}
        if provider=='codex_cli':return {'model':wire['model'],'body':deepcopy(body),'usage':{'input_tokens':10,'output_tokens':5}}
        return {'model':wire['model'],'choices':[{'finish_reason':'stop','message':{'content':json.dumps(body)}}],'usage':{'prompt_tokens':10,'completion_tokens':5}}
    def test_all_provider_wire_contracts_and_independent_input(self):
        for provider in ('remote_chat','ollama','llamacpp','codex_cli'):
            with self.subTest(provider=provider):
                def transport(path,wire,timeout,max_bytes):
                    if provider!='codex_cli':
                        assert len(wire['messages'])==2
                        packet=json.loads(wire['messages'][1]['content'])
                        assert packet['request_id']=='actual-thought-row'
                        assert packet['observation']['value'] is False
                        schema=wire['format'] if provider=='ollama' else wire['response_format']['json_schema']['schema']
                        assert 'action' not in schema['properties']
                        assert schema['properties']['contract']['const']==OUTPUT
                    else:
                        assert not wire['resume'] and not wire['fork']
                        assert wire['fresh_process'] is True
                    return self.envelope(provider,wire)
                port,packet=self.port(provider,transport)
                result=port.generate_fresh(packet)
                self.assertEqual(result['body'],BODY);self.assertEqual(result['route'],self.route)
                self.assertEqual(result['usage']['input_tokens'],10)
                self.assertEqual(result['usage']['attempts'],1)
    def test_default_capability_denies_before_transport(self):
        packet=self.packet('remote_chat');port=FreshLearningProvider(self.reasoner('remote_chat'),self.route,transport=lambda *a: self.fail('must not enter'))
        with self.assertRaises(Forbidden):port.generate_fresh(packet)
    def test_codex_no_synthetic_transport_never_invokes_binary(self):
        packet=self.packet('codex_cli');port=FreshLearningProvider(self.reasoner('codex_cli'),self.route,SyntheticCapability())
        with self.assertRaises(Forbidden):port.generate_fresh(packet)
    def test_action_output_never_selected_by_response_version(self):
        port,packet=self.port('remote_chat',lambda p,w,*a:self.envelope('remote_chat',w,{'schema_version':1,'action':{'tool':'wait','arguments':{'reason':'x'}},'explanation':'not learning'}))
        with self.assertRaises(ContractError):port.generate_fresh(packet)
    def test_wrong_request_contract_denied(self):
        port,packet=self.port('ollama',lambda *a:self.fail('must not call'));packet['contract']='action'
        with self.assertRaises(Forbidden):port.generate_fresh(packet)
    def test_continuation_denied(self):
        for field in ('history','messages','thread_id','previous_response_id','conversation_id','resume','fork'):
            port,packet=self.port('ollama',lambda *a:None);packet[field]='bad'
            with self.assertRaises(Forbidden):port.preflight(packet)
    def test_route_changed_denied(self):
        port,packet=self.port('remote_chat',lambda *a:None);packet['binding']['model']['id']='replacement'
        with self.assertRaises(Forbidden):port.preflight(packet)
    def test_wrong_observed_route_denied(self):
        port,packet=self.port('ollama',lambda p,w,*a:dict(self.envelope('ollama',w),model='other'))
        with self.assertRaises(Forbidden):port.generate_fresh(packet)
    def test_unknown_provider_usage_not_zero(self):
        def transport(p,w,*a):
            result=self.envelope('remote_chat',w);del result['usage'];return result
        port,packet=self.port('remote_chat',transport)
        self.assertIsNone(port.generate_fresh(packet)['usage'])
    def test_refusal_not_result(self):
        def transport(p,w,*a):
            result=self.envelope('remote_chat',w);result['choices'][0]['message']['refusal']='no';return result
        port,packet=self.port('remote_chat',transport)
        with self.assertRaises(ContractError):port.generate_fresh(packet)
    def test_token_and_byte_preflight_limits(self):
        port,packet=self.port('ollama',lambda *a:None);packet['limits']['max_input_tokens']=1
        with self.assertRaises(Forbidden):port.preflight(packet)
        packet['limits']['max_input_tokens']=30000;packet['limits']['max_bytes']=1
        with self.assertRaises(Forbidden):port.preflight(packet)
    def test_hanging_transport_terminated_real_process(self):
        with tempfile.TemporaryDirectory() as folder:
            marker=folder+'/late'
            def call():
                time.sleep(.4)
                with open(marker,'w') as f:f.write('must never happen')
                return {}
            start=time.monotonic()
            with self.assertRaises(Forbidden):supervised(call,.06,1000)
            self.assertLess(time.monotonic()-start,.3)
            time.sleep(.45);self.assertFalse(os.path.exists(marker))
    def test_managed_nested_process_cannot_outlive_transport_deadline(self):
        import subprocess,sys,signal
        with tempfile.TemporaryDirectory() as folder:
            pidfile=folder+'/child.pid';late=folder+'/late'
            def transport():
                child=subprocess.Popen([sys.executable,'-c',"import time;time.sleep(.6);open(%r,'w').write('late')"%late],start_new_session=False)
                with open(pidfile,'w') as stream:stream.write(str(child.pid))
                child.wait();return {}
            with self.assertRaises(Forbidden):supervised(transport,.15,1000)
            self.assertTrue(os.path.exists(pidfile))
            time.sleep(.65);self.assertFalse(os.path.exists(late))
            # A reparented zombie is already dead; unlike kill(pid,0), ps lets
            # this assertion distinguish it from a live sleeping descendant.
            with open(pidfile) as stream:pid=int(stream.read())
            import ctypes,sys
            if sys.platform=='darwin':
                lib=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True);buf=ctypes.create_string_buffer(256)
                size=lib.proc_pidinfo(pid,3,0,buf,256)
                self.assertTrue(size==0 or int.from_bytes(buf.raw[4:8],'little')==5)
            else:
                from pathlib import Path
                stat=Path('/proc')/str(pid)/'stat'
                self.assertTrue(not stat.exists() or stat.read_text().split(') ')[1].startswith('Z'))
    def test_capability_boolean_is_not_authority(self):
        class Bad(SyntheticCapability):
            def verify(self,*args):return False
        packet=self.packet('ollama');port=FreshLearningProvider(self.reasoner('ollama'),self.route,Bad(),lambda *a:None)
        with self.assertRaises(Forbidden):port.preflight(packet)
    def test_packet_bool_limits_and_unknown_fields_rejected(self):
        port,packet=self.port('ollama',lambda *a:None);packet['limits']['max_attempts']=True
        with self.assertRaises(ContractError):port.preflight(packet)
        packet['limits']['max_attempts']=1;packet['hidden_history']='bad'
        with self.assertRaises(ContractError):port.preflight(packet)
    def test_content_duplicate_keys_rejected_but_known_usage_survives(self):
        def transport(p,w,*a):
            result=self.envelope('remote_chat',w);result['choices'][0]['message']['content']='{"contract":"bad","contract":"'+OUTPUT+'","rationale":"x","limitations":[],"missing_items":[]}'
            return result
        port,packet=self.port('remote_chat',transport)
        with self.assertRaises(ContractError):port.generate_fresh(packet)
        self.assertEqual(port.last_usage['input_tokens'],10)
        self.assertEqual(port.last_measurements['dimensions']['output_tokens']['value'],5)
    def test_partial_usage_preserves_known_facts_and_holds_unknown(self):
        def transport(p,w,*a):
            result=self.envelope('ollama',w);del result['eval_count'];return result
        port,packet=self.port('ollama',transport);result=port.generate_fresh(packet)
        self.assertIsNone(result['usage']);facts=port.last_measurements['dimensions']
        self.assertEqual(facts['input_tokens']['value'],10);self.assertEqual(facts['attempts']['value'],1)
        self.assertEqual(facts['output_tokens']['status'],'unknown');self.assertEqual(facts['bytes']['status'],'known')
    def test_late_use_denied_known_consumption_kept(self):
        port,packet=self.port('ollama',lambda p,w,*a:self.envelope('ollama',w))
        now=datetime.now(timezone.utc);future=datetime.fromisoformat(utc(60).replace('Z','+00:00'))
        calls=[now,future];port.clock=lambda:calls.pop(0)
        with self.assertRaises(Forbidden):port.generate_fresh(packet)
        self.assertEqual(port.last_usage['input_tokens'],10)
        self.assertEqual(port.last_measurements['dimensions']['elapsed_ms']['status'],'known')
    def test_response_byte_limit(self):
        with self.assertRaises(ContractError):supervised(lambda:'x'*20000,.5,100)
    def test_expired_deadline_never_enters(self):
        port,packet=self.port('remote_chat',lambda *a:self.fail('must not enter'));packet['limits']['deadline']=utc(-1)
        with self.assertRaises(Forbidden):port.generate_fresh(packet)
    def test_malformed_usage_not_counted_known(self):
        def transport(p,w,*a):
            result=self.envelope('ollama',w);result['eval_count']=False;return result
        port,packet=self.port('ollama',transport)
        self.assertIsNone(port.generate_fresh(packet)['usage'])


class ManifestTests(unittest.TestCase):
    def field(self,path,value,dependencies=(),kind='fixed_instruction'):
        from digital_life.domain import tool_learning_contract as c
        return {'path':path,'digest':{'algorithm':'sha256','hex':c.fingerprint(value)},'kind':kind,'usage':'fixed_instruction' if kind=='fixed_instruction' else 'historical_observation','dependencies':list(dependencies),'dependency_scopes':[scope() for _ in dependencies],'scope':scope()}
    def manifest(self,packet,fields):
        from digital_life.domain import tool_learning_contract as c
        return {'contract':'TL-INPUT-ASSEMBLY-1','packet_digest':c.fingerprint(packet),'fields':fields}
    def test_complete_all_features_not_selected_memory_only(self):
        from digital_life.application.learning.runtime import validate_manifest
        packet={'task':'x','personality':{'traits':[0,False,None]},'conversation':{'he':'previous person'}}
        good=self.manifest(packet,[self.field('/'+k,v) for k,v in packet.items()])
        validate_manifest(packet,good)
        with self.assertRaises(Forbidden):validate_manifest(packet,self.manifest(packet,good['fields'][:1]))
    def test_field_digest_and_overlapping_prefix_rejected(self):
        from digital_life.application.learning.runtime import validate_manifest
        packet={'data':{'x':False}}
        with self.assertRaises(Conflict):validate_manifest(packet,self.manifest(packet,[self.field('/data',{'x':0})]))
        with self.assertRaises(Forbidden):validate_manifest(packet,self.manifest(packet,[self.field('/data',packet['data']),self.field('/data/x',False)]))
    def test_source_material_without_read_provenance_rejected(self):
        from digital_life.application.learning.runtime import validate_manifest
        packet={'source':'actual user data'}
        with self.assertRaises(Forbidden):validate_manifest(packet,self.manifest(packet,[self.field('/source',packet['source'],kind='source_material')]))

class ControllerReviewHttpTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_acceptance import AcceptanceTests
        self.base=AcceptanceTests();self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.s=self.base.s;self.db=self.s.db;policy=self.base.policy()
        self.db.execute('UPDATE policy_epochs SET policy_version_id=? WHERE instance_id=?',(policy,self.s.instance_id))
        self.body=self.base.review();self.body['expires_at']=utc(60)
        from digital_life.application.learning.eligibility import ref,ToolLearningEligibility
        from tests.test_tool_learning_invalidation import MechanicalEligibility
        principal=deepcopy(self.base.request['principal']);principal.update(recipient=ref(self.s,self.s.config()['controller']))
        dependency={'target':deepcopy(self.base.obs.source['source']),'relation':'derive','expected':{'object':deepcopy(self.base.obs.source['source']),'revision':1,'epoch':0},'consumer_purpose':'accept'}
        ToolLearningEligibility(self.s,MechanicalEligibility()).register_dependency('synthetic-fixture-only',principal,ref(self.s,self.base.proposal['id']),dependency,'/synthetic-source',self.body['actual_scope'])
        from digital_life.entrypoints.http import create_server
        import threading
        self.server=create_server(self.s.root,0);self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.token=(self.s.root/'controller.token').read_text().strip()
    def call(self,bearer,body=None):
        import http.client
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        conn.request('POST','/v1/learning/content-reviews',body=json.dumps(self.body if body is None else body),headers={'Authorization':bearer,'Content-Type':'application/json'})
        response=conn.getresponse();result=(response.status,json.loads(response.read()));conn.close();return result
    def test_real_bearer_required_not_actor_claim(self):
        count=len(self.s.rows('perception_signals'))
        self.assertEqual(self.call('Bearer invalid')[0],403)
        self.assertEqual(len(self.s.rows('perception_signals')),count)
    def test_authenticated_full_bound_review_persisted_no_credential(self):
        status,result=self.call('Bearer '+self.token)
        self.assertEqual(status,201,result)
        row=self.s.row('perception_signals',result['review']['id'])
        self.assertEqual(row['source_actor_id'],self.s.config()['controller'])
        body=self.s.read_artifact(row['artifact_id']);self.assertEqual(body,self.body)
        self.assertNotIn(self.token,json.dumps(body));self.assertFalse(result['scientific_support_granted'])
    def test_authenticated_wrong_digest_rejected(self):
        body=deepcopy(self.body);body['proposal_digest']='0'*64
        self.assertEqual(self.call('Bearer '+self.token,body)[0],409)

class ProductLineageTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_observation import ObservationTests
        self.base=ObservationTests();self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.s=self.base.s
    def test_all_four_products_and_actual_copies_are_source_reachable(self):
        self.base.assess();source=self.base.source['source']['id']
        reached=self.base.service.eligibility.closure(source)
        rows=self.s.rows('tl_product');self.assertEqual(len(rows),4)
        for row in rows:
            self.assertIn(row['id'],reached);self.assertIn(row['payload_artifact_id'],reached)
            deps=self.s.db.execute('SELECT relation FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=?',(self.s.instance_id,row['payload_artifact_id'])).fetchall()
            self.assertEqual({r[0] for r in deps},{'read','delete'})
    def test_dependency_write_fault_rolls_back_product_and_all_copies(self):
        from unittest.mock import patch
        before=len(self.s.rows('tl_dependency'));original=self.base.service._derived_dependency
        def fault(*args,**kwargs):original(*args,**kwargs);raise OSError('synthetic lineage write failure')
        with patch.object(self.base.service,'_derived_dependency',fault):
            with self.assertRaises(OSError):self.base.assess()
        self.assertFalse(self.s.rows('tl_product'))
        # The separately committed real retrieval input remains a truthful
        # pre-C1 fact; no failed Product/payload dependency may survive C1.
        staged={row['payload_artifact_id'] for row in self.s.rows('runtime_events') if row['event_type'] in ('observation.prepare','observation.material')}
        for row in self.s.rows('tl_dependency'):
            kind=self.s.row('object_registry',row['consumer_ref_id'])['kind']
            self.assertIn(kind,('memory_retrieval_runs','runtime_events','artifacts'))
            if kind=='artifacts':self.assertIn(row['consumer_ref_id'],staged)
        registered={row['storage_ref'] for row in self.s.rows('artifacts')}
        self.assertTrue(all(path.name in registered for path in (self.s.root/'blobs').iterdir()))


class AssemblyGateTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_invalidation import F1Tests,MechanicalEligibility
        from digital_life.application.learning.runtime import ToolLearningRuntime,RuntimeAuthority
        from digital_life.application.learning.eligibility import ref
        from digital_life.domain.contracts import identifier
        from digital_life.domain import tool_learning_contract as c
        self.base=F1Tests();self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.s=self.base.s;self.principal=deepcopy(self.base.query_principal)
        class MechanicalRuntime(RuntimeAuthority):
            def verify_assembly(self,*args):return None
            def verify_retention(self,*args):return None
        self.runtime=ToolLearningRuntime(self.s,MechanicalRuntime(),MechanicalEligibility())
        self.packet={'task':'received literal source','personality':{'synthetic_trait':False},'states':{'synthetic':0}}
        fields=[]
        for key,value in self.packet.items():
            fields.append({'path':'/'+key,'digest':{'algorithm':'sha256','hex':c.fingerprint(value)},'kind':'source_material','usage':'historical_observation',
                'dependencies':[{'target':deepcopy(self.base.token['object']),'expected':deepcopy(self.base.token),'relation':'read','consumer_purpose':'learn'}],'dependency_scopes':[deepcopy(self.base.scope)], 'scope':deepcopy(self.base.scope)})
        self.manifest={'contract':'TL-INPUT-ASSEMBLY-1','packet_digest':c.fingerprint(self.packet),'fields':fields}
        activity=self.base.work['learning_activity_id'];configuration=self.s.db.execute('SELECT * FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone();model=self.s.db.execute('SELECT * FROM model_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()
        artifact=self.s.artifact(self.packet)
        step=self.s.insert('activity_steps',activity_id=activity,step_no=0,step_type='synthetic-assembly',state='pending',attempt=0,idempotency_key=identifier())
        thought=self.s.insert('thought_requests',activity_id=activity,step_id=step,request_key=identifier(),purpose='infer',task='synthetic',instruction_version='synthetic-assembly',output_schema_version=70,request_artifact_id=artifact,request_hash=c.fingerprint(self.packet),input_manifest_hash=c.fingerprint(self.manifest),model_config_id=configuration['id'],model_version_id=model['id'],prepared_activity_revision=0,expected_input_epoch=0,expected_policy_epoch=0,runtime_epoch=0,process_run_id='synthetic-no-runtime',deadline=utc(30),token_budget=100,attempt_limit=1,retry_policy={'max_attempts':1},generation_config={},state='prepared')
        self.request=ref(self.s,thought)
    def assemble(self):return self.runtime.assemble('synthetic-runtime',self.request,self.principal,self.packet,self.manifest)
    def invoke(self,callback):return self.runtime.invoke('synthetic-runtime',self.request,self.principal,self.packet,self.manifest,callback)
    def test_complete_manifest_all_fields_registered_before_actual_callback(self):
        proof=self.assemble();self.assertEqual(len(proof['inputs']),3)
        called=[];self.assertEqual(self.invoke(lambda:called.append('actual') or 'result'),'result');self.assertEqual(called,['actual'])
    def test_no_complete_proof_no_actual_callback(self):
        with self.assertRaises(Forbidden):self.invoke(lambda:self.fail('must not enter'))
    def test_partial_registration_is_not_complete_assembly(self):
        from unittest.mock import patch
        original=self.runtime.eligibility.register_input;calls=[]
        def fail_second(*args,**kwargs):
            calls.append(1)
            if len(calls)==2:raise Forbidden('synthetic second source denial')
            return original(*args,**kwargs)
        with patch.object(self.runtime.eligibility,'register_input',fail_second):
            with self.assertRaises(Forbidden):self.assemble()
        self.assertEqual(len(self.s.rows('tl_input_dependency')),1)
        with self.assertRaises(Forbidden):self.invoke(lambda:self.fail('partial cannot enter'))
    def test_f1_after_complete_assembly_blocks_actual_callback(self):
        self.assemble();self.base.apply()
        with self.assertRaises((Forbidden,Conflict)):self.invoke(lambda:self.fail('revoked input cannot enter'))
    def test_packet_mutation_does_not_reuse_existing_proof(self):
        self.assemble();self.packet['personality']['synthetic_trait']=0
        with self.assertRaises(Conflict):self.invoke(lambda:self.fail('changed payload cannot enter'))

class StrictLegacyBoundaryTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_work import WorkTests
        self.base=WorkTests();self.base.setUp();self.addCleanup(self.base.doCleanups);self.s=self.base.s
        policy=self.s.insert('policy_versions',version=90,mode='authorization',scope={'tool_learning_runtime':{'contract':'TL-STRICT-RUNTIME-1','enabled':True}},effective_at=utc(),authority=self.s.config()['controller'])
        self.s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE instance_id=?',(policy,self.s.instance_id))
    def test_strict_legacy_engine_blocks_before_prepare_or_inference(self):
        from digital_life.application.runtime.engine import Engine
        engine=Engine(self.s)
        class NoModel:
            name='synthetic'
            def generate(self,*args):raise AssertionError('must not enter')
        count=len(self.s.rows('activities'))
        with self.assertRaises(Forbidden):engine.submit('not accepted into legacy path','new-input')
        self.assertEqual(len(self.s.rows('activities')),count)
        with self.assertRaises(Forbidden):engine.prepare(self.base.source_activity,NoModel())
        with self.assertRaises(Forbidden):engine.think(self.base.source_activity,NoModel())
        self.assertFalse(self.s.rows('thought_attempts'))
    def test_strict_executor_blocks_before_tool_callback(self):
        from digital_life.application.runtime.execution import Executor
        from digital_life.domain.contracts import RuntimeIdentity
        with self.assertRaises(Forbidden):Executor(self.s,RuntimeIdentity(0,'synthetic')).dispatch('nonexistent',lambda *a:self.fail('must not execute'))
    def test_strict_legacy_private_read_surfaces_blocked(self):
        from digital_life.application.chat.chat import Chat
        from digital_life.application.monitoring.thought_inspection import ThoughtInspection
        with self.assertRaises(Forbidden):Chat(self.s).detail('synthetic')
        with self.assertRaises(Forbidden):ThoughtInspection(self.s).detail('synthetic')

class SourceSnapshotTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_work import WorkTests
        from digital_life.application.learning.source_snapshot import SourceSnapshots,SnapshotAuthority
        from digital_life.application.learning.eligibility import ref
        self.base=WorkTests();self.base.setUp();self.addCleanup(self.base.doCleanups);self.s=self.base.s
        class MechanicalSnapshot(SnapshotAuthority):
            def verify_source(self,*args):return None
            def verify_capture(self,*args):return None
            def dependencies(self,*args):return []
        self.authority=MechanicalSnapshot();self.snapshots=SourceSnapshots(self.s,self.authority)
        self.principal=deepcopy(self.base.request['principal']);self.scope=scope()
        row=self.s.rows('personality_trait_values')[0];self.origin=ref(self.s,row['id']);self.selector=['central_value']
    def capture(self):return self.snapshots.capture('synthetic-snapshot',self.principal,self.origin,self.selector,self.scope)
    def test_real_snapshot_registry_payload_and_same_observation_reuse(self):
        first=self.capture();second=self.capture();self.assertEqual(first,second);self.assertEqual(first['revision'],1)
        fixed=self.snapshots.fixed('synthetic-snapshot',self.principal,first,self.scope)
        self.assertEqual(fixed['native_revision']['status'],'not_applicable');self.assertEqual(fixed['value'],{'central_value':0.0})
        revision=self.s.db.execute('SELECT * FROM object_revision_registry WHERE object_id=?',(self.origin['id'],)).fetchone()
        self.assertEqual(self.s.row('object_registry',revision['id'])['kind'],'runtime_events')
    def test_inplace_change_rejects_old_fixed_request_without_repair(self):
        first=self.capture();self.s.db.execute('UPDATE personality_trait_values SET central_value=.4 WHERE id=?',(self.origin['id'],))
        before=len(self.s.rows('runtime_events'))
        with self.assertRaises(Conflict):self.snapshots.fixed('synthetic-snapshot',self.principal,first,self.scope)
        self.assertEqual(len(self.s.rows('runtime_events')),before)
        second=self.capture();self.assertEqual(second['revision'],2)
        self.assertEqual(self.snapshots.fixed('synthetic-snapshot',self.principal,second,self.scope)['value']['central_value'],.4)
    def test_unobserved_aba_never_invents_intermediate_history(self):
        first=self.capture();self.s.db.execute('UPDATE personality_trait_values SET central_value=.4 WHERE id=?',(self.origin['id'],));self.s.db.execute('UPDATE personality_trait_values SET central_value=0 WHERE id=?',(self.origin['id'],))
        self.assertEqual(self.capture(),first)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM object_revision_registry WHERE object_id=?',(self.origin['id'],)).fetchone()[0],1)
    def test_two_source_categories_and_native_source_refusal(self):
        from digital_life.application.learning.eligibility import ref
        actor=ref(self.s,self.s.config()['self_actor']);token=self.snapshots.capture('synthetic-snapshot',self.principal,actor,['identity_status'],self.scope)
        self.assertEqual(token['revision'],1)
        memory=ref(self.s,self.base.f.expected['memory_id'])
        with self.assertRaises(Forbidden):self.snapshots.capture('synthetic-snapshot',self.principal,memory,['state'],self.scope)
    def test_audit_no_new_snapshot_or_repair_write(self):
        before=len(self.s.rows('runtime_events'))
        with self.assertRaises(Forbidden):self.snapshots.capture('synthetic-snapshot',self.principal,self.origin,self.selector,self.scope,audit=True)
        self.assertEqual(len(self.s.rows('runtime_events')),before)
    def test_real_event_mapping_required_not_just_registry_number(self):
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        token=self.capture();known=deepcopy(self.origin);known['revision']=slot(token['revision']);ToolLearningStore(self.s).validate_ref(known)
        event=self.s.db.execute('SELECT id FROM object_revision_registry WHERE object_id=?',(self.origin['id'],)).fetchone()[0]
        self.s.db.execute("UPDATE runtime_events SET source='not-a-source-snapshot' WHERE id=?",(event,))
        with self.assertRaises(Conflict):ToolLearningStore(self.s).validate_ref(known)
    def test_snapshot_and_payload_actual_retention_targets_reachable(self):
        from digital_life.application.learning.eligibility import ToolLearningEligibility
        self.capture();closure=ToolLearningEligibility(self.s).closure(self.origin['id'])
        row=self.s.db.execute("SELECT * FROM runtime_events WHERE source='tl.source.snapshot'").fetchone()
        self.assertIn(row['id'],closure);self.assertIn(row['payload_artifact_id'],closure)

    def test_native_cas_aba_rejects_old_live_but_history_stays_real(self):
        from digital_life.application.learning.eligibility import ref
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        origin=ref(self.s,self.base.source_activity)
        first=self.snapshots.capture('synthetic-snapshot',self.principal,origin,['state'],self.scope)
        self.s.db.execute('UPDATE activities SET revision=revision+2 WHERE id=?',(origin['id'],))
        before=len(self.s.rows('runtime_events'))
        known=deepcopy(origin);known['revision']=slot(first['revision'])
        ToolLearningStore(self.s).validate_ref(known)
        with self.assertRaises(Conflict):self.snapshots.fixed('synthetic-snapshot',self.principal,first,self.scope)
        self.assertEqual(len(self.s.rows('runtime_events')),before)
        second=self.snapshots.capture('synthetic-snapshot',self.principal,origin,['state'],self.scope)
        self.assertEqual(second['revision'],first['revision']+1)

class ImmutableReferenceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.base=AssemblyGateTests();self.base.setUp();self.addCleanup(self.base.doCleanups);self.s=self.base.s
    def test_cached_ref_never_caches_source_barrier_or_epoch(self):
        from digital_life.infrastructure.persistence.tool_learning_meter import immutable_reference_boundary
        eligibility=self.base.runtime.eligibility;root=self.base.base
        with immutable_reference_boundary(self.s):
            eligibility.check('synthetic-runtime',self.base.principal,root.token,root.scope,'learn',self.base.principal['recipient'])
            root.apply()
            with self.assertRaises((Conflict,Forbidden)):
                eligibility.check('synthetic-runtime',self.base.principal,root.token,root.scope,'learn',self.base.principal['recipient'])
    def test_exact_mapping_cache_invalidates_on_write_and_next_boundary(self):
        from digital_life.infrastructure.persistence.tool_learning_meter import immutable_reference_boundary
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        storage=ToolLearningStore(self.s);value=deepcopy(self.base.request);before=self.s.db.total_changes
        with immutable_reference_boundary(self.s):
            storage.validate_ref(value);storage.validate_ref(value)
            self.assertEqual(self.s.db.total_changes,before)
            wrong=deepcopy(value);wrong['kind']='perception_signals'
            with self.assertRaises(ContractError):storage.validate_ref(wrong)
            wrong=deepcopy(value);wrong['revision']=slot(999)
            with self.assertRaises(Conflict):storage.validate_ref(wrong)
            import sqlite3
            with self.assertRaises(sqlite3.IntegrityError):
                self.s.db.execute("UPDATE object_registry SET kind='synthetic-wrong-owner' WHERE id=?",(value['id'],))
        with immutable_reference_boundary(self.s):
            with self.assertRaises(Conflict):storage.validate_ref(wrong)
    def test_same_connection_snapshot_mapping_mutation_invalidates_cached_fact(self):
        from digital_life.infrastructure.persistence.tool_learning_meter import immutable_reference_boundary
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        fixture=SourceSnapshotTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        token=fixture.capture();storage=ToolLearningStore(fixture.s);known=deepcopy(token['object']);known['revision']=slot(token['revision'])
        with immutable_reference_boundary(fixture.s):
            storage.validate_ref(known);storage.validate_ref(known)
            event=fixture.s.db.execute('SELECT id FROM object_revision_registry WHERE object_id=?',(known['id'],)).fetchone()[0]
            fixture.s.db.execute("UPDATE runtime_events SET source='invalidated-mapping' WHERE id=?",(event,))
            with self.assertRaises(Conflict):storage.validate_ref(known)
        with immutable_reference_boundary(fixture.s):
            with self.assertRaises(Conflict):storage.validate_ref(known)


class OriginalActivityBudgetTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_work import WorkTests
        from digital_life.application.learning.activity_budget import ActivityResourceBudget,ActivityBudgetAuthority
        from digital_life.application.learning.budget import BudgetAuthority
        from digital_life.application.learning.eligibility import ref
        from digital_life.domain.contracts import identifier
        self.base=WorkTests();self.base.setUp();self.addCleanup(self.base.doCleanups);self.s=self.base.s
        class Initial(ActivityBudgetAuthority):
            def verify_initial_caps(self,*args):return None
        class MechanicalBudget(BudgetAuthority):
            def verify_budget(self,*args):return None
            def verify_entry(self,*args):return None
            def verify_settlement(self,*args):return None
        self.initial=Initial();self.activity=identifier();deadline=utc(500)
        with self.s.tx():
            self.s.insert('activities',id=self.activity,trigger_event_id=self.s.row('activities',self.base.source_activity)['trigger_event_id'],state='pending',budget_json={'tokens':300,'tool_calls':1},release_id='synthetic',publication_state='ready',deadline=deadline)
            account=self.s.insert('activity_budget_accounts',activity_id=self.activity,token_limit=300,tool_call_limit=1,attempt_limit=2,time_limit_ms=100000)
            self.caps={'account_ref':ref(self.s,account),'deadline':deadline,'max_attempts':2,'max_input_tokens':200,'max_output_tokens':100,'max_tool_calls':1,'max_scan':10,'max_items':10,'max_bytes':1000}
            self.policy={'object':ref(self.s,self.base.f.expected['policy_id']),'revision':0,'epoch':0}
            ActivityResourceBudget.initialize(self.s,'synthetic-initial',self.activity,self.caps,self.policy,self.initial)
        context=self.s.insert('context_snapshots',activity_id=self.activity,context_schema='synthetic',attributes_json={})
        run=self.s.insert('memory_retrieval_runs',activity_id=self.activity,context_id=context,query='synthetic',retriever_version='synthetic')
        self.run=ref(self.s,run);self.budget=ActivityResourceBudget(self.s,MechanicalBudget())
    def reserve(self):return self.budget.reserve('synthetic-budget',self.activity,self.run,'retrieval',{'scan':10,'items':10,'bytes':1000,'elapsed_ms':1000},request_budget=self.caps)
    def test_actual_original_eight_dimensional_cap_once_and_own_reservation(self):
        row=self.reserve();self.assertEqual(self.budget.check_activity(self.activity)['remaining']['bytes'],0)
        self.budget.record_entry('synthetic-budget',self.activity,row['id'],{'actual_run':self.run})
        actual={k:0 for k in ('input_tokens','output_tokens','attempts','tool_calls','scan','items','bytes','elapsed_ms')};actual.update(scan=1,items=1,bytes=55,elapsed_ms=2)
        self.budget.settle('synthetic-budget',self.activity,row['id'],actual)
        self.assertEqual(self.budget.check_activity(self.activity)['remaining']['bytes'],945)
        self.assertFalse(self.s.db.execute('SELECT id FROM tl_work WHERE learning_activity_id=?',(self.activity,)).fetchone())
    def test_no_reinitialize_or_legacy_budget_bypass(self):
        from digital_life.application.learning.activity_budget import ActivityResourceBudget
        from digital_life.application.runtime.scheduling import Budget
        with self.s.tx():
            with self.assertRaises(Conflict):ActivityResourceBudget.initialize(self.s,'synthetic',self.activity,self.caps,self.policy,self.initial)
            with self.assertRaises(ContractError):Budget(self.s).reserve(self.activity,'fake','thought_attempt')
    def test_unknown_actual_preserves_original_full_hold(self):
        row=self.reserve();self.budget.record_entry('synthetic-budget',self.activity,row['id'],{'actual_run':self.run});self.budget.settle('synthetic-budget',self.activity,row['id'],None)
        snapshot=self.budget.check_activity(self.activity);self.assertIn('usage_unknown',snapshot['block_reasons']);self.assertEqual(snapshot['remaining']['bytes'],0)
    def test_cap_mutation_not_a_new_budget(self):
        from digital_life.domain import tool_learning_contract as c
        from digital_life.domain.contracts import dumps
        doc=c.loads(self.s.row('activities',self.activity)['budget_json']);doc['budget']['max_bytes']+=1
        self.s.db.execute('UPDATE activities SET budget_json=? WHERE id=?',(dumps(doc),self.activity))
        with self.assertRaises(Conflict):self.budget.check_activity(self.activity)

class PhysicalMeterTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_work import WorkTests
        self.base=WorkTests();self.base.setUp();self.addCleanup(self.base.doCleanups);self.s=self.base.s
    def meter(self,bytes=100000,scan=1000):
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
        return PhysicalReadMeter({'input_tokens':0,'output_tokens':0,'attempts':0,'tool_calls':0,'scan':scan,'items':scan,'bytes':bytes,'elapsed_ms':10000},utc(10))
    def test_m17_immutable_body_reused_only_within_one_measured_operation(self):
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        artifact=self.s.artifact({'body':'x'*5000});meter=self.meter();storage=ToolLearningStore(self.s)
        with meter.installed(self.s):
            storage.read_artifact(artifact);first=meter.actual['bytes'];storage.read_artifact(artifact)
        self.assertGreater(first,5000);self.assertGreater(meter.actual['bytes'],first)
        self.assertLess(meter.actual['bytes']-first,5000)
        next_meter=self.meter()
        with next_meter.installed(self.s):storage.read_artifact(artifact)
        self.assertGreater(next_meter.actual['bytes'],5000)
    def test_metadata_big_artifact_prechecked_no_hidden_body_read(self):
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        artifact=self.s.artifact({'body':'x'*10000});meter=self.meter(bytes=1000);storage=ToolLearningStore(self.s)
        with meter.installed(self.s):
            with self.assertRaises(Forbidden):storage.read_artifact(artifact)
        self.assertLess(meter.actual['bytes'],1000);self.assertFalse(meter.unknown_bytes)
    def test_cursor_fetchall_cannot_materialize_unbounded_rows(self):
        meter=self.meter(scan=2)
        with meter.installed(self.s):
            with self.assertRaises(Forbidden):self.s.db.execute('WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<1000) SELECT x FROM n').fetchall()
        self.assertEqual(meter.actual['scan'],2)
    def test_failed_artifact_bytes_remain_unknown(self):
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        artifact=self.s.artifact({'body':'not readable'});row=self.s.row('artifacts',artifact);(self.s.root/'blobs'/row['storage_ref']).unlink()
        meter=self.meter();storage=ToolLearningStore(self.s)
        with meter.installed(self.s):
            with self.assertRaises(ContractError):storage.read_artifact(artifact)
        self.assertIsNone(meter.usage());self.assertGreater(meter.actual['scan'],0)

class StrictEngineEndToEndTests(unittest.TestCase):
    enable_features=True
    def setUp(self):
        from tests.test_tool_learning_work import WorkTests
        from digital_life.application.runtime.configuration import configure_model
        from digital_life.application.learning.eligibility import ref
        from digital_life.infrastructure.llm.fresh_learning import FreshActionProvider
        from digital_life.domain.contracts import identifier
        self.base=WorkTests();self.base.setUp();self.addCleanup(self.base.doCleanups);self.s=self.base.s;self.control=self.base.f.control
        self.control.stop('synthetic strict config')
        caps={'max_input_tokens':200000,'max_output_tokens':200,'max_attempts':8,'max_tool_calls':8,'max_scan':2000000,'max_items':2000000,'max_bytes':512*1024*1024,'elapsed_ms':600000}
        policy=self.s.insert('policy_versions',version=101,mode='authorization',scope={'tool_learning_runtime':{'contract':'TL-STRICT-RUNTIME-1','enabled':True,'ordinary_activity_caps':caps}},effective_at=utc(),authority=self.s.config()['controller'])
        self.s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE instance_id=?',(policy,self.s.instance_id))
        if getattr(self,'enable_features',False):
            from digital_life.application.behavior.behavior_policy import BehaviorPolicy
            from digital_life.application.behavior.goal_regulation import GoalRegulation
            from digital_life.application.behavior.personality_growth import PersonalityGrowth
            from digital_life.application.behavior.habit_learning import HabitLearning
            from digital_life.application.behavior.people_relations import PeopleRelations
            from digital_life.application.memory.memory_quality import MemoryQuality
            from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
            from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
            actor=self.s.config()['controller']
            BehaviorPolicy(self.s).configure(True,actor);GoalRegulation(self.s).configure(True,actor,min_disk_bytes=0)
            for service in (PersonalityGrowth,HabitLearning,PeopleRelations,MemoryQuality,AutonomyAgenda,SelfMaintenance):service(self.s).configure(True,actor)
        configure_model(self.s,{'backend':'remote_chat','model':'synthetic-fixed','base_url':'https://synthetic.invalid','enabled':True,'context_window':262144,'max_output_tokens':200},self.s.config()['controller'],check_available=False)
        self.s.db.execute('PRAGMA user_version=4');self.control.resume('synthetic strict resume')
        deployment=self.control.insert('deployments',release='synthetic-im11-only',build_hash='synthetic-not-a-production-release',schema_min=4,schema_max=4,state='active')
        self.identity=self.control.begin_run(deployment);self.addCleanup(self.control.finish_run,self.identity)
        self.key=identifier();self.control.accept_inbound('strict-fixture-controller',self.key,{'text':'你好，我是liwei'},self.s.config()['controller'])
        from digital_life.application.runtime.engine import Engine
        self.activity=Engine(self.s,self.identity).submit('你好，我是liwei',self.key,'strict-fixture-controller')
        route={'configuration':ref(self.s,self.s.db.execute('SELECT * FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()['id']),'model':ref(self.s,self.s.db.execute('SELECT * FROM model_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()['id']),'provider':'remote_chat'}
        self.output={'schema_version':3,'action':{'tool':'wait','arguments':{'reason':'await next input'}},'explanation':'你好，liwei。','cognition':{'claims':[],'questions':[],'predictions':[],'plan':[]}}
        def transport(path,wire,*args):return {'model':'synthetic-fixed','choices':[{'finish_reason':'stop','message':{'content':json.dumps(self.output)}}],'usage':{'prompt_tokens':100,'completion_tokens':20}}
        class FixedChargeSyntheticCapability(SyntheticCapability):
            # This fake transport's declared accounting protocol charges exactly
            # 100 input tokens per independent call, regardless of JSON size.
            # This is not a tokenizer or capability attestation for a real LLM.
            def input_tokens(self,reasoner,wire):
                if reasoner.model!='synthetic-fixed':raise Forbidden('only the fixed-charge synthetic protocol is known')
                return 100
        provider=FreshActionProvider(configured_reasoner(self.s.config()['model']),route,FixedChargeSyntheticCapability(),transport)
        from digital_life.application.learning.engine import StrictEngine
        self.strict=StrictEngine(self.s,self.identity,provider)
    def test_ordinary_actual_engine_full_packet_and_real_original_account(self):
        from digital_life.application.runtime.engine import Engine
        from digital_life.application.services import Cognition
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(self.activity,)).fetchone()[0]
        for index in range(17):Cognition(self.s).episode(self.activity,context,'synthetic prior episode '+str(index))
        import time
        started=time.monotonic()
        try:result=Engine(self.s,self.identity,strict_runtime=self.strict).think(self.activity)
        finally:
            ledger=json.loads(self.s.row('activities',self.activity)['budget_json'])['ledger']['reservations']
            actuals=[r['actual'] for r in ledger.values() if r['actual'] is not None]
            print('STRICT_ENGINE_MEASUREMENTS '+json.dumps({'wall_seconds':round(time.monotonic()-started,3),'known_actual_scan':sum(r['scan'] for r in actuals),'known_actual_items':sum(r['items'] for r in actuals),'known_actual_bytes':sum(r['bytes'] for r in actuals),'known_actual_elapsed_ms':sum(r['elapsed_ms'] for r in actuals),'unknown_reservations':sum(r['state']=='usage_unknown' for r in ledger.values())}),flush=True)
        self.assertTrue(result['accepted'])
        request=self.s.row('thought_requests',result['request_id']);packet=self.s.read_artifact(request['request_artifact_id'])
        self.assertEqual(packet['request_id'],request['id']);self.assertEqual(packet['binding']['process_run_id'],self.identity.process_id)
        self.assertIn('personality',packet['input']['features']);self.assertIn('relationships',packet['input']['features']);self.assertIn('internal_state',packet['input']['features'])
        self.assertGreater(len(self.s.rows('tl_input_dependency')),5)
        doc=json.loads(self.s.row('activities',self.activity)['budget_json'])
        self.assertEqual(doc['contract'],'TL-ACTIVITY-BUDGET-1');self.assertEqual(sum(r['actual']['attempts'] for r in doc['ledger']['reservations'].values() if r['actual']),1)
        self.assertFalse(self.s.db.execute('SELECT id FROM tl_work WHERE learning_activity_id=?',(self.activity,)).fetchone())
        self.assertFalse(self.s.rows('cognition_beliefs'))


class StrictActualUseTests(unittest.TestCase):
    def setUp(self):
        fixture=StrictEngineEndToEndTests();fixture.enable_features=False;fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.f=fixture;self.s=fixture.s;self.activity=fixture.activity;self.k=fixture.strict;self.control=fixture.control
        (self.s.root/'controller.token').write_text('synthetic-isolated-controller-token')
    def producer(self,action=None):
        from digital_life.domain.contracts import identifier,sha,dumps
        from digital_life.application.learning.eligibility import ref
        from digital_life.application.learning.engine import source_scope,_dependency
        from digital_life.application.services import Decisions
        from digital_life.application.accounts.authorization import Policy
        c=__import__('digital_life.domain.tool_learning_contract',fromlist=['fingerprint'])
        action=action or {'tool':'write_note','arguments':{'path':'synthetic-note.txt','text':'controlled synthetic text'}}
        scope=source_scope(self.s);signal=self.s.row('activities',self.activity)['trigger_event_id'];primary={'object':ref(self.s,signal),'revision':0,'epoch':0}
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(self.activity,)).fetchone()[0]
        packet={'contract':'synthetic-manually-authored-fixture','input':{'task':'synthetic fixture'}};output=dict(self.f.output,action=action)
        with self.s.tx():
            step=self.s.insert('activity_steps',activity_id=self.activity,step_no=0,step_type='synthetic-explicit-producer',state='pending',attempt=0,idempotency_key=identifier())
            artifact=self.s.artifact(packet);response=self.s.artifact(output)
            request=self.s.insert('thought_requests',activity_id=self.activity,step_id=step,request_key=identifier(),purpose='plan',task='synthetic',instruction_version='synthetic-explicit-producer',output_schema_version=3,request_artifact_id=artifact,request_hash=c.fingerprint(packet),input_manifest_hash=c.fingerprint(packet),model_config_id=self.s.db.execute('SELECT * FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()['id'],model_version_id=self.s.db.execute('SELECT * FROM model_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(self.s.instance_id,)).fetchone()['id'],prepared_activity_revision=0,expected_input_epoch=0,expected_policy_epoch=self.s.rows('policy_epochs')[0]['epoch'],runtime_epoch=self.f.identity.epoch,process_run_id=self.f.identity.process_id,deadline=utc(300),token_budget=100,attempt_limit=1,retry_policy={'max_attempts':1},generation_config={},state='running')
            attempt=self.s.insert('thought_attempts',request_id=request,attempt_no=1,state='received',queued_at=utc(),dispatch_token=identifier(),provider='synthetic-no-model',model='synthetic',runtime_epoch=self.f.identity.epoch,process_run_id=self.f.identity.process_id)
            result=self.s.insert('thought_results',request_id=request,attempt_id=attempt,response_artifact_id=response,response_hash=c.fingerprint(output),received_at=utc(),parsed_artifact_id=response,validation_errors=[],validation_state='valid',acceptance='accepted',accepted_at=utc())
            self.s.db.execute("UPDATE thought_requests SET state='succeeded',accepted_result_id=? WHERE id=?",(result,request))
            for key in (request,artifact,result,response):
                for relation in ('read','delete'):_dependency(self.s,ref(self.s,key),primary,scope,relation,'/synthetic-explicit-source','learn')
            goal=self.s.db.execute('SELECT id FROM goal_items WHERE source_ref=?',(signal,)).fetchone()[0]
            decision=Decisions(self.s).finalize(self.activity,goal,context,[action])
            intent=Policy(self.s).propose(self.activity,decision['selected'],action);approval=Policy(self.s).request(intent)
            token={'object':ref(self.s,result),'revision':0,'epoch':0}
            for relation in ('read','delete'):_dependency(self.s,ref(self.s,intent),token,scope,relation,'/model_derivation','learn')
        Policy(self.s).approve(approval,self.s.config()['controller'])
        return request,result,intent,scope
    def reader(self):
        from digital_life.application.learning.controller_read import ControllerMaterialReader
        return ControllerMaterialReader(self.s,'Bearer '+(self.s.root/'controller.token').read_text().strip())
    def test_actual_executor_original_ledger_and_managed_workspace_side_effect(self):
        from digital_life.application.runtime.engine import Engine
        request,result,intent,scope=self.producer()
        outcome=Engine(self.s,self.f.identity,strict_runtime=self.k).execute(intent)
        self.assertEqual(outcome['state'],'succeeded')
        self.assertEqual((self.s.root/'workspace'/'synthetic-note.txt').read_text(),'controlled synthetic text')
        ledger=json.loads(self.s.row('activities',self.activity)['budget_json'])['ledger']
        tool=[r for r in ledger['reservations'].values() if r['kind']=='tool_attempt']
        self.assertEqual(len(tool),1);self.assertEqual(tool[0]['actual']['tool_calls'],1);self.assertEqual(tool[0]['actual']['attempts'],1)
        closure=self.k.runtime.eligibility.closure(self.s.row('activities',self.activity)['trigger_event_id'])
        self.assertIn(outcome['result'],closure);self.assertIn(outcome['receipt'],closure)
        self.assertTrue(Engine(self.s,self.f.identity,strict_runtime=self.k).execute(intent)['duplicate'])
    def test_entered_tool_failure_records_unknown_and_never_retries(self):
        from digital_life.application.runtime.execution import Executor
        request,result,intent,scope=self.producer()
        def fail(*args):raise OSError('synthetic unknown effect')
        with self.assertRaises(ContractError):Executor(self.s,self.f.identity).dispatch(intent,fail)
        self.assertEqual(self.s.row('action_intents',intent)['state'],'unknown')
        self.assertTrue(json.loads(self.s.row('activities',self.activity)['budget_json'])['ledger']['halted'])
        with self.assertRaises((Forbidden,Conflict)):Executor(self.s,self.f.identity).dispatch(intent,lambda *a:self.fail('must not retry'))
    def test_authenticated_history_stopped_and_locked_is_read_only(self):
        request,result,intent,scope=self.producer();reader=self.reader()
        self.control.stop('synthetic audit stopped');(self.s.root/'WAKE_DISABLED').write_text('synthetic audit lock')
        before=self.s.db.total_changes;events=len(self.s.rows('runtime_events'))
        detail=reader.thought(request)
        self.assertEqual(detail['results'][0]['parsed_output']['value']['explanation'],'你好，liwei。')
        self.assertEqual(self.s.db.total_changes,before);self.assertEqual(len(self.s.rows('runtime_events')),events)
        self.assertTrue((self.s.root/'WAKE_DISABLED').exists());self.assertTrue(self.control.state()['user_stopped'])
    def test_reader_cannot_pair_authorized_owner_with_unrelated_artifact(self):
        from digital_life.application.learning.eligibility import ref
        request,result,intent,scope=self.producer();unrelated=self.s.artifact({'secret':'not this request'})
        with self.assertRaises(Forbidden):self.reader().material(ref(self.s,request),unrelated)
    def test_controller_identity_does_not_override_private_memory_source_acl(self):
        from digital_life.application.services import Memory
        from digital_life.application.learning.engine import _dependency
        from digital_life.application.learning.eligibility import ref
        request,result,intent,scope=self.producer()
        private=self.s.insert('policy_versions',version=999,mode='authorization',scope={'memory_readers':[self.s.config()['self_actor']]},effective_at=utc(),authority=self.s.config()['controller'])
        memory=self.s.rows('memory_items')[0];self.s.db.execute('UPDATE memory_items SET access_policy_ref=? WHERE id=?',(private,memory['id']))
        token=self.k.owners.token(ref(self.s,memory['id']),scope)
        with self.s.tx():_dependency(self.s,ref(self.s,result),token,scope,'read','/synthetic-private-source','learn')
        with self.assertRaises(Forbidden):self.reader().thought(request)
        from digital_life.application.runtime.execution import Executor
        with self.assertRaises(Forbidden):Executor(self.s,self.f.identity).dispatch(intent,lambda *a:self.fail('must not send private source to this recipient'))



class StrictLearningFlowTests(unittest.TestCase):
    def setUp(self):
        fixture=StrictActualUseTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.f=fixture;self.s=fixture.s;self.k=fixture.k;self.activity=fixture.activity
        from digital_life.domain import tool_learning_contract as c
        active=self.s.rows('policy_epochs')[0];old=self.s.row('policy_versions',active['policy_version_id']);scope=c.loads(old['scope'])
        scope['tool_learning_acceptance']={'contract':'TL-ACCEPT-REVIEW-1','content_kinds':['source_report'],'proposal_operations':['add'],'require_controller_review':True,'expires_at':utc(3600)}
        policy=self.s.insert('policy_versions',version=102,mode='authorization',scope=scope,effective_at=utc(-1),authority=self.s.config()['controller'])
        self.s.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE instance_id=?',(policy,self.s.instance_id))
        from digital_life.application.learning.runtime_learning import StrictLearningCoordinator
        from digital_life.infrastructure.llm.fresh_learning import FreshLearningProvider
        provider,route,reasoner=self.k._route()
        def transport(path,wire,*args):return {'model':'synthetic-fixed','choices':[{'finish_reason':'stop','message':{'content':json.dumps(BODY)}}],'usage':{'prompt_tokens':100,'completion_tokens':20}}
        self.provider=FreshLearningProvider(reasoner,route,SyntheticCapability(),transport)
        self.r=StrictLearningCoordinator(self.k,self.provider)
    def observe(self,interpret=False):
        signal=self.s.row('activities',self.activity)['trigger_event_id']
        work=self.r.admit(self.activity,signal,{'kind':'json_pointer','pointer':'/text'},interpret=interpret)
        response=self.r.assess(work['id'])
        proposal=self.s.db.execute("SELECT * FROM tl_product WHERE instance_id=? AND work_id=? AND product_type='UpdateProposal'",(self.s.instance_id,work['id'])).fetchone()
        self.assertIsNotNone(proposal)
        return work,dict(proposal)
    def review(self,proposal):
        from digital_life.application.learning.runtime import ControllerReviewAuthor
        from digital_life.application.learning.eligibility import ref
        from digital_life.domain import tool_learning_contract as c
        body=self.s.read_artifact(proposal['payload_artifact_id']);policy=self.s.rows('policy_epochs')[0]['policy_version_id']
        review={'contract':'TL-CONTROLLER-CONTENT-REVIEW-1','proposal':ref(self.s,proposal['id']),'proposal_digest':c.fingerprint(body),'review_round':0,'expected':deepcopy(body['body']['target']['expected']),'native_expected':slot(),'actual_scope':deepcopy(body['body']['claims'][0]['scope']),'policy':ref(self.s,policy),'atomic_group':slot(),'verdict':'accept','expires_at':utc(120)}
        return ControllerReviewAuthor(self.s).author('Bearer synthetic-isolated-controller-token',review)['review']
    def test_native_all_four_products_without_review_stay_candidate(self):
        work,proposal=self.observe()
        self.assertEqual(len(self.s.rows('tl_product')),4)
        decision_response=self.r.decide(proposal['id'])
        decision=self.s.row('tl_decision',decision_response['result_refs'][0]['id'])
        self.assertEqual(decision['operation'],'candidate');self.assertFalse(self.s.rows('tl_handoff'))
        gain=self.s.db.execute("SELECT payload_artifact_id FROM tl_product WHERE product_type='EffectAssessment'").fetchone()[0]
        self.assertEqual(self.s.read_artifact(gain)['body']['gain']['status'],'not_collected')
        self.assertFalse(self.s.rows('cognition_beliefs'))
    def test_real_process_source_to_authenticated_c1_and_c2(self):
        work,proposal=self.observe(interpret=True);review=self.review(proposal)
        response=self.r.decide(proposal['id'],review)
        decision=self.s.row('tl_decision',response['result_refs'][0]['id']);self.assertEqual(decision['operation'],'accept')
        handoff=self.s.db.execute('SELECT id FROM tl_handoff WHERE instance_id=? AND work_id=?',(self.s.instance_id,work['id'])).fetchone()[0]
        published=self.r.publish(handoff)
        self.assertEqual(published['operation'],'publish_representation')
        self.assertEqual(self.s.row('tl_handoff',handoff)['state'],'published')
        self.assertEqual(self.s.rows('tl_representation')[0]['state'],'ready')
        doc=json.loads(self.s.row('activities',self.s.row('tl_work',work['id'])['learning_activity_id'])['budget_json'])
        self.assertEqual(sum(r['actual']['attempts'] for r in doc['ledger']['reservations'].values() if r['actual']),1)
        self.assertTrue(all(r['state']=='settled' for r in doc['ledger']['reservations'].values()))



class StaticControlTokenTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_work import WorkTests
        self.f=WorkTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        self.storage=ToolLearningStore(self.s)
    def token(self,kind):
        from digital_life.application.learning.eligibility import ref
        row=self.s.rows(kind)[0]
        return {'object':ref(self.s,row['id'],kind),'revision':0,'epoch':0}
    def walk(self,token):return self.storage._ToolLearningStore__walk_refs(token)
    def test_real_static_control_payloads_have_technical_zero_without_fake_registry(self):
        for kind in ('configuration_versions','model_versions','policy_versions','perception_signals'):
            token=self.token(kind);before=self.s.db.total_changes;self.walk(token)
            self.assertEqual(self.s.db.total_changes,before)
            known=deepcopy(token['object']);known['revision']=slot(0)
            with self.assertRaises(Conflict):self.storage.validate_ref(known)
    def test_wrong_kind_missing_owner_and_unapproved_mutable_zero_rejected(self):
        token=self.token('configuration_versions');token['object']['kind']='policy_versions'
        with self.assertRaises(ContractError):self.walk(token)
        token=self.token('configuration_versions');token['object']['id']='f'*32
        with self.assertRaises(ContractError):self.walk(token)
        token=self.token('activities')
        with self.assertRaises(Conflict):self.walk(token)
    def test_real_artifact_wrong_embedded_digest_rejected(self):
        token=self.token('configuration_versions');self.s.db.execute('UPDATE configuration_versions SET hash=? WHERE id=?',('0'*64,token['object']['id']))
        with self.assertRaises(Conflict):self.walk(token)
    def test_conflicting_registry_and_native_source_cannot_fall_back_to_zero(self):
        token=self.token('configuration_versions');origin=token['object']
        from digital_life.domain.contracts import identifier
        self.s.insert('object_revision_registry',id=origin['id'],object_id=origin['id'],revision_no=1,kind='configuration_versions')
        with self.assertRaises(Conflict):self.walk(token)
        token=self.token('memory_items')
        with self.assertRaises(Conflict):self.walk(token)



class RollbackBlobTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_work import WorkTests
        self.f=WorkTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
    def test_only_new_unregistered_blob_is_removed_shared_committed_body_survives(self):
        from digital_life.domain.contracts import sha,dumps
        old=self.s.artifact({'shared':'old committed'});old_path=self.s.root/'blobs'/self.s.row('artifacts',old)['storage_ref']
        target=sha(dumps({'private':'failed local new body'}))
        with self.assertRaises(OSError):
            with self.s.tx():self.s.artifact({'shared':'old committed'});self.s.artifact({'private':'failed local new body'});raise OSError('synthetic rollback')
        self.assertTrue(old_path.is_file());self.assertFalse((self.s.root/'blobs'/target).exists())
        self.assertEqual(self.s.read_artifact(old),{'shared':'old committed'})
    def test_nested_commit_file_is_owned_by_outer_rollback(self):
        from digital_life.domain.contracts import sha,dumps
        target=sha(dumps({'private':'nested body'}))
        with self.assertRaises(OSError):
            with self.s.tx():
                with self.s.tx():self.s.artifact({'private':'nested body'})
                raise OSError('outer rollback')
        self.assertFalse((self.s.root/'blobs'/target).exists())
    def test_symbolic_replacement_never_deletes_or_reads_unrelated_target(self):
        unrelated=self.s.root/'workspace'/'unrelated';unrelated.write_text('synthetic keep')
        with self.assertRaises(OSError):
            with self.s.tx():
                artifact=self.s.artifact({'private':'new owned file'});path=self.s.root/'blobs'/self.s.row('artifacts',artifact)['storage_ref']
                path.unlink();path.symlink_to(unrelated);raise OSError('rollback with replaced path')
        self.assertTrue(path.is_symlink());self.assertEqual(unrelated.read_text(),'synthetic keep')
    def test_commit_acknowledgement_unknown_preserves_actual_registered_files(self):
        from tests.test_tool_learning_invalidation import F1Tests
        from digital_life.infrastructure.persistence.tool_learning_store import CommitUnknown
        from unittest.mock import patch
        case=F1Tests();case.setUp();self.addCleanup(case.doCleanups);original=case.service.storage._commit
        def lost():original();raise OSError('synthetic lost commit acknowledgement')
        with patch.object(case.service.storage,'_commit',lost):
            with self.assertRaises(CommitUnknown):case.apply()
        self.assertTrue(case.s.rows('tl_change'))
        for row in case.s.rows('artifacts'):self.assertTrue((case.s.root/'blobs'/row['storage_ref']).is_file())

class CurrentHealthGuardTests(unittest.TestCase):
    def setUp(self):
        case=StrictActualUseTests();case.setUp();self.addCleanup(case.doCleanups);self.s=case.s;self.activity=case.activity
        from digital_life.application.learning.health import REQUIRED
        from digital_life.application.services import States
        evidence=self.s.evidence(object_id=self.s.row('activities',self.activity)['trigger_event_id'],method='synthetic old health measurement')
        for name in REQUIRED:States(self.s).observe(name,1,'synthetic unit',evidence,ttl=30)
        self.s.db.execute('UPDATE state_observations SET observed_at=? WHERE instance_id=?',(utc(-40),self.s.instance_id))
    def assess(self):
        from digital_life.application.behavior.goal_regulation import GoalRegulation
        from digital_life.application.learning.health import CurrentHealthEvidence
        evidence=CurrentHealthEvidence(self.s,self.activity,None)
        return GoalRegulation(self.s).assess(self.activity,0,0,current_health=evidence),evidence
    def test_expired_input_observation_is_not_relabelled_but_current_readonly_probe_allows(self):
        from digital_life.application.behavior.goal_regulation import GoalRegulation
        before=self.s.rows('state_observations');definitions=self.s.rows('state_definitions');changes=self.s.db.total_changes
        self.assertFalse(GoalRegulation(self.s).assess(self.activity,0,0)['eligible'])
        result,evidence=self.assess();self.assertTrue(result['eligible']);self.assertEqual(set(evidence.probes),{'R.disk_free_bytes','F.sqlite_integrity','F.restore_reconciliation_required','W.queue_depth'})
        self.assertEqual(self.s.rows('state_observations'),before);self.assertEqual(self.s.rows('state_definitions'),definitions);self.assertEqual(self.s.db.total_changes,changes)
    def test_current_disk_sqlite_and_restore_failure_each_blocks(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        with patch('digital_life.application.learning.health.shutil.disk_usage',return_value=SimpleNamespace(free=0)):self.assertFalse(self.assess()[0]['eligible'])
        with patch.object(self.s,'integrity',return_value={'integrity':'bad','foreign_keys':[]}):self.assertFalse(self.assess()[0]['eligible'])
        (self.s.root/'RESTORE_RECONCILIATION_REQUIRED').write_text('synthetic changed after preparation')
        self.assertFalse(self.assess()[0]['eligible'])
    def test_unknown_queue_probe_and_unmeasured_disk_never_become_zero(self):
        from unittest.mock import patch
        from digital_life.application.learning.health import CurrentHealthEvidence
        import sqlite3
        actual=self.s.db
        class Proxy:
            def __getattr__(self,name):return getattr(actual,name)
            def execute(self,sql,*args):
                if sql.startswith('SELECT count(*) FROM jobs'):raise sqlite3.OperationalError('synthetic unconfirmed queue')
                return actual.execute(sql,*args)
        self.s.db=Proxy()
        try:
            evidence=CurrentHealthEvidence(self.s,self.activity,None)
            self.assertEqual(evidence.probes['W.queue_depth']['status'],'unknown')
            with self.assertRaises(Forbidden):evidence.consume(self.s,self.activity)
        finally:self.s.db=actual
        with patch('digital_life.application.learning.health.shutil.disk_usage',side_effect=OSError('synthetic unknown')):
            with self.assertRaises(Forbidden):self.assess()



class StrictControllerSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.case=StrictActualUseTests();self.case.setUp();self.addCleanup(self.case.doCleanups);self.s=self.case.s
        from digital_life.entrypoints.http import Application
        self.app=Application(self.s.root);self.bearer='Bearer synthetic-isolated-controller-token'
    def call(self,method,path,body=None,bearer=True):return self.app.dispatch(method,path,body,controller_bearer=self.bearer if bearer else None)
    def test_real_controller_panels_and_stopped_reads_do_not_write_or_wake(self):
        request,result,intent,scope=self.case.producer()
        self.case.control.stop('synthetic stopped audit');(self.s.root/'WAKE_DISABLED').write_text('synthetic lock')
        before=len(self.s.rows('runtime_events'));changes=self.s.db.total_changes
        for path in ('/v1/overview','/v1/activities','/v1/activities/'+self.case.activity,'/v1/model/configuration','/v1/health','/v1/approvals','/v1/thoughts/'+request,'/v1/logs'):
            code,value=self.call('GET',path);self.assertEqual(code,200,path)
        self.assertEqual(len(self.s.rows('runtime_events')),before);self.assertEqual(self.s.db.total_changes,changes)
        self.assertTrue(self.case.control.state()['user_stopped']);self.assertTrue((self.s.root/'WAKE_DISABLED').exists())
        with self.assertRaises(Forbidden):self.call('GET','/v1/overview',bearer=False)
    def test_chat_admission_requires_real_bearer_and_preserves_actual_predecessor(self):
        with self.assertRaises(Forbidden):self.call('POST','/v1/chats/new-thread/messages',{'text':'Bob is my friend','idempotency_key':'first','expected_last_activity_id':None},bearer=False)
        code,first=self.call('POST','/v1/chats/new-thread/messages',{'text':'Bob is my friend','idempotency_key':'first','expected_last_activity_id':None});self.assertEqual(code,202)
        self.assertFalse(first['inference_started'])
        self.s.db.execute("UPDATE activities SET state='waiting_input' WHERE id=?",(first['activity_id'],))
        code,second=self.call('POST','/v1/chats/new-thread/messages',{'text':'What about him?','idempotency_key':'second','expected_last_activity_id':first['activity_id']})
        self.assertEqual(code,202);self.assertEqual(self.s.row('activities',second['activity_id'])['predecessor_activity_id'],first['activity_id'])
        from digital_life.application.learning.engine import source_scope
        entry,principal=self.case.k.owners.entry('M14','learn',self.s.config()['controller']);scope=source_scope(self.s)
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(second['activity_id'],)).fetchone()[0]
        primary=self.case.k.owners.token(__import__('digital_life.application.learning.eligibility',fromlist=['ref']).ref(self.s,self.s.row('activities',second['activity_id'])['trigger_event_id']),scope)
        quoted=self.case.k._conversation(entry,principal,second['activity_id'],context,primary,scope)
        self.assertTrue(any('Bob is my friend' in item['text'] for item in quoted['messages']))
        self.assertEqual(quoted['authority'],'bounded quoted historical reports; no provider session')
    def test_strict_codex_test_cannot_bypass_unverified_inference_capability(self):
        code,value=self.call('POST','/v1/codex/test',{})
        self.assertEqual(code,200);self.assertFalse(value['inference_executed']);self.assertFalse(value['available'])


if __name__=='__main__':unittest.main()

class InternalAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.f=StrictEngineEndToEndTests();self.f.enable_features=False;self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
        self.s.db.execute("UPDATE activities SET state='cancelled'")
    def test_genuine_exploration_config_creates_one_self_intent_original_account(self):
        from digital_life.application.autonomy.exploration import Exploration
        from digital_life.application.learning.admission import InternalAdmission
        x=Exploration(self.s);x.configure(self.s.config()['controller'],True,max_activities=1,max_rounds=2)
        service=InternalAdmission(self.f.strict);activity=service.tick();self.assertIsNotNone(activity)
        signal=self.s.row('perception_signals',self.s.row('activities',activity)['trigger_event_id'])
        self.assertEqual(signal['source_actor_id'],self.s.config()['self_actor']);self.assertEqual(x.binding(activity)['generation'],x.config()['generation'])
        ledger=json.loads(self.s.row('activities',activity)['budget_json']);self.assertEqual(ledger['contract'],'TL-ACTIVITY-BUDGET-1');self.assertEqual(ledger['budget']['max_tool_calls'],2)
        self.s.db.execute("UPDATE activities SET state='cancelled' WHERE id=?",(activity,));self.assertIsNone(service.tick())
    def test_disabled_and_held_original_opportunity_prevent_new_activity(self):
        from digital_life.application.learning.admission import InternalAdmission
        from digital_life.application.autonomy.exploration import Exploration
        admission=InternalAdmission(self.f.strict);self.assertIsNone(admission.tick())
        Exploration(self.s).configure(self.s.config()['controller'],True)
        doc=json.loads(self.s.row('activities',self.f.activity)['budget_json']);doc['ledger']['reservations']['synthetic']={'state':'usage_unknown'}
        self.s.db.execute('UPDATE activities SET budget_json=? WHERE id=?',(json.dumps(doc),self.f.activity));self.assertIsNone(admission.tick())
    def test_strict_process_one_never_calls_legacy_ticks_or_state_claim(self):
        from unittest.mock import patch
        from digital_life.application.runtime.engine import Engine
        with patch('digital_life.application.autonomy.autonomy_agenda.AutonomyAgenda.tick',side_effect=AssertionError('legacy agenda')),patch('digital_life.application.autonomy.exploration.Exploration.tick',side_effect=AssertionError('legacy exploration')),patch('digital_life.application.behavior.goal_regulation.GoalRegulation.claim',side_effect=AssertionError('legacy StateCollector')):
            self.s.db.execute("UPDATE jobs SET state='cancelled'");self.assertIsNone(Engine(self.s,self.f.identity,strict_runtime=self.f.strict).process_one())

    def test_real_agenda_promise_admits_bound_task_without_controller_impersonation(self):
        from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
        from digital_life.application.learning.engine import StrictEngine
        from digital_life.application.learning.admission import InternalAdmission
        control=self.f.control;control.finish_run(self.f.identity);control.stop('synthetic configure')
        agenda=AutonomyAgenda(self.s);agenda.configure(True,self.s.config()['controller'])
        promise=agenda.promise('write the promised note',utc(-1),utc(300),{'kind':'file_contains','path':'promise.txt','text':'done'},'genuine-promise',self.s.config()['controller'])
        control.resume('synthetic resume');deployment=control.db.execute('SELECT deployment_id FROM process_runs WHERE id=?',(self.f.identity.process_id,)).fetchone()[0]
        identity=control.begin_run(deployment);self.addCleanup(control.finish_run,identity);strict=StrictEngine(self.s,identity,self.f.strict.provider)
        activity=InternalAdmission(strict).tick();self.assertEqual(agenda.bound(promise['commitment'])['activity'],activity)
        signal=self.s.row('perception_signals',self.s.row('activities',activity)['trigger_event_id']);self.assertEqual(signal['source_actor_id'],self.s.config()['self_actor'])
        self.assertEqual(self.s.read_artifact(signal['artifact_id']),{'text':'write the promised note'})
        self.assertLessEqual(self.s.row('activities',activity)['deadline'],promise['spec']['due_at'])
    def test_wrong_module_and_task_hash_are_not_runtime_admission(self):
        from digital_life.application.learning.admission import InternalAdmission
        from digital_life.application.learning.engine import active_profile
        from digital_life.application.autonomy.exploration import Exploration
        x=Exploration(self.s);x.configure(self.s.config()['controller'],True);cfg=x.config();epoch,policy,caps=active_profile(self.s)
        admission=InternalAdmission(self.f.strict)
        for module in ('fake-module','exploration'):
            with self.assertRaises(Forbidden):admission._admit(module,'forged task',cfg['generation']+':0',cfg['generation'],caps,epoch,policy)

class FixedChargeAndByteSliceTests(unittest.TestCase):
    def test_fixed_synthetic_protocol_refuses_below_100_before_transport(self):
        helper=FreshProviderTests();packet=helper.packet('remote_chat');calls=[]
        class Fixed(FreshCapability):
            def verify(self,*args):return None
            def input_tokens(self,*args):return 100
        def send(path,wire,*args):
            calls.append(wire);return {'model':'synthetic-fixed','choices':[{'finish_reason':'stop','message':{'content':json.dumps(BODY)}}],'usage':{'prompt_tokens':100,'completion_tokens':20}}
        port=FreshLearningProvider(helper.reasoner('remote_chat'),helper.route,Fixed(),send)
        packet['limits']['max_input_tokens']=99
        with self.assertRaises(Forbidden):port.generate_fresh(packet)
        self.assertEqual(calls,[]);self.assertFalse(port.last_transport_entered)
        packet['limits']['max_input_tokens']=100
        result=port.generate_fresh(packet);self.assertEqual(result['usage']['input_tokens'],100);self.assertEqual(result['usage']['output_tokens'],20)
    def test_actual_byte_slice_only_tightens_fixed_packet_and_never_sends_when_too_small(self):
        helper=FreshProviderTests();port,packet=helper.port('remote_chat',lambda *args:(_ for _ in ()).throw(AssertionError('transport entered')))
        original=deepcopy(packet)
        with self.assertRaises(Forbidden):port.generate_fresh(packet,execution_max_bytes=1)
        self.assertEqual(packet,original);self.assertFalse(port.last_transport_entered)

class ActualReadTakeoverTests(unittest.TestCase):
    def setUp(self):
        self.f=StrictLearningFlowTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.r=self.f.r;self.s=self.f.s
        signal=self.s.row('activities',self.f.activity)['trigger_event_id'];self.work=self.r.admit(self.f.activity,signal,{'kind':'json_pointer','pointer':'/text'},interpret=False)
    def test_actual_context_is_exact_work_run_single_use_and_no_double_read_reservation(self):
        entry,principal=self.r.o.entry('M14','learn',self.s.config()['controller'])
        with self.r.read_stage(entry,work_id=self.work['id'],fraction=.45):
            entry,request=self.r.assessment_request(self.work['id'],entry);self.r.bind_stage_request(entry,request)
            owner=self.r.observation.authority;work=self.s.row('tl_work',self.work['id']);context=owner.read_operation_context(entry,request,work)
            wrong=deepcopy(context);wrong['reservation_id']='not-the-real-run'
            with self.assertRaises(Forbidden):owner.verify_read_operation_context(entry,request,work,wrong)
            self.assertIsNone(owner.verify_read_operation_context(entry,request,work,context))
            with self.assertRaises(Forbidden):owner.verify_read_operation_context(entry,request,work,context)
            forged=deepcopy(request);forged['work_ref']['value']['id']='other-work'
            with self.assertRaises((Forbidden,Conflict)):self.r.stage_context(entry,forged)
        doc=self.r.budget._load(self.work['id'])[3]
        self.assertEqual(len(doc['ledger']['reservations']),1);self.assertEqual(next(iter(doc['ledger']['reservations'].values()))['state'],'settled')
        with self.assertRaises(Forbidden):owner.read_operation_context(entry,request,work)
    def test_unbound_or_different_account_cannot_take_over_physical_meter(self):
        entry,principal=self.r.o.entry('M14','learn',self.s.config()['controller'])
        with self.r.read_stage(entry,work_id=self.work['id'],fraction=.45):
            entry,request=self.r.assessment_request(self.work['id'],entry)
            with self.assertRaises(Forbidden):self.r.stage_context(entry,request)
            wrong=deepcopy(request);wrong['budget']['account_ref']['id']='other-account'
            with self.assertRaises(Conflict):self.r.bind_stage_request(entry,wrong)
            self.r.bind_stage_request(entry,request)
            with self.assertRaises(Forbidden):self.r.bind_stage_request(entry,request)

class StrictRoundSelectionTests(unittest.TestCase):
    def setUp(self):
        self.f=StrictActualUseTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
    def test_old_success_is_not_selected_for_new_input_epoch(self):
        from unittest.mock import patch
        request,_,_,_=self.f.producer()
        self.s.db.execute("UPDATE thought_requests SET instruction_version='strict-complete-packet-1' WHERE id=?",(request,))
        self.s.db.execute("UPDATE activities SET state='running',input_epoch=input_epoch+1 WHERE id=?",(self.f.activity,))
        class NewRoundReached(Exception):pass
        with patch.object(self.f.k,'_features',side_effect=NewRoundReached('new independent round, not prior success')):
            with self.assertRaises(NewRoundReached):self.f.k.prepare(self.f.activity)
        self.assertEqual(self.s.row('thought_requests',request)['expected_input_epoch'],0)

class HousekeepingOpportunityTests(unittest.TestCase):
    def setUp(self):
        self.f=InternalAdmissionTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s;self.strict=self.f.f.strict
    def reserved(self):return self.s.db.execute("SELECT count(*) FROM runtime_events WHERE source='strict.housekeeping.reserved'").fetchone()[0]
    def test_empty_ticks_clock_rollback_and_new_process_do_not_renew_cycle(self):
        from digital_life.application.learning.admission import InternalAdmission
        from digital_life.application.learning.engine import StrictEngine
        from unittest.mock import patch
        admission=InternalAdmission(self.strict)
        with patch('digital_life.application.autonomy.autonomy_agenda.AutonomyAgenda.events',side_effect=AssertionError('disabled module historical scan')):self.assertIsNone(admission.tick())
        self.assertEqual(self.reserved(),1);self.assertIsNone(admission.tick());self.assertEqual(self.reserved(),1)
        real_utc=utc
        with patch('digital_life.application.learning.admission.utc',side_effect=lambda offset=0:real_utc(-120+offset)):
            self.assertIsNone(InternalAdmission(self.strict).tick())
        control=self.f.f.control;identity=self.f.f.identity;deployment=control.db.execute('SELECT deployment_id FROM process_runs WHERE id=?',(identity.process_id,)).fetchone()[0]
        control.finish_run(identity);new=control.begin_run(deployment);self.addCleanup(control.finish_run,new)
        self.assertIsNone(InternalAdmission(StrictEngine(self.s,new,self.strict.provider)).tick());self.assertEqual(self.reserved(),1)
        settled=self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='strict.housekeeping.settled'").fetchone()
        value=self.s.read_artifact(settled[0]);self.assertGreater(value['actual']['scan'],0);self.assertGreater(value['actual']['bytes'],0);self.assertGreaterEqual(value['actual']['elapsed_ms'],1)
    def test_unsettled_opportunity_survives_new_owner_and_unknown_artifact_denies(self):
        from digital_life.application.learning.admission import InternalAdmission
        from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
        self.s.event('strict.housekeeping.reserved',payload={'synthetic':'interrupted actual opportunity'},source='strict.housekeeping.reserved')
        self.assertIsNone(InternalAdmission(self.strict).tick());self.assertEqual(self.reserved(),1)
        artifact=self.s.artifact({'private':'unmapped bytes must not be read'})
        with dispatch_gate(self.s.root),self.s.tx(),InternalAdmission(self.strict)._source_reads():
            with self.assertRaises(Forbidden):self.s.read_artifact(artifact)

class FreshExecutionDeadlineTests(unittest.TestCase):
    def test_current_source_guard_consumes_the_same_configured_total_time_opportunity(self):
        helper=FreshProviderTests();port,packet=helper.port('remote_chat',lambda *args:(_ for _ in ()).throw(AssertionError('expired call must not enter transport')))
        port.reasoner.timeout=.02
        with self.assertRaises(Forbidden):port.generate_fresh(packet,execution_timeout_ms=1000,before_transport=lambda:time.sleep(.03))
        self.assertFalse(port.last_transport_entered)

class IndependentVerifierReadMeterTests(unittest.TestCase):
    def setUp(self):
        self.f=StrictActualUseTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
        from digital_life.application.autonomy.task_loop import TaskLoop
        self.path=self.s.root/'workspace'/'verified.txt';self.path.parent.mkdir(exist_ok=True);self.path.write_text('target '+('x'*2000))
        self.loop=TaskLoop(self.s);self.loop.configure(self.f.activity,{'kind':'file_contains','path':'verified.txt','text':'target'},self.s.config()['controller'])
    def meter(self,bytes_limit):
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
        return PhysicalReadMeter({'input_tokens':0,'output_tokens':0,'attempts':0,'tool_calls':0,'scan':10000,'items':10000,'bytes':bytes_limit,'elapsed_ms':5000},utc(5))
    def test_real_verifier_bytes_count_and_original_slice_blocks_before_file_read(self):
        from pathlib import Path
        from unittest.mock import patch
        meter=self.meter(1000000)
        with meter.installed(self.s):self.assertTrue(self.loop.verify(self.f.activity)['passed'])
        raw_size=self.path.stat().st_size;self.assertGreaterEqual(meter.usage()['bytes'],raw_size);self.assertGreater(meter.usage()['scan'],0)
        smaller=self.meter(meter.usage()['bytes']-raw_size//2);opened=[];original=Path.open
        def tracked(path,*args,**kwargs):
            if path==self.path:opened.append(True)
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',tracked),smaller.installed(self.s):
            with self.assertRaises(Forbidden):self.loop.verify(self.f.activity)
        self.assertEqual(opened,[])

class StrictProtectiveControllerTests(unittest.TestCase):
    def setUp(self):
        self.f=StrictControllerSurfaceTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
    def test_bearer_can_cancel_original_activity_without_reading_private_body_or_waking(self):
        activity=self.f.case.activity;revision=self.s.row('activities',activity)['revision']
        with self.assertRaises(Forbidden):self.f.call('POST','/v1/activities/'+activity+'/cancel',{'expected_revision':revision},bearer=False)
        self.f.case.control.stop('synthetic protective cancellation');(self.s.root/'WAKE_DISABLED').write_text('synthetic lock')
        code,result=self.f.call('POST','/v1/activities/'+activity+'/cancel',{'expected_revision':revision})
        self.assertEqual(code,200);self.assertFalse(result['runtime_started']);self.assertEqual(self.s.row('activities',activity)['state'],'cancelled');self.assertTrue((self.s.root/'WAKE_DISABLED').exists());self.assertTrue(self.f.case.control.state()['user_stopped'])
    def test_log_export_uses_the_same_current_source_filtered_reader(self):
        self.f.case.producer()
        code,regular=self.f.call('GET','/v1/logs');other,exported=self.f.call('GET','/v1/logs/export')
        self.assertEqual((code,other),(200,200));self.assertEqual(regular,exported)

class CrossInstanceRollbackBlobTests(unittest.TestCase):
    def setUp(self):
        self.f=RollbackBlobTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
    def test_b_recreating_missing_inode_then_rollback_preserves_actual_a_reference(self):
        from digital_life.domain.contracts import identifier
        original_instance=self.s.instance_id;body={'shared':'actual A reference, B rolls back'}
        artifact=self.s.artifact(body);path=self.s.root/'blobs'/self.s.row('artifacts',artifact)['storage_ref'];path.unlink()
        second=identifier()
        with self.s.tx():self.s.insert('identity_instances',id=second,instance_id=second,state='active',generation=0)
        self.s.instance_id=second
        try:
            with self.assertRaises(OSError):
                with self.s.tx():self.s.artifact(body);raise OSError('synthetic B rollback after new inode')
            self.assertFalse(self.s.db.execute('SELECT id FROM artifacts WHERE instance_id=?',(second,)).fetchone())
        finally:self.s.instance_id=original_instance
        self.assertTrue(path.is_file());self.assertEqual(self.s.read_artifact(artifact),body);self.assertEqual(self.s.integrity()['integrity'],'ok')
    def test_nested_rollback_is_reconciled_after_outer_success_not_while_writer_held(self):
        from digital_life.domain.contracts import dumps,sha
        body={'private':'rolled back inner body, successful outer metadata'};path=self.s.root/'blobs'/sha(dumps(body))
        with self.s.tx():
            with self.assertRaises(OSError):
                with self.s.tx():self.s.artifact(body);raise OSError('inner rollback')
            self.assertTrue(path.exists())
            self.s.event('synthetic.outer.survives',payload={'kept':True})
        self.assertFalse(path.exists())

    def test_new_reference_cannot_commit_between_fresh_no_reference_check_and_unlink(self):
        from digital_life.infrastructure.persistence.sqlite_store import Store
        from digital_life.domain.contracts import dumps,sha
        import threading
        body={'shared':'concurrent writer must restore or preserve its registered blob'};raw=dumps(body).encode();name=sha(raw);path=self.s.root/'blobs'/name;path.write_bytes(raw);st=path.stat()
        checked=threading.Event();attempting=threading.Event();committed=threading.Event();errors=[];result=[];actual=self.s.db
        def writer():
            other=None
            try:
                checked.wait(3);other=Store(self.s.root);original=other.insert
                def insert(table,**fields):
                    if table=='artifacts':attempting.set()
                    return original(table,**fields)
                other.insert=insert;key=other.artifact(body);result.append(other.read_artifact(key));committed.set()
            except BaseException as error:errors.append(error)
            finally:
                if other:other.close()
        thread=threading.Thread(target=writer);thread.start()
        class Cursor:
            def __init__(self,cursor):self.cursor=cursor
            def fetchone(inner):
                row=inner.cursor.fetchone();checked.set()
                if not attempting.wait(3):raise AssertionError('concurrent writer did not reach its real INSERT')
                self.assertFalse(committed.is_set());return row
        class Proxy:
            def __init__(self):self.actual=actual
            def __getattr__(self,key):return getattr(actual,key)
            def execute(self,sql,*args):
                cursor=actual.execute(sql,*args)
                return Cursor(cursor) if sql.startswith('SELECT 1 FROM artifacts WHERE storage_ref=') else cursor
        self.s.db=Proxy()
        try:self.s._discard_unregistered_blobs([(name,st.st_dev,st.st_ino)])
        finally:self.s.db=actual;checked.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[]);self.assertEqual(result,[body]);self.assertTrue(committed.is_set());self.assertTrue(path.is_file())
        # The old transaction's inode proof cannot unlink this writer's inode.
        self.s._discard_unregistered_blobs([(name,st.st_dev,st.st_ino)]);self.assertTrue(path.is_file())

    def test_reference_database_error_and_replaced_regular_inode_are_preserved(self):
        import sqlite3
        from digital_life.domain.contracts import dumps,sha
        body={'private':'new unregistered inode'};raw=dumps(body).encode();name=sha(raw);path=self.s.root/'blobs'/name;path.write_bytes(raw);st=path.stat();actual=self.s.db
        class Broken:
            def __init__(self):self.actual=actual
            def __getattr__(self,key):return getattr(actual,key)
            def execute(self,sql,*args):
                if sql.startswith('SELECT 1 FROM artifacts WHERE storage_ref='):raise sqlite3.OperationalError('synthetic reference status unknown')
                return actual.execute(sql,*args)
        self.s.db=Broken()
        try:self.s._discard_unregistered_blobs([(name,st.st_dev,st.st_ino)])
        finally:self.s.db=actual
        self.assertTrue(path.is_file());self.assertFalse(actual.in_transaction)
        with path.open('rb') as held_original:
            path.unlink();path.write_text('replacement belongs to another writer')
            self.assertNotEqual(path.stat().st_ino,st.st_ino)
            self.s._discard_unregistered_blobs([(name,st.st_dev,st.st_ino)])
            self.assertEqual(path.read_text(),'replacement belongs to another writer')

    def test_gate_failure_and_generic_store_commit_acknowledgement_unknown_keep_blobs(self):
        from digital_life.domain.contracts import dumps,sha
        from unittest.mock import patch
        body={'private':'gate status unknown'};raw=dumps(body).encode();name=sha(raw);path=self.s.root/'blobs'/name;path.write_bytes(raw);st=path.stat()
        with patch('digital_life.infrastructure.processes.dispatch_gate.dispatch_gate',side_effect=OSError('synthetic gate unavailable')):
            self.s._discard_unregistered_blobs([(name,st.st_dev,st.st_ino)])
        self.assertTrue(path.is_file())
        actual=self.s.db
        class CommitAckUnknown:
            def __init__(self):self.actual=actual
            def __getattr__(self,key):return getattr(actual,key)
            def execute(self,sql,*args):
                result=actual.execute(sql,*args)
                if sql=='COMMIT':raise OSError('synthetic acknowledgement lost after actual commit')
                return result
        self.s.db=CommitAckUnknown()
        try:
            with self.assertRaises(OSError):
                with self.s.tx():key=self.s.artifact({'committed':'generic Store transaction'})
        finally:self.s.db=actual
        self.assertEqual(self.s.read_artifact(key),{'committed':'generic Store transaction'});self.assertEqual(self.s.depth,0);self.assertEqual(self.s._blob_frames,[])

class ActualBehaviorInspectionTests(unittest.TestCase):
    def setUp(self):
        self.f=StrictActualUseTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.s
        from digital_life.application.behavior.behavior_policy import BehaviorPolicy
        from digital_life.application.learning.engine import StrictEngine
        control=self.f.control;old=self.f.f.identity;deployment=control.db.execute('SELECT deployment_id FROM process_runs WHERE id=?',(old.process_id,)).fetchone()[0]
        control.finish_run(old);control.stop('synthetic behavior configuration');self.behavior=BehaviorPolicy(self.s)
        self.behavior.configure(True,self.s.config()['controller'],parameters={'biases':{'wait':20,'ask':-20,'write_note':-20}})
        control.resume('synthetic behavior resume');identity=control.begin_run(deployment);self.addCleanup(control.finish_run,identity);self.f.f.identity=identity;self.f.k=StrictEngine(self.s,identity,self.f.f.strict.provider)
    def record(self):
        from digital_life.application.services import Personality,Values,States
        from digital_life.application.learning.engine import _dependency
        from digital_life.application.learning.eligibility import ref
        request,result,_,scope=self.f.producer();activity=self.f.activity
        context=self.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(activity,)).fetchone()[0];goal=self.s.db.execute('SELECT id FROM goal_items WHERE source_ref=(SELECT trigger_event_id FROM activities WHERE id=?)',(activity,)).fetchone()[0]
        personality=Personality(self.s);traits=personality.activate(activity,context,{r['name']:1 for r in personality.current()['traits']})
        payload={'activity_id':activity,'personality':traits,'values':Values(self.s).activate(activity,context),'selected_memories':[],'habit_suggestions':[],'states':States(self.s).snapshot()}
        payload['behavior_policy']=self.behavior.context(activity,payload)
        decision=self.behavior.select(activity,goal,context,payload,{'tool':'wait','arguments':{'reason':'synthetic actual selection'}},request)
        event=self.s.db.execute("SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='behavior_policy.selected' ORDER BY event_seq DESC LIMIT 1",(self.s.instance_id,activity)).fetchone()
        token={'object':ref(self.s,result),'revision':0,'epoch':0}
        with self.s.tx():
            for consumer in (ref(self.s,event['id']),ref(self.s,event['payload_artifact_id'])):
                for relation in ('read','delete'):_dependency(self.s,consumer,token,scope,relation,'/model_derivation','learn')
        original=self.s.read_artifact(self.s.row('thought_requests',request)['request_artifact_id'])
        return request,decision,original,scope
    def test_real_behavior_selection_is_request_bound_and_complete_input_is_preserved(self):
        request,decision,original,scope=self.record();data=self.f.reader().thought(request)
        self.assertEqual(data['input']['value'],original);self.assertEqual(len(data['behavior_decisions']),1)
        actual=data['behavior_decisions'][0]['value'];self.assertEqual(actual['request'],request);self.assertEqual(actual['decision'],decision['decision']);self.assertAlmostEqual(sum(c['probability'] for c in actual['candidates']),1)
        rows=self.s.db.execute('SELECT selection_probability FROM decision_candidates WHERE decision_id=? ORDER BY rowid',(decision['decision'],)).fetchall()
        self.assertEqual([r[0] for r in rows],[c['probability'] for c in actual['candidates']]);self.assertIn('personality.openness',actual['feature_snapshot']['features'])
    def test_stopped_locked_behavior_audit_zero_write_and_source_revoke_still_blocks(self):
        from digital_life.application.learning.invalidation import ToolLearningInvalidation
        from tests.test_tool_learning_invalidation import MechanicalInvalidation
        from tests.test_tool_learning_products import envelope
        from digital_life.application.learning.eligibility import ref
        request,decision,original,scope=self.record()
        from digital_life.application.learning.runtime_learning import StrictLearningCoordinator
        coordinator=StrictLearningCoordinator(self.f.k);work=coordinator.admit(self.f.activity,self.s.row('activities',self.f.activity)['trigger_event_id'],{'kind':'json_pointer','pointer':'/text'})
        self.f.control.stop('synthetic stopped audit');(self.s.root/'WAKE_DISABLED').write_text('synthetic lock')
        changes=self.s.db.total_changes;events=len(self.s.rows('runtime_events'));data=self.f.reader().thought(request)
        self.assertEqual(data['input']['value'],original);self.assertEqual(len(data['behavior_decisions']),1);self.assertEqual(self.s.db.total_changes,changes);self.assertEqual(len(self.s.rows('runtime_events')),events)
        source=ref(self.s,self.s.row('activities',self.f.activity)['trigger_event_id']);token={'object':source,'revision':0,'epoch':0}
        payload={'change_id':__import__('uuid').uuid4().hex,'kind':'revoke','source':token,'replacement':slot(),'affected_scope':scope,'subjects':[],'purposes':['learn','history_audit'],'expected_epoch':0,'evidence':[],'erase_scope':slot()}
        change=envelope(payload);policy=self.s.rows('policy_epochs')[0]['policy_version_id'];change.update(instance_id=self.s.instance_id,principal={'actor':ref(self.s,self.s.config()['controller']),'recipient':ref(self.s,self.s.config()['controller']),'module':'M12','purpose':'propagate','authorization':ref(self.s,policy)},work_ref=slot(work),budget=coordinator.budget.check_work(work['id'])['budget'],control=self.f.k._control(self.s.row('tl_work',work['id'])['learning_activity_id'],scope,[token]))
        ToolLearningInvalidation(self.s,MechanicalInvalidation()).apply('mechanical-im06',change)
        with self.assertRaises((Forbidden,Conflict)):self.f.reader().thought(request)
        self.assertTrue((self.s.root/'WAKE_DISABLED').exists());self.assertTrue(self.f.control.state()['user_stopped'])

class LegacyBehaviorInputInspectionTests(unittest.TestCase):
    def test_real_legacy_behavior_record_does_not_replace_complete_request_input(self):
        from tests.test_behavior_policy import BehaviorPolicyTests,Model
        from digital_life.application.monitoring.thought_inspection import ThoughtInspection
        case=BehaviorPolicyTests();case.setUp();self.addCleanup(case.doCleanups);case.enable({'biases':{'wait':20,'write_note':-20,'ask':-20}})
        activity,request,payload=case.prepare();case.engine.think(activity,Model())
        data=ThoughtInspection(case.s).detail(request['id']);self.assertEqual(data['input']['value'],case.s.read_artifact(request['request_artifact_id']));self.assertEqual(data['input']['value']['task'],'test')
        self.assertEqual(len(data['behavior_decisions']),1);self.assertEqual(data['behavior_decisions'][0]['value']['request'],request['id']);self.assertNotEqual(data['input']['artifact_id'],data['behavior_decisions'][0]['artifact_id'])

class SupervisedChildFailureTests(unittest.TestCase):
    def test_child_exception_or_sigsegv_keeps_usage_unknown_no_retry_parent_alive(self):
        import signal
        import resource
        from pathlib import Path
        parent=os.getpid()
        for kind in ('exception','sigsegv'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                marker=Path(directory)/'actual-child-entry'
                def failure(*args):
                    marker.write_text((marker.read_text() if marker.exists() else '')+'entered\n')
                    if kind=='sigsegv':
                        resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.kill(os.getpid(),signal.SIGSEGV)
                    raise RuntimeError('synthetic local child failure, not a remote acknowledgement')
                helper=FreshProviderTests();port,packet=helper.port('remote_chat',failure)
                with self.assertRaises(ContractError):port.generate_fresh(packet)
                self.assertEqual(os.getpid(),parent);self.assertEqual(marker.read_text().splitlines(),['entered'])
                self.assertIsNone(port.last_usage);self.assertIsNone(port.last_observed_route)
                dimensions=port.last_measurements['dimensions'];self.assertEqual(dimensions['attempts']['value'],1)
                for field in ('input_tokens','output_tokens','bytes'):self.assertEqual(dimensions[field]['status'],'unknown')
                self.assertTrue(port.last_transport_entered)  # local opportunity only, not server receipt

class ActivePausedMeterTests(unittest.TestCase):
    def meter(self,monotonic=None):
        from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter
        limits={'input_tokens':0,'output_tokens':0,'attempts':0,'tool_calls':0,'scan':100000,'items':100000,'bytes':32*1024*1024,'elapsed_ms':20000}
        return PhysicalReadMeter(limits,utc(20),**({'monotonic':monotonic} if monotonic else {}))
    def test_active_and_nested_exclusions_are_one_union_not_an_irreversible_peak(self):
        clock=[0];meter=self.meter(lambda:clock[0]);clock[0]=1;meter.time()
        with meter.excluding_child():
            clock[0]=6;meter.consume(7,scan=1,items=1);self.assertEqual(meter.usage()['elapsed_ms'],1000)
            with meter.excluding_child():
                clock[0]=9;meter.time();self.assertEqual(meter.usage()['elapsed_ms'],1000)
            clock[0]=11;meter.time();self.assertEqual(meter.usage()['elapsed_ms'],1000)
        clock[0]=13;usage=meter.usage()
        self.assertEqual(usage['elapsed_ms'],3000);self.assertEqual(usage['bytes'],7);self.assertEqual(usage['scan'],1)
        self.assertEqual(usage['elapsed_ms']+10000,13000)
    def test_original_ten_plus_fifty_millisecond_probe_has_no_fifty_ms_charge(self):
        clock=[0.0];meter=self.meter(lambda:clock[0]);clock[0]=.01;meter.time()
        with meter.excluding_child():clock[0]=.06;meter.time();self.assertEqual(meter.usage()['elapsed_ms'],10)
        # Integer-ms ceilings may add one floating-clock resolution unit.
        self.assertIn(meter.usage()['elapsed_ms'],(10,11));self.assertLess(meter.usage()['elapsed_ms'],20)
    def test_real_store_read_during_pause_and_exception_restore_elapsed_owner(self):
        from tests.test_tool_learning_work import WorkTests
        import math
        fixture=WorkTests();fixture.setUp();self.addCleanup(fixture.doCleanups);meter=self.meter();began=time.monotonic();model_started=None;model_finished=None
        with meter.installed(fixture.s):
            try:
                with meter.excluding_child():
                    model_started=time.monotonic();before=meter.usage()['elapsed_ms'];time.sleep(.04)
                    fixture.s.db.execute('SELECT id FROM identity_instances').fetchone()
                    self.assertEqual(meter.usage()['elapsed_ms'],before)
                    raise RuntimeError('synthetic model opportunity fails after a real parent-side read')
            except RuntimeError:model_finished=time.monotonic()
            time.sleep(.02);fixture.s.db.execute('SELECT id FROM identity_instances').fetchone()
        end=time.monotonic();usage=meter.usage();model_ms=math.ceil((model_finished-model_started)*1000);wall_ms=math.ceil((end-began)*1000)
        self.assertGreaterEqual(usage['elapsed_ms'],20);self.assertGreater(usage['scan'],0);self.assertGreater(usage['bytes'],0)
        self.assertLessEqual(abs(usage['elapsed_ms']+model_ms-wall_ms),4)

class ActivePauseActualBudgetTests(unittest.TestCase):
    def setUp(self):
        self.f=StrictLearningFlowTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.r=self.f.r;self.s=self.f.s
    def run_assessment(self,fail=False):
        import math
        signal=self.s.row('activities',self.f.activity)['trigger_event_id'];work=self.r.admit(self.f.activity,signal,{'kind':'json_pointer','pointer':'/text'},interpret=True)
        provider=self.r.thought.provider;original=provider.generate_fresh;observed=[]
        def measured(packet,**kwargs):
            meter=self.r.active['meter'];before=meter.usage()['elapsed_ms'];time.sleep(.04)
            self.s.db.execute('SELECT id FROM identity_instances').fetchone();observed.append((before,meter.usage()['elapsed_ms']))
            result=original(packet,**kwargs)
            if fail:raise RuntimeError('synthetic local error after measured fake inference consumption')
            return result
        provider.generate_fresh=measured;started=time.monotonic()
        if fail:
            with self.assertRaises(RuntimeError):self.r.assess(work['id'])
        else:self.r.assess(work['id'])
        wall_ms=math.ceil((time.monotonic()-started)*1000);doc=self.r.budget._load(work['id'])[3];reservations=list(doc['ledger']['reservations'].values())
        self.assertEqual(len(observed),1);self.assertEqual(observed[0][0],observed[0][1])
        reads=[r for r in reservations if r['kind']=='retrieval'];models=[r for r in reservations if r['kind']=='thought_attempt']
        self.assertEqual(len(reads),1);self.assertEqual(len(models),1);self.assertTrue(all(r['state']=='settled' for r in reservations))
        self.assertEqual(models[0]['actual']['attempts'],1);self.assertGreaterEqual(models[0]['actual']['elapsed_ms'],40)
        self.assertGreater(reads[0]['actual']['scan'],0);self.assertGreater(reads[0]['actual']['bytes'],0)
        total_ms=sum(r['actual']['elapsed_ms'] for r in reservations)
        self.assertLessEqual(total_ms,wall_ms+5);self.assertGreaterEqual(total_ms,40)
        self.accounting_measurements={'basis':'real local monotonic clock, actual original work ledger, fake transport only','outcome':'local_error' if fail else 'success','read_elapsed_ms':reads[0]['actual']['elapsed_ms'],'model_elapsed_ms':models[0]['actual']['elapsed_ms'],'total_elapsed_ms':total_ms,'wall_elapsed_ms':wall_ms,'read_scan':reads[0]['actual']['scan'],'read_bytes':reads[0]['actual']['bytes'],'read_opportunities':len(reads),'model_opportunities':len(models)}
        if fail:self.assertFalse(self.s.db.execute('SELECT id FROM tl_product WHERE work_id=?',(work['id'],)).fetchone())
    def test_real_original_work_read_and_model_elapsed_conserve_on_success(self):self.run_assessment()
    def test_real_original_work_restores_pause_and_settles_once_on_model_error(self):self.run_assessment(True)

    def test_post_model_source_review_elapsed_belongs_to_read_not_model(self):
        import math
        signal=self.s.row('activities',self.f.activity)['trigger_event_id'];work=self.r.admit(self.f.activity,signal,{'kind':'json_pointer','pointer':'/text'},interpret=True)
        port=self.r.thought.generate_fresh;owner=self.r.observation.eligibility.authority;verify=owner.verify_callback;duration=[];post=[]
        def measured(packet):
            start=time.monotonic()
            try:return port(packet)
            finally:duration.append(math.ceil((time.monotonic()-start)*1000))
        def guarded(entry,principal,context,stage):
            result=verify(entry,principal,context,stage)
            if stage=='result_use' and (context.get('request') or {}).get('kind')=='thought_requests':
                time.sleep(.04);self.s.db.execute('SELECT id FROM identity_instances').fetchone();post.append(True)
            return result
        self.r.thought.generate_fresh=measured;owner.verify_callback=guarded;self.r.assess(work['id'])
        rows=list(self.r.budget._load(work['id'])[3]['ledger']['reservations'].values());model=next(r for r in rows if r['kind']=='thought_attempt');read=next(r for r in rows if r['kind']=='retrieval')
        self.assertEqual(len(duration),1);self.assertEqual(post,[True]);self.assertLessEqual(model['actual']['elapsed_ms'],duration[0]+2);self.assertGreaterEqual(read['actual']['elapsed_ms'],40)
        self.accounting_measurements={'basis':'actual port endpoint and post-use guard with fake transport','port_elapsed_ms':duration[0],'model_elapsed_ms':model['actual']['elapsed_ms'],'read_elapsed_ms':read['actual']['elapsed_ms'],'post_model_guard_delay_ms':40}
    def test_pretransport_binding_failure_does_not_reuse_previous_call_measurements(self):
        from unittest.mock import patch
        from digital_life.domain.tool_learning_resources import DIMENSIONS
        signal=self.s.row('activities',self.f.activity)['trigger_event_id'];work=self.r.admit(self.f.activity,signal,{'kind':'json_pointer','pointer':'/text'},interpret=True)
        previous=dict.fromkeys(DIMENSIONS,0);previous.update(attempts=1,input_tokens=999,output_tokens=888,elapsed_ms=777)
        provider=self.r.thought.provider;provider.last_usage=previous;provider.last_observed_route={'provider':'remote_chat','model':'previous-only'};provider.last_transport_entered=True
        original=self.r.thought.generate_fresh;row=self.s.row
        def rejected(packet):
            def read(table,key):
                if table=='thought_requests' and key==packet['request_id']:raise Forbidden('synthetic current binding denied before provider entry')
                return row(table,key)
            with patch.object(self.s,'row',read):return original(packet)
        self.r.thought.generate_fresh=rejected
        with self.assertRaises(Forbidden):self.r.assess(work['id'])
        self.assertIsNone(provider.last_usage);self.assertIsNone(provider.last_observed_route);self.assertFalse(provider.last_transport_entered)
        reservations=list(self.r.budget._load(work['id'])[3]['ledger']['reservations'].values());model=next(r for r in reservations if r['kind']=='thought_attempt');read=next(r for r in reservations if r['kind']=='retrieval')
        self.assertEqual(model['state'],'usage_unknown');self.assertIsNone(model['actual']);self.assertEqual(read['state'],'settled')
