# GENOS 골든 관리·평가

## 상태와 연결

2026-09-16 추가한 `pipeline.py golden`은 현행 `term-runtime-v1` 전용 관리·평가 경로다.
골든은 평가기만 읽고, 제품 요청에는 질문·문서 범위·`use_llm`만 전달한다.
검색·선택·답변 엔진과 데이터 CURRENT를 변경하지 않는다.

실행 위치는 **GENOS 코드스페이스**다. `semantic_runtime.app.create_app`의 실제
`POST /v1/rag/ask` 라우트를 ASGI로 호출한다. 코드서빙과 같은 앱·엔진을 사용하지만,
배포 게이트웨이·워크플로우·채팅 바인딩을 통과한 테스트는 아니다.
그 결과를 배포 리비전 검증이나 현장 성능 확인으로 확대하지 않는다.

로컬에서는 모의 원문과 provider double로 평가 계약을 검사했다. 공개 법제처 해석례 골든의
원문 좌표 연결 예시도 만들었다. 내부 모델 호출·실제 내부 데이터 품질·GENOS 배포는 미확인이다.
골든 작성은 간단 CSV 또는 기존 골든 import와 오프라인 HTML 검토 화면을 사용한다.
LLM 자동 의미 채점은 없으며, 평가 결과 조회는 JSON/HTML이다.

## 파일 왕복 UI — SSH·포트 프록시 불필요

2026-09-16: 현장 사진에서 코드스페이스의 테스트 웹서버 `200 OK`, Jupyter
`/proxy/8899/`의 404, 확인한 확장 목록에 `jupyter_server_proxy`가 없는 상태를 확인했다.
사용자가 SSH는 내부 정책상 차단됐다고 전달했다. 파일 다운로드·업로드가 허용된 내부 PC를
대상으로 아래 경로를 제공한다. 현장 브라우저의 HTML 실행·JSON 다운로드는 아직 미확인이다.

1. 기존 `golden import`로 후보를 만든다. `review.html`과 `NEXT_STEPS.txt`가 생성된다.
   HTML에는 해당 문항의 후보 원문만 포함한다. 인터넷 연결이나 GENOS API 호출은 하지 않는다.
2. 허용된 내부 PC로 `review.html`을 다운로드해 브라우저에서 연다. 문항을 승인하고
   `검토본 JSON 내려받기`로 저장한다. 중단할 때는 `작업 저장`을 하고 같은 HTML에서 복원한다.
3. 검토본을 GENOS에 업로드하고 `receive`를 실행한다. **원래 authoring 폴더는 GENOS에 보존**한다.

```bash
python 06_TOOLS/pipeline.py golden receive \
  --authoring /현장/평가/작성-v1 --reviewed /현장/업로드/team-golden-reviewed.json \
  --generation /현장/선택세대 --output /현장/평가/검증-v1
```

`receive`는 원래 작성 묶음의 receipt·원문 세대·전체 문항·근거 그룹 역할·후보 범위와
기존 freeze의 승인·원문 구절 검증을 함께 수행한다. 문항을 삭제하거나 필수 근거 그룹을
줄인 파일은 거부한다. 결과는 `validation.html`, `validation.json`, 업로드 원본 보관,
receipt다. 모든 문항이 통과해야 `suite.json`을 생성한다. 오류가 있으면 종료 코드 2이며,
문항 ID별 수정 사항을 확인해 재승인 후 새 출력 폴더로 다시 수신한다. 기존 이력은 덮어쓰지 않는다.
손상된 원래 작성 묶음이나 잘못된 원문 세대 자체는 검증 보고서 생성 전에 실행 오류로 거부된다.
체크섬은 무결성·혼입 검사이며 전자서명이나 승인자 인증을 대신하지 않는다.

4. 생성된 suite로 아래 기존 `plan` → `run` 절차를 진행한다. 실제 평가에는 기존 ADR·내부
   모델·코드/데이터 고정 조건이 그대로 적용된다. UI가 평가 조건을 자동 승인하지 않는다.
5. 새 실행에는 `answer-review.html`도 생성된다. 이미 완료된 실행은 다음 명령으로 생성한다.

```bash
python 06_TOOLS/pipeline.py golden review-answers \
  --run /현장/평가/run-001-baseline --output /현장/평가/답변검토-v1
```

