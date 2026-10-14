"""The external-workflow backend renders once and binds the display to its result."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import copy
import json

import pytest
from fastapi.testclient import TestClient

import main_workflow
from test_rag_flow_svg import body, events, image_xml, workflow


@pytest.fixture
def backend(monkeypatch, tmp_path):
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path / 'runtime'))
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'on')
    calls = []
    active = ContextVar('test_workflow_progress')
    @contextmanager
    def capture(request_id, runtime, sink):
        token = active.set(sink)
        try:
            yield
        finally:
            active.reset(token)
    async def service(config, data):
        calls.append(copy.deepcopy(data))
        if data['API_TYPE'] not in {'LEGAL_AGENT', 'ELS_QUERY'}:
            return {'status': 200, 'body': {'operation': data['API_TYPE']}}
        for event in events():
            active.get()({**event, 'request_id': data['request_id']})
        from semantic_runtime.legal_agent.answer_stream import current_sink
        if current_sink() is not None:
            current_sink()('확인한 답변.')
        return {'status': 200, 'body': body()}
    monkeypatch.setattr(main_workflow.backend, 'capture', capture)
    monkeypatch.setattr(main_workflow.backend, 'service', service)
    return calls


def response_body(route, client):
    response = client.post(route, json={'API_TYPE': 'LEGAL_AGENT', 'question': '모의',
        'request_id': 'display-r1', 'scope': {'document_version_ids': ['allowed']}})
    assert response.status_code == 200
    if route == '/json':
        return response.json(), []
    frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    return next(row['data'] for row in frames if row['event'] == 'result'), frames


@pytest.mark.parametrize('route', ['/json', '/stream'])
def test_main_workflow_result_has_r9_graph_and_compact_progress_without_mutating_raw(route, backend):
    raw, frames = response_body(route, TestClient(main_workflow.app))
    provided = raw['body'].pop('workflow_display')
    assert raw == {'status': 200, 'body': body()}
    assert len(backend) == 1 and backend[0]['scope'] == {'document_version_ids': ['allowed']}
    assert provided['request_id'] == 'display-r1'
    assert provided['judgment_display_revision'] == 'judgment-evidence-svg-20261008-r10'
    assert provided['progress_display_revision'] == 'rag-source-provider-20261013-r2'
    assert provided['judgment_flow']['theme'] == 'graphite-evidence'
    assert image_xml(provided['text']).tag.endswith('svg')
    cards = provided['agentFlowExecutedData']
    joined = json.dumps(cards, ensure_ascii=False)
    assert '관련 문서 찾기' in joined
    assert len(cards) <= 5
    assert '예외 적용 근거가 부족합니다' not in joined and '돌아갑니다' not in joined
    assert '대기 중' not in joined and '내부 모델 대기' not in joined
    if frames:
        assert any(row['event'] == 'answer_delta' for row in frames)
        assert [row['event'] for row in frames][-1] == 'result'


def test_workflow_reuses_backend_display_and_cards_without_re_rendering(backend, monkeypatch):
    raw, _ = response_body('/json', TestClient(main_workflow.app))
    view = workflow()
    provided = raw['body']['workflow_display']
    monkeypatch.setattr(view, '_post_code_serving', lambda data: {'status': 200, 'body': {}})
    async def received(question, data, display, *, probe=False):
        return view.unwrap(copy.deepcopy(raw))
    monkeypatch.setattr(view, '_stream_code_serving', received)
    monkeypatch.setattr(view, '_judgment_flow', lambda *a, **kw: pytest.fail('matching server display was re-rendered'))
    result = asyncio.run(view.run({'question': '모의', 'request_id': 'display-r1'}))
    assert result['text'] == provided['text']
    assert result['agentFlowExecutedData'] == provided['agentFlowExecutedData']
    assert result['judgment_flow'] == provided['judgment_flow']
    assert result['workflow_display_binding']['producer'] == 'main_workflow'


@pytest.mark.parametrize('changed', ['request_id', 'answer', 'display', 'revision'])
def test_stale_or_modified_backend_display_is_rejected(backend, changed):
    raw, _ = response_body('/json', TestClient(main_workflow.app))
    view = workflow()
    current = view.unwrap(raw)
    assert view._bound_workflow_display(current, 'display-r1')
    if changed == 'request_id':
        request_id = 'later-request'
    else:
        request_id = 'display-r1'
        if changed == 'answer':current['answer']['text'] = '현재 요청의 다른 답변'
        elif changed == 'display':current['workflow_display']['text'] = '임의 수정'
        else:current['workflow_display']['judgment_display_revision'] = 'older'
    assert view._bound_workflow_display(current, request_id) is None


def test_non_rag_operations_and_workflow_mode_contract_are_preserved(backend):
    client = TestClient(main_workflow.app)
    response = client.post('/json', json={'API_TYPE': 'WARMUP_STATUS'})
    assert response.json() == {'status': 200, 'body': {'operation': 'WARMUP_STATUS'}}
    assert client.post('/chat', json={'question': '일반 질문'}).status_code == 409
    assert client.post('/chat', json={'question': '__verify__'}).json()['data']['text'] == 'verified'
    mode = client.get('/chat-mode').json()
    assert mode['mode'] == 'workflow' and mode['display_producer'] == 'main_workflow'
    assert mode['judgment_display_revision'] == 'judgment-evidence-svg-20261008-r10'
    assert mode['progress_display_revision'] == 'rag-source-provider-20261013-r2'
    assert mode['display_renderer_path'].endswith('/08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    assert len(backend) == 1


@pytest.mark.parametrize('route', ['/json', '/stream'])
def test_full_failure_is_kept_while_normal_progress_stays_compact(route, backend, monkeypatch):
    original = main_workflow.backend.service
    detail = 'ERROR_START\n' + 'x' * 45000 + '\nERROR_END'
    async def failed(config, data):
        await original(config, data)
        return {'status': 500, 'body': {'error': 'synthetic failure', 'detail': detail}}
    monkeypatch.setattr(main_workflow.backend, 'service', failed)
    raw, _ = response_body(route, TestClient(main_workflow.app))
    provided = raw['body'].pop('workflow_display')
    assert raw['status']==500 and raw['body']['answer_status']=='failed'
    assert 'ERROR_END' not in json.dumps(raw)
    assert provided['answer_status'] == 'failed'
    assert 'ERROR_END' not in provided['text'] and '조회 번호' in provided['text']
    view = workflow()
    raw['body']['workflow_display'] = provided
    assert view._bound_workflow_display(view.unwrap(raw), 'display-r1') == provided
