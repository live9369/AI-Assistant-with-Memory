"""Pure TL-LOOP-0.1 structural types. No authority, truth or storage assertion."""
import json
import math
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from digital_life.domain.contracts import ContractError, dumps, sha

REASONS = frozenset('none source_reported_null not_measured no_prior_prediction missing_unit ambiguous_entity incomplete_source unavailable_source no_baseline out_of_scope not_requested access_restricted conflicting_support invalid_locator invalid_type budget_limit deadline unsupported other'.split())
STATUSES = frozenset('known unknown not_collected not_applicable withheld conflicted invalid'.split())
MODULES = frozenset('M01 M03 M04 M12 M13 M14 M17 coordinator evaluator'.split())
PURPOSES = frozenset('learn accept represent recall_experience recall_episode verify_source evaluate history_audit propagate erase recover'.split())
SOURCE_KINDS = frozenset('tool_result user_statement system_event model_output'.split())
CHECK_STATES = frozenset('readable temporarily_unavailable revoked deleted unknown not_checked matched unresolved mismatch not_assessed supports_scoped_claim insufficient conflicting not_applicable ready_for_handoff needs_material blocked pass fail incomplete'.split())

_SURROGATE = re.compile('[\ud800-\udfff]')
_STRUCTURAL_SCOPES = ContextVar('tl_structural_scope_proofs', default=None)


@contextmanager
def structural_validation_boundary():
    """Bounded pure grammar proofs, never source/permission/version results.

    No mutable object identity is a key. The owner installs a fresh scope for
    each verification boundary; neither plaintext keys nor proofs survive exit.
    A copied asynchronous context cannot reactivate a closed proof collection.
    """
    state = {'active': True, 'cache': {}, 'bytes': 0}
    token = _STRUCTURAL_SCOPES.set(state)
    try:
        yield
    finally:
        state['active'] = False
        state['cache'].clear()
        state['bytes'] = 0
        _STRUCTURAL_SCOPES.reset(token)


def fail(message):
    raise ContractError(message)


def string(value, nonempty=True):
    if type(value) is not str or (nonempty and not value.strip()):
        fail('string required')
    if not value.isascii() and _SURROGATE.search(value) is not None:
        fail('invalid Unicode surrogate')
    return value


