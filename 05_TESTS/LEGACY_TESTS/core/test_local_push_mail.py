from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
SPEC = importlib.util.spec_from_file_location(
    "local_push_mail",
    ROOT / "06_TOOLS" / "LEGACY_SCRIPTS" / "local_push_mail.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_remote_sha_returns_matching_sha(monkeypatch):
    sha = "a" * 40

    def fake_git(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, f"{sha}\trefs/heads/main\n", "")

    monkeypatch.setattr(MODULE, "_git", fake_git)
    assert MODULE.remote_sha("origin", "refs/heads/main") == sha


def test_remote_sha_rejects_missing_or_invalid_output(monkeypatch):
    monkeypatch.setattr(
        MODULE,
        "_git",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 2, "", "missing"),
    )
    assert MODULE.remote_sha("origin", "refs/heads/main") is None

    monkeypatch.setattr(
        MODULE,
        "_git",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "not-a-sha\tref\n", ""),
    )
    assert MODULE.remote_sha("origin", "refs/heads/main") is None


def test_wait_for_push_stops_when_remote_matches(monkeypatch):
    expected = "b" * 40
    observed = iter([None, "a" * 40, expected])
    monkeypatch.setattr(MODULE, "remote_sha", lambda *args: next(observed))
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)
    assert MODULE.wait_for_push("origin", "refs/heads/main", expected, 30)


def test_shell_environment_credential_takes_priority(monkeypatch):
    monkeypatch.setenv("GMAIL_USERNAME", "sender@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app password")
    monkeypatch.setattr(MODULE, "read_windows_credential", lambda: (_ for _ in ()).throw(AssertionError()))
    assert MODULE.read_smtp_credential() == ("sender@example.com", "apppassword")
