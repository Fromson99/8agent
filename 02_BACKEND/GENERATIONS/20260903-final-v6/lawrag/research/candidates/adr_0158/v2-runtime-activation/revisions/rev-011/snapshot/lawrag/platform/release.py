"""Hash-locked release contract shared by local, onsite, and GenOS runtimes.

The original stateless validators remain the public boundary for release
candidates.  This isolated ADR candidate also contains a small POSIX
``ReleaseStore`` deployment adapter.  It installs immutable manifests and
validation receipts, then changes one ``ACTIVE_RELEASE.json`` pointer with a
generation-and-hash compare-and-swap and an append-only activation ledger.

The store never edits an installed release.  Rollback is another activation of
the immediately previous immutable release and therefore always advances the
active generation.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Iterator, Mapping

from lawrag.datasets.catalog import UnifiedCorpusView


SCHEMA_VERSION = "release-manifest-v1"
LEGACY_ACTIVATION_PLAN_SCHEMA = "release-activation-plan-v1"
ACTIVATION_PLAN_SCHEMA = "release-activation-plan-v2"
ACTIVE_POINTER_SCHEMA = "active-release-v1"
VALIDATION_RECEIPT_SCHEMA = "release-validation-receipt-v1"
ACTIVATION_RECEIPT_SCHEMA = "release-activation-receipt-v1"
INDEX_BUILD_FINGERPRINT_SCHEMA = "index-build-fingerprint-v1"
RUNTIME_BINDING_SCHEMA = "release-runtime-binding-v2"
RUNTIME_PROVENANCE_RESULT_SCHEMA = "release-runtime-provenance-result-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,191}$")
_TARGETS = frozenset({"genos", "onsite", "local"})
_LAYOUTS = frozenset({"v1", "v2"})
_INDEX_KINDS = frozenset({"lexical", "vector"})
_RECEIPT_KINDS = frozenset({"schema", "hash", "acl", "smoke", "provenance"})
_RUNTIME_PATH_KEYS = frozenset(
    {
        "STRUCTURE_STORE",
        "STRUCTURE_CUSTOM_DIR",
        "GLOSSARY_STORE",
        "RAG_LINKS_STORE",
        "RAG_VECTOR_STORE",
    }
)


class ReleaseContractError(ValueError):
    """A release mixes incompatible code, data, semantics, or indexes."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _identifier(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not _ID.fullmatch(text):
        raise ReleaseContractError(f"invalid {field}: {text!r}")
    return text


def _hash(value: object, field: str) -> str:
    text = str(value or "")
    if not _SHA256.fullmatch(text):
        raise ReleaseContractError(f"{field} must be sha256")
    return text


def _object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReleaseContractError(f"{field} must be an object")
    return value


