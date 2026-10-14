"""Process cache lifetime/ACL/concurrency contracts; synthetic data, no model calls."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import threading
from types import SimpleNamespace

import pytest
from test_unit_fulltext_adaptive_read import tree  # noqa: F401
from semantic_runtime import runtime_cache as rc
from semantic_runtime.legal_agent import law_candidates as lc
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex


@pytest.fixture(autouse=True)
def empty_process_cache():
    rc.CACHE.clear()
    yield
    rc.CACHE.clear()


def test_closed_connection_new_session_reuses_matches_and_fresh_preview(tree):
    _, idx = tree
    with closing(idx.connect()) as first:
        law = idx.law_groups_page(first, ['승인'])
        sid = idx.article_groups_page(first, ['승인'], law['items'][0]['document_id'])['items'][0]['source_id']
        original = idx.hit_page(first, ['승인'], sid, limit=1)
        original['items'][0]['text'] = 'changed by caller'
        original['items'][0]['block_ids'].append('bad')
    assert first._match_projection is None and first._cache_remaining is None
    with closing(idx.connect()) as second:
        sql = []; second.set_trace_callback(sql.append)
        assert idx.law_groups_page(second, ['승인']) == law
        preview = idx.hit_page(second, ['승인'], sid, limit=1)
        assert preview['items'][0]['text'] != 'changed by caller'
        assert 'bad' not in preview['items'][0]['block_ids']
        assert not any('unit_fts MATCH' in s or 'SELECT key,json FROM unit' in s for s in sql)
        # A different query needs new ranking, but can reuse the exact preview.
        idx.law_groups_page(second, ['승인', '기준'])
        assert sum('unit_fts MATCH' in s for s in sql) == 1


def test_scope_ids_reused_across_sessions_and_questions_but_acl_changes(tree):
    gen, _ = tree
    with closing(Store(gen)) as store:
        nav = TermIndex(gen/'navigation', store)
        first = nav.tools(['d'])
        try:
            session = SimpleNamespace(scope={'d'}, tools=first)
            expected = lc.allowed(session)
        finally: first.db.close()
        second = nav.tools(['d'])
        try:
            sql = []; second.db.set_trace_callback(sql.append)
            session = SimpleNamespace(scope={'d'}, tools=second)
            assert lc.allowed(session) == expected
            assert not any('SELECT id FROM source' in s for s in sql)
            session.scope = {'other'}
            assert lc.allowed(session).isdisjoint(expected)
            assert sum('SELECT id FROM source' in s for s in sql) == 1
        finally: second.db.close()


def test_warm_cache_rejects_changed_generation_and_nav(tree):
    gen, idx = tree
    with closing(idx.connect()) as db:
        idx.law_groups_page(db, ['승인'])
        with (idx.path/'units.sqlite').open('ab') as file: file.write(b'changed')
        with pytest.raises(ValueError, match='changed'):
            idx.law_groups_page(db, ['승인'])
    with closing(Store(gen)) as store:
        nav = TermIndex(gen/'navigation', store); tools = nav.tools(['d'])
        try:
            lc.allowed(SimpleNamespace(scope={'d'}, tools=tools))
            with (gen/'navigation/navigation.sqlite').open('ab') as file: file.write(b'changed')
            with pytest.raises(ValueError, match='changed'):
                lc.allowed(SimpleNamespace(scope={'d'}, tools=tools))
        finally: tools.db.close()


def test_concurrent_connections_build_once(tree):
    _, idx = tree; entered = threading.Event(); release = threading.Event()
    lock = threading.Lock(); builds = []; caller_count = [0]
    def remaining():
        with lock:
            caller_count[0] += 1
            if caller_count[0] >= 3: entered.set()
    connections=[idx.connect() for _ in range(3)]
    def query(db):
        with closing(db):
            db._cache_remaining = remaining
            def trace(sql):
                if sql.startswith('SELECT u.key,u.document_id'):
                    with lock: builds.append(sql)
                    assert release.wait(5)
            db.set_trace_callback(trace)
            return idx.law_groups_page(db, ['승인'])
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(query, db) for db in connections]
        try: assert entered.wait(5)
        finally: release.set()
        results = [f.result(5) for f in futures]
    assert len(builds) == 1 and results[0] == results[1] == results[2]


def test_limits_evict_lru_without_ttl_and_oversize_not_admitted():
    cache = rc.ProcessCache(max_bytes=4096, max_entries=2)
    calls = []
    def get(key, value):
        return cache.get_or_build(key, lambda: (calls.append(key), value)[1], kind='test')
    get('a', 'one'); get('b', 'two'); get('a', 'unused'); get('c', 'three')
    assert list(cache.entries) == ['a', 'c'] and cache.evictions == 1
    assert get('a', 'unused')[0] == 'one'
    get('b', 'rebuilt')
    assert calls == ['a', 'b', 'c', 'b']
    before = list(cache.entries)
    assert get('huge', 'x'*5000)[1]['cache_admitted'] is False
    assert list(cache.entries) == before and cache.bytes <= cache.max_bytes
    size = rc.footprint(('a', 'x'*100))
    bounded = rc.ProcessCache(max_bytes=size+20, max_entries=100)
    for key in ('a', 'b', 'c'):
        bounded.get_or_build(key, lambda: 'x'*100, kind='test')
    assert len(bounded.entries) == 1 and bounded.bytes <= bounded.max_bytes
    cache.clear(); assert not cache.entries and cache.bytes == 0


def test_failed_owner_wakes_waiter_and_never_caches_failure():
    cache = rc.ProcessCache(); started = threading.Event(); release = threading.Event()
    waiter = threading.Event()
    def fail():
        started.set(); assert release.wait(5); raise RuntimeError('build failed')
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(cache.get_or_build, 'k', fail, kind='test')
        assert started.wait(5)
        waiting = pool.submit(cache.get_or_build, 'k', lambda: 'recovered', kind='test',
                              remaining=waiter.set)
        assert waiter.wait(5); release.set()
        with pytest.raises(RuntimeError, match='build failed'): owner.result(5)
        assert waiting.result(5)[0] == 'recovered'
    assert not cache.pending
    assert cache.get_or_build('k', lambda: pytest.fail('warm entry rebuilt'), kind='test')[0] == 'recovered'


def test_waiter_deadline_does_not_cancel_owner():
    cache = rc.ProcessCache(); started = threading.Event(); release = threading.Event()
    class Deadline(Exception): pass
    checks = [0]
    def remaining():
        checks[0] += 1
        if checks[0] > 1: raise Deadline()
    def build():
        started.set(); assert release.wait(5); return 'ready'
    with ThreadPoolExecutor(max_workers=1) as pool:
        owner = pool.submit(cache.get_or_build, 'k', build, kind='test')
        assert started.wait(5)
        try:
            with pytest.raises(Deadline): cache.get_or_build('k', lambda: None, kind='test', remaining=remaining)
            assert 'k' in cache.pending
        finally: release.set()
        assert owner.result(5)[0] == 'ready'


def test_cache_metrics_are_in_live_allowlist_and_summary():
    from semantic_runtime.request_report import _LIVE_FIELD_NAMES
    from pathlib import Path
    import importlib.util
    path=Path(__file__).resolve().parents[2]/'06_TOOLS/OFFLINE/genos_query_latency_summary.py'
    spec=importlib.util.spec_from_file_location('cache_summary',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    fields={'cache_scope','cache_bytes','cache_entries','cache_hit','cache_wait_ms','cache_evictions','cache_admitted'}
    assert fields <= _LIVE_FIELD_NAMES and fields <= module.FIELDS
    rows=[json.dumps({'event':'step.finished','step':'runtime_cache.matches',
          'diagnostic_revision':module.REVISION,'cache_hit':hit,'cache_bytes':123,'cache_evictions':2})
          for hit in (False,True)]
    result=module.summarize(rows)
    assert result['process_cache_hits']==1 and result['process_cache_builds']==1
    assert result['process_cache_evictions']==2 and result['process_cache_peak_observed_bytes']==123
