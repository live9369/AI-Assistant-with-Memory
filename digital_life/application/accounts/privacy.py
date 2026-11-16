"""Evidence-preserving redaction within explicitly managed storage scope.

This cannot erase files exported to third parties or guarantee SSD forensic erasure.
Unregistered backups are never searched or modified.
"""
import json
from pathlib import Path
import sqlite3
from digital_life.domain.contracts import Forbidden,Conflict,ContractError,dumps,sha,utc
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate,coordinated

CONTENT_COLUMNS={'content','task','question','query','reconstructed_content','attributes_json','proposed_change','predicted_outcome','action_template','response_template','reason','original_feedback','feedback_content'}

def replace_content(value,secrets):
    if isinstance(value,str):
        for secret in secrets:
            if secret: value=value.replace(secret,'[redacted]')
        return value
    if isinstance(value,list): return [replace_content(v,secrets) for v in value]
    if isinstance(value,dict): return {k:replace_content(v,secrets) for k,v in value.items()}
    return value

class Privacy:
    def __init__(self,store): self.s=store
    @coordinated
    def erase(self,memory,actor,include_registered_backups=False):
        from digital_life.application.learning.runtime import legacy_protection_present
        if legacy_protection_present(self.s):raise Forbidden('protected source cleanup requires the current M12 plan; legacy erasure is blocked')
        if actor!=self.s.config()['controller']: raise Forbidden('controller required')
        from digital_life.application.lifecycle.control_plane import Control
        control=Control(self.s.root,self.s.instance_id)
        try:
            state=control.state()
            if not state['user_stopped'] or state['active_process_run_id']: raise Conflict('stop runtime before storage erasure')
        finally: control.close()
        self.s.row('memory_items',memory)
        affected={memory}
        while True:
            extra={r['from_memory_id'] for r in self.s.rows('memory_relations') if r['relation_type'] in ('derived_from','summary_of','consolidated_from') and r['to_memory_id'] in affected}
            if extra<=affected: break
            affected|=extra
        secrets=[r['content'] for r in self.s.rows('memory_revisions') if r['memory_id'] in affected and r['content']!='[redacted]']
        if not secrets: raise Conflict('memory already redacted; use existing deletion verification')
        backups=[]; snapshots=[]
        if include_registered_backups:
            folder=self.s.root/'snapshots'
            if folder.is_symlink(): raise ContractError('unsafe managed snapshot directory')
            for snapshot in folder.glob('*.sqlite'):
                if snapshot.is_symlink(): raise ContractError('unsafe managed snapshot')
                raw=snapshot.read_bytes()
                if any(secret.encode() in raw or dumps(secret)[1:-1].encode() in raw for secret in secrets): snapshots.append(snapshot)
            for event in self.s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type='backup.created'",(self.s.instance_id,)):
                backup=Path(self.s.read_artifact(event[0])['path'])
                if backup.is_symlink() or not backup.is_dir(): raise ContractError('registered backup unavailable; deletion not complete')
                manifest=json.loads((backup/'manifest.json').read_text())
                if manifest['instance_id']!=self.s.instance_id: raise ContractError('backup identity mismatch')
                for name,digest in manifest['files'].items():
                    path=backup/name
                    if path.is_symlink() or backup.resolve() not in path.resolve().parents or sha(path.read_bytes())!=digest: raise ContractError('backup integrity mismatch')
                backups.append(backup)
        request=self._clean(self.s,affected,secrets,actor)
        for backup in backups:
            copy=Store(backup)
            try:
                copy_request=self._clean(copy,affected,secrets,copy.config()['controller'])
                with copy.tx(): copy.db.execute("UPDATE deletion_requests SET state='verified' WHERE id=?",(copy_request,))
                self._compact(copy)
            finally: copy.close()
            manifest=json.loads((backup/'manifest.json').read_text())
            manifest['files']={str(path.relative_to(backup)):sha(path.read_bytes()) for path in [backup/'runtime.sqlite']+list((backup/'blobs').iterdir()) if path.is_file()}
            manifest['redaction_applied_at']=utc()
            (backup/'manifest.json').write_text(dumps(manifest))
        for snapshot in snapshots: snapshot.unlink()
        with self.s.tx():
            self.s.db.execute("UPDATE deletion_requests SET state='verified' WHERE id=?",(request,))
            self.s.event('privacy.erasure_verified',payload={'request':request,'memories':sorted(affected),'backups':list(map(str,backups)),
                'purged_managed_snapshots':list(map(str,snapshots)),
                'scope':'live database, referenced blobs and explicitly included registered backups','external_copies_erased':False,'forensic_erasure_claimed':False},lane='control')
        self._compact(self.s)
        return {'request':request,'state':'verified','managed_memories':len(affected),'managed_backups':len(backups),'managed_snapshots':len(snapshots),'external_copies_erased':False}
    @staticmethod
    def _compact(store):
        store.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        store.db.execute('VACUUM')
        store.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    def _clean(self,store,memories,secrets,actor):
        store.db.execute('PRAGMA secure_delete=ON'); old_blobs=[]
        with dispatch_gate(store.root),store.tx():
            request=store.insert('deletion_requests',subject_scope={'memories':sorted(memories),'scope':'managed-storage'},requested_at=utc(),authority_ref=actor,state='cleaning')
            revisions={r['id'] for r in store.rows('memory_revisions') if r['memory_id'] in memories}
            origins=set(revisions)
            for link in store.rows('memory_source_links'):
                if link['memory_revision_id'] in revisions:
                    origin=store.row('evidence_items',link['evidence_id'])['origin_object_id']
                    if origin:origins.add(origin)
            activities={a['id'] for a in store.rows('activities') if a['trigger_event_id'] in origins}
            requests={r['request_id'] for r in store.rows('thought_request_inputs') if r['object_revision_id'] in revisions}
            requests.update(r['id'] for r in store.rows('thought_requests') if r['activity_id'] in activities)
            results=[r for r in store.rows('thought_results') if r['request_id'] in requests or r['id'] in origins]
            requests.update(r['request_id'] for r in results)
            results=[r for r in store.rows('thought_results') if r['request_id'] in requests]
            origins.update(r['id'] for r in results)
            forced_artifacts={r['request_artifact_id'] for r in store.rows('thought_requests') if r['id'] in requests}
            forced_artifacts.update(ref for r in results for ref in (r['response_artifact_id'],r['parsed_artifact_id']) if ref)
            # A response need not be accepted or quote the source verbatim to be a known dependent.
            cognitive={link['target_revision_id'] for link in store.rows('cognition_evidence_links') if store.row('evidence_items',link['evidence_id'])['origin_object_id'] in origins}
            for revision in cognitive:
                row=store.row('cognition_belief_revisions',revision)
                store.insert('deletion_effects',request_id=request,object_ref=revision,operation='redact',result='pending')
                store.db.execute('UPDATE cognition_belief_revisions SET content=? WHERE id=?',(dumps({'redacted_by':request}),revision))
                belief=store.row('cognition_beliefs',row['belief_id'])
                if belief['current_revision_id']==revision:
                    store.insert('deletion_effects',request_id=request,object_ref=belief['id'],operation='redact',result='pending')
                    store.db.execute('UPDATE cognition_beliefs SET literal=? WHERE id=?',(dumps({'redacted_by':request}),belief['id']))
            for table,columns in store.columns.items():
                if 'id' not in columns or 'instance_id' not in columns: continue
                for column in columns & CONTENT_COLUMNS:
                    for row in store.db.execute('SELECT id,'+column+' FROM '+table+' WHERE instance_id=?',(store.instance_id,)).fetchall():
                        raw=row[1]
                        if not isinstance(raw,str) or not any(secret in raw or dumps(secret)[1:-1] in raw for secret in secrets): continue
                        try: parsed=json.loads(raw); replacement=dumps(replace_content(parsed,secrets))
                        except (ValueError,TypeError): replacement=replace_content(raw,secrets)
                        if replacement==raw: continue
                        store.insert('deletion_effects',request_id=request,object_ref=row['id'],operation='redact',result='pending')
                        store.db.execute('UPDATE '+table+' SET '+column+'=? WHERE id=?',(replacement,row['id']))
            protected={r['artifact_ref'] for table in ('configuration_versions','model_versions') for r in store.rows(table)}
            for artifact in store.rows('artifacts'):
                try: value=store.read_artifact(artifact['id'])
                except (OSError,ValueError): continue
                changed=replace_content(value,secrets)
                if changed==value and artifact['id'] not in forced_artifacts: continue
                if artifact['id'] in protected: raise ContractError('requested text also occurs in protected configuration; explicit configuration redaction is required first')
                # Entire source artifact is tombstoned; remaining consumers must rebuild.
                tombstone=store.artifact({'redacted_by':request})
                replacement=store.row('artifacts',tombstone)
                store.insert('deletion_effects',request_id=request,artifact_ref=artifact['id'],operation='purge',result='done',verified_at=utc())
                old_blobs.append(artifact['storage_ref'])
                store.db.execute('UPDATE artifacts SET hash=?,size=?,media_type=?,storage_ref=? WHERE id=?',(replacement['hash'],replacement['size'],replacement['media_type'],replacement['storage_ref'],artifact['id']))
            for memory in memories: store.db.execute("UPDATE memory_items SET state='deleted' WHERE instance_id=? AND id=?",(store.instance_id,memory))
            # FTS delete markers retain old token segments until the index is rebuilt.
            if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='memory_search' AND type='table'").fetchone():
                store.db.execute("INSERT INTO memory_search(memory_search) VALUES('rebuild')")
            # Invalidate all active work; redacted requests must never be reused.
            from digital_life.application.runtime.engine import Engine
            for activity in store.rows('activities'):
                if activity['state'] not in ('completed','failed','cancelled'): Engine(store).cancel(activity['id'],actor)
            store.db.execute("UPDATE deletion_effects SET result='done',verified_at=? WHERE request_id=?",(utc(),request))
        from digital_life.application.memory.memory_quality import MemoryQuality
        MemoryQuality.drop_index(store.root)
        for name in old_blobs:
            if not store.db.execute('SELECT 1 FROM artifacts WHERE storage_ref=?',(name,)).fetchone():
                path=store.root/'blobs'/name
                if path.parent!=store.root/'blobs' or path.is_symlink(): raise ContractError('unsafe blob deletion path')
                path.unlink(missing_ok=True)
        self._compact(store)
        return request
