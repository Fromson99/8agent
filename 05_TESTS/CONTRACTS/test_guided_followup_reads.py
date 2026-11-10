"""Located-original reserve, proposed next reads and partial answer updates across turns.

Actual HTTP/store/pipeline boundary with a scripted model transport only.
"""
from copy import deepcopy
import json
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import memory_methods as mm, guided_answer as ga, law_candidates as lc
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.legal_agent.shortcut_store import selected_store
from test_guided_continue_bounds import Transport, find, fill, BROAD, OFFER
from test_legal_agent_double_harness import ROOT, wire
from test_memory_runtime_v2 import command, fit, related_all
from test_multiturn_structured_scope import tree
from test_definition_context_recovery import context_probe

FIRST = '제1조제1항은 각 호의 승인 기준을 적용합니다.'
SECOND = '제1조제2항은 승인 후 보고하도록 정합니다.'
FOLLOWUP = '제1조제2항도 확인해줘'


def method(branch):
    rule = branch['properties']['method_id']
    return rule.get('const') or (rule.get('enum') or [None])[0]


def coordinate(row):
    path = row.get('path') or []
    return path[-1].get('coordinate') if path and isinstance(path[-1], dict) else None


class Scripted(Transport):
    """Each investigation call pops one scripted action of the current turn."""

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage') or view['phase']
        if phase.startswith('memory-resolve-related'):  # every earlier question (pre-selection behavior)
            return wire(related_all(body['response_format']['json_schema']['schema']))
        schema = body['response_format']['json_schema']['schema']
        if phase in ('memory-resolve', 'memory-resolve-fields'):
            self.log.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view), 'schema': schema})
            reads = ((schema.get('properties') or {}).get('continue_reads') or {}).get('items', {}).get('enum', [])
            return wire(fit(command('RESEARCH_CONTINUE', target=self.target, stage='SELECT', continue_reads=reads), schema))
        if 'open_questions' in schema.get('properties', {}):
            self.log.append({'turn': self.turn, 'phase': 'answer', 'view': deepcopy(view), 'schema': schema})
            issue = find(schema, 'issue_refs')['items']['enum'][:1]
            originals = view.get('originals', [])
            value = {'open_questions': [], 'answer_points': []}
            props = schema['properties']
            if self.turn == 1:
                first = next(o['id'] for o in originals if '각 호의 승인 기준' in o['text'])
                value['answer_points'] = [{'issue_refs': issue, 'evidence_refs': [first], 'text': FIRST}]
                second = [o['id'] for o in originals if '승인 후 보고' in o['text']]
                if second:
                    value['answer_points'].append({'issue_refs': issue, 'evidence_refs': second[:1], 'text': SECOND})
                else:
                    value['open_questions'] = [{'issue_refs': issue, **OFFER}]
                if 'next_reads' in props:
                    wanted = [r['location_id'] for r in view.get('readable_locations', []) if '제2항' in r['label'] or '②' in r['label']]
                    value['next_reads'] = wanted[:1]
            else:
                second = next(o['id'] for o in originals if '승인 후 보고' in o['text'])
                value['answer_points'] = [{'issue_refs': issue, 'evidence_refs': [second], 'text': SECOND}]
                if 'kept_points' in props:
                    value['kept_points'] = [p['point_id'] for p in view.get('previous_answer_points', [])]
            for name in ('next_reads', 'kept_points'):
                if name in props: value.setdefault(name, [])
            return wire(value)
        if phase == 'investigate':
            self.log.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view), 'schema': schema})
            options = {}
            for branch in schema.get('anyOf', []):
                options.setdefault(branch['properties']['choice'].get('const'), []).append(branch)
            queue = self.plan['actions'].setdefault(self.turn, [])
            step = queue[0] if queue else ('ANSWER',)
            kind = step[0]
            if kind == 'ANSWER' and 'ANSWER' not in options and 'FOLLOW' in options:
                return wire(fill(options['FOLLOW'][0]))  # one connection lookup before answering
            queue[:1] = []
            if kind == 'ANSWER':
                branch = options['ANSWER'][0]
                value = fill(branch)
                if 'basis_refs' in branch['properties']:  # finish on every presented original
                    value['basis_refs'] = list(branch['properties']['basis_refs']['items']['enum'])
                return wire(value)
            if kind == 'LOCATE':
                branch = next(b for b in options['SEARCH'] if 'structure_filter' in b['properties'])
                value = fill(branch)
                value['structure_filter'] = {'coordinate': step[1], 'title': '', 'coordinate_scope': 'body'}
                return wire(value)
            if kind == 'QUERY':
                branch = next(b for b in options['SEARCH'] if 'queries' in b['properties'] and 'structure_filter' not in b['properties'])
                return wire({**fill(branch), 'queries': [step[1]]})
            if kind == 'ASK':
                value = fill(options['ASK_USER'][0])
                value['questions'] = [{**value['questions'][0], 'kind': step[1],
                    'uncertainty': '질문 범위가 넓습니다.', 'question': '이 범위에서 답변할까요, 다른 부분도 볼까요?'}]
                return wire(value)
            if kind == 'READ':
                value = fill(options['READ'][0])
                target = next(r['target'] for r in view['read_candidates'] if coordinate(r) == step[1])
                value['selections'] = [{**value['selections'][0], 'target': target}]
                return wire(value)
            raise AssertionError(step)
        return super().send_once(body=body, ticket=ticket)


def run(tree, tmp_path, plan, *, turns, navigation):
    gen, idx = tree
    plan.setdefault('relation', 'CONTINUE')
    transport = Scripted(BROAD, 'authorized', plan); runtime = tmp_path / 'runtime'
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    profile['candidate_navigation'].update(navigation)
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=runtime,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    responses = []
    with TestClient(app) as api:
        request = {'session_id': 's', 'request_id': '1', 'question': BROAD}
        responses.append(api.post('/v1/rag/ask', json=request))
        assert responses[0].status_code == 200, responses[0].text
        db = connect(selected_store(runtime))
        row = db.execute('SELECT id,state FROM goal ORDER BY ordinal DESC LIMIT 1').fetchone()
        transport.target = row['id']; transport.task = json.loads(row['state'])['task']; db.close()
        for n in range(2, turns + 1):
            transport.turn = n
            responses.append(api.post('/v1/rag/ask', json={**request, 'request_id': str(n), 'question': FOLLOWUP}))
    return transport, responses


