import json
import sqlite3
import asyncio

from semantic_runtime import observability as obs
from semantic_runtime.request_report import capture_events, write_report, live_log, safe_live_log


def test_one_request_file_contains_prompt_reply_tool_and_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("GENOS_LLM_KEY", "private-test-key")
    run_id = "a" * 32
    runtime = tmp_path / "runtime"
    journal = runtime / "legal-agent" / "runs" / "20260923" / run_id / "journal.sqlite"
    journal.parent.mkdir(parents=True)
    with sqlite3.connect(journal) as db:
        db.executescript("""
            CREATE TABLE event(seq INTEGER,kind TEXT,payload_json TEXT);
            CREATE TABLE model_attempt(created_seq INTEGER,request_json TEXT,response_json TEXT,status TEXT);
            CREATE TABLE observation(created_seq INTEGER,request_json TEXT,result_json TEXT);
            CREATE TABLE entity_version(created_seq INTEGER,kind TEXT,payload_json TEXT);
            INSERT INTO event VALUES(1,'MODEL_SENT','{"decision":"search"}');
            INSERT INTO model_attempt VALUES(1,
              '{"messages":[{"role":"system","content":"system prompt"},{"role":"user","content":"question"}],"api_key":"private-test-key"}',
              '{"body_json":{"choices":[{"message":{"content":"model reply"}}]}}','SUCCEEDED');
            INSERT INTO observation VALUES(1,'{"tool":"SEARCH"}','{"hits":["source A"]}');
            INSERT INTO entity_version VALUES(1,'assessment','{"decision":"insufficient"}');
        """)
    logger = obs.get_logger("report-test")
    with capture_events("req-1") as events, obs.context(request_id="req-1"):
        obs.event(logger, "agent.step", phase="review", question="must not appear in event")
    result = {"status": 200, "body": {"run_id": run_id, "answer": {"text": "final answer"}}}
    path = write_report(tmp_path / "shared", runtime, request_id="req-1", api_type="LEGAL_AGENT",
                        request={"question": "original question"}, result=result, events=events)
    files = list((tmp_path / "shared").rglob("*.json"))
    assert files == [path]
    report = json.loads(path.read_text())
    assert report["request"]["question"] == "original question"
    assert report["journal"]["status"] == "FOUND"
    entry = report["journal"]["timeline"][0]
    assert entry["event"]["payload"]["decision"] == "search"
    records = {item["table"]: item["record"] for item in entry["created_records"]}
    attempt = records["model_attempt"]
    assert attempt["request"]["messages"][0]["content"] == "system prompt"
    assert attempt["response"]["body_json"]["choices"][0]["message"]["content"] == "model reply"
    assert records["observation"]["result"]["hits"] == ["source A"]
    assert records["entity_version"]["payload"]["decision"] == "insufficient"
    assert "private-test-key" not in path.read_text()
    assert "question" not in report["service_events"][0]


def test_missing_journal_still_writes_one_failure_report(tmp_path):
    result = {"status": 503, "body": {"error": "runtime unavailable"}}
    path = write_report(tmp_path / "shared", tmp_path / "runtime", request_id="req-2",
                        api_type="LEGAL_AGENT", request={"question": "test"}, result=result, events=[])
    report = json.loads(path.read_text())
    assert report["journal"]["status"] == "NO_RUN_ID"
    assert report["result"]["status"] == 503


def test_concurrent_request_captures_do_not_mix_events():
    logger = obs.get_logger("request-isolation-test")
    with capture_events("req-a") as first, capture_events("req-b") as second:
        with obs.context(request_id="req-a"):
            obs.event(logger, "first.step")
        with obs.context(request_id="req-b"):
            obs.event(logger, "second.step")
    assert [item["event"] for item in first] == ["first.step"]
    assert [item["event"] for item in second] == ["second.step"]


def test_live_log_is_visible_before_request_finishes_and_excludes_content(tmp_path):
    logger = obs.get_logger("live-request-test")
    with live_log(tmp_path, "req-a") as (path, handler):
        with obs.context(request_id="req-a"):
            obs.event(logger, "model.attempt.started", phase="investigate", attempt_id="M1",
                      question="private question", detail="private source", request_bytes=123,
                      work_ms=123.5, thread_cpu_ms=8.5, start_log_ms=20.0,
                      diagnostic_revision='latency-20260928-r1')
        with obs.context(request_id="req-b"):
            obs.event(logger, "model.attempt.failed", phase="review", attempt_id="M2")
        assert handler.writer.drain(2)
        text = path.read_text(encoding="utf-8")
        assert "model.attempt.started" in text
        assert "phase=investigate" in text
        assert "work_ms=123.5" in text and "thread_cpu_ms=8.5" in text
        assert "start_log_ms=20.0" in text
        assert "diagnostic_revision=latency-20260928-r1" in text
        assert "private question" not in text
        assert "private source" not in text
        assert "req-b" not in text
        handler.last_at -= 10
        handler.last_heartbeat -= 10
        handler.heartbeat()
        assert "request.heartbeat" in path.read_text(encoding="utf-8")
        assert not handler.failed
    assert path.stat().st_mode & 0o777 == 0o640


