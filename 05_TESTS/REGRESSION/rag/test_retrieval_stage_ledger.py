from __future__ import annotations

from copy import deepcopy
import inspect

import pytest

from lawrag.runtime import retrieval_stage_ledger as subject


def _article_root(coordinate):
    doc_id, node = coordinate
    aliases = {
        101: 1,
        102: 1,
        201: 2,
    }
    return doc_id, aliases.get(node, node)


def _identity(doc_id: str, node: object) -> dict:
    return {"doc_id": doc_id, "node": node}


def _two_stage_graded(
    case_id: str,
    source_coordinates,
    selected_coordinates,
    gold_coordinates,
    *,
    reason: str = "tail_cap",
):
    recorder = subject.StageLedgerRecorder(
        case_id, "candidate", subject.identity_canonicalizer)
    recorder.record_stage(
        "pool", "source", source_coordinates)
    before = set(source_coordinates)
    after = set(selected_coordinates)
    discarded = before - after
    recorder.record_stage(
        "selected", "present", selected_coordinates,
        parent_stage_ids=("pool",),
        discard_reasons=[(coordinate, reason) for coordinate in discarded])
    return subject.grade_capture(recorder.capture(), gold_coordinates)


def test_recorder_canonicalizes_article_roots_before_set_accounting():
    recorder = subject.StageLedgerRecorder("cm-001", "candidate", _article_root)

    raw = recorder.record_stage(
        "raw_pool", "retrieve",
        [("law", 101), ("law", 102), ("law", 2)])
    filtered = recorder.record_stage(
        "filtered", "filter", [("law", 2), ("law", 3)],
        parent_stage_ids=("raw_pool",),
        discard_reasons={("law", 1): "below_route_cap"})

    assert raw["after"] == [_identity("law", 1), _identity("law", 2)]
    assert raw["after_count"] == 2
    assert raw["occurrence_counts"] == {
        "before": 0,
        "after": 3,
        "canonical_collapsed_before": 0,
        "canonical_collapsed_after": 1,
    }
    assert filtered["before"] == raw["after"]
    assert filtered["added"] == [_identity("law", 3)]
    assert filtered["discarded"] == [_identity("law", 1)]
    assert filtered["after_count"] == (
        filtered["before_count"] + filtered["added_count"]
        - filtered["discarded_count"])
    assert filtered["discard_reason_counts"] == {"below_route_cap": 1}


def test_frozen_occurrence_override_preserves_raw_counts_without_fake_discard():
    recorder = subject.StageLedgerRecorder(
        "frozen", "candidate", subject.identity_canonicalizer)

    raw_pool = recorder.record_stage(
        "raw_pool", "source", [("law", 1), ("law", 2)],
        after_occurrence_count=3620)
    canonical_pool = recorder.record_stage(
        "canonical_pool", "canonicalize", [("law", 1), ("law", 2)],
        parent_stage_ids=("raw_pool",), after_occurrence_count=3492)

    assert raw_pool["after_count"] == 2
    assert raw_pool["occurrence_counts"]["after"] == 3620
    assert raw_pool["occurrence_counts"]["canonical_collapsed_after"] == 3618
    assert canonical_pool["before_count"] == canonical_pool["after_count"] == 2
    assert canonical_pool["occurrence_counts"] == {
        "before": 3620,
        "after": 3492,
        "canonical_collapsed_before": 3618,
        "canonical_collapsed_after": 3490,
    }
    assert canonical_pool["added_count"] == 0
    assert canonical_pool["discarded_count"] == 0
    assert canonical_pool["discard_reason_counts"] == {}


def test_stage_dag_uses_parent_after_union_and_skip_is_identity_preserving():
    recorder = subject.StageLedgerRecorder(
        "cm-002", "candidate", subject.identity_canonicalizer)
    recorder.record_stage(
        "keyword", "retrieve", [("law", 1), ("law", 2)])
    recorder.record_stage(
        "vector", "retrieve", [("law", 2), ("law", 3)])
    union = recorder.record_stage(
        "route_union", "union", [("law", 3), ("law", 1), ("law", 2)],
        parent_stage_ids=("keyword", "vector"))
    skipped = recorder.record_stage(
        "rerank", "rerank", parent_stage_ids=("route_union",),
        executed=False, skip_reason="no_provider_budget")

    assert union["before"] == [
        _identity("law", 1), _identity("law", 2), _identity("law", 3)]
    assert union["occurrence_counts"]["before"] == 4
    assert union["before_count"] == 3
    assert union["added_count"] == union["discarded_count"] == 0
    assert skipped["executed"] is False
    assert skipped["before"] == skipped["after"] == union["after"]
    assert skipped["occurrence_counts"]["before"] == (
        skipped["occurrence_counts"]["after"])


