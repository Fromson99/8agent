# 법령 특화 지식화 모듈 API 명세서

버전 1.0 설계안 · 기준일 2026-10-30 · 모듈 식별자 `legal-knowledge-builder`

법령·내규 원문을 문서 구조와 출처 좌표가 있는 지식 데이터로 변환하고, 검색 자료와 벡터를 Oracle에 게시하는 배치 모듈이다. 호출자는 입력 자료와 등록된 실행 프로필을 선택하고, 완료 후 원문 판본·검색 판본·벡터 게시본 ID와 처리 내역을 받는다. 첫 구현 대상은 기존 과제 3·5 파이프라인이다.

**기존 구조화·적재·벡터 코드를 재사용하고, 실행 순서와 입출력만 하나의 계약으로 묶는다.** Dataiku가 작업과 영속 기록을 관리하고 GENOS는 구조화·색인 계산 및 임베딩 계산을 수행한다. 원문·결과 파일은 Dataiku 관리 폴더/S3, 지식 데이터는 Oracle에 둔다.

이 문서의 통합 Python/HTTP API는 신규 어댑터의 구현 명세다. 내부 GENOS 프로토콜과 단계별 함수는 기존 구현이다. HTTP API가 이미 배포되어 있다는 의미가 아니다. 예제의 ID·건수·해시는 모두 설명용이다.

## 1. 범위와 제품 계약

| 항목 | 계약 |
|---|---|
| 표시명 | 법령 특화 지식화 모듈 |
| 핵심 기능 | 원문 검증 → 구조화 → 기존 용어·정의 연결 및 탐색/본문 색인 → Oracle 적재 → 임베딩·벡터 게시 |
| 전체 실행 | `RAW_TO_VECTOR`: 준비된 원문 ZIP부터 벡터 준비까지 |
| 벡터만 실행 | `ORACLE_TO_VECTOR`: 이미 COMPLETE인 검색 판본에서 벡터만 생성 |
| 최초 실행 프로필 | `legal-native-r10-vector2`: R10 구조화와 2테이블 벡터 전달본 |
| 기존 설정 | PDF 파싱·변환·VLM 비활성, 검증된 처리 성공 문서만 후속 단계 진행 |
| 결과 | 지식 판본 ID, 처리/제외 범위, 벡터 게시본, 무결성·게시 상태, 감사 자료 참조 |
| 별도 책임 | 법제처 수집 배치, 새로운 용어 의미 승인, 온톨로지 내용 승인·게시, RAG 질문/답변, 활성 검색 채널 전환 |

이번 모듈은 데이터를 **만드는** 배치 모듈이다. 앞서 논의한 읽기 전용 RDB RAG 조회 모듈과 권한이 다르다. 정상 실행은 Oracle INSERT/UPDATE 및 Dataiku 결과 저장을 수행한다. 테이블 생성은 배포 준비 단계이며 실행 API에서 DDL·DROP·TRUNCATE를 제공하지 않는다. 기존 Dataiku SDK와 계산 엔진 의존성을 재사용하므로 stdlib 전용 모듈로 설명하지 않는다.

기존 `lawrag.legal_knowledge` 및 `/legal-knowledge` 관련 코드는 지식 관리·계획 기능이다. 이름이 비슷하다는 이유로 이번 구축 API가 이미 존재한다고 해석하지 않는다.

## 2. 실행 구조와 책임

```text
호출자 또는 Dataiku 시나리오
  └─ 법령 특화 지식화 모듈: 입력 검증 / 작업 ID / 단계 연결 / 결과 정규화
      ├─ Dataiku: 원문 ZIP·지원 ZIP 검증, 원문 스냅샷, 상태·로그·재개 기록
      ├─ GENOS 계산: 구조화 → 성공 문서 선택 → prepare → reindex → 결과 ZIP
      ├─ Dataiku → Oracle: 원문·자산·조회행 적재 및 재조회 검증
      └─ Dataiku → GENOS 임베딩 → Oracle: 벡터 생성·적재·READY 및 게시본 선택
```

| 단계 | 입력 | 기존 처리 | 출력과 완료 기준 |
|---|---|---|---|
| CHECK | 등록 프로필, 폴더·DB 연결, 원문 영수증 | 코드/파서 지문, 테이블·연결·입력 검사 | 사용할 코드·데이터·대상 고정. 연결 성공만으로 구축 완료가 되지 않음 |
| SNAPSHOT | RAW_INPUT.zip + receipt | `recipes_runtime.unpack_raw` | S3 재조회 해시가 일치하는 원문 스냅샷 |
| STRUCTURE_INDEX | raw/support ZIP | `controller.structure` → GENOS `worker.compute` | 구조화 결과 ZIP, coverage, 제외 문서, 로그. Oracle 쓰기는 아직 없음 |
| LOAD_ORACLE | 검증된 결과 ZIP | `controller.load` → `client.dataiku_run.load_oracle` | 원문 판본과 COMPLETE 검색 판본, 적재 영수증 |
| BUILD_VECTOR | 위 단계의 정확한 `query_release_id` + 모델 프로필 | `vector_silver.runtime.run` → `Publisher.build` | 누락 없는 벡터 게시본 READY, 원문/모델 결속 확인 |
| FINALIZE | 각 단계의 영수증 | 신규 결과 어댑터 | 최종 결과와 처리 범위 저장, 결과 조회 가능 |

