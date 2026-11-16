import copy
import unittest
from evaluation.im20.preparation import TARGET,RETENTION,KINDS,MaterialError,validate,assemble,project,digest,strict_loads,strict_dumps
from digital_life.domain.contracts import ContractError

def fixture(p='TARGET',category=None,index=0):
    category=category or TARGET[0]; cid=f'{p}.{category}.{index:04}'
    inp={'query':'Which supported value applies?','purpose':'isolated synthetic test','subject':cid,'recipient':'test-request','scope':'test-only','k':5}
    truth={'claims':[{'claim':'fixture value','support_locator':cid+':1','expected_support':'source_report','scope':'test','unknown':False}], 'scope':'test','value_slot':{'status':'known','value':index,'reason_code':'none','reason':'','basis_refs':[]},'correct_endpoint':'supported_report','major_error_examples':['reporting as universal fact'],'relevance_rationale':'fixture record is the sole support','label_provenance':'developer synthetic self-test, not independent','relevant_set':[cid+':record'],'answerable':True}
    return {'case_id':cid,'partition':p,'category':category,'source_cluster_id':cid,'answer_sharing_key':cid,'template_family':'self-test-template','material_type':'synthetic','source_locator':'generated unittest fixture','source_version':'1','source_digest':digest(cid),'permission':'local temporary fixture only','event_timeline':['observe then query'],'independence_evidence':'synthetic structure shared: no natural independence claimed','author_provenance':'developer self-test','learning_input':{'observation':f'Synthetic report {index}','baseline':'test baseline','source_permissions':'fixture only','observed_at':'2026-11-10T00:00:00.000Z','parser_version':'fixture1','tool_version':'stub1'},'eligible_catalog':[cid+':record'],'queries':[{'kind':k,'query_input':copy.deepcopy(inp),'truth':copy.deepcopy(truth)} for k in KINDS[p]]}

class PreparationTests(unittest.TestCase):
    def test_valid_synthetic_is_never_formal(self):
        r=validate([fixture()]); self.assertFalse(r['formal_launch_eligible']);self.assertFalse(r['semantic_truth_verified'])
    def test_reject_cross_partition_source(self):
        a=fixture(); b=fixture('RETENTION',RETENTION[0]);b['source_cluster_id']=a['source_cluster_id']
        with self.assertRaises((MaterialError,ContractError)):validate([a,b])
    def test_cross_partition_answer_and_dev_exclusions(self):
        a=fixture();b=fixture('RETENTION',RETENTION[0]);b['answer_sharing_key']=a['answer_sharing_key']
        with self.assertRaises((MaterialError,ContractError)):validate([a,b])
        for key,val in [('dev_clusters',[a['source_cluster_id']]),('dev_families',[a['template_family']]),('dev_answer_keys',[a['answer_sharing_key']])]:
            with self.assertRaises((MaterialError,ContractError)):validate([a],**{key:val})
    def test_queries_truth_and_relevance_fail_closed(self):
        for mutate in [lambda c:c['queries'].pop(),lambda c:c['queries'][0]['query_input'].update(k=4),lambda c:c['queries'][0]['truth'].update(relevant_set=['unknown']),lambda c:c['queries'][0]['truth'].update(relevant_set=[]),lambda c:c['queries'][0]['truth'].pop('major_error_examples'),lambda c:c['queries'][0]['truth']['claims'][0].pop('support_locator')]:
            c=fixture();mutate(c)
            with self.assertRaises((MaterialError,ContractError,KeyError)):validate([c])
    def test_leak_projection_and_permissions(self):
        c=fixture();learning=project(c,'learning');q=project(c,'query','new_question')
        self.assertNotIn('truth',learning);self.assertNotIn('relevant_set',q)
        learning['observation']='changed'; self.assertNotEqual(c['learning_input']['observation'],'changed')
        with self.assertRaises((MaterialError,ContractError)):project(c,'controller-truth')
        c['learning_input']['truth']='secret'
        with self.assertRaises((MaterialError,ContractError)):project(c,'learning')
    def test_partial_never_makes_placeholder_batches(self):
        with self.assertRaises((MaterialError,ContractError)):assemble([fixture()])
    def test_legal_zero_false_and_reported_null(self):
        c=fixture();self.assertEqual(c['queries'][0]['truth']['value_slot']['value'],0)
        validate([c])
        q=c['queries'][0];q['truth']['value_slot'].update(value=False)
        validate([c])
        q['truth']['value_slot'].update(value=None,reason_code='source_reported_null')
        q['truth'].update(answerable=False,relevant_set=[])
        validate([c]);self.assertEqual(strict_loads(strict_dumps(c)),c)
    def test_closed_schema_rejects_wrong_types_and_extra_fields(self):
        mutations=[lambda c:c.update(extra='leak'),lambda c:c.update(event_timeline='not list'),lambda c:c.update(template_family=0),lambda c:c['queries'][0]['truth'].update(answerable=0),lambda c:c['queries'][0]['query_input'].update(k=True),lambda c:c['queries'][0]['truth']['claims'][0].update(unknown='false'),lambda c:c['queries'][0]['truth']['claims'][0].update(expected_support='guessed'),lambda c:c['queries'][0]['truth']['value_slot'].update(extra=1),lambda c:c['queries'][0]['truth']['value_slot'].update(value=None),lambda c:c['queries'][0]['truth'].update(claims={})]
        for mutation in mutations:
            c=fixture();mutation(c)
            with self.assertRaises((MaterialError,ContractError)):validate([c])
    def test_strict_json_rejects_nonfinite_duplicate_and_non_json(self):
        for raw in ('NaN','Infinity','-Infinity','1e999','{"a":1,"a":2}'):
            with self.assertRaises((MaterialError,ContractError)):strict_loads(raw)
        for value in (float('nan'),float('inf'),{'nested':[float('-inf')]},{1:'bad key'},(1,2)):
            with self.assertRaises((ValueError,ContractError)):digest(value)
        c=fixture();c['queries'][0]['truth']['value_slot']['value']=float('nan')
        with self.assertRaises(ContractError):validate([c])
    def test_exact_batch_order_counts_seed_and_family_disclosure(self):
        # Transient protocol load test only; not stored and not independent material.
        cases=[fixture(p,c,i) for p,cats,n in [('TARGET',TARGET,100),('RETENTION',RETENTION,400)] for c in cats for i in range(n)]
        a=assemble(list(reversed(cases)));b=assemble(cases)
        self.assertEqual(a,b);self.assertEqual(len(a['batches']),28)
        self.assertEqual(sum(len(x['assignments']) for x in a['batches']),16800)
        self.assertEqual(a['batches'][0]['case_ids'][0],f'TARGET.{TARGET[0]}.0000')
        self.assertEqual(a['batches'][8]['case_ids'][0],f'RETENTION.{RETENTION[0]}.0000')
        self.assertEqual(len(a['validation']['correlated_families']['self-test-template']),2800)
        self.assertFalse(a['formal_launch_eligible'])
        for batch in a['batches']:
            self.assertEqual(len(batch['case_ids']),100)
            for i in range(0,600,2):self.assertEqual({x['arm'] for x in batch['assignments'][i:i+2]},{'E','N'})

if __name__=='__main__':unittest.main()
