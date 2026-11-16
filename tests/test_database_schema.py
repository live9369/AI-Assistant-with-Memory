"""SQLite contract tests; no model or live tools are used."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('schema',ROOT/'scripts/development/build_database_schema.py')
schema=importlib.util.module_from_spec(spec); spec.loader.exec_module(schema)

class Fixture:
    def __init__(self,db,control=False):
        self.db=db; self.control=control
        self.tables={t[1]:t[3] for t in schema.schema_tables(schema.CONTROL if control else schema.SPEC)}
        self.ids={}; self.seq=0
        if not control:
            db.execute("INSERT INTO identity_instances(id,instance_id,state,generation) VALUES('life','life','active',0)")
            self.ids['identity_instances']='life'
    def insert(self,table,**overrides):
        self.seq+=1; row={'id':f'{table}-{self.seq}'}
        if not self.control: row['instance_id']='life'
        for key,typ,_ in self.tables[table]:
            if typ.startswith('?'): continue
            if typ.startswith('@'): row[key]=self.ensure(typ[1:])
            elif typ.startswith('e('): row[key]=typ[2:-1].split(',')[0]
            elif typ=='j': row[key]='{}'
            elif typ in ('i','i0'): row[key]=0
            elif typ=='b': row[key]=0
            elif typ in ('r','p','n'): row[key]=0.5
            else: row[key]='sample'
        if table=='personality_dimensions': row.update(scale_min=-1.,scale_max=1.)
        if table in schema.PROFILE_REV:
            row[schema.PROFILE_REV[table][0]]=self.insert('object_registry',kind=table+'-root')
        if table=='cognition_beliefs': row['literal']='"fact"'
        if table=='evidence_items': row['artifact_id']=self.ensure('artifacts')
        if table=='perception_quality_checks': row['signal_id']=self.ensure('perception_signals')
        if table=='cognition_assessment_outcomes': row['prediction_id']=self.ensure('cognition_predictions')
        if table=='working_memory_items': row.update(item_kind='temporary',content='new thought')
        if table=='commitment_conflict_members': row['commitment_id']=self.ensure('commitment_items')
        if table=='state_activity_snapshots': row['state_estimate_id']=self.ensure('state_estimates')
        if table=='decision_candidates': row.update(eligible=1,selected=1,selection_probability=1.)
        if table=='learning_feedback': row['description']='observed feedback'
        if table=='learning_update_commits' and 'new_revision_id' not in overrides:
            root=self.ensure('object_registry')
            seq=self.db.execute('SELECT coalesce(max(revision_no),-1)+1 FROM object_revision_registry WHERE object_id=?',(root,)).fetchone()[0]
            row['new_revision_id']=self.insert('object_revision_registry',revision_no=seq)
        if table=='deletion_effects': row['object_ref']=self.ensure('object_registry')
        if table in schema.TRANSITIONS:
            owner,parent,allowed=schema.TRANSITIONS[table]
            current=self.db.execute(f'SELECT state,state_revision FROM {parent} WHERE id=?',(row[owner],)).fetchone()
            row.update(from_state=current[0],to_state=allowed[current[0]][0],transition_no=current[1]+1)
        if table=='action_intents':
            candidate=self.db.execute('SELECT decision_id FROM decision_candidates WHERE id=?',(row['candidate_id'],)).fetchone()[0]
            self.db.execute("UPDATE decision_records SET state='finalized' WHERE id=?",(candidate,))
        row.update(overrides)
        self.db.execute(f'INSERT INTO {table} ({",".join(row)}) VALUES ({",".join("?" for _ in row)})',list(row.values()))
        self.ids.setdefault(table,row['id'])
        return row['id']
    def ensure(self,table):
        return self.ids.get(table) or self.insert(table)

class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.executescript((ROOT/'database/runtime.sql').read_text())
        self.f=Fixture(self.db)
    def tearDown(self): self.db.close()
    def rejected(self,fn):
        self.db.execute('SAVEPOINT bad')
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                fn()
                # Foreign keys are deferred: inspect and force a failure in test scope.
                if self.db.execute('PRAGMA foreign_key_check').fetchall():
                    raise sqlite3.IntegrityError('deferred foreign key')
        finally:
            self.db.execute('ROLLBACK TO bad'); self.db.execute('RELEASE bad')
    def test_every_runtime_table_accepts_valid_connected_fixture(self):
        # Edges representing cycles or transition history need specific fixtures.
        edges={'identity_lineage','evidence_derivations','cognition_plan_dependencies'}
        for _,table,_,_ in schema.schema_tables(schema.SPEC):
            if table not in edges: self.f.ensure(table)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.db.commit()
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_schema_covers_architecture_tables(self):
        import re
        text=(ROOT/'docs/research/phase-2-database-architecture.md').read_text()
        listed=set()
        for line in text.splitlines():
            if line.startswith('| `'): listed.update(re.findall(r'`([a-z][a-z0-9_]+)`',line.split('|')[1]))
        names=set(self.f.tables)|{t[1] for t in schema.parse(schema.CONTROL)}
        # Public field names are also in architecture tables, remove those.
        fields={'id','instance_id','created_at','recorded_at','occurred_at','received_at','valid_from','valid_to','revision_no','activity_id','caused_by_event_id','schema_version','status'}
        self.assertEqual(listed-names-fields,set())
    def test_probability_json_enum_and_boolean(self):
        self.f.ensure('personality_states')
        for field,value in [('value_origin','imaginary')]:
            self.rejected(lambda:self.db.execute(f'UPDATE personality_states SET {field}=?',(value,)))
        habit=self.f.ensure('habit_items')
        self.rejected(lambda:self.db.execute('UPDATE habit_items SET response_template=? WHERE id=?',('not-json',habit)))
        self.f.ensure('decision_candidates')
        self.rejected(lambda:self.db.execute('UPDATE decision_candidates SET selection_probability=1.1'))
        self.rejected(lambda:self.db.execute('UPDATE decision_candidates SET selected=2'))
    def test_instance_scope_and_real_deferred_commit(self):
        self.db.execute("INSERT INTO identity_instances(id,instance_id,state,generation) VALUES('other','other','active',0)")
        ch=self.f.ensure('perception_channels'); art=self.f.ensure('artifacts'); self.db.commit()
        self.db.execute('BEGIN')
        self.db.execute("INSERT INTO perception_signals(id,instance_id,channel_id,artifact_id,received_at) VALUES('bad','other',?,?,'now')",(ch,art))
        with self.assertRaises(sqlite3.IntegrityError): self.db.commit()
        self.db.rollback()
    def test_revision_belongs_to_same_object(self):
        a=self.f.ensure('memory_items'); b=self.f.insert('memory_items')
        rev=self.f.insert('memory_revisions',memory_id=a)
        self.rejected(lambda:self.db.execute('UPDATE memory_items SET current_revision_id=? WHERE id=?',(rev,b)))
        self.db.execute('UPDATE memory_items SET current_revision_id=? WHERE id=?',(rev,a))
        self.rejected(lambda:self.db.execute('UPDATE memory_revisions SET content=? WHERE id=?',('silently changed',rev)))
        self.db.commit()
    def test_memory_multiple_axes_and_working_memory(self):
        mem=self.f.ensure('memory_items')
        self.f.insert('memory_classifications',memory_id=mem,axis='content',label='episodic')
        self.f.insert('memory_classifications',memory_id=mem,axis='self_relation',label='autobiographical')
        self.f.ensure('working_memory_items')
        self.rejected(lambda:self.f.insert('working_memory_items',item_kind='reference',content='both',object_revision_ref=self.f.ensure('object_revision_registry')))
    def test_cycles_insert_and_update(self):
        for table,start,end,target in [('evidence_derivations','derived_evidence_id','parent_evidence_id','evidence_items'),('cognition_plan_dependencies','step_id','depends_on_step_id','cognition_plan_steps')]:
            a=self.f.ensure(target); b=self.f.insert(target)
            edge=self.f.insert(table,**{start:a,end:b})
            self.rejected(lambda:self.f.insert(table,**{start:b,end:a}))
            self.rejected(lambda:self.db.execute(f'UPDATE {table} SET {end}={start} WHERE id=?',(edge,)))
    def test_lineage_cross_instance_and_cycle(self):
        self.db.execute("INSERT INTO identity_instances(id,instance_id,state,generation) VALUES('child','child','active',1)")
        self.f.insert('identity_lineage',parent_instance_id='life',child_instance_id='child')
        self.rejected(lambda:self.f.insert('identity_lineage',parent_instance_id='child',child_instance_id='life'))
    def test_habit_owner(self):
        self.f.ensure('habit_associations'); other=self.f.insert('habit_items')
        self.rejected(lambda:self.db.execute('UPDATE habit_associations SET habit_id=?',(other,)))
    def test_goal_commitment_intention_state_transitions(self):
        for table,(owner,parent,allowed) in schema.TRANSITIONS.items():
            key=self.f.ensure(parent)
            self.rejected(lambda:self.db.execute(f"UPDATE {parent} SET state='completed' WHERE id=?",(key,)))
            transition=self.f.insert(table)
            current=self.db.execute(f'SELECT state,state_revision FROM {parent} WHERE id=?',(key,)).fetchone()
            self.assertEqual(current[1],1)
            self.rejected(lambda:self.db.execute(f'UPDATE {table} SET reason_ref=id' if table=='intention_transitions' else f'UPDATE {table} SET reason=\'rewrite\''))
            self.rejected(lambda:self.f.insert(table,from_state='proposed',to_state='violated',transition_no=1))
    def test_decision_finalize_and_blocked_candidate(self):
        candidate=self.f.ensure('decision_candidates')
        self.rejected(lambda:self.db.execute('UPDATE decision_candidates SET eligible=0 WHERE id=?',(candidate,)))
        self.db.execute('UPDATE decision_candidates SET selection_probability=0.2')
        self.rejected(lambda:self.db.execute("UPDATE decision_records SET state='finalized'"))
        self.db.execute('UPDATE decision_candidates SET selection_probability=1')
        self.db.execute("UPDATE decision_records SET state='finalized'")
        self.rejected(lambda:self.db.execute('UPDATE decision_candidates SET score=99'))
        self.rejected(lambda:self.db.execute("UPDATE decision_records SET state='draft'"))
    def test_null_denominator_unknown_results_and_lease(self):
        sample=self.f.ensure('metric_samples')
        self.rejected(lambda:self.db.execute('UPDATE metric_samples SET denominator=0,value=1 WHERE id=?',(sample,)))
        self.db.execute('UPDATE metric_samples SET denominator=0,value=NULL WHERE id=?',(sample,))
        self.f.ensure('action_results'); self.db.execute("UPDATE action_results SET state='unknown'")
        job=self.f.ensure('jobs')
        self.rejected(lambda:self.db.execute("UPDATE jobs SET state='leased' WHERE id=?",(job,)))
        self.db.execute("UPDATE jobs SET state='leased',lease_owner='worker',lease_expiry='later' WHERE id=?",(job,))
    def test_restart_and_full_connected_dataflow(self):
        for table in ['perception_observation_revisions','memory_revisions','cognition_belief_revisions','cognition_predictions','commitment_goal_links','action_results','action_effects','learning_update_commits','maintenance_verifications','self_narrative_sources','checkpoints']:
            self.f.ensure(table)
        # Unknown remote result survives restart; no automatic repeat is implied.
        self.db.execute("UPDATE action_results SET state='unknown'")
        self.db.commit()
        with tempfile.TemporaryDirectory() as tmp:
            target=sqlite3.connect(str(Path(tmp)/'restored.sqlite'))
            self.db.backup(target); target.close()
            restored=sqlite3.connect(str(Path(tmp)/'restored.sqlite'))
            restored.execute('PRAGMA foreign_keys=ON')
            self.assertEqual(restored.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(restored.execute('SELECT state FROM action_results').fetchone()[0],'unknown')
            self.assertEqual(restored.execute('SELECT count(*) FROM commitment_items').fetchone()[0],1)
            restored.close()
    def test_supervisor_is_separate_and_valid(self):
        db=sqlite3.connect(':memory:'); db.executescript((ROOT/'database/supervisor.sql').read_text())
        f=Fixture(db,control=True)
        for table in f.tables: f.ensure(table)
        db.commit(); self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertFalse(any(row[2]=='identity_instances' for row in db.execute('PRAGMA foreign_key_list(process_runs)')))
        db.close()

    def test_all_typed_columns_and_foreign_keys_reject_bad_values(self):
        # Reuse the all-table fixture, then mutate each constrained field in isolation.
        self.test_every_runtime_table_accepts_valid_connected_fixture()
        for _,table,_,fields in schema.schema_tables(schema.SPEC):
            row=self.db.execute(f'SELECT id FROM {table} LIMIT 1').fetchone()
            if not row: continue
            for key,typ,_ in fields:
                kind=typ.lstrip('?'); bad=None
                if kind.startswith('@'): bad='missing-foreign-object'
                elif kind.startswith('e('): bad='invalid-enum'
                elif kind=='j': bad='invalid-json'
                elif kind=='p': bad=1.01
                elif kind in ('i','i0','n'): bad=-1
                elif kind=='b': bad=2
                if bad is None: continue
                with self.subTest(table=table,field=key):
                    self.rejected(lambda:self.db.execute(f'UPDATE {table} SET {key}=? WHERE id=?',(bad,row[0])))

    def test_all_business_unique_indexes(self):
        self.test_every_runtime_table_accepts_valid_connected_fixture()
        self.db.row_factory=sqlite3.Row
        for _,table,_,_ in schema.schema_tables(schema.SPEC):
            row=self.db.execute(f'SELECT * FROM {table} LIMIT 1').fetchone()
            if row is None: continue
            indexes=list(self.db.execute(f'PRAGMA index_list({table})'))
            for index in indexes:
                if not index['unique']: continue
                keys=[r['name'] for r in self.db.execute(f'PRAGMA index_info("{index["name"]}")')]
                if 'id' in keys or any(row[k] is None for k in keys): continue
                clone=dict(row); clone['id']='duplicate-'+table
                with self.subTest(table=table,index=index['name']):
                    self.rejected(lambda:self.db.execute(f'INSERT INTO {table} ({",".join(clone)}) VALUES ({",".join("?" for _ in clone)})',list(clone.values())))

    def test_learning_update_and_compensating_reversal(self):
        mem=self.f.ensure('memory_items')
        old=self.f.insert('memory_revisions',memory_id=mem,revision_no=1,content='old belief')
        new=self.f.insert('memory_revisions',memory_id=mem,revision_no=2,content='corrected belief')
        proposal=self.f.insert('learning_update_proposals',target_object_id=mem,state='accepted')
        commit=self.f.insert('learning_update_commits',proposal_id=proposal,old_revision_id=old,new_revision_id=new)
        self.db.execute('UPDATE memory_items SET current_revision_id=? WHERE id=?',(new,mem))
        unrelated=self.f.insert('memory_items')
        bad=self.f.insert('memory_revisions',memory_id=unrelated,revision_no=1)
        self.rejected(lambda:self.f.insert('learning_update_commits',proposal_id=proposal,old_revision_id=old,new_revision_id=bad))
        undo_proposal=self.f.insert('learning_update_proposals',target_object_id=mem,state='accepted')
        reverted=self.f.insert('memory_revisions',memory_id=mem,revision_no=3,content='old belief')
        self.f.insert('learning_update_commits',proposal_id=undo_proposal,old_revision_id=new,new_revision_id=reverted,reversal_of=commit)
        self.db.execute('UPDATE memory_items SET current_revision_id=? WHERE id=?',(reverted,mem))
        self.db.commit()
        self.assertEqual(self.db.execute('SELECT count(*) FROM memory_revisions WHERE memory_id=?',(mem,)).fetchone()[0],3)

    def test_redaction_propagates_to_fts_without_rewriting_identity(self):
        rev=self.f.insert('memory_revisions',content='secrettoken')
        self.assertEqual(self.db.execute("SELECT count(*) FROM memory_search WHERE memory_search MATCH 'secrettoken'").fetchone()[0],1)
        request=self.f.insert('deletion_requests',state='cleaning')
        self.f.insert('deletion_effects',request_id=request,object_ref=rev,operation='redact')
        self.db.execute("UPDATE memory_revisions SET content='[redacted]' WHERE id=?",(rev,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM memory_search WHERE memory_search MATCH 'secrettoken'").fetchone()[0],0)
        # Normalized identity and owner cannot be changed during redaction.
        self.rejected(lambda:self.db.execute('UPDATE memory_revisions SET id=? WHERE id=?',('other-id',rev)))
        self.db.commit()

    def test_transaction_rollback_removes_half_created_state(self):
        self.f.ensure('goal_items'); self.db.commit()
        self.db.execute('BEGIN')
        before=self.db.execute('SELECT count(*) FROM object_registry').fetchone()[0]
        self.f.insert('goal_items',id='temporary-goal')
        self.db.rollback()
        self.assertEqual(self.db.execute("SELECT count(*) FROM goal_items WHERE id='temporary-goal'").fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM object_registry').fetchone()[0],before)

    def test_trait_scale_and_goal_batch_normalization(self):
        state=self.f.ensure('personality_states')
        self.rejected(lambda:self.db.execute('UPDATE personality_states SET value=2 WHERE id=?',(state,)))
        self.f.ensure('goal_activation_records')
        self.rejected(lambda:self.db.execute("UPDATE goal_activation_batches SET state='finalized'"))
        self.db.execute('UPDATE goal_activation_records SET probability=1,selected=1')
        self.db.execute("UPDATE goal_activation_batches SET state='finalized'")
        self.rejected(lambda:self.db.execute('UPDATE goal_activation_records SET score=5'))

    def test_plan_dependency_cannot_cross_plan(self):
        a=self.f.ensure('cognition_plan_steps')
        otherplan=self.f.insert('cognition_plans',version=1)
        b=self.f.insert('cognition_plan_steps',plan_id=otherplan)
        self.rejected(lambda:self.f.insert('cognition_plan_dependencies',step_id=a,depends_on_step_id=b))

if __name__=='__main__': unittest.main(verbosity=2)
