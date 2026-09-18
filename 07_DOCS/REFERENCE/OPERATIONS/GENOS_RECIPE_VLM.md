# MAIN PDF 구간별 구조화 틀·bbox 검수

## 2026-09-17 v37: 기업공시 복합 조문·작성지침과 호출 예산 진단

`genos-recipe-v37-disclosure-budget-diagnostics`. 기존 `build-data-stages → ingest →
revise_pdf → recipe_basic.seed` 연결에서 복합 조문 표제와 독립 `【 작성지침 】`이 함께
관측되면 `structure/templates/disclosure_v1.json`의 부분 계층 순서를 선택한다.
일반 조·항 문서는 기존 basic 틀을 사용하고 명시적 사용자 hints는 우선한다.

- `제2-1-1조`·`제2-1-1조의2`를 하나의 원문 마커와 서수로 읽는다. `제N부`도 인식한다.
  부→장→절→조→항→작성지침→소문자 로마 항목의 부분 순서를 제공하며 나머지는 기존
  구조 엔진이 결정한다. 항이 없는 조의 작성지침은 열린 상위 조 아래에 둘 수 있다.
- 작성지침의 독립 표제만 인식하고 본문 속 언급과 표 셀은 표제로 추가하지 않는다.
  앞 본문과 같은 블록인 표제는 `writing_guidance_shares_source_block`으로 남긴다.
  PDF 읽기 순서·병합 표·지침의 실제 적용 범위는 파서·VLM 검수 대상이다.
  이 변경이 원문 순서나 표 셀을 추정해서 복원하지는 않는다.
- 원문 SQLite와 용어 색인 계약을 유지한다. 명시 참조 색인 및 용어집 정의 후보의
  조문 패턴도 여러 하이픈을 지원한다. 이전 구조화/색인은 새 코드와 새 run ID로 재구축한다.
  두 틀 파일과 코드가 구조화 지문에 결속되어 이전 검수 승인을 재사용하지 않는다.
- `review-budget.json`과 `recipe.review.budget`에 페이지 수·묶음 크기·새 전체 검수의
  최소 호출 수·문서 호출 상한을 기록한다. 재개 시 재사용 가능한 승인을 차감한 견적은 아니며,
  본문 확인·수정·재검수·논리 재요청은 이 최소치 외에 호출을 소비한다.
- `model_call_budget_exhausted`는 **문서별 호출 횟수 상한**이다. 입력 문맥 초과
  `document_context_budget_exceeded`, 출력 잘림 `OUTPUT_LENGTH_LIMIT`과 다르다.
  기본 1쪽/창·64회로는 404쪽 전수 검수가 불가능하다. 예를 들어 4쪽/창·128회 설정은
  첫 검수 최소 101회와 추가 27회 여유를 주지만, 전체 수정·재검수 완료를 보장하지 않는다.
  `MAX_CALLS` 허용 범위는 1–256이며 기본값은 올리지 않았다.
- 예산 소진 이후 남은 창마다 반복하던 경고를 한 번으로 합치고 모든 미검수 페이지를
  `coverage.review_warnings`에 남긴다. 같은 설정으로 재개해도 이 경고를 승인하거나
  자동으로 추가 호출하지 않는다. 재검수가 필요하면 설정을 명시하고 새 run ID로 구축한다.

검증 범위는 작성한 모의 문서의 계층·원문 보존·참조 연결과 모의 HTTP 검수/예산/재개 계약이다.
실제 404쪽 전체 파싱·모델 검수 품질과 GENOS 배포는 미확인이다. MAIN/CURRENT는 변경하지 않는다.

## 2026-09-17 v36: thinking 끄기 요청과 원응답 보존, 부칙 인식

`genos-recipe-v36-direct-response`. GENOS 구조화의 모든 시각/본문 확인/수정 요청에서
`LLM.structured(enable_thinking=False)` → `chat_template_kwargs: {enable_thinking: false}`를
실제 HTTP 본문에 넣는다. JSON Schema를 거부해 prompt 모드로 재시도해도 이 옵션은 제거하지 않는다.
이는 요청의 설정이며 서버가 옵션을 무시하는지 여부는 현장 응답으로 확인해야 한다.
서버가 해당 요청을 거부하면 기존 v35 경고 처리로 기록하며 옵션을 몰래 빼서 재호출하지 않는다.

- `raw_response`: `delta.content`를 합친 원문. `<think>`·코드 울타리·머리말을 제거하기 전 내용이다.
  파싱용 JSON 정리는 별도로 수행한다. 응답 중간 연결 실패에서도 수신한 내용을 보존한다.
- `provider_response`: JSON으로 디코딩한 서버 SSE 이벤트를 필드 변경 없이 보존한다.
  별도 `reasoning_content`, finish reason, 공급자 사용량 상세 등이 왔으면 함께 남는다.
- `call-*-provider-response.json`: 위 수신 이벤트만 담은 파일. 요청 프롬프트와 섞지 않는다.
- `provider_usage`: 공급자가 반환한 usage 객체. 추론 토큰 상세가 없으면 임의로 추정하지 않는다.
- 이 변경은 응답을 만들어내거나 토큰 카운트를 조정하지 않는다. 내용이 전혀 오지 않았다면 빈 답변으로 남고,
  수신한 다른 필드와 오류를 통해 원인을 확인한다. v35의 출력/호출 상한과 경고 포함 통과를 유지한다.

부칙 인식은 줄 단위로 공백·`부 칙`·`[부칙]`·`〔부칙〕`·날짜/시행일 괄호를 처리한다.
`부칙에 따라`·`부칙을 적용`·`[부칙]에 따른` 같은 본문은 표제로 만들지 않는다.
같은 원문 블록에 앞 문장/다른 표제가 합쳐진 부칙은 후보 위치를 보존하고
`supplementary_heading_shares_source_block` 경고로 통과한다. 원문 블록을 임의로 잘라
빈/겹치는 구조 마디를 만들거나 문장의 소속을 확정하지 않는다. 파서 블록 분리는 별도 확인 대상이다.

검증은 모의 HTTP/SSE와 기존 목업 계약 검사다. 실제 GENOS thinking 해제 효과·속도·품질은 미확인이다.

## 2026-09-17 v35: 원문 보존 + 경고 포함 통과

현행 `genos-recipe-v35-warning-tolerant`는 사용자 요청에 따라 구조 완성도 100%를 요구하지 않는다.
`STRUCTURE_RECIPE_PROTOCOL=basic`, `STRUCTURE_RECIPE_ACCEPT_WARNINGS=on`이 기본이다.
아래 v34 이하 기록의 **보류 후 전체 실패/겹치는 창 분할** 설명은 현행 기본 모드에 적용하지 않는다.

- 기본 한 페이지의 원본+박스 이미지 2장씩 검수한다. `MAX_PAGES`로 묶음을 늘려도 창을 겹치지 않는다.
  페이지 경계 관계는 단일 이미지에서 불확실할 수 있으므로 미확인 사항으로 남긴다.
- 모델 요청 출력은 `min(STRUCTURE_RECIPE_MAX_TOKENS, STRUCTURE_RECIPE_REVIEW_MAX_TOKENS)`.
  후자 기본값은 1024이며 basic 시각/본문 확인/수정 호출에 적용한다. 한도 설정이 실제 출력 잘림을
  없애는 것은 아니다. 잘림·응답 형식 실패·VLM hold/missing_rules/source_error·호출 예산 소진 시
  마지막 구조를 보존하고 `coverage.review_warnings`에 원인과 페이지를 기록한다.
