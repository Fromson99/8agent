"""Prior opinions survive research; only current authorized originals ground them."""
from conftest import term_glossary
from copy import deepcopy
import json
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import request_repair as rr, completion_contracts as cc
from semantic_runtime.legal_agent.errors import ContractError
from test_source_span_norm import SpanTransport, tree, settings, ROOT, ok

QUESTION = '승인 기준은?'
ISSUES = [{'id': 'Q1', 'question': QUESTION}]

def fixture_review():
    span = {'id': 'S1', 'source_id': 'article:s', 'document_id': 'd', 'block_id': 'b',
            'start_cp': 0, 'end_cp': 9, 'text': '승인 후 보고한다.', 'text_hash': digest('승인 후 보고한다.')}
    claim = {'claim_id': 'C1', 'issue_refs': ['Q1'], 'text': '승인 후 보고 의무가 있다.',
             'span_receipts': [deepcopy(span)]}
    state = {'model_used': 9, 'no_progress': 1, 'reentry_counters': {'used': 1}}
    rr.retain_assessment_review(state, {'claims': [claim]}, QUESTION)
    return state, span, claim

def test_exact_original_rebinds_current_reference_after_restart_and_epoch():
    state, span, claim = fixture_review()
    span['id'] = 'S99'
    restarted = json.loads(json.dumps(state))
    next_state = rr.new_epoch(restarted, reason='ASSESS_GAP_REENTRY')
    projected = rr.assessment_review_context(next_state, QUESTION, [span], ISSUES)
    assert projected['claims'][0]['evidence_refs'] == ['S99']
    assert projected['claims'][0]['text'] == claim['text']
    assert projected['status'] == 'PRIOR_MODEL_OPINIONS_FOR_REVIEW'
    assert 'text' not in next_state['assessment_reviews'][0]['payload']['claims'][0]['spans'][0]
    assert next_state['model_used'] == 9 and next_state['no_progress'] == 1
    assert next_state['reentry_counters'] == {'used': 1}

def test_duplicate_and_empty_later_assessments_preserve_existing_review():
    state, span, claim = fixture_review()
    rr.retain_assessment_review(state, {'claims': [claim]}, QUESTION)
    rr.retain_assessment_review(state, {'claims': []}, QUESTION)
    assert len(state['assessment_reviews']) == 1
    assert rr.assessment_review_context(state, QUESTION, [span], ISSUES)['claims']

@pytest.mark.parametrize('change', ['source_id', 'document_id', 'block_id', 'start_cp', 'end_cp', 'text', 'missing'])
def test_old_opinion_cannot_supply_missing_changed_or_unauthorized_original(change):
    state, span, _ = fixture_review()
    if change in ('start_cp', 'end_cp'): span[change] += 1
    elif change == 'text': span.update(text='다른 원문', text_hash=digest('다른 원문'))
    elif change != 'missing': span[change] = 'other'
    projected = rr.assessment_review_context(state, QUESTION, [] if change == 'missing' else [span], ISSUES)
    assert projected['claims'] == [] and projected['unavailable_claims'] == 1
    assert '승인 후 보고 의무' not in json.dumps(projected, ensure_ascii=False)
    assert len(state['assessment_reviews']) == 1

@pytest.mark.parametrize('kind', ['state', 'source'])
def test_corruption_fails_without_model_repair(kind):
    state, span, _ = fixture_review()
    if kind == 'state': state['assessment_reviews'][0]['payload']['claims'][0]['text'] = '변조'
    else: span['text'] = '변조'
    with pytest.raises(ContractError, match='hash mismatch'):
        rr.assessment_review_context(state, QUESTION, [span], ISSUES)

def test_request_and_issue_boundaries_are_preserved():
    state, span, _ = fixture_review()
    assert rr.assessment_review_context(state, '다른 질문', [span], ISSUES)['claims'] == []
    assert rr.assessment_review_context(state, QUESTION, [span], [{'id': 'Q2'}])['claims'] == []
    assert rr.assessment_review_context({}, QUESTION, [{'id': 'legacy'}], ISSUES)['claims'] == []

class RememberingTransport(SpanTransport):
    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        phase = view.get('source_stage', view['phase'])
        if phase.startswith('memory-assess'):
            self.assessment_inputs.append(deepcopy(view))
        return super().send_once(body=body, ticket=ticket)

def test_actual_api_delivers_prior_claims_after_research_and_reuses_request(tmp_path, tree):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    gen, idx = tree
    transport = RememberingTransport(True, False)
    transport.direct_note = False
    transport.assessment_inputs = []
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True,
        'completion_contract': True, 'completion_policy_version': cc.V8, 'compact_input': True}}
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'test_team', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app) as api:
        body = {'question': '모의승인규정 제1조 승인 기준은?', 'session_id': 'continuity', 'request_id': 'r1'}
        out = ok(api.post('/v1/rag/ask', json=body))
        assert out['assembly']['term_agent']['accepted_outcome']['answer_coverage'] == 'COVERED'
        first, second = transport.assessment_inputs
        assert first['previous_assessments']['claims'] == []
        remembered = second['previous_assessments']['claims']
        assert remembered and '승인' in remembered[0]['text']
        current_refs = {o['id'] for o in second['evidence_options']}
        assert set(remembered[0]['evidence_refs']) <= current_refs
        again = ok(api.post('/v1/rag/ask', json=body))
        assert again['answer'] == out['answer'] and len(transport.assessment_inputs) == 2
