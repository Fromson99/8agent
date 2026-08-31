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

from lawrag.core.rag import definitions as definitions_mod
from lawrag.core.rag import delegation as delegation_mod
from lawrag.core.rag import relations as relations_mod
from lawrag.core.rag import tags as tags_mod
from lawrag.core.rag.answer import CANDIDATES_MAX, SECTION_CHARS, Section
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.index import Index

log = logging.getLogger("lawrag.core.rag.expand")

# 편-조 체계(제4-19조)까지 문다 — 좁게 잡으면 규정·세칙류에서 조용히 빠진다
# (docs/LEGAL_DOMAIN §2 함정 ①, wikictx._ART_RE 와 같은 교훈).
_JO_SURFACE = re.compile(r"^제\d+(?:-\d+)?조(?:의\d+)?$")
DELEG_PER_SECTION = int(control_value("expand.delegations_per_section_max"))
NAV_HOPS = int(control_value("expand.navigation_hops_max"))
NAV_PICKS = int(control_value("expand.navigation_picks_max"))
NAV_CARDS = int(control_value("expand.navigation_cards_max"))


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


def _expand_floor_legacy(index: Index, sections: list[Section],
                         cap: int = CANDIDATES_MAX) -> list[Section]:
    """배제(역방향 포함)·위임·준용 — 원 히트에서 한 걸음, 무조건 동반."""
    from lawrag.core.rag import switches as switches_mod   # 지연 — 순환 회피
    from lawrag.core.rag import verdicts as verdicts_mod

    # 엔진 스위치 — 동반 규칙은 전부 사용자가 켜고 끈다
    on_excl = switches_mod.is_on("floor_exclusion")
    on_deleg = switches_mod.is_on("floor_delegation")
    on_jun = switches_mod.is_on("floor_junyong")
    on_recv = switches_mod.is_on("floor_reception")
    on_def = switches_mod.is_on("floor_definition")
    on_sanc = switches_mod.is_on("floor_sanction")

    out = list(sections)
    seen = {(s.doc_id, s.node) for s in sections}
    # 후순위(demote) — "참조무관" 판정을 사람이 승인한 간선은 지우지 않고
    # **자리 경쟁에서 뒤로** 민다. 바닥은 무조건 동반이라 cap 을 먼저 먹으므로,
    # 여기서 안 밀면 expand_refs 의 후순위는 관측되지 않는다(2026-08-18 감사).
    deferred: list[tuple] = []

    def push(doc_id, node, kind, matched, ref_src=None, _late=False) -> None:
        if (doc_id, node) in seen or len(out) >= cap:
            return
        if (not _late and ref_src
                and verdicts_mod.is_demoted(ref_src["doc_id"], ref_src["node"],
                                            doc_id, node)):
            deferred.append((doc_id, node, kind, matched, ref_src))
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
        # 제재: 착지가 의무·금지 조문일 때만(성격 태그), 벌칙 조에서 이 조를
        # 겨누는 역간선("제N조를 위반한 자는…")을 싣는다. rel 이 아니라
        # **출발점의 성격**(벌칙 조인가)이 가르는 유일한 동반이다 — 벌칙 조의
        # 인용은 rel 분류가 없어 이 검사 없이는 영영 안 온다.
        sanc_ok = (on_sanc
                   and tags_mod.has_condition(v, s.node, ("의무", "금지")))
        if sanc_ok:
            REV["제재"] = "{tail} 위반의 벌칙·과태료 — '{surface}'"
        rev_caps = {"배제": cap, "수임": 3, "제재": 2}   # 배제는 전부
        rev_n = {"배제": 0, "수임": 0, "제재": 0}

        def hits_here(dst: int) -> bool:
            """역간선의 도착이 이 착지인가 — 역간선은 "제26조제1항제1호 단서에서"
            (세칙 수임)·"제17조제1항을 위반한 자"(벌칙)처럼 착지 조의 **항·호**를
            겨눈다. 도착의 소속 조까지 올려 대조한다 (2026-08-19: 처음엔 제재만
            완화했는데 KRX 규정→세칙 수임이 같은 이유로 안 서서 전부 완화)."""
            if dst in targets:
                return True
            return jo is not None and _enclosing_jo(v, dst) == jo

        for src_doc, src_node, rel, surface, e_dst in (
                [(s.doc_id, e["src"], e.get("rel"), e["surface"], e["dst"])
                 for e in index.ref_edges().get(s.doc_id, [])
                 if hits_here(e["dst"])]
                + [(e["src_doc"], e["src"], e.get("rel"), e["surface"], e["dst"])
                   for e in index.cross_to(s.doc_id) if hits_here(e["dst"])]):
            lab = rel if rel in REV else None
            if lab is None and sanc_ok:
                sv = index.docs.get(src_doc)
                if sv is not None and tags_mod.is_sanction(sv, src_node):
                    lab = "제재"
            if lab is None or rev_n[lab] >= rev_caps[lab]:
                continue
            if verdicts_mod.is_suppressed(src_doc, src_node, s.doc_id, e_dst):
                continue
            before = len(out)
            push(src_doc, src_node, lab,
                 REV[lab].format(tail=tail, surface=surface),
                 ref_src={"doc_id": s.doc_id, "node": s.node,
                          "path": s.path, "surface": surface})
            if len(out) > before:
                rev_n[lab] += 1

        # ── 순방향 배제·준용 — 이 구역 본문의 문면 간선 중 바닥 관계
        fwd_kinds = ({"배제"} if on_excl else set()) | ({"준용"} if on_jun else set())
        near = [(s.doc_id, e) for e in index.ref_edges().get(s.doc_id, [])]
        far = [(e["dst_doc"], e) for e in index.cross_from(s.doc_id)]
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

        # ── 정의 동반 — 착지 조문의 관할 정의 조(최근접 스코프 + 문서 대표).
        #    실체 조문만 잡고 정의를 놓치는 실측(casereview: 미회수 4건)의
        #    질의응답판. 관할 계산은 tags.governing_definitions — 편마다 제
        #    정의 조를 두는 규정류(금융투자업규정 11개)에서 엉뚱한 편의
        #    용어를 끌고 오지 않는다.
        #    정의 **호** 우선 — 착지 본문에 실제로 쓰인 정의어의 호만 동반한다
        #    (definitions.terms_in: 개보법 제17조 → 제2조 5호·1호·3호·2호). 조
        #    통째(호 열 개)를 싣던 것보다 좁고 정확하다. 쓰인 정의어가 하나도
        #    안 물리면 관할 정의 조로 폴백 — 정의는 있는데 낱말 대조가 안 된
        #    경우(별칭 표기 등)를 잃지 않기 위해서다.
        if on_def:
            used = definitions_mod.terms_in(v, s.node)
            if used:
                for d in used:
                    push(s.doc_id, d["node"], "정의",
                         f"{tail}의 '{d['term']}' 정의",
                         ref_src={"doc_id": s.doc_id, "node": s.node,
                                  "path": s.path, "surface": d["term"]})
            else:
                for d_node in tags_mod.governing_definitions(v, s.node):
                    push(s.doc_id, d_node, "정의",
                         f"{tail} 용어의 관할 정의 조",
                         ref_src={"doc_id": s.doc_id, "node": s.node,
                                  "path": s.path, "surface": "용어의 뜻"})
    # 후순위 간선은 남은 자리에만 앉는다 — 연결은 살아 있고 순서만 뒤다.
    for doc_id, node, kind, matched, ref_src in deferred:
        push(doc_id, node, kind, matched + " (후순위)", ref_src, _late=True)
    return out