GENOS 구조화 서비스는 작업 수명에 한정된 임시 파일과 메모리 핸들을 사용한다. GENOS에 영속 작업 DB를 추가하지 않는다. 임베딩은 기존 임베딩 서비스로 호출하며 구조화 서비스의 OPEN/RUN 프로토콜과 별개다.

## 3. 최소 변경으로 연결하는 방법

외부 계약은 다음 두 함수를 중심으로 한다. 이름과 시그니처는 제안이며 아직 설치 가능한 패키지가 아니다.

```python
build_legal_knowledge(request: dict, runtime: RuntimeBindings) -> dict
resume_legal_knowledge(build_id: str, runtime: RuntimeBindings) -> dict
```

`build_legal_knowledge`는 Dataiku 작업 프로세스 안에서 수행하는 장시간 배치 함수다. HTTP 접수는 작업 ID만 반환하고 Dataiku가 이 함수를 실행한다. 영속 상태·취소·로그는 기존 Dataiku 작업 폴더와 실행 제어를 사용한다.

| 기존 상태와 관측 사실 | 연결 변경 | 원하는 결과와 확인 방법 |
|---|---|---|
| 구조화·적재·벡터가 별도 레시피/함수다. 현재 통합 접수 API는 없음 | 얇은 runner가 기존 단계들을 순서대로 호출 | 한 build ID에서 모든 영수증을 추적할 수 있는지 확인 |
| 벡터 실행은 프로젝트 변수 `LEGAL_VECTOR_QUERY_RELEASE`를 읽음 | 해당 실행에 고정한 변수 사본을 받도록 벡터 진입점을 분리 | 적재 결과 ID와 벡터가 읽은 검색 ID가 같은지 확인 |
| R10은 일부 문서를 제외하고 적재할 수 있음 | 외부 결과에 coverage와 제외 목록을 항상 노출 | 누락이 있는 실행을 전체 완료로 표시하지 않는지 확인 |
| 구조화 작업과 벡터 작업의 기한·예산은 별도 기록 | runner가 양쪽 기존 영수증과 기한을 보존 | 재개가 이전 사용량을 초기화하지 않는지 확인 |
| 작업 트리와 봉인 R10 파일 일부가 다름 | 프로필에 compute/client/vector/mapping 지문을 고정 | 다른 코드나 매핑이면 실행 전 거절되는지 확인 |

기존 구조화와 적재 함수 본문은 유지한다. 변경 지점은 등록 프로필 해석, 단계 runner, 벡터 진입점의 실행별 설정 주입, 결과/상태 변환이다. 기존 `LEGAL_RAG` 프로젝트와 AIDP 연결 제한도 첫 어댑터에서는 유지한다. 프로필 이름이 있다는 이유로 임의 프로젝트·DB를 지원하는 것은 아니다.

벡터 runtime은 환경변수도 설정하므로 작업별 별도 프로세스에서 실행한다. 공유 프로젝트 변수나 프로세스 환경을 동시에 덮어쓰는 구현은 사용하지 않는다. `schema` 작업은 외부 API에 연결하지 않는다.

## 4. 입력 계약

### 4.1 공통 요청

| 필드 | 형식 | 필수 | 의미 |
|---|---|---|---|
| `schema_version` | 문자열, `legal-knowledge-build-v1` | 예 | 외부 입력 계약 버전 |
| `job_name` | 영문·숫자·밑줄·하이픈 1~80자 | 예 | 기존 Dataiku 작업 기록과 연결할 이름 |
| `mode` | `RAW_TO_VECTOR` / `ORACLE_TO_VECTOR` | 예 | 시작 지점 |
| `profile` | `legal-native-r10-vector2` | 예 | 서버에 등록한 코드·매핑·대상·폴더 프로필 |
| `input` | 아래 두 입력 중 하나 | 예 | 원문 자료 또는 완료 검색 판본 |
| `embedding_profile` | 등록 프로필 이름 | 예 | 모델명·불변 revision·차원·endpoint hash 등을 해석하는 키 |
| `coverage_policy` | `allow_verified` / `require_complete` | 예 | 처리 성공 문서만 진행 허용 / 하나라도 제외되면 적재 전 중단 |

