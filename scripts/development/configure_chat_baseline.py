"""Apply an explicitly approved neutral-profile baseline to a stopped native instance."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from digital_life.infrastructure.persistence.sqlite_store import Store
from digital_life.application.lifecycle.control_plane import Control
from digital_life.application.services.personality import Personality
from digital_life.application.behavior.people_relations import PeopleRelations
from digital_life.application.behavior.goal_regulation import GoalRegulation
from digital_life.application.behavior.behavior_policy import BehaviorPolicy
from digital_life.application.behavior.personality_growth import PersonalityGrowth
from digital_life.application.learning.runtime import strict_legacy_boundary
from digital_life.infrastructure.processes.dispatch_gate import dispatch_gate
from digital_life.domain.contracts import Conflict, Forbidden, dumps, sha


def apply(root, spec_path, approval_path):
    spec = json.loads(Path(spec_path).read_text())
    approval = json.loads(Path(approval_path).read_text())
    if spec.get('version') != 'chat-personality-v0.1' or spec.get('growth_enabled') is not False:
        raise Conflict('unsupported chat baseline')
    if approval.get('approved_spec_sha256') != sha(dumps(spec)) or approval.get('approved') is not True:
        raise Forbidden('explicit approval must bind the exact specification')
    s = Store(root)
    try:
        with dispatch_gate(s.root):
            strict_legacy_boundary(s, 'legacy_prepare')
            c = Control(s.root, s.instance_id)
            try:
                control = c.state()
                if not control['user_stopped'] or control['active_process_run_id']:
                    raise Conflict('stop the instance before configuring its chat baseline')
            finally:
                c.close()
            if PersonalityGrowth(s).config()['enabled']:
                raise Conflict('personality growth must remain disabled; review existing configuration')
            service = Personality(s)
            current = service.current()
            values = {r['name']: r['central_value'] for r in current['traits']}
            if set(spec['values']) != set(values):
                raise Conflict('complete existing trait set required')
            previous = s.db.execute("SELECT id FROM runtime_events WHERE instance_id=? AND event_type='chat_baseline.configured' ORDER BY event_seq DESC LIMIT 1", (s.instance_id,)).fetchone()
            if previous:
                event = s.row('runtime_events', previous[0])
                recorded = s.read_artifact(event['payload_artifact_id'])
                if recorded['spec_hash'] != sha(dumps(spec)) or values != spec['values']:
                    raise Conflict('baseline already configured differently; explicit review required')
            elif current['profile']['version'] != 0 or any(values.values()):
                raise Conflict('existing non-neutral or changed personality requires separate review')
            actor = s.config()['controller']
            with s.tx():
                if not previous:
                    # Two distinct configuration sources: proposal and controller approval.
                    # Neither is presented as a psychometric observation or learned experience.
                    refs = [s.evidence(artifact=s.artifact(value), method=method) for value, method in (
                        (spec, 'controller-configuration-proposal-not-observation'),
                        (approval, 'controller-configuration-approval-not-observation'))]
                    service.replace(spec['values'], refs, actor, expected_profile=current['profile']['id'])
                for module in (PeopleRelations(s), GoalRegulation(s), BehaviorPolicy(s)):
                    if not module.config()['enabled']:
                        module.configure(True, actor)
                if not previous:
                    s.event('chat_baseline.configured', payload={'spec_hash': sha(dumps(spec)), 'approval_hash': sha(dumps(approval)), 'personality_profile': service.current()['profile']['id'], 'growth_enabled': False}, lane='control')
            return {'instance_id': s.instance_id, 'values': spec['values'], 'modules': ['relationships', 'goal_regulation', 'behavior_policy'], 'growth_enabled': False, 'inference_started': False}
    finally:
        s.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--approval', required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.data, args.spec, args.approval), ensure_ascii=False))
