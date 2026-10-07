"""Machine-readable stage catalog for the legal ontology lifecycle.

The JSON file is the human-reviewable source of truth.  This module adds the
cross-record checks that JSON Schema cannot express cleanly: unique stage IDs,
valid dependency references, acyclic ordering, and a one-to-one mapping to the
executable batch stages.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from lawrag.platform.paths import repository_root


SCHEMA_VERSION = "legal-ontology-lifecycle-v1"
PIPELINE_FILE = Path("00_SYSTEM/ONTOLOGY_PIPELINE.json")
PHASE_ORDER = ("input", "extract", "transform", "use", "restructure")


class CatalogError(ValueError):
    """The lifecycle catalog is ambiguous or cannot map to the runner."""


def catalog_path() -> Path:
    return repository_root() / PIPELINE_FILE


def load_catalog(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else catalog_path()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot read ontology pipeline catalog {target}: {exc}") from exc
    if not isinstance(value, dict):
        raise CatalogError("ontology pipeline catalog root must be an object")
    return value


def _strings(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise CatalogError(f"{field} must be a non-empty string list")
    return value


def validate_catalog(
    catalog: Mapping[str, Any],
    *,
    runner_stages: Iterable[str] | None = None,
) -> Mapping[str, Any]:
    if catalog.get("schema_version") != SCHEMA_VERSION:
        raise CatalogError(f"schema_version must be {SCHEMA_VERSION}")
    phases = catalog.get("phases")
    if not isinstance(phases, list):
        raise CatalogError("phases must be a list")
    phase_ids = [str(row.get("id") or "") for row in phases if isinstance(row, Mapping)]
    if tuple(phase_ids) != PHASE_ORDER:
        raise CatalogError(f"phases must be ordered as {PHASE_ORDER}")

    raw_stages = catalog.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        raise CatalogError("stages must be a non-empty list")
    stages: list[Mapping[str, Any]] = []
    for index, row in enumerate(raw_stages):
        if not isinstance(row, Mapping):
            raise CatalogError(f"stages[{index}] must be an object")
        stages.append(row)
    stage_ids = [str(row.get("id") or "") for row in stages]
    if any(not stage_id for stage_id in stage_ids) or len(stage_ids) != len(set(stage_ids)):
        raise CatalogError("stage IDs must be non-empty and unique")
    stage_set = set(stage_ids)
    positions = {stage_id: index for index, stage_id in enumerate(stage_ids)}
    phase_set = set(PHASE_ORDER)
    mapped_runner_stages: list[str] = []

    for row in stages:
        stage_id = str(row["id"])
        phase = str(row.get("phase") or "")
        if phase not in phase_set:
            raise CatalogError(f"{stage_id}: unknown phase {phase!r}")
        if row.get("auto_promote") is not False:
            raise CatalogError(f"{stage_id}: auto_promote must be false")
        policy = str(row.get("execution_policy") or "")
        if policy not in {"automatic", "explicit", "manual_only"}:
            raise CatalogError(f"{stage_id}: invalid execution_policy {policy!r}")
        runner_stage = row.get("runner_stage")
        if policy == "manual_only":
            if runner_stage is not None:
                raise CatalogError(f"{stage_id}: manual_only stage cannot name a runner_stage")
        elif not isinstance(runner_stage, str) or not runner_stage:
            raise CatalogError(f"{stage_id}: executable stage requires runner_stage")
        else:
            mapped_runner_stages.append(runner_stage)
        dependencies = _strings(row.get("depends_on"), f"{stage_id}.depends_on") if row.get("depends_on") else []
        unknown = sorted(set(dependencies) - stage_set)
        if unknown:
            raise CatalogError(f"{stage_id}: unknown dependencies {unknown}")
        late = [dependency for dependency in dependencies if positions[dependency] >= positions[stage_id]]
        if late:
            raise CatalogError(f"{stage_id}: dependencies must precede the stage: {late}")

    if len(mapped_runner_stages) != len(set(mapped_runner_stages)):
        raise CatalogError("runner_stage values must be unique")
    if runner_stages is not None:
        expected = tuple(runner_stages)
        actual = tuple(mapped_runner_stages)
        if set(actual) != set(expected):
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            raise CatalogError(f"runner mapping mismatch: missing={missing}, extra={extra}")
        if [value for value in actual if value in expected] != list(expected):
            raise CatalogError("runner stages must preserve batch execution order")
    return catalog


def stages_by_phase(catalog: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    result = {phase: [] for phase in PHASE_ORDER}
    for stage in catalog.get("stages") or []:
        if isinstance(stage, Mapping) and stage.get("phase") in result:
            result[str(stage["phase"])].append(stage)
    return result
