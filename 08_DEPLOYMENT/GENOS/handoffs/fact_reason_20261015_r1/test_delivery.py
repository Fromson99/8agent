"""Actual standalone TXT, existing checkout, synthetic data and loopback TLS only."""
import gzip,hashlib,importlib.util,json,os,subprocess,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
import pytest
from conftest import term_glossary
from test_compact_v2_rag import structured_generation
from test_unit_fulltext_adaptive_read import tree as source_tree
from test_genos_urllib_transport import certificates,server,MODEL
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
PRIOR=OUT.with_name('length_recovery_20261014_r1')
RUN=OUT/'GENOS_FACT_REASON_20261015_R1_RUN.txt'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
spec=importlib.util.spec_from_file_location('dependency_delivery_installer',OUT/'apply_patch.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

@pytest.fixture
def tree(tmp_path_factory,term_glossary):
    return source_tree.__wrapped__(tmp_path_factory.mktemp('dependency-synthetic-api-data'),term_glossary)

@pytest.mark.parametrize('kind,budget_enabled',[('query_latency_20261007_r3',False),('query_latency_20261007_r4',True)])
def test_install_service_api_repeat_tamper_undo_and_gate(tmp_path,structured_generation,tree,certificates,kind,budget_enabled):
    fixture=next(row for row in json.loads((PRIOR/'FIXTURES.json').read_bytes()) if row['kind']==kind)
    archive=PRIOR/fixture['path'];assert sha(archive.read_bytes())==fixture['sha256']
    root=tmp_path/'DEV';root.mkdir();transfer=tmp_path/'actual-upload-TRANSFER';transfer.mkdir()
    with zipfile.ZipFile(archive) as z:z.extractall(root)
    patch=json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))
    # The sealed CM fixture has an intentionally non-existent example NFS
    # binding. Bind only its supported operator configuration to synthetic
    # data before taking the preservation baseline; do not change code.
    config=root/'00_SYSTEM/GENOS_SERVING_PATHS.json'
    if config.exists():
        value=json.loads(config.read_bytes())
        digest=sha((structured_generation/'manifest.json').read_bytes())
        value.update(generation=str(structured_generation),runtime=str(tmp_path/'runtime'),
                     generation_manifest_sha256=digest,source='synthetic local installer validation')
        config.write_bytes(installer.encoded(value))
        manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
        # The legacy display builder fabricated minimal metadata for its CM
        # inventory enumeration. Actual code_ship.pack writes this format;
        # reconstruct that metadata for a real release-gate fixture.
        if 'format' not in manifest:
            assert manifest['schema_version']=='genos-code-ship-v1'
            assert '"format": "8agent-code/1"' in (root/'06_TOOLS/COMMANDS/code_ship.py').read_text()
            manifest['format']='8agent-code/1'
        manifest['cm_oneclick']['generation_manifest_sha256']=digest
        for row in manifest['files']:
            if row['path']=='00_SYSTEM/GENOS_SERVING_PATHS.json':row.update(sha256=sha(config.read_bytes()),bytes=config.stat().st_size)
        (root/'CODE_MANIFEST.json').write_bytes(installer.encoded(manifest))
    if budget_enabled:
        previous=(root/'CODE_MANIFEST.json').read_bytes();manifest=json.loads(previous)
        service=root/'service.py';service.write_bytes(installer.budget_transform(service.read_bytes(),patch,restore=True))
        policy=patch['budget_policy']
        manifest['investigation_budget_settings']={'revision':policy['revision'],'prior_inventory_sha256':sha(previous),'modified_paths':['service.py'],'settings':policy['settings'],'default_model_attempts_changed':False,'field_deployed':False}
        for row in manifest['files']:
            if row['path']=='service.py':row.update(sha256=sha(service.read_bytes()),bytes=service.stat().st_size)
        (root/'CODE_MANIFEST.json').write_bytes(installer.encoded(manifest))
    # Exercise the existing schema base and the latest length-recovery output.
    # This creates only a synthetic predecessor fixture, never field code.
    physical_before={}
    if budget_enabled:
        prior_path=OUT.with_name('length_recovery_20261015_r2')
        oldspec=importlib.util.spec_from_file_location('fact_length_predecessor',prior_path/'apply_patch.py')
        oldinst=importlib.util.module_from_spec(oldspec);oldspec.loader.exec_module(oldinst)
        oldpatch=json.loads(gzip.decompress((prior_path/'PATCH_SPEC.json.gz').read_bytes()))
        _,_,changes,_,_=oldinst.prepared(root,oldpatch)
        for name,raw in changes.items():
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    before_manifest=(root/'CODE_MANIFEST.json').read_bytes();before=json.loads(before_manifest)
    before_files={row['path']:(root/row['path']).read_bytes() for row in before['files']}
    generation=structured_generation
    genhashes={str(p.relative_to(generation)):sha(p.read_bytes()) for p in generation.rglob('*') if p.is_file()}
    env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),'GENOS_DEV_ROOT':str(root),'GENOS_PYTHON_DIR':str(ROOT/'.venv/bin'),
         'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'GENOS_GENERATION':str(generation),
         'GENOS_RUNTIME_DIR':str(tmp_path/'runtime'),'GENOS_SYSTEM_LOG_DIR':str(tmp_path/'logs'),'GENOS_LOG_SPOOL_DIR':str(tmp_path/'spool'),
         'GENOS_RAG_IMPLEMENTATION':'legal-agent-unified-v6','GENOS_LLM_MODEL':MODEL,'GENOS_BASE_URL':'https://synthetic-genos.invalid',
         'GENOS_LLM_SERVING_ID':'1','GENOS_LLM_KEY':'synthetic-test-key','SEMANTIC_LLM_BACKEND':'genos','GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0',
         'METRICS_TEST_GENERATION':str(tree[0]),'METRICS_TEST_UNIT_INDEX':str(tree[1].path),'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'}
    for key in ('LEGAL_AGENT_PROFILE','LEGAL_AGENT_PROFILE_SHA256','GENOS_LLM_URL','GENOS_PATCH_DEV','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy','SSL_CERT_FILE','SSL_CERT_DIR'):
        env.pop(key,None)
    if budget_enabled:env.update(GENOS_RAG_MAX_MODEL_ATTEMPTS='60',GENOS_RAG_MAX_TOOL_ACTIONS='2048',GENOS_RAG_WALL_SECONDS='3600',GENOS_RAG_SEARCH_ROUNDS='12',GENOS_RAG_ASSESSMENT_REENTRY_LIMIT='0')
    transcript=[]
    def run(args,success=True,work=root):
        r=subprocess.run(args,cwd=work,env=env,text=True,capture_output=True,timeout=240)
        transcript.append({'argv':args,'cwd':str(work),'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        (OUT/('TEST_'+kind+'.json.gz')).write_bytes(gzip.compress(json.dumps(transcript,ensure_ascii=False).encode(),mtime=0))
        assert (r.returncode==0)==success,r.stdout+r.stderr
        return r
    def txt(*args,success=True):return run(['bash',str(RUN),*args],success,transfer)
    run(['git','init','-q',str(root)])
    run(['git','add','-f','--','CODE_MANIFEST.json',*before_files])
    run(['git','-c','user.name=Synthetic validation','-c','user.email=validation@example.invalid','commit','-qm','Exact predecessor fixture'])
    txt('check');txt('install');txt('install');txt('verify')
    assert (transfer/'fact-reason-r1-logs').is_dir()
    backups=list((root/'TRANSFER/fact-reason-r1').glob('backup-*'));assert len(backups)==1
    backup=backups[0];receipt=json.loads((backup/'receipt.json').read_bytes())
    assert set(receipt['adopted_unrecorded_files'])==set(physical_before)
    for name,raw in physical_before.items():
        assert (backup/name).read_bytes()==raw
        record=next(r for r in receipt['files'] if r['path']==name)
        assert record['before_sha256']==sha(raw) and record['mode']==0o640 and record['inventory_before']=='ABSENT'

    allowed={'CODE_MANIFEST.json','00_SYSTEM/PIPELINE.json'}|set(json.loads((OUT/'SOURCE_BINDING.json').read_bytes())['source_files'])
    allowed|={row['manifest'] for row in json.loads(before_files['00_SYSTEM/PIPELINE.json'])['engines'].values()}
    assert {row['path'] for row in receipt['files']}<=allowed
    assert all((root/n).read_bytes()==raw for n,raw in before_files.items() if n not in allowed)
    assert json.loads((root/'CODE_MANIFEST.json').read_bytes()).get('investigation_budget_settings')==before.get('investigation_budget_settings')
    binding=json.loads((OUT/'SOURCE_BINDING.json').read_bytes())
    for n,variants in binding['field_variants'].items():assert sha((root/n).read_bytes())==variants[sha(before_files[n]) if n in before_files else 'ABSENT']
    diagnostic='02_BACKEND/semantic_runtime/legal_agent/investigation_diagnostics.py'
    assert (b"'traceback':" in (root/diagnostic).read_bytes())==(b"'traceback':" in before_files[diagnostic])
    postboot='''import asyncio,json,socket,sys
original_connect=socket.socket.connect
def loopback_only(sock,address):
 assert address[0]=='127.0.0.1','non-loopback network denied'
 return original_connect(sock,address)
socket.socket.connect=loopback_only
import service
from semantic_runtime import stdlib_http
reply=asyncio.run(service.service({}, {'API_TYPE':'HEALTH'}))
assert reply['status']==200,reply
assert service._BINDING['mode']=='genos-generation'
p=service._APP.state.pipeline.term_agent.profile
assert p['candidate_navigation']['completion_policy_version']=='investigation-completion-v8'
from semantic_runtime.legal_agent import completion_contracts as cc
assert '결론을 하나로 확정하려면' in cc.GAP_WORDS['MISSING_FACT']
assert p['request_entry_policy']=='fused-title-v1'
assert stdlib_http.REVISION=='genos-urllib-tls-20261008-r1'
import os
if os.environ.get('GENOS_RAG_MAX_MODEL_ATTEMPTS')=='60':
 assert p['max_model_attempts']==60 and p['max_tool_actions']==2048 and p['wall_seconds']==3600
 assert p['candidate_navigation']['search_rounds']==12 and p['candidate_navigation']['assessment_reentry_limit']==0
print('SERVICE_TLS_BOOTSTRAP PASS; real service.service; synthetic loopback model discovery; inference=0')
'''
    with server(certificates) as (target,transport,state):
        env.update(GENOS_BASE_URL=target.root,SSL_CERT_FILE=str(certificates/'ca.pem'))
        run([str(ROOT/'.venv/bin/python'),'-c',postboot])
        assert len(state['calls'])==1 and state['calls'][0]['method']=='GET' and state['calls'][0]['path'].endswith('/models')
    suites=[ROOT/'05_TESTS/CONTRACTS/test_assessment_gap_action.py',
            ROOT/'05_TESTS/CONTRACTS/test_narrative_answer.py',OUT/'test_fact_display.py']
    installed=run([str(ROOT/'.venv/bin/python'),str(OUT/'installed_runner.py'),str(root),
                   *map(str,suites),'--junitxml='+str(OUT/('INSTALLED_'+kind+'.xml'))])
    results=list(ET.parse(OUT/('INSTALLED_'+kind+'.xml')).iter('testcase'))
    assert results and not any(c.find('failure') is not None or c.find('error') is not None
                               or c.find('skipped') is not None for c in results)
    assert (root/'02_BACKEND/semantic_runtime/progress.py').read_bytes()==before_files['02_BACKEND/semantic_runtime/progress.py']

    run(['git','add','-f','--',*[row['path'] for row in receipt['files']]])
    run(['git','-c','user.name=Synthetic validation','-c','user.email=validation@example.invalid','commit','-qm','Validated fact explanation fixture'])
    gate=txt('gate',str(backup),'--generation',str(generation));assert 'GENOS_RELEASE_GATE PASS' in gate.stdout
    target=root/'02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py';saved=target.read_bytes()
    target.write_bytes(saved+b'\n# unknown edit\n')
    txt('verify',success=False);txt('undo',str(backup),success=False)
    assert target.read_bytes()==saved+b'\n# unknown edit\n';target.write_bytes(saved)
    txt('undo',str(backup))
    for name,raw in physical_before.items():
        assert (root/name).read_bytes()==raw and ((root/name).stat().st_mode & 0o777)==0o640
    assert (root/'CODE_MANIFEST.json').read_bytes()==before_manifest
    assert all((root/n).read_bytes()==raw for n,raw in before_files.items())
    assert {str(p.relative_to(generation)):sha(p.read_bytes()) for p in generation.rglob('*') if p.is_file()}==genhashes
    txt('check')
