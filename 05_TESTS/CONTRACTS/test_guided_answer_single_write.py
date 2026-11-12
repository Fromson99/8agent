"""The full answer is written once: short planning calls decide the reads first (2026-11-11).

Field report: four full answer writes of about 3,000 tokens took 83% of the model time of a question.
"""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import guided_answer as g, law_candidates as lc
from semantic_runtime.legal_agent.completion_execution import CompletionExecution
from semantic_runtime.legal_agent.corrected_memory import Reenter
from semantic_runtime.legal_agent.errors import ContractError
from test_guided_answer import ISSUES, SOURCES, execution, value
from test_guided_followup_reads import run, calls, FIRST, SECOND
from test_multiturn_structured_scope import tree  # noqa: F401 - fixture

NAV = {'guided_answer_read_rounds': 6, 'guided_answer_brief_rounds': True}
READ = {'read_id': 'R1', 'label': '제2조', 'origin': 'LOCATION'}
PARTS = {'READ': {'payload': {}}, 'SELECT': {'payload': {'final_ids': ['source:1'], 'issues': ISSUES, 'investigation_state': {}}}}


def stage(monkeypatch, replies, *, navigation=NAV, model_reserved=4, remaining=500, count=0):
    """completion_stage with the answer writer replaced: which writes run, in which mode."""
    e, _ = execution()
    e.s.sources.profile = {'answer_presentation': g.VERSION, 'candidate_navigation': navigation, 'selection_time_reserve_seconds': 10}
    e.s.work.budget = lambda: {'model_limit': 40, 'finalization_reserve': 6, 'model_reserved': model_reserved}
    e.s.context = S(remaining=lambda: remaining)
    e.reentry_counters = {'ASSESS_READ_REENTRY': count}
    modes, queue = [], list(replies)
    def assess(*_, **kw):
        modes.append({k: kw[k] for k in ('brief', 'final') if k in kw})
        return {'guided_reply': queue.pop(0)}
    monkeypatch.setattr(g, 'assess', assess)
    def run_stage():
        return CompletionExecution.completion_stage(e, 'ASSESS', {'facts': []}, deepcopy(PARTS), '질문', None, {})
    return run_stage, modes


def test_planning_call_with_reads_goes_back_to_read_without_a_full_write(monkeypatch):
    go, modes = stage(monkeypatch, [{'read_planning_round': True, 'proposed_reads': [READ]}])
    with pytest.raises(Reenter):
        go()
    assert modes == [{'brief': True}]


def test_no_more_reads_writes_the_full_answer_once(monkeypatch):
    final = {'questions': []}
    go, modes = stage(monkeypatch, [{'read_planning_round': True, 'proposed_reads': []}, final])
    assert go()['guided_reply'] is final and modes == [{'brief': True}, {'final': True}]


def test_unknown_planning_outcome_is_not_followed_by_another_send(monkeypatch):
    stopped = {'read_planning_round': True, 'interruption': {'kind': 'MODEL_OUTCOME_UNKNOWN'}}
    go, modes = stage(monkeypatch, [stopped])
    assert go()['guided_reply'] is stopped and modes == [{'brief': True}]


def test_invalid_planning_output_still_gets_the_full_answer(monkeypatch):
    bad = {'read_planning_round': True, 'interruption': {'kind': 'MODEL_OUTPUT_INVALID'}}
    go, modes = stage(monkeypatch, [bad, {'questions': []}])
    go()
    assert modes == [{'brief': True}, {'final': True}]


def test_budget_ending_after_a_planning_call_writes_the_answer_instead_of_reading(monkeypatch):
    go, modes = stage(monkeypatch, [{'read_planning_round': True, 'proposed_reads': [READ]}, {'questions': []}])
    e_budget = []
    # capacity is true when planning starts and false when its reads would be scheduled
    from semantic_runtime.legal_agent import completion_execution as ce
    real = ce.CompletionExecution.completion_stage
    def limited(self, *a, **k):
        seen = iter([{'model_limit': 40, 'finalization_reserve': 6, 'model_reserved': 4},
                     {'model_limit': 40, 'finalization_reserve': 6, 'model_reserved': 34}])
        self.s.work.budget = lambda: next(seen)
        e_budget.append(True)
        return real(self, *a, **k)
    monkeypatch.setattr(ce.CompletionExecution, 'completion_stage', limited)
    go()
    assert e_budget and modes == [{'brief': True}, {'final': True}]


def test_round_limit_keeps_the_previous_single_write_path(monkeypatch):
    reply = {'proposed_reads': [READ]}
    go, modes = stage(monkeypatch, [reply], count=6)
    assert go()['guided_reply'] is reply and modes == [{'brief': False}]


def test_switch_off_keeps_the_rewrite_rounds(monkeypatch):
    go, modes = stage(monkeypatch, [{'proposed_reads': [READ]}], navigation={'guided_answer_read_rounds': 6})
    with pytest.raises(Reenter):
        go()
    assert modes == [{'brief': False}]


def test_planning_input_is_marked_and_is_never_kept_as_a_draft():
    e, sent = execution(value(open=False))
    result = g.assess(e, SOURCES, ISSUES, '어느 유형인가요?', [], brief=True)
    assert sent[0][1]['read_planning_round'] == g.READ_PLANNING_ROUND
    assert result['guided_reply']['read_planning_round'] is True
    assert getattr(e, 'round_draft', None) is None and e.brief_evidence_sources == {'source:1'}


def test_final_write_offers_no_reads_and_schedules_none():
    e, sent = execution(value(open=False))
    captured = []
    original = e.invoke
    e.invoke = lambda prompt, data, schema, phase: captured.append(schema) or original(prompt, data, schema, phase)
    result = g.assess(e, SOURCES, ISSUES, '어느 유형인가요?', [], final=True)
    assert 'read_planning_round' not in sent[0][1] and 'readable_locations' not in sent[0][1]
    assert 'next_reads' not in captured[0]['properties']
    assert not result['guided_reply'].get('proposed_reads') and result['claims']


def test_policy_needs_answer_read_rounds_and_a_boolean():
    assert lc.validate_policy({'guided_loop': True, 'guided_action_limit': 3, **NAV})['guided_answer_brief_rounds'] is True
    with pytest.raises(ContractError):
        lc.validate_policy({'guided_answer_brief_rounds': True})
    with pytest.raises(ContractError):
        lc.validate_policy({'guided_loop': True, 'guided_answer_read_rounds': 6, 'guided_answer_brief_rounds': 1})


def test_service_reads_after_planning_and_writes_the_answer_once(tree, tmp_path):
    plan = {'actions': {1: [('LOCATE', '제1조제1항'), ('READ', '제1조제1항'), ('LOCATE', '제1조제2항'), ('QUERY', '승인 보고')]}}
    transport, responses = run(tree, tmp_path, plan, turns=1, navigation={'guided_action_limit': 3, **NAV})
    assert responses[0].status_code == 200, responses[0].text
    answers = calls(transport, 1, 'answer')
    planning = [a for a in answers if 'read_planning_round' in a['view']]
    written = [a for a in answers if 'read_planning_round' not in a['view']]
    assert len(written) == 1 and answers[-1] is written[0] and len(planning) == 2
    assert not any('승인 후 보고' in o['text'] for o in planning[0]['view']['originals'])
    assert any('승인 후 보고' in o['text'] for o in written[0]['view']['originals'])
    assert 'next_reads' not in written[0]['schema']['properties'] and 'previous_answer_points' not in written[0]['view']
    assert [c['text'] for c in responses[0].json()['answer']['claims']] == [FIRST, SECOND]
