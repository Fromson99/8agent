"""Bind completed qualification and working verification to stable promotion."""
from pathlib import Path
import json,hashlib,sys,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0704-compact-progress-call-metrics';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
r=read(A/'artifacts/run-001/result.json');assert r['strict_success'];install=read(A/'artifacts/working-install-receipt.json')
for row in install['files']:assert sha(R/row['path'])==row['after'],row['path']
tests=list(E.parse(A/'artifacts/working-required.xml').iter('testcase'));assert len(tests)>=100 and all(t.find('failure') is None and t.find('error') is None for t in tests)
qualification={'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'compact-display','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}
authorization={'authorized_by':'user','authorization_text':'기존 전체 구현 및 MAIN 반영 요청에 이어 진행 표시를 압축하고 최종 접힘에 실제 LLM 호출 수와 각각 걸린 시간을 표시해 달라는 후속 요청.','quality_gate_override':False,'qualification':qualification,
 'rollback_pipeline':bound(A/'artifacts/working-backup/00_SYSTEM/PIPELINE.json')}
validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'working_required_tests':bound(A/'artifacts/working-required.xml'),
 'limitations':['Presentation-only 20 synthetic boundary combinations and 233 contracts; no new legal/model-quality claims.','Transport attempt timings include retries; server request time excludes workflow delivery.','Nine legacy fixtures failed equally in the parent and candidate; no new regression.','GENOS not accessed or deployed.']}

code=R/read(D/'freeze.json')['code_root'];sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.release_qualification import verify
verify(R,authorization,validation)
put(A/'artifacts/main-authorization.json',authorization);put(A/'artifacts/main-validation.json',validation)
print('Qualification bound; ready for stable prepare/apply')