def test_child_explicit_before_must_equal_complete_parent_union():
    recorder = subject.StageLedgerRecorder(
        "cm-003", "candidate", subject.identity_canonicalizer)
    recorder.record_stage("a", "retrieve", [("law", 1)])
    recorder.record_stage("b", "retrieve", [("law", 2)])

    with pytest.raises(subject.LedgerValidationError, match="parent union"):
        recorder.record_stage(
            "union", "union", [("law", 1), ("law", 2)],
            parent_stage_ids=("a", "b"),
            before_coordinates=[("law", 1)])


def test_every_discard_requires_exactly_one_nonempty_reason():
    recorder = subject.StageLedgerRecorder(
        "cm-004", "candidate", subject.identity_canonicalizer)
    recorder.record_stage("pool", "retrieve", [("law", 1), ("law", 2)])

    with pytest.raises(subject.LedgerValidationError, match="exactly 100%"):
        recorder.record_stage(
            "missing_reason", "filter", [("law", 1)],
            parent_stage_ids=("pool",))
    with pytest.raises(subject.LedgerValidationError, match="exactly 100%"):
        recorder.record_stage(
            "extra_reason", "filter", [("law", 1), ("law", 2)],
            parent_stage_ids=("pool",),
            discard_reasons={("law", 2): "not_actually_discarded"})
    with pytest.raises(subject.LedgerValidationError, match="discard reason is empty"):
        recorder.record_stage(
            "empty_reason", "filter", [("law", 1)],
            parent_stage_ids=("pool",),
            discard_reasons={("law", 2): ""})


def test_skipped_stage_requires_reason_and_cannot_change_candidates():
    recorder = subject.StageLedgerRecorder(
        "cm-005", "candidate", subject.identity_canonicalizer)
    recorder.record_stage("pool", "retrieve", [("law", 1)])

    with pytest.raises(subject.LedgerValidationError, match="requires"):
        recorder.record_stage(
            "no_reason", "rerank", parent_stage_ids=("pool",),
            executed=False)
    with pytest.raises(subject.LedgerValidationError, match="preserve"):
        recorder.record_stage(
            "changed", "rerank", [("law", 2)],
            parent_stage_ids=("pool",), executed=False,
            skip_reason="provider_unavailable")


def test_product_capture_api_has_no_gold_and_offline_grade_does_not_mutate_it():
    parameters = set(inspect.signature(
        subject.StageLedgerRecorder.record_stage).parameters)
    assert not any("gold" in parameter for parameter in parameters)

    recorder = subject.StageLedgerRecorder(
        "cm-006", "candidate", subject.identity_canonicalizer)
    recorder.record_stage("pool", "retrieve", [("law", 1), ("law", 2)])
    capture = recorder.capture()
    frozen_capture = deepcopy(capture)

    serialized = subject.canonical_json(capture)
    for forbidden in (
        "gold_total", "gold_before", "gold_after", "golden_recall",
        "discarded_gold", "expected_articles", "reference_answer",
    ):
        assert forbidden not in serialized
    assert capture["gold_visible_to_product"] is False

    graded = subject.grade_capture(capture, [("law", 2)])

    assert capture == frozen_capture
    assert "gold_total" not in capture
    assert graded["computed_post_selection"] is True
    assert graded["gold_visible_to_product"] is False


