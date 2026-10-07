# GENOS 요청 준비 반복 비용 수정 — 2026-09-29 R1

캐시 적중 후에도 반복하는 요청 원장 초기화와 출처/약칭 projection 파일 읽기를 줄였다. 이전 FULLTEXT 수정은 준비 완료 후의 검색 위치 구성 비용을 줄였으므로 이번 수정과 측정 구간이 다르다.

## 확인된 코드 경로와 변경

`ServingLegalAgent._open_session` → source resources → `WorkRepository.__init__` → 요청별 sources/session 구성이다. 원장은 요청마다 새 SQLite 파일을 만든다. 기존 초기화는 autocommit 연결에서 버전별 SQL의 표·색인·트리거를 각각 실행했다. 초기 캐시를 로딩해도 이 쓰기 경로는 매 요청 반복했다.

- 연결 PRAGMA 설정 후 `BEGIN IMMEDIATE`를 열고 스키마·user_version·seed·run/budget를 함께 한 번 commit한다. DDL 파일/버전, `synchronous=FULL`, `journal_mode=DELETE`, 외래키, 원장/연결 분리를 유지한다. 실패 시 스키마와 버전도 rollback한다.
- `folder_navigation.load_origin_projection`와 `document_aliases.load`는 기존 `_verified_json`을 재사용한다. 파일 stat proof/해시/세대 바인딩을 검증하고 반환본을 복사하므로 요청별 수정이 캐시를 오염시키지 않는다.
- PIPELINE 해시 증명은 기존 `cached_code_sha`를 재사용하며 변경된 파일 상태는 다시 검증한다.
- `session.prepare.timings`를 READY/FAILED에 한 번 기록한다. PID, 총 wall/CPU, store/resources/context/journal/sources/gateway 각각의 wall/CPU를 남긴다. 준비 완료 뒤의 검색과 LLM 실행은 제외한다. 전체 준비와 그 안의 단계 시간을 더하지 않는다.

원장 쓰기는 여전히 존재하므로 디스크/NFS 지연을 배제하지 않는다. wall과 thread CPU의 차이에는 I/O, 락, 스케줄링 등 여러 대기가 포함된다. 최초 캐시 로딩, 다른 worker/PID의 캐시 로딩, 검색/LLM 지연을 해결했다고 주장하지 않는다. 내부 데이터에서 준비 시간이 얼마나 감소했는지는 미측정이다.

## 계약 확인과 적용 상태

v1~v5의 SQLite trace로 모든 초기 DDL/seed/request 쓰기가 한 트랜잭션 안에 있음을 확인했다. 기존 DDL로 만든 reference DB와 `sqlite_master`가 같고, FULL/FK/DELETE 설정과 재열기 바인딩이 유지된다. 실패 rollback, warm projection 1회 읽기, 변조/세대 불일치 거부, 별도 요청 원장, 정상/실패 준비 이벤트와 실제 보고 capture를 검사했다.

확장 검사 222개 중 220개 통과, 2개는 수정 전 원장 코드에서도 동일하게 실패했다: `test_trailing_parenthetical_context_stays_with_the_question`, `test_initial_source_trigger_aliases_matching_unassessed_question_issue`. 기존 질문 분할/쟁점 병합 동작이며 이번 변경 범위에서 수정하지 않았다. 별도 요청 준비/현장 인계 검사는 validation receipt에 기록한다.

4개 작업 코드와 소비하는 엔진 manifest 26개, PIPELINE 코드 pin에 반영했다. preimage는 `90_RUNTIME/diagnostics/request-prepare-20260929-preimage`에 보존했다. Git main 병합, frozen local MAIN 승격, 현장 checkout 적용/commit/push, GENOS 리비전 배포와 워크플로우 현장 확인은 별도이며 이 기록만으로 완료가 아니다.

새 색인/SQL 저장 구조 변경은 이번 패치와 별개다. 이번 패치는 generation/CURRENT/색인 manifest/data pin을 변경하지 않는다.

## 현장 파일

`08_DEPLOYMENT/GENOS/patches/GENOS_REQUEST_PREPARE_20260929_R1.zip`, 같은 접두사의 `_APPLY.txt`, `_CAPTURE.txt`, `_NOTES.txt`, `_SHA256SUMS.txt`를 사용한다. 적용 TXT에 ZIP을 포함하여 코드스페이스의 기존 `~/DEV`에서 바로 실행한다. 승인된 4개 함수만 교체하고 다른 현장 함수/추가 코드/프로필을 보존한다. 기존 코드/스키마 pin, 필요한 검증 캐시 함수를 적용 전 확인하며 알 수 없는 구현은 쓰기 전에 거부한다. 이전 RESPONSE_OVERHEAD R3가 전제다.

`MODE=check`는 적용 전 확인, 기본 실행은 백업 후 적용, `MODE=rollback ROLLBACK_FROM=...`은 변경 후 해시를 확인하여 복원한다. 첫 단계부터 지속 로그와 종료 상태를 남긴다. 배포 전 실제 checkout에서 commit 후 `MODE=verify GENOS_GENERATION=/실제/선택된/generation`으로 코드 ZIP/커밋/세대 게이트를 확인한다. 통과한 커밋 push와 새 리비전 선택, 워크플로우 테스트는 별도다.

준비 수치 캡처는 완료된 워크플로우 보고 JSON의 경로를 `REPORT_JSON`으로 지정해 `_CAPTURE.txt`를 실행한다. `service_events`에서 준비 요약 최대 3개만 보여 주며 질문/본문/LLM 답변을 출력하지 않는다. 이벤트가 없으면 성공으로 처리하지 않는다.
