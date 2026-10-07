# GENOS 준비·검색 지연 수정 계획

작성일: 2026-09-28. 상태: 코드와 사용자 현장 사진을 대조한 구현 계획.
현재 반영된 `latency-20260928-r1`은 진단 로그 패치다. 이 문서는 성능 수정·실험·새 패치 발송·GENOS 배포 완료를 의미하지 않는다.
대상은 전체 MAIN 중 **선택된 데이터 세대를 소비하는 GENOS RAG 서빙 경로**다.
구조화·용어집 의미 검토·원문 정본을 다시 만드는 작업은 우선 수정 범위에 포함하지 않는다.

## 1. 이번 사진의 판정과 전체 관측

이번 사진은 기존 `fulltext.sqlite`를 검색하는 `fulltext_tool.rank` 구간이다.
인덱스를 만드는 build 명령을 실행 중인 화면이 아니다. 기존 색인·SQL·저장장치의 문제 중 어디인지는 추가 구분이 필요하다.

| ID | 현장 사진에서 확인한 값 | 종류·분모·범위 | 판단 |
|---|---|---|---|
| O1 | 캐시 적중 요청에서도 API와 Pipeline이 2,105건 팀 정보를 각각 조회. 빠른 요청 약 7.4초·10.5초 | 관측, 한 요청의 서로 다른 두 조회 | 팀 매핑이 기존 리소스 캐시에 포함되지 않음 |
| O2 | 느린 요청에서 첫 팀 조회 work 약 34.5초·CPU 약 10.3초, 두 번째 work 42.904초·CPU 9.813초 | 관측, 같은 요청의 별도 조회 | 전체 문서 JSON 파싱과 대기 비용이 함께 큼 |
| O3 | 같은 요청의 문서 ID 조회 두 번: work 23.420초·28.779초, CPU 0.064초·0.069초 | 관측, `plan.document_ids` 두 호출 | 읽기/잠금/스케줄링 대기를 우선 구분해야 함 |
| O4 | 전체 약 35만 구조 마디 중 약 21만 마디 검사. 느린 요청 work 7.396초·CPU 3.131초 | 관측, `sources.structure_validate` 한 번 | 요청마다 list 포함 검사와 부모 경로 확인을 반복 |
| O5 | 요청 시작부터 세션 준비 완료까지 약 153.6초 | 관측, 23:58:16 UTC→00:00:50 UTC, 같은 request/run | 답변 모델 시간과 구분해야 함 |
| O6 | FTS 순위 검색 duration 65.043초·work 64.915초·CPU 0.304초 | 관측, 추가 사진의 `fulltext_tool.rank` 한 번 | 큰 비CPU 시간이 존재. 파일 I/O·SQLite 잠금·자원 대기 중 어디인지는 미확인 |
| O7 | rank 완료 00:02:13 UTC→다음 model.attempt.started 00:03:03 UTC, 약 50.6초 | 관측, 이벤트 사이의 공백 | 결과 구성·프리뷰·원장 commit·다음 model view 준비가 후보. 어느 하나의 시간으로 확정하지 않음 |
| O8 | 다수 previous_log_ms 약 100~300ms. 작은 단계는 work보다 시작 로그 시간이 큼 | 관측, 개별 이벤트 | 동기 INFO 로그 출력도 요청 지연을 더함 |

서로 다른 질문의 시간을 평균·p95·성능 보장으로 사용하지 않는다. 중첩 step은 합산하지 않는다.
CPU 시간이 작다는 사실만으로 NFS 병목을 확정할 수 없다.
실제 GENOS commit·선택 generation 경로/manifest SHA·리비전·컨테이너 자원 배정은 사진에 없어 미확인이다.
모델 답변의 정확성이나 생성 속도도 위 관측만으로 판정하지 않는다.

## 2. 현재 실행 경로와 유지할 계약

`service.service/_dispatch` → cached application → `/v1/rag/ask` →
`Pipeline.run/plan` → `ServingLegalAgent.open_session` → 요청별 Store·Tools·Glossary 연결 →
`Coordinator/StageRunner.retrieve` → `workflow_relations_tools.search` →
`FulltextIndex.rank` → 후보/프리뷰·원장 observation → 다음 모델 view/call → FINAL → 기존 비동기 publication/report.

