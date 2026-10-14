"""Real Windows PowerShell 5.1 file round trips; runs from repository WSL Python."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT / "08_DEPLOYMENT/GENOS/handoffs/zip_parts_20261007_r1"
POWERSHELL = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
WINDOWS_TEMP = Path("/mnt/c/Users/Jin/AppData/Local/Temp")
pytestmark = pytest.mark.skipif(not POWERSHELL.is_file(), reason="Windows PowerShell/WSL unavailable")


def windows_path(path: Path) -> str:
    return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory(prefix="8agent-zip-parts-test-", dir=WINDOWS_TEMP) as tmp:
        directory = Path(tmp)
        for name in ("Split-ZipParts.ps1", "Join-ZipParts.ps1"):
            shutil.copyfile(DELIVERY / name, directory / name)
        yield directory


def ps(workspace: Path, script: str, **parameters):
    command = [str(POWERSHELL), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", windows_path(workspace / script)]
    for key, value in parameters.items():
        command.extend(["-" + key, windows_path(value) if isinstance(value, Path) else str(value)])
    result = subprocess.run(command, capture_output=True, timeout=240)
    return result.returncode, (result.stdout + result.stderr).decode("cp949", errors="replace")


def split(workspace: Path, source: Path, chunk=1):
    parts = workspace / "parts"
    code, output = ps(workspace, "Split-ZipParts.ps1", InputFile=source, OutputDirectory=parts, ChunkSizeMB=chunk)
    assert code == 0, output
    return parts, json.loads((parts / "parts-manifest.json").read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.mark.parametrize("size", [0, 17, 999_999, 1_000_000, 1_000_001, 3_000_021])
def test_round_trip_boundaries_and_unicode(workspace, size):
    source = workspace / "한글 자료 [원본].zip"
    source.write_bytes(os.urandom(size))
    parts, manifest = split(workspace, source)
    assert len(manifest["parts"]) == (size + 999_999) // 1_000_000
    assert all(row["bytes"] <= 1_000_000 for row in manifest["parts"])
    output = workspace / "복원 자료 [검증].zip"
    code, log = ps(workspace, "Join-ZipParts.ps1", PartsDirectory=parts, OutputFile=output)
    assert code == 0, log
    assert output.stat().st_size == size
    assert digest(output) == digest(source) == manifest["archive_sha256"]


def test_real_zip_default_49_decimal_mb(workspace):
    source = workspace / "nfs data.zip"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("한글/데이터.bin", b"test data\n" * 5_600_000)
    parts = workspace / "default parts"
    code, log = ps(workspace, "Split-ZipParts.ps1", InputFile=source, OutputDirectory=parts)
    assert code == 0, log
    manifest = json.loads((parts / "parts-manifest.json").read_text())
    assert manifest["part_max_bytes"] == 49_000_000
    assert len(manifest["parts"]) == 2
    assert all((parts / row["name"]).stat().st_size < 50_000_000 for row in manifest["parts"])
    output = workspace / "restored.zip"
    code, log = ps(workspace, "Join-ZipParts.ps1", PartsDirectory=parts, OutputFile=output)
    assert code == 0, log
    assert digest(output) == digest(source)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None


@pytest.mark.parametrize("damage", ["missing", "truncated", "corrupted", "duplicate", "traversal", "order", "original_hash", "oversized"])
def test_damaged_transfer_never_publishes_zip(workspace, damage):
    source = workspace / "data.zip"
    source.write_bytes(os.urandom(1_000_010))
    parts, manifest = split(workspace, source)
    first = parts / manifest["parts"][0]["name"]
    if damage == "missing":
        first.unlink()
    elif damage == "truncated":
        first.write_bytes(first.read_bytes()[:-1])
    elif damage == "corrupted":
        raw = bytearray(first.read_bytes())
        raw[0] ^= 1
        first.write_bytes(raw)
    elif damage == "duplicate":
        manifest["parts"][1]["name"] = manifest["parts"][0]["name"]
    elif damage == "traversal":
        manifest["parts"][0]["name"] = "../data.zip"
    elif damage == "order":
        manifest["parts"].reverse()
    elif damage == "original_hash":
        manifest["archive_sha256"] = "0" * 64
    elif damage == "oversized":
        manifest["part_max_bytes"] = 50_000_001
    (parts / "parts-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    output = workspace / "restored.zip"
    code, _ = ps(workspace, "Join-ZipParts.ps1", PartsDirectory=parts, OutputFile=output)
    assert code != 0
    assert not output.exists()
    assert digest(source) == manifest["archive_sha256"] or damage == "original_hash"


def test_existing_outputs_are_preserved(workspace):
    source = workspace / "data.zip"
    source.write_bytes(b"original bytes")
    parts, _ = split(workspace, source)
    code, _ = ps(workspace, "Split-ZipParts.ps1", InputFile=source, OutputDirectory=parts)
    assert code != 0
    output = workspace / "restored.zip"
    output.write_bytes(b"keep this")
    code, _ = ps(workspace, "Join-ZipParts.ps1", PartsDirectory=parts, OutputFile=output)
    assert code != 0
    assert output.read_bytes() == b"keep this"


def test_windows_split_linux_join(workspace, tmp_path):
    source = workspace / "자료.zip"
    source.write_bytes(os.urandom(1_000_100))
    parts, manifest = split(workspace, source)
    spec = importlib.util.spec_from_file_location("join_zip_parts", DELIVERY / "Join-ZipParts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "restored.zip"
    module.restore(parts, output)
    assert digest(output) == digest(source)
    first = parts / manifest["parts"][0]["name"]
    raw = bytearray(first.read_bytes())
    raw[0] ^= 1
    first.write_bytes(raw)
    with pytest.raises(ValueError, match="hash/size"):
        module.restore(parts, tmp_path / "bad.zip")
    assert not (tmp_path / "bad.zip").exists()


@pytest.mark.skipif(os.environ.get("ZIP_PARTS_GIGABYTE_TEST") != "1", reason="Opt-in gigabyte I/O check")
def test_gigabyte_round_trip(workspace):
    source = workspace / "gigabyte.zip"
    with source.open("wb") as stream:
        stream.write(b"start marker")
        stream.seek(49_000_000)
        stream.write(b"second part marker")
        stream.seek(1_000_000_016)
        stream.write(b"Z")
    parts, manifest = split(workspace, source, chunk=49)
    assert len(manifest["parts"]) == 21
    assert all(row["bytes"] <= 49_000_000 for row in manifest["parts"])
    output = workspace / "gigabyte-restored.zip"
    code, log = ps(workspace, "Join-ZipParts.ps1", PartsDirectory=parts, OutputFile=output)
    assert code == 0, log
    assert output.stat().st_size == 1_000_000_017
    assert digest(output) == digest(source)
