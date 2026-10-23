from conftest import term_glossary
"""Fixed synthetic tool contracts, no model or retrieval-quality experiment."""
import copy
import json
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError

from semantic_runtime.legal_agent import law_name_recovery as names
from semantic_runtime.legal_agent import law_navigation as ln, query_scope as qs
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from test_unit_fulltext_adaptive_read import tree, session
from test_followup_structure_lookup import investigation, apply, forbid_fulltext, structured_generation
from test_law_grouped_navigation import reader, decide
from test_main50_request_repair import tree as bound_tree


def failed(inv, query='모의승인규칙 제1조'):
    data, actions = inv.view()
    target = next(k for k, a in actions.items() if a['action'] == 'SEARCH_STRUCTURE'
                  and a['identity']['document_id'] is None)
    return apply(inv, data, actions, 'SEARCH_STRUCTURE', target, [query])


def test_title_search_only_returns_permitted_metadata():
    m = SimpleNamespace(documents={'a':'모의 승인 규정', 'b':'모의 승인 시행규칙', 'hidden':'모의승인규칙',
                                  'unrelated':'휴가규정', 'annex':'모의 승인 규정 별표'},
        document_context={'annex':{'document_role':'annex'}}, document_aliases={})
    rows, total = names.candidates(m, ['a','b','unrelated','annex'], '모의승인규칙')
    assert {r['document_id'] for r in rows} == {'a','b'} and total == 2
    assert all(not r['citation_eligible'] and 'text' not in r for r in rows)
    assert names.candidates(m, ['unrelated'], '모의승인규칙') == ([], 0)


def test_failed_pair_offers_name_selection_preserving_original_coordinate(session, monkeypatch):
    native, idx = session; inv = investigation(native)
    inv.policy['structure_first'] = True
    forbid_fulltext(monkeypatch, idx)
    data, actions = failed(inv)
    r = data['law_name_recovery']
    assert r['name_query'] == '모의승인규칙'
    assert r['structure_filter']['coordinate'] == '제1조'
    row = next(r for r in r['candidates'] if r['document_id'] == 'd')
    assert actions[row['retry_action']]['action'] == 'RETRY_LAW_STRUCTURE'
    before = copy.deepcopy(inv.p['selected'])
    data, actions = apply(inv, data, actions, 'RETRY_LAW_STRUCTURE', row['retry_action'])
    assert inv.p['selected'] == before
    assert data['law_name_recovery'] is None
    assert data['structure_catalogue']['items'][0]['coordinate'] == '제1조'
    assert inv.p['structure_page']['name_retry']['original_queries'] == ['모의승인규칙 제1조']
    data, _ = apply(inv, data, actions, 'READ_ARTICLES', data['structure_catalogue']['items'][0]['read_action'])
    assert data['sources'] and any('승인' in r['text'] for r in data['sources'])
    assert all(g['status'] != 'ACTIVE' for g in inv.p['groups'].values())


def test_retry_miss_preserves_failure_without_loop_or_read(session):
    native, _ = session; inv = investigation(native)
    data, actions = failed(inv, '모의승인규칙 제99조')
    target = data['law_name_recovery']['candidates'][0]['retry_action']
    data, actions = apply(inv, data, actions, 'RETRY_LAW_STRUCTURE', target)
    page = inv.p['structure_page']
    assert page['lookup_status'] == 'MISS' and page['failure']['code'] == 'MISSING_COORDINATE'
    assert page['name_retry']['structure_filter']['coordinate'] == '제99조'
    assert not data['law_name_recovery']
    assert not any(a['action'] == 'RETRY_LAW_STRUCTURE' for a in actions.values())


def test_initial_catalogue_uses_same_recovery_and_no_hit_stays_unconfirmed(session):
    native, _ = session; inv = investigation(native)
    page = qs.catalogue(inv.s, queries=['모의승인규칙 제1조'])
    assert page['law_name_recovery']['candidates'][0]['document_id'] == 'd'
    missing = qs.catalogue(inv.s, queries=['우주비행연료법 제99조'])
    assert missing['law_name_recovery']['candidates'] == []
    assert missing['lookup_status'] == 'MISS'


def test_typed_missing_coordinate_preserves_all_filter_fields(session):
    native, _ = session; inv = investigation(native)
    filters = {'coordinate':'제99조', 'title':'승인', 'coordinate_scope':'body'}
    page = qs.catalogue(inv.s, document_id='d', structure_filter=filters)
    assert page['law_name_recovery']['structure_filter'] == filters
    assert page['law_name_recovery']['name_query'] == '모의승인규정'