6. 내부 PC에서 답변 채점 HTML을 연다. 질문·기준답변·실제 답변·정답 구절·실제 검색/선택 원문·
   인용 ID·단계별 회수율을 함께 확인한다. 각 필수 내용과 동작 적절성·인용 뒷받침·근거 없는
   주장 여부를 `미판정/충족/미충족`으로 판정한다. 모든 판정과 검토자가 있어야 완료된다.
   완료 후 판정을 수정하면 다시 미완료가 된다. 실행 실패·문맥 밖 인용은 사람이 모두
   충족으로 표시해도 PASS로 바뀌지 않는다. 유효 답변이 없는 문항은 채점 불가로 보존한다.
7. `answers-reviewed.json`을 업로드하고 기존 `golden report --reviews ...`로 새 보고서를 만든다.
   작업 파일은 suite·실행 결과·답변 해시에 결속한다. 다른 실행의 작업 복원/채점본 혼입을 거부한다.
   미완료 판정은 최종 보고서에서 미검토다. `작업 저장` 파일과 `채점본` 파일은 구분한다.

현재 `navigation-loop-v1` 응답에는 이전 `term-agent-v1`의 첫 `search_results` 및
`after_evidence_ids`가 없을 수 있다. 해당 경우 최초·첫 확장은 **미측정**이며 0점이나
누적 회수율로 대체하지 않는다. 누적 지표는 응답의 candidates(새 탐색의 경우 읽은 원문)
기준이다. 서로 다른 엔진의 단계 점수를 같은 의미로 비교하지 않는다. 이번 UI 추가는
검색 엔진의 trace 계약을 변경하거나 미측정 지표를 새로 계측하는 작업이 아니다.

호출 연결: `pipeline.py golden` → `golden_exchange.receive/review_answers` → 기존
`freeze/apply_reviews/report`. 신규 모듈·HTML도 평가 plan의 코드 해시에 포함한다.
새 Python 의존성은 없다. 운영 코드·CURRENT·GENOS 배포를 자동 변경하지 않는다.
롤백 시 이 변경 이전 코드 리비전으로 복구하고 작성·업로드·검증·평가 파일은 보존한다.
코드 변경 후 기존 plan을 재사용하면 해시 검사로 거부되므로 기존 실험을 덮어쓰지 않고
표준에 따라 새 plan을 만든다.

## 사용자 작성 — ID를 직접 입력하지 않는 경로

1. `csv-template`로 양식을 만든다. Excel에서 문항ID·질문·기준답변·기준일·문서명·조문을
   입력한다. 여러 필수 근거는 같은 문항ID로 행을 추가하고 근거그룹을 다르게 쓴다.
   대체 가능한 근거들은 같은 근거그룹으로 쓴다. 참고 근거는 역할을 `reference`/`참고`로 쓴다.
2. `import --format csv`를 실행하면 선택 데이터 세대에서 문서명·조문·본칙/부칙을 대조한다.
   문서명은 정식 이름을 사용한다. 공백 차이를 제외한 별칭/유사 이름은 자동 확정하지 않는다.
3. `review.html`을 브라우저에서 열고 문항별 후보·기존 근거 구절·조문 전체를 확인한다.
   블록을 선택하고 정답 근거 구절과 답변 기준을 다듬는다. 검토자·확인 체크 후 문항을 승인한다.
4. 검토본 JSON을 내려받고 `freeze`로 서버의 원문·해시 검증을 통과시킨다.

```bash
python 06_TOOLS/pipeline.py golden csv-template --output /현장/평가/질문양식.csv
python 06_TOOLS/pipeline.py golden import --format csv \
  --input /현장/평가/질문양식.csv --generation /현장/선택세대 \
  --suite-id team-golden --version 1 --output /현장/평가/작성-v1
```

조문에는 `제35조제2항`도 입력할 수 있다. 시스템은 조문 후보를 찾되 항·호 정보와
기존 근거 구절을 보존한다. `구분`은 `body`/`본칙` 또는 `addendum`/`부칙`이다.
개정 시점은 자동 승인하지 않는다. 같은 이름의 여러 문서/부칙 후보는 사람이 선택한다.
원문이 없으면 `NOT_FOUND`, 기존 구절이 달라졌으면 `TEXT_MISMATCH`, 여러 후보면 `AMBIGUOUS`다.
유일한 후보도 `UNIQUE_CANDIDATE`일 뿐 승인 상태가 아니다.

HTML은 서버·인터넷 없이 실행되고 외부 전송을 차단한다. 파일을 닫으면 입력이 사라지므로
`작업 저장`으로 다운로드하고 다음에 `작업 불러오기`로 이어간다. 검토본 전체를 내려받으며,
미승인·미연결 문항을 자동 제외하지 않는다. 새 문항 추가나 없는 원문의 재매핑은 CSV 수정 및
재import로 수행한다. 내부 데이터의 HTML/작업 파일은 GENOS 내부에서 보관한다.

