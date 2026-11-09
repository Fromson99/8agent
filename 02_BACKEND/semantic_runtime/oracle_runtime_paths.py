"""Explicit logical runtime paths backed by Oracle, retaining normal code paths.

Only the configured runtime/state/report roots are virtual under DP=oracle.
No global pathlib/OS monkeypatch, mount, local spool or filesystem fallback.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import fnmatch
import io
import os
from pathlib import Path as LocalPath
import stat as stat_module
import time
from urllib.parse import unquote, urlsplit
import uuid

from .oracle_dp_io import DPError, canonical, digest
from .oracle_agent_records import sha

_PROVIDER = None
_RECORDS = ContextVar('oracle_runtime_record_store', default=None)
DEFAULT_ROOT = '/__oracle_agent__/runtime'


def configure(provider):
    global _PROVIDER
    _PROVIDER = provider


@contextmanager
def using(records):
    token = _RECORDS.set(records)
    try:
        yield records
    finally:
        _RECORDS.reset(token)


def records():
    value = _RECORDS.get()
    if value is None:
        if _PROVIDER is None:
            from .oracle_dp import client_from_environment
            from .oracle_query_service import environment_binding
            from .oracle_agent_records import AgentRecords,RecordSQL
            sql=RecordSQL(client_from_environment(),binding=environment_binding(),deadline=time.monotonic()+1800,max_calls=10000)
            value=AgentRecords(sql,namespace=os.environ.get('GENOS_ORACLE_AGENT_NAMESPACE','genos-rag'))
        else:value = _PROVIDER()
        _RECORDS.set(value)
    return value


def roots():
    found = [os.environ.get('GENOS_RUNTIME_DIR') or DEFAULT_ROOT]
    found.extend(os.environ[k] for k in ('GENOS_STATE_DIR',) if os.environ.get(k))
    result = []
    for root in found:
        if not os.path.isabs(root) or os.path.normpath(root) == '/':
            raise DPError('AGENT_ROOT: non-root absolute logical runtime identifier required')
        result.append(os.path.normpath(root))
    from .detailed_log_storage import log_roots
    if any(root==log or root.startswith(log+'/') for root in result for log in log_roots()):
        raise DPError('AGENT_ROOT_OVERLAP: choose a dedicated NFS log directory that does not contain the Oracle runtime/state root')
    return tuple(sorted(set(result), key=len, reverse=True))


def runtime_directory(default):
    """One runtime identity for service, administration, reporting and chat."""
    from .oracle_dp import enabled
    fallback=DEFAULT_ROOT if enabled() else default
    return Path(os.environ.get('GENOS_RUNTIME_DIR','').strip() or fallback).resolve()


def filename(value):
    text = os.fspath(value)
    if text.startswith('file:'):
        uri = urlsplit(text)
        if uri.netloc not in ('', 'localhost'):
            raise DPError('AGENT_PATH: remote file URI is not a record identifier')
        text = unquote(uri.path)
    return os.path.normpath(os.path.abspath(text))


def virtual(value):
    from .oracle_dp import enabled
    if not enabled() or str(value) == ':memory:':
        return False
    text = filename(value)
    declared=roots()
    from .detailed_log_storage import diagnostic_path
    if diagnostic_path(text):return False
    return any(text == root or text.startswith(root + '/') for root in declared)


def identity(path):
    return digest({'runtime_path_v1': filename(path)})


def head(path):
    return records().state('a1:head:' + identity(path))


def entry_change(path, *, kind='file'):
    path = Path(path)
    value = {'name': path.name, 'path': str(path), 'type': kind, 'owner': identity(path)}
    raw = canonical(value).encode(); records().put_bodies([raw])
    return {'owner': identity(path.parent), 'kind': 'FS_ENTRY', 'key': digest(path.name), 'order': 0,
            'lookup': None, 'body': sha(raw), 'deleted': 0}


def list_entries(path):
    store = records(); rows = store.rows(identity(path), kind='FS_ENTRY')
    bodies = store.bodies(r['BODY_HASH_VAL'] for r in rows)
    result = []
    import json
    for row in rows:
        value = json.loads(bodies[row['BODY_HASH_VAL']])
        if value['path'] != str(Path(path)/value['name']) or '/' in value['name'] or value['name'] in ('.', '..'):
            raise DPError('AGENT_DIRECTORY_HASH: child identity differs')
        result.append(value)
    return result


def metadata(path):
    if str(path) in roots():
        return {'type': 'directory', 'size': 0, 'mtime': 0}
    value = head(path)
    return value['value'] if value else None


def create_directory(path, *, parents=False, exist_ok=False):
    path = Path(path)
    current = metadata(path)
    if current:
        if current['type'] != 'directory' or not exist_ok:
            raise FileExistsError(str(path))
        return
    if not path.parent.is_dir():
        if not parents:
            raise FileNotFoundError(str(path.parent))
        path.parent.mkdir(parents=True, exist_ok=True)
    store = records()
    with store.lease(['directory-create', str(path)], wait=30):
        old = head(path)
        if old:
            if not exist_ok or old['value']['type'] != 'directory':
                raise FileExistsError(str(path))
            return
        store.commit(identity(path), 0, {'type': 'directory', 'path': str(path), 'size': 0, 'mtime': time.time()},
                     [entry_change(path, kind='directory')])


def write_file(path, raw, *, exclusive=False, append=False):
    path = Path(path)
    if not isinstance(raw, bytes):
        raise TypeError('Oracle file writes require exact bytes')
    if not path.parent.is_dir():
        raise FileNotFoundError(str(path.parent))
    store = records()
    with store.lease(['file-write', str(path)], wait=30):
        old = head(path)
        if old and (exclusive or old['value']['type'] != 'file'):
            raise FileExistsError(str(path))
        changes = []; revision = old['revision'] if old else 0
        if append and old:
            value = dict(old['value']); seq = value['append_seq'] + 1
            changes.append({'kind': 'FS_CHUNK:' + value['epoch'], 'key': digest(seq), 'order': seq,
                            'lookup': None, 'body': sha(raw), 'deleted': 0})
            value.update(append_seq=seq, size=value['size'] + len(raw), mtime=time.time())
        else:
            value = {'type': 'file', 'path': str(path), 'base': sha(raw), 'epoch': uuid.uuid4().hex,
                     'append_seq': 0, 'size': len(raw), 'mtime': time.time()}
        if not old:
            changes.append(entry_change(path))
        # The file bytes are stored in the same acknowledged transaction as the head that names them.
        store.commit(identity(path), revision, value, changes, bodies=[raw])
    return len(raw)


def read_file(path):
    path = Path(path); state = head(path)
    if state is None or state['value']['type'] == 'deleted':
        raise FileNotFoundError(str(path))
    value = state['value']
    if value['type'] != 'file':
        raise IsADirectoryError(str(path))
    store = records(); raw = bytearray(store.body(value['base']))
    parts = store.rows(identity(path), kind='FS_CHUNK:' + value['epoch']) if value['append_seq'] else []
    parts.sort(key=lambda r: r['ORD_SEQ_NO'])
    if [r['ORD_SEQ_NO'] for r in parts] != list(range(1, value['append_seq'] + 1)):
        raise DPError('AGENT_FILE_PARTS: append sequence differs')
    bodies = store.bodies(r['BODY_HASH_VAL'] for r in parts)
    for part in parts:
        raw.extend(bodies[part['BODY_HASH_VAL']])
    if len(raw) != value['size']:
        raise DPError('AGENT_FILE_SIZE: complete bytes differ')
    if head(path)['sha256'] != state['sha256']:
        raise DPError('AGENT_FILE_CHANGED: reload current file head')
    return bytes(raw)


class _OracleFile(io.BytesIO):
    def __init__(self, path, mode):
        self.path, self.mode = path, mode
        self.append_mode = 'a' in mode
        self.writable_mode = any(c in mode for c in 'wax+')
        existing = read_file(path) if 'r' in mode else b''
        if 'x' in mode and path.exists():
            raise FileExistsError(str(path))
        super().__init__(existing if not self.append_mode else b'')
        self.saved = 0
        self.saved_hash = None

    def flush(self):
        if not self.closed and self.writable_mode:
            raw = self.getvalue()
            if self.append_mode:
                if raw:
                    write_file(self.path, raw, append=True)
                    super().seek(0); super().truncate(0)
            elif self.saved_hash != sha(raw) or not self.path.exists():
                write_file(self.path, raw, exclusive='x' in self.mode and self.saved == 0)
                self.saved = len(raw); self.saved_hash = sha(raw)
        return super().flush()

    def close(self):
        if not self.closed:
            self.flush()
        super().close()

    def __exit__(self, typ, value, traceback):
        if typ is not None:
            self.writable_mode = False
        self.close()


class Path(type(LocalPath())):
    """Explicit opt-in path class; non-runtime/code paths retain pathlib behavior."""
    def resolve(self, strict=False):
        if virtual(self):
            result = type(self)(filename(self))
            if strict and not result.exists():
                raise FileNotFoundError(str(result))
            return result
        return type(self)(super().resolve(strict=strict))

    def exists(self, *, follow_symlinks=True):
        if not virtual(self):
            return super().exists()
        value = metadata(self)
        return value is not None and value['type'] != 'deleted'

    def is_dir(self):
        if not virtual(self):
            return super().is_dir()
        value = metadata(self)
        return bool(value and value['type'] == 'directory')

    def is_file(self):
        if not virtual(self):
            return super().is_file()
        value = metadata(self)
        return bool(value and value['type'] in ('file', 'sqlite'))

    def is_symlink(self):
        return False if virtual(self) else super().is_symlink()

    def mkdir(self, mode=0o777, parents=False, exist_ok=False):
        if virtual(self):
            return create_directory(self, parents=parents, exist_ok=exist_ok)
        return super().mkdir(mode=mode, parents=parents, exist_ok=exist_ok)

    def chmod(self, mode, *, follow_symlinks=True):
        if virtual(self):
            # Oracle grants own access, not POSIX modes on a logical identifier.
            return
        return super().chmod(mode, follow_symlinks=follow_symlinks)

    def read_bytes(self):
        return read_file(self) if virtual(self) else super().read_bytes()

    def read_text(self, encoding=None, errors=None, newline=None):
        if virtual(self):
            return self.read_bytes().decode(encoding or 'utf-8', errors or 'strict')
        return super().read_text(encoding=encoding, errors=errors)

    def write_bytes(self, data):
        return write_file(self, bytes(data)) if virtual(self) else super().write_bytes(data)

    def write_text(self, data, encoding=None, errors=None, newline=None):
        if virtual(self):
            write_file(self, data.encode(encoding or 'utf-8', errors or 'strict'))
            return len(data)
        return super().write_text(data, encoding=encoding, errors=errors, newline=newline)

    def open(self, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
        if not virtual(self):
            return super().open(mode, buffering, encoding, errors, newline)
        stream = _OracleFile(self, mode)
        return stream if 'b' in mode else io.TextIOWrapper(stream, encoding=encoding or 'utf-8', errors=errors, newline=newline)

    def iterdir(self):
        if not virtual(self):
            yield from super().iterdir(); return
        if not self.is_dir():
            raise FileNotFoundError(str(self))
        for item in sorted(list_entries(self), key=lambda r: r['name']):
            path = self/item['name']
            if path.exists():
                yield path

    def glob(self, pattern, *, case_sensitive=None, recurse_symlinks=False):
        if not virtual(self):
            yield from super().glob(pattern); return
        if pattern.startswith('/') or '..' in pattern.split('/'):
            raise ValueError('relative contained Oracle glob required')
        parts = pattern.split('/')
        def walk(root, index):
            if index == len(parts):
                yield root; return
            if not root.is_dir():
                return
            part = parts[index]
            if part == '**':
                yield from walk(root, index + 1)
                for child in root.iterdir():
                    if child.is_dir():
                        yield from walk(child, index)
            else:
                for child in root.iterdir():
                    if fnmatch.fnmatchcase(child.name, part):
                        yield from walk(child, index + 1)
        yield from walk(self, 0)

    def rglob(self, pattern, *, case_sensitive=None, recurse_symlinks=False):
        yield from self.glob('**/' + str(pattern))

    def stat(self, *, follow_symlinks=True):
        if not virtual(self):
            return super().stat(follow_symlinks=follow_symlinks)
        value = metadata(self)
        if value is None or value['type'] == 'deleted':
            raise FileNotFoundError(str(self))
        mode = stat_module.S_IFDIR if value['type'] == 'directory' else stat_module.S_IFREG
        stamp = value.get('mtime', 0)
        return os.stat_result((mode | 0o600, 0, 0, 1, 0, 0, value.get('size', 0), stamp, stamp, stamp))

    def unlink(self, missing_ok=False):
        if not virtual(self):
            return super().unlink(missing_ok=missing_ok)
        store = records()
        with store.lease(['file-write', str(self)], wait=30):
            old = head(self)
            if not old or old['value']['type'] == 'deleted':
                if not missing_ok:
                    raise FileNotFoundError(str(self))
                return
            if old['value']['type'] == 'sqlite':
                raise DPError('AGENT_DELETE: runtime cannot delete a record database')
            store.commit(identity(self), old['revision'], {'type': 'deleted', 'path': str(self), 'mtime': time.time()}, [])

    def touch(self, mode=0o666, exist_ok=True):
        if not virtual(self):
            return super().touch(mode=mode, exist_ok=exist_ok)
        if self.exists() and exist_ok:
            return
        write_file(self, b'', exclusive=not exist_ok)
