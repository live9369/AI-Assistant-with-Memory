"""Current read-only substrate probes, separate from historical model input."""
import shutil
import time
import sqlite3
from digital_life.domain.contracts import Forbidden,ContractError,utc

REQUIRED=('R.disk_free_bytes','F.sqlite_integrity','F.restore_reconciliation_required','W.queue_depth')


def startup_integrity_matches(store,connection=None):
    stamp=getattr(store,'_startup_integrity',None)
    if not stamp:return False
    path=store.root/'runtime.sqlite'
    if path.is_symlink():return False
    info=path.stat();db=connection or store.db
    configuration=store.db.execute('SELECT id FROM configuration_versions WHERE instance_id=? ORDER BY rowid DESC LIMIT 1',(store.instance_id,)).fetchone()[0]
    return stamp['file_identity']==(info.st_dev,info.st_ino) and stamp['schema_version']==db.execute('PRAGMA schema_version').fetchone()[0] and stamp['configuration_id']==configuration


class CurrentHealthEvidence:
    def __init__(self,store,activity,request,*,completion_freshness=False):
        self.store=store;self.activity=activity;self.request=request;self.at=utc();self.started=time.monotonic();self.used=False;self.probes={}
        if type(completion_freshness)is not bool:raise ContractError('boolean completion freshness required')
        self.completion_freshness=completion_freshness;self.measurement_started_at=self.at
        self.connection=None;self.version=None;self.file_identity=None;self.database_unchanged=False
        self.local_changes=store.db.total_changes
        def known(name,read):
            try:
                value=read()
                if type(value) is not int or value<0:raise ContractError('invalid health probe value')
                self.probes[name]={'status':'known','value':value,'basis':'actual current local probe'}
            except (OSError,ValueError,TypeError,ContractError,sqlite3.DatabaseError):self.probes[name]={'status':'unknown','value':None,'basis':'current local probe could not be confirmed'}
        def sqlite():
            if self.completion_freshness:
                path=store.root/'runtime.sqlite'
                if path.is_symlink():raise ContractError('health database symlink')
                info=path.stat();self.file_identity=(info.st_dev,info.st_ino)
                self.connection=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)
                self.version=self.connection.execute('PRAGMA data_version').fetchone()[0]
                reusable=startup_integrity_matches(store,self.connection)
                self.integrity_basis='startup check with current file/schema/configuration match' if reusable else 'current full database check'
                if reusable:integrity='ok';foreign=None
                else:
                    integrity=self.connection.execute('PRAGMA integrity_check').fetchone()[0]
                    foreign=self.connection.execute('PRAGMA foreign_key_check').fetchone()
                if self.connection.execute('PRAGMA data_version').fetchone()[0]!=self.version:
                    raise ContractError('database changed during health measurement')
                return int(integrity=='ok' and foreign is None)
            if getattr(store.db,'in_transaction',False):
                # Health measures committed storage, not intermediate rows in
                # the calculation transaction. Actual dispatch/retention still
                # repeats this probe after that transaction has committed.
                path=store.root/'runtime.sqlite'
                if path.is_symlink():raise Forbidden('health database symlink')
                connection=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)
                try:
                    integrity=connection.execute('PRAGMA integrity_check').fetchone()[0]
                    foreign=connection.execute('PRAGMA foreign_key_check').fetchone()
                    return int(integrity=='ok' and foreign is None)
                finally:connection.close()
            value=store.integrity();return int(value['integrity']=='ok' and not value['foreign_keys'])
        if not self.completion_freshness:known(REQUIRED[0],lambda:shutil.disk_usage(store.root).free)
        known(REQUIRED[1],sqlite)
        if self.completion_freshness:known(REQUIRED[0],lambda:shutil.disk_usage(store.root).free)
        known(REQUIRED[2],lambda:int((store.root/'RESTORE_RECONCILIATION_REQUIRED').exists()))
        known(REQUIRED[3],lambda:store.db.execute("SELECT count(*) FROM jobs WHERE instance_id=? AND state IN ('queued','leased')",(store.instance_id,)).fetchone()[0])
        if self.completion_freshness:self.probes[REQUIRED[1]]['basis']=getattr(self,'integrity_basis','current full database check')
        self.completed=time.monotonic();self.measurement_finished_at=utc()
        if self.completion_freshness:self.at=self.measurement_finished_at
    def consume(self,store,activity):
        if self.completion_freshness:
            try:
                if self.used or self.store is not store or self.activity!=activity or time.monotonic()-self.completed>1:
                    raise Forbidden('current health evidence is stale, reused or misbound')
                self.used=True
                if set(self.probes)!=set(REQUIRED) or any(value['status']!='known' for value in self.probes.values()):
                    raise Forbidden('required current health probe is unknown')
                path=store.root/'runtime.sqlite';info=path.stat()
                if path.is_symlink() or (info.st_dev,info.st_ino)!=self.file_identity or self.connection is None:
                    raise Forbidden('health database identity changed')
                if self.connection.execute('PRAGMA data_version').fetchone()[0]!=self.version or store.db.total_changes!=self.local_changes:
                    raise Forbidden('database changed during health measurement or before consumption')
                if time.monotonic()-self.completed>1:raise Forbidden('completed health evidence expired during verification')
                self.database_unchanged=True
                return {name:{'value':value['value'],'fresh':True,'observed_at':self.at,'source':'current-read-only-admission-probe','ref':None} for name,value in self.probes.items()}
            except (OSError,sqlite3.DatabaseError) as error:
                raise Forbidden('current health database consistency could not be confirmed') from error
            finally:
                if self.connection is not None:self.connection.close();self.connection=None
        if self.used or self.store is not store or self.activity!=activity or time.monotonic()-self.started>1:raise Forbidden('current health evidence is stale, reused or misbound')
        self.used=True
        if set(self.probes)!=set(REQUIRED) or any(value['status']!='known' for value in self.probes.values()):raise Forbidden('required current health probe is unknown')
        return {name:{'value':value['value'],'fresh':True,'observed_at':self.at,'source':'current-read-only-admission-probe','ref':None} for name,value in self.probes.items()}
    def audit(self):
        result={'contract':'TL-CURRENT-HEALTH-GUARD-1','activity_id':self.activity,'request':self.request,'observed_at':self.at,'probes':self.probes,'input_snapshot_rewritten':False,'state_observations_written':False}
        if self.completion_freshness:result.update(freshness_basis='measurement_completed',measurement_started_at=self.measurement_started_at,measurement_finished_at=self.measurement_finished_at,measurement_elapsed_ms=(self.completed-self.started)*1000,database_unchanged=self.database_unchanged)
        return result


class CurrentHealthProbe:
    """Bound one-shot probe request, not pre-collected evidence."""
    def __init__(self,store,activity,request,*,completion_freshness=False):
        self.store=store;self.activity=activity;self.request=request;self.evidence=None;self.completion_freshness=completion_freshness
    def measure(self,store,activity):
        if self.store is not store or self.activity!=activity or self.evidence is not None:
            raise Forbidden('current health probe is reused or misbound')
        self.evidence=CurrentHealthEvidence(store,activity,self.request,completion_freshness=self.completion_freshness)
        return self.evidence
    def audit(self):
        if self.evidence is not None:return self.evidence.audit()
        return {'contract':'TL-CURRENT-HEALTH-GUARD-1','activity_id':self.activity,'request':self.request,'observed_at':None,
                'probes':{name:{'status':'unknown','value':None,'basis':'probe not entered'} for name in REQUIRED},
                'input_snapshot_rewritten':False,'state_observations_written':False}
