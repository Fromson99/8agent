"""Photo regression: readable paths and one card per consecutive read group."""
import os
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(os.getenv('SOURCE_PROVIDER_PROJECT_ROOT', str(ROOT)))
HANDOFF = PROJECT / '08_DEPLOYMENT/GENOS/handoffs/workflow_source_provider_20261013_r2'
PASTE = HANDOFF / 'GENOS_WORKFLOW_SOURCE_PROVIDER_20261013_R2_PASTE_ALL.txt'


@pytest.fixture(params=['working', 'editor'])
def view(request, monkeypatch):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio')
    # The standalone editor installs its existing diagnostics module on import.
    # Restore the caller's module after each independently compiled delivery.
    monkeypatch.setitem(sys.modules, 'genos_diagnostics', types.ModuleType('genos_diagnostics'))
    sys.modules['genos_diagnostics'].install = lambda *a: None
    path = PASTE if request.param == 'editor' else ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
    module = types.ModuleType('source_cards_' + request.param)
    module.__file__ = str(path)
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), module.__dict__)
    return module


def event(kind, basis, rows=(), **extra):
    labels = {'candidate': '자료 검색 · 관련 법령을 찾았습니다',
              'reading': '원문 확인 · 법령 본문을 읽기 시작합니다',
              'decision': '근거 선택 · 원문을 검토했습니다'}
    return {'schema_version': 'rag-progress-v1', 'request_id': 'mock-request',
        'run_id': 'mock-run', 'kind': kind, 'label': labels.get(kind, '현재 단계'),
        'details': list(rows), 'basis': {'kind': basis, 'detail_mode': 'activity'}, **extra}


def content(block):
    return json.loads(block['data']['output']['content'])['visible_rationale']


def recorder(view):
    display = view._ChatProgress({'socketIOClientId': 'test-room'})
    sent = []
    async def emit(name, value, room=None):
        sent.append((name, json.loads(json.dumps(value))))
    display.emit = emit
    return display, sent


def test_paths_are_separate_markdown_items_and_title_appears_once(view):
    d, sent = recorder(view)
    rows = ['external > financial_team > law > 모의법',
            'external > financial_team > krx > 모의 시행세칙']
    e = event('candidate', 'LAW_FULLTEXT_DIRECTORY', rows)
    async def run():
        await d.progress(e)
        await d._flush_source_reads()
    asyncio.run(run())
    text = content(d.blocks[0])
    assert text.count(e['label']) == 1
    assert '외부법률 / 법제처\n\n1. 모의법' in text
    assert '외부법률 / 한국거래소\n\n1. 모의 시행세칙' in text
    assert 'external' not in text and 'financial' not in text
    assert len(sent) == 1 and sent[0][0] == 'agentFlowExecutedData'
    assert any(row.get('details') == rows for row in d.flow_events)
    html = MarkdownIt().render(text)
    assert html.count('<li>') == 2
    assert html.count('<ol>') == 2


def test_many_reads_emit_once_before_next_stage_without_losing_paths(view):
    d, sent = recorder(view)
    rows = [f'external > financial_team > law > 모의법{i} · 제{i}조' for i in range(1, 22)]
    async def run():
        for row in rows:
            await d.progress(event('reading', 'UNIT_READ_STARTED', [row]))
        await d.progress(event('reading', 'UNIT_READ_STARTED', [rows[0]]))
        await d.progress(event('heartbeat', 'HEARTBEAT'))
        assert sent == []  # no per-document card/update that GENOS could append
        await d.progress(event('decision', 'LAW_SELECTION_DECISION', ['선택 이유']))
        await d.finish('최종 답변')
    asyncio.run(run())
    read_cards = [b for b in d.blocks if '확인 대상' in content(b)]
    assert len(read_cards) == 1
    text = content(read_cards[0])
    assert '21곳' in text and MarkdownIt().render(text).count('<li>') == 21
    assert all(view._ChatProgress._plain(row.rsplit(" > ", 1)[-1]) in text for row in rows)
    # First emitted snapshot contains the entire read batch, never a partial one.
    assert len(sent[0][1]) == 1 and content(sent[0][1][0]) == text
    assert ''.join(v for k, v in sent if k == 'token') == '최종 답변'
    assert sent[-1] == ('end', 'end')
    assert any(row.get('details') == [rows[-1]] for row in d.flow_events)


