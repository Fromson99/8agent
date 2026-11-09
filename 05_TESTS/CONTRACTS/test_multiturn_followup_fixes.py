"""Follow-ups after the 8-scenario multi-turn run (ADR-1454/1455, 2026-11-08).

1. ANSWER_PRESENT asking for one part of an earlier answer shows that part (one claim-choice call, no search).
2. The clarification "n번째 질문 “…”" names the question in the user's own words, not the model-written purpose.
4. Anything connected to an earlier question continues it; an explicit new-question wording starts a new one (prompt rules).
6. Persisted reference read grants that cannot be re-witnessed are dropped, never an HTTP 500 (MAIN176 S4).
7. An investigation stopped by MODEL_DECISION_UNRESOLVED still answers from the acquired originals (ADR-1451).
"""
from copy import deepcopy
import inspect
import json
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import guided_answer as g, completion_contracts as cc, memory_methods as mm, query_scope as qs
from semantic_runtime.legal_agent import corrected_memory
from semantic_runtime.legal_agent.completion_execution import CompletionExecution
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.legal_agent.shortcut_store import selected_store
from test_guided_answer import execution, ISSUES, SOURCES, OPTIONS
from test_legal_agent_double_harness import ROOT, wire
from test_memory_runtime_v2 import command, fit
from test_multiturn_structured_scope import tree, change
from test_batch_reference_navigation import connected, initial
from semantic_runtime.legal_agent import unit_relations as relations, unit_reading as ur
import test_guided_followup_reads as followup
from test_multiturn_related_questions import run as related_run, second_topic, pick, unsure, NAMED, NEW, checker, new_question

POINTS = [{'issue_refs': ['Q1'], 'evidence_refs': [OPTIONS[0]['id']], 'text': '준법감시인은 사내이사 또는 업무집행책임자 중에서 선임합니다.'},
          {'issue_refs': ['Q1'], 'evidence_refs': [OPTIONS[0]['id']], 'text': '준법감시인의 임기는 2년 이상으로 합니다.'}]


def two_claim_assessment():
    e, _ = execution({'answer_points': deepcopy(POINTS), 'open_questions': []})
    a = g.assess(e, SOURCES, ISSUES, '준법감시인은 어떻게 임면해?', [])
    assert [c['text'] for c in a['claims']] == [p['text'] for p in POINTS]
    return a


def focus_executor(reply):
    e, calls = execution(reply)
    return e, calls


# ---- 1. focused re-show -------------------------------------------------------------------------

def test_present_a_part_shows_only_the_claims_that_hold_it_with_one_choice_call():
    a = two_claim_assessment()
    e, calls = focus_executor({'reason': '임기를 묻는다', 'scope': 'PART', 'claim_ids': ['C2']})
    plan = g.focus_plan(e, a, {'utterance': '그 사람 임기는 몇 년이야?', 'question': '준법감시인 임면 절차'})
    assert [c[0] for c in calls] == [g.FOCUS_PHASE]
    assert calls[0][1]['current_request'] == '그 사람 임기는 몇 년이야?'
    assert [p['point_id'] for p in calls[0][1]['answer_points']] == ['C1', 'C2'], 'claim IDs only, no new text'
    assert plan['focus'] == {'claim_ids': ['C2'], 'request': '그 사람 임기는 몇 년이야?', 'omitted': 1}
    assert plan['claim_order'] == ['C1', 'C2'], 'every accepted claim stays in the saved judgment'
    out = cc.compose(a, plan)
    cc.verify_composition(a, out)
    assert out['text'].startswith(POINTS[1]['text']) and POINTS[0]['text'] not in out['text']
    assert '나머지 설명 1개는 그대로 유지' in out['text']
    assert out['claims'] == a['claims']
    assert any(k == 'PRESENTATION_FOCUS' and v['scope'] == 'PART' for k, v in e.s.work.events)


@pytest.mark.parametrize('reply', [
    {'reason': '전체를 다시', 'scope': 'WHOLE', 'claim_ids': []},
    {'reason': '둘 다', 'scope': 'PART', 'claim_ids': ['C1', 'C2']},
    {'reason': '형식 오류', 'scope': 'PART', 'claim_ids': []},
    {'reason': '없는 ID', 'scope': 'PART', 'claim_ids': ['C9']}])
