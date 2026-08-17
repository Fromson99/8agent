"""골든 v2 태깅 — 사람이 화면에서 정답 조문을 직접 짚는다.

    GET  /v1/golden/cases              후보 목록 (태깅 진행률 포함)
    GET  /v1/golden/case/{no}          한 건 — 질의요지·회답·이유 + 저장된 태그
    GET  /v1/golden/laws               창고 법령 목록
    GET  /v1/golden/law?name=&jo=      조를 항·호까지 펴서 — 마디마다 id
    POST /v1/golden/tag/{no}           태그 저장 (결정/전제 마디 + 구어 질문 + 방향)

## 왜 이 화면이 필요한가

지금 자(尺)는 회답 본문에서 「법령」제N조 를 정규식으로 긁는다. 원문 마킹
38건에서 그 자의 결함이 드러났다(docs/RETRIEVAL.md 1장) — **결정 근거와 전제
인용을 못 가르고**, 조(條) 단위라 제9조 아래 20개 마디 중 아무거나 맞혀도
만점이며, 부칙과 본칙을 구별하지 못한다.

정규식으로는 못 가른다. 사람이 원문을 열어 짚는 수밖에 없다 — 이 화면이
그 일을 10분 안에 끝내게 한다.

저장 형식은 data/review/marked.json 과 같다. 에이전트가 채운 38건과
사람이 채운 것이 한 파일에서 만난다.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
MARKED = ROOT / "data" / "review" / "marked.json"
PICKED = ROOT / "data" / "review" / "golden_v2.json"

router = APIRouter(prefix="/v1/golden", tags=["golden"])
log = logging.getLogger("api.golden")
_JO_RE = re.compile(r"^제\d+조(?:의\d+)?$")


def _idx():
    os.environ.setdefault("STRUCTURE_STORE", str(ROOT / "data" / "structure"))
    from core.rag import index as index_mod
    return index_mod.current()


def _cases() -> dict:
    import sys
    sys.path.insert(0, str(ROOT))
    from scripts.review_golden import _cases as load
    return {c["case_no"]: c for c in load()}


def _marked() -> dict:
    if not MARKED.is_file():
        return {"cases": {}}
    return json.loads(MARKED.read_text("utf-8"))


class Tag(BaseModel):
    decisive: list = []          # [{law, jo, hang_ho, node_id, why}]
    premise: list = []
    direction: Optional[str] = None      # 긍정 | 부정 | 조건부
    colloquial: Optional[str] = None     # 새로 쓴 구어 질문
    note: str = ""
    by: str = "사람"


@router.get("/cases", summary="후보 목록 — 태깅 진행률")
def cases(limit: int = Query(60, ge=1, le=200)):
    import sys
    sys.path.insert(0, str(ROOT))
    from scripts.golden_pick import score
    from scripts.review_golden import _cases as load
    rows = score(load())
    marked = _marked()["cases"]
    out = []
    for r in rows[:limit]:
        m = marked.get(r["case_no"]) or {}
        out.append({
            "case_no": r["case_no"], "score": r["score"], "year": r["year"],
            "title": r["title"], "laws": r["laws"],
            "store_missing": r["store_missing"], "jo_gone": r["jo_gone"],
            "needs_precedent": r["needs_precedent"], "multi_part": r["multi_part"],
            "tagged": bool(m.get("decisive")),
            "tagged_by": m.get("by") or ("에이전트" if m.get("decisive") else None),
            "has_colloquial": bool(m.get("colloquial")),
        })
    done = sum(1 for x in out if x["tagged"])
    return {"total": len(out), "tagged": done, "cases": out}


@router.get("/case/{case_no}", summary="한 건 — 원문과 저장된 태그")
def case(case_no: str):
    c = _cases().get(case_no)
    if c is None:
        raise HTTPException(404, "그런 사례가 없습니다")
    return {
        "case_no": case_no,
        "issue": c.get("issue") or "",
        "answer": c.get("answer") or "",
        "reason": str(c.get("reason") or "")[:20000],
        "laws": c.get("laws") or [],
        "tag": _marked()["cases"].get(case_no),
    }


@router.get("/laws", summary="창고 법령 목록")
def laws():
    idx = _idx()
    return {"laws": sorted(v.name for v in idx.docs.values())}


@router.get("/law", summary="조를 항·호까지 편다 — 마디마다 id")
def law(name: str = Query(...), jo: str = Query("")):
    from core.rag import wikictx
    idx = _idx()
    key = wikictx._pack(name)
    hits = sorted((v for v in idx.docs.values() if key in wikictx._pack(v.name)),
                  key=lambda v: len(v.name))
    if not hits:
        raise HTTPException(404, f"'{name}' 에 걸리는 법령이 없습니다")
    v = hits[0]
    if not jo:
        return {"law": v.name, "alts": [d.name for d in hits[:6]],
                "jos": [{"surface": n["surface"], "title": n.get("title") or "",
                         "node_id": str(n["id"]),
                         "addendum": "부칙" in (v.path(n["id"]) if hasattr(v, "path") else "")}
                        for n in v.nodes if _JO_RE.match(n.get("surface") or "")]}

    def walk(node, depth=0):
        kids = [k for k in v.nodes if k.get("parent") == node["id"]]
        own = v.section_text(node, cap=100000) or ""
        head = own
        if kids:
            first = kids[0].get("surface") or ""
            if first and first in own:
                head = own.split(first)[0]
        return {"node_id": str(node["id"]), "surface": node.get("surface") or "",
                "title": node.get("title") or "", "depth": depth,
                "text": head.strip()[:1200],
                "children": [walk(k, depth + 1) for k in kids]}

    tops = [n for n in v.nodes if (n.get("surface") or "") == jo]
    if not tops:
        raise HTTPException(404, f"{v.name} 에 {jo} 가 없습니다")
    return {"law": v.name, "jo": jo, "nodes": [walk(n) for n in tops]}


@router.post("/tag/{case_no}", summary="태그 저장")
def tag(case_no: str, body: Tag):
    if case_no not in _cases():
        raise HTTPException(404, "그런 사례가 없습니다")
    data = _marked()
    rec = data["cases"].get(case_no) or {}
    if body.decisive:
        rec["decisive"] = [[d.get("law", ""), d.get("jo", "")] for d in body.decisive]
        rec["decisive_full"] = body.decisive
    if body.premise:
        rec["premise_full"] = body.premise
    if body.direction:
        rec["direction"] = body.direction
    if body.colloquial:
        rec["colloquial"] = body.colloquial
    if body.note:
        rec["note"] = body.note
    rec["by"] = body.by
    rec["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["cases"][case_no] = rec
    MARKED.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    log.info("골든 태그 저장 — %s (결정 %d · %s)", case_no, len(body.decisive), body.by)
    return {"ok": True, "case_no": case_no, "tag": rec}
