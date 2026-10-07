"""Request admission correctness with synthetic data; no model or load experiment."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import threading

import pytest
from fastapi.testclient import TestClient

import service
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.workflow_tiers_policy import profile
from test_genos_team_selection import team_generation
from test_legal_agent_v5 import PROFILE, app_for


@pytest.mark.parametrize('value', [None, '', '0', '1', '4', '-1', 'many'])
def test_genos_request_limit_is_disabled_regardless_of_legacy_environment(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('GENOS_RAG_MAX_CONCURRENT_REQUESTS', raising=False)
    else:
        monkeypatch.setenv('GENOS_RAG_MAX_CONCURRENT_REQUESTS', value)
    pinned = {**PROFILE, 'max_concurrent_requests_per_process': 4}
    configured = profile(service._genos_v5_admission_profile(pinned))
    assert configured['max_concurrent_requests_per_process'] == 0
    assert pinned['max_concurrent_requests_per_process'] == 4


@pytest.mark.parametrize('value', [None, '', '0'])
def test_genos_model_binding_accepts_unlimited(monkeypatch, value):
    monkeypatch.setenv('GENOS_BASE_URL', 'https://internal-fixture.invalid')
    monkeypatch.setenv('GENOS_LLM_SERVING_ID', '123')
    monkeypatch.setenv('GENOS_LLM_KEY', 'synthetic-test-key')
    monkeypatch.setenv('GENOS_LLM_MODEL', 'fixture-model')
    monkeypatch.delenv('GENOS_LLM_URL', raising=False)
    if value is None:
        monkeypatch.delenv('GENOS_RAG_MAX_CONCURRENT_REQUESTS', raising=False)
    else:
        monkeypatch.setenv('GENOS_RAG_MAX_CONCURRENT_REQUESTS', value)
    configured, _ = service._genos_v5_environment_binding()
    assert configured['max_concurrent_requests_per_process'] == 0
    assert configured['final_review_enabled'] is False


@pytest.mark.parametrize('value', [-1, True, 1.5, '0'])
def test_profile_still_rejects_invalid_request_limits(value):
    with pytest.raises(ContractError, match='max_concurrent_requests_per_process'):
        profile({**PROFILE, 'max_concurrent_requests_per_process': value})


def test_unlimited_v5_overlapping_requests_keep_separate_scopes_and_release(tmp_path, team_generation, monkeypatch):
    monkeypatch.setenv('GENOS_RAG_MAX_CONCURRENT_REQUESTS', '1')
    app = app_for(tmp_path, team_generation, profile=service._genos_v5_admission_profile(PROFILE))
    agent = app.state.pipeline.term_agent
    assert agent.admission is None
    # All six real sessions must be open before any can finish: this would fail
    # under the old four-request cap even if individual requests finish quickly.
    opened = threading.Barrier(6, timeout=15)
    original = agent._open_session

    @contextmanager
    def synchronized(*args, **kwargs):
        with original(*args, **kwargs) as session:
            opened.wait()
            yield session

    monkeypatch.setattr(agent, '_open_session', synchronized)
    teams = ['risk_team', 'financial_team'] * 3
    with TestClient(app) as client:
        def ask(team):
            response = client.post('/v1/rag/ask', json={
                'question': '전체 문서 목록', 'team_id': team, 'use_llm': False})
            assert response.status_code == 200, response.text
            result = response.json()
            expected = {'duplicate', 'risk' if team == 'risk_team' else 'finance'}
            assert set(result['query']['scope']['document_version_ids']) == expected
            assert result['answer']['text']
            return result['run_id']

        with ThreadPoolExecutor(max_workers=6) as pool:
            run_ids = list(pool.map(ask, teams))
        assert len(set(run_ids)) == 6
        monkeypatch.setattr(agent, '_open_session', original)
        assert client.post('/v1/rag/ask', json={
            'question': '목록', 'team_id': 'missing_team', 'use_llm': False}).status_code == 422
        assert ask('risk_team') not in run_ids


def test_unlimited_leases_expire_on_exception_and_reject_foreign_owner(tmp_path, team_generation):
    app = app_for(tmp_path, team_generation, profile={**PROFILE, 'max_concurrent_requests_per_process': 0})
    agent = app.state.pipeline.term_agent
    try:
        with pytest.raises(RuntimeError, match='synthetic cancellation'):
            with agent.admit() as lease:
                with agent.admit(lease):
                    raise RuntimeError('synthetic cancellation')
        assert not lease.active
        with pytest.raises(ContractError, match='invalid request admission lease'):
            with agent.admit(lease):
                pass
        with agent.admit() as fresh:
            fresh.owner = object()
            with pytest.raises(ContractError, match='invalid request admission lease'):
                with agent.admit(fresh):
                    pass
    finally:
        app.state.pipeline.store.close()
