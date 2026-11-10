"""관계 조항(준용 다리·경합·우선·포괄)·인용 구절 묶음(범위 4개까지)·상대 문서 이름·제목 낱말 (계획 r5, ADR-1477 못 찾은 조문)."""
import re
from types import SimpleNamespace as S
from semantic_runtime.legal_agent import guided_answer as ga
from semantic_runtime.legal_agent import guided_navigation as gn
from semantic_runtime.legal_agent.citation_roles import relation


def kind_of(text, mention):
    at = text.index(mention)
    rel = relation(text, at, at + len(mention))
    return gn.relation_kind(rel, rel.get('sentence')), rel


def test_relation_kinds_come_from_the_citing_sentence():
    k, rel = kind_of('제382조제2항, 제388조, 제400조는 감사에 준용한다.', '제388조')
    assert k == 'BRIDGE' and gn.subject_matches(rel['subject'], ['감사', '보수']) == ['감사']
    text = '① 하나의 증여에 대하여 제33조부터 제39조까지, 제41조의2부터 제41조의5까지의 규정이 둘 이상 동시에 적용되는 경우에는 그 중 이익이 가장 많게 계산되는 것 하나만을 적용한다.'
    assert kind_of(text, '제41조의2부터 제41조의5까지')[0] == 'OVERLAP'
    assert kind_of('③ 제2항에도 불구하고 제16조의3제1항제3호에 해당하는 자에게 부여하는 경우에는', '제16조의3')[0] == 'PRIORITY'
    assert kind_of('④ 제16조의3부터 제16조의6까지에서 규정한 사항 외에 주식매수선택권 부여에 필요한 사항은 대통령령으로 정한다.', '제16조의3부터 제16조의6까지')[0] == 'RESIDUAL'
    assert kind_of('③ 벤처기업의 주식매수선택권에 관하여는 「상법」 제340조의2부터 제340조의5까지에 우선하여 이 법을 적용한다.', '제340조의2부터 제340조의5까지')[0] == 'PRIORITY'
    # 한 조문 안의 계산("A에서 B를 차감한 가액")은 경합이 아니다.
    assert kind_of('① 법 제41조의3제1항에 따른 이익은 제1호의 가액에서 제2호 및 제3호의 가액을 차감한 가액으로 한다.', '제41조의3')[0] is None
    assert kind_of('제2조제1호에 따른 벤처기업의 임직원', '제2조')[0] is None


def test_a_long_bridge_subject_is_a_clause_not_a_subject():
    assert gn.subject_matches('따로 평가방법을 규정하지 아니한 재산의 평가', ['평가']) == []
    assert gn.subject_matches('유한회사의 감사', ['감사']) == ['감사']


def test_relation_question_markers():
    assert gn.relation_question('상장차익 증여의제의 이익을 계산할 때 이미 과세된 저가분이 조정되는가?')
    assert not gn.relation_question('우선주 발행 요건은?') and not gn.relation_question('정관 변경의 결의요건은?')


def test_phrase_gap_and_range_members():
    assert gn.phrase_gap(' 또는 ') == 'JOIN' and gn.phrase_gap('제1항, ') == 'JOIN' and gn.phrase_gap('제2항제1호부터 ') == 'RANGE'
    assert gn.phrase_gap(' 「상법」 ') is None and gn.phrase_gap('에 따른 ') is None
    assert gn.range_members('제340조의2', '제340조의5') == ['제340조의3', '제340조의4']
    assert gn.range_members('제340조', '제340조의3') == ['제340조의2']
    assert gn.range_members('제33조', '제39조') == ['제34조', '제35조', '제36조', '제37조', '제38조']
    assert gn.range_members('제39조', '제33조') is None
    assert gn.cited_in_range('「상법」 제340조의2부터 제340조의5까지에 우선하여', '제340조의4')
    assert not gn.cited_in_range('제340조의2부터 제340조의5까지', '제341조')


def test_family_names_before_an_article_number():
    m = gn.FAMILY_SUFFIX.search('「자본시장과 금융투자업에 관한 법률」 제165조와 법 시행규칙 ')
    assert m.group('law') == '법' and m.group('rank') == '시행규칙'
    assert gn.FAMILY_SUFFIX.search('영 ').group('law') == '영'
    m = gn.FAMILY_SUFFIX.search('주식매수선택권 ')
    assert not (m.group('law') or m.group('rank'))


