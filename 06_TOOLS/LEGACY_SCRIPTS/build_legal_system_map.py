#!/usr/bin/env python3
"""Deterministically check or atomically refresh the legal-system catalog.

The four issue-family rows remain human-maintained seeds.  The CLI regenerates
only the closed corpus inventory, profile/effective-date fingerprints and
current Legal Graph snapshot metadata.  It never calls an LLM.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core.rag.index import Index
from lawrag.core.rag.legal_research_atlas import LegalResearchAtlas
from lawrag.core.rag.legal_system_map import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_LAW_INDEX_PATH,
    DEFAULT_LEGAL_GRAPH_ROOT,
    build_legal_system_catalog_snapshot,
    legal_system_catalog_diff,
    load_legal_system_map,
)


DEFAULT_RECEIPT_PATH = (
    ROOT / "01_DATA" / "legal_system" / "catalog-update-receipts.jsonl"
)


def _read_object(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def _catalog_bytes(value: dict) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _write_temp(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temp, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return temp


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _append_receipt(path: Path, receipt: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    with os.fdopen(descriptor, "ab") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _atlas() -> LegalResearchAtlas:
    index = Index.load(
        store=ROOT / "01_DATA" / "structure",
        terms_file=ROOT / "01_DATA" / "glossary.json",
        links_file=ROOT / "01_DATA" / "links.json",
    )
    return LegalResearchAtlas.from_index(index)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--law-index", type=Path, default=DEFAULT_LAW_INDEX_PATH)
    parser.add_argument("--legal-graph-root", type=Path, default=DEFAULT_LEGAL_GRAPH_ROOT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    parser.add_argument(
        "--catalog-version",
        help="required for --write when generated data changed; must differ from old version",
    )
    args = parser.parse_args()

    catalog_path = args.catalog.resolve()
    seed, before_file_sha = _read_object(catalog_path)
    atlas = _atlas()
    generated_without_version_bump = build_legal_system_catalog_snapshot(
        atlas,
        seed,
        catalog_version=str(seed.get("catalog_version") or ""),
        law_index_path=args.law_index.resolve(),
        legal_graph_root=args.legal_graph_root.resolve(),
    )
    data_diff = legal_system_catalog_diff(seed, generated_without_version_bump)

    if args.check:
        receipt = {
            "schema_version": "legal-system-catalog-update-receipt-v1",
            "mode": "check",
            "catalog": str(catalog_path),
            "catalog_file_sha256": before_file_sha,
            "catalog_version": str(seed.get("catalog_version") or ""),
            "authority_generation": str(
                generated_without_version_bump.get("authority_generation") or ""
            ),
            "diff": data_diff,
        }
        if not data_diff["changed"]:
            load_legal_system_map(
                atlas,
                catalog_path=catalog_path,
                law_index_path=args.law_index.resolve(),
                legal_graph_root=args.legal_graph_root.resolve(),
            )
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
        return 1 if data_diff["changed"] else 0

    old_version = str(seed.get("catalog_version") or "")
    if data_diff["changed"] and (
        not args.catalog_version or args.catalog_version == old_version
    ):
        parser.error(
            "generated catalog data changed; --catalog-version must name a new version"
        )
    candidate = build_legal_system_catalog_snapshot(
        atlas,
        seed,
        catalog_version=args.catalog_version or old_version,
        law_index_path=args.law_index.resolve(),
        legal_graph_root=args.legal_graph_root.resolve(),
    )
    diff = legal_system_catalog_diff(seed, candidate)
    if not diff["changed"]:
        load_legal_system_map(
            atlas,
            catalog_path=catalog_path,
            law_index_path=args.law_index.resolve(),
            legal_graph_root=args.legal_graph_root.resolve(),
        )
        print(json.dumps({
            "schema_version": "legal-system-catalog-update-receipt-v1",
            "mode": "write",
            "status": "unchanged",
            "catalog": str(catalog_path),
            "catalog_file_sha256": before_file_sha,
            "diff": diff,
        }, ensure_ascii=False, sort_keys=True, indent=2))
        return 0

    payload = _catalog_bytes(candidate)
    temp = _write_temp(catalog_path, payload)
    try:
        # Validate the exact bytes that will become current before replacement.
        load_legal_system_map(
            atlas,
            catalog_path=temp,
            law_index_path=args.law_index.resolve(),
            legal_graph_root=args.legal_graph_root.resolve(),
        )
        os.replace(temp, catalog_path)
        _fsync_directory(catalog_path.parent)
    finally:
        temp.unlink(missing_ok=True)
    after_file_sha = hashlib.sha256(payload).hexdigest()
    receipt = {
        "schema_version": "legal-system-catalog-update-receipt-v1",
        "mode": "write",
        "status": "updated",
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "catalog": str(catalog_path),
        "receipt_path": str(args.receipt.resolve()),
        "before_catalog_file_sha256": before_file_sha,
        "after_catalog_file_sha256": after_file_sha,
        "before_catalog_version": old_version,
        "after_catalog_version": str(candidate.get("catalog_version") or ""),
        "authority_generation": str(candidate.get("authority_generation") or ""),
        "authority_as_of": str(candidate.get("authority_as_of") or ""),
        "diff": diff,
    }
    _append_receipt(args.receipt.resolve(), receipt)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
