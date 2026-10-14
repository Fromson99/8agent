"""Operator settings reach real service profiles and durable request budgets; no model calls."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

import pytest
import service
from semantic_runtime.legal_agent.errors import BudgetExhausted
from semantic_runtime.legal_agent.workflow_tiers_policy import profile
from test_genos_team_selection import team_generation


ROOT = Path(__file__).resolve().parents[2]
SETTINGS = (
    'GENOS_RAG_MAX_MODEL_ATTEMPTS', 'GENOS_RAG_MAX_TOOL_ACTIONS', 'GENOS_RAG_WALL_SECONDS',
    'GENOS_RAG_SEARCH_ROUNDS', 'GENOS_RAG_ASSESSMENT_REENTRY_LIMIT',
)


@pytest.fixture(autouse=True)
def clean_budget_environment(monkeypatch):
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)


def pinned():
    return json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())


def test_unconfigured_settings_preserve_defaults_and_original_profile():
    original = pinned()
    snapshot = deepcopy(original)
    configured = profile(service._investigation_profile(original))
    assert service._investigation_budget(configured) == {
        'max_model_attempts': 40, 'finalization_reserve': 3, 'investigation_model_attempts': 37,
        'max_tool_actions': 1024, 'wall_seconds': 1800, 'max_no_progress': 2,
        'search_rounds': 8, 'assessment_reentry_limit': 2,
    }
    configured['candidate_navigation']['search_rounds'] = 100
    assert original == snapshot


@pytest.mark.parametrize('name', SETTINGS)
@pytest.mark.parametrize('value', ['-1', '1.5', 'many'])
def test_invalid_setting_names_are_reported(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        service._investigation_profile(pinned())


@pytest.mark.parametrize('name,value', [
    ('GENOS_RAG_MAX_MODEL_ATTEMPTS', '0'), ('GENOS_RAG_MAX_MODEL_ATTEMPTS', '3'),
    ('GENOS_RAG_MAX_TOOL_ACTIONS', '0'), ('GENOS_RAG_MAX_TOOL_ACTIONS', '4'),
    ('GENOS_RAG_WALL_SECONDS', '0'), ('GENOS_RAG_SEARCH_ROUNDS', '0'),
])
def test_finalization_reserves_and_positive_budgets_are_preserved(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        service._investigation_profile(pinned())


def test_reentry_can_be_disabled_and_blank_settings_use_defaults(monkeypatch):
    for name in SETTINGS:
        monkeypatch.setenv(name, '  ')
    monkeypatch.setenv('GENOS_RAG_ASSESSMENT_REENTRY_LIMIT', '0')
    configured = profile(service._investigation_profile(pinned()))
    assert configured['max_model_attempts'] == 40
    assert configured['candidate_navigation']['assessment_reentry_limit'] == 0


@pytest.mark.parametrize('mode', ['genos-generation', 'genos-data-current'])
def test_service_settings_reach_health_deadline_and_physical_reservations(
        tmp_path, team_generation, monkeypatch, mode):
    monkeypatch.setattr(service, '_APP', None)
    monkeypatch.setattr(service, '_BINDING', None)
    monkeypatch.setattr(service, '_provider', lambda *args: object())
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path / 'runtime'))
    monkeypatch.setenv('GENOS_RAG_IMPLEMENTATION', 'legal-agent-unified-v6')
    for name in ('LEGAL_AGENT_PROFILE', 'LEGAL_AGENT_PROFILE_SHA256', 'GENOS_LLM_URL',
                 'GENOS_LLM_SERVING_ID', 'GENOS_LLM_MODEL', 'GENOS_LLM_KEY'):
        monkeypatch.delenv(name, raising=False)
    if mode == 'genos-generation':
        monkeypatch.setenv('GENOS_GENERATION', str(team_generation))
    else:
        monkeypatch.delenv('GENOS_GENERATION', raising=False)
        data_root = tmp_path / 'built'
        (data_root / 'generations').mkdir()
        manifest = team_generation / 'manifest.json'
        (data_root / 'generations/CURRENT.json').write_text(json.dumps({
            'schema_version': 'genos-current-generation-v1', 'generation_id': 'fixture',
            'path': str(team_generation), 'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
        }))
        monkeypatch.setenv('GENOS_DATA_ROOT', str(data_root))
    for name, value in zip(SETTINGS, ('7', '6', '120', '12', '0')):
        monkeypatch.setenv(name, value)
    try:
        health = asyncio.run(service.service({}, {'API_TYPE': 'HEALTH'}))
        assert health['status'] == 200, health
        binding = health['body']['release']
        assert binding['mode'] == mode
        assert binding['investigation_budget']['investigation_model_attempts'] == 4
        assert binding['investigation_budget']['search_rounds'] == 12
        assert binding['investigation_budget']['assessment_reentry_limit'] == 0
        agent = service._APP.state.pipeline.term_agent
        canonical = json.dumps(agent.profile, sort_keys=True, separators=(',', ':')).encode()
        assert binding['effective_profile_sha256'] == hashlib.sha256(canonical).hexdigest()
        assert binding['service_entry_sha256'] == hashlib.sha256(Path(service.__file__).read_bytes()).hexdigest()
        pipeline = service._APP.state.pipeline
        request = {'question': '모의 승인?', 'use_llm': False}
        query = pipeline.plan(request['question'], team_id='risk_team')
        with agent.open_session(request, query=query, runtime=tmp_path / 'runtime') as session:
            assert 110 < session.context.deadline - time.monotonic() <= 120
            assert session.work.budget()['model_limit'] == 7
            assert session.work.budget()['tool_limit'] == 6
            view = session.work.save_view('investigate', {'purpose': 'synthetic budget contract'}, [])
            wire = {'messages': [{'role': 'system', 'content': 'Synthetic contract'},
                {'role': 'user', 'content': json.dumps({'view': view})}]}
            for attempt in range(1, 5):
                session.work.reserve_attempt(view, wire, 'fixture', attempt, 'investigate')
            with pytest.raises(BudgetExhausted):
                session.work.reserve_attempt(view, wire, 'fixture', 5, 'investigate')
            for attempt in range(1, 4):
                session.work.reserve_attempt(view, wire, 'fixture-final', attempt, 'compose')
            with pytest.raises(BudgetExhausted):
                session.work.reserve_attempt(view, wire, 'fixture-final', 4, 'compose')
            for _ in range(6):
                session.work.reserve_tool()
            with pytest.raises(BudgetExhausted):
                session.work.reserve_tool()
        # Settings are startup configuration: a cached app retains its original limits.
        monkeypatch.setenv('GENOS_RAG_MAX_MODEL_ATTEMPTS', '99')
        assert service.application() is service._APP
        assert agent.profile['max_model_attempts'] == 7
    finally:
        if service._APP is not None:
            service._APP.state.pipeline.store.close()


def test_environment_model_binding_accepts_operator_budget(monkeypatch):
    from types import SimpleNamespace
    from semantic_runtime import genos
    monkeypatch.setenv('GENOS_LLM_URL', 'http://synthetic.invalid')
    monkeypatch.setenv('GENOS_LLM_KEY', 'synthetic-contract-token')
    monkeypatch.setenv('GENOS_RAG_MAX_MODEL_ATTEMPTS', '60')
    monkeypatch.setenv('GENOS_RAG_MAX_TOOL_ACTIONS', '2048')
    monkeypatch.setattr(genos, 'from_env', lambda role: (SimpleNamespace(root='http://synthetic.invalid'), 'fixture-model'))
    original = pinned()
    configured, transport = service._genos_v5_environment_binding(original)
    assert configured['max_model_attempts'] == 60
    assert configured['max_tool_actions'] == 2048
    assert configured['finalization_reserve'] == 3
    assert configured['model_binding'] == transport.binding
    assert original['max_model_attempts'] == 40


def test_selected_local_release_receives_settings_without_rewriting_frozen_files(tmp_path, monkeypatch):
    monkeypatch.setattr(service, '_APP', None)
    monkeypatch.setattr(service, '_BINDING', None)
    monkeypatch.setattr(service, '_provider', lambda *args: object())
    for name in ('GENOS_GENERATION', 'GENOS_DATA_ROOT', 'GENOS_RAG_IMPLEMENTATION',
                 'LEGAL_AGENT_PROFILE', 'LEGAL_AGENT_PROFILE_SHA256'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path / 'runtime'))
    monkeypatch.setenv('OPEN_ROUTER', 'synthetic-not-used-for-model-calls')
    monkeypatch.setenv('GENOS_RAG_MAX_MODEL_ATTEMPTS', '60')
    monkeypatch.setenv('GENOS_RAG_MAX_TOOL_ACTIONS', '2048')
    monkeypatch.setenv('GENOS_RAG_WALL_SECONDS', '900')
    pointer = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    before = pointer.read_bytes()
    code_root, _, original_binding = service._local_release()
    source = code_root / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'
    original_profile = source.read_bytes()
    try:
        health = asyncio.run(service.service({}, {'API_TYPE': 'HEALTH'}))
        assert health['status'] == 200, health
        binding = health['body']['release']
        assert binding['release_id'] == original_binding['release_id']
        assert binding['profile_sha256'] == hashlib.sha256(original_profile).hexdigest()
        assert binding['investigation_budget']['investigation_model_attempts'] == 57
        assert binding['investigation_budget']['max_tool_actions'] == 2048
        assert binding['investigation_budget']['wall_seconds'] == 900
        actual = service._APP.state.pipeline.term_agent.profile
        assert actual['max_model_attempts'] == 60 and actual['wall_seconds'] == 900
        canonical = json.dumps(actual, sort_keys=True, separators=(',', ':')).encode()
        assert binding['effective_profile_sha256'] == hashlib.sha256(canonical).hexdigest()
        assert pointer.read_bytes() == before and source.read_bytes() == original_profile
    finally:
        if service._APP is not None:
            service._APP.state.pipeline.store.close()
