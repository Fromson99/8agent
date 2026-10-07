# FULLTEXT 위치 구성의 본문 조회 제거 — 2026-09-29 R1

## 2026-09-29 현장 비교 관측과 실제 사용 상태

사용자가 제공한 캡처 3장에는 `offline-20260929T011900137772Z`,
`term-source-ccb504d56d2a7d71c140`의 COMPLETE 요약이 표시됐다. 10개 case 모두
결과 동일·비어 있지 않음·위치 구성 본문 SQL 0·개선 기준을 통과했고, 각 case의
위치 시간은 4쌍 모두 감소했다. 프리뷰 포함 검색 함수의 중앙값 감소율은
7.6~69.4%, 위치 구성 감소율은 98.3~99.7%다. 후보 검색 시간은 2.118~2.835초다.
사진 요약 관측이며 원본 RESULTS/FROZEN_PLAN의 해시·전체 행을 외부에서 검증한 기록은 아니다.
모델 호출 0회·워크플로우 검증 미수행이다. 초기 로딩·답변 전체·콜드 캐시·NFS 원인과
GENOS 리비전 배포 성공을 이 결과로 판단하지 않는다. ADR의 완료/품질 승격 상태도 자동 변경하지 않는다.

MAIN 작업 코드의 실제 v5 `RelationsTools.search`에 개선 함수가 연결됐고 이를 소비하는
20개 엔진 및 PIPELINE pin이 일치한다. BENCH는 동결한 두 함수를 직접 비교하며
checkout의 함수를 교체하지 않는다. 실제 GENOS에서는 기존 R1 APPLY TXT로 checkout에
적용한 뒤 해당 commit/선택 generation을 검증하고 push·코드서빙 리비전 배포·워크플로우
확인을 진행한다. 이번 코드 수정 자체에는 데이터 재구축이나 워크플로우 Python 교체가 필요 없다.
2026-09-29 확인 시 로컬 활성 frozen release의 검색 함수에는 이 변경이 포함되지 않았다.
다른 작업의 로컬 release 전환과 GENOS 코드 반영을 구분한다.

## 구축 감사 분리와의 호환 확인

진행 중인 `navigation_storage` 변경은 구축 감사 표 4개를 별도 보존하고 검색용
`source` 및 용어·정의·참조 표를 유지한다. 이번 위치 구성은 같은 `source`의
ID/document_id/unit_id 메타데이터를 사용하므로 해당 표의 계약을 함께 사용할 수 있다.
압축된 navigation SQLite의 SHA는 달라지므로 FULLTEXT manifest 및 legacy profile의
navigation 연결 해시는 새 세대에 맞춰 결속해야 한다. 해당 구축 작업의
`compact_generation`/`document-release rebind-fulltext` 경로가 이를 담당한다.

모의 단일 DB를 감사 분리 세대로 파생해 실제 v5 FULLTEXT 검색·프리뷰·READ 원문 근거
검증을 연결하는 계약 검사를 추가했다. 위치 SQL/lookup 0회, 비어 있지 않은 검색 결과,
프리뷰와 READ span/해시 검증을 확인했다. metadata/location·navigation storage·handoff
관련 검사 30개 통과. GENOS의 새 압축 세대와 이번 코드의 조합은 현장 검증 별도다.
적용기는 현장 검색 함수와 consuming 엔진 pin만 변경하고 다른 함수·PIPELINE 설정을 보존한다.
향후 source/좌표 계약 또는 검색 backend 변경은 그 변경 코드와 세대의 별도 호환 확인이 필요하다.

## 코드스페이스 비교 실행 수정 R2

현장 사진에서 R1 BENCH의 ZIP 검증은 통과했지만 `operator_generation`이
`Code-serving settings are not present in this codespace`를 발생시켜 검색 전에 중단했다.
R1은 `~/DEV` 자체 문제가 아니라, 배포 환경의 GENOS_GENERATION/CURRENT 또는 배포 검증
영수증이 코드스페이스에도 있다고 가정한 선택기가 원인이다. 이 실행에서는 비교 수치가 생성되지 않았다.

R1 BENCH 대신 `GENOS_FULLTEXT_LOCATION_20260929_R2_BENCH.txt`를 사용한다.

```bash
bash TRANSFER/GENOS_FULLTEXT_LOCATION_20260929_R2_BENCH.txt
```

