"""Q10 case-specific aggregation fixtures; authored truth is not model science."""
from evaluation.tool_learning_statistics import count_metric,retrieval_metrics,paired_effect,latency_summary,cost_summary


def row(ident,value=True,status='measured',case=None):
    return {'id':str(ident),'case_id':case or str(ident),'category':'fixed-authored-mechanism','status':status,'value':value}


def run_arithmetic(case_id):
    number=int(case_id.rsplit('C',1)[1]);inputs={};outputs={};checks=[]
    def require(name,condition):
        checks.append({'assertion':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    if number==1:
        outputs={'zero':count_metric('TL02',[]),'not_run':count_metric('TL02',[row('registered',None,'not_run')])}
        require('zero opportunities is no rate/not applicable, never successful run',outputs['zero']['denominator']==0 and outputs['zero']['rate'] is None and outputs['zero']['decision']=='not_applicable')
        require('registered unrun remains denominator one and incomplete',outputs['not_run']['denominator']==1 and outputs['not_run']['rate'] is None and outputs['not_run']['decision']=='incomplete')
    elif number==2:
        inputs['rows']=[row('known'),row('unlabelled',None,'missing')];outputs=count_metric('TL06',inputs['rows'])
        require('all preregistered opportunities and bounds retained',outputs['denominator']==2 and outputs['bounds']==[.5,1] and outputs['decision']=='incomplete' and outputs['rate'] is None)
    elif number==3:
        inputs['rows']=[dict(row('success'),failure_kind=None),dict(row('timeout',False),failure_kind='timeout'),dict(row('provider_failure',False),failure_kind='provider_failure')];outputs=count_metric('TL06',inputs['rows'])
        require('timeout/provider failures do not vanish behind success subset',outputs['denominator']==3 and outputs['rate']==1/3 and outputs['decision']=='fail')
    elif number==4:
        inputs['rows']=[row('paraphrase-'+str(i),case='one-original-source-case')for i in range(9)];outputs=count_metric('TL03',inputs['rows'],required_categories=['fixed-authored-mechanism'],formal=True)
        require('paraphrases/repeats create no independent cases',outputs['independent_cases_by_required_category']=={'fixed-authored-mechanism':1} and outputs['decision']=='insufficient_sample')
    elif number==5:
        inputs['legal_rejections']=[row(i)for i in range(3)];inputs['learning_coverage']=[row(i,False)for i in range(3)];outputs={'endpoint':count_metric('TL02',inputs['legal_rejections']),'coverage':count_metric('TL04',inputs['learning_coverage'])}
        require('all legal rejects do not pass learning coverage',outputs['endpoint']['decision']=='pass' and outputs['coverage']['decision']=='fail')
    elif number==6:
        inputs['answerability']=['answerable','answerable','unknown'];inputs['answers']=['UNKNOWN']*3;outputs={'quality':count_metric('TL06',[row(0,False),row(1,False),row(2)]),'unknown_boundary':count_metric('TL07',[row('unknown')])}
        require('correct unknown boundary does not certify answerable queries',outputs['quality']['decision']=='fail' and outputs['unknown_boundary']['decision']=='pass')
    elif number in (7,9):
        inputs={'source':{'claim':'at_most_10' if number==9 else 'file_report_10','time':'t0','scope':'one_report'},'candidate':{'claim':'exactly_10' if number==9 else 'world_stock_10','time':'now','scope':'unconditional'}}
        outputs=count_metric('TL06',[row('authored-unsupported-upgrade',False)])
        require('authored scope/qualifier violation fails fidelity despite equal numeral',outputs['decision']=='fail')
    elif number==8:
        inputs['queries']=[{'id':'price-query','case_id':'price','relevant_ids':[],'returned_ids':['inventory-reading']}];outputs=retrieval_metrics(inputs['queries'])
        require('empty relevant set does not make irrelevant fill precision one',outputs['queries'][0]['precision']==0 and outputs['decision']!='pass')
    elif number==15:
        inputs['latencies']=[{'completed':True,'observed_ms':10},{'completed':True,'observed_ms':20},{'completed':False,'observed_ms':100}];outputs=latency_summary(inputs['latencies'])
        require('right-censored backlog excluded from completed p95 but retained',outputs['completed_p95_ms']==20 and outputs['completed_fraction']==2/3 and outputs['right_censored_observation_ms']==[100])
    elif number==18:
        inputs['rows']=[row(str(case)+'-'+str(i),case='source-case-'+str(case))for case in range(2)for i in range(100)];inputs['template_family']='one-finite-template-family';outputs=count_metric('TL04',inputs['rows'],formal=True,required_categories=['fixed-authored-mechanism'])
        require('200 rows are two cases, not 200 independent samples',outputs['independent_cases_by_required_category']=={'fixed-authored-mechanism':2} and outputs['decision']=='insufficient_sample')
    elif number==20:
        def paired(e,n):return [{'case_id':case,'arm':arm,'repeat':repeat,'status':'measured','score':e if arm=='E'else n}for case in ('a','b')for arm in ('E','N')for repeat in (1,2,3)]
        outputs={}
        for label,effect,retention in [('improve_but_forget',(1,0),(0,1)),('retain_without_improvement',(0,0),(1,1))]:
            a=paired_effect(paired(*effect),metric_id='TL13',expected_cases=['a','b'],query_kind='new_question');b=paired_effect(paired(*retention),metric_id='TL14',expected_cases=['a','b'],query_kind='retention');outputs[label]={'improvement':a,'retention':b,'combined_pass':a['decision']==b['decision']=='pass'}
            require(label+' cannot pass both gates',not outputs[label]['combined_pass'])
    else:raise ValueError('case uses separately bound actual runtime fixture: '+case_id)
    return {'case_id':case_id,'inputs':inputs,'actual_statistics':outputs,'assertions':checks,'endpoint':'authored_aggregation_boundary_verified','scope':'Actual deterministic metric functions on explicitly authored truth, not evidence of model accuracy, semantic scoring or statistical independence. Runtime boundary cases are separate linked actual executions.','real_model_called':False}


def run_actual(case_id):
    if case_id=='Q10-C12':
        import uuid
        from unittest.mock import patch
        from tests.test_tool_learning_observation import ObservationTests
        from digital_life.domain import tool_learning_contract as c
        from digital_life.domain.contracts import ContractError
        f=ObservationTests();f.setUp()
        try:
            f.plan['interpret']=True;erase=f.erase_request();f.thought.hook=lambda:f.apply_erase(erase)
            original=f.thought.generate_fresh;private_marker=uuid.uuid4().hex;fingerprints=[]
            def late(packet):
                result=original(packet);result['body']['rationale']=private_marker
                fingerprints.append(c.fingerprint(result['body']));return result
            rejected=False
            with patch.object(f.thought,'generate_fresh',late):
                try:f.assess()
                except ContractError:rejected=True
            if not rejected or len(f.thought.calls)!=1 or len(fingerprints)!=1:raise AssertionError('real erase-during-entry was not observed exactly once')
            persisted='\n'.join(f.s.db.iterdump()).encode()
            blobs=[p.read_bytes()for p in (f.s.root/'blobs').iterdir()if p.is_file()and not p.is_symlink()]
            if any(private_marker.encode()in raw or fingerprints[0].encode()in raw for raw in [persisted]+blobs):raise AssertionError('forbidden late response body or response digest persisted')
            results=f.s.db.execute('SELECT count(*) FROM thought_results').fetchone()[0]
            if results or f.products():raise AssertionError('erased-source late result was retained')
            return {'case_id':case_id,'actual_callback_entries':len(f.thought.calls),'rejected_after_actual_erase':rejected,'thought_result_rows':results,'late_body_or_hash_persisted':False,'persisted_metadata_observed':True,'real_model_called':False,'scope':'Synthetic response-only secret and digest scanned across actual main database dump and all managed blobs; secret itself is not sealed in evidence.'}
        finally:f.doCleanups()
    if case_id=='Q10-C13':
        from tests.test_tool_learning_propagation import PropagationTests
        f=PropagationTests();f.setUp()
        try:
            plan,path=f.blob_plan();plan['targets'].append({'target':f.f.source,'location':'remote','operation':'observe','expected':{}})
            f.erasure.prepare('synthetic-im12',plan);result=f.erasure.run('synthetic-im12',plan['id'])
            states=[v['state']for v in result['targets'].values()]
            if states.count('verified')!=2 or states.count('unknown')!=1 or result['state']!='blocked' or path.exists():raise AssertionError('actual physical 2/3 completion lost unknown target')
            return {'case_id':case_id,'actual_plan':plan,'actual_result':result,'denominator':3,'verified_targets':2,'unresolved_targets':1,'all_deleted':False,'real_model_called':False}
        finally:f.doCleanups()
    if case_id=='Q10-C16':
        from tests.test_tool_learning_evaluation import BudgetRunnerTests
        from evaluation.tool_learning_runner import DeterministicRunner,DeterministicFixture
        f=BudgetRunnerTests();f.setUp()
        try:
            runner=DeterministicRunner(f.b)
            first=runner.run(DeterministicFixture('known100',lambda:dict(passed=True,output_tokens=40,evidence={'explicit_authored_input_tokens':60}),'IM19 fixed deterministic protocol',input_tokens=60),'known','trial','batch','run')
            def fail():raise RuntimeError('IM19 actual entered callback with unknown provider usage')
            try:runner.run(DeterministicFixture('unknown',fail,'IM19 fixed deterministic failure'),'unknown','trial','batch','run')
            except RuntimeError:pass
            else:raise AssertionError('actual unknown callback did not fail')
            rows=[{'attempt_id':'known','transport':'model','input_tokens':60,'output_tokens':40,'tool_calls':0,'elapsed_ms':1,'money':None},{'attempt_id':'unknown','transport':'model','input_tokens':None,'output_tokens':None,'tool_calls':0,'elapsed_ms':None,'money':None}]
            result=cost_summary(rows,correct_queries=1)
            if result['components']['input_tokens']['known_subtotal']!=60 or result['components']['output_tokens']['known_subtotal']!=40 or result['components']['input_tokens']['total']is not None or f.b.state()['reason']!='usage_unknown':raise AssertionError('known100/unknown consumption replaced by reservation or zero')
            return {'case_id':case_id,'actual_first':first,'actual_events':runner.events,'actual_results':runner.results,'actual_balances':f.b.balances('run'),'actual_cost_summary':result,'actual_attempt_rows':rows,'real_model_called':False}
        finally:f.tearDown()
    if case_id=='Q10-C17':
        from tests.test_tool_learning_evaluation import StoreTests,record,RUN
        f=StoreTests();f.setUp()
        try:
            f.s.register_identity('author1','author','synthetic-author');f.s.register_identity('reviewer1','reviewer','synthetic-reviewer')
            f.s.put('Label',record('Label'));f.s.put('Review',record('Review'))
            gate=f.s.review_gate(RUN,'blind1')
            if gate['state']!='blocked_before_start' or 'two independent review groups absent'not in gate['issues']:raise AssertionError('single synthetic reviewer passed formal evidence gate')
            return {'case_id':case_id,'actual_review_gate':gate,'actual_review_count':f.w.truth.execute('SELECT count(*) FROM tle_review').fetchone()[0],'mode':'single_reviewer_exploratory','formal_evidence_qualified':False,'real_model_called':False}
        finally:f.tearDown()
    raise ValueError(case_id)
