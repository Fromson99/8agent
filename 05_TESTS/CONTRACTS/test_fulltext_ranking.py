"""Morpheme full-text index: build binding, candidate order, ranked LEGAL_SEARCH and repeats."""
import json
import shutil
import sqlite3
from types import SimpleNamespace
from contextlib import closing

import pytest
from semantic_runtime import fulltext
from semantic_runtime.document_agent import ServingDocumentAgent
from semantic_runtime.storage import Store
from semantic_runtime.term_agent import TermAgent
from semantic_runtime.term_index import cached_serving_index
from test_work_navigation_loop import Provider, ask, generation_with


def test_rank_keeps_bm25_order_scope_and_limit_without_sqlite_temp_sort():
    db = sqlite3.connect(':memory:')
    try:
        db.execute('CREATE VIRTUAL TABLE source_fts USING fts5(source_id UNINDEXED,heading,body)')
        db.executemany('INSERT INTO source_fts VALUES(?,?,?)', [
            ('z', 'alpha', 'beta'), ('b', 'beta', 'alpha'),
            ('a', 'alpha', 'beta'), ('c', 'gamma', 'alpha beta'),
            ('d', 'other', 'other'),
        ])
        index = fulltext.FulltextIndex.__new__(fulltext.FulltextIndex)
        index.manifest = {'ranking': {'bm25_weights': {'heading': 10.0, 'body': 1.0}}}
        terms = ['alpha', 'beta']
        previous = [sid for (sid,) in db.execute(
            'SELECT source_id FROM source_fts WHERE source_fts MATCH ? '
            'ORDER BY bm25(source_fts,0,?,?),source_id',
            (fulltext.expression(terms), 10.0, 1.0))]
        assert index.rank(db, terms) == previous
        assert index.rank(db, terms, {'a', 'b', 'c'}) == [s for s in previous if s in {'a', 'b', 'c'}]
        assert index.rank(db, terms, {'a', 'b', 'c'}, 2) == [s for s in previous if s in {'a', 'b', 'c'}][:2]
        assert index.rank(db, terms, set()) == []
        plan = db.execute('EXPLAIN QUERY PLAN SELECT source_id,rank FROM source_fts '
                          'WHERE source_fts MATCH ? AND rank MATCH ? ORDER BY rank',
                          (fulltext.expression(terms), 'bm25(0,10.0,1.0)')).fetchall()
        assert not any('TEMP B-TREE' in detail for *_, detail in plan)
    finally:
        db.close()


def test_index_chunks_bound_pecab_input_without_losing_text(monkeypatch):
    text = '영업일 규정 ' * 100
    seen = []

    def tokenize(chunk):
        seen.append(chunk)
        return [SimpleNamespace(form='영업일', tag='NNG')]

    monkeypatch.setattr(fulltext.term_morph, 'tokenize', tokenize)
    assert ''.join(fulltext._index_chunks(text)) == text
    assert fulltext._search_forms(text).split() == ['영업일'] * len(seen)
    assert len(seen) > 1
    assert all(len(chunk) <= fulltext.INDEX_CHUNK_CHARS for chunk in seen)
    assert all(chunk.endswith(' ') for chunk in seen[:-1])


@pytest.fixture
def bound(tmp_path, term_glossary, monkeypatch):
    docs = [('one', '가상규정', [['영업일에 신청한다.'], ['괴리율은 공모가격과 평가가격의 차이로 산정한다.']]),
            ('two', '가상세칙', [['자금지원 절차를 정한다.']])]
    generation = generation_with(tmp_path, term_glossary, docs)
    if not (generation/'fulltext').exists():
        fulltext.build(generation/'navigation', generation/'fulltext', workers=2)
    nav = json.loads((generation/'navigation/manifest.json').read_text())
    index = fulltext.FulltextIndex(generation/'fulltext', nav)
    monkeypatch.setattr(ServingDocumentAgent, 'get_fulltext', lambda self: index)
    return generation


def test_generation_fulltext_binding_overrides_stale_code_profile(bound):
    with closing(Store(bound)) as store:
        pipeline = SimpleNamespace(store=store, contracts=SimpleNamespace(root=bound.parent))
        agent = TermAgent(pipeline, {'fulltext': {'path': 'fulltext',
                          'navigation_index_sha256': '0'*64, 'manifest_sha256': '0'*64}})
        assert agent.get_fulltext().manifest['navigation_index_sha256'] == (
            agent.get_index().manifest['index_sha256'])