기존 골든 입력도 지원한다.

- `--format moleg --input 01_DATA/expc/index.json --labels 01_DATA/review/marked.json`:
  공개 해석례 질의·회답과 기존 결정 근거 태그. `decisive_full`의 항·호·구절·검토 이유 보존.
- `--format cm --input 01_DATA/review/cm_core_e2e_v3.json`: CM 기존 질문·기준답변·필수/동반/참고
  근거를 초안으로 변환. **실제 내부 자료 처리는 GENOS에서 실행**한다. 기존 승인으로 새 세대의
  검토를 자동 승인하지 않는다. v2/v3의 의미 차이와 별도 primary/companion 기준은 입력 기록에
  남기며, 새 도구의 그룹 회수율을 이전 점수와 같은 값으로 비교하지 않는다.

import 출력은 `questions.csv`, `draft.json`, `mapping.json`, `review.html`, `receipt.json`이다.
입력·원문 세대·파일 해시를 보존한다. 이는 골든 작성/매핑이며 RAG 성능 측정은 아니다.

## 골든 등록부 — CM·내규 묶음을 한 곳에서 관리

2026-10-07 사진의 Risk팀 질문 105문항을 `risk_cm`으로 등록했다.
[원본·외규 마킹·사용 범위](../../../../01_DATA/GOLDEN/risk_cm/README.md)와
[현재 공통 등록부](../../../../01_DATA/GOLDEN/registry-v2-risk_cm.json)를 따른다.
새 선택적 `--collection NAME CSV`는 기존 등록 명령에서 이름을 지정한 묶음을 읽는다.
`--annotations`의 `scope_assessment`는 외규 단독/부분/내규 필요/확인 필요 판정과 근거를
평가 메타데이터로 보존하며 제품 요청에 전달하지 않는다. 기존 `--cm`·`--internal`도 유지한다.
외규만 가능 3문항을 포함하여 risk_cm 전체는 아직 `question_only`이며 정답 승인·품질
실험·원문 반출 승인 상태가 아니다. 기준답변·날짜·필수근거 작성 전에는 import의 deferred에 남는다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py golden registry \
  --cm 01_DATA/review/cm_core_e2e_v3.json \
  --collection risk_cm 01_DATA/GOLDEN/risk_cm/v1/questions.csv \
  --annotations 01_DATA/GOLDEN/risk_cm/v1/annotations.json \
  --output /새/출력/등록부.json
```

골든 묶음은 각자 원래 작성 원본을 유지한다. CM은 `01_DATA/review/cm_core_e2e_v3.json`,
내규는 `RAW/internal/risk_team/.staging/internal-rules-20260916-v1/golden/내규_골든_질문셋.csv`다.
등록부는 두 원본을 다시 읽어 만든 **파생 파일**이다. 직접 고치지 않는다. 답변·근거를 채우려면
원본(내규는 CSV 또는 같은 열의 xlsx)을 수정하고 등록부를 새 파일로 다시 만든다.

```bash
python 06_TOOLS/pipeline.py golden registry \
  --cm 01_DATA/review/cm_core_e2e_v3.json \
  --internal ".../golden/내규_골든_질문셋.csv" \
  [--annotations 태그.json] --output 01_DATA/GOLDEN/registry-v2.json
python 06_TOOLS/pipeline.py golden registry-status --registry 01_DATA/GOLDEN/registry-v2.json
python 06_TOOLS/pipeline.py golden import --format registry \
  --input 01_DATA/GOLDEN/registry-v2.json --generation /현장/선택세대 --output /현장/평가/작성-v1
