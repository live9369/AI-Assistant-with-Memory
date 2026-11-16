"""Disposable, independent TL evaluation databases. No production path is accepted."""
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from digital_life.domain.contracts import ContractError
from digital_life.domain import tool_learning_types as t
from evaluation.tool_learning_records import validate_record, eval_id, known

TRUTH_TYPES = {'Label','Review'}
ROLES = {'controller','evaluator','reviewer','actor','auditor'}


class EvaluationWorkspace:
    def __init__(self, temporary):
        self._temporary = temporary
        self.root = Path(temporary.name)
        os.chmod(self.root,0o700)
        for role in ('learning','query','controller-truth','fault-plan','blind-review','run-manifest'):
            (self.root/role).mkdir(mode=0o700)
        # The IM03 exact DDL is the single authoritative evaluation layout.
        canonical=self.root/'controller-truth'/'evaluation.sqlite'
        self.metadata = sqlite3.connect(canonical,isolation_level=None,check_same_thread=False,timeout=5)
        self.truth = self.metadata
        canonical.chmod(0o600)
        self.metadata.row_factory=sqlite3.Row
        ddl=(Path(__file__).resolve().parents[1]/'digital_life/resources/tool_learning_evaluation_v1.sql').read_text()
        self.metadata.executescript(ddl)
        self.metadata.create_function('document_digest',1,lambda raw:hashlib.sha256(json.dumps(json.loads(raw),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),deterministic=True)
        self.json_fields={}
        import re
        from evaluation.tool_learning_records import FIELDS,COMMON
        selects=[]
        for kind,fields in FIELDS.items():
            table='tle_'+kind.lower()
            block=ddl.split('CREATE TABLE '+table+' (',1)[1].split(') STRICT;',1)[0]
            jf=set(re.findall(r'CHECK\(json_valid\((\w+)\)\)',block));self.json_fields[kind]=jf
            fields=list(COMMON)+fields.split()
            values=[]
            for field in fields:
                value='json('+field+')' if field in jf else "json(CASE major_error WHEN 1 THEN 'true' ELSE 'false' END)" if field=='major_error' else field
                values.extend(["'"+field+"'",value])
            body='json_object('+','.join(values)+')'
            extras=[]
            for alias,field in [('case_id','case_id'),('arm','arm'),('repeat_no','repeat'),('occurrence','occurrence'),('logical_id','logical_trial_id'),('query_kind','query_kind'),('query_id','query_id'),('claim_id','claim_id'),('reviewer_id','reviewer_id'),('blind_item_id','blind_item_id')]:
                val='NULL' if field not in fields else "json_extract("+field+",'$.value')" if field in jf else field
                extras.append(val+' AS '+alias)
            selects.append("SELECT run_id,id,'"+kind+"' AS type,"+body+' AS body,document_digest('+body+') AS digest,'+','.join(extras)+' FROM '+table)
        self.metadata.execute('CREATE VIEW records AS '+' UNION ALL '.join(selects))
        self.metadata.execute('CREATE VIEW runs AS SELECT id AS run_id FROM tle_run')
        self.metadata.executescript('''CREATE TABLE artifacts(run_id TEXT NOT NULL,id TEXT NOT NULL,kind TEXT NOT NULL,domain TEXT NOT NULL,body TEXT NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(run_id,id));
        CREATE TABLE replacement_authorizations(run_id TEXT NOT NULL,original_id TEXT NOT NULL,fault_id TEXT NOT NULL,assessor_id TEXT NOT NULL,PRIMARY KEY(run_id,original_id));
        CREATE TABLE identities(id TEXT PRIMARY KEY,role TEXT NOT NULL,independence_group TEXT NOT NULL,synthetic INTEGER NOT NULL CHECK(synthetic IN (0,1)));''')
    @classmethod
    def create(cls):
        return cls(tempfile.TemporaryDirectory(prefix='tl-eval-isolated-'))
    def session(self,role):
        if role not in ROLES:raise ContractError('unsupported evaluation role')
        return EvaluationStore(self,role)
    def close(self):
        self.metadata.close();self._temporary.cleanup()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class EvaluationStore:
    def __init__(self,workspace,role):self.workspace=workspace;self.role=role
    def _allow(self,roles):
        if self.role not in roles:raise ContractError('evaluation role cannot access this domain')
    def _db(self,kind):return self.workspace.truth if kind in TRUTH_TYPES else self.workspace.metadata
    def register_artifact(self,run_id,ident,kind,domain,body):
        self._allow({'controller','evaluator'})
        eval_id(run_id);eval_id(ident);t.string(kind);t.enum(domain,('learning','query','controller-truth','fault-plan','blind-review','run-manifest'))
        t.json_value(body);encoded=json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':'));digest=hashlib.sha256(encoded.encode()).hexdigest()
        if domain in ('controller-truth','blind-review'):self._allow({'controller'})
        db=self.workspace.truth if domain in ('controller-truth','blind-review') else self.workspace.metadata
        try:db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?)',(run_id,ident,kind,domain,encoded,digest))
        except sqlite3.IntegrityError:
            row=db.execute('SELECT digest,kind,domain FROM artifacts WHERE run_id=? AND id=?',(run_id,ident)).fetchone()
            if not row or tuple(row)!=(digest,kind,domain):raise ContractError('artifact identity already bound differently')
        return {'instance_id':run_id,'id':ident,'kind':kind,'revision':{'status':'known','value':0,'reason_code':'none','reason':'','basis_refs':[]}}
    def artifact(self,ref):
        t.validate_ref(ref)
        for db in (self.workspace.metadata,self.workspace.truth):
            row=db.execute('SELECT * FROM artifacts WHERE run_id=? AND id=?',(ref['instance_id'],ref['id'])).fetchone()
            if row:
                if self.role=='actor' and row['domain'] not in ('learning','query'):raise ContractError('actor cannot read truth/audit/fault domains')
                if self.role=='reviewer' and row['domain']!='blind-review':raise ContractError('reviewer only receives blinded evidence projection')
                if row['domain'] in ('controller-truth','blind-review'):self._allow({'controller','reviewer','auditor'})
                if row['kind']!=ref['kind']:raise ContractError('artifact reference kind mismatch')
                return json.loads(row['body'])
        raise ContractError('missing evaluation artifact')
    def register_identity(self,ident,role,independence_group,synthetic=True):
        self._allow({'controller'});eval_id(ident);t.enum(role,('author','reviewer','adjudicator','independent_evaluator'));eval_id(independence_group);t.boolean(synthetic)
        if not synthetic:raise ContractError('real independent identities require external role provisioning, unavailable in synthetic tooling')
        self.workspace.truth.execute('INSERT INTO identities VALUES(?,?,?,?)',(ident,role,independence_group,int(synthetic)))
    def _record(self,db,run_id,ident,kind=None):
        row=db.execute('SELECT type,body FROM records WHERE run_id=? AND id=?',(run_id,ident)).fetchone()
        if row is None or (kind and row['type']!=kind):raise ContractError('missing or wrong-type same-run record')
        return json.loads(row['body'])
    def get(self,kind,run_id,ident):
        if self.role in ('actor','reviewer'):raise ContractError('actor/reviewer only receives explicit input/blind projections')
        if kind in TRUTH_TYPES:self._allow({'controller','auditor'})
        return self._record(self._db(kind),run_id,ident,kind)
    def _check_refs(self,v,run_id):
        if type(v) is dict:
            if set(v)=={'instance_id','id','kind','revision'}:
                found=False
                for db in (self.workspace.metadata,self.workspace.truth):
                    row=db.execute('SELECT kind FROM artifacts WHERE run_id=? AND id=?',(run_id,v['id'])).fetchone()
                    if row and row['kind']==v['kind']:found=True
                    row=db.execute('SELECT type FROM records WHERE run_id=? AND id=?',(run_id,v['id'])).fetchone()
                    if row and row['type']==v['kind']:found=True
                if not found:raise ContractError('unregistered or wrong-kind evaluation reference: '+v['id'])
            for x in v.values():self._check_refs(x,run_id)
        elif type(v) is list:
            for x in v:self._check_refs(x,run_id)
    def _relations(self,name,v):
        db=self.workspace.metadata;r=v['run_id']
        if name=='Case':
            for row in db.execute("SELECT body FROM records WHERE run_id=? AND type='Case'",(r,)):
                old=json.loads(row[0])
                if old['source_cluster_id']==v['source_cluster_id'] and old['partition']!=v['partition'] and {old['partition'],v['partition']} <= {'DEV','TARGET','RETENTION'}:raise ContractError('source cluster crosses experimental partitions')
        if name in ('Query','Trial'):
            case=self._record(db,r,v['case_id'],'Case')
            if name=='Query':
                if (case['partition']=='RETENTION') != (v['query_kind']=='retention'):raise ContractError('retention query partition mismatch')
            else:
                if case['partition'] in ('TARGET','RETENTION') and v['arm']=='O':raise ContractError('O is DEV diagnostic only')
                if case['partition']=='DEV' and v['repeat']!=1:raise ContractError('DEV one repeat only')
                if v['occurrence']=='replacement':
                    if v['replacement_of']['value']['kind']!='Trial':raise ContractError('replacement requires typed Trial reference')
                    original=self._record(db,r,v['replacement_of']['value']['id'],'Trial')
                    if original['occurrence']!='original' or original['status']!='infrastructure_invalid':raise ContractError('only damaged infrastructure original may be replaced')
                    for key in ('logical_trial_id','case_id','arm','repeat','budget_ref','assigned_order'):
                        if original[key]!=v[key]:raise ContractError('replacement changes allocation or budget')
                    auth=db.execute('SELECT 1 FROM replacement_authorizations WHERE run_id=? AND original_id=?',(r,original['id'])).fetchone()
                    if auth is None:raise ContractError('replacement lacks independent evaluator damage evidence')
        if name=='Attempt':
            trial=self._record(db,r,v['trial_id'],'Trial')
            if trial['logical_trial_id']!=v['logical_trial_id']:raise ContractError('attempt logical trial mismatch')
            if known(v['query_id']):
                query=self._record(db,r,v['query_id']['value'],'Query')
                if query['case_id']!=trial['case_id']:raise ContractError('attempt query belongs to another case')
                for row in db.execute("SELECT body FROM records WHERE run_id=? AND type='Attempt'",(r,)):
                    old=json.loads(row[0])
                    if old['trial_id']==v['trial_id'] and old['query_id']==v['query_id']:raise ContractError('query already attempted in this occurrence')
        if name=='Label':
            query=self._record(db,r,v['query_id'],'Query')
            ids=[]
            for ident,role in ((v['author_id'],'author'),(v['reviewer_id'],'reviewer')):
                row=self.workspace.truth.execute('SELECT * FROM identities WHERE id=?',(ident,)).fetchone()
                if row is None or row['role']!=role:raise ContractError('label identity role not independently provisioned')
                ids.append(row)
            if ids[0]['independence_group']==ids[1]['independence_group']:raise ContractError('label author/reviewer share independence group')
        if name=='Review':
            if v['label_ref']['kind']!='Label':raise ContractError('review requires typed Label reference')
            label=self._record(self.workspace.truth,r,v['label_ref']['id'],'Label')
            identity=self.workspace.truth.execute('SELECT role FROM identities WHERE id=?',(v['reviewer_id'],)).fetchone()
            if identity is None or identity[0] not in ('reviewer','adjudicator'):raise ContractError('reviewer role absent')
            author=self.workspace.truth.execute('SELECT independence_group FROM identities WHERE id=?',(label['author_id'],)).fetchone()
            reviewer=self.workspace.truth.execute('SELECT independence_group FROM identities WHERE id=?',(v['reviewer_id'],)).fetchone()
            if author is None or reviewer is None or author[0]==reviewer[0]:raise ContractError('review not independent of label author')
        if name=='Fault':
            case=self._record(db,r,v['mechanism_case_id'],'Case')
            if case['partition']!='MECH':raise ContractError('fault belongs to a MECH case')
        if name=='Metric':
            case=None
            if known(v['case_id']):
                case=self._record(db,r,v['case_id']['value'],'Case')
                if case['partition']!=v['partition']:raise ContractError('metric partition mismatch')
            if known(v['trial_id']):
                trial=self._record(db,r,v['trial_id']['value'],'Trial')
                if case is not None and trial['case_id']!=case['id']:raise ContractError('metric case/trial mismatch')
                trial_case=self._record(db,r,trial['case_id'],'Case')
                if trial_case['partition']!=v['partition']:raise ContractError('metric trial partition mismatch')
        if name=='Usage':
            self._record(db,r,v['logical_trial_id'],'Trial')
            for row in db.execute("SELECT body FROM records WHERE run_id=? AND type='Usage'",(r,)):
                old=json.loads(row[0])
                key=lambda ref:(ref['instance_id'],ref['id'],ref['kind'])
                attempt_key=lambda slot:key(slot['value']) if known(slot) else None
                if key(old['reservation_ref'])==key(v['reservation_ref']) and attempt_key(old['attempt_ref'])==attempt_key(v['attempt_ref']):raise ContractError('consumption event already recorded; no duplicate usage')
        if name=='Usage' and known(v['attempt_ref']):
            if v['attempt_ref']['value']['kind']!='Attempt':raise ContractError('usage requires typed Attempt reference')
            attempt=self._record(db,r,v['attempt_ref']['value']['id'],'Attempt')
            if attempt['logical_trial_id']!=v['logical_trial_id'] or attempt['reservation_ref']!=v['reservation_ref']:raise ContractError('usage attempt/reservation mismatch')
    def put(self,name,v):
        self._allow({'controller','evaluator'} if name not in TRUTH_TYPES else {'controller','reviewer'})
        validate_record(name,v);db=self._db(name)
        encoded=json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'));digest=hashlib.sha256(encoded.encode()).hexdigest();r=v['run_id']
        db.execute('BEGIN IMMEDIATE')
        try:
            old=db.execute('SELECT digest FROM records WHERE run_id=? AND id=?',(r,v['id'])).fetchone()
            if old:
                if old[0]!=digest:raise ContractError('record identity immutable; append explicit new evidence')
                db.execute('COMMIT');return v
            if name in TRUTH_TYPES:
                if self.workspace.metadata.execute('SELECT 1 FROM runs WHERE run_id=?',(r,)).fetchone() is None:raise ContractError('run absent')

            self._check_refs(v,r);self._relations(name,v)
            columns=list(v)
            values=[json.dumps(v[k],sort_keys=True,ensure_ascii=False,separators=(',',':')) if k in self.workspace.json_fields[name] else int(v[k]) if type(v[k]) is bool else v[k] for k in columns]
            db.execute('INSERT INTO tle_'+name.lower()+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',values)
            db.execute('COMMIT');return v
        except Exception:
            db.execute('ROLLBACK');raise
    def authorize_replacement(self,run_id,original_id,fault_id,assessor_id):
        self._allow({'controller'})
        original=self._record(self.workspace.metadata,run_id,original_id,'Trial')
        fault=self._record(self.workspace.metadata,run_id,fault_id,'Fault')
        identity=self.workspace.truth.execute('SELECT role FROM identities WHERE id=?',(assessor_id,)).fetchone()
        if original['status']!='infrastructure_invalid' or fault['status']!='completed' or fault['actual_terminal']['value']!='infrastructure_invalid' or identity is None or identity[0]!='independent_evaluator':raise ContractError('no qualified independent infrastructure damage evidence')
        self.workspace.metadata.execute('INSERT INTO replacement_authorizations VALUES(?,?,?,?)',(run_id,original_id,fault_id,assessor_id))
    def export_evidence(self,target,*,include_truth=False):
        """Explicit trusted-controller export; never a model-visible projection."""
        self._allow({'controller'})
        t.boolean(include_truth)
        target=Path(os.path.abspath(target))
        if any(p.is_symlink() for p in [target,*target.parents]):raise ContractError('symlink evidence path forbidden')
        if target.exists():raise ContractError('evidence export requires a new directory')
        target.mkdir(mode=0o700)
        exported=[]
        def snapshot(source,relative):
            path=target/relative;path.parent.mkdir(mode=0o700,exist_ok=True)
            out=sqlite3.connect(path)
            try:source.backup(out)
            finally:out.close()
            path.chmod(0o600);exported.append({'path':relative,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        rows=[{'type':r['type'],'record':json.loads(r['body'])} for r in self.workspace.metadata.execute("SELECT type,body FROM records WHERE type NOT IN ('Label','Review') ORDER BY run_id,id")]
        path=target/'evaluation-records.json';path.write_text(json.dumps(rows,sort_keys=True,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
        exported.append({'path':'evaluation-records.json','sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        if include_truth:snapshot(self.workspace.truth,'controller-truth/evaluation.sqlite')
        if (self.workspace.root/'budget.sqlite').exists():
            source=sqlite3.connect(self.workspace.root/'budget.sqlite')
            try:snapshot(source,'budget.sqlite')
            finally:source.close()
        manifest={'classification':'controller_audit_not_actor_input','includes_truth':include_truth,'snapshot_scope':'individual SQLite consistent snapshots; not a cross-database atomic snapshot','files':exported}
        path=target/'manifest.json';path.write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n');path.chmod(0o600)
        return manifest

    def validate_admission(self,run_id,partition):
        self._allow({'controller','evaluator','auditor'})
        cases=[json.loads(x[0]) for x in self.workspace.metadata.execute("SELECT body FROM records WHERE run_id=? AND type='Case'",(run_id,))]
        cases=[c for c in cases if c['partition']==partition]
        needed={'TARGET':800,'RETENTION':2000,'DEV':24}.get(partition)
        issues=[]
        if needed is not None and len(cases)!=needed:issues.append('wrong fixed case count')
        for case in cases:
            qs=[json.loads(x[0]) for x in self.workspace.metadata.execute("SELECT body FROM records WHERE run_id=? AND type='Query' AND case_id=?",(run_id,case['id']))]
            expected={'retention'} if partition=='RETENTION' else {'same_observation','new_question','boundary'}
            if {x['query_kind'] for x in qs}!=expected:issues.append('incomplete fixed queries: '+case['id'])
        return {'state':'blocked_before_start' if issues else 'material_structure_ready_only','issues':issues,'does_not_authorize_execution':True}

    def transition(self,name,run_id,ident,changes,*,deterministic_only=False):
        """Preserve lifecycle history; identity/configuration is immutable after creation."""
        self._allow({'controller','evaluator'})
        allowed={'Run':{'state'},'Trial':{'phase','status','outcome_ref'},'Attempt':{'actual_callback_entry','receipt_ref','outcome','usage_ref'},'Fault':{'actual_trace_ref','actual_terminal','status'}}
        if name not in allowed or not changes or set(changes)-allowed[name]:raise ContractError('unsupported lifecycle change')
        db=self._db(name);db.execute('BEGIN IMMEDIATE')
        try:
            old=self._record(db,run_id,ident,name);v={**old,**changes};validate_record(name,v)
            state_key={'Run':'state','Trial':'status','Attempt':'outcome','Fault':'status'}[name]
            before,after=old[state_key],v[state_key]
            edges={
              'Run':{'blocked_before_start':{'mechanism','stopped','failed'},'mechanism':{'completed','incomplete','failed','stopped'},'registered':{'stopped','failed'},'failed':set(),'stopped':set(),'completed':set(),'incomplete':set()},
              'Trial':{'registered':{'running','failed','stopped','not_run','infrastructure_invalid'},'running':{'completed','failed','stopped','incomplete','infrastructure_invalid'}},
              'Attempt':{'prepared':{'in_flight','failed','stopped','unknown'},'in_flight':{'received','failed','unknown','stopped'}},
              'Fault':{'planned':{'running','not_run'},'running':{'completed','failed'}}}
            if before!=after and after not in edges[name].get(before,set()):raise ContractError('illegal evaluation lifecycle transition')
            if name=='Run' and after=='mechanism' and not deterministic_only:raise ContractError('only deterministic mechanism may start here')
            if name=='Run' and after in ('dev','formal'):raise ContractError('real model launch unavailable')
            if name=='Attempt' and known(old['actual_callback_entry']) and old['actual_callback_entry']!=v['actual_callback_entry']:raise ContractError('actual callback entrance is immutable')
            self._check_refs(v,run_id)
            db.execute('CREATE TABLE IF NOT EXISTS lifecycle_history(run_id TEXT,id TEXT,sequence INTEGER,body TEXT NOT NULL,PRIMARY KEY(run_id,id,sequence))')
            seq=db.execute('SELECT COUNT(*) FROM lifecycle_history WHERE run_id=? AND id=?',(run_id,ident)).fetchone()[0]
            db.execute('INSERT INTO lifecycle_history VALUES(?,?,?,?)',(run_id,ident,seq,json.dumps(old,sort_keys=True)))
            body=json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
            columns=list(changes)
            values=[json.dumps(v[k],sort_keys=True,ensure_ascii=False,separators=(',',':')) if k in self.workspace.json_fields[name] else v[k] for k in columns]
            db.execute('UPDATE tle_'+name.lower()+' SET '+','.join(k+'=?' for k in columns)+' WHERE run_id=? AND id=?',(*values,run_id,ident))
            db.execute('COMMIT');return v
        except Exception:db.execute('ROLLBACK');raise

    def review_gate(self,run_id,blind_item_id):
        self._allow({'controller','reviewer','auditor'})
        reviews=[json.loads(x[0]) for x in self.workspace.truth.execute("SELECT body FROM records WHERE run_id=? AND type='Review' AND blind_item_id=?",(run_id,blind_item_id))]
        identities=[self.workspace.truth.execute('SELECT * FROM identities WHERE id=?',(x['reviewer_id'],)).fetchone() for x in reviews]
        groups={x['independence_group'] for x in identities if x is not None}
        issues=[]
        if len(reviews)<2 or len(groups)<2:issues.append('two independent review groups absent')
        if any(x is None or x['synthetic'] for x in identities):issues.append('synthetic/unprovisioned roles cannot satisfy formal review')
        if len({r['original_rating'] for r in reviews})>1 and any(not known(r['resolution_ref']) for r in reviews):issues.append('disagreement adjudication missing')
        return {'state':'blocked_before_start' if issues else 'review_evidence_ready_only','issues':issues,'does_not_authorize_execution':True}