- 상태는 `accepted_with_warnings`; 시각 승인 상태와 구분한다. 경고 창을 승인으로 재사용하지 않는다.
  동일 소스·설정 checkpoint 재개 시 경고는 경고로 유지하며 완료된 창을 다시 호출하지 않는다.
- 기본 문서 수정 2회, 총 모델 호출 64회. 예산 소진 뒤 이미지 렌더/모델 호출을 더 하지 않는다.
  실제 규칙을 수정하면 기존 검수 기록을 무효화하고 현재 규칙을 다시 검토한다.
- `genos_build._ingest_files → preserve_unowned_source → validate_structure → source_jobs`에서
  제목·머리말 등 미소속 원문 구간을 `unstructured_text`로 보존한다. 원문·기존 마디 ID·좌표·점수는
  유지하고 신규 구역/소속만 추가한다. 조문이나 표제로 판정했다는 의미가 아니다.
- 기존 기본 내규 PROFILE의 장>절>조 제약은 장·절 없는 조·항 문서에서 authored basic을 막지 않는다.
  다른 번호 체계와 명시적 사용자 ladder hints는 기존 엔진 경로를 보존한다.
- 입력 원문/OCR 누락, 빈 원문, 좌표 범위 오류, 부모 순환, 원문/결과 해시 불일치는 계속 오류다.
  `STRUCTURE_RECIPE_ACCEPT_WARNINGS=off`로 이전 엄격 검수를 선택할 수 있다.

로그: 실행 폴더의 `detail.log`, `progress.log`, `doc-status.html`; 문서별
`structure-recipe-runs/<run-id>/events.jsonl`, `coverage.json`, `review-warnings.json`,
`call-*-input.json`, `call-*-response.json`. 입력 로그에는 요청 출력 상한도 기록한다.
최종 문서 `result.json`의 `source_preservation`, `meta.json`의 `structure_admission.warnings`가
저장 결과의 미확인 사항이다. MAIN/CURRENT 자동 승격은 하지 않는다.

로컬 검증은 HTTP 모의 응답과 기존 5개 모의 문서의 저장 계약 검사다. 새 Gemini 성능 실험,
GENOS 내부 모델 호출 및 현장 배포는 수행하지 않았다. 토큰·지연의 실제 개선율은 미확인이다.

## 2026-09-16 이전 v34 기록

### v34: 직접 작성한 틀을 basic 기본값으로 적용

`genos-recipe-v34-authored-basic`, 기본 `STRUCTURE_RECIPE_PROTOCOL=basic`.
사용자가 직접 작성한 목업 틀을 basic으로 지정했다. 정본은
`02_BACKEND/lawrag/core/structure/templates/basic_v1.json`이다.
`recipe_pages.run → recipe_basic.seed → recipe_regions.build`에서 모델 호출 전에 적용한다.
제N조는 최상위, 원문자 항은 해당 조의 하위, 별첨·부칙은 독립 최상위이며,
문장 중간의 인용·소수는 위치 조건으로 제외한다. 원문·표의 소속은 기존 엔진이 계산한다.
`recipe.basic.ready`의 reason이 `basic-v1:`로 시작하면 이 틀이 선택된 것이다.

조 표제가 없거나 이 틀 밖의 번호 체계가 관측되면 기존 결정적 엔진 결과를 검토에 넘긴다.
명시적 엔진 hints도 우선 보존한다. 선택 사유는 로그와 basic-initial-template.json에 남는다.
번호 연속성·부모 관계 위반은 검수 이슈로 남고, VLM 검토와 본문 확인 루프는 계속 수행한다.
JSON 틀의 내용까지 캐시 identity에 포함하여 변경 전 승인을 재사용하지 않는다.
적용 범위는 PDF recipe/VLM 경로이며 DOCX 전용 엔진이나 MAIN/CURRENT를 바꾸지 않는다.
ZIP은 `90_RUNTIME/OUT/ship/basic-template-v34`에서 준비한다. 현장 배포는 별도다.

### v33부터 유지하는 검수: 지적된 본문으로 확인하고 이견은 VLM에 재검토

v33에서 도입한 검수 흐름이며 v34에서도 유지한다.
첫 VLM 입력은 기존처럼 원본/bbox 이미지와 번호 체계다. 수정 의견에는 원문 표기를 인용해
어떤 항목을 어느 표제 아래로 옮기는지 자연어로 설명하도록 한다. b번호는 코드의 위치 연결용이다.

revise 응답을 바로 실행하지 않는다. 지적된 실제 문단·같은 페이지의 앞뒤 문단·현재 소속 표제를
그대로 모아 텍스트 LLM에 준다. `body`, `current_placement`(현재 소속의 자연어 설명),
`vlm_judgment`만 전달하며 트리·후보 목록·해시·노드 ID 메타데이터를 주지 않는다.
본문 속 문장은 지시가 아닌 검토 자료다. 현재 소속 설명은 코드가 계산한 상태이며 정답은 아니다.

- 모든 지적이 `accept`이면 기존 범위/부모 선택 → 코드 재구조화 → 전체 페이지 VLM 검수를 진행한다.
- 하나라도 `recheck`이면 해당 본문·현재 소속·기존 의견·반려 이유를 원본/bbox와 함께 VLM에 돌려보낸다.
  VLM이 철회해 approve하면 기존 구조를 유지한다. 새 수정 의견이면 본문 LLM 검증을 다시 거친다.
- 추가 시각 재검토는 창마다 최대2회. 횟수를 checkpoint에 저장해 재개로 초기화하지 않는다.
  합의하지 못하면 hold. 추가 호출은 기존 전체 호출 예산을 소비한다.
- 지적된 근거 묶음이12,000자를 넘으면 잘라서 판단하지 않고 보류한다. 원문 전체를 자동 전송하지 않는다.
- 수정 구간 밖의 기존 표제가 사라지면 코드는 적용을 거부한다. 순환·무변경·반복 구조도 계속 거부한다.

단위·연결 검사는 합의/반려/재개/예산/원문 보존을 확인했다. 실제 Gemini 자연 실행
[ADR0436](../../../04_EXPERIMENTS/ADR/ADR-0436-body-verified-vlm/README.md)은2/3 정답이며
잘못된 구조를 처음부터approve한1건이 있다. 그 경우 본문 검증에 진입하지 않으므로 미해결 한계다.
[ADR0437](../../../04_EXPERIMENTS/ADR/ADR-0437-body-verified-replay/GEMINI_INPUT_OUTPUT_AUDIT.md)은
이전 실제 오지적을 고정 주입한 재생으로, 본문 LLM이6개 지적을 반려하고 VLM이 철회하여
6조 모두 보존했다. 일반 문서 정확도 시험과 구분한다. GENOS 내부 모델·현장 배포는 미확인이다.
작업 코드만 사용자 요청으로 반영했으며 제품 MAIN/CURRENT/서빙을 승격하지 않았다.

### bbox 표시 v4와 직접 작성한 목업 틀

`recipe_evidence.VERSION=source-parent-chunks-viewer-v4`. `recipe_pages`의 기존
`review_images` 호출 경로에 적용된다. 원본 이미지는 유지하고 오버레이에는 왼쪽 라벨
여백을 추가한다. 표제는 굵은 실선, 본문·표는 점선이며 글자를 덮는 라벨 배경을 제거했다.
`HEAD n… L… parent=…`는 표제와 부모, `BODY/TABLE in n…`은 해당 표제 소속을 뜻한다.
기존 뷰어에서 소속이 있는 본문에 `n=none`을 붙이던 표시를 바로잡았다.
`owner=none`은 실제 뷰어 소속이 없을 때만 쓴다. 원본/bbox 두 장 구성을 유지하고 긴 변은
1,600px 이하로 제한한다. 오버레이 이동·배율은 `evidence.json.images[].transform`에 기록한다.
basic VLM 지시도 새 범례를 사용한다. 기존 코드 해시 결속으로 이전 승인 캐시와 구분한다.

