"""Multi-turn branch: a new topic starts a new question; a reply to the clarification executes it.

Field photos 2026-11-07 (B05 guided mode): an unrelated question after a guided answer ended in
"기존 질문의 조사를 이어갈까요, 아니면 … 목적을 바꿀까요?" (no new-question option), and the reply
"새롭게 질문을 해줘" was answered as plain guidance. Actual HTTP/store/pipeline boundary with a
scripted model transport only; the scripted INTENT stop marks where the executed request is checked.
"""
from copy import deepcopy
import json
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import memory_methods as mm
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.legal_agent.shortcut_store import selected_store
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from test_memory_runtime_v2 import command, fit
from test_multiturn_structured_scope import tree
from test_guided_continue_bounds import Transport as GuidedTransport, NAMED

NEW = '긴급 승인 예외 기준을 알려줘'
NEW_REPLY = '새롭게 질문을 해줘'
CONTINUE_REPLY = '이전 질문에 이어서 해줘'


class Stop(RuntimeError):
    pass


class Transport(GuidedTransport):
    """Turn 1 = the guided harness; later turns follow the scripted resolver/checker plan."""

    def __init__(self, plan):
        super().__init__(NAMED, 'named', {'reads': 1})
        self.script = plan; self.resolves = []; self.checks = []; self.routes = []; self.intents = []

    def send_once(self, *, body, ticket):
        if self.turn == 1:
            return super().send_once(body=body, ticket=ticket)
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage') or view['phase']
        schema = body['response_format']['json_schema']['schema']
        self.log.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view), 'schema': schema})
        step = self.script[self.turn]
        if phase == 'source-request-route':
            self.routes.append({**deepcopy(view), '_system': body['messages'][0]['content']})
            return wire({'mode': 'CASE', 'answer': '', 'reason': '모의 분류'})
        if phase.startswith('memory-resolve'):
            self.resolves.append({'phase': phase, 'view': deepcopy(view), 'schema': schema})
            attempt = sum(r['phase'] == 'memory-resolve' or r['phase'] == 'memory-resolve-repair' for r in self.resolves) - 1
            proposals = step['resolve']
            value = proposals[min(attempt, len(proposals) - 1)](self, view)
            return wire(fit(value, schema))
        if phase == 'memory-command-check':
            self.checks.append(deepcopy(view))
            return wire(step['check'](self, view))
        if phase == 'memory-intent':
            self.intents.append(deepcopy(view))
            raise Stop('intentional stop: the executed request is checked at INTENT')
        raise AssertionError(phase)


def pending_id(view):
    rows = view.get('pending_requests') or view.get('context', {}).get('pending_requests') or []
    return rows[-1]['event_id']


def run(tree, tmp_path, script):
    gen, idx = tree
    transport = Transport(script); runtime = tmp_path / 'runtime'
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=runtime,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx

    def goals():
        db = connect(selected_store(runtime))
        rows = [dict(r) for r in db.execute('SELECT id,revision,state,status FROM goal ORDER BY ordinal')]
        events = [dict(r) for r in db.execute("SELECT goal,utterance,command,kind FROM event WHERE goal IS NOT NULL ORDER BY id")]
        db.close()
        for r in rows: r['state'] = json.loads(r['state'])
        return rows, events
    responses = []
    with TestClient(app) as api:
        request = {'session_id': 's', 'request_id': '1', 'question': NAMED}
        responses.append(api.post('/v1/rag/ask', json=request))
        assert responses[0].status_code == 200, responses[0].text
        first = goals()[0][0]; transport.target = first['id']; transport.task = first['state']['task']
        for n, question in sorted((n, s['question']) for n, s in script.items()):
            transport.turn = n
            responses.append(api.post('/v1/rag/ask', json={**request, 'request_id': str(n), 'question': question}))
    return transport, responses, goals()


def new_question(task, category='KEEP'):
    return lambda t, v: command('CASE_START', document_scope_mode='AUTHORIZED', stage='INTENT', task=task, facts=[],
                                queries=['긴급 승인'], source_category=category)


def checker(relation, task):
    return lambda t, v: {'valid': True, 'reason': '모의 대조', 'request_relation': relation, 'requested_task': task}


def test_new_question_drops_the_marker_copied_from_the_previous_turn(tree, tmp_path):
    # The resolver copies the previous turn's "외규:" marker; the checker reads the plain request.
    transport, responses, (goals, events) = run(tree, tmp_path, {2: {'question': NEW,
        'resolve': [new_question('외규: ' + NEW, 'external')], 'check': checker('NEW_TOPIC', NEW)}})
    assert responses[1].status_code >= 400 and transport.intents, responses[1].text
    assert len(goals) == 2 and goals[1]['state']['task'] == NEW
    # Neither the marker nor the 외규 category of the previous turn is this request's configuration.
    assert goals[1]['state']['source_category'] == 'ALL'
    # No unapplied request: the routing gate gets no reply-to-clarification instruction.
    assert transport.routes[-1]['pending_requests'] == [] and 'pending_requests는' not in transport.routes[-1]['_system']
    assert transport.intents[0]['current_request'] == NEW
    assert [r['phase'] for r in transport.resolves].count('memory-resolve-repair') == 0
    # The previous goal is untouched.
    assert goals[0]['revision'] == 1 and goals[0]['state']['task'] == NAMED


def test_checker_paraphrase_of_a_verbatim_new_question_is_not_a_conflict(tree, tmp_path):
    transport, responses, (goals, _) = run(tree, tmp_path, {2: {'question': NEW,
        'resolve': [new_question(NEW)], 'check': checker('NEW_TOPIC', '긴급 승인 예외 기준 확인')}})
    assert transport.intents and len(goals) == 2 and goals[1]['state']['task'] == NEW
    assert len(transport.checks) == 1, 'accepted on the first proposal; no repair round'


