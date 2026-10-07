# ADR·LLM 실험 기록 표준 v4

## 신규 실험 모델 정책 — 2026-09-30 사용자 변경

ADR-0583 이후 신규 외부 실험 기본값은 **Qwen3.8 / qwen/qwen3.8-27b**다.
정본은 `00_SYSTEM/EXPERIMENT_MODEL_POLICY.json`, 공통 호출은
`lawrag.research.experiment_client.ExperimentClient`다. OpenRouter Parasail
FP8 단독, reasoning effort none, provider/model fallback 없음으로 고정한다.
`.env`의 `OPEN_ROUTER`를 메모리에서만 읽고 키를 출력·기록하지 않는다.
생성·중간처리·평가에 적용한다. ADR-0538~0581 Gemma 완료 기록은 보존한다.
ADR-0582는 예약 후 사용자 변경으로 실제 공개 사례에 Qwen3.8을 사용한 전환 기록이다.
GENOS 내부 모델·활성 MAIN 릴리스는 별도다.

### 이전 정책 기록 — 2026-09-23 사용자 변경

ADR-0538 이후 신규 외부 실험의 기본값은 **Gemma / google/gemma-4-31b-it**다.
정본은 `00_SYSTEM/EXPERIMENT_MODEL_POLICY.json`, 공통 호출은
`lawrag.research.experiment_client.ExperimentClient`다. `.env`의 `OPEN_ROUTER`를 읽으며
Parasail FP8·thinking off·허용 provider를 고정한다. 생성·중간처리·VLM·오프라인 평가에
적용하고 다른 모델/provider로 자동 전환하지 않는다. 키나 `.env` 원문을 기록하지 않는다.
사용자 지시: “Qwen이아니라 Gemma써 왜 계속 qwen쓰냐 이제부터 llm은 Gemma임” (ADR-0538).
기존 Qwen·Gemini·Haiku 완료 기록 및 명시적 scoped override는 역사적 정본으로 보존한다.
새 재실행은 새 ADR에서 현재 정책을 동결한다. 본문에 남은 이전 모델 규칙은 과거 기록용이며
신규 외부 실험에는 이 절이 우선한다. GENOS 내부 모델과 실제 현장 검증은 별도다.

- v1 적용 시작: ADR-0043
- v2 적용 시작: ADR-0044
- v3 적용 시작: ADR-0077
- v4 적용 시작: ADR-0082
- 상태: 필수
- 모델 정책: 제품 경로는 Haiku 고정, 격리된 오프라인 평가는 승인 allowlist,
  답변 모델 비교는 제품과 단절된 동결 벤치마크 class에서만 허용
- 검사기: `scripts/adr_structure.py`

## 1. 표준 디렉터리

새 ADR은 반드시 디렉터리형으로 만든다. 과거 ADR은 감사 가능성을 위해 이동하거나 재작성하지 않고 legacy로 보존한다.

```text
docs/adr/ADR-NNNN-kebab-slug/
├── claim.json
├── README.md
├── 실험/
│   ├── README.md
│   ├── manifest.json
│   └── 질문-001-case-id.md
└── artifacts/
    └── manifest.json
```

- `claim.json`: 생성 lock을 풀기 전에 쓰는 immutable 번호·scope 선점 영수증이다(v3).
- `README.md`: 가설, 사전 성공 기준, 실험 결과, 결정과 롤백을 담는 결정문이다.
- `실험/README.md`: 모든 질문 파일과 arm별 판정을 한 표로 연결한다.
- `실험/manifest.json`: 설계, 계보, 실행, 집계를 기계 판독 가능한 형태로 보존한다.
- `실험/질문-NNN-case-id.md`: 해당 질문의 실제 입력·출력·채점 원문을 보존한다.
- `artifacts/manifest.json`: ADR 폴더에 복제하지 않은 원시 JSON 등의 경로와 hash를 남긴다.

질문 수가 0인 구조 감사도 같은 디렉터리를 사용한다. 이 경우 manifest의 `questions`는 빈 배열로 두고 `실험/README.md`에 질문 단위 평가가 없었던 이유를 적는다.

### 1.1 작업 전 선점과 생성 이력(v3·v4)

