"""Vector initial search keeps every user restriction: document scope, unit scope, structure entry.

Vector search ranks whole documents only. A named document narrows it, a chapter/
article/paragraph scope or an explicit structure request skips it, and coordinates
in the accepted search words (e.g. 제365조) are still read first.
"""
import types
import pytest
from test_unit_fulltext_adaptive_read import tree, session  # noqa: F401  (pytest fixtures)
from semantic_runtime import vector_navigation as vn
from semantic_runtime import initial_vector as iv
from semantic_runtime.initial_vector import VectorError
from semantic_runtime.legal_agent import law_candidates as lc, query_scope as qs, structure_query
from semantic_runtime.legal_agent.source_recall import SourceRecall


class Retriever:
    """Records the scope the vector search received; returns the given sources."""
    def __init__(self, rows):
        self.rows = rows; self.calls = []

    def search(self, question, documents, source_ids=None):
        self.calls.append({'question': question, 'documents': sorted(documents)})
        return {'publication_id': 'pub', 'revision': 1, 'truncated': False, 'embedding_calls': 1,
                'rows': [{'SOURCE_ID': sid, 'DOC_ID': did, 'DISTANCE': 0.1 * (n + 1)} for n, (sid, did) in enumerate(self.rows)]}


def fake(scope, *, direct=None, law_search_queries=None, rows=()):
    sources = {'s1': {'document_id': '상법', 'unit_id': 'u1', 'document_name': '상법', 'heading': '제365조'},
               's2': {'document_id': '민법', 'unit_id': 'u2', 'document_name': '민법', 'heading': '제1조'}}
    events = []
    s = types.SimpleNamespace(matcher=types.SimpleNamespace(initial_vector=Retriever(rows)), law_search_queries=law_search_queries,
        context=types.SimpleNamespace(request={'question': '정기총회 소집 시기'}), scope=scope,
        tools=types.SimpleNamespace(sources=sources), repo=types.SimpleNamespace(event=lambda k, p: events.append((k, p))))
    if direct is not None:
        s.direct_search_scope = {'targets': direct, 'hash': 'scope-hash'}
    return s, events


@pytest.fixture
def vector_mode(monkeypatch):
    monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', 'vector')
    monkeypatch.setattr(lc, 'index', lambda s: (types.SimpleNamespace(manifest={'index_sha256': 'i'}), None))


def test_named_document_scope_narrows_the_vector_search(vector_mode):
    s, events = fake(['상법', '민법'], direct=[{'document_id': '상법', 'unit_id': None}], rows=[('s1', '상법')])
    _, discovery = vn.discover(s, ['정기총회 소집'], ['정기총회'], 'accepted_request_queries')
    assert s.matcher.initial_vector.calls == [{'question': '정기총회 소집 시기', 'documents': ['상법']}]
    assert [r['document_id'] for r in discovery['law_navigation']['vector_candidates']] == ['상법']


def test_vector_row_outside_named_document_is_rejected(vector_mode):
    s, _ = fake(['상법', '민법'], direct=[{'document_id': '상법', 'unit_id': None}], rows=[('s2', '민법')])
    with pytest.raises(VectorError, match='VECTOR_COORDINATE'):
        vn.discover(s, ['정기총회 소집'], ['정기총회'], 'accepted_request_queries')


def test_article_or_paragraph_scope_skips_vector(vector_mode, monkeypatch):
    s, events = fake(['상법', '민법'], direct=[{'document_id': '상법', 'unit_id': 'u1'}], rows=[('s1', '상법')])
    monkeypatch.setattr(lc, 'fulltext_scope_keys', lambda session, did, uid: frozenset({did + ':' + uid}))
    assert qs.fulltext(s) == {'unit_keys': frozenset({'상법:u1'})}
    assert vn.discover(s, ['정기총회 소집'], ['정기총회'], 'accepted_request_queries') is None
    assert s.matcher.initial_vector.calls == [] and events == []


def test_research_with_selected_queries_skips_vector(vector_mode):
    s, events = fake(['상법'], law_search_queries=['소집 통지'], rows=[('s1', '상법')])
    assert vn.discover(s, ['소집 통지'], ['소집'], 'selected_search_queries') is None
    assert s.matcher.initial_vector.calls == []


def test_keyword_mode_never_calls_vector(monkeypatch):
    monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', 'keyword')
    s, _ = fake(['상법'], rows=[('s1', '상법')])
    assert vn.discover(s, ['q'], ['q'], 'x') is None and s.matcher.initial_vector.calls == []