def test_whole_or_an_unusable_choice_keeps_the_full_answer(reply):
    a = two_claim_assessment()
    e, calls = focus_executor(reply)
    plan = g.focus_plan(e, a, {'utterance': '아까 답변 다시 보여줘', 'question': None})
    assert len(calls) == 1 and 'focus' not in plan
    assert cc.compose(a, plan)['text'] == cc.compose(a, g.plan(a))['text']


def test_a_single_claim_or_a_literal_repeat_needs_no_choice_call():
    e, calls = execution()
    a = g.assess(e, SOURCES, ISSUES, '어느 유형인가요?', [])
    assert len(a['claims']) == 1
    plan = g.focus_plan(e, a, {'utterance': '금액 기준만', 'question': None})
    assert 'focus' not in plan and [c[0] for c in calls] == [g.PHASE]
    a2 = two_claim_assessment()
    assert 'focus' not in g.focus_plan(e, a2, None)


def test_render_refuses_a_focus_that_is_not_a_strict_subset():
    a = two_claim_assessment()
    base = g.plan(a)
    for focus in ({'claim_ids': ['C1', 'C2'], 'omitted': 0}, {'claim_ids': ['C9'], 'omitted': 1},
                  {'claim_ids': ['C2'], 'omitted': 0}, {'claim_ids': [], 'omitted': 2}):
        with pytest.raises(ContractError, match='strict subset'):
            cc.render(a, {**base, 'focus': focus})


def test_compose_stage_uses_the_presentation_request_only_when_set():
    a = two_claim_assessment()
    e, calls = focus_executor({'reason': '임기', 'scope': 'PART', 'claim_ids': ['C2']})
    parts = {'READ': {'payload': {}}, 'SELECT': {'payload': {'final_ids': ['source:1'], 'issues': ISSUES}}, 'ASSESS': {'payload': a}}
    full = CompletionExecution.completion_stage(e, 'COMPOSE', {'facts': []}, parts, '다시 보여줘', None, {})
    assert not calls and full['text'] == cc.compose(a, g.plan(a))['text']
    e.presentation_request = {'utterance': '그 사람 임기는 몇 년이야?', 'question': '준법감시인 임면', 'format': 'prose'}
    part = CompletionExecution.completion_stage(e, 'COMPOSE', {'facts': []}, parts, '그 사람 임기는 몇 년이야?', None, {})
    assert [c[0] for c in calls] == [g.FOCUS_PHASE]
    assert part['text'].startswith(POINTS[1]['text']) and POINTS[0]['text'] not in part['text']
    rendered = [v for k, v in e.s.work.events if k == 'COMPOSITION_RENDERED']
    assert rendered[-1]['model_call'] is True and rendered[-1]['focus']['claim_ids'] == ['C2']


class PresentScripted(followup.Scripted):
    """Turn 2 asks for one part of the turn-1 answer; the composer's claim choice is scripted."""

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage') or view['phase']
        schema = body['response_format']['json_schema']['schema']
        if self.turn == 2 and phase in ('memory-resolve', 'memory-resolve-fields'):
            self.log.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view), 'schema': schema})
            return wire(fit(command('ANSWER_PRESENT', target=self.target, stage='COMPOSE'), schema))
        if phase == g.FOCUS_PHASE:
            self.log.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view), 'schema': schema})
            second = next(p['point_id'] for p in view['answer_points'] if '승인 후 보고' in p['text'])
            return wire({'reason': '보고 의무 부분', 'scope': 'PART', 'claim_ids': [second]})
        return super().send_once(body=body, ticket=ticket)


