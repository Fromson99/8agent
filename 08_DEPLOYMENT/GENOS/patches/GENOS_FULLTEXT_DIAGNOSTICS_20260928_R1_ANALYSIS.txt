# GENOS fulltext 병목 계측

2026-09-28 `fulltext-diagnostics-20260928-r1` MAIN 작업 코드.
사용자가 제공한 검색 로그 사진 2장을 근거로 기존 FTS/위치 구성 계측을 세분화했다.
검색 OR, BM25 가중치와 동점 순서, 팀/문서 범위, 정확한 total/cursor,
요청 deadline과 요청별 SQLite 연결을 유지한다. 모델 호출·새 성능 실험은 수행하지 않는다.
데이터 generation, CURRENT, 로컬 활성 frozen 릴리스와 완료된 인계 ZIP은 변경하지 않는다.

## 사진으로 확인된 구간과 남은 원인

| 항목 | 사진의 값 | 해석 |
|---|---:|---|
| FTS rank 전체 | 84,166ms | 검색 도구 안의 순위/범위 처리 구간 |
| SQL execute | 877.028ms | prepare/초기 SQLite 실행을 포함 |
| 첫 행 | 5.603ms | 첫 fetchone |
| 이후 SQL fetch | 82,920.937ms | SQLite 내부 순위 계산과 파일 읽기/스케줄링이 함께 포함 |
| SQL 일치 / 범위 선택 | 7,676 / 2,191건 | 전체 일치를 읽은 뒤 Python에서 허용 source를 필터 |
| 위치 구성 work / 스레드 CPU | 21,216.404 / 365.325ms | 해당 스레드의 계산 외 대기가 큼. I/O·GIL·잠금·스케줄링은 별도 구분 필요 |
| 페이지 프리뷰 | 689ms | 반환 페이지 구성 |
| 다음 모델 HTTP | 63,299ms | 내부 모델의 대기/생성/전송은 이 사진으로 분리되지 않음 |
| 출력 보정 | schema_repairs=0 | 보이는 모델 응답에는 스키마 보정 재호출 없음 |

사진의 `cpu_throttled_usec_delta=542767`은 약 0.543초다. cgroup 누적값이며
해당 요청만의 CPU 제한 시간이 아니다. `nr_throttled=605`를 605초로 해석하지 않는다.
이 값만으로 84초의 원인을 CPU quota 또는 NFS로 확정하지 않는다.
HTTP 완료부터 schema accepted까지 약 0.4초이나 검증 단독 계측값은 아니다.

위치 구성은 `workflow_relations_tools.search` → `SourceMap.__getitem__`을 통해
캐시에 없는 source마다 본문 JSON 전체를 SQL로 읽고 decode한다. SQL 지연과 decode
지연의 비율은 아래 새 계측을 받은 뒤 판단한다.

## 연결과 로그

실행: `service.py` → GENOS가 선택한 generation → `Pipeline`/v5 세션 →
`workflow_relations_tools.search(mode=fulltext)` → `FulltextIndex.rank` → 위치 구성 → 페이지 프리뷰.
`FulltextIndex.connect`는 요청별 read-only 연결을 유지하며 최초 연결의 설정만 읽는다.
다음 로그는 기존 코드서빙 진단 로그와 요청별 공유 로그의 숫자 계측에 들어간다.
`request_report.py`의 실시간 TXT·최종 TXT 필터도 새 숫자/고정 상태 항목을 표시한다.
JSON에는 query plan·느린 배치 목록 등 구조화한 세부 항목을 보존한다.
질문, 검색 단어, 본문, 키, 원문 ID를 이 계측에 추가하지 않는다.

