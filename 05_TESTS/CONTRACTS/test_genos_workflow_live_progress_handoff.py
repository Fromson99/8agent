"""The editor-only workflow handoff forwards backend progress while running."""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest


HANDOFF = (Path(__file__).resolve().parents[2] /
           '08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261007_r1/WORKFLOW_PASTE_ALL.txt')


def load_workflow():
    spec = importlib.util.spec_from_file_location('workflow_live_progress_handoff', HANDOFF)
    # The GENOS editor accepts the file as Python even though the handoff is TXT.
    module = types.ModuleType(spec.name if spec else 'workflow_live_progress_handoff')
    module.__file__ = str(HANDOFF)
    exec(compile(HANDOFF.read_text(encoding='utf-8'), str(HANDOFF), 'exec'), module.__dict__)
    return module


def test_live_workflow_progress_reaches_chat_before_final_result(monkeypatch):
    workflow = load_workflow()
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio-inline')
    monkeypatch.setattr(workflow, '_post_code_serving', lambda body: {'status': 200, 'body': {}})
    emitted = []
    class Socket:
        async def emit(self, event, value, room=None):
            emitted.append((event, value, room))
    monkeypatch.setitem(sys.modules, 'main_socketio', types.SimpleNamespace(sio_server=Socket()))

    async def check():
        progress_sent = asyncio.Event()
        release = asyncio.Event()
        async def backend(question, data, display, *, probe=False):
            display.transport.update(route='/stream', opened=True, progress_events=1)
            await display.progress({'schema_version': 'rag-progress-v1',
                                    'request_id': data['request_id'], 'kind': 'phase',
                                    'label': '요청을 접수함', 'elapsed_ms': 1})
            progress_sent.set()
            await release.wait()
            return {'answer': {'text': '완료'}, 'assembly': {}}
        monkeypatch.setattr(workflow, '_stream_code_serving', backend)
        task = asyncio.create_task(workflow.run({'question': '모의', 'socketIOClientId': 'room-1'}))
        await asyncio.wait_for(progress_sent.wait(), 3)
        assert not task.done()
        assert any(event == 'token' and '에이전트 진행 상황' in value and room == 'room-1'
                   for event, value, room in emitted)
        assert any(event == 'agentFlowExecutedData' and room == 'room-1'
                   for event, value, room in emitted)
        release.set()
        result = await asyncio.wait_for(task, 3)
        assert result['code_serving_transport']['route'] == '/stream'
        assert result['agentFlowExecutedData']
        assert emitted[-1] == ('end', 'end', 'room-1')
    asyncio.run(check())


@pytest.mark.parametrize('mode,with_sid', [('off', True), ('socketio-inline', False),
                                          ('final-cards', True)])
def test_workflow_socket_is_optional_and_not_imported_without_activation(monkeypatch, mode, with_sid):
    workflow = load_workflow()
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', mode)
    monkeypatch.delitem(sys.modules, 'main_socketio', raising=False)
    async def backend(question, data, display, *, probe=False):
        display.transport.update(route='/stream', opened=True, progress_events=1)
        await display.progress({'schema_version': 'rag-progress-v1',
                                'request_id': data['request_id'], 'kind': 'phase',
                                'label': '요청을 접수함', 'elapsed_ms': 1})
        return {'answer': {'text': '완료'}, 'assembly': {}}
    monkeypatch.setattr(workflow, '_stream_code_serving', backend)
    monkeypatch.setattr(workflow, '_post_code_serving', lambda body: {'status': 200, 'body': {}})
    data = {'question': '모의'}
    if with_sid:
        data['socketIOClientId'] = 'room-1'
    result = asyncio.run(workflow.run(data))
    assert result['text']
    if mode == 'final-cards':
        assert result['agentFlowExecutedData']
    assert 'main_socketio' not in sys.modules
