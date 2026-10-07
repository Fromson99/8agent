"""Synthetic existing-cache repair, installer and release-gate contracts."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import subprocess
import zipfile

import pytest
from conftest import term_glossary
from test_compact_v2_rag import structured_generation

SOURCE = Path(os.environ['GENOS_PROGRESSIVE_SOURCE_ROOT'])
OUT = SOURCE / '08_DEPLOYMENT/GENOS/handoffs/progressive_reading_20261006_r1'
NAME = 'GENOS_PROGRESSIVE_READING_20261006_R1'
SCRIPT = OUT / (NAME + '_APPLY.txt')
ARCHIVE = OUT / (NAME + '.zip')
COMPILER = '02_BACKEND/semantic_runtime/full_glossary.py'
COMPACT = 'e03dab542ab0e1c9d129336308ddcdd0ab7a0ee1246fc29614f4efa12a8b4406'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def contents(directory, name):
    with zipfile.ZipFile(SOURCE/'08_DEPLOYMENT/GENOS/handoffs'/directory/name) as z:
        manifest = json.loads(z.read('CODE_MANIFEST.json'))
        result = {r['path']: z.read(r['path']) for r in manifest['files']}
        assert all(sha(result[r['path']]) == r['sha256'] for r in manifest['files'])
        return result


base = contents('request_input_20261006_r2', 'GENOS_V6_REQUEST_INPUT_20261006_R2.zip')
nfs = contents('nfs_state_sqlite_20261006_r1', 'GENOS_NFS_STATE_SQLITE_20261006_R1.zip')
timer = contents('source_recall_timeout_20261006_r1', 'GENOS_SOURCE_RECALL_TIMEOUT_20261006_R1.zip')
route = contents('source_recall_timeout_20261006_r2', 'GENOS_SOURCE_RECALL_TIMEOUT_20261006_R2.zip')
ad1 = contents('ad_language_20261006_r1', 'GENOS_AD_LANGUAGE_20261006_R1.zip')
ad2 = contents('ad_language_20261006_r2', 'GENOS_AD_LANGUAGE_20261006_R2.zip')
rel1 = contents('relation_reading_20261006_r1', 'GENOS_RELATION_READING_20261006_R1.zip')
rel2 = contents('relation_reading_20261006_r2', 'GENOS_RELATION_READING_20261006_R2.zip')
routed = {**base, **nfs, **timer, **route}
PREDECESSORS = {
    'request-input-r2': base,
    'nfs-sqlite-r1': {**base, **nfs},
    'timeout-r1': {**base, **nfs, **timer},
    'routing-r2': routed,
    'ad-r1': {**routed, **ad1},
    'ad-r2': {**routed, **ad1, **ad2},
    'relation-r1': {**routed, **rel1},
    'relation-r1-then-ad-r2': {**routed, **rel1, **ad2},
    'photo-latest-relation-r2': {**routed, **rel1, **ad2, **rel2},
}


PARENT_OUT=SOURCE/'08_DEPLOYMENT/GENOS/handoffs/glossary_binding_repair_20261006_r1'
PARENT_ROOT=SOURCE/'09_ARTIFACTS/DELIVERIES/glossary_binding_repair_20261006_r1'
parent_manifest=json.loads((PARENT_OUT/'CODE_MANIFEST.json').read_text())
PREDECESSORS['compact-repaired-r1']={**PREDECESSORS['photo-latest-relation-r2'],**{r['path']:(PARENT_ROOT/r['path']).read_bytes() for r in parent_manifest['files']+parent_manifest['required_files']}}
r1_manifest=json.loads((SOURCE/'08_DEPLOYMENT/GENOS/handoffs/judgment_view_20261006_r1/CODE_MANIFEST.json').read_text())
r1_root=SOURCE/'09_ARTIFACTS/DELIVERIES/judgment_view_20261006_r1'
PREDECESSORS['judgment-r1']={**PREDECESSORS['compact-repaired-r1'],**{r['path']:(r1_root/r['path']).read_bytes() for r in r1_manifest['files']+r1_manifest['required_files']}}
r2_manifest=json.loads((SOURCE/'08_DEPLOYMENT/GENOS/handoffs/judgment_view_20261006_r2/CODE_MANIFEST.json').read_text())
r2_root=SOURCE/'09_ARTIFACTS/DELIVERIES/judgment_view_20261006_r2'
PREDECESSORS['judgment-r2']={**PREDECESSORS['judgment-r1'],**{r['path']:(r2_root/r['path']).read_bytes() for r in r2_manifest['files']+r2_manifest['required_files']}}
CHANGED=set(json.loads((OUT/'HANDOFF.json').read_text())['runtime_changes'])


def write_checkout(root, prior):
    root.mkdir()
    for name, raw in prior.items():
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)


def environment(root, tmp_path):
    return {**os.environ, 'GENOS_DEV': str(root), 'GENOS_HANDOFF_LOG_DIR': str(tmp_path/'logs'),
            'GENOS_PYTHON_DIR': str(SOURCE/'.venv/bin'), 'PYTHONPATH': str(root/'02_BACKEND'),
            'LAWRAG_WORKSPACE_ROOT': str(root), 'LAWRAG_TOOL_WORKSPACE_ROOT': str(root),
            'GENOS_AUTO_WARMUP': '0', 'AD_WORKER_ENABLED': '0'}


def run(env, mode, argument, success=True):
    done = subprocess.run(['bash', str(SCRIPT), mode, str(argument)], env=env,
                          capture_output=True, text=True, timeout=60)
    assert (done.returncode == 0) == success, done.stdout + done.stderr
    assert 'PROGRESSIVE_READING_EXIT=' in done.stdout
    return done


def data_hashes(root):
    return {str(p.relative_to(root)): sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('predecessor', list(PREDECESSORS))
def test_exact_installer_preserves_existing_cache_and_other_sources(tmp_path, structured_generation, predecessor):
    prior = PREDECESSORS[predecessor]
    root = tmp_path/'DEV'
    write_checkout(root, prior)
    env = environment(root, tmp_path)
    sentinel = root/'90_RUNTIME/user-state.sqlite'
    sentinel.parent.mkdir(); sentinel.write_bytes(b'preserve-user-operational-state')
    before = data_hashes(structured_generation)
    if predecessor == 'photo-latest-relation-r2':
        probe = subprocess.run([str(SOURCE/'.venv/bin/python'), '-c',
            "from lawrag.pipeline.term_serving_bundle import verify_assets; import sys; verify_assets(sys.argv[1])",
            str(structured_generation)], cwd=root, env=env, capture_output=True, text=True)
        assert probe.returncode != 0 and 'glossary compiler/cache binding mismatch' in probe.stderr
    run(env, 'check', structured_generation)
    run(env, 'apply', structured_generation)
    run(env, 'apply', structured_generation)
    assert sha((root/COMPILER).read_bytes()) == COMPACT
    with zipfile.ZipFile(ARCHIVE) as z:
        manifest = json.loads(z.read('CODE_MANIFEST.json'))
        for row in manifest['files']:
            assert (root/row['path']).read_bytes() == z.read(row['path'])
    # Current AD sources and typed relation reading remain exactly as delivered.
    for name, raw in ad2.items():
        if name.startswith('02_BACKEND/semantic_runtime/') and name != COMPILER and name not in CHANGED:
            assert (root/name).read_bytes() == PREDECESSORS['judgment-r2'].get(name,raw)
    for name, raw in rel1.items():
        if name.startswith('02_BACKEND/semantic_runtime/legal_agent/') and name not in CHANGED:
            assert (root/name).read_bytes() == PREDECESSORS['judgment-r2'].get(name,raw)
    pipeline = json.loads((root/'00_SYSTEM/PIPELINE.json').read_text())
    for entry in pipeline['engines'].values():
        raw = (root/entry['manifest']).read_bytes()
        assert sha(raw) == entry['sha256']
        for name, digest in json.loads(raw)['files'].items():
            assert sha((root/name).read_bytes()) == digest, name
    if predecessor == 'compact-repaired-r1':
        run(env, 'verify', structured_generation)
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        paths = sorted(set(prior) | {r['path'] for r in manifest['files']} | {'CODE_MANIFEST.json'})
        subprocess.run(['git', '-C', str(root), 'add', '-f', '--', *paths], check=True)
        subprocess.run(['git', '-C', str(root), '-c', 'user.name=Repair validation', '-c',
                        'user.email=validation@example.invalid', 'commit', '-qm', 'Synthetic repair checkout'], check=True)
        gate = run(env, 'gate', structured_generation)
        assert 'VERIFY_ASSETS PASS' in gate.stdout and 'GENOS_RELEASE_GATE PASS' in gate.stdout
    assert before == data_hashes(structured_generation)
    assert sentinel.read_bytes() == b'preserve-user-operational-state'
    backup = next((root/'09_ARTIFACTS/BACKUPS/code-replacement').iterdir())
    run(env, 'rollback', backup)
    for row in manifest['files']:
        path = root/row['path']
        if row['path'] in prior:
            assert path.read_bytes() == prior[row['path']]
        else:
            assert not path.exists()
    assert before == data_hashes(structured_generation)


@pytest.mark.parametrize('failure', ['unknown-code', 'receipt-tamper', 'different-cache-compiler'])
def test_preflight_failure_preserves_existing_code_and_data(tmp_path, structured_generation, failure):
    root = tmp_path/'DEV'; prior = PREDECESSORS['photo-latest-relation-r2']
    write_checkout(root, prior)
    env = environment(root, tmp_path)
    if failure == 'unknown-code':
        target = root/COMPILER; target.write_bytes(target.read_bytes()+b'\n# unrecognized field modification\n')
    else:
        manifest_path = structured_generation/'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        binding = manifest['glossary']
        receipt_path = structured_generation/binding['cache']/binding['cache_receipt']
        receipt = json.loads(receipt_path.read_text())
        receipt['binding']['compiler_sha256'] = 'f'*64
        receipt_path.write_text(json.dumps(receipt))
        if failure == 'different-cache-compiler':
            binding['cache_receipt_sha256'] = sha(receipt_path.read_bytes())
            manifest_path.write_text(json.dumps(manifest))
    before_code = {name: (root/name).read_bytes() for name in prior}
    before_data = data_hashes(structured_generation)
    run(env, 'apply', structured_generation, success=False)
    assert before_code == {name: (root/name).read_bytes() for name in prior}
    assert before_data == data_hashes(structured_generation)
    assert not (root/'09_ARTIFACTS/BACKUPS/code-replacement').exists()
