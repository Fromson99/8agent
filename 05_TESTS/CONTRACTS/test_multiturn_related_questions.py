"""Multi-turn: choose the related earlier questions first, then decide from them (user design 2026-11-07).

"질문이 10개가 있으면 그중에서 연관된 질문을 선택해(여러 개도 가능), 그 내용을 가지고 내 질문과 함께
어떻게 할지 판단". Each new question runs in its own investigation, so earlier questions of the same chat
are listed from the investigations this conversation was linked to. Actual HTTP/store/pipeline boundary
with a scripted model transport; the scripted INTENT stop marks where the executed request is checked.
"""
from copy import deepcopy
import json
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import memory_methods as mm
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.legal_agent.shortcut_store import selected_store
from test_legal_agent_double_harness import ROOT, wire
from test_memory_runtime_v2 import command, fit
from test_multiturn_structured_scope import tree
from test_multiturn_new_topic_branch import Transport as BranchTransport, Stop, NEW, NAMED, checker, new_question

THIRD = '긴급 승인 예외가 허용되는 조문을 다시 확인해줘'
BACK = '아까 첫 질문으로 돌아가서 제1조제2항도 확인해줘'
BOTH = '앞의 두 질문을 비교해줘'


def pick(*phrases):
    """Scripted selection: the earlier questions whose text contains one of the phrases."""
    def choose(t, view, schema):
        assert all('goal_id' not in q for q in view['questions']), 'judged by order; IDs stay host-side'
        assert list(schema['properties'])[0] == 'reason'
        return {'reason': '모의 선택', **{'q' + str(q['order']): {'related': 'YES' if any(p in (q['question'] or '') for p in phrases) else 'NO',
                'why': '모의 판단'} for q in view['questions']}}
    return choose


class Transport(BranchTransport):
    def __init__(self, plan):
        super().__init__(plan); self.related = []

    def send_once(self, *, body, ticket):
        if self.turn == 1:
            return super().send_once(body=body, ticket=ticket)
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage') or view['phase']
        schema = body['response_format']['json_schema']['schema']
        step = self.script[self.turn]
        if phase.startswith('memory-resolve-related'):
            self.related.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view)})
            return wire(step['related'](self, view, schema))
        if phase.startswith('memory-resolve'):
            self.resolves.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view), 'schema': schema})
            attempt = sum(r['turn'] == self.turn and r['phase'] in ('memory-resolve', 'memory-resolve-repair')
                          for r in self.resolves) - 1
            proposals = step['resolve']
            return wire(fit(proposals[min(attempt, len(proposals) - 1)](self, view), schema))
        return super().send_once(body=body, ticket=ticket)


def run(tree, tmp_path, script):
    gen, idx = tree
    transport = Transport(script); runtime = tmp_path / 'runtime'
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=runtime,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx

    def state():
        db = connect(selected_store(runtime))
        goals = [dict(r) for r in db.execute('SELECT id,session,revision,state,status FROM goal ORDER BY rowid')]
        links = [dict(r) for r in db.execute('SELECT investigation,detached FROM sw_session_link ORDER BY rowid')]
        db.close()
        for g in goals: g['state'] = json.loads(g['state'])
        return goals, links
    responses = []
    with TestClient(app) as api:
        request = {'session_id': 's', 'request_id': '1', 'question': NAMED}
        responses.append(api.post('/v1/rag/ask', json=request))
        assert responses[0].status_code == 200, responses[0].text
        first = state()[0][0]; transport.target = first['id']; transport.task = first['state']['task']
        for n, step in sorted(script.items()):
            transport.turn = n
            responses.append(api.post('/v1/rag/ask', json={**request, 'request_id': str(n), 'question': step['question']}))
    return transport, responses, state()


def second_topic(later):
    """Turn 2 starts a separate question (its own investigation); later turns are the cases under test."""
    return {2: {"question": NEW, "related": pick(), "resolve": [new_question(NEW)], "check": checker("NEW_TOPIC", NEW)}, **later}


