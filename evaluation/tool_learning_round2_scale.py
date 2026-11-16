"""PF07 supplemental synthetic scale/failure replay: fixed world inputs, real monotonic/accounting.

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
import stat
import sys
import time
import uuid



def budget_snapshot(store,activity):
    """Fresh synthetic DB only; preserve actual known/unknown charges on failure."""
    row=store.row('activities',activity)
    return {'activity':dict(row),'budget':json.loads(row['budget_json']),
            'requests':[dict(r)for r in store.db.execute('SELECT * FROM thought_requests WHERE instance_id=? AND activity_id=? ORDER BY rowid',(store.instance_id,activity))],
            'attempts':[dict(r)for r in store.db.execute('SELECT a.* FROM thought_attempts a JOIN thought_requests r ON r.instance_id=a.instance_id AND r.id=a.request_id WHERE r.instance_id=? AND r.activity_id=? ORDER BY a.rowid',(store.instance_id,activity))]}


def _failure_artifact(store,key,folder,name):
    """Copy actual immutable bytes after the meter closes; never create a blob."""
    row=store.db.execute('SELECT * FROM artifacts WHERE instance_id=? AND id=?',(store.instance_id,key)).fetchone()
    if row is None:raise ValueError('artifact metadata missing')
    location=row['storage_ref']
    if type(location)is not str or len(location)!=64 or any(c not in '0123456789abcdef'for c in location):raise ValueError('unsafe artifact location')
    directory=os.open(store.root/'blobs',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fd=os.open(location,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
        with os.fdopen(fd,'rb')as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('not regular artifact bytes')
            raw=stream.read()
    finally:os.close(directory)
    digest=hashlib.sha256(raw).hexdigest()
    if len(raw)!=row['size']or digest!=row['hash']or digest!=location:raise ValueError('artifact bytes do not match actual metadata')
    value=json.loads(raw);target=folder/(name+'.json');target.write_bytes(raw)
    return {'status':'observed','artifact_id':key,'file':str(target),'bytes':len(raw),'sha256':digest},value


def failure_registration_progress(store,activity,folder,read_opportunities=None):
    """Read-only post-failure facts; rows are not a successful assembly proof."""
    from digital_life.infrastructure.persistence.tool_learning_meter import _ACTIVE
    if _ACTIVE.get()is not None:return {'status':'unknown','reason':'physical meter is still active; diagnostic not attempted'}
    from digital_life.domain import tool_learning_contract as c
    from digital_life.application.learning.runtime import validate_manifest
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    result={'status':'observed','meaning':'committed rows and actual prepared materials only; not eligibility or complete assembly','requests':[]}
    rows=store.db.execute('SELECT rowid AS diagnostic_rowid,* FROM thought_requests WHERE instance_id=? AND activity_id=? ORDER BY rowid',(store.instance_id,activity)).fetchall()
    for ordinal,row in enumerate(rows):
        target=folder/('request-'+str(ordinal));target.mkdir()
        request=dict(row);item={'request':request,'packet':{'status':'unknown'},'manifest':{'status':'unknown','reason':'no persisted proof or actual owner material observed'},'assembly_complete':False,'dependencies':[],'inputs':[],'fields':None,'expected_field_count':None,'remaining_field_count':None}
        result['requests'].append(item);packet=None;manifest=None;errors=[]
        try:
            item['packet'],packet=_failure_artifact(store,row['request_artifact_id'],target,'packet')
            if c.fingerprint(packet)!=row['request_hash']:raise ValueError('packet differs from actual request hash')
            item['packet']['request_hash_matches']=True
        except BaseException as exc:
            packet=None;item['packet']={'status':'unknown','reason':type(exc).__name__+': '+str(exc)}
        event=store.db.execute("SELECT rowid AS diagnostic_rowid,* FROM runtime_events WHERE instance_id=? AND source='tl.input.assembly' AND source_event_id=? ORDER BY rowid",(store.instance_id,row['id'])).fetchone()
        candidates=[]
        if event is not None:
            try:
                observed,proof=_failure_artifact(store,event['payload_artifact_id'],target,'assembly-proof')
                candidates.append(('persisted_assembly_event',proof['manifest'],{'event':dict(event),'artifact':observed}))
            except BaseException as exc:errors.append({'origin':'persisted_assembly_event','reason':type(exc).__name__+': '+str(exc)})
        actual=(read_opportunities or{}).get('assembly:'+row['id'])
        if isinstance(actual,dict)and isinstance(actual.get('manifest'),dict):candidates.append(('actual_owner_read_opportunity',actual['manifest'],{}))
        for origin,value,details in candidates:
            try:
                if packet is None:raise ValueError('actual packet unavailable for manifest validation')
                if c.fingerprint(value)!=row['input_manifest_hash']:raise ValueError('manifest differs from actual request manifest hash')
                validate_manifest(packet,value);manifest=value
                manifest_path=target/'manifest.json';manifest_path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
                item['manifest']={'status':'observed','origin':origin,'file':str(manifest_path),'request_manifest_hash_matches':True,'validated_with_actual_packet':True,**details}
                item['assembly_complete']=origin=='persisted_assembly_event'
                break
            except BaseException as exc:errors.append({'origin':origin,'reason':type(exc).__name__+': '+str(exc)})
        if errors:item['manifest_capture_errors']=errors
        for index,dep in enumerate(store.db.execute('SELECT rowid AS diagnostic_rowid,* FROM tl_dependency WHERE instance_id=? AND consumer_ref_id=? ORDER BY rowid',(store.instance_id,row['id']))):
            value={'row':dict(dep),'metadata_capture':{'status':'unknown'},'metadata':None}
            try:value['metadata_capture'],value['metadata']=_failure_artifact(store,dep['metadata_artifact_id'],target,'dependency-metadata-'+str(index))
            except BaseException as exc:value['metadata_capture']['reason']=type(exc).__name__+': '+str(exc)
            item['dependencies'].append(value)
        item['inputs']=[dict(v)for v in store.db.execute('SELECT rowid AS diagnostic_rowid,* FROM tl_input_dependency WHERE instance_id=? AND request_ref_id=? ORDER BY rowid',(store.instance_id,row['id']))]
        grouped={}
        for value in item['dependencies']:
            raw=value['row'];grouped.setdefault(raw['field_path'],{'dependency_rowids':[],'input_rowids':[],'retention_states':[]})['dependency_rowids'].append(raw['diagnostic_rowid'])
        for raw in item['inputs']:
            group=grouped.setdefault(raw['field_path'],{'dependency_rowids':[],'input_rowids':[],'retention_states':[]});group['input_rowids'].append(raw['diagnostic_rowid']);group['retention_states'].append(raw['retention_state'])
        item['by_raw_field_path']={path:dict(group,dependency_count=len(group['dependency_rowids']),input_count=len(group['input_rowids']))for path,group in grouped.items()}
        if manifest is not None:
            fields=[]
            for index,field in enumerate(manifest['fields']):
                expectations=[]
                for dep_index,expected in enumerate(field['dependencies']):
                    matching=[]
                    for value in item['dependencies']:
                        raw=value['row'];meta=value['metadata']
                        if (raw['field_path']==field['path']and raw['source_ref_id']==expected['target']['id']and raw['relation']==expected['relation']and raw['purpose']==expected['consumer_purpose']and raw['expected_epoch']==expected['expected']['epoch']and isinstance(meta,dict)and meta.get('dependency')==expected and meta.get('scope')==field['dependency_scopes'][dep_index]and meta.get('field_path')==field['path']):matching.append(raw['diagnostic_rowid'])
                    token=expected['expected'];source=token['object'];inputs=[]
                    revisions={value['row']['source_revision_id']for value in item['dependencies']if value['row']['diagnostic_rowid']in matching}
                    if expected['relation']!='delete':
                        for raw in item['inputs']:
                            if raw['field_path']==field['path']and raw['source_ref_id']==source['id']and raw['source_epoch']==token['epoch']and raw['source_revision_ref_id']in revisions and raw['purpose']==expected['consumer_purpose']and raw['body_digest']==field['digest']['hex']and raw['retention_state']=='allowed':inputs.append(raw['diagnostic_rowid'])
                    expectations.append({'dependency_index':dep_index,'expected':expected,'scope':field['dependency_scopes'][dep_index],'matching_dependency_rowids':matching,'input_required':expected['relation']!='delete','matching_input_rowids':inputs,'rows_observed':bool(matching)and(expected['relation']=='delete'or bool(inputs))})
                complete=all(v['rows_observed']for v in expectations)
                some=any(v['matching_dependency_rowids']or v['matching_input_rowids']for v in expectations)
                fields.append({'manifest_index':index,'field_path':field['path'],'digest':field['digest'],'status':'no_registration_required'if not expectations else 'all_expected_rows_observed'if complete else 'partial_rows_observed'if some else 'not_started','expected_dependency_count':len(expectations),'expected_input_count':sum(v['input_required']for v in expectations),'expectations':expectations})
            item['fields']=fields;item['expected_field_count']=len(fields)
            item['remaining_field_count']=sum(v['status']in ('partial_rows_observed','not_started')for v in fields)
            item['fields_with_registration_count']=sum(v['expected_dependency_count']>0 for v in fields)
            item['expected_dependency_count']=sum(v['expected_dependency_count']for v in fields);item['expected_input_count']=sum(v['expected_input_count']for v in fields)
            item['missing_dependency_expectations']=sum(not v['matching_dependency_rowids']for field in fields for v in field['expectations'])
            item['missing_input_expectations']=sum(v['input_required']and not v['matching_input_rowids']for field in fields for v in field['expectations'])
        item['actual_dependency_rows']=len(item['dependencies']);item['actual_input_rows']=len(item['inputs'])
    return result


def controller_reader(fixture):
    from digital_life.application.learning.controller_read import ControllerMaterialReader
    # This token belongs only to the just-created TemporaryDirectory fixture.
    token_path=fixture.s.root/'controller.token'
    if not token_path.exists():token_path.write_text('synthetic-pf07-controller-token\n')
    token=token_path.read_text().strip()
    return ControllerMaterialReader(fixture.s,'Bearer '+token)


def seed_shared_source(fixture):
    """Use real synthetic inbound, Memory and PeopleRelations owner APIs.

    Cancel an unprocessed first chat turn through controller API; retain its
    authenticated input as old memory. Two actual observations support a local
    'self-reported liwei' role, never identity verification or a family claim.
    """
    from digital_life.application.runtime.engine import Engine
    from digital_life.application.behavior.people_relations import PeopleRelations
    from digital_life.domain.contracts import identifier
    s=fixture.s;reader=controller_reader(fixture);thread='pf07-shared-source'
    first=reader.send(thread,{'text':'你好，我是liwei。','idempotency_key':'shared-intro','expected_last_activity_id':None})['activity_id']
    first_signal=s.row('activities',first)['trigger_event_id']
    first_evidence=s.db.execute("SELECT id FROM evidence_items WHERE instance_id=? AND origin_object_id=? AND method='authenticated-controller-input' ORDER BY rowid LIMIT 1",(s.instance_id,first_signal)).fetchone()[0]
    reader.cancel(first,{'expected_revision':s.row('activities',first)['revision']})
    second=reader.send(thread,{'text':'你好，我是liwei。请回顾我刚才的介绍。','idempotency_key':'shared-current','expected_last_activity_id':first})['activity_id']
    second_signal=s.row('activities',second)['trigger_event_id']
    second_evidence=s.db.execute("SELECT id FROM evidence_items WHERE instance_id=? AND origin_object_id=? AND method='authenticated-controller-input' ORDER BY rowid LIMIT 1",(s.instance_id,second_signal)).fetchone()[0]
    owner=PeopleRelations(s);controller=s.config()['controller']
    person=owner.register('liwei',[first_evidence],'pf07-person',controller)
    relation=owner.relate(person['actor'],'自称liwei',[first_evidence,second_evidence],'pf07-reported-role',controller)
    extras=[]
    for index in range(6):
        key=identifier();text='liwei synthetic prior memory '+str(index)
        fixture.control.accept_inbound('pf07-growth',key,{'text':text},controller)
        extras.append(Engine(s,fixture.identity).submit(text,key,'pf07-growth'))
    memories=[dict(r)for r in s.db.execute('SELECT r.id,r.memory_id,r.content,l.evidence_id FROM memory_revisions r JOIN memory_source_links l ON l.instance_id=r.instance_id AND l.memory_revision_id=r.id WHERE r.instance_id=? AND l.evidence_id=?',(s.instance_id,first_evidence))]
    fixture.activity=second
    return {'thread':thread,'first_activity':first,'first_signal':first_signal,'first_evidence':first_evidence,'second_activity':second,'second_signal':second_signal,'second_evidence':second_evidence,'first_input_memories':memories,'person':person,'relation':relation,'extra_original_input_activities':extras,'meaning':'two authenticated self-reports; person/role remains locally unverified; no hand-written provenance edges'}


def material_proof(fixture,packet,manifest):
    from digital_life.application.learning.runtime import validate_manifest
    validate_manifest(packet,manifest)
    features=packet['input']['features'];expected={'identity','personality','values','cognition_candidates','goals_and_motivation','habits','relationships','internal_state','health_and_maintenance','commitments','learning_feedback'}
    if set(features)!=expected:raise AssertionError('full feature groups changed')
    fields=[]
    for field in manifest['fields']:
        fields.append({'path':field['path'],'digest':field['digest'],'usage':field['usage'],'source_tokens':[d['expected']for d in field['dependencies']],'relations':[d['relation']for d in field['dependencies']],'dependency_scopes':field['dependency_scopes']})
    return {'all_feature_groups_present':True,'features':{k:{'record_count':len(v['records']),'source_bindings':[{'source':r['source'],'observed_version':r['observed_version']}for r in v['records']],'selection':v['selection'],'coverage':v['coverage'],'missing':v['missing']}for k,v in features.items()},'fields':fields,'native_input_dependencies':fixture.s.db.execute('SELECT count(*) FROM tl_input_dependency WHERE instance_id=? AND request_ref_id=?',(fixture.s.instance_id,packet['request_id'])).fetchone()[0]}


def invocation_proofs(store):
    out=[]
    for row in store.db.execute("SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND source='strict.provider.invocation' ORDER BY rowid",(store.instance_id,)):
        invocation=store.read_artifact(row['payload_artifact_id']);wire=invocation['wire'];messages=wire.get('messages',[])
        body=json.loads(messages[1]['content'])if len(messages)==2 else None
        forbidden={'session','session_id','conversation_id','previous_response_id','resume','thread_id'}&set(wire)
        out.append({'event':row['id'],'fresh':invocation.get('fresh'),'two_message_wire':len(messages)==2 and [m.get('role')for m in messages]==['system','user'],'forbidden_top_level_session_keys':sorted(forbidden),'request_id':body.get('request_id')if isinstance(body,dict)else None,'context_mode':body.get('input',{}).get('context_mode')if isinstance(body,dict)else None,'invocation':invocation})
    return out



def capture_result_artifacts(store,request_id,folder):
    """Observe persisted bytes, never reconstruct an output from fixture constants."""
    records=[]
    for index,row in enumerate(store.db.execute('SELECT * FROM thought_results WHERE instance_id=? AND request_id=? ORDER BY rowid',(store.instance_id,request_id))):
        record={'result_row':dict(row),'artifacts':{}}
        for column in ('response_artifact_id','parsed_artifact_id'):
            key=row[column]
            if key is None:
                record['artifacts'][column]={'status':'unknown','reason':'artifact was not recorded'};continue
            try:
                artifact=store.row('artifacts',key);location=artifact['storage_ref']
                if type(location)is not str or len(location)!=64 or any(c not in '0123456789abcdef'for c in location):raise ValueError('unsafe synthetic artifact location')
                directory=os.open(store.root/'blobs',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:
                    fd=os.open(location,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
                    with os.fdopen(fd,'rb')as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('not regular artifact bytes')
                        raw=stream.read()
                finally:os.close(directory)
                digest=hashlib.sha256(raw).hexdigest()
                if len(raw)!=artifact['size']or digest!=artifact['hash']or digest!=location:raise ValueError('persisted artifact integrity mismatch')
                target=folder/(column+'-'+str(index)+'.json');target.write_bytes(raw)
                record['artifacts'][column]={'status':'observed','artifact_id':key,'storage_hash':artifact['hash'],'saved_sha256':digest,'bytes':len(raw),'file':str(target)}
            except BaseException as exc:record['artifacts'][column]={'status':'unknown','artifact_id':key,'reason':type(exc).__name__+': '+str(exc)}
        records.append(record)
    return {'results':records,'all_expected_artifacts_observed':bool(records)and all(a['status']=='observed'for r in records for a in r['artifacts'].values())}


def memory_catalog(store):
    values=[]
    for row in store.db.execute('SELECT r.id,r.memory_id,r.revision_no,r.content,r.encoding_method,m.state FROM memory_revisions r JOIN memory_items m ON m.instance_id=r.instance_id AND m.id=r.memory_id WHERE r.instance_id=? ORDER BY r.rowid',(store.instance_id,)):
        value=dict(row);value['source_links']=[dict(r)for r in store.db.execute('SELECT l.role,l.evidence_id,e.origin_object_id,e.artifact_id,e.method FROM memory_source_links l JOIN evidence_items e ON e.instance_id=l.instance_id AND e.id=l.evidence_id WHERE l.instance_id=? AND l.memory_revision_id=? ORDER BY l.rowid',(store.instance_id,row['id']))];values.append(value)
    return values


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--history',type=int,default=17);parser.add_argument('--continuous',type=int,default=1);parser.add_argument('--setup-only',action='store_true');parser.add_argument('--shared-source',action='store_true')
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
    result={'scope':'fixed synthetic environmental inputs; real monotonic and original accounting','source':str(source),'history':args.history,'continuous':args.continuous,'setup_only':args.setup_only,'shared_source':args.shared_source,'real_models_called':False,'formal_instance_accessed':False,'clock':'2031-01-02T03:04:05.678Z','runs':[]}
    result['source_files_before']=source_hashes();result['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    from digital_life.infrastructure.llm import fresh_learning
    original_supervised=fresh_learning.supervised;raw_provider_observations=[]
    def observed_transport(*a,**k):
        record={'index':len(raw_provider_observations),'status':'entered','body_status':'unknown'};raw_provider_observations.append(record)
        try:raw=original_supervised(*a,**k)
        except BaseException as exc:
            record.update(status='failed',error_type=type(exc).__name__);raise
        record['status']='returned';record['returned_type']=type(raw).__name__
        if type(raw)is str:
            body=raw.encode('utf-8');target=output/('raw-provider-response-'+str(record['index'])+'.json')
            try:
                target.write_bytes(body);record.update(body_status='observed',file=str(target),sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
            except BaseException as exc:record['capture_error']=type(exc).__name__+': '+str(exc)
        return raw
    fresh_learning.supervised=observed_transport
    result['memory_catalog_before_thought']={};result['episode_catalog_before_thought']={}
    try:
        fixture.setUp()
        import tempfile
        assert fixture.s.root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        result['fixture_uuid_calls']=sequence[0]
        result['fixture_configuration']=fixture.s.config()
        if args.shared_source and args.continuous!=1:raise ValueError('separate shared-source and continuous scenarios')
        reader=None;prior_chat=None
        if args.shared_source:result['shared_seed']=seed_shared_source(fixture)
        elif args.continuous==2:
            reader=controller_reader(fixture)
            fixture.activity=reader.send('pf07-continuous',{'text':'你好，我是liwei。','idempotency_key':'turn-0','expected_last_activity_id':None})['activity_id']
        result['counts_before']={table:fixture.s.db.execute('SELECT count(*) FROM '+table+' WHERE instance_id=?',(fixture.s.instance_id,)).fetchone()[0]for table in ('memory_items','memory_revisions','social_relationships','social_relationship_values','cognition_episodes','thought_requests')}
        for index in range(0 if args.setup_only else args.continuous):
            if index:
                fixture.activity=reader.send('pf07-continuous',{'text':'继续独立思考，你记得我刚才的介绍吗？','idempotency_key':'turn-'+str(index),'expected_last_activity_id':prior_chat})['activity_id']
            context=fixture.s.db.execute('SELECT id FROM context_snapshots WHERE activity_id=?',(fixture.activity,)).fetchone()[0]
            for item in range(args.history):Cognition(fixture.s).episode(fixture.activity,context,'synthetic prior episode '+str(item))
            result['attempted_activity']=fixture.activity;result['attempted_index']=index
            result['memory_catalog_before_thought'][str(index)]=memory_catalog(fixture.s)
            result['episode_catalog_before_thought'][str(index)]=[dict(r)for r in fixture.s.db.execute('SELECT id,activity_id,question FROM cognition_episodes WHERE instance_id=? ORDER BY rowid',(fixture.s.instance_id,))]
            started=time.monotonic();thought=Engine(fixture.s,fixture.identity,strict_runtime=fixture.strict).think(fixture.activity)
            row=fixture.s.row('thought_requests',thought['request_id']);packet=fixture.s.read_artifact(row['request_artifact_id'])
            event=fixture.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE source='tl.input.assembly' AND source_event_id=?",(row['id'],)).fetchone()
            manifest=fixture.s.read_artifact(event[0])['manifest']
            folder=output/('thought-'+str(index));folder.mkdir()
            for name,value in (('packet',packet),('manifest',manifest)):(folder/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
            budget=json.loads(fixture.s.row('activities',fixture.activity)['budget_json'])
            (folder/'material-proof.json').write_text(json.dumps(material_proof(fixture,packet,manifest),ensure_ascii=False,indent=2)+'\n')
            (folder/'activity-snapshot.json').write_text(json.dumps(budget_snapshot(fixture.s,fixture.activity),ensure_ascii=False,indent=2)+'\n')
            output_capture=capture_result_artifacts(fixture.s,row['id'],folder)
            (folder/'output-capture.json').write_text(json.dumps(output_capture,ensure_ascii=False,indent=2)+'\n')
            if not output_capture['all_expected_artifacts_observed']:raise AssertionError('actual output artifacts not fully observed')
            prior_chat=fixture.activity
            result['runs'].append({'accepted':thought['accepted'],'activity_id':fixture.activity,'instance_id':fixture.s.instance_id,'wall_seconds':time.monotonic()-started,'request_id':row['id'],'packet_folder':str(folder),'budget':budget,'uuid_calls':sequence[0]})
        result['passed']=all(r['accepted']for r in result['runs'])
        if not args.setup_only and (len(raw_provider_observations)!=args.continuous or any(r['body_status']!='observed'for r in raw_provider_observations)):raise AssertionError('actual raw provider output not fully observed')
        result['invocation_proofs']=invocation_proofs(fixture.s)
        if args.shared_source and not args.setup_only:
            seed=result['shared_seed'];matches=[]
            def original_sources(value,path=''):
                if isinstance(value,dict):
                    if isinstance(value.get('source_refs'),list):
                        for source_ref in value['source_refs']:
                            if source_ref.get('source',{}).get('id')==seed['first_signal']:matches.append(path+'/source_refs')
                    for key,child in value.items():original_sources(child,path+'/'+str(key))
                elif isinstance(value,list):
                    for index,child in enumerate(value):original_sources(child,path+'/'+str(index))
            original_sources(packet['input'])
            relationship_matches=[r['source']for r in packet['input']['features']['relationships']['records']if r['source']['kind']=='social_relationship_values'and r['report'].get('evidence_id')==seed['first_evidence']]
            result['shared_source_proof']={'original_memory_source_paths':matches,'relationship_value_sources_using_same_evidence':relationship_matches,'same_original_evidence_bound':bool(matches and relationship_matches),'meaning':'first authenticated self-report enters old-memory material and a separately evidenced unverified relationship role'}
            if not result['shared_source_proof']['same_original_evidence_bound']:raise AssertionError('shared original source did not reach both memory and relationship input')
        result['counts_after']={table:fixture.s.db.execute('SELECT count(*) FROM '+table+' WHERE instance_id=?',(fixture.s.instance_id,)).fetchone()[0]for table in result['counts_before']}
        if args.continuous==2 and not args.setup_only:
            proofs=result['invocation_proofs'];requests=[p['request_id']for p in proofs]
            result['continuous_proof']={'same_instance':True,'requests_distinct':len(requests)==2 and len(set(requests))==2,'all_independent':len(proofs)==2 and all(p['fresh']is True and p['two_message_wire'] and not p['forbidden_top_level_session_keys'] and p['context_mode']=='fresh_request'for p in proofs),'first_request':result['runs'][0]['request_id'],'second_request':result['runs'][1]['request_id'],'second_conversation_context':packet['input'].get('conversation_context')}
            prior=fixture.s.row('thought_requests',result['runs'][0]['request_id'])
            messages=(packet['input'].get('conversation_context')or{}).get('messages',[])
            result['continuous_proof']['previous_success_preserved']=prior['state']=='succeeded'
            result['continuous_proof']['predecessor_matches']=fixture.s.row('activities',result['runs'][1]['activity_id'])['predecessor_activity_id']==result['runs'][0]['activity_id']
            result['continuous_proof']['old_materials_present']=bool(messages)and any(m.get('role')=='user'and m.get('text')=='你好，我是liwei。'and m.get('memory_revision')for m in messages)
            if not all(result['continuous_proof'][k]for k in ('requests_distinct','all_independent','previous_success_preserved','predecessor_matches','old_materials_present')):raise AssertionError('fresh-call continuity proof failed')
    except BaseException as exc:
        import traceback
        result.update(passed=False,error_type=type(exc).__name__,traceback=traceback.format_exc())
        try:
            result['failed_activity_snapshot']=budget_snapshot(fixture.s,fixture.activity)
            result['invocation_proofs']=invocation_proofs(fixture.s)
            result['failure_monotonic_seconds']=time.monotonic()-started if 'started'in locals()else None
            diagnostic_started=time.monotonic()
            try:
                opportunities=getattr(getattr(getattr(fixture,'strict',None),'owners',None),'read_opportunities',None)
                result['failed_activity_snapshot']['registration_progress']=failure_registration_progress(fixture.s,fixture.activity,output/'failure-registration-progress',opportunities)
            except BaseException as diagnostic_error:result['failed_activity_snapshot']['registration_progress']={'status':'unknown','reason':type(diagnostic_error).__name__+': '+str(diagnostic_error)}
            result['failure_registration_diagnostic_seconds']=time.monotonic()-diagnostic_started
        except BaseException as snapshot_error:result['failure_snapshot_error']=type(snapshot_error).__name__+': '+str(snapshot_error)
    finally:
        fresh_learning.supervised=original_supervised
        result['raw_provider_observations']=raw_provider_observations
        fixture.doCleanups()
        sql_clock.close()
        result['source_files_after']=source_hashes();result['source_stable']=result['source_files_before']==result['source_files_after']
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':result['passed'],'runs':[(r['accepted'],r['wall_seconds'])for r in result['runs']],'error':result.get('error_type')}),flush=True)
    return 0 if result['passed']else 1


if __name__=='__main__':raise SystemExit(main())