`05_TESTS/FIXTURES/structure/mock_internal_rules_v1.json`은 목업 5종을 읽고 직접 작성한
명시 선택용 틀이다. 조 → 원문자 항, 별첨·부칙 최상위, 문장 중간 인용·소수 제외를
기존 `recipe_visual_loop.build`로 실행했다. 전체 202개 표제, 일반 본문 21개, 표 7개의
소속을 작성 원문에서 구한 기대값과 확인했다. 이후 사용자 지시로 v34의 basic 기본값에 연결했다.
재현 스크립트는 `90_RUNTIME/OUT/reports/mock-structure-human-v1/build_examples.py`,
결과는 같은 경로의 `examples/REPORT.md`다. 재실행할 때는 새 출력 디렉터리를 인자로 준다.
이 작업은 외부 모델 호출 없는 구현·계약 확인이며 새 Gemini 품질 실험이 아니다.
기존 합성 PDF의 오른쪽 글자 잘림·표 머리글 중복은 남아 있다. GENOS 배포는 미확인이다.

### v32 당시: 이미지와 사용 가능한 번호 체계만 전달

`genos-recipe-v32-image-pattern-review`, `STRUCTURE_RECIPE_PROTOCOL=basic`.
원본/bbox 이미지 쌍과 `{"available_patterns":["제N조 / 제N조의M", "가. 나. 다. … 하.", ...]}`만
VLM 입력으로 전달한다. 원문 텍스트, recipe, 현재 트리, 후보, 관측/선택 개수, visual_evidence,
해시와 파일 경로는 코드의 검증·감사·재개 상태에만 남는다. 짧은 system 지시에는 이미지 쌍의
페이지 순서와 b/n/L/p 라벨 설명을 포함한다. schema도 기존 LLM 전송 계약을 따른다.

VLM 응답은 `verdict`, `corrections`, `summary` 세 필드다. 정상 관찰은 summary에만 쓰고
approve의 corrections는 비어야 한다. 오류는 이미지의 page/b번호와 원하는 변경을 적는다.
누락 표제를 지적할 수 있도록 아직 표제가 아닌 블록에도 `b번호 n=none`을 그린다.
좌표나 번호를 읽을 수 없으면 hold이며, 보이지 않는 블록/다른 페이지를 인용하면 재질문한다.

긍정 의견을 오류로 전환하던 의견별 accept/reject 및 별도 review_action 호출을 basic 경로에서
제거했다. 명시적 VLM approve는 코드 오류가 없을 때만 해당 창 승인으로 연결한다.
코드 오류가 있으면 로컬 감사 파일에 남기고 hold한다. 최종 전체 구조 검증은 유지한다.

revise일 때만 두 번의 **텍스트 전용** LLM 호출을 한다. 범위 선택에는 수정 의견·허용 구간/경계,
부모 선택에는 수정 의견·F1/F2의 짧은 번호 표기 예시만 준다. 이 두 단계에 이미지나 본문을
다시 보내지 않는다. 코드는 틀을 원문에 적용하고 순환·무변경·과거 구조 반복을 거부한다.
변경 후 원본/새 bbox로 전체 페이지 재검수하며, 상태 해시와 이미지 결속은 코드가 유지한다.

v32의 ADR0435 Gemini 실측은 모의3건 중2건 성공, 입력60,444토큰이었다. 긴 본문에서는
오지적 후 구간 분할로 제6조가 누락돼 보류됐다. 앞선 ADR0434는 v31 실패 기록으로 보존한다.
각 버전의 기록을 새 코드의 결과로 바꾸지 않는다. GENOS 현장 품질은 미확인이다.

### v31 당시: basic 결과부터 검수하고 코드로 재구조화

`genos-recipe-v31-basic-first-review`의 기본 프로토콜은 `STRUCTURE_RECIPE_PROTOCOL=basic`이다.
실행 순서는 다음과 같다.

1. 기존 `pipeline.interpret(llm=None)`이 원문 전체로 basic 구조를 만든다. 사용자 구조 힌트도
   보존한다. 초기 모델 호출 없이 이 트리의 bbox를 만든다. `baseline.json`이 최초 결과다.
2. 원본/오버레이 이미지와 실제 구조 요약, 해당 페이지의 짧은 원문 근거, 현재 registry의
   지원 체계 목록을 VLM에 보낸다. 지원하지만 미선택인 체계와 관측된 후보를 함께 안내한다.
   등록되지 않은 표기를 지원한다고 주장하거나 새 Python/정규식을 생성하지 않는다.
3. VLM 의견을 LLM이 하나씩 근거와 대조한다. approve/hold/missing_rules/source_error 조건은
   유지하고, 수정이 필요한 경우에만 수정 범위와 부모 관계 `parents`를 받는다.
4. 코드는 해당 원문 구간을 기존 인식기로 다시 검사해 실제 존재하는 가족 ID만 제시한다.
   LLM은 F1/F2/ROOT 사이 관계만 선택한다. 마커 모양·서수 해석은 코드가 담당한다.
   위치 규칙은 source_style 또는 line_start_or_parent_title, 번호 순서 강제는 unordered로
   컴파일한다. 부모 선택만으로 연속 번호 제약을 새로 추정하지 않는다.
5. 코드는 틀을 해당 구간 전체에 적용해 트리를 자동 재생성한다. 인접 원문 구간과 원문 텍스트를
   보존하고, 변경 후 모든 이전 승인을 무효화하여 새 bbox로 전체 페이지를 다시 검수한다.
   확정된 틀은 모델 호출 없이 동일한 트리로 재실행 가능하다.

모델에는 전체 문서 `source_blocks`를 넣지 않는다. 검수는 최대 3쪽 창에서 진행하며 원본
이미지는 해당 페이지 전체다. 텍스트는 블록별 최대 96자, 블록 수에 따라 더 줄인 접두부이고
`text_truncated`와 `text_scope`로 불완전 근거임을 명시한다. 긴 본문은 코드와 감사 파일에만
보존한다. 필수 내용을 이미지에서도 읽을 수 없으면 보류한다. 입력 JSON은 기본 24,000자
(`STRUCTURE_RECIPE_REVIEW_MAX_CHARS`)로 제한하고, 기존 MAX_CHARS보다 크게 허용하지 않는다.
입력/출력 초과 시 창을 겹쳐 분할하며 2쪽 이하에서 계속 실패하면 한도 원인으로 중단한다.
전체 페이지 및 인접 페이지 쌍을 검수 범위에서 빼지 않는다.

`supported_methods`는 실제 registry와 구성된 custom 규칙에서 생성한다. 관측/선택 개수와
표기 예시만 보내고 임의 실행 코드는 보내지 않는다. 기본 한글 인식기는 `가. … 하.`이며
`ㄱ. ㄴ. ㄷ.`를 새로 지원하도록 바꾼 것은 아니다. 미지원 표기는 규칙 확장 대상으로 보류한다.
정본 원문·이전 완료 세대·기존 발송 ZIP은 보존한다. 코드/프로토콜/선언 어휘 해시가 캐시와
결속되어 이전 버전의 승인이나 변경 전 어휘를 재사용하지 않는다.

