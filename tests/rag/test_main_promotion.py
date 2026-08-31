from __future__ import annotations

import json
from pathlib import Path

import pytest

from lawrag.core.rag import main_promotion, switches


def _source(tmp_path: Path, *, eligible: bool = True, in_sample: bool = False) -> Path:
    adr = tmp_path / "ADR-0900-main-candidate"
    experiment = adr / "실험"
    experiment.mkdir(parents=True)
    (adr / "README.md").write_text(
        "\n".join([
            "---",
            "adr_id: ADR-0900",
            "status: Accepted",
            "main_wiring: promotion-candidate",
            "---",
            "# candidate",
            "",
        ]),
        "utf-8",
    )
    manifest = {
        "schema_version": "adr-experiment-v3",
        "adr_id": "ADR-0900",
        "experiment_id": "ADR-0900-experiment-v1",
        "in_sample": in_sample,
        "decision_eligible": eligible,
        "reservation": {"status": "completed"},
        "design": {
            "arms": [
                {"id": "baseline", "role": "baseline", "derived_from": []},
                {"id": "candidate", "role": "candidate", "derived_from": ["baseline"]},
            ]
        },
        "results": {"status": "complete"},
    }
    path = experiment / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return path


def _workspace(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    pipeline = tmp_path / "main" / "pipeline.json"
    receipts = tmp_path / "main" / "receipts.jsonl"
    engine = tmp_path / "engine.json"
    monkeypatch.setenv("RAG_MAIN_PIPELINE_MANIFEST", str(pipeline))
    monkeypatch.setenv("RAG_MAIN_PROMOTION_RECEIPTS", str(receipts))
    monkeypatch.setenv("RAG_ENGINE_RULES", str(engine))
    switches._cache.update(mtime=None, ovr={})
    return pipeline, receipts, engine


def test_verified_adr_arm_promotes_to_main_and_rolls_back(monkeypatch, tmp_path: Path) -> None:
    pipeline, receipts_path, engine = _workspace(monkeypatch, tmp_path)
    source = _source(tmp_path)
    code = tmp_path / "candidate.py"
    code.write_text("FEATURE = True\n", "utf-8")
    validation = tmp_path / "validation.json"
    validation.write_text('{"tests":"passed"}\n', "utf-8")

    plan = main_promotion.prepare_plan(
        source,
        "candidate",
        switch_changes={"legalclosure_feedback_explore": True},
        code_artifacts=[(code, "legalclosure_feedback_explore")],
        validation_receipts=[validation],
        actor="tester",
    )
    assert main_promotion.validate_plan(plan) == []
    with pytest.raises(ValueError, match="confirm_main"):
        main_promotion.apply_plan(
            plan, actor="tester", approval_note="승인", confirm_main=False)

    applied = main_promotion.apply_plan(
        plan, actor="tester", approval_note="holdout 통과", confirm_main=True)
    assert applied["state"]["generation"] == 1
    assert applied["state"]["active_promotions"][0]["arm_id"] == "candidate"
    assert pipeline.is_file() and receipts_path.is_file()
    assert switches.is_on("legalclosure_feedback_explore") is True
    row = next(row for row in switches.snapshot()
               if row["key"] == "legalclosure_feedback_explore")
    assert row["source"] == "main_promotion"
    provenance = main_promotion.runtime_provenance()
    assert provenance["generation"] == 1
    assert provenance["sources"][0]["adr_id"] == "ADR-0900"

    # 사람의 emergency override가 승격값보다 우선한다.
    switches.set_switch("legalclosure_feedback_explore", False)
    assert switches.is_on("legalclosure_feedback_explore") is False
    assert json.loads(engine.read_text("utf-8"))["switches"] == {
        "legalclosure_feedback_explore": False}

    rolled_back = main_promotion.rollback(
        plan["promotion_id"], actor="tester", note="회귀 발견", confirm_main=True)
    assert rolled_back["state"]["generation"] == 2
    assert rolled_back["state"]["active_promotions"] == []
    assert [row["action"] for row in main_promotion.read_receipts()] == [
        "apply", "rollback"]


def test_stale_plan_and_duplicate_active_arm_are_rejected(monkeypatch, tmp_path: Path) -> None:
    _workspace(monkeypatch, tmp_path)
    source = _source(tmp_path)
    validation = tmp_path / "validation.json"
    validation.write_text("{}\n", "utf-8")
    first = main_promotion.prepare_plan(
        source, "candidate", switch_changes={"query_guide": True},
        validation_receipts=[validation], actor="tester")
    stale = main_promotion.prepare_plan(
        source, "candidate", switch_changes={"query_guide": True},
        validation_receipts=[validation], actor="tester")
    main_promotion.apply_plan(
        first, actor="tester", approval_note="승인", confirm_main=True)

    errors = main_promotion.validate_plan(stale)
    assert any("stale plan" in error for error in errors)
    assert any("already active" in error for error in errors)


@pytest.mark.parametrize(
    ("eligible", "in_sample", "message"),
    [(False, False, "decision_eligible"), (True, True, "in-sample")],
)
def test_ineligible_or_in_sample_adr_cannot_prepare_main_plan(
    monkeypatch, tmp_path: Path, eligible: bool, in_sample: bool, message: str,
) -> None:
    _workspace(monkeypatch, tmp_path)
    source = _source(tmp_path, eligible=eligible, in_sample=in_sample)
    validation = tmp_path / "validation.json"
    validation.write_text("{}\n", "utf-8")

    with pytest.raises(ValueError, match=message):
        main_promotion.prepare_plan(
            source, "candidate", switch_changes={"query_guide": True},
            validation_receipts=[validation], actor="tester")


def test_code_artifact_requires_promoted_guard_switch(monkeypatch, tmp_path: Path) -> None:
    _workspace(monkeypatch, tmp_path)
    source = _source(tmp_path)
    code = tmp_path / "candidate.py"
    code.write_text("FEATURE = True\n", "utf-8")
    validation = tmp_path / "validation.json"
    validation.write_text("{}\n", "utf-8")

    with pytest.raises(ValueError, match="guard switch is not in promotion changes"):
        main_promotion.prepare_plan(
            source, "candidate", switch_changes={"query_guide": True},
            code_artifacts=[(code, "legalclosure_feedback_explore")],
            validation_receipts=[validation], actor="tester")
