"""Lossless repeated-string encoding for explicit input, retaining every field."""
from collections import Counter
import json


def compact_shared_strings(payload):
    counts=Counter();key_counts=Counter();json_strings={};json_counts=Counter()
    canonical=lambda value:json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    def count(value):
        if isinstance(value,str):
            if value.startswith(('{','[')):
                try:
                    parsed=json.loads(value)
                    if isinstance(parsed,(dict,list)) and canonical(parsed)==value:
                        json_strings[value]=parsed;json_counts[value]+=1;count(parsed);return
                except (ValueError,TypeError):pass
            counts[value]+=1
        elif isinstance(value,list):
            for item in value:count(item)
        elif isinstance(value,dict):
            for key,item in value.items():key_counts[key]+=1;count(item)
    count(payload)
    encoded=lambda value:json.dumps(value,ensure_ascii=False,separators=(',',':'))
    strings=[value for value,n in counts.items() if n>1 and n*(len(encoded(value).encode())-12)-len(encoded(value).encode())-1>8]
    prefix="~"
    while any(key.startswith(prefix) for key in key_counts):prefix+="~"
    keys=[key for key,n in key_counts.items() if n>1 and n*(len(key.encode())-1)-len(key.encode())-7>16]
    alphabet=[c for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in key_counts]
    keys.sort(key=lambda key:(-key_counts[key],key))
    json_keys=[key for key,n in json_counts.items() if n>1]
    json_indices={key:i for i,key in enumerate(json_keys)}
    key_aliases={key:alphabet[i] if i<len(alphabet) else prefix+str(i) for i,key in enumerate(keys)}
    if not strings and not keys:return payload
    indices={value:i for i,value in enumerate(strings)}
    string_prefix="~"
    while any(value.startswith(string_prefix) for value in counts):string_prefix+="~"
    def replace(value):
        if isinstance(value,str) and value in json_indices:return {'$j':json_indices[value]}
        if isinstance(value,str) and value in json_strings:return {'$json':replace(json_strings[value])}
        if isinstance(value,str) and value in indices:return string_prefix+str(indices[value])
        if isinstance(value,list):return [replace(item) for item in value]
        if isinstance(value,dict):
            if '' in value or '$s' in value or '$literal' in value or '$json' in value or '$j' in value:return {'$literal':[[key,replace(item)] for key,item in value.items()]}
            return {key_aliases.get(key,key):replace(item) for key,item in value.items()}
        return value
    result={'encoding':'shared-strings-v4','string_prefix':string_prefix,'strings':strings,'jsons':[replace(json_strings[key]) for key in json_keys],'keys':{alias:key for key,alias in key_aliases.items()},'data':replace(payload)}
    if len(encoded(result).encode())+512>=len(encoded(payload).encode()):return payload
    if expand_shared_strings(result)!=payload:raise ValueError('shared-string roundtrip mismatch')
    return result


def expand_shared_strings(payload):
    if payload.get('encoding') not in ('shared-strings-v1','shared-strings-v2','shared-strings-v3','shared-strings-v4'):return payload
    strings=payload['strings'];keys=payload.get('keys',{})
    def expand(value):
        prefix=payload.get("string_prefix")
        if prefix and isinstance(value,str) and value.startswith(prefix):return strings[int(value[len(prefix):])]
        if isinstance(value,list):return [expand(item) for item in value]
        if isinstance(value,dict):
            if set(value)=={'$j'}:return json.dumps(expand(payload['jsons'][value['$j']]),ensure_ascii=False,sort_keys=True,separators=(',',':'))
            if set(value)=={'$json'}:return json.dumps(expand(value['$json']),ensure_ascii=False,sort_keys=True,separators=(',',':'))
            if set(value)=={''}:return strings[value['']]
            if set(value)=={'$s'}:return strings[value['$s']]
            if set(value)=={'$literal'}:return {key:expand(item) for key,item in value['$literal']}
            return {keys.get(key,key):expand(item) for key,item in value.items()}
        return value
    return expand(payload['data'])
