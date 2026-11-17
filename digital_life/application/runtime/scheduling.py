"""M02/M17 durable leases, consumer receipts and resource reservations."""
import json
from digital_life.domain.contracts import utc,identifier,Conflict,ContractError

class Queue:
    def __init__(self,store): self.s=store
    def enqueue(self,kind,target,due=None):
        return self.s.insert('jobs',kind=kind,target_ref=target,due_at=due or utc(),state='queued',attempt=0)
    def claim(self,worker,seconds=60,preferred_job=None):
        if not 1<=seconds<=3600: raise ContractError('invalid lease duration')
        with self.s.tx():
            row=self.s.db.execute("SELECT * FROM jobs WHERE instance_id=? AND due_at<=? AND (state='queued' OR (state='leased' AND lease_expiry<=?)) AND (? IS NULL OR id=?) ORDER BY due_at,id LIMIT 1",(self.s.instance_id,utc(),utc(),preferred_job,preferred_job)).fetchone()
            if not row: return None
            token=identifier(); generation=row['lease_generation']+1
            self.s.db.execute("UPDATE jobs SET state='leased',lease_owner=?,lease_token=?,lease_generation=?,lease_expiry=?,attempt=attempt+1 WHERE id=?",(worker,token,generation,utc(seconds),row['id']))
            return self.s.row('jobs',row['id'])
    def finish(self,job,success=True):
        with self.s.tx():
            count=self.s.db.execute("UPDATE jobs SET state=?,lease_owner=NULL,lease_token=NULL,lease_expiry=NULL WHERE id=? AND instance_id=? AND state='leased' AND lease_owner=? AND lease_token=? AND lease_generation=? AND lease_expiry>?",('succeeded' if success else 'failed',job['id'],self.s.instance_id,job['lease_owner'],job['lease_token'],job['lease_generation'],utc())).rowcount
            if count!=1: raise Conflict('lease expired or replaced')
    def renew(self,job,seconds=60):
        with self.s.tx():
            count=self.s.db.execute("UPDATE jobs SET lease_expiry=? WHERE id=? AND instance_id=? AND state='leased' AND lease_token=? AND lease_generation=? AND lease_expiry>?",(utc(seconds),job['id'],self.s.instance_id,job['lease_token'],job['lease_generation'],utc())).rowcount
            if count!=1: raise Conflict('stale lease')
    def receipt(self,consumer,event,callback):
        with self.s.tx():
            old=self.s.db.execute('SELECT * FROM consumer_receipts WHERE instance_id=? AND consumer_name=? AND consumer_version=? AND event_id=?',(self.s.instance_id,consumer,'v1',event)).fetchone()
            if old and old['state']=='processed': return {'duplicate':True}
            value=callback()
            if old: self.s.db.execute("UPDATE consumer_receipts SET state='processed',processed_at=? WHERE id=?",(utc(),old['id']))
            else: self.s.insert('consumer_receipts',consumer_name=consumer,consumer_version='v1',event_id=event,state='processed',processed_at=utc())
            return value

