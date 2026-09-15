# 영구 v2 전환 상태와 잔여 경계

## 2026-09-06 — 파이프라인·의미 SSOT

`PIPELINE.json`이 조립/엔진 선택, `LEGAL_SCHEMA.json`이 의미 계약의 새 정본이다. 기존 MAIN은 legacy 계약이며 아직 변환하지 않았다. 공통 host와 계약 감사 TOOL은 구현됐고 authoring/RAG/feedback profile의 제품 adapter는 MIGRATION_REQUIRED다. 상세 계약과 변경별 처리: `00_SYSTEM/PIPELINE.md`, `00_SYSTEM/DATA_MODEL.md`.

## 2026-09-05 최신: 대량 LLM 전 작성용 통합 완료 — 운영·반출은 미승인

이 절이 아래의 이전 상태를 대체한다. MAIN generation 5 / ACTIVE release
`adr0185-local-main-g5-final`과 원본 데이터는 유지했다. LLM·임베딩·네트워크 호출 0.
구현은 동결된 research 후보와 STAGING 산출물이며, 제품 코드 교체나 운영 승격이 아니다.

| 경계 | 이번에 실제 확인한 상태 |
|---|---|
| 입력 | 5,105 artifact SourceSet; 207문서 package/해제 입력 byte/hash 검증 |
| Graph | ADR-0202 재컴파일: 341,969 StructuralUnit, 629,080 ClauseSpan; 2,554,813행/30 artifact 전수 검증 오류 0·경고 0 |
| 의미 승인 | compiler의 자동 ACCEPTED 제거, 독립 source/provider/review 검증과 typed reviewed bundle 컴파일 연결; 신규 승인 의미 데이터는 0 |
| DP·runtime | ADR-0204: 명시적 reviewed-only 빈 저장소 검증, READY 0; 실제 runtime NO_RULE_MATCH fallback 확인 |
| 추출 계획 | 341,790 node jobs; 341,655개를 58,136배치에 배정; 원문과 조상 문맥 보존, 24 node jobs/24,000 serialized characters 상한 |
| 인덱스·결속 | ADR-0206: 207문서, 제목 50,886 + legacy 용어 3,651 = 54,537 entries; authoring input snapshot + Graph/DP/lexical/batch 파일 hash 결속, 24/24 통과 |
| 감사 기록 | ADR-0203/0204 실패 보존. ADR-0205는 실제 실패 영수증을 검증하는 final-audit 후보, 17/17; 실패를 성공 실행으로 위장하지 않음 |

완료 근거: [ADR-0206](../../04_EXPERIMENTS/ADR/ADR-0206-input-snapshot-binding/README.md),
[작성용 binding](../../09_ARTIFACTS/STAGING/ADR-0206/derived/runtime-binding.json),
[최종 인계](../../07_DOCS/PRE_LLM_AUTHORING_HANDOFF.md).

### 남은 항목 — 데이터·권한·추가 구현을 구별할 것

| 항목 | 남은 작업·완료 조건 |
|---|---|
| 과대 작업 135개 | 원문/조상 문맥을 손실 없이 나누는 검토된 split recipe와 재검증. 자동 잘라내기 금지 |
| 소유 미정 block 56개 | 실제 원문/노드 경계 검토 및 수정 receipt. 임의의 부모/자식에 귀속 금지 |
| 반출 정책 | 현재 207문서 structure package가 restricted/export=false라 58,136배치 모두 EXPORT_DENIED. 제목만 보고 공개로 완화 금지; 공개 원문 계보·권한자 정책 및 새 package/SourceSet 필요 |
| 유료 실행기 | 금액/호출/출력 token hard limit, 실제 가격표와 비용 승인, crash/provider receipt reconciliation을 갖춘 실행 CLI가 아직 필요. offline claim/plan 구현은 실제 유료 executor 완료가 아님 |
| 검토 권한 | 독립 host review/provider trust store의 실제 배치·권한·폐기 운영 검증. 합성 승인 계약을 실제 사람 승인으로 간주 금지 |
| 의미 데이터·품질 | 승인된 작은 조·항·호·목/조건/예외 표본부터 추출→사람 검토→확대. 새 데이터 기여도와 답변 판단 오류를 별도 OOS로 비교 |
| 운영·현장 | release-bound SourceSet/ACL/cache/runtime/rollback 검증, 명시 MAIN 승격, 실제 GenOS/onsite host 영수증. authoring binding으로 대체 금지 |

