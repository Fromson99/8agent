"""Actual v6 journals to the existing GENOS Reasoner format; synthetic models only."""
import asyncio
import json

from semantic_runtime import observability as obs
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
from semantic_runtime.progress import ProgressCapture, capture
from test_unified_legal_agent import unified, ok, command
from test_structure_first_search import structured_generation
from test_genos_reasoner_display import load as workflow, rationale


def judgments(events, state="COMPLETED"):
    return [e for e in events if e.get("basis", {}).get("kind") == "CASE_JUDGMENT_ACCEPTED"
            and e["basis"]["state"] == state]


def run_captured(runtime, send, *args, **kwargs):
    events = []
    obs.configure()
    with obs.context(request_id="v6-progress"), capture("v6-progress", runtime, events.append):
        response = send(*args, **kwargs)
    return response, events


def test_seven_native_checkpoints_reach_cumulative_reasoner(unified, monkeypatch):
    _, send, transport, _, runtime = unified
    events, live = [], []
    obs.configure()
    with obs.context(request_id="v6-progress"), capture("v6-progress", runtime, events.append) as projection:
        def before_return(phase, view):
            projection.poll_journal()
            live.append((phase, list(events)))
        transport.before_return = before_return
        result = ok(send())
    completed = judgments(events)
    assert [e["basis"]["stage"] for e in completed] == result["executed"]
    assert result["executed"] == ["INTENT", "PLAN", "RECALL", "READ", "SELECT", "ASSESS", "COMPOSE"]
    assert all(e["run_id"] == result["run_id"] for e in completed)
    compose_wait = next(snapshot for phase, snapshot in live if phase == "memory-compose")
    assert any(e["kind"] == "model_wait" and "답변을 작성 중" in e["label"] for e in compose_wait)
    assert not any(e["basis"]["stage"] == "COMPOSE" for e in judgments(compose_wait))
    selected = next(e for e in completed if e["basis"]["stage"] == "SELECT")
    assert selected["kind"] == "selected" and "모의승인규정" in " ".join(selected["details"])
    serialized = json.dumps(events, ensure_ascii=False)
    assert result["answer"]["text"] not in serialized
    assert "source_store_sha256" not in serialized and "current_facts" not in serialized

    monkeypatch.setenv("GENOS_RAG_PROGRESS_UI", "socketio")
    display = workflow()._ChatProgress({"socketIOClientId": "fixture-room"})
    sent = []
    async def emit(name, value, room):
        assert room == "fixture-room"
        sent.append((name, value))
    display.emit = emit
    async def render():
        for event in events:
            await display.progress(event)
        await display.finish(result["answer"]["text"])
    asyncio.run(render())
    arrays = [value for name, value in sent if name == "agentFlowExecutedData"]
    assert arrays and all(isinstance(value, list) for value in arrays)
    assert arrays[-1][:len(arrays[0])] == arrays[0]
    text = "\n".join(rationale(block) for block in arrays[-1])
    for event in completed:
        assert event["label"] in text
    assert all(block["status"] == "FINISHED" and block["nodeLabel"] == "Visible Reasoner"
               and isinstance(block["data"]["output"]["content"], str) for block in arrays[-1])
    assert "".join(value for name, value in sent if name == "token") == result["answer"]["text"]
    assert sent[-1] == ("end", "end")


def test_fact_correction_reports_only_executed_checkpoints(unified):
    _, send, _, _, runtime = unified
    first = ok(send())
    response, events = run_captured(runtime, send,
        command("FACT_UPDATE", target=first["question_id"], facts=[{"name": "대상", "value": "A"}]))
    result = ok(response)
    assert result["executed"] == ["ASSESS", "COMPOSE"]
    assert [e["basis"]["stage"] for e in judgments(events)] == result["executed"]
    assert any("현재 사실과 원문의 조건·단서를 검토 중" in e["label"] for e in events)


def test_confirmed_experience_rebinding_is_not_new_research(unified):
    _, send, _, _, runtime = unified
    first = ok(send())
    stored, events = run_captured(runtime, send, command("EXPERIENCE_CONFIRM", target=first["question_id"]))
    experience = ok(stored)["experience_id"]
    assert not judgments(events)
    assert any(e["label"] == "사용자가 최종 확인한 경험을 저장함" for e in events)
    response, events = run_captured(runtime, send,
        command("EXPERIENCE_REUSE", document_scope_mode="AUTHORIZED", knowledge_id=experience,
                task="모의승인규정 제1조의 승인 대상은?", queries=["승인"], facts=[]), session_id="other")
    result = ok(response)
    assert result["executed"] == ["COMPOSE"]
    assert [e["basis"]["stage"] for e in judgments(events)] == ["COMPOSE"]
    rebound = judgments(events, "REBOUND")
    assert [e["basis"]["stage"] for e in rebound] == ["INTENT", "PLAN", "RECALL", "READ", "SELECT", "ASSESS"]
    assert all("재결속함" in e["label"] for e in rebound)


