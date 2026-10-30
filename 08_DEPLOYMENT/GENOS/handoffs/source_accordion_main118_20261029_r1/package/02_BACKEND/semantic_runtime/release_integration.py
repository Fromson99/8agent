"""Fail-closed comparison of a proposed local RAG release with its active parent.

The integration declaration is part of the hash-pinned validation receipt.  It
names every changed release file; an ADR candidate additionally binds the
changed source files to one frozen revision and their original MAIN hashes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "local-release-integration-v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_sha(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _inside(root: Path, raw: str) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw or ".." in Path(raw).parts:
        raise ValueError(f"invalid integration path: {raw}")
    path = (root / raw).resolve()
    if Path(raw).is_absolute() or path == root or not path.is_relative_to(root):
        raise ValueError(f"integration path escapes workspace: {raw}")
    return path


def _candidate_files(root: Path, declaration: dict[str, Any]) -> dict[str, tuple[str | None, str]]:
    candidate = declaration.get("candidate")
    if candidate is None:
        return {}
    if not isinstance(candidate, dict) or set(candidate) != {
        "manifest_path", "manifest_sha256", "revision_id", "revision_sha256"
    }:
        raise ValueError("integration candidate binding is incomplete")
    path = _inside(root, candidate["manifest_path"])
    research = (root / "02_BACKEND/lawrag/research/candidates").resolve()
    if not path.is_relative_to(research) or path.name != "candidate.json":
        raise ValueError("integration candidate must be an ADR candidate manifest")
    if _sha(path) != candidate["manifest_sha256"]:
        raise ValueError("integration candidate manifest changed")
    manifest = json.loads(path.read_text("utf-8"))
    if (manifest.get("schema_version") != "adr-code-candidate-v2" or
            manifest.get("status") != "research-only" or
            manifest.get("production_loadable") is not False):
        raise ValueError("integration candidate must be a frozen research candidate")
    revisions = [r for r in manifest.get("revisions", []) if r.get("revision_id") == candidate["revision_id"]]
    if len(revisions) != 1 or revisions[0].get("revision_sha256") != candidate["revision_sha256"]:
        raise ValueError("integration candidate revision changed or is missing")
    revision = revisions[0]
    if _record_sha({key: value for key, value in revision.items() if key != "revision_sha256"}) != revision["revision_sha256"]:
        raise ValueError("integration candidate revision seal is invalid")
    frozen = {r.get("snapshot_path"): r for r in revision.get("files", [])}
    result: dict[str, tuple[str | None, str]] = {}
    for row in manifest.get("files", []):
        target = row.get("target_path")
        record = frozen.get(row.get("snapshot_path"))
        if not isinstance(target, str) or not isinstance(record, dict) or target in result:
            raise ValueError("integration candidate file inventory is invalid")
        _inside(root, target)
        expected = (path.parent / "revisions" / candidate["revision_id"] / "snapshot" / target).resolve()
        file = _inside(root, record.get("frozen_path", ""))
        if file != expected or not file.is_file() or file.is_symlink() or _sha(file) != record.get("snapshot_sha256"):
            raise ValueError(f"integration candidate frozen file changed: {target}")
        if row.get("upstream_state") == "present":
            upstream = row.get("upstream_sha256")
        elif row.get("upstream_state") == "absent":
            upstream = None
        else:
            raise ValueError(f"integration candidate upstream state is invalid: {target}")
        result[target] = upstream, record["snapshot_sha256"]
    if len(result) != len(frozen) or not result:
        raise ValueError("integration candidate frozen inventory is incomplete")
    return result


def draft(root: Path, active_pointer: dict[str, Any], staged_files: dict[str, str]) -> dict[str, Any]:
    """Produce a review template; blank reasons deliberately fail validation."""
    manifest_path = _inside(root.resolve(), active_pointer["manifest_path"])
    expected = active_pointer["release_manifest_sha256"]
    if _sha(manifest_path) != expected:
        raise ValueError("active MAIN release manifest changed")
    before = json.loads(manifest_path.read_text("utf-8"))["files"]
    changes = [{"path": path, "before": before.get(path), "after": staged_files.get(path),
                "reason": ""}
               for path in sorted(set(before) | set(staged_files))
               if before.get(path) != staged_files.get(path)]
    return {"schema_version": SCHEMA, "base_release_manifest_sha256": expected,
            "changes": changes, "candidate": None}


def check(root: Path, active: dict[str, Any], staged_files: dict[str, str],
          declaration: dict[str, Any]) -> dict[str, Any]:
    """Validate a prepared file inventory before any release manifest is issued."""
    root = root.resolve()
    if not isinstance(declaration, dict) or declaration.get("schema_version") != SCHEMA:
        raise ValueError("local release integration declaration is required")
    if set(declaration) not in ({"schema_version", "base_release_manifest_sha256", "changes", "candidate"}, {"schema_version", "base_release_manifest_sha256", "changes", "candidate", "rebase_receipt"}):
        raise ValueError("integration declaration fields are not exact")
    pointer_path = root / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json"
    if _sha(pointer_path) != active.get("pointer_sha256"):
        raise ValueError("active MAIN changed during release preparation")
    pointer = active["pointer"]
    if pointer.get("release_manifest_sha256") != declaration["base_release_manifest_sha256"]:
        raise ValueError("integration baseline is not the active MAIN release")
    manifest_path = _inside(root, pointer["manifest_path"])
    if _sha(manifest_path) != declaration["base_release_manifest_sha256"]:
        raise ValueError("active MAIN release manifest changed")
    baseline = json.loads(manifest_path.read_text("utf-8")).get("files")
    if not isinstance(baseline, dict):
        raise ValueError("active MAIN release file inventory is invalid")
    actual = {path: {"before": baseline.get(path), "after": staged_files.get(path)}
              for path in set(baseline) | set(staged_files)
              if baseline.get(path) != staged_files.get(path)}
    rows = declaration["changes"]
    if not isinstance(rows, list):
        raise ValueError("integration changes must be a list")
    declared: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "before", "after", "reason"}:
            raise ValueError("integration change record fields are not exact")
        path = row["path"]
        if not isinstance(path, str) or path in declared or not row["reason"] or not isinstance(row["reason"], str):
            raise ValueError("integration change path/reason is invalid or duplicated")
        _inside(root, path)
        declared[path] = {"before": row["before"], "after": row["after"]}
    if declared != actual:
        missing = sorted(set(actual) - set(declared))
        extra = sorted(set(declared) - set(actual))
        mismatch = sorted(path for path in set(actual) & set(declared) if actual[path] != declared[path])
        raise ValueError(f"integration delta differs from active MAIN: missing={missing}, extra={extra}, hash_mismatch={mismatch}")
    candidate_files = _candidate_files(root, declaration)
    if 'rebase_receipt' in declaration:
        from .release_qualification import bound
        receipt = json.loads(bound(root, declaration['rebase_receipt']).read_text())
        if (receipt.get('schema_version') != 'evaluated-release-rebase-v1' or
                receipt.get('base_release_manifest_sha256') != declaration['base_release_manifest_sha256'] or
                receipt.get('candidate') != declaration['candidate'] or
                receipt.get('staged_files') != staged_files or not candidate_files):
            raise ValueError('evaluated rebase does not bind current MAIN and exact stage')
        excluded = receipt.get('excluded_candidate_paths', {})
        if set(excluded) != set(candidate_files) - set(staged_files) or not all(isinstance(v, str) and v.strip() for v in excluded.values()):
            raise ValueError('unserved candidate files require exact exclusion inventory')
        for path, (_, frozen) in candidate_files.items():
            if path in staged_files and staged_files[path] != frozen:
                raise ValueError('evaluated stage differs from frozen candidate: ' + path)
        if set(actual) - set(candidate_files):
            raise ValueError('evaluated rebase changed a file outside frozen candidate')
        return {'base_release_id':pointer['release_id'],
                'base_release_manifest_sha256':declaration['base_release_manifest_sha256'],
                'changed_files':len(actual), 'candidate_files':sorted(set(candidate_files)&set(staged_files)),
                'preserved_files':len(set(baseline)&set(staged_files))-sum(p in baseline and p in staged_files for p in actual),
                'rebase_receipt':declaration['rebase_receipt']}
    for path, (upstream, frozen) in candidate_files.items():
        if path not in actual or actual[path] != {"before": upstream, "after": frozen}:
            raise ValueError(f"candidate must be rebased on active MAIN before promotion: {path}")
    return {"base_release_id": pointer["release_id"],
            "base_release_manifest_sha256": declaration["base_release_manifest_sha256"],
            "changed_files": len(actual), "candidate_files": sorted(candidate_files),
            "preserved_files": len(set(baseline) & set(staged_files)) -
                               sum(path in baseline and path in staged_files for path in actual)}