따라서 “남은 것은 LLM 호출 버튼뿐”이나 “전체 CUTOVER 완료”는 아직 아니다.
이번 결과는 새 구조의 로컬 작성 경로를 끝까지 연결한 것이며 새로운 RAG 정답률은 측정하지 않았다.
기존 6건 Anthropic 승인을 전체 원문 반출·대량 비용 승인으로 확장하지 않는다.

아래 절은 이 통합 이전의 감사 이력이다.

## 2026-09-05 최신: 전체 검증 복구·의미 승인 계약 구현

이 절이 아래 과거 상태보다 최신이다. MAIN generation 5 / ACTIVE release
`adr0185-local-main-g5-final`은 그대로이며 운영 CUTOVER 완료를 선언하지 않는다.

- [ADR-0199](../../04_EXPERIMENTS/ADR/ADR-0199-bounded-validation-foundation/README.md):
  독립 검증기의 row 저장소를 bounded SQLite로 바꾼 격리 후보와 정확한 hash/path
  계보·비계보 관계 탐색 후보를 구현했다. 원본 memory validator와 손상/정상 fixture의
  전체 진단이 일치하고 중복 ID 의미·임시 정리를 포함해 29/29 통과, DAG 오류 0.
  첫 전수 실행은 `/tmp`가 tmpfs여서 용량 부족으로 실패했다. 실패 영수증은 보존한다.
- [ADR-0201](../../04_EXPERIMENTS/ADR/ADR-0201-disk-backed-full-validation/README.md):
  같은 동결 검증기로 디스크 작업 공간에서 재실행했다. 기존 Graph 2,286,503행,
  29 artifact 전수 검증 **오류 0, 경고 0**, 6/6 실행 gate 통과. 약 197.268초,
  최대 RSS 2,384,752 KiB, 주소공간 상한 4 GiB. 원본·입력·코드 hash 유지,
  private 임시 DB와 작업 디렉터리 자동 정리. 기존 154문서 Graph 검증이며
  207문서 입력으로 재컴파일한 결과는 아니다.
- [ADR-0200](../../04_EXPERIMENTS/ADR/ADR-0200-semantic-admission-contract/README.md):
  `semantic-observation-v2` 후보 schema와 source/provider/review/scope 검증 모듈을
  구현했다. 조건·결과·예외 대상·관계와 원문 문자 span·최하위 소유 노드를 검증한다.
  모델 출력은 CANDIDATE만 허용하며, 검증을 우회한 승인/신뢰되지 않은 검토/UNKNOWN/
  미해결 관계의 Canonical 컴파일 승인을 거절한다. 계약 76/76 통과.
  실제 외부 호출과 실제 사람 승인 0; 합성 교환은 실제 provider 증거가 아니다.
- 활성 DP 3,232건은 모두 TERM_LOOKUP_ONLY로 분류된다. 활성 metadata 검사에서
  문서 coverage, Graph/DP authority·SourceSet, DP row scope, glossary/links 입력 누락의
  8개 차단 사유를 확인했다. metadata 통과만으로 배포를 허가하지 않는다.

### 빠짐없이 관리할 잔여 구현·검증 목록

| 경계 | 현재 상태 | 완료 조건 |
|---|---|---|
| 입력 package/SourceSet | 5,105개 입력·glossary/links staging 준비(ADR-0197) | verified package ACL과 입력 lock을 새 빌드에 사용; derived를 입력에 재포함하지 않음 |
| 전체 검증 메모리·임시 공간 | 후보와 기존 Graph 전수 검증 완료(ADR-0199/0201) | 후속 통합 빌드에서 동일 검증 적용; 후보가 활성 도구/제품에 설치됐다고 가정하지 않음 |
| 의미 추출 schema | typed observation·조/항/호/목 span 계약 완료(ADR-0200) | 실제 추출 recipe/CLI와 연결; 구조 contract의 전체 불변조건 및 실제 문서 호환성 추가 검증 |
| 추출 재개·반출 제어 | hash receipt/resume 합성 계약 완료(ADR-0198) | verified package ACL, 예산 상한, 실행 claim 복구를 CLI에 연결; 공개 원문 전송 범위·비용 승인 |
| 승인→Canonical 경계 | 별도 승인 eligibility 모듈 완료(ADR-0200) | 신뢰된 review store 연결, 실제 compiler의 자동 ACCEPTED 제거, 승인 observation→Canonical 매핑과 receipt 구현 |
| 새 전체 파생 세대 | 미완료 | 207문서 입력으로 Graph→DP→불변 lexical index 재컴파일, 동일 input/authority/semantic scope·파일 hash 전수 검증 |
| RAG 판단 capability | TERM_LOOKUP_ONLY와 부분/미검증 구별 후보 완료 | 실제 runtime에서 capability/scope 적용; 용어 READY를 일반 법적 판단으로 사용하지 않음 |
| 운영 CUTOVER·배포 | MAIN/ACTIVE 보존, 아직 승격 금지 | source-only/derived binding, 공개·제한·실험 SourceSet ACL/캐시/격리/복구, OOS와 명시 승격, 현장 GenOS ACL/runtime 영수증 |

