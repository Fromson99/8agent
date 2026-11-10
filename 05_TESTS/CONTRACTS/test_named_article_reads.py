"""MAIN177 CM 9문항(ADR-1458)에서 본 탐색 결함의 서버 측 수정 (2026-11-08).

1) 답변이 문서명과 함께 이름 댄 조문(cm-030 시행령 제125조, cm-041 상법 제542조의8, cm-045 상법 제341조의4)은
   서버가 범위 안에서 찾아 이번 요청의 읽기로 더한다. 없는 번호(cm-023 제45조의6)는 NOT_IN_DOCUMENT로 다음 입력에 남는다.
2) 중복 참조 ID(cm-030 evidence_refs 중복)는 순서를 지키며 제거하고 기록한다. "판단 처리 오류"로 끝나지 않는다.
3) 읽은 원문이 다른 법령을 이름과 함께 인용하면(증발공 제4-3조 → 「상법」 제341조의4) 그 조문이 읽기 후보가 된다.
4) 같은 제도의 역방향 인용(제16조의3 ← 제16조의5 주식매수선택권의 행사)은 개수만 세지 않고 선택할 수 있게 남긴다.
5) 같은 조의 항 단위 후보는 한 번만 제시하고, 질문 낱말에서 조사·형식어를 뺀다.
"""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest

from semantic_runtime.legal_agent import guided_answer as g, completion_contracts as cc, connection_scope as cs
from semantic_runtime.legal_agent import guided_navigation as gn, structure_query as sq
from test_guided_answer import ISSUES, SOURCES, OPTIONS, execution, value


def test_duplicate_reference_ids_are_normalized_and_recorded():
    v = value()
    v['answer_points'][0]['evidence_refs'] = [OPTIONS[0]['id'], OPTIONS[0]['id']]
    v['answer_points'][0]['issue_refs'] = ['Q1', 'Q1']
    out, changes = g.normalize_references(v)
    assert out['answer_points'][0]['evidence_refs'] == [OPTIONS[0]['id']] and out['answer_points'][0]['issue_refs'] == ['Q1']
    assert {c['field'] for c in changes} == {'evidence_refs', 'issue_refs'} and v['answer_points'][0]['evidence_refs'][1] == OPTIONS[0]['id']
    e, calls = execution(v)
    result = g.assess(e, SOURCES, ISSUES, '어느 유형인가요?', [])
    assert result['claims'] and 'interruption' not in result['guided_reply']
    assert result['guided_reply']['reference_normalizations'][0]['field'] in ('evidence_refs', 'issue_refs')
    assert any(k == 'GUIDED_ANSWER_REFERENCE_NORMALIZED' for k, _ in e.s.work.events)
    assert not any(k == 'GUIDED_ANSWER_FORMAT_STOPPED' for k, _ in e.s.work.events)


def test_named_article_mentions_are_fragments_with_a_law_name():
    assert g.named_article_mentions('자본시장과 금융투자업에 관한 법률 시행령 제125조(신고서의 기재사항 및 첨부서류) 본문을 이어서 읽어볼까요?') == ['자본시장과 금융투자업에 관한 법률 시행령 제125조']
    assert g.named_article_mentions('(2) 상법상 자기주식 소각의무(예: 상법 제341조의4)를 별도로 확인할지요?') == ['상법 제341조의4']
    # A bare article number without a law name is not resolved (no guessing of the document).
    assert g.named_article_mentions('다른 증여의제 조문(제45조의2, 제45조의3)의 위치만 확인되었을 뿐') == []


def fake_resolve(table):
    def resolve(fragment, matcher, scope, **_):
        hit = table.get(fragment)
        if hit is None:
            return {'status': 'MISS', 'reason': 'MISSING_OR_AMBIGUOUS_COORDINATE', 'failure': {'code': 'MISSING_COORDINATE'}}
        return {'status': 'MATCH', 'pairs': [{'document_id': hit[0], 'unit_id': hit[1], 'document_name': 'external > t > law > ' + hit[2], 'coordinate': hit[3]}],
                'source_ids': [hit[4]], 'reason': 'EXACT_DOCUMENT_COORDINATE'}
    return resolve


