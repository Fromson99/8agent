"""인용 관계별 처리: 위임·구체화·적용 특례 판정, 준용 대상, 역방향 문장 카드, 질문 낱말 우선 정방향."""
from semantic_runtime.legal_agent import citation_roles as cr
from semantic_runtime.legal_agent import connection_scope as cs

LAW = 'external > financial_team > law > 소득세법'
DECREE = 'external > financial_team > law > 소득세법 시행령'


def rel(text, mention, **kw):
    a = text.index(mention)
    return cr.role(text, a, a + len(mention)), cr.relation(text, a, a + len(mention), **kw)


def test_existing_pair_roles_stay():
    assert rel('제434조(정관변경의 특별결의) 제433조제1항의 결의는 출석한 주주의 의결권의 3분의 2 이상의 수로써 하여야 한다.', '제433조제1항')[0] == cr.SPECIFIES
    assert rel('②전항의 경우에는 제363조의 규정을 적용하지 아니한다.', '제363조')[0] == cr.EXCEPTION
    assert rel('① 회사가 다음 각 호의 행위를 할 때에는 제434조에 따른 결의가 있어야 한다.', '제434조') [0] == cr.BORROWS
    assert rel('제1조(경과조치) 제19조제2항의 개정규정에도 불구하고 종전의 규정에 따른다.', '제19조제2항')[0] == cr.TRANSITIONAL


def test_delegation_definition_reads_each_item_frame():
    text = '⑥법 제97조제2항제2호 각 목 외의 부분 본문에서 "대통령령으로 정하는 금액"이란 다음 각 호의 금액을 말한다.'
    assert rel(text, '제97조제2항제2호 ', citing_document=DECREE, cited_document=LAW)[0] == cr.SPECIFIES
    text = '⑪법 제97조제7항 각 호 외의 부분 본문에서 "대통령령으로 정하는 방법"이란 다음 각 호의 어느 하나에 해당하는 방법을 말한다.'
    assert rel(text, '제97조제7항 ')[0] == cr.SPECIFIES


def test_cited_rule_as_subject_and_application_method_specify():
    assert rel('⑩ 법 제97조제1항제1호가목은 다음 각 호에 따라 적용한다.', '제97조제1항제1호가목')[0] == cr.SPECIFIES
    assert rel('받은 자산에 대하여 법 제97조제1항제1호가목을 적용할 때에는 평가한 가액을 취득당시의 실지거래가액으로 본다.', '제97조제1항제1호가목')[0] == cr.SPECIFIES
    # A mid-sentence "제X조는" is not the sentence subject.
    assert rel('회사는 필요한 경우 제5조는 물론 제6조에 따른 절차를 거친다.', '제5조')[0] == cr.BORROWS


def test_case_specific_application_is_a_card_kind_not_a_role():
    text = ('⑬주식매수선택권을 행사하여 취득한 주식을 양도하는 때에는 주식매수선택권을 행사하는 당시의 시가를 '
            '법 제97조제1항제1호의 규정에 의한 취득가액으로 한다. <신설 2000.12.29>')
    role, relation = rel(text, '제97조제1항제1호', citing_document=DECREE, cited_document=LAW)
    assert role == cr.BORROWS and relation['kind'] == cr.APPLIES_CASE
    assert '주식매수선택권을 행사하는 당시의 시가' in relation['sentence'] and len(relation['sentence']) <= 210


def test_lower_rule_reuse_is_implementing_only_across_rank():
    text = '①법 제97조제1항제1호가목에 따른 취득에 든 실지거래가액은 다음 각 호의 금액을 합한 것으로 한다.'
    assert rel(text, '제97조제1항제1호가목', citing_document=DECREE, cited_document=LAW)[1]['kind'] == cr.IMPLEMENTS
    assert rel(text, '제97조제1항제1호가목', citing_document=LAW, cited_document=LAW)[1]['kind'] == cr.BORROWS
    assert rel(text, '제97조제1항제1호가목', citing_document=LAW, cited_document=DECREE)[1]['kind'] == cr.BORROWS
    assert rel(text, '제97조제1항제1호가목', citing_document='x > 금융투자업규정', cited_document='x > 자본시장과 금융투자업에 관한 법률', declared_name=True)[1]['kind'] == cr.IMPLEMENTS
    assert cr.lower_regulation('a > 유가증권시장 상장규정 시행세칙', 'a > 유가증권시장 상장규정')
    assert cr.lower_regulation('a > 소득세법 시행규칙 > 별표서식 > [별표 1]', 'a > 소득세법 시행령')
    assert not cr.lower_regulation('a > 상법', 'a > 상법 시행령') and not cr.lower_regulation('a > 상법', 'a > 소득세법')