ADR-0077 이후에는 ADR 생성이 해당 작업의 **첫 쓰기**여야 한다. 소스, 설정, 데이터,
prompt, 실험 스크립트나 산출물을 먼저 수정한 뒤 ADR을 소급 생성할 수 없다. 읽기 전용 조사와
기존 상태 확인만 선점 전에 허용한다.

1. `docs/adr`의 진행 중인 `reservation`을 확인해 번호뿐 아니라 제목·scope·`scope_key`가
   겹치는 작업이 없는지 확인한다.
2. `scripts/adr_structure.py new`로 번호와 scope를 선점한다. 폴더를 손으로 만들거나 기존
   ADR을 복사하지 않는다.
3. 생성기는 전역 생성 lock 아래에서 같은 번호를 다른 slug로 만드는 경우와 진행 중인 같은
   `scope_key`를 거부한다. lock을 풀기 전에 immutable `claim.json`을 써서 폴더 생성과
   manifest 생성 사이의 동시성 창도 막는다. 충돌 시 번호만 바꿔 우회하지 않고 기존
   owner와 조율한다.
4. `실험/manifest.json`의 `reservation`은 다음 필드를 보존한다.
   - `status`: `in_progress`, `completed`, `abandoned`
   - `owner`, `session_id`, `scope`, `scope_key`
   - UTC `created_at`, `work_started_at`, `updated_at`, `completed_at`, `abandoned_at`
   - append-only `events`: 최소 `reserved`, `started`와 이후 `completed`/`abandoned`/`resumed`
5. `README.md` front matter의 `created_at`, `updated_at`, `owner`, `work_status`는 manifest와
   일치해야 한다. 생성 시각은 수정하지 않는다. owner 이전이나 상태 변경은 기존 이벤트를
   덮어쓰지 않고 새 이벤트로 추가한다.
   WSL·원격 shell이 Codex 환경 변수를 상속하지 않으면 `--session-id`로 현재 task ID를
   명시한다.
6. 완료는 `adr_structure.py status --status completed`, 실행하지 않을 선점은
   `--status abandoned --note "사유"`로 닫는다. 완료·포기된 ADR 디렉터리는 삭제하거나
   번호를 재사용하지 않는다.

위임된 agent는 같은 작업에 별도 ADR을 선점하지 않는다. 주 agent가 만든 ADR의 정확한
run/arm과 artifacts 경로를 사용한다. 범위가 독립적인 새 실험으로 갈라질 때만 새 ADR을
선점하고 부모 `experiment_id/arm_id`를 연결한다.


### 1.2 새 실험 후보 코드 격리(v4, ADR-0138 이후)

ADR-0138 이후 제품 답변·제품 context·retrieval 후보 집합에 영향을 줄 수 있는 구현 후보는
운영 경로와 물리적으로 분리하며 `design.code_isolation`을 결과 확인 전에 고정한다.

- `schema_version`은 `adr-code-isolation-v1`이다.
- `mode`는 `candidate_snapshot` 또는 `not_applicable`이다.
- 공통 flag는 `production_paths_modified_before_decision=false`,
  `runtime_import_allowed=false`, `production_registry_registered=false`,
  `main_wiring_unchanged=true`로 고정한다.
- candidate는 ID, exact experiment/arm/run, `candidate.json`과 SHA-256, frozen revision ID와
  SHA-256, 명시적 research runner 경로와 SHA-256을 가진다.
- 제품 영향 구현 후보가 없는 문서·구조 감사만 `not_applicable`과 구체적 사유를 허용한다.

제품 영향 후보의 실행 순서는 다음과 같다.
1. ADR 선점과 가설·기준·arm·run 동결.
2. `scripts/adr_candidate.py snapshot`으로 필요한 기존 파일을 research candidate 아래 복사.
   신규 파일은 candidate의 최종 `snapshot/<target_path>`에 만든 뒤
   `adr_candidate.py register --upstream-state absent`로 등록한다.
   `adr-code-candidate-v2`는 최종 `target_path`와 `upstream_state`를 분리한다.
   기존 파일은 `present`와 최초 upstream hash를, 신규 파일은 `absent`, null upstream
   path/hash, 부재 확인 시각, 최초 proposal hash를 기록하며 둘을 자동 동일시하지 않는다.