def test_http_present_a_part_of_the_earlier_guided_answer(tree, tmp_path):
    gen, idx = tree
    plan = {'actions': {1: [('LOCATE', '제1조제1항'), ('READ', '제1조제1항'), ('LOCATE', '제1조제2항'), ('READ', '제1조제2항')]},
            'relation': 'PRESENTATION'}
    transport = PresentScripted(followup.BROAD, 'authorized', plan); runtime = tmp_path / 'runtime'
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    profile['candidate_navigation'].update({'guided_action_limit': 6, 'guided_answer_read_rounds': 0})
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=runtime,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app) as api:
        request = {'session_id': 's', 'request_id': '1', 'question': followup.BROAD}
        first = api.post('/v1/rag/ask', json=request)
        assert first.status_code == 200, first.text
        assert [c['text'] for c in first.json()['answer']['claims']] == [followup.FIRST, followup.SECOND]
        db = connect(selected_store(runtime))
        row = db.execute('SELECT id,state FROM goal ORDER BY ordinal DESC LIMIT 1').fetchone()
        transport.target = row['id']; transport.task = json.loads(row['state'])['task']; db.close()
        transport.turn = 2
        second = api.post('/v1/rag/ask', json={**request, 'request_id': '2', 'question': '승인 뒤에 보고는 어떻게 해?'})
        assert second.status_code == 200, second.text
        body = second.json()
        assert body['goal_id'] == row['id'] and body['method_id'] == 'ANSWER_PRESENT' and body['executed'] == ['COMPOSE']
        text = body['answer']['text']
        assert text.startswith(followup.SECOND) and followup.FIRST not in text and '나머지 설명 1개' in text
        assert [c['text'] for c in body['answer']['claims']] == [followup.FIRST, followup.SECOND], 'the saved judgment keeps every claim'
        focus_calls = followup.calls(transport, 2, g.FOCUS_PHASE)
        assert len(focus_calls) == 1 and focus_calls[0]['view']['current_request'] == '승인 뒤에 보고는 어떻게 해?'
        assert not followup.calls(transport, 2, 'investigate') and not followup.calls(transport, 2, 'answer'), 'no search, no rewrite'
        again = api.post('/v1/rag/ask', json={**request, 'request_id': '2', 'question': '승인 뒤에 보고는 어떻게 해?'})
        assert again.json()['answer'] == body['answer'] and len(followup.calls(transport, 2, g.FOCUS_PHASE)) == 1


# ---- 2. clarification in the user's words -------------------------------------------------------

def test_the_clarification_names_the_question_as_the_user_asked_it(tree, tmp_path):
    # ADR-1455 S8: the purpose written by the model carried "상법상 …"; the user never said 상법.
    written = '상법상 ' + NEW + ' (모델이 쓴 목적)'
    transport, responses, (goals, links) = related_run(tree, tmp_path, {
        2: {'question': NEW, 'related': pick(), 'resolve': [new_question(written)], 'check': checker('NEW_TOPIC', written)},
        3: {'question': '제2항은?', 'related': unsure('모델이 쓴 목적'), 'resolve': [], 'check': None}})
    assert goals[1]['state']['task'] == written
    text = responses[2].json()['answer']['text']
    assert responses[2].json()['status'] == 'CLARIFY'
    assert text.startswith('이번 요청이 2번째 질문 “' + NEW + '”에 대한 것인가요?'), text
    assert '상법상' not in text and '모델이 쓴 목적' not in text


# ---- 4. connected means continue; explicit new-question wording means new ------------------------

def test_prompt_rules_connected_continues_and_explicit_new_request_starts_new():
    relate = corrected_memory.RELATE
    assert '조금이라도 이어지면 관련' in relate and '위험관리위원회를 꼭 둬야 해?' in relate
    assert '새 질문 지시' in relate and '"새로 찾아줘"' in relate
    resolve = inspect.getsource(corrected_memory.Memory.resolve)
    assert '조금이라도 이어져 있으면 (가)다' in resolve and '새 질문임을 직접 말하면 내용이 이어져 있어도 (나)다' in resolve
    assert '다른 조문을 묻는 것' in mm.TRANSITION_PROMPT and '새 질문임을 직접 말한 요청은 내용이 이어져 있어도 NEW_TOPIC' in mm.TRANSITION_PROMPT


# ---- 6. unverifiable persisted grants are dropped, not a request failure --------------------------