def test_mutatis_subject_both_orders_and_long_enumeration_tail():
    text = '제415조(준용규정) 제382조제2항, 제382조의4, 제385조, 제386조, 제388조, 제400조, 제401조, 제403조부터 제406조까지, 제406조의2 및 제407조는 감사에 준용한다.'
    role, relation = rel(text, '제388조')
    assert role == cr.MUTATIS and relation['subject'] == '감사' and relation['sentence'].endswith('감사에 준용한다.')
    assert rel('② 투자회사의 주주에 관하여는 「금융회사의 지배구조에 관한 법률」 제33조를 준용한다.', '제33조')[1]['subject'] == '투자회사의 주주'
    assert rel('⑤ 제1항에 따라 조직을 변경하는 경우 제340조제3항 및 제606조를 준용한다.', '제606조')[1]['subject'] is None
    assert cr.subject('제434조에 따른 결의가 있어야 한다.', 0, 5) is None


def test_bad_span_is_borrows_and_empty_sentence():
    assert cr.role('abc', 2, 2) == cr.BORROWS and cr.sentence(None, 0, 1) == ''
    assert cr.relation('abc', 5, 9)['kind'] == cr.BORROWS


def card(ident, direction, role, kind, sentence, *, read=True, heading='제1조 무관', subject=None, already=False):
    return {'direction': direction, 'citation_role': role, 'already_read': already,
            'citation_relation': {'kind': kind, 'subject': subject, 'sentence': sentence},
            'read_action': ident if read else None, 'target': {'heading': heading}, 'anchor': {'heading': '제97조 양도소득의 필요경비 계산'}}


def test_reverse_sentence_cards_stay_selectable_question_words_first():
    cards = [card('T1', 'INCOMING', cr.BORROWS, cr.BORROWS, '제97조에 따른 필요경비를 공제하여 계산'),
             card('T2', 'INCOMING', cr.BORROWS, cr.IMPLEMENTS, '법 제97조제1항제1호가목에 따른 취득에 든 실지거래가액은'),
             card('T3', 'INCOMING', cr.BORROWS, cr.APPLIES_CASE, '주식매수선택권을 행사하여 취득한 주식을 양도하는 때에는 … 취득가액으로 한다.'),
             card('T4', 'INCOMING', cr.MUTATIS, cr.MUTATIS, '제97조는 감사에 준용한다.', subject='감사'),
             card('T5', 'INCOMING', cr.SPECIFIES, cr.SPECIFIES, '법 제97조제1항제2호에서 "대통령령으로 정하는 것"이란'),
             card('T6', 'OUTGOING', cr.BORROWS, cr.BORROWS, '제94조제1항 각 호의 자산')]
    actions = {c['read_action']: {} for c in cards}; listed = []
    kept = cs.list_only_incoming(cards, actions, listed, {'주식매수선택권', '취득가액', '양도'})
    assert [c['read_action'] for c in kept] == ['T5', 'T6', 'T3', 'T2', 'T4']
    assert [c['read_action'] for c in listed] == ['T1'] and 'T1' not in actions and {'T2', 'T3', 'T4'} <= set(actions)
    notes = {c['read_action']: c.get('citation_note') for c in kept}
    assert notes['T5'] is None and notes['T6'] is None
    assert '특정한 경우' in notes['T3'] and '하위 규정' in notes['T2'] and '대상: 감사.' in notes['T4']
    assert all('차감되지 않는다' in notes[k] for k in ('T2', 'T3', 'T4'))


def test_sentence_cards_are_bounded_and_skip_unreadable_or_read():
    cards = [card('T%d' % i, 'INCOMING', cr.BORROWS, cr.IMPLEMENTS, '법 제97조에 따른 사항 %d' % i) for i in range(cs.SENTENCE_CARD_LIMIT + 3)]
    cards += [card('U1', 'INCOMING', cr.MUTATIS, cr.MUTATIS, '준용한다', read=False), card('U2', 'INCOMING', cr.MUTATIS, cr.MUTATIS, '준용한다', already=True)]
    actions = {c['read_action']: {} for c in cards if c['read_action']}; listed = []
    kept = cs.list_only_incoming(cards, actions, listed, ())
    assert len(kept) == cs.SENTENCE_CARD_LIMIT and len(listed) == 5
    assert [c['read_action'] for c in kept] == ['T%d' % i for i in range(cs.SENTENCE_CARD_LIMIT)]
    assert 'T%d' % cs.SENTENCE_CARD_LIMIT not in actions and 'U2' not in actions
    # The same read offered by two sentences takes one place.
    twice = [card('T0', 'INCOMING', cr.BORROWS, cr.IMPLEMENTS, '법 제97조제1항 및 제2항의 금액') for _ in range(2)]
    twice += [card('T%d' % i, 'INCOMING', cr.BORROWS, cr.IMPLEMENTS, '법 제97조에 따른 사항') for i in range(1, cs.SENTENCE_CARD_LIMIT + 1)]
    actions = {c['read_action']: {} for c in twice}; listed = []
    kept = cs.list_only_incoming(twice, actions, listed, ())
    assert len(kept) == cs.SENTENCE_CARD_LIMIT + 1 and [c['read_action'] for c in listed] == ['T%d' % cs.SENTENCE_CARD_LIMIT]