다음 조건을 유지한다.

- 문서 ID·팀·문서 범위는 매 요청 서버에서 확인한다. 캐시는 불변 자료만 공유하고 질문·핸들·답변·원장·deadline은 요청별로 분리한다.
- source/navigation/fulltext/glossary의 해시·세대·PeCab 버전과 원문 span 검사, 부모 누락/순환 거부를 보존한다.
- FTS의 OR 형태소·BM25 가중치·source ID 동점 순서·범위·정확한 total·페이지/next_cursor를 유지한다.
- 2026-09-27 사용자 지시로 제거한 별도 20초 FTS 중단을 재도입하지 않는다. 현재 전체 요청 deadline과 실제 오류 보고를 유지한다.
- FINAL 답변 journal의 내구 저장과 publication recovery를 유지한다. 공유 TXT/JSON 사본과 진단 로그는 원장과 구분한다.
- WARMUP과 실제 질문은 같은 준비 함수를 호출한다. 별도 질문 실행기를 늘리지 않는다.

## 3. 변경 지도와 적용 순서

### A. 반복 팀 조회·문서 ID 조회 제거 — 첫 코드 패치

대상: `team_scope.document_teams/select_documents`, `Pipeline.document_roles/plan/run`,
`app.ask`, `service._warm_resources`, `storage.Store`의 연결/세대 확인.

1. 검증한 Store에 대해 문서 ID·팀 매핑·문서 분류를 한 번 준비한 불변 catalogue로 묶는다.
   세대 절대경로, manifest digest, store SHA, dev/inode/size/mtime/ctime, catalogue 구현 버전을 키로 사용한다.
   다른 Store 인스턴스에서도 동일한 검증 세대면 재사용하되 SQLite 연결 자체는 공유하지 않는다.
2. API의 `ask.team_validate`가 전체 문서 JSON을 읽지 않도록 catalogue로 유효한 팀인지 확인한다.
   Pipeline에서도 같은 catalogue를 소비해 선택 결과를 한 번 계산한다.
3. `run`의 팀 계획과 후속 `rag.plan`에서 같은 Query를 다시 만들지 않도록 내부 준비 결과를 재사용한다.
   HTTP Request에 비공개 필드를 추가하지 않고, 기존 Query·Request 포트의 검증과 CLI 동작을 유지한다.
4. 팀 파싱은 기존 중복 문서 aliases 소속 처리와 정확히 같은 결과를 보존한다.
   필요하면 SQLite에서 metadata만 추출하되 초기 DB 순회가 사라지는 것으로 오해하지 않는다.
5. catalogue 키가 바뀌면 폐기·재검증한다. 생성 중 동시 요청은 한 번만 구축하도록 합친다.
   지원 범위 밖 팀/문서·빈 교집합은 기존처럼 거부한다.
6. 기존 WARMUP에서 catalogue도 준비하고, READY는 이 실제 준비의 완료 상태를 표시한다.
   일반 질문도 같은 함수를 이용한다. 프로세스 재시작·다른 worker의 첫 준비 비용은 별도로 기록한다.

재구축: 기존 데이터 세대 그대로 사용. 코드·엔진 pin 변경 및 새 코드서빙 리비전 필요.
완료 기준: 동일 worker·세대의 후속 요청에서 팀 정보/ID 전체 SQL 순회 0회; 팀별 결과와 기존 거부 동작 일치.

### B. 구조 검사와 검색 범위 계산의 반복 제거 — 첫 코드 패치

대상: `ExplorationTools.__init__/sources_in/ancestors`, `ReverseMatcher`의 순수 데이터 캐시,
`ServingDocumentAgent.resources`, `bind_structure`에서 선택되는 최종 구조.

- scope list는 출력용으로 보존하고 membership 검사는 별도 frozenset을 사용한다.
- document→source IDs, document→unit keys의 순수 자료를 기존 검증 세대 캐시에 연결한다.
  `sources_in`에서 모든 source와 문서 list를 반복 대조하지 않는다.
