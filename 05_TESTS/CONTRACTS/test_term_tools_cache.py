"""Serving catalog reuse without sharing request state or widening scope."""
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from types import SimpleNamespace

import pytest
from semantic_runtime import term_index as module
from semantic_runtime.contracts import sha, digest


@pytest.fixture
def index(tmp_path):
    path = tmp_path / 'navigation'
    path.mkdir()
    with sqlite3.connect(path / 'navigation.sqlite') as db:
        db.executescript("""
        CREATE TABLE term(json TEXT);
        CREATE TABLE edge(json TEXT);
        CREATE TABLE term_stats(term_id TEXT,n INTEGER);
        CREATE TABLE source(id TEXT,document_id TEXT,json TEXT);
        CREATE TABLE definition(id TEXT,document_id TEXT,json TEXT);
        CREATE TABLE term_surface(term_id TEXT,key TEXT,text TEXT);
        """)
        db.execute('INSERT INTO term VALUES (?)', (json.dumps({'id': 't1', 'label': '영업일'}),))
        db.execute('INSERT INTO term_stats VALUES (?,?)', ('t1', 2))
        for did in ('a', 'b'):
            db.execute('INSERT INTO source VALUES (?,?,?)', (did, did, json.dumps({'id': did, 'text': '영업일'})))
            definition = {'id': did, 'document_id': did, 'term_ids': ['t1'], 'key': '영업일'}
            db.execute('INSERT INTO definition VALUES (?,?,?)', (did, did, json.dumps(definition)))
        db.executemany('INSERT INTO term_surface VALUES (?,?,?)', [('t1', '업무일', '업무일')] * 2)
    store = SimpleNamespace(manifest={'store_sha256': 'fixture-store', 'generation_id': 'fixture'})
    manifest = {'schema_version': 'term-navigation-index-v4',
                'source_store_sha256': store.manifest['store_sha256'],
                'source_manifest_sha256': digest(store.manifest),
                'index_sha256': sha(path / 'navigation.sqlite')}
    (path / 'manifest.json').write_text(json.dumps(manifest))
    return module.cached_serving_index(path, store)


def test_next_question_uses_catalog_without_sql_scans_and_isolates_state(index, monkeypatch):
    original_ro = module.ro
    first = index.tools(['a'])
    # Compare cached tools with the old uncached construction contract.
    with closing(original_ro(index.path/'navigation.sqlite')) as db:
        uncached = module.IndexTools(db, index.terms, index.relations, ['a'])
        for name in ('terms', 'labels', 'prefix', 'edges', 'df', 'document_ids', 'definitions'):
            assert getattr(first, name) == getattr(uncached, name)
    first.labels['업무일'].append('poison')
    first.terms['t1']['label'] = 'changed'
    first.definitions['a']['term_ids'].append('poison')
    first.references['private'] = {'request': 'one'}
    first.sources.cache['private'] = {}
    first.db.close()
    scans = []
    def counted_ro(path):
        db = original_ro(path)
        db.set_trace_callback(scans.append)
        return db
    monkeypatch.setattr(module, 'ro', counted_ro)
    second = index.tools(['b'])
    third = index.tools(['a'])
    try:
        assert scans == []  # No catalogue / scope definition SQL on a warm request.
        assert second.db is not third.db
        assert second.match('업무일') == ['t1']
        assert second.terms['t1']['label'] == '영업일'
        assert set(second.definitions) == {'b'}
        assert third.definitions['a']['term_ids'] == ['t1']
        assert not second.references and not second.sources.cache
        with pytest.raises(ValueError, match='scope'):
            second.validate_scope(['a'])
    finally:
        second.db.close()
        third.db.close()


def test_concurrent_first_questions_only_load_catalog_once(index, monkeypatch):
    calls = []
    original = module.IndexTools._load_catalog
    def counted(self, db):
        calls.append(1)
        return original(self, db)
    monkeypatch.setattr(module.IndexTools, '_load_catalog', counted)
    def prepare(did):
        tools = index.tools([did])
        try:
            return tools.match('업무일'), set(tools.definitions)
        finally:
            tools.db.close()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(prepare, ['a', 'b', 'a']))
    assert len(calls) == 1
    assert results == [(['t1'], {'a'}), (['t1'], {'b'}), (['t1'], {'a'})]


def test_failed_catalog_load_does_not_publish_partial_cache(index, monkeypatch):
    original = module.IndexTools._load_catalog
    def fail(self, db):
        raise RuntimeError('fixture I/O failure')
    monkeypatch.setattr(module.IndexTools, '_load_catalog', fail)
    with pytest.raises(RuntimeError):
        index.tools(['a'])
    assert index._tool_catalog is None
    monkeypatch.setattr(module.IndexTools, '_load_catalog', original)
    tools = index.tools(['a'])
    assert tools.match('업무일') == ['t1']
    tools.db.close()


def test_label_search_restores_request_sql_deadline(index):
    tools = index.tools(['a'])
    try:
        tools.request_deadline = time.monotonic() + 0.02
        tools.search_labels(['영업일'], ['a'])
        time.sleep(0.03)
        with pytest.raises(sqlite3.OperationalError, match='interrupted'):
            tools.db.execute('''WITH RECURSIVE n(x) AS (
                SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<1000000)
                SELECT sum(x) FROM n''').fetchone()
    finally:
        tools.db.close()
