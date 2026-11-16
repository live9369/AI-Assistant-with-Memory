"""Deterministic isolated exploration: no real model, network or formal instance."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.runtime.engine import Engine
from digital_life.application.autonomy.exploration import Exploration
from digital_life.application.accounts.authorization import Policy
from digital_life.application.services.memory import Memory
from digital_life.domain.contracts import utc,RuntimeIdentity,Forbidden,ContractError,ToolResult
from digital_life.infrastructure.tools.workspace import registry
from digital_life.infrastructure.llm.schemas import validate,schema_for

class ExploringModel:
    name='offline-exploration'
    def __init__(self): self.inputs=[]; self.mutate=None
    def generate(self,request):
        self.inputs.append(copy.deepcopy(request)); ctx=request['exploration']
        refs=ctx['allowed_evidence_refs']
        e={'candidates':[],'disposition':'dormant','assessment':'Need an observation to test the claim.','evidence_refs':[]}
        action={'tool':'wait','arguments':{'reason':'no action'}}
        if ctx['kind']=='discover' and refs:
            e['candidates']=[{'question':'Does the file contradict the earlier count?', 'verification':'Compare the number in notes/count.txt with the memory.', 'expected_gain':0.8,'cost':0.1,'evidence_refs':[refs[0]]}]
        elif ctx['kind']=='investigate' and not ctx['observations']:
            e['disposition']='continue'; action={'tool':'read_file','arguments':{'path':'notes/count.txt'}}
        elif ctx['kind']=='investigate':
            e.update(disposition='resolved',assessment='Observed count is 2; the earlier count of 1 is contradicted.',evidence_refs=[ctx['observations'][-1]['evidence_ref']])
        output={'schema_version':2,'action':action,'explanation':'test fixture','exploration':e}
        if self.mutate: self.mutate(request,output)
        return output

class ExplorationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'isolated'
        self.s=Store.prepare(self.root,model_config={'backend':'fixture','model':'offline-exploration'})
        self.c=Control(self.root,self.s.instance_id); self.engine=Engine(self.s,RuntimeIdentity(0,'offline'))
        self.x=Exploration(self.s); self.model=ExploringModel()
        (self.root/'workspace/notes').mkdir(); (self.root/'workspace/notes/count.txt').write_text('count=2')
        with self.s.tx():
            ev=self.s.evidence(artifact=self.s.artifact({'count':1}))
            self.memory=Memory(self.s).encode('The count in notes/count.txt was 1.',ev)
    def tearDown(self): self.c.close(); self.s.close(); self.tmp.cleanup()
    def enable(self,**options):
        self.x.configure(self.s.config()['controller'],True,**options)
        (self.root/'WAKE_DISABLED').unlink(); self.c.resume('isolated-only')
        Policy(self.s).mode('open',['read_file','list_files'],self.s.config()['controller'])
    def next_activity(self):
        with patch('digital_life.application.autonomy.exploration.utc',side_effect=lambda seconds=0:utc(2000+seconds)):
            return self.x.tick(self.engine)
    def discover(self):
        self.enable(); self.engine.process_one(self.model)
        self.assertEqual(len(self.x.questions()),1)
        return self.next_activity()
    def backend(self,action,root,operation): return registry().invoke(action,root,operation)
    def test_disabled_by_default_and_locked_opt_in_does_not_run(self):
        self.assertFalse(self.x.config()['enabled']); self.assertIsNone(self.x.tick(self.engine))
        self.x.configure(self.s.config()['controller'],True)
        with self.assertRaises(Forbidden): self.x.tick(self.engine)
        self.assertTrue((self.root/'WAKE_DISABLED').exists()); self.assertEqual(self.s.rows('thought_attempts'),[])
    def test_discovery_observation_revision_and_restart(self):
        activity=self.discover()
        self.engine.process_one(self.model)
        self.assertEqual(self.s.row('activities',activity)['state'],'waiting_input')
        self.engine.process_one(self.model,self.backend)
        # Successful read is an observation, not completion.
        self.assertEqual(self.s.row('activities',activity)['state'],'running')
        self.assertEqual(len(self.x.observations(activity)),1)
        self.s.close(); self.s=Store(self.root); self.x=Exploration(self.s); self.engine=Engine(self.s,RuntimeIdentity(0,'offline'))
        self.engine.process_one(self.model,self.backend)
        self.assertEqual(self.s.row('activities',activity)['state'],'completed')
        question=next(iter(self.x.questions().values())); self.assertEqual(question['state'],'resolved')
        self.assertIn('contradicted',question['assessment'])
        requests=[r for r in self.s.rows('thought_requests') if r['activity_id']==activity]
        self.assertEqual(len(requests),2); self.assertEqual(requests[1]['request_parent_id'],requests[0]['id'])
        self.assertNotEqual(requests[0]['request_key'],requests[1]['request_key'])
        self.assertIn('count=2',str(self.model.inputs[-1]['exploration']['observations']))
        self.assertEqual(self.s.integrity()['foreign_keys'],[])
        signal=self.engine.details(activity)[2]
        self.assertEqual(self.s.row('perception_channels',signal['channel_id'])['kind'],'internal')
        self.assertEqual(signal['source_actor_id'],self.s.config()['self_actor'])
    def test_unfounded_resolution_and_forged_evidence_rejected(self):
        activity=self.discover()
        self.model.mutate=lambda req,out:out['exploration'].update(disposition='resolved',evidence_refs=['invented'])
        with self.assertRaises(ContractError): self.engine.think(activity,self.model)
        self.assertEqual(len([r for r in self.s.rows('thought_results') if r['acceptance']=='accepted']),1)
    def test_round_limit_and_duplicate_observation(self):
        activity=self.discover(); self.engine.process_one(self.model)
        proposal=self.s.rows('action_intents')[-1]; self.engine.process_one(self.model,self.backend)
        self.assertTrue(self.engine.execute(proposal['id'],self.backend)['duplicate'])
        self.assertEqual(len(self.x.observations(activity)),1)
        def always_continue(req,out):
            if req['exploration']['kind']=='investigate':
                out['exploration'].update(disposition='continue'); out['action']={'tool':'read_file','arguments':{'path':'notes/count.txt'}}
        self.model.mutate=always_continue
        (self.root/'workspace/notes/count.txt').write_text('count=3')
        for _ in range(3): self.engine.process_one(self.model,self.backend)
        self.assertEqual(self.s.row('activities',activity)['state'],'paused')
        self.assertEqual(len(self.x.observations(activity)),2)
        self.assertEqual(next(iter(self.x.questions().values()))['stop_reason'],'round-budget')
    def test_total_budget_and_duplicate_questions(self):
        self.enable(max_activities=1)
        self.engine.process_one(self.model)
        self.assertIsNone(self.next_activity()); self.assertEqual(self.x.status()['remaining_activities'],0)
        self.assertEqual(len(self.x.questions()),1)
    def test_disable_cancels_pending_exploration(self):
        activity=self.discover(); self.engine.process_one(self.model)
        intent=self.s.rows('action_intents')[-1]['id']
        self.x.configure(self.s.config()['controller'],False)
        self.assertEqual(self.s.row('activities',activity)['state'],'cancelled')
        with self.assertRaises(Forbidden): self.engine.execute(intent,self.backend)
        self.assertEqual(len(self.x.observations(activity)),0)
    def test_memory_restriction_blocks_prepared_request(self):
        self.enable(); activity=self.x.tick(self.engine)
        self.engine.prepare(activity,self.model)
        Memory(self.s).restrict(self.memory['memory_id'],[self.s.config()['controller']],self.s.config()['controller'])
        with self.assertRaises(Forbidden): self.engine.think(activity,self.model)
        self.assertEqual(self.model.inputs,[])
    def test_unknown_observation_pauses_without_replay(self):
        activity=self.discover(); self.engine.process_one(self.model)
        self.engine.process_one(self.model,lambda *args:ToolResult('timeout','unknown','unknown'))
        self.assertEqual(self.s.row('activities',activity)['state'],'paused')
        self.assertEqual(next(iter(self.x.questions().values()))['state'],'dormant')
    def test_receipt_commit_crash_is_reconciled_without_tool_replay(self):
        from digital_life.application.runtime.execution import Executor
        activity=self.discover(); self.engine.process_one(self.model)
        intent=self.s.rows('action_intents')[-1]['id']
        outcome=Executor(self.s,self.engine.identity).dispatch(intent,self.backend)
        self.assertEqual(len(self.x.observations(activity)),0)
        self.engine.execute(intent,lambda *a:self.fail('tool replay'))
        self.assertEqual(self.x.observations(activity)[0]['result'],outcome['result'])
    def test_contract_selection_and_strict_candidate_validation(self):
        self.assertEqual(schema_for({})['properties']['schema_version']['const'],1)
        self.assertEqual(schema_for({'output_schema_version':2})['properties']['schema_version']['const'],2)
        activity=self.discover(); _,payload=self.engine.prepare(activity,self.model)
        out=self.model.generate(payload); out['exploration']['candidates']=[{'question':'q','verification':'test','expected_gain':True,'cost':0,'evidence_refs':['x']}]
        with self.assertRaises(ContractError): validate(out)

    def test_new_runtime_epoch_continues_after_committed_observation(self):
        activity=self.discover(); self.engine.process_one(self.model)
        self.engine.process_one(self.model,self.backend)
        self.engine=Engine(self.s,RuntimeIdentity(1,'new-offline-runtime'))
        self.engine.process_one(self.model,self.backend)
        self.assertEqual(self.s.row('activities',activity)['state'],'completed')
        requests=[r for r in self.s.rows('thought_requests') if r['activity_id']==activity]
        self.assertEqual([r['runtime_epoch'] for r in requests],[0,1])
    def test_disable_during_generation_discards_result(self):
        activity=self.discover()
        self.model.mutate=lambda req,out:self.x.configure(self.s.config()['controller'],False)
        result=self.engine.think(activity,self.model)
        self.assertFalse(result['accepted']); self.assertEqual(result['reason'],'stale')
        self.assertEqual(self.s.rows('action_intents'),[])
    def test_tick_respects_user_work_and_cooldown(self):
        self.enable(); user=self.engine.submit('human request','priority')
        self.assertIsNone(self.x.tick(self.engine))
        self.engine.cancel(user,self.s.config()['controller'])
        first=self.x.tick(self.engine)
        self.assertIsNone(self.x.tick(self.engine))
        self.engine.think(first,self.model)
        self.assertIsNone(self.x.tick(self.engine))
    def test_question_deduplication_and_generation_budget(self):
        self.enable(max_activities=2); self.engine.process_one(self.model)
        cfg=self.x.config(); before=self.x.questions()
        # A fresh discovery proposal of the same normalized question cannot reset visits.
        q=next(iter(before.values()))
        with self.s.tx(): self.x.record(dict(q,state='resolved'))
        activity=self.next_activity(); self.assertIsNotNone(activity)
        self.engine.process_one(self.model)
        self.assertEqual(len(self.x.questions()),1)
        self.assertEqual(next(iter(self.x.questions().values()))['state'],'resolved')
        self.assertIsNone(self.next_activity())
    def test_failed_model_job_pauses_instead_of_blocking_scheduler(self):
        activity=self.discover()
        self.model.mutate=lambda req,out:out.update(schema_version=1)
        with self.assertRaises(ContractError): self.engine.process_one(self.model)
        self.assertEqual(self.s.row('activities',activity)['state'],'paused')
        self.assertEqual(next(iter(self.x.questions().values()))['stop_reason'],'thought-failed')
    def test_provider_schema_selection_without_network(self):
        from digital_life.infrastructure.llm.inference import configured_reasoner
        from digital_life.infrastructure.llm.codex_cli import CodexReasoner
        from digital_life.infrastructure.llm.remote_chat import RemoteChatReasoner
        from digital_life.infrastructure.llm.ollama import OllamaReasoner
        import json
        from digital_life.infrastructure.llm.schemas import SCHEMA
        ollama=OllamaReasoner('fixture',output_schema=SCHEMA,output_validator=validate)
        self.assertEqual(ollama.payload({'model':ollama.name,'output_schema_version':2})['format']['properties']['schema_version']['const'],2)
        remote=RemoteChatReasoner({'backend':'remote_chat','enabled':False,'model':'fixture','base_url':'https://provider.example/v1','api_key_env':'FIXTURE_KEY'})
        self.assertEqual(remote.payload({'model':remote.name,'output_schema_version':2})['response_format']['json_schema']['schema']['properties']['schema_version']['const'],2)
        codex=CodexReasoner({'backend':'codex_cli','model':'fixture','enabled':True,'executable':'/fixture/codex'})
        output={'schema_version':2,'action':{'tool':'wait','arguments':{'reason':'fixture'}},'explanation':'fixture','exploration':{'candidates':[],'disposition':'dormant','assessment':'No evidence','evidence_refs':[]}}
        def fake_run(args,root,stdin=''):
            schema=json.loads((root/'schema.json').read_text())
            self.assertEqual(schema['properties']['schema_version']['const'],2)
            return '\n'.join(json.dumps(e) for e in [{'type':'thread.started','thread_id':'fixture'},{'type':'item.completed','item':{'type':'agent_message','text':json.dumps(output)}},{'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}}])
        with patch.object(codex,'run',side_effect=fake_run): self.assertEqual(codex.generate({'model':codex.name,'output_schema_version':2}),output)

if __name__=='__main__': unittest.main()
