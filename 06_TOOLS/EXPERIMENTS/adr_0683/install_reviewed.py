"""Merge only reviewed scope into current development; do not activate a release."""
import difflib,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0683-core-evidence-shortcut-consumer-closure';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(A/'artifacts/run-001/result.json')['strict_success']
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');code=R/f['code_root'];b=read(D/'baseline.json');base=R/b['manifest']['code_root']
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
for p,h in f['serving_files'].items():assert sha(code/p)==h,p
scoped=[str(Path('02_BACKEND/semantic_runtime/legal_agent')/name) for name in (
    'core_evidence_route.py','shortcut_repository.py','wiki_execution.py','law_candidates.py',
    'unified_runtime.py','unified_rag.py','shortcut_cases.py','knowledge_repository.py')]
expected=read(D/'starting-binding.json')['working_before']
for p in scoped:assert sha(R/p)==expected[p],('Concurrent scope mutation',p)
patch=''
for p in scoped:
    old=(R/p).read_text().splitlines(keepends=True) if (R/p).exists() else []
    if (base/p).exists():
        merged=subprocess.run(['git','merge-file','-p',str(R/p),str(base/p),str(code/p)],capture_output=True,text=True)
        assert merged.returncode==0,('Merge requires explicit conflict resolution',p,merged.stderr)
        new=merged.stdout.splitlines(keepends=True)
    else:new=(code/p).read_text().splitlines(keepends=True)
    patch+=''.join(difflib.unified_diff(old,new,fromfile='a/'+p if old else '/dev/null',tofile='b/'+p))
pp=A/'artifacts/reviewed-runtime.patch'
if pp.exists():shutil.copy2(pp,A/'artifacts/reviewed-runtime-first-context.patch')
pp.write_text(patch)
subprocess.run(['git','apply','--check',str(pp)],cwd=R,check=True)
pipeline=read(R/'00_SYSTEM/PIPELINE.json');pins=['00_SYSTEM/PIPELINE.json']+[e['manifest'] for e in pipeline['engines'].values()]
untouched={p:sha(R/p) for p in f['serving_files'] if p not in scoped+pins}
backup=A/'artifacts/working-backup';backup.mkdir(exist_ok=False)
plan=[]
for p in scoped+pins:
    h=sha(R/p)
    if h:
        dest=backup/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/p,dest)
    plan.append({'path':p,'before':h,'kind':'runtime' if p in scoped else 'working-pins'})
put(A/'artifacts/working-install-plan.json',{'files':plan,'backup':str(backup.relative_to(R)),'selected_release_unchanged':True})
subprocess.run(['git','apply',str(pp)],cwd=R,check=True)
candidate_pipeline=read(code/'00_SYSTEM/PIPELINE.json')
pipeline['shortcut_v4']['features']['core_evidence_route']=True
pipeline['shortcut_v4']['core_route_contract']=candidate_pipeline['shortcut_v4']['core_route_contract']
new='02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py'
for engine in pipeline['engines'].values():
    ep=R/engine['manifest'];v=read(ep);v['files'][new]=sha(R/new)
    for p in v['files']:v['files'][p]=sha(R/p);assert v['files'][p],p
    put(ep,v);engine['sha256']=sha(ep)
put(R/'00_SYSTEM/PIPELINE.json',pipeline)
assert all(sha(R/p)==h for p,h in untouched.items()),'Unrelated working file changed during scoped merge'
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
for row in plan:row['after']=sha(R/row['path'])
receipt={'status':'integrated-development-only','files':plan,'backup':str(backup.relative_to(R)),
    'runtime_scope':scoped,'candidate_binding':f['candidate_manifest'],'frozen_revision':f['revision_sha256'],
    'preserved_pending_cache_and_reentry_changes':True,'unrelated_pending_files_preserved':True,'working_engine_pins_use_current_bytes':True,
    'selected_main_release':b['pointer'],'selected_main_pointer_unchanged':True,'genos_deployed':False}
put(A/'artifacts/working-install-receipt.json',receipt)
print('Merged8 scoped runtime modules and rehashed current working dependencies; selected MAIN unchanged')
