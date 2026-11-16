import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from digital_life.application.runtime.strict_initialization import prepare_new_strict,ORDINARY_CAPS
from digital_life.application.lifecycle.control_plane import Control
from digital_life.domain.contracts import ContractError

class StrictInitializationTests(unittest.TestCase):
 def test_new_schema_policy_features_and_offline_model_remain_locked(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary)/'strict'
   with patch('digital_life.application.runtime.configuration.probe',side_effect=AssertionError('no real model probe')):
    store=prepare_new_strict(root,model_config={'backend':'ollama','model':'isolated-not-downloaded','base_url':'http://127.0.0.1:11434'})
   try:
    self.assertEqual(store.db.execute('PRAGMA user_version').fetchone()[0],4)
    self.assertIn('tl_work',store.columns)
    self.assertTrue((root/'WAKE_DISABLED').is_file())
    control=Control(root,store.instance_id)
    try:self.assertEqual(control.state()['user_stopped'],1);self.assertIsNone(control.state()['active_process_run_id'])
    finally:control.close()
    row=store.db.execute('SELECT p.scope FROM policy_versions p JOIN policy_epochs e ON p.id=e.policy_version_id WHERE e.instance_id=?',(store.instance_id,)).fetchone()
    scope=json.loads(row[0]);self.assertEqual(scope['tool_learning_runtime']['ordinary_activity_caps'],ORDINARY_CAPS)
    self.assertEqual(scope['root'],str(root.resolve()/'workspace'))
    from digital_life.application.behavior.goal_regulation import GoalRegulation
    self.assertEqual(GoalRegulation(store).config()['min_disk_bytes'],67108864)
    from digital_life.application.behavior.behavior_policy import BehaviorPolicy
    from digital_life.application.behavior.personality_growth import PersonalityGrowth
    from digital_life.application.behavior.habit_learning import HabitLearning
    from digital_life.application.behavior.people_relations import PeopleRelations
    from digital_life.application.memory.memory_quality import MemoryQuality
    from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
    from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
    for service in (BehaviorPolicy,GoalRegulation,PersonalityGrowth,HabitLearning,PeopleRelations,MemoryQuality,AutonomyAgenda,SelfMaintenance):
     self.assertTrue(service(store).config()['enabled'],service.__name__)
    config=store.db.execute('SELECT compatibility FROM configuration_versions ORDER BY rowid DESC LIMIT 1').fetchone()
    self.assertIn('model_version_id',json.loads(config[0]))
    self.assertEqual(store.integrity(),{'foreign_keys':[],'integrity':'ok'})
   finally:store.close()
   with self.assertRaises(ContractError):prepare_new_strict(root,model_config={'backend':'ollama','model':'isolated'})
 def test_existing_empty_root_refused_without_mutation(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary)/'existing';root.mkdir();(root/'marker').write_text('retain')
   with self.assertRaises(ContractError):prepare_new_strict(root,model_config={'backend':'ollama','model':'isolated'})
   self.assertEqual(list(root.iterdir()),[root/'marker'])

if __name__=='__main__':unittest.main()
