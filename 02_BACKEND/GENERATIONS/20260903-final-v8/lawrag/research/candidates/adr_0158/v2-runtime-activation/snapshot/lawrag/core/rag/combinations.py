"""확정 구조 스코프 안에서 역할 Concept를 지연 확장하는 회수 트리.

질문에 명시된 Document/TOC/Heading/Locator는 DB 역매칭으로 확정하고 루트의
좌표 제약으로 사용한다. 나머지 실제 질문 Span은 역할별 Concept 벡터 후보로만
되돌린다. 같은 Span의 역할·Concept 후보는 OR, 서로 다른 Span은 좌표 AND다.

트리는 카테시안 곱을 먼저 만들지 않는다. 다음 역할 후보와 좌표 교집합이 실제로
남을 때만 자식 노드를 생성한다. 살아남은 좌표는 문서 계층 트리로 다시 꽂고,
LLM은 R id만 선택한다. 선택한 R의 Heading과 하위 원문 전체가 답변 합성기로 간다.
BM25, 전체질문 벡터, 임의 키워드는 이 회수기에 섞지 않는다.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from lawrag.core.domain_graph import spanparts
from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.rag import exploration as exploration_mod
from lawrag.core.rag.answer import Section
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.index import Index


LEXICON_NEIGHBORS_MAX = int(control_value("combination.lexicon_neighbors_max"))
CANDIDATES_PER_PART_MAX = int(control_value("combination.candidates_per_part_max"))
SURVIVING_NODES_MAX = int(control_value("combination.surviving_states_max"))
NODES_TO_EXPAND_MAX = int(control_value("combination.states_to_expand_max"))
COORDINATES_PER_NODE_MAX = int(
    control_value("combination.coordinates_per_state_max"))
LLM_RANGES_MAX = int(control_value("combination.llm_options_max"))
ENTRY_SECTIONS_MAX = int(control_value("entry.combination_sections_max"))


def _pack(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


@dataclass(frozen=True)
class Candidate:
    id: str
    group: str
    role: str
    surface: str
    label: str
    via: str
    coordinates: frozenset[tuple[str, object]]
    score: float = 1.0


@dataclass(frozen=True)
class CandidateGroup:
    id: str
    start: int
    end: int
    surface: str
    roles: tuple[str, ...]
    candidates: tuple[Candidate, ...]

    @property
    def coordinate_union(self) -> frozenset[tuple[str, object]]:
        return frozenset().union(*(row.coordinates for row in self.candidates))


@dataclass(frozen=True)
class TreeNode:
    id: int
    parent_id: int | None
    depth: int
    picks: tuple[Candidate, ...]
    coordinates: frozenset[tuple[str, object]]

    @property
    def rank(self) -> tuple:
        return (
            len(self.picks),
            round(sum(row.score for row in self.picks), 6),
            -len(self.coordinates),
        )


@dataclass
class TreeCounts:
    theoretical_assignments: int = 1
    attempted_extensions: int = 0
    zero_intersections: int = 0
    viable_extensions: int = 0
    pruned_states: int = 0
    depths: list[dict] = field(default_factory=list)

    def as_dict(self, surviving: int) -> dict:
        return {
            "theoretical_assignments": self.theoretical_assignments,
            "attempted_extensions": self.attempted_extensions,
            "zero_intersections": self.zero_intersections,
            "viable_extensions": self.viable_extensions,
            "surviving": surviving,
            "pruned_states": self.pruned_states,
            "depths": list(self.depths),
        }


def _valid_coordinates(index: Index, coordinates, *,
                       scope: frozenset[tuple[str, object]] | None = None) \
        -> frozenset[tuple[str, object]]:
    valid = frozenset(
        (doc_id, node) for doc_id, node in coordinates
        if index.in_scope(doc_id) and doc_id in index.docs
        and node in index.docs[doc_id].by_id
    )
    return valid if scope is None else valid & scope


def _concept_roles(registry: Tier1Registry) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for assertion in registry.active_assertions:
        for role, ids in assertion.roles.items():
            for cid in ids:
                out.setdefault(cid, set()).add(role)
    return out


def _direct_candidates(index: Index, registry: Tier1Registry, guide, span,
                       group: str, concept_coords: dict,
                       roles: dict[str, set[str]], *,
                       scope: frozenset[tuple[str, object]] | None) \
        -> list[Candidate]:
    wanted_role = span.role.upper()
    out = []
    # 같은 실제 문자열 범위에 DB가 직접 역매칭한 Concept는 모두 OR 가지로 둔다.
    # Span LLM의 reading_ids 선택으로 정답 가지를 선제 삭제하지 않는다.
    readings = [reading for reading in guide.readings
                if (reading.start, reading.end) == (span.start, span.end)]
    for reading in readings:
        if reading.object_kind != "concept":
            continue
        cid = reading.object_id
        concept = registry.active_concepts.get(cid)
        if concept is None or wanted_role not in roles.get(cid, set()):
            continue
        coordinates = _valid_coordinates(
            index, concept_coords.get(cid, ()), scope=scope)
        if not coordinates:
            continue
        out.append(Candidate(
            id=f"exact:{group}:{wanted_role}:{cid}", group=group,
            role=wanted_role, surface=span.text, label=concept.label,
            via=f"db-reverse:{reading.via}", coordinates=coordinates,
            score=2.0,
        ))
    return out


def _vector_candidates(index: Index, registry: Tier1Registry, lexicon,
                       span, group: str, concept_coords: dict,
                       by_surface: dict, roles: dict[str, set[str]], *,
                       scope: frozenset[tuple[str, object]] | None,
                       neighbors_max: int = LEXICON_NEIGHBORS_MAX,
                       min_cos: float = 0.40) \
        -> list[Candidate]:
    """같은 Assertion 역할이고 현재 구조 스코프에 출현한 Concept만 반환한다."""
    wanted_role = span.role.upper()
    if lexicon is None or span.role not in spanparts.PART_ROLES:
        return []
    if len(_pack(span.text)) < 2:
        return []
    eligible_ids = {
        cid for cid, concept_roles in roles.items()
        if wanted_role in concept_roles
        and _valid_coordinates(index, concept_coords.get(cid, ()), scope=scope)
    }
    allowed_terms = {
        surface for surface, concept_rows in by_surface.items()
        if any(cid in eligible_ids for cid, _matched in concept_rows)
    }
    if callable(getattr(lexicon, "neighbors_many_filtered", None)):
        neighbors = lexicon.neighbors_many_filtered(
            [span.text], allowed_terms, k=neighbors_max,
            min_cos=min_cos)[0]
    else:
        # 작은 단위시험 Lexicon과의 호환. 운영 CachedTermLexicon은 항상 위의
        # 역할 제한 랭킹을 사용한다.
        neighbors = lexicon.neighbors_many(
            [span.text], k=neighbors_max, min_cos=min_cos)[0]
    ranked: list[tuple[float, str, str, frozenset]] = []
    seen: set[str] = set()
    for row in neighbors:
        term = str(row.get("term") or "")
        cosine = float(row.get("cos") or 0.0)
        term_key = _pack(term)
        matches = [(1.0, cid, matched)
                   for cid, matched in by_surface.get(term_key, ())]
        if not matches and len(term_key) >= 8:
            nearby = []
            for concept_key, concept_rows in by_surface.items():
                if len(concept_key) < 6 or not (
                        concept_key in term_key or term_key in concept_key):
                    continue
                ratio = min(len(concept_key), len(term_key)) / max(
                    len(concept_key), len(term_key))
                if ratio >= 0.58:
                    nearby.extend((ratio, cid, matched)
                                  for cid, matched in concept_rows)
            matches = sorted(
                nearby, key=lambda item: (-item[0], item[1]))[:3]
        for ratio, cid, matched in matches:
            if cid in seen or wanted_role not in roles.get(cid, set()):
                continue
            coordinates = _valid_coordinates(
                index, concept_coords.get(cid, ()), scope=scope)
            if not coordinates:
                continue
            seen.add(cid)
            ranked.append((
                cosine * (0.85 + 0.15 * ratio), cid, matched, coordinates))
    ranked.sort(key=lambda row: (-row[0], len(row[3]), row[1]))
    return [Candidate(
        id=f"vector:{group}:{wanted_role}:{cid}", group=group,
        role=wanted_role, surface=span.text,
        label=registry.active_concepts[cid].label,
        via=f"role-vector:{matched}", coordinates=coordinates, score=score,
    ) for score, cid, matched, coordinates in ranked]


def _cap_candidates(rows: list[Candidate], *, limit: int) -> tuple[Candidate, ...]:
    """역할 가설 하나가 후보 상한을 독식하지 않게 역할별로 순환해 자른다."""
    best: dict[tuple[str, str, frozenset], Candidate] = {}
    for row in rows:
        key = (row.role, row.label, row.coordinates)
        old = best.get(key)
        if old is None or (row.score, row.via.startswith("db-reverse")) > \
                (old.score, old.via.startswith("db-reverse")):
            best[key] = row
    buckets: dict[str, list[Candidate]] = {}
    for row in sorted(best.values(), key=lambda item: (-item.score, item.id)):
        buckets.setdefault(row.role, []).append(row)
    out: list[Candidate] = []
    role_order = sorted(buckets)
    while len(out) < limit:
        grew = False
        for role in role_order:
            if buckets[role]:
                out.append(buckets[role].pop(0))
                grew = True
                if len(out) >= limit:
                    break
        if not grew:
            break
    return tuple(out)


def build_lazy_tree(groups: list[CandidateGroup], *,
                    scope_coordinates: frozenset[tuple[str, object]] | None = None,
                    nodes_max: int = SURVIVING_NODES_MAX) \
        -> tuple[list[TreeNode], TreeCounts, list[CandidateGroup]]:
    """좌표가 남는 자식만 생성한다. 각 단계의 기존 노드는 skip 경로로 보존한다."""
    ordered = sorted(groups, key=lambda group: (
        len(group.coordinate_union), len(group.candidates), group.start, group.end))
    counts = TreeCounts()
    next_id = 1
    root = TreeNode(
        id=0, parent_id=None, depth=0, picks=(),
        coordinates=scope_coordinates or frozenset(),
    )
    frontier = [root]
    for depth, group in enumerate(ordered, 1):
        counts.theoretical_assignments *= len(group.candidates) + 1
        before = len(frontier)
        zero_before = counts.zero_intersections
        viable_before = counts.viable_extensions
        extended = list(frontier)
        for parent in frontier:
            for candidate in group.candidates:
                counts.attempted_extensions += 1
                coordinates = candidate.coordinates
                if parent.coordinates:
                    coordinates = coordinates & parent.coordinates
                if not coordinates:
                    counts.zero_intersections += 1
                    continue
                counts.viable_extensions += 1
                extended.append(TreeNode(
                    id=next_id, parent_id=parent.id, depth=depth,
                    picks=parent.picks + (candidate,),
                    coordinates=frozenset(coordinates),
                ))
                next_id += 1
        unique: dict[tuple[tuple[str, ...], frozenset], TreeNode] = {}
        for node in extended:
            key = (tuple(row.id for row in node.picks), node.coordinates)
            unique[key] = node
        ranked = sorted(unique.values(), key=lambda node: node.rank, reverse=True)
        if len(ranked) > nodes_max:
            counts.pruned_states += len(ranked) - nodes_max
            ranked = ranked[:nodes_max]
        frontier = ranked
        counts.depths.append({
            "depth": depth, "group": group.id,
            "surface": group.surface, "roles": list(group.roles),
            "branch_count": len(group.candidates), "nodes_before": before,
            "zero_at_depth": counts.zero_intersections - zero_before,
            "viable_at_depth": counts.viable_extensions - viable_before,
            "nodes_after": len(frontier),
        })
    leaves = [node for node in frontier if node.picks]
    return leaves, counts, ordered


def _coordinate_rows(index: Index, question: str, node: TreeNode, *,
                     coordinates_max: int = COORDINATES_PER_NODE_MAX) -> list[dict]:
    from lawrag.core.rag import vector

    coordinates = node.coordinates
    if node.id != -2 and len(coordinates) > coordinates_max:
        hits = vector.search(
            question, topk=coordinates_max,
            coordinates=coordinates, minimum=-1.0)
        picked = [(doc_id, source_node, score)
                  for doc_id, source_node, score in hits]
        if not picked:
            picked = [(doc_id, source_node, None)
                      for doc_id, source_node in sorted(
                          coordinates, key=lambda row: (row[0], str(row[1])))
                          [:coordinates_max]]
    else:
        picked = [(doc_id, source_node, None)
                  for doc_id, source_node in sorted(
                      coordinates, key=lambda row: (row[0], str(row[1])))]
    out = []
    for doc_id, source_node, vector_score in picked:
        view = index.docs.get(doc_id)
        section = view.by_id.get(source_node) if view is not None else None
        if view is None or section is None:
            continue
        out.append({
            "doc_id": doc_id, "node": source_node, "doc": view.name,
            "path": view.path(source_node) or view.name,
            "vector_score": vector_score,
        })
    return out


def _tree_options(index: Index, question: str, nodes: list[TreeNode], *,
                  scope_coordinates: frozenset[tuple[str, object]] | None = None,
                  structural_roots: frozenset[tuple[str, object]] = frozenset(),
                  nodes_to_expand_max: int = NODES_TO_EXPAND_MAX,
                  coordinates_per_node_max: int = COORDINATES_PER_NODE_MAX,
                  ranges_max: int = LLM_RANGES_MAX) \
        -> list[dict]:
    selected = sorted(nodes, key=lambda node: node.rank, reverse=True)
    selected = selected[:nodes_to_expand_max]
    if structural_roots:
        # 확정된 조문/Heading은 하위 Vector 결과로 대체하지 않는다. 이 노드를
        # 선택하면 exploration.subtree_text가 하위 전체를 답변 단계에 싣는다.
        selected = [TreeNode(-2, None, 0, (), structural_roots),
                    *selected[:max(0, nodes_to_expand_max - 1)]]
    elif scope_coordinates:
        # 문서만 확정된 경우 문서 자체는 선택 단위가 아니므로 문서 안 Vector
        # 좌표를 구조 루트 폴백으로 사용한다.
        scope_root = TreeNode(-1, None, 0, (), scope_coordinates)
        selected = [scope_root, *selected[:max(0, nodes_to_expand_max - 1)]]

    merged: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for node in selected:
        node_rank = ((10 ** 6, 0.0, -len(node.coordinates))
                     if node.id == -2 else node.rank)
        matched = [{
            "surface": pick.surface, "kind": "concept",
            "label": f"{pick.label} [{pick.role}]", "role": pick.role,
            "via": pick.via, "object_id": pick.id,
        } for pick in node.picks]
        for coordinate in _coordinate_rows(
                index, question, node,
                coordinates_max=coordinates_per_node_max):
            coordinate_matched = matched
            if node.id == -2:
                coordinate_matched = [{
                    "surface": coordinate["path"], "kind": "section",
                    "label": "확정 구조 루트", "role": "STRUCTURE",
                    "via": "db-reverse:confirmed-structure",
                    "object_id": f"structure:{coordinate['doc_id']}:{coordinate['node']}",
                }]
            key = (coordinate["doc_id"], str(coordinate["node"]))
            row = merged.get(key)
            if row is None:
                row = {
                    **coordinate, "matched": [],
                    "channels": (["structure"] if node.id == -2
                                 else ["lazy_tree"]),
                    "category": ("structure" if node.id == -2
                                 else "lazy_tree"),
                    "intersection_count": len(node.coordinates),
                    "rank": node_rank,
                }
                merged[key] = row
                order.append(key)
            elif node_rank > tuple(row["rank"]):
                row["rank"] = node_rank
                row["intersection_count"] = len(node.coordinates)
            have = {item["object_id"] for item in row["matched"]}
            row["matched"].extend(
                item for item in coordinate_matched if item["object_id"] not in have)
    rows = [merged[key] for key in order]
    rows.sort(key=lambda row: tuple(row["rank"]), reverse=True)
    return rows[:ranges_max]


CHOOSE_SYSTEM = (
    "너는 법률 질의의 근거 범위를 고르는 탐색자다. 입력은 코드가 역할 Concept의 "
    "좌표 교집합으로 만든 문서→조→항/호/목 트리다. 숫자 점수나 새 검색어, 조합식, "
    "객체 ID를 만들지 말고 트리에 표시된 R id만 고른다.\n"
    "R 하나를 고르면 그 Heading과 하위 항·호·목·본문 전체가 답변 단계에 전달된다. "
    "질문에 답하려면 여러 가지가 필요할 수 있으므로 필요한 R을 함께 고른다. 문구만 "
    "비슷하고 행위자·행위·대상·조건이 다른 가지는 고르지 않는다. 적합한 가지가 없으면 "
    "picks를 비운다."
)


def _choose(llm, question: str, options: list[dict], *, max_picks: int,
            tree: str) -> dict:
    ids = [row["id"] for row in options]
    if llm is None or not ids:
        return {"picks": [], "reason": "선택기 없음", "overflow": 0}
    schema = {
        "type": "object",
        "properties": {
            "picks": {"type": "array",
                      "items": {"type": "string", "enum": ids}},
            "reason": {"type": "string"},
        },
        "required": ["picks", "reason"], "additionalProperties": False,
    }
    out = llm.structured(
        "rag.lazy_tree.choose", CHOOSE_SYSTEM,
        f"[질문]\n{question}\n\n[선택 상한]\n최대 {max_picks}개\n\n"
        f"[생존 근거 트리]\n{tree}", schema,
        max_tokens=700, effort="low") or {}
    allowed = set(ids)
    picks = list(dict.fromkeys(
        value for value in out.get("picks") or [] if value in allowed))
    return {
        "picks": picks[:max_picks],
        "overflow": max(0, len(picks) - max_picks),
        "reason": str(out.get("reason") or ""),
    }


def _structure_scope(index: Index, anchors: spanparts.StructureAnchors) \
        -> tuple[frozenset[tuple[str, object]] | None, str]:
    if anchors.source_coordinates and anchors.resolved:
        coordinates = frozenset(
            (doc_id, child)
            for doc_id, node in anchors.source_coordinates
            if doc_id in index.docs and node in index.docs[doc_id].by_id
            for child in spanparts.structure_descendants(index.docs[doc_id], node)
        )
        return coordinates, "resolved-structure"
    if anchors.doc_ids:
        coordinates = frozenset(
            (doc_id, node.get("id"))
            for doc_id in anchors.doc_ids if doc_id in index.docs
            for node in index.docs[doc_id].nodes
            if node.get("id") in index.docs[doc_id].by_id
        )
        return coordinates, "resolved-document"
    return None, "none"


def _rebind_selected_documents(index: Index, question: str,
                               anchors: spanparts.StructureAnchors,
                               doc_ids: set[str]) -> spanparts.StructureAnchors:
    if not doc_ids:
        return spanparts.StructureAnchors(
            doc_ids=(), documents=(), locators=anchors.locators,
            source_coordinates=(), unresolved_locators=anchors.locators,
        )
    scoped = index.scoped(doc_ids, name="DB 역매칭 문서 선택")
    resolved = spanparts.resolve_structure(scoped, question)
    ordered = tuple(sorted(doc_id for doc_id in doc_ids if doc_id in index.docs))
    return spanparts.StructureAnchors(
        doc_ids=ordered,
        documents=tuple(index.docs[doc_id].name for doc_id in ordered),
        locators=resolved.locators or anchors.locators,
        source_coordinates=resolved.source_coordinates,
        unresolved_locators=resolved.unresolved_locators,
    )


def _candidate_groups(index: Index, registry: Tier1Registry, guide, spans,
                      lexicon, *,
                      scope: frozenset[tuple[str, object]] | None,
                      candidate_limit: int,
                      role_hypotheses: dict[str, tuple[str, ...]] | None = None,
                      vector_neighbors_max: int = LEXICON_NEIGHBORS_MAX,
                      vector_min_cos: float = 0.40) \
        -> tuple[list[CandidateGroup], dict[str, dict]]:
    from lawrag.core.rag import queryguide

    by_surface, _guide_roles, concept_coords, _assertions, _max_len = \
        queryguide._concept_catalog(registry)
    roles = _concept_roles(registry)
    grouped: dict[tuple[int, int], list] = {}
    for span in spans:
        if span.role not in spanparts.PART_ROLES or span.role == "unknown":
            continue
        grouped.setdefault((span.start, span.end), []).append(span)

    prepare = getattr(lexicon, "prepare", None)
    if callable(prepare):
        needed = []
        for hypotheses in grouped.values():
            for original in hypotheses:
                expanded = tuple(spanparts.QuerySpan(
                    original.text, original.start, original.end, role,
                    original.reading_ids)
                    for role in ((role_hypotheses or {}).get(
                        original.role, (original.role,)))
                    if role in spanparts.PART_ROLES and role != "unknown")
                for span in expanded:
                    wanted_role = span.role.upper()
                    if any(
                        wanted_role in concept_roles
                        and _valid_coordinates(
                            index, concept_coords.get(cid, ()), scope=scope)
                        for cid, concept_roles in roles.items()
                    ):
                        needed.append(span.text)
                        break
        prepare(needed)

    out = []
    audit: dict[str, dict] = {}
    for (start, end), hypotheses in sorted(grouped.items()):
        group_id = f"M:{start}:{end}"
        candidates: list[Candidate] = []
        expanded = {
            (row.start, row.end, row.role): row
            for span in hypotheses
            for row in tuple(spanparts.QuerySpan(
                span.text, span.start, span.end, role, span.reading_ids)
                for role in ((role_hypotheses or {}).get(
                    span.role, (span.role,)))
                if role in spanparts.PART_ROLES and role != "unknown")
        }
        for span in expanded.values():
            candidates.extend(_direct_candidates(
                index, registry, guide, span, group_id,
                concept_coords, roles, scope=scope))
            candidates.extend(_vector_candidates(
                index, registry, lexicon, span, group_id,
                concept_coords, by_surface, roles, scope=scope,
                neighbors_max=vector_neighbors_max, min_cos=vector_min_cos))
        uncapped = _cap_candidates(
            candidates, limit=max(1, len(candidates)))
        capped = _cap_candidates(candidates, limit=candidate_limit)
        if not capped:
            continue
        group = CandidateGroup(
            id=group_id, start=start, end=end,
            surface="/".join(dict.fromkeys(span.text for span in hypotheses)),
            roles=tuple(sorted({span.role.upper() for span in expanded.values()})),
            candidates=capped,
        )
        out.append(group)
        audit[group.id] = {
            "candidate_limit": candidate_limit,
            "uncapped_count": len(uncapped),
            "capped_count": len(group.candidates),
            # 회수 전용 진단기가 어느 좌표가 상한에서 사라졌는지 판별한다.
            # 운영 meta에는 아래 객체를 직렬화하지 않는다.
            "_uncapped": uncapped,
        }
    return out, audit


def retrieve(index: Index, question: str, registry: Tier1Registry, *, llm,
             cap: int = ENTRY_SECTIONS_MAX, lexicon=None) \
        -> tuple[list[Section], dict]:
    """질문을 지연 트리로 회수하고 LLM이 고른 원문 하위 트리를 반환한다."""
    from lawrag.core.rag import queryguide

    started = time.perf_counter()
    meta = {
        "strategy": "structure_constrained_lazy_tree",
        "spans": [], "query_guide": {}, "groups": [],
        "tree_counts": {}, "combination_counts": {},
        "coordinate_option_count": 0, "option_count": 0,
        "options": [], "selected": [], "fallback": "",
    }
    if llm is None or not registry.active_concepts:
        meta["fallback"] = "LLM 또는 active Concept 없음"
        return [], meta

    anchors = spanparts.resolve_structure(index, question)
    guide = queryguide.build(index, question, registry, anchors)
    spans = spanparts.extract_spans(llm, question, guide=guide)
    # resolve_structure가 정식명/승인 별칭으로 확정한 문서는 LLM의 다른 Span
    # 해석이 취소할 수 없다. LLM은 DB 닫힌 문서 후보를 추가할 수만 있다.
    selected_docs = set(anchors.doc_ids) | queryguide.selected_document_ids(
        guide, spans, ())
    anchors = _rebind_selected_documents(
        index, question, anchors, selected_docs)
    anchors = spanparts.resolve_named_structure(index, anchors, spans)
    scope_coordinates, scope_kind = _structure_scope(index, anchors)
    meta["spans"] = [span.as_dict() for span in spans]
    meta["query_guide"] = guide.as_dict()
    meta["structure"] = {
        **anchors.as_dict(), "constraint": scope_kind,
        "coordinate_count": len(scope_coordinates or ()),
    }

    if lexicon is None:
        lexicon = spanparts.cached_term_lexicon()
    candidate_limit = CANDIDATES_PER_PART_MAX
    groups, candidate_audit = _candidate_groups(
        index, registry, guide, spans, lexicon, scope=scope_coordinates,
        candidate_limit=candidate_limit)
    meta["candidate_policy"] = {
        "scope_kind": scope_kind, "per_span_max": candidate_limit,
        "role_hypotheses": "strict",
    }
    meta["groups"] = [{
        "id": group.id, "surface": group.surface,
        "roles": list(group.roles),
        "coordinate_union_count": len(group.coordinate_union),
        "candidate_limit": candidate_audit[group.id]["candidate_limit"],
        "uncapped_count": candidate_audit[group.id]["uncapped_count"],
        "capped_count": candidate_audit[group.id]["capped_count"],
        "candidates": [{
            "role": row.role, "label": row.label, "via": row.via,
            "coordinate_count": len(row.coordinates),
            "score": round(row.score, 4),
        } for row in group.candidates],
    } for group in groups]
    if not groups and not scope_coordinates:
        meta["fallback"] = "구조 스코프와 역할 Concept 후보 없음"
        return [], meta

    nodes, counts, ordered_groups = build_lazy_tree(
        groups, scope_coordinates=scope_coordinates)
    counts_dict = counts.as_dict(len(nodes))
    meta["tree_counts"] = counts_dict
    # 저장된 평가 리더와의 필드 호환. 값의 의미는 이제 지연 트리 노드다.
    meta["combination_counts"] = counts_dict
    meta["expansion_order"] = [group.id for group in ordered_groups]

    structural_roots = frozenset(anchors.source_coordinates) \
        if anchors.source_coordinates and anchors.resolved else frozenset()
    coordinate_options = _tree_options(
        index, question, nodes, scope_coordinates=scope_coordinates,
        structural_roots=structural_roots)
    meta["coordinate_option_count"] = len(coordinate_options)
    menu = exploration_mod.build(index, coordinate_options)
    options = [row.as_dict() for row in menu.ranges]
    meta["option_count"] = len(options)
    meta["exploration"] = menu.as_dict()
    meta["options"] = [
        row.as_dict(include_outline=False) for row in menu.ranges]

    selection_cap = min(max(1, int(cap)), ENTRY_SECTIONS_MAX)
    choice = _choose(
        llm, question, options, max_picks=selection_cap,
        tree=exploration_mod.prompt_tree(menu))
    choice["picks"], redundant = exploration_mod.remove_descendant_picks(
        menu.ranges, choice["picks"])
    choice["redundant_descendants"] = redundant
    choice["edges"] = exploration_mod.selected_edges(
        menu, choice["picks"])
    meta["choice"] = choice

    option_by_id = {row["id"]: row for row in options}
    picked = [option_by_id[oid] for oid in choice["picks"] if oid in option_by_id]
    meta["selected"] = [{
        "id": row["id"], "doc_id": row["doc_id"], "node": row["node"],
        "doc": row["doc"], "path": row["path"],
        "heading": row["heading"], "channels": row["channels"],
        "matched": row["matched"], "signals": row["signals"],
        "candidate_coordinates": row["candidate_coordinates"],
    } for row in picked]
    if not picked:
        meta["fallback"] = "생존 트리에서 LLM 선택 없음"
        meta["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        return [], meta

    sections = []
    for row in picked:
        view = index.docs[row["doc_id"]]
        section = view.by_id[row["node"]]
        surfaces = " · ".join(dict.fromkeys(
            item["surface"] for item in row["matched"] if item["surface"]))
        sections.append(Section(
            n=0, doc_id=row["doc_id"], doc=view.name, node=row["node"],
            path=view.path(row["node"]) or view.name,
            page=section.get("page"), kind="지연트리선택",
            matched=f"lazy_tree — {surfaces}"[:160],
            text=exploration_mod.subtree_text(view, row["node"], cap=None),
            edges=[edge for edge in choice["edges"]
                   if edge.get("from") == row["id"]
                   or edge.get("to") == row["id"]],
        ))
    meta["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return sections, meta
