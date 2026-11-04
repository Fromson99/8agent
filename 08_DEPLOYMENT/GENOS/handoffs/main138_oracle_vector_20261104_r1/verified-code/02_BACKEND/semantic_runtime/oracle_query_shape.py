"""Identify a reviewed query template and bind its variable values.

Only lexical normalization happens here. Oracle SQL plans are prepared by the
developer tool, shipped with the code and never compiled in a serving request.
"""
from collections.abc import Mapping
from hashlib import sha256

from .oracle_dp_io import DPError
from .oracle_sql_tokens import tokens


def shape(statement, parameters=()):
    if isinstance(parameters, Mapping):
        raise DPError('QUERY_SQL_BINDS: maintained port requires positional parameters')
    parameters = list(parameters)
    for value in parameters:
        if value is not None and not isinstance(value, (str, int, float)):
            raise DPError('QUERY_SQL_BINDS: unsupported scalar bind')
    scanned = tokens(statement)
    parts, values = [], {}
    at = 0
    for token in scanned:
        if token.text == '?':
            if at >= len(parameters):
                raise DPError('QUERY_SQL_BINDS: parameter count differs')
            name = 'a8_p' + str(at)
            values[name] = parameters[at]
            parts.append(('value', ':' + name))
            at += 1
        elif token.kind == 'bind':
            raise DPError('QUERY_SQL_BINDS: maintained port requires question mark parameters')
        elif token.kind == 'string':
            if not token.text.startswith("'"):
                raise DPError('QUERY_SQL_TOKEN: maintained queries use ordinary SQL literals')
            name = 'a8_v' + str(len(values))
            values[name] = token.text[1:-1].replace("''", "'")
            parts.append(('value', ':' + name))
        elif token.kind == 'identifier':
            parts.append(('identifier', '"' + token.text.replace('"', '""') + '"'))
        else:
            parts.append((token.kind, token.text.lower() if token.kind == 'word' else token.text))
    if at != len(parameters):
        raise DPError('QUERY_SQL_BINDS: parameter count differs')
    if parts and parts[-1][1] == ';':
        parts.pop()
    if any(value == ';' for _, value in parts):
        raise DPError('QUERY_SQL_READ_ONLY: one maintained SELECT required')
    # An IN list is one template slot regardless of its bounded cardinality.
    # Values retain their original bind names for precise diagnostics.
    groups, normalized = {}, []
    i = 0
    while i < len(parts):
        if parts[i][1] == 'in' and i + 3 < len(parts) and parts[i+1][1] == '(':
            j, items = i + 2, []
            while j < len(parts) and parts[j][0] == 'value':
                items.append(parts[j][1][1:])
                j += 1
                if j < len(parts) and parts[j][1] == ',':
                    j += 1
                    continue
                break
            if items and j < len(parts) and parts[j][1] == ')':
                group = 'a8_list' + str(len(groups))
                groups[group] = items
                normalized.extend(['in', '(', ':' + group, ')'])
                i = j + 1
                continue
        normalized.append(parts[i][1])
        i += 1
    # Slot names depend on shape, not the size of a preceding IN list.
    slots, canonical = {}, []
    for part in normalized:
        if part.startswith(':'):
            name = part[1:]
            if name not in slots:
                slots[name] = 's' + str(len(slots))
            canonical.append(':' + slots[name])
        else:
            canonical.append(part)
    sql = ' '.join(canonical)
    bound = {slot: ([(n, values[n]) for n in groups[name]] if name in groups
                    else [(name, values[name])]) for name, slot in slots.items()}
    lists = {slots[n] for n in groups}
    # Distinguish scalar and variadic slots in the plan identity.
    key = sha256((sql + '|' + ','.join(sorted(lists))).encode()).hexdigest()
    return key, sql, bound, lists