신규 기본 경로에는 전체 원문으로 구간을 먼저 감지하거나 가족별 규칙을 처음부터 생성하는
단계가 없다. 이전 compact/legacy 계약은 명시 선택 시만 존재하며 자동 fallback은 없다.
현장 명령에 protocol=basic을 명시하고 새 run ID로 실행한다. 데이터/CURRENT/서빙은 별도이며
이 교체로 자동 활성화하지 않는다. 로컬 합성 응답 계약 검사 224개 통과, 실제 GENOS 모델의
품질·지연·완료율은 현장 확인 전이다.

### v30에서 도입한 소형 모델용 응답 분리

`genos-recipe-v30-small-model-contracts` 당시 기본 `STRUCTURE_RECIPE_PROTOCOL=compact`는
기존 구간별 파이프라인과 `LLM.structured` 안에서 응답만 작은 단위로 나눈다.
`legacy`는 이전 통합 출력 계약이며 자동 fallback은 없다. 기존 환경파일을 덮어쓰지 않는다.

- 초기 틀: 번호 체계 하나당 평평한 규칙 객체 다섯 필드만 요청한다. 코드가 부여한
  F1/F2 등의 별칭과 ROOT를 사용하며 실제 가족 ID는 코드가 복원한다. 전체 원문과 다른
  가족의 근거를 유지한다. 다른 가족을 부모로 삼을 수 있고, 조립 후 누락/순환/깊이를 검증한다.
- VLM: 의견 문자열 목록과 요약을 유지하고 짧은 한국어 지시·구체적 JSON 예시를 제공한다.
- LLM 의견 판정: 의견 하나씩 `decision`, `blocks`, `reason`만 받는다. 의견 ID는 코드가
  연결하며 어떤 의견도 누락하지 않는다. 하나라도 hold면 승인하지 않는다.
- LLM 조치 선택: `verdict`, `blocks`, `reason`만 받는다. 상태 해시, 수정 규칙, 의견 ID 목록을
  동시에 출력하게 하지 않는다. VLM 의견이 없어도 이 검토를 수행한다. 채택 의견이나 코드
  문제가 남으면 approve를 거부한다. revise일 때 현재 창에 등장하는 형식들의 가족 규칙을
  하나씩 다시 받고 조립한다. 원문 근거가 없는 규칙은 유지하도록 지시한다.
- 최종 `reviewed_state_id`, `opinion_decisions`, `template_changes`는 코드가 기존 계약으로
  조립한다. 기존 승인 조건·근거 검사·무변경/과거 구조 반복 방지·재검수는 유지한다.
  여러 부모 변경은 한 형식의 모든 변경을 합친 뒤 검증하여 중간 상태의 가짜 순환을 피한다.
- 작은 호출은 최초 포함 3회 한도이며 재요청에 이전 작은 답변과 해당 오류 위치/허용 값만
  전달한다. VLM 의견과 구간 탐지의 재요청 한도는 기존과 같다. 형식 의미 검증은 기존 상위
  루프가 맡고, 모든 실제 호출이 `STRUCTURE_RECIPE_MAX_CALLS`(기본 64)를 소비한다.
  예산이 부족해도 남은 작업을 생략하거나 승인하지 않는다.
- 출력 잘림은 구간 분할/검수 창 분할 경로를 유지한다. 이미 규칙 하나만 요구한 초기 호출도
  잘리면 더 큰 가족 묶음 계약으로 돌아가지 않고 정확한 OUTPUT_LENGTH_LIMIT 원인으로 중단한다.

예시 응답은 정답이 아니며 값은 원문 근거로 정하도록 명시한다. 모델 입력의 원문을 줄여
출력 부담을 맞추지 않는다. 호출 수·총 입력 토큰·감사 파일 수는 늘어날 수 있다.
v30 코드/프로토콜은 캐시 결속에 포함되므로 이전 승인/태그를 재사용하지 않는다. 새 run ID로
실행하며, 같은 v30 실행의 보류 후 재개는 기존 checkpoint 계약을 따른다. 개별 의견 판정 도중
중단되면 저장된 VLM 의견부터 판정을 다시 수행할 수 있다.

로컬 합성 HTTP 응답으로 계약·재구축·검수·실패·캐시를 검증했다. 실제 소형 GENOS 모델의
정확도/지연 개선은 아직 미확인이다. 패치 인계에는 v27/v28의 알려진 파일 해시 사전 검사,
백업·원상 복구, 새 모듈 제거를 포함한다. 기존 발송 ZIP은 변경하지 않는다.

### v29에서 도입한 검증 실패의 모델 재요청 연결

`genos-recipe-v29-validation-feedback`는 구간 탐지·형식별 틀 생성·VLM 의견·LLM 판정의
기존 재요청에 `repair_feedback`을 추가한다. 실패 단계/시도/남은 횟수, 검증 메시지,
스키마 위반 필드 경로·실제 값·허용 값, 해당 단계의 허용 블록·가족·의견 ID·상태 ID를
전달한다. `invalid_plan`, `invalid_template`, `invalid_opinions`, `invalid_review`에는
직전 응답을 보존한다. 요청과 실패 값은 같은 GENOS 모델에 보내는 비공개 감사 자료이며,
원문·응답 전체나 Python traceback을 공개 오류 요약에 복사하지 않는다.

| 중단/재요청 조건 | 모델에 제공하는 수정 근거 또는 처리 |
|---|---|
| 완료 응답의 JSON 문법 오류, 필드 누락·타입·enum·추가 필드 오류 | 거부된 응답과 요청 스키마, 스키마 오류의 필드/실제 값/위반 조건. 어댑터 밖 기존 재요청 루프로 전달 |
| 구간 시작 0 누락·역순·중복·범위 초과·근거 없는 경계 | 전체 원문/기존 답변, 허용 시작 블록·전체 블록 수·구간 64/형식 12 상한 |
| 가족 누락·잘못된 부모·부모 순환·깊이 초과 | 기존 규칙, 관찰 가족 목록·허용 부모 목록·오류 순환 경로·깊이 16 상한 |
| 검수 상태 불일치·범위 밖/빈 근거 | 정확한 reviewed_state_id, 허용 원문 블록 ID, 기존 판정 |
| VLM 의견 누락·중복 판정·근거 없는 accept/reject | 필요한 모든 의견 ID와 판정 계약. hold는 승인 불가 |
| approve와 수정안/미해결 문제 충돌 | 이전 답변, 남은 코드 문제와 승인 금지 상태, verdict별 편집 계약 |
| 무변경 수정·이전 구조 반복 | NO_EXECUTABLE_CHANGE/REPEATED_STRUCTURE와 rule_comparison 전후 실행 필드 |
| 출력 토큰 초과 | 아래 v28 분할 경로 사용. JSON 형식 재요청으로 처리하지 않음 |
| HTTP/인증·모델 거절·이미지 누락/불일치·입력/호출 예산 초과 | 모델이 수정할 답변으로 취급하지 않고 해당 원인으로 중단 |
| 원문/OCR 부족·checkpoint/태그 무결성 불일치·hold/missing_rules/source_error·수정/재구간화 예산 소진 | 원문·설정·구현 점검 또는 사용자 검수 대상으로 보존. 승인 강제나 무한 재요청 없음 |