def calls(transport, turn, phase):
    return [r for r in transport.log if r['turn'] == turn and r['phase'] == phase]


def test_reads_are_not_counted_and_after_the_limit_only_reads_run(tree, tmp_path):
    plan = {'actions': {1: [('LOCATE', '제1조제1항'), ('READ', '제1조제1항'), ('LOCATE', '제1조제2항'), ('READ', '제1조제2항')]}}
    transport, responses = run(tree, tmp_path, plan, turns=1,
                               navigation={'guided_action_limit': 2, 'guided_answer_read_rounds': 0})
    nav = calls(transport, 1, 'investigate')
    budgets = [r['view']['action_budget'] for r in nav]
    # READ never spends the search allowance; after two searches only READ/ANSWER run.
    assert [b['used'] for b in budgets[:4]] == [0, 1, 1, 2]
    assert budgets[1]['reads_free'] and budgets[2]['reads_this_request'] == 1
    assert 'read_only' not in budgets[2] and budgets[3]['read_only'] is True
    answer = calls(transport, 1, 'answer')
    texts = [o['text'] for o in answer[0]['view']['originals']]
    assert any('각 호의 승인 기준' in t for t in texts) and any('승인 후 보고' in t for t in texts)
    assert [c['text'] for c in responses[0].json()['answer']['claims']] == [FIRST, SECOND]


def test_read_rounds_bound_free_reads_and_answer_from_what_was_read(tree, tmp_path):
    plan = {'actions': {1: [('LOCATE', '제1조제1항'), ('READ', '제1조제1항'), ('LOCATE', '제1조제2항'), ('READ', '제1조제2항')]}}
    transport, responses = run(tree, tmp_path, plan, turns=1,
                               navigation={'guided_action_limit': 6, 'guided_read_rounds': 1, 'guided_answer_read_rounds': 0})
    nav = calls(transport, 1, 'investigate')
    # The chosen READ runs; then the request answers instead of asking for more READ decisions.
    assert len(nav) == 2 and nav[1]['view']['action_budget']['read_rounds_left'] == 1
    answer = calls(transport, 1, 'answer')
    texts = [o['text'] for o in answer[0]['view']['originals']]
    assert any('각 호의 승인 기준' in t for t in texts) and not any('승인 후 보고' in t for t in texts)
    assert responses[0].status_code == 200


def test_scope_question_after_reading_is_asked_after_the_answer(tree, tmp_path):
    plan = {'actions': {1: [('LOCATE', '제1조제1항'), ('READ', '제1조제1항'), ('ASK', 'SCOPE')]}}
    transport, responses = run(tree, tmp_path, plan, turns=1,
                               navigation={'guided_action_limit': 6, 'guided_answer_read_rounds': 6})
    answer = calls(transport, 1, 'answer')
    # The question no longer replaces the explanation of what was read.
    assert len(answer) == 1 and answer[0]['view']['investigation_questions'][0]['kind'] == 'SCOPE'
    assert 'next_reads' not in answer[0]['schema']['properties']
    body = responses[0].json()
    assert [c['text'] for c in body['answer']['claims']] == [FIRST]
    assert '다음 방향을 기다립니다' not in body['answer']['text']


def test_fact_question_after_reading_is_asked_after_the_explanation(tree, tmp_path):
    plan = {'actions': {1: [('LOCATE', '제1조제1항'), ('READ', '제1조제1항'), ('ASK', 'FACT')]}}
    transport, responses = run(tree, tmp_path, plan, turns=1,
                               navigation={'guided_action_limit': 6, 'guided_answer_read_rounds': 6})
    # Since 2026-11-10 (ADR-1478 cm-006/021) the acquired original is explained before the FACT
    # question; the question stays for the user and nothing is read further in this request.
    answer = calls(transport, 1, 'answer')
    assert len(answer) == 1 and answer[0]['view'].get('investigation_questions')
    assert 'readable_locations' not in answer[0]['view'] and 'next_reads' not in answer[0]['schema']['properties']
    body = responses[0].json()
    assert [c['text'] for c in body['answer']['claims']] == [FIRST]


def test_after_the_limit_a_new_search_is_not_executed(tree, tmp_path):
    plan = {'actions': {1: [('LOCATE', '제1조제1항'), ('LOCATE', '제1조제2항')]}}
    transport, responses = run(tree, tmp_path, plan, turns=1,
                               navigation={'guided_action_limit': 1, 'guided_answer_read_rounds': 0})
    nav = calls(transport, 1, 'investigate')
    assert len(nav) == 2 and nav[1]['view']['action_budget']['read_only'] is True
    # The proposed search is not executed: nothing was read, so no answer model call.
    assert not calls(transport, 1, 'answer')
    assert responses[0].status_code == 200


def test_answer_selected_read_is_read_in_the_same_request_and_answered_again(tree, tmp_path):
    # The search limit stops right after locating 제1조제2항; the answer says it must
    # be read, the server reads it without a search or an action, and answers again.
    plan = {'actions': {1: [('LOCATE', '제1조제1항'), ('READ', '제1조제1항'), ('LOCATE', '제1조제2항'),
                            ('QUERY', '승인 보고')]}}
    transport, responses = run(tree, tmp_path, plan, turns=1,
                               navigation={'guided_action_limit': 3, 'guided_answer_read_rounds': 6})
    assert responses[0].status_code == 200, responses[0].text
    answers = calls(transport, 1, 'answer')
    assert len(answers) == 2
    assert not any('승인 후 보고' in o['text'] for o in answers[0]['view']['originals'])
    assert any('제2항' in r['label'] for r in answers[0]['view']['readable_locations'])
    assert any('승인 후 보고' in o['text'] for o in answers[1]['view']['originals'])
    assert 'readable_locations' not in answers[1]['view'] or not any(
        '제2항' in r['label'] for r in answers[1]['view']['readable_locations'])
    # No navigation decision read it (the script never READs 제1조제2항); the server did.
    assert not plan['actions'][1]
    assert [c['text'] for c in responses[0].json()['answer']['claims']] == [FIRST, SECOND]


