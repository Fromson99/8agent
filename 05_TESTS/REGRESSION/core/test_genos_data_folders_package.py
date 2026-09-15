"""Test new delivery against original, E2E and last schema delivery."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest
from . import test_genos_build_package as prior_tests

ROOT = prior_tests.ROOT
PATCH = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-data-folders-20260909.zip'
INSTALLER = ROOT / '06_TOOLS/COMMANDS/genos_apply_data_folders.sh'


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(prior_tests, 'PATCH', PATCH)
    monkeypatch.setattr(prior_tests, 'INSTALLER', INSTALLER)


@pytest.mark.parametrize('case', ['original', 'e2e', 'modified', 'symlink', 'corrupt'])
def test_delivery_safety(tmp_path, patched, case):
    prior_tests.test_patch_preserves_existing_state(tmp_path, case)


def test_isolated_new_zip(tmp_path, patched):
    prior_tests.test_mailed_bundle_plus_patch_runs_without_checkout_dependencies(tmp_path)


def test_previous_schema_patch_upgrade(tmp_path):
    root = tmp_path / 'DEV'; transfer = root / 'TRANSFER'; transfer.mkdir(parents=True)
    shutil.copyfile(PATCH, transfer / PATCH.name)
    shutil.copyfile(INSTALLER, transfer / INSTALLER.name)
    for archive in (prior_tests.PRIOR, ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-schema-build-20260909.zip'):
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if not name.endswith('/') and (name.startswith(('00_SYSTEM/', '02_BACKEND/', '06_TOOLS/', '07_DOCS/')) or name == 'service.py'):
                    p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(z.read(name))
    proc = subprocess.run(['bash', str(transfer / INSTALLER.name)], cwd=root,
                          env={**os.environ, 'GENOS_SCHEMA_BUILD_ROOT': str(root)}, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    with zipfile.ZipFile(PATCH) as z:
        for name, record in json.loads(z.read('patch-manifest.json'))['files'].items():
            assert hashlib.sha256((root / name).read_bytes()).hexdigest() == record['sha256']
    assert not (root / 'data').exists()  # Installer itself never starts models/data copy.


def test_fixed_paths_and_old_environment(tmp_path):
    root = tmp_path / 'DEV'
    script = root / '06_TOOLS/COMMANDS/genos_data.sh'
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / '06_TOOLS/COMMANDS/genos_data.sh', script)
    env = {**os.environ, 'GENOS_DATA_ROOT': '/wrong', 'GENOS_INPUT_ROOT': '/wrong'}
    p = subprocess.run(['bash', str(script), 'paths'], env=env, text=True, capture_output=True)
    assert p.returncode == 0 and str(root / 'data/corpus/internal') in p.stdout
    assert '/wrong' not in p.stdout and not (root / 'data').exists()


def test_setup_idempotent_layout_uses_explicit_bootstrap_root(tmp_path):
    root = tmp_path / 'DEV'
    script = root / '06_TOOLS/COMMANDS/genos_data.sh'
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / '06_TOOLS/COMMANDS/genos_data.sh', script)
    # Stub only the already-tested public-package bootstrap; inspect exact CLI boundary.
    script.with_name('genos_unified_pipeline.py').write_text(
        'import sys\nfrom pathlib import Path\n'
        'assert sys.argv[1:] == ["--data-root", str(Path.cwd()/"data"), "bootstrap-external"]\n')
    old = root / 'GENOS_DATA'; old.mkdir(); (old / 'keep').write_text('keep')
    for _ in range(2):
        p = subprocess.run(['bash', str(script), 'setup'], text=True, capture_output=True,
                           env={**os.environ, 'GENOS_DATA_ROOT': str(old)})
        assert p.returncode == 0, p.stdout + p.stderr
        assert (root / 'data/corpus/internal').is_dir()
        assert (root / 'data/.gitignore').read_text() == '*\n!.gitignore\n'
        assert (old / 'keep').read_text() == 'keep'
