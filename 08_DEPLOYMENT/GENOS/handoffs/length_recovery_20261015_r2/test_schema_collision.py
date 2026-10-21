"""Check exact preimages, refusal before writes, and physical-file rollback."""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import zipfile

import pytest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
PRIOR = OUT.with_name('length_recovery_20261014_r1')
RUN = OUT / 'GENOS_LENGTH_RECOVERY_20261015_R2_RUN.txt'
SCHEMA = '00_SYSTEM/SCHEMAS/pipeline-v1.schema.json'
ENGINE_SCHEMA = '00_SYSTEM/SCHEMAS/pipeline-engine-v1.schema.json'
spec = importlib.util.spec_from_file_location('schema_r2_installer', OUT / 'apply_patch.py')
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
    patch = json.loads(gzip.decompress((OUT / 'PATCH_SPEC.json.gz').read_bytes()))
    return root, patch


def add_schema(root, patch, name=SCHEMA, origin='git_commit'):
    rules = patch['unrecorded_schema_preimages'][name]
    digest = next(h for h, r in rules.items() if any(origin in e for e in r['evidence']))
    raw = (OUT / 'known-preimages' / digest).read_bytes()
    target = root / name
    target.parent.mkdir(exist_ok=True, parents=True)
    target.write_bytes(raw)
    target.chmod(0o640)
    return raw


def snapshot(root):
    return {str(p.relative_to(root)): (installer.sha(p.read_bytes()), p.stat().st_mode & 0o777)
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()
            and '__pycache__' not in p.parts
            and not str(p.relative_to(root)).startswith('TRANSFER/')
            and p.name != '.genos-code-replacement.lock'}


@pytest.mark.parametrize('mode', ['absent', 'historical_one', 'historical_both', 'target_both'])
def test_preflight_and_standalone_install_restore(setup, tmp_path, mode):
    root, patch = setup
    if mode != 'absent':
        for name in (SCHEMA,) if mode == 'historical_one' else (SCHEMA, ENGINE_SCHEMA):
            add_schema(root, patch, name, 'sealed_delivery' if mode == 'target_both' else 'git_commit')
    before = snapshot(root)
    prepared = installer.prepared(root, patch)
    assert snapshot(root) == before
    expected_count = {'absent': 0, 'historical_one': 1, 'historical_both': 2, 'target_both': 2}[mode]
    assert len(prepared[-1]) == expected_count
    transfer = tmp_path / 'actual-TRANSFER'
    transfer.mkdir()
    env = {**os.environ, 'GENOS_DEV_ROOT': str(root), 'GENOS_PYTHON_DIR': str(ROOT / '.venv/bin')}
    env.pop('GENOS_GENERATION', None)
    env.pop('GENOS_PATCH_DEV', None)
    rows = []
    def run(*args):
        result = subprocess.run(['bash', str(RUN), *args], cwd=transfer, env=env,
                                capture_output=True, text=True, timeout=60)
        rows.append({'argv': list(args), 'returncode': result.returncode,
                     'stdout': result.stdout, 'stderr': result.stderr})
        (OUT / ('COLLISION_' + mode + '.json.gz')).write_bytes(gzip.compress(installer.encoded(rows), mtime=0))
        assert result.returncode == 0, result.stdout + result.stderr
    run('install')
    run('install')
    backups = list((root / 'TRANSFER/length-recovery-r2').glob('backup-*'))
    assert len(backups) == 1
    assert len(json.loads((backups[0] / 'receipt.json').read_bytes())['adopted_unrecorded_files']) == expected_count
    run('undo', str(backups[0]))
    assert snapshot(root) == before
    run('undo', str(backups[0]))
    assert snapshot(root) == before


@pytest.mark.parametrize('kind', ['unknown_schema', 'unknown_engine_schema', 'unknown_module', 'symlink', 'directory', 'tracked_drift'])
def test_unknown_or_unsafe_preimage_refused_without_code_write(setup, tmp_path, kind):
    root, patch = setup
    target = root / SCHEMA
    target.parent.mkdir(exist_ok=True, parents=True)
    if kind == 'symlink':
        external = tmp_path / 'external.json'
        external.write_text('{}')
        target.symlink_to(external)
    elif kind == 'directory':
        target.mkdir()
    elif kind == 'tracked_drift':
        target = root / 'service.py'
        target.write_bytes(target.read_bytes() + b'\n# changed\n')
    else:
        name = {'unknown_schema': SCHEMA, 'unknown_engine_schema': ENGINE_SCHEMA,
                'unknown_module': '02_BACKEND/semantic_runtime/legal_agent/tool_outcome.py'}[kind]
        target = root / name
        target.write_text('{"unapproved": true}\n')
    before = snapshot(root)
    for _ in range(2):
        with pytest.raises(ValueError) as failure:
            installer.apply(root, patch, root / 'TRANSFER/length-recovery-r2')
        if kind.startswith('unknown'):
            assert 'UNRECORDED_FILE_UNKNOWN' in str(failure.value)
            assert installer.sha(target.read_bytes()) in str(failure.value)
        assert snapshot(root) == before
        assert not (root / 'TRANSFER/length-recovery-r2').exists()


