"""Ship exact selected MAIN bytes and the already validated GENOS installer/gates.
No dataset copying, snapshot overwrite, engine repinning, or production code edits.
"""
from pathlib import Path
import ast,hashlib,json,zipfile
R=Path(__file__).resolve().parents[4];O=Path(__file__).resolve().parent
NAME='GENOS_INVESTIGATION_CONTROL_20261007_R1'
P=R/'08_DEPLOYMENT/GENOS/handoffs/investigation_logging_20261006_r2'
read=lambda p:json.loads(p.read_text());sha=lambda raw:hashlib.sha256(raw).hexdigest()
encoded=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
archive=O/(NAME+'.zip');assert not archive.exists(),'Built deliveries are immutable; create another revision.'
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/pointer['manifest_path'])
assert pointer['release_id']=='investigation-control-v6-20261007-r1' and pointer['generation']==43
assert sha((R/pointer['manifest_path']).read_bytes())==pointer['release_manifest_sha256']
for name,h in release['files'].items():
 assert sha((R/name).read_bytes())==sha((R/release['code_root']/name).read_bytes())==h,name
parent=read(P/'CODE_MANIFEST.json');pr=read(P/'HANDOFF.json');pz=P/(pr['version']+'.zip')
assert sha(pz.read_bytes())==pr['code_zip_sha256']
with zipfile.ZipFile(pz) as z:assert sha(z.read('CODE_MANIFEST.json'))==sha((P/'CODE_MANIFEST.json').read_bytes())
prior={x['path']:x for x in parent['files']+parent['required_files']}
inventory=set(release['files'])|set(prior);payload={name:(R/name).read_bytes() for name in inventory}
for name in set(prior)-set(release['files']):assert sha(payload[name])==prior[name]['sha256'],name
assert sha(payload['02_BACKEND/semantic_runtime/full_glossary.py'])==parent['expected_cache_compiler_sha256']
# Explicit known cumulative NFS diagnostics are accepted; arbitrary field edits are not.
probe=R/'08_DEPLOYMENT/GENOS/handoffs/nfs_read_probe_20261006_r7/CODE_MANIFEST.json'
probe_rows=[]
if probe.exists():
 pm=read(probe);probe_rows=pm.get('files',[])+pm.get('required_files',[])
known={x['path']:set([x['sha256'],*x.get('allowed_predecessors',[])]) for x in probe_rows}
old=read(R/'08_DEPLOYMENT/RELEASES/local-genos-unit-v6-20261006-r1/release.json')
files=[]
for name,raw in sorted(payload.items()):
 assert Path(name).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.sqlite','.sqlite3','.db','.key','.pem','.log'}
 assert not name.startswith(('01_DATA/','90_RUNTIME/','02_BACKEND/lawrag/research/candidates/'))
 if name.endswith('.py'):compile(raw,name,'exec');ast.parse(raw,feature_version=(3,11))
 row=prior.get(name,{});allowed=set(row.get('allowed_predecessors',[]))|known.get(name,set())
 if row:allowed.add(row['sha256'])
 if name in old['files']:allowed.add(old['files'][name])
 files.append({'path':name,'sha256':sha(raw),'bytes':len(raw),'allowed_predecessors':sorted(allowed),'allow_missing_predecessor':not row or row.get('allow_missing_predecessor',False)})
manifest={**parent,'id':NAME,'scope':'Exact selected local MAIN investigation-control-v2 code, for GENOS internal provider and existing generation; no dataset transfer or rebuild','parent_code_zip_sha256':pr['code_zip_sha256'],'files':files,'required_files':[],'requires_rebuilt_generation':False,'main_basis':{'pointer':pointer,'serving_files':release['files'],'extra_installer_gate_documents':sorted(set(prior)-set(release['files']))},'investigation_control_contract':'investigation-control-v2','field_deployment_status':'NOT_RUN'}
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for name,raw in sorted({**payload,'CODE_MANIFEST.json':encoded(manifest)}.items()):z.writestr(name,raw)
with zipfile.ZipFile(archive) as z:
 assert set(z.namelist())==set(payload)|{'CODE_MANIFEST.json'}
 for name,h in release['files'].items():assert sha(z.read(name))==h
 assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
archive_sha=sha(archive.read_bytes())
script=(O/'APPLY_TEMPLATE.txt').read_text().replace('@NAME@',NAME).replace('@ZIP_SHA256@',archive_sha)
(O/(NAME+'_APPLY.txt')).write_text(script)
(O/(NAME+'_WORKFLOW_PASTE_ALL.txt')).write_bytes(payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
(O/'CODE_MANIFEST.json').write_bytes(encoded(manifest))
record={'version':NAME,'created_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'code_zip_sha256':archive_sha,'code_zip_bytes':archive.stat().st_size,'code_manifest_sha256':sha(encoded(manifest)),'apply_txt_sha256':sha(script.encode()),'workflow_txt_sha256':sha(payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']),'code_files':len(files),'exact_main_serving_files':len(release['files']),'main_release_manifest_sha256':pointer['release_manifest_sha256'],'compiler_sha256':parent['expected_cache_compiler_sha256'],'requires_rebuilt_generation':False,'genos_deployed':False,'push_checkout':'~/DEV (existing field Git checkout)','field_generation_path_from_20261006_record':'/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation','actual_selected_generation':None,'actual_generation_manifest_sha256':None,'push_commit':None,'code_serving_revision':None,'field_workflow_test':'NOT_RUN','external_model_calls_for_delivery':0}
(O/'HANDOFF.json').write_bytes(encoded(record))
print(json.dumps(record,ensure_ascii=False))