- 부모 경로·span 검증 완료 결과를 **최종 bind_structure 결과와 연결된 불변 구조**별로 보존한다.
  projection/aliases가 달라지는 경우도 키에 포함한다. matcher 객체 전체를 공유하지 않는다.
- 부모/순환 검사는 선형 상태 탐색으로 중복 방문을 줄인다. 검증에 성공한 문서만 완료로 저장한다.
  실패·중단·데이터 변화는 완료 캐시를 만들지 않는다. 요청별 팀 범위 검사와 실제 읽기 span 검사는 계속한다.
- 구조 객체의 수정·세대 바뀜이 캐시로 가려지지 않도록 상태 확인과 기존 check_sources_unchanged를 결속한다.

재구축: 데이터 변경 없음. 최초 검증 비용은 남으며 WARMUP에 연결한다.
완료 기준: 후속 요청의 전체 구조 순회 0회; 모의 부모 누락·순환·잘못된 span 및 다른 팀 원문 접근은 계속 실패.

### C. 로그 출력의 동기 대기 제거 + 비CPU 대기 구분 — 첫 코드 패치와 함께

대상: `observability.event/step`, `request_report._LiveLog/DeferredReport`,
`FulltextIndex.rank`, `workflow_relations_tools.search/execute/candidate/preview`, `WorkRepository.transaction`, model view 준비.

- 요청 스레드는 필요한 진단 이벤트를 메모리의 **크기 제한 큐**에 넣고 바로 진행한다.
  프로세스별 writer가 순서대로 공유 `.log`를 쓰고 묶어서 flush한다.
  큐는 건수/bytes를 제한하고 대기 없이 넣는다. 포화 시 낮은 우선순위 진단 항목의 누락 수를 기록하며
  오류/완료 정보는 별도 예약 용량과 컨테이너 출력으로 남긴다.
- 컨테이너 stderr 핸들러도 동기 비용 측정 대상이다. 공유 NFS 핸들러만 옮긴 뒤 모든 대기가 없어졌다고 보고하지 않는다.
- 질문·도구 원문을 새 지연 진단 항목에 추가하지 않는다. 기존 상세 보고서 정책은 유지한다.
- journal은 감사 정본이다. 이 큐로 원장 쓰기를 보내거나 성공처럼 표시하지 않는다.
  종료 전 사본 기록은 제한된 시간에 drain하며 강제 종료 시 진단 사본 누락 가능성을 표시한다.
- 준비 요청에서 catalogue/cache hit, 조회 횟수, cold 준비 시간, worker/process, 논리·물리 DB 경로를 구분한다.
- FTS는 `execute/first_row/fetch/scope_filter`, 결과 후처리는 `location_mapping/page_preview`,
  원장은 `begin/body/commit`, 다음 모델 준비는 `view_build/view_save/attempt_reserve`의 시간·CPU·개수만 남긴다.
  **행마다 로그를 쓰지 않고 구간별 누적 값 한 번만 기록한다.** 위 세부 이벤트 이름은 구현 시 추가할 제안이다.
- SQLite version, query plan 요약, 해당 파일의 mount 유형, 로컬 디스크 공간, 연결 lease 대기,
  cgroup CPU throttling·memory pressure의 전후 delta를 측정 가능한 범위에서 수집한다.
  읽을 수 없는 플랫폼 값은 미확인으로 표시한다. 일반 JSON 질문 안에 기술 설정을 노출하지 않는다.

재구축: 없음. 로그 writer·포화·종료 테스트가 필요하다.
완료 기준: 요청 스레드의 공유 로그 write/flush 0회; 큐 포화·NFS 쓰기 실패가 RAG를 막지 않고 누락 상태가 보임.

### D. 읽기 전용 SQLite의 NFS 접근 완화 — 조건부 두 번째 패치

대상: `service._bootstrap_application/_warm_resources`의 세대 선택,
`Store`, `TermIndex`와 도구 연결, `FulltextIndex.connect`, glossary lease 연결.