`require_complete`는 신규 runner에서 검사할 정책이다. 현재 R10은 `allow_verified`에 해당한다. ORACLE_TO_VECTOR에서는 원본 coverage 영수증을 확인할 수 없는 판본의 범위를 `UNKNOWN`으로 반환한다. 그 경우 `require_complete`는 거절한다. DB의 COMPLETE는 해당 게시본의 완결성이며 최초 업로드 전체 문서가 성공했다는 뜻이 아니다.

인증 사용자가 접근할 수 있는 입력 폴더와 실행 프로필은 서버에서 결정한다. `profile`이나 폴더 ID를 알고 있다는 사실만으로 접근 권한이 생기지 않는다. 요청에 비밀키·비밀번호·임의 SQL·모델 URL·물리 테이블명을 받지 않는다.

### 4.2 RAW_TO_VECTOR

`input.kind="raw_archive"`이며 다음 세 항목을 받는다.

| 필드 | 의미 |
|---|---|
| `landing_folder_id` | 원문·지원 ZIP과 영수증이 보관된 승인된 Dataiku 폴더 |
| `raw` | `{path, receipt_path, sha256, bytes}` 원문 ZIP 참조 |
| `support` | `{path, receipt_path, sha256, bytes}` 기존 용어집·카탈로그 지원 ZIP 참조 |

SHA-256은 소문자 64자리, bytes는 양의 정수다. 현재 GENOS OPEN은 ZIP별 최대 64 GiB를 검사하지만 임시 디스크·메모리·기한 때문에 그 크기의 처리를 보장하지 않는다. 첫 어댑터는 기존 RAW_INPUT.zip/PIPELINE_SUPPORT.zip 및 허용된 단일 `(1)` 복사본 규칙을 유지한다. 승인된 명시 선택 없이 이름이 둘 다 존재하거나 해시가 다르면 임의 선택하지 않는다.

ZIP에는 기존 `legal-pipeline-files-v1` 형식의 `TRANSPORT.json`이 필요하다. 일반 압축 파일을 이름만 바꾸어 보내지 않는다. raw 허용 경로는 `01_DATA/RAW/`, `01_DATA/INPUT_MAPPING/`; support는 `01_DATA/LEXICON/`, `01_DATA/CATALOG/`이다. support의 `metadata.glossary_config_sha256`은 계산 코드의 용어집 설정과 일치해야 한다. 경로 이동·심볼릭 링크·중복 항목·변조는 거절한다.

첫 프로필은 native 처리 가능한 자료를 대상으로 하며 PDF는 파싱 전에 보류한다. 파일 확장자만으로 성공을 보장하지 않는다. legacy DOC도 현재 `genos_doc.prepare`에서 거절한다. 모든 문서가 제외되어 성공 문서가 0이면 적재와 벡터 단계를 시작하지 않는다.

### 4.3 ORACLE_TO_VECTOR

`input.kind="oracle_release"`, `input.query_release_id=<64자리 SHA-256>`를 받는다. 등록 대상 DB에서 검색 manifest가 COMPLETE이고 해시·원문 판본·dataset_version·source.integrity가 일치해야 한다. 최신 날짜의 판본이나 `main`을 자동 선택하지 않는다. 이 모드에서는 원문 압축 해제·구조화·원문 재적재를 하지 않는다.

### 4.4 임베딩 프로필

| 내부 필드 | 현행 계약 |
|---|---|
| `schema_version` | `legal-vector-profile-v1` |
| `model`, `revision` | 비어 있지 않은 모델명과 불변 버전 |
| `dimensions` | 정수 1~4096, 실제 모델 출력과 일치 |
| `endpoint_sha256` | 선택한 HTTPS 임베딩 endpoint의 SHA-256 |
| `chunk_chars`, `overlap_chars` | 각각 800 / 100 |
| `normalization`, `metric` | `l2` / `COSINE` |

현재 구간 생성은 **블록별 본문 최대 800자, 이동 간격 700자**다. 실제 임베딩 입력 앞에는 문서명·조문 제목을 붙인다. 따라서 800은 토큰 수나 최종 입력 전체 길이가 아니다. 끝부분도 포함하고 문서·단위·블록·start/end·원문/입력 hash를 메타데이터에 남긴다. 한 임베딩 요청의 입력은 최대 16개다. 구조화/VLM 비활성과 임베딩 호출 유무를 구분한다.

## 5. 출력 계약

### 5.1 작업 상태

`BuildStatus`는 build_id, job_name, mode, status, stage, created_at, updated_at, progress, result_url, error를 반환한다. 데이터가 아직 없으면 nullable 필드에 null을 사용한다. 과거 성공 건수를 채워 넣지 않는다.