def test_title_terms_do_not_cut_words():
    # user 2026-11-10 "쪼개지 않는 방법으로만": no two-syllable pieces ("고서" from 신고서)
    terms = gn.title_terms('IPO를 위한 증권신고서 제출 시 검토보고서를 첨부하여야 하는가?')
    assert '고서' not in terms and '증권신고서' in terms and 'IPO를' not in terms


def option(ident, source):
    return {'id': ident, 'source_id': source, 'document_id': 'D', 'block_id': '1', 'start_cp': 0, 'end_cp': 100, 'text': ''}


def location(ident, label, **hints):
    return {'id': ident, 'label': label, 'origin': 'LOCATION', 'identity': {'document_id': 'D', 'source_id': 's-' + ident, 'unit_id': ident}, **hints}


def test_relation_clauses_of_the_answers_evidence_are_read_bridge_first_two_at_most():
    options = [option('S1', 'a388')]
    value = {'answer_points': [{'evidence_refs': ['S1'], 'text': '이사의 보수는 정관 또는 주주총회 결의로 정한다.'}]}
    clause = lambda ident, kind, anchor='a388', rank=(0, 0, 0): location(ident, ident, relation_clause={'kind': kind, 'anchor_source_id': anchor, 'rank': list(rank)})
    reads = [clause('L1', 'PRIORITY', rank=(1, 0, 0)), clause('L2', 'BRIDGE', rank=(0, -1, 1)), clause('L3', 'BRIDGE', rank=(0, -1, 0)),
             clause('L4', 'BRIDGE', anchor='other')]
    assert [r['id'] for _, r in ga.relation_reads(reads, set(), value, options)] == ['L3', 'L2']
    assert ga.relation_reads(reads, set(), value, options, room=0) == []
    assert ga.relation_reads(reads, set(), value, options, frozen={'a388'}) == []
    # 다른 방향으로 읽은 첫 화면 조문도 출발점이다.
    assert [r['id'] for _, r in ga.relation_reads(reads, set(), {'answer_points': []}, options, starts={'other'})] == ['L4']


def test_phrase_groups_are_read_together_from_used_evidence_or_a_read_relation_clause():
    options = [option('S1', 'a16-6')]
    value = {'answer_points': [{'evidence_refs': ['S1'], 'text': '벤처기업 주식매수선택권은 상법보다 우선 적용된다.'}]}
    group = lambda ident, source: location(ident, ident, group={'source_id': source, 'block_id': '3', 'start': 10, 'members': ['제340조의3', '제340조의4', '제340조의5']})
    reads = [group('L1', 'a16-6'), group('L2', 'a16-6'), group('L3', 'elsewhere'), location('L4', 'plain')]
    assert [r['id'] for _, r in ga.group_reads(reads, set(), value, options)] == ['L1', 'L2']
    assert [r['id'] for _, r in ga.group_reads(reads, set(), {'answer_points': []}, options, relation_sources={'elsewhere'})] == ['L3']
    assert ga.group_reads(reads, set(), value, options, frozen={'a16-6'}) == []


def test_relative_family_uses_the_rule_s_declared_law():
    assert ga.relative_mentions('법 시행규칙 제14조', ['증권 인수업무 등에 관한 규정'], {'증권 인수업무 등에 관한 규정': '자본시장과 금융투자업에 관한 법률'}) == \
        ['자본시장과 금융투자업에 관한 법률 시행규칙 제14조']
    assert ga.relative_mentions('규정 제5조', ['증권 인수업무 등에 관한 규정'], {'증권 인수업무 등에 관한 규정': '자본시장과 금융투자업에 관한 법률'}) == \
        ['증권 인수업무 등에 관한 규정 제5조']


def test_generic_document_family_bonus_is_named_by_the_question():
    from semantic_runtime import vector_navigation as vn
    session = S(tools=S(sources={'k': {'document_name': 'external > law > 코스닥시장 상장규정'}, 'u': {'document_name': 'external > law > 상법'}}))
    family = vn.family_documents(session, 'IPO 단계에서 거래소 규정상 제출이 요구되는 재무서류는?')
    assert family('k') and not family('u')
    assert vn.family_documents(session, '정관 변경의 결의요건은?') is None