class Budget:
    def __init__(self,store): self.s=store
    def create(self,activity,tokens=None,calls=None,attempts=None):
        from digital_life.application.runtime.settings import for_activity
        options=for_activity(self.s,activity)
        return self.s.insert('activity_budget_accounts',activity_id=activity,token_limit=options['tokens'] if tokens is None else tokens,tool_call_limit=options['tool_calls'] if calls is None else calls,attempt_limit=options['attempts'] if attempts is None else attempts,time_limit_ms=options['duration_seconds']*1000)
    def unlimited(self,activity):
        document=json.loads(self.s.row('activities',activity)['budget_json'])
        # Never relax a protected/shared learning resource contract.
        return (document.get('runtime_settings',{}).get('budget_enabled') is False
                and document.get('contract') not in ('TL-WORK-BUDGET-1','TL-ACTIVITY-BUDGET-1')
                and 'tl_work_allocations' not in document)
    def remaining(self,activity):
        from datetime import datetime
        row=self.s.row('activities',activity)
        account=self.s.db.execute('SELECT * FROM activity_budget_accounts WHERE activity_id=?',(activity,)).fetchone()
        if account is None:raise ContractError('budget account missing')
        document=json.loads(row['budget_json'])
        if document.get('contract') in ('TL-WORK-BUDGET-1','TL-ACTIVITY-BUDGET-1'):raise ContractError('project task cannot use a protected learning budget')
        allocated={'tokens':0,'tools':0,'attempts':0}
        if 'tl_work_allocations' in document:
            from digital_life.application.learning.budget import allocation_occupancy
            allocated=allocation_occupancy(document)
        reservations=self.s.db.execute("SELECT * FROM budget_reservations WHERE activity_id=? AND state<>'released'",(activity,)).fetchall()
        elapsed=(datetime.fromisoformat(utc().replace('Z','+00:00'))-datetime.fromisoformat(row['recorded_at'].replace('Z','+00:00'))).total_seconds()*1000
        if self.unlimited(activity):
            return {'mode':'unlimited','tokens':None,'tools':None,'attempts':None,'time_ms':None,
                    'deadline_valid':not row['deadline'] or row['deadline']>utc(),
                    'usage_unknown':any(r['state']=='usage_unknown' for r in reservations)}
        return {'tokens':max(0,account['token_limit']-allocated['tokens']-sum(r['reserved_tokens'] for r in reservations)),
                'tools':max(0,account['tool_call_limit']-allocated['tools']-sum(r['reserved_tool_calls'] for r in reservations)),
                'attempts':max(0,account['attempt_limit']-allocated['attempts']-len(reservations)),
                'time_ms':max(0,account['time_limit_ms']-elapsed),'deadline_valid':not row['deadline'] or row['deadline']>utc(),
                'usage_unknown':any(r['state']=='usage_unknown' for r in reservations)}
    def reserve(self,activity,operation,kind,tokens=0):
        with self.s.tx():
            account=self.s.db.execute('SELECT * FROM activity_budget_accounts WHERE activity_id=?',(activity,)).fetchone()
            if account is None: raise ContractError('budget account missing')
            activity_row=self.s.row('activities',activity)
            budget_document=json.loads(activity_row['budget_json'])
            if isinstance(budget_document,dict) and budget_document.get('contract') in ('TL-WORK-BUDGET-1','TL-ACTIVITY-BUDGET-1'):
                raise ContractError('learning work requires the unified work budget entry')
            allocated={'tokens':0,'tools':0,'attempts':0}
            if isinstance(budget_document,dict) and 'tl_work_allocations' in budget_document:
                from digital_life.application.learning.budget import allocation_occupancy
                allocated=allocation_occupancy(budget_document)
            rows=self.s.db.execute("SELECT * FROM budget_reservations WHERE activity_id=? AND state<>'released'",(activity,)).fetchall()
            if isinstance(budget_document,dict) and 'tl_work_allocations' in budget_document and any(r['state']=='usage_unknown' for r in rows):
                raise ContractError('shared learning parent has unknown consumption; reconcile before new reservations')
            tools=int(kind=='tool_attempt')
            if not self.unlimited(activity) and (sum(r['reserved_tokens'] for r in rows)+allocated['tokens']+tokens>account['token_limit'] or len(rows)+allocated['attempts']+1>account['attempt_limit'] or sum(r['reserved_tool_calls'] for r in rows)+allocated['tools']+tools>account['tool_call_limit']):
                raise ContractError('budget exhausted')
            ref=self.s.insert('budget_reservations',activity_id=activity,operation_ref=operation,operation_kind=kind,reservation_key=operation,reserved_tokens=tokens,reserved_tool_calls=tools,reserved_attempts=1,state='reserved',reserved_at=utc())
            self.s.db.execute('UPDATE activity_budget_accounts SET revision=revision+1 WHERE id=?',(account['id'],)); return ref
    def settle(self,reservation,usage=None,unknown=False):
        with self.s.tx():
            row=self.s.row('budget_reservations',reservation)
            activity=self.s.row('activities',row['activity_id'])
            document=json.loads(activity['budget_json'])
            if isinstance(document,dict) and document.get('contract')=='TL-WORK-BUDGET-1':
                raise ContractError('learning work requires unified usage settlement')
            if row['state']!='reserved': return row['state']
            state='usage_unknown' if unknown else 'settled'
            self.s.db.execute('UPDATE budget_reservations SET state=?,actual_usage=?,settled_at=? WHERE id=?',(state,json.dumps(usage) if usage is not None else None,utc(),reservation))
            return state