현재 작업 폴더의 실제 Git root를 먼저 확인하고 논리 data root, GENOS_DATA,
TERM_RELEASES, AUTHORING와 `/nfs-root/diamo/8-agent/term-releases`의 기존 검색 세대를 확인한다.
기존 명시 GENOS_GENERATION이나 유효한 CURRENT가 있으면 존중하며 없어도 발행/구축된
source/navigation/PeCab fulltext manifest와 DB가 결속된 후보를 확인할 수 있다.
후보 하나면 실행하고 여러 개면 터미널 번호로 명시 선택한다. 임의 최신 폴더를 자동 선택하지 않는다.
다른 mount는 `GENOS_BENCH_DATA_ROOTS=/실제/데이터루트`, 반복 실행은 `GENERATION_INDEX=번호`를 쓸 수 있다.
선택 경로/해시/선택 방식과 변경 감시 proof를 FROZEN_PLAN에 보존하고 실제 코드서빙 선택과 구분한다.

ZIP 내장 TXT 전체를 배포 설정·CURRENT·genos_generation_e2e 스크립트가 없는 모의 checkout에서
실행하여 두 함수의 검색 결과가 같은지, 본문 SQL을 제거하는지, RESULTS.json이 생성되는지 확인했다.
~/DEV→workspace 링크, 복수 후보 선택, CURRENT/manifest 변조, 코드 변경 없음과 패키지 검사를 포함한
관련 17개 계약 검사가 통과했다. 로컬 실행은 성능 수치 인증이 아니며 실제 GENOS 속도는 미확인이다.

R2는 비교 실행기/데이터 선택만 수정했다. R1 검색 수정 함수·행렬·판정 기준 및 기존 적용/원복 패키지는
그대로 보존한다. 모델/HTTP 호출과 데이터/CURRENT/배포 설정 변경 없이 실행한다.

사용자가 제공한 병목 로그 사진을 대조한 뒤, 사용자 지시로 MAIN 작업 코드의
범위 제한 없는 fulltext 위치 구성에 기존 matcher 메타데이터를 연결했다.
새 모델/검색 품질/속도 비교 실험은 실행하지 않았으며 합성 계약·회귀 검사로 확인한다.
현재 Git 브랜치는 `feature/legal_RAG`다. 작업 코드 반영과 Git main 병합,
로컬 활성 frozen 릴리스 교체, GENOS 코드서빙 배포는 별도 상태다.

## 근거와 적용 범위

앞선 상세 요청과 추가 사진의 중복을 제거한 5개 요청에서 본문 SQL 조회는
각각 12,815 / 4,594 / 4,594 / 12,815 / 2,191회였고, 위치 구성 중 캐시 적중은
모두 0회였다. SQL 실행·읽기 누적은 각각 11.117 / 3.979 / 4.510 / 13.618 /
3.179초, JSON 변환은 0.269 / 0.138 / 0.137 / 0.273 / 0.080초였다.
구간 내부 계측은 상위 구간과 합산하지 않는다. 이 관측은 개선 후 성능값이 아니다.
긴 초기 준비 137.67초와 별도 FTS rank 40.18초는 이 수정으로 해소했다고 보고하지 않는다.

위치 구성의 CPU 외 대기가 크므로 파일 접근·SQLite·잠금·GIL·스케줄링 등이
원인 후보다. 디스크/파일 I/O 가능성을 배제하지 않으며 NFS 단독 원인으로 확정하지 않는다.
`thread_read_bytes_delta`는 Linux 블록 I/O 계측이며 NFS 네트워크 읽기량이 아니다.
`fulltext.cached`는 색인 바인딩 재사용이고 본문·검색 결과 캐시 적중이 아니다.

## 기존 실행 경로에 반영

`service.py` → 선택 GENOS generation → v5 세션 →
`workflow_relations_tools.RelationsTools.search(mode=fulltext)` →
`FulltextIndex.rank` → 위치 목록 → 반환 페이지 프리뷰 → READ 순서다.

`navigation_match.ReverseMatcher._build`는 검증된 navigation SQLite에서
source별 ID·문서 ID·조문 ID·표제를 이미 준비하며 세대/색인 결속 캐시가 이를 보존한다.
이 데이터를 같은 요청의 허용 source 집합으로 필터한 FTS 결과의 위치 구성에 사용한다.
별도 실행기, 운영 registry, 새 설정이나 외부 모델 호출은 추가하지 않는다.

