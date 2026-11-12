"""서버가 연결을 대신 읽는다 (2026-11-11, ADR-1496/1497 cm-030 후속).

- 모델이 READ로 고른 조문은 서버가 읽은 직후 연결을 조회하고 필요한 대상을 읽는다.
- 연결 카드는 아직 읽지 않은 대상만 한 줄씩, 이전 조회는 다시 보내지 않는다.
- (r2, ADR-1498) READ 뒤 서버 조회는 GENOS_SERVER_FOLLOW=on일 때만, 자동 읽기 한도·빌려 씀·같은 절은 MAIN209로,
  모델 화면의 읽음 상태표·보여 준 읽기·문서 목차는 줄인다.
- 항별 연결 수는 인용한 문장의 위치(정방향)로 센다.
- 대사 자식 조사도 가이드 루프를 쓰고 한도는 환경변수로 정한다.
"""
import pytest

from semantic_runtime.legal_agent import follow_coordinates as fc, guided_navigation as gn
from semantic_runtime.legal_agent import connection_scope as cs, law_candidates as lc, law_navigation as ln
from semantic_runtime.legal_agent.errors import ContractError


def scope(label, block, root='s1'):
    return {'label': label, 'structural_selection': {'scope_id': root, 'delivered_only': True}, 'members': [{'spans': [{'block_id': block}]}]}


ROOT = {'label': '규정 제2-6조', 'structural_selection': {'scope_id': 's1'}, 'members': []}


def test_forward_links_are_counted_where_the_citing_sentence_is():
    choices = [(ROOT, []), (scope('규정 제2-6조 ④', 'b4'), []), (scope('규정 제2-6조 ⑧', 'b8'), [])]
    result = {'groups': [
        {'direction': 'OUTGOING', 'connections': [{'source_unit_path': ['④', '1.']}, {'witness_block_id': 'b4'}, {'witness_block_id': 'b8'}]},
        {'direction': 'INCOMING', 'connections': [{'anchor_head_block_ids': []}, {'anchor_head_block_ids': ['zz']}]}]}
    assert fc.by_unit(result, choices, ROOT) == [{'unit': '제4항', 'connection_count': 2}, {'unit': '제8항', 'connection_count': 1},
                                                  {'unit': fc.WHOLE, 'connection_count': 2}]


def card(target, anchor='A', coordinate='제3조', read=False, role='SPECIFIES', direction='OUTGOING'):
    return {'target': {'source_id': target, 'document_name': '모의규정 > 인수위험관리준칙', 'heading': '준용'},
            'anchor': {'source_id': anchor}, 'coordinate': coordinate, 'already_read': read, 'citation_role': role,
            'direction': direction, 'citation_relation': {'sentence': '가' * 300}, 'read_action': 'r1', 'reference_witness': {'block_id': 'b'}}


def test_cards_keep_only_unread_targets_in_one_line():
    view = {'references': {'dependency_cards': [card('B'), card('B'), card('C', read=True), card('A'), card('D', role='MUTATIS', direction='INCOMING')],
                           'previously_inspected_cards': [card('E'), card('F')]}}
    refs = fc.compact_cards(view)['references']
    assert [c['to'] for c in refs['dependency_cards']] == ['인수위험관리준칙 제3조 준용'] * 2
    assert [c['kind'] for c in refs['dependency_cards']] == ['구체화', '준용']
    assert refs['dependency_cards'][1]['direction'] == '이 조문을 인용' and len(refs['dependency_cards'][0]['sentence']) == 160
    assert refs['left_out_connections'] == {'already_read': 1, 'same_article': 1, 'same_target': 1}
    assert refs['earlier_lookups'] == 2 and 'previously_inspected_cards' not in refs
    assert 'reference_witness' not in refs['dependency_cards'][0]


def test_a_view_without_cards_is_unchanged():
    assert fc.compact_cards({'sources': []}) == {'sources': []}


def test_a_reverse_borrowing_is_not_read_by_the_server():
    link = {'citation_relation': {'kind': 'BORROWS', 'sentence': '제2-5조에 따른 인수위험 한도를 적용한다'}}
    assert not cs.question_match(link, ['인수위험'])


def test_auto_read_limits_are_main209_and_the_environment_can_raise_them(monkeypatch):
    assert (cs.CHAIN_LIMITS['outgoing'], cs.CHAIN_LIMITS['chars'], cs.SECTION_LIMITS['reads']) == (6, 12000, 2)
    assert cs._limit('GENOS_NOT_SET_X', 6) == 6
    monkeypatch.setenv('GENOS_NOT_SET_X', '20')
    assert cs._limit('GENOS_NOT_SET_X', 6) == 20


def test_the_model_view_keeps_short_bookkeeping():
    view = {'sources': [{'document_id': 'd1', 'text': '본문'}],
            'already_read': [{'document_id': 'd1', 'path': '규정 제1조', 'status': 'READ', 'availability': 'DELIVERED', 'reason': '긴 사유' * 20, 'missing_spans': []}],
            'already_presented_reads': [{'action_id': 'T1', 'covered_spans': []}, {'action_id': 'T2'}],
            'document_structures': [{'document_id': 'd1', 'name': '규정', 'structure': {'children': [1, 2]}}, {'document_id': 'd2', 'name': '법', 'structure': {'children': [3]}}]}
    gn.compact_ledger(view)
    assert view['already_read'] == [{'document_id': 'd1', 'path': '규정 제1조', 'status': 'READ'}]
    assert view['already_presented_reads']['count'] == 2
    assert view['document_structures'] == [{'document_id': 'd1', 'name': '규정', 'structure': {'children': [1, 2]}}, {'document_id': 'd2', 'name': '법'}]
    before = {'document_structures': [{'document_id': 'd2', 'name': '법', 'structure': {'children': [3]}}]}
    gn.compact_ledger(before)  # nothing on screen yet: every structure stays
    assert before['document_structures'][0]['structure'] == {'children': [3]}


