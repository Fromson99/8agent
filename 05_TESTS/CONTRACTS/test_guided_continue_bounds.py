"""Naive "continue" after a guided offer, bounded exploration, and re-entry crashes.

Actual HTTP/store/pipeline boundary with a scripted model transport only.
"""
from copy import deepcopy
import json
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import memory_methods as mm, output_contract as output
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.legal_agent.shortcut_store import selected_store
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from test_memory_runtime_v2 import command, fit
from test_multiturn_structured_scope import tree
from test_definition_context_recovery import context_probe

# The request-entry search field asks_definition exists from the definition-priority change on; older
# code rejects it, so scripted entries carry it only when the loaded schema has it.
from semantic_runtime.legal_agent import request_entry as _asks_entry
import json as _asks_json
ASKS_DEFINITION = {'asks_definition': True} if 'asks_definition' in _asks_json.dumps(_asks_entry.schema(model=True)) else {}

NAMED = '모의승인규정 제1조제1항의 승인 기준을 알려줘'
BROAD = '긴급 승인 예외 기준을 알려줘'
CONTINUE = '어 계속 찾아줘'
OFFER = {'kind': 'SOURCE', 'uncertainty': '모의승인규정 제1조제2항의 본문은 아직 읽지 않았습니다.',
         'question': '제1조제2항을 이어서 읽어볼까요?'}


def find(node, name):
    if isinstance(node, dict):
        if name in node.get('properties', {}): return node['properties'][name]
        for child in node.values():
            found = find(child, name)
            if found is not None: return found
    if isinstance(node, list):
        for child in node:
            found = find(child, name)
            if found is not None: return found


def fill(schema):
    if 'const' in schema: return schema['const']
    if 'enum' in schema: return schema['enum'][0]
    if 'anyOf' in schema: return fill(schema['anyOf'][0])
    kind = schema.get('type')
    if isinstance(kind, list): kind = kind[0]
    if kind == 'object': return {k: fill(schema['properties'][k]) for k in schema.get('required', [])}
    if kind == 'array':
        n = max(1, schema.get('minItems', 0)) if schema.get('minItems', 0) or 'enum' in schema.get('items', {}) else 0
        return [fill(schema['items']) for _ in range(n)]
    if kind == 'boolean': return False
    if kind == 'null': return None
    if kind == 'integer': return 1
    return '모의 이유: 다음 본문 확인'


class Transport:
    binding = settings()['model_binding']

    def __init__(self, question, scope, plan):
        self.question = question; self.scope = scope; self.plan = plan
        self.turn = 1; self.target = None; self.task = None; self.log = []; self.reads = {}

    def validate_model(self): return {'verified': True, 'synthetic': True}

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage') or view['phase']
        schema = body['response_format']['json_schema']['schema']
        self.log.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view), 'schema': schema})
        if phase == 'request-entry':
            decision = ({'mode': 'NAMED_SCOPE', 'targets': [{'document': '모의승인규정', 'structure': '제1조제1항',
                         'selection': None}], 'user_quote': self.question, 'reason': '명시된 항'} if self.scope == 'named'
                        else {'mode': 'AUTHORIZED_SCOPE', 'targets': [], 'user_quote': '', 'reason': '범위 미지정'})
            return wire({'routing': {'mode': 'CASE', 'answer': '', 'reason': '모의 조사'},
                'command': {'method_id': 'CASE_START', 'source_category': 'ALL', 'facts': [], 'queries': ['승인'],
                            'format': 'prose', 'reason': '모의'},
                'intent': {'purpose': self.question, 'concepts': ['승인'], 'issues': [{'id': 'Q1', 'question': self.question,
                    'subject': '승인', 'kind': 'OTHER', 'request_quote': self.question}]}, 'context_quotes': [],
                'search': {**ASKS_DEFINITION, 'mode': 'FULLTEXT', 'scope_decision': decision, 'reason': '범위 조회'}})
        if phase == 'memory-reason-decision-review':
            raise AssertionError('guided conversation must not spend a separate reason review')
        if phase == 'source-request-route': return wire({'mode': 'CASE', 'answer': '', 'reason': '기존 조사 후속'})
        if phase.startswith('memory-resolve'):
            method, stage = self.plan['resolve']
            return wire(fit(command(method, target=self.target, stage=stage), schema))
        if phase == 'memory-command-check':
            return wire({'valid': True, 'reason': '모의 대조', 'request_relation': self.plan['relation'],
                         'requested_task': self.task})
        if 'open_questions' in schema.get('properties', {}):
            issue = find(schema, 'issue_refs')['items']['enum'][:1]
            evidence = find(schema, 'evidence_refs')['items'].get('enum', [])[:1]
            points = [{'issue_refs': issue, 'evidence_refs': evidence, 'text': '제1조제1항은 각 호의 승인 기준을 적용합니다.'}] if evidence else []
            return wire({'open_questions': [{'issue_refs': issue, **OFFER}], 'answer_points': points})
        if phase == 'investigate':
            options = {}
            for branch in schema.get('anyOf', []):
                options.setdefault(branch['properties']['choice'].get('const'), []).append(branch)
            if self.plan.get('ask') and self.turn == 1:
                return wire({'choice': 'ASK_USER', 'questions': [{'issue_refs': find(schema, 'issue_refs')['items']['enum'][:1], **OFFER}]})
            used = self.reads.get(self.turn, 0)
            if 'READ' in options and view.get('read_candidates') and used < self.plan.get('reads', 1):
                self.reads[self.turn] = used + 1
                return wire(fill(options['READ'][0]))
            if view.get('sources') and not self.plan.get('followed', {}).get(self.turn):
                self.plan.setdefault('menus_after_read', []).append(sorted(k for k in options if k))
            if 'ANSWER' in options: return wire(fill(options['ANSWER'][0]))
            if 'FOLLOW' in options and not self.plan.setdefault('followed', {}).get(self.turn):
                self.plan['followed'][self.turn] = True
                return wire(fill(options['FOLLOW'][0]))
            return wire({'choice': 'ASK_USER', 'questions': [{'issue_refs': find(schema, 'issue_refs')['items']['enum'][:1], **OFFER}]})
        raise AssertionError(phase)


