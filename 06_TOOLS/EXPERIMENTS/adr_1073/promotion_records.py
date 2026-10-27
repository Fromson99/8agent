"""Create source-bound promotion inputs; does not prepare or activate MAIN."""
from pathlib import Path
import hashlib,json,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1073-navigation-sql-main-qualification';D=A/'artifacts/design-r3'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):
 with p.open('x') as stream:json.dump(v,stream,ensure_ascii=False,indent=2);stream.write('\n')
f=read(D/'freeze.json');B=read(D/'baseline.json');C=R/f['code_root'];result=read(A/'artifacts/run-003/result.json')
assert result['strict_success'] and (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==B['pointer_sha256']
assert all(sha(C/n)==h for n,h in f['serving_files'].items())
targets=read(D/'candidate-preparation.json')['source_targets']
assert all(sha(R/n)==sha(C/n) for n in targets)
backup=A/'artifacts/working-pipeline-before-promotion.json';assert not backup.exists();shutil.copyfile(R/'00_SYSTEM/PIPELINE.json',backup)
q={'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'optimized','result':bound(A/'artifacts/run-003/result.json'),'rebase':bound(D/'release-rebase.json')}
auth={'authorized_by':'user','authorization_text':'오케이 이걸 메인에 반영하고 이부분 전체를 잘 반영해 빠짐없이 그리고 실험도 해봐 반영하고 이후에 온톨로지 실험을 다시해 그리고 메인은 삼성에일로 쫘줘',
 'scope':'Exact MAIN103 derivative: two SQL lookup transformations and required31pins only. Separate ontology and post-activation experiments remain separate. No inherited quality waiver.',
 'quality_gate_override':False,'qualification':q,'rollback_pipeline':bound(backup)}
validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'finite_matrix':bound(A/'artifacts/run-003/matrix.json'),'result':bound(A/'artifacts/run-003/result.json'),'supplemental_regressions':bound(A/'artifacts/run-003/supplemental.log'),'exact_working_source_hashes':{n:sha(R/n) for n in targets},'limitations':result['limitations']}
sys.dont_write_bytecode=True;sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.release_qualification import verify
from semantic_runtime.release_integration import check
assert verify(R,auth,validation)==q
integration=check(R,{'pointer':B['pointer'],'pointer_sha256':B['pointer_sha256']},f['serving_files'],validation['integration'])
put(A/'artifacts/main-authorization.json',auth);put(A/'artifacts/main-validation.json',validation)
put(A/'artifacts/promotion-records.json',{'status':'READY_FOR_STANDARD_PREPARE','qualification':q,'integration':integration,'release_id':'navigation-sql-20261027-r1','source_code_root':str(C.relative_to(R)),'data_generation':B['manifest']['data_path'],'authorization':bound(A/'artifacts/main-authorization.json'),'validation':bound(A/'artifacts/main-validation.json'),'source_manifest_immutable':True,'main_activated':False,'new_model_calls':0})
print('Qualification and exact integration verified; standard prepare ready; MAIN unchanged')
