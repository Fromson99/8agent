"""Readable progress on synthetic originals; no GENOS field/quality claim."""
import asyncio
import importlib.util
import json
import logging
from pathlib import Path
import sqlite3

import pytest
from conftest import term_glossary
from test_legal_agent_double_harness import generation

from semantic_runtime import observability as obs
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.obligation_repository import ObligationRepository
from semantic_runtime.progress import ProgressCapture, capture

ROOT = Path(__file__).resolve().parents[2]


def workflow():
    spec = importlib.util.spec_from_file_location("chat_flow_test", ROOT / "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def event(kind, label, **kwargs):
    return {"schema_version": "rag-progress-v1", "kind": kind, "label": label, **kwargs}


def test_markdown_paragraphs_document_bullets_and_exact_final_answer(monkeypatch):
    monkeypatch.setenv("GENOS_RAG_PROGRESS_UI", "socketio-inline")
    display = workflow()._ChatProgress({"socketIOClientId": "synthetic"})
    sent = []
    async def emit(name, value, room):
        sent.append((name, value))
    display.emit = emit
    answer = "최종 답변.\n\n원문 출처"
    async def run():
        await display.progress(event("reading", "열람할 문서·조문", details=["모의규정 · 제1조", "모의규정 · 제2조"]))
        await display.progress(event("selected", "근거 선택 결과", details=["모의규정 · 제1조 · 핵심 근거 채택 · 이유: 승인 요건 확인"]))
        await display.finish(answer)
    asyncio.run(run())
    text = "".join(value for name, value in sent if name == "token")
    assert "**1. 열람**" in text and "\n\n- 모의규정 · 열람 시작 2개 범위\n- 제2조\n\n" in text
    assert "**2. 근거 선택**" in text and "이유: 승인 요건 확인" in text
    assert text.split("**최종 답변**\n\n", 1)[1] == answer
    assert sent[-1] == ("end", "end")


def test_transport_diagnostics_and_repeated_waits_do_not_spam(monkeypatch):
    monkeypatch.setenv("GENOS_RAG_PROGRESS_UI", "socketio-inline")
    display = workflow()._ChatProgress({"socketIOClientId": "synthetic"})
    sent = []
    async def emit(name, value, room): sent.append((name, value))
    display.emit = emit
    async def run():
        for _ in range(3):
            for kind, label in [("model_wait", "답변 초안을 작성 중"), ("phase", "내부 모델 응답을 받음"),
                                ("phase", "모델 결과 형식을 검증함")]:
                await display.progress(event(kind, label))
        await display.progress(event("heartbeat", "요청 처리 중", elapsed_ms=32000))
        await display.progress(event("heartbeat", "요청 처리 중", elapsed_ms=33000))
    asyncio.run(run())
    tokens = [value for name, value in sent if name == "token"]
    assert len(tokens) == 2
    assert "32초" in tokens[1] and "답변 초안을 작성 중" in tokens[1]
    assert not any("형식" in value or "응답을 받음" in value for value in tokens)


def test_document_labels_cannot_inject_markdown_html_or_extra_lines(monkeypatch):
    monkeypatch.setenv("GENOS_RAG_PROGRESS_UI", "socketio-inline")
    display = workflow()._ChatProgress({"socketIOClientId": "synthetic"})
    sent = []
    async def emit(name, value, room): sent.append((name, value))
    display.emit = emit
    asyncio.run(display.progress(event("selected", "근거 선택 결과", details=[
        "<script>\n[문서](https://example.invalid) **채택**", 3, "x" * 301])))
    token = next(value for name, value in sent if name == "token")
    assert "<script>" not in token and "\\[문서\\]" in token and "\\*\\*채택\\*\\*" in token
    assert "\n[문서]" not in token and "x" * 301 not in token


@pytest.fixture
def journal(tmp_path):
    run_id = "a" * 32
    binding = {"scope": {"document_version_ids": ["allowed"]}}
    context = RequestContext.create({"id": "q1", "question": "모의 질문"}, {"question": "모의 질문"}, binding, 60, run_id)
    path = tmp_path / "legal-agent/runs/day" / run_id / "journal.sqlite"
    repo = ObligationRepository(path, context, {"max_model_attempts": 10, "finalization_reserve": 2, "max_tool_actions": 10})
    events = []
    projection = ProgressCapture("r1", tmp_path, events.append)
    projection.run_id = run_id
    yield repo, projection, events
    repo.close()


def evidence(did="allowed", suffix="1"):
    return {"evidence_id": "e" + suffix, "source_id": "s" + suffix, "document_id": did, "unit_id": "u1",
            "generation_id": "synthetic", "source_artifact_hash": "0" * 64, "text_hash": "0" * 64,
            "role": "reference", "temporal_status": "unknown",
            "metadata": {"document_name": "모의규정" if did == "allowed" else "다른 팀 문서", "heading": "제1조"}, "spans": []}


def read(repo, item, complete=True):
    return repo.record_observation({"tool": "read", "args": {"target": item["evidence_id"]}},
        {"status": "OK" if complete else "PARTIAL", "coverage": {"complete": complete},
         "next_cursor": None, "items": [{"text": "DO NOT SEND ORIGINAL TEXT"}]}, [item], verify=lambda _: None)


def select(repo, item, status="SELECTED"):
    with repo.transaction():
        seq = repo.event("SOURCE_SELECTION", {})
        repo.put("source_selection", "ss" + item["evidence_id"], {"evidence_id": item["evidence_id"],
                 "tier": "CORE", "status": status, "relevance_reason": "승인 조건 확인", "binding_hash": repo.context.binding_hash},
                 seq, evidence_ids=[item["evidence_id"]])


@pytest.mark.parametrize('mode,label', [('SEARCH', '법률 검색'), ('BROWSE', '자료 현황 조회'),
                                      ('DIRECT', '인사·역할 안내'), ('OUT_OF_DOMAIN', '서비스 범위 밖')])
def test_committed_request_route_reaches_workflow_chat(journal, monkeypatch, mode, label):
    repo, projection, events = journal
    with repo.transaction():
        seq = repo.event('REQUEST_ROUTED', {'mode': mode, 'reason': '요청의 목적을 확인했습니다.\n짧은 사유',
                                           'answer': 'DO NOT SEND FULL ANSWER', 'prompt': 'DO NOT SEND PROMPT'})
    projection.poll_journal()
    route = next(e for e in events if e.get('basis', {}).get('kind') == 'REQUEST_ROUTED')
    assert route['kind'] == 'decision' and route['label'] == '요청 판단: ' + label
    assert route['basis']['journal_seq'] == seq
    assert '\n' not in route['details'][0]
    assert 'DO NOT SEND' not in json.dumps(route)
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio-inline')
    display = workflow()._ChatProgress({'socketIOClientId': 'synthetic'})
    sent = []
    async def emit(name, value, room): sent.append((name, value))
    display.emit = emit
    asyncio.run(display.progress(route))
    text = ''.join(value for name, value in sent if name == 'token')
    assert label in text and '이유: 요청의 목적을 확인했습니다.' in text


def test_only_admitted_document_titles_and_committed_selection_reason_leave_journal(journal):
    repo, projection, events = journal
    allowed, denied = evidence(), evidence("other-team", "2")
    read(repo, allowed); read(repo, denied)
    select(repo, allowed); select(repo, denied)
    with repo.transaction():
        repo.event("QUESTION_PLAN", {"plan": {"demands": [{"requirement": "승인 요건을 확인하라", "missing_fact": None}]}})
        repo.event("REVIEW_V3", {"checks": [{"verdict": "SUPPORTED", "evidence": [allowed["evidence_id"]], "reason": "원문 조건 일치"}]})
    projection.poll_journal(); projection._flush_reads(force=True)
    rendered = json.dumps(events, ensure_ascii=False)
    assert "모의규정" in rendered and "제1조" in rendered and "승인 조건 확인" in rendered
    assert "핵심 근거 채택" in rendered and "승인 요건을 확인하라" in rendered and "원문 부합" in rendered
    assert "다른 팀 문서" not in rendered and "DO NOT SEND ORIGINAL TEXT" not in rendered
    assert all(e["basis"].get("journal_seq") for e in events)
    count = len(events); projection.poll_journal(); projection._flush_reads(force=True)
    assert len(events) == count


def test_partial_read_never_claims_complete_and_completion_is_separate(journal):
    repo, projection, events = journal
    item = evidence()
    read(repo, item, complete=False)
    projection.poll_journal(); projection._flush_reads(force=True)
    text = json.dumps(events, ensure_ascii=False)
    assert "일부 열람" in text and "열람 완료" not in text
    read(repo, item, complete=True)
    projection.poll_journal(); projection._flush_reads(force=True)
    assert "열람 완료" in json.dumps(events, ensure_ascii=False)


@pytest.mark.parametrize("status,outcome", [("REJECTED", "근거 제외"), ("PENDING", "판단 보류")])
def test_committed_exclusion_and_deferral_keep_actual_reason(journal, status, outcome):
    repo, projection, events = journal
    item = evidence(); read(repo, item)
    with repo.transaction():
        seq = repo.event("SOURCE_SELECTION", {})
        repo.put("source_selection", "ss1", {"evidence_id": item['evidence_id'], "status": status,
                 "reason": "질문 대상과 직접 연결되지 않음", "binding_hash": repo.context.binding_hash}, seq,
                 evidence_ids=[item['evidence_id']])
    projection.poll_journal(); projection._flush_reads(force=True)
    text = json.dumps(events, ensure_ascii=False)
    assert outcome in text and "질문 대상과 직접 연결되지 않음" in text


def test_replaced_selection_names_previously_chosen_source(journal):
    repo, projection, events = journal
    item = evidence(); read(repo, item); select(repo, item)
    with repo.transaction():
        repo.event("SOURCE_SELECTION_EXCLUDED", {"selection_id": "sse1", "version": 1, "reason": "MODEL_REPLACED"})
    projection.poll_journal(); projection._flush_reads(force=True)
    changed = next(e for e in events if e['kind'] == 'revised')
    assert "모의규정" in changed['details'][0] and "이전 선택 철회" in changed['details'][0]


def test_reading_start_uses_scope_and_coalesces_repeated_pages(journal):
    repo, projection, events = journal
    projection.poll_journal()
    for did in ("other-team", "allowed", "allowed", "allowed"):
        record = logging.LogRecord("genos.source_reader", logging.INFO, __file__, 1, "source.read.started", (), None)
        record.fields = {"request_id": "r1", "run_id": repo.context.run_id, "document_id": did,
                         "document_name": "モック" if did == "other-team" else "모의규정", "heading": "제1조"}
        projection.handle(record)
    projection._flush_reads(force=True)
    assert len(events) == 1 and events[0]["kind"] == "reading"
    assert "모의규정" in events[0]["details"][0] and "モック" not in json.dumps(events)


def test_mismatched_run_or_binding_cannot_disclose_titles(tmp_path):
    path = tmp_path / "legal-agent/runs/day" / ("b" * 32) / "journal.sqlite"
    path.parent.mkdir(parents=True)
    binding = {"scope": {"document_version_ids": ["allowed"]}}
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE run(singleton INTEGER,run_id TEXT,binding_json TEXT,binding_hash TEXT); CREATE TABLE event(seq INTEGER,kind TEXT);")
        db.execute("INSERT INTO run VALUES(1,?,?,?)", ("b" * 32, json.dumps(binding), "0" * 64))
    events = []; projection = ProgressCapture("r1", tmp_path, events.append); projection.run_id = "b" * 32
    projection.poll_journal()
    assert projection.admitted is None
    with sqlite3.connect(path) as db:
        db.execute("UPDATE run SET binding_hash=?,run_id=?", (digest(binding), "c" * 32))
    projection.poll_journal()
    assert projection.admitted is None and events == []


def test_real_source_recall_records_document_sections_and_selected_reasons(tmp_path, generation):
    # Exercise the actual source reader + committed v5 repository on synthetic
    # fixture originals, including the many-page path that formerly spammed.
    from test_bounded_source_main import Transport, settings, app_for
    app = app_for(tmp_path, generation, Transport(), {**settings(), 'max_read_chars': 2})
    pipeline = app.state.pipeline
    events = []
    runtime = tmp_path / "runtime"
    obs.configure()
    try:
        request = {"question": "모의승인규정의 승인 대상과 예외는?", "document_ids": ["d"], "use_llm": True}
        with obs.context(request_id="scope-test"), capture("scope-test", runtime, events.append) as projection:
            with pipeline.term_agent.open_session(request, query=pipeline.plan(request['question'], ['d']), runtime=runtime) as session:
                session.investigate()
                assert not session.limitations
                projection.poll_journal()
                projection._flush_reads(force=True)
                assert session.work.db.execute("SELECT COUNT(*) FROM observation WHERE tool='read'").fetchone()[0] > 20
        text = json.dumps(events, ensure_ascii=False)
        assert "모의승인규정" in text and "승인 원칙 확인" in text and "승인 예외 복구" in text
        assert "질문에서 확인할 사항" in text and "승인 대상을 분류하라" in text
        selected = [e for e in events if e['label'] == '근거 선택 결과']
        assert len(selected) == 1 and selected[0]['count'] == 2
        # Aggregate notifications still stay bounded; requested input/output and
        # per-location activity are explicit rows rather than hidden summaries.
        assert len([e for e in events if e.get('details') and
                    e.get('basis', {}).get('detail_mode') != 'activity']) < 15
        assert any(e.get('basis', {}).get('kind') == 'SOURCE_FULLTEXT_RESULTS' for e in events)
        assert any(e.get('basis', {}).get('kind') == 'ATTEMPT_SENT' for e in events)
        assert "모델 결과 형식을 검증함" not in text and "messages" not in text
    finally:
        pipeline.store.close()
