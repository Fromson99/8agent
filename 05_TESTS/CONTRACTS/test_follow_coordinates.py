"""FOLLOW를 번호 목록 대신 읽은 원문 번호와 항·호·목으로 받는다 (2026-11-11).

현장·ADR-1496 cm-030: 조 6개에 선택지 237개, 모델이 조 전체를 골라 카드 40개·128K자가 들어왔다.
"""
import json

import pytest
from jsonschema import Draft202012Validator

from test_multiturn_structured_scope import tree  # noqa: F401

from semantic_runtime.legal_agent import follow_coordinates as fc, guided_navigation as gn, output_contract as oc
from semantic_runtime.legal_agent.errors import ProposalError


@pytest.mark.parametrize('text,expected', [('⑧', '8'), ('제8항', '8'), ('8', '8'), ('1.', '1'), ('제1호의2', '1의2'), ('라목', '라'), ('라.', '라'), ('', None), (None, None)])
def test_number(text, expected):
    assert fc.number(text) == expected


@pytest.mark.parametrize('label,expected', [
    ('{D2} 제2-9조 ① 2. 가.', ('1', '2', '가')), ('인수위험관리준칙 제2-6조 ⑧ 1. 라.', ('8', '1', '라')), ('규정 제5조 2.', (None, '2', None)),
    ('자본시장법 제129조 ⑪', ('11', None, None)), ('상법 제434조의2 ②', ('2', None, None)), ('{D2} 제2-6조', None), ('규정 제5조 1) 가)', None)])
def test_label_coordinates(label, expected):
    assert fc.coordinate_of(label) == expected


def choice(label, target, sub=False, refs=('E9',), seen=False, scope='s1'):
    selection = {'document_id': 'd', 'scope_id': scope, 'unit_id': label, **({'delivered_only': True} if sub else {})}
    return {'label': label, 'read_action': target, 'structural_selection': selection, 'source_refs': list(refs), 'previously_inspected': seen, 'selected': False}


CHOICES = [choice('규정 제2-6조', 'T0'), choice('규정 제2-6조 ⑧', 'T8', True), choice('규정 제2-6조 ⑧ 1.', 'T81', True),
           choice('규정 제2-6조 ⑧ 1. 라.', 'T81R', True), choice('규정 제2-6조 ⑨', None, True, seen=True), choice('규정 제2-6조 ① 12.', 'T112', True)]
ACTIONS = {c['read_action'] for c in CHOICES if c['read_action']}


def follow():
    menu = fc.menu({'connection_scope_choices': CHOICES}, ACTIONS)
    return menu, fc.offered(menu, ACTIONS)


def ask(from_source='E9', paragraph=None, item=None, subitem=None):
    return {'choice': 'FOLLOW', 'from_source': from_source, 'paragraph': paragraph, 'item': item, 'subitem': subitem, 'issue_id': 'I1'}


@pytest.mark.parametrize('coordinate,target', [((), 'T0'), (('8',), 'T8'), (('⑧', '제1호'), 'T81'), (('8', '1', '라목'), 'T81R')])
def test_coordinate_reaches_only_that_point(coordinate, target):
    menu, sources = follow()
    result = fc.resolve(ask(**dict(zip(fc.FIELDS, coordinate))), menu, sources)
    assert result['target'] == target and not set(fc.FIELDS + ('from_source',)) & set(result)


def test_unknown_coordinate_lists_the_actual_numbers():
    menu, sources = follow()
    with pytest.raises(fc.CoordinateMiss) as error:
        fc.resolve(ask(paragraph='3'), menu, sources)
    assert '제3항' in str(error.value) and '실제 항: 1, 8, 9' in str(error.value) and error.value.proposal['paragraph'] == '3'
    with pytest.raises(fc.CoordinateMiss) as error:
        fc.resolve(ask(paragraph='8', item='7'), menu, sources)
    assert '실제 호: 1' in str(error.value)