| 이벤트 | 확인할 값 |
|---|---|
| `fulltext.connection.facts` | 선택 색인의 `index_bytes`, manifest의 `indexed_source_count`, SQLite 버전, page/cache/mmap/temp 설정, query plan의 `uses_temp_sort`; 설정 수집 시간은 `facts_ms` |
| `fulltext.sql.started` | `search_id`, 프로세스/스레드 ID, 형태소/허용 source 개수, 같은 프로세스의 시작 시 동시 검색 수 |
| `fulltext.sql.progress` | fetch 배치가 반환된 뒤 15초 이상 지났을 때만 최대 4회. SQLite 호출이 막힌 동안의 실시간 진행률이 아님 |
| `fulltext.sql.timings` | execute/첫 행/fetch의 벽시계·스레드 CPU, 배치 수와 느린 배치 최대 5개, 조회/선택/범위 제외 건수, 오류/완료, 동시 검색 peak, 스레드 자원 delta |
| `fulltext.location.timings` | source 조회/캐시 적중/SQL 횟수, execute/fetch/JSON decode 시간·CPU, 읽은 JSON 문자 수, 가장 느린 source SQL, route 생성, 좁은 범위의 재형태소 분석, 스레드 자원 delta |

`SourceMap.measure_loads`는 위치 구성 동안만 숫자를 집계한다. 행마다 로그를 쓰지 않는다.
위치 구성이 실패하면 기존 예외를 보존하고 측정 상태를 해제한다.
FTS 실패/요청 deadline 중단에서도 동시 검색 카운터를 해제하며 검색 오류를 성공으로 바꾸지 않는다.
동시 검색 수는 프로세스 범위다. 다른 worker/코드서빙/팀의 검색 수와 합산하지 않는다.

스레드 자원은 `/proc/thread-self/io`, `/proc/thread-self/schedstat`,
`getrusage(RUSAGE_THREAD)`의 지원되는 값만 읽는다. 미지원 필드는 생략하며 0으로 대체하지 않는다.
`thread_non_cpu_ms`는 경과시간과 해당 스레드 CPU의 차이이며 I/O 전용 시간이 아니다.
`scheduler_wait_ms`는 CPU 실행을 기다린 runqueue 시간으로 blocked I/O나 GIL 대기 전체를 나타내지 않는다.
`thread_read_bytes_delta`는 Linux 블록 I/O 계측이므로 NFS 네트워크 읽기량으로 간주하지 않는다.
proc 자체를 읽는 작은 비용도 read 문자/시스템 호출에 포함된다.

## 원인별 후속 수정 후보

1. **위치 SQL이 큼:** 좁은 본문 범위가 없는 검색에서는 기존 검증된 matcher source metadata로
   문서/조문 위치를 얻고, 본문은 실제 반환 페이지/READ에서 읽는 후보를 검토한다.
2. **fetch CPU가 큼:** BM25/FTS 작업량과 OR 단어의 범위를 검토한다. SQL로 scope를 옮겨도
   FTS 내부 계산량까지 줄어든다고 가정하지 않는다. 범위별 색인은 BM25 통계와 순위를
   바꿀 수 있으므로 기존 전체 색인 순위와의 의미 차이를 검증해야 한다.
3. **fetch CPU는 작고 SQL 대기가 큼:** 실제 page cache 크기·읽기/major fault·runqueue 대기를
   대조한다. 메모리 예산에 맞는 연결 cache, 검증된 불변 파일의 로컬 읽기 사본을 후보로 둔다.
   로컬 사본은 generation/파일 해시/접근 범위/교체 검사를 보존해야 한다.
4. **같은 검색의 페이지 재요청이 반복됨:** generation·범위·query terms·순위 설정에 결속한
   제한된 검색 결과 재사용을 검토한다. 요청별 핸들/접근 범위는 공유하지 않는다.
5. **동시 검색 때만 악화:** process peak와 같은 시각의 worker 자원/모델 대기를 대조한다.
   프로세스 로그 하나로 전체 현장 동시성이나 NFS 서버 병목을 확정하지 않는다.

현행 SQL은 이미 `ORDER BY rank`를 사용하고 빌드는 FTS `optimize`를 실행한다.
보관된 과거 세대가 여러 개라는 이유로 현재 검색이 모든 세대를 읽는 것은 아니다.
총 source 수, 현재 파일 크기, query의 일치 비율과 I/O를 함께 확인해야 한다.
임의 LIMIT·단어 삭제·AND 전환은 정확한 total/회수 범위를 바꾸므로 이 계측에 포함하지 않는다.
실제 효과 비교를 수행하면 저장소의 ADR reservation/freeze/평가 절차를 별도로 따른다.

## 검증과 반영 상태

