import json
from pathlib import Path
import tempfile
import unittest
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.runtime.engine import Engine
from digital_life.application.services import Memory,Personality,Learning
from digital_life.application.lifecycle.health_monitor import HealthMonitor
from digital_life.application.accounts.privacy import Privacy
from digital_life.application.memory.data_management import backup_bundle,restore_bundle
from digital_life.domain.contracts import Conflict

class RemainingServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'instance'; self.s=Store.prepare(self.root)
        self.addCleanup(self.tmp.cleanup); self.addCleanup(self.s.close)
    def evidence(self):
        with self.s.tx(): return self.s.evidence(artifact=self.s.artifact({'independent':'fixture'}))
    def test_expand_only_migration_preserves_history_and_is_idempotent(self):
        from digital_life.application.lifecycle.schema_migration import migrate
        Engine(self.s).submit('before migration','migration-test')
        count=len(self.s.rows('activities')); result=migrate(self.s,self.s.config()['controller'])
        self.assertEqual(result['version'],3); self.assertEqual(len(self.s.rows('activities')),count)
        self.assertTrue(migrate(self.s,self.s.config()['controller'])['already_applied'])
        self.assertTrue((self.root/'WAKE_DISABLED').exists()); self.assertEqual(self.s.integrity()['foreign_keys'],[])
    def test_retrieval_permissions_and_derived_policy_intersection(self):
        engine=Engine(self.s); activity=engine.submit('sensitive','key'); context=engine.details(activity)[1]['id']
        memory=Memory(self.s); controller=self.s.config()['controller']; evidence=self.evidence()
        first=memory.encode('sensitive secret',evidence)['memory_id']
        memory.restrict(first,[controller],controller)
        derived=memory.derive('sensitive summary',[first],evidence,controller)['memory_id']
        self.assertEqual(memory.readers(derived),{controller})
        results=memory.retrieve('sensitive',activity,context)
        self.assertNotIn('sensitive secret',[r['content'] for r in results['items']])
        results=memory.retrieve('sensitive',activity,context,actor=controller)
        self.assertNotIn('sensitive secret',[r['content'] for r in results['items']])
    def test_multidimensional_health_does_not_invent_cognitive_health(self):
        report=HealthMonitor(self.s).scan()
        self.assertEqual(report['dimensions']['cognition']['state'],'unknown')
        self.assertEqual(report['state'],'unknown')
        (self.root/'workspace').rmdir()
        self.assertEqual(HealthMonitor(self.s).scan()['state'],'degraded')
    def test_personality_rollback_appends_history_and_rejects_replay(self):
        refs=[self.evidence(),self.evidence()]; actor=self.s.config()['controller']
        commit=Personality(self.s).replace({'openness':0.5},refs,actor)['commit']
        reversal=Learning(self.s).rollback(commit,refs,actor)
        self.assertEqual(Personality(self.s).current()['profile']['version'],2)
        current=Personality(self.s).current()
        self.assertEqual(next(r['central_value'] for r in current['traits'] if r['name']=='openness'),0)
        self.assertEqual(self.s.row('learning_update_commits',reversal)['reversal_of'],commit)
        with self.assertRaises(Conflict): Learning(self.s).rollback(commit,refs,actor)
        self.assertEqual(self.s.integrity()['foreign_keys'],[])
    def test_managed_erasure_propagates_to_derivation_and_backup(self):
        secret='unique-secret-for-erasure-843982'
        engine=Engine(self.s); engine.submit(secret,'privacy-input')
        memory=self.s.rows('memory_items')[0]['id']; evidence=self.evidence(); actor=self.s.config()['controller']
        derived=Memory(self.s).derive('summary '+secret,[memory],evidence,actor)['memory_id']
        backup=Path(self.tmp.name)/'backup'; backup_bundle(self.s,backup)
        snapshot=self.root/'snapshots/private.sqlite'; self.s.snapshot(snapshot)
        result=Privacy(self.s).erase(memory,actor,True)
        self.assertEqual(result['state'],'verified'); self.assertEqual(result['managed_backups'],1)
        self.assertFalse(snapshot.exists()); self.assertEqual(result['managed_snapshots'],1)
        self.assertEqual(self.s.row('memory_items',derived)['state'],'deleted')
        for root in (self.root,backup):
            self.assertNotIn(secret.encode(),(root/'runtime.sqlite').read_bytes())
            for blob in (root/'blobs').iterdir(): self.assertNotIn(secret.encode(),blob.read_bytes())
        restored=Path(self.tmp.name)/'restored'
        self.assertTrue(restore_bundle(backup,restored)['wake_disabled'])
        self.assertEqual(self.s.integrity()['foreign_keys'],[])
