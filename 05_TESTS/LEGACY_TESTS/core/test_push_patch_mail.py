from __future__ import annotations

import importlib.util
import json
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "push_patch_mail", ROOT / "scripts" / "push_patch_mail.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, text=True,
                          stdout=subprocess.PIPE).stdout.strip()


def test_pack_contains_changed_blob_and_deletion_manifest(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "keep.py").write_text("old\n", encoding="utf-8")
    (repo / "gone.txt").write_text("gone\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    before = _git(repo, "rev-parse", "HEAD")

    (repo / "keep.py").write_text("new\n", encoding="utf-8")
    (repo / "gone.txt").unlink()
    (repo / ".env").write_text("SECRET=x\n", encoding="utf-8")
    (repo / "data").mkdir()
    (repo / "data" / "large.json").write_text("{}\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "patch")
    after = _git(repo, "rev-parse", "HEAD")

    monkeypatch.setattr(MODULE, "ROOT", repo)
    out = tmp_path / "patch.zip"
    report = MODULE.pack(before, after, out, max_file_mb=12)
    assert report["included"][0]["path"] == "keep.py"
    assert report["deleted"][0]["path"] == "gone.txt"
    assert {row["path"] for row in report["excluded"]} == {".env", "data/large.json"}
    with zipfile.ZipFile(out) as zf:
        assert set(zf.namelist()) == {"keep.py", "PATCH_MANIFEST.json"}
        assert zf.read("keep.py") == b"new\n"
        manifest = json.loads(zf.read("PATCH_MANIFEST.json"))
        assert manifest["after"] == after


def test_pack_renames_javascript_member_for_gmail(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.js").write_text("old\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    before = _git(repo, "rev-parse", "HEAD")
    (repo / "app.js").write_text("new\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "patch")
    after = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(MODULE, "ROOT", repo)
    out = tmp_path / "patch.zip"
    MODULE.pack(before, after, out, max_file_mb=12)
    with zipfile.ZipFile(out) as zf:
        assert "app.js.gmail-safe.txt" in zf.namelist()
        manifest = json.loads(zf.read("PATCH_MANIFEST.json"))
    assert manifest["included"][0]["path"] == "app.js"
    assert manifest["included"][0]["archive_path"] == "app.js.gmail-safe.txt"


def test_recipient_priority(monkeypatch):
    monkeypatch.setenv("GMAIL_USERNAME", "sender@gmail.com")
    monkeypatch.delenv("PATCH_MAIL_TO", raising=False)
    assert MODULE._recipient(None) == "sender@gmail.com"
    monkeypatch.setenv("PATCH_MAIL_TO", "onsite@example.com")
    assert MODULE._recipient(None) == "onsite@example.com"
    assert MODULE._recipient("manual@example.com") == "manual@example.com"