def test_a_quoted_passage_with_raw_line_breaks_inside_a_long_original_is_stored_unchanged(tmp_path, monkeypatch):
    """ADR-1477 cm-023/024/025 (HTTP 422): a form original quoted lines that hold raw line breaks; the
    nested-string factoring parsed such a passage as a JSON string literal and ended the request."""
    import json
    from semantic_runtime.legal_agent import journal_storage as js
    monkeypatch.setenv('GENOS_JOURNAL_STORAGE', 'compact')
    db = js.connect(str(tmp_path / 'j.sqlite')); js.initialize(db)
    quoted = '"' + ('가' * 300) + '\n' + ('나' * 300) + '"'  # a quoted passage, not a JSON string literal
    original = json.dumps({'text': '서식 원문 ' + quoted + ' 끝' + '다' * 600}, ensure_ascii=False)
    nested = json.dumps({'messages': [{'content': original}]}, ensure_ascii=False)
    for value in (original, nested):
        stored = js.store(db, value)
        assert stored != value and js.restore(db, stored) == value


def test_forms_are_not_first_screen_server_reads():
    from semantic_runtime.legal_agent import guided_answer as ga
    reads = [location('L1', '서식 10의6', vector_rank=1, matched_terms=['증여'], form=True),
             location('L2', '제41조의3(주식등의 상장 등에 따른 이익의 증여)', vector_rank=4, matched_terms=['증여'])]
    assert [r['id'] for r in ga.vector_title_reads({'next_reads': []}, reads)] == ['L2']


def test_a_long_apply_list_in_the_evidence_is_offered_not_forced():
    options = [option('S1', 'a415-2')]
    value = {'answer_points': [{'evidence_refs': ['S1'], 'text': '감사위원회에는 이사의 규정이 준용된다.'}]}
    ctx = lambda size: [{'source_id': 'a415-2', 'block_id': '1', 'start': 10, 'text': '제382조제2항, 제386조, 제400조, 제401조, 제407조는 감사위원회에 준용한다.',
                         'link': 'APPLY', 'phrase': 0, 'phrase_size': size}]
    short = [location('L1', '제386조', cited_contexts=ctx(2))]
    long = [location('L1', '제386조', cited_contexts=ctx(6))]
    assert ga.evidence_cited_rows(short, set(), value, options)[0][0] == 'LINK'
    assert ga.evidence_cited_rows(long, set(), value, options)[0][0] == 'EVIDENCE_CITED'
    assert ga.evidence_cited_rows(long, set(), value, options, first=False) == []


def test_an_invalid_answer_gets_one_full_correction():
    from copy import deepcopy
    from types import SimpleNamespace as S
    from semantic_runtime.legal_agent import completion_contracts as cc
    text = '거래 금액이 100 이상이면 A유형으로 본다.'
    sources = [{'source_id': 'source:1', 'document_id': 'doc1', 'document_name': '모의규정', 'heading': '제1조', 'text': text,
                'adopted_spans': [{'text': text, 'block_id': '1', 'start_cp': 0, 'end_cp': len(text), 'evidence_id': 'E1'}]}]
    issues = [{'id': 'Q1', 'question': '기준은?'}]
    ref = cc.evidence_options(sources)[0]['id']
    outputs = [{'answer_points': [], 'open_questions': []},
               {'answer_points': [{'issue_refs': ['Q1'], 'evidence_refs': [ref], 'text': '100 이상이면 A유형입니다.'}], 'open_questions': []}]
    calls = []
    class Journal:
        def __init__(self): self.states = {}; self.events = []
        def event(self, k, v): self.events.append(k)
        def output_decision_state(self, k): return self.states.get(k)
        def output_decision_event(self, v): self.states[v['decision_key']] = deepcopy(v)
    def invoke(prompt, data, schema, phase):
        calls.append(data); return deepcopy(outputs[len(calls) - 1])
    e = S(s=S(work=Journal(), sources=S(profile={'answer_presentation': ga.VERSION})), host=S(binding={'generation': 'fixture'}, verify=lambda _: None), invoke=invoke)
    result = ga.assess(e, deepcopy(sources), issues, '기준은?', [])
    assert len(calls) == 2 and result['claims'] and 'contract_error' in calls[1]
