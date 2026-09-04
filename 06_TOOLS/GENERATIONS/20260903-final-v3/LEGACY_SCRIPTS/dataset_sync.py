#!/usr/bin/env python3
"""Build verifiable internal/external dataset ZIP sets with logical overlays."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES = ROOT / "config" / "dataset_sync" / "profiles.json"
BUNDLE_MANIFEST = "BUNDLE_MANIFEST.json"
SET_MANIFEST = "SYNC_SET.json"
BLOCKED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache"}
BLOCKED_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
KNOWN_OVERLAY_ROLES = {"primary", "structure", "frame", "taxonomy"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _canonical(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe repository-relative path: {raw}")
    if any(part in BLOCKED_PARTS for part in path.parts):
        raise ValueError(f"blocked path: {raw}")
    if path.name in {".env", ".env.local"} or path.suffix.lower() in BLOCKED_SUFFIXES:
        raise ValueError(f"secret-like path is forbidden: {raw}")
    return path


def _expand(root: Path, source: str, target: str | None = None) -> list[dict]:
    source_rel = _safe_relative(source)
    target_rel = _safe_relative(target or source)
    source_path = root / source_rel
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if source_path.is_symlink():
        raise ValueError(f"symlink source is forbidden: {source_rel}")
    if source_path.is_file():
        paths = [source_path]
    else:
        paths = sorted(path for path in source_path.rglob("*") if path.is_file())
    rows = []
    for path in paths:
        if path.is_symlink():
            raise ValueError(f"symlink source is forbidden: {path}")
        suffix = path.relative_to(source_path) if source_path.is_dir() else Path()
        archive = PurePosixPath(target_rel.as_posix(), suffix.as_posix())
        _safe_relative(archive.as_posix())
        rows.append({"source_path": path, "path": archive.as_posix()})
    return rows


def _matches(path: str, patterns: list[str]) -> bool:
    pure = PurePosixPath(path)
    return any(pure.match(pattern) for pattern in patterns)


def load_overlay(path: Path, *, require_files: bool = True, root: Path = ROOT) -> dict:
    value = _json(path)
    if value.get("schema_version") != "dataset-overlay-v1":
        raise ValueError(f"unsupported overlay schema: {path}")
    if value.get("representation") not in {"real", "mock"}:
        raise ValueError("overlay representation must be real or mock")
    logical_ids = [str(row.get("logical_id") or "") for row in value.get("items") or []]
    if not logical_ids or len(logical_ids) != len(set(logical_ids)) or "" in logical_ids:
        raise ValueError("overlay logical_id values must be non-empty and unique")
    for item in value["items"]:
        contract = item.get("contract") or {}
        if set(contract) != {
            "kind", "format_family", "version_role", "artifact_roles"
        }:
            raise ValueError(f"incomplete contract: {item['logical_id']}")
        roles = {str(row.get("role") or "") for row in item.get("files") or []}
        expected_roles = set(contract.get("artifact_roles") or [])
        if (
            roles != expected_roles
            or not {"primary", "structure"}.issubset(roles)
            or not roles.issubset(KNOWN_OVERLAY_ROLES)
        ):
            raise ValueError(
                f"overlay roles must match contract artifact_roles: "
                f"{item['logical_id']}"
            )
        for row in item["files"]:
            _safe_relative(str(row.get("source") or ""))
            _safe_relative(str(row.get("target") or ""))
            if require_files:
                _expand(root, row["source"], row["target"])
    return value


def overlay_contract(overlay: dict) -> dict:
    items = [
        {"logical_id": row["logical_id"], "contract": row["contract"]}
        for row in overlay["items"]
    ]
    value = {"schema_version": "dataset-overlay-contract-v1", "items": items}
    value["contract_sha256"] = _sha_bytes(_canonical(value))
    return value


def check_overlay_pair(left: dict, right: dict) -> dict:
    left_contract, right_contract = overlay_contract(left), overlay_contract(right)
    if left_contract != right_contract:
        raise ValueError("internal and external overlays have different logical contracts")
    if {left.get("representation"), right.get("representation")} != {"real", "mock"}:
        raise ValueError("overlay pair must contain exactly one real and one mock representation")
    return left_contract


def _overlay_entries(overlay: dict, root: Path) -> list[dict]:
    entries = []
    active_items = []
    for item in overlay["items"]:
        item_files = []
        for spec in item["files"]:
            expanded = _expand(root, spec["source"], spec["target"])
            for row in expanded:
                row.update({"logical_id": item["logical_id"], "role": spec["role"]})
                entries.append(row)
                item_files.append({"path": row["path"], "role": spec["role"]})
        active_items.append({
            "logical_id": item["logical_id"],
            "contract": item["contract"],
            "representation": overlay["representation"],
            "doc_id": item.get("doc_id"),
            "files": item_files,
        })
    active = {
        "schema_version": "active-dataset-overlay-v1",
        "overlay_id": overlay["overlay_id"],
        "representation": overlay["representation"],
        "contract_sha256": overlay_contract(overlay)["contract_sha256"],
        "items": active_items,
    }
    entries.append({
        "path": "data/sync/ACTIVE_DATASET.json",
        "payload": json.dumps(active, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
        "logical_id": "overlay-active-manifest",
        "role": "manifest",
    })
    return entries


def _excluded_overlay_paths(overlays: list[dict], root: Path) -> set[str]:
    paths = set()
    for overlay in overlays:
        for item in overlay["items"]:
            for spec in item["files"]:
                try:
                    expanded = _expand(root, spec["source"], spec["target"])
                except FileNotFoundError:
                    continue
                paths.update(row["path"] for row in expanded)
    return paths


def profile_entries(
    profile_name: str,
    profiles: dict,
    *,
    root: Path = ROOT,
    excluded_overlays: list[dict] | None = None,
) -> list[dict]:
    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        raise ValueError(f"unknown profile: {profile_name}")
    excluded_paths = _excluded_overlay_paths(excluded_overlays or [], root)
    rows = []
    for source in profile.get("include") or []:
        rows.extend(_expand(root, source))
    patterns = [str(value) for value in profile.get("exclude_globs") or []]
    unique = {}
    for row in rows:
        if row["path"] in excluded_paths or _matches(row["path"], patterns):
            continue
        if row["path"] in unique:
            raise ValueError(f"duplicate archive target: {row['path']}")
        unique[row["path"]] = row
    return [unique[path] for path in sorted(unique)]


def _materialize(entries: list[dict]) -> tuple[list[dict], dict[str, bytes | Path]]:
    rows, payloads = [], {}
    for entry in entries:
        path = entry["path"]
        if path in payloads:
            raise ValueError(f"duplicate archive target: {path}")
        if "payload" in entry:
            raw = entry["payload"]
            size, digest, payload = len(raw), _sha_bytes(raw), raw
        else:
            source = entry["source_path"]
            size, digest, payload = source.stat().st_size, _sha_file(source), source
        row = {"path": path, "bytes": size, "sha256": digest}
        for key in ("logical_id", "role"):
            if entry.get(key) is not None:
                row[key] = entry[key]
        rows.append(row)
        payloads[path] = payload
    return rows, payloads


def bundle_manifest(bundle_id: str, classification: str, entries: list[dict]) -> tuple[dict, dict]:
    rows, payloads = _materialize(entries)
    identity = {
        "schema_version": "dataset-bundle-content-v1",
        "bundle_id": bundle_id,
        "classification": classification,
        "files": rows,
    }
    manifest = dict(identity)
    manifest["content_sha256"] = _sha_bytes(_canonical(identity))
    manifest["file_count"] = len(rows)
    manifest["bytes"] = sum(row["bytes"] for row in rows)
    return manifest, payloads


def pack_bundle(
    output: Path,
    bundle_id: str,
    classification: str,
    entries: list[dict],
    *,
    max_mb: int,
) -> dict:
    manifest, payloads = bundle_manifest(bundle_id, classification, entries)
    limit = max_mb * 1024 * 1024
    payload_limit = limit - 1024 * 1024
    if payload_limit <= 0:
        raise ValueError("shard size must be at least 2MB")
    groups: list[list[dict]] = []
    current, size = [], 0
    for row in manifest["files"]:
        if row["bytes"] > payload_limit:
            raise ValueError(f"file exceeds shard limit {max_mb}MB: {row['path']}")
        if current and size + row["bytes"] > payload_limit:
            groups.append(current)
            current, size = [], 0
        current.append(row)
        size += row["bytes"]
    if current:
        groups.append(current)
    output.mkdir(parents=True, exist_ok=False)
    manifest["created_at"] = _now()
    manifest["shards"] = []
    total = len(groups)
    for number, group in enumerate(groups, 1):
        name = f"{bundle_id}.p{number:02d}-of-{total:02d}.zip"
        target = output / name
        shard_manifest = {
            "schema_version": "dataset-bundle-shard-v1",
            "bundle_id": bundle_id,
            "content_sha256": manifest["content_sha256"],
            "shard": {"number": number, "total": total},
            "files": group,
        }
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for row in group:
                payload = payloads[row["path"]]
                if isinstance(payload, Path):
                    archive.write(payload, row["path"])
                else:
                    archive.writestr(row["path"], payload)
            archive.writestr(
                BUNDLE_MANIFEST,
                json.dumps(shard_manifest, ensure_ascii=False, indent=2) + "\n",
            )
        if target.stat().st_size > limit:
            raise ValueError(f"compressed shard exceeds {max_mb}MB: {target}")
        manifest["shards"].append({
            "file": name,
            "bytes": target.stat().st_size,
            "sha256": _sha_file(target),
            "file_count": len(group),
        })
    (output / "bundle.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    return manifest


def verify_bundle(directory: Path) -> dict:
    manifest_path = directory / "bundle.manifest.json"
    manifest = _json(manifest_path)
    expected_files = {row["path"]: row for row in manifest["files"]}
    observed = set()
    for shard in manifest["shards"]:
        path = directory / shard["file"]
        if _sha_file(path) != shard["sha256"] or path.stat().st_size != shard["bytes"]:
            raise ValueError(f"shard hash or size mismatch: {path}")
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or BUNDLE_MANIFEST not in names:
                raise ValueError(f"invalid shard member list: {path}")
            embedded = json.loads(archive.read(BUNDLE_MANIFEST))
            if (
                embedded.get("schema_version") != "dataset-bundle-shard-v1"
                or embedded.get("bundle_id") != manifest["bundle_id"]
                or embedded.get("content_sha256") != manifest["content_sha256"]
                or {row["path"] for row in embedded.get("files") or []}
                != set(names) - {BUNDLE_MANIFEST}
            ):
                raise ValueError(f"embedded shard manifest mismatch: {path}")
            for name in names:
                if name == BUNDLE_MANIFEST:
                    continue
                _safe_relative(name)
                row = expected_files.get(name)
                if row is None:
                    raise ValueError(f"unexpected shard member: {name}")
                raw = archive.read(name)
                if len(raw) != row["bytes"] or _sha_bytes(raw) != row["sha256"]:
                    raise ValueError(f"payload mismatch: {name}")
                if name in observed:
                    raise ValueError(f"payload repeated across shards: {name}")
                observed.add(name)
    if observed != set(expected_files):
        raise ValueError("bundle payload set does not match manifest")
    return manifest


def pack_set(
    output: Path,
    environment: str,
    *,
    profiles_path: Path = DEFAULT_PROFILES,
    overlay_path: Path | None = None,
    max_mb: int = 35,
    root: Path = ROOT,
) -> dict:
    profiles = _json(profiles_path)
    external_path = root / profiles["external_overlay"]
    external = load_overlay(external_path, root=root)
    if environment == "external":
        if overlay_path is not None:
            raise ValueError("external environment always uses the locked mock overlay")
        overlay = external
    elif environment == "internal":
        if overlay_path is None:
            raise ValueError("internal environment requires --overlay-manifest")
        overlay = load_overlay(overlay_path, root=root)
        if overlay.get("representation") != "real" or overlay.get("export_allowed") is not False:
            raise ValueError("internal overlay must be real and export_allowed=false")
        check_overlay_pair(external, overlay)
    else:
        raise ValueError("environment must be internal or external")
    if output.exists():
        raise FileExistsError(output)
    partial = output.with_name(output.name + ".part")
    if partial.exists():
        raise FileExistsError(partial)
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.mkdir()
    bundle_specs = []
    exclusions = [external, overlay]
    for name in ("common-runtime", "common-evaluation"):
        entries = profile_entries(name, profiles, root=root, excluded_overlays=exclusions)
        bundle_specs.append((name, profiles[name]["classification"], entries))
    bundle_specs.append((
        f"overlay-{overlay['representation']}",
        "restricted-real" if environment == "internal" else "synthetic-mock",
        _overlay_entries(overlay, root),
    ))
    bundles = []
    targets = set()
    for bundle_id, classification, entries in bundle_specs:
        overlap = targets & {row["path"] for row in entries}
        if overlap:
            raise ValueError("bundle target overlap: " + ", ".join(sorted(overlap)[:5]))
        targets.update(row["path"] for row in entries)
        manifest = pack_bundle(
            partial / bundle_id, bundle_id, classification, entries, max_mb=max_mb
        )
        bundles.append({
            "bundle_id": bundle_id,
            "classification": classification,
            "content_sha256": manifest["content_sha256"],
            "manifest": f"{bundle_id}/bundle.manifest.json",
        })
    contract = overlay_contract(overlay)
    sync_set = {
        "schema_version": "dataset-sync-set-v1",
        "created_at": _now(),
        "environment": environment,
        "overlay_representation": overlay["representation"],
        "overlay_contract_sha256": contract["contract_sha256"],
        "bundles": bundles,
        "invariants": {
            "common_bundle_hashes_must_match": True,
            "overlay_contract_must_match": True,
            "overlay_payload_hashes_may_differ": True,
            "vectors_included": False,
        },
    }
    set_path = partial / SET_MANIFEST
    set_path.write_text(
        json.dumps(sync_set, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    (partial / f"{SET_MANIFEST}.sha256").write_text(
        _sha_file(set_path) + "  " + SET_MANIFEST + "\n", "utf-8"
    )
    partial.rename(output)
    return sync_set


def verify_set(directory: Path) -> dict:
    set_path = directory / SET_MANIFEST
    checksum_path = directory / f"{SET_MANIFEST}.sha256"
    expected_checksum = checksum_path.read_text("utf-8").split()[0]
    if _sha_file(set_path) != expected_checksum:
        raise ValueError("SYNC_SET.json checksum mismatch")
    value = _json(set_path)
    targets = set()
    for bundle in value["bundles"]:
        manifest = verify_bundle(directory / bundle["bundle_id"])
        if manifest["content_sha256"] != bundle["content_sha256"]:
            raise ValueError(f"bundle content identity mismatch: {bundle['bundle_id']}")
        overlap = targets & {row["path"] for row in manifest["files"]}
        if overlap:
            raise ValueError("sync set contains overlapping targets")
        targets.update(row["path"] for row in manifest["files"])
    return value


def compare_sets(left_dir: Path, right_dir: Path) -> dict:
    left, right = verify_set(left_dir), verify_set(right_dir)
    if left["overlay_contract_sha256"] != right["overlay_contract_sha256"]:
        raise ValueError("overlay logical contracts differ")
    def common(value):
        return {
            row["bundle_id"]: row["content_sha256"] for row in value["bundles"]
            if row["bundle_id"].startswith("common-")
        }
    if common(left) != common(right):
        raise ValueError("common runtime/evaluation bundle hashes differ")
    if {left["environment"], right["environment"]} != {"internal", "external"}:
        raise ValueError("comparison requires one internal and one external set")
    return {
        "status": "compatible",
        "common": common(left),
        "overlay_contract_sha256": left["overlay_contract_sha256"],
    }


def unpack_set(directory: Path, destination: Path, *, replace: bool, dry_run: bool) -> None:
    verify_set(directory)
    manifests = [
        _json(directory / row["manifest"])
        for row in _json(directory / SET_MANIFEST)["bundles"]
    ]
    paths = [row["path"] for manifest in manifests for row in manifest["files"]]
    existing = [path for path in paths if (destination / path).exists()]
    if existing and not replace and not dry_run:
        raise ValueError(
            f"{len(existing)} targets already exist; use --replace or --dry-run"
        )
    if dry_run:
        print(json.dumps({"files": len(paths), "existing": len(existing)}, indent=2))
        return
    backup = destination / ".dataset_sync_backup" / _now().replace(":", "")
    for bundle in _json(directory / SET_MANIFEST)["bundles"]:
        bundle_dir = directory / bundle["bundle_id"]
        for shard in _json(bundle_dir / "bundle.manifest.json")["shards"]:
            with zipfile.ZipFile(bundle_dir / shard["file"]) as archive:
                for name in archive.namelist():
                    if name == BUNDLE_MANIFEST:
                        continue
                    relative = _safe_relative(name)
                    target = destination / relative
                    if target.exists() and replace:
                        saved = backup / relative
                        saved.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, saved)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
    receipt = destination / "data" / "sync" / SET_MANIFEST
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_bytes((directory / SET_MANIFEST).read_bytes())


def _summary(entries: list[dict]) -> dict:
    manifest, _ = bundle_manifest("preview", "preview", entries)
    return {"files": manifest["file_count"], "bytes": manifest["bytes"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--environment", choices=("internal", "external"), required=True)
    listing.add_argument("--overlay-manifest", type=Path)
    pack = sub.add_parser("pack")
    pack.add_argument("--environment", choices=("internal", "external"), required=True)
    pack.add_argument("--overlay-manifest", type=Path)
    pack.add_argument("--out", type=Path, required=True)
    pack.add_argument("--size", type=int, default=35)
    verify = sub.add_parser("verify")
    verify.add_argument("directory", type=Path)
    compare = sub.add_parser("compare")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("directory", type=Path)
    unpack.add_argument("--root", type=Path, required=True)
    unpack.add_argument("--replace", action="store_true")
    unpack.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            value = pack_set(
                args.out.resolve(), args.environment,
                overlay_path=args.overlay_manifest.resolve() if args.overlay_manifest else None,
                max_mb=args.size,
            )
            print(json.dumps(value, ensure_ascii=False, indent=2))
            print(f"SYNC_SET SHA256: {_sha_file(args.out.resolve() / SET_MANIFEST)}")
        elif args.command == "verify":
            print(json.dumps(verify_set(args.directory.resolve()), ensure_ascii=False, indent=2))
        elif args.command == "compare":
            print(json.dumps(compare_sets(args.left.resolve(), args.right.resolve()), indent=2))
        elif args.command == "unpack":
            unpack_set(
                args.directory.resolve(), args.root.resolve(),
                replace=args.replace, dry_run=args.dry_run,
            )
        else:
            profiles = _json(DEFAULT_PROFILES)
            external = load_overlay(ROOT / profiles["external_overlay"])
            if args.environment == "external":
                overlay = external
            else:
                if args.overlay_manifest is None:
                    raise ValueError("internal list requires --overlay-manifest")
                overlay = load_overlay(args.overlay_manifest.resolve())
                check_overlay_pair(external, overlay)
            result = {}
            for name in ("common-runtime", "common-evaluation"):
                result[name] = _summary(profile_entries(
                    name, profiles, excluded_overlays=[external, overlay]
                ))
            result[f"overlay-{overlay['representation']}"] = _summary(
                _overlay_entries(overlay, ROOT)
            )
            result["overlay_contract_sha256"] = overlay_contract(overlay)[
                "contract_sha256"
            ]
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