큰 레거시 모듈/폴더 정리는 위 통합 경로·receipt를 깨지 않는 후속 코드 세대에서만 한다.
기존 완성 세대·실패 기록·역사 ADR을 새 이름으로 다시 복사하거나 원본으로 덮어쓰지 않는다.

### 추가 권한이 필요한 실행

대량 LLM 호출은 아직 승인되지 않았다. 이전 Anthropic 승인은 CM 질문 6건과 그 회수
문맥·기준답변이며 전체 법령 재추출 승인이 아니다. 공개 문서 범위와 최대 비용을 먼저
확인하고, 제한 문서는 반출하지 않는다. 그 후 대표 조·항·호·목/조건/예외 표본→사람 검토→
확대 추출→OOS 순서로 실행한다. 실제 host ACL·GenOS 검증과 MAIN 승격도 별도 경계다.
데이터 누락이 성능 저하의 원인 후보라는 관찰을 새 LLM 품질 개선 실적으로 바꾸지 않는다.

아래는 이번 구현 이전의 이력이며, 남은 절차는 위 표를 기준으로 읽는다.

## 2026-09-05 후속 감사: 입력 보완·LLM 추출 재개·전체 검증 실패

MAIN/ACTIVE에는 적용하지 않았다. 아래 연구 후보 통과를 운영 CUTOVER 완료로 읽지 않는다.

- [ADR-0197](../../04_EXPERIMENTS/ADR/ADR-0197-input-bound-derived-runtime/README.md):
  glossary 4,438건과 links 1,759건을 출처 hash가 있는 별도 입력 package로 등록했다.
  입력 SourceSet은 5,105 artifact이며 staging에만 있다. 구조 207개/frames 106개와
  frame 참조 무결성을 포함한 입력 준비 gate 6개는 통과했다.
- 전체 Graph 작성 뒤 독립 검증의 `_load_artifacts`에서 10 GiB 주소공간 한도로
  `MemoryError`가 발생했다(740.236초). compiler 객체 해제/GC는 이미 구현되어 있다.
  검증기의 전체 row 상주와 교차 참조 인덱스 메모리를 줄여야 한다. DP/index/runtime
  admission 단계에는 도달하지 않았으며 실패한 임시 Graph만 compiler가 자동 정리했다.
  실패 run은 그대로 보존했다. 성공 run을 요구하는 ADR final 검증 요건도 미충족이다.
- 사후 감사에서 고정 원본 파일 7개와 봉인 코드 409개 hash 유지 확인.
  MAIN/ACTIVE/원본 데이터 변경과 실제 provider 호출은 없다.
- exact-parent DAG 후보는 LEGACY_ADR 조상을 찾지만, 새로 도달한 ADR-0158의
  비계보 관계 대상 ADR-0135/0136/0157은 아직 누락이다. 관계를 부모로 위장하지 말고
  해시가 고정된 relationships 대상도 별도로 해석해야 한다. 활성 tool에는 미반영이다.
- [ADR-0198](../../04_EXPERIMENTS/ADR/ADR-0198-frame-resume-receipt-gate/README.md):
  입력·SourceSet·authority·모델·프롬프트·스키마·추출 코드 hash 기반 재개 후보의
  합성 계약 20/20 통과. 실패 재시도/정상 빈 결과/호출 상한/불변 provider receipt/
  활성 경로 쓰기 거부/미승인 전송 거부를 확인했다. 실제 LLM 호출 0, fake 호출 7.
  기존 추출기/운영 기본 경로는 바꾸지 않았다. 실제 추출 품질이나 ACL 운영 검증은 아니다.

### LLM 데이터 문제에 대한 관찰과 한계

- 구조 문서 207개 중 frame 파일 보유 106개, 미보유 101개.
- 31,879개 frame 행 중 빈 marker 1,728개를 제외한 30,151개는 조 4,247개와
  항 25,904개에 연결된다. 호·목 family에 연결된 유효 frame은 없다.
  원본 frame 참조 orphan은 없다. 모든 구조 노드가 반드시 의미 규칙을 가져야 하는 것은 아니다.
