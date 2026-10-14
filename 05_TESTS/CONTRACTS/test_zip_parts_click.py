"""Exercise the shipped CMD files through real Windows cmd.exe and PowerShell."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT / "08_DEPLOYMENT/GENOS/handoffs/zip_parts_click_20261007_r2"
CMD = Path("/mnt/c/Windows/System32/cmd.exe")
WINDOWS_TEMP = Path("/mnt/c/Users/Jin/AppData/Local/Temp")
pytestmark = pytest.mark.skipif(not CMD.is_file(), reason="Windows cmd.exe/WSL unavailable")


def win(path: Path) -> str:
    return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory(prefix="8agent-zip-click-test-", dir=WINDOWS_TEMP) as tmp:
        folder = Path(tmp)
        launchers = folder / "downloaded scripts"
        desktop = folder / "mock OneDrive Desktop"
        launchers.mkdir()
        desktop.mkdir()
        for name in ("1_SPLIT_ZIP.cmd", "2_JOIN_ZIP.cmd"):
            shutil.copyfile(DELIVERY / name, launchers / name)
        yield launchers, desktop


def click(workspace, filename, answer, *, pause=False):
    launchers, desktop = workspace
    env = dict(os.environ)
    env["ZIP_PARTS_DESKTOP"] = win(desktop)
    env["ZIP_PARTS_NO_PAUSE"] = "0" if pause else "1"
    env["WSLENV"] = ":".join(filter(None, [env.get("WSLENV"), "ZIP_PARTS_DESKTOP", "ZIP_PARTS_NO_PAUSE"]))
    result = subprocess.run(
        [str(CMD), "/d", "/c", win(launchers / filename)], input=(answer + "\r\n" + ("\r\n" if pause else "")).encode("cp949"),
        capture_output=True, timeout=180, env=env,
    )
    return result.returncode, (result.stdout + result.stderr).decode("cp949", errors="replace")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("answer", ["한글 자료 [원본].zip", "한글 자료 [원본]", '"한글 자료 [원본].zip"'])
def test_name_only_round_trip_and_original_preserved(workspace, answer):
    _, desktop = workspace
    source = desktop / "한글 자료 [원본].zip"
    source.write_bytes(os.urandom(2_000_017))
    expected = sha(source)
    code, log = click(workspace, "1_SPLIT_ZIP.cmd", answer)
    assert code == 0, log
    parts = desktop / (source.name + ".parts")
    assert (parts / "parts-manifest.json").is_file()
    code, log = click(workspace, "2_JOIN_ZIP.cmd", answer)
    assert code == 0, log
    assert sha(desktop / "한글 자료 [원본]_restored.zip") == expected == sha(source)


def test_join_folder_name_and_existing_output(workspace):
    _, desktop = workspace
    source = desktop / "data.zip"
    source.write_bytes(b"synthetic content")
    code, log = click(workspace, "1_SPLIT_ZIP.cmd", "data")
    assert code == 0, log
    existing = desktop / "data_restored.zip"
    existing.write_bytes(b"keep existing")
    code, log = click(workspace, "2_JOIN_ZIP.cmd", "data.zip.parts")
    assert code == 0, log
    assert existing.read_bytes() == b"keep existing"
    outputs = list(desktop.glob("data_restored_*.zip"))
    assert len(outputs) == 1 and sha(outputs[0]) == sha(source)


@pytest.mark.parametrize("answer", ["missing.zip", "../outside.zip", "..", "", "x.zip & echo injected"])
def test_invalid_or_missing_input_never_creates_parts(workspace, answer):
    _, desktop = workspace
    code, _ = click(workspace, "1_SPLIT_ZIP.cmd", answer)
    assert code != 0
    assert list(desktop.iterdir()) == []


def test_damaged_part_is_not_published(workspace):
    _, desktop = workspace
    source = desktop / "data.zip"
    source.write_bytes(b"original content")
    code, log = click(workspace, "1_SPLIT_ZIP.cmd", "data.zip")
    assert code == 0, log
    part = desktop / "data.zip.parts/data.zip.part0001"
    part.write_bytes(b"X" + part.read_bytes()[1:])
    code, _ = click(workspace, "2_JOIN_ZIP.cmd", "data.zip")
    assert code != 0
    assert not (desktop / "data_restored.zip").exists()


def test_49mb_boundary(workspace):
    _, desktop = workspace
    source = desktop / "boundary.zip"
    with source.open("wb") as stream:
        stream.write(b"start")
        stream.seek(49_000_000)
        stream.write(b"last")
    code, log = click(workspace, "1_SPLIT_ZIP.cmd", "boundary")
    assert code == 0, log
    parts = list((desktop / "boundary.zip.parts").glob("*.part*"))
    assert sorted(p.stat().st_size for p in parts) == [4, 49_000_000]
    code, log = click(workspace, "2_JOIN_ZIP.cmd", "boundary")
    assert code == 0, log
    assert sha(desktop / "boundary_restored.zip") == sha(source)


def test_completion_waits_for_enter_and_split_repeat_preserves_parts(workspace):
    _, desktop = workspace
    source = desktop / "data.zip"
    source.write_bytes(b"original bytes")
    code, log = click(workspace, "1_SPLIT_ZIP.cmd", "data", pause=True)
    assert code == 0, log
    assert "Enter" in log, log
    manifest = desktop / "data.zip.parts/parts-manifest.json"
    before = manifest.read_bytes()
    code, _ = click(workspace, "1_SPLIT_ZIP.cmd", "data")
    assert code != 0
    assert manifest.read_bytes() == before
    assert source.read_bytes() == b"original bytes"
