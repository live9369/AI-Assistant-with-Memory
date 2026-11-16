"""Approved expand-only migrations; release rollback never rewinds life history."""
from digital_life.domain.contracts import sha,dumps,utc,ContractError,Forbidden,identifier

V3=[
 'CREATE INDEX ix_metrics_by_run ON metric_samples(instance_id,run_id,definition_id)',
 'CREATE INDEX ix_events_by_type ON runtime_events(instance_id,event_type,event_seq)',
 '''CREATE TABLE module_checkpoints (
   instance_id TEXT NOT NULL, module_name TEXT NOT NULL, cursor INTEGER NOT NULL CHECK(cursor>=0),
   updated_at TEXT NOT NULL, PRIMARY KEY(instance_id,module_name),
   FOREIGN KEY(instance_id) REFERENCES identity_instances(id)) STRICT''',
]

def migrate(store,actor,target=3):
    if actor!=store.config()['controller']: raise Forbidden('controller required')
    from digital_life.application.lifecycle.control_plane import Control
    control=Control(store.root,store.instance_id)
    try:
        state=control.state()
        if not state['user_stopped'] or state['active_process_run_id']: raise Forbidden('stop runtime before migration')
    finally: control.close()
    version=store.db.execute('PRAGMA user_version').fetchone()[0]; checksum=sha(dumps(V3))
    if version==target:
        prior=store.db.execute('SELECT checksum FROM schema_migrations WHERE instance_id=? AND version=?',(store.instance_id,target)).fetchone()
        if target==3 and (not prior or prior[0]!=checksum): raise ContractError('migration checksum mismatch')
        return {'version':version,'already_applied':True}
    if version!=2 or target!=3: raise ContractError('no approved migration path; database downgrade refused')
    backup=store.snapshot(store.root/'snapshots'/('pre-schema-3-'+identifier()+'.sqlite'))
    with store.tx():
        for statement in V3: store.db.execute(statement)
        store.insert('schema_migrations',version=3,checksum=checksum,applied_at=utc(),release_id='schema-expand-v3')
        store.db.execute('PRAGMA user_version=3')
        store.event('schema.expanded',payload={'from':2,'to':3,'checksum':checksum,'backup':backup,'backward_compatible':True},lane='control')
        if store.integrity()['foreign_keys']: raise ContractError('migration foreign key failure')
    return {'version':3,'checksum':checksum,'snapshot':backup,'data_rewound':False}
