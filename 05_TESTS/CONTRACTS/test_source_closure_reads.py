"""Server reads before the guided answer is final (2026-11-09, financial CM 51 missed articles).

1) The answer's named articles were never read: the completion executor's own session has no
   matcher, so every lookup stopped at NO_MATCHER and was dropped without a note (cm-051 asked
   "자본시장과 금융투자업에 관한 법률 시행규칙 제14조제1항의 본문을 이어서 확인해 볼까요?").
   Now the request's source session is used, the trimmed law-name mention is resolved, answer
   points are scanned too and every failure is kept.
2) A lower rule that specifies a read article (시행령 제11조의3 → 법 제16조의3 "대통령령으로 정하는")
   is found from the read article's connection directory and read by the server.
3) An article that the read originals cite by number and whose title holds a question word
   (유가증권시장 상장규정 제13조 cited by 시행세칙 제9조) is read by the server.
4) The answer asks the user only what the user can answer; it does not ask to read or search.
"""
from copy import deepcopy
from types import SimpleNamespace as S

from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import guided_answer as g, guided_navigation as gn, structure_query as sq
from semantic_runtime.legal_agent import connection_scope as cs, evidence_inventory as inventory
from test_guided_answer import ISSUES, SOURCES, OPTIONS, execution, value
from test_named_article_reads import fake_resolve, fake_hits


def loc(i, label, **hints):
    return {'identity': {'document_id': 'd' + str(i), 'source_id': 's' + str(i), 'unit_id': str(i)}, 'label': label, **hints}


def test_named_reads_use_the_request_source_session_not_the_executor_session(monkeypatch):
    monkeypatch.setattr(sq, 'resolve', fake_resolve({'자본시장과 금융투자업에 관한 법률 시행규칙 제14조':
        ('rule', '125', '자본시장과 금융투자업에 관한 법률 시행규칙', '제14조', 'article:14')}))
    monkeypatch.setattr(sq, 'document_hits', fake_hits({'자본시장과 금융투자업에 관한 법률 시행규칙': 'rule'}))
    v = value()
    v['open_questions'][0]['uncertainty'] = ('증권 인수업무 등에 관한 규정 제6조제2항이 준용하는 자본시장과 금융투자업에 관한 법률 '
                                             '시행규칙 제14조제1항의 본문은 이번 조사에서 확인하지 못했습니다.')
    e, calls = execution(v)
    # As in the service: the executor session has no matcher; the request's sources session has it.
    e.s.sources.matcher = S(documents={}); e.s.sources.scope = {'rule'}
    e.s.sources.tools = S(sources={'article:14': {'document_id': 'rule'}})
    assert g.source_session(e) is e.s.sources
    result = g.assess(e, SOURCES, ISSUES, '보유비율은 어떻게 산정하는가?', [])
    reads = result['guided_reply']['proposed_reads']
    assert [(r['origin'], r['identity']['unit_id']) for r in reads] == [('NAMED', '125')]
    lookup = {n['mention']: n['status'] for n in result['guided_reply']['named_article_lookup']}
    assert lookup['자본시장과 금융투자업에 관한 법률 시행규칙 제14조'] == 'READ_SCHEDULED'
    event = next(p for k, p in e.s.work.events if k == 'GUIDED_ANSWER_NAMED_ARTICLES')
    assert event['session'] == 'sources' and event['model_called'] is False


def test_trimmed_mention_is_resolved_before_the_raw_fragment(monkeypatch):
    asked = []
    def resolve(text, matcher, scope, **_):
        asked.append(text)
        return {'status': 'MATCH', 'pairs': [{'document_id': 'rule', 'unit_id': '125', 'document_name': 'x > 시행규칙', 'coordinate': '제14조'}],
                'source_ids': ['article:14'], 'reason': 'EXACT_DOCUMENT_COORDINATE'}
    monkeypatch.setattr(sq, 'resolve', resolve)
    monkeypatch.setattr(sq, 'document_hits', fake_hits({'시행규칙': 'rule'}))
    session = S(matcher=S(documents={}), scope={'rule'}, tools=S(sources={'article:14': {'document_id': 'rule'}}))
    identity, failure, mention = g.resolve_named_article(session, '제2항이 준용하는 시행규칙 제14조')
    assert failure is None and asked == ['시행규칙 제14조'] and mention.endswith('제14조')


