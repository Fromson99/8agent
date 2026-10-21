"""Integrate the reviewed delta, then prepare the exact qualified snapshot."""
from pathlib import Path
import hashlib,json,subprocess,shutil,sys

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0789-risk-workflow-rag-orchestration'
D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}

assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');result=read(A/'artifacts/run-001/result.json')
assert result['strict_success'] and all(result['checks'].values())
C=R/f['code_root']
for n,h in f['serving_files'].items():assert sha(C/n)==h,n
plan=read(A/'artifacts/working-merge-plan.json')
for row in plan['changes']:
    assert sha(R/row['path'])==row['before'],row['path']
    assert sha(A/'artifacts/working-merge-preview'/row['path'])==row['after'],row['path']
backup=A/'artifacts/working-pipeline-before-promotion.json'
assert not backup.exists();shutil.copy2(R/'00_SYSTEM/PIPELINE.json',backup)
backups=A/'artifacts/working-source-before';backups.mkdir(exist_ok=False)
for row in plan['changes']:
    n=row['path'];p=R/n
    if p.is_file():
        saved=backups/n;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,saved)
    p.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(A/'artifacts/working-merge-preview'/n,p)
# Add only the new runtime dependencies that this candidate actually measures.
# Other working engine dependencies remain present and are rehashed in place.
for cp in (C/'02_BACKEND/ENGINES').rglob('*.json'):
    cv=read(cp)
    if 'files' not in cv:continue
    rel=cp.relative_to(C);p=R/rel;v=read(p)
    saved=backups/rel;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,saved)
    for n in cv['files']:
        if n not in v['files'] and n.startswith(('02_BACKEND/workflow/','02_BACKEND/semantic_runtime/')):
            assert (R/n).is_file(),n
            v['files'][n]=sha(R/n)
    put(p,v)
with (A/'artifacts/working-repin.log').open('w') as log:
    subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','rehash-engines','--apply'],cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
differences=[{'path':n,'working_sha256':sha(R/n),'candidate_sha256':h,
    'reason':'Unrelated working development or generated engine pins preserved; measured release uses frozen snapshot'}
    for n,h in f['serving_files'].items() if sha(R/n)!=h]
put(A/'artifacts/working-integration-receipt.json',{'status':'PASS','changes':plan['changes'],
    'other_working_differences':differences,'production_release_code_root':f['code_root']})
authorization={'authorized_by':'user','authorization_text':'이렇게 수정하고 메인에 반영해봐',
    'quality_gate_override':False,'qualification':{'source':bound(A/'실험/manifest.json'),
    'readme':bound(A/'README.md'),'arm':'orchestration','result':bound(A/'artifacts/run-001/result.json'),
    'rebase':bound(D/'release-rebase.json')},'rollback_pipeline':bound(backup)}
validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),
    'source_final_validation':bound(A/'artifacts/final-validation.txt'),
    'working_exact_candidate_binding':bound(A/'artifacts/working-integration-receipt.json'),
    'limitations':result['limitations']}
sys.dont_write_bytecode=True;sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.release_qualification import verify
verify(R,authorization,validation)
put(A/'artifacts/main-authorization.json',authorization);put(A/'artifacts/main-validation.json',validation)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare',
    '--code-root',str(C),'--generation',str(R/read(D/'data-binding.json')['path']),
    '--release-id','risk-rag-orchestration-20261015-r1',
    '--authorization',str(A/'artifacts/main-authorization.json'),
    '--validation',str(A/'artifacts/main-validation.json')]
with (A/'artifacts/main-prepare.log').open('w') as log:
    subprocess.run(cmd,cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Integrated scoped working sources and prepared qualified release')