구간/틀/판정은 최초 포함 3회, VLM 의견은 2회이며 모든 호출이 전역 호출 예산을 소비한다.
출력 분할 중 응답 검증 실패도 소유 단계의 남은 재요청 안에서 처리한다.
`*-feedback-input.json`에는 실제 다음 요청에 쓰는 피드백이 남으며 마지막 실패도 기록한다.
구간/틀의 초기 스키마 오류가 재요청 전에 탈출하던 경로와, VLM 의견에 구체적인 오류 대신
일반 안내만 전달하던 경로를 보완했다. 모델이 지적을 실제로 올바르게 고치는지는 현장 확인
대상이다. 이 버전은 로컬 합성 검증용 작업 코드이며 기존 발송 v28 ZIP을 변경하지 않았다.
정책 버전이 달라 이전 승인/캐시는 재사용하지 않는다. 현장 반입 시 새 run ID로 실행한다.

### v28에서 도입한 출력 잘림 시 작업 분할

`genos-recipe-v28-bounded-output-recovery`는 모든 구조화 호출에 간결한 JSON 출력을
요구하고, `max_tokens`로 잘리면 같은 큰 응답을 다시 요구하지 않고 출력 작업을 분할한다.
기존 `LLM.structured`·GENOS 프로필·호출별 출력 한도(기본 4096, 상한 16384)는 유지한다.

- 구간 목록: 전체 원문을 매번 유지하면서 다음 구간을 4개씩 요청한다. 다시 잘리면
  2개→1개로 줄인다. 이전 확정 항목과 `has_more`를 사용하며, 완전한 JSON 페이지를
  모두 받은 뒤 기존 전체 구간·근거·빈틈/중복 검증을 수행한다.
- 형식별 규칙: 전체 원문·전체 번호 체계 목록을 유지하고 출력할 규칙만 4개→2개→1개로
  나눈다. 다른 묶음의 번호 체계도 부모로 지정할 수 있다. 합친 뒤 전체 계층·순환·실행을
  검증한다. 입력 원문을 요약하거나 잘라서 예산을 맞추지 않는다.
- VLM 의견/LLM 판정: 출력 잘림을 일반 형식 오류로 재시도하지 않고 상위 검수 계획으로
  전달한다. 페이지 묶음을 줄이고 한 페이지를 겹쳐, 기존 범위의 모든 인접 페이지 쌍을
  적어도 한 창에서 함께 본다. 새 범위는 원본/오버레이 이미지·상태 ID·의견·판정을 새로 만든다.
  두 페이지 이하에서도 계속 잘리면 보류하며, 인접 페이지 근거를 버려 강제로 완료하지 않는다.

모든 분할 호출은 문서별 `STRUCTURE_RECIPE_MAX_CALLS` 안에서 실행한다. 잘린 JSON을
파싱·이어붙여 결과로 사용하지 않는다. 항목 중복·진행 없는 페이지·미완성 목록·규칙 누락은
실패하며 성공 태그를 발행하지 않는다. 상세 요청/응답과 조립 결과는 기존 실행 로그 안에 남는다.
진행 화면에는 출력 잘림 복구와 분할 단위를 표시한다. 최소 단위에서도 잘리거나 전체 호출/입력
문맥 예산이 소진되면 원인을 표시하고 보류한다. 모든 문서의 무조건 성공을 보장하는 변경은 아니다.

checkpoint v3에는 검수 분할 범위도 저장한다. 같은 조건의 재개는 작은 범위와 기존 승인부터
이어가며, 틀 변경 시 승인·의견은 기존대로 무효화한다. v28의 코드/정책 결속으로 이전 버전의
완료 결과·승인을 재사용하지 않으며 이전 산출물은 보존한다. 처음 반입할 때는 새 run ID를 사용한다.
합성 응답으로 출력 잘림·조립·전체 범위 검수·재개·예산 소진을 검사하며 현장 품질은 미확인이다.
롤백은 변경 전 코드 묶음을 복원하고 별도 run ID로 실행한다. CURRENT나 서빙 배포는 변경하지 않는다.

### 실패 원인 확인

검수 수정안의 실행 규칙이 현재와 같으면 `NO_EXECUTABLE_CHANGE`, 이미 검토한 이전
구조와 같으면 `REPEATED_STRUCTURE`로 구분한다. `parent_family`, `heading_position`,
`sequence`, `reset_scope`의 전후 값을 `rule_comparison`으로 재확인 요청에 포함한다.
`rationale`만 바꾸는 것은 실행 변경이 아니다. 검증을 통과하려고 임의 규칙을 바꾸지 말고,
근거가 부족하면 hold, 표현 불가능하면 근거와 함께 missing_rules를 사용하도록 안내한다.
기존 3회 한도와 무변경/순환 거부는 유지한다. 보류 시 최종 화면과 오류 요약에는 구체적
분류와 해당 `*-pending.json`의 정확한 경로를 남긴다. 실제 필드 비교와 원문은 그 상세
파일에만 보존한다. 이 진단 보완은 현장 모델이 유효한 수정안을 생성했다는 검증이 아니다.

작업 코드에서는 모델 출력 잘림을 `OUTPUT_LENGTH_LIMIT`로 구분하여 터미널과 문서 상태표에
원인·실패 단계·실제 `max_tokens`·조치·응답 JSON의 정확한 경로를 표시한다.
`structure-errors.json`의 해당 문서에도 같은 오류와 `diagnostic` 항목을 저장한다.
터미널은 현황판 아래에 경로를 생략하지 않은 실패 메시지를 남긴다. 모델 응답 본문은 상세
응답 파일에 유지하고 요약에는 복사하지 않는다. `STRUCTURE_RECIPE_MAX_TOKENS`는
공개 숫자 설정이므로 인증 토큰처럼 마스킹하지 않는다. 실제 인증키 마스킹은 유지한다.

16384 미만이면 모델 지원 범위에서 출력 예산 조정을 검토한다. 이미 16384이면 현행 코드의
허용 상한이다. v28은 위 분할 복구를 시도하고, 최소 단위에서도 실패하면 보류한다.
현장 반입·실제 출력 성공 여부는 별도 확인 대상이다.

### v27에서 도입한 역할: VLM 의견 → LLM 검증·수정안

사용자 요청으로 `genos-recipe-v27-vlm-opinions-llm-adjudication`은 역할을 분리한다.
전체 파싱 텍스트를 읽는 LLM이 초기 구간/틀을 생성하며 이 단계에는 이미지를 보내지 않는다.
VLM은 원본/구조 오버레이와 현재 구조를 보고 의견 문자열 목록과 요약만 반환한다.
블록 ID·실행 규칙·최종 판정을 VLM에 요구하지 않는다. 의견 ID는 코드가 부여한다.
이후 LLM이 원문·현재 틀·VLM 의견·동일 근거 이미지를 대조하여 각 의견을 accept/reject/hold로
분류하고 근거 블록/이유 및 수정안을 반환한다. 실행 규칙의 적용과 최종 승인 검증은 코드가 한다.
같은 GENOS_LLM_PROFILE의 기존 LLM.structured 호출을 역할별로 사용하며 독립 모델 교차검증이 아니다.

모든 의견은 정확히 한 번 판정돼야 한다. 근거 없는 채택/기각, 보류 의견의 승인, 범위 밖 블록,
변경 없는 수정안은 통과시키지 않는다. VLM 요청은 최초 포함 2회, LLM 판정은 3회 한도다.
검수당 호출이 두 단계로 늘어난다. 전역 호출 예산과 수정 횟수 상한은 유지한다.

