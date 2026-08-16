"""벡터 우선 회수 — 성능 비교용 실험 모드 (2026-08-10 사용자 결정).

    질의 → 벡터로 진입 구역(entry) 착지
         → 참조 간선(문서 내 상호참조 + 문서 간 링크)을 **결정론으로**
           깊이 제한까지 따라가 연결 구역을 전부 싣는다
         → 출처는 이 회수 집합에서 **정적으로** 만든다 — LLM 이 무엇을
           인용하든 출처 목록은 회수가 정한다

용어 사다리는 지우지 않았다 — 모드로 갈랐다(mode="vector"). A/B 없이는
성능 체크가 안 되고, 벡터가 이기는지 지는지는 골든 질의가 판정할 일이다.
이 모드에서 용어 단은 **아예 돌지 않는다** — 순수 벡터의 성능이 보이도록.

진입 착지는 승격 후보로 적재된다(rag 라우터) — 모드가 바뀌어도
"착지가 쌓이면 용어가 된다"는 자기상각 고리는 같다.
"""

from __future__ import annotations

import logging
import os
import time

from core.rag import answer as answer_mod
from core.rag import vector as vector_mod
from core.rag.answer import CANDIDATES_MAX, SECTION_CHARS, Section
from core.rag.index import Index, norm
from core.rag.search import _ascii_only, _token_in_query

log = logging.getLogger("core.rag.vecfirst")

ENTRY_K = 4             # 진입 구역 수 — 너무 많으면 확장 자리가 없다
# 참조 닫힘의 깊이 — 법령 참조망은 얕고 넓다. 바닥(배제·위임·준용)과 항해가
# 생기면서 이 무차별 닫힘은 보수화 후보다 — golden A/B 로 정할 손잡이.
MAX_DEPTH = int(os.environ.get("RAG_REF_DEPTH", "3"))
KEYWORD_ENTRY_CAP = 2   # 승인 용어가 차지할 수 있는 진입 자리 — 나머지는 벡터


def _approved_hits(index: Index, query: str, cap: int = KEYWORD_ENTRY_CAP):
    """질의에 통째로 들어 있는 **승인(활성) 용어**의 앵커 — 전문 용어는
    keyword 매칭이 맞다(사용자 결정). 색인에 활성만 실리므로 여기 오는 것은
    전부 사람이(또는 저자 선언이) 승인한 것이다. 긴 값 우선 — 더 구체적인
    지목이 이긴다."""
    qn = norm(query)
    q_lower = query.casefold()
    cands = [e for e in index.entries
             if e.kind == "용어" and len(e.key) >= 2 and e.key in qn
             and not (_ascii_only(e.key) and not _token_in_query(e.value, q_lower))]
    cands.sort(key=lambda e: -len(e.key))
    out = []
    seen: set[tuple] = set()
    for e in cands:
        occ = sorted(e.occurrences,
                     key=lambda o: 0 if o.get("via") in ("제목", "정의") else 1)
        for o in occ:
            key = (o.get("doc_id"), o.get("node"))
            if key[0] is None or key[1] is None or key in seen:
                continue
            seen.add(key)
            # target("term:{병합키}")의 키를 함께 낸다 — 실적(hits/misses)은
            # 표면형이 아니라 용어 행에 쌓여야 한다("PSV" 진입도 안전밸브의 실적).
            out.append((e.value, e.target.partition(":")[2], o))
            break                       # 용어 하나에 앵커 하나 — 독식 방지
        if len(out) >= cap:
            break
    return out