def expand_floor(index: Index, sections: list[Section],
                 cap: int = CANDIDATES_MAX) -> list[Section]:
    """필수 companion을 통합 관계 번들에서 한 층 연다.

    과거에는 배제·위임·준용·수임·정의·제재가 각각 별도 생성기를 호출했다. 이제
    LegalClosure·간선 항해·domain graph와 같은 ``relations.RelationBundle``을 걷는다.
    정의어가 본문에 직접 나타나지 않는 경우의 관할 정의 조 fallback만 기존 호환 계약으로
    남긴다. 이것은 확정 ``USES_DEFINITION`` 간선이 아니라 검색 보조임을 matched에 표시한다.
    """
    from lawrag.core.rag import switches as switches_mod
    from lawrag.core.rag import verdicts as verdicts_mod

    enabled = {
        "EXCLUDES": switches_mod.is_on("floor_exclusion"),
        "DELEGATES_TO": switches_mod.is_on("floor_delegation"),
        "INCORPORATES": switches_mod.is_on("floor_junyong"),
        "RECEIVES_FROM": switches_mod.is_on("floor_reception"),
        "USES_DEFINITION": switches_mod.is_on("floor_definition"),
        "VIOLATION_SANCTIONED_BY": switches_mod.is_on("floor_sanction"),
        "DEEMS": True,
        "EFFECTIVE_FOR": True,
        "APPLIES_TO": True,
        "TRANSITION_FOR": True,
    }
    public_kind = {
        "EXCLUDES": "배제", "DELEGATES_TO": "위임",
        "INCORPORATES": "준용", "RECEIVES_FROM": "수임",
        "USES_DEFINITION": "정의", "VIOLATION_SANCTIONED_BY": "제재",
        "DEEMS": "의제", "EFFECTIVE_FOR": "시행일",
        "APPLIES_TO": "적용례", "TRANSITION_FOR": "경과조치",
    }
    per_seed_cap = {
        "DELEGATES_TO": DELEG_PER_SECTION, "RECEIVES_FROM": 3,
        "VIOLATION_SANCTIONED_BY": 2, "USES_DEFINITION": 4,
    }
    priority = {
        "EXCLUDES": 0, "DELEGATES_TO": 1, "INCORPORATES": 2,
        "RECEIVES_FROM": 3, "USES_DEFINITION": 4,
        "VIOLATION_SANCTIONED_BY": 5, "DEEMS": 6,
        "APPLIES_TO": 7, "TRANSITION_FOR": 8, "EFFECTIVE_FOR": 9,
    }
    out = list(sections)
    seen = {(row.doc_id, row.node) for row in out}
    deferred = []

    def push(seed: Section, doc_id: str, node: object, rel_kind: str,
             matched: str, *, late: bool = False) -> bool:
        if (doc_id, node) in seen or len(out) >= cap:
            return False
        if verdicts_mod.is_suppressed(seed.doc_id, seed.node, doc_id, node):
            return False
        ref_src = {"doc_id": seed.doc_id, "node": seed.node,
                   "path": seed.path, "surface": matched}
        if not late and verdicts_mod.is_demoted(
                seed.doc_id, seed.node, doc_id, node):
            deferred.append((seed, doc_id, node, rel_kind, matched, ref_src))
            return False
        section = _mk(index, doc_id, node, public_kind[rel_kind],
                      matched + (" (후순위)" if late else ""), ref_src)
        if section is None:
            return False
        seen.add((doc_id, node))
        out.append(section)
        return True

    for seed in list(sections):
        view = index.docs.get(seed.doc_id)
        if view is None or seed.node not in view.by_id:
            continue
        root = relations_mod.article_root(view, seed.node)
        outgoing, incoming = relations_mod.incident(index, seed.doc_id, root)
        candidates = []
        for edge in outgoing:
            if edge.kind in {"EXCLUDES", "DELEGATES_TO", "INCORPORATES",
                             "USES_DEFINITION", "VIOLATION_SANCTIONED_BY", "DEEMS"}:
                candidates.append((edge, edge.dst_doc, edge.dst_node, False))
        for edge in incoming:
            if edge.kind in {"EXCLUDES", "RECEIVES_FROM", "EFFECTIVE_FOR",
                             "APPLIES_TO", "TRANSITION_FOR"}:
                candidates.append((edge, edge.src_doc, edge.src_node, True))
        candidates.sort(key=lambda item: (
            priority.get(item[0].kind, 99), item[1], str(item[2])))
        counts = {}
        exact_definition = False
        for edge, doc_id, node, reverse in candidates:
            if not enabled.get(edge.kind, False):
                continue
            limit = per_seed_cap.get(edge.kind, cap)
            if counts.get(edge.kind, 0) >= limit:
                continue
            tail = seed.path.split(" ▸ ")[-1] if seed.path else seed.doc
            surface = str(edge.props.get("surface") or edge.props.get("link")
                          or edge.props.get("term") or edge.label)
            if edge.kind == "EXCLUDES" and reverse:
                matched = f"{tail}의 적용을 배제·제한 — '{surface}'"
            elif edge.kind == "RECEIVES_FROM" and reverse:
                matched = f"{tail}의 위임을 받은 조문 — '{surface}'"
            elif edge.kind == "DELEGATES_TO":
                matched = f"{tail}의 위임 — '{surface}'"
            elif edge.kind == "USES_DEFINITION":
                matched = f"{tail}의 '{edge.props.get('term') or surface}' 정의"
                exact_definition = True
            elif edge.kind == "VIOLATION_SANCTIONED_BY":
                matched = f"{tail} 위반의 {edge.props.get('sanction_kind') or '제재'} — '{surface}'"
            else:
                matched = f"{tail}의 {edge.label} 관계 — '{surface}'"
            if push(seed, doc_id, node, edge.kind, matched):
                counts[edge.kind] = counts.get(edge.kind, 0) + 1

        if enabled["USES_DEFINITION"] and not exact_definition:
            for definition_node in tags_mod.governing_definitions(view, seed.node):
                push(seed, seed.doc_id, definition_node, "USES_DEFINITION",
                     f"{seed.path.split(' ▸ ')[-1]} 용어의 관할 정의 조 (검색 fallback)")

    for seed, doc_id, node, rel_kind, matched, _ref_src in deferred:
        push(seed, doc_id, node, rel_kind, matched, late=True)
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
    """열 수 있는 통합 관계 카드 — 본문 없이 관계·대상·원천만."""
    cards: list[dict] = []
    for s in frontier:
        v = index.docs.get(s.doc_id)
        if v is None or s.node not in v.by_id:
            continue
        tail = s.path.split(" ▸ ")[-1] if s.path else s.doc
        root = relations_mod.article_root(v, s.node)
        outgoing, incoming = relations_mod.incident(index, s.doc_id, root)
        candidates = [
            (edge, edge.dst_doc, edge.dst_node, False) for edge in outgoing
        ] + [
            (edge, edge.src_doc, edge.src_node, True) for edge in incoming
        ]
        for edge, dst_doc, dst_node, reverse in candidates:
            if (dst_doc, dst_node) in seen or len(cards) >= cap:
                continue
            tv = index.docs.get(dst_doc)
            if tv is None or dst_node not in tv.by_id:
                continue
            surface = str(edge.props.get("surface") or edge.props.get("link") or edge.label)
            cards.append({"id": len(cards), "rel": edge.label,
                          "from": tail, "direction": "incoming" if reverse else "outgoing",
                          "to": f"{tv.name} ▸ {tv.path(dst_node)}",
                          "표면형": surface,
                          "_dst": (dst_doc, dst_node), "_src": s})
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