3. 복사본만 수정하고 `freeze`, `validate`로 revision hash 고정. freeze는 present upstream이
   최초 hash에서 바뀌거나 absent target이 나타난 경우, 또는 manifest에 없는 snapshot 파일이
   있는 경우 fail-closed한다. 기존 `adr-code-candidate-v1`은 과거 기록 검증용으로 계속 읽는다.
4. hash가 맞는 explicit research runner가 해당 revision을 직접 import·주입.
5. 후보 snapshot과 원시 실행 receipt를 ADR artifact manifest에 기록.

완료 validator는 candidate 경로 containment, ADR/experiment/arm/run 일치, manifest·runner hash,
frozen revision, `production_loadable=false`를 검사한다. 세 운영 변경 flag는 모두 false여야 하며,
승격은 검토본을 production component로 옮긴 뒤 별도 MAIN 절차로만 수행한다.
## 2. 실험 분기 DAG

실험 계보는 트리가 아니라 여러 부모와 재검증을 허용하는 DAG로 관리한다.

```text
A/baseline
├── A/B
│   ├── B/B1
│   └── B/B2
└── A/C
```

분기 단위는 다음과 같이 구분한다.

1. **같은 ADR의 arm**: 같은 동결 데이터셋과 판정 기준으로 동시에 비교하는 A/B/C다.
2. **새 ADR**: B 결과를 본 뒤 B1/B2를 설계하거나 prompt, judge, parser, 데이터셋, 성공 기준을 바꾸는 후속 실험이다.
3. 자식 ADR은 부모 ADR이 아니라 정확한 `experiment_id/arm_id`를 참조한다.
4. ADR이 열려 있는 동안 사전에 계획한 반복은 `run-002`처럼 추가할 수 있다. 완료된 manifest·질문 원문·실행 결과는 수정하지 않으며, 완료 후 재실행·재채점·후속 가설은 새 ADR로 추가한다.
5. 탈락 arm과 실패한 분기도 삭제하지 않는다. 그래프에서 상태와 탈락 이유를 남긴다.
6. 서로 다른 분기를 합치면 `lineage.parents`에 모든 부모 arm과 관계를 기록한다.
7. 부모 실험의 결과가 `complete`일 때만 자식 분기를 만든다. 제안 단계의 arm을 부모로 삼지 않는다.

### 2.1 다중 부모 ADR merge

둘 이상의 ADR 결과를 결합하는 작업은 기존 ADR 하나를 수정하지 않고 새 ADR을 선점한다.

1. 모든 부모는 `complete`인 정확한 `experiment_id/arm_id`여야 하며 relation은
   `merged_from`이다. ADR 번호만 참조하거나 부모의 baseline을 임의로 추정하지 않는다.
2. merge 결과의 `baseline.derived_from`은 모든 부모 arm을 포함한다. 각 부모 manifest의
   경로와 SHA-256, 각 root와 source branch path를 보존한다.
3. manifest의 `integration`에 다음을 실행 전에 고정한다.
   - merge ID, 결과 arm, merge 이유, 공통 불변조건, rollback parent
   - 부모별 `adopted`와 `excluded` 항목
   - 충돌별 ID, 충돌한 부모, 선택한 부모/해결안, 근거
   - 충돌이 없으면 빈 배열과 구체적인 `no_conflict_reason`
4. 부모 중 하나의 기록을 덮어쓰거나 “최신 ADR이 이전 것을 포함한다”고만 적지 않는다.
   통합 후 탈락한 선택도 각 부모의 `excluded`에 남긴다.
5. merge 후 새로운 비교·평가가 있으면 새 ADR의 arm/run으로 실행한다. 단순 코드 합치기와
   실험 결과 채택을 같은 의미로 취급하지 않는다.

계보가 아닌 ADR 관계는 manifest의 `relationships`에 별도로 기록한다. 허용 관계는
`related_to`, `depends_on`, `informed_by`, `conflicts_with`, `duplicates`, `blocks`,
`blocked_by`, `supersedes`, `superseded_by`다. 각 관계는 대상 ADR, 관계, 설명과 대상의
immutable `claim.json`(legacy면 manifest) 경로·SHA-256을 가진다. 이 관계는 arm DAG의
부모나 cycle 판정에 포함하지 않지만 전역 graph의 ADR 관계 표에 출력한다.

