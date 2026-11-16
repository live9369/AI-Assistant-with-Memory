"""Locally reviewed schema4 bridge baseline and durable deployment proof.

This is not a signature for arbitrary code. A new candidate must exactly match
our currently loaded, reviewed source baseline before it can be registered.
"""
import ast
import json
import os
from digital_life.domain.tool_learning_contract import loads as strict_json
from pathlib import Path
from digital_life.domain.contracts import ContractError,Forbidden,Conflict,dumps,sha,utc

CONTRACT='TL-SCHEMA4-BRIDGE-1'
CAPABILITY={'contract':CONTRACT,'barrier_contract':'TL-LOOP-0.1','qualified_plane':'schema4-always','new_learning_default':False,'rollback':'same-current-database'}
EXCLUDE={'work','.git','__pycache__','.venv','snapshots','releases','blobs','build','dist','outputs','.codex','.agents','.aws','.ssh','.gnupg','.secrets','node_modules'}
ROOT_RUNTIME={'workspace','inbound','launches','logs','sessions'}
ROOT_PRIVATE_FILES={'controller.token','auth.json','credentials.json','tokens.json','token.json','runtime.sqlite','control.sqlite'}
SUFFIXES={'.py','.sql','.json','.toml','.html','.css','.js'}


def source_files(source):
    source=Path(source).resolve();files=[];size=0;scanned=0;pending=[source]
    # Prune directory entries BEFORE recursion or file reads. Iterative scandir
    # also bounds public metadata traversal, including ignored file suffixes.
    while pending:
        parent=pending.pop()
        with os.scandir(str(parent)) as entries:
            for entry in entries:
                scanned+=1
                if scanned>20000:raise ContractError('release source traversal exceeds bounds')
                path=parent/entry.name;relative=path.relative_to(source);name=entry.name
                if name in EXCLUDE or name.endswith('.egg-info') or relative.parts[:2]==('config','local') or len(relative.parts)==1 and name in ROOT_RUNTIME:continue
                if relative==Path('manifest.json') or name=='.env' or name.startswith('.env.') or len(relative.parts)==1 and name in ROOT_PRIVATE_FILES:continue
                if entry.is_symlink():raise Forbidden('release contains symlinks')
                if entry.is_dir(follow_symlinks=False):pending.append(path);continue
                if not entry.is_file(follow_symlinks=False) or path.suffix not in SUFFIXES:continue
                raw=path.read_bytes();size+=len(raw)
                if size>20000000 or len(files)>=5000:raise ContractError('release exceeds bounds')
                if path.suffix=='.py':ast.parse(raw,filename=str(relative))
                files.append((relative,raw))
    return sorted(files,key=lambda item:str(item[0]))


def declaration(value,allow_legacy=False):
    if not isinstance(value,dict):raise ContractError('release declaration must be an object')
    low=value.get('schema_min');high=value.get('schema_max')
    if type(low) is not int or type(high) is not int or not 2<=low<=high<=4:raise ContractError('invalid release schema compatibility declaration')
    if high==4:
        keys={'schema_min','schema_max','engineering_version','tool_learning_bridge','capabilities'}
        legacy=allow_legacy and 'capabilities' not in value
        if set(value)!=(keys-{'capabilities'} if legacy else keys) or value['tool_learning_bridge']!=CAPABILITY:raise Forbidden('schema4 release lacks the closed bridge capability')
        if not legacy and (type(value['capabilities']) is not list or len(value['capabilities'])!=1 or type(value['capabilities'][0]) is not str or value['capabilities']!=['TL-LOOP-0.1']):raise Forbidden('release capabilities must be the exact unique TL contract array')
        capability=value['tool_learning_bridge']
        if type(capability) is not dict or type(capability.get('new_learning_default')) is not bool or any(type(capability.get(k)) is not str for k in ('contract','barrier_contract','qualified_plane','rollback')):raise Forbidden('schema4 bridge capability has invalid field types')
        if not isinstance(value['engineering_version'],str) or not value['engineering_version']:raise ContractError('release engineering version missing')
    return value


