from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import adr_candidate


def test_candidate_root_is_mutable_workspace_tree() -> None:
    assert adr_candidate.CANDIDATE_ROOT == (
        adr_candidate.ROOT / "02_BACKEND/lawrag/research/candidates"
    )


def test_candidate_validate_detects_snapshot_tampering(tmp_path: Path) -> None:
    copied = tmp_path / "copy.py"
    copied.write_text("VALUE = 1\n", "utf-8")
    manifest = {
        "schema_version": "adr-code-candidate-v1",
        "production_loadable": False,
        "files": [{
            "snapshot_path": copied.relative_to(adr_candidate.ROOT).as_posix()
            if copied.is_relative_to(adr_candidate.ROOT) else str(copied),
            "snapshot_sha256": adr_candidate.sha256(copied),
        }],
    }
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(manifest), "utf-8")

    assert adr_candidate.validate(path) == []
    copied.write_text("VALUE = 2\n", "utf-8")
    assert any("hash mismatch" in error for error in adr_candidate.validate(path))

    adr_candidate.freeze(path)
    assert adr_candidate.validate(path) == []
    frozen = json.loads(path.read_text("utf-8"))
    assert len(frozen["revisions"]) == 1



def _strict_adr(root: Path) -> tuple[Path, Path]:
    source = root / "lawrag" / "core" / "example.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", "utf-8")
    adr = root / "docs" / "adr" / "ADR-0138-isolated-candidate"
    (adr / "실험").mkdir(parents=True)
    (adr / "claim.json").write_text(
        json.dumps({"adr_id": "ADR-0138"}), "utf-8")
    (adr / "실험" / "manifest.json").write_text(json.dumps({
        "experiment_id": "ADR-0138-experiment-v1",
        "design": {"arms": [
            {"id": "baseline", "role": "baseline"},
            {"id": "isolated-arm", "role": "candidate"},
        ]},
        "runs": [{
            "id": "run-001",
            "arm_ids": ["baseline", "isolated-arm"],
        }],
    }), "utf-8")
    return adr, source


def test_strict_candidate_freezes_immutable_linked_revisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adr_candidate, "ROOT", tmp_path)
    monkeypatch.setattr(
        adr_candidate,
        "CANDIDATE_ROOT",
        tmp_path / "lawrag" / "research" / "candidates",
    )
    adr, source = _strict_adr(tmp_path)

    with pytest.raises(ValueError, match="--experiment-id"):
        adr_candidate.snapshot(adr, "law-family-entry", [str(source)])

    target = adr_candidate.snapshot(
        adr,
        "law-family-entry",
        [str(source)],
        experiment_id="ADR-0138-experiment-v1",
        arm_id="isolated-arm",
        run_ids=["run-001"],
    )
    assert adr_candidate.validate(target) == ["frozen revision required"]

    adr_candidate.freeze(target)
    assert adr_candidate.validate(target) == []
    manifest_path = target / "candidate.json"
    first = json.loads(manifest_path.read_text("utf-8"))
    initial_hash = first["files"][0]["initial_snapshot_sha256"]
    assert first["revisions"][0]["revision_id"] == "rev-001"
    assert first["revisions"][0]["revision_sha256"]
    frozen_first = adr_candidate._resolve_stored_path(
        first["revisions"][0]["files"][0]["frozen_path"])
    assert frozen_first.read_text("utf-8") == "VALUE = 1\n"

    snapshot_path = adr_candidate._resolve_stored_path(
        first["files"][0]["snapshot_path"])
    snapshot_path.write_text("VALUE = 2\n", "utf-8")
    drift_errors = adr_candidate.validate(target)
    assert any("snapshot hash mismatch" in error for error in drift_errors)
    assert any("latest frozen revision" in error for error in drift_errors)

    adr_candidate.freeze(target)
    assert adr_candidate.validate(target) == []
    second = json.loads(manifest_path.read_text("utf-8"))
    assert [row["revision_id"] for row in second["revisions"]] == [
        "rev-001", "rev-002"]
    assert second["files"][0]["initial_snapshot_sha256"] == initial_hash
    assert frozen_first.read_text("utf-8") == "VALUE = 1\n"

    frozen_first.write_text("tampered\n", "utf-8")
    assert any(
        "frozen file hash mismatch" in error
        for error in adr_candidate.validate(target)
    )


