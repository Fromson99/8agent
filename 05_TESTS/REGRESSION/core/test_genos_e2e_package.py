"""Installer tests against the previously mailed bundle, never live GENOS."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
PATCH = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-e2e-patch-20260909.zip'
PRIOR = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-unified-dev-root-20260908.zip'
INSTALLER = ROOT / '06_TOOLS/COMMANDS/genos_apply_e2e.sh'


@pytest.mark.parametrize('case', ['success', 'modified', 'corrupt', 'symlink'])
def test_installer_preserves_onsite_changes(tmp_path, case):
    checkout = tmp_path / 'DEV'
    transfer = checkout / 'TRANSFER'
    transfer.mkdir(parents=True)
    shutil.copy2(INSTALLER, transfer / INSTALLER.name)
    shutil.copy2(PATCH, transfer / PATCH.name)
    with zipfile.ZipFile(PATCH) as patch:
        manifest = json.loads(patch.read('patch-manifest.json'))
    with zipfile.ZipFile(PRIOR) as prior:
        names = [n for n, r in manifest['files'].items() if r['previous_sha256']]
        for name in names + ['00_SYSTEM/WORKSPACE.json', '02_BACKEND/semantic_runtime/genos.py']:
            p = checkout/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(prior.read(name))
    transport = checkout/'02_BACKEND/semantic_runtime/genos.py'
    transport.write_text(transport.read_text() + '\n# onsite URL/connection repair retained\n')
    transport_sha = hashlib.sha256(transport.read_bytes()).hexdigest()
    (checkout/'.env').write_text('KEY=do-not-touch\n')
    victim = checkout/'06_TOOLS/COMMANDS/genos_unified_pipeline.py'
    if case == 'modified':
        victim.write_text(victim.read_text() + '\n# user change\n')
    if case == 'corrupt':
        (transfer/PATCH.name).write_bytes(b'corrupt')
    if case == 'symlink':
        saved = tmp_path/'outside.py'
        shutil.move(victim, saved)
        victim.symlink_to(saved)
    env = {**os.environ, 'GENOS_E2E_ROOT': str(checkout)}
    before = {str(p.relative_to(checkout)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in checkout.rglob('*') if p.is_file() and transfer not in p.parents}
    result = subprocess.run(['bash', str(transfer/INSTALLER.name), '--install-only'],
                            env=env, cwd=transfer, capture_output=True, text=True)
    assert hashlib.sha256(transport.read_bytes()).hexdigest() == transport_sha
    assert (checkout/'.env').read_text() == 'KEY=do-not-touch\n'
    if case == 'success':
        assert result.returncode == 0, result.stdout+result.stderr
        for name, entry in manifest['files'].items():
            assert hashlib.sha256((checkout/name).read_bytes()).hexdigest() == entry['sha256']
        receipts = list((checkout/'runtime/patch-backups').glob('*/receipt.json'))
        assert len(receipts) == 1
        again = subprocess.run(['bash', str(transfer/INSTALLER.name), '--install-only'],
                               env=env, cwd=transfer, capture_output=True, text=True)
        assert again.returncode == 0
        assert len(list((checkout/'runtime/patch-backups').glob('*/receipt.json'))) == 1
    else:
        assert result.returncode != 0
        for name, digest in before.items():
            assert hashlib.sha256((checkout/name).read_bytes()).hexdigest() == digest
        assert not (checkout/'runtime/patch-backups').exists()


def test_old_exporter_accepts_fresh_source_coordinates(tmp_path):
    import ast
    from lawrag.pipeline.genos_e2e import stage_document
    raw = tmp_path/'law.xml'
    raw.write_text('<법령/>')
    run = tmp_path/'run'
    run.mkdir()
    stage_document({'path': str(raw), 'name': '법령', 'via': 'law', 'source': 'law',
                    'folder': '법령', 'item': {}}, run)
    with zipfile.ZipFile(PRIOR) as prior:
        tree = ast.parse(prior.read('02_BACKEND/lawrag/pipeline/genos_unified.py'))
    method = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_source_hashes')
    namespace = {'Path': Path, 'json': json}
    exec(compile(ast.Module(body=[method], type_ignores=[]), 'old-source-coordinates', 'exec'), namespace)
    expected = hashlib.sha256(raw.read_bytes()).hexdigest()
    assert namespace['_source_hashes'](run) == {expected[:16]: expected}
