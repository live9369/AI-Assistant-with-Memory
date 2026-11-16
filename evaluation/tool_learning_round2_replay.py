"""Independent synthetic replay: fixed world inputs, real monotonic/accounting.

Execute as a script with --source pointing at a reviewed public source snapshot.
Never accepts an instance path. Source imports must resolve underneath --source.
"""
import argparse
from collections import namedtuple
import datetime
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import uuid


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--history',type=int,default=17);parser.add_argument('--continuous',type=int,default=1);parser.add_argument('--setup-only',action='store_true')
    args=parser.parse_args()
    if args.history not in (0,17,50,100) or args.continuous not in (1,2):raise ValueError('fixed synthetic scale only')
    source=Path(args.source).resolve();output=Path(args.output).resolve()
    if not (source/'tests/test_tool_learning_runtime.py').is_file():raise ValueError('reviewed source tree required')
    output.mkdir(parents=True,exist_ok=False)
    os.environ['DIGITAL_LIFE_REAL_MODEL']='0'
    sys.path.insert(0,str(source))
    # Fixed environmental inputs apply only inside this one synthetic process.
    real_datetime=datetime.datetime
    instant=real_datetime(2031,1,2,3,4,5,678000,tzinfo=datetime.timezone.utc)
    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls,tz=None):
            value=instant if tz is None else instant.astimezone(tz)
            if tz is None:value=value.replace(tzinfo=None)
            return cls.fromisoformat(value.isoformat())
        @classmethod
        def utcnow(cls):return cls.now(datetime.timezone.utc).replace(tzinfo=None)
    datetime.datetime=FrozenDateTime
    original_connect=sqlite3.connect
    sql_clock=original_connect(':memory:')
    def connect(*a,**k):
        db=original_connect(*a,**k)
        def strftime(*values):
            values=list(values)
            if len(values)>1 and values[1]=='now':values[1]='2031-01-02T03:04:05.678Z'
            # Delegate date validation and modifiers to SQLite's real builtin.
            return sql_clock.execute('SELECT strftime('+','.join('?'for _ in values)+')',values).fetchone()[0]
        db.create_function('strftime',-1,strftime)
        return db
    sqlite3.connect=connect
    sequence=[0]
    def next_uuid():
        sequence[0]+=1
        return uuid.UUID(hashlib.sha256(('PF-REPLAY-1:'+str(sequence[0])).encode()).hexdigest()[:32])
    uuid.uuid4=next_uuid
    disk=namedtuple('usage','total used free')(1024**4,512*1024**3,512*1024**3)
    shutil.disk_usage=lambda path:disk
    import digital_life
    if not Path(digital_life.__file__).resolve().is_relative_to(source):raise ValueError('source isolation failed')
    from tests.test_tool_learning_runtime import StrictEngineEndToEndTests
    from digital_life.application.runtime.engine import Engine
    from digital_life.application.services import Cognition
    from digital_life.domain.contracts import identifier
    source_hashes=lambda:{str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((source/'digital_life').rglob('*.py'))}
    fixture=StrictEngineEndToEndTests('test_ordinary_actual_engine_full_packet_and_real_original_account')
    result={'scope':'fixed synthetic environmental inputs; real monotonic and original accounting','source':str(source),'history':args.history,'continuous':args.continuous,'setup_only':args.setup_only,'real_models_called':False,'formal_instance_accessed':False,'clock':'2031-01-02T03:04:05.678Z','runs':[]}
    result['source_files_before']=source_hashes();result['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        fixture.setUp()
        import tempfile
        assert fixture.s.root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        result['fixture_uuid_calls']=sequence[0]
        result['fixture_configuration']=fixture.s.config()
        for index in range(0 if args.setup_only else args.continuous):
            if index:
                key=identifier();fixture.control.accept_inbound('strict-fixture-controller',key,{'text':'继续独立思考'},fixture.s.config()['controller'])
                fixture.activity=Engine(fixture.s,fixture.identity).submit('继续独立思考',key,'strict-fixture-controller')
            context=fixture.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(fixture.activity,)).fetchone()[0]
            for item in range(args.history):Cognition(fixture.s).episode(fixture.activity,context,'synthetic prior episode '+str(item))
            started=time.monotonic();thought=Engine(fixture.s,fixture.identity,strict_runtime=fixture.strict).think(fixture.activity)
            row=fixture.s.row('thought_requests',thought['request_id']);packet=fixture.s.read_artifact(row['request_artifact_id'])
            event=fixture.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='tl.input.assembly' AND source_event_id=?",(row['id'],)).fetchone()
            manifest=fixture.s.read_artifact(event[0])['manifest']
            folder=output/('thought-'+str(index));folder.mkdir()
            for name,value in (('packet',packet),('manifest',manifest)):(folder/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
            budget=json.loads(fixture.s.row('activities',fixture.activity)['budget_json'])
            result['runs'].append({'accepted':thought['accepted'],'wall_seconds':time.monotonic()-started,'request_id':row['id'],'packet_folder':str(folder),'budget':budget,'uuid_calls':sequence[0]})
        result['passed']=all(r['accepted']for r in result['runs'])
    except BaseException as exc:
        import traceback
        result.update(passed=False,error_type=type(exc).__name__,traceback=traceback.format_exc())
    finally:
        fixture.doCleanups()
        sql_clock.close()
        result['source_files_after']=source_hashes();result['source_stable']=result['source_files_before']==result['source_files_after']
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':result['passed'],'runs':[(r['accepted'],r['wall_seconds'])for r in result['runs']],'error':result.get('error_type')}),flush=True)
    return 0 if result['passed']else 1


if __name__=='__main__':raise SystemExit(main())