def baseline_candidate(source,manifest,description):
    declaration(description)
    if description['schema_max']<4:return None
    from digital_life.infrastructure.persistence.sqlite_store import PROJECT
    reference={str(path):sha(raw) for path,raw in source_files(PROJECT)}
    if manifest!=reference:raise Forbidden('schema4 candidate differs from the current reviewed executable source baseline')
    import digital_life
    if description['engineering_version']!=digital_life.__version__:raise Conflict('bridge declaration does not match actual loaded package version')
    return {'contract':CONTRACT,'manifest_digest':sha(dumps(manifest)),'capability':CAPABILITY,'engineering_version':digital_life.__version__,'schema_min':description['schema_min'],'schema_max':description['schema_max']}


def register_baseline(control,checksum,proof):
    if proof is None:return
    value=dict(proof,build_hash=checksum,instance_id=control.instance)
    with control.tx():
        key,_=control.command('bridge.baseline_verified','schema4-bridge:'+checksum,value,authority='reviewed-bridge-baseline')
        control.db.execute("UPDATE control_commands SET state='succeeded',finished_at=? WHERE id=?",(utc(),key))


def verified_baseline(control,release,manifest,description):
    declaration(description,allow_legacy=True)
    if description['schema_max']<4:return None
    row=control.db.execute("SELECT * FROM control_commands WHERE instance_ref=? AND source='reviewed-bridge-baseline' AND command_key=? AND kind='bridge.baseline_verified' AND state='succeeded'",(control.instance,'schema4-bridge:'+release['build_hash'])).fetchone()
    if row is None:raise Forbidden('no current trusted bridge baseline record for this build')
    from digital_life.domain import tool_learning_contract as c
    value=c.loads(row['payload'])
    expected={'contract':CONTRACT,'manifest_digest':sha(dumps(manifest)),'capability':CAPABILITY,'engineering_version':description['engineering_version'],'schema_min':release['schema_min'],'schema_max':release['schema_max'],'build_hash':release['build_hash'],'instance_id':control.instance}
    if dumps(value)!=dumps(expected) or row['payload_hash']!=sha(dumps(value)):raise Conflict('bridge baseline identity/capability binding differs')
    return value


def loaded_runtime(control,store,deployment,loaded_path):
    """Verify the actual imported runtime against its staged immutable files."""
    from digital_life.application.lifecycle.control_plane import Releases
    release=control.db.execute('SELECT * FROM deployments WHERE id=?',(deployment,)).fetchone()
    if release is None:raise Forbidden('runtime deployment missing')
    path=Releases(control).verify(deployment);actual=Path(loaded_path).resolve()
    if actual!=path/'digital_life/entrypoints/runtime.py':raise Forbidden('runtime was imported outside the selected verified deployment')
    description=declaration(strict_json((path/'digital_life/resources/release.json').read_text()),allow_legacy=True)
    manifest=strict_json((path/'manifest.json').read_text());version=store.db.execute('PRAGMA user_version').fetchone()[0]
    import sys
    for name,module in tuple(sys.modules.items()):
        if name!='digital_life' and not name.startswith('digital_life.'):continue
        filename=getattr(module,'__file__',None)
        if not filename:raise Forbidden('loaded digital-life module has no verifiable source path')
        filename=Path(filename).resolve()
        try:relative=str(filename.relative_to(path))
        except ValueError:raise Forbidden('loaded module comes from another release baseline')
        if relative not in manifest or sha(filename.read_bytes())!=manifest[relative]:raise Forbidden('loaded module bytes differ from selected bridge baseline')
    if not release['schema_min']<=version<=release['schema_max']:raise Forbidden('actual database schema is outside loaded release range')
    required=protected_storage_required(store.db,control)
    if required:
        verify_schema4_layout(store.db)
        if release['schema_max']!=4:raise Forbidden('protected storage requires a verified bridge even before schema4 migration')
    proof=verified_baseline(control,release,manifest,description) if required else None
    import digital_life
    if proof and digital_life.__version__!=proof['engineering_version']:raise Conflict('loaded bridge package version differs')
    return {'instance_id':store.instance_id,'schema_version':version,'build_hash':release['build_hash'],'bridge_contract':CONTRACT if proof else None,'manifest_digest':sha(dumps(manifest)),'engineering_version':digital_life.__version__,'qualified_plane_required':required}


