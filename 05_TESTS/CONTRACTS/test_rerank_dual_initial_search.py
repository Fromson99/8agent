"""Two more initial-search variants on top of the hybrid search.

hybrid_rerank: the fused list, then one model call orders its top candidates (IDs only); the chosen
articles go first in the first menu and the saved choice is reused on every redraw.
dual: the vector list and the body-search list are not combined; each keeps its own order, the first
menu shows them side by side in blocks of five and every row says which search found it.
"""
import types
import pytest
from semantic_runtime import vector_navigation as vn
from semantic_runtime.initial_vector import VectorError
from semantic_runtime.legal_agent import query_scope as qs
from semantic_runtime.legal_agent.errors import TransportError
import test_hybrid_initial_search as thb
from test_hybrid_initial_search import SOURCES, fake


def ids(rows):
    return [r['source_id'] for r in rows]


def investigation(catalogue, reply=None, selected=None):
    calls, saved, events = [], [], []

    def invoke(system, payload, schema, phase, timeout):
        calls.append({'payload': payload, 'schema': schema, 'phase': phase})
        if isinstance(reply, Exception):
            raise reply
        return reply(payload) if callable(reply) else reply

    blocks = {('d1', 'b1'): '의무인수 조문의 첫 줄', ('d1', 'b2'): '둘째 줄'}
    store = types.SimpleNamespace(sources=lambda did, wanted: [{'block_id': b, 'text': blocks[(did, b)]} for b in wanted if (did, b) in blocks])
    s = types.SimpleNamespace(tools=types.SimpleNamespace(sources=thb.SOURCES), scope=['d1', 'd2'], store=store,
                              repo=types.SimpleNamespace(event=lambda k, p: events.append((k, p))))
    inv = types.SimpleNamespace(p={'catalogue': catalogue, 'window': 'search', 'selected': selected or {}}, s=s,
                                question='의무인수가 면제되는 경우는?', invoke=invoke, left=lambda: 500,
                                save=lambda: saved.append(True))
    return inv, calls, saved, events


def menu(inv):
    data = {}
    offered = []
    def offer(kind, identity, label):
        offered.append(identity['source_id']); return 'R' + str(len(offered))
    vn.attach(inv, data, offer)
    return data['initial_vector_candidates']


def menu_catalogue(monkeypatch, mode, vector, lexical):
    s, index, events = fake(monkeypatch, mode, vector, lexical)
    _, discovery = vn.discover(s, ['q'], ['의무인수', '면제'], 'x')
    # The fake sources carry no hash-relevant change between discover and attach.
    return discovery['law_navigation'], events


def test_dual_keeps_both_lists_unmerged(monkeypatch):
    vector = [(f's{i}', 'd1') for i in range(1, 13)]
    lexical = ['s55', 's7', 's56', 's1']
    catalogue, events = menu_catalogue(monkeypatch, 'dual', vector, lexical)
    assert ids(catalogue['vector_candidates']) == [f's{i}' for i in range(1, 13)]        # pure vector order
    assert ids(catalogue['fulltext_candidates']) == lexical                              # pure body-search order
    assert [r['rank'] for r in catalogue['fulltext_candidates']] == [1, 2, 3, 4]
    assert catalogue['fulltext_candidates'][1]['vector_rank'] == 7 and catalogue['fulltext_candidates'][0]['vector_rank'] is None
    assert catalogue['dual'] == {'method': 'separate-v1', 'block': 5, 'terms': ['의무인수', '면제'], 'vector': 12, 'fulltext': 4, 'both': 2}
    assert 'fusion' not in catalogue
    assert {d['document_id'] for d in catalogue['law_page']['items']} == {'d1', 'd2'}
    assert any(k == 'INITIAL_VECTOR_CANDIDATES' and p.get('dual') for k, p in events)


def test_dual_menu_shows_blocks_of_each_list_with_labels(monkeypatch):
    vector = [(f's{i}', 'd1') for i in range(1, 13)]
    catalogue, _ = menu_catalogue(monkeypatch, 'dual', vector, ['s55', 's7', 's56', 's1'])
    monkeypatch.setattr(qs, 'documents', lambda s: ['d1', 'd2'])
    inv, calls, _, _ = investigation(catalogue)
    rows = menu(inv)
    order = [r['article'] for r in rows]
    # vector 1-5, then body search 1-4 (s1 already shown), then vector 6-10 (s7 already shown), then 11-12
    assert order[:8] == ['제1조', '제2조', '제3조', '제4조', '제5조', '제55조', '제7조', '제56조']
    labels = {r['article']: r['found_by'] for r in rows}
    assert labels['제1조'] == '벡터 1위 · 본문 검색 4위' and labels['제55조'] == '본문 검색 1위' and labels['제2조'] == '벡터 2위'
    assert labels['제7조'] == '벡터 7위 · 본문 검색 2위'
    assert [r['retrieval_order'] for r in rows] == list(range(1, len(rows) + 1)) and len(rows) == 14
    assert calls == []                                                                   # no model call


def test_dual_top_candidates_take_the_top_of_each_list(monkeypatch):
    vector = [(f's{i}', 'd1') for i in range(1, 13)]
    catalogue, _ = menu_catalogue(monkeypatch, 'dual', vector, ['s55', 's7', 's56', 's1'])
    inv, _, _, _ = investigation(catalogue)
    assert ids(vn.top_candidates(inv, 2)) == ['s1', 's55', 's2', 's7']