def test_proposed_read_is_read_without_search_and_kept_points_are_reused(tree, tmp_path):
    # Turn 1 locates 제1조제2항 and the answer proposes it for later (answer-time reads off).
    plan = {'actions': {1: [('LOCATE', '제1조제1항'), ('READ', '제1조제1항'), ('LOCATE', '제1조제2항'),
                            ('QUERY', '승인 보고')],
                        2: [('ANSWER',)]}}
    # Answer-time reads off: the proposal is left for the user's follow-up.
    transport, responses = run(tree, tmp_path, plan, turns=2,
                               navigation={'guided_action_limit': 3, 'guided_answer_read_rounds': 0})
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    first_answer = calls(transport, 1, 'answer')[0]
    proposed = [r for r in first_answer['view']['readable_locations'] if '제2항' in r['label'] or '②' in r['label']]
    assert proposed, first_answer['view'].get('readable_locations')
    # Turn 2: the resolver chooses among the previous answer's own proposal IDs.
    resolve = calls(transport, 2, 'memory-resolve')[0]
    fields = calls(transport, 2, 'memory-resolve-fields')[0]['schema']
    offered = fields['properties']['continue_reads']['items']['enum']
    assert len(offered) == 1 and 'continue_reads' in fields['required']
    goals = (resolve['view'].get('context') or resolve['view'])['goals']
    shown = goals[-1]['previous_response']['guidance']['proposed_reads']
    assert [r['read_id'] for r in shown] == offered and set(shown[0]) == {'read_id', 'label'}
    nav = calls(transport, 2, 'investigate')
    assert nav and nav[0]['view']['continuation_request']['requested_reads'] == [shown[0]['label']]
    # The original was read by the server before the first selector call; the model chose no READ.
    assert not plan['actions'][2]
    second_answer = calls(transport, 2, 'answer')[0]
    assert any('승인 후 보고' in o['text'] for o in second_answer['view']['originals'])
    assert second_answer['view']['previous_answer_points'] == [{'point_id': 'P1', 'text': FIRST, 'issue_refs': ['Q1']}]
    claims = responses[1].json()['answer']['claims']
    assert [c['text'] for c in claims] == [FIRST, SECOND]


def test_continue_reads_are_limited_to_the_target_answer_offer():
    goal = {'id': 'G1', 'status': 'READY', 'command_ready': True, 'pending': None,
            'state': {'task': '질문', 'source_category': 'ALL', 'document_ids': ['d'], 'facts': [], 'queries': []},
            'events': [{'id': 1, 'after': {'task': '질문'}}],
            'previous_response': {'guidance': {'proposed_reads': [{'read_id': 'Rabc', 'label': '제1조제2항'}]}}}
    context = {'utterance': FOLLOWUP, 'goals': [goal], 'knowledge': []}
    base = {'method_id': 'RESEARCH_CONTINUE', 'document_scope_mode': 'KEEP', 'target': 'G1', 'stage': 'SELECT',
            'source_category': 'KEEP', 'task': None, 'facts': None, 'queries': None, 'document_ids': None}
    assert mm.normalize({**base, 'continue_reads': ['Rabc']}, context)['continue_reads'] == ['Rabc']
    for bad in (['Rzzz'], ['Rabc', 'Rabc']):
        with pytest.raises(ValueError):
            mm.normalize({**base, 'continue_reads': bad}, context)
    with pytest.raises(ValueError):
        mm.normalize({**base, 'method_id': 'RESEARCH_REENTER', 'continue_reads': ['Rabc']}, context)
    schema = {'type': 'object', 'properties': {'continue_reads': {'type': 'array', 'maxItems': 0}}, 'required': []}
    branch = mm.command_branch(schema, 'RESEARCH_CONTINUE', context)
    assert branch['properties']['continue_reads']['items']['enum'] == ['Rabc'] and 'continue_reads' in branch['required']
    assert mm.command_branch(schema, 'ANSWER_PRESENT', context)['properties']['continue_reads']['maxItems'] == 0


def test_kept_points_keep_exact_text_order_and_only_still_offered_spans():
    issues = [{'id': 'Q1'}]
    options = [{'id': 'S1'}, {'id': 'S2'}]
    previous = {'guided_reply': {}, 'claims': [
        {'text': 'A', 'issue_refs': ['Q1'], 'evidence_refs': ['S1']},
        {'text': 'B', 'issue_refs': ['Q1'], 'evidence_refs': ['S9']},  # span no longer offered
        {'text': 'C', 'issue_refs': ['Q1'], 'evidence_refs': ['S2']}]}
    points = ga.previous_points(previous, options, issues)
    assert [(p['point_id'], p['text']) for p in points] == [('P1', 'A'), ('P2', 'C')]
    assert ga.previous_points({'claims': previous['claims']}, options, issues) == []  # not a guided answer
    value = {'kept_points': ['P2', 'P1'], 'answer_points': [
        {'issue_refs': ['Q1'], 'evidence_refs': ['S2'], 'text': 'C'},  # verbatim repeat of a kept point is dropped
        {'issue_refs': ['Q1'], 'evidence_refs': ['S2'], 'text': 'D'}], 'open_questions': []}
    assert [p['text'] for p in ga.merged_points(value, points)] == ['A', 'C', 'D']
    wire_schema = ga.schema(issues, options, (), (), points)
    assert wire_schema['properties']['kept_points']['items']['enum'] == ['P1', 'P2']
    assert wire_schema['properties']['answer_points']['maxItems'] == 8
    with pytest.raises(ProposalError):
        ga.verify({**value, 'kept_points': ['P1', 'P1']}, issues, options, [], previous=points)


def test_read_choices_number_locations_after_unread_links_without_duplicates():
    unread = [{'unread_id': 'U1', 'target_label': '제436조', 'document_id': 'd', 'source_id': 's', 'unit_id': '7'},
              {'unread_id': 'U2', 'target_label': 'x', 'document_id': 'd', 'source_id': 's', 'unit_id': '8', 'list_only': True}]
    locations = [{'identity': {'document_id': 'd', 'source_id': 's', 'unit_id': '7'}, 'label': '같은 조문'},
                 {'identity': {'document_id': 'd', 'source_id': 's', 'unit_id': '9'}, 'label': '제368조'}]
    rows = ga.read_choices(unread, locations)
    assert [(r['id'], r['origin']) for r in rows] == [('U1', 'CONNECTION'), ('L1', 'LOCATION')]
    assert rows[1]['label'] == '제368조'


