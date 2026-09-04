"""컨텍스트 조립과 답변 — 두 번의 LLM, 닫힌 목록의 인용.

원본(DELTAFlow RAG)의 답변 경로에서 두 가지를 그대로 가져온다.

**관련성 필터.** 검색은 글자 겹침으로 엉뚱한 것까지 끌어온다. LLM 이 질문의
뜻으로 걸러낸다 — 애매하면 남기고, 하나도 안 맞으면 빈 배열로 정직하게
비운다. 실패하면 원본을 그대로 쓴다(필터는 없어도 되는 단이지, 없으면
안 되는 단이 아니다).

**닫힌 목록 인용.** 원본이 쌓아 온 환각 방지 규칙의 핵심은 하나로 줄면
"근거는 시스템이 준 목록 안에서만" 이다. 여기서는 구조가 그걸 강제한다 —
컨텍스트 구역에 번호를 붙여 주고, 모델은 번호(refs)로만 인용한다. 링크·좌표는
모델이 아니라 코드가 번호를 되짚어 만든다. 모델이 URL 을 지어낼 자리가 없다.

LLM 이 없으면(키 없음·호출 실패) 검색까지만 내려간다 — 검색은 결정론이라
언제나 동작한다.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from lawrag.core.rag import switches, wikictx
from lawrag.core.rag.content_snapshot import (
    ArtifactProvenance,
    ContentSnapshot,
    ContentSnapshotError,
    artifact_provenance_receipt,
    current_content_snapshot,
)
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.index import Index
from lawrag.core.rag.search import SearchResult

log = logging.getLogger("lawrag.core.rag.answer")

# 컨텍스트 규모. CANDIDATES_MAX는 일반 조립·바닥·참조 확장이 공유하는 예산이지
# 최종 절대 상한이 아니다. vecfirst의 가산 진입과 문서 동반은 이 값을 넘을 수
# 있다. controls.audit가 그 구조 충돌을 상시 보고하고 평가 manifest가 실제 수를 잰다.
CANDIDATES_MAX = int(control_value("context.shared_sections_max"))
SECTION_CHARS = int(control_value("context.section_chars"))
SUMMARY_CHARS = int(control_value("context.filter_summary_chars"))
TERM_SECTIONS = int(control_value("context.term_sections_max"))
REF_SECTIONS = int(control_value("context.refs_per_section_max"))
FILTER_MIN = int(control_value("context.filter_min_sections"))
DISCARD_CHARS = int(control_value("context.discard_excerpt_chars"))


@dataclass
class Section:
    """답변의 근거 단위 — 문서의 한 구역, 좌표가 다 붙어 있다."""
    n: int                     # 컨텍스트 번호 (1부터) — 인용은 이 번호로만
    doc_id: str
    doc: str
    node: Optional[int]
    path: str                  # "제2장 ▸ 제19조 ▸ 제3항"
    page: Optional[int]
    kind: str                  # 어느 단이 데려왔나 — "제목"|"용어"|"본문"
    matched: str               # 매칭된 표면형
    text: str = ""
    block: Optional[int] = None
    # 참조 확장으로 끌려온 구역이면 — 어느 간선이 데려왔나. 판정 지문이
    # "이 간선이 잘못됐다"를 좌표로 찍으려면 출발점이 남아 있어야 한다.
    ref_src: Optional[dict] = None
    # 용어 진입이면 — 어느 용어(키)가 데려왔나. 실적(hits·misses)은 표면형이
    # 아니라 용어 행에 쌓여야 한다("PSV" 진입도 안전밸브의 실적).
    term_key: Optional[str] = None
    # 질의 스코프 밖에서 동반(배제·위임·준용·수임·정의·제재·참조·항해)으로
    # 끌려온 구역 — 진입은 스코프 안에서만 일어나므로 이 표식이 붙은 구역은
    # 반드시 ref_src 가 있다. 답변·출처에 "스코프 밖 동반" 으로 보인다.
    scope_out: bool = False
    # 계층 탐색에서 이 조·항을 선택할 때 함께 확정된 실제 DB 간선. LLM이 만든
    # 설명이 아니라 코드가 좌표로 고정한 E 행이다.
    edges: list[dict] = field(default_factory=list)
    # LegalClosure가 동일 원문에서 계산한 규범요건 span·법원성·시점 경고.
    # 답변 모델의 자유 요약이 아니라 좌표에 붙는 관측/검증 메타데이터다.
    legal_meta: dict = field(default_factory=dict)
    # 일반 근거와 분리된 선택 규정의 정의 부록. 독립 인용 번호를 부여하지 않고
    # 법정 용어를 일상어로 오해하지 않게 하는 해석 보조로만 렌더링한다.
    definition_context: list[dict] = field(default_factory=list)
    # The exact DatasetPackage artifact that supplied this document.  Keep the
    # domain object until a JSON boundary so hashes/coordinates cannot be
    # rewritten by intermediate presentation code.
    content_provenance: ArtifactProvenance | None = None

    @property
    def is_companion(self) -> bool:
        """동반으로 왔나(진입이 아니라) — 간선 출발점(ref_src)이 있으면 동반이다."""
        return self.ref_src is not None

    def cite(self) -> dict:
        d = {"n": self.n, "doc_id": self.doc_id, "doc": self.doc,
             "node": self.node, "path": self.path, "page": self.page,
             "block": self.block}
        if self.scope_out:
            d["scope_out"] = True
        if self.edges:
            d["edges"] = list(self.edges)
        provenance_value = self.content_provenance
        snapshot = current_content_snapshot()
        if snapshot is not None:
            expected = snapshot.provenance_for_document(self.doc_id)
            if provenance_value is not None and provenance_value != expected:
                raise ContentSnapshotError(
                    "citation artifact provenance disagrees with process snapshot")
            provenance_value = expected
        provenance = artifact_provenance_receipt(provenance_value)
        if provenance is not None:
            d["content_provenance"] = provenance
        return d


def _view_content_provenance(view) -> ArtifactProvenance | None:
    value = (getattr(view, "content_provenance", None)
             or getattr(view, "artifact_provenance", None))
    snapshot = current_content_snapshot()
    if snapshot is not None:
        expected = snapshot.provenance_for_document(view.doc_id)
        if value is not None and value != expected:
            raise ContentSnapshotError(
                "section artifact provenance disagrees with process snapshot")
        return expected
    return value


# ------------------------------------------------------------------ 스코프
def enforce_scope(index: Index, sections: list[Section]) -> tuple[list[Section], dict]:
    """질의 스코프의 마지막 보루 — 채널이 무엇을 놓쳤든 여기서 불변식이 선다.

    - 스코프 밖 **진입**(ref_src 없음 — 벡터·용어·본문·기억·회복·카드)은 버린다
    - 스코프 밖 **동반**(ref_src 있음 — 배제·위임·준용·수임·정의·제재·참조·항해)은
      남기되 scope_out 표식을 붙인다 (2026-08-19 결정: 동반은 밖으로 나가도 된다)
    반환 (구역들, {"dropped": [...], "out": n}) — 번호는 다시 매긴다."""
    if index.scope is None:
        return sections, {"dropped": [], "out": 0}
    kept: list[Section] = []
    dropped: list[dict] = []
    n_out = 0
    for s in sections:
        if index.in_scope(s.doc_id):
            kept.append(s)
            continue
        if s.is_companion:
            s.scope_out = True
            n_out += 1
            kept.append(s)
        else:
            dropped.append({"doc_id": s.doc_id, "doc": s.doc, "node": s.node,
                            "kind": s.kind, "path": s.path})
    for i, s in enumerate(kept, start=1):
        s.n = i
    return kept, {"dropped": dropped, "out": n_out}


# ------------------------------------------------------------------ 조립
def assemble(index: Index, result: SearchResult,
             seeds: Optional[list] = None) -> list[Section]:
    """히트 → 구역. 같은 (문서, 마디) 는 한 번만 싣는다 — 용어와 제목이 같은
    자리를 가리키면 그것은 근거 하나지 둘이 아니다.

    seeds 는 검색 없이 여는 좌표(질문 기억 — promote.direct_hits)다. 사람이
    승인한 연결이라 히트보다 앞에 앉고 진입 제외를 받지 않는다. 히트는
    **진입 제외**(검색무관 판정을 사람이 승인한 좌표)를 거른다 — 벡터 우선
    경로(vecfirst)와 같은 규율이다. 참조 확장으로는 여전히 온다."""
    from lawrag.core.rag import verdicts as verdicts_mod

    out: list[Section] = []
    seen: set[tuple] = set()

    def push(doc_id: str, node_id: Optional[int], kind: str, matched: str,
             block: Optional[int] = None, page: Optional[int] = None,
             term_key: Optional[str] = None, entry: bool = True) -> None:
        v = index.docs.get(doc_id)
        if v is None:
            return
        key = (doc_id, node_id)
        if key in seen:
            return
        if entry and verdicts_mod.is_entry_blocked(doc_id, node_id):
            return
        seen.add(key)
        n = v.by_id.get(node_id)
        if page is None and block is not None:
            page = (v.block_by_idx.get(block) or {}).get("page")
        out.append(Section(
            n=0, doc_id=doc_id, doc=v.name, node=node_id,
            path=v.path(node_id) or v.name,
            page=page if page is not None else (n or {}).get("page"),
            kind=kind, matched=matched, block=block, term_key=term_key,
            text=v.section_outline(n, cap=SECTION_CHARS) if n else "",
            content_provenance=_view_content_provenance(v)))

    for c in seeds or []:
        if not index.in_scope(c.get("doc_id", "")):    # 기억도 진입 — 스코프 밖은 안 연다
            continue
        push(c.get("doc_id", ""), c.get("node"), c.get("via") or "질문 기억",
             (c.get("why") or "")[:80], entry=False)

    for h in result.hits:
        if len(out) >= CANDIDATES_MAX:
            break
        if h.kind == "용어":
            # 출현 좌표는 glossary 가 이미 훑어 뒀다. 제목 출현(그 구역이 그 말을
            # **다루는** 자리)을 먼저, 본문 언급을 나중에.
            occ = sorted(h.occurrences,
                         key=lambda o: 0 if o.get("via") == "제목" else 1)
            tkey = h.target.partition(":")[2] if h.target.startswith("term:") else None
            for o in occ[:TERM_SECTIONS]:
                push(o.get("doc_id", ""), o.get("node"), "용어", h.value,
                     block=o.get("block"), page=o.get("page"), term_key=tkey)
        else:
            # 값만 남기면 "무엇이 걸렸나"는 알아도 "어떻게 걸렸나"(정확·부분·
            # 하이브리드)를 모른다 — 검수는 그 둘이 다 있어야 선다.
            push(h.doc_id, h.node, h.kind,
                 f"{h.match} '{h.value}'" if h.match else h.value,
                 block=h.block)

    out = expand_refs(index, out[:CANDIDATES_MAX])
    for i, s in enumerate(out, start=1):
        s.n = i
    return out


def sections_from_coords(index: Index, coords: list[dict]) -> list[Section]:
    """회복 루프의 좌표들 → 구역. via(어느 단이 데려왔나)가 matched 자리에 남는다 —
    조용히 정확 매칭인 척하지 않는다."""
    out: list[Section] = []
    seen: set[tuple] = set()
    for c in coords:
        v = index.docs.get(c.get("doc_id"))
        node_id = c.get("node")
        if v is None or node_id is None or (c["doc_id"], node_id) in seen:
            continue
        if not index.in_scope(c["doc_id"]):         # 회복 착지도 진입 — 스코프 밖은 버린다
            continue
        seen.add((c["doc_id"], node_id))
        n = v.by_id.get(node_id)
        out.append(Section(
            n=0, doc_id=c["doc_id"], doc=v.name, node=node_id,
            path=v.path(node_id) or v.name, page=(n or {}).get("page"),
            kind=f"탐색({c.get('via', '')})", matched=c.get("why", "")[:80],
            text=v.section_outline(n, cap=SECTION_CHARS) if n else "",
            content_provenance=_view_content_provenance(v)))
        if len(out) >= CANDIDATES_MAX:
            break
    out = expand_refs(index, out)
    for i, s in enumerate(out, start=1):
        s.n = i
    return out


def _in_subtree(v, node_id, root_id) -> bool:
    """node_id 가 root_id 자신 또는 그 자손인가 — 참조 확장의 중복 가드."""
    seen: set = set()
    while node_id is not None and node_id not in seen:
        if node_id == root_id:
            return True
        seen.add(node_id)
        node_id = (v.by_id.get(node_id) or {}).get("parent")
    return False


def expand_refs(index: Index, sections: list[Section],
                cap: int = CANDIDATES_MAX) -> list[Section]:
    """구역 본문의 상호참조("제4조를 참고한다")가 가리키는 구역을 뒤에 잇는다.

    용어가 구역을 끌어오는 것과 같은 걸음이다 — 회수된 구역의 연결점을 타고
    근거를 같이 든다. 간선은 참조가 쓰인 **블록**의 좌표를 다므로, 구역의
    범위(span) 안에서 난 참조는 깊은 자식이 쓴 것이라도 여기서 잡힌다. 문서
    사이 간선(이름 대조·판정 링크)도 같은 걸음으로 탄다.
    원 히트를 밀어내지 않는다 — 빈자리만 채운다."""
    from lawrag.core.rag import verdicts as verdicts_mod   # 지연 — 순환 회피

    out = list(sections)
    seen = {(s.doc_id, s.node) for s in sections}
    for s in sections:
        if len(out) >= cap:
            break
        v = index.docs.get(s.doc_id)
        n = v.by_id.get(s.node) if v else None
        if v is None or n is None:
            continue
        span = n.get("span") or [0, 0]
        added = 0
        near = [(s.doc_id, e) for e in index.ref_edges().get(s.doc_id, [])]
        far = [(e["dst_doc"], e) for e in index.cross_from(s.doc_id)]
        # 후순위 간선은 **뒤로 민다**(빼지 않는다) — "연결은 옳은데 이번 질문엔
        # 안 맞았다"는 판정의 처리다. 자리가 남으면 여전히 온다.
        cand = sorted(near + far,
                      key=lambda p: verdicts_mod.is_demoted(
                          s.doc_id, s.node, p[0], p[1].get("dst")))
        for dst_doc, e in cand:
            if added >= REF_SECTIONS or len(out) >= cap:
                break
            blk = e.get("block")
            if blk is None or not (span[0] <= blk < max(span[1], span[0] + 1)):
                continue
            dst = e["dst"]
            key = (dst_doc, dst)
            tv = index.docs.get(dst_doc)
            if tv is None or key in seen:
                continue
            # 이 구역 자신의 안이면 — 본문에 이미 들어 있다
            if dst_doc == s.doc_id and _in_subtree(v, dst, s.node):
                continue
            # 사람이 승인한 억제 간선 — 판정 지문이 쌓여 확정된 "잘못된 참조"는
            # 다시 끌고 오지 않는다 (규칙이 못 가른 것을 판정 루프가 가린다).
            if verdicts_mod.is_suppressed(s.doc_id, s.node, dst_doc, dst):
                continue
            seen.add(key)
            dn = tv.by_id.get(dst)
            src_tail = s.path.split(" ▸ ")[-1] if s.path else s.doc
            out.append(Section(
                n=0, doc_id=dst_doc, doc=tv.name, node=dst,
                path=tv.path(dst) or tv.name, page=(dn or {}).get("page"),
                kind="참조", matched=f"{src_tail} → {e['surface']}",
                text=tv.section_text(dn, cap=SECTION_CHARS) if dn else "",
                ref_src={"doc_id": s.doc_id, "node": s.node,
                         "path": s.path, "surface": e["surface"]},
                content_provenance=_view_content_provenance(tv)))
            added += 1
    return out


# ------------------------------------------------------------------ 착지 교정
# 문서 안 간선의 18%(실측 2026-08-10: 사슬 참조 4,328 중 768)는 "제2조제3항"을
# 가리키고도 조에 머문다 — 그 가지가 구조에 없거나 라벨이 결정론 문법 밖이라서.
# 결정론이 멈춘 자리만 LLM 에 넘긴다: 착지의 자손(닫힌 후보) 중에서 표면형이
# 가리키는 가지를 고르게 하고, 고르면 이번 답변은 그 구역을 근거로 쓴다.
# 제안은 기록으로 남고(verdicts.log_fixes) 간선 자체는 사람이 승인해야 옮겨
# 앉는다(edge_rules.json redirect) — 제안자/검증자 분리 그대로다.
REPAIR_MAX = int(control_value("context.repair_refs_max"))
REPAIR_KIDS = int(control_value("context.repair_children_max"))

REPAIR_SYSTEM = (
    "너는 문서 상호참조의 '착지 검사원'이다. 본문이 \"제2조제3항\"처럼 깊은 "
    "가지를 가리켰는데 구역 계층에서는 조(윗단)까지만 내려간 간선들을 받는다.\n"
    "각 항목에 착지 구역의 자손 후보 목록(id·라벨·첫머리)이 있다. 표면형이 "
    "가리키는 가지(항·호·목 번호)와 실제로 맞는 후보가 있으면 그 id 를 고른다.\n"
    "  - 번호 표기가 달라도 뜻이 같으면 맞다 — 제3항이 ③ 이나 (3) 으로 적혀 "
    "있을 수 있다.\n"
    "  - 맞는 후보가 없으면 node 를 null 로 둔다 — 억지로 고르지 마라. 없는 "
    "것은 없는 것이다(그 가지가 구조에 안 잡혔을 수 있다).\n"
    '반드시 이 JSON 만 출력: {"fixes": [{"idx": <항목 번호>, '
    '"node": <후보 id 또는 null>, "reason": "한 줄 근거"}]}'
)

REPAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "fixes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "idx": {"type": "integer"},
                "node": {"type": ["integer", "null"]},
                "reason": {"type": "string"},
            },
            "required": ["idx", "node", "reason"],
            "additionalProperties": False}},
    },
    "required": ["fixes"],
    "additionalProperties": False,
}


def _descendants(v, children: dict, root, depth: int = 2) -> list:
    """root 의 자손 (id, 라벨, 첫머리) — 닫힌 후보 목록의 재료."""
    out, frontier = [], [root]
    for _ in range(depth):
        nxt = []
        for cur in frontier:
            for kid in children.get(cur, []):
                n = v.by_id.get(kid) or {}
                label = ((n.get("surface") or "").strip()
                         or (n.get("title") or "").strip())
                blk = v.block_by_idx.get((n.get("span") or [0, 0])[0]) or {}
                out.append({"id": kid, "라벨": label,
                            "첫머리": (blk.get("text") or "")[:60]})
                nxt.append(kid)
        frontier = nxt
    return out[:REPAIR_KIDS]


def repair_landings(llm, index: Index, sections: list[Section]) -> list[dict]:
    """참조로 끌려온 구역 중 사슬이 덜 내려간 착지를 LLM 이 자손 후보에서
    고쳐 앉힌다. 고친 구역은 즉시 이번 답변의 근거가 되고(본문 교체),
    교정 제안 목록을 돌려준다 — 적재와 승인은 호출부·백로그의 몫이다."""
    if llm is None:
        return []
    from lawrag.core.rag import refs as refs_mod              # 지연 — 순환 회피

    items, flagged = [], []
    kids_cache: dict = {}
    for s in sections:
        if s.kind != "참조" or not s.ref_src or s.node is None:
            continue
        surface = s.ref_src.get("surface") or ""
        found = refs_mod.find(surface)
        chain = found[0].chain if found else ()
        if not chain:
            continue                                   # 깊은 가지를 안 가리켰다
        v = index.docs.get(s.doc_id)
        if v is None:
            continue
        want = chain[-1]
        sk = refs_mod._sub_key(v, s.node)
        if sk and (want[0] is None or sk[0] == want[0]) and sk[1] == want[1]:
            continue                                   # 이미 끝까지 내려갔다
        if s.doc_id not in kids_cache:
            kids_cache[s.doc_id] = refs_mod._children(v)
        cands = _descendants(v, kids_cache[s.doc_id], s.node)
        if not cands:
            continue                                   # 내려갈 자손이 없다
        items.append({"idx": len(items), "표면형": surface,
                      "착지": s.path, "후보": cands})
        flagged.append((s, surface, {c["id"] for c in cands}))
        if len(items) >= REPAIR_MAX:
            break
    if not items:
        return []

    out = llm.structured("rag.repair", REPAIR_SYSTEM,
                         json.dumps({"items": items}, ensure_ascii=False),
                         REPAIR_SCHEMA, max_tokens=1500, effort="low")
    if out is None:
        return []

    fixes: list[dict] = []
    for f in out.get("fixes", []):
        i, node = f.get("idx"), f.get("node")
        if not isinstance(i, int) or not (0 <= i < len(flagged)) or node is None:
            continue
        s, surface, valid = flagged[i]
        if node not in valid:
            continue                                   # 닫힌 후보 밖 — 버린다
        v = index.docs[s.doc_id]
        nd = v.by_id.get(node)
        if nd is None:
            continue
        old, old_path = s.node, s.path
        s.node, s.path = node, v.path(node) or s.path
        s.page = nd.get("page") or s.page
        s.text = v.section_text(nd, cap=SECTION_CHARS)
        s.kind = "참조(교정)"
        rs = s.ref_src or {}
        fixes.append({"n": s.n,
                      "src_doc": rs.get("doc_id"), "src": rs.get("node"),
                      "src_path": rs.get("path", ""), "surface": surface,
                      "dst_doc": s.doc_id, "dst": old, "dst_path": old_path,
                      "new_dst": node, "new_dst_path": s.path,
                      "reason": (f.get("reason") or "")[:200]})
    return fixes


# ------------------------------------------------------------------ 필터
FILTER_SYSTEM = (
    "너는 문서 검색의 '관련성 필터'다. 검색이 회수한 구역 목록(각 idx)을 받는다. "
    "검색은 글자 겹침으로 엉뚱한 것까지 끌어올 수 있다. 사용자 질문이 가리키는 "
    "대상과 **실제로 맞는 구역만** 남기고 무관한 구역은 버린다.\n"
    "  - 요약을 **뜻으로** 판단하라 — 표면형이 겹치는가가 아니라, 그 구역에 질문이 "
    "묻는 내용(값·규정·설명)이 실릴 만한가다.\n"
    "  - 애매하면 남긴다(과도한 제거 금지). 맥락상 명백히 다른 대상만 버린다.\n"
    "  - 질문에 맞는 구역이 하나도 없으면 keep 을 빈 배열로 둔다(정직 — 억지로 "
    "남기지 말 것).\n"
    '반드시 이 JSON 만 출력: {"keep": [<idx>, ...], "reason": "한 줄 근거"}'
)

FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "keep": {"type": "array", "items": {"type": "integer"}},
        "reason": {"type": "string"},
    },
    "required": ["keep", "reason"],
    "additionalProperties": False,
}


def filter_sections(llm, question: str, sections: list[Section]) -> tuple[list[Section], dict]:
    """LLM 이 뜻으로 거른다. 실패는 막지 않는다 — 원본 유지가 폴백이다."""
    meta = {"in": len(sections), "out": len(sections), "applied": False, "reason": ""}
    if llm is None or len(sections) < FILTER_MIN:
        return sections, meta
    view = [{"idx": s.n, "doc": s.doc[:50], "path": s.path[:80], "kind": s.kind,
             "값": s.matched[:50], "요약": s.text[:SUMMARY_CHARS]}
            for s in sections]
    user = (f"[질문]\n{question}\n\n[검색 회수 구역]\n"
            f"{json.dumps(view, ensure_ascii=False)}")
    out = llm.structured("rag.filter", FILTER_SYSTEM, user, FILTER_SCHEMA,
                         max_tokens=2000, effort="low")
    if out is None:
        log.warning("관련성 필터 실패 — 회수 원본 %d구역을 그대로 쓴다", len(sections))
        return sections, meta
    valid = {s.n for s in sections}
    keep = [i for i in out.get("keep", []) if isinstance(i, int) and i in valid]
    kept = [s for s in sections if s.n in keep]
    # 버린 것도 남긴다 — "왜 이 조문이 답에 없나"의 절반은 여기 있다. 버려진
    # 구역은 context 에 실리지 않으므로 이 자리에 안 적으면 영영 안 보인다.
    meta.update({"out": len(kept), "applied": True,
                 "reason": (out.get("reason") or "")[:200],
                 "버림": [{"n": s.n, "doc": s.doc, "path": s.path, "kind": s.kind,
                           "matched": s.matched,
                           "발췌": (s.text or "")[:DISCARD_CHARS]}
                          for s in sections if s.n not in keep]})
    log.info("관련성 필터 — %d → %d구역%s", meta["in"], meta["out"],
             f" ({meta['reason']})" if meta["reason"] else "")
    return kept, meta


# ------------------------------------------------------------------ 답변
ANSWER_SYSTEM = (
    "너는 문서 질의응답 보조자다. [컨텍스트]는 구조화된 문서들에서 이번 질의로 "
    "회수된 구역들이다 — 이것**만** 근거로 한국어로 답한다.\n"
    "지켜야 할 규칙(위반은 곧 오답):\n"
    "① 수치·조항·명칭은 컨텍스트에 실제로 있을 때만 인용한다. 없으면 일반 지식으로 "
    "채우지 말고 '회수된 자료에는 없다'고만 밝힌다. '자료에 없다'고 말한 뒤 일반 "
    "수치를 이어 붙이지 마라(자기모순).\n"
    "② 컨텍스트가 부족해도 '문서에 없다'고 단정하지 마라 — 그것은 '이번 검색으로는 "
    "회수되지 않았다'는 뜻일 뿐이다.\n"
    "③ 회수된 구역은 검색 표본이지 전체가 아니다 — '총 N개뿐' 같은 전수 단정 금지.\n"
    "④ 출처 목록은 코드가 이번 최종 컨텍스트의 실제 좌표에서 확정한다. refs나 "
    "문서 좌표를 출력하지 말고, 답변 문장만 작성한다. 컨텍스트 밖의 문서·조항을 "
    "새로 만들어 인용하지 마라.\n"
    "⑤ 결론을 먼저 1~3문장으로, 그 뒤에 근거 설명. 컨텍스트에 답이 없으면 "
    "answerable 을 false 로 두고, 어떤 자료가 있으면 답할 수 있는지만 안내한다.\n"
    "⑥ [해석 맥락 — 지식 위키]가 있으면 그것은 축적된 해석 지식(법제처 해석례 "
    "요약 등)에서 온 **배경**이다 — 답의 방향(문턱이 좁은지, 준용이 어디까지 "
    "가는지)을 잡는 데 쓰되, refs 에는 넣지 말고 수치·조항 인용의 근거로도 쓰지 "
    "마라. 위키와 [컨텍스트]의 조문이 어긋나면 조문이 이긴다."
)
# 판정(어느 구역이 잘못 끌려왔나)은 **이 콜에 없다.** 사용자를 기다리게 하는 콜에서
# 판정까지 하면 구조화 출력이 그 배열을 다 만들 때까지 답이 나오지 않는다 —
# 답변 지연에 감사 비용이 얹힌다. 감사는 답을 보낸 **뒤** 백그라운드로 돈다(audit.py).

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "answerable": {"type": "boolean"},
    },
    "required": ["answer", "answerable"],
    "additionalProperties": False,
}

LEGAL_COMPILED_ANSWER_SYSTEM = ANSWER_SYSTEM + (
    "\n⑦ [법률 evidence compiler]가 있으면 claim_id와 evidence_id는 검증된 원문 "
    "span에 결속된 닫힌 목록이다. 답의 각 핵심 법률 명제는 그 목록의 claim에만 "
    "근거하고, 사용한 evidence_id를 evidence_ids에 낸다. 목록 밖 ID를 만들지 마라."
    "\n⑧ answer_mode가 DIRECT_RULE일 때만 DIRECT 결론을 허용한다. "
    "CONDITIONAL_APPLICATION이면 추가 사실과 조건을 명시한 조건부 답만 하며, "
    "INSUFFICIENT이면 가능/불가능을 단정하지 않고 부족한 규범이나 사실을 밝힌다."
)

LEGAL_COMPILED_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "answerable": {"type": "boolean"},
        "conclusion_strength": {
            "type": "string",
            "enum": ["DIRECT", "CONDITIONAL", "INSUFFICIENT"],
        },
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "answer", "answerable", "conclusion_strength", "evidence_ids"
    ],
    "additionalProperties": False,
}

ISSUE_ATOMIC_ANSWER_SYSTEM = LEGAL_COMPILED_ANSWER_SYSTEM + (
    "\n⑨ schema_version이 issue-role-atomic-entailment v3이면 issues의 모든 "
    "issue_id를 issue_results에 정확히 한 번씩 답한다. 각 쟁점은 그 issue_id에 "
    "연결된 unit의 evidence_id만 사용한다. missing_requirements가 남은 쟁점은 "
    "DIRECT로 단정하지 말고 unresolved_requirements에 그대로 낸다."
    "\n⑩ unit의 quote는 원문 근거이지 자동으로 포섭 결론이 된 것이 아니다. "
    "DIRECT_TEXT entailment가 없는 요건을 추측으로 채우거나 새 조건·예외를 만들지 마라."
)

ISSUE_ATOMIC_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "answerable": {"type": "boolean"},
        "conclusion_strength": {
            "type": "string",
            "enum": ["DIRECT", "CONDITIONAL", "INSUFFICIENT"],
        },
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "issue_results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string"},
                    "conclusion": {"type": "string"},
                    "conclusion_strength": {
                        "type": "string",
                        "enum": ["DIRECT", "CONDITIONAL", "INSUFFICIENT"],
                    },
                    "evidence_ids": {
                        "type": "array", "items": {"type": "string"}
                    },
                    "unresolved_requirements": {
                        "type": "array", "items": {"type": "string"}
                    },
                },
                "required": [
                    "issue_id", "conclusion", "conclusion_strength",
                    "evidence_ids", "unresolved_requirements",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "answer", "answerable", "conclusion_strength", "evidence_ids",
        "issue_results",
    ],
    "additionalProperties": False,
}

SOFT_ATOMIC_ANSWER_SYSTEM = ANSWER_SYSTEM + (
    "\n⑦ [법률 evidence compiler]의 claims는 검증된 원문 span과 evidence_id의 "
    "닫힌 목록이다. 핵심 법률 명제에 사용한 evidence_id를 evidence_ids에 내고 목록 밖 "
    "ID를 만들지 마라. 결론 강도는 원문과 질문의 사실관계에 따라 직접 판단한다."
    "\n⑧ schema_version이 integrated-atomic-claim v4이면 issues는 빠뜨리기 쉬운 "
    "쟁점의 soft checklist다. 근거가 있는 쟁점은 모두 답하되 issue_id나 requirement ID를 "
    "출력하지 않는다. issues가 법률 결론을 미리 정하거나 답변을 차단하지 않는다."
    "\n⑨ claims의 proposition은 원문 exact quote다. 핵심 법률 명제에 사용한 조문의 "
    "evidence_id만 evidence_ids에 내고, 닫힌 claims 밖 ID를 만들지 마라. CONTEXT claim은 "
    "원문 탐색 보조이며 그 자체를 요약된 법률효과로 오해하지 마라."
)


def _legal_compilation(sections: list[Section]) -> dict:
    """Return the one immutable compiler packet attached to selected evidence."""

    for section in sections:
        packet = (section.legal_meta or {}).get("legal_compilation")
        if isinstance(packet, dict) and packet.get("schema_version"):
            return packet
    return {}


def _context_text(sections: list[Section]) -> str:
    """머리에 **경위**를 단다 — 참조로 끌려온 구역은 "어느 표면형이 어디서
    이리로 보냈는지"가 보여야 판정(오참조)이 좌표를 근거로 설 수 있다.
    이게 없으면 모델은 주제만 보고 "무관하니 오참조"라고 뭉갠다(실측)."""
    parts = []
    packet = _legal_compilation(sections)
    if packet:
        compiler_view = {
            "answer_mode": packet.get("answer_mode"),
            "direct_rule_answer_allowed": bool(
                packet.get("direct_rule_answer_allowed")
            ),
            "claims": packet.get("claims") or [],
            "coverage": packet.get("coverage") or [],
            "missing": packet.get("missing") or [],
            "selected_scope_ids": packet.get("selected_scope_ids") or [],
            "required_elements": packet.get("required_elements") or [],
            "decision_elements": packet.get("decision_elements") or [],
            "missing_elements": packet.get("missing_elements") or [],
            "protected_evidence_ids": packet.get("protected_evidence_ids") or [],
            "issues": packet.get("issues") or [],
            "units": packet.get("units") or [],
            "entailments": packet.get("entailments") or [],
            "missing_requirements": packet.get("missing_requirements") or [],
            "quota": packet.get("quota") or {},
            "reason": packet.get("reason") or "",
        }
        parts.append(
            "[법률 evidence compiler — 검증 span에 결속된 닫힌 명제]\n"
            + json.dumps(compiler_view, ensure_ascii=False)
        )
    for s in sections:
        head = f"[{s.n}] {s.doc} ▸ {s.path}" + (f" (p.{s.page})" if s.page else "")
        if s.kind.startswith("참조") and s.ref_src:
            head += (f"  ← 참조로 옴: 「{s.ref_src.get('path', '')}」 본문의 "
                     f"'{s.ref_src.get('surface', '')}'")
        if s.scope_out:
            # 질문이 정한 문서 범위 밖 — 간선(배제·위임·준용…)이 데려온 것이다.
            # 모델이 이것을 "범위 안 조문" 처럼 근거의 중심에 세우지 않게 알린다.
            head += "  ⟨질의 범위 밖 문서 — 간선으로 동반됨⟩"
        research_meta = (s.legal_meta or {}).get("integrated_research") or {}
        if research_meta.get("scope_id"):
            head += f"  ⟨법률 scope: {research_meta['scope_id']}⟩"
        edge_block = ""
        if s.edges:
            edge_lines = []
            for edge in s.edges:
                surface = f" '{edge.get('surface')}'" if edge.get("surface") else ""
                edge_lines.append(
                    f"{edge.get('id', 'E?')}: {edge.get('from')} "
                    f"--{edge.get('relation', '인용')}{surface}--> {edge.get('to')}")
            edge_block = "\n[함께 선택된 간선]\n" + "\n".join(edge_lines)
        parts.append(f"{head}{edge_block}\n{s.text}")
    return "\n\n".join(parts)


def _definition_context_text(sections: list[Section]) -> str:
    """선택 규정의 필요한 정의만 별도 비인용 부록으로 정리한다."""
    rows, seen = [], set()
    for section in sections:
        for row in section.definition_context:
            key = (row.get("doc_id"), row.get("node"), row.get("block"),
                   row.get("term"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    if not rows:
        return ""
    parts = [
        "\n\n[선택 규정의 용어 정의 — 해석 보조, 독립 인용 근거 아님]",
        "아래 정의는 선택된 규정의 원문 정의다. 결론·의무·예외는 위 [컨텍스트]의 "
        "인용 가능한 조문에서 판단하고, 이 부록에는 별도 인용번호를 만들지 마라.",
    ]
    current_doc = None
    for row in rows:
        if row.get("doc") != current_doc:
            current_doc = row.get("doc")
            parts.append(f"\n《{current_doc}》")
        parts.append(
            f"- 용어: {row.get('term', '')}\n"
            f"  위치: {row.get('path', '')}\n"
            f"  정의 원문: {row.get('quote', '')}")
    return "\n".join(parts)


@dataclass
class Answer:
    answer: str
    refs: list = field(default_factory=list)      # Section.cite() 목록
    answerable: bool = False
    error: str = ""
    # 판정 지문은 여기 없다 — 답을 보낸 뒤 `core.rag.audit` 이 백그라운드에서 남긴다.
    # (호환을 위해 자리는 둔다: 옛 호출자가 `.discards` 를 읽어도 빈 목록이다.)
    discards: list = field(default_factory=list)
    # 이번 합성에 배경으로 들어간 위키 아티클 [{slug, title, why}] — 관측용.
    wiki: list = field(default_factory=list)
    # ADR-0115 compiler profile only. Legacy callers see stable empty defaults.
    conclusion_strength: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    issue_results: list[dict] = field(default_factory=list)
    gate_violation: bool = False
    content_snapshot: ContentSnapshot | None = None


def synthesize(llm, question: str, sections: list[Section],
               spots: list[dict] | None = None) -> Answer:
    """구역들로 답을 만든다. ``refs``는 모델 출력이 아니라 이 호출에 확정된
    구역 좌표 전체에서 결정론으로 만든다. spots 는 검색 전에 이미 골라진 쟁점 카드
    (wikictx.spot) — 위키 맥락 블록의 앞자리에 같이 끼운다."""
    content_snapshot = current_content_snapshot()
    if not sections:
        # 원본 §0-0 ② — 부재 단정이 아니라 회수 실패를 말한다.
        return Answer(answer="이번 검색으로는 관련 구역이 회수되지 않았습니다. "
                             "다른 표현으로 다시 묻거나, 용어집에 용어를 더해 두면 "
                             "다음 검색이 닿을 수 있습니다.",
                      answerable=False, content_snapshot=content_snapshot)
    if llm is None:
        return Answer(answer="", error="LLM 없음 — ANTHROPIC_API_KEY(개발망) 또는 "
                                       "GENOS_LLM_URL(GenOS)을 설정해야 답변 합성이 "
                                       "동작합니다. 검색(/search)은 그대로 쓸 수 있습니다.",
                      content_snapshot=content_snapshot)
    # 받은 것을 전부 본다 — 규모는 조립 단계(CANDIDATES_MAX)가 이미 지켰다.
    # 여기서 또 자르면 사용자에게 보여준 컨텍스트와 모델이 본 컨텍스트가 갈린다.
    use = sections
    t0 = time.perf_counter()
    # 위키 맥락 — "어떻게 읽는가"의 배경 (wikictx.py 머리). 조문이 근거,
    # 위키는 방향이다 (ANSWER_SYSTEM ⑥). 끄면 기존 프롬프트 그대로다.
    # 순서: 쟁점 카드(검색을 이끈 카드) → 방법(회수 결과의 성격 — 단서·제재·
    # 정의 동반이 깨운다) → 일반 아티클(문서명·낱말). 셋 다 코드 결정론이다.
    picks = list(spots or [])
    if switches.is_on("wiki_context"):
        have = {p["slug"] for p in picks}
        for p in wikictx.methods_for(use):
            if p["slug"] not in have:
                picks.append(p)
                have.add(p["slug"])
        picks += [p for p in wikictx.pick(question, {s.doc for s in use})
                  if p["slug"] not in have]
    user = (f"[질문]\n{question}\n\n[컨텍스트]\n{_context_text(use)}"
            + _definition_context_text(use)
            + wikictx.block(picks))
    compilation = _legal_compilation(use)
    schema_version = str(compilation.get("schema_version") or "")
    atomic_v3 = schema_version.startswith(
        "issue-role-atomic-entailment"
    )
    atomic_v4 = schema_version.startswith("integrated-atomic-claim")
    answer_system = (
        ISSUE_ATOMIC_ANSWER_SYSTEM if atomic_v3 else
        SOFT_ATOMIC_ANSWER_SYSTEM if atomic_v4 else
        LEGAL_COMPILED_ANSWER_SYSTEM if compilation else ANSWER_SYSTEM
    )
    answer_schema = (
        ISSUE_ATOMIC_ANSWER_SCHEMA if atomic_v3 else
        LEGAL_COMPILED_ANSWER_SCHEMA if compilation else ANSWER_SCHEMA
    )
    out = llm.structured("rag.answer", answer_system, user, answer_schema,
                         max_tokens=4000, effort="high")
    if out is None:
        err = llm.log[-1].error if llm.log else "알 수 없는 실패"
        log.error("답변 합성 실패 — 구역 %d, %.0fms: %s",
                  len(use), (time.perf_counter() - t0) * 1000, err)
        return Answer(answer="", error=f"답변 합성 실패: {err}",
                      content_snapshot=content_snapshot)
    gate_violation = False
    if compilation:
        allowed_ids = set(compilation.get("selected_evidence_ids") or ())
        used_ids = out.get("evidence_ids") or ()
        invalid_ids = sorted({str(value) for value in used_ids} - allowed_ids)
        mode = str(compilation.get("answer_mode") or "INSUFFICIENT")
        strength = str(out.get("conclusion_strength") or "INSUFFICIENT")
        gate_violation = bool(invalid_ids)
        if atomic_v4:
            gate_violation = gate_violation or (
                bool(out.get("answerable")) and not used_ids
            )
        else:
            gate_violation = gate_violation or (
                strength == "DIRECT" and mode != "DIRECT_RULE"
            )
            gate_violation = gate_violation or (
                strength == "CONDITIONAL" and mode == "INSUFFICIENT"
            )
            gate_violation = gate_violation or (
                bool(out.get("answerable")) and mode == "INSUFFICIENT"
            )
            gate_violation = gate_violation or (
                bool(out.get("answerable")) and not used_ids
            )
        if atomic_v3:
            expected_issues = {
                str(row.get("issue_id") or "")
                for row in compilation.get("issues") or ()
                if str(row.get("issue_id") or "")
            }
            issue_rows = out.get("issue_results") or ()
            returned_issues = [str(row.get("issue_id") or "") for row in issue_rows]
            gate_violation = gate_violation or set(returned_issues) != expected_issues
            gate_violation = gate_violation or len(returned_issues) != len(set(returned_issues))
            unit_ids_by_issue: dict[str, set[str]] = {}
            for unit in compilation.get("units") or ():
                for issue_id in unit.get("issue_ids") or ():
                    unit_ids_by_issue.setdefault(str(issue_id), set()).add(
                        str(unit.get("evidence_id") or "")
                    )
            missing_requirements = set(
                str(value) for value in compilation.get("missing_requirements") or ()
            )
            requirement_issue = {
                str(requirement.get("requirement_id") or ""): str(issue.get("issue_id") or "")
                for issue in compilation.get("issues") or ()
                for requirement in issue.get("requirements") or ()
            }
            for issue_row in issue_rows:
                issue_id = str(issue_row.get("issue_id") or "")
                issue_evidence = {
                    str(value) for value in issue_row.get("evidence_ids") or ()
                }
                issue_missing = {
                    requirement for requirement in missing_requirements
                    if requirement_issue.get(requirement) == issue_id
                }
                gate_violation = gate_violation or not issue_evidence.issubset(
                    unit_ids_by_issue.get(issue_id, set())
                )
                gate_violation = gate_violation or (
                    str(issue_row.get("conclusion_strength") or "") == "DIRECT"
                    and bool(issue_missing)
                )
                gate_violation = gate_violation or not issue_missing.issubset({
                    str(value) for value in issue_row.get("unresolved_requirements") or ()
                })
        if gate_violation:
            missing = [
                str(row.get("coverage_key") or "")
                for row in compilation.get("missing") or ()
                if str(row.get("coverage_key") or "").strip()
            ]
            suffix = f" 추가 확인 항목: {', '.join(missing[:5])}." if missing else ""
            out = {
                "answer": (
                    "현재 회수·검증된 근거만으로는 이 질문에 대한 법률 결론을 "
                    f"단정할 수 없습니다.{suffix}"
                ),
                "answerable": False,
                "conclusion_strength": "INSUFFICIENT",
                "evidence_ids": [],
                "issue_results": [],
            }
    refs = [section.cite() for section in use]
    log.info("답변 합성 — 구역 %d, 인용 %d, answerable=%s (%.0fms)",
             len(use), len(refs), bool(out.get("answerable")),
             (time.perf_counter() - t0) * 1000)
    return Answer(answer=out.get("answer", ""), refs=refs,
                  answerable=bool(out.get("answerable")),
                  wiki=[{"slug": p["slug"], "title": p["title"],
                         "why": p["why"]} for p in picks],
                  conclusion_strength=str(out.get("conclusion_strength") or ""),
                  evidence_ids=[str(value) for value in out.get("evidence_ids") or ()],
                  issue_results=[dict(value) for value in out.get("issue_results") or ()],
                  gate_violation=gate_violation,
                  content_snapshot=content_snapshot)
