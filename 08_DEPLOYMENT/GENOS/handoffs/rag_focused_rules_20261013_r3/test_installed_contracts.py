"""Exercise scoped SEARCH_BODY and cache regressions in the installed code."""
import gzip, json, os, subprocess, zipfile
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent

@pytest.mark.parametrize('basis',['query_latency_20261007_r3','query_latency_20261007_r4'])
def test_installed_structure_and_cache_contracts(tmp_path,basis):
    folder=OUT.with_name(basis);hand=json.loads((folder/'HANDOFF.json').read_bytes())
    root=tmp_path/'DEV';root.mkdir()
    with zipfile.ZipFile(folder/(hand['version']+'.zip')) as z:z.extractall(root)
    env={**os.environ,'GENOS_DEV_ROOT':str(root),'GENOS_PYTHON_DIR':str(ROOT/'.venv/bin'),
         'PYTHONPATH':str(root/'02_BACKEND')+':'+str(ROOT/'05_TESTS/CONTRACTS')+':'+str(ROOT/'05_TESTS/REGRESSION/core'),
         'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'AD_WORKER_ENABLED':'0',
         'GENOS_AUTO_WARMUP':'0'}
    for key in ('GENOS_PATCH_DEV','GENOS_GENERATION','GENOS_DATA_ROOT'):env.pop(key,None)
    steps=[('db_log_rollback_20261007_r3','GENOS_DB_LOG_ROLLBACK_20261007_R3')]
    steps += [(f'rag_focused_rules_20261013_r{i}',f'GENOS_RAG_FOCUSED_RULES_20261013_R{i}') for i in (1,2,3)]
    for folder,name in steps:
        r=subprocess.run(['bash',str(OUT.with_name(folder)/(name+'_RUN.txt')),'apply'],cwd=root,env=env,text=True,capture_output=True,timeout=90)
        assert r.returncode==0,r.stdout+r.stderr
    # Test fixture support only. None of these files alter the installed engine
    # inventory; the independent release-gate tests use pristine inventories.
    for source in (ROOT/'00_SYSTEM').rglob('*.json'):
        dest=root/source.relative_to(ROOT)
        if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read_bytes())
    helper=root/'02_BACKEND/semantic_runtime/factorized_audit.py'
    if not helper.exists():helper.write_bytes((ROOT/'02_BACKEND/semantic_runtime/factorized_audit.py').read_bytes())
    (root/'.venv').symlink_to(ROOT/'.venv',target_is_directory=True)
    testdir=root/'05_TESTS/CONTRACTS';testdir.mkdir(parents=True)
    for source in (ROOT/'05_TESTS/CONTRACTS').glob('*.py'):(testdir/source.name).write_bytes(source.read_bytes())
    tests=['test_structure_reading.py','test_query_latency_cache.py']
    if basis.endswith('_r4'):tests.append('test_process_search_cache.py')
    cmd=[str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py'),str(root),
         *[str(testdir/t) for t in tests],'--junitxml='+str(OUT/('CONTRACTS_'+basis+'.xml'))]
    r=subprocess.run(cmd,cwd=root,env=env,text=True,capture_output=True,timeout=180)
    (OUT/('CONTRACTS_'+basis+'.log.gz')).write_bytes(gzip.compress((r.stdout+r.stderr).encode(),mtime=0))
    assert r.returncode==0,r.stdout+r.stderr
