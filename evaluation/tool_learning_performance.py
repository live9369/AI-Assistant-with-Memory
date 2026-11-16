"""One fresh synthetic full-packet benchmark; never reads an existing instance."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run(destination):
    os.environ['DIGITAL_LIFE_REAL_MODEL']='0'
    from tests.test_tool_learning_runtime import StrictEngineEndToEndTests
    from digital_life.infrastructure.persistence.sqlite_store import Store
    from digital_life.infrastructure.persistence.tool_learning_meter import _Connection,_Cursor
    fixture=StrictEngineEndToEndTests('test_ordinary_actual_engine_full_packet_and_real_original_account')
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((ROOT/'digital_life').rglob('*.py'))}
    (destination/'pid.json').write_text(json.dumps({'pid':os.getpid(),'scope':'owned fresh synthetic benchmark'})+'\n')
    result={'scope':'Exact existing full 8-module/17-episode synthetic case, original caps; no stack sampling','real_models_called':False,'formal_instance_accessed':False,'source_files_before':sources}
    try:
        fixture.setUp()
        import tempfile
        assert fixture.s.root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        assert 'question' in {r[1]for r in fixture.s.db.execute('PRAGMA table_info(cognition_episodes)')}
        result['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        started=time.monotonic()
        fixture.test_ordinary_actual_engine_full_packet_and_real_original_account()
        result['wall_seconds']=time.monotonic()-started
        s=fixture.s
        request=s.db.execute("SELECT * FROM thought_requests WHERE activity_id=? AND instruction_version='strict-complete-packet-1'",(fixture.activity,)).fetchone()
        packet=s.read_artifact(request['request_artifact_id'])
        proof=s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='tl.input.assembly' AND source_event_id=?",(request['id'],)).fetchone()
        manifest=s.read_artifact(proof[0])['manifest']
        feature=packet['input']['features']
        result['input_coverage']={'feature_keys':sorted(feature),'feature_top_level_shapes':{k:sorted(v)if type(v)is dict else {'type':type(v).__name__,'length':len(v)if type(v)in(list,str)else None}for k,v in feature.items()},'manifest_paths':sorted(f['path']for f in manifest['fields']),'manifest_fields':len(manifest['fields']),'manifest_dependencies':sum(len(f['dependencies'])for f in manifest['fields']),'native_tl_input_dependencies':s.db.execute('SELECT count(*) FROM tl_input_dependency WHERE request_ref_id=?',(request['id'],)).fetchone()[0],'source_episode_count':s.db.execute("SELECT count(*) FROM cognition_episodes WHERE activity_id=? AND question LIKE 'synthetic prior episode %'",(fixture.activity,)).fetchone()[0]}
        result['budget']=json.loads(s.row('activities',fixture.activity)['budget_json'])
        result['accepted']=request['state']=='succeeded'
        (destination/'packet.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n')
        (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        result['packet_sha256']=hashlib.sha256((destination/'packet.json').read_bytes()).hexdigest()
        result['passed']=True
    except BaseException as error:
        import traceback
        result.update(passed=False,error_type=type(error).__name__,traceback=traceback.format_exc())
    finally:
        fixture.doCleanups()
        result['source_files_after']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((ROOT/'digital_life').rglob('*.py'))}
        result['source_stable_during_benchmark']=result['source_files_before']==result['source_files_after']
        (destination/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result.get(k)for k in ('passed','wall_seconds','source_stable_during_benchmark','input_coverage','error_type')},ensure_ascii=False),flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    raise SystemExit(0 if run(a.output)['passed']else 1)
