"""Offline installer contracts; no GENOS access, source data or model calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / '08_DEPLOYMENT/GENOS/patches/latency_20260928_r1'


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(params=['latency_20260928_r1','latency_20260928_r2','request_unlimited_20260928_r1',
                        'relation_wait_20260928_r1', 'thinking_log_20260928_r1',
                        'thinking_log_20260928_r2', 'evidence_read_20260928_r1',
                        'response_overhead_20260928_r1', 'proposal_retry_20260928_r1'])
def install(tmp_path, monkeypatch, request):
    PATCH = ROOT / '08_DEPLOYMENT/GENOS/patches' / request.param
    spec = importlib.util.spec_from_file_location('latency_apply_fixture', PATCH / 'apply.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    patch = tmp_path / 'patch'; shutil.copytree(PATCH, patch)
    monkeypatch.setattr(module, 'PATCH', patch)
    plan = json.loads((patch / 'PATCH_MANIFEST.json').read_bytes())
    root = tmp_path / 'DEV'; root.mkdir()
    for name in plan['files']:
        dest = root / name; dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text('"""Synthetic pre-patch module for installer contracts."""\n')
        plan['files'][name]['base_sha256'] = digest(dest.read_bytes())
    (patch / 'PATCH_MANIFEST.json').write_text(json.dumps(plan))
    unrelated = root / 'other.py'; unrelated.write_text('x = 1\n')
    files = {n: digest((root / n).read_bytes()) for n in plan['files']}
    files['other.py'] = digest(unrelated.read_bytes())
    manifest_name = '02_BACKEND/ENGINES/fixture.json'
    manifest = root / manifest_name; manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'files': files}) + '\n')
    schema = root / '00_SYSTEM/schema.json'; schema.parent.mkdir()
    schema.write_text('{}\n')
    (root / '00_SYSTEM/PIPELINE.json').write_text(json.dumps({
        'engines': {'fixture': {'manifest': manifest_name, 'sha256': digest(manifest.read_bytes())}},
        'contracts': {'fixture': {'schema_path': '00_SYSTEM/schema.json', 'schema_sha256': digest(schema.read_bytes())}}
    }) + '\n')
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture'], check=True)
    monkeypatch.setattr('sys.argv', ['apply.py', '--deploy-root', str(root)])
    return module, root, plan, patch


def snapshot(root):
    return {str(p.relative_to(root)): digest(p.read_bytes()) for p in root.rglob('*')
            if p.is_file() and '.git' not in p.parts and 'TRANSFER' not in p.parts}


def test_apply_reapply_rollback_and_gate_manifest(install, monkeypatch):
    import zipfile
    module, root, plan, _ = install
    before = snapshot(root)
    module.main(); applied = snapshot(root)
    assert before != applied
    for name, row in plan['files'].items():
        assert digest((root / name).read_bytes()) == row['new_sha256']
    module.main()
    assert snapshot(root) == applied
    backups = list((root / ('TRANSFER/'+module.PATCH_ID)).glob('backup-*'))
    assert len(backups) == 1
    with zipfile.ZipFile(root / ('TRANSFER/'+module.PATCH_ID+'/applied-code.zip')) as z:
        rows = json.loads(z.read('CODE_MANIFEST.json'))['files']
        assert set(z.namelist()) == {r['path'] for r in rows} | {'CODE_MANIFEST.json'}
        for row in rows:
            assert digest(z.read(row['path'])) == digest((root / row['path']).read_bytes()) == row['sha256']
    monkeypatch.setattr('sys.argv', ['apply.py', '--deploy-root', str(root), '--rollback-from', str(backups[0])])
    module.main(); assert snapshot(root) == before
    module.main(); assert snapshot(root) == before


@pytest.mark.parametrize('kind', ['target', 'payload', 'unrelated', 'schema', 'manifest'])
def test_mismatch_refuses_before_any_code_write(install, kind):
    module, root, plan, patch = install
    name = next(iter(plan['files']))
    targets = {'target': root / name, 'payload': patch / 'payload' / name,
               'unrelated': root / 'other.py', 'schema': root / '00_SYSTEM/schema.json',
               'manifest': root / '02_BACKEND/ENGINES/fixture.json'}
    with targets[kind].open('ab') as stream:
        stream.write(b'\n# mismatch\n')
    before = snapshot(root)
    with pytest.raises(ValueError):
        module.main()
    assert snapshot(root) == before


def test_interrupted_write_restores_code_and_pins(install, monkeypatch):
    module, root, plan, _ = install
    before = snapshot(root); original = module.atomic; calls = 0
    interrupted_file = root / next(iter(plan['files']))
    def fail_once(path, data):
        nonlocal calls
        if path == interrupted_file:
            calls += 1
            if calls == 1:
                raise OSError('simulated interrupted write')
        return original(path, data)
    monkeypatch.setattr(module, 'atomic', fail_once)
    with pytest.raises(OSError, match='simulated'):
        module.main()
    assert snapshot(root) == before


def test_rollback_preserves_later_user_edits(install):
    module, root, plan, _ = install
    module.main()
    with (root / next(iter(plan['files']))).open('ab') as stream:
        stream.write(b'\n# later user edit\n')
    before = snapshot(root)
    backup = next((root / ('TRANSFER/'+module.PATCH_ID)).glob('backup-*'))
    with pytest.raises(ValueError, match='rollback refused'):
        module.rollback(root, backup)
    assert snapshot(root) == before