def test_index_is_bound_to_its_navigation_generation_and_file(bound):
    nav = json.loads((bound/'navigation/manifest.json').read_text())
    with pytest.raises(ValueError, match='generation mismatch'):
        fulltext.FulltextIndex(bound/'fulltext', {**nav, 'index_sha256': '0'*64})
    copy = bound.parent/'tampered'
    shutil.copytree(bound/'fulltext', copy)
    with (copy/'fulltext.sqlite').open('ab') as stream:
        stream.write(b'x')
    with pytest.raises(ValueError, match='hash mismatch'):
        fulltext.FulltextIndex(copy, nav)
    binding = {'path': 'fulltext', 'manifest_sha256': '0'*64}
    with pytest.raises(ValueError, match='manifest mismatch'):
        fulltext.open_bound(bound, binding, nav)


def test_serving_navigation_cache_rechecks_changed_file(bound):
    path = bound/'navigation'
    with closing(Store(bound)) as store:
        first = cached_serving_index(path, store)
        assert cached_serving_index(path, store) is first
        with (path/'navigation.sqlite').open('ab') as stream:
            stream.write(b'changed')
        with pytest.raises(ValueError, match='generation/hash mismatch'):
            cached_serving_index(path, store)


def test_serving_fulltext_cache_reuses_hash_but_rejects_changed_file_or_pins(bound, monkeypatch):
    nav = json.loads((bound/'navigation/manifest.json').read_text())
    binding = json.loads((bound/'manifest.json').read_text())['fulltext']
    fulltext._SERVING_CACHE.clear()
    hashed = []
    original = fulltext.sha

    def counted(path):
        hashed.append(path.name)
        return original(path)

    monkeypatch.setattr(fulltext, 'sha', counted)
    first = fulltext.cached_open_bound(bound, binding, nav)
    assert fulltext.cached_open_bound(bound, binding, nav) is first
    assert hashed.count('fulltext.sqlite') == 1
    with closing(first.connect()) as a, closing(first.connect()) as b:
        assert a is not b
    with pytest.raises(ValueError, match='manifest mismatch'):
        fulltext.cached_open_bound(bound, {**binding, 'manifest_sha256': '0'*64}, nav)
    with pytest.raises(ValueError, match='generation mismatch'):
        fulltext.cached_open_bound(bound, binding, {**nav, 'index_sha256': '0'*64})
    with (bound/'fulltext/fulltext.sqlite').open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        fulltext.cached_open_bound(bound, binding, nav)


def test_serving_fulltext_cache_does_not_hide_tokenizer_drift(bound, monkeypatch):
    nav = json.loads((bound/'navigation/manifest.json').read_text())
    binding = json.loads((bound/'manifest.json').read_text())['fulltext']
    fulltext.cached_open_bound(bound, binding, nav)
    monkeypatch.setattr(fulltext, 'tokenizer_version', lambda: 'different')
    with pytest.raises(ValueError, match='tokenizer mismatch'):
        fulltext.cached_open_bound(bound, binding, nav)


def test_warmup_prepares_the_same_request_resource_caches(tmp_path, bound, monkeypatch, caplog):
    import service
    from semantic_runtime.app import create_app
    from semantic_runtime import observability as obs
    from semantic_runtime.request_report import capture_events
    from test_work_navigation_loop import ROOT

    # Cache-hit details moved to DEBUG in the response-overhead revision.
    import logging
    caplog.set_level(logging.DEBUG, logger=obs.ROOT)

    app = create_app(tmp_path/'runtime', bound, contracts_root=ROOT,
                     provider=Provider([]), implementation='document-navigation-v1')
    monkeypatch.setenv('GENOS_GENERATION', str(bound))
    monkeypatch.setattr(service, '_bootstrap_application', lambda: app)
    monkeypatch.setattr(service, '_BINDING', {'mode': 'genos-generation'})
    monkeypatch.setattr(ServingDocumentAgent, 'get_fulltext', TermAgent.get_fulltext)
    try:
        first = service._warm_resources()
        assert first['generation_path'] == str(bound)
        with capture_events('warm-again') as events, obs.context(request_id='warm-again'):
            service._warm_resources()
        assert any(row['event'] == 'fulltext.cached' for row in events)
        assert any(row['event'] == 'glossary.file.cached' for row in events)
        assert any(row['event'] == 'tools.cache.hit' for row in events)
        assert not any(row.get('step') in {'fulltext.verify', 'glossary.file.verify',
                                           'tools.catalog', 'tools.definition_catalog'} for row in events)
    finally:
        app.state.pipeline.store.close()


