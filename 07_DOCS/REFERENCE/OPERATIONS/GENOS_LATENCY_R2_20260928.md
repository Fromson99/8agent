# GENOS 1차 성능 수정 R2

2026-09-28, `latency-20260928-r2` 작업 코드 및 반입 패키지.
기존 R1 진단 로그로 확인한 반복 준비 작업을 줄이고 검색/원장 대기의 세부 계측을 추가했다.
전체 MAIN 중 선택된 원문·용어집 세대를 소비하는 RAG 서빙 경로만 변경한다.
데이터 세대, CURRENT, 외부 모델, 로컬 활성 릴리스를 변경하지 않았다.

수정·현장 실행·재개·gate·원복의 정본은 [R2 패치노트](../../../08_DEPLOYMENT/GENOS/patches/latency_20260928_r2/PATCH_NOTES.txt)다.
사용자에게는 ZIP·독립 실행 TXT·독립 패치노트 TXT 3개를 인계한다.
기본 적용 대상은 R1이 적용된 기존 `~/DEV`이며, `~/DEV/TRANSFER/code`에 첨부를 두고 실행한다.

`team_scope.prepared_catalogue`는 문서 metadata 조회 한 번으로 ID/팀/분류를 준비한다.
`Store.check_unchanged`와 경로·manifest digest·dev/inode/size/mtime/ctime으로 캐시를 결속한다.
Pipeline은 같은 Query를 재사용하며 HTTP Request 스키마를 확장하지 않는다.
`multi_entry_navigation.bind_structure/validate_structure`는 최종 바인딩의 불변 구조와
문서별 순수 source 목록을 보존한다. 성공한 검증만 재사용하고 요청별 핸들·SQLite 연결은 분리한다.

`Pipeline.run`의 admission lease를 세션으로 전달하고, WARMUP도 동일 자료를 준비한다.
`observability.AsyncHandler`와 `_LiveLog`는 요청 스레드의 이벤트 출력 I/O를 분리한다.
큐는 건수/bytes를 제한하며 오류/최종 이벤트 예약 용량과 누락/쓰기 실패 이벤트를 둔다.
원장은 기존 동기 transaction과 durable commit 경계를 유지한다.
log file 생성·source/journal I/O·첫 구조 준비는 여전히 현장 자원에 영향을 받는다.
추가 구조 메모리는 현장 worker 수와 함께 확인해야 하며 단축 시간을 보장하지 않는다.

검색 OR·BM25·동점·범위·정확 total/cursor를 유지한다. FTS row fetch 단계를 나눠 계측했으며
계측을 위해 검색 결과에 임의 LIMIT를 추가하지 않았다. 위치 구성/프리뷰, 원장 begin/body/commit,
v5 view 구성·저장, 요청 생성과 attempt 예약에 시간이 남는다.
cgroup 값은 읽을 수 있는 로컬 v2 cpu.stat만 사용하며 미지원 값은 미확인으로 둔다.
프로세스 중단·저장 장애 시 비동기 진단 사본은 누락될 수 있으며 journal이 감사 정본이다.

검증: 로컬 합성 계약·회귀 135개와 R1/R2 설치기 계약 16개 통과.
185개 실제 preimage 파일의 격리 Git fixture에서 적용·재실행·clean commit의 code gate·정확 원복 통과.
현장 generation E2E/verify_assets, Git push, 코드서빙 리비전과 실제 질의는 미확인이다.
실제 질문·WARMUP은 기존 워크플로우 테스트 화면에서만 확인한다.

로그의 후속 요청에서 `catalogue.cache.hit`, `sources.structure_ready checked_count=0`,
`diagnostic_revision=latency-20260928-r2`를 확인한다. worker별 첫 준비는 별도로 본다.
FTS 65초와 다음 모델까지 약 50초는 새 계측을 현장에서 받은 뒤 다음 수정 범위를 결정한다.

## 현장 사진 확인 — 2026-09-28 10:22 KST 수신

사용자 사진 4장에서 `diagnostic_revision=latency-20260928-r2`, 2,105 문서 catalogue.cache.hit,
선택 1,003 문서, `sources.structure_ready cache_hit=true checked_count=0`을 확인했다.
구조 검사의 work는 0.158ms다. 같은 요청의 반복 준비를 재사용한 관측이며 전체 성능 인증은 아니다.
모델 요청 구성은 work 2.358ms / 시작 로그 109.416ms, view 저장은 work 1.795ms,
view 구성은 work 911.199ms다. 로그 호출의 약 80~110ms 비용은 여전히 남았다.
R2는 I/O writer를 옮겼지만 큐 투입 전 `_safe_fields`와 요청 capture의 정제·변환은 동기다.
어느 처리/핸들러/자원 대기가 시간의 대부분인지는 세부 CPU·처리 구간 계측이 필요하다.

`MODEL_PROPOSAL_INVALID`는 workflow 행동/선별 검증 거부로 보정 요청을 만드는 경로다.
성공한 선별은 보존한다. 재호출 HTTP 200, HTTP 소요 10,321ms가 보이나 FINAL 반환은 보이지 않는다.
구체 원인은 같은 원장의 `WORKFLOW_REPAIR.errors`에 남고 사진은 이 오류 항목을 보여주지 않는다.
표시된 transaction commit은 약 0.4~5.6ms이며 전체 원장 I/O가 빠르다는 결론으로 확대하지 않는다.
`fulltext.cached`는 인덱스 바인딩 재사용 표시다. 검색 실행 `fulltext.sql.timings`가 없어
이전 65초 검색 지연 해소 여부는 확인하지 못했다.

다음 수정 후보: 동일 이벤트 정제의 중복 제거/비동기 이동 및 handler별 시간 계측,
보정 로그에 거부 field·고정 오류 코드와 상세 원장 위치 연결, 정확한 errors를 근거로
허용 행동/선별 전달 계약 개선. 범위·인용 검증은 유지하고 오류를 자동 통과시키지 않는다.
새 코드 패치·메일 발송·배포는 이 사진 검토에서 수행하지 않았다.
