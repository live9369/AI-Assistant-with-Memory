"""Controller-authored finite registry counterexample proof; default closed.

This owner recognizes one explicit structured universal over registered source
records. It does not interpret arbitrary prose or infer replacement conditions.
Its proof is an auditable local judgment, not independent scientific evidence.
"""
from copy import deepcopy
from dataclasses import dataclass,field
import json
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,utc
from digital_life.application.learning.eligibility import ref,slot
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate

MEMBERSHIP='tl.comparison.membership'
PROOF='tl.comparison.restriction'


@dataclass(frozen=True)
class VerifiedComparisonRelation:
    difference: str
    basis_refs: list
    proof_token: dict
    limitation: str
    owner: object=field(default=None,repr=False,compare=False)


def profile(s):
    key=s.rows('policy_epochs')[0]['policy_version_id'];row=s.row('policy_versions',key)
    value=json.loads(row['scope']).get('tool_learning_comparison')
    t.obj(value,('contract','enabled','domain_ids','expires_at'))
    if value['contract']!='TL-BOUNDED-COMPARISON-POLICY-1' or value['enabled'] is not True or row['authority']!=s.config()['controller']:raise Forbidden('bounded comparison policy not enabled by current controller')
    t.array(value['domain_ids'],t.string);c.validate('UTC',value['expires_at'])
    if not value['domain_ids'] or len(value['domain_ids'])>32 or value['expires_at']<=utc() or row['effective_at']>utc() or row['valid_to'] is not None and row['valid_to']<=utc():raise Forbidden('bounded comparison policy unavailable/expired')
    return key,value


def owned_source(s,source):
    c.validate('EvidenceRef',source)
    if source['source']['instance_id']!=s.instance_id or source['source']['kind']!='perception_signals':raise Forbidden('finite comparison supports only actual controller-authored source records')
    row=s.row('perception_signals',source['source']['id'])
    if row['source_actor_id']!=s.config()['controller'] or row['artifact_id']!=source['artifact']['id']:raise Forbidden('source is not the actual controller record')
    artifact=s.row('artifacts',row['artifact_id'])
    if source['digest']['hex']!=artifact['hash'] or source['media_type']!=artifact['media_type'] or source['view']['status']!='not_applicable':raise Forbidden('fixed original source artifact/view differs')
    if artifact['size']>65536:raise Forbidden('bounded original counterexample source required')
    return c.resolve_locator(source['locator'],s.read_artifact(artifact['id']))


def current_baseline(s,material):
    t.obj(material,('contract','token','claims'))
    if material['contract']!='TL-OBSERVATION-BASELINE-1' or len(material['claims'])!=1:raise Forbidden('one explicit typed baseline required')
    token=material['token'];c.validate('VersionToken',token);obj=token['object']
    if obj['instance_id']!=s.instance_id or obj['kind']!='cognition_beliefs':raise Forbidden('finite comparison requires a real current native M03 belief')
    row=s.row('cognition_beliefs',obj['id']);revision=s.row('cognition_belief_revisions',row['current_revision_id'])
    if token['revision']!=revision['revision_no'] or revision['acceptance_state'] not in ('held','accepted'):raise Conflict('baseline is not the current held/accepted M03 head')
    claim=material['claims'][0];c.validate('Claim',claim)
    if claim['predicate']!=row['predicate'] or claim['subject']!=slot(ref(s,row['subject_ref'])) or claim['scope']!=json.loads(row['scope']) or claim['value']['status']!='known' or claim['value']['value']!=json.loads(row['literal']):raise Conflict('baseline material differs from actual native content')
    expression=claim['value']['value'];t.obj(expression,('contract','quantifier','domain_ref','property','value'))
    if expression['contract']!='TL-EXPLICIT-UNIVERSAL-1' or expression['quantifier']!='all' or expression['property']!=claim['predicate']:raise Forbidden('no explicit structured universal proposition')
    c.validate('Ref',expression['domain_ref']);t.slot(expression['value'],t.json_value)
    if expression['value']['status']!='known' or expression['domain_ref']!=ref(s,row['subject_ref']):raise Forbidden('universal domain/value not established')
    return row,claim,expression


def source_plan(s,work_id):
    from digital_life.application.learning.observation import validate_plan
    work=s.row('tl_work',work_id)
    for key in ('conditions_artifact_id','method_artifact_id'):
        if s.row('artifacts',work[key])['size']>65536:raise Forbidden('bounded fixed work material required')
    conditions=s.read_artifact(work['conditions_artifact_id']);method=s.read_artifact(work['method_artifact_id'])
    if method['request_ref']['status']!='known':raise Forbidden('fixed observation plan absent')
    if s.row('artifacts',method['request_ref']['value']['id'])['size']>65536:raise Forbidden('bounded fixed comparison plan required')
    plan=validate_plan(s.read_artifact(method['request_ref']['value']['id']))
    return work,conditions,plan


