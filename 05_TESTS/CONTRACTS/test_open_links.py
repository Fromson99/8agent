"""열린 고리 읽기·후보 12개·답변 입력 예산·결과 불명 처리·검색 낱말 (ADR-1475 못 맞춘 조문의 로직별 원인 대응)."""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import guided_answer as ga
from semantic_runtime.legal_agent import guided_navigation as gn
from semantic_runtime.legal_agent.errors import TransportError


def option(ident, source, block='10', start=0, end=200, text=''):
    return {'id': ident, 'source_id': source, 'document_id': 'D', 'block_id': block, 'start_cp': start, 'end_cp': end, 'text': text}


def location(ident, label, **hints):
    return {'id': ident, 'label': label, 'origin': 'LOCATION', 'identity': {'document_id': 'D', 'source_id': 's-' + ident, 'unit_id': ident}, **hints}


def context(source, start, text, link=None, block='10'):
    return {'source_id': source, 'block_id': block, 'start': start, 'text': text, **({'link': link} if link else {})}


def test_link_kind_reads_the_sentence_not_the_title():
    text = '평가기간 경과 후부터 제78조제1항에 따른 기한까지의 기간 중에 매매등이 있는 경우'
    at = text.index('제78조'); assert gn.link_kind(text, at, at + 4) == 'VALUE'
    text = '제388조는 감사에 준용한다.'; assert gn.link_kind(text, 0, 5) == 'APPLY'
    text = '「증권 인수업무 등에 관한 규정」 제5조에 따른 공모가격으로 취득한다.'
    at = text.index('제5조'); assert gn.link_kind(text, at, at + 3) == 'VALUE'
    text = '제2조제1호에 따른 벤처기업의 임직원'; assert gn.link_kind(text, 0, 3) == 'REFERENCE'
    text = '제27조에도 불구하고 다음 각 호의 경우에는'; assert gn.link_kind(text, 0, 4) == 'PARENT'


def test_a_value_or_application_link_in_used_evidence_is_read_whatever_the_title():
    options = [option('S1', 'a49', start=0, end=300)]
    value = {'answer_points': [{'evidence_refs': ['S1'], 'text': '평가기준일 전후 6개월 이내의 매매가액을 시가로 본다.'}]}
    reads = [location('L1', '시행령 제60조(조건부 권리 등의 평가)', matched_terms=['평가'], cited_contexts=[context('a49', 400, '제60조에 따라 평가한 가액', 'REFERENCE')]),
             location('L2', '시행령 제78조(결정ㆍ경정)', cited_contexts=[context('a49', 120, '제78조제1항에 따른 기한까지', 'VALUE')]),
             location('L3', '시행령 제61조(신탁의 이익을 받을 권리의 평가)', matched_terms=['평가'], cited_contexts=[context('a49', 420, '제61조 평가', 'REFERENCE')])]
    rows = ga.evidence_cited_rows(reads, set(), value, options, {'평가'})
    assert rows[0] == ('LINK', reads[1])
    # 다음 라운드(first=False)에도 고리는 읽고, 그 밖의 인용은 읽지 않는다.
    assert ga.evidence_cited_rows(reads, set(), value, options, {'평가'}, first=False) == [('LINK', reads[1])]
    # 둘째 답변 라운드 뒤에 읽은 조문이 가리키는 곳은 더 따라가지 않는다.
    assert ga.evidence_cited_rows(reads, set(), value, options, {'평가'}, frozen={'a49'}) == []


def test_kept_points_count_as_used_evidence_and_lower_rules_of_used_articles_are_links():
    options = [option('S1', 'a13', start=0, end=300)]
    previous = [{'point_id': 'P1', 'text': '보유기간', 'issue_refs': ['Q1'], 'evidence_refs': ['S1']}]
    value = {'answer_points': [], 'kept_points': ['P1']}
    reads = [location('L1', '시행세칙 제15조', specifies=['규정 제13조'], specifies_score=2, connection={'kind': 'LOWER_RULE', 'anchor_source_id': 'a13'}),
             location('L2', '시행세칙 제21조', specifies=['규정 제27조'], specifies_score=5, connection={'kind': 'LOWER_RULE', 'anchor_source_id': 'a27'})]
    assert ga.lower_rule_links(reads, set(), value, options, previous=previous) == [('LINK', reads[0])]
    assert ga.lower_rule_links(reads, set(), value, options) == []


