"""Bind prebuilt Oracle plans to a request's declared, authorized projections.

No SQL parser/transpiler is loaded here. The shipped catalogue determines SQL
structure; this module fills schema, bind, scope and CLOB/empty-value slots.
Unknown query shapes fail before an Oracle request, without a legacy fallback.
"""
from __future__ import annotations

import json
import re
import hashlib
import math
from functools import lru_cache
from pathlib import Path

from .oracle_dp_io import DPError
from .oracle_query_catalog import LOOKUP_ENCODING, lookup_key
from .oracle_query_shape import shape


@lru_cache(maxsize=1)
def validate_sources():
    """Reject stale plans even when engine pins were updated independently."""
    from .oracle_query_plans import SOURCES
    root = Path(__file__).resolve().parents[2]
    for relative, expected in SOURCES.items():
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise DPError('QUERY_SQL_STALE: regenerate prepared Oracle queries for ' + relative)


def quoted(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_0-9]+', name):
        raise DPError('QUERY_SQL_IDENTIFIER: undeclared identifier syntax')
    return '"' + name + '"'


class Scope:
    def __init__(self, parent=None):
        self.parent = parent
        self.relations = {}
        self.outputs = {}
        self.projections = {}
        self.order_flags = {}
        self.flags = {}
        self.using = set()
        self.ctes = {}

    def column(self, qualifier, name):
        if qualifier:
            relation = self.relations.get(qualifier)
            if relation is not None:
                if name not in relation['columns']:
                    raise DPError('QUERY_SQL_COLUMN: undeclared column ' + name)
                return qualifier, relation['columns'][name]
        else:
            matches = [(alias, r['columns'][name]) for alias, r in self.relations.items() if name in r['columns']]
            if len(matches) == 1 or matches and name in self.using:
                return matches[0]
            if len(matches) > 1:
                raise DPError('QUERY_SQL_COLUMN: ambiguous column ' + name)
        if self.parent is not None:
            return self.parent.column(qualifier, name)
        raise DPError('QUERY_SQL_COLUMN: undeclared column ' + name)