def run(tree, tmp_path, *, question=NAMED, scope='named', plan, turns=2, profile_update=None):
    gen, idx = tree
    transport = Transport(question, scope, plan); runtime = tmp_path / 'runtime'
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    profile.update(model_binding=transport.binding, max_read_chars=10000)
    for key, value in (profile_update or {}).items(): profile['candidate_navigation'][key] = value
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport, runtime_root=runtime,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d', 'other']})
    app.state.pipeline.term_agent.unit_fulltext = idx

    def goal():
        db = connect(selected_store(runtime))
        row = dict(db.execute('SELECT id,revision,state,status FROM goal ORDER BY ordinal DESC LIMIT 1').fetchone())
        db.close(); row['state'] = json.loads(row['state']); return row
    responses = []
    with TestClient(app) as api:
        request = {'session_id': 's', 'request_id': '1', 'question': question}
        responses.append(api.post('/v1/rag/ask', json=request))
        assert responses[0].status_code == 200, responses[0].text
        first = goal(); transport.target = first['id']; transport.task = first['state']['task']
        for n in range(2, turns + 1):
            transport.turn = n
            responses.append(api.post('/v1/rag/ask', json={**request, 'request_id': str(n), 'question': CONTINUE}))
    return transport, responses, goal()


@pytest.mark.parametrize('scope', ['named', 'authorized'])
def test_naive_continue_resumes_investigation_with_previous_offer(tree, tmp_path, scope):
    transport, responses, last = run(tree, tmp_path, question=NAMED if scope == 'named' else BROAD, scope=scope,
        plan={'resolve': ('RESEARCH_CONTINUE', 'SELECT'), 'relation': 'CONTINUE'}, turns=3)
    for response in responses:
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'READY'
    assert responses[1].json()['executed'] == ['SELECT', 'ASSESS', 'COMPOSE']
    assert responses[1].json()['method_id'] == 'RESEARCH_CONTINUE'
    nav = [r for r in transport.log if r['turn'] == 2 and r['phase'] == 'investigate']
    assert nav, 'continue must reach the investigation selector'
    offer = nav[0]['view']['continuation_request']
    assert offer['user_request'] == CONTINUE and offer['previous_offer_questions'][0]['question'] == OFFER['question']
    assert nav[0]['view']['action_budget']['remaining'] == nav[0]['view']['action_budget']['limit'] == 6
    # Same goal, purpose and facts; the follow-up spends no separate reason reviews.
    assert last['revision'] == 3 and last['state']['task'] == transport.task
    control = [r['phase'] for r in transport.log if r['turn'] == 2 and r['phase'] != 'investigate']
    # The related earlier question is chosen first, then the command from it.
    assert control[:4] == ['source-request-route', 'memory-resolve-related', 'memory-resolve', 'memory-command-check']


def test_guided_answer_waits_for_one_connection_lookup_after_reading(tree, tmp_path):
    plan = {'resolve': ('RESEARCH_CONTINUE', 'SELECT'), 'relation': 'CONTINUE'}
    transport, responses, last = run(tree, tmp_path, question=BROAD, scope='authorized', plan=plan, turns=1)
    assert responses[0].status_code == 200, responses[0].text
    # The first menu after reading offers FOLLOW but not ANSWER; after the lookup ANSWER returns.
    assert plan['menus_after_read'][0] == sorted(['ASK_USER', 'FOLLOW', 'SEARCH'])
    assert plan['followed'][1] is True and responses[0].json()['status'] == 'READY'


