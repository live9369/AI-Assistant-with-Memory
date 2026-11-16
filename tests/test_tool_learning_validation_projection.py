"""Same-database validation decisions and actual collector row completeness."""
import copy
import unittest
from digital_life.domain.contracts import ContractError,Conflict,Forbidden,utc
from digital_life.domain.tool_learning_resources import DIMENSIONS
from digital_life.application.learning.eligibility import slot
from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
from digital_life.infrastructure.persistence.tool_learning_meter import PhysicalReadMeter

class ValidationMetadataProjectionTests(unittest.TestCase):
    def setUp(self):
        from tests.test_tool_learning_runtime import SourceSnapshotTests
        self.f=SourceSnapshotTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.token=self.f.capture();self.known=copy.deepcopy(self.token['object']);self.known['revision']=slot(self.token['revision'])
        self.storage=ToolLearningStore(self.s)
        self.event=self.s.db.execute('SELECT e.* FROM object_revision_registry r JOIN runtime_events e ON e.instance_id=r.instance_id AND e.id=r.id WHERE r.instance_id=? AND r.object_id=? AND r.revision_no=?',(self.s.instance_id,self.known['id'],self.token['revision'])).fetchone()
        self.artifact=self.event['payload_artifact_id']
    def outcome(self,operation,complete):
        meter=PhysicalReadMeter({k:10000000 for k in DIMENSIONS},utc(60));rows=[];sql=[];self.s.db.set_trace_callback(sql.append)
        if complete:meter.row_observer=lambda row:rows.append(dict(row))
        with meter.installed(self.s):
            try:value=operation();result=('ok',value)
            except (ContractError,Conflict,Forbidden)as error:result=('error',type(error).__name__,str(error))
        self.s.db.set_trace_callback(None)
        return result,dict(meter.actual),rows,sql
    def equivalent(self,operation):
        projected=self.outcome(operation,False);complete=self.outcome(operation,True)
        self.assertEqual(projected[0],complete[0]);return projected,complete
    def test_valid_reference_full_body_and_actual_meter_match_except_unused_metadata_bytes(self):
        projected,complete=self.equivalent(lambda:self.storage.validate_ref(self.known))
        self.assertEqual(projected[0],('ok',self.known));self.assertEqual(projected[1]['scan'],complete[1]['scan'])
        self.assertLess(projected[1]['bytes'],complete[1]['bytes'])
        self.assertTrue(any('SELECT e.event_type,e.payload_artifact_id,e.payload_hash FROM'in sql for sql in projected[3]))
        self.assertTrue(any('SELECT e.* FROM'in sql for sql in complete[3]))
        self.assertTrue(any('SELECT instance_id,id,hash,size,media_type,storage_ref FROM artifacts'in sql for sql in projected[3]))
        self.assertTrue(any('SELECT * FROM artifacts'in sql for sql in complete[3]))
    def test_bad_event_type_is_equally_rejected(self):
        self.s.db.execute("UPDATE runtime_events SET event_type='synthetic.wrong.type' WHERE id=?",(self.event['id'],))
        self.assertEqual(self.equivalent(lambda:self.storage.validate_ref(self.known))[0][0][0],'error')
    def test_bad_source_is_equally_rejected(self):
        self.s.db.execute("UPDATE runtime_events SET source='synthetic.wrong.source' WHERE id=?",(self.event['id'],))
        self.assertEqual(self.equivalent(lambda:self.storage.validate_ref(self.known))[0][0][0],'error')
    def test_missing_join_registration_is_equally_rejected(self):
        self.s.db.execute('PRAGMA foreign_keys=OFF')
        for row in self.s.db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='object_registry'").fetchall():self.s.db.execute('DROP TRIGGER '+row[0])
        self.s.db.execute('DELETE FROM object_registry WHERE id=?',(self.event['id'],))
        self.assertEqual(self.equivalent(lambda:self.storage.validate_ref(self.known))[0][0][0],'error')
    def test_bad_payload_hash_is_equally_rejected(self):
        self.s.db.execute('UPDATE runtime_events SET payload_hash=? WHERE id=?',('0'*64,self.event['id']))
        self.assertEqual(self.equivalent(lambda:self.storage.validate_ref(self.known))[0][0][0],'error')
    def test_wrong_revision_and_owner_are_equally_rejected(self):
        wrong=copy.deepcopy(self.known);wrong['revision']=slot(self.token['revision']+100)
        self.assertEqual(self.equivalent(lambda:self.storage.validate_ref(wrong))[0][0][0],'error')
        self.assertEqual(self.equivalent(lambda:self.storage.validate_ref(self.known,version_owner=self.s.config()['controller']))[0][0][0],'error')
    def test_snapshot_payload_origin_and_revision_mapping_are_equally_rejected(self):
        from digital_life.domain.tool_learning_contract import fingerprint
        original=self.storage.read_artifact(self.artifact)
        other=self.s.db.execute('SELECT id FROM personality_trait_values WHERE instance_id=? AND id<>? LIMIT 1',(self.s.instance_id,self.known['id'])).fetchone()[0]
        for changed in ('origin','revision'):
            value=copy.deepcopy(original)
            if changed=='origin':value['origin']['id']=other
            else:value['snapshot_revision']+=1
            artifact=self.s.artifact(value)
            self.s.db.execute('UPDATE runtime_events SET payload_artifact_id=?,payload_hash=? WHERE id=?',(artifact,fingerprint(value),self.event['id']))
            self.assertEqual(self.equivalent(lambda:self.storage.validate_ref(self.known))[0][0][0],'error')
    def test_invalid_location_and_body_preflight_budget_still_fail_before_unsafe_read(self):
        from unittest.mock import patch
        self.s.db.execute("UPDATE artifacts SET storage_ref='../runtime.sqlite' WHERE id=?",(self.artifact,))
        self.assertEqual(self.equivalent(lambda:self.storage.read_artifact(self.artifact))[0][0][0],'error')
        large=self.s.artifact({'full bytes':'x'*10000});limits={k:100000 for k in DIMENSIONS};limits['bytes']=9999
        meter=PhysicalReadMeter(limits,utc(30))
        with meter.installed(self.s),patch('digital_life.infrastructure.persistence.tool_learning_store.os.open',side_effect=AssertionError('insufficient body budget must reject first')):
            with self.assertRaises(Forbidden):self.storage.read_artifact(large)
        self.assertEqual(meter.actual['scan'],1);self.assertGreater(meter.actual['bytes'],0)
    def test_missing_artifact_is_equally_rejected(self):
        self.assertEqual(self.equivalent(lambda:self.storage.read_artifact('f'*32))[0][0][0],'error')
    def test_wrong_artifact_size_and_hash_reject(self):
        self.s.db.execute('UPDATE artifacts SET size=size+1 WHERE id=?',(self.artifact,))
        self.assertEqual(self.equivalent(lambda:self.storage.read_artifact(self.artifact))[0][0][0],'error')
        self.s.db.execute('UPDATE artifacts SET size=size-1,hash=? WHERE id=?',('0'*64,self.artifact))
        self.assertEqual(self.equivalent(lambda:self.storage.read_artifact(self.artifact))[0][0][0],'error')
    def test_corrupt_bytes_and_symlink_reject(self):
        row=self.s.row('artifacts',self.artifact);path=self.s.root/'blobs'/row['storage_ref'];raw=path.read_bytes()
        path.write_bytes(b'x'*len(raw));self.assertEqual(self.equivalent(lambda:self.storage.read_artifact(self.artifact))[0][0][0],'error')
        path.unlink();path.symlink_to(self.s.root/'runtime.sqlite')
        self.assertEqual(self.equivalent(lambda:self.storage.read_artifact(self.artifact))[0][0][0],'error')
    def test_metadata_does_not_truncate_real_body_or_disable_named_json_validation(self):
        value={'full body':'中文'*10000};key=self.s.artifact(value)
        projected,complete=self.equivalent(lambda:self.storage.read_artifact(key,fresh=True))
        self.assertEqual(projected[0],('ok',value));self.assertGreaterEqual(projected[1]['bytes'],self.s.row('artifacts',key)['size'])
        self.s.db.execute("UPDATE artifacts SET media_type='text/plain' WHERE id=?",(key,))
        self.assertEqual(self.equivalent(lambda:self.storage.read_artifact(key,'Scope'))[0][0][0],'error')