def test_collision_race_refused_before_code_mutation(setup, monkeypatch):
    root, patch = setup
    add_schema(root, patch)
    original = snapshot(root)
    def change_during_identity(_):
        (root / SCHEMA).write_bytes((root / SCHEMA).read_bytes() + b'\n')
        return {'synthetic': True}
    monkeypatch.setattr(installer, 'field_identity', change_during_identity)
    with pytest.raises(ValueError, match='Code changed during preparation'):
        installer.apply(root, patch, root / 'TRANSFER/length-recovery-r2')
    after = snapshot(root)
    assert {k: v for k, v in after.items() if k != SCHEMA} == {k: v for k, v in original.items() if k != SCHEMA}
    assert after[SCHEMA] != original[SCHEMA]


def test_original_r1_reproduces_screenshot_without_writes(setup):
    root, patch = setup
    add_schema(root, patch)
    old_spec = importlib.util.spec_from_file_location('schema_r1_installer', PRIOR / 'apply_patch.py')
    old = importlib.util.module_from_spec(old_spec)
    old_spec.loader.exec_module(old)
    old_patch = json.loads(gzip.decompress((PRIOR / 'PATCH_SPEC.json.gz').read_bytes()))
    before = snapshot(root)
    with pytest.raises(ValueError, match='Unrecorded new module already exists; preserved: ' + SCHEMA):
        old.prepared(root, old_patch)
    assert snapshot(root) == before


def test_product_and_all_predecessor_bindings_identical():
    before = json.loads(gzip.decompress((PRIOR / 'PATCH_SPEC.json.gz').read_bytes()))
    after = json.loads(gzip.decompress((OUT / 'PATCH_SPEC.json.gz').read_bytes()))
    assert len(after['signatures']) == 1320
    for name in ('signatures', 'blobs', 'engine_additions', 'budget_policy'):
        assert after[name] == before[name]
    assert set(after['unrecorded_schema_preimages']) == {SCHEMA, ENGINE_SCHEMA}


@pytest.mark.parametrize('tamper_backup', [False, True])
def test_interrupted_apply_restores_physical_schema_or_preserves_tampered_backup(setup, monkeypatch, tamper_backup):
    root, patch = setup
    original_schema = add_schema(root, patch)
    original = snapshot(root)
    atomic = installer.atomic
    seen_schema = False
    def interrupt_after_schema(path, raw, mode=None):
        nonlocal seen_schema
        if path == root / SCHEMA:
            seen_schema = True
        elif seen_schema and path.is_relative_to(root) and 'TRANSFER' not in path.relative_to(root).parts:
            raise OSError('synthetic interrupted installation after schema write')
        atomic(path, raw, mode)
    monkeypatch.setattr(installer, 'atomic', interrupt_after_schema)
    with pytest.raises(OSError, match='synthetic interrupted'):
        installer.apply(root, patch, root / 'TRANSFER/length-recovery-r2')
    monkeypatch.setattr(installer, 'atomic', atomic)
    backups = list((root / 'TRANSFER/length-recovery-r2').glob('backup-*'))
    assert len(backups) == 1
    backup = backups[0]
    assert json.loads((backup / 'receipt.json').read_bytes())['state'] == 'PREPARED'
    assert (backup / SCHEMA).read_bytes() == original_schema
    if tamper_backup:
        (backup / SCHEMA).write_bytes(original_schema + b'\n')
        interrupted = snapshot(root)
        with pytest.raises(ValueError, match='Backup hash mismatch'):
            installer.undo(root, backup)
        assert snapshot(root) == interrupted
        (backup / SCHEMA).write_bytes(original_schema)
    installer.undo(root, backup)
    assert snapshot(root) == original