def test_locations_without_a_unit_id_are_not_merged_by_document():
    locs = [{'identity': {'document_id': 'D', 'source_id': 'a%d' % i}, 'label': '상법 · 제%d조' % i} for i in (388, 391, 412)]
    assert [r['label'] for r in ga.read_choices([], locs)] == ['상법 · 제388조', '상법 · 제391조', '상법 · 제412조']


def test_offered_locations_keep_links_and_near_first_screen_rows_once_per_article():
    row = lambda label, uid, **k: {'label': label, 'identity': {'document_id': 'D', 'source_id': label, 'unit_id': uid}, **k}
    common = [row('평가%d' % i, str(i), cited_by=['제49조'], matched_terms=['평가']) for i in range(12)]
    rows = common + [row('제78조', '78', cited_by=['제49조'], relation='값 참조(기한·금액·요건 등)'),
                     row('제39조', '39', vector_rank=6, matched_terms=['이익', '증여']),
                     row('제41조의2', '412', vector_rank=27, matched_terms=['이익', '증여']),
                     row('평가0', None, cited_by=['제49조'], matched_terms=['평가'])]
    out = gn.offered_locations(rows)
    labels = [r['label'] for r in out]
    assert len(out) == 12 and labels[0] == '제78조' and labels[1:3] == ['제39조', '제41조의2'] and labels.count('평가0') == 1


def test_first_screen_read_prefers_a_title_word_no_read_title_holds():
    reads = [location('L1', '제391조의2(감사의 이사회출석)', vector_rank=6, matched_terms=['감사', '이사회']),
             location('L2', '제388조(이사의 보수)', vector_rank=11, matched_terms=['보수'])]
    assert [r['id'] for r in ga.vector_title_reads({'next_reads': []}, reads, {'감사', '이사회'})] == ['L2', 'L1']
    assert [r['id'] for r in ga.vector_title_reads({'next_reads': []}, reads)] == ['L1', 'L2']


def test_relative_mentions_use_the_evidence_document_family():
    assert ga.relative_mentions('평가기간 경과 후 제78조', ['상속세 및 증여세법 시행령']) == ['상속세 및 증여세법 시행령 제78조']
    assert ga.relative_mentions('법 제63조', ['상속세 및 증여세법 시행령']) == ['상속세 및 증여세법 제63조']
    assert ga.relative_mentions('시행규칙 제14조', ['자본시장과 금융투자업에 관한 법률']) == ['자본시장과 금융투자업에 관한 법률 시행규칙 제14조']
    assert ga.relative_mentions('세칙 제15조', ['코스닥시장 상장규정']) == ['코스닥시장 상장규정 시행세칙 제15조']
    assert ga.relative_mentions('같은 조 제3항', ['상법']) == []
    assert ga.named_article_mentions('「자본시장과 금융투자업에 관한 법률」 시행규칙 제14조제1항을 준용') == ['「자본시장과 금융투자업에 관한 법률」 시행규칙 제14조']


def source(sid, text, heading=''):
    return {'source_id': sid, 'document_id': 'D', 'document_name': '외규 > 모의법', 'heading': heading, 'text': text,
            'adopted_spans': [{'text': text}]}


def test_answer_input_keeps_draft_and_new_originals_within_the_budget():
    sources = [source('a', '가' * 400), source('b', '주식매수선택권 취득가액 ' + '나' * 400), source('c', '다' * 400), source('d', '라' * 400)]
    shown, withheld = ga.shown_sources(sources, '주식매수선택권 취득가액은?', budget=10 ** 6)
    assert shown == sources and not withheld
    shown, withheld = ga.shown_sources(sources, '주식매수선택권 취득가액은?', keep={'c'}, fresh={'d'}, budget=900)
    assert [s['source_id'] for s in shown] == ['c', 'd'] and [s['source_id'] for s in withheld] == ['a', 'b']
    shown, withheld = ga.shown_sources(sources, '주식매수선택권 취득가액은?', budget=900)
    assert [s['source_id'] for s in shown] == ['b', 'd']  # 질문 낱말이 든 원문, 그다음 최근에 읽은 원문
    assert ga.schema([{'id': 'Q1'}], [{'id': 'S1'}])['properties']['answer_points']['items']['properties']['evidence_refs']['maxItems'] == ga.EVIDENCE_REF_LIMIT


