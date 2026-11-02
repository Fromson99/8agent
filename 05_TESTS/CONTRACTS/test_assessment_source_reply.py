from conftest import term_glossary
"""A valid unresolved judgment must not discard already verified originals."""
from copy import deepcopy
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.errors import ContractError
from test_main50_request_repair import tree, GAP
from test_bounded_delivered_handoff import StopTransport
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire


class EmptyAssessment(StopTransport):
    def send_once(self, *, body, ticket):
        v = json.loads(body['messages'][1]['content'])['view']
        phase = v.get('source_stage', v['phase'])
        if phase.startswith('memory-assess'):
            self.phases.append(phase)
            if getattr(self, 'invalid', False):
                return wire({'claims': [], 'issue_assessments': [], 'gaps': []})
            gap = deepcopy(GAP)
            if v['gap_history']:
                gap['previous_gap_key'] = v['gap_history'][-1]['gaps'][0]['gap_key']
            return wire({'claims': [],
                'issue_assessments': [{'issue_id': i['id'], 'status': 'INSUFFICIENT', 'reason':'요청된 원문 부족을 보존한다.'}
                    for i in v['issues']], 'gaps': [gap]})
        return super().send_once(body=body, ticket=ticket)


@pytest.mark.parametrize('rich', [False, True])
@pytest.mark.parametrize('version', [cc.V8])
@pytest.mark.parametrize('reentry_limit', [0, 1])
def test_empty_accepted_assessment_publishes_sources_and_reuses_request(tmp_path, tree, rich, version, reentry_limit):
    gen, idx = tree
    transport = EmptyAssessment('repaired')
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        **({'answer_presentation': 'grounded-narrative-v1'} if rich else {}),
        'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True,
            'completion_contract': True, 'completion_policy_version': version,
            'compact_input': True, 'assessment_reentry_limit': reentry_limit}}
    runtime = tmp_path/'runtime'
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(),
        implementation='legal-agent-unified-v6', legal_agent_profile=profile,
        legal_agent_transport=transport, runtime_root=runtime,
        memory_identity=lambda _: {'user_id': 'synthetic', 'team_id': 'risk_team', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    body = {'question': '모의승인규정 제1조 승인 기준은?', 'session_id': 'source-reply', 'request_id': 'r1'}
    with TestClient(app) as api:
        response = api.post('/v1/rag/ask', json=body)
        assert response.status_code == 200, response.text
        out = response.json()
        count = len(transport.phases)
        again = api.post('/v1/rag/ask', json=body)
        assert again.status_code == 200, again.text
        assert again.json()['answer'] == out['answer']
        assert len(transport.phases) == count
        assert again.json()['execution_stats']['llm_calls'] == 0
    assert not out['answer']['claims']
    assert '승인 후 보고한다.' in out['answer']['text']
    assert '모의승인규정' in out['answer']['text']
    assert '확정' in out['answer']['text'] and out['answer']['unresolved']
    assert '미확인 사유(AI 판단·검증 전): ' + GAP['reason'] in out['answer']['text']
    meta = out['assembly']['term_agent']
    assert meta['answer_coverage'] == 'INSUFFICIENT'
    assert meta['accepted_outcome']['disposition'] == 'LIMITED_ANSWER'
    assert meta['text_integrity'] == 'VERIFIED_SOURCE_EXCERPTS'
    import importlib.util
    spec = importlib.util.spec_from_file_location('source_reply_workflow', ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    workflow = importlib.util.module_from_spec(spec); spec.loader.exec_module(workflow)
    assert workflow._completion_answer_status(out, True) == 'partial'
    displayed = workflow.render(out)
    assert '승인 후 보고한다.' in displayed and workflow.REVIEW_INCOMPLETE_MESSAGE not in displayed
    assert GAP['reason'] in displayed and 'AI 판단·검증 전' in displayed
    assert transport.phases.count('memory-assess') == 1 + reentry_limit
    assert not any(p.startswith('memory-compose') for p in transport.phases)
    from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
    from semantic_runtime.legal_agent.unified_publication import validate_saved, validate_current
    journal = next((runtime/'legal-agent/runs').glob('*/'+out['run_id']+'/journal.sqlite'))
    repo = UnifiedRepository(journal)
    try:
        validate_saved(repo, out)
        events = [(k, json.loads(p)) for k, p in repo.db.execute('SELECT kind,payload_json FROM event')]
        assert any(k == 'ASSESSMENT_SOURCE_EXCERPT_REPLY' for k, p in events)
        if reentry_limit:
            assert any(k == 'ASSESSMENT_GAP_REPEATED' for k, p in events)
        budget = dict(repo.budget())
        deadline = repo.run()['deadline_at']
        changed = deepcopy(out); changed['answer']['text'] += ' 승인 가능하다.'
        with pytest.raises(ContractError, match='public answer differs'):
            validate_saved(repo, changed)
        with pytest.raises(ContractError, match='authorization changed'):
            validate_current(repo, out, app.state.pipeline.store, allowed_documents=[])
    finally:
        repo.close()
    # A fresh app instance recovers the same publication without a new budget or model call.
    if not rich and version == cc.V8 and not reentry_limit:
        restarted = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(),
            implementation='legal-agent-unified-v6', legal_agent_profile=profile,
            legal_agent_transport=transport, runtime_root=runtime,
            memory_identity=lambda _: {'team_id': 'risk_team', 'document_ids': ['d']})
        restarted.state.pipeline.term_agent.unit_fulltext = idx
        with TestClient(restarted) as api:
            resumed = api.post('/v1/rag/ask', json=body)
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()['answer'] == out['answer']
            assert len(transport.phases) == count
        repo = UnifiedRepository(journal)
        try:
            assert repo.budget() == budget and repo.run()['deadline_at'] == deadline
        finally:
            repo.close()
    from semantic_runtime.legal_agent.shortcut_store import selected_store
    with sqlite3.connect(selected_store(runtime)) as db:
        assert db.execute("SELECT count(*) FROM sw_event WHERE kind='ANSWER_PUBLISHED'").fetchone()[0] == 0


def source_assessment(version=cc.V8):
    from test_investigation_completion_adr0678 import sources
    originals = sources()
    a = {'claims': [], 'gaps': [deepcopy(GAP)], 'disposition': 'LIMITED_ANSWER',
         'issue_assessments': [{'issue_id': 'Q1', 'status': 'INSUFFICIENT', 'reason': '미확인'}],
         'answer_coverage': 'INSUFFICIENT', 'completion_contract': version,
         'source_excerpt_reply': cc.source_excerpt_reply(originals)}
    cc.refresh_limitations(a, [{'id': 'Q1', 'question': '승인 기준은?'}], 'REPEATED_ASSESSMENT_GAP')
    return a, originals


@pytest.mark.parametrize('version', [cc.V1, cc.V2, cc.V3, cc.CONTRACT, cc.V5, cc.V6, cc.V7, cc.V8])
def test_source_reply_internal_contract_is_separate_from_legal_claims(version):
    from jsonschema import validate
    from semantic_runtime.legal_agent.memory_rag import ANSWER
    a, originals = source_assessment(version)
    before = deepcopy(a)
    answer = cc.compose(a, cc.default_plan(a))
    cc.verify_source_excerpt_reply(a, originals)
    cc.verify_composition(a, answer)
    validate(answer, cc.internal_schema(ANSWER, 'COMPOSE'))
    assert a == before and answer['claims'] == []
    assert '聯結' in answer['text'] and '다만 예외를 확인한다.' in answer['text']


@pytest.mark.parametrize('mutation', ['text', 'source_id', 'heading', 'offset', 'covered', 'claim', 'removed'])
def test_source_reply_rejects_changed_span_identity_or_claim_promotion(mutation):
    a, originals = source_assessment()
    row = a['source_excerpt_reply']['sources'][0]
    if mutation == 'text': row['span_receipts'][0]['text'] += '승인 가능'
    elif mutation == 'source_id': row['source_id'] = 'other-team'
    elif mutation == 'heading': row['heading'] = '제99조'
    elif mutation == 'offset': row['span_receipts'][0]['start_cp'] += 1
    elif mutation == 'covered': a['answer_coverage'] = 'COVERED'
    elif mutation == 'claim': a['claims'] = [{'text': '승인 가능'}]
    elif mutation == 'removed': a['source_excerpt_reply']['sources'] = []
    with pytest.raises(ContractError): cc.verify_source_excerpt_reply(a, originals)


def test_no_verified_original_cannot_become_source_reply():
    with pytest.raises(ContractError): cc.source_excerpt_reply([])


def test_legacy_partial_judgment_is_preserved_without_promoting_coverage():
    a, originals = source_assessment(cc.CONTRACT)
    a['issue_assessments'][0]['status'] = 'PARTIAL'; a['answer_coverage'] = 'PARTIAL'
    cc.verify_source_excerpt_reply(a, originals)
    assert not cc.compose(a, cc.default_plan(a))['claims']


def test_invalid_assessment_stays_rejected_while_verified_sources_are_delivered(tmp_path, tree):
    gen, idx = tree; transport = EmptyAssessment('repaired'); transport.invalid = True
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True,
            'completion_contract': True, 'completion_policy_version': cc.V8, 'compact_input': True}}
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(),
        implementation='legal-agent-unified-v6', legal_agent_profile=profile,
        legal_agent_transport=transport, runtime_root=tmp_path/'runtime',
        memory_identity=lambda _: {'team_id': 'risk_team', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app) as api:
        response = api.post('/v1/rag/ask', json={'question': '모의승인규정 제1조 승인 기준은?',
            'session_id': 'invalid', 'request_id': 'r1'})
    assert response.status_code == 200,response.text
    result=response.json();outcome=result['assembly']['term_agent']['accepted_outcome']
    assert not result['answer']['claims'] and result['answer']['unresolved']
    assert outcome['disposition']=='LIMITED_ANSWER' and outcome['answer_coverage']!='COVERED'
    assert outcome['stop_reason']=='ASSESSMENT_CONTRACT_UNRESOLVED'
    assert [p for p in transport.phases if p.startswith('memory-assess')] == ['memory-assess', 'memory-assess-repair']
    for journal in (tmp_path/'runtime/legal-agent/runs').glob('*/*/journal.sqlite'):
        with sqlite3.connect(journal) as db:
            assert db.execute("SELECT count(*) FROM event WHERE kind='ASSESSMENT_SOURCE_EXCERPT_REPLY'").fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM event WHERE kind='COMPLETION_ASSESSMENT_REJECTED'").fetchone()[0] == 2
            assert db.execute("SELECT count(*) FROM event WHERE kind='ASSESSMENT_REVIEW_STOPPED'").fetchone()[0] == 1
