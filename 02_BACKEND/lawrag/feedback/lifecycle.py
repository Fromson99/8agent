"""FeedbackEvent -> inert ChangeCandidate control plane.

Operational feedback is an observation, not authority.  This module keeps the
runtime, definition, data-correction, and ingestion-rule routes distinct and
never edits Canonical KG, Projection stores, or ingestion rules.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping


EVENT_SCHEMA = "feedback-event-v1"
CANDIDATE_SCHEMA = "change-candidate-v1"
_SIGNALS = frozenset({
    "ANSWER_CORRECT",
    "ANSWER_INCORRECT",
    "DEFINITION_AMBIGUOUS",
    "DATA_ERROR",
    "DATA_CORRECTED",
    "STALE_GENERATION",
})
_CANDIDATE_KINDS = frozenset({
    "QUERY_PROJECTION",
    "DEFINITION_OBSERVATION",
    "DATA_CORRECTION",
    "INGESTION_RULE",
})
_SHA_LENGTH = 64


class FeedbackLifecycleError(ValueError):
    """The feedback lineage is incomplete, stale, or hash-invalid."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _hash_or_none(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    if len(text) != _SHA_LENGTH or any(char not in "0123456789abcdef" for char in text):
        raise FeedbackLifecycleError("expected lowercase sha256")
    return text


def _empty_resolution() -> dict[str, None]:
    return {
        "resolves_event_id": None,
        "before_sha256": None,
        "after_sha256": None,
        "receipt_sha256": None,
    }


