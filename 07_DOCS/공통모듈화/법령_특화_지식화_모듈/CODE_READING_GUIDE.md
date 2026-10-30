# 법령 특화 지식화 모듈 코드 읽기 가이드

기준 브랜치 `feature/legal_RAG` · 확인한 HEAD `7c17098fc2a96e76964483ae26551cebbbeaf511` · 2026-10-30

모든 경로는 저장소 루트 기준이다. **코드 사본은 제공하지 않는다.** 현재 브랜치에서 아래 파일과 함수명을 검색하면 된다. 줄 번호는 이 기준 커밋에서의 탐색 보조이며 이후 변경 시 함수명이 우선한다.

현재 파이프라인은 코드가 여러 전달 폴더에 나뉘어 있다. R10은 R7의 서비스·파서 정책과 R6의 controller 등을 재사용한다. 폴더 날짜가 오래됐다고 해당 파일을 폐기 코드로 판단하면 안 된다. 아래 'R10 동일'은 봉인 전달본과 파일 바이트가 같은 것을 확인했다는 의미이며 현장 배포 확인을 뜻하지 않는다.

## 1. 먼저 볼 다섯 곳

1. **전체 계산 순서:** `08_DEPLOYMENT/DATAIKU/pipeline_single_cpu_20261029_r10/worker.py` → `stage_commands` 45행, `compute` 88행.
2. **Dataiku 작업과 단계 연결:** `08_DEPLOYMENT/DATAIKU/pipeline_partial_20261028_r6/controller.py` → `structure` 257행, `load` 350행, `execute` 405행. R10 동일.
3. **실제 Oracle 적재:** `08_DEPLOYMENT/DATAIKU/pipeline_layers_20261027_r1/dataiku_run.py` → `load_oracle` 142행. R10 동일.
4. **기존 Oracle 판본부터 벡터 실행:** `08_DEPLOYMENT/DATAIKU/oracle_vector_only_20261029_r1/vector_silver/runtime.py` → `run`.
5. **벡터 구간·게시 알고리즘:** `08_DEPLOYMENT/DATAIKU/oracle_vector_only_20261029_r1/payload/02_BACKEND/semantic_runtime/vector_publish.py` → `segments`, `Publisher.build`, `Publisher.activate`.

이 순서로 읽으면 '어떤 자료가 들어와서 어떤 함수가 실행되고 어디에 저장되는가'를 먼저 이해할 수 있다. 새 통합 runner는 이 다섯 경계 위에 얹는다.

## 2. 호출 경로

```text
Dataiku 레시피
  controller.execute(stage, cfg, work)
    ├─ connection: 계산 코드·파서 설정 HEALTH 확인
    ├─ unpack: 원문 ZIP 검증 및 S3 스냅샷
    ├─ structure
    │   ├─ 입력/대상/코드 binding, ManagedJob
    │   ├─ HEALTH → OPEN → PUT → RUN → POLL/READ
    │   │   └─ service.handle → run_compute → worker.compute
    │   │       ├─ pipeline.py build-data-stages --stage structure
    │   │       ├─ partial_pipeline.select
    │   │       ├─ pipeline.py document-release prepare
    │   │       ├─ pipeline.py document-release reindex
    │   │       └─ worker.export_result
    │   └─ 결과 ZIP·coverage 검증/S3 보존 → CLOSE
    └─ load
        └─ dataiku_run.load_oracle
            ├─ 원문 transfer(run, verify)
            ├─ 자산 publish / verify_assets
            └─ 미리 계산한 query-data.db import_db

별도 벡터 레시피
  vector_silver.runtime.run(action='build')
    ├─ 명시 query_release_id / Snapshot / source.integrity 확인
    └─ vector_silver.publisher.Publisher.build
        ├─ vector_publish.segments → 검증한 원문을 800/700 구간으로 분할
        ├─ 기존 구간 확인 → 누락 구간만 Encoder.encode
        ├─ insert_many → 행/차원/메타 재조회
        └─ READY → query ID에 대한 벡터 게시본 CAS 선택
```

