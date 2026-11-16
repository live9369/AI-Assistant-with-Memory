"""Strict packet/manifest differential. No inferred IDs or ignored business data.

ID mappings identify exact JSON pointers in a bundle containing packet/manifest.
Timestamps, scope, conditions, versions and caps are never ignored. A generated
manifest digest is recomputed only after original digests were fully validated.
This tool does not assert independent fixture equivalence without supplied proof.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
from digital_life.application.learning.runtime import validate_manifest
from digital_life.domain import tool_learning_contract as c

_UUID = re.compile(r'[0-9a-f]{32}\Z')


def _parts(pointer):
    if not isinstance(pointer,str) or not pointer.startswith('/'):
        raise ValueError('exact non-root JSON pointer required')
    return [v.replace('~1','/').replace('~0','~') for v in pointer[1:].split('/')]


def _get(value,pointer):
    for key in _parts(pointer):
        value=value[int(key)] if isinstance(value,list) else value[key]
    return value


def _set(value,pointer,new):
    parts=_parts(pointer)
    for key in parts[:-1]:value=value[int(key)] if isinstance(value,list) else value[key]
    key=int(parts[-1]) if isinstance(value,list) else parts[-1]
    value[key]=new


def _esc(key):return str(key).replace('~','~0').replace('/','~1')


def _diff(left,right,path=''):
    if type(left) is not type(right):return [{'path':path,'left':left,'right':right,'reason':'type'}]
    if isinstance(left,dict):
        result=[]
        for key in sorted(left.keys()|right.keys()):
            pointer=path+'/'+_esc(key)
            if key not in left or key not in right:
                result.append({'path':pointer,'reason':'missing_key','left_present':key in left,'right_present':key in right})
            else:result.extend(_diff(left[key],right[key],pointer))
        return result
    if isinstance(left,list):
        result=[]
        if len(left)!=len(right):result.append({'path':path,'reason':'array_length','left':len(left),'right':len(right)})
        for index,(a,b) in enumerate(zip(left,right)):result.extend(_diff(a,b,path+'/'+str(index)))
        return result
    return [] if left==right else [{'path':path,'left':left,'right':right,'reason':'value'}]


def compare(left,right,id_mappings=()):
    """Mappings: [{left: uuid32, right: uuid32, paths: [exact pointer,...]}].

    No normalization is inferred from field names. All used mapping paths and
    original values appear in the report. Missing/duplicate paths fail closed.
    """
    for bundle in (left,right):
        if set(bundle)!={'packet','manifest'}:raise ValueError('packet and manifest required, no partial projections')
        validate_manifest(bundle['packet'],bundle['manifest'])
    normalized=deepcopy(left);target=deepcopy(right)
    seen_left={};seen_right={};seen_paths=set();applied=[]
    for mapping in id_mappings:
        if set(mapping)!={'left','right','paths'}:raise ValueError('exact ID mapping fields required')
        a,b,paths=mapping['left'],mapping['right'],mapping['paths']
        if not all(isinstance(v,str) and _UUID.fullmatch(v) for v in (a,b)):
            raise ValueError('only explicit UUID32 technical identities can be mapped')
        if not isinstance(paths,list) or not paths:raise ValueError('mapping requires exact path witnesses')
        if a in seen_left and seen_left[a]!=b or b in seen_right and seen_right[b]!=a:
            raise ValueError('ID mapping must be bijective')
        seen_left[a]=b;seen_right[b]=a
        for path in paths:
            if path in seen_paths:raise ValueError('duplicate mapping path')
            seen_paths.add(path)
            if _get(left,path)!=a or _get(right,path)!=b:raise ValueError('ID path does not witness supplied mapping')
            _set(normalized,path,b);applied.append({'path':path,'left':a,'right':b})
    # These fields are not excluded: their original binding was validated above,
    # and replacement is derived mechanically from the complete normalized input.
    for bundle in (normalized,target):
        manifest=bundle['manifest'];packet=bundle['packet']
        manifest['packet_digest']=c.fingerprint(packet)
        for field in manifest['fields']:
            value=c.resolve_locator({'kind':'json_pointer','pointer':field['path']},packet)
            field['digest']['hex']=c.fingerprint(value)
    differences=_diff(normalized,target)
    return {'passed':not differences,'scope':'complete packet and manifest; no ignored time/scope/condition/cap fields',
            'original_manifests_valid':True,'applied_id_paths':applied,
            'differences':differences,'difference_count':len(differences),
            'derived_digest_policy':'originals validated; only manifest packet_digest and field digest recomputed after explicit ID mapping'}


def load_bundle(folder):
    folder=Path(folder)
    return {k:json.loads((folder/(k+'.json')).read_text()) for k in ('packet','manifest')}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--left',required=True);parser.add_argument('--right',required=True)
    parser.add_argument('--id-map');parser.add_argument('--output',required=True);args=parser.parse_args()
    mappings=[] if args.id_map is None else json.loads(Path(args.id_map).read_text())
    try:result=compare(load_bundle(args.left),load_bundle(args.right),mappings)
    except Exception as exc:result={'passed':False,'error_type':type(exc).__name__,'error':str(exc)}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
