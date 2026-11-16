"""Deterministic-only evaluation dispatch, atomic three-level budgets and launch gates."""
import json
import copy
import os
import fcntl
from contextlib import contextmanager
import sqlite3
import threading
import time
from dataclasses import dataclass
from digital_life.domain.contracts import ContractError
from digital_life.domain import tool_learning_types as t
from evaluation.tool_learning_records import eval_id

DIMENSIONS=('attempts','tokens','tools')


class BudgetLedger:
    """Run/batch/logical-trial quotas are shared by all original/replacement attempts."""
    def __init__(self,workspace):
        self.path=workspace.root/'budget.sqlite'
        self.db=sqlite3.connect(self.path,isolation_level=None,check_same_thread=False,timeout=5)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS ledger_format(id INTEGER PRIMARY KEY CHECK(id=1),contract TEXT NOT NULL,revision INTEGER NOT NULL);
        INSERT OR IGNORE INTO ledger_format VALUES(1,'TL-EVAL-BUDGET-0.1',1);
        CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,level TEXT NOT NULL,parent TEXT,attempts INTEGER NOT NULL,tokens INTEGER NOT NULL,tools INTEGER NOT NULL,FOREIGN KEY(parent) REFERENCES accounts(id));
        CREATE TABLE IF NOT EXISTS reservations(id TEXT PRIMARY KEY,trial TEXT NOT NULL,batch TEXT NOT NULL,run TEXT NOT NULL,attempts INTEGER NOT NULL,tokens INTEGER NOT NULL,tools INTEGER NOT NULL,state TEXT NOT NULL,actual TEXT,entered INTEGER NOT NULL DEFAULT 0,phase TEXT NOT NULL,query_id TEXT,occurrence TEXT NOT NULL,FOREIGN KEY(trial) REFERENCES accounts(id),FOREIGN KEY(batch) REFERENCES accounts(id),FOREIGN KEY(run) REFERENCES accounts(id));
        CREATE UNIQUE INDEX IF NOT EXISTS query_once ON reservations(trial,query_id,occurrence) WHERE query_id IS NOT NULL AND attempts=1;
        CREATE TABLE IF NOT EXISTS budget_violations(reservation TEXT PRIMARY KEY,reason TEXT NOT NULL,actual TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS replacement_permissions(trial TEXT PRIMARY KEY,replacement_id TEXT UNIQUE NOT NULL,evidence TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS trial_deadlines(trial TEXT PRIMARY KEY,started_wall REAL NOT NULL,deadline_wall REAL NOT NULL,FOREIGN KEY(trial) REFERENCES accounts(id));
        CREATE TABLE IF NOT EXISTS ledger_control(id INTEGER PRIMARY KEY CHECK(id=1),stopped INTEGER NOT NULL,reason TEXT NOT NULL);
        INSERT OR IGNORE INTO ledger_control VALUES(1,0,'');
        ''')
        if tuple(self.db.execute('SELECT contract,revision FROM ledger_format WHERE id=1').fetchone())!=('TL-EVAL-BUDGET-0.1',1):raise ContractError('unsupported evaluation ledger format')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.path.chmod(0o600)
        self.lock=threading.RLock()
        self.gate_path=workspace.root/'dispatch.lock'
        self.local=threading.local()
    @contextmanager
    def dispatch_gate(self):
        with self.lock:
            depth=getattr(self.local,'depth',0)
            if depth:
                self.local.depth=depth+1
                try:yield
                finally:self.local.depth-=1
            else:
                with open(self.gate_path,'a+b') as handle:
                    self.gate_path.chmod(0o600)
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX);self.local.depth=1
                    try:yield
                    finally:self.local.depth=0;fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
    def close(self):self.db.close()
    def account(self,ident,level,limits,parent=None):
        eval_id(ident);t.enum(level,('run','batch','trial'));t.obj(limits,DIMENSIONS)
        for x in limits.values():t.integer(x)
        if (level=='run')!=(parent is None):raise ContractError('run alone has no parent')
        if parent is not None:
            p=self.db.execute('SELECT level FROM accounts WHERE id=?',(parent,)).fetchone()
            if p is None or p[0]!=('run' if level=='batch' else 'batch'):raise ContractError('budget parent level mismatch')
        if level=='trial' and (limits['attempts']>6 or limits['tokens']>196608 or limits['tools']>4):raise ContractError('trial exceeds Q11 maximum')
        try:self.db.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?)',(ident,level,parent,*(limits[k] for k in DIMENSIONS)))
        except sqlite3.IntegrityError:raise ContractError('budget identity already allocated')
    def stop(self,reason):
        t.string(reason)
        with self.dispatch_gate():self.db.execute('UPDATE ledger_control SET stopped=1,reason=? WHERE id=1',(reason,))
    def state(self):return dict(self.db.execute('SELECT stopped,reason FROM ledger_control WHERE id=1').fetchone())
    def _spent(self,account):
        sums={k:0 for k in DIMENSIONS}
        for row in self.db.execute('SELECT * FROM reservations WHERE trial=? OR batch=? OR run=?',(account,account,account)):
            if row['state']=='released':continue
            amounts=json.loads(row['actual']) if row['state'] in ('settled','violated') else {k:row[k] for k in DIMENSIONS}
            for k in DIMENSIONS:sums[k]+=amounts[k]
        return sums
    def reserve(self,ident,trial,batch,run,*,phase='learn',query_id=None,transport='model',tokens=32768,occurrence='original'):
        for x in (ident,trial,batch,run):eval_id(x)
        t.enum(phase,('learn','query'));t.enum(transport,('model','tool'));t.integer(tokens);t.enum(occurrence,('original','replacement'))
        if phase=='query':eval_id(query_id)
        elif query_id is not None:raise ContractError('learning has no query id')
        if tokens>32768:raise ContractError('per call token cap')
        amounts={'attempts':int(transport=='model'),'tokens':tokens if transport=='model' else 0,'tools':int(transport=='tool')}
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                if self.state()['stopped']:raise ContractError('run dispatch stopped')
                old=self.db.execute('SELECT * FROM reservations WHERE id=?',(ident,)).fetchone()
                if old:
                    if tuple(old[k] for k in ('trial','batch','run','phase','query_id','attempts','tokens','tools','occurrence'))!=(trial,batch,run,phase,query_id,amounts['attempts'],amounts['tokens'],amounts['tools'],occurrence):raise ContractError('reservation key reused with different meaning')
                    self.db.execute('COMMIT');return dict(old)
                if occurrence=='replacement' and self.db.execute('SELECT 1 FROM replacement_permissions WHERE trial=?',(trial,)).fetchone() is None:raise ContractError('replacement budget not independently authorized')
                accounts=[self.db.execute('SELECT * FROM accounts WHERE id=?',(x,)).fetchone() for x in (trial,batch,run)]
                if any(x is None for x in accounts) or [x['level'] for x in accounts]!=['trial','batch','run'] or accounts[0]['parent']!=batch or accounts[1]['parent']!=run:raise ContractError('wrong three-level budget chain')
                if phase=='learn' and transport=='model':
                    count=self.db.execute("SELECT COUNT(*) FROM reservations WHERE trial=? AND phase='learn' AND attempts=1 AND state!='released'",(trial,)).fetchone()[0]
                    if count>=3:raise ContractError('learning attempts capped at three')
                for a in accounts:
                    spent=self._spent(a['id'])
                    if any(spent[k]+amounts[k]>a[k] for k in DIMENSIONS):raise ContractError('budget exhausted: '+a['level'])
                self.db.execute('INSERT INTO reservations(id,trial,batch,run,attempts,tokens,tools,state,phase,query_id,occurrence) VALUES(?,?,?,?,?,?,?,\'reserved\',?,?,?)',(ident,trial,batch,run,*(amounts[k] for k in DIMENSIONS),phase,query_id,occurrence))
                self.db.execute('COMMIT');return dict(self.db.execute('SELECT * FROM reservations WHERE id=?',(ident,)).fetchone())
            except Exception:self.db.execute('ROLLBACK');raise
    def authorize_replacement(self,store,run_id,replacement_id):
        if store.role!='controller':raise ContractError('replacement authorization requires trusted controller')
        record=store.get('Trial',run_id,replacement_id)
        if record['occurrence']!='replacement':raise ContractError('not an authorized replacement occurrence')
        original_id=record['replacement_of']['value']['id']
        auth=store.workspace.metadata.execute('SELECT fault_id,assessor_id FROM replacement_authorizations WHERE run_id=? AND original_id=?',(run_id,original_id)).fetchone()
        if auth is None:raise ContractError('independent replacement evidence absent')
        try:self.db.execute('INSERT INTO replacement_permissions VALUES(?,?,?)',(record['logical_trial_id'],replacement_id,json.dumps(dict(auth),sort_keys=True)))
        except sqlite3.IntegrityError:raise ContractError('replacement already authorized once')
    def observe_trial_deadline(self,trial,now_wall):
        t.number(now_wall)
        with self.lock:
            self.db.execute('INSERT OR IGNORE INTO trial_deadlines VALUES(?,?,?)',(trial,now_wall,now_wall+1200))
            row=self.db.execute('SELECT started_wall,deadline_wall FROM trial_deadlines WHERE trial=?',(trial,)).fetchone()
            if now_wall<row[0] or now_wall>=row[1]:
                self.stop('trial_observation_deadline_or_clock_regression')
                raise ContractError('original trial deadline exhausted or clock regressed')
            return row[1]
    def enter(self,ident):
        # Shared lock covers the actual local callback, not merely this entry method.
        if self.state()['stopped']:raise ContractError('stopped before actual callback')
        cur=self.db.execute("UPDATE reservations SET entered=1 WHERE id=? AND entered=0 AND state='reserved'",(ident,))
        if cur.rowcount!=1:raise ContractError('callback already entered or reservation unavailable')
    def settle(self,ident,actual=None):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row=self.db.execute('SELECT * FROM reservations WHERE id=?',(ident,)).fetchone()
                if row is None:raise ContractError('reservation missing')
                if actual is not None:
                    t.obj(actual,DIMENSIONS)
                    for k in DIMENSIONS:t.integer(actual[k])
                    if not row['entered'] and any(actual.values()):raise ContractError('no callback entry cannot claim actual consumption')
                    if actual['attempts']!=row['attempts']*row['entered'] or actual['tools']!=row['tools']*row['entered']:raise ContractError('actual call count disagrees with callback transport')

                if row['state'] in ('settled','released','violated') and actual is None:
                    self.db.execute('COMMIT');return dict(row)
                if row['state'] in ('settled','released','violated'):
                    if row['actual']!=json.dumps(actual,sort_keys=True):raise ContractError('usage identity already settled differently')
                else:
                    state='unknown' if actual is None else 'settled' if row['entered'] else 'released'
                    self.db.execute('UPDATE reservations SET state=?,actual=? WHERE id=?',(state,None if actual is None else json.dumps(actual,sort_keys=True),ident))
                    if actual is None:self.db.execute("UPDATE ledger_control SET stopped=1,reason='usage_unknown' WHERE id=1")
                if actual is not None and any(actual[k]>row[k] for k in DIMENSIONS):
                    encoded=json.dumps(actual,sort_keys=True)
                    self.db.execute("UPDATE reservations SET state='violated',actual=? WHERE id=?",(encoded,ident))
                    self.db.execute('INSERT OR IGNORE INTO budget_violations VALUES(?,?,?)',(ident,'actual_exceeded_reservation',encoded))
                    self.db.execute("UPDATE ledger_control SET stopped=1,reason='budget_violation' WHERE id=1")
                self.db.execute('COMMIT')
            except Exception:self.db.execute('ROLLBACK');raise
    def record_violation(self,ident,reason):
        t.string(reason)
        row=self.db.execute('SELECT actual FROM reservations WHERE id=?',(ident,)).fetchone()
        if row is None or row[0] is None:raise ContractError('known usage required for known budget violation')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                self.db.execute("UPDATE reservations SET state='violated' WHERE id=?",(ident,))
                self.db.execute('INSERT OR IGNORE INTO budget_violations VALUES(?,?,?)',(ident,reason,row[0]))
                self.db.execute("UPDATE ledger_control SET stopped=1,reason='budget_violation' WHERE id=1")
                self.db.execute('COMMIT')
            except Exception:self.db.execute('ROLLBACK');raise
    def balances(self,ident):
        row=self.db.execute('SELECT * FROM accounts WHERE id=?',(ident,)).fetchone()
        if row is None:raise ContractError('budget absent')
        return {'limits':{k:row[k] for k in DIMENSIONS},'charged_or_reserved':self._spent(ident)}


@dataclass(frozen=True)
class DeterministicFixture:
    fixture_id: str
    callback: object
    provenance: str
    input_tokens: int = 0
    max_output_tokens: int = 8000
    def __post_init__(self):
        eval_id(self.fixture_id);t.string(self.provenance)
        if not callable(self.callback):raise ContractError('deterministic callback required')
        t.integer(self.input_tokens,0,24000);t.integer(self.max_output_tokens,0,8000)


class DeterministicRunner:
    """Trusted local test callbacks only; this API is not a sandbox for untrusted code."""
    def __init__(self,ledger,clock=time.monotonic,wall_clock=time.time):
        self.ledger=ledger;self.clock=clock;self.wall_clock=wall_clock;self.events=[];self.started={};self.results={};self.identities={}
    def _event(self,kind,ident,**fields):
        self.events.append({'kind':kind,'id':ident,'clock':self.clock(),**fields})
    def evidence_json(self):
        return json.dumps({'mode':'deterministic_substitute','events':copy.deepcopy(self.events),'results':copy.deepcopy(self.results),'real_model_called':False},sort_keys=True,separators=(',',':'))
    def run(self,fixture,ident,trial,batch,run,*,phase='learn',query_id=None,transport='model',case_id='synthetic',category='mechanism',occurrence='original'):
        if type(fixture) is not DeterministicFixture:raise ContractError('explicit deterministic fixture required')
        identity=(fixture.fixture_id,fixture.provenance,id(fixture.callback),fixture.input_tokens,fixture.max_output_tokens,trial,batch,run,phase,query_id,transport,case_id,category,occurrence)
        if ident in self.identities and self.identities[ident]!=identity:raise ContractError('runner key reused with different meaning')
        self.identities[ident]=identity
        if ident in self.results:return self.results[ident]
        self.ledger.observe_trial_deadline(trial,self.wall_clock())
        start=self.started.setdefault(trial,self.clock())
        if self.clock()-start>=1200:
            self.ledger.stop('trial_observation_deadline');raise ContractError('trial deadline')
        self.ledger.reserve(ident,trial,batch,run,phase=phase,query_id=query_id,transport=transport,occurrence=occurrence)
        self._event('prepared',ident,fixture_id=fixture.fixture_id)
        entered=False
        try:
            with self.ledger.dispatch_gate():
                self.ledger.enter(ident);entered=True
                before=self.clock();self._event('actual_callback_entry',ident)
                result=fixture.callback()
                self._event('actual_callback_exit',ident)
                t.obj(result,('passed','output_tokens','evidence'))
                t.boolean(result['passed']);t.integer(result['output_tokens']);t.json_value(result['evidence'])
                usage={'attempts':int(transport=='model'),'tokens':fixture.input_tokens+result['output_tokens'] if transport=='model' else 0,'tools':int(transport=='tool')}
                self.ledger.settle(ident,usage)
                if result['output_tokens']>fixture.max_output_tokens:
                    self.ledger.record_violation(ident,'output_token_cap')
                    raise ContractError('fixture exceeded output token limit; actual retained')
                if self.clock()-before>180 or self.clock()-start>1200:
                    self.ledger.stop('observation_deadline');status='not_evaluable';value=None
                else:status='measured';value=result['passed']
                if self.ledger.state()['reason']=='budget_violation':raise ContractError('known budget violation; actual retained')
                if value is False:self.ledger.stop('mechanism_hard_failure')
                observation={'id':ident,'case_id':case_id,'category':category,'status':status,'value':value}
                output={'mode':'deterministic_substitute','fixture_id':fixture.fixture_id,'observation':observation,'evidence':result['evidence'],'actual_callback_entry':True,'real_model_called':False}
                self.results[ident]=output;return output
        except Exception as error:
            # Callback failure retains actual entrance and unknown consumption, never fake zero.
            self._event('failed',ident,error_type=type(error).__name__,actual_callback_entry=entered)
            self.ledger.settle(ident,None if entered else {k:0 for k in DIMENSIONS})
            self.results[ident]={'mode':'deterministic_substitute','fixture_id':fixture.fixture_id,'observation':{'id':ident,'case_id':case_id,'category':category,'status':'measured','value':False},'evidence':{'error_type':type(error).__name__},'actual_callback_entry':entered,'real_model_called':False}
            raise


def check_launch_conditions(partition,conditions):
    """Reports missing evidence; no real-provider transport exists in this module."""
    t.enum(partition,('DEV','TARGET','RETENTION'))
    required={'sealed_materials','exact_model_and_capabilities','verified_price','money_limit','account_limits','explicit_run_authorization','mechanism_and_g1_pass','qualified_roles','finite_mech_time_disk_limits'}
    if partition in ('TARGET','RETENTION'):required|={'dev_preflight','independent_formal_truth','two_independent_reviewers','adjudicator','source_cluster_isolation'}
    t.json_value(conditions)
    missing=sorted(k for k in required if not isinstance(conditions.get(k),dict) or not conditions[k].get('evidence_ref'))
    return {'state':'blocked_before_start','missing':missing,'transport_available':False,'reason':'real-model execution is not implemented/authorized by deterministic tooling; evidence references require controller verification'}