- 문서/폴더/전체 범위 검색: `matcher.sources`로 위치를 구성한다. 위치 목록을 만들기
  위해 결과 전체의 `SourceMap` 본문 JSON을 읽지 않는다.
- 조문 내부 범위 검색: 기존 `SourceMap` 본문·블록 범위·형태소 일치 검사를 유지한다.
  범위 밖에만 단어가 있는 source는 반환하지 않는다.
- 페이지/READ: 기존 프리뷰·좌표·본문·span/해시 검증을 유지한다. 검색 프리뷰는
  인용 근거로 승인되지 않으며 READ로 확인한 원문이 기존 근거 소비자에 전달된다.
- 실패: 위치 메타데이터 누락은 오류로 남기고 결과에서 조용히 제외하지 않는다.
  본문/JSON 오류는 실제 본문 검사·페이지 읽기에서 계속 실패한다.
- 요청 전체 deadline: 위치 순회에서도 256건마다 확인해 메타데이터 경로의 시간 제한을
  유지한다. 별도 SQL 제한은 추가하지 않는다.

FTS OR·BM25·동점 순서·허용 범위·위치 중복 제거·정확 total/cursor·출력 계약은 유지한다.
다음 페이지에서 FTS를 다시 실행하는 경로, 본문 범위의 scope 검사, 초기 matcher 구축,
원문 프리뷰/READ I/O는 남는다. 속도 개선이나 응답 전체의 단축 시간을 보장하지 않는다.

## 코드와 데이터 결속

변경 코드: `02_BACKEND/semantic_runtime/legal_agent/workflow_relations_tools.py`.
이 모듈을 pin하는 작업 엔진 manifest 20개와 `00_SYSTEM/PIPELINE.json`의 해당 manifest
hash를 함께 갱신했다. PIPELINE의 비엔진 필드·데이터/모델/프로필은 이전 값과 같다.
기존 데이터 generation·CURRENT·로컬 활성 frozen 릴리스는 변경하지 않는다.
재색인·데이터 재구축·워크플로우 Python 교체가 필요한 변경은 아니다.

변경 전 코드·엔진 manifest·PIPELINE 바이트와 해시는
`90_RUNTIME/diagnostics/fulltext-location-20260929-preimage-002402/inventory.json`에 보존한다.
코드 및 엔진 pin 갱신 영수증은
`90_RUNTIME/diagnostics/fulltext-location-20260929-r1.json`이다.
원복 시 후속 수정 여부를 확인하고 해당 코드와 연결된 pin만 함께 복구한다.
완료된 릴리스·실험·데이터를 덮어쓰지 않는다.

## 검증과 현장 확인

합성 단위 검사는 위치 구성의 본문 SQL 0건, 순위·source 중복·빈 결과·정확 total/cursor,
범위 밖 일치 제외, 조문 내부 본문 검사, 메타데이터 누락·본문 오류, 요청 deadline을 확인한다.
실제 v5 모의 세션에서는 페이지별 본문 적재와 READ 근거의 span/해시 검증을 확인한다.
기존 fulltext 순위·v5·원문·페이지·latency R2 계약 검사도 실행한다.

GENOS 현장 적용·Git push·새 코드서빙 리비전·실제 응답 시간은 별도 미확인이다.
검증한 작업 코드를 현장 checkout에 적용하고 코드/세대 gate를 확인한 뒤 새 코드서빙
리비전으로 배포해야 한다. 현장 확인은 기존 워크플로우 테스트 화면에서 수행한다.
범위 제한 없는 검색의 `fulltext.location.timings`에서 `source_sql_count=0`,
`source_lookup_count=0`과 정확한 결과 수·페이지 이동을 확인한다. 페이지 프리뷰/READ와
조문 내부 검색의 SQL 읽기까지 0건이라고 해석하지 않는다.

최종 검증:

- 변경 경로의 새 계약 검사 13개 통과. 모의 v5의 첫 페이지/다음 페이지는 반환 본문만
  적재하고, READ 근거의 원문 span/해시 검증이 통과했다.