def test_an_earlier_topic_is_listed_chosen_and_continued_in_its_own_investigation(tree, tmp_path):
    revise = lambda t, v: command('PURPOSE_REVISE', target=t.target, stage='INTENT', task=NAMED + ' 제1조제2항도 포함')
    transport, responses, (goals, links) = run(tree, tmp_path, second_topic({3: {'question': BACK,
        'related': pick(NAMED), 'resolve': [revise], 'check': checker('FOLLOWUP', NAMED + ' 제1조제2항도 포함')}}))
    first, second = goals[0], goals[1]
    assert first['session'] != second['session'], 'each new question has its own investigation'
    # Selection sees every earlier question of the chat, including the earlier investigation's.
    listed = transport.related[-1]['view']['questions']
    assert [q['order'] for q in listed] == [1, 2] and listed[0]['earlier_topic'] is True and listed[1]['latest'] is True
    assert listed[0]['question'] == NAMED and listed[1]['question'] == NEW
    # The decision sees only the chosen question, and can target only it.
    decision = [r for r in transport.resolves if r['turn'] == 3 and r['phase'] == 'memory-resolve'][-1]
    assert [g['id'] for g in decision['view']['goals']] == [first['id']]
    assert decision['view']['related_selection']['related'][0]['goal_id'] == first['id']
    assert decision['view']['related_selection']['related'][0]['order'] == 1
    # Executed on the earlier question, back in its investigation; the second question is untouched.
    assert first['revision'] == 2 and first['state']['task'] == NAMED + ' 제1조제2항도 포함'
    assert second['revision'] == 1
    active = [l['investigation'] for l in links if l['detached'] is None]
    assert active == [first['session']]
    assert transport.intents[-1]['current_request'] == BACK
    # The checker gets the whole question list and the selection.
    assert len(transport.checks[-1]['question_catalogue']) == 2


def test_no_related_question_leaves_only_a_new_question(tree, tmp_path):
    transport, responses, (goals, links) = run(tree, tmp_path, second_topic({3: {'question': THIRD,
        'related': pick(), 'resolve': [new_question(THIRD)], 'check': checker('NEW_TOPIC', THIRD)}}))
    decision = [r for r in transport.resolves if r['turn'] == 3 and r['phase'] == 'memory-resolve'][-1]
    methods = decision['schema']['properties']['method_id']['enum']
    assert 'CASE_START' in methods and not {'PURPOSE_REVISE', 'RESEARCH_CONTINUE', 'FACT_UPDATE'} & set(methods)
    assert decision['view']['goals'] == []
    assert len(goals) == 3 and goals[2]['state']['task'] == THIRD and transport.intents[-1]['current_request'] == THIRD


def test_several_related_questions_are_background_for_a_new_combined_question(tree, tmp_path):
    transport, responses, (goals, links) = run(tree, tmp_path, second_topic({3: {'question': BOTH,
        'related': pick(NAMED, NEW), 'resolve': [new_question(BOTH)], 'check': checker('NEW_TOPIC', BOTH)}}))
    first, second, third = goals
    decision = [r for r in transport.resolves if r['turn'] == 3 and r['phase'] == 'memory-resolve'][-1]
    assert {g['id'] for g in decision['view']['goals']} == {first['id'], second['id']}
    background = [t for t in transport.intents[-1]['dialogue'] if t.get('related_goal_id')]
    assert {t['related_goal_id'] for t in background} == {first['id'], second['id']}
    assert all(t['context_only'] and 'state_change' not in t for t in background)
    assert third['state']['task'] == BOTH and first['revision'] == second['revision'] == 1


