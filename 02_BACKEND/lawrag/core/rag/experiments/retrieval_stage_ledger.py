"""Gold-free retrieval stage capture and post-selection recall accounting.

The product-side boundary is :class:`StageLedgerRecorder`.  It accepts only
retrieval coordinates and transition metadata; no method on that class accepts
gold, a reference answer, or a case grading object.  ``grade_capture`` is the
separate offline boundary that joins gold *after* retrieval has finished.

The ADR v4 validator consumes :func:`build_experiment_artifact` output::

    {
      "schema_version": "retrieval-stage-ledger-v1",
      "adr_id": "ADR-0082",
      "experiment_id": "ADR-0082-experiment-v1",
      "accounting_unit": "case_id + canonical article-root coordinate",
      "computed_post_selection": true,
      "gold_visible_to_product": false,
      "runs": [{
        "run_id": "run-001",
        "arms": [{
          "arm_id": "candidate",
          "declared_stage_ids": ["pool", "selected"],
          "cases": [<graded retrieval-stage-ledger-v1>, ...],
          "aggregate": <micro aggregate>
        }]
      }],
      "artifact_sha256": "..."
    }

The intermediate :func:`build_run_artifact` shape is::

    {
      "schema_version": "retrieval-stage-ledger-run-v1",
      "run_id": "run-001",
      "accounting_unit": "case_id + canonical article-root coordinate",
      "gold_join": {
        "computed_post_selection": true,
        "gold_visible_to_product": false
      },
      "arms": {
        "candidate": {
          "declared_stage_ids": ["pool", "selected"],
          "cases": [<graded retrieval-stage-ledger-v1>, ...],
          "aggregate": <micro aggregate>
        }
      },
      "artifact_sha256": "..."
    }

Every case stage contains exact canonical article-root identities for
``before``, ``added``, ``discarded``, and ``after``.  Their ``*_count`` values
are therefore comparable and obey set arithmetic.  Raw occurrences are kept
separately in ``occurrence_counts`` so subnode aliases and duplicate route hits
are never mislabeled as legal-article discards or gold loss.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any


CAPTURE_SCHEMA_VERSION = "retrieval-stage-ledger-v1"
RUN_SCHEMA_VERSION = "retrieval-stage-ledger-run-v1"
ACCOUNTING_UNIT = "case_id + canonical article-root coordinate"
STAGE_KINDS = frozenset({
    "source",
    "retrieve",
    "union",
    "canonicalize",
    "filter",
    "expand",
    "rerank",
    "select",
    "present",
})

Coordinate = tuple[str, int]
Canonicalizer = Callable[[Coordinate], Coordinate]

_STAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_CAPTURE_TOP_FIELDS = frozenset({
    "schema_version", "case_id", "arm_id", "accounting_unit",
    "gold_visible_to_product", "stages", "capture_sha256",
})
_CAPTURE_STAGE_FIELDS = frozenset({
    "stage_id", "kind", "parent_stage_ids", "executed", "skip_reason",
    "before", "added", "discarded", "after",
    "before_count", "added_count", "discarded_count", "after_count",
    "occurrence_counts", "discard_receipts", "discard_reason_counts",
})
_GRADED_TOP_FIELDS = _CAPTURE_TOP_FIELDS | frozenset({
    "computed_post_selection", "gold_total", "gold_identities",
    "gold_sha256", "ledger_sha256",
})
_GRADED_STAGE_FIELDS = _CAPTURE_STAGE_FIELDS | frozenset({
    "gold_total", "gold_before", "gold_added", "gold_discarded", "gold_after",
    "golden_recall", "gold_before_identities", "gold_added_identities",
    "discarded_gold", "gold_after_identities",
})
_OCCURRENCE_FIELDS = frozenset({
    "before", "after", "canonical_collapsed_before",
    "canonical_collapsed_after",
})
_FORBIDDEN_CAPTURE_KEYS = frozenset({
    "gold_total", "gold_identities", "gold_sha256", "ledger_sha256",
    "gold_before", "gold_added", "gold_discarded", "gold_after",
    "golden_recall", "gold_before_identities", "gold_added_identities",
    "discarded_gold", "gold_after_identities", "gold_results",
    "expected_articles", "reference_answer", "case_all_gold_hit",
    "case_all_gold_internal_pool_hit", "paired", "computed_post_selection",
    "gold_join",
})


class LedgerValidationError(ValueError):
    """Raised when a capture, grade, or run artifact violates the contract."""


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LedgerValidationError("NaN and infinity are not valid ledger values")
        return value
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex()}
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise LedgerValidationError("ledger mapping keys must be strings")
            out[key] = _json_safe(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        rows = [_json_safe(item) for item in value]
        return sorted(rows, key=canonical_json)
    raise LedgerValidationError(
        f"unsupported ledger value {type(value).__module__}."
        f"{type(value).__qualname__}")


def canonical_json(value: Any) -> str:
    """Return the strict deterministic JSON representation used for hashes."""

    return json.dumps(
        _json_safe(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False)


def deterministic_sha256(value: Any) -> str:
    """Return a bare SHA-256 hex digest over :func:`canonical_json`."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def identity_canonicalizer(coordinate: Coordinate) -> Coordinate:
    """Use already-canonical coordinates without rebinding them."""

    return coordinate


def index_article_root_canonicalizer(index: object) -> Canonicalizer:
    """Build a canonicalizer backed by the repository's legal index.

    This helper is for live/frozen-index runners.  A frozen artifact backfill
    that already contains canonical coordinates can use
    :func:`identity_canonicalizer` plus explicit occurrence-count overrides,
    avoiding a dependency on mutable live corpus state.
    """

    from lawrag.core.rag import legal_coordinates

    def canonicalize(coordinate: Coordinate) -> Coordinate:
        doc_id, node = _coordinate(coordinate)
        docs = getattr(index, "docs", {})
        view = docs.get(doc_id)
        if view is None or node not in view.by_id:
            raise LedgerValidationError(
                f"coordinate is absent from index: {(doc_id, node)!r}")
        root = legal_coordinates.article_root(view, node)
        if root not in view.by_id:
            raise LedgerValidationError(
                f"article root is absent from index: {(doc_id, root)!r}")
        return doc_id, root

    return canonicalize


