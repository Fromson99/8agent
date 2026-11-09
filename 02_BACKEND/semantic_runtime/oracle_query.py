"""Request-scoped Oracle reads. No source mirror, file journal, or data cache.

This is the data access port, not a replacement legal reasoning engine. A
snapshot pins one completed publication for the entire request. Callers supply
their already-authorized document scope; this module never widens that scope.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time

from . import observability as obs
from .oracle_dp_assets import get_release
from .oracle_dp_io import DPError, BudgetPause, SQL, read_rows, canonical, digest

log = obs.get_logger('oracle.query')
MAX_PAGE = 100
MAX_IDS = 100
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
# One INFO line per SQL made the request log mostly SQL bookkeeping, and each
# line cost the request thread 5-10 ms in the field (2026-11-06 photos).
# Per-SQL lines are DEBUG (GENOS_LOG_LEVEL=DEBUG); slow and failed SQL stay
# visible and every request ends with one oracle.sql.summary line.
SLOW_SQL_MS = int(os.environ.get('GENOS_ORACLE_SQL_SLOW_MS', '1000'))


# Field 2026-11-07: 70% of SQL time was Agent-record traffic that SQL hashes alone could not name.
# Each SQL is also counted by its call site: the first frame outside the transport modules ("inner",
# e.g. oracle_agent_records.put_bodies) and the first frame outside the oracle_*/record plumbing
# ("outer", e.g. repository.transaction). Frame walk only, no log line per SQL.
_TRANSPORT_FILES = frozenset({'oracle_query.py', 'oracle_dp_io.py', 'oracle_shared_cache.py', 'runtime_cache.py',
                              'oracle_query_state.py'})
_PLUMBING_FILES = frozenset({'runtime_sqlite.py', 'journal_storage.py', 'contextlib.py', 'functools.py'})
_RECORD_TRANSPORT = frozenset({'mutate', '_mutate', '_query', 'timed_call'})
SITE_LIMIT = 12


def call_site(depth=3):
    """'inner<outer' module.function names of the code that sent this SQL (bounded frame walk)."""
    try:
        frame = sys._getframe(depth)
    except ValueError:
        return 'unknown'
    inner = outer = None
    for _ in range(60):
        if frame is None:
            break
        name = os.path.basename(frame.f_code.co_filename)
        transport = name in _TRANSPORT_FILES or (name == 'oracle_agent_records.py' and frame.f_code.co_name in _RECORD_TRANSPORT)
        if inner is None and not transport:
            inner = name[:-3] + '.' + frame.f_code.co_name
        if inner is not None and not transport and not name.startswith('oracle_') and name not in _PLUMBING_FILES:
            outer = name[:-3] + '.' + frame.f_code.co_name
            break
        frame = frame.f_back
    return (inner or 'unknown') + ('<' + outer if outer and outer != inner else '')


class SQLStats:
    def __init__(self):
        self.lock = threading.Lock()
        self.sent = self.writes = self.failed = self.cache_hits = self.cache_misses = 0
        self.ms = self.slowest_ms = 0.0
        self.families = {}
        self.sites = {}
        self.agent_calls = {}
        self.agent_ms = 0.0

    def finished(self, family, ms, *, write, site=None):
        with self.lock:
            self.sent += 1; self.writes += bool(write); self.ms += ms
            self.slowest_ms = max(self.slowest_ms, ms)
            row = self.families.setdefault(family, [0, 0.0]); row[0] += 1; row[1] += ms
            if site is not None:
                row = self.sites.setdefault(site, [0, 0.0, 0]); row[0] += 1; row[1] += ms; row[2] += bool(write)

    def failure(self):
        with self.lock: self.failed += 1

    def cache(self, hit):
        with self.lock:
            if hit: self.cache_hits += 1
            else: self.cache_misses += 1

    def agent(self, name, ms, *, top):
        """Wall time of one Agent-record method (SQL + Python encode/decode); top-level calls only add to agent_ms."""
        with self.lock:
            row = self.agent_calls.setdefault(name, [0, 0.0]); row[0] += 1; row[1] += ms
            if top: self.agent_ms += ms

    def progress(self):
        """Cumulative counters for model-call events: per-segment SQL/Agent time is a difference of two snapshots."""
        with self.lock:
            return {'sql_count_total': self.sent, 'sql_ms_total': round(self.ms), 'agent_ms_total': round(self.agent_ms)}

    def summary(self):
        with self.lock:
            top = sorted(self.families.items(), key=lambda item: -item[1][1])[:3]
            sites = sorted(self.sites.items(), key=lambda item: -item[1][1])[:SITE_LIMIT]
            return {'sql_count': self.sent, 'sql_write_count': self.writes, 'sql_failed_count': self.failed,
                    'sql_ms': round(self.ms), 'sql_slowest_ms': round(self.slowest_ms),
                    'sql_cache_hits': self.cache_hits, 'sql_cache_misses': self.cache_misses,
                    'sql_top': '-'.join(f'{f}:{n}:{round(ms)}' for f, (n, ms) in top) or 'none',
                    'sql_sites': [{'site': k, 'count': n, 'ms': round(ms), 'writes': w} for k, (n, ms, w) in sites],
                    'sql_site_count': len(self.sites),
                    'agent_ms': round(self.agent_ms),
                    'agent_calls': [{'name': k, 'count': n, 'ms': round(ms)} for k, (n, ms) in sorted(self.agent_calls.items())]}


class QuerySQL(SQL):
    """Read-only ORDS calls, using stdout telemetry rather than serving files.

    There is no retry here. The owning request retains this object and its
    budget across tool calls. Partial results and expired budgets are failures,
    never an empty search result or permission to fall back to SQLite.
    """
    def __init__(self, client, *, binding, deadline, max_calls=1000):
        if not 1 <= max_calls <= 10000 or deadline <= time.monotonic():
            raise DPError('QUERY_BUDGET: positive bounded request budget required')
        self.client, self.binding = client, binding
        self.deadline, self.max_calls, self.calls = deadline, max_calls, 0
        self.progress = None
        self.stats = SQLStats()
        self.shared_cache = None  # oracle_shared_cache.SharedRows, set by the serving factory only
        self.shared_scope = None
        self._sql_started = self._sql_family = self._sql_site = None

    def pin_shared_cache(self, release_id):
        """Reuse published rows of exactly one content-addressed release per request."""
        cache = self.shared_cache
        if cache is None or not cache.enabled:
            return
        scope = cache.scope(release_id)
        if self.shared_scope is None:
            self.shared_scope = scope
        elif self.shared_scope != scope:
            self.shared_scope = False  # a second release in one request: no reuse for the rest

    def _remaining(self):
        if time.monotonic() >= self.deadline:
            raise BudgetPause('QUERY_DEADLINE: request deadline exceeded while reading published rows')

    def query(self,statement,binds=(),*,limit=100):
        from .oracle_silver_reads import rewrite
        text=rewrite(statement,getattr(self.client,'schema_map',None))
        cache,scope=self.shared_cache,self.shared_scope
        if cache is not None and scope and cache.cacheable(text):
            rows,hit=cache.rows(scope,text,binds,limit,lambda:SQL.query(self,text,binds,limit=limit),self._remaining)
            self.stats.cache(hit)
            return rows
        return super().query(text,binds,limit=limit)

    def event(self, status, **extra):
        now = time.perf_counter()
        if status == 'STARTED':
            self._sql_started, self._sql_family = now, (extra.get('sql_sha256') or 'unknown')[:12]
            self._sql_site = call_site()
            if log.isEnabledFor(logging.DEBUG):
                obs.event(log, 'oracle.sql', level=logging.DEBUG, binding=self.binding, call=self.calls,
                          status=status, **extra)
            return
        ms = (now - self._sql_started) * 1000 if self._sql_started is not None else 0.0
        family, self._sql_started = self._sql_family or 'unknown', None
        site, self._sql_site = self._sql_site or 'unknown', None
        if status == 'ACKNOWLEDGED':
            self.stats.finished(family, ms, write=bool(extra.get('write')), site=site)
            if ms >= SLOW_SQL_MS:
                obs.event(log, 'oracle.sql.slow', call=self.calls, status=status, duration_ms=round(ms),
                          sql_family=family, write=bool(extra.get('write')), sql_site=site)
            elif log.isEnabledFor(logging.DEBUG):
                obs.event(log, 'oracle.sql', level=logging.DEBUG, binding=self.binding, call=self.calls,
                          status=status, duration_ms=round(ms, 3), sql_family=family, **extra)
            return
        self.stats.failure()
        obs.event(log, 'oracle.sql', level=logging.WARNING, binding=self.binding, call=self.calls,
                  status=status, duration_ms=round(ms), sql_family=family, sql_site=site, **extra)

    def request(self, statement, binds=(), *, write=False, limit=MAX_PAGE):
        if write or not statement.lstrip().upper().startswith('SELECT '):
            raise DPError('READ_ONLY: serving data port accepts SELECT only')
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise DPError('QUERY_PAGE: page size must be between 1 and 100')
        result = super().request(statement, binds, write=False, limit=limit)
        if time.monotonic() >= self.deadline:
            raise BudgetPause('QUERY_DEADLINE: result arrived after request deadline')
        if len(canonical(result).encode()) > MAX_RESPONSE_BYTES:
            raise DPError('QUERY_RESPONSE_SIZE: narrow the requested scope/page')
        return result


def checked_id(value, name):
    if not isinstance(value, str) or not value or len(value.encode()) > 512:
        raise DPError('QUERY_ID: invalid ' + name)
    return value


def _page_size(value):
    if type(value) is not int or not 1 <= value <= MAX_PAGE:
        raise DPError('QUERY_PAGE: page size must be between 1 and 100')
    return value


@dataclass(frozen=True)
class Snapshot:
    release_id: str
    dataset_version: str
    generation_id: str
    source_store_sha256: str
    manifest: dict
    excluded: frozenset[str]
    binding_hash: str

    @classmethod
    def open(cls, sql, release_id):
        if not isinstance(release_id, str) or not re.fullmatch('[0-9a-f]{64}', release_id):
            raise DPError('DP_CONFIG: completed Oracle DP_RELEASE_ID required')
        release = get_release(sql, release_id)
        manifest = release['source_manifest']
        # The existing publication hashes the exact manifest bytes as version.
        text = release['source_manifest_text']
        version = release['dataset_version']
        if (json.loads(text) != manifest or
                hashlib.sha256(text.encode()).hexdigest() != version):
            raise DPError('QUERY_MANIFEST: source manifest/version mismatch')
        selection = release.get('search_selection') or {}
        if selection and (selection.get('manifest_sha256') != version or
                          selection.get('store_sha256') != manifest['store_sha256']):
            raise DPError('QUERY_SELECTION: selection belongs to another version')
        excluded = frozenset(row['document_id'] for row in selection.get('excluded', []))
        return cls(release_id, version, manifest['generation_id'], manifest['store_sha256'],
                   manifest, excluded, digest({'release_id': release_id, 'connection': sql.binding}))

    def reader(self, sql, *, document_ids, verify_rows=None):
        """An explicit authorized scope is required, even for an empty scope."""
        if isinstance(document_ids, (str, bytes)) or document_ids is None:
            raise DPError('QUERY_SCOPE: explicit authorized document IDs required')
        allowed = frozenset(checked_id(d, 'document_id') for d in document_ids)
        known = frozenset(self.manifest['scope']['document_version_ids'])
        if allowed - known or allowed & self.excluded:
            raise DPError('QUERY_SCOPE: unknown or excluded document')
        if digest({'release_id': self.release_id, 'connection': sql.binding}) != self.binding_hash:
            raise DPError('QUERY_BINDING: request connection differs from snapshot')
        return SourceReader(sql, self, allowed, verify_rows=verify_rows)


class SourceReader:
    """Bounded ID/range reads against the already-published Oracle source rows."""
    MEMO_BYTES = 32 * 1024 * 1024

    def __init__(self, sql, snapshot, allowed, *, verify_rows=None):
        self.sql, self.snapshot, self.allowed = sql, snapshot, allowed
        self.verify_rows = verify_rows
        # Verified rows of this request's pinned release (never shared across requests).
        self._memo_lock = threading.Lock()
        self._blocks, self._documents, self._units, self._memo_bytes = {}, {}, {}, 0

    def _reuse(self):
        # Same switch as the process cache of published rows (GENOS_ORACLE_SHARED_CACHE, field
        # default on). With it off, every read is verified again, as before.
        cache = getattr(self.sql, 'shared_cache', None)
        return bool(cache is not None and getattr(cache, 'enabled', False) and getattr(self.sql, 'shared_scope', None))

    def _remember(self, table, key, value):
        if not self._reuse():
            return
        size = len(json.dumps(value, ensure_ascii=False, default=str).encode())
        with self._memo_lock:
            if key not in table and self._memo_bytes + size <= self.MEMO_BYTES:
                table[key] = value
                self._memo_bytes += size

    def _where(self, did):
        checked_id(did, 'document_id')
        if did not in self.allowed:
            raise DPError('QUERY_SCOPE: document outside authorized request scope')
        return ('DATASET_VERSION=:version AND DOCUMENT_ID=:document',
                [('version', self.snapshot.dataset_version, 'VARCHAR2'),
                 ('document', did, 'VARCHAR2')])

    def _rows(self, kind, did, predicate='', binds=(), *, limit=MAX_PAGE, order=''):
        where, base = self._where(did)
        where+=predicate
        mapping=getattr(self.sql.client,'schema_map',None)
        if mapping is not None:
            from .physical_mapping import CONTRACT_COLUMNS
            from .oracle_sql_tokens import mapped_columns
            n=mapping.names(kind)
            def physical(expression):
                return mapped_columns(expression,n,CONTRACT_COLUMNS[kind].split())
            where,order=physical(where),physical(order)
        rows = read_rows(self.sql, kind, where, [*base, *binds],
                         limit=_page_size(limit), order=order)
        for row in rows:
            if row['DATASET_VERSION'] != self.snapshot.dataset_version or row['DOCUMENT_ID'] != did:
                raise DPError('QUERY_ROW_BINDING: returned row belongs to another document/version')
        if self.verify_rows is not None:
            self.verify_rows(kind, rows)
        return rows

    def document(self, did):
        self._where(did)
        if did in self._documents and self._reuse():
            return dict(self._documents[did])
        rows = self._rows('document', did, limit=1)
        if not rows:
            raise KeyError(did)
        r = rows[0]
        value = {'document_id': did, 'name': r['NAME'],
                 'source_artifact_sha256': r['SOURCE_ARTIFACT_SHA256'], 'json': r['SOURCE_JSON']}
        self._remember(self._documents, did, value)
        return dict(value)

    def unit_ids(self, did, *, after=None, limit=MAX_PAGE):
        """Read candidate IDs from the authorized source index, never evidence.

        Callers must fetch and verify the corresponding published native rows.
        Avoid fetching/parsing source JSON when only the indexed identity is used.
        """
        from .oracle_dp_io import names, OWNER, TABLES
        _, binds = self._where(did)
        limit = _page_size(limit)
        n = names(self.sql, 'source_unit', OWNER+'.'+TABLES['source_unit'])
        where = n.c('DATASET_VERSION')+'=:version AND '+n.c('DOCUMENT_ID')+'=:document'
        order = "NLSSORT("+n.c('UNIT_ID')+",'NLS_SORT=BINARY')"
        if after is not None:
            checked_id(after, 'after_unit_id')
            where += " AND "+order+">NLSSORT(:after_unit,'NLS_SORT=BINARY')"
            binds.append(('after_unit',after,'VARCHAR2'))
        projection = ','.join(n.select(c) for c in ('DATASET_VERSION','DOCUMENT_ID','UNIT_ID'))
        rows = self.sql.query(f'SELECT {projection} FROM {n.table} WHERE {where} ORDER BY {order} FETCH FIRST {limit} ROWS ONLY',binds,limit=limit)
        ids=[]
        for row in rows:
            if row['DATASET_VERSION']!=self.snapshot.dataset_version or row['DOCUMENT_ID']!=did:
                raise DPError('QUERY_ROW_BINDING: unit ID belongs to another document/version')
            ids.append(checked_id(row['UNIT_ID'],'unit_id'))
        if ids!=sorted(set(ids)) or (after is not None and any(uid<=after for uid in ids)):
            raise DPError('QUERY_PAGE_ORDER: invalid source unit ID page')
        return {'rows':ids,'next':ids[-1] if len(ids)==limit else None}

    def unit(self, did, uid):
        uid = checked_id(str(uid), 'unit_id')
        self._where(did)
        if (did, uid) in self._units and self._reuse():
            found = self._units[(did, uid)]
            if found is None:
                raise KeyError((did, uid))
            return dict(found)
        rows = self._rows('source_unit', did, ' AND UNIT_ID=:unit', [('unit', uid, 'VARCHAR2')], limit=1)
        if not rows:
            self._remember(self._units, (did, uid), None)
            raise KeyError((did, uid))
        r = rows[0]
        value = {'document_id': did, 'unit_id': r['UNIT_ID'], 'parent_id': r['PARENT_ID'], 'json': r['SOURCE_JSON']}
        self._remember(self._units, (did, uid), value)
        return dict(value)

    def sources(self, did, bids):
        ids = [checked_id(str(b), 'block_id') for b in bids]
        self._where(did)
        if len(ids) > MAX_IDS:
            raise DPError('QUERY_PAGE: split block reads into pages of at most 100')
        if not ids:
            return []
        unique = list(dict.fromkeys(ids))
        reuse = self._reuse()
        converted = {bid: self._blocks[(did, bid)] for bid in unique if reuse and (did, bid) in self._blocks}
        missing = [bid for bid in unique if bid not in converted]
        if missing:
            rows = self._rows('block_payload', did,
                              ' AND BLOCK_ID IN (' + ','.join(':b'+str(i) for i in range(len(missing))) + ')',
                              [('b'+str(i), bid, 'VARCHAR2') for i, bid in enumerate(missing)], limit=len(missing))
            found = {r['BLOCK_ID']: r for r in rows}
            if len(found) != len(rows) or set(found) != set(missing):
                raise DPError('QUERY_SOURCE_MISSING: requested block set differs; no partial success')
            doc = self.document(did)
            for bid, r in found.items():
                converted[bid] = self._block(r, doc['source_artifact_sha256'])
                self._remember(self._blocks, (did, bid), converted[bid])
        return [dict(converted[bid]) for bid in ids]

    def source(self, did, bid):
        return self.sources(did, [bid])[0]

    def section(self, did, uid, *, max_blocks=4096):
        """Existing Store.section contract, scoped to one explicitly chosen unit.

        Only that unit's range and ancestor chain are read. An oversized range
        is an explicit request to use blocks() pagination, never a truncated
        successful section. The shared SQL budget also bounds deep structures.
        """
        if type(max_blocks) is not int or not 1 <= max_blocks <= 4096:
            raise DPError('QUERY_PAGE: invalid section block budget')
        uid = checked_id(str(uid), 'unit_id')
        first = self.unit(did, uid)
        unit = json.loads(first['json'])
        span = unit.get('span')
        if (not isinstance(span,list) or len(span)!=2 or
                any(type(n) is not int or n<0 for n in span) or span[1]<span[0]):
            raise DPError('QUERY_UNIT_SPAN: unit has no valid original block interval')
        ancestors, seen, current, row = [], set(), uid, first
        while current is not None:
            if current in seen or len(seen)>=256:
                raise DPError('QUERY_ANCESTOR: cycle or excessive ancestor depth')
            seen.add(current)
            value = json.loads(row['json'])
            ancestors.append({'id':current,'title':value.get('title',value.get('surface','')),
                              'family':value.get('family')})
            current = str(row['parent_id']) if row['parent_id'] is not None else None
            if current is not None:
                try:
                    row = self.unit(did,current)
                except KeyError as exc:
                    raise DPError('QUERY_ANCESTOR: missing parent within pinned document') from exc
        blocks, after = [], None
        while True:
            page = self.blocks(did,start=span[0],stop=span[1],after=after,limit=min(MAX_PAGE,max_blocks-len(blocks)+1))
            blocks.extend({k:r[k] for k in ('block_id','unit_id','text')} for r in page['rows'])
            if len(blocks)>max_blocks:
                raise DPError('QUERY_SECTION_SIZE: use explicit block pages; no partial section returned')
            after = page['next_after']
            if after is None:
                break
        doc = self.document(did)
        return {'document_id':did,'document_name':doc['name'],'unit_id':uid,'title':unit.get('title',''),
                'ancestors':list(reversed(ancestors)),'blocks':blocks}

    def source_scope(self, did, bid):
        source = self.source(did,bid)
        uid = source['unit_id']
        if uid is not None:
            try:
                self.unit(did,uid)
            except KeyError:
                pass  # Same raw-block contract as Store.source_scope.
            else:
                return self.section(did,uid)
        return {'document_id':did,'document_name':self.document(did)['name'],'unit_id':None,'title':'',
                'ancestors':[],'blocks':[source],'unresolved_reason':'SOURCE_WITHOUT_STRUCTURAL_UNIT'}

    @staticmethod
    def _block(row, document_sha):
        if row['SOURCE_ARTIFACT_SHA256'] != document_sha:
            raise DPError('QUERY_SOURCE_PROVENANCE: block/document artifact mismatch')
        value = row['SOURCE_JSON']
        if row['JSON_TEXT_ELIDED']:
            parsed = json.loads(value)
            parsed['text'] = row['TEXT']
            value = json.dumps(parsed, ensure_ascii=False, separators=(',', ':'))
        return {'document_id': row['DOCUMENT_ID'], 'block_id': row['BLOCK_ID'],
                'unit_id': row['UNIT_ID'], 'text': row['TEXT'],
                'source_artifact_sha256': document_sha, 'json': value}

    def blocks(self, did, *, start=0, stop=None, after=None, limit=MAX_PAGE):
        """Keyset pagination; the caller never loads a complete corpus to slice it."""
        limit = _page_size(limit)
        if type(start) is not int or start < 0 or (stop is not None and (type(stop) is not int or stop < start)):
            raise DPError('QUERY_RANGE: invalid block interval')
        if after is not None and (type(after) is not int or after < 0):
            raise DPError('QUERY_CURSOR: nonnegative block number required')
        predicates = [' AND TO_NUMBER(BLOCK_ID)>=:block_start']
        binds = [('block_start', start, 'NUMBER')]
        if stop is not None:
            predicates.append(' AND TO_NUMBER(BLOCK_ID)<:stop')
            binds.append(('stop', stop, 'NUMBER'))
        if after is not None:
            predicates.append(' AND TO_NUMBER(BLOCK_ID)>:after')
            binds.append(('after', after, 'NUMBER'))
        rows = self._rows('block_payload', did, ''.join(predicates), binds, limit=limit,
                          order=f'ORDER BY TO_NUMBER(BLOCK_ID) FETCH FIRST {limit} ROWS ONLY')
        numbers = [int(r['BLOCK_ID']) for r in rows]
        if numbers != sorted(set(numbers)) or any(n < start or (stop is not None and n >= stop) or
                                                  (after is not None and n <= after) for n in numbers):
            raise DPError('QUERY_PAGE_ORDER: invalid block page')
        doc = self.document(did)
        return {'rows': [self._block(r, doc['source_artifact_sha256']) for r in rows],
                'next_after': numbers[-1] if len(rows) == limit else None,
                'release_id': self.snapshot.release_id}
