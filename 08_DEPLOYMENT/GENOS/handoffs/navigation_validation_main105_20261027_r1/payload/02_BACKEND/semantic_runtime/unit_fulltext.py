"""Own-block FTS: the stored structural owner, never its descendants, is a hit.

This derived index does not rewrite the source store or article navigation.
Article IDs are a compatibility projection; unit IDs remain the search identity.
"""
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from contextlib import nullcontext
from pathlib import Path
import json
import sqlite3
import time
from itertools import islice
from .fulltext import _search_forms, expression, sha, tokenizer_version, TAGS
from . import query_latency as latency
from .runtime_cache import CACHE

SCHEMA = 'semantic-unit-fulltext-v1'
MATCH_CACHE_ROWS = 50000


class _SearchConnection(sqlite3.Connection):
    """Request-owned SQLite handle and fast references to the process cache."""
    def close(self):
        self._match_projection = None
        self._match_binding = None
        self._cache_remaining = None
        super().close()


def build(store, navigation, output, *, document_ids=None, workers=None):
    store, navigation, output = map(Path, (store, navigation, output))
    from . import fulltext
    progress = getattr(fulltext, '_BUILD_PROGRESS', lambda **kw: None)
    progress(task='unit-fulltext-input-verification', completed=0, total=None, unit='checks')
    if workers is None: workers = fulltext.automatic_workers((store/'store.sqlite').stat().st_size)
    if type(workers) is not int or workers < 1: raise ValueError('workers must be positive')
    if output.resolve() == store.resolve(): raise ValueError('cannot overwrite source generation')
    sm = json.loads((store/'manifest.json').read_text())
    nm = json.loads((navigation/'manifest.json').read_text())
    if (nm['generation_id'] != sm['generation_id'] or
            nm['source_store_sha256'] != sm['store_sha256'] or sha(store/'store.sqlite') != sm['store_sha256']):
        raise ValueError('unit FTS source binding mismatch')
    if sha(navigation/'navigation.sqlite') != nm['index_sha256']:
        raise ValueError('unit FTS navigation hash mismatch')
    started = time.monotonic()
    input_pins = {p:sha(p) for p in (store/'manifest.json',store/'store.sqlite',navigation/'manifest.json',navigation/'navigation.sqlite')}
    output.mkdir(parents=True, exist_ok=False)
    sd = sqlite3.connect('file:'+str(store/'store.sqlite')+'?mode=ro', uri=True)
    nd = sqlite3.connect('file:'+str(navigation/'navigation.sqlite')+'?mode=ro', uri=True)
    db = sqlite3.connect(output/'units.sqlite')
    count = 0
    try:
        known = {r[0] for r in sd.execute('SELECT document_id FROM document')}
        scope = known if document_ids is None else set(document_ids)
        if not scope or scope-known or workers < 1:
            raise ValueError('invalid unit FTS build scope/workers')
        progress(task='unit-fulltext-structure-projection', completed=0, total=None, unit='blocks')
        total=sum(sd.execute('SELECT count(*) FROM (SELECT unit_id,CASE WHEN unit_id IS NULL THEN block_id END '
                  'FROM source_block WHERE document_id=? GROUP BY 1,2)',(did,)).fetchone()[0] for did in scope)
        stats={'sources':set(),'blocks':0,'navigation_blocks':0}
        db.execute('CREATE TABLE unit(key TEXT PRIMARY KEY,source_id TEXT,document_id TEXT,json TEXT)')
        db.execute('CREATE INDEX unit_source ON unit(source_id)')
        db.execute('CREATE VIRTUAL TABLE unit_fts USING fts5(key UNINDEXED,body,tokenize="unicode61")')
        entries = _entries(sd,nd,scope,stats)
        progress(task='unit-tokenize-and-index', completed=0, total=total, unit='structural_units')
        with (ProcessPoolExecutor(max_workers=workers, mp_context=get_context('spawn')) if workers>1 else nullcontext()) as pool:
            while part := list(islice(entries,128)):
                forms = pool.map(_search_forms, (r['text'] for r in part), chunksize=16) if pool else map(_search_forms,(r['text'] for r in part))
                for row, tokens in zip(part, forms):
                    db.execute('INSERT INTO unit VALUES(?,?,?,?)',(row['key'],row['source_id'],row['document_id'],json.dumps(row,ensure_ascii=False)))
                    db.execute('INSERT INTO unit_fts VALUES(?,?)',(row['key'],tokens))
                count += len(part); db.commit()
                progress(task='unit-tokenize-and-index', completed=count, total=total, unit='structural_units')
                print(f'UNIT_FTS indexed={count}/{total} seconds={time.monotonic()-started:.1f}',flush=True)
        if count!=total:raise ValueError('structural owner count does not match indexed units')
        progress(task='unit-fulltext-optimize-and-verify', completed=0, total=None, unit='checks')
        db.execute("INSERT INTO unit_fts(unit_fts) VALUES('optimize')"); db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('unit FTS integrity failure')
        manifest = {'schema_version':SCHEMA,'generation_id':sm['generation_id'],
            'source_store_sha256':sm['store_sha256'],'navigation_index_sha256':nm['index_sha256'],
            'tokenizer':{'name':'pecab','version':tokenizer_version(),'tags':list(TAGS)},
            'ranking':{'query':'OR','body_only':True,'heading_indexed':False},
            'scope':{'document_version_ids':sorted(scope),'source_ids':sorted(stats['sources'])},
            'counts':{'unit':count,'source':len(stats['sources']),'covered_blocks':stats['blocks'],'navigation_blocks':stats['navigation_blocks']},
            'granularity':'stored-own-block-owner', 'descendant_text_included':False,
            'source_manifest_sha256':input_pins[store/'manifest.json'],
            'navigation_manifest_sha256':input_pins[navigation/'manifest.json'],
            'tokenizer_code_sha256':sha(Path(fulltext.__file__)),
            'builder_sha256':sha(__file__),'build_seconds':time.monotonic()-started}
    finally:
        sd.close();nd.close();db.close()
    manifest['index_sha256'] = sha(output/'units.sqlite')
    if any(sha(p)!=v for p,v in input_pins.items()): raise ValueError('unit fulltext input changed during build')
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def _entries(sd,nd,scope,stats):
    """Keep document-local ownership and at most one unit body; never retain the corpus."""
    for did in sorted(scope):
        owners,roots={},{}
        for sid,raw in nd.execute('SELECT id,json FROM source WHERE document_id=? ORDER BY id',(did,)):
            source=json.loads(raw)
            roots[sid]={k:source.get(k) for k in ('unit_id','document_name','heading')}
            stats['sources'].add(sid)
            for block in source['blocks']:
                bid=str(block['block_id'])
                if bid in owners:raise ValueError('a source block belongs to two article roots')
                owners[bid]=sid;stats['navigation_blocks']+=1
        known_units={str(r[0]) for r in sd.execute('SELECT unit_id FROM source_unit WHERE document_id=?',(did,))}
        previous,row=None,None;covered=set()
        for bid,uid,body in sd.execute('SELECT block_id,unit_id,text FROM source_block WHERE document_id=? '
                                      'ORDER BY unit_id,CAST(block_id AS INTEGER)',(did,)):
            bid=str(bid);sid=owners.get(bid)
            if sid is None:raise ValueError('selected source block missing from navigation')
            uid=str(uid) if uid is not None else None
            if uid is not None and uid not in known_units:raise ValueError('unit fulltext structural owner missing')
            key=(sid,uid if uid is not None else 'block:'+bid)
            if key!=previous:
                if row:
                    row['text']='\n'.join(row.pop('texts'));yield row
                row={'key':sid+'#unit:'+key[1],'source_id':sid,'document_id':did,'unit_id':uid,
                     'article_unit_id':roots[sid]['unit_id'],'document_name':roots[sid]['document_name'],
                     'heading':roots[sid]['heading'] or '', 'block_ids':[],'texts':[]}
                previous=key
            row['block_ids'].append(bid);row['texts'].append(body);covered.add(bid);stats['blocks']+=1
        if row:
            row['text']='\n'.join(row.pop('texts'));yield row
        if covered!=set(owners):raise ValueError('navigation contains blocks missing from selected structure')


