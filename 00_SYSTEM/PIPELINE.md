# 파이프라인 중심 SSOT

**시스템의 조립 정본은 `00_SYSTEM/PIPELINE.json`이다.** 엔진은 파이프라인의 명시적
입출력 계약을 구현하는 교체 부품이다. 엔진이 자신만의 데이터 정본·기본 pipeline·
모델 정책을 다시 소유하지 않는다. 실행기는 `06_TOOLS/pipeline.py` 하나로 진입한다.

**일상 표현·용어·조문·연결 조문 검색도 이 통합 파이프라인의 일부다.** `legal-rag`의
`retrieve → select → assemble → answer`에서 공식 용어 연결을 기존 검색 후보에 합친다.
선택된 조문 원문과 기존 Rule/Proviso/LegalRelation 연결은 같은 조립 단계에서 처리한다.
선택기·답변기·provider를 공동으로 사용하며, 용어 연결에 별도 LLM을 호출하지 않는다.

2026-09-11 로컬 generation 11에 [공식 API 관계의 RAG 소비](../07_DOCS/REFERENCE/RAG/MOLEG_LINKS_RAG_WIRING.md)를 적용했다.
기존 [최신 법령 선택](../07_DOCS/REFERENCE/RAG/LATEST_LAWS_AND_API_LINKS.md)의 159문서와 원문·벡터는 유지한다.
현재 색인은 일상표현 3개에서 수집한 허용 관계 7개를 소비한다. 미수집 용어의 관계를 만들어내지 않는다.
[ADR-0361 계약](../07_DOCS/REFERENCE/RAG/UNIFIED_TERM_ARTICLE_PIPELINE.md)의 별도 명시참조 후보 전체가
이 릴리스에 승격된 것은 아니다. 법률 정답률·실모델 성능 평가는 이번 배선 검증 범위 밖이다.

## 1. 소유권과 저장 위치

| 무엇 | 유일한 소유자 | 위치/경계 |
|---|---|---|
| 단계/DAG/슬롯/엔진 선택 | Pipeline | `00_SYSTEM/PIPELINE.json` |
| 법률 엔티티/역할/조건/효과 | Legal schema registry | `00_SYSTEM/LEGAL_SCHEMA.json` → 단일 schema |
| 원문/구조/패키지/보안 | DatasetPackage/SourceSet | `01_DATA`; pipeline에는 버전·hash 참조 |
| 엔진 코드와 포트/매개변수 | 버전 고정 engine manifest | `02_BACKEND/ENGINES/<name>/<version>/` |
| 공통 계획/검증/실행/영수증 | Engine host | `02_BACKEND/PIPELINE/engine_host.py` |
| 실험 목적/비교/결과 | ADR | `04_EXPERIMENTS/ADR/ADR-...` |
| 실험 엔진 코드 | 동결 후보 | `02_BACKEND/lawrag/research/candidates/adr_.../` |
| 실험 파생 데이터 | ADR 소유 staging | `09_ARTIFACTS/STAGING/ADR-.../` |
| 실행 선택의 최종 권위 | Release/ACTIVE | 기존 receipt-bound activation 계약 |
| 모델 역할/허용 모델 | 기존 모델 정책 | ADR STANDARD의 모델 정책; 엔진의 별도 override 금지 |
| 질문 피드백 | 세대/정본 ID를 가리키는 제안 | SSOT FEEDBACK; 원문/정본 직접 덮어쓰기 금지 |

SSOT는 모든 데이터를 한 파일에 넣는다는 뜻이 아니다. **각 책임에 하나의 정본만 있고,
상위 pipeline이 그 정본을 참조**한다. 예시는 examples, 검증 출력은 run artifact로 구분한다.
기존 완료 ADR와 receipt-bound 세대는 역사 기록이다. 정리를 이유로 이동/수정하지 않는다.

## 2. 표준 파이프라인

```text
legal-authoring
  structure → EXTRACTOR → OBSERVATION → COMPILER(admission) → CANONICAL → INDEXER

legal-rag
  QUERY_PLAN + INDEX → RETRIEVER → hits
  hits + QUERY_PLAN + CANONICAL + TEMPLATE → ASSEMBLER → RULE_BUNDLE
  QUERY_PLAN + RULE_BUNDLE → ANSWERER

legal-feedback
  answer + CANONICAL → FEEDBACK engine → 수정 제안
  승인된 제안 → 새 observation / 재컴파일 작업
```

QUERY_PLAN은 질문 분석 결과다. 질문 분석 자체를 바꾸려면 QUERY_PLANNER 종류의 엔진/입력
계약/노드를 명시적으로 추가한다. 현재 legal-rag profile은 이미 생성된 QUERY_PLAN을 입력으로
받는다. 다중 카드 fan-out/통합 답변 정책은 assembler 계약 확장과 전용 검증을 거쳐야 한다.
이번 공통 host는 법률 판단/LLM provider/승인 서비스의 대체 구현이 아니다.

