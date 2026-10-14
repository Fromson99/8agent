"""Deterministic search-contract regressions; synthetic data, no model benchmark."""
from contextlib import closing
from hashlib import sha256
import json
import logging
import sqlite3
from types import SimpleNamespace

import pytest
from test_unit_fulltext_adaptive_read import tree, session  # noqa: F401
from semantic_runtime import query_latency as latency, unit_fulltext as uf
from semantic_runtime.legal_agent import law_candidates as lc
from semantic_runtime.term_index import SourceMap


def pages(idx, db, terms, allowed):
    laws = idx.law_groups_page(db, terms, allowed, limit=1)
    result = [('law', laws)]
    cursor = laws['next_cursor']
    while cursor:
        page = idx.law_groups_page(db, terms, allowed, cursor=cursor, limit=1)
        result.append(('law', page)); cursor = page['next_cursor']
    for did in ('d', 'other', 'missing'):
        articles = idx.article_groups_page(db, terms, did, allowed, limit=1)
        result.append(('articles', articles))
        for item in articles['items']:
            cursor = None
            while True:
                page = idx.hit_page(db, terms, item['source_id'], allowed, cursor=cursor, limit=1)
                result.append(('hit', page)); cursor = page['next_cursor']
                if not cursor: break
    return result


@pytest.mark.parametrize('terms', [['승인', '원문'], ['긴급'], ['승인', '승인', '보고'], ['없는표현'], []])
@pytest.mark.parametrize('scope', ['all', 'd', 'empty'])
def test_exact_ranking_totals_cursors_bodies_match_sql(tree, terms, scope):
    _, idx = tree
    before = sha256((idx.path/'units.sqlite').read_bytes()).hexdigest()
    with closing(idx.connect()) as cached, closing(sqlite3.connect(
            'file:'+str(idx.path/'units.sqlite')+'?mode=ro', uri=True)) as oracle:
        allowed = None if scope == 'all' else ({r[0] for r in oracle.execute(
            "SELECT DISTINCT source_id FROM unit WHERE document_id='d'")} if scope == 'd' else set())
        assert pages(idx, cached, terms, allowed) == pages(idx, oracle, terms, allowed)
        assert pages(idx, cached, terms, allowed) == pages(idx, oracle, terms, allowed)
    assert sha256((idx.path/'units.sqlite').read_bytes()).hexdigest() == before


def test_one_fts_scan_and_body_only_reads_for_following_previews(tree):
    _, idx = tree
    with closing(idx.connect()) as db:
        traced = []; db.set_trace_callback(traced.append)
        laws = idx.law_groups_page(db, ['승인', '원문'])
        for law in laws['items']:
            for article in idx.article_groups_page(db, ['승인', '원문'], law['document_id'])['items']:
                idx.hit_page(db, ['승인', '원문'], article['source_id'], limit=3)
        matches = [s for s in traced if 'WHERE unit_fts MATCH' in s]
        assert len(matches) == 1
        assert 'u.json' not in matches[0]
        assert all('text' not in repr(v) for v in db._match_projection['hits'].values())


def test_overflow_never_truncates_and_does_not_retry_projection(tree, monkeypatch):
    _, idx = tree; monkeypatch.setattr(uf, 'MATCH_CACHE_ROWS', 1)
    with closing(idx.connect()) as db, closing(sqlite3.connect(
            'file:'+str(idx.path/'units.sqlite')+'?mode=ro', uri=True)) as oracle:
        traced = []; db.set_trace_callback(traced.append)
        expected = pages(idx, oracle, ['승인', '원문'], None)
        assert pages(idx, db, ['승인', '원문'], None) == expected
        assert pages(idx, db, ['승인', '원문'], None) == expected
        assert db._match_projection is None
        assert len([s for s in traced if s.startswith('SELECT u.key,u.document_id')]) == 1


def test_cache_rebind_acl_query_cursor_and_database_change(tree):
    _, idx = tree
    with closing(idx.connect()) as db:
        page = idx.law_groups_page(db, ['승인', '원문'], limit=1)
        page['items'][0]['document_id'] = 'mutated'
        assert idx.law_groups_page(db, ['승인', '원문'], limit=1)['items'][0]['document_id'] != 'mutated'
        scope = {r[0] for r in db.execute("SELECT source_id FROM unit WHERE document_id='d'")}
        assert idx.law_groups_page(db, ['승인', '원문'], scope)['total'] == 1
        assert idx.law_groups_page(db, ['없는표현'], scope)['total'] == 0
        with pytest.raises(ValueError, match='cursor'):
            idx.law_groups_page(db, ['승인'], cursor=page['next_cursor'])
        with (idx.path/'units.sqlite').open('ab') as f: f.write(b'changed')
        with pytest.raises(ValueError, match='changed'):
            idx.law_groups_page(db, ['승인', '원문'], scope)


def test_projection_shared_across_connections_and_interrupt_not_cached(tree):
    _, idx = tree
    with closing(idx.connect()) as first, closing(idx.connect()) as second:
        idx.law_groups_page(first, ['승인'])
        assert not hasattr(second, '_match_binding')
        assert idx.law_groups_page(second, ['승인']) == idx.law_groups_page(first, ['승인'])
        second.execute('SELECT rowid FROM unit_fts LIMIT 1').fetchall()
        second.set_progress_handler(lambda: 1, 1)
        with pytest.raises(sqlite3.OperationalError, match='interrupted'):
            idx.law_groups_page(second, ['원문'])
        assert getattr(second, '_match_binding', None) is None
        second.set_progress_handler(None, 0)
        assert idx.law_groups_page(second, ['승인']) == idx.law_groups_page(first, ['승인'])
    assert first._match_projection is None


def test_allowed_scope_uses_metadata_without_decoding_all_bodies(tree):
    gen, _ = tree
    with closing(sqlite3.connect('file:'+str(gen/'navigation/navigation.sqlite')+'?mode=ro', uri=True)) as db:
        sources = SourceMap(db); traced = []; db.set_trace_callback(traced.append)
        s = SimpleNamespace(scope={'d'}, tools=SimpleNamespace(sources=sources))
        ids = lc.allowed(s)
        assert ids and not sources.cache
        assert lc.allowed(s) is ids
        assert len([sql for sql in traced if sql.startswith('SELECT id FROM source')]) == 1
        s.scope = {'other'}
        assert lc.allowed(s).isdisjoint(ids)
        s.scope = set()
        assert lc.allowed(s) == frozenset()
        s.tools.sources = {'x': {'document_id': 'd'}}; s.scope = {'d'}
        assert lc.allowed(s) == {'x'}


@pytest.mark.parametrize('configured', [None, '0', '1'])
def test_rolled_back_diagnostics_preserve_failure_and_emit_no_logs(monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv('GENOS_QUERY_LATENCY', raising=False)
    else:
        monkeypatch.setenv('GENOS_QUERY_LATENCY', configured)
    records = []
    class Capture(logging.Handler):
        def emit(self, record): records.append(record)
    logger = logging.getLogger('semantic_runtime.query_latency')
    handler = Capture(); logger.addHandler(handler); prior = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        with pytest.raises(RuntimeError, match='private-query-sentinel'):
            with latency.span('law.test', pressure=True):
                raise RuntimeError('private-query-sentinel')
        with latency.span('law.test'): pass
        assert records == []
    finally:
        logger.removeHandler(handler); logger.setLevel(prior)
