"""IM02 pure structural contract and locator checks; no runtime or models."""
import copy
import json
import unittest
from digital_life.domain.contracts import ContractError,dumps,sha
from digital_life.domain import tool_learning_types as t


def known(value):
    return {'status':'known','value':value,'reason_code':'source_reported_null' if value is None else 'none','reason':'','basis_refs':[]}


def absent(status='not_applicable'):
    return {'status':status,'value':None,'reason_code':'not_requested','reason':'explicit fixture absence','basis_refs':[]}


def ref(id='legacy-id'):
    return {'instance_id':'fixture-instance','id':id,'kind':'fixture-kind','revision':absent()}


def version():return {'object':ref(),'revision':1,'epoch':0}
def method():return {'name':'deterministic-fixture','version':'1','request_ref':absent(),'model_config_ref':absent()}
def principal():return {'actor':ref('actor'),'module':'M14','recipient':ref('recipient'),'purpose':'learn','authorization':ref('authorization')}
def coverage():return {'state':'complete','domain':known('fixture source'),'scanned':1,'limit':1,'truncated':False,'missing':[]}
def digest():return {'algorithm':'sha256','hex':'a'*64}
def check():return {'state':'matched','checker':principal(),'method':method(),'at':'2026-11-09T12:00:00.000Z','targets':[version()],'reason':'none','basis_refs':[]}
def evidence():
    return {'source':ref('source'),'source_kind':'tool_result','original_result':known(ref('result')),'receipt':known(ref('receipt')),'artifact':ref('artifact'),'source_revision':known(1),'digest':digest(),'media_type':'application/json','encoding':known('utf-8'),'view':absent(),'view_digest':absent(),'locator':{'kind':'json_pointer','pointer':'/value'},'origin_method':method(),'observed_at':known('2026-11-09T12:00:00.000Z'),'reported_at':absent('unknown'),'coverage':coverage(),'derivation_refs':[],'access_dependencies':[]}
def scope():
    return {'subject':known(ref('subject')),'subject_label':known('S'),'property':'reported-inventory','claim_target':'source_report','temporal':{'kind':'observation','start':known('2026-11-09T12:00:00.000Z'),'end':absent(),'bounds':'point'},'conditions':known({}),'domain':known('local source'),'unit':absent('unknown'),'granularity':absent('unknown'),'coverage':coverage(),'exceptions':[],'limitations':['source report only']}
def claim():
    return {'claim_id':'a'*32,'form':'source_report','subject':known(ref('subject')),'predicate':'reported-inventory','value':known(7),'scope':scope(),'evidence':[evidence()],'derivation':method(),'limitations':['not independently true-world verified']}