class UnitFulltextIndex:
    def __init__(self, path, navigation_manifest):
        self.path = Path(path)
        for p in (self.path/'manifest.json',self.path/'units.sqlite'):
            if p.is_symlink() or Path(str(p)+'-wal').exists(): raise ValueError('unbound unit fulltext file')
        self.manifest = m = json.loads((self.path/'manifest.json').read_text())
        if m.get('schema_version') != SCHEMA or m['generation_id'] != navigation_manifest['generation_id'] or m['source_store_sha256'] != navigation_manifest['source_store_sha256'] or m['navigation_index_sha256'] != navigation_manifest['index_sha256']:
            raise ValueError('unit FTS generation mismatch')
        if m['index_sha256'] != sha(self.path/'units.sqlite') or m['tokenizer'] != {'name':'pecab','version':tokenizer_version(),'tags':list(TAGS)}:
            raise ValueError('unit FTS hash/tokenizer mismatch')
        self.source_ids = frozenset(m['scope']['source_ids'])
        self.indexed_scope_ids = self.source_ids
        self._signature = self.signature()

    def signature(self):
        files=(self.path/'manifest.json',self.path/'units.sqlite')
        if any(p.is_symlink() or Path(str(p)+'-wal').exists() for p in files): raise ValueError('unbound unit fulltext file')
        return tuple((p.stat().st_dev,p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ctime_ns) for p in files)

    def check_unchanged(self):
        if self.signature()!=self._signature:raise ValueError('unit FTS changed; reopen and verify')

    def connect(self):
        self.check_unchanged()
        with latency.span('unit_fts.connect'):
            from .resident_data import POOL
            db = POOL.connect(self.path/'units.sqlite', expected=self.manifest['index_sha256'],
                              factory=_SearchConnection)
        return db

    def cache_namespace(self):
        self.check_unchanged()
        return (str(self.path.resolve()), self._signature, self.manifest['generation_id'],
                self.manifest['source_store_sha256'], self.manifest['navigation_index_sha256'],
                self.manifest['index_sha256'], SCHEMA)

    def _projection(self, db, terms, allowed):
        """Reuse exact rank metadata, or fall back to complete SQL on overflow.

        No truncation is exposed to callers. Main DB bytes and schema stay immutable.
        Query order/duplicates are part of the cache key even though cursor identity
        preserves the older normalized-term contract.
        """
        if not isinstance(db, _SearchConnection):
            return None
        scope = self.source_ids if allowed is None else frozenset(allowed)
        binding = ('matches', self.cache_namespace(), tuple(terms), scope, MATCH_CACHE_ROWS)
        hit = getattr(db, '_match_binding', None) == binding
        with latency.span('unit_fts.projection', cache_hit=hit, allowed_count=len(scope),
                          term_count=len(terms), cache_scope='process') as metrics:
            if hit:
                metrics['cache_overflow'] = db._match_projection is None
                return db._match_projection
            db._match_binding = None; db._match_projection = None
            def build():
                matches = latency.rows(db,
                    'SELECT u.key,u.document_id,u.source_id,unit_fts.rank FROM unit_fts '
                    'JOIN unit u ON u.key=unit_fts.key WHERE unit_fts MATCH ? '
                    'AND u.source_id IN (SELECT value FROM json_each(?)) LIMIT ?',
                    [expression(terms), json.dumps(sorted(scope)), MATCH_CACHE_ROWS+1], 'project_matches')
                if len(matches) > MATCH_CACHE_ROWS:
                    self.check_unchanged()
                    return None  # Share the overflow marker; fallback SQL remains complete.
                sources, documents = {}, {}
                for key, did, sid, score in matches:
                    sources.setdefault(sid, []).append((score, key))
                    groups = documents.setdefault(did, {})
                    best, count = groups.get(sid, (score, 0))
                    groups[sid] = (min(best, score), count+1)
                for hits in sources.values(): hits.sort()
                laws = []; articles = {}
                for did, groups in documents.items():
                    ranked = sorted((best, sid, count) for sid, (best, count) in groups.items())
                    articles[did] = [{'source_id': sid, 'unit_count': count} for _, sid, count in ranked]
                    laws.append((ranked[0][0], did, len(groups), sum(v[1] for v in groups.values())))
                projection = {'laws': [{'document_id': did, 'article_count': count, 'unit_count': units}
                                       for _, did, count, units in sorted(laws)],
                              'articles': articles, 'hits': sources}
                self.check_unchanged()
                return projection
            projection, stats = CACHE.get_or_build(binding, build, kind='matches',
                                                    remaining=getattr(db, '_cache_remaining', None))
            self.check_unchanged()
            metrics.update(stats, cache_overflow=projection is None,
                           match_count=MATCH_CACHE_ROWS+1 if projection is None else
                           sum(len(hits) for hits in projection['hits'].values()))
            db._match_projection = projection; db._match_binding = binding
            return projection

    @staticmethod
    def _cached_page(items, binding, offset, limit):
        from copy import deepcopy
        selected = deepcopy(items[offset:offset+limit])
        total = len(items)
        return {'items': selected, 'total': total, 'next_cursor':
                {'binding': binding, 'offset': offset+len(selected)} if offset+len(selected)<total else None}

    def rank_units(self, db, terms, allowed=None, limit=None):
        self.check_unchanged()
        if allowed is not None and set(allowed)-self.source_ids:
            raise ValueError('unit FTS does not cover requested article scope')
        if limit is not None and (not isinstance(limit,int) or limit<0): raise ValueError('invalid unit fulltext limit')
        if not terms or allowed is not None and not allowed or limit == 0:
            return []
        out = []
        scope_sql = '' if allowed is None else ' AND u.source_id IN (SELECT value FROM json_each(?))'
        params = [expression(terms)] + ([] if allowed is None else [json.dumps(sorted(allowed))])
        limit_sql = '' if limit is None else ' LIMIT ?'
        if limit is not None: params.append(limit)
        cursor = db.execute('SELECT f.key,f.rank,u.json FROM unit_fts f JOIN unit u ON u.key=f.key WHERE unit_fts MATCH ?'+scope_sql+' ORDER BY f.rank,f.key'+limit_sql,params)
        try:
            for key, score, raw in cursor:
                row = json.loads(raw)
                if allowed is None or row['source_id'] in allowed:
                    out.append({**row,'score':score,'query_terms':list(terms)})
                    if limit and len(out)>=limit: break
        finally: cursor.close()
        return out

    def rank(self, db, terms, allowed=None, limit=None):
        """Compatibility for article consumers; exact hits remain in rank_units."""
        if limit is not None and (not isinstance(limit,int) or limit<0): raise ValueError('invalid fulltext limit')
        if limit == 0: return []
        roots=list(dict.fromkeys(h['source_id'] for h in self.rank_units(db,terms,allowed)))
        return roots if limit is None else roots[:limit]

    @latency.timed('unit_fts.bind')
    def _page_query(self, terms, allowed, cursor, limit, kind, identity=None, unit_keys=None):
        """Bind pagination to the immutable index, query, ACL and group identity."""
        from .contracts import digest
        self.check_unchanged()
        if type(limit) is not int or limit < 1:
            raise ValueError('invalid fulltext page size')
        scope = self.source_ids if allowed is None else set(allowed)
        if scope-self.source_ids:
            raise ValueError('unit FTS does not cover requested article scope')
        binding = digest({'index': self.manifest['index_sha256'], 'order': 'best-own-block-match-v1', 'terms': sorted(set(terms)),
                          'scope': sorted(scope), 'kind': kind, 'identity': identity,
                          **({'unit_keys':sorted(set(unit_keys))} if unit_keys is not None else {})})
        offset = 0
        if cursor is not None:
            if (set(cursor) != {'binding', 'offset'} or cursor['binding'] != binding
                    or type(cursor['offset']) is not int or cursor['offset'] < 0):
                raise ValueError('fulltext cursor belongs to another query, scope or group')
            offset = cursor['offset']
        where = 'unit_fts MATCH ? AND u.source_id IN (SELECT value FROM json_each(?))'
        params = [expression(terms) if terms else '""', json.dumps(sorted(scope))]
        if kind == 'articles':
            where += ' AND u.document_id=?'; params.append(identity)
        elif kind == 'hits':
            where += ' AND u.source_id=?'; params.append(identity)
        if unit_keys is not None:
            where += ' AND u.key IN (SELECT value FROM json_each(?))'; params.append(json.dumps(sorted(set(unit_keys))))
        return where, params, binding, offset, bool(terms and scope and (unit_keys is None or unit_keys))

    def law_groups_page(self, db, terms, allowed=None, *, cursor=None, limit=12, unit_keys=None):
        """All matching laws remain addressable before any top-k source selection."""
        where, params, binding, offset, nonempty = self._page_query(terms, allowed, cursor, limit, 'laws', unit_keys=unit_keys)
        if not nonempty:
            return {'items': [], 'total': 0, 'next_cursor': None}
        projection = self._projection(db, terms, allowed) if unit_keys is None else None
        if projection is not None:
            return self._cached_page(projection['laws'], binding, offset, limit)
        join = ' FROM unit_fts JOIN unit u ON u.key=unit_fts.key WHERE '+where
        total = latency.rows(db, 'SELECT COUNT(DISTINCT u.document_id)'+join, params, 'count_laws')[0][0]
        # Materialize FTS rank before aggregation; bm25 cannot run in a GROUP BY
        # context. Keep every candidate and use the score only for menu ordering.
        matches = 'WITH matches AS MATERIALIZED (SELECT u.document_id,u.source_id,unit_fts.rank AS match_score'+join+') '
        rows = latency.rows(db, matches+'SELECT document_id,COUNT(DISTINCT source_id),COUNT(*) FROM matches'+
            ' GROUP BY document_id ORDER BY MIN(match_score),document_id LIMIT ? OFFSET ?', [*params, limit, offset], 'rank_laws')
        items = [{'document_id': did, 'article_count': articles, 'unit_count': units}
                 for did, articles, units in rows]
        return {'items': items, 'total': total, 'next_cursor':
                {'binding': binding, 'offset': offset+len(items)} if offset+len(items)<total else None}

    def article_groups_page(self, db, terms, document_id, allowed=None, *, cursor=None, limit=8, unit_keys=None):
        where, params, binding, offset, nonempty = self._page_query(terms, allowed, cursor, limit, 'articles', document_id, unit_keys=unit_keys)
        if not nonempty:
            return {'items': [], 'total': 0, 'next_cursor': None}
        projection = self._projection(db, terms, allowed) if unit_keys is None else None
        if projection is not None:
            return self._cached_page(projection['articles'].get(document_id, []), binding, offset, limit)
        join = ' FROM unit_fts JOIN unit u ON u.key=unit_fts.key WHERE '+where
        total = latency.rows(db, 'SELECT COUNT(DISTINCT u.source_id)'+join, params, 'count_articles')[0][0]
        matches = 'WITH matches AS MATERIALIZED (SELECT u.source_id,unit_fts.rank AS match_score'+join+') '
        rows = latency.rows(db, matches+'SELECT source_id,COUNT(*) FROM matches'+
            ' GROUP BY source_id ORDER BY MIN(match_score),source_id LIMIT ? OFFSET ?', [*params, limit, offset], 'rank_articles')
        items = [{'source_id': sid, 'unit_count': units} for sid, units in rows]
        return {'items': items, 'total': total, 'next_cursor':
                {'binding': binding, 'offset': offset+len(items)} if offset+len(items)<total else None}

    def hit_page(self, db, terms, source_id, allowed=None, *, cursor=None, limit=16, unit_keys=None):
        """Retrieve one source's own-block hits; lexical score stays server-side."""
        where, params, binding, offset, nonempty = self._page_query(terms, allowed, cursor, limit, 'hits', source_id, unit_keys=unit_keys)
        if not nonempty:
            return {'items': [], 'total': 0, 'next_cursor': None}
        projection = self._projection(db, terms, allowed) if unit_keys is None else None
        if projection is not None:
            hits = projection['hits'].get(source_id, [])
            keys = [key for _, key in hits[offset:offset+limit]]
            def load_bodies():
                rows = latency.rows(db, 'SELECT key,json FROM unit WHERE key IN (SELECT value FROM json_each(?))',
                                    [json.dumps(keys)], 'read_hit_bodies')
                if {key for key, _ in rows} != set(keys):
                    raise ValueError('unit FTS projection body missing')
                self.check_unchanged()
                return tuple((key, raw) for key, raw in rows)
            rows, _ = CACHE.get_or_build(('preview', self.cache_namespace(), tuple(sorted(keys))),
                                        load_bodies, kind='preview',
                                        remaining=getattr(db, '_cache_remaining', None)) if keys else ((), {})
            self.check_unchanged()
            with latency.span('unit_fts.decode', fetched_count=len(rows)):
                bodies = {key: json.loads(raw) for key, raw in rows}
                if set(bodies) != set(keys): raise ValueError('unit FTS projection body missing')
                items = [{**bodies[key], 'query_terms': list(terms)} for key in keys]
            total = len(hits)
            return {'items': items, 'total': total, 'next_cursor':
                    {'binding': binding, 'offset': offset+len(items)} if offset+len(items)<total else None}
        join = ' FROM unit_fts JOIN unit u ON u.key=unit_fts.key WHERE '+where
        total = latency.rows(db, 'SELECT COUNT(*)'+join, params, 'count_hits')[0][0]
        rows = latency.rows(db, 'SELECT u.json'+join+' ORDER BY unit_fts.rank,u.key LIMIT ? OFFSET ?',
                          [*params, limit, offset], 'rank_hits')
        with latency.span('unit_fts.decode', fetched_count=len(rows)):
            items = [{**json.loads(raw), 'query_terms': list(terms)} for (raw,) in rows]
        return {'items': items, 'total': total, 'next_cursor':
                {'binding': binding, 'offset': offset+len(items)} if offset+len(items)<total else None}


class ArticleProjection:
    """Existing recall/reference discovery uses projected roots; hits stay exact."""
    def __init__(self, index, db):
        self.index,self.db = index,db
        self.manifest = index.manifest
        self.calls = []
    def rank(self, ignored_db, terms, allowed=None, limit=None):
        hits = self.index.rank_units(self.db,terms,allowed)
        roots = list(dict.fromkeys(h['source_id'] for h in hits))
        kept = roots[:limit] if limit else roots
        self.calls.append({'terms':list(terms),'allowed_count':None if allowed is None else len(allowed),
            'hits':hits,'projected_source_ids':kept})
        return kept