def test_post_selection_grader_records_gold_gain_loss_recall_and_reason():
    recorder = subject.StageLedgerRecorder(
        "cm-007", "candidate", subject.identity_canonicalizer)
    recorder.record_stage("pool", "retrieve", [("law", 1), ("law", 2)])
    recorder.record_stage(
        "selected", "select", [("law", 1), ("law", 3)],
        parent_stage_ids=("pool",),
        discard_reasons={("law", 2): "proof_cell_dominated"})

    graded = subject.grade_capture(
        recorder.capture(), [("law", 2), ("law", 3)])
    selected = graded["stages"][1]

    assert selected["gold_before"] == 1
    assert selected["gold_total"] == 2
    assert selected["gold_added"] == 1
    assert selected["gold_discarded"] == 1
    assert selected["gold_after"] == 1
    assert selected["golden_recall"] == 0.5
    assert selected["gold_after"] == (
        selected["gold_before"] + selected["gold_added"]
        - selected["gold_discarded"])
    assert selected["discarded_gold"] == [{
        "identity": _identity("law", 2),
        "reason": "proof_cell_dominated",
    }]
    subject.validate_graded_ledger(graded)


def test_zero_gold_has_none_recall_but_valid_equations():
    recorder = subject.StageLedgerRecorder(
        "empty-gold", "candidate", subject.identity_canonicalizer)
    recorder.record_stage("pool", "retrieve", [("law", 1)])

    graded = subject.grade_capture(recorder.capture(), [])

    assert graded["gold_total"] == 0
    assert graded["stages"][0]["gold_after"] == 0
    assert graded["stages"][0]["golden_recall"] is None
    subject.validate_graded_ledger(graded)


def test_capture_and_grade_hashes_are_stable_under_coordinate_input_order():
    def build(order):
        recorder = subject.StageLedgerRecorder(
            "stable", "candidate", subject.identity_canonicalizer)
        recorder.record_stage("pool", "retrieve", order)
        capture = recorder.capture()
        return capture, subject.grade_capture(
            capture, [("law", 2), ("law", 1)])

    left_capture, left_graded = build(
        [("law", 2), ("law", 1), ("law", 2)])
    right_capture, right_graded = build(
        [("law", 1), ("law", 2), ("law", 2)])

    assert left_capture == right_capture
    assert left_capture["capture_sha256"] == right_capture["capture_sha256"]
    assert left_graded == right_graded
    assert left_graded["ledger_sha256"] == right_graded["ledger_sha256"]
    assert len(left_capture["capture_sha256"]) == 64


def test_validator_rejects_count_and_hash_tampering():
    recorder = subject.StageLedgerRecorder(
        "tamper", "candidate", subject.identity_canonicalizer)
    recorder.record_stage("pool", "retrieve", [("law", 1)])
    capture = recorder.capture()

    count_tampered = deepcopy(capture)
    count_tampered["stages"][0]["after_count"] = 2
    with pytest.raises(subject.LedgerValidationError, match="after_count"):
        subject.validate_capture(count_tampered)

    hash_tampered = deepcopy(capture)
    hash_tampered["capture_sha256"] = "0" * 64
    with pytest.raises(subject.LedgerValidationError, match="capture_sha256"):
        subject.validate_capture(hash_tampered)

    graded = subject.grade_capture(capture, [("law", 1)])
    graded["stages"][0]["gold_after"] = 0
    with pytest.raises(subject.LedgerValidationError, match="gold_after"):
        subject.validate_graded_ledger(graded)


def test_micro_aggregate_sums_counts_reasons_and_gold_denominator():
    case_one = _two_stage_graded(
        "case-1", [("law", 1), ("law", 2)],
        [("law", 1), ("law", 3)], [("law", 2), ("law", 3)])
    case_two = _two_stage_graded(
        "case-2", [("law", 10), ("law", 11)],
        [("law", 11)], [("law", 11)])

    aggregate = subject.aggregate_graded_ledgers([case_one, case_two])
    selected = aggregate["stages"]["selected"]

    assert aggregate["case_count"] == 2
    assert aggregate["gold_total"] == 3
    assert selected["before_count"] == 4
    assert selected["added_count"] == 1
    assert selected["discarded_count"] == 2
    assert selected["after_count"] == 3
    assert selected["gold_total"] == 3
    assert selected["gold_before"] == 2
    assert selected["gold_added"] == 1
    assert selected["gold_discarded"] == 1
    assert selected["gold_after"] == 2
    assert selected["golden_recall"] == 2 / 3
    assert selected["discard_reason_counts"] == {"tail_cap": 2}
    assert selected["discard_reason_coverage"] == 1.0


