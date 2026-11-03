"""Request-scoped Oracle reads. No source mirror, file journal, or data cache.

This is the data access port, not a replacement legal reasoning engine. A
snapshot pins one completed publication for the entire request. Callers supply
their already-authorized document scope; this module never widens that scope.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import time

from . import observability as obs
from .oracle_dp_assets import get_release
from .oracle_dp_io import DPError, BudgetPause, SQL, read_rows, canonical, digest

log = obs.get_logger('oracle.query')
MAX_PAGE = 100
MAX_IDS = 100
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


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

    def query(self,statement,binds=(),*,limit=100):
        from .oracle_silver_reads import rewrite
        return super().query(rewrite(statement,getattr(self.client,'schema_map',None)),binds,limit=limit)

    def event(self, status, **extra):
        obs.event(log, 'oracle.sql', binding=self.binding, call=self.calls,
                  status=status, **extra)

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
    def __init__(self, sql, snapshot, allowed, *, verify_rows=None):
        self.sql, self.snapshot, self.allowed = sql, snapshot, allowed
        self.verify_rows = verify_rows

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
            from sqlglot import Dialect
            from sqlglot.tokens import TokenType as T
            n=mapping.names(kind)
            def physical(expression):
                tokens=Dialect.get_or_raise('oracle').tokenize(expression)
                for i,t in reversed(list(enumerate(tokens))):
                    if t.text in CONTRACT_COLUMNS[kind].split() and t.token_type in (T.VAR,T.IDENTIFIER) and (not i or tokens[i-1].token_type!=T.COLON):
                        expression=expression[:t.start]+n.c(t.text)+expression[t.end+1:]
                return expression
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
        rows = self._rows('document', did, limit=1)
        if not rows:
            raise KeyError(did)
        r = rows[0]
        return {'document_id': did, 'name': r['NAME'],
                'source_artifact_sha256': r['SOURCE_ARTIFACT_SHA256'], 'json': r['SOURCE_JSON']}

    def unit(self, did, uid):
        uid = checked_id(str(uid), 'unit_id')
        rows = self._rows('source_unit', did, ' AND UNIT_ID=:unit', [('unit', uid, 'VARCHAR2')], limit=1)
        if not rows:
            raise KeyError((did, uid))
        r = rows[0]
        return {'document_id': did, 'unit_id': r['UNIT_ID'], 'parent_id': r['PARENT_ID'], 'json': r['SOURCE_JSON']}

    def sources(self, did, bids):
        ids = [checked_id(str(b), 'block_id') for b in bids]
        self._where(did)
        if len(ids) > MAX_IDS:
            raise DPError('QUERY_PAGE: split block reads into pages of at most 100')
        if not ids:
            return []
        unique = list(dict.fromkeys(ids))
        rows = self._rows('block_payload', did,
                          ' AND BLOCK_ID IN (' + ','.join(':b'+str(i) for i in range(len(unique))) + ')',
                          [('b'+str(i), bid, 'VARCHAR2') for i, bid in enumerate(unique)], limit=len(unique))
        found = {r['BLOCK_ID']: r for r in rows}
        if len(found) != len(rows) or set(found) != set(unique):
            raise DPError('QUERY_SOURCE_MISSING: requested block set differs; no partial success')
        doc = self.document(did)
        converted = {bid: self._block(r, doc['source_artifact_sha256']) for bid, r in found.items()}
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