checkpoint v2는 창별 VLM 의견도 저장한다. LLM 단계 실패 후 같은 조건으로 재개하면
그 의견을 재사용하고 LLM 검증부터 이어간다. 틀 변경 시 의견과 승인 모두 무효화한다.
이전 버전 체크포인트는 역할/계약이 달라 재사용하지 않는다. 첫 실행은 새 틀 생성부터 시작한다.
`*-vlm-opinions.json`, `*-llm-adjudicate-compiled-response.json`과 기존 최종 틀/트리/coverage가
감사 산출물이다. 합성 검증과 현장 품질 검증은 별도다.

### 검수 보정·재개 v26

`genos-recipe-v26-review-resume`은 기존 GENOS LLM 호출을 유지한다. 지역 검수는
판정의 대소문자/주변 공백 및 완전히 동일한 수정안 중복만 보정하고 원응답·보정 내역을 남긴다.
`approve/hold`와 수정안이 함께 오는 의미 충돌은 자동 판정하지 않는다. schema와 프롬프트에
`revise`만 수정안을 포함하는 조건을 명시하고 동일 구간을 최대 3회(최초+재확인 2회) 요청한다.
끝내 해결되지 않으면 `review_pending`으로 중간 결과를 저장하고 정본/승인 태그를 발행하지 않는다.

틀 생성 이후에는 `structure-recipe-runs/checkpoints/<binding hash>.json`에 틀·수정 횟수·
검수 승인 상태와 원실행 로그 경로를 보관한다. 동일 명령/설정/원문/모델로 재실행하면 코드로
구조를 재구축하고 정확히 동일한 검수 입력·이미지 상태의 승인만 재사용한다. 미완료 창에서
모델 호출을 계속한다. 틀 또는 구간 수정 시 모든 이전 창 승인을 무효화한다.
코드·원문·설정·모델 변경 또는 체크포인트 해시 불일치 시 오래된 승인을 재사용하지 않는다.
같은 ID 뒤의 모델 리비전 교체는 자동 감지할 수 없으므로 새 run-id/별도 실행 저장소를 사용한다.

v25 로그에는 필요한 체크포인트 계약이 없으므로 자동 이행하지 않는다. v26 첫 실행은 틀을
새로 만들며 그 이후부터 재개 가능하다. 검수 대기는 문서 최종 성공과 구분하며 기존 CLI의
보류/실패 요약은 남을 수 있다. 다른 문서의 정상 완료 결과는 보존한다.
합성 응답 기반 재개·변조 거부·모델 변경·승인 무효화 검증이며 GENOS 실제 품질은 미확인이다.

### GENOS v1.8.6 공식 API 대조

