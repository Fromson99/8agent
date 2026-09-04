from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from pathlib import Path
import sys

import pytest


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))

from scripts import adr_structure
from scripts.adr_structure import (
    HAIKU_MODEL,
    UNRESOLVED_PLACEHOLDER_RE,
    build_experiment_graph,
    scaffold_adr,
    update_question_hashes,
    update_reservation_status,
    validate_adr,
)


def test_final_placeholder_scan_ignores_domain_identifier_substrings() -> None:
    assert UNRESOLVED_PLACEHOLDER_RE["PENDING"].search(
        '"status": "PENDING_VERIFIED_EVIDENCE"'
    ) is None
    assert UNRESOLVED_PLACEHOLDER_RE["TODO"].search("TODO_ITEM") is None
    assert UNRESOLVED_PLACEHOLDER_RE["PENDING"].search('"sha256": "PENDING"')
    assert UNRESOLVED_PLACEHOLDER_RE["TODO"].search("결과: TODO")


def _canonical_fixture_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _complete_scaffold_run(target: Path) -> None:
    artifact = target / "artifacts" / "run-result.json"
    artifact.write_text('{"status":"complete"}\n', "utf-8")
    manifest_path = target / "실험" / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["runs"][0]["status"] = "complete"
    manifest["runs"][0]["artifact_path"] = str(artifact)
    manifest["runs"][0]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest["results"]["status"] = "complete"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")