ISSUES = [{'id': 'Q1', 'question': '기준은?'}]
TEXT = '거래 금액이 100 이상이면 A유형으로 본다.'
SOURCES = [{'source_id': 'source:1', 'document_id': 'doc1', 'document_name': '모의규정', 'heading': '제1조', 'text': TEXT,
            'adopted_spans': [{'text': TEXT, 'block_id': '1', 'start_cp': 0, 'end_cp': len(TEXT), 'evidence_id': 'E1'}]}]


class Journal:
    def __init__(self): self.states = {}; self.events = []
    def event(self, k, v): self.events.append((k, deepcopy(v)))
    def output_decision_state(self, k): return self.states.get(k)
    def output_decision_event(self, v): self.states[v['decision_key']] = deepcopy(v)


def execution(outputs):
    calls = []; work = Journal(); queue = list(outputs)
    def invoke(prompt, data, schema, phase):
        calls.append(deepcopy(data)); out = queue.pop(0)
        if isinstance(out, Exception): raise out
        return deepcopy(out)
    e = S(s=S(work=work, sources=S(profile={'answer_presentation': ga.VERSION})), host=S(binding={'generation': 'fixture'}, verify=lambda _: None), invoke=invoke)
    return e, calls, work


def test_unknown_answer_call_returns_the_acquired_originals_without_a_second_send():
    e, calls, work = execution([TransportError('deadline', retryable=False, unknown=True)])
    result = ga.assess(e, deepcopy(SOURCES), ISSUES, '어떤 기준인가요?', [])
    assert len(calls) == 1 and not result['claims'] and result['source_excerpt_reply']['sources']
    assert result['guided_reply']['interruption']['kind'] == 'MODEL_OUTCOME_UNKNOWN'
    assert ('GUIDED_ANSWER_CALL_UNKNOWN', {'code': 'MODEL_TRANSPORT_ERROR', 'resent': False, 'returned': 'ORIGINALS_ONLY', 'originals': 1}) in work.events


def test_unknown_rewrite_returns_the_verified_draft_of_this_request():
    options = __import__('semantic_runtime.legal_agent.completion_contracts', fromlist=['x']).evidence_options(SOURCES)
    first = {'answer_points': [{'issue_refs': ['Q1'], 'evidence_refs': [options[0]['id']], 'text': '거래 금액이 100 이상이면 A유형입니다.'}], 'open_questions': []}
    e, calls, work = execution([first, TransportError('deadline', retryable=False, unknown=True)])
    draft = ga.assess(e, deepcopy(SOURCES), ISSUES, '어떤 기준인가요?', [])
    assert draft['claims'] and e.round_draft[1] == draft
    more = deepcopy(SOURCES) + [{**deepcopy(SOURCES[0]), 'source_id': 'source:2', 'heading': '제2조', 'text': '제2조 원문', 'adopted_spans': [{'text': '제2조 원문', 'block_id': '2', 'start_cp': 0, 'end_cp': 6, 'evidence_id': 'E2'}]}]
    again = ga.assess(e, more, ISSUES, '어떤 기준인가요?', [])
    assert len(calls) == 2 and again['claims'] == draft['claims'] and again['guided_reply']['rewrite_interrupted'] is True
    assert 'proposed_reads' not in again['guided_reply'] and again['guided_reply']['original_count'] == 2
    with pytest.raises(TransportError):  # 알려진 거절(결과가 확인된 오류)은 그대로 올린다
        e2, _, _ = execution([TransportError('rejected', retryable=False, unknown=False)]); ga.assess(e2, deepcopy(SOURCES), ISSUES, '질문', [])


def test_body_search_gets_the_question_words_the_model_left_out(monkeypatch):
    from semantic_runtime import vector_navigation as vn
    seen = {}
    monkeypatch.setattr(vn, 'lexical_articles', lambda session, terms: seen.setdefault('terms', list(terms)) and [])
    session = S(context=S(request={'question': '외규: 상장주선인이 의무인수한 주식의 보유기간이 연장되는 경우는?'}), scope={'D'}, tools=S(sources={}))
    monkeypatch.setattr('semantic_runtime.legal_agent.query_scope.documents', lambda s: {'D'})
    rows, info = vn.fuse(session, [], ['보유', '연장'])
    assert '주선인' in seen['terms'] and '외규' not in seen['terms'] and info['model_terms'] == ['보유', '연장'] and '주선인' in info['question_terms_added']
