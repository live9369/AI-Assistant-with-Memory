"""Lossless column encoding of native chat state observations only."""
import copy
from digital_life.domain.contracts import dumps


def compact_chat_states(request):
    states = request.get('states')
    if not request.get('chat_expression') or not isinstance(states, dict) or not states:
        return request
    if not all(isinstance(value, dict) for value in states.values()):
        return request
    fields = sorted(next(iter(states.values())))
    if any(sorted(value) != fields for value in states.values()):
        return request  # Never turn absent fields into null or discard unknown columns.
    columns = ['name'] + fields
    rows = [[name] + [value[field] for field in fields] for name, value in states.items()]
    dictionaries = {}
    size = lambda value: len(dumps(value).encode())
    for index, column in enumerate(columns):
        values = [row[index] for row in rows]
        # Preserve booleans versus integers, and support arbitrary JSON values.
        unique, indices, keys = [], [], {}
        for value in values:
            key = dumps(value)
            if key not in keys:
                keys[key] = len(unique)
                unique.append(value)
            indices.append(keys[key])
        if size(values) > size(unique) + size(indices) + len(column.encode()) + 8:
            dictionaries[column] = unique
            for row, position in zip(rows, indices):
                row[index] = position
    encoded = {'encoding': 'columns-and-rows-v1', 'columns': columns,
               'dictionaries': dictionaries, 'rows': rows}
    if size(encoded) >= size(states):
        return request
    result = copy.deepcopy(request)
    result['states'] = encoded
    return result


def expand_states(encoded):
    """Decode for local integrity checks; model receives the explicit same rule."""
    result = {}
    for row in encoded['rows']:
        values = [encoded['dictionaries'][column][value] if column in encoded['dictionaries'] else value
                  for column, value in zip(encoded['columns'], row)]
        result[values[0]] = dict(zip(encoded['columns'][1:], values[1:]))
    return result