def verify_handshake(control,deployment,response,stage=None):
    release=control.db.execute('SELECT * FROM deployments WHERE id=?',(deployment,)).fetchone()
    if release is None:raise Forbidden('handshake deployment missing')
    if type(response) is not dict:raise ContractError('readiness must be an object')
    if response.get('deployment')!=deployment or response.get('schema_compatible') is not True:raise ContractError('runtime deployment readiness mismatch')
    # Existing schema2/3 drivers keep their legacy protocol. Actual schema4
    # requires the full proof and cannot be certified by a bool-only fake.
    import sqlite3
    db=sqlite3.connect((control.root/'runtime.sqlite').as_uri()+'?mode=ro',uri=True)
    try:
        version=db.execute('PRAGMA user_version').fetchone()[0];required=protected_storage_required(db,control)
        if required:verify_schema4_layout(db)
    finally:db.close()
    if required:
        if release['schema_max']!=4:raise Forbidden('protected storage cannot accept an old release handshake')
        from digital_life.application.lifecycle.control_plane import Releases
        path=Releases(control).verify(deployment);manifest=strict_json((path/'manifest.json').read_text());description=declaration(strict_json((path/'digital_life/resources/release.json').read_text()),allow_legacy=True);proof=verified_baseline(control,release,manifest,description)
        expected={'instance_id':control.instance,'schema_version':version,'build_hash':release['build_hash'],'bridge_contract':CONTRACT,'manifest_digest':proof['manifest_digest'],'engineering_version':description['engineering_version'],'qualified_plane_required':True}
        value=response.get('capability')
        if type(value) is not dict or set(value)!=set(expected) or type(value.get('schema_version')) is not int or type(value.get('qualified_plane_required')) is not bool or any(type(value.get(key)) is not str for key in ('instance_id','build_hash','bridge_contract','manifest_digest','engineering_version')) or value!=expected:raise Forbidden('actual schema4 runtime capability handshake missing or differs')
        if type(response.get('pid')) is not int or response['pid']<=0:raise Forbidden('schema4 runtime actual PID missing')
        if response.get('state') not in ('prepared','running') or stage is not None and response['state']!=stage:raise Forbidden('schema4 runtime readiness phase mismatch')
        if type(response.get('model_access_verified')) is not bool or response['model_access_verified'] or response.get('inference_ready')!='unknown' or response.get('model_readiness')!='unverified':raise Forbidden('bridge readiness must not assert unverified model access')
    return response


def read_readiness(path,max_bytes=65536):
    """Small nofollow local control message, strict JSON, no material body."""
    import os,stat
    from digital_life.domain import tool_learning_contract as c
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>max_bytes:raise ContractError('runtime readiness exceeds local control bound')
        raw=stream.read(max_bytes+1)
    if len(raw)>max_bytes:raise ContractError('runtime readiness exceeds local control bound')
    result=c.loads(raw)
    if not isinstance(result,dict):raise ContractError('runtime readiness must be an object')
    return result


_EXPECTED_TL_SCHEMA=None
_EXPECTED_SOURCE_LOOKUP_INDEX=None