| status | 의미 |
|---|---|
| `QUEUED` | 입력 참조와 작업 접수가 기록됨 |
| `RUNNING` | 현재 단계 수행 중 |
| `SUCCEEDED` | 필요한 단계 완료, 원래 입력 coverage도 COMPLETE |
| `SUCCEEDED_WITH_OMISSIONS` | 허용 정책 아래 일부 문서를 제외하고 나머지 구축 완료 |
| `SUCCEEDED_COVERAGE_UNKNOWN` | 기존 Oracle 판본의 구축은 완료했으나 최초 입력 전체 coverage를 확인할 수 없음 |
| `FAILED` | 확인된 오류로 중단. 이전 완료 단계와 적재 데이터를 유지 |
| `UNKNOWN` | 응답 유실 등으로 실행/커밋 여부가 불명. 자동 새 실행 금지 |
| `CANCEL_REQUESTED` | 취소 요청 기록. 실제 중지 확인 전 |
| `CANCELLED` | 실행 중지 확인. 이미 커밋한 데이터는 삭제하지 않음 |

stage는 `CHECK`, `SNAPSHOT`, `STRUCTURE_INDEX`, `LOAD_ORACLE`, `BUILD_VECTOR`, `FINALIZE` 중 하나다. 진행률은 실제 문서·구간 건수와 관측 단계로 표시한다. 정확한 분모가 없으면 total과 percent를 null로 둔다.

### 5.2 최종 결과

| 필드 | 의미와 출처 |
|---|---|
| `schema_version`, `build_id`, `job_name`, `mode`, `status` | 통합 결과 식별 |
| `releases.dataset_version` | 원문 manifest의 데이터 판본 |
| `releases.source_release_id` | 검증된 원문/자산 게시본 |
| `releases.query_release_id` | 검색·탐색·원문 무결성 행 게시본 |
| `releases.vector_publication_id` | 원문 판본+모델 프로필에 결속된 벡터 게시본 |
| `coverage` | COMPLETE/PARTIAL/UNKNOWN, attempted/selected/omitted/bypassed/failed 건수 |
| `vector` | READY, 실제 구간 수, 재사용 수, 임베딩 호출 수, query ID 기준 활성 여부 |
| `validation` | manifest/행 해시, 적재 재조회, 벡터 메타·차원 검사 결과. 법률 의미 품질은 미인증 |
| `publication` | `query_channel_changed=false`, `vector_active_for_query`, `serving_verified=false` |
| `artifacts` | 원문 스냅샷·결과 ZIP·적재 영수증·coverage/제외 목록·벡터 로그 참조 |
| `warnings` | 일부 제외, coverage 미확인, 서빙 미확인 등 결과에 영향을 주는 사항 |
| `binding` | compute/client/vector/mapping 프로필 지문 |

binding의 hash 기준은 compute=CODE_PINS.json 원본 바이트, client=등록된 Dataiku 클라이언트 ZIP 원본 바이트, vector=등록된 벡터 전달 파일 manifest 원본 바이트, mapping=실행에 사용한 매핑 파일 원본 바이트다. embedding_profile_sha256은 실제 프로필 객체를 UTF-8·키 정렬·공백 없는 JSON으로 직렬화한 SHA-256이며 ensure_ascii=false, allow_nan=false를 사용한다. 기존 DB의 release ID 계산은 각 게시기의 기존 규칙을 그대로 따른다. ORACLE_TO_VECTOR의 미사용 compute/client 지문은 null이다.

건수의 의미를 보존한다. `selected_count + omitted_count = attempted_count`는 알려진 구조화 coverage에서만 검사한다. 벡터 구간 수는 원문 블록 수와 다르다. 재사용 벡터 수를 신규 임베딩 수로 세지 않는다. 조회하지 않은 데이터는 null 또는 UNKNOWN이다.

검색 채널과 벡터의 활성 개념은 다르다. 현재 적재기는 `LGL_SRCH_CHNL_S.main`을 전환하지 않는다. 2테이블 벡터 `Publisher.build()`는 기본적으로 **그 query ID의 벡터 게시본을 활성화**한다. 이 성공만으로 채팅 서빙이 새 검색 판본이나 2테이블 reader를 사용한다고 선언하지 않는다.

최종 결과 API는 성공 상태에서만 200을 반환한다. 실패 또는 진행 중이면 409와 현재 상태 URL을 반환하고, 보존된 부분 산출물은 상태 응답의 진단 정보와 관리 폴더에서 확인한다.

## 6. HTTP API 명세

아래 경로는 통합 어댑터의 신규 계약이다. 실제 주소는 배포 시 등록하며 예제 호스트는 실행 주소가 아니다. 영속 작업 관리 주체는 Dataiku다. 동봉 `openapi.yaml`이 기계 판독 계약이며 문서의 조건부 규칙도 함께 적용한다.