def test_free_read_policy_bounds():
    base = dict(lc.DEFAULT_POLICY, guided_loop=True, guided_action_limit=6)
    value = lc.validate_policy({**base, 'guided_reads_free': True, 'guided_read_rounds': 4, 'guided_answer_read_rounds': 6})
    assert value['guided_reads_free'] is True and value['guided_read_rounds'] == 4 and value['guided_answer_read_rounds'] == 6
    for bad in ({**base, 'guided_reads_free': 1}, {**base, 'guided_action_limit': 0, 'guided_reads_free': True},
                {**base, 'guided_answer_read_rounds': 9}, {**base, 'guided_reads_free': True, 'guided_read_rounds': 13},
                {**base, 'guided_reads_free': True, 'guided_read_rounds': -1}, {**base, 'guided_loop': False, 'guided_action_limit': 0,
                 'guided_answer_read_rounds': 1}):
        with pytest.raises(ContractError):
            lc.validate_policy(bad)


def test_question_terms_keep_content_words_only():
    from semantic_runtime.legal_agent.guided_navigation import question_terms
    assert question_terms('외규: 주주총회 결의 요건') == ['주주총회', '결의', '요건']
    assert question_terms('어어 상법상 주주총회 결의 요건을 확인해줘') == ['상법', '주주총회', '결의', '요건']
    assert question_terms('이어서 읽어봐봐') == []


def large_section(monkeypatch):
    """A 28-article section like 상법 제1관 주주총회; titles only, no bodies needed."""
    from types import SimpleNamespace as S
    from semantic_runtime.legal_agent import unit_reading as ur
    titles = {361: '총회의 권한', 362: '소집의 결정', 363: '소집의 통지', 364: '소집지', 365: '총회의 소집',
              368: '총회의 결의방법과 의결권의 행사', 371: '정족수, 의결권수의 계산', 372: '총회의 연기, 속행의 결의'}
    units = {('d', 'S'): {'surface': '제1관', 'title': '주주총회', 'parent': None, 'span': [0, 100]}}
    sources = {}
    for n in range(361, 389):
        uid = str(n)
        units[('d', uid)] = {'surface': '제%d조' % n, 'title': titles.get(n, '기타 사항'), 'parent': 'S', 'span': [n, n + 1]}
        sources['s' + uid] = {'document_id': 'd', 'unit_id': uid, 'document_name': '상법'}
    matcher = S(units=units, _unit_sources=lambda did, uid: ['s' + uid])
    monkeypatch.setattr(ur, 'blocks', lambda s, did, uid, extent: ['b' + str(uid)])
    session = S(matcher=matcher, tools=S(sources=sources), scope={'d'},
                profile={'candidate_navigation': {'guided_loop': True}, 'answer_presentation': 'guided-conversation-v1'})
    return S(s=session, p={'selected': {}, 'groups': {}}, question='외규: 주주총회 결의 요건',
             policy={'guided_section_title_matches': True})


def test_large_section_offers_title_matched_articles_as_free_reads(monkeypatch):
    from semantic_runtime.legal_agent import guided_navigation as gn
    inv = large_section(monkeypatch)
    rows = gn.section_title_matches(inv, inv.question, [{'source_id': 's363'}])
    # The 6-article title window around 제363조 cannot reach 제368조; the title match does.
    assert [r['coordinate'] for r in rows] == ['제368조', '제372조']
    assert rows[0]['matched_terms'] == ['결의'] and rows[0]['section'] == '주주총회'
    data = {'sources': [{'source_id': 's363'}]}
    gn.attach_section_matches(inv, data, lambda action, identity, label: 'T-' + identity['source_id'])
    assert [r['read_action'] for r in data['section_title_matches']] == ['T-s368', 'T-s372']
    assert data['section_title_matches'][0]['heading'] == '제368조 총회의 결의방법과 의결권의 행사'
    # Already-read articles and the policy switch are respected.
    inv.p['selected'] = {'B1': {'source_id': 's368', 'document_id': 'd',
                                'evidence': [{'source_id': 's368', 'spans': [{'block_id': 'b368'}]}]}}
    assert [r['coordinate'] for r in gn.section_title_matches(inv, inv.question, [{'source_id': 's363'}])] == ['제372조']
    inv.policy['guided_section_title_matches'] = False
    data = {'sources': [{'source_id': 's363'}]}
    gn.attach_section_matches(inv, data, lambda *a: 'T')
    assert 'section_title_matches' not in data


def chapter_tree(monkeypatch):
    """상법 제4장 shape: 제3절 제1관 주주총회 (363 read, 368) and separate 절 for 정관변경·해산."""
    from types import SimpleNamespace as S
    from semantic_runtime.legal_agent import unit_reading as ur
    units = {('d', 'C'): {'surface': '제4장', 'title': '제4장 주식회사', 'parent': 'B', 'span': [0, 1000]},
             ('d', 'B'): {'surface': '제3편', 'title': '제3편 회사', 'parent': None, 'span': [0, 2000]},
             ('d', 'S3'): {'surface': '제3절', 'title': '제3절 회사의 기관', 'parent': 'C', 'span': [300, 430]},
             ('d', 'K1'): {'surface': '제1관', 'title': '제1관 주주총회', 'parent': 'S3', 'span': [361, 390]},
             ('d', 'S5'): {'surface': '제5절', 'title': '제5절 정관의 변경', 'parent': 'C', 'span': [433, 437]},
             ('d', 'S10'): {'surface': '제10절', 'title': '제10절 해산', 'parent': 'C', 'span': [517, 521]},
             ('d', 'C5'): {'surface': '제5장', 'title': '제5장 유한회사', 'parent': 'B', 'span': [1000, 1100]}}
    titles = {('K1', 363): '소집의 통지', ('K1', 368): '총회의 결의방법과 의결권의 행사', ('K1', 372): '총회의 연기, 속행의 결의',
              ('S5', 433): '정관변경의 방법', ('S5', 434): '정관변경의 특별결의', ('S5', 435): '종류주주총회',
              ('S10', 517): '해산사유', ('S10', 518): '해산의 결의', ('C5', 585): '정관변경의 특별결의'}
    sources = {}
    for (parent, n), title in titles.items():
        uid = str(n)
        units[('d', uid)] = {'surface': '제%d조' % n, 'title': title, 'parent': parent, 'span': [n, n + 1]}
        units[('d', uid + 'p')] = {'surface': '①', 'title': '결의 본문 항', 'parent': uid, 'span': [n, n + 1]}
        sources['s' + uid] = {'document_id': 'd', 'unit_id': uid, 'document_name': 'external > team > law > 상법'}
    matcher = S(units=units, _unit_sources=lambda did, uid: ['s' + uid], documents={'d': 'external > team > law > 상법'})
    monkeypatch.setattr(ur, 'blocks', lambda s, did, uid, extent: ['b' + str(uid)])
    session = S(matcher=matcher, tools=S(sources=sources), scope={'d'},
                profile={'candidate_navigation': {'guided_loop': True}, 'answer_presentation': 'guided-conversation-v1'})
    return S(s=session, p={'selected': {}, 'groups': {}}, question='외규: 주주총회 결의 요건',
             policy={'guided_section_title_matches': True})


