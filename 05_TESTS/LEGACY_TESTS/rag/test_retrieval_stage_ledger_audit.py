from __future__ import annotations

import json

import pytest

from scripts import rag_retrieval_stage_ledger_audit as audit


@pytest.fixture(scope="module")
def frozen_sources():
    return audit._load_frozen_sources()


@pytest.fixture(scope="module")
def frozen_report(frozen_sources):
    manifest = json.loads(audit.MANIFEST.read_text(encoding="utf-8"))
    run = next(row for row in manifest["runs"] if row["id"] == audit.RUN_ID)
    assert audit._sha256(audit.OUTPUT) == run["sha256"]
    return json.loads(audit.OUTPUT.read_text(encoding="utf-8"))


def test_frozen_source_and_manifest_hash_gates():
    manifest_sha256 = audit._sha256(audit.MANIFEST)
    manifest = json.loads(audit.MANIFEST.read_text(encoding="utf-8"))
    assert manifest["adr_id"] == audit.ADR_ID

    # 완료 실행은 당시 구현 hash에 결속된다. 공용 validator가 진화한 뒤 현재
    # 파일로 재실행하지 않고, 위 fixture에서 고정 artifact를 검증해 읽는다.
    with pytest.raises(ValueError, match="runner hash mismatch|implementation_sha256 mismatch"):
        audit._validate_manifest(
            audit.MANIFEST,
            expected_sha256=manifest_sha256,
        )

    with pytest.raises(ValueError, match="manifest hash mismatch"):
        audit._validate_manifest(
            audit.MANIFEST,
            expected_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="manifest SHA-256 is required"):
        audit._validate_manifest(
            audit.MANIFEST,
            expected_sha256="PENDING",
        )


def test_manifest_stage_plan_is_an_exact_ordered_gate(tmp_path):
    manifest = json.loads(audit.MANIFEST.read_text(encoding="utf-8"))
    assert manifest["design"]["backfill_stage_plan"] == (
        audit.EXPECTED_STAGE_PLAN
    )
    manifest["design"]["backfill_stage_plan"][audit.CANDIDATE_ARM][
        -1
    ]["parent_stage_ids"] = ["wrong-parent"]
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="backfill stage plan mismatch"):
        audit._validate_manifest(
            path,
            expected_sha256=audit._sha256(path),
        )


def test_backfill_has_exact_61_case_83_gold_contract(frozen_report):
    assert frozen_report["schema_version"] == (
        "retrieval-stage-ledger-v1"
    )
    assert set(frozen_report) == {
        "schema_version",
        "adr_id",
        "experiment_id",
        "accounting_unit",
        "computed_post_selection",
        "gold_visible_to_product",
        "runs",
        "audit",
        "artifact_sha256",
    }
    assert frozen_report["audit"]["receipt_schema_version"] == (
        "retrieval-stage-ledger-audit-v1"
    )
    assert frozen_report["audit"]["contract"] == {
        "offline_backfill": True,
        "computed_post_selection": True,
        "gold_visible_to_product": False,
        "llm_calls": 0,
        "provider_calls": 0,
        "main_wiring": "unchanged",
        "raw_counts_are_occurrences": True,
        "canonical_counts_are_unique_article_roots": True,
    }
    assert frozen_report["audit"]["summary"]["cases"] == 61
    assert frozen_report["audit"]["summary"]["scorable_cases"] == 60
    assert frozen_report["audit"]["summary"]["gold_total"] == 83
    assert frozen_report["audit"]["summary"][
        "corpus_article_roots"
    ] == 12019
    assert frozen_report["computed_post_selection"] is True
    assert frozen_report["gold_visible_to_product"] is False


def test_candidate_stage_counts_recall_and_all_gold_cases(frozen_report):
    stages = frozen_report["audit"]["summary"]["candidate_stages"]
    expected = {
        "raw-pool": (3492, 3620, 68, 48),
        "canonical-pool": (3492, 3492, 68, 48),
        "raw-incumbent": (1112, 1155, 65, 45),
        "canonical-b0": (1112, 1112, 65, 45),
        "baseline-core": (1036, 1036, 64, 44),
        "b0-plus-admissible": (2585, 2585, 68, 48),
        "b0-plus-evaluated": (1861, 1861, 68, 48),
        "winner-pre-eviction": (1255, 1255, 65, 45),
        "final-selected": (1210, 1210, 65, 45),
    }
    for stage_id, (
        canonical_count,
        occurrence_count,
        gold_after,
        all_gold_cases,
    ) in expected.items():
        stage = stages[stage_id]
        assert stage["after_count"] == canonical_count
        assert stage["occurrence_count"] == occurrence_count
        assert stage["gold_total"] == 83
        assert stage["gold_after"] == gold_after
        assert stage["golden_recall"] == round(gold_after / 83, 6)
        assert stage["all_gold_cases"] == all_gold_cases


def test_parent_final_is_separate_exact_replay(frozen_report):
    baseline = frozen_report["audit"]["summary"]["baseline_stages"]
    assert baseline["parent-source"]["after_count"] == 1210
    assert baseline["parent-source"]["gold_after"] == 66
    stage = baseline["parent-final"]
    assert stage["after_count"] == 1210
    assert stage["occurrence_count"] == 1210
    assert stage["gold_total"] == 83
    assert stage["gold_after"] == 66
    assert stage["golden_recall"] == round(66 / 83, 6)
    assert stage["all_gold_cases"] == 46