def _nonempty(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise LedgerValidationError(f"{field} is empty")
    return text


def _coordinate(value: object) -> Coordinate:
    if isinstance(value, Mapping):
        if "doc_id" not in value or "node" not in value:
            raise LedgerValidationError("coordinate mapping needs doc_id and node")
        doc_id, node = value["doc_id"], value["node"]
    else:
        try:
            doc_id, node = tuple(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise LedgerValidationError(
                "coordinate must contain exactly (doc_id, node)") from exc
    doc = _nonempty(doc_id, field="coordinate doc_id")
    if isinstance(node, bool) or not isinstance(node, int) or node < 0:
        raise LedgerValidationError(
            "canonical article-root node must be a non-negative integer")
    return doc, node


def _identity(coordinate: Coordinate) -> dict[str, Any]:
    doc_id, node = coordinate
    return {"doc_id": doc_id, "node": _json_safe(node)}


def _identity_key(identity: Mapping[str, Any]) -> str:
    return canonical_json({"doc_id": identity["doc_id"], "node": identity["node"]})


def _canonicalize_one(value: object, canonicalizer: Canonicalizer) \
        -> dict[str, Any]:
    raw = _coordinate(value)
    try:
        canonical = _coordinate(canonicalizer(raw))
        fixed_point = _coordinate(canonicalizer(canonical))
    except LedgerValidationError:
        raise
    except Exception as exc:
        raise LedgerValidationError(
            f"coordinate canonicalization failed for {raw!r}") from exc
    if canonical_json(canonical) != canonical_json(fixed_point):
        raise LedgerValidationError(
            f"canonicalizer is not idempotent for {raw!r}")
    return _identity(canonical)


def _canonical_identities(values: Iterable[object], canonicalizer: Canonicalizer) \
        -> tuple[list[dict[str, Any]], int]:
    if isinstance(values, (str, bytes, Mapping)):
        raise LedgerValidationError("coordinates must be an iterable of coordinates")
    rows: dict[str, dict[str, Any]] = {}
    occurrences = 0
    for value in values:
        identity = _canonicalize_one(value, canonicalizer)
        rows[_identity_key(identity)] = identity
        occurrences += 1
    return [rows[key] for key in sorted(rows)], occurrences


def _identity_map(values: Sequence[Mapping[str, Any]]) \
        -> dict[str, dict[str, Any]]:
    return {_identity_key(row): deepcopy(dict(row)) for row in values}


def _sorted_identity_rows(rows: Mapping[str, Mapping[str, Any]]) \
        -> list[dict[str, Any]]:
    return [deepcopy(dict(rows[key])) for key in sorted(rows)]


def _count(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise LedgerValidationError(
            f"{field} must be an integer >= {minimum}")
    return value


def _occurrence_override(value: int | None, *, inferred: int,
                         canonical_count: int, field: str) -> int:
    if value is None:
        value = inferred
    count = _count(value, field=field)
    if count < canonical_count:
        raise LedgerValidationError(
            f"{field} cannot be smaller than canonical identity count "
            f"{canonical_count}")
    return count


def _reason_rows(value: object, canonicalizer: Canonicalizer) \
        -> dict[str, tuple[dict[str, Any], str]]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        raw_rows = list(value.items())
    else:
        try:
            raw_rows = list(value)  # type: ignore[arg-type]
        except TypeError as exc:
            raise LedgerValidationError(
                "discard_reasons must be a mapping or iterable") from exc
    out: dict[str, tuple[dict[str, Any], str]] = {}
    for raw in raw_rows:
        if isinstance(raw, Mapping):
            coordinate = raw.get("coordinate") or raw.get("identity")
            reason = raw.get("reason")
        else:
            try:
                coordinate, reason = tuple(raw)
            except (TypeError, ValueError) as exc:
                raise LedgerValidationError(
                    "discard reason row must contain coordinate and reason") from exc
        identity = _canonicalize_one(coordinate, canonicalizer)
        key = _identity_key(identity)
        if key in out:
            raise LedgerValidationError(
                f"duplicate discard reason for {identity!r}")
        out[key] = (identity, _nonempty(reason, field="discard reason"))
    return out


class StageLedgerRecorder:
    """Append topologically ordered, gold-free retrieval stage snapshots."""

    def __init__(self, case_id: str, arm_id: str, canonicalizer: Canonicalizer):
        self.case_id = _nonempty(case_id, field="case_id")
        self.arm_id = _nonempty(arm_id, field="arm_id")
        if not callable(canonicalizer):
            raise LedgerValidationError("canonicalizer must be callable")
        self._canonicalizer = canonicalizer
        self._stages: list[dict[str, Any]] = []
        self._stage_by_id: dict[str, dict[str, Any]] = {}

    def record_stage(
        self,
        stage_id: str,
        kind: str,
        after_coordinates: Iterable[object] | None = None,
        *,
        parent_stage_ids: Sequence[str] = (),
        before_coordinates: Iterable[object] | None = None,
        executed: bool = True,
        skip_reason: str = "",
        discard_reasons: object = None,
        before_occurrence_count: int | None = None,
        after_occurrence_count: int | None = None,
    ) -> dict[str, Any]:
        """Record one stage and return an immutable JSON-compatible copy.

        For a non-root stage, ``before`` is the set union of every parent's
        canonical ``after`` identities.  An explicitly supplied
        ``before_coordinates`` sequence is accepted only when its canonical
        set equals that parent union.  This makes route unions a DAG operation,
        not an order-dependent concatenation.

        ``before_occurrence_count`` and ``after_occurrence_count`` are optional
        frozen-artifact diagnostics.  They may exceed canonical set counts but
        may never be smaller.  Duplicate/alias collapse is consequently not a
        discard and needs no discard reason.
        """

        sid = _nonempty(stage_id, field="stage_id")
        if not _STAGE_ID_RE.fullmatch(sid):
            raise LedgerValidationError(f"invalid stage_id: {sid!r}")
        if sid in self._stage_by_id:
            raise LedgerValidationError(f"duplicate stage_id: {sid}")
        stage_kind = _nonempty(kind, field="kind")
        if stage_kind not in STAGE_KINDS:
            raise LedgerValidationError(
                f"unsupported stage kind {stage_kind!r}; expected one of "
                f"{sorted(STAGE_KINDS)}")
        if not isinstance(executed, bool):
            raise LedgerValidationError("executed must be boolean")
        reason = str(skip_reason or "").strip()
        if executed and reason:
            raise LedgerValidationError(
                "executed stage cannot declare a skip_reason")
        if not executed and not reason:
            raise LedgerValidationError(
                "skipped stage requires a non-empty skip_reason")

        parents = tuple(_nonempty(value, field="parent_stage_id")
                        for value in parent_stage_ids)
        if len(parents) != len(set(parents)):
            raise LedgerValidationError("parent_stage_ids contain duplicates")
        missing = [value for value in parents if value not in self._stage_by_id]
        if missing:
            raise LedgerValidationError(
                f"parent stages must already be recorded: {missing}")

        if parents:
            inherited: dict[str, dict[str, Any]] = {}
            inherited_occurrences = 0
            for parent_id in parents:
                parent = self._stage_by_id[parent_id]
                inherited.update(_identity_map(parent["after"]))
                inherited_occurrences += int(
                    parent["occurrence_counts"]["after"])
            before = _sorted_identity_rows(inherited)
            if before_coordinates is not None:
                supplied, supplied_occurrences = _canonical_identities(
                    before_coordinates, self._canonicalizer)
                if _identity_map(supplied) != inherited:
                    raise LedgerValidationError(
                        f"stage {sid} before identities differ from parent union")
                inferred_before_occurrences = supplied_occurrences
            else:
                inferred_before_occurrences = inherited_occurrences
        else:
            if before_coordinates is None:
                before, inferred_before_occurrences = [], 0
            else:
                before, inferred_before_occurrences = _canonical_identities(
                    before_coordinates, self._canonicalizer)

        before_map = _identity_map(before)
        before_occurrences = _occurrence_override(
            before_occurrence_count, inferred=inferred_before_occurrences,
            canonical_count=len(before), field="before_occurrence_count")

        if not executed:
            if after_coordinates is not None:
                supplied_after, supplied_occurrences = _canonical_identities(
                    after_coordinates, self._canonicalizer)
                if _identity_map(supplied_after) != before_map:
                    raise LedgerValidationError(
                        "skipped stage must preserve its before identities")
                if supplied_occurrences != before_occurrences:
                    raise LedgerValidationError(
                        "skipped stage must preserve its occurrence count")
            after = deepcopy(before)
            after_occurrences = _occurrence_override(
                after_occurrence_count, inferred=before_occurrences,
                canonical_count=len(after), field="after_occurrence_count")
            if after_occurrences != before_occurrences:
                raise LedgerValidationError(
                    "skipped stage must preserve its occurrence count")
        else:
            if after_coordinates is None:
                raise LedgerValidationError(
                    "executed stage requires after_coordinates")
            after, inferred_after_occurrences = _canonical_identities(
                after_coordinates, self._canonicalizer)
            after_occurrences = _occurrence_override(
                after_occurrence_count, inferred=inferred_after_occurrences,
                canonical_count=len(after), field="after_occurrence_count")

        after_map = _identity_map(after)
        added_map = {key: row for key, row in after_map.items()
                     if key not in before_map}
        discarded_map = {key: row for key, row in before_map.items()
                         if key not in after_map}
        reasons = _reason_rows(discard_reasons, self._canonicalizer)
        if set(reasons) != set(discarded_map):
            missing_reasons = sorted(set(discarded_map) - set(reasons))
            extra_reasons = sorted(set(reasons) - set(discarded_map))
            raise LedgerValidationError(
                "discard reason coverage must be exactly 100%; "
                f"missing={missing_reasons}, extra={extra_reasons}")

        receipts = [
            {"identity": deepcopy(reasons[key][0]), "reason": reasons[key][1]}
            for key in sorted(reasons)
        ]
        reason_counts = dict(sorted(Counter(
            row["reason"] for row in receipts).items()))
        stage = {
            "stage_id": sid,
            "kind": stage_kind,
            "parent_stage_ids": list(parents),
            "executed": executed,
            "skip_reason": reason,
            "before": deepcopy(before),
            "added": _sorted_identity_rows(added_map),
            "discarded": _sorted_identity_rows(discarded_map),
            "after": deepcopy(after),
            "before_count": len(before),
            "added_count": len(added_map),
            "discarded_count": len(discarded_map),
            "after_count": len(after),
            "occurrence_counts": {
                "before": before_occurrences,
                "after": after_occurrences,
                "canonical_collapsed_before": before_occurrences - len(before),
                "canonical_collapsed_after": after_occurrences - len(after),
            },
            "discard_receipts": receipts,
            "discard_reason_counts": reason_counts,
        }
        self._stages.append(stage)
        self._stage_by_id[sid] = stage
        return deepcopy(stage)

    def capture(self) -> dict[str, Any]:
        """Seal the current gold-free capture and attach its content hash."""

        value = {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "case_id": self.case_id,
            "arm_id": self.arm_id,
            "accounting_unit": ACCOUNTING_UNIT,
            "gold_visible_to_product": False,
            "stages": deepcopy(self._stages),
        }
        value["capture_sha256"] = deterministic_sha256(value)
        validate_capture(value)
        return deepcopy(value)


def _validate_identity_list(value: object, *, field: str) \
        -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise LedgerValidationError(f"{field} must be a list")
    out: dict[str, dict[str, Any]] = {}
    keys: list[str] = []
    for row in value:
        if not isinstance(row, Mapping) or set(row) != {"doc_id", "node"}:
            raise LedgerValidationError(
                f"{field} identities need exactly doc_id and node")
        identity = _identity(_coordinate(row))
        key = _identity_key(identity)
        if key in out:
            raise LedgerValidationError(f"{field} contains duplicate identity")
        out[key] = identity
        keys.append(key)
    if keys != sorted(keys):
        raise LedgerValidationError(f"{field} identities are not sorted")
    return out


def _forbid_gold_keys(value: object, *, path: str = "capture") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _FORBIDDEN_CAPTURE_KEYS:
                raise LedgerValidationError(
                    f"gold/post-selection field {key!r} found at {path}")
            _forbid_gold_keys(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _forbid_gold_keys(item, path=f"{path}[{index}]")


def _capture_without_hash(capture: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in capture.items()
            if key != "capture_sha256"}


def validate_capture(capture: Mapping[str, Any], *,
                     expected_stage_ids: Sequence[str] | None = None) -> None:
    """Validate a gold-free case capture, raising on the first violation."""

    if not isinstance(capture, Mapping):
        raise LedgerValidationError("capture must be a mapping")
    if set(capture) != _CAPTURE_TOP_FIELDS:
        raise LedgerValidationError(
            f"capture fields differ: {sorted(set(capture) ^ _CAPTURE_TOP_FIELDS)}")
    if capture.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        raise LedgerValidationError("capture schema_version mismatch")
    _nonempty(capture.get("case_id"), field="case_id")
    _nonempty(capture.get("arm_id"), field="arm_id")
    if capture.get("accounting_unit") != ACCOUNTING_UNIT:
        raise LedgerValidationError("capture accounting_unit mismatch")
    if capture.get("gold_visible_to_product") is not False:
        raise LedgerValidationError("gold_visible_to_product must be false")
    _forbid_gold_keys(_capture_without_hash(capture))
    stages = capture.get("stages")
    if not isinstance(stages, list) or not stages:
        raise LedgerValidationError("capture needs at least one stage")

    seen: dict[str, Mapping[str, Any]] = {}
    actual_stage_ids: list[str] = []
    for index, stage in enumerate(stages):
        if not isinstance(stage, Mapping) or set(stage) != _CAPTURE_STAGE_FIELDS:
            fields = set(stage) if isinstance(stage, Mapping) else set()
            raise LedgerValidationError(
                f"stage[{index}] fields differ: "
                f"{sorted(fields ^ _CAPTURE_STAGE_FIELDS)}")
        stage_id = _nonempty(stage.get("stage_id"), field="stage_id")
        if not _STAGE_ID_RE.fullmatch(stage_id) or stage_id in seen:
            raise LedgerValidationError(f"invalid/duplicate stage_id: {stage_id}")
        kind = _nonempty(stage.get("kind"), field="kind")
        if kind not in STAGE_KINDS:
            raise LedgerValidationError(f"unsupported stage kind: {kind}")
        parents = stage.get("parent_stage_ids")
        if (not isinstance(parents, list)
                or any(not isinstance(parent, str) or not parent.strip()
                       for parent in parents)
                or any(parent not in seen for parent in parents)
                or len(parents) != len(set(parents))):
            raise LedgerValidationError(
                f"stage {stage_id} parents are not a prior unique DAG set")
        if not isinstance(stage.get("executed"), bool):
            raise LedgerValidationError(f"stage {stage_id} executed is not bool")
        skip_reason = str(stage.get("skip_reason") or "").strip()
        if stage["executed"] == bool(skip_reason):
            raise LedgerValidationError(
                f"stage {stage_id} executed/skip_reason contract failed")

        before = _validate_identity_list(
            stage.get("before"), field=f"{stage_id}.before")
        added = _validate_identity_list(
            stage.get("added"), field=f"{stage_id}.added")
        discarded = _validate_identity_list(
            stage.get("discarded"), field=f"{stage_id}.discarded")
        after = _validate_identity_list(
            stage.get("after"), field=f"{stage_id}.after")
        for name, rows in (
            ("before", before), ("added", added),
            ("discarded", discarded), ("after", after),
        ):
            count = _count(stage.get(f"{name}_count"),
                           field=f"{stage_id}.{name}_count")
            if count != len(rows):
                raise LedgerValidationError(
                    f"stage {stage_id} {name}_count does not match identities")
        expected_after = (set(before) | set(added)) - set(discarded)
        if (set(added) & set(before) or set(discarded) - set(before)
                or set(after) != expected_after):
            raise LedgerValidationError(
                f"stage {stage_id} canonical set equation failed")
        if parents:
            parent_union: set[str] = set()
            for parent in parents:
                parent_union.update(_identity_map(seen[parent]["after"]))
            if set(before) != parent_union:
                raise LedgerValidationError(
                    f"stage {stage_id} before does not equal parent union")

        occurrences = stage.get("occurrence_counts")
        if (not isinstance(occurrences, Mapping)
                or set(occurrences) != _OCCURRENCE_FIELDS):
            raise LedgerValidationError(
                f"stage {stage_id} occurrence_counts fields differ")
        before_occ = _count(
            occurrences.get("before"), field=f"{stage_id}.occurrence.before")
        after_occ = _count(
            occurrences.get("after"), field=f"{stage_id}.occurrence.after")
        if before_occ < len(before) or after_occ < len(after):
            raise LedgerValidationError(
                f"stage {stage_id} occurrence count below canonical count")
        collapsed_before = _count(
            occurrences.get("canonical_collapsed_before"),
            field=f"{stage_id}.occurrence.canonical_collapsed_before")
        collapsed_after = _count(
            occurrences.get("canonical_collapsed_after"),
            field=f"{stage_id}.occurrence.canonical_collapsed_after")
        if collapsed_before != before_occ - len(before):
            raise LedgerValidationError(
                f"stage {stage_id} collapsed-before count mismatch")
        if collapsed_after != after_occ - len(after):
            raise LedgerValidationError(
                f"stage {stage_id} collapsed-after count mismatch")
        if not stage["executed"] and (before != after or added or discarded
                                      or before_occ != after_occ):
            raise LedgerValidationError(
                f"skipped stage {stage_id} changed its snapshot")

        receipts = stage.get("discard_receipts")
        if not isinstance(receipts, list):
            raise LedgerValidationError(
                f"stage {stage_id} discard_receipts must be list")
        receipt_map: dict[str, str] = {}
        receipt_keys: list[str] = []
        for receipt in receipts:
            if (not isinstance(receipt, Mapping)
                    or set(receipt) != {"identity", "reason"}):
                raise LedgerValidationError(
                    f"stage {stage_id} discard receipt fields differ")
            row_map = _validate_identity_list(
                [receipt["identity"]], field=f"{stage_id}.discard_receipt")
            key = next(iter(row_map))
            if key in receipt_map:
                raise LedgerValidationError(
                    f"stage {stage_id} has duplicate discard receipt")
            receipt_map[key] = _nonempty(
                receipt.get("reason"), field="discard receipt reason")
            receipt_keys.append(key)
        if receipt_keys != sorted(receipt_keys) or set(receipt_map) != set(discarded):
            raise LedgerValidationError(
                f"stage {stage_id} discard reason coverage is not 100%")
        expected_reason_counts = dict(sorted(Counter(receipt_map.values()).items()))
        if stage.get("discard_reason_counts") != expected_reason_counts:
            raise LedgerValidationError(
                f"stage {stage_id} discard_reason_counts mismatch")
        seen[stage_id] = stage
        actual_stage_ids.append(stage_id)

    if (expected_stage_ids is not None
            and actual_stage_ids != list(expected_stage_ids)):
        raise LedgerValidationError(
            f"declared stage IDs differ: expected={list(expected_stage_ids)}, "
            f"actual={actual_stage_ids}")
    expected_hash = deterministic_sha256(_capture_without_hash(capture))
    if capture.get("capture_sha256") != expected_hash:
        raise LedgerValidationError("capture_sha256 mismatch")


def _capture_projection(graded: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": graded.get("schema_version"),
        "case_id": graded.get("case_id"),
        "arm_id": graded.get("arm_id"),
        "accounting_unit": graded.get("accounting_unit"),
        "gold_visible_to_product": graded.get("gold_visible_to_product"),
        "stages": [
            {key: deepcopy(stage[key]) for key in _CAPTURE_STAGE_FIELDS}
            for stage in graded.get("stages") or ()
        ],
        "capture_sha256": graded.get("capture_sha256"),
    }


def grade_capture(
    capture: Mapping[str, Any],
    gold_coordinates: Iterable[object],
    *,
    canonicalizer: Canonicalizer = identity_canonicalizer,
) -> dict[str, Any]:
    """Join canonical gold after product selection, without mutating capture."""

    validate_capture(capture)
    gold, _occurrences = _canonical_identities(gold_coordinates, canonicalizer)
    gold_map = _identity_map(gold)
    graded = deepcopy(dict(capture))
    graded["computed_post_selection"] = True
    graded["gold_total"] = len(gold)
    graded["gold_identities"] = deepcopy(gold)
    graded["gold_sha256"] = deterministic_sha256(gold)

    graded_stages: list[dict[str, Any]] = []
    for raw_stage in capture["stages"]:
        stage = deepcopy(dict(raw_stage))
        before = _identity_map(stage["before"])
        added = _identity_map(stage["added"])
        discarded = _identity_map(stage["discarded"])
        after = _identity_map(stage["after"])
        before_gold = {key: before[key] for key in before if key in gold_map}
        added_gold = {key: added[key] for key in added if key in gold_map}
        discarded_gold = {
            key: discarded[key] for key in discarded if key in gold_map}
        after_gold = {key: after[key] for key in after if key in gold_map}
        reason_map = {
            _identity_key(row["identity"]): str(row["reason"])
            for row in stage["discard_receipts"]
        }
        stage.update({
            "gold_total": len(gold),
            "gold_before": len(before_gold),
            "gold_added": len(added_gold),
            "gold_discarded": len(discarded_gold),
            "gold_after": len(after_gold),
            "golden_recall": (
                len(after_gold) / len(gold) if gold else None),
            "gold_before_identities": _sorted_identity_rows(before_gold),
            "gold_added_identities": _sorted_identity_rows(added_gold),
            "discarded_gold": [
                {"identity": deepcopy(discarded_gold[key]),
                 "reason": reason_map[key]}
                for key in sorted(discarded_gold)
            ],
            "gold_after_identities": _sorted_identity_rows(after_gold),
        })
        graded_stages.append(stage)
    graded["stages"] = graded_stages
    graded["ledger_sha256"] = deterministic_sha256(graded)
    validate_graded_ledger(graded)
    return graded


def _graded_without_hash(graded: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in graded.items()
            if key != "ledger_sha256"}


def validate_graded_ledger(
    graded: Mapping[str, Any], *,
    expected_stage_ids: Sequence[str] | None = None,
) -> None:
    """Validate post-selection gold equations and source-capture integrity."""

    if not isinstance(graded, Mapping) or set(graded) != _GRADED_TOP_FIELDS:
        fields = set(graded) if isinstance(graded, Mapping) else set()
        raise LedgerValidationError(
            f"graded ledger fields differ: "
            f"{sorted(fields ^ _GRADED_TOP_FIELDS)}")
    if graded.get("computed_post_selection") is not True:
        raise LedgerValidationError("computed_post_selection must be true")
    if graded.get("gold_visible_to_product") is not False:
        raise LedgerValidationError("gold_visible_to_product must remain false")
    capture = _capture_projection(graded)
    validate_capture(capture, expected_stage_ids=expected_stage_ids)
    gold = _validate_identity_list(
        graded.get("gold_identities"), field="gold_identities")
    gold_total = _count(graded.get("gold_total"), field="gold_total")
    if gold_total != len(gold):
        raise LedgerValidationError("gold_total does not match gold identities")
    if graded.get("gold_sha256") != deterministic_sha256(
            graded.get("gold_identities")):
        raise LedgerValidationError("gold_sha256 mismatch")

    for stage in graded["stages"]:
        if not isinstance(stage, Mapping) or set(stage) != _GRADED_STAGE_FIELDS:
            fields = set(stage) if isinstance(stage, Mapping) else set()
            raise LedgerValidationError(
                f"graded stage fields differ: "
                f"{sorted(fields ^ _GRADED_STAGE_FIELDS)}")
        sid = stage["stage_id"]
        before = _identity_map(stage["before"])
        added = _identity_map(stage["added"])
        discarded = _identity_map(stage["discarded"])
        after = _identity_map(stage["after"])
        expected_sets = {
            "gold_before_identities": {
                key: row for key, row in before.items() if key in gold},
            "gold_added_identities": {
                key: row for key, row in added.items() if key in gold},
            "gold_after_identities": {
                key: row for key, row in after.items() if key in gold},
        }
        for field, expected in expected_sets.items():
            actual = _validate_identity_list(
                stage.get(field), field=f"{sid}.{field}")
            if actual != expected:
                raise LedgerValidationError(f"stage {sid} {field} mismatch")
        discarded_expected = {
            key: row for key, row in discarded.items() if key in gold}
        discarded_rows = stage.get("discarded_gold")
        if not isinstance(discarded_rows, list):
            raise LedgerValidationError(
                f"stage {sid} discarded_gold must be list")
        actual_discarded: dict[str, tuple[dict[str, Any], str]] = {}
        for row in discarded_rows:
            if (not isinstance(row, Mapping)
                    or set(row) != {"identity", "reason"}):
                raise LedgerValidationError(
                    f"stage {sid} discarded_gold receipt fields differ")
            identity_rows = _validate_identity_list(
                [row["identity"]], field=f"{sid}.discarded_gold")
            key = next(iter(identity_rows))
            if key in actual_discarded:
                raise LedgerValidationError(
                    f"stage {sid} duplicate discarded_gold identity")
            actual_discarded[key] = (
                identity_rows[key], _nonempty(
                    row.get("reason"), field="discarded_gold reason"))
        if set(actual_discarded) != set(discarded_expected):
            raise LedgerValidationError(
                f"stage {sid} discarded_gold identities mismatch")
        receipt_reasons = {
            _identity_key(row["identity"]): row["reason"]
            for row in stage["discard_receipts"]
        }
        if any(actual_discarded[key][1] != receipt_reasons[key]
               for key in actual_discarded):
            raise LedgerValidationError(
                f"stage {sid} discarded_gold reason mismatch")

        counts = {
            "gold_before": len(expected_sets["gold_before_identities"]),
            "gold_added": len(expected_sets["gold_added_identities"]),
            "gold_discarded": len(discarded_expected),
            "gold_after": len(expected_sets["gold_after_identities"]),
        }
        if stage.get("gold_total") != gold_total:
            raise LedgerValidationError(f"stage {sid} gold_total mismatch")
        for field, expected in counts.items():
            if stage.get(field) != expected:
                raise LedgerValidationError(
                    f"stage {sid} {field} mismatch")
        if (counts["gold_after"] != counts["gold_before"]
                + counts["gold_added"] - counts["gold_discarded"]):
            raise LedgerValidationError(f"stage {sid} gold equation failed")
        expected_recall = counts["gold_after"] / gold_total if gold_total else None
        if stage.get("golden_recall") != expected_recall:
            raise LedgerValidationError(f"stage {sid} golden_recall mismatch")
    if graded.get("ledger_sha256") != deterministic_sha256(
            _graded_without_hash(graded)):
        raise LedgerValidationError("ledger_sha256 mismatch")


def aggregate_graded_ledgers(
    ledgers: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return per-stage micro sums over one arm's graded case ledgers."""

    values = [deepcopy(dict(value)) for value in ledgers]
    if not values:
        raise LedgerValidationError("cannot aggregate an empty ledger set")
    for value in values:
        validate_graded_ledger(value)
    arm_id = values[0]["arm_id"]
    if any(value["arm_id"] != arm_id for value in values):
        raise LedgerValidationError("aggregate may contain only one arm")
    case_ids = [value["case_id"] for value in values]
    if len(case_ids) != len(set(case_ids)):
        raise LedgerValidationError("aggregate contains duplicate case_id")
    stage_ids = [stage["stage_id"] for stage in values[0]["stages"]]
    for value in values[1:]:
        if [stage["stage_id"] for stage in value["stages"]] != stage_ids:
            raise LedgerValidationError(
                "all aggregated cases need the same ordered stage IDs")

    stage_aggregates: dict[str, dict[str, Any]] = {}
    for index, stage_id in enumerate(stage_ids):
        stages = [value["stages"][index] for value in values]
        kinds = {stage["kind"] for stage in stages}
        parents = {tuple(stage["parent_stage_ids"]) for stage in stages}
        if len(kinds) != 1 or len(parents) != 1:
            raise LedgerValidationError(
                f"stage {stage_id} kind/parents differ across cases")
        reason_counts: Counter[str] = Counter()
        occurrence_counts: Counter[str] = Counter()
        for stage in stages:
            reason_counts.update(stage["discard_reason_counts"])
            occurrence_counts.update(stage["occurrence_counts"])
        aggregate = {
            "stage_id": stage_id,
            "kind": stages[0]["kind"],
            "parent_stage_ids": deepcopy(stages[0]["parent_stage_ids"]),
            "case_count": len(stages),
            "executed_cases": sum(bool(stage["executed"]) for stage in stages),
            "skipped_cases": sum(not stage["executed"] for stage in stages),
            "before_count": sum(stage["before_count"] for stage in stages),
            "added_count": sum(stage["added_count"] for stage in stages),
            "discarded_count": sum(
                stage["discarded_count"] for stage in stages),
            "after_count": sum(stage["after_count"] for stage in stages),
            "occurrence_counts": dict(sorted(occurrence_counts.items())),
            "gold_total": sum(value["gold_total"] for value in values),
            "gold_before": sum(stage["gold_before"] for stage in stages),
            "gold_added": sum(stage["gold_added"] for stage in stages),
            "gold_discarded": sum(
                stage["gold_discarded"] for stage in stages),
            "gold_after": sum(stage["gold_after"] for stage in stages),
            "discard_reason_counts": dict(sorted(reason_counts.items())),
        }
        aggregate["golden_recall"] = (
            aggregate["gold_after"] / aggregate["gold_total"]
            if aggregate["gold_total"] else None)
        aggregate["discard_reason_coverage"] = (
            sum(reason_counts.values()) / aggregate["discarded_count"]
            if aggregate["discarded_count"] else 1.0)
        stage_aggregates[stage_id] = aggregate
    return {
        "arm_id": arm_id,
        "accounting_unit": ACCOUNTING_UNIT,
        "case_count": len(values),
        "gold_total": sum(value["gold_total"] for value in values),
        "stage_ids": stage_ids,
        "stages": stage_aggregates,
    }


def build_run_artifact(
    run_id: str,
    graded_ledgers: Iterable[Mapping[str, Any]],
    declared_stage_ids: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Build the hash-stable run artifact consumed by the ADR validator."""

    rid = _nonempty(run_id, field="run_id")
    values = [deepcopy(dict(value)) for value in graded_ledgers]
    if not values:
        raise LedgerValidationError("run artifact needs at least one case ledger")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for value in values:
        validate_graded_ledger(value)
        grouped.setdefault(value["arm_id"], []).append(value)
    if set(grouped) != set(declared_stage_ids):
        raise LedgerValidationError(
            "declared_stage_ids arms differ from graded ledger arms")

    arms: dict[str, dict[str, Any]] = {}
    for arm_id in sorted(grouped):
        declared = [_nonempty(value, field="declared stage_id")
                    for value in declared_stage_ids[arm_id]]
        if len(declared) != len(set(declared)) or not declared:
            raise LedgerValidationError(
                f"arm {arm_id} declared stage IDs are empty/duplicated")
        cases = sorted(grouped[arm_id], key=lambda value: value["case_id"])
        for case in cases:
            validate_graded_ledger(case, expected_stage_ids=declared)
            if case["stages"][0]["kind"] != "source":
                raise LedgerValidationError(
                    f"arm {arm_id} must begin with a source stage")
            if case["stages"][-1]["kind"] != "present":
                raise LedgerValidationError(
                    f"arm {arm_id} must end with a present stage")
        arms[arm_id] = {
            "declared_stage_ids": declared,
            "cases": cases,
            "aggregate": aggregate_graded_ledgers(cases),
        }
    artifact = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": rid,
        "accounting_unit": ACCOUNTING_UNIT,
        "gold_join": {
            "computed_post_selection": True,
            "gold_visible_to_product": False,
        },
        "arms": arms,
    }
    artifact["artifact_sha256"] = deterministic_sha256(artifact)
    validate_run_artifact(artifact)
    return artifact


def validate_run_artifact(artifact: Mapping[str, Any]) -> None:
    """Validate the complete run/arm/case/stage artifact shape and hashes."""

    expected_fields = {
        "schema_version", "run_id", "accounting_unit", "gold_join", "arms",
        "artifact_sha256",
    }
    if not isinstance(artifact, Mapping) or set(artifact) != expected_fields:
        fields = set(artifact) if isinstance(artifact, Mapping) else set()
        raise LedgerValidationError(
            f"run artifact fields differ: {sorted(fields ^ expected_fields)}")
    if artifact.get("schema_version") != RUN_SCHEMA_VERSION:
        raise LedgerValidationError("run artifact schema_version mismatch")
    _nonempty(artifact.get("run_id"), field="run_id")
    if artifact.get("accounting_unit") != ACCOUNTING_UNIT:
        raise LedgerValidationError("run artifact accounting_unit mismatch")
    if artifact.get("gold_join") != {
            "computed_post_selection": True,
            "gold_visible_to_product": False,
    }:
        raise LedgerValidationError("run artifact gold_join contract failed")
    arms = artifact.get("arms")
    if not isinstance(arms, Mapping) or not arms:
        raise LedgerValidationError("run artifact arms must be non-empty mapping")
    if list(arms) != sorted(arms):
        raise LedgerValidationError("run artifact arms are not sorted")
    for arm_id, value in arms.items():
        if (not isinstance(value, Mapping)
                or set(value) != {"declared_stage_ids", "cases", "aggregate"}):
            raise LedgerValidationError(f"arm {arm_id} fields differ")
        declared = value["declared_stage_ids"]
        cases = value["cases"]
        if not isinstance(declared, list) or not isinstance(cases, list) or not cases:
            raise LedgerValidationError(f"arm {arm_id} declaration/cases invalid")
        if [case.get("case_id") for case in cases] != sorted(
                case.get("case_id") for case in cases):
            raise LedgerValidationError(f"arm {arm_id} cases are not sorted")
        for case in cases:
            if case.get("arm_id") != arm_id:
                raise LedgerValidationError(f"arm {arm_id} contains foreign case")
            validate_graded_ledger(case, expected_stage_ids=declared)
        if value["aggregate"] != aggregate_graded_ledgers(cases):
            raise LedgerValidationError(f"arm {arm_id} aggregate mismatch")
    unhashed = {key: deepcopy(value) for key, value in artifact.items()
                if key != "artifact_sha256"}
    if artifact.get("artifact_sha256") != deterministic_sha256(unhashed):
        raise LedgerValidationError("artifact_sha256 mismatch")


def build_experiment_artifact(
    adr_id: str,
    experiment_id: str,
    run_artifacts: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Wrap one or more run artifacts in the ADR v4 validator shape.

    The wrapper deliberately repeats the two gold-boundary booleans at the
    experiment top level.  Every input run must first pass
    :func:`validate_run_artifact`, including its ``gold_join`` contract.
    ``arms`` are serialized as a list here because the ADR structure validator
    treats ``arm_id`` as an explicit foreign key into the experiment manifest.
    """

    aid = _nonempty(adr_id, field="adr_id")
    eid = _nonempty(experiment_id, field="experiment_id")
    source_runs = [deepcopy(dict(value)) for value in run_artifacts]
    if not source_runs:
        raise LedgerValidationError(
            "experiment artifact needs at least one run artifact")
    for value in source_runs:
        validate_run_artifact(value)
    run_ids = [value["run_id"] for value in source_runs]
    if len(run_ids) != len(set(run_ids)):
        raise LedgerValidationError("experiment artifact has duplicate run_id")

    runs: list[dict[str, Any]] = []
    for source in sorted(source_runs, key=lambda value: value["run_id"]):
        arms = [
            {
                "arm_id": arm_id,
                "declared_stage_ids": deepcopy(
                    source["arms"][arm_id]["declared_stage_ids"]),
                "cases": deepcopy(source["arms"][arm_id]["cases"]),
                "aggregate": deepcopy(source["arms"][arm_id]["aggregate"]),
            }
            for arm_id in sorted(source["arms"])
        ]
        runs.append({"run_id": source["run_id"], "arms": arms})
    artifact = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "adr_id": aid,
        "experiment_id": eid,
        "accounting_unit": ACCOUNTING_UNIT,
        "computed_post_selection": True,
        "gold_visible_to_product": False,
        "runs": runs,
    }
    artifact["artifact_sha256"] = deterministic_sha256(artifact)
    validate_experiment_artifact(artifact)
    return artifact


def validate_experiment_artifact(artifact: Mapping[str, Any]) -> None:
    """Validate the multi-run artifact consumed by ``adr_structure.py``."""

    expected_fields = {
        "schema_version", "adr_id", "experiment_id", "accounting_unit",
        "computed_post_selection", "gold_visible_to_product", "runs",
        "artifact_sha256",
    }
    if not isinstance(artifact, Mapping) or set(artifact) != expected_fields:
        fields = set(artifact) if isinstance(artifact, Mapping) else set()
        raise LedgerValidationError(
            f"experiment artifact fields differ: "
            f"{sorted(fields ^ expected_fields)}")
    if artifact.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        raise LedgerValidationError("experiment artifact schema_version mismatch")
    _nonempty(artifact.get("adr_id"), field="adr_id")
    _nonempty(artifact.get("experiment_id"), field="experiment_id")
    if artifact.get("accounting_unit") != ACCOUNTING_UNIT:
        raise LedgerValidationError("experiment artifact accounting_unit mismatch")
    if artifact.get("computed_post_selection") is not True:
        raise LedgerValidationError(
            "experiment artifact computed_post_selection must be true")
    if artifact.get("gold_visible_to_product") is not False:
        raise LedgerValidationError(
            "experiment artifact gold_visible_to_product must be false")
    runs = artifact.get("runs")
    if not isinstance(runs, list) or not runs:
        raise LedgerValidationError("experiment artifact runs must be non-empty")
    run_ids = [run.get("run_id") for run in runs
               if isinstance(run, Mapping)]
    if (len(run_ids) != len(runs) or len(run_ids) != len(set(run_ids))
            or run_ids != sorted(run_ids)):
        raise LedgerValidationError(
            "experiment artifact runs are invalid, duplicate, or unsorted")
    for run in runs:
        if set(run) != {"run_id", "arms"}:
            raise LedgerValidationError(
                f"experiment run {run.get('run_id')} fields differ")
        _nonempty(run.get("run_id"), field="run_id")
        arms = run.get("arms")
        if not isinstance(arms, list) or not arms:
            raise LedgerValidationError(
                f"experiment run {run['run_id']} arms must be non-empty")
        arm_ids = [arm.get("arm_id") for arm in arms
                   if isinstance(arm, Mapping)]
        if (len(arm_ids) != len(arms) or len(arm_ids) != len(set(arm_ids))
                or arm_ids != sorted(arm_ids)):
            raise LedgerValidationError(
                f"experiment run {run['run_id']} arms are invalid/unsorted")
        for arm in arms:
            if set(arm) != {
                    "arm_id", "declared_stage_ids", "cases", "aggregate"}:
                raise LedgerValidationError(
                    f"experiment arm {arm.get('arm_id')} fields differ")
            arm_id = _nonempty(arm.get("arm_id"), field="arm_id")
            declared = arm.get("declared_stage_ids")
            cases = arm.get("cases")
            if (not isinstance(declared, list) or not declared
                    or len(declared) != len(set(declared))
                    or not isinstance(cases, list) or not cases):
                raise LedgerValidationError(
                    f"experiment arm {arm_id} declaration/cases invalid")
            case_ids = [case.get("case_id") for case in cases]
            if case_ids != sorted(case_ids) or len(case_ids) != len(set(case_ids)):
                raise LedgerValidationError(
                    f"experiment arm {arm_id} cases duplicate/unsorted")
            for case in cases:
                if case.get("arm_id") != arm_id:
                    raise LedgerValidationError(
                        f"experiment arm {arm_id} contains foreign case")
                validate_graded_ledger(case, expected_stage_ids=declared)
            if arm.get("aggregate") != aggregate_graded_ledgers(cases):
                raise LedgerValidationError(
                    f"experiment arm {arm_id} aggregate mismatch")
    unhashed = {key: deepcopy(value) for key, value in artifact.items()
                if key != "artifact_sha256"}
    if artifact.get("artifact_sha256") != deterministic_sha256(unhashed):
        raise LedgerValidationError("experiment artifact_sha256 mismatch")


__all__ = [
    "ACCOUNTING_UNIT",
    "CAPTURE_SCHEMA_VERSION",
    "RUN_SCHEMA_VERSION",
    "STAGE_KINDS",
    "LedgerValidationError",
    "StageLedgerRecorder",
    "aggregate_graded_ledgers",
    "build_experiment_artifact",
    "build_run_artifact",
    "canonical_json",
    "deterministic_sha256",
    "grade_capture",
    "identity_canonicalizer",
    "index_article_root_canonicalizer",
    "validate_capture",
    "validate_experiment_artifact",
    "validate_graded_ledger",
    "validate_run_artifact",
]
