"""Approved function-only decision repair for the photographed and integrated code."""
import ast
import hashlib
import json


def signature(node):
    def canonical(value):
        if isinstance(value, ast.AST):
            return {'node': type(value).__name__, 'fields': {
                name: canonical(child) for name, child in ast.iter_fields(value)
                if name != 'type_params'}}
        if isinstance(value, list):
            return [canonical(child) for child in value]
        return value
    return hashlib.sha256(json.dumps(canonical(node), sort_keys=True, ensure_ascii=True,
                                    separators=(',', ':')).encode()).hexdigest()


def node_for(raw, qualified):
    nodes = ast.parse(raw).body
    for part in qualified.split('.'):
        matches = [n for n in nodes if getattr(n, 'name', None) == part or
                   isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == part for t in n.targets)]
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError('ambiguous patch node: ' + qualified)
        node = matches[0]
        nodes = getattr(node, 'body', [])
    return node


def snippet(raw, node):
    start = min([node.lineno] + [n.lineno for n in getattr(node, 'decorator_list', [])]) - 1
    return start, node.end_lineno, b''.join(raw.splitlines(keepends=True)[start:node.end_lineno])


def transform(raw, row, bundle):
    if raw is None:
        raise ValueError('missing decision module')
    for change in row['nodes']:
        current = node_for(raw, change['qualified'])
        if current is None and change.get('optional'):
            continue
        if current is None:
            raise ValueError('missing decision prerequisite: ' + change['qualified'])
        matched = next((x for x in change['variants'] if signature(current) in (x['before_ast'], x['after_ast'])), None)
        if matched is None:
            raise ValueError('unknown decision function; no writes: ' + change['qualified'])
        if signature(current) == matched['after_ast']:
            continue
        after = (bundle / matched['after']).read_bytes()
        start, end, _ = snippet(raw, current)
        _, _, replacement = snippet(after, node_for(after, change['qualified']))
        lines = raw.splitlines(keepends=True)
        raw = b''.join(lines[:start]) + replacement + b''.join(lines[end:])
        if signature(node_for(raw, change['qualified'])) != matched['after_ast']:
            raise ValueError('decision function verification failed')
    compile(raw, '<decision-repair>', 'exec')
    return raw
