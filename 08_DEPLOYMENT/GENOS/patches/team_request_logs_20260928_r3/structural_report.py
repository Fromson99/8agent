"""Validate and edit only the reporting functions; keep other installed bytes."""
import ast
import hashlib
import json
from pathlib import Path


def signature(node):
    # ast.dump changed its empty-field formatting in Python 3.13. Frozen dumps
    # produced on 3.14 therefore reject identical functions on GENOS 3.11.
    # Serialize the actual AST fields ourselves, keeping empty/None values.
    def canonical(value):
        if isinstance(value, ast.AST):
            fields = {}
            for name, child in ast.iter_fields(value):
                if name == 'type_params':
                    if child:
                        raise ValueError('generic type parameters are unsupported')
                    continue  # Added in 3.12; absent on the 3.11 target.
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

    edits = []
    incompatible = []
    for name, row in templates['functions'].items():
        node = one(nodes.get(name, []), name)
        actual = signature(node)
        if actual == row['new_ast_sha256']:
            continue
        if actual not in row['accepted_ast_sha256']:
            incompatible.append(name + ' ast_sha256=' + actual)
            continue
        start, end = span(node)
        indent = raw[offsets[node.lineno - 1]:start].decode('utf-8')
        if indent.strip():
            raise ValueError('unsupported report indentation: ' + name)
        newline = '\r\n' if lines[node.lineno - 1].endswith(b'\r\n') else '\n'
        source = row['new_source'].splitlines()
        replacement = source[0] + ''.join(newline + indent + line for line in source[1:])
        edits.append((start, end, replacement.encode('utf-8')))

    if incompatible:
        raise ValueError('incompatible report functions: ' + '; '.join(incompatible))

    required = {'report_directory', 'team_name'}
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == 'request_summary':
            imported.update(alias.name for alias in node.names if alias.asname is None)
    missing = required - imported
    if missing:
        # Refuse name collisions, rather than changing an unrelated binding.
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in missing:
                raise ValueError('report helper name collision: ' + node.name)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(n, ast.Name) and n.id in missing for target in targets for n in ast.walk(target)):
                    raise ValueError('report helper assignment collision')
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if any((alias.asname or alias.name.split('.')[0]) in missing for alias in node.names):
                    raise ValueError('report helper import collision')
        anchor = one((n for n in tree.body if isinstance(n, ast.ImportFrom)
                      and n.level == 1 and n.module is None
                      and any(a.name == 'observability' and a.asname == 'obs' for a in n.names)),
                     'observability import')
        # Place the import at the next line, preserving any original comment.
        position = offsets[anchor.end_lineno]
        newline = b'\r\n' if lines[anchor.end_lineno - 1].endswith(b'\r\n') else b'\n'
        insertion = ('from .request_summary import ' + ', '.join(sorted(missing))).encode() + newline
        edits.append((position, position, insertion))

    boundary = len(raw) + 1
    for start, end, data in sorted(edits, key=lambda row: (row[0], row[1]), reverse=True):
        if end > boundary:
            raise ValueError('overlapping report structural edits')
        raw = raw[:start] + data + raw[end:]
        boundary = start
    result = ast.parse(raw, feature_version=(3, 11))
    after = functions(result)
    for name, row in templates['functions'].items():
        if signature(one(after.get(name, []), name)) != row['new_ast_sha256']:
            raise ValueError('post-transform function mismatch: ' + name)
    compile(raw, 'request_report.py', 'exec')
    return raw


def load_templates(directory):
    return json.loads((Path(directory) / 'REPORT_TEMPLATES.json').read_bytes())
