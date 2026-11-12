"""현장 2026-11-11: 답변이 "인수위험관리준칙(20251205) 제7-5조 … 위치를 알고 계신가요?"라고 되물었다.

답변이 문서명과 함께 이름 댄 조문은 서버가 찾아 읽게 돼 있지만(ADR-1459), 추출 패턴이 제N조만 알아
내규의 하이픈 번호(제7-5조)를 놓쳤고, 문서명 꼬리의 (20251205) 괄호에서 이름을 잘랐다.
번호 해석·구조 조회는 이미 하이픈을 알므로 추출만 고친다.
"""
from types import SimpleNamespace as S

import pytest

from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime.navigation_match import SurfaceIndex, norm
from semantic_runtime.legal_agent import guided_answer as g, structure_query as sq

FIELD_QUESTION = ('인수위험관리준칙(20251205) 제7-5조(미매각자산 보유기한)에 상장리츠 IPO 인수 처분기한 관련 규정이 '
                  '포함되어 있는지, 해당 조문이 있는 문서 위치를 알고 계신가요?')


@pytest.mark.parametrize('text,expected', [
    (FIELD_QUESTION, ['인수위험관리준칙(20251205) 제7-5조']),
    ('수탁업무준칙_개정(案)_240710 제11조를 보면', ['수탁업무준칙_개정(案)_240710 제11조']),
    ('상품관리준칙 제2-1조의 기준', ['상품관리준칙 제2-1조']),
    # 이전 동작 유지
    ('(2) 상법상 자기주식 소각의무(예: 상법 제341조의4)를 별도로 확인할지요?', ['상법 제341조의4']),
    ('다른 증여의제 조문(제45조의2, 제45조의3)의 위치만 확인되었을 뿐', []),
])
def test_mentions_keep_hyphen_numbers_and_dated_names(text, expected):
    assert g.named_article_mentions(text) == expected


def field_matcher():
    title = '인수위험관리준칙(20251205)'
    names = SurfaceIndex()
    names.add(title, 'rule')
    coords, units, sources = {}, {}, {}
    for locator in ('제2-5조', '제7-5조'):
        key = 'rule', locator
        coords[key] = find_coordinates(locator)[0].coordinate
        units[key] = {'coordinate_scope': 'body'}
        sources['rule'+locator] = {'document_id': 'rule', 'unit_id': locator}
    return S(document_names=names, structures=SurfaceIndex(), documents={'rule': title}, title_keys={norm(title)},
             stored_coordinates=coords, units=units, sources=sources, _unit_sources=lambda did, uid: [did+uid])


def executor_for(matcher):
    return S(s=S(matcher=matcher, scope={'rule'}, tools=S(sources=dict(matcher.sources))))


def test_field_question_resolves_to_the_stored_article_and_becomes_a_read():
    executor = executor_for(field_matcher())
    value = {'answer_points': [], 'open_questions': [{'uncertainty': '', 'question': FIELD_QUESTION}]}
    rows, notes = g.named_article_reads(executor, value, [], [])
    assert [r['identity']['source_id'] for r in rows] == ['rule제7-5조']
    assert [n['status'] for n in notes] == ['READ_SCHEDULED']
    assert notes[0]['label'] == '인수위험관리준칙(20251205) · 제7-5조'


def test_already_read_hyphen_article_is_not_read_again():
    executor = executor_for(field_matcher())
    value = {'answer_points': [], 'open_questions': [{'uncertainty': '', 'question': '인수위험관리준칙(20251205) 제2-5조를 더 볼까요?'}]}
    rows, notes = g.named_article_reads(executor, value, [], [{'source_id': 'rule제2-5조'}])
    assert rows == [] and [n['status'] for n in notes] == ['ALREADY_READ']


def test_missing_hyphen_article_is_a_note_not_a_read():
    executor = executor_for(field_matcher())
    value = {'answer_points': [], 'open_questions': [{'uncertainty': '', 'question': '인수위험관리준칙(20251205) 제9-9조에 있나요?'}]}
    rows, notes = g.named_article_reads(executor, value, [], [])
    assert rows == [] and [n['status'] for n in notes] == ['NOT_IN_DOCUMENT']


def test_resolver_itself_accepts_the_dated_name_and_hyphen_number():
    m = field_matcher()
    result = sq.resolve('인수위험관리준칙(20251205) 제7-5조', m, {'rule'})
    assert result['status'] == 'MATCH' and result['pairs'][0]['unit_id'] == '제7-5조'
