from pathlib import Path
import hashlib,json,sys,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0788-navigation-finish-delivery-recovery';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json');result=read(A/'artifacts/run-001/result.json');assert result['strict_success'];code=R/f['code_root']
for n,h in f['serving_files'].items():assert sha(code/n)==h,n
before=read(D/'working-before.json');targets=before['target_files']
for n in targets:assert sha(R/n)==before['files'][n],n
backup=A/'artifacts/working-pipeline-before-promotion.json';assert not backup.exists();shutil.copy2(R/'00_SYSTEM/PIPELINE.json',backup)
# Integrate only reviewed source modules; preserve unrelated working development.
backups=A/'artifacts/working-source-before';backups.mkdir(exist_ok=False)
for n in targets:
 p=backups/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/n,p)
 shutil.copy2(code/n,R/n)
assert all(sha(R/n)==sha(code/n) for n in targets)
with (A/'artifacts/working-repin.log').open('w') as log:
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','rehash-engines','--apply'],cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
different=[{'path':n,'working_sha256':sha(R/n),'selected_candidate_sha256':h,'reason':'Other ongoing working development excluded from this measured release'} for n,h in f['serving_files'].items() if sha(R/n)!=h]
put(A/'artifacts/working-integration-receipt.json',{'status':'PASS','target_files_equal_frozen_candidate':True,
 'integrated':{n:sha(R/n) for n in targets},'other_working_differences':different,'baseline':read(D/'baseline.json')['pointer'],
 'integration':'Only scoped modules copied after checking initial working hashes; engine pins recomputed against current working tree. Release uses exact frozen full snapshot.'})
a={'authorized_by':'user','authorization_text':'수정해봐 코드 업데이트 해봐 메인에 바로 반영하고 실험해봐','quality_gate_override':False,
 'qualification':{'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'recovery','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')},'rollback_pipeline':bound(backup)}
v={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),
 'working_exact_candidate_binding':bound(A/'artifacts/working-integration-receipt.json'),'limitations':result['limitations']}
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.release_qualification import verify
verify(R,a,v);put(A/'artifacts/main-authorization.json',a);put(A/'artifacts/main-validation.json',v)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(code),'--generation',read(D/'baseline.json')['manifest']['data_path'],
 '--release-id','navigation-delivery-recovery-20261015-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')]
with (A/'artifacts/main-prepare.log').open('w') as log:subprocess.run(cmd,cwd=R,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Integrated scoped working sources and prepared qualified release')