- fulltext 진단·순위·v5·v5 원문·v3 페이지·latency R2를 포함한 관련 검사 159개 통과,
  기존 WARMUP 로그 검사 1개는 제외했다. 최초 전체 실행은 157개 통과/1개 실패였다.
  이후 추가한 deadline 순회·빈 결과 검사 2개를 포함해 최종 관련 묶음을 확인했다.
- 제외한 `test_warmup_prepares_the_same_request_resource_caches`는
  `glossary.file.cached` 이벤트를 기대하며 실패한다. 변경 전 저장 코드로도 같은 실패를
  재현했다. 해당 테스트와 제품 WARMUP 경로는 이번 수정에서 변경하지 않았다.
  저장소 전체 회귀 통과나 WARMUP 성능 확인으로 보고하지 않는다.
- 엔진 manifest 26개의 PIPELINE hash와 변경 모듈을 소비하는 20개의 코드 hash가 일치한다.
  `rehash_engines` 읽기 전용 검사에서 추가 코드/엔진/스키마 변경은 없고,
  기본 경로의 index/fulltext/origin/alias 데이터 pin 6개가 모두 일치한다.
- WSL 환경 검사, 변경 Python 문법, Git whitespace 검사 통과.

이 결과는 로컬 합성 계약 검사이며 실제 내부 데이터 성능·GENOS 배포 인증이 아니다.
# 2026-09-29 현장 인계

필요 부분만 포함한 `GENOS_FULLTEXT_LOCATION_20260929_R1.zip`과 ZIP이 내장된 실행 TXT를
`08_DEPLOYMENT/GENOS/patches/`에 준비했다. 기존 `~/DEV`의 승인된 검색 함수만 교체하며
현장 다른 함수와 설정을 보존하고 기존 pin이 일치할 때만 consuming engine/PIPELINE pin을 갱신한다.
적용·재적용·중단 복구·원복과 실제 v5 모의 검색 비교를 포함한 인계 계약 검사 10개,
위치 구성/계측 검사와 합쳐 32개가 통과했다. GENOS 실제 성능 비교/배포는 미실행이다.

```bash
# 코드 적용과 워크플로우 배포 전에 실행 가능, 모델/API 호출 없음
bash GENOS_FULLTEXT_LOCATION_20260929_R1_BENCH.txt
# ~/DEV에 백업 후 한 함수 적용
MODE=check bash GENOS_FULLTEXT_LOCATION_20260929_R1_APPLY.txt
bash GENOS_FULLTEXT_LOCATION_20260929_R1_APPLY.txt
```

비교는 두 팀과 다섯 검색어, AB/BA 4쌍을 사전 고정한다. 기존 selected profile의 페이지/미리보기 설정을
유지하고 model_binding만 끄며 요청 예산은 두 arm 모두 1800초다. 전체 위치 순서/정확 total/첫 페이지/미리보기
내용을 비교하고 요청별 미리보기·원문 span hash를 검증한다. 결과가 있고 계약이 동일하며 위치 SQL이 0회,
위치 시간 중앙값 20% 이상 감소 및 4쌍 중 3쌍 이상 개선할 때 케이스의 `observed_location_improvement=true`다.
빈 결과와 기준 미달은 개선 미확인이다. OS 캐시는 지우지 않으며 초기 로딩/답변/서빙 지연은 별도다.

현장 `TRANSFER/fulltext-location-20260929-r1/offline-*/`에 FROZEN_PLAN·숫자/해시 결과 JSON과 내부 journal을
보존한다. journal은 외부에 반출하지 않는다. generation/code/팀 scope/검색어 해시를 첫 측정 전에 결속하고
사후 변경은 실패 처리한다. 현장 generation이 실제로 어떤 것인지는 실행 전까지 미확인이다.

commit 이후 `MODE=verify`는 실제 checkout 바이트/commit/selected generation E2E/verify_assets를 검증한다.
Git push와 코드서빙 리비전 배포 및 최종 워크플로우 테스트는 별도다. 워크플로우 Python 변경은 이 패치에 필요 없다.
`MODE=rollback ROLLBACK_FROM=/BACKUP_READY/실제경로`로 원복하며 이후 수정된 파일은 자동 원복을 거부한다.
실행 전체와 실패 상태는 TXT의 시작부터 지속 로그로 남긴다. frozen 비교 설계는 ADR-0549이며 현장 run은 planned다.
