"""위키 적중 원장 — 아티클이 실전(질의)에서 어떻게 쓰였는지의 관측.

규칙의 적중 원장(rules hits)과 같은 자리를 위키에 준다: 답 합성에 아티클이
끼면 "주입"이 남고, 그 질의에 사용자 피드백(정답/오답)이 오면 "부검"이
붙는다. 이 둘을 접으면 아티클 단위 실적 — "이 아티클이 끼면 답이 맞는가" —
이 되고, 생애 보고서(wikilife.py)의 하중·부검 축이 된다.

append-only jsonl 이다 — 관측을 고쳐 쓰지 않는다 (tuples·logbook 과 같은
규율). 파일: data/wiki/ledger.jsonl (WIKI_STORE 로 이동 가능).

    {"kind": "주입", "ts": …, "qid": …, "q": …, "slugs": […], "answerable": bool}
    {"kind": "부검", "ts": …, "qid": …, "verdict": "정답"|"오답", "note": …}

부검은 qid 가 원장에 있을 때만 남는다 — 위키가 끼지 않은 질의의 피드백은
위키 실적이 아니다.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from lawrag.platform.paths import data_path


def ledger_path() -> Path:
    from lawrag.core.rag.content_snapshot import current_content_snapshot

    if current_content_snapshot() is not None:
        # The semantic wiki tree is immutable release input.  Runtime usage
        # observations belong beside the other external feedback ledgers.
        root = Path(os.environ.get("RAG_LOG_DIR") or data_path("rag"))
        return root / "wiki_ledger.jsonl"
    return Path(os.environ.get("WIKI_STORE") or data_path("wiki")) \
        / "ledger.jsonl"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _append(rec: dict) -> None:
    if os.environ.get("LAWRAG_FEEDBACK_DISABLED", "").strip().casefold() in {
        "1", "true", "yes", "on",
    }:
        return
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _rows() -> list[dict]:
    if os.environ.get("LAWRAG_FEEDBACK_DISABLED", "").strip().casefold() in {
        "1", "true", "yes", "on",
    }:
        return []
    p = ledger_path()
    if not p.is_file():
        return []
    out = []
    for line in p.read_text("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:      # 깨진 줄은 건너뛴다 — 원장은 계속 산다
            continue
    return out


def record(qid: str, question: str, slugs: list[str], answerable: bool) -> None:
    """주입 기록 — 답 합성에 아티클이 낀 질의."""
    if not qid or not slugs:
        return
    _append({"kind": "주입", "ts": _now(), "qid": qid,
             "q": question[:200], "slugs": slugs, "answerable": bool(answerable)})


def feedback(qid: str, verdict: str, note: str = "") -> bool:
    """부검 기록 — 그 질의에 위키가 끼었을 때만 남는다. 남겼으면 True."""
    if not qid or verdict not in ("정답", "오답"):
        return False
    if not any(r.get("kind") == "주입" and r.get("qid") == qid for r in _rows()):
        return False
    _append({"kind": "부검", "ts": _now(), "qid": qid,
             "verdict": verdict, "note": note[:200]})
    return True


def stats() -> dict[str, dict]:
    """아티클별 실적 — {slug: {주입, 정답, 오답, last}}. 부검은 그 질의에
    끼었던 모든 아티클에 같이 접힌다 (개별 기여 분리는 판정이 아니라 추정이다
    — 하지 않는다)."""
    by_qid: dict[str, list[str]] = {}
    out: dict[str, dict] = {}
    for r in _rows():
        if r.get("kind") == "주입":
            slugs = r.get("slugs", [])
            by_qid[r.get("qid", "")] = slugs
            for s in slugs:
                row = out.setdefault(s, {"주입": 0, "정답": 0, "오답": 0, "last": ""})
                row["주입"] += 1
                row["last"] = max(row["last"], r.get("ts", ""))
        elif r.get("kind") == "부검":
            for s in by_qid.get(r.get("qid", ""), []):
                row = out.setdefault(s, {"주입": 0, "정답": 0, "오답": 0, "last": ""})
                row[r["verdict"]] += 1
    return out
