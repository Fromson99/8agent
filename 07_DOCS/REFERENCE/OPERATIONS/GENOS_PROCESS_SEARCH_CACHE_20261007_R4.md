# GENOS 서버 프로세스 검색 캐시 — 2026-10-07 R4

사용자 정정: 첫 질문에서 생성한 캐시는 서버가 살아 있는 동안 이후 요청과 세션에서
계속 재사용한다. 이전 query-latency R3의 연결별 검색 메타데이터 캐시를 프로세스 공용
LRU로 확장했다. 질문·답변·프롬프트·증거 ledger·세션 상태와 SQLite 연결은 공유하지 않는다.

## 연결과 무효화

`TermIndex.tools → SourceMap.cache_binding → law_candidates.allowed`는 검증된 navigation
파일 상태·generation·원문/색인 해시·현재 문서 권한 범위로 source ID를 재사용한다.
질문이 달라도 같은 문서 범위면 이 캐시를 사용한다. 일반 mutable mapping은 공유하지 않는다.

`law_candidates.index → UnitFulltextIndex._projection`은 검증된 FTS 파일 상태·generation·
원문/navigation/FTS 해시·검색어 순서/중복·허용 source ID·행 한도로 순위 메타데이터를
재사용한다. SQLite 연결이 닫혀도 공용 캐시는 남는다. SQL 오류는 캐시하지 않는다.
동시에 같은 key가 처음 들어오면 한 요청만 생성하고 나머지는 해당 완료를 기다린다.
대기 요청의 기존 deadline을 유지하며, 하나의 요청 취소가 생성자를 취소하지 않는다.

`UnitFulltextIndex.hit_page`는 현재 ACL로 고른 정확한 key 목록의 원문 JSON 문자열을
재사용한다. 반환할 때마다 새 JSON으로 해석하므로 한 요청의 수정이 다음 요청을 오염시키지
않는다. 페이지 순서·전체 건수·cursor binding은 기존 SQL과 동일하다. 파일 변화를
캐시 조회/생성 전후에 검사하며, 이전 세대의 캐시를 새 세대에서 사용하지 않는다.

## 유지 기간과 한도

TTL은 없다. 기본 `GENOS_RUNTIME_CACHE_MIB=128`, `GENOS_RUNTIME_CACHE_ENTRIES=256`이다.
공유한 세 종류의 key/value Python 객체 예상 크기 합과 항목 수에 적용하며 전체 프로세스 RSS
한도가 아니다. 한도를 넘으면 최근에 사용하지 않은 항목부터 비우고 필요하면 다시 계산한다.
한 항목이 용량보다 크면 해당 요청에서 사용하되 서버 캐시에 넣지 않는다.
`MATCH_CACHE_ROWS=50000`을 넘는 검색은 overflow marker만 재사용하고 기존 전체 SQL로 처리한다.
검색 결과를 잘라 한도에 맞추지 않는다. 한도는 서버 시작 때 읽으며 변경하려면 재시작한다.

현재 GENOS `start_sse.py`는 단일 워커다. 캐시는 해당 Python 프로세스 안에서 유지된다.
서버/컨테이너 재시작·새 리비전 배포 때 비워진다. 여러 replica나 Python 워커를 운영하면
각 프로세스가 각각 생성한다. 전체 데이터 상주는 아래 별도 snapshot 경로에서 관리하며 이 LRU 한도를 적용하지 않는다.

## 계측과 현장 확인

기존 query-latency INFO 계측과 누적 system logging을 보존한다.
`runtime_cache.scope/matches/preview/wait/admission`에 hit·용량·항목 수·축출·대기 시간을 기록한다.
로그 요약에 process_cache_hits/builds/evictions/peak_observed_bytes를 추가했다.
새 캐시 로그에 검색어·본문·source key·사용자 인증정보를 기록하지 않는다.