def verify_schema4_layout(db):
    """An integer version is not proof that the actual protective DDL exists."""
    global _EXPECTED_TL_SCHEMA,_EXPECTED_SOURCE_LOOKUP_INDEX
    if _EXPECTED_TL_SCHEMA is None:
        import sqlite3
        from digital_life.infrastructure.persistence.sqlite_store import RESOURCES
        expected=sqlite3.connect(':memory:')
        try:
            expected.executescript((RESOURCES/'runtime.sql').read_text())
            expected.executescript((RESOURCES/'tool_learning_v1.sql').read_text())
            _EXPECTED_TL_SCHEMA={row[0]:(row[1],row[2]) for row in expected.execute("SELECT name,type,sql FROM sqlite_master WHERE name GLOB 'tl_*'")}
            expected.execute((RESOURCES/'source_lookup_indexes.sql').read_text())
            _EXPECTED_SOURCE_LOOKUP_INDEX=expected.execute("SELECT type,sql FROM sqlite_master WHERE name='tl_dependency_consumer_order'").fetchone()
        finally:expected.close()
    actual={row[0]:(row[1],row[2]) for row in db.execute("SELECT name,type,sql FROM sqlite_master WHERE name GLOB 'tl_*'")}
    # One reviewed, non-unique read index is optional for existing instances.
    # Validate its complete definition; all original protective DDL and every
    # other tl_* object still require an exact frozen-layout match.
    lookup=actual.pop('tl_dependency_consumer_order',None)
    if lookup is not None and lookup!=_EXPECTED_SOURCE_LOOKUP_INDEX:
        raise Forbidden('source lookup index differs from the reviewed definition')
    if actual!=_EXPECTED_TL_SCHEMA:raise Forbidden('actual schema4 protective tables/constraints/triggers do not match the frozen layout')
    return sha(dumps(actual))


def protected_storage_required(db,control):
    version=db.execute('PRAGMA user_version').fetchone()[0]
    if type(version) is not int or version not in (2,3,4):raise Forbidden('unsupported storage schema cannot receive a compatibility grant')
    if version==4:return True
    from digital_life.application.learning.runtime import PERSISTENT_TL_MATERIAL_TABLES,strict_feature_enabled,managed_material_tables
    from types import SimpleNamespace
    if strict_feature_enabled(SimpleNamespace(db=db,instance_id=control.instance)):return True
    tables=managed_material_tables(db)
    for table in PERSISTENT_TL_MATERIAL_TABLES:
        if table in tables and db.execute('SELECT 1 FROM '+table+' WHERE instance_id=? LIMIT 1',(control.instance,)).fetchone():return True
    if 'tl_barrier' in tables and db.execute("SELECT 1 FROM tl_barrier WHERE instance_id=? AND (state='active' OR kind='erase') LIMIT 1",(control.instance,)).fetchone():return True
    if 'tl_erasure_target' in tables and db.execute('SELECT 1 FROM tl_erasure_target WHERE instance_id=? LIMIT 1',(control.instance,)).fetchone():return True
    return control.db.execute("SELECT 1 FROM control_commands WHERE instance_ref=? AND source='maintenance-controller' AND ((kind='maintenance.protective_change_pending' AND state<>'rejected') OR (kind='maintenance.exclusion_head' AND state='succeeded')) LIMIT 1",(control.instance,)).fetchone() is not None


def effective_capabilities(control,deployment):
    from digital_life.application.lifecycle.control_plane import Releases
    path=Releases(control).verify(deployment);row=control.db.execute('SELECT * FROM deployments WHERE id=?',(deployment,)).fetchone()
    description=declaration(strict_json((path/'digital_life/resources/release.json').read_text()),allow_legacy=True)
    if row['schema_max']!=4:raise Forbidden('release has no verified TL capability')
    proof=verified_baseline(control,row,strict_json((path/'manifest.json').read_text()),description)
    return {'capabilities':['TL-LOOP-0.1'],'basis':'explicit_array' if 'capabilities' in description else 'verified_im15_nested_projection','original_array_present':'capabilities' in description,'build_hash':proof['build_hash']}
