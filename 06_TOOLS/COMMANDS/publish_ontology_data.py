#!/usr/bin/env python3
"""Publish or roll back one verified Legal Graph + DefinitionProjection pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from lawrag.ontology.definition_projection import DefinitionProjectionStore, GraphSnapshot
from lawrag.platform.paths import repository_root


ROOT = repository_root()
RECEIPT_SCHEMA = "ontology-data-release-receipt-v1"
ROLLBACK_SCHEMA = "ontology-data-rollback-receipt-v1"
RELEASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _value_sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_child(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    target.relative_to(root.resolve())
    return target


def _atomic_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_once(path: Path, value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    raw = payload.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise RuntimeError(f"immutable release record differs: {path}")
    else:
        try:
            os.write(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return hashlib.sha256(raw).hexdigest()


def _pointer_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return {"sha256": _file_sha(path), "value": _json(path)}


def _verify_manifest_generation(store: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    pointer = _json(store / "CURRENT.json")
    manifest_path = _safe_child(store, str(pointer.get("manifest") or ""))
    manifest = _json(manifest_path)
    if pointer.get("generation_id") != manifest.get("generation_id"):
        raise RuntimeError(f"CURRENT/manifest generation mismatch: {store}")
    unsigned = dict(manifest)
    claimed = str(unsigned.pop("content_sha256", ""))
    if not claimed or claimed != _value_sha(unsigned) or claimed != pointer.get("content_sha256"):
        raise RuntimeError(f"manifest content hash mismatch: {store}")
    validation = _json(manifest_path.parent / "validation/summary.json")
    if validation.get("ok") is not True or validation.get("generation_id") != manifest.get("generation_id"):
        raise RuntimeError(f"independent validation receipt failed: {store}")
    for relative, metadata in (manifest.get("artifacts") or {}).items():
        if not isinstance(metadata, Mapping):
            raise RuntimeError(f"invalid artifact metadata: {relative}")
        artifact = _safe_child(manifest_path.parent, str(metadata.get("path") or relative))
        if _file_sha(artifact) != metadata.get("sha256"):
            raise RuntimeError(f"artifact hash mismatch: {artifact}")
    return pointer, manifest_path.parent, manifest


def _copy_generation(source: Path, destination: Path) -> bool:
    if destination.exists():
        if not destination.is_dir() or _file_sha(destination / "manifest.json") != _file_sha(source / "manifest.json"):
            raise RuntimeError(f"immutable generation conflict: {destination}")
        return True
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        shutil.rmtree(staging)
        shutil.copytree(source, staging, symlinks=True)
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return False


def _restore_pointer(path: Path, state: dict[str, Any] | None) -> None:
    if state is None:
        if path.exists():
            path.unlink()
        return
    _atomic_json(path, state["value"])


def publish(args: argparse.Namespace) -> int:
    if not args.confirm_publish:
        raise RuntimeError("publication requires --confirm-publish")
    if not RELEASE_ID_RE.fullmatch(args.release_id):
        raise RuntimeError("release-id must be lowercase kebab-case")
    source_graph = args.staged_graph.resolve()
    source_definitions = args.staged_definitions.resolve()
    target_graph = args.target_graph.resolve()
    target_definitions = args.target_definitions.resolve()
    record_dir = args.receipt_root.resolve() / args.release_id
    if (record_dir / "activation-receipt.json").exists():
        raise RuntimeError(f"release already activated: {args.release_id}")

    graph_pointer, graph_generation, graph_manifest = _verify_manifest_generation(source_graph)
    definition_checked = DefinitionProjectionStore(source_definitions).verify(
        expected_graph_generation=str(graph_manifest["generation_id"])
    )
    definition_pointer = _json(source_definitions / "CURRENT.json")
    definition_manifest_path = _safe_child(
        source_definitions, str(definition_pointer.get("manifest") or "")
    )
    definition_manifest = _json(definition_manifest_path)
    if definition_checked["invalid"] or definition_checked["multi_owner_ready_surfaces"]:
        raise RuntimeError("DefinitionProjection store is not safe to publish")

    graph_current = target_graph / "CURRENT.json"
    definition_current = target_definitions / "CURRENT.json"
    previous = {
        "legal_graph": _pointer_state(graph_current),
        "definition_projections": _pointer_state(definition_current),
    }
    plan = {
        "schema_version": "ontology-data-release-plan-v1",
        "release_id": args.release_id,
        "created_at": _now(),
        "actor": args.actor,
        "source": {
            "legal_graph": str(source_graph),
            "definition_projections": str(source_definitions),
        },
        "target": {
            "legal_graph": str(target_graph),
            "definition_projections": str(target_definitions),
        },
        "previous": previous,
        "next": {
            "legal_graph": {"sha256": _file_sha(source_graph / "CURRENT.json"), "value": graph_pointer},
            "definition_projections": {
                "sha256": _file_sha(source_definitions / "CURRENT.json"),
                "value": definition_pointer,
            },
        },
        "verification": {
            "graph_generation": graph_manifest["generation_id"],
            "graph_content_sha256": graph_manifest["content_sha256"],
            "definition_generation": definition_manifest["generation_id"],
            "definition_content_sha256": definition_manifest["content_sha256"],
            "definition_ready": definition_checked["ready"],
            "ambiguous_surfaces_withheld": definition_checked["ambiguous_surfaces_withheld"],
            "excluded_terms_withheld": definition_checked["excluded_terms_withheld"],
        },
    }
    plan["plan_sha256"] = _value_sha(plan)
    _write_once(record_dir / "plan.json", plan)

    graph_target_generation = target_graph / "generations" / str(graph_manifest["generation_id"])
    definition_target_generation = (
        target_definitions / "generations" / str(definition_manifest["generation_id"])
    )
    graph_reused = _copy_generation(graph_generation, graph_target_generation)
    definition_reused = _copy_generation(
        definition_manifest_path.parent, definition_target_generation
    )
    try:
        # This order is intentionally fail-closed: a new graph with an old/missing
        # definition pointer causes runtime fallback until the matching definition flips.
        _atomic_json(graph_current, graph_pointer)
        _atomic_json(definition_current, definition_pointer)
        published_graph = GraphSnapshot.open(target_graph)
        published_definition = DefinitionProjectionStore(target_definitions).verify(
            expected_graph_generation=str(published_graph.manifest["generation_id"])
        )
    except BaseException:
        _restore_pointer(graph_current, previous["legal_graph"])
        _restore_pointer(definition_current, previous["definition_projections"])
        raise

    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "release_id": args.release_id,
        "activated_at": _now(),
        "actor": args.actor,
        "approval_note": args.approval_note,
        "plan_path": str(record_dir / "plan.json"),
        "plan_file_sha256": _file_sha(record_dir / "plan.json"),
        "plan_sha256": plan["plan_sha256"],
        "previous": previous,
        "active": {
            "legal_graph": _pointer_state(graph_current),
            "definition_projections": _pointer_state(definition_current),
        },
        "generation_copy": {
            "legal_graph_reused": graph_reused,
            "definition_projections_reused": definition_reused,
        },
        "verification": {
            "source_graph_generation": published_definition["source_graph_generation"],
            "definition_generation": published_definition["generation_id"],
            "ready": published_definition["ready"],
            "invalid": published_definition["invalid"],
            "multi_owner_ready_surfaces": published_definition["multi_owner_ready_surfaces"],
        },
    }
    receipt["receipt_sha256"] = _value_sha(receipt)
    receipt_file_sha = _write_once(record_dir / "activation-receipt.json", receipt)
    print(json.dumps({
        "release_id": args.release_id,
        "graph_generation": published_graph.manifest["generation_id"],
        "definition_generation": published_definition["generation_id"],
        "ready": published_definition["ready"],
        "receipt": str(record_dir / "activation-receipt.json"),
        "receipt_file_sha256": receipt_file_sha,
    }, ensure_ascii=False, indent=2))
    return 0


def rollback(args: argparse.Namespace) -> int:
    if not args.confirm_rollback:
        raise RuntimeError("rollback requires --confirm-rollback")
    if not RELEASE_ID_RE.fullmatch(args.release_id):
        raise RuntimeError("release-id must be lowercase kebab-case")
    record_dir = args.receipt_root.resolve() / args.release_id
    activation_path = record_dir / "activation-receipt.json"
    activation = _json(activation_path)
    if activation.get("schema_version") != RECEIPT_SCHEMA:
        raise RuntimeError("invalid activation receipt")
    rollback_path = record_dir / "rollback-receipt.json"
    if rollback_path.exists():
        raise RuntimeError(f"release already rolled back: {args.release_id}")
    target_graph = args.target_graph.resolve() / "CURRENT.json"
    target_definitions = args.target_definitions.resolve() / "CURRENT.json"
    current = {
        "legal_graph": _pointer_state(target_graph),
        "definition_projections": _pointer_state(target_definitions),
    }
    if current != activation.get("active"):
        raise RuntimeError("current ontology pointers no longer match this activation")
    _restore_pointer(target_graph, activation["previous"]["legal_graph"])
    _restore_pointer(target_definitions, activation["previous"]["definition_projections"])
    receipt = {
        "schema_version": ROLLBACK_SCHEMA,
        "release_id": args.release_id,
        "rolled_back_at": _now(),
        "actor": args.actor,
        "activation_receipt_path": str(activation_path),
        "activation_receipt_sha256": _file_sha(activation_path),
        "from": current,
        "to": {
            "legal_graph": _pointer_state(target_graph),
            "definition_projections": _pointer_state(target_definitions),
        },
    }
    receipt["receipt_sha256"] = _value_sha(receipt)
    _write_once(rollback_path, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--release-id", required=True)
    common.add_argument("--actor", required=True)
    common.add_argument(
        "--receipt-root", type=Path,
        default=ROOT / "01_DATA/ops/ontology_releases",
    )
    common.add_argument(
        "--target-graph", type=Path, default=ROOT / "01_DATA/legal_graph"
    )
    common.add_argument(
        "--target-definitions", type=Path,
        default=ROOT / "01_DATA/PROJECTIONS/DEFINITIONS",
    )
    publish_parser = sub.add_parser("publish", parents=[common])
    publish_parser.add_argument("--staged-graph", required=True, type=Path)
    publish_parser.add_argument("--staged-definitions", required=True, type=Path)
    publish_parser.add_argument("--approval-note", required=True)
    publish_parser.add_argument("--confirm-publish", action="store_true")
    rollback_parser = sub.add_parser("rollback", parents=[common])
    rollback_parser.add_argument("--confirm-rollback", action="store_true")
    args = parser.parse_args()
    return publish(args) if args.command == "publish" else rollback(args)


if __name__ == "__main__":
    raise SystemExit(main())
