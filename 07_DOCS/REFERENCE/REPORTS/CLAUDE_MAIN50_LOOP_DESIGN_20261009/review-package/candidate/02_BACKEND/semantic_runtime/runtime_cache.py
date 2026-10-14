"""Bounded process-lifetime cache for immutable search metadata and preview JSON.

No connection, session, prompt, answer, read ledger or evidence enters this cache.
Callers bind every key to their verified generation and enforce the current ACL.
There is no TTL. Concurrent misses for one key have one builder.
"""
from collections import OrderedDict
from collections.abc import Mapping
import os
import sys
import threading
import time
from . import query_latency as latency

REVISION = 'runtime-cache-20261007-r1'


def footprint(value):
    """Account for Python containers once, including the key and immutable IDs."""
    seen = set(); pending = [value]; total = 0
    while pending:
        item = pending.pop(); identity = id(item)
        if identity in seen: continue
        seen.add(identity); total += sys.getsizeof(item)
        if isinstance(item, Mapping):
            pending.extend(item.keys()); pending.extend(item.values())
        elif isinstance(item, (tuple, list, set, frozenset)):
            pending.extend(item)
    return total


class ProcessCache:
    def __init__(self, *, max_bytes=128*1024*1024, max_entries=256):
        if type(max_bytes) is not int or max_bytes < 1 or type(max_entries) is not int or max_entries < 1:
            raise ValueError('positive process cache budgets required')
        self.max_bytes = max_bytes; self.max_entries = max_entries
        self.entries = OrderedDict(); self.pending = {}; self.bytes = 0
        self.evictions = 0; self.lock = threading.RLock()

    def clear(self):
        with self.lock:
            if self.pending: raise RuntimeError('cannot clear cache while a build is active')
            self.entries.clear(); self.bytes = 0; self.evictions = 0

    def get_or_build(self, key, build, *, kind, remaining=None):
        """Share values, never SQLite handles. Failed builds are not cached."""
        started = time.monotonic(); owner = threading.get_ident()
        with latency.span('runtime_cache.'+kind, cache_scope='process') as metrics:
            while True:
                if remaining is not None: remaining()
                with self.lock:
                    entry = self.entries.get(key)
                    if entry is not None:
                        self.entries.move_to_end(key)
                        metrics.update(cache_hit=True, cache_wait_ms=round((time.monotonic()-started)*1000, 3),
                                       cache_entries=len(self.entries), cache_bytes=self.bytes)
                        return entry[0], metrics.copy()
                    flight = self.pending.get(key)
                    if flight is None:
                        flight = (owner, threading.Event()); self.pending[key] = flight
                        break
                    if flight[0] == owner:
                        raise RuntimeError('recursive build of the same immutable cache key')
                # Context.remaining raises the caller's normal deadline error.
                # Bound the wait without a context; timeout leaves the owner intact.
                with latency.span('runtime_cache.wait', cache_scope='process'):
                    while not flight[1].wait(0.1):
                        if remaining is not None: remaining()
                        elif time.monotonic()-started > 180:
                            raise TimeoutError('immutable cache build wait exceeded')
            try:
                value = build()
                with latency.span('runtime_cache.admission', cache_scope='process'):
                    size = footprint((key, value))
                with self.lock:
                    admitted = size <= self.max_bytes
                    if admitted:
                        while self.entries and (self.bytes+size > self.max_bytes or len(self.entries) >= self.max_entries):
                            _, (_, old_size) = self.entries.popitem(last=False)
                            self.bytes -= old_size; self.evictions += 1
                        self.entries[key] = (value, size); self.bytes += size
                    metrics.update(cache_hit=False, cache_admitted=admitted, cache_bytes=self.bytes,
                                   cache_entries=len(self.entries), cache_evictions=self.evictions)
                return value, metrics.copy()
            finally:
                with self.lock:
                    self.pending.pop(key, None)
                    flight[1].set()


def _settings():
    mib = int(os.environ.get('GENOS_RUNTIME_CACHE_MIB', '128'))
    entries = int(os.environ.get('GENOS_RUNTIME_CACHE_ENTRIES', '256'))
    if not 1 <= mib <= 4096 or not 1 <= entries <= 100000:
        raise ValueError('invalid GENOS runtime cache budget')
    return mib*1024*1024, entries


_bytes, _entries = _settings()
CACHE = ProcessCache(max_bytes=_bytes, max_entries=_entries)
