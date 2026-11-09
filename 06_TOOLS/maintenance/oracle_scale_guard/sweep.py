"""Execute every Oracle-reachable prepared plan with edge-case values (read-only).

For each original SQLite statement that has a shipped plan and whose tables are all in one
published Oracle asset (or the source tables), run Connection.execute exactly as the
shared consumers do, under three column-size profiles:
  fixture  - the published fixture's own column shapes;
  gold     - shapes measured on the local real-data Gold release (21 documents);
  worst    - every text column >4000 bytes, with empty strings and NULLs.
Cases per statement: sample values, empty, long (>4000 bytes), special characters, NULL,
numeric 0/1e9, IN lists of 1000 and 1001 items.
"""
import copy
import json
import re
import sys
import time
import traceback
from pathlib import Path

LONG = 'ㄱ' * 1400  # 4200 UTF-8 bytes -> CLOB comparison path
SPECIAL = "it's 😀 %_\\ 「제1조」\n\t"


def walk(node, parent=None, grand=None):
    if isinstance(node, dict):
        for v in node.values():
            yield from walk(v, node, parent)
    elif isinstance(node, list):
        yield node, parent, grand
        for v in node:
            yield from walk(v, node, parent)


def slot_contexts(plan, slot):
    """('int'|'text'|'list', column-name or None) usage hints for one slot."""
    hints = []
    for n, parent, grand in walk(plan):
        if not (isinstance(n, list) and n[:2] == ['slot', slot]):
            continue
        if isinstance(parent, list) and parent and not isinstance(parent[0], str):
            # n sits in a children/items list: the operator is the grandparent
            parent = grand
        if isinstance(parent, dict):
            for key in ('limit', 'offset'):
                if parent.get(key) is n:
                    hints.append(('int', None))
        elif isinstance(parent, list) and parent:
            kind = parent[0]
            if kind in ('eq', 'neq'):
                other = parent[2] if parent[1] is n else parent[1]
                hints.append(('col', other[2] if isinstance(other, list) and other and other[0] == 'column' else None))
            elif kind == 'in':
                hints.append(('col', parent[1][2] if isinstance(parent[1], list) and parent[1][0] == 'column' else None))
            elif kind == 'sql':
                text = parent[1]
                index = next((i for i, c in enumerate(parent[2]) if c is n), -1)
                token = '__a8_slot_%d__' % index
                around = text[max(0, text.find(token) - 60): text.find(token) + 60]
                columns = [c for c in parent[2] if c is not n and isinstance(c, list) and c and c[0] == 'column']
                if columns and not re.search(r'CAST\(', around, re.I):
                    hints.append(('col', columns[0][2]))  # compared with a column: use that column's type
                elif re.search(r'CAST\(.*AS (?:INT|NUMBER)|[<>]=?\s*' + token + '|' + token + r'\s*[<>]=?|[-+*/]\s*' + token, around, re.I):
                    hints.append(('int', None))
                else:
                    hints.append(('text', None))
            elif kind == 'array':
                hints.append(('array', None))
    return hints


