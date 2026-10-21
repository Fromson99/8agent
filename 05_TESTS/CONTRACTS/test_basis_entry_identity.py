"""GENOS ask ingress with an enabled shared relationship DB; no live models."""
import json
import os
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.basis_links.execution import CURRENT
from test_risk_team_compare_workflow import ROOT
from test_internal_concept_comparison import tree, Transport
from test_authority import WHO, BODY as LINK, review_body

REQUEST = {'question': '대사: 모의내규와 모의승인규정의 승인 기준을 비교해 주세요.',
           'team_id': 'risk_team', 'session_id': 'entry-chat',
           'request_id': 'entry-request', 'use_llm': True}


@pytest.fixture
def enabled_app(tmp_path, tree, monkeypatch):
    from lawrag.pipeline.fulltext_stage import derive
    from lawrag.pipeline.search_selection import plan, activate
    from semantic_runtime import state_sqlite
    for key in ('WORKFLOW_USER_ID', 'TEAM_ID', 'GENOS_GENERATION', 'GENOS_DATA_ROOT'):
        monkeypatch.delenv(key, raising=False)
    selected = tmp_path / 'selected'
    derive(tree[0], selected, workers=1)
    activate(plan(selected, latest=True))
    runtime = tmp_path / 'runtime'
    marker = runtime / 'basis-links/SQLITE_ENABLED.json'
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({'schema_version': 'basis-shared-sqlite-v1',
                                 'database': 'authority.sqlite'}))
    # Only the mount classification is simulated; actual source/SQLite/API code runs.
    monkeypatch.setattr(state_sqlite, 'network_storage',
                        lambda p: Path(p).is_relative_to(runtime))
    profile = json.loads((ROOT / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
    transport = Transport()
    app = create_app(tmp_path, selected, contracts_root=ROOT,
                     workspace_root=Path(__file__).resolve().parents[2],
                     runtime_root=runtime, release={'mode': 'genos-generation'},
                     provider=object(), implementation='legal-agent-unified-v6',
                     legal_agent_profile={**profile, 'model_binding': transport.binding},
                     legal_agent_transport=transport)
    with app.state.pipeline.basis_factory() as service:
        row = service.propose(WHO, LINK)
        service.review(WHO, review_body(row))
    app.state.test_link_id = row['link']['link_id']
    app.state.test_db = marker.with_name('authority.sqlite')
    yield app
    app.state.pipeline.store.close()


def test_real_ask_enters_internal_before_link_lookup(enabled_app, monkeypatch):
    from semantic_runtime.basis_links import integration
    observed = []
    original = integration.parent_task

    def traced(ctx, state, side, action):
        before = [e['document_id'] for e in ctx.rag.evidence() if e['side'] == 'internal']
        original(ctx, state, side, action)
        observed.append((side, before, action['args']['task'].get('basis_targets', [])))

    monkeypatch.setattr(integration, 'parent_task', traced)
    with enabled_app.state.pipeline.basis_factory() as service:
        before = service.repo.history(enabled_app.state.test_link_id)
    sentinel = ('outer-context', {'team_id': 'unrelated_team'})
    token = CURRENT.set(sentinel)
    try:
        with TestClient(enabled_app) as client:
            response = client.post('/v1/rag/ask', json=REQUEST)
            if os.environ.get('BASIS_EXPECT_OLD_FAILURE') == '1':
                assert response.status_code == 403, response.text
                assert response.json()['error_code'] == 'BASIS_IDENTITY'
                assert not observed
                return
            assert response.status_code == 200, response.text
            result = response.json()
            assert result['status'] in ('completed', 'partial'), result
            assert all(result['rag_results'][s]['evidence_ids'] for s in ('internal', 'external'))
            assert observed[0] == ('internal', [], [])
            outside = next(v for v in observed if v[0] == 'external')
            assert set(outside[1]) == {'inside'}
            assert outside[2][0]['link_id'] == enabled_app.state.test_link_id
            assert outside[2][0]['retrieval_role'] == 'REVIEWED_BASIS'
            assert outside[2][0]['endpoint']['document_id'] == 'outside'
            calls = len(observed)
            again = client.post('/v1/rag/ask', json=REQUEST)
            assert again.status_code == 200 and again.json()['run_id'] == result['run_id']
            assert len(observed) == calls
            params = {'team_id': 'risk_team', 'session_id': REQUEST['session_id']}
            status = client.get('/v1/workflows/runs/' + result['run_id'], params=params)
            assert status.status_code == 200 and status.json()['answer'] == result['answer']
            assert client.get('/v1/workflows/runs/' + result['run_id'],
                              params={**params, 'session_id': 'another-chat'}).status_code == 404
        assert CURRENT.get() == sentinel
    finally:
        CURRENT.reset(token)
    # Existing comparison capture may append separate unapproved candidates.
    # It must not modify the already approved relationship or its history.
    with enabled_app.state.pipeline.basis_factory() as service:
        assert service.repo.history(enabled_app.state.test_link_id) == before


@pytest.mark.parametrize('change,code', [
    ({'document_ids': ['hidden']}, 'WORKFLOW_SCOPE_DENIED'),
    ({'session_id': ''}, 'WORKFLOW_SESSION_REQUIRED'),
    ({'team_id': 'invalid'}, 'WORKFLOW_SESSION_REQUIRED'),
])
def test_invalid_scope_and_session_still_rejected(enabled_app, change, code):
    with TestClient(enabled_app) as client:
        response = client.post('/v1/rag/ask', json={**REQUEST, **change})
        assert response.status_code in (403, 422), response.text
        assert response.json()['error_code'] == code
    assert CURRENT.get() is None


def test_basis_management_still_requires_trusted_identity(enabled_app):
    with TestClient(enabled_app) as client:
        assert client.get('/v1/basis-links').status_code == 403
        response = client.post('/v1/basis-links/proposals',
                               json={**LINK, 'user_id': 'claimed', 'team_id': 'risk_team'})
        assert response.status_code == 403 and response.json()['error_code'] == 'BASIS_IDENTITY'


def test_corrupt_link_keeps_existing_integrity_failure(enabled_app, monkeypatch):
    from semantic_runtime.basis_links import integration
    sides = []
    original = integration.parent_task

    def traced(ctx, state, side, action):
        sides.append(side)
        return original(ctx, state, side, action)

    monkeypatch.setattr(integration, 'parent_task', traced)
    with sqlite3.connect(enabled_app.state.test_db) as db:
        db.execute("UPDATE basis_revision SET payload='{}'")
    with TestClient(enabled_app) as client:
        response = client.post('/v1/rag/ask', json=REQUEST)
        assert response.status_code == 409, response.text
        assert response.json()['error_code'] == 'BASIS_INTEGRITY'
    assert sides == ['internal']  # Existing native cache dependency check fails closed.
    assert CURRENT.get() is None


def test_native_session_reuses_prepared_principal(enabled_app, monkeypatch):
    """Inspect the existing pipeline boundary, without another model call."""
    seen = []
    pipeline = enabled_app.state.pipeline
    def run(question, docs, use_llm, scope, **kwargs):
        context = kwargs['execution_context']
        seen.append(context['principal'])
        assert CURRENT.get() is None
        assert context['principal']['user_id'].startswith('session:')
        assert context['principal']['team_id'] == 'risk_team'
        assert context['principal']['document_ids'] == ['inside', 'outside']
        raise RuntimeError('synthetic stop after prepared identity')
    monkeypatch.setattr(pipeline, 'run', run)
    with TestClient(enabled_app, raise_server_exceptions=False) as client:
        response = client.post('/v1/rag/ask', json={
            **REQUEST, 'question': '영업일 승인 기준', 'use_llm': True})
        assert response.status_code == 500, response.text
    assert len(seen) == 1 and CURRENT.get() is None
