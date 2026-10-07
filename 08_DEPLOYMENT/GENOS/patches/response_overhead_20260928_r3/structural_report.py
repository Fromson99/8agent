"""Apply reviewed function edits while retaining other installed report bytes."""
import ast
import hashlib
import json
from pathlib import Path


def signature(node):
    def canonical(value):
        if isinstance(value, ast.AST):
            fields = {}
            for name, child in ast.iter_fields(value):
                if name == 'type_params':
                    if child:
                        raise ValueError('generic type parameters are unsupported')
                    continue
                fields[name] = canonical(child)
            return {'node': type(value).__name__, 'fields': fields}
        if isinstance(value, list):
            return [canonical(child) for child in value]
        if isinstance(value, complex):
            return {'complex': [value.real, value.imag]}
        if isinstance(value, bytes):
            return {'bytes_hex': value.hex()}
        if value is Ellipsis:
            return {'ellipsis': True}
        return value
    raw = json.dumps(canonical(node), ensure_ascii=True, sort_keys=True,
                     separators=(',', ':')).encode('ascii')
    return hashlib.sha256(raw).hexdigest()


def one(values, description):
    values = list(values)
    if len(values) != 1:
        raise ValueError('report structural check failed: ' + description)
    return values[0]


def functions(tree):
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.setdefault(node.name, []).append(node)
        elif isinstance(node, ast.ClassDef):
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result.setdefault(node.name + '.' + method.name, []).append(method)
    return result


def literal_fields(node, definitions=None, seen=()):
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return literal_fields(node.left, definitions, seen) | literal_fields(node.right, definitions, seen)
    if (isinstance(node, ast.Name) and node.id.endswith('_DIAGNOSTIC_FIELD_NAMES')
            and definitions and node.id in definitions and node.id not in seen):
        return literal_fields(definitions[node.id], definitions, seen + (node.id,))
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'frozenset' and len(node.args) == 1 and not node.keywords
            and isinstance(node.args[0], (ast.Set, ast.List, ast.Tuple))
            and all(isinstance(n, ast.Constant) and isinstance(n.value, str) for n in node.args[0].elts)):
        return {n.value for n in node.args[0].elts}
    raise ValueError('unsupported live field inventory')


def transform(raw, templates):
    if templates.get('signature_format') != 'canonical-ast-fields-v1':
        raise ValueError('unsupported AST signature format')
    tree = ast.parse(raw, feature_version=(3, 11))
    nodes = functions(tree)
    lines = raw.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def span(node):
        return (offsets[node.lineno - 1] + node.col_offset,
                offsets[node.end_lineno - 1] + node.end_col_offset)

    def replacement(node, source):
        start, end = span(node)
        indent = raw[offsets[node.lineno - 1]:start].decode('utf-8')
        if indent.strip():
            raise ValueError('unsupported report indentation')
        newline = '\r\n' if lines[node.lineno - 1].endswith(b'\r\n') else '\n'
        pieces = source.splitlines()
        return start, end, (pieces[0] + ''.join(newline + indent + s for s in pieces[1:])).encode()

    edits, expected, incompatible = [], {}, []
    for name, choices in templates['functions'].items():
        node = one(nodes.get(name, []), name)
        actual = signature(node)
        row = choices.get(actual)
        if row is None:
            incompatible.append(name + ' ast_sha256=' + actual)
            continue
        expected[name] = row['new_ast_sha256']
        if actual != row['new_ast_sha256']:
            edits.append(replacement(node, row['new_source']))
    for name, row in templates['add_methods'].items():
        if name in nodes:
            node = one(nodes[name], name)
            if signature(node) not in row['accepted_ast_sha256']:
                incompatible.append(name + ' ast_sha256=' + signature(node))
        else:
            class_name, method_name = name.split('.')
            cls = one((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), class_name)
            # Insert after the existing class body without touching its last method.
            anchor = cls.body[-1]
            pos = offsets[anchor.end_lineno]
            indent = ' ' * (cls.col_offset + 4)
            newline = '\r\n' if lines[anchor.end_lineno - 1].endswith(b'\r\n') else '\n'
            data = newline + ''.join(indent + line + newline for line in row['new_source'].splitlines())
            edits.append((pos, pos, data.encode()))
    if incompatible:
        raise ValueError('incompatible report functions: ' + '; '.join(incompatible))
    inventory = one((n for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == '_LIVE_FIELD_NAMES' for t in n.targets)),
                    '_LIVE_FIELD_NAMES')
    definitions = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith('_DIAGNOSTIC_FIELD_NAMES'):
                    if target.id in definitions:
                        raise ValueError('duplicate diagnostic field definition: ' + target.id)
                    definitions[target.id] = node.value
    fields = literal_fields(inventory.value, definitions)
    if not {'phase', 'duration_ms', 'schema'}.issubset(fields):
        raise ValueError('live field inventory lacks event contract')
    if 'observability_revision' not in fields:
        start, end = span(inventory.value)
        edits.append((end, end, b" | frozenset({'observability_revision'})"))
    boundary = len(raw) + 1
    for start, end, data in sorted(edits, key=lambda r: (r[0], r[1]), reverse=True):
        if end > boundary:
            raise ValueError('overlapping report structural edits')
        raw = raw[:start] + data + raw[end:]
        boundary = start
    after = functions(ast.parse(raw, feature_version=(3, 11)))
    for name, digest in expected.items():
        if signature(one(after.get(name, []), name)) != digest:
            raise ValueError('post-transform function mismatch: ' + name)
    for name, row in templates['add_methods'].items():
        if signature(one(after.get(name, []), name)) not in row['accepted_ast_sha256']:
            raise ValueError('post-transform method mismatch: ' + name)
    compile(raw, 'request_report.py', 'exec')
    return raw


def load_templates(directory):
    return json.loads((Path(directory) / 'REPORT_TEMPLATES.json').read_bytes())