```

문항마다 `collection`(cm/internal), 단계, 막힌 이유를 계산한다.

| 단계 | 뜻 | import |
|---|---|---|
| `question_only` | 기준답변 없음 | 제외, `import_provenance.deferred`에 사유와 함께 기록 |
| `incomplete` | 답은 있으나 기준일·필수 근거 없음 또는 질문 전사 미완(`partial`·`uncertain`·`source_placeholder`) | 제외, 사유 기록 |
| `ready` | 질문·기준답변·기준일·필수 근거가 모두 있음 | 초안으로 변환 |

`ready`도 승인이 아니다. 이후 경로는 위의 review.html → receive/freeze와 같다.
경고(`transcription_unverified`, `duplicate_of:…`)는 막지 않고 검토 화면에 넘긴다.
원본 77·86행처럼 같은 질문이 두 행이면 둘 다 남는다. 묶음별 점수는 중복을 감안해 읽는다.

2026-09-18 첫 등록부(`01_DATA/GOLDEN/registry-v1.json`): 전체 156문항, CM 51문항 전부 `ready`,
내규 105문항 전부 `question_only`(실제 내규 원문·기준답변 미제공, 전사 미완 5문항).

**태그.** `--annotations`는 `{"문항ID": {"tags": ["reconciliation", "temporal"]}}`이다. 사람이 붙인다.
- `reconciliation`: 여러 규범을 함께 정리해야 답이 나온다(법↔시행령↔감독규정 위계, 특별법 우선,
  내규↔외규). freeze는 필수 근거가 서로 다른 문서 둘 이상에 걸쳐야 통과시킨다.
  등록부의 `signals.required_documents`는 후보 신호일 뿐이다(CM 51문항 중 22문항이 2문서 이상).
- `temporal`: 개정·시행일·부칙 경과규정이 답을 가른다.

`collection`과 `tags`는 초안 → 검토 → suite까지 문항에 붙어 간다. 제품 요청에는 들어가지 않는다.
`report`는 전체 요약 외에 `by_collection`·`by_tag`로 같은 지표를 나눠 낸다.
작은 층일수록 두 판 사이의 노이즈 폭이 크므로 층별 비교도 같은 코드 두 판으로 폭부터 잰다.

## 입력과 산출물 계약

| 단계 | 입력 | 출력 / 소비자 |
|---|---|---|
| catalog | 명시한 원문 세대와 결속된 navigation index | 문서 버전·조문·원문 블록·해시 목록 / 골든 작성자 |
| template | 없음 | `term-golden-v1` 초안 / 골든 작성자 |
| freeze | 사람이 승인한 초안 + 선택 세대 | 해시 고정 suite / plan·오프라인 scorer |
| plan | suite + 같은 세대 + 진행 중 ADR의 run/arm + 내부 모델 ID | 코드·설정·세대·suite·ADR 해시 고정 plan / runner |
| run | 변경되지 않은 plan + GENOS 환경 | 요청·원응답·점수·provider 기록·검토 양식·보고서·receipt |
| report | 무결성 확인된 run + 선택적 사람 검토 | 새 경로의 JSON/HTML 보고서 |

진입점: `06_TOOLS/pipeline.py golden`.
구현: `lawrag.pipeline.golden`, `lawrag.pipeline.golden_run`.
`PIPELINE.json.authorities.golden_evaluation`이 이 운영 계약을 가리킨다.
평가기는 `legal-rag` 엔진 그래프 밖에 있으며 산출물을 제품 검색/답변에서 읽지 않는다.

모든 출력 파일은 기존 파일이 있으면 실패한다. 수정 시 초안의 다음 버전을 만들고 새 suite로
고정한다. 원문 재구축 시 예전 `source_id`를 무조건 재사용하지 말고 새 catalog에서 문서
버전·본문·좌표를 다시 대조한다. 자동 유사 매칭·LLM 조문 승인 기능은 없다.

## 골든 작성·조문 지정

GENOS에서 선택 세대와 평가 저장 위치를 명시한다. 아래 `python`은 현장 코드스페이스의
프로젝트 Python이다. WSL 개발에서는 `.venv/bin/python`을 사용한다.

```bash
python 06_TOOLS/pipeline.py golden catalog \
  --generation /현장/선택세대 --output /현장/평가/catalog-v1.json
