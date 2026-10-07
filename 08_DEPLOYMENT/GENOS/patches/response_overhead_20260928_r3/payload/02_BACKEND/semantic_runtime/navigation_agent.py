"""Serving adapter for the ID-driven navigation loop and pinned glossary assets.

Resources are request-local because HTTP requests run on different worker threads.
No research runner, answer data, or provider discovery participates in retrieval.
"""
import json
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import sqlite3
import threading

from .contracts import sha
from . import observability as obs
from . import full_glossary
from .full_glossary import Glossary

_HASH_MEMO = {}
_JSON_MEMO = {}
_HASH_LOCK = threading.Lock()
_GLOSSARY_POOL = {}
_GLOSSARY_POOL_LOCK = threading.Lock()
_GLOSSARY_ACTIVE_KEY = None
_ORIGINAL_SHA = full_glossary.sha
log = obs.get_logger('glossary')


def _asset_label(path):
    if len(path.stem) == 64 and all(char in '0123456789abcdef' for char in path.stem):
        return 'cache-receipt.json' if path.suffix == '.json' else 'cache-index.sqlite'
    return path.name


def _file_size(size):
    if size >= 1024 ** 3:
        return f'{size / 1024 ** 3:.2f}GiB'
    if size >= 1024 ** 2:
        return f'{size / 1024 ** 2:.1f}MiB'
    return f'{size / 1024:.1f}KiB'


def memoized_sha(path):
    """SHA-256 of a pinned glossary file, recomputed only when its stat signature changes.

    The glossary bundle is ~14GB; hashing it on every HTTP request cost ~11s. The
    stat tuple (size, mtime_ns, ctime_ns, inode) is the same drift signal
    Glossary.check_unchanged already relies on inside a request.
    """
    resolved = Path(path).resolve()
    stat = os.stat(resolved)
    signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
    label = _asset_label(resolved)
    size = _file_size(stat.st_size)
    with _HASH_LOCK:
        cached = _HASH_MEMO.get(resolved)
        if cached is not None and cached[0] == signature:
            obs.event(log, 'glossary.file.cached', file=label, file_size=size)
            return cached[1]
        # Keep the same-file verification single-flight. Automatic worker
        # warmup and the first request can otherwise hash a large NFS file at
        # the same time, making both slower.
        with obs.step(log, 'glossary.file.verify', file=label, file_size=size):
            digest = _ORIGINAL_SHA(resolved)
        _HASH_MEMO[resolved] = (signature, digest)
        return digest


# full_glossary.py bytes are pinned by every serving cache receipt (compiler_sha256),
# so the memo is installed from here instead of editing that module.
full_glossary.sha = memoized_sha


def _serving_glossary_ro(path):
    # Leased connections are exclusive to one request, but warmup and HTTP
    # requests may execute on different threads in the same process.
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True,
                         check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


full_glossary.ro = _serving_glossary_ro
from .full_glossary_connections import ConnectionReader
from .navigation_loop import NavigationAgent, NavigationSession
from .navigation_match import ReverseMatcher
from .term_agent import TermAgent


class _BorrowedGlossary:
    """One request owns each read-only SQLite connection set at a time."""
    def __init__(self, value, key):
        self._value, self._key, self._closed = value, key, False

    def __getattr__(self, name):
        if self._closed:
            raise RuntimeError('glossary lease already closed')
        return getattr(self._value, name)

    def close(self):
        if self._closed:
            return
        self._closed = True
        value = self._value
        try:
            # Relation scans install request-deadline progress handlers on all
            # glossary databases. A pooled connection must not carry that
            # expired deadline into the next request.
            _clear_glossary_progress_handlers(value)
            value.check_unchanged()
            # These are request-discovered handles; never expose them to a later
            # request even though the source generation is immutable.
            value.known.clear()
            if value.connections is not None:
                value.connections._resolved.clear()
                value.connections._aliases.clear()
        except Exception:
            value.close()
            return
        with _GLOSSARY_POOL_LOCK:
            if self._key != _GLOSSARY_ACTIVE_KEY:
                value.close()
                return
            pool = _GLOSSARY_POOL.setdefault(self._key, [])
            if len(pool) < 2:
                pool.append(value)
                return
        value.close()


def _clear_glossary_progress_handlers(value):
    for db in value.dbs.values():
        db.set_progress_handler(None, 0)