WSL 개발 환경 검사와 Python 문법·Git whitespace 검사가 통과했다.
`test_fulltext_diagnostics.py`, `test_fulltext_ranking.py`, `test_legal_agent_v5.py`,
`test_legal_agent_v5_sources.py`, `test_genos_latency_r2.py`와 반입 설치기·요청 기록·thinking
실시간 로그 테스트를 함께 실행해 모의 계약·회귀 **144개가 통과했다**(42.13초).
계측 미지원, 실패/중단 후 카운터 회수, 두 검색의 동시성, 캐시 재사용, 범위/동점/페이지를
확인했다. 작업 엔진 manifest 26개는 진단 세 파일과 보고서 출력 필터의 pin만 갱신했고 PIPELINE의
데이터·모델·프로필 필드는 수정 전과 같음을 대조했다.
이 검증은 현장 성능 수치나 내부 모델 품질 인증이 아니다.
이번 수정은 작업 코드와 반입 ZIP/TXT까지 준비했다. 현장 checkout 적용·generation gate,
Git push, 새 코드서빙 리비전 배포, 실제 워크플로우 질문은 별도이며 현재 미확인이다.
현장 확인은 기존 워크플로우 테스트 화면에서만 수행한다.
기존 generation을 소비하며 재색인/워크플로우 Python 교체를 요구하는 변경은 없다.

이번 세션의 수정 전 바이트는 `90_RUNTIME/diagnostics/fulltext-20260928-r1-preimage/`
및 `inventory.json`에 보존한다. 원복은 이 수정 파일과 갱신한 작업 엔진 pin만 대상으로
후속 변경 유무를 검토해 수행한다. 기존 데이터·완료 릴리스·인계 ZIP을 원복 대상으로 쓰지 않는다.

## 삼성메일 반입본과 request_report 해시

전달본은 `GENOS_FULLTEXT_DIAGNOSTICS_20260928_R1.zip`과 같은 이름의 `_APPLY.txt`다.
실행 TXT에 ZIP을 포함하며 기존 `~/DEV`에 백업 후 적용한다. 기존 현장 버전이
latency R2인지 관계 제한 제거 이후인지 확인해 위치 구성 외의 관계 탐색 코드는 보존한다.
`request_report.py`는 선택 엔진의 유효한 pin으로 확인한 현장 파일에서 출력 필터만
구조적으로 확장한다. 기존 thinking·팀별 기록·요약·최종 기록 기능을 통째로 교체하지 않는다.

그 파일의 기대/실제 해시가 다른 경우, 기대 해시가 보존된 전달본에 있고 설치 코드가
기존 전달본 또는 검증한 출력 변환의 SHA-256/AST와 일치할 때만 복구한다.
주석·공백 차이는 허용하지만 임의 기능 수정의 불일치는 자동 승인하지 않는다.
모든 선택 소비 엔진의 코드 pin과 PIPELINE manifest pin을 함께 갱신하고,
`KNOWN_REPORT_PIN_REPAIR`에 기대/실제/새 해시를 남긴다. 다른 파일·스키마·manifest의
불일치는 대상 코드 변경 전에 중단한다. 실제 현장 오류 원문은 아직 미확인이다.

설치기는 적용·재실행·중간 실패 복구·롤백과 이후 수정 보존을 지원한다.
apply 뒤 변경 파일만 검토/commit하고 같은 TXT의 `MODE=verify`로 기존 설정이 선택한
generation과 바로 그 checkout을 검증한다. `MODE=code-only`는 코드 결속 검사만 수행한다.
데이터 해시를 덮어쓰거나 generation을 새로 만들지 않는다. 검증 후 push·팀별 코드서빙
리비전 배포·기존 워크플로우 화면 확인은 각각 별도다. 상세 실행은 첨부 PATCH_NOTES를 따른다.

근거: [SQLite FTS5 rank](https://www.sqlite.org/fts5.html#sorting_by_auxiliary_function_results),
[SQLite cache_size](https://www.sqlite.org/pragma.html#pragma_cache_size),
[Linux proc I/O](https://kernel.org/doc/html/latest/filesystems/proc.html),
[Linux scheduler stats](https://kernel.org/doc/html/latest/scheduler/sched-stats.html).