def integer(value, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        fail('integer outside contract range')
    return value


def number(value):
    if type(value) is int:
        return value
    if type(value) is not float or not math.isfinite(value):
        fail('finite number required')
    return value


def boolean(value):
    if type(value) is not bool:
        fail('boolean required')
    return value


def enum(value, choices):
    string(value)
    if value not in choices:
        fail('unsupported enum value')
    return value


def obj(value, required, optional=()):
    if type(value) is not dict:
        fail('object required')
    for key in value:
        string(key, nonempty=False)
    needed = set(required)
    if not needed <= set(value) or set(value) - needed - set(optional):
        fail('unknown or missing object fields')
    return value


def array(value, item_check):
    if type(value) is not list:
        fail('array required')
    for item in value:
        item_check(item)
    return value


def json_value(value, _active=None):
    active = set() if _active is None else _active
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        return string(value, nonempty=False)
    if type(value) in (int, float):
        return number(value)
    if type(value) not in (dict, list):
        fail('JSON value required')
    if id(value) in active:
        fail('cyclic JSON value')
    active.add(id(value))
    try:
        if type(value) is dict:
            for key, item in value.items():
                string(key, nonempty=False)
                json_value(item, active)
        else:
            for item in value:
                json_value(item, active)
    finally:
        active.remove(id(value))
    return value


def identifier(value):
    string(value)
    if not re.fullmatch('[0-9a-f]{32}', value):
        fail('new ID must be 32 lowercase hexadecimal characters')
    return value


def utc(value):
    string(value)
    if not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z', value):
        fail('UTC milliseconds timestamp required')
    try:
        datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        fail('invalid UTC date')
    return value


def slot(value, item_check, allow_null=False):
    obj(value, ('status', 'value', 'reason_code', 'reason', 'basis_refs'))
    enum(value['status'], STATUSES)
    enum(value['reason_code'], REASONS)
    string(value['reason'], nonempty=value['status'] != 'known' or value['reason_code'] == 'other')
    array(value['basis_refs'], validate_ref)
    if value['status'] != 'known':
        if value['value'] is not None:
            fail('non-known Slot value must be null')
    else:
        if value['reason_code'] not in ('none', 'source_reported_null'):
            fail('known Slot reason must match contract')
        if value['value'] is None:
            if not allow_null or value['reason_code'] != 'source_reported_null':
                fail('known null needs explicitly nullable source-reported field')
        else:
            item_check(value['value'])
    return value


def validate_ref(value):
    obj(value, ('instance_id', 'id', 'kind', 'revision'))
    string(value['instance_id']); string(value['id']); string(value['kind'])
    if len(value['id']) > 240:
        fail('legacy Ref.id exceeds 240 characters')
    slot(value['revision'], integer)
    return value


def validate_digest(value):
    obj(value, ('algorithm', 'hex'))
    enum(value['algorithm'], ('sha256',))
    string(value['hex'])
    if not re.fullmatch('[0-9a-f]{64}', value['hex']):
        fail('lowercase SHA256 required')
    return value


def validate_version(value):
    obj(value, ('object', 'revision', 'epoch'))
    validate_ref(value['object']); integer(value['revision']); integer(value['epoch'])
    if value['object']['revision']['status']=='known' and value['object']['revision']['value']!=value['revision']:
        fail('VersionToken revision disagrees with object reference')
    return value


def validate_dependency(value):
    obj(value, ('target', 'relation', 'expected', 'consumer_purpose'))
    validate_ref(value['target']); enum(value['relation'], ('support', 'derive', 'read', 'delete', 'representation', 'group'))
    validate_version(value['expected']); enum(value['consumer_purpose'], PURPOSES)
    if any(value['target'][key]!=value['expected']['object'][key] for key in ('instance_id','id','kind')):
        fail('dependency target differs from expected version object')
    if value['target']['revision']['status']=='known' and value['target']['revision']['value']!=value['expected']['revision']:
        fail('dependency target revision differs from expected version')
    return value


def validate_principal(value):
    obj(value, ('actor', 'module', 'recipient', 'purpose', 'authorization'))
    for field in ('actor', 'recipient', 'authorization'):
        validate_ref(value[field])
    enum(value['module'], MODULES); enum(value['purpose'], PURPOSES)
    return value


def validate_method(value):
    obj(value, ('name', 'version', 'request_ref', 'model_config_ref'))
    string(value['name']); string(value['version'])
    slot(value['request_ref'], validate_ref); slot(value['model_config_ref'], validate_ref)
    return value


def validate_control(value):
    obj(value, ('policy', 'configuration', 'source_epochs', 'runtime_epoch', 'input_epoch', 'cancelled'))
    validate_version(value['policy']); validate_version(value['configuration'])
    array(value['source_epochs'], validate_version)
    integer(value['runtime_epoch']); integer(value['input_epoch']); boolean(value['cancelled'])
    return value


def validate_budget(value):
    fields = ('max_attempts', 'max_input_tokens', 'max_output_tokens', 'max_tool_calls', 'max_scan', 'max_items', 'max_bytes')
    obj(value, ('account_ref', 'deadline', *fields))
    validate_ref(value['account_ref']); utc(value['deadline'])
    for field in fields:
        integer(value[field], minimum=1 if field == 'max_attempts' else 0)
    return value


def validate_coverage(value):
    obj(value, ('state', 'domain', 'scanned', 'limit', 'truncated', 'missing'))
    enum(value['state'], ('complete', 'partial', 'unknown')); slot(value['domain'], string)
    integer(value['scanned']); integer(value['limit']); boolean(value['truncated'])
    array(value['missing'], lambda v: slot(v, string))
    return value


def validate_check(value, states=None):
    obj(value, ('state', 'checker', 'method', 'at', 'targets', 'reason', 'basis_refs'))
    enum(value['state'], CHECK_STATES if states is None else states)
    validate_principal(value['checker']); validate_method(value['method']); utc(value['at'])
    array(value['targets'], validate_version); enum(value['reason'], REASONS); array(value['basis_refs'], validate_ref)
    return value


def validate_locator(value):
    if type(value) is not dict or 'kind' not in value:
        fail('locator object with kind required')
    kind = value['kind']
    if kind == 'json_pointer':
        obj(value, ('kind', 'pointer')); string(value['pointer'], nonempty=False)
        pointer = value['pointer']
        if (pointer and not pointer.startswith('/')) or re.search(r'~(?![01])', pointer):
            fail('invalid RFC6901 pointer')
    elif kind in ('text_range', 'byte_range'):
        obj(value, ('kind', 'start', 'end', 'quote') if kind == 'text_range' else ('kind', 'start', 'end'))
        integer(value['start']); integer(value['end'], minimum=value['start'])
        if kind == 'text_range':
            slot(value['quote'], lambda v:string(v,nonempty=False))
    elif kind == 'whole_artifact':
        obj(value, ('kind', 'justification')); string(value['justification'])
    else:
        fail('unknown locator kind')
    return value


def resolve_locator(locator, view):
    validate_locator(locator)
    kind = locator['kind']
    if kind == 'byte_range':
        if type(view) is not bytes or locator['end'] > len(view):
            fail('byte range does not match supplied byte view')
        return view[locator['start']:locator['end']]
    if kind == 'text_range':
        string(view, nonempty=False)
        if locator['end'] > len(view):
            fail('text range exceeds supplied Unicode view')
        fragment = view[locator['start']:locator['end']]
        if locator['quote']['status'] == 'known' and locator['quote']['value'] != fragment:
            fail('text quote mismatch')
        return fragment
    if kind == 'whole_artifact':
        if type(view) is not bytes:
            json_value(view)
        return view
    json_value(view)
    current = view
    pointer = locator['pointer']
    if not pointer:
        return current
    for encoded in pointer[1:].split('/'):
        key = encoded.replace('~1', '/').replace('~0', '~')
        if type(current) is dict:
            if key not in current:fail('JSON pointer member missing')
            current = current[key]
        elif type(current) is list:
            if not re.fullmatch('0|[1-9][0-9]*', key):fail('JSON pointer array index invalid')
            index = int(key)
            if index >= len(current):fail('JSON pointer array index outside view')
            current = current[index]
        else:
            fail('JSON pointer cannot traverse scalar or implicitly decode string')
    return current


def validate_evidence(value):
    fields = ('source','source_kind','original_result','receipt','artifact','source_revision','digest','media_type','encoding','view','view_digest','locator','origin_method','observed_at','reported_at','coverage','derivation_refs','access_dependencies')
    obj(value, fields)
    validate_ref(value['source']); enum(value['source_kind'], SOURCE_KINDS)
    slot(value['original_result'], validate_ref); slot(value['receipt'], validate_ref)
    required_status = 'known' if value['source_kind'] == 'tool_result' else 'not_applicable'
    if value['original_result']['status'] != required_status or value['receipt']['status'] != required_status:
        fail('source kind does not match original tool result and receipt slots')
    validate_ref(value['artifact']); slot(value['source_revision'], integer); validate_digest(value['digest'])
    string(value['media_type']); slot(value['encoding'], string); slot(value['view'], validate_ref); slot(value['view_digest'], validate_digest)
    validate_locator(value['locator']); validate_method(value['origin_method'])
    slot(value['observed_at'], utc); slot(value['reported_at'], utc); validate_coverage(value['coverage'])
    array(value['derivation_refs'], validate_ref); array(value['access_dependencies'], validate_dependency)
    return value


def validate_scope(value):
    obj(value, ('subject','subject_label','property','claim_target','temporal','conditions','domain','unit','granularity','coverage','exceptions','limitations'))
    slot(value['subject'], validate_ref); slot(value['subject_label'], string); string(value['property'])
    enum(value['claim_target'], ('source_report','world_claim','method_claim','causal_claim','effect_statistic'))
    temporal = value['temporal'];obj(temporal, ('kind','start','end','bounds'))
    enum(temporal['kind'], ('observation','source_validity','general_candidate'))
    slot(temporal['start'], utc);slot(temporal['end'], utc)
    enum(temporal['bounds'], ('point','closed','open','half_open','unknown'))
    if temporal['start']['status']=='known' and temporal['end']['status']=='known':
        start,end=temporal['start']['value'],temporal['end']['value']
        if start>end or temporal['bounds']=='point' and start!=end:
            fail('temporal scope boundaries disagree')
    slot(value['conditions'], json_value, allow_null=True)
    for field in ('domain','unit','granularity'):slot(value[field], string)
    validate_coverage(value['coverage']);array(value['exceptions'], validate_ref);array(value['limitations'], string)
    return value


def _scope_structure(value):
    try:
        return validate_scope(value)
    except RecursionError as error:
        raise ContractError('recursive contract value') from error


def scope_fingerprint(value):
    """Exactly the Scope proof and canonical digest, with phase-local reuse.

    Strict JSON validation precedes serialization on every lookup: tuples,
    non-string keys, nonfinite numbers and subclasses cannot alias valid JSON.
    This is exclusively structural; live eligibility is always checked by its
    original owner. Outside a boundary the original full algorithm is used.
    """
    state = _STRUCTURAL_SCOPES.get()
    if state is None or not state['active']:
        _scope_structure(value)
        return fingerprint(value)
    try:
        json_value(value)
        encoded = dumps(value).encode('utf-8')
    except ContractError:
        raise
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ContractError('invalid canonical JSON') from error
    previous = state['cache'].get(encoded)
    if previous is not None:
        return previous
    _scope_structure(value)
    result = sha(encoded)
    # Bound retained canonical-key bytes as well as entry count. Oversized
    # scopes are fully checked, but never retained as an optimization fact.
    cost = len(encoded) + 64
    if len(encoded) <= 8192:
        while state['cache'] and (len(state['cache']) >= 256 or state['bytes'] + cost > 1048576):
            old = next(iter(state['cache']))
            state['cache'].pop(old)
            state['bytes'] -= len(old) + 64
        state['cache'][encoded] = result
        state['bytes'] += cost
    return result


def validate_claim(value):
    obj(value, ('claim_id','form','subject','predicate','value','scope','evidence','derivation','limitations'))
    identifier(value['claim_id']);enum(value['form'], ('source_report','explicit_transformation','interpretation'))
    slot(value['subject'], validate_ref);string(value['predicate']);slot(value['value'], json_value, allow_null=True)
    validate_scope(value['scope']);array(value['evidence'], validate_evidence)
    if not value['evidence']:fail('substantive claim needs evidence')
    validate_method(value['derivation']);array(value['limitations'], string)
    return value


VALIDATORS = {'JSON':json_value,'ID':identifier,'UTC':utc,'Ref':validate_ref,'Digest':validate_digest,'VersionToken':validate_version,'Dependency':validate_dependency,'Principal':validate_principal,'Method':validate_method,'Control':validate_control,'Budget':validate_budget,'Coverage':validate_coverage,'Check':validate_check,'Locator':validate_locator,'EvidenceRef':validate_evidence,'Scope':validate_scope,'Claim':validate_claim,'Reason':lambda v:enum(v,REASONS)}


def validate(name, value):
    if type(name) is not str or name not in VALIDATORS:fail('unknown structural type')
    try:
        return VALIDATORS[name](value)
    except RecursionError:
        fail('recursive contract value')


def loads(raw, type_name=None):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:fail('duplicate JSON object member')
            result[key] = value
        return result
    try:
        if type(raw) is bytes:raw=raw.decode('utf-8', errors='strict')
        if type(raw) is not str:fail('JSON text or UTF-8 bytes required')
        string(raw, nonempty=False)
        value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:fail('nonfinite JSON constant'))
        json_value(value)
        return validate(type_name,value) if type_name is not None else value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ContractError('invalid strict JSON') from error


def fingerprint(value):
    try:
        json_value(value)
        return sha(dumps(value).encode('utf-8'))
    except (ValueError,UnicodeError,RecursionError) as error:raise ContractError('invalid canonical JSON') from error
