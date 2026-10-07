"""Surgical display edits to a pinned installed report; never execute its source."""
import ast
import json
from pathlib import Path

REVISION = 'thinking-live-20260928-r3'


def signature(node):
    return ast.dump(node, include_attributes=False)


def expression(source):
    return ast.parse(source, mode='eval').body


def one(nodes, description):
    values = list(nodes)
    if len(values) != 1:
        raise ValueError('report structural check failed: ' + description)
    return values[0]


def transform(raw, templates):
    """Only validated AST nodes are replaced; all other bytes remain intact."""
    tree = ast.parse(raw, feature_version=(3, 11))
    lines = raw.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    edits = []
    def span(node):
        return (offsets[node.lineno-1]+node.col_offset,
                offsets[node.end_lineno-1]+node.end_col_offset)
    def replace(node, text):
        start, end = span(node)
        edits.append((start, end, text.encode()))
    def segment(node):
        start, end = span(node)
        return raw[start:end].decode('utf-8')
    def assignments(name):
        return [node for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)]
    def global_definition(name, expected_source):
        present = assignments(name)
        wanted = ast.parse(expected_source).body[0]
        if present:
            actual = one(present, name)
            if signature(actual) != signature(wanted):
                raise ValueError('report diagnostic definition differs: ' + name)
            return False
        return True
    fields = one(assignments('_LIVE_FIELD_NAMES'), '_LIVE_FIELD_NAMES')
    allowed = fields.value
    if isinstance(allowed, ast.BinOp) and isinstance(allowed.op, ast.BitOr):
        if not isinstance(allowed.right, ast.Name) or allowed.right.id != '_LIVE_DIAGNOSTIC_FIELD_NAMES':
            raise ValueError('report field union is incompatible')
        allowed = allowed.left
        union_present = True
    else:
        union_present = False
    if not (isinstance(allowed, ast.Call) and isinstance(allowed.func, ast.Name)
            and allowed.func.id == 'frozenset' and len(allowed.args) == 1 and not allowed.keywords):
        raise ValueError('report live fields must be a literal frozenset')
    values = ast.literal_eval(allowed.args[0])
    if not isinstance(values, (set, list, tuple)) or not all(isinstance(x, str) for x in values):
        raise ValueError('report live fields have incompatible values')
    if not {'phase', 'duration_ms', 'schema'}.issubset(set(values)):
        raise ValueError('report live fields lack the expected event contract')
    if global_definition('_LIVE_DIAGNOSTIC_FIELD_NAMES', templates['diagnostic_fields']):
        start, _ = span(fields)
        edits.append((start, start, (templates['diagnostic_fields']+'\n').encode()))
    if not union_present:
        replace(fields.value, '('+segment(fields.value)+') | _LIVE_DIAGNOSTIC_FIELD_NAMES')
    live_class = one((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_LiveLog'), '_LiveLog')
    helpers = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_live_diagnostic_value']
    if helpers:
        wanted = ast.parse(templates['helper']).body[0]
        if signature(one(helpers, '_live_diagnostic_value')) != signature(wanted):
            raise ValueError('report diagnostic helper differs')
    else:
        start, _ = span(live_class)
        edits.append((start, start, (templates['helper']+'\n\n').encode()))
    emit = one((n for n in live_class.body if isinstance(n, ast.FunctionDef) and n.name == 'emit'), '_LiveLog.emit')
    field_loop = one((n for n in ast.walk(emit) if isinstance(n, ast.For)
        and isinstance(n.target, ast.Name) and n.target.id == 'key'
        and signature(n.iter) == signature(expression('sorted(_LIVE_FIELD_NAMES)'))), 'emit field loop')
    safe = one((n for n in ast.walk(field_loop) if isinstance(n, ast.Assign)
        and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == 'safe'), 'emit safe field projection')
    old_value = expression('_live_value(fields[key])')
    new_value = expression(templates['safe_expression'])
    if signature(safe.value) == signature(old_value):
        replace(safe.value, templates['safe_expression'])
    elif signature(safe.value) != signature(new_value):
        raise ValueError('report emit field conversion is incompatible')
    details = one((n for n in emit.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'details' for t in n.targets)
        and isinstance(n.value, ast.List) and not n.value.elts), 'emit details initialization')
    markers = [n for n in emit.body if isinstance(n, ast.If)
               and signature(n.test) == signature(expression("'diagnostics_version' in fields"))]
    marker_source = "if 'diagnostics_version' in fields:\n    details.append('live_diagnostics_version="+REVISION+"')"
    if markers:
        marker = one(markers, 'emit revision marker')
        wanted = ast.parse(marker_source).body[0]
        old_marker = ast.parse(marker_source.replace(REVISION, 'thinking-live-20260928-r2')).body[0]
        if signature(marker) == signature(old_marker):
            replace(marker, marker_source.replace('\n', '\n'+(' '*marker.col_offset)))
        elif signature(marker) != signature(wanted):
            raise ValueError('report revision marker is incompatible')
    else:
        _, end = span(details)
        indent = ' '*details.col_offset
        edits.append((end, end, ('\n'+indent+marker_source.replace('\n', '\n'+indent)).encode()))
    summary = one((n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name == 'format_readable_report'), 'format_readable_report')
    old_body = ast.parse(templates['old_summary_body']).body
    new_body = ast.parse(templates['new_summary_body']).body
    loops = [n for n in ast.walk(summary) if isinstance(n, ast.For)
             and isinstance(n.target, ast.Name) and n.target.id == 'key']
    matching = [n for n in loops if [signature(x) for x in n.body] in
                ([signature(x) for x in old_body], [signature(x) for x in new_body])]
    summary_loop = one(matching, 'summary service field loop')
    if [signature(x) for x in summary_loop.body] == [signature(x) for x in old_body]:
        if not isinstance(summary_loop.iter, (ast.Tuple, ast.List)):
            raise ValueError('report summary field list is incompatible')
        keys = ast.literal_eval(summary_loop.iter)
        if not all(isinstance(x, str) for x in keys) or not {'phase','duration_ms'}.issubset(set(keys)):
            raise ValueError('report summary lacks the expected event contract')
        loop_source = 'for key in tuple('+segment(summary_loop.iter)+') + tuple(sorted(_LIVE_DIAGNOSTIC_FIELD_NAMES)):\n'
        loop_source += '\n'.join('    '+line for line in templates['new_summary_body'].splitlines())
        replace(summary_loop, loop_source.replace('\n', '\n'+(' '*summary_loop.col_offset)))
    else:
        # A pre-existing typed summary must consume the diagnostic field list.
        if not any(isinstance(n, ast.Name) and n.id == '_LIVE_DIAGNOSTIC_FIELD_NAMES'
                   for n in ast.walk(summary_loop.iter)):
            raise ValueError('report summary does not consume diagnostic fields')
    last = len(raw)+1
    for start, end, value in sorted(edits, key=lambda row:(row[0],row[1]), reverse=True):
        if end > last:
            raise ValueError('overlapping report edits')
        raw = raw[:start]+value+raw[end:]
        last = start
    ast.parse(raw, feature_version=(3, 11))
    return raw


def load_templates(directory):
    return json.loads((Path(directory)/'REPORT_TEMPLATES.json').read_bytes())