class ToolLearningTypesTests(unittest.TestCase):
    def test_strict_json_rejects_duplicate_members_at_every_level(self):
        for raw in ('{"a":1,"a":2}','{"x":{"a":1,"a":2}}','[{"a":1,"a":2}]'):
            with self.subTest(raw=raw),self.assertRaises(ContractError):t.loads(raw)

    def test_nonfinite_constants_and_overflow_are_not_json(self):
        for raw in ('NaN','Infinity','-Infinity','1e309','{"x":-1e999}'):
            with self.subTest(raw=raw),self.assertRaises(ContractError):t.loads(raw)
        for value in (float('nan'),float('inf'),-float('inf')):
            with self.assertRaises(ContractError):t.fingerprint({'value':value})

    def test_invalid_unicode_rejected_recursively_without_normalization(self):
        for raw in ('"\\ud800"','{"\\udfff":1}',b'"\xff"','"'+chr(0xD800)+'"'):
            with self.assertRaises(ContractError):t.loads(raw)
        self.assertEqual(t.loads('"\\ud83d\\ude00"'),'😀')
        self.assertNotEqual(t.fingerprint('é'),t.fingerprint('e\u0301'))

    def test_fingerprint_exactly_matches_existing_reference_encoding(self):
        value={'原文':['a',1,False,None],'z':0}
        before=copy.deepcopy(value)
        self.assertEqual(t.fingerprint(value),sha(dumps(value)))
        self.assertEqual(t.fingerprint(value),t.fingerprint({'z':0,'原文':['a',1,False,None]}))
        self.assertNotEqual(t.fingerprint([1,2]),t.fingerprint([2,1]))
        self.assertNotEqual(t.fingerprint(1),t.fingerprint(1.0))
        self.assertEqual(value,before)

    def test_json_objects_must_not_contain_python_only_types_or_cycles(self):
        for value in ({1:'key'},(1,2),{1,2},b'bytes'):
            with self.assertRaises(ContractError):t.fingerprint(value)
        cycle=[];cycle.append(cycle)
        with self.assertRaises(ContractError):t.fingerprint(cycle)

    def test_boolean_is_neither_integer_nor_number(self):
        for validate in (t.integer,t.number):
            with self.assertRaises(ContractError):validate(True)
        self.assertEqual(t.integer(0),0)
        with self.assertRaises(ContractError):t.integer(-1)
        with self.assertRaises(ContractError):t.integer(4,maximum=3)
        self.assertEqual(t.number(-.25),-.25)

    def test_new_ids_are_strict_but_legacy_ref_ids_remain_opaque(self):
        self.assertEqual(t.validate('ID','a'*32),'a'*32)
        for bad in ('A'*32,'a'*31,'g'*32):
            with self.assertRaises(ContractError):t.validate('ID',bad)
        r=ref('legacy:not-a-uuid')
        self.assertIs(t.validate_ref(r),r)
        with self.assertRaises(ContractError):t.validate_ref(ref('x'*241))

    def test_utc_requires_calendar_validity_exact_milliseconds_and_z(self):
        self.assertEqual(t.validate('UTC','2024-02-29T00:00:00.001Z'),'2024-02-29T00:00:00.001Z')
        for value in ('2025-02-29T00:00:00.001Z','2026-01-01T24:00:00.000Z','2026-01-01T00:00:00Z','2026-01-01T00:00:00.000+00:00'):
            with self.assertRaises(ContractError):t.validate('UTC',value)

    def test_slot_preserves_known_false_zero_empty_and_explicit_null(self):
        for value in (0,False,'',[],{}):
            s=known(value)
            self.assertIs(t.slot(s,t.json_value),s)
        s=known(None)
        with self.assertRaises(ContractError):t.slot(s,t.json_value)
        self.assertIs(t.slot(s,t.json_value,allow_null=True),s)
        s['reason_code']='none'
        with self.assertRaises(ContractError):t.slot(s,t.json_value,allow_null=True)

    def test_unknown_is_explicit_not_missing_or_default_zero(self):
        for state in t.STATUSES-{'known'}:
            s=absent(state);self.assertIs(t.slot(s,t.integer),s)
            s['value']=0
            with self.assertRaises(ContractError):t.slot(s,t.integer)
        for mutation in ({'reason':''},{'status':'maybe'},{'reason_code':'made_up'}):
            s=absent();s.update(mutation)
            with self.assertRaises(ContractError):t.slot(s,t.integer)
        s=absent();del s['status']
        with self.assertRaises(ContractError):t.slot(s,t.integer)
        # The frozen spec does not impose additional reason-to-status mappings.
        s=absent('unknown');s['reason_code']='none';t.slot(s,t.integer)

    def test_objects_reject_unknown_keys_and_missing_required_fields(self):
        for value in ({'x':1,'y':2},{},None,[]):
            with self.assertRaises(ContractError):t.obj(value,('x',))
        original={'x':1};self.assertIs(t.obj(original,('x',)),original)

    def test_all_public_structures_return_the_original_without_mutation(self):
        values={'Ref':ref(),'Digest':digest(),'VersionToken':version(),'Principal':principal(),'Method':method(),'Coverage':coverage(),'Check':check(),'EvidenceRef':evidence(),'Scope':scope(),'Claim':claim(),'Control':{'policy':version(),'configuration':version(),'source_epochs':[version()],'runtime_epoch':0,'input_epoch':0,'cancelled':False},'Budget':{'account_ref':ref(),'deadline':'2026-11-09T13:00:00.000Z','max_attempts':1,'max_input_tokens':0,'max_output_tokens':0,'max_tool_calls':0,'max_scan':0,'max_items':0,'max_bytes':0},'Dependency':{'target':ref(),'relation':'support','expected':version(),'consumer_purpose':'learn'}}
        for name,value in values.items():
            with self.subTest(name=name):
                before=copy.deepcopy(value);self.assertIs(t.validate(name,value),value);self.assertEqual(value,before)
                self.assertEqual(t.loads(dumps(value),name),value)

    def test_authority_is_not_implied_by_principal_shape(self):
        value=principal();value['module']='M03';self.assertIs(t.validate('Principal',value),value)
        value['module']='administrator'
        with self.assertRaises(ContractError):t.validate('Principal',value)
        with self.assertRaises(ContractError):t.validate('Unregistered',{})

    def test_check_state_can_be_restricted_by_each_qualification_axis(self):
        value=check();self.assertIs(t.validate_check(value,('matched','mismatch')),value)
        with self.assertRaises(ContractError):t.validate_check(value,('pass','fail'))

    def test_unbounded_json_integer_is_not_limited_by_float_conversion(self):
        large=10**1000
        self.assertEqual(t.loads(str(large)),large)
        self.assertEqual(t.fingerprint(large),sha(dumps(large)))
        t.slot(known(large),t.integer)
        with self.assertRaises(ContractError):t.integer(large,maximum=100)

    def test_content_reference_version_and_dependency_target_must_agree(self):
        v=version();v['object']['revision']=known(2)
        with self.assertRaises(ContractError):t.validate('VersionToken',v)
        d={'target':ref('A'),'relation':'support','expected':version(),'consumer_purpose':'learn'}
        with self.assertRaises(ContractError):t.validate('Dependency',d)
        d['target']=ref();d['target']['revision']=known(2)
        with self.assertRaises(ContractError):t.validate('Dependency',d)

    def test_known_scope_bounds_cannot_reverse_or_disagree_on_point(self):
        s=scope();s['temporal']['end']=known('2026-11-08T12:00:00.000Z')
        with self.assertRaises(ContractError):t.validate_scope(s)
        s['temporal']['end']=known('2026-11-10T12:00:00.000Z')
        with self.assertRaises(ContractError):t.validate_scope(s)
        s['temporal']['bounds']='closed';self.assertIs(t.validate_scope(s),s)
        s['temporal']['end']=absent('unknown');self.assertIs(t.validate_scope(s),s)

    def test_json_pointer_escapes_empty_key_and_array_indices(self):
        view={'a/b':{'~':{'':7}},'array':[None,False,0]}
        self.assertEqual(t.resolve_locator({'kind':'json_pointer','pointer':'/a~1b/~0/'},view),7)
        self.assertIs(t.resolve_locator({'kind':'json_pointer','pointer':'/array/1'},view),False)
        self.assertIs(t.resolve_locator({'kind':'json_pointer','pointer':''},view),view)
        for pointer in ('no-slash','/bad~2','/array/01','/array/-','/array/3','/missing'):
            with self.subTest(pointer=pointer),self.assertRaises(ContractError):t.resolve_locator({'kind':'json_pointer','pointer':pointer},view)

    def test_nested_json_string_is_not_implicitly_parsed(self):
        view={'text':'{"value":7}'}
        with self.assertRaises(ContractError):t.resolve_locator({'kind':'json_pointer','pointer':'/text/value'},view)
        nested=t.loads(t.resolve_locator({'kind':'json_pointer','pointer':'/text'},view))
        self.assertEqual(t.resolve_locator({'kind':'json_pointer','pointer':'/value'},nested),7)

    def test_unicode_text_ranges_use_codepoints_and_exact_quotes(self):
        view='A😀中e\u0301Z'
        loc={'kind':'text_range','start':1,'end':3,'quote':known('😀中')}
        self.assertEqual(t.resolve_locator(loc,view),'😀中')
        loc['quote']=known('wrong')
        with self.assertRaises(ContractError):t.resolve_locator(loc,view)
        loc.update(start=2,end=20,quote=absent())
        with self.assertRaises(ContractError):t.resolve_locator(loc,view)
        self.assertEqual(t.resolve_locator({'kind':'text_range','start':0,'end':0,'quote':known('')},view),'')
        self.assertEqual(t.resolve_locator({'kind':'text_range','start':0,'end':1,'quote':known(' ')},' '),' ')

    def test_byte_range_rejects_text_view_and_oversized_end(self):
        loc={'kind':'byte_range','start':1,'end':3};self.assertEqual(t.resolve_locator(loc,b'abc'),b'bc')
        with self.assertRaises(ContractError):t.resolve_locator(loc,'abc')
        loc['end']=4
        with self.assertRaises(ContractError):t.resolve_locator(loc,b'abc')

    def test_tool_source_requires_known_original_result_and_receipt(self):
        e=evidence();e['receipt']=absent()
        with self.assertRaises(ContractError):t.validate('EvidenceRef',e)
        e=evidence();e['source_kind']='user_statement'
        with self.assertRaises(ContractError):t.validate('EvidenceRef',e)
        e['original_result']=absent();e['receipt']=absent();self.assertIs(t.validate('EvidenceRef',e),e)

    def test_view_and_digest_preserve_independent_unknown_slots(self):
        e=evidence();e['view']=known(ref('view'));e['view_digest']=absent('unknown')
        self.assertIs(t.validate('EvidenceRef',e),e)
        e['view_digest']=absent('not_collected');self.assertIs(t.validate('EvidenceRef',e),e)
        e['view']=absent('unknown');e['view_digest']=known(digest())
        self.assertIs(t.validate('EvidenceRef',e),e)
        e['view']=known(ref('view'));self.assertIs(t.validate('EvidenceRef',e),e)

    def test_empty_evidence_never_satisfies_a_substantive_claim(self):
        c=claim();c['evidence']=[]
        with self.assertRaises(ContractError):t.validate_claim(c)

    def test_budget_has_no_implicit_infinite_or_negative_allowance(self):
        b={'account_ref':ref(),'deadline':'2026-11-09T13:00:00.000Z','max_attempts':1,'max_input_tokens':0,'max_output_tokens':0,'max_tool_calls':0,'max_scan':0,'max_items':0,'max_bytes':0}
        t.validate('Budget',b)
        for field,value in (('max_attempts',0),('max_scan',-1),('max_bytes',None),('max_output_tokens',True)):
            bad=copy.deepcopy(b);bad[field]=value
            with self.assertRaises(ContractError):t.validate('Budget',bad)

    def test_whole_artifact_returns_explicit_supplied_bytes_without_parsing(self):
        data=b'\xff\x00fixture';loc={'kind':'whole_artifact','justification':'explicit atomic binary fixture'}
        self.assertIs(t.resolve_locator(loc,data),data)
        text='raw text';self.assertIs(t.resolve_locator(loc,text),text)
        with self.assertRaises(ContractError):t.resolve_locator({'kind':'json_pointer','pointer':''},data)


if __name__=='__main__':unittest.main()
