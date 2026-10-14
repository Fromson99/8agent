"""Whole immutable SQLite datasets retained by the server, independent of queries.

Request-owned connections read the same process-lifetime snapshot. Originals and
their generation bindings remain authoritative. No TTL or result truncation.
"""
import atexit
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from . import query_latency as latency

REVISION = 'resident-data-20261007-r1'


def signature(path):
    path = Path(path)
    if path.is_symlink() or Path(str(path)+'-wal').exists():
        raise ValueError('unbound resident data file')
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def available_memory():
    values = []
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'): values.append(int(line.split()[1])*1024)
    except (OSError, ValueError): pass
    try:
        root = Path('/sys/fs/cgroup')
        limit = (root/'memory.max').read_text().strip()
        if limit != 'max': values.append(max(0, int(limit)-int((root/'memory.current').read_text())))
    except (OSError, ValueError): pass
    return min(values) if values else 0


_WRITES = frozenset(getattr(sqlite3, name) for name in (
    'SQLITE_INSERT','SQLITE_UPDATE','SQLITE_DELETE','SQLITE_CREATE_INDEX','SQLITE_CREATE_TABLE',
    'SQLITE_CREATE_TEMP_INDEX','SQLITE_CREATE_TEMP_TABLE','SQLITE_CREATE_TEMP_TRIGGER',
    'SQLITE_CREATE_TEMP_VIEW','SQLITE_CREATE_TRIGGER','SQLITE_CREATE_VIEW','SQLITE_DROP_INDEX',
    'SQLITE_DROP_TABLE','SQLITE_DROP_TEMP_INDEX','SQLITE_DROP_TEMP_TABLE','SQLITE_DROP_TEMP_TRIGGER',
    'SQLITE_DROP_TEMP_VIEW','SQLITE_DROP_TRIGGER','SQLITE_DROP_VIEW','SQLITE_ALTER_TABLE',
    'SQLITE_REINDEX','SQLITE_ANALYZE','SQLITE_CREATE_VTABLE','SQLITE_DROP_VTABLE',
    'SQLITE_ATTACH','SQLITE_DETACH'))