def test_candidate_v2_registers_absent_upstream_without_false_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adr_candidate, "ROOT", tmp_path)
    monkeypatch.setattr(
        adr_candidate,
        "CANDIDATE_ROOT",
        tmp_path / "lawrag" / "research" / "candidates",
    )
    adr, source = _strict_adr(tmp_path)
    target = adr_candidate.snapshot(
        adr,
        "law-family-entry",
        [str(source)],
        experiment_id="ADR-0138-experiment-v1",
        arm_id="isolated-arm",
        run_ids=["run-001"],
    )
    proposal_target = Path("00_SYSTEM/SCHEMAS/new-contract.schema.json")
    proposal = target / "snapshot" / proposal_target
    proposal.parent.mkdir(parents=True)
    proposal.write_text('{"type":"object"}\n', "utf-8")

    adr_candidate.register_file(
        target,
        proposal_target.as_posix(),
        upstream_state="absent",
    )
    manifest = json.loads((target / "candidate.json").read_text("utf-8"))
    assert manifest["schema_version"] == "adr-code-candidate-v2"
    row = next(
        item for item in manifest["files"]
        if item["target_path"] == proposal_target.as_posix()
    )
    assert row["upstream_state"] == "absent"
    assert row["upstream_path"] is None
    assert row["upstream_sha256"] is None
    assert row["initial_snapshot_sha256"] == adr_candidate.sha256(proposal)
    assert row["upstream_absence_verified_at"].endswith("Z")

    adr_candidate.freeze(target)
    assert adr_candidate.validate(target) == []


def test_candidate_v2_freeze_rejects_absent_target_that_appeared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adr_candidate, "ROOT", tmp_path)
    monkeypatch.setattr(
        adr_candidate,
        "CANDIDATE_ROOT",
        tmp_path / "lawrag" / "research" / "candidates",
    )
    adr, source = _strict_adr(tmp_path)
    target = adr_candidate.snapshot(
        adr,
        "law-family-entry",
        [str(source)],
        experiment_id="ADR-0138-experiment-v1",
        arm_id="isolated-arm",
        run_ids=["run-001"],
    )
    proposal_target = Path("00_SYSTEM/SCHEMAS/new-contract.schema.json")
    proposal = target / "snapshot" / proposal_target
    proposal.parent.mkdir(parents=True)
    proposal.write_text('{"type":"object"}\n', "utf-8")
    adr_candidate.register_file(
        target,
        proposal_target.as_posix(),
        upstream_state="absent",
    )
    canonical = tmp_path / proposal_target
    canonical.parent.mkdir(parents=True)
    canonical.write_text("appeared\n", "utf-8")

    with pytest.raises(ValueError, match="absent upstream appeared"):
        adr_candidate.freeze(target)


def test_candidate_v2_rejects_unregistered_snapshot_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adr_candidate, "ROOT", tmp_path)
    monkeypatch.setattr(
        adr_candidate,
        "CANDIDATE_ROOT",
        tmp_path / "lawrag" / "research" / "candidates",
    )
    adr, source = _strict_adr(tmp_path)
    target = adr_candidate.snapshot(
        adr,
        "law-family-entry",
        [str(source)],
        experiment_id="ADR-0138-experiment-v1",
        arm_id="isolated-arm",
        run_ids=["run-001"],
    )
    rogue = target / "snapshot" / "unregistered.py"
    rogue.write_text("VALUE = 2\n", "utf-8")

    errors = adr_candidate.validate(target)
    assert any("unregistered candidate snapshot file" in error for error in errors)
    with pytest.raises(ValueError, match="inventory does not match"):
        adr_candidate.freeze(target)


