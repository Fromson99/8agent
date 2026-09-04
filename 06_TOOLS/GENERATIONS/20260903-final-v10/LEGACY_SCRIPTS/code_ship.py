#!/usr/bin/env python3
"""GenOS 망 반입용 코드 ZIP을 만들고 검증한다.

현재 작업판의 실행 코드만 허용목록으로 담는다. .git, .env, 가상환경, 테스트,
원문 문서, 런타임 데이터는 넣지 않는다. 데이터는 data_ship.sh로 따로 나른다.

    python scripts/code_ship.py pack --out var/out/ship/8agent-code.zip
    python scripts/code_ship.py verify var/out/ship/8agent-code.zip
    python scripts/code_ship.py list
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable


ROOT = Path(
    os.environ.get("LAWRAG_TOOL_WORKSPACE_ROOT", Path(__file__).resolve().parents[1])
).resolve()
MANIFEST = "CODE_MANIFEST.json"
REQUIRED_FILES = (
    "service.py",
    "requirements-serving.txt",
    "00_SYSTEM/WORKSPACE.json",
)

ROOT_FILES = (
    ".gitignore", ".env.example", ".env.genos.example", ".env.onsite.example",
    "README.md", "service.py",
    "requirements.txt", "requirements-serving.txt",
)
TREE_ROOTS = ("00_SYSTEM", "lawrag", "scripts", "config/dataset_sync")
DOC_FILES = (
    "docs/GENOS_QUICKSTART.md", "docs/GENOS_DEPLOY.md",
    "docs/GENOS_SITE_RUNBOOK.md", "docs/ONSITE_RUNBOOK.md",
    "docs/OPS_TRANSPORT.md", "docs/DATASET_SYNC.md", "docs/GENOS_PATCH_UPDATE.md",
)
STATIC_FILES = (
    "data/aliases.json", "data/rag/scopes.yml",
    "data/domain_graph/canonical.json",
)

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", "output"}
SKIP_PREFIXES = (
    "lawrag/agents/agent6/corpus/",
    "lawrag/research/",
)
BLOCKED_NAMES = {".env", ".env.local"}
BLOCKED_SUFFIXES = {
    ".key", ".pem", ".p12", ".pfx",
    ".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".zip", ".tar", ".gz", ".7z", ".bak", ".pyc",
    ".orig", ".ps1",
}


def _git(*args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(ROOT), *args], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _blocked(rel: str) -> bool:
    path = PurePosixPath(rel)
    if path.name in BLOCKED_NAMES or path.suffix.lower() in BLOCKED_SUFFIXES:
        return True
    if any(part in SKIP_DIRS for part in path.parts):
        return True
    return any(rel.startswith(prefix) for prefix in SKIP_PREFIXES)


def _allowed(rel: str) -> bool:
    """Accept only the audited code/config surface, including the path contract."""

    if rel in {*ROOT_FILES, *DOC_FILES, *STATIC_FILES}:
        return True
    return any(rel.startswith(f"{root}/") for root in TREE_ROOTS)


def _active_targets() -> dict[str, Path]:
    """Resolve immutable code/tool targets from the active v2 receipt."""

    manifest = json.loads((ROOT / "00_SYSTEM/WORKSPACE.json").read_text("utf-8"))
    activation_rel = (manifest.get("lifecycle") or {}).get("activation_receipt")
    if manifest.get("mode") != "v2-only" or not isinstance(activation_rel, str):
        return {}
    activation = json.loads((ROOT / activation_rel).read_text("utf-8"))
    final = json.loads(
        (ROOT / activation["validation_receipt_path"]).read_text("utf-8")
    )
    targets: dict[str, Path] = {}
    for source in ("lawrag", "scripts"):
        rows = [row for row in final.get("items", []) if row.get("source") == source]
        if len(rows) != 1:
            raise RuntimeError(f"활성 영수증의 {source!r} 바인딩이 하나가 아닙니다")
        targets[source] = (ROOT / rows[0]["target"]).resolve()
    return targets


def _bundle_relative(path: Path, active: dict[str, Path] | None = None) -> str:
    active = active if active is not None else _active_targets()
    resolved = path.resolve()
    for archive_root, source_root in (
        ("lawrag", active.get("lawrag")),
        ("scripts", active.get("scripts")),
        ("config", ROOT / "08_DEPLOYMENT/CONFIG"),
        ("docs", ROOT / "07_DOCS/LEGACY_DOCS"),
        ("data", ROOT / "01_DATA"),
    ):
        if source_root is None:
            continue
        try:
            suffix = resolved.relative_to(source_root.resolve()).as_posix()
        except ValueError:
            continue
        return archive_root if suffix == "." else f"{archive_root}/{suffix}"
    return resolved.relative_to(ROOT).as_posix()


def _files() -> list[Path]:
    candidates: list[Path] = []
    active = _active_targets()
    physical_files = {
        **{rel: ROOT / rel for rel in ROOT_FILES},
        **{rel: ROOT / "07_DOCS/LEGACY_DOCS" / Path(rel).name for rel in DOC_FILES},
        **{rel: ROOT / "01_DATA" / rel.removeprefix("data/") for rel in STATIC_FILES},
    }
    for rel, path in physical_files.items():
        if path.is_file():
            candidates.append(path)
    tree_sources = (
        ROOT / "00_SYSTEM",
        active.get("lawrag", ROOT / "lawrag"),
        active.get("scripts", ROOT / "scripts"),
        ROOT / "08_DEPLOYMENT/CONFIG/dataset_sync",
    )
    for base in tree_sources:
        if base.is_dir():
            candidates.extend(path for path in base.rglob("*") if path.is_file())

    rows: dict[str, Path] = {}
    for path in candidates:
        if path.is_symlink():
            raise RuntimeError(f"심볼릭 링크는 코드 ZIP에 넣지 않습니다: {path}")
        rel = _bundle_relative(path, active)
        if _allowed(rel) and not _blocked(rel):
            rows[rel] = path
    missing = [name for name in REQUIRED_FILES if name not in rows]
    if missing:
        raise RuntimeError("필수 파일 없음: " + ", ".join(missing))
    return [rows[name] for name in sorted(rows)]


def _rows(paths: Iterable[Path]) -> tuple[list[dict], dict[str, bytes]]:
    rows, payloads = [], {}
    for path in paths:
        rel = _bundle_relative(path)
        raw = path.read_bytes()
        payloads[rel] = raw
        rows.append({"path": rel, "bytes": len(raw), "sha256": _sha256(raw)})
    return rows, payloads


def _default_output() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rev = _git("rev-parse", "--short", "HEAD") or "nogit"
    return ROOT / "90_RUNTIME" / "OUT" / "SHIP" / f"8agent-code-{stamp}-{rev}.zip"


def pack(output: Path | None) -> Path:
    target = (output or _default_output()).resolve()
    if target.exists():
        raise RuntimeError(f"이미 존재합니다: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    paths = _files()
    rows, payloads = _rows(paths)
    status = _git("status", "--porcelain=v1")
    manifest = {
        "format": "8agent-code/1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git": {
            "branch": _git("branch", "--show-current") or "detached",
            "head": _git("rev-parse", "HEAD") or None,
            "dirty": bool(status),
            "status_rows": len(status.splitlines()) if status else 0,
        },
        "note": "코드 전용. 런타임 데이터는 scripts/data_ship.sh로 별도 반입.",
        "files": rows,
    }
    manifest_raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"

    partial = target.with_suffix(target.suffix + ".part")
    try:
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=9) as archive:
            for rel, raw in payloads.items():
                info = zipfile.ZipInfo(rel)
                info.date_time = (2026, 1, 1, 0, 0, 0)
                mode = next(path.stat().st_mode & 0o777 for path in paths if _bundle_relative(path) == rel)
                info.external_attr = (0o100000 | mode) << 16
                archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED,
                                 compresslevel=9)
            archive.writestr(MANIFEST, manifest_raw,
                             compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)

    verify(target)
    print(f"생성: {target}")
    print(f"크기: {target.stat().st_size / 1024 / 1024:.1f}MB · 파일 {len(rows)}개")
    print(f"SHA256: {_sha256(target.read_bytes())}")
    if manifest["git"]["dirty"]:
        print(f"주의: 미커밋 작업판 스냅샷입니다(status {manifest['git']['status_rows']}행).")
    return target


def verify(path: Path) -> None:
    target = path.resolve()
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("ZIP 안에 중복 경로가 있습니다")
        for name in names:
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts or "" in pure.parts:
                raise RuntimeError(f"안전하지 않은 ZIP 경로: {name}")
            if name != MANIFEST and (not _allowed(name) or _blocked(name)):
                raise RuntimeError(f"허용되지 않은 파일이 들어 있습니다: {name}")
        if MANIFEST not in names:
            raise RuntimeError(f"{MANIFEST} 없음")
        manifest = json.loads(archive.read(MANIFEST))
        if manifest.get("format") != "8agent-code/1":
            raise RuntimeError("모르는 코드 ZIP 형식")
        expected = {row["path"]: row for row in manifest.get("files") or []}
        actual = set(names) - {MANIFEST}
        if actual != set(expected):
            raise RuntimeError("매니페스트와 ZIP 파일 목록이 다릅니다")
        for name, row in expected.items():
            raw = archive.read(name)
            if len(raw) != row["bytes"] or _sha256(raw) != row["sha256"]:
                raise RuntimeError(f"크기 또는 SHA256 불일치: {name}")
        for required in REQUIRED_FILES:
            if required not in actual:
                raise RuntimeError(f"필수 파일 없음: {required}")
    print(f"검증 OK: {target} · 파일 {len(expected)}개")


def listing() -> None:
    rows, _payloads = _rows(_files())
    for row in rows:
        print(f"{row['bytes']:>10}  {row['path']}")
    print(f"합계: {sum(row['bytes'] for row in rows) / 1024 / 1024:.1f}MB · {len(rows)}개")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_pack = sub.add_parser("pack", help="코드 ZIP 생성")
    p_pack.add_argument("--out", type=Path, help="출력 ZIP (기본: var/out/ship)")
    p_verify = sub.add_parser("verify", help="코드 ZIP 검증")
    p_verify.add_argument("zip", type=Path)
    sub.add_parser("list", help="포함될 파일 목록")
    args = parser.parse_args()
    try:
        if args.command == "pack":
            pack(args.out)
        elif args.command == "verify":
            verify(args.zip)
        else:
            listing()
    except Exception as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
