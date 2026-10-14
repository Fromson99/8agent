"""Test plain-text interactive source without renaming or creating executable files."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT / "08_DEPLOYMENT/GENOS/handoffs/zip_parts_text_20261007_r3"
PS = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
TEMP = Path("/mnt/c/Users/Jin/AppData/Local/Temp")
pytestmark = pytest.mark.skipif(not PS.is_file(), reason="Windows PowerShell/WSL unavailable")


def win(path):
    return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()


@pytest.fixture
def desktop():
    with tempfile.TemporaryDirectory(prefix="8agent-zip-text-test-", dir=TEMP) as tmp:
        path = Path(tmp)
        for name in ("ZIP_SPLIT_RUN.txt", "ZIP_JOIN_RUN.txt"):
            shutil.copyfile(DELIVERY / name, path / name)
        yield path


def run(desktop, filename, answer, pause=False):
    env = dict(os.environ)
    env["ZIP_PARTS_DESKTOP"] = win(desktop)
    env["ZIP_PARTS_NO_PAUSE"] = "0" if pause else "1"
    env["WSLENV"] = ":".join(filter(None, [env.get("WSLENV"), "ZIP_PARTS_DESKTOP", "ZIP_PARTS_NO_PAUSE"]))
    # Same ReadAllText -> ScriptBlock invocation shown in email; test desktop substituted.
    command = "& ([scriptblock]::Create([IO.File]::ReadAllText('" + win(desktop / filename).replace("'", "''") + "')))"
    result = subprocess.run(
        [str(PS), "-NoLogo", "-NoProfile", "-Command", command], env=env,
        input=(answer + "\r\n" + ("\r\n" if pause else "")).encode("cp949"),
        capture_output=True, timeout=180,
    )
    return result.returncode, (result.stdout + result.stderr).decode("cp949", errors="replace")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("answer", ["한글 자료.zip", "한글 자료", '"한글 자료.zip"'])
def test_plain_text_round_trip(desktop, answer):
    source = desktop / "한글 자료.zip"
    source.write_bytes(os.urandom(2_000_017))
    expected = sha(source)
    code, log = run(desktop, "ZIP_SPLIT_RUN.txt", answer)
    assert code == 0, log
    code, log = run(desktop, "ZIP_JOIN_RUN.txt", answer, pause=True)
    assert code == 0, log
    assert "Enter" in log
    assert sha(desktop / "한글 자료_restored.zip") == expected == sha(source)
    assert not list(desktop.glob("*.cmd")) and not list(desktop.glob("*.ps1"))


def test_corrupt_input_and_existing_output_preserved(desktop):
    source = desktop / "data.zip"
    source.write_bytes(b"original bytes")
    code, log = run(desktop, "ZIP_SPLIT_RUN.txt", "data")
    assert code == 0, log
    previous = desktop / "data_restored.zip"
    previous.write_bytes(b"keep existing")
    code, log = run(desktop, "ZIP_JOIN_RUN.txt", "data.zip.parts")
    assert code == 0, log
    assert previous.read_bytes() == b"keep existing"
    assert len(list(desktop.glob("data_restored_*.zip"))) == 1
    part = desktop / "data.zip.parts/data.zip.part0001"
    part.write_bytes(b"X" + part.read_bytes()[1:])
    code, _ = run(desktop, "ZIP_JOIN_RUN.txt", "data")
    assert code != 0
    assert len(list(desktop.glob("data_restored_*.zip"))) == 1


@pytest.mark.parametrize("answer", ["not-here", "../data.zip", ""])
def test_missing_or_invalid_name_fails(desktop, answer):
    code, _ = run(desktop, "ZIP_SPLIT_RUN.txt", answer)
    assert code != 0
    assert not list(desktop.glob("*.parts"))