| Method / Path | operationId | 입력 | 정상 출력 |
|---|---|---|---|
| POST `/v1/legal-knowledge/builds` | `createKnowledgeBuild` | BuildRequest + Idempotency-Key | 202 BuildStatus, Location 헤더 |
| GET `/v1/legal-knowledge/builds/{build_id}` | `getKnowledgeBuild` | build_id | 200 BuildStatus |
| GET `/v1/legal-knowledge/builds/{build_id}/result` | `getKnowledgeBuildResult` | build_id | 200 BuildResult |
| POST `/v1/legal-knowledge/builds/{build_id}/resume` | `resumeKnowledgeBuild` | reason + Idempotency-Key | 202 BuildStatus |
| POST `/v1/legal-knowledge/builds/{build_id}/cancel` | `cancelKnowledgeBuild` | reason + Idempotency-Key | 202 BuildStatus |

공통: HTTPS, Bearer 인증, JSON UTF-8. POST Content-Type은 application/json이다. Idempotency-Key는 1~128자 영문·숫자·점·밑줄·콜론·하이픈이다. 인증정보는 응답·로그·산출물에 넣지 않는다. build ID에 대한 조회·재개·취소에도 원래 작업의 소유 범위를 검사한다.

접수 성공 202는 완료가 아니다. 동일 인증 범위·동일 경로·동일 키·동일 정규화 본문이면 같은 작업/제어 응답을 반환한다. 같은 키로 다른 입력이면 409다. job_name이 이미 존재할 때 입력·대상·코드 결속이 다르면 거절하며 실패 우회를 위한 새 작업 생성으로 처리하지 않는다. 키 보관 기간은 작업 기록 보존 기간과 같다. idempotency 기록도 Dataiku에 저장한다.

| HTTP | 의미 |
|---|---|
| 400 | JSON/필수 필드/enum/형식 오류 |
| 401 / 403 | 인증 실패 / 작업·프로필·입력 범위 접근 불가 |
| 404 | 접근 가능한 작업을 찾지 못함 |
| 409 | 중복 키 충돌, 작업 진행 중, 재개 불가, 결과 준비 전, 코드·대상 충돌 |
| 422 | 구조화 0건, 엄격 coverage 위반, 원문/모델/manifest 검증 실패 |
| 429 | 신규 작업 수용 한도. 기존 작업을 복제하지 않고 Retry-After 참고 |
| 503 | Dataiku/Oracle/GENOS 사용 불가. 접수 여부가 불명하면 같은 키로 조회·조정 |

오류 형식은 `{code, message, build_id, stage, recovery, details_ref}`다. `recovery`는 `FIX_INPUT`, `RECONCILE`, `RESUME_SAME_BUILD`, `INSPECT`, `NONE` 중 하나다. 원래 내부 오류는 권한이 있는 감사 기록에 보존하고 공개 message는 자격값이나 원문 전체를 포함하지 않는다.

요청·진행·완료·부분 완료·실패 예제는 [examples](examples/raw_request.json)에 있다. 전체 필드의 필수성·형식은 [OpenAPI](openapi.yaml)를 따른다.

### 6.1 원문부터 벡터까지 요청 예제

아래는 합성 예제이며 등록 프로필·폴더·hash를 실제 값으로 바꿔야 한다. 토큰은 헤더로만 전달한다.

```json
{
  "schema_version": "legal-knowledge-build-v1",
  "job_name": "legal_build_demo_20261030",
  "mode": "RAW_TO_VECTOR",
  "profile": "legal-native-r10-vector2",
  "input": {
    "kind": "raw_archive",
    "landing_folder_id": "EXAMPLE_LANDING",
    "raw": {
      "path": "RAW_INPUT.zip",
      "receipt_path": "RAW_INPUT.zip.receipt.json",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "bytes": 1048576
    },
    "support": {
      "path": "PIPELINE_SUPPORT.zip",
      "receipt_path": "PIPELINE_SUPPORT.zip.receipt.json",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "bytes": 262144
    }
  },
  "embedding_profile": "legal_embedding_registered_v1",
  "coverage_policy": "allow_verified"
}
```

### 6.2 일부 제외 후 완료한 응답 예제

아래는 4개 입력 중 1개를 건너뛴 설명용 결과다. 실제 실행 결과가 아니다. 모든 필드는 동봉 스키마를 만족한다.

```json
{
  "schema_version": "legal-knowledge-result-v1",
  "build_id": "lkb_11111111111111111111111111111111",
  "job_name": "legal_build_demo_20261030",
  "mode": "RAW_TO_VECTOR",
  "status": "SUCCEEDED_WITH_OMISSIONS",
  "releases": {
    "dataset_version": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "source_release_id": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    "query_release_id": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "vector_publication_id": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
  },
  "coverage": {
    "status": "PARTIAL",
    "attempted_count": 4,
    "selected_count": 3,
    "omitted_count": 1,
    "bypassed_count": 1,
    "failed_count": 0
  },
  "vector": {
    "status": "READY",
    "count": 12,
    "reused": 4,
    "embedding_calls": 1,
    "active_for_query": true
  },
  "validation": {
    "source_manifest": "PASS",
    "source_row_hashes": "PASS",
    "oracle_readback": "PASS",
    "vector_metadata_dimensions": "PASS",
    "legal_semantics_certified": false
  },
  "publication": {
    "query_channel_changed": false,
    "vector_active_for_query": true,
    "serving_verified": false
  },
  "artifacts": [
    {
      "kind": "LOAD_RECEIPT",
      "folder_id": "EXAMPLE_LOAD",
      "path": "_pipeline/dataiku-owned-v1/jobs/legal_build_demo_20261030/complete.json",
      "sha256": "1111111111111111111111111111111111111111111111111111111111111111",
      "bytes": 1024
    }
  ],
  "warnings": [
    "RAG_SERVING_NOT_VERIFIED",
    "PDF_BYPASSED_BY_PROFILE"
  ],
  "binding": {
    "compute_code_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
    "client_code_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
    "vector_code_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
    "mapping_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
    "embedding_profile_sha256": "2222222222222222222222222222222222222222222222222222222222222222"
  }
}
```

