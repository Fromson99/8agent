from pathlib import Path
import json,hashlib,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0728-navigation-input-public-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
r=read(A/'artifacts/run-001/result.json');assert r['strict_success'];install=read(A/'artifacts/working-install-receipt.json')
for row in install['files']:assert sha(R/row['path'])==row['after']
verification=read(A/'artifacts/working-verification.json');assert not verification['new_failures'] and verification['new59_pass']
qualification={'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'integrated','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}
authorization={'authorized_by':'user','authorization_text':'사용자: 일부구현된거 + 부족한거 전부다 구현해서 메인에 반영하고 실험도 돌려 외부에 데이터쏴도됨 몇몇문제만 돌려. 현재 세션의 명시적 로컬 MAIN 반영 승인. 동결 공개 검증·인용·권한·상태·내용 보존·해시 기준 통과 후 적용. GENOS 별도.','quality_gate_override':False,'qualification':qualification,'rollback_pipeline':bound(A/'artifacts/working-backup/00_SYSTEM/PIPELINE.json')}
validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'working_verification':bound(A/'artifacts/working-verification.json'),'working_tests':bound(A/'artifacts/working-all.xml'),
 'limitations':['59 compaction/boundary/native contracts and zero new failures over MAIN51 330 tests (311 baseline plus19 new compaction contracts);15 pre-existing legacy fixtures fail on both and are retained, not counted passed.', 'Three new public roots paired with MAIN51, no repeats; aggregate efficiency includes failed baseline requests, sole successful pair input improvement0.43%; semantic law accuracy, CM51 and statistical speed/stability not certified.', 'Request-sampled process RSS includes shared caches and concurrent allocations; observed peak is not exclusive per-request memory.', 'Overall experiment graph retains8 historical errors; new ADR final validations and exact source parent/rebase qualify this local release through release_qualification, without a quality override.', 'GENOS inaccessible; field deployment and resident local-server restart not performed.']}
code=R/read(D/'freeze.json')['code_root'];sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.release_qualification import verify
verify(R,authorization,validation)
put(A/'artifacts/main-authorization.json',authorization);put(A/'artifacts/main-validation.json',validation)
print('Fresh qualification bound with no quality waiver')
