"""Gold-free LegalClosure article reachability and lifecycle accounting.

The product path records only observed retrieval attempts and canonical article
coordinates.  Gold coordinates are joined later by :func:`grade_capture`, so
the trace cannot influence retrieval selection.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

from lawrag.core.rag.content_snapshot import (
    ContentSnapshotError,
    current_content_snapshot,
)
from lawrag.core.rag.experiments import retrieval_stage_ledger as stage_ledger


SCHEMA_VERSION = "legalclosure-article-reachability-capture-v1"
GRADED_SCHEMA_VERSION = "legalclosure-article-reachability-graded-v1"

REASON_CODES = frozenset({
    "selected",
    "generated",
    "no_term_extracted",
    "term_not_in_question",
    "term_too_short",
    "term_corpus_miss",
    "operation_term_ungrounded",
    "explicit_reference_unresolved",
    "no_document_hit",
    "document_out_of_scope",
    "document_not_selected",
    "wrong_document_family",
    "wrong_generation",
    "document_cap_dropped",
    "form_filtered",
    "no_node_hit",
    "node_not_article",
    "article_not_selected",
    "article_cap_dropped",
    "optional_review_dropped",
    "deduplicated",
    "definition_compacted",
    "final_cap_dropped",
    "final_scope_dropped",
    "context_build_failed",
    "no_outgoing_relation",
    "relation_unresolved",
    "relation_target_missing",
    "relation_not_mandatory",
    "relation_query_mismatch",
    "relation_cap_dropped",
    "seed_fairness_dropped",
    "reference_ambiguous",
    "reference_no_match",
    "no_remaining_slot",
    "no_concept_match",
    "no_assertion_match",
    "assertion_not_selected",
    "assertion_route_failed",
    "tree_route_failed",
    "shortcut_signature_miss",
    "shortcut_fingerprint_miss",
    "shortcut_ambiguous",
    "shortcut_target_missing",
    "not_applicable",
})

CHANNELS = (
    "A_EXACT",
    "B_ASSERTION",
    "C_BM25",
    "D_CLOSURE",
    "REFERENCE_RESCUE",
    "MERGE",
    "SCOPE",
    "PRESENT",
)


def _coordinate(value: object | None) -> tuple[str, int] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        doc_id, node = value.get("doc_id"), value.get("node")
    else:
        doc_id, node = tuple(value)  # type: ignore[arg-type]
    if isinstance(node, str) and node.isdigit():
        node = int(node)
    if not str(doc_id or "").strip() or isinstance(node, bool) \
            or not isinstance(node, int) or node < 0:
        raise ValueError(f"invalid article coordinate: {(doc_id, node)!r}")
    return str(doc_id), node


def _identity(value: object | None) -> dict[str, Any] | None:
    coordinate = _coordinate(value)
    if coordinate is None:
        return None
    return {"doc_id": coordinate[0], "node": coordinate[1]}


def _identity_key(value: Mapping[str, Any]) -> tuple[str, int]:
    return str(value["doc_id"]), int(value["node"])


def _forbid_gold(value: object, path: str = "capture") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if (str(key) != "gold_visible_to_product"
                    and "gold" in str(key).lower()) or str(key) in {
                    "expected_articles", "reference_answer"}:
                raise ValueError(f"gold field is forbidden in product trace: {path}.{key}")
            _forbid_gold(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _forbid_gold(child, f"{path}[{index}]")


class ArticleReachabilityTrace:
    """Record stage snapshots and candidate/negative-attempt lifecycle events."""

    def __init__(self, index, case_id: str, arm_id: str = "traced-v2", *,
                 content_snapshot: Any = None):
        self.case_id = str(case_id).strip()
        self.arm_id = str(arm_id).strip()
        if not self.case_id or not self.arm_id:
            raise ValueError("case_id and arm_id are required")
        self._canonicalizer = stage_ledger.index_article_root_canonicalizer(index)
        self._ledger = stage_ledger.StageLedgerRecorder(
            self.case_id, self.arm_id, self._canonicalizer)
        self._events: list[dict[str, Any]] = []
        index_snapshot = getattr(index, "content_snapshot", None)
        process_snapshot = current_content_snapshot()
        self._content_snapshot = (
            content_snapshot if content_snapshot is not None else
            index_snapshot if index_snapshot is not None else
            process_snapshot)
        identities = [value for value in (
            content_snapshot, index_snapshot, process_snapshot) if value is not None]
        hashes = {
            str(getattr(value, "content_snapshot_sha256", "")
                or (value.get("content_snapshot_sha256")
                    if isinstance(value, Mapping) else ""))
            for value in identities
        }
        if "" in hashes:
            raise ContentSnapshotError("reachability snapshot identity is incomplete")
        if len(hashes) > 1:
            raise ContentSnapshotError(
                "reachability index and process snapshots disagree")
        self._document_ids: set[str] = set()

    def _artifact_receipt(self, doc_id: str) -> dict[str, Any] | None:
        snapshot = self._content_snapshot
        if snapshot is None:
            return None
        if hasattr(snapshot, "provenance_for_document"):
            artifact = snapshot.provenance_for_document(doc_id)
            return artifact.receipt()
        if isinstance(snapshot, Mapping):
            if "artifacts" not in snapshot:
                raise ContentSnapshotError(
                    "compact content snapshot cannot supply reachability provenance")
            rows = [
                dict(row) for row in snapshot.get("artifacts", ())
                if isinstance(row, Mapping) and row.get("document_id") == doc_id
            ]
            if len(rows) > 1:
                raise ValueError(f"ambiguous content provenance: {doc_id}")
            if not rows:
                raise ContentSnapshotError(
                    f"unmapped reachability document: {doc_id}")
            return rows[0]
        raise TypeError("content_snapshot must provide provenance_for_document()")

    def _snapshot_receipt(self) -> dict[str, Any] | None:
        snapshot = self._content_snapshot
        if snapshot is None:
            return None
        if hasattr(snapshot, "compact_receipt"):
            return snapshot.compact_receipt()
        if isinstance(snapshot, Mapping):
            return dict(snapshot)
        raise TypeError("content_snapshot must provide compact_receipt()")

    def canonical(self, value: object) -> tuple[str, int]:
        coordinate = _coordinate(value)
        if coordinate is None:
            raise ValueError("coordinate is required")
        return _coordinate(self._canonicalizer(coordinate))  # type: ignore[return-value]

    def event(
        self,
        channel: str,
        task: str,
        decision: str,
        reason_code: str,
        *,
        raw_coordinate: object | None = None,
        article_coordinate: object | None = None,
        source_coordinate: object | None = None,
        trigger_type: str = "",
        trigger_value: object = None,
        rank: int | None = None,
        score: float | None = None,
        mandatory: bool = False,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        channel_name = str(channel).strip()
        if channel_name not in CHANNELS:
            raise ValueError(f"unsupported channel: {channel_name}")
        reason = str(reason_code).strip()
        if reason not in REASON_CODES:
            raise ValueError(f"unsupported reason code: {reason}")
        raw = _coordinate(raw_coordinate)
        article = (_coordinate(article_coordinate)
                   if article_coordinate is not None else
                   (self.canonical(raw) if raw is not None else None))
        event = {
            "event_no": len(self._events) + 1,
            "channel": channel_name,
            "task": str(task).strip(),
            "decision": str(decision).strip(),
            "reason_code": reason,
            "raw_coordinate": _identity(raw),
            "article_coordinate": _identity(article),
            "source_coordinate": _identity(source_coordinate),
            "trigger_type": str(trigger_type or ""),
            "trigger_value": deepcopy(trigger_value),
            "rank": rank,
            "score": score,
            "mandatory": bool(mandatory),
            "detail": deepcopy(dict(detail or {})),
        }
        endpoint_provenance = {}
        for role, coordinate in (
                ("raw", raw), ("article", article),
                ("source", _coordinate(source_coordinate))):
            if coordinate is None:
                continue
            self._document_ids.add(coordinate[0])
            receipt = self._artifact_receipt(coordinate[0])
            if receipt is not None:
                endpoint_provenance[role] = receipt
        if endpoint_provenance:
            event["content_provenance"] = endpoint_provenance
        if not event["task"] or not event["decision"]:
            raise ValueError("task and decision are required")
        self._events.append(event)

    def stage(
        self,
        stage_id: str,
        kind: str,
        after_coordinates: Iterable[object],
        *,
        parent_stage_ids: Sequence[str] = (),
        discard_reasons: object = None,
        before_occurrence_count: int | None = None,
        after_occurrence_count: int | None = None,
    ) -> dict[str, Any]:
        coordinates = list(after_coordinates)
        row = self._ledger.record_stage(
            stage_id, kind, coordinates,
            parent_stage_ids=parent_stage_ids,
            discard_reasons=discard_reasons,
            before_occurrence_count=before_occurrence_count,
            after_occurrence_count=after_occurrence_count)
        for value in coordinates:
            coordinate = _coordinate(value)
            if coordinate is not None:
                self._document_ids.add(coordinate[0])
        return row

    def capture(self) -> dict[str, Any]:
        value = {
            "schema_version": SCHEMA_VERSION,
            "case_id": self.case_id,
            "arm_id": self.arm_id,
            "gold_visible_to_product": False,
            "stage_ledger": self._ledger.capture(),
            "events": deepcopy(self._events),
            "event_reason_counts": dict(sorted(Counter(
                row["reason_code"] for row in self._events).items())),
        }
        snapshot = self._snapshot_receipt()
        if snapshot is not None:
            value["content_snapshot"] = snapshot
        provenance = {
            doc_id: receipt for doc_id in sorted(self._document_ids)
            if (receipt := self._artifact_receipt(doc_id)) is not None
        }
        if provenance:
            value["content_provenance"] = provenance
        _forbid_gold(value)
        value["capture_sha256"] = stage_ledger.deterministic_sha256(value)
        return value


def validate_capture(capture: Mapping[str, Any]) -> None:
    if capture.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unexpected article reachability schema")
    if capture.get("gold_visible_to_product") is not False:
        raise ValueError("product trace must keep gold invisible")
    _forbid_gold({key: value for key, value in capture.items()
                  if key != "capture_sha256"})
    expected = stage_ledger.deterministic_sha256({
        key: deepcopy(value) for key, value in capture.items()
        if key != "capture_sha256"})
    if capture.get("capture_sha256") != expected:
        raise ValueError("article reachability capture_sha256 mismatch")
    stage_ledger.validate_capture(capture["stage_ledger"])
    for expected_no, event in enumerate(capture.get("events") or (), 1):
        if event.get("event_no") != expected_no:
            raise ValueError("event sequence is not append-only")
        if event.get("channel") not in CHANNELS:
            raise ValueError("invalid event channel")
        if event.get("reason_code") not in REASON_CODES:
            raise ValueError("invalid event reason code")


def _stage(graded: Mapping[str, Any], stage_id: str) -> Mapping[str, Any]:
    return next(row for row in graded["stages"] if row["stage_id"] == stage_id)


def _ids(rows: Iterable[Mapping[str, Any]]) -> set[tuple[str, int]]:
    return {_identity_key(row) for row in rows}


def grade_capture(capture: Mapping[str, Any], gold_coordinates: Iterable[object]) \
        -> dict[str, Any]:
    """Join exact gold only after the product trace is sealed."""
    validate_capture(capture)
    gold = {_coordinate(value) for value in gold_coordinates}
    gold.discard(None)
    graded_stage = stage_ledger.grade_capture(capture["stage_ledger"], gold)
    raw_stage = {
        "A_EXACT": "a-exact-retrieve",
        "B_ASSERTION": "b-assertion-retrieve",
        "C_BM25": "c-keyword-retrieve",
        "D_CLOSURE": "d-relation-retrieve",
        "REFERENCE_RESCUE": "reference-rescue-expand",
    }
    selected_stage = {
        "A_EXACT": "a-exact-select",
        "B_ASSERTION": "b-assertion-select",
        "C_BM25": "c-keyword-select",
        "D_CLOSURE": "d-relation-select",
        "REFERENCE_RESCUE": "reference-rescue-expand",
    }
    channel_base_stage = {
        "D_CLOSURE": "abc-union",
        "REFERENCE_RESCUE": "d-relation-select",
    }
    channel_rows: dict[str, dict[str, Any]] = {}
    raw_hits_by_gold: dict[tuple[str, int], list[str]] = {value: [] for value in gold}
    for channel in raw_stage:
        raw = _stage(graded_stage, raw_stage[channel])
        selected = _stage(graded_stage, selected_stage[channel])
        raw_after = _ids(raw["after"])
        channel_base = (_ids(_stage(graded_stage, channel_base_stage[channel])
                             ["after"])
                        if channel in channel_base_stage else set())
        channel_raw = raw_after - channel_base
        selected_after = _ids(selected["after"])
        channel_selected = selected_after - channel_base
        raw_gold = sorted(gold & channel_raw)
        selected_gold = sorted(gold & channel_selected)
        for coordinate in raw_gold:
            raw_hits_by_gold[coordinate].append(channel)
        channel_rows[channel] = {
            "raw_candidates": len(channel_raw),
            "selected_candidates": len(channel_selected),
            "raw_gold_hits": len(raw_gold),
            "selected_gold_hits": len(selected_gold),
            "raw_gold_coordinates": [_identity(value) for value in raw_gold],
            "selected_gold_coordinates": [_identity(value) for value in selected_gold],
            "first_touch": 0,
            "unique_contribution": 0,
        }
    order = list(raw_stage)
    present = _ids(_stage(graded_stage, "present")["after"])
    fates = []
    for coordinate in sorted(gold):
        touches = raw_hits_by_gold[coordinate]
        first = min(touches, key=order.index) if touches else None
        if first:
            channel_rows[first]["first_touch"] += 1
        if len(touches) == 1:
            channel_rows[touches[0]]["unique_contribution"] += 1
        selected_touches = []
        for channel in order:
            selected = _stage(graded_stage, selected_stage[channel])
            selected_after = _ids(selected["after"])
            channel_base = (_ids(_stage(
                graded_stage, channel_base_stage[channel])["after"])
                if channel in channel_base_stage else set())
            channel_selected = selected_after - channel_base
            if coordinate in channel_selected:
                selected_touches.append(channel)
        if coordinate in present:
            fate = "PRESENTED"
        elif selected_touches:
            fate = "SELECTED_NOT_MERGED"
        elif touches:
            fate = "GENERATED_NOT_SELECTED"
        else:
            fate = "NOT_GENERATED"
        fates.append({
            "identity": _identity(coordinate),
            "raw_channels": touches,
            "selected_channels": selected_touches,
            "first_touch": first,
            "final_present": coordinate in present,
            "fate": fate,
        })
    value = {
        "schema_version": GRADED_SCHEMA_VERSION,
        "case_id": capture["case_id"],
        "arm_id": capture["arm_id"],
        "computed_post_selection": True,
        "gold_visible_to_product": False,
        "product_capture_sha256": capture["capture_sha256"],
        "stage_ledger": graded_stage,
        "channels": channel_rows,
        "article_fates": fates,
        "failure_counts": dict(sorted(Counter(
            row["fate"] for row in fates).items())),
    }
    for key in ("content_snapshot", "content_provenance"):
        if key in capture:
            value[key] = deepcopy(capture[key])
    value["graded_sha256"] = stage_ledger.deterministic_sha256(value)
    return value