## 7. 기존 GENOS 계산 API와의 정확한 대응

현행 R10은 **하나의 설정된 URL에 POST하고 `API_TYPE`으로 구분**한다. REST `/builds`를 직접 받지 않는다. 프로토콜은 `dataiku-owned-compute-v1`이다. 구 R1/R2의 START/UPLOAD/EXECUTE/STATUS/DOWNLOAD/ACK 안내를 R10에 적용하지 않는다.

```text
HEALTH → OPEN → PUT(raw/support 반복) → RUN → POLL + READ(log)
       → READ(result 반복) → Dataiku 저장·전체 hash 확인 → CLOSE
실패:  POLL → READ(audit) → Dataiku 감사 저장 → CLOSE
취소:  CANCEL → POLL로 실제 종료 확인
```

| API_TYPE | 요청 필드 | 응답/동작 |
|---|---|---|
| HEALTH | API_TYPE | protocol, instance, code_sha256, chunk_bytes, lease_seconds, preprocessor 설정 |
| OPEN | code_sha256, instance, handle, handle_token, parser_config_sha256, archives, deadline; 선택 max_rss_mb, purpose | 동일 identity면 기존 핸들 반환, 신규면 RECEIVING |
| PUT | 공통 인증 필드 + slot, offset, content, sha256 | 1 MiB 이하 base64 조각 수신. 동일 offset의 동일 바이트 재전송 허용, 다르면 충돌 |
| RUN | 공통 인증 필드 | 입력 수신 완료 후 계산 시작. 같은 핸들의 중복 RUN은 재계산하지 않음 |
| POLL | 공통 인증 필드 | state, phase, error, result/audit, received, log_bytes |
| READ | 공통 인증 필드 + kind(log/result/audit), offset | offset, bytes, sha256, content(base64), total_bytes |
| CANCEL | 공통 인증 필드 | 취소 요청. RUNNING은 감독자가 자식 종료를 확인한 뒤 CANCELLED |
| CLOSE | 공통 인증 필드 + 완료 result_sha256 또는 audit_sha256 | 영수증 대조 후 해당 임시 파일·핸들 정리 |

공통 인증 필드는 `code_sha256`, `instance`, `handle`, `handle_token`이다. controller는 `parser_config_sha256`도 전달한다. handle은 32자리 hex, handle_token은 64자리 hex이며 Dataiku가 생성·보관한다. 외부 통합 API의 인증 토큰과 다른 내부 capability다. 고객용 결과에 노출하지 않는다.

OPEN archives는 `raw`와 `support` 두 키를 가지며 각각 sha256/bytes를 담는다. deadline은 epoch 초, 현재 시각 이후 최대 7일이다. max_rss_mb는 기본/최대 6144, 최소 256이다. R10의 핸들 lease는 900초이며 유효 인증 요청으로 갱신한다. 최대 핸들 4개·동시 RUNNING 1개이며 배포 worker/replica도 1을 전제로 한다. 이는 계산 서비스 코드 제한이며 통합 API의 처리시간 보장이 아니다.

성공 envelope는 `{"code":0,"data":{...}}`, 실패는 `{"code":1,"error":"...","error_type":"..."}`다. HTTP 전송 성공만으로 계산 성공을 판정하지 않는다. 정확한 분기는 [R10과 동일한 service.py](../../../08_DEPLOYMENT/DATAIKU/pipeline_skip_parser_20261028_r7/service.py)와 [controller.py](../../../08_DEPLOYMENT/DATAIKU/pipeline_partial_20261028_r6/controller.py)를 읽는다.

## 8. 저장 모델과 RAG 인계

| 저장 위치 | 주요 자료 |
|---|---|
| Dataiku landing 폴더 | 원본 ZIP·영수증·실행 코드 패키지 |
| Dataiku raw 폴더 | `snapshots/<raw_sha>/manifest.json` 및 원래 파일 |
| Dataiku structured 폴더 | `_pipeline/dataiku-owned-v1/` 아래 작업 체크포인트, 전송 조각, 결과 ZIP, coverage, 실패 감사 |
| Dataiku load 폴더 | 동일 namespace의 적재 체크포인트·영수증 및 `jobs/<job_name>/complete.json` |
| Dataiku vector 결과 폴더 | `/vector/<work_key>/build-state.json`, SQL·시간 기록 |
| Oracle 개발 실버 | 아래 원문·조회·벡터 테이블 |