def test_dual_rejects_a_body_search_row_outside_the_request_scope(monkeypatch):
    s, _, _ = fake(monkeypatch, 'dual', [('s1', 'd1')], ['out'])
    monkeypatch.setattr(qs, 'search_sources', lambda s: frozenset(SOURCES))
    with pytest.raises(VectorError, match='VECTOR_COORDINATE'):
        vn.discover(s, ['q'], ['q'], 'x')


def rerank_catalogue(monkeypatch):
    monkeypatch.setattr(thb, 'SOURCES', {**SOURCES, 's3': {**SOURCES['s3'], 'blocks': [{'block_id': 'b1'}, {'block_id': 'b2'}]}})
    vector = [(f's{i}', 'd1') for i in range(1, 21)]
    catalogue, _ = menu_catalogue(monkeypatch, 'hybrid_rerank', vector, ['s15', 's3'])
    monkeypatch.setattr(qs, 'documents', lambda s: ['d1', 'd2'])
    return catalogue


def test_rerank_puts_the_chosen_candidates_first_once(monkeypatch):
    catalogue = rerank_catalogue(monkeypatch)
    fused = ids(catalogue['vector_candidates'])
    assert catalogue['fusion']['rerank'] == {'method': 'llm-rerank-v1', 'pool': 30, 'chosen_max': 10}
    handle = {sid: 'C' + str(i) for i, sid in enumerate(fused, 1)}
    inv, calls, saved, events = investigation(catalogue, {'reason': '면제 요건', 'candidate_ids': [handle['s12'], handle['s3']]})
    rows = menu(inv)
    assert [r['article'] for r in rows[:2]] == ['제12조', '제3조']
    rest = [sid for sid in fused if sid not in ('s12', 's3')]
    assert [r['article'] for r in rows[2:]] == [SOURCES[sid]['heading'] for sid in rest]
    assert len(calls) == 1 and calls[0]['phase'] == 'source-law-initial-rerank'
    sent = {c['id']: c for c in calls[0]['payload']['candidates']}
    assert sent[handle['s3']]['preview'] == '의무인수 조문의 첫 줄 둘째 줄' and 'preview' not in sent[handle['s1']]
    assert calls[0]['schema']['properties']['candidate_ids']['maxItems'] == 10
    assert inv.p['initial_rerank']['status'] == 'APPLIED' and inv.p['initial_rerank']['chosen'] == ['s12', 's3'] and saved
    assert any(k == 'INITIAL_CANDIDATE_RERANK' for k, _ in events)
    # Redraw: the saved order, no second model call; the answer-time top follows it.
    assert [r['article'] for r in menu(inv)[:2]] == ['제12조', '제3조'] and len(calls) == 1
    assert ids(vn.top_candidates(inv, 2)) == ['s12', 's3']


def test_rerank_with_an_unknown_id_keeps_the_fused_order(monkeypatch):
    catalogue = rerank_catalogue(monkeypatch)
    inv, calls, _, _ = investigation(catalogue, {'reason': 'x', 'candidate_ids': ['C99']})
    rows = menu(inv)
    assert [r['article'] for r in rows] == [SOURCES[sid]['heading'] for sid in ids(catalogue['vector_candidates'])]
    assert inv.p['initial_rerank']['status'] == 'SKIPPED' and len(calls) == 1
    menu(inv)
    assert len(calls) == 1                                                               # a failed rerank is not retried


def test_rerank_pool_skips_already_read_articles_and_transport_errors_propagate(monkeypatch):
    catalogue = rerank_catalogue(monkeypatch)
    fused = ids(catalogue['vector_candidates'])
    inv, calls, _, _ = investigation(catalogue, lambda payload: {'reason': 'x', 'candidate_ids': []},
                                     selected={'a': {'source_id': fused[0]}})
    menu(inv)
    assert len(calls[0]['payload']['candidates']) == len(fused) - 1
    assert inv.p['initial_rerank']['status'] == 'APPLIED' and inv.p['initial_rerank']['chosen'] == []
    inv2, _, _, _ = investigation(rerank_catalogue(monkeypatch), TransportError('timeout'))
    with pytest.raises(TransportError):
        menu(inv2)


def test_plain_hybrid_makes_no_model_call(monkeypatch):
    vector = [(f's{i}', 'd1') for i in range(1, 6)]
    catalogue, _ = menu_catalogue(monkeypatch, 'hybrid', vector, ['s5'])
    monkeypatch.setattr(qs, 'documents', lambda s: ['d1', 'd2'])
    inv, calls, _, _ = investigation(catalogue, {'reason': 'x', 'candidate_ids': []})
    rows = menu(inv)
    assert calls == [] and 'initial_rerank' not in inv.p and 'found_by' not in rows[0]


def test_mode_accepts_the_new_values(monkeypatch):
    from semantic_runtime import initial_vector as iv
    for value in ('hybrid_rerank', 'dual'):
        monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', value); assert iv.mode() == value


def test_progress_card_names_the_separate_lists(tmp_path):
    from semantic_runtime.progress import ProgressCapture
    capture = ProgressCapture('r', tmp_path, lambda *a, **k: None)
    capture.vector_previews = []
    rows = [{'source_id': f's{i}', 'document_id': 'd1'} for i in range(3)]
    assert capture._vector_candidates({'vector_candidates': rows, 'dual': {'fulltext': 7}})[0] == '벡터 후보 3개 · 본문 검색 후보 7개 · 따로 표시'