def session_with(sources):
    return S(matcher=S(documents={}), scope={'law', 'decree'}, tools=S(sources=sources))


def test_named_articles_in_open_questions_become_reads_and_failures_become_notes(monkeypatch):
    monkeypatch.setattr(sq, 'resolve', fake_resolve({
        '자본시장과 금융투자업에 관한 법률 시행령 제125조': ('decree', '2475', '자본시장과 금융투자업에 관한 법률 시행령', '제125조', 'article:125'),
        '상법 제341조의4': ('law', '1108', '상법', '제341조의4', 'article:341-4')}))
    executor = S(s=session_with({'article:125': {'document_id': 'decree'}, 'article:341-4': {'document_id': 'law'}, 'source:1': {'document_id': 'doc1'}}))
    v = {'answer_points': [], 'open_questions': [
        {'issue_refs': ['Q1'], 'kind': 'SOURCE', 'uncertainty': '자본시장과 금융투자업에 관한 법률 시행령 제125조 본문이 아직 확보되지 않았습니다.',
         'question': '제125조를 이어서 읽어볼까요?'},
        {'issue_refs': ['Q1'], 'kind': 'DECISION', 'uncertainty': '상속세 및 증여세법 제45조의6의 본문이 없습니다.',
         'question': '상법 제341조의4를 별도로 확인할까요?'}]}
    monkeypatch.setattr(sq, 'document_hits', fake_hits({'자본시장과 금융투자업에 관한 법률 시행령': 'decree', '상법': 'law', '상속세 및 증여세법': 'tax'}))
    rows, notes = g.named_article_reads(executor, v, [], SOURCES)
    assert [(r['id'], r['origin'], r['identity']) for r in rows] == [
        ('N1', 'NAMED', {'document_id': 'decree', 'source_id': 'article:125', 'unit_id': '2475'}),
        ('N2', 'NAMED', {'document_id': 'law', 'source_id': 'article:341-4', 'unit_id': '1108'})]
    assert rows[0]['label'] == '자본시장과 금융투자업에 관한 법률 시행령 · 제125조'
    by = {n['mention']: n['status'] for n in notes}
    assert by == {'자본시장과 금융투자업에 관한 법률 시행령 제125조': 'READ_SCHEDULED', '상속세 및 증여세법 제45조의6': 'NOT_IN_DOCUMENT',
                  '상법 제341조의4': 'READ_SCHEDULED'}
    # Already acquired articles are not added again. Since 2026-11-09 an already offered article
    # is returned as that offered location (same id) so the server reads it now; before, it was
    # read only if the answer also chose it (test_source_closure_reads.py).
    offered = [{'id': 'L1', 'label': 'x', 'origin': 'LOCATION', 'identity': {'document_id': 'law', 'source_id': 'article:341-4', 'unit_id': '1108'}}]
    rows2, notes2 = g.named_article_reads(executor, v, offered, SOURCES + [{'source_id': 'article:125'}])
    assert [(r['id'], r.get('named')) for r in rows2] == [('L1', True)]
    assert {n['status'] for n in notes2} == {'ALREADY_READ', 'NOT_IN_DOCUMENT', 'READ_SCHEDULED'}


def fake_hits(names):
    def hits(text, matcher):
        out = []
        for name, did in names.items():
            i = text.find(name)
            if i >= 0:
                out.append({'key': name, 'start': i, 'end': i + len(name), 'values': [did]})
        return sorted(out, key=lambda h: h['start'])
    return hits


