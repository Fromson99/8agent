"""MAIN90 exact serving code over the previously sent, sealed GENOS cumulative package."""
from pathlib import Path
import ast,hashlib,io,json,shutil,zipfile
H=Path(__file__).resolve().parent;R=H.parents[3]
B=H.parent/'workflow_progress_20261019_r1';N='GENOS_MAIN90_RESEARCH_20261020_R1'
OLD='GENOS_WORKFLOW_PROGRESS_20261019_R1'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
assert not (H/'SEALED.json').exists()
pointer=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())
assert pointer['generation']==90 and pointer['release_id']=='durable-research-review-20261020-r1'
release=json.loads((R/pointer['manifest_path']).read_bytes());assert sha((R/pointer['manifest_path']).read_bytes())==pointer['release_manifest_sha256']
base=(B/'code.zip').read_bytes();assert sha(base)==json.loads((B/'PACKAGE_SPEC.json').read_bytes())['code_zip_sha256']
with zipfile.ZipFile(io.BytesIO(base)) as z:
    old=json.loads(z.read('CODE_MANIFEST.json'));files={r['path']:z.read(r['path']) for r in old['files']}
    assert all(sha(files[r['path']])==r['sha256'] for r in old['files'])
before=dict(files)
for n,h in release['files'].items():
    raw=(R/release['code_root']/n).read_bytes();assert sha(raw)==h,n
    files[n]=raw
# Keep the guide reference resolvable in the field-only full package. All executable
# code, workflow manifests, schemas, profiles and engine manifests remain exact MAIN90.
pipeline=json.loads(files['00_SYSTEM/PIPELINE.json'])
guide=json.loads(before['00_SYSTEM/PIPELINE.json'])['authorities']['oracle_query_serving'];assert guide in files
pipeline['authorities']['oracle_query_serving']=guide;files['00_SYSTEM/PIPELINE.json']=enc(pipeline)
for e in pipeline['engines'].values():
    assert sha(files[e['manifest']])==e['sha256']
    for n,h in json.loads(files[e['manifest']])['files'].items():assert sha(files[n])==h,n
for e in pipeline['workflows']['registered']:
    assert sha(files[e['manifest']])==e['sha256']
    for n,h in json.loads(files[e['manifest']])['files'].items():assert sha(files['02_BACKEND/workflow/'+n])==h,n
changes={n:{'before':sha(before[n]) if n in before else None,'after':sha(b)} for n,b in files.items() if before.get(n)!=b}
for n,b in files.items():
    assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.db','.sqlite','.key','.pem'}
    assert not (Path(n).name.startswith('.env') and not n.endswith('.example'))
    if n.endswith('.py'):ast.parse(b,filename=n,feature_version=(3,11))
exact=[n for n,h in release['files'].items() if sha(files[n])==h]
assert set(release['files'])-set(exact)=={'00_SYSTEM/PIPELINE.json'}
manifest={**old,'id':N,'files':[{'path':n,'sha256':sha(b),'bytes':len(b)} for n,b in sorted(files.items())],
    'required_files':[{'path':r['path'],'sha256':sha(files[r['path']])} for r in old['required_files']],
    'main90_overlay':{'base_package':OLD,'base_code_zip_sha256':sha(base),'source_pointer':pointer,
        'changes':changes,'exact_main_files':exact,'only_main_difference':'PIPELINE authorities.oracle_query_serving points to included field guide',
        'quality_certified':False,'field_status':'NOT_VERIFIED'}}
with zipfile.ZipFile(H/'code.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for n,b in sorted({**files,'CODE_MANIFEST.json':enc(manifest)}.items()):
        info=zipfile.ZipInfo(n,(2026,10,20,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,b)
(H/'CODE_MANIFEST.json').write_bytes(enc(manifest));(H/'SOURCE_POINTER.json').write_bytes((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())
binding={'base_package':OLD,'base_code_zip_sha256':sha(base),'local_main_release_manifest_sha256':pointer['release_manifest_sha256'],
    'changes':changes,'unchanged_files':len(files)-len(changes),'exact_main_files':exact,
    'pipeline_guide_reference_only':True,'field_checkout':'Existing DEV Git checkout; use verified physical path; previous field photo /workspace',
    'field_commit':None,'field_generation':None,'field_generation_manifest_sha256':None,'field_oracle_query_release':None,
    'field_codeserving_revision':None,'field_workflow_editor_saved':False,'field_verified':False,
    'local_main_changed_by_packaging':False,'working_source_changed_by_packaging':False,
    'known_legal_limitations':'Prior ADR0936 RP required source selection and current leverage paragraph citation weaknesses remain; not quality certified.'}
(H/'SOURCE_BINDING.json').write_bytes(enc(binding))
spec=json.loads((B/'PACKAGE_SPEC.json').read_bytes());spec.update(version=N,main_release=pointer['release_id'],main_generation=90,code_zip_sha256=sha((H/'code.zip').read_bytes()))
(H/'PACKAGE_SPEC.json').write_bytes(enc(spec))
for n in ('replace.py','run.py','code_smoke.py','installed_contract_runner.py','test_delivery.py','final_verify.py','prepare_package.py','compile_311.py'):
    text=(B/n).read_text().replace(OLD,N).replace('WORKFLOW_PROGRESS','MAIN90_RESEARCH').replace('workflow-progress-r1-logs','main90-research-r1-logs')
    if n=='test_delivery.py':text=text.replace("H.parent/'main88_oracle_query_20261019_r1/code.zip'","H.parent/'workflow_progress_20261019_r1/code.zip'")
    if n=='code_smoke.py':text=text.replace("'risk_team_compare_workflow':'1.10.0'","'risk_team_compare_workflow':'1.16.0'")
    (H/n).write_text(text)
run=(B/(OLD+'_RUN.txt')).read_text().replace(OLD,N).replace('WORKFLOW_PROGRESS','MAIN90_RESEARCH').replace('workflow-progress-r1-logs','main90-research-r1-logs')
(H/(N+'_RUN.txt')).write_text(run)
(H/(N+'_WORKFLOW_PASTE_ALL.txt')).write_bytes(files['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
for n in ('ORACLE_QUERY_DDL.sql','ORACLE_QUERY_IMPLEMENTATION_UTF8.txt'):shutil.copyfile(B/n,H/n)
shutil.copytree(B/'wheels',H/'wheels',dirs_exist_ok=True)
root=H/'test-code';root.mkdir(exist_ok=True)
for n,b in {**files,'CODE_MANIFEST.json':enc(manifest)}.items():
    p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
for row in json.loads(files['00_SYSTEM/WORKSPACE.json'])['roots']:(root/row['canonical_path']).mkdir(parents=True,exist_ok=True)
print(json.dumps({'code_files':len(files),'changed_files':len(changes),'unchanged_files':binding['unchanged_files'],'exact_main_files':len(exact),'code_zip_bytes':(H/'code.zip').stat().st_size}))
