"""Minimal deployment patch must preserve data pins and unrelated code."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import os

import pytest
from conftest import term_glossary
from test_legal_agent_double_harness import generation

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('decision_patch_installer', ROOT/'06_TOOLS/OFFLINE/genos_model_decision_repair.py')
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)
BASE = ROOT/'08_DEPLOYMENT/RELEASES/legal-agent-structure-catalogue-pecab-20260929-r1/code'
AFTER = ROOT/'08_DEPLOYMENT/RELEASES/legal-agent-structure-catalogue-pecab-repair-20260929-r1/code'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path/'DEV'
    root.mkdir()
    rows = []
    for name in INSTALLER.FILES:
        p = root/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((BASE/name).read_bytes())
        payload = (AFTER/name).read_bytes()
        rows.append({'path': name, 'sha256': sha(payload), 'bytes': len(payload),
                     'before_sha256': sha(p.read_bytes())})
    (root/'untouched.py').write_text('value = 1\n')
    (root/'schema.json').write_text('{}\n')
    manifest_path = '02_BACKEND/ENGINES/mock/retrieve.json'
    manifest = {'files': {name: sha((root/name).read_bytes()) for name in (*INSTALLER.FILES, 'untouched.py')}}
    p = root/manifest_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(INSTALLER.dump(manifest))
    pipeline = {'engines': {'mock': {'manifest': manifest_path, 'sha256': sha(p.read_bytes())}},
                'contracts': {'port': {'schema_path': 'schema.json', 'schema_sha256': sha((root/'schema.json').read_bytes())}},
                'profiles': {'GENOS_DATA': {'path': '/actual/internal/generation', 'hash': 'FIELD_DATA_PIN'}}}
    p = root/'00_SYSTEM/PIPELINE.json'
    p.parent.mkdir(parents=True)
    p.write_bytes(INSTALLER.dump(pipeline))
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    git(root, 'config', 'user.name', 'Patch fixture')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'fixture baseline')
    archive = tmp_path/'code.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in INSTALLER.FILES:
            z.writestr(name, (AFTER/name).read_bytes())
        z.writestr('CODE_MANIFEST.json', INSTALLER.dump({'format': '8agent-code/1',
                    'patch': INSTALLER.PATCH_ID, 'files': rows}))
    return root, archive, pipeline


def run(root, archive, *args, ok=True):
    result = subprocess.run([sys.executable, str(ROOT/'06_TOOLS/OFFLINE/genos_model_decision_repair.py'),
        '--deploy-root', str(root), '--archive', str(archive), *args], capture_output=True, text=True)
    assert (result.returncode == 0) is ok, result.stdout+result.stderr
    return result


def test_apply_rerun_gate_and_rollback_preserve_field_data(checkout):
    root, archive, before = checkout
    first = run(root, archive)
    receipt = json.loads(first.stdout.splitlines()[-1])
    assert receipt['status'] == 'APPLIED' and len(receipt['changed_files']) == 5
    backup = receipt['backup']
    after = json.loads((root/'00_SYSTEM/PIPELINE.json').read_text())
    assert after['profiles'] == before['profiles']
    for name in INSTALLER.FILES:
        assert (root/name).read_bytes() == (AFTER/name).read_bytes()
    second = json.loads(run(root, archive).stdout.splitlines()[-1])
    assert second['status'] == 'ALREADY_APPLIED' and not second['changed_files']
    git(root, 'add', '-u')
    git(root, 'commit', '-qm', 'apply fixture patch')
    spec = importlib.util.spec_from_file_location('decision_patch_gate', ROOT/'06_TOOLS/COMMANDS/genos_release_gate.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    assert gate.compare_zip_to_checkout(Path(second['gate_zip']), root)['code_files'] == 5
    run(root, archive, '--rollback-from', backup)
    for name in INSTALLER.FILES:
        assert (root/name).read_bytes() == (BASE/name).read_bytes()
    assert json.loads((root/'00_SYSTEM/PIPELINE.json').read_text()) == before


@pytest.mark.parametrize('target', [INSTALLER.FILES[0], 'untouched.py', 'schema.json', '02_BACKEND/ENGINES/mock/retrieve.json'])
def test_unknown_code_and_pin_drift_fail_before_any_patch_write(checkout, target):
    root, archive, _ = checkout
    (root/target).write_bytes((root/target).read_bytes()+b'\n# unexpected drift\n')
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file() and '.git' not in p.parts}
    run(root, archive, ok=False)
    assert all((root/name).read_bytes() == raw for name, raw in before.items())
    assert not list((root/'TRANSFER'/INSTALLER.PATCH_ID).glob('backup-*'))


def test_corrupt_archive_is_rejected(checkout):
    root, archive, _ = checkout
    with zipfile.ZipFile(archive, 'a') as z:
        z.writestr('unexpected.py', 'print("never install")')
    run(root, archive, ok=False)
    assert not (root/'unexpected.py').exists()


def test_rollback_preserves_post_install_user_edits(checkout):
    root, archive, _ = checkout
    receipt = json.loads(run(root, archive).stdout.splitlines()[-1])
    edited = root/INSTALLER.FILES[0]
    edited.write_bytes(edited.read_bytes()+b'\n# user edit\n')
    raw = edited.read_bytes()
    run(root, archive, '--rollback-from', receipt['backup'], ok=False)
    assert edited.read_bytes() == raw


def test_final_txt_on_full_integrated_checkout_apply_rerun_commit_gate_and_rollback(tmp_path, generation):
    root = tmp_path/'full-DEV'
    root.mkdir()
    baseline_zip = ROOT/'09_ARTIFACTS/HANDOFFS/20260929-rag-main-integrated/code.zip'
    with zipfile.ZipFile(baseline_zip) as z:
        z.extractall(root)
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    git(root, 'config', 'user.name', 'Full handoff fixture')
    git(root, 'add', '-f', '.')
    git(root, 'commit', '-qm', 'integrated code baseline')
    bundle = ROOT/'09_ARTIFACTS/HANDOFFS/20260929-model-decision-repair-minimal'
    txt = bundle/'GENOS_MODEL_DECISION_REPAIR_20260929_R1_APPLY.txt'
    env = {**os.environ, 'DEPLOY_ROOT': str(root), 'PYTHON_BIN': sys.executable,
           'GENOS_GENERATION': str(generation), 'TMPDIR': str(tmp_path)}
    env.pop('LAWRAG_WORKSPACE_ROOT', None)
    env.pop('LAWRAG_TOOL_WORKSPACE_ROOT', None)
    def execute(mode, **extra):
        r = subprocess.run(['bash', str(txt)], env={**env, 'MODE': mode, **extra},
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout+r.stderr
        return r.stdout
    assert 'BACKUP_READY' in execute('apply')
    state = root/'TRANSFER/model-decision-repair-20260929-r1'
    receipts = [json.loads(p.read_text()) for p in state.glob('apply-*.json')]
    applied = next(r for r in receipts if r['status'] == 'APPLIED')
    assert len(applied['changed_files']) == 30
    assert 'ALREADY_APPLIED' in execute('apply')
    assert 'GENOS_RELEASE_GATE PASS' in execute('commit_gate')
    assert 'GENOS_RELEASE_GATE PASS' in execute('verify')
    assert list(state.glob('gate-*.json'))
    assert 'ROLLED_BACK' in execute('rollback', ROLLBACK_FROM=applied['backup'])
    for name in INSTALLER.FILES:
        assert (root/name).read_bytes() == (BASE/name).read_bytes()
