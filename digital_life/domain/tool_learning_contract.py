"""TL-LOOP-0.1 structural validation, never authorization or fact proof.

The business owner must still check actual sources, permissions, versions,
remaining budgets and stop state at the execution/commit boundary.
"""
from digital_life.domain import tool_learning_products as products
from digital_life.domain.tool_learning_types import fingerprint, resolve_locator, string


def validate(type_name, value):
    string(type_name)
    return products.validate(type_name, value)


def loads(raw, type_name=None):
    if type_name is not None:
        string(type_name)
    return products.loads(raw, type_name)


def validate_request(operation, value):
    """Use a named operation; recall is a read request, not a write Envelope."""
    string(operation)
    if operation == 'recall':
        return validate('RecallRequest', value)
    return products.validate_envelope(value, operation)


__all__ = ('validate', 'loads', 'validate_request', 'fingerprint', 'resolve_locator')
