"""Record verified activation separately from the immutable qualification decision."""
from pathlib import Path
import hashlib,json,datetime
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0690-judgment-loop-package-holdout'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p)
smoke=read(A/'artifacts/main-smoke.json')
assert smoke['status']=='passed' and smoke['pointer']==pointer
assert smoke['completion_contract']=='investigation-completion-v3'
assert pointer['release_id']=='judgment-loop-v6-20261008-r1'
manifest=R/pointer['manifest_path'];release=read(manifest)
assert sha(manifest)==pointer['release_manifest_sha256']
rebase=read(A/'artifacts/design/release-rebase.json')
assert release['files']==rebase['staged_files']
for name,h in release['files'].items():assert sha(R/release['code_root']/name)==h,name
scoped={}
for name in ('completion_contracts.py','law_navigation.py'):
    rel='02_BACKEND/semantic_runtime/legal_agent/'+name
    assert sha(R/rel)==sha(R/release['code_root']/rel)
    scoped[rel]=sha(R/rel)
result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
authorization=read(A/'artifacts/main-authorization.json')
for ref in authorization['qualification'].values():
    if isinstance(ref,dict) and 'path' in ref:assert sha(R/ref['path'])==ref['sha256']
record={'status':'local-main-verified','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'active_pointer':bound(p),'release_manifest':bound(manifest),'pointer':pointer,
 'qualification':authorization['qualification'],'working_scoped_sha256':scoped,
 'working_install_receipt':bound(A/'artifacts/working-install-receipt.json'),
 'working_tests':bound(A/'artifacts/working-required.xml'),'service_verification':bound(A/'artifacts/main-smoke.json'),
 'execution_binding':smoke['execution_binding'],'exact_validated_release_inventory':True,
 'git_main_merged':False,'genos_deployed':False,'resident_server_restarted':False,
 'semantic_quality_certified':False}
(A/'artifacts/main-completion.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
text=f'''# 판단 루프 보완의 로컬 MAIN 반영 결과

검증한 `judgment-loop-v6-20261008-r1`을 로컬 MAIN 포인터 generation {pointer['generation']}에 반영했다.
새 프로세스의 `service.service`에서 HEALTH·RAG_SEARCH를 실행해 코드·프로필·데이터 binding을 확인했다.
실행 중인 별도 로컬 서버를 재시작한 기록이나 GENOS 배포 결과는 아니다.

- 작업 코드: 부족 식별·행동별 완료 증명·공유 판단 표시를 보완한 두 파일과 관련 검사를 선택 반영했다.
- 검증 코드 → 선택 릴리스: 전체 서빙 파일의 해시가 동결 패키지와 일치한다.
- 작업 코드의 병행 저장공간·감사 기능 수정은 보존했으며 이번 선택 패키지와 구분한다.
- 계약 검사 37개 통과. 유지 회귀는 수정 전후 같은 1개 실패이며 새로운 실패는 없다.
- 실제 공개 모델 비교와 판정은 [실험 보고서](README.md), 의미상 누락·단정은 [의미 검토](SEMANTIC_REVIEW.md)를 따른다.
- Git main 병합·GENOS 현장 반입·배포는 수행하지 않았다.

[완료 영수증](artifacts/main-completion.json) · [실제 진입점 검사](artifacts/main-smoke.json) · [작업 반영 영수증](artifacts/working-install-receipt.json)

승격 이후 인용·권한·상태·해시·연결 문제가 확인되면 stable `rag_main_promotion.py rollback`의 명시적 `--confirm-main` 절차로 이전 선택 포인터를 복구한다.
작업 코드 복구는 별도 `rollback_working.py --confirm-working-rollback`으로 적용 이후 변경 여부를 확인한 뒤 이번 수정만 되돌린다.
'''
(A/'MAIN_RESULT.md').write_text(text)
print(json.dumps({'status':record['status'],'release':pointer['release_id'],'generation':pointer['generation']},ensure_ascii=False))
