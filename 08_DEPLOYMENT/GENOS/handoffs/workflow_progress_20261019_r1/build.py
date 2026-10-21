"""Sealed MAIN88/Oracle delivery plus only the audited workflow defect fix."""
from pathlib import Path
import ast,hashlib,io,json,shutil,zipfile
H=Path(__file__).resolve().parent;R=H.parents[3]
B=H.parent/'main88_oracle_query_20261019_r1'
A=R/'09_ARTIFACTS/AUDITS/20261019-workflow-progress'
NAME='GENOS_WORKFLOW_PROGRESS_20261019_R1'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
assert not (H/'SEALED.json').exists()
base=(B/'code.zip').read_bytes()
assert sha(base)==json.loads((B/'PACKAGE_SPEC.json').read_bytes())['code_zip_sha256']
with zipfile.ZipFile(io.BytesIO(base)) as z:
    old=json.loads(z.read('CODE_MANIFEST.json'))
    files={row['path']:z.read(row['path']) for row in old['files']}
    assert all(sha(files[row['path']])==row['sha256'] for row in old['files'])
before=dict(files)
pins=json.loads((A/'pins_after.json').read_bytes())
pre=json.loads((A/'before.json').read_bytes())
for name,pin in pre.items():
    assert sha(files[name])==pin,('sealed base differs from audited preimage',name)
    data=(R/name).read_bytes();assert sha(data)==pins[name],('working drift',name)
    files[name]=data
new='02_BACKEND/semantic_runtime/request_journals.py'
assert new not in files
files[new]=(R/new).read_bytes();assert sha(files[new])==pins[new]
pipeline=json.loads(files['00_SYSTEM/PIPELINE.json'])
for row in pipeline['workflows']['registered']:
    name=row['manifest'];m=json.loads(files[name])
    for p in m['files']:m['files'][p]=sha(files['02_BACKEND/workflow/'+p])
    files[name]=enc(m);row['sha256']=sha(files[name])
for row in pipeline['engines'].values():
    name=row['manifest'];m=json.loads(files[name])
    if '02_BACKEND/semantic_runtime/progress.py' in m['files']:m['files'][new]=sha(files[new])
    for p in m['files']:m['files'][p]=sha(files[p])
    m['files']=dict(sorted(m['files'].items()))
    files[name]=enc(m);row['sha256']=sha(files[name])
files['00_SYSTEM/PIPELINE.json']=enc(pipeline)
changes={n:{'before':sha(before[n]) if n in before else None,'after':sha(b)} for n,b in files.items() if before.get(n)!=b}
for n,b in files.items():
    assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.db','.sqlite','.key','.pem'}
    assert not (Path(n).name.startswith('.env') and not n.endswith('.example'))
    if n.endswith('.py'):ast.parse(b,filename=n,feature_version=(3,11))
manifest={**old,'id':NAME,'files':[{'path':n,'sha256':sha(b),'bytes':len(b)} for n,b in sorted(files.items())],
 'required_files':[{'path':r['path'],'sha256':sha(files[r['path']])} for r in old['required_files']],
 'workflow_progress_overlay':{'base_code_zip_sha256':sha(base),'changes':changes,'audit':'20261019-workflow-progress',
 'answer_stream':'verified result chunks; not live model generation','field_status':'NOT_VERIFIED'}}
with zipfile.ZipFile(H/'code.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for n,b in sorted({**files,'CODE_MANIFEST.json':enc(manifest)}.items()):
        info=zipfile.ZipInfo(n,(2026,10,19,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,b)
(H/'CODE_MANIFEST.json').write_bytes(enc(manifest))
(H/'SOURCE_POINTER.json').write_bytes((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())
(H/'SOURCE_BINDING.json').write_bytes(enc({'base':'GENOS_MAIN88_ORACLE_QUERY_20261019_R1',
 'base_zip_sha256':sha(base),'audit_preimages_match':True,'changes':changes,'unchanged_files':len(files)-len(changes),
 'field_checkout':'existing DEV; physical /workspace confirmed in earlier field photo','field_commit':None,
 'field_generation':None,'field_generation_manifest_sha256':None,'field_codeserving_revision':None,
 'working_fix_sha256':{n:pins[n] for n in [*pre,new]},'local_main_changed':False}))
spec=json.loads((B/'PACKAGE_SPEC.json').read_bytes());spec.update(version=NAME,code_zip_sha256=sha((H/'code.zip').read_bytes()))
(H/'PACKAGE_SPEC.json').write_bytes(enc(spec))
for n in ('replace.py','run.py','code_smoke.py','installed_contract_runner.py','test_delivery.py','final_verify.py'):
    text=(B/n).read_text().replace('GENOS_MAIN88_ORACLE_QUERY_20261019_R1',NAME).replace('MAIN88_ORACLE_QUERY','WORKFLOW_PROGRESS').replace('main88-oracle-query-r1-logs','workflow-progress-r1-logs')
    if n=='test_delivery.py':text=text.replace("H.parent/'session_identity_20261019_r1/code.zip'","H.parent/'main88_oracle_query_20261019_r1/code.zip'")
    (H/n).write_text(text)
run=(B/'GENOS_MAIN88_ORACLE_QUERY_20261019_R1_RUN.txt').read_text().replace('GENOS_MAIN88_ORACLE_QUERY_20261019_R1',NAME).replace('MAIN88_ORACLE_QUERY','WORKFLOW_PROGRESS').replace('main88-oracle-query-r1-logs','workflow-progress-r1-logs')
(H/(NAME+'_RUN.txt')).write_text(run)
(H/(NAME+'_WORKFLOW_PASTE_ALL.txt')).write_bytes(files['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'])
for n in ('ORACLE_QUERY_DDL.sql','ORACLE_QUERY_IMPLEMENTATION_UTF8.txt'):
    shutil.copyfile(B/n,H/n)
shutil.copytree(B/'wheels',H/'wheels',dirs_exist_ok=True)
root=H/'test-code';root.mkdir(exist_ok=True)
for n,b in {**files,'CODE_MANIFEST.json':enc(manifest)}.items():
    p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
for row in json.loads(files['00_SYSTEM/WORKSPACE.json'])['roots']:(root/row['canonical_path']).mkdir(parents=True,exist_ok=True)
print(json.dumps({'code_files':len(files),'changed_files':len(changes),'code_zip_bytes':(H/'code.zip').stat().st_size}))
