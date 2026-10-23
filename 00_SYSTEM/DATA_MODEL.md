# 현행 데이터 계약 — 원문과 용어

**Dataiku 저장 레이어 기준(사용자 확인 2026-10-22):** LLM 질의·에이전트 판단·실행 로그는 에이전트 레이어, 구조화 데이터·온톨로지·LLM Wiki는 골드 레이어에 저장한다. 저장 책임과 실제 연동 상태는 [Dataiku 데이터 레이어](ARCHITECTURE.md#dataiku-data-layers)를 따른다.

**골드 스키마 규약(사용자 제공 2026-10-22):** 골드 테이블·컬럼의 명명·타입·길이·메타 등록과 Description은 [골드 레이어 스키마·메타데이터 규약](ARCHITECTURE.md#dataiku-gold-schema-convention)을 따른다. 각 테이블의 행 단위·PK·원천·기간·갱신·산식·주의·오너·예시 질의와 컬럼의 논리명·업무 의미·허용값·산식을 작성한다. 기존 물리 스키마의 준수·이행 여부는 별도 확인 대상이다.

표준단어·금칙어·한글 용어의 `수식어 + 도메인` 구성, 물리명·용어명 30바이트 규약, 유형별 용어·ID 예외·도메인 타입·코드값 표준화와 신청·승인 절차는 [메타마이너 가이드 정리 및 원본 사진](../07_DOCS/REFERENCE/ARCHITECTURE/DATAIKU_GOLD_METADATA_20261022/README.md)을 참조한다. 사진의 예시를 승인된 프로젝트 물리명·타입·코드값으로 간주하지 않는다.

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

2026-10-20 기존 ZIP 입력 R2의 `oracle_legacy_parts`는 사진의 0부터 시작하는 조각과
GNU PARTS/ORIGINAL.sha256을 Dataiku 스트림에서 검증·병합해 기존 ZIP 복원 소비자에 전달한다.
서로 같은 체크섬 복사본은 허용하고 다른 복사본은 명시 선택을 요구한다. 한 조각의 끝1바이트
제외는 조각 원본 SHA와 병합 전체 원본 SHA가 모두 맞을 때만 새 출력에 적용하며 업로드 파일은 보존한다.
큰 조각 읽기 전 목록 검사와 병합 완료 검사를 구분한다. Oracle 이관/중복 정책은 기존과 동일하다.
[옛 조각 실행·복구·중단](../08_DEPLOYMENT/DATAIKU/legal_oracle_existing_zip_20261020_r2/package/GUIDE_UTF8.txt).

2026-10-20 기존 GENOS 데이터 ZIP 직접 입력은 `oracle_existing_zip`이 담당한다.
`genos-rag-data-path-preserving-v1/live-v2`의 명시 generation과 해당 검색 선택표를
파일별 해시/원문·색인 결속 검사 후 복원하고 `oracle-existing-zip-generation-v1` 영수증으로
기존 `oracle_full_package.import_generation`에 연결한다. runtime/옛 실행 코드는 적재하지 않는다.
개발계는 ZIP 직접 입력, 운영계는 `genos-existing-zip-parts-v1`의49MB 조각 검증/병합이다.
동일 원문·자산·조회 키/내용은 유지하고 없는 행만 삽입하며 충돌은 덮어쓰지 않는다.
조회 publisher/선택표가 다르면 새 릴리스가 될 수 있다. ACTIVE/STATE는 별도다.
58개 로컬 검사 통과이며 사용자 실제 ZIP·최신성·현장 Dataiku/Oracle19는 미확인이다.
[직접 ZIP·중복 처리·운영계 분할 안내](../08_DEPLOYMENT/DATAIKU/legal_oracle_existing_zip_20261020_r1/package/GUIDE_UTF8.txt).

2026-10-20 추가본 전달 R2는 같은 `oracle-query-transport-v1`의 논리 행/순서를 유지하면서
FTS 길이를 한 번 집계한 TEMP 기본키 테이블로 조회한다. 새 publisher 코드 해시 때문에
조회 release ID는 달라지며 원문 release ID는 유지한다. 정확한 봉인 R1 코드와 동일 원본의
미완료 작업만 기존 행 전수 대조/최초 기한 보존으로 재개한다. 전달 entry는 `direct_parts=True`로
완성 ZIP 없이 최대49,000,000바이트 조각을 만들고 기존 restore/import 소비자를 사용한다.
새 진행 기록은 확인/추가 행과 SQLite 작업량·자원을 구분한다. 67개 로컬 검사가 통과했으며
현장 대용량/공간 충분성/Dataiku·Oracle19 완료는 미확인이다. 봉인 FULL_PARTS R1은 별도다.
[R2 실행·재개·로그](../08_DEPLOYMENT/DATAIKU/legal_oracle_query_parts_20261020_r2/package/GUIDE_UTF8.txt).

2026-10-20 전체 데이터 반출에는 `oracle-full-generation-transport-v1`을 사용한다.
`lawrag.pipeline.oracle_full_package.export`는 같은 generation의 원문 DB와 선언된 전체
navigation/fulltext/glossary 자산 및 검색 선택표를 원본 바이트 그대로 ZIP/49MB 조각으로
운반한다. Dataiku의 `restore → import_generation(check/publish/status)`는 기존
`oracle_migration.transfer → oracle_publish.publish → oracle_query_publish.publish`를
순서대로 호출하며 원문 전체 행·자산 전체 해시·조회 전체 행/총건수를 대조한다.
완료는 `FULL_DATA_VERIFIED`다. 추가본과 달리 원문5테이블도 포함하며 ACTIVE/STATE·서빙
전환은 별도다. RAW 업로드 파일·다른 세대·runtime 운영 이력은 generation 계약 밖이다.
합성/회귀55검사와 로컬 Oracle23.26 실제 전체SQL1검사 통과, 현장 Dataiku/Oracle19는 미확인이다.
[전체 실행/범위/재개](../08_DEPLOYMENT/DATAIKU/legal_oracle_full_parts_20261020_r1/package/GUIDE_UTF8.txt).

2026-10-20 데이터 운반용 `oracle-query-transport-v1`을 추가했다. 명시된 불변 generation을
`lawrag.pipeline.oracle_query_package.export`가 기존 조회 투영 엔진으로 읽어 `query-data.db`의
`query_row`와 `metadata`에 기록한다. 원문 완료 릴리스 설명자와 조회 manifest/행 순서별 해시를
보존하고 ZIP·49MB 조각의 크기/SHA를 검증한다. Dataiku 소비자 `oracle_query_dataiku.DataikuClient`
→ `oracle_query_package.import_db`는 기존 Oracle 원문 완료 릴리스와 대조 후 추가 QUERY_ROW/RELEASE를
적재한다. 이 SQLite는 이관 입력이며 서빙 로컬 캐시가 아니다. ACTIVE/STATE·기존 원문5테이블·
MAIN 포인터를 변경하지 않는다. [실행/재개/현장 미확인 범위](../08_DEPLOYMENT/DATAIKU/legal_oracle_query_parts_20261020_r1/package/GUIDE_UTF8.txt).

Oracle DP 전환(2026-10-16 작업 코드/GENOS 추가 패치, 현장 검증 전):
`oracle-source-migration-v1`은 compact source-v2의 document/source_unit/block_payload를
SIDDA의 원문 3테이블로 `DATASET_VERSION`(원본 manifest 파일 SHA256)과 함께 이관한다.
`oracle-rag-release-v1` 완료 레코드는 검증된 원문 행의 순서별 해시·건수와 기존 navigation/fulltext/glossary
자산의 파일 SHA256·분할 해시·검색 선택표를 묶는다. Oracle 자료가 정본이며 로컬 SQLite는 재생성 가능한 캐시다.
`oracle-dp-cache-v1`은 원문 행 전체 일치 후 새 SQLite 바이트 해시에 기존 색인 manifest를 다시 결속한
파생 캐시이고 원래 manifest를 `oracle_origin`에 보존한다. 기존 원본/색인 바이트·접근 범위·공개/내부 표시는 유지한다.
불완전 버전/행·자산 변조/설정 변경은 자동 NFS fallback 없이 실패하며, 갱신은 새 DP_RELEASE_ID와 프로세스로 선택한다.
별도 vectors 자산은 이번 형식의 지원 범위 밖이다. [실행·제한](../08_DEPLOYMENT/GENOS/handoffs/oracle_dp_20261016_r1/GUIDE_UTF8.txt).

명명 정의의 증분 보강 계약은 `naming-definition-append-v1`이다. 기존 `definition` 스키마에
원문 span·원본 해시·`EXPLICIT_NAMING_HINT`/`UNRESOLVED`/`canonical_approval=false` 행을 추가하고,
`definition_reference(definition_id, reference_id)`에 기존 참조와의 연결 및 역조회 인덱스를 둔다.
명시 문구와 참조의 결합은 탐색 단서이며 법률상 의미 동일성이나 문서 전체 적용의 승인으로 쓰지 않는다.
기존 원문·참조·정의·전문 색인 행은 보존하고 새 navigation SHA와 부모/추가 원장을 결속한다.
원문 generation ID는 동일하며 갱신본의 경로·navigation/전체 manifest 해시로 버전을 구분한다.
모호하거나 미해소된 관계는 추가 원장의 HELD 사유로 남긴다. 기존 정의/참조 도구를 통해 조회할 수 있지만
일반 검색의 후보 우선순위를 자동 변경하지 않는다. 진입점은 `PIPELINE.json#document_build.incremental_definitions`다.

기존 세대의 파일 버전별 검색 제외는 `filename-search-selection-v1`이다.
`pipeline.py search-selection plan/apply/status/rollback`이 명시적으로 선택한 generation의
메타데이터만 스캔하고, generation 밖 형제 `SEARCH_SELECTION/<디렉터리명>.json`에
generation ID·manifest/store 해시·문서 ID/원문 해시·제외 이유·모호성 보고를 결속한다.
Store/TermIndex의 연결별 TEMP view와 요청 문서 범위가 이를 소비한다. 원본 DB·색인·manifest는
불변이며 FTS/용어 통계는 재계산하지 않는다. 구버전으로 연결되는 참조를 최신본으로 추정 치환하지 않는다.
설정 변경은 캐시를 분리하고 실행 중 재사용을 차단하므로 프로세스를 재시작한다. 설정의 이전/이후
snapshot과 receipt로 원복한다. 같은 폴더·제목의 유효한 8자리 날짜만 비교하며 불명확한 경로·날짜와
다른 위치에서 최신인 공유 문서는 보고 후 보존한다. 새 세대에는 새 계획을 적용한다.
[GENOS 적용·원복](../08_DEPLOYMENT/GENOS/handoffs/search_latest_20261015_r1/GUIDE_UTF8.txt).

문서 표현본 선택은 `structured-primary-pdf-reference-v2`다. 동일 문서의 XML/HTML/HWPX/DOCX가
PDF보다 우선하며 DOC+PDF는 PDF를 사용한다. `document_metadata`의 `file_name`, `relative_path`,
`folder_names`, `display_name`, `aliases`를 원문 SQLite와 RAG 문서 탐색에 보존한다.
`representations`는 원본 위치·전체 해시 목록, `pdf_references`는 참고 PDF의 해시·저장 위치다.
파일명으로 연결된 서로 다른 형식의 내용 일치는 미검증이며 자동 승인하지 않는다.
HWPX 블록의 `native_metadata`에는 XML 위치·스타일·중첩 표 정보를 보존한다.
원본 구조의 표시용 합성 좌표와 참고 PDF 물리 좌표는 별개다. 기존 입력·출력 필드는 유지하며
새 메타데이터가 없는 과거 세대도 읽을 수 있다. [실행 계약](../07_DOCS/REFERENCE/OPERATIONS/GENOS_NATIVE_PRIMARY.md).

선택형 `internal-filename-date-v1`은 내규의 같은 폴더·문서명에서 `(YYYYMMDD)`가 가장 큰
판본을 형식 선택 전에 고른다. `document_metadata.filename_version`에 정책·파일명 날짜·
문서명·미확인 시행일 상태를 보존하며, 제외 판본은 입력 inventory의 해시·사유로 추적한다.
구판을 최신판의 별칭·참고 PDF로 합치지 않는다. 입력 선택 지문이 바뀌면 새 run ID가 필요하다.
구조 원문/RAG 스키마는 유지하며 신규 구조화·연결·색인 세대로 이행한다. 구세대 합병은
재유입 방지를 위해 차단하고 기존 원본·완료 세대는 보존한다. GENOS 선택/배포는 별도다.

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

2026-10-08 로컬 MAIN의 신규 `compact-v2` 구축은 `audit_profile=factorized-v1`을
명시 선택한다. `term-navigation-storage-v4` 감사 DB의 `link_catalogue`와
`link_occurrence`는 검증·확정된 입력 기록이고, 기존 label-match 연결은 독립 ID 사전과
정수 키로 저장한다. `occurrence_evidence`/`occurrence_origin`은 이전과 같은 컬럼·행·
ACCEPTED/HELD 사유를 복원하는 view다. 출현×후보 곱과 출처의 문자열 복사본은 생성하지 않는다.
본문/선택 source/navigation/fulltext의 논리 계약은 유지하며 재개 identity에 audit profile과
재현 코드 SHA를 포함한다. 같은 트랜잭션의 checkpoint·검증·승인 참조 overlay는 v4를 읽는다.
기존 v1/v2/v3 감사와 완료 세대는 보존한다. 이 설정은 로컬 작업 구축의 변경이며 기존
선택 RAG 데이터 및 GENOS 봉인 ZIP/현장 실행을 바꾸지 않는다.

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

### 문서 색인 증분 결합 (2026-10-15 작업 코드)

`document-release append`의 `document-append-v1`은 동일한 용어집·참조 입력·토크나이저를 사용한 compact-v2 원문/navigation과 단위 fulltext의 서로 겹치지 않는 문서 집합을 결합한다. 새 문서만 기존 구조화·용어 연결·색인기로 처리하고, 기존 원문·조문·참조·occurrence·fulltext 토큰 행은 그대로 복사한다. 새 문서의 참조만 전체 문서 목록에서 해석하며 기존 미해결 참조는 소급 변경하지 않는다. 동일 concept의 대표 표기는 기존 값을 유지하고, 새 표기가 동일 concept의 색인 surface임을 확인한 경우에만 추가한다. 다른 충돌은 실패한다.

소비자는 기존 `Store`, `TermIndex`, `UnitFulltextIndex` 및 RAG/워크플로우 원문 도구다. 서빙 스키마는 유지하고 감사 기록은 `append_lineage`로 구분한다. 부모의 전체 구축 감사 기록을 새 세대의 감사 기록으로 위장하지 않는다. 새 `audit/append.json`은 부모 원문·색인 해시와 행 보존 검증을 결속하고, `document-release verify-append --output NEW`가 부모/결과 해시와 서빙 자산을 검증한다. 실패 시 미공개 attempt와 원인을 보존하고 재실행은 새 attempt를 만든다. 완료 출력은 동일 입력에서 재사용하고 변경된 입력·중복 문서·해시 불일치는 중단한다. 활성 포인터 변경은 하지 않는다.


### 공용 근거 관계·승인·판본별 위치 (2026-10-16 로컬 MAIN82)

`basis-link-v1`은 원문에 결속한 내규–외규 관계 후보/승인 revision, `basis-binding-v1`은 generation별 위치, `basis-review-v1`은 명시 검토의 행별 receipt다. 의미 관계의 승인 상태(PROPOSED/APPROVED/REJECTED/REVOKED)와 위치 상태(current/review_needed/unresolved)를 분리한다. 시스템이 승인자·시각·revision·원문 hash를 조립하고 검증하며 LLM 제안은 자동 승인하지 않는다. RELATED/역사적 유래를 현재 근거로 자동 확대하지 않는다.

로컬 저장은 runtime의 `basis-links/authority.sqlite`이며 `basis_head/revision/binding/event/receipt/lineage/migration/view_head`를 사용한다. 코드 선택과 독립하여 과거 원문·승인·판본 대응을 보존한다. 기존 reference_resolution·폐기된 의미 그래프·답변 feedback과 같은 객체로 취급하지 않는다. 현장 Oracle adapter는 명시적 연결·테이블 맵·원문 포트를 받으며 실제 Oracle 저장 검증은 미완료다. [저장·API·개정·복구 계약](../07_DOCS/REFERENCE/OPERATIONS/BASIS_LINK_LIFECYCLE_20261016.txt)을 따른다.
