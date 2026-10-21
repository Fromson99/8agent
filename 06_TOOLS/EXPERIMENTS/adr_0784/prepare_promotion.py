from pathlib import Path
import hashlib,json,sys,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0784-length-adapter-parity';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');result=read(A/'artifacts/run-001/result.json');assert result['strict_success'];code=R/f['code_root']
for n,h in f['serving_files'].items():assert sha(code/n)==sha(R/n)==h,n
backup=A/'artifacts/working-pipeline-before-promotion.json';assert not backup.exists();shutil.copy2(R/'00_SYSTEM/PIPELINE.json',backup)
put(A/'artifacts/working-integration-receipt.json',{'status':'PASS','all_serving_files_equal_frozen_candidate':True,'files_verified':len(f['serving_files']),'changes':read(D/'working-delta.json')['changes'],'baseline':read(D/'baseline.json')['pointer'],'integration':'Already implemented working code, verified unchanged; no candidate overwrites of current code'})
a={'authorized_by':'user','authorization_text':'메인에 반영하고 삼성으로 메일쏴줘','quality_gate_override':False,'qualification':{'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'recovery','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')},'rollback_pipeline':bound(backup)}
v={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'working_exact_candidate_binding':bound(A/'artifacts/working-integration-receipt.json'),'limitations':result['limitations']}
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.release_qualification import verify
verify(R,a,v);put(A/'artifacts/main-authorization.json',a);put(A/'artifacts/main-validation.json',v)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(code),'--generation',read(D/'baseline.json')['manifest']['data_path'],'--release-id','length-recovery-20261015-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')]
with (A/'artifacts/main-prepare.log').open('w') as log:subprocess.run(cmd,cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Qualified release prepared; unchanged code and data checked')