### 2.2 통합 ADR arm의 MAIN RAG 승격

ADR merge는 계보만 만든다. 실제 운영 `legalclosure-v2` 배선 변경은
[MAIN RAG 승격 절차](MAIN_PROMOTION.md)를 별도로 따른다.

1. source ADR은 `Accepted`, `main_wiring: promotion-candidate`, `in_sample=false`,
   `decision_eligible=true`, `results.status=complete`, v3 reservation `completed`여야 한다.
2. 여러 arm의 기능을 함께 올리면 먼저 2.1의 merge ADR 하나로 접고 그 결과 arm 하나를
   promotion source로 쓴다. 개별 arm 여러 개를 MAIN에 직접 순차 적용해 암묵적으로 합치지 않는다.
3. `rag_main_promotion.py prepare`는 source manifest, code artifact, validation receipt와
   현재 MAIN generation/hash, 적용 전 전체 state를 동결한다. prepare는 MAIN을 바꾸지 않는다.
4. 승격할 모든 code artifact는 같은 plan에서 적용하는 등록된 guard switch를 가져야 한다.
   동적 import나 무가드 code-only 승격은 금지한다.
5. `check` 통과 뒤 승인자가 이유와 `--confirm-main`을 명시한 `apply`만 새 generation을
   원자 적용한다. source/code/receipt 또는 MAIN generation이 바뀐 stale plan은 거부한다.
6. MAIN manifest의 switch는 repository default보다 우선하고 사람 emergency override보다
   낮다. 적용 source ADR/experiment/arm, promotion ID와 generation을 API 응답에 노출한다.
7. apply와 rollback은 append-only receipt를 남긴다. rollback도 generation을 되감지 않고
   새 generation을 발행하며 가장 최근 active promotion부터 수행한다.
8. 실험 성공이나 ADR `Accepted`만으로 자동 승격하지 않는다. 사용자 승인 없이 agent가
   `apply --confirm-main`을 실행할 수 없다.

arm의 `derived_from`은 변경의 직접 기준을 표시한다. 같은 실험 안의 arm은 로컬 arm ID를, 이전 실험은 `experiment_id/arm_id`를 쓴다. 예를 들어 B와 C가 A의 한 변수씩만 바꿨다면 둘 다 `derived_from: ["baseline"]`이다.

전역 계보는 다음 명령으로 생성한다. 생성 파일은 손으로 고치지 않는다.

```bash
python scripts/adr_structure.py graph --adr-root docs/adr
```

출력은 `docs/adr/EXPERIMENT_GRAPH.json`과 `docs/adr/EXPERIMENT_GRAPH.md`다.

## 3. ADR 결정문 필수 순서

`README.md`는 다음 제목을 순서대로 갖는다.

1. `결정 요약`
2. `문제와 변경 전 구조`
3. `가설과 사전 판정 기준`
4. `실험 설계`
5. `데이터·모델·재현성`
6. `결과`
7. `사례별 오류 분석`
8. `비용·지연·회수 규모`
9. `해석`
10. `한계와 일반화 가능 범위`
11. `운영 결정·롤백 조건`
12. `재현 명령`

메타데이터에는 ADR 번호, 상태, 결정일, 실험 단계, 인샘플 여부, 운영 배선 변경 여부를 명시한다. 상태는 `Proposed`, `Accepted`, `Rejected`, `Superseded` 중 하나다. v3는 여기에
생성·갱신 시각, owner와 작업 상태를 추가한다. ADR 결정 상태와 작업 선점 상태는 별개다.

## 4. 실험 설계 규칙

