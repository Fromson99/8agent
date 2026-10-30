"""Source fidelity and publication consumers for the two-level source disclosure."""
import asyncio
from copy import deepcopy

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from markdown_it import MarkdownIt
import pytest

from semantic_runtime import chat_adapter


def rendered(text):
    return BeautifulSoup(MarkdownIt('commonmark', {'html': True}).render(text), 'html.parser')


def body():
    return {
        'answer': {'text': '확인한 답변입니다.', 'claims': [{'source_ids': ['used']}]},
        'assembly': {'context': [
            {'id': 'used', 'document_id': 'allowed', 'document_name': 'internal > risk_team > 모의규정',
             'ancestors': [{'title': '제2조'}],
             'text': '① 원문의 첫 문장입니다.\n\n② 3~5일 [별표 1]을 확인한다.\n| 항목 | 기준 |'},
            {'id': 'unused', 'document_name': '미채택 문서', 'text': '표시하면 안 되는 원문'},
        ]},
    }


def test_source_text_survives_markdown_exactly_and_does_not_mutate_response():
    w = chat_adapter.views(); original = body()
    # No length cap, including blank lines and characters otherwise rewritten by Markdown.
    original['assembly']['context'][0]['text'] += '\n긴 원문 문단.' * 2000
    before = deepcopy(original)
    text = w._for_markdown(w.render(original)); dom = rendered(text)
    assert dom.select_one('[data-source-text]').get_text() == original['assembly']['context'][0]['text']
    assert len(dom.select('details[data-genos-source]')) == 1
    assert not dom.select('details[open]')
    assert dom.select_one('details[data-genos-sources] > div > details[data-genos-source]')
    assert 'risk_team' not in text and '표시하면 안 되는 원문' not in text
    assert original == before
    assert w._for_markdown(text) == text


def test_source_html_and_markdown_are_literal_and_cannot_load_resources():
    w = chat_adapter.views(); original = body()
    attack = '</div></details><script>alert(1)</script><img src="https://invalid.test/pixel">\n![image](https://invalid.test/image) & `code` [1]'
    source = original['assembly']['context'][0]
    source.update(document_name=attack, text=attack, coordinate_label=attack, version=attack)
    dom = rendered(w._for_markdown(w.render(original)))
    assert not dom.select('script, img, iframe, a, style')
    assert len(dom.select('details[data-genos-source]')) == 1
    assert dom.select_one('[data-source-text]').get_text() == attack


def test_same_title_keeps_different_versions_and_spans_but_deduplicates_exact_copy():
    w = chat_adapter.views()
    source = {'tier': 'CORE', 'document_name': '모의규정', 'coordinate_label': '제1조',
              'version': '2025', 'spans': [{'text': '첫 번째 원문'}], 'excerpt': '사용하지 않을 요약'}
    newer = {**source, 'version': '2026'}
    other = {**source, 'spans': [{'text': '별도의 범위'}]}
    dom = rendered(w._for_markdown(w._tier_sources({'sources': [source, newer, other, deepcopy(source)]})))
    assert len(dom.select('[data-genos-source]')) == 3
    assert [x.get_text() for x in dom.select('[data-source-text]')] == ['첫 번째 원문', '첫 번째 원문', '별도의 범위']
    assert '사용하지 않을 요약' not in dom.get_text()


def test_workflow_retains_read_scope_and_unreviewed_status():
    w = chat_adapter.views()
    source = {'selection_id': 'read', 'side': 'internal', 'content_read': True,
              'document_name': '모의규정', 'coordinate_label': '제1조',
              'spans': [{'text': '가목 원문'}, {'text': '바목 원문'}]}
    original = {'answer': {'text': '검토 중입니다.'}, 'assembly': {'term_agent': {'source_bundle': {
        'schema_version': 'workflow-source-v1', 'sources': [source, {**source, 'selection_id': 'unread',
            'content_read': False, 'document_name': '미확보 후보', 'spans': [{'text': '미확보 내용'}]}]}}},
        'unreviewed_sources': [{'evidence_id': 'read'}]}
    dom = rendered(w._for_markdown(w.render(original)))
    assert [x.get_text() for x in dom.select('[data-source-text]')] == ['가목 원문', '바목 원문']
    assert '항목별 해석은 아직 완료되지 않았습니다.' in dom.get_text()
    assert '미확보' not in dom.get_text()


def test_missing_original_stays_missing_and_failures_never_publish_sources():
    w = chat_adapter.views(); original = body()
    del original['assembly']['context'][0]['text']
    dom = rendered(w._for_markdown(w.render(original)))
    assert not dom.select('[data-source-text]')
    assert '원문 내용이 저장되지 않았습니다.' in dom.get_text()
    assert not rendered(w.render({**body(), '_gateway_status': 403})).select('[data-genos-source]')
    assert not rendered(w.render({'answer': {'text': '안녕하세요.'}})).select('[data-genos-sources]')


def test_bound_workflow_display_rejects_previous_renderer_and_preserves_new_source_text():
    w = chat_adapter.views(); original = body()
    result = asyncio.run(w.workflow_display_result(original, [], request_id='req'))
    assert w._bound_workflow_display({**original, 'workflow_display': result}, 'req') == result
    previous = {**result, 'answer_display_revision': 'workflow-unlimited-text-20261021-r1'}
    previous['content_sha256'] = w._workflow_display_digest({k:v for k,v in previous.items() if k != 'content_sha256'})
    assert w._bound_workflow_display({**original, 'workflow_display': previous}, 'req') is None
    assert rendered(result['text']).select_one('[data-source-text]').get_text() == original['assembly']['context'][0]['text']


@pytest.mark.parametrize('stream', [False, True])
def test_native_chat_endpoint_publishes_source_cards_without_another_service_call(monkeypatch, tmp_path, stream):
    import main
    original = body(); calls = []
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path))
    monkeypatch.setenv('GENOS_MEMORY_ENABLED', '0')
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'off')
    monkeypatch.delenv('TEAM_ID', raising=False)
    monkeypatch.delenv('GENOS_CHAT_TRUST_PLATFORM_IDENTITY', raising=False)
    async def service(request):
        calls.append(request)
        from semantic_runtime.legal_agent.answer_stream import current_sink
        sink = current_sink()
        if sink:
            sink(original['answer']['text'])
        return {'status': 200, 'body': original}
    monkeypatch.setattr(chat_adapter, 'call_service', service)
    response = TestClient(main.app).post('/chat', json={'question': '모의 질문', 'stream': stream})
    assert response.status_code == 200 and len(calls) == 1
    if stream:
        import json
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        result = next(event['data'] for event in events if event.get('event') == 'result')
        text = result['text']
        assert ''.join(event['data'] for event in events if event.get('event') == 'token') == text
    else:
        text = response.json()['data']['text']
    dom = rendered(text)
    assert dom.select_one('[data-source-text]').get_text() == original['assembly']['context'][0]['text']
    assert '미채택 문서' not in text
