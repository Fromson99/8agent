"""Check the exact repaired checkout against unchanged compact synthetic data."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

import pytest
from conftest import term_glossary  # noqa: F401
from test_compact_v2_rag import structured_generation  # noqa: F401

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_DB_LOG_ROLLBACK_20261007_R3'


@pytest.mark.parametrize('basis,predecessor', [
    ('query_latency_20261007_r3', 'original'),
    ('query_latency_20261007_r3', 'rollback-r2'),
    ('query_latency_20261007_r4', 'original'),
    ('query_latency_20261007_r4', 'rollback-r2'),
    ('system_logging_20261007_r1', 'rollback-r2'),
])
def test_exact_txt_gate_same_checkout_and_unchanged_generation(
        tmp_path, structured_generation, basis, predecessor):
    folder = OUT.parent/basis
    record = json.loads((folder/'HANDOFF.json').read_bytes())
    root = tmp_path/'DEV'
    root.mkdir()
    with zipfile.ZipFile(folder/(record['version']+'.zip')) as archive:
        archive.extractall(root)
    generation = structured_generation
    before = {p.relative_to(generation).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in generation.rglob('*') if p.is_file()}
    linked = tmp_path/'linked-DEV'
    linked.symlink_to(root, target_is_directory=True)
    env = {**os.environ, 'GENOS_DEV_ROOT': str(linked), 'GENOS_GENERATION': str(generation),
        'GENOS_PYTHON_DIR': str(ROOT/'.venv/bin'), 'GENOS_QUERY_LATENCY': '1',
        'GENOS_SYSTEM_LOG_DIR': str(tmp_path/'system-logs'), 'GENOS_LOG_SPOOL_DIR': str(tmp_path/'spool'),
        'LAWRAG_WORKSPACE_ROOT': str(root), 'LAWRAG_TOOL_WORKSPACE_ROOT': str(root),
        'PYTHONPATH': str(root/'02_BACKEND')}
    if predecessor == 'rollback-r2':
        prior = OUT.with_name('db_log_rollback_20261007_r2')
        r = subprocess.run(['bash', str(prior/'GENOS_DB_LOG_ROLLBACK_20261007_R2_RUN.txt'), 'apply'],
            cwd=root, env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stdout+r.stderr
    apply = subprocess.run(['bash', str(OUT/(NAME+'_RUN.txt')), 'apply'],
        cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert apply.returncode == 0, apply.stdout+apply.stderr
    assert 'ENGINE_BINDINGS PASS; engines=30' in apply.stdout
    backup = next((root/'TRANSFER/db-log-rollback-r3').glob('backup-*'))
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    names = ['CODE_MANIFEST.json', *[r['path'] for r in json.loads(
        (root/'CODE_MANIFEST.json').read_bytes())['files']]]
    subprocess.run(['git', '-C', str(root), 'add', '-f', '--', *names], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Synthetic validation',
        '-c', 'user.email=validation@example.invalid', 'commit', '-qm', 'R3 gate fixture'], check=True)
    result = subprocess.run(['bash', str(OUT/(NAME+'_RUN.txt')), 'gate', str(backup),
        '--generation', str(generation)], cwd=root, env=env, capture_output=True, text=True, timeout=60)
    (tmp_path/'gate.log').write_text(result.stdout+result.stderr)
    assert result.returncode == 0, result.stdout+result.stderr
    assert 'GENOS_RELEASE_GATE PASS' in result.stdout
    receipt = json.loads((backup/'gate-receipt.json').read_bytes())
    assert receipt['state'] == 'PASS' and receipt['identity']['generation'] == str(generation)
    assert receipt['identity']['code_serving_revision'] is None
    after = {p.relative_to(generation).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in generation.rglob('*') if p.is_file()}
    assert after == before