선행 조건: 실제 mount, SQL 대기 구간, CPU 제한과 로컬 저장장치 용량을 C에서 확인한다.
공유 SQLite 연결의 lease/잠금 대기가 원인이면 요청별 읽기 연결/전용 lease로 먼저 격리한다.
CPU throttling이면 배포 자원 배정과 warmup·다른 요청 동시 실행을 조정한다.
서빙 admission을 무거운 준비 앞에도 적용하되 기존 정책처럼 초과 요청은 즉시 상태를 반환한다.
Pipeline.run에서 얻은 요청별 lease를 open_session까지 전달하는 내부 계약을 제안한다.
기존 open_session 직접 호출도 보호하며 이중 acquire를 피하고 실패·취소 때 한 번만 release한다.

NFS 페이지 읽기 대기가 확인되면, **GENOS 컨테이너 내부의 승인된 로컬 저장소**에
해시가 같은 불변 DB 읽기 사본을 준비한다. 우선 fulltext, 이후 source/navigation/glossary를 필요별로 확장한다.
설정 이름·경로는 새 후보 설계이며 현재 코드의 기존 기능으로 설명하지 않는다.

- NFS generation이 원천이고 논리 세대/manifest/hash는 그대로 보존한다. 사본은 실행 캐시이며 CURRENT를 바꾸지 않는다.
- 임시 파일로 복사 → 전체 SHA 확인 → 복사 중 원천 상태 확인 → 원자적 rename → ready receipt 순서다.
- 여러 worker의 구축 lock, 디스크 부족·복사 실패·중간 종료·다른 세대·WAL 동반 파일을 처리한다.
  깨진 사본을 사용하지 않는다. 명시된 사본 모드가 준비되지 않으면 READY로 표시하지 않는다.
- NFS source와 사본의 상태가 바뀌면 거부·재준비하고 활성 연결을 교체한다.
  `Store.path`를 물리 사본 경로로 단순 덮어 바인딩/출처 검증이 어긋나게 하지 않는다.
- `immutable=1`은 파일 불변성이 실제 보장된 읽기 사본에 한해서 검토한다.
  변경 가능한 DB에 적용하면 잠금/변경 감지를 건너뛰므로 사용하지 않는다.
- journal은 복사 대상에서 제외한다. 권한·수명·삭제 정책을 GENOS 내부 데이터 정책에 맞춘다.

새 데이터 생성/재색인: 필요 없음. 복사 bytes와 해시 검증 시간·추가 디스크가 운영 비용이다.
원복: 사본 reader를 해제하고 검증된 기존 NFS reader로 돌아간다. 데이터/세대 원본은 보존한다.

### E. fulltext 검색의 전체 결과 처리와 반복 검색 개선 — 세 번째 패치

대상: `FulltextIndex.rank`, `workflow_relations_tools.search`, `search_receipt/next_cursor` 소비자.

현재 구현은 OR 검색·`ORDER BY rank`로 **전체 일치 행을 순회**하고 Python에서 allowed 범위를
걸러낸다. search는 limit 없이 호출하며 정확한 total을 만든다. SQL의 rank 최적화는 이미 들어가 있다.

1. 먼저 같은 SQL의 실행계획·읽은 행 수·범위 내 행 수·동점 크기와 execute/first/fetch 시간을 확인한다.
   broad OR가 비용을 키우는지와 페이지 I/O 대기를 구분한다. DB를 재구축해야 한다고 선결론 내리지 않는다.
2. 같은 요청의 동일 형태소·범위·bounds·가중치·tokenizer·index 해시에 결속한 **순수 source ID 순위/개수**를 재사용한다.
   핸들·답변·프리뷰·다른 팀 범위는 공유하지 않는다. 캐시는 bytes/항목 제한을 둔다.
   후속 cursor에서 같은 전체 순위 조회를 다시 하지 않도록 조회 상태를 재사용한다.
3. 기존 정확한 total·동점 순서·완전 탐색을 유지하는 streaming/범위 처리 개선부터 검증한다.
   임의 LIMIT로 잘라낸 뒤 `total_status=exact`라고 표시하는 변경은 하지 않는다.
4. SQL 범위 pushdown/rowid 보조 매핑은 **별도 검증 후보**다. 기존 테이블 구조에 있는 식별자로
   가능한지 먼저 확인한다. JOIN/임시 allowed table이 오히려 sorting/I/O를 늘릴 수 있으므로 자동 채택하지 않는다.
