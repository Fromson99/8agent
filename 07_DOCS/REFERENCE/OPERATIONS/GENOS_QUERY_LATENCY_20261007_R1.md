# GENOS 검색 준비 계측·중복 조회 감소 R1

2026-10-07 현장 사진은 PLAN 다음 RECALL 진입 05:46:20.730에서
LAW_FULLTEXT_DIRECTORY 05:48:42.027까지 약 141.3초를 보여 준다.
READ 뒤 SELECT 진입 05:48:44.391에서 마지막 heartbeat 05:51:54.824까지
약 190.4초 동안 새 이벤트가 없다. 이는 작업 구간 관측이며 SQL, NFS,
내부 모델 가운데 어느 하나의 소요 시간으로 확정할 수 없다.
사진에는 실제 서빙 리비전과 generation 해시가 없다.

## 근거와 수정

기준은 마지막 인계 `GENOS_NO_SOCKET_CHAT_20261007_R3` ZIP이며 SHA-256은
`5ec5384b020cb76e8ca2f28b252850168888bed29e855c6116ee113b2002cb06`이다.
발송 전 선택된 로컬 MAIN이 `session-runtime-v6-20261007-r1`(generation45)로 갱신되어,
최종 R3는 이 릴리스의 세션 런타임 변경과 이번 계측/최적화를 함께 결속한다.
10월 3일 SQL/SQLite 읽기 재사용과 9월 28일 검증된 카탈로그 재사용은 이미
이 코드에 있다. 법령별 후보 검색은 이후 추가되어 별도 중복이 남아 있었다.

| 실행 경로 | 확인한 기존 동작 | 이번 수정 |
|---|---|---|
| `law_candidates.allowed` | SourceMap 전체 항목의 JSON을 읽어 문서 ID 확인; 같은 요청에서 반복 | 문서 권한 범위에 해당하는 source ID만 한 SQL로 조회; 범위·mapping 객체 변경 시 다시 계산 |
| `UnitFulltextIndex` 법령/조문/적중 페이지 | 페이지마다 FTS count와 rank 검색 반복 | 동일 요청 연결·색인 해시·검색식·ACL의 적중 메타데이터를 한 번 계산해 재사용; 본문은 선택 페이지의 key로 조회 |
| RECALL/SELECT 준비 | 새 후보 경로의 상세 타이밍 공백 | 토큰화, 범위 조회, 구조 해석, SQL execute/fetch, JSON 해석, 원문 검증/읽기, 후보 구성, checkpoint를 개별 계측 |
| 모델 진입 | 일부 준비 계측이 DEBUG에만 존재 | 입력 기록, schema/view 준비, 요청 구성/인코딩/예약, transport 대기, 출력 검증/기록을 INFO에서 계측 |
| 기본 v6 설정 결속 | 인계 R3에서 프로필 내용과 PIPELINE의 프로필 pin이 다름 | 기존 프로필 내용의 실제 해시로 pin 수정; 프로필 내용/검색 정책 변경 없음 |

검색 캐시는 **요청의 SQLite 연결 안에서만** 유지하며 다른 사용자의 질문에
공유하지 않는다. 현재 검색식 하나의 메타데이터만 유지하고 본문은 넣지 않는다.
적중 메타데이터 50,000개를 넘으면 캐시를 포기하고 기존 전체 SQL 검색으로
돌아간다. 이 한도는 결과·법령·조문을 자르는 검색 한도가 아니다.
전체 건수, BM25 순서와 동점 ID 순서, 페이지 cursor, 권한 범위, 명시 참조,
원문·근거·재개 계약을 유지한다. 색인/원문 파일과 glossary compiler는 바꾸지 않는다.
큰 적중 집합에서는 한 번의 캐시 시도가 추가되므로 현장 로그로 fallback을 확인한다.

## 계측 확인

`GENOS_QUERY_LATENCY=1`과 `GENOS_LOG_LEVEL=INFO`가 기본이다.
`query-latency-20261007-r1` 진단 버전과 `step.started/finished/failed`가
기존 요청 로그에 붙는다. heartbeat의 active_step은 현재 세부 작업을 표시한다.
신규 계측은 질문·원문·SQL 문자열·인증키를 추가 출력하지 않는다.
기존 감사 journal의 입출력 보존 정책은 그대로다.

- SQL: `unit_fts.sql.*`의 sql_execute_ms, sql_fetch_ms, fetched_count.
- 캐시: `unit_fts.projection`의 cache_hit, match_count, cache_overflow.
- SQLite/NFS 단서: `unit_fts.connection`의 mount_type와 page_size/cache_size/mmap_size/temp_store.
- CPU 단서: thread_cpu_ms와 thread_non_cpu_ms; 큰 구간의 cgroup throttle 증분.
- 모델: model.request_build/encode/attempt_reserve/transport와 request_bytes;
  기존 모델 시도 로그에 토큰 사용량이 있으면 함께 확인한다.
- 저장/읽기: law.select.checkpoint, law.evidence.verify, law.read.original.

thread_non_cpu_ms만으로 NFS 대기라고 판정하지 않는다. SQL execute도 초기
결과를 만들 수 있어 fetch와 함께 읽는다. 중첩 span의 시간을 모두 더하면
중복 계산된다. start_log_ms가 크면 로그 기록 자체의 비용을 확인한다.
로그 비용이 문제이면 `GENOS_QUERY_LATENCY=0`으로 신규 span을 끌 수 있으며,
이때도 검색 최적화와 기존 감사 기록은 유지한다.

현장 workflow 화면에서 기존 문제가 생긴 질의를 실행한 뒤 해당 요청 로그를
첨부된 `GENOS_QUERY_LATENCY_20261007_R3_SUMMARIZE.txt`로 요약한다.
이 Python TXT는 질문/본문을 요약 산출물에 넣지 않고 timing 필드만 읽는다.

```bash
python3 GENOS_QUERY_LATENCY_20261007_R3_SUMMARIZE.txt /절대경로/요청.log --output /절대경로/새_요약.json
```

## 반입과 검증 범위

[누적 코드 ZIP과 실행 TXT](../../../../08_DEPLOYMENT/GENOS/handoffs/query_latency_20261007_r3/README.md)는
기존 `~/DEV`에서 검증된 선행 해시를 확인하고 백업 후 적용한다.
일반 개발 rehash로 현장 해시 차이를 덮지 않는다. 선택된 기존 NFS generation을
그대로 결속해 loader 및 동일 checkout의 Git gate를 검증한다.
push와 코드서빙 리비전 배포, 플랫폼 binding, workflow 화면 테스트는 별개다.
통합 JSON / 분리 workflow SSE의 기존 선택과 Socket.IO 제거 R3를 포함한다.

외부 검증은 모의 데이터의 검색 계약, 권한, 모든 페이지, 캐시 overflow/변조/중단,
요청 간 격리와 실제 적용 TXT의 적용·재실행·원복·gate 검사다. 내부 모델 호출이나
새 성능/프롬프트 A/B 실험은 수행하지 않는다. 속도 개선 배수는 주장하지 않는다.
별도 검증 기록에 통과/기존 실패 재현을 기록한다. 작업 코드와 반입 ZIP을 준비하며,
선택된 로컬 MAIN generation45 및 기존 frozen 릴리스는 변경하지 않는다.
GENOS 반입·push·리비전 배포·내부 질의 실측은 현장 확인 전까지 미확인이다.