@pytest.mark.parametrize('code', ['OUTSIDE_SCOPE','MISSING_ORIGINAL','NON_UNIQUE_ORIGINAL',
    'AMBIGUOUS_COORDINATE','UNRESOLVED_COORDINATE_BINDING','UNSUPPORTED_STRUCTURE_RANGE'])
def test_integrity_and_unsupported_failures_never_use_name_recovery(code):
    page = {'offset':0,'document_id':None,'queries':['모의규정 제1조'],
            'resolutions':[], 'failure':{'code':code}}
    assert names.attach(page, None, []) is page


@pytest.mark.parametrize('query', ['모의승인규칙 부칙 제1조', '모의승인규칙 제1조부터 제2조',
    '모의승인규칙 제1조 제2조', '제99조'])
def test_ambiguous_pairs_ranges_and_missing_names_do_not_invent_a_pair(session, query):
    native, _ = session; inv = investigation(native)
    page=qs.catalogue(inv.s, queries=[query])
    if query == '제99조':
        assert 'law_name_recovery' not in page
    else:
        clue=page['law_name_recovery']
        assert clue['structure_filter'] is None and clue['requires_structure_decision']
        assert clue['original_queries'] == [query]


def test_name_search_respects_user_direct_document_boundary(session):
    native, _ = session; inv = investigation(native)
    scope = qs.resolve({'operation':'REPLACE','targets':[{'document':'모의승인규정','structure':None}],
        'user_quote':'모의승인규정'}, None, inv.s.matcher, inv.s.scope, '모의승인규정')
    qs.attach(inv.s, scope)
    page = qs.catalogue(inv.s, queries=['모의승인규칙 제99조'])
    assert {r['document_id'] for r in page['law_name_recovery']['candidates']} <= {'d'}
    assert qs.active(inv.s) == scope


def test_resume_return_and_repeated_retry_share_history_and_budget(session):
    native, _ = session; inv = investigation(native)
    data, actions = failed(inv)
    frame = data['chain_frame_id']; target = data['law_name_recovery']['candidates'][0]['retry_action']
    state = copy.deepcopy(inv.p)
    resumed = ln.Investigation(inv.s, inv.question, inv.record, reader, 120, state, None)
    data, actions = resumed.view()
    data, actions = apply(resumed, data, actions, 'RETRY_LAW_STRUCTURE', target)
    assert len(resumed.p['structure_search_history']) == 2
    point = next(p for p in data['return_points'] if p['id'] == frame)
    data, actions = apply(resumed, data, actions, 'RETURN_TO', point['return_action'])
    assert target not in actions
    with pytest.raises(ProposalError, match='unchanged'):
        names.validate_retry(resumed, {'document_id':'d',
            'recovery_id':resumed.p['structure_page']['law_name_recovery']['recovery_id']})
    assert len(resumed.p['law_name_retry_history']) == 1


def test_budget_exhaustion_does_not_offer_name_retry(session):
    native, _ = session; inv = investigation(native)
    inv.policy['search_rounds'] = 1
    data, actions = failed(inv)
    assert data['law_name_recovery']['candidates'][0]['retry_action'] is None
    assert all(a['action'] != 'RETRY_LAW_STRUCTURE' for a in actions.values())


def test_metadata_hash_acl_and_model_coordinate_change_are_rejected(session):
    native, _ = session; inv = investigation(native)
    data, actions = failed(inv)
    target = data['law_name_recovery']['candidates'][0]['retry_action']
    with pytest.raises(ValidationError):
        apply(inv, data, actions, 'RETRY_LAW_STRUCTURE', target, ['제2조'])
    context = inv.s.matcher.document_context
    original = copy.deepcopy(context['d'])
    try:
        context['d'] = {**original,'document_title':'변조된 제목'}
        with pytest.raises(ContractError, match='metadata changed'):
            apply(inv, data, actions, 'RETRY_LAW_STRUCTURE', target)
    finally:
        context['d'] = original
    scope = inv.s.scope
    try:
        inv.s.scope = []
        with pytest.raises(ContractError, match='outside search scope'):
            names.validate_retry(inv, actions[target]['identity'])
    finally:
        inv.s.scope = scope