def _generation_from_trace(
    trace: Mapping[str, Any] | None,
    ask_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    trace = trace or {}
    ask_record = ask_record or {}
    content = ask_record.get("content_snapshot") or {}
    if not isinstance(content, Mapping):
        content = {}
    runtime = ask_record.get("runtime") or {}
    if not isinstance(runtime, Mapping):
        runtime = {}
    main = trace.get("main_pipeline") or runtime.get("main_pipeline") or {}
    if not isinstance(main, Mapping):
        main = {}
    return {
        "runtime_profile": _text(
            trace.get("profile_id")
            or trace.get("effective_profile")
            or runtime.get("effective_profile")
            or main.get("runtime_profile")
        ),
        "main_generation": (
            int(main["generation"])
            if isinstance(main.get("generation"), int)
            and not isinstance(main.get("generation"), bool)
            and int(main["generation"]) >= 0
            else None
        ),
        "graph_generation": _text(
            trace.get("graph_generation") or trace.get("generation_id")
        ),
        "definition_generation": _text(trace.get("definition_generation")),
        "source_set_sha256": _hash_or_none(content.get("source_set_sha256")),
    }


def _finish_event(core: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(core)
    value["event_sha256"] = _sha(value)
    return value


def build_rag_feedback_event(
    *,
    qid: str,
    verdict: str,
    ask_record: Mapping[str, Any],
    expected: Mapping[str, Any] | None = None,
    note: str = "",
    occurred_at: str | None = None,
) -> dict[str, Any]:
    """Turn one user verdict and its frozen retrieval trace into an observation."""

    if verdict not in {"정답", "오답"}:
        raise FeedbackLifecycleError("verdict must be 정답 or 오답")
    question = str(ask_record.get("질의") or "").strip()
    ontology = ask_record.get("ontology_rag") or {}
    if not isinstance(ontology, Mapping):
        ontology = {}
    reason = str(ontology.get("reason") or "")
    if verdict == "정답":
        signal = "ANSWER_CORRECT"
    elif reason == "AMBIGUOUS_SURFACE":
        signal = "DEFINITION_AMBIGUOUS"
    elif reason == "STALE_GENERATION":
        signal = "STALE_GENERATION"
    elif reason in {"VERIFICATION_FAILED", "BLOCKING_QUALITY_ISSUE"}:
        signal = "DATA_ERROR"
    else:
        signal = "ANSWER_INCORRECT"
    expected_rows: list[dict[str, Any]] = []
    if expected:
        document_id = _text(expected.get("doc_id") or expected.get("document_id"))
        node = expected.get("node") if "node" in expected else expected.get("node_id")
        if document_id is not None:
            expected_rows.append({
                "document_id": document_id,
                "node_id": node if isinstance(node, int) and not isinstance(node, bool) else None,
            })
    surface = _text(ontology.get("matched_surface") or ontology.get("detail"))
    timestamp = occurred_at or _now()
    target = {
        "qid": _text(qid),
        "query_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest()
        if question else None,
        "document_id": expected_rows[0]["document_id"] if expected_rows else None,
        "node_id": expected_rows[0]["node_id"] if expected_rows else None,
        "clause_span_id": None,
        "projection_id": _text(ontology.get("projection_id")),
        "surface": surface,
    }
    evidence = {
        "reason": reason or ("USER_CONFIRMED" if verdict == "정답" else "USER_OVERTURN"),
        "note": str(note or ""),
        "expected_coordinates": expected_rows,
        "detector_id": "ontology-rag-runtime" if signal == "DATA_ERROR" else None,
        "detector_fingerprint": (
            _sha({"reason": reason, "target": target, "generation": ontology})
            if signal == "DATA_ERROR" else None
        ),
    }
    identity = {
        "source_kind": "RAG_USER",
        "signal_kind": signal,
        "occurred_at": timestamp,
        "qid": qid,
        "target": target,
        "evidence": evidence,
    }
    return _finish_event({
        "schema_version": EVENT_SCHEMA,
        "event_id": f"feedback:{_sha(identity)[:24]}",
        "occurred_at": timestamp,
        "source_kind": "RAG_USER",
        "signal_kind": signal,
        "status": "OBSERVED",
        "generation": _generation_from_trace(ontology, ask_record),
        "target": target,
        "evidence": evidence,
        "resolution": _empty_resolution(),
    })


def build_data_error_event(
    *,
    detector_id: str,
    issue_code: str,
    detector_fingerprint: str,
    document_id: str,
    before_sha256: str,
    node_id: int | None = None,
    clause_span_id: str | None = None,
    note: str = "",
    generation: Mapping[str, Any] | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    """Create an inert ingestion/validator finding; no source bytes are changed."""

    timestamp = occurred_at or _now()
    fingerprint = _hash_or_none(detector_fingerprint)
    before = _hash_or_none(before_sha256)
    if fingerprint is None or before is None:
        raise FeedbackLifecycleError("data error hashes are required")
    target = {
        "qid": None,
        "query_sha256": None,
        "document_id": _text(document_id),
        "node_id": node_id,
        "clause_span_id": _text(clause_span_id),
        "projection_id": None,
        "surface": None,
    }
    evidence = {
        "reason": str(issue_code or "DATA_VALIDATION_FAILED"),
        "note": str(note or ""),
        "expected_coordinates": [],
        "detector_id": _text(detector_id),
        "detector_fingerprint": fingerprint,
    }
    identity = {
        "occurred_at": timestamp,
        "target": target,
        "evidence": evidence,
        "before_sha256": before,
    }
    resolution = _empty_resolution()
    resolution["before_sha256"] = before
    supplied_generation = dict(generation or {})
    normalized_generation = {
        "runtime_profile": _text(supplied_generation.get("runtime_profile")),
        "main_generation": supplied_generation.get("main_generation")
        if isinstance(supplied_generation.get("main_generation"), int)
        and not isinstance(supplied_generation.get("main_generation"), bool)
        else None,
        "graph_generation": _text(supplied_generation.get("graph_generation")),
        "definition_generation": _text(supplied_generation.get("definition_generation")),
        "source_set_sha256": _hash_or_none(supplied_generation.get("source_set_sha256")),
    }
    return _finish_event({
        "schema_version": EVENT_SCHEMA,
        "event_id": f"feedback:{_sha(identity)[:24]}",
        "occurred_at": timestamp,
        "source_kind": "VALIDATOR",
        "signal_kind": "DATA_ERROR",
        "status": "OBSERVED",
        "generation": normalized_generation,
        "target": target,
        "evidence": evidence,
        "resolution": resolution,
    })


def build_data_correction_event(
    *,
    finding: Mapping[str, Any],
    after_sha256: str,
    correction_receipt_sha256: str,
    note: str = "",
    occurred_at: str | None = None,
) -> dict[str, Any]:
    """Record a human-applied correction as a new event, preserving the finding."""

    validate_feedback_event(finding)
    if finding.get("signal_kind") != "DATA_ERROR":
        raise FeedbackLifecycleError("only a DATA_ERROR can be resolved as data correction")
    before = _hash_or_none((finding.get("resolution") or {}).get("before_sha256"))
    after = _hash_or_none(after_sha256)
    receipt = _hash_or_none(correction_receipt_sha256)
    if before is None or after is None or receipt is None or before == after:
        raise FeedbackLifecycleError("correction requires distinct before/after hashes and receipt")
    timestamp = occurred_at or _now()
    identity = {
        "occurred_at": timestamp,
        "resolves_event_id": finding["event_id"],
        "after_sha256": after,
        "receipt_sha256": receipt,
    }
    return _finish_event({
        "schema_version": EVENT_SCHEMA,
        "event_id": f"feedback:{_sha(identity)[:24]}",
        "occurred_at": timestamp,
        "source_kind": "INGESTION",
        "signal_kind": "DATA_CORRECTED",
        "status": "OBSERVED",
        "generation": dict(finding["generation"]),
        "target": dict(finding["target"]),
        "evidence": {
            "reason": "HUMAN_CORRECTION_APPLIED",
            "note": str(note or ""),
            "expected_coordinates": [],
            "detector_id": (finding.get("evidence") or {}).get("detector_id"),
            "detector_fingerprint": (
                finding.get("evidence") or {}
            ).get("detector_fingerprint"),
        },
        "resolution": {
            "resolves_event_id": finding["event_id"],
            "before_sha256": before,
            "after_sha256": after,
            "receipt_sha256": receipt,
        },
    })


def validate_feedback_event(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "event_id", "occurred_at", "source_kind",
        "signal_kind", "status", "generation", "target", "evidence",
        "resolution", "event_sha256",
    }
    if set(value) != required or value.get("schema_version") != EVENT_SCHEMA:
        raise FeedbackLifecycleError("feedback event fields are not exact")
    if value.get("signal_kind") not in _SIGNALS or value.get("status") != "OBSERVED":
        raise FeedbackLifecycleError("feedback signal or status is invalid")
    declared = _hash_or_none(value.get("event_sha256"))
    core = dict(value)
    core.pop("event_sha256", None)
    if declared != _sha(core):
        raise FeedbackLifecycleError("feedback event_sha256 mismatch")
    resolution = value.get("resolution")
    if not isinstance(resolution, Mapping):
        raise FeedbackLifecycleError("feedback resolution must be an object")
    if value.get("signal_kind") == "DATA_CORRECTED":
        if any(resolution.get(key) is None for key in (
            "resolves_event_id", "before_sha256", "after_sha256", "receipt_sha256"
        )):
            raise FeedbackLifecycleError("data correction lineage is incomplete")


def _candidate(
    kind: str,
    events: list[Mapping[str, Any]],
    *,
    target: Mapping[str, Any],
    reason: str,
    resolved_by: Iterable[str] = (),
) -> dict[str, Any]:
    if kind not in _CANDIDATE_KINDS or not events:
        raise FeedbackLifecycleError("invalid empty change candidate")
    event_ids = sorted({str(event["event_id"]) for event in events})
    resolved_ids = sorted(set(resolved_by))
    status = "RESOLVED" if kind == "DATA_CORRECTION" and resolved_ids else "CANDIDATE"
    identity = {
        "kind": kind,
        "events": event_ids,
        "target": target,
        "generation": events[0]["generation"],
    }
    core = {
        "schema_version": CANDIDATE_SCHEMA,
        "candidate_id": f"change:{_sha(identity)[:24]}",
        "candidate_kind": kind,
        "status": status,
        "activation": "INERT_UNTIL_REVIEW",
        "feedback_event_ids": event_ids,
        "generation": dict(events[0]["generation"]),
        "target": dict(target),
        "evidence": {
            "reason": reason,
            "example_count": len(event_ids),
            "resolved_by_event_ids": resolved_ids,
        },
        "review": {
            "required_next_step": (
                "HUMAN_REVIEW" if kind == "DATA_CORRECTION"
                else "EXPERIMENT_THEN_REVIEW"
            ),
            "approved_by": None,
            "experiment_id": None,
            "applied_generation": None,
        },
    }
    return {**core, "candidate_sha256": _sha(core)}


def validate_change_candidate(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != CANDIDATE_SCHEMA:
        raise FeedbackLifecycleError("unsupported change candidate schema")
    if value.get("candidate_kind") not in _CANDIDATE_KINDS:
        raise FeedbackLifecycleError("invalid change candidate kind")
    if value.get("activation") != "INERT_UNTIL_REVIEW":
        raise FeedbackLifecycleError("feedback candidate cannot activate directly")
    declared = _hash_or_none(value.get("candidate_sha256"))
    core = dict(value)
    core.pop("candidate_sha256", None)
    if declared != _sha(core):
        raise FeedbackLifecycleError("change candidate_sha256 mismatch")


def compile_change_candidates(
    events: Iterable[Mapping[str, Any]],
    *,
    min_ingestion_rule_examples: int = 2,
) -> tuple[dict[str, Any], ...]:
    """Compile deterministic review candidates without changing serving data."""

    rows = [dict(event) for event in events]
    for row in rows:
        validate_feedback_event(row)
    corrections: dict[str, list[str]] = {}
    for row in rows:
        if row["signal_kind"] == "DATA_CORRECTED":
            finding_id = str(row["resolution"]["resolves_event_id"])
            corrections.setdefault(finding_id, []).append(str(row["event_id"]))

    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    data_errors: list[Mapping[str, Any]] = []
    for row in rows:
        signal = str(row["signal_kind"])
        generation_key = _sha(row["generation"])
        if signal == "ANSWER_INCORRECT":
            group_key = str(row["target"].get("query_sha256") or row["event_id"])
            groups.setdefault(("QUERY_PROJECTION", generation_key, group_key), []).append(row)
        elif signal == "DEFINITION_AMBIGUOUS":
            group_key = str(row["target"].get("surface") or row["event_id"])
            groups.setdefault(("DEFINITION_OBSERVATION", generation_key, group_key), []).append(row)
        elif signal in {"DATA_ERROR", "STALE_GENERATION"}:
            data_errors.append(row)

    out: list[dict[str, Any]] = []
    for (kind, _generation, _key), grouped in sorted(groups.items()):
        out.append(_candidate(
            kind,
            grouped,
            target=grouped[0]["target"],
            reason=(
                "repeated query landing correction"
                if kind == "QUERY_PROJECTION"
                else "ambiguous definition surface requires canonical review"
            ),
        ))
    for finding in data_errors:
        out.append(_candidate(
            "DATA_CORRECTION",
            [finding],
            target=finding["target"],
            reason=str(finding["evidence"].get("reason") or "data validation failed"),
            resolved_by=corrections.get(str(finding["event_id"]), ()),
        ))

    rule_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for finding in data_errors:
        fingerprint = finding["evidence"].get("detector_fingerprint")
        if fingerprint:
            rule_groups.setdefault((_sha(finding["generation"]), str(fingerprint)), []).append(finding)
    threshold = max(2, int(min_ingestion_rule_examples))
    for (_generation, fingerprint), grouped in sorted(rule_groups.items()):
        unique_documents = {
            str(row["target"].get("document_id")) for row in grouped
            if row["target"].get("document_id")
        }
        if len(grouped) < threshold or len(unique_documents) < 2:
            continue
        out.append(_candidate(
            "INGESTION_RULE",
            grouped,
            target={
                "detector_id": grouped[0]["evidence"].get("detector_id"),
                "detector_fingerprint": fingerprint,
            },
            reason="repeated validator pattern across distinct documents",
        ))
    out.sort(key=lambda row: (row["candidate_kind"], row["candidate_id"]))
    for row in out:
        validate_change_candidate(row)
    return tuple(out)
