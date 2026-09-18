# 사용자 표현 수집과 탐색 절차 재사용 — 첫 구현

작성일: 2026-09-16. 작업 코드에 구현했고 모의 데이터 계약 검사를 수행했다.
로컬 활성 릴리스 `navigation-rag-20260916-v1` 및 GENOS 배포는 변경하지 않았다.

## 구현 범위

1. 질문에서 기존 용어·구조로 매칭되지 않은 구간을 검토 후보로 수집한다.
2. 운영자가 검토한 표현을 **기존 등록 용어 ID의 검색 단서**로 연결한다.
3. 검토한 탐색 절차가 질문의 용어·문구·문서 범위에 맞으면 같은 메타데이터 탐색 순서를 실행한다.
4. 이후 원문을 새로 읽고 판단한다. 지정한 확인 항목의 근거가 없으면 `sufficient`로 종료할 수 없다.

표현 연결은 개념 동일성 선언이나 정본 용어집의 새 개념 생성이 아니다. 절차의 재사용 범위는 정의 조회·관계 탐색·원문 목록 조회와 필수 확인 항목이다. 이후 LLM의 모든 행동과 답변이 같아짐을 보장하지 않는다. 새 개념·의미를 만드는 절차, 임베딩 기반 질문 분류, 과거 성공 실행에서 절차를 자동 추출하는 기능, 검토 UI는 후속 범위다.

## 기존 MAIN과 연결

```text
/v1/rag/ask → 기존 Pipeline → NavigationSession → READ/JUDGE → 답변·run 저장
  └ capture=true → 미매칭 질문 구간 → 로컬 review.sqlite [PROPOSED]

pipeline.py glossary learn collect/list/review/resubmit/propose-recipe/publish
  └ 검토 이벤트 + 선택 세대 검증 → 불변 navigation-learning-v1 JSON

PIPELINE legal-rag.retrieve.parameters.term_agent.learning.bundle
  → ServingNavigationAgent → 번들 해시·세대·등록 ID·범위 검사
  → LearnedMatcher → 기존 NavigationSession 안에서 검토 절차 실행
  → 새 원문 읽기·판단 → 기존 select/assemble/answer
```

| 담당 | 구현 | 입력 → 소비되는 출력 |
|---|---|---|
| 관측 수집 | `semantic_runtime.learning_store.collect_run` | 저장된 run의 전체 매칭 span → 구간·실행 해시·query ID·원문 세대에 결속한 후보 |
| 운영자 검토 | `pipeline.py glossary learn` | 후보 → 검토자·사유·시각을 남긴 승인/거절/철회 이벤트 |
| 번들 컴파일 | `learning_store.publish` | 최신 승인 상태 + 선택 세대의 실제 색인 → 기존 용어 ID만 포함한 불변 번들 |
| 표현 매칭·선택 | `navigation_learning` | 명시한 번들 → 추가 시작 용어·조건이 유일하게 맞는 절차 |
| 실행 | `navigation_loop.NavigationSession.prepare_recipe` | 검토한 OPEN_TERM/GRAPH/LIST → 같은 세션의 목록·이력·필수 issues |
| 릴리스 준비 | `control.prepare` | 검증한 번들 → 새 릴리스 코드 루트에 동일 경로·해시로 복사, release 파일 목록에 포함 |

기존 `/feedback` 계약은 유지된다. 이번 관측은 `/ask`의 저장된 실행에서 분기한다. 스키마가 닫힌 Request/Query에 임의 필드를 추가하지 않으며, 내부 결과는 기존 `retrieval.term_agent.learning`, `matched_question_spans`에 남긴다.

## 계약과 상태

실행 가능한 계약 정본은 `semantic_runtime/navigation_learning.py`의 `validate_item`, `validate_bundle`이다. 기존 용어집 의미 검토 응답과 별개의 `navigation-learning-v1` 계약이며 폐기한 법률 의미 스키마를 복원하지 않는다.