def test_assess_reads_named_articles_now_and_tells_the_next_round(monkeypatch):
    monkeypatch.setattr(sq, 'resolve', fake_resolve({'상법 제341조의4': ('law', '1108', '상법', '제341조의4', 'article:341-4')}))
    monkeypatch.setattr(sq, 'document_hits', fake_hits({'상법': 'law', '상속세 및 증여세법': 'tax'}))
    v = value()
    v['open_questions'] = [{'issue_refs': ['Q1'], 'kind': 'DECISION', 'uncertainty': '상법 제341조의4를 아직 읽지 않았고 상속세 및 증여세법 제45조의6은 없습니다.',
                            'question': '상법 제341조의4를 확인할까요?'}]
    e, calls = execution(v)
    e.s.matcher = S(documents={}); e.s.scope = {'law'}; e.s.tools = S(sources={'article:341-4': {'document_id': 'law'}})
    result = g.assess(e, SOURCES, ISSUES, '자기주식 소각의무는?', [])
    reads = result['guided_reply']['proposed_reads']
    assert [(r['origin'], r['identity']['unit_id']) for r in reads] == [('NAMED', '1108')] and reads[0]['read_id'].startswith('R')
    lookup = result['guided_reply']['named_article_lookup']
    assert {n['mention']: n['status'] for n in lookup} == {'상법 제341조의4': 'READ_SCHEDULED', '상속세 및 증여세법 제45조의6': 'NOT_IN_DOCUMENT'}
    assert '를 아직' not in str(lookup)  # the note names the law, not the preceding clause
    assert any(k == 'GUIDED_ANSWER_NAMED_ARTICLES' and p['model_called'] is False for k, p in e.s.work.events)
    # The next answer round of the same request sees the lookup result instead of a repeated guess.
    g.assess(e, SOURCES, ISSUES, '자기주식 소각의무는? (다음 라운드)', [])
    data = calls[-1][1]
    assert data['named_article_lookup'][1] == {'mention': '상속세 및 증여세법 제45조의6', 'status': 'NOT_IN_DOCUMENT'}
    assert 'named_article_lookup' in g.PROMPT and 'NOT_IN_DOCUMENT' in g.PROMPT


def test_read_choices_offer_one_article_for_its_paragraph_units():
    locations = [{'identity': {'document_id': 'd', 'source_id': 's1', 'unit_id': '7'}, 'label': '상법 시행령 · 제34조의2(상장회사의 독립이사에 관한 등기)'},
                 {'identity': {'document_id': 'd', 'source_id': 's2', 'unit_id': '8'}, 'label': '상법 시행령 · 제34조의2(상장회사의 독립이사에 관한 등기)'},
                 {'identity': {'document_id': 'd', 'source_id': 's3', 'unit_id': '9'}, 'label': '상법 · 제383조(원수, 임기)'}]
    rows = g.read_choices([], locations)
    assert [(r['id'], r['label']) for r in rows] == [('L1', locations[0]['label']), ('L2', locations[2]['label'])]


def test_question_terms_drop_particles_and_form_words():
    terms = gn.question_terms('외규: 증권신고서 제출 시 1분기 검토보고서를 첨부하여야 하는가?\n(업무 문맥: IPO 단계의 재무서류 제출범위)')
    assert '하는가' not in terms and '문맥' not in terms and '업무' not in terms and '제출' in terms and '검토보고서' in terms
    assert gn.question_terms('외규: 주주총회 결의 요건') == ['주주총회', '결의', '요건']


def test_same_subject_incoming_links_stay_selectable():
    card = {'direction': 'INCOMING', 'citation_role': 'BORROWS', 'read_action': 'T1',
            'target': {'heading': '주식매수선택권의 행사'}, 'anchor': {'heading': '벤처기업의 주식매수선택권'}}
    other = {'direction': 'INCOMING', 'citation_role': 'BORROWS', 'read_action': 'T2',
             'target': {'heading': '위탁의 거부'}, 'anchor': {'heading': '자기주식의 취득ㆍ처분기준'}}
    assert cs.same_subject(card) and not cs.same_subject(other)
    # A question word in the heading also keeps the link (질문: 자기주식 소각 → 제5-9조 자기주식 처분기간).
    assert cs.same_subject({'target': {'heading': '자기주식 처분기간 등'}, 'anchor': {'heading': '취득ㆍ처분기준'}}, gn.question_terms('자기주식 소각의무의 내용은?'))
    actions = {'T1': {'action': 'READ_ARTICLES'}, 'T2': {'action': 'READ_ARTICLES'}}; listed = []
    kept = cs.list_only_incoming([card, other], actions, listed)
    assert kept == [card] and listed == [other] and 'T1' in actions and 'T2' not in actions
    assert 'SAME_SUBJECT_INCOMING' in cs.REASON_TEXT and cs.REASON_TEXT['SAME_SUBJECT_INCOMING'][1] is False


