"""분산된 사람 승인을 공통 receipt와 진화 후보로 겹쳐 읽는 계약."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import approvals, promote, tuples, verdicts  # noqa: E402


def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path / "rag"))
    monkeypatch.setenv("RAG_RULES_DIR", str(tmp_path / "rules"))
    verdicts._rules_cache.clear()
    promote._qvec_cache.clear()


def _fix(src: int, dst: int, new_dst: int) -> dict:
    return {
        "src_doc": "d1", "src": src, "src_path": f"제{src}조",
        "surface": f"제{dst}조제{new_dst}항",
        "dst_doc": "d1", "dst": dst, "dst_path": f"제{dst}조",
        "new_dst": new_dst, "new_dst_path": f"제{dst}조제{new_dst}항",
    }


def test_최신_판정만_세어_반복_클릭이_증거를_부풀리지_않는다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    subject = {"doc_id": "d1", "node": 3}
    approvals.record(kind="question_memory", decision="활성",
                     effect="memory_activate", failure="질문기억_누락",
                     subject=subject)
    approvals.record(kind="question_memory", decision="활성",
                     effect="memory_activate", failure="질문기억_누락",
                     subject=subject)

    assert len(approvals.read()) == 2
    assert len(approvals.current()) == 1
    summary = approvals.evolution_summary(min_evidence=2)
    assert summary["current_subjects"] == 1
    assert summary["candidates"][0]["evidence"] == 1
    assert summary["candidates"][0]["status"] == "관측중"


def test_승인된_교정은_receipt와_진화후보를_동시에_만든다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    first, second = _fix(1, 2, 3), _fix(4, 5, 6)
    verdicts.log_fixes("q1", "첫 질문", [first])
    verdicts.log_fixes("q2", "둘째 질문", [second])
    verdicts.resolve_fix(first, "승인", "항까지 내려가야 한다")
    verdicts.resolve_fix(second, "승인", "같은 실패")

    rows = approvals.read()
    assert [row["effect"] for row in rows] == ["redirect", "redirect"]
    assert rows[0]["qids"] == ["q1"] and rows[1]["qids"] == ["q2"]
    summary = approvals.evolution_summary(min_evidence=2)
    candidate = summary["candidates"][0]
    assert candidate["failure"] == "얕은_착지"
    assert candidate["evidence"] == 2 and candidate["status"] == "탐색후보"
    assert "operator:reference.landing_resolution" in candidate["mutation_targets"]
    assert "control:context.repair_children_max" in candidate["mutation_targets"]


def test_질문기억과_답변피드백도_같은_원장에_합류한다(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    tuples.record_candidates("벌칙이 뭐야", [{"doc_id": "d1", "node": 3}])
    assert promote.approve(tuples.norm("벌칙이 뭐야"), "d1", 3, "맞는 착지")
    tuples.log_feedback("q-bad", "오답", {"doc_id": "d1", "node": 3}, "누락")

    rows = approvals.read()
    assert {(row["kind"], row["effect"]) for row in rows} == {
        ("question_memory", "memory_activate"),
        ("answer_feedback", "answer_overturn"),
    }
    summary = approvals.evolution_summary(min_evidence=1)
    assert {row["failure"] for row in summary["candidates"]} == {
        "질문기억_누락", "답변_오류"}


def test_receipt와_진화후보_API는_읽기만_한다(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from lawrag.api.routers import rag as rag_router

    _iso(tmp_path, monkeypatch)
    approvals.record(kind="landing_fix", decision="승인", effect="redirect",
                     failure="얕은_착지", subject=_fix(1, 2, 3))
    app = FastAPI()
    app.include_router(rag_router.router)
    client = TestClient(app)

    ledger = client.get("/v1/rag/approvals?current_only=true").json()
    assert ledger["count"] == 1 and ledger["rows"][0]["kind"] == "landing_fix"
    evolution = client.get("/v1/rag/approvals/evolution?min_evidence=1").json()
    assert evolution["candidates"][0]["status"] == "탐색후보"
    assert len(approvals.read()) == 1                 # 조회가 원장을 쓰지 않는다
