#!/usr/bin/env python3
"""Git push 두 SHA 사이의 안전한 증분 ZIP을 만들고 Gmail SMTP로 발송한다.

GitHub Actions에서는 ``run``을 사용한다. 로컬에서는 ``pack``으로 같은 ZIP을
검사할 수 있다. Gmail 비밀번호는 명령행 인자로 받지 않고 환경변수로만 읽는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import smtplib
import ssl
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
ZERO_SHA = "0" * 40
MANIFEST = "PATCH_MANIFEST.json"
DEFAULT_MAX_ZIP_MB = 18
DEFAULT_MAX_FILE_MB = 12
BLOCKED_NAMES = {".env", ".env.local"}
BLOCKED_SUFFIXES = {
    ".key", ".pem", ".p12", ".pfx",
    ".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".zip", ".tar", ".7z", ".bak",
}
BLOCKED_PREFIXES = (
    ("docs/adr/", "adr_or_experiment_record"),
    ("ADR-", "adr_or_experiment_record"),
    ("data/", "runtime_or_bulk_data"),
    ("tmp/", "temporary_or_generated_artifact"),
    ("artifacts/", "temporary_or_generated_artifact"),
    ("lawrag/agents/agent6/corpus/", "source_corpus"),
)


def _git(*args: str, text: bool = True) -> str | bytes:
    done = subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=text,
    )
    return done.stdout


def _resolve_range(before: str, after: str) -> tuple[str, str]:
    after = str(_git("rev-parse", "--verify", f"{after}^{{commit}}")).strip()
    if before and before != ZERO_SHA:
        before = str(_git("rev-parse", "--verify", f"{before}^{{commit}}")).strip()
        return before, after
    # 새 브랜치의 before는 40자리 0이다. 첫 커밋이면 Git empty tree와 비교한다.
    parent = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", f"{after}^"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    if parent.returncode == 0:
        return parent.stdout.strip(), after
    empty = str(_git("hash-object", "-t", "tree", "/dev/null")).strip()
    return empty, after


def _changes(before: str, after: str) -> list[dict[str, str]]:
    raw = bytes(_git(
        "diff", "--name-status", "-z", "--find-renames", before, after,
        text=False,
    ))
    tokens = raw.decode("utf-8", "surrogateescape").split("\0")
    if tokens and not tokens[-1]:
        tokens.pop()
    rows: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        code = status[:1]
        if code in {"R", "C"}:
            old, path = tokens[index:index + 2]
            index += 2
            rows.append({"status": status, "old_path": old, "path": path})
        else:
            path = tokens[index]
            index += 1
            rows.append({"status": status, "path": path})
    return rows


def _blocked(path: str) -> str | None:
    posix = PurePosixPath(path)
    if posix.is_absolute() or ".." in posix.parts:
        return "unsafe_path"
    if posix.name in BLOCKED_NAMES or posix.suffix.lower() in BLOCKED_SUFFIXES:
        return "sensitive_or_source_document"
    for prefix, reason in BLOCKED_PREFIXES:
        if path.startswith(prefix):
            return reason
    return None


def _blob(after: str, path: str) -> tuple[str, bytes]:
    mode = str(_git("ls-tree", after, "--", path)).split(maxsplit=1)[0]
    if mode == "120000":
        raise ValueError("symlink")
    return mode, bytes(_git("show", f"{after}:{path}", text=False))


def _zip_info(path: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = ((0o100755 if executable else 0o100644) & 0xFFFF) << 16
    return info


def pack(before: str, after: str, out: Path, *, max_file_mb: int) -> dict:
    before, after = _resolve_range(before, after)
    changes = _changes(before, after)
    included: list[dict] = []
    deleted: list[dict] = []
    excluded: list[dict] = []
    blobs: list[tuple[str, bytes, bool]] = []
    max_file = max_file_mb * 1024 * 1024

    for row in changes:
        status, path = row["status"], row["path"]
        if status.startswith("D"):
            deleted.append(row)
            continue
        reason = _blocked(path)
        if reason:
            excluded.append({**row, "reason": reason})
            continue
        try:
            mode, raw = _blob(after, path)
        except ValueError as exc:
            excluded.append({**row, "reason": str(exc)})
            continue
        if len(raw) > max_file:
            excluded.append({**row, "reason": "file_too_large", "bytes": len(raw)})
            continue
        digest = hashlib.sha256(raw).hexdigest()
        included.append({**row, "bytes": len(raw), "sha256": digest, "mode": mode})
        blobs.append((path, raw, mode == "100755"))

    manifest = {
        "format": "8agent-push-patch/1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "ref": os.environ.get("GITHUB_REF_NAME", ""),
        "before": before,
        "after": after,
        "included": included,
        "deleted": deleted,
        "excluded": excluded,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, raw, executable in sorted(blobs):
            zf.writestr(_zip_info(path, executable), raw)
        body = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode()
        zf.writestr(_zip_info(MANIFEST), body)
    manifest["zip"] = str(out)
    manifest["zip_bytes"] = out.stat().st_size
    manifest["zip_sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
    return manifest


def _recipient(explicit: str | None) -> str:
    # 수동 입력 > Repository variable > 발신 Gmail(본인)의 순서다.
    value = (explicit or os.environ.get("PATCH_MAIL_TO") or
             os.environ.get("GMAIL_USERNAME") or "").strip()
    if not value or "@" not in value or any(ch in value for ch in "\r\n"):
        raise ValueError("수신 이메일이 없습니다: --to, PATCH_MAIL_TO 또는 GMAIL_USERNAME 설정 필요")
    return value


def send(zip_path: Path, manifest: dict, *, recipient: str | None) -> str:
    username = os.environ.get("GMAIL_USERNAME", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not username or not password:
        raise ValueError("GMAIL_USERNAME·GMAIL_APP_PASSWORD GitHub Secrets가 필요합니다")
    to = _recipient(recipient)
    ref = manifest.get("ref") or "unknown-ref"
    after = str(manifest.get("after") or "")[:12]
    excluded = manifest.get("excluded") or []
    warning = f" · 제외 {len(excluded)}개" if excluded else ""

    message = EmailMessage()
    message["From"] = username
    message["To"] = to
    message["Subject"] = f"[8-AGENT patch] {ref}@{after}{warning}"
    message.set_content(
        "Git push 증분 ZIP입니다.\n"
        f"repository: {manifest.get('repository') or '-'}\n"
        f"ref: {ref}\n"
        f"before: {manifest.get('before')}\n"
        f"after: {manifest.get('after')}\n"
        f"included: {len(manifest.get('included') or [])}\n"
        f"deleted: {len(manifest.get('deleted') or [])}\n"
        f"excluded: {len(excluded)}\n"
        f"sha256: {manifest.get('zip_sha256')}\n\n"
        "삭제·이름변경·제외 상세는 ZIP의 PATCH_MANIFEST.json을 확인하세요.\n"
    )
    message.add_attachment(zip_path.read_bytes(), maintype="application", subtype="zip",
                           filename=zip_path.name)
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30) as smtp:
        smtp.login(username, password)
        smtp.send_message(message)
    return to


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("pack", "run"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--before", required=True)
        cmd.add_argument("--after", required=True)
        cmd.add_argument("--out", type=Path, required=True)
        cmd.add_argument("--max-file-mb", type=int, default=DEFAULT_MAX_FILE_MB)
        cmd.add_argument("--max-zip-mb", type=int, default=DEFAULT_MAX_ZIP_MB)
        if name == "run":
            cmd.add_argument("--to", help="수동 실행 수신 주소; 없으면 PATCH_MAIL_TO→GMAIL_USERNAME")
    send_cmd = sub.add_parser("send")
    send_cmd.add_argument("zip", type=Path)
    send_cmd.add_argument("--to", help="수신 주소; 없으면 PATCH_MAIL_TO→GMAIL_USERNAME")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "send":
            with zipfile.ZipFile(args.zip) as zf:
                manifest = json.loads(zf.read(MANIFEST))
            manifest["zip_sha256"] = hashlib.sha256(args.zip.read_bytes()).hexdigest()
            to = send(args.zip, manifest, recipient=args.to)
            print(f"발송 완료: {to} · {args.zip.name}")
            return 0

        manifest = pack(args.before, args.after, args.out,
                        max_file_mb=args.max_file_mb)
        limit = args.max_zip_mb * 1024 * 1024
        if manifest["zip_bytes"] > limit:
            raise ValueError(
                f"ZIP이 Gmail 안전 한도 {args.max_zip_mb}MB를 넘습니다: "
                f"{manifest['zip_bytes']} bytes"
            )
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        if args.command == "run":
            to = send(args.out, manifest, recipient=args.to)
            print(f"발송 완료: {to} · {args.out.name}")
        return 0
    except Exception as exc:
        print(f"오류: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
