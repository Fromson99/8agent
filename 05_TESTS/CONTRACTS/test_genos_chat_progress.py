"""The progress channel preserves the verified answer and excludes journal text."""
import asyncio
import importlib.util
import json
import logging
from pathlib import Path
import sqlite3
import sys
import types
import urllib.error

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stream_emits_progress_before_exact_service_result(monkeypatch):
    app_module = _load("genos_stream_app_test", ROOT / "08_DEPLOYMENT/GENOS/stream_app.py")
    from semantic_runtime import observability as obs

    expected = {"status": 200, "body": {"answer": {"text": "verified"}}}

    async def fake_service(config, data):
        if "request_id" in data:
            with obs.context(request_id=data["request_id"]):
                obs.event(obs.get_logger("service"), "request.started", question="private question")
        await asyncio.sleep(0.02)
        return expected

    monkeypatch.setattr(app_module, "service", fake_service)

    async def request():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://local") as client:
            response = await client.post("/stream", json={"API_TYPE": "LEGAL_AGENT", "question": "secret"})
            frames = [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]
            assert [frame["event"] for frame in frames] == ["progress", "result"]
            assert frames[0]["data"]["label"] == "요청을 접수함"
            assert "secret" not in response.text and "private question" not in response.text
            assert frames[-1]["data"] == expected
            json_response = await client.post("/json", json={"API_TYPE": "LEGAL_AGENT"})
            assert json_response.json() == expected

    asyncio.run(request())


def test_workflow_streams_blocks_and_returns_final_dict(monkeypatch):
    workflow = _load("genos_rag_chat_progress_test", ROOT / "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py")
    monkeypatch.setattr(workflow, '_post_code_serving', lambda body: {})
    monkeypatch.setenv("GENOS_RAG_PROGRESS_UI", "socketio-inline")
    monkeypatch.setenv("GENOS_BASE_URL", "http://genos.local")
    monkeypatch.setenv("GENOS_CODESERVING_ID", "497")
    monkeypatch.setenv("GENOS_CODESERVING_TOKEN", "test-token")
    sent = []

    async def emit(name, value, room):
        sent.append((name, value, room))

    monkeypatch.setitem(sys.modules, "main_socketio", types.SimpleNamespace(sio_server=types.SimpleNamespace(emit=emit)))
    request_id = "request-1"
    body = {"status": 200, "body": {"answer": {"text": "검증된 답"}}}
    class Response:
        status = 200
        headers = {"Content-Type": "text/event-stream"}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def __init__(self, frames):
            self.frames = frames
        def __iter__(self):
            return iter(("data: " + json.dumps(frame, ensure_ascii=False) + "\n").encode() for frame in self.frames)

    def urlopen(request, timeout):
        assert request.full_url.endswith("/stream")
        assert timeout == 2100
        actual_id = json.loads(request.data)["request_id"]
        return Response([
            {"event": "progress", "data": {"schema_version": "rag-progress-v1", "request_id": actual_id,
                "kind": "candidate", "label": "검색 후보를 확인함", "count": 2}},
            {"event": "result", "data": body},
        ])

    monkeypatch.setattr(workflow.urllib.request, "urlopen", urlopen)
    result = asyncio.run(workflow._run_once({"question": "질문", "request_id": request_id,
                                               "socketIOClientId": "socket-1"}))
    assert result["text"] == "검증된 답"
    assert result["agentFlowExecutedData"][0]["nodeLabel"] == "Visible Reasoner"
    assert json.loads(result["agentFlowExecutedData"][0]["data"]["output"]["content"])["visible_rationale"] == "[검색 후보를 확인함]\n검색 후보를 확인함 · 2건"
    assert [item[0] for item in sent] == ["token", "agentFlowExecutedData", "token", "end"]
    assert all(item[2] == "socket-1" for item in sent)


