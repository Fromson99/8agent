"""답변 근거가 인용한 조문 읽기, 하위 규정 읽기 좁히기, 읽기 순서(ADR-1470 누락 대응)."""
from semantic_runtime.legal_agent import guided_answer as ga
from semantic_runtime.legal_agent import guided_navigation as gn


def option(ident, source, block='10', start=0, end=200, text=''):
    return {'id': ident, 'source_id': source, 'document_id': 'D', 'block_id': block, 'start_cp': start, 'end_cp': end, 'text': text}


def location(ident, label, **hints):
    return {'id': ident, 'label': label, 'origin': 'LOCATION', 'identity': {'document_id': 'D', 'source_id': 's-' + ident, 'unit_id': ident}, **hints}


def context(source, start, text, block='10'):
    return {'source_id': source, 'block_id': block, 'start': start, 'text': text}


def test_reads_what_the_answer_evidence_cites_inside_line_first():
    options = [option('S1', 'a13', start=0, end=120), option('S2', 'a26', start=0, end=80)]
    value = {'answer_points': [{'evidence_refs': ['S1'], 'text': '상장주선인은 공모가격으로 주식을 취득하여 보유하여야 한다.'}]}
    reads = [location('L1', '인수규정 제5조', cited_contexts=[context('a13', 40, '인수규정 제5조에 따른 공모가격으로 취득')]),
             location('L2', '규정 제31조', cited_contexts=[context('a13', 300, '제31조제1항제3호마목에 따른 신속이전기업은 제외한다')]),
             location('L3', '규정 제40조', cited_contexts=[context('a26', 10, '제40조에 따른 공모가격으로 취득')]),
             location('L4', '규정 제50조', cited_contexts=[context('a13', 500, '제50조에 따른 상장주선인 공모가격 취득 보유')]),
             location('L5', '규정 제60조', matched_terms=['주식'], cited_by=['제13조'])]
    rows = ga.evidence_cited_rows(reads, set(), value, options, {'의무인수'})
    # L1: 근거 줄 안의 인용. L4: 같은 근거 조문, 답변 낱말 2개 이상. L2: 겹침 부족. L3: 답변이 근거로 쓰지 않은 조문.
    assert [(k, r['id']) for k, r in rows] == [('EVIDENCE_CITED', 'L1'), ('EVIDENCE_CITED', 'L4')]
    assert ga.evidence_cited_rows(reads, {'L1'}, value, options) == [('EVIDENCE_CITED', reads[3])]
    assert ga.evidence_cited_rows(reads, set(), {'answer_points': []}, options) == []


def test_evidence_cited_is_bounded_and_question_words_count():
    options = [option('S1', 'a1', start=0, end=50)]
    value = {'answer_points': [{'evidence_refs': ['S1'], 'text': '설명'}]}
    reads = [location('L%d' % i, '제%d조' % i, cited_contexts=[context('a1', 100 + i, '주식매수선택권 행사 취득가액 제%d조' % i)]) for i in range(6)]
    rows = ga.evidence_cited_rows(reads, set(), value, options, {'주식매수선택권', '취득가액'})
    assert [r['id'] for _, r in rows] == ['L0', 'L1', 'L2'] and ga.SERVER_READ_LIMITS['evidence_cited'] == 3


def test_lower_rule_reads_take_the_sentence_with_more_question_words():
    reads = [location('L1', '시행령 제10조', specifies=['법 제5조'], specifies_score=1),
             location('L2', '시행령 제163조', specifies=['법 제97조'], specifies_score=6),
             location('L3', '시행령 제20조', specifies=['법 제5조'], specifies_score=2),
             location('L4', '제434조', cited_by=['제433조'], matched_terms=['결의'])]
    assert [(k, r['id']) for k, r in ga.server_read_rows(reads, set())] == [('SPECIFIES', 'L2'), ('SPECIFIES', 'L3'), ('CITED', 'L4')]


def test_internal_hints_are_carried_but_not_shown_to_the_model():
    loc = {'identity': {'document_id': 'D', 'source_id': 's', 'unit_id': '1'}, 'label': '규정 제5조', 'cited_by': ['제13조'],
           'cited_contexts': [context('a13', 1, '제5조')], 'specifies': ['법 제1조'], 'specifies_score': 3}
    row = ga.read_choices([], [loc])[0]
    assert row['cited_contexts'] and row['specifies_score'] == 3
    assert not set(ga.INTERNAL_HINTS) & set(ga.LOCATION_HINTS)
    shown = {k: row[k] for k in ga.LOCATION_HINTS if row.get(k)}
    assert 'cited_contexts' not in shown and 'specifies_score' not in shown


def test_prompts_say_the_mode_prefix_is_not_a_document_and_keep_earlier_points():
    assert "문서 이름이 아니다" in gn.PROMPT and "'외규:'" in gn.PROMPT
    assert "문서 이름이 아니다" in ga.PROMPT
    assert '직전 초안의 설명' in ga.PROMPT and '바꿔 쓰지 않는다' in ga.PROMPT
    from semantic_runtime.legal_agent import request_entry
    assert "subject" in request_entry.ENTRY_SCOPE_PROMPT and "조회 방식 표시" in request_entry.ENTRY_SCOPE_PROMPT
    assert gn.VECTOR_TOP == 30 and ga.VECTOR_REQUEST_LIMIT == 4


