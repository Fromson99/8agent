# GENOS 두 번째 질문 준비 지연 진단 — latency-20260928-r1

2026-09-28 사용자 제공 현장 사진에서 캐시 적중 상태에도 ask.started부터
rag.started까지 약 23.4초, rag.plan 2.884초, session.open.ready 9.646초,
그 안의 session.sources 6.124초를 관찰했다. 사진의 마지막은 세션 준비 완료이며
이후 모델 생성 지연은 이 사진으로 판단하지 않는다. 실제 현장 배포 커밋·세대는 미확인이다.

## 변경 및 실행 경로

`service.py` → `/v1/rag/ask` → `Pipeline.run/plan` → `open_session` →
`workflow_tiers_tools.TiersTools` → `ExplorationTools/SourceSession`의 기존 경로에
INFO 진단 로그를 추가했다. 모델·검색·문서 범위·검증 기준·기존 캐시 정책은 유지한다.
데이터 재구축이나 워크플로우 Python 교체는 이번 패치에 필요하지 않다.
새 코드서빙 리비전 적용은 필요하다. 이 진단 패치는 속도 개선 완료를 의미하지 않는다.

| 로그 | 구분하는 처리 |
|---|---|
| `ask.team_validate` | ask.started 이전 API 팀 입력 검증/문서 조회 |
| `rag.prepare.started` | run 진입, 진단 버전 `latency-20260928-r1` 확인 |
| `rag.runner_import`, `rag.runner_init` | 모듈 적재와 실행기 생성 |
| `rag.team_plan` | rag.started 이전 팀 범위 계획 전체 |
| `plan.document_ids`, `plan.scope_documents`, `plan.document_roles.load/cached` | 문서 ID·분류·범위 선택 |
| `plan.team_documents`, `team.metadata_scan` | 팀 메타데이터 DB 순회·JSON 해석 |
| `plan.query_validate`, `rag.request_validate` | Query·Request 스키마 검증 |
| `sources.reader/navigator/sqlite_callbacks` | 원문 읽기 도구와 SQLite 콜백 준비 |
| `sources.folders`, `sources.root_handle` | 폴더 구성 및 요청별 root 핸들 DB 저장 |
| `sources.structure_validate`, `sources.structure_ready` | 전체 구조 순회·부모/순환/span 검사, 전체/검사 마디 수 |
| `sources.relation_cards`, `sources.lexical_schema/cached` | 관계 도구 및 용어 스키마 확인 |

기존 `session.store/context/journal/sources/gateway`, `rag.loop.started`와 함께 읽는다.
진단에는 질문·원문·팀명·키를 추가하지 않는다. 기존 공유 보고서의 원문 기록 정책은
변경하지 않으므로 원본 로그의 외부 전송 승인을 의미하지 않는다.

## 시간값 읽는 방법

- `duration_ms`: 기존 step 시작부터 완료 이벤트 직전까지. 시작 로그 출력 시간을 포함한다.
- `work_ms`: 시작 로그 출력이 끝난 뒤부터 실제 블록 종료까지.
- `thread_cpu_ms`: 그 블록을 실행한 스레드의 CPU 시간. 다른 스레드 CPU는 제외한다.
- `start_log_ms`: 시작 이벤트 출력 호출에 든 시간.
- `previous_log_ms`: 같은 요청·run·스레드에서 바로 앞 이벤트의 출력 호출 시간.
  `previous_event/previous_step`으로 어떤 로그였는지 확인한다. 현재 행의 출력 시간은 다음 행에 나타난다.
  포맷팅·핸들러 잠금·컨테이너 출력·공유 파일 write/flush를 포함하며 NFS만의 측정값은 아니다.
- `elapsed_ms`, request/run/worker 식별자를 기존 공유 `.log`에도 표시한다.

중첩 step 시간은 겹치므로 더하지 않는다. `work_ms`와 `thread_cpu_ms`가 함께 크면
해당 계산/검증 구간을 우선 확인한다. work만 크면 I/O·잠금·스케줄링 대기 등을
의심할 수 있지만 NFS라고 단정할 수 없다. 로그 시간만 크면 로그 출력 경로를 조사한다.
블록 내부의 하위 로그 비용은 상위 work 시간에 포함된다. 개별 문서마다 로그를 쓰지 않는다.

## 반입·실행·재개

첨부 ZIP과 `_APPLY.txt`를 같은 폴더에 두고 `bash GENOS_LATENCY_20260928_R1_APPLY.txt`.
기본 대상은 기존 `~/DEV`이며 `DEPLOY_ROOT`로 명시 변경할 수 있다.
TXT는 첫 단계에서 TMPDIR 또는 /tmp에 지속 실행 로그를 열고 EXIT에 상태를 기록한다.
패키지 SHA-256 확인 → 임시 해제 → 기존 checkout 파일 해시 확인 → 백업 → 적용 →
엔진 파일 해시와 PIPELINE manifest pin 갱신 → 재검증 순이다.
여덟 실행 파일은 포함된 base 해시와 정확히 같거나 이미 패치된 해시여야 한다.
다른 판이면 `unsupported installed version`으로 변경 전에 중단한다.
관련 없는 코드·스키마 불일치도 자동 승인하지 않는다.