현재 `controller.execute`가 벡터까지 자동 호출하는 것은 아니다. 통합 모듈이 `load`의 query_release_id를 벡터 단계에 넘기는 부분을 새로 연결한다.

## 3. Dataiku 입력과 작업 상태

**파일:** `08_DEPLOYMENT/DATAIKU/pipeline_recipes_20261027_r1/recipes_runtime.py`

읽을 함수: `input_receipts`, `unpack_raw`, `context`, `CheckedClient.call`, `execute`.

- RAW_INPUT.zip/PIPELINE_SUPPORT.zip과 영수증을 선택하고 실제 해시를 확인하는 경계다.
- `unpack_raw`는 승인된 경로의 원문을 Dataiku 관리 폴더에 보존한다.
- `context`는 폴더/입력/DB 연결/계산 코드/서비스 주소를 작업 identity에 묶는다.
- R10에서 이 파일 단독의 옛 `structure/load`를 진입점으로 삼지 않는다. `controller.execute`가 해당 함수를 연결한다.

**연결 변경 근거:** `08_DEPLOYMENT/DATAIKU/pipeline_stateless_20261027_r1/build.py` 44~58행 부근. 입력 선택 어댑터와 controller 호출이 전달 패키지에 어떻게 들어가는지 확인한다. 입력 선택 추가 보완은 `08_DEPLOYMENT/DATAIKU/pipeline_resume_20261027_r3/`와 후속 패키지 조립 기록을 함께 읽는다.

**작업 기록:** `08_DEPLOYMENT/DATAIKU/pipeline_mapped_20261023_r1/src/managed_job.py` → `ManagedJob.__init__`, `save`, `put_blob`, `BudgetClient`. R10 동일. 체크포인트 hash/순서, 결과 ZIP의 내용 주소, 최초 기한과 예약 SQL 사용량을 읽는다.

**상위 controller:** `08_DEPLOYMENT/DATAIKU/pipeline_partial_20261028_r6/controller.py`.

- `open_store` 82행: 기존 기록·기한·대상 결속.
- `transfer_inputs` 166행: raw/support를 1 MiB 조각으로 전송.
- `collect_result` 189행: S3 조각 재사용, 전체 결과 ZIP 해시와 coverage 검증.
- `structure` 257행: 계산 핸들 생성·상태 확인·결과 수신.
- `load` 350행: 검증 결과만 적재하며 이전 구조화를 재실행하지 않음.
- `apply_retry` 237행: 확인된 종료·기한·횟수·model_execution_possible 제한.

## 4. GENOS의 실제 API

**파일:** `08_DEPLOYMENT/DATAIKU/pipeline_skip_parser_20261028_r7/service.py` — R10 동일.

읽을 함수: `handle` 153행, `auth` 136행, `public` 127행, `run_compute` 62행, `resource_check` 51행, `stop_child` 38행.

`API_TYPE`은 HEALTH/OPEN/PUT/RUN/POLL/READ/CANCEL/CLOSE다. 메모리 HANDLES와 계산 수명의 임시 폴더를 사용한다. code_sha256·instance·handle·handle_token의 결속을 확인한다. RUN 중복이 새 계산을 만들지 않는 분기, CANCELLED가 프로세스 종료 확인 뒤 설정되는 분기를 읽는다.

`service(config, data)`의 code=0/data와 code=1/error envelope가 실제 응답이다. R1/R2의 START/UPLOAD/EXECUTE/STATUS/DOWNLOAD/ACK 방식과 혼동하지 않는다.

**전송 무결성:** `08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r3/src/transport.py` → `pack`, `unpack`, `relative`, `checked`. R10 동일. ZIP 내부 TRANSPORT.json, 파일별 해시·크기, 안전한 상대 경로, 심볼릭 링크 거절을 확인한다.

## 5. 구조화와 성공 문서 선택

**실행 순서:** `08_DEPLOYMENT/DATAIKU/pipeline_single_cpu_20261029_r10/worker.py`.

