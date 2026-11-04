#!/usr/bin/env python3
"""Prepare reviewed Oracle query plans during development, never in serving.

SQLGlot is a build dependency only. Plans contain native Oracle expressions
and explicit schema/bind slots, not serialized SQLGlot/SQLite syntax trees.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pprint
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '02_BACKEND'))
import sqlglot
from sqlglot import exp
from semantic_runtime.oracle_query_shape import shape
from semantic_runtime.oracle_sql_tokens import tokens
from semantic_runtime.oracle_dp_io import DPError


def expression(node, *, scalar=False):
    if node is None:
        return None
    if isinstance(node, exp.Alias):
        return expression(node.this, scalar=scalar)
    if isinstance(node, exp.Column):
        return ['star', node.table] if node.is_star else ['column', node.table, node.name]
    if isinstance(node, exp.Star):
        return ['star', '']
    if isinstance(node, exp.Placeholder):
        return ['slot', node.this]
    if isinstance(node, exp.Null):
        return ['null']
    if isinstance(node, exp.Literal):
        return ['literal', node.this, node.is_string]
    if isinstance(node, (exp.Select, exp.Union)):
        return ['query', query(node)]
    if isinstance(node, exp.Subquery):
        return ['query', query(node.this)]
    if isinstance(node, exp.JSONExtractScalar):
        return ['json', expression(node.this), expression(node.expression)]
    if isinstance(node, exp.Window):
        if node.args.get('spec') or node.args.get('alias'):
            raise ValueError('window frame requires an explicit prepared template')
        return ['window', expression(node.this), [expression(n) for n in node.args.get('partition_by') or []],
                [expression(n) for n in (node.args.get('order') or exp.Order()).expressions]]
    if isinstance(node, exp.Case):
        return ['case', expression(node.this),
                [[expression(n.this), expression(n.args.get('true'))] for n in node.args.get('ifs') or []],
                expression(node.args.get('default'))]
    if isinstance(node, exp.If):
        return ['case', None, [[expression(node.this), expression(node.args.get('true'))]], expression(node.args.get('false'))]
    if isinstance(node, exp.Anonymous) and node.name.lower() == 'legal_normalized':
        return ['normalized', *[expression(arg) for arg in node.expressions]]
    if isinstance(node, exp.Paren):
        return ['paren', expression(node.this, scalar=scalar)]
    if isinstance(node, (exp.And, exp.Or)):
        value = [node.key, expression(node.this), expression(node.expression)]
    elif isinstance(node, (exp.EQ, exp.NEQ)):
        value = [node.key, expression(node.this), expression(node.expression)]
    elif isinstance(node, exp.Is) and isinstance(node.expression, exp.Null):
        value = ['is_null', expression(node.this)]
    elif isinstance(node, exp.In):
        value = ['in', expression(node.this), [expression(x) for x in node.expressions],
                 expression(node.args.get('query'))]
    elif isinstance(node, exp.Ordered):
        return ['order', expression(node.this), bool(node.args.get('desc')), bool(node.args.get('nulls_first'))]
    else:
        clone, children = node.copy(), []
        for key, value in node.args.items():
            def replace(child):
                index = len(children)
                children.append(expression(child, scalar=isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Div))))
                return exp.Var(this='__a8_slot_' + str(index) + '__')
            if isinstance(value, exp.Expression):
                clone.set(key, replace(value))
            elif isinstance(value, list):
                clone.set(key, [replace(v) if isinstance(v, exp.Expression) else v for v in value])
        value = ['sql', clone.sql(dialect='oracle', identify=True,
                                 unsupported_level=sqlglot.ErrorLevel.RAISE), children]
    if scalar and isinstance(node, (exp.Predicate, exp.And, exp.Or, exp.Not)):
        return ['boolean_number', value]
    return value


def relation(node, index):
    if isinstance(node, exp.Subquery):
        return ['subquery', node.alias or '_q' + str(index), query(node.this)]
    if not isinstance(node, exp.Table) or node.db or node.catalog:
        raise ValueError('only declared logical relations are permitted')
    if isinstance(node.this, exp.Anonymous) and node.this.name.lower() == 'json_each':
        if len(node.this.expressions) != 1:
            raise ValueError('json_each requires one array')
        return ['array', node.alias or '_q' + str(index), expression(node.this.expressions[0])]
    if not isinstance(node.this, exp.Identifier):
        raise ValueError('unsupported table function')
    return ['table', node.alias_or_name, node.name]


def query(tree):
    if not isinstance(tree, (exp.Select, exp.Union)) or tree.find(exp.Into) or tree.find(exp.Lock):
        raise ValueError('one read-only SELECT/UNION required')
    tree = tree.copy()
    # Identity rows contain CLOBs; an inner join used only for existence must
    # not force Oracle DISTINCT on the large text. Preserve the old optimizer.
    base = tree.args.get('from_')
    base = base.this if base is not None else None
    joins = tree.args.get('joins') or []
    if (isinstance(base, exp.Table) and base.name in ('reference', 'source', 'term', 'definition')
            and tree.args.get('distinct') and len(joins) == 1):
        projections = [p.this if isinstance(p, exp.Alias) else p for p in tree.expressions]
        if (all(isinstance(p, exp.Column) and p.table == base.alias_or_name for p in projections)
                and any(p.name in ('id', 'json') for p in projections) and not joins[0].args.get('side')):
            condition = joins[0].args.get('on')
            where = tree.args.get('where')
            if where is not None:
                condition = exp.and_(condition, where.this.copy()) if condition is not None else where.this.copy()
            exists = exp.select('1').from_(joins[0].this.copy())
            if condition is not None:
                exists = exists.where(condition.copy())
            tree.set('joins', [])
            tree.set('distinct', None)
            tree.set('where', exp.Where(this=exp.Exists(this=exists)))
    plan = {'kind': tree.key}
    with_ = tree.args.get('with_')
    if with_:
        if with_.args.get('recursive'):
            raise ValueError('recursive query requires an explicit Oracle implementation')
        plan['ctes'] = [[cte.alias, query(cte.this)] for cte in with_.expressions]
    if isinstance(tree, exp.Union):
        plan.update(left=query(tree.this), right=query(tree.expression), distinct=bool(tree.args.get('distinct')))
    else:
        plan['columns'] = []
        for i, p in enumerate(tree.expressions):
            name = p.alias or p.output_name or '_col_' + str(i)
            if not p.alias and isinstance(p, exp.JSONExtractScalar):
                name = ['path_name', expression(p.expression), '_col_' + str(i)]
            plan['columns'].append([expression(p, scalar=True), name])
        plan['distinct'] = bool(tree.args.get('distinct'))
        plan['aggregate'] = any(p.find(exp.AggFunc) for p in tree.expressions)
        plan['from'] = relation(base, 0) if base is not None else None
        plan['joins'] = []
        for i, join in enumerate(tree.args.get('joins') or [], 1):
            kind = ' '.join(v for v in (join.args.get('side'), join.args.get('kind')) if v)
            plan['joins'].append([relation(join.this, i), kind,
                                  expression(join.args.get('on')), [n.name for n in join.args.get('using') or []]])
        for key in ('where', 'having'):
            node = tree.args.get(key)
            plan[key] = expression(node.this) if node is not None else None
        plan['group'] = [expression(e) for e in (tree.args.get('group') or exp.Group()).expressions]
    plan['order'] = [expression(e) for e in (tree.args.get('order') or exp.Order()).expressions]
    for key in ('limit', 'offset'):
        node = tree.args.get(key)
        plan[key] = expression(node.expression) if node is not None else None
    return plan


def prepare(statement):
    count = sum(t.text == '?' for t in tokens(statement))
    key, normalized, _, lists = shape(statement, [None] * count)
    trees = sqlglot.parse(normalized, read='sqlite')
    if len(trees) != 1:
        raise ValueError('one SELECT required')
    plan = query(trees[0])
    return key, {'sql': normalized, 'lists': sorted(lists), 'plan': plan}


def source_queries(root=ROOT):
    """Full literal queries plus explicit enumerations of dynamic families."""
    for path in sorted((root / '02_BACKEND/semantic_runtime').rglob('*.py')):
        if path.name.startswith('oracle_query_plan'):
            continue
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value.strip()
                if value.upper().startswith(('SELECT ', 'WITH ')):
                    yield value, str(path.relative_to(root)) + ':' + str(node.lineno)
    from oracle_query_families import queries
    yield from queries()


def build():
    entries, rejected = {}, []
    for statement, origin in source_queries():
        try:
            key, entry = prepare(statement)
        except (ValueError, sqlglot.errors.SqlglotError, TypeError, AttributeError, DPError) as exc:
            rejected.append({'source': origin, 'reason': str(exc).splitlines()[0], 'sql': statement})
            continue
        if key not in entries:
            entries[key] = {**entry, 'sources': []}
        entries[key]['sources'].append(origin)
    return dict(sorted(entries.items())), rejected


def source_hashes(entries):
    pinned = json.loads((ROOT / '02_BACKEND/ENGINES/legal_agent/6.0.0/retrieve.json').read_text())['files']
    paths = set()
    for entry in entries.values():
        for source in entry['sources']:
            path = source.rsplit(':', 1)[0]
            if not path.startswith('02_BACKEND/'):
                path = '02_BACKEND/semantic_runtime/' + path
            if path in pinned:
                paths.add(path)
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    entries, rejected = build()
    # JSON in a Python module is intentionally avoided: importing the catalogue
    # requires only Python and the generated file is included by engine pins.
    content = ('"""Generated Oracle plans. Run 06_TOOLS/maintenance/prepare_oracle_queries.py.\n'
               'Do not edit plans; update shared query sources/dynamic families and regenerate.\n"""\n'
               'SOURCES = ' + pprint.pformat(source_hashes(entries), sort_dicts=False) + '\n\n'
               'PLANS = ' + pprint.pformat(entries, width=120, sort_dicts=False) + '\n')
    target = ROOT / '02_BACKEND/semantic_runtime/oracle_query_plans.py'
    if args.check:
        if not target.exists() or target.read_text() != content:
            raise SystemExit('Oracle query plans are stale; regenerate before serving/deploying')
    else:
        target.write_text(content)
    if args.report:
        args.report.write_text(json.dumps({'plans': len(entries), 'rejected_fragments': rejected,
            'generated_sha256': hashlib.sha256(content.encode()).hexdigest()}, ensure_ascii=False, indent=2) + '\n')
    print(('Checked' if args.check else 'Prepared'), len(entries), 'Oracle query plans')


if __name__ == '__main__':
    main()