def test_a_paraphrased_follow_up_task_is_still_checked(tree, tmp_path):
    # Only the user's own request text is exempt; a model-written purpose must still match the review.
    revise = lambda t, v: command('PURPOSE_REVISE', target=t.target, stage='INTENT', task='승인 예외의 범위')
    transport, responses, (goals, _) = run(tree, tmp_path, {2: {'question': NEW,
        'resolve': [revise], 'check': checker('FOLLOWUP', '긴급 승인 예외 기준')}})
    assert responses[1].status_code == 200 and responses[1].json()['status'] == 'CLARIFY'
    assert len(transport.checks) == 2 and not transport.intents


def disagreement(tree, tmp_path, third):
    """Turn 2: the resolver keeps continuing the old goal while the checker reads a new topic."""
    revise = lambda t, v: command('PURPOSE_REVISE', target=t.target, stage='INTENT', task=NEW)
    return run(tree, tmp_path, {2: {'question': NEW, 'resolve': [revise], 'check': lambda t, v: {
        'valid': False, 'reason': '다른 제도를 묻는 새 질문이다.', 'request_relation': 'NEW_TOPIC', 'requested_task': NEW}},
        3: third})


def test_disagreement_asks_new_or_continue_and_new_reply_starts_the_pending_question(tree, tmp_path):
    start = lambda t, v: command('CASE_START', document_scope_mode='AUTHORIZED', stage='INTENT', task=NEW,
                                 facts=[], queries=['긴급 승인'], pending_request=pending_id(v))
    transport, responses, (goals, events) = disagreement(tree, tmp_path, {'question': NEW_REPLY,
        'resolve': [start], 'check': checker('NEW_TOPIC', NEW)})
    text = responses[1].json()['answer']['text']
    assert responses[1].json()['status'] == 'CLARIFY'
    assert '새 질문으로 조사할까요' in text and NEW in text and '이어서 확인할까요' in text
    assert '이어갈까요' not in text
    # Turn 3: the routing gate and the resolver both see the unapplied request by event ID.
    assert transport.routes[-1]['pending_requests'][-1]['text'] == NEW and 'pending_requests는' in transport.routes[-1]['_system']
    step1 = [r for r in transport.resolves if r['phase'] == 'memory-resolve'][-1]
    assert 'pending_request' in step1['schema']['properties'], 'the pending choice is part of the branch decision'
    assert transport.checks[-1]['transition']['applies_pending_request'] == NEW
    # A new goal executes the pending question exactly; the old goal and its answer stay.
    assert len(goals) == 2 and goals[1]['state']['task'] == NEW and goals[0]['revision'] == 1
    assert transport.intents[-1]['current_request'] == NEW
    started = [e for e in events if e['goal'] == goals[1]['id']]
    assert started[0]['utterance'] == NEW_REPLY and json.loads(started[0]['command'])['pending_request'] is not None


def test_continue_reply_applies_the_pending_question_to_the_previous_goal(tree, tmp_path):
    revise = lambda t, v: command('PURPOSE_REVISE', target=t.target, stage='INTENT', task=NEW,
                                  pending_request=pending_id(v))
    transport, responses, (goals, _) = disagreement(tree, tmp_path, {'question': CONTINUE_REPLY,
        'resolve': [revise], 'check': checker('FOLLOWUP', NEW)})
    assert len(goals) == 1 and goals[0]['revision'] == 2 and goals[0]['state']['task'] == NEW
    assert transport.intents[-1]['current_request'] == NEW


def test_pending_request_is_offered_only_after_an_unapplied_request():
    context = {'utterance': NEW_REPLY, 'goals': [], 'knowledge': [], 'recent_dialogue': [
        {'event_id': 7, 'speaker': 'user', 'text': NAMED, 'clarification': False},
        {'event_id': 7, 'speaker': 'assistant', 'text': '답변', 'clarification': False},
        {'event_id': 9, 'speaker': 'user', 'text': NEW, 'clarification': True},
        {'event_id': 9, 'speaker': 'assistant', 'text': '새 질문으로 조사할까요?', 'clarification': True}]}
    assert mm.pending_requests(context) == [{'event_id': 9, 'text': NEW}]
    answered = {**context, 'recent_dialogue': context['recent_dialogue'][:2]}
    assert mm.pending_requests(answered) == []
    assert mm.effective_request({'pending_request': 9}, context) == NEW
    with pytest.raises(ValueError):
        mm.effective_request({'pending_request': 7}, context)
    assert mm.effective_request({'pending_request': None}, context) == NEW_REPLY


@pytest.mark.parametrize('task,executed,expected', [
    ('외규: ' + NEW, NEW, NEW),
    (NEW, '내규: ' + NEW, '내규: ' + NEW),
    ('외규: 승인 예외', '내규: ' + NEW, '내규: 승인 예외'),
    ('승인 예외', NEW, '승인 예외'),
])
def test_new_question_marker_is_the_executed_requests_own(task, executed, expected):
    assert mm.bind_request_marker(task, executed) == expected


@pytest.mark.parametrize('question,category,expected', [
    ('내규 기준으로 ' + NEW, 'internal', 'internal'),
    ('외규: ' + NEW, 'internal', 'external'),
])
def test_new_question_keeps_a_category_the_request_itself_names(tree, tmp_path, question, category, expected):
    transport, responses, (goals, _) = run(tree, tmp_path, {2: {'question': question,
        'resolve': [new_question(question, category)], 'check': checker('NEW_TOPIC', question)}})
    # The fixture documents carry no 내규/외규 category, so retrieval may stop later; the command is checked here.
    assert len(transport.checks) == 1 and len(goals) == 2 and goals[1]['state']['source_category'] == expected, responses[1].text