5. 인덱스 변경이 필요한 경우에만 새로운 fulltext 파생 generation으로 만든다. tokenizer/BM25의
   통계 모집단이 달라지는 팀별 별도 FTS는 순위가 변할 수 있어 동등한 최적화로 취급하지 않는다.
   바뀐 source/navigation binding·manifest·배포 receipt를 함께 검증하고 기존 generation을 보존한다.

현장 검증 전 FTS 65초→몇 초 같은 개선 수치는 미산정이다. 별도 20초 제한 제거는 그대로 유지한다.

### F. 검색 후 약 50초 공백과 원장 쓰기 개선 — C의 계측 결과로 적용

대상: `workflow_relations_tools.search/preview/candidate/execute`,
`ExplorationTools.handle/location`, `WorkRepository` 및 `RelationsRepository.transaction`, 모델 view 저장 경로.

- rank 뒤 location 목록, 반환 페이지 프리뷰, root/후보/폴더/ancestor 핸들 저장,
  observation commit, system task drain, 모델 view 구성/저장 시간을 분리한다.
- 이미 현재 코드는 프리뷰를 반환 페이지에만 만든다. 변경의 핵심은 페이지 수 제한의 재도입이 아니라
  **한 후보 프리뷰가 block마다 원문 DB를 조회하는 비용과 반복 핸들 writes**다.
- 같은 요청의 동일 canonical block 읽기를 bytes 제한 캐시로 재사용하고 일괄 조회한다. source_chars·발췌·span hash를
  기존 계산과 동일하게 유지한다. 다른 요청 핸들이나 미검증 preview를 근거로 승격하지 않는다.
- action 예산 예약/상태 기록, 후보 핸들/route 구성, observation 저장의 작은 autocommit을
  의미 단위 transaction으로 묶는다. 기존 savepoint 지원을 이용해 중첩과 복구를 유지한다.
  예산/action 예약의 내구 commit→도구 실행→결과/observation의 내구 commit 경계는 유지한다.
  예약과 결과를 하나의 지연 commit으로 합쳐 프로세스 중단 시 예약 이력을 잃게 하지 않는다.
- 모델 HTTP 요청 전에 필요한 ATTEMPT/모델 view 기록을 내구 저장한다. network/LLM 대기 동안
  transaction을 유지하지 않는다. 감사 순서·action idempotency·restart recovery를 검사한다.
- `synchronous=OFF`로 속도를 얻지 않는다. NFS journal에 WAL을 무조건 켜지 않는다.
  journal을 로컬로 옮기는 설계는 내구 복제/복구 계약이 먼저이며 첫 패치 범위 밖이다.

재구축: 없음. 원장 동작 변경은 오류·강제 종료·재개 검증이 선행 조건이다.

## 4. 도입 묶음과 검증 계획

| 묶음 | 구현 대상 | 현장 진입/종료 조건 | 데이터 변경 |
|---|---|---|---|
| 수정 R2 후보 | A·B·C + 준비 admission + F 구간 계측 | 기존 계약 일치, 세대/팀 격리, 반복 SQL/구조 순회 제거, 진단 큐 장애 처리 | 없음 |
| 수정 R3 후보 | D + F에서 원인이 확인된 transaction/일괄 읽기 | 현장 DB/mount/자원 측정, 로컬 저장소 조건, audit/recovery 검사 통과 | 같은 해시 읽기 사본만 |
| 검색 후보 | E | 결과·순위·total·cursor·범위·회귀 기준을 사전에 고정해 검증 | 필요할 때만 새 fulltext 파생 세대 |

현재 보고서 작성은 새 실험이 아니다. 성능 A/B·검색 효과 비교를 실제로 실행할 때는
저장소 실험 표준 두 문서를 끝까지 읽고 동일 scope reservation 확인 → ADR 선점 →
부모/arm·코드·데이터·질문·설정·성공/회귀 기준 동결 → 격리 비교 절차를 먼저 따른다.
실제 내부 질문/성능 실험은 GENOS에서 하고 외부에서는 동일 계약 모의 자료를 사용한다.

### 정상·실패 시나리오

