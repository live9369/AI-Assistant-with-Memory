"""IM08 M03 decisions and atomic C1; no work-owner impersonation or model call."""
from copy import deepcopy
import json
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,identifier,utc,dumps
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore,StorageAuthority,command_fingerprint
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.application.learning.budget import ToolLearningBudget
from digital_life.application.learning.eligibility import ToolLearningEligibility,slot,ref,same_ref,scope_key

GATES=tuple('G%02d'%n for n in range(1,9))
OWNERS={'G01':('M12',),'G02':('M03',),'G03':('M01','M13','M17'),'G04':('M03',),'G05':('M03',),'G06':('M03',),'G07':('M12',),'G08':('M03',)}
LEGACY=('cognition_beliefs','cognition_concepts')
SEVERITY={'pass':0,'not_applicable':0,'incomplete':1,'fail':2,'blocked':3}

def worsen(check,state):
    if SEVERITY[state]>SEVERITY[check['state']]:check['state']=state


class LiteralLocatorUnavailable(ContractError):
    pass


class AcceptanceAuthority(StorageAuthority):
    def read_byte_limit(self,entry,request,snapshot):return min(snapshot['remaining']['bytes'],1048576)
    def verify_proposal_access(self,entry,request,row,stage):raise Forbidden('current M03 proposal access is not configured')
    def source_token(self,entry,request,evidence):raise Forbidden('actual evidence source/version owner is not configured')
    def preserved_token(self,entry,request,preserved):raise Forbidden('preserved content owner is not configured')
    def verify_target_metadata(self,entry,request,token,scope,stage):raise Forbidden('CAS-only target metadata permission is not configured')
    def verify_read_accounting(self,entry,request,work,snapshot,read_context,stage):
        # IM11 must resolve this unique occurrence to an already reserved real
        # operation_ref on the original account; never reserve inside C1.
        # Its durable meter includes repeated commit reads, settles outside C1,
        # and holds unknown usage. A blanket stage/boolean grant is invalid.
        raise Forbidden('metered C1 review-read opportunity is not configured')
    def evaluate_gate(self,entry,request,context,gate,stage):raise Forbidden('actual gate owner is not configured')
    def verify_policy(self,entry,request,policy,stage):raise Forbidden('M12 acceptance policy authority is not configured')
    def verify_review(self,entry,request,review,stage):raise Forbidden('authenticated controller review resolver is not configured')
    def verify_group(self,entry,request,contexts,stage):raise Forbidden('atomic group authority is not configured')
    def verify_projection(self,entry,principal,context):raise Forbidden('M14/coordinator projection read authority is not configured')


class _Authority(StorageAuthority):
    def __init__(self,service):self.service=service
    def verify(self,entry,operation,request,instance_id,stage):
        grant=self.service.authority.verify(entry,operation,deepcopy(request),instance_id,stage)
        self.service._guard(entry,request,stage)
        return grant
    def project_response(self,entry,operation,request,response,instance_id,stage):
        result=self.service.authority.project_response(entry,operation,deepcopy(request),response,instance_id,stage)
        self.service._guard(entry,request,stage)
        return result