def test_additional_source_reentry_and_failure_never_invent_completion(unified):
    _, send, transport, _, runtime = unified
    transport.fulltext_once = True
    response, events = run_captured(runtime, send)
    result = ok(response)
    assert [e["basis"]["stage"] for e in judgments(events)] == result["executed"]
    assert result["executed"].count("RECALL") == 2
    assert any(e.get("basis", {}).get("kind") == "MEMORY_FULLTEXT_REENTRY" for e in events)
    transport.fail = "memory-assess"
    response, events = run_captured(runtime, send, session_id="failed")
    assert response.status_code >= 400
    assert not any(e["basis"]["stage"] in ("ASSESS", "COMPOSE") for e in judgments(events))


def test_invalid_domain_choice_has_no_accepted_checkpoint(unified):
    _, send, transport, _, runtime = unified
    transport.bad_domain = True
    response, events = run_captured(runtime, send)
    assert response.status_code == 502
    assert not judgments(events)


def test_wait_can_reappear_after_actual_research_reentry(monkeypatch):
    monkeypatch.setenv("GENOS_RAG_PROGRESS_UI", "socketio")
    display = workflow()._ChatProgress({"socketIOClientId": "fixture-room"})
    sent = []
    async def emit(name, value, room): sent.append(value)
    display.emit = emit
    async def render():
        for kind, label in [("model_wait", "근거를 선별 중"), ("model_wait", "근거를 선별 중"),
                            ("revised", "추가 원문을 검색함"), ("model_wait", "근거를 선별 중")]:
            await display.progress({"schema_version": "rag-progress-v1", "kind": kind, "label": label})
    asyncio.run(render())
    assert len(sent) == 3 and [rationale(b) for b in sent[-1]].count("[근거를 선별 중]\n근거를 선별 중") == 2


def test_case_selection_uses_bound_evidence_and_checks_native_payload_hash(tmp_path):
    from test_genos_chat_flow import evidence, read
    run_id = "b" * 32
    context = RequestContext.create({"id": "q", "question": "모의 질문"}, {"question": "모의 질문"},
                                    {"scope": {"document_version_ids": ["allowed", "other-team"]}}, 60, run_id)
    path = tmp_path / "legal-agent/runs/day" / run_id / "journal.sqlite"
    repo = UnifiedRepository(path, context,
        {"max_model_attempts": 10, "finalization_reserve": 2, "max_tool_actions": 10})
    events = []
    projection = ProgressCapture("fixture", tmp_path, events.append)
    projection.run_id = run_id
    try:
        repo.event("CASE_EXECUTION_CONTEXT", {"documents": ["allowed"]})
        allowed, other = evidence(), evidence("other-team", "2")
        read(repo, allowed); read(repo, other)
        payload = {"final_ids": [allowed["source_id"], other["source_id"]],
                   "label_to_source": {"C001": allowed["source_id"], "C002": other["source_id"]},
                   "decisions": [{"decision": {"choices": [
                       {"id": "C001", "reason": "승인 조건 확인"},
                       {"id": "C002", "reason": "다른 팀의 비공개 조건"}]}}],
                   "raw": "DO NOT SEND MODEL OUTPUT"}
        with repo.transaction():
            seq = repo.event("CASE_JUDGMENT_ACCEPTED", {"stage": "SELECT", "payload_hash": digest(payload), "origin": None})
            repo.put("case_stage", "case:SELECT", payload, seq)
        projection.poll_journal(); projection._flush_reads(force=True)
        selected = judgments(events)[0]
        assert selected["count"] == 1
        text = json.dumps(events, ensure_ascii=False)
        assert "모의규정" in text and "승인 조건 확인" in text
        assert "다른 팀" not in text and "DO NOT SEND" not in text
        count = len(events)
        projection.poll_journal()
        assert len(events) == count
        with repo.transaction():
            seq = repo.event("CASE_JUDGMENT_ACCEPTED", {"stage": "COMPOSE", "payload_hash": "0" * 64})
            repo.put("case_stage", "case:COMPOSE", {"text": "DO NOT SEND ANSWER"}, seq)
        projection.poll_journal()
        assert len(events) == count
    finally:
        repo.close()
