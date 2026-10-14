"""Freeze workflow/SSE versus direct/Socket.IO routing over the preserved R1."""
from __future__ import annotations
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PARENT = OUT.parent / 'routed_socket_chat_20261007_r1'
NAME = 'GENOS_ROUTED_SOCKET_CHAT_20261007_R2'
ZIP = OUT / (NAME + '.zip')
sha = lambda raw: hashlib.sha256(raw).hexdigest()
def encode(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
if ZIP.exists():
    raise ValueError('Published handoff is immutable; use a new revision')
record = json.loads((PARENT/'HANDOFF.json').read_text())
prior = PARENT/(record['version']+'.zip')
assert sha(prior.read_bytes()) == record['code_zip_sha256']
with zipfile.ZipFile(prior) as z:
    raw = z.read('CODE_MANIFEST.json')
    assert sha(raw) == record['code_manifest_sha256']
    parent = json.loads(raw)
    payload = {r['path']:z.read(r['path']) for r in parent['files']}
rows = {r['path']:dict(r) for r in parent['files']}
changed = ('main_router.py','main_integrated.py','08_DEPLOYMENT/GENOS/start_sse.py')
added = ('main_workflow.py','07_DOCS/REFERENCE/OPERATIONS/GENOS_ROUTED_CHAT_MODES_20261007_R2.md')
for path, data in payload.items():
    if path not in changed:
        assert (ROOT/path).read_bytes() == data, 'Working code drift: '+path
for path in changed:
    raw = (ROOT/path).read_bytes()
    assert raw != payload[path]
    allowed = {sha(payload[path]),*rows[path].get('allowed_predecessors',[])}
    payload[path] = raw
    rows[path].update(sha256=sha(raw),bytes=len(raw),allowed_predecessors=sorted(allowed))
for path in added:
    raw = (ROOT/path).read_bytes(); payload[path] = raw
    rows[path] = {'path':path,'sha256':sha(raw),'bytes':len(raw),'allow_missing_predecessor':True}
for path,raw in payload.items():
    assert sha(raw)==rows[path]['sha256']
    assert Path(path).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.db','.sqlite','.pem','.key'}
    if path.endswith('.py'):
        ast.parse(raw,feature_version=(3,10) if '/workflow/' in path else (3,11))
pointer = json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
assert pointer == record['selected_local_baseline'] and pointer['generation']==44
candidate = dict(parent['main_basis']['candidate_serving_files'])
candidate.update({path:rows[path]['sha256'] for path in (*changed,*added) if path.endswith('.py')})
manifest = {**parent,'id':NAME,'files':[rows[k] for k in sorted(rows)],
    'parent_code_zip_sha256':record['code_zip_sha256'],
    'main_basis':{**parent['main_basis'],'candidate_serving_files':candidate,'local_active_pointer_changed':False},
    'scope':{'updated_entrypoints':list(changed),'added':list(added),'unchanged_parent_code_files':len(parent['files'])-len(changed)},
    'socket_chat':{'entrypoint':'main_router:app','default_mode':'workflow','workflow_mode':'workflow',
        'existing_alias':'workflow','integrated_mode':'integrated','workflow_backend_route':'/stream',
        'workflow_executor':'external-genos-python-workflow','route':'/chat','socketio_path_default':'/socket.io',
        'platform_binding_switch':'MANUAL_PLATFORM_CONFIGURATION','field_rendering':'NOT_VERIFIED'}}
raw=encode(manifest)
with zipfile.ZipFile(ZIP,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for path,data in sorted({**payload,'CODE_MANIFEST.json':raw}.items()):z.writestr(path,data)
(OUT/'CODE_MANIFEST.json').write_bytes(raw)
script=(PARENT/(record['version']+'_APPLY.txt')).read_text()
assert sha(script.encode())==record['apply_txt_sha256']
script=script.replace(record['version'],NAME).replace(record['code_zip_sha256'],sha(ZIP.read_bytes()))
script=script.replace('routed-socket-chat-r1-logs','routed-socket-chat-r2-logs')
script=script.replace('Add routed Socket.IO chat over local MAIN generation 44','Select workflow SSE or integrated Socket.IO over local MAIN generation 44')
script=script.replace("assert main_router.MODE in ('existing','integrated')","assert main_router.MODE in ('workflow','integrated')")
marker="print('ROUTED_CHAT_CONTRACT PASS',main_router.MODE,flush=True)"
assert script.count(marker)==1
script=script.replace(marker,"""if main_router.MODE=='workflow':
 import main_workflow
 assert main_router.app is main_workflow.app
print('ROUTED_CHAT_CONTRACT PASS',main_router.MODE,flush=True)""")
script=script.replace('Deploy a new code-serving revision with main_router:app, GENOS_MAIN_MODE=integrated, then select /chat and test only in the workflow screen.',
    'Deploy main_router:app with GENOS_MAIN_MODE=workflow or integrated; match the separate platform workflow/chat binding and Socket.IO option, then test only in the workflow screen.')
loader=script.split("<<'LOADER_PY'\n",1)[1].rsplit('\nLOADER_PY',1)[0];ast.parse(loader,feature_version=(3,11))
(OUT/(NAME+'_APPLY.txt')).write_text(script)
workflow=payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
(OUT/(NAME+'_WORKFLOW_PASTE_ALL.txt')).write_bytes(workflow)
push=(PARENT/(record['version']+'_PUSH_NEW_REMOTE.txt')).read_text().replace(record['version'],NAME).replace('R1','R2')
(OUT/(NAME+'_PUSH_NEW_REMOTE.txt')).write_text(push)
handoff={**record,'version':NAME,'created_at':datetime.now(timezone.utc).isoformat(),
    'code_zip_sha256':sha(ZIP.read_bytes()),'code_zip_bytes':ZIP.stat().st_size,'code_manifest_sha256':sha(raw),
    'code_files':len(rows),'apply_txt_sha256':sha(script.encode()),'parent_code_zip_sha256':record['code_zip_sha256'],
    'workflow_txt_sha256':sha(workflow),'workflow_unchanged_from_r1':True,
    'source_git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'changed_payload_files':list((*changed,*added)),'platform_binding_switch':'MANUAL_PLATFORM_CONFIGURATION',
    'email_status':'NOT_SENT','local_active_pointer_changed':False}
(OUT/'HANDOFF.json').write_bytes(encode(handoff))
print(json.dumps({'files':len(rows),'zip_sha256':handoff['code_zip_sha256'],'zip_bytes':ZIP.stat().st_size}))
