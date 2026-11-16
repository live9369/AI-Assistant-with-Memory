"""Current-build re-execution of all inherited G1 entities; synthetic only.

Does not call the historical CLI's formal_guard or read any formal directory.
Historical frozen baselines remain historical, not current code equality gates.
"""
import json
from pathlib import Path
import socket
import tempfile
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def run_g1(case_spec):
    from evaluation.exploration.harness import Harness
    from evaluation.exploration.scenarios import material_smoke, mechanism, stop_matrix
    cases = json.loads((ROOT / 'evaluation/exploration/materials/cases-v1.json').read_text())['cases']
    material = case_spec['kind'] == 'g1_material'
    spec = None if material else case_spec['legacy_spec']
    case_id = case_spec['legacy_case_id'] if material else spec['case_id']
    case = next(c for c in cases if c['case_id'] == case_id)
    with tempfile.TemporaryDirectory(prefix='im19-g1-') as folder:
        root = Path(folder) / 'instance'
        h = None; error = None; snapshot = None; artifacts = None; audit = None
        try:
            with patch.object(socket, 'socket', side_effect=RuntimeError('network forbidden for deterministic G1')):
                h = Harness(root, case)
                if material:
                    material_smoke(h)
                elif spec['kind'] == 'mechanism':
                    mechanism(h, spec['operation'])
                else:
                    stop_matrix(h, spec)
                h.check(h.s.integrity() == {'integrity': 'ok', 'foreign_keys': []}, 'sqlite-integrity')
        except BaseException:
            error = traceback.format_exc()
        finally:
            if h:
                try:
                    export = Path(folder) / 'export'
                    audit = h.export(export)
                    snapshot = json.loads((export / 'snapshot.json').read_text())
                    artifacts = json.loads((export / 'artifacts.json').read_text())
                finally:
                    h.close()
        result = {'case_id': case_spec['id'], 'legacy_case_id': case_id, 'input': case,
            'legacy_spec': spec, 'status': 'pass' if error is None else 'fail', 'error': error,
            'assertions': h.assertions if h else [], 'trace': h.trace_events if h else [],
            'audit': audit, 'snapshot': snapshot, 'artifacts': artifacts,
            'real_model_called': False, 'formal_instance_accessed': False,
            'historical_failures_replaced': False, 'build': 'current-workspace',
            'endpoint': case_spec['expected_endpoint'] if error is None else None}
    result['temporary_scope_removed'] = not root.exists()
    return result
