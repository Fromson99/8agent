"""Bounded ORDS transport and immutable Oracle row transfer. No import-time IO."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import time
from .physical_mapping import names

REVISION = 'oracle-dp-io-v1'
OWNER = 'SIDDA'
TABLES = {'document': 'LEGAL_SRC_DOCUMENT_A', 'source_unit': 'LEGAL_SRC_SOURCE_UNIT_A',
          'block_payload': 'LEGAL_SRC_BLOCK_PAYLOAD_A'}
COLUMNS = {
    'document': ('DATASET_VERSION', 'DOCUMENT_ID', 'NAME', 'SOURCE_ARTIFACT_SHA256', 'SOURCE_JSON'),
    'source_unit': ('DATASET_VERSION', 'DOCUMENT_ID', 'UNIT_ID', 'PARENT_ID', 'SOURCE_JSON'),
    'block_payload': ('DATASET_VERSION', 'DOCUMENT_ID', 'BLOCK_ID', 'UNIT_ID', 'TEXT',
                      'SOURCE_ARTIFACT_SHA256', 'SOURCE_JSON', 'JSON_TEXT_ELIDED'),
}
KEYS = {'document': ('DATASET_VERSION', 'DOCUMENT_ID'),
        'source_unit': ('DATASET_VERSION', 'DOCUMENT_ID', 'UNIT_ID'),
        'block_payload': ('DATASET_VERSION', 'DOCUMENT_ID', 'BLOCK_ID')}
CLOBS = {'NAME', 'TEXT', 'SOURCE_JSON'}
LOB_UNITS = 1000  # <= 4000 UTF-8 bytes, including supplementary characters.
MAX_VALUE_BYTES = 64 * 1024 * 1024


class DPError(RuntimeError):
    pass


class BudgetPause(DPError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while data := f.read(4 * 1024 * 1024):
            h.update(data)
    return h.hexdigest()


def identifier(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', name):
        raise DPError('IDENTIFIER: invalid SQL identifier')
    return name


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as f:
        f.write(canonical(value) + '\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temporary, path)


def units(value):
    return len(value.encode('utf-16-le')) // 2


def response_item(response):
    body = response if isinstance(response, dict) else getattr(response, 'raw', None)
    if not isinstance(body, dict):
        candidate = getattr(response, 'json', None)
        body = candidate() if callable(candidate) else candidate
    if not isinstance(body, dict):
        raise DPError('RESPONSE_SHAPE: expected JSON object')
    items = body.get('items')
    for item in [body] + (items if isinstance(items, list) else []):
        if isinstance(item, dict) and (item.get('errorCode') not in (None, 0, '0') or
                                     item.get('errorMessage') or item.get('errorDetails')):
            code = str(item.get('errorCode', ''))
            raise DPError('ORACLE_ERROR: ' + (f'ORA-{int(code):05d}' if code.isdigit() else 'unclassified'))
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise DPError('RESPONSE_SHAPE: expected exactly one SQL result')
    if not any(k in items[0] for k in ('result', 'resultSet')):
        raise DPError('RESPONSE_SHAPE: SQL result is missing')
    return items[0]


class SQL:
    """One physical call per request; no retry. Journal excludes text/bind values."""
    def __init__(self, client, *, journal, binding, max_calls=1000000, seconds=3600, progress=None):
        self.client, self.binding = client, binding
        self.progress = progress
        self.journal = Path(journal)
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        self.max_calls, self.deadline, self.calls = max_calls, time.monotonic() + seconds, 0
        if self.journal.exists():
            with self.journal.open() as f:
                for line in f:
                    r = json.loads(line)
                    if r['binding'] != binding:
                        raise DPError('JOURNAL_BINDING: target differs')
                    self.calls = max(self.calls, r['call'])

    def event(self, status, **extra):
        with self.journal.open('a', encoding='utf-8') as f:
            f.write(canonical({'binding': self.binding, 'call': self.calls, 'at': time.time(),
                               'status': status, **extra}) + '\n')
            f.flush(); os.fsync(f.fileno())
        if self.progress is not None:
            self.progress.sql(status, self.calls)

    def request(self, statement, binds=(), *, write=False, limit=100):
        if self.calls >= self.max_calls or time.monotonic() >= self.deadline:
            raise BudgetPause('BUDGET_PAUSED: checkpoint retained; inspect and resume')
        payload = {'statementText': statement, 'offset': 0, 'limit': limit}
        if binds:
            payload['binds'] = [{'name': name, 'value': value, 'data_type': kind}
                                for name, value, kind in binds]
        if len(canonical(payload).encode()) > MAX_VALUE_BYTES + 1024 * 1024:
            raise DPError('REQUEST_SIZE: value exceeds explicit request bound; no truncation')
        self.calls += 1
        self.event('STARTED', write=write, sql_sha256=hashlib.sha256(statement.encode()).hexdigest())
        try:
            item = response_item(self.client.request('POST', self.client.SQL_PATH, json=payload))
        except Exception as exc:
            # Neither SDK exception strings nor raw responses are logged: both may contain credentials/content.
            safe = str(exc) if isinstance(exc, DPError) else type(exc).__name__
            self.event('WRITE_UNCONFIRMED' if write else 'READ_FAILED', error=safe)
            raise DPError(('WRITE_UNCONFIRMED: ' if write else 'READ_FAILED: ') + safe) from None
        self.event('ACKNOWLEDGED', write=write)
        return item

    def query(self, statement, binds=(), *, limit=100):
        if not statement.lstrip().upper().startswith('SELECT '):
            raise DPError('READ_ONLY: query accepts SELECT only')
        rs = self.request(statement, binds, limit=limit).get('resultSet')
        if not isinstance(rs, dict) or not isinstance(rs.get('items'), list) or rs.get('hasMore') is not False:
            raise DPError('PARTIAL_READ: incomplete/malformed result; narrow the SQL window')
        if int(rs.get('offset', -1)) != 0 or len(rs['items']) > limit:
            raise DPError('PARTIAL_READ: offset/row bound differs')
        if not all(isinstance(r, dict) for r in rs['items']):
            raise DPError('RESPONSE_ROW: expected object rows')
        return [{str(k).upper(): v for k, v in r.items()} for r in rs['items']]


def validate_row(kind, row):
    if set(row) != set(COLUMNS[kind]):
        raise DPError('ROW_COLUMNS: source/target columns differ')
    for col, value in row.items():
        if col in KEYS[kind] and (not isinstance(value, str) or not value):
            raise DPError('ROW_KEY: nonempty string required')
        if col == 'JSON_TEXT_ELIDED':
            if value is not None and (type(value) is not int or value not in (0, 1)):
                raise DPError('ROW_FLAG: expected 0/1/NULL')
            continue
        if value is not None:
            if not isinstance(value, str):
                raise DPError('ROW_TYPE: expected string/NULL')
            size = len(value.encode())
            maximum = MAX_VALUE_BYTES if col in CLOBS else 64 if col in ('DATASET_VERSION', 'SOURCE_ARTIFACT_SHA256') else 512
            if size > maximum or (col not in CLOBS and value == ''):
                raise DPError('ROW_SIZE: value cannot be transferred losslessly under the configured limit')


def bind_row(kind, row, prefix):
    expressions, binds = {}, []
    for i, col in enumerate(COLUMNS[kind]):
        value = row[col]
        if value is None:
            expressions[col] = 'NULL'
        elif col in CLOBS and value == '':
            expressions[col] = 'EMPTY_CLOB()'
        else:
            name = f'{prefix}_{i}'
            kind_sql = 'CLOB' if col in CLOBS else 'NUMBER' if col == 'JSON_TEXT_ELIDED' else 'VARCHAR2'
            expressions[col] = ':' + name
            binds.append((name, value, kind_sql))
    return expressions, binds


def equality(columns, row, expressions, column_name=lambda c:c):
    predicates = []
    for col in columns:
        value = row[col]
        physical = column_name(col)
        if value is None:
            predicates.append(f'{physical} IS NULL')
        elif col in CLOBS:
            predicates.append(f'{physical} IS NOT NULL AND ' +
                (f'DBMS_LOB.GETLENGTH({physical})=0' if value == '' else f'DBMS_LOB.COMPARE({physical},{expressions[col]})=0'))
        else:
            predicates.append(f'{physical}={expressions[col]}')
    return ' AND '.join(predicates)


def insert_statement(kind, rows, *, sql=None):
    """Insert absent rows; an existing differing row aborts the whole batch."""
    n=names(sql,kind,OWNER+'.'+TABLES[kind])
    table, statements, bindings = n.table, ['DECLARE n NUMBER; BEGIN'], []
    for i, row in enumerate(rows):
        validate_row(kind, row)
        expressions, binds = bind_row(kind, row, 'r' + str(i))
        bindings.extend(binds)
        keys = equality(KEYS[kind], row, expressions,n.c)
        same = equality(COLUMNS[kind], row, expressions,n.c)
        statements += [f'SELECT COUNT(*) INTO n FROM {table} WHERE {keys};',
            f'IF n=0 THEN INSERT INTO {table} ({",".join(n.c(c) for c in COLUMNS[kind])}) VALUES ({",".join(expressions[c] for c in COLUMNS[kind])}); END IF;',
            f'SELECT COUNT(*) INTO n FROM {table} WHERE {same};',
            "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20001,'DP_EXISTING_VALUE_CONFLICT'); END IF;"]
    statements += ['COMMIT;', 'EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;']
    statement = '\n'.join(statements)
    if len(statement.encode()) > 60000:
        raise DPError('SQL_SIZE: reduce batch rows')
    return statement, bindings


def read_rows(sql, kind, where, binds=(), *, limit=100, order=''):
    """Read CLOB in bounded VARCHAR pieces; retain empty CLOB versus SQL NULL."""
    n=names(sql,kind,OWNER+'.'+TABLES[kind]);table=n.table
    projection = []
    for col in COLUMNS[kind]:
        if col in CLOBS:
            projection += [f'DBMS_LOB.SUBSTR({n.c(col)},{LOB_UNITS},1) AS {col}',
                           f'DBMS_LOB.GETLENGTH({n.c(col)}) AS {col}__TOTAL']
        else:
            projection.append(n.select(col))
    rows = sql.query(f'SELECT {",".join(projection)} FROM {table} WHERE {where} {order}', binds, limit=limit)
    batch_size = getattr(sql.client, 'source_clob_batch_size', 1)
    if batch_size != 1:
        from .oracle_dp_batched_read import complete_rows
        return complete_rows(sql, kind, rows, batch_size=batch_size)
    for row in rows:
        keybinds = [(f'k{i}', row[c], 'VARCHAR2') for i, c in enumerate(KEYS[kind])]
        keywhere = ' AND '.join(f'{n.c(c)}=:k{i}' for i, c in enumerate(KEYS[kind]))
        for col in CLOBS.intersection(COLUMNS[kind]):
            length = row.pop(col + '__TOTAL')
            if length is None:
                if row[col] is not None: raise DPError('CLOB_NULL: inconsistent response')
                continue
            length = int(length)
            value = row[col] or ''
            consumed = units(value)
            while consumed < length:
                part = sql.query(f'SELECT DBMS_LOB.SUBSTR({n.c(col)},{LOB_UNITS},:pos) AS PIECE, '
                    f'DBMS_LOB.GETLENGTH({n.c(col)}) AS TOTAL FROM {table} WHERE {keywhere}',
                    [*keybinds, ('pos', consumed + 1, 'NUMBER')], limit=1)
                if len(part) != 1 or part[0]['TOTAL'] != length or not part[0]['PIECE']:
                    raise DPError('CLOB_INCOMPLETE: missing/changed chunk')
                piece = part[0]['PIECE']
                value += piece; consumed += units(piece)
                if len(value.encode()) > MAX_VALUE_BYTES:
                    raise DPError('CLOB_SIZE: exceeds configured bound')
            if consumed != length: raise DPError('CLOB_LENGTH: incomplete/duplicated Unicode data')
            row[col] = value
        validate_row(kind, row)
    return rows


def read_batch(sql, kind, expected):
    if (getattr(sql.client, 'source_native_clob', False) and
            not getattr(sql.client, 'source_native_clob_disabled', False)):
        from .oracle_dp_native_read import read_expected
        native = read_expected(sql, kind, expected)
        if native is not None:
            return native
    n=names(sql,kind,OWNER+'.'+TABLES[kind])
    predicates, binds = [], []
    for i, row in enumerate(expected):
        terms = []
        for j, col in enumerate(KEYS[kind]):
            name = f'k{i}_{j}'; binds.append((name, row[col], 'VARCHAR2')); terms.append(f'{n.c(col)}=:{name}')
        predicates.append('(' + ' AND '.join(terms) + ')')
    return read_rows(sql, kind, ' OR '.join(predicates), binds, limit=len(expected))


def compare_batch(kind, expected, observed, *, require_all=True):
    key = lambda r: tuple(r[c] for c in KEYS[kind])
    wanted, found = {key(r): r for r in expected}, {key(r): r for r in observed}
    if len(wanted) != len(expected) or len(found) != len(observed) or not set(found) <= set(wanted):
        raise DPError('ROW_KEYS: duplicate or unexpected keys')
    if any(found[k] != wanted[k] for k in found):
        raise DPError('ROW_CONFLICT: existing row differs; not overwritten')
    if require_all and set(found) != set(wanted):
        raise DPError('READBACK_MISSING: not all committed rows were observed')
    return [r for r in expected if key(r) not in found]


def check_source_tables(sql):
    schema=getattr(sql.client,'schema_map',None)
    if schema:return schema.preflight(sql,keys=list(TABLES))
    names = ','.join("'" + n + "'" for n in TABLES.values())
    rows = sql.query('SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_USED,NULLABLE '
                     f"FROM ALL_TAB_COLUMNS WHERE OWNER='{OWNER}' AND TABLE_NAME IN ({names})", limit=30)
    found = {(r['TABLE_NAME'], r['COLUMN_NAME']): r for r in rows}
    if len(rows) != 18 or set(found) != {(TABLES[k], c) for k in COLUMNS for c in COLUMNS[k]}:
        raise DPError('TARGET_SCHEMA: expected three tables and 18 columns')
    for kind, columns in COLUMNS.items():
        for col in columns:
            r = found[(TABLES[kind], col)]
            typ = 'CLOB' if col in CLOBS else 'NUMBER' if col == 'JSON_TEXT_ELIDED' else 'VARCHAR2'
            size = 64 if col in ('DATASET_VERSION', 'SOURCE_ARTIFACT_SHA256') else 512
            if (r['DATA_TYPE'] != typ or (col in KEYS[kind] and r['NULLABLE'] != 'N') or
                    (typ == 'VARCHAR2' and (r['DATA_LENGTH'] != size or r['CHAR_USED'] != 'B'))):
                raise DPError('TARGET_SCHEMA: column type/width/nullability differs')
    keys = sql.query('SELECT c.TABLE_NAME,c.STATUS,c.VALIDATED,k.COLUMN_NAME,k.POSITION '
        'FROM ALL_CONSTRAINTS c JOIN ALL_CONS_COLUMNS k ON k.OWNER=c.OWNER AND k.CONSTRAINT_NAME=c.CONSTRAINT_NAME '
        f"WHERE c.OWNER='{OWNER}' AND c.CONSTRAINT_TYPE='P' AND c.TABLE_NAME IN ({names}) "
        'ORDER BY c.TABLE_NAME,k.POSITION', limit=12)
    for kind, columns in KEYS.items():
        selected = [r for r in keys if r['TABLE_NAME'] == TABLES[kind]]
        if tuple(r['COLUMN_NAME'] for r in selected) != columns or any(r['STATUS'] != 'ENABLED' or r['VALIDATED'] != 'VALIDATED' for r in selected):
            raise DPError('TARGET_PK: validated enabled primary keys required for safe resume')
