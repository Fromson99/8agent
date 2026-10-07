# 현행 데이터 계약 — 원문과 용어

RAG HTTP 입력의 선택적 `team_id`는 저장된 팀 메타데이터로 문서 ID 범위를 고정한 뒤
기존 `term-runtime-v1` Request의 `document_ids`로 변환한다. 내부 스키마·원문 저장 형식은
유지하며 팀 미지정 자료는 명시 팀 선택에서 제외한다. [선택·이행 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_LEGAL_AGENT_TEAMS.md).

팀별 원문 준비는 [GENOS_TEAM_RAW](../07_DOCS/REFERENCE/OPERATIONS/GENOS_TEAM_RAW.md)를 따른다.
`team-raw-v1`은 기존 구조 원문 SQLite 스키마를 유지하고 `document_metadata`에 팀·전체
상대 경로·파일명·중복 별칭을 추가한다. 팀은 ACL/반출 허용이 아니다. 새 경로와 파생 PDF는
새 구조화 지문이며 기존 구조화/용어 색인/서빙 세대를 갱신하지 않는다. 신규 구조화와
색인 재구축 후 기존 릴리스 절차를 사용한다. `raw-preparation-v1` 영수증은 ZIP → XML MD →
누락 PDF 순서와 원본·파생 해시를 결속한다. XML MD/PDF는 원문 불변층을 대체하지 않는다.

2026-09-15 사용자 지시로 법률 의미 재작성 스키마를 현행 생성·RAG 계약에서 제거했다.
정본: [term-runtime-v1](SCHEMAS/term-runtime-v1.schema.json), [PIPELINE](PIPELINE.json).
용어집 검토만 [GLOSSARY_SCHEMA.json](GLOSSARY_SCHEMA.json)을 사용한다.
이전 의미 계약·원본 레지스트리는 변경 이력이며 신규 산출물의 필수 입력이 아니다.

## 저장과 탐색

문서 표현본 선택은 `structured-primary-pdf-reference-v2`다. 동일 문서의 XML/HTML/HWPX/DOCX가
PDF보다 우선하며 DOC+PDF는 PDF를 사용한다. `document_metadata`의 `file_name`, `relative_path`,
`folder_names`, `display_name`, `aliases`를 원문 SQLite와 RAG 문서 탐색에 보존한다.
`representations`는 원본 위치·전체 해시 목록, `pdf_references`는 참고 PDF의 해시·저장 위치다.
파일명으로 연결된 서로 다른 형식의 내용 일치는 미검증이며 자동 승인하지 않는다.
HWPX 블록의 `native_metadata`에는 XML 위치·스타일·중첩 표 정보를 보존한다.
원본 구조의 표시용 합성 좌표와 참고 PDF 물리 좌표는 별개다. 기존 입력·출력 필드는 유지하며
새 메타데이터가 없는 과거 세대도 읽을 수 있다. [실행 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_NATIVE_PRIMARY.md).

| 산출물 | 필수 내용 | 소비자 |
|---|---|---|
| 구조 원문 SQLite | `document`, `source_unit`, `source_block`: 문서 ID, 상위 마디, 범위, 원문, 원본 해시 | 원문 세대 게시·용어 연결 |
| `term-source-generation-v1` | 위 3개 테이블만 복사, 데이터 상태·반출 설정·실제 문서 범위·입력/출력 해시 | `Store`, 서비스 |
| `term-navigation-index-v4` | v3 + target별 `reference_target`, 비정본 `reference_candidate`; 기존 `reference`·`reference_end` 호환 | 용어·참조 탐색 에이전트 |
| `term-runtime-v1` 요청·응답 | 질문·문서 범위 → query → retrieval → selection → assembly.context → answer | API·단계 엔진·피드백 |
| 피드백 | 실행 파일 해시·답변 ID·query ID·원문 세대 및 해시 | 검토 후보 저장 |
| `navigation-learning-v1` | 검토된 표현→등록 용어 ID, 문서 범위, 탐색 절차·필수 확인 항목, 승인 근거, 원문 세대 manifest 해시 | 명시적 번들 설정 시 기존 NavigationSession에서 사용. [계약·검토·이행](../07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_LEARNING.md) |

새 v4/v5 탐색 색인은 선택 세대의 참조 근거 중복 건수를 `reference_witness_count`에
미리 저장한다. 이 테이블은 읽기 성능을 위한 파생 색인이며 원본 `reference`가 정본이다.
기존 세대에 테이블이 없어도 서빙은 `reference_end`에서 같은 건수를 계산한다.

`query`에는 ID·질문·문서 범위·원문 세대만 있다. 답변의 claim은 선택 원문의 `source_ids`를 가리킨다. API에서 `query_plan`, 카드, `clause_values`, 규칙 조회가 제거되었다. `answer.text`와 `answer.unresolved[].reason`은 유지한다. `/v1/rag/links`는 `source_id`로 들어오고 나가는 원문 참조를 조회한다.

2026-09-27 v5 작업 코드의 최종 검토는 advisory다. `answer.claims`는 최종 작성해
저장한 문장을 포함하며 검토 승인 여부를 뜻하지 않는다. 법률 검토 필요사항은
`answer.unresolved[].reason`과 `answer.text`에 함께 표시한다.
`provider_receipt.final_review_policy=advisory`, `claim_review_status`에 문장별
실제 검토 상태(미완료는 `UNREVIEWED`)를 기록하고 `quality_certified=false`를 유지한다.
기존 object 확장 범위 안의 변경으로 term-runtime-v1·원문 데이터 스키마와 세대는
변경하지 않는다. API·워크플로우·outbox가 같은 최종 답변과 확인사항을 소비한다.