백업은 `~/DEV/TRANSFER/latency-20260928-r1/backup-*`에 저장된다.
같은 TXT 재실행은 이미 적용된 파일을 확인하며 `ALREADY_APPLIED`를 표시한다.
쓰기 오류 시 백업으로 복구하고 실패로 종료한다. 강제 종료 후에는 같은 TXT를
재실행하거나 출력된 백업으로 원복한다. 원복 전 이후 사용자 변경 여부를 확인한다.

적용 성공 뒤 변경된 실행 파일·엔진 manifest·PIPELINE.json만 검토해 Git commit한다.
검증 실행은 다음과 같다(실제 선택 경로를 지정해야 하며 최신 폴더를 추측하지 않는다).

```bash
MODE=verify GENOS_GENERATION=/실제/선택된/generation bash GENOS_LATENCY_20260928_R1_APPLY.txt
```

이 모드는 대상 Git checkout이 clean인지 확인하고 적용 과정에서 생성한
`TRANSFER/latency-20260928-r1/applied-code.zip`의 전체 해시와 해당 commit을 대조한다.
그 checkout의 `genos_generation_e2e.py`와 `verify_assets`를 동일 Python으로 실행한다.
NFS 전체 검증에는 시간이 걸릴 수 있다. 세대 ID·절대경로·manifest SHA와 commit을 기록한다.
검증 후 코드가 바뀌면 새 commit으로 다시 실행해야 한다.
검증한 commit을 push하고 같은 commit/GENOS_GENERATION으로 코드서빙 새 리비전을 배포한다.
Git push·서빙 리비전 배포·워크플로우 성공은 각각 별도 확인 상태다.

## 현장 진단

1. 워크플로우 테스트 화면에서 첫 질문과 두 번째 질문을 실행한다.
2. 기존 공유 요청 `.log`에서 `diagnostic_revision=latency-20260928-r1`을 확인한다.
3. 두 요청의 worker_id, 캐시 적중 여부와 위 구간을 비교한다.
4. 선택적으로 `MODE=summary LOG_FILE=/해당/요청.log bash ..._APPLY.txt`로
   내용 대신 단계·시간·개수·식별자만 출력한다. 원본 로그는 현장에 보존한다.
5. 패치 ZIP SHA, 적용 영수증, 검증 commit, generation 경로/manifest SHA,
   실제 코드서빙 리비전과 해당 요청 ID를 함께 보존한다.

새 컨테이너 로그에 진단 버전이 없으면 코드 ZIP 적용과 별개로 실제 선택 리비전을 확인한다.
코드서빙 직접 테스트 UI/API 실행은 요구하지 않는다.

## 원복

```bash
MODE=rollback ROLLBACK_FROM=/home/사용자/DEV/TRANSFER/latency-20260928-r1/backup-실제값 bash GENOS_LATENCY_20260928_R1_APPLY.txt
```

백업 코드와 엔진/pipeline pin을 함께 복원한다. 원복 파일에 이후 다른 수정이 있으면
덮어쓰지 않고 중단한다. 원복 코드는 별도 commit·push·리비전 배포가 필요하다.
이미 배포한 서비스는 이전 검증 리비전과 같은 generation으로 돌릴 수도 있다.
데이터 generation과 CURRENT는 이 패치가 변경하지 않는다.

## 로컬 검증과 미확인

로깅 시간 분리·예외 전파·공유 로그 필드·팀 범위·v5 회귀 100개 통과.
적용·재적용·원복·해시 불일치 거부·중도 쓰기 실패 복구·사용자 후속 변경 보존 8개 통과.
이는 로컬 합성 계약 검사이며 실제 현장 지연 원인·성능·GENOS 반입·배포는 미확인이다.

## 2026-09-28 사용자 현장 사진의 진단 로그 확인

사용자 제공 사진 3장(`6BE74A0D-3743-44C4-97F6-CE531579A32C`)에서
`diagnostic_revision=latency-20260928-r1`과 동일 request/run의 준비 로그를 확인했다.
실행 환경은 GENOS 코드서빙 요청의 Jupyter 터미널 로그이며, 선택 commit·generation
절대경로·manifest SHA·서빙 리비전은 사진에 없어 미확인이다.

사진에서 팀 메타데이터 조회는 API의 `ask.team_validate`와 Pipeline의
`rag.team_plan/plan.team_documents`에서 각각 발생한다. 두 조회 모두 문서 2,105건을
순회하며, `team.metadata_scan` 시간은 각각 약 7.4초와 10.5초로 읽힌다.
후자의 CPU 시간도 약 9.8초여서 이 구간의 계산 비용이 크다.
작업 코드의 `team_scope.document_teams`는 `SELECT document_id,json FROM document`의
전체 JSON을 Python에서 해석하며 요청 간 재사용을 하지 않는다.