def test_fulltext_seeds_and_orders_candidates_without_registered_terms(tmp_path, bound):
    provider = Provider([{'tool': 'STOP', 'args': {'reason': 'x'}}])
    state = ask(tmp_path, bound, provider, question='괴리율은 어떻게 산정하는가?')['retrieval']['term_agent']
    entry = next(e for e in state['entry_paths'] if e['kind'] == 'fulltext')
    assert '괴리' in entry['query_terms'] and entry['candidate_count'] >= 1
    cards = [c for c in state['work_state']['entities'].values() if c['type'] == 'article']
    ranked = sorted((c for c in cards if c.get('fulltext_rank')), key=lambda c: c['fulltext_rank'])
    assert ranked and ranked[0]['heading'].startswith('제2조') and ranked[0]['document_name'] == '가상규정'


def test_legal_search_tokens_is_ranked_or_and_repeats_are_flagged(tmp_path, bound):
    search = {'tool': 'LEGAL_SEARCH', 'args': {'query': '괴리율 없는단어 자금지원', 'mode': 'tokens', 'document_id': '', 'offset': 0}}
    provider = Provider([search, search, {'tool': 'STOP', 'args': {'reason': 'x'}}])
    state = ask(tmp_path, bound, provider, question='영업일 절차')['retrieval']['term_agent']
    events = [e for e in state['trace'] if e['tool'] == 'LEGAL_SEARCH']
    assert len(events) == 2 and all(e['status'] == 'OK' for e in events)
    first, second = (e['result'] for e in events)
    # An AND filter over all three words would be empty; the ranked search returns both articles.
    assert first['status'] == 'MATCHES' and first['total'] == 2 and first['mode'] == 'legal_tokens'
    assert 'repeated_query' not in first and second['repeated_query'] is True


def test_rejected_relation_demotes_researches_and_is_ledgered(tmp_path, bound, monkeypatch):
    from semantic_runtime import relation_issues
    from semantic_runtime.work_navigation import WorkSession
    seed = WorkSession.seed_pool

    def with_bridge(self):
        # The fixture glossary has no MOLEG bridge; mark the question term as bridged-in.
        seed(self)
        entry = next(e for e in self.entries if e['kind'] == 'term')
        tid = entry['term_ids'][0]
        self.relations['bridge:'+tid+'>'+tid+'@140305'] = {
            'kind': 'bridge', 'everyday': {'id': tid, 'label': '보조'}, 'legal': {'id': tid, 'label': entry['labels'][0]},
            'relation_code': '140305', 'question_spans': entry['question_spans']}
    monkeypatch.setattr(WorkSession, 'seed_pool', with_bridge)
    # Rank only: with no full-text seed entry the bridged term is each candidate's only origin.
    monkeypatch.setattr(WorkSession, 'FULLTEXT_SEED', 0)

    def reject(data):
        rid = next(v for c in data['candidates']['items'] for v in c.get('via', []))
        return {'tool': 'REJECT_RELATION', 'args': {'relation_id': rid, 'reason': '다른 뜻의 단어로 연결됨', 'quote': ''}}
    provider = Provider([reject, {'tool': 'STOP', 'args': {'reason': 'x'}}])
    state = ask(tmp_path, bound, provider, question='영업일은?')['retrieval']['term_agent']
    [rejection] = state['relation_rejections']
    assert rejection['relation']['kind'] == 'bridge' and rejection['reason'] == '다른 뜻의 단어로 연결됨'
    result = next(e['result'] for e in state['trace'] if e['tool'] == 'REJECT_RELATION')
    assert result['scope'] == 'this request only' and result['demoted_candidates'] >= 1
    assert any(e['tool'] == 'LEGAL_SEARCH' and 'relation rejected' in e['reason'] for e in state['trace'])
    [row] = relation_issues.summary(tmp_path/'runtime/90_RUNTIME/semantic/relation-issues/rejections.sqlite')
    assert row['kind'] == 'bridge' and row['rejections'] == 1