def _reject_unknown(
    blob: Mapping[str, Any], allowed: frozenset[str], field: str
) -> None:
    unknown = sorted(set(blob) - allowed)
    if unknown:
        raise ReleaseContractError(
            f"unknown {field} fields: {', '.join(str(value) for value in unknown)}"
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _timestamp(value: object, field: str) -> str:
    """Return a strict UTC RFC-3339 timestamp used by persisted store records."""

    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseContractError(f"{field} must be an RFC-3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ReleaseContractError(f"{field} must be UTC")
    return text


def _required_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ReleaseContractError(f"{field} is required")
    return text


@dataclass(frozen=True)
class MainBinding:
    pipeline_id: str
    runtime_profile: str
    generation: int
    state_sha256: str
    # Historical wire name; binds ``main-rag-transition-chain-v1`` bytes.
    promotion_receipt_sha256: str | None
    promotion_plan_sha256: str | None


@dataclass(frozen=True)
class SourceSetBinding:
    source_set_id: str
    generation_id: str
    sha256: str
    export_allowed: bool
    # Legacy releases omit the six serving proofs.  The SourceSet content
    # snapshot adapter accepts only the all-present form so a lock or
    # materialization path can never become its own authority.
    lock_sha256: str | None = None
    lock_artifact_sha256: str | None = None
    materialization_sha256: str | None = None
    materialization_receipt_sha256: str | None = None
    catalog_sha256: str | None = None
    catalog_artifact_sha256: str | None = None


@dataclass(frozen=True)
class SemanticBinding:
    generation_id: str
    authority_generation: str
    content_sha256: str
    source_set_sha256: str
    runtime_wired: bool


@dataclass(frozen=True)
class IndexBinding:
    kind: str
    artifact_id: str
    artifact_sha256: str
    source_set_sha256: str
    semantic_generation: str
    build_fingerprint: str
    embedding_model_fingerprint: str | None


@dataclass(frozen=True)
class ValidationReceipt:
    kind: str
    receipt_id: str
    sha256: str


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    target: str
    layout_version: str
    created_at: str
    code_revision: str
    code_package_sha256: str
    main: MainBinding
    source_set: SourceSetBinding
    semantics: SemanticBinding
    indexes: tuple[IndexBinding, ...]
    manifest_sha256: str

    def receipt(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "release_id": self.release_id,
            "target": self.target,
            "layout_version": self.layout_version,
            "manifest_sha256": self.manifest_sha256,
            "code_revision": self.code_revision,
            "code_package_sha256": self.code_package_sha256,
            "main_generation": self.main.generation,
            "main_state_sha256": self.main.state_sha256,
            "main_promotion_receipt_sha256": self.main.promotion_receipt_sha256,
            "main_promotion_plan_sha256": self.main.promotion_plan_sha256,
            "source_set_id": self.source_set.source_set_id,
            "source_set_generation": self.source_set.generation_id,
            "source_set_sha256": self.source_set.sha256,
            "semantic_generation": self.semantics.generation_id,
            "authority_generation": self.semantics.authority_generation,
            "semantic_content_sha256": self.semantics.content_sha256,
            "indexes": {
                index.kind: {
                    "artifact_id": index.artifact_id,
                    "artifact_sha256": index.artifact_sha256,
                    "build_fingerprint": index.build_fingerprint,
                    "embedding_model_fingerprint": index.embedding_model_fingerprint,
                }
                for index in self.indexes
            },
        }
        if self.source_set.lock_sha256 is not None:
            value["source_set_lock_sha256"] = self.source_set.lock_sha256
            value["source_set_lock_artifact_sha256"] = (
                self.source_set.lock_artifact_sha256
            )
            value["source_set_materialization_sha256"] = (
                self.source_set.materialization_sha256
            )
            value["source_set_materialization_receipt_sha256"] = (
                self.source_set.materialization_receipt_sha256
            )
            value["source_set_catalog_sha256"] = self.source_set.catalog_sha256
            value["source_set_catalog_artifact_sha256"] = (
                self.source_set.catalog_artifact_sha256
            )
        return value


@dataclass(frozen=True)
class ReleaseActivationPlan:
    schema_version: str
    action: str
    activation_id: str
    target: str
    created_at: str
    release_id: str
    release_manifest_sha256: str
    expected_active_generation: int
    expected_active_pointer_sha256: str | None
    rollback_release_id: str | None
    validation_receipts: tuple[ValidationReceipt, ...]
    plan_sha256: str

    def as_mapping(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": self.schema_version,
            "activation_id": self.activation_id,
            "target": self.target,
            "created_at": self.created_at,
            "release_id": self.release_id,
            "release_manifest_sha256": self.release_manifest_sha256,
            "expected_active_generation": self.expected_active_generation,
            "expected_active_pointer_sha256": self.expected_active_pointer_sha256,
            "rollback_release_id": self.rollback_release_id,
            "validation_receipts": [
                {
                    "kind": receipt.kind,
                    "receipt_id": receipt.receipt_id,
                    "sha256": receipt.sha256,
                }
                for receipt in self.validation_receipts
            ],
            "plan_sha256": self.plan_sha256,
        }
        if self.schema_version == ACTIVATION_PLAN_SCHEMA:
            value["action"] = self.action
        return value


def _parse_main(blob: Mapping[str, Any]) -> MainBinding:
    _reject_unknown(
        blob,
        frozenset(
            {
                "pipeline_id",
                "runtime_profile",
                "generation",
                "state_sha256",
                "promotion_receipt_sha256",
                "promotion_plan_sha256",
            }
        ),
        "main",
    )
    generation = blob.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise ReleaseContractError("main.generation must be a non-negative integer")
    raw_receipt = blob.get("promotion_receipt_sha256")
    receipt = None if raw_receipt is None else _hash(
        raw_receipt, "main.promotion_receipt_sha256"
    )
    raw_plan = blob.get("promotion_plan_sha256")
    plan = None if raw_plan is None else _hash(
        raw_plan, "main.promotion_plan_sha256"
    )
    if generation > 0 and (receipt is None or plan is None):
        raise ReleaseContractError(
            "promoted MAIN generation requires receipt and plan SHA-256"
        )
    if generation == 0 and (receipt is not None or plan is not None):
        raise ReleaseContractError(
            "unpromoted MAIN generation cannot carry promotion evidence"
        )
    runtime_profile = _identifier(
        blob.get("runtime_profile"), "main.runtime_profile"
    )
    try:
        from lawrag.runtime.registry import validate_profile_id

        validate_profile_id(runtime_profile)
    except ValueError as exc:
        raise ReleaseContractError(str(exc)) from exc
    return MainBinding(
        pipeline_id=_identifier(blob.get("pipeline_id"), "main.pipeline_id"),
        runtime_profile=runtime_profile,
        generation=generation,
        state_sha256=_hash(blob.get("state_sha256"), "main.state_sha256"),
        promotion_receipt_sha256=receipt,
        promotion_plan_sha256=plan,
    )


def _parse_source_set(blob: Mapping[str, Any]) -> SourceSetBinding:
    _reject_unknown(
        blob,
        frozenset({
            "id", "generation_id", "sha256", "export_allowed",
            "lock_sha256", "lock_artifact_sha256",
            "materialization_sha256", "materialization_receipt_sha256",
            "catalog_sha256", "catalog_artifact_sha256",
        }),
        "source_set",
    )
    export_allowed = blob.get("export_allowed")
    if not isinstance(export_allowed, bool):
        raise ReleaseContractError("source_set.export_allowed must be boolean")
    proof_names = (
        "lock_sha256", "lock_artifact_sha256",
        "materialization_sha256", "materialization_receipt_sha256",
        "catalog_sha256", "catalog_artifact_sha256",
    )
    present = [blob.get(name) is not None for name in proof_names]
    if any(present) and not all(present):
        raise ReleaseContractError(
            "source_set serving proofs must be all present or all absent"
        )
    proofs = {
        name: (_hash(blob.get(name), f"source_set.{name}") if all(present) else None)
        for name in proof_names
    }
    return SourceSetBinding(
        source_set_id=_identifier(blob.get("id"), "source_set.id"),
        generation_id=_identifier(
            blob.get("generation_id"), "source_set.generation_id"
        ),
        sha256=_hash(blob.get("sha256"), "source_set.sha256"),
        export_allowed=export_allowed,
        lock_sha256=proofs["lock_sha256"],
        lock_artifact_sha256=proofs["lock_artifact_sha256"],
        materialization_sha256=proofs["materialization_sha256"],
        materialization_receipt_sha256=proofs[
            "materialization_receipt_sha256"
        ],
        catalog_sha256=proofs["catalog_sha256"],
        catalog_artifact_sha256=proofs["catalog_artifact_sha256"],
    )


def _parse_semantics(blob: Mapping[str, Any]) -> SemanticBinding:
    _reject_unknown(
        blob,
        frozenset(
            {
                "generation_id",
                "authority_generation",
                "content_sha256",
                "source_set_sha256",
                "runtime_wired",
            }
        ),
        "semantics",
    )
    runtime_wired = blob.get("runtime_wired")
    if runtime_wired is not True:
        raise ReleaseContractError("semantics.runtime_wired must be true")
    return SemanticBinding(
        generation_id=_identifier(
            blob.get("generation_id"), "semantics.generation_id"
        ),
        authority_generation=_identifier(
            blob.get("authority_generation"), "semantics.authority_generation"
        ),
        content_sha256=_hash(
            blob.get("content_sha256"), "semantics.content_sha256"
        ),
        source_set_sha256=_hash(
            blob.get("source_set_sha256"), "semantics.source_set_sha256"
        ),
        runtime_wired=True,
    )


def _parse_indexes(
    rows: object, *, source_set_sha256: str, semantic_generation: str
) -> tuple[IndexBinding, ...]:
    if not isinstance(rows, list) or not rows:
        raise ReleaseContractError("indexes must be a non-empty list")
    indexes: list[IndexBinding] = []
    seen: set[str] = set()
    for position, value in enumerate(rows):
        blob = _object(value, f"indexes[{position}]")
        _reject_unknown(
            blob,
            frozenset(
                {
                    "kind",
                    "artifact_id",
                    "artifact_sha256",
                    "source_set_sha256",
                    "semantic_generation",
                    "build_fingerprint",
                    "embedding_model_fingerprint",
                }
            ),
            f"indexes[{position}]",
        )
        kind = str(blob.get("kind") or "")
        if kind not in _INDEX_KINDS or kind in seen:
            raise ReleaseContractError(f"invalid or duplicate index kind: {kind!r}")
        seen.add(kind)
        bound_source = _hash(
            blob.get("source_set_sha256"),
            f"indexes[{position}].source_set_sha256",
        )
        bound_semantics = _identifier(
            blob.get("semantic_generation"),
            f"indexes[{position}].semantic_generation",
        )
        if bound_source != source_set_sha256:
            raise ReleaseContractError(f"{kind} index is bound to another source set")
        if bound_semantics != semantic_generation:
            raise ReleaseContractError(
                f"{kind} index is bound to another semantic generation"
            )
        raw_embedding = blob.get("embedding_model_fingerprint")
        embedding = None
        if raw_embedding is not None:
            embedding = _hash(
                raw_embedding,
                f"indexes[{position}].embedding_model_fingerprint",
            )
        if kind == "vector" and embedding is None:
            raise ReleaseContractError(
                "vector index requires embedding_model_fingerprint"
            )
        indexes.append(
            IndexBinding(
                kind=kind,
                artifact_id=_identifier(
                    blob.get("artifact_id"), f"indexes[{position}].artifact_id"
                ),
                artifact_sha256=_hash(
                    blob.get("artifact_sha256"),
                    f"indexes[{position}].artifact_sha256",
                ),
                source_set_sha256=bound_source,
                semantic_generation=bound_semantics,
                build_fingerprint=_hash(
                    blob.get("build_fingerprint"),
                    f"indexes[{position}].build_fingerprint",
                ),
                embedding_model_fingerprint=embedding,
            )
        )
    if "lexical" not in seen:
        raise ReleaseContractError("release requires a lexical index binding")
    return tuple(indexes)


def _parse_receipts(rows: object) -> tuple[ValidationReceipt, ...]:
    if not isinstance(rows, list):
        raise ReleaseContractError("validation_receipts must be a list")
    out: list[ValidationReceipt] = []
    seen: set[str] = set()
    for position, value in enumerate(rows):
        blob = _object(value, f"validation_receipts[{position}]")
        _reject_unknown(
            blob,
            frozenset({"kind", "receipt_id", "sha256"}),
            f"validation_receipts[{position}]",
        )
        kind = str(blob.get("kind") or "")
        if kind not in _RECEIPT_KINDS or kind in seen:
            raise ReleaseContractError(
                f"invalid or duplicate validation receipt kind: {kind!r}"
            )
        seen.add(kind)
        out.append(
            ValidationReceipt(
                kind=kind,
                receipt_id=_identifier(
                    blob.get("receipt_id"),
                    f"validation_receipts[{position}].receipt_id",
                ),
                sha256=_hash(
                    blob.get("sha256"), f"validation_receipts[{position}].sha256"
                ),
            )
        )
    missing = sorted(_RECEIPT_KINDS - seen)
    if missing:
        raise ReleaseContractError(
            "activation plan is missing validation receipts: " + ", ".join(missing)
        )
    return tuple(out)


def release_from_mapping(blob: Mapping[str, Any]) -> ReleaseManifest:
    if blob.get("schema_version") != SCHEMA_VERSION:
        raise ReleaseContractError(
            f"unsupported release schema: {blob.get('schema_version')!r}"
        )
    _reject_unknown(
        blob,
        frozenset(
            {
                "schema_version",
                "release_id",
                "target",
                "layout_version",
                "created_at",
                "code",
                "main",
                "source_set",
                "semantics",
                "indexes",
                "manifest_sha256",
            }
        ),
        "release",
    )
    target = str(blob.get("target") or "")
    if target not in _TARGETS:
        raise ReleaseContractError(f"invalid release target: {target!r}")
    layout_version = str(blob.get("layout_version") or "")
    if layout_version not in _LAYOUTS:
        raise ReleaseContractError(f"invalid layout_version: {layout_version!r}")
    created_at = _timestamp(blob.get("created_at"), "release created_at")

    code = _object(blob.get("code"), "code")
    _reject_unknown(code, frozenset({"revision", "package_sha256"}), "code")
    main = _parse_main(_object(blob.get("main"), "main"))
    source_set = _parse_source_set(_object(blob.get("source_set"), "source_set"))
    semantics = _parse_semantics(_object(blob.get("semantics"), "semantics"))
    if semantics.source_set_sha256 != source_set.sha256:
        raise ReleaseContractError("semantics is bound to another source set")
    indexes = _parse_indexes(
        blob.get("indexes"),
        source_set_sha256=source_set.sha256,
        semantic_generation=semantics.generation_id,
    )
    normalized = dict(blob)
    normalized.pop("manifest_sha256", None)
    manifest_sha256 = _digest(normalized)
    declared = blob.get("manifest_sha256")
    if declared is not None and declared != manifest_sha256:
        raise ReleaseContractError("release manifest_sha256 mismatch")
    code_revision = str(code.get("revision") or "")
    if not _GIT_REVISION.fullmatch(code_revision):
        raise ReleaseContractError("code.revision must be a full Git object ID")
    return ReleaseManifest(
        release_id=_identifier(blob.get("release_id"), "release_id"),
        target=target,
        layout_version=layout_version,
        created_at=created_at,
        code_revision=code_revision,
        code_package_sha256=_hash(
            code.get("package_sha256"), "code.package_sha256"
        ),
        main=main,
        source_set=source_set,
        semantics=semantics,
        indexes=indexes,
        manifest_sha256=manifest_sha256,
    )


def validate_release_for_source_set(
    release: ReleaseManifest, view: UnifiedCorpusView
) -> None:
    """Ensure the selected multi-package view is exactly the release input."""

    mismatches: list[str] = []
    if release.source_set.source_set_id != view.source_set_id:
        mismatches.append("id")
    if release.source_set.generation_id != view.generation_id:
        mismatches.append("generation")
    if release.source_set.sha256 != view.source_set_sha256:
        mismatches.append("sha256")
    if release.source_set.export_allowed != view.export_allowed:
        mismatches.append("export_allowed")
    if mismatches:
        raise ReleaseContractError(
            "release/source-set mismatch: " + ", ".join(mismatches)
        )


def validation_receipt_map(
    receipts: Iterable[ValidationReceipt],
) -> dict[str, str]:
    return {receipt.kind: receipt.sha256 for receipt in receipts}


def activation_plan_from_mapping(blob: Mapping[str, Any]) -> ReleaseActivationPlan:
    schema_version = str(blob.get("schema_version") or "")
    if schema_version not in {
        LEGACY_ACTIVATION_PLAN_SCHEMA,
        ACTIVATION_PLAN_SCHEMA,
    }:
        raise ReleaseContractError(
            f"unsupported activation plan schema: {blob.get('schema_version')!r}"
        )
    allowed_fields = {
        "schema_version",
        "activation_id",
        "target",
        "created_at",
        "release_id",
        "release_manifest_sha256",
        "expected_active_generation",
        "expected_active_pointer_sha256",
        "rollback_release_id",
        "validation_receipts",
        "plan_sha256",
    }
    if schema_version == ACTIVATION_PLAN_SCHEMA:
        allowed_fields.add("action")
    _reject_unknown(
        blob,
        frozenset(allowed_fields),
        "activation plan",
    )
    if schema_version == LEGACY_ACTIVATION_PLAN_SCHEMA:
        action = "activate"
    else:
        action = str(blob.get("action") or "")
        if action not in {"activate", "rollback"}:
            raise ReleaseContractError(
                f"invalid activation plan action: {action!r}"
            )
    target = str(blob.get("target") or "")
    if target not in _TARGETS:
        raise ReleaseContractError(f"invalid activation target: {target!r}")
    expected_generation = blob.get("expected_active_generation")
    if (
        isinstance(expected_generation, bool)
        or not isinstance(expected_generation, int)
        or expected_generation < 0
    ):
        raise ReleaseContractError(
            "expected_active_generation must be a non-negative integer"
        )
    raw_pointer = blob.get("expected_active_pointer_sha256")
    pointer_hash = None if raw_pointer is None else _hash(
        raw_pointer, "expected_active_pointer_sha256"
    )
    raw_rollback = blob.get("rollback_release_id")
    rollback_release_id = None if raw_rollback is None else _identifier(
        raw_rollback, "rollback_release_id"
    )
    created_at = _timestamp(blob.get("created_at"), "activation plan created_at")
    receipts = _parse_receipts(blob.get("validation_receipts"))
    normalized = dict(blob)
    normalized.pop("plan_sha256", None)
    plan_sha256 = _digest(normalized)
    declared = blob.get("plan_sha256")
    if declared is not None and declared != plan_sha256:
        raise ReleaseContractError("activation plan_sha256 mismatch")
    return ReleaseActivationPlan(
        schema_version=schema_version,
        action=action,
        activation_id=_identifier(blob.get("activation_id"), "activation_id"),
        target=target,
        created_at=created_at,
        release_id=_identifier(blob.get("release_id"), "release_id"),
        release_manifest_sha256=_hash(
            blob.get("release_manifest_sha256"), "release_manifest_sha256"
        ),
        expected_active_generation=expected_generation,
        expected_active_pointer_sha256=pointer_hash,
        rollback_release_id=rollback_release_id,
        validation_receipts=receipts,
        plan_sha256=plan_sha256,
    )


def validate_activation_plan(
    plan: ReleaseActivationPlan,
    release: ReleaseManifest,
    *,
    current_pointer: Mapping[str, Any] | None,
) -> None:
    """Validate compare-and-swap inputs without mutating the active pointer."""

    mismatches: list[str] = []
    if plan.release_id != release.release_id:
        mismatches.append("release_id")
    if plan.release_manifest_sha256 != release.manifest_sha256:
        mismatches.append("release_manifest_sha256")
    if plan.target != release.target:
        mismatches.append("target")
    if current_pointer is None:
        actual_generation = 0
        actual_hash = None
        actual_release_id = None
    else:
        actual_generation = current_pointer.get("generation")
        if (
            isinstance(actual_generation, bool)
            or not isinstance(actual_generation, int)
            or actual_generation < 0
        ):
            raise ReleaseContractError(
                "current active pointer generation must be a non-negative integer"
            )
        actual_hash = _digest(current_pointer)
        raw_release_id = current_pointer.get("release_id")
        actual_release_id = (
            None
            if raw_release_id is None
            else _identifier(raw_release_id, "current_pointer.release_id")
        )
    if plan.expected_active_generation != actual_generation:
        mismatches.append("expected_active_generation")
    if plan.expected_active_pointer_sha256 != actual_hash:
        mismatches.append("expected_active_pointer_sha256")
    if plan.rollback_release_id != actual_release_id:
        mismatches.append("rollback_release_id")
    if mismatches:
        raise ReleaseContractError(
            "stale or incompatible activation plan: " + ", ".join(mismatches)
        )


def validate_release_bindings(
    release: ReleaseManifest,
    *,
    view: UnifiedCorpusView,
    main_state: Mapping[str, Any],
    main_promotion_receipt_sha256: str | None,
    main_promotion_plan_sha256: str | None,
    semantic_snapshot: Mapping[str, Any],
    index_snapshots: Mapping[str, Mapping[str, Any]],
) -> None:
    """Cross-check a candidate against the exact installed runtime snapshots."""

    validate_release_for_source_set(release, view)
    mismatches: list[str] = []
    # The same validator used by sealed bootstrap protects the build path.
    # In particular, generation zero has no transition proof and therefore
    # must be the one canonical default state byte-for-byte semantically.
    from lawrag.core.rag.main_promotion import validate_state as validate_main_state

    main_state_errors = validate_main_state(main_state)
    mismatches.extend(f"main.state:{item}" for item in main_state_errors)
    if release.main.pipeline_id != main_state.get("pipeline_id"):
        mismatches.append("main.pipeline_id")
    if release.main.runtime_profile != main_state.get("runtime_profile"):
        mismatches.append("main.runtime_profile")
    if release.main.generation != main_state.get("generation"):
        mismatches.append("main.generation")
    if release.main.state_sha256 != _digest(main_state):
        mismatches.append("main.state_sha256")
    actual_receipt = (
        None
        if main_promotion_receipt_sha256 is None
        else _hash(
            main_promotion_receipt_sha256, "main_promotion_receipt_sha256"
        )
    )
    if release.main.promotion_receipt_sha256 != actual_receipt:
        mismatches.append("main.promotion_receipt_sha256")
    actual_plan = (
        None
        if main_promotion_plan_sha256 is None
        else _hash(main_promotion_plan_sha256, "main_promotion_plan_sha256")
    )
    if release.main.promotion_plan_sha256 != actual_plan:
        mismatches.append("main.promotion_plan_sha256")

    semantic_fields = {
        "generation_id": release.semantics.generation_id,
        "authority_generation": release.semantics.authority_generation,
        "content_sha256": release.semantics.content_sha256,
        "source_set_sha256": release.semantics.source_set_sha256,
        "runtime_wired": True,
    }
    for field, expected in semantic_fields.items():
        if semantic_snapshot.get(field) != expected:
            mismatches.append(f"semantics.{field}")

    if set(index_snapshots) != {index.kind for index in release.indexes}:
        mismatches.append("indexes.kinds")
    else:
        for index in release.indexes:
            snapshot = index_snapshots[index.kind]
            expected = {
                "artifact_id": index.artifact_id,
                "artifact_sha256": index.artifact_sha256,
                "source_set_sha256": index.source_set_sha256,
                "semantic_generation": index.semantic_generation,
                "build_fingerprint": index.build_fingerprint,
                "embedding_model_fingerprint": index.embedding_model_fingerprint,
            }
            for field, value in expected.items():
                if snapshot.get(field) != value:
                    mismatches.append(f"indexes.{index.kind}.{field}")
    if mismatches:
        raise ReleaseContractError(
            "release/runtime binding mismatch: " + ", ".join(mismatches)
        )


# ---------------------------------------------------------------------------
# Deterministic index identity helpers


def source_set_binding_fingerprint(binding: SourceSetBinding) -> str:
    """Hash every SourceSet field that can change runtime selection or access."""

    value: dict[str, Any] = {
        "schema_version": "source-set-binding-fingerprint-v1",
        "source_set_id": binding.source_set_id,
        "generation_id": binding.generation_id,
        "source_set_sha256": binding.sha256,
        "export_allowed": binding.export_allowed,
    }
    if binding.lock_sha256 is not None:
        value["schema_version"] = "source-set-binding-fingerprint-v2"
        value.update({
            "lock_sha256": binding.lock_sha256,
            "lock_artifact_sha256": binding.lock_artifact_sha256,
            "materialization_sha256": binding.materialization_sha256,
            "materialization_receipt_sha256": (
                binding.materialization_receipt_sha256
            ),
            "catalog_sha256": binding.catalog_sha256,
            "catalog_artifact_sha256": binding.catalog_artifact_sha256,
        })
    return _digest(value)


def semantic_binding_fingerprint(binding: SemanticBinding) -> str:
    """Hash the semantic generation and the exact source/authority it compiles."""

    return _digest(
        {
            "schema_version": "semantic-binding-fingerprint-v1",
            "generation_id": binding.generation_id,
            "authority_generation": binding.authority_generation,
            "content_sha256": binding.content_sha256,
            "source_set_sha256": binding.source_set_sha256,
            "runtime_wired": binding.runtime_wired,
        }
    )


def embedding_model_fingerprint(
    *,
    backend: str,
    model_id: str,
    model_revision: str,
    model_artifact_sha256: str,
    dimensions: int,
    normalized: bool,
    document_profile: str,
    query_profile: str,
) -> str:
    """Create a stable encoder-space identity without including credentials.

    ``model_revision`` must identify the deployed model artifact, not merely a
    mutable serving alias.  Query and document preprocessing are deliberately
    separate because equal model weights do not make differently prompted
    vectors compatible.
    """

    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions <= 0:
        raise ReleaseContractError("embedding dimensions must be a positive integer")
    if not isinstance(normalized, bool):
        raise ReleaseContractError("embedding normalized must be boolean")
    core = {
        "schema_version": "embedding-model-fingerprint-v2",
        "backend": _required_text(backend, "embedding.backend"),
        "model_id": _required_text(model_id, "embedding.model_id"),
        "model_revision": _required_text(
            model_revision, "embedding.model_revision"
        ),
        "model_artifact_sha256": _hash(
            model_artifact_sha256, "embedding.model_artifact_sha256"
        ),
        "dimensions": dimensions,
        "normalized": normalized,
        "document_profile": _required_text(
            document_profile, "embedding.document_profile"
        ),
        "query_profile": _required_text(query_profile, "embedding.query_profile"),
    }
    return _digest(core)


def _artifact_hash_rows(
    values: Mapping[str, str] | Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    rows = list(values.items() if isinstance(values, Mapping) else values)
    normalized: dict[str, str] = {}
    for raw_id, raw_sha256 in rows:
        artifact_id = _required_text(raw_id, "index input artifact ID")
        if artifact_id in normalized:
            raise ReleaseContractError(
                f"duplicate index input artifact ID: {artifact_id}"
            )
        normalized[artifact_id] = _hash(
            raw_sha256, f"index input {artifact_id} sha256"
        )
    if not normalized:
        raise ReleaseContractError("index build requires input artifact hashes")
    return tuple(sorted(normalized.items()))


@dataclass(frozen=True)
class IndexBuildFingerprint:
    kind: str
    source_set_sha256: str
    source_set_fingerprint: str
    semantic_generation: str
    semantic_fingerprint: str
    authority_generation: str
    builder_id: str
    builder_revision: str
    input_artifacts: tuple[tuple[str, str], ...]
    configuration_sha256: str
    embedding_model_fingerprint: str | None
    build_fingerprint: str

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": INDEX_BUILD_FINGERPRINT_SCHEMA,
            "kind": self.kind,
            "source_set_sha256": self.source_set_sha256,
            "source_set_fingerprint": self.source_set_fingerprint,
            "semantic_generation": self.semantic_generation,
            "semantic_fingerprint": self.semantic_fingerprint,
            "authority_generation": self.authority_generation,
            "builder_id": self.builder_id,
            "builder_revision": self.builder_revision,
            "input_artifacts": [
                {"artifact_id": artifact_id, "sha256": sha256}
                for artifact_id, sha256 in self.input_artifacts
            ],
            "configuration_sha256": self.configuration_sha256,
            "embedding_model_fingerprint": self.embedding_model_fingerprint,
            "build_fingerprint": self.build_fingerprint,
        }


def create_index_build_fingerprint(
    *,
    kind: str,
    source_set: SourceSetBinding,
    semantics: SemanticBinding,
    builder_id: str,
    builder_revision: str,
    input_artifacts: Mapping[str, str] | Iterable[tuple[str, str]],
    configuration: Mapping[str, Any],
    model_fingerprint: str | None = None,
) -> IndexBuildFingerprint:
    """Bind an index build to all inputs that define its search space."""

    if kind not in _INDEX_KINDS:
        raise ReleaseContractError(f"invalid index kind: {kind!r}")
    if semantics.source_set_sha256 != source_set.sha256:
        raise ReleaseContractError("semantics is bound to another source set")
    if not isinstance(configuration, Mapping):
        raise ReleaseContractError("index build configuration must be an object")
    revision = str(builder_revision or "")
    if not _GIT_REVISION.fullmatch(revision):
        raise ReleaseContractError(
            "index builder_revision must be a full Git object ID"
        )
    embedding = None
    if model_fingerprint is not None:
        embedding = _hash(model_fingerprint, "embedding_model_fingerprint")
    if kind == "vector" and embedding is None:
        raise ReleaseContractError(
            "vector index build requires embedding_model_fingerprint"
        )
    if kind == "lexical" and embedding is not None:
        raise ReleaseContractError(
            "lexical index build cannot carry embedding_model_fingerprint"
        )
    rows = _artifact_hash_rows(input_artifacts)
    config_hash = _digest(
        {
            "schema_version": "index-build-configuration-v1",
            "configuration": dict(configuration),
        }
    )
    core = {
        "schema_version": INDEX_BUILD_FINGERPRINT_SCHEMA,
        "kind": kind,
        "source_set_sha256": source_set.sha256,
        "source_set_fingerprint": source_set_binding_fingerprint(source_set),
        "semantic_generation": semantics.generation_id,
        "semantic_fingerprint": semantic_binding_fingerprint(semantics),
        "authority_generation": semantics.authority_generation,
        "builder_id": _identifier(builder_id, "index builder_id"),
        "builder_revision": revision,
        "input_artifacts": [
            {"artifact_id": artifact_id, "sha256": sha256}
            for artifact_id, sha256 in rows
        ],
        "configuration_sha256": config_hash,
        "embedding_model_fingerprint": embedding,
    }
    return IndexBuildFingerprint(
        kind=kind,
        source_set_sha256=source_set.sha256,
        source_set_fingerprint=core["source_set_fingerprint"],
        semantic_generation=semantics.generation_id,
        semantic_fingerprint=core["semantic_fingerprint"],
        authority_generation=semantics.authority_generation,
        builder_id=core["builder_id"],
        builder_revision=revision,
        input_artifacts=rows,
        configuration_sha256=config_hash,
        embedding_model_fingerprint=embedding,
        build_fingerprint=_digest(core),
    )


def index_build_fingerprint_from_mapping(
    blob: Mapping[str, Any],
) -> IndexBuildFingerprint:
    _reject_unknown(
        blob,
        frozenset(
            {
                "schema_version",
                "kind",
                "source_set_sha256",
                "source_set_fingerprint",
                "semantic_generation",
                "semantic_fingerprint",
                "authority_generation",
                "builder_id",
                "builder_revision",
                "input_artifacts",
                "configuration_sha256",
                "embedding_model_fingerprint",
                "build_fingerprint",
            }
        ),
        "index build fingerprint",
    )
    if blob.get("schema_version") != INDEX_BUILD_FINGERPRINT_SCHEMA:
        raise ReleaseContractError("unsupported index build fingerprint schema")
    kind = str(blob.get("kind") or "")
    if kind not in _INDEX_KINDS:
        raise ReleaseContractError(f"invalid index kind: {kind!r}")
    raw_inputs = blob.get("input_artifacts")
    if not isinstance(raw_inputs, list):
        raise ReleaseContractError("index input_artifacts must be a list")
    pairs: list[tuple[str, str]] = []
    for position, value in enumerate(raw_inputs):
        row = _object(value, f"input_artifacts[{position}]")
        _reject_unknown(
            row,
            frozenset({"artifact_id", "sha256"}),
            f"input_artifacts[{position}]",
        )
        pairs.append(
            (
                _required_text(
                    row.get("artifact_id"),
                    f"input_artifacts[{position}].artifact_id",
                ),
                _hash(row.get("sha256"), f"input_artifacts[{position}].sha256"),
            )
        )
    inputs = _artifact_hash_rows(pairs)
    canonical_inputs = [
        {"artifact_id": artifact_id, "sha256": sha256}
        for artifact_id, sha256 in inputs
    ]
    if raw_inputs != canonical_inputs:
        raise ReleaseContractError(
            "index input_artifacts must be unique and sorted by artifact_id"
        )
    raw_model = blob.get("embedding_model_fingerprint")
    model = None if raw_model is None else _hash(
        raw_model, "embedding_model_fingerprint"
    )
    if kind == "vector" and model is None:
        raise ReleaseContractError(
            "vector index build requires embedding_model_fingerprint"
        )
    if kind == "lexical" and model is not None:
        raise ReleaseContractError(
            "lexical index build cannot carry embedding_model_fingerprint"
        )
    revision = str(blob.get("builder_revision") or "")
    if not _GIT_REVISION.fullmatch(revision):
        raise ReleaseContractError(
            "index builder_revision must be a full Git object ID"
        )
    normalized = dict(blob)
    declared = _hash(normalized.pop("build_fingerprint", None), "build_fingerprint")
    actual = _digest(normalized)
    if actual != declared:
        raise ReleaseContractError("index build_fingerprint mismatch")
    return IndexBuildFingerprint(
        kind=kind,
        source_set_sha256=_hash(
            blob.get("source_set_sha256"), "source_set_sha256"
        ),
        source_set_fingerprint=_hash(
            blob.get("source_set_fingerprint"), "source_set_fingerprint"
        ),
        semantic_generation=_identifier(
            blob.get("semantic_generation"), "semantic_generation"
        ),
        semantic_fingerprint=_hash(
            blob.get("semantic_fingerprint"), "semantic_fingerprint"
        ),
        authority_generation=_identifier(
            blob.get("authority_generation"), "authority_generation"
        ),
        builder_id=_identifier(blob.get("builder_id"), "builder_id"),
        builder_revision=revision,
        input_artifacts=inputs,
        configuration_sha256=_hash(
            blob.get("configuration_sha256"), "configuration_sha256"
        ),
        embedding_model_fingerprint=model,
        build_fingerprint=declared,
    )


def validate_index_build_fingerprint(
    index: IndexBinding,
    fingerprint: IndexBuildFingerprint | Mapping[str, Any],
    *,
    source_set: SourceSetBinding,
    semantics: SemanticBinding,
    runtime_model_fingerprint: str | None = None,
) -> None:
    """Reject reuse across source, semantic, authority, builder, or model space."""

    record = index_build_fingerprint_from_mapping(
        fingerprint if isinstance(fingerprint, Mapping) else fingerprint.receipt()
    )
    mismatches: list[str] = []
    if record.kind != index.kind:
        mismatches.append("kind")
    if record.source_set_sha256 != source_set.sha256:
        mismatches.append("source_set_sha256")
    if record.source_set_fingerprint != source_set_binding_fingerprint(source_set):
        mismatches.append("source_set_fingerprint")
    if record.semantic_generation != semantics.generation_id:
        mismatches.append("semantic_generation")
    if record.semantic_fingerprint != semantic_binding_fingerprint(semantics):
        mismatches.append("semantic_fingerprint")
    if record.authority_generation != semantics.authority_generation:
        mismatches.append("authority_generation")
    if record.build_fingerprint != index.build_fingerprint:
        mismatches.append("build_fingerprint")
    if index.source_set_sha256 != source_set.sha256:
        mismatches.append("index.source_set_sha256")
    if index.semantic_generation != semantics.generation_id:
        mismatches.append("index.semantic_generation")
    if index.embedding_model_fingerprint != record.embedding_model_fingerprint:
        mismatches.append("embedding_model_fingerprint")
    if runtime_model_fingerprint is not None:
        runtime_model = _hash(
            runtime_model_fingerprint, "runtime_model_fingerprint"
        )
        if runtime_model != record.embedding_model_fingerprint:
            mismatches.append("runtime_model_fingerprint")
    elif index.kind == "vector":
        raise ReleaseContractError(
            "vector index validation requires runtime_model_fingerprint"
        )
    if mismatches:
        raise ReleaseContractError(
            "index fingerprint mismatch: " + ", ".join(mismatches)
        )


# ---------------------------------------------------------------------------
# Runtime materialization binding


def _safe_runtime_relative(value: object, field: str) -> str:
    raw = str(value or "")
    text = raw.strip()
    path = PurePosixPath(text)
    if (
        not text
        or raw != text
        or "\x00" in text
        or "\\" in text
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != text
    ):
        raise ReleaseContractError(f"{field} must be a canonical relative path")
    return path.as_posix()


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _stable_file_sha256(path: Path) -> tuple[str, int, str]:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ReleaseContractError(f"cannot stat runtime file {path}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ReleaseContractError(f"runtime file is not regular: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReleaseContractError(f"cannot safely open runtime file {path}: {exc}") from exc
    digest = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if _file_identity(before) != _file_identity(opened):
            raise ReleaseContractError(f"runtime file changed before hashing: {path}")
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(descriptor)
        if _file_identity(opened) != _file_identity(after):
            raise ReleaseContractError(f"runtime file changed while hashing: {path}")
    finally:
        os.close(descriptor)
    return digest.hexdigest(), opened.st_size, f"{stat.S_IMODE(opened.st_mode):04o}"


def _runtime_tree_rows(root: Path, current: Path, relative: str) -> list[dict[str, Any]]:
    before = current.lstat()
    if stat.S_ISLNK(before.st_mode):
        raise ReleaseContractError(f"runtime tree contains a symlink: {current}")
    mode = f"{stat.S_IMODE(before.st_mode):04o}"
    if stat.S_ISREG(before.st_mode):
        sha256, size, stable_mode = _stable_file_sha256(current)
        return [{
            "path": relative,
            "kind": "file",
            "mode": stable_mode,
            "bytes": size,
            "sha256": sha256,
        }]
    if not stat.S_ISDIR(before.st_mode):
        raise ReleaseContractError(f"runtime tree contains a special file: {current}")
    rows: list[dict[str, Any]] = [{
        "path": relative,
        "kind": "directory",
        "mode": mode,
    }]
    for child in sorted(current.iterdir(), key=lambda value: os.fsencode(value.name)):
        child_relative = child.name if relative == "." else f"{relative}/{child.name}"
        rows.extend(_runtime_tree_rows(root, child, child_relative))
    after = current.lstat()
    if _file_identity(before) != _file_identity(after):
        raise ReleaseContractError(f"runtime directory changed while hashing: {current}")
    return rows


def _runtime_path_fingerprint(path: Path) -> tuple[str, str]:
    if path.is_symlink() or not path.exists():
        raise ReleaseContractError(f"runtime path is missing or symbolic: {path}")
    info = path.lstat()
    kind = "file" if stat.S_ISREG(info.st_mode) else "directory" if stat.S_ISDIR(info.st_mode) else ""
    if not kind:
        raise ReleaseContractError(f"runtime path is not file/directory: {path}")
    rows = _runtime_tree_rows(path, path, ".")
    return kind, _digest({
        "schema_version": "runtime-path-fingerprint-v1",
        "kind": kind,
        "rows": rows,
    })


def _runtime_content_rows(current: Path, relative: str) -> list[dict[str, Any]]:
    """Hash artifact bytes and names without making chmod part of identity."""

    before = current.lstat()
    if stat.S_ISLNK(before.st_mode):
        raise ReleaseContractError(f"runtime artifact contains a symlink: {current}")
    if stat.S_ISREG(before.st_mode):
        sha256, size, _ = _stable_file_sha256(current)
        return [{
            "path": relative,
            "kind": "file",
            "bytes": size,
            "sha256": sha256,
        }]
    if not stat.S_ISDIR(before.st_mode):
        raise ReleaseContractError(
            f"runtime artifact contains a special file: {current}"
        )
    rows: list[dict[str, Any]] = [{"path": relative, "kind": "directory"}]
    for child in sorted(current.iterdir(), key=lambda value: os.fsencode(value.name)):
        child_relative = child.name if relative == "." else f"{relative}/{child.name}"
        rows.extend(_runtime_content_rows(child, child_relative))
    after = current.lstat()
    if _file_identity(before) != _file_identity(after):
        raise ReleaseContractError(
            f"runtime artifact directory changed while hashing: {current}"
        )
    return rows


def _runtime_artifact_content(path: Path) -> tuple[str, str]:
    if path.is_symlink() or not path.exists():
        raise ReleaseContractError(f"runtime artifact is missing or symbolic: {path}")
    info = path.lstat()
    if stat.S_ISREG(info.st_mode):
        sha256, _, _ = _stable_file_sha256(path)
        return "file", sha256
    if not stat.S_ISDIR(info.st_mode):
        raise ReleaseContractError(f"runtime artifact is not file/directory: {path}")
    return "directory", _digest({
        "schema_version": "runtime-artifact-content-v1",
        "kind": "directory",
        "rows": _runtime_content_rows(path, "."),
    })


def runtime_artifact_sha256(path: str | os.PathLike[str]) -> str:
    """Return the digest used by physical release-artifact proofs.

    A regular file is hashed byte-for-byte.  A directory hashes every relative
    name, object kind, and regular-file byte digest, but deliberately excludes
    modes so the same declared content can be sealed read-only at install time.
    Symlinks and special files are never valid release artifacts.
    """

    _, sha256 = _runtime_artifact_content(Path(path).expanduser().absolute())
    return sha256


def _runtime_tree_paths(current: Path) -> list[tuple[Path, os.stat_result]]:
    info = current.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise ReleaseContractError(f"runtime tree contains a symlink: {current}")
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise ReleaseContractError(f"runtime tree contains a special file: {current}")
    rows = [(current, info)]
    if stat.S_ISDIR(info.st_mode):
        for child in sorted(current.iterdir(), key=lambda value: os.fsencode(value.name)):
            rows.extend(_runtime_tree_paths(child))
    return rows


def _fsync_directory_path(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise ReleaseContractError(f"runtime object is not a directory: {path}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _seal_runtime_tree(root: Path) -> None:
    """Durably remove write bits from the complete materialized runtime tree."""

    rows = _runtime_tree_paths(root)
    for path, before in rows:
        if not stat.S_ISREG(before.st_mode):
            continue
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if _file_identity(before) != _file_identity(opened):
                raise ReleaseContractError(
                    f"runtime file changed before sealing: {path}"
                )
            os.fsync(descriptor)
            os.fchmod(
                descriptor,
                (stat.S_IMODE(opened.st_mode) & ~0o222) | stat.S_IRUSR,
            )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    for path, before in reversed(rows):
        if not stat.S_ISDIR(before.st_mode):
            continue
        current = path.lstat()
        if stat.S_ISLNK(current.st_mode) or not stat.S_ISDIR(current.st_mode):
            raise ReleaseContractError(f"runtime directory changed before sealing: {path}")
        os.chmod(
            path,
            (stat.S_IMODE(current.st_mode) & ~0o222) | stat.S_IRUSR | stat.S_IXUSR,
            follow_symlinks=False,
        )
        _fsync_directory_path(path)


def _assert_runtime_tree_sealed(root: Path) -> None:
    for path, info in _runtime_tree_paths(root):
        if stat.S_IMODE(info.st_mode) & 0o222:
            raise ReleaseContractError(f"runtime tree object remains writable: {path}")


def _resolve_runtime_member(root: Path, relative: str, *, field: str) -> Path:
    safe = _safe_runtime_relative(relative, field)
    resolved_root = root.resolve()
    current = resolved_root
    for part in PurePosixPath(safe).parts:
        current = current / part
        if current.is_symlink():
            raise ReleaseContractError(f"{field} contains a symlink")
    resolved = current.resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ReleaseContractError(f"{field} escapes runtime root") from exc
    if not resolved.exists():
        raise ReleaseContractError(f"missing {field}: {safe}")
    return resolved


@dataclass(frozen=True)
class RuntimePathBinding:
    key: str
    path: str
    kind: str
    fingerprint_sha256: str

    def as_mapping(self) -> dict[str, str]:
        return {
            "path": self.path,
            "kind": self.kind,
            "fingerprint_sha256": self.fingerprint_sha256,
        }


@dataclass(frozen=True)
class RuntimeArtifactProof:
    key: str
    path: str
    kind: str
    content_sha256: str
    build_fingerprint: str | None
    embedding_model_fingerprint: str | None

    def as_mapping(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "content_sha256": self.content_sha256,
            "build_fingerprint": self.build_fingerprint,
            "embedding_model_fingerprint": self.embedding_model_fingerprint,
        }


def _runtime_artifact_expectations(
    release: ReleaseManifest,
) -> dict[str, tuple[str, str | None, str | None]]:
    expected: dict[str, tuple[str, str | None, str | None]] = {
        "main.state": (release.main.state_sha256, None, None),
        "semantics.content": (release.semantics.content_sha256, None, None),
    }
    if release.main.generation > 0:
        # The historical field name is retained, but its digest binds the full
        # canonical-root-to-tip transition-chain artifact.  A latest receipt
        # alone cannot prove that an intermediate MAIN state was authorized.
        # Generation zero deliberately has no transition artifact.
        receipt_sha256 = release.main.promotion_receipt_sha256
        # Defensive for direct dataclass construction outside ``_parse_main``.
        if receipt_sha256 is None:
            raise ReleaseContractError(
                "promoted MAIN runtime requires transition chain bytes"
            )
        expected["main.promotion_receipt"] = (receipt_sha256, None, None)
        plan_sha256 = release.main.promotion_plan_sha256
        if plan_sha256 is None:
            raise ReleaseContractError(
                "promoted MAIN runtime requires promotion plan bytes"
            )
        expected["main.promotion_plan"] = (plan_sha256, None, None)
    if release.source_set.lock_sha256 is not None:
        expected.update({
            "source_set.lock": (
                str(release.source_set.lock_artifact_sha256), None, None
            ),
            "source_set.materialization": (
                str(release.source_set.materialization_sha256), None, None
            ),
            "source_set.catalog": (
                str(release.source_set.catalog_artifact_sha256), None, None
            ),
        })
    else:
        # The legacy release contract represented a source set as one opaque
        # content artifact.  A proof-bound SourceSet has a semantic composition
        # hash that is deliberately independent from any one file, so its lock,
        # materialization and catalog proofs replace the opaque artifact.
        expected["source_set.content"] = (release.source_set.sha256, None, None)
    for index in release.indexes:
        expected[f"index.{index.kind}"] = (
            index.artifact_sha256,
            index.build_fingerprint,
            index.embedding_model_fingerprint,
        )
    return expected


@dataclass(frozen=True)
class RuntimeBindingDocument:
    release_id: str
    release_manifest_sha256: str
    source_set_sha256: str
    created_at: str
    sealed: bool
    runtime_root_fingerprint_sha256: str
    code_package_kind: str
    code_package_sha256: str
    artifacts: tuple[RuntimeArtifactProof, ...]
    paths: tuple[RuntimePathBinding, ...]
    binding_sha256: str

    def as_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": RUNTIME_BINDING_SCHEMA,
            "release_id": self.release_id,
            "release_manifest_sha256": self.release_manifest_sha256,
            "source_set_sha256": self.source_set_sha256,
            "created_at": self.created_at,
            "sealed": self.sealed,
            "runtime_root_fingerprint_sha256": self.runtime_root_fingerprint_sha256,
            "code_package": {
                "kind": self.code_package_kind,
                "content_sha256": self.code_package_sha256,
            },
            "artifacts": {
                row.key: row.as_mapping() for row in self.artifacts
            },
            "paths": {row.key: row.as_mapping() for row in self.paths},
            "binding_sha256": self.binding_sha256,
        }

    def provenance_result(self) -> dict[str, Any]:
        """The only accepted deterministic result for a provenance receipt."""

        return {
            "schema_version": RUNTIME_PROVENANCE_RESULT_SCHEMA,
            "release_id": self.release_id,
            "release_manifest_sha256": self.release_manifest_sha256,
            "runtime_binding_sha256": self.binding_sha256,
            "runtime_root_fingerprint_sha256": self.runtime_root_fingerprint_sha256,
            "code_package_sha256": self.code_package_sha256,
            "artifacts": {
                row.key: row.content_sha256 for row in self.artifacts
            },
        }

    def provenance_details(self) -> dict[str, str]:
        return {
            "runtime_binding_sha256": self.binding_sha256,
            "provenance_result_sha256": _digest(self.provenance_result()),
        }

    def resolved_paths(self, runtime_root: Path) -> dict[str, str]:
        return {
            row.key: str(
                _resolve_runtime_member(
                    runtime_root, row.path, field=f"runtime path {row.key}"
                )
            )
            for row in self.paths
        }

    def resolved_artifacts(self, runtime_root: Path) -> dict[str, str]:
        """Resolve release-bound artifact proofs below the sealed runtime root."""

        return {
            row.key: str(
                _resolve_runtime_member(
                    runtime_root, row.path, field=f"runtime artifact {row.key}"
                )
            )
            for row in self.artifacts
        }


def create_runtime_binding(
    *,
    release: ReleaseManifest,
    runtime_root: str | os.PathLike[str],
    paths: Mapping[str, str],
    artifact_paths: Mapping[str, str],
    code_package_root: str | os.PathLike[str],
    created_at: str,
) -> RuntimeBindingDocument:
    root = Path(runtime_root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ReleaseContractError("runtime root must be a safe existing directory")
    _assert_runtime_tree_sealed(root)
    if set(paths) != _RUNTIME_PATH_KEYS:
        raise ReleaseContractError(
            "runtime binding paths must be exactly: "
            + ", ".join(sorted(_RUNTIME_PATH_KEYS))
        )
    rows: list[RuntimePathBinding] = []
    for key in sorted(paths):
        relative = _safe_runtime_relative(paths[key], f"runtime path {key}")
        target = _resolve_runtime_member(root, relative, field=f"runtime path {key}")
        kind, fingerprint = _runtime_path_fingerprint(target)
        if key in {"STRUCTURE_STORE", "STRUCTURE_CUSTOM_DIR"} and kind != "directory":
            raise ReleaseContractError(f"{key} must bind a directory")
        if key in {"GLOSSARY_STORE", "RAG_LINKS_STORE"} and kind != "file":
            raise ReleaseContractError(f"{key} must bind a file")
        rows.append(RuntimePathBinding(key, relative, kind, fingerprint))
    expected_artifacts = _runtime_artifact_expectations(release)
    if set(artifact_paths) != set(expected_artifacts):
        raise ReleaseContractError(
            "runtime artifact proofs must be exactly: "
            + ", ".join(sorted(expected_artifacts))
        )
    artifacts: list[RuntimeArtifactProof] = []
    for key in sorted(artifact_paths):
        relative = _safe_runtime_relative(
            artifact_paths[key], f"runtime artifact {key}"
        )
        target = _resolve_runtime_member(
            root, relative, field=f"runtime artifact {key}"
        )
        kind, content_sha256 = _runtime_artifact_content(target)
        if key in {"main.promotion_receipt", "main.promotion_plan"} and kind != "file":
            raise ReleaseContractError(
                "MAIN promotion evidence runtime artifact must be a regular file"
            )
        expected_sha256, build_fingerprint, model_fingerprint = expected_artifacts[key]
        if content_sha256 != expected_sha256:
            raise ReleaseContractError(
                f"runtime artifact bytes do not match release manifest: {key}"
            )
        artifacts.append(
            RuntimeArtifactProof(
                key=key,
                path=relative,
                kind=kind,
                content_sha256=content_sha256,
                build_fingerprint=build_fingerprint,
                embedding_model_fingerprint=model_fingerprint,
            )
        )
    code_root = Path(code_package_root).expanduser()
    if not code_root.is_absolute():
        raise ReleaseContractError("code_package_root must be absolute")
    code_kind, code_sha256 = _runtime_artifact_content(code_root)
    if code_sha256 != release.code_package_sha256:
        raise ReleaseContractError(
            "deployed code package bytes do not match release manifest"
        )
    _, runtime_root_fingerprint = _runtime_path_fingerprint(root)
    core = {
        "schema_version": RUNTIME_BINDING_SCHEMA,
        "release_id": release.release_id,
        "release_manifest_sha256": release.manifest_sha256,
        "source_set_sha256": release.source_set.sha256,
        "created_at": _timestamp(created_at, "runtime binding created_at"),
        "sealed": True,
        "runtime_root_fingerprint_sha256": runtime_root_fingerprint,
        "code_package": {
            "kind": code_kind,
            "content_sha256": code_sha256,
        },
        "artifacts": {
            row.key: row.as_mapping() for row in artifacts
        },
        "paths": {row.key: row.as_mapping() for row in rows},
    }
    return RuntimeBindingDocument(
        release_id=release.release_id,
        release_manifest_sha256=release.manifest_sha256,
        source_set_sha256=release.source_set.sha256,
        created_at=core["created_at"],
        sealed=True,
        runtime_root_fingerprint_sha256=runtime_root_fingerprint,
        code_package_kind=code_kind,
        code_package_sha256=code_sha256,
        artifacts=tuple(artifacts),
        paths=tuple(rows),
        binding_sha256=_digest(core),
    )


def runtime_binding_from_mapping(
    blob: Mapping[str, Any],
    *,
    release: ReleaseManifest,
    runtime_root: str | os.PathLike[str],
    code_package_root: str | os.PathLike[str] | None = None,
    verify_paths: bool = True,
) -> RuntimeBindingDocument:
    _reject_unknown(
        blob,
        frozenset(
            {
                "schema_version",
                "release_id",
                "release_manifest_sha256",
                "source_set_sha256",
                "created_at",
                "sealed",
                "runtime_root_fingerprint_sha256",
                "code_package",
                "artifacts",
                "paths",
                "binding_sha256",
            }
        ),
        "runtime binding",
    )
    if blob.get("schema_version") != RUNTIME_BINDING_SCHEMA:
        raise ReleaseContractError("unsupported runtime binding schema")
    if (
        blob.get("release_id") != release.release_id
        or blob.get("release_manifest_sha256") != release.manifest_sha256
        or blob.get("source_set_sha256") != release.source_set.sha256
    ):
        raise ReleaseContractError("runtime binding is bound to another release")
    if blob.get("sealed") is not True:
        raise ReleaseContractError("runtime binding must declare a sealed tree")
    root_fingerprint = _hash(
        blob.get("runtime_root_fingerprint_sha256"),
        "runtime_root_fingerprint_sha256",
    )
    raw_code = _object(blob.get("code_package"), "runtime code_package")
    _reject_unknown(
        raw_code,
        frozenset({"kind", "content_sha256"}),
        "runtime code_package",
    )
    code_kind = str(raw_code.get("kind") or "")
    if code_kind not in {"file", "directory"}:
        raise ReleaseContractError("invalid runtime code package kind")
    code_sha256 = _hash(
        raw_code.get("content_sha256"), "runtime code_package content_sha256"
    )
    if code_sha256 != release.code_package_sha256:
        raise ReleaseContractError(
            "runtime code package proof does not match release manifest"
        )
    expected_artifacts = _runtime_artifact_expectations(release)
    raw_artifacts = blob.get("artifacts")
    if not isinstance(raw_artifacts, Mapping) or set(raw_artifacts) != set(expected_artifacts):
        raise ReleaseContractError("runtime artifact proof set is incomplete")
    artifacts: list[RuntimeArtifactProof] = []
    for key in sorted(raw_artifacts):
        raw_row = _object(raw_artifacts[key], f"runtime artifact {key}")
        _reject_unknown(
            raw_row,
            frozenset(
                {
                    "path",
                    "kind",
                    "content_sha256",
                    "build_fingerprint",
                    "embedding_model_fingerprint",
                }
            ),
            f"runtime artifact {key}",
        )
        relative = _safe_runtime_relative(
            raw_row.get("path"), f"runtime artifact {key}"
        )
        kind = str(raw_row.get("kind") or "")
        if kind not in {"file", "directory"}:
            raise ReleaseContractError(f"invalid runtime artifact kind: {key}")
        if key in {"main.promotion_receipt", "main.promotion_plan"} and kind != "file":
            raise ReleaseContractError(
                "MAIN promotion evidence runtime artifact must be a regular file"
            )
        content_sha256 = _hash(
            raw_row.get("content_sha256"),
            f"runtime artifact {key} content_sha256",
        )
        expected_sha256, expected_build, expected_model = expected_artifacts[key]
        if (
            content_sha256 != expected_sha256
            or raw_row.get("build_fingerprint") != expected_build
            or raw_row.get("embedding_model_fingerprint") != expected_model
        ):
            raise ReleaseContractError(
                f"runtime artifact proof does not match release manifest: {key}"
            )
        artifacts.append(
            RuntimeArtifactProof(
                key=key,
                path=relative,
                kind=kind,
                content_sha256=content_sha256,
                build_fingerprint=expected_build,
                embedding_model_fingerprint=expected_model,
            )
        )
    raw_paths = blob.get("paths")
    if not isinstance(raw_paths, Mapping) or set(raw_paths) != _RUNTIME_PATH_KEYS:
        raise ReleaseContractError("runtime binding path set is incomplete")
    root = Path(runtime_root).absolute()
    rows: list[RuntimePathBinding] = []
    for key in sorted(raw_paths):
        raw_row = _object(raw_paths[key], f"runtime path {key}")
        _reject_unknown(
            raw_row,
            frozenset({"path", "kind", "fingerprint_sha256"}),
            f"runtime path {key}",
        )
        relative = _safe_runtime_relative(raw_row.get("path"), f"runtime path {key}")
        kind = str(raw_row.get("kind") or "")
        if kind not in {"file", "directory"}:
            raise ReleaseContractError(f"invalid runtime path kind: {key}")
        fingerprint = _hash(
            raw_row.get("fingerprint_sha256"),
            f"runtime path {key} fingerprint_sha256",
        )
        if verify_paths:
            target = _resolve_runtime_member(root, relative, field=f"runtime path {key}")
            actual_kind, actual_fingerprint = _runtime_path_fingerprint(target)
            if actual_kind != kind or actual_fingerprint != fingerprint:
                raise ReleaseContractError(f"runtime path fingerprint mismatch: {key}")
        rows.append(RuntimePathBinding(key, relative, kind, fingerprint))
    normalized = dict(blob)
    declared = _hash(normalized.pop("binding_sha256", None), "binding_sha256")
    if _digest(normalized) != declared:
        raise ReleaseContractError("runtime binding_sha256 mismatch")
    if verify_paths:
        if code_package_root is None:
            raise ReleaseContractError(
                "runtime readiness requires an absolute code_package_root"
            )
        code_root = Path(code_package_root).expanduser()
        if not code_root.is_absolute():
            raise ReleaseContractError("code_package_root must be absolute")
        actual_code_kind, actual_code_sha256 = _runtime_artifact_content(code_root)
        if actual_code_kind != code_kind or actual_code_sha256 != code_sha256:
            raise ReleaseContractError("deployed code package fingerprint mismatch")
        _assert_runtime_tree_sealed(root)
        _, actual_root_fingerprint = _runtime_path_fingerprint(root)
        if actual_root_fingerprint != root_fingerprint:
            raise ReleaseContractError("sealed runtime root fingerprint mismatch")
        for artifact in artifacts:
            target = _resolve_runtime_member(
                root,
                artifact.path,
                field=f"runtime artifact {artifact.key}",
            )
            actual_kind, actual_sha256 = _runtime_artifact_content(target)
            if (
                actual_kind != artifact.kind
                or actual_sha256 != artifact.content_sha256
            ):
                raise ReleaseContractError(
                    f"runtime artifact fingerprint mismatch: {artifact.key}"
                )
    return RuntimeBindingDocument(
        release_id=release.release_id,
        release_manifest_sha256=release.manifest_sha256,
        source_set_sha256=release.source_set.sha256,
        created_at=_timestamp(blob.get("created_at"), "runtime binding created_at"),
        sealed=True,
        runtime_root_fingerprint_sha256=root_fingerprint,
        code_package_kind=code_kind,
        code_package_sha256=code_sha256,
        artifacts=tuple(artifacts),
        paths=tuple(rows),
        binding_sha256=declared,
    )


# ---------------------------------------------------------------------------
# Persisted release/receipt/pointer records


@dataclass(frozen=True)
class ValidationReceiptDocument:
    kind: str
    receipt_id: str
    target: str
    release_id: str
    release_manifest_sha256: str
    status: str
    created_at: str
    result_sha256: str
    details: Mapping[str, Any]

    def as_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": VALIDATION_RECEIPT_SCHEMA,
            "kind": self.kind,
            "receipt_id": self.receipt_id,
            "target": self.target,
            "release_id": self.release_id,
            "release_manifest_sha256": self.release_manifest_sha256,
            "status": self.status,
            "created_at": self.created_at,
            "result_sha256": self.result_sha256,
            "details": dict(self.details),
        }

    @property
    def sha256(self) -> str:
        return _digest(self.as_mapping())

    def reference(self) -> ValidationReceipt:
        return ValidationReceipt(self.kind, self.receipt_id, self.sha256)


def validation_receipt_from_mapping(
    blob: Mapping[str, Any],
) -> ValidationReceiptDocument:
    _reject_unknown(
        blob,
        frozenset(
            {
                "schema_version",
                "kind",
                "receipt_id",
                "target",
                "release_id",
                "release_manifest_sha256",
                "status",
                "created_at",
                "result_sha256",
                "details",
            }
        ),
        "validation receipt",
    )
    if blob.get("schema_version") != VALIDATION_RECEIPT_SCHEMA:
        raise ReleaseContractError("unsupported validation receipt schema")
    kind = str(blob.get("kind") or "")
    if kind not in _RECEIPT_KINDS:
        raise ReleaseContractError(f"invalid validation receipt kind: {kind!r}")
    target = str(blob.get("target") or "")
    if target not in _TARGETS:
        raise ReleaseContractError(f"invalid validation receipt target: {target!r}")
    if blob.get("status") != "passed":
        raise ReleaseContractError("validation receipt status must be passed")
    details = blob.get("details", {})
    if not isinstance(details, Mapping):
        raise ReleaseContractError("validation receipt details must be an object")
    return ValidationReceiptDocument(
        kind=kind,
        receipt_id=_identifier(blob.get("receipt_id"), "receipt_id"),
        target=target,
        release_id=_identifier(blob.get("release_id"), "release_id"),
        release_manifest_sha256=_hash(
            blob.get("release_manifest_sha256"), "release_manifest_sha256"
        ),
        status="passed",
        created_at=_timestamp(blob.get("created_at"), "created_at"),
        result_sha256=_hash(blob.get("result_sha256"), "result_sha256"),
        details=dict(details),
    )


def create_validation_receipt(
    *,
    kind: str,
    receipt_id: str,
    release: ReleaseManifest,
    created_at: str,
    result: object,
    details: Mapping[str, Any] | None = None,
) -> ValidationReceiptDocument:
    """Build a deterministic passed receipt bound to one exact release."""

    return validation_receipt_from_mapping(
        {
            "schema_version": VALIDATION_RECEIPT_SCHEMA,
            "kind": kind,
            "receipt_id": receipt_id,
            "target": release.target,
            "release_id": release.release_id,
            "release_manifest_sha256": release.manifest_sha256,
            "status": "passed",
            "created_at": created_at,
            "result_sha256": _digest(result),
            "details": dict(details or {}),
        }
    )


@dataclass(frozen=True)
class ActiveReleasePointer:
    generation: int
    target: str
    release_id: str
    release_manifest_sha256: str
    activation_id: str
    activation_plan_sha256: str
    action: str
    previous_release_id: str | None
    previous_pointer_sha256: str | None
    activated_at: str

    def as_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": ACTIVE_POINTER_SCHEMA,
            "generation": self.generation,
            "target": self.target,
            "release_id": self.release_id,
            "release_manifest_sha256": self.release_manifest_sha256,
            "activation_id": self.activation_id,
            "activation_plan_sha256": self.activation_plan_sha256,
            "action": self.action,
            "previous_release_id": self.previous_release_id,
            "previous_pointer_sha256": self.previous_pointer_sha256,
            "activated_at": self.activated_at,
        }

    @property
    def pointer_sha256(self) -> str:
        return _digest(self.as_mapping())


def active_pointer_from_mapping(blob: Mapping[str, Any]) -> ActiveReleasePointer:
    """Parse ``ACTIVE_RELEASE.json`` without accepting forward/unknown fields."""

    _reject_unknown(
        blob,
        frozenset(
            {
                "schema_version",
                "generation",
                "target",
                "release_id",
                "release_manifest_sha256",
                "activation_id",
                "activation_plan_sha256",
                "action",
                "previous_release_id",
                "previous_pointer_sha256",
                "activated_at",
            }
        ),
        "active release pointer",
    )
    if blob.get("schema_version") != ACTIVE_POINTER_SCHEMA:
        raise ReleaseContractError("unsupported active release pointer schema")
    generation = blob.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise ReleaseContractError(
            "active release generation must be a positive integer"
        )
    target = str(blob.get("target") or "")
    if target not in _TARGETS:
        raise ReleaseContractError(f"invalid active release target: {target!r}")
    action = str(blob.get("action") or "")
    if action not in {"activate", "rollback"}:
        raise ReleaseContractError(f"invalid active release action: {action!r}")
    raw_previous_release = blob.get("previous_release_id")
    previous_release = (
        None
        if raw_previous_release is None
        else _identifier(raw_previous_release, "previous_release_id")
    )
    raw_previous_pointer = blob.get("previous_pointer_sha256")
    previous_pointer = (
        None
        if raw_previous_pointer is None
        else _hash(raw_previous_pointer, "previous_pointer_sha256")
    )
    if generation == 1 and (previous_release is not None or previous_pointer is not None):
        raise ReleaseContractError(
            "first active release cannot claim a previous release or pointer"
        )
    if generation > 1 and (previous_release is None or previous_pointer is None):
        raise ReleaseContractError(
            "later active release requires previous release and pointer hashes"
        )
    release_id = _identifier(blob.get("release_id"), "release_id")
    if previous_release == release_id:
        raise ReleaseContractError("active release cannot point to itself as previous")
    return ActiveReleasePointer(
        generation=generation,
        target=target,
        release_id=release_id,
        release_manifest_sha256=_hash(
            blob.get("release_manifest_sha256"), "release_manifest_sha256"
        ),
        activation_id=_identifier(blob.get("activation_id"), "activation_id"),
        activation_plan_sha256=_hash(
            blob.get("activation_plan_sha256"), "activation_plan_sha256"
        ),
        action=action,
        previous_release_id=previous_release,
        previous_pointer_sha256=previous_pointer,
        activated_at=_timestamp(blob.get("activated_at"), "activated_at"),
    )


@dataclass(frozen=True)
class ReleaseActivationResult:
    pointer: ActiveReleasePointer
    prepared_receipt: Mapping[str, Any]
    committed_receipt: Mapping[str, Any]


_ACTIVATION_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "event",
        "event_sha256",
        "previous_event_sha256",
        "prepared_event_sha256",
        "activation_id",
        "action",
        "target",
        "at",
        "actor",
        "note",
        "plan_sha256",
        "release_id",
        "release_manifest_sha256",
        "before_generation",
        "after_generation",
        "before_pointer_sha256",
        "after_pointer_sha256",
        "previous_release_id",
        "validation_receipts",
    }
)


def _activation_event_from_mapping(blob: Mapping[str, Any]) -> dict[str, Any]:
    _reject_unknown(blob, _ACTIVATION_EVENT_FIELDS, "activation receipt event")
    if blob.get("schema_version") != ACTIVATION_RECEIPT_SCHEMA:
        raise ReleaseContractError("unsupported activation receipt schema")
    event = str(blob.get("event") or "")
    if event not in {"prepared", "committed"}:
        raise ReleaseContractError(f"invalid activation receipt event: {event!r}")
    action = str(blob.get("action") or "")
    if action not in {"activate", "rollback"}:
        raise ReleaseContractError(f"invalid activation action: {action!r}")
    target = str(blob.get("target") or "")
    if target not in _TARGETS:
        raise ReleaseContractError(f"invalid activation target: {target!r}")
    before_generation = blob.get("before_generation")
    after_generation = blob.get("after_generation")
    if (
        isinstance(before_generation, bool)
        or not isinstance(before_generation, int)
        or before_generation < 0
        or isinstance(after_generation, bool)
        or not isinstance(after_generation, int)
        or after_generation != before_generation + 1
    ):
        raise ReleaseContractError(
            "activation receipt generations must advance by exactly one"
        )
    raw_previous_event = blob.get("previous_event_sha256")
    if raw_previous_event is not None:
        _hash(raw_previous_event, "previous_event_sha256")
    raw_prepared = blob.get("prepared_event_sha256")
    if event == "prepared" and raw_prepared is not None:
        raise ReleaseContractError(
            "prepared activation receipt cannot reference another prepared event"
        )
    if event == "committed" and raw_prepared is None:
        raise ReleaseContractError(
            "committed activation receipt requires prepared_event_sha256"
        )
    if raw_prepared is not None:
        _hash(raw_prepared, "prepared_event_sha256")
    raw_before_pointer = blob.get("before_pointer_sha256")
    raw_previous_release = blob.get("previous_release_id")
    if before_generation == 0:
        if raw_before_pointer is not None or raw_previous_release is not None:
            raise ReleaseContractError(
                "first activation receipt cannot have previous state"
            )
    else:
        _hash(raw_before_pointer, "before_pointer_sha256")
        _identifier(raw_previous_release, "previous_release_id")
    _hash(blob.get("after_pointer_sha256"), "after_pointer_sha256")
    _hash(blob.get("plan_sha256"), "plan_sha256")
    _hash(blob.get("release_manifest_sha256"), "release_manifest_sha256")
    _identifier(blob.get("activation_id"), "activation_id")
    _identifier(blob.get("release_id"), "release_id")
    _required_text(blob.get("actor"), "activation actor")
    _required_text(blob.get("note"), "activation note")
    _timestamp(blob.get("at"), "activation timestamp")
    receipt_rows = blob.get("validation_receipts")
    receipts = _parse_receipts(receipt_rows)
    canonical_receipts = [
        {
            "kind": receipt.kind,
            "receipt_id": receipt.receipt_id,
            "sha256": receipt.sha256,
        }
        for receipt in sorted(receipts, key=lambda value: value.kind)
    ]
    if receipt_rows != canonical_receipts:
        raise ReleaseContractError(
            "activation validation_receipts must be sorted by kind"
        )
    normalized = dict(blob)
    declared = _hash(normalized.pop("event_sha256", None), "event_sha256")
    if _digest(normalized) != declared:
        raise ReleaseContractError("activation event_sha256 mismatch")
    return dict(blob)


class ReleaseStore:
    """Immutable release objects plus one generation-locked active pointer.

    Identifiers are never interpolated into filesystem paths.  Registries use a
    SHA-256 key and all caller-controlled paths remain data inside strict JSON
    records.  Every read rejects symbolic links and every mutation is serialized
    with a POSIX advisory lock rooted on the same filesystem as the pointer.
    """

    _DIRECTORIES = (
        "STAGING",
        "MANIFESTS",
        "RELEASE_IDS",
        "VALIDATION_RECEIPTS",
        "VALIDATION_RECEIPT_IDS",
        "POINTERS",
        "ACTIVATION_EVENTS",
        "RUNTIMES",
        "RUNTIME_BINDINGS",
    )

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        target: str | None = None,
        code_package_root: str | os.PathLike[str] | None = None,
        read_only: bool = False,
        clock: Callable[[], str] | None = None,
    ) -> None:
        if target is not None and target not in _TARGETS:
            raise ReleaseContractError(f"invalid release store target: {target!r}")
        if not isinstance(read_only, bool):
            raise ReleaseContractError("read_only must be boolean")
        candidate = Path(root).expanduser().absolute()
        normalized_code_root: Path | None = None
        if code_package_root is not None:
            normalized_code_root = Path(code_package_root).expanduser()
            if not normalized_code_root.is_absolute():
                raise ReleaseContractError("code_package_root must be absolute")
            if normalized_code_root.is_symlink() or not normalized_code_root.exists():
                raise ReleaseContractError(
                    "code_package_root must be an existing non-symbolic path"
                )
            if normalized_code_root.is_dir():
                try:
                    candidate.resolve().relative_to(normalized_code_root.resolve())
                except ValueError:
                    pass
                else:
                    raise ReleaseContractError(
                        "release store cannot live inside the code package"
                    )
        if candidate.exists() and candidate.is_symlink():
            raise ReleaseContractError("release store root cannot be a symbolic link")
        if candidate.exists() and not candidate.is_dir():
            raise ReleaseContractError("release store root must be a directory")
        if read_only and not candidate.is_dir():
            raise ReleaseContractError("read-only release store root is missing")
        if not read_only:
            candidate.mkdir(parents=True, exist_ok=True)
        if candidate.is_symlink():
            raise ReleaseContractError("release store root cannot be a symbolic link")
        self.root = candidate
        self.target = target
        self.code_package_root = normalized_code_root
        self.read_only = read_only
        self._clock = clock or _utc_now
        for name in self._DIRECTORIES:
            path = self.root / name
            if path.exists() and (path.is_symlink() or not path.is_dir()):
                raise ReleaseContractError(
                    f"release store directory is unsafe: {path}"
                )
            if read_only and not path.is_dir():
                raise ReleaseContractError(
                    f"read-only release store directory is missing: {path}"
                )
            if not read_only:
                path.mkdir(exist_ok=True)
        if not read_only:
            self._fsync_directory(self.root)

    @property
    def active_path(self) -> Path:
        return self._path("ACTIVE_RELEASE.json")

    @property
    def ledger_path(self) -> Path:
        return self._path("ACTIVATION_EVENTS")

    @staticmethod
    def _key(namespace: str, value: str) -> str:
        return hashlib.sha256(f"{namespace}\0{value}".encode("utf-8")).hexdigest()

    def _path(self, *parts: str) -> Path:
        for part in parts:
            if (
                not part
                or part in {".", ".."}
                or "/" in part
                or "\\" in part
                or Path(part).name != part
            ):
                raise ReleaseContractError(f"unsafe release store path part: {part!r}")
        path = self.root.joinpath(*parts)
        self._assert_safe(path)
        return path

    def _assert_safe(self, path: Path) -> None:
        try:
            relative = path.absolute().relative_to(self.root)
        except ValueError as exc:
            raise ReleaseContractError(
                f"release store path escapes root: {path}"
            ) from exc
        current = self.root
        if current.is_symlink():
            raise ReleaseContractError("release store root became a symbolic link")
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ReleaseContractError(
                    f"symbolic links are forbidden in release store: {current}"
                )
        resolved_root = self.root.resolve()
        try:
            path.resolve(strict=False).relative_to(resolved_root)
        except ValueError as exc:
            raise ReleaseContractError(
                f"release store path resolves outside root: {path}"
            ) from exc

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _fsync_regular(self, path: Path) -> None:
        self._assert_safe(path)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ReleaseContractError(
                    f"release store object is not a regular file: {path}"
                )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _read_regular(self, path: Path) -> bytes:
        self._assert_safe(path)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ReleaseContractError(f"cannot safely read {path}: {exc}") from exc
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise ReleaseContractError(f"release store object is not a file: {path}")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(descriptor)

    def _atomic_write(self, path: Path, raw: bytes) -> None:
        self._assert_safe(path)
        parent = path.parent
        self._assert_safe(parent)
        if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
            raise ReleaseContractError(f"unsafe release store parent: {parent}")
        parent.mkdir(parents=True, exist_ok=True)
        staging = self._path("STAGING")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="release-", suffix=".tmp", dir=staging
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            self._assert_safe(path)
            os.replace(temporary, path)
            self._fsync_directory(parent)
            if staging != parent:
                self._fsync_directory(staging)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _install_immutable(self, path: Path, raw: bytes) -> None:
        if path.exists() or path.is_symlink():
            current = self._read_regular(path)
            if current != raw:
                raise ReleaseContractError(
                    f"immutable release store object already differs: {path}"
                )
            return
        self._atomic_write(path, raw)

    def _remove_active_pointer(self) -> None:
        path = self.active_path
        self._assert_safe(path)
        if path.is_symlink():
            raise ReleaseContractError("ACTIVE_RELEASE.json cannot be a symbolic link")
        if path.exists():
            path.unlink()
            self._fsync_directory(path.parent)

    @contextmanager
    def _lock(self, *, exclusive: bool) -> Iterator[None]:
        try:
            import fcntl
        except ImportError as exc:  # pragma: no cover - candidate is POSIX-only
            raise ReleaseContractError("ReleaseStore requires POSIX fcntl locks") from exc
        path = self._path(".release-store.lock")
        if exclusive and self.read_only:
            raise ReleaseContractError("read-only release store forbids mutation")
        flags = os.O_RDONLY if self.read_only else os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ReleaseContractError("release store lock is not a regular file")
            operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(descriptor, operation)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _append_event(self, event: Mapping[str, Any]) -> dict[str, Any]:
        history = self._read_events_unlocked()
        row = dict(event)
        row["previous_event_sha256"] = (
            history[-1]["event_sha256"] if history else None
        )
        row.pop("event_sha256", None)
        row["event_sha256"] = _digest(row)
        checked = _activation_event_from_mapping(row)
        index = len(history) + 1
        path = self._path(
            "ACTIVATION_EVENTS",
            f"{index:020d}-{checked['event_sha256']}.json",
        )
        raw = _canonical(checked)
        try:
            self._install_immutable(path, raw)
            self._fsync_regular(path)
            self._fsync_directory(path.parent)
        except Exception:
            # os.replace may already have made the immutable event visible
            # before a directory fsync reported failure.  Re-read the exact
            # postcondition and retry both durability barriers.  Returning is
            # permitted only after the installed bytes and both fsyncs agree.
            try:
                if path.exists() and self._read_regular(path) == raw:
                    self._fsync_regular(path)
                    self._fsync_directory(path.parent)
                    return checked
            except Exception:
                pass
            raise
        return checked

    def _ensure_event_durable(
        self,
        event: Mapping[str, Any],
        history: Iterable[Mapping[str, Any]],
    ) -> None:
        rows = list(history)
        event_hash = _hash(event.get("event_sha256"), "event_sha256")
        positions = [
            position
            for position, row in enumerate(rows, 1)
            if row.get("event_sha256") == event_hash
        ]
        if len(positions) != 1:
            raise ReleaseContractError(
                "activation event durability check requires one ledger object"
            )
        path = self._path(
            "ACTIVATION_EVENTS",
            f"{positions[0]:020d}-{event_hash}.json",
        )
        if self._read_regular(path) != _canonical(dict(event)):
            raise ReleaseContractError("activation event durable bytes mismatch")
        self._fsync_regular(path)
        self._fsync_directory(path.parent)

    def _read_events_unlocked(self) -> list[dict[str, Any]]:
        directory = self.ledger_path
        if directory.is_symlink() or not directory.is_dir():
            raise ReleaseContractError("activation event store is not a safe directory")
        paths = sorted(directory.iterdir(), key=lambda value: value.name)
        events: list[dict[str, Any]] = []
        events_by_hash: dict[str, dict[str, Any]] = {}
        prepared_by_activation: dict[str, str] = {}
        committed_activations: set[str] = set()
        previous: str | None = None
        for position, path in enumerate(paths, 1):
            if path.is_symlink() or not path.is_file():
                raise ReleaseContractError(
                    f"unsafe activation event object: {path.name}"
                )
            match = re.fullmatch(r"([0-9]{20})-([0-9a-f]{64})\.json", path.name)
            if match is None or int(match.group(1)) != position:
                raise ReleaseContractError(
                    f"activation event sequence breaks at object {path.name}"
                )
            raw = self._read_regular(path)
            try:
                value = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ReleaseContractError(
                    f"invalid activation event JSON: {path.name}"
                ) from exc
            event = _activation_event_from_mapping(
                _object(value, f"activation event {path.name}")
            )
            if (
                event["event_sha256"] != match.group(2)
                or raw != _canonical(event)
            ):
                raise ReleaseContractError(
                    f"activation event object/hash mismatch: {path.name}"
                )
            if event.get("previous_event_sha256") != previous:
                raise ReleaseContractError(
                    f"activation receipt hash chain breaks at line {position}"
                )
            activation_id = str(event["activation_id"])
            if event["event"] == "prepared":
                if activation_id in prepared_by_activation:
                    raise ReleaseContractError(
                        f"duplicate prepared activation receipt: {activation_id}"
                    )
                prepared_by_activation[activation_id] = str(event["event_sha256"])
            else:
                prepared_hash = str(event["prepared_event_sha256"])
                prepared = events_by_hash.get(prepared_hash)
                if prepared is None or prepared.get("event") != "prepared":
                    raise ReleaseContractError(
                        f"committed activation lacks its prepared receipt: {activation_id}"
                    )
                if prepared.get("activation_id") != activation_id:
                    raise ReleaseContractError(
                        "committed activation references another activation ID"
                    )
                if activation_id in committed_activations:
                    raise ReleaseContractError(
                        f"duplicate committed activation receipt: {activation_id}"
                    )
                common_fields = {
                    "action",
                    "target",
                    "at",
                    "actor",
                    "note",
                    "plan_sha256",
                    "release_id",
                    "release_manifest_sha256",
                    "before_generation",
                    "after_generation",
                    "before_pointer_sha256",
                    "after_pointer_sha256",
                    "previous_release_id",
                    "validation_receipts",
                }
                mismatches = sorted(
                    field
                    for field in common_fields
                    if event.get(field) != prepared.get(field)
                )
                if mismatches:
                    raise ReleaseContractError(
                        "committed/prepared activation mismatch: "
                        + ", ".join(mismatches)
                    )
                committed_activations.add(activation_id)
            previous = str(event["event_sha256"])
            events.append(event)
            events_by_hash[previous] = event
        return events

    def activation_events(self) -> tuple[Mapping[str, Any], ...]:
        with self._lock(exclusive=False):
            return tuple(self._read_events_unlocked())

    def _manifest_path(self, manifest_sha256: str) -> Path:
        return self._path("MANIFESTS", _hash(manifest_sha256, "manifest_sha256") + ".json")

    def _release_ref_path(self, release_id: str) -> Path:
        identifier = _identifier(release_id, "release_id")
        return self._path("RELEASE_IDS", self._key("release", identifier) + ".json")

    def install_manifest(self, blob: Mapping[str, Any]) -> ReleaseManifest:
        """Install one declared-hash manifest; an ID can never change meaning."""

        release = release_from_mapping(blob)
        if blob.get("manifest_sha256") != release.manifest_sha256:
            raise ReleaseContractError(
                "installed release manifest must declare its canonical manifest_sha256"
            )
        if self.target is not None and release.target != self.target:
            raise ReleaseContractError("release target does not match ReleaseStore target")
        manifest_raw = _canonical(dict(blob))
        reference = {
            "schema_version": "release-install-reference-v1",
            "release_id": release.release_id,
            "manifest_sha256": release.manifest_sha256,
            "target": release.target,
        }
        reference_raw = _canonical(reference)
        with self._lock(exclusive=True):
            manifest_path = self._manifest_path(release.manifest_sha256)
            self._install_immutable(manifest_path, manifest_raw)
            ref_path = self._release_ref_path(release.release_id)
            if ref_path.exists() or ref_path.is_symlink():
                try:
                    current = json.loads(self._read_regular(ref_path))
                except json.JSONDecodeError as exc:
                    raise ReleaseContractError(
                        f"invalid release install reference: {ref_path}"
                    ) from exc
                if current != reference:
                    raise ReleaseContractError(
                        f"release ID already has another manifest: {release.release_id}"
                    )
            self._install_immutable(ref_path, reference_raw)
        return release

    install_release = install_manifest

    def load_manifest(self, release_id: str) -> ReleaseManifest:
        ref_path = self._release_ref_path(release_id)
        try:
            reference = json.loads(self._read_regular(ref_path))
        except json.JSONDecodeError as exc:
            raise ReleaseContractError(
                f"invalid release install reference: {ref_path}"
            ) from exc
        reference = _object(reference, "release install reference")
        _reject_unknown(
            reference,
            frozenset({"schema_version", "release_id", "manifest_sha256", "target"}),
            "release install reference",
        )
        if reference.get("schema_version") != "release-install-reference-v1":
            raise ReleaseContractError("unsupported release install reference schema")
        expected_id = _identifier(release_id, "release_id")
        if reference.get("release_id") != expected_id:
            raise ReleaseContractError("release install reference ID mismatch")
        expected_sha = _hash(reference.get("manifest_sha256"), "manifest_sha256")
        target = str(reference.get("target") or "")
        if target not in _TARGETS:
            raise ReleaseContractError("release install reference target is invalid")
        manifest_path = self._manifest_path(expected_sha)
        try:
            blob = json.loads(self._read_regular(manifest_path))
        except json.JSONDecodeError as exc:
            raise ReleaseContractError(f"invalid installed manifest: {manifest_path}") from exc
        release = release_from_mapping(_object(blob, "installed release manifest"))
        if (
            release.release_id != expected_id
            or release.manifest_sha256 != expected_sha
            or release.target != target
        ):
            raise ReleaseContractError("installed release manifest/reference mismatch")
        if blob.get("manifest_sha256") != expected_sha:
            raise ReleaseContractError("installed release manifest lacks its declared hash")
        if self.target is not None and release.target != self.target:
            raise ReleaseContractError("installed release has another target")
        return release

    load_release = load_manifest

    def runtime_root(self, release_id: str, *, create: bool = False) -> Path:
        release = self.load_manifest(release_id)
        path = self._path("RUNTIMES", release.manifest_sha256)
        if path.exists() and (path.is_symlink() or not path.is_dir()):
            raise ReleaseContractError("release runtime root is unsafe")
        if create and not path.exists():
            with self._lock(exclusive=True):
                path.mkdir(mode=0o750, exist_ok=False)
                self._fsync_directory(path.parent)
        if not create and not path.is_dir():
            raise ReleaseContractError("release runtime root is not installed")
        return path

    def _runtime_binding_path(self, manifest_sha256: str) -> Path:
        return self._path(
            "RUNTIME_BINDINGS",
            _hash(manifest_sha256, "manifest_sha256") + ".json",
        )

    def install_runtime_binding(
        self,
        release_id: str,
        *,
        paths: Mapping[str, str],
        artifact_paths: Mapping[str, str],
        created_at: str | None = None,
    ) -> RuntimeBindingDocument:
        if self.code_package_root is None:
            raise ReleaseContractError(
                "runtime binding install requires code_package_root"
            )
        release = self.load_manifest(release_id)
        root = self.runtime_root(release_id)
        with self._lock(exclusive=True):
            _seal_runtime_tree(root)
            document = create_runtime_binding(
                release=release,
                runtime_root=root,
                paths=paths,
                artifact_paths=artifact_paths,
                code_package_root=self.code_package_root,
                created_at=created_at or self._clock(),
            )
            raw = _canonical(document.as_mapping())
            self._install_immutable(
                self._runtime_binding_path(release.manifest_sha256), raw
            )
        return document

    def load_runtime_binding(
        self,
        release_id: str,
        *,
        verify_paths: bool = True,
    ) -> RuntimeBindingDocument:
        release = self.load_manifest(release_id)
        root = self.runtime_root(release_id)
        path = self._runtime_binding_path(release.manifest_sha256)
        try:
            blob = json.loads(self._read_regular(path))
        except json.JSONDecodeError as exc:
            raise ReleaseContractError("installed runtime binding is invalid JSON") from exc
        return runtime_binding_from_mapping(
            _object(blob, "installed runtime binding"),
            release=release,
            runtime_root=root,
            code_package_root=self.code_package_root,
            verify_paths=verify_paths,
        )

    def verify_runtime_ready(
        self,
        release_id: str,
        *,
        expected_binding_sha256: str,
    ) -> RuntimeBindingDocument:
        """Re-hash one process-pinned runtime without following ACTIVE_RELEASE."""

        expected = _hash(
            expected_binding_sha256, "expected runtime binding_sha256"
        )
        with self._lock(exclusive=False):
            binding = self.load_runtime_binding(release_id, verify_paths=True)
            if binding.binding_sha256 != expected:
                raise ReleaseContractError(
                    "process-pinned runtime binding identity changed"
                )
            return binding

    def _validation_path(self, sha256: str) -> Path:
        return self._path(
            "VALIDATION_RECEIPTS",
            _hash(sha256, "validation receipt sha256") + ".json",
        )

    def _validation_ref_path(self, kind: str, receipt_id: str) -> Path:
        if kind not in _RECEIPT_KINDS:
            raise ReleaseContractError(f"invalid validation receipt kind: {kind!r}")
        identifier = _identifier(receipt_id, "receipt_id")
        return self._path(
            "VALIDATION_RECEIPT_IDS",
            self._key("validation", f"{kind}\0{identifier}") + ".json",
        )

    def install_validation_receipt(
        self, blob: Mapping[str, Any] | ValidationReceiptDocument
    ) -> ValidationReceipt:
        document = (
            blob
            if isinstance(blob, ValidationReceiptDocument)
            else validation_receipt_from_mapping(blob)
        )
        release = self.load_manifest(document.release_id)
        if (
            document.target != release.target
            or document.release_manifest_sha256 != release.manifest_sha256
        ):
            raise ReleaseContractError(
                "validation receipt is bound to another release or target"
            )
        raw = _canonical(document.as_mapping())
        sha256 = hashlib.sha256(raw).hexdigest()
        reference = {
            "schema_version": "validation-receipt-install-reference-v1",
            "kind": document.kind,
            "receipt_id": document.receipt_id,
            "sha256": sha256,
        }
        ref_raw = _canonical(reference)
        with self._lock(exclusive=True):
            self._install_immutable(self._validation_path(sha256), raw)
            ref_path = self._validation_ref_path(document.kind, document.receipt_id)
            if ref_path.exists() or ref_path.is_symlink():
                try:
                    current = json.loads(self._read_regular(ref_path))
                except json.JSONDecodeError as exc:
                    raise ReleaseContractError(
                        f"invalid validation receipt reference: {ref_path}"
                    ) from exc
                if current != reference:
                    raise ReleaseContractError(
                        "validation receipt ID already has another immutable value"
                    )
            self._install_immutable(ref_path, ref_raw)
        return ValidationReceipt(document.kind, document.receipt_id, sha256)

    def load_validation_receipt(
        self, reference: ValidationReceipt
    ) -> ValidationReceiptDocument:
        path = self._validation_path(reference.sha256)
        raw = self._read_regular(path)
        if hashlib.sha256(raw).hexdigest() != reference.sha256:
            raise ReleaseContractError("installed validation receipt hash mismatch")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReleaseContractError(f"invalid validation receipt JSON: {path}") from exc
        document = validation_receipt_from_mapping(
            _object(value, "installed validation receipt")
        )
        if document.kind != reference.kind or document.receipt_id != reference.receipt_id:
            raise ReleaseContractError("validation receipt reference mismatch")
        ref_path = self._validation_ref_path(reference.kind, reference.receipt_id)
        try:
            installed_ref = json.loads(self._read_regular(ref_path))
        except json.JSONDecodeError as exc:
            raise ReleaseContractError(
                f"invalid validation receipt install reference: {ref_path}"
            ) from exc
        expected_ref = {
            "schema_version": "validation-receipt-install-reference-v1",
            "kind": reference.kind,
            "receipt_id": reference.receipt_id,
            "sha256": reference.sha256,
        }
        if installed_ref != expected_ref:
            raise ReleaseContractError("validation receipt install reference mismatch")
        return document

    @staticmethod
    def _verify_runtime_provenance_receipt(
        documents: Iterable[ValidationReceiptDocument],
        binding: RuntimeBindingDocument,
    ) -> None:
        provenance_rows = [
            document for document in documents if document.kind == "provenance"
        ]
        if len(provenance_rows) != 1:
            raise ReleaseContractError(
                "runtime readiness requires exactly one provenance receipt"
            )
        provenance = provenance_rows[0]
        expected_result_sha256 = _digest(binding.provenance_result())
        if (
            provenance.result_sha256 != expected_result_sha256
            or dict(provenance.details) != binding.provenance_details()
        ):
            raise ReleaseContractError(
                "provenance receipt does not attest the verified runtime bytes"
            )

    def _verify_plan_receipts(
        self,
        plan: ReleaseActivationPlan,
        release: ReleaseManifest,
    ) -> tuple[ValidationReceiptDocument, ...]:
        documents = tuple(
            self.load_validation_receipt(reference)
            for reference in plan.validation_receipts
        )
        for document in documents:
            if (
                document.release_id != release.release_id
                or document.release_manifest_sha256 != release.manifest_sha256
                or document.target != release.target
                or document.status != "passed"
            ):
                raise ReleaseContractError(
                    f"{document.kind} validation receipt is not bound to this release"
                )
        binding = self.load_runtime_binding(release.release_id)
        self._verify_runtime_provenance_receipt(documents, binding)
        return documents

    def _read_active_pointer_unlocked(self) -> ActiveReleasePointer | None:
        path = self.active_path
        if not path.exists() and not path.is_symlink():
            return None
        try:
            value = json.loads(self._read_regular(path))
        except json.JSONDecodeError as exc:
            raise ReleaseContractError("ACTIVE_RELEASE.json is invalid JSON") from exc
        pointer = active_pointer_from_mapping(_object(value, "ACTIVE_RELEASE.json"))
        if self.target is not None and pointer.target != self.target:
            raise ReleaseContractError("active pointer has another deployment target")
        release = self.load_manifest(pointer.release_id)
        if (
            release.manifest_sha256 != pointer.release_manifest_sha256
            or release.target != pointer.target
        ):
            raise ReleaseContractError("active pointer/release manifest mismatch")
        return pointer

    @staticmethod
    def _pointer_event_expected(pointer: ActiveReleasePointer) -> dict[str, Any]:
        return {
            "action": pointer.action,
            "target": pointer.target,
            "plan_sha256": pointer.activation_plan_sha256,
            "release_id": pointer.release_id,
            "release_manifest_sha256": pointer.release_manifest_sha256,
            "after_generation": pointer.generation,
            "after_pointer_sha256": pointer.pointer_sha256,
            "before_pointer_sha256": pointer.previous_pointer_sha256,
            "previous_release_id": pointer.previous_release_id,
        }

    def _validate_pointer_commit(
        self,
        pointer: ActiveReleasePointer,
        history: Iterable[Mapping[str, Any]],
    ) -> None:
        rows = list(history)
        commits = [
            event
            for event in rows
            if event.get("event") == "committed"
            and event.get("activation_id") == pointer.activation_id
        ]
        if len(commits) != 1:
            raise ReleaseContractError(
                "active pointer requires exactly one committed activation receipt"
            )
        committed_history = [
            event for event in rows if event.get("event") == "committed"
        ]
        if (
            not committed_history
            or committed_history[-1].get("activation_id") != pointer.activation_id
        ):
            raise ReleaseContractError(
                "active pointer is not the latest committed activation"
            )
        commit = commits[0]
        expected = self._pointer_event_expected(pointer)
        mismatches = [key for key, expected_value in expected.items()
                      if commit.get(key) != expected_value]
        if mismatches:
            raise ReleaseContractError(
                "active pointer/activation receipt mismatch: " + ", ".join(mismatches)
            )

    def _load_active_unlocked(self) -> ActiveReleasePointer | None:
        pointer = self._read_active_pointer_unlocked()
        if pointer is None:
            return None
        self._validate_pointer_commit(pointer, self._read_events_unlocked())
        return pointer

    def recover_incomplete_activation(self) -> dict[str, Any]:
        """Roll back an atomically switched pointer lacking a commit receipt.

        The immutable pointer archive and prepared event make the crash window
        deterministic: a pointer with a matching commit is retained; a pointer
        with only its exact prepared event is restored to its prior generation.
        Any other shape is corruption and remains fail-closed.
        """

        with self._lock(exclusive=True):
            pointer = self._read_active_pointer_unlocked()
            if pointer is None:
                return {"status": "no-active-release", "recovered": False}
            history = self._read_events_unlocked()
            commits = [
                event
                for event in history
                if event.get("event") == "committed"
                and event.get("activation_id") == pointer.activation_id
            ]
            if commits:
                self._validate_pointer_commit(pointer, history)
                self._ensure_event_durable(commits[0], history)
                return {
                    "status": "already-committed",
                    "recovered": False,
                    "generation": pointer.generation,
                    "release_id": pointer.release_id,
                }
            prepared_rows = [
                event
                for event in history
                if event.get("event") == "prepared"
                and event.get("activation_id") == pointer.activation_id
            ]
            if len(prepared_rows) != 1:
                raise ReleaseContractError(
                    "uncommitted active pointer lacks exactly one prepared receipt"
                )
            prepared = prepared_rows[0]
            expected = self._pointer_event_expected(pointer)
            mismatches = sorted(
                key for key, value in expected.items() if prepared.get(key) != value
            )
            if mismatches:
                raise ReleaseContractError(
                    "uncommitted pointer/prepared receipt mismatch: "
                    + ", ".join(mismatches)
                )
            if pointer.generation == 1:
                self._remove_active_pointer()
                return {
                    "status": "restored-empty",
                    "recovered": True,
                    "aborted_release_id": pointer.release_id,
                }
            previous_path = self._path(
                "POINTERS",
                f"{pointer.generation - 1:020d}-{pointer.previous_pointer_sha256}.json",
            )
            try:
                previous_value = json.loads(self._read_regular(previous_path))
            except json.JSONDecodeError as exc:
                raise ReleaseContractError(
                    "previous pointer archive is invalid JSON"
                ) from exc
            previous = active_pointer_from_mapping(
                _object(previous_value, "previous pointer archive")
            )
            if (
                previous.pointer_sha256 != pointer.previous_pointer_sha256
                or previous.generation != pointer.generation - 1
                or previous.release_id != pointer.previous_release_id
            ):
                raise ReleaseContractError(
                    "previous pointer archive does not match recovery boundary"
                )
            self._validate_pointer_commit(previous, history)
            self._atomic_write(self.active_path, _canonical(previous.as_mapping()))
            return {
                "status": "restored-previous",
                "recovered": True,
                "aborted_release_id": pointer.release_id,
                "generation": previous.generation,
                "release_id": previous.release_id,
                "pointer_sha256": previous.pointer_sha256,
            }

    def load_active(self) -> ActiveReleasePointer | None:
        with self._lock(exclusive=False):
            return self._load_active_unlocked()

    def _load_active_runtime_unlocked(
        self,
    ) -> tuple[
        ActiveReleasePointer,
        ReleaseManifest,
        RuntimeBindingDocument,
        tuple[ValidationReceiptDocument, ...],
    ]:
        pointer = self._load_active_unlocked()
        if pointer is None:
            raise ReleaseContractError("release store has no active release")
        release = self.load_manifest(pointer.release_id)
        history = self._read_events_unlocked()
        # Re-bind the pointer to this exact ledger snapshot.  _load_active_unlocked
        # performed the same check on its read, but an accessor must not trust a
        # receipt set obtained from a later, independently parsed history.
        self._validate_pointer_commit(pointer, history)
        commits = [
            event
            for event in history
            if event.get("event") == "committed"
            and event.get("activation_id") == pointer.activation_id
        ]
        if len(commits) != 1:
            raise ReleaseContractError(
                "active release requires exactly one committed activation receipt"
            )
        commit = commits[0]
        self._ensure_event_durable(commit, history)
        references = _parse_receipts(commit.get("validation_receipts"))
        documents = tuple(
            self.load_validation_receipt(reference) for reference in references
        )
        for document in documents:
            if (
                document.release_id != release.release_id
                or document.release_manifest_sha256 != release.manifest_sha256
                or document.target != release.target
                or document.status != "passed"
            ):
                raise ReleaseContractError(
                    f"{document.kind} validation receipt is not bound to this release"
                )
        binding = self.load_runtime_binding(release.release_id)
        self._verify_runtime_provenance_receipt(documents, binding)
        return pointer, release, binding, documents

    def load_active_runtime(
        self,
    ) -> tuple[ActiveReleasePointer, ReleaseManifest, RuntimeBindingDocument]:
        """Load one process-pinnable release and its exact runtime path tree."""

        with self._lock(exclusive=False):
            pointer, release, binding, _ = self._load_active_runtime_unlocked()
            return pointer, release, binding

    def load_active_validation_receipt(
        self,
        *,
        kind: str,
    ) -> ValidationReceiptDocument:
        """Load one exact, active-plan-bound validation receipt without mutation."""

        if kind not in _RECEIPT_KINDS:
            raise ReleaseContractError(f"invalid validation receipt kind: {kind!r}")
        with self._lock(exclusive=False):
            _, _, _, documents = self._load_active_runtime_unlocked()
            matches = [document for document in documents if document.kind == kind]
            if len(matches) != 1:
                raise ReleaseContractError(
                    f"active release requires exactly one {kind} validation receipt"
                )
            return matches[0]

    current = load_active

    def current_cas(self) -> dict[str, Any]:
        pointer = self.load_active()
        return {
            "generation": pointer.generation if pointer else 0,
            "pointer_sha256": pointer.pointer_sha256 if pointer else None,
            "release_id": pointer.release_id if pointer else None,
        }

    def prepare_activation(
        self,
        release_id: str,
        *,
        activation_id: str,
        validation_receipts: Iterable[ValidationReceipt],
        created_at: str | None = None,
    ) -> ReleaseActivationPlan:
        """Freeze current CAS state; a later concurrent apply will make it stale."""

        return self._prepare_activation(
            release_id,
            action="activate",
            activation_id=activation_id,
            validation_receipts=validation_receipts,
            created_at=created_at,
        )

    def _prepare_activation(
        self,
        release_id: str,
        *,
        action: str,
        activation_id: str,
        validation_receipts: Iterable[ValidationReceipt],
        created_at: str | None,
    ) -> ReleaseActivationPlan:
        if action not in {"activate", "rollback"}:
            raise ReleaseContractError(f"invalid activation plan action: {action!r}")

        release = self.load_manifest(release_id)
        references = tuple(
            sorted(tuple(validation_receipts), key=lambda value: value.kind)
        )
        receipt_rows = [
            {
                "kind": reference.kind,
                "receipt_id": reference.receipt_id,
                "sha256": reference.sha256,
            }
            for reference in references
        ]
        parsed_receipts = _parse_receipts(receipt_rows)
        current = self.load_active()
        blob: dict[str, Any] = {
            "schema_version": ACTIVATION_PLAN_SCHEMA,
            "action": action,
            "activation_id": _identifier(activation_id, "activation_id"),
            "target": release.target,
            "created_at": _timestamp(
                created_at or self._clock(), "activation plan created_at"
            ),
            "release_id": release.release_id,
            "release_manifest_sha256": release.manifest_sha256,
            "expected_active_generation": current.generation if current else 0,
            "expected_active_pointer_sha256": (
                current.pointer_sha256 if current else None
            ),
            "rollback_release_id": current.release_id if current else None,
            "validation_receipts": [
                {
                    "kind": reference.kind,
                    "receipt_id": reference.receipt_id,
                    "sha256": reference.sha256,
                }
                for reference in parsed_receipts
            ],
        }
        blob["plan_sha256"] = _digest(blob)
        plan = activation_plan_from_mapping(blob)
        self._verify_plan_receipts(plan, release)
        return plan

    def prepare_rollback(
        self,
        *,
        activation_id: str,
        validation_receipts: Iterable[ValidationReceipt],
        created_at: str | None = None,
    ) -> ReleaseActivationPlan:
        current = self.load_active()
        if current is None or current.previous_release_id is None:
            raise ReleaseContractError("there is no previous release to roll back to")
        return self._prepare_activation(
            current.previous_release_id,
            action="rollback",
            activation_id=activation_id,
            validation_receipts=validation_receipts,
            created_at=created_at,
        )

    @staticmethod
    def _coerce_plan(
        plan: ReleaseActivationPlan | Mapping[str, Any],
    ) -> ReleaseActivationPlan:
        if isinstance(plan, ReleaseActivationPlan):
            return activation_plan_from_mapping(plan.as_mapping())
        if plan.get("plan_sha256") is None:
            raise ReleaseContractError(
                "persisted activation plan must declare plan_sha256"
            )
        return activation_plan_from_mapping(plan)

    @staticmethod
    def _receipt_rows(plan: ReleaseActivationPlan) -> list[dict[str, str]]:
        return [
            {
                "kind": reference.kind,
                "receipt_id": reference.receipt_id,
                "sha256": reference.sha256,
            }
            for reference in sorted(
                plan.validation_receipts, key=lambda value: value.kind
            )
        ]

    def _activate(
        self,
        raw_plan: ReleaseActivationPlan | Mapping[str, Any],
        *,
        action: str,
        actor: str,
        note: str,
        confirm: bool,
    ) -> ReleaseActivationResult:
        if confirm is not True:
            raise ReleaseContractError("release activation requires confirm=True")
        actor = _required_text(actor, "activation actor")
        note = _required_text(note, "activation note")
        plan = self._coerce_plan(raw_plan)
        if plan.action != action:
            raise ReleaseContractError(
                f"activation plan action {plan.action!r} cannot be used as {action!r}"
            )
        if self.target is not None and plan.target != self.target:
            raise ReleaseContractError("activation plan has another target")
        with self._lock(exclusive=True):
            current = self._load_active_unlocked()
            release = self.load_manifest(plan.release_id)
            current_mapping = current.as_mapping() if current else None
            validate_activation_plan(
                plan,
                release,
                current_pointer=current_mapping,
            )
            self._verify_plan_receipts(plan, release)
            history = self._read_events_unlocked()
            if any(
                event.get("activation_id") == plan.activation_id
                for event in history
            ):
                raise ReleaseContractError(
                    f"activation ID was already used: {plan.activation_id}"
                )
            if action == "rollback":
                if current is None or current.previous_release_id is None:
                    raise ReleaseContractError(
                        "there is no previous active release to roll back to"
                    )
                if plan.release_id != current.previous_release_id:
                    raise ReleaseContractError(
                        "rollback can activate only the immediately previous release"
                    )
            elif action == "activate":
                if current is not None and plan.release_id == current.release_id:
                    raise ReleaseContractError("release is already active")
            else:  # defensive: public methods pass literals
                raise ReleaseContractError(f"invalid activation action: {action!r}")

            before_generation = current.generation if current else 0
            before_pointer_sha256 = current.pointer_sha256 if current else None
            previous_release_id = current.release_id if current else None
            activated_at = _timestamp(self._clock(), "activation timestamp")
            pointer = ActiveReleasePointer(
                generation=before_generation + 1,
                target=release.target,
                release_id=release.release_id,
                release_manifest_sha256=release.manifest_sha256,
                activation_id=plan.activation_id,
                activation_plan_sha256=plan.plan_sha256,
                action=action,
                previous_release_id=previous_release_id,
                previous_pointer_sha256=before_pointer_sha256,
                activated_at=activated_at,
            )
            common_event: dict[str, Any] = {
                "schema_version": ACTIVATION_RECEIPT_SCHEMA,
                "activation_id": plan.activation_id,
                "action": action,
                "target": release.target,
                "at": activated_at,
                "actor": actor,
                "note": note,
                "plan_sha256": plan.plan_sha256,
                "release_id": release.release_id,
                "release_manifest_sha256": release.manifest_sha256,
                "before_generation": before_generation,
                "after_generation": pointer.generation,
                "before_pointer_sha256": before_pointer_sha256,
                "after_pointer_sha256": pointer.pointer_sha256,
                "previous_release_id": previous_release_id,
                "validation_receipts": self._receipt_rows(plan),
            }
            prepared = self._append_event(
                {
                    **common_event,
                    "event": "prepared",
                    "prepared_event_sha256": None,
                }
            )
            pointer_raw = _canonical(pointer.as_mapping())
            pointer_archive = self._path(
                "POINTERS",
                f"{pointer.generation:020d}-{pointer.pointer_sha256}.json",
            )
            self._install_immutable(pointer_archive, pointer_raw)
            try:
                self._atomic_write(self.active_path, pointer_raw)
                committed = self._append_event(
                    {
                        **common_event,
                        "event": "committed",
                        "prepared_event_sha256": prepared["event_sha256"],
                    }
                )
            except Exception:
                # A commit event may have crossed os.replace before its first
                # directory fsync failed.  Once that immutable event is visible
                # we must never roll the pointer back: doing so would leave the
                # ledger committed to B while ACTIVE_RELEASE names A.  Re-read
                # the ledger, re-establish both durability barriers, and accept
                # success only when the active pointer still has the exact bytes.
                history_readable = False
                matching_commits: list[Mapping[str, Any]] = []
                committed_after_error: Mapping[str, Any] | None = None
                try:
                    history_after_error = self._read_events_unlocked()
                    history_readable = True
                    matching_commits = [
                        event
                        for event in history_after_error
                        if event.get("event") == "committed"
                        and event.get("activation_id") == plan.activation_id
                    ]
                    if matching_commits:
                        self._validate_pointer_commit(pointer, history_after_error)
                        self._ensure_event_durable(
                            matching_commits[0], history_after_error
                        )
                        if self._read_regular(self.active_path) != pointer_raw:
                            self._atomic_write(self.active_path, pointer_raw)
                        if self._read_regular(self.active_path) != pointer_raw:
                            raise ReleaseContractError(
                                "committed activation pointer postcondition failed"
                            )
                        committed_after_error = matching_commits[0]
                except Exception:
                    # An unreadable/unsyncable visible commit is indeterminate.
                    # Preserve the new pointer and fail closed for startup
                    # recovery; never manufacture the contradictory old state.
                    if history_readable and matching_commits:
                        raise
                    history_readable = False
                if committed_after_error is not None:
                    return ReleaseActivationResult(
                        pointer, prepared, committed_after_error
                    )
                if not history_readable:
                    raise
                active_is_new = False
                try:
                    active_is_new = (
                        self.active_path.exists()
                        and self._read_regular(self.active_path) == pointer_raw
                    )
                except ReleaseContractError:
                    # An unreadable active pointer is never treated as the old
                    # state; attempt the same bounded restoration below.
                    active_is_new = True
                if active_is_new:
                    if current is None:
                        self._remove_active_pointer()
                    else:
                        self._atomic_write(
                            self.active_path, _canonical(current.as_mapping())
                        )
                raise
            return ReleaseActivationResult(pointer, prepared, committed)

    def activate(
        self,
        plan: ReleaseActivationPlan | Mapping[str, Any],
        *,
        actor: str,
        note: str,
        confirm: bool,
    ) -> ReleaseActivationResult:
        return self._activate(
            plan,
            action="activate",
            actor=actor,
            note=note,
            confirm=confirm,
        )

    def rollback(
        self,
        plan: ReleaseActivationPlan | Mapping[str, Any],
        *,
        actor: str,
        note: str,
        confirm: bool,
    ) -> ReleaseActivationResult:
        return self._activate(
            plan,
            action="rollback",
            actor=actor,
            note=note,
            confirm=confirm,
        )