def cross_document_inv(blocks, names, scope=('r', 'law')):
    from test_unread_connection_labels import inv_with
    inv = inv_with([], evidence=[('s4-3', ['x1'])], names=names, blocks=blocks, scope=scope)
    inv.s.tools.sources.update({'s4-3': {'document_id': 'r', 'unit_id': 'u43'}, 'article:341-4': {'document_id': 'law', 'unit_id': '1108'}})
    inv.s.matcher.units = {('r', 'u43'): {'surface': '제4-3조', 'title': '사업보고서의 기재사항 등'}, ('law', '1108'): {'surface': '제341조의4', 'title': '자기주식의 소각의무 등'}}
    inv.s.matcher.stored_coordinates = {}
    inv.question = '자기주식 소각의무에 관한 신설 규정의 내용은?'
    inv.p.update(binding='b', turn=3, request_turn_start=1)
    inv.s.repo.events = []
    inv.s.repo.event = lambda k, v: inv.s.repo.events.append((k, v))
    return inv


def test_read_original_citing_another_law_by_name_offers_that_article(monkeypatch):
    blocks = {'x1': '⑨ 영 제170조제3항제1호나목에서 "금융위원회가 정하여 고시하는 서류"란 「상법」 제341조의4제4항에 따라 이사 전원이 기명날인한 자기주식보유처분계획의 사본을 말한다.'}
    inv = cross_document_inv(blocks, {'r': 'external > t > law > 증권의 발행 및 공시 등에 관한 규정', 'law': 'external > t > law > 상법'})
    monkeypatch.setattr(sq, 'document_hits', lambda text, matcher: [{'key': '상법', 'start': text.index('상법'), 'end': text.index('상법') + 2, 'values': ['law']}])
    known = {'s4-3': {'x1'}}
    scan = gn.scan_read_originals(inv, known)
    assert scan['cited'][('law', '제341조의4')] == ['증권의 발행 및 공시 등에 관한 규정 제4-3조']
    # "영 제170조" names the 시행령 of the law the rule declares, not the rule's own 제170조 (plan r5 4-1);
    # unresolved here, it is not recorded as the citing document's article.
    assert ('r', '제170조') not in scan['cited'] and ('r', '제341조의4') not in scan['cited']
    # The cited article of the other law becomes a readable location without any menu or search.
    monkeypatch.setattr(sq, 'coordinate_index', lambda matcher: {('law', '제341조의4'): ['1108']})
    inv.s.matcher._unit_sources = lambda did, uid: ['article:341-4']
    from semantic_runtime.legal_agent import unit_reading as ur
    monkeypatch.setattr(ur, 'blocks', lambda s, did, uid, extent: ['l1', 'l2'] if did == 'law' else [])
    # Since 2026-11-09 a cited article is offered only when this request can read it (tool_availability).
    from semantic_runtime.legal_agent import tool_availability as av
    monkeypatch.setattr(av, 'article_plan', lambda s, identity: (('hit', 'offer'), None))
    rows = gn.cited_locations(inv, scan['cited'], [], known, inv.s.matcher.units)
    assert [r['identity'] for r in rows] == [{'document_id': 'law', 'source_id': 'article:341-4', 'unit_id': '1108'}] and rows[0]['from_citation']
    assert '제341조의4' in rows[0]['label'] and '상법' in rows[0]['label']
    assert any(v.get('from_citation') for v in inv.p['guided_locations'].values())
    assert any(k == 'CITED_LOCATIONS_OFFERED' and p['model_called'] is False for k, p in inv.s.repo.events)
