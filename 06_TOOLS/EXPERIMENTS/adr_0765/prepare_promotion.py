from pathlib import Path
import json,hashlib,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0765-bounded-wiki-recall';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
r=read(A/'artifacts/run-001/result.json');assert r['strict_success']
for row in read(A/'artifacts/working-install-receipt.json')['files']:assert sha(R/row['path'])==row['after']
v=read(A/'artifacts/working-verification.json');assert not v['new_failures'] and v['new_contracts_pass']
qualification={'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'integrated','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}
authorization={'authorized_by':'user','authorization_text':'사용자: 제안한 저장 시 정리·단회 검색·기존 agent 판단 통합·미도움 시 기존 조사 흐름 기반으로 재설계해서 돌아가게 만들고 지금 MAIN에서 잘 돌아가게 만들어줘. 검증된 동일 코드 로컬 MAIN 반영 승인. GENOS 배포 별도.','quality_gate_override':False,'qualification':qualification,'rollback_pipeline':bound(A/'artifacts/working-backup/00_SYSTEM/PIPELINE.json')}
validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'working_verification':bound(A/'artifacts/working-verification.json'),'working_tests':bound(A/'artifacts/working-all.xml'),
 'limitations':['22 new memory contracts pass; the relevant 171-test suite has the same 25 legacy failures in selected MAIN53 and candidate, zero new regressions.','Three paired public-only cases and synthetic historical records certify wiring, access and bounded retrieval; not overall CM semantic recall or statistical latency.','Word and Korean bigram index may miss paraphrases without lexical overlap. No vector/model search.','GENOS inaccessible; field behavior unverified. Historical graph issues recorded separately.']}
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/read(D/'freeze.json')['code_root']/'02_BACKEND'))
from semantic_runtime.release_qualification import verify
verify(R,authorization,validation)
put(A/'artifacts/main-authorization.json',authorization);put(A/'artifacts/main-validation.json',validation)
print('Qualification verified; no quality waiver')
