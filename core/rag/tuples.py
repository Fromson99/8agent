"""진단 튜플 — 질의마다 남기는 관측 기록 (ontology_kg §5.2 의 최소 구현).

지금까지 /ask 는 사다리·탐험 경로·필터 결과를 응답 JSON 에 실어 보내고
**버렸다.** 루프 2(질의 구동 진화)는 그 기록이 연료다 — 루프는 나중에
만들어도 데이터는 첫날부터 쌓여야 한다.

## 왜 append-only jsonl 인가

튜플은 관측이다. 관측을 고쳐 쓰기 시작하면 "그때 시스템이 뭘 봤나"가
사라진다. 질의 기록과 피드백 기록을 **따로 append** 하고, 읽을 때 qid 로
합친다 — links.json 처럼 파일이 정본이고 DB 는 없다.

## 승격 후보는 세는 장부다

탐험이 성공하면 (질의 정규형 → 착지 좌표) 쌍을 적재만 한다. 승격은
동형 착지가 쌓인 뒤 게이트(Phase 3)가 한다 — 표본 1 즉시 승격은
과잉일반화다(§5.5). 같은 쌍이 다시 오면 개수를 올려야 하므로 이 파일만은
읽고-고쳐-쓴다(candidates.json).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.rag.index import norm, store_path


def rag_dir() -> Path:
    """진단 기록의 자리 — glossary.json·links.json 과 같은 규약(스토어 옆)."""
    return Path(os.environ.get("RAG_LOG_DIR", store_path().parent / "rag"))


def tuples_dir() -> Path:
    return rag_dir() / "tuples"


def candidates_path() -> Path:
    return rag_dir() / "candidates.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _month_file(ts: Optional[str] = None) -> Path:
    ym = (ts or _now())[:7].replace("-", "")
    return tuples_dir() / f"{ym}.jsonl"


def _append(rec: dict) -> None:
    p = _month_file(rec.get("ts"))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- 질의 기록
def log_ask(out: dict, prompt: Optional[dict] = None,
            calls: Optional[list] = None) -> str:
    """/ask 응답에서 진단 튜플을 뽑아 적재한다. 응답에 실을 qid 를 돌려준다.

    "어떻게 찾았는가"(사다리·탐험 경로·좌표)에 더해 **무엇이 나갔는가**(답
    전문·회수 구역 목록)도 남긴다 — 최근 질의를 눌러 그때의 전모(질문·답·
    회수 경위)를 다시 보는 것이 검수의 입구다(2026-08-11 사용자 결정.
    LLM 답은 재실행해도 같은 문장이 아니라서 "재현 가능"이 성립하지 않았다).

    prompt 는 답 합성 호출에 실제로 들어간 {"system","user"} — 지식이 어떻게
    주입됐는지를 그대로 남긴다(재구성은 문서가 다시 서면 어긋난다). 컨텍스트
    상한(12구역×6k자) 덕에 커야 수십 KB 다.
    """
    qid = uuid.uuid4().hex[:12]
    rec = {
        "kind": "질의", "qid": qid, "ts": _now(),
        "질의": out.get("question", ""),
        "mode": out.get("mode"),
        "ladder": out.get("ladder"),
        "filter": out.get("filter"),
        "answerable": out.get("answerable"),
        "답": out.get("answer") or "",
        # 회수 구역 — 어느 단(벡터·용어·참조·탐색)이 무엇을 데려왔는지 그대로.
        "context": out.get("context") or [],
        # 모델이 실제 인용한 컨텍스트 번호(벡터 모드) — 회수≠인용을 가른다.
        "cited": out.get("cited") or [],
        "refs": [{k: r.get(k) for k in
                  ("n", "doc_id", "doc", "node", "block", "page", "path",
                   "kind", "matched") if k in r}
                 for r in out.get("refs", [])],
    }
    if prompt:
        rec["프롬프트"] = {"system": prompt.get("system", ""),
                           "user": prompt.get("user", "")}
    # 쟁점기의 전모(트리거 적중·판정·질의 확장)와 **모든 LLM 콜의 원문**.
    # 답 합성 프롬프트만으로는 "판정이 무엇을 보고 섰나"가 안 보인다 —
    # 검수는 결론이 아니라 그 앞의 입력을 봐야 성립한다.
    if out.get("쟁점"):
        rec["쟁점"] = out["쟁점"]
    if calls:
        rec["콜"] = calls
    if out.get("timing") is not None:
        rec["timing"] = out["timing"]
    if out.get("recovery") is not None:
        rec["recovery"] = out["recovery"]
    if out.get("ask_user"):
        rec["ask_user"] = out["ask_user"]
    if out.get("usage"):
        rec["usage"] = out["usage"]
    _append(rec)
    return qid


def log_feedback(qid: str, verdict: str, expected: Optional[dict] = None,
                 note: str = "") -> dict:
    """사용자 신호 — "A 를 물었는데 B 가 나왔다. A 가 나와야 한다."

    실패_원인(a~d)은 여기서 판정하지 않는다(§5.1 책임 귀속은 Phase 2).
    미판정으로 남겨야 나중에 귀속기가 "아직 안 본 것"을 찾을 수 있다.
    """
    rec = {"kind": "피드백", "qid": qid, "ts": _now(), "판정": verdict,
           "기대": expected, "메모": note, "실패_원인": None}
    _append(rec)
    return rec


def read(limit: int = 200) -> list[dict]:
    """질의 기록에 피드백을 합쳐 최신순으로. 화면(튜플 브라우저)용.

    피드백이 여럿이면 마지막 것이 남는다 — 사람이 판단을 고친 것이다.
    """
    d = tuples_dir()
    if not d.exists():
        return []
    asks: dict[str, dict] = {}
    order: list[str] = []
    for p in sorted(d.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            qid = rec.get("qid")
            if rec.get("kind") == "질의":
                asks[qid] = rec
                order.append(qid)
            elif rec.get("kind") == "피드백" and qid in asks:
                asks[qid]["피드백"] = {k: rec.get(k)
                                       for k in ("판정", "기대", "메모", "실패_원인", "ts")}
    rows = [asks[q] for q in reversed(order) if q in asks]
    return rows[:limit]


def find(qid: str) -> Optional[dict]:
    for rec in read(limit=10_000):
        if rec.get("qid") == qid:
            return rec
    return None


# ---------------------------------------------------------------- 승격 후보
def record_candidates(query: str, coords: list[dict], cap: int = 3) -> int:
    """탐험 성공을 승격 후보로 적재 — (질의 정규형, 착지 좌표)별로 센다.

    상위 cap 개 좌표만 적는다. 탐험이 넓게 긁어 온 꼬리까지 다 적으면
    장부가 노이즈로 비대해진다 — 첫 몇 좌표가 실제로 답변에 실린 것들이다.
    """
    qkey = norm(query)
    if not qkey or not coords:
        return 0
    path = candidates_path()
    rows: list[dict] = []
    if path.exists():
        try:
            rows = json.loads(path.read_text(encoding="utf-8")).get("candidates", [])
        except Exception:
            rows = []
    by_key = {(r.get("qkey"), r.get("doc_id"), r.get("node")): r for r in rows}
    now = _now()
    fresh = 0
    for c in coords[:cap]:
        doc_id, node = c.get("doc_id"), c.get("node")
        if not doc_id or node is None:
            continue
        k = (qkey, doc_id, node)
        row = by_key.get(k)
        if row is None:
            row = {"qkey": qkey, "surfaces": [query], "doc_id": doc_id,
                   "node": node, "via": c.get("via", ""),
                   "count": 0, "first": now, "last": now}
            by_key[k] = row
            rows.append(row)
            fresh += 1
        if query not in row["surfaces"]:
            row["surfaces"].append(query)
        row["count"] += 1
        row["last"] = now
        row["via"] = c.get("via", row.get("via", ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"candidates": rows}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return fresh


def candidates() -> list[dict]:
    p = candidates_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("candidates", [])
    except Exception:
        return []