def test_candidate_v2_imports_stable_present_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adr_candidate, "ROOT", tmp_path)
    monkeypatch.setattr(
        adr_candidate,
        "CANDIDATE_ROOT",
        tmp_path / "lawrag" / "research" / "candidates",
    )
    adr, source = _strict_adr(tmp_path)
    target = adr_candidate.snapshot(
        adr,
        "law-family-entry",
        [str(source)],
        experiment_id="ADR-0138-experiment-v1",
        arm_id="isolated-arm",
        run_ids=["run-001"],
    )
    added = tmp_path / "lawrag/core/added.py"
    added.write_text("ADDED = True\n", "utf-8")

    adr_candidate.import_present_file(target, "lawrag/core/added.py")

    copied = target / "snapshot/lawrag/core/added.py"
    manifest = json.loads((target / "candidate.json").read_text("utf-8"))
    row = next(
        item for item in manifest["files"]
        if item["target_path"] == "lawrag/core/added.py"
    )
    assert copied.read_bytes() == added.read_bytes()
    assert row["upstream_state"] == "present"
    assert row["upstream_sha256"] == adr_candidate.sha256(added)
    assert row["snapshot_sha256"] == adr_candidate.sha256(copied)
    with pytest.raises(ValueError, match="already exists"):
        adr_candidate.import_present_file(target, "lawrag/core/added.py")


def test_candidate_v2_import_rejects_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adr_candidate, "ROOT", tmp_path)
    monkeypatch.setattr(
        adr_candidate,
        "CANDIDATE_ROOT",
        tmp_path / "lawrag" / "research" / "candidates",
    )
    adr, source = _strict_adr(tmp_path)
    target = adr_candidate.snapshot(
        adr,
        "law-family-entry",
        [str(source)],
        experiment_id="ADR-0138-experiment-v1",
        arm_id="isolated-arm",
        run_ids=["run-001"],
    )
    drifting = tmp_path / "lawrag/core/drifting.py"
    drifting.write_text("VALUE = 1\n", "utf-8")
    original_copy = adr_candidate.shutil.copyfile

    def copy_then_mutate(*args, **kwargs):
        result = original_copy(*args, **kwargs)
        drifting.write_text("VALUE = 2\n", "utf-8")
        return result

    monkeypatch.setattr(adr_candidate.shutil, "copyfile", copy_then_mutate)
    with pytest.raises(ValueError, match="changed during import"):
        adr_candidate.import_present_file(target, "lawrag/core/drifting.py")
    assert not (target / "snapshot/lawrag/core/drifting.py").exists()


def test_candidate_v2_refreshes_registered_files_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adr_candidate, "ROOT", tmp_path)
    monkeypatch.setattr(
        adr_candidate,
        "CANDIDATE_ROOT",
        tmp_path / "lawrag" / "research" / "candidates",
    )
    adr, source = _strict_adr(tmp_path)
    target = adr_candidate.snapshot(
        adr,
        "law-family-entry",
        [str(source)],
        experiment_id="ADR-0138-experiment-v1",
        arm_id="isolated-arm",
        run_ids=["run-001"],
    )
    manifest_path = target / "candidate.json"
    before = json.loads(manifest_path.read_text("utf-8"))
    before_row = before["files"][0]
    copied = target / "snapshot/lawrag/core/example.py"
    copied.write_text("VALUE = 2\n", "utf-8")

    adr_candidate.refresh(target)

    after = json.loads(manifest_path.read_text("utf-8"))
    after_row = after["files"][0]
    assert after_row["upstream_sha256"] == before_row["upstream_sha256"]
    assert after_row["initial_snapshot_sha256"] == before_row["initial_snapshot_sha256"]
    assert after_row["snapshot_sha256"] == adr_candidate.sha256(copied)
    assert after_row["bytes"] == copied.stat().st_size

    rogue = target / "snapshot/rogue.py"
    rogue.write_text("ROGUE = True\n", "utf-8")
    with pytest.raises(ValueError, match="inventory does not match"):
        adr_candidate.refresh(target)