def retrieve(index: Index, query: str, entry_k: int = ENTRY_K,
             cap: int = CANDIDATES_MAX, llm=None,
             vec_query: str = "") -> tuple[list[Section], dict]:
    """(구역들, 회수 경위). 진입: 승인 용어(정밀) → 벡터(의미). 확장: 결정론
    바닥(배제·위임·준용 무조건) → 무차별 참조 닫힘 → 남은 자리는 LLM 항해.

    vec_query 는 **벡터 채널 전용** 질의다(쟁점 재작성, wikictx.vector_query).
    용어 진입은 여전히 query(원문)로 간다 — 채널마다 무는 것이 다르기
    때문이다: 색인 용어는 사용자의 낱말과 겹쳐야 물고, 벡터는 조문 문체와
    겹쳐야 문다. 합류는 순위·슬롯 기반이라 질의가 달라도 안전하다."""
    t0 = time.perf_counter()
    vec = vector_mod.search(vec_query or query, topk=max(entry_k * 2, 8))
    meta: dict = {"vector_hits": len(vec), "entries": [], "keywords": [],
                  "depth": 0, "vec_query": vec_query or ""}

    sections: list[Section] = []
    seen: set[tuple] = set()
    # 진입 제외 — "검색무관" 판정이 쌓여 사람이 승인한 좌표는 **진입으로는** 안
    # 데려온다. 참조를 타고는 여전히 온다(연결 지식을 지우는 것이 아니다).
    from core.rag import verdicts as verdicts_mod

    # ── 승인 용어 진입 — 벡터보다 앞선다. 활성만 색인에 있으므로 일반어
    #    오염("가입" 선점)은 승인 단계가 이미 걸렀다.
    for value, term_key, o in _approved_hits(index, query):
        v = index.docs.get(o.get("doc_id"))
        node = o.get("node")
        if v is None or (o["doc_id"], node) in seen:
            continue
        if verdicts_mod.is_entry_blocked(o["doc_id"], node):
            continue
        seen.add((o["doc_id"], node))
        n = v.by_id.get(node)
        sections.append(Section(
            n=0, doc_id=o["doc_id"], doc=v.name, node=node,
            path=v.path(node) or v.name, page=(n or {}).get("page"),
            kind="용어", matched=f"승인 용어 '{value}'",
            text=v.section_text(n, cap=SECTION_CHARS) if n else ""))
        meta["keywords"].append({"용어": value, "key": term_key,
                                 "doc_id": o["doc_id"], "node": node})

    budget = entry_k + len(meta["keywords"])      # 용어가 벡터 자리를 뺏지 않는다
    for doc_id, node, cos in vec:
        if len(sections) >= budget:
            break
        v = index.docs.get(doc_id)
        n = v.by_id.get(node) if v else None
        if v is None or (doc_id, node) in seen:
            continue
        if verdicts_mod.is_entry_blocked(doc_id, node):
            continue
        seen.add((doc_id, node))
        sections.append(Section(
            n=0, doc_id=doc_id, doc=v.name, node=node,
            path=v.path(node) or v.name, page=(n or {}).get("page"),
            kind="벡터", matched=f"코사인 {cos:.2f}",
            text=v.section_text(n, cap=SECTION_CHARS) if n else ""))
        meta["entries"].append({"doc_id": doc_id, "node": node, "cos": cos})

    # ── 결정론 바닥 — 배제(역방향 포함)·위임·준용은 판단 없이 무조건 동반.
    #    배제는 누락이 오답을 만드는 유일한 간선이라 자리 경쟁보다 먼저다.
    from core.rag import expand as expand_mod
    n0 = len(sections)
    sections = expand_mod.expand_floor(index, sections, cap=cap)
    meta["floor"] = [{"kind": s.kind, "path": s.path, "matched": s.matched}
                     for s in sections[n0:]]

    # 연결 닫힘 — expand_refs(1-hop 결정론)를 새 구역이 안 늘 때까지.
    # 매 회전마다 직전 회전의 신규 구역이 확장 출발점이 된다.
    depth = 0
    while depth < MAX_DEPTH and len(sections) < cap:
        grown = answer_mod.expand_refs(index, sections, cap=cap)
        if len(grown) == len(sections):
            break
        sections = grown
        depth += 1
    meta["depth"] = depth

    # ── LLM 항해 — 자리가 남고 판단자가 있으면, 간선 카드를 보고 고른다.
    #    걸음은 kind="항해" 로 남아 진단 튜플에 경로가 쌓인다(승격 루프의 연료).
    from core.rag import switches as switches_mod
    if llm is not None and switches_mod.is_on("navigate") and len(sections) < cap:
        sections, nav = expand_mod.navigate(llm, index, query, sections, cap=cap)
        if nav.get("hops"):
            meta["nav"] = nav

    for i, s in enumerate(sections, start=1):
        s.n = i
    log.info("벡터우선 '%s' → 용어 %d + 진입 %d + 확장(깊이 %d) = %d구역 (%.0fms)",
             query[:60], len(meta["keywords"]), len(meta["entries"]),
             depth, len(sections), (time.perf_counter() - t0) * 1000)
    return sections, meta


def static_refs(sections: list[Section]) -> list[dict]:
    """출처 목록 — 회수 집합 그대로, 좌표·경위·딥링크까지 결정론으로.
    모델 인용(answer 본문의 [n])과 번호가 같아 서로 참조된다."""
    out = []
    for s in sections:
        link = f"/structure/?doc={s.doc_id}"
        if s.node is not None:
            link += f"&node={s.node}"
        if s.block is not None:
            link += f"&block={s.block}"
        out.append({**s.cite(), "kind": s.kind, "matched": s.matched,
                    "link": link})
    return out
