"""A reply with no answer says what was searched and what the searches caught (user 2026-11-11).

"못 찾으면 가령 우리 이런걸로 검색을 했고 이런거 확인했는데 없더라" / "갯수는 의미없어 빼버려. 어떤 내용들이
잡혔는지 상위 2개씩 보여줘, 본문에서 근처 내용 잡힌 것들."
"""
import re
import types

import pytest

from semantic_runtime import vector_navigation as vn
from semantic_runtime.legal_agent import completion_contracts as cc, guided_answer as g, law_candidates as lc
from semantic_runtime.legal_agent import query_scope as qs, search_record as sr
from semantic_runtime.legal_agent.errors import ProposalError
from semantic_runtime.oracle_dp_io import DPError
from test_guided_answer import ISSUES, SOURCES, execution, value
from test_hybrid_initial_search import fake
from test_progress_report import REPORT, Reporting, shown  # noqa: F401
from test_multiturn_structured_scope import tree  # noqa: F401  (pytest fixture)

BODY = '가' * 300 + ' 공매 대상 사업장의 선정 기준은 위원회가 정한다. ' + '나' * 300


class Index:
    def __init__(self, texts): self.texts = texts; self.calls = []

    def hit_page(self, db, terms, sid, allowed, *, limit):
        self.calls.append((sid, list(terms), limit))
        if isinstance(self.texts, Exception): raise self.texts
        return {'items': [{'text': self.texts[sid]}] if sid in self.texts else []}


def session(monkeypatch, texts, record, blocks=()):
    index = Index(texts)
    monkeypatch.setattr(lc, 'index', lambda s: (index, None))
    monkeypatch.setattr(qs, 'search_sources', lambda s: frozenset())
    sources = {'a': {'document_id': 'd', 'document_name': '1. 준칙 > 신용거래관리준칙', 'heading': '제4조 종목 선정', 'blocks': [{'block_id': n} for n in range(len(blocks))]},
               'b': {'document_id': 'd', 'document_name': '주관업무준칙', 'heading': '제18조'}}
    return types.SimpleNamespace(search_record=record, tools=types.SimpleNamespace(sources=sources),
        store=types.SimpleNamespace(source=lambda d, b: {'text': blocks[b]})), index


def test_words_keep_each_search_word_once_without_exact_marks():
    assert sr.words(['공매 대상 "1,000억원"', '공매', '기준']) == ['공매', '대상', '1,000억원', '기준']


def test_excerpt_is_the_window_holding_the_search_words():
    text = sr.excerpt(BODY, ['공매', '사업장', '기준'])
    assert '공매 대상 사업장의 선정 기준은' in text and text.startswith('…') and text.endswith('…')
    assert len(text) <= sr.EXCERPT_CHARS + 2


def test_excerpt_of_a_text_without_search_words_starts_at_the_beginning():
    assert sr.excerpt(' 가 \n' + '나' * 300, ['공매']).startswith('가 나')


def test_hybrid_search_remembers_the_top_two_of_each_search(monkeypatch):
    s, _, _ = fake(monkeypatch, 'hybrid', [(f's{i}', 'd1') for i in range(1, 9)], ['s55', 's15', 's3'])
    vn.discover(s, ['의무인수 면제'], ['의무인수 면제'], 'accepted_request_queries')
    assert s.search_record['vector'] == ['s1', 's2'] and s.search_record['lexical'] == ['s55', 's15']
    assert s.search_record['terms'][0] == '의무인수 면제'


def test_report_lists_candidates_with_the_text_around_the_hit_and_no_counts(monkeypatch):
    s, index = session(monkeypatch, {'a': BODY, 'b': BODY}, {'terms': ['공매 사업장'], 'vector': ['a'], 'lexical': ['b']})
    text = sr.report(s)
    assert text.startswith(sr.HEAD) and '- 의미 검색(벡터): 질문 문장 전체' in text and '- 낱말 검색(본문): 공매, 사업장' in text
    assert '  - 신용거래관리준칙 제4조 종목 선정: “…' in text and '  - 주관업무준칙 제18조: “…' in text and '공매 대상 사업장의' in text
    assert not re.search(r'\d+\s*개', text)
    assert sr.report(s) == text and len(index.calls) == 2  # candidate lines are built once per request