def test_compact_choice_sees_candidates_and_cannot_rewrite_locator(session):
    from semantic_runtime.legal_agent.decision_projection import choose_read
    native, _ = session; inv = investigation(native)
    data, actions = failed(inv); inv.modern = True
    seen = []
    def invoke(system, payload, schema, phase, timeout):
        seen.append(payload)
        row = payload['law_name_recovery']['candidates'][0]
        assert row['title'] == '모의승인규정' and '원래 조문' in system
        return {'choice':'RETRY_LAW_STRUCTURE','target':row['retry_action'],
            'issue_id':data['issues'][0]['id'],'missing_need':'실제 이름 확인 후 원래 조문 찾기',
            'relation':'DIRECT','source_ref':None}
    inv.invoke = invoke
    decision = choose_read(inv, data, actions, 'contract')
    assert seen and decision['next_action'] == 'RETRY_LAW_STRUCTURE' and decision['queries'] == []
    inv.execute(decision, data, actions)
    assert inv.p['structure_page']['items'][0]['coordinate'] == '제1조'


def test_current_api_name_selection_read_publication_and_restart(tmp_path, bound_tree):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.navigation_input import expand_cards
    from test_assessment_source_reply import EmptyAssessment
    from test_bounded_source_main import settings
    from test_legal_agent_double_harness import ROOT, wire
    from test_memory_runtime_v2 import command

    class Transport(EmptyAssessment):
        def __init__(self):
            super().__init__('repaired')
            self.name_choices = []
            self.searched = False

        def send_once(self, *, body, ticket):
            view = expand_cards(json.loads(body['messages'][1]['content'])['view'])
            phase = view.get('source_stage', view['phase'])
            if '-read-choice' not in phase:
                return super().send_once(body=body, ticket=ticket)
            self.phases.append(phase)
            issue = view['issues'][0]['id']
            recovery = view.get('law_name_recovery')
            common = {'issue_id':issue,'missing_need':'실제 법령 이름과 지정 조문의 원문 확인',
                      'relation':'DIRECT','source_ref':None}
            if recovery:
                row = next(r for r in recovery['candidates'] if r['title'] == '모의승인규정')
                assert recovery['name_query'] == '모의승인규칙'
                assert recovery['structure_filter']['coordinate'] == '제1조'
                self.name_choices.append(copy.deepcopy(recovery)); self.searched = True
                return wire({'choice':'RETRY_LAW_STRUCTURE','target':row['retry_action'],**common})
            if not self.searched:
                self.searched = True
                option = next(r for r in view['tool_options'] if r['choice'] == 'CATALOG_SEARCH')
                return wire({'choice':'CATALOG_SEARCH','target':option['target'],
                             'queries':['모의승인규칙 제1조'],**common})
            if not view['sources']:
                row = next(r for r in view['read_candidates'] if r.get('coordinate') == '제1조')
                return wire({'choice':'READ','selections':[{'target':row['target'],**common}]})
            return wire({'choice':'FINISH','basis_refs':[r['id'] for r in view['sources']],
                'issue_refs':[issue],'evidence_sufficient':False,'reason':'읽은 원문을 전달하고 미확인을 보존'})

    gen, idx = bound_tree; transport = Transport()
    transport.command = command('CASE_START',document_scope_mode='AUTHORIZED',task='승인 기준은?',
                                queries=['모의승인규칙 제1조'],facts=[])
    profile = {**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,
            'completion_contract':True,'completion_policy_version':'investigation-completion-v8',
            'compact_input':True,'structure_first':True,'selectable_search':True,
            'assessment_reentry_limit':0}}
    runtime = tmp_path/'api-runtime'
    def app():
        result = create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),
            implementation='legal-agent-unified-v6',legal_agent_profile=profile,
            legal_agent_transport=transport,runtime_root=runtime,
            memory_identity=lambda _:{'team_id':'test_team','document_ids':['d']})
        result.state.pipeline.term_agent.unit_fulltext = idx
        return result
    request = {'question':'승인 기준은?','session_id':'law-name','request_id':'r1'}
    with TestClient(app()) as api:
        response = api.post('/v1/rag/ask',json=request)
        assert response.status_code == 200, response.text
        first = response.json(); calls = len(transport.phases)
        again = api.post('/v1/rag/ask',json=request)
        assert again.status_code == 200 and again.json()['answer'] == first['answer']
        assert len(transport.phases) == calls
    assert len(transport.name_choices) == 1
    assert '승인 후 보고한다.' in first['answer']['text']
    steps = first['assembly']['term_agent']['investigation_chain']['steps']
    retry = next(r for r in steps if r['action'] == 'RETRY_LAW_STRUCTURE')
    assert retry['structure_lookup']['name_retry']['structure_filter']['coordinate'] == '제1조'
    assert any(r['action'] == 'READ_ARTICLES' for r in steps)
    with TestClient(app()) as api:
        resumed = api.post('/v1/rag/ask',json=request)
        assert resumed.status_code == 200 and resumed.json()['answer'] == first['answer']
        assert len(transport.phases) == calls
