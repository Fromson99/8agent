"""Prepare the exact qualified release after integration and working checks."""
from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0845-source-terminal-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');C=R/f['code_root'];v=read(A/'artifacts/run-001/result.json')
assert v['strict_success'] and (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
assert str(v['tests_passed'])+' passed' in (A/'artifacts/working-api.log').read_text()
wc=read(A/'artifacts/working-consumer-v2.json');assert wc['status']=='PASS' and wc['qualified_component_hashes_match']
assert all(sha(C/n)==h for n,h in f['serving_files'].items())
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']
auth={'authorized_by':'user','authorization_text':'사용자: 설계 전체 구현및 검증까지 진행해줘. 설계서의 작업 코드 통합→동일 코드 검증→hash고정 승격→활성 포인터와 실제 로컬 서비스 binding 확인까지 수행한다. GENOS 반입은 별도다.',
 'quality_gate_override':False,'qualification':{'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'terminal','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}}
validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),
 'working_api':bound(A/'artifacts/working-api.log'),'working_consumer':bound(A/'artifacts/working-consumer-v2.json'),'limitations':v['limitations']}
put(A/'artifacts/main-authorization.json',auth);put(A/'artifacts/main-validation.json',validation)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',str(R/read(D/'data-binding.json')['path']),'--release-id','source-return-comparison-20261016-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')]
with (A/'artifacts/main-prepare.log').open('x') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Prepared exact qualified source-return-comparison-20261016-r1')
