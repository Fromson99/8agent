"""구조 우선 착지 검색.

질문을 DB의 검색 객체와 역할 단서로 나누고, 각 출현이 소속된 본문 좌표 집합을
교차한다. Assertion/Frame ID는 어느 추출에서 왔는지 설명하는 provenance일 뿐
검색 교집합의 단위가 아니다. 검색 순서는 단순하다.

    Document -> TOC/Heading -> 본문에 속한 역할 Concept/조각 -> 원문 좌표

DB 값과 질문 표현이 정확히 맞으면 코드가 즉시 착지한다. 맞지 않으면 후보 풀이
작을 때는 전부 닫힌 메뉴로, 클 때는 Vector로 메뉴를 줄인 뒤 LLM이 DB 객체만
선택한다. 원문 교집합이 작으면 그대로 사용하고, 클 때만 다시 Vector + LLM으로
본문을 고른다. LLM은 객체 ID나 SQL을 만들 수 없다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from lawrag.core.domain_graph import spanparts
from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.rag.answer import SECTION_CHARS, Section
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.index import Index


CLOSED_MENU_MAX = int(control_value("landing.closed_menu_max"))
DIRECT_SECTIONS_MAX = int(control_value("landing.direct_sections_max"))
VECTOR_SHORTLIST_MAX = int(control_value("landing.vector_shortlist_max"))

ROLE_MAP = {
    "actor": ("ACTOR",),
    "predicate": ("PREDICATE",),
    "object": ("OBJECT",),
    "target": ("TARGET",),
    "method": ("METHOD",),
    # 역할 간선이 없는 질문 조각을 PREDICATE로 대체하지 않는다. 예를 들어
    # CONDITION 문장을 임의의 행위 Concept에 붙이면 질문의 실제 술어보다 먼저
    # 좌표를 잠가 버린다. 현재 정본에 해당 역할이 없으면 이 조각은 검색 AND에
    # 참여하지 않고, 저장된 ACTOR/PREDICATE/OBJECT 같은 실제 요소만 교차한다.
    "modality": ("MODALITY",),
    "condition": ("CONDITION",),
    "effect": ("EFFECT",),
    "subject": ("SUBJECT",),
    "unknown": tuple(sorted(spanparts.PART_ROLES)),
}
_CORPUS_DOC = re.compile(
    r"(?:법|법률|시행령|시행규칙|규정|규칙|세칙|약관|조례|정관|지침|고시)$"
)
_QUERY_RELATION_SURFACES = frozenset({"관계", "관련성", "연관성"})

MAP_SYSTEM = (
    "질문에 쓰인 표현이 어느 DB 객체를 뜻하는지 닫힌 메뉴에서만 고른다. "
    "후보 ID를 새로 만들거나 메뉴 밖 값을 쓰지 않는다. 확실하지 않으면 그 질문 "
    "조각은 picks에서 생략한다. 약칭·줄임말·활용형은 후보 label과 문맥을 보고 판단한다."
)
SECTION_SYSTEM = (
    "질문에 직접 답하는 원문 구역만 닫힌 후보에서 고른다. 후보 ID를 새로 만들지 "
    "않는다. 근거가 아닌 후보는 생략하고 최대 허용 개수보다 많이 고르지 않는다."
)


def _pack(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _surface_score(left: str, right: str) -> float:
    l, r = _pack(left), _pack(right)
    if not l or not r:
        return 0.0
    if l == r:
        return 1.0
    if l in r or r in l:
        return 0.72 + 0.2 * min(len(l), len(r)) / max(len(l), len(r))
    lg = {l[i:i + 2] for i in range(max(1, len(l) - 1))}
    rg = {r[i:i + 2] for i in range(max(1, len(r) - 1))}
    return 2 * len(lg & rg) / max(1, len(lg) + len(rg))


def _subsequence_score(needle: str, haystack: str) -> float:
    """`금투법`처럼 정본의 핵심 글자를 순서대로 줄인 표현의 렉시컬 안전망."""
    n, h = _pack(needle), _pack(haystack)
    if not n or not h:
        return 0.0
    positions, cursor = [], 0
    for char in n:
        pos = h.find(char, cursor)
        if pos < 0:
            return 0.0
        positions.append(pos)
        cursor = pos + 1
    span = positions[-1] - positions[0] + 1
    return 0.45 + 0.4 * len(n) / max(span, len(n))


@dataclass
class ValueCandidate:
    id: str
    label: str
    kind: str
    context: str = ""

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "kind": self.kind,
                "context": self.context}


@dataclass
class Menu:
    part_index: int
    surface: str
    role: str
    candidates: list[ValueCandidate]
    raw_count: int
    route: str

    def as_dict(self) -> dict:
        return {"part_index": self.part_index, "surface": self.surface,
                "role": self.role, "raw_count": self.raw_count,
                "route": self.route,
                "candidates": [candidate.as_dict() for candidate in self.candidates]}


@dataclass
class Landing:
    part_index: int
    surface: str
    role: str
    object_kind: str
    object_id: str
    label: str
    via: str
    coordinates: set[tuple] = field(default_factory=set)
    assertion_ids: set[str] = field(default_factory=set)

    def as_dict(self) -> dict:
        return {"part_index": self.part_index, "surface": self.surface,
                "role": self.role, "object_kind": self.object_kind,
                "object_id": self.object_id, "label": self.label,
                "via": self.via, "coordinate_count": len(self.coordinates),
                "assertion_count": len(self.assertion_ids)}


def _schema(candidate_ids: set[str]) -> dict:
    return {
        "type": "object",
        "properties": {"picks": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "part_index": {"type": "integer"},
                "candidate_id": {"type": "string", "enum": sorted(candidate_ids)},
            },
            "required": ["part_index", "candidate_id"],
            "additionalProperties": False,
        }}},
        "required": ["picks"], "additionalProperties": False,
    }


def _select_menus(llm, question: str, menus: list[Menu], *, kind: str) -> dict[int, str]:
    if llm is None or not menus:
        return {}
    candidate_ids = {candidate.id for menu in menus for candidate in menu.candidates}
    if not candidate_ids:
        return {}
    lines = [f"[질문]\n{question}", "\n[DB 객체 후보]"]
    allowed: dict[int, set[str]] = {}
    for menu in menus:
        allowed[menu.part_index] = {candidate.id for candidate in menu.candidates}
        lines.append(
            f"\nP{menu.part_index} 표현={menu.surface!r} 역할={menu.role} "
            f"원래후보={menu.raw_count} 축소={menu.route}"
        )
        for candidate in menu.candidates:
            context = candidate.context[:240]
            lines.append(f"- {candidate.id} | {candidate.label} | {candidate.kind}"
                         + (f" | {context}" if context else ""))
    out = llm.structured(kind, MAP_SYSTEM, "\n".join(lines), _schema(candidate_ids),
                         max_tokens=900, effort="low")
    selected: dict[int, str] = {}
    for row in (out or {}).get("picks") or []:
        part_index, cid = row.get("part_index"), str(row.get("candidate_id") or "")
        if isinstance(part_index, int) and cid in allowed.get(part_index, set()) \
                and part_index not in selected:
            selected[part_index] = cid
    return selected


def _lexical_documents(index: Index, surface: str) -> list[ValueCandidate]:
    ranked = []
    for doc_id, view in index.entry_docs.items():
        score = max(_surface_score(surface, view.name),
                    _subsequence_score(surface, view.name))
        ranked.append((score, len(_pack(view.name)), doc_id, view.name))
    ranked.sort(key=lambda row: (-row[0], row[1], row[2]))
    return [ValueCandidate(f"document:{doc_id}", label, "Document")
            for _, _, doc_id, label in ranked]


def _document_menu(index: Index, surface: str, part_index: int) -> Menu:
    all_docs = _lexical_documents(index, surface)
    if len(all_docs) <= CLOSED_MENU_MAX:
        return Menu(part_index, surface, "document", all_docs, len(all_docs), "all")

    from lawrag.core.rag import vector as vector_mod

    vector_docs = []
    seen = set()
    for doc_id, _node, _score in vector_mod.search(
            surface, topk=CLOSED_MENU_MAX * 3, doc_ids=index.scope):
        if doc_id in seen or doc_id not in index.entry_docs:
            continue
        seen.add(doc_id)
        vector_docs.append(ValueCandidate(
            f"document:{doc_id}", index.docs[doc_id].name, "Document"))
    merged = vector_docs[:]
    for candidate in all_docs:
        if candidate.id in {row.id for row in merged}:
            continue
        merged.append(candidate)
        if len(merged) >= CLOSED_MENU_MAX:
            break
    route = "vector+surface" if vector_docs else "vector-unavailable+surface"
    return Menu(part_index, surface, "document", merged[:CLOSED_MENU_MAX],
                len(all_docs), route)


def _looks_like_corpus_document(span: spanparts.QuerySpan, anchors) -> bool:
    if span.role != "document":
        return False
    packed = _pack(span.text)
    if any(_pack(name) in packed or packed in _pack(name)
           for name in anchors.documents):
        return True
    return bool(_CORPUS_DOC.search(span.text.strip()))


def _scope_assertions(registry: Tier1Registry, doc_ids: set[str],
                      coordinates: set[tuple]) -> list:
    out = []
    for assertion in registry.active_assertions:
        pair = (str(assertion.source.get("doc_id") or ""),
                assertion.source.get("node"))
        if coordinates and pair not in coordinates:
            continue
        if not coordinates and doc_ids and pair[0] not in doc_ids:
            continue
        out.append(assertion)
    return out


def _role_edges(role: str) -> tuple[str, ...]:
    if role == "document":
        return ("SUBJECT",)
    if role == "unknown":
        from lawrag.core.domain_graph.tier1 import ASSERTION_ROLES
        return tuple(sorted(ASSERTION_ROLES))
    return ROLE_MAP.get(role, ())


def _concept_pool(registry: Tier1Registry, assertions: list, role: str) -> set[str]:
    edges = _role_edges(role)
    return {cid for assertion in assertions for edge in edges
            for cid in (assertion.roles.get(edge) or ())
            if cid in registry.active_concepts}


def _concept_context(index: Index, assertions: list, cid: str, role: str) -> str:
    edges = set(_role_edges(role))
    for assertion in assertions:
        if not any(cid in (assertion.roles.get(edge) or ()) for edge in edges):
            continue
        doc_id, node = str(assertion.source.get("doc_id") or ""), \
            assertion.source.get("node")
        view = index.docs.get(doc_id)
        section = view.by_id.get(node) if view else None
        if view is not None and section is not None:
            return f"{view.name} | {view.path(node)} | {view.section_text(section, cap=180)}"
    return ""


def _concept_candidates(registry: Tier1Registry, index: Index, assertions: list,
                        role: str, pool: set[str]) -> list[ValueCandidate]:
    return [ValueCandidate(cid, registry.active_concepts[cid].label,
                           registry.active_concepts[cid].type,
                           _concept_context(index, assertions, cid, role))
            for cid in sorted(pool)]


def _semantic_menu(registry: Tier1Registry, index: Index, assertions: list,
                   span: spanparts.QuerySpan, part_index: int,
                   *, lexicon=None, exact_assertions: list | None = None) \
        -> tuple[Optional[Landing], Optional[Menu]]:
    role = "subject" if span.role == "document" else span.role
    pool = _concept_pool(registry, assertions, role)
    exact_pool = _concept_pool(
        registry, exact_assertions if exact_assertions is not None else assertions,
        role)
    if not pool and not exact_pool:
        return None, None
    exact = []
    for cid in exact_pool:
        concept = registry.active_concepts[cid]
        if any(_pack(span.text) == _pack(surface) for surface in concept.surfaces):
            exact.append(cid)
    if len(exact) == 1:
        concept = registry.active_concepts[exact[0]]
        return Landing(part_index, span.text, role, "concept", exact[0],
                       concept.label, "exact"), None
    if exact:
        candidates = _concept_candidates(registry, index, assertions, role, set(exact))
        return None, Menu(part_index, span.text, role, candidates, len(exact), "exact-menu")

    candidates = _concept_candidates(registry, index, assertions, role, pool)
    if len(candidates) <= CLOSED_MENU_MAX:
        return None, Menu(part_index, span.text, role, candidates, len(candidates), "all")

    vector_ids = []
    if lexicon is not None:
        try:
            rows = lexicon.neighbors_many(
                [span.text], k=CLOSED_MENU_MAX * 4,
                min_cos=float(control_value("concept.semantic_cos_min")))[0]
            by_surface = {}
            for cid in pool:
                for surface in registry.active_concepts[cid].surfaces:
                    by_surface.setdefault(_pack(surface), []).append(cid)
            for row in rows:
                for cid in by_surface.get(_pack(row.get("term") or ""), ()):
                    if cid not in vector_ids:
                        vector_ids.append(cid)
        except Exception:
            vector_ids = []
    lexical = sorted(
        pool,
        key=lambda cid: (
            -max(_surface_score(span.text, surface)
                 for surface in registry.active_concepts[cid].surfaces),
            cid,
        ),
    )
    shortlisted = vector_ids[:]
    for cid in lexical:
        if cid not in shortlisted:
            shortlisted.append(cid)
        if len(shortlisted) >= CLOSED_MENU_MAX:
            break
    route = "vector+surface" if vector_ids else "vector-unavailable+surface"
    selected = _concept_candidates(
        registry, index, assertions, role, set(shortlisted[:CLOSED_MENU_MAX]))
    order = {cid: pos for pos, cid in enumerate(shortlisted)}
    selected.sort(key=lambda item: order.get(item.id, len(order)))
    return None, Menu(part_index, span.text, role, selected,
                      len(candidates), route)


def _occurrences_for_concept(assertions: list, cid: str,
                             role: str) -> tuple[set[str], set[tuple]]:
    """구조 범위 안에서 Concept가 요청 역할로 붙은 원문 좌표.

    Assertion ID는 어떤 추출 행이 근거였는지 남기는 provenance일 뿐,
    검색 교집합의 키가 아니다. 같은 본문을 조건·효과·예외로 여러 번
    추출해도 검색 단위는 항상 ``(doc_id, node)`` 하나다.
    """
    edges = set(_role_edges(role))
    assertion_ids, coordinates = set(), set()
    for assertion in assertions:
        if not any(cid in (assertion.roles.get(edge) or ()) for edge in edges):
            continue
        assertion_ids.add(assertion.id)
        pair = (str(assertion.source.get("doc_id") or ""),
                assertion.source.get("node"))
        if pair[0] and pair[1] is not None:
            coordinates.add(pair)
    return assertion_ids, coordinates


def _assertions_at_landing_coordinates(assertions: list, landing: Landing) -> list:
    """이미 확정된 Concept와 같은 본문 좌표의 모든 추출 행.

    같은 본문을 여러 Assertion으로 쪼갠 행은 전부 유지하고, 다른 본문 행만 메뉴
    후보에서 뺀다. Assertion ID 교집합으로 되돌아가지 않기 위한 좌표 필터다.
    """
    _ids, coordinates = _occurrences_for_concept(
        assertions, landing.object_id, landing.role)
    if not coordinates:
        return []
    return [assertion for assertion in assertions
            if (str(assertion.source.get("doc_id") or ""),
                assertion.source.get("node")) in coordinates]


def _literal_fragment_landings(question: str, assertions: list) -> list[Landing]:
    """용어로 승격하지 않고 본문에서 잘라 둔 ``query_cues``의 좌표 출현.

    cue가 어느 Assertion 행에 있었는지는 provenance로만 남긴다. 같은 cue가 같은
    본문에서 여러 번 추출됐거나 서로 다른 추출 행에 있어도 ``(doc_id, node)``로
    합친다. 긴 cue가 잡히면 그 안에 포함된 짧은 cue는 같은 질문 조각을 중복해서
    AND하지 않는다.
    """
    packed_question = _pack(question)
    grouped: dict[str, dict] = {}
    for assertion in assertions:
        pair = (str(assertion.source.get("doc_id") or ""),
                assertion.source.get("node"))
        if not pair[0] or pair[1] is None:
            continue
        for cue in assertion.query_cues:
            key = _pack(cue)
            if len(key) < 2 or key not in packed_question:
                continue
            row = grouped.setdefault(key, {
                "surface": cue, "coordinates": set(), "assertion_ids": set(),
            })
            row["coordinates"].add(pair)
            row["assertion_ids"].add(assertion.id)
    maximal = {key for key in grouped
               if not any(key != other and key in other for other in grouped)}
    out = []
    for pos, key in enumerate(sorted(maximal, key=lambda value: (-len(value), value)), 1):
        row = grouped[key]
        out.append(Landing(
            -2000 - pos, row["surface"], "literal_fragment", "literal_fragment",
            f"fragment:{key}", row["surface"], "exact-body-fragment",
            coordinates=set(row["coordinates"]),
            assertion_ids=set(row["assertion_ids"]),
        ))
    return out


def _surface_catalog(registry: Tier1Registry) \
        -> tuple[dict[str, list[tuple[str, str]]], int]:
    """정본 Concept 표면의 프로세스 내 역조회 사전."""
    catalog = getattr(registry, "_landing_surface_catalog", None)
    if catalog is not None:
        return catalog
    by_key: dict[str, list[tuple[str, str]]] = {}
    max_len = 0
    for cid, concept in registry.active_concepts.items():
        for surface in concept.surfaces:
            key = _pack(surface)
            if len(key) < 2:
                continue
            by_key.setdefault(key, []).append((cid, surface))
            max_len = max(max_len, len(key))
    catalog = (by_key, max_len)
    registry._landing_surface_catalog = catalog
    return catalog


def _deterministic_spans(registry: Tier1Registry, question: str,
                         assertions: list, *,
                         excluded_ranges: tuple[tuple[int, int], ...] = ()) \
        -> list[spanparts.QuerySpan]:
    """무LLM 경로: 질문에 실제 표면형이 들어간 Concept만 단서로 쓴다."""
    roles_by_cid: dict[str, set[str]] = {}
    for assertion in assertions:
        for role, ids in assertion.roles.items():
            for cid in ids:
                roles_by_cid.setdefault(cid, set()).add(role.lower())
    if not roles_by_cid:
        return []

    # 4만여 Concept를 질문마다 전부 순회하지 않는다. 레지스트리가 살아 있는 동안
    # 표면형 사전을 한 번만 만들고, 짧은 질문의 부분문자열만 역조회한다.
    catalog = _surface_catalog(registry)

    packed_chars, offsets = [], []
    for original_pos, char in enumerate(question):
        if char.isspace():
            continue
        for folded in char.casefold():
            packed_chars.append(folded)
            offsets.append(original_pos)
    packed = "".join(packed_chars)
    by_key, max_len = catalog
    found = []
    for start in range(len(packed)):
        stop = min(len(packed), start + max_len)
        for end in range(start + 2, stop + 1):
            if any(left <= start and end <= right
                   for left, right in excluded_ranges):
                continue
            key = packed[start:end]
            rows = by_key.get(key)
            if not rows or key in _QUERY_RELATION_SURFACES:
                continue
            original_start, original_end = offsets[start], offsets[end - 1] + 1
            original = question[original_start:original_end]
            for cid, surface in rows:
                if cid not in roles_by_cid:
                    continue
                # 두 글자 용어는 질문의 단어 경계를 넘어 붙이지 않는다.
                # ``회사 채용``을 공백 제거 후 ``사채``로 읽던 실제 오탐을 막되,
                # ``투자 설명서`` 같은 보편적인 긴 띄어쓰기 변형은 허용한다.
                if len(key) < 4 and not any(ch.isspace() for ch in surface) \
                        and any(ch.isspace() for ch in original):
                    continue
                roles = roles_by_cid[cid]
                # 실제 데이터에서 같은 Concept가 여러 본문의 ACTOR/TARGET 등에
                # 나타나는 것은 자연스럽다. 역할이 하나가 아니면 모든 역할 출현을
                # 조회하는 unknown으로 둔다.
                role = next(iter(roles)) if len(roles) == 1 else "unknown"
                # Frame 추출에서 조사까지 붙은 임시 Concept(``투자자가``)보다
                # 정본 역할 Concept(``투자자``)를 먼저 쓴다. 둘은 같은 질문
                # 구간에서 겹치므로 아래 범위 중복 가드가 임시형을 제거한다.
                frame_penalty = int(cid.startswith("concept:frame_concept_"))
                found.append((len(key), original_start, original_end,
                              original, role, cid, key, frame_penalty))

    # 역할별 하나만 남기면 ``금융투자업자 + 투자설명서``처럼 둘 다 여러 역할로
    # 쓰인 질문에서 하나가 사라진다. 질문에 실제로 들어 있는 서로 다른 긴 표면을
    # 모두 유지하되, 더 긴 용어 안의 부분 Concept와 중복 구간은 뺀다.
    selected, selected_surfaces, selected_ranges, selected_cids = [], [], [], set()
    for row in sorted(found, key=lambda item: (
            item[7], -item[0], item[1], item[5])):
        _, start, end, _surface, _role, cid, surface_key, _penalty = row
        if cid in selected_cids:
            continue
        if any(surface_key in longer for longer in selected_surfaces):
            continue
        if any(surface_key == existing for existing in selected_surfaces):
            continue
        if any(start < other_end and other_start < end
               for other_start, other_end in selected_ranges):
            continue
        selected.append(row)
        selected_surfaces.append(surface_key)
        selected_ranges.append((start, end))
        selected_cids.add(cid)
        if len(selected) >= spanparts.MAX_QUERY_SPANS:
            break
    return [spanparts.QuerySpan(surface, start, end, role)
            for _, start, end, surface, role, _cid, _key, _penalty in
            sorted(selected, key=lambda item: (item[1], item[2], item[5]))]


def _scoped_body_occurrences(index: Index, coordinates: set[tuple],
                             surfaces: tuple[str, ...]) -> set[tuple]:
    """명시 구조 범위의 원문에서 Concept 표면이 직접 쓰인 소유 좌표.

    Assertion 추출이 ``면접위원``을 다른 복합 OBJECT로 잘라 놓았더라도 원문에
    실제 낱말이 있으면 같은 본문에 착지해야 한다. 부모 Section의 전체 subtree
    텍스트를 쓰면 자식 출현이 부모에도 복제되므로 block의 실제 owner만 센다.
    무좌표 전역 질의는 12만 노드를 런타임에 훑지 않고 정본 Assertion 출현만 쓴다.
    """
    if not coordinates:
        return set()
    keys = {_pack(surface) for surface in surfaces if len(_pack(surface)) >= 2}
    if not keys:
        return set()
    wanted_by_doc: dict[str, set[object]] = {}
    for doc_id, node in coordinates:
        wanted_by_doc.setdefault(doc_id, set()).add(node)
    out = set()
    for doc_id, wanted in wanted_by_doc.items():
        view = index.docs.get(doc_id)
        if view is None:
            continue
        for block in view.blocks:
            node = block.get("node")
            if node is None:
                node = (view.owner(block.get("idx")) or {}).get("id")
            if node not in wanted:
                continue
            text = _pack(block.get("text") or "")
            if any(key in text for key in keys):
                out.add((doc_id, node))
    return out


def _compound_action_occurrences(index: Index, coordinates: set[tuple],
                                 surface: str) -> set[tuple]:
    """붙여 쓴 복합 행위어의 두 글자 성분이 같은 본문에 모두 있는 좌표.

    ``손해배상책임`` 정본이 다른 추출 행에만 있어도 원문이 ``손해를 배상할
    책임``이라고 풀어 쓴 경우를 놓치지 않는다. 이미 다른 요소로 좁혀진 후보
    안에서만 검사하고, 모든 성분이 같은 block owner에 있어야 하므로 전역 OR
    확장이 아니다. 네 글자 미만·홀수형은 억지 분해하지 않는다.
    """
    key = _pack(surface)
    if len(key) < 4 or len(key) % 2:
        return set()
    atoms = tuple(key[pos:pos + 2] for pos in range(0, len(key), 2))
    if len(set(atoms)) < 2:
        return set()
    wanted_by_doc: dict[str, set[object]] = {}
    for doc_id, node in coordinates:
        wanted_by_doc.setdefault(doc_id, set()).add(node)
    out = set()
    for doc_id, wanted in wanted_by_doc.items():
        view = index.docs.get(doc_id)
        if view is None:
            continue
        for block in view.blocks:
            node = block.get("node")
            if node is None:
                node = (view.owner(block.get("idx")) or {}).get("id")
            if node not in wanted:
                continue
            text = _pack(block.get("text") or "")
            if all(atom in text for atom in atoms):
                out.add((doc_id, node))
    return out


def _structure_packed_ranges(index: Index, question: str, anchors) \
        -> tuple[tuple[int, int], ...]:
    """문서 제목/약칭과 조문 좌표가 차지한 compact-question 구간.

    문서명 안의 ``절차``·``규정``이나 ``제18조``를 의미 Concept로 다시 AND하면
    제목/Heading 좌표와 본문 역할 좌표가 서로 죽는다. 구조 파서가 이미 소비한
    구간은 의미 역매칭에서 제외한다.
    """
    ranges = [(start, end)
              for start, end, _doc_id, _name in
              spanparts._document_mentions(index, question)]
    packed_question = _pack(question)
    for locator in anchors.locators:
        key = _pack(locator)
        if not key:
            continue
        cursor = 0
        while True:
            pos = packed_question.find(key, cursor)
            if pos < 0:
                break
            ranges.append((pos, pos + len(key)))
            cursor = pos + max(1, len(key))
    return tuple(sorted(set(ranges)))


def _without_structure_ranges(question: str,
                              ranges: tuple[tuple[int, int], ...]) -> str:
    """구조가 이미 소비한 compact 구간을 의미/정의 검색 입력에서 가린다."""
    chars = list(_pack(question))
    for start, end in ranges:
        for pos in range(max(0, start), min(len(chars), end)):
            chars[pos] = " "
    return "".join(chars)


def _rerun_locator(index: Index, question: str, doc_ids: set[str], anchors):
    resolved = anchors
    if anchors.unresolved_locators and len(doc_ids) == 1:
        scoped = index.scoped(doc_ids, name="질문 문서 착지")
        resolved = spanparts.resolve_structure(scoped, question)
    return spanparts.StructureAnchors(
        doc_ids=tuple(doc_ids),
        documents=tuple(index.docs[doc_id].name for doc_id in doc_ids),
        locators=resolved.locators or anchors.locators,
        source_coordinates=resolved.source_coordinates,
        unresolved_locators=resolved.unresolved_locators,
    )


def _rebind_structure(index: Index, question: str, doc_ids: set[str], anchors):
    """QueryGuide가 문서/Concept 중의성을 가른 뒤 숫자 좌표도 그 문서에 재결합."""
    if doc_ids == set(anchors.doc_ids):
        return _rerun_locator(index, question, doc_ids, anchors)
    if not doc_ids:
        return spanparts.StructureAnchors(
            doc_ids=(), documents=(), locators=anchors.locators,
            source_coordinates=(), unresolved_locators=anchors.locators,
        )
    scoped = index.scoped(doc_ids, name="DB 역매칭 문서 선택")
    resolved = spanparts.resolve_structure(scoped, question)
    return spanparts.StructureAnchors(
        doc_ids=tuple(sorted(doc_ids)),
        documents=tuple(index.docs[doc_id].name for doc_id in sorted(doc_ids)),
        locators=resolved.locators or anchors.locators,
        source_coordinates=resolved.source_coordinates,
        unresolved_locators=resolved.unresolved_locators,
    )


def _structure_landings(index: Index, spans: list[spanparts.QuerySpan],
                        anchors) -> list[Landing]:
    """TOC/Heading/법조문을 Concept와 같은 Landing 관측 형식으로 낸다."""
    out, seen = [], set()
    final_coords = set(anchors.source_coordinates)
    doc_scope = tuple(anchors.doc_ids)
    for pos, span in enumerate(spans, 1):
        if span.role in ("toc", "heading"):
            candidates = spanparts.named_structure_candidates(
                index, span.text, doc_ids=doc_scope)
            if not doc_scope and len({doc_id for doc_id, _ in candidates}) > 1:
                candidates = []
            for doc_id, node in candidates:
                key = (pos, doc_id, node)
                if key in seen:
                    continue
                seen.add(key)
                view = index.docs[doc_id]
                subtree = {(doc_id, child)
                           for child in spanparts.structure_descendants(view, node)}
                coords = subtree & final_coords if final_coords else subtree
                out.append(Landing(
                    pos, span.text, span.role, "section",
                    f"section:{doc_id}:{node}", view.path(node) or span.text,
                    "exact-structure", coordinates=coords,
                ))
        elif span.role == "locator" and final_coords:
            # source_coordinates는 정확 좌표의 하위 트리다. 집합 안에 부모가 없는
            # 노드가 질문이 실제로 착지한 구조 객체다.
            for doc_id in sorted({doc_id for doc_id, _ in final_coords}):
                view = index.docs.get(doc_id)
                if view is None:
                    continue
                nodes = {node for did, node in final_coords if did == doc_id}
                roots = [node for node in nodes
                         if (view.by_id.get(node) or {}).get("parent") not in nodes]
                for node in sorted(roots, key=str):
                    key = (pos, doc_id, node)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(Landing(
                        pos, span.text, "locator", "section",
                        f"section:{doc_id}:{node}", view.path(node) or span.text,
                        "exact-structure", coordinates=set(final_coords),
                    ))
    return out


def _section_schema(ids: list[str]) -> dict:
    return {
        "type": "object",
        # 공급자 공통 구조화 출력은 maxItems를 받지 않는 경우가 있다. 실제 상한은
        # _judge_sections의 검증/슬라이스가 강제하므로 스키마에는 enum만 둔다.
        "properties": {"picks": {"type": "array",
            "items": {"type": "string", "enum": ids}}},
        "required": ["picks"], "additionalProperties": False,
    }


def _judge_sections(llm, index: Index, question: str,
                    coordinates: list[tuple]) -> list[tuple]:
    if llm is None:
        return coordinates[:DIRECT_SECTIONS_MAX]
    ids, rows = [], []
    by_id = {}
    for pos, (doc_id, node) in enumerate(coordinates, 1):
        view = index.docs.get(doc_id)
        section = view.by_id.get(node) if view else None
        if view is None or section is None:
            continue
        cid = f"S{pos}"
        ids.append(cid)
        by_id[cid] = (doc_id, node)
        rows.append(f"{cid} | {view.name} | {view.path(node)} | "
                    f"{view.section_text(section, cap=500)}")
    if not ids:
        return []
    out = llm.structured(
        "rag.landing.sections", SECTION_SYSTEM,
        f"[질문]\n{question}\n\n[교집합 안 원문 후보]\n" + "\n".join(rows),
        _section_schema(ids), max_tokens=500, effort="low",
    )
    picked = []
    for cid in (out or {}).get("picks") or []:
        if cid in by_id and by_id[cid] not in picked:
            picked.append(by_id[cid])
    return picked[:DIRECT_SECTIONS_MAX]


def _definition_sections(index: Index, question: str, doc_ids: set[str],
                         *, cap: int) -> tuple[list[Section], list[dict]]:
    """정의 질문은 Assertion 교집합이 아니라 저자 선언 정의 좌표로 직행한다."""
    from lawrag.core.rag import definitions

    if not definitions.is_definition_question(question):
        return [], []
    hits = definitions.query_hits(index, question, doc_ids=doc_ids or None)
    target = definitions.definition_target(question)
    if target:
        target_key = _pack(target)
        hits = [hit for hit in hits if _pack(hit.get("term") or "") == target_key]
    sections, meta = [], []
    for hit in hits:
        doc_id, node = hit["doc_id"], hit["node"]
        view = index.docs.get(doc_id)
        source = view.by_id.get(node) if view else None
        if view is None or source is None:
            continue
        sections.append(Section(
            n=0, doc_id=doc_id, doc=view.name, node=node,
            path=view.path(node) or view.name, page=source.get("page"),
            kind="정의", matched=f"질문 용어 '{hit['term']}'의 저자 선언 정의",
            text=view.section_outline(source, cap=SECTION_CHARS),
        ))
        meta.append({"term": hit["term"], "doc_id": doc_id, "node": node,
                     "path": view.path(node), "definition_kind": hit.get("kind")})
        if len(sections) >= max(1, int(cap)):
            break
    return sections, meta


def retrieve(index: Index, question: str, registry: Tier1Registry, *, llm=None,
             cap: int = DIRECT_SECTIONS_MAX, propose_terms: bool = True,
             lexicon=None) -> tuple[list[Section], dict]:
    """질문 조각별 DB 착지 -> 좌표 교집합 -> 필요할 때만 Vector/LLM."""
    meta = {"strategy": "coordinate_intersection", "structure": {}, "spans": [],
            "menus": [], "landings": [], "intersection": [],
            "candidate_count": 0, "pruning": "", "fallback": ""}
    anchors = spanparts.resolve_structure(index, question)
    guide = None
    if llm is not None:
        from lawrag.core.rag import queryguide

        if queryguide.enabled():
            guide = queryguide.build(index, question, registry, anchors)
    spans = spanparts.extract_spans(llm, question, guide=guide) \
        if llm is not None else []
    meta["spans"] = [span.as_dict() for span in spans]
    if guide is None:
        meta["query_guide"] = {"enabled": False}
    else:
        meta["query_guide"] = guide.as_dict()
        selected_ids = list(dict.fromkeys(
            rid for span in spans for rid in span.reading_ids))
        table = guide.by_id
        meta["query_guide"]["selected_ids"] = selected_ids
        meta["query_guide"]["selected"] = [
            table[rid].as_dict() for rid in selected_ids if rid in table]

    # 1) 문서 제목/약칭 착지. 이미 결정론으로 맞은 문서는 그대로 쓴다.
    doc_ids = set(anchors.doc_ids)
    selected_by_span: dict[tuple[int, int], list] = {}
    if guide is not None:
        from lawrag.core.rag import queryguide

        doc_ids = queryguide.selected_document_ids(guide, spans, doc_ids)
        for span in spans:
            selected_by_span[(span.start, span.end)] = guide.selected(span.reading_ids)
        anchors = _rebind_structure(index, question, doc_ids, anchors)
    selected_doc_rows = [
        row for rows in selected_by_span.values() for row in rows
        if row.object_kind == "document"
    ]
    landings: list[Landing] = [
        Landing(
            -(pos + 1),
            next((row.surface for row in selected_doc_rows
                  if row.object_id == f"document:{doc_id}"), name),
            "document", "document", f"document:{doc_id}", name,
            next((f"query-guide:{row.via}" for row in selected_doc_rows
                  if row.object_id == f"document:{doc_id}"),
                 "exact-or-approved-alias"),
        )
        for pos, (doc_id, name) in enumerate(zip(anchors.doc_ids, anchors.documents))
    ]
    doc_menus = []
    known_doc_surfaces = {_pack(name) for name in anchors.documents}
    for pos, span in enumerate(spans, 1):
        if not _looks_like_corpus_document(span, anchors):
            continue
        if any(row.object_kind == "document"
               for row in selected_by_span.get((span.start, span.end), ())):
            continue
        mentioned = {row[2] for row in spanparts._document_mentions(index, span.text)}
        if mentioned & doc_ids or any(
                name in _pack(span.text) or _pack(span.text) in name
                for name in known_doc_surfaces):
            continue
        doc_menus.append(_document_menu(index, span.text, pos))
    doc_picks = _select_menus(llm, question, doc_menus, kind="rag.landing.documents")
    for menu in doc_menus:
        picked = doc_picks.get(menu.part_index)
        candidate = next((row for row in menu.candidates if row.id == picked), None)
        if candidate is None:
            continue
        doc_id = candidate.id.removeprefix("document:")
        doc_ids.add(doc_id)
        landing = Landing(menu.part_index, menu.surface, "document", "document",
                          candidate.id, candidate.label, "llm-menu")
        landings.append(landing)
        if propose_terms:
            from lawrag.core.rag import term_proposals
            term_proposals.propose(
                menu.surface, target_kind="document", target_id=doc_id,
                target_label=candidate.label, question=question, role="document",
                proposed_by=f"llm:{getattr(llm, 'model', 'unknown')}",
            )
    anchors = _rerun_locator(index, question, doc_ids, anchors)
    # 법조문 숫자 좌표뿐 아니라 질문에서 TOC/Heading으로 분해된 실제 제목도 같은
    # 구조 객체로 착지시킨다. 문서가 먼저 잡혔으므로 제목 후보도 그 문서 안에 한정된다.
    anchors = spanparts.resolve_named_structure(index, anchors, spans)
    landings.extend(_structure_landings(index, spans, anchors))
    meta["structure"] = anchors.as_dict()
    meta["menus"].extend(menu.as_dict() for menu in doc_menus)

    # 정의는 ACTOR/PREDICATE 교집합의 재료가 아니다. 질문이 뜻 자체를 묻는다면
    # 확정 문서 범위의 저자 선언 정의 좌표로 바로 가고, 일반 사실 질문에서만
    # 아래 본문 출현 좌표 교집합을 실행한다.
    definition_sections, definition_hits = _definition_sections(
        index, question, doc_ids, cap=cap)
    if definition_sections:
        meta["strategy"] = "definition_lookup"
        meta["definition_hits"] = definition_hits
        meta["candidate_count"] = len(definition_sections)
        meta["pruning"] = "definition-direct"
        for pos, hit in enumerate(definition_hits, 1):
            landings.append(Landing(
                pos, hit["term"], "definition", "section",
                f"section:{hit['doc_id']}:{hit['node']}", hit["path"],
                "author-definition",
                coordinates={(hit["doc_id"], hit["node"])},
            ))
        meta["landings"] = [landing.as_dict() for landing in landings]
        return definition_sections, meta
    if anchors.unresolved_locators:
        meta["fallback"] = "명시 Heading을 DB 좌표로 확정하지 못함"
        meta["landings"] = [landing.as_dict() for landing in landings]
        return [], meta

    structure_coords = set(anchors.source_coordinates)
    structure_ranges = _structure_packed_ranges(index, question, anchors)
    # ``A(이하 B라 한다)``는 A와 B를 별도 조건으로 쓰는 AND가
    # 아니라, 같은 질문 조각의 문서 내 대체 표면(OR)이다. 질문에 A가
    # 있으면 선언 이후 B가 쓰인 본문 좌표를 미리 열어 둔다.
    from lawrag.core.rag import definitions as definitions_mod

    definition_expansion_hits = definitions_mod.query_expansion_hits(
        index, _without_structure_ranges(question, structure_ranges),
        doc_ids=doc_ids or None,
        coordinates=structure_coords or None,
    )
    definition_landings = []
    for pos, hit in enumerate(definition_expansion_hits, 1):
        targets = " / ".join(hit.get("targets") or [hit["to"]])
        definition_landings.append(Landing(
            -1000 - pos, hit["from"], "definition_alias",
            "definition_expansion", f"definition:{hit['doc_id']}:{hit['node']}",
            f"{hit['from']} → {targets}", "author-alias-expansion",
            coordinates=set(hit["coordinates"]),
        ))
    landings.extend(definition_landings)
    meta["definition_expansions"] = [{
        "from": hit["from"], "to": hit.get("targets") or [hit["to"]],
        "doc_id": hit["doc_id"], "definition_node": hit.get("node"),
        "coordinate_count": len(hit["coordinates"]),
        "scope": hit.get("scope"),
    } for hit in definition_expansion_hits]

    scoped_assertions = _scope_assertions(registry, doc_ids, structure_coords)
    literal_landings = _literal_fragment_landings(question, scoped_assertions)
    landings.extend(literal_landings)
    meta["literal_fragments"] = [{
        "surface": landing.surface,
        "coordinate_count": len(landing.coordinates),
        "provenance_count": len(landing.assertion_ids),
    } for landing in literal_landings]
    meta["scope"] = {
        "documents": len(doc_ids),
        "structure_coordinates": len(structure_coords),
        "assertions": len(scoped_assertions),
    }
    if llm is None:
        spans = _deterministic_spans(
            registry, question, scoped_assertions,
            excluded_ranges=structure_ranges)
        meta["spans"] = [span.as_dict() for span in spans]

    # 2) ACTOR/PREDICATE/... 값 착지. exact는 코드, 불일치는 닫힌 메뉴의 LLM.
    if llm is not None and lexicon is None:
        lexicon = spanparts.cached_term_lexicon()
    semantic_menus = []
    menu_assertions = scoped_assertions
    exact_anchor_seen = False
    for pos, span in enumerate(spans, 1):
        if span.role in ("locator", "toc", "heading") or \
                _looks_like_corpus_document(span, anchors):
            continue
        guided_concepts = [
            row for row in selected_by_span.get((span.start, span.end), ())
            if row.object_kind == "concept"
            and row.object_id in registry.active_concepts
            and (span.role in row.roles or "unknown" in row.roles)
            # 명시 Document/Heading/조문 안에서 출현 0인 전역 Concept를 모델이
            # 표면만 보고 골라도 직접 신뢰하지 않는다. 기존 scoped 닫힌 메뉴가
            # 해당 범위의 실제 객체로 다시 검증해야 문서 밖 오염을 막을 수 있다.
            and (not anchors.explicit or row.scoped_count > 0)
        ]
        if len(guided_concepts) == 1:
            row = guided_concepts[0]
            exact, menu = Landing(
                pos, span.text, span.role, "concept", row.object_id,
                registry.active_concepts[row.object_id].label,
                "query-guide:concept-surface",
            ), None
        elif guided_concepts:
            candidates = _concept_candidates(
                registry, index, menu_assertions, span.role,
                {row.object_id for row in guided_concepts})
            exact, menu = None, Menu(
                pos, span.text, span.role, candidates, len(candidates),
                "query-guide-ambiguity",
            )
        else:
            exact, menu = _semantic_menu(
                registry, index, menu_assertions, span, pos,
                # 앞에서 정확 Concept가 잡혔으면 뒤 후보는 결국 그 Concept와 같은
                # Assertion/본문에 있어야 한다. 이 작은 풀에서는 표면 점수 상위 메뉴가
                # 충분하며, 1.4만 전역 후보용 런타임 임베딩을 다시 띄우지 않는다.
                lexicon=None if exact_anchor_seen else lexicon,
                exact_assertions=scoped_assertions)
        if exact is not None:
            landings.append(exact)
            narrowed = _assertions_at_landing_coordinates(
                menu_assertions, exact) if llm is not None else []
            # 명시 조문은 이미 작은 닫힌 범위다. 그 안에서 첫 단서 하나로 다음
            # 메뉴를 다시 자르면 Span 역할 오판이 나머지 정답 후보를 영구 제거한다.
            # 큰 무좌표/문서 범위에서만 이 성능 최적화를 사용한다.
            if llm is not None and narrowed and not structure_coords:
                menu_assertions = narrowed
                exact_anchor_seen = True
        elif menu is not None and llm is not None:
            semantic_menus.append(menu)
    semantic_picks = _select_menus(
        llm, question, semantic_menus, kind="rag.landing.values")
    for menu in semantic_menus:
        picked = semantic_picks.get(menu.part_index)
        candidate = next((row for row in menu.candidates if row.id == picked), None)
        if candidate is None:
            continue
        landing = Landing(menu.part_index, menu.surface, menu.role, "concept",
                          candidate.id, candidate.label, "llm-menu")
        landings.append(landing)
        if propose_terms:
            from lawrag.core.rag import term_proposals
            term_proposals.propose(
                menu.surface, target_kind="concept", target_id=candidate.id,
                target_label=candidate.label, question=question, role=menu.role,
                proposed_by=f"llm:{getattr(llm, 'model', 'unknown')}",
            )
    meta["menus"].extend(menu.as_dict() for menu in semantic_menus)

    # 3) 각 역할 Concept가 속한 **본문 좌표**를 교차한다. Assertion은
    #    본문에서 추출한 검색 조각의 provenance이다. 같은 본문을 여러
    #    Assertion으로 쪼갰도 하나의 좌표로 합쳐지며, 서로 다른 본문의
    #    ACTOR/PREDICATE는 좌표 교집합에서 결합되지 않는다.
    semantic_landings = [landing for landing in landings
                         if landing.object_kind == "concept"]
    semantic_spans = [
        span for span in spans
        if span.role not in ("locator", "toc", "heading")
        and not _looks_like_corpus_document(span, anchors)
    ]
    if semantic_spans and not semantic_landings and not definition_landings \
            and not literal_landings:
        meta["landings"] = [landing.as_dict() for landing in landings]
        meta["fallback"] = "질문의 의미 요소가 DB 객체에 착지하지 못함"
        return [], meta

    # 같은 질문 표면이 Concept에도 착지했다면 원래 용어 A 출현과
    # 정의 별칭 B 출현을 합집합한다. 별칭 좌표를 따로 교차하면
    # A와 B가 동시에 쓰인 본문만 남아 정의 확장의 목적이 사라진다.
    consumed_alternative_landings: set[int] = set()
    for landing in semantic_landings:
        landing.assertion_ids, landing.coordinates = _occurrences_for_concept(
            scoped_assertions, landing.object_id, landing.role)
        # 명시 조문 안에서는 정본 역할 출현뿐 아니라 원문의 직접 표면 출현도
        # 합친다. 추출기가 ``지원자``를 CONDITION 문구 안에 넣어 역할 간선을
        # 빠뜨렸더라도 그 낱말이 실제 본문에 있으면 검색 요소로는 살아야 한다.
        # 구조 범위 밖을 훑지 않으므로 전역 일반어 오염이나 대형 스캔은 없다.
        if structure_coords:
            concept = registry.active_concepts.get(landing.object_id)
            if concept is not None:
                body_coordinates = _scoped_body_occurrences(
                    index, structure_coords, concept.surfaces)
                if body_coordinates - landing.coordinates:
                    landing.coordinates.update(body_coordinates)
                    landing.via += "+exact-body"
        concept = registry.active_concepts.get(landing.object_id)
        semantic_keys = {
            _pack(value) for value in (
                landing.surface, landing.label,
                *((concept.surfaces if concept is not None else ())),
            ) if _pack(value)
        }
        for alternative in [*definition_landings, *literal_landings]:
            right = _pack(alternative.surface)
            if not right or not any(
                    left == right or left in right or right in left
                    for left in semantic_keys):
                continue
            landing.coordinates.update(alternative.coordinates)
            landing.assertion_ids.update(alternative.assertion_ids)
            suffix = "+author-alias" if alternative.object_kind == "definition_expansion" \
                else "+body-fragment"
            if suffix not in landing.via:
                landing.via += suffix
            consumed_alternative_landings.add(id(alternative))

    search_landings = semantic_landings + [
        landing for landing in [*definition_landings, *literal_landings]
        if id(landing) not in consumed_alternative_landings
    ]
    candidate_coords: Optional[set[tuple]] = set(structure_coords) \
        if structure_coords else None
    for landing in search_landings:
        before_coords = set(candidate_coords or ())
        next_coords = (set(landing.coordinates)
                       if candidate_coords is None
                       else candidate_coords & landing.coordinates)
        # 정본 action이 붙여 쓴 복합어이고, 앞의 독립 요소들이 이미 후보를
        # 만들었는데 추출 좌표만 충돌하면 같은 본문 안 원문 성분을 확인한다.
        concept = registry.active_concepts.get(landing.object_id) \
            if landing.object_kind == "concept" else None
        # Assertion 역할 좌표가 빠졌어도 앞선 교집합 후보의 실제 본문에 같은
        # 정본 표면이 있으면 그 좌표를 보완한다. 전역 코퍼스를 새로 여는 것이
        # 아니라 이미 좁혀진 후보 안만 확인한다.
        if not next_coords and candidate_coords and concept is not None:
            repaired = _scoped_body_occurrences(
                index, set(candidate_coords), concept.surfaces)
            if repaired:
                landing.coordinates.update(repaired)
                if "+exact-body" not in landing.via:
                    landing.via += "+exact-body"
                next_coords = set(candidate_coords) & landing.coordinates
        if not next_coords and candidate_coords and concept is not None \
                and concept.type in {"action", "legal_effect", "domain_term"}:
            repaired = _compound_action_occurrences(
                index, set(candidate_coords), landing.surface)
            if repaired:
                landing.coordinates.update(repaired)
                if "+compound-body" not in landing.via:
                    landing.via += "+compound-body"
                next_coords = set(candidate_coords) & landing.coordinates
        candidate_coords = next_coords
        meta["intersection"].append({
            "part_index": landing.part_index, "label": landing.label,
            "role": landing.role, "part_coordinates": len(landing.coordinates),
            "part_assertions": len(landing.assertion_ids),
            "before": len(before_coords), "after": len(candidate_coords),
        })

    if candidate_coords is None:
        if doc_ids:
            candidate_coords = {(doc_id, node.get("id")) for doc_id in doc_ids
                                for node in index.docs.get(doc_id).nodes}
        else:
            candidate_coords = set()
    candidate_coords = {(doc_id, node) for doc_id, node in candidate_coords
                        if index.in_scope(doc_id) and doc_id in index.docs
                        and node in index.docs[doc_id].by_id}
    meta["candidate_count"] = len(candidate_coords)
    meta["landings"] = [landing.as_dict() for landing in landings]
    if not candidate_coords:
        meta["fallback"] = "착지 좌표 교집합이 비어 있음"
        return [], meta

    # 4) N 이하면 전부. 넘을 때만 Vector로 교집합 안에서 자르고 LLM이 판정한다.
    ordered = sorted(candidate_coords, key=lambda row: (row[0], str(row[1])))
    direct_limit = min(max(1, int(cap)), DIRECT_SECTIONS_MAX)
    if len(ordered) <= DIRECT_SECTIONS_MAX:
        chosen = ordered[:direct_limit]
        meta["pruning"] = "direct-all"
    else:
        from lawrag.core.rag import vector as vector_mod

        vector_rows = vector_mod.search(
            question, topk=VECTOR_SHORTLIST_MAX,
            doc_ids=frozenset(doc_ids) if doc_ids else index.scope,
            coordinates=frozenset(candidate_coords), minimum=-1.0,
        )
        shortlist = []
        for doc_id, node, _score in vector_rows:
            pair = (doc_id, node)
            if pair in candidate_coords and pair not in shortlist:
                shortlist.append(pair)
        if not shortlist:
            shortlist = ordered[:VECTOR_SHORTLIST_MAX]
            vector_route = "vector-unavailable"
        else:
            vector_route = "vector"
        chosen = _judge_sections(llm, index, question, shortlist)[:direct_limit]
        meta["pruning"] = f"{vector_route}+" + ("llm" if llm is not None else "top")
        meta["shortlist_count"] = len(shortlist)
    if not chosen:
        meta["fallback"] = "교집합 후보 판정 결과 없음"
        return [], meta

    labels = " · ".join(dict.fromkeys(landing.label for landing in landings))
    sections = []
    for doc_id, node in chosen:
        view = index.docs[doc_id]
        section = view.by_id[node]
        sections.append(Section(
            n=0, doc_id=doc_id, doc=view.name, node=node,
            path=view.path(node) or view.name, page=section.get("page"),
            kind="교집합", matched=f"구조·역할 착지 — {labels}"[:160],
            text=view.section_outline(section, cap=SECTION_CHARS),
        ))
    return sections, meta