| 입력/상태 | 계획한 동작 | 완료 확인 |
|---|---|---|
| 같은 worker·세대의 첫 질문 | 검증 catalogue/구조 준비; 사본 모드는 사본 준비; cold 시간 별도 표시 | READY와 선택 binding이 일치 |
| 같은 세대에서 팀만 다른 다음 질문 | catalogue 재사용, 팀별 scope 다시 계산, 새 journal/handles/SQLite lease | 다른 팀 원문·근거가 포함되지 않음 |
| 허용되지 않은 팀/문서 또는 빈 교집합 | 기존 요청 검증 경로에서 거부 | 원문/모델 실행 전에 실패 |
| generation/파일 상태 변경 | 관련 캐시 폐기·재검증 또는 변경 오류, 이전 결과 사용 금지 | 오래된 DB·tokenizer mismatch 차단 |
| 잘못된 부모/span 또는 복사 중단 | 완료 캐시/사본 READY를 만들지 않음 | 부분 파일 사용·품질 검증 우회 없음 |
| 동시 질문·warmup·로그 큐 포화 | cache build/lease 격리·기존 admission 정책, 진단 누락 수 기록 | 질문 교차 오염·무제한 메모리 대기 없음 |
| 검색 순위의 동점·빈 결과·다음 페이지 | 기존 순서·total·cursor 재현, 0건과 오류 구분 | 전체 페이지 합이 기준 결과와 같음 |
| 전체 deadline/DB 오류 | 실제 오류·시간·단계 기록, 전체 deadline 유지 | 20초 별도 차단 재도입 없음 |
| 원장 commit 실패·프로세스 종료 | transaction rollback/유효한 완료 기록에 한해 복구 | 성공/발행 완료를 거짓 표시하지 않음 |

계약 검사: 팀 aliases/범위, generation 변화, 부모 누락/순환, source span, rank/동점/정확 total,
cursor 완전성, deadline, 원장 reserve→tool→observation→model delivery 순서, FINAL recovery,
로그 writer 포화/실패/종료, 사본 hash/용량/동시성/원복.
측정은 첫/후속 질문·다른 worker·다른 팀을 구분한다. 같은 질문 반복을 독립 품질 표본으로 세지 않는다.

### 현장 인계와 원복

기존 `~/DEV`에 백업 후 적용하는 ZIP와 별도 완전 실행 TXT를 준비한다.
ZIP·실행 파일·엔진/PIPELINE pin·선택 generation·환경 설정 이름을 receipt로 결속한다.
commit한 실제 push checkout에서 `genos_release_gate.py`의 ZIP 대조·generation E2E·verify_assets를 실행한다.
검증한 commit을 push하고 같은 generation으로 새 코드서빙 리비전을 배포한다.
워크플로우 코드를 바꾸는 경우에만 Python 단계 전체 교체를 별도 인계한다.
실제 질의·warmup은 **워크플로우 테스트 화면에서만** 확인한다.
Git main 병합·push·CURRENT 선택·코드서빙 리비전·질문 성공은 각각 상태를 기록한다.
오류/회귀 시 이전 검증 코드 리비전과 generation으로 복귀한다. 새 사본/파생물은 분리해 보존한다.

## 5. 기대효과·자원·미확인

| ID | 기대/비용 | 종류와 계산 | 한계 |
|---|---|---|---|
| C1 | 사진의 네 반복 조회가 노출한 work 합 약 129.6초 | 계산: 34.5+23.420+42.904+28.779 초, 동일 요청의 비중첩 작업 | 제거 대상으로 드러난 과거 시간이며 실제 절감 예측이 아님. 새 검증·cold 준비·캐시 확인 비용을 빼야 함 |
| T1 | warm 요청의 team/ID SQL 전체 순회와 전체 구조 검사를 각각 0회로 만드는 것 | 목표, 실행 횟수로 검증 | 모델·FTS·원장·플랫폼 지연을 포함한 전체 응답 시간 보장이 아님 |
| C2 | 읽기 사본의 추가 디스크와 cold 준비 | 계산식: 선택 DB bytes 합 + 임시 복사 공간 + 보존 세대 공간. 복사시간≈bytes/실효 대역폭 + 해시 검증시간 | 실제 파일 크기·로컬 디스크·대역폭 미확인. 첫 요청에서 복사하면 오히려 느려질 수 있음 |
| C3 | 부가 메모리 | ID/팀/구조/순위 캐시 + 진단 큐 bytes 한도 | 전 DB 메모리 적재를 가정하지 않음. worker 수만큼 늘 수 있어 상한 측정 필요 |
| U1 | FTS latency, 다음 모델까지 공백, 전체 답변 지연의 개선률 | 미산정 | 파일 I/O·연결 잠금·throttling·순위 일치 결과가 필요 |
| U2 | 실제 구현 일정·GENOS 배포 대기 | 미산정 | 현장 로컬 저장소·권한·플랫폼 설정과 검증 가능한 시간이 아직 없음 |

