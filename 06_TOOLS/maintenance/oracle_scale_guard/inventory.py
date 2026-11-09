"""Static inventory of every Oracle SQL template in one code release (no DB, no model).

1. Prepared plans (SQLite statements translated by oracle_query_native): original statement
   text with literals, origins, referenced tables, features.
2. Hand-written Oracle SQL in semantic_runtime/oracle_*.py: NUMBER/CLOB binds, WITH, JSON_TABLE.
3. Code that enumerates lazy Oracle collections (units/sources/... ) - the
   QUERY_NAV_BUDGET / QUERY_SQL_RESULT_BUDGET / QUERY_FULL_CATALOGUE class.

usage: inventory.py --code-root <release/code> --out inventory.json
"""
import argparse, ast, hashlib, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
p = argparse.ArgumentParser(); p.add_argument('--code-root', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
args = p.parse_args(); code = args.code_root.resolve()
sys.path[:0] = [str(ROOT/'06_TOOLS/maintenance'), str(code/'02_BACKEND')]
import prepare_oracle_queries as prep  # noqa: E402  (build-time sqlglot, as the release tool)
# prep inserts the work tree's 02_BACKEND first; use the release's runtime modules instead.
for _n in [n for n in sys.modules if n == 'semantic_runtime' or n.startswith('semantic_runtime.')]:
    del sys.modules[_n]
sys.path.insert(0, str(code/'02_BACKEND'))
from semantic_runtime.oracle_query_plans import PLANS  # noqa: E402
from semantic_runtime.oracle_query_shape import shape  # noqa: E402
from semantic_runtime.oracle_sql_tokens import tokens  # noqa: E402


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        yield node
        for v in node:
            yield from walk(v)


def plan_tables(plan, ctes=()):
    names = set(ctes) | {c[0] for c in plan.get('ctes', [])}
    found = set()
    for n in walk(plan):
        if isinstance(n, list) and len(n) == 3 and n[0] == 'table' and isinstance(n[2], str) and n[2] not in names:
            found.add(n[2])
    return found


def features(plan):
    f = set()
    for n in walk(plan):
        if isinstance(n, dict):
            if n.get('ctes'): f.add('cte')
            if n.get('kind') == 'union': f.add('union')
            if n.get('distinct'): f.add('distinct')
            if n.get('group'): f.add('group')
            if n.get('limit'): f.add('limit')
            if n.get('offset'): f.add('offset')
        elif isinstance(n, list) and n and isinstance(n[0], str):
            k = n[0]
            if k in ('window', 'json', 'array', 'normalized', 'case', 'query', 'subquery', 'boolean_number'):
                f.add(k)
            if k == 'sql' and isinstance(n[1], str):
                for fn in re.findall(r'([A-Z_]+)\(', n[1]):
                    f.add('fn:' + fn)
    return sorted(f)


# 1. prepared plans --------------------------------------------------------------
statements = {}
for statement, origin in prep.source_queries(root=code):
    try:
        count = sum(t.text == '?' for t in tokens(statement))
        key, _, _, _ = shape(statement, [None]*count)
    except Exception as exc:  # shape-rejected fragments never reach Oracle as prepared plans
        continue
    if key in PLANS:
        statements.setdefault(key, [])
        if statement not in [s['statement'] for s in statements[key]]:
            statements[key].append({'statement': statement, 'origin': origin, 'params': count})
missing = sorted(set(PLANS) - set(statements))
plans = []
for key, entry in PLANS.items():
    plans.append({'key': key, 'sql': entry['sql'], 'lists': entry['lists'], 'sources': entry['sources'],
                  'tables': sorted(plan_tables(entry['plan'])), 'features': features(entry['plan']),
                  'statements': statements.get(key, [])})

# 2. hand-written Oracle SQL -------------------------------------------------------
handwritten = []
for path in sorted((code/'02_BACKEND/semantic_runtime').glob('oracle_*.py')):
    if path.name == 'oracle_query_plans.py':
        continue
    text = path.read_text()
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Constant, ast.JoinedStr)):
            raw = ast.get_source_segment(text, node) or ''
            if re.search(r'\b(SELECT|WITH|INSERT|UPDATE|DELETE|MERGE|DECLARE)\b', raw) and re.search(r'\bFROM\b|\bINTO\b|\bBEGIN\b|\bSET\b', raw):
                handwritten.append({'file': path.name, 'line': node.lineno,
                                    'with': bool(re.search(r"\bWITH\b\s+\w+\s+AS\s*\(", raw, re.I)),
                                    'json_table': 'JSON_TABLE' in raw.upper(), 'snippet': raw[:300]})
    for i, line in enumerate(lines, 1):
        if "'NUMBER')" in line or '"NUMBER")' in line:
            handwritten.append({'file': path.name, 'line': i, 'number_bind': True, 'snippet': line.strip()[:300]})