정의는 문서 내 정의 후보의 출처·범위 단서·본문·좌표를 보존한다. 조문 참조는 문자열 span과 원문 해시를 남긴다.
항·호는 구조 역할과 부모가 유일할 때 연결하고, 같은 문서·부모·역할 축의 완전한 범위는 결정론적으로
복수 target으로 확장한다. target마다 source/unit/block 범위를 `reference_target`에 보존한다. 문서·별표·구조가
없거나 판본이 모호하면 DATA_GAP/UNKNOWN으로 남긴다. 폐쇄 후보의 모델 선택은 observation일 뿐이며 운영자 승인
receipt를 거친 결과만 새 navigation 세대에 반영한다. 미승인 후보는 `reference_candidate`에 분리하고
`reference_end` 역참조 정본에 넣지 않는다. 원문에서 제거한 부분을 glue로 재작성하지 않는다.

## 결속과 이행

2026-09-29 신규 공통 용어 generation은 검색 navigation과 구축 감사 원장을 분리한다.
`link_catalogue`, `link_occurrence`, `occurrence_evidence`, `occurrence_origin`은 분리 전
완성 DB snapshot인 `audit/navigation/navigation.sqlite`에 보존하고 검색 DB에서만 제외한다.
nav manifest의 선택적 `storage`와 build `result.navigation_audit`가 감사 manifest SHA를
연결한다. 검색은 generation만 사용하며 작성 측 재개·release/publish는 감사 파일도 검증한다.
승인 참조 overlay는 부모 audit/apply receipt와 새 nav/fulltext SHA를 연결한다.
기존 단일 DB 계약·원문 generation ID·접근/반출 상태는 유지한다.
[이행·실행·소비자·복구](../07_DOCS/REFERENCE/OPERATIONS/NAVIGATION_STORAGE.md).

원문 세대는 `store_sha256`으로 고정한다. 색인은 원문 저장소 해시 및 navigation 필드를 제외한 manifest의 canonical JSON 해시(`source_manifest_sha256`)에 결속한다. 이 방식은 manifest의 navigation 항목이 색인 manifest 해시를 가리킬 때 순환 해시를 피하면서 문서 범위·반출 상태까지 고정한다. 색인 SQLite 자체도 해시로 검증한다.

생성기의 `result.json`은 입력 원문·선택 용어집·생성 코드와 결과를 결속한다. 재개 시 같은 지문과 무결성만 재사용한다. 원문·용어집·관련 코드가 바뀌면 새 run ID가 필요하다. 신규 생성은 의미 추출 및 임베딩을 필수 단계로 요구하지 않는다. 구조 복원 과정의 PDF VLM은 별도다.

기존 세대의 원문 3개 테이블을 새 세대로 복사하고 용어·정의·참조 색인을 다시 만든다. 과거 의미 테이블·authoring queue·projection·완료 ADR을 덮어쓰지 않는다. 새 런타임에 구세대를 직접 넣으면 이행 필요 오류를 낸다. 이전 릴리스는 이전 코드와 데이터로 복구한다.

통합 추가 문서 구축은 [GENOS_DOCUMENT_CONNECTIONS](../07_DOCS/REFERENCE/OPERATIONS/GENOS_DOCUMENT_CONNECTIONS.md)를 따른다. 새 정의 검토는 용어집 observation이며 의미 재작성 단계를 복원하지 않는다. 신규 서빙 세대의 `glossary` 필드는 같은 세대 안의 사전·지식 묶음·캐시 해시를 고정한다.

단계별 구축의 명시 성공분 선택은 기존 `structure-selection-v1`에 선택적 `origin_sha256`를
추가하고 `structure-selection-origin-v1` 감사 기록을 결속한다. 원래 실행의 선택/상태 스냅샷,
완료 문서 ID, 제외 문서·사유, 전체 대비 PARTIAL 범위를 보존한다. 새 선택의 completed는
선택 범위에만 적용한다. 최종 `document-release-v1.structure_coverage`와 복사된 감사 기록도
해시로 연결하며 이전 전체 완료 선택·release는 그대로 읽는다. 원문 SQLite·RAG 계약 변경은 없다.
[단계 계약·재개·이행](../07_DOCS/REFERENCE/OPERATIONS/GENOS_RELEASE_STAGES.md).

### 최소 구조 단위 fulltext 작업 경로 (2026-10-02)

완료된 구조화/navigation에서 `06_TOOLS/pipeline.py fulltext --generation PATH --output NEW_PATH`로 항·호·목 소유 본문만 새 색인에 결속한다. 원본과 연결/navigation을 재구축하지 않는다. 로컬 작업 코드에 연결했으며 GENOS/활성 릴리스는 별도 반입·선택이 필요하다. 입력·스키마·소비자·로그·재개 계약은 [최소 단위 fulltext 안내](../07_DOCS/REFERENCE/OPERATIONS/MINIMUM_UNIT_FULLTEXT_20261002.md)를 따른다.

### 법령별 후보 탐색과 부모 읽기 (2026-10-06 작업 코드)

`law-candidate-navigation-v1`은 소유 본문 색인 위에서 법령 판본/조별 목록을 조회하고 SELECT에서 선택한 부모 subtree와 상위 도입문을 읽는다. 최소 저장 단위와 exact span 인용을 합쳐 재색인하지 않는다. 커서는 색인·검색식·권한 scope·페이지 종류에 결속하고 조사 checkpoint는 질문·코드/프로필·세대와 결속한다. 미해결 REQUIRED 연결도 답변 완료를 허용하되 원문 확보 상태와 경고를 보존한다. [구현/설정/검증](../07_DOCS/REFERENCE/REPORTS/LAW_GROUPED_NAVIGATION_DESIGN_20261006/IMPLEMENTATION.md)을 따른다.
