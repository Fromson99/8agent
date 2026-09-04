"""피드백 탐색이 ``RelationBundle``을 걷는 제한된 Section 간선 facade.

관계의 생성·해소·provenance 정본은 :mod:`lawrag.core.rag.relations` 하나다.
이 모듈은 SQLite나 delegation 파일을 다시 읽지 않고, 선택된 조문에 대한
``relations.incident()`` 결과를 방향·관계별 상한으로 잘라 닫힌 ``E`` 메뉴로
바꾼다. Requirement와 Document endpoint는 조문 후보가 아니므로 여기서 승격하지
않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag import relations
from lawrag.core.rag.index import Index


@dataclass(frozen=True)
class RelationRule:
    label: str
    mandatory_out: bool
    mandatory_in: bool
    out_cap: int
    in_cap: int
    priority: int


# 실제 graph 차수의 p95와 법적 방향성을 기준으로 한 피드백 메뉴 상한이다.
# 특히 정의조 → 모든 사용조문은 최대 720개까지 열리므로 역방향을 금지한다.
RULES: dict[str, RelationRule] = {
    "EXCLUDES": RelationRule("배제", True, True, 2, 2, 0),
    "DELEGATES_TO": RelationRule("위임", True, True, 4, 4, 1),
    "RECEIVES_FROM": RelationRule("수임", True, True, 3, 3, 2),
    "INCORPORATES": RelationRule("준용", True, False, 2, 3, 3),
    "USES_DEFINITION": RelationRule("정의적용", True, False, 4, 0, 4),
    "VIOLATION_SANCTIONED_BY": RelationRule("제재", True, True, 2, 2, 5),
    "DEEMS": RelationRule("의제", True, False, 2, 2, 6),
    # 시점 관계는 피드백 판정자가 질문의 사건일·적용시점 결손을 본 뒤 고른다.
    "APPLIES_TO": RelationRule("적용례", False, False, 2, 2, 7),
    "TRANSITION_FOR": RelationRule("경과조치", False, False, 2, 2, 8),
    "EFFECTIVE_FOR": RelationRule("시행일", False, False, 2, 2, 9),
    "AMENDS": RelationRule("개정", False, False, 2, 2, 10),
    "BASED_ON": RelationRule("근거", False, False, 2, 2, 20),
    "REFERENCES": RelationRule("인용", False, False, 2, 2, 21),
}


@dataclass(frozen=True)
class RelationHop:
    source_doc_id: str
    source_node: object
    target_doc_id: str
    target_node: object
    relation: str
    direction: str
    provenance: str
    surface: str = ""
    graph_kind: str = ""
    mandatory: bool = False
    edge_id: str = ""

    @property
    def target(self) -> tuple[str, object]:
        return self.target_doc_id, self.target_node

    def as_dict(self, index: Index | None = None) -> dict:
        row = {
            "id": self.edge_id,
            "source_doc_id": self.source_doc_id,
            "source_node": self.source_node,
            "target_doc_id": self.target_doc_id,
            "target_node": self.target_node,
            "relation": self.relation,
            "direction": self.direction,
            "provenance": self.provenance,
            "surface": self.surface,
            "graph_kind": self.graph_kind,
            "mandatory": self.mandatory,
        }
        if index is not None and self.target_doc_id in index.docs:
            view = index.docs[self.target_doc_id]
            row.update(target_doc=view.name,
                       target_path=view.path(self.target_node) or view.name)
        return row


@dataclass(frozen=True)
class ProvisoPackage:
    proviso_id: str
    source_doc_id: str
    source_node: object
    source_article: object
    source_block: object
    cue: str
    body: str
    parent_text: str
    effect_kind: str
    scope_status: str
    relations: tuple[dict, ...]
    route_targets: tuple[dict, ...]

    def as_dict(self) -> dict:
        return {
            "proviso_id": self.proviso_id,
            "source_doc_id": self.source_doc_id,
            "source_node": self.source_node,
            "source_article": self.source_article,
            "source_block": self.source_block,
            "cue": self.cue, "body": self.body,
            "parent_text": self.parent_text,
            "effect_kind": self.effect_kind,
            "scope_status": self.scope_status,
            "relations": list(self.relations),
            "route_targets": list(self.route_targets),
        }


def _root(index: Index, doc_id: str, node: object) -> tuple[str, object] | None:
    view = index.docs.get(doc_id)
    if view is None or node not in view.by_id:
        return None
    article = coordinates.article_root(view, node)
    return (doc_id, article) if article in view.by_id else None


def _provenance(edge: relations.SectionRelation) -> str:
    raw = edge.props.get("provenance") or ()
    values = [raw] if isinstance(raw, str) else list(raw)
    return "·".join(str(value) for value in values if str(value)) or "relations"


def _surface(edge: relations.SectionRelation) -> str:
    return str(edge.props.get("surface") or edge.props.get("link")
               or edge.props.get("term") or edge.label)


def neighbors(index: Index, seeds: Iterable[tuple[str, object]], *,
              direction: str = "both", cap: int = 24,
              exclude: Iterable[tuple[str, object]] = (),
              kinds: Iterable[str] | None = None) -> tuple[list[RelationHop], dict]:
    """선택 조문의 Section 이웃을 정책 상한 안에서 닫힌 간선 메뉴로 반환한다."""
    if direction not in {"out", "in", "both"}:
        raise ValueError("direction은 out | in | both 중 하나여야 합니다")
    allowed = set(kinds or RULES)
    normalized = []
    for doc_id, node in seeds:
        value = _root(index, doc_id, node)
        if value is not None and value not in normalized:
            normalized.append(value)
    blocked = set(exclude) | set(normalized)
    rows: list[tuple[int, int, int, RelationHop]] = []
    rejected_by_policy: dict[str, int] = {}

    for seed_order, seed in enumerate(normalized):
        outgoing, incoming = relations.incident(index, *seed)
        streams = []
        if direction in {"out", "both"}:
            streams.append(("out", outgoing))
        if direction in {"in", "both"}:
            streams.append(("in", incoming))
        for edge_direction, edges in streams:
            counts: dict[str, int] = {}
            for edge in edges:
                rule = RULES.get(edge.kind)
                if rule is None or edge.kind not in allowed:
                    continue
                limit = rule.out_cap if edge_direction == "out" else rule.in_cap
                if limit <= 0 or counts.get(edge.kind, 0) >= limit:
                    rejected_by_policy[edge.kind] = (
                        rejected_by_policy.get(edge.kind, 0) + 1)
                    continue
                target_raw = ((edge.dst_doc, edge.dst_node)
                              if edge_direction == "out"
                              else (edge.src_doc, edge.src_node))
                target = _root(index, *target_raw)
                if target is None or target in blocked:
                    continue
                counts[edge.kind] = counts.get(edge.kind, 0) + 1
                mandatory = (rule.mandatory_out if edge_direction == "out"
                             else rule.mandatory_in)
                rows.append((rule.priority, counts[edge.kind], seed_order, RelationHop(
                    source_doc_id=seed[0], source_node=seed[1],
                    target_doc_id=target[0], target_node=target[1],
                    relation=rule.label, direction=edge_direction,
                    provenance=_provenance(edge), surface=_surface(edge),
                    graph_kind=edge.kind, mandatory=mandatory)))

    deduped: list[tuple[int, int, int, RelationHop]] = []
    seen = set()
    for priority, relation_order, seed_order, hop in sorted(rows, key=lambda item: (
            not item[3].mandatory, item[0], item[1], item[2],
            item[3].target_doc_id, str(item[3].target_node),
            item[3].graph_kind, item[3].direction)):
        key = (hop.source_doc_id, hop.source_node, hop.target_doc_id,
               hop.target_node, hop.graph_kind, hop.direction)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((priority, relation_order, seed_order, hop))
    selected = [replace(hop, edge_id=f"E{pos}")
                for pos, (_priority, _relation_order, _seed_order, hop) in enumerate(
                    deduped[:max(0, int(cap))], start=1)]
    counts: dict[str, int] = {}
    for hop in selected:
        counts[hop.graph_kind] = counts.get(hop.graph_kind, 0) + 1
    return selected, {
        "source": "relations.RelationBundle",
        "seed_count": len(normalized), "candidate_count": len(deduped),
        "selected_count": len(selected), "by_kind": counts,
        "rejected_by_policy": rejected_by_policy, "direction": direction,
    }


def proviso_packages(index: Index, seeds: Iterable[tuple[str, object]], *,
                     cap: int = 48, target_text_cap: int = 12000) \
        -> tuple[list[ProvisoPackage], dict]:
    """선택 조문에 붙은 단서와 그 외부 탐색 대상을 한 번에 제시한다.

    외부 대상은 관계가 가리키는 조문 전체 outline을 제공한다. 이는 검색 경로일 뿐
    단서의 법적 효과가 외부 조문에 미친다고 자동 판정하지 않는다.
    """
    normalized = []
    for doc_id, node in seeds:
        value = _root(index, doc_id, node)
        if value is not None and value not in normalized:
            normalized.append(value)
    bundle = relations.build(index)
    packages = []
    by_plane: dict[str, int] = {}
    routed = 0
    for doc_id, article in normalized:
        for span, edges in bundle.proviso_incident(doc_id, article):
            relation_rows, targets = [], []
            target_seen = set()
            for edge in edges:
                by_plane[edge.plane] = by_plane.get(edge.plane, 0) + 1
                relation_rows.append({
                    "plane": edge.plane, "kind": edge.kind,
                    "dst_kind": edge.dst_kind, "dst_doc": edge.dst_doc,
                    "dst_node": edge.dst_node, "props": dict(edge.props),
                })
                if edge.plane != "SEARCH_ROUTING":
                    continue
                key = (edge.dst_kind, edge.dst_doc, edge.dst_node)
                if key in target_seen:
                    continue
                target_seen.add(key)
                view = index.docs.get(edge.dst_doc)
                if view is None:
                    continue
                target = {
                    "route_kind": edge.kind, "doc_id": edge.dst_doc,
                    "document": view.name, "node": edge.dst_node,
                    "confidence": edge.props.get("confidence", ""),
                    "legal_effect_inferred": False,
                }
                if edge.dst_kind == "section" and edge.dst_node in view.by_id:
                    target.update(
                        path=view.path(edge.dst_node),
                        text=view.section_outline(
                            view.by_id[edge.dst_node], cap=target_text_cap))
                targets.append(target)
                routed += 1
            packages.append(ProvisoPackage(
                proviso_id=span.proviso_id, source_doc_id=span.doc_id,
                source_node=span.node, source_article=span.article,
                source_block=span.block, cue=span.cue, body=span.body,
                parent_text=span.parent_text, effect_kind=span.effect_kind,
                scope_status=span.scope_status,
                relations=tuple(relation_rows), route_targets=tuple(targets)))
            if len(packages) >= max(0, int(cap)):
                return packages, {
                    "source": "relations.RelationBundle.proviso_relations",
                    "seed_count": len(normalized), "selected_count": len(packages),
                    "routed_target_count": routed, "by_plane": by_plane,
                    "truncated": True,
                }
    return packages, {
        "source": "relations.RelationBundle.proviso_relations",
        "seed_count": len(normalized), "selected_count": len(packages),
        "routed_target_count": routed, "by_plane": by_plane,
        "truncated": False,
    }