2026-09-16 공개 공식 문서의 [LLM API](https://genos-docs.gitbook.io/default/v1.8.6/advanced-tutorials/guides/api/llm.md)와
[멀티모달 API](https://genos-docs.gitbook.io/default/v1.8.6/advanced-tutorials/guides/api/multi-madal.md)를 직접 확인했다.
두 문서는 `/api/gateway/rep/serving/{id}` 아래 `/v1/models`와 `/v1/chat/completions`,
`Authorization: Bearer`를 사용한다. 모델 미설정 시 문서 예제는 `data[0].id`를 선택한다.
멀티모달은 messages content의 text와 image_url(data:image/...;base64,...)를 함께 보낸다.
LLM 문서는 스트리밍과 선택적 x-genos-user-id를 설명한다. 기존 LLM의 이미지 먼저 배치는
OpenAI 호환 content 배열이며 별도 VLM endpoint를 추가하지 않는다.

v25는 아래 기존 호출부를 통해 이 계약을 사용한다. 프록시 미사용, JSON schema/prompt 전환,
구조화 예산·검수 규칙은 우리 구현 정책이며 공식 문서의 필수 요구로 표현하지 않는다.
이 대조는 공개 규약 확인이다. 사진의 401 원인이 경로만이라고 확정하거나 현장 인증 성공으로 간주하지 않는다.

| 항목 | 현행 연결 |
|---|---|
| 실행 | GENOS 코드스페이스 Python 3.11, pipeline.py build-data-stages |
| 모델 | 기존 GENOS_LLM_PROFILE의 서빙·키·모델, 명시 GENOS_LLM_URL 우선 |
| 이미지 | 기존 LLM.structured(images=...) → image_url base64 |
| 응답 | 기존 SSE 조립 → JSON 해석 → 구조화 schema/검수 |
| 데이터 | RAW/internal PDF → 전처리기 전체 청크 → 틀 → VLM 검수 → 재구조화 |
| 배포 | ZIP 적용은 코드스페이스 파일 변경; 코드서빙 리비전 배포와 별도 |

과거 integration 브랜치의 `/models` 계약은 이 v25 경로에 적용하지 않는다.

모델 연결 보완(v25): 구조화도 기존 `lawrag.core.llm.LLM.structured(..., images=...)`를
직접 호출한다. 별도 HTTP transport나 VLM 프로파일을 만들지 않는다. 기존
`GENOS_LLM_PROFILE`의 URL·키·모델 선택, `/v1/models`, `/v1/chat/completions`,
프록시 미사용, 스트리밍, JSON 모드를 그대로 사용한다. 기존 호출부는 모델 미설정 시
`/v1/models`의 첫 모델을 선택한다. JSON schema가 거부되면 기존 호출부의 prompt 모드로
재요청하며 이미지는 유지한다. 구조화 어댑터는 추가 재시도를 하지 않는다.
이미지 개수·응답 스키마·완료 상태·구조화 호출 예산은 검증한다. 내부 PDF에서 외부 provider는 거부한다.
실제 선택 모델과 공용 LLM 코드 해시는 캐시에 결속한다. 모델 교체 시 새 run ID를 쓴다.
사용자 사진에서 v24의 `/models` 요청 HTTP 401이 확인되었으며, v25 현장 성공은 아직 미확인이다.

현행 runtime은 `genos-recipe-v28-bounded-output-recovery`이다. 틀 생성에 전체 파싱
텍스트를 제공하고, VLM 보정이 완료된 최종 틀로 전체 문서를 다시 실행·저장한다.
아래 대표 텍스트 샘플링 설명은 이전 v22 기록이다. 원본 이미지 창은 계속 예산에 맞게 나눈다.
Docling 구조 또는 순서 검증된 기존 전처리기 청크를 입력으로 사용한다. 청크 입력은
전 페이지 VLM 검수 필수이며 셀·좌표 미확인을 보존한다. 문자·문맥 상한 초과는 보류한다.
현행 입력은 RAW/internal이고 build-all은 구조화와 용어집을 병렬 실행한다.
자세한 수신·검증·제약은 [현행 전처리기 계약](GENOS_PREPROCESSOR_PARSING.md)을 따른다.

## 기존 연결과 검수 이력

2026-09-15 현재 GENOS PDF 파싱 진입점은 [전처리기 파싱·적재](GENOS_PREPROCESSOR_PARSING.md)다.
전처리기가 반환한 Docling JSON이 아래 구조화/VLM 단계의 입력이 된다. 이후 신규 적재는
`source.sqlite → 용어·정의·명시 참조 색인 → TERM/.../generation`이며, 아래 과거 설명의
의미 추출·임베딩은 현행 필수 단계가 아니다. 기존 검수/완료 이력은 보존한다.

2026-09-14 작업 코드: `genos-recipe-v22-main-regions`.
사용자의 MAIN 배선 지시로 ADR0396의 구간별 틀 프로세스를 공용 입력 경로에 연결했다.
ADR0397의 모델 비교 기록과 완료 후보는 그대로 보존했다. 신규 품질 실험이나
Accepted arm 승격, 활성 RAG 데이터/CURRENT 변경, GENOS 배포를 수행한 것은 아니다.

## 실행 경로와 소비자

`build-data-stages`의 입력은 논리 data root의 내규 `PDF/internal`(PDF만)과
외규 `RAW/<source>`다. `build-all`도 같은 선택을 사용한다. 내규 원본·ZIP은
`RAW/internal`에 보존하며 이 명령이 자동 변환하거나 대체 입력으로 선택하지 않는다.
PDF 경로 전환 후에는 새 run-id로 시작하고 같은 명령으로 재개한다. 이전 구조화·완료
세대는 보존하며 코드/입력 지문이 달라진 결과는 새 구조화 키로 저장한다.
기존 RAW를 직접 지정하는 레거시 실행기와 API 업로드의 입력 계약은 별도다.

```text
pipeline.py build-all
  → 용어집 review complete → build-data-stages --stage all
pipeline.py build-data-stages --stage structure|all
  → genos_stages.structure → genos_build.ingest_files
업로드·재해석 API / service.py PIPELINE_*의 공용 ingest 경로
  → ingest.interpret_doc
  → 원본 PDF이고 VLM 활성 상태이면 recipe_runtime.revise_pdf
      전체 파싱·원문 좌표 보존
      → 전체 문서에 걸친 연속 청크 샘플링 + 원본 지면
      → 형식 전환 구간 감지
      → 형식별 계층·번호 문법 생성
      → 구간별 실행·원문 좌표를 유지한 합침
      → 프론트 뷰어와 같은 bbox 결과로 VLM 검수
      → 틀/구간 변경 시 재구축·이전 승인 무효화·재검수
  → 기존 viewer result.json / meta.json / structure-receipt.json
  → authoring-source.sqlite → 문서–용어 연결 → 의미 추출·검토 → 임베딩/DRAFT
```

`PIPELINE.json.authorities.document_ingestion`은 이 실행 계약을 가리킨다.
기존 CLI와 API의 공용 ingestion 함수를 교체했으며 별도 병렬 실행기를 추가하지 않았다.
engine-host `legal-authoring`의 extract/admit/index는 아직 MIGRATION_REQUIRED다.
이번 배선은 MAIN의 실제 CLI 문서 구축 경로이며 그 미연결 profile을 READY로 바꾸지 않는다.

## 모델이 만드는 것

문서 시작 몇 페이지만 보지 않는다. 전체 블록의 전환 단서와 시작·중간·끝, 표기·배치
유형을 대표하는 연속 청크를 사용한다. 모델은 본문·부칙·별표·서식처럼 형식이 달라지는
경계를 원문 근거로 제안한다. 같은 형식의 여러 구간은 한 틀을 재사용한다.

틀에는 관측된 표기 계열마다 다음 규칙을 둔다.

- `parent_family`: 바로 위 표기 계열. 예: `kr_article → kr_장` 또는 `1. → 가.`.
- `heading_position`: 행 시작, 상위 제목 직후, 원문 스타일 제목 중 선택.
- `sequence`: 연속 번호 / 증가 번호 / 순서 제약 없음.
- `reset_scope`: 상위 제목별 또는 해당 구간 전체에서 번호를 센다.

구간 경계에서 번호 상태를 새로 시작하므로 여러 부칙의 제1조를 한 수열로 강제하지 않는다.
같은 `1.`도 본문과 서식에서 서로 다른 상위 계열을 가질 수 있다. 각 구간은 원문 블록을
빠짐없이 한 번씩 덮고 부모·본문 span이 구간 밖으로 새지 않는다. 원문·표·좌표는 유지한다.

검수 모델은 `template_changes`로 해당 형식을 공유하는 모든 구간의 규칙을 수정하거나,
`resegment`로 형식 경계를 다시 탐지하도록 요청한다. 개별 후보 ID 수정, 임의 Python·정규식
생성, 원문 덮어쓰기는 실행 인터페이스에 없다. singleton 제목도 명시한 계층대로 실행한다.

## 검수·후속 단계·캐시

원본 페이지와 실제 `viewer.payload` bbox를 그린 이미지를 함께 제공한다.
`reviewed_state_id`는 원문·구조·구간 틀·페이지·실제 이미지의 해시에 결속된다.
틀/경계를 바꾸면 이전 창의 승인을 무효화하고 다시 검수한다. 근거 없는 승인, 순환/무변경
수정, 원문 부족, 호출/교정/재분할 한도 소진은 `NeedsReview`로 중단하고 기록을 보존한다.

- `visual_approved`: 모든 페이지의 이미지 검수 완료. 의미 정확성 승인이 아니다.
- `visual_sampled`: 선택한 페이지 검수 완료. 미검수 페이지를 명시한다.
- 실패/보류: 성공 태그를 저장하지 않고 해당 문서의 의미 추출·임베딩을 차단한다.

`meta.json`과 `result.json`에 같은 `recipe_review`를 저장한다. 이 기록에는 process/runtime,
모델, 구간 수, 틀 수, run ID, 호출 수, 검수 범위가 있다. `genos_stages` 문서별 보고서도 이를
전달한다. metadata/result 검수 기록이 다르거나 실패 상태이면 admission에서 거부한다.
한 문서의 실패 때문에 다른 정상 문서까지 중단하지 않는다.

원문·블록·구조 코드·모델 설정·틀·검수 범위와 재구축 트리가 같을 때만 캐시를 재사용한다.
재사용에도 모델/검수 메타데이터를 유지하며 모델 호출은 0회다. 이번 runtime 버전과 파일
해시 변경으로 이전 구조화 캐시/승인 태그를 새 프로세스의 성공으로 재사용하지 않는다.
이미 완료된 문서·릴리스는 덮어쓰지 않고 새 구조화 키로 생성한다.

## 설정과 실행

MAIN/GENOS는 기존 내부 VLM 설정을 사용한다. Gemini 실험용 API 키나 research candidate를
제품 경로에서 읽지 않는다. 더 나은 내부 VLM을 사용할 때는 기존 `GENOS_LLM_MODEL` 또는
선택한 `GENOS_LLM_PROFILE`의 모델/서빙 ID/키를 일치시킨다. 다른 모델로 자동 fallback하지 않는다.
현재 Codex 환경에서는 GENOS 접속·배포·내부 모델 품질 확인을 할 수 없다.

```bash
export LLM_BACKEND=genos
export STRUCTURE_RECIPE_VLM=on
export STRUCTURE_RECIPE_REVIEW_MODE=adaptive
# 내부 모델이 지원하는 경우 출력 예산을 늘릴 수 있다.
export STRUCTURE_RECIPE_MAX_TOKENS=16384

# 데이터 입력 목록 확인 (모델 호출 없음)
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id region-main-001 --check-only
# 구조화까지만 실행하고 문서별 검수 기록 확인
.venv/bin/python 06_TOOLS/pipeline.py build-data-stages --run-id region-main-001 --stage structure --execute
# 검토된 용어집 완료부터 문서 DRAFT까지 기존 MAIN 명령
.venv/bin/python 06_TOOLS/pipeline.py build-all --run-id region-main-001 --execute
```

`build-all`은 용어집 검토 미완료 시 문서 단계로 넘어가지 않는다. 구체적인 모델·키 연결은
[GENOS.md](../../../../GENOS.md), 데이터 경로는 [4단계 가이드](GENOS_FOUR_STAGE.md)를 따른다.

| 설정 | 기본값 / 의미 |
|---|---|
| STRUCTURE_RECIPE_VLM | auto: LLM_BACKEND=genos일 때 활성; on/off 명시 가능 |
| STRUCTURE_RECIPE_REVIEW_MODE | adaptive: 유형·위험 표본 검수; full: 같은 프로세스로 모든 페이지를 창 단위 검수 |
| STRUCTURE_RECIPE_MAX_PAGES | 기본 basic+warnings는 1, 그 외 6; 창의 원본 페이지 수. 원본+오버레이 이미지 두 장씩 제공 |
| STRUCTURE_RECIPE_MAX_DOCUMENT_PAGES | 2000 |
| STRUCTURE_RECIPE_MAX_CHARS | 160000; 요청 문맥 상한 |
| STRUCTURE_RECIPE_MAX_TOKENS | 4096; 최대16384 |
| STRUCTURE_RECIPE_MAX_CALLS | 64; 문서별 논리 호출 상한, 전송 재시도는 별도 기록 |
| STRUCTURE_RECIPE_MAX_CORRECTIONS | 기본 basic+warnings는 2, 그 외 6; 형식 경계 재탐지는 최대2회 |
| STRUCTURE_RECIPE_TAGS | 기본 structure store의 상위 디렉터리/structure-recipes.json |

로그는 구조 store 상위의 `structure-recipe-runs/<run_id>`에 저장된다. 원문 청크 계획,
구간·틀·실제 트리·bbox 이미지·모델 응답·실패 원인을 연결해서 확인할 수 있다.
MAIN의 문서별 상태/재개 명령은 기존 `01_DATA/LOGS/<run-id>`를 사용한다.

`build-all --execute → build-data-stages --stage all → ingestion`에서도 VLM 이벤트를
문서별 진행 표시로 직접 전달한다. 형식 구간 감지, 틀 생성 n/m, 구조 적용 회차,
bbox 검수 n/m창·페이지, 수정 횟수·이전 승인 해제, 모델 호출·재시도·응답 시간·사용량,
검수 완료/보류를 표시한다. `progress.log`에는 상태 변경 요약, `detail.log`에는
`[STRUCTURE VLM]` 구조화 이벤트, `current.json`에는 현재 단계와 `vlm_run_id`가 남는다.
용어 검토가 완료되지 않아 build-all이 앞 단계에서 멈추거나 입력 점검만 실행하면
VLM 로그는 발생하지 않는다. 구조화 캐시 재사용은 별도 CACHE 상태로 표시한다.

대화형 터미널에서는 줄을 계속 추가하지 않고 누적 현황판을 같은 위치에서 갱신한다.
이번 실행의 구조화·의미 추출·임베딩 완료/실패 건수, 현재 문서의 단계별 상태,
구간·틀·검수·수정·모델별 최신 상태와 최근 결과 두 건을 유지한다. 화면 높이에 맞춰
표시 행 수를 제한한다. 터미널 갱신을 지원하지 않는 출력/파이프에서는 문서 단계
시작·종료 요약만 출력한다. 중간 이벤트는 계속 progress.log/detail.log에 기록한다.
`current.json`은 현재 문서의 누적 단계·VLM 상태를, `progress-summary.json`은 이번
호출에서 처리한 문서별 단계 결과를 저장한다. 후자는 단계 종료 시 갱신하며 이전
호출의 결과와 합산하지 않는다. 전체 재개 이력의 정본은 기존 문서 상태표/ledger다.
전용 GENOS 로거도 구축 CLI 실행 동안 detail.log로 연결해 현황판에 끼어들지 않게 한다.

개별 VLM 실행의 `events.jsonl`은 상세 이벤트 전체를 보존한다. 컨테이너 로그는
파일 저장·페이지 렌더링·단계 시작/종료·대기 이벤트를 DEBUG로, 재시도를 WARNING,
단계 실패·검수 보류를 ERROR로 구분한다. 기본 INFO에서도 구간·틀·검수 진행과 모델
호출 정보는 확인할 수 있다. DEBUG 전환은 기존 `GENOS_LOG_LEVEL=DEBUG`를 사용한다.
진행 이벤트에는 원문·프롬프트·모델 응답을 넣지 않는다. 해당 내용은 기존 접근 제한
실행 디렉터리의 검수 근거로 보존하며 이 변경은 자동 삭제나 보관 정책을 추가하지 않는다.

## 지원 범위와 남은 한계

XML/HTML 전용 파서, 명시적인 형식 바인딩과 DOCX 스타일 경로가 우선한다.
HWP/DOCX의 합성 PDF는 원본 지면 증거가 아니므로 VLM 대상에서 제외한다.
원본 또는 검증된 변환 PDF를 별도 PDF로 입력하면 이 경로를 사용한다.
OCR 필요 페이지는 기존 Docling·한국어 RapidOCR 자산 설정을 요구하며 텍스트가 없으면 보류한다.

ADR0397에서 Flash는 KRX 본문 장·조 연결을17/17로 개선하고 누락 항을 발견했다. 그러나
블록 중간의 `②` 분리와 날짜 조각의 잘못된 번호 인식을 복구하는 기능은 아직 없다.
`resegment`는 형식 구간을 나누며 원문 블록을 분할·재결합하는 명령이 아니다.
VLM 승인과 문서 전체 정확도는 구분하고 결과는 DRAFT로 후속 검토에 넘긴다.

## 검증·롤백·이력

합성 원문과 가짜 내부 모델 응답으로 공용 ingestion→구간 틀→bbox→저장/재사용,
실패 문서의 후속 차단, 기존 XML 문서의 단계별 의미 추출·임베딩 연결을 검사한다.
이는 실제 내부 데이터 품질·현장 배포 검증을 대신하지 않는다.

`STRUCTURE_RECIPE_VLM=off`는 기존 휴리스틱 구조화로 되돌린다. 모델 설정/코드 복원은 새
구조화 키를 사용한다. 이전 태그나 CURRENT를 수동으로 덮어쓰지 않는다.
변경 전 파일·해시와 도입 기록은 [배선 감사](../../../../09_ARTIFACTS/AUDITS/20260914-region-main-wiring/README.md)에 있다.

이전 배선/검수 이력: ADR0358, ADR0370~0381. 구간 틀 원본: [ADR0396](../../../../04_EXPERIMENTS/ADR/ADR-0396-pdf-region-explicit-ladder/README.md).
모델 비교: [ADR0397](../../../../04_EXPERIMENTS/ADR/ADR-0397-pdf-model-tier-benchmark/MODEL_COMPARISON.md).
# 최종 구조화 이미지 로그 (v37)

`build-data-stages` 종료 시 `doc-status.html` 내보내기가 최종 저장 result.json의
원본/bbox 이미지 보고서를 LOGS의 `structure-images.html` 및 `structure-images/<지문>/`에 생성한다.
기존 성공 건도 `.venv/bin/python 06_TOOLS/COMMANDS/genos_data_status.py --run-id <ID> --export`로
모델 재호출 없이 생성한다. 구조화 영수증·원본 PDF 해시를 확인하고 원문 보존 이후의 소속을 그린다.
좌표 누락과 이미지 오류는 별도 표시하며 구조화 상태를 실패로 바꾸지 않는다. 구조화 캐시는 변경하지 않는다.
HTML을 옮기면 연결된 이미지 폴더도 함께 옮긴다. 보고서에는 원본 이미지/본문이 포함된다.
v36a 현장 1건 완료는 확인했지만 v37 현장 실행과 전수 품질은 미확인이다.
샘플 틀 확정 후 무모델 전수 처리는 아직 미구현이며 기존 VLM=on 전체 실행은 문서마다 모델을 호출한다.