def test_a_rejected_decision_chooses_the_related_questions_again_with_the_reason(tree, tmp_path):
    wrong = lambda t, v: command('PURPOSE_REVISE', target=v['goals'][0]['id'], stage='INTENT', task=BACK)
    reject = lambda t, v: {'valid': False, 'reason': '첫 질문을 가리키는데 다른 질문을 골랐다.', 'request_relation': 'FOLLOWUP', 'requested_task': BACK}
    transport, responses, _ = run(tree, tmp_path, second_topic({3: {'question': BACK,
        'related': pick(NEW), 'resolve': [wrong], 'check': reject}}))
    calls = [r for r in transport.related if r['turn'] == 3]
    assert [c['phase'] for c in calls] == ['memory-resolve-related', 'memory-resolve-related-repair']
    assert '첫 질문을 가리키는데' in json.dumps(calls[1]['view']['previous_decision_rejected'], ensure_ascii=False)
    assert responses[2].json()['status'] == 'CLARIFY'


def test_question_catalogue_orders_and_marks_earlier_questions():
    goals = [{'id': 'A', 'state': {'task': 'PF 딜 의사결정기구'}, 'events': [{'utterance': 'PF?'}], 'earlier_topic': True,
              'previous_response': {'text': 'x' * 900}, 'status': 'READY'},
             {'id': 'B', 'state': {'task': '내부회계관리제도'}, 'events': [{'utterance': '내부회계?'}, {'utterance': '내부회계?'}],
              'status': 'READY'}]
    rows = mm.question_catalogue({'goals': goals, 'recent_dialogue': [
        {'goal_id': 'B', 'speaker': 'assistant', 'text': '외감법 제8조'}]})
    assert [r['order'] for r in rows] == [1, 2] and [r['latest'] for r in rows] == [False, True]
    assert rows[0]['earlier_topic'] and len(rows[0]['answer_start']) == 400
    assert rows[1]['user_requests'] == ['내부회계?'] and rows[1]['answer_start'] == '외감법 제8조'


def unsure(*phrases):
    """Scripted selection that cannot tell whether the request is for the matching questions."""
    def choose(t, view, schema):
        return {'reason': '어느 질문인지 불확실', **{'q' + str(q['order']): {'related': 'UNSURE' if any(p in (q['question'] or '') for p in phrases) else 'NO',
                'why': '모의 판단'} for q in view['questions']}}
    return choose


def test_an_unclear_request_asks_whether_it_is_for_that_question_then_the_reply_applies_it(tree, tmp_path):
    AMBIGUOUS = '제2항은?'
    revise = lambda t, v: command('PURPOSE_REVISE', target=t.target, stage='INTENT', task=NAMED + ' 제2항',
                                  pending_request=v['pending_requests'][-1]['event_id'])
    transport, responses, (goals, links) = run(tree, tmp_path, second_topic({
        3: {'question': AMBIGUOUS, 'related': unsure(NAMED), 'resolve': [], 'check': None},
        4: {'question': '응 첫 번째 질문 맞아', 'related': pick(NAMED), 'resolve': [revise], 'check': checker('FOLLOWUP', NAMED + ' 제2항')}}))
    text = responses[2].json()['answer']['text']
    assert responses[2].json()['status'] == 'CLARIFY'
    assert text.startswith('이번 요청이 1번째 질문 “' + NAMED + '”에 대한 것인가요?') and '새 질문으로 조사하겠습니다' in text
    assert not [r for r in transport.resolves if r['turn'] == 3], 'nothing is decided until the user answers'
    # The reply sees the unapplied request and the question actually asked, and continues that question with it.
    reply = [r for r in transport.related if r['turn'] == 4][0]['view']
    assert reply['pending_requests'][-1]['text'] == AMBIGUOUS
    assert '1번째 질문' in json.dumps(reply['pending_dialogue'], ensure_ascii=False)
    first = goals[0]
    assert first['revision'] == 2 and first['state']['task'] == NAMED + ' 제2항'
    assert transport.intents[-1]['current_request'] == AMBIGUOUS
    assert [l['investigation'] for l in links if l['detached'] is None] == [first['session']]


