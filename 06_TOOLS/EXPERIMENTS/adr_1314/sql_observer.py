"""Experiment-only SQLite trace counts and exclusive API time; no bind values saved.

Trace includes direct sqlite3.Connection.execute bypasses and implicit SQL.
API seconds include stepping, row factories and Python UDF work, not pure engine
CPU. Direct base-method calls have trace counts but no separate API timer.
Nested timers are subtracted, so totals do not double-count recursive reads.
"""
import sqlite3, time, threading, collections

class Observer:
    def __init__(self, source, runtime):
        self.source, self.runtime = str(source), str(runtime)
        self.phase = 'prepare'
        self.original = sqlite3.connect
        self.local = threading.local()
        self.rows = collections.defaultdict(lambda: {'trace_statements': 0, 'api_calls': 0, 'api_seconds': 0.0, 'returned_rows': 0})
        self.factories = {}
        self.connections = collections.Counter()
        self.callback_seconds = 0.0

    def kind(self, db):
        name = str(db)
        return 'corpus' if self.source in name else 'journal' if self.runtime in name else 'memory' if ':memory:' in name or 'mode=memory' in name else 'other'

    def timed(self, db, operation, function, *args, **kwargs):
        stack = getattr(self.local, 'stack', None)
        if stack is None:
            stack = self.local.stack = []
        frame = [time.perf_counter(), 0.0]
        stack.append(frame)
        key = (self.phase, db._ob_kind, operation)
        try:
            value = function(*args, **kwargs)
            if operation == 'fetchone': self.rows[key]['returned_rows'] += int(value is not None)
            elif operation in ('fetchall', 'fetchmany'): self.rows[key]['returned_rows'] += len(value)
            elif operation == 'next': self.rows[key]['returned_rows'] += 1
            return value
        finally:
            elapsed = time.perf_counter() - frame[0]
            stack.pop()
            if stack: stack[-1][1] += elapsed
            row = self.rows[key]
            row['api_calls'] += 1
            row['api_seconds'] += max(0.0, elapsed - frame[1])

    def cursor_type(self, parent):
        key = ('cursor', parent)
        if key in self.factories: return self.factories[key]
        ob = self
        class Cursor(parent):
            def execute(self, *a, **k): return ob.timed(self.connection, 'execute', super().execute, *a, **k)
            def executemany(self, *a, **k): return ob.timed(self.connection, 'executemany', super().executemany, *a, **k)
            def executescript(self, *a, **k): return ob.timed(self.connection, 'executescript', super().executescript, *a, **k)
            def fetchone(self, *a, **k): return ob.timed(self.connection, 'fetchone', super().fetchone, *a, **k)
            def fetchall(self, *a, **k): return ob.timed(self.connection, 'fetchall', super().fetchall, *a, **k)
            def fetchmany(self, *a, **k): return ob.timed(self.connection, 'fetchmany', super().fetchmany, *a, **k)
            def __next__(self): return ob.timed(self.connection, 'next', super().__next__)
        self.factories[key] = Cursor
        return Cursor

    def connection_type(self, parent):
        key = ('connection', parent)
        if key in self.factories: return self.factories[key]
        # Existing local factories only add attributes. Fail before dispatch if
        # one changes SQL method semantics instead of silently replacing it.
        for name in ('execute', 'executemany', 'executescript', 'cursor'):
            if getattr(parent, name) is not getattr(sqlite3.Connection, name):
                raise TypeError('Unreviewed custom SQLite method: ' + name)
        ob = self
        class Connection(parent):
            def cursor(self, factory=sqlite3.Cursor): return super().cursor(factory=ob.cursor_type(factory))
            def execute(self, *a, **k): return self.cursor().execute(*a, **k)
            def executemany(self, *a, **k): return self.cursor().executemany(*a, **k)
            def executescript(self, *a, **k): return self.cursor().executescript(*a, **k)
            def set_trace_callback(self, callback):
                def trace(sql):
                    start = time.perf_counter()
                    verb = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else 'EMPTY'
                    if verb not in ('SELECT','WITH','INSERT','UPDATE','DELETE','BEGIN','COMMIT','ROLLBACK','PRAGMA','CREATE','DROP','SAVEPOINT','RELEASE'): verb = 'OTHER'
                    ob.rows[(ob.phase, self._ob_kind, 'trace_' + verb)]['trace_statements'] += 1
                    ob.callback_seconds += time.perf_counter() - start
                    if callback: callback(sql)
                return super().set_trace_callback(trace)
        self.factories[key] = Connection
        return Connection

    def connect(self, *args, **kwargs):
        args = list(args)
        parent = args[5] if len(args) > 5 else kwargs.get('factory', sqlite3.Connection)
        factory = self.connection_type(parent)
        if len(args) > 5: args[5] = factory
        else: kwargs['factory'] = factory
        db = self.original(*args, **kwargs)
        db._ob_kind = self.kind(args[0] if args else kwargs['database'])
        self.connections[db._ob_kind] += 1
        db.set_trace_callback(None)
        return db

    def install(self): sqlite3.connect = self.connect
    def uninstall(self): sqlite3.connect = self.original
    def report(self):
        return {'connections': dict(self.connections), 'trace_callback_seconds': self.callback_seconds,
                'rows': [dict(phase=k[0], database=k[1], operation=k[2], **v) for k,v in sorted(self.rows.items())],
                'boundary': __doc__, 'bind_values_recorded': False}

def self_test():
    class Journal(sqlite3.Connection): compact = True
    ob=Observer('/corpus', '/runtime');ob.install()
    try:
        db=sqlite3.connect(':memory:',factory=Journal)
        assert isinstance(db,Journal) and db.compact
        db.row_factory=sqlite3.Row
        db.execute('create table t(v)')
        db.executemany('insert into t values(?)',[(1,),(2,)])
        db.commit()
        sqlite3.Connection.execute(db,'insert into t values(3)')
        db.rollback()
        seen=[];db.set_trace_callback(seen.append)
        assert [x['v'] for x in db.execute('select v from t')]==[1,2]
        assert db.cursor().execute('select v from t').fetchmany(1)[0][0]==1
        assert len(db.execute('select v from t').fetchall())==2
        db.create_function('nested',0,lambda:db.execute('select 4').fetchone()[0])
        assert db.execute('select nested()').fetchone()[0]==4
        db.set_trace_callback(None)
        assert db.execute('select 5').fetchone()[0]==5
        assert len(seen)>=5
        db.close()
        r=ob.report();assert sum(x['trace_statements'] for x in r['rows'])==14
        assert all(x['api_seconds']>=0 for x in r['rows'])
        return {'passed':True,'conditions':10,'trace_statements':sum(x['trace_statements'] for x in r['rows'])}
    finally:ob.uninstall()

if __name__=='__main__':
    print(self_test())
