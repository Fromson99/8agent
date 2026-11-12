"""A reply to what the system asked continues that question (field photos 2026-11-11, B05 guided mode).

Turn 1 asked which work the question was about. "파생상품 거래 쪽을 알려줘" and then "…에 이어서 확인해줘"
both ended in "새 질문으로 조사할까요, 아니면 이어서 확인할까요?", because the resolver and the reviewer
disagreed about which kind of continuation it was, and the user was asked the same thing again.
Actual HTTP/store boundary with a scripted transport; the INTENT stop marks the executed request.
"""
import pytest
from semantic_runtime.legal_agent import corrected_memory, memory_methods as mm
from semantic_runtime.legal_agent import output_contract as output
from test_memory_runtime_v2 import command
from test_multiturn_new_topic_branch import NEW, Stop, checker, pending_id, run, tree  # noqa: F401
from test_guided_continue_bounds import NAMED

REPLY = '파생상품 거래 쪽을 알려줘'
TASK = NAMED + ' (파생상품 거래)'
BEFORE = {'task': '심사검토기간 10일이 적정한지', 'facts': [], 'queries': [], 'source_category': 'ALL'}
AFTER = {**BEFORE, 'task': '파생상품 거래의 심사검토기간 10일이 적정한지'}
EDITED = {'before': BEFORE, 'after': AFTER}
REPLAN = {'method_id': 'RESEARCH_REPLAN', 'stage': 'PLAN'}


def review(relation, valid):
    return {'valid': valid, 'reason': '모의 검사', 'request_relation': relation, 'requested_task': '파생상품 심사기간'}


@pytest.mark.parametrize('relation', ['FOLLOWUP', 'CONTINUE', 'CONDITION_CHANGE'])
def test_a_reply_that_searches_the_same_question_is_not_refused_for_its_kind(relation):
    override = mm.validate_transition(REPLAN, EDITED, review(relation, False), replying=True)
    assert override['kind'] in ('COMMAND_CHECK_REPLY_SAME_QUESTION', 'COMMAND_CHECK_SAME_QUESTION')
    assert override['reviewer_valid'] is False


def test_a_real_branch_disagreement_is_still_refused_for_a_reply():
    with pytest.raises(output.OutputContractError):
        mm.validate_transition(REPLAN, EDITED, review('NEW_TOPIC', False), replying=True)
    with pytest.raises(output.OutputContractError):
        mm.validate_transition(REPLAN, EDITED, review('NEW_TOPIC', True), replying=True)


def test_a_changed_purpose_that_the_command_would_not_apply_is_still_refused():
    # ADR-1397/1398: "임시총회는?" kept the earlier purpose and investigated the old question.
    unchanged = {'before': BEFORE, 'after': BEFORE}
    with pytest.raises(output.OutputContractError):
        mm.validate_transition({'method_id': 'RESEARCH_CONTINUE', 'stage': 'SELECT'}, unchanged, review('FOLLOWUP', True), replying=True)
    with pytest.raises(output.OutputContractError):
        mm.validate_transition(REPLAN, unchanged, review('FOLLOWUP', True))
    with pytest.raises(output.OutputContractError):
        mm.validate_transition(REPLAN, unchanged, review('FOLLOWUP', False))


def test_a_same_question_rewrite_is_accepted_outside_a_reply():
    assert mm.validate_transition(REPLAN, EDITED, review('CONTINUE', True)) is None
    assert mm.validate_transition(REPLAN, EDITED, review('CONTINUE', False))['kind'] == 'COMMAND_CHECK_SAME_QUESTION'
    with pytest.raises(output.OutputContractError):
        mm.validate_transition(REPLAN, EDITED, review('FOLLOWUP', False))


def test_prompts_state_the_reply_rule_in_all_three_places():
    assert 'asked_user 또는 answer_start' in corrected_memory.RELATE and REPLY in corrected_memory.RELATE
    assert 'FOLLOWUP 또는 CONTINUE이며 어느 쪽이든 valid=true다' in mm.TRANSITION_PROMPT
    assert '어느 관계로 볼지를 이유로 거절하지 않는다' in mm.TRANSITION_PROMPT


def asked_back(monkeypatch):
    """Turn 1 found nothing and asked which work; the stored answer otherwise comes from the guided harness."""
    original = corrected_memory.Memory.goal_detail

    def goal_detail(self, g):
        original(self, g)
        g['previous_response'].update(legal_conclusion_confirmed=False, answer_coverage='INSUFFICIENT',
            guidance={'questions': [{'question': '어떤 업무인지 알려주시겠어요?'}], 'proposed_reads': []})
    monkeypatch.setattr(corrected_memory.Memory, 'goal_detail', goal_detail)


