"""Ship the current direct chat transport over the validated cumulative R4 base."""
from pathlib import Path
import ast,hashlib,io,json,subprocess,tarfile,zipfile
from datetime import datetime,timezone

R=Path(__file__).resolve().parents[4];O=Path(__file__).resolve().parent
P=O.parent/'investigation_control_20261007_r4'
NAME='GENOS_NATIVE_CHAT_SSE_20261007_R1'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
encoded=lambda value:(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
archive=O/(NAME+'.zip')
assert not archive.exists(),'Published handoffs are immutable; use a new revision'
parent_record=json.loads((P/'HANDOFF.json').read_text())
parent_archive=P/(parent_record['version']+'.zip')
assert sha(parent_archive.read_bytes())==parent_record['code_zip_sha256']
with zipfile.ZipFile(parent_archive) as z:
    parent_raw=z.read('CODE_MANIFEST.json')
    assert sha(parent_raw)==parent_record['code_manifest_sha256']
    parent=json.loads(parent_raw)
    prior={r['path']:z.read(r['path']) for r in parent['files']}
payload={};rows={};changed=[]
for row in parent['files']:
    name=row['path'];old=prior[name];raw=(R/name).read_bytes()
    assert sha(old)==row['sha256']
    payload[name]=raw
    rows[name]={**row,'sha256':sha(raw),'bytes':len(raw),
        'allowed_predecessors':sorted({row['sha256'],*row.get('allowed_predecessors',[])})}
    if raw!=old:changed.append(name)
doc='07_DOCS/REFERENCE/OPERATIONS/GENOS_NATIVE_CHAT_SSE_20261007.md'
payload[doc]=(R/doc).read_bytes()
rows[doc]={'path':doc,'sha256':sha(payload[doc]),'bytes':len(payload[doc]),'allow_missing_predecessor':True}
transport={'main.py','08_DEPLOYMENT/GENOS/stream_app.py','02_BACKEND/semantic_runtime/chat_adapter.py'}
pins={n for n in changed if n.startswith('02_BACKEND/ENGINES/') or n=='00_SYSTEM/PIPELINE.json'}
carry={'06_TOOLS/COMMANDS/genos_rag_data_bundle.py'}
assert set(changed)<=transport|pins|carry,changed
assert transport<=set(changed)
for name,raw in payload.items():
    assert raw==(R/name).read_bytes()
    if name.endswith('.py'):
        compile(raw,name,'exec');ast.parse(raw,feature_version=(3,10) if '/workflow/' in name else (3,11))
    assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.db','.sqlite','.key','.pem'}
for name in pins:
    if name.startswith('02_BACKEND/ENGINES/'):
        for path,digest in json.loads(payload[name])['files'].items():
            assert sha(payload[path])==digest,(name,path)
baseline=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
assert baseline==parent['main_basis']['pointer'],'The selected baseline changed while preparing this handoff'
source_commit=subprocess.check_output(['git','rev-parse','infocz/fde/seungho/cicd'],cwd=R,text=True).strip()
assert source_commit=='388cd39208dd189b902799002884ef8c4d9025b0'
source_names=['02-els-qa/main.py','07-issuance-note/front/app.py','07-issuance-note/front/stream.py',
              '07-issuance-note/workflow/chat.py','07-issuance-note/deploy/prod.env']
source_rows=[]
with tarfile.open(O/'UPSTREAM_EVIDENCE.tar.gz','w:gz') as tar:
    for name in source_names:
        raw=subprocess.check_output(['git','show',source_commit+':'+name],cwd=R)
        info=tarfile.TarInfo(name);info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
        source_rows.append({'path':name,'sha256':sha(raw)})
    raw=subprocess.check_output(['git','show','-s','--format=fuller','36b9cc38'],cwd=R)
    info=tarfile.TarInfo('FIELD_SSE_ROLLBACK_COMMIT.txt');info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
manifest={**parent,'id':NAME,'files':[rows[n] for n in sorted(rows)],
    'parent_code_zip_sha256':parent_record['code_zip_sha256'],
    'main_basis':{'baseline_pointer':baseline,'baseline_serving_files':parent['main_basis']['serving_files'],
        'candidate_serving_files':{n:sha(payload[n]) for n in parent['main_basis']['serving_files']},
        'local_active_pointer_changed':False,'quality_experiment':False},
    'native_chat':{'entrypoint':'main:app','route':'/chat','default_transport':'json',
        'adapter_revision':'main-chat-sse-20261007-r1','sse_contract':'genos-chat-sse-v1',
        'upstream_commit':source_commit,'field_sse_support':'NOT_VERIFIED'},
    'scope':{'transport_files':sorted(transport),'engine_pin_files':sorted(pins),
        'unchanged_working_files_carried_from_other_tasks':sorted(set(changed)&carry)}}
manifest_raw=encoded(manifest)
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name,raw in sorted({**payload,'CODE_MANIFEST.json':manifest_raw}.items()):z.writestr(name,raw)
template=(P/'APPLY_TEMPLATE.txt').read_text()
template=template.replace('task_mode="${1:-all}"','task_mode="${1:-check}"')
template=template.replace('investigation-control-r4-logs','native-chat-r1-logs').replace('INVESTIGATION_CONTROL_EXIT','NATIVE_CHAT_EXIT')
template=template.replace('Integrate validated investigation control v2 and NFS tools from local MAIN generation 43',
    'Integrate direct native chat transport preserving investigation control and NFS tools')
template=template.replace("workflow_editor='NOT_APPLIED'","chat_binding='NOT_SELECTED'")
template=template.replace('Complete the code-serving revision deployment and workflow editor replacement, then test only in the workflow screen.',
    'Deploy main:app and select its /chat binding with GENOS_CHAT_TRANSPORT=json; test native SSE explicitly in the workflow test screen.')
template=template.replace("print('SERVICE_LOADER_CONTRACT PASS',binding['mode'],str(generation),flush=True)",
    """print('SERVICE_LOADER_CONTRACT PASS',binding['mode'],str(generation),flush=True)
from fastapi.testclient import TestClient
import main,json
client=TestClient(main.app)
assert client.post('/chat',json={'question':'__verify__'}).json()=={'code':0,'data':{'text':'verified'}}
response=client.post('/chat?stream=1',json={'API_TYPE':'SSE_CHECK'})
frames=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
assert frames[-1]['event']=='result' and frames[-1]['data']['sse_check']['sse_ready'] is True
assert frames[-1]['data']['chat_adapter_revision']=='main-chat-sse-20261007-r1'
print('NATIVE_CHAT_CONTRACT PASS in-process token/result; platform rendering NOT_VERIFIED',flush=True)""")
script=template.replace('@NAME@',NAME).replace('@ZIP_SHA256@',sha(archive.read_bytes()))
ast.parse(script.split("<<'LOADER_PY'\n",1)[1].rsplit('\nLOADER_PY',1)[0],feature_version=(3,11))
(O/(NAME+'_APPLY.txt')).write_text(script)
(O/'CODE_MANIFEST.json').write_bytes(manifest_raw)
record={'version':NAME,'created_at':datetime.now(timezone.utc).isoformat(),
    'code_zip_sha256':sha(archive.read_bytes()),'code_zip_bytes':archive.stat().st_size,
    'code_manifest_sha256':sha(manifest_raw),'code_files':len(rows),'apply_txt_sha256':sha(script.encode()),
    'parent_code_zip_sha256':parent_record['code_zip_sha256'],'source_code_root':str(R),
    'source_git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),
    'source_has_uncommitted_changes':True,'selected_local_baseline':baseline,
    'changed_payload_files':changed,'scope':manifest['scope'],
    'upstream':{'remote_ref':'infocz/fde/seungho/cicd','commit':source_commit,'files':source_rows,
        'archive_sha256':sha((O/'UPSTREAM_EVIDENCE.tar.gz').read_bytes()),'field_rollback_commit':'36b9cc381bf576b663956b5df19a2c7d61eb6132'},
    'requires_rebuilt_generation':False,'push_checkout':'~/DEV (existing field Git checkout)',
    'actual_selected_generation':None,'actual_generation_manifest_sha256':None,'push_commit':None,
    'code_serving_revision':None,'genos_deployed':False,'field_chat_sse':'NOT_VERIFIED',
    'local_active_pointer_changed':False,'external_model_calls':0}
(O/'HANDOFF.json').write_bytes(encoded(record))
print(json.dumps({'version':NAME,'code_files':len(rows),'zip_bytes':archive.stat().st_size,'changed':changed},ensure_ascii=False))