def test_first_screen_reads_are_nearest_first():
    reads = [location('L1', '제1조', vector_rank=2, matched_terms=['주식']),
             location('L2', '제2조', vector_rank=25, matched_terms=['주식매수선택권', '취득가액']),
             location('L3', '제3조', vector_rank=1), location('L4', '제4조', vector_rank=3, matched_terms=['양도'])]
    assert [r['id'] for r in ga.vector_title_reads({'next_reads': []}, reads)] == ['L1', 'L4']
    assert [r['id'] for r in ga.vector_title_reads({'next_reads': ['L1']}, reads)] == ['L4', 'L2']


class _S:
    def __init__(self, **kw): self.__dict__.update(kw)


def _scoped_inv(monkeypatch, *, active=True, citing_text='상장주선인은 「증권 인수업무 등에 관한 규정」 제5조에 따른 공모가격으로 취득한다.'):
    from semantic_runtime.legal_agent import query_scope as qs, evidence_inventory as inventory
    granted = []
    monkeypatch.setattr(qs, 'active', lambda s: {'hash': 'h', 'targets': []} if active else None)
    monkeypatch.setattr(qs, 'grant', lambda s, sid, blocks, *, witness: granted.append((sid, list(blocks), witness)))
    monkeypatch.setattr(inventory, 'acquired_records', lambda p, **_: {'g': {'evidence': [{'source_id': 'kosdaq:13', 'spans': [{'block_id': 'b7'}]}]}})
    sources = {'kosdaq:13': {'document_id': 'kosdaq', 'unit_id': '13', 'blocks': [{'block_id': 'b7'}]},
               'rule:5': {'document_id': 'rule', 'unit_id': '5', 'blocks': [{'block_id': 'r1'}, {'block_id': 'r2'}]},
               'decree:163': {'document_id': 'decree', 'unit_id': '163', 'blocks': [{'block_id': 'd1'}]}}
    texts = {('kosdaq', 'b7'): citing_text, ('decree', 'd1'): '법 제13조제1항에서 "대통령령으로 정하는 것"이란'}
    s = _S(tools=_S(sources=sources), scope={'kosdaq', 'rule', 'decree'}, store=_S(source=lambda did, bid: {'text': texts.get((did, bid), '')}),
           matcher=_S(units={('rule', '5'): {'surface': '제5조'}, ('kosdaq', '13'): {'surface': '제13조'}, ('decree', '163'): {'surface': '제163조'}}))
    return _S(s=s, p={}), granted


def test_a_cited_article_is_readable_despite_a_narrowed_direct_scope(monkeypatch):
    inv, granted = _scoped_inv(monkeypatch)
    identity = {'document_id': 'rule', 'source_id': 'rule:5', 'unit_id': '5'}
    link = {'kind': 'TEXT_CITATION', 'source_id': 'kosdaq:13', 'block_id': 'b7'}
    assert gn.grant_connected_read(inv, identity, link) is None
    assert granted and granted[0][0] == 'rule:5' and granted[0][1] == ['r1', 'r2'] and granted[0][2]['kind'] == 'ANSWER_STAGE_CONNECTION'
    # A lower rule whose own text names the acquired article it specifies.
    lower = {'kind': 'LOWER_RULE', 'anchor_source_id': 'kosdaq:13', 'anchor_unit_id': '13'}
    assert gn.grant_connected_read(inv, {'document_id': 'decree', 'source_id': 'decree:163', 'unit_id': '163'}, lower) is None and len(granted) == 2


def test_connection_grant_needs_a_verified_citation_and_the_authorization(monkeypatch):
    identity = {'document_id': 'rule', 'source_id': 'rule:5', 'unit_id': '5'}
    inv, granted = _scoped_inv(monkeypatch, citing_text='상장주선인은 공모가격으로 취득한다.')  # the acquired block does not name 제5조
    assert gn.grant_connected_read(inv, identity, {'kind': 'TEXT_CITATION', 'source_id': 'kosdaq:13', 'block_id': 'b7'}) == 'CONNECTION_NOT_VERIFIED'
    inv, granted = _scoped_inv(monkeypatch)
    assert gn.grant_connected_read(inv, identity, {'kind': 'TEXT_CITATION', 'source_id': 'kosdaq:13', 'block_id': 'b9'}) == 'CONNECTION_NOT_VERIFIED'  # not an acquired block
    inv.s.scope = {'kosdaq'}
    assert gn.grant_connected_read(inv, identity, {'kind': 'TEXT_CITATION', 'source_id': 'kosdaq:13', 'block_id': 'b7'}) == 'CONNECTION_TARGET_OUTSIDE_AUTHORIZATION'
    assert granted == []
    inv, granted = _scoped_inv(monkeypatch, active=False)  # no narrowed scope: nothing to grant
    assert gn.grant_connected_read(inv, identity, {'kind': 'TEXT_CITATION', 'source_id': 'kosdaq:13', 'block_id': 'b7'}) is None and granted == []
    assert gn.grant_connected_read(inv, identity, None) is None


def test_navigation_prompt_asks_only_what_the_user_alone_can_answer():
    assert '사용자만 아는 사실' in gn.PROMPT and '각각 읽어 함께 답한다' in gn.PROMPT and '더 읽을지' in gn.PROMPT