def test_automatic_reads_take_question_sentences_first(monkeypatch):
    monkeypatch.setattr(cs, 'read_plan', lambda group, link: None)
    monkeypatch.setattr(cs, 'endpoint_key', lambda group, link: link['id'])
    def link(ident, role, sentence, order):
        return {'id': ident, 'citation_role': role, 'citation_relation': {'kind': role, 'sentence': sentence}, 'witness_source_order': order}
    out = [link('o%d' % i, cr.BORROWS, '제%d조에 따른 통지' % i, i) for i in range(8)]
    out[7]['citation_relation']['sentence'] = '제7조에 따른 주식매수선택권 행사'
    inc = [link('i1', cr.SPECIFIES, '법 제1조에서 "대통령령으로 정하는 것"이란', 0), link('i2', cr.EXCEPTION, '제1조에도 불구하고', 1),
           link('i3', cr.BORROWS, '제1조에 따른', 2)]
    directory = {'groups': [{'direction': 'OUTGOING', 'connections': out}, {'direction': 'INCOMING', 'connections': inc}]}
    rows = cs.chain_rows(directory, forward_only=False, terms={'주식매수선택권'})
    assert [r['endpoint'] for r in rows] == ['o7', 'o0', 'o1', 'o2', 'o3', 'o4', 'i2', 'i1']
    assert not any(r['matched'] for r in rows)
    assert [r['endpoint'] for r in cs.chain_rows(directory, forward_only=False)][:3] == ['o0', 'o1', 'o2']
    assert all(r['outgoing'] for r in cs.chain_rows(directory, forward_only=True, terms={'주식매수선택권'}))


def test_system_reads_reverse_links_whose_subject_or_case_is_the_question(monkeypatch):
    monkeypatch.setattr(cs, 'read_plan', lambda group, link: None)
    monkeypatch.setattr(cs, 'endpoint_key', lambda group, link: link['id'])
    def link(ident, role, kind, sentence, subject=None):
        return {'id': ident, 'citation_role': role, 'citation_relation': {'kind': kind, 'subject': subject, 'sentence': sentence}, 'witness_source_order': 0}
    inc = [link('m1', cr.MUTATIS, cr.MUTATIS, '제388조는 유한회사의 이사에 준용한다.', '유한회사의 이사'),
           link('m2', cr.MUTATIS, cr.MUTATIS, '제388조는 감사에 준용한다.', '감사'),
           link('m3', cr.MUTATIS, cr.MUTATIS, '이 경우 제388조를 준용한다.'),
           link('c1', cr.BORROWS, cr.APPLIES_CASE, '주식매수선택권을 행사하여 취득한 주식을 양도하는 때에는 … 취득가액으로 한다.'),
           link('c2', cr.BORROWS, cr.APPLIES_CASE, '자사주를 양도하는 경우에는 … 취득가액으로 한다.'),
           link('c3', cr.BORROWS, cr.APPLIES_CASE, '합병의 경우에는 … 가액으로 한다.'),
           link('b1', cr.BORROWS, cr.IMPLEMENTS, '법 제388조에 따른 감사 보수'),
           link('p1', cr.SPECIFIES, cr.SPECIFIES, '제388조의 보수는')]
    directory = {'groups': [{'direction': 'INCOMING', 'connections': inc}]}
    # 감사 질문: 대상어가 질문 낱말인 준용만. "이사회"는 "유한회사의 이사"와 맞지 않는다.
    rows = cs.chain_rows(directory, forward_only=False, terms={'감사', '보수', '이사회', '위임할'})
    assert [(r['endpoint'], r['matched']) for r in rows] == [('m2', True), ('p1', False)]
    # 주식매수선택권 질문: 질문 낱말이 둘 이상 든 적용 특례, 많이 겹치는 순, 2개까지. 시행 세부는 읽지 않는다.
    rows = cs.chain_rows(directory, forward_only=False, terms={'주식매수선택권', '취득가액', '양도'})
    assert [r['endpoint'] for r in rows] == ['c1', 'c2', 'p1']
    assert cs.chain_rows(directory, forward_only=True, terms={'감사'}) == []
    assert not cs.question_match(inc[6], {'감사', '보수'}) and not cs.question_match(inc[2], {'감사'})
    assert cs.CHAIN_LIMITS['matched_incoming'] == 2