def test_chapter_title_matches_reach_other_sections_of_the_same_chapter(monkeypatch):
    from semantic_runtime.legal_agent import guided_navigation as gn, decision_projection as dp
    inv = chapter_tree(monkeypatch)
    data = {'sources': [{'source_id': 's363'}]}
    offered = {}
    def offer(action, identity, label):
        offered['T-' + identity['source_id']] = {'identity': {**identity}, 'label': label}
        return 'T-' + identity['source_id']
    gn.attach_section_matches(inv, data, offer)
    # Same 관: 368/372. Same 장, other 절: 434 (특별결의), 435 (종류주주총회), 518 (해산의 결의); 제5장 585 is outside.
    assert [r['read_action'] for r in data['section_title_matches']] == ['T-s368', 'T-s372']
    group, = data['chapter_title_matches']
    assert group['chapter'] == '제4장 주식회사' and group['title_only_not_evidence'] is True
    assert [a['heading'] for a in group['articles']] == ['제434조 정관변경의 특별결의', '제435조 종류주주총회', '제518조 해산의 결의']
    assert group['articles'][0]['section'] == '제5절 정관의 변경' and group['articles'][0]['matched_terms'] == ['결의']
    assert group['listed_complete'] is True and group['matched_total'] == 3
    # The chapter rows are ordinary read candidates with the document carried by the group.
    rows = {r['target']: r for r in dp.read_candidate_rows(data, offered)}
    assert rows['T-s434']['heading'] == '제434조 정관변경의 특별결의' and rows['T-s434']['document_id'] == 'd'
    # Read articles leave the list; the policy switch removes both lists.
    inv.p['selected'] = {'B1': {'source_id': 's434', 'document_id': 'd',
                                'evidence': [{'source_id': 's434', 'spans': [{'block_id': 'b434'}]}]}}
    groups = gn.chapter_title_matches(inv, inv.question, [{'source_id': 's363'}])
    assert [a['coordinate'] for a in groups[0]['articles']] == ['제368조', '제372조', '제435조', '제518조']
    inv.policy['guided_section_title_matches'] = False
    data = {'sources': [{'source_id': 's363'}]}
    gn.attach_section_matches(inv, data, offer)
    assert 'chapter_title_matches' not in data and 'section_title_matches' not in data


def test_chapter_title_matches_are_bounded_and_rank_more_matched_terms_first(monkeypatch):
    from semantic_runtime.legal_agent import guided_navigation as gn
    inv = chapter_tree(monkeypatch)
    units, sources = inv.s.matcher.units, inv.s.tools.sources
    for n in range(600, 640):
        units[('d', str(n))] = {'surface': '제%d조' % n, 'title': '결의 사항 %d' % n, 'parent': 'S10', 'span': [n, n + 1]}
        sources['s%d' % n] = {'document_id': 'd', 'unit_id': str(n), 'document_name': '상법'}
    units[('d', '700')] = {'surface': '제700조', 'title': '주주총회 결의의 요건', 'parent': 'S10', 'span': [700, 701]}
    sources['s700'] = {'document_id': 'd', 'unit_id': '700', 'document_name': '상법'}
    group, = gn.chapter_title_matches(inv, inv.question, [{'source_id': 's363'}])
    assert len(group['articles']) == gn.CHAPTER_TITLE_MATCH_LIMIT and group['listed_complete'] is False
    assert group['articles'][0]['coordinate'] == '제700조'  # three matched terms before one
    assert group['matched_total'] == 46


def test_answer_chosen_read_offers_its_title_matches_to_the_next_answer(monkeypatch):
    from types import SimpleNamespace as S
    from semantic_runtime.legal_agent import guided_navigation as gn
    inv = chapter_tree(monkeypatch)
    events = []
    inv.s.repo = S(event=lambda kind, value: events.append(kind))
    inv.save = lambda: None
    # The answer chose 제368조 and the server read it; no selector view follows.
    inv.p['selected'] = {'B1': {'source_id': 's368', 'document_id': 'd',
                                'evidence': [{'source_id': 's368', 'spans': [{'block_id': 'b368'}]}]}}
    inv.p['continuation_read_key'] = 'K'
    inv.p['continuation_reads'] = {'K': {'reads': [{'identity': {'document_id': 'd', 'source_id': 's368'}}]}}
    assert gn.remember_title_matches(inv) > 0 and events == ['ANSWER_READ_TITLE_MATCHES_OFFERED']
    labels = [row['label'] for row in inv.p['guided_locations'].values()]
    assert '상법 · 제434조(정관변경의 특별결의)' in labels and not any('제368조' in label for label in labels)
    # Offered once: the same reads add nothing again.
    assert gn.remember_title_matches(inv) == 0
    inv.policy['guided_section_title_matches'] = False
    inv.p.pop('guided_locations')
    assert gn.remember_title_matches(inv) == 0 and 'guided_locations' not in inv.p