`query_latency_20261007_r4`의 ZIP·APPLY TXT·전체 workflow TXT·요약 TXT로 기존 `~/DEV`에
검증/백업 후 적용한다. SQLite schema나 NFS generation을 재구축할 필요 없다.
Git push·새 리비전 배포·workflow 편집기 반영은 별도이며 질의는 workflow 테스트 화면에서 한다.
같은 문서 범위와 검색어로 첫/두 번째 요청 및 새 세션 요청의 캐시 hit를 확인한다.
GENOS 실제 실행 binding·내부 데이터 속도·현장 배포는 외부 세션에서 확인하지 못했다.
로컬 ACTIVE_RELEASE 포인터는 변경하지 않았다. 과거 인계본과 실패 기록은 보존한다.

## 전체 데이터 상주 — 사용자 추가 정정과 16GB 설정

사용자는 동일 검색 결과를 재사용하는 방식만 원한 것이 아니라, 선택된 검색 데이터
전체를 한 번 올린 뒤 모든 질문에 재사용하는 방식을 원한다고 다시 명시했다.
`resident_data.POOL`이 원문 Store, TermIndex navigation, 신/구 FTS 색인,
서빙 Glossary의 실제 소비 SQLite 전체를 처음 열 때 적재한다. 결과 캐시는 보조 기능이다.
`full_glossary.py`는 compiler/cache pin을 유지하기 위해 수정하지 않았고 기존
`navigation_agent._serving_glossary_ro` 연결 주입 지점에서 전체 적재를 연결했다.

검증한 원본 파일 상태와 SHA로 snapshot을 결속한다. RAM은 SQLite online backup과
named shared-memory database를 사용하고 연결별 query_only/authorizer로 쓰기를 막는다.
RAM keeper는 서버 종료까지 유지한다. 로컬 복사본은 스트리밍 SHA를 확인한 전체 바이트이며
권한 0400·읽기 전용 immutable URI로 읽는다. 한 snapshot을 모든 질문의 SQL이 사용한다.
첫 질문 이전에 기존 warmup이 이 경로를 열면 그때 적재되고, 그렇지 않으면 첫 요청에서
적재한다. 질문별로 필요한 데이터만 LRU에 저장하는 방식과 다르며 snapshot은 TTL/LRU로
비우지 않는다. 새 프로세스는 새 snapshot을 만든다. 정상 종료 시 로컬 임시본을 정리한다.

사용자 확인 서버 메모리는 16GB다. 기본 `GENOS_RESIDENT_DATA=auto`,
`GENOS_RESIDENT_CACHE_MIB=8192`, `GENOS_RESIDENT_CACHE_DIR=/var/tmp`로 정했다.
RAM 예산은 파일 크기에 1/3 여유를 둔 추정치이며 전체 프로세스 RSS 상한이 아니다.
사용 가능한 메모리와 cgroup을 확인하고 2GiB 여유를 남긴다. RAM 예산이 부족한 파일도
전체 로컬 snapshot으로 유지하며 NFS 직접 검색으로 조용히 복귀하지 않는다.
`memory` 모드는 전체 RAM만 허용하며 부족하면 명확히 실패한다. `local`은 전체 로컬
복사본, `off`는 원본 읽기 경로다. 네트워크 파일시스템을 로컬 캐시 경로로 지정하면 거부한다.

로컬 MAIN45 데이터의 원문/navigation/units SQLite 합은 1,526,788,096바이트(1.42GiB),
하위 glossary 파일까지 물리적 SQLite 전체 합은 4,670,906,368바이트(약4.35GiB)다.
실제 서빙 Glossary가 소비하는 파일만 적재하며 외부 보고서용 전체 복제를 생성하지 않았다.
GENOS 데이터 크기와 이미 사용하는 RAM은 이 외부 세션에서 확인하지 못했다.
`resident_data.open/load/wait`, `cache_storage`, `dataset_bytes`,
`resident_memory_reserved_bytes`, `resident_local_bytes`로 실제 선택과 최초 적재/재사용을 확인한다.
GENOS workflow 화면에서 서로 다른 질문과 새 세션을 실행하여 resident_data hit를 확인한다.
검색 결과 계산·모델 호출 지연 자체를 없앤다는 주장은 하지 않는다.

구현 근거: Python 3.11 SQLite Connection.backup 공식 문서
https://docs.python.org/3.11/library/sqlite3.html#sqlite3.Connection.backup
및 SQLite named in-memory database 공식 문서 https://www.sqlite.org/inmemorydb.html .
