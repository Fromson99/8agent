"""Actual standalone Bash TXT split/join, using synthetic TRANSFER directories."""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT / "08_DEPLOYMENT/GENOS/handoffs/zip_parts_bash_20261007_r4"


def invoke(name, root, arg=None, typed=None):
    env = dict(os.environ, ZIP_TRANSFER_DIR=str(root), LC_ALL="C.UTF-8")
    command = ["bash", str(DELIVERY / name)]
    if arg is not None:
        command.append(arg)
    return subprocess.run(command, cwd=root, env=env, input=typed, text=True, capture_output=True, timeout=120)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.mark.parametrize("size", [17, 49_000_000, 49_000_019, 98_000_004])
def test_round_trip_boundary_and_unicode(tmp_path, size):
    source = tmp_path / "자료 [원본] (1).zip"
    with source.open("wb") as stream:
        stream.write(b"start")
        stream.seek(size-1)
        stream.write(b"Z")
    before = digest(source)
    result = invoke("SPLIT_TRANSFER_ZIP.txt", tmp_path, source.name)
    assert result.returncode == 0, result.stdout + result.stderr
    parts = tmp_path / (source.name + ".parts")
    fragments = list(parts.glob("*.part*"))
    assert len(fragments) == (size + 48_999_999) // 49_000_000
    assert all(p.stat().st_size <= 49_000_000 for p in fragments)
    result = invoke("JOIN_TRANSFER_ZIP.txt", tmp_path, str(parts))
    assert result.returncode == 0, result.stdout + result.stderr
    restored = tmp_path / "자료 [원본] (1)_restored.zip"
    assert digest(restored) == before == digest(source)


@pytest.mark.parametrize("damage", ["missing", "corrupt", "extra", "original_hash"])
def test_damaged_transfer_not_published(tmp_path, damage):
    source = tmp_path / "data.zip"
    source.write_bytes(b"original content")
    result = invoke("SPLIT_TRANSFER_ZIP.txt", tmp_path, "data")
    assert result.returncode == 0, result.stderr
    parts = tmp_path / "data.zip.parts"
    part = parts / "data.zip.part000000"
    if damage == "missing":
        part.unlink()
    elif damage == "corrupt":
        part.write_bytes(b"X" + part.read_bytes()[1:])
    elif damage == "extra":
        (parts / "data.zip.part000001").write_bytes(b"extra bytes")
    else:
        (parts / "ORIGINAL.sha256").write_text("0" * 64 + "  data.zip\n")
    result = invoke("JOIN_TRANSFER_ZIP.txt", tmp_path, str(parts))
    assert result.returncode != 0
    assert not (tmp_path / "data_restored.zip").exists()


def test_existing_outputs_and_prompt(tmp_path):
    source = tmp_path / "data.zip"
    source.write_bytes(b"original content")
    result = invoke("SPLIT_TRANSFER_ZIP.txt", tmp_path, typed="data.zip\n")
    assert result.returncode == 0, result.stderr
    parts = tmp_path / "data.zip.parts"
    before = (parts / "PARTS.sha256").read_bytes()
    result = invoke("SPLIT_TRANSFER_ZIP.txt", tmp_path, "data.zip")
    assert result.returncode != 0
    assert (parts / "PARTS.sha256").read_bytes() == before
    existing = tmp_path / "data_restored.zip"
    existing.write_bytes(b"keep existing")
    result = invoke("JOIN_TRANSFER_ZIP.txt", tmp_path, typed=str(parts) + "\n")
    assert result.returncode != 0
    assert existing.read_bytes() == b"keep existing"


@pytest.mark.parametrize("arg", ["missing", "../data.zip", "../", "..", "data\\fake.zip"])
def test_invalid_input_rejected(tmp_path, arg):
    result = invoke("SPLIT_TRANSFER_ZIP.txt", tmp_path, arg)
    assert result.returncode != 0
    assert not list(tmp_path.glob("*.parts"))
    assert not list(tmp_path.glob("*.partial-*"))
