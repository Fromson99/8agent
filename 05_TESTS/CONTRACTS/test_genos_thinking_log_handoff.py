"""Execute the delivered standalone TXT against the exact two baseline modules."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / '08_DEPLOYMENT/GENOS/patches/thinking_log_20260928_r1'
TXT = ROOT / '08_DEPLOYMENT/GENOS/patches/GENOS_THINKING_LOG_20260928_R1_APPLY.txt'


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize('version', [1, 2, 3])
def test_final_package_inventory_and_python_311_syntax(version):
    PATCH = ROOT / f'08_DEPLOYMENT/GENOS/patches/thinking_log_20260928_r{version}'
    TXT = ROOT / f'08_DEPLOYMENT/GENOS/patches/GENOS_THINKING_LOG_20260928_R{version}_APPLY.txt'
    subprocess.run(['bash', '-n', str(TXT)], check=True)
    with zipfile.ZipFile(PATCH / 'PACKAGE.zip') as z:
        manifest = json.loads(z.read('CODE_MANIFEST.json'))
        assert set(z.namelist()) == {row['path'] for row in manifest['files']} | {'CODE_MANIFEST.json'}
        for row in manifest['files']:
            raw = z.read(row['path'])
            assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
            assert Path(row['path']).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'}
            if row['path'].endswith('.py'):
                ast.parse(raw, feature_version=(3, 11))


@pytest.mark.parametrize('version, baseline', [(1, 'current'), (2, 'current'),
    (2, 'r1'), (2, 'before_r1'), (2, 'relation')])
def test_delivered_txt_apply_reapply_committed_gate_and_rollback(tmp_path, version, baseline):
    PATCH = ROOT / f'08_DEPLOYMENT/GENOS/patches/thinking_log_20260928_r{version}'
    TXT = ROOT / f'08_DEPLOYMENT/GENOS/patches/GENOS_THINKING_LOG_20260928_R{version}_APPLY.txt'
    root = tmp_path / 'DEV'; root.mkdir()
    plan = json.loads((PATCH / 'PATCH_MANIFEST.json').read_bytes())
    files = {}; expected_after = {}
    for name, row in plan['files'].items():
        target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
        raw = (PATCH / 'baseline' / name).read_bytes()
        if baseline != 'current':
            patches = ROOT / '08_DEPLOYMENT/GENOS/patches'
            if name.endswith('request_report.py'):
                folder = 'relation_wait_20260928_r1' if baseline == 'relation' else 'latency_20260928_r2'
                raw = (patches / folder / 'payload' / name).read_bytes()
            else:
                folder = 'baseline' if baseline == 'before_r1' else 'payload'
                raw = (patches / 'thinking_log_20260928_r1' / folder / name).read_bytes()
        target.write_bytes(raw)
        chosen = next(v for v in [row, *row.get('variants', [])]
                      if sha(raw) in (v['base_sha256'], v['new_sha256']))
        expected_after[name] = chosen['new_sha256']
        files[name] = sha(raw)
    schema = root / '00_SYSTEM/schema.json'; schema.parent.mkdir(); schema.write_text('{}\n')
    manifest = root / '02_BACKEND/ENGINES/fixture.json'; manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'files': files}, indent=2) + '\n')
    pipeline = root / '00_SYSTEM/PIPELINE.json'
    pipeline.write_text(json.dumps({'engines': {'fixture': {
        'manifest': str(manifest.relative_to(root)), 'sha256': sha(manifest.read_bytes())}},
        'contracts': {'fixture': {'schema_path': str(schema.relative_to(root)),
                                 'schema_sha256': sha(schema.read_bytes())}}}) + '\n')
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True)
    def commit(message):
        git('add', '00_SYSTEM', '02_BACKEND')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', message)
    git('init', '-q'); commit('exact prior logging bytes')
    env = {**os.environ, 'DEPLOY_ROOT': str(root), 'PYTHON_BIN': sys.executable,
           'MODE': 'apply', 'TMPDIR': str(tmp_path)}
    def execute():
        return subprocess.run(['bash', str(TXT)], env=env, capture_output=True, text=True)
    first = execute()
    assert first.returncode == 0, first.stdout + first.stderr
    assert 'PACKAGE_HASHES PASS' in first.stdout and 'BACKUP_READY' in first.stdout
    for name, row in plan['files'].items():
        assert sha((root / name).read_bytes()) == expected_after[name]
    second = execute()
    assert second.returncode == 0 and 'ALREADY_APPLIED' in second.stdout
    backups = list((root / f'TRANSFER/thinking-log-20260928-r{version}').glob('backup-*'))
    assert len(backups) == 1
    commit('verified diagnostic code and engine pins')
    gate = subprocess.run([sys.executable, str(PATCH / 'gate.py'), '--code-only',
        '--code-zip', str(root / f'TRANSFER/thinking-log-20260928-r{version}/applied-code.zip'),
        '--deploy-root', str(root)], check=True, capture_output=True, text=True)
    assert 'CODE_CHECK PASS' in gate.stdout
    env.update(MODE='rollback', ROLLBACK_FROM=str(backups[0]))
    rolled = execute()
    assert rolled.returncode == 0 and 'ROLLED_BACK' in rolled.stdout
    assert all((root / name).read_bytes() == raw for name, raw in before.items())
    logs = list(tmp_path.glob(f'genos-thinking-log-r{version}-*.log'))
    assert len(logs) == 3 and all('FINISHED status=0' in p.read_text() for p in logs)