def _verified_json(path, expected):
    """Reuse small pinned receipts without reopening them on every question."""
    path = Path(path).resolve()
    def signature():
        state = path.stat()
        return (state.st_dev, state.st_ino, state.st_size,
                state.st_mtime_ns, state.st_ctime_ns)
    with _HASH_LOCK:
        before = signature()
        cached = _JSON_MEMO.get(path)
        if cached is not None and cached[:2] == (before, expected):
            return deepcopy(cached[2])
        raw = path.read_bytes()
        if signature() != before or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('glossary cache receipt mismatch')
        value = json.loads(raw)
        if len(_JSON_MEMO) >= 16:
            _JSON_MEMO.clear()
        _JSON_MEMO[path] = (before, expected, value)
        return deepcopy(value)


def glossary_assets(generation, config, *, manifest=None):
    root = Path(generation).resolve()
    if manifest is None:
        manifest = json.loads((root / 'manifest.json').read_text()) if (root / 'manifest.json').is_file() else {}
    binding = manifest.get('glossary') or config['glossary']
    paths = {}
    for key in ('bundle', 'dictionary', 'cache'):
        path = (root / binding[key]).resolve()
        path.relative_to(root)
        paths[key] = path
    # Refuse implicit cache builds in the serving process.
    receipt = paths['cache'] / binding['cache_receipt']
    receipt.resolve().relative_to(paths['cache'])
    with obs.step(log, 'glossary.receipt'):
        cache_binding = _verified_json(receipt, binding['cache_receipt_sha256'])['binding']
        if cache_binding['compiler_sha256'] != memoized_sha(Path(__file__).with_name('full_glossary.py')):
            raise ValueError('glossary compiler/cache binding mismatch')
    with obs.step(log, 'glossary.open'):
        key = (str(root), json.dumps(binding, sort_keys=True, ensure_ascii=False))
        global _GLOSSARY_ACTIVE_KEY
        with _GLOSSARY_POOL_LOCK:
            if _GLOSSARY_ACTIVE_KEY != key:
                stale = [item for pool in _GLOSSARY_POOL.values() for item in pool]
                _GLOSSARY_POOL.clear()
                _GLOSSARY_ACTIVE_KEY = key
            else:
                stale = []
            available = _GLOSSARY_POOL.get(key, [])
            value = available.pop() if available else None
        for item in stale:
            item.close()
        if value is not None:
            try:
                _clear_glossary_progress_handlers(value)
                value.check_unchanged()
            except Exception:
                value.close()
                value = None
        if value is None:
            value = Glossary(paths['bundle'], paths['dictionary'], paths['cache'],
                             manifest_sha256=binding['manifest_sha256'],
                             connection_factory=ConnectionReader)
            obs.event(log, 'glossary.pool.ready')
        else:
            obs.event(log, 'glossary.pool.hit')
        return _BorrowedGlossary(value, key)


class ServingNavigationAgent(TermAgent):
    def retrieve(self, plan, use_llm=True):
        index = self.get_index()
        tools = index.tools(plan['scope']['document_version_ids'])
        glossary = None
        try:
            glossary = glossary_assets(self.pipeline.store.path, self.config)
            matcher = ReverseMatcher(self.pipeline.store.db, tools, glossary)
            binding = self.config.get('learning', {}).get('bundle')
            if binding is not None:
                from .navigation_learning import bind_learning
                matcher = bind_learning(matcher, binding, self.pipeline.contracts.root,
                                        self.pipeline.store.path)
            limits = self.config.get('limits')
            if use_llm:
                result = NavigationAgent(self.pipeline, glossary, index, matcher, limits).retrieve(plan, True)
            else:
                session = NavigationSession(matcher, tools, glossary, plan['question'],
                                            plan['scope']['document_version_ids'], limits)
                state = {'status': 'METADATA_ONLY', 'use_llm': False, 'selected_ids': [],
                         'calls': 0, 'provider_receipts': [], 'trace': [], 'failure': None,
                         'initial': session.context()['initial'], 'quality_certified': False,
                         'final': {'findings': [], 'evidence_ids': [], 'open_questions': [],
                                   'question_for_user': '', 'next_action': 'STOP'}}
                result = {'candidates': [], 'routes': {'navigation_loop': 0},
                          'vector_status': 'NOT_USED', 'generation_id': plan['generation_id'],
                          'term_agent': state}
                if hasattr(session, 'seed'):
                    state['matched_question_spans'] = [span for kind in ('terms', 'structures')
                                                      for row in session.seed[kind]
                                                      for span in row['question_spans']]
                    state['learning'] = session.learning
            glossary.check_unchanged()
            return result
        finally:
            tools.db.close()
            if glossary is not None:
                glossary.close()
