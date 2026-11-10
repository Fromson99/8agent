"""Hybrid initial search: vector rows and body-search (BM25) articles merged by reciprocal rank (k=60).

A lexical-only article enters the first menu, an article both searches rank goes first, the request
scope still binds every row, and the vector/keyword modes keep their previous behaviour.
"""
import types
import pytest
from semantic_runtime import vector_navigation as vn
from semantic_runtime.initial_vector import VectorError
from semantic_runtime.legal_agent import law_candidates as lc, query_scope as qs
from test_vector_scope_respect import Retriever

SOURCES = {f's{i}': {'document_id': 'd1' if i < 50 else 'd2', 'unit_id': f'u{i}', 'document_name': '법', 'heading': f'제{i}조'} for i in range(1, 60)}
SOURCES['out'] = {'document_id': 'other', 'unit_id': 'u0', 'document_name': '다른 법', 'heading': '제1조'}


class Index:
    manifest = {'index_sha256': 'i'}

    def __init__(self, order):
        self.order = order; self.calls = []

    def rank_page(self, db, terms, allowed, *, cursor=None, limit=16, unit_keys=None):
        self.calls.append({'terms': list(terms), 'limit': limit})
        start = cursor or 0
        items = [{'source_id': sid, 'key': f'{sid}:k'} for sid in self.order[start:start + limit]]
        nxt = start + len(items)
        return {'items': items, 'total': len(self.order), 'next_cursor': nxt if nxt < len(self.order) else None}


def fake(monkeypatch, mode, vector_rows, lexical, scope=('d1', 'd2')):
    monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', mode)
    index = Index(lexical)
    monkeypatch.setattr(lc, 'index', lambda s: (index, None))
    monkeypatch.setattr(qs, 'search_sources', lambda s: frozenset(k for k, v in SOURCES.items() if v['document_id'] in scope))
    events = []
    s = types.SimpleNamespace(matcher=types.SimpleNamespace(initial_vector=Retriever(vector_rows)), law_search_queries=None,
        context=types.SimpleNamespace(request={'question': '의무인수가 면제되는 경우는?'}), scope=list(scope),
        tools=types.SimpleNamespace(sources=SOURCES), repo=types.SimpleNamespace(event=lambda k, p: events.append((k, p))))
    return s, index, events


def ranks(discovery):
    return [r['source_id'] for r in discovery['law_navigation']['vector_candidates']]


def test_lexical_only_article_enters_the_menu_and_shared_hits_go_first(monkeypatch):
    vector = [(f's{i}', 'd1') for i in range(1, 21)]          # s1..s20 by distance
    lexical = ['s55', 's15', 's3']                             # s55 is never a vector neighbour
    s, index, events = fake(monkeypatch, 'hybrid', vector, lexical)
    _, discovery = vn.discover(s, ['의무인수 면제'], ['의무인수', '면제'], 'accepted_request_queries')
    order = ranks(discovery)
    assert order[:2] == ['s3', 's15']                          # both searches rank them
    assert 's55' in order[:5]                                  # lexical rank 1 beats vector-only rank >= 4
    row = next(r for r in discovery['law_navigation']['vector_candidates'] if r['source_id'] == 's55')
    assert row['vector_rank'] is None and row['lexical_rank'] == 1 and row['distance'] is None and row['document_id'] == 'd2'
    assert [r['rank'] for r in discovery['law_navigation']['vector_candidates']] == list(range(1, len(order) + 1))
    fusion = discovery['law_navigation']['fusion']
    assert fusion['method'] == 'rrf-v1' and fusion['both'] == 2 and fusion['lexical_only_kept'] == 1
    # The model terms come first; since 2026-11-09 the question's own content words follow them
    # (ADR-1477 r3: "상장주선인", "사내규정" never reached the body search).
    assert index.calls[0]['terms'][:2] == ['의무인수', '면제']
    assert {d['document_id'] for d in discovery['law_navigation']['law_page']['items']} == {'d1', 'd2'}
    assert any(k == 'INITIAL_VECTOR_CANDIDATES' and p.get('fusion') for k, p in events)


def test_fused_list_is_capped_and_lexical_pages_are_followed(monkeypatch):
    vector = [(f's{i}', 'd1') for i in range(1, 50)]
    lexical = [f's{i}' for i in range(50, 60)] + [f's{i}' for i in range(1, 49)]
    s, index, _ = fake(monkeypatch, 'hybrid', vector, lexical)
    monkeypatch.setattr(vn, 'FUSION_LIMIT', 30)
    monkeypatch.setattr(vn, 'LEXICAL_UNITS', 200)
    _, discovery = vn.discover(s, ['q'], ['q'], 'x')
    assert len(ranks(discovery)) == 30 and len(set(ranks(discovery))) == 30


def test_lexical_candidate_outside_the_request_scope_is_rejected(monkeypatch):
    s, _, _ = fake(monkeypatch, 'hybrid', [('s1', 'd1')], ['out'])
    monkeypatch.setattr(qs, 'search_sources', lambda s: frozenset(SOURCES))   # a broken index widening the scope
    with pytest.raises(VectorError, match='VECTOR_COORDINATE'):
        vn.discover(s, ['q'], ['q'], 'x')


def test_vector_mode_keeps_the_pure_vector_order(monkeypatch):
    vector = [(f's{i}', 'd1') for i in range(1, 6)]
    s, index, _ = fake(monkeypatch, 'vector', vector, ['s5', 's55'])
    _, discovery = vn.discover(s, ['q'], ['q'], 'x')
    assert ranks(discovery) == ['s1', 's2', 's3', 's4', 's5'] and index.calls == []
    assert 'fusion' not in discovery['law_navigation']


def test_hybrid_without_terms_is_the_vector_order(monkeypatch):
    s, index, _ = fake(monkeypatch, 'hybrid', [('s1', 'd1'), ('s2', 'd1')], ['s2'])
    _, discovery = vn.discover(s, [], [], 'x')
    assert ranks(discovery) == ['s1', 's2'] and index.calls == []


def test_mode_accepts_hybrid_and_rejects_unknown(monkeypatch):
    from semantic_runtime import initial_vector as iv
    monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', 'hybrid'); assert iv.mode() == 'hybrid'
    monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', 'bm25')
    with pytest.raises(VectorError, match='VECTOR_CONFIG'):
        iv.mode()


def test_progress_card_names_the_merged_list(tmp_path):
    from semantic_runtime.progress import ProgressCapture
    capture = ProgressCapture('r', tmp_path, lambda *a, **k: None)
    capture.vector_previews = []
    rows = [{'source_id': f's{i}', 'document_id': 'd1'} for i in range(3)]
    assert capture._vector_candidates({'vector_candidates': rows, 'fusion': {'method': 'rrf-v1'}})[0] == '벡터·본문 검색 후보 3개 · 합친 순'
    assert capture._vector_candidates({'vector_candidates': rows})[0] == '벡터 후보 3개 · 가까운 순'
