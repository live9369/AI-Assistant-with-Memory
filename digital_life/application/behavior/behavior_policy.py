"""Versioned contextual behavior probabilities. Engineering priors, not psychology."""
import json
import math
import secrets
from digital_life.domain.contracts import ContractError, Conflict, Forbidden, dumps, validate_action
from digital_life.infrastructure.processes.dispatch_gate import coordinated
from digital_life.application.services.decisions import Decisions

TOOLS = ('read_file', 'write_note', 'list_files', 'wait', 'ask')
BASE = ('proposed', 'cost', 'habit', 'memory.coverage', 'cognition.uncertainty', 'relationship.reliability', 'motivation.intensity', 'state.load', 'context.chat', 'context.task_loop', 'context.internal')


def sample(probabilities, draw):
    if isinstance(draw, bool) or not isinstance(draw, (int, float)) or not math.isfinite(draw) or not 0 <= draw < 1:
        raise ContractError('draw must be in [0,1)')
    if not probabilities or any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or p < 0 for p in probabilities) or not math.isclose(sum(probabilities), 1, abs_tol=1e-12):
        raise ContractError('normalized probabilities required')
    total = 0
    for i, p in enumerate(probabilities):
        total += p
        if p > 0 and draw < total: return i
    return max(i for i, p in enumerate(probabilities) if p > 0)