def test_live_status_reaches_chat_tokens_and_heartbeat_keeps_actual_stage(monkeypatch):
    workflow = _load('chat_live_status', ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio-inline')
    display = workflow._ChatProgress({'socketIOClientId': 'fixture'})
    sent = []
    async def emit(name, value, room):
        sent.append((name, value))
    display.emit = emit
    async def check():
        for kind, label, elapsed in (
            ('phase', '관련 자료를 검색 중', 1000),
            ('model_wait', '답변 초안을 작성 중 · 내부 모델 대기', 2000),
            ('heartbeat', '요청 처리 중 · 경과 32초', 32000),
        ):
            await display.progress({'schema_version': 'rag-progress-v1', 'kind': kind,
                                    'label': label, 'elapsed_ms': elapsed})
    asyncio.run(check())
    tokens = [value for name, value in sent if name == 'token']
    assert len(tokens) == 3
    assert '관련 자료를 검색 중' in tokens[0]
    assert '답변 초안을 작성 중 · 내부 모델 대기' in tokens[1]
    assert '답변 초안을 작성 중 · 내부 모델 대기' in tokens[2] and '32초' in tokens[2]
    assert all('답변 근거를 확인 중입니다.' not in token for token in tokens)


def test_live_status_continues_when_reasoner_blocks_are_full(monkeypatch):
    workflow = _load('chat_status_after_block_limit', ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio-inline')
    display = workflow._ChatProgress({'socketIOClientId': 'fixture'})
    display.blocks = [{} for _ in range(80)]
    sent = []
    async def emit(name, value, room):
        sent.append((name, value))
    display.emit = emit
    asyncio.run(display.progress({'schema_version': 'rag-progress-v1', 'kind': 'model_wait',
                                 'label': '내부 모델 응답을 기다리는 중', 'elapsed_ms': 900000}))
    assert any(name == 'token' and '내부 모델 응답' in value for name, value in sent)
    assert len(display.blocks) == 80


def test_live_status_deduplicates_repeated_stage_and_preserves_final_answer(monkeypatch):
    workflow = _load('chat_status_dedup', ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio-inline')
    display = workflow._ChatProgress({'socketIOClientId': 'fixture'})
    sent = []
    async def emit(name, value, room):
        sent.append((name, value))
    display.emit = emit
    async def check():
        event = {'schema_version': 'rag-progress-v1', 'kind': 'reading',
                 'label': '후보 원문을 열람 중', 'count': 2, 'elapsed_ms': 2000}
        await display.progress(event)
        await display.progress({**event, 'elapsed_ms': 3000})
        await display.finish('검증된 최종 답변')
    asyncio.run(check())
    tokens = [value for name, value in sent if name == 'token']
    assert sum('후보 원문을 열람 중' in value for value in tokens) == 1
    assert '검증된 최종 답변' in ''.join(tokens)
    assert sent[-1] == ('end', 'end')


def test_default_chat_stream_sends_only_final_text(monkeypatch):
    workflow = _load("genos_rag_chat_final_only_test", ROOT / "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py")
    monkeypatch.delenv("GENOS_RAG_PROGRESS_UI", raising=False)
    display = workflow._ChatProgress({"socketIOClientId": "socket-1"})
    sent = []
    async def emit(name, value, room):
        sent.append((name, value))
    display.emit = emit
    async def check():
        await display.progress({"schema_version": "rag-progress-v1", "kind": "phase", "label": "검색 중"})
        await display.finish("최종 답변.\n\n출처 경로")
    asyncio.run(check())
    assert sent == [("token", "최종 답변.\n\n출처 경로"), ("end", "end")]


def test_committed_journal_projection_separates_read_selection_and_revision(tmp_path):
    from semantic_runtime.progress import ProgressCapture

    run_id = "a" * 32
    journal = tmp_path / "legal-agent" / "runs" / "day" / run_id / "journal.sqlite"
    journal.parent.mkdir(parents=True)
    with sqlite3.connect(journal) as db:
        db.executescript("""
            CREATE TABLE event(seq INTEGER,kind TEXT);
            CREATE TABLE observation(observation_id TEXT,tool TEXT,status TEXT,created_seq INTEGER);
            CREATE TABLE observation_evidence(observation_id TEXT,evidence_id TEXT);
            CREATE TABLE entity_head(kind TEXT,entity_id TEXT,version INTEGER,validity TEXT);
            CREATE TABLE entity_version(kind TEXT,entity_id TEXT,version INTEGER,payload_json TEXT);
        """)
        db.executemany("INSERT INTO event VALUES(?,?)", [(1, "OBSERVATION"),
            (2, "SOURCE_SELECTION"), (3, "SOURCE_SELECTION_EXCLUDED"), (4, "REVIEW_V2")])
        db.execute("INSERT INTO observation VALUES('o1','read','OK',1)")
        db.execute("INSERT INTO observation_evidence VALUES('o1','e1')")
        db.execute("INSERT INTO entity_head VALUES('source_selection','s1',1,'CURRENT')")
        db.execute("INSERT INTO entity_version VALUES('source_selection','s1',1,?)",
                   ('{"status":"SELECTED","document_name":"private title"}',))
    events = []
    capture = ProgressCapture("request-1", tmp_path, events.append)
    capture.run_id = run_id
    capture.poll_journal()
    assert [event["kind"] for event in events] == ["read_complete", "selected", "revised", "review"]
    assert events[1]["count"] == 1
    assert "private title" not in json.dumps(events)


def test_stream_404_falls_back_once_but_broken_stream_does_not_rerun(monkeypatch):
    workflow = _load("genos_rag_chat_fallback_test", ROOT / "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py")
    monkeypatch.setenv("GENOS_RAG_PROGRESS_UI", "socketio-inline")
    monkeypatch.setenv("GENOS_BASE_URL", "http://genos.local")
    monkeypatch.setenv("GENOS_CODESERVING_ID", "497")
    monkeypatch.setenv("GENOS_CODESERVING_TOKEN", "test-token")
    calls = []
    monkeypatch.setattr(workflow, "call_code_serving", lambda question, data: calls.append(1) or {"answer": {"text": "ok"}})

    def missing(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, None)

    monkeypatch.setattr(workflow.urllib.request, "urlopen", missing)
    display = workflow._ChatProgress({"socketIOClientId": "socket-1"})
    result = asyncio.run(workflow._stream_code_serving("q", {"request_id": "r1"}, display))
    assert result["answer"]["text"] == "ok"
    assert calls == [1]
    assert display.enabled

    class Broken:
        headers = {"Content-Type": "text/event-stream"}
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def __iter__(self): return iter(())

    monkeypatch.setattr(workflow.urllib.request, "urlopen", lambda request, timeout: Broken())
    with pytest.raises(ConnectionError, match="without result"):
        asyncio.run(workflow._stream_code_serving("q", {"request_id": "r2"}, display))
    assert calls == [1]


def test_progress_handler_never_mixes_request_ids(tmp_path):
    from semantic_runtime.progress import ProgressCapture

    events = []
    capture = ProgressCapture("our-request", tmp_path, events.append)
    for request_id in ("other-request", "our-request"):
        record = logging.LogRecord("genos.service", logging.INFO, __file__, 1,
                                   "request.started", (), None)
        record.fields = {"request_id": request_id, "question": "private"}
        capture.handle(record)
    assert len(events) == 1
    assert events[0]["request_id"] == "our-request"
    assert "private" not in json.dumps(events)