def test_vector_cannot_widen_the_authorized_scope():
    sql = types.SimpleNamespace(deadline=None)
    request = types.SimpleNamespace(sql=sql, sources=types.SimpleNamespace(allowed={'상법'}), release_id='r')
    retriever = iv.Retriever(request)
    with pytest.raises(VectorError, match='cannot widen'):
        retriever.search('질문', {'상법', '민법'})


def test_vector_sql_filters_named_documents_and_rejects_foreign_rows():
    statements = []
    class SQL:
        rows = []
        def query(self, statement, binds, limit=None):
            statements.append(statement)
            if 'LGL_VCTR_SEG_S' in statement:return self.rows
            return [{'PUB_ID': 'p', 'QUERY_ID': 'q', 'PROFILE_JSON': {}, 'MANIFEST_JSON': {}, 'STATUS': 'READY',
                     'EXPECTED_COUNT': 1, 'ACTUAL_COUNT': 1}]
    sql = SQL()
    repo = iv.Repository(sql)
    profile = {'schema_version': 'legal-vector-profile-v1', 'model': 'm', 'revision': 'r', 'dimensions': 2,
               'endpoint_sha256': '0' * 64, 'chunk_chars': 800, 'overlap_chars': 100, 'normalization': 'l2', 'metric': 'COSINE'}
    repo.read = lambda pub: {'STATUS': 'READY', 'PROFILE_JSON': profile}
    assert repo.search('p', [1.0, 0.0], {'상법'}) == []
    assert "DOC_ID IN ('상법')" in statements[-1] and '민법' not in statements[-1]
    sql.rows = [{'DOC_ID': '민법', 'SOURCE_ID': 's2', 'DISTANCE': 0.1}]
    with pytest.raises(VectorError, match='VECTOR_SCOPE'):
        repo.search('p', [1.0, 0.0], {'상법'})


def vector_session(session, monkeypatch, **policy):
    native, _ = session; s = native.sources
    s.profile['candidate_navigation'] = {**lc.DEFAULT_POLICY, 'mode': 'law-first-v1', **policy}
    sid = next(k for k, v in s.tools.sources.items() if v['document_id'] == 'd')
    s.matcher.initial_vector = Retriever([(sid, 'd')])
    monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', 'vector')
    return s, sid


def match_unit(monkeypatch, sid, uid='4'):
    monkeypatch.setattr(structure_query, 'resolve', lambda *args, **kwargs: {'status': 'MATCH', 'source_ids': [sid],
        'pairs': [{'document_id': 'd', 'unit_id': uid, 'coordinate': '제1조제1항제2호'}], 'reason': 'EXACT_DOCUMENT_COORDINATE'})


def test_structure_request_never_reaches_vector(session, monkeypatch):
    s, sid = vector_session(session, monkeypatch, structure_first=True, selectable_search=True)
    s.entry_search = {'mode': 'STRUCTURE'}
    match_unit(monkeypatch, sid)
    _, receipt = SourceRecall(s).discover()
    assert s.matcher.initial_vector.calls == []
    assert receipt['law_navigation'].get('search_policy') != 'vector-initial-v1'


def test_coordinate_in_search_words_is_kept_in_vector_mode(session, monkeypatch):
    s, sid = vector_session(session, monkeypatch)
    match_unit(monkeypatch, sid)
    selected, receipt = SourceRecall(s).discover()
    assert len(s.matcher.initial_vector.calls) == 1
    assert receipt['law_navigation']['search_policy'] == 'vector-initial-v1'
    assert receipt['law_navigation']['vector_candidates'][0]['source_id'] == sid
    assert receipt['structure_query']['status'] == 'MATCH'
    assert selected == [sid] and receipt['selected_for_read'] == [sid]
    assert [(h['unit_id'], h['entry_reason']) for h in receipt['unit_hits']] == [('4', 'exact_structure')]


def test_named_coordinate_is_read_before_the_vector_menu(session, monkeypatch):
    s, sid = vector_session(session, monkeypatch)
    match_unit(monkeypatch, sid)
    record = SourceRecall(s).prepare()
    assert record['unit_reads'] and record['unit_reads'][0]['source_id'] == sid
    assert record['selected_for_read'] == [sid]


def test_vector_result_without_coordinate_is_unchanged(session, monkeypatch):
    s, sid = vector_session(session, monkeypatch)
    monkeypatch.setattr(structure_query, 'resolve', lambda *args, **kwargs: {'status': 'NO_MATCH', 'source_ids': [], 'pairs': []})
    seen = {}
    original = vn.discover
    def capture(*args):
        seen['result'] = original(*args); return seen['result']
    monkeypatch.setattr(vn, 'discover', capture)
    assert SourceRecall(s).discover() is seen['result']
    assert seen['result'][1]['unit_hits'] == [] and seen['result'][1]['structure_query']['status'] == 'NO_MATCH'
