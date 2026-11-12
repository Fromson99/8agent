"""현장 2026-11-11: 인수위험관리준칙 제7-5조 "단, IPO 미매각분은 제2-5조를 준용한다."에서 준용 대상을 못 뽑아
자동 읽기가 안 됐다. "A는 제N조를 준용한다"의 A도 대상으로 본다.
"""
import pytest

from semantic_runtime.legal_agent import citation_roles, connection_scope as cs, guided_navigation as gn

ARTICLE_7_5 = ('제7-5조 (미매각자산 보유기한) 재매각목적으로 취득한 자산의 보유기한 및 보유기한 연장 기준은 제3-5조를 준용한다. '
               '상장 리츠 및 상장 인프라 펀드 등은 주식으로 간주한다. 단, IPO 미매각분은 제2-5조를 준용한다.')
ARTICLE_7_6 = '제7-6조 (대체투자 자산의 관리 및 평가) 대체투자 자산의 관리 및 평가는 제6-5조와 제6-7조를 준용한다.'


@pytest.mark.parametrize('text,cited,expected', [
    (ARTICLE_7_5, '제2-5조', 'IPO 미매각분'),
    (ARTICLE_7_5, '제3-5조', '재매각목적으로 취득한 자산의 보유기한 및 보유기한 연장 기준'),
    (ARTICLE_7_6, '제6-5조', '대체투자 자산의 관리 및 평가'),
    (ARTICLE_7_6, '제6-7조', '대체투자 자산의 관리 및 평가'),
    ('② 유한회사의 이사는 제382조를 준용한다.', '제382조', '유한회사의 이사'),
    # 기존 두 문형 유지
    ('제415조 (준용) 제382조제2항은 감사에 준용한다.', '제382조제2항', '감사'),
    ('감사에 관하여는 제382조제2항을 준용한다.', '제382조제2항', '감사'),
    # 뜻이 없는 주어·주어 없는 문장은 대상이 아니다
    ('이 경우 제10조를 준용한다.', '제10조', None),
    ('이 규정은 제10조를 준용한다.', '제10조', None),
    ('제5조는 제10조를 준용한다.', '제10조', None),
    ('제10조를 준용한다.', '제10조', None),
])
def test_mutatis_subject_phrasings(text, cited, expected):
    start = text.index(cited)
    assert citation_roles.subject(text, start, start + len(cited)) == expected


def link_for(text, cited):
    start = text.index(cited)
    return {'citation_relation': citation_roles.relation(text, start, start + len(cited))}


def test_field_article_is_read_when_the_question_names_its_subject():
    terms = gn.question_terms('상장리츠 IPO 인수 시 취득하는 주식의 처분기한은 언제까지인가요?')
    assert cs.question_match(link_for(ARTICLE_7_5, '제2-5조'), terms)


def test_field_article_stays_unread_when_the_question_is_about_something_else():
    terms = gn.question_terms('주식 의무보유기간이 끝나면 언제까지 처분해야 하나요?')
    assert not cs.question_match(link_for(ARTICLE_7_5, '제2-5조'), terms)