def test_run_artifact_has_validator_facing_arm_case_and_aggregate_shape():
    case_one = _two_stage_graded(
        "case-1", [("law", 1), ("law", 2)],
        [("law", 2)], [("law", 2)])
    case_two = _two_stage_graded(
        "case-2", [("law", 3), ("law", 4)],
        [("law", 4)], [("law", 4)])

    artifact = subject.build_run_artifact(
        "run-001", [case_two, case_one],
        {"candidate": ["pool", "selected"]})

    assert artifact["schema_version"] == "retrieval-stage-ledger-run-v1"
    assert artifact["accounting_unit"] == (
        "case_id + canonical article-root coordinate")
    assert artifact["gold_join"] == {
        "computed_post_selection": True,
        "gold_visible_to_product": False,
    }
    arm = artifact["arms"]["candidate"]
    assert arm["declared_stage_ids"] == ["pool", "selected"]
    assert [row["case_id"] for row in arm["cases"]] == ["case-1", "case-2"]
    assert arm["aggregate"] == subject.aggregate_graded_ledgers(
        arm["cases"])
    assert len(artifact["artifact_sha256"]) == 64
    subject.validate_run_artifact(artifact)

    same = subject.build_run_artifact(
        "run-001", [case_one, case_two],
        {"candidate": ["pool", "selected"]})
    assert same == artifact


def test_run_builder_rejects_undeclared_or_missing_stage():
    case = _two_stage_graded(
        "case-1", [("law", 1), ("law", 2)],
        [("law", 2)], [("law", 2)])

    with pytest.raises(subject.LedgerValidationError, match="declared stage IDs"):
        subject.build_run_artifact(
            "run-001", [case], {"candidate": ["pool"]})
    with pytest.raises(subject.LedgerValidationError, match="arms differ"):
        subject.build_run_artifact(
            "run-001", [case], {"different-arm": ["pool", "selected"]})


def test_experiment_wrapper_matches_v4_multi_run_validator_shape():
    case = _two_stage_graded(
        "case-1", [("law", 1), ("law", 2)],
        [("law", 2)], [("law", 2)])
    first_run = subject.build_run_artifact(
        "run-001", [case], {"candidate": ["pool", "selected"]})
    second_run = subject.build_run_artifact(
        "run-002", [case], {"candidate": ["pool", "selected"]})

    artifact = subject.build_experiment_artifact(
        "ADR-0082", "ADR-0082-experiment-v1", [second_run, first_run])

    assert artifact["schema_version"] == "retrieval-stage-ledger-v1"
    assert artifact["adr_id"] == "ADR-0082"
    assert artifact["experiment_id"] == "ADR-0082-experiment-v1"
    assert artifact["accounting_unit"] == (
        "case_id + canonical article-root coordinate")
    assert artifact["computed_post_selection"] is True
    assert artifact["gold_visible_to_product"] is False
    assert [run["run_id"] for run in artifact["runs"]] == [
        "run-001", "run-002"]
    assert artifact["runs"][0]["arms"][0]["arm_id"] == "candidate"
    assert artifact["runs"][0]["arms"][0]["declared_stage_ids"] == [
        "pool", "selected"]
    assert len(artifact["artifact_sha256"]) == 64
    subject.validate_experiment_artifact(artifact)


@pytest.mark.parametrize("node", [True, False, -1, "1"])
def test_coordinate_node_must_be_nonnegative_integer(node):
    recorder = subject.StageLedgerRecorder(
        "bad-node", "candidate", subject.identity_canonicalizer)

    with pytest.raises(subject.LedgerValidationError, match="non-negative integer"):
        recorder.record_stage("pool", "retrieve", [("law", node)])


def test_non_idempotent_canonicalizer_is_rejected():
    def unstable(coordinate):
        doc_id, node = coordinate
        return doc_id, int(node) + 1

    recorder = subject.StageLedgerRecorder("bad", "candidate", unstable)

    with pytest.raises(subject.LedgerValidationError, match="not idempotent"):
        recorder.record_stage("pool", "retrieve", [("law", 1)])
