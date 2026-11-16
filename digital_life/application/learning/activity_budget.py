"""Original schema4 ordinary-activity eight-dimensional accounting.

Reuses the IM05 reservation algorithm, not a fabricated tl_work row. The owner
loaded here is the actual activity and its original physical budget account.
Initialization requires a named policy owner and happens once at creation.
"""
from copy import deepcopy
from digital_life.application.learning.budget import ToolLearningBudget,DIMENSIONS,CAPS
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,dumps,utc
from digital_life.domain import tool_learning_contract as c
from digital_life.domain import tool_learning_types as t

CONTRACT='TL-ACTIVITY-BUDGET-1'


def usage_occupancy(doc):
    ledger=doc['ledger'];used={k:0 for k in DIMENSIONS}
    if ledger['halted'] or any(r['state']=='usage_unknown' for r in ledger['reservations'].values()):raise Forbidden('original activity has unknown or halted resource consumption')
    for record in ledger['reservations'].values():
        if record['state']=='released':continue
        amounts=record['actual'] if record['state']=='settled' else record['reserved']
        for key in DIMENSIONS:used[key]+=amounts[key]
    return used


class ActivityBudgetAuthority:
    def verify_initial_caps(self,entry,activity,account,caps,policy):raise Forbidden('actual initial activity policy budget owner is not configured')


