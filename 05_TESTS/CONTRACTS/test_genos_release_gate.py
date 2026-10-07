"""A passing ZIP check must describe the committed code-serving checkout."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "genos_release_gate", ROOT / "06_TOOLS/COMMANDS/genos_release_gate.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "deploy"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    target = root / "02_BACKEND/semantic_runtime/term_index.py"
    target.parent.mkdir(parents=True)
    raw = b"def current(): return True\n"
    target.write_bytes(raw)
    git(root, "add", ".")
    git(root, "commit", "-qm", "candidate")
    archive = tmp_path / "candidate.zip"
    row = {"path": target.relative_to(root).as_posix(), "bytes": len(raw),
           "sha256": hashlib.sha256(raw).hexdigest()}
    manifest = {"format": "8agent-code/1", "files": [row]}
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr(row["path"], raw)
        out.writestr("CODE_MANIFEST.json", json.dumps(manifest))
    return archive, root


def test_matching_zip_and_committed_checkout_pass(tmp_path):
    archive, root = fixture(tmp_path)
    receipt = GATE.compare_zip_to_checkout(archive, root)
    assert receipt["code_files"] == 1
    assert receipt["commit"]


def test_stale_committed_code_fails_even_when_zip_is_valid(tmp_path):
    archive, root = fixture(tmp_path)
    target = root / "02_BACKEND/semantic_runtime/term_index.py"
    target.write_text("def current(): return False\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "stale deployment")
    with pytest.raises(ValueError, match="ZIP/deployment checkout mismatch"):
        GATE.compare_zip_to_checkout(archive, root)


def test_uncommitted_change_cannot_pass(tmp_path):
    archive, root = fixture(tmp_path)
    (root / "02_BACKEND/semantic_runtime/term_index.py").write_text("edited\n")
    with pytest.raises(ValueError, match="uncommitted tracked changes"):
        GATE.compare_zip_to_checkout(archive, root)


def test_patch_requires_exact_committed_dependency(tmp_path):
    archive, root = fixture(tmp_path)
    dependency = root / 'dependency.py'; dependency.write_text('original\n')
    git(root, 'add', '.'); git(root, 'commit', '-qm', 'dependency')
    with zipfile.ZipFile(archive) as z:
        contents = {n: z.read(n) for n in z.namelist()}
    manifest = json.loads(contents['CODE_MANIFEST.json'])
    manifest['required_files'] = [{'path': 'dependency.py', 'sha256': GATE.sha(dependency)}]
    contents['CODE_MANIFEST.json'] = json.dumps(manifest).encode()
    with zipfile.ZipFile(archive, 'w') as z:
        for name, raw in contents.items(): z.writestr(name, raw)
    GATE.compare_zip_to_checkout(archive, root)
    dependency.write_text('changed\n')
    git(root, 'add', '.'); git(root, 'commit', '-qm', 'drift')
    with pytest.raises(ValueError, match='dependency differs'):
        GATE.compare_zip_to_checkout(archive, root)
