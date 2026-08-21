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
from typing import Optional

from lawrag.core.rag import answer as answer_mod
from lawrag.core.rag import vector as vector_mod
from lawrag.core.rag.answer import CANDIDATES_MAX, SECTION_CHARS, Section
from lawrag.core.rag.index import Index, norm
from lawrag.core.rag.search import _ascii_only, _token_in_query

log = logging.getLogger("lawrag.core.rag.vecfirst")

DOC_COMPANION_FANOUT = 20   # 문서 동반 게이트 — 밖 인용(중복 접음)이 이보다 많으면 안 태운다
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
             vec_query: str = "", seeds: Optional[list] = None,
             raw_query: str = ""
             ) -> tuple[list[Section], dict]:
    """(구역들, 회수 경위). 진입: 질문 기억(승인 좌표) → 승인 용어(정밀) →
    벡터(의미). 확장: 결정론 바닥(배제·위임·준용 무조건) → 무차별 참조 닫힘 →
    남은 자리는 LLM 항해.

    vec_query 는 **벡터 채널 전용** 질의다(쟁점 재작성, wikictx.vector_query).
    용어 진입은 호출부가 넘긴 query 로 간다(라우터는 쟁점 확장 질의 qx 를
    넘긴다) — 채널마다 무는 것이 다르기 때문이다: 색인 용어는 사용자의 낱말과
    겹쳐야 물고, 벡터는 조문 문체와 겹쳐야 문다. 합류는 순위·슬롯 기반이라
    질의가 달라도 안전하다.

    seeds 는 검색 없이 여는 좌표(promote.direct_hits — 사람이 승인한 질문↔조문
    연결)다. 진입보다 앞에 앉고 벡터 예산을 뺏지 않으며 진입 제외를 받지 않는다."""
    t0 = time.perf_counter()
    vec = vector_mod.search(vec_query or query, topk=max(entry_k * 2, 8),
                            doc_ids=index.scope)          # 진입은 스코프 안만
    meta: dict = {"vector_hits": len(vec), "entries": [], "keywords": [],
                  "memory": [], "concept_hits": [], "depth": 0,
                  "vec_query": vec_query or ""}

    sections: list[Section] = []
    seen: set[tuple] = set()
    # 진입 제외 — "검색무관" 판정이 쌓여 사람이 승인한 좌표는 **진입으로는** 안
    # 데려온다. 참조를 타고는 여전히 온다(연결 지식을 지우는 것이 아니다).
    from lawrag.core.rag import verdicts as verdicts_mod

    # ── 1급 Concept/Assertion — 자연어를 직접 Cypher로 바꾸지 않는다. 승인
    #    Concept 메뉴 정렬 → 고정 OQL pattern → ID 파라미터 바인딩만 허용한다.
    from lawrag.core.rag import switches as switches_mod
    meta["concept"] = {}
    if switches_mod.is_on("concept_entry"):
        from lawrag.core.rag import conceptfirst as conceptfirst_mod
        concept_sections, cmeta = conceptfirst_mod.retrieve(
            index, raw_query or query, llm=llm)
        meta["concept"] = cmeta
        for section in concept_sections:
            key = (section.doc_id, section.node)
            if key in seen or verdicts_mod.is_entry_blocked(*key):
                continue
            seen.add(key)
            sections.append(section)
            meta["concept_hits"].append({"doc_id": section.doc_id,
                                         "node": section.node,
                                         "matched": section.matched})

    # ── 질문 기억 — 같은/비슷한 질문에 사람이 승인한 착지. 검색보다 앞선다.
    for c in seeds or []:
        v = index.docs.get(c.get("doc_id"))
        node = c.get("node")
        if v is None or node is None or (c["doc_id"], node) in seen:
            continue
        if not index.in_scope(c["doc_id"]):       # 기억도 진입이다 — 스코프 밖은 안 연다
            continue
        seen.add((c["doc_id"], node))
        n = v.by_id.get(node)
        sections.append(Section(
            n=0, doc_id=c["doc_id"], doc=v.name, node=node,
            path=v.path(node) or v.name, page=(n or {}).get("page"),
            kind=c.get("via") or "질문 기억", matched=(c.get("why") or "")[:80],
            text=v.section_text(n, cap=SECTION_CHARS) if n else ""))
        meta["memory"].append({"doc_id": c["doc_id"], "node": node,
                               "why": c.get("why", "")})

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
            kind="용어", matched=f"승인 용어 '{value}'", term_key=term_key,
            text=v.section_text(n, cap=SECTION_CHARS) if n else ""))
        meta["keywords"].append({"용어": value, "key": term_key,
                                 "doc_id": o["doc_id"], "node": node})

    # ── 프레임 진입 — 질문을 '누가·무엇을·한다' 슬롯으로 옮겨(LLM 1콜) 조문
    #    프레임의 행위 어휘와 렉시컬로 맞춘다. 벡터가 낱말 겹침으로 이웃 조에
    #    끌리는 자리(실측: '성과보수' → 제98조의2, 정답 제71조)를 행위 문형이
    #    가른다. 스코프는 entry_docs 가 이미 걸렀다.
    meta["frame_hits"] = []
    if llm is not None and switches_mod.is_on("frame_entry"):
        from lawrag.core.rag import framequery as framequery_mod
        fhits, fmeta = framequery_mod.lex_hits(index, llm, query)
        meta["frame_query"] = fmeta.get("frames") or []
        for h in fhits:
            v = index.docs.get(h["doc_id"])
            node = h["node"]
            if v is None or (h["doc_id"], node) in seen:
                continue
            if verdicts_mod.is_entry_blocked(h["doc_id"], node):
                continue
            seen.add((h["doc_id"], node))
            n = v.by_id.get(node)
            sections.append(Section(
                n=0, doc_id=h["doc_id"], doc=v.name, node=node,
                path=v.path(node) or v.name, page=(n or {}).get("page"),
                kind="프레임", matched=h["why"][:80],
                text=v.section_text(n, cap=SECTION_CHARS) if n else ""))
            meta["frame_hits"].append({"doc_id": h["doc_id"], "node": node,
                                       "score": h["score"]})

    # Concept·용어·기억·프레임이 벡터 자리를 뺏지 않는다
    budget = (entry_k + len(meta["keywords"]) + len(meta["memory"])
              + len(meta["frame_hits"]) + len(meta["concept_hits"]))
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
    from lawrag.core.rag import expand as expand_mod
    n0 = len(sections)
    sections = expand_mod.expand_floor(index, sections, cap=cap)
    meta["floor"] = [{"kind": s.kind, "path": s.path, "matched": s.matched}
                     for s in sections[n0:]]

    # ── 문서 동반 — 밖 인용이 적은 실무문서가 착지하면 그 문서의 밖 인용 전부를
    #    동반한다. 모범규준·가이드·내규는 법령 요약·인용 모음이라 밖 인용 목록이
    #    곧 그 주제의 법령 지도인데, 참조 닫힘은 **착지한 마디**에서만 출발하므로
    #    인용 마디가 착지하지 않으면 다리가 있어도 못 탄다(실측 2026-08-20 t3-16:
    #    §125 간선 확정 후에도 체크리스트 구역만 착지해 미회수). 게이트는 문서의
    #    중복 접은 목적지 수 ≤ FANOUT — 실측 분포(중앙값 9 · 최대 1,795)에서 법령·
    #    시행령(수백~)은 자동 배제되고 실무문서(0~86)만 든다. 문서별 상수가 아니라
    #    관측 게이트다.
    meta["doc_companion"] = []
    if switches_mod.is_on("doc_companion"):
        landed = {s.doc_id for s in sections}
        fan: dict = {}
        for e in index.cross_ref_edges():
            if e.get("src_doc") in landed:
                fan.setdefault(e["src_doc"], {}).setdefault(
                    (e["dst_doc"], e["dst"]), e["src"])
        for did in sorted(landed):
            tgts = fan.get(did) or {}
            if not tgts or len(tgts) > DOC_COMPANION_FANOUT:
                continue
            src_name = index.docs[did].name if did in index.docs else did
            for (dst_doc, dst), src_node in sorted(tgts.items()):
                # cap 밖 전용 예산 — 동반은 자리 경쟁보다 먼저다(배제 동반과 같은
                # 원리). cap 안에서 겨루게 하면 벡터·바닥이 채운 뒤 남는 자리가
                # 없어 7개 중 3개만 타고 §125 가 잘렸다(실측 2026-08-20 t3-16,
                # doc_id 정렬 6번째). 총량은 게이트 문턱(≤20)이 그대로 막는다.
                if len(meta["doc_companion"]) >= DOC_COMPANION_FANOUT:
                    break
                if (dst_doc, dst) in seen:
                    continue
                tv = index.docs.get(dst_doc)
                if tv is None or verdicts_mod.is_entry_blocked(dst_doc, dst):
                    continue
                seen.add((dst_doc, dst))
                n = tv.by_id.get(dst)
                sections.append(Section(
                    n=0, doc_id=dst_doc, doc=tv.name, node=dst,
                    path=tv.path(dst) or tv.name, page=(n or {}).get("page"),
                    kind="문서 동반", matched=f"{src_name[:24]} 의 밖 인용",
                    ref_src={"doc_id": did, "node": src_node},
                    text=tv.section_text(n, cap=SECTION_CHARS) if n else ""))
                meta["doc_companion"].append(
                    {"src": did, "doc_id": dst_doc, "node": dst})

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