각 노드는 고정된 `slot`, 선택한 `engine`, 포트별 `bindings`, 검증되는 `parameters`를 갖는다.
엔진은 `run(inputs, parameters, context) -> {output_port: value}`를 구현한다.
입력/출력은 JSON artifact이며 계약 이름과 schema hash에 결속한다.
미등록 엔진 자동 탐색, 환경변수 기반 숨은 fallback, 엔진 내부의 암묵적 schema 변환은 없다.

## 3. 무엇을 바꾸느냐에 따른 관리

| 변경 종류 | 변경할 것 | 필요한 검증/새로 만들 것 |
|---|---|---|
| 의미 스키마 | schema + registry revision/hash + 명시적 MIGRATOR | ID/crosswalk, 조건/효과 보존, 미해결 기록, 영향받은 canonical/index/card 재생성 |
| LLM 추출 | EXTRACTOR engine version | 같은 OBSERVATION 계약, 원문 근거, 의미 품질 평가 |
| 정규화·승인 | COMPILER engine version | 입력/검토 영수증, 동일 의미 보존, canonical generation |
| BM25/vector/hybrid 회수 | RETRIEVER engine version | 같은 hits 계약이면 연결 유지, recall/회귀/비용 평가 |
| 카드 조립 | ASSEMBLER engine version + recipe | Rule/Proviso/Relation 근거와 누락, 다중 카드 회귀 |
| 답변 모델/prompt | ANSWERER engine version | 기존 모델 정책, 인용과 답변 회귀 |
| 피드백 | FEEDBACK engine version | exact generation/target/field 추적, 승인 후 재컴파일 |

같은 slot의 입력/출력이 같으면 선택한 엔진만 교체한다. 달라지면 교체 요청은 실패한다.
그때는 **MIGRATOR 노드를 pipeline DAG에 직접 추가**한다. migration manifest는 from/to와
LOSSLESS/CANDIDATE_WITH_UNRESOLVED/REJECT_LOSS를 기록한다. 자동 변환 경로를 추정하지 않는다.
실행기는 선언된 포트와 데이터 shape를 검사한다. 의미 보존/무손실 선언의 진위는 별도
도메인 검증 대상이다. 선언만으로 데이터 migration 성공으로 처리하지 않는다.

## 4. 엔진 등록과 실험 격리

엔진 manifest에는 ID/version/kind, input/output contracts, parameters_schema,
entrypoint, 실행 파일 전체 hash를 넣는다. 엔진 ID는 버전을 포함해야 한다.
PIPELINE.json.engines에 manifest의 경로/hash를 명시해 등록한다.
실행 때 manifest와 파일 hash를 재검증한다. 같은 버전 디렉터리의 완성 엔진을 덮어쓰지 않는다.

- TOOL: 오프라인 계약 감사와 원문 보존·관측 이관 도구. 이관 출력은 SHADOW/CANDIDATE로 제한하며, 법률 의미의 신규 추론·canonical 승인·제품 답변·운영 활성화를 수행하지 않는다.
- RESEARCH: 후보 공간에만 존재. exact candidate/revision/experiment manifest hash와 arm/run 필수.
- RELEASED: 검토된 엔진 공간. 운영 선택은 별도 release receipt와 활성화가 필요하다.

research 모드에서만 RESEARCH를 선택할 수 있다. 운영/도구 profile에 연구 경로를 숨겨 넣으면
검사에 실패한다. 파일 hash는 코드 identity이며 보안 sandbox가 아니다. 등록 코드는 검토된
신뢰 코드여야 한다. 임의 코드를 등록해 안전하게 실행할 수 있다는 의미가 아니다.

## 5. 실행과 영수증

### 명시적 오프라인 데이터 구축

완료 용어집 ZIP을 반입해 GENOS의 기존 LLM·임베딩 API와 SQLite로 단일 세대를 만드는 호환 명령은
`bash 06_TOOLS/genos_pipeline.sh` 또는 `06_TOOLS/pipeline.py build-all-legacy`다.
용어집 → 원문 구조화 → 기존 의미 추출/검토 → 임베딩 → 공식 관계 연결 → 기존 RAG용 세대까지 이어진다.
실행·재개·현재 최적화의 범위: [GENOS 단일 명령](../07_DOCS/REFERENCE/OPERATIONS/GENOS_GLOSSARY_SINGLE_COMMAND.md).
이는 명시적인 데이터 명령이며 로컬 MAIN/고정 engine manifest를 자동 승격하지 않는다.

현재 공통 `06_TOOLS/pipeline.py build-all`은 유지되는 단위 명령을 합성한다:
`glossary review complete` → 완료 초안 영수증 검증 → `build-data-stages --stage all`.
용어 작업이 대기 중이면 exit 3으로 멈추고 문서 작성에 이전 초안을 사용하지 않는다.
이 명령의 범위는 구조/의미/벡터 DRAFT까지이며 통합 RAG 세대와 피드백 루프는 별도다.
[용어 검토 합성 운영법](../07_DOCS/REFERENCE/OPERATIONS/GLOSSARY_ALIGNMENT.md).

