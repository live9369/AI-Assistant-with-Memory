"""Audited one-to-many reuse of real existing isolated unittest fixtures.

Each unique fixture runs once per repeat; aliases never manufacture additional
opportunities. Full assertion values and committed synthetic snapshots are
external observations, not a second runtime authority or a semantic oracle.
"""
import ast
import hashlib
import inspect
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def encode(value):
    if value is None or type(value) in (str,int,float,bool):return value
    if isinstance(value,bytes):return {'bytes_hex':value.hex()}
    if isinstance(value,(tuple,list)):return [encode(v) for v in value]
    if isinstance(value,dict):return {str(k):encode(v) for k,v in value.items()}
    if isinstance(value,type):return {'type':value.__module__+'.'+value.__name__}
    return {'repr':repr(value),'type':type(value).__name__}


def fixture_index():
    result={}
    for path in sorted((ROOT/'tests').glob('test_tool_learning*.py')):
        if path.name=='test_tool_learning_mechanisms.py':continue
        source=path.read_text();tree=ast.parse(source)
        for cl in tree.body:
            if not isinstance(cl,ast.ClassDef):continue
            for node in cl.body:
                if not isinstance(node,ast.FunctionDef) or not node.name.startswith('test_'):continue
                key=path.stem.removeprefix('test_tool_learning_')+'.'+node.name.removeprefix('test_')
                ident='tests.'+path.stem+'.'+cl.name+'.'+node.name
                result.setdefault(key,[]).append({'id':ident,'path':str(path.relative_to(ROOT)),'line':node.lineno,
                    'source':ast.get_source_segment(source,node),'source_file_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


def _snapshot(store):
    root=store.root.resolve();temporary=Path(tempfile.gettempdir()).resolve()
    if not root.is_relative_to(temporary):raise AssertionError('observer refused a non-temporary instance path')
    result={'root':str(root),'instance_id':store.instance_id,'tables':{},'artifacts':{},'observer':'external read-only committed snapshot; not charged as runtime IO'}
    connection=None
    try:
        connection=sqlite3.connect((root/'runtime.sqlite').as_uri()+'?mode=ro',uri=True);connection.row_factory=sqlite3.Row
        names=[r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        selected={'object_registry','object_revision_registry','activities','activity_budget_accounts','cognition_beliefs','cognition_belief_revisions','cognition_concepts','cognition_concept_revisions','memory_items','memory_revisions','thought_requests','thought_attempts','thought_results','action_intents','action_attempts','action_results','artifacts','runtime_events'}
        for table in names:
            if table.startswith('tl_') or table in selected:
                result['tables'][table]=[encode(dict(row)) for row in connection.execute('SELECT * FROM "'+table+'" ORDER BY rowid')]
        blobs=root/'blobs'
        if blobs.is_symlink():result['artifact_observation_error']='blob directory is a symlink; observer did not follow'
        else:
            for artifact in result['tables'].get('artifacts',[]):
                name=artifact['storage_ref']
                if not isinstance(name,str) or len(name)!=64 or any(v not in '0123456789abcdef' for v in name):continue
                path=blobs/name
                if path.is_symlink():result['artifacts'][artifact['id']]={'unsafe_symlink_not_read':True};continue
                if not path.exists():result['artifacts'][artifact['id']]={'missing':True};continue
                if path.stat().st_size>1048576:
                    result['artifacts'][artifact['id']]={'bytes':path.stat().st_size,'body_retained':False,'reason':'large byte-bound fixture; actual assertions retained'};continue
                raw=path.read_bytes();body=None
                try:body=json.loads(raw) if artifact['media_type']=='application/json' else raw.decode('utf-8')
                except (ValueError,UnicodeError):body={'bytes_hex':raw.hex()}
                result['artifacts'][artifact['id']]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'body':body}
    except BaseException as error:result['observation_error']={'type':type(error).__name__,'message':str(error)}
    finally:
        if connection is not None:connection.close()
    return result


def run_fixture(spec):
    from digital_life.infrastructure.persistence.sqlite_store import Store
    assertions=[];snapshots=[];connections=[];sql=[];sql_count=0;sql_digest=hashlib.sha256()
    original_init=Store.__init__;original_close=Store.close
    def opened(store,root):
        path=Path(root).resolve()
        if not path.is_relative_to(Path(tempfile.gettempdir()).resolve()):raise AssertionError('reused fixture attempted to open a non-temporary Store')
        original_init(store,root);connections.append(store)
        def trace(statement):
            nonlocal sql_count
            sql_count+=1;sql_digest.update(statement.encode());sql_digest.update(b'\n')
            if len(sql)<4096:sql.append(statement)
        store.db.set_trace_callback(trace)
    def closed(store):
        if any(store is item for item in connections):
            snapshots.append(_snapshot(store));connections[:]=[item for item in connections if item is not store]
        return original_close(store)
    def assertion(name,original):
        def wrapped(test,*args,**kwargs):
            frame=inspect.currentframe().f_back
            path=Path(frame.f_code.co_filename)
            assertions.append({'method':name,'source':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),'line':frame.f_lineno,'arguments':encode(args),'keywords':encode(kwargs)})
            return original(test,*args,**kwargs)
        return wrapped
    patches=[patch.object(Store,'__init__',opened),patch.object(Store,'close',closed)]
    for name in vars(unittest.TestCase):
        if name.startswith('assert') and callable(getattr(unittest.TestCase,name)):
            patches.append(patch.object(unittest.TestCase,name,assertion(name,getattr(unittest.TestCase,name))))
    started=time.monotonic();result=unittest.TestResult()
    try:
        for item in patches:item.start()
        suite=unittest.defaultTestLoader.loadTestsFromName(spec['id'])
        suite.run(result)
    finally:
        for store in list(connections):
            try:snapshots.append(_snapshot(store))
            except BaseException:pass
        for item in reversed(patches):item.stop()
    status='pass' if result.testsRun==1 and not(result.failures or result.errors or result.skipped or result.expectedFailures or result.unexpectedSuccesses) else 'fail'
    return {'fixture_id':spec['id'],'fixture_source':spec,'status':status,'tests_run':result.testsRun,
        'failures':[(str(test),error) for test,error in result.failures],'errors':[(str(test),error) for test,error in result.errors],
        'skipped':[(str(test),why) for test,why in result.skipped],'assertion_execution_trace':assertions,'synthetic_committed_snapshots':snapshots,
        'physical_sql_sample':sql,'physical_sql_statements':sql_count,'physical_sql_sha256':sql_digest.hexdigest(),'sql_sample_truncated':sql_count>len(sql),
        'duration_seconds':time.monotonic()-started,'real_model_called':False,'formal_instance_opened':False,
        'opportunity_policy':'one actual fixture per repeat, may support multiple explicit obligation clauses; no alias creates a new case/trial'}
