from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from lawrag.api import legalclosure_presenter
from lawrag.ontology import lifecycle as ontology_lifecycle
from lawrag.feedback.lifecycle import (
    FeedbackLifecycleError,
    build_data_correction_event,
    build_data_error_event,
    build_rag_feedback_event,
    compile_change_candidates,
    validate_feedback_event,
)


ROOT = Path(__file__).resolve().parents[3]
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _generation() -> dict:
    return {
        "runtime_profile": "ontology-rag-v1",
        "main_generation": 1,
        "graph_generation": "graph-v1",
        "definition_generation": "definitions-v1",
        "source_set_sha256": SHA_A,
    }


def _ask(reason: str, *, surface: str = "") -> dict:
    return {
        "질의": f"{surface or '등록기관'}이란?",
        "content_snapshot": {"source_set_sha256": SHA_A},
        "runtime": {
            "effective_profile": "ontology-rag-v1",
            "main_pipeline": {
                "runtime_profile": "ontology-rag-v1",
                "generation": 1,
            },
        },
        "ontology_rag": {
            "profile_id": "ontology-rag-v1",
            "reason": reason,
            "detail": surface,
            "graph_generation": "graph-v1",
            "definition_generation": "definitions-v1",
        },
    }


def test_ambiguous_runtime_feedback_becomes_inert_definition_observation() -> None:
    event = build_rag_feedback_event(
        qid="query-1",
        verdict="오답",
        ask_record=_ask("AMBIGUOUS_SURFACE", surface="가명정보"),
        occurred_at="2026-09-04T00:00:00Z",
    )
    validate_feedback_event(event)
    candidates = compile_change_candidates([event])
    assert event["signal_kind"] == "DEFINITION_AMBIGUOUS"
    assert event["generation"] == _generation()
    assert len(candidates) == 1
    assert candidates[0]["candidate_kind"] == "DEFINITION_OBSERVATION"
    assert candidates[0]["activation"] == "INERT_UNTIL_REVIEW"
    assert candidates[0]["review"]["required_next_step"] == "EXPERIMENT_THEN_REVIEW"


def test_wrong_landing_feedback_routes_to_query_projection_only() -> None:
    event = build_rag_feedback_event(
        qid="query-2",
        verdict="오답",
        ask_record=_ask("NO_RULE_MATCH"),
        expected={"doc_id": "law-1", "node": 10},
        occurred_at="2026-09-04T00:00:01Z",
    )
    candidate, = compile_change_candidates([event])
    assert candidate["candidate_kind"] == "QUERY_PROJECTION"
    assert candidate["target"]["document_id"] == "law-1"
    assert candidate["status"] == "CANDIDATE"


def test_data_fix_is_distinct_and_repetition_only_proposes_ingestion_rule() -> None:
    first = build_data_error_event(
        detector_id="clause-offset-validator",
        issue_code="QUOTE_HASH_MISMATCH",
        detector_fingerprint=SHA_C,
        document_id="law-1",
        before_sha256=SHA_A,
        generation=_generation(),
        occurred_at="2026-09-04T00:00:02Z",
    )
    second = build_data_error_event(
        detector_id="clause-offset-validator",
        issue_code="QUOTE_HASH_MISMATCH",
        detector_fingerprint=SHA_C,
        document_id="law-2",
        before_sha256=SHA_B,
        generation=_generation(),
        occurred_at="2026-09-04T00:00:03Z",
    )
    fixed = build_data_correction_event(
        finding=first,
        after_sha256=SHA_B,
        correction_receipt_sha256=SHA_C,
        occurred_at="2026-09-04T00:00:04Z",
    )
    candidates = compile_change_candidates([first, second, fixed])
    corrections = [row for row in candidates if row["candidate_kind"] == "DATA_CORRECTION"]
    rules = [row for row in candidates if row["candidate_kind"] == "INGESTION_RULE"]
    assert len(corrections) == 2 and len(rules) == 1
    resolved = next(row for row in corrections if row["status"] == "RESOLVED")
    assert resolved["feedback_event_ids"] == [first["event_id"]]
    assert resolved["evidence"]["resolved_by_event_ids"] == [fixed["event_id"]]
    assert rules[0]["evidence"]["example_count"] == 2
    assert rules[0]["activation"] == "INERT_UNTIL_REVIEW"


def test_feedback_hash_tampering_fails_closed() -> None:
    event = build_rag_feedback_event(
        qid="query-3",
        verdict="정답",
        ask_record=_ask("VERIFIED_DEFINITION_MATCH"),
        occurred_at="2026-09-04T00:00:05Z",
    )
    event["evidence"]["note"] = "tampered"
    with pytest.raises(FeedbackLifecycleError, match="sha256 mismatch"):
        validate_feedback_event(event)


def test_feedback_and_candidate_json_schemas_accept_compiler_output() -> None:
    event = build_rag_feedback_event(
        qid="query-4",
        verdict="오답",
        ask_record=_ask("AMBIGUOUS_SURFACE", surface="가명정보"),
        occurred_at="2026-09-04T00:00:06Z",
    )
    candidate, = compile_change_candidates([event])
    for name, value in (
        ("feedback-event-v1.schema.json", event),
        ("change-candidate-v1.schema.json", candidate),
    ):
        schema = json.loads((ROOT / "00_SYSTEM/SCHEMAS" / name).read_text("utf-8"))
        errors = list(Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(value))
        assert not errors, errors


def test_public_presenter_preserves_bounded_ontology_trace() -> None:
    public = legalclosure_presenter.public_meta({
        "ontology_rag": {
            "profile_id": "ontology-rag-v1",
            "status": "fallback",
            "reason": "AMBIGUOUS_SURFACE",
            "detail": "가명정보",
            "knowledge_cache": "hit",
            "private_internal_row": "must not escape",
        }
    })
    trace = public["ontology_rag"]
    assert trace["reason"] == "AMBIGUOUS_SURFACE"
    assert trace["knowledge_cache"] == "hit"
    assert "private_internal_row" not in trace


def test_lifecycle_feedback_status_counts_only_inert_candidates(monkeypatch) -> None:
    from lawrag.core.rag import tuples

    event = build_rag_feedback_event(
        qid="query-status",
        verdict="오답",
        ask_record=_ask("AMBIGUOUS_SURFACE", surface="가명정보"),
        occurred_at="2026-09-04T00:00:07Z",
    )
    monkeypatch.setattr(
        tuples,
        "read",
        lambda limit=10_000: [{"피드백": {"ontology_feedback": event}}],
    )
    status = ontology_lifecycle.feedback_status()
    assert status["events"] == 1
    assert status["pending"] == status["total"] == 1
    assert status["detail"][0]["kind"] == "DEFINITION_OBSERVATION"
    assert "자동 승격 없음" in status["note"]
