"""Synthetic contracts for the default draft return path; no model evaluation."""
import json
import importlib.util
from copy import deepcopy

import pytest

from conftest import term_glossary
from test_legal_agent_double_harness import ROOT, generation
from test_legal_agent_v5 import SETTINGS, drafted, session
from test_tool_exploration_v3 import delivered
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE, profile


def test_main_and_legacy_v5_profiles_default_to_no_final_review():
    pinned = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json').read_text())
    assert DEFAULT_PROFILE['final_review_enabled'] is False
    assert pinned['final_review_enabled'] is False
    assert profile({})['final_review_enabled'] is False
    pinned.pop('final_review_enabled')
    assert profile(pinned)['final_review_enabled'] is False
    assert profile({'final_review_enabled': True})['final_review_enabled'] is True


@pytest.mark.parametrize('value', [0, 1, 'false', None])
def test_final_review_switch_requires_boolean(value):
    with pytest.raises(ContractError, match='final_review_enabled'):
        profile({'final_review_enabled': value})


@pytest.mark.parametrize('limitation', ['', '신청서 제출 사실이 확인되지 않아 위반 여부는 조건부로 판단합니다.'])
def test_disabled_review_returns_draft_after_one_compose_call(tmp_path, generation, monkeypatch, limitation):
    with session(tmp_path, generation, profile={**SETTINGS, 'final_review_enabled': False}) as s:
        drafted(s)
        paragraph = deepcopy(s.work.heads('claim', current=True)[0]['payload'])
        phases = []
        initial_attempts = s.work.budget()['model_reserved']

        def generate(phase, view, name):
            phases.append(phase)
            assert phase == 'compose', 'review and review repairs must never be invoked'
            delivered(s, view)
            return {'paragraphs': [paragraph], 'limitations': [limitation] if limitation else []}

        monkeypatch.setattr(s.gateway, 'generate', generate)
        result, control = s.answer_and_review({
            'request': s.context.request, 'query': s.context.query,
            'retrieval': s.retrieval(), 'selection': {}, 'assembly': {}})
        answer = result['answer']
        assert phases == ['compose']
        assert s.work.budget()['model_reserved'] == initial_attempts + 1
        assert control == {**control, 'decision': 'FINAL', 'gate': 'BOUNDED'}
        assert answer['claims'][0]['text'] == paragraph['text']
        assert answer['text'].startswith(paragraph['text'])
        assert '법률 검토 필요사항' not in answer['text']
        assert '최종 원문 대조가 완료되지' not in answer['text']
        if limitation:
            assert limitation in answer['text'] and answer['unresolved']
        else:
            assert answer['text'] == paragraph['text'] and not answer['unresolved']
        receipt = answer['provider_receipt']
        assert receipt['final_review_policy'] == 'disabled'
        assert receipt['final_review_status'] == 'SKIPPED'
        assert receipt['quality_certified'] is False
        assert set(receipt['claim_review_status'].values()) == {'UNREVIEWED'}
        assert not s.work.heads('review', current=True)
        assert not s.work.heads('obligation_review', current=True)
        assert not s.work.db.execute("SELECT 1 FROM model_view WHERE phase='review'").fetchone()
        assert s.work.db.execute("SELECT 1 FROM event WHERE kind='FINAL_REVIEW_SKIPPED'").fetchone()
        assert all(row['status'] == 'OPEN' for row in result['assembly']['term_agent']['question_obligations']['items'])


def test_disabled_review_keeps_selected_source_membership_checks(tmp_path, generation):
    with session(tmp_path, generation, profile={**SETTINGS, 'final_review_enabled': False}) as s:
        drafted(s)
        paragraph = deepcopy(s.work.heads('claim', current=True)[0]['payload'])
        paragraph['evidence'] = ['E-not-delivered']
        view = s.view('compose', required=s.packed['evidence_ids'])
        delivered(s, view)
        with pytest.raises(ProposalError):
            s.commit_draft(view, {'paragraphs': [paragraph], 'limitations': []})


def test_delivered_draft_survives_selection_mismatch_without_repair_call(tmp_path, generation, monkeypatch):
    with session(tmp_path, generation, profile={**SETTINGS, 'final_review_enabled': False}) as s:
        drafted(s)
        paragraph = deepcopy(s.work.heads('claim', current=True)[0]['payload'])
        for head in s.work.heads('source_selection', current=True):
            s.work.invalidate('source_selection', head['entity_id'], head['version'])
        calls = []

        def generate(phase, view, name):
            calls.append(phase)
            delivered(s, view)
            return {'paragraphs': [paragraph], 'limitations': []}

        monkeypatch.setattr(s.gateway, 'generate', generate)
        result, control = s.answer_and_review({
            'request': s.context.request, 'query': s.context.query,
            'retrieval': s.retrieval(), 'selection': {}, 'assembly': {}})
        assert calls == ['compose']
        assert result['answer']['text'] == paragraph['text']
        assert not result['answer']['unresolved']
        spec = importlib.util.spec_from_file_location(
            'answer_fallback_workflow', ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
        workflow = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(workflow)
        assert '근거 연결' not in workflow.render(result)
        assert paragraph['text'] in workflow.render(result)
        assert result['answer']['claims'] == []
        assert 'draft_reference_status' not in result['answer']['provider_receipt']
        assert control['gate'] == 'BOUNDED'
        assert s.work.db.execute("SELECT 1 FROM event WHERE kind='DRAFT_REFERENCE_UNVERIFIED'").fetchone()


def test_undelivered_reference_does_not_enter_answer_fallback(tmp_path, generation, monkeypatch):
    with session(tmp_path, generation, profile={**SETTINGS, 'final_review_enabled': False}) as s:
        drafted(s)
        paragraph = deepcopy(s.work.heads('claim', current=True)[0]['payload'])
        paragraph['evidence'] = ['E-not-delivered']
        calls = []

        def generate(phase, view, name):
            calls.append(phase)
            delivered(s, view)
            return {'paragraphs': [paragraph], 'limitations': []}

        monkeypatch.setattr(s.gateway, 'generate', generate)
        result, _ = s.answer_and_review({
            'request': s.context.request, 'query': s.context.query,
            'retrieval': s.retrieval(), 'selection': {}, 'assembly': {}})
        assert calls == ['compose']
        assert 'draft_reference_status' not in result['answer']['provider_receipt']
        assert not s.work.db.execute("SELECT 1 FROM event WHERE kind='DRAFT_REFERENCE_UNVERIFIED'").fetchone()