def test_a_point_already_followed_is_not_repeated():
    menu, sources = follow()
    with pytest.raises(fc.CoordinateMiss, match='이미 조회'):
        fc.resolve(ask(paragraph='9'), menu, sources)


def test_whole_article_after_it_was_followed_asks_for_a_point():
    rows = [choice('규정 제2-6조', None, seen=True), choice('규정 제2-6조 ⑧', 'T8', True)]
    menu = fc.menu({'connection_scope_choices': rows}, {'T8'})
    with pytest.raises(fc.CoordinateMiss, match='전체 연결은 이미'):
        fc.resolve(ask(), menu, fc.offered(menu, {'T8'}))


def test_a_page_with_fewer_targets_offers_only_those_sources():
    other = choice('다른 규정 제1조', 'X', refs=('E2',), scope='s2')
    menu = fc.menu({'connection_scope_choices': CHOICES + [other]}, ACTIONS | {'X'})
    assert set(fc.offered(menu, {'X'})) == {'E2'} and set(fc.offered(menu, ACTIONS)) == {'E9'}


def schema():
    follow_branch = {'type': 'object', 'additionalProperties': False, 'required': ['choice', 'target', 'issue_id'],
                     'properties': {'choice': {'const': 'FOLLOW_CONNECTION'}, 'target': {'type': 'string', 'enum': sorted(ACTIONS)}, 'issue_id': {'type': 'string'}}}
    other = {'type': 'object', 'additionalProperties': False, 'required': ['choice'], 'properties': {'choice': {'const': 'PENDING'}}}
    return {'type': 'object', 'anyOf': [follow_branch, other]}


PAYLOAD = {'tool_options': [{'choice': 'FOLLOW_CONNECTION', 'target': t, 'label': t} for t in sorted(ACTIONS)] + [{'choice': 'LOCATE', 'target': 'L', 'label': 'L'}],
           'connection_scope_choices': CHOICES, 'connection_review': {'rule': 'r', 'source_inspections': [{'offered_scope_ids': ['a'] * 9}]}}


def test_the_model_sees_coordinates_instead_of_the_number_list():
    wire, view, restore = gn.projection(schema(), PAYLOAD, follow()[0])
    branch = next(b for b in wire['anyOf'] if b['properties']['choice']['const'] == 'FOLLOW')
    assert 'target' not in branch['properties'] and branch['properties']['from_source']['enum'] == ['E9']
    assert [o['choice'] for o in view['tool_options']] == ['SEARCH'] and 'source_inspections' not in view['connection_review']
    assert [c['label'] for c in view['connection_scope_choices']] == ['규정 제2-6조 ⑨'] and 'read_action' not in view['connection_scope_choices'][0]
    assert view['connection_follow'] == [{'source_ref': 'E9', 'label': '규정 제2-6조', 'whole_available': True, 'already_followed': ['제9항']}]
    value = ask(paragraph='8', item='1', subitem='라')
    Draft202012Validator(branch).validate(value)
    assert restore(value) == {'choice': 'FOLLOW_CONNECTION', 'target': 'T81R', 'issue_id': 'I1'}


def test_other_choices_pass_through_and_no_scope_keeps_the_old_menu():
    _, _, restore = gn.projection(schema(), PAYLOAD, follow()[0])
    assert restore({'choice': 'ANSWER'}) == {'choice': 'PENDING'}
    wire, view, restore = gn.projection(schema(), PAYLOAD)
    assert 'target' in wire['anyOf'][0]['properties'] and len(view['tool_options']) == len(PAYLOAD['tool_options'])
    assert restore({'choice': 'FOLLOW', 'target': 'T8', 'issue_id': 'I1'})['target'] == 'T8'


class Repo:
    def __init__(self):
        self.calls = []