def test_the_field_reply_executes_on_the_same_question(tree, tmp_path, monkeypatch):
    asked_back(monkeypatch)
    replan = lambda t, v: command('RESEARCH_REPLAN', target=t.target, stage='PLAN', task=TASK, queries=['파생상품 심사기간'])
    transport, responses, (goals, events) = run(tree, tmp_path, {2: {'question': REPLY, 'resolve': [replan], 'check': lambda t, v: {
        'valid': False, 'reason': '사실 추가로 보인다', 'request_relation': 'CONDITION_CHANGE', 'requested_task': TASK}}})
    assert len(goals) == 1 and goals[0]['state']['task'] == TASK
    assert len(transport.checks) == 1, 'accepted on the first proposal; no repair round'
    assert '판단이 엇갈려' not in responses[1].text


def test_an_explicit_continue_is_not_asked_again(tree, tmp_path):
    # Turn 2 is a real disagreement and asks; turn 3 answers "이어서"; the reviewer still refuses twice.
    revise = lambda t, v: command('PURPOSE_REVISE', target=t.target, stage='INTENT', task=NEW)
    answer = lambda t, v: command('RESEARCH_CONTINUE', target=t.target, pending_request=pending_id(v))
    transport, responses, (goals, _) = run(tree, tmp_path, {
        2: {'question': NEW, 'resolve': [revise], 'check': lambda t, v: {'valid': False, 'reason': '새 질문', 'request_relation': 'NEW_TOPIC', 'requested_task': NEW}},
        3: {'question': '이전 질문에 이어서 해줘', 'resolve': [answer], 'check': lambda t, v: {'valid': False, 'reason': '목적이 다르다', 'request_relation': 'FOLLOWUP', 'requested_task': NEW}}})
    assert '판단이 엇갈려' in responses[1].text
    assert '판단이 엇갈려' not in responses[2].text and '새 질문으로 조사할까요' not in responses[2].text
    assert len(goals) == 1


def test_a_second_confirmation_quotes_the_request_not_the_reply(tree, tmp_path):
    # Field photo 3 quoted the user's own "…에 이어서 확인해줘" back as the question.
    revise = lambda t, v: command('PURPOSE_REVISE', target=t.target, stage='INTENT', task=NEW)
    conflict = {'question': NEW, 'resolve': [revise], 'check': lambda t, v: {'valid': False, 'reason': '새 질문', 'request_relation': 'NEW_TOPIC', 'requested_task': NEW}}
    reply = '음 글쎄'
    transport, responses, _ = run(tree, tmp_path, {2: conflict, 3: {**conflict, 'question': reply}})
    text = responses[2].json()['answer']['text']
    assert NEW in text and '“'+reply not in text



def test_a_selected_release_package_still_finds_the_request(monkeypatch):
    # ADR-1489: the selected release runs under its own package name, with its own empty log context,
    # while service.py sets the request on semantic_runtime.observability; every block was dropped.
    from contextvars import ContextVar
    import logging
    from types import SimpleNamespace
    from semantic_runtime import observability as entry, request_report
    monkeypatch.setattr(request_report, 'obs', SimpleNamespace(ROOT=entry.ROOT, _CONTEXT=ContextVar('release_copy', default={})))
    seen = []

    class Capture(logging.Handler):
        def emit(self, record):
            seen.append(record)
    handler = Capture(); logger = logging.getLogger(entry.ROOT); logger.addHandler(handler)
    try:
        with entry.context(request_id='r-1'):
            request_report.decision_detail('MULTITURN 명령 제안', {'method': 'RESEARCH_REPLAN'})
    finally:
        logger.removeHandler(handler)
    assert [r.fields['request_id'] for r in seen] == ['r-1'] and seen[0].live_detail[0] == 'MULTITURN 명령 제안'


def test_naming_the_question_twice_with_the_wrong_method_executes_the_pending_request(tree, tmp_path):
    # ADR-1490 S8 T4: "1번째 질문 법 기준으로 봐줘" as ANSWER_PRESENT + pending_request, kept through the correction.
    revise = lambda t, v: command('PURPOSE_REVISE', target=t.target, stage='INTENT', task=NEW)
    present = lambda t, v: command('ANSWER_PRESENT', target=t.target, pending_request=pending_id(v))
    transport, responses, (goals, _) = run(tree, tmp_path, {
        2: {'question': NEW, 'resolve': [revise], 'check': lambda t, v: {'valid': False, 'reason': '새 질문', 'request_relation': 'NEW_TOPIC', 'requested_task': NEW}},
        3: {'question': '1번째 질문 말이야', 'resolve': [present], 'check': checker('CONTINUE', NEW)}})
    assert '판단이 엇갈려' not in responses[2].text
    assert transport.checks[-1]['transition']['applies_pending_request'] == NEW and transport.checks[-1]['command']['method_id'] == 'RESEARCH_CONTINUE'
    assert len(goals) == 1