@pytest.mark.parametrize('boundary', ['model_wait', 'candidate', 'decision', 'run'])
def test_new_activity_or_run_starts_a_separate_read_group(view, boundary):
    d, sent = recorder(view)
    async def run():
        await d.progress(event('reading', 'UNIT_READ_STARTED', ['모의법 · 제1조']))
        if boundary != 'run':
            await d.progress(event(boundary, 'ATTEMPT_SENT' if boundary == 'model_wait' else 'LAW_FULLTEXT_DIRECTORY', ['중간 단계']))
        await d.progress(event('reading', 'UNIT_READ_STARTED', ['모의법 · 제2조'],
                               run_id='next-run' if boundary == 'run' else 'mock-run'))
        await d.finish('완료')
    asyncio.run(run())
    reads = [content(b) for b in d.blocks if '확인 대상' in content(b)]
    assert len(reads) == 2 and '제1조' in reads[0] and '제2조' in reads[1]


@pytest.mark.parametrize('mode,sid', [('socketio', ''), ('final-cards', 'room'), ('off', 'room')])
def test_pending_reads_reach_final_list_without_a_socket(view, monkeypatch, mode, sid):
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', mode)
    d = view._ChatProgress({'socketIOClientId': sid})
    async def run():
        await d.progress(event('reading', 'UNIT_READ_STARTED', ['모의법 · 제3조']))
        await d.finish('완료')
    asyncio.run(run())
    assert bool(d.blocks) == (mode != 'off')


def test_reads_flush_before_first_answer_delta_and_ignore_late_progress(view):
    d, sent = recorder(view)
    async def run():
        await d.progress(event('reading', 'UNIT_READ_STARTED', ['모의법 · 제4조']))
        await d.answer_delta({'schema_version': 'rag-answer-delta-v1', 'seq': 1, 'text': '답변'})
        await d.progress(event('reading', 'UNIT_READ_STARTED', ['늦은 원문']))
        await d.finish('답변')
    asyncio.run(run())
    assert [k for k, _ in sent] == ['agentFlowExecutedData', 'token', 'end']
    assert len(d.blocks) == 1 and '늦은 원문' not in content(d.blocks[0])


def test_source_labels_cannot_inject_markdown_or_html(view):
    d, _ = recorder(view)
    row = '<script>x</script> [원문](https://invalid.example) **별표**'
    async def run():
        await d.progress(event('candidate', 'LAW_FULLTEXT_DIRECTORY', [row]))
        await d._flush_source_reads()
    asyncio.run(run())
    text = content(d.blocks[0])
    assert '<script>' not in text and '\\[원문\\]' in text and '\\*\\*별표\\*\\*' in text