- `stage_commands` 45행: STRUCTURE → PREPARE → INDEX → RETURN. fulltext worker=1.
- `compute` 88행: 입력 ZIP/지원 설정/코드 pin 확인, 격리 workspace, 환경 설정과 단계 호출.
- `export_result` 60행: offline_e2e/serving_verified/coverage 확인, query projection과 감사 파일을 result.zip에 포함.

**고정 정책:** `08_DEPLOYMENT/DATAIKU/pipeline_skip_parser_20261028_r7/parser_config.py` → POLICY, `environment`, `inspect`, `require`. PDF skip, VLM off, 전처리 비활성이 R10에 유지된다.

**엔진 진입:** `06_TOOLS/pipeline.py` → build-data-stages, document-release 분기; `06_TOOLS/COMMANDS/genos_data_stages.py` → `main`; `02_BACKEND/lawrag/pipeline/genos_stages.py` → `execute`, `structure`.

주의: 작업 트리의 `genos_stages.py`는 R10과 다르다. **R10의 skip 모드 추가는 `08_DEPLOYMENT/DATAIKU/pipeline_skip_parser_20261028_r7/build.py` 27행 이후의 패치**를 함께 읽어야 한다. 현재 엔진 본문만 읽고 R10이 PDF를 처리한다고 설명하면 틀린다.

실제 원문 구조 생성의 하위 호출은 genos_stages의 `build.ingest_files`, `build.source_jobs`다. `build`는 `lawrag.pipeline.genos_build`다. 파서/구조 로직을 더 확인할 때 `02_BACKEND/lawrag/pipeline/genos_build.py`와 `02_BACKEND/lawrag/pipeline/genos_doc.py`의 `prepare`를 이어 읽는다. 이번 프로필의 비활성 VLM 코드를 일반 호출 경로에 포함하지 않는다.

**부분 성공 선택:** `08_DEPLOYMENT/DATAIKU/pipeline_skip_parser_20261028_r7/partial_pipeline.py` → `select`, `verify_generation`, `export_paths`.

일반 문서 실패와 무결성 실패를 구분하며 성공 문서 집합과 실제 generation의 document 집합을 대조한다. `pipeline_coverage.py`의 `validate`, `summary`, `read`에서 attempted/selected/omitted의 관계와 audit 파일 hash를 확인한다.

## 6. 용어·탐색·본문 검색 자료 만들기

**파일:** `02_BACKEND/lawrag/pipeline/document_release.py` → `build` 273행, `reindex_prepared` 843행, `main` 899행.

prepare는 검증된 구조 자료와 기존 용어집 기반을 준비하고, reindex는 준비된 입력으로 compact-v2 탐색 자료와 unit fulltext를 만든다. 새 법률 의미를 생성·승인하는 단계와 기존 지식을 재사용하는 색인 단계를 구분한다.

**하위 엔진:** `06_TOOLS/OFFLINE/genos_reindex_only.py` → `prepared`; `06_TOOLS/OFFLINE/genos_reindex_runner.py` → `fork_prepared`, `rebuild`.

**Oracle 조회행 변환:** `02_BACKEND/lawrag/pipeline/oracle_query_publish.py` → `source_records`, `asset_rows`, `describe`; `02_BACKEND/lawrag/pipeline/oracle_query_package.py` → `export`, `verify_db`, `import_db`.

R10에는 바이너리/BLOB 반환·query DB 패키징 후속 수정이 들어 있다. 해당 두 파일의 작업 트리와 차이는 `08_DEPLOYMENT/DATAIKU/pipeline_export_20261028_r8/build.py` 40행 이후 및 R9/R10 build.py에서 추적한다. 새 실행 없이 기존 수정 내역만 확인한다.

## 7. Oracle 적재

**진입:** `08_DEPLOYMENT/DATAIKU/pipeline_layers_20261027_r1/dataiku_run.py` → `load_oracle` 142행. R10 동일.