def test_answer_points_are_scanned_and_every_failure_is_a_note(monkeypatch):
    monkeypatch.setattr(sq, 'resolve', fake_resolve({'상법 제413조': ('law', '413', '상법', '제413조', 'article:413')}))
    monkeypatch.setattr(sq, 'document_hits', fake_hits({'상법': 'law', '모의법': 'mock'}))
    v = value(open=False)
    v['answer_points'][0]['text'] = '감사의 보수는 상법 제413조를 함께 보아야 하고 모의법 제9조와도 관련됩니다.'
    e, _ = execution(v)
    e.s.matcher = S(documents={}); e.s.scope = {'law'}; e.s.tools = S(sources={'article:413': {'document_id': 'law'}})
    rows, notes = g.named_article_reads(e, v, [], SOURCES)
    assert [r['identity']['unit_id'] for r in rows] == ['413']
    assert {n['mention']: (n['status'], n['origin']) for n in notes} == {
        '상법 제413조': ('READ_SCHEDULED', 'ANSWER_POINT'), '모의법 제9조': ('NOT_IN_DOCUMENT', 'ANSWER_POINT')}
    # Without any matcher the failure is recorded instead of silently dropped.
    bare, _ = execution(v)
    rows, notes = g.named_article_reads(bare, v, [], SOURCES)
    assert rows == [] and notes and {n['failure'] for n in notes} == {'NO_MATCHER'} and {n['status'] for n in notes} == {'UNRESOLVED'}


def test_a_named_article_already_offered_uses_the_offered_location():
    reads = g.read_choices([], [loc(1, '상법 · 제413조(감사의 보수)')])
    v = value(open=False)
    session = S(matcher=S(documents={}), scope={'d1'}, tools=S(sources={'s1': {'document_id': 'd1'}}))
    import semantic_runtime.legal_agent.guided_answer as module
    old = module.resolve_named_article
    module.resolve_named_article = lambda s, f: ({'document_id': 'd1', 'source_id': 's1', 'unit_id': '1', 'document_name': '상법', 'coordinate': '제413조'}, None, '상법 제413조')
    try:
        v['answer_points'][0]['text'] = '상법 제413조를 확인해야 합니다.'
        rows, notes = g.named_article_reads(S(s=session), v, reads, SOURCES)
    finally:
        module.resolve_named_article = old
    assert [r['id'] for r in rows] == ['L1'] and notes[0]['status'] == 'READ_SCHEDULED'


def test_server_reads_take_lower_rules_and_cited_question_titled_articles():
    locations = [loc(1, '벤처기업육성에 관한 특별법 시행령 · 제11조의3', specifies=['벤처기업육성에 관한 특별법 · 제16조의3']),
                 loc(2, '유가증권시장 상장규정 · 제13조(상장주선인의 의무)', cited_by=['시행세칙 제9조'], matched_terms=['상장주선인']),
                 loc(3, '상법 · 제1조(목적)', cited_by=['제5조']),  # cited once, no question word: not forced
                 loc(4, '상법 · 제2조', cited_by=['제5조', '제6조']),  # cited by two read articles
                 loc(5, '상법 · 제3조', vector_rank=1, matched_terms=['상장주선인'])]
    reads = g.read_choices([], locations)
    rows = g.server_read_rows(reads, set())
    # Cited by two read articles without a question word is not forced (ADR-1468: 상법 제401조의2).
    assert [(k, r['label'].split(' · ')[-1]) for k, r in rows] == [('SPECIFIES', '제11조의3'), ('CITED', '제13조(상장주선인의 의무)')]
    assert g.server_read_rows(reads, {'L1'})[0][0] == 'CITED'