1. **가설과 성공·반증 기준을 실행 전에 적는다.** 결과를 본 뒤 기준을 바꾸면 새 ADR 또는 run으로 기록하고 원래 기준을 삭제하지 않는다.
2. baseline, candidate, ablation, control arm의 차이는 한 표로 적는다. 바뀐 것과 고정한 것을 분리한다.
3. 기존 오답을 보고 설계하거나 프롬프트를 조정했다면 `phase=probe`, `in_sample=true`, `decision_eligible=false`로 기록한다.
4. 인샘플 probe는 운영 채택 근거가 될 수 없다. 운영 채택은 분리된 holdout 또는 사전에 고정한 전수 평가가 필요하다.
5. 제품 모델에 기준답변을 넣지 않는다. 기준답변은 채점 호출에만 제공하고 질문 Markdown에서도 제품 입력과 물리적으로 분리한다.
6. 같은 질문에서 제품 호출 순서와 judge의 arm 위치 편향을 통제하거나, 통제하지 못했다면 한계로 기록한다.
7. 결과 확인 후 judge·prompt·parser를 변경하면 기존 run을 덮어쓰지 않는다. ADR 완료 전이면 새 run, 완료 후면 새 ADR로 남긴다.
8. 각 run은 실행 목적, 포함 arm, 표본 선택 규칙, 부모 run, 산출물 hash를 기록한다.

## 5. 모델 규칙

- 제품 답변, router, compiler, verifier, repair 등 사용자에게 보일 답을 생성·선택·변경하는
  모든 호출은 `claude-haiku-4-5-20251001`만 사용한다.
- 제품 경로와 격리되어 점수만 생성하는 `offline_evaluator`는
  `claude-haiku-4-5-20251001`, `claude-sonnet-5`, `claude-opus-5`를 사용할 수 있다.
- offline evaluator는 제품 답변을 수정하거나 운영 호출의 입력으로 들어갈 수 없다. 그
  출력으로 답변을 고치면 evaluator가 아니라 product 역할이므로 Haiku를 써야 한다.
- `role-separated-v2`의 `offline_benchmark_candidate`는 모델 자체의 답변 상한을 재는
  격리 벤치마크에만 쓴다. 이 class의 출력은 사용자 답변을 변경하거나 제품 context에
  들어갈 수 없고, 동결된 기준답변을 보지 않으며, 점수 전용 offline evaluator만 읽는다.
  manifest는 실행 전에 비교 모델 ID의 닫힌 목록과 다음 격리 계약을 고정해야 한다:
  `may_change_product_answer=false`, `may_enter_product_context=false`, `judge_only_use=true`.
  이 예외는 제품·router·compiler·verifier·repair의 Haiku 의무를 완화하지 않는다.
- `실험/manifest.json`의 `llm_calls`에 역할, `class`(`product` 또는
  `offline_evaluator`, 격리 벤치마크이면 `offline_benchmark_candidate`), 모델, 반복 횟수,
  temperature 또는 provider 기본값을 기록한다.
- 모델별 점수는 사람 확정 calibration set의 false pass·false fail·불일치와 지연을 함께
  기록하기 전에는 서로 직접 비교하지 않는다.
- LLM을 쓰지 않은 단계는 모델명을 꾸며 넣지 말고 `llm_calls`에서 제외한다.
- 모델 정책을 바꾸려면 이 표준을 개정하는 별도 ADR이 먼저 필요하다. 격리 답변 모델
  비교 정책은 ADR-0054에서 도입했다.

## 6. 질문별 Markdown 규칙

각 질문 파일에는 다음을 생략 없이 기록한다.

1. 실행 메타: case ID, run ID, arm, 실행 시각, 모델, 원본 상태
2. 사용자 질문 원문
3. 기준답변: **채점 전용이며 제품 입력 비공개임을 표시**
4. 제품 입력 원값: 회수 좌표, 조문, 정의, Wiki, 관계, 필터 결과
5. run·arm별 제품 호출: system, user, schema/tool, provider 원응답, structured output
6. 중간 LLM 호출: router/compiler/verifier/repair의 입력과 출력
7. 채점 호출: system, user, 출력, 반복 표, 최종 다수결
8. 사례 판정: arm별 정오, 비교쌍의 신규 정답·회귀, 실패 유형

v4에서 회수·필터·가지치기·확장·rerank·선택 중 하나라도 후보 집합에 관여하면 4번 제품
입력 원값 아래에 run·arm별 단계표를 둔다. 각 단계의 후보 before/added/discarded/after,
gold before/gain/loss/after, recall, 탈락 이유와 정확한 discarded gold 좌표를 적고 dedicated
stage-ledger artifact를 연결한다. 후보 snapshot은 gold-free로 먼저 고정하며 gold는 제품 선택
완료 뒤 offline grader가 결합한다.

