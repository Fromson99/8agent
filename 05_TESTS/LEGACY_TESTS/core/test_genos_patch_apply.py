from __future__ import annotations

import importlib.util
import json
import subprocess
import zipfile
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
SPEC = importlib.util.spec_from_file_location(
    "genos_patch_apply",
    ROOT / "06_TOOLS" / "LEGACY_SCRIPTS" / "genos_patch_apply.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _zip(path: Path, manifest: dict, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr("PATCH_MANIFEST.json", json.dumps(manifest))


def _entry(path: str, raw: bytes, **extra: object) -> dict:
    import hashlib
    return {"path": path, "archive_path": extra.pop("archive_path", path), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "mode": "100644", **extra}


def test_apply_restores_gmail_safe_member_and_backs_up(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "app.js").write_bytes(b"old\n")
    (root / "gone.py").write_bytes(b"gone\n")
    raw = b"new\n"
    manifest = {"format": "8agent-push-patch/1", "before": "a" * 40, "after": "b" * 40,
                "included": [_entry("app.js", raw, archive_path="app.js.gmail-safe.txt")],
                "deleted": [{"status": "D", "path": "gone.py"}], "excluded": []}
    bundle = tmp_path / "patch.zip"
    _zip(bundle, manifest, {"app.js.gmail-safe.txt": raw})
    backup = MODULE.apply(bundle, root, execute=True, allow_dirty=False)
    assert backup is not None
    assert (root / "app.js").read_bytes() == raw
    assert not (root / "gone.py").exists()
    assert (backup / "files/app.js").read_bytes() == b"old\n"
    assert (backup / "files/gone.py").read_bytes() == b"gone\n"


def test_verify_rejects_data_and_env_paths(tmp_path):
    raw = b"bad\n"
    manifest = {"format": "8agent-push-patch/1", "included": [_entry("data/evil.py", raw)],
                "deleted": [], "excluded": []}
    bundle = tmp_path / "bad.zip"
    _zip(bundle, manifest, {"data/evil.py": raw})
    try:
        MODULE.verify(bundle)
    except ValueError as exc:
        assert "패치 금지" in str(exc)
    else:
        raise AssertionError("data path must be rejected")