def test_repeated_guidance_pause_then_continue_does_not_reuse_stale_page_cursor(tree, tmp_path):
    transport, responses, last = run(tree, tmp_path, plan={'resolve': ('RESEARCH_REENTER', 'SELECT'),
        'relation': 'REPEAT', 'ask': True, 'reads': 0}, turns=4)
    assert [r.status_code for r in responses] == [200, 200, 200, 200], [r.text for r in responses]
    assert last['status'] == 'READY' and last['revision'] == 4


def test_assess_reentry_restores_scope_grants_before_rebinding_originals(tree, tmp_path):
    transport, responses, last = run(tree, tmp_path, plan={'resolve': ('RESEARCH_REENTER', 'ASSESS'),
        'relation': 'REPEAT'}, turns=3)
    assert [r.status_code for r in responses] == [200, 200, 200], [r.text for r in responses]
    assert responses[1].json()['executed'] == ['ASSESS', 'COMPOSE']


def test_action_limit_stops_one_request_and_continue_grants_a_new_bound(tree, tmp_path):
    transport, responses, last = run(tree, tmp_path, question=BROAD, scope='authorized',
        plan={'resolve': ('RESEARCH_CONTINUE', 'SELECT'), 'relation': 'CONTINUE', 'reads': 5},
        turns=2, profile_update={'guided_action_limit': 1, 'guided_reads_free': False, 'guided_answer_read_rounds': 0})
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    nav = [r for r in transport.log if r['turn'] == 1 and r['phase'] == 'investigate']
    assert len(nav) == 1 and nav[0]['view']['action_budget']['remaining'] == 1
    # The original read by the only allowed action reaches the answer; no false "not acquired".
    answer = [r for r in transport.log if r['turn'] == 1 and 'open_questions' in r['schema'].get('properties', {})]
    assert answer and answer[0]['view']['stop_reason'] == 'GUIDED_ACTION_LIMIT' and answer[0]['view']['originals']
    assert responses[0].json()['answer']['claims']
    # The user's "continue" opens a fresh, equally bounded request.
    nav = [r for r in transport.log if r['turn'] == 2 and r['phase'] == 'investigate']
    assert len(nav) == 1 and nav[0]['view']['action_budget'] == {**nav[0]['view']['action_budget'], 'used': 0, 'remaining': 1}


def context(goal_status='READY'):
    goal = {'id': 'G1', 'status': goal_status, 'command_ready': True, 'pending': None,
            'state': {'task': '질문', 'source_category': 'ALL', 'document_ids': ['d'], 'facts': [], 'queries': []},
            'events': [{'id': 1, 'after': {'task': '질문'}}]}
    return {'utterance': CONTINUE, 'goals': [goal], 'knowledge': []}


def test_continue_method_is_offered_for_ready_goals_and_cannot_edit_state():
    assert mm.offered(context())['RESEARCH_CONTINUE']['targets'] == ['G1']
    assert 'RESEARCH_CONTINUE' not in mm.offered(context('PENDING'))
    base = {'method_id': 'RESEARCH_CONTINUE', 'document_scope_mode': 'KEEP', 'target': 'G1', 'stage': 'ASSESS',
            'source_category': 'KEEP', 'task': None, 'facts': None, 'queries': None, 'document_ids': None}
    assert mm.normalize(base, context())['stage'] == 'SELECT'
    with pytest.raises(ValueError):
        mm.normalize({**base, 'task': '다른 목적'}, context())


@pytest.mark.parametrize('method,stage,ok', [('RESEARCH_CONTINUE', 'SELECT', True), ('RESEARCH_REENTER', 'SELECT', True),
                                              ('RESEARCH_REENTER', 'ASSESS', False), ('PURPOSE_REVISE', 'INTENT', False)])
def test_continue_relation_requires_resumed_investigation(method, stage, ok):
    transition = {'before': {'task': '질문'}, 'after': {'task': '질문'}}
    review = {'valid': True, 'reason': 'r', 'request_relation': 'CONTINUE', 'requested_task': '질문'}
    call = lambda: mm.validate_transition({'method_id': method, 'stage': stage}, transition, review)
    if ok: call()
    else:
        with pytest.raises(output.OutputContractError):
            call()