def test_location_label_uses_the_document_name_without_its_storage_path(monkeypatch):
    from semantic_runtime.legal_agent import guided_navigation as gn
    inv = chapter_tree(monkeypatch)
    inv.s.matcher.stored_coordinates = {}
    label = gn._location_label(inv, {'document_id': 'd', 'source_id': 's434'}, {}, {'label': '제434조 정관변경의 특별결의'})
    assert label.startswith('상법') and 'external' not in label


def test_answer_locations_rank_articles_cited_by_read_originals_before_recent_titles(monkeypatch):
    """해산 결의 (ADR-1438): 제434조 was the oldest of 24 chapter titles and the answer saw only the latest 12."""
    from types import SimpleNamespace as S
    from semantic_runtime.legal_agent import guided_navigation as gn, guided_answer as ga
    inv = chapter_tree(monkeypatch)
    units, sources = inv.s.matcher.units, inv.s.tools.sources
    for n in range(600, 614):
        units[('d', str(n))] = {'surface': '제%d조' % n, 'title': '사채권자집회 결의 %d' % n, 'parent': 'S10', 'span': [n, n + 1]}
        sources['s%d' % n] = {'document_id': 'd', 'unit_id': str(n), 'document_name': '상법'}
    texts = {'b518': '제518조(해산의 결의) 해산의 결의는 제434조의 규정에 의하여야 한다.'}
    inv.s.store = S(source=lambda did, bid: {'text': texts.get(bid, '')})
    inv.question = '외규: 주식회사를 해산하려면 주주총회에서 어떤 결의가 필요해?'
    inv.p['selected'] = {'B1': {'source_id': 's518', 'document_id': 'd',
                                'evidence': [{'source_id': 's518', 'spans': [{'block_id': 'b518'}]}]}}
    # Remembered oldest first: 제434조, 제435조, then fourteen newer noise titles.
    order = ['434', '435'] + [str(n) for n in range(600, 614)]
    candidates = {'T' + u: {'identity': {'source_id': 's' + u, 'document_id': 'd'}, 'label': u} for u in order}
    gn.remember_locations(inv, candidates, [])
    ranked = gn.unread_locations(inv)
    assert len(ranked) == gn.LOCATION_LIMITS['offered']
    assert ranked[0]['identity']['source_id'] == 's434' and ranked[0]['cited_by'] == ['제518조']
    assert ranked[0]['matched_terms'] == ['결의']
    assert 's435' not in [r['identity']['source_id'] for r in ranked[:1]]
    # The old rule (latest 12) would have dropped 제434조 entirely.
    assert 's434' not in [i['identity']['source_id'] for i in list(inv.p['guided_locations'].values())[-12:]]
    reads = ga.read_choices([], ranked)
    assert reads[0]['id'] == 'L1' and reads[0]['cited_by'] == ['제518조']


def test_citation_scan_ignores_the_citing_articles_own_heading(monkeypatch):
    from types import SimpleNamespace as S
    from semantic_runtime.legal_agent import guided_navigation as gn
    inv = chapter_tree(monkeypatch)
    inv.s.store = S(source=lambda did, bid: {'text': '제434조(정관변경의 특별결의) 제433조의 결의는 출석한 주주의 의결권의 3분의 2 이상'})
    cited = gn.cited_articles(inv, {'s434': {'b434'}})
    assert ('d', '제434조') not in cited and cited[('d', '제433조')] == ['제434조']
    assert gn.cited_articles(S(s=S(matcher=inv.s.matcher, tools=inv.s.tools, scope={'d'})), {'s434': {'b434'}}) == {}


def test_unread_notes_fold_many_rows_from_one_article_or_section():
    from semantic_runtime.legal_agent import guided_answer as ga
    rows = [{'from_label': '제206조(「상법」과의 관계)', 'target_label': '제%d조(조문 %d)' % (n, n), 'relation': None,
             'relation_text': '인용한 조문(정방향)', 'reason': '자동으로 읽는 연결 수 한도를 넘어서', 'judged_unneeded': False,
             'reason_origin': 'SYSTEM_RULE', 'list_only': False} for n in range(301, 331)]
    rows += [{'from_label': '', 'target_label': '제%d조(동전)' % n, 'relation': 'SAME_SECTION', 'section': '제6절 자본금의 감소',
              'relation_text': '같은 절의 조문', 'reason': '결의 요건과 무관해서', 'judged_unneeded': True,
              'reason_origin': 'MODEL', 'list_only': False} for n in range(439, 444)]
    rows.append({'from_label': '제438조(자본금 감소의 결의)', 'target_label': '제363조(소집의 통지)', 'relation': None,
                 'relation_text': '인용한 조문(정방향)', 'reason': '이미 설명한 통지 절차라서', 'judged_unneeded': True,
                 'reason_origin': 'MODEL', 'list_only': False})
    text, = ga.unread_paragraphs({'unread_connections': rows, 'unread_connection_total': len(rows) + 63})
    lines = text.splitlines()
    assert len([l for l in lines if l.startswith('- ')]) == 3 + 1 + 3 + 1 + 1 + 1
    assert '- 제206조(「상법」과의 관계)에 연결된 다른 조문 27건(제304조, 제305조, 제306조, 제307조, 제308조 등)도 지금은 읽지 않았습니다.' in lines
    assert '- 같은 절(제6절 자본금의 감소)의 다른 조문 2건(제442조, 제443조)도 지금은 읽지 않았습니다.' in lines
    assert any(l.startswith('- 제438조(자본금 감소의 결의)에 연결된 제363조') for l in lines)
    assert lines[-2] == '- 그 밖에 연결 조문 63건도 읽지 않았습니다.'


