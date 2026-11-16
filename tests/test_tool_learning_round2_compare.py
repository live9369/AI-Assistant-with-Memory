"""Comparator tests use a complete tiny manifest, never an actual instance."""
from copy import deepcopy
import unittest
from evaluation.tool_learning_round2_compare import compare
from digital_life.domain import tool_learning_contract as c
from tests.test_tool_learning_products import scope


def bundle(identity='a'*32):
    packet={'id':identity,'value':{'scope':scope(),'condition':'must retain','timestamp':'2026-01-01T00:00:00Z','cap':256},'empty':[]}
    fields=[]
    for key in packet:
        fields.append({'path':'/'+key,'digest':{'algorithm':'sha256','hex':c.fingerprint(packet[key])},'kind':'fixed_instruction','usage':'fixed_instruction','dependencies':[],'dependency_scopes':[],'scope':scope()})
    return {'packet':packet,'manifest':{'contract':'TL-INPUT-ASSEMBLY-1','packet_digest':c.fingerprint(packet),'fields':fields}}


def reseal(value):
    packet=value['packet'];manifest=value['manifest'];manifest['packet_digest']=c.fingerprint(packet)
    for field in manifest['fields']:field['digest']['hex']=c.fingerprint(packet[field['path'][1:]])


class StrictRound2CompareTests(unittest.TestCase):
    def test_identical_full_bundle_passes(self):self.assertTrue(compare(bundle(),bundle())['passed'])
    def test_ids_require_explicit_exact_paths(self):
        a,b=bundle(),bundle('b'*32)
        self.assertFalse(compare(a,b)['passed'])
        result=compare(a,b,[{'left':'a'*32,'right':'b'*32,'paths':['/packet/id']}])
        self.assertTrue(result['passed']);self.assertEqual(len(result['applied_id_paths']),1)
    def test_timestamps_conditions_caps_scope_are_not_ignored(self):
        for key,new in [('timestamp','2026-01-02T00:00:00Z'),('condition','relaxed'),('cap',257),('scope',dict(scope(),property='different'))]:
            with self.subTest(key=key):
                a=bundle();b=deepcopy(a);b['packet']['value'][key]=new;reseal(b)
                self.assertFalse(compare(a,b)['passed'])
    def test_broken_original_digest_does_not_get_resealed_into_success(self):
        a=bundle();b=deepcopy(a);b['manifest']['fields'][0]['digest']['hex']='0'*64
        with self.assertRaises(Exception):compare(a,b)
    def test_duplicate_or_false_id_witness_is_rejected(self):
        a,b=bundle(),bundle('b'*32)
        for paths in [['/packet/id','/packet/id'],['/packet/value/condition']]:
            with self.assertRaises(ValueError):compare(a,b,[{'left':'a'*32,'right':'b'*32,'paths':paths}])
    def test_injective_mapping_and_exact_types(self):
        a=bundle();b=deepcopy(a);b['packet']['value']['cap']=256.0;reseal(b)
        self.assertFalse(compare(a,b)['passed'])
        with self.assertRaises(ValueError):compare(a,b,[{'left':'a'*32,'right':'b'*32,'paths':['/packet/id']}])
    def test_many_to_one_identity_mapping_is_rejected(self):
        a=bundle();b=deepcopy(a)
        a['packet']['empty']=['c'*32];b['packet']['id']='b'*32;b['packet']['empty']=['b'*32]
        reseal(a);reseal(b)
        with self.assertRaises(ValueError):compare(a,b,[{'left':'a'*32,'right':'b'*32,'paths':['/packet/id']},{'left':'c'*32,'right':'b'*32,'paths':['/packet/empty/0']}])
    def test_array_order_missing_fields_and_partial_projection_fail(self):
        a=bundle();b=deepcopy(a);b['packet']['empty']=[1];reseal(b)
        self.assertFalse(compare(a,b)['passed'])
        with self.assertRaises(ValueError):compare({'packet':{}},b)

if __name__=='__main__':unittest.main()