def test_small_connection_reads_apply_only_without_read_judgments():
    from types import SimpleNamespace as S
    from semantic_runtime.legal_agent.connection_scope import small_context
    guided = {'answer_presentation': 'guided-conversation-v1', 'candidate_navigation': {'guided_loop': True}}
    policy = {"small_connection_context": False, "selected_connection_scope": True, "read_judgment": True}
    assert small_context(S(policy=policy, s=S(profile=guided)))
    assert not small_context(S(policy=policy, s=S(profile={'candidate_navigation': {}})))
    assert not small_context(S(policy={**policy, 'selected_connection_scope': False}, s=S(profile=guided)))


# --- citation roles and guided role-chain reading (2026-11-06) ---
from semantic_runtime.legal_agent import citation_roles as roles


@pytest.mark.parametrize('text,mention,expected', [
    ('제434조(정관변경의 특별결의) 제433조제1항의 결의는 출석한 주주의 의결권의 3분의 2 이상', '제433조제1항', roles.SPECIFIES),
    ('① 법 제5조제1항에서 "대통령령으로 정하는 자"란 다음 각 호의 자를 말한다.', '법 제5조제1항', roles.SPECIFIES),
    ('②전항의 경우에는 제363조의 규정을 적용하지 아니한다.', '제363조', roles.EXCEPTION),
    ('공고함으로써 제363조제1항의 소집통지를 갈음할 수 있다.', '제363조제1항', roles.EXCEPTION),
    ('제363조, 제364조 및 제368조제2항에도 불구하고 회사는', '제363조', roles.EXCEPTION),
    ('「소득세법」 제16조제2항 및 제17조제3항 각 호 외의 부분 본문에도 불구하고 총수입금액에서', '제16조제2항', roles.EXCEPTION),
    ('①제434조의 규정은 사채권자집회의 결의에 준용한다.', '제434조', roles.MUTATIS),
    ('① 자본금의 감소에는 제434조에 따른 결의가 있어야 한다.', '제434조', roles.BORROWS),
    ('②제1항의 승인결의는 제434조의 규정에 의하여야 한다.', '제434조', roles.BORROWS),
    ('4. 제11조제1항 각 호의 어느 하나에 해당함에도 불구하고 회피하지 않은 경우', '제11조제1항', roles.BORROWS),
    ('제121조의2제3항ㆍ제6항ㆍ제7항 및 제121조의5제1항의 개정규정에도 불구하고 종전의 규정에 따른다.', '제121조의2제3항', roles.TRANSITIONAL),
    ('제174조의2제3호의 개정규정은 이 법 시행 이후 주식등의 거래가 발생하는 경우부터 적용한다.', '제174조의2제3호', roles.TRANSITIONAL)])
def test_citation_role_follows_standard_statutory_phrasing(text, mention, expected):
    i = text.index(mention)
    assert roles.role(text, i, i + len(mention)) == expected
    assert roles.role(text, i, i + len(mention)) == roles.role(text, i, i + len(mention))  # deterministic
    assert roles.role(None, 0, 1) == roles.BORROWS and roles.role(text, 5, 2) == roles.BORROWS


def test_role_regex_is_linear_on_long_enumerations():
    import time
    text = '제1조 ' + '제2조, ' * 40 + '제3조에 따른 것은 ' + '가' * 400
    start = time.monotonic()
    for _ in range(500): roles.role(text, 0, 3)
    assert time.monotonic() - start < 1


def directory_with(rows):
    groups = []
    for n, (direction, role) in enumerate(rows):
        hit = {'source_id': 's%d' % n, 'document_id': 'd', 'unit_id': str(n)}
        offer = {'id': 'o%d' % n, 'unit_id': str(n), 'extent': 'subtree', 'block_ids': [str(n)]}
        groups.append({'direction': direction, 'target': {'source_id': 's%d' % n}, 'anchor': {'source_id': 'a'},
            'offers': {'o%d' % n: (hit, offer)}, 'connections': [{'reference_id': 'r%d' % n, 'citation_role': role,
            'already_read': False, 'endpoint_scopes': ['o%d' % n], 'endpoint_block_ids': [str(n)], 'witness_source_order': n}]})
    return {'status': 'COMPLETE', 'groups': groups, 'limits': [], 'unresolved': []}


def test_chain_reads_forward_and_rule_changing_pairs_only_within_caps():
    from semantic_runtime.legal_agent import connection_scope as cs
    rows = [('OUTGOING', roles.BORROWS)] * 8 + [('INCOMING', roles.BORROWS)] * 20 + [('INCOMING', roles.MUTATIS)] * 3 + \
           [('INCOMING', roles.SPECIFIES), ('INCOMING', roles.EXCEPTION), ('INCOMING', roles.SPECIFIES), ('INCOMING', roles.SPECIFIES)]
    chosen = cs.chain_rows(directory_with(rows), forward_only=False)
    outgoing = [r for r in chosen if r['outgoing']]; incoming = [r for r in chosen if not r['outgoing']]
    assert len(outgoing) == cs.CHAIN_LIMITS['outgoing'] and len(incoming) == cs.CHAIN_LIMITS['pair_incoming']
    assert all(r['pair'] for r in incoming) and incoming[0]['role'] == roles.EXCEPTION  # exceptions first
    assert not [r for r in cs.chain_rows(directory_with(rows), forward_only=True) if not r['outgoing']]


