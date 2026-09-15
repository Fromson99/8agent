"""Data-only delivery contracts; fake models and temporary installations only."""
import os
import shutil
import subprocess
import zipfile
import json
import pytest
from . import test_genos_latest_compatible as prior
from .test_genos_latest_compatible import (
    test_install_latest_preserved_and_registry_closed,
    test_failure_is_prewrite_and_unknowns_all_reported,
    test_crlf_known_version_and_check_only,
    test_exact_zip_isolated_full_build,
    test_latest_mail_bytes_and_python311_syntax,
    test_failed_second_write_rolls_back,
    test_python311_installed_entrypoints,
)

ROOT = prior.ROOT
PATCH = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-data-e2e-20260910.zip'
INSTALLER = ROOT / '06_TOOLS/COMMANDS/genos_apply_data_e2e.sh'


@pytest.fixture(autouse=True)
def delivered(monkeypatch):
    monkeypatch.setattr(prior, 'PATCH', PATCH)
    monkeypatch.setattr(prior, 'INSTALLER', INSTALLER)
    monkeypatch.setattr(prior, 'LATEST', ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-qwen-response-fix-20260910.zip')


@pytest.mark.parametrize('arguments,expected,code', [
    ([], ['--check-only'], 0),
    (['--run-id', 'data-001', '--check-only'], ['--run-id', 'data-001', '--check-only'], 0),
    (['--run-id', 'data-001', '--execute', '--embed-batch-size', '64'], ['--run-id', 'data-001', '--embed-batch-size', '64'], 0),
    (['--execute', '--resume'], ['--resume'], 0),
    (['--execute', '--check-only'], [], 2),
    (['--resume'], [], 2),
])
def test_shell_modes(tmp_path, arguments, expected, code):
    commands = tmp_path / '06_TOOLS/COMMANDS'
    commands.mkdir(parents=True)
    script = commands / 'genos_data_e2e.sh'
    # Historical delivery contract: later DOC/skip CLI changes are tested separately.
    with zipfile.ZipFile(PATCH) as z:
        script.write_bytes(z.read('06_TOOLS/COMMANDS/genos_data_e2e.sh'))
    (commands / 'genos_build_all.sh').write_text('printf "ARG:%s\\n" "$@"\nexit 0\n')
    result = subprocess.run(['bash', str(script), *arguments], text=True, capture_output=True)
    assert result.returncode == code, result.stdout + result.stderr
    actual = [line[4:] for line in result.stdout.splitlines() if line.startswith('ARG:')]
    assert actual == expected


def test_shell_keeps_failure_exit(tmp_path):
    commands = tmp_path / '06_TOOLS/COMMANDS'
    commands.mkdir(parents=True)
    script = commands / 'genos_data_e2e.sh'
    with zipfile.ZipFile(PATCH) as z:
        script.write_bytes(z.read('06_TOOLS/COMMANDS/genos_data_e2e.sh'))
    (commands / 'genos_build_all.sh').write_text('exit 17\n')
    result = subprocess.run(['bash', str(script), '--execute'], capture_output=True)
    assert result.returncode == 17


def test_data_algorithms_unchanged_no_new_oql():
    with zipfile.ZipFile(PATCH) as z, zipfile.ZipFile(ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-all-corpus-compatible-20260910.zip') as old:
        manifest = json.loads(z.read('patch-manifest.json'))
        assert manifest['scope'] == 'DATA_BUILD_ONLY_NO_OQL_NO_ANSWER'
        for name in ('02_BACKEND/lawrag/pipeline/genos_build.py', '02_BACKEND/lawrag/pipeline/genos_corpus.py',
                     '06_TOOLS/COMMANDS/genos_build_all.py', '06_TOOLS/COMMANDS/genos_build_all.sh'):
            assert z.read(name) == old.read(name)
        assert not any('adr_0318' in n or 'adr_0319' in n or 'adr_0327' in n for n in z.namelist())
        assert not any(n.startswith(('data/', '01_DATA/', '.git/', '.env')) for n in z.namelist())


def test_previous_compatible_then_qwen_then_new_install(tmp_path):
    root = prior.host(tmp_path, latest=True)
    result = prior.run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    with zipfile.ZipFile(ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-qwen-response-fix-20260910.zip') as z:
        for name in z.namelist():
            assert (root / name).read_bytes() == z.read(name)
