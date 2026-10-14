from pathlib import Path
import hashlib,json,sys,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0772-source-provider-display';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(A/'artifacts/run-001/result.json')['strict_success']
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
f=read(D/'freeze.json')
for row in read(A/'artifacts/working-install-receipt.json')['files']:assert sha(R/row['path'])==row['after'],row['path']
for name,h in read(A/'artifacts/working-install-plan.json')['unrelated_serving_before'].items():assert sha(R/name)==h,name
cases=list(ET.parse(A/'artifacts/working-required.xml').iter('testcase'));assert len(cases)==97
assert all(t.find('failure') is None and t.find('error') is None for t in cases)
q={'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'provider-display','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}
a={'authorized_by':'user','authorization_text':'사용자의 기관별 한국어 법령 목록, internal 내부 규정 표시 및 진행 오류 숨김 요청과 이전 "메인에 연결했냐? 그리고 삼성메일로도 쏴줘"에 따라 실제 MAIN 연결을 완료한다. GENOS 편집기 적용은 별도다.','quality_gate_override':False,'qualification':q,'rollback_pipeline':bound(A/'artifacts/working-backup/00_SYSTEM/PIPELINE.json')}
v={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'working_required_tests':bound(A/'artifacts/working-required.xml'),'limitations':['Synthetic display boundary matrix only, no legal-quality or latency claim.','Consecutive notification groups do not identify individual LLM calls.','Prior UI regressions excluded from new qualification; prior logs retained.','GENOS editor saved/browser rendering not verified.']}
sys.path.insert(0,str(R/f['code_root']/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.release_qualification import verify
verify(R,a,v)
put(A/'artifacts/main-authorization.json',a);put(A/'artifacts/main-validation.json',v)
print('Qualified source, exact code and working checks bound for standard MAIN promotion')