def test_list_only_cards_keep_forward_and_pairs_and_count_the_rest():
    from semantic_runtime.legal_agent import connection_scope as cs
    cards = [{'direction': 'OUTGOING', 'citation_role': roles.BORROWS, 'read_action': 'T1', 'anchor': {}},
             {'direction': 'INCOMING', 'citation_role': roles.SPECIFIES, 'read_action': 'T2', 'anchor': {}},
             {'direction': 'INCOMING', 'citation_role': roles.BORROWS, 'read_action': 'T3', 'anchor': {'heading': '제434조'}, 'coordinate': '제374조', 'target': {'heading': '영업양도'}},
             {'direction': 'INCOMING', 'citation_role': roles.MUTATIS, 'read_action': 'T4', 'anchor': {'heading': '제434조'}, 'coordinate': '제495조', 'target': {'heading': '결의의 방법'}}]
    actions = {k: {} for k in ('T1', 'T2', 'T3', 'T4')}; listed = []
    kept = cs.list_only_incoming(cards, actions, listed)
    assert [c['read_action'] for c in kept] == ['T1', 'T2'] and set(actions) == {'T1', 'T2'}
    summary = cs.incoming_summary(listed)['by_role']
    assert summary['차용'] == {'count': 1, 'examples': ['제374조 영업양도']} and summary['준용']['count'] == 1


@pytest.mark.parametrize('role,reads', [(roles.SPECIFIES, ['B']), (roles.EXCEPTION, ['B']), (roles.BORROWS, []), (roles.MUTATIS, [])])
def test_guided_automatic_reading_uses_role_without_model(context_probe, monkeypatch, role, reads):
    from test_small_connection_context import probe
    from semantic_runtime.legal_agent import connection_scope as cs
    inv, directory, scope, f = probe(context_probe, monkeypatch)
    inv.s.profile = {'max_read_chars': 1000, 'answer_presentation': 'guided-conversation-v1', 'candidate_navigation': {'guided_loop': True}}
    inv.policy.update(small_connection_context=False, selected_connection_scope=True)
    for g in directory['groups']:
        for c in g['connections']: c['citation_role'] = role
    # Depth 2 opens the acquired pair's own directory (forward only); the
    # synthetic probe has no structural catalog, so record that call.
    opened = []
    monkeypatch.setattr(cs, 'inspect_directory', lambda inv, sub: opened.append(sub) or {'status': 'COMPLETE', 'groups': [], 'limits': [], 'unresolved': []})
    assert cs.acquire_role_chain(inv, scope, directory) == reads and f.calls == [1] * len(reads)
    assert len(opened) == (1 if reads and f.body.get('evidence') else 0) or not reads
    assert all(sub['structural_selection']['role_chain_depth'] == 2 for sub in opened)
    row = next(iter(inv.p['role_chain_directories'].values()))
    assert row['status'] == 'COMPLETE' and not row['model_called']
    # The same request never repeats the read; the character budget is shared.
    assert cs.acquire_small_directory(inv, scope, directory) == reads and f.calls == [1] * len(reads)
    if reads:
        assert inv.p['role_chain_budget']['chars'] > 0


def test_character_budget_leaves_pair_as_card(context_probe, monkeypatch):
    from test_small_connection_context import probe
    from semantic_runtime.legal_agent import connection_scope as cs, tool_availability as av
    inv, directory, scope, f = probe(context_probe, monkeypatch)
    inv.s.profile = {'max_read_chars': 1000, 'answer_presentation': 'guided-conversation-v1', 'candidate_navigation': {'guided_loop': True}}
    inv.policy.update(selected_connection_scope=True)
    for g in directory['groups']:
        for c in g['connections']: c['citation_role'] = roles.SPECIFIES
    monkeypatch.setattr(av, 'sequence_cost', lambda *a: (12001, 1))
    assert cs.acquire_role_chain(inv, scope, directory) == [] and f.calls == []
    row = next(iter(inv.p['role_chain_directories'].values()))
    assert row['skipped'][0]['reason'] == 'ROLE_CHAIN_CHARACTER_LIMIT'