class Sweep:
    def __init__(self, request, records, code_root, gold_release=None):
        from semantic_runtime.oracle_query_db import Connection
        from semantic_runtime.oracle_query_store import SourceConnection
        from semantic_runtime.oracle_query_plans import PLANS
        self.request, self.records, self.PLANS = request, records, PLANS
        self.code = Path(code_root)
        self.connections = {}
        for kind, spec in request.records.manifest['tables'].items():
            if 'columns' in spec and spec.get('asset') not in self.connections:
                self.connections[spec['asset']] = Connection(request, spec['asset'])
        self.connections['oracle-source'] = SourceConnection(request)
        self.gold = {}
        if gold_release:
            for spec in gold_release['tables'].values():  # {'tables': {kind: {asset, table, columns}}}
                if spec.get('table') and 'columns' in spec:
                    self.gold[(spec['asset'], spec['table'])] = spec['columns']
        self.samples = {}
        self.results = []
        import os
        measured = Path(os.environ.get('GUARD_WIDTHS', str(Path(__file__).with_name('widths-local-1547.json'))))
        self.fullgen = json.loads(measured.read_text()) if measured.exists() else {}

    def sample(self, connection, table):
        key = (connection.asset, table)
        if key not in self.samples:
            values = {}
            if connection.asset == 'oracle-source':
                values = {'document_id': ['d'], 'block_id': ['1'], 'unit_id': ['1'], 'name': ['모의승인규정']}
            else:
                kind = connection.tables[table][0]
                try:
                    rows = self.request.records.page(kind, limit=5)['rows']
                except Exception:
                    rows = []
                for row in rows:
                    for column, value in row.items():
                        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                            values.setdefault(column, []).append(value)
            self.samples[key] = values
        return self.samples[key]

    def targets(self, tables):
        found = []
        for asset, connection in self.connections.items():
            if set(tables) <= set(connection.tables):
                found.append(connection)
        return found

    def profile(self, connection, name):
        clone = copy.copy(connection)
        clone.tables = copy.deepcopy(connection.tables)
        for table, (kind, spec) in clone.tables.items():
            if name == 'gold':
                asset = connection.asset if connection.asset != 'oracle-source' else None
                columns = self.gold.get((asset, table)) if asset else None
                if columns:
                    for column, shape in columns.items():
                        if column in spec['columns']:
                            spec['columns'][column] = {**spec['columns'][column], **shape}
            elif name == 'fullgen':
                # gold shapes, then byte widths measured on the full local generation (1,547 documents)
                asset = connection.asset if connection.asset != 'oracle-source' else None
                columns = self.gold.get((asset, table)) if asset else None
                if columns:
                    for column, shape in columns.items():
                        if column in spec['columns']:
                            spec['columns'][column] = {**spec['columns'][column], **shape}
                measured = self.fullgen.get(str(asset) + ':' + table, {}).get('max_bytes', {})
                for column, size in measured.items():
                    if column in spec['columns'] and size is not None and spec['columns'][column].get('type') == 'text':
                        spec['columns'][column]['max_bytes'] = max(size, spec['columns'][column].get('max_bytes', 0))
            elif name == 'worst':
                for column, shape in spec['columns'].items():
                    if shape.get('type') == 'text':
                        shape.update(max_bytes=max(5000, shape.get('max_bytes', 0)), has_empty=True, has_null=True)
        if hasattr(clone, '_schema_results'):
            clone._schema_results = {}
        return clone

    def params(self, statement, plan, connection, tables, case):
        from semantic_runtime.oracle_sql_tokens import tokens
        from semantic_runtime.oracle_query_shape import shape
        count = sum(t.text == '?' for t in tokens(statement))
        markers = ['m%d' % i for i in range(count)]
        _, _, bound, _ = shape(statement, markers)
        values = []
        for i in range(count):
            slot = next(s for s, pairs in bound.items() if any(n == 'a8_p%d' % i for n, _ in pairs))
            hints = slot_contexts(plan, slot)
            numeric = any(h[0] == 'int' for h in hints)
            column = next((h[1] for h in hints if h[0] == 'col' and h[1]), None)
            if any(h[0] == 'array' for h in hints):
                base = self.pick(connection, tables, column or 'id')
                values.append(json.dumps([base] if case != 'empty' else []))
                continue
            if column:
                spec = next((connection.tables[t][1]['columns'].get(column) for t in tables if column in connection.tables[t][1]['columns']), None)
                if spec and spec.get('type') in ('integer', 'real'):
                    numeric = True
            if numeric:
                values.append({'zero': 0, 'big': 10 ** 9}.get(case, 5))
                continue
            values.append({'empty': '', 'long': LONG, 'special': SPECIAL, 'null': None}.get(case) if case in ('empty', 'long', 'special', 'null')
                          else self.pick(connection, tables, column))
        return values

    def pick(self, connection, tables, column):
        for table in tables:
            sample = self.sample(connection, table)
            if column in sample:
                return sample[column][0]
        return 'd' if column in (None, 'document_id', 'source') else 'x'

    def run(self, inventory, *, profiles=('fixture', 'gold', 'worst'), cases=('sample', 'empty', 'long', 'special', 'null', 'zero', 'big', 'list1000', 'list1001')):
        for item in inventory['plans']:
            if not item['tables'] or not item['statements']:
                continue
            for statement_info in item['statements']:
                statement = statement_info['statement']
                for base in self.targets(item['tables']):
                    for profile in profiles:
                        connection = self.profile(base, profile)
                        for case in cases:
                            text, list_at = statement, None
                            if case.startswith('list'):
                                match = re.search(r'\bIN\s*\(\s*\?\s*\)', statement, re.I)
                                if not match:
                                    continue
                                n = int(case[4:])
                                list_at = statement[:match.start()].count('?')
                                text = statement[:match.start()] + 'IN (' + ','.join('?' * n) + ')' + statement[match.end():]
                            self.one(item, statement_info, text, connection, profile, case, list_at)

    def one(self, item, statement_info, text, connection, profile, case, list_at=None):
        entry = {'key': item['key'][:16], 'origin': statement_info['origin'], 'asset': connection.asset, 'profile': profile,
                 'case': case, 'error': None, 'rows': None}
        started = time.monotonic()
        before = len(self.records.sql)
        try:
            plan = self.PLANS[item['key']]['plan']
            if case.startswith('list'):
                from semantic_runtime.oracle_sql_tokens import tokens
                from semantic_runtime.oracle_query_shape import shape
                count = sum(t.text == '?' for t in tokens(text))
                key = shape(text, [None] * count)[0]
                plan = self.PLANS[key]['plan']
            params = self.params(text, plan, connection, item['tables'], 'sample' if case.startswith('list') else case)
            if case.startswith('list'):
                # vary list members so Oracle sees n distinct binds
                n = int(case[4:])
                prefix = list_at
                base_value = params[prefix]
                params[prefix:prefix + n] = [base_value if j == 0 else (str(base_value) + '#' + str(j) if isinstance(base_value, str) else base_value) for j in range(n)]
            entry['params'] = [p if not isinstance(p, str) or len(p) < 80 else p[:40] + '...(%d)' % len(p) for p in params[:8]]
            cursor = connection.execute(text, params)
            entry['rows'] = len(cursor.fetchall())
        except Exception as exc:
            entry['error'] = type(exc).__name__ + ': ' + str(exc)[:300]
            frames = [l for l in traceback.format_exc().splitlines() if l.strip().startswith('File ')][-3:]
            entry['frames'] = [f.strip() for f in frames]
        entry['ms'] = round((time.monotonic() - started) * 1000, 1)
        sent = self.records.sql[before:]
        entry['sql_sent'] = len(sent)
        entry['with_and_number'] = any(s['with_and_number'] for s in sent)
        entry['number_binds'] = sorted({n for s in sent for n in s['number_binds']})
        entry['max_payload'] = max([s['payload_bytes'] for s in sent] or [0])
        entry['max_binds'] = max([s['binds'] for s in sent] or [0])
        self.results.append(entry)
