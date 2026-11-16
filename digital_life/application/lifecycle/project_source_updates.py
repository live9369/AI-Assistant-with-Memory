"""Bind authorized project edit receipts to immutable source proposals only."""
import json
from pathlib import Path
from digital_life.domain.contracts import ContractError, Forbidden, Conflict, sha
from digital_life.application.lifecycle.project_access import ProjectAccess
from digital_life.application.lifecycle.control_plane import Control, Releases
from digital_life.infrastructure.tools.project_versions import Versions


def capture(updates, intent, outcome):
    s = updates.s
    row = s.row('action_intents', intent)
    name = s.row('tool_definitions', row['tool_id'])['name']
    if name not in ('project_write', 'project_edit'): return None
    args = json.loads(row['arguments_json']); path = args['path']
    if not path.startswith('digital_life/'): return None
    if any(e.get('result') == outcome['result'] for e in updates.events('captured')): return None
    try:
        canonical = s.row('action_results', outcome['result'])
        attempt = s.row('action_attempts', canonical['attempt_id'])
        if attempt['intent_id'] != intent or canonical['state'] != 'succeeded' or canonical['receipt_artifact_id'] != outcome['receipt'] or canonical['outcome_ref'] != outcome['evidence']: raise Forbidden('source receipt mismatch')
        receipt = s.read_artifact(canonical['receipt_artifact_id']); data = receipt.get('evidence', {})
        if receipt.get('verification') != 'pass' or data.get('path') != path: raise Forbidden('source edit not verified')
        scope = json.loads(row['resource_scope']); ProjectAccess(s).check(name, scope)
        if 'project_version_save' not in scope['tools'] or not data.get('version'): raise Forbidden('source update needs immutable project version')
        decision = s.row('decision_candidates', row['candidate_id'])['decision_id']
        activity = s.row('decision_records', decision)['activity_id']
        lineage = None
        for event in s.db.execute("SELECT payload_artifact_id FROM runtime_events WHERE instance_id=? AND activity_id=? AND event_type='thought.accepted' ORDER BY event_seq DESC", (s.instance_id, activity)):
            value = s.read_artifact(event[0])
            if value.get('decision') == decision: lineage = value; break
        if lineage is None: raise Forbidden('source proposal lacks accepted thought')
        result = s.row('thought_results', lineage['result']); request = s.row('thought_requests', lineage['request'])
        if result['request_id'] != request['id'] or result['acceptance'] != 'accepted' or request['accepted_result_id'] != result['id']: raise Forbidden('source thought not accepted')
        packet = s.read_artifact(request['request_artifact_id'])
        active = updates.active()
        if not active or packet.get('self_maintenance', {}).get('base_deployment') != active['id']: raise Conflict('edit thought pinned to a different deployment')
        repo = Versions(scope, s.root/'project-operations')
        with repo.locked():
            version = repo.revision(data['version']); raw = repo.content(repo.tree(version), path)
        if sha(raw) != data.get('sha256') or data.get('before_sha256') != (args['expected_sha256'] or None): raise Forbidden('edit version hash mismatch')
        control = Control(s.root, s.instance_id)
        try:
            base = Releases(control).verify(active['id']) / path
            before = sha(base.read_bytes()) if base.is_file() else None
        finally: control.close()
        if before != data.get('before_sha256'): raise Conflict('working draft does not match deployed source baseline')
        proposal = updates.propose(active['id'], {path: raw.decode('utf-8')},
            '已核验项目源码修改，等待CLI构建和验收：'+path, 'action:'+intent, s.config()['controller'],
            source={'request': request['id'], 'thought_result': result['id'], 'intent': intent,
                    'result': outcome['result'], 'evidence': outcome['evidence'], 'path': path,
                    'project_version': version, 'sha256': sha(raw), 'before_sha256': before})
        updates.emit('captured', {'result': outcome['result'], 'proposal': proposal['id'], 'method': 'project-version-v1'}, activity)
        return proposal
    except (ContractError, OSError, ValueError, TypeError, SyntaxError) as error:
        updates.emit('captured', {'result': outcome['result'], 'rejected': True, 'reason': type(error).__name__, 'detail': str(error)[:240], 'method': 'project-version-v1'})
        return {'rejected': True}
