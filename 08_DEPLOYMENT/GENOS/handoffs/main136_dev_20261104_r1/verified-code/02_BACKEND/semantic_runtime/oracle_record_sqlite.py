"""Memory-only execution of legacy record SQL over Oracle-authoritative rows.

This is not an on-disk SQLite replica or a source/index corpus cache. Each open
hydrates one logical Agent record namespace; commits upload changed rows only.
Existing SQL triggers/FKs/versions still validate before the Oracle CAS commit.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import re
import sqlite3
import threading
from functools import wraps
import time

from .oracle_dp_io import DPError, canonical, digest
from .oracle_agent_records import sha
from . import oracle_runtime_paths as paths


def encode(value):
    if value is None: return ['null', None]
    if isinstance(value, bytes): return ['bytes', base64.b64encode(value).decode()]
    if isinstance(value, str): return ['text', value]
    if isinstance(value, int): return ['integer', str(value)]
    if isinstance(value, float): return ['float', value.hex()]
    raise DPError('AGENT_SQL_VALUE: unsupported SQLite value type')


def decode(value):
    kind, data = value
    if kind == 'null': return None
    if kind == 'bytes': return base64.b64decode(data, validate=True)
    if kind == 'text': return data
    if kind == 'integer': return int(data)
    if kind == 'float': return float.fromhex(data)
    raise DPError('AGENT_SQL_VALUE: unknown stored value type')


def quoted(name):
    if not isinstance(name, str) or '\x00' in name:
        raise DPError('AGENT_SQL_IDENTIFIER: invalid maintained schema identifier')
    return '"' + name.replace('"', '""') + '"'


def synchronized(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._mutex:
            return method(self, *args, **kwargs)
    return locked


class Cursor(sqlite3.Cursor):
    """Result rows are detached before another writer can refresh the RAM DB.

    A live SQLite VM must never outlive replacement of its database pages. The
    caller still sees the SELECT snapshot, including partially consumed rows.
    """
    def __init__(self, connection):
        super().__init__(connection)
        self._result = None
        self._position = 0

    def _execute(self, operation, sql, *, script=False):
        def run():
            self._result = None
            result = operation()
            self._result = sqlite3.Cursor.fetchall(self) if self.description else []
            self._position = 0
            return result
        return self.connection._run(run, sql, script=script)
    def execute(self, sql, parameters=()):
        return self._execute(lambda: sqlite3.Cursor.execute(self, sql, parameters), sql)
    def executemany(self, sql, parameters):
        return self._execute(lambda: sqlite3.Cursor.executemany(self, sql, parameters), sql)
    def executescript(self, sql):
        return self._execute(lambda: sqlite3.Cursor.executescript(self, sql), sql, script=True)
    def fetchone(self):
        if self._result is None: return sqlite3.Cursor.fetchone(self)
        if self._position >= len(self._result): return None
        value = self._result[self._position]; self._position += 1
        return value
    def fetchmany(self, size=None):
        size = self.arraysize if size is None else size
        if size < 0: raise ValueError('negative fetch size')
        if self._result is None: return sqlite3.Cursor.fetchmany(self, size)
        end = min(len(self._result), self._position + size)
        value = self._result[self._position:end]; self._position = end
        return value
    def fetchall(self):
        if self._result is None: return sqlite3.Cursor.fetchall(self)
        return self.fetchmany(len(self._result) - self._position)
    def __iter__(self): return self
    def __next__(self):
        if self._result is None: return sqlite3.Cursor.__next__(self)
        if self._position >= len(self._result): raise StopIteration
        value = self._result[self._position]; self._position += 1
        return value
    def close(self):
        with self.connection._mutex:
            self._result = None
            return sqlite3.Cursor.close(self)


class Connection(sqlite3.Connection):
    is_oracle_record = True
    compact = False

    def _initialize_oracle(self, path, readonly):
        self._mutex = threading.RLock()
        self.record_path = paths.Path(path).resolve()
        self.records = paths.records(); self.owner = paths.identity(path)
        self.readonly_record = readonly
        self.revision = 0; self._baseline = {}; self._dirty = set()
        self._table_changes = set(); self._schema_dirty = False; self._suppressed = True
        self._lease = None; self._poisoned = False; self._closed_record = False
        self._tables = {}; self._virtual_tables = set()
        self._schema_hash = None
        self._base('PRAGMA temp_store=MEMORY')
        self.create_function('_oracle_dirty', -1, self._mark)
        self.set_authorizer(self._authorize)
        state = self.records.state('a1:head:' + self.owner)
        if state:
            self._load(state)
        elif readonly:
            raise FileNotFoundError(str(path))
        self._suppressed = False

    def _base(self, sql, args=()):
        cursor = sqlite3.Connection.execute(self, sql, args)
        cursor.row_factory = None
        return cursor

    def _mark(self, table, *key):
        if not self._suppressed:
            self._dirty.add((table, canonical([encode(v) for v in key])))
        return None

    def _authorize(self, operation, a, b, database, trigger):
        if self._suppressed:
            return sqlite3.SQLITE_OK
        if operation in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
            return sqlite3.SQLITE_DENY
        if operation in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
            self._table_changes.add(a)
        if operation in (sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_CREATE_TRIGGER,
                         sqlite3.SQLITE_CREATE_VIEW, sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_DROP_INDEX,
                         sqlite3.SQLITE_DROP_TRIGGER, sqlite3.SQLITE_DROP_VIEW, sqlite3.SQLITE_ALTER_TABLE):
            self._schema_dirty = True
        if operation == sqlite3.SQLITE_PRAGMA and a in ('user_version', 'application_id') and b is not None:
            self._schema_dirty = True
        return sqlite3.SQLITE_OK

    def _catalogue(self):
        shadows = {r[1] for r in self._base('PRAGMA table_list') if r[2] == 'shadow'}
        definitions = [list(r) for r in self._base("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name") if r[1] not in shadows]
        value = {'definitions': definitions, 'user_version': self._base('PRAGMA user_version').fetchone()[0],
                 'application_id': self._base('PRAGMA application_id').fetchone()[0]}
        if self._base("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone():
            value['sequence'] = [list(r) for r in self._base('SELECT name,seq FROM sqlite_sequence ORDER BY name')]
        return value

    def _install_tracking(self):
        self._suppressed = True
        try:
            self._tables = {}; self._virtual_tables = set()
            for kind, name, _, sql in self._catalogue()['definitions']:
                if kind != 'table': continue
                fields = [r for r in self._base('PRAGMA table_xinfo(' + quoted(name) + ')') if not r[6]]
                cols = [r[1] for r in fields]
                without = bool(re.search(r'WITHOUT\s+ROWID', sql, re.I))
                pk = [r[1] for r in sorted(fields, key=lambda r: r[5]) if r[5]]
                self._tables[name] = {'columns': cols, 'without': without, 'pk': pk}
                if re.match(r'CREATE\s+VIRTUAL\s+TABLE', sql, re.I):
                    self._virtual_tables.add(name); continue
                for action in ('INSERT', 'UPDATE', 'DELETE'):
                    trigger = '_oracle_' + digest([name, action])[:20]
                    self._base('DROP TRIGGER IF EXISTS temp.' + quoted(trigger))
                    calls = []
                    for ref in (('OLD', 'NEW') if action == 'UPDATE' else ('OLD',) if action == 'DELETE' else ('NEW',)):
                        args = [f'{ref}.{quoted(c)}' for c in pk] if without else [f'{ref}.rowid']
                        calls.append("SELECT _oracle_dirty('" + name.replace("'", "''") + "'," + ','.join(args) + ');')
                    self._base('CREATE TEMP TRIGGER ' + quoted(trigger) + ' AFTER ' + action + ' ON ' + quoted(name) + ' BEGIN ' + ''.join(calls) + ' END')
        finally:
            self._suppressed = False

    def _load(self, state):
        if self.in_transaction:
            raise StateConflict('AGENT_SQL_CONFLICT: reopen instead of refreshing an active transaction')
        value = state['value']
        if value.get('migration',{}).get('status') not in (None,'COMPLETE'):
            raise DPError('AGENT_MIGRATION_INCOMPLETE: finish the original import before opening records')
        if value.get('type') != 'sqlite' or value.get('path') != str(self.record_path):
            raise DPError('AGENT_SQL_BINDING: logical database identity differs')
        catalogue = json.loads(self.records.body(value['schema']))
        current = [r for r in self.records.rows(self.owner) if r['REC_KIND_CD'].startswith('SQLROW:')]
        bodies = self.records.bodies(r['BODY_HASH_VAL'] for r in current)
        after = self.records.state('a1:head:' + self.owner)
        if after is None or after['sha256'] != state['sha256']:
            raise StateConflict('AGENT_SQL_CHANGED: record namespace changed during hydration')
        import os
        limit = int(os.environ.get('GENOS_ORACLE_AGENT_MEMORY_MIB', '256')) * 1024 * 1024
        if sum(len(raw) for raw in bodies.values()) > limit:
            raise DPError('AGENT_SQL_MEMORY: narrow/migrate the record namespace before loading; nothing was truncated')
        fresh = sqlite3.connect(':memory:', isolation_level=None)
        try:
            fresh.execute('PRAGMA temp_store=MEMORY'); fresh.execute('PRAGMA foreign_keys=OFF')
            definitions = catalogue['definitions']
            for kind, _, _, sql in definitions:
                if kind == 'table': fresh.execute(sql)
            baseline = {}
            for row in current:
                raw = bodies[row['BODY_HASH_VAL']]; item = json.loads(raw)
                if item['table'] != row['REC_KIND_CD'][7:] or digest({'table': item['table'], 'key': item['key']}) != row['REC_KEY_HASH_VAL']:
                    raise DPError('AGENT_SQL_ROW_HASH: row identity differs')
                values = [decode(v) for v in item['values']]
                columns = item['columns']; key = [decode(v) for v in item['key']]
                if item['rowid']:
                    columns = ['rowid', *columns]; values = [key[0], *values]
                fresh.execute('INSERT INTO ' + quoted(item['table']) + '(' + ','.join(map(quoted, columns)) + ') VALUES(' + ','.join('?' for _ in values) + ')', values)
                baseline[(item['table'], canonical(item['key']))] = row['BODY_HASH_VAL']
            for kind, _, _, sql in definitions:
                if kind != 'table': fresh.execute(sql)
            if catalogue.get('sequence'):
                fresh.execute('DELETE FROM sqlite_sequence')
                fresh.executemany('INSERT INTO sqlite_sequence(name,seq) VALUES(?,?)', catalogue['sequence'])
            fresh.execute('PRAGMA user_version=' + str(int(catalogue['user_version'])))
            fresh.execute('PRAGMA application_id=' + str(int(catalogue['application_id'])))
            # Native backup expires SQLite schema/VM state safely. Results from public
            # cursors are detached; the destination has no active transaction.
            # Never deserialize over a live Connection/prepared-statement cache.
            self._suppressed = True
            sqlite3.Connection.backup(fresh, self)
            self._base('PRAGMA temp_store=MEMORY')
            self.revision = state['revision']; self._baseline = baseline
            self._schema_hash = value['schema']
            self._dirty.clear(); self._table_changes.clear(); self._schema_dirty = False
        finally:
            fresh.close(); self._suppressed = False
        self._install_tracking()

    def _acquire(self):
        if self._lease is not None: return
        if self.readonly_record:
            raise sqlite3.OperationalError('attempt to write a readonly Oracle record namespace')
        self._lease = self.records.lease(['sql-transaction', str(self.record_path)], wait=30)
        self._lease.__enter__()
        try:
            state = self.records.state('a1:head:' + self.owner)
            if state and state['revision'] != self.revision:
                if self._dirty or (self._schema_dirty and sha(canonical(self._catalogue()).encode()) != self._schema_hash):
                    raise StateConflict('AGENT_SQL_CONFLICT: uncommitted local changes cannot be rebased')
                self._load(state)
        except BaseException:
            self._release(); raise

    def _release(self):
        lease, self._lease = self._lease, None
        if lease is not None: lease.__exit__(None, None, None)

    def _row(self, table, key):
        info = self._tables[table]; values = [decode(v) for v in json.loads(key)]
        where = ' AND '.join(quoted(k) + ' IS ?' for k in info['pk']) if info['without'] else 'rowid=?'
        got = self._base('SELECT ' + ','.join(map(quoted, info['columns'])) + ' FROM ' + quoted(table) + ' WHERE ' + where, values).fetchone()
        if got is None: return None
        return {'table': table, 'key': json.loads(key), 'rowid': not info['without'], 'columns': info['columns'], 'values': [encode(v) for v in got]}

    def _scan(self, table):
        info = self._tables[table]
        cols = info['pk'] if info['without'] else ['rowid']
        for values in self._base('SELECT ' + ','.join(map(quoted, cols)) + ' FROM ' + quoted(table)):
            yield table, canonical([encode(v) for v in values])

    def _flush(self):
        if not (self._dirty or self._table_changes or self._schema_dirty): return
        if not self._dirty and not self._virtual_tables and self._schema_hash == sha(canonical(self._catalogue()).encode()):
            self._table_changes.clear();self._schema_dirty=False
            return
        if self._lease is None: self._acquire()
        if self._schema_dirty or not self._tables:
            self._install_tracking()
            for table in self._tables:
                self._dirty.update(self._scan(table))
            self._dirty.update(self._baseline)
        # SQLite REPLACE can delete a row through a UNIQUE constraint without
        # firing its DELETE trigger. Reconcile removed keys for touched tables;
        # only their changed row bodies are uploaded.
        for table in self._table_changes & self._tables.keys():
            live=set(self._scan(table))
            self._dirty.update(k for k in self._baseline if k[0]==table and k not in live)
        for table in self._virtual_tables:
            if self._table_changes:
                self._dirty.update(self._scan(table))
                self._dirty.update(k for k in self._baseline if k[0] == table)
        bodies = []; changes = []; updates = {}
        for table, key in sorted(self._dirty):
            item = self._row(table, key) if table in self._tables else None
            raw = canonical(item if item is not None else {'deleted': True, 'table': table, 'key': json.loads(key)}).encode()
            body_hash = sha(raw)
            if item is not None and self._baseline.get((table, key)) == body_hash: continue
            if item is None and (table, key) not in self._baseline: continue
            bodies.append(raw)
            changes.append({'kind': 'SQLROW:' + table, 'key': digest({'table': table, 'key': json.loads(key)}),
                            'order': 0, 'lookup': None, 'body': body_hash, 'deleted': int(item is None)})
            updates[(table, key)] = None if item is None else body_hash
        catalogue = self._catalogue()
        schema_raw = canonical(catalogue).encode(); bodies.append(schema_raw)
        if not changes and self._schema_hash == sha(schema_raw):
            self._dirty.clear(); self._table_changes.clear(); self._schema_dirty = False
            return
        if self.revision == 0: changes.append(paths.entry_change(self.record_path, kind='sqlite'))
        value = {'type': 'sqlite', 'path': str(self.record_path), 'schema': sha(schema_raw), 'mtime': time.time(), 'size': sum(len(b) for b in bodies)}
        run = None
        if 'run' in self._tables:
            cursor = self._base('SELECT * FROM run WHERE singleton=1'); row = cursor.fetchone()
            if row:
                r = dict(zip([d[0] for d in cursor.description], row))
                started = datetime.fromisoformat(r['started_at']).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f +00:00')
                run = {'id': digest(r['run_id']), 'request': digest(r['query_id']), 'status': r['status'], 'started': started,
                       'session': None, 'parent': None, 'path': str(self.record_path)}
        self.revision = self.records.commit(self.owner, self.revision, value, changes, run=run, bodies=bodies)
        self._schema_hash = sha(schema_raw)
        for key, new in updates.items():
            if new is None: self._baseline.pop(key, None)
            else: self._baseline[key] = new
        self._dirty.clear(); self._table_changes.clear(); self._schema_dirty = False

    @synchronized
    def _run(self, operation, sql, *, script=False):
        if self._poisoned: raise DPError('AGENT_SQL_UNCONFIRMED: reopen the Oracle record namespace')
        token = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ''
        if token in ('COMMIT', 'END') and not script:
            self.commit(); return self.cursor()
        if token == 'ROLLBACK' and ' TO ' not in sql.upper() and not script:
            self.rollback(); return self.cursor()
        reading = token in ('SELECT', 'EXPLAIN') or (token == 'PRAGMA' and '=' not in sql)
        if token == 'PRAGMA' and re.match(r'\s*PRAGMA\s+journal_mode\s*=', sql, re.I):
            return self._base('PRAGMA journal_mode=MEMORY')
        if token == 'PRAGMA' and re.match(r'\s*PRAGMA\s+temp_store\s*=', sql, re.I):
            return self._base('PRAGMA temp_store=MEMORY')
        # Existing constructors repeat IF NOT EXISTS schema declarations. Queue
        # schema-only changes in RAM and commit them together before data access.
        # This is initialization, not delayed durability of application writes.
        declaration = token in ('CREATE','ALTER','DROP','PRAGMA')
        if self._schema_dirty and not self.in_transaction and not declaration and not script:
            self._flush();self._release()
        if script and self.in_transaction:
            self.commit()
        if not reading and not declaration and not script:
            self._acquire()
        if token in ('INSERT','UPDATE','DELETE','REPLACE','WITH'):
            self._table_changes.add('*')
        try:
            result = operation()
            if script or self._schema_dirty: self._install_tracking()
            if script and self.in_transaction:self._acquire()
            if not self.in_transaction and not reading and not declaration and not script:
                self._flush(); self._release()
            return result
        except BaseException:
            if not self.in_transaction: self._release()
            raise

    def execute(self, sql, parameters=()): return self.cursor().execute(sql, parameters)
    def executemany(self, sql, parameters): return self.cursor().executemany(sql, parameters)
    def executescript(self, sql): return self.cursor().executescript(sql)
    def cursor(self, factory=Cursor): return sqlite3.Connection.cursor(self, factory)

    @synchronized
    def commit(self):
        try:
            sqlite3.Connection.commit(self)
            self._flush()
        except BaseException:
            self._poisoned = True; raise
        finally:
            self._release()

    @synchronized
    def rollback(self):
        sqlite3.Connection.rollback(self)
        self._dirty.clear(); self._table_changes.clear(); self._schema_dirty = False
        self._release()

    @synchronized
    def close(self):
        if self._closed_record: return
        try:
            if self.in_transaction: self.rollback()
            elif self._schema_dirty and not self._poisoned:self._flush()
        finally:
            self._release(); self._closed_record = True; sqlite3.Connection.close(self)

    def __enter__(self): return self
    def __exit__(self, typ, value, traceback):
        if typ is None: self.commit()
        else: self.rollback()


def connect(path, *args, **kwargs):
    text = str(path)
    readonly = text.startswith('file:') and ('mode=ro' in text or 'immutable=1' in text)
    path = paths.filename(path)
    if paths.Path(path).name in {'store.sqlite','navigation.sqlite','fulltext.sqlite','dictionary.sqlite','lookup.sqlite','graph.sqlite'}:
        raise DPError('AGENT_SOURCE_MIRROR_FORBIDDEN: source/index databases must use their Oracle query ports')
    kwargs.pop('uri', None); kwargs.pop('factory', None)
    kwargs.setdefault('cached_statements', 0)
    db = sqlite3.connect(':memory:', *args, factory=Connection, **kwargs)
    try:
        db._initialize_oracle(path, readonly)
        return db
    except BaseException:
        sqlite3.Connection.close(db); raise


from .oracle_query_state import StateConflict