def _readonly(action, first, second, database, source):
    if action in _WRITES: return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and first.lower() == 'query_only' and second is not None:
        if second.lower() not in ('1', 'true', 'on', 'yes'): return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class ResidentPool:
    def __init__(self, *, mode='auto', max_memory_bytes=8192*1024*1024, directory=None):
        if mode not in ('auto','memory','local','off') or type(max_memory_bytes) is not int or max_memory_bytes < 1:
            raise ValueError('invalid resident cache setting')
        self.mode=mode; self.max_memory_bytes=max_memory_bytes; self.directory=directory
        self.entries={}; self.lock=threading.RLock(); self.memory_bytes=0; self.local_bytes=0
        self.pending={}; self.local_root=None

    def close(self):
        with self.lock:
            if self.pending: raise RuntimeError('resident cache build still active')
            for entry in self.entries.values():
                if entry['keeper'] is not None: entry['keeper'].close()
            self.entries.clear(); self.memory_bytes=0; self.local_bytes=0
            if self.local_root is not None: shutil.rmtree(self.local_root); self.local_root=None

    def connect(self, path, *, expected=None, factory=sqlite3.Connection, remaining=None):
        original=Path(path)
        before=signature(original); path=original.resolve()
        key=(str(path), before, expected)
        if self.mode == 'off':
            return sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, check_same_thread=False, factory=factory)
        with latency.span('resident_data.open', cache_scope='whole-dataset', dataset_bytes=before[2]) as metrics:
            while True:
                if remaining: remaining()
                with self.lock:
                    entry=self.entries.get(key)
                    if entry is not None: metrics['cache_hit']=True; break
                    flight=self.pending.get(key)
                    if flight is None:
                        flight=(threading.get_ident(), threading.Event()); self.pending[key]=flight
                        break
                    if flight[0]==threading.get_ident(): raise RuntimeError('recursive resident dataset build')
                with latency.span('resident_data.wait'):
                    started=time.monotonic()
                    while not flight[1].wait(0.1):
                        if remaining: remaining()
                        elif time.monotonic()-started>1800: raise TimeoutError('resident dataset wait exceeded')
            if entry is None:
                reserved=0
                try:
                    estimate=before[2]+before[2]//3
                    with self.lock:
                        memory=(self.mode!='local' and self.memory_bytes+estimate<=self.max_memory_bytes
                                and available_memory()>=estimate+2048*1024*1024)
                        if self.mode=='memory' and not memory:
                            raise MemoryError('whole dataset does not fit resident RAM budget; increase GENOS_RESIDENT_CACHE_MIB or use local/auto')
                        if memory: reserved=estimate; self.memory_bytes+=estimate
                    entry=self._build(path, before, expected, memory, remaining)
                    with self.lock:
                        self.entries[key]=entry
                        if not memory: self.local_bytes+=before[2]
                    metrics['cache_hit']=False
                except BaseException:
                    with self.lock: self.memory_bytes-=reserved
                    raise
                finally:
                    with self.lock: self.pending.pop(key, None); flight[1].set()
            if signature(original)!=before: raise ValueError('resident source changed; reopen and verify')
            metrics.update(cache_storage=entry['storage'], resident_memory_reserved_bytes=self.memory_bytes,
                           resident_local_bytes=self.local_bytes, cache_entries=len(self.entries))
            db=sqlite3.connect(entry['uri'], uri=True, check_same_thread=False, factory=factory)
            try:
                db.execute('PRAGMA query_only=ON'); db.set_authorizer(_readonly)
                return db
            except BaseException:
                db.close(); raise

    def _build(self, path, before, expected, memory, remaining):
        keeper=None; target=None
        try:
            with latency.span('resident_data.load', dataset_bytes=before[2], cache_storage='memory' if memory else 'local'):
                digest=hashlib.sha256()
                if not memory:
                    with self.lock:
                        if self.local_root is None:
                            base=Path(self.directory or os.environ.get('GENOS_RESIDENT_CACHE_DIR','/var/tmp'))
                            base.mkdir(parents=True, exist_ok=True)
                            self.local_root=Path(tempfile.mkdtemp(prefix='8-agent-resident-',dir=base))
                        root=self.local_root
                    if latency.obs.environment_facts(root).get('mount_type') in ('nfs','nfs4','cifs','smb3'):
                        raise ValueError('resident local cache must not use a network filesystem')
                    if (latency.obs.environment_facts(root).get('mount_type') in ('tmpfs','ramfs')
                            and available_memory()<before[2]+512*1024*1024):
                        raise MemoryError('local cache directory is RAM-backed and does not fit; use disk-backed GENOS_RESIDENT_CACHE_DIR')
                    if shutil.disk_usage(root).free<before[2]+16*1024*1024:
                        raise OSError('insufficient local space for whole resident dataset')
                    target=root/(uuid.uuid4().hex+'.sqlite')
                # A byte-for-byte local mirror is verified while streaming. RAM
                # uses SQLite's online backup to preserve FTS and all SQL indexes.
                with path.open('rb') as source:
                    output=target.open('xb') if target is not None else None
                    try:
                        while block:=source.read(4*1024*1024):
                            if remaining: remaining()
                            digest.update(block)
                            if output: output.write(block)
                    finally:
                        if output: output.close()
                if expected is not None and digest.hexdigest()!=expected:
                    raise ValueError('resident dataset hash mismatch')
                if signature(path)!=before: raise ValueError('resident source changed while copying')
                if memory:
                    uri='file:8-agent-'+uuid.uuid4().hex+'?mode=memory&cache=shared'
                    keeper=sqlite3.connect(uri,uri=True,check_same_thread=False)
                    source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,check_same_thread=False)
                    try:
                        def progress(status, left, total):
                            if remaining: remaining()
                        source.backup(keeper,pages=1024,progress=progress)
                    finally: source.close()
                    keeper.execute('PRAGMA query_only=ON'); keeper.set_authorizer(_readonly)
                else:
                    os.chmod(target,0o400)
                    uri=target.as_uri()+'?mode=ro&immutable=1'
                if signature(path)!=before: raise ValueError('resident source changed while loading')
                return {'uri':uri,'keeper':keeper,'storage':'memory' if memory else 'local'}
        except BaseException:
            if keeper is not None: keeper.close()
            if target is not None: target.unlink(missing_ok=True)
            raise


POOL=ResidentPool(mode=os.environ.get('GENOS_RESIDENT_DATA','auto'),
                  max_memory_bytes=int(os.environ.get('GENOS_RESIDENT_CACHE_MIB','8192'))*1024*1024)
atexit.register(POOL.close)
