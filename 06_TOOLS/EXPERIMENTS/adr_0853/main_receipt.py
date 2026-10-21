from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0853-basis-wire-integration';D=A/'artifacts/design';O=R/'09_ARTIFACTS/AUDITS/20261016-internal-external-basis-lifecycle-design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def ref(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['release_id']=='basis-link-lifecycle-20261016-r1' and p['generation']==82
release_path=R/p['manifest_path'];m=read(release_path);v=read(D/'verification-binding.json');f=read(D/'freeze.json');cm=read(R/f['candidate']['manifest_path'])
assert sha(release_path)==p['release_manifest_sha256'] and m['files']==v['serving_files'] and len(m['files'])==370
assert all(sha(R/m['code_root']/n)==h for n,h in m['files'].items())
assert all(sha(R/x['target_path'])==sha(R/f['code_root']/x['target_path']) for x in cm['files'])
a=read(A/'artifacts/active-consumer.json');w=read(A/'artifacts/working-consumer.json');c=read(A/'artifacts/candidate-consumer.json')
assert not a['app_injected'] and all(x['status']=='PASS' and len(x['checks'])==10 and all(x['checks'].values()) for x in (a,w,c))
binding=a['health']['body']['release'];assert binding['release_id']==p['release_id'] and binding['generation']==82
assert '214 passed' in (A/'artifacts/working-api.log').read_text() and '213 passed, 1 deselected' in (A/'artifacts/candidate-api.log').read_text()
result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
receipt={'status':'PASS','active_pointer':p,'release':ref(release_path),'candidate':f['candidate'],'serving_files':370,'registered_files':711,'all_working_registered_files_match':True,'candidate_tests':213,'working_tests':214,'candidate_working_active_service_checks_each':10,'actual_service_entry':a['service_entry'],'actual_service_entry_sha256':a['service_sha256'],'actual_service_release_binding':binding,'data_manifest_sha256':a['data_manifest_sha256'],'search_selection_fingerprint':a['search_selection_fingerprint'],'verified_candidate':ref(D/'verification-binding.json'),'qualification':ref(A/'artifacts/run-001/result.json'),'merge_selection':ref(D/'merge-selection.json'),'working_api':ref(A/'artifacts/working-api.log'),'active_consumer':ref(A/'artifacts/active-consumer.json'),'working_consumer':ref(A/'artifacts/working-consumer.json'),'apply_log':ref(A/'artifacts/main-apply.log'),'real_model_calls':0,'quality_certified':False,'genos_deployed':False,'dataiku_recipe_updated_onsite':False,'real_oracle_verified':False,'git_commit_or_push_performed':False,'resident_local_services_restarted':False,'limitations':result['limitations']+['Global ADR graph retains9unrelated historical errors; current853final validation passes.'],'working_backups':['04_EXPERIMENTS/ADR/ADR-0851-basis-lifecycle-qualification/artifacts/working-before.tar.gz','04_EXPERIMENTS/ADR/ADR-0850-minimal-output-qualification/artifacts/working-before.tar.gz','04_EXPERIMENTS/ADR/ADR-0853-basis-wire-integration/artifacts/working-before.tar.gz'],'rollback':'Only while pointer remains this exact82release: .venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main. Previous release is MAIN81. Preserve authority history; do not force new workflow journals into old schemas.'}
put(A/'MAIN_RESULT.json',receipt);put(O/'IMPLEMENTATION_RESULT.json',receipt)
report='''공용 근거 관계 원장 구현 결과
2026-10-16 / 로컬 MAIN82 / basis-link-lifecycle-20261016-r1

완료 범위
세 기능을 하나의 관계 원장으로 구현하고 기존 작업 코드에 통합했다.
검증 후보 → 동일 작업 코드 검사 → 해시 고정 릴리스 승격 → 선택 포인터82 → 실제 service.application의 새 프로세스 진입점 확인까지 완료했다.
전체 MAIN의 원문 입력·구조화·용어집·색인 단계는 유지했다. 원문 데이터 세대는 바꾸지 않았다.

1. 질의 중 발견한 관계의 승인·재사용
일반 RAG의 실제 양측 인용, 대사의 원문 대응 및 전체 조사 결과를 PROPOSED 후보로 저장한다.
사용자가 원문/판본을 검토하고 승인하면 다음 질문에서 현재 근거·이행 관계의 외규 위치를 기존 원문 도구로 우선 직접 읽는다.
승인자·이유·원문·판본·revision·receipt를 보존한다. 수정·반려·승인 취소와 중복 요청/오래된 행 충돌을 처리한다.
내용 대응만 확인한 대사 관계는 RELATED(참고)다. 근거임을 자동 확정하지 않으며 사용자가 종류·이유를 고쳐 승인할 수 있다.
RELATED와 역사적 유래 승인은 현재 근거 우선 읽기로 자동 확대하지 않는다.

2. 내규 전체 조사
internal_basis_discovery_workflow 1.0.0을 기존 Runtime/Registry/API에 등록했다.
문서의 전체 구조와 원문 블록 목록을 기준으로 승인 관계·새 후보·읽었으나 미확보·미처리를 표시한다.
원문을 읽은 receipt와 조문별 진행을 저장하며 중단 재개/예산 소진 후 명시적인 후속 실행을 지원한다.
외규 조사 권한을 선택 내규 한 문서로 잘못 제한하지 않는다. 승인·취소는 다음 조회부터 반영한다.

3. 개정 후 위치 갱신
원문·구조 문맥이 유일하게 같은 이동은 위치만 current로 갱신하고 과거 승인을 유지한다.
내용 변경·분할·통합은 review_needed, 대응 불명은 unresolved로 보존한다. 일반 질의와 대사는 계속 조사한다.
구·신 판본/계열/원문 hash가 확인되어야 이행한다. 법제처 신구법 보조 자료도 실제 판본과 결속한다.
기존 document_release.activate 및 Oracle 게시 함수에 prepare/verify hook을 연결했다.

검토 화면과 API
새 릴리스를 읽는 로컬 서비스의 /basis/에서 내규 선택 → 전체 조사 → 원문 확인 → 행 선택 승인/반려/취소를 수행한다.
활성 AD에서는 '근거 관계 목록' 후 '1번 승인' 같은 명시 명령을 처리한다.
상세 계약/GENOS 조립 조건/개정 배치/실패 재개/롤백은 아래 운영 안내에 기록했다.
07_DOCS/REFERENCE/OPERATIONS/BASIS_LINK_LIFECYCLE_20261016.txt

실제 검증
후보213개와 최종 작업 코드214개 검사 통과. 후보에서 작업 폴더의 편집기를 읽던 구 검사는 정확한 후보 경로 검사로 대체했고, 작업 코드에서는 둘 다 통과했다.
후보·작업·선택 릴리스 각각 실제 데이터/서비스10개 검사 통과: 후보 저장, 승인, 다음 요청 목표, 정확 원문 읽기, 허용 모델 scope, 취소 반영 등.
동시 개발된 완료 ADR0850의 최소 모델 출력 기능도 보존·통합해 함께 검사했다.
711개 등록 파일의 작업/검증 후보 동일성,370개 서빙 파일의 후보/선택 릴리스 동일성을 확인했다.
원문 세대: 01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation.
실제 실행 코드·프로필·검색 선택·데이터 지문과 서비스 binding은 IMPLEMENTATION_RESULT.json에 연결했다.

실패 기록
초기 전체 조사 허용 workflow ID 누락, 보고 스크립트의 종속 hash 판정 오류, 편집기 asyncio 지역변수로 인한 기존 AD 진입 오류를 별도 ADR에 보존하고 후속 수정·검증했다.
후보 전체로 작업 폴더를 덮어쓰지 않았다. 동시 완료된 수정은 정확한 부모와 파일 선택을 기록해 병합했다.
전역 ADR graph에는 이번 작업과 무관한 기존 오류9개가 남아 있다. 최종 ADR0853 validate --final은 통과했다.

현장 미완료와 검증 한계
GENOS에 접근할 수 없어 현장 코드 반입/배포, 실제 Oracle 연결·테이블 매핑·인증 주체, Dataiku 실제 레시피 주입은 수행하지 않았다.
OracleRepository와 명시적 connection/source/table factory, 기존 게시 hook은 구현했다. 현장에서는 승인된 인터페이스를 연결해야 하며 SQLite로 자동 대체하지 않는다.
현장 워크플로우 Python 편집기에는 갱신된 genos_rag_chat.py를 별도로 반영해야 한다. 현장 확인은 워크플로우 테스트 화면에서 수행한다.
실제 외부 Qwen/GENOS 내부 모델 호출0. 모델 테스트 더블을 사용한 기술 검증이며 법률 의미 판단 정확도나 현장 성능 인증은 아니다.
기술 검사는 격리된 원장에서 수행했으며 사용자의 운영 원장에 임의 승인 관계를 넣지 않았다.
기존 로컬 상주 프로세스는 재시작하지 않았다. 새 프로세스의 실제 서비스 선택을 확인했으므로 기존 실행 프로세스는 새 릴리스를 읽도록 다시 시작해야 한다.
Git commit/push와 GENOS 리비전 배포는 하지 않았다.

롤백
현재 선택이 이 MAIN82와 일치할 때 stable rag_main_promotion.py rollback --confirm-main으로 MAIN81로 복귀한다.
후속 승격 뒤에는 이 명령을 무조건 재사용하지 말고 현재 포인터·대상부터 확인한다.
원장·승인·원문 이력은 보존한다. 코드 롤백을 데이터 삭제나 새 워크플로우 journal의 구버전 강제 재개로 처리하지 않는다.
'''
(O/'IMPLEMENTATION.txt').write_text(report)
print('MAIN82 selected service verified;370serving files,711working files,214tests,10active service checks')