def test_guidance_for_an_unanswered_question_continues_it_with_a_same_purpose_replan():
    before = {'task': '위험 한도 초과 거래 승인 기구', 'source_category': 'ALL', 'facts': [], 'queries': ['한도 초과']}
    after = {**before, 'queries': ['위험관리위원회 한도 승인']}
    transition = {'before': before, 'after': after}
    command_ = {'method_id': 'RESEARCH_REPLAN', 'stage': 'PLAN'}
    review = {'valid': True, 'reason': '같은 질문에 단서를 준 요청', 'request_relation': 'CONTINUE', 'requested_task': before['task']}
    mm.validate_transition(command_, transition, review)
    import pytest
    from semantic_runtime.legal_agent import output_contract as output
    with pytest.raises(output.OutputContractError):   # a changed purpose is not a same-question continuation
        mm.validate_transition(command_, {'before': before, 'after': {**after, 'task': '다른 목적'}},
                               {**review, 'requested_task': '다른 목적'})


def test_question_list_says_whether_the_answer_was_found_and_what_it_left_open():
    goals = [{'id': 'A', 'state': {'task': '한도 초과 거래 승인 기구'}, 'events': [], 'status': 'READY',
              'previous_response': {'text': '찾지 못했습니다', 'legal_conclusion_confirmed': False, 'answer_coverage': 'INSUFFICIENT',
                  'guidance': {'questions': [{'question': '어느 규정을 볼까요?'}],
                               'unread_connections': [{'target_label': '제27조(위험관리기준)'}]}}}]
    row = mm.question_catalogue({'goals': goals, 'recent_dialogue': []})[0]
    assert row['answer_found'] is False and row['asked_user'] == ['어느 규정을 볼까요?']
    # Linked-but-unread lists are mechanical (same section, borrowing rules); they are not a relevance signal.
    assert 'mentioned_unread' not in row


def test_each_question_is_judged_and_the_server_maps_goal_ids():
    ids = ['GA', 'GB', 'GC']
    judged = {'reason': '2번과 3번', 'q1': {'related': 'UNSURE', 'why': '불확실'},
              'q2': {'related': 'YES', 'why': 'x'}, 'q3': {'related': 'YES', 'why': 'y'}}
    value = mm.check_related(judged, ids)
    assert [r['goal_id'] for r in value['related']] == ['GB', 'GC'] and mm.stored_related(value, ids) == ['GB', 'GC']
    assert [r['goal_id'] for r in value['unsure']] == ['GA']
    import pytest
    from semantic_runtime.legal_agent import output_contract as output
    from semantic_runtime.legal_agent.errors import ContractError
    with pytest.raises(output.OutputContractError):   # a question left unjudged
        mm.check_related({'reason': '누락', 'q1': {'related': 'YES', 'why': 'x'}}, ids)
    with pytest.raises(ContractError):
        mm.stored_related({'reason': '변조', 'related': [{'order': 1, 'goal_id': 'GB', 'why': 'x'}]}, ids)
    schema = mm.related_schema(ids)
    assert list(schema['properties']) == ['reason', 'q1', 'q2', 'q3'] and schema['required'] == ['reason', 'q1', 'q2', 'q3']


def scoped_new_question(quote):
    return lambda t, v: command('CASE_START', document_scope_mode='AUTHORIZED', stage='INTENT', task='모의승인규정 제1조제2항',
        facts=[], queries=['제2항'], search_scope_change={'operation': 'REPLACE', 'targets': [{'document': '모의승인규정',
        'structure': None, 'selection': None}], 'user_quote': quote})


def test_a_new_question_may_take_its_omitted_law_name_from_a_related_question(tree, tmp_path):
    # "그럼 제2항은?" names no regulation; the related turn-1 question said "모의승인규정".
    transport, responses, (goals, links) = run(tree, tmp_path, second_topic({3: {'question': '그럼 제2항은?',
        'related': pick(NAMED), 'resolve': [scoped_new_question('모의승인규정')], 'check': checker('NEW_TOPIC', '모의승인규정 제1조제2항')}}))
    assert len(transport.intents) == 2, responses[2].text   # turn 2 and turn 3 reached INTENT
    assert transport.intents[-1]['current_request'] == '그럼 제2항은?'
    assert goals[-1]['state']['search_scope']['targets'][0]['document_id'] == 'd'