`06_TOOLS/pipeline.py build-data`는 GENOS 데이터 wrapper와 **같은** 오프라인 적재 경로다.
`--extraction-mode staged`를 주면 개념·근거 → 절·역할 → 규칙·단서·관계 → 커버리지를
각각 실제 모델 호출로 저장하고 병합·전체 계약/근거 검증·독립 리뷰 후 DRAFT로 적재한다.
`--extraction-mode single`은 기존 단일 추출 경로다. 기본은 기존 single이며 단계별 추출은 명시한다.
이 명령은 engine-host의 `legal-authoring` 미이행 슬롯을 채우거나 승인/MAIN 활성화하지 않는다.
데이터 명령의 code/source/schema/options 해시는 batch-plan과 queue identity에 고정한다.
GENOS provider 설정은 기존 환경변수를 사용한다. [설치·실행](../07_DOCS/REFERENCE/OPERATIONS/GENOS_STAGED_AUTHORING.md).

```bash
.venv/bin/python 06_TOOLS/pipeline.py build-data --run-id external-staged-001 --exclude-internal --extraction-mode staged --check-only
```

### 등록 엔진 실행

```bash
.venv/bin/python -B 06_TOOLS/pipeline.py check
.venv/bin/python -B 06_TOOLS/pipeline.py plan --profile semantic-contract-check
.venv/bin/python -B 06_TOOLS/pipeline.py plan --profile semantic-contract-check \
  --engine validate=semantic-contract-audit@1.0.0
.venv/bin/python -B 06_TOOLS/pipeline.py run --profile semantic-contract-check \
  --inputs /absolute/path/input-artifacts.json --output /absolute/path/new-run
```

input-artifacts.json은 `{port: {path, sha256}}`이며 입력을 실행 전 검증한다.
새 실행 디렉터리는 원자적으로 선점하며 기존 run을 덮어쓰지 않는다. 엔진별 출력 artifact,
contract, 선택 엔진/manifest hash, 실제 config hash, 시작/종료, 실패 사유를 receipt.json에 남긴다.
COMPLETE는 명령 실행 완료이고 법률 데이터 승인이나 운영 승격이 아니다.

## 6. 현재 이행 상태 — 숨기지 않는다

**구현됨:** 단일 의미 계약, pipeline/engine manifest, DAG/port/parameter 검증, 엔진 교체,
명시적 migration stage 실행, 연구 namespace 차단, 파일 hash 검증, 성공/실패 영수증, CI.
실행 가능한 도구 profile은 `semantic-contract-check`와 `legal-semantic-migration`이다.
후자는 `legacy.shadow → MIGRATOR → semantic.store`를 명시하고 전수 보존·원문 검증·crosswalk·
미해결 목록·재추출 작업을 생성한다. 실제 저장소는 `01_DATA/SEMANTIC/GENERATIONS`에 있고,
현재 descriptor/hash는 LEGAL_SCHEMA registry가 참조한다. SHADOW 출력은 운영 승격이 아니다.

**아직 이행되지 않음:** 기존 추출·승인·색인·RAG·피드백 제품 엔진의 공통 run 인터페이스
adapter와 승인된 Rule/Proviso 정본. 기존 Assertion과 ClauseSpan의 관측 이관은 완료했지만
새 의미 정본을 구축한 것은 아니다. 해당 제품 profile은 `MIGRATION_REQUIRED`, engine=null로 고정한다.
빈 engine을 기존 runtime으로 조용히 대체하지 않는다. `check`는 준비 상태를 드러내고,
`plan/run`은 미이행 노드와 계약 불일치를 거절한다.

`00_SYSTEM/ONTOLOGY_PIPELINE.json`은 기존 화면/배치의 legacy catalog다. 새 엔진 선택의 정본이
아니다. 기존 `core/batch.py`와 receipt-bound MAIN은 아직 그 경로를 실행한다. 공통 host의
serving 실행은 release adapter가 연결되기 전 차단한다. 따라서 이번 계약 구축을 운영
전체 교체나 기존 corpus migration 완료로 보고하면 안 된다.

다음 실제 이행은 엔진별 adapter + 계약 검증 + 결과 평가를 각각의 ADR로 관리하고,
파이프라인 profile의 한 slot에 명시적으로 연결한다. 스키마 변환부터 새 canonical을 만들고
그 데이터에 맞는 index/assembler/retriever를 연결한 뒤 최종 release로 고정한다.

## 7. 다섯 단계 스키마 목록

데이터 입력 → 처리 → 적재 → RAG → 피드백의 필드 정의는
[STAGE_SCHEMAS.md](STAGE_SCHEMAS.md)를 따른다. `PIPELINE.json.stage_schemas`가 단계별 계약 목록이며,
실제 연결과 선택은 `slots/profiles/engines`에 있다. 목록 등록만으로 기존 제품 profile이나 MAIN을 바꾸지 않는다.

공유 의미 필드는 legal-semantic-v2를 `$ref`하고, 여러 형식을 가진 파일은 `schema_definition`으로 정확히
하나를 선택한다. schema reference는 계약에 해시로 등록한 로컬 파일만 사용하며 외부 URL을 가져오지 않는다.
새 원문·적재·카드·피드백 형식의 엔진 연결은 기존 `MIGRATION_REQUIRED` 상태를 유지한다.
