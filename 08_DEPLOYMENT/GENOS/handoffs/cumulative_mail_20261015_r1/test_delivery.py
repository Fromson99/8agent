"""Exact mailed-entry integration on old R4 and screenshot/fact-success states."""
import gzip,hashlib,importlib.util,json,os,subprocess,zipfile
from pathlib import Path
import pytest
from conftest import term_glossary
from test_compact_v2_rag import structured_generation
from test_genos_urllib_transport import certificates,server,MODEL

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3];BASE=OUT.parent
NAME='GENOS_CUMULATIVE_MAIL_20261015_R1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ins=load('cumulative_test_installer',OUT/'apply_patch.py')
SPEC=json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))

@pytest.mark.parametrize('kind',['early_r4','field_fact'])
def test_complete_delivery(tmp_path,structured_generation,certificates,kind):
    archive=(OUT/'fixtures/early-R4.zip' if kind=='early_r4' else BASE/'fact_reason_20261015_r2/fixtures/field-signature-predecessor.zip')
    root=tmp_path/'workspace';root.mkdir();transfer=tmp_path/'arbitrary-TRANSFER';transfer.mkdir()
    with zipfile.ZipFile(archive) as z:z.extractall(root)
    for row in json.loads((root/'00_SYSTEM/WORKSPACE.json').read_bytes())['roots']:
        (root/row['canonical_path']).mkdir(parents=True,exist_ok=True)
    config=root/ins.CONFIG;v=json.loads(config.read_bytes());g=structured_generation
    digest=sha((g/'manifest.json').read_bytes())
    v.update(generation=str(g),runtime=str(tmp_path/'runtime'),generation_manifest_sha256=digest,source='synthetic local validation')
    config.write_bytes(ins.encoded(v));manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
    manifest['format']='8agent-code/1';manifest['cm_oneclick']['generation_manifest_sha256']=digest
    for row in manifest['files']:
        if row['path']==ins.CONFIG:row.update(sha256=sha(config.read_bytes()),bytes=config.stat().st_size)
    # Preserve the exact approved field budget overlay too.
    policy=SPEC['budget_policy'];previous=ins.encoded(manifest)
    service=root/'service.py';service.write_bytes(ins.budget_transform(service.read_bytes(),SPEC,restore=True))
    manifest['investigation_budget_settings']={'revision':policy['revision'],'prior_inventory_sha256':sha(previous),
        'modified_paths':['service.py'],'settings':policy['settings'],'default_model_attempts_changed':False,'field_deployed':False}
    for row in manifest['files']:
        if row['path']=='service.py':row.update(sha256=sha(service.read_bytes()),bytes=service.stat().st_size)
    (root/'CODE_MANIFEST.json').write_bytes(ins.encoded(manifest))
    env={**os.environ,'PATH':str(ROOT/'.venv/bin')+':'+os.environ['PATH'],'GENOS_DEV_ROOT':str(root),
        'GENOS_PYTHON_DIR':str(ROOT/'.venv/bin'),'PYTHONPATH':str(root/'02_BACKEND'),
        'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'PYTHONDONTWRITEBYTECODE':'1',
        'GENOS_DATA_ROOT':str(root/'01_DATA'),'GENOS_RUNTIME_DIR':str(tmp_path/'runtime'),
        'GENOS_RAG_IMPLEMENTATION':'legal-agent-unified-v6','GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0',
        'GENOS_SYSTEM_LOG_DIR':str(tmp_path/'system-logs'),'GENOS_LOG_SPOOL_DIR':str(tmp_path/'spool'),
        'GENOS_BASE_URL':'https://synthetic.invalid','GENOS_LLM_SERVING_ID':'1','GENOS_LLM_MODEL':MODEL,
        'GENOS_LLM_KEY':'synthetic-test-key','GENOS_RAG_MAX_OUTPUT_TOKENS':'6400',
        'GENOS_RAG_MAX_MODEL_ATTEMPTS':'60','GENOS_RAG_MAX_TOOL_ACTIONS':'2048','GENOS_RAG_WALL_SECONDS':'3600',
        'GENOS_RAG_SEARCH_ROUNDS':'12','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT':'0',
        'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'}
    for k in ('GENOS_GENERATION','GENOS_LLM_URL','LEGAL_AGENT_PROFILE','LEGAL_AGENT_PROFILE_SHA256','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):env.pop(k,None)
    transcript=[]
    def run(args,ok=True,cwd=transfer):
        result=subprocess.run(list(map(str,args)),cwd=cwd,env=env,text=True,capture_output=True,timeout=240)
        transcript.append({'argv':list(map(str,args)),'cwd':str(cwd),'code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        (OUT/('TEST_'+kind+'.json.gz')).write_bytes(gzip.compress(json.dumps(transcript,ensure_ascii=False).encode(),mtime=0))
        assert (result.returncode==0)==ok,result.stdout+result.stderr
        return result
    run(['git','init','-q',root]);run(['git','-C',root,'config','user.name','Synthetic Validation']);run(['git','-C',root,'config','user.email','validation@example.invalid'])
    if kind=='field_fact':
        actual=ins.signature(ins.inventory(root,manifest),manifest,SPEC)
        assert actual=='7e3b5d20b21d33cd6e667896fdd023a9842b1c2d82dbef81892438e0b92b9686'
        run(['git','-C',root,'add','-f','.']);run(['git','-C',root,'commit','-qm','synthetic field length predecessor'])
        run(['bash',BASE/'fact_reason_20261015_r2/GENOS_FACT_REASON_20261015_R2_RUN.txt','install'])
    run(['git','-C',root,'add','-f','.']);run(['git','-C',root,'commit','--allow-empty','-qm','exact integration preimage'])
    before_manifest=(root/'CODE_MANIFEST.json').read_bytes();manifest=json.loads(before_manifest)
    before={r['path']:(root/r['path']).read_bytes() for r in manifest['files']}
    assert ins.signature(before,manifest,SPEC) in SPEC['signatures']
    generation_before={str(p.relative_to(g)):sha(p.read_bytes()) for p in g.rglob('*') if p.is_file()}
    # Original failure: same legacy GENOS_DATA_ROOT but existing fixed config.
    old=run(['bash',BASE/'search_latest_20261015_r1/GENOS_SEARCH_LATEST_20261015_R1_RUN.txt','check'],ok=False)
    assert 'CURRENT.json' in old.stdout and 'No such file or directory' in old.stdout
    assert all((root/n).read_bytes()==raw for n,raw in before.items())
    import shutil
    shutil.copy2(OUT/(NAME+'.zip'),transfer/(NAME+'.zip'))
    run(['python3','-m','zipfile','-e','./'+NAME+'.zip','./package'])
    txt=['bash','./package/'+NAME+'_RUN.txt']
    # A wrong explicit generation must fail before code changes.
    wrong=tmp_path/'wrong-generation';wrong.mkdir();(wrong/'manifest.json').write_bytes((g/'manifest.json').read_bytes())
    failed=run([*txt,'install','--generation',wrong],ok=False)
    assert 'differs from GENOS_GENERATION' in failed.stdout
    assert (root/'CODE_MANIFEST.json').read_bytes()==before_manifest
    # A well-formed but stale deployed hash must fail without code mutation.
    saved_config=config.read_bytes();stale=json.loads(saved_config);stale['generation_manifest_sha256']='f'*64
    config.write_bytes(ins.encoded(stale));stale_manifest=json.loads(before_manifest)
    stale_manifest['cm_oneclick']['generation_manifest_sha256']='f'*64
    for row in stale_manifest['files']:
        if row['path']==ins.CONFIG:row.update(sha256=sha(config.read_bytes()),bytes=config.stat().st_size)
    (root/'CODE_MANIFEST.json').write_bytes(ins.encoded(stale_manifest))
    failed=run([*txt,'install'],ok=False);assert 'deployed generation manifest changed' in failed.stdout
    config.write_bytes(saved_config);(root/'CODE_MANIFEST.json').write_bytes(before_manifest)
    run([*txt,'check']);run([*txt,'install']);run([*txt,'install']);run([*txt,'status'])
    state=json.loads((transfer/'cumulative-mail-r1-state/STATUS.json').read_bytes())
    backup=Path(state['backup']);receipt=json.loads((backup/'receipt.json').read_bytes())
    assert state['phase']=='CODE_AND_SELECTION_APPLIED_DEPLOYMENT_PENDING'
    assert len(list((root/'TRANSFER/cumulative-mail-r1').glob('backup-*')))==1
    assert (root/ins.CONFIG).read_bytes()==before[ins.CONFIG]
    assert json.loads((root/'CODE_MANIFEST.json').read_bytes())['investigation_budget_settings']==manifest['investigation_budget_settings']
    changed={r['path'] for r in receipt['files']}
    assert all((root/n).read_bytes()==raw for n,raw in before.items() if n not in changed)
    boot='''import asyncio,json,socket,sys,os
original=socket.socket.connect
def only_loopback(sock,address):
 assert address[0]=='127.0.0.1',address
 return original(sock,address)
socket.socket.connect=only_loopback
import service
value=asyncio.run(service.service({}, {'API_TYPE':'HEALTH'}))
assert value['status']==200,value
assert service._BINDING['mode']=='genos-generation'
p=service._APP.state.pipeline.term_agent.profile
assert p['max_output_tokens'] is None and p['max_model_attempts']==60 and p['max_tool_actions']==2048
assert p['candidate_navigation']['completion_policy_version']=='investigation-completion-v8'
assert 'search_selection' in service._APP.openapi()['paths']['/health']['get']['responses']['200'].get('description','') or hasattr(service._APP.state.pipeline.store,'selection')
print('SERVICE_TLS_BOOTSTRAP PASS; actual service.service; no inference')
'''
    # Service reads fixed operator config despite legacy GENOS_DATA_ROOT.
    with server(certificates) as (target,transport,server_state):
        env.update(GENOS_BASE_URL=target.root,SSL_CERT_FILE=str(certificates/'ca.pem'))
        run([ROOT/'.venv/bin/python','-c',boot],cwd=root)
        assert len(server_state['calls'])==1 and server_state['calls'][0]['method']=='GET'
    env['GENOS_BASE_URL']='https://synthetic.invalid'
    suites=[ROOT/'05_TESTS/CONTRACTS/test_search_selection.py',ROOT/'05_TESTS/CONTRACTS/test_genos_output_unlimited.py',
            ROOT/'05_TESTS/CONTRACTS/test_assessment_gap_action.py',BASE/'fact_reason_20261015_r2/test_fact_display.py']
    run([ROOT/'.venv/bin/python',OUT/'installed_runner.py',root,*suites,'--junitxml='+str(OUT/('INSTALLED_'+kind+'.xml'))],cwd=root)
    run(['git','-C',root,'add','-f','--',*[r['path'] for r in receipt['files']]])
    run(['git','-C',root,'commit','-qm','verified unified fixture'])
    run([*txt,'gate'])
    # Unknown code changes and stale generation pins never get an auto-rehash.
    target=root/'02_BACKEND/semantic_runtime/legal_agent/gateway.py';saved=target.read_bytes();target.write_bytes(saved+b'\n# unknown\n')
    run([*txt,'install'],ok=False);run([*txt,'undo'],ok=False);assert target.read_bytes()==saved+b'\n# unknown\n';target.write_bytes(saved)
    run([*txt,'undo'])
    assert (root/'CODE_MANIFEST.json').read_bytes()==before_manifest
    assert all((root/n).read_bytes()==raw for n,raw in before.items())
    assert generation_before=={str(p.relative_to(g)):sha(p.read_bytes()) for p in g.rglob('*') if p.is_file()}
    assert list((transfer/'cumulative-mail-r1-logs').glob('*.log.exit'))
    run([*txt,'check'])


def test_failed_postwrite_verification_restores_exact_code(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir()
    with zipfile.ZipFile(BASE/'fact_reason_20261015_r2/fixtures/field-signature-predecessor.zip') as z:z.extractall(root)
    before_manifest=(root/'CODE_MANIFEST.json').read_bytes();manifest=json.loads(before_manifest)
    before={r['path']:(root/r['path']).read_bytes() for r in manifest['files']}
    artifacts=tmp_path/'receipts';artifacts.mkdir()
    monkeypatch.setattr(ins,'field_identity',lambda r:{'code_root':str(r),'synthetic':True})
    def failed(root):raise RuntimeError('injected postwrite verification failure')
    monkeypatch.setattr(ins,'local_verification',failed)
    with pytest.raises(RuntimeError,match='injected'):ins.apply(root,SPEC,artifacts)
    assert (root/'CODE_MANIFEST.json').read_bytes()==before_manifest
    assert all((root/n).read_bytes()==raw for n,raw in before.items())
    receipt=json.loads(next(artifacts.glob('backup-*/receipt.json')).read_bytes())
    assert receipt['state']=='UNDONE'
    assert all(not (root/r['path']).exists() for r in receipt['files'] if r['before_sha256'] is None)