- 현재 legacy frame schema는 actor/act/target/object/mode/function/proviso/jo/node이며
  조건·결과·예외 대상과 상하위 적용 관계를 독립 구조로 충분히 표현하지 못한다.
- frame 추출기에는 Haiku 호출 코드가 존재한다. 기존 행의 embedded provider/model receipt
  부재만으로 과거 LLM 미사용을 단정할 수 없다. 과거 소규모 실제 호출 이력도 있다.
- 기존 `extract_doc`는 `jo`가 있으면 완료로 취급하므로 입력/모델/스키마 변경을 감지하지
  못할 수 있다. ADR-0198은 이 문제의 격리 후보이며 아직 제품 경로 교체가 아니다.
- 기존 compiler는 deterministic observation에서 ACCEPTED/SEMANTIC_READY를 자동 생성한다.
  이를 LLM 추출+출처 검증+사람 승인의 대체로 인정하지 않는다.
- 누락은 품질 저하의 원인 후보이지 기여도를 입증한 A/B 결과가 아니다.
  [ADR-0193](../../04_EXPERIMENTS/ADR/ADR-0193-rag-bounded-normative-integration/README.md)에는
  올바른 법령 문맥을 찾고도 답변이 틀린 사례가 있다. 데이터만 전량 재추출해도 해결된다고
  가정하지 않는다. 이번 두 감사에서 새 답변 정답률을 측정하지 않았다.

### 다음 실행 순서와 완료 조건

1. 검증기 메모리 상주를 제한하는 별도 후보를 선점·동결한다. 단순 상한 증액/검증 생략이
   아니라 전체 행/참조/해시 검사를 보존하고 원본 불변성과 최대 RSS를 함께 검증한다.
   ADR-0197의 실패 결과/코드는 덮어쓰지 않는다.
2. 비계보 relationships까지 정확한 저장 경로/hash로 탐색하는 ADR resolver를 완료한다.
   과거 기록 이동·복사나 관계를 merged_from으로 변경해 검사를 통과시키지 않는다.
3. 추출 recipe를 현행 의미 스키마와 연결한다. 조·항·호·목 좌표, 주체, 행위, 대상,
   조건, 예외, 효과, 적용/위임 관계, 원문 span, provenance를 명시하고 검증 기준을 동결한다.
   실제 원문에서 표현되지 않은 의미를 결정론적 재컴파일로 만들어내지 않는다.
4. 공개/제한 자료를 verified package ACL로 분리한 실행 CLI, 중단 claim 복구,
   비용 상한을 연결한다. Anthropic 대량 전송 범위와 최대 비용은 사용자 확인 전이다.
   이전 CM 6건 전송 승인을 전체 데이터 승인으로 확장하지 않는다.
5. 가장 작은 대표 조·항·호·목/조건·예외 표본을 Haiku로 추출해 source/schema 검증과
   사람 검토를 거친다. 재개 영수증이 일치하는 성공 단위는 재호출하지 않는다.
   품질 통과 전 101개 미추출 문서 전체를 보내지 않는다.
6. 기존 vs 새 의미 데이터의 retrieval 및 답변 기여를 분리한 OOS 비교를 별도 ADR로
   동결한다. context는 맞지만 답변이 틀린 유형도 포함한다. 자동 ACCEPTED를 제거하고
   승인된 observation만 Canonical/Projection의 근거가 되도록 한다.
7. Graph/DP/인덱스 전수 검증, input/derived runtime binding, ACL/캐시/롤백 검증을
   통과한 decision-eligible arm만 명시적 MAIN 승격으로 연결한다. GenOS 현장 배포와
   실제 호스트 ACL 영수증은 로컬 계약 통과로 대체하지 않는다.

아래 입력 분리 감사는 후속 작업 이전의 이력이다.

## 2026-09-05 입력 SourceSet 분리 감사

- ADR-0196: 연구 전용 입력 publisher와 derived metadata 결속 계약 40/40 통과.
  [실험 기록](../../04_EXPERIMENTS/ADR/ADR-0196-ontology-input-sourceset-separation/README.md).
- 활성 artifact 8,377개를 입력 5,103개와 파생 산출물 3,274개로 전수 분류했다.
  10개 입력 package, 구조 문서 207개, frame 파일 106개를 staging에 보존했다.
  원본 package/version/build/hash 계보와 비공개 export 정책을 보존했으며
  MAIN/ACTIVE 및 원본 package bytes는 변경하지 않았다.