class Rejecting(Scripted):
    """The follow-up check rejects the first interpretation; the resolver gets one correction."""

    def __init__(self, *a, reject=1, **k):
        super().__init__(*a, **k); self.reject = reject; self.checks = 0

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage') or view['phase']
        if phase.startswith('memory-resolve-related'):  # every earlier question (pre-selection behavior)
            return wire(related_all(body['response_format']['json_schema']['schema']))
        if phase in ('memory-resolve-repair', 'memory-resolve-repair-fields'):
            self.log.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view)})
            schema = body['response_format']['json_schema']['schema']
            return wire(fit(command('RESEARCH_CONTINUE', target=self.target, stage='SELECT', continue_reads=[]), schema))
        schema = body['response_format']['json_schema']['schema']
        if self.turn == 2 and 'open_questions' in schema.get('properties', {}):
            self.log.append({'turn': self.turn, 'phase': 'answer', 'view': deepcopy(view), 'schema': schema})
            issue = find(schema, 'issue_refs')['items']['enum'][:1]
            first = view['originals'][0]['id']
            value = {'open_questions': [], 'answer_points': [{'issue_refs': issue, 'evidence_refs': [first], 'text': FIRST}]}
            for name in ('next_reads', 'kept_points', 'unread_notes'):
                if name in schema['properties']: value[name] = []
            return wire(value)
        if phase == 'memory-command-check':
            self.checks += 1; self.log.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view)})
            if self.checks <= self.reject:
                return wire({'valid': False, 'reason': '직전 답변이 읽지 않았다고 안내한 위치를 읽자는 동의로 해석했다.',
                             'request_relation': 'CONTINUE', 'requested_task': self.task})
        return super().send_once(body=body, ticket=ticket)


def run_rejecting(tree, tmp_path, reject):
    gen, idx = tree
    plan = {'relation': 'CONTINUE', 'actions': {1: [('LOCATE', '제1조제1항'), ('READ', '제1조제1항')], 2: [('ANSWER',)]}}
    transport = Rejecting(BROAD, 'authorized', plan, reject=reject); runtime = tmp_path / 'runtime'
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    profile['candidate_navigation'].update({'guided_action_limit': 3, 'guided_answer_read_rounds': 0})
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=runtime,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app) as api:
        request = {'session_id': 's', 'request_id': '1', 'question': BROAD}
        first = api.post('/v1/rag/ask', json=request); assert first.status_code == 200, first.text
        db = connect(selected_store(runtime))
        row = db.execute('SELECT id,state FROM goal ORDER BY ordinal DESC LIMIT 1').fetchone()
        transport.target = row['id']; transport.task = json.loads(row['state'])['task']; db.close()
        transport.turn = 2
        second = api.post('/v1/rag/ask', json={**request, 'request_id': '2', 'question': '제1조제1항은 다시 설명해줘'})
    return transport, second


def test_guided_follow_up_rejected_once_is_corrected_with_the_checkers_reason(tree, tmp_path):
    transport, second = run_rejecting(tree, tmp_path, reject=1)
    assert second.status_code == 200, second.text
    repair = calls(transport, 2, 'memory-resolve-repair')
    assert len(repair) == 1 and transport.checks == 2
    payload = repair[0]['view']
    assert 'rejected_decision' in json.dumps(payload, ensure_ascii=False)
    # The corrected RESEARCH_CONTINUE ran the same goal's investigation and answer instead of asking back.
    assert calls(transport, 2, 'answer'), [r['phase'] for r in transport.log if r['turn'] == 2]
    assert '연결하는 판단이 맞지 않아' not in json.dumps(second.json(), ensure_ascii=False)


def test_guided_follow_up_rejected_twice_still_asks_after_one_correction(tree, tmp_path):
    transport, second = run_rejecting(tree, tmp_path, reject=2)
    assert second.status_code == 200, second.text
    assert len(calls(transport, 2, 'memory-resolve-repair')) == 1 and transport.checks == 2
    assert not calls(transport, 2, 'answer')
    assert '판단이 엇갈려' in json.dumps(second.json(), ensure_ascii=False) and '새 질문으로 조사할까요' in json.dumps(second.json(), ensure_ascii=False)


def test_rule_that_defers_exceptions_puts_special_rule_titles_first(monkeypatch):
    """주주총회 결의 요건 (ADR-1441): 제368조① "다른 정함이 있는 경우를 제외하고는" was read and 제434조
    정관변경의 특별결의 sat behind earlier '결의' titles in the chapter list; it is now first and flagged."""
    from types import SimpleNamespace as S
    from semantic_runtime.legal_agent import guided_navigation as gn
    inv = chapter_tree(monkeypatch)
    units, sources = inv.s.matcher.units, inv.s.tools.sources
    units[('d', 'S1')] = {'surface': '제1절', 'title': '제1절 설립', 'parent': 'C', 'span': [290, 299]}
    units[('d', '309')] = {'surface': '제309조', 'title': '창립총회의 결의', 'parent': 'S1', 'span': [309, 310]}
    sources['s309'] = {'document_id': 'd', 'unit_id': '309', 'document_name': '상법'}
    texts = {'b368': '①총회의 결의는 이 법 또는 정관에 다른 정함이 있는 경우를 제외하고는 출석한 주주의 의결권의 과반수와 '
                     '발행주식총수의 4분의 1 이상의 수로써 하여야 한다.'}
    inv.s.store = S(source=lambda did, bid: {'text': texts.get(bid, '')})
    # Before anything that defers is read: document order (제309조 first).
    plain = gn.chapter_title_matches(inv, inv.question, [{'source_id': 's363'}])
    assert [a['coordinate'] for a in plain[0]['articles']][:2] == ['제309조', '제368조']
    inv.p['selected'] = {'B1': {'source_id': 's368', 'document_id': 'd',
                                'evidence': [{'source_id': 's368', 'spans': [{'block_id': 'b368'}]}]}}
    defers = gn.scan_read_originals(inv, gn._known_reads(inv))['defers']
    assert defers == {'d': ['제368조']}
    groups = gn.chapter_title_matches(inv, inv.question, [{'source_id': 's363'}], defers=defers)
    first = groups[0]['articles'][0]
    assert first['coordinate'] == '제434조' and first['exception_for'] == ['제368조']
    data = {'sources': [{'source_id': 's363'}]}
    gn.attach_section_matches(inv, data, lambda action, identity, label: 'T-' + identity['source_id'])
    assert data['chapter_title_matches'][0]['articles'][0]['heading'] == '제434조 정관변경의 특별결의'
    assert data['chapter_title_matches'][0]['articles'][0]['exception_for'] == ['제368조']
    # Answer-stage ranking: the special rule precedes newer plain '결의' titles.
    candidates = {'T' + u: {'identity': {'source_id': 's' + u, 'document_id': 'd'}, 'label': u} for u in ('434', '309', '372', '518')}
    gn.remember_locations(inv, candidates, [])
    ranked = gn.unread_locations(inv)
    assert ranked[0]['identity']['source_id'] == 's434' and ranked[0]['exception_for'] == ['제368조']
    assert all(not r['exception_for'] for r in ranked[1:])


