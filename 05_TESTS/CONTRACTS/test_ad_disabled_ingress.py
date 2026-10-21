"""Disabled administration must never inspect a legal request's AD workspace."""
import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient
from test_basis_entry_identity import enabled_app, tree, REQUEST


def forbidden(*args, **kwargs):
    raise AssertionError('disabled management was entered')


@pytest.mark.parametrize('bound_team', [None, 'risk_team'])
@pytest.mark.parametrize('old_session', [False, True])
def test_normal_request_skips_management_before_storage(enabled_app, monkeypatch, bound_team, old_session):
    from semantic_runtime import ad_gateway, ad_mode
    from semantic_runtime.ad_store import Store
    from semantic_runtime.legal_agent.shortcut_store import selected_store
    pipeline = enabled_app.state.pipeline
    runtime = pipeline.basis_shared_runtime
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(runtime))
    monkeypatch.delenv('AD_WORKSPACE', raising=False)
    if bound_team:
        monkeypatch.setenv('TEAM_ID', bound_team)
    path = selected_store(runtime)
    store = Store(path)
    with store.transaction():
        session = store.session(bound_team or 'request', 'genos-chat', REQUEST['session_id'])
        store.db.execute('UPDATE ad_session SET enabled=? WHERE id=?', (int(old_session), session['id']))
    store.close()
    with sqlite3.connect(path) as db:
        before = db.execute('SELECT * FROM ad_session').fetchall()
    calls = []
    def run(*args, **kwargs):
        calls.append(kwargs['execution_context']['principal'])
        raise RuntimeError('synthetic downstream stop')
    monkeypatch.setattr(pipeline, 'run', run)
    # A regression must fail even when TEAM_ID is present or a past AD session is enabled.
    if bound_team:
        monkeypatch.setattr(ad_gateway, 'workspace', forbidden)
    monkeypatch.setattr(ad_mode, 'handle', forbidden)
    with TestClient(enabled_app, raise_server_exceptions=False) as client:
        response = client.post('/v1/rag/ask', json={**REQUEST, 'question': '승인 기준을 알려주세요.'})
    assert response.status_code == 500, response.text
    assert len(calls) == 1 and calls[0]['team_id'] == 'risk_team'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM ad_session').fetchall() == before


def test_direct_basis_chat_disabled_without_workspace(enabled_app, monkeypatch):
    from semantic_runtime import ad_gateway
    monkeypatch.setattr(ad_gateway, 'workspace', forbidden)
    assert enabled_app.state.basis_chat(REQUEST) is None


def test_no_session_native_rag_uses_its_own_scope_and_keeps_basis(enabled_app, monkeypatch):
    from semantic_runtime.legal_agent import coordinator
    from semantic_runtime.legal_agent.memory_binding import RuntimeModel
    pipeline=enabled_app.state.pipeline
    runtime=pipeline.basis_shared_runtime
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(runtime))
    monkeypatch.delenv('AD_WORKSPACE',raising=False)
    monkeypatch.setattr(enabled_app.state,'basis_identity',forbidden)
    seen=[]
    def run_case(p,body,principal,options,lease):
        assert principal['team_id']=='risk_team'
        assert principal['document_ids']==['inside','outside']
        model=RuntimeModel(p,runtime,body,principal)
        try:
            source=model.ensure().sources.source
            assert source.basis_factory is p.basis_factory
            assert source.basis_principal is principal
        finally:model.close()
        seen.append(principal)
        raise RuntimeError('synthetic stop after actual scoped source binding')
    monkeypatch.setattr(coordinator,'run_case',run_case)
    with TestClient(enabled_app,raise_server_exceptions=False) as client:
        response=client.post('/v1/rag/ask',json={
            'question':'승인 기준을 알려주세요.','team_id':'risk_team','use_llm':True})
    assert response.status_code==500
    assert len(seen)==1


@pytest.mark.parametrize('change',[{'team_id':'invalid'}, {'document_ids':['hidden']}])
def test_no_session_scope_errors_still_block(enabled_app,monkeypatch,change):
    from semantic_runtime.legal_agent import coordinator
    monkeypatch.setattr(coordinator,'run_case',forbidden)
    with TestClient(enabled_app,raise_server_exceptions=False) as client:
        response=client.post('/v1/rag/ask',json={
            'question':'승인 기준','team_id':'risk_team','use_llm':True,**change})
    assert response.status_code in (403,422), response.text


def test_explicit_host_identity_is_not_bypassed(enabled_app,monkeypatch):
    monkeypatch.setattr(enabled_app.state.pipeline,'run',forbidden)
    @enabled_app.middleware('http')
    async def host_identity(request,call_next):
        request.state.workflow_principal={'user_id':'host-user','team_id':'another_team','document_ids':['inside']}
        return await call_next(request)
    with TestClient(enabled_app,raise_server_exceptions=False) as client:
        response=client.post('/v1/rag/ask',json={
            'question':'승인 기준','team_id':'risk_team','use_llm':True})
    assert response.status_code==403 and response.json()['error_code']=='BASIS_IDENTITY'


@pytest.mark.parametrize('endpoint', ['/v1/rag/memory/command', '/v1/rag/memory/query'])
def test_direct_management_api_disabled_before_session(enabled_app, monkeypatch, endpoint, caplog):
    from semantic_runtime import ad_gateway
    monkeypatch.setattr(ad_gateway, 'workspace', forbidden)
    with TestClient(enabled_app) as client:
        response = client.post(endpoint, json=REQUEST)
    assert response.status_code == 403
    assert any('AD_DISABLED' in str(r.__dict__) for r in caplog.records)


def test_direct_start_command_cannot_enable_management(enabled_app, monkeypatch, caplog):
    from semantic_runtime import ad_gateway, ad_mode
    monkeypatch.setattr(ad_gateway, 'workspace', forbidden)
    monkeypatch.setattr(ad_mode, 'handle', forbidden)
    monkeypatch.setattr(enabled_app.state.pipeline, 'run', forbidden)
    with TestClient(enabled_app) as client:
        response = client.post('/v1/rag/ask', json={**REQUEST, 'question': '[AD모드 시작]'})
    assert response.status_code == 403
    assert any('AD_DISABLED' in str(r.__dict__) for r in caplog.records)


def test_service_disables_worker_before_oracle_and_management_before_app(monkeypatch):
    import service
    from semantic_runtime import oracle_query_service
    monkeypatch.setenv('DP', 'oracle')  # Select working checkout; never contact Oracle.
    monkeypatch.setenv('AD_WORKER_ENABLED', '1')
    monkeypatch.setattr(oracle_query_service, 'external_runtime', forbidden)
    monkeypatch.setattr(service, 'application', forbidden)
    monkeypatch.setattr(service, '_AD_WORKER_RECOVERY', {'state': 'RUNNING'})
    service._recover_ad_worker()
    assert service._AD_WORKER_RECOVERY == {'state': 'DISABLED'}
    monkeypatch.delenv('DP')
    monkeypatch.setenv('GENOS_GENERATION', '/synthetic-generation')
    for question in ('승인 기준', '[AD모드 시작]', '[AD모드 종료]'):
        result = asyncio.run(service.service({}, {'API_TYPE': 'AD_PROBE', 'question': question,
                                                  'team_id': 'financial_team', 'ad_session_id': 'old'}))
        assert result['status'] == 200
        if question.startswith('[AD'):
            assert result['body']['ad_mode'] is False
        else:
            assert result['body'] == {'ad_handled': False}
