"""User-visible footnotes are hidden without altering evidence or source labels."""
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'


@pytest.fixture
def workflow():
    spec = importlib.util.spec_from_file_location('answer_reference_workflow', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('raw, expected', [
    ('수집하여야 합니다 [4]. 최소한으로 수집해야 합니다 [3]. 목적을 명확히 합니다 [1].',
     '수집하여야 합니다. 최소한으로 수집해야 합니다. 목적을 명확히 합니다.'),
    ('답변[1]입니다. 답변 [2, 3]입니다 [4–6].', '답변입니다. 답변입니다.'),
    ('답변 [1][2] [3].', '답변.'),
    ('**답변** [1]. "원문 [2]" [3] 및 `값 [4]` [5].',
     '**답변**. "원문 [2]" 및 `값 [4]`.'),
    ('답변 [ 1 ; 3 ]\n다음 문단 [2]', '답변\n다음 문단'),
    ('「개인정보 보호법」 제3조제1항 및 제2항, [별표 1], [시행 2026. 9. 29.]',
     '「개인정보 보호법」 제3조제1항 및 제2항, [별표 1], [시행 2026. 9. 29.]'),
    ('원문은 "항목 [1]"입니다 [3].', '원문은 "항목 [1]"입니다.'),
    ('원문은 “항목 [1]” 및 『항목 [2]』입니다 [3].', '원문은 “항목 [1]” 및 『항목 [2]』입니다.'),
    ('`값 [1]`입니다 [3].\n```python\nvalue = [1]\n```',
     '`값 [1]`입니다.\n```python\nvalue = [1]\n```'),
    ('[1] 첫 항목\n  [2] 둘째 항목', '[1] 첫 항목\n  [2] 둘째 항목'),
    ('링크 [1](https://example.invalid) 및 링크 [2][원문]',
     '링크 [1](https://example.invalid) 및 링크 [2][원문]'),
    (r'원문 \[1\] 및 값 = [0, 1]', r'원문 \[1\] 및 값 = [0, 1]'),
    ('미완료 문장 [', '미완료 문장 ['),
])
def test_prose_footnotes_and_literal_content(workflow, raw, expected):
    assert workflow._without_inline_reference_numbers(raw) == expected


@pytest.mark.parametrize('policy', [None, 'advisory', 'disabled'])
def test_render_cleans_answer_but_retains_sources_and_original_body(workflow, policy):
    body = {'answer': {'text': '수집해야 합니다 [4].',
            'claims': [{'evidence_ids': ['source:used']}]},
            'assembly': {'context': [{'id': 'source:used', 'document_name': '[별표 1] 개인정보 보호법',
                         'ancestors': [{'title': '제3조제1항'}]}]}}
    if policy:
        body['answer']['provider_receipt'] = {'final_review_policy': policy}
    before = deepcopy(body)
    rendered = workflow.render(body)
    assert rendered == '수집해야 합니다.\n\n**출처**\n- [별표 1] 개인정보 보호법 · 제3조제1항'
    assert body == before


@pytest.mark.parametrize('width', [1, 2, 7, 160])
@pytest.mark.parametrize('raw', [
    '수집하여야 합니다 [4]. 최소한으로 수집해야 합니다 [3].\n목적을 명확히 합니다 [1].',
    '답변 [1][2] [3]. 다음 문장 [4, 5–7]',
    '원문은 "항목 [1]"입니다 [3]. [별표 1] 및 `값 [1]` 참조 [2].',
    '링크 [1](https://example.invalid) 및 링크 [2][원문]입니다 [3].',
    '**답변** [1]. "원문 [2]" [3] 및 `값 [4]` [5].',
])
def test_stream_never_exposes_pending_citations_and_matches_completion(workflow, monkeypatch, width, raw):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio-final')
    async def run():
        display = workflow._ChatProgress({'socketIOClientId': 'fixture'})
        sent = []
        async def emit(event, value, **kwargs):
            sent.append((event, value))
        display.emit = emit
        expected = workflow._for_markdown(workflow._without_inline_reference_numbers(raw).strip())
        for seq, start in enumerate(range(0, len(raw), width), 1):
            await display.answer_delta({'schema_version': 'rag-answer-delta-v1', 'seq': seq,
                                        'text': raw[start:start+width]})
            # Each displayed fragment must already belong to the final answer;
            # no temporary bracket or citation digit can be appended and erased.
            visible = ''.join(value for event, value in sent if event == 'token')
            assert expected.startswith(visible)
        await display.finish(expected + '\n\n**출처**\n\n- 개인정보 보호법 · 제3조')
        visible = ''.join(value for event, value in sent if event == 'token')
        assert visible == expected + '\n\n**출처**\n\n- 개인정보 보호법 · 제3조'
        assert '답변 작성 결과' not in visible
        assert sent[-1] == ('end', 'end')
    asyncio.run(run())


@pytest.mark.parametrize('mode', ['socketio', 'socketio-final', 'off'])
def test_workflow_run_returns_clean_text_in_all_display_modes(workflow, monkeypatch, mode):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', mode)
    monkeypatch.setattr(workflow, '_settings', lambda: ('http://fixture/json', 'synthetic', 2))
    sent = []
    async def send(self, event, value):
        if self.enabled:
            sent.append((event, value))
    monkeypatch.setattr(workflow._ChatProgress, '_send', send)
    class Response:
        status = 200
        headers = {'Content-Type': 'text/event-stream'}
        def __init__(self, request_id): self.request_id = request_id
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __iter__(self):
            for seq, part in enumerate(['수집해야 합니다 ', '[', '4', ']', '.'], 1):
                yield ('data: ' + json.dumps({'event': 'answer_delta', 'data': {
                    'schema_version': 'rag-answer-delta-v1', 'request_id': self.request_id,
                    'seq': seq, 'text': part}}) + '\n\n').encode()
            yield ('data: ' + json.dumps({'event': 'result', 'data': {'status': 200,
                'body': {'answer': {'text': '수집해야 합니다 [4].'}}}}) + '\n\n').encode()
    monkeypatch.setattr(workflow.urllib.request, 'urlopen',
                        lambda request, **kwargs: Response(json.loads(request.data)['request_id']))
    result = asyncio.run(workflow.run({'question': '합성 질문', 'socketIOClientId': 'fixture'}))
    assert result['text'] == '수집해야 합니다.' and result['answer_status'] == 'answered'
    assert result['answer_display_revision'] == workflow.ANSWER_DISPLAY_REVISION
    if mode == 'off':
        assert not sent
    else:
        assert ''.join(value for event, value in sent if event == 'token') == result['text']