- 새 SourceSet은 `09_ARTIFACTS/STAGING/ADR-0196/input-publication`에만 있다.
  약 2.1 GiB의 독립 복사이며 `serving_ready=false`다. 기존 파생 파일을 삭제하지 않았다.
- ADR-0195의 기존 전체 재컴파일 계획은 실행 전 중단했다. serving SourceSet을
  그 SourceSet에 포함되는 Graph에 다시 넣는 순환 해시 설계이므로 그대로 실행하지 않는다.

### 후속 게이트 — 아직 운영 적용 아님

1. 새 입력 package에서 compiler 입력을 재현한다. 구조 bundle 해제뿐 아니라 glossary/
   links 등 보조 입력의 출처와 변환 hash도 결속해야 한다. 기존 query 캐시를 출처 없이
   복사하거나 현재 serving hash만 새 Graph에 덮어쓰지 않는다.
2. 전체 Graph/DefinitionProjection/index를 해당 입력 lock으로 생성하고 실제 파일 hash,
   권위·의미 세대 및 누락 문서/조항 accounting을 독립 검증한다. ADR-0196의 derived
   binding 검사는 합성 metadata이지 실제 compiler 또는 RAG 검증이 아니다.
3. release/runtime resolver를 input SourceSet과 별도 derived bundle에 연결하고 실제 RAG,
   ACL, 캐시 격리, OOS 및 롤백 검증 뒤에만 명시적 MAIN 승격 절차를 밟는다.
4. raw 문서 ID와 structure ID의 매칭 및 의미 observation 누락은 별도 데이터 계보 과제다.
   이번 package provenance 보존을 그 문제까지 해결한 것으로 해석하지 않는다.
5. 전역 ADR graph 검사: `graph edge source missing: ADR-0158-experiment-v1/v2-candidate`.
   부모는 LEGACY_ADR에 존재하지만 현행 graph builder는 ADR 폴더만 열거한다.
   완료 실험을 이동·수정하지 않고 exact parent path/hash를 따라가는 resolver 보완이 필요하다.
   ADR-0196 개별 `validate --final`은 통과했으나 전역 graph 검사는 실패 상태다.

아래 2026-09-04 기록은 해당 시점의 이력이며 현행 code generation을 뜻하지 않는다.
현재 layout/code 선택은 WORKSPACE.json의 v2-only lifecycle receipt를 따른다.

## 2026-09-04 코드 상태

- workspace는 `v2-only`이며 legacy top-level root와 unknown root가 없다.
- editable backend/tool source를 각각 `02_BACKEND/lawrag`,
  `06_TOOLS/LEGACY_SCRIPTS`에 두고, 실행 선택은 활성화 영수증에 봉인된
  `20260904-code-v5` 불변 generation을 사용한다.
- 과거 기록의 `data/docs/scripts/lawrag/var` 경로는 기록을 재작성하지 않고
  활성·이력 activation receipt의 source→target binding으로 해석한다.
- `ExperimentStore`는 ADR/experiment ID 중복을 fail-closed 처리하고 artifact SHA-256을
  읽기 전에 검증한다.
- 기본 pytest 수집 범위는 smoke+legacy regression이며 `1960 passed`다.
- `pyproject.toml` 기반 wheel을 만들 수 있고 research 및 agent6 raw corpus는 wheel에
  포함되지 않는다. GenOS 코드 ZIP도 canonical code/config만 포함하고 data/runtime/
  experiment/research root를 제외한다.
- `release-manifest-v1`, source-set 고정, index build provenance, embedding fingerprint,
  `ACTIVE_RELEASE` generation+hash CAS, append-only apply/rollback receipt 계약은 구현·검증돼 있다.
- root의 domain graph 정적 파일은 코드 ZIP에서 제거됐으며 권위 데이터 패키지로만 운반한다.

## 코드와 분리된 잔여 작업

1. Legal Graph compiler의 regex Requirement/Frame observation을 canonical `ACCEPTED`로
   자동 승격하는 경로는 별도 효과성 ADR에서 제거해야 한다. 조건·결과·효과·연결은
   observation→validator→명시 승인 경계를 거쳐야 하며, 이 변경은 검색 의미를 바꾸므로
   ADR-0166의 결정론적 경로 이행에 섞지 않는다.
2. GenOS host의 실제 activation/rollback smoke, 내부+외부 source-set 검색, ACL 누수와
   관찰 기간은 배포 작업이다. 사용자가 배포를 제외했으므로 이번 코드 작업에는 포함하지 않았다.

위 두 항목 전에는 제품 의미 배선이나 GenOS 활성 포인터를 변경하지 않는다.