def test_assess_merges_reads_up_to_four_and_does_not_force_a_location_twice():
    locations = [loc(1, '시행령 · 제11조의3', specifies=['법 · 제16조의3']),
                 loc(2, '규정 · 제13조(상장주선인의 의무)', cited_by=['시행세칙 제9조'], matched_terms=['상장주선인']),
                 loc(3, '규정 · 제14조', vector_rank=2, matched_terms=['상장주선인']),
                 loc(4, '규정 · 제15조'), loc(5, '규정 · 제16조')]
    v = value(open=False); v['next_reads'] = ['L4', 'L5']
    e, _ = execution(v)
    selection = {'issues': ISSUES, 'unread_locations': deepcopy(locations)}
    result = g.assess(e, SOURCES, ISSUES, '상장주선인의 의무인수 수량은?', [], selection=selection)
    proposed = [r['label'] for r in result['guided_reply']['proposed_reads']]
    # The answer's two choices, then the lower rule and the cited article; the vector read waits.
    assert proposed == ['규정 · 제15조', '규정 · 제16조', '시행령 · 제11조의3', '규정 · 제13조(상장주선인의 의무)']
    event = next(p for k, p in e.s.work.events if k == 'GUIDED_ANSWER_SERVER_READS')
    assert [r['kind'] for r in event['reads']] == ['SPECIFIES', 'CITED'] and event['deferred'] == [{'kind': 'VECTOR', 'label': '규정 · 제14조'}]
    # Next round of the same request: the forced ones are not forced again (an unreadable one cannot loop).
    v2 = value(open=False); v2['next_reads'] = []  # the schema requires the field when reads are offered
    e.invoke = lambda *a, **k: deepcopy(v2)
    again = g.assess(e, SOURCES, ISSUES, '상장주선인의 의무인수 수량은? (다음 라운드)', [], selection=selection)
    assert [r['label'] for r in again['guided_reply']['proposed_reads']] == ['규정 · 제14조']


def test_no_server_read_without_hints_keeps_the_answer_unchanged():
    e, calls = execution(value(open=False))
    selection = {'issues': ISSUES, 'unread_locations': [loc(4, '규정 · 제15조')]}
    result = g.assess(e, SOURCES, ISSUES, '질문', [], selection=selection)
    assert result['guided_reply']['proposed_reads'] == [] and not any(k == 'GUIDED_ANSWER_SERVER_READS' for k, _ in e.s.work.events)


def test_prompt_and_server_texts_ask_only_what_the_user_can_answer():
    assert '사용자만 답할 수 있는 것만 묻는다' in g.PROMPT and "'더 찾아볼까요?' 금지" in g.PROMPT
    assert 'specifies' in g.PROMPT and 'answer_points에 문서명과 조문번호를 함께 적은 조문' in g.PROMPT
    import inspect
    source = inspect.getsource(g)
    assert '같은 질문으로 이어서 더 찾아볼까요' not in source and '이 내용을 더 찾아볼까요' not in source


# ---- guided_navigation: lower-rule locations from the read article's connection directory

class Repo:
    def __init__(self): self.events = []
    def event(self, kind, payload): self.events.append((kind, deepcopy(payload)))


def nav_inv(monkeypatch, directory, text='벤처기업이 대통령령으로 정하는 바에 따라 주식매수선택권을 부여할 수 있다.', readable=None):
    readable = readable or {}
    def article(inv, did, uid):
        if (did, str(uid)) in readable:
            return None, readable[(did, str(uid))]
        return {'document_id': did, 'source_id': did + ':' + str(uid), 'unit_id': 'A' + str(uid)}, None
    monkeypatch.setattr(gn, 'readable_article', article)
    record = {'source_id': 'law:16-3', 'document_id': 'law', 'offer': {'unit_id': '163', 'extent': 'subtree', 'block_ids': ['b1']},
              'evidence': [{'source_id': 'law:16-3', 'spans': [{'block_id': 'b1', 'start_cp': 0, 'end_cp': len(text), 'text': text}]}]}
    monkeypatch.setattr(inventory, 'acquired_records', lambda p, **_: {'g1': record})
    opened = []
    def inspect(inv, scope, **_):
        opened.append(scope)
        return deepcopy(directory)
    monkeypatch.setattr(cs, 'inspect_directory', inspect)
    monkeypatch.setattr(gn, '_location_label', lambda inv, identity, row, action: identity['document_id'] + ' ' + str(identity['unit_id']))
    store = S(source=lambda did, bid: {'text': text})
    s = S(store=store, matcher=S(units={}, documents={}), scope={'law', 'decree'}, repo=Repo(),
          tools=S(sources={'law:16-3': {'document_id': 'law'}, 'decree:11-3': {'document_id': 'decree'}}))
    return S(s=s, p={'turn': 1}, question='행사가격'), opened


