"""Actual ZIP/TXT install, hard interruption, selection resume, API and rollback."""
import gzip,hashlib,importlib.util,json,os,subprocess,sys,zipfile
from pathlib import Path
import pytest
from conftest import term_glossary
from test_compact_v2_rag import structured_generation
from test_genos_urllib_transport import certificates,server,MODEL

H=Path(__file__).resolve().parent;R=H.parents[3];B=H.parent;NAME='GENOS_MAIN_FULL_20261016_R1'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
CONFIG='00_SYSTEM/GENOS_SERVING_PATHS.json'

@pytest.mark.parametrize('kind',['photo_legacy','unknown_full_overlay'])
def test_actual_full_delivery(tmp_path,structured_generation,certificates,kind):
    root=tmp_path/'workspace';root.mkdir()
    with zipfile.ZipFile(B/'cumulative_mail_20261015_r1/fixtures/early-R4.zip') as z:z.extractall(root)
    transfer=(root/'TRANSFER' if kind=='photo_legacy' else tmp_path/'arbitrary-TRANSFER');transfer.mkdir()
    for row in json.loads((root/'00_SYSTEM/WORKSPACE.json').read_bytes())['roots']:
        (root/row['canonical_path']).mkdir(parents=True,exist_ok=True)
    g=structured_generation;config=root/CONFIG;v=json.loads(config.read_bytes())
    v.update(generation=str(g),runtime=str(tmp_path/'runtime'),generation_manifest_sha256=sha((g/'manifest.json').read_bytes()),source='synthetic full install test')
    config.write_bytes(enc(v));manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes());manifest['format']='8agent-code/1'
    manifest['cm_oneclick']['generation_manifest_sha256']=v['generation_manifest_sha256']
    for row in manifest['files']:
        if row['path']==CONFIG:row.update(sha256=sha(config.read_bytes()),bytes=config.stat().st_size)
    (root/'CODE_MANIFEST.json').write_bytes(enc(manifest))
    llm=root/'02_BACKEND/lawrag/core/llm.py';llm.parent.mkdir(parents=True,exist_ok=True)
    legacy=subprocess.check_output(['git','show','fd09e050a:02_BACKEND/lawrag/core/llm.py'],cwd=R)
    assert sha(legacy)=='7a8494fc7b1fa84edb899f1967ff26500c358871be382554ecaeb0e9e164364a'
    llm.write_bytes(legacy if kind=='photo_legacy' else b'# synthetic unknown original, full replacement authorized\n')
    preserved={'extra.py':b'# unrelated local helper\n','.env':b'SYNTHETIC_ONLY=preserve\n','01_DATA/preserve.txt':b'synthetic input',
               '02_BACKEND/GENERATIONS/fixture/preserve.py':b'# immutable history\n'}
    for n,raw in preserved.items():p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    env={**os.environ,'PATH':str(R/'.venv/bin')+':'+os.environ['PATH'],'GENOS_PYTHON_DIR':str(R/'.venv/bin'),
         'GENOS_DEV_ROOT':str(root),'PYTHONPATH':str(root/'02_BACKEND'),'PYTHONDONTWRITEBYTECODE':'1',
         'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
         'GENOS_DATA_ROOT':str(root/'01_DATA'),'GENOS_RUNTIME_DIR':str(tmp_path/'runtime'),'GENOS_RAG_IMPLEMENTATION':'legal-agent-unified-v6',
         'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0','GENOS_SYSTEM_LOG_DIR':str(tmp_path/'logs'),'GENOS_LOG_SPOOL_DIR':str(tmp_path/'spool'),
         'GENOS_BASE_URL':'https://synthetic.invalid','GENOS_LLM_SERVING_ID':'1','GENOS_LLM_MODEL':MODEL,'GENOS_LLM_KEY':'synthetic-test-key',
         'GENOS_RAG_MAX_MODEL_ATTEMPTS':'60','GENOS_RAG_MAX_TOOL_ACTIONS':'2048','GENOS_RAG_WALL_SECONDS':'3600',
         'GENOS_RAG_SEARCH_ROUNDS':'12','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT':'0','GENOS_RAG_MAX_OUTPUT_TOKENS':'6400',
         'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'}
    for k in ('GENOS_GENERATION','GENOS_LLM_URL','LEGAL_AGENT_PROFILE','LEGAL_AGENT_PROFILE_SHA256','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):env.pop(k,None)
    transcript=[]
    def run(args,ok=True,cwd=transfer):
        result=subprocess.run(list(map(str,args)),cwd=cwd,env=env,text=True,capture_output=True,timeout=240)
        transcript.append({'argv':list(map(str,args)),'cwd':str(cwd),'code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        (H/('TEST_'+kind+'.json.gz')).write_bytes(gzip.compress(enc(transcript),mtime=0))
        assert (result.returncode==0)==ok,result.stdout+result.stderr
        return result
    run(['git','init','-q',root]);run(['git','-C',root,'config','user.name','Synthetic Validation']);run(['git','-C',root,'config','user.email','validation@example.invalid'])
    paths=[r['path'] for r in manifest['files']]+['CODE_MANIFEST.json','02_BACKEND/lawrag/core/llm.py','extra.py']
    run(['git','-C',root,'add','-f','--',*paths]);run(['git','-C',root,'commit','-qm','synthetic field preimage'])
    before={n:(root/n).read_bytes() for n in paths};before_config=config.read_bytes()
    generation_before={str(p.relative_to(g)):sha(p.read_bytes()) for p in g.rglob('*') if p.is_file()}
    if kind=='photo_legacy':
        failed=run(['bash',B/'latest_selection_20261015_r1/GENOS_LATEST_SELECTION_20261015_R1_RUN.txt','check'],ok=False)
        assert 'unrecorded existing file differs: 02_BACKEND/lawrag/core/llm.py' in failed.stdout
        assert all((root/n).read_bytes()==raw for n,raw in before.items())
    import shutil
    shutil.copyfile(H/(NAME+'.zip'),transfer/(NAME+'.zip'))
    run(['python3','-m','zipfile','-e','./'+NAME+'.zip','./package'])
    txt=['bash','./package/'+NAME+'_RUN.txt'];state_dir=transfer/'main-full-r1-state'
    wrong=tmp_path/'wrong';wrong.mkdir()
    run([*txt,'check','--generation',wrong],ok=False)
    run([*txt,'check']);assert all((root/n).read_bytes()==raw for n,raw in before.items())
    if kind=='photo_legacy':
        # Hard termination immediately after the original fixed config is moved.
        crash="""import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import replace,run
original=replace.move
def move(source,destination):
    original(source,destination)
    if source==Path(os.environ['GENOS_DEV_ROOT'])/'00_SYSTEM/GENOS_SERVING_PATHS.json':os._exit(77)
replace.move=move;sys.argv=['run.py','install'];run.main()
"""
        result=run([R/'.venv/bin/python','-c',crash,state_dir],ok=False);assert result.returncode==77
        assert not config.exists()
        run([*txt,'check'],ok=False)
        # Recover interrupted code and then inject a selection execution failure.
        fail="""import sys
sys.path.insert(0,sys.argv[1]);import run
original=run.command
def command(args,*a,**kw):
    if 'lawrag.pipeline.search_selection' in args and 'apply' in args:raise RuntimeError('synthetic selection interruption')
    return original(args,*a,**kw)
run.command=command;sys.argv=['run.py','install'];run.main()
"""
        run([R/'.venv/bin/python','-c',fail,state_dir],ok=False)
        assert json.loads((state_dir/'STATUS.json').read_bytes())['phase']=='CODE_APPLIED_SELECTION_FAILED'
    run([*txt,'install']);run([*txt,'status']);run([*txt,'install'])
    state=json.loads((state_dir/'STATUS.json').read_bytes());receipt=json.loads((Path(state['backup'])/'receipt.json').read_bytes())
    assert state['phase']=='CODE_AND_LATEST_APPLIED_DEPLOYMENT_PENDING'
    assert config.read_bytes()==before_config
    for n,raw in preserved.items():assert (root/n).read_bytes()==raw
    basis=json.loads((H/'SOURCE_BINDING.json').read_bytes())['main_basis']
    assert all(sha((root/n).read_bytes())==pin for n,pin in basis['deployment_serving_files'].items())
    assert llm.read_bytes()!=before['02_BACKEND/lawrag/core/llm.py']
    # Recover an applied selector receipt when a process dies before journaling it.
    state.pop('selection_receipt');state.pop('selection_sha256');(state_dir/'STATUS.json').write_bytes(enc(state))
    run([*txt,'install']);state=json.loads((state_dir/'STATUS.json').read_bytes());assert state['selection_receipt']
    run([R/'.venv/bin/python',B/'latest_selection_20261015_r1/installed_selection_runner.py',root],cwd=root)
    run([R/'.venv/bin/python',B/'latest_selection_20261015_r1/installed_native_runner.py',root],cwd=root)
    run([R/'.venv/bin/python',H/'installed_contract_runner.py',root,
         R/'05_TESTS/CONTRACTS/test_genos_output_unlimited.py'],cwd=root)
    boot="""import asyncio,json,socket
from pathlib import Path
original=socket.socket.connect
def only_loopback(sock,address):
    assert address[0]=='127.0.0.1',address
    return original(sock,address)
socket.socket.connect=only_loopback
import service
value=asyncio.run(service.service({}, {'API_TYPE':'HEALTH'}));assert value['status']==200,value
assert service._BINDING['mode']=='genos-generation'
p=service._APP.state.pipeline
p.store.selection.require_latest();assert p.store.selection.value['schema_version']=='filename-search-selection-v2'
from semantic_runtime.legal_agent.completion_contracts import GAP_WORDS
assert GAP_WORDS['MISSING_FACT']=='해당 사안에 적용할 결론을 하나로 확정하려면 추가 사실 정보가 필요합니다'
assert p.term_agent.profile['max_output_tokens'] is None
assert p.term_agent.profile['max_model_attempts']==60 and p.term_agent.profile['max_tool_actions']==2048
assert p.contracts.pipeline['workflows']['registered'][0]['version']==json.loads((Path.cwd()/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json').read_bytes())['version']
print('SERVICE_TLS_BOOTSTRAP PASS; selected MAIN76 and actual service.service; inference calls=0')
"""
    with server(certificates) as (target,transport,server_state):
        env.update(GENOS_BASE_URL=target.root,SSL_CERT_FILE=str(certificates/'ca.pem'))
        run([R/'.venv/bin/python','-c',boot],cwd=root)
        assert len(server_state['calls'])==1 and server_state['calls'][0]['method']=='GET'
    env['GENOS_BASE_URL']='https://synthetic.invalid'
    run(['git','-C',root,'add','-f','--',*receipt['units']]);run(['git','-C',root,'commit','-qm','verified selected MAIN76 full replacement'])
    run([*txt,'gate'])
    target=root/'service.py';saved=target.read_bytes();target.write_bytes(saved+b'\n# later user edit\n')
    selection=Path(json.loads(Path(state['selection_receipt']).read_bytes())['target']);selected_bytes=selection.read_bytes()
    run([*txt,'install'],ok=False);run([*txt,'undo'],ok=False)
    assert target.read_bytes()==saved+b'\n# later user edit\n' and selection.read_bytes()==selected_bytes
    target.write_bytes(saved)
    run([*txt,'undo']);run([*txt,'undo'])
    assert all((root/n).read_bytes()==raw for n,raw in before.items())
    for n,raw in preserved.items():assert (root/n).read_bytes()==raw
    assert generation_before=={str(p.relative_to(g)):sha(p.read_bytes()) for p in g.rglob('*') if p.is_file()}
    assert not selection.exists()
    assert list((transfer/'main-full-r1-logs').glob('*.log.exit'))
