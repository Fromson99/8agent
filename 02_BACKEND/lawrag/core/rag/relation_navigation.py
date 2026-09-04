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
