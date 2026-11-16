"""Lossless bounded graph data; actual qualification remains outside the cache."""
from contextlib import contextmanager
from copy import deepcopy
import json
import sys
import unittest
from unittest.mock import patch
import zlib
from digital_life.domain.contracts import ContractError,Conflict,Forbidden
from digital_life.infrastructure.persistence import tool_learning_readset as reads
from digital_life.infrastructure.persistence.tool_learning_graph_material import GraphMaterial,encode_graph,decode_graph,storage_size
from digital_life.application.learning.eligibility import _mint_signature_check
from tests import test_tool_learning_certified_input as fixture

class GraphCodecTests(unittest.TestCase):
    def test_lossless_unicode_fresh_decode_and_real_storage_headers(self):
        text=json.dumps({'scope':['中文'*100]*100},ensure_ascii=False);value=encode_graph(text,4194304)
        self.assertTrue(value.compressed);self.assertEqual(storage_size(value),sum(sys.getsizeof(v)for v in (value,value.body,value.raw_size,value.compressed)))
        first=json.loads(decode_graph(value,4194304));first['scope'].append('changed')
        self.assertEqual(json.loads(decode_graph(value,4194304)),json.loads(text))
    def test_small_uncompressed_graph_has_same_strict_size_and_utf8_checks(self):
        text='["small"]';value=encode_graph(text,4194304)
        self.assertFalse(value.compressed);self.assertEqual(decode_graph(value,4194304),text)
        for value in (GraphMaterial(b'bad',1,False),GraphMaterial(b'\xff',1,False),GraphMaterial(b'x',1,1)):
            with self.assertRaises(ContractError):decode_graph(value,4194304)
    def test_stream_corruption_truncation_tails_second_stream_and_raw_bounds(self):
        raw=b'"'+b'a'*2048+b'"';body=zlib.compress(raw)
        for value in (GraphMaterial(body[:-1],len(raw),True),GraphMaterial(body+b'x',len(raw),True),GraphMaterial(body+body,len(raw),True),GraphMaterial(body,len(raw)-1,True),GraphMaterial(body,True,True),GraphMaterial(zlib.compress(b'\xff'),1,True),GraphMaterial(body,4194305,True),GraphMaterial(b'x'*4194305,1,True)):
            with self.subTest(size=value.raw_size),self.assertRaises(ContractError):decode_graph(value,4194304)
        self.assertIsNone(encode_graph('a'*4194305,4194304))
        with self.assertRaises(ContractError):encode_graph([],4194304)