def relation_state(s,relation_id,domain,source_ref,scope):
    row=s.row('world_entity_relations',relation_id)
    if row['object_id']!=domain or row['relation_type']!='member_of':raise Forbidden('actual native membership does not name this domain')
    for key in (row['subject_id'],row['object_id']):
        if s.row('world_entities',key)['resolution_status']!='resolved':raise Forbidden('ambiguous member/domain identity')
    event=s.db.execute('SELECT * FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=?',(s.instance_id,MEMBERSHIP,relation_id)).fetchone()
    if event is None:raise Forbidden('membership was not authored through the authenticated semantic owner')
    statement=s.read_artifact(event['payload_artifact_id'])
    evidence=s.row('evidence_items',row['evidence_id']);signal=s.row('perception_signals',evidence['origin_object_id'])
    active,_=profile(s)
    qualify_basis(s,active,{'source':ref(s,signal['id'])},scope)
    body=s.read_artifact(signal['artifact_id'])
    if signal['source_actor_id']!=s.config()['controller'] or evidence['artifact_id']!=signal['artifact_id'] or statement['statement']!=ref(s,signal['id']) or statement['controller']!=ref(s,s.config()['controller']) or statement['digest']!=c.fingerprint(body):raise Forbidden('membership lacks an actual bound controller statement')
    if body!={'contract':'TL-EXPLICIT-DOMAIN-MEMBERSHIP-1','member':ref(s,row['subject_id']),'domain':ref(s,row['object_id']),'source_ref':source_ref,'relation':'member_of'}:raise Conflict('actual membership/source record binding changed')
    return dict(row),statement,ref(s,event['id']),ref(s,signal['id'])


def qualify_basis(s,policy,source,scope,baseline=None):
    from digital_life.application.learning.runtime import ControllerSourceAuthority,_ControllerReadSession
    from digital_life.application.learning.eligibility import ToolLearningEligibility
    class NativeComparisonAuthority(ControllerSourceAuthority):
        def verify(self,entry,principal,token,scope,purpose,recipient,stage):
            if token['object']['kind']=='cognition_beliefs':
                self._session(entry,principal)
                active,allowed=profile(s)
                row=s.row('cognition_beliefs',token['object']['id'])
                if active!=policy or row['subject_ref'] not in allowed['domain_ids']:raise Forbidden('native baseline outside actual current domain authority')
                return None
            return super().verify(entry,principal,token,scope,purpose,recipient,stage)
    authority=NativeComparisonAuthority(s);authority.session=_ControllerReadSession(s.config()['controller'],'learn')
    principal={'actor':ref(s,s.config()['controller']),'recipient':ref(s,s.config()['controller']),'module':'M03','purpose':'learn','authorization':ref(s,policy)}
    token=baseline or {'object':source['source'],'revision':0,'epoch':0}
    eligibility=ToolLearningEligibility(s,authority)
    if s.db.in_transaction:eligibility._check(authority.session.nonce,principal,token,scope,'learn',principal['recipient'],'bounded_comparison_basis')
    else:eligibility.check(authority.session.nonce,principal,token,scope,'learn',principal['recipient'],'bounded_comparison_basis')


