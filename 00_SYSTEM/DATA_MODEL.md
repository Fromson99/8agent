# 현행 데이터 계약 — 원문과 용어

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
| `term-navigation-index-v3` | `term`, `edge`, `source`, `occurrence`, `definition`, `reference` 및 조회 보조 인덱스 | 용어 에이전트 |
| `term-runtime-v1` 요청·응답 | 질문·문서 범위 → query → retrieval → selection → assembly.context → answer | API·단계 엔진·피드백 |
| 피드백 | 실행 파일 해시·답변 ID·query ID·원문 세대 및 해시 | 검토 후보 저장 |
| `navigation-learning-v1` | 검토된 표현→등록 용어 ID, 문서 범위, 탐색 절차·필수 확인 항목, 승인 근거, 원문 세대 manifest 해시 | 명시적 번들 설정 시 기존 NavigationSession에서 사용. [계약·검토·이행](../07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_LEARNING.md) |

`query`에는 ID·질문·문서 범위·원문 세대만 있다. 답변의 claim은 선택 원문의 `source_ids`를 가리킨다. API에서 `query_plan`, 카드, `clause_values`, 규칙 조회가 제거되었다. `answer.text`와 `answer.unresolved[].reason`은 유지한다. `/v1/rag/links`는 `source_id`로 들어오고 나가는 원문 참조를 조회한다.

정의는 문서 내 정의 후보의 출처·범위 단서·본문·좌표를 보존한다. 조문 참조는 문자열 span과 원문 해시를 남기고, 동일 문서 또는 명시한 문서명의 선택 버전에서 유일한 조문 대상을 연결한다. 복수 버전·범위·항/호·모호한 참조는 미확인이다. 원문에서 제거한 부분을 glue로 재작성하지 않는다.

## 결속과 이행

원문 세대는 `store_sha256`으로 고정한다. 색인은 원문 저장소 해시 및 navigation 필드를 제외한 manifest의 canonical JSON 해시(`source_manifest_sha256`)에 결속한다. 이 방식은 manifest의 navigation 항목이 색인 manifest 해시를 가리킬 때 순환 해시를 피하면서 문서 범위·반출 상태까지 고정한다. 색인 SQLite 자체도 해시로 검증한다.

생성기의 `result.json`은 입력 원문·선택 용어집·생성 코드와 결과를 결속한다. 재개 시 같은 지문과 무결성만 재사용한다. 원문·용어집·관련 코드가 바뀌면 새 run ID가 필요하다. 신규 생성은 의미 추출 및 임베딩을 필수 단계로 요구하지 않는다. 구조 복원 과정의 PDF VLM은 별도다.

기존 세대의 원문 3개 테이블을 새 세대로 복사하고 용어·정의·참조 색인을 다시 만든다. 과거 의미 테이블·authoring queue·projection·완료 ADR을 덮어쓰지 않는다. 새 런타임에 구세대를 직접 넣으면 이행 필요 오류를 낸다. 이전 릴리스는 이전 코드와 데이터로 복구한다.

통합 추가 문서 구축은 [GENOS_DOCUMENT_CONNECTIONS](../07_DOCS/REFERENCE/OPERATIONS/GENOS_DOCUMENT_CONNECTIONS.md)를 따른다. 새 정의 검토는 용어집 observation이며 의미 재작성 단계를 복원하지 않는다. 신규 서빙 세대의 `glossary` 필드는 같은 세대 안의 사전·지식 묶음·캐시 해시를 고정한다.
