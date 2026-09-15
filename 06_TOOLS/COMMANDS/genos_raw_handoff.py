#!/usr/bin/env python3
"""Build and verify the flat GENOS code + external-public raw handoff."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
SOURCE_SET = (
    ROOT / "01_DATA/SOURCE_SETS/external-public-v1"
    / "sourceset-489b3bcff1cf01fb0f5a97a4.json"
)
SOURCE_LOCK = SOURCE_SET.with_name(SOURCE_SET.stem + ".lock.json")
PACKAGES = ROOT / "01_DATA/PACKAGES/EXTERNAL"
MANIFEST = "GENOS_HANDOFF_MANIFEST.json"
DEFAULT_PART_BYTES = 8_000_000
EXPECTED_PACKAGES = frozenset(
    {
        "source-expc-95be582c307663b0",
        "source-fsc-3af218f11d7a2d5f",
        "source-kofia-85542fe8150a1be2",
        "source-krx-e6ef2a9a5355335d",
        "source-law-267b1cfc7bfd3349",
        "source-moleg-e309c3f3f9ee6a7f",
        "source-prec-3aa01fa14582b5e0",
    }
)


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _code_files() -> list[Path]:
    path = ROOT / "06_TOOLS/COMMANDS/code_ship.py"
    spec = importlib.util.spec_from_file_location("genos_code_ship", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module._files()


def _package_files() -> list[Path]:
    declaration = json.loads(SOURCE_SET.read_text(encoding="utf-8"))
    package_ids = {str(row["package_id"]) for row in declaration["members"]}
    if package_ids != EXPECTED_PACKAGES:
        raise RuntimeError("external-public SourceSet member list changed")
    backend = ROOT / "02_BACKEND"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from lawrag.datasets.catalog import load_package, load_source_set, load_source_set_lock

    packages = []
    paths = [SOURCE_SET, SOURCE_LOCK]
    for package_id in sorted(package_ids):
        manifests = sorted((PACKAGES / package_id).glob("gen-*/manifest.json"))
        if len(manifests) != 1:
            raise RuntimeError(f"one package generation required: {package_id}")
        package = load_package(manifests[0], verify_files=True)
        if (
            package.source_origin != "public_external"
            or package.security_class != "public"
            or package.representation != "real"
            or package.authority != "authoritative"
            or package.capabilities != ("raw",)
            or not package.export_allowed
            or any(row.role != "raw" for row in package.artifacts)
        ):
            raise RuntimeError(f"not an authoritative public raw package: {package_id}")
        packages.append(package)
        paths.extend(path for path in manifests[0].parent.rglob("*") if path.is_file())
    view = load_source_set(SOURCE_SET, packages)
    lock = load_source_set_lock(SOURCE_LOCK)
    if lock.source_set_sha256 != view.source_set_sha256:
        raise RuntimeError("SourceSet lock does not match selected packages")
    return paths


def _payloads() -> dict[str, bytes]:
    rows: dict[str, bytes] = {}
    for path in [*_code_files(), *_package_files()]:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"non-regular handoff input: {path}")
        relative = path.relative_to(ROOT).as_posix()
        rows[relative] = path.read_bytes()
    return rows


def _forbidden(name: str) -> bool:
    pure = PurePosixPath(name)
    lowered = tuple(part.lower() for part in pure.parts)
    if pure.suffix.lower() == ".js":
        return True
    if pure.name in {".env", ".env.local", "structured-prellm.sqlite", "queue.sqlite"}:
        return True
    if any(part in {".git", ".venv"} for part in lowered):
        return True
    if name.startswith("01_DATA/PACKAGES/"):
        return any(part.startswith("source-internal-") or part.startswith("ontology-") for part in lowered)
    return any(
        name.startswith(prefix)
        for prefix in (
            "01_DATA/SEMANTIC/",
            "01_DATA/INBOX/",
            "01_DATA/ACTIVE/",
            "01_DATA/INDEXES/",
            "01_DATA/PROJECTIONS/",
            "04_EXPERIMENTS/",
            "09_ARTIFACTS/",
            "90_RUNTIME/",
            "99_ARCHIVE/",
        )
    )


def verify(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or MANIFEST not in names:
            raise RuntimeError("handoff ZIP has duplicate paths or no manifest")
        for name in names:
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts or _forbidden(name):
                raise RuntimeError(f"forbidden handoff path: {name}")
        manifest = json.loads(archive.read(MANIFEST))
        expected = {row["path"]: row for row in manifest["files"]}
        if set(names) - {MANIFEST} != set(expected):
            raise RuntimeError("handoff manifest/file set mismatch")
        for name, row in expected.items():
            raw = archive.read(name)
            if len(raw) != row["bytes"] or _sha_bytes(raw) != row["sha256"]:
                raise RuntimeError(f"handoff file hash mismatch: {name}")
        package_manifests = {
            PurePosixPath(name).parts[3]
            for name in names
            if name.startswith("01_DATA/PACKAGES/EXTERNAL/")
            and name.endswith("/manifest.json")
        }
        if package_manifests != EXPECTED_PACKAGES:
            raise RuntimeError("handoff package set mismatch")
    return {
        "ok": True,
        "archive": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": _sha_file(path),
        "files": len(expected),
        "packages": len(package_manifests),
    }


def pack(output: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise RuntimeError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    payloads = _payloads()
    manifest = {
        "schema_version": "genos-unified-raw-handoff-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "install_root": "/home/genos/DEV",
        "pipeline": "lawrag.common-batch-v1",
        "external_source_set": SOURCE_SET.relative_to(ROOT).as_posix(),
        "internal_input": "GenOS upload at deployment time; no internal example included",
        "historical_llm_outputs_included": False,
        "files": [
            {"path": name, "bytes": len(raw), "sha256": _sha_bytes(raw)}
            for name, raw in sorted(payloads.items())
        ],
    }
    partial = output.with_suffix(output.suffix + ".partial")
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, raw in sorted(payloads.items()):
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.external_attr = (0o100644 << 16)
                archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            archive.writestr(
                MANIFEST,
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
        os.replace(partial, output)
    finally:
        partial.unlink(missing_ok=True)
    return verify(output)


def split(path: Path, output: Path, part_bytes: int = DEFAULT_PART_BYTES) -> dict:
    if not 1 <= part_bytes <= 9_000_000:
        raise ValueError("part size must be between 1 and 9,000,000 bytes")
    receipt = verify(path.resolve())
    output = output.resolve()
    if output.exists():
        raise RuntimeError(f"parts directory already exists: {output}")
    output.mkdir(parents=True)
    parts = []
    with path.open("rb") as stream:
        number = 1
        while raw := stream.read(part_bytes):
            name = f"{path.name}.part{number:03d}"
            target = output / name
            target.write_bytes(raw)
            parts.append({"name": name, "bytes": len(raw), "sha256": _sha_bytes(raw)})
            number += 1
    manifest = {
        "schema_version": "split-archive-v1",
        "archive": path.name,
        "archive_bytes": receipt["bytes"],
        "archive_sha256": receipt["sha256"],
        "part_max_bytes": part_bytes,
        "parts": parts,
    }
    (output / "parts-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for name in ("genos_install.sh", "genos_git_publish.sh"):
        shutil.copy2(ROOT / name, output / name)
        shutil.copy2(ROOT / name, output / f"{name}.txt")
    return {**receipt, "parts_dir": str(output), "part_count": len(parts), "parts": parts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("pack")
    make.add_argument("--out", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("zip", type=Path)
    pieces = sub.add_parser("split")
    pieces.add_argument("zip", type=Path)
    pieces.add_argument("--out", type=Path, required=True)
    pieces.add_argument("--part-bytes", type=int, default=DEFAULT_PART_BYTES)
    args = parser.parse_args()
    try:
        if args.command == "pack":
            result = pack(args.out)
        elif args.command == "verify":
            result = verify(args.zip.resolve())
        else:
            result = split(args.zip.resolve(), args.out, args.part_bytes)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
