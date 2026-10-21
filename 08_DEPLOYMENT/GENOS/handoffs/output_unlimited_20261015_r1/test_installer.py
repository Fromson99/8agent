"""Refuse drift and preserve recoverable backups for the output-token policy patch."""
import gzip
import importlib.util
import json
from pathlib import Path
import zipfile
import pytest

OUT = Path(__file__).resolve().parent
PRIOR = OUT.with_name('length_recovery_20261014_r1')
SOURCE = '02_BACKEND/semantic_runtime/legal_agent/model_contract.py'
spec = importlib.util.spec_from_file_location('output_unlimited_safety', OUT / 'apply_patch.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'DEV'
    root.mkdir()
    fixture = json.loads((PRIOR / 'FIXTURES.json').read_bytes())[0]
    archive = PRIOR / fixture['path']
    assert installer.sha(archive.read_bytes()) == fixture['sha256']
    with zipfile.ZipFile(archive) as z:
        z.extractall(root)
    p = OUT.with_name('length_recovery_20261015_r2')
    module_spec = importlib.util.spec_from_file_location('output_test_length_predecessor', p/'apply_patch.py')
    previous = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(previous)
    oldpatch = json.loads(gzip.decompress((p/'PATCH_SPEC.json.gz').read_bytes()))
    _, _, changes, _, _ = previous.prepared(root, oldpatch)
    for name, raw in changes.items():
        target = root/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    patch = json.loads(gzip.decompress((OUT / 'PATCH_SPEC.json.gz').read_bytes()))
    return root, patch


def snapshot(root):
    return {str(p.relative_to(root)): (installer.sha(p.read_bytes()), p.stat().st_mode & 0o777)
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()
            and '__pycache__' not in p.parts and 'TRANSFER' not in p.relative_to(root).parts}


@pytest.mark.parametrize('target', [SOURCE, 'service.py', '00_SYSTEM/PIPELINE.json'])
def test_unknown_changed_file_refused_before_write(setup, target):
    root, patch = setup
    path = root / target
    path.write_bytes(path.read_bytes() + b'\n# unapproved edit\n')
    before = snapshot(root)
    with pytest.raises(ValueError, match='CHECKOUT_DRIFT'):
        installer.prepared(root, patch)
    assert snapshot(root) == before


def test_symlink_refused_before_write(setup, tmp_path):
    root, patch = setup
    original = (root / SOURCE).read_bytes()
    external = tmp_path / 'external.py'
    external.write_bytes(original)
    (root / SOURCE).unlink()
    (root / SOURCE).symlink_to(external)
    with pytest.raises(ValueError, match='Symlink preserved'):
        installer.prepared(root, patch)
    assert external.read_bytes() == original and (root / SOURCE).is_symlink()


def test_preflight_does_not_write_and_signatures_bind_all_changed_sources(setup):
    root, patch = setup
    before = snapshot(root)
    installer.prepared(root, patch)
    assert snapshot(root) == before
    binding = json.loads((OUT / 'SOURCE_BINDING.json').read_bytes())
    assert len(patch['signatures']) == binding['known_predecessors']
    for row in patch['signatures'].values():
        assert set(row['patches']) == set(binding['source_files'])
        for name, change in row['patches'].items():
            assert binding['field_variants'][name][change['before_sha256']] == change['after_sha256']


@pytest.mark.parametrize('tamper_backup', [False, True])
def test_partial_apply_restores_or_refuses_tampered_backup(setup, monkeypatch, tamper_backup):
    root, patch = setup
    (root / SOURCE).chmod(0o640)
    before = snapshot(root)
    atomic = installer.atomic
    source_written = False

    def interrupt(path, raw, mode=None):
        nonlocal source_written
        if path == root / SOURCE:
            source_written = True
        elif source_written and path.is_relative_to(root) and 'TRANSFER' not in path.relative_to(root).parts:
            raise OSError('synthetic interrupted installation')
        atomic(path, raw, mode)

    monkeypatch.delenv('GENOS_GENERATION', raising=False)
    monkeypatch.setattr(installer, 'atomic', interrupt)
    with pytest.raises(OSError, match='synthetic interrupted'):
        installer.apply(root, patch, root / 'TRANSFER/output-unlimited-r1')
    monkeypatch.setattr(installer, 'atomic', atomic)
    backups = list((root / 'TRANSFER/output-unlimited-r1').glob('backup-*'))
    assert len(backups) == 1
    backup = backups[0]
    assert json.loads((backup / 'receipt.json').read_bytes())['state'] == 'PREPARED'
    if tamper_backup:
        saved = backup / SOURCE
        saved.write_bytes(saved.read_bytes() + b'\n# corrupted backup\n')
        interrupted = snapshot(root)
        with pytest.raises(ValueError, match='Backup hash mismatch'):
            installer.undo(root, backup)
        assert snapshot(root) == interrupted
    else:
        installer.undo(root, backup)
        assert snapshot(root) == before
        installer.undo(root, backup)
        assert snapshot(root) == before


def test_race_after_preflight_preserves_new_bytes(setup, monkeypatch):
    root, patch = setup
    before = snapshot(root)

    def change_during_identity(_):
        path = root / SOURCE
        path.write_bytes(path.read_bytes() + b'\n# concurrent edit\n')
        return {'synthetic': True}

    monkeypatch.setattr(installer, 'field_identity', change_during_identity)
    with pytest.raises(ValueError, match='Code changed during preparation'):
        installer.apply(root, patch, root / 'TRANSFER/output-unlimited-r1')
    after = snapshot(root)
    assert after[SOURCE] != before[SOURCE]
    assert {k: v for k, v in after.items() if k != SOURCE} == {k: v for k, v in before.items() if k != SOURCE}
