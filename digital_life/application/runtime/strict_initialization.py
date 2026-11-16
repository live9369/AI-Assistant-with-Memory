"""Explicit new-only strict bootstrap. Never deploys, resumes or invokes a model."""
import json
from pathlib import Path
import sqlite3
from digital_life.domain.contracts import ContractError, dumps, sha, utc
from digital_life.infrastructure.persistence.sqlite_store import Store, RESOURCES
from digital_life.application.lifecycle.control_plane import Control

ORDINARY_CAPS={'max_input_tokens':200000,'max_output_tokens':200,'max_attempts':8,
 'max_tool_calls':8,'max_scan':2000000,'max_items':2000000,
 'max_bytes':512*1024*1024,'elapsed_ms':600000}

def prepare_new_strict(root,name='原初00',model_config=None):
    if model_config is None:raise ContractError('strict initialization requires an explicit model configuration')
    root=Path(root).absolute()
    if root.is_symlink() or (root/'runtime.sqlite').exists() or (root/'runtime.sqlite').is_symlink():
        raise ContractError('strict initialization requires a new runtime database')
    # Reserve the new directory atomically; never adopt a partial/previous root.
    if root.exists():raise ContractError('strict initialization requires a new root')
    root.mkdir(parents=True,exist_ok=False)
    (root/'WAKE_DISABLED').write_text('Strict initialization: explicit wake authorization required.\n')
    store=None;control=None
    try:
        store=Store.prepare(root,name,model_config)
        control=Control(root,store.instance_id)
        from digital_life.application.lifecycle.schema_migration import migrate
        migrate(store,store.config()['controller'],target=3)
        ddl=(RESOURCES/'tool_learning_v1.sql').read_text()
        checksum=sha(ddl)
        with store.tx():
            statement=''
            for line in ddl.splitlines(keepends=True):
                statement+=line
                if sqlite3.complete_statement(statement):
                    store.db.execute(statement);statement=''
            if statement.strip():
                # Trailing SQL comments need no execution.
                if any(line.strip() and not line.lstrip().startswith('--') for line in statement.splitlines()):
                    raise ContractError('incomplete strict schema statement')
            store.db.execute((RESOURCES/'source_lookup_indexes.sql').read_text())
            store.insert('schema_migrations',version=4,checksum=checksum,applied_at=utc(),release_id='strict-new-schema-v4')
            store.db.execute('PRAGMA user_version=4')
            store.event('schema.expanded',payload={'from':3,'to':4,'checksum':checksum,'new_instance_only':True},lane='control')
            if store.integrity()['foreign_keys']:raise ContractError('strict schema foreign key failure')
        store.close();store=Store(root)
        actor=store.config()['controller']
        with store.tx():
            current=store.db.execute('SELECT p.* FROM policy_versions p JOIN policy_epochs e ON e.policy_version_id=p.id AND e.instance_id=p.instance_id WHERE e.instance_id=?',(store.instance_id,)).fetchone()
            scope=json.loads(current['scope']);scope['tool_learning_runtime']={'contract':'TL-STRICT-RUNTIME-1','enabled':True,'ordinary_activity_caps':dict(ORDINARY_CAPS)}
            policy=store.insert('policy_versions',version=current['version']+1,mode=current['mode'],scope=scope,effective_at=utc(),authority=actor)
            store.db.execute('UPDATE policy_epochs SET policy_version_id=?,epoch=epoch+1 WHERE instance_id=?',(policy,store.instance_id))
        from digital_life.application.behavior.behavior_policy import BehaviorPolicy
        from digital_life.application.behavior.goal_regulation import GoalRegulation
        from digital_life.application.behavior.personality_growth import PersonalityGrowth
        from digital_life.application.behavior.habit_learning import HabitLearning
        from digital_life.application.behavior.people_relations import PeopleRelations
        from digital_life.application.memory.memory_quality import MemoryQuality
        from digital_life.application.autonomy.autonomy_agenda import AutonomyAgenda
        from digital_life.application.lifecycle.self_maintenance import SelfMaintenance
        for service in (BehaviorPolicy,GoalRegulation,PersonalityGrowth,HabitLearning,PeopleRelations,MemoryQuality,AutonomyAgenda,SelfMaintenance):
            service(store).configure(True,actor)
        from digital_life.application.runtime.configuration import configure_model
        configure_model(store,model_config,actor,check_available=False)
        return store
    except BaseException:
        if store is not None:store.close()
        raise
    finally:
        if control is not None:control.close()
