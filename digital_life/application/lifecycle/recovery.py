"""Conservative crash reconciliation. Never replay an uncertain external action."""
from digital_life.domain.contracts import Forbidden,utc
from digital_life.application.runtime.engine import Engine

class Recovery:
    def __init__(self,store): self.s=store
    def reconcile(self,actor,bearer=None):
        if actor!=self.s.config()['controller']: raise Forbidden('controller required')
        # A controller must stop the Runtime first; this also keeps model calls out.
        from digital_life.application.lifecycle.control_plane import Control
        control=Control(self.s.root,self.s.instance_id)
        try:
            state=control.state()
            if not state['user_stopped'] or state['active_process_run_id']:
                raise Forbidden('stop and reconcile process ownership before recovery')
        finally: control.close()
        tl=None
        if 'tl_work' in self.s.columns and self.s.db.execute('SELECT 1 FROM tl_work WHERE instance_id=? LIMIT 1',(self.s.instance_id,)).fetchone():
            if bearer is None:raise Forbidden('TL crash reconciliation requires the current authenticated controller channel')
            from digital_life.application.learning.recovery import reconcile_stopped_work
            tl=reconcile_stopped_work(self.s,bearer)
        paused=[]
        with self.s.tx():
            for activity in self.s.rows('activities'):
                if activity['state'] not in ('running','waiting_tool'): continue
                Engine(self.s).transition(activity['id'],'paused','controller-crash-reconciliation')
                paused.append(activity['id'])
            # Dispatched actions may already have affected the world. Retain their
            # authorizations and receipts, and require evidence before any retry.
            attempts=self.s.db.execute("SELECT id,intent_id FROM action_attempts WHERE instance_id=? AND state='running'",(self.s.instance_id,)).fetchall()
            for attempt in attempts:
                self.s.db.execute("UPDATE action_attempts SET state='unknown',finished_at=? WHERE id=?",(utc(),attempt['id']))
                self.s.db.execute("UPDATE outbox SET dispatch_state='unknown' WHERE intent_id=? AND dispatch_state='sent'",(attempt['intent_id'],))
            self.s.db.execute("UPDATE budget_reservations SET state='usage_unknown',settled_at=? WHERE instance_id=? AND state='reserved'",(utc(),self.s.instance_id))
            self.s.db.execute("UPDATE jobs SET state='failed',lease_owner=NULL,lease_token=NULL,lease_expiry=NULL WHERE instance_id=? AND state='leased'",(self.s.instance_id,))
            event=self.s.event('recovery.reconciled',payload={'paused':paused,'uncertain_attempts':[r['id'] for r in attempts],'automatic_replay':False},lane='control')
        return {'event':event,'paused':paused,'uncertain_actions':len(attempts),'automatic_replay':False,'tool_learning':tl}
