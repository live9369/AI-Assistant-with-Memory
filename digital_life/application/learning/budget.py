"""IM05 work-wide resource accounting; no model/tool dispatch or wake path."""
from copy import deepcopy
from contextlib import contextmanager
import json

from digital_life.domain.contracts import ContractError, Conflict, Forbidden, dumps, identifier, utc
from digital_life.domain import tool_learning_contract as contract
from digital_life.domain import tool_learning_types as types
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate

CONTRACT = 'TL-WORK-BUDGET-1'
from digital_life.domain.tool_learning_resources import DIMENSIONS
CAPS = {'input_tokens':'max_input_tokens', 'output_tokens':'max_output_tokens',
        'attempts':'max_attempts', 'tool_calls':'max_tool_calls', 'scan':'max_scan',
        'items':'max_items', 'bytes':'max_bytes'}
KINDS = ('thought_attempt', 'tool_attempt', 'retrieval')


def make_work_budget(budget, source_budget=None):
    contract.validate('Budget', budget)
    if source_budget is not None: contract.validate('Budget', source_budget)
    return {'contract':CONTRACT, 'budget':deepcopy(budget), 'source_budget':deepcopy(source_budget),
            'ledger':{'reservations':{}, 'halted':False, 'violations':[], 'last_seen_at':None}}


def allocation_occupancy(budget_json):
    """Conservative child allocations for the legacy budget's three dimensions."""
    doc = types.loads(budget_json) if isinstance(budget_json, str) else budget_json
    types.json_value(doc)
    ledger = doc.get('tl_work_allocations') if isinstance(doc, dict) else None
    result = {'tokens':0, 'tools':0, 'attempts':0}
    if ledger is None: return result
    types.obj(ledger, ('contract','caps','allocations'))
    if ledger['contract'] != 'TL-WORK-ALLOCATIONS-1': raise ContractError('unknown parent allocation contract')
    contract.validate('Budget', ledger['caps'])
    if not isinstance(ledger['allocations'], dict): raise ContractError('allocation dictionary required')
    seen = set()
    for work, allocation in ledger['allocations'].items():
        types.string(work);types.obj(allocation, ('activity_id','account_id','budget'))
        for key in ('activity_id','account_id'): types.string(allocation[key])
        if allocation['account_id'] in seen: raise ContractError('duplicate allocated account')
        seen.add(allocation['account_id'])
        b = allocation['budget'];contract.validate('Budget', b)
        if b['account_ref']['id'] != allocation['account_id']: raise ContractError('allocation account mismatch')
        result['tokens'] += b['max_input_tokens'] + b['max_output_tokens']
        result['tools'] += b['max_tool_calls'];result['attempts'] += b['max_attempts']
    return result


class BudgetAuthority:
    """Trusted composition port; request data cannot implement this service."""
    def verify_evaluation_read(self, entry, work, operation, binding, stage):
        raise Forbidden('actual original-work effect read owner is not configured')

    def verify_representation_read(self,entry,work,operation,binding,stage):
        raise Forbidden('actual terminal representation read owner is not configured')

    def verify_recovery_read(self, entry, work, operation, binding, stage):
        raise Forbidden('actual original-work recovery read owner is not configured')

    def verify_budget(self, entry, work, original_budget, request_budget, operation, stage):
        raise Forbidden('current work budget authority is not configured')

    def verify_entry(self, entry, work, reservation, witness):
        raise Forbidden('trusted actual callback-entry witness is not configured')

    def verify_settlement(self, entry, work, reservation, actual):
        raise Forbidden('trusted settlement/release evidence service is not configured')


