"""Exact Gold R19 types in explicit development placement; bounded JDBC writes."""
import hashlib
import json
from pathlib import Path
import re
import time
import uuid


class Stop(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def literal(value):
    if value is None:
        return 'NULL'
    if type(value) is int:
        return str(value)
    if not isinstance(value, str) or '\0' in value or len(value.encode()) > 4000:
        raise Stop('SQL_LITERAL_TYPE_OR_SIZE')
    return "'" + value.replace("'", "''") + "'"


def error_codes(exc):
    codes = []
    seen = set()
    current = exc
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        for c in re.findall(r'(?:ORA|PLS)-\d{5}', str(current)):
            if c not in codes:
                codes.append(c)
        current = current.__cause__ or current.__context__
    return codes[:12]


class Database:
    def __init__(self, executor):
        self.executor = executor
        self.calls = 0

    def query(self, sql, limit=200):
        self.calls += 1
        frame = self.executor.query_to_df(sql, infer_from_schema=True, parse_dates=False)
        frame = frame.astype(object).where(frame.notna(), None)
        rows = frame.to_dict(orient='records')
        if len(rows) > limit:
            raise Stop('RESULT_LIMIT')
        result = []
        for row in rows:
            result.append({str(k).upper(): v.item() if hasattr(v, 'item') else v for k, v in row.items()})
        return result

    def block(self, sql, binds=(), rollback=False):
        from lawrag.pipeline.oracle_query_dataiku import render
        rendered = render(sql, binds, write=True)
        self.calls += 1
        start = time.monotonic()
        frame = self.executor.query_to_df('SELECT 1 AS OK FROM DUAL', pre_queries=[rendered],
                                         post_queries=['ROLLBACK' if rollback else 'COMMIT'])
        if len(frame) != 1 or int(frame.iloc[0]['OK']) != 1:
            raise Stop('WRITE_RESPONSE_UNCONFIRMED')
        return time.monotonic() - start


class Contract:
    def __init__(self, path):
        self.value = json.loads(Path(path).read_text())
        self.tables = self.value['tables']
        self.sha256 = digest(self.value)

    def table(self, key):
        t = self.tables[key]
        return t['owner'] + '.' + t['name']

    def col(self, key, name):
        return self.tables[key]['columns'][name]['name']

    def ddl(self, key):
        t = self.tables[key]
        if t.get('create_sql'):
            return t['create_sql']
        fields = [c['name'] + ' ' + c['type'] + (' DEFAULT ' + c['default'] if c['default'] else '') +
                  (' NOT NULL' if c['required'] else '') for c in t['columns'].values()]
        fields.append('CONSTRAINT X0_' + t['name'] + ' PRIMARY KEY (' +
                      ','.join(self.col(key, n) for n in t['primary_key']) + ')')
        return 'CREATE TABLE ' + self.table(key) + ' (' + ','.join(fields) + ')'

    def indexes(self, key):
        t = self.tables[key]
        if t.get('index_sql'):
            return t['index_sql']
        return ['CREATE INDEX ' + t['owner'] + '.X' + str(i) + '_' + t['name'] +
                ' ON ' + self.table(key) + ' (' + ','.join(self.col(key, n) for n in cols) + ')'
                for i, cols in enumerate(t['indexes'], 1)]

    def preflight(self, db, key):
        t = self.tables[key]
        where = 'OWNER=' + literal(t['owner']) + ' AND TABLE_NAME=' + literal(t['name'])
        rows = db.query('SELECT COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_USED,DATA_PRECISION,DATA_SCALE,NULLABLE,DATA_DEFAULT '
                        'FROM ALL_TAB_COLUMNS WHERE ' + where)
        found = {r['COLUMN_NAME']: r for r in rows}
        if set(found) != {c['name'] for c in t['columns'].values()}:
            raise Stop('COLUMNS_MISMATCH:' + self.table(key))
        for c in t['columns'].values():
            r, typ = found[c['name']], c['type']
            if typ.startswith(('VARCHAR2', 'CHAR')):
                ok = r['DATA_TYPE'] == typ.split('(')[0] and r['DATA_LENGTH'] == int(re.search(r'\((\d+)', typ)[1]) and r['CHAR_USED'] == 'B'
            elif typ.startswith('NUMBER'):
                ok = r['DATA_TYPE'] == 'NUMBER' and r['DATA_PRECISION'] == int(re.search(r'\((\d+)', typ)[1]) and r['DATA_SCALE'] == 0
            elif typ.startswith('TIMESTAMP'):
                ok = r['DATA_TYPE'] == 'TIMESTAMP(6) WITH TIME ZONE'
            else:
                ok = r['DATA_TYPE'] == ('VECTOR' if typ.startswith('VECTOR') else typ)
            if not ok or r['NULLABLE'] != ('N' if c['required'] else 'Y') or (r.get('DATA_DEFAULT') or '').strip().upper() != (c['default'] or ''):
                raise Stop('TYPE_MISMATCH:' + self.table(key) + '.' + c['name'])
        pks = db.query('SELECT cc.COLUMN_NAME,c.STATUS,c.VALIDATED FROM ALL_CONSTRAINTS c '
                       'JOIN ALL_CONS_COLUMNS cc ON cc.OWNER=c.OWNER AND cc.CONSTRAINT_NAME=c.CONSTRAINT_NAME '
                       'WHERE c.OWNER=' + literal(t['owner']) + ' AND c.TABLE_NAME=' + literal(t['name']) +
                       " AND c.CONSTRAINT_TYPE='P' ORDER BY cc.POSITION")
        if [r['COLUMN_NAME'] for r in pks] != [self.col(key, n) for n in t['primary_key']] or any(r['STATUS'] != 'ENABLED' or r['VALIDATED'] != 'VALIDATED' for r in pks):
            raise Stop('PRIMARY_KEY_MISMATCH:' + self.table(key))
        triggers = db.query('SELECT TRIGGER_NAME FROM ALL_TRIGGERS WHERE TABLE_OWNER=' + literal(t['owner']) +
                            ' AND TABLE_NAME=' + literal(t['name']) + " AND STATUS='ENABLED' FETCH FIRST 1 ROWS ONLY")
        if triggers:
            raise Stop('ENABLED_TRIGGER_REVIEW_REQUIRED:' + self.table(key))

    def create(self, db, emit, *, allow_create=True):
        # Test native VECTOR support before creating any of the 17 target tables.
        rows = db.query("SELECT VECTOR_DIMENSION_COUNT(TO_VECTOR('[1,0]',2,FLOAT32)) AS N FROM DUAL")
        if len(rows) != 1 or rows[0]['N'] != 2:
            raise Stop('NATIVE_VECTOR_REQUIRED')
        for key, t in self.tables.items():
            emit('TABLE_PREPARE', table=self.table(key))
            present = db.query('SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER=' + literal(t['owner']) +
                               ' AND TABLE_NAME=' + literal(t['name']))
            if not present:
                if not allow_create:raise Stop('RESUME_TABLE_MISSING:'+self.table(key))
                db.block('BEGIN EXECUTE IMMEDIATE ' + literal(self.ddl(key)) + '; END;')
            self.preflight(db, key)
            for ddl in self.indexes(key):
                owner, name = re.search(r'CREATE INDEX ([A-Z0-9_]+)\.([A-Z0-9_]+)', ddl).groups()
                indexes = db.query('SELECT TABLE_OWNER,TABLE_NAME,STATUS FROM ALL_INDEXES WHERE OWNER=' +
                                   literal(owner) + ' AND INDEX_NAME=' + literal(name))
                if not indexes:
                    if not allow_create:raise Stop('RESUME_INDEX_MISSING:'+name)
                    db.block('BEGIN EXECUTE IMMEDIATE ' + literal(ddl) + '; END;')
                elif indexes != [{'TABLE_OWNER': t['owner'], 'TABLE_NAME': t['name'], 'STATUS': 'VALID'}]:
                    raise Stop('INDEX_TARGET_MISMATCH:' + name)
                if t['group']=='GOLD_R19':
                    expected=re.search(r' ON [A-Z0-9_.]+ \(([^)]+)\)',ddl)[1].split(',')
                    actual=db.query('SELECT COLUMN_NAME FROM ALL_IND_COLUMNS WHERE INDEX_OWNER='+literal(owner)+
                                    ' AND INDEX_NAME='+literal(name)+' ORDER BY COLUMN_POSITION')
                    if [r['COLUMN_NAME'] for r in actual]!=expected:
                        raise Stop('INDEX_COLUMNS_MISMATCH:'+name)
            emit('TABLE_READY', table=self.table(key))

    def probe(self, db, key, vector_dimensions=2):
        t = self.tables[key]
        token = uuid.uuid4().hex
        expressions = {}
        for name, c in t['columns'].items():
            typ = c['type']
            expressions[name] = ('1' if typ.startswith('NUMBER') else 'SYSTIMESTAMP' if typ.startswith('TIMESTAMP')
                                 else "TO_VECTOR('"+json.dumps([1]+[0]*(vector_dimensions-1))+"',"+str(vector_dimensions)+",FLOAT32)" if typ.startswith('VECTOR')
                                 else "TO_CLOB('{}')" if typ == 'CLOB' else "'N'" if typ.startswith('CHAR') else literal(token))
        where = ' AND '.join(self.col(key, n) + '=' + expressions[n] for n in t['primary_key'])
        vector_cols=[c['name'] for c in t['columns'].values() if c['type'].startswith('VECTOR')]
        check_where=where+''.join(" AND VECTOR_DIMENSION_FORMAT("+c+")='FLOAT32' AND VECTOR_DIMENSION_COUNT("+c+")="+
                                 str(vector_dimensions) for c in vector_cols)
        # UUID collision is rejected; no replacement or deletion of existing rows.
        sql = ('DECLARE n NUMBER; BEGIN SELECT COUNT(*) INTO n FROM ' + self.table(key) + ' WHERE ' + where +
               "; IF n<>0 THEN RAISE_APPLICATION_ERROR(-20040,'PROBE_KEY_EXISTS'); END IF; INSERT INTO " + self.table(key) +
               ' (' + ','.join(self.col(key, n) for n in expressions) + ') VALUES (' + ','.join(expressions.values()) +
               '); SELECT COUNT(*) INTO n FROM ' + self.table(key) + ' WHERE ' + check_where +
               "; IF n<>1 THEN RAISE_APPLICATION_ERROR(-20041,'PROBE_READBACK'); END IF; ROLLBACK; "
               'EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
        seconds = db.block(sql, rollback=True)
        rows = db.query('SELECT COUNT(*) AS N FROM ' + self.table(key) + ' WHERE ' + where)
        if rows != [{'N': 0}]:
            raise Stop('PROBE_ROLLBACK_UNCONFIRMED:' + self.table(key))
        if vector_cols and vector_dimensions==2:
            seconds+=self.probe(db,key,vector_dimensions=3)
        return seconds

    def validate(self, key, rows):
        t = self.tables[key]
        if not rows or len(rows) > 5000:
            raise Stop('BATCH_SIZE')
        seen = {}
        for row in rows:
            if set(row) - set(t['columns']):
                raise Stop('ROW_UNKNOWN_COLUMN:' + key)
            for name, c in t['columns'].items():
                value = row.get(name)
                if value is None:
                    if c['required'] and not c['default']:
                        raise Stop('ROW_REQUIRED:' + key + '.' + name)
                    continue
                typ = c['type']
                if typ.startswith(('VARCHAR2', 'CHAR')):
                    if type(value) is not str or not value or '\0' in value or len(value.encode()) > int(re.search(r'\((\d+)', typ)[1]):
                        raise Stop('ROW_BYTE_LENGTH_OR_EMPTY:' + key + '.' + name)
                elif typ.startswith('NUMBER'):
                    if type(value) is not int or len(str(abs(value))) > int(re.search(r'\((\d+)', typ)[1]):
                        raise Stop('ROW_NUMBER:' + key + '.' + name)
                elif typ == 'CLOB':
                    if type(value) is not str or '\0' in value or len(value.encode()) > 16 * 1024**2:
                        raise Stop('ROW_CLOB:' + key + '.' + name)
                else:
                    raise Stop('LOAD_TYPE_NOT_SUPPORTED:' + key + '.' + name)
            pk = tuple(row[n] for n in t['primary_key'])
            if pk in seen and seen[pk] != row:
                raise Stop('BATCH_DUPLICATE_CONFLICT:' + key)
            seen[pk] = row
        return list(seen.values())

    def batch(self, key, rows, *, verify_only=False):
        rows = self.validate(key, rows)
        t = self.tables[key]
        names = [n for n, c in t['columns'].items() if not c['default']]
        payload = []
        specs, expressions = [], {}
        for i, n in enumerate(names):
            typ = t['columns'][n]['type']
            alias = 'c' + str(i)
            json_type='VARCHAR2(1)' if typ.startswith('CHAR(') else typ
            specs.append(alias + ' ' + json_type + " PATH '$." + alias + "' ERROR ON ERROR")
            if typ == 'CLOB':
                specs.append(alias + "e NUMBER PATH '$." + alias + "e' ERROR ON ERROR")
                expressions[n] = '(CASE WHEN s.' + alias + 'e=1 THEN EMPTY_CLOB() ELSE s.' + alias + ' END)'
            else:
                expressions[n] = 's.' + alias
        for row in rows:
            value = {}
            for i, n in enumerate(names):
                alias = 'c' + str(i)
                value[alias] = row.get(n)
                if t['columns'][n]['type'] == 'CLOB':
                    value[alias+'e'] = int(row.get(n) == '')
            payload.append(value)
        source = "JSON_TABLE(:payload,'$[*]' ERROR ON ERROR COLUMNS(" + ','.join(specs) + ')) s'
        pk = ' AND '.join('t.' + self.col(key, n) + '=' + expressions[n] for n in t['primary_key'])
        equal = []
        for n in names:
            left, right = 't.' + self.col(key, n), expressions[n]
            test = 'DBMS_LOB.COMPARE(' + left + ',' + right + ')=0' if t['columns'][n]['type'] == 'CLOB' else left + '=' + right
            equal.append('(' + test + ' OR (' + left + ' IS NULL AND ' + right + ' IS NULL))')
        sql = 'DECLARE n NUMBER; BEGIN '
        if not verify_only:
            sql += ('INSERT INTO ' + self.table(key) + ' (' + ','.join(self.col(key, n) for n in names) + ') SELECT ' +
                    ','.join(expressions[n] for n in names) + ' FROM ' + source + ' WHERE NOT EXISTS (SELECT 1 FROM ' +
                    self.table(key) + ' t WHERE ' + pk + '); ')
        sql += ('SELECT COUNT(*) INTO n FROM ' + source + ' JOIN ' + self.table(key) + ' t ON (' + pk + ') WHERE ' +
                ' AND '.join(equal) + "; IF n<>:expected THEN RAISE_APPLICATION_ERROR(-20042,'GOLD_ROW_CONFLICT_OR_MISSING'); END IF; " +
                ('ROLLBACK;' if verify_only else 'COMMIT;') + ' EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
        return sql, [('payload', canonical(payload), 'CLOB'), ('expected', len(rows), 'NUMBER')]
