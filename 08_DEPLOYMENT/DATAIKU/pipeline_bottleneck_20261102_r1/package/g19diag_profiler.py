"""Coarse in-process timing; preserve original calls, return values and errors.

Inclusive intervals are reported separately from exclusive nested wall time.
No original rows, SQL literals, model inputs, vectors or credentials are logged.
"""
from contextlib import contextmanager
import functools
import threading
import time
from g19diag_common import error, write


class Recorder:
    def __init__(self, path, clock=time.perf_counter):
        self.path, self.clock = path, clock
        self.local = threading.local(); self.lock = threading.RLock()
        self.started = clock(); self.last_saved = clock()
        self.metrics = {}; self.batch_metrics = {}; self.table = 'setup'; self.mode = 'setup'
        self.status = 'RUNNING'; self.failure = None; self.save_error = None

    @contextmanager
    def span(self, name):
        stack = getattr(self.local, 'stack', None)
        if stack is None: self.local.stack = stack = []
        frame = [self.clock(), 0.0]; stack.append(frame); failed = False
        try:
            yield
        except BaseException:
            failed = True; raise
        finally:
            elapsed = self.clock()-frame[0]; stack.pop()
            if stack: stack[-1][1] += elapsed
            with self.lock:
                key = self.mode+'|'+self.table+'|'+name
                m = self.metrics.setdefault(key, {'calls':0, 'failures':0, 'inclusive_seconds':0., 'exclusive_seconds':0., 'max_seconds':0.})
                m['calls'] += 1; m['failures'] += int(failed); m['inclusive_seconds'] += elapsed
                m['exclusive_seconds'] += max(0, elapsed-frame[1]); m['max_seconds'] = max(m['max_seconds'], elapsed)
            if self.clock()-self.last_saved >= 3: self.save()

    def save(self):
        try:
            with self.lock:
                write(self.path, {'status':self.status, 'elapsed_seconds':self.clock()-self.started,
                                 'active_table':self.table, 'active_mode':self.mode, 'metrics':self.metrics,
                                 'batch_metrics':self.batch_metrics, 'error':self.failure,
                                 'scope':'this actual process; exclusive times only are additive; timing overhead not subtracted'})
            self.last_saved = self.clock()
        except OSError as exc:
            self.save_error = type(exc).__name__  # Diagnostics must not alter an original write outcome.

    def wrap(self, owner, name, label=None):
        original = getattr(owner, name)
        if getattr(original, '_g19_profiled', False): return
        @functools.wraps(original)
        def call(*args, **kwargs):
            with self.span(label or name): return original(*args, **kwargs)
        call._g19_profiled = True
        setattr(owner, name, call)


def install(loader, recorder):
    import jdbc_transport
    # Transport installs the true block implementation first. Later installs are no-ops.
    jdbc_transport.install(loader)
    recorder.wrap(jdbc_transport, 'render', 'gzip_hex_sql_render')
    recorder.wrap(loader.Contract, 'batch', 'validate_payload_sql_build')
    recorder.wrap(loader, 'inputs', 'input_hash_and_descriptor')
    recorder.wrap(loader, 'file_hash', 'file_hash')
    recorder.wrap(loader, 'atomic', 'checkpoint_save')
    from lawrag.pipeline import oracle_migration
    recorder.wrap(oracle_migration, 'source_batch', 'sqlite_source_read')
    recorder.wrap(loader, 'publish', 'publication')
    original_init = loader.Database.__init__
    class ExecutorProxy:
        def __init__(self, executor): self._executor = executor
        def __getattr__(self, key): return getattr(self._executor, key)
        def query_to_df(self, *args, **kwargs):
            with recorder.span('db_request_boundary'):
                return self._executor.query_to_df(*args, **kwargs)
    def init(db, *args, **kwargs):
        original_init(db, *args, **kwargs); db.executor = ExecutorProxy(db.executor)
    loader.Database.__init__ = init
    original_grouped = loader.grouped
    @functools.wraps(original_grouped)
    def grouped(*args, **kwargs):
        iterator = iter(original_grouped(*args, **kwargs))
        while True:
            with recorder.span('query_generation_and_grouping'):
                try: batch = next(iterator)
                except StopIteration: return
            yield batch
    loader.grouped = grouped
    original_batch = loader.Job.batch
    @functools.wraps(original_batch)
    def batch(job, key, rows, *args, **kwargs):
        old_table, old_mode = recorder.table, recorder.mode
        recorder.table, recorder.mode = key, 'verify' if kwargs.get('verify_only') else 'load'
        started = recorder.clock(); success = False
        try:
            with recorder.span('batch_total'):
                value = original_batch(job, key, rows, *args, **kwargs)
            success = True; return value
        finally:
            k = recorder.mode+'|'+key
            m = recorder.batch_metrics.setdefault(k, {'attempts':0, 'successful_rows':0, 'failed_attempts':0, 'seconds':0.})
            m['attempts'] += 1; m['successful_rows'] += len(rows) if success else 0
            m['failed_attempts'] += int(not success); m['seconds'] += recorder.clock()-started
            recorder.table, recorder.mode = old_table, old_mode
            recorder.save()
    loader.Job.batch = batch
    for name, group in (('load_sources', 'source'), ('load_query', 'search')):
        original = getattr(loader, name)
        def build(original=original, group=group):
            @functools.wraps(original)
            def phase(*args, **kwargs):
                old = recorder.table, recorder.mode
                recorder.table, recorder.mode = group, 'verify' if kwargs.get('verify_only') else 'load'
                try:
                    with recorder.span('stage_total'): return original(*args, **kwargs)
                finally: recorder.table, recorder.mode = old
            return phase
        setattr(loader, name, build())
    import mesh_embedding
    recorder.wrap(mesh_embedding, 'encode', 'embedding_model_request')
    # vector_stage imports the already-wrapped encode symbol.
    import vector_stage
    recorder.wrap(vector_stage, 'vector_sql', 'vector_sql_build')
    recorder.wrap(loader.Database, 'block', 'database_block_total')
    recorder.wrap(loader.Database, 'query', 'metadata_query_total')