def group(direction, role, did, sid, uid, *, already=False):
    return {'direction': direction, 'target': {'heading': '제11조의3(주식매수선택권)'}, 'anchor': {'heading': '제16조의3'},
            'offers': {'k': ({'source_id': sid, 'document_id': did}, {'unit_id': uid, 'extent': 'subtree', 'block_ids': ['c1']})},
            'connections': [{'citation_role': role, 'already_read': already, 'endpoint_scopes': ['k'], 'reference_id': 'r' + uid}]}


def test_lower_rule_specifying_a_read_article_becomes_a_location(monkeypatch):
    directory = {'groups': [group('INCOMING', 'SPECIFIES', 'decree', 'decree:11-3', '113'),
                            group('INCOMING', 'BORROWS', 'decree', 'decree:12', '12'),  # borrowing: not a lower rule's specification
                            group('INCOMING', 'SPECIFIES', 'law', 'law:20', '20'),  # same law: stays with FOLLOW pairs
                            group('OUTGOING', 'SPECIFIES', 'decree', 'decree:30', '30')]}
    inv, opened = nav_inv(monkeypatch, directory)
    rows = gn.delegated_locations(inv, [], {}, {})
    # The location is the whole article the paragraph belongs to (readable_article), read once.
    assert [(r['identity']['document_id'], r['identity']['unit_id'], r['specifies']) for r in rows] == [('decree', 'A113', ['law 163'])]
    assert len(opened) == 1 and opened[0]['structural_selection']['purpose'] == 'DELEGATED_SPECIFICATION'
    kind, payload = inv.s.repo.events[-1]
    assert kind == 'DELEGATED_LOCATIONS_OFFERED' and payload['model_called'] is False and payload['search_called'] is False


def test_no_delegation_wording_opens_no_directory_and_read_targets_are_skipped(monkeypatch):
    directory = {'groups': [group('INCOMING', 'SPECIFIES', 'decree', 'decree:11-3', '113', already=True)]}
    inv, opened = nav_inv(monkeypatch, directory)
    assert gn.delegated_locations(inv, [], {}, {}) == []  # already read
    inv, opened = nav_inv(monkeypatch, directory, text='주식매수선택권은 정관으로 정한다.')
    assert gn.delegated_locations(inv, [], {}, {}) == [] and opened == []


def test_directory_failure_is_recorded_not_raised(monkeypatch):
    inv, _ = nav_inv(monkeypatch, {'groups': []})
    def boom(inv, scope, **_): raise RuntimeError('x')
    monkeypatch.setattr(cs, 'inspect_directory', boom)
    assert gn.delegated_locations(inv, [], {}, {}) == []
    assert inv.s.repo.events[-1][1]['directory_failures'] == [{'anchor': 'law 163', 'error': 'RuntimeError'}]


def test_unread_locations_runs_without_remembered_menu_locations(monkeypatch):
    """Every remembered menu location read (or none remembered) used to return [] before the
    cited and lower-rule hints of the read originals were computed."""
    monkeypatch.setattr(inventory, 'acquired_records', lambda p, **_: {'g1': {'evidence': [{'source_id': 'law:5', 'spans': [{'block_id': 'b1'}]}]}})
    monkeypatch.setattr(gn, 'scan_read_originals', lambda inv, known: {'cited': {('law', '제13조'): ['제9조']}, 'defers': {}})
    cited = {'identity': {'document_id': 'law', 'source_id': 'law:13', 'unit_id': '13'}, 'label': '규정 · 제13조', 'from_citation': True}
    monkeypatch.setattr(gn, 'cited_locations', lambda inv, c, rows, known, units, terms=(): [deepcopy(cited)])
    monkeypatch.setattr(gn, 'delegated_locations', lambda inv, rows, known, units: [])
    monkeypatch.setattr(gn, 'vector_top_locations', lambda inv, rows, known, units: [])
    s = S(matcher=S(units={('law', '13'): {'surface': '제13조', 'title': '상장주선인의 의무'}}), scope={'law'},
          tools=S(sources={'law:13': {'document_id': 'law', 'unit_id': '13'}}))
    inv = S(s=s, p={}, question='상장주선인의 의무인수 수량')
    rows = gn.unread_locations(inv)
    assert [(r['label'], r['cited_by'], r['matched_terms']) for r in rows] == [('규정 · 제13조', ['제9조'], ['상장주선인'])]