class Binding:
    def __init__(self, connection, slots, lists):
        self.connection = connection
        self.slots, self.lists = slots, lists
        self.binds = {}
        self.view_number = 0

    def bind(self, name, value):
        kind = ('NUMBER' if isinstance(value, (int, float)) else
                'CLOB' if isinstance(value, str) and len(value.encode()) > 4000 else 'VARCHAR2')
        previous = self.binds.get(name)
        if previous is not None and previous != (value, kind):
            raise DPError('QUERY_SQL_BINDS: conflicting prepared bind')
        self.binds[name] = value, kind
        return ':' + name

    def scalar(self, node):
        if node and node[0] == 'slot' and node[1] not in self.lists:
            return self.slots[node[1]][0][1]
        if node and node[0] == 'literal':
            return node[1] if node[2] else float(node[1]) if '.' in node[1] else int(node[1])
        return None

    def spec(self, node, scope):
        if node and node[0] == 'column':
            if not node[1] and not scope.relations and node[2] in scope.outputs:
                return scope.outputs[node[2]]
            return scope.column(node[1], node[2])[1]
        return {}

    def flag(self, node, scope):
        if self.connection.asset != 'oracle-source' and node and node[0] == 'column':
            alias, spec = scope.column(node[1], node[2])
            if spec.get('has_empty'):
                return scope.flags.get((alias, node[2]), quoted(alias) + '.' + quoted('a8_empty_' + node[2]))
        return None

    @staticmethod
    def chunks(text, spec):
        count = max(1, math.ceil(spec.get('max_bytes', 4000) / 1000))
        if count > 900:
            raise DPError('QUERY_SQL_CLOB: use a bounded identity query for this large DISTINCT/order key')
        # A CLOB's fixed UCS2 offsets may bisect a supplementary character.
        # Match complete characters instead; n includes newlines. Each scalar
        # is at most 1000 Unicode characters (4000 AL32UTF8 bytes).
        return ["CAST(REGEXP_SUBSTR(" + text + ",'.{1,1000}',1," + str(i + 1) + ",'cn') AS VARCHAR2(4000))"
                for i in range(count)]

    def distinct(self, text, columns, flags, root, parent):
        """Lossless DISTINCT of long IDs using every bounded scalar chunk."""
        inner, outer = [], []
        for i, (name, spec) in enumerate(columns.items()):
            value = 'd.' + quoted(name)
            if spec.get('max_bytes', 0) > 4000:
                parts = self.chunks(value, spec)
                names = ['a8_d' + str(i) + '_' + str(j) for j in range(len(parts))]
                inner += [part + ' AS ' + quoted(n) for part, n in zip(parts, names)]
                rebuilt = ' || '.join(('TO_CLOB(z.' + quoted(n) + ')' if j == 0 else 'z.' + quoted(n)) for j, n in enumerate(names))
                outer.append(rebuilt + ' AS ' + quoted(name))
            else:
                inner.append(value + ' AS ' + quoted(name))
                outer.append('z.' + quoted(name) + ' AS ' + quoted(name))
        for i, _ in flags:
            name = 'a8_e' + str(i) if root else 'a8_empty_' + list(columns)[i]
            inner.append('d.' + quoted(name) + ' AS ' + quoted(name))
            outer.append('z.' + quoted(name) + ' AS ' + quoted(name))
        if len(inner) > 1000:
            raise DPError('QUERY_SQL_CLOB: DISTINCT projection exceeds Oracle column budget')
        sql = 'SELECT ' + ','.join(outer) + ' FROM (SELECT DISTINCT ' + ','.join(inner) + ' FROM (' + text + ') d) z'
        return sql

    def equal(self, left, right, scope, *, different=False):
        if left[0] in ('slot', 'literal') and right[0] == 'column':
            left, right = right, left
        a, b = self.expression(left, scope), self.expression(right, scope)
        value = self.scalar(right)
        if value == '':
            if different:
                return a + ' IS NOT NULL'
            flag = self.flag(left, scope)
            return flag + ' = 1' if flag else '1 = 0'
        if (self.spec(left, scope).get('max_bytes', 0) > 4000 or
                self.spec(right, scope).get('max_bytes', 0) > 4000 or
                isinstance(value, str) and len(value.encode()) > 4000):
            return 'DBMS_LOB.COMPARE(' + a + ',' + b + ') ' + ('<>' if different else '=') + ' 0'
        return a + (' <> ' if different else ' = ') + b

    def expression(self, node, scope, *, order=False):
        kind = node[0]
        if kind == 'column':
            if order and not node[1] and node[2] in scope.outputs:
                return quoted(node[2])
            alias, _ = scope.column(node[1], node[2])
            return quoted(alias) + '.' + quoted(node[2])
        if kind == 'star':
            return quoted(node[1]) + '.*' if node[1] else '*'
        if kind == 'slot':
            if node[1] in self.lists:
                raise DPError('QUERY_SQL_BINDS: list slot outside IN predicate')
            return self.bind(*self.slots[node[1]][0])
        if kind == 'literal':
            return "'" + node[1].replace("'", "''") + "'" if node[2] else node[1]
        if kind == 'null':
            return 'NULL'
        if kind == 'paren':
            return '(' + self.expression(node[1], scope, order=order) + ')'
        if kind in ('and', 'or'):
            return '(' + self.expression(node[1], scope) + ' ' + kind.upper() + ' ' + self.expression(node[2], scope) + ')'
        if kind in ('eq', 'neq'):
            return self.equal(node[1], node[2], scope, different=kind == 'neq')
        if kind == 'is_null':
            text = self.expression(node[1], scope) + ' IS NULL'
            flag = self.flag(node[1], scope)
            return '(' + text + ' AND ' + flag + ' <> 1)' if flag else text
        if kind == 'boolean_number':
            condition = self.expression(node[1], scope)
            # SQLite comparisons return NULL for unknown, not zero.
            return '(CASE WHEN ' + condition + ' THEN 1 WHEN NOT (' + condition + ') THEN 0 ELSE NULL END)'
        if kind == 'in':
            lhs = self.expression(node[1], scope)
            if node[3]:
                return lhs + ' IN ' + self.expression(node[3], scope)
            values = []
            for item in node[2]:
                if item[0] == 'slot' and item[1] in self.lists:
                    values.extend((self.bind(n, v), v) for n, v in self.slots[item[1]])
                else:
                    values.append((self.expression(item, scope), self.scalar(item)))
            if not values:
                return '1 = 0'
            flag = self.flag(node[1], scope)
            has_empty, has_null = any(v == '' for _, v in values), any(v is None for _, v in values)
            if flag:
                values = [(text, value) for text, value in values if value != '']
            def preserve_empty(predicate):
                if not flag:
                    return predicate
                empty = '1 = 1' if has_empty else 'NULL = 1' if has_null else '1 = 0'
                return '((' + flag + ' = 1 AND ' + empty + ') OR (' + flag + ' <> 1 AND (' + predicate + ')))'
            if not values:
                return preserve_empty('CASE WHEN ' + lhs + ' IS NULL THEN NULL ELSE 0 END = 1')
            if self.spec(node[1], scope).get('max_bytes', 0) > 4000 or any(isinstance(v, str) and len(v.encode()) > 4000 for _, v in values):
                return preserve_empty('(' + ' OR '.join('DBMS_LOB.COMPARE(' + lhs + ',' + val + ')=0' for val, _ in values) + ')')
            # Oracle 19c permits at most 1000 scalar expressions per IN list.
            chunks = [lhs + ' IN (' + ','.join(v for v, _ in values[i:i+1000]) + ')'
                      for i in range(0, len(values), 1000)]
            return preserve_empty(chunks[0] if len(chunks) == 1 else '(' + ' OR '.join(chunks) + ')')
        if kind == 'json':
            path = self.scalar(node[2])
            if not isinstance(path, str) or not path.startswith('$'):
                raise DPError('QUERY_SQL_JSON: prepared JSON path required')
            spec = self.spec(node[1], scope).get('json_paths', {}).get(path, {})
            types = set(spec.get('types', [])) - {'null'}
            if types and types <= {'array', 'object'}:
                function, datatype = 'JSON_QUERY', 'CLOB'
            elif types and types <= {'integer', 'real'}:
                function, datatype = 'JSON_VALUE', 'NUMBER'
            else:
                function = 'JSON_VALUE'
                datatype = 'CLOB' if spec.get('max_bytes', 0) > 4000 or path in ('$.text', '$.body') else 'VARCHAR2(4000)'
            text = function + '(' + self.expression(node[1], scope) + ", '" + path.replace("'", "''") + "' RETURNING " + datatype + ' NULL ON EMPTY ERROR ON ERROR)'
            if function == 'JSON_QUERY':
                # A SQLite JSON extraction of an array/object is JSON text.
                # Concatenation removes Oracle's implicit FORMAT JSON marker
                # before the result is packed into the outer JSON_ARRAY.
                return '(' + text + " || TO_CLOB(''))"
            return "CASE " + text + " WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END" if types == {'boolean'} else text
        if kind == 'normalized':
            if len(node) != 2 or node[1][0] != 'column' or node[1][2] != 'text' or self.connection.asset != 'oracle-source':
                raise DPError('QUERY_SQL_FUNCTION: unsupported normalization expression')
            alias, _ = scope.column(node[1][1], 'text')
            return quoted(alias) + '."a8_normalized_text"'
        if kind == 'order':
            return self.ordering(node, scope, aliases=True)
        if kind == 'window':
            parts = []
            if node[2]:
                partition = [self.expression(n, scope) for n in node[2]]
                partition += [flag for n in node[2] if (flag := self.flag(n, scope))]
                parts.append('PARTITION BY ' + ','.join(partition))
            if node[3]:
                parts.append('ORDER BY ' + ','.join(self.ordering(n, scope) for n in node[3]))
            return self.expression(node[1], scope) + ' OVER (' + ' '.join(parts) + ')'
        if kind == 'case':
            text = 'CASE' + (' ' + self.expression(node[1], scope) if node[1] else '')
            for condition, value in node[2]:
                text += ' WHEN ' + self.expression(condition, scope) + ' THEN ' + self.expression(value, scope)
            if node[3]:
                text += ' ELSE ' + self.expression(node[3], scope)
            return text + ' END'
        if kind == 'query':
            text, _, _ = self.query(node[1], parent=scope, ctes=scope.ctes)
            return '(' + text + ')'
        if kind == 'sql':
            values = [self.expression(child, scope, order=order) for child in node[2]]
            return re.sub(r'__a8_slot_(\d+)__', lambda m: values[int(m[1])], node[1])
        raise DPError('QUERY_SQL_PLAN: unsupported prepared expression')

    def ordering(self, node, scope, *, aliases=False):
        expression = node[1]
        original = expression
        if aliases and expression[0] == 'column' and not expression[1]:
            original = scope.projections.get(expression[2], expression)
        direction = ' DESC' if node[2] else ' ASC'
        suffix = direction + (' NULLS FIRST' if node[3] else ' NULLS LAST')
        if self.spec(original, scope).get('max_bytes', 0) > 4000:
            text = ','.join(part + suffix for part in self.chunks(self.expression(original, scope), self.spec(original, scope)))
        else:
            text = self.expression(expression, scope, order=aliases) + suffix
        flag = (scope.order_flags.get(original[2]) if aliases and original[0] == 'column' and not scope.relations
                else self.flag(original, scope))
        if flag:
            text += ',' + flag + direction
        return text

    def indexed(self, node, alias, table, scope):
        """Retain physical key narrowing and exact logical predicates together."""
        specs = table['columns']
        encoding = table.get('lookup_encoding')
        if encoding not in (None, LOOKUP_ENCODING):
            raise DPError('QUERY_LOOKUP_ENCODING: unsupported auxiliary key encoding')
        columns = {}
        for physical, choices in [('LOOKUP_ID', ('id', 'key', 'term_id', 'node_id')),
                                   ('OWNER_ID', ('source_id', 'reference_id', 'definition_id')),
                                   ('TARGET_ID', ('target_id', 'target', 'parent_id'))]:
            logical = next((name for name in choices if name in specs), None)
            spec = specs.get(logical, {})
            if logical and spec.get('type') == 'text' and not spec.get('has_null') and not spec.get('has_empty'):
                columns[logical] = physical

        def column(expression):
            if expression and expression[0] == 'column':
                resolved, _ = scope.column(expression[1], expression[2])
                if resolved == alias and expression[2] in columns:
                    return 'r.' + columns[expression[2]]
            return None

        def value(expression):
            actual = self.scalar(expression)
            if not isinstance(actual, str) or not actual:
                return None
            if encoding == LOOKUP_ENCODING and len(actual.encode()) > 512:
                return self.bind('a8_index_key' + str(len(self.binds)), lookup_key(actual))
            return self.expression(expression, scope)

        def push(expression):
            if not expression:
                return None
            kind = expression[0]
            if kind == 'paren':
                return push(expression[1])
            if kind in ('and', 'or'):
                a, b = push(expression[1]), push(expression[2])
                if a and b:
                    return '(' + a + ' ' + kind.upper() + ' ' + b + ')'
                return a or b if kind == 'and' else None
            if kind == 'eq':
                a = column(expression[1])
                b = value(expression[2]) if a else None
                if a is None:
                    a = column(expression[2])
                    b = value(expression[1]) if a else None
                return a + ' = ' + b if a and b else None
            if kind == 'in':
                a = column(expression[1])
                if a is None:
                    return None
                items = expression[2]
                values = None
                if len(items) == 1 and items[0][0] == 'slot' and items[0][1] in self.lists:
                    values = [v for _, v in self.slots[items[0][1]]]
                elif expression[3]:
                    sub = expression[3]
                    plan = sub[1] if sub[0] == 'query' else {}
                    source = plan.get('from')
                    if (source and source[0] == 'array' and len(plan['columns']) == 1
                            and plan['columns'][0][0] == ['column', '', 'value']
                            and not any(plan.get(k) for k in ('where', 'joins', 'group', 'limit', 'offset', 'distinct'))):
                        raw = self.scalar(source[2])
                        try:
                            values = json.loads(raw) if isinstance(raw, str) else None
                        except ValueError:
                            values = None
                elif items:
                    values = [self.scalar(item) for item in items]
                if (not isinstance(values, list) or not 1 <= len(values) <= 1000
                        or any(not isinstance(v, str) or not v for v in values)):
                    return None
                rendered = [self.bind('a8_index_key' + str(len(self.binds)), lookup_key(v) if encoding == LOOKUP_ENCODING else v)
                            for v in values]
                return a + ' IN (' + ','.join(rendered) + ')'
            return None
        return push(node)

    def query(self, plan, parent=None, ctes=None, *, root=False, union_branch=False):
        scope = Scope(parent)
        ctes = dict(ctes or {})
        prefix = []
        for name, subplan in plan.get('ctes', []):
            text, columns, _ = self.query(subplan, parent=parent, ctes=ctes)
            prefix.append(quoted(name) + ' AS (' + text + ')')
            ctes[name] = columns
        scope.ctes = ctes
        if plan['kind'] == 'union':
            left, columns, flags = self.query(plan['left'], parent, ctes, root=root, union_branch=True)
            right, other, other_flags = self.query(plan['right'], parent, ctes, root=root, union_branch=True)
            if len(columns) != len(other) or [i for i, _ in flags] != [i for i, _ in other_flags]:
                raise DPError('QUERY_SQL_COLUMNS: union column counts differ')
            clob_distinct = plan['distinct'] and any(v.get('max_bytes', 0) > 4000 for v in columns.values())
            text = left + (' UNION ' if plan['distinct'] and not clob_distinct else ' UNION ALL ') + right
            scope.outputs = columns
            scope.order_flags = {list(columns)[i]: quoted('a8_e' + str(i) if root else 'a8_empty_' + list(columns)[i]) for i, _ in flags}
        else:
            relations = ([plan['from']] if plan['from'] else []) + [j[0] for j in plan['joins']]
            for relation in relations:
                kind, alias = relation[:2]
                if kind == 'table':
                    name = relation[2]
                    if name in ctes:
                        scope.relations[alias] = {'columns': ctes[name], 'text': quoted(name)}
                    else:
                        if name not in self.connection.tables:
                            raise DPError('QUERY_SQL_TABLE: undeclared relational table')
                        scope.relations[alias] = {'columns': self.connection.tables[name][1]['columns'], 'table': name}
                elif kind == 'array':
                    scope.relations[alias] = {'columns': {'value': {'type': 'text', 'max_bytes': 4000}},
                        'text': "JSON_TABLE(" + self.expression(relation[2], scope) + ", '$[*]' COLUMNS(\"value\" VARCHAR2(4000) PATH '$'))"}
                else:
                    text, columns, _ = self.query(relation[2], parent, ctes)
                    scope.relations[alias] = {'columns': columns, 'text': '(' + text + ')'}
            scope.using = {name for join in plan['joins'] for name in join[3]}
            projections = []
            for node, name in plan['columns']:
                if isinstance(name, list):
                    path = self.scalar(name[1])
                    match = re.fullmatch(r'\$\.([A-Za-z_][A-Za-z_0-9]*)', path or '')
                    name = match[1] if match else name[2]
                if node[0] == 'star':
                    selected = [(node[1], scope.relations[node[1]])] if node[1] else scope.relations.items()
                    seen = set()
                    for alias, relation in selected:
                        for column in relation['columns']:
                            if column in scope.using and column in seen:
                                continue
                            projections.append((['column', alias, column], column))
                            seen.add(column)
                else:
                    projections.append((node, name))
            columns = {}
            for node, name in projections:
                if name in columns:
                    raise DPError('QUERY_SQL_COLUMNS: output names must be unambiguous')
                columns[name] = self.spec(node, scope)
            scope.outputs = columns
            scope.projections = {name: node for node, name in projections}
            clob_distinct = plan['distinct'] and any(v.get('max_bytes', 0) > 4000 for v in columns.values())
            fields = [self.expression(node, scope) + ' AS ' + quoted(name) for node, name in projections]
            flags = [(i, self.flag(node, scope)) for i, (node, _) in enumerate(projections)]
            flags = [(i, flag) for i, flag in flags if flag]
            fields += [flag + ' AS ' + quoted('a8_e' + str(i) if root else 'a8_empty_' + projections[i][1]) for i, flag in flags]

            def render_relation(relation):
                alias = relation[1]
                item = scope.relations[alias]
                if 'text' in item:
                    return item['text'] + ' ' + quoted(alias)
                name = item['table']
                number = self.view_number
                self.view_number += 1
                text, binds = self.connection._view(name, number)
                for n, v, t in binds:
                    if n in self.binds:
                        raise DPError('QUERY_SQL_BINDS: duplicate view parameter')
                    self.binds[n] = v, t
                if self.connection.asset != 'oracle-source':
                    pushed = self.indexed(plan.get('where'), alias, self.connection.tables[name][1], scope)
                    if pushed:
                        text += ' AND (' + pushed + ')'
                return '(' + text + ') ' + quoted(alias)

            text = 'SELECT ' + ('DISTINCT ' if plan['distinct'] and not clob_distinct else '') + ','.join(fields)
            text += ' FROM ' + (render_relation(plan['from']) if plan['from'] else 'DUAL')
            preceding = [plan['from'][1]] if plan['from'] else []
            for relation, kind, on, using in plan['joins']:
                if not kind and on is None and not using:
                    text += ' CROSS JOIN ' + render_relation(relation)
                else:
                    text += ' ' + (kind + ' ' if kind else '') + 'JOIN ' + render_relation(relation)
                    if on:
                        text += ' ON ' + self.expression(on, scope)
                    if using:
                        # Oracle forbids qualified references to USING keys;
                        # shared consumers explicitly use d.document_id etc.
                        if kind.startswith(('RIGHT', 'FULL')):
                            raise DPError('QUERY_SQL_JOIN: right/full USING needs an explicit prepared projection')
                        predicates = []
                        for name in using:
                            left = next((a for a in preceding if name in scope.relations[a]['columns']), None)
                            if left is None or name not in scope.relations[relation[1]]['columns']:
                                raise DPError('QUERY_SQL_JOIN: undeclared USING key')
                            predicates.append(quoted(left) + '.' + quoted(name) + ' = ' + quoted(relation[1]) + '.' + quoted(name))
                        text += ' ON ' + ' AND '.join(predicates)
                preceding.append(relation[1])
            if plan.get('where'):
                text += ' WHERE ' + self.expression(plan['where'], scope)
            if plan['group']:
                groups = []
                for node in plan['group']:
                    if node[0] == 'literal' and not node[2] and node[1].isdigit():
                        position = int(node[1])
                        if not 1 <= position <= len(projections):
                            raise DPError('QUERY_SQL_GROUP: projection position out of range')
                        node = projections[position-1][0]
                    groups.append(node)
                grouping = [self.expression(n, scope) for n in groups]
                grouping += [flag for n in groups if (flag := self.flag(n, scope))]
                grouping += [flag for _, flag in flags]
                text += ' GROUP BY ' + ','.join(dict.fromkeys(grouping))
            if plan.get('having'):
                text += ' HAVING ' + self.expression(plan['having'], scope)
            if root and not union_branch and not plan['order'] and not plan['group'] and not plan['aggregate'] and not clob_distinct:
                if plan['distinct']:
                    text += ' ORDER BY ' + ','.join(quoted(n) for n in columns)
                else:
                    aliases = [alias for alias, r in scope.relations.items() if 'table' in r]
                    if aliases:
                        text += ' ORDER BY ' + ','.join(quoted(a) + '."a8_row_id"' for a in aliases)
        if clob_distinct:
            text = self.distinct(text, columns, flags, root, parent)
            # The outer projection has the same public columns and hidden
            # empty markers. Further ordering/paging uses that projection.
            text = 'SELECT * FROM (' + text + ') "a8_distinct"'
            scope = Scope(parent)
            scope.ctes = ctes
            scope.outputs = columns
            scope.relations['a8_distinct'] = {'columns': columns}
            scope.projections = {name: ['column', 'a8_distinct', name] for name in columns}
            scope.flags = {('a8_distinct', list(columns)[i]): '"a8_distinct".' + quoted('a8_e' + str(i) if root else 'a8_empty_' + list(columns)[i]) for i, _ in flags}
            if root and not plan['order'] and not union_branch:
                text += ' ORDER BY ' + ','.join(self.ordering(['order', ['column', '', n], False, True], scope, aliases=True) for n in columns)
        if plan['order']:
            text += ' ORDER BY ' + ','.join(self.expression(n, scope, order=True) for n in plan['order'])
        if plan.get('offset'):
            text += ' OFFSET ' + self.expression(plan['offset'], scope) + ' ROWS'
        if plan.get('limit'):
            text += ' FETCH NEXT ' + self.expression(plan['limit'], scope) + ' ROWS ONLY'
        if prefix:
            text = 'WITH ' + ','.join(prefix) + ' ' + text
        return text, columns, flags


def prepare(connection, statement, parameters):
    from .oracle_query_plans import PLANS
    validate_sources()
    key, _, slots, lists = shape(statement, parameters)
    entry = PLANS.get(key)
    if entry is None:
        raise DPError('QUERY_SQL_NOT_PREPARED: query=' + key + '; regenerate the Oracle query catalogue')
    binding = Binding(connection, slots, lists)
    text, columns, flags = binding.query(entry['plan'], root=True)
    fields = [quoted('x') + '.' + quoted(name) for name in columns]
    fields += ['"x"."a8_e' + str(i) + '"' for i, _ in flags]
    packed = 'SELECT TO_CLOB(JSON_ARRAY(' + ','.join(fields) + ' NULL ON NULL RETURNING CLOB)) AS body FROM (' + text + ') "x"'
    # Eliminated empty comparisons/JSON-path slots do not produce unused binds.
    used = set(re.findall(r':(a8_[A-Za-z_0-9]+)', packed))
    binds = [(n, v, t) for n, (v, t) in binding.binds.items() if n in used]
    return list(columns), packed, binds, [i for i, _ in flags]