def test_same_section_titles_offer_uncited_neighbors():
    from types import SimpleNamespace as S
    from semantic_runtime.legal_agent.guided_navigation import section_articles
    units = {('d', 'sec'): {'surface': '제5절', 'title': '제5절 정관의 변경', 'parent': None, 'span': [0, 9]}}
    for n, (art, title) in enumerate([('제433조', '정관변경의 방법'), ('제434조', '정관변경의 특별결의'), ('제435조', '종류주주총회'), ('제436조', '준용규정')]):
        units[('d', art)] = {'surface': art, 'title': title, 'parent': 'sec', 'span': [n, n + 1]}
        units[('d', art + '①')] = {'surface': '①', 'title': '', 'parent': art, 'span': [n, n + 1]}
    session = S(matcher=S(units=units, documents={'d': '상법'}), tools=S(sources={'src': {'document_id': 'd', 'unit_id': '제433조'}}))
    result = section_articles(session, [{'source_id': 'src'}])
    assert result[0]['section'] == '제5절 정관의 변경' and result[0]['document'] == '상법'
    assert [(r['coordinate'], r['already_read']) for r in result[0]['articles']] == [
        ('제433조', True), ('제434조', False), ('제435조', False), ('제436조', False)]
    assert section_articles(S(matcher=S(units={}), tools=S(sources={})), [{'source_id': 'x'}]) == []


# --- unread connected articles: same-section reading, reasons, display ------
def section_session(texts, *, extra=0):
    from types import SimpleNamespace as S
    units = {('d', 'sec'): {'surface': '제5절', 'title': '제5절 정관의 변경', 'parent': None, 'span': [0, 99]}}
    sources = {}; blocks = {}
    arts = [('제433조', '정관변경의 방법'), ('제434조', '정관변경의 특별결의'), ('제435조', '종류주주총회'),
            ('제436조', '준용규정'), ('제437조', '')] + [('제%d조' % (500 + n), '') for n in range(extra)]
    for n, (art, title) in enumerate(arts):
        units[('d', art)] = {'surface': art, 'title': title, 'parent': 'sec', 'span': [n, n + 1]}
        sources['s' + art] = {'document_id': 'd', 'unit_id': art}
        blocks[str(n)] = texts.get(art, art + ' 다른 내용')
    store = S(source=lambda did, bid: {'text': blocks[bid]})
    # Real matchers (SQLite ReverseMatcher and the Oracle Matcher) expose the member index.
    members = lambda did, uid: sorted(sid for sid, v in sources.items() if v['document_id'] == did and v['unit_id'] == uid)
    return S(matcher=S(units=units, _unit_sources=members), tools=S(sources=sources), store=store, scope={'d'})


class PagedUnits:
    """Oracle-port shape: point and parent lookups only; enumerating the corpus is forbidden."""
    def __init__(self, units): self.units = dict(units); self.calls = []
    def __getitem__(self, key): return self.units[key]
    def __contains__(self, key): return key in self.units
    def get(self, key, default=None): return self.units.get(key, default)
    def children_for(self, did, parent):
        self.calls.append(('children_for', did, parent))
        return [(k, v) for k, v in self.units.items() if k[0] == did and str(v.get('parent')) == str(parent)]
    def items(self): raise AssertionError('QUERY_NAV_BUDGET: whole-corpus unit scan')
    def __iter__(self): raise AssertionError('QUERY_NAV_BUDGET: whole-corpus unit scan')
    def __len__(self): raise AssertionError('unit count is a remote query; not needed here')


class PagedSources(dict):
    def items(self): raise AssertionError('QUERY_NAV_BUDGET: whole-corpus source scan')
    def values(self): raise AssertionError('QUERY_NAV_BUDGET: whole-corpus source scan')


def test_same_section_reads_use_parent_lookups_on_the_oracle_port(monkeypatch):
    """ADR-1426: units.items() paged the whole Gold corpus and hit the 10,000-row budget."""
    from types import SimpleNamespace as S
    from semantic_runtime.legal_agent import connection_scope as cs
    from semantic_runtime.legal_agent.guided_navigation import section_articles
    monkeypatch.setattr(cs.ur, 'blocks', lambda s, did, uid, extent: [str(int(uid[1:4]) - 433)] if uid.startswith('제43') else ['9'])
    texts = {'제435조': '제435조 회사가 종류주식을 발행한 경우에 정관을 변경함으로써 어느 종류주식의 주주에게 손해를 미치게 될 때에는'}
    plain = section_session(texts)
    expected = cs.section_neighbors(S(s=plain), {'members': [{'source_id': 's제433조'}]})
    paged = section_session(texts)
    paged.matcher.units = PagedUnits(paged.matcher.units)
    paged.tools.sources = PagedSources(paged.tools.sources)
    got = cs.section_neighbors(S(s=paged), {'members': [{'source_id': 's제433조'}]})
    assert got == expected and [r['label'] for r in got if r['matched']] == ['제435조 종류주주총회']
    assert paged.matcher.units.calls == [('children_for', 'd', 'sec')]  # one parent lookup, then cached
    titles = section_articles(S(matcher=S(units=paged.matcher.units, documents={'d': '상법'}), tools=paged.tools), [{'source_id': 's제433조'}])
    assert [r['coordinate'] for r in titles[0]['articles']] == ['제433조', '제434조', '제435조', '제436조', '제437조']


