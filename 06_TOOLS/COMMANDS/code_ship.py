#!/usr/bin/env python3
"""GenOS 망 반입용 코드 ZIP을 만들고 검증한다.

현재 작업판의 실행 코드만 허용목록으로 담는다. .git, .env, 가상환경, 테스트,
원문 문서, 런타임 데이터는 넣지 않는다. 데이터는 data_ship.sh로 따로 나른다.

    python 06_TOOLS/run_tool.py code_ship.py pack --out 90_RUNTIME/OUT/ship/8agent-code.zip
    python 06_TOOLS/run_tool.py code_ship.py verify 90_RUNTIME/OUT/ship/8agent-code.zip
    python 06_TOOLS/run_tool.py code_ship.py list
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


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
MANIFEST = "CODE_MANIFEST.json"
# The maintained DRAFT builder verifies these exact historical source files.
# Preserve their paths and bytes; do not ship unrelated research candidates.
AUTHORING_SUPPORT_ROOT = "02_BACKEND/lawrag/research/candidates/adr_0252/source-ids/revisions/rev-001/snapshot/06_TOOLS/OFFLINE"
AUTHORING_SUPPORT_FILES = tuple(
    f"{AUTHORING_SUPPORT_ROOT}/{name}"
    for name in ("genos_authoring.py", "source_candidates.py", "definition_patterns.py")
)
PIPELINE_FILES = (
    "GENOS.md",
    "06_TOOLS/pipeline.py",
    "06_TOOLS/run_tool.py",
    "06_TOOLS/ACTIVE_TOOLS.json",
    "06_TOOLS/genos_pipeline.sh",
    "06_TOOLS/AUDIT/legal_semantic_contract.py",
    "08_DEPLOYMENT/CONFIG/raw-source-packages.json",
    "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py",
    "08_DEPLOYMENT/GENOS/pipeline.env.example",
    *AUTHORING_SUPPORT_FILES,
)
REQUIRED_FILES = (
    "service.py",
    "pyproject.toml",
    "requirements-serving.txt",
    "requirements-pipeline.txt",
    "00_SYSTEM/WORKSPACE.json",
    "02_BACKEND/semantic_runtime/app.py",
    "02_BACKEND/semantic_runtime/genos.py",
    "02_BACKEND/PIPELINE/engine_host.py",
    *PIPELINE_FILES,
)

ROOT_FILES = (
    ".gitignore", ".env.example", ".env.genos.example", ".env.onsite.example",
    "README.md", "service.py", "genos_install.sh", "genos_git_publish.sh",
    "genos_unpack_all.sh", "pyproject.toml",
    "requirements.txt", "requirements-serving.txt", "requirements-pipeline.txt",
    *PIPELINE_FILES,
)
TREE_ROOTS = (
    "00_SYSTEM",
    "02_BACKEND/lawrag",
    "02_BACKEND/semantic_runtime",
    "02_BACKEND/ENGINES",
    "02_BACKEND/PIPELINE",
    "06_TOOLS/COMMANDS",
    "08_DEPLOYMENT/CONFIG/dataset_sync",
)
DOC_FILES = (
    "07_DOCS/REFERENCE/OPERATIONS/GENOS_QUICKSTART.md",
    "07_DOCS/REFERENCE/OPERATIONS/GENOS_DEPLOY.md",
    "07_DOCS/REFERENCE/OPERATIONS/GENOS_SITE_RUNBOOK.md",
    "07_DOCS/REFERENCE/OPERATIONS/ONSITE_RUNBOOK.md",
    "07_DOCS/REFERENCE/OPERATIONS/OPS_TRANSPORT.md",
    "07_DOCS/REFERENCE/OPERATIONS/DATASET_SYNC.md",
    "07_DOCS/REFERENCE/OPERATIONS/GENOS_PATCH_UPDATE.md",
    "07_DOCS/REFERENCE/OPERATIONS/GENOS_UNIFIED_RAW_PIPELINE.md",
    "07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md",
    "07_DOCS/REFERENCE/OPERATIONS/GENOS_RECIPE_VLM.md",
    "07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_ALIGNMENT.md",
    "07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_KNOWLEDGE_BUNDLE.md",
    "07_DOCS/REFERENCE/OPERATIONS/GENOS_CODE_SERVING_CURRENT.md",
    "07_DOCS/REFERENCE/OPERATIONS/GENOS_PIPELINE_GLOSSARY_HANDOFF.md",
)
# Runtime data, including small lookup tables, travels through the separately
# verified dataset package.  A code archive must remain data-free.
STATIC_FILES = (
    "03_FRONTEND/README.md",
    "05_TESTS/README.md",
)

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", "output"}
SKIP_PREFIXES = (
    "02_BACKEND/lawrag/agents/agent6/corpus/",
    "02_BACKEND/lawrag/research/",
)
BLOCKED_NAMES = {".env", ".env.local"}
BLOCKED_SUFFIXES = {
    ".key", ".pem", ".p12", ".pfx",
    ".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".zip", ".tar", ".gz", ".7z", ".bak", ".pyc",
    ".orig", ".ps1", ".js",
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
    if rel in AUTHORING_SUPPORT_FILES:
        return False
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


def _files() -> list[Path]:
    candidates: list[Path] = []
    for rel in (*ROOT_FILES, *DOC_FILES, *STATIC_FILES):
        path = ROOT / rel
        if path.is_file():
            candidates.append(path)
    for rel in TREE_ROOTS:
        base = ROOT / rel
        if base.is_dir():
            candidates.extend(path for path in base.rglob("*") if path.is_file())

    rows: dict[str, Path] = {}
    for path in candidates:
        if path.is_symlink():
            raise RuntimeError(f"심볼릭 링크는 코드 ZIP에 넣지 않습니다: {path}")
        rel = path.relative_to(ROOT).as_posix()
        if _allowed(rel) and not _blocked(rel):
            rows[rel] = path
    missing = [name for name in REQUIRED_FILES if name not in rows]
    if missing:
        raise RuntimeError("필수 파일 없음: " + ", ".join(missing))
    return [rows[name] for name in sorted(rows)]


def _rows(paths: Iterable[Path]) -> tuple[list[dict], dict[str, bytes]]:
    rows, payloads = [], {}
    for path in paths:
        rel = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        payloads[rel] = raw
        rows.append({"path": rel, "bytes": len(raw), "sha256": _sha256(raw)})
    return rows, payloads


def _default_output() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rev = _git("rev-parse", "--short", "HEAD") or "nogit"
    return ROOT / "90_RUNTIME" / "LEGACY_VAR" / "out" / "ship" / f"8agent-code-{stamp}-{rev}.zip"


def pack(output: Path | None) -> Path:
    target = (output or _default_output()).resolve()
    if target.exists():
        raise RuntimeError(f"이미 존재합니다: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    rows, payloads = _rows(_files())
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
                mode = (ROOT / rel).stat().st_mode & 0o777
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
