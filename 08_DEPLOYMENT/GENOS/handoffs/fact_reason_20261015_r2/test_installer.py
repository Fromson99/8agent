"""Refuse drift and preserve recoverable backups for the narrow display patch."""
import gzip
import importlib.util
import json
from pathlib import Path
import zipfile
import pytest

OUT = Path(__file__).resolve().parent
PRIOR = OUT
SOURCE = '02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py'
spec = importlib.util.spec_from_file_location('fact_reason_safety', OUT / 'apply_patch.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'DEV'
    root.mkdir()
    fixture = next(r for r in json.loads((PRIOR / 'FIXTURES.json').read_bytes()) if r['kind'] == 'field_signature')
    archive = PRIOR / fixture['path']
    assert installer.sha(archive.read_bytes()) == fixture['sha256']
    with zipfile.ZipFile(archive) as z:
        z.extractall(root)
    patch = json.loads(gzip.decompress((OUT / 'PATCH_SPEC.json.gz').read_bytes()))
    config = root / installer.CONFIG
    if config.exists():
        generation = tmp_path / 'synthetic-generation'
        generation.mkdir()
        (generation / 'manifest.json').write_bytes(b'{}\n')
        digest = installer.sha((generation / 'manifest.json').read_bytes())
        value = json.loads(config.read_bytes())
        value.update(generation=str(generation), runtime=str(tmp_path / 'runtime'), generation_manifest_sha256=digest)
        config.write_bytes(installer.encoded(value))
        cm = root / 'CODE_MANIFEST.json'
        manifest = json.loads(cm.read_bytes())
        manifest['cm_oneclick']['generation_manifest_sha256'] = digest
        for row in manifest['files']:
            if row['path'] == installer.CONFIG:
                row.update(sha256=installer.sha(config.read_bytes()), bytes=config.stat().st_size)
        cm.write_bytes(installer.encoded(manifest))
    return root, patch


def snapshot(root):
    return {str(p.relative_to(root)): (installer.sha(p.read_bytes()), p.stat().st_mode & 0o777)
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()
            and '__pycache__' not in p.parts and 'TRANSFER' not in p.relative_to(root).parts}


def test_photo_inventory_rejected_by_r1_supported_by_r2_without_writes(setup):
    root, patch = setup
    manifest = json.loads((root / 'CODE_MANIFEST.json').read_bytes())
    key = installer.signature(installer.inventory(root, manifest), manifest, patch)
    assert key == '7e3b5d20b21d33cd6e667896fdd023a9842b1c2d82dbef81892438e0b92b9686'
    prior = OUT.with_name('fact_reason_20261015_r1')
    old_patch = json.loads(gzip.decompress((prior / 'PATCH_SPEC.json.gz').read_bytes()))
    assert key not in old_patch['signatures'] and key in patch['signatures']
    before = snapshot(root)
    with pytest.raises(ValueError, match='Known complete GENOS/CM'):
        installer.prepared(root, old_patch)
    installer.prepared(root, patch)
    assert snapshot(root) == before


def test_every_sealed_branch_covered_and_r1_entries_unchanged(setup):
    _, patch = setup
    prior = OUT.with_name('fact_reason_20261015_r1')
    old_patch = json.loads(gzip.decompress((prior / 'PATCH_SPEC.json.gz').read_bytes()))
    assert len(patch['signatures']) == 2310
    assert len(set(patch['signatures']) - set(old_patch['signatures'])) == 660
    assert patch['blobs'] == old_patch['blobs']
    assert all(patch['signatures'][key] == value for key, value in old_patch['signatures'].items())
    for folder in ('tool_availability_20261014_r1', 'tool_recovery_20261014_r1', 'length_recovery_20261015_r2'):
        transition = json.loads(gzip.decompress((OUT.with_name(folder) / 'PATCH_SPEC.json.gz').read_bytes()))
        assert {v['output_signature'] for v in transition['signatures'].values()} <= set(patch['signatures'])


def test_unknown_self_consistent_inventory_still_refused(setup):
    root, patch = setup
    path = '00_SYSTEM/UNKNOWN_DIAGNOSTIC_TEST.json'
    raw = b'{}\n'
    (root / path).write_bytes(raw)
    cm = root / 'CODE_MANIFEST.json'
    manifest = json.loads(cm.read_bytes())
    manifest['files'].append({'path': path, 'sha256': installer.sha(raw), 'bytes': len(raw)})
    cm.write_bytes(installer.encoded(manifest))
    before = snapshot(root)
    with pytest.raises(ValueError, match='actual_signature='):
        installer.prepared(root, patch)
    assert snapshot(root) == before


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


def test_preflight_does_not_write_and_all_signatures_change_only_one_source(setup):
    root, patch = setup
    before = snapshot(root)
    installer.prepared(root, patch)
    assert snapshot(root) == before
    binding = json.loads((OUT / 'SOURCE_BINDING.json').read_bytes())
    assert len(patch['signatures']) == binding['known_predecessors']
    for row in patch['signatures'].values():
        assert set(row['patches']) == {SOURCE}
        assert row['patches'][SOURCE]['before_sha256'] == binding['preimage_files'][SOURCE]
        assert row['patches'][SOURCE]['after_sha256'] == binding['source_files'][SOURCE]


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
        installer.apply(root, patch, root / 'TRANSFER/fact-reason-r2')
    monkeypatch.setattr(installer, 'atomic', atomic)
    backups = list((root / 'TRANSFER/fact-reason-r2').glob('backup-*'))
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
        installer.apply(root, patch, root / 'TRANSFER/fact-reason-r2')
    after = snapshot(root)
    assert after[SOURCE] != before[SOURCE]
    assert {k: v for k, v in after.items() if k != SOURCE} == {k: v for k, v in before.items() if k != SOURCE}
