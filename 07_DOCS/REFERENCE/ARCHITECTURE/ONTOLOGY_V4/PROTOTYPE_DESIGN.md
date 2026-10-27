# 프로토타입 구현 설계

[v4 목차](../ONTOLOGY_V4.md) · [구축 순서](BUILD_PLAN.md) · [지식 축적](CONTROLLED_KNOWLEDGE.md) · [멀티턴](MULTITURN_LEGAL_AGENT.md) · [현재 상태](CURRENT_STATE.md)

2026-10-24 구축 결정과 저장 구조(에이전트 레이어 / S3 JSON / 골드 SQL 적재)에 맞춰 재작성했다. 이전 판은 [HISTORY](HISTORY/20261024_before_build_plan/README.md)에 있다. 아래 파일·모듈·계약은 모두 **구현 계획**이며 아직 만들지 않았다.

## 원칙

- 진입점은 기존 `service.py`의 RAG_ASK → `/v1/rag/ask` → `legal_agent/request_entry.py`다. 별도 멀티턴 챗봇이나 중복 실행기를 만들지 않는다.
- 저장은 세 곳이다: 사용자 로그·LLM 판단은 에이전트 레이어, 온톨로지 작업 JSON은 S3 관리 폴더, 사용하는 온톨로지는 골드. [저장 위치](CONTROLLED_KNOWLEDGE.md#저장-위치).
- RAG 서비스(GENOS 서빙)는 S3를 읽지 않는다. 골드만 Oracle로 조회한다.
- 구현은 [구축 순서](BUILD_PLAN.md#단계)의 단계별로 한다. 운영 반영은 단계 1·2 묶음이 먼저다.

## 새 코드 위치

~~~text
02_BACKEND/lawrag/legal_knowledge/ontology_work/
  store.py        작업 폴더 포트. LocalFolderStore(01_DATA/ONTOLOGY_WORK) / DataikuFolderStore(dataiku.Folder)
  schema.py       스키마 v0와 받아들인 제안으로 JSON 검사
  bundling.py     판단 기록 → 개념 묶음·스키마 제안 (LLM)
  simulation.py   시뮬레이션 다섯 검사
  mapping.py      골드 표 정의 등록·필드 매핑 검사
  load_sql.py     적재 SQL 생성 (Oracle MERGE / 로컬 SQLite upsert)
  gold_reader.py  RAG가 골드에서 적재된 묶음을 조항 anchor로 읽는 포트 (Oracle / 로컬 SQLite)
02_BACKEND/lawrag/pipeline/ontology_work.py
  CLI: pipeline.py ontology-work bundle | simulate | load-sql | load-local | status
00_SYSTEM/SCHEMAS/
  judgment-graph-v1.schema.json
  ontology-bundle-v0.schema.json
  ontology-schema-proposal-v0.schema.json
  ontology-mapping-v0.schema.json
00_SYSTEM/ONTOLOGY_GOLD_MAPPING.json   RAG의 골드 조회용 확정 매핑 (코드 릴리스에 고정)
~~~

`06_TOOLS/pipeline.py`에 기존 하위 명령과 같은 방식으로 `ontology-work`를 추가한다(`lawrag.pipeline.ontology_work.main`). Streamlit은 `ontology_work` 모듈을 직접 import해 쓴다. 단계 3~5에는 새 HTTP API를 만들지 않는다.

## 단계별 변경

### 단계 1: 판단 기록 통합

| 파일 | 변경 |
|---|---|
| `semantic_runtime/legal_agent/read_judgment.py` | 작업 코드의 최신 판을 MAIN 경로에 통합. 통합 전 작업 코드와 MAIN103의 `request_entry.py`·`judgment_view.py`·`PIPELINE.json` 차이를 대조 |
| `unit_relations.py`, `relation_read_policy.py` | 연결 판단(FOLLOW/SKIP/DEFER)과 제시된 미판단 후보에 `judgment_id` 부여 |
| `judgment_view.py` | `judgment-view-v1` → `judgment-graph-v1`. 세 종류 판단 기록, 화면 번호 `J1…`, 항목 한도([멀티턴](MULTITURN_LEGAL_AGENT.md#판단-그래프에-넣는-것)) |
| `unit_reading.py` → `unit_relations.catalog` | 원문 읽기가 끝나면 그 조항을 anchor로 연결 목록을 만들어 판단 그래프의 미판단 후보로 넣음(모델 호출 없음) |
| `06_TOOLS/OFFLINE/cm_shortcut_package.py` | `question_export` 값을 반출 승인에 맞게 변경 |
| `00_SYSTEM/PIPELINE.json` | `bounded_recall.external`의 "internal CM excluded" 문구 변경 |

ID 규칙:
- `judgment_id` = `jg-` + sha256(`session_id`, `goal_id`, 판단 종류, 출발 unit_id, 대상 unit_id 또는 검색어, 판단 순번)의 앞 16자리. 같은 기록이면 다시 만들어도 같다.
- 화면 번호 `J1, J2 …`는 판단 그래프를 만들 때 표시 순서대로 붙인다. 같은 판단도 턴마다 번호가 다를 수 있다.
- `view_hash` = 판단 그래프 JSON(정렬된 키)의 sha256. 그래프를 에이전트 레이어에 저장할 때 함께 저장한다.

발행 계약은 바꾸지 않는다. 턴마다 기존처럼 FINAL로 발행하고, 부분 답은 기존 PARTIAL/LIMITED_ANSWER를 쓴다. `investigation_status=COMPLETED` 표기 변경은 이번 단계 범위가 아니다.

### 단계 2: 재지시·턴 분류

| 파일 | 변경 |
|---|---|
| `memory_methods.py` | `JUDGMENT_OVERRIDE` 추가: `{'action': 'CORRECT', 'stage': None, 'purpose': '판단 기록의 지정 항목을 지시대로 바꿔 다시 판단한다'}`. 시작 단계는 서버가 정한다: READ·FOLLOW → READ, USE·EXCLUDE → ASSESS |
| `corrected_memory.py` | `investigation_hints`의 이전 질문 조회를 `LIMIT 1`에서 같은 세션 최근 10개 질문(goal)으로. 분류 입력에 턴 목록과 최근 판단 그래프. 이전 턴을 고르면 그 턴 그래프로 한 번 더 분류. 재지시 대상 검증과 3개 제한 |
| `completion_execution.py` | 재지시 턴: 대상 연결의 기존 읽기 범위(`required_block_ids` 전체)만 읽고 재평가. 새로 발견한 연결은 따라가지 않고 판단 그래프에 "다음 턴 안내"로만 넣음 |
| 답변 조립 | 첫 줄 분류 표시, 재지시마다 "실행함 / 불가능함(이유)", 초과 지시 목록 |
| 분류 정정 | 사용자가 분류를 바로잡으면 `CASE_START`에 `source_turn`(직전 턴 번호)을 넣어 그 발화를 새 질문으로 다시 처리 |
| `structure_query.py` | `READ_NAMED`: 사용자가 말한 문서·조문을 기존 정확한 조문 조회(`_resolve`)로 찾음. 요청 범위에서 하나일 때만 읽고, 여럿이면 되물음 |

### 단계 3: 스키마 v0·작업 폴더

- `store.py`: `get(path)`, `put_new(path, bytes)`(이미 있으면 실패), `put_head(path, expected_revision, revision)`, `list(prefix)`. Dataiku 구현은 `dataiku.Folder("LEGAL_ONTOLOGY_WORK", project_key="LEGAL_RAG")`의 `get_download_stream`·`upload_stream`·`list_paths_in_partition`을 쓰고 `get_path()`는 쓰지 않는다.
- `schema.py`: `ontology-bundle-v0.schema.json` 검사 + 받아들인 제안 필드 허용 + 연결 타입 14종·역할 7종(`DEFINITION`…`EFFECT`)·비교 5종 검사.
- `simulation.py`: [검사](CONTROLLED_KNOWLEDGE.md#시뮬레이션) 중 형식·원문 결속·근거 결속·골드 규약 네 가지. 재생 검사는 단계 6 경로 조립기가 생긴 뒤 연결한다. 모델 호출 없음.

### 단계 4: 판단 모음·승인

- `bundling.py`: [개념 묶음 작업](CONTROLLED_KNOWLEDGE.md#개념-묶음-작업) 규칙대로 에이전트 레이어 판단 기록을 읽어 S3에 묶음·제안을 쓴다.
- Streamlit([site_design_app.py](../../../../03_FRONTEND/APPS/legal-knowledge-streamlit/site_design_app.py) 확장) 화면: 묶음 목록(상태별) → 묶음 상세(근거 판단·원문 펼침) → 승인·수정·쪼개기·합치기·반려·보류. 제안 스키마 목록 → 받아들임·거절. 모든 동작은 새 revision 파일 + `HEAD.json` 갱신.

### 단계 5: 골드 매핑·적재

- `mapping.py`: 골드 표 정의(표 이름, 컬럼 이름·타입·길이·NULL 여부) 등록, JSON 필드 ↔ 컬럼 매핑, 타입·길이·30바이트 규칙 검사.
- `load_sql.py`: `MAPPED` 묶음에서 Oracle `MERGE`와 로컬 SQLite `INSERT … ON CONFLICT DO UPDATE`를 같은 매핑으로 생성해 `loads/<load_id>/load.sql`에 저장.
- `pipeline.py ontology-work load-local`: 로컬 골드 SQLite에 표 정의대로 표를 만들고 적재 SQL을 실행한 뒤 실행 기록을 쓴다(현장의 신청·생성·실행을 로컬에서 대신).
- 확정된 매핑을 `00_SYSTEM/ONTOLOGY_GOLD_MAPPING.json`으로 내보내 코드 릴리스에 고정한다.
- `gold_reader.py`: `read_by_anchor(unit_ids) → 적재된 묶음 목록`. 로컬은 로컬 골드 SQLite, GENOS는 Oracle. 설정 `PIPELINE.json`의 새 키 `ontology_work.gold_read`(`off` / `on`, 기본 `off`).

### 단계 6~8

- 단계 6: [조문 진입](SOURCE_ENTRY_COMPOSITION.md). 지식은 `gold_reader`로 읽는다. 기존 `knowledge_bridge.prepare/augment`의 연결 지점은 쓰되, 그 안의 `legal_knowledge.Service.plan` 대신 `gold_reader`를 부른다.
- 단계 7: `case_repository.py`의 저장 포트를 로컬 SQLite / 에이전트 레이어 Oracle로 나누고, `DataikuFolderStore`와 Streamlit을 Dataiku에 배포한다. 개념 묶음 작업은 Dataiku에서 GENOS 내부 LLM을 호출한다(호출 가능, 2026-10-24 사용자 확인). 에이전트 레이어 표 정의서는 [골드 메타 규약](../DATAIKU_GOLD_METADATA_20261022/README.md)의 이름·타입 규칙으로 작성한다.
- 단계 8: [컴파일과 시나리오](COMPILATION_AND_SCENARIOS.md). 시나리오 입력·결과는 사용자 작업 기록이므로 에이전트 레이어에 둔다.

## 계약 목록

| 계약 | 만드는 쪽 | 쓰는 쪽 | 저장 |
|---|---|---|---|
| `judgment-graph-v1` | `judgment_view` | 화면, 턴 분류, 재지시 검증, 개념 묶음 작업 | 에이전트 레이어 |
| `JUDGMENT_OVERRIDE` 명령 | 턴 분류 LLM(화면 번호 선택) → 서버가 ID 결속 | `corrected_memory`, `completion_execution` | 에이전트 레이어 |
| `ontology-bundle-v0` | `bundling`, Streamlit | 시뮬레이션, 매핑, 적재 SQL | S3 |
| `ontology-schema-proposal-v0` | `bundling` | Streamlit, `schema` | S3 |
| `ontology-simulation-v0` | `simulation` | Streamlit | S3 |
| `ontology-mapping-v0` | Streamlit(매핑 화면) | `load_sql`, `ONTOLOGY_GOLD_MAPPING.json` | S3, 확정분은 코드 릴리스 |
| `ontology-load-receipt-v0` | 사람(실행 기록 등록) / `load-local` | Streamlit(`LOADED` 전환) | S3 |

## 기존 기능의 처리

| 기존 기능 | 처리 |
|---|---|
| `legal_knowledge` 저장소(`lk_record`·`lk_head`·`lk_lookup`), 초안·검토·게시, 관리 router·viewer | v4 경로에서 쓰지 않는다. 설정 `management_enabled=false`, `consumer_mode=off` 그대로 둔다. 계약 검사 함수만 재사용할 수 있다 |
| `knowledge_bridge` | 단계 6에서 연결 지점만 재사용하고 조회 대상을 `gold_reader`로 바꾼다 |
| `basis_links` | 내규–외규 연결의 정본으로 유지. v4 묶음은 필요하면 그 ID를 참조만 한다 |
| `ontology.evaluate` | 단계 8에서 재사용. `min` 연산은 없으므로 필요하면 연산 추가를 별도 검토 |
| 기존 발행 계약(`result_port`·`publication`) | 단계 1·2에서는 그대로 쓴다 |

## 검사

각 단계의 완료 조건은 [구축 순서](BUILD_PLAN.md#단계), 시나리오별 검사는 [멀티턴 확인 시나리오](MULTITURN_LEGAL_AGENT.md#확인할-시나리오)와 [검증과 도입](VALIDATION_AND_ROLLOUT.md)에 있다. 최소 한 검사는 실제 `/v1/rag/ask` 또는 `service.py` 진입점으로 한다. 함수별 모의 검사만으로 연결 완료로 보지 않는다.