def test_a_vector_candidate_without_a_word_hit_shows_its_first_body_block(monkeypatch):
    s, _ = session(monkeypatch, {}, {'terms': ['공매'], 'vector': ['a'], 'lexical': []}, blocks=['제4조', '신용거래 종목은 위험관리위원회가 선정한다.'])
    assert '신용거래 종목은 위험관리위원회가' in sr.report(s)


def test_a_failed_lookup_keeps_the_candidate_without_an_excerpt(monkeypatch):
    s, _ = session(monkeypatch, DPError('QUERY_FTS_BODY'), {'terms': ['공매'], 'vector': ['a'], 'lexical': []})
    assert '  - 신용거래관리준칙 제4조 종목 선정' in sr.report(s).split('\n') 


def test_re_search_phrases_are_listed_and_no_record_writes_nothing(monkeypatch):
    s, _ = session(monkeypatch, {}, {'terms': [], 'vector': [], 'lexical': []})
    assert sr.report(s, ['PF 사업장 공매', 'PF 사업장 공매']).endswith('- 다시 찾은 검색어: PF 사업장 공매')
    assert sr.report(types.SimpleNamespace()) == ''


@pytest.mark.parametrize('kind,listed', [('SOURCE', True), ('FACT', False)])
def test_only_a_could_not_find_reply_carries_the_search_section(monkeypatch, kind, listed):
    monkeypatch.setattr(sr, 'report', lambda session, later=(): '찾은 기록')
    v = value()
    v['answer_points'] = []
    v['open_questions'][0]['kind'] = kind
    e, _ = execution(v)
    a = g.assess(e, SOURCES, ISSUES, '어느 유형인가요?', [])
    text = cc.compose(a, g.plan(a))['text']
    assert ('찾은 기록' in text) is listed and a['guided_reply'].get('search_record') == ('찾은 기록' if listed else None)


def test_an_answer_with_explanations_carries_no_search_section(monkeypatch):
    monkeypatch.setattr(sr, 'report', lambda session, later=(): '찾은 기록')
    e, _ = execution(value())
    a = g.assess(e, SOURCES, ISSUES, '어느 유형인가요?', [])
    assert 'search_record' not in a['guided_reply']


def test_a_rejected_answer_reports_the_search_and_what_was_read(tree, tmp_path, monkeypatch):  # noqa: F811
    from test_progress_report import serve_real
    remembered = []
    def discover(s, queries, terms, origin):
        sid = next(iter(s.tools.sources))
        sr.remember(s, ['승인'], [{'source_id': sid}], [sid])
        remembered.append(s)
    monkeypatch.setattr(vn, 'discover', discover)
    original, calls = g.verify, []
    def verify(value, *args, **kwargs):
        # MAIN208 writes a short planning call then the one full answer. Both model answers are rejected;
        # only the full answer's rejection ends in the report. The server's fallback reply still passes.
        calls.append(1)
        if value.get('answer_points'):
            raise ProposalError('Duplicate evidence reference')
        return original(value, *args, **kwargs)
    monkeypatch.setattr(g, 'verify', verify)
    transport = Reporting()
    response = serve_real(tree, tmp_path, transport)
    assert response.status_code == 200, response.text
    assert remembered and len(transport.reports) == 1
    assert transport.reports[0]['view']['stop']['kind'] == 'ANSWER_UNSETTLED'
    text = response.json()['answer']['text']
    assert text.index('**이렇게 찾았습니다**') < text.index('**읽어 본 결과**') < text.index(REPORT['unclear'])
    assert '- 낱말 검색(본문): 승인' in text and REPORT['found'] in text and REPORT['decisions'][0] in text
    assert '서로 맞지' not in text and '판단하기 어려운' not in text and not re.search(r'후보 \d+', text)