def bounded(can_repair, make, monkeypatch):
    journal = type('J', (), {'state': lambda s: None, 'reserve': lambda s, a, correction_budget=None: None, 'reject': lambda s, a, e, v, can_retry, correction_budget=None: seen.append(can_retry),
                             'accept': lambda s, a, v, **k: None, 'key': 'k', '_put': lambda *a, **k: None})
    seen = []
    monkeypatch.setattr(oc, 'DecisionJournal', lambda *a, **k: journal())
    attempts = []

    def invoke(payload, attempt):
        attempts.append(attempt)
        raise make()
    with pytest.raises(Exception):
        oc.bounded_decision(Repo(), 'read-choice', {}, {}, invoke, lambda v: None, can_repair=can_repair)
    return attempts, seen


def test_a_wrong_coordinate_gets_one_correction_in_a_turn_without_repairs(monkeypatch):
    attempts, seen = bounded(lambda: False, lambda: fc.CoordinateMiss('실제 항: 1'), monkeypatch)
    assert attempts == [0, 1] and seen == [True, False]


def test_other_proposal_errors_still_get_no_correction_there(monkeypatch):
    attempts, seen = bounded(lambda: False, lambda: ProposalError('x'), monkeypatch)
    assert attempts == [0] and seen == [False]


def root_scope():
    return {'label': '규정 제2-6조', 'structural_selection': {'scope_id': 's1'}, 'members': []}


def sub_scope(label, block):
    return {'label': label, 'structural_selection': {'scope_id': 's1', 'delivered_only': True}, 'members': [{'spans': [{'block_id': block}]}]}


def test_many_connections_on_a_whole_article_are_narrowed_first():
    result = {'status': 'COMPLETE', 'groups': []}
    assert fc.needs_narrowing(root_scope(), result, fc.CARD_LIMIT + 1)
    assert not fc.needs_narrowing(root_scope(), result, fc.CARD_LIMIT)
    assert not fc.needs_narrowing(sub_scope('규정 제2-6조 ⑧', 'b8'), result, 99)
    assert not fc.needs_narrowing(root_scope(), {**result, 'status': 'FAILED'}, 99)


def test_counts_per_paragraph_use_the_citing_block():
    scopes = [(root_scope(), []), (sub_scope('규정 제2-6조 ⑧', 'b8'), []), (sub_scope('규정 제2-6조 ⑧ 1.', 'b81'), []), (sub_scope('규정 제2-6조 ⑨', 'b9'), [])]
    result = {'groups': [{'connections': [{'anchor_head_block_ids': ['b8']}, {'anchor_head_block_ids': ['b8']}, {'anchor_head_block_ids': []}]}]}
    assert fc.by_unit(result, scopes, root_scope()) == [{'unit': '제8항', 'connection_count': 2}, {'unit': fc.WHOLE, 'connection_count': 1}]


def http_run(tree, tmp_path, monkeypatch, paragraphs):
    import test_guided_continue_bounds as api
    original, asked = api.fill, []
    plan = {'resolve': ('RESEARCH_CONTINUE', 'SELECT'), 'relation': 'CONTINUE'}

    def coordinate_fill(schema):
        value = original(schema)
        if isinstance(value, dict) and value.get('choice') == 'FOLLOW':
            value['paragraph'] = paragraphs[min(len(asked), len(paragraphs) - 1)]
            asked.append(value['paragraph'])
            if len(asked) < len(paragraphs):  # the scripted model follows once per turn; let the correction through
                plan['followed'].clear()
        return value
    monkeypatch.setattr(api, 'fill', coordinate_fill)
    monkeypatch.setenv('GENOS_SERVER_FOLLOW', 'off')  # the model's own FOLLOW; the server follow is in test_server_links
    transport, responses, _ = api.run(tree, tmp_path, question=api.BROAD, scope='authorized', plan=plan, turns=1)
    return transport, responses, asked


def after_read(transport):
    return [r['view'] for r in transport.log if r['phase'] == 'investigate' and r['view'].get('connection_follow')]