| 논리 자료 | 첫 어댑터의 물리 대상 |
|---|---|
| 문서 판본 / 구조 단위 / 본문 | SIDDS.LGL_DOC_VER_S / LGL_DOC_UNIT_S / LGL_DOC_BLK_S |
| 자산 조각 / 원문 게시본 | SIDDS.LGL_FILE_PART_S / LGL_SRC_PBLS_S |
| 검색·탐색 행 / 검색 게시본 | SIDDS.LGL_SRCH_ROW_S / LGL_SRCH_PBLS_S |
| 조회 채널 | SIDDS.LGL_SRCH_CHNL_S, 본 구축 API에서 전환하지 않음 |
| 벡터 게시본 / 구간 | SIDDS.LGL_VCTR_SET_S / LGL_VCTR_ITEM_S |

이 목록은 현행 전달본의 대상이다. 실제 현장 테이블·권한·매핑은 preflight로 대조한다. 골드 로컬 연결기 `A8_GR12_CM1208`, `IDD_B03_*`, DTLS_HASH_VALU, VCTR_SCTN_ID의 후속 변경은 별도 프로필이다. 이번 v1에 이미 연결됐다고 표시하지 않는다. 작업 트리의 옛 3테이블 벡터와 전달본의 2테이블 벡터를 혼용하지 않는다.

RAG 인계 최소값은 query_release_id, source_release_id, dataset_version, vector_publication_id, 모델 프로필 지문, 허용 문서 범위다. 소비자는 현재 요청의 판본·권한을 고정한 뒤 실제 원문을 다시 검증한다. 이 모듈이 만든 검색 후보나 벡터 유사도는 법률 판단 결과가 아니다.

## 9. 부분 실패와 재개

| 상황 | 처리와 재개 경계 |
|---|---|
| 이름 중복·원문/ZIP 해시 불일치 | 입력 수정 전 계산·적재 금지 |
| PDF/일부 문서 처리 제외 | coverage와 제외 이유 보존. allow_verified는 성공 문서만, require_complete는 적재 전에 중단 |
| 구조화 성공 0건 | 실패. 빈 지식/벡터 게시본을 성공으로 만들지 않음 |
| 구조화 서비스 재시작 | instance/handle 불일치로 확인. Dataiku 기록 보존; 새 핸들을 자동 만들어 재계산하지 않음 |
| 결과 수신 중단 | 이미 S3에 보존·검증한 조각을 재사용하고 전체 ZIP hash 확인 |
| Oracle 부분 적재 | 동일 입력·대상·기한·영수증으로 적재 단계 재개. 구조화 재실행 불필요 |
| 커밋 후 응답 유실 | UNKNOWN/RECONCILE. DB 재조회로 반영 여부 확인 후 이어감 |
| 벡터 부분 적재 | 같은 query ID·모델·work_key로 기존 행의 metadata/차원 대조, 누락 구간만 처리 |
| 같은 구간의 값 불일치 | 덮어쓰지 않고 실패. 원인과 게시본을 확인 |
| 벡터 활성 CAS 충돌 | 기존 게시본 보호. 최신 active_revision 확인 후 명시적으로 조정 |
| 취소 | 현재 계산 종료/트랜잭션 경계 확인. 이미 적재한 자료 삭제나 게시본 역전환을 취소에 포함하지 않음 |

resume API는 '처음부터 재실행'이 아니다. 확인된 중단점에서 동일 binding을 재검증하고 재개한다. 기존 R10의 계산 재시도는 확인된 종료·횟수·원래 기한·model_execution_possible 제약을 유지한다. RUN 이후 일반 자동 재시작은 지원한다고 약속하지 않는다. UNKNOWN에서는 상태 조정이 먼저다.

취소 API는 이미 종료된 작업이면 그 종료 상태를 그대로 반환한다. resume은 QUEUED/RUNNING/CANCEL_REQUESTED 및 성공 작업에서 409다. FAILED/CANCELLED도 기존 단계가 재개 가능하다고 확인된 경우만 202를 반환하며, 변경된 입력을 같은 build ID에 덮어쓰지 않는다. 재개 시 binding은 서버의 등록 프로필 현재값 대신 해당 작업에 고정한 값을 먼저 확인한다.

기존 코드에는 구조화 취소가 있지만 Oracle 적재·벡터 전체를 아우르는 취소는 없다. 통합 runner는 단계 시작 전과 안전한 배치 경계에 취소 확인을 연결해야 한다. 커밋 여부가 불명확하면 CANCELLED를 확정하지 않는다.