번들 최상위 필드는 `schema_version`, `id`, `generation_id`, `generation_manifest_sha256`, `expressions`, `recipes`다. 미지 필드는 거부한다. 최대 파일 크기는 16 MB, 표현·절차는 각각 최대 10,000개이며 이는 검증 상한이지 성능 보장치가 아니다.

- 표현: `id`, `expression`, `term_id`, `document_version_ids`, `review`.
- 절차: `id`, `trigger_term_ids`, `required_phrases`, `excluded_phrases`, `document_version_ids`, `issues`, `steps`, `require_references`, `review`.
- 검토: `reviewer`, `reason`, `event_id`, `candidate_sha256`, `evidence`. 표현의 evidence는 실제 저장 실행 파일의 SHA-256이다. 절차의 evidence는 운영자가 제공하는 검토 근거이며 코드가 의미 타당성을 인증하지 않는다.
- 검토 상태: `PROPOSED → APPROVED 또는 REJECTED`, `APPROVED → REVOKED`. 기존 기록을 수정하지 않는다. 개정안은 새 후보로 제출한다.
- 거절·철회한 관측을 정정할 때 `learn resubmit --candidate ID --reason 사유`로 원래 실행 근거와 부모 후보 ID를 유지한 새 후보를 만든다. 이후 새 후보를 별도로 검토한다.
- 동일 run·구간의 재수집은 동일 후보 ID로 중복 방지한다. 동일 표현의 다른 실행은 독립 근거 후보로 남긴다.
- 발행은 같은 파일시스템 임시 파일을 완성한 뒤 hard link로 게시한다. 기존 출력은 덮어쓰지 않는다.

## 사용 절차

WSL 저장소 루트에서 `.venv/bin/python`을 사용한다. 모든 예시 ID·경로는 명시적으로 선택해야 하며 파일명으로 최신 세대를 추정하지 않는다. 기본 검토함은 workspace의 `runtime` root 아래 `semantic/learning/review.sqlite`다.

먼저 새 작업 코드용 설정에서 `PIPELINE.json`의 `legal-rag` retrieve 노드의 `term_agent.learning`을 다음처럼 설정한다. 기본값은 수집 꺼짐이며 번들 지정도 없다.

```json
{"capture": true}
```

이 상태의 `/v1/rag/ask`는 실행 파일을 먼저 저장한 뒤 후보를 수집한다. 별도 외부 모델 호출은 없다. 수집 실패는 `learning.capture_failed` 이벤트로 남기고 답변은 반환한다. 저장된 run은 다음 CLI로 재처리할 수 있다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary learn collect --run /선택한/실행.json
.venv/bin/python 06_TOOLS/pipeline.py glossary learn list
.venv/bin/python 06_TOOLS/pipeline.py glossary learn review \
  --candidate 'candidate:목록에서_확인한_ID' --status APPROVED \
  --term-id '실제_등록_용어_ID' --reviewer '검토자' --reason '원문과 문서 범위를 확인한 사유'
```

구버전 run에는 전체 매칭 span이 없으므로 수집을 거부한다. 전체 질문을 매칭되지 않은 표현으로 잘못 간주하는 구버전 fallback은 없다. 미매칭 구간은 구두점과 이미 매칭된 구간으로 나누고 2~120자의 후보를 실행당 최대 8개만 수집한다. 이는 단순 후보 제안 방식이며 언어학적 용어 추출·개인정보 탐지기가 아니다.

다음은 모의 문서와 모의 용어 ID를 쓴 절차 입력 예다. 실제 사용 시 선택한 색인의 ID, 문서 버전, 확인 항목으로 바꾼다. `review`는 입력하지 않으며 별도 승인 시 붙는다.

```json
{
  "id": "recipe:business-day-definition-v1",
  "document_version_ids": ["mock-document:v1"],
  "trigger_term_ids": ["fixture:day"],
  "required_phrases": ["뜻"],
  "excluded_phrases": ["과거"],
  "issues": [{"id": "R1", "text": "질문에 적용되는 정의와 예외를 원문에서 확인"}],
  "steps": [
    {"tool": "OPEN_TERM", "args": {"term_id": "fixture:day"}},
    {"tool": "GRAPH", "args": {"term_id": "fixture:day", "hops": 1}},
    {"tool": "LIST", "args": {"term_ids": ["fixture:day"], "match": "all"}}
  ],
  "require_references": true
}
```

```bash
.venv/bin/python 06_TOOLS/pipeline.py glossary learn propose-recipe \
  --file /검토할/절차.json --generation /선택한/세대 \
  --evidence '설계 문서 위치와 검토한 실행 해시'
