from pathlib import Path
import hashlib,json,sys,subprocess,shutil,zipfile
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0777-schema-recovery-main';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
code=R/f['code_root'];cm=read(R/f['candidate']['manifest_path'])
backup=A/'artifacts/working-pipeline-before-promotion.json'
assert not backup.exists(),'Preserve first integration record'
changes=[]
for row in cm['files']:
    name=row['target_path'];live=R/name;after=sha(code/name);before=row.get('upstream_sha256')
    if before==after:continue
    assert (sha(live) if live.exists() else None)==before,'Concurrent working change: '+name
    changes.append({'path':name,'before':before,'after':after})
shutil.copy2(R/'00_SYSTEM/PIPELINE.json',backup)
with zipfile.ZipFile(A/'artifacts/working-preintegration.zip','x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for row in changes:
        if row['before'] is not None:z.write(R/row['path'],row['path'])
for row in changes:
    dest=R/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(code/row['path'],dest)
for name,h in f['serving_files'].items():assert sha(R/name)==h,name
for row in changes:assert sha(R/row['path'])==row['after']
put(A/'artifacts/working-integration-receipt.json',{'status':'PASS','all_serving_files_equal_frozen_candidate':True,
 'files_verified':len(f['serving_files']),'changes':changes,'baseline':read(D/'baseline.json')['pointer'],
 'integration':'Changed files only; checked upstream preimage, preserved all unrelated working files and histories'})
q={'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'recovery',
 'result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}
a={'authorized_by':'user','authorization_text':'이거 싹다 구현해봐 (approved schema failure recovery design P0-P7)',
 'quality_gate_override':False,'qualification':q,'rollback_pipeline':bound(backup)}
v={'structural_checks_passed':True,'integration':read(D/'integration.json'),
 'source_final_validation':bound(A/'artifacts/final-validation.txt'),
 'working_exact_candidate_binding':bound(A/'artifacts/working-integration-receipt.json'),'limitations':result['limitations']}
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.release_qualification import verify
verify(R,a,v);put(A/'artifacts/main-authorization.json',a);put(A/'artifacts/main-validation.json',v)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(code),
 '--generation',read(D/'baseline.json')['manifest']['data_path'],'--release-id','schema-recovery-20261014-r1',
 '--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')]
with (A/'artifacts/main-prepare.log').open('w') as log:subprocess.run(cmd,cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Working integration and qualified release prepared; not activated yet')