최초 Dataiku 작업의 기한·예약 HTTP/SQL 사용량과 벡터 작업의 별도 7일 기한·SQL/임베딩 사용량을 모두 유지한다. 전체 모듈에도 최초 접수 기준 상한을 적용하며 하위 기한과 비교해 더 이른 시각을 따른다. 새 작업명·체크포인트 삭제로 예산을 초기화하는 기능은 제공하지 않는다.

## 10. 구현 변경 지도

| 추가/연결 대상 | 책임 | 기존 소비자 보존 |
|---|---|---|
| 신규 `legal_knowledge_builder/contracts.py` | 입력/출력·오류·상태 스키마 | 기존 내부 결과는 원본 영수증으로 유지 |
| 신규 `legal_knowledge_builder/runner.py` | 단계 연결·coverage gate·동일 작업 재개 | 기존 structure/load/Publisher 알고리즘 재사용 |
| 신규 `legal_knowledge_builder/adapters/dataiku.py` | 승인된 폴더·프로필·변수 사본·작업 ID 연결 | 기존 LEGAL_00~03과 R4 벡터 레시피를 호출 가능하게 유지 |
| 신규 선택 HTTP 접수부 | 인증·idempotency·Dataiku 작업 실행/조회 | GENOS 계산 서비스에 영속 작업 기능 추가 없음 |
| 벡터 runtime 설정 분리 | 프로젝트 전역변수 대신 실행별 설정 입력 | 기존 `run(cfg, action=...)`는 호환 wrapper로 유지 |
| 결과 정규화 | releases/coverage/validation/artifacts를 하나로 반환 | 기존 stage receipt를 수정하거나 지우지 않음 |

이 표는 제안 파일명이다. 이번 산출물은 명세와 코드 안내이며 제품 모듈을 구현·배포한 것이 아니다. 기존 문서·조회·벡터 스키마 재구축을 요구하지 않는 범위에서 어댑터를 먼저 만든다. 골드 writer 연결이나 PDF/VLM 재도입은 별도 프로필과 검증 범위다.

## 11. 검증과 도입 기준

1. 동일 입력과 고정 프로필로 기존 단계 실행과 통합 runner 실행의 문서/판본/원문·조회행·벡터 메타가 일치해야 한다. 작업 ID 차이가 들어가는 파일 전체 hash를 무조건 동일 기준으로 삼지 않는다.
2. 모든 source/query/vector ID의 연결을 실제 DB에서 재조회하고, 잘못된 원문·모델·매핑 조합을 거절해야 한다.
3. 혼합 입력에서 제외 문서·범위·이유를 보존하고 require_complete가 적재 전에 중단해야 한다.
4. 적재·벡터 중단, 응답 유실, 중복 요청, 동시 작업, 취소, 프로세스 재시작을 확인한다. 모호한 상태에서 자동 새 실행이 없어야 한다.
5. 기존 RAG에 결과 ID를 명시해 후보 조회와 원문 읽기가 되는지 확인한다. 채널 전환과 법률 답변 품질 검증은 별도다.
6. 기존 레시피 경로를 유지한 채 runner만 비활성화할 수 있어야 한다. 원복 시 이미 게시된 지식·벡터·감사 기록을 삭제하지 않는다.

시간·비용 개선치는 산정하지 않는다. 이 작업의 목적은 실행 경계와 관리 단위를 통합하는 것이며 계산량 감소를 약속하지 않는다. 이후 측정은 단계별 wall time·SQL 왕복·임베딩 요청/입력량·신규/재사용 구간·실패 복구 작업량을 같은 입력과 코드 조건에서 비교한다.

## 12. 코드 읽기와 근거

처음 읽을 파일은 [코드 읽기 가이드](CODE_READING_GUIDE.md)다. 현재 feature/legal_RAG 브랜치의 파일 경로·함수명·읽는 순서와 주의할 구버전 함수를 적었다. 코드 사본이나 실행 ZIP은 제공하지 않는다. [SOURCE_MAP.json](SOURCE_MAP.json)에 해당 브랜치 파일의 경로·SHA-256·함수 시작 줄을 기록했다.

구조화 기준은 R10 compute/client ZIP, 벡터 기준은 Oracle-only R1의 2테이블 payload다. 현장 설치·배포 여부를 파일 존재로 확정하지 않는다. 특히 작업 트리의 genos_stages.py와 R10 파일은 PDF skip 처리부터 다르므로 이 문서의 설명을 확인할 때 가이드에 지정한 현재 브랜치 파일과 패키지 조립 패치를 함께 읽는다.

기계 판독 API 형식은 [OpenAPI Specification 3.1.0](https://spec.openapis.org/oas/v3.1.0.html)을 사용한다. 기존 GENOS의 API_TYPE envelope는 이 외부 HTTP 계약과 별도로 위 7절에 명시했다.
