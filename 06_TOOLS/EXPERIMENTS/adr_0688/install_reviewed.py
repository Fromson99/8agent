from pathlib import Path
import hashlib,json,shutil,subprocess,difflib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0688-followup-structure-observability-recovery';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(A/'artifacts/run-001/result.json')['strict_success']
f=read(D/'freeze.json');b=read(D/'baseline.json');code=R/f['code_root']
scoped=['02_BACKEND/semantic_runtime/legal_agent/'+name for name in ('structure_query.py','investigation_chain.py','law_navigation.py','judgment_view.py')]
scoped+=['02_BACKEND/semantic_runtime/progress.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
for p,h in f['serving_files'].items():assert sha(code/p)==h,p
for p in scoped:assert sha(R/p)==b['working_files'][p],('Concurrent scoped edit',p)
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
pipeline=read(R/'00_SYSTEM/PIPELINE.json');pins=['00_SYSTEM/PIPELINE.json']+[e['manifest'] for e in pipeline['engines'].values()]
untouched={p:sha(R/p) for p in f['serving_files'] if p not in scoped+pins}
backup=A/'artifacts/working-backup';backup.mkdir(exist_ok=False)
plan=[];patch=''
for p in scoped+pins:
 dest=backup/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/p,dest)
 plan.append({'path':p,'before':sha(R/p),'kind':'runtime' if p in scoped else 'working-pin'})
for p in scoped:
 patch+=''.join(difflib.unified_diff((R/p).read_text().splitlines(keepends=True),(code/p).read_text().splitlines(keepends=True),fromfile='a/'+p,tofile='b/'+p))
pp=A/'artifacts/reviewed-runtime.patch';pp.write_text(patch)
subprocess.run(['git','apply','--check',str(pp)],cwd=R,check=True)
subprocess.run(['git','apply',str(pp)],cwd=R,check=True)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0688/repin.py',str(R)],cwd=R,check=True)
for p in scoped:assert sha(R/p)==f['serving_files'][p],p
for p,h in untouched.items():assert sha(R/p)==h,('Unrelated working file modified',p)
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
for row in plan:row['after']=sha(R/row['path'])
put(A/'artifacts/working-install-receipt.json',{'status':'integrated-development-only','files':plan,
 'runtime_scope':scoped,'backup':str(backup.relative_to(R)),'candidate_manifest':f['candidate_manifest'],
 'revision_sha256':f['revision_sha256'],'validated_bytes_identical':True,'unrelated_pending_files_preserved':True,
 'selected_main_pointer_unchanged':True,'selected_main_release':b['pointer'],'genos_deployed':False,
 'rollback':'Verify each after hash and restore only these files from working-backup. Preserve subsequent unrelated changes.'})
print('Integrated six validated runtime/workflow files; scoped pins updated; selected MAIN45 and GENOS unchanged.')
