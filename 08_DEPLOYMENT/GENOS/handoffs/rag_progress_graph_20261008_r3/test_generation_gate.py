"""Verify the exact attached TXT in committed checkouts with compact mock data."""
import hashlib
import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import zipfile

import pytest
from conftest import term_glossary  # noqa: F401
from test_compact_v2_rag import structured_generation  # noqa: F401

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
NAME='GENOS_RAG_PROGRESS_GRAPH_20261008_R3'


@pytest.mark.parametrize('basis',['query_latency_20261007_r3','query_latency_20261007_r4','system_logging_20261007_r1'])
def test_same_checkout_generation_gate(tmp_path,structured_generation,basis):
    folder=OUT.with_name(basis);record=json.loads((folder/'HANDOFF.json').read_bytes())
    root=tmp_path/'DEV';root.mkdir()
    with zipfile.ZipFile(folder/(record['version']+'.zip')) as z:z.extractall(root)
    generation=structured_generation
    original={p.relative_to(generation).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
              for p in generation.rglob('*') if p.is_file()}
    env={**os.environ,'GENOS_DEV_ROOT':str(root),'GENOS_GENERATION':str(generation),
         'GENOS_PYTHON_DIR':str(ROOT/'.venv/bin'),'PYTHONPATH':str(root/'02_BACKEND'),
         'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
         'GENOS_SYSTEM_LOG_DIR':str(tmp_path/'logs'),'GENOS_LOG_SPOOL_DIR':str(tmp_path/'spool')}
    prior=OUT.with_name('db_log_rollback_20261007_r3')/'GENOS_DB_LOG_ROLLBACK_20261007_R3_RUN.txt'
    for script in (prior,OUT/(NAME+'_RUN.txt')):
        r=subprocess.run(['bash',str(script),'apply'],cwd=root,env=env,capture_output=True,text=True,timeout=90)
        assert r.returncode==0,r.stdout+r.stderr
    backup=next((root/'TRANSFER/rag-progress-graph-r3').glob('backup-*'))
    subprocess.run(['git','init','-q',str(root)],check=True)
    manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
    subprocess.run(['git','-C',str(root),'add','-f','--','CODE_MANIFEST.json',
                    *[r['path'] for r in manifest['files']]],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Synthetic validation',
                    '-c','user.email=validation@example.invalid','commit','-qm','display fixture'],check=True)
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
    assert after==original


@pytest.mark.parametrize('basis',['GENOS_CM_ONECLICK_20261008_R14/','GENOS_CM_ONECLICK_20261008_R15/'])
def test_cm_budget_and_selected_generation_binding_are_preserved(tmp_path,basis):
    spec=json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))
    loader=importlib.util.spec_from_file_location('r3_budget_build',OUT/'build_delivery.py')
    build=importlib.util.module_from_spec(loader);loader.loader.exec_module(build)
    label,payload,_=next(row for row in build.states() if row[0].startswith(basis))
    root=tmp_path/'DEV';root.mkdir();build.write_payload(root,payload)
    policy=spec['budget_policy'];before=payload['service.py'].decode()
    for operation in policy['operations']:
        assert before.count(operation['before'])==1
        before=before.replace(operation['before'],operation['after'],1)
    service=before.encode();(root/'service.py').write_bytes(service)
    manifest=json.loads(payload['CODE_MANIFEST.json'])
    meta={'revision':policy['revision'],'prior_inventory_sha256':hashlib.sha256(payload['CODE_MANIFEST.json']).hexdigest(),
          'modified_paths':['service.py'],'settings':policy['settings'],'default_model_attempts_changed':False,'field_deployed':False}
    manifest['investigation_budget_settings']=meta
    manifest['cm_oneclick']['preserved_investigation_budget']=meta
    for row in manifest['files']:
        if row['path']=='service.py':row.update(sha256=hashlib.sha256(service).hexdigest(),bytes=len(service))
    (root/'CODE_MANIFEST.json').write_bytes(build.encoded(manifest))
    binding=(root/'00_SYSTEM/GENOS_SERVING_PATHS.json').read_bytes()
    env={**os.environ,'GENOS_DEV_ROOT':str(root),'GENOS_PYTHON_DIR':str(ROOT/'.venv/bin'),
         'GENOS_SYSTEM_LOG_DIR':str(tmp_path/'logs'),'GENOS_LOG_SPOOL_DIR':str(tmp_path/'spool'),
         'PYTHONPATH':str(root/'02_BACKEND')}
    for key in ('GENOS_GENERATION','GENOS_DISPLAY_CHILD','GENOS_LOG_RUN_ID'):env.pop(key,None)
    run=OUT/(NAME+'_RUN.txt')
    for mode in ('check','apply','verify'):
        result=subprocess.run(['bash',str(run),mode],cwd=root,env=env,capture_output=True,text=True,timeout=90)
        assert result.returncode==0,result.stdout+result.stderr
    assert (root/'service.py').read_bytes()==service
    assert (root/'00_SYSTEM/GENOS_SERVING_PATHS.json').read_bytes()==binding
    assert json.loads((root/'CODE_MANIFEST.json').read_bytes())['investigation_budget_settings']==meta
    if 'R15/' in basis:
        from contextlib import redirect_stdout
        import io
        library=build.load('r3_frozen_error_check',OUT.with_name('full_error_logging_20261007_r10')/'INSTALL.py')
        error_spec=json.loads((OUT.with_name('full_error_logging_20261007_r10')/'PATCH_SPEC.json').read_bytes())
        after=json.loads((root/'CODE_MANIFEST.json').read_bytes())
        current={row['path']:(root/row['path']).read_bytes() for row in after['files']}
        with redirect_stdout(io.StringIO()):library.local_verification(current,error_spec)
        assert after['full_error_logging']==json.loads(payload['CODE_MANIFEST.json'])['full_error_logging']
        for name in error_spec['files']:
            if name not in build.OWN:assert current[name]==(service if name=='service.py' else payload[name])
    # A later valid-Python edit outside the sealed budget operation must stop
    # before writing, even when its inventory row has been updated to match.
    changed=service+b'\n# unknown field change\n';(root/'service.py').write_bytes(changed)
    manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
    for row in manifest['files']:
        if row['path']=='service.py':row.update(sha256=hashlib.sha256(changed).hexdigest(),bytes=len(changed))
    (root/'CODE_MANIFEST.json').write_bytes(build.encoded(manifest))
    result=subprocess.run(['bash',str(run),'verify'],cwd=root,env=env,capture_output=True,text=True,timeout=90)
    assert result.returncode!=0 and 'output inventory differs' in result.stdout+result.stderr
    assert (root/'service.py').read_bytes()==changed
