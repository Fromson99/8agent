"""LegalClosure 선택 좌표에 규범요건 span과 시점·법원성 메타를 붙인다."""

from __future__ import annotations

from lawrag.core.domain_graph import requirements
from lawrag.core.rag import legal_validity
from lawrag.core.rag import legal_coordinates as coordinates
from lawrag.runtime.content_snapshot import (
    ContentSnapshotError,
    artifact_provenance_receipt,
    current_content_snapshot,
)
from lawrag.core.rag.index import Index


def annotate(index: Index, question: str, selected: list[coordinates.Branch], *,
             text_cache: dict[coordinates.Coordinate, str] | None = None) -> dict:
    requested = requirements.requested_kinds(question)
    as_of = legal_validity.parse_as_of(question)
    cache = text_cache if text_cache is not None else {}
    rows, warnings = [], []
    snapshot = getattr(index, "content_snapshot", None)
    process_snapshot = current_content_snapshot()
    if (snapshot is not None and process_snapshot is not None
            and snapshot.content_snapshot_sha256
            != process_snapshot.content_snapshot_sha256):
        raise ContentSnapshotError(
            "legal evidence index and process snapshots disagree")
    if snapshot is None:
        snapshot = process_snapshot
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
        view = index.docs[branch.doc_id]
        provenance = (getattr(view, "content_provenance", None)
                      or getattr(view, "artifact_provenance", None))
        if snapshot is not None:
            expected = snapshot.provenance_for_document(branch.doc_id)
            if provenance is not None and provenance != expected:
                raise ContentSnapshotError(
                    "legal evidence artifact provenance disagrees with snapshot")
            provenance = expected
        row = {
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
        }
        receipt = artifact_provenance_receipt(provenance)
        if receipt is not None:
            row["content_provenance"] = receipt
        rows.append(row)
    result = {
        "requested_kinds": list(requested),
        "as_of": as_of.isoformat() if as_of else "",
        "warnings": warnings,
        "rows": rows,
    }
    if snapshot is not None:
        result["content_snapshot"] = snapshot.compact_receipt()
    return result
