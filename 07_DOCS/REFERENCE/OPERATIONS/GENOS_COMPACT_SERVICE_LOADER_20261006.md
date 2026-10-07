# compact generation의 GENOS 서비스 진입점 연결

2026-10-06 사용자 사진에서 `/app/src/service/service.py`의 adapter가 루트 구현을 호출하고,
루트 `_explicit_generation`이 `GENOS_GENERATION has an unsupported manifest`를 발생시켜
`runtime.bootstrap.failed`, HTTP 503으로 종료했다. 선택된 경로의 manifest 원문·배포 커밋과
리비전은 사진에 없으므로 현장 로그 오류만으로 데이터 해시 손상 여부를 판정하지 않는다.

앞선 발행 사진은 `financial-risk-success-20261005-schema-r2`의 `OFFLINE_READY`,
NFS 발행 완료와 `REBUILD_EXIT=0`을 보여 준다. `ACTIVATED=False`,
`LIVE_WORKFLOW_E2E=NOT_RUN`도 함께 기록돼 있으며 서빙 성공을 뜻하지 않는다.

반입 reference R1의 서비스는 source v1만 허용하고 PeCab 사전 검사도 조 단위 fulltext v2만
허용했다. 반면 그 반입본의 `storage.Store`, `fulltext.open_index`, `verify_assets`와 오프라인
E2E는 compact source v2와 최소 단위 fulltext를 지원한다. 데이터 생성·검증과 서비스
bootstrap 사이의 허용 스키마 불일치가 직접 연결 누락이다.

수정은 루트 서비스의 두 허용 목록에 source v2와 unit fulltext v1을 추가한다. legacy source
v1·조 단위 fulltext v2·PeCab 1.0.8 검사는 유지한다. 해시/SQLite/세대/권한 검증을 생략하지
않으며 데이터·소비자 계약을 새로 바꾸지 않는다. 플랫폼 adapter는 같은 root runtime을
계속 읽는다. 신규 모델 실험이나 품질 비교가 아닌 서비스 계약 오류 수정이다.

[현장 실행·검증·배포·원복 안내](../../../08_DEPLOYMENT/GENOS/handoffs/compact_loader_20261006_r1/GUIDE_UTF8.txt),
[검증 기록](../../../08_DEPLOYMENT/GENOS/handoffs/compact_loader_20261006_r1/VALIDATION.json).
기존 `~/DEV`에 서비스 패치를 적용·커밋하고 새 패치의 결속 gate를 통과한 commit을 push한다.
같은 generation을 설정한 새 코드서빙 리비전을 배포하고 워크플로우 테스트 화면에서 warmup과
실제 질문을 확인한다. 워크플로우 Python 변경·재구축·CURRENT 변경은 이 수정에 필요 없다.

현장 반입 바이트를 재현한 WSL 격리 환경의 38개 검사가 통과했다. 모의 source/glossary/model로
실제 서비스 bootstrap·검색과 v6 질문·정정·경험 재사용을 확인했다. root 서비스 원문 변조 거부,
알 수 없는 스키마·tokenizer 거부, 실제 TXT 재실행·의존성 변경 보존·롤백·Git commit 이후
`GENOS_RELEASE_GATE PASS`와 `VERIFY_ASSETS PASS`를 확인했다. 새 코드 ZIP은 reference R1의
기존 서비스 바이트에서 두 검사만 수정한 파일과 동일한 백업 installer를 포함하며 나머지 809개
의존성을 정본 manifest의 해시로 고정한다. 로컬의 후속 SQL AD 코드를 현장에 덮어쓰지 않는다.

현재 작업 저장소에는 reference R1과 다른 full_glossary.py가 있어 전체 저장소 검사와 반입본
검증을 구분했다. WSL Python 3.14.4에서 실행했고 반입 소스·TXT 내 Python을 3.11 문법으로
검사한다. GENOS 실제 코드 적용·현장 Python·배포 commit/리비전·내부 모델 답변과 현장
generation manifest 해시는 아직 미확인이다. rollback은 원래 서비스와 이전 검증된 서빙
리비전/generation 쌍으로 돌아가며 새 데이터·로그를 보존한다.