def test_unreadable_lower_rule_is_not_offered_and_is_recorded(monkeypatch):
    directory = {'groups': [group('INCOMING', 'SPECIFIES', 'decree', 'decree:11-3', '113')]}
    inv, _ = nav_inv(monkeypatch, directory, readable={('decree', '113'): 'NO_ORIGINAL_IN_SELECTED_SCOPE'})
    assert gn.delegated_locations(inv, [], {}, {}) == []
    assert inv.s.repo.events[-1][1]['unreadable'] == [{'unit_id': '113', 'document_id': 'decree', 'reason': 'NO_ORIGINAL_IN_SELECTED_SCOPE'}]


def test_no_lower_rule_cascade_from_articles_read_by_answer_rounds(monkeypatch):
    directory = {'groups': [group('INCOMING', 'SPECIFIES', 'decree', 'decree:11-3', '113')]}
    inv, opened = nav_inv(monkeypatch, directory)
    inv.p['continuation_reads'] = {'k': {'reads': [{'identity': {'source_id': 'law:16-3'}}]}}
    assert gn.delegated_locations(inv, [], {}, {}) == [] and opened == []


def test_readable_article_groups_paragraphs_and_checks_the_request_scope(monkeypatch):
    from semantic_runtime.legal_agent import tool_availability as av
    units = {('d', '1'): {'surface': '제23조', 'parent': None}, ('d', '2'): {'surface': '③', 'parent': '1'}}
    matcher = S(units=units, _unit_sources=lambda did, uid: ['d:23'] if uid == '1' else ['d:23-3'])
    inv = S(s=S(matcher=matcher, tools=S(sources={'d:23': {'document_id': 'd'}, 'd:23-3': {'document_id': 'd'}})))
    monkeypatch.setattr(av, 'article_plan', lambda s, identity: (('hit', 'offer'), None))
    assert gn.readable_article(inv, 'd', '2') == ({'document_id': 'd', 'source_id': 'd:23', 'unit_id': '1'}, None)
    monkeypatch.setattr(av, 'article_plan', lambda s, identity: (None, 'NO_ORIGINAL_IN_SELECTED_SCOPE'))
    assert gn.readable_article(inv, 'd', '2') == (None, 'NO_ORIGINAL_IN_SELECTED_SCOPE')


def test_lower_rule_and_cited_reads_only_in_the_first_answer_round():
    locations = [loc(1, '시행령 · 제11조의3', specifies=['법 · 제16조의3']), loc(2, '규정 · 제15조')]
    v = value(open=False); v['next_reads'] = []
    e, _ = execution(v)
    e.closure_round_done = True  # an earlier answer round of this request already ran
    result = g.assess(e, SOURCES, ISSUES, '질문', [], selection={'issues': ISSUES, 'unread_locations': deepcopy(locations)})
    assert result['guided_reply']['proposed_reads'] == []


def test_unresolved_answer_point_names_do_not_reach_the_next_round(monkeypatch):
    monkeypatch.setattr(sq, 'resolve', fake_resolve({}))
    monkeypatch.setattr(sq, 'document_hits', fake_hits({'상법': 'law'}))
    v = value(open=False)
    v['answer_points'][0]['text'] = '같은 법 시행령 제49조와 상법 제999조를 함께 봅니다.'
    e, calls = execution(v)
    e.s.matcher = S(documents={}); e.s.scope = {'law'}; e.s.tools = S(sources={})
    g.assess(e, SOURCES, ISSUES, '질문', [])
    assert e.named_article_notes == []
    assert any(k == 'GUIDED_ANSWER_NAMED_ARTICLES' and p['notes'] for k, p in e.s.work.events)
