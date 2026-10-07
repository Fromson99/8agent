"""Minimal R2 archive and complete Bash TXT on an isolated Git checkout."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / '08_DEPLOYMENT/GENOS/patches/chat_flow_20260928_r2'
PREFIX = ROOT / '08_DEPLOYMENT/GENOS/patches/GENOS_CHAT_FLOW_20260928_R2'


def sha(raw): return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / 'DEV'; root.mkdir()
    plan = json.loads((PATCH / 'PATCH_MANIFEST.json').read_bytes())
    files = {}
    for name, row in plan['files'].items():
        dest = root / name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PATCH / 'preimage' / name, dest)
        assert sha(dest.read_bytes()) == row['base_sha256']
        files[name] = row['base_sha256']
    schema = root / '00_SYSTEM/schema.json'; schema.parent.mkdir(exist_ok=True); schema.write_text('{}\n')
    other = root / 'unrelated.py'; other.write_text('X = 1\n'); files['unrelated.py'] = sha(other.read_bytes())
    manifest = root / '02_BACKEND/ENGINES/fixture.json'; manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({'files': files}) + '\n')
    pipeline = {'engines': {'fixture': {'manifest': manifest.relative_to(root).as_posix(), 'sha256': sha(manifest.read_bytes())}},
                'contracts': {'fixture': {'schema_path': '00_SYSTEM/schema.json', 'schema_sha256': sha(schema.read_bytes())}},
                'profiles': {'fixture': {'generation': '01_DATA/synthetic-generation'}}}
    (root / '00_SYSTEM/PIPELINE.json').write_text(json.dumps(pipeline) + '\n')
    data = root / '01_DATA/synthetic-generation/CURRENT'; data.parent.mkdir(parents=True); data.write_text('synthetic-only\n')
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    commit(root)
    return root


def commit(root):
    subprocess.run(['git', '-C', str(root), 'add', '--', '00_SYSTEM', '01_DATA', '02_BACKEND', '08_DEPLOYMENT', 'unrelated.py'], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    'commit', '-qm', 'fixture'], check=True)


def snapshot(root):
    return {str(p.relative_to(root)): sha(p.read_bytes()) for p in root.rglob('*')
            if p.is_file() and '.git' not in p.parts and 'TRANSFER' not in p.parts}


def run(root, mode='apply', backup=None):
    env = dict(os.environ, DEPLOY_ROOT=str(root), PYTHON_BIN=str(ROOT / '.venv/bin/python'), MODE=mode)
    if backup: env['ROLLBACK_FROM'] = str(backup)
    return subprocess.run(['bash', str(PREFIX) + '_APPLY.txt'], env=env, capture_output=True, text=True)


def test_archive_has_only_required_payloads_and_verified_inventory():
    plan = json.loads((PATCH / 'PATCH_MANIFEST.json').read_bytes())
    with zipfile.ZipFile(str(PREFIX) + '.zip') as z:
        expected = {'apply.py', 'PATCH_MANIFEST.json', 'CODE_MANIFEST.json'} | {'payload/' + n for n in plan['files']}
        assert set(z.namelist()) == expected and len(z.namelist()) == 7
        for row in json.loads(z.read('CODE_MANIFEST.json'))['files']:
            raw = z.read(row['path']); assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
        for name, row in plan['files'].items():
            assert z.read('payload/' + name) == (ROOT / name).read_bytes()
            assert sha(z.read('payload/' + name)) == row['new_sha256']
    paste = Path(str(PREFIX) + '_WORKFLOW_PASTE_ALL.txt')
    assert paste.read_bytes() == (ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_bytes()


def test_complete_txt_check_apply_reapply_gate_and_rollback_preserve_data(checkout):
    root = checkout; before = snapshot(root)
    check = run(root, 'check'); assert check.returncode == 0, check.stdout + check.stderr
    assert snapshot(root) == before
    applied = run(root); assert applied.returncode == 0, applied.stdout + applied.stderr
    assert 'BACKUP_READY' in applied.stdout and '"status": "APPLIED"' in applied.stdout
    after = snapshot(root); assert after != before
    assert after['01_DATA/synthetic-generation/CURRENT'] == before['01_DATA/synthetic-generation/CURRENT']
    again = run(root); assert again.returncode == 0 and 'ALREADY_APPLIED' in again.stdout
    assert snapshot(root) == after
    commit(root)
    loader = importlib.util.spec_from_file_location('flow_gate', ROOT / '06_TOOLS/COMMANDS/genos_release_gate.py')
    module = importlib.util.module_from_spec(loader); loader.loader.exec_module(module)
    gate_zip = root / 'TRANSFER/chat-flow-20260928-r2/applied-code.zip'
    verified = module.compare_zip_to_checkout(gate_zip, root)
    assert verified['commit'] == subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    backups = list((root / 'TRANSFER/chat-flow-20260928-r2').glob('backup-*'))
    assert len(backups) == 1
    rollback = run(root, 'rollback', backups[0]); assert rollback.returncode == 0, rollback.stdout + rollback.stderr
    assert snapshot(root) == before


def test_unknown_installed_version_fails_without_overwriting_any_code(checkout):
    root = checkout
    source = root / '02_BACKEND/semantic_runtime/progress.py'
    source.write_bytes(source.read_bytes() + b'\n# unknown field change\n')
    before = snapshot(root); result = run(root)
    assert result.returncode != 0 and 'unsupported installed version' in result.stdout
    assert 'FINISHED status=1' in result.stdout and snapshot(root) == before