def _measured_stage_fixture(target: Path) -> tuple[Path, dict, dict]:
    _complete_scaffold_run(target)
    manifest_path = target / "실험" / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    arm_ids = [arm["id"] for arm in manifest["design"]["arms"]]
    plan = [
        {"stage_id": "corpus", "kind": "source", "parent_stage_ids": []},
        {"stage_id": "presented", "kind": "present",
         "parent_stage_ids": ["corpus"]},
    ]
    manifest["design"]["retrieval_stage_plan"]["stages_by_arm"] = {
        arm_id: plan for arm_id in arm_ids}
    manifest["retrieval_accounting"] = {
        "changed": True,
        "corpus_total": 10,
        "before_filter": {arm_id: 2 for arm_id in arm_ids},
        "after_filter": {arm_id: 1 for arm_id in arm_ids},
        "presented_total": {arm_id: 1 for arm_id in arm_ids},
        "presented_mean": {arm_id: 1.0 for arm_id in arm_ids},
        "presented_p50": {arm_id: 1 for arm_id in arm_ids},
        "presented_p95": {arm_id: 1 for arm_id in arm_ids},
        "golden_recall": {arm_id: 1.0 for arm_id in arm_ids},
        "selectivity": {arm_id: 0.1 for arm_id in arm_ids},
        "not_applicable_reason": None,
        "stage_ledger": {
            "mode": "measured",
            "schema_version": "retrieval-stage-ledger-v1",
            "accounting_unit": "case_id + canonical article-root coordinate",
            "summary_run_id": "run-001",
            "artifact_path": None,
            "sha256": None,
            "not_applicable_reason": None,
        },
    }
    gold_identity = {"doc_id": "doc-a", "node": 1}
    other_identity = {"doc_id": "doc-b", "node": 2}
    source_stage = {
        "stage_id": "corpus",
        "kind": "source",
        "parent_stage_ids": [],
        "executed": True,
        "skip_reason": "",
        "before": [],
        "added": [gold_identity, other_identity],
        "discarded": [],
        "after": [gold_identity, other_identity],
        "before_count": 0,
        "added_count": 2,
        "discarded_count": 0,
        "after_count": 2,
        "occurrence_counts": {
            "before": 0,
            "after": 2,
            "canonical_collapsed_before": 0,
            "canonical_collapsed_after": 0,
        },
        "discard_receipts": [],
        "gold_total": 1,
        "gold_before": 0,
        "gold_added": 1,
        "gold_discarded": 0,
        "gold_after": 1,
        "golden_recall": 1.0,
        "discard_reason_counts": {},
        "gold_before_identities": [],
        "gold_added_identities": [gold_identity],
        "discarded_gold": [],
        "gold_after_identities": [gold_identity],
    }
    present_stage = {
        "stage_id": "presented",
        "kind": "present",
        "parent_stage_ids": ["corpus"],
        "executed": True,
        "skip_reason": "",
        "before": [gold_identity, other_identity],
        "added": [],
        "discarded": [other_identity],
        "after": [gold_identity],
        "before_count": 2,
        "added_count": 0,
        "discarded_count": 1,
        "after_count": 1,
        "occurrence_counts": {
            "before": 2,
            "after": 1,
            "canonical_collapsed_before": 0,
            "canonical_collapsed_after": 0,
        },
        "discard_receipts": [{"identity": other_identity, "reason": "rank_cut"}],
        "gold_total": 1,
        "gold_before": 1,
        "gold_added": 0,
        "gold_discarded": 0,
        "gold_after": 1,
        "golden_recall": 1.0,
        "discard_reason_counts": {"rank_cut": 1},
        "gold_before_identities": [gold_identity],
        "gold_added_identities": [],
        "discarded_gold": [],
        "gold_after_identities": [gold_identity],
    }
    case_ids = [row["case_id"] for row in manifest["questions"]]
    ledger = {
        "schema_version": "retrieval-stage-ledger-v1",
        "adr_id": manifest["adr_id"],
        "experiment_id": manifest["experiment_id"],
        "accounting_unit": "case_id + canonical article-root coordinate",
        "computed_post_selection": True,
        "gold_visible_to_product": False,
        "audit": {"lineage": "synthetic-validator-fixture"},
        "runs": [{
            "run_id": "run-001",
            "arms": [{
                "arm_id": arm_id,
                "declared_stage_ids": ["corpus", "presented"],
                "cases": [{
                    "schema_version": "retrieval-stage-ledger-v1",
                    "case_id": case_id,
                    "arm_id": arm_id,
                    "accounting_unit": "case_id + canonical article-root coordinate",
                    "computed_post_selection": True,
                    "gold_visible_to_product": False,
                    "gold_total": 1,
                    "gold_identities": [gold_identity],
                    "stages": [dict(source_stage), dict(present_stage)],
                } for case_id in case_ids],
                "aggregate": {},
            } for arm_id in arm_ids],
        }],
    }
    ledger["artifact_sha256"] = _canonical_fixture_sha256(ledger)
    ledger_path = target / "artifacts" / "retrieval-stage-ledger-run-001.json"
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), "utf-8")
    manifest["retrieval_accounting"]["stage_ledger"]["artifact_path"] = str(ledger_path)
    manifest["retrieval_accounting"]["stage_ledger"]["sha256"] = hashlib.sha256(
        ledger_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    return ledger_path, ledger, manifest


def _reseal_stage_fixture(target: Path, ledger_path: Path, ledger: dict) -> None:
    ledger.pop("artifact_sha256", None)
    ledger["artifact_sha256"] = _canonical_fixture_sha256(ledger)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), "utf-8")
    manifest_path = target / "실험" / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["retrieval_accounting"]["stage_ledger"]["sha256"] = hashlib.sha256(
        ledger_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")


def test_scaffold_creates_canonical_tree_and_validates(tmp_path: Path) -> None:
    target = scaffold_adr(
        tmp_path, 177, "sample-probe", "표준 구조 시험", "probe", ["cm-001", "cm-002"])

    assert (target / "README.md").is_file()
    assert (target / "claim.json").is_file()
    assert (target / "실험" / "질문-001-cm-001.md").is_file()
    assert (target / "실험" / "질문-002-cm-002.md").is_file()
    assert (target / "artifacts" / "manifest.json").is_file()
    assert validate_adr(target) == []

    manifest = json.loads((target / "실험" / "manifest.json").read_text("utf-8"))
    assert manifest["schema_version"] == "adr-experiment-v4"
    assert manifest["in_sample"] is True
    assert manifest["decision_eligible"] is False
    assert {call["model"] for call in manifest["llm_policy"]["llm_calls"]} == {HAIKU_MODEL}
    reservation = manifest["reservation"]
    assert reservation["status"] == "in_progress"
    assert reservation["created_at"].endswith("Z")
    assert reservation["created_at"] <= reservation["work_started_at"]
    assert [event["action"] for event in reservation["events"]] == ["reserved", "started"]


def test_schema_v4_cutover_grandfathers_v3(tmp_path: Path) -> None:
    legacy = scaffold_adr(
        tmp_path, 81, "last-v3", "마지막 v3", "audit", [], scope_key="last-v3")
    current = scaffold_adr(
        tmp_path, 82, "first-v4", "첫 v4", "audit", [], scope_key="first-v4")

    legacy_manifest = json.loads(
        (legacy / "실험" / "manifest.json").read_text("utf-8"))
    current_manifest = json.loads(
        (current / "실험" / "manifest.json").read_text("utf-8"))
    assert legacy_manifest["schema_version"] == "adr-experiment-v3"
    assert current_manifest["schema_version"] == "adr-experiment-v4"
    assert validate_adr(legacy) == []
    assert validate_adr(current) == []


def test_scaffold_rejects_duplicate_number_even_with_another_slug(tmp_path: Path) -> None:
    scaffold_adr(tmp_path, 77, "first-claim", "첫 선점", "audit", [])

    with pytest.raises(FileExistsError, match="number 0077 already claimed"):
        scaffold_adr(tmp_path, 77, "second-claim", "중복 선점", "audit", [])


def test_scaffold_rejects_duplicate_active_scope(tmp_path: Path) -> None:
    first = scaffold_adr(
        tmp_path, 77, "first-scope", "첫 범위", "audit", [],
        scope_key="shared-scope", owner="agent-a")
    # Simulate the concurrency window after the immutable receipt but before manifest creation.
    (first / "실험" / "manifest.json").unlink()

    with pytest.raises(FileExistsError, match="active scope 'shared-scope'"):
        scaffold_adr(
            tmp_path, 78, "second-scope", "둘째 범위", "audit", [],
            scope_key="shared-scope", owner="agent-b")


def test_reservation_status_appends_history_and_updates_front_matter(tmp_path: Path) -> None:
    target = scaffold_adr(
        tmp_path, 77, "lifecycle", "수명주기", "audit", [], owner="agent-a")
    reservation = update_reservation_status(
        target, "completed", owner="agent-a", note="검증 완료")

    assert reservation["status"] == "completed"
    assert reservation["completed_at"] == reservation["updated_at"]
    assert [event["action"] for event in reservation["events"]] == [
        "reserved", "started", "completed"]
    readme = (target / "README.md").read_text("utf-8")
    assert "work_status: completed" in readme
    assert f"updated_at: {reservation['updated_at']}" in readme
    assert validate_adr(target) == []

    with pytest.raises(ValueError, match="immutable"):
        update_reservation_status(target, "abandoned")


def test_validator_rejects_non_haiku_model(tmp_path: Path) -> None:
    target = scaffold_adr(tmp_path, 178, "wrong-model", "모델 정책 시험", "holdout", ["q1"])
    path = target / "실험" / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["llm_policy"]["llm_calls"][0]["model"] = "another-model"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")

    errors = validate_adr(target)
    assert any("must use" in error for error in errors)


def test_hash_command_seals_question_files_but_final_still_rejects_todos(tmp_path: Path) -> None:
    target = scaffold_adr(tmp_path, 179, "hash-probe", "해시 시험", "probe", ["cm-003"])
    assert update_question_hashes(target) == 1
    assert not any("hash" in error.lower() for error in validate_adr(target))

    final_errors = validate_adr(target, final=True)
    assert any("contains TODO" in error for error in final_errors)
    assert any("criteria before run" in error for error in final_errors)

    artifact_path = target / "artifacts" / "manifest.json"
    artifacts = json.loads(artifact_path.read_text("utf-8"))
    artifacts["files"] = [{
        "path": str(target / "README.md"),
        "sha256": "0" * 64,
        "bytes": (target / "README.md").stat().st_size,
    }]
    artifact_path.write_text(json.dumps(artifacts, ensure_ascii=False, indent=2), "utf-8")
    assert any("artifact hash mismatch" in error for error in validate_adr(target))


def test_validator_requires_retrieval_denominators_when_changed(tmp_path: Path) -> None:
    target = scaffold_adr(tmp_path, 180, "retrieval-probe", "회수 분모 시험", "probe", [])
    path = target / "실험" / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["retrieval_accounting"]["changed"] = True
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")

    errors = validate_adr(target)
    assert any("corpus_total" in error for error in errors)
    assert any("selectivity" in error for error in errors)


def test_v4_measured_stage_ledger_validates_exact_coverage_and_summary(
    tmp_path: Path,
) -> None:
    target = scaffold_adr(
        tmp_path, 182, "measured-ledger", "측정 원장", "holdout", ["q1"])
    _measured_stage_fixture(target)

    assert validate_adr(target) == []


def test_v4_stage_ledger_accepts_exact_multi_parent_union(tmp_path: Path) -> None:
    target = scaffold_adr(
        tmp_path, 190, "ledger-dag", "원장 DAG", "holdout", ["q1"])
    ledger_path, ledger, _ = _measured_stage_fixture(target)
    manifest_path = target / "실험" / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    planned = [
        {"stage_id": "source-a", "kind": "source", "parent_stage_ids": []},
        {"stage_id": "source-b", "kind": "source", "parent_stage_ids": []},
        {"stage_id": "merged", "kind": "union",
         "parent_stage_ids": ["source-a", "source-b"]},
        {"stage_id": "presented", "kind": "present",
         "parent_stage_ids": ["merged"]},
    ]
    manifest["design"]["retrieval_stage_plan"]["stages_by_arm"] = {
        arm["id"]: planned for arm in manifest["design"]["arms"]}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")

    for arm in ledger["runs"][0]["arms"]:
        arm["declared_stage_ids"] = [stage["stage_id"] for stage in planned]
        for case in arm["cases"]:
            original_source, original_present = case["stages"]
            gold_identity, other_identity = original_source["after"]
            source_a = deepcopy(original_source)
            source_a.update({
                "stage_id": "source-a", "added": [gold_identity],
                "after": [gold_identity], "added_count": 1, "after_count": 1,
                "occurrence_counts": {
                    "before": 0, "after": 1, "canonical_collapsed_before": 0,
                    "canonical_collapsed_after": 0,
                },
            })
            source_b = deepcopy(original_source)
            source_b.update({
                "stage_id": "source-b", "added": [other_identity],
                "after": [other_identity], "added_count": 1, "after_count": 1,
                "gold_added": 0, "gold_after": 0, "golden_recall": 0.0,
                "gold_added_identities": [], "gold_after_identities": [],
                "occurrence_counts": {
                    "before": 0, "after": 1, "canonical_collapsed_before": 0,
                    "canonical_collapsed_after": 0,
                },
            })
            merged = deepcopy(original_source)
            merged.update({
                "stage_id": "merged", "kind": "union",
                "parent_stage_ids": ["source-a", "source-b"],
                "before": [gold_identity, other_identity], "added": [],
                "after": [gold_identity, other_identity], "before_count": 2,
                "added_count": 0, "after_count": 2, "gold_before": 1,
                "gold_added": 0, "gold_before_identities": [gold_identity],
                "gold_added_identities": [],
                "occurrence_counts": {
                    "before": 2, "after": 2, "canonical_collapsed_before": 0,
                    "canonical_collapsed_after": 0,
                },
            })
            original_present["parent_stage_ids"] = ["merged"]
            case["stages"] = [source_a, source_b, merged, original_present]
    _reseal_stage_fixture(target, ledger_path, ledger)

    assert validate_adr(target) == []


def test_v4_measured_stage_ledger_rejects_missing_or_drifted_artifact(
    tmp_path: Path,
) -> None:
    target = scaffold_adr(
        tmp_path, 183, "ledger-hash", "원장 해시", "holdout", ["q1"])
    ledger_path, _, _ = _measured_stage_fixture(target)
    ledger_path.write_text("{}\n", "utf-8")

    errors = validate_adr(target)
    assert any("artifact hash mismatch" in error for error in errors)


def test_v4_stage_ledger_rejects_run_arm_case_and_stage_coverage_gaps(
    tmp_path: Path,
) -> None:
    target = scaffold_adr(
        tmp_path, 184, "ledger-coverage", "원장 coverage", "holdout", ["q1"])
    ledger_path, ledger, _ = _measured_stage_fixture(target)
    ledger["runs"][0]["arms"] = ledger["runs"][0]["arms"][:1]
    ledger["runs"][0]["arms"][0]["cases"][0]["stages"] = ledger[
        "runs"][0]["arms"][0]["cases"][0]["stages"][:1]
    _reseal_stage_fixture(target, ledger_path, ledger)

    errors = validate_adr(target)
    assert any("cover every run arm" in error for error in errors)
    assert any("stage IDs/order" in error for error in errors)


def test_v4_stage_ledger_rejects_count_gold_continuity_and_recall_errors(
    tmp_path: Path,
) -> None:
    target = scaffold_adr(
        tmp_path, 185, "ledger-equations", "원장 산술", "holdout", ["q1"])
    ledger_path, ledger, _ = _measured_stage_fixture(target)
    stages = ledger["runs"][0]["arms"][0]["cases"][0]["stages"]
    stages[0]["after_count"] = 3
    stages[0]["golden_recall"] = 0.5
    stages[1]["before"] = [{"doc_id": "doc-a", "node": 1}]
    _reseal_stage_fixture(target, ledger_path, ledger)

    errors = validate_adr(target)
    assert any("after_count must equal identity count" in error for error in errors)
    assert any("golden_recall" in error for error in errors)
    assert any("parent output union" in error for error in errors)


def test_v4_stage_ledger_rejects_unaccounted_discards_and_gold_leakage(
    tmp_path: Path,
) -> None:
    target = scaffold_adr(
        tmp_path, 186, "ledger-boundary", "원장 경계", "holdout", ["q1"])
    ledger_path, ledger, _ = _measured_stage_fixture(target)
    ledger["gold_visible_to_product"] = True
    stage = ledger["runs"][0]["arms"][0]["cases"][0]["stages"][1]
    stage["discard_reason_counts"] = {}
    _reseal_stage_fixture(target, ledger_path, ledger)

    errors = validate_adr(target)
    assert any("gold_visible_to_product=false" in error for error in errors)
    assert any("discard_reason_counts mismatch" in error for error in errors)


def test_v4_inherited_and_not_applicable_modes_require_provenance(
    tmp_path: Path,
) -> None:
    measured = scaffold_adr(
        tmp_path, 187, "ledger-source", "원장 원본", "holdout", ["q1"])
    ledger_path, _, _ = _measured_stage_fixture(measured)

    inherited = scaffold_adr(
        tmp_path, 188, "ledger-inherited", "상속 원장", "audit", [])
    manifest_path = inherited / "실험" / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["retrieval_accounting"]["not_applicable_reason"] = "동결 retrieval exact replay"
    manifest["retrieval_accounting"]["stage_ledger"] = {
        "mode": "inherited",
        "schema_version": "retrieval-stage-ledger-v1",
        "accounting_unit": "case_id + canonical article-root coordinate",
        "summary_run_id": "run-001",
        "artifact_path": str(ledger_path),
        "sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        "not_applicable_reason": None,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    assert validate_adr(inherited) == []

    manifest["retrieval_accounting"]["stage_ledger"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    assert any("inherited retrieval stage ledger hash mismatch" in error
               for error in validate_adr(inherited))

    not_applicable = scaffold_adr(
        tmp_path, 189, "ledger-na", "원장 해당 없음", "audit", [])
    na_path = not_applicable / "실험" / "manifest.json"
    na_manifest = json.loads(na_path.read_text("utf-8"))
    na_manifest["retrieval_accounting"]["stage_ledger"]["not_applicable_reason"] = ""
    na_path.write_text(json.dumps(na_manifest, ensure_ascii=False, indent=2), "utf-8")
    assert any("requires a reason" in error for error in validate_adr(not_applicable))


def test_branch_scaffold_points_to_exact_parent_arm_and_builds_dag(tmp_path: Path) -> None:
    root = scaffold_adr(
        tmp_path, 181, "root-branch", "루트 분기", "probe", ["cm-001"],
        branch_id="A", candidate_arms=["B", "C"])
    with pytest.raises(ValueError, match="must be complete"):
        scaffold_adr(
            tmp_path, 185, "premature-child", "미완료 부모", "probe", [],
            parent_manifest=root / "실험" / "manifest.json", parent_arm="B")
    assert not (tmp_path / "ADR-0185-premature-child").exists()
    _complete_scaffold_run(root)
    child = scaffold_adr(
        tmp_path, 182, "b-children", "B 후속 분기", "probe", ["cm-001"],
        branch_id="B-followup", candidate_arms=["B1", "B2"],
        parent_manifest=root / "실험" / "manifest.json", parent_arm="B")

    assert validate_adr(root) == []
    assert validate_adr(child) == []
    child_manifest = json.loads((child / "실험" / "manifest.json").read_text("utf-8"))
    parent = child_manifest["lineage"]["parents"][0]
    assert parent["experiment_id"] == "ADR-0181-experiment-v1"
    assert parent["arm_id"] == "B"
    assert child_manifest["design"]["arms"][0]["derived_from"] == [
        "ADR-0181-experiment-v1/B"]
    assert child_manifest["lineage"]["branch_path"] == ["A", "B", "B-followup"]

    graph = build_experiment_graph(tmp_path)
    assert graph["validation_errors"] == []
    assert {node["ref"] for node in graph["nodes"]} == {
        "ADR-0181-experiment-v1/baseline",
        "ADR-0181-experiment-v1/B",
        "ADR-0181-experiment-v1/C",
        "ADR-0182-experiment-v1/baseline",
        "ADR-0182-experiment-v1/B1",
        "ADR-0182-experiment-v1/B2",
    }
    assert any(edge["from"] == "ADR-0181-experiment-v1/B" and
               edge["to"] == "ADR-0182-experiment-v1/baseline"
               for edge in graph["edges"])


def test_validator_rejects_parent_drift_and_arm_cycle(tmp_path: Path) -> None:
    root = scaffold_adr(tmp_path, 183, "parent", "부모", "probe", [])
    _complete_scaffold_run(root)
    child = scaffold_adr(
        tmp_path, 184, "child", "자식", "probe", [],
        parent_manifest=root / "실험" / "manifest.json", parent_arm="candidate")

    parent_path = root / "실험" / "manifest.json"
    parent_manifest = json.loads(parent_path.read_text("utf-8"))
    parent_manifest["design"]["hypothesis"] = "parent changed after child fork"
    parent_path.write_text(json.dumps(parent_manifest, ensure_ascii=False, indent=2), "utf-8")
    assert any("parent manifest hash mismatch" in error for error in validate_adr(child))

    child_path = child / "실험" / "manifest.json"
    child_manifest = json.loads(child_path.read_text("utf-8"))
    child_manifest["design"]["arms"][0]["derived_from"] = ["candidate"]
    child_manifest["design"]["arms"][1]["derived_from"] = ["baseline"]
    child_path.write_text(json.dumps(child_manifest, ensure_ascii=False, indent=2), "utf-8")
    assert any("local cycle" in error for error in validate_adr(child))


def test_multi_parent_merge_and_related_adr_are_fully_recorded(tmp_path: Path) -> None:
    left = scaffold_adr(tmp_path, 186, "left-parent", "왼쪽 부모", "audit", [])
    right = scaffold_adr(tmp_path, 187, "right-parent", "오른쪽 부모", "audit", [])
    _complete_scaffold_run(left)
    _complete_scaffold_run(right)

    merged = scaffold_adr(
        tmp_path, 188, "merged-child", "병합 자식", "audit", [],
        parent_specs=[
            (left / "실험" / "manifest.json", "candidate", "merged_from"),
            (right / "실험" / "manifest.json", "candidate", "merged_from"),
        ],
        related_adrs=[(left, "informed_by", "왼쪽 ADR의 운영 제약을 참조")],
    )

    assert validate_adr(merged) == []
    manifest = json.loads((merged / "실험" / "manifest.json").read_text("utf-8"))
    parent_refs = [
        "ADR-0186-experiment-v1/candidate",
        "ADR-0187-experiment-v1/candidate",
    ]
    assert manifest["design"]["arms"][0]["derived_from"] == parent_refs
    assert manifest["integration"]["parent_refs"] == parent_refs
    assert [row["parent_ref"] for row in manifest["integration"]["parent_contributions"]] == parent_refs
    assert manifest["relationships"][0]["adr_id"] == "ADR-0186"
    assert manifest["relationships"][0]["record_path"].endswith("claim.json")

    graph = build_experiment_graph(tmp_path)
    assert graph["validation_errors"] == []
    assert sum(
        edge["to"] == "ADR-0188-experiment-v1/baseline" and
        edge["relation"] == "merged_from"
        for edge in graph["edges"]
    ) == 2
    assert graph["adr_relationships"] == [{
        "from_adr": "ADR-0188",
        "to_adr": "ADR-0186",
        "relation": "informed_by",
        "note": "왼쪽 ADR의 운영 제약을 참조",
    }]


def test_multi_parent_merge_rejects_non_merge_relation_before_claim(tmp_path: Path) -> None:
    left = scaffold_adr(tmp_path, 189, "left-source", "왼쪽", "audit", [])
    right = scaffold_adr(tmp_path, 190, "right-source", "오른쪽", "audit", [])
    _complete_scaffold_run(left)
    _complete_scaffold_run(right)

    with pytest.raises(ValueError, match="every multi-parent relation must be merged_from"):
        scaffold_adr(
            tmp_path, 191, "invalid-merge", "잘못된 병합", "audit", [],
            parent_specs=[
                (left / "실험" / "manifest.json", "candidate", "extends"),
                (right / "실험" / "manifest.json", "candidate", "merged_from"),
            ],
        )
    assert not (tmp_path / "ADR-0191-invalid-merge").exists()


def test_promotion_candidate_requires_accepted_out_of_sample_complete_result(
    tmp_path: Path,
) -> None:
    target = scaffold_adr(
        tmp_path, 192, "premature-promotion", "성급한 승격", "probe", [])
    readme = target / "README.md"
    readme.write_text(
        readme.read_text("utf-8").replace(
            "main_wiring: unchanged", "main_wiring: promotion-candidate"),
        "utf-8",
    )

    errors = validate_adr(target)
    assert any("status must be Accepted" in error for error in errors)
    assert any("decision_eligible=true" in error for error in errors)
    assert any("in-sample" in error for error in errors)
    assert any("results must be complete" in error for error in errors)



def _planned_code_isolation(target: Path) -> dict:
    manifest_path = target / "실험" / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["design"]["code_isolation"] = {
        "schema_version": "adr-code-isolation-v1",
        "mode": "candidate_snapshot",
        "reason": None,
        "production_paths_modified_before_decision": False,
        "runtime_import_allowed": False,
        "production_registry_registered": False,
        "main_wiring_unchanged": True,
        "candidates": [{
            "candidate_id": "law-family-entry",
            "experiment_id": manifest["experiment_id"],
            "arm_id": "isolated-arm",
            "run_ids": ["run-001"],
            "manifest_path": (
                "lawrag/research/candidates/adr_0138/"
                "law-family-entry/candidate.json"
            ),
            "manifest_sha256": "PENDING",
            "revision_id": "PENDING",
            "revision_sha256": "PENDING",
            "runner_path": "scripts/law_family_entry_runner.py",
            "runner_sha256": "PENDING",
        }],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    return manifest


def test_adr_0138_requires_safe_code_isolation_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adr_structure, "ROOT", tmp_path)
    target = scaffold_adr(
        tmp_path / "docs" / "adr",
        138,
        "isolation-required",
        "격리 필수",
        "audit",
        [],
        candidate_arms=["isolated-arm"],
    )
    manifest_path = target / "실험" / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    del manifest["design"]["code_isolation"]
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    assert any(
        "code_isolation is required for ADR-0138+" in error
        for error in validate_adr(target)
    )

    manifest["design"]["code_isolation"] = {
        "schema_version": "adr-code-isolation-v1",
        "mode": "not_applicable",
        "reason": "제품 영향 구현 후보가 없는 구조 감사",
        "production_paths_modified_before_decision": True,
        "runtime_import_allowed": False,
        "production_registry_registered": False,
        "main_wiring_unchanged": True,
        "candidates": [],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    assert any(
        "production_paths_modified_before_decision must be false" in error
        for error in validate_adr(target)
    )


def test_code_isolation_allows_planned_hashes_then_verifies_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adr_structure, "ROOT", tmp_path)
    target = scaffold_adr(
        tmp_path / "docs" / "adr",
        138,
        "isolation-linkage",
        "격리 연결",
        "audit",
        [],
        candidate_arms=["isolated-arm"],
    )
    manifest = _planned_code_isolation(target)
    assert validate_adr(target) == []
    final_errors = validate_adr(target, final=True)
    assert any("manifest sha256 is PENDING" in error for error in final_errors)
    assert any("frozen revision is PENDING" in error for error in final_errors)
    assert any("runner sha256 is PENDING" in error for error in final_errors)

    candidate_dir = (
        tmp_path / "lawrag" / "research" / "candidates" /
        "adr_0138" / "law-family-entry"
    )
    candidate_dir.mkdir(parents=True)
    revision = {
        "revision_id": "rev-001",
        "frozen_at": "2026-08-31T00:00:00Z",
        "files": [],
    }
    revision["revision_sha256"] = _canonical_fixture_sha256(revision)
    candidate_manifest = {
        "schema_version": "adr-code-candidate-v1",
        "adr_id": "ADR-0138",
        "experiment_id": "ADR-0138-experiment-v1",
        "arm_id": "isolated-arm",
        "run_ids": ["run-001"],
        "candidate_id": "law-family-entry",
        "status": "research-only",
        "production_loadable": False,
        "revisions": [revision],
    }
    candidate_path = candidate_dir / "candidate.json"
    candidate_path.write_text(
        json.dumps(candidate_manifest, ensure_ascii=False, indent=2), "utf-8")
    runner = tmp_path / "scripts" / "law_family_entry_runner.py"
    runner.parent.mkdir()
    runner.write_text("RESULT = 'isolated'\n", "utf-8")

    isolation = manifest["design"]["code_isolation"]["candidates"][0]
    isolation["manifest_sha256"] = hashlib.sha256(
        candidate_path.read_bytes()).hexdigest()
    isolation["revision_id"] = "rev-001"
    isolation["revision_sha256"] = revision["revision_sha256"]
    isolation["runner_sha256"] = hashlib.sha256(runner.read_bytes()).hexdigest()
    manifest_path = target / "실험" / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    assert validate_adr(target) == []

    runner.write_text("RESULT = 'tampered'\n", "utf-8")
    assert any(
        "runner sha256 mismatch" in error for error in validate_adr(target)
    )
