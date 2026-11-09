"""Process-lifetime reuse of published, release-addressed Oracle rows.

Every request still reads the active pointer from Oracle and pins one release.
Only a SELECT whose every table reference is a published source/search table
is reused, keyed by connection, physical mapping, pinned release, statement,
binds and page size. The release and dataset IDs are content hashes, so a new
publication is a new key. Active pointers, request state, Agent records,
ontology/vector heads, dictionary views and time-dependent SQL always go to
Oracle. Rows are copied in and out; nothing is written to serving storage.
GENOS_ORACLE_SHARED_CACHE=off restores the previous request-only behaviour.
"""
from __future__ import annotations

import copy
import os
import re
import threading

from .oracle_dp_io import DPError, OWNER, TABLES, digest
from .runtime_cache import ProcessCache

REVISION = 'oracle-shared-rows-20261106-r1'
# Content-addressed publication tables (dev silver / Gold B003 logical keys).
PUBLISHED_KEYS = ('DOC_VER', 'DOC_UNIT', 'DOC_BLK', 'SRC_POST', 'SRCH_POST', 'SRCH_ROW')
# The same tables under the legacy logical port names.
PUBLISHED_PORTS = ('document', 'source_unit', 'block_payload', 'source_release', 'query_release', 'query_row', 'asset_part')
_REF = re.compile(r'(?<![A-Za-z0-9_$#"])([A-Z][A-Z0-9_$#]*)\.([A-Z][A-Z0-9_$#]*)')
_VOLATILE = re.compile(
    r'\b(?:ALL|USER|DBA|CDB)_[A-Z0-9_$#]+|\bG?V\$|\bSYS(?:DATE|TIMESTAMP)\b|\bCURRENT_(?:DATE|TIMESTAMP)\b'
    r'|\bLOCALTIMESTAMP\b|\bDBMS_RANDOM\b|\bSYS_GUID\b|\bUSERENV\b|\bSYS_CONTEXT\b|\bFOR\s+UPDATE\b', re.I)
_SCALARS = (str, int, float, bool, type(None))


def settings(environ=None):
    env = os.environ if environ is None else environ
    mode = (env.get('GENOS_ORACLE_SHARED_CACHE', 'on').strip().lower() or 'on')
    if mode not in ('on', 'off'):
        raise DPError('DP_CONFIG: GENOS_ORACLE_SHARED_CACHE must be on or off')
    try:
        mib = int(env.get('GENOS_ORACLE_SHARED_CACHE_MIB', '512'))
        entries = int(env.get('GENOS_ORACLE_SHARED_CACHE_ENTRIES', '100000'))
    except ValueError:
        raise DPError('DP_CONFIG: GENOS_ORACLE_SHARED_CACHE_MIB/_ENTRIES must be integers') from None
    if not 16 <= mib <= 8192 or not 1 <= entries <= 1000000:
        raise DPError('DP_CONFIG: GENOS_ORACLE_SHARED_CACHE_MIB 16..8192, _ENTRIES 1..1000000')
    return {'mode': mode, 'mib': mib, 'entries': entries}


def published_tables(client):
    """(owners, published physical tables) for the client's mapping, or None if unknown."""
    mapping = getattr(client, 'schema_map', None)
    if mapping is None:
        from .oracle_dp_assets import RELEASE_TABLE, PART_TABLE
        from .oracle_query_catalog import RELEASE, ROW
        published = {OWNER + '.' + name for name in TABLES.values()} | {RELEASE_TABLE, PART_TABLE, RELEASE, ROW}
        return frozenset({OWNER}), frozenset(published)
    tables = getattr(mapping, 'tables', None)
    if hasattr(mapping, 'physical_table') and tables is not None and set(PUBLISHED_KEYS) <= set(tables):
        owners = {table['owner'] for table in tables.values()}
        agents = getattr(mapping, 'agent_tables', None) or {}
        owners |= {name.split('.')[0] for name in agents.values()}
        return frozenset(owners | {'SIDDA', 'SIDDS'}), frozenset(mapping.physical_table(k) for k in PUBLISHED_KEYS)
    owners = getattr(mapping, 'owners', None)
    if owners is not None and tables is not None and hasattr(mapping, 'names'):
        published = {mapping.names(k).table for k in PUBLISHED_PORTS if k in tables}
        return frozenset(set(owners.values()) | {'SIDDA', 'SIDDS'}), frozenset(published)
    return None


def _copy_rows(rows):
    return [{k: v if type(v) in _SCALARS else copy.deepcopy(v) for k, v in row.items()} for row in rows]


class SharedRows:
    def __init__(self, client, environment, *, environ=None):
        self.settings = settings(environ)
        tables = published_tables(client) if self.settings['mode'] == 'on' else None
        self.owners, self.published = tables if tables else (frozenset(), frozenset())
        self.enabled = bool(tables and self.published)
        mapping = getattr(client, 'schema_map', None)
        self.base = digest({'revision': REVISION, 'environment': environment,
                            'mapping': getattr(mapping, 'target_sha256', None),
                            'published': sorted(self.published)})
        self.cache = ProcessCache(max_bytes=self.settings['mib'] * 1024 * 1024,
                                  max_entries=self.settings['entries'])
        self.lock = threading.Lock()
        self.hits = self.misses = 0

    def scope(self, release_id):
        return digest({'base': self.base, 'release_id': release_id})

    def cacheable(self, text):
        if not self.enabled or _VOLATILE.search(text):
            return False
        refs = {owner + '.' + name for owner, name in _REF.findall(text) if owner in self.owners}
        return bool(refs) and refs <= self.published

    def rows(self, scope, text, binds, limit, fetch, remaining):
        key = digest({'scope': scope, 'statement': text, 'binds': [list(b) for b in binds], 'limit': limit})
        built = []

        def build():
            built.append(True)
            return _copy_rows(fetch())

        value, _ = self.cache.get_or_build(key, build, kind='oracle_rows', remaining=remaining)
        with self.lock:
            if built:
                self.misses += 1
            else:
                self.hits += 1
        return _copy_rows(value), not built

    def status(self):
        with self.cache.lock:
            entries, used, evictions = len(self.cache.entries), self.cache.bytes, self.cache.evictions
        with self.lock:
            hits, misses = self.hits, self.misses
        return {'enabled': self.enabled, 'revision': REVISION, 'mib': self.settings['mib'],
                'entries': entries, 'bytes': used, 'evictions': evictions, 'hits': hits, 'misses': misses}