python 06_TOOLS/pipeline.py golden template --output /현장/평가/draft-v1.json
```

초안의 문항에는 다음을 기록한다.

- `id`, `question`, `as_of`: 문항 ID·질문·적용 기준일. 기준일은 평가 메타데이터다.
  필요한 시간 조건은 실제 질문에도 쓰고, 그 시점에 맞는 문서 버전을 담당자가 지정한다.
- `document_ids`: 사용자가 제품에 실제 지정할 문서 범위. 빈 배열은 세대 전체다.
  정답을 아는 평가기가 정답 문서만 남겨 검색을 쉽게 만들어서는 안 된다.
- `expected_behavior`: `answer`, `ask_user`, `abstain`.
- `required_points`: 필수 결론·조건·예외 또는 추가 질문/유보 기준.
- `evidence_groups`: `required` 필수 근거와 `reference` 참고 근거. 필수 그룹 간은 AND,
  각 그룹의 `any_of`는 OR다. 여러 조문이 모두 필요하면 그룹을 각각 만든다.
- 각 근거의 `source_id`, `document_id`, `source_artifact_sha256`, `block_id`, `quote`는
  catalog에서 복사한다. `locator`에는 본칙/부칙과 조·항·호 등 사람이 확인할 표기를 남긴다.
- `review.status=approved`, `review.by`, ISO 형식 `review.at`: 담당자의 검토 완료 기록.

freeze는 승인·날짜·중복 ID·문서 범위·원본 해시·원문 구절의 정확한 블록 포함 여부를 검사한다.
현재 ID 존재만으로 개정 전후 법적 동등성을 승인하지 않는다. 적용 버전의 적합성은 담당자
검토 책임이며, 계정 인증/전자서명 기반 승인 시스템은 아니다.

```bash
python 06_TOOLS/pipeline.py golden freeze \
  --draft /현장/평가/draft-v1.json --generation /현장/선택세대 \
  --output /현장/평가/suite-v1.json
```

정답 문서 미수록·해시 불일치·근거 구절 불일치 시 freeze를 거부한다. 해당 문항을 삭제해서
성능을 높이지 말고 원문 반입/매핑을 먼저 해결한다. 모든 문항의 검증이 통과해야 실행한다.

## 평가 계획과 실행

실제 성능 측정 전 [실험 표준](../../../../04_EXPERIMENTS/LEGACY_ADR/STANDARD.md)과
[실험 지침](../../../../04_EXPERIMENTS/LEGACY_ADR/EXPERIMENT_AGENT_PROMPT.md)을 끝까지 따른다.
동일 scope reservation을 먼저 확인하고 stable runner의 `adr_structure.py new --adr-root
04_EXPERIMENTS/ADR ...`로 선점한다. 질문·성공 기준·전체 파이프라인·모델·stage plan·run/arm을
동결한다. 현장 내부 모델은 외부 Gemini 실험과 구분해서 명시한다.

이 도구는 ADR을 자동 생성·완료·승격하지 않는다. `plan`은 진행 중 reservation, 사전 기준
동결 표시, run/arm 존재를 확인하는 최소 gate다. 표준의 모든 요구를 자동 승인하는 validator는
아니다. 운영 승격 자격과 표준 stage-ledger artifact는 별도 표준 검사 대상이다.

환경: `SEMANTIC_LLM_BACKEND=genos`, `GENOS_BASE_URL`, `GENOS_LLM_SERVING_ID`,
`GENOS_LLM_KEY`. 키를 명령 인자나 골든 파일에 쓰지 않는다. plan은 키를 저장하지 않는다.
provider의 `/models` 응답에서 사용할 정확한 내부 모델 ID를 `--model`로 지정한다.

```bash
python 06_TOOLS/pipeline.py golden plan \
  --suite /현장/평가/suite-v1.json --generation /현장/선택세대 \
  --adr-manifest 04_EXPERIMENTS/ADR/ADR-NNNN-example/실험/manifest.json \
  --run-id run-001 --arm-id baseline --model 내부모델ID \
  --output /현장/평가/plan-v1.json
python 06_TOOLS/pipeline.py golden run \
  --plan /현장/평가/plan-v1.json --output /현장/평가/run-001-baseline
