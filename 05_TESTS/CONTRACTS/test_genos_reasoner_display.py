"""Photo-shaped progress transport, independent of answer generation."""
import asyncio
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location('reasoner_display', ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def event(kind='phase', label='자료 확인 중', **kwargs):
    return {'schema_version': 'rag-progress-v1', 'kind': kind, 'label': label, **kwargs}


def rationale(block):
    return json.loads(block['data']['output']['content'])['visible_rationale']


def test_cumulative_photo_shape_dedup_and_exact_answer_stream(monkeypatch):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio')
    display = load()._ChatProgress({'socketIOClientId': 'mock-room'})
    sent = []
    async def emit(name, value, room):
        assert room == 'mock-room'
        sent.append((name, value))
    display.emit = emit
    async def run():
        await display.progress(event('reading', '원문 열람', details=['모의규정 · 제1조']))
        await display.progress(event('reading', '원문 열람', details=['모의규정 · 제1조']))
        await display.progress(event('selected', '근거 선택', details=['채택 · 이유: 승인 요건 확인']))
        await display.progress(event('heartbeat', elapsed_ms=32000))
        await display.progress(event('heartbeat', elapsed_ms=33000))
        assert all(name == 'agentFlowExecutedData' for name, _ in sent)
        await display.answer_delta({'schema_version': 'rag-answer-delta-v1', 'seq': 1, 'text': '확인된 답변.'})
        await display.progress(event(label='뒤늦은 진행'))
        await display.finish('확인된 답변.\n\n출처: 모의규정')
    asyncio.run(run())
    arrays = [value for name, value in sent if name == 'agentFlowExecutedData']
    assert [len(value) for value in arrays] == [1, 2, 3]
    assert arrays[1][0] == arrays[0][0]
    assert len({b['nodeId'] for b in arrays[-1]}) == 3
    assert all(b['nodeLabel'] == 'Visible Reasoner' and b['status'] == 'FINISHED' for b in arrays[-1])
    assert rationale(arrays[0][0]) == '[원문 열람 중]\n원문 열람 중 · 문서 1개 · 열람 시작 1개 범위\n모의규정 · 열람 시작 1개 범위\n  제1조'
    assert '승인 요건 확인' in rationale(arrays[1][1])
    assert '근거 선택' in rationale(arrays[2][2]) and '32초' in rationale(arrays[2][2])
    assert ''.join(value for name, value in sent if name == 'token') == '확인된 답변.\n\n출처: 모의규정'
    assert sent[-1] == ('end', 'end')


def test_limit_refreshes_last_node_without_mutating_earlier_emissions(monkeypatch):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio')
    display = load()._ChatProgress({'socketIOClientId': 'mock-room'})
    snapshots = []
    async def emit(name, value, room): snapshots.append(value)
    display.emit = emit
    async def run():
        for index in range(82):
            await display.progress(event(label=f'단계 {index}'))
    asyncio.run(run())
    assert len(display.blocks) == 80
    assert len(snapshots[0]) == 1
    assert snapshots[-1][:-1] == snapshots[-3][:-1]
    assert snapshots[-1][-1]['nodeId'] == snapshots[-3][-1]['nodeId']
    assert '단계 81' in rationale(snapshots[-1][-1])
    assert '단계 79' in rationale(snapshots[-3][-1])


@pytest.mark.parametrize('mode', ['socketio', 'socketio-inline'])
def test_many_annex_units_update_two_summaries_and_preserve_answer(monkeypatch, mode):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', mode)
    display = load()._ChatProgress({'socketIOClientId': 'mock-room'})
    sent = []
    async def emit(name, value, room):
        sent.append((name, value))
    display.emit = emit
    rows = [f'모의규정{i % 5} · {10000 + i}' for i in range(128)]
    async def run():
        for start in range(0, len(rows), 8):
            chunk = rows[start:start + 8]
            await display.progress(event('reading', '원문 열람 시작', count=8,
                                         details=chunk, elapsed_ms=start * 1000))
            await display.progress(event('read_complete', '원문 열람 결과', count=8,
                details=[row + ' · 일부 열람, 나머지 확인 필요' for row in chunk]))
        # Completing a partial range updates its state without counting it twice.
        for start in range(0, len(rows), 8):
            await display.progress(event('read_complete', '원문 열람 결과',
                details=[row + ' · 열람 완료' for row in rows[start:start + 8]]))
        await display.progress(event('selected', '근거 선택', details=['필요한 조문 · 제8조']))
        await display.progress(event('reading', '원문 열람 시작', details=rows[:8]))
        await display.finish('원래 최종 답변')
    asyncio.run(run())
    arrays = [value for name, value in sent if name == 'agentFlowExecutedData']
    assert len(display.blocks) == 3
    assert all(len(value) <= 3 for value in arrays)
    assert len(arrays[0]) == 1 and '열람 시작 8개 범위' in rationale(arrays[0][0])
    assert '열람 시작 128개 범위' in rationale(display.blocks[0])
    assert '확보 확인 128개 범위' in rationale(display.blocks[1])
    assert '일부 열람' not in rationale(display.blocks[1])
    assert '그 외 1개 문서' in rationale(display.blocks[0])
    assert '10125' in rationale(display.blocks[0])
    assert len(arrays)==4  # two initial channels, selection, one final snapshot; append-only transport
    assert arrays[0][0]['nodeId'] == display.blocks[0]['nodeId']
    tokens = [value for name, value in sent if name == 'token']
    if mode == 'socketio-inline':
        assert sum('**1. 열람**' in value for value in tokens) == 1
        assert sum('**2. 열람 결과**' in value for value in tokens) == 1
        assert len(tokens) == 4  # two read summaries, selection, final answer
    else:
        assert tokens == ['원래 최종 답변']
    assert sent[-1] == ('end', 'end')


def test_socket_failure_preserves_final_return_and_single_service_call(monkeypatch):
    module = load()
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio')
    calls = []
    async def stream(question, data, display):
        calls.append(question)
        async def fail(*args, **kwargs): raise RuntimeError('mock socket failure')
        display.emit = fail
        await display.progress(event())
        return {'answer': {'text': '원래 답변'}}
    monkeypatch.setattr(module, '_stream_code_serving', stream)
    # The current workflow checks AD mode before entering the answer stream.
    monkeypatch.setattr(module, '_post_code_serving', lambda body: {})
    result = asyncio.run(module._run_once({'question': '모의 질문', 'socketIOClientId': 'mock-room'}))
    assert calls == ['모의 질문']
    assert result['text'] == '원래 답변' and result['answer_status'] == 'answered'
    assert result['agentFlowExecutedData'][0]['data']['output']['content']
    assert result['progress_display_revision'] == module.PROGRESS_DISPLAY_REVISION
