"""닫힌 후보 메뉴에서만 법률 proof witness를 검증한다.

이 모듈은 LLM의 판단을 다시 해석하지 않는다. 호출부가 공개한 ``candidate_id``와
stable relation ``edge_id``만 받아, 실제 :class:`Index` 원문과
``relations.RelationBundle``에 다시 대조한다. 후보 조문이 어떤 facet 근처에 있다는
``span`` 관측과, 그 facet을 정확한 원문 구간으로 증명했다는 ``witness``는 별도다.

검증 결과의 ``status`` 계약은 다음과 같다.

``complete``
    모든 필수 facet에 오류 없는 exact witness가 있다.
``partial``
    제출된 witness는 모두 유효하지만 아직 필수 facet이 남았다.
``invalid``
    가짜 candidate/edge, 틀린 source span, 연결되지 않은 companion 등 신뢰할 수
    없는 주장이 하나라도 있다. 유효한 일부 witness는 감사용으로 그대로 반환한다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from lawrag.core.domain_graph.model import stable_id
from lawrag.core.rag import legal_coordinates, relations
from lawrag.core.rag.index import Index


@dataclass(frozen=True)
class ClosedEdge:
    """LLM에 공개할 수 있는 실제 SectionRelation의 안정 식별자.

    ``from``/``to``는 탐색 방향이고, ``src``/``dst``는 관계 정본의 방향이다.
    따라서 같은 정본 간선을 역방향으로 걷는 메뉴도 의미를 잃지 않는다.
    """

    edge_id: str
    from_candidate_id: str
    to_candidate_id: str
    kind: str
    direction: str
    src_doc_id: str
    src_node: object
    dst_doc_id: str
    dst_node: object

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def stable_edge_id(edge: relations.SectionRelation, direction: str) -> str:
    """메뉴 순서와 무관한 relation traversal ID를 만든다."""
    if direction not in {"out", "in"}:
        raise ValueError("direction은 out 또는 in이어야 합니다")
    return stable_id(
        "witness-edge", edge.kind, edge.src_doc, edge.src_node,
        edge.dst_doc, edge.dst_node, direction,
    )


def _canonical_coordinate(index: Index, branch: object) \
        -> tuple[str, object] | None:
    doc_id = str(getattr(branch, "doc_id", "") or "")
    node = getattr(branch, "node", None)
    view = index.docs.get(doc_id)
    if view is None or node not in view.by_id:
        return None
    root = legal_coordinates.article_root(view, node)
    if root not in view.by_id:
        return None
    return doc_id, root


def _source_text(index: Index, branch: object) -> str | None:
    coordinate = _canonical_coordinate(index, branch)
    if coordinate is None:
        return None
    view = index.docs[coordinate[0]]
    # TermBranch.body는 폭주 방지를 위해 잘릴 수 있다. witness는 정본 전체에서
    # 검증해야 뒤쪽 항·호의 정확한 인용도 거짓 음성이 되지 않는다.
    return legal_coordinates.subtree_text(view, coordinate[1], cap=None)


def _source_blocks(index: Index, branch: object) -> str | None:
    """구조 표시(``▸``)를 제외한 실제 block 원문을 돌려준다."""
    coordinate = _canonical_coordinate(index, branch)
    if coordinate is None:
        return None
    view = index.docs[coordinate[0]]
    node = view.by_id[coordinate[1]]
    start, end = node.get("span") or [0, 0]
    parts = []
    for block_idx in range(start, max(end, start + 1)):
        block = view.block_by_idx.get(block_idx)
        text = str((block or {}).get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _eligible_relation(edge: relations.SectionRelation) -> bool:
    status = str(edge.props.get("status") or "")
    return (not edge.kind.startswith("MAY_")
            and status in {"", "resolved"})


def build_closed_edge_menu(
    index: Index,
    candidates: Mapping[str, object],
    *,
    kinds: Iterable[str] | None = None,
) -> dict[str, ClosedEdge]:
    """후보 메뉴 안의 실제 관계만 stable ID의 닫힌 메뉴로 만든다.

    이 함수가 반환하지 않은 ID는 validator가 받아들이지 않는다. ``MAY_*``와
    미해결 관계는 탐색 힌트일 수는 있어도 witness를 완성할 수 없어 제외한다.
    """
    allowed = set(kinds) if kinds is not None else None
    by_coordinate: dict[tuple[str, object], list[str]] = {}
    for candidate_id, branch in candidates.items():
        coordinate = _canonical_coordinate(index, branch)
        if coordinate is not None:
            by_coordinate.setdefault(coordinate, []).append(str(candidate_id))

    out: dict[str, ClosedEdge] = {}
    for from_id, branch in candidates.items():
        source = _canonical_coordinate(index, branch)
        if source is None:
            continue
        outgoing, incoming = relations.incident(index, *source)
        streams = (("out", outgoing), ("in", incoming))
        for direction, rows in streams:
            for edge in rows:
                if (not _eligible_relation(edge)
                        or (allowed is not None and edge.kind not in allowed)):
                    continue
                target = ((edge.dst_doc, edge.dst_node) if direction == "out"
                          else (edge.src_doc, edge.src_node))
                for to_id in by_coordinate.get(target, ()):
                    if str(from_id) == to_id:
                        continue
                    edge_id = stable_edge_id(edge, direction)
                    out.setdefault(edge_id, ClosedEdge(
                        edge_id=edge_id,
                        from_candidate_id=str(from_id),
                        to_candidate_id=to_id,
                        kind=edge.kind,
                        direction=direction,
                        src_doc_id=edge.src_doc,
                        src_node=edge.src_node,
                        dst_doc_id=edge.dst_doc,
                        dst_node=edge.dst_node,
                    ))
    return out


def _coerce_edge(value: object) -> ClosedEdge | None:
    if isinstance(value, ClosedEdge):
        return value
    if not isinstance(value, Mapping):
        return None
    try:
        return ClosedEdge(
            edge_id=str(value.get("edge_id") or ""),
            from_candidate_id=str(value.get("from_candidate_id") or ""),
            to_candidate_id=str(value.get("to_candidate_id") or ""),
            kind=str(value.get("kind") or ""),
            direction=str(value.get("direction") or ""),
            src_doc_id=str(value.get("src_doc_id") or ""),
            src_node=value.get("src_node"),
            dst_doc_id=str(value.get("dst_doc_id") or ""),
            dst_node=value.get("dst_node"),
        )
    except (TypeError, ValueError):
        return None


def _edge_error(
    index: Index,
    candidates: Mapping[str, object],
    menu_key: str,
    edge: ClosedEdge,
) -> str | None:
    if edge.direction not in {"out", "in"}:
        return "edge_direction_invalid"
    canonical = relations.SectionRelation(
        edge.kind, edge.src_doc_id, edge.src_node,
        edge.dst_doc_id, edge.dst_node, {"status": "resolved"},
    )
    if not edge.edge_id or edge.edge_id != menu_key \
            or stable_edge_id(canonical, edge.direction) != edge.edge_id:
        return "edge_id_not_stable"
    if edge.kind.startswith("MAY_"):
        return "uncertain_edge_cannot_close_witness"

    from_branch = candidates.get(edge.from_candidate_id)
    to_branch = candidates.get(edge.to_candidate_id)
    from_coordinate = (_canonical_coordinate(index, from_branch)
                       if from_branch is not None else None)
    to_coordinate = (_canonical_coordinate(index, to_branch)
                     if to_branch is not None else None)
    if from_coordinate is None or to_coordinate is None:
        return "edge_candidate_unknown_or_invalid"
    expected_from = ((edge.src_doc_id, edge.src_node)
                     if edge.direction == "out"
                     else (edge.dst_doc_id, edge.dst_node))
    expected_to = ((edge.dst_doc_id, edge.dst_node)
                   if edge.direction == "out"
                   else (edge.src_doc_id, edge.src_node))
    if from_coordinate != expected_from or to_coordinate != expected_to:
        return "edge_candidate_mismatch"

    outgoing, incoming = relations.incident(index, *from_coordinate)
    rows = outgoing if edge.direction == "out" else incoming
    key = (edge.kind, edge.src_doc_id, edge.src_node,
           edge.dst_doc_id, edge.dst_node)
    if not any(row.key == key and _eligible_relation(row) for row in rows):
        return "edge_not_in_index"
    return None


def _source_span(value: object) -> tuple[int, int] | None:
    if isinstance(value, Mapping):
        start, end = value.get("start"), value.get("end")
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        start, end = value
    else:
        return None
    if (isinstance(start, bool) or isinstance(end, bool)
            or not isinstance(start, int) or not isinstance(end, int)):
        return None
    return start, end


def _ordered_unique(values: Iterable[object]) -> list[str]:
    return list(dict.fromkeys(
        str(value).strip() for value in values if str(value).strip()))


def validate_witness(
    index: Index,
    candidates: Mapping[str, object],
    required_facets: Iterable[str],
    proposal: Mapping[str, object] | None,
    *,
    closed_edges: Mapping[str, ClosedEdge | Mapping[str, object]] | None = None,
    companion_facets: Iterable[str] = (),
) -> dict[str, Any]:
    """LLM witness 제안을 실제 원문과 닫힌 메뉴에 대해 검증한다.

    ``proposal`` 형식은 ``{"witnesses": [...]}``이다. 각 witness는
    ``facet``, ``candidate_id``, ``quote``, ``source_span``을 가져야 한다.
    companion facet은 추가로 ``source_candidate_id``와 ``edge_id``를 가져야
    하며, edge의 탐색 출발/도착 candidate와 정확히 일치해야 한다.

    ``span_covered_facets``는 실재하는 closed candidate를 가리킨 facet이다.
    ``covered_facets``는 quote/span 및 필요한 edge까지 모두 검증된 facet이다.
    전자는 후자를 대신해 ``complete``를 만들 수 없다.
    """
    required = _ordered_unique(required_facets)
    required_set = set(required)
    companion_set = set(_ordered_unique(companion_facets))
    edge_menu = dict(closed_edges or {})
    errors: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    span_covered: set[str] = set()
    covered: set[str] = set()

    def reject(position: int | None, code: str, **details: Any) -> None:
        error = {"code": code, **details}
        if position is not None:
            error["witness"] = position
        errors.append(error)
        if position is not None:
            rejected.append(error)

    if not required:
        reject(None, "no_required_facets")
    if not isinstance(proposal, Mapping):
        reject(None, "proposal_not_object")
        witness_rows: list[object] = []
    else:
        raw_rows = proposal.get("witnesses", [])
        if not isinstance(raw_rows, list):
            reject(None, "witnesses_not_array")
            witness_rows = []
        else:
            witness_rows = raw_rows

    for position, raw in enumerate(witness_rows, start=1):
        if not isinstance(raw, Mapping):
            reject(position, "witness_not_object")
            continue
        facet = str(raw.get("facet") or "").strip()
        candidate_id = str(raw.get("candidate_id") or "")
        row_errors_before = len(errors)
        if facet not in required_set:
            reject(position, "facet_not_in_closed_requirements", facet=facet)
            continue
        branch = candidates.get(candidate_id)
        if branch is None:
            reject(position, "candidate_id_not_in_closed_menu",
                   facet=facet, candidate_id=candidate_id)
            continue
        coordinate = _canonical_coordinate(index, branch)
        source = _source_text(index, branch)
        source_blocks = _source_blocks(index, branch)
        if coordinate is None or source is None or source_blocks is None:
            reject(position, "candidate_coordinate_invalid",
                   facet=facet, candidate_id=candidate_id)
            continue

        # 단순 coordinate span은 여기서 충족된다. 이후 quote나 edge가 틀려도
        # witness coverage로 승격하지 않는다.
        span_covered.add(facet)
        quote = raw.get("quote")
        span = _source_span(raw.get("source_span"))
        if not isinstance(quote, str) or not quote:
            reject(position, "quote_missing", facet=facet,
                   candidate_id=candidate_id)
        if span is None:
            reject(position, "source_span_invalid", facet=facet,
                   candidate_id=candidate_id)
        elif (span[0] < 0 or span[1] <= span[0] or span[1] > len(source)):
            reject(position, "source_span_out_of_bounds", facet=facet,
                   candidate_id=candidate_id, source_span=list(span))
        elif isinstance(quote, str) and source[span[0]:span[1]] != quote:
            reject(position, "quote_not_exact_source_span", facet=facet,
                   candidate_id=candidate_id, source_span=list(span))
        elif isinstance(quote, str) and quote not in source_blocks:
            reject(position, "quote_not_in_source_blocks", facet=facet,
                   candidate_id=candidate_id, source_span=list(span))

        needs_edge = (facet in companion_set
                      or bool(raw.get("edge_id"))
                      or bool(raw.get("source_candidate_id")))
        edge: ClosedEdge | None = None
        if needs_edge:
            source_candidate_id = str(raw.get("source_candidate_id") or "")
            edge_id = str(raw.get("edge_id") or "")
            if not source_candidate_id or not edge_id:
                reject(position, "companion_edge_required", facet=facet,
                       candidate_id=candidate_id)
            elif edge_id not in edge_menu:
                reject(position, "edge_id_not_in_closed_menu", facet=facet,
                       candidate_id=candidate_id, edge_id=edge_id)
            else:
                edge = _coerce_edge(edge_menu[edge_id])
                if edge is None:
                    reject(position, "closed_edge_malformed", facet=facet,
                           edge_id=edge_id)
                else:
                    edge_error = _edge_error(
                        index, candidates, edge_id, edge)
                    if edge_error:
                        reject(position, edge_error, facet=facet,
                               candidate_id=candidate_id, edge_id=edge_id)
                    elif (edge.from_candidate_id != source_candidate_id
                          or edge.to_candidate_id != candidate_id):
                        reject(position, "edge_does_not_connect_companion",
                               facet=facet, candidate_id=candidate_id,
                               source_candidate_id=source_candidate_id,
                               edge_id=edge_id)

        if len(errors) == row_errors_before:
            covered.add(facet)
            receipt: dict[str, Any] = {
                "facet": facet,
                "candidate_id": candidate_id,
                "coordinate": [coordinate[0], coordinate[1]],
                "quote": quote,
                "source_span": [span[0], span[1]] if span else None,
            }
            if edge is not None:
                receipt.update(
                    edge_id=edge.edge_id,
                    source_candidate_id=edge.from_candidate_id,
                )
            accepted.append(receipt)

    covered_ordered = [facet for facet in required if facet in covered]
    span_ordered = [facet for facet in required if facet in span_covered]
    missing = [facet for facet in required if facet not in covered]
    if errors:
        status = "invalid"
    elif missing:
        status = "partial"
    else:
        status = "complete"
    return {
        "status": status,
        "complete": status == "complete",
        "span_covered_facets": span_ordered,
        "covered_facets": covered_ordered,
        "span_only_facets": [facet for facet in span_ordered
                             if facet not in covered],
        "missing_facets": missing,
        "errors": errors,
        "accepted_witnesses": accepted,
        "rejected_witnesses": rejected,
    }


# 짧은 이름도 공개하되 정본 구현은 validate_witness 하나다.
validate = validate_witness