실제 provider payload를 저장하지 않았다면 `exact`라고 표시하지 않는다. `reconstructed`로 표시하고 재구성 재료와 누락 가능성을 적는다. 긴 원문도 질문 파일에서 임의로 생략하지 않는다. 대용량 binary만 artifacts로 분리할 수 있다.

실패 유형은 가능한 한 다음 공통 분류를 사용하고, 맞지 않으면 `other`와 설명을 쓴다.

- `retrieval_miss`
- `governing_rule_selection`
- `scope_actor_mismatch`
- `condition_exception`
- `numeric_temporal`
- `authority_or_version`
- `definition_resolution`
- `required_issue_omission`
- `unsupported_inference`
- `judge_or_gold_error`

## 7. 필수 결과 지표

모든 답변 실험은 다음을 함께 보고한다.

- arm별 `정답 수 / 전체 수`와 비율
- 사전에 고정한 비교쌍별 paired delta
- 비교쌍별 `candidate만 정답`, `baseline만 정답(회귀)`, `둘 다 정답`, `둘 다 오답`
- judge 불일치 수와 재채점 방식
- 오류 유형별 건수와 분모
- 입력·출력 토큰, 호출 수, p50/p95 지연 또는 측정 불가 사유

회수 또는 가지치기를 건드린 실험은 추가로 다음을 보고한다.

- 전체 corpus 단위 수
- 필터 전 후보 수
- 필터 후 후보 수
- 실제 LLM에 제시한 수
- 질문당 평균·p50·p95 제시 수
- golden recall과 `제시 수 / 전체 corpus` selectivity

### 7.1 v4 단계별 회수·탈락 원장

ADR-0082 이후에는 `retrieval_accounting.stage_ledger.mode`를 반드시 다음 셋 중 하나로
선언한다.

- `measured`: 후보 집합을 바꾸거나 새로 측정한 실험. 완료된 모든 run의 모든 arm·case·stage를
  dedicated `retrieval-stage-ledger-v1` artifact에 기록하고 path와 SHA-256을 고정한다.
- `inherited`: 동결 retrieval을 그대로 재사용한 실험. 원본 canonical ledger의 path와
  SHA-256을 기록한다.
- `not_applicable`: retrieval이 전혀 없는 구조 감사. 구체적인 사유를 적고 artifact를 만들지
  않는다.

`changed=true`는 반드시 `measured`다. 실행 전 `design.retrieval_stage_plan`에 arm별
`stage_id`, `kind`, `parent_stage_ids`를 동결한다. 허용 kind는 `source`, `retrieve`, `union`,
`canonicalize`, `filter`, `expand`, `rerank`, `select`, `present`이며 첫 단계는 `source`, 마지막
단계는 `present`다. 단계는 위상 순서로 저장하고 모든 parent는 앞선 stage여야 한다.

회수율의 정본 단위는 전 단계에서 동일한
`case_id + canonical article-root coordinate`다. raw route·subnode·별칭 중복은
`occurrence_counts`에 별도로 두고 canonicalization으로 줄어든 발생 수를 조문 탈락이나 gold
손실로 세지 않는다. 각 stage는 정렬된 exact identity 집합 `before`, `added`, `discarded`,
`after`와 모든 discard의 단일 primary reason receipt를 보존해야 한다. 검사기는 다음을
재계산한다.

canonical artifact root는 필수 schema 필드와 선택적인 `audit` object만 허용한다. 과거
backfill의 lineage·reconstruction 범위·요약은 `audit` 안에 두며, `artifact_sha256`은 이
`audit`까지 포함한 root 전체에서 자기 hash 필드만 제외하고 계산한다.

```text
before(stage) = union(after(parent))          # parent가 있을 때
after = (before ∪ added) \ discarded
gold_after = gold_before + gold_added - gold_discarded
golden_recall = gold_after / gold_total
```

count는 identity 집합 크기와 같아야 하고 discard receipt와 reason count는 discarded 집합을
100% 덮어야 한다. `discarded_gold`는 `{identity:{doc_id,node}, reason}`으로 exact gold loss와
이유를 보존한다. 모든 case의 `computed_post_selection=true`,
`gold_visible_to_product=false`를 검사하며, 최종 `present` stage에서 arm별
`presented_total/mean/p50/p95`, `golden_recall`, `selectivity`를 다시 계산해 manifest의 flat
요약과 대조한다.

