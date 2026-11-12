"""현장 2026-11-11: 인수위험관리준칙 제7-7조 ④항은 "투자위험관리준칙 제2-10조"라고 쓰지만 문서는 "투자위험관리준칙(20260226)"으로
저장돼 있어 구조 조회가 문서를 못 찾았다. 위임 연결이 쓰는 제목 목록(날짜 제거·최신 판본)을 구조 조회에서도 쓴다.
"""
from types import SimpleNamespace as S

from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime.navigation_match import SurfaceIndex, norm
from semantic_runtime.legal_agent import structure_query as sq

TITLES = {'inv-old': '투자위험관리준칙(20250101)', 'inv': '투자위험관리준칙(20260226)', 'und': '인수위험관리준칙(20251205)',
          'law': '금융투자업규정'}
SCOPE = set(TITLES)


def matcher(titles=TITLES, category='internal'):
    names = SurfaceIndex()
    for did, title in titles.items():
        names.add(title, did)
    coords, units, sources = {}, {}, {}
    for did, locator in (('inv-old', '제2-10조'), ('inv', '제2-10조'), ('und', '제2-10조'), ('law', '제2-10조')):
        if did in titles:
            key = did, locator
            coords[key] = find_coordinates(locator)[0].coordinate
            units[key] = {'coordinate_scope': 'body'}
            sources[did+locator] = {'document_id': did, 'unit_id': locator}
    context = {did: {'source_category': 'external' if did == 'law' else category, 'document_title': title} for did, title in titles.items()}
    return S(document_names=names, structures=SurfaceIndex(), documents=titles, title_keys={norm(t) for t in titles.values()},
             document_context=context, stored_coordinates=coords, units=units, sources=sources, _unit_sources=lambda did, uid: [did+uid])


def found(question, m=None, scope=SCOPE):
    result = sq.resolve(question, m or matcher(), set(scope))
    return result['status'], [p['document_id'] for p in result['pairs']]


def test_undated_name_finds_the_latest_edition():
    assert found('투자위험관리준칙 제2-10조') == ('MATCH', ['inv'])


def test_brackets_and_spacing_do_not_matter():
    assert found('「투자위험관리준칙」 제2-10조') == ('MATCH', ['inv'])
    assert found('투자위험 관리준칙 제2-10조') == ('MATCH', ['inv'])


def test_exact_stored_name_is_unchanged():
    assert found('투자위험관리준칙(20250101) 제2-10조') == ('MATCH', ['inv-old'])


def test_the_title_must_stand_right_before_the_article():
    assert found('투자위험관리준칙에 따라 제2-10조') == ('MISS', [])


def test_unknown_title_and_bare_article_stay_missing():
    assert found('없는준칙 제2-10조') == ('MISS', [])
    assert found('제2-10조') == ('MISS', [])


def test_edition_outside_the_request_scope_is_not_used():
    assert found('투자위험관리준칙 제2-10조', scope={'inv-old', 'und'}) == ('MATCH', ['inv-old'])


def test_external_documents_are_not_matched_by_this_route():
    titles = {'ext': '모의규정(20260226)'}
    m = matcher(titles, category='external')
    m.stored_coordinates = {('ext', '제1조'): find_coordinates('제1조')[0].coordinate}
    m.units = {('ext', '제1조'): {'coordinate_scope': 'body'}}
    assert found('모의규정 제1조', m, {'ext'}) == ('MISS', [])
