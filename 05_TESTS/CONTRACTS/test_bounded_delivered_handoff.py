"""Confirmed input survives rejected navigation; no model or live data calls."""
from copy import deepcopy
import json
import pytest

from test_navigation_delivery_recovery import tree, session, ready, delivery
from semantic_runtime.legal_agent import evidence_inventory as inventory
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.errors import ContractError
from test_source_span_norm import SpanTransport, proposal
from test_legal_agent_double_harness import ROOT, wire
from test_bounded_source_main import settings


class StopTransport(SpanTransport):
    def __init__(self, mode):
        super().__init__(False, False)
        self.mode = mode; self.failures = []; self.assessments = []

    def send_once(self, *, body, ticket):
        from semantic_runtime.legal_agent.navigation_input import expand_cards
        view = expand_cards(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage', view['phase'])
        if '-read-choice' in phase:
            self.phases.append(phase)
            if not view['sources']:
                return wire({'choice':'READ', 'selections':[{
                    'target':view['read_candidates'][0]['target'], 'issue_id':view['issues'][0]['id'],
                    'missing_need':'모의 원문 확인', 'relation':'DIRECT', 'source_ref':None}]})
            self.failures.append(phase)
            if self.mode == 'repaired' and phase.endswith('-repair'):
                return wire({'choice':'FINISH', 'basis_refs':[s['id'] for s in view['sources']],
                    'issue_refs':[i['id'] for i in view['issues']], 'evidence_sufficient':False,
                    'reason':'확보한 원문으로 판단'})
            # The response completes normally, but its empty source choice is invalid.
            return wire({'choice':'FINISH', 'basis_refs':[], 'issue_refs':[],
                         'evidence_sufficient':False, 'reason':'결정 미완료'})
        if phase.startswith('memory-assess'):
            self.phases.append(phase); self.assessments.append(deepcopy(view))
            options = view['evidence_options']
            ref = next(o['id'] for o in options if '승인 후 보고한다.' in o['text'])
            value = proposal('승인 후 보고한다.', 'OBLIGATION', [ref], ref)
            value.pop('disposition')
            # Current wire preserves issue-specific reasons.
            return wire(value)
        return super().send_once(body=body, ticket=ticket)


@pytest.mark.parametrize('version', [cc.CONTRACT, cc.V5, cc.V6, cc.V7, cc.V8])
def test_confirmed_unaccepted_pages_reach_assessment_after_bounded_stop(session, version):
    inv, data, _ = ready(session, version)
    inv.modern = version in (cc.V5, cc.V6, cc.V7, cc.V8)
    delivery(inv, data)
    inventory.reconcile_delivery(inv.s, inv.p, data, 'source-law-navigation-2')
    before = deepcopy(inv.p['delivery_history']); budget = inv.s.repo.budget()
    assert not inv.p['basis_history'] and not inventory.originals_for(inv.s, inv.p)
    first = inv.bounded_result('MODEL_DECISION_UNRESOLVED')
    again = inv.bounded_result('MODEL_DECISION_UNRESOLVED')
    assert first['status'] == 'complete' and first['final_ids']
    assert first['adoption_fallback'] and first['selected_evidence']
    assert first['answer_coverage'] == 'UNASSESSED' and not first['evidence_sufficient']
    assert first['stop_reason'] == 'MODEL_DECISION_UNRESOLVED'
    assert first['selected_originals'] == again['selected_originals']
    assert inv.p['delivery_history'] == before and not inv.p['basis_history']
    assert inv.s.repo.budget() == budget


@pytest.mark.parametrize('mutation', ['no_receipt', 'excluded', 'deferred', 'scope', 'bytes', 'budget'])
def test_bounded_fallback_preserves_delivery_authority_bytes_and_context_limit(session, mutation):
    inv, data, _ = ready(session)
    if mutation != 'no_receipt':
        delivery(inv, data)
        inventory.reconcile_delivery(inv.s, inv.p, data, 'source-law-navigation-2')
    if mutation in ('excluded', 'deferred'):
        for group in inv.p['groups'].values(): group['status'] = mutation.upper()
    if mutation == 'scope': inv.s.scope = []
    if mutation == 'bytes': next(iter(inv.p['delivery_history'].values()))['spans'][0]['text'] += '변조'
    if mutation == 'budget': inv.s.profile.update(max_read_chars=1, max_context_chars=2)
    if mutation in ('scope', 'bytes'):
        with pytest.raises(ContractError): inv.bounded_result('MODEL_DECISION_UNRESOLVED')
    else:
        result = inv.bounded_result('MODEL_DECISION_UNRESOLVED')
        assert result['status'] == 'pending' and not result['final_ids']
        assert '실제 열람한 원문을 판단 단계에 전달' not in result['sufficiency_reason']


def test_failed_choice_reentry_retains_originals_without_resetting_repair_budget(session):
    inv, data, _ = ready(session)
    delivery(inv, data)
    inventory.reconcile_delivery(inv.s, inv.p, data, 'source-law-navigation-2')
    phases = []; budget = inv.s.repo.budget()
    def reject(system, view, schema, phase, timeout):
        phases.append(phase)
        return {'choice':'FINISH', 'basis_refs':[], 'issue_refs':[],
                'evidence_sufficient':False, 'reason':'모의 선택 실패'}
    inv.invoke = reject
    first = inv.run(); checkpoint = deepcopy(inv.p)
    again = inv.run()
    assert len(phases) == 2 and phases[-1].endswith('-repair')
    assert first['selected_originals'] == again['selected_originals']
    assert first['adoption_fallback'] and again['adoption_fallback']
    assert inv.p['read_choice_reviews'] == checkpoint['read_choice_reviews']
    assert inv.p['delivery_history'] == checkpoint['delivery_history']
    assert inv.s.repo.budget() == budget


@pytest.mark.parametrize('mode', ['repaired', 'repeated'])
def test_current_api_publishes_verified_sources_and_duplicate_request_reuses_answer(tmp_path, tree, mode):
    import sqlite3
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    gen, idx = tree; transport = StopTransport(mode)
    profile = {**settings(), 'max_model_attempts':40, 'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1', 'investigation_control':True,
            'completion_contract':True, 'completion_policy_version':cc.V8, 'compact_input':True}}
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(),
        implementation='legal-agent-unified-v6', runtime_root=tmp_path/'runtime',
        legal_agent_profile=profile, legal_agent_transport=transport,
        memory_identity=lambda _: {'team_id':'test_team', 'document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app) as api:
        body = {'question':'모의승인규정 제1조 승인 기준은?', 'session_id':mode, 'request_id':'r1'}
        response = api.post('/v1/rag/ask', json=body)
        assert response.status_code == 200, response.text
        result = response.json(); count = len(transport.phases)
        assert '승인 후 보고한다.' in result['answer']['text']
        again = api.post('/v1/rag/ask', json=body)
        assert again.json()['answer'] == result['answer'] and len(transport.phases) == count
        assert len(transport.failures) == 2 and len(transport.assessments) == 1
    events = []
    for path in (tmp_path/'runtime/legal-agent/runs').glob('*/*/journal.sqlite'):
        with sqlite3.connect(path) as db:
            events.extend((k, json.loads(p)) for k,p in db.execute('SELECT kind,payload_json FROM event'))
    assert any(k == 'NAVIGATION_INPUT_DELIVERED' for k,p in events)
    if mode == 'repeated':
        stops = [p for k,p in events if k == 'INVESTIGATION_BOUNDED_STOP']
        assert stops[-1]['reason'] == 'MODEL_DECISION_UNRESOLVED'
        assert stops[-1]['adopted_sources'] == 0 and stops[-1]['delivered_fallback_sources'] > 0
        assert transport.assessments[0]['adoption_fallback'] is True
        assert result['assembly']['term_agent']['stop_reason'] == 'MODEL_DECISION_UNRESOLVED'


@pytest.mark.parametrize('mutation', ['none','excluded','deferred','scope','hash','limit'])
def test_acquired_assessment_original_survives_bounded_stop(session, mutation):
    inv, data, _ = ready(session)
    inv.modern = True
    inv.completion = True
    inv.s.profile['candidate_navigation']['answer_first'] = True
    first = inv.assessment_handoff()
    assert first and first['selected_originals'] and first['selected_evidence']
    assert inv.p['assessment_handoffs'] and not inv.p['basis_history']
    budget = dict(inv.s.repo.budget())
    if mutation in ('excluded','deferred'):
        for group in inv.p['groups'].values(): group['status'] = mutation.upper()
    elif mutation == 'scope': inv.s.scope = []
    elif mutation == 'hash': next(iter(inv.p['selected'].values()))['evidence'][0]['spans'][0]['text'] += '변조'
    elif mutation == 'limit': inv.s.profile.update(max_read_chars=1,max_context_chars=2)
    if mutation in ('scope','hash'):
        with pytest.raises(ContractError): inv.bounded_result('INVESTIGATION_BUDGET')
    else:
        result = inv.bounded_result('INVESTIGATION_BUDGET')
        if mutation == 'none':
            assert result['selected_originals'] == first['selected_originals']
            assert result['selected_evidence'] == first['selected_evidence']
            assert result['stop_reason'] == 'INVESTIGATION_BUDGET'
            assert not result['evidence_sufficient'] and result['answer_coverage'] == 'UNASSESSED'
            assert result['original_delivery_context']['navigation_delivery_claimed'] is False
            assert not inv.p['basis_history'] and not inv.p.get('delivery_history')
            assert inv.bounded_result('INVESTIGATION_BUDGET')['selected_originals'] == result['selected_originals']
        else: assert not result['selected_originals'] and result['status'] == 'pending'
    assert dict(inv.s.repo.budget()) == budget


@pytest.mark.parametrize('empty', [False, True])
def test_budget_limited_answer_first_native_api_keeps_source_and_gaps(tmp_path, tree, empty):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from test_assessment_gap_action import GapTransport
    gen, idx = tree; transport = GapTransport(repeat=True,empty=empty)
    # Legacy-entry fixture: ten calls leave one investigation slot after its first ASSESS.
    profile = {**settings(),'max_model_attempts':10,'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,
            'completion_contract':True,'completion_policy_version':cc.V8,'compact_input':True,
            'answer_first':True,'assessment_reentry_limit':2}}
    app = create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=tmp_path/'runtime',
        memory_identity=lambda _:{'team_id':'test_team','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app) as api:
        body = {'question':'모의승인규정 제1조 승인 기준은?','session_id':'bounded','request_id':'r1'}
        response = api.post('/v1/rag/ask',json=body)
        assert response.status_code == 200, (response.text,transport.phases)
        result = response.json(); count = len(transport.phases)
        assert '승인 후 보고한다.' in result['answer']['text'] and result['answer']['unresolved']
        assert result['assembly']['term_agent']['accepted_outcome']['disposition'] == 'LIMITED_ANSWER'
        assert count <= 10 and transport.phases.count('memory-assess') == 1, transport.phases
        again = api.post('/v1/rag/ask',json=body)
        assert again.json()['answer'] == result['answer'] and len(transport.phases) == count
        if empty: assert not result['answer']['claims']
        else: assert result['answer']['claims']
