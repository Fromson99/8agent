"""Actual transfer ZIP/TXT, installed checkout, interruption, gate and rollback."""
import gzip,hashlib,json,os,shutil,subprocess,zipfile
from pathlib import Path
import pytest
from conftest import term_glossary
from test_compact_v2_rag import structured_generation
from test_genos_urllib_transport import certificates,server,MODEL

H=Path(__file__).resolve().parent;R=H.parents[3];B=H.parent
NAME='GENOS_MAIN84_FOLLOWUP_20261018_R1';CONFIG='00_SYSTEM/GENOS_SERVING_PATHS.json'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()

@pytest.mark.parametrize('kind',['prior_main83','legacy_interrupted','oracle_dp'])
def test_actual_delivery(tmp_path,structured_generation,certificates,kind):
    root=tmp_path/'DEV';root.mkdir()
    with zipfile.ZipFile(B/'cumulative_mail_20261015_r1/fixtures/early-R4.zip') as z:z.extractall(root)
    if kind in ('prior_main83','oracle_dp'):
        with zipfile.ZipFile(B/'main83_host_assembly_20261018_r1/code.zip') as z:z.extractall(root)
    if kind=='oracle_dp':
        patch=B/'oracle_dp_20261016_r1';spec=json.loads((patch/'PATCH_SPEC.json').read_bytes())
        manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
        rows={r['path']:r for r in manifest['files']}
        for n,pin in spec['after'].items():
            raw=(patch/'payload'/n).read_bytes();assert sha(raw)==pin
            path=root/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            rows[n]={'path':n,'sha256':pin,'bytes':len(raw)}
        manifest['files']=list(rows.values())
        (root/'CODE_MANIFEST.json').write_bytes(enc(manifest))
    transfer=root/'TRANSFER' if kind=='prior_main83' else tmp_path/'actual uploaded files'
    transfer.mkdir()
    for row in json.loads((root/'00_SYSTEM/WORKSPACE.json').read_bytes())['roots']:
        (root/row['canonical_path']).mkdir(parents=True,exist_ok=True)
    g=structured_generation;config=root/CONFIG;v=json.loads(config.read_bytes())
    v.update(generation=str(g),runtime=str(tmp_path/'runtime'),generation_manifest_sha256=sha((g/'manifest.json').read_bytes()),source='synthetic R2 handoff')
    config.write_bytes(enc(v));m=json.loads((root/'CODE_MANIFEST.json').read_bytes());m['format']='8agent-code/1'
    m['files']=[r for r in m['files'] if r['path']!=CONFIG]+[{'path':CONFIG,'bytes':config.stat().st_size,'sha256':sha(config.read_bytes())}]
    (root/'CODE_MANIFEST.json').write_bytes(enc(m))
    preserved={'.env':b'SYNTHETIC=preserve\n','unrelated.py':b'# unrelated local helper\n',
               '01_DATA/preserved.txt':b'synthetic original','02_BACKEND/GENERATIONS/test/preserved.py':b'# history\n'}
    for n,raw in preserved.items():p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    env={**os.environ,'PATH':str(R/'.venv/bin')+':'+os.environ['PATH'],'GENOS_PYTHON_DIR':str(R/'.venv/bin'),
         'GENOS_DEV_ROOT':str(root),'PYTHONPATH':str(root/'02_BACKEND'),'PYTHONDONTWRITEBYTECODE':'1',
         'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
         'GENOS_DATA_ROOT':str(root/'01_DATA'),'GENOS_RUNTIME_DIR':str(tmp_path/'runtime'),
         'GENOS_RAG_IMPLEMENTATION':'legal-agent-unified-v6','GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0',
         'GENOS_SYSTEM_LOG_DIR':str(tmp_path/'logs'),'GENOS_LOG_SPOOL_DIR':str(tmp_path/'spool'),
         'GENOS_BASE_URL':'https://synthetic.invalid','GENOS_LLM_SERVING_ID':'1','GENOS_LLM_MODEL':MODEL,'GENOS_LLM_KEY':'synthetic-key',
         'GENOS_RAG_MAX_MODEL_ATTEMPTS':'60','GENOS_RAG_MAX_TOOL_ACTIONS':'2048','GENOS_RAG_WALL_SECONDS':'3600',
         'GENOS_RAG_SEARCH_ROUNDS':'12','GENOS_RAG_ASSESSMENT_REENTRY_LIMIT':'0','GENOS_RAG_MAX_OUTPUT_TOKENS':'6400',
         'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'}
    for key in ('GENOS_GENERATION','GENOS_LLM_URL','LEGAL_AGENT_PROFILE','LEGAL_AGENT_PROFILE_SHA256','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
        env.pop(key,None)
    transcript=[]
    def run(argv,ok=True,cwd=transfer):
        out=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,text=True,capture_output=True,timeout=240)
        transcript.append({'argv':list(map(str,argv)),'cwd':str(cwd),'exit':out.returncode,'stdout':out.stdout,'stderr':out.stderr})
        (H/('TEST_'+kind+'.json.gz')).write_bytes(gzip.compress(enc(transcript),mtime=0))
        assert (out.returncode==0)==ok,out.stdout+out.stderr
        return out
    run(['git','init','-q',root]);run(['git','-C',root,'config','user.name','Synthetic Validation']);run(['git','-C',root,'config','user.email','validation@example.invalid'])
    names=[r['path'] for r in m['files']]+['CODE_MANIFEST.json','unrelated.py']
    run(['git','-C',root,'add','-f','--',*names]);run(['git','-C',root,'commit','-qm','synthetic original'])
    before={n:(root/n).read_bytes() for n in names};original_config=config.read_bytes()
    source_before={str(p.relative_to(g)):sha(p.read_bytes()) for p in g.rglob('*') if p.is_file()}
    shutil.copyfile(H/(NAME+'.zip'),transfer/(NAME+'.zip'))
    run(['python3','-m','zipfile','-e','./'+NAME+'.zip','./'+NAME])
    txt=['bash','./'+NAME+'/'+NAME+'_RUN.txt'];state_dir=transfer/'main84-followup-r1-state'
    wrong=tmp_path/'wrong';wrong.mkdir();run([*txt,'check','--generation',wrong],ok=False)
    run([*txt,'check']);assert all((root/n).read_bytes()==raw for n,raw in before.items())
    if kind=='legacy_interrupted':
        crash="""import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import replace,run
original=replace.move
def move(source,destination):
 original(source,destination)
 if source==Path(os.environ['GENOS_DEV_ROOT'])/'00_SYSTEM/GENOS_SERVING_PATHS.json':os._exit(77)
replace.move=move;sys.argv=['run.py','apply'];run.main()
"""
        out=run([R/'.venv/bin/python','-c',crash,state_dir],ok=False);assert out.returncode==77
        assert not config.exists();run([*txt,'check'],ok=False)
    run([*txt,'apply']);run([*txt,'status']);run([*txt,'apply'])
    state=json.loads((state_dir/'STATUS.json').read_bytes());receipt=json.loads((Path(state['backup'])/'receipt.json').read_bytes())
    assert state['phase']=='CODE_APPLIED_DEPLOYMENT_PENDING'
    assert state['data_changes']==state['selection_changes']=='NONE' and config.read_bytes()==original_config
    for n,raw in preserved.items():assert (root/n).read_bytes()==raw
    basis=json.loads((H/'SOURCE_BINDING.json').read_bytes())['main_basis']
    assert all(sha((root/n).read_bytes())==pin for n,pin in basis['deployment_serving_files'].items())
    # Capture installation state before any explicit data verification.
    assert source_before=={str(p.relative_to(g)):sha(p.read_bytes()) for p in g.rglob('*') if p.is_file()}
    assert not (state_dir/'SELECTION_PLAN.json').exists()
    run([*txt,'gate-code'],ok=False)  # Uncommitted installed bytes cannot be deployment evidence.
    if kind=='prior_main83':
        run([R/'.venv/bin/python',H/'installed_contract_runner.py',root,
             R/'06_TOOLS/EXPERIMENTS/adr_0874/test_followup.py',
             R/'06_TOOLS/EXPERIMENTS/adr_0874/test_public_failure.py',
             R/'06_TOOLS/EXPERIMENTS/adr_0853/test_wire_boundaries.py',
             R/'06_TOOLS/EXPERIMENTS/adr_0848/test_gateway_minimal.py',
             R/'06_TOOLS/EXPERIMENTS/adr_0870/test_minimal_output.py',
             R/'06_TOOLS/EXPERIMENTS/adr_0870/test_contracts.py',
             R/'06_TOOLS/EXPERIMENTS/adr_0870/test_exact.py',
             R/'06_TOOLS/EXPERIMENTS/adr_0852/test_editor.py',
             R/'06_TOOLS/EXPERIMENTS/adr_0849/test_wiring.py',
             R/'06_TOOLS/EXPERIMENTS/adr_0847',
             R/'06_TOOLS/EXPERIMENTS/adr_0846/test_boundaries.py',
             R/'06_TOOLS/EXPERIMENTS/adr_0844/test_sources.py',
             R/'05_TESTS/CONTRACTS/test_law_grouped_navigation.py',
             R/'05_TESTS/CONTRACTS/test_ad_language.py',
             R/'05_TESTS/CONTRACTS/test_genos_output_unlimited.py',
             R/'05_TESTS/CONTRACTS/test_oracle_dp.py',
             R/'05_TESTS/CONTRACTS/test_oracle_dp_runtime.py',
             ],cwd=root)
    # Real GENOS-mode service bootstrap with a local TLS fake configuration endpoint.
    # Synthetic fixture selection is created explicitly by this test, never the installer.
    boot="""import asyncio,json,socket
from pathlib import Path
from lawrag.pipeline.search_selection import plan,activate
from semantic_runtime.search_selection import selection_path
import os
g=Path(json.loads(Path('00_SYSTEM/GENOS_SERVING_PATHS.json').read_text())['generation'])
if not selection_path(g).exists():activate(plan(g,latest=True))
original=socket.socket.connect
def local(sock,address):
 assert address[0]=='127.0.0.1',address
 return original(sock,address)
socket.socket.connect=local
import service
value=asyncio.run(service.service({}, {'API_TYPE':'HEALTH'}));assert value['status']==200,value
assert service._BINDING['mode']=='genos-generation'
p=service._APP.state.pipeline
assert {w['id']:w['version'] for w in p.contracts.pipeline['workflows']['registered']}=={'risk_team_compare_workflow':'1.9.1','internal_basis_discovery_workflow':'1.0.0'}
assert p.term_agent.profile['max_output_tokens'] is None
assert p.term_agent.profile['max_model_attempts']==60
from semantic_runtime.legal_agent.completion_contracts import GAP_WORDS
assert GAP_WORDS['MISSING_FACT']=='해당 사안에 적용할 결론을 하나로 확정하려면 추가 사실 정보가 필요합니다'
print('SERVICE_TLS_BOOTSTRAP PASS MAIN84; model calls=0')
"""
    with server(certificates) as (target,transport,server_state):
        env.update(GENOS_BASE_URL=target.root,SSL_CERT_FILE=str(certificates/'ca.pem'))
        run([R/'.venv/bin/python','-c',boot],cwd=root)
        assert len(server_state['calls'])==1 and server_state['calls'][0]['method']=='GET'
    env['GENOS_BASE_URL']='https://synthetic.invalid'
    run(['git','-C',root,'add','-f','--',*receipt['units']]);run(['git','-C',root,'commit','-qm','verified MAIN84 delivery'])
    run([*txt,'gate-code']);run([*txt,'gate'])
    target=root/'service.py';saved=target.read_bytes();target.write_bytes(saved+b'\n# later user edit\n')
    run([*txt,'apply'],ok=False);run([*txt,'undo'],ok=False)
    assert target.read_bytes()==saved+b'\n# later user edit\n';target.write_bytes(saved)
    run([*txt,'undo']);run([*txt,'undo'])
    assert all((root/n).read_bytes()==raw for n,raw in before.items())
    for n,raw in preserved.items():assert (root/n).read_bytes()==raw
    # Generation original files remain unchanged, including throughout explicit verification.
    assert all(sha((g/n).read_bytes())==pin for n,pin in source_before.items())
    assert list((transfer/'main84-followup-r1-logs').glob('*.log.exit'))
    (H/('PASS_'+kind+'.json')).write_bytes(enc({'status':'PASS','commands':len(transcript),'code_root':str(root),
        'exact_rollback':True,'data_preserved':True,'main_basis':basis,'model_calls':0,
        'installed_archive':state['code_zip_sha256'],'transcript_sha256':sha((H/('TEST_'+kind+'.json.gz')).read_bytes())}))
