"""진단 튜플·승격 후보·생애주기 — 루프 2 의 저장 계약을 시험한다.

관측은 append-only, 승격 후보는 세는 장부, 강등(tombstone)은 색인에서 빠진다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import tuples                                # noqa: E402
from lawrag.core.rag.index import Index                           # noqa: E402
from lawrag.core.rag.search import search                         # noqa: E402


def _out(q="설명의무가 뭐야"):
    return {"question": q, "mode": "정확",
            "ladder": [{"stage": "정확", "count": 1}],
            "filter": {"in": 1, "out": 1, "applied": False},
            "answerable": True,
            "refs": [{"doc_id": "d1", "doc": "KSB.pdf", "node": 2,
                      "block": 1, "page": 1, "link": "/structure/?doc=d1"}]}


def test_질의_적재와_피드백_병합(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path))
    qid = tuples.log_ask(_out())
    assert qid and tuples.find(qid)["질의"] == "설명의무가 뭐야"

    tuples.log_feedback(qid, "오답", {"doc_id": "d1", "node": 3}, "이게 아님")
    rec = tuples.read()[0]
    assert rec["qid"] == qid
    assert rec["피드백"]["판정"] == "오답"
    assert rec["피드백"]["기대"]["node"] == 3
    # 실패 원인은 미판정으로 남는다 — 책임 귀속은 별도 국면이다
    assert rec["피드백"]["실패_원인"] is None


def test_피드백은_마지막_것이_남는다(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path))
    qid = tuples.log_ask(_out())
    tuples.log_feedback(qid, "오답", None, "")
    tuples.log_feedback(qid, "정답", None, "다시 보니 맞음")
    assert tuples.read()[0]["피드백"]["판정"] == "정답"


def test_legal_graph_세대와_활성화_원장을_진단튜플에_보존한다(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path))
    out = _out("주요주주인지")
    out["legalclosure"] = {"legal_graph": {
        "enabled": True,
        "status": "expanded",
        "generation_id": "lgv1-test",
        "added_count": 1,
        "reason_counts": {"activated": 1},
        "decisions": [{"assertion_id": "relation:test", "activated": True}],
        "selected": [{"doc_id": "d2", "node": 4}],
    }}
    qid = tuples.log_ask(out)
    stored = tuples.find(qid)["legal_graph"]
    assert stored["generation_id"] == "lgv1-test"
    assert stored["reason_counts"] == {"activated": 1}
    assert stored["selected"] == [{"doc_id": "d2", "node": 4}]


def test_승격후보는_정규형으로_묶여_센다(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path))
    coords = [{"doc_id": "d1", "node": 5, "via": "깔때기"}]
    assert tuples.record_candidates("점검 주기", coords) == 1     # 신규
    assert tuples.record_candidates("점검주기", coords) == 0      # 같은 쌍 — 카운트만
    row = tuples.candidates()[0]
    assert row["count"] == 2
    assert sorted(row["surfaces"]) == ["점검 주기", "점검주기"]


def test_승격후보_상한(tmp_path, monkeypatch):
    """탐험이 넓게 긁어 온 꼬리는 적재하지 않는다 — 상위 cap 개만."""
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path))
    coords = [{"doc_id": "d1", "node": i} for i in range(10)]
    assert tuples.record_candidates("질의", coords, cap=3) == 3
    assert len(tuples.candidates()) == 3


# ---------------------------------------------------------------- 색인 생애주기
def _docs():
    nodes = [{"id": 1, "parent": None, "level": 1, "surface": "제1조",
              "title": "안전장치", "page": 1, "span": [0, 1]}]
    blocks = [{"idx": 0, "page": 1, "text": "안전밸브는 압력을 낮춘다", "kind": "text"}]
    return [("d1", {"name": "A.pdf"}, {"nodes": nodes, "blocks": blocks})]


def test_별칭_표면형도_색인에_오른다():
    terms = [{"term": "안전밸브", "key": "안전밸브", "status": "활성",
              "surfaces": ["안전밸브", "PSV"],
              "occurrences": [{"doc_id": "d1", "doc": "A.pdf", "node": 1,
                               "block": 0, "page": 1}]}]
    idx = Index.from_docs(_docs(), terms)
    r = search(idx, "PSV가 뭐야")
    assert r.mode == "정확"
    top = r.hits[0]
    assert top.kind == "용어" and top.value == "PSV"
    # 표면형이 달라도 병합 단위(target)는 하나다
    assert top.occurrences[0]["node"] == 1


def test_tombstone_은_색인에서_빠진다():
    terms = [{"term": "안전밸브", "key": "안전밸브", "status": "tombstone",
              "surfaces": ["안전밸브", "PSV"],
              "occurrences": [{"doc_id": "d1", "node": 1, "block": 0}]}]
    idx = Index.from_docs(_docs(), terms)
    assert not any(e.kind == "용어" for e in idx.entries)


def test_잠정_용어도_색인에_오르지_않는다():
    """승인(활성)된 keyword 만 검색에 참여한다 (2026-08-10 사용자 결정) —
    잠정은 검수 큐 대기지 검색 자산이 아니다. status 없는 옛 행(수기)은
    활성으로 본다."""
    terms = [
        {"term": "가입", "key": "가입", "status": "잠정",
         "surfaces": ["가입"], "occurrences": [{"doc_id": "d1", "node": 1}]},
        {"term": "안전밸브", "key": "안전밸브",          # status 없음 — 수기 옛 행
         "surfaces": ["안전밸브"], "occurrences": [{"doc_id": "d1", "node": 1}]},
    ]
    idx = Index.from_docs(_docs(), terms)
    words = {e.value for e in idx.entries if e.kind == "용어"}
    assert words == {"안전밸브"}