.venv/bin/python 06_TOOLS/pipeline.py glossary learn review \
  --candidate 'candidate:반환된_ID' --status APPROVED \
  --reviewer '검토자' --reason '적용 조건과 필수 확인 항목 검토'
.venv/bin/python 06_TOOLS/pipeline.py glossary learn publish \
  --generation /선택한/세대 --output /새로운/번들.json
```

`--ledger /별도/검토함.sqlite`는 `learn` 뒤, 하위 명령 앞에 둔다. 발행은 선택 세대의 Store와 실제 navigation 색인 해시·등록 ID를 확인한다. 신규 번들의 경로와 SHA-256을 출력하며 MAIN을 활성화하지 않는다.

작업 코드용 PIPELINE 설정에 다음 구조를 추가하면 재사용한다. `path`는 해당 Pipeline의 **contracts_root 기준 상대 경로**이며 절대 경로·루트 탈출은 거부한다. 번들은 그 경로에 따로 배치해야 한다. 완료된 원문 세대나 기존 릴리스는 수정하지 않는다.

```json
{
  "capture": true,
  "bundle": {
    "path": "09_ARTIFACTS/LEARNING/검토완료-v1.json",
    "sha256": "발행_명령이_반환한_실제_SHA256"
  }
}
```

새 로컬 릴리스 준비는 기존 `control.prepare` 경로를 사용하며 번들을 검증·복사한다. 이 코드를 추가했다고 기존 릴리스가 갱신되지는 않는다. 기존 준비/활성화의 승인·품질 기준을 우회하지 않는다. GENOS 코드 ZIP은 데이터 번들을 자동 포함하지 않으므로 별도 허용된 데이터 반입으로 같은 상대 경로를 준비하고 해시를 확인해야 한다. 비공개 표현을 공개 코드 저장소나 외부 패키지로 이동시키지 않는다.

## 시나리오와 실패 처리

| 경우 | 실제 동작 |
|---|---|
| 사용자가 모의 표현 ‘은행 문 여는 날’을 입력 | 알려진 용어로 매칭되지 않으면 검토 후보. 승인 전 검색 확장 없음 |
| 검토자가 특정 문서 범위에서 기존 ‘영업일’ ID로 연결 | 이후 해당 표현이 같은 범위 질문에 나오면 추가 시작점. 정본 동의어 선언은 아님 |
| 해당 ID와 질문 문구가 승인 절차에 부합 | 정의·관계·목록을 순서대로 조회하고 R1 등의 확인 항목을 고정 |
| 절차 실행 후 모델이 원문을 읽지 않고 답하려 함 | READ 후 다음 모델 호출에서 전달된 segment가 없으면 JUDGE 거부 |
| 일부 필수 확인 항목의 근거 누락 | 모든 issue의 채택 근거가 없으면 sufficient 거부 |
| 참조 확인 필수 절차 | 채택 원문의 REFERENCES 전체 페이지를 조회해야 sufficient 가능. 참조 대상의 법적 적용이나 모두 읽었음까지 인증하지는 않음 |
| 둘 이상의 절차가 조건에 부합 | `AMBIGUOUS_FALLBACK`: 절차 실행 없이 기존 탐색. 표현 매핑은 유지 |
| 번들 손상·세대 변경·등록 ID 무효·루트 탈출 | `INVALID_BINDING_FALLBACK`: 학습 단서 전체를 사용하지 않고 기존 탐색 |
| 절차 중 도구 실패 | `EXECUTION_FALLBACK`: 기존 모델 탐색을 계속하되 필수 issues 유지, sufficient는 차단하고 incomplete 보고 |
| 호출·행동·시간 예산 소진 | 기존 한도에서 incomplete. 절차의 행동도 max_actions에 포함 |
| 승인 철회 | 새 번들에서는 제외. 이미 발행·선택된 번들은 자동 변경되지 않으므로 새 릴리스/설정으로 재선택해야 함 |

문서 범위는 질의 범위와 **집합이 정확히 일치할 때만** 재사용한다. 상위 범위로 자동 확장하지 않는다. 이 검사 자체가 인증·인가를 제공하지는 않는다. 사용자별 접근권한은 기존 호스트/서빙 계층에서 검증해야 한다.

## 한계와 기대치

관측 가능한 기대 동작은 미등록 표현의 검토 가능성, 승인된 검색 단서의 재사용, 조건이 맞는 질문에 동일한 메타데이터 탐색 절차 적용, 원문을 다시 확인하는 경로 유지다. 정확도 향상률·시간 절감률·비용 절감률은 측정하지 않았고 보장하지 않는다. 전처리의 추가 모델 호출은 0이지만 기존 탐색 모델 호출은 계속 필요하다. 절차가 불필요한 탐색을 줄일 수도 있고 메타데이터·문맥량을 늘릴 수도 있다.

주요 남은 위험은 후보 잡음, 다른 의미의 표현을 검토자가 잘못 연결하는 일, 질문의 관할·상품·시점·부정/가정 조건을 문구 조건만으로 구별하지 못하는 일, 읽은 인용과 결론 사이의 의미적 비약이다. 단순 예외 문구와 원문 인용 존재만으로 법률·금융 적용을 확정하면 안 된다. 운영자 식별은 로컬 CLI 입력이며 별도 인증된 승인 서비스는 없다. 검토함에는 질문 조각이 있으므로 기존 실행 기록과 동일한 접근·보존 정책이 필요하다.

현재 수치 검사는 계약 상한과 상태 전이를 확인하는 테스트다. 실사용 효과 비교·A/B·holdout을 시작할 때는 새 ADR 선점·후보 격리·평가 동결 절차를 적용한다. 이번 기능 구현과 모의 계약 검사를 효과 실험이나 품질 인증으로 보고하지 않는다.

## 검증 명령

```bash
.venv/bin/python -m pytest \
  05_TESTS/CONTRACTS/test_glossary_learning.py \
  05_TESTS/CONTRACTS/test_navigation_loop.py \
  05_TESTS/CONTRACTS/test_navigation_main_wiring.py -q
```

새 검사에는 후보 수집·재수집·검토·철회, 실제 CLI의 절차 제출·승인·발행, `/ask`의 수집과 새 원문 READ/JUDGE, 해시·세대·범위·충돌·필수 근거·예산, 릴리스 번들 복사 후 해시 유지가 포함된다. 합성 fixture와 스크립트 provider를 사용하며 외부 모델 호출·실제 GENOS 접속은 없다.

최종 확인: 새 기능·기존 탐색·문서 릴리스·원문 세대의 5개 테스트 파일에서 **60 passed**. XML 결과는 `09_ARTIFACTS/AUDITS/20260916-glossary-learning-v1/contracts.xml`에 있다.

별도로 실행한 `test_pipeline_engine_ssot.py`는 1 passed / 15 failed였다. 폐기된 `semantic-contract-check`·`semantic.observation`과 구 fixture를 전제한 실패, 작업 코드와 활성 릴리스가 다르면 거부하는 engine_host 검사 실패가 포함된다. 이 테스트를 고치기 위해 폐기 계약을 복원하거나 현재 코드를 MAIN에 활성화하지 않았다. 저장소 전체 테스트 통과로 보고하지 않는다.