class BehaviorPolicy:
    def __init__(self, store): self.s = store

    def dimensions(self):
        return BASE + tuple('personality.'+r['name'] for r in self.s.rows('personality_dimensions')) + tuple('value.'+r['definition'] for r in self.s.rows('value_dimensions'))

    def defaults(self):
        weights = {tool: {'proposed': 1.5, 'cost': -.3, 'habit': 1.} for tool in TOOLS}
        weights['read_file'].update({'personality.openness': .3, 'value.exploration': .4, 'memory.coverage': -.2})
        weights['list_files'].update({'personality.openness': .3, 'value.exploration': .4})
        weights['write_note'].update({'personality.conscientiousness': .3, 'value.continuity': .4, 'motivation.intensity': .3})
        weights['ask'].update({'personality.extraversion': .2, 'cognition.uncertainty': .8, 'relationship.reliability': .2, 'context.chat': .2})
        weights['wait'].update({'state.load': .8, 'context.internal': .1})
        return {'enabled': False, 'temperature': .7, 'biases': {}, 'weights': weights, 'event_id': None, 'version': 'contextual-softmax-v1'}

    def config(self):
        row = self.s.db.execute("SELECT id,payload_artifact_id FROM runtime_events WHERE instance_id=? AND event_type='behavior_policy.configured' ORDER BY event_seq DESC LIMIT 1", (self.s.instance_id,)).fetchone()
        return dict(self.s.read_artifact(row['payload_artifact_id']), event_id=row['id']) if row else self.defaults()

    @coordinated
    def configure(self, enabled, actor, temperature=.7, parameters=None):
        if actor != self.s.config()['controller']: raise Forbidden('controller required')
        if type(enabled) is not bool: raise ContractError('boolean enabled required')
        def finite(value, low, high):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ContractError('finite bounded parameter required')
        finite(temperature, .05, 5)
        parameters = {} if parameters is None else parameters
        if not isinstance(parameters, dict) or set(parameters)-{'biases','weights'}: raise ContractError('unknown behavior parameters')
        cfg = self.defaults(); cfg.update(enabled=enabled, temperature=temperature, actor=actor)
        for field in ('biases','weights'):
            values = parameters.get(field, {})
            if not isinstance(values, dict) or set(values)-set(TOOLS): raise ContractError('unknown tool parameters')
            for tool, value in values.items():
                if field == 'biases': finite(value, -20, 20); cfg[field][tool] = value
                else:
                    if not isinstance(value, dict) or set(value)-set(self.dimensions()): raise ContractError('unknown feature')
                    for coefficient in value.values(): finite(coefficient, -20, 20)
                    cfg[field][tool].update(value)
        from digital_life.application.lifecycle.control_plane import Control
        control = Control(self.s.root, self.s.instance_id)
        try:
            state = control.state()
            if not state['user_stopped'] or state['active_process_run_id']: raise Conflict('stop before behavior configuration')
        finally: control.close()
        cfg.pop('event_id')
        with self.s.tx(): self.s.event('behavior_policy.configured', payload=cfg, lane='control')
        return self.config()

    def context(self, activity, payload):
        cfg = self.config()
        if not cfg['enabled']: return None
        if payload.get('exploration'): return {'configuration': cfg['event_id'], 'bypass': 'V2 exploration retains dedicated verified selection'}
        features = {}
        def add(name, value, refs=(), missing=False):
            if not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value)>1: raise ContractError('invalid behavior feature')
            features[name] = {'value': float(value), 'missing': missing, 'refs': list(refs)}
        for name, value in payload['personality'].items(): add('personality.'+name, value['value'], [value['state_ref']])
        names = {r['id']: r['definition'] for r in self.s.rows('value_dimensions')}
        for value in payload['values']: add('value.'+names[value['dimension_id']], value['activation'], [value['ref']])
        memories = payload['selected_memories']; add('memory.coverage', min(1, len(memories)/8), [m['revision_id'] for m in memories])
        beliefs = payload.get('cognition_snapshot', [])
        add('cognition.uncertainty', sum(b['acceptance_state']!='accepted' for b in beliefs)/len(beliefs) if beliefs else 0, [b['current_revision_id'] for b in beliefs], not bool(beliefs))
        signal = self.s.row('perception_signals', self.s.row('activities', activity)['trigger_event_id'])
        trust = self.s.db.execute("SELECT t.* FROM social_trust_assessments t JOIN social_relationships r ON r.id=t.relationship_id AND r.instance_id=t.instance_id WHERE t.instance_id=? AND r.actor_id=? AND t.domain='behavior' AND t.dimension='reliability' AND COALESCE(json_extract(t.uncertainty_json,'$.method'),'')<>'people-relations-v1' ORDER BY t.rowid DESC LIMIT 1", (self.s.instance_id, signal['source_actor_id'])).fetchone()
        if trust:
            from digital_life.domain.rules import Rules
            rule = json.loads(self.s.row('rule_definitions', trust['condition_rule'])['expression_json'])
            if Rules().evaluate(rule, {'activity': activity, 'chat': bool(payload.get('conversation_context'))}) is not True: trust = None
        if payload.get('relationships'):
            scoped=payload['relationships']['behavior_reliability']
            add('relationship.reliability',scoped['estimate'] if scoped else 0,scoped['observations'] if scoped else [],scoped is None)
        else:
            add('relationship.reliability', trust['estimate'] if trust else 0, [trust['id']] if trust else [], trust is None)
        motivation = payload.get('goal_regulation'); add('motivation.intensity', motivation['intensity'] if motivation else 0, [motivation['motivation_ref']] if motivation else [], motivation is None)
        load = payload.get('states', {}).get('W.queue_depth'); fresh = bool(load and load['fresh'])
        depth = max(0, load['value']) if fresh else 0
        add('state.load', depth/(depth+10), [load['ref']] if fresh else [], not fresh)
        for key, value in (('chat', 'conversation_context'), ('task_loop', 'task_loop'), ('internal', 'exploration')): add('context.'+key, int(bool(payload.get(value))))
        habits = []; invalid_habits = []
        for suggestion in payload['habit_suggestions']:
            item = self.s.row('habit_items', suggestion['habit'])
            try:
                action = json.loads(item['response_template']); validate_action(action)
            except (ValueError, TypeError):
                invalid_habits.append(item['id']); continue
            habits.append(dict(suggestion, action=action))
        return {'configuration': cfg['event_id'], 'version': cfg['version'], 'parameters': cfg, 'features': features, 'habit_suggestions': habits, 'invalid_habits': invalid_habits}

    def check(self, payload):
        from digital_life.application.behavior.habit_learning import HabitLearning
        HabitLearning(self.s).check(payload)
        from digital_life.application.behavior.people_relations import PeopleRelations
        PeopleRelations(self.s).check(payload['activity_id'],payload)
        pinned = payload.get('behavior_policy'); cfg = self.config()
        if not cfg['enabled'] and pinned is None: return
        if not pinned or not cfg['enabled'] or pinned['configuration'] != cfg['event_id']: raise Forbidden('behavior configuration superseded')
        if pinned.get('bypass'): return
        from digital_life.application.services.memory import Memory
        for ref in pinned['features']['memory.coverage']['refs']:
            revision = self.s.row('memory_revisions', ref); memory = self.s.row('memory_items', revision['memory_id'])
            if memory['state']!='active' or memory['current_revision_id']!=ref or self.s.config()['self_actor'] not in Memory(self.s).readers(memory['id']): raise Forbidden('behavior memory source withdrawn or superseded')

    def candidates(self, proposed):
        validate_action(proposed)
        actions = [proposed]
        for tool, reason in (('wait','暂缓当前行动'), ('ask','需要补充信息以决定下一步')):
            if proposed['tool'] != tool: actions.append({'tool':tool, 'arguments':{'reason':reason}})
        return actions

    def eligibility(self, action):
        if action['tool'] in ('wait','ask'): return True, None
        try:
            from digital_life.domain.project_files import NAMES
            if action['tool'] in NAMES:
                from digital_life.application.lifecycle.project_access import ProjectAccess
                from digital_life.infrastructure.tools.project_files import parts
                resource=ProjectAccess(self.s).resource(action['tool'])
                paths=action['arguments'].get('paths',[action['arguments']['path']] if 'path' in action['arguments'] else [])
                for path in paths:parts(resource,path)
                return True,None
            from digital_life.infrastructure.tools.workspace import registry, safe_path
            if action['tool'] not in registry().entries: raise Forbidden('tool not registered')
            current = self.s.rows('policy_epochs')[0]['policy_version_id']
            policy = self.s.row('policy_versions', current); scope = json.loads(policy['scope'])
            # Initial authorization policy has no allow-list: registered tools are reviewable, never pre-authorized.
            if action['tool'] not in scope.get('tools', registry().entries) or scope.get('root')!=str(self.s.root/'workspace'): raise Forbidden('outside current policy')
            path = action['arguments'].get('path')
            if 'path' in action['arguments']: safe_path(self.s.root/'workspace', path)
            return True, None
        except ContractError as error: return False, str(error)

    def execution_constraint(self,payload,proposed):
        from digital_life.domain.project_files import NAMES
        from digital_life.application.lifecycle.project_access import ProjectAccess
        from digital_life.application.accounts import account_scope as account_scope
        acceptance=payload.get('deployment_acceptance')
        if acceptance:
            from digital_life.application.lifecycle.deployment_thought import PROTOCOL,expected
            context=self.s.db.execute('SELECT attributes_json FROM context_snapshots WHERE activity_id=?',(payload['activity_id'],)).fetchone()
            actual=json.loads(context[0]).get('deployment_acceptance') if context else None
            if actual!=acceptance or acceptance.get('protocol')!=PROTOCOL or proposed!=expected(acceptance['nonce']):raise Forbidden('invalid deployment acceptance decision')
            return PROTOCOL
        cfg=payload.get('project_access')
        if not cfg or not cfg.get('auto_approve') or payload.get('exploration'):return None
        loop=payload.get('task_loop',{}).get('configuration') or {}
        if proposed['tool'] not in NAMES and loop.get('verification',{}).get('kind')!='project_task':return None
        activity=payload['activity_id'];signal=self.s.row('perception_signals',self.s.row('activities',activity)['trigger_event_id'])
        if self.s.row('perception_channels',signal['channel_id'])['kind']!='user':return None
        if account_scope.active(self.s):
            if (account_scope.current(self.s) or {}).get('role')!='root':return None
        elif signal['source_actor_id']!=self.s.config()['controller']:return None
        current=ProjectAccess(self.s).context()
        if current is None or not current['auto_approve'] or any(cfg.get(key)!=current.get(key) for key in ('generation','root','root_identity','exclude','tools')):return None
        if not self.eligibility(proposed)[0]:return None
        return 'explicit-authorized-project-task-v1'

    def evaluate(self, payload, proposed, draw):
        self.check(payload); pinned = payload['behavior_policy']; cfg = pinned['parameters']
        constraint=self.execution_constraint(payload,proposed)
        candidates = []
        for index, action in enumerate(self.candidates(proposed)):
            features = {key: value['value'] for key,value in pinned['features'].items()}
            from digital_life.application.behavior.habit_learning import canonical
            matching = [h for h in pinned['habit_suggestions'] if dumps(canonical(h['action']))==dumps(canonical(action))]
            features.update(proposed=int(index==0), cost=int(action['tool'] not in ('wait','ask')), habit=max([h['strength'] for h in matching] or [0]))
            aliases={'project_version_status':'read_file','project_version_log':'read_file','project_version_save':'write_note','project_version_diff':'read_file','project_version_restore':'write_note','project_check':'read_file','project_list':'list_files','project_read':'read_file','project_search':'read_file','project_write':'write_note','project_edit':'write_note','project_mkdir':'write_note'}
            parameter_tool=aliases.get(action['tool'],action['tool'])
            factors = {key: weight*features.get(key,0) for key,weight in cfg['weights'][parameter_tool].items()}
            factors['bias'] = cfg['biases'].get(action['tool'],0)
            eligible, reason = self.eligibility(action)
            if constraint and index>0:eligible,reason=False,'random alternative not applicable to explicit authorized project step'
            candidates.append({'action':action,'features':features,'factors':factors,'score':sum(factors.values()),'eligible':eligible,'blocked_reason':reason})
        probabilities = Decisions(self.s).distribution([c['score'] for c in candidates], [c['eligible'] for c in candidates], cfg['temperature'])
        selected = sample(probabilities, draw)
        for candidate, p in zip(candidates, probabilities): candidate['probability'] = p
        return {'configuration': pinned['configuration'], 'version': cfg['version'], 'execution_constraint':constraint, 'temperature':cfg['temperature'], 'entropy_bits':-sum(p*math.log2(p) for p in probabilities if p>0), 'candidates':candidates, 'draw':draw, 'selected_index':selected}

    def select(self, activity, goal, context, payload, proposed, request):
        seed = secrets.randbits(53); evaluation = self.evaluate(payload, proposed, seed/2**53)
        with self.s.tx():
            decision = self.s.insert('decision_records', activity_id=activity, goal_id=goal, context_id=context, strategy_type='probabilistic', strategy_version=evaluation['version'], seed=seed, state='draft')
            refs = []
            for i, candidate in enumerate(evaluation['candidates']):
                refs.append(self.s.insert('decision_candidates', decision_id=decision, action_template=candidate['action'], eligible=int(candidate['eligible']), blocked_reason=candidate['blocked_reason'], score=candidate['score'], selection_probability=candidate['probability'], selected=int(i==evaluation['selected_index'])))
            self.s.db.execute("UPDATE decision_records SET state='finalized' WHERE id=?", (decision,))
            self.s.event('behavior_policy.selected', payload=dict(evaluation, decision=decision, request=request, seed=seed, feature_snapshot=payload['behavior_policy']), activity=activity)
        return {'decision':decision, 'selected':refs[evaluation['selected_index']], 'action':evaluation['candidates'][evaluation['selected_index']]['action']}