class ControllerComparisonAuthor:
    def __init__(self,store,bearer):self.s=store;self.bearer=bearer
    def membership(self,domain_id,member_id,source_ref,*,valid_from):
        from digital_life.application.learning.runtime import authenticate_controller
        c.validate('Ref',source_ref);c.validate('UTC',valid_from)
        with dispatch_gate(self.s.root),self.s.tx():
            actor=authenticate_controller(self.s,self.bearer);policy,allowed=profile(self.s)
            if domain_id not in allowed['domain_ids'] or source_ref['kind']!='perception_signals' or source_ref['instance_id']!=self.s.instance_id:raise Forbidden('domain/source outside current bounded policy')
            for key in (domain_id,member_id):
                if self.s.row('world_entities',key)['resolution_status']!='resolved':raise Forbidden('explicit resolved native registry identities required')
            original=self.s.row('perception_signals',source_ref['id'])
            if original['source_actor_id']!=actor:raise Forbidden('membership record source is not owned by this controller')
            body={'contract':'TL-EXPLICIT-DOMAIN-MEMBERSHIP-1','member':ref(self.s,member_id),'domain':ref(self.s,domain_id),'source_ref':deepcopy(source_ref),'relation':'member_of'}
            artifact=self.s.artifact(body)
            signal=self.s.insert('perception_signals',channel_id=original['channel_id'],source_actor_id=actor,artifact_id=artifact,received_at=utc())
            evidence=self.s.evidence(object_id=signal,artifact=artifact,method='authenticated-finite-domain-registration')
            relation=self.s.insert('world_entity_relations',subject_id=member_id,relation_type='member_of',object_id=domain_id,evidence_id=evidence,valid_from=valid_from)
            self.s.event('controller.domain_membership_authored',payload={'statement':ref(self.s,signal),'relation':ref(self.s,relation),'controller':ref(self.s,actor),'policy':ref(self.s,policy),'digest':c.fingerprint(body)},source=MEMBERSHIP,key=relation,lane='control')
            return ref(self.s,relation)
    def restriction(self,work_id,baseline_artifact,membership_ref,reason):
        from digital_life.application.learning.runtime import authenticate_controller
        t.string(reason);c.validate('Ref',baseline_artifact);c.validate('Ref',membership_ref)
        if not reason.strip() or len(reason)>2000:raise ContractError('bounded explicit counterexample reason required')
        with dispatch_gate(self.s.root),self.s.tx():
            actor=authenticate_controller(self.s,self.bearer);policy,allowed=profile(self.s)
            work,conditions,plan=source_plan(self.s,work_id)
            if baseline_artifact['kind']!='artifacts' or baseline_artifact['instance_id']!=self.s.instance_id or membership_ref['kind']!='world_entity_relations' or membership_ref['instance_id']!=self.s.instance_id:raise Forbidden('exact local basis references required')
            if self.s.row('artifacts',baseline_artifact['id'])['size']>65536:raise Forbidden('bounded baseline material required')
            material=self.s.read_artifact(baseline_artifact['id']);row,claim,expression=current_baseline(self.s,material)
            qualify_basis(self.s,policy,conditions['source'],plan['scope'])
            qualify_basis(self.s,policy,conditions['source'],claim['scope'],material['token'])
            for evidence in claim['evidence']:
                qualify_basis(self.s,policy,evidence,claim['scope']);owned_source(self.s,evidence)
            value=owned_source(self.s,conditions['source']);domain=expression['domain_ref']['id']
            if domain not in allowed['domain_ids']:raise Forbidden('universal domain outside current policy')
            relation,statement,membership_event,membership_signal=relation_state(self.s,membership_ref['id'],domain,conditions['source']['source'],plan['scope'])
            self._logical_basis(plan,claim,expression,value,relation)
            body={'contract':'TL-BOUNDED-COUNTEREXAMPLE-1','work_id':work_id,'source':conditions['source'],'scope':plan['scope'],'baseline_material':baseline_artifact,'baseline':material['token'],
                'baseline_digest':c.fingerprint(material),'membership':membership_ref,'membership_snapshot':relation,'membership_event':membership_event,'membership_signal':membership_signal,
                'counterexample_value':value,'domain':expression['domain_ref'],'policy':ref(self.s,policy),'controller':ref(self.s,actor),'reason':reason,
                'expires_at':min(work['deadline'],allowed['expires_at']),'remaining_valid_subset':'unknown','replacement_universal':False}
            key=work_id+':'+material['token']['object']['id']+':'+str(material['token']['revision'])
            event=self.s.event('controller.bounded_counterexample_authored',payload=body,source=PROOF,key=key,lane='control')
            # The proof is derived from immutable controller statements and the
            # exact native baseline version, never from a guessed text match.
            from digital_life.application.learning.engine import _dependency
            sources=[{'object':conditions['source']['source'],'revision':0,'epoch':0},material['token'],{'object':membership_signal,'revision':0,'epoch':0}]+[{'object':evidence['source'],'revision':0,'epoch':0} for evidence in claim['evidence']]
            for index,token in enumerate(sources):
                for edge in ('read','delete'):_dependency(self.s,ref(self.s,event),token,plan['scope'],edge,'/counterexample/'+str(index),'learn')
            return ref(self.s,event)
    @staticmethod
    def _logical_basis(plan,claim,expression,value,relation):
        a,b=plan['scope'],claim['scope']
        if b['domain']!=slot('registered-source-domain:'+expression['domain_ref']['id']) or b['conditions']!=slot({'domain_registry':expression['domain_ref']['id'],'quantifier':'all','as_of':a['temporal']['start']['value']}):raise Forbidden('universal has no exact known finite registry scope/conditions')
        if plan['predicate']!=expression['property'] or c.fingerprint(value)==c.fingerprint(expression['value']['value']):raise Forbidden('no same-property counterexample to the explicit universal')
        if a['unit']['status']!='known' or a['unit']!=b['unit'] or a['temporal']!=b['temporal'] or a['temporal']['bounds']!='point' or a['temporal']['start']['status']!='known':raise Forbidden('unit/time scope of universal and counterexample is not known identical')
        point=a['temporal']['start']['value']
        if relation['valid_from'] is None or relation['valid_from']>point or relation['valid_to'] is not None and relation['valid_to']<=point:raise Forbidden('membership is not valid at the actual observation scope')