def test_same_section_neighbors_match_heading_words_and_skip_repealed_or_large(monkeypatch):
    from types import SimpleNamespace as S
    from semantic_runtime.legal_agent import connection_scope as cs
    monkeypatch.setattr(cs.ur, 'blocks', lambda s, did, uid, extent: [str(int(uid[1:4]) - 433)] if uid.startswith('제43') else ['9'])
    texts = {'제435조': '제435조 회사가 종류주식을 발행한 경우에 정관을 변경함으로써 어느 종류주식의 주주에게 손해를 미치게 될 때에는',
             '제436조': '제436조 제344조제3항에 따라 주주총회의 결의가 있어야 하는 경우에는 제435조를 준용한다.',
             '제437조': '제437조 삭제 <1995.12.29>'}
    assert cs.section_terms('제5절 정관의 변경') == ['정관', '변경']
    inv = S(s=section_session(texts))
    rows = {r['label']: r for r in cs.section_neighbors(inv, {'members': [{'source_id': 's제433조'}]})}
    assert rows['제435조 종류주주총회']['matched'] is True
    assert rows['제436조 준용규정']['matched'] is False and '제437조' not in rows
    assert all(r['anchor_label'] == '제433조 정관변경의 방법' for r in rows.values())
    # A large section is not one institution: no same-section reading at all.
    big = S(s=section_session(texts, extra=8))
    monkeypatch.setattr(cs.ur, 'blocks', lambda s, did, uid, extent: ['0'])
    assert cs.section_neighbors(big, {'members': [{'source_id': 's제433조'}]}) == []


def unread_inv(read_blocks=()):
    from types import SimpleNamespace as S
    s = section_session({'제436조': '제436조 ' + '가' * 2000})
    s.repo = S(evidence=lambda: [{'source_id': 's제435조', 'spans': [{'block_id': b} for b in read_blocks]}])
    skipped = [
        {'kind': 'SECTION', 'role': 'SAME_SECTION', 'outgoing': False, 'anchor_label': '제433조 정관변경의 방법',
         'section': '제5절 정관의 변경', 'label': '제436조 준용규정', 'terms': ['정관', '변경'],
         'identity': {'source_id': 's제436조', 'document_id': 'd', 'unit_id': '제436조'}, 'block_ids': ['3'],
         'reason': 'SECTION_TERMS_NOT_MATCHED'},
        {'kind': 'CONNECTION', 'role': 'SPECIFIES', 'outgoing': False, 'anchor_label': '제433조 정관변경의 방법',
         'identity': {'source_id': 's제435조', 'document_id': 'd', 'unit_id': '제435조'}, 'block_ids': ['2'],
         'reason': 'CHAIN_COUNT_LIMIT'},
        {'kind': 'CONNECTION', 'role': 'SPECIFIES', 'outgoing': False, 'anchor_label': 'x',
         'identity': {'source_id': 's제436조', 'document_id': 'd', 'unit_id': '제436조'}, 'block_ids': ['3'],
         'reason': 'CHAIN_COUNT_LIMIT'}]
    p = {'role_chain_directories': {'k': {'skipped': skipped}},
         'list_only_connections': {'m': {'role': 'MUTATIS', 'anchor_label': '제434조 정관변경의 특별결의',
             'identity': {'source_id': 's제437조', 'document_id': 'd', 'unit_id': '제437조'}, 'block_ids': ['4'],
             'label': '제437조 ②설립위원'}}}
    return S(s=s, p=p)


def test_unread_connections_keep_reason_origin_text_and_skip_read_targets():
    from semantic_runtime.legal_agent import connection_scope as cs
    out = cs.unread_connections(unread_inv())
    rows = out['entries']
    assert out['total'] == 3 and [r['target_label'] for r in rows] == ['제436조(준용규정)', '제435조(종류주주총회)', '제437조(설립위원)']
    first = rows[0]
    assert first['from_label'] == '제433조(정관변경의 방법)' and first['relation'] == 'SAME_SECTION'
    assert '(정관·변경)' in first['reason'] and first['judged_unneeded'] is True
    assert len(first['text']) == 1500 and first['text_clipped'] and first['used_as_evidence'] is False
    assert rows[1]['reason_code'] == 'CHAIN_COUNT_LIMIT' and rows[1]['judged_unneeded'] is False
    assert rows[2]['list_only'] and rows[2]['relation'] == 'MUTATIS'
    # Once the target is actually read, it is no longer listed as unread.
    assert [r['target_label'] for r in cs.unread_connections(unread_inv(read_blocks=['2']))['entries']] == ['제436조(준용규정)', '제437조(설립위원)']