def test_http_follow_names_a_point_and_the_number_list_is_gone(tree, tmp_path, monkeypatch):
    transport, responses, asked = http_run(tree, tmp_path, monkeypatch, ['1'])
    assert responses[0].status_code == 200, responses[0].text
    assert responses[0].json()['status'] == 'READY' and asked == ['1']
    view = after_read(transport)[0]
    assert not any(row['choice'] == 'FOLLOW' for row in view['tool_options'])
    assert 'source_inspections' not in view['connection_review'] and view['connection_follow'][0]['whole_available'] is True


def test_http_wrong_paragraph_is_corrected_once_with_the_actual_numbers(tree, tmp_path, monkeypatch):
    transport, responses, asked = http_run(tree, tmp_path, monkeypatch, ['99', '1'])
    assert responses[0].status_code == 200, responses[0].text
    assert asked == ['99', '1'] and responses[0].json()['status'] == 'READY'
    retried = next(v for v in after_read(transport) if v.get('contract_error'))
    assert '실제 항' in json.dumps(retried['contract_error'], ensure_ascii=False)


# ADR-1497 cm-030: the model put "제2항" in the item field and the reply said "제2호이 없다".
@pytest.mark.parametrize('fields,expected', [
    ({'item': '제2항'}, ('2', None, None)), ({'paragraph': '⑧', 'item': '1'}, ('8', '1', None)),
    ({'paragraph': '라목'}, (None, None, '라')), ({'item': '2'}, (None, '2', None)), ({'subitem': '제1호의2'}, (None, '1의2', None))])
def test_a_written_unit_word_decides_the_level(fields, expected):
    assert fc.wanted_of(fields) == expected


def test_two_numbers_for_one_level_are_sent_back():
    with pytest.raises(fc.CoordinateMiss, match='같은 단위'):
        fc.wanted_of({'paragraph': '8', 'item': '제2항'})


def test_unit_word_in_the_wrong_field_reaches_the_paragraph():
    menu, sources = follow()
    assert fc.resolve(ask(item='제8항'), menu, sources)['target'] == 'T8'


@pytest.mark.parametrize('coordinate,word', [(('3',), '제3항이 없다'), (('8', '7'), '제8항 제7호가 없다'), (('8', '1', '하'), '하목이 없다')])
def test_the_missing_point_reads_with_the_right_particle(coordinate, word):
    menu, sources = follow()
    with pytest.raises(fc.CoordinateMiss) as error:
        fc.resolve(ask(**dict(zip(fc.FIELDS, coordinate))), menu, sources)
    assert word in str(error.value)


def test_planning_schema_bounds_the_output():
    from semantic_runtime.legal_agent import guided_answer as ga
    issues = [{'id': 'Q1'}]; options = [{'id': 'S1'}]; unread = [{'unread_id': 'U1'}]
    full = ga.schema(issues, options, unread)
    plan = ga.schema(issues, options, unread, planning=True)
    assert 'unread_notes' in full['properties'] and 'unread_notes' not in plan['properties']
    point = plan['properties']['answer_points']
    assert point['items']['properties']['text']['maxLength'] == ga.PLANNING_LIMITS['point_chars'] and point['maxItems'] <= 6
    assert plan['properties']['open_questions']['maxItems'] == 1
    assert 'maxLength' not in full['properties']['answer_points']['items']['properties']['text']


def test_coordinate_fields_are_optional_and_written_last():
    """ADR-1501: required paragraph/item/subitem left a model that closed early in a whitespace loop."""
    branch = fc.model_branch({'properties': {'choice': {'const': 'FOLLOW'}, 'target': {'enum': ['T1']}, 'relation': {}, 'missing_need': {'type': 'string'}},
                              'required': ['choice', 'target', 'relation', 'missing_need']}, {'E9': {}})
    assert set(branch['required']) == {'choice', 'relation', 'missing_need', 'from_source'}
    order = list(branch['properties'])
    assert order[:3] == ['choice', 'from_source', 'missing_need'] and order[-3:] == list(fc.FIELDS)
    assert fc.wanted_of({'from_source': 'E9'}) == (None, None, None)