class ActivityResourceBudget(ToolLearningBudget):
    @classmethod
    def initialize(cls,store,entry,activity_id,budget,policy,authority):
        if not isinstance(authority,ActivityBudgetAuthority):raise ContractError('trusted original-cap authority required')
        c.validate('Budget',budget);c.validate('VersionToken',policy)
        if not store.db.in_transaction:raise Conflict('initial activity accounting must join its original creation transaction')
        activity=store.row('activities',activity_id);account=store.row('activity_budget_accounts',budget['account_ref']['id'])
        if account['activity_id']!=activity_id:raise Forbidden('new activity cannot borrow another account')
        if store.db.execute('SELECT 1 FROM budget_reservations WHERE instance_id=? AND activity_id=? LIMIT 1',(store.instance_id,activity_id)).fetchone():raise Conflict('initial caps cannot be retrofitted after resource use')
        old=c.loads(activity['budget_json'])
        if old.get('contract')==CONTRACT:raise Conflict('original activity accounting was already initialized')
        if old.get('contract')=='TL-WORK-BUDGET-1' or 'tl_work_allocations' in old:raise Conflict('an existing allocation cannot become a new activity budget')
        if (account['token_limit']!=budget['max_input_tokens']+budget['max_output_tokens'] or account['tool_call_limit']!=budget['max_tool_calls'] or account['attempt_limit']!=budget['max_attempts'] or activity['deadline']!=budget['deadline']):raise Conflict('initial policy caps must match the actual original account')
        value=authority.verify_initial_caps(entry,dict(activity),dict(account),deepcopy(budget),deepcopy(policy))
        if value is not None:raise Forbidden('initial-cap owner must attest by None')
        fixed={'contract':'TL-ACTIVITY-INITIAL-CAPS-1','activity_id':activity_id,'account_id':account['id'],'budget':deepcopy(budget),'policy':deepcopy(policy),'time_limit_ms':account['time_limit_ms']}
        artifact=store.artifact(fixed)
        document={'contract':CONTRACT,'budget':deepcopy(budget),'source_budget':None,'initial_caps_artifact':artifact,
                  'ledger':{'reservations':{},'halted':False,'violations':[],'last_seen_at':None}}
        store.db.execute('UPDATE activities SET budget_json=? WHERE instance_id=? AND id=?',(dumps(document),store.instance_id,activity_id))
        return deepcopy(document)
    def _load(self,activity_id):
        activity=self.s.row('activities',activity_id)
        account=self.s.db.execute('SELECT * FROM activity_budget_accounts WHERE instance_id=? AND activity_id=?',(self.s.instance_id,activity_id)).fetchone()
        if account is None:raise Forbidden('original activity account missing')
        account=dict(account);doc=c.loads(activity['budget_json'])
        if doc.get('contract')!=CONTRACT:raise Forbidden('ordinary activity has no originally authorized eight-dimensional accounting')
        t.obj(doc,('contract','budget','source_budget','initial_caps_artifact','ledger'),('tl_work_allocations',))
        if doc['source_budget'] is not None:raise ContractError('ordinary activity cannot pretend to be a child learning allocation')
        budget=doc['budget'];c.validate('Budget',budget)
        fixed=self.artifacts.read_artifact(doc['initial_caps_artifact'])
        t.obj(fixed,('contract','activity_id','account_id','budget','policy','time_limit_ms'))
        if fixed['contract']!='TL-ACTIVITY-INITIAL-CAPS-1' or fixed['activity_id']!=activity_id or fixed['account_id']!=account['id'] or fixed['budget']!=budget:raise Conflict('original activity cap binding changed')
        c.validate('VersionToken',fixed['policy'])
        if budget['account_ref']['id']!=account['id'] or budget['account_ref']['instance_id']!=self.s.instance_id or budget['account_ref']['kind']!='activity_budget_accounts' or budget['deadline']!=activity['deadline']:raise Conflict('ordinary original account/deadline differs')
        if account['token_limit']!=budget['max_input_tokens']+budget['max_output_tokens'] or account['tool_call_limit']!=budget['max_tool_calls'] or account['attempt_limit']!=budget['max_attempts'] or account['time_limit_ms']!=fixed['time_limit_ms']:raise Conflict('ordinary original physical caps differ')
        t.obj(doc['ledger'],('reservations','halted','violations','last_seen_at'));t.boolean(doc['ledger']['halted']);t.array(doc['ledger']['violations'],t.json_value)
        if doc['ledger']['last_seen_at'] is not None:c.validate('UTC',doc['ledger']['last_seen_at'])
        for key,value in doc['ledger']['reservations'].items():self._validate_reservation(key,value)
        projections={r['id']:dict(r) for r in self.s.db.execute('SELECT * FROM budget_reservations WHERE instance_id=? AND activity_id=?',(self.s.instance_id,activity_id))}
        expected={k:v for k,v in doc['ledger']['reservations'].items() if v['kind']!='retrieval'}
        if set(expected)!=set(projections):raise Conflict('ordinary physical attempt reservations differ from original ledger')
        for ident,record in expected.items():
            row=projections[ident]
            if row['operation_ref']!=record['operation']['id'] or row['operation_kind']!=record['kind'] or row['state']!=record['state'] or row['reserved_tokens']!=record['reserved']['input_tokens']+record['reserved']['output_tokens'] or row['reserved_attempts']!=record['reserved']['attempts'] or row['reserved_tool_calls']!=record['reserved']['tool_calls'] or c.loads(row['actual_usage'])!=record:raise Conflict('ordinary physical attempt projection mismatch')
        limits={key:budget[field] for key,field in CAPS.items()};limits['elapsed_ms']=account['time_limit_ms']
        # This is the real activity owner, not a tl_work stand-in in storage.
        owner=dict(activity);owner['owner_kind']='activities'
        return owner,dict(activity),account,doc,limits
    def _snapshot(self,loaded,request_budget=None):
        snapshot=super()._snapshot(loaded,request_budget)
        allocated=loaded[3].get('tl_work_allocations',{}).get('allocations',{})
        for dimension,cap in CAPS.items():
            if dimension in ('attempts','tool_calls'):continue
            amount=sum(item['budget'][cap] for item in allocated.values())
            snapshot['charged_or_reserved'][dimension]+=amount
            snapshot['remaining'][dimension]=max(0,snapshot['remaining'][dimension]-amount)
        snapshot['owner_kind']='activities';snapshot['activity_id']=loaded[1]['id']
        return snapshot
    def check_activity(self,activity_id,request_budget=None):return self.check_work(activity_id,request_budget)