class TwoStep(Scripted):
    """A provider that answers exactly the schema it is given: method choice first, then the remaining fields."""

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage') or view['phase']
        if phase.startswith('memory-resolve-related'):  # every earlier question (pre-selection behavior)
            return wire(related_all(body['response_format']['json_schema']['schema']))
        schema = body['response_format']['json_schema']['schema']
        if phase == 'memory-resolve':
            self.log.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view), 'schema': schema})
            props = schema['properties']
            assert 'anyOf' not in schema and set(props) <= {'method_id', 'target', 'reason', 'format'}, sorted(props)
            value = {'method_id': 'RESEARCH_CONTINUE', 'target': self.target, 'reason': '직전 답변의 제2항 제안을 이어서 읽는다.'}
            if 'format' in props: value['format'] = 'prose'
            return wire(value)
        if phase == 'memory-resolve-fields':
            self.log.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view), 'schema': schema})
            props = schema['properties']
            assert view['selected']['method_id'] == 'RESEARCH_CONTINUE' and 'method_id' not in props
            assert not {'document_ids', 'knowledge_id', 'restore_event', 'task', 'facts', 'queries'} & set(props)
            value = {}
            if 'continue_reads' in props:
                value['continue_reads'] = list(props['continue_reads']['items']['enum'])
            for name, rule in props.items():
                value.setdefault(name, rule.get('enum', [None])[0] if 'enum' in rule else value.get(name))
            return wire(value)
        return super().send_once(body=body, ticket=ticket)


def test_two_step_resolver_fills_fixed_fields_and_keeps_the_full_contract(tree, tmp_path):
    gen, idx = tree
    plan = {'relation': 'CONTINUE', 'actions': {1: [('LOCATE', '제1조제1항'), ('READ', '제1조제1항'), ('LOCATE', '제1조제2항'),
                                                   ('QUERY', '승인 보고')], 2: [('ANSWER',)]}}
    transport = TwoStep(BROAD, 'authorized', plan); runtime = tmp_path / 'runtime'
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    profile['candidate_navigation'].update({'guided_action_limit': 3, 'guided_answer_read_rounds': 0})
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=runtime,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app) as api:
        request = {'session_id': 's', 'request_id': '1', 'question': BROAD}
        assert api.post('/v1/rag/ask', json=request).status_code == 200
        db = connect(selected_store(runtime))
        row = db.execute('SELECT id,state FROM goal ORDER BY ordinal DESC LIMIT 1').fetchone()
        transport.target = row['id']; transport.task = json.loads(row['state'])['task']; db.close()
        transport.turn = 2
        second = api.post('/v1/rag/ask', json={**request, 'request_id': '2', 'question': FOLLOWUP})
    assert second.status_code == 200, second.text
    step1 = calls(transport, 2, 'memory-resolve'); step2 = calls(transport, 2, 'memory-resolve-fields')
    assert len(step1) == 1 and len(step2) == 1
    assert len(json.dumps(step1[0]['schema'])) < 2000  # was ~15,000 characters with 11 branches
    # The proposed read chosen in step 2 was read before navigation, exactly as with the one-call resolver.
    nav = calls(transport, 2, 'investigate')
    assert nav and nav[0]['view']['continuation_request']['requested_reads']
    second_answer = calls(transport, 2, 'answer')[0]
    assert any('승인 후 보고' in o['text'] for o in second_answer['view']['originals'])
    # Resolver input: no unread article text, the previous answer text appears once.
    view = step1[0]['view']; text = json.dumps(view, ensure_ascii=False)
    goal = view['goals'][-1]
    answer = goal['previous_response']['text']
    assert answer and text.count(json.dumps(answer, ensure_ascii=False)[1:-1]) == 1
    guide = goal['previous_response']['guidance']
    assert 'investigation_record' not in guide and all('text' not in r for r in guide['unread_connections'])
    assert guide['read_originals'] and guide['proposed_reads']


def test_resolver_view_keeps_host_context_intact():
    from semantic_runtime.legal_agent import corrected_memory as cm
    text = '이전 답변 ' * 50
    context = {'goals': [{'id': 'G', 'previous_response': {'text': text, 'guidance': {
        'proposed_reads': [{'read_id': 'R1', 'label': '제2항'}],
        'unread_connections': [{'from_label': '제1조', 'target_label': '제%d조' % n, 'relation_text': '인용한 조문',
                                'judged_unneeded': True, 'text': '원문 ' * 300, 'unread_id': 'U%d' % n} for n in range(20)],
        'unread_connection_total': 40,
        'investigation_record': {'entry_search': {'queries': ['승인']}, 'steps': [
            {'outcome': {'new_reads': ['external > team > law > 모의승인규정 제1조']}}]}}},
        'dialogue': [{'speaker': 'user', 'text': '질문'}, {'speaker': 'assistant', 'text': text}]}],
        'recent_dialogue': [{'speaker': 'user', 'text': '질문'}, {'speaker': 'assistant', 'text': text},
                            {'speaker': 'assistant', 'text': '확인 질문입니다', 'clarification': True}]}
    view = cm.resolver_view(context)
    guide = view['goals'][0]['previous_response']['guidance']
    assert guide['read_originals'] == ['모의승인규정 제1조'] and guide['searched'] == ['승인']
    assert len(guide['unread_connections']) == cm.GUIDANCE_VIEW['unread'] and guide['unread_connection_total'] == 40
    assert json.dumps(view, ensure_ascii=False).count(text) == 1
    assert view['recent_dialogue'][2]['text'] == '확인 질문입니다'  # clarifications stay
    # The host context is not modified.
    assert 'investigation_record' in context['goals'][0]['previous_response']['guidance']
    assert context['recent_dialogue'][1]['text'] == text
