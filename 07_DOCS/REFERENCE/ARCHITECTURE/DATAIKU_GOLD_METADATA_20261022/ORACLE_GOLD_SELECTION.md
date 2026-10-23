# 기존 Oracle 테이블의 골드 레이어 선정안

2026-10-22 사용자 요청에 따른 **선정 제안**이다. 기존 Oracle 이관 계약 9개를 현재 작업 코드의 직접 조회 경로와 대조했다. 현장 Oracle 접속·전체 적재 확인, 메타마이너 신청·승인, DBA 생성, MAIN·GENOS 전환은 수행하지 않았다. 아래 물리명과 타입은 저장소의 현재 계약이며 승인된 골드 표준명이라는 뜻이 아니다.

[골드 규약](../../../../00_SYSTEM/ARCHITECTURE.md#dataiku-gold-schema-convention) · [작성 양식](TABLE_SCHEMA_WORKBOOK.md) · [테이블 선정 CSV](ORACLE_GOLD_TABLES.csv) · [현행 46컬럼 CSV](ORACLE_GOLD_COLUMNS.csv)

## 선정 결론

**기존 9개 중 지식 데이터 4개를 1차 골드 등록 후보로, 판본·게시 관리 3개를 지원 테이블 후보로 선정한다.** 합계 7개·36컬럼이다. 지원 3개의 운영 골드 배치는 거버넌스 확인 항목이며, 현재 조회 코드의 의존성은 유지한다. 실행 상태 1개는 에이전트 레이어, 파일 자산 1개는 이관·보관 영역으로 분류한다. 제외는 골드 등록 대상에서의 제외 제안이며 기존 테이블 삭제 지시가 아니다.

원천 스키마는 현재 코드의 `SIDDA`다. 목표 Gold 스키마와 승인 물리명, 과제 에이전트번호, 관리 부서는 미확정이다. `SIDDA`라는 이름이나 `_A` 접미사만으로 현재 Dataiku 레이어를 판정하지 않는다. 아래 `1차/추가 검토`는 이번 제안의 우선순위이며 제공 사진 속 A06 과제의 승인 상태를 가져온 것이 아니다.

| 차수·분류 | 현재 테이블명 (`SIDDA.` 생략) | 업무 용도·선정 이유 | 핵심 컬럼 | 1행 단위·PK |
|---|---|---|---|---|
| 1차·골드 지식 | `LEGAL_SRC_DOCUMENT_A` | 내규·외규 문서와 데이터 세대의 출처 정본 | `DATASET_VERSION`, `DOCUMENT_ID`, `NAME`, `SOURCE_ARTIFACT_SHA256`, `SOURCE_JSON` | 세대 내 문서 1건. PK `(DATASET_VERSION, DOCUMENT_ID)` |
| 1차·골드 지식 | `LEGAL_SRC_SOURCE_UNIT_A` | 문서를 장·절·조·항·호 등 구조로 탐색하고 부모 범위 확인 | `DATASET_VERSION`, `DOCUMENT_ID`, `UNIT_ID`, `PARENT_ID`, `SOURCE_JSON` | 세대·문서 내 구조 단위 1건. PK `(DATASET_VERSION, DOCUMENT_ID, UNIT_ID)` |
| 1차·골드 지식 | `LEGAL_SRC_BLOCK_PAYLOAD_A` | 답변 인용·대사에 필요한 정확한 원문과 원본 해시 | `DATASET_VERSION`, `DOCUMENT_ID`, `BLOCK_ID`, `UNIT_ID`, `TEXT`, `SOURCE_ARTIFACT_SHA256`, `SOURCE_JSON`, `JSON_TEXT_ELIDED` | 세대·문서 내 본문 블록 1건. PK `(DATASET_VERSION, DOCUMENT_ID, BLOCK_ID)` |
| 1차·골드 지식 | `LEGAL_RAG_QUERY_ROW_A` | 문서 탐색·검색, 용어·정의·참조·관계의 조회 투영과 무결성 정보 | `RELEASE_ID`, `KIND`, `ROW_ID`, `DOCUMENT_ID`, `LOOKUP_ID`, `OWNER_ID`, `TARGET_ID`, `ROW_SHA256`, `VALUE_JSON` | 조회 릴리스 내 종류별 행 1건. PK `(RELEASE_ID, KIND, ROW_ID)` |
| 추가 검토·골드 지원 | `LEGAL_RAG_RELEASE_A` | 원문 세대·manifest·기존 자산 게시의 완료 결속. 현재 직접 조회도 읽음 | `RELEASE_ID`, `DATASET_VERSION`, `RELEASE_JSON`, `CREATED_AT` | 원문·자산 완료 릴리스 1건. PK `RELEASE_ID` |
| 추가 검토·골드 지원 | `LEGAL_RAG_QUERY_RELEASE_A` | 어떤 원문 세대와 검색·용어 투영을 함께 사용할지 고정 | `RELEASE_ID`, `MANIFEST_JSON` | 완료 조회 릴리스 1건. PK `RELEASE_ID` |
| 추가 검토·골드 지원 | `LEGAL_RAG_QUERY_ACTIVE_A` | 채널별 게시 버전 선택과 revision 충돌 방지 | `CHANNEL`, `RELEASE_ID`, `REVISION` | 채널별 현재 선택 1건. PK `CHANNEL`; 조회 릴리스 FK |
| 골드 제외 제안·Agent | `LEGAL_RAG_QUERY_STATE_A` | 실행 상태·재개용 JSON과 동시 수정 revision | `SCOPE_HASH`, `STATE_KEY`, `REVISION`, `VALUE_SHA256`, `VALUE_JSON` | 범위별 상태 키 1건. PK `(SCOPE_HASH, STATE_KEY)` |
| 골드 제외 제안·이관/보관 | `LEGAL_RAG_ASSET_PART_A` | 기존 색인 파일 등의 Base64 조각. 직접 지식 조회 대상이 아님 | `ASSET_SHA256`, `PART_NO`, `RAW_BYTES`, `PART_SHA256`, `DATA_B64` | 자산의 분할 조각 1건. PK `(ASSET_SHA256, PART_NO)` |

고정 `DP_QUERY_RELEASE_ID`를 지정하는 모드는 `QUERY_ACTIVE` 조회를 생략할 수 있다. 기본 채널 선택·버전 전환을 지원하는 선정안에는 포함한다. `QUERY_STATE`에는 Oracle CAS 포트가 있지만 현재 `Factory`의 이력 저장 바인딩은 외부 NFS이며, 실제 대화 이력이 이 테이블로 전환되었다는 뜻은 아니다.

`ASSET_PART`는 기존 Dataiku 게시·이관에서 아직 사용한다. 골드 지식에서 제외하더라도 보존·복원 책임과 기존 게시 검사는 유지한다. `RELEASE_A`까지 함께 제외하면 `Snapshot.open()`의 원문 세대 결속이 끊어진다.

## 기존 테이블로 처리하는 범위

현재 서비스는 `service._oracle_factory()` → `oracle_query_service.Factory` → `select_release()` → `Snapshot.open()` → 원문·조회 행 읽기로 연결된다. 기본 채널 모드에서는 `QUERY_ACTIVE`를 읽고, `QUERY_RELEASE.MANIFEST_JSON`의 `source_release_id`로 `RELEASE_A`를 읽어 데이터 세대를 고정한다. 원문은 원문 3개, 검색·용어·관계는 `QUERY_ROW`에서 조건별로 조회한다. 서빙에 전체 데이터를 내려받아 SQLite로 복원하는 경로가 아니다.

`QUERY_ROW`는 **하나의 개념 테이블이나 하나의 관계 테이블이 아니라 여러 논리 조회 데이터를 담는 물리 테이블**이다.

- `source.schema`, `source.integrity`: 원문 논리 스키마와 원문 행 검증 정보.
- `native.*`: 구조 좌표, 원문 소속, 표면형, 정의 요약, 정규화 본문 등.
- `asset_<경로 해시 일부>.<논리 테이블명>`: 해당 릴리스 manifest가 지정한 navigation/fulltext/glossary의 논리 테이블 투영. 실제 포함 종류는 해당 완료 manifest로 확인한다.

따라서 사진의 `CONCEPT`, `CONCEPT_EDGE`, `DOCUMENT`, `CHUNK`, `CHUNK_EMB` 등을 우리 현행 테이블로 단정하거나 동일 이름의 새 테이블을 즉시 만들지 않는다. 원문·구조·용어·정의·참조가 기존 네 테이블과 릴리스 manifest에 어떻게 연결되는지 먼저 등록한다. `QUERY_ROW`의 용어·관계 조회만으로 아래 기업 온톨로지·LLM Wiki 저장까지 완료된 것은 아니다.

## 온톨로지·LLM Wiki 후속 선정

전체 골드 목표에는 원문에 붙는 개념·검토 사항·근거 관계·`llm_wiki`가 필요하다. **위 7개는 현재 원문 RAG 계약의 선정이며 전체 목표 골드 스키마의 완성 목록이 아니다.** 다음은 기존 구현·설계의 재사용 후보이며 현장 생성된 Oracle 테이블로 집계하지 않는다.

| 영역 | 재사용할 기존 논리 테이블·설계 | 선정 범위와 남은 일 |
|---|---|---|
| 업무 개념·검토 지식 | `lk_record`, `lk_head`, `lk_lookup` | Oracle adapter와 DDL 함수가 있다. definition·release·channel 등 지식·게시 내용은 골드 후보. `operation` receipt와 실행 관련 feedback까지 무조건 골드로 옮기지 않도록 namespace별 저장 책임을 정해야 한다. 현재 adapter는 테이블별 매핑이므로 문서 분류만으로 물리 분리가 되지 않는다. |
| 원문·개념·관계의 연결 | 설계 초안 `LK_OBJECT`, `LK_KREV`, `LK_REF`, `LK_EDGE`, `LK_EVIDENCE`, `LK_ENTRY`, `LK_ROUTE_STEP` | 원문 판본·span·개념과 검토 사항의 연결, 관계 끝점, 근거 역할, 원문에서 지식 찾기를 위한 후속 골드 후보. 승인 물리명·표준 매핑·adapter·적재는 후속 작업. |
| 지식 검토·게시 관리 | 설계 초안 `LK_REVIEW`, `LK_CONTROL`, `LK_SCOPE_GATE`, `LK_RELEASE`, `LK_RELEASE_ITEM` | 재사용 지식의 검토·게시 지원 후보. 개별 질문의 에이전트 판단 로그와 구분한다. 운영 배치와 승인 정책 확인 필요. |
| 내규–외규 근거 관계 | `basis_head`, `basis_revision`, `basis_binding`, `basis_lineage` | 기존 관계 정본·판본 대응을 재사용할 골드 후보. Oracle adapter는 있으나 현장 table map은 미확정. `basis_event/receipt/migration/view_head`의 감사·실행·세션 책임은 별도 분류하고 같은 내용의 새 승인 원장을 중복 생성하지 않는다. |
| LLM Wiki | 기존 `sw_*` 중 재사용 지식·근거·검토·수명주기 계약 | 현재 SQLite/artifact 소비자를 Oracle 또는 승인 조회 API로 이행해야 한다. `WIKI_LINK`는 위키 참조이며 위키 본문 저장을 대체하지 않는다. 질문·사실·조사·queue·로그를 포함한 `sw_*` 전체를 골드로 옮기지 않는다. 운영 위키의 물리 테이블명·컬럼은 아직 확정하지 않는다. |

v3 초안의 `LK_RUN`, `LK_CLAIM`, `LK_USE`는 실행 기록이므로 Agent 대상이다. `LK_DEPENDENCY`는 지식 간 의존과 실행 주장 의존이 혼재하므로 소비자 종류별 분리·조회 계약을 정해야 한다. `LK_OUTBOX`, `LK_SYNC`는 처리·동기화 상태다. 설계 초안의 테이블 수를 그대로 골드 신청 수로 사용하지 않는다.

재사용 지식의 기준 키는 **문서 판본 + 조항/span + 개념**이다. 질문 ID는 발견 이력에 연결한다. 다른 질문으로 동일 원문에 도달했을 때 같은 검토 사항을 조회할 수 있어야 한다. 질문별 답변을 복사한 테이블은 이 역할을 충족하지 않는다.

## 등록 준비와 컬럼 보존

CSV는 사진의 활용테이블 목록·Bizmeta·컬럼 정의에 옮겨 적기 위한 초안이다. 현재 9개 전체를 기록해 제외 사유까지 추적하며, 골드 후보 필터를 적용하면 7개·36컬럼이다. 컬럼 순서·타입·길이·PK·NULL은 기존 통합 DDL에서 추출했다. 한글 논리명은 설명용 초안이며 메타마이너 승인 표준용어가 아니다.

1. **스키마·표준 매핑:** 현재 `SIDDA.*_A`와 목표 Gold owner/물리명/표준용어/도메인/인포타입을 매핑한다. 현재 코드는 `SIDDA`와 이름을 사용하므로 스키마나 이름이 바뀌면 조회·게시 코드, 승인된 뷰·매핑 등 실제 접근 경로도 함께 정해야 한다.
2. **타입:** 현행 계약의 `VARCHAR2(... BYTE)`, `CLOB`, `NUMBER`, timestamp를 그대로 적었다. 긴 원문·JSON을 임의 길이 VARCHAR로 바꾸지 않는다. 한글 3바이트 규약, BYTE/CHAR와 실제 데이터 길이, 승인 인포타입을 확인한 뒤 목표 타입을 정한다. 기존 ID·해시·선행 0을 보존한다.
3. **JSON 내부 정보:** 시행일·공개/내부 구분·접근 범위·span 등이 현재 독립 컬럼으로 모두 존재하는 것은 아니다. `SOURCE_JSON`/`VALUE_JSON`/manifest의 현재 계약을 확인하고, 자주 조회할 필드의 독립 컬럼화는 별도 설계·소비자 변경으로 한다. 현행 컬럼 목록에 없는 이름을 기존 컬럼으로 넣지 않는다.
4. **Bizmeta 보완:** 생성시각·관리 부서·보유기간은 미확정으로 둔다. 외규 일일 수집과 내규 업로드 후 처리는 목표 흐름이며 고정 완료 시각이나 운영 실적을 추정하지 않는다. 원문 판본·과거 게시 결과는 보존하며 삭제 기간을 새로 정하지 않는다.
5. **진행 상태:** 선정 → 표준 매핑 → 메타 신청/승인 → DBA 신청/생성 → 적재/조회 확인을 구분한다. 이번 결과는 첫 단계와 현재 계약의 컬럼 목록까지다. 상세 테이블/컬럼 Description의 미확정 항목과 예시 업무 SQL을 보완한 뒤 신청본을 작성한다.

## 확인 근거

- [기존 Oracle 9테이블 DDL](../../../../08_DEPLOYMENT/DATAIKU/legal_oracle_all_tables_20261019_r1/LEGAL_ORACLE_ALL_9_TABLES_20261019_R1.sql): 9테이블·46컬럼, owner·PK·현재 타입.
- [원문 컬럼 계약](../../../../02_BACKEND/semantic_runtime/oracle_dp_io.py), [자산·원문 릴리스](../../../../02_BACKEND/semantic_runtime/oracle_dp_assets.py), [조회 테이블·선택 계약](../../../../02_BACKEND/semantic_runtime/oracle_query_catalog.py).
- [서비스 진입점](../../../../service.py), [Oracle 서비스](../../../../02_BACKEND/semantic_runtime/oracle_query_service.py), [원문 snapshot](../../../../02_BACKEND/semantic_runtime/oracle_query.py), [원문 조회](../../../../02_BACKEND/semantic_runtime/oracle_query_store.py), [용어 조회](../../../../02_BACKEND/semantic_runtime/oracle_query_glossary.py).
- [조회 투영 게시](../../../../02_BACKEND/lawrag/pipeline/oracle_query_publish.py), [구조·정의 투영](../../../../02_BACKEND/lawrag/pipeline/oracle_query_navigation_publish.py).
- [지식 Oracle adapter](../../../../02_BACKEND/lawrag/legal_knowledge/adapters/oracle.py), [근거 관계 Oracle adapter](../../../../02_BACKEND/semantic_runtime/basis_links/oracle.py), [현행 위키 저장 계약](../../../../02_BACKEND/semantic_runtime/legal_agent/shortcut_store.py).
- [원문 중심 저장 기준](../ONTOLOGY_V3/SOURCE_ANCHORED_STORAGE.md), [온톨로지 DB 초안](../../REPORTS/ONTOLOGY_V3_CONTROL_REVIEW_20261022/database/MODEL.md).

확인은 문서·DDL·작업 코드의 정적 대조다. 실제 현장 생성·적재·권한·성능과 선택 릴리스의 Oracle 운영 바인딩을 새로 인증하지 않는다.
