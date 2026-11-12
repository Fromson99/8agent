"""Unread connection notes name what was actually left unread (R5 display findings, 2026-11-06).

1) An article some of whose text was read is listed as its unread part only.
2) A target in a document the answer did not read carries the document name.
3) Paragraph units of one article are one entry, not "제9조, 제9조, 제9조".
4) Siblings under a chapter (no section level) are "같은 장", not "같은 절".
"""
from types import SimpleNamespace as S

from test_guided_continue_bounds import section_session


def inv_with(skipped, list_only=None, *, evidence=(), names=None, blocks=None, scope=('d', 'e')):
    s = section_session({})
    if blocks:
        base = s.store.source
        s.store = S(source=lambda did, bid: {'text': blocks[bid]} if bid in blocks else base(did, bid))
    s.matcher.documents = dict(names or {})
    s.scope = set(scope)
    s.tools.sources.update({'e9a': {'document_id': 'e', 'unit_id': 'e9-1'}, 'e9b': {'document_id': 'e', 'unit_id': 'e9-2'},
                            'e190': {'document_id': 'e', 'unit_id': 'e190'}})
    s.repo = S(evidence=lambda: [{'source_id': sid, 'spans': [{'block_id': b} for b in bids]} for sid, bids in evidence])
    return S(s=s, p={'role_chain_directories': {'k': {'skipped': list(skipped)}},
                     'list_only_connections': dict(list_only or {})})


def chain(sid, did, uid, block_ids, label=None, **extra):
    row = {'kind': 'CONNECTION', 'role': 'SPECIFIES', 'outgoing': False, 'anchor_label': '제434조 정관변경의 특별결의',
           'identity': {'source_id': sid, 'document_id': did, 'unit_id': uid}, 'block_ids': list(block_ids),
           'reason': 'CHAIN_COUNT_LIMIT', **extra}
    if label:
        row['label'] = label
    return row


def test_partly_read_article_is_listed_as_its_unread_part_only():
    from semantic_runtime.legal_agent import connection_scope as cs
    blocks = {'p1': '제433조 ① 정관의 변경은 주주총회의 결의에 의하여야 한다.', 'p2': '② 정관의 변경에 관한 의안의 요령은 제363조에 따른 통지에 기재하여야 한다.'}
    inv = inv_with([chain('s제433조', 'd', '제433조', ['p1', 'p2'])], evidence=[('s제433조', ['p1'])], blocks=blocks)
    row, = cs.unread_connections(inv)['entries']
    assert row['target_label'] == '제433조(정관변경의 방법) 중 읽지 않은 부분' and row['partially_read'] is True
    assert row['text'] == blocks['p2']  # the read paragraph is not repeated as "unread"
    # Fully read: not listed at all (unchanged behaviour).
    full = inv_with([chain('s제433조', 'd', '제433조', ['p1', 'p2'])], evidence=[('s제433조', ['p1', 'p2'])], blocks=blocks)
    assert cs.unread_connections(full)['entries'] == []


