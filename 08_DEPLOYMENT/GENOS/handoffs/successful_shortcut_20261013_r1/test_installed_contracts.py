"""Exercise scoped SEARCH_BODY and cache regressions in the installed code."""
import gzip, importlib.util, json, os, subprocess, zipfile
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
         'GENOS_AUTO_WARMUP':'0','GENOS_TEST_INSTALLED_TRANSPORT':'1','LAWRAG_TOKEN_TEST_REPOSITORY':str(ROOT)}
    for key in ('GENOS_PATCH_DEV','GENOS_GENERATION','GENOS_DATA_ROOT'):env.pop(key,None)
    steps=[('db_log_rollback_20261007_r3','GENOS_DB_LOG_ROLLBACK_20261007_R3')]
    steps += [(f'rag_focused_rules_20261013_r{i}',f'GENOS_RAG_FOCUSED_RULES_20261013_R{i}') for i in (1,2,3)]
    steps.append(('rag_narrative_stream_20261013_r2','GENOS_RAG_NARRATIVE_STREAM_20261013_R2'))
    steps.append(('model_stream_fix_20261013_r1','GENOS_MODEL_STREAM_FIX_20261013_R1'))
    for folder,name in steps:
        r=subprocess.run(['bash',str(OUT.with_name(folder)/(name+'_RUN.txt')),'apply'],cwd=root,env=env,text=True,capture_output=True,timeout=90)
        assert r.returncode==0,r.stdout+r.stderr
    budget_dir=OUT.with_name('investigation_budget_20261007_r1')
    module_spec=importlib.util.spec_from_file_location('budget_for_contracts',budget_dir/'install_budget.py')
    budget_installer=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(budget_installer)
    _,_,changes,_=budget_installer.prepare(root,json.loads((budget_dir/'PATCH_SPEC.json').read_bytes()))
    for name,raw in changes.items():(root/name).write_bytes(raw)
    steps_final=[('ad_request_logs_20261013_r2','GENOS_AD_REQUEST_LOGS_20261013_R2'),('successful_shortcut_20261013_r1','GENOS_SUCCESSFUL_SHORTCUT_20261013_R1')]
    for folder,name in steps_final:
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
    src=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0769/polished/revisions/rev-001/snapshot/05_TESTS/CONTRACTS/test_narrative_answer.py'
    (testdir/src.name).write_text(src.read_text().replace('contracts_root=ROOT,',"contracts_root=ROOT,runtime_root=tmp_path/'runtime',"))
    src=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0770/token/revisions/rev-003/snapshot/05_TESTS/CONTRACTS/test_token_answer_stream.py'
    (testdir/src.name).write_text(src.read_text().replace('contracts_root=ROOT,',"contracts_root=ROOT,runtime_root=tmp_path/'runtime',"))
    stream_test=(ROOT/'05_TESTS/CONTRACTS/test_genos_answer_stream.py').read_text()
    stream_test=stream_test.replace("'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'",repr(str(ROOT/'08_DEPLOYMENT/GENOS/handoffs/workflow_live_progress_20261008_r4/genos_rag_chat.py')))
    transport_fixture=(OUT.with_name('rag_narrative_stream_20261013_r2')/'field_transport_fixture.txt').read_text()
    begin=stream_test.index('    import io\n',stream_test.index('def transport('))
    end=stream_test.index("    target = endpoint(",begin)
    stream_test=stream_test[:begin]+transport_fixture+stream_test[end:]
    (testdir/'test_genos_answer_stream.py').write_text(stream_test)
    for source in (ROOT/'05_TESTS/REGRESSION/core').glob('test_genos_request_*.py'):(testdir/source.name).write_bytes(source.read_bytes())
    tests=['test_successful_shortcut.py','test_successful_core_routes.py','test_ad_pagination.py','test_ad_language.py','test_ad_request_reports.py','test_genos_model_stream_completion.py']
    assert not (root/'02_BACKEND/semantic_runtime/legal_agent/wiki_recall.py').exists()
    assert not json.loads((root/'00_SYSTEM/PIPELINE.json').read_text())['shortcut_v4']['features'].get('bounded_recall',False)
    cmd=[str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0773/run_tests.py'),str(root),
         *[str(testdir/t) for t in tests],'--junitxml='+str(OUT/('CONTRACTS_'+basis+'.xml'))]
    r=subprocess.run(cmd,cwd=root,env=env,text=True,capture_output=True,timeout=180)
    (OUT/('CONTRACTS_'+basis+'.log.gz')).write_bytes(gzip.compress((r.stdout+r.stderr).encode(),mtime=0))
    assert r.returncode==0,r.stdout+r.stderr
