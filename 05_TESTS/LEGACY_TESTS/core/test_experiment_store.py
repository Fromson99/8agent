from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from lawrag.platform.experiment_store import ExperimentStore, ExperimentStoreError


def _record(root: Path, area: str, adr_id: str, experiment_id: str, status: str) -> Path:
    path = root / area / f"{adr_id}-sample/실험/manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "adr_id": adr_id,
        "experiment_id": experiment_id,
        "results": {"status": status},
    }), "utf-8")
    return path


def test_resolves_current_and_legacy_records_by_id(tmp_path: Path) -> None:
    current = _record(
        tmp_path, "04_EXPERIMENTS/ADR", "ADR-0101", "ADR-0101-experiment-v1", "complete"
    )
    legacy = _record(
        tmp_path,
        "04_EXPERIMENTS/LEGACY_ADR",
        "ADR-0042",
        "ADR-0042-experiment-v2",
        "complete",
    )
    store = ExperimentStore(tmp_path)

    assert store.by_adr_id("ADR-0101", completed_only=True).manifest_path == current
    assert store.by_experiment_id("ADR-0042-experiment-v2").manifest_path == legacy


def test_duplicate_and_incomplete_id_resolution_fail_closed(tmp_path: Path) -> None:
    _record(tmp_path, "04_EXPERIMENTS/ADR", "ADR-0101", "duplicate", "not_run")
    _record(tmp_path, "04_EXPERIMENTS/LEGACY_ADR", "ADR-0101", "duplicate", "complete")
    store = ExperimentStore(tmp_path)

    with pytest.raises(ExperimentStoreError, match="ambiguous"):
        store.by_adr_id("ADR-0101")

    other = _record(tmp_path, "04_EXPERIMENTS/ADR", "ADR-0102", "pending", "not_run")
    assert other.is_file()
    with pytest.raises(ExperimentStoreError, match="not complete"):
        store.by_experiment_id("pending", completed_only=True)


def test_artifact_requires_exact_hash(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", "utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    store = ExperimentStore(tmp_path)

    assert store.artifact("artifact.json", digest) == artifact
    with pytest.raises(ExperimentStoreError, match="hash mismatch"):
        store.artifact("artifact.json", "0" * 64)
