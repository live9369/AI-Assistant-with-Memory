"""Versioned native runtime defaults; activity budgets are frozen at submission."""
import json

LEGACY_DEFAULTS = {
    'budget_enabled':True,
    'tokens':16000, 'tool_calls':8, 'attempts':8, 'duration_seconds':600,
    'thought_tokens':4096, 'request_attempts':3, 'request_seconds':300,
    'history_messages':8, 'history_bytes':8000,
    'recall_items':8, 'exploration_recall_items':3,
    'root_weight':2.0, 'other_weight':1.0,
}

DEFAULTS = dict(LEGACY_DEFAULTS, budget_enabled=False)


def current(store):
    return dict(DEFAULTS, **store.config().get('runtime_settings', {}))


def for_activity(store, activity):
    document = json.loads(store.row('activities', activity)['budget_json'])
    # Legacy activities retain the original defaults even after a settings edit.
    return dict(LEGACY_DEFAULTS, **document.get('runtime_settings', {}))