v1-v3 완료 manifest는 소급 수정하지 않는다. 과거 artifact backfill은 새 ADR/run에서
`reconstructed` 또는 복원 불가 범위를 명시하며, exact snapshot이 없는 단계를 추정값으로
채우지 않는다.

정답률과 `answerable`, 실행 성공률, 원문 검증 통과율은 서로 다른 지표로 분리한다.

## 8. 결정 규칙

- `Accepted`는 사전 성공 기준을 충족하고, 분리된 평가에서 비열등성과 운영 비용을 함께 확인했을 때만 사용한다.
- 전체 점수가 같아도 신규 정답과 회귀가 상쇄된 경우 비열등으로 자동 판정하지 않는다.
- 소표본에서 개선이 없거나 회귀가 있으면 메인 배선은 `Rejected` 또는 `Proposed`로 남긴다.
- 법령 시행 버전과 기준답변 버전이 다르면 해당 사례를 성능 집계에서 분리하고 drift로 보고한다.
- 실패한 실험도 삭제하지 않는다. 왜 실패했는지와 재사용 가능한 진단 부품을 기록한다.
- 한 분기에서의 승리는 형제 분기의 결과를 소급 변경하지 않는다. 승격한 arm만 후속 ADR의 부모가 된다.

## 9. 생성·검사

루트 실험:

```bash
python scripts/adr_structure.py new \
  --number NNNN --slug example-root --title "예시 루트 실험" \
  --phase probe --branch-id A --candidate-arms B C \
  --owner "agent-name" --scope "예시 루트 실험 전체" --scope-key example-root \
  --questions cm-001 cm-002
```

B에서 갈라지는 후속 실험:

```bash
python scripts/adr_structure.py new \
  --number MMMM --slug example-b-children --title "B 후속 실험" \
  --phase probe --branch-id B-followup \
  --parent-manifest docs/adr/ADR-NNNN-example-root/실험/manifest.json \
  --parent-arm B --candidate-arms B1 B2 \
  --owner "agent-name" --scope "B 결과 이후 B1/B2 후속" --scope-key example-b-children \
  --questions cm-001 cm-002
```

여러 완료 arm을 합치는 ADR:

```bash
python scripts/adr_structure.py new \
  --number KKKK --slug merged-approach --title "두 완료 분기 통합" \
  --phase audit --branch-id merge-A-B --candidate-arms integrated \
  --merge-parent docs/adr/ADR-0072-example-a/실험/manifest.json accepted-arm merged_from \
  --merge-parent docs/adr/ADR-0073-example-b/실험/manifest.json accepted-arm merged_from \
  --related-adr docs/adr/ADR-0071-policy depends_on "적용할 운영 정책" \
  --owner "agent-name" --scope "A/B 완료 분기의 통합" --scope-key merged-approach
```

생성 직후 `integration.parent_contributions`, `conflicts` 또는 `no_conflict_reason`,
`common_invariants`, `rollback_ref`를 실제 내용으로 동결한 뒤 작업을 시작한다.

```bash
python scripts/adr_structure.py status \
  --path docs/adr/ADR-MMMM-example-b-children --status completed --note "검증과 기록 완료"
python scripts/adr_structure.py validate --path docs/adr/ADR-MMMM-example-b-children
python scripts/adr_structure.py validate --path docs/adr/ADR-MMMM-example-b-children --final
python scripts/adr_structure.py graph --adr-root docs/adr
```

일반 `validate`는 구조, 모델 정책, 부모 arm·hash, arm 내부 cycle과 v3/v4 선점 이력을 검사한다.
`--final`은 `TODO`, `PENDING` hash, 미실행 결과나 완료되지 않은 선점 상태가 남아 있으면
실패한다. `adr-experiment-v1`부터 v3까지는 과거 기록 검증을 위해 그대로 읽고,
ADR-0082 이후 새 scaffold는 v4를 생성한다. v4 graph·status·question 검증은 v3의
reservation·lineage·relationship 규칙을 그대로 상속한다.
