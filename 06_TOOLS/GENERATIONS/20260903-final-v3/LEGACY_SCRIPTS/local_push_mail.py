#!/usr/bin/env python3
"""로컬 push 성공을 확인한 뒤 안전한 증분 ZIP을 Gmail로 발송한다."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import push_patch_mail  # noqa: E402


ROOT = SCRIPT_DIR.parent
ZERO_SHA = "0" * 40
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CREDENTIAL_SCRIPT = SCRIPT_DIR / "push_patch_credential.ps1"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def remote_sha(remote: str, remote_ref: str) -> str | None:
    done = _git("ls-remote", "--exit-code", remote, remote_ref, check=False)
    if done.returncode != 0 or not done.stdout.strip():
        return None
    sha = done.stdout.split(maxsplit=1)[0].lower()
    return sha if SHA_RE.fullmatch(sha) else None


def wait_for_push(remote: str, remote_ref: str, after: str, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if remote_sha(remote, remote_ref) == after:
            return True
        time.sleep(2)
    return remote_sha(remote, remote_ref) == after


def _windows_path(path: Path) -> str:
    done = subprocess.run(
        ["wslpath", "-w", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return done.stdout.strip()


def read_windows_credential() -> tuple[str, str]:
    done = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            _windows_path(CREDENTIAL_SCRIPT),
            "-Mode",
            "Get",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    value = json.loads(done.stdout)
    username = str(value.get("username") or "").strip()
    password = str(value.get("password") or "").replace(" ", "").strip()
    if not username or not password:
        raise ValueError("Windows 자격 증명 관리자에 Gmail 자격증명이 없습니다")
    return username, password


def read_smtp_credential() -> tuple[str, str]:
    """Prefer transient shell environment, then retain the WSL credential fallback."""
    username = os.environ.get("GMAIL_USERNAME", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if username or password:
        if not username or not password:
            raise ValueError("GMAIL_USERNAME과 GMAIL_APP_PASSWORD를 함께 설정하세요")
        return username, password
    return read_windows_credential()


def _config(name: str) -> str:
    done = _git("config", "--local", "--get", name, check=False)
    return done.stdout.strip() if done.returncode == 0 else ""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--remote-ref", required=True)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    before, after = args.before.lower(), args.after.lower()
    if before != ZERO_SHA and not SHA_RE.fullmatch(before):
        print("오류: before SHA 형식이 잘못되었습니다", file=sys.stderr)
        return 2
    if not SHA_RE.fullmatch(after) or after == ZERO_SHA:
        print("오류: after SHA 형식이 잘못되었습니다", file=sys.stderr)
        return 2

    if not wait_for_push(args.remote, args.remote_ref, after, args.timeout):
        print("발송 안 함: 제한 시간 안에 원격 push 성공을 확인하지 못했습니다")
        return 0

    short = after[:12]
    out = ROOT / "var" / "out" / "ship" / "local-mail" / f"8agent-patch-{short}.zip"
    manifest = push_patch_mail.pack(
        before,
        after,
        out,
        max_file_mb=push_patch_mail.DEFAULT_MAX_FILE_MB,
    )
    if manifest["zip_bytes"] > push_patch_mail.DEFAULT_MAX_ZIP_MB * 1024 * 1024:
        raise ValueError(f"ZIP이 {push_patch_mail.DEFAULT_MAX_ZIP_MB}MB 제한을 넘습니다")
    manifest["repository"] = args.remote
    manifest["ref"] = args.remote_ref.removeprefix("refs/heads/")

    username, password = read_smtp_credential()
    recipient = os.environ.get("PATCH_MAIL_TO", "").strip() or _config("patchmail.to") or username
    sent_to = push_patch_mail.send(
        out,
        manifest,
        recipient=recipient,
        username=username,
        password=password,
    )
    print(f"발송 완료: {sent_to} · {out.name} · {manifest['zip_sha256']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"오류: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
