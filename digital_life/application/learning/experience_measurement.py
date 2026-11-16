"""Sealed before/after prediction measurement, kept outside live selection.

A trusted prediction port gets no labels. Controller-attested holdout labels are
revealed only after both arms are sealed. This validates computation/provenance,
not the truth or semantic independence of a controller's supplied dataset.
"""
import json
import math
import time
from datetime import datetime,timezone
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,dumps,sha,text,identifier,utc
from digital_life.infrastructure.processes.dispatch_gate import coordinated,dispatch_gate
from digital_life.application.runtime.scheduling import Budget
from digital_life.domain.experience import PredictionPort

CONTRACT='EXPERIENCE-MEASUREMENT-0.1'
SOURCE='experience-measurement'
MEASURER='prediction_brier_v1'

class ExperienceMeasurement:
    def __init__(self,store):self.s=store
    def _controller(self,actor):
        if actor!=self.s.config()['controller']:raise Forbidden('controller required for experience measurement')
    def _events(self,kind):
        return [dict(id=r['id'],payload=self.s.read_artifact(r['payload_artifact_id'])) for r in self.s.db.execute(
            'SELECT * FROM runtime_events WHERE instance_id=? AND source=? AND event_type=? ORDER BY event_seq',
            (self.s.instance_id,SOURCE,'learning.measurement_'+kind))]
    def _get(self,kind,key):
        row=self.s.db.execute('SELECT * FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=? AND event_type=?',
            (self.s.instance_id,SOURCE,kind+':'+key,'learning.measurement_'+kind)).fetchone()
        return dict(id=row['id'],payload=self.s.read_artifact(row['payload_artifact_id'])) if row else None
    def _write(self,kind,key,value):
        return self.s.event('learning.measurement_'+kind,payload=dict(value,contract_id=CONTRACT,instance_id=self.s.instance_id),
            source=SOURCE,key=kind+':'+key,lane='telemetry')
    def configuration(self):
        rows=self._events('configured')
        return dict(rows[-1]['payload'],generation=rows[-1]['id']) if rows else {'enabled':False,'generation':None}
    @coordinated
    def configure(self,enabled,actor):
        self._controller(actor)
        if type(enabled) is not bool:raise ContractError('measurement enabled must be boolean')
        if enabled:
            from digital_life.application.lifecycle.control_plane import Control
            c=Control(self.s.root,self.s.instance_id)
            try:
                state=c.state()
                if not state['user_stopped'] or state['active_process_run_id']:raise Conflict('stop before enabling measurement')
            finally:c.close()
        with self.s.tx():
            return self.s.event('learning.measurement_configured',payload={'enabled':enabled,'contract_id':CONTRACT,'instance_id':self.s.instance_id},source=SOURCE,lane='control')
    @staticmethod
    def commitment(labels,nonce):
        text(nonce,256)
        if len(nonce)<32:raise ContractError('label commitment needs a private nonce of at least 32 characters')
        return sha(nonce+'|'+dumps(labels))
    def _registered(self,run_ref):
        row=self._get('registered',run_ref)
        if not row:raise ContractError('unknown measurement run')
        return row['payload']
    def _live(self,registration,deadline=False):
        self.s.assert_execution_allowed();cfg=self.configuration()
        if not cfg['enabled'] or cfg['generation']!=registration['configuration_generation']:raise Forbidden('measurement disabled or superseded')
        from digital_life.application.services.learning import Learning
        from digital_life.application.autonomy.exploration import Exploration
        from digital_life.application.learning.self_feedback import SelfFeedback
        if not SelfFeedback(self.s).configuration()['enabled']:raise Forbidden('shadow recording disabled')
        exploration=Exploration(self.s).config()
        if not exploration['enabled'] or exploration['generation']!=registration['exploration_generation']:raise Forbidden('parent exploration disabled or superseded')
        parent=self.s.row('activities',registration['parent_activity_ref'])
        if parent['cancel_requested_at'] or parent['state'] in ('cancelled','failed'):raise Forbidden('measurement parent activity cancelled or failed')
        opportunity,_=Learning(self.s)._experience_opportunity(registration['opportunity_ref'])
        if not Exploration(self.s).readable_refs(opportunity['source_refs']):raise Forbidden('measurement source no longer readable')
        if deadline and registration['expires_at']<=utc():raise Forbidden('measurement deadline expired')
    @coordinated
    def register(self,opportunity_ref,cases,classes,label_commitment,actor,common_context=None,training_case_ids=(),tokens_per_call=512,wall_seconds=120):
        self._controller(actor);self.s.assert_execution_allowed();cfg=self.configuration()
        if not cfg['enabled']:raise Forbidden('measurement is disabled')
        if type(classes) is not int or not 2<=classes<=16:raise ContractError('two to sixteen classes required')
        if type(tokens_per_call) is not int or not 1<=tokens_per_call<=32768:raise ContractError('invalid measurement token reservation')
        if type(wall_seconds) is not int or not 1<=wall_seconds<=300:raise ContractError('invalid measurement deadline')
        if not isinstance(label_commitment,str) or len(label_commitment)!=64 or any(c not in '0123456789abcdef' for c in label_commitment):raise ContractError('invalid label commitment')
        if not isinstance(cases,list) or not 2<=len(cases)<=20:raise ContractError('two to twenty heldout cases required')
        if not isinstance(training_case_ids,(list,tuple)) or any(not isinstance(v,str) for v in training_case_ids):raise ContractError('invalid training case identities')
        ids=[]
        for case in cases:
            if not isinstance(case,dict) or set(case)!={'case_id','input','split'}:raise ContractError('cases expose inputs only, no labels')
            text(case['case_id'],200);text(case['input'],4000)
            if case['split'] not in ('target','retention'):raise ContractError('invalid measurement split')
            ids.append(case['case_id'])
        if len(set(ids))!=len(ids) or set(ids)&set(training_case_ids):raise ContractError('duplicate or training-overlapping heldout case ID')
        if {c['split'] for c in cases}!={'target','retention'}:raise ContractError('target and retention checks both required')
        if common_context is None:common_context={}
        if not isinstance(common_context,dict) or len(dumps(common_context).encode())>8000:raise ContractError('invalid common measurement context')
        def forbidden_keys(value):
            if isinstance(value,dict):return bool(set(value)&{'labels','oracle','ground_truth','nonce','label_commitment','cognitive_experience'}) or any(forbidden_keys(v) for v in value.values())
            if isinstance(value,list):return any(forbidden_keys(v) for v in value)
            return False
        if forbidden_keys(common_context):raise Forbidden('reserved oracle/experience keys in common context')
        from digital_life.application.services.learning import Learning
        from digital_life.application.services.cognition import Cognition
        from digital_life.application.autonomy.exploration import Exploration
        opportunity,result=Learning(self.s)._experience_opportunity(opportunity_ref)
        attempt=self.s.row('action_attempts',result['attempt_id']);intent=self.s.row('action_intents',attempt['intent_id'])
        candidate=self.s.row('decision_candidates',intent['candidate_id']);activity=self.s.row('decision_records',candidate['decision_id'])['activity_id']
        with self.s.tx():
            run_ref=identifier()
            registration={'run_ref':run_ref,'opportunity_ref':opportunity_ref,'cases':cases,'classes':classes,'label_commitment':label_commitment,
                'common_context':common_context,'experience_snapshot':Cognition(self.s).experience_snapshot(actor),
                'parent_activity_ref':activity,'exploration_generation':Exploration(self.s).binding(activity)['generation'],'max_calls':2*len(cases),'tokens_per_call':tokens_per_call,'expires_at':utc(wall_seconds),
                'configuration_generation':cfg['generation'],'measurer_version':MEASURER,'training_case_ids':list(training_case_ids),
                'scoring_policy':'target-improvement-with-retention-veto-v1','label_authority':'controller-attested heldout labels; independence not automatically provable',
                'affects_selection':False}
            self._live(registration)
            self._write('registered',run_ref,registration)
            return run_ref
    def _probabilities(self,value,classes):
        if value is None:return None
        if not isinstance(value,list) or len(value)!=classes:raise ContractError('prediction dimension mismatch')
        if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or not 0<=v<=1 for v in value):raise ContractError('invalid prediction probability')
        if not math.isclose(sum(value),1.,rel_tol=0,abs_tol=1e-8):raise ContractError('prediction probabilities must sum to one')
        return value
    def run_predictions(self,run_ref,predictor:PredictionPort,actor,*,strict_execution=None,entry=None):
        if self.s.depth:raise Conflict('prediction I/O cannot run inside a runtime write transaction')
        self._controller(actor);registration=self._registered(run_ref);self._live(registration,True)
        document=json.loads(self.s.row('activities',registration['parent_activity_ref'])['budget_json'])
        if document.get('contract')=='TL-ACTIVITY-BUDGET-1':
            from digital_life.application.learning.effect_measurement import StrictMeasurementExecution
            if not isinstance(strict_execution,StrictMeasurementExecution) or strict_execution.s is not self.s:raise Forbidden('strict measurement requires its explicit original-account execution owner')
            return strict_execution.run_predictions(self,run_ref,actor,entry)
        if strict_execution is not None:raise Forbidden('strict measurement cannot borrow a different legacy account')
        if self._get('labels',run_ref):raise Forbidden('labels already revealed; no further predictions allowed')
        model=text(predictor.name,200)
        pending=sum(not self._get('prediction',run_ref+'|'+case['case_id']+'|'+arm) for case in registration['cases'] for arm in ('without_experience','with_experience'))
        account=self.s.db.execute('SELECT * FROM activity_budget_accounts WHERE activity_id=?',(registration['parent_activity_ref'],)).fetchone()
        reservations=self.s.db.execute("SELECT * FROM budget_reservations WHERE activity_id=? AND state<>'released'",(registration['parent_activity_ref'],)).fetchall()
        if not account or len(reservations)+pending>account['attempt_limit'] or sum(r['reserved_tokens'] for r in reservations)+pending*registration['tokens_per_call']>account['token_limit']:
            raise ContractError('parent budget insufficient for remaining paired predictions')
        # Order is frozen and counterbalanced by case; no oracle enters this request.
        for index,case in enumerate(registration['cases']):
            arms=('without_experience','with_experience') if index%2==0 else ('with_experience','without_experience')
            for arm in arms:
                with dispatch_gate(self.s.root):
                    if self._get('labels',run_ref):raise Forbidden('labels already revealed; no further predictions allowed')
                    if text(predictor.name,200)!=model:raise Conflict('measurement model changed during comparison')
                    key=run_ref+'|'+case['case_id']+'|'+arm
                    prior=self._get('prediction',key)
                    if prior:
                        if prior['payload']['usage_known'] and prior['payload']['actual_tokens']>registration['tokens_per_call']:return {'state':'pending','reason':'observed-token-overage','run_ref':run_ref}
                        if not prior['payload']['usage_known']:return {'state':'pending','reason':'unknown-usage','run_ref':run_ref}
                        if prior['payload']['model']!=model:raise Conflict('measurement model changed')
                        continue
                    if self._get('dispatch',key):return {'state':'pending','reason':'unreconciled-prior-dispatch','run_ref':run_ref}
                    self._live(registration,True)
                    context=dict(registration['common_context'])
                    if arm=='with_experience':context['cognitive_experience']=registration['experience_snapshot']
                    request={'case_id':case['case_id'],'input':case['input'],'context':context,'classes':registration['classes'],
                        'remaining_seconds':(datetime.fromisoformat(registration['expires_at'].replace('Z','+00:00'))-datetime.now(timezone.utc)).total_seconds(),
                        'max_tokens':registration['tokens_per_call'],'contract_id':CONTRACT,'context_mode':'fresh_request','instruction':'Return probabilities only. No tools, labels, or learning updates.'}
                    with self.s.tx():
                        sent=self._write('dispatch',key,{'run_ref':run_ref,'case_id':case['case_id'],'arm':arm,'model':model,'request':request,'request_hash':sha(dumps(request))})
                        reserved=Budget(self.s).reserve(registration['parent_activity_ref'],sent,'thought_attempt',registration['tokens_per_call'])
                    started=time.monotonic()
                    try:
                        response=predictor.predict(json.loads(dumps(request)))
                        if not isinstance(response,dict) or set(response)-{'probabilities','actual_tokens'}:raise ContractError('invalid prediction response')
                        probabilities=self._probabilities(response.get('probabilities'),registration['classes'])
                        tokens=response.get('actual_tokens');known=type(tokens) is int and tokens>=0
                        if tokens is not None and not known:raise ContractError('invalid prediction token usage')
                        with self.s.tx():
                            Budget(self.s).settle(reserved,usage={'measurement':run_ref,'actual_tokens':tokens},unknown=not known)
                            self._write('prediction',key,{'run_ref':run_ref,'case_id':case['case_id'],'arm':arm,'model':model,'probabilities':probabilities,
                                'dispatch_ref':sent,'actual_tokens':tokens,'usage_known':known,'elapsed_seconds':time.monotonic()-started})
                        if not known:return {'state':'pending','reason':'unknown-usage','run_ref':run_ref}
                        if tokens>registration['tokens_per_call']:return {'state':'pending','reason':'observed-token-overage','run_ref':run_ref}
                    except BaseException as error:
                        with self.s.tx():
                            Budget(self.s).settle(reserved,unknown=True)
                            self._write('failed',key,{'run_ref':run_ref,'dispatch_ref':sent,'error':type(error).__name__})
                        raise
        return {'state':'predictions_sealed','run_ref':run_ref,'calls':registration['max_calls']}
    def _predictions(self,registration):
        result={}
        for case in registration['cases']:
            for arm in ('without_experience','with_experience'):
                row=self._get('prediction',registration['run_ref']+'|'+case['case_id']+'|'+arm)
                if not row:raise Conflict('both prediction arms must be sealed before labels')
                result[(case['case_id'],arm)]=row
        return result
    @coordinated
    def reveal_labels(self,run_ref,labels,nonce,actor):
        self._controller(actor);r=self._registered(run_ref);self._live(r,True)
        with self.s.tx():
            self._predictions(r)
            if not isinstance(labels,dict) or set(labels)!={c['case_id'] for c in r['cases']}:raise ContractError('heldout labels do not match registered cases')
            if any(type(v) is not int or not 0<=v<r['classes'] for v in labels.values()):raise ContractError('invalid class label')
            if self.commitment(labels,nonce)!=r['label_commitment']:raise Forbidden('labels differ from prior commitment')
            return self._write('labels',run_ref,{'run_ref':run_ref,'labels':labels,'nonce':nonce,'actor':actor,'authority':r['label_authority']})
    @staticmethod
    def brier(probabilities,label):return .5*sum((p-int(i==label))**2 for i,p in enumerate(probabilities))
    def _calculate(self,r):
        predictions=self._predictions(r);labels=self._get('labels',r['run_ref'])
        if not labels:raise Conflict('labels have not been revealed')
        label_seq=self.s.row('runtime_events',labels['id'])['event_seq']
        registered_seq=self.s.row('runtime_events',self._get('registered',r['run_ref'])['id'])['event_seq']
        for (case_id,arm),prediction in predictions.items():
            sent=self._get('dispatch',r['run_ref']+'|'+case_id+'|'+arm)
            if not sent or prediction['payload']['dispatch_ref']!=sent['id']:raise Forbidden('prediction missing its dispatch')
            sent_seq=self.s.row('runtime_events',sent['id'])['event_seq'];prediction_seq=self.s.row('runtime_events',prediction['id'])['event_seq']
            if not registered_seq<sent_seq<prediction_seq<label_seq:raise Forbidden('measurement chronology invalid')
            if sent['payload']['request_hash']!=sha(dumps(sent['payload']['request'])):raise Forbidden('prediction input hash invalid')
            wire=sent['payload']['request'];p=prediction['payload'];case=next(v for v in r['cases'] if v['case_id']==case_id)
            context=dict(r['common_context'])
            if arm=='with_experience':context['cognitive_experience']=r['experience_snapshot']
            expected={'case_id':case_id,'input':case['input'],'context':context,'classes':r['classes'],'max_tokens':r['tokens_per_call'],
                'contract_id':CONTRACT,'context_mode':'fresh_request','instruction':'Return probabilities only. No tools, labels, or learning updates.'}
            if set(wire)!=set(expected)|{'remaining_seconds'} or any(wire[k]!=v for k,v in expected.items()):raise Forbidden('prediction input differs from registered arm and frozen snapshot')
            if isinstance(wire['remaining_seconds'],bool) or not isinstance(wire['remaining_seconds'],(int,float)) or not math.isfinite(wire['remaining_seconds']) or wire['remaining_seconds']<=0:raise Forbidden('prediction dispatch has no finite remaining time')
            if any(sent['payload'].get(k)!=v or p.get(k)!=v for k,v in {'run_ref':r['run_ref'],'case_id':case_id,'arm':arm,'model':p['model']}.items()):raise Forbidden('prediction/dispatch identity differs')
            operation=sent['payload'].get('strict_attempt_ref',{}).get('id',sent['id'])
            reservation=self.s.db.execute('SELECT * FROM budget_reservations WHERE instance_id=? AND operation_ref=?',(self.s.instance_id,operation)).fetchone()
            if reservation is None or reservation['activity_id']!=r['parent_activity_ref'] or reservation['operation_kind']!='thought_attempt' or reservation['state'] not in ('settled','usage_unknown'):raise Forbidden('measurement dispatch has no original parent reservation')
            usage=json.loads(reservation['actual_usage']) if reservation['actual_usage'] else {}
            if operation!=sent['id']:
                from digital_life.application.learning.effect_measurement import check_strict_prediction
                usage=check_strict_prediction(self.s,r,sent['payload'],p,reservation)
            elif reservation['reserved_tokens']!=r['tokens_per_call']:raise Forbidden('measurement original reserved total differs')
            if type(p['usage_known']) is not bool or (p['usage_known'] and (type(p['actual_tokens']) is not int or p['actual_tokens']<0 or reservation['state']!='settled' or usage.get('actual_tokens')!=p['actual_tokens'] or usage.get('measurement')!=r['run_ref'])):raise Forbidden('prediction usage differs from actual settlement')
            if not p['usage_known'] and (p['actual_tokens'] is not None or reservation['state']!='usage_unknown'):raise Forbidden('unknown prediction usage lost its reservation')
            if isinstance(p['elapsed_seconds'],bool) or not isinstance(p['elapsed_seconds'],(int,float)) or not math.isfinite(p['elapsed_seconds']) or p['elapsed_seconds']<0:raise Forbidden('prediction elapsed time invalid')
        oracle=labels['payload']
        if self.commitment(oracle['labels'],oracle['nonce'])!=r['label_commitment']:raise Forbidden('label commitment invalid')
        unknown=[];scores=[]
        models={row['payload']['model'] for row in predictions.values()}
        if len(models)!=1:raise Forbidden('both arms must use the same model')
        for case in r['cases']:
            pair=[predictions[(case['case_id'],arm)] for arm in ('without_experience','with_experience')]
            values=[self._probabilities(v['payload']['probabilities'],r['classes']) for v in pair]
            if any(v is None for v in values) or any(not v['payload']['usage_known'] or v['payload']['actual_tokens']>r['tokens_per_call'] for v in pair):unknown.append(case['case_id']);continue
            before,after=[self.brier(v,oracle['labels'][case['case_id']]) for v in values]
            scores.append({'case_id':case['case_id'],'split':case['split'],'before_brier':before,'after_brier':after,'difference':before-after})
        gain=target_gain=regression=None
        if not unknown:
            target=[s['difference'] for s in scores if s['split']=='target'];retention=[-s['difference'] for s in scores if s['split']=='retention']
            target_gain=sum(target)/len(target);regression=max(0.,max(retention));gain=min(target_gain,-regression) if regression>0 else target_gain
        return {'run_ref':r['run_ref'],'opportunity_ref':r['opportunity_ref'],'measurer_version':MEASURER,'status':'unknown' if unknown else 'measured',
            'gain':gain,'gain_status':'unknown' if gain is None else 'positive' if gain>0 else 'negative' if gain<0 else 'measured_zero',
            'target_gain':target_gain,'retention_regression':regression,'case_scores':scores,'unknown_case_ids':unknown,'case_count':len(r['cases']),
            'prediction_refs':[v['id'] for v in predictions.values()],'labels_ref':labels['id'],'model':next(iter(models)),
            'scoring_policy':r['scoring_policy'],'parent_activity_ref':r['parent_activity_ref'],'model_port_calls':len(predictions),
            'actual_tokens':sum(v['payload']['actual_tokens'] for v in predictions.values()) if all(v['payload']['usage_known'] for v in predictions.values()) else None,
            'label_authority':r['label_authority'],'independent_cases':None,'affects_selection':False}
    @coordinated
    def evaluate(self,run_ref,actor):
        self._controller(actor);r=self._registered(run_ref);self._live(r)
        with self.s.tx():return self._write('report',run_ref,self._calculate(r))
    def checked_report(self,report_ref,require_live=False):
        event=self.s.row('runtime_events',report_ref)
        if event['source']!=SOURCE or event['event_type']!='learning.measurement_report':raise Forbidden('not a measurement report')
        value=self.s.read_artifact(event['payload_artifact_id']);r=self._registered(value['run_ref'])
        from digital_life.application.learning.effects import check_measurement_protection
        check_measurement_protection(self.s,report_ref,r,value)
        if value.get('contract_id')!=CONTRACT or value.get('instance_id')!=self.s.instance_id:raise Forbidden('measurement report scope mismatch')
        if self._get('invalidated',value['run_ref']):raise Forbidden('measurement report invalidated')
        if require_live:self._live(r)
        expected=dict(self._calculate(r),contract_id=CONTRACT,instance_id=self.s.instance_id)
        if dumps(value)!=dumps(expected):raise Forbidden('measurement report does not match sealed evidence')
        return value
    @coordinated
    def invalidate(self,run_ref,reason,actor):
        self._controller(actor);text(reason,1000);self._registered(run_ref)
        with self.s.tx():return self._write('invalidated',run_ref,{'run_ref':run_ref,'reason':reason,'actor':actor})
    @coordinated
    def adopt_shadow(self,report_ref,actor):
        self._controller(actor);report=self.checked_report(report_ref,True)
        from digital_life.application.services.learning import Learning
        from digital_life.application.services.cognition import Cognition
        with self.s.tx():
            learning=Learning(self.s);cognition=Cognition(self.s)
            assessment=learning.assess_measured_experience(report['opportunity_ref'],report_ref)
            a=self.s.read_artifact(self.s.row('runtime_events',assessment)['payload_artifact_id'])
            revision=cognition.experience_revision(a['cell']);proposal=learning.propose_experience(assessment,revision)
            return cognition.save_experience(proposal,revision)

    def status(self,actor):
        self._controller(actor)
        return {'configuration':self.configuration(),'registered_runs':[r['payload']['run_ref'] for r in self._events('registered')],
            'reports':[{'report_ref':r['id'],'run_ref':r['payload']['run_ref'],'gain_status':r['payload']['gain_status'],'gain':r['payload']['gain']} for r in self._events('report')],
            'affects_selection':False,'inference_started':False}