def test_other_document_targets_carry_the_document_name_and_paragraph_units_merge():
    from semantic_runtime.legal_agent import connection_scope as cs, guided_answer as ga
    blocks = {'x1': '① 이 영에서 사용하는 용어의 뜻은 다음과 같다.', 'x2': '② 제1항에도 불구하고 …', 'x3': '제190조 집합투자기구 …'}
    list_only = {
        'a': {'role': 'MUTATIS', 'anchor_label': '제8조 내부회계관리제도의 운영 등',
              'identity': {'source_id': 'e9a', 'document_id': 'e', 'unit_id': 'e9-1'}, 'block_ids': ['x1'], 'label': '제9조 ①정의'},
        'b': {'role': 'MUTATIS', 'anchor_label': '제8조 내부회계관리제도의 운영 등',
              'identity': {'source_id': 'e9b', 'document_id': 'e', 'unit_id': 'e9-2'}, 'block_ids': ['x2'], 'label': '제9조 ②정의'}}
    names = {'d': '상법', 'e': '주식회사 등의 외부감사에 관한 법률 시행령'}
    inv = inv_with([chain('e190', 'e', 'e190', ['x3'], label='제190조 집합투자기구')], list_only,
                   evidence=[('s제433조', ['0'])], names=names, blocks=blocks)
    rows = cs.unread_connections(inv)['entries']
    labels = [r['target_label'] for r in rows]
    assert labels == ['「주식회사 등의 외부감사에 관한 법률 시행령」 제190조(집합투자기구)',
                      '「주식회사 등의 외부감사에 관한 법률 시행령」 제9조(정의)']
    # A target in a document the answer did read keeps the short label.
    same = inv_with([chain('s제435조', 'd', '제435조', ['2'])], evidence=[('s제433조', ['0'])], names=names)
    assert [r['target_label'] for r in cs.unread_connections(same)['entries']] == ['제435조(종류주주총회)']
    assert [r['target_label'] for r in ga.unread_reply(rows, [])] == labels  # 항 단위 중복 없이 한 줄씩(화면 칸에 그대로)


def test_chapter_siblings_are_named_same_chapter():
    from semantic_runtime.legal_agent import connection_scope as cs, guided_answer as ga
    assert [cs.section_level(x) for x in ('제4장 내부통제 및 위험관리 등', '제5절 정관의 변경', '제2관 소집', '제3편 회사', '부칙')] == \
        ['장', '절', '관', '편', '절']
    s = section_session({'제435조': '제435조 회사가 정관을 변경함으로써 …'})
    s.matcher.units[('d', 'sec')] = {'surface': '제4장', 'title': '제4장 내부통제 및 위험관리 등', 'parent': None, 'span': [0, 99]}
    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(cs.ur, 'blocks', lambda s, did, uid, extent: [str(int(uid[1:4]) - 433)] if uid.startswith('제43') else ['9'])
    try:
        rows = cs.section_neighbors(S(s=s), {'members': [{'source_id': 's제433조'}]})
    finally:
        mp.undo()
    assert rows and {r['section_level'] for r in rows} == {'장'}
    skip = {'kind': 'SECTION', 'role': 'SAME_SECTION', 'outgoing': False, 'anchor_label': '제433조 정관변경의 방법',
            'section': '제4장 내부통제 및 위험관리 등', 'section_level': '장', 'label': '제436조 준용규정', 'terms': ['내부통제'],
            'identity': {'source_id': 's제436조', 'document_id': 'd', 'unit_id': '제436조'}, 'block_ids': ['3'],
            'reason': 'SECTION_TERMS_NOT_MATCHED'}
    row, = cs.unread_connections(inv_with([skip], evidence=[('s제433조', ['0'])]))['entries']
    assert row['relation_text'] == '같은 장의 조문' and row['section_level'] == '장'
    assert row['reason'].startswith('같은 장 조문이지만 앞부분에 장 제목의 핵심 표현') and '같은 절' not in row['reason']
    assert ga.unread_reply([row], [])[0]['section_level'] == '장'


def test_rows_saved_before_the_level_field_read_it_from_the_heading():
    from semantic_runtime.legal_agent import guided_answer as ga
    # Saved MAIN177 reply rows (ADR-1458 cm-007) have no section_level: "제1장 통 칙" is a chapter.
    old = [{'from_label': '제26조(신규상장 의무보유)', 'target_label': '제1조(목적)', 'relation': 'SAME_SECTION', 'section': '제1장 통 칙',
            'relation_text': '같은 절의 조문', 'reason': '규정의 목적을 명시한 조항이라서', 'judged_unneeded': True,
            'reason_origin': 'MODEL_NOTE', 'list_only': False}]
    assert ga.section_level(old[0]) == '장'
    assert ga.section_level({'section': '제5절 정관의 변경'}) == '절' and ga.section_level({}) == '절'