def test_live_log_open_failure_does_not_raise(tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x")
    with safe_live_log(blocker, "req-a") as (path, handler, error):
        assert path is None and handler is None
        assert error == "NotADirectoryError"


def test_live_log_writes_exception_traceback_immediately(tmp_path):
    logger=obs.get_logger('report-failure-test')
    with live_log(tmp_path,'req-failure') as (path,handler):
        with obs.context(request_id='req-failure'):
            try:
                raise sqlite3.OperationalError('interrupted')
            except sqlite3.OperationalError:
                obs.event(logger,'tool.execution.failed',level=40,exc_info=True,step='fulltext_tool.rank')
        assert handler.writer.drain(2)
        text=path.read_text(encoding='utf-8')
        assert 'tool.execution.failed' in text
        assert 'sqlite3.OperationalError: interrupted' in text


def test_live_journal_shows_decision_tool_and_model_reply_without_ids(tmp_path):
    run_id = "a" * 32
    runtime = tmp_path / "runtime"
    journal = runtime / "legal-agent" / "runs" / "20260923" / run_id / "journal.sqlite"
    journal.parent.mkdir(parents=True)
    with sqlite3.connect(journal) as db:
        db.executescript("""
            CREATE TABLE event(seq INTEGER,kind TEXT,payload_json TEXT,created_at TEXT);
            CREATE TABLE model_view(view_id TEXT,phase TEXT);
            CREATE TABLE model_attempt(attempt_id TEXT,view_id TEXT,attempt_no INTEGER,
                created_seq INTEGER,request_json TEXT,response_json TEXT,status TEXT);
            CREATE TABLE observation(created_seq INTEGER,tool TEXT,request_json TEXT,
                result_json TEXT,status TEXT);
            INSERT INTO model_view VALUES('Vopaque','investigate');
            INSERT INTO event VALUES(1,'WORKFLOW_TURN',
                '{"decision":{"intent":"search","run_id":"hidden-run","actions":[{"tool":"SEARCH","args":{"query":"안녕"}}]}}',
                '2026-09-23T00:00:01+00:00');
            INSERT INTO event VALUES(2,'ATTEMPT_RESERVED','{"attempt_id":"Mopaque"}',
                '2026-09-23T00:00:02+00:00');
            INSERT INTO model_attempt VALUES('Mopaque','Vopaque',1,2,'{}',
                '{"body_json":{"choices":[{"message":{"content":"{\\"intent\\":\\"greet\\",\\"reason\\":\\"인사에 답합니다\\",\\"source_id\\":\\"hidden-source\\"}"}}]}}',
                'SUCCEEDED');
            INSERT INTO event VALUES(3,'ATTEMPT_FINISHED','{"attempt_id":"Mopaque"}',
                '2026-09-23T00:00:03+00:00');
            INSERT INTO event VALUES(4,'OBSERVATION','{"observation_id":"Oopaque"}',
                '2026-09-23T00:00:04+00:00');
            INSERT INTO observation VALUES(4,'SEARCH',
                '{"tool":"SEARCH","args":{"query":"건축법","document_id":"hidden-document"}}',
                '{"status":"OK","count":2,"source_id":"hidden-source"}','OK');
        """)
    with live_log(tmp_path / "shared", "req-test", runtime) as (path, handler):
        handler.run_id = run_id
        handler.poll_journal()
        output = path.read_text(encoding="utf-8")
        assert "AGENT DECISION" in output
        assert "MODEL CALL" in output
        assert "MODEL RESPONSE / LLM ANSWER" in output
        assert "인사에 답합니다" in output
        assert "TOOL RESULT" in output and "건축법" in output
        assert "hidden-run" not in output
        assert "MODEL RAW RESPONSE" in output
        assert '"source_id":"hidden-source"' in output
        assert "hidden-document" not in output
        assert '"attempt_id": "Mopaque"' in output
        assert '"view_id": "Vopaque"' in output


def test_service_writes_request_log_while_preserving_gateway_result(tmp_path, monkeypatch):
    import service

    monkeypatch.setenv("GENOS_SHARED_LOG_DIR", str(tmp_path / "nfs"))
    result = asyncio.run(service.service({}, {"API_TYPE": "PING", "request_id": "req-live"}))
    from semantic_runtime.request_report import _FINALIZER_QUEUE
    _FINALIZER_QUEUE.join()
    assert result["ok"] is True
    files = list((tmp_path / "nfs").rglob("req-live-*.log"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "request.started" in content
    assert "request.returning" in content
    assert "shared_report.written" in content


def test_service_keeps_response_when_nfs_log_directory_is_unwritable(tmp_path, monkeypatch):
    import service

    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x")
    monkeypatch.setenv("GENOS_SHARED_LOG_DIR", str(blocker))
    result = asyncio.run(service.service({}, {"API_TYPE": "PING", "request_id": "req-nfs-failed"}))
    from semantic_runtime.request_report import _FINALIZER_QUEUE
    _FINALIZER_QUEUE.join()
    assert result["ok"] is True