def test_guided_answer_notes_unread_links_in_the_requested_sentence_form():
    from semantic_runtime.legal_agent import connection_scope as cs, guided_answer as ga
    unread = cs.unread_connections(unread_inv())
    issues = [{'id': 'Q1', 'question': 'q'}]
    schema = ga.schema(issues, [{'id': 'S1'}], unread['entries'])
    # Only rule-relevant links take a model note; reuse/extension links keep the system rule.
    assert schema['properties']['unread_notes']['items']['properties']['unread_ref']['enum'] == ['U1', 'U2']
    assert 'unread_notes' not in ga.schema(issues, [{'id': 'S1'}], [])['properties']
    rows = ga.unread_reply(unread['entries'], [{'unread_ref': 'U1', 'reason': '종류주식을 발행한 회사에만 해당하는 준용 규정이라서'}])
    assert rows[0]['reason_origin'] == 'MODEL_NOTE' and rows[1]['reason_origin'] == 'SYSTEM_RULE'
    text = ga.unread_paragraphs({'unread_connections': rows, 'unread_connection_total': 3})[0]
    assert text.startswith('확인하지 않은 연결 조문')
    assert ('같은 절(제5절 정관의 변경)에 있는 제436조(준용규정): 지금은 종류주식을 발행한 회사에만 해당하는 '
            '준용 규정이라서 읽을 필요가 없다고 판단했습니다.') in text
    assert '제433조(정관변경의 방법)에 연결된 제435조(종류주주총회) — 규칙을 구체화하는 조문(역방향): 지금은 ' in text
    assert '아직 읽지 않았습니다.' in text
    assert '제434조(정관변경의 특별결의)에 연결된 조문 중 이 조문을 준용하는 조문 1건(제437조)' in text
    assert text.endswith('필요하면 말씀해 주세요. 해당 조문을 이어서 읽겠습니다.')
    with pytest.raises(Exception):
        ga.verify({'open_questions': [], 'answer_points': [], 'unread_notes': [{'unread_ref': 'U3', 'reason': 'r'}]},
                  issues, [{'id': 'S1'}], [], complete=False, unread=unread['entries'])


def test_continue_request_carries_previous_unread_links():
    from semantic_runtime.legal_agent.guided_navigation import continuation
    parts = {'ASSESS': {'payload': {'guided_reply': {'unread_connections': [
        {'from_label': '제433조(정관변경의 방법)', 'target_label': '제436조(준용규정)', 'relation_text': '같은 절의 조문'}]}}}}
    value = continuation(parts, CONTINUE)
    assert value['previous_unread_connections'] == [{'from': '제433조(정관변경의 방법)', 'target': '제436조(준용규정)', 'relation': '같은 절의 조문'}]


def test_workflow_folds_unread_articles_under_their_origin_like_sources():
    import sys
    sys.path.insert(0, str(ROOT / '08_DEPLOYMENT/GENOS/workflow'))
    import genos_rag_chat as w
    from semantic_runtime.legal_agent import connection_scope as cs, guided_answer as ga
    rows = ga.unread_reply(cs.unread_connections(unread_inv())['entries'], [])
    rows[0]['text'] = '<script>x</script> [링크](u)'
    text = '설명\n\n' + ga.unread_paragraphs({'unread_connections': rows, 'unread_connection_total': 3})[0]
    body = {'answer': {'text': text}, 'assembly': {'term_agent': {'text_integrity': 'GUIDED_SOURCE_EXPLANATION',
            'guided_reply': {'schema_version': 'guided-conversation-v1', 'text_hash': w._workflow_display_digest(text),
                             'unread_connections': rows, 'unread_connection_total': 3}}}}
    html = w._unread_cards(body)
    assert '미확인 조문 · 3건' in html and html.count('data-genos-unread="true"') == 3
    assert '제433조(정관변경의 방법) → 제436조(준용규정) · 같은 절의 조문' in html
    assert '답변 근거로 쓰지 않은 원문 (앞부분)' in html.split('data-genos-unread="true"')[1]
    assert '<script>' not in html and '&lt;script&gt;' in html and '&#91;링크&#93;' in html
    rendered = w.render(body)
    assert rendered.index('GENOS_UNREAD_START') > rendered.index('설명')
    assert w._for_markdown(rendered).count('GENOS_UNREAD_START') == 1
    # A reply whose text no longer matches its saved hash shows no unread cards.
    body['assembly']['term_agent']['guided_reply']['text_hash'] = 'stale'
    assert w._unread_cards(body) == ''
