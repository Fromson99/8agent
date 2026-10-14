"""Verify patched prior GENOS code against one unchanged synthetic generation."""
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
NAME = 'GENOS_DB_LOG_ROLLBACK_20261007_R2'


@pytest.mark.parametrize('basis', ['query_latency_20261007_r3','query_latency_20261007_r4'])
@pytest.mark.parametrize('linked', [False, True])
def test_exact_txt_and_same_checkout_generation_gate(tmp_path, structured_generation, basis, linked):
    folder=OUT.parent/basis
    record=json.loads((folder/'HANDOFF.json').read_bytes())
    root=tmp_path/'DEV';root.mkdir()
    with zipfile.ZipFile(folder/(record['version']+'.zip')) as archive:
        archive.extractall(root)
    generation=structured_generation
    before={p.relative_to(generation).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in generation.rglob('*') if p.is_file()}
    requested=root
    if linked:
        requested=tmp_path/'linked-DEV';requested.symlink_to(root,target_is_directory=True)
    env={**os.environ,'GENOS_DEV_ROOT':str(requested),'GENOS_GENERATION':str(generation),
        'GENOS_PYTHON_DIR':str(ROOT/'.venv/bin'),'GENOS_QUERY_LATENCY':'1',
        'GENOS_SYSTEM_LOG_DIR':str(tmp_path/'system-logs'),
        'GENOS_LOG_SPOOL_DIR':str(tmp_path/'spool'),
        'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
        'PYTHONPATH':str(root/'02_BACKEND')}
    apply=subprocess.run(['bash',str(OUT/(NAME+'_RUN.txt')),'apply'],
        cwd=root,env=env,capture_output=True,text=True,timeout=60)
    assert apply.returncode==0,apply.stdout+apply.stderr
    backup=next((root/'TRANSFER/db-log-rollback-r2').glob('backup-*'))
    subprocess.run(['git','init','-q',str(root)],check=True)
    names=['CODE_MANIFEST.json',*[r['path'] for r in json.loads(
        (root/'CODE_MANIFEST.json').read_bytes())['files']]]
    subprocess.run(['git','-C',str(root),'add','-f','--',*names],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Synthetic validation',
        '-c','user.email=validation@example.invalid','commit','-qm','DB log rollback fixture'],check=True)
    result=subprocess.run(['bash',str(OUT/(NAME+'_RUN.txt')),'gate',str(backup),
        '--generation',str(generation)],cwd=root,env=env,capture_output=True,text=True,timeout=60)
    (tmp_path/'gate.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'GENOS_RELEASE_GATE PASS' in result.stdout
    receipt=json.loads((backup/'gate-receipt.json').read_bytes())
    assert receipt['state']=='PASS' and receipt['identity']['generation']==str(generation)
    assert receipt['identity']['code_serving_revision'] is None
    after={p.relative_to(generation).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in generation.rglob('*') if p.is_file()}
    assert after==before