def test_three_pool_gold_candidates_reach_evaluation_but_not_winner(
    frozen_report,
):
    unresolved = []
    for case in frozen_report["audit"]["gold_fates_by_case"]:
        for gold in case["gold"]:
            if gold["fate"] == (
                "rejected_in_unresolved_bundle_or_objective_interval"
            ):
                unresolved.append(
                    (
                        case["case_id"],
                        gold["law"],
                        gold["article"],
                        gold["coordinate"],
                    )
                )
                membership = gold["membership"]
                assert membership["b0-plus-admissible"] is True
                assert membership["b0-plus-evaluated"] is True
                assert membership["winner-pre-eviction"] is False
                assert membership["final-selected"] is False

    assert unresolved == [
        (
            "cm-004",
            "증권 인수업무 등에 관한 규정",
            "제5조",
            ["7687ac5d901e9a4a", 39],
        ),
        (
            "cm-009",
            "코스닥시장 상장규정",
            "제13조",
            ["3521c3aaa5a735fd", 175],
        ),
        (
            "fsc-hard-009",
            "자본시장과 금융투자업에 관한 법률 시행령",
            "제46조",
            ["2fc762b3b8ed81f0", 791],
        ),
    ]


def test_no_gold_is_lost_by_canonical_collapse_or_final_eviction(
    frozen_report,
):
    stages = frozen_report["audit"]["summary"]["candidate_stages"]
    assert stages["raw-pool"]["gold_after"] == 68
    assert stages["canonical-pool"]["gold_after"] == 68
    assert stages["raw-incumbent"]["gold_after"] == 65
    assert stages["canonical-b0"]["gold_after"] == 65
    assert stages["winner-pre-eviction"]["gold_after"] == 65
    assert stages["final-selected"]["gold_after"] == 65

    evicted_gold = [
        gold
        for case in frozen_report["audit"]["gold_fates_by_case"]
        for gold in case["gold"]
        if gold["fate"] == "evicted_after_winner_addition"
    ]
    assert evicted_gold == []


def test_upstream_misses_and_parent_only_regression_are_identified(
    frozen_report,
):
    fate_counts = frozen_report["audit"]["summary"]["fate_counts"]
    assert fate_counts["not_generated_upstream"] == 15
    assert fate_counts[
        "rejected_in_unresolved_bundle_or_objective_interval"
    ] == 3
    assert fate_counts["retained_in_candidate_final"] == 65
    assert frozen_report["audit"]["summary"][
        "parent_only_regressions"
    ] == [
        {
            "case_id": "cm-004",
            "coordinate": ["7687ac5d901e9a4a", 39],
            "law": "증권 인수업무 등에 관한 규정",
            "article": "제5조",
        }
    ]


def test_unrecoverable_bundle_substages_are_not_claimed_exact(
    frozen_report,
):
    reconstruction = frozen_report["audit"]["reconstruction"]
    assert reconstruction["status"] == "incomplete"
    assert len(reconstruction["unavailable_boundaries"]) == 2
    assert {
        value["status"] for value in reconstruction["unavailable_boundaries"]
    } == {"incomplete"}
    assert reconstruction["coarse_transition"] == {
        "from_stage": "b0-plus-evaluated",
        "to_stage": "winner-pre-eviction",
        "boundary_sets_exact": True,
        "internal_discard_attribution": "incomplete",
        "discard_reason": (
            "unresolved_bundle_feasibility_or_objective_from_frozen_trace"
        ),
    }
    assert frozen_report["audit"]["summary"]["bundle_totals"] == {
        "closure_screened_bundles": 146531,
        "dominance_screened_bundles": 36675,
        "evaluated_bundles": 270732,
        "extra_eviction_bundles_screened": 162880,
        "feasible_bundles": 87526,
        "objective_bound_bundles_screened": 82118,
    }


def test_report_generation_is_deterministic(frozen_sources):
    adr76, adr68 = frozen_sources
    manifest_sha256 = audit._sha256(audit.MANIFEST)
    first = audit.build_report(
        adr76,
        adr68,
        manifest_path=audit.MANIFEST,
        manifest_sha256=manifest_sha256,
    )
    second = audit.build_report(
        adr76,
        adr68,
        manifest_path=audit.MANIFEST,
        manifest_sha256=manifest_sha256,
    )
    assert first == second
    assert "content_sha256" not in first
    assert first["artifact_sha256"] == second["artifact_sha256"]
    unhashed = {
        key: value for key, value in first.items()
        if key != "artifact_sha256"
    }
    assert first["artifact_sha256"] == audit._json_sha256(unhashed)


def test_validate_only_performs_full_backfill_without_writing(
    tmp_path,
    capsys,
):
    output = tmp_path / "must-not-exist.json"
    manifest_sha256 = audit._sha256(audit.MANIFEST)
    with pytest.raises(ValueError, match="runner hash mismatch|implementation_sha256 mismatch"):
        audit.main(
            [
                "--manifest",
                str(audit.MANIFEST),
                "--manifest-sha256",
                manifest_sha256,
                "--output",
                str(output),
                "--validate-only",
            ]
        )
    assert not output.exists()
    assert capsys.readouterr().out == ""