# 3. lazy-collection enumerations ------------------------------------------------
LAZY = {'units', 'sources', 'stored_coordinates', 'coordinate_index', 'members', 'index_labels', 'terms', 'df',
        'definitions', 'labels', 'edges', 'source_terms', 'definition_summaries', 'structures'}
ITER_METHODS = {'items', 'keys', 'values'}
WRAPPERS = {'sorted', 'list', 'set', 'tuple', 'len', 'sum', 'any', 'all', 'max', 'min', 'frozenset', 'dict', 'enumerate'}


def lazy_name(node):
    """'x.units' / 'self.tools.sources' / 'matcher.units' -> attribute name if lazy."""
    if isinstance(node, ast.Attribute) and node.attr in LAZY:
        return ast.unparse(node)
    return None


enumerations = []
for path in sorted((code/'02_BACKEND/semantic_runtime').rglob('*.py')):
    rel = str(path.relative_to(code))
    if path.name.startswith('oracle_') or '/research/' in rel:
        continue
    text = path.read_text()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        hit = None
        if isinstance(node, (ast.For, ast.comprehension)):
            target = node.iter
            if lazy_name(target):
                hit = ('iterate', lazy_name(target))
            elif isinstance(target, ast.Call) and isinstance(target.func, ast.Attribute) and target.func.attr in ITER_METHODS and lazy_name(target.func.value):
                hit = (target.func.attr + '()', lazy_name(target.func.value))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in WRAPPERS and node.args and lazy_name(node.args[0]):
                hit = (node.func.id + '()', lazy_name(node.args[0]))
            elif isinstance(node.func, ast.Name) and node.func.id in WRAPPERS and node.args and isinstance(node.args[0], ast.Call) \
                    and isinstance(node.args[0].func, ast.Attribute) and node.args[0].func.attr in ITER_METHODS and lazy_name(node.args[0].func.value):
                hit = (node.func.id + '(' + node.args[0].func.attr + '())', lazy_name(node.args[0].func.value))
            elif isinstance(node.func, ast.Attribute) and node.func.attr in ITER_METHODS and lazy_name(node.func.value) \
                    and not isinstance(getattr(node, 'parent', None), ast.For):
                hit = (node.func.attr + '()', lazy_name(node.func.value))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Sub, ast.BitAnd, ast.BitOr)) and (lazy_name(node.left) or lazy_name(node.right)):
            hit = ('set-op', lazy_name(node.left) or lazy_name(node.right))
        if hit:
            line = text.splitlines()[node.lineno-1].strip() if hasattr(node, 'lineno') else ''
            enumerations.append({'file': rel, 'line': getattr(node, 'lineno', None), 'form': hit[0], 'object': hit[1], 'code': line[:200]})
uniq = {}
for e in enumerations:
    uniq.setdefault((e['file'], e['line'], e['object']), e)
enumerations = sorted(uniq.values(), key=lambda e: (e['file'], e['line'] or 0))

import semantic_runtime
assert Path(semantic_runtime.__file__).resolve().is_relative_to(code), semantic_runtime.__file__
result = {'code_root': str(code), 'plans': plans, 'plans_without_source_statement': missing,
          'handwritten': handwritten, 'lazy_enumerations': enumerations,
          'plans_sha256': hashlib.sha256((code/'02_BACKEND/semantic_runtime/oracle_query_plans.py').read_bytes()).hexdigest()}
args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
print('plans', len(plans), 'missing statements', len(missing), 'handwritten', len(handwritten), 'enumerations', len(enumerations))
