"""Execute the shipped TXT on a synthetic Git checkout, including rollback."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT/'08_DEPLOYMENT/GENOS/patches/answer_stream_20260929_r1'
PREFIX = ROOT/'08_DEPLOYMENT/GENOS/patches/GENOS_ANSWER_STREAM_20260929_R1'
NEW = '02_BACKEND/semantic_runtime/legal_agent/answer_stream.py'


def sha(raw): return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path/'DEV'; root.mkdir()
    spec = json.loads((PATCH/'PATCH_MANIFEST.json').read_bytes()); files = {}
    for name,row in spec['files'].items():
        if row['base_sha256'] is None: continue
        dest = root/name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PATCH/'preimage'/name, dest)
        assert sha(dest.read_bytes()) == row['base_sha256']
        files[name] = row['base_sha256']
    other = root/'unrelated.py'; other.write_text('X = 1\n'); files['unrelated.py'] = sha(other.read_bytes())
    schema = root/'00_SYSTEM/schema.json'; schema.parent.mkdir(exist_ok=True); schema.write_text('{}\n')
    manifest = root/'02_BACKEND/ENGINES/fixture.json'; manifest.parent.mkdir(parents=True,exist_ok=True)
    manifest.write_text(json.dumps({'files':files})+'\n')
    config = {'engines': {'fixture': {'manifest': manifest.relative_to(root).as_posix(), 'sha256': sha(manifest.read_bytes())}},
              'contracts': {'fixture': {'schema_path':'00_SYSTEM/schema.json','schema_sha256':sha(schema.read_bytes())}}}
    (root/'00_SYSTEM/PIPELINE.json').write_text(json.dumps(config)+'\n')
    data = root/'01_DATA/synthetic/CURRENT'; data.parent.mkdir(parents=True); data.write_text('original-generation\n')
    subprocess.run(['git','init','-q',str(root)],check=True)
    subprocess.run(['git','-C',str(root),'add','.'],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],check=True)
    return root


def snapshot(root):
    return {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in root.rglob('*')
            if p.is_file() and '.git' not in p.parts and 'TRANSFER' not in p.parts}


def run(root,mode='apply',backup=None):
    env = dict(os.environ, DEPLOY_ROOT=str(root), PYTHON_BIN=str(ROOT/'.venv/bin/python'), MODE=mode)
    if backup: env['ROLLBACK_FROM'] = str(backup)
    result = subprocess.run(['bash',str(PREFIX)+'_APPLY.txt'],env=env,text=True,capture_output=True)
    assert result.returncode == 0, result.stdout+result.stderr
    return result


def test_archive_inventory_and_workflow_are_exact():
    with zipfile.ZipFile(str(PREFIX)+'.zip') as z:
        rows = json.loads(z.read('CODE_MANIFEST.json'))['files']
        assert set(z.namelist()) == {r['path'] for r in rows}|{'CODE_MANIFEST.json'}
        for row in rows:
            raw = z.read(row['path']); assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
        for name in json.loads((PATCH/'PATCH_MANIFEST.json').read_bytes())['files']:
            assert z.read('payload/'+name) == (ROOT/name).read_bytes()
    assert Path(str(PREFIX)+'_WORKFLOW.py').read_bytes() == (ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_bytes()


def test_full_txt_apply_reapply_rollback_and_data_preservation(checkout, tmp_path):
    before = snapshot(checkout)
    # ~/DEV may be an entry symlink to the actual Git checkout.
    link = tmp_path/'DEV-link'; link.symlink_to(checkout, target_is_directory=True)
    run(link, 'check'); first = run(link)
    records = [json.loads(line) for line in first.stdout.splitlines() if line.startswith('{')]
    applied = next(row for row in records if row.get('status') == 'APPLIED')
    assert (checkout/NEW).exists()
    config = json.loads((checkout/'00_SYSTEM/PIPELINE.json').read_bytes())
    engine = config['engines']['fixture']; manifest_path = checkout/engine['manifest']
    assert sha(manifest_path.read_bytes()) == engine['sha256']
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest['files'][NEW] == sha((checkout/NEW).read_bytes())
    assert (checkout/'01_DATA/synthetic/CURRENT').read_text() == 'original-generation\n'
    assert 'ALREADY_APPLIED' in run(link).stdout
    run(link,'rollback',applied['backup'])
    assert snapshot(checkout) == before and not (checkout/NEW).exists()


def test_unsupported_existing_code_stops_before_mutation(checkout):
    path = checkout/'08_DEPLOYMENT/GENOS/stream_app.py'; path.write_text(path.read_text()+'\nFIELD_VARIANT = True\n')
    before = snapshot(checkout)
    env = dict(os.environ, DEPLOY_ROOT=str(checkout), PYTHON_BIN=str(ROOT/'.venv/bin/python'))
    result = subprocess.run(['bash',str(PREFIX)+'_APPLY.txt'],env=env,text=True,capture_output=True)
    assert result.returncode != 0 and 'unsupported installed version' in result.stdout
    assert snapshot(checkout) == before