def test_an_unrelated_question_cannot_borrow_a_scope_quote(tree, tmp_path):
    transport, responses, (goals, links) = run(tree, tmp_path, second_topic({3: {'question': '그럼 제2항은?',
        'related': pick(), 'resolve': [scoped_new_question('모의승인규정')], 'check': checker('NEW_TOPIC', '모의승인규정 제1조제2항')}}))
    # Caught while the command can be corrected; after the one correction the user is asked for the law name.
    assert responses[2].json()['status'] == 'CLARIFY' and '법령이나 문서 이름' in responses[2].json()['answer']['text']
    assert len(transport.intents) == 1, 'only turn 2 reached INTENT'
    assert len(transport.checks) == 1, 'only turn 2 was reviewed; neither turn-3 proposal reached the review'


def test_scope_quote_must_be_one_span_of_the_users_own_words():
    texts = ['자본시장법상 단기매매차익 반환 대상은 누구야?', '그럼 미공개중요정보 이용은 어떻게 금지돼?']
    change = lambda quote, doc='자본시장과 금융투자업에 관한 법률': {'operation': 'REPLACE', 'user_quote': quote,
        'targets': [{'document': doc, 'structure': None, 'selection': None}]}
    assert mm.scope_quote_issues({'method_id': 'CASE_START', 'search_scope_change': change('자본시장법상')}, texts) == []
    joined = mm.scope_quote_issues({'method_id': 'CASE_START', 'search_scope_change': change('자본시장법상 미공개중요정보 이용행위 금지')}, texts)
    assert joined[0]['code'] == 'SCOPE_QUOTE_NOT_USER_WORDS' and joined[0]['expected_constraint']['user_texts'] == texts
    # A follow-up command keeps the lexical contract: the named target must be inside the quote.
    follow = mm.scope_quote_issues({'method_id': 'RESEARCH_REPLAN', 'search_scope_change': change('제368조', '상법')}, ['제368조에서 정관으로 다르게 정할 수 있어?'])
    assert follow[0]['code'] == 'SCOPE_NAME_NOT_IN_QUOTE'
    assert mm.scope_quote_issues({'method_id': 'RESEARCH_REPLAN', 'search_scope_change': {'operation': 'KEEP', 'targets': [], 'user_quote': ''}}, []) == []


def test_a_joined_scope_quote_is_corrected_before_execution(tree, tmp_path):
    transport, responses, (goals, links) = run(tree, tmp_path, second_topic({3: {'question': '그럼 제2항은?',
        'related': pick(NAMED), 'resolve': [scoped_new_question('모의승인규정 제2항'), scoped_new_question('모의승인규정')],
        'check': checker('NEW_TOPIC', '모의승인규정 제1조제2항')}}))
    phases = [r['phase'] for r in transport.resolves if r['turn'] == 3]
    assert phases[0] == 'memory-resolve' and 'memory-resolve-repair' in phases
    repair = [r for r in transport.resolves if r['turn'] == 3 and r['phase'] == 'memory-resolve-repair'][0]['view']
    assert 'SCOPE_QUOTE_NOT_USER_WORDS' in json.dumps(repair['repair_contract'], ensure_ascii=False)
    assert NAMED in json.dumps(repair['repair_contract'], ensure_ascii=False), 'the allowed user texts are shown'
    assert len(transport.checks) == 2, 'turn 2 and the corrected turn-3 command; the joined quote never reached the review'
    assert len(transport.intents) == 2 and goals[-1]['state']['search_scope']['targets'][0]['document_id'] == 'd'


