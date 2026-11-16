"""Evidence/review integrity and statistical tests. No real model or formal instance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from evaluation.exploration.harness import Harness
from evaluation.exploration.scenarios import material_smoke
from evaluation.exploration.g2.review import export_packets,load_reviews,digest,write,read_trials
from evaluation.exploration.g2.aggregate import aggregate,cluster_ratio
from evaluation.exploration.g2.runtime import RealTrial
ROOT=Path(__file__).resolve().parents[1]

class G2ToolingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.run=self.root/'run';self.run.mkdir()
        self.public=json.loads((ROOT/'evaluation/exploration/g2/materials/development-public.json').read_text());self.oracle=json.loads((ROOT/'evaluation/exploration/g2/materials/development-oracle.json').read_text())
        self.public['cases']=self.public['cases'][:1];self.oracle['cases']=self.oracle['cases'][:1]
        case=self.public['cases'][0]
        converted={'case_id':case['case_id'],'topic':case['topic'],'public':{'memory':case['memories'][0],'files':case['files'],'observation_path':next(iter(case['files']))},'world_events':[],'fixture_behavior':'resolve'}
        td=self.run/'trials/test-trial';td.mkdir(parents=True)
        h=Harness(self.root/'fixture',converted)
        try:material_smoke(h);h.export(td)
        finally:h.close()
        result={'trial_id':'test-trial','case_id':case['case_id'],'status':'completed','error':None,'summary':{'real_model_calls':3,'tool_calls':1,'observed_tokens':10,'unknown_usage_calls':0,'wall_seconds':1},'evidence_hashes':{n:digest(td/n) for n in ('snapshot.json','artifacts.json','trace.json')},'real_model_used':False}
        write(td/'result.json',result);write(self.run/'public.json',self.public);write(self.run/'oracle.json',self.oracle)
        manifest={'run_id':'g2-unit-only','protocol_id':'AE-EVAL-1.0','mode':'pilot','split':'development','sampling':{'repeats':1},'g0':{'successful':True},'g1':{'gates':{'G1':'pass'}},'public_sha256':digest(self.run/'public.json'),'oracle_sha256':digest(self.run/'oracle.json'),
          'trials':[{'trial_id':'test-trial','case_id':case['case_id'],'stratum':'A','arm':'full','repeat':1}]}
        write(self.run/'manifest.json',manifest);(self.run/'manifest.sha256').write_text(digest(self.run/'manifest.json'))
        write(self.run/'evidence-index.json',{'test-trial':{'exit_code':0,'watchdog_fired':False,'result_sha256':digest(td/'result.json')}});(self.run/'evidence-index.sha256').write_text(digest(self.run/'evidence-index.json'))
        write(self.run/'formal-instance-guard.json',{'unchanged':True})
        p=self.run/'source-snapshot/docs/architecture';p.mkdir(parents=True);(p/'autonomous-exploration-baseline-v1.1.json').write_bytes((ROOT/'docs/architecture/autonomous-exploration-baseline-v1.1.json').read_bytes())
        export_packets(self.run)
    def tearDown(self):self.tmp.cleanup()
    def labels(self,name,independent=False):
        record=json.loads((self.run/'review/labels-template.json').read_text());record['reviewer']={'id':name,'independent':independent,'material_author':not independent,'actor_operator':not independent,'blind_to_model':independent,'blind_to_arm':independent,'mode':'independent' if independent else 'single_exploratory'}
        bundle=json.loads((self.run/'review/packets.json').read_text());units={u['unit_id']:u for u in bundle['units']}
        packet=bundle['packets'][0];obs=packet['observations'][0]['evidence_ref']
        for label in record['labels']:
            u=units[label['unit_id']];label['fields']={f:f!='redundant' for f in u['required_fields']};label['reason']='Unit-test labels, not real quality evidence';label['evidence_refs']=[obs if u['kind']=='investigation' else u['packet_id']]
        path=self.run/(name+'.json');write(path,record);return path
    def test_single_author_review_never_passes_formal_gate(self):
        record=aggregate(self.run,[self.labels('author')])
        self.assertEqual(record['review']['mode'],'single_exploratory');self.assertEqual(record['gates']['G2'],'not_evaluable')
        m=next(m for m in record['metrics'] if m['metric_id']=='M07');self.assertEqual(m['value'],1);self.assertEqual(m['status'],'insufficient_sample')
    def test_conflicts_require_distinct_adjudicator(self):
        first=self.labels('r1',True);second=self.labels('r2',True);r=json.loads(second.read_text())
        label=next(l for l in r['labels'] if 'autonomous' in l['fields']);label['fields']['autonomous']=False;write(second,r)
        reviewed=load_reviews(self.run,[first,second]);self.assertTrue(reviewed['conflicts'])
        with self.assertRaises(ValueError):load_reviews(self.run,[first,first])
        adjudicator={'reviewer':{'id':'r3','independent':True,'blind_to_model':True,'blind_to_arm':True,'material_author':False,'actor_operator':False},'packet_sha256':digest(self.run/'review/packets.json'),'labels':[dict(label,fields={'autonomous':True})]};path=self.run/'adjudication.json';write(path,adjudicator)
        self.assertFalse(load_reviews(self.run,[first,second],path)['conflicts'])
    def test_missing_reviews_remain_missing_not_zero(self):
        r=aggregate(self.run);m=next(m for m in r['metrics'] if m['metric_id']=='M01')
        self.assertEqual(m['status'],'missing');self.assertIsNone(m['value']);self.assertIsNone(m['numerator'])
    def test_packet_hides_actor_identity_metadata(self):
        packet=json.loads((self.run/'review/packets.json').read_text())
        text=json.dumps(packet);self.assertNotIn('ae-g1-scripted-v1',text);self.assertNotIn('test-trial',text);self.assertNotIn('P01',text)
        self.assertTrue(packet['identity_metadata_removed'])
    def test_oracle_and_evidence_tampering_rejected(self):
        (self.run/'oracle.json').write_text('{}')
        with self.assertRaises(ValueError):read_trials(self.run)
    def test_unfilled_or_wrong_evidence_labels_rejected(self):
        with self.assertRaises(ValueError):load_reviews(self.run,[self.run/'review/labels-template.json'])
        path=self.labels('author');record=json.loads(path.read_text());record['labels'][0]['evidence_refs']=['made-up-evidence'];write(path,record)
        with self.assertRaises(ValueError):load_reviews(self.run,[path])
    def test_case_cluster_not_repetition_count(self):
        rows=[{'case_id':'one','numerator':1,'denominator':1} for _ in range(30)]
        r=cluster_ratio(rows,bootstrap=1000);self.assertEqual(r['independent_cases'],1)
        rows += [{'case_id':'two','numerator':0,'denominator':1}]
        self.assertEqual(cluster_ratio(rows,1000)['value'],0.5)
    def test_formal_and_development_materials_are_disjoint(self):
        base=ROOT/'evaluation/exploration/g2/materials';formal=json.loads((base/'formal-candidate-public.json').read_text());dev=json.loads((base/'development-public.json').read_text())
        self.assertEqual(len(formal['cases']),60);self.assertEqual(len(dev['cases']),6)
        self.assertFalse({c['topic'] for c in formal['cases']}&{c['topic'] for c in dev['cases']})
        self.assertTrue(all('oracle' not in c and 'gaps' not in c for c in formal['cases']))
    def test_real_runner_passes_only_public_experience_and_honors_zero_call_budget(self):
        class Model:
            name='fixture:public-only';timeout=120;last_usage={'input_tokens':2,'output_tokens':1}
            def generate(self,request):
                text=json.dumps(request);self_outer.assertNotIn('resolution_rule',text);self_outer.assertNotIn('oracle',text)
                return {'schema_version':2,'action':{'tool':'wait','arguments':{'reason':'no question'}},'explanation':'test','exploration':{'candidates':[],'disposition':'dormant','assessment':'No evidence gap selected.','evidence_refs':[]}}
        self_outer=self
        limits={'activities':1,'model_calls':0,'wall_seconds':10,'observed_tokens':1000}
        directory=self.root/'runtime-evidence';directory.mkdir()
        with patch('evaluation.exploration.g2.runtime.configured_reasoner',return_value=Model()):
            env=RealTrial(self.root/'real-env',self.public['cases'][0],{'backend':'fixture','model':'public-only','timeout':120},limits,directory)
            try:r=env.run();self.assertEqual(r['real_model_calls'],0)
            finally:env.close()
            limits=dict(limits,model_calls=1)
            env=RealTrial(self.root/'real-env-two',self.public['cases'][0],{'backend':'fixture','model':'public-only','timeout':120},limits,directory)
            try:r=env.run();self.assertEqual(r['real_model_calls'],1)
            finally:env.close()

    def test_review_turns_follow_actual_callback_sequence(self):
        bundle=json.loads((self.run/'review/packets.json').read_text())
        for packet in bundle['packets']:
            sequences=[turn['sequence'] for turn in packet['turns']]
            self.assertEqual(sequences,sorted(sequences))
    def test_adjudicator_cannot_claim_independence_while_author_or_unblinded(self):
        first=self.labels('r1',True);second=self.labels('r2',True);record=json.loads(second.read_text())
        label=next(l for l in record['labels'] if 'autonomous' in l['fields']);label['fields']['autonomous']=False;write(second,record)
        adjudicator={'reviewer':{'id':'r3','independent':True,'material_author':True,'blind_to_model':False,'blind_to_arm':False},'packet_sha256':digest(self.run/'review/packets.json'),'labels':[dict(label,fields={'autonomous':True})]}
        path=self.run/'bad-adjudication.json';write(path,adjudicator)
        with self.assertRaises(ValueError):load_reviews(self.run,[first,second],path)

if __name__=='__main__':unittest.main()
