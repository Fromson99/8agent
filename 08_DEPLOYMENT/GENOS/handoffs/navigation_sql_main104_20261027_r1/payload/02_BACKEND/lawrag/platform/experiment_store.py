"""ID-first, hash-verifying access to current and migrated ADR records."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from lawrag.platform.stored_paths import StoredPathError, resolve_stored_path


ADR_ID = re.compile(r"^ADR-\d{4}$")


class ExperimentStoreError(ValueError):
    """An ADR reference is missing, ambiguous, malformed, or hash-invalid."""


@dataclass(frozen=True)
class ExperimentRecord:
    adr_id: str
    experiment_id: str
    adr_path: Path
    manifest_path: Path
    manifest_sha256: str
    manifest: dict


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExperimentStore:
    """Resolve immutable experiment identities without persisting moved paths.

    Both the current ADR area and the receipt-migrated legacy ADR area are
    indexed.  Duplicate IDs fail closed instead of choosing by directory order.
    """

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.roots = (
            self.workspace / "04_EXPERIMENTS/ADR",
            self.workspace / "04_EXPERIMENTS/LEGACY_ADR",
        )

    def _records(self) -> tuple[ExperimentRecord, ...]:
        records: list[ExperimentRecord] = []
        for root in self.roots:
            if not root.is_dir():
                continue
            for adr_path in sorted(root.glob("ADR-[0-9][0-9][0-9][0-9]-*")):
                manifest_path = adr_path / "실험/manifest.json"
                if not manifest_path.is_file() or manifest_path.is_symlink():
                    continue
                try:
                    manifest = json.loads(manifest_path.read_text("utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise ExperimentStoreError(
                        f"cannot read experiment manifest: {manifest_path}: {exc}"
                    ) from exc
                if not isinstance(manifest, dict):
                    raise ExperimentStoreError(
                        f"experiment manifest must be an object: {manifest_path}"
                    )
                adr_id = str(manifest.get("adr_id") or "")
                experiment_id = str(manifest.get("experiment_id") or "")
                if not ADR_ID.fullmatch(adr_id) or not experiment_id:
                    raise ExperimentStoreError(
                        f"experiment manifest has invalid IDs: {manifest_path}"
                    )
                if not adr_path.name.startswith(f"{adr_id}-"):
                    raise ExperimentStoreError(
                        f"ADR directory and manifest ID disagree: {manifest_path}"
                    )
                records.append(ExperimentRecord(
                    adr_id=adr_id,
                    experiment_id=experiment_id,
                    adr_path=adr_path,
                    manifest_path=manifest_path,
                    manifest_sha256=_sha256(manifest_path),
                    manifest=manifest,
                ))
        return tuple(records)

    @staticmethod
    def _one(records: list[ExperimentRecord], identity: str) -> ExperimentRecord:
        if not records:
            raise ExperimentStoreError(f"experiment record not found: {identity}")
        if len(records) != 1:
            paths = ", ".join(str(row.manifest_path) for row in records)
            raise ExperimentStoreError(f"ambiguous experiment identity {identity}: {paths}")
        return records[0]

    def by_adr_id(self, adr_id: str, *, completed_only: bool = False) -> ExperimentRecord:
        if not ADR_ID.fullmatch(adr_id):
            raise ExperimentStoreError(f"invalid ADR ID: {adr_id}")
        record = self._one(
            [row for row in self._records() if row.adr_id == adr_id], adr_id
        )
        self._require_completion(record, completed_only)
        return record

    def by_experiment_id(
        self, experiment_id: str, *, completed_only: bool = False
    ) -> ExperimentRecord:
        if not experiment_id or "/" in experiment_id or "\\" in experiment_id:
            raise ExperimentStoreError(f"invalid experiment ID: {experiment_id}")
        record = self._one(
            [row for row in self._records() if row.experiment_id == experiment_id],
            experiment_id,
        )
        self._require_completion(record, completed_only)
        return record

    @staticmethod
    def _require_completion(record: ExperimentRecord, required: bool) -> None:
        if required and (record.manifest.get("results") or {}).get("status") != "complete":
            raise ExperimentStoreError(f"experiment is not complete: {record.experiment_id}")

    def artifact(self, stored_path: object, expected_sha256: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", str(expected_sha256 or "")):
            raise ExperimentStoreError("expected artifact SHA-256 must be lowercase hex")
        try:
            path = resolve_stored_path(self.workspace, stored_path)
        except StoredPathError as exc:
            raise ExperimentStoreError(str(exc)) from exc
        if not path.is_file() or path.is_symlink():
            raise ExperimentStoreError(f"artifact must be a regular file: {path}")
        actual = _sha256(path)
        if actual != expected_sha256:
            raise ExperimentStoreError(
                f"artifact hash mismatch: {stored_path}: expected {expected_sha256}, got {actual}"
            )
        return path
