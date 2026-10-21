"""Ship bytes: fixed baseline, actual TXT, interruption, endpoint and same-root gate."""
import gzip,hashlib,json,os,shutil,subprocess,zipfile
from pathlib import Path
import pytest
from conftest import term_glossary
from test_compact_v2_rag import structured_generation
from test_genos_urllib_transport import certificates,server,MODEL

H=Path(__file__).resolve().parent;R=H.parents[3];B=H.parent
NAME='GENOS_READABLE_TRACE_20261016_R1';CONFIG='00_SYSTEM/GENOS_SERVING_PATHS.json'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
enc=lambda value:(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

@pytest.mark.parametrize('mode',['zip','standalone'])
def test_installed_delivery(tmp_path,structured_generation,certificates,mode):
    root=tmp_path/'DEV-real';root.mkdir();alias=tmp_path/'DEV';alias.symlink_to(root,target_is_directory=True)
    transfer=tmp_path/'arbitrary-upload-folder';transfer.mkdir()
    with zipfile.ZipFile(B/'main_full_20261016_r1/code.zip') as z:z.extractall(root)
    for row in json.loads((root/'00_SYSTEM/WORKSPACE.json').read_bytes())['roots']:
        (root/row['canonical_path']).mkdir(parents=True,exist_ok=True)
    generation=structured_generation
    config={'schema_version':'genos-serving-paths-v1','selection':'operator-fixed','generation':str(generation),
            'runtime':str(tmp_path/'runtime'),'generation_manifest_sha256':sha((generation/'manifest.json').read_bytes())}
    (root/CONFIG).write_bytes(enc(config));m=json.loads((root/'CODE_MANIFEST.json').read_bytes())
    m['files'].append({'path':CONFIG,'sha256':sha(enc(config)),'bytes':len(enc(config))})
    (root/'CODE_MANIFEST.json').write_bytes(enc(m))
    before={row['path']:(root/row['path']).read_bytes() for row in m['files']}
    before['CODE_MANIFEST.json']=(root/'CODE_MANIFEST.json').read_bytes()
    extras={'.env':b'SYNTHETIC_ONLY=preserved\n','unrelated.py':b'# keep user helper\n'}
    for n,raw in extras.items():(root/n).write_bytes(raw)
    env={**os.environ,'PATH':str(R/'.venv/bin')+':'+os.environ['PATH'],'GENOS_PYTHON_DIR':str(R/'.venv/bin'),
         'GENOS_DEV_ROOT':str(alias),'PYTHONPATH':str(root/'02_BACKEND'),'PYTHONDONTWRITEBYTECODE':'1',
         'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
         'GENOS_DATA_ROOT':str(root/'01_DATA'),'GENOS_RUNTIME_DIR':str(tmp_path/'runtime'),
         'GENOS_RAG_IMPLEMENTATION':'legal-agent-unified-v6','GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0',
         'GENOS_SYSTEM_LOG_DIR':str(tmp_path/'logs'),'GENOS_LOG_SPOOL_DIR':str(tmp_path/'spool'),
         'GENOS_BASE_URL':'https://synthetic.invalid','GENOS_LLM_SERVING_ID':'1','GENOS_LLM_MODEL':MODEL,
         'GENOS_LLM_KEY':'synthetic-test-key','GENOS_RAG_MAX_MODEL_ATTEMPTS':'60','GENOS_RAG_MAX_TOOL_ACTIONS':'2048',
         'GENOS_RAG_WALL_SECONDS':'3600','GENOS_RAG_SEARCH_ROUNDS':'12','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT':'0',
         'GENOS_RAG_MAX_OUTPUT_TOKENS':'6400','NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'}
    for key in ('GENOS_GENERATION','GENOS_LLM_URL','LEGAL_AGENT_PROFILE','LEGAL_AGENT_PROFILE_SHA256',
                'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy','GENOS_PATCH_DEV'):
        env.pop(key,None)
    transcript=[]
    def run(args,ok=True,cwd=transfer):
        value=subprocess.run(list(map(str,args)),cwd=cwd,env=env,text=True,capture_output=True,timeout=180)
        transcript.append({'argv':list(map(str,args)),'cwd':str(cwd),'returncode':value.returncode,
                           'stdout':value.stdout,'stderr':value.stderr})
        (H/('TEST_'+mode+'.json.gz')).write_bytes(gzip.compress(enc(transcript),mtime=0))
        assert (value.returncode==0)==ok,value.stdout+value.stderr
        return value
    run([R/'.venv/bin/python','-c',"from lawrag.pipeline.search_selection import plan,activate; import sys; activate(plan(sys.argv[1],latest=True))",generation],cwd=root)
    generation_before={str(p.relative_to(generation)):sha(p.read_bytes()) for p in generation.rglob('*') if p.is_file()}
    if mode=='zip':
        shutil.copyfile(H/(NAME+'.zip'),transfer/(NAME+'.zip'))
        run(['python3','-m','zipfile','-e','./'+NAME+'.zip','./package'])
        txt=['bash','./package/'+NAME+'_RUN.txt']
    else:
        shutil.copyfile(H/(NAME+'_RUN.txt'),transfer/(NAME+'_RUN.txt'))
        txt=['bash','./'+NAME+'_RUN.txt']
    drift=root/'service.py';drift.write_bytes(before['service.py']+b'\n# unknown edit\n')
    run([*txt,'check'],ok=False);assert drift.read_bytes()==before['service.py']+b'\n# unknown edit\n'
    drift.write_bytes(before['service.py'])
    run([*txt,'check']);assert all((root/n).read_bytes()==raw for n,raw in before.items())
    if mode=='zip':
        crash="""import gzip,json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import apply_patch as a
original=a.atomic
def atomic(path,raw,mode=None):
    original(path,raw,mode)
    if path==Path(os.environ['GENOS_DEV_ROOT']).resolve()/'service.py':os._exit(77)
a.atomic=atomic
a.main(json.loads(gzip.decompress((Path(sys.argv[1])/'PATCH_SPEC.json.gz').read_bytes())),['apply','--root',os.environ['GENOS_DEV_ROOT']])
"""
        value=run([R/'.venv/bin/python','-c',crash,H],ok=False);assert value.returncode==77
    run([*txt,'apply']);run([*txt,'apply']);run([*txt,'verify'])
    receipts=[p for p in (transfer/'readable-trace-r1-state').glob('backup-*/receipt.json')
              if json.loads(p.read_bytes())['state']=='VERIFIED'];assert len(receipts)==1
    receipt=json.loads(receipts[0].read_bytes());backup=receipts[0].parent
    changed={row['path'] for row in receipt['files']}
    assert all((root/n).read_bytes()==raw for n,raw in before.items() if n not in changed)
    assert (root/CONFIG).read_bytes()==before[CONFIG]
    assert all((root/n).read_bytes()==raw for n,raw in extras.items())
    source=json.loads((H/'SOURCE_BINDING.json').read_bytes())['source_files']
    assert all(sha((root/n).read_bytes())==pin for n,pin in source.items())
    run([R/'.venv/bin/python',B/'main_full_20261016_r1/installed_contract_runner.py',root,
         R/'05_TESTS/CONTRACTS/test_readable_process_trace.py',
         R/'05_TESTS/CONTRACTS/test_genos_output_unlimited.py'],cwd=root)
    boot="""import asyncio,socket
original=socket.socket.connect
def loopback(sock,address):
    assert address[0]=='127.0.0.1',address
    return original(sock,address)
socket.socket.connect=loopback
import service
result=asyncio.run(service.service({}, {'API_TYPE':'HEALTH'}));assert result['status']==200,result
assert service._BINDING['mode']=='genos-generation'
p=service._APP.state.pipeline;p.store.selection.require_latest()
assert p.term_agent.profile['max_output_tokens'] is None
assert p.term_agent.profile['max_model_attempts']==60 and p.term_agent.profile['max_tool_actions']==2048
from semantic_runtime.legal_agent.completion_contracts import GAP_WORDS
assert GAP_WORDS['MISSING_FACT']=='해당 사안에 적용할 결론을 하나로 확정하려면 추가 사실 정보가 필요합니다'
print('ACTUAL_SERVICE_BOOT PASS; field overlays preserved; synthetic model discovery only')
"""
    with server(certificates) as (target,transport,state):
        env.update(GENOS_BASE_URL=target.root,SSL_CERT_FILE=str(certificates/'ca.pem'))
        run([R/'.venv/bin/python','-c',boot],cwd=root)
        assert len(state['calls'])==1 and state['calls'][0]['method']=='GET'
    env['GENOS_BASE_URL']='https://synthetic.invalid'
    run(['git','init','-q',root]);run(['git','-C',root,'config','user.name','Synthetic Validation'])
    run(['git','-C',root,'config','user.email','validation@example.invalid'])
    current=json.loads((root/'CODE_MANIFEST.json').read_bytes())
    run(['git','-C',root,'add','-f','--','CODE_MANIFEST.json',*[row['path'] for row in current['files']]])
    run(['git','-C',root,'commit','-qm','synthetic trace delivery validation'])
    value=run([*txt,'gate']);assert 'GENOS_RELEASE_GATE PASS' in value.stdout
    saved=drift.read_bytes();drift.write_bytes(saved+b'\n# later user edit\n')
    run([*txt,'verify'],ok=False);run([*txt,'undo',backup],ok=False)
    assert drift.read_bytes()==saved+b'\n# later user edit\n';drift.write_bytes(saved)
    run([*txt,'undo',backup]);run([*txt,'undo',backup])
    assert all((root/n).read_bytes()==raw for n,raw in before.items())
    assert not (root/'02_BACKEND/semantic_runtime/process_trace.py').exists()
    assert generation_before=={str(p.relative_to(generation)):sha(p.read_bytes()) for p in generation.rglob('*') if p.is_file()}
    assert list((transfer/'readable-trace-r1-logs').glob('*.log.exit'))
