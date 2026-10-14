"""Bind completed qualification and working verification to stable promotion."""
from pathlib import Path
import json,hashlib,sys,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
r=read(A/'artifacts/run-001/result.json');assert r['strict_success'];install=read(A/'artifacts/working-install-receipt.json')
for row in install['files']:assert sha(R/row['path'])==row['after'],row['path']
tests=list(E.parse(A/'artifacts/working-required.xml').iter('testcase'));assert len(tests)>=100 and all(t.find('failure') is None and t.find('error') is None for t in tests)
qualification={'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'compact','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}
authorization={'authorized_by':'user','authorization_text':'사용자: 진햅해봐. 직전 입력 최적화 설계를 진행하도록 지시했고, 앞선 검증 코드 MAIN 반영 요청의 범위에 따라 로컬 MAIN 통합까지 수행한다. 후보의 토큰/호출/인용/권한/상태 기준 통과를 전제로 하며 GENOS는 제외한다.','quality_gate_override':False,'qualification':qualification,
 'rollback_pipeline':bound(A/'artifacts/working-backup/00_SYSTEM/PIPELINE.json')}
validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'working_required_tests':bound(A/'artifacts/working-required.xml'),
 'limitations':['Three independent public questions paired with MAIN49, two known regressions kept separate and 288 contracts; general legal accuracy and stable speed not certified.','Transport attempt timings include retries; server request time excludes workflow delivery.','ADR0708 reason/action mismatch and repeated rejected search proposals remain a known limitation; compact menus reduce input but do not guarantee semantic reason/action agreement; dedicated sparse repairs remain follow-up.','H02/R02 lose requested detail during existing rule-based final rendering: full claim.text has detail but rule.conclusion is underspecified; recorded in SEMANTIC_REVIEW.md. Supported response is not semantic completeness.', 'GENOS not accessed or deployed.']}

code=R/read(D/'freeze.json')['code_root'];sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.release_qualification import verify
verify(R,authorization,validation)
put(A/'artifacts/main-authorization.json',authorization);put(A/'artifacts/main-validation.json',validation)
print('Qualification bound; ready for stable prepare/apply')
