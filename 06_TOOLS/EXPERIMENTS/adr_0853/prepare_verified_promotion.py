"""Prepare only the exact verified merged candidate after working checks."""
from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0853-basis-wire-integration';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
f=read(D/'freeze.json');C=R/f['code_root'];v=read(A/'artifacts/run-001/result.json');cm=read(R/f['candidate']['manifest_path'])
assert v['strict_success'] and (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
assert '214 passed' in (A/'artifacts/working-api.log').read_text()
w=read(A/'artifacts/working-consumer.json');assert w['status']=='PASS' and len(w['checks'])==10 and all(w['checks'].values())
assert all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files'])
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']
auth={'authorized_by':'user','authorization_text':'사용자: 전체 구현 설계서에 대해 이거 구현해봐. 설계·AGENTS의 작업 코드 통합→동일 코드 검증→로컬 MAIN 배선/승격→선택 포인터·실제 서비스 확인 범위. 동시 완료된 최소 출력 수정은 보존하여 검증한 부모 통합을 선택한다. GENOS 현장 배포는 별도.', 'quality_gate_override':False, 'qualification':{'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'integrated','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}}
validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'working_api':bound(A/'artifacts/working-api.log'),'working_consumer':bound(A/'artifacts/working-consumer.json'),'all711_registered_files_match':True,'limitations':v['limitations']}
put(A/'artifacts/main-authorization.json',auth);put(A/'artifacts/main-validation.json',validation)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',str(R/read(D/'data-binding.json')['path']),'--release-id','basis-link-lifecycle-20261016-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')]
with (A/'artifacts/main-prepare.log').open('x') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Prepared basis-link-lifecycle-20261016-r1')