`sources.structure_validate`는 전체 약 35만 마디를 순회하고 선택 문서 1,003건의
약 21만 마디에 대해 부모 경로·span을 다시 확인한다. 사진상 약 3.2초다.
작업 코드의 scope는 list여서 매 마디에 대한 범위 포함 여부 확인도 선형 검색이다.
`rag.loop.started.elapsed_ms=18170`은 Pipeline.run 진입 후 약 18.17초이며,
그 전에 실행한 API 팀 검증 시간은 포함하지 않는다. 사진 시각상 runtime 요청부터
루프 진입까지는 약 26초다. 모델 호출 이후 시간은 이 사진으로 판단하지 않는다.

`runtime.cache.hit`, `tools.cache.hit`, 용어집 파일 캐시 로그는 확인되지만 위 두
요청별 작업은 그 캐시에 포함되지 않는다. 앞 이벤트 로그 출력은 대체로 수십 ms로
보여 추가 비용은 있으나 큰 조회/구조 검사 구간을 로그 출력만으로 설명할 수 없다.
대기 시간만으로 NFS 병목을 확정하지 않는다.

후속 수정 방향은 검증된 불변 세대에 결속한 팀 매핑의 재사용, 같은 요청의 팀
선택 중복 제거, 구조 검사에서 scope set 사용 및 검증 결과 재사용이다.
세대 변경·팀 범위·부모 누락/순환 검증을 보존해야 한다. 이 절은 관찰과 원인 분석
기록이며 위 개선의 구현·현장 성능 검증·추가 패치 발송을 의미하지 않는다.

## 추가 현장 기록: 동일 요청의 준비 지연 약 154초

2026-09-28 추가 사용자 사진 `CA0FEF42-51C0-49DD-97BE-88EE2D5996C1` 및
`5C74AB08-52A9-4AEF-BD2C-1DC161518482`는 같은 request/run의 연속 로그다.
runtime 요청 시작 23:58:16 UTC부터 session.open.ready 약 00:00:50 UTC까지
약 154초가 걸렸다. 세션 준비 완료 이후 실제 모델 응답 시간은 포함하지 않는다.

- API 팀 metadata scan: 앞 사진상 약 34.5초(work), 스레드 CPU 약 10.3초.
- 팀 계획의 문서 ID 조회: work_ms=23420.012, thread_cpu_ms=63.881.
- 두 번째 팀 metadata scan: duration_ms=43006, work_ms=42904.438,
  thread_cpu_ms=9812.987. 앞 사진에서 진행 중이던 조회의 완료 로그다.
- rag.plan의 문서 ID 재조회: duration_ms=29097, work_ms=28779.313,
  thread_cpu_ms=69.302. 같은 `SELECT document_id FROM document`를 재실행한다.
- 출처 구조 검사: duration_ms=7464, work_ms=7396.496,
  thread_cpu_ms=3130.603. 전체 약 35만 마디 중 약 21만 마디를 검사한다.
- 세션 준비 전체는 약 18초이며 위 구조 검사·리소스·journal·로그 시간이 포함된다.
  중첩 단계의 숫자를 더하지 않는다.

문서 ID 조회 두 번의 CPU 합은 약 0.13초인데 실제 work 합은 약 52.2초다.
계산 비용만으로 설명할 수 없는 SQLite 조회/순회 또는 스케줄링 대기가 확인된다.
이 로그만으로 NFS I/O, SQLite 연결 잠금, 컨테이너 자원 대기를 구별할 수 없다.
기본 runtime·도구·용어집 캐시는 계속 적중했다.

앞 이벤트 출력은 다수 행에서 약 100~300ms로 읽히며, context 같은 일부 작은
단계는 실제 work보다 시작 로그 출력 시간이 대부분이다. 진단 INFO 로그도 동기
포맷팅·핸들러 잠금·컨테이너 출력·공유 write/flush 비용을 더한다.
다만 문서 ID 조회의 work 블록 내부에는 로그 호출이 없어 그 52초를 해당 step의
시작 로그 비용으로 돌릴 수 없다. 각 대기 원인과 로그 출력 경로는 별도 진단 대상이다.

후속 개선 범위에는 팀 정보뿐 아니라 세대 결속 문서 ID 목록의 재사용과 중복
계획 실행 제거를 포함해야 한다. 구조 검사의 scope set 전환과 동기 로그 비용
완화도 필요하며 검증·오류 기록·요청 격리를 보존해야 한다. 이 추가 기록 역시
분석만 반영한 상태로 성능 수정·새 패치 발송·현장 재검증은 아직 하지 않았다.
