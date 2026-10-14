"""Verify attached CM TXT on committed GENOS checkouts with compact mock data."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
import pytest
from conftest import term_glossary  # noqa: F401
from test_compact_v2_rag import structured_generation  # noqa: F401

ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
NAME='GENOS_CM_SHORTCUT_DATA_20261007_R2'


@pytest.mark.parametrize('basis',['query_latency_20261007_r3','query_latency_20261007_r4','system_logging_20261007_r1'])
def test_same_checkout_generation_gate(tmp_path,structured_generation,basis):
    folder=OUT.with_name(basis);record=json.loads((folder/'HANDOFF.json').read_bytes())
    root=tmp_path/'DEV';root.mkdir()
    with zipfile.ZipFile(folder/(record['version']+'.zip')) as archive:archive.extractall(root)
    generation=structured_generation
    before={p.relative_to(generation).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in generation.rglob('*') if p.is_file()}
    env={**os.environ,'GENOS_DEV_ROOT':str(root),'GENOS_GENERATION':str(generation),
         'GENOS_PYTHON_DIR':str(ROOT/'.venv/bin'),'PYTHONPATH':str(root/'02_BACKEND'),
         'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
         'GENOS_SYSTEM_LOG_DIR':str(tmp_path/'logs'),'GENOS_LOG_SPOOL_DIR':str(tmp_path/'spool')}
    scripts=[OUT.with_name('db_log_rollback_20261007_r3')/'GENOS_DB_LOG_ROLLBACK_20261007_R3_RUN.txt',
             OUT.with_name('core_evidence_shortcut_20261007_r1')/'GENOS_CORE_EVIDENCE_SHORTCUT_20261007_R1_RUN.txt',
             OUT/(NAME+'_RUN.txt')]
    for script in scripts:
        r=subprocess.run(['bash',str(script),'apply'],cwd=root,env=env,capture_output=True,text=True,timeout=90)
        assert r.returncode==0,r.stdout+r.stderr
    backup=next((root/'TRANSFER/cm-shortcut-data-r2').glob('backup-*'))
    subprocess.run(['git','init','-q',str(root)],check=True)
    manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
    subprocess.run(['git','-C',str(root),'add','-f','--','CODE_MANIFEST.json',
                    *[r['path'] for r in manifest['files']]],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Synthetic validation',
                    '-c','user.email=validation@example.invalid','commit','-qm','curated CM fixture'],check=True)
    r=subprocess.run(['bash',str(OUT/(NAME+'_RUN.txt')),'gate',str(backup),'--generation',str(generation)],
                     cwd=root,env=env,capture_output=True,text=True,timeout=90)
    (tmp_path/'gate.log').write_text(r.stdout+r.stderr)
    assert r.returncode==0,r.stdout+r.stderr
    assert 'GENOS_RELEASE_GATE PASS' in r.stdout
    receipt=json.loads((backup/'gate-receipt.json').read_bytes())
    assert receipt['state']=='PASS' and receipt['identity']['generation']==str(generation)
    assert receipt['identity']['code_serving_revision'] is None
    after={p.relative_to(generation).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in generation.rglob('*') if p.is_file()}
    assert before==after