class AuthenticatedComparisonOwner:
    def __init__(self,store,verifier=None):self.s=store;self.verifier=verifier
    def _resolve(self,entry,request,token):
        if self.verifier is None:raise Forbidden('actual entered runtime comparison owner is not configured')
        if self.verifier(entry,request) is not None:raise Forbidden('runtime comparison verifier must attest by successful None')
        policy,allowed=profile(self.s);work=request['work_ref']['value']['id']
        key=work+':'+token['object']['id']+':'+str(token['revision'])
        event=self.s.db.execute('SELECT * FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=?',(self.s.instance_id,PROOF,key)).fetchone()
        if event is None:raise Forbidden('no actual authenticated bounded comparison proof')
        body=self.s.read_artifact(event['payload_artifact_id']);current,conditions,plan=source_plan(self.s,work)
        if body['policy']!=ref(self.s,policy) or body['controller']!=ref(self.s,self.s.config()['controller']) or body['expires_at']<=utc() or body['source']!=conditions['source'] or body['scope']!=plan['scope'] or body['baseline']!=token:raise Forbidden('counterexample proof is stale or belongs to another source/scope')
        material=self.s.read_artifact(body['baseline_material']['id']);row,claim,expression=current_baseline(self.s,material)
        if c.fingerprint(material)!=body['baseline_digest']:raise Conflict('baseline material changed')
        relation,statement,membership_event,membership_signal=relation_state(self.s,body['membership']['id'],expression['domain_ref']['id'],conditions['source']['source'],plan['scope'])
        if relation!=body['membership_snapshot'] or expression['domain_ref']['id'] not in allowed['domain_ids']:raise Conflict('actual domain membership changed since review')
        qualify_basis(self.s,policy,conditions['source'],plan['scope'])
        qualify_basis(self.s,policy,conditions['source'],claim['scope'],material['token'])
        for evidence in claim['evidence']:
            qualify_basis(self.s,policy,evidence,claim['scope']);owned_source(self.s,evidence)
        value=owned_source(self.s,conditions['source'])
        ControllerComparisonAuthor._logical_basis(plan,claim,expression,value,relation)
        if value!=body['counterexample_value']:raise Conflict('counterexample source value changed')
        return event,body,material
    def baseline_material(self,entry,request,token):
        event,body,material=self._resolve(entry,request,token)
        return {'token':deepcopy(token),'artifact':deepcopy(body['baseline_material'])}
    def relation(self,entry,request,observation,baseline):
        event,body,material=self._resolve(entry,request,baseline['token'])
        if baseline['claims']!=material['claims'] or observation['value']['status']!='known' or observation['value']['value']!=body['counterexample_value']:raise Conflict('comparison inputs differ from the actual reviewed basis')
        token={'object':ref(self.s,event['id']),'revision':0,'epoch':0}
        return VerifiedComparisonRelation('restriction',[ref(self.s,event['id']),body['membership'],body['baseline']['object'],body['domain'],body['source']['source']],token,'Counterexample defeats this explicit universal only; the remaining valid subset and replacement conditions are unknown.',self)
    def preserved_token(self,entry,request,preserved):
        if self.verifier is None or self.verifier(entry,request) is not None:raise Forbidden('actual entered preserved-content owner is not configured')
        if preserved['kind']!='cognition_beliefs' or preserved['instance_id']!=self.s.instance_id:raise Forbidden('bounded comparison preserves only its actual original M03 baseline')
        prefix=request['work_ref']['value']['id']+':'+preserved['id']+':'
        rows=self.s.db.execute('SELECT * FROM runtime_events WHERE instance_id=? AND source=? AND substr(source_event_id,1,?)=? LIMIT 2',(self.s.instance_id,PROOF,len(prefix),prefix)).fetchall()
        if len(rows)!=1:raise Forbidden('one actual current counterexample proof required for preserved content')
        body=self.s.read_artifact(rows[0]['payload_artifact_id'])
        self._resolve(entry,request,body['baseline'])
        return deepcopy(body['baseline'])