class ActualCollectorProjectionProtectionTests(unittest.TestCase):
    def test_real_collector_keeps_full_rows_and_event_uuid_sources(self):
        from tests.test_tool_learning_runtime import StrictEngineEndToEndTests
        from digital_life.application.learning.contexts import DomainReadCollector
        from digital_life.application.learning.engine import source_scope
        from digital_life.application.learning.eligibility import ref
        fixture=StrictEngineEndToEndTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        s=fixture.s;engine=fixture.strict;scope=source_scope(s)
        entry,principal=engine.owners.entry('M14','learn',engine._recipient(fixture.activity))
        origin=ref(s,s.rows('personality_trait_values')[0]['id'])
        token=engine.owners.snapshots.capture(entry,principal,origin,['central_value'],scope)
        known=copy.deepcopy(origin);known['revision']=slot(token['revision'])
        event=s.db.execute('SELECT e.* FROM object_revision_registry r JOIN runtime_events e ON e.instance_id=r.instance_id AND e.id=r.id WHERE r.instance_id=? AND r.object_id=? AND r.revision_no=?',(s.instance_id,origin['id'],token['revision'])).fetchone()
        collector=DomainReadCollector(engine,entry,principal,scope,set());meter=PhysicalReadMeter({k:10000000 for k in DIMENSIONS},utc(60));sql=[];s.db.set_trace_callback(sql.append)
        observed=[];actual_observer=collector.on_row
        def record_and_observe(row):
            observed.append(dict(row));return actual_observer(row)
        collector.on_row=record_and_observe
        with meter.installed(s),collector.installed(meter):engine.owners.eligibility.artifacts.validate_ref(known)
        self.assertIn(event['id'],{key[0]for key in collector.tokens})
        self.assertIn(event['payload_artifact_id'],{key[0]for key in collector.tokens})
        self.assertTrue(any('SELECT e.* FROM'in statement for statement in sql))
        self.assertTrue(any('SELECT * FROM artifacts WHERE'in statement for statement in sql))
        self.assertFalse(any('SELECT e.event_type,e.payload_artifact_id,e.payload_hash FROM'in statement for statement in sql))
        # Existing readset identity queries already use six columns; they are
        # not this change. Prove the safe reader still supplies complete rows.
        artifact=s.row('artifacts',event['payload_artifact_id'])
        self.assertTrue(any(row.get('id')==artifact['id'] and set(artifact)<=set(row)for row in observed))
        self.assertTrue(any(row.get('id')==event['id'] and set(event.keys())<=set(row)for row in observed))

if __name__=='__main__':unittest.main()
