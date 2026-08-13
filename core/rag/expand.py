"""타입 간선 확장 — 결정론 바닥과 LLM 항해.

expand_refs(answer.py)는 참조를 타입 무차별로 걷는다. 여기는 두 층을 얹는다:

**결정론 바닥(floor)** — 판단이 필요 없는(또는 판단에 맡기면 안 되는) 간선을
빈자리보다 먼저, 무조건 싣는다:
    배제   "제N조에도 불구하고 / 적용하지 아니한다" — **역방향 포함**. 착지
           조문을 배제하는 조항이 안 실리면 LLM 은 모르는 게 아니라 **틀린
           답을 확신**한다. 유일하게 누락이 오답을 만드는 간선이라 판단에
           맡기지 않는다.
    위임   "대통령령으로 정하는" — 대상이 착지 조문의 내용을 구성한다(답의
           반쪽). 거의 항상 옳아 판단이 낭비다. delegation.json 이 좌표를 준다.
    준용   "제N조를 준용한다" — 위임과 같은 보완 관계, 문면 간선(rel)로 잡힌다.
    수임   "제N조에서 '…'이란"을 쓴 하위 규정 조문 — **역방향**. 위임 데이터가
           행정규칙 대상의 조 좌표를 안 주므로(문서 수준뿐), 시행령→규정
           수직 체인의 조 단위 좌표는 이 역간선이 유일한 원천이다.

**LLM 항해(navigate)** — 바닥 뒤 남은 자리의 배분은 판단 문제다. "인용은
보수적으로"는 뭉툭한 일괄 규칙이고, 어떤 인용이 이번 질문에 결정적인지는
질문을 읽어야 안다. 내비게이터는 본문이 아니라 **간선 카드**(관계·대상 경로·
표면형)만 보고 열 것을 고른다 — 카드가 짧아 콜이 싸고, 걸음은 회수 경위
(kind="항해")로 남아 진단 튜플에 경로가 쌓인다. 반복되는 경로는 승격 루프의
연료다(탐색은 규칙의 탄생지, 결정론은 규칙의 실행지).

억제 간선(edge_rules)과 사람의 관계 정정(rel_fixes)은 색인 조립에서 이미
반영돼 있으므로 두 층 다 공짜로 물려받는다.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from core.rag import delegation as delegation_mod
from core.rag.answer import CANDIDATES_MAX, SECTION_CHARS, Section
from core.rag.index import Index

log = logging.getLogger("core.rag.expand")

_JO_SURFACE = re.compile(r"^제\d+조(의\d+)?$")
DELEG_PER_SECTION = 3                   # 조 하나의 위임 동반 상한 — 꼬리는 항해 몫
NAV_HOPS = 2
NAV_PICKS = 6
NAV_CARDS = 24


def _enclosing_jo(v, node: Optional[int]) -> Optional[int]:
    """구역을 덮는 조 — 위임 간선의 좌표계(조 단위)로 올라간다."""
    cur = v.by_id.get(node) if node is not None else None
    while cur is not None:
        if _JO_SURFACE.fullmatch((cur.get("surface") or "").strip()):
            return cur.get("id")
        cur = v.by_id.get(cur.get("parent"))
    return None


def _mk(index: Index, doc_id: str, node: int, kind: str, matched: str,
        ref_src: Optional[dict] = None) -> Optional[Section]:
    v = index.docs.get(doc_id)
    n = v.by_id.get(node) if v else None
    if v is None or n is None:
        return None
    return Section(n=0, doc_id=doc_id, doc=v.name, node=node,
                   path=v.path(node) or v.name, page=n.get("page"),
                   kind=kind, matched=matched,
                   text=v.section_text(n, cap=SECTION_CHARS),
                   ref_src=ref_src)


def expand_floor(index: Index, sections: list[Section],
                 cap: int = CANDIDATES_MAX) -> list[Section]:
    """배제(역방향 포함)·위임·준용 — 원 히트에서 한 걸음, 무조건 동반."""
    from core.rag import switches as switches_mod   # 지연 — 순환 회피
    from core.rag import verdicts as verdicts_mod

    # 엔진 스위치 — 동반 규칙은 전부 사용자가 켜고 끈다
    on_excl = switches_mod.is_on("floor_exclusion")
    on_deleg = switches_mod.is_on("floor_delegation")
    on_jun = switches_mod.is_on("floor_junyong")
    on_recv = switches_mod.is_on("floor_reception")

    out = list(sections)
    seen = {(s.doc_id, s.node) for s in sections}
    cross = index.cross_ref_edges()

    def push(doc_id, node, kind, matched, ref_src=None) -> None:
        if (doc_id, node) in seen or len(out) >= cap:
            return
        s = _mk(index, doc_id, node, kind, matched, ref_src)
        if s is not None:
            seen.add((doc_id, node))
            out.append(s)

    deleg = delegation_mod.adjacency()
    for s in list(sections):                        # 원 히트만 출발점 — 1층
        v = index.docs.get(s.doc_id)
        n = v.by_id.get(s.node) if v else None
        if v is None or n is None:
            continue
        jo = _enclosing_jo(v, s.node)
        span = n.get("span") or [0, 0]
        tail = s.path.split(" ▸ ")[-1] if s.path else s.doc

        # ── 역방향 배제·수임 — 이 구역(또는 그 조)을 **가리키는** 조항. 간선
        #    방향이 반대라 expand_refs 는 영영 못 데려온다.
        #    배제: 착지의 적용을 막는 조항 — 누락이 오답을 만든다.
        #    수임: "제N조에서 '…'이란"으로 착지의 위임을 받은 조문 — 위임
        #    데이터가 행정규칙 대상의 조 좌표를 안 주므로(문서 수준뿐, 실측)
        #    시행령→규정 수직 체인의 좌표는 이 역간선이 유일하다.
        targets = {t for t in (s.node, jo) if t is not None}
        REV = {}
        if on_excl:
            REV["배제"] = "{tail}의 적용을 배제·제한 — '{surface}'"
        if on_recv:
            REV["수임"] = "{tail}의 위임을 받은 조문 — '{surface}'"
        rev_caps = {"배제": cap, "수임": 3}      # 배제는 전부, 수임은 조문당 3
        rev_n = {"배제": 0, "수임": 0}
        for src_doc, src_node, rel, surface, e_dst in (
                [(s.doc_id, e["src"], e.get("rel"), e["surface"], e["dst"])
                 for e in index.ref_edges().get(s.doc_id, [])
                 if e["dst"] in targets]
                + [(e["src_doc"], e["src"], e.get("rel"), e["surface"], e["dst"])
                   for e in cross
                   if e.get("dst_doc") == s.doc_id and e["dst"] in targets]):
            if rel not in REV or rev_n[rel] >= rev_caps[rel]:
                continue
            if verdicts_mod.is_suppressed(src_doc, src_node, s.doc_id, e_dst):
                continue
            before = len(out)
            push(src_doc, src_node, rel,
                 REV[rel].format(tail=tail, surface=surface),
                 ref_src={"doc_id": s.doc_id, "node": s.node,
                          "path": s.path, "surface": surface})
            if len(out) > before:
                rev_n[rel] += 1

        # ── 순방향 배제·준용 — 이 구역 본문의 문면 간선 중 바닥 관계
        fwd_kinds = ({"배제"} if on_excl else set()) | ({"준용"} if on_jun else set())
        near = [(s.doc_id, e) for e in index.ref_edges().get(s.doc_id, [])]
        far = [(e["dst_doc"], e) for e in cross if e.get("src_doc") == s.doc_id]
        for dst_doc, e in near + far:
            blk = e.get("block")
            if e.get("rel") not in fwd_kinds or blk is None \
                    or not (span[0] <= blk < max(span[1], span[0] + 1)):
                continue
            if verdicts_mod.is_suppressed(s.doc_id, s.node, dst_doc, e["dst"]):
                continue
            push(dst_doc, e["dst"], e["rel"], f"{tail} → '{e['surface']}'",
                 ref_src={"doc_id": s.doc_id, "node": s.node,
                          "path": s.path, "surface": e["surface"]})

        # ── 위임 — 조 단위 좌표계. 착지가 항·호라도 조로 올라가 걷는다.
        rows = []
        if on_deleg:
            for key in {(s.doc_id, jo), (s.doc_id, s.node)}:
                rows.extend(deleg.get(key, []))
        for d in rows[:DELEG_PER_SECTION]:
            if verdicts_mod.is_suppressed(s.doc_id, s.node, d["doc_id"], d["node"]):
                continue
            push(d["doc_id"], d["node"], "위임",
                 f"{tail}의 위임({d['kind']}) — '{d['link']}'",
                 ref_src={"doc_id": s.doc_id, "node": s.node,
                          "path": s.path, "surface": d["link"] or d["kind"]})
    return out


# ------------------------------------------------------------------ LLM 항해
NAV_SYSTEM = (
    "너는 법령 검색의 간선 항해사다. 사용자 질문과, 이미 회수된 구역들에서 "
    "뻗어 나가는 간선 카드 목록을 받는다. 카드는 {id, rel(관계), from(출발), "
    "to(대상 문서와 구역), 표면형(원문 표현)}이다.\n"
    "질문에 답하는 데 **열 가치가 있는** 간선만 고른다 — 대상 구역의 제목과 "
    "관계로 판단한다. 과다 선택 금지: 확신 있는 것만, 없으면 picks 를 비우고 "
    "done=true. 필수 간선(배제·위임·준용)은 이미 실려 있다 — 너의 몫은 "
    "인용·근거 중 이번 질문에 결정적인 것을 고르는 판단이다."
)
NAV_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {"type": "integer"}},
                   "done": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["picks", "done", "reason"], "additionalProperties": False,
}


def _edge_cards(index: Index, frontier: list[Section], seen: set,
                cap: int = NAV_CARDS) -> list[dict]:
    """열 수 있는 간선의 카드 — 본문 없이 관계·대상·표면형만."""
    from core.rag import verdicts as verdicts_mod

    cross = index.cross_ref_edges()
    cards: list[dict] = []
    for s in frontier:
        v = index.docs.get(s.doc_id)
        n = v.by_id.get(s.node) if v else None
        if v is None or n is None:
            continue
        span = n.get("span") or [0, 0]
        tail = s.path.split(" ▸ ")[-1] if s.path else s.doc
        near = [(s.doc_id, e) for e in index.ref_edges().get(s.doc_id, [])]
        far = [(e["dst_doc"], e) for e in cross if e.get("src_doc") == s.doc_id]
        for dst_doc, e in near + far:
            blk = e.get("block")
            if blk is None or not (span[0] <= blk < max(span[1], span[0] + 1)):
                continue
            if (dst_doc, e["dst"]) in seen or len(cards) >= cap:
                continue
            tv = index.docs.get(dst_doc)
            if tv is None or verdicts_mod.is_suppressed(
                    s.doc_id, s.node, dst_doc, e["dst"]):
                continue
            cards.append({"id": len(cards), "rel": e.get("rel", "인용"),
                          "from": tail,
                          "to": f"{tv.name} ▸ {tv.path(e['dst'])}",
                          "표면형": e["surface"],
                          "_dst": (dst_doc, e["dst"]), "_src": s})
    return cards


def navigate(llm, index: Index, question: str, sections: list[Section],
             cap: int = CANDIDATES_MAX, hops: int = NAV_HOPS) -> tuple[list[Section], dict]:
    """남은 자리를 LLM 판단으로 — (구역들, 항해 기록). LLM 이 없으면 그대로."""
    import json as json_mod

    meta = {"hops": 0, "picked": []}
    if llm is None:
        return sections, meta
    out = list(sections)
    frontier = sections
    for hop in range(hops):
        if len(out) >= cap:
            break
        seen = {(x.doc_id, x.node) for x in out}
        cards = _edge_cards(index, frontier, seen)
        if not cards:
            break
        view = [{k: c[k] for k in ("id", "rel", "from", "to", "표면형")}
                for c in cards]
        resp = llm.structured(
            "rag.navigate", NAV_SYSTEM,
            f"[질문]\n{question}\n\n[간선 카드(JSON)]\n"
            f"{json_mod.dumps(view, ensure_ascii=False)}",
            NAV_SCHEMA, max_tokens=400, effort="low")
        meta["hops"] = hop + 1
        if resp is None:
            break
        by_id = {c["id"]: c for c in cards}
        fresh: list[Section] = []
        for i in resp.get("picks", [])[:NAV_PICKS]:
            c = by_id.get(i)
            if c is None or len(out) >= cap:
                continue
            dst_doc, dst = c["_dst"]
            if (dst_doc, dst) in seen:
                continue
            src = c["_src"]
            s = _mk(index, dst_doc, dst, "항해",
                    f"{c['rel']} · {c['from']} → '{c['표면형']}'",
                    ref_src={"doc_id": src.doc_id, "node": src.node,
                             "path": src.path, "surface": c["표면형"]})
            if s is not None:
                seen.add((dst_doc, dst))
                out.append(s)
                fresh.append(s)
                meta["picked"].append({"rel": c["rel"], "to": c["to"],
                                       "표면형": c["표면형"], "hop": hop + 1})
        if resp.get("done") or not fresh:
            break
        frontier = fresh
    return out, meta