def test_unrestorable_reference_grants_are_dropped_with_an_event(connected):
    s, idx = connected
    scope = qs.resolve(change('모의승인규정'), None, s.matcher, s.scope, '모의승인규정'); qs.attach(s, scope)
    detail = next(v for v in s.tools.sources.values() if v['document_id'] == 'detail')
    rec, sid = initial(s)
    groups, *_ = relations.catalog(s, [sid], {'U1': rec['unit_reads'][0]}, set())
    group = next(gr for gr in groups if gr['target']['document_id'] == 'detail')
    h, offer = next(pair for pair in group['offers'].values() if pair[1]['extent'] == 'exact')
    read = ur.read(s, relations.hit_for(s, detail['id'], offer['unit_id']), offer, action_state=ur.read_state(s))
    checkpoint = {'selected': {'direct': rec['unit_reads'][0], 'linked': read}, 'contexts': {},
                  'scope_read_grants': deepcopy(s.scope_read_grants), 'direct_scope_hash': scope['hash']}
    events = []
    original = s.repo.event
    s.repo.event = lambda kind, payload: (events.append((kind, deepcopy(payload))), original(kind, payload))[1]
    # A grant whose block no current acquired original witnesses (MAIN176 S4 shape): dropped, the rest restored.
    corrupt = deepcopy(checkpoint); corrupt['scope_read_grants'][detail['id']]['999'] = {'reference_id': 'absent', 'kind': 'REFERENCE'}
    qs.attach(s, scope)
    qs.restore_grants(s, corrupt)
    permitted = qs.permitted_blocks(s, detail['id'])
    assert set(offer['block_ids']) <= permitted and '999' not in permitted
    dropped = [v for k, v in events if k == 'SCOPE_REFERENCE_GRANT_DROPPED']
    assert dropped and dropped[-1]['reason'] == 'NO_CURRENT_VERIFIED_WITNESS'
    assert dropped[-1]['sources'][detail['id']]['block_ids'] == ['999']
    assert '999' not in s.scope_read_grants.get(detail['id'], {})
    # The anchor record itself gone (turn 2 re-selected other blocks): nothing can be re-witnessed, nothing fails.
    bare = {**deepcopy(checkpoint), 'selected': {'linked': read}}
    qs.attach(s, scope); events.clear()
    qs.restore_grants(s, bare)
    assert s.scope_read_grants == {} and [k for k, _ in events] == ['SCOPE_REFERENCE_GRANT_DROPPED']
    assert qs.documents(s) == ['d'], 'the direct scope is unchanged'
    # Grants saved under another search scope are given up as well (no 500 on a scope REPLACE follow-up).
    other = qs.resolve(change('모의승인세칙'), None, s.matcher, s.scope, '모의승인세칙')
    qs.attach(s, other); events.clear()
    qs.restore_grants(s, checkpoint)
    assert s.scope_read_grants == {} and events[-1][1]['reason'] == 'DIRECT_SCOPE_CHANGED'


# ---- 7. MODEL_DECISION_UNRESOLVED with acquired originals answers from them -----------------------

def test_unresolved_investigation_decision_with_originals_answers_as_a_limited_answer():
    e, calls = execution({'answer_points': deepcopy(POINTS[:1]), 'open_questions': []})
    selection = {'issues': ISSUES, 'stop_reason': 'MODEL_DECISION_UNRESOLVED', 'completion_limitations': [], 'final_ids': ['source:1']}
    a = g.assess(e, SOURCES, ISSUES, '준법감시인은 어떻게 임면해?', [], selection=selection)
    assert [c[0] for c in calls] == [g.PHASE], 'the answer model runs once over the acquired originals'
    assert a['claims'] and a['disposition'] == 'LIMITED_ANSWER'
    assert cc.STOP_WORDS['MODEL_DECISION_UNRESOLVED'] in a['guided_reply']['execution_limits']
    assert 'interruption' not in a['guided_reply']
    text = cc.compose(a, g.plan(a))['text']
    assert text.startswith(POINTS[0]['text']) and '판단을 처리하는 과정에서 오류' not in text
    assert '근거 선택 결정을 확정하지 못해' in text


def test_unresolved_investigation_decision_without_originals_still_asks():
    e, calls = execution()
    selection = {'issues': ISSUES, 'stop_reason': 'MODEL_DECISION_UNRESOLVED', 'completion_limitations': []}
    a = g.assess(e, [], ISSUES, '준법감시인은 어떻게 임면해?', [], selection=selection)
    assert not calls and a['claims'] == []
    assert a['guided_reply']['questions'][0]['kind'] == 'DECISION' and a['guided_reply']['interruption']['stage'] == 'SELECT'


# ---- S8 T4 (ADR-1456 run-1): an approved same-purpose command is not refused for the reviewer's task paraphrase ----