class ToolLearningAcceptance:
    def __init__(self,store,authority=None,eligibility_authority=None,clock=utc,max_members=32):
        self.s=store;self.authority=AcceptanceAuthority() if authority is None else authority
        if not isinstance(self.authority,AcceptanceAuthority):raise ContractError('trusted AcceptanceAuthority required')
        self.clock=clock;t.integer(max_members,1,128);self.max_members=max_members
        self.storage=ToolLearningStore(store,_Authority(self));self.eligibility=ToolLearningEligibility(store,eligibility_authority);self.budget=ToolLearningBudget(store)
        self._planned=None

    def _attest(self,value):
        if value is not None:raise Forbidden('owner attestation must not be a self-reported boolean')

    def _requests(self,request):
        atomic=request['payload']['atomic_group']
        if atomic['status']!='known':return [deepcopy(request)],None
        self.storage.validate_ref(atomic['value'],expected_kind='artifacts')
        if self.s.row('artifacts',atomic['value']['id'])['size']>1048576:raise Forbidden('group intent byte limit exceeded')
        group=self.storage.read_artifact(atomic['value']['id']);t.obj(group,('contract','group_key','members'))
        if group['contract']!='TL-ACCEPTANCE-GROUP-1':raise ContractError('unsupported C1 group intent')
        t.string(group['group_key'])
        if not isinstance(group['members'],list) or not 1<=len(group['members'])<=self.max_members:raise ContractError('bounded complete group members required')
        result=[];seen=set()
        for member in group['members']:
            t.obj(member,('proposal','work','review_round','policy','review','expected','control','budget'))
            if member['proposal']['id'] in seen:raise ContractError('duplicate atomic group proposal')
            seen.add(member['proposal']['id'])
            envelope=deepcopy(request);envelope.update(work_ref=slot(member['work']),expected=member['expected'],control=member['control'],budget=member['budget'])
            envelope['payload'].update(proposal=member['proposal'],review_round=member['review_round'],policy=member['policy'],review=member['review'])
            c.validate_request('decide_proposal',envelope);result.append(envelope)
        primary=next((item for item in result if same_ref(item['payload']['proposal'],request['payload']['proposal'])),None)
        if primary is None or command_fingerprint(primary)!=command_fingerprint(request):raise Conflict('primary request differs from fixed atomic group intent')
        return result,group

    def _load(self,entry,request,stage):
        self.storage.validate_ref(request['payload']['proposal'],expected_kind='tl_product')
        row=self.s.row('tl_product',request['payload']['proposal']['id'])
        self._attest(self.authority.verify_proposal_access(entry,deepcopy(request),dict(row),stage))
        work=self.s.row('tl_work',row['work_id']);snapshot=self.budget.check_work(work['id'],request['budget'])
        read_limit=self.authority.read_byte_limit(entry,deepcopy(request),deepcopy(snapshot));t.integer(read_limit,0,min(request['budget']['max_bytes'],1048576))
        read_context={'contract':'TL-C1-READ-CONTEXT-1','occurrence_id':identifier(),'request_fingerprint':command_fingerprint(request),'work_ref':ref(self.s,work['id']),'account_ref':request['budget']['account_ref'],'stage':stage,'deadline':min(work['deadline'],request['budget']['deadline']),'byte_cap':read_limit,'scan_cap':128,'claim_cap':64}
        self._attest(self.authority.verify_read_accounting(entry,deepcopy(request),deepcopy(work),deepcopy(snapshot),deepcopy(read_context),stage))
        if self.s.row('artifacts',row['payload_artifact_id'])['size']>read_limit:raise Forbidden('proposal byte scan limit exceeded')
        product=self.storage.read_artifact(row['payload_artifact_id'],'Product')
        if row['product_type']!='UpdateProposal' or product['product_type']!='UpdateProposal' or product['product_id']!=row['id'] or product['work_ref']['id']!=row['work_id'] or product['processing_identity']['hex']!=row['processing_identity']:
            raise ContractError('authoritative proposal mapping mismatch')
        if row['work_id']!=request['work_ref']['value']['id']:raise Forbidden('proposal belongs to another work')
        self.storage.validate_ref(product['producer']['actor']);self.storage.validate_ref(product['producer']['authorization'])
        work=self.s.row('tl_work',row['work_id'])
        self.s.assert_execution_allowed()
        if request['principal']['module']!='M03' or request['principal']['purpose']!='accept':raise Forbidden('C1 requires actual M03 accept principal')
        if request['control']['cancelled'] or self.clock()>=min(work['deadline'],request['budget']['deadline']):raise Forbidden('C1 cancelled or deadline exhausted')
        for key in ('source_activity_id','learning_activity_id'):
            activity=self.s.row('activities',work[key])
            if activity['cancel_requested_at'] or activity['state']=='cancelled':raise Forbidden('C1 source or processing activity cancelled')
        snapshot=self.budget.check_work(work['id'],request['budget'])
        hard=[r for r in snapshot['block_reasons'] if r not in ('attempts_exhausted','work_waiting','work_blocked','work_failed','work_stopped','work_completed','work_no_change','work_rejected')]
        if hard:raise Forbidden(','.join(hard))
        if request['payload']['review_round']!=work['review_round']:raise Conflict('decision cannot silently change the current review round')
        sources=[]
        if len(product['body']['preserved_content'])>128:raise Forbidden('preserved content scan limit exceeded')
        if len(product['body']['claims'])>64 or sum(len(claim['evidence']) for claim in product['body']['claims'])>128:raise Forbidden('proposal claim/evidence scan limit exceeded')
        for claim in product['body']['claims']:
            for evidence in claim['evidence']:
                token=self.authority.source_token(entry,deepcopy(request),deepcopy(evidence));c.validate('VersionToken',token)
                if not same_ref(token['object'],evidence['source']):raise ContractError('source resolver changed evidence identity')
                self._qualify(entry,request,token,claim['scope'],stage);sources.append({'token':deepcopy(token),'scope':deepcopy(claim['scope'])})
        if product['body']['atomic_group']['status']=='known' and product['body']['atomic_group']!=request['payload']['atomic_group']:raise Conflict('proposal atomic group differs from current group intent')
        target=product['body']['target']
        if target['mode']=='existing':self._target_metadata(entry,request,target['expected']['value'],product['body']['claims'][0]['scope'],stage)
        inherited=list(product['derivation_links'])+list(product['access_dependencies'])
        for claim in product['body']['claims']:
            for evidence in claim['evidence']:inherited.extend(evidence['access_dependencies'])
        if len(inherited)>128:raise Forbidden('inherited dependency scan limit exceeded')
        for dependency in inherited:
            c.validate('Dependency',dependency)
            if dependency['relation']!='delete':self._qualify(entry,request,dependency['expected'],product['body']['claims'][0]['scope'],stage)
            else:self.eligibility.validate_token(entry,request['principal'],dependency['expected'],stage+'_delete_retention')
        for preserved in product['body']['preserved_content']:
            token=self.authority.preserved_token(entry,deepcopy(request),deepcopy(preserved));c.validate('VersionToken',token)
            if not same_ref(token['object'],preserved):raise ContractError('preserved resolver changed object')
            self._qualify(entry,request,token,product['body']['claims'][0]['scope'],stage);sources.append({'token':deepcopy(token),'scope':deepcopy(product['body']['claims'][0]['scope']),'read_byte_limit':read_limit,'inherited_dependencies':deepcopy(inherited)})
        return {'request':deepcopy(request),'row':dict(row),'product':product,'work':work,'sources':sources,'scope':deepcopy(product['body']['claims'][0]['scope']),'read_byte_limit':read_limit,'inherited_dependencies':deepcopy(inherited)}

    def _target_metadata(self,entry,request,token,scope,stage):
        # CAS/identity inspection is not a read of the old factual payload.
        self.eligibility.validate_token(entry,request['principal'],token,stage+'_cas_metadata')
        self._attest(self.authority.verify_target_metadata(entry,deepcopy(request),deepcopy(token),deepcopy(scope),stage))
        if self.eligibility.current_epoch(token['object'],scope)!=token['epoch']:raise Conflict('target metadata scope epoch is stale')
        rows=self.s.db.execute("SELECT b.*,ch.payload_artifact_id FROM tl_barrier b JOIN tl_change ch ON ch.instance_id=b.instance_id AND ch.id=b.change_id WHERE b.instance_id=? AND b.source_ref_id=? AND b.state='active' ORDER BY b.id LIMIT 129",(self.s.instance_id,token['object']['id'])).fetchall()
        if len(rows)>128:raise Forbidden('target barrier scan limit exceeded')
        p=request['principal']
        for row in rows:
            payload=self.storage.read_artifact(row['payload_artifact_id'])
            if payload['purposes'] and p['purpose'] not in payload['purposes']:continue
            applies=self.eligibility.authority.barrier_applies(entry,deepcopy(p),dict(row,access_mode='cas_metadata'),deepcopy(payload),deepcopy(scope),p['purpose'],deepcopy(p['recipient']))
            if applies is not None and type(applies) is not bool:raise ContractError('target barrier applicability must be true/false/unknown')
            if applies is not False and self.eligibility.overlaps(entry,p,self.storage.read_artifact(row['scope_artifact_id'],'Scope'),scope):raise Forbidden('direct target metadata barrier')
        self.s.assert_execution_allowed()

    def _qualify(self,entry,request,token,scope,stage):
        p=request['principal']
        if self.s.db.in_transaction:
            # This private path is used only inside our already-held C1 gate.
            return self.eligibility._check(entry,p,token,scope,p['purpose'],p['recipient'],stage)
        return self.eligibility.check(entry,p,token,scope,p['purpose'],p['recipient'],stage)

    def _guard(self,entry,request,stage):
        requests,group=self._requests(request);contexts=[self._load(entry,item,stage) for item in requests]
        if group is not None:self._attest(self.authority.verify_group(entry,deepcopy(request),deepcopy(contexts),stage))
        if self._planned is not None and stage in ('commit','replay'):
            for context in contexts:
                planned=self._planned.get(context['row']['id'])
                if planned and planned['operation']=='accept':
                    context['_target_snapshot']=deepcopy(planned['target'])
                    fresh=self._evaluate(entry,context,stage)
                    if fresh['operation']!='accept':raise Forbidden('C1 eligibility changed before commit')
        self.s.assert_execution_allowed()
        if self._planned is not None and stage=='commit':
            for planned in self._planned.values():
                if 'written_head' in planned:
                    actual=self.s.row('tl_content',planned['written_content'])
                    if actual['head_revision_id']!=planned['written_head'] or actual['row_revision']!=planned['written_row_revision']:raise Conflict('native head changed after C1 write')
        self.s.assert_execution_allowed()
        if any(self.clock()>=min(context['work']['deadline'],context['request']['budget']['deadline']) for context in contexts):raise Forbidden('C1 deadline expired after final owner callback')
        return contexts,group

    def _policy(self,entry,context,stage):
        request=context['request'];self.storage.validate_ref(request['payload']['policy'],expected_kind='policy_versions')
        row=self.s.row('policy_versions',request['payload']['policy']['id'])
        if len(row['scope'].encode())>65536:raise Forbidden('acceptance policy byte limit exceeded')
        profile=json.loads(row['scope']).get('tool_learning_acceptance')
        if not isinstance(profile,dict) or profile.get('contract')!='TL-ACCEPT-REVIEW-1':return None
        t.obj(profile,('contract','content_kinds','proposal_operations','require_controller_review','expires_at'))
        for values,allowed in ((profile['content_kinds'],('source_report','world_claim','method_claim','causal_claim')),(profile['proposal_operations'],('add','confirm','temporal_add','correct','restrict','mark_conflict'))):
            if not isinstance(values,list) or not values:raise ContractError('policy requires explicit bounded enum lists')
            for value in values:t.enum(value,allowed)
        if profile['require_controller_review'] is not True:raise Forbidden('this policy version cannot authorize unsupervised acceptance')
        c.validate('UTC',profile['expires_at'])
        if profile['expires_at']<=self.clock() or row['effective_at']>self.clock() or row['valid_to'] is not None and row['valid_to']<=self.clock():return None
        current=self.s.db.execute('SELECT max(version) FROM policy_versions WHERE instance_id=? AND effective_at<=?',(self.s.instance_id,self.clock())).fetchone()[0]
        if row['version']!=current:return None
        body=context['product']['body']
        if body['target']['content_kind'] not in profile['content_kinds'] or body['operation'] not in profile['proposal_operations']:return None
        self._attest(self.authority.verify_policy(entry,deepcopy(request),{'row':row,'profile':profile},stage))
        return profile

    def _review(self,entry,context,stage):
        request=context['request'];review=request['payload']['review']
        if review['status']!='known':return None
        self.storage.validate_ref(review['value'],expected_kind='perception_signals');signal=self.s.row('perception_signals',review['value']['id'])
        if signal['source_actor_id']!=self.s.config()['controller']:raise Forbidden('review does not originate from the current controller')
        if self.s.row('artifacts',signal['artifact_id'])['size']>65536:raise Forbidden('controller review byte limit exceeded')
        body=self.storage.read_artifact(signal['artifact_id']);t.obj(body,('contract','proposal','proposal_digest','review_round','expected','native_expected','actual_scope','policy','atomic_group','verdict','expires_at'))
        if body['contract']!='TL-CONTROLLER-CONTENT-REVIEW-1':raise ContractError('not a content review record')
        c.validate('UTC',body['expires_at']);t.enum(body['verdict'],('accept','candidate','defer','reject','conflict','reuse'))
        actual={'proposal':request['payload']['proposal'],'proposal_digest':c.fingerprint(context['product']),'review_round':request['payload']['review_round'],
                'expected':context['product']['body']['target']['expected'],'actual_scope':context['scope'],'policy':request['payload']['policy'],'atomic_group':request['payload']['atomic_group']}
        if any(body[key]!=value for key,value in actual.items()):raise Conflict('controller review is not bound to this proposal, baseline, scope, policy, group and round')
        c.validate('VersionToken',body['native_expected']['value']) if body['native_expected']['status']=='known' else t.slot(body['native_expected'],lambda v:c.validate('VersionToken',v))
        target=context.get('_target_snapshot') or self._target(context)
        if target['native'] is not None and target['previous'] is not None:
            native_expected=body['native_expected']
            if native_expected['status']!='known' or native_expected['value']['object']['id']!=target['native']['id'] or native_expected['value']['object']['kind']!='tl_content' or native_expected['value']['revision']!=target['previous']['revision_no']:raise Conflict('review must bind the actual native head version')
            self._target_metadata(entry,request,native_expected['value'],context['scope'],stage)
        elif body['native_expected']['status']!='not_applicable':raise Conflict('review must not invent an unrelated bridge head')
        if body['expires_at']<=self.clock():return None
        self._attest(self.authority.verify_review(entry,deepcopy(request),{'signal':signal,'body':body},stage))
        return body

    def _literal(self,evidence,remaining):
        self.storage.validate_ref(evidence['artifact'],expected_kind='artifacts');row=self.s.row('artifacts',evidence['artifact']['id'])
        if row['hash']!=evidence['digest']['hex'] or row['media_type']!=evidence['media_type']:raise ContractError('source digest/media differs from real artifact')
        remaining[0]-=row['size']
        if remaining[0]<0:raise Forbidden('literal byte scan limit exceeded')
        view=self.storage.read_artifact(row['id'])
        if evidence['view']['status']=='known':
            if evidence['view_digest']['status']!='known':raise ContractError('bound parsed view digest missing')
            self.storage.validate_ref(evidence['view']['value'],expected_kind='artifacts');parsed=self.s.row('artifacts',evidence['view']['value']['id'])
            if parsed['hash']!=evidence['view_digest']['value']['hex']:raise ContractError('parsed view digest mismatch')
            remaining[0]-=parsed['size']
            if remaining[0]<0:raise Forbidden('literal view byte scan limit exceeded')
            view=self.storage.read_artifact(parsed['id'])
        elif evidence['view']['status']!='not_applicable':raise ContractError('unavailable view cannot be replaced by the original')
        elif evidence['view_digest']['status']=='known' and evidence['view_digest']['value']['hex']!=row['hash']:raise ContractError('original view digest mismatch')
        if isinstance(view,bytes) and evidence['locator']['kind']=='text_range':
            if evidence['encoding']['status']!='known' or evidence['encoding']['value'].lower() not in ('utf-8','utf8'):raise ContractError('unsupported text decoding')
            view=view.decode('utf-8')
        try:return c.resolve_locator(evidence['locator'],view)
        except (ContractError,KeyError,IndexError,UnicodeError) as exc:raise LiteralLocatorUnavailable('literal locator does not resolve') from exc

    def _target(self,context):
        body=context['product']['body'];target=body['target'];native=None;legacy=None;conflict=False;previous=None
        if target['mode']=='existing':
            expected=target['expected']['value'];obj=target['object']['value'];self.storage.validate_ref(obj)
            if obj['kind']=='tl_content':native=self.s.row('tl_content',obj['id'])
            elif obj['kind'] in LEGACY:
                legacy=deepcopy(expected)
                row=self.s.row(obj['kind'],obj['id']);rev=self.s.row('cognition_belief_revisions' if obj['kind']=='cognition_beliefs' else 'cognition_concept_revisions',row['current_revision_id'])
                if rev['revision_no']!=expected['revision']:conflict=True
                bridges=self.s.db.execute("SELECT d.*,c.content_kind,c.id AS native_id FROM tl_dependency d JOIN tl_content_revision r ON r.instance_id=d.instance_id AND r.id=d.consumer_ref_id JOIN tl_content c ON c.instance_id=r.instance_id AND c.id=r.content_id WHERE d.instance_id=? AND d.source_ref_id=? AND d.relation='derive' ORDER BY d.id LIMIT 129",(self.s.instance_id,obj['id'])).fetchall()
                if len(bridges)>128:raise Forbidden('legacy bridge scan limit exceeded')
                matches={}
                for bridge in bridges:
                    meta=self.eligibility._metadata(bridge)
                    if bridge['field_path']=='/_bridges/TL-LEGACY-COGNITION-BRIDGE-1' and meta.get('contract')=='TL-DEPENDENCY-1' and bridge['content_kind']==target['content_kind']:matches[bridge['native_id']]=bridge
                if len(matches)>1:raise Conflict('legacy target maps to multiple native content identities')
                if matches:native=self.s.row('tl_content',next(iter(matches)))
            else:raise Forbidden('target is not owned by M03')
            if native is not None:
                if native['content_kind']!=target['content_kind']:raise Conflict('target kind cannot change in place')
                if native['head_revision_id']:
                    previous=self.s.row('tl_content_revision',native['head_revision_id'])
                    if obj['kind']=='tl_content' and previous['revision_no']!=expected['revision']:conflict=True
        else:
            prior=self.s.db.execute('SELECT r.content_id FROM tl_decision d JOIN tl_content_revision r ON r.instance_id=d.instance_id AND r.id=d.content_revision_id WHERE d.instance_id=? AND d.proposal_id=? ORDER BY d.review_round DESC LIMIT 1',(self.s.instance_id,context['row']['id'])).fetchone()
            if prior:
                native=self.s.row('tl_content',prior['content_id'])
                if native['head_revision_id']:previous=self.s.row('tl_content_revision',native['head_revision_id'])
        return {'native':native,'legacy':legacy,'previous':previous,'conflict':conflict}

    def _evaluate(self,entry,context,stage):
        request=context['request'];checks={};body=context['product']['body'];target=context.get('_target_snapshot') or self._target(context)
        context=deepcopy(context);context['target_snapshot']=deepcopy(target)
        if target['previous'] is not None:
            previous_token={'object':ref(self.s,target['previous']['content_id'],'tl_content'),'revision':target['previous']['revision_no'],'epoch':self.eligibility.current_epoch(ref(self.s,target['previous']['content_id'],'tl_content'),context['scope'])}
            self._target_metadata(entry,request,previous_token,context['scope'],stage)
        for gate in GATES:
            check=self.authority.evaluate_gate(entry,deepcopy(request),deepcopy(context),gate,stage)
            t.validate_check(check,states=('pass','fail','incomplete','blocked','not_applicable'))
            if check['checker']['module'] not in OWNERS[gate]:raise Forbidden('gate receipt does not belong to its actual domain')
            for key in ('actor','recipient','authorization'):self.storage.validate_ref(check['checker'][key])
            for basis in check['basis_refs']:self.storage.validate_ref(basis)
            if check['at']>self.clock():raise ContractError('gate receipt claims a future check')
            checks[gate]=deepcopy(check)
        policy=self._policy(entry,context,stage);review=self._review(entry,context,stage)
        if policy is None or review is None:worsen(checks['G07'],'incomplete')
        remaining=[context['read_byte_limit']]
        # A literal match cannot upgrade the content category or unknown value.
        for claim in body['claims']:
            if claim['scope']['claim_target']!=body['target']['content_kind']:worsen(checks['G04'],'fail')
            if claim['form']=='source_report':
                if body['target']['content_kind']!='source_report':worsen(checks['G04'],'fail')
                if claim['value']['status']!='known':worsen(checks['G04'],'incomplete')
                else:
                    supported=False;missing_locator=False
                    for evidence in claim['evidence']:
                        try:value=self._literal(evidence,remaining)
                        except LiteralLocatorUnavailable:missing_locator=True;continue
                        if not isinstance(value,bytes) and c.fingerprint(value)==c.fingerprint(claim['value']['value']):supported=True
                    if not supported:
                        worsen(checks['G04'],'fail')
                        if missing_locator:worsen(checks['G03'],'incomplete')
            elif not checks['G04']['basis_refs']:worsen(checks['G04'],'incomplete')
        if any(scope_key(item['scope'])!=scope_key(context['scope']) for item in body['claims']):worsen(checks['G08'],'incomplete')
        if target['conflict']:worsen(checks['G05'],'fail')
        verdict=review['verdict'] if review is not None else 'candidate'
        if any(item['state']=='blocked' for item in checks.values()):raise Forbidden('actual gate owner blocks this C1')
        elif target['conflict']:operation='conflict'
        elif any(item['state']=='fail' for item in checks.values()):operation='reject'
        elif policy is None or review is None:operation='candidate'
        elif verdict in ('reject','defer','candidate','conflict'):operation=verdict
        elif any(item['state']!='pass' for item in checks.values()):operation='candidate'
        else:operation=verdict
        if operation=='reuse':
            previous=target['previous']
            if previous is None or previous['status']!='accepted':operation='defer'
            else:
                previous_token={'object':ref(self.s,previous['content_id'],'tl_content'),'revision':previous['revision_no'],'epoch':self.eligibility.current_epoch(ref(self.s,previous['content_id'],'tl_content'),context['scope'])}
                self._qualify(entry,request,previous_token,context['scope'],stage)
                old=self.storage.read_artifact(previous['payload_artifact_id'])
                def semantic(claims):return [{k:v for k,v in claim.items() if k!='claim_id'} for claim in claims]
                if old.get('contract')!='TL-CONTENT-1' or semantic(old['claims'])!=semantic(body['claims']):operation='reject'
        return {'context':context,'checks':checks,'operation':operation,'target':target,'policy':policy,'review':review}

    def decide(self,entry,envelope):
        c.validate_request('decide_proposal',envelope);request=c.loads(dumps(envelope))
        if self.s.db.in_transaction:raise Conflict('C1 requires gate before independent main transaction')
        with dispatch_gate(self.s.root):
            self._planned=None
            try:return self.storage.execute(entry,'decide_proposal',request,lambda tx:self._commit(tx,entry,request))
            finally:self._planned=None

    def _prior(self,context):
        request=context['request'];row=self.s.db.execute('SELECT * FROM tl_decision WHERE instance_id=? AND proposal_id=? AND review_round=?',(self.s.instance_id,context['row']['id'],request['payload']['review_round'])).fetchone()
        if row is None:return None
        event=self.s.db.execute('SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND source=? AND source_event_id=?',(self.s.instance_id,'tl.acceptance.decision',context['row']['id']+':'+str(row['review_round']))).fetchone()
        if event is None or self.storage.read_artifact(event[0])['request_fingerprint']!=command_fingerprint(request):raise Conflict('review round already has a different immutable decision')
        return dict(row)

    def _commit(self,tx,entry,request):
        contexts,group=self._guard(entry,request,'C1_begin');prior=[self._prior(context) for context in contexts]
        if any(prior):
            if not all(prior):raise Conflict('atomic group is only partially previously decided')
            return self._response(request,[row['id'] for row in prior],'reused')
        for context in contexts:
            work=context['work']
            if work['state']!='awaiting_decision' or work['phase']!='decide':raise Forbidden('only currently awaiting work may receive a new C1')
        native_targets=[target['native']['id'] for target in (self._target(context) for context in contexts) if target['native'] is not None]
        if len(native_targets)!=len(set(native_targets)):raise Conflict('atomic group repeats a native target')
        plans=[self._evaluate(entry,context,'prepare') for context in contexts]
        if group is not None and any(plan['operation']!='accept' for plan in plans):
            for plan in plans:
                if plan['operation']=='accept':plan['operation']='candidate';plan['checks']['G08']['state']='incomplete'
                if plan['operation']=='reuse':plan['operation']='defer'
        self._planned={plan['context']['row']['id']:plan for plan in plans}
        group_id=identifier() if group is not None and all(plan['operation']=='accept' for plan in plans) else None
        allocated=[]
        for plan in plans:
            target=plan['target'];context=plan['context'];operation=plan['operation'];native=target['native'];previous=target['previous']
            content=native['id'] if native else identifier() if operation in ('accept','candidate') else None
            revision=identifier() if operation in ('accept','candidate') else previous['id'] if previous and operation in ('reuse','conflict') else None
            number=self.s.db.execute('SELECT coalesce(max(revision_no),0)+1 FROM tl_content_revision WHERE instance_id=? AND content_id=?',(self.s.instance_id,content)).fetchone()[0] if operation in ('accept','candidate') else None
            allocated.append({'plan':plan,'id':identifier(),'content':content,'revision':revision,'number':number,'handoff':identifier() if operation=='accept' else None})
        if group_id:
            members={'contract':'TL-C1-GROUP-MEMBERS-1','intent':request['payload']['atomic_group']['value'],
                'members':[{'proposal':ref(self.s,item['plan']['context']['row']['id']),'content':{'instance_id':self.s.instance_id,'id':item['content'],'kind':'tl_content','revision':slot()},'content_revision_id':item['revision'],'revision_no':item['number'],'format_version':'TL-TEXT-1','handoff_id':item['handoff']} for item in allocated]}
            tx.insert('tl_group',id=group_id,group_key=group['group_key'],members_artifact_id=tx.put_artifact(members),state='pending',row_revision=0)
        ids=[]
        for item in allocated:
            self._write(tx,entry,item,group_id);ids.append(item['id'])
        return self._response(request,ids)

    def _write(self,tx,entry,item,group_id):
        plan=item['plan'];context=plan['context'];request=context['request'];target=plan['target'];operation=plan['operation'];product=context['product'];body=product['body'];previous=target['previous']
        handoffs=[]
        if operation=='reuse':handoffs=[ref(self.s,row[0],'tl_handoff') for row in self.s.db.execute('SELECT id FROM tl_handoff WHERE instance_id=? AND content_revision_id=? ORDER BY id',(self.s.instance_id,item['revision']))]
        elif item['handoff']:handoffs=[{'instance_id':self.s.instance_id,'id':item['handoff'],'kind':'tl_handoff','revision':slot()}]
        decision={'id':item['id'],'work_ref':deepcopy(request['work_ref']['value']),'proposal_ref':deepcopy(request['payload']['proposal']),'review_round':request['payload']['review_round'],'actor':deepcopy(request['principal']),'policy_ref':deepcopy(request['payload']['policy']),
            'checks':plan['checks'],'operation':operation,'actual_scope':deepcopy(context['scope']),'content_ref':slot({'instance_id':self.s.instance_id,'id':item['content'],'kind':'tl_content','revision':slot()}) if item['content'] else slot(),
            'revision_ref':slot({'instance_id':self.s.instance_id,'id':item['revision'],'kind':'tl_content_revision','revision':slot()}) if item['revision'] else slot(),
            'previous':slot({'object':ref(self.s,previous['content_id'],'tl_content'),'revision':previous['revision_no'],'epoch':self.eligibility.current_epoch(ref(self.s,previous['content_id'],'tl_content'),context['scope'])}) if previous else slot(),
            'reason':'none' if operation in ('accept','reuse') else 'unsupported' if plan['policy'] is None else 'incomplete_source','coverage':deepcopy(product['body']['claims'][0]['scope']['coverage']),'handoff_refs':handoffs,'created_at':self.clock()}
        if operation in ('accept','candidate'):
            if target['native'] is None:tx.insert('tl_content',id=item['content'],content_kind=body['target']['content_kind'],head_revision_id=None,row_revision=0)
            content_payload={'contract':'TL-CONTENT-1','proposal':deepcopy(request['payload']['proposal']),'proposal_digest':c.fingerprint(product),'claims':deepcopy(body['claims']),'scope':deepcopy(context['scope']),
                'preserved_content':deepcopy(body['preserved_content']),'unresolved_items':deepcopy(body['unresolved_items']),'source_versions':deepcopy(context['sources']),'legacy_expected':deepcopy(target['legacy']),
                'policy':deepcopy(request['payload']['policy']),'review':deepcopy(request['payload']['review']),'decision_id':item['id']}
            tx.insert('tl_content_revision',id=item['revision'],content_id=item['content'],revision_no=item['number'],decision_id=item['id'],product_id=context['row']['id'],payload_artifact_id=tx.put_artifact(content_payload),status='accepted' if operation=='accept' else 'candidate',previous_revision_id=previous['id'] if previous else None)
            if operation=='accept' or target['native'] is None:
                tx.cas_update('tl_content',item['content'],target['native']['row_revision'] if target['native'] else 0,head_revision_id=item['revision'])
        if operation in ('accept','candidate'):
            actual=self.s.row('tl_content',item['content']);plan.update(written_content=item['content'],written_head=actual['head_revision_id'],written_row_revision=actual['row_revision'])
        if item['handoff']:
            tx.insert('tl_handoff',id=item['handoff'],work_id=context['work']['id'],content_revision_id=item['revision'],decision_id=item['id'],group_id=group_id,format_version='TL-TEXT-1',input_fingerprint=c.fingerprint({'revision':item['revision'],'payload':content_payload}),state='pending',lease_generation=0,attempts=0,deadline=min(context['work']['deadline'],request['budget']['deadline']),budget_account_id=context['work']['budget_account_id'],row_revision=0)
        c.validate('Decision',decision)
        tx.insert('tl_decision',id=item['id'],work_id=context['work']['id'],proposal_id=context['row']['id'],review_round=request['payload']['review_round'],decision_artifact_id=tx.put_artifact(decision,'Decision'),operation=operation,content_revision_id=item['revision'],policy_ref_id=request['payload']['policy']['id'],created_at=decision['created_at'])
        if operation in ('accept','candidate'):
            for index,source in enumerate(context['sources']):self._dependency(tx,item['revision'],source['token'],source['scope'],'read','/sources/'+str(index),request)
            proposal_token={'object':deepcopy(request['payload']['proposal']),'revision':0,'epoch':self.eligibility.current_epoch(request['payload']['proposal'],context['scope'])}
            self._dependency(tx,item['revision'],proposal_token,context['scope'],'derive','/actual_proposal',request)
            for index,dependency in enumerate(context['inherited_dependencies']):self._dependency(tx,item['revision'],dependency['expected'],context['scope'],dependency['relation'],'/inherited/'+str(index),request)
            if target['legacy'] is not None:self._dependency(tx,item['revision'],target['legacy'],context['scope'],'derive','/legacy_bridge',request,bridge=True)
        event=self.s.event('acceptance.decision',payload={'request_fingerprint':command_fingerprint(request),'decision_id':item['id'],'operation':operation},source='tl.acceptance.decision',key=context['row']['id']+':'+str(request['payload']['review_round']),activity=context['work']['learning_activity_id'])
        proposal_token={'object':deepcopy(request['payload']['proposal']),'revision':0,'epoch':self.eligibility.current_epoch(request['payload']['proposal'],context['scope'])}
        copies=[ref(self.s,item['id'],'tl_decision'),ref(self.s,self.s.row('tl_decision',item['id'])['decision_artifact_id'],'artifacts'),ref(self.s,event,'runtime_events'),ref(self.s,self.s.row('runtime_events',event)['payload_artifact_id'],'artifacts')]
        for consumer in copies:self._copy_dependency(tx,consumer,proposal_token,context['scope'],request)
        if operation in ('accept','candidate'):
            body=self.s.row('tl_content_revision',item['revision'])['payload_artifact_id']
            token={'object':ref(self.s,item['content'],'tl_content'),'revision':item['number'],'epoch':self.eligibility.current_epoch(ref(self.s,item['content'],'tl_content'),context['scope'])}
            self._copy_dependency(tx,ref(self.s,body,'artifacts'),token,context['scope'],request)

    def _copy_dependency(self,tx,consumer,token,scope,request):
        revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.s.instance_id,token['object']['id'],token['revision'])).fetchone()
        for relation in ('read','delete'):
            path='/retained_material';dependency={'target':deepcopy(token['object']),'relation':relation,'expected':deepcopy(token),'consumer_purpose':'accept'}
            metadata={'contract':'TL-DEPENDENCY-1','consumer':consumer,'dependency':dependency,'field_path':path,'scope':deepcopy(scope)}
            tx.insert('tl_dependency',id=identifier(),consumer_ref_id=consumer['id'],source_ref_id=token['object']['id'],source_revision_id=revision[0] if revision else None,relation=relation,purpose='accept',expected_epoch=token['epoch'],field_path=path,metadata_artifact_id=tx.put_artifact(metadata))

    def _dependency(self,tx,consumer,token,scope,relation,path,request,bridge=False):
        dependency={'target':deepcopy(token['object']),'relation':relation,'expected':deepcopy(token),'consumer_purpose':'accept'}
        metadata={'contract':'TL-DEPENDENCY-1','consumer':{'instance_id':self.s.instance_id,'id':consumer,'kind':'tl_content_revision','revision':slot()},'dependency':dependency,'field_path':path,'scope':deepcopy(scope)}
        # A reserved field_path identifies the bridge without extending the
        # closed TL-DEPENDENCY-1 metadata contract.
        if bridge:
            path='/_bridges/TL-LEGACY-COGNITION-BRIDGE-1';metadata['field_path']=path
        revision=self.s.db.execute('SELECT id FROM object_revision_registry WHERE instance_id=? AND object_id=? AND revision_no=?',(self.s.instance_id,token['object']['id'],token['revision'])).fetchone()
        tx.insert('tl_dependency',consumer_ref_id=consumer,source_ref_id=token['object']['id'],source_revision_id=revision[0] if revision else None,relation=relation,purpose='accept',expected_epoch=token['epoch'],field_path=path,metadata_artifact_id=tx.put_artifact(metadata))

    def _response(self,request,decisions,disposition='applied'):
        return {'command_id':request['command_id'],'operation':'decide_proposal','disposition':disposition,'owner':'M03','result_refs':[ref(self.s,key,'tl_decision') for key in decisions],'current':slot(),'reason':'none','error_code':'NONE',
            'coverage':{'state':'complete','domain':slot('explicit C1 proposal set'),'scanned':len(decisions),'limit':self.max_members,'truncated':False,'missing':[]},'retry':{'allowed':False,'condition':slot(),'resume_work':slot()},'committed_at':slot(self.clock())}

    def work_projection(self,entry,principal,work):
        c.validate('Principal',principal);self.storage.validate_ref(work,expected_kind='tl_work')
        row=self.s.row('tl_work',work['id'])
        if principal['module'] not in ('M14','coordinator'):raise Forbidden('only the actual work owner may request coordination projection')
        for field in ('actor','recipient','authorization'):self.storage.validate_ref(principal[field])
        decisions=[dict(item) for item in self.s.db.execute('SELECT * FROM tl_decision WHERE instance_id=? AND work_id=? AND review_round=? ORDER BY id LIMIT ?',(self.s.instance_id,work['id'],row['review_round'],self.max_members+1))]
        context={'work':dict(row),'decisions':deepcopy(decisions)}
        self._attest(self.authority.verify_projection(entry,deepcopy(principal),context))
        if len(decisions)>self.max_members:raise Forbidden('bounded projection scan exceeded')
        if not decisions:return {'contract':'TL-C1-WORK-PROJECTION-1','work':work,'expected_revision':row['row_revision'],'target':None,'decisions':[]}
        operations={item['operation'] for item in decisions}
        target='handoff_pending' if 'accept' in operations else 'rejected' if operations=={'reject'} else 'waiting' if operations & {'defer','candidate','conflict'} else 'no_change' if operations=={'reuse'} else 'completed'
        return {'contract':'TL-C1-WORK-PROJECTION-1','work':deepcopy(work),'expected_revision':row['row_revision'],'target':target,'phase':'represent' if target=='handoff_pending' else 'decide' if target=='waiting' else 'complete','condition':{'kind':'acceptance_reassessment','requires':['current_policy','authenticated_controller_review','coordinator_new_review_round']} if target=='waiting' else None,'decisions':[ref(self.s,item['id'],'tl_decision') for item in decisions]}