class ToolLearningBudget:
    def __init__(self, store, authority=None, clock=utc):
        self.s = store
        self.authority = BudgetAuthority() if authority is None else authority
        if not isinstance(self.authority, BudgetAuthority): raise ContractError('trusted BudgetAuthority required')
        self.clock = clock
        self.__recovery_read = None
        self.artifacts = ToolLearningStore(store)

    @contextmanager
    def recovery_read_context(self,entry,work_id,operation,binding):
        """Trusted owner-bound local read only; no model/tool permission."""
        if self.__recovery_read is not None:raise Conflict('recovery read contexts cannot nest')
        fixed=deepcopy(binding);operation=deepcopy(operation)
        with dispatch_gate(self.s.root):
            loaded=self._load(work_id);state=loaded[0]['state']
            if state not in ('waiting','blocked','failed','stopped'):raise Forbidden('recovery read requires suspended work')
            self._operation(operation,'retrieval',loaded[1]['id'])
            result=self.authority.verify_recovery_read(entry,deepcopy(loaded[0]),deepcopy(operation),deepcopy(fixed),'begin')
            if result is not None:raise Forbidden('recovery read attestation must not be boolean')
            self.__recovery_read=(entry,work_id,operation,fixed,state,'verify_recovery_read')
            try:
                if self._snapshot(self._load(work_id))['blocked']:raise Forbidden('recovery cannot bypass original control/resource limits')
                yield
            finally:self.__recovery_read=None

    @contextmanager
    def evaluation_read_context(self,entry,work_id,operation,binding):
        """Actual M14 effect read of a terminal work, not work resumption."""
        if self.__recovery_read is not None:raise Conflict('owned read contexts cannot nest')
        fixed=deepcopy(binding);operation=deepcopy(operation)
        with dispatch_gate(self.s.root):
            loaded=self._load(work_id);state=loaded[0]['state']
            if state not in ('completed','no_change','rejected'):raise Forbidden('evaluation read requires terminal work')
            self._operation(operation,'retrieval',loaded[1]['id'])
            result=self.authority.verify_evaluation_read(entry,deepcopy(loaded[0]),deepcopy(operation),deepcopy(fixed),'begin')
            if result is not None:raise Forbidden('evaluation read attestation must not be boolean')
            self.__recovery_read=(entry,work_id,operation,fixed,state,'verify_evaluation_read')
            try:
                if self._snapshot(self._load(work_id))['blocked']:raise Forbidden('evaluation cannot bypass original control/resource limits')
                yield
            finally:self.__recovery_read=None

    @contextmanager
    def representation_read_context(self,entry,work_id,operation,binding):
        """One exact controller-authorized M03/M04 local rendering read only."""
        if self.__recovery_read is not None:raise Conflict('owned read contexts cannot nest')
        fixed=deepcopy(binding);operation=deepcopy(operation)
        with dispatch_gate(self.s.root):
            loaded=self._load(work_id);state=loaded[0]['state']
            if state not in ('completed','handoff_pending'):raise Forbidden('representation read requires an accepted work endpoint')
            self._operation(operation,'retrieval',loaded[1]['id'])
            result=self.authority.verify_representation_read(entry,deepcopy(loaded[0]),deepcopy(operation),deepcopy(fixed),'begin')
            if result is not None:raise Forbidden('representation read owner must not be a boolean')
            self.__recovery_read=(entry,work_id,operation,fixed,state,'verify_representation_read')
            try:
                if self._snapshot(self._load(work_id))['blocked']:raise Forbidden('representation read cannot renew original limits/control')
                yield
            finally:self.__recovery_read=None

    def _check_recovery_operation(self,entry,work_id,operation,kind):
        current=self.__recovery_read
        if current is None:return
        if (entry,work_id,operation,kind)!=(current[0],current[1],current[2],'retrieval'):raise Forbidden('recovery read scope cannot authorize another operation')
        loaded=self._load(work_id)
        result=getattr(self.authority,current[5])(entry,deepcopy(loaded[0]),deepcopy(operation),deepcopy(current[3]),'current')
        if result is not None:raise Forbidden('recovery read attestation must not be boolean')
        self.s.assert_execution_allowed()

    def _now(self):
        value = self.clock();contract.validate('UTC', value);return value

    def _load(self, work_id):
        types.string(work_id)
        found=self.s.db.execute('SELECT * FROM tl_work WHERE instance_id=? AND id=?',(self.s.instance_id,work_id)).fetchone()
        if found is None:raise ContractError('work not found in this instance')
        work=dict(found)
        activity = self.s.row('activities', work['learning_activity_id'])
        account = self.s.row('activity_budget_accounts', work['budget_account_id'])
        if account['activity_id'] != activity['id']: raise ContractError('work account activity mismatch')
        doc = types.loads(activity['budget_json'])
        if not isinstance(doc, dict) or doc.get('contract') != CONTRACT: raise ContractError('work budget document required')
        if 'tl_work_allocations' in doc: raise Forbidden('nested learning-work allocations require a later allocation protocol')
        budget = doc['budget'];contract.validate('Budget', budget)
        source_budget = doc['source_budget']
        if source_budget is not None: contract.validate('Budget', source_budget)
        conditions = self.artifacts.read_artifact(work['conditions_artifact_id'])
        if conditions.get('budget') != budget or conditions.get('source_budget') != source_budget:
            raise ContractError('original work caps differ from immutable conditions')
        if budget['account_ref']['instance_id'] != self.s.instance_id or budget['account_ref']['id'] != account['id'] or budget['account_ref']['kind'] != 'activity_budget_accounts':
            raise ContractError('work budget is not bound to the original account')
        if budget['deadline'] != work['deadline'] or activity['deadline'] != work['deadline']:
            raise ContractError('original work deadline mismatch')
        if (account['token_limit'] != budget['max_input_tokens']+budget['max_output_tokens'] or
                account['tool_call_limit'] != budget['max_tool_calls'] or account['attempt_limit'] != budget['max_attempts']):
            raise ContractError('technical account caps differ from original work budget')
        types.integer(conditions.get('time_limit_ms'))
        if account['time_limit_ms']!=conditions['time_limit_ms']: raise ContractError('original time limit mismatch')
        ledger = doc['ledger'];types.obj(ledger, ('reservations','halted','violations','last_seen_at'))
        types.boolean(ledger['halted']);types.array(ledger['violations'], types.json_value)
        if ledger['last_seen_at'] is not None: contract.validate('UTC', ledger['last_seen_at'])
        if not isinstance(ledger['reservations'], dict): raise ContractError('reservation dictionary required')
        limits = {k:budget[v] for k,v in CAPS.items()};limits['elapsed_ms'] = account['time_limit_ms']
        for ident, reservation in ledger['reservations'].items():
            self._validate_reservation(ident, reservation)
        projections={r['id']:dict(r) for r in self.s.db.execute('SELECT * FROM budget_reservations WHERE instance_id=? AND activity_id=?', (self.s.instance_id,activity['id']))}
        expected={k:v for k,v in ledger['reservations'].items() if v['kind']!='retrieval'}
        if set(projections)!=set(expected): raise ContractError('attempt reservations differ from work-wide ledger')
        for ident,row in expected.items():
            physical=projections[ident]
            if (physical['operation_ref']!=row['operation']['id'] or physical['operation_kind']!=row['kind'] or
                    physical['reservation_key']!=row['key'] or physical['state']!=row['state'] or
                    physical['reserved_tokens']!=row['reserved']['input_tokens']+row['reserved']['output_tokens'] or
                    physical['reserved_tool_calls']!=row['reserved']['tool_calls'] or physical['reserved_attempts']!=row['reserved']['attempts'] or
                    types.loads(physical['actual_usage'])!=row):
                raise ContractError('physical reservation mapping differs from work ledger')
        return work, activity, account, doc, limits

    @staticmethod
    def _amounts(value):
        if not isinstance(value, dict) or set(value)-set(DIMENSIONS): raise ContractError('unknown resource dimension')
        result = {k:value.get(k,0) for k in DIMENSIONS}
        for v in result.values(): types.integer(v)
        return result

    def _validate_reservation(self, ident, row):
        types.string(ident)
        types.obj(row, ('id','key','kind','operation','reserved','state','entry','actual','reserved_at','settled_at'))
        if row['id'] != ident: raise ContractError('reservation identity mismatch')
        types.string(row['key']);types.enum(row['kind'], KINDS);contract.validate('Ref',row['operation'])
        types.enum(row['state'], ('reserved','settled','released','usage_unknown'))
        if set(row['reserved']) != set(DIMENSIONS): raise ContractError('incomplete reserved dimensions')
        self._amounts(row['reserved']);contract.validate('UTC',row['reserved_at'])
        if row['actual'] is not None:
            if set(row['actual']) != set(DIMENSIONS): raise ContractError('incomplete actual dimensions')
            self._amounts(row['actual'])
        if row['state'] in ('settled','released') and row['actual'] is None: raise ContractError('settled usage absent')
        if row['state'] in ('reserved','usage_unknown') and row['actual'] is not None: raise ContractError('unsettled usage cannot have actual totals')
        if row['entry'] is not None:
            types.obj(row['entry'], ('at','witness'));contract.validate('UTC',row['entry']['at']);types.json_value(row['entry']['witness'])
        if row['settled_at'] is not None: contract.validate('UTC',row['settled_at'])

    def _snapshot(self, loaded, request_budget=None):
        work, activity, account, doc, limits = loaded
        ledger = doc['ledger'];used={k:0 for k in DIMENSIONS}
        for row in ledger['reservations'].values():
            if row['state'] == 'released': continue
            charged = row['actual'] if row['state'] == 'settled' else row['reserved']
            for k in DIMENSIONS: used[k] += charged[k]
        # Legacy/new child allocations are disjoint obligations that remain held.
        allocated = allocation_occupancy(doc)
        used['attempts'] += allocated['attempts'];used['tool_calls'] += allocated['tools']
        total_tokens = used['input_tokens']+used['output_tokens']+allocated['tokens']
        remaining={k:max(0,limits[k]-used[k]) for k in DIMENSIONS}
        remaining['tokens'] = max(0, account['token_limit']-total_tokens)
        reasons=[];now=self._now()
        try:self.s.assert_execution_allowed()
        except Forbidden:reasons.append('instance_stopped')
        if ledger['halted']: reasons.append('budget_halted')
        if any(r['state']=='usage_unknown' for r in ledger['reservations'].values()): reasons.append('usage_unknown')
        if ledger['last_seen_at'] is not None and now < ledger['last_seen_at']: reasons.append('clock_regressed')
        if now >= work['deadline']: reasons.append('deadline')
        if work['state'] in ('waiting','blocked','failed','stopped','completed','no_change','rejected'):
            recovery=self.__recovery_read
            if recovery is None or work['id']!=recovery[1] or work['state']!=recovery[4]:reasons.append('work_'+work['state'])
        if activity['cancel_requested_at'] is not None or activity['state']=='cancelled': reasons.append('cancelled')
        if activity['state'] in ('paused','failed','completed'): reasons.append('activity_'+activity['state'])
        if remaining['attempts']==0: reasons.append('attempts_exhausted')
        if request_budget is not None:
            contract.validate('Budget', request_budget)
            if request_budget['account_ref'] != doc['budget']['account_ref']: raise Conflict('request cannot replace original account')
            if request_budget['deadline'] > work['deadline']: raise Conflict('request cannot extend original deadline')
            if now >= request_budget['deadline']: reasons.append('request_deadline')
            for k, field in CAPS.items():
                if request_budget[field] > doc['budget'][field]: raise Conflict('request cannot increase original cap')
                remaining[k] = min(remaining[k], request_budget[field])
        return {'work_id':work['id'],'account_id':account['id'],'activity_id':activity['id'],
                'account_revision':account['revision'],'deadline':work['deadline'],
                'limits':limits,'charged_or_reserved':used,'remaining':remaining,
                'blocked':bool(reasons),'block_reasons':reasons,'budget':deepcopy(doc['budget'])}

    def check_work(self, work_id, request_budget=None):
        if self.s.db.in_transaction:return self._snapshot(self._load(work_id), request_budget)
        self.s.db.execute('BEGIN')
        try:
            value=self._snapshot(self._load(work_id),request_budget);self.s.db.execute('COMMIT');return value
        except BaseException:
            self.s.db.execute('ROLLBACK');raise

    def _verify(self, entry, loaded, request_budget, operation, stage):
        types.string(entry)
        value=self.authority.verify_budget(entry,deepcopy(loaded[0]),deepcopy(loaded[3]['budget']),
                                          deepcopy(request_budget),deepcopy(operation),stage)
        if value is not None: raise Forbidden('budget verifier must attest by successful return, not a boolean')

    def _save(self, loaded):
        work, activity, account, doc, _ = loaded
        changed=self.s.db.execute('UPDATE activity_budget_accounts SET revision=revision+1 WHERE instance_id=? AND id=? AND revision=?',
                                 (self.s.instance_id,account['id'],account['revision'])).rowcount
        if changed != 1: raise Conflict('budget account revision changed')
        self.s.db.execute('UPDATE activities SET budget_json=? WHERE instance_id=? AND id=?',
                          (dumps(doc),self.s.instance_id,activity['id']))

    def _operation(self, reference, kind, activity):
        contract.validate('Ref',reference)
        if reference['instance_id'] != self.s.instance_id: raise Forbidden('operation belongs to another instance')
        self.artifacts.validate_ref(reference)
        expected={'thought_attempt':('thought_attempts',),'tool_attempt':('action_attempts',),'retrieval':('memory_retrieval_runs',)}[kind]
        if reference['kind'] not in expected: raise ContractError('wrong operation kind for resource reservation')
        row=self.s.row('object_registry',reference['id'])
        if row['kind'] != reference['kind']: raise ContractError('operation registry kind mismatch')
        actual=self.s.row(reference['kind'],reference['id'])
        if kind=='thought_attempt': actual=self.s.row('thought_requests',actual['request_id'])
        if kind=='tool_attempt':
            intent=self.s.row('action_intents',actual['intent_id'])
            candidate=self.s.row('decision_candidates',intent['candidate_id'])
            actual=self.s.row('decision_records',candidate['decision_id'])
        if actual.get('activity_id') != activity: raise ContractError('operation is not bound to original learning activity')

    def reserve(self, entry, work_id, operation_ref, kind, amounts, *, request_budget=None, reservation_key=None):
        self._check_recovery_operation(entry,work_id,operation_ref,kind)
        types.enum(kind,KINDS);amounts=self._amounts(amounts)
        if kind=='thought_attempt' and (amounts['attempts']!=1 or amounts['tool_calls']): raise ContractError('thought reservation must reserve one model attempt')
        if kind=='tool_attempt' and (amounts['attempts']!=1 or amounts['tool_calls']!=1): raise ContractError('tool reservation must reserve one tool attempt')
        if kind=='retrieval' and any(amounts[k] for k in ('input_tokens','output_tokens','attempts','tool_calls')): raise ContractError('local retrieval is not a model or tool call')
        if not any(amounts.values()): raise ContractError('empty reservation is not a resource opportunity')
        key=operation_ref['id'] if reservation_key is None else reservation_key;types.string(key)
        if len(key)>240: raise ContractError('reservation key too long')
        if self.s.db.in_transaction: raise Conflict('budget operation requires an independent transaction')
        with dispatch_gate(self.s.root), self.s.tx():
            loaded=self._load(work_id);self._verify(entry,loaded,request_budget,operation_ref,'reserve')
            doc=loaded[3];ledger=doc['ledger'];snapshot=self._snapshot(loaded,request_budget)
            for old in ledger['reservations'].values():
                if old['key']==key:
                    if old['kind']!=kind or old['operation']!=operation_ref or old['reserved']!=amounts: raise Conflict('reservation key reused with different meaning')
                    reasons=[r for r in snapshot['block_reasons'] if r!='attempts_exhausted']
                    if reasons: raise Forbidden(','.join(reasons))
                    return deepcopy(old)
                if kind!='retrieval' and (old['operation']['instance_id'],old['operation']['id'],old['operation']['kind'])==(operation_ref['instance_id'],operation_ref['id'],operation_ref['kind']):
                    raise Conflict('one real model/tool attempt cannot acquire a second reservation under a new key')
            if snapshot['blocked']: raise Forbidden(','.join(snapshot['block_reasons']))
            self._operation(operation_ref,kind,loaded[1]['id'])
            if any(amounts[k]>snapshot['remaining'][k] for k in DIMENSIONS) or amounts['input_tokens']+amounts['output_tokens']>snapshot['remaining']['tokens']:
                raise Forbidden('original work budget exhausted')
            ident=identifier();now=self._now()
            record={'id':ident,'key':key,'kind':kind,'operation':deepcopy(operation_ref),'reserved':amounts,
                    'state':'reserved','entry':None,'actual':None,'reserved_at':now,'settled_at':None}
            ledger['reservations'][ident]=record;ledger['last_seen_at']=now
            if kind!='retrieval':
                self.s.insert('budget_reservations',id=ident,activity_id=loaded[1]['id'],operation_ref=operation_ref['id'],operation_kind=kind,
                              reservation_key=key,reserved_tokens=amounts['input_tokens']+amounts['output_tokens'],
                              reserved_tool_calls=amounts['tool_calls'],reserved_attempts=amounts['attempts'],state='reserved',actual_usage=record,reserved_at=now)
            self._save(loaded)
            self._verify(entry,loaded,request_budget,operation_ref,'commit')
            final=self._snapshot(self._load(work_id),request_budget)
            if any(r!='attempts_exhausted' for r in final['block_reasons']):raise Forbidden('work changed before reservation commit')
            self.s.assert_execution_allowed();return deepcopy(record)

    def record_entry(self, entry, work_id, reservation_id, witness):
        types.json_value(witness)
        if self.s.db.in_transaction: raise Conflict('budget operation requires an independent transaction')
        with dispatch_gate(self.s.root), self.s.tx():
            loaded=self._load(work_id);row=loaded[3]['ledger']['reservations'].get(reservation_id)
            if row is None: raise ContractError('unknown reservation')
            self._check_recovery_operation(entry,work_id,row['operation'],row['kind'])
            self._verify(entry,loaded,None,row['operation'],'entry')
            result=self.authority.verify_entry(entry,deepcopy(loaded[0]),deepcopy(row),deepcopy(witness))
            if result is not None: raise Forbidden('actual-entry verifier must not return a boolean')
            if row['entry'] is not None:
                if row['entry']['witness'] != witness: raise Conflict('actual-entry witness identity changed')
                return deepcopy(row)
            snapshot=self._snapshot(loaded)
            reasons=[r for r in snapshot['block_reasons'] if r!='attempts_exhausted']
            if reasons or row['state']!='reserved': raise Forbidden('reservation cannot enter callback')
            now=self._now();row['entry']={'at':now,'witness':deepcopy(witness)};loaded[3]['ledger']['last_seen_at']=now
            self._projection(row);self._save(loaded)
            self._verify(entry,loaded,None,row['operation'],'commit')
            final=self._snapshot(self._load(work_id))
            if any(r!='attempts_exhausted' for r in final['block_reasons']):raise Forbidden('work changed before entry commit')
            self.s.assert_execution_allowed();return deepcopy(row)

    def _projection(self,row):
        if row['kind']=='retrieval': return
        count=self.s.db.execute('UPDATE budget_reservations SET state=?,actual_usage=?,settled_at=? WHERE instance_id=? AND id=?',
                                (row['state'],dumps(row),row['settled_at'],self.s.instance_id,row['id'])).rowcount
        if count!=1: raise ContractError('physical attempt reservation is missing')

    def settle(self, entry, work_id, reservation_id, actual):
        if actual is not None and (not isinstance(actual,dict) or set(actual)!=set(DIMENSIONS)):
            raise ContractError('actual usage must explicitly report every resource dimension; missing is not zero')
        amounts=None if actual is None else self._amounts(actual)
        if self.s.db.in_transaction: raise Conflict('budget operation requires an independent transaction')
        with dispatch_gate(self.s.root), self.s.tx():
            loaded=self._load(work_id);ledger=loaded[3]['ledger'];row=ledger['reservations'].get(reservation_id)
            if row is None: raise ContractError('unknown reservation')
            self._verify(entry,loaded,None,row['operation'],'settle')
            verified=self.authority.verify_settlement(entry,deepcopy(loaded[0]),deepcopy(row),deepcopy(amounts))
            if verified is not None:raise Forbidden('settlement verifier must attest by successful return, not a boolean')
            if row['state'] in ('settled','released'):
                if row['actual'] != amounts: raise Conflict('known usage cannot be overwritten')
                return deepcopy(row)
            if amounts is not None:
                if row['entry'] is None and any(amounts.values()): raise ContractError('no verified actual entry for nonzero consumption')
                if row['entry'] is not None:
                    expected_attempt=int(row['kind']!='retrieval');expected_tool=int(row['kind']=='tool_attempt')
                    if amounts['attempts']!=expected_attempt or amounts['tool_calls']!=expected_tool: raise ContractError('actual entry call counts disagree with operation kind')
            now=self._now();row['actual']=amounts;row['settled_at']=now
            row['state']='usage_unknown' if amounts is None else 'released' if row['entry'] is None else 'settled'
            if amounts is None: ledger['halted']=True
            elif any(amounts[k]>row['reserved'][k] for k in DIMENSIONS):
                ledger['violations'].append({'reservation_id':row['id'],'reason':'actual_exceeded_reservation','at':now,'actual':deepcopy(amounts)})
                ledger['halted']=True
            if ledger['last_seen_at'] is not None and now<ledger['last_seen_at']:
                ledger['violations'].append({'reservation_id':row['id'],'reason':'clock_regressed','at':now})
                ledger['halted']=True
            else:ledger['last_seen_at']=now
            self._projection(row);self._save(loaded);return deepcopy(row)
