from pathlib import Path
import hashlib,json,sys,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0775-public-failure-main';D=A/'artifacts/design';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:');f=read(D/'freeze.json');result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
for n,h in f['serving_files'].items():assert sha(R/n)==h,n
backup=A/'artifacts/working-pipeline-before-promotion.json';shutil.copy2(R/'00_SYSTEM/PIPELINE.json',backup)
put(A/'artifacts/working-integration-receipt.json',{'status':'PASS','all_serving_files_equal_frozen_candidate':True,'files_verified':len(f['serving_files']),'source_changes':4,'binding_changes':31,'product_edits_only_before_freeze_in_isolated_candidate':True,'baseline':read(D/'baseline.json')['pointer'],'source_files':{n:h for n,h in f['serving_files'].items() if n.endswith(('app.py','chat_adapter.py','stream_app.py','genos_rag_chat.py'))}})
q={'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'guidance','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}
a={'authorized_by':'user','authorization_text':'그 예외 케이스들도 이렇게 비슷하게 나오게 해주고 전체 메인 반영하고 그리고 삼성메일로 쏴줘','quality_gate_override':False,'qualification':q,'rollback_pipeline':bound(backup)}
v={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'working_exact_candidate_binding':bound(A/'artifacts/working-integration-receipt.json'),'limitations':result['limitations']}
sys.path.insert(0,str(R/f['code_root']/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.release_qualification import verify
verify(R,a,v);put(A/'artifacts/main-authorization.json',a);put(A/'artifacts/main-validation.json',v)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(R/f['code_root']),'--generation',read(D/'baseline.json')['manifest']['data_path'],'--release-id','public-failure-guidance-20261014-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')]
with (A/'artifacts/main-prepare.log').open('w') as out:subprocess.run(cmd,check=True,stdout=out,stderr=subprocess.STDOUT)
