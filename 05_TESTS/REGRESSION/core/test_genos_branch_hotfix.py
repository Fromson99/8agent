"""Offline checks for the field installer against the actual shipped ZIP."""
import ast
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
SCRIPT = ROOT / 'genos_branch_hotfix.sh'
ZIP = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-unified-dev-root-20260908.zip'
NAMES = {'endpoint', 'from_env', 'request_json', 'check'}


def functions(source):
    lines = source.splitlines(keepends=True)
    return {n.name: ''.join(lines[n.lineno - 1:n.end_lineno])
            for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}


@pytest.mark.parametrize('requests_patch', [False, True])
def test_installs_on_shipped_zip_preserves_other_code_and_is_repeatable(tmp_path, requests_patch):
    if not ZIP.is_file():
        pytest.skip('local handoff ZIP unavailable')
    with zipfile.ZipFile(ZIP) as archive:
        original = archive.read('02_BACKEND/semantic_runtime/genos.py').decode()
    if requests_patch:
        original = original.replace('client.trust_env = False', 'client.trust_env = True')
        original = original.replace('allow_redirects=False', 'allow_redirects=True')
    (tmp_path / 'service.py').touch()
    target = tmp_path / '02_BACKEND/semantic_runtime/genos.py'
    target.parent.mkdir(parents=True)
    target.write_text(original)
    target.chmod(0o640)
    (tmp_path / '.venv').symlink_to(sys.prefix, target_is_directory=True)
    env = {**os.environ, 'GENOS_CODE_ROOT': str(tmp_path)}
    for _ in range(2):
        run = subprocess.run(['bash', str(SCRIPT), '--patch-only'], env=env,
                             capture_output=True, text=True, timeout=15)
        assert run.returncode == 0, run.stdout + run.stderr
    patched = functions(target.read_text())
    expected = functions((ROOT / '02_BACKEND/semantic_runtime/genos.py').read_text())
    for name, source in functions(original).items():
        assert patched[name] == (expected[name] if name in NAMES else source)
    backups = list(target.parent.glob('*.bak'))
    assert len(backups) == 1
    assert backups[0].read_text() == original
    assert target.stat().st_mode & 0o777 == 0o640
    # Unknown edits must not get overwritten by a whole-function patch.
    changed = target.read_text().replace('model = configured or "genos"', 'model = configured or "custom"')
    target.write_text(changed)
    run = subprocess.run(['bash', str(SCRIPT), '--patch-only'], env=env,
                         capture_output=True, text=True, timeout=15)
    assert run.returncode != 0
    assert target.read_text() == changed
    assert len(list(target.parent.glob('*.bak'))) == 1


def test_embedded_programs_compile_and_use_branch_httpx():
    source = SCRIPT.read_text()
    for tag in ('PATCHPY', 'PY'):
        embedded = source.split("<<'" + tag + "'\n", 1)[1].split('\n' + tag + '\n', 1)[0]
        compile(embedded, tag, 'exec')
    assert "with httpx.Client(trust_env=True, follow_redirects=False) as client:" in embedded
    assert "client.stream('GET'" in embedded
    assert 'iter_bytes' in embedded
    assert 'import requests' not in embedded
    assert 'verify=False' not in source
    assert '30908' not in source and '32154' not in source
