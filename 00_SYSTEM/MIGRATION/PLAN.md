# v1 → v2 이행 실행계획

이 계획의 핵심은 “폴더 이동”이 아니라 “정본 포인터 전환”이다. 각
단계는 다음 단계를 자동으로 활성화하지 않고 별도 영수증을 남긴다.

## Phase 1 — bridge (활성 상태)

완료된 계약:

- 12개 `NN_UPPERCASE` canonical root와 논리 path resolver
- receipt 없는 `LAWRAG_LAYOUT_VERSION=v2` 활성화 차단
- 외부·GENOS 내부 동형 `DatasetPackage` 및 다중 `SourceSet`
- 충돌·real/mock 혼용·restricted 반출 fail-closed
- 세대·landing ACL·evidence를 잠근 append-only `QueryShortcut`
- code/MAIN/SourceSet/semantic/index를 묶는 `ReleaseManifest`
- 영수증·CAS 기대값·롤백 대상을 묶는 `ReleaseActivationPlan`
- GENOS code ZIP의 `00_SYSTEM` 포함, research/data/runtime 경계 차단

아직 활성화하지 않은 것:

- v2 물리 경로
- 다중 SourceSet RAG runtime adapter
- 피드백 shortcut runtime adapter
- Legal Graph canonical semantic 승격 수정
- `ACTIVE_RELEASE` 파일 쓰기

현재 물리 진행은 Phase 2의 주요 제품 경로 전환과 Phase 3의 shadow copy,
dual-read, 12개 root final-verify까지 완료했다. 최종 검증 정본은
`20260903-workspace-partition-final-v5.final-verify.json`이며 287개 항목과
12/12 root binding을 담는다. 다만 activation receipt를 발행·설정하지 않았으므로
런타임 권위는 계속 v1이고 `LAWRAG_LAYOUT_VERSION=v2`는 fail-closed 상태다.

## Phase 2 — reference cutover preparation

1. `Path(__file__).parents`, `data/`, `var/`, `docs/adr`, `scripts.*` 의존을 도메인
   Settings·Store API로 교체한다.
2. legacy `active-dataset-overlay-v1`을 package/source-set으로 변환하는
   일회성 adapter를 만들고 양쪽 receipt가 같은 물리 artifact hash를
   가리키는지 확인한다.
3. 이 단계에서는 새 경로를 읽지 않고, 모든 consumer가 중앙 resolver를
   통하는지만 검증한다.

게이트: 제품·도구·테스트의 하드코딩 경로가 inventory에 등록되고,
새 resolver 뒤로 바꾸어도 v1 기본값은 같아야 한다.

## Phase 3 — copy-verify-0 (shadow publication)

1. `ROOT_CLASSIFICATION.json`과 root mapping 순서대로 새 위치에 복사한다.
2. 파일은 SHA-256, 디렉터리는 경로+크기+내용 Merkle hash로 검증한다.
3. 원본과 새 경로를 모두 읽어 구조 row·의미 row·인덱스 카운트·
   최상위 회수·ACL 결과를 비교한다.
4. 완료 ADR은 원본 path/hash를 건드리지 않고 ID resolver에 legacy 위치를
   등록한다.
5. 디렉터리 게시는 폴백이 부분 target을 노출할 수 있으므로, 모든
   consumer가 `readiness receipt + live fingerprint`를 통한 검증 open을 사용한다.
   incomplete marker·special file·ancestor symlink가 있으면 즉시 거부한다.

이 단계가 dual-read보다 먼저다. 비교할 v2 bytes가 없는 상태에서
dual-read를 켜지 않는다. 영수증이 있어도 live bytes가 달라지면 ready가 아니다.

게이트: source·target live hash 일치, incomplete publication 0건, 복사 영수증,
원본 byte 변경·삭제 0건. 이 단계는 아직 v2를 활성화하지 않는다.

2026-09-03 결과: direct-child partition 4개(`data`, `docs`, `frontend`,
`experiments`), whole-root 7개, already-canonical 1개로 게이트를 통과했다.
중첩 root는 `delegated_sources`, frontend 생성물은 제한된 `excluded_sources`로
기계 판독 가능하게 기록했다.

## Phase 4 — dual-read 및 SourceSet runtime

1. 검증된 v1·v2 경로를 동시에 읽고 exact artifact hash·구조 row·권한
   결과를 비교한다.
2. hit·Evidence·RuleBundle·answer trace에
   `dataset/version/build/package/source_set` provenance를 끝까지 전파한다.
3. 인덱스 builder가 source-set·semantic·model fingerprint manifest를 발행하게 한다.
4. RAG 선택기에 `UnifiedCorpusView`를 주입하되 legacy/default arm과 완전히
   격리된 candidate로 OOS 실험한다.
5. 서로 다른 dataset 사이 relation은 배선된 central relation gate의 capability
   ID·code hash·receipt가 SourceSet과 release에 고정되기 전에는 허용하지 않는다.

게이트: legacy와 dual-read가 동일 package 선택·동일 hit 근거를 내고,
내부 package가 인가된 사용자에게만 노출되며, 제품 RAG OOS 게이트를 통과한다.

## Phase 5 — activate-v2

1. `WORKSPACE.json`의 모든 root를 `active`, mode/default를 `v2-only/v2`로 바꾸는
   candidate를 만든다.
2. 그 manifest hash와 전체 검증 receipt를 `workspace-layout-activation-v1`에
   고정한다.
3. GENOS에서 `ReleaseActivationPlan`을 검증한 후 `ACTIVE_RELEASE`를
   compare-and-swap한다.
4. 서비스는 포인터 하나에서 code/MAIN/SourceSet/semantic/index를 읽는다.
5. 활성 release runtime은 조회 전용으로 seal한다. upload·feedback·apply·인덱스
   재생성은 별도 authoring/control plane에서 새 release를 만들고 재활성화한다.

게이트: 경쟁 활성화 중 하나만 성공, commit event·pointer durability 결과
일치, 재시작 후 동일 release 로드, code·MAIN·SourceSet·semantic·index의
live artifact fingerprint 일치, 변경 API 차단, 롤백 smoke 통과.

## Phase 6 — retire-v1

롤백 관찰 기간이 끝나기 전에는 legacy root를 지우지 않는다. 기간 종료 후에도
완료 ADR·원문 package·activation receipt는 삭제하지 않고 archive resolver에
영구 보존한다.
