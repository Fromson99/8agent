"""Real shell/tar recovery tests, with isolated mock generations and no GENOS."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
TXT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_FULL_PIPELINE_BACKUP_E2E_R5.txt'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def setup(tmp_path, completed=True):
    data = tmp_path / 'data'
    base = tmp_path / 'term-releases/base/generation'
    base.mkdir(parents=True)
    (base / 'manifest.json').write_text('{}')
    controls = ['CATALOG/TEAM_LAYOUT.json', 'RAW/union_file/manifest.json']
    for rel in controls:
        path = data / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}')
    backup = tmp_path / 'BACKUPS/full-e2e/financial-risk-full-e2e-20260930-r2'
    backup.mkdir(parents=True)
    archive = backup / 'previous-generation-and-controls.tar.gz'
    receipt = backup / 'receipt.json'
    if completed:
        with tarfile.open(archive, 'w:gz') as out:
            out.add(base, arcname='generation')
            for rel in controls:
                out.add(data / rel, arcname=rel)
        receipt.write_text(json.dumps({'schema_version': 'genos-full-e2e-backup-v1',
            'base_generation': str(base), 'base_manifest_sha256': sha(base/'manifest.json'),
            'archive': str(archive), 'archive_bytes': archive.stat().st_size,
            'archive_sha256': sha(archive), 'controls': {rel: sha(data/rel) for rel in controls}}))
    partial = tmp_path / 'BACKUPS/full-e2e/financial-risk-full-e2e-20260930-r3/previous-generation-and-controls.tar.gz.partial'
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b'interrupted-original-bytes')
    return data, base, archive, partial


def run_backup(data, base):
    source = TXT.read_text()
    section = source.split('BASE_STORAGE_ROOT=', 1)[1].split("printf 'PIPELINE_START", 1)[0]
    script = 'set -Eeuo pipefail\nstage() { printf "STEP %s\\n" "$1"; }\nBASE_STORAGE_ROOT=' + section
    env = {k: v for k, v in os.environ.items() if not k.startswith('GENOS_')}
    env.update(GENOS_DATA_ROOT=str(data), BASE=str(base), RUN_ID='financial-risk-full-e2e-20260930-r3')
    return subprocess.run(['bash', '-c', script], env=env, text=True, capture_output=True)


def test_exact_r2_backup_reused_and_partial_preserved(tmp_path):
    data, base, archive, partial = setup(tmp_path)
    before = sha(archive)
    result = run_backup(data, base)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'BACKUP_REUSE_SELECTED' in result.stdout and 'BACKUP_REUSED' in result.stdout
    assert 'BACKUP_START output=' not in result.stdout
    assert partial.read_bytes() == b'interrupted-original-bytes'
    assert sha(archive) == before


def test_changed_control_rejects_reuse(tmp_path):
    data, base, archive, partial = setup(tmp_path)
    (data/'CATALOG/TEAM_LAYOUT.json').write_text('{"changed":true}')
    result = run_backup(data, base)
    assert result.returncode != 0
    assert 'saved backup control differs' in result.stderr
    assert partial.exists() and archive.exists()


def test_same_size_corrupted_archive_rejects_reuse(tmp_path):
    data, base, archive, partial = setup(tmp_path)
    raw = bytearray(archive.read_bytes())
    raw[-1] ^= 1
    archive.write_bytes(raw)
    result = run_backup(data, base)
    assert result.returncode != 0
    assert 'Backup binding differs' in result.stderr
    assert partial.exists()


def test_no_completed_backup_preserves_partial_and_creates_verified_backup(tmp_path):
    data, base, archive, partial = setup(tmp_path, completed=False)
    result = run_backup(data, base)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'INTERRUPTED_BACKUP_PRESERVED' in result.stdout
    preserved = list(partial.parent.glob('*.partial.interrupted-*'))
    assert len(preserved) == 1
    assert preserved[0].read_bytes() == b'interrupted-original-bytes'
    receipt = json.loads((partial.parent/'receipt.json').read_text())
    assert receipt['archive_sha256'] == sha(partial.parent/'previous-generation-and-controls.tar.gz')
