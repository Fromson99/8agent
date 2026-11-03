"""Bounded, request-owned reuse of completed, verified query metadata."""
from collections import OrderedDict
from copy import deepcopy
import json
import time

from .oracle_dp_io import DPError, BudgetPause, digest

MAX_BYTES = 16 * 1024 * 1024
MAX_ENTRY_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 128


class Cache:
    def __init__(self, request):
        self.request = request
        self.pin = self.binding()
        self.values = OrderedDict()
        self.bytes = 0

    def binding(self):
        r = self.request
        return (r.release_id, getattr(getattr(r, 'snapshot', None), 'binding_hash', None),
                frozenset(r.sources.allowed), digest(getattr(getattr(r, 'records', None), 'manifest', None)))

    def check(self):
        if self.binding() != self.pin:
            raise DPError('QUERY_CACHE_BINDING: request release or authorization changed')
        sql = getattr(self.request, 'sql', None)
        if time.monotonic() >= getattr(sql, 'deadline', float('inf')):
            raise BudgetPause('QUERY_DEADLINE: cached request deadline exceeded')

    def get(self, key):
        self.check()
        if key not in self.values:
            return False, None
        self.values.move_to_end(key)
        return True, deepcopy(self.values[key][0])

    def put(self, key, value):
        self.check()
        size = len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())
        if size > MAX_ENTRY_BYTES:
            return False
        if key in self.values:
            self.bytes -= self.values.pop(key)[1]
        while self.values and (self.bytes + size > MAX_BYTES or len(self.values) >= MAX_ENTRIES):
            _, (_, removed) = self.values.popitem(last=False)
            self.bytes -= removed
        self.values[key] = (deepcopy(value), size)
        self.bytes += size
        return True

    def find_rows(self, key, field, value):
        """Look up a point in a cached document without copying the whole tree."""
        self.check()
        if key not in self.values:
            return False, None
        self.values.move_to_end(key)
        return True, [deepcopy(row) for row in self.values[key][0] if str(row[field]) == str(value)]


def for_request(request):
    cache = getattr(request, '_verified_query_cache', None)
    if cache is None:
        cache = Cache(request)
        request._verified_query_cache = cache
    cache.check()
    return cache


def key(kind, **filters):
    return digest([kind, filters])