class GraphMaterialTests(unittest.TestCase):
    def setUp(self):
        self.c=fixture.CertifiedInputTests();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.s=self.c.s;self.service=self.c.e.runtime.eligibility
    @contextmanager
    def lease(self):
        with self.c.meter().installed(self.s),self.c.e.owners.source.verification_boundary():
            phase=reads.current_readset(self.s);phase.checkpoint();phase.check_depth=1
            phase.signature_check=_mint_signature_check(self.service,phase);self.assertIsNotNone(phase.signature_check)
            try:yield phase
            finally:phase.signature_check=None;phase.check_depth=0
    def build(self):return self.service._upstream(self.c.token,self.c.scope,{'remaining':self.service.max_rows})
    def test_first_complete_graph_is_retained_and_each_hit_spends_same_logical_rows(self):
        with self.lease()as phase:
            first_budget={'remaining':self.service.max_rows};first=self.service._upstream(self.c.token,self.c.scope,first_budget)
            self.assertEqual(self.s._graph_material_stats,dict(eligible=1,stored=1,returned=0,used=0))
            self.assertIs(type(next(iter(phase.graphs.values()))[0]),GraphMaterial)
            expected=deepcopy(first);first[0][1]['mutated_return']=True
            second_budget={'remaining':self.service.max_rows};second=self.service._upstream(self.c.token,self.c.scope,second_budget)
            self.assertEqual(second,expected);self.assertEqual(first_budget,second_budget)
            self.assertEqual(self.s._graph_material_stats,dict(eligible=2,stored=1,returned=1,used=1))
            self.assertLessEqual(phase.bytes+phase.blob_bytes,phase.max_bytes);self.assertLessEqual(phase.entry_count(),phase.max_keys)
    def test_decoded_graph_without_enough_logical_budget_is_not_used(self):
        with self.lease()as phase:
            self.build();self.assertGreater(next(iter(phase.graphs.values()))[1],0)
            before=dict(self.s._graph_material_stats)
            with self.assertRaisesRegex(Forbidden,'row scan limit'):
                self.service._upstream(self.c.token,self.c.scope,{'remaining':0})
            self.assertEqual(self.s._graph_material_stats['used'],before['used'])
            self.assertEqual(self.s._graph_material_stats['returned'],before['returned']+1)
    def test_unknown_consumer_cannot_decode_first_produced_small_or_large_material(self):
        with self.lease()as phase:
            phase.remember_graph('small','[]',0);phase.remember_graph('large','['+'"'+('x'*2000)+'"'+']',0)
            phase.signature_check=None
            self.assertIsNone(phase.graph('small'));self.assertIsNone(phase.graph('large'))
            self.assertFalse(phase.graph_admitted('unknown'));self.assertTrue(phase.graph_admitted('unknown'))
    def test_bad_retained_stream_is_rejected_before_any_return_counter(self):
        with self.lease()as phase:
            self.build();key=next(iter(phase.graphs));value,rows=phase.graphs[key]
            phase.graphs[key]=(GraphMaterial(value.body+b'tail',value.raw_size,value.compressed),rows)
            with self.assertRaises(ContractError):phase.graph(key)
            self.assertEqual(self.s._graph_material_stats['returned'],0)
    def test_preflight_key_and_byte_reclaim_uses_prepared_then_cold_facts_not_blobs(self):
        with self.lease()as phase:
            phase.max_keys=3
            phase.remember_prepared_metadata(('old',1),'{}','scope')
            phase.remember_prepared_metadata(('old',2),'{}','scope')
            phase.remember(('source_kind',('synthetic',)),())
            blobs=dict(phase.blobs)
            phase.remember_graph('fit',json.dumps(['x'*2000]*10),4)
            self.assertIn('fit',phase.graphs);self.assertEqual(len(phase.prepared),1)
            self.assertEqual(phase.blobs,blobs);self.assertEqual(phase.entry_count(),3)
            before=(dict(phase.prepared),dict(phase.cache),dict(phase.blobs),phase.bytes)
            phase.remember_graph('too-big','x'*(phase.max_bytes+1),4)
            self.assertEqual(before,(dict(phase.prepared),dict(phase.cache),dict(phase.blobs),phase.bytes))
    def test_tracked_blob_priority_can_evict_graph_without_refunding_logical_budget(self):
        with self.lease()as phase:
            phase.remember_graph('graph','[]',19);phase._evict_material()
            self.assertNotIn('graph',phase.graphs);self.assertEqual(self.s._graph_material_stats['stored'],1)
    def test_failed_partial_walk_never_creates_graph(self):
        row=self.s.db.execute('SELECT metadata_artifact_id FROM tl_dependency WHERE consumer_ref_id=? AND relation=? LIMIT 1',(self.c.token['object']['id'],'read')).fetchone()
        artifact=self.s.row('artifacts',row[0]);path=self.s.root/'blobs'/artifact['storage_ref'];prior=path.read_bytes();path.write_bytes(b'bad')
        try:
            with self.lease()as phase:
                with self.assertRaises((ContractError,Conflict)):self.build()
                self.assertEqual(phase.graphs,{});self.assertGreater(self.s._graph_material_stats['eligible'],0)
                self.assertEqual(self.s._graph_material_stats['stored'],0)
        finally:path.write_bytes(prior)
    def test_mutation_configuration_and_rollback_invalidate_old_graph(self):
        for action in ('write','config','rollback'):
            with self.subTest(action=action),self.lease()as phase:
                self.build()
                if action=='write':self.s.db.execute('UPDATE activities SET revision=revision WHERE id=?',('missing',))
                elif action=='config':self.s.db.create_function('graph_config_test',0,lambda:1)
                else:self.s.db.execute('BEGIN');self.s.db.rollback()
                self.assertIsNone(phase.graph(next(iter(phase.graphs),'missing')))
                self.assertEqual(phase.graphs,{})
    def test_callback_and_observer_never_admit_first_graph(self):
        observed=[]
        def callback():
            phase=reads.current_readset(self.s);observed.append(phase.graph_admitted('callback'));return 1
        self.s.db.create_function('graph_callback_test',0,callback)
        with self.lease()as phase:
            self.s.db.execute('SELECT graph_callback_test()').fetchone();self.assertEqual(observed,[False])
            meter=phase.signature_check['meter'];prior=getattr(meter,'row_observer',None);meter.row_observer=lambda row:None
            try:self.assertFalse(phase.graph_admitted('observer'))
            finally:meter.row_observer=prior
