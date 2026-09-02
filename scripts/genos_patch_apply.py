#!/usr/bin/env python3
"""Gmail로 받은 8-AGENT 증분 코드 ZIP을 GenOS Git 작업판에 안전 적용한다.

데이터, .env, 인증서와 원문 파일은 적용 대상이 아니다. 기본은 검증만 하며 실제
변경에는 --apply가 필요하다. 바뀌거나 삭제될 코드 파일의 이전 사본은
``var/patch-backups/``에 남긴다.

    python3 scripts/genos_patch_apply.py verify /path/8agent-patch-*.zip
    python3 scripts/genos_patch_apply.py apply /path/8agent-patch-*.zip --root "$HOME/DEV/8-agent-new" --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


MANIFEST_NAME = "PATCH_MANIFEST.json"
PATCH_FORMAT = "8agent-push-patch/1"
BLOCKED_NAMES = {".env", ".env.local"}
BLOCKED_SUFFIXES = {
    ".key", ".pem", ".p12", ".pfx",
    ".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".zip", ".tar", ".7z", ".bak",
}
BLOCKED_PREFIXES = (
    "docs/adr/", "ADR-", "data/", "tmp/", "artifacts/",
    "lawrag/agents/agent6/corpus/",
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_rel(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"안전하지 않은 경로: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.name in {"", ".", ".."}:
        raise ValueError(f"안전하지 않은 경로: {value!r}")
    if path.name in BLOCKED_NAMES or path.suffix.lower() in BLOCKED_SUFFIXES:
        raise ValueError(f"패치 금지 파일: {value}")
    if any(value.startswith(prefix) for prefix in BLOCKED_PREFIXES):
        raise ValueError(f"패치 금지 경로: {value}")
    return value


def _entry_paths(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    included = manifest.get("included")
    deleted = manifest.get("deleted")
    if not isinstance(included, list) or not isinstance(deleted, list):
        raise ValueError("PATCH_MANIFEST.json의 included/deleted 형식이 잘못되었습니다")

    seen_paths: set[str] = set()
    seen_members: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for entry in included:
        if not isinstance(entry, dict):
            raise ValueError("included 항목 형식이 잘못되었습니다")
        path = _safe_rel(entry.get("path"))
        member = _safe_rel(entry.get("archive_path", path))
        if path in seen_paths or member in seen_members:
            raise ValueError(f"중복 패치 경로: {path}")
        size, digest, mode = entry.get("bytes"), entry.get("sha256"), entry.get("mode")
        if not isinstance(size, int) or size < 0:
            raise ValueError(f"파일 크기 형식이 잘못되었습니다: {path}")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"SHA256 형식이 잘못되었습니다: {path}")
        if mode not in {"100644", "100755"}:
            raise ValueError(f"파일 모드 형식이 잘못되었습니다: {path}")
        old_path = entry.get("old_path")
        if old_path is not None:
            _safe_rel(old_path)
        seen_paths.add(path)
        seen_members.add(member)
        normalized.append({**entry, "path": path, "archive_path": member})

    removals: set[str] = set()
    for entry in deleted:
        if not isinstance(entry, dict):
            raise ValueError("deleted 항목 형식이 잘못되었습니다")
        removals.add(_safe_rel(entry.get("path")))
    for entry in normalized:
        if entry.get("old_path"):
            removals.add(_safe_rel(entry["old_path"]))
    removals.difference_update(seen_paths)
    return normalized, sorted(removals)


def verify(zip_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or MANIFEST_NAME not in names:
            raise ValueError("PATCH_MANIFEST.json 누락 또는 ZIP 안에 중복 경로가 있습니다")
        for info in infos:
            member = _safe_rel(info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f"심볼릭 링크 ZIP 항목은 허용하지 않습니다: {member}")
        manifest = json.loads(archive.read(MANIFEST_NAME))
        if manifest.get("format") != PATCH_FORMAT:
            raise ValueError("알 수 없는 패치 ZIP 형식입니다")
        included, removals = _entry_paths(manifest)
        expected = {MANIFEST_NAME, *(entry["archive_path"] for entry in included)}
        if set(names) != expected:
            raise ValueError("ZIP 파일 목록과 PATCH_MANIFEST.json이 일치하지 않습니다")
        for entry in included:
            raw = archive.read(entry["archive_path"])
            if len(raw) != entry["bytes"] or _sha256(raw) != entry["sha256"]:
                raise ValueError(f"크기 또는 SHA256 불일치: {entry['path']}")
    return manifest, included, removals


def _target(root: Path, rel: str) -> Path:
    target = root.joinpath(*PurePosixPath(rel).parts)
    parent = target.parent
    while parent != root:
        if parent.is_symlink():
            raise ValueError(f"심볼릭 링크 아래에는 적용할 수 없습니다: {rel}")
        parent = parent.parent
    if target.exists() and target.is_symlink():
        raise ValueError(f"심볼릭 링크 파일은 덮어쓸 수 없습니다: {rel}")
    return target


def _git_dirty(root: Path) -> bool:
    import subprocess
    done = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1"],
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return done.returncode == 0 and bool(done.stdout.strip())


def apply(zip_path: Path, root: Path, *, execute: bool, allow_dirty: bool) -> Path | None:
    manifest, included, removals = verify(zip_path)
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"--root가 폴더가 아닙니다: {root}")
    if _git_dirty(root) and not allow_dirty:
        raise ValueError("Git 작업판에 미커밋 변경이 있습니다. 먼저 commit/stash하거나 --allow-dirty를 명시하세요")

    targets = {entry["path"] for entry in included} | set(removals)
    resolved = {rel: _target(root, rel) for rel in sorted(targets)}
    summary = {
        "before": manifest.get("before"), "after": manifest.get("after"),
        "write": [entry["path"] for entry in included], "remove": removals,
        "root": str(root), "apply": execute,
    }
    if not execute:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("검증 OK — 실제 적용은 끝에 --apply를 붙이세요.")
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short = str(manifest.get("after") or "unknown")[:12]
    backup = root / "var" / "patch-backups" / f"{stamp}-{short}"
    backup.mkdir(parents=True, exist_ok=False)
    receipt: dict[str, Any] = {**summary, "applied_at": datetime.now(timezone.utc).isoformat(), "entries": []}
    for rel, target in resolved.items():
        existed = target.exists()
        if existed and not target.is_file():
            raise ValueError(f"파일이 아닌 기존 경로는 교체할 수 없습니다: {rel}")
        row: dict[str, Any] = {"path": rel, "existed": existed}
        if existed:
            backup_file = backup / "files" / rel
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_file)
            row["backup_sha256"] = _sha256(backup_file.read_bytes())
        receipt["entries"].append(row)

    with zipfile.ZipFile(zip_path) as archive:
        for entry in included:
            target = resolved[entry["path"]]
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = archive.read(entry["archive_path"])
            handle = tempfile.NamedTemporaryFile(prefix=".patch-", dir=target.parent, delete=False)
            try:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                handle.close()
            os.chmod(handle.name, 0o755 if entry["mode"] == "100755" else 0o644)
            os.replace(handle.name, target)
        for rel in removals:
            target = resolved[rel]
            if target.exists():
                target.unlink()

    (backup / "APPLY_RECEIPT.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"적용 완료: 쓰기 {len(included)}개 · 삭제 {len(removals)}개 · 백업 {backup}")
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    verify_parser = sub.add_parser("verify", help="ZIP 무결성·허용 경로 확인")
    verify_parser.add_argument("zip", type=Path)
    apply_parser = sub.add_parser("apply", help="검증 후 코드 작업판에 적용")
    apply_parser.add_argument("zip", type=Path)
    apply_parser.add_argument("--root", type=Path, required=True)
    apply_parser.add_argument("--apply", action="store_true", help="실제로 파일을 변경")
    apply_parser.add_argument("--allow-dirty", action="store_true", help="미커밋 Git 변경을 허용")
    args = parser.parse_args()
    try:
        if args.command == "verify":
            manifest, included, removals = verify(args.zip)
            print(f"검증 OK: {args.zip} · 쓰기 {len(included)}개 · 삭제 {len(removals)}개 · {manifest.get('after')}")
        else:
            apply(args.zip, args.root, execute=args.apply, allow_dirty=args.allow_dirty)
    except Exception as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