```

plan 이후 코드·환경·ADR·suite·세대가 바뀌면 실행을 거부한다. 모델 ID도 첫 질의 전에 검증한다.
모델이 없을 때 원문 조회나 외부 모델로 자동 대체하지 않는다. 실제 provider 요청·원응답은
`providers/`에 저장되고 전체 파일 해시는 `receipt.json`에 결속된다.
각 문항의 원응답 저장 후 오프라인에서 정답을 결합한다. 문항 오류가 나도 나머지를 계속하고,
실패 문항을 분모에서 조용히 제외하지 않는다. 키를 포함할 수 있는 예외 메시지를 점수 파일에
복사하지 않고 예외 유형만 기록한다.

이 경로는 코드스페이스의 현재 작업 코드로 실행하며 `GENOS_GENERATION`이나 로컬 활성 포인터를
자동 선택하지 않는다. 배포된 코드서빙과 비교할 때는 plan의 코드 해시·원문 세대·모델을 배포
리비전과 별도로 대조한다. 운영 채팅과 배치 평가가 모델 자원을 공유한다면 실행 시간을 조정한다.

## 결과와 답변 검토

`report/report.html`을 열면 문항별 다음 지점을 볼 수 있다.

1. 최초: 첫 라운드 `search_results`.
2. 첫 확장: 첫 라운드 `after_evidence_ids` — bounded prefetch 포함.
3. 누적: 모든 탐색의 `retrieval.candidates`.
4. 선택: `assembly.context`.
5. 인용: `answer.claims[].source_ids`.

회수율은 필수 근거 그룹 중 한 개 이상의 대체 근거를 확보한 그룹 비율이다. 점수는 조문
존재 기준이다. freeze에서 지정한 항·호 원문이 답변 주장을 뒷받침하는지는 사람 검토로 판정한다.
첫 검색 trace가 없으면 미측정이며, 용어 미해결이 명시된 정상 종료만 실제 0건으로 기록한다.
답변 유보 문항처럼 필수 근거 그룹이 없으면 회수율은 해당 없음이다.
누적→선택, 선택→인용에서 빠진 필수 그룹도 상세 결과에 남긴다.

원응답 `cases/NNNNN/response.json`, 점수 `score.json`, 전체 `rows.json`을 함께 확인한다.
`reviews-template.json`을 **별도 파일로 복사**해서 문항별 다음을 검토한다.

- `required_points_met`: 각 필수 내용 충족 여부.
- `behavior_correct`: 답변/추가 질문/유보 선택이 맞는지.
- `citations_supported`: 인용 원문이 실제 주장을 뒷받침하는지.
- `no_unsupported_claims`: 근거 없는 주장이 없는지.
- 검토자 `by`, 검토일 `at`, 사유 `notes`.

모든 판정은 true/false다. null과 빈 검토자는 미검토다. 검토는 suite와 답변 해시에 묶이므로
다른 답변을 재채점한 파일을 섞으면 실패한다. 사람 검토가 전부 통과해도 실행 실패나 context
밖 ID를 인용한 구조 오류가 있으면 PASS가 아니다. 일반 문체 일치나 문자열 유사도로 정답을
자동 승인하지 않는다.

```bash
python 06_TOOLS/pipeline.py golden report \
  --run /현장/평가/run-001-baseline --reviews /현장/평가/reviews-v1.json \
  --output /현장/평가/reviewed-report-v1
```

보고서는 전체 문항 수, 실패/미측정, 검토 수, 검토 완료 기준 정답률, 전체 문항 기준 확인된
정답 비율을 나눠 표시한다. 단계별 평균 회수율은 실제 측정 문항 수를 함께 제공한다.
지연 p50/p95는 문항 전체 경과 시간이고, gateway latency나 동시 부하 성능이 아니다.

## 중단·재실행·검증·롤백

- 동일 ADR experiment/run/arm은 출력 경로를 바꿔도 한 번만 실행한다. 실행 선점은 ADR의
  `실험/golden-<hash>.claim.json`에 남는다. 중단된 실행도 삭제하거나 선점을 지우지 않는다.
- 자동 재개는 없다. 중단까지의 원시 파일을 보존하고, ADR 표준에 따라 새 run 또는 새 ADR에
  재실행을 사전 기록한 뒤 새 plan을 만든다. 완료 후 재평가는 새 ADR이다.
- `receipt.json`이 없으면 완결된 run이 아니다. 실행 도중 전체 코드/세대가 바뀐 경우에도
  원시 기록만 남기며 완료 receipt를 발행하지 않는다.
- 실제 실험의 모델 사용량·정확한 입력·전체 파이프라인 결속·stage ledger·사례별 기록과
  통계를 ADR 산출물에 연결한 후 stable runner `validate --final`, `graph`를 수행한다.
  이 도구의 `receipt`만으로 실험 종료나 MAIN 승격을 보고하지 않는다.
- 생산 코드/데이터 선택을 바꾸지 않으므로 실행 취소에 CURRENT 롤백은 필요 없다.
  코드 도입을 되돌릴 때 CLI 분기와 신규 두 모듈을 이전 코드 리비전으로 복구하고,
  suite·실행·검토 이력은 보존한다.
- 내부 질문·원문·답변·보고서는 GENOS 내부의 접근 통제된 저장소에 둔다.
  HTML은 외부 스크립트/네트워크를 쓰지 않지만 민감 원문을 포함한다.

개발 계약 검사:

```bash
.venv/bin/python -m pytest 05_TESTS/CONTRACTS/test_golden_system.py -q
```

이번 개발 검사는 합성 fixture의 관리·채점·배선 검사이며 신규 RAG 품질 실험이 아니다.