def test_reviewer_paraphrase_of_an_unchanged_task_does_not_refuse_a_continue():
    from semantic_runtime.legal_agent import output_contract as output
    task = '외규: 위험관리위원회는 어떤 사항을 심의·의결해?'
    transition = {'contract': 'memory-command-transition-v1', 'target': 'G1', 'before': {'task': task, 'facts': [], 'queries': [], 'source_category': 'ALL'},
                  'after': {'task': task, 'facts': [], 'queries': [], 'source_category': 'ALL'}, 'changed_fields': [], 'requested_entry': 'SELECT',
                  'applies_pending_request': '제24조는?'}
    command = {'method_id': 'RESEARCH_CONTINUE', 'target': 'G1', 'stage': 'SELECT', 'pending_request': 15}
    annotated = {'valid': True, 'reason': '대기 요청 제24조를 1번 질문에서 확인', 'request_relation': 'CONTINUE',
                 'requested_task': task + ' (제24조 관련 확인)'}
    mm.validate_transition(command, transition, annotated)   # accepted: the purpose did not change
    # A purpose change still has to match exactly.
    changed = {**transition, 'after': {**transition['after'], 'task': '외규: 위험관리위원회 구성 요건'}, 'changed_fields': ['task']}
    revise = {'method_id': 'PURPOSE_REVISE', 'target': 'G1', 'stage': 'INTENT', 'task': '외규: 위험관리위원회 구성 요건'}
    with pytest.raises(output.OutputContractError, match='not reflected'):
        mm.validate_transition(revise, changed, {'valid': True, 'reason': '구성', 'request_relation': 'FOLLOWUP', 'requested_task': '외규: 위험관리위원회 설치 의무'})
    mm.validate_transition(revise, changed, {'valid': True, 'reason': '구성', 'request_relation': 'FOLLOWUP', 'requested_task': '외규: 위험관리위원회 구성 요건'})


def test_guided_navigation_prompt_says_background_answers_are_not_originals():
    # ADR-1456 S5 T3 (both runs): the compare question's navigation chose ANSWER "원문을 이미 확보했으므로" with
    # zero originals read in that question (the earlier answers were in dialogue as background).
    from semantic_runtime.legal_agent import guided_navigation as gn
    assert '확보한 원문이 아니며' in gn.PROMPT and '비교·종합하는 새 질문이면' in gn.PROMPT and 'context_only' in gn.PROMPT


def test_prompts_treat_a_law_named_for_an_unanswered_question_as_its_guidance():
    # ADR-1456 S7 run-2: the related judgment said NO because the earlier answer had searched another law.
    assert '금융회사 지배구조법 제21조를 보면 될 거야' in corrected_memory.RELATE and '찾을 곳을 알려 주는 말투는 새 질문이 아니라 가이드다' in corrected_memory.RELATE
    assert '다른 법령이라는 이유만으로 NEW_TOPIC으로 보지 않는다' in mm.TRANSITION_PROMPT


def test_a_self_contradicting_rejection_of_a_same_purpose_command_is_recorded_not_refused():
    from semantic_runtime.legal_agent import output_contract as output
    task = '외규: 위험관리위원회는 어떤 사항을 심의·의결해?'
    transition = {'contract': 'memory-command-transition-v1', 'target': 'G1', 'before': {'task': task, 'facts': [], 'queries': [], 'source_category': 'ALL'},
                  'after': {'task': task, 'facts': [], 'queries': [], 'source_category': 'ALL'}, 'changed_fields': [], 'requested_entry': 'SELECT'}
    command = {'method_id': 'RESEARCH_CONTINUE', 'target': 'G1', 'stage': 'SELECT', 'pending_request': 15}
    review = {'valid': False, 'reason': 'RESEARCH_CONTINUE를 선택해야 하며 task는 제24조 확인으로 갱신되어야 합니다.',
              'request_relation': 'CONTINUE', 'requested_task': '외규: 위험관리위원회 제24조 확인'}
    override = mm.validate_transition(command, transition, review)
    assert override['kind'] == 'COMMAND_CHECK_SELF_CONTRADICTION' and override['relation'] == 'CONTINUE'
    # A genuine disagreement is still a refusal: the reviewer wants a new topic / a changed purpose.
    with pytest.raises(output.OutputContractError):
        mm.validate_transition(command, transition, {**review, 'request_relation': 'NEW_TOPIC'})
    with pytest.raises(output.OutputContractError):
        mm.validate_transition(command, transition, {**review, 'request_relation': 'FOLLOWUP'})
    assert mm.validate_transition(command, transition, {**review, 'valid': True, 'requested_task': task}) is None
    # A rejection that keeps the task is a genuine refusal (e.g. the reviewer disputes the continue_reads choice).
    with pytest.raises(output.OutputContractError, match='읽자는 동의'):
        mm.validate_transition(command, transition, {'valid': False, 'reason': '직전 답변이 읽지 않았다고 안내한 위치를 읽자는 동의로 해석했다.',
                                                     'request_relation': 'CONTINUE', 'requested_task': task})