새 모델 호출·외부 모델 전송은 이 성능 수정의 전제에 없다.
로컬 단위/합성 계약 통과는 GENOS 성능이나 법률 답변 품질 인증이 아니다.

## 6. 근거와 자체 검토

작업 코드 근거: `service.py`, `app.py`, `pipeline.py`, `team_scope.py`, `storage.py`,
`document_agent.py`, `navigation_match.py`, `fulltext.py`, `legal_agent_adapter.py`,
`legal_agent/exploration_tools.py`, `workflow_relations_tools.py`, `repository.py`, `relations_repository.py`,
`request_report.py`, `observability.py`. 해시와 사진 출처는 `EVIDENCE.json`에 고정한다.
운영 근거: GENOS 진입 문서, latency diagnostics와 fulltext wait 문서, MAIN architecture.

외부 공식 근거:

- [SQLite 네트워크 파일시스템 사용 고려사항](https://www.sqlite.org/useovernet.html): 네트워크 파일 접근은 latency/locking 문제를 만들 수 있다는 일반 근거다. 우리 현장 원인을 증명하지 않는다.
- [SQLite FTS5 rank 정렬](https://www.sqlite.org/fts5.html#sorting_by_auxiliary_function_results): rank column 정렬은 bm25 함수 직접 정렬보다 유리할 수 있다. 현재 코드에 이미 적용되어 있어 같은 수정으로 추가 개선을 주장하지 않는다.
- [SQLite immutable 연결](https://www.sqlite.org/c3ref/open.html): immutable은 읽기 전용과 함께 locking/change detection을 끈다. 실제 변하는 파일에 사용하면 잘못된 결과가 가능해 불변 사본 조건을 요구한다.
- [SQLite WAL](https://www.sqlite.org/wal.html): 네트워크 파일시스템에서의 WAL 제약이 있어 NFS journal의 단순 WAL 전환은 계획에서 제외한다.
- [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): CPU 제약/pressure 지표를 읽어 자원 대기 가설을 구분한다. 현재 GENOS 값은 읽지 못했다.
- [Python 3.11 sqlite3](https://docs.python.org/3.11/library/sqlite3.html): 연결·thread·transaction·progress callback 계약의 구현 기준.

설계/수치 검토는 동일 작성자의 자체 검토다. 독립 에이전트 검토·현장 성능 인증은 수행하지 않았다.
`REVIEW.md`에 선행 조건과 미해결 항목을 남긴다.

## 7. 1차 패치 실행 기록

`latency-20260928-r2`로 A·B, 로그 비동기 출력과 주요 지연 계측, 계획 전 admission·WARMUP을 구현했다.
로컬 계약·회귀 135개와 R1/R2 설치기 계약 16개 통과. 185개 preimage의 적용·재실행·정확 원복,
최종 ZIP/TXT 적용·코드 gate·문법·해시·JS 제외 검증을 완료했다.
삼성메일에 ZIP·실행 TXT·패치노트 3개 발송 확인(message 1a0e572ac39322db).
[실행·한계·원복](../../OPERATIONS/GENOS_LATENCY_R2_20260928.md)을 따른다.
GENOS generation gate·push·리비전 배포·현장 속도는 미확인이다.
C의 자원 계측은 SQLite/mount/읽을 수 있는 cgroup v2 CPU에 한정하며 memory pressure·디스크 용량·
query plan·connection lease 대기 세부 분리는 아직 미구현이다. D/E와 F의 transaction 묶음은 후속이다.