class Session:
    profile = {'candidate_navigation': {'guided_loop': True, 'guided_action_limit': 6, 'guided_read_rounds': 4}}


def handoff(monkeypatch, on=True):
    from semantic_runtime.legal_agent import source_handoff
    monkeypatch.setattr(source_handoff, 'enabled', lambda: on)


def test_comparison_children_use_the_guided_limits_from_the_environment(monkeypatch):
    handoff(monkeypatch)
    monkeypatch.setenv('GENOS_COMPARE_GUIDED', 'on')
    assert lc.policy(Session)['guided_action_limit'] == 6
    monkeypatch.setenv('GENOS_COMPARE_GUIDED_ACTION_LIMIT', '10')
    monkeypatch.setenv('GENOS_COMPARE_GUIDED_READ_ROUNDS', '6')
    result = lc.policy(Session)
    assert (result['guided_action_limit'], result['guided_read_rounds']) == (10, 6)
    monkeypatch.setenv('GENOS_COMPARE_GUIDED_ACTION_LIMIT', '99')
    with pytest.raises(ContractError):
        lc.policy(Session)
    handoff(monkeypatch, False)
    assert lc.policy(Session)['guided_action_limit'] == 6


def test_the_old_selector_stays_the_comparison_default(monkeypatch):
    assert not gn.compare_guided()
    monkeypatch.setenv('GENOS_COMPARE_GUIDED', 'on')
    assert gn.compare_guided()
    monkeypatch.setenv('GENOS_COMPARE_GUIDED', 'off')
    monkeypatch.setenv('GENOS_COMPARE_GUIDED_ACTION_LIMIT', '10')
    handoff(monkeypatch)
    assert lc.policy(Session)['guided_action_limit'] == 6


class Repo:
    def __init__(self):
        self.events = []

    def event(self, kind, payload):
        self.events.append((kind, payload))


class Inv:
    def __init__(self):
        self.p = {}
        self.s = type('S', (), {'repo': Repo()})()
        self.saved = 0

    def save(self):
        self.saved += 1


def test_a_comparison_question_goes_back_to_the_parent(monkeypatch):
    handoff(monkeypatch)
    inv = Inv()
    value = {'questions': [{'uncertainty': '대상 상품이 두 가지다', 'question': '어느 상품인가요?'}]}
    with pytest.raises(gn.Pause, match='COMPARISON_QUESTION_RETURNED'):
        gn.pause(inv, {'presentation_id': 'p'}, value)
    assert inv.p['comparison_open_questions'] == value['questions'] and 'user_guidance' not in inv.p
    assert inv.s.repo.events[0][0] == 'COMPARISON_QUESTION_RETURNED' and inv.saved == 1


def test_server_follow_is_switched_by_the_environment(monkeypatch):
    class I:
        policy = {'selected_connection_scope': True}
        s = type('S', (), {'profile': {}})()
    monkeypatch.setattr(gn, 'enabled', lambda profile: True)
    assert not ln.server_follow_enabled(I)  # off by default since ADR-1498
    monkeypatch.setenv('GENOS_SERVER_FOLLOW', 'on')
    assert ln.server_follow_enabled(I)


from test_multiturn_structured_scope import tree  # noqa: F401,E402


def test_http_the_server_looks_up_the_connections_of_what_the_model_read(tree, tmp_path, monkeypatch):
    import test_guided_continue_bounds as api
    original, follows = api.fill, []

    def fill(schema):
        value = original(schema)
        if isinstance(value, dict) and value.get('choice') == 'FOLLOW':
            follows.append(value)
        return value
    monkeypatch.setattr(api, 'fill', fill)
    monkeypatch.setenv('GENOS_SERVER_FOLLOW', 'on')
    plan = {'resolve': ('RESEARCH_CONTINUE', 'SELECT'), 'relation': 'CONTINUE'}
    transport, responses, _ = api.run(tree, tmp_path, question=api.BROAD, scope='authorized', plan=plan, turns=1)
    assert responses[0].status_code == 200, responses[0].text
    assert responses[0].json()['status'] == 'READY' and follows == []
    views = [r['view'] for r in transport.log if r['phase'] == 'investigate']
    assert any((v.get('connection_review') or {}).get('required_before_finish') is False for v in views), [v.get('connection_review') for v in views]
    assert any('left_out_connections' in (v.get('references') or {}) for v in views), [sorted(v) for v in views]


def test_http_without_the_server_follow_the_model_follows_itself(tree, tmp_path, monkeypatch):
    import test_guided_continue_bounds as api
    original, follows = api.fill, []

    def fill(schema):
        value = original(schema)
        if isinstance(value, dict) and value.get('choice') == 'FOLLOW':
            follows.append(value)
        return value
    monkeypatch.setattr(api, 'fill', fill)
    plan = {'resolve': ('RESEARCH_CONTINUE', 'SELECT'), 'relation': 'CONTINUE'}
    transport, responses, _ = api.run(tree, tmp_path, question=api.BROAD, scope='authorized', plan=plan, turns=1)
    assert responses[0].status_code == 200, responses[0].text
    assert responses[0].json()['status'] == 'READY' and follows
    views = [r['view'] for r in transport.log if r['phase'] == 'investigate']
    assert all(isinstance(v.get('already_presented_reads', {'count': 0}), dict) for v in views)
