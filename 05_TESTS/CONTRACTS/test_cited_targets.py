"""현장 2026-11-11: 인수위험관리준칙 제7-7조 ④항 "투자위험관리준칙 제2-10조 내지 제2-11조".

색인이 문서명을 못 읽으면 같은 번호의 현재 문서 조문에 연결한다. 인용 문장에 적힌 문서 이름이 색인보다 우선한다.
모델이 판단 응답에 함께 적은 조문은 추가 호출 없이 그 차례에 읽는다.
"""
from types import SimpleNamespace as S

import pytest

from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime.navigation_match import SurfaceIndex, norm
from semantic_runtime.legal_agent import cited_targets as ct, guided_navigation as gn

TITLES = {'und': '인수위험관리준칙(20251205)', 'inv': '투자위험관리준칙(20260226)'}
PARAGRAPH = '④ 제1항 내지 2항 이외의 사항은 제6-6조, 제6-7조, 투자위험관리준칙 제2-10조 내지 제2-11조를 준용한다.'
ARTICLES = (('und', '제2-10조'), ('und', '제6-6조'), ('und', '제6-7조'), ('inv', '제2-10조'), ('inv', '제2-11조'))


def session(scope=None):
    names = SurfaceIndex()
    for did, title in TITLES.items():
        names.add(title, did)
    coords, units, sources = {}, {}, {}
    for did, locator in ARTICLES:
        key = did, locator
        coords[key] = find_coordinates(locator)[0].coordinate
        units[key] = {'coordinate_scope': 'body'}
        sources[did+locator] = {'document_id': did, 'unit_id': locator}
    context = {did: {'source_category': 'internal', 'document_title': title} for did, title in TITLES.items()}
    matcher = S(document_names=names, structures=SurfaceIndex(), documents=TITLES, title_keys={norm(t) for t in TITLES.values()},
                document_context=context, stored_coordinates=coords, units=units, sources=sources, _unit_sources=lambda did, uid: [did+uid])
    return S(matcher=matcher, scope=set(scope or TITLES), tools=S(sources=sources))


def reference(mention, targets, text=PARAGRAPH):
    start = text.index(mention)
    return {'id': 'r1', 'document_id': 'und', 'source_text': text, 'mention_start': start, 'mention_end': start + len(mention),
            'target_source_ids': targets, 'resolution': 'EXACT_DETERMINISTIC_RANGE'}


@pytest.mark.parametrize('mention,expected', [
    ('제2-10조 내지 제2-11조', (['제2-10조', '제2-11조'], 0)),
    ('제3조부터 제5조까지', (['제3조', '제4조', '제5조'], 0)),
    ('제1조부터 제9조까지', (['제1조', '제2조', '제3조', '제4조'], 5)),
    ('제7-5조', (['제7-5조'], 0)),
    ('문서 없음', ([], 0)),
])
def test_articles_in(mention, expected):
    assert ct.articles_in(mention) == expected


def test_written_name_overrides_a_link_to_the_citing_document():
    fixed = ct.correct_reference(session(), reference('제2-10조 내지 제2-11조', ['und제2-10조']))
    assert fixed['target_source_ids'] == ['inv제2-10조', 'inv제2-11조']
    assert fixed['resolution'] == 'EXACT_CITED_NAME' and fixed['stored_resolution'] == 'EXACT_DETERMINISTIC_RANGE'


def test_citations_without_a_written_name_keep_their_link():
    assert ct.correct_reference(session(), reference('제6-6조', ['und제6-6조'])) is None


def test_a_link_already_in_the_named_document_is_kept():
    assert ct.correct_reference(session(), reference('제2-10조 내지 제2-11조', ['inv제2-10조', 'inv제2-11조'])) is None


def test_a_named_document_outside_the_request_never_falls_back_to_the_same_number():
    fixed = ct.correct_reference(session({'und'}), reference('제2-10조 내지 제2-11조', ['und제2-10조']))
    assert fixed['target_source_ids'] == [] and fixed['resolution'] == 'CITED_NAME_UNRESOLVED'


def test_ordinary_words_are_not_document_names():
    text = '관련규정 제2-10조를 준용한다.'
    assert ct.correct_reference(session(), reference('제2-10조', ['und제2-10조'], text)) is None


def test_broken_offsets_keep_the_reference():
    assert ct.correct_reference(session(), {'source_text': 'x', 'mention_start': 9, 'mention_end': 12}) is None


SCHEMA = {'type': 'object', 'anyOf': [
    {'type': 'object', 'properties': {'choice': {'const': 'READ'}}, 'required': ['choice']},
    {'type': 'object', 'properties': {'choice': {'const': 'ASK_USER'}}, 'required': ['choice']}]}


def test_cited_reads_are_offered_only_when_a_read_text_names_an_article():
    assert gn.with_cited_reads(SCHEMA, [{'text': '거래담당부서는 보고한다.'}]) is SCHEMA
    offered = gn.with_cited_reads(SCHEMA, [{'text': PARAGRAPH}])
    assert 'cited_reads' in offered['anyOf'][0]['required'] and 'cited_reads' not in offered['anyOf'][1]['properties']
    assert 'cited_reads' not in SCHEMA['anyOf'][0]['properties']


def investigation(monkeypatch):
    done = []
    s = session()
    inv = S(s=S(**vars(s), continuation_reads=None), p={}, save=lambda: None)
    monkeypatch.setattr(gn, '_known_reads', lambda _inv: {'inv제2-11조': {'b'}})
    monkeypatch.setattr(gn, 'preread', lambda i: done.append(list(i.s.continuation_reads)))
    return inv, done


def test_named_range_is_read_in_the_same_turn_without_a_model_call(monkeypatch):
    inv, done = investigation(monkeypatch)
    gn.read_cited(inv, ['투자위험관리준칙(20260226) 제2-10조 내지 제2-11조', '투자위험관리준칙 제9-9조', '제목 없음'])
    assert [t['identity']['source_id'] for t in done[0]] == ['inv제2-10조']
    assert {n['mention']: n['status'] for n in inv.p['cited_read_notes']} == {
        '투자위험관리준칙(20260226) 제2-10조': 'READ_SCHEDULED', '투자위험관리준칙(20260226) 제2-11조': 'ALREADY_READ',
        '투자위험관리준칙 제9-9조': 'MISSING_COORDINATE', '제목 없음': 'NO_ARTICLE_NUMBER'}
    assert inv.s.continuation_reads is None


def test_nothing_is_read_for_an_empty_list(monkeypatch):
    inv, done = investigation(monkeypatch)
    gn.read_cited(inv, [])
    assert done == [] and inv.p == {}
