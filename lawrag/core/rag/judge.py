"""닫힌 목록 링크 판정 — 결정론이 못 정한 연결의 소수만 LLM 이 고른다.

term_marker 의 원칙(§2.3-2 — 찾기는 결정론, 해석은 LLM)을 연결에도 적용한다.
결정론(refs.cross_resolve 의 이름 대조)이 하나로 떨어뜨리지 못한 것 — 동법·
같은 규정 같은 대용어, 여러 문서·구역에 걸린 번호 — 만 여기로 온다.

재사용을 위해 판정기는 도메인을 모른다. 항목마다 {id, ask, context,
candidates[{cid, label}]} 를 받고 **후보 cid 로만** 답한다(answer.py 의 닫힌
인용과 같은 규율 — 모델이 좌표를 지어낼 자리가 없다). 조문 참조 말고도 애매한
용어 출현, 구역 제목 충돌처럼 "닫힌 후보 중 하나 고르기" 모양이면 그대로 쓴다.

fail-closed: LLM 없음 · 저신뢰(<0.5) · 목록 밖 cid 는 전부 버린다 — 잘못 이은
링크는 없는 링크보다 나쁘다. 판정 결과는 호출자가 저장한다(links.json) —
컴파일 국면에 한 번 정하고, 질의마다 재판단하지 않는다.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:                      # 실행 시 의존을 만들지 않는다 — 타입만
    from lawrag.core.rag.index import Index

JUDGE_MIN_CONF = 0.5

JUDGE_SYSTEM = (
    "너는 문서 연결 판정기다. 결정론 검색이 하나로 정하지 못한 연결 항목들을 받는다. "
    "각 항목은 {id, ask(무엇을 정하는가), context(참조가 쓰인 원문), "
    "candidates[{cid, label}]} 다.\n"
    "  - 항목마다 context 가 실제로 가리키는 후보를 **cid 로만** 고른다.\n"
    "  - 어느 후보도 아니거나 근거가 부족하면 cid 를 null 로 둔다 — 추측 금지. "
    "잘못 이은 링크는 없는 링크보다 나쁘다.\n"
    "  - confidence 는 0~1. 확신이 없으면 낮게 — 낮은 것은 시스템이 버린다."
)

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"},
        "cid": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "reason": {"type": "string"}},
        "required": ["id", "cid", "confidence", "reason"],
        "additionalProperties": False}}},
    "required": ["picks"],
    "additionalProperties": False,
}


def judge(llm, items: list[dict], kind: str = "rag.link.judge") -> dict:
    """항목들을 한 번에 판정한다 — {id: {"cid","confidence","reason"}}.

    확신 있는 선택만 남는다. LLM 이 없거나 실패하면 빈 dict — 호출자는 그
    항목들을 보류로 유지하면 된다(없는 링크가 잘못 이은 링크보다 낫다)."""
    if llm is None or not items:
        return {}
    view = [{"id": it["id"], "ask": it.get("ask", ""),
             "context": it.get("context", ""), "candidates": it["candidates"]}
            for it in items]
    out = llm.structured(kind, JUDGE_SYSTEM,
                         f"[판정 항목(JSON)]\n{json.dumps(view, ensure_ascii=False)}",
                         JUDGE_SCHEMA, max_tokens=2000, effort="low")
    if out is None:
        return {}
    valid = {it["id"]: {c["cid"] for c in it["candidates"]} for it in items}
    picked: dict = {}
    for p in out.get("picks", []):
        pid, cid = p.get("id"), p.get("cid")
        if pid not in valid or cid is None or cid not in valid[pid]:
            continue
        if float(p.get("confidence", 0)) < JUDGE_MIN_CONF:
            continue
        picked[pid] = {"cid": cid, "confidence": float(p["confidence"]),
                       "reason": (p.get("reason") or "")[:200]}
    return picked


def settle_cross(llm, index: "Index") -> tuple[list, dict]:
    """보류된 문서 간 참조를 판정해 확정 링크로 만든다.

    저장은 호출자가 한다(links.json) — 여기서는 좌표만 만든다. 후보 라벨은
    "문서명 ▸ 경로" 라서 모델이 문서 내용을 몰라도 이름과 원문 문맥으로
    고를 수 있다."""
    _, pending = index.cross_refs()
    items: list[dict] = []
    for i, p in enumerate(pending):
        # 후보는 자르지 않는다 — 닫힌 목록에서 정답이 빠지면 판정 자체가 무효다.
        # 개수는 "같은 번호를 가진 문서 수"라 본질적으로 작다.
        cands = []
        for c in p.get("candidates", []):
            v = index.docs.get(c.get("doc_id"))
            if v is None:
                continue
            cands.append({"cid": f"{c['doc_id']}:{c['node']}",
                          "label": f"{v.name} ▸ {v.path(c['node']) or c['node']}"})
        if not cands:
            continue
        items.append({"id": f"p{i}",
                      "ask": f"'{p['surface']}' (단서: {p['hint'] or '없음'}) 가 "
                             "가리키는 문서·구역은?",
                      "context": p.get("context", ""), "candidates": cands})
    picks = judge(llm, items)
    links: list[dict] = []
    for i, p in enumerate(pending):
        got = picks.get(f"p{i}")
        if not got:
            continue
        d, _, n = got["cid"].rpartition(":")
        links.append({"src_doc": p["src_doc"], "src": p["src"],
                      "dst_doc": d, "dst": int(n),
                      "surface": p["surface"], "hint": p["hint"],
                      "key": p.get("key"), "block": p.get("block"),
                      "via": "LLM", "confidence": got["confidence"],
                      "reason": got.get("reason", "")})
    return links, {"pending": len(pending), "settled": len(links)}