def test_no_related_question_and_no_target_asks_which_question_by_name(tree, tmp_path):
    need = lambda t, v: command('NEED_TARGET', stage='NONE', reason='법령명이 없어 대상을 특정할 수 없음')
    transport, responses, _ = run(tree, tmp_path, second_topic({3: {'question': '제2조는?', 'related': pick(),
        'resolve': [need], 'check': lambda t, v: {'valid': True, 'reason': '모의', 'request_relation': 'UNCLEAR', 'requested_task': None}}}))
    text = responses[2].json()['answer']['text']
    assert responses[2].json()['status'] == 'CLARIFY'
    assert text.startswith('이번 요청이 어느 질문에 대한 것인가요? 1번째 “' + NAMED + '”, 2번째 “' + NEW + '”')
    assert '법령이나 문서 이름' in text and '특정할 수 없음' not in text


def test_a_reply_naming_the_question_with_a_non_executing_method_is_chosen_again(tree, tmp_path):
    # ADR-1454 S8: the reply "1번째 질문 …" came with ANSWER_PRESENT + the pending request; the field repair kept
    # the method and failed again. The pending request needs a method that executes it, so the method is re-chosen.
    AMBIGUOUS = '제2항은?'
    present = lambda t, v: command('ANSWER_PRESENT', target=t.target, stage='COMPOSE',
                                   pending_request=v['pending_requests'][-1]['event_id'])
    revise = lambda t, v: command('PURPOSE_REVISE', target=t.target, stage='INTENT', task=NAMED + ' 제2항',
                                  pending_request=v['pending_requests'][-1]['event_id'])
    transport, responses, (goals, links) = run(tree, tmp_path, second_topic({
        3: {'question': AMBIGUOUS, 'related': unsure(NAMED), 'resolve': [], 'check': None},
        4: {'question': '1번째 질문 기준으로 봐줘', 'related': pick(NAMED), 'resolve': [present, revise],
            'check': checker('FOLLOWUP', NAMED + ' 제2항')}}))
    phases = [r['phase'] for r in transport.resolves if r['turn'] == 4]
    assert phases[0] == 'memory-resolve' and 'memory-resolve-repair' in phases, phases
    repair = [r for r in transport.resolves if r['turn'] == 4 and r['phase'] == 'memory-resolve-repair'][0]
    assert 'PENDING_REQUEST_METHOD' in json.dumps(repair['view']['repair_contract'], ensure_ascii=False)
    assert 'ANSWER_PRESENT' in repair['schema']['properties']['method_id']['enum'], 'the whole menu is offered again'
    first = goals[0]
    assert first['revision'] == 2 and first['state']['task'] == NAMED + ' 제2항'
    assert transport.intents[-1]['current_request'] == AMBIGUOUS


def test_a_user_shorthand_of_a_law_title_resolves_one_document():
    from types import SimpleNamespace
    from semantic_runtime.legal_agent import query_scope as qs
    titles = {'g': '금융회사의 지배구조에 관한 법률', 'gr': '금융회사의 지배구조에 관한 법률 시행령',
              'c': '자본시장과 금융투자업에 관한 법률', 'cr': '자본시장과 금융투자업에 관한 법률 시행령', 's': '상법'}
    matcher = SimpleNamespace(document_context={d: {'document_title': t} for d, t in titles.items()},
                              documents=dict(titles), document_aliases={}, units={})
    def scope(name, quote):
        change = {'operation': 'REPLACE', 'user_quote': quote, 'targets': [{'document': name, 'structure': None, 'selection': None}]}
        return [t['document_id'] for t in qs.resolve(change, None, matcher, list(titles), quote)['targets']]
    assert scope('금융회사 지배구조법', '금융회사 지배구조법 제21조를 보면 될 거야') == ['g']
    assert scope('자본시장법', '자본시장법 보면 돼') == ['c']
    assert scope('자본시장법 시행령', '자본시장법 시행령 보면 돼') == ['cr']
    assert scope('상법', '상법 보면 돼') == ['s'], 'an exact title still wins'
    import pytest
    with pytest.raises(qs.UnresolvedScope):   # not a shorthand of any title (different first character)
        scope('지배구조법', '지배구조법 보면 돼')
    assert not qs.abbreviates('외감법', '주식회사 등의 외부감사에 관한 법률')
