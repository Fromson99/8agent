"""Vector initial search shows a short candidate card (count + nearest articles), not body-search words."""
import json
import os
import types
from semantic_runtime import vector_navigation as vn
from semantic_runtime.initial_vector import VectorUnavailable
from test_rag_key_progress import commit, display_events, journal, native  # noqa: F401  (pytest fixtures)


def preview(n=5):
    return [{'source_id': f's{i}', 'document_id': 'allowed', 'document_name': '모의법', 'article': f'제{i}조(정의)'}
            for i in range(1, n + 1)]


def recall(rows, *, publication='pub-1'):
    return {'selected_for_read': [], 'discovery': {'law_navigation': {
        'terms': ['내부', '회계'], 'search_policy': 'vector-initial-v1', 'vector_publication': publication,
        'vector_candidates': rows}}}


def card(events):
    return [e for e in events if e.get('basis', {}).get('stage') == 'RECALL'][0]


def test_vector_recall_card_lists_count_and_nearest_articles(native):
    repo, projection, events = native
    rows = [{'source_id': f's{i}', 'document_id': 'allowed', 'rank': i} for i in range(1, 8)]
    repo.event('INITIAL_VECTOR_CANDIDATES', {'publication_id': 'pub-1', 'count': 7, 'preview': preview()})
    commit(repo, 'RECALL', recall(rows))
    projection.poll_journal()
    details = card(events)['details']
    assert details == ['벡터 후보 7개 · 가까운 순'] + [f'모의법 · 제{i}조(정의)' for i in range(1, 6)] + ['외 2개']
    assert not any('본문 검색에 사용한 단어' in d for d in details)
    display, _, _ = display_events(events)
    shown = '\n'.join(json.loads(b['data']['output']['content'])['visible_rationale'] for b in display.blocks)
    for line in details:
        assert '- ' + display._plain(line) in shown


def test_vector_card_short_list_and_scope_filter(native):
    repo, projection, events = native
    rows = [{'source_id': 's1', 'document_id': 'allowed', 'rank': 1}, {'source_id': 'x', 'document_id': 'other', 'rank': 2},
            {'source_id': 's2', 'document_id': 'allowed', 'rank': 3}]
    repo.event('INITIAL_VECTOR_CANDIDATES', {'publication_id': 'pub-1', 'count': 3, 'preview': [
        preview()[0], {'source_id': 'x', 'document_id': 'other', 'document_name': '비공개', 'article': '제9조'}, preview()[1]]})
    commit(repo, 'RECALL', recall(rows))
    projection.poll_journal()
    text = json.dumps(card(events), ensure_ascii=False)
    assert '벡터 후보 2개 · 가까운 순' in text and '비공개' not in text and '외 ' not in text


def test_vector_card_without_matching_preview_shows_count_only(native):
    repo, projection, events = native
    rows = [{'source_id': 's1', 'document_id': 'allowed', 'rank': 1}]
    repo.event('INITIAL_VECTOR_CANDIDATES', {'publication_id': 'other-publication', 'count': 1, 'preview': preview(1)})
    commit(repo, 'RECALL', recall(rows))
    projection.poll_journal()
    assert card(events)['details'] == ['벡터 후보 1개 · 가까운 순']


def test_body_search_recall_keeps_search_words(native):
    repo, projection, events = native
    commit(repo, 'RECALL', {'selected_for_read': [], 'discovery': {'law_navigation': {'terms': ['승인', '조건']}}})
    projection.poll_journal()
    assert card(events)['details'] == ['본문 검색에 사용한 단어: 승인 / 조건']


def fake_session(rows):
    from semantic_runtime.legal_agent import query_scope as qs
    sources = {f's{i}': {'document_id': 'd1', 'unit_id': f'u{i}', 'document_name': '상법', 'heading': f'제{i}조'} for i in range(1, 8)}
    events = []

    class Retriever:
        def search(self, question, documents, source_ids=None):
            return {'publication_id': 'pub', 'revision': 1, 'truncated': False, 'embedding_calls': 1,
                    'rows': [{'SOURCE_ID': sid, 'DOC_ID': 'd1', 'DISTANCE': 0.1 * n} for n, sid in enumerate(rows)]}
    session = types.SimpleNamespace(matcher=types.SimpleNamespace(initial_vector=Retriever()), law_search_queries=None,
        context=types.SimpleNamespace(request={'question': '내부 회계 관리자 지정'}), scope=['d1'],
        tools=types.SimpleNamespace(sources=sources), repo=types.SimpleNamespace(event=lambda k, p: events.append((k, p))))
    return session, events, qs


def test_discover_event_carries_five_preview_names_and_catalogue_is_unchanged(monkeypatch):
    from semantic_runtime.legal_agent import law_candidates as lc
    session, events, qs = fake_session([f's{i}' for i in range(1, 8)])
    monkeypatch.setattr(qs, 'fulltext', lambda s: {}); monkeypatch.setattr(qs, 'documents', lambda s: {'d1'})
    monkeypatch.setattr(qs, 'active', lambda s: None)
    monkeypatch.setattr(lc, 'index', lambda s: (types.SimpleNamespace(manifest={'index_sha256': 'i'}), None))
    monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', 'vector')
    _, discovery = vn.discover(session, ['내부 회계 관리자 지정'], ['내부', '회계'], 'accepted_request_queries')
    kind, payload = events[-1]
    assert kind == 'INITIAL_VECTOR_CANDIDATES' and payload['count'] == 7
    assert payload['preview'] == [{'source_id': f's{i}', 'document_id': 'd1', 'document_name': '상법', 'article': f'제{i}조'} for i in range(1, 6)]
    rows = discovery['law_navigation']['vector_candidates']
    assert len(rows) == 7 and set(rows[0]) == {'source_id', 'document_id', 'unit_id', 'source_sha256', 'rank', 'distance'}


def test_missing_head_still_follows_mode(monkeypatch):
    session, events, qs = fake_session([])
    def missing(*a, **k): raise VectorUnavailable('VECTOR_NOT_PUBLISHED: selected Oracle query has no vector head')
    session.matcher.initial_vector.search = missing
    monkeypatch.setattr(qs, 'fulltext', lambda s: {}); monkeypatch.setattr(qs, 'documents', lambda s: {'d1'})
    monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', 'auto')
    assert vn.discover(session, ['q'], ['q'], 'x') is None and events[-1][0] == 'INITIAL_VECTOR_DEGRADED'
