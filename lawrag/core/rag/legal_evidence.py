"""LegalClosure 선택 좌표에 규범요건 span과 시점·법원성 메타를 붙인다."""

from __future__ import annotations

from lawrag.core.domain_graph import requirements
from lawrag.core.rag import legal_validity
from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.core.rag.index import Index


def annotate(index: Index, question: str, selected: list[coordinates.Branch], *,
             text_cache: dict[coordinates.Coordinate, str] | None = None) -> dict:
    requested = requirements.requested_kinds(question)
    as_of = legal_validity.parse_as_of(question)
    cache = text_cache if text_cache is not None else {}
    rows, warnings = [], []
    for branch in selected:
        text = cache.get(branch.coordinate)
        if text is None:
            text = coordinates.subtree_text(
                index.docs[branch.doc_id], branch.node, cap=None)
            cache[branch.coordinate] = text
        spans = requirements.extract(text)
        requested_spans = [row for row in spans if row.kind in requested]
        ordered = sorted(requested_spans or spans, key=lambda row: (
            row.start, row.kind))[:3]
        validity = legal_validity.validate_document(index.docs[branch.doc_id], as_of)
        if validity.warning and validity.warning not in warnings:
            warnings.append(validity.warning)
        rows.append({
            "doc_id": branch.doc_id, "node": branch.node,
            "requested_kinds": list(requested),
            "present_kinds": sorted({row.kind for row in spans}),
            "requirement_spans": [{
                **row.as_dict(),
                "surface": (row.surface[:160] + "…")
                    if len(row.surface) > 160 else row.surface,
                "surface_truncated": len(row.surface) > 160,
            } for row in ordered],
            "validity": validity.as_dict(),
        })
    return {"requested_kinds": list(requested), "as_of": as_of.isoformat() if as_of else "",
            "warnings": warnings, "rows": rows}