def test_editor_build_is_reproducible_and_shared_methods_are_identical():
    path = PROJECT / '06_TOOLS/OFFLINE/genos_source_provider_handoff.py'
    spec = importlib.util.spec_from_file_location('source_cards_build', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = json.loads((HANDOFF / 'CODE_MANIFEST.json').read_text(encoding='utf-8'))
    # Reproduce the sealed R2 from its recorded source. Later public-failure
    # policies may evolve while the shared source-card methods stay identical.
    source = PROJECT / manifest['shared_source_path']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest['shared_source_sha256']
    text, methods = module.build(source)
    assert text == PASTE.read_text(encoding='utf-8')
    current = (ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_text(encoding='utf-8')
    assert module.extract(current, module.METHODS, '_ChatProgress') == methods
    assert manifest['editor_sha256'] == hashlib.sha256(PASTE.read_bytes()).hexdigest()
    assert hashlib.sha256(module.BASE.read_bytes()).hexdigest() == module.BASE_SHA


def test_workflow_sse_groups_reads_and_preserves_answer_and_final_card_list(view, monkeypatch):
    sent = []
    async def emit(name, value, room=None):
        sent.append((name, json.loads(json.dumps(value))))
    monkeypatch.setitem(sys.modules, 'main_socketio', types.SimpleNamespace(
        sio_server=types.SimpleNamespace(emit=emit)))
    monkeypatch.setattr(view, '_post_code_serving', lambda data: {'status': 200, 'body': {}})
    monkeypatch.setattr(view, '_settings', lambda: ('http://mock-server/json', 'mock-token', 2100))
    class Response:
        status = 200
        headers = {'Content-Type': 'text/event-stream'}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def __iter__(self):
            def frame(kind, data):
                return ('data: ' + json.dumps({'event': kind, 'data': data}, ensure_ascii=False) + '\n\n').encode()
            yield frame('progress', event('candidate', 'LAW_FULLTEXT_DIRECTORY', ['모의법A', '모의법B']))
            for i in range(12):
                yield frame('progress', event('reading', 'UNIT_READ_STARTED', [f'모의법{i} · 제1조']))
            yield frame('answer_delta', {'schema_version': 'rag-answer-delta-v1', 'request_id': 'mock-request', 'seq': 1, 'text': '최종 답변입니다.'})
            yield frame('result', {'status': 200, 'body': {'answer': {'text': '최종 답변입니다.'}}})
    monkeypatch.setattr(view.urllib.request, 'urlopen', lambda request, timeout: Response())
    result = asyncio.run(view.run({'question': '모의 질문', 'request_id': 'mock-request', 'socketIOClientId': 'room'}))
    assert result['text'] == '최종 답변입니다.'
    assert ''.join(v for k, v in sent if k == 'token') == result['text']
    snapshots = [v for k, v in sent if k == 'agentFlowExecutedData']
    assert result['agentFlowExecutedData'] == snapshots[-1]
    read_cards = [b for b in snapshots[-1] if '확인 대상' in content(b)]
    assert len(read_cards) == 1 and content(read_cards[0]).count('\n\n- ') == 12
    assert len([s for s in snapshots if any('확인 대상' in content(b) for b in s)]) == 1
    assert result['code_serving_transport']['answer_events'] == 1


@pytest.mark.parametrize('key', ['LAW_DECISION_REJECTED', 'MODEL_OUTPUT_INVALID', 'COMPLETION_ASSESSMENT_REJECTED', 'OBS_EVENT'])
def test_private_errors_do_not_flush_groups_or_reach_public_flow(view, key):
    d, sent = recorder(view)
    raw = event('decision', key, ['PRIVATE_TRACEBACK duplicate branch or missing reason'], label='실행 오류')
    raw['basis']['detail_mode'] = 'full_error'
    async def run():
        await d.progress(event('reading', 'UNIT_READ_STARTED', ['external/krx/규정A']))
        await d.progress(raw)
        assert not sent and not d.blocks
        await d.progress(event('reading', 'UNIT_READ_STARTED', ['external/krx/규정B']))
        await d.finish('완료')
    asyncio.run(run())
    assert 'PRIVATE_TRACEBACK' not in json.dumps([sent,d.blocks,d.flow_events])
    assert len(d.blocks) == 1 and '2곳' in content(d.blocks[0])
    assert raw['details'][0].startswith('PRIVATE_TRACEBACK')  # diagnostic input retained
    assert '조회 번호: r-1' in view.render_error({'request_id':'r-1','traceback':raw['details'][0]})


def test_candidate_chunks_and_request_boundaries(view):
    d, _ = recorder(view)
    async def run():
        for i in range(19):
            e = event('candidate', 'LAW_FULLTEXT_DIRECTORY', [f'external > financial_team > krx > 규정{i}'])
            e['basis']['journal_seq'] = 3
            await d.progress(e)
        e = event('candidate', 'LAW_FULLTEXT_DIRECTORY', ['external/kofia/협회규정'])
        e['basis']['journal_seq'] = 4
        await d.progress(e)
        await d.finish('완료')
    asyncio.run(run())
    assert len(d.blocks) == 2
    assert content(d.blocks[0]).count('외부법률 / 한국거래소') == 1
    assert MarkdownIt().render(content(d.blocks[0])).count('<li>') == 19
    assert '19. 규정18' in content(d.blocks[0])
    assert '외부법률 / 한국금융투자협회' in content(d.blocks[1])


def test_unknown_provider_internal_and_duplicate_titles_are_not_mislabelled(view):
    d,_=recorder(view)
    rows=['external/team/unknown/규정A','internal/team/사규B',
          'external/law/동일명','external/krx/동일명','external/kofia/<img src=x> **위험**']
    text=d._card_rationale('검색',rows)
    assert '외부법률 / 기타 출처' in text and '내부 규정' in text
    assert text.count('1. 동일명') == 2
    assert all(x not in text for x in ['external','internal','unknown','<img'])
    html=MarkdownIt().render(text)
    assert '<img' not in html and '<strong>' not in html


def test_committed_judgment_survives_privacy_filter(view):
    d,_=recorder(view)
    e=event('decision','CASE_JUDGMENT_ACCEPTED',['현재 판단: 확인한 원문에 근거한 판단'])
    e['basis'].update(detail_mode='judgment',state='COMPLETED')
    asyncio.run(d.progress(e))
    assert d.blocks and any('확인한 원문' in str(x) for x in d.flow_events)


@pytest.mark.parametrize('code,label', [('fsc','금융위원회'),('expc','법제처 (법령해석례)'),('prec','판례'),('moleg','법제처')])
def test_registered_additional_source_labels(view, code, label):
    text=view._ChatProgress({})._card_rationale('검색',[f'external > team > {code} > 자료명'])
    assert '외부법률 / '+label in text and '1. 자료명' in text
    assert code not in text


def test_nested_annex_keeps_parent_law_and_internal_category(view):
    text=view._ChatProgress({})._card_rationale('검색',[
        'external > risk_team > law > 전자금융감독규정 > 별표서식 > [별지 1] 삭제',
        'internal > financial_team > forms > 상장주선인의 기업실사점검표(2024.12.31)'])
    assert '전자금융감독규정 / 별표서식 / ' in text
    assert '내부 규정' in text and '1. 상장주선인의' in text
    assert 'forms' not in text and 'team' not in text