순서는 원문 transfer(run/verify) → 자산 publish → 실제 자산 재검증 → query-data.db 무결성 대조 → query.import_db다. 이 파일의 `process`, `run_dataiku`에는 옛 원격 프로토콜도 남아 있다. R10은 controller가 `load_oracle`만 재사용하는 경로를 기준으로 읽는다.

하위 코드는 `02_BACKEND/lawrag/pipeline/oracle_migration.py`, `oracle_publish.py`, `oracle_query_package.py`에 있다. 물리명은 `00_SYSTEM/ORACLE/physical_mapping.yaml`, `02_BACKEND/semantic_runtime/physical_mapping.py`와 연결된다. DDL은 사전 준비이며 적재 함수가 테이블 생성·채널 전환을 자동 수행한다고 해석하지 않는다.

## 8. 벡터 생성과 게시

**Dataiku 실행:** `08_DEPLOYMENT/DATAIKU/oracle_vector_only_20261029_r1/vector_silver/runtime.py` → `source_pin`, `Checkpoint.save`, `Checkpoint.sql`, `run`.

`LEGAL_VECTOR_QUERY_RELEASE`로 명시 판본을 선택하고 원문 manifest·권한·모델 endpoint hash를 확인한다. `action='check'`는 임베딩·벡터 적재를 하지 않지만 결과 폴더에 검사 기록을 쓴다. `schema`는 테이블 준비용 별도 기능이며 통합 실행 API에 노출하지 않는다.

**구간 생성·재개·완료:** `08_DEPLOYMENT/DATAIKU/oracle_vector_only_20261029_r1/payload/02_BACKEND/semantic_runtime/vector_publish.py`.

- `segments`: 원문 블록을 직접 읽고 문서·단위·블록·start/end·hash와 묶음.
- `Publisher.existing`: 이미 있는 행의 메타데이터·차원 대조.
- `Publisher.build`: 16개 단위 임베딩, 누락 구간 적재, 전체 count 대조, READY.
- `Publisher.activate`: query ID별 활성 벡터 게시본 CAS 전환.

**실제 SQL 묶음:** `08_DEPLOYMENT/DATAIKU/vector_silver_20261029_r3/vector_silver/publisher.py` → `Publisher.insert_many`. Oracle-only payload와 동일. SQL 크기 상한과 commit/rollback, lease 조건을 읽는다.

**모델 호출·2테이블 reader:** `08_DEPLOYMENT/DATAIKU/oracle_vector_only_20261029_r1/payload/02_BACKEND/semantic_runtime/initial_vector.py` → `profile`, `Encoder.encode`, `Repository.read`, `Repository.active`.

작업 트리의 `02_BACKEND/semantic_runtime/initial_vector.py`는 옛 PBLS/SEG/ACT 3테이블 코드다. 이번 명세는 SET/ITEM 2테이블 전달본을 기준으로 한다. 이 차이는 현재 브랜치에서도 확인할 수 있다.

## 9. 기존 호출과 새 모듈의 연결 지점

| 새 모듈의 책임 | 재사용할 기존 지점 |
|---|---|
| 입력/코드/대상 검증 | recipes_runtime/context, controller/health, physical_mapping/preflight |
| 구조화·색인 | controller.structure → worker.compute |
| Oracle 원문·검색 게시 | controller.load → dataiku_run.load_oracle |
| 벡터 게시 | vector_silver.runtime.run → Publisher.build |
| 전체 결과 | load summary + vector result + coverage를 신규 mapper가 결합 |
| 재개·취소 | 기존 ManagedJob/controller 제약 보존, 적재·벡터 경계 제어 추가 |

새 API의 경로·함수명은 [API 명세서](법령_특화_지식화_모듈_API_명세서.md)에 있다. 위 파일들이 이미 그 REST API를 제공한다고 해석하지 않는다. 코드 위치와 함수 시작 줄은 [SOURCE_MAP.json](SOURCE_MAP.json)에서도 확인할 수 있다.
