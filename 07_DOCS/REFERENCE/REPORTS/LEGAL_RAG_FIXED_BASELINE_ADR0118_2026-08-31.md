# 대한민국 법령·금융규제 RAG
# 최종 고정 연구구조 상세설계서

- 고정 기준: `ADR-0118-experiment-v1 / integrated-atomic-claim-v4b`
- 구조 계보: `ADR-0114 integrated-seven-layer retrieval` + `ADR-0118 non-destructive atomic claim compiler`
- 평가 정본: Golden61 v3, CM core 51 + FSC hard 10, corpus-resolvable 필요 조문 116개
- 법령 시점: authority as-of `20260827`
- 문서 기준일: 2026-08-31
- 적용 범위: **후속 비교를 위한 연구 기준선 고정**. MAIN·검색·API 기본 배선은 변경하지 않음

## 1. 고정 결정

> 지금부터 추가 실험을 멈추고, 비교 가능한 구조 중 난도균형 목적함수 점수가 가장 높은 ADR-0118 `integrated-atomic-claim-v4b`를 최종 연구 기준선으로 고정한다. 이 결정은 운영 승격이 아니라 연구 비교점의 고정이다.

### 1.1 무엇을 고정하는가

고정 대상은 단일 프롬프트가 아니라 다음 두 층의 결합이다.

1. ADR-0114의 `integrated-seven-layer` 회수·증거 컴파일 구조
2. ADR-0118의 `integrated-atomic-claim-v4b` 비파괴 원자 claim 보조층과 closed evidence 답변 계약

정확한 실험 참조는 `ADR-0118-experiment-v1/integrated-atomic-claim-v4b`, 실행은 `run-002`다. 후속 문서·코드·평가에서 “고정 구조”, “최종 기준”, “compiler baseline”이라고 하면 이 참조를 뜻한다.

### 1.2 무엇을 고정하지 않는가

- MAIN 검색 경로, API 기본 라우터, feature switch는 바꾸지 않는다.
- ADR-0118의 상태를 `Accepted`나 `promoted`로 소급 변경하지 않는다. ADR-0118은 당시 사전 운영 기준을 비용·지연·회귀 측면에서 통과하지 못해 `Rejected`다.
- Golden61은 반복 관찰된 인샘플 데이터이므로 이 구조를 미관측 질문의 운영 성능으로 단정하지 않는다.
- 법률 결론을 자동 확정하는 포섭 엔진이 완성되었다고 보지 않는다. 현재 compiler는 근거 사용을 돕는 advisory 계층이다.

따라서 “최종 고정”의 정확한 뜻은 다음과 같다.

```text
연구 비교 기준: 고정
운영 MAIN 승격: 미실시
법률적 안전성 보증: 미충족
추가 실험: 사용자의 새 지시 전까지 중단
```

{{FIGURE_FIXED_OVERVIEW}}

### 1.3 왜 ADR-0118인가

최신 세 구조는 같은 28개 조문을 입력으로 사용했다. 차이는 답변 모델에게 어떤 가이드를 주었는지다.

| 구조 | TP/FP/FN | P/R/F1 | 완전충족 | 난도균형 점수 |
|---|---:|---:|---:|---:|
| 원문 28개 + evidence ID 직접선택, ADR-0131 | 65 / 61 / 51 | 51.59 / 56.03 / 53.72% | 27/61 | 50.479709 |
| **전체 compiler, ADR-0118** | **67 / 72 / 49** | **48.20 / 57.76 / 52.55%** | **29/61** | **52.638970** |
| 선별 법률 가이드, ADR-0132 | 69 / 79 / 47 | 46.62 / 59.48 / 52.27% | 31/61 | 52.490865 |

원문 직접선택은 FP가 적고 micro F1은 가장 높다. 선별 가이드는 TP·recall·완전충족 수가 가장 높다. 그러나 법률 질의에서는 쉬운 질문의 정밀도만 높이는 것보다 필수 조문 누락, 복합 질문 완결성, hard-set 성능을 함께 봐야 한다. 이 목적을 위해 ADR-0128은 다음 점수를 고정했다.

```text
legal Tversky = TP / (TP + 0.25×FP + 1.0×FN)
group score   = 100 × (0.45×micro T + 0.35×macro T + 0.20×완전충족률)
primary score = 0.5×core group score + 0.5×hard group score
```

FN 한 개를 FP 한 개보다 네 배 무겁게 보고, core 51문항과 hard 10문항을 50:50으로 평가한다. 이 고정 목적함수에서 ADR-0118이 `52.638970`으로 가장 높다. ADR-0121의 두 arm도 동일한 선언 evidence 결과로 동률이지만, 실제 구조의 원천과 상세 실행 산출물이 ADR-0118에 있으므로 기준 참조는 ADR-0118로 단일화한다.

### 1.4 상대적 최고와 운영 합격은 다르다

최고 구조도 ADR-0128의 운영 선택 gate를 통과하지 못했다.

| 운영 선택 gate | 요구값 | ADR-0118 | 판정 |
|---|---:|---:|---|
| overall recall | 80% 이상 | 57.76% | 미달 |
| hard recall | 70% 이상 | 66.67% | 미달 |
| 완전충족 질문률 | 70% 이상 | 47.54% | 미달 |

즉 이 문서는 “현재 비교군 중 가장 낫기 때문에 기준으로 고정한다”는 결정 기록이지, “운영에 바로 연결해도 된다”는 승인 문서가 아니다.

## 2. 전체 구조 한눈에 보기

고정 구조는 질문을 한 번에 벡터 검색하고 top-k로 자르는 파이프라인이 아니다. 법률가의 조사 흐름을 세 구간으로 분리한다.

1. **회수**: 가능한 지배 법령과 조문을 넓게 찾고, 기존 baseline을 보존한다.
2. **컴파일**: 질문 쟁점과 조문 원문 사이에 exact quote 기반 원자 claim을 붙인다.
3. **답변**: 28개 원문과 compiler packet을 함께 보고 실제 사용한 evidence ID를 선언한다.

```text
[사용자 질문]
    ↓
[질문 계획: exact span, family/predicate 가설]
    ↓
[12단계 회수·검증 상태 머신]
    ↓  최종 28개 article-root 원문
[비파괴 atomic claim compiler]
    ↓  issues + role + exact quote + closed E ID
[Haiku 답변 합성]
    ↓  answer + answerable + evidence_ids
[결정론 gate]
    └─ 목록 밖 ID 또는 근거 없는 answerable → INSUFFICIENT
```

### 2.1 각 구간의 책임 경계

| 구간 | 입력 | 출력 | 하지 않는 일 |
|---|---|---|---|
| 질문 계획 | 사용자 원문 | mention, family·predicate 복수 가설 | 법률 결론 생성 |
| 회수 상태 머신 | 질문 계획, baseline floor, 법체계·그래프·원문 | 검증된 최대 28개 조문 | 관계 발견만으로 결론 허용 |
| atomic compiler | 질문, 28개 조문 | issues, units, claims, closed E ID | 조문 삭제·재정렬·법률효과 요약 |
| 답변 합성 | 28개 원문 + compiler packet | 답변, 사용 evidence IDs | 목록 밖 근거 생성 |
| 결정론 gate | compiler 허용 ID + 답변 출력 | 통과 또는 INSUFFICIENT | 답변의 실질 법률 타당성 완전 판정 |

### 2.2 회수와 컴파일을 분리한 이유

회수는 놓치지 않아야 하므로 `fail-open`이 적합하다. grounding이 실패하거나 semantic card가 비어도 baseline floor를 유지하고 다른 branch를 계속 본다. 반대로 답변 명제는 실제 원문으로 지지되어야 하므로 closed evidence와 exact quote가 필요하다.

둘을 한 단계로 합치면 다음 두 오류가 생긴다.

- 검색 가설이 약하다는 이유로 정답 조문을 너무 일찍 버린다.
- 검색에서 관련 있어 보였다는 이유만으로 법률 결론까지 허용한다.

고정 구조는 후보를 보존하는 회수 계약과 결론에 사용할 근거를 제한하는 답변 계약을 분리한다.

## 3. 입력 데이터와 공통 좌표

### 3.1 조문 단위

최종 evidence의 기본 단위는 임의 길이 텍스트 chunk가 아니라 current corpus의 `article root`다. 하나의 Section은 최소한 다음 정보를 가진다.

```json
{
  "evidence_id": "E01",
  "coordinate": ["3521c3aaa5a735fd", 175],
  "document": "코스닥시장 상장규정",
  "path": "제13조",
  "scope_id": "MARKET:KOSDAQ",
  "excerpt": "조문 원문 전문"
}
```

`evidence_id`는 해당 질문에 제시된 닫힌 메뉴 안의 식별자다. 정본 좌표는 `doc_id + node`이며, 법령 세대와 authority 시점이 현재 index에 맞는지 다시 확인한다. E01이라는 문자열은 질문별 로컬 ID이므로 영구 정본 ID로 사용하지 않는다.

### 3.2 질문 계획

질문 계획은 원문을 보존한 채 검색 가설을 만든다.

```json
{
  "question": "금융회사가 외부기관에 심사업무를 위탁해도 되는가?",
  "mentions": [
    {"surface": "금융회사", "role": "SOURCE_ACTOR"},
    {"surface": "외부기관", "role": "TARGET_ACTOR"},
    {"surface": "심사업무", "role": "OBJECT"},
    {"surface": "위탁", "role": "ACTION"}
  ],
  "family_hypotheses": [{"family_id": "ENTRUSTMENT"}],
  "predicate_hypotheses": [{"predicate": "ENTRUSTS_TASK"}]
}
```

이 값은 hard AND 필터가 아니다. 복수 가설을 허용하고, 불확실한 grounding은 다른 검색 경로를 차단하지 않는다. 특히 사용자가 법명·조문을 명시한 경우 그 좌표가 가장 강한 anchor다.

### 3.3 후보 상태

각 후보에는 좌표와 점수뿐 아니라 출처와 역할이 남는다.

```text
coordinate
score
branch_id
origins
relation_ids
coverage_keys
matched terms
source_order
```

`origins`는 closed grounding, legal-system prior, semantic entry, relation expansion, baseline floor 등 후보가 왜 생겼는지를 나타낸다. 같은 좌표가 여러 경로에서 나오면 정본 좌표로 합치되 provenance는 합집합으로 보존한다.

## 4. 12단계 회수·검증 상태 머신

{{FIGURE_RETRIEVAL_STAGES}}

### 4.1 단계 원장

| 단계 | 하는 일 | 실패 시 동작 | 법률적 의미 |
|---|---|---|---|
| 1. `question-source` | 질문 원문을 실행의 source로 고정 | 해당 없음 | 이후 모든 span·가설의 원점 |
| 2. `closed-grounding-retrieve` | DB에 존재하는 역색인 개념·용어로 후보 생성 | 빈 결과여도 계속 | 없는 개념을 발명하지 않되 검색을 중단하지 않음 |
| 3. `legal-system-route-retrieve` | issue별 법률 영역→법령→진입 조문 선택 | 다른 branch 유지 | 법명→조→항으로 내려가는 법체계 탐색의 시작 |
| 4. `semantic-card-retrieve` | 의미 카드 posting으로 유력 조문 진입 | AND 무결과면 term별 OR branch | 그래프에 있는 정답으로 들어가는 검색 입구 |
| 5. `baseline-floor-union` | 기존 LegalClosure 결과를 immutable floor로 합침 | 절대 삭제 금지 | 새 구조 때문에 기존 회수 정답을 잃지 않음 |
| 6. `typed-legal-relation-expand` | 정의·위임·준용 등 활성 predicate의 bounded closure | 관계 실패는 후보 추가만 포기 | 법률효과 관계와 단순 유사도를 구별 |
| 7. `wiki-method-dependency-expand` | 정의 우선·단서·제재 등 읽기 방법을 dependency 요청으로 변환 | 결론이나 coverage로 승격하지 않음 | 법률가식 동반 조문 탐색 |
| 8. `adaptive-gap-retrieve` | 유력 법령의 인접 조문을 cursor/page 방식으로 추가 | 다음 법령·다음 페이지로 이동 | 전역 cutoff 대신 법령 내부 탐색 |
| 9. `provenance-canonicalize` | current article root로 정본화하고 원문 span 재검증 | 검증 실패 후보 제외, floor 보호 | 오래된 조문·빈 원문·좌표 오류 차단 |
| 10. `actor-scope-filter` | 명시 시장·행위자·숫자 scope 불일치 후보 완화 제거 | baseline floor는 제거하지 않음 | 코스닥 질문에 코스피 규정을 지배근거로 쓰는 오류 방지 |
| 11. `verified-coverage-select` | 검증 후보를 cap 안에서 선택 | floor 전부 포함, coverage·점수·순서 사용 | 최종 LLM 입력 예산 안의 증거 묶음 |
| 12. `compiled-evidence-present` | 선택 좌표를 원문 Section으로 제시 | 좌표·본문 불변 | 답변 모델이 실제로 보는 최종 검색 결과 |

### 4.2 immutable baseline floor

기존 LegalClosure가 회수한 조문은 5단계에서 `baseline-floor`로 합쳐진다. 점수는 매우 높게 주고 `mandatory=True`, `baseline_floor=True`로 표시한다. 최종 compiler가 이 집합을 포함하지 않으면 런타임 오류를 발생시킨다.

이 설계의 목적은 새 법률 구조가 도움을 주지 못하더라도 기존 정답을 삭제하지 않게 하는 것이다. 보조 자원 로딩, 그래프, grounding이 실패하면 전체 파이프라인은 floor-only fallback으로 돌아간다.

### 4.3 법체계 기반 진입

질문에서 법률 영역과 issue branch를 만들고, branch마다 최대 8개 법령과 법령별 진입 조문을 계획한다. 이 단계는 전체 16,506개 article root를 한 번에 순위화하는 방식과 다르다.

```text
업무위탁 issue
  ├─ 금융회사 업무위탁의 직접 규율 법령
  ├─ 감독규정·시행세칙
  └─ 개인정보·신용정보 동시 관문

각 법령
  ├─ 정의조
  ├─ 본칙·금지·허용 조문
  ├─ 위임받은 세부기준
  └─ 보고·승인·제재 조문
```

한 branch가 실패해도 다른 branch는 병렬로 유지된다. 검색 cap은 한 번에 보는 조문 수이지, 법체계 탐색 전체를 중단하는 cutoff가 아니다.

### 4.4 semantic card의 위치

semantic card는 정답 자체가 아니라 진입 posting이다. 질문 용어와 카드가 맞으면 해당 조문 좌표를 후보에 넣지만, 카드의 요약문을 법률 근거로 사용하지 않는다. 최종 evidence가 되려면 current corpus 원문이 다시 확인되어야 한다.

이 구분은 다음 문제를 해결한다.

```text
그래프가 정답 조문을 설명할 수 있음
≠
사용자 질문에서 그 조문의 시작 좌표를 찾을 수 있음
```

카드는 두 상태 사이의 검색 입구다.

### 4.5 typed relation closure

질문 계획의 `family_hypotheses`와 `predicate_hypotheses`로 활성 관계를 좁힌다. 위임, 재위임, 정의 사용, 규범 내용의 준용·적용, 업무위탁 같은 관계를 모두 일반 `related_to`로 처리하지 않는다.

관계에서 발견한 target은 `RELATION_EXPANDED` 후보일 뿐이다. 다음 원칙이 적용된다.

- 관계 발견만으로 verified evidence가 되지 않는다.
- 위탁 관계가 있다고 권한 전체 이전을 추론하지 않는다.
- 수임 사실을 새로운 재위임 권한으로 확대하지 않는다.
- 준용 관계를 원문과 완전히 동일한 법률효과로 보지 않는다.
- target 조문 원문과 authority generation이 검증되어야 최종 제시 가능하다.

### 4.6 adaptive law-local page

유력 법령의 진입 조문 주변을 4개 단위 page로 읽고, 다음 page 점수와 coverage 상태를 보고 계속할지를 정한다. 하나의 조문만 보고 매번 LLM을 다시 부르는 구조가 아니라, 사람보다 넓은 branch를 병렬로 열면서 각 branch 안에서는 법령 순서를 따라간다.

### 4.7 cap의 의미

- 절대 최대: `32`개 article root
- 정상 제시 목표: `28`개
- 내부 후보 최대: `96`개
- baseline floor가 28보다 크면 floor 길이까지 보호하되 32를 넘지 않는다.

28은 “정답이라고 확정한 수”가 아니라 답변 모델이 한 번에 검토할 수 있도록 정본화·검증 후 제시하는 수다. ADR-0118·0131·0132 비교에서는 61문항 모두 정확히 28개가 제시되었다.

## 5. 비파괴 atomic claim compiler

{{FIGURE_COMPILER_PACKET}}

### 5.1 목적

28개 원문이 있어도 LLM은 필요한 본칙과 동반 세칙을 고르지 못할 수 있다. compiler는 질문의 쟁점을 soft checklist로 만들고, 조문 안의 exact quote를 법률 역할과 evidence ID에 결속한다.

중요한 점은 이 계층이 회수 결과를 바꾸지 않는다는 것이다.

```text
before coordinates == after coordinates
before order       == after order
before source text == after source text
```

### 5.2 compiler 입력

```text
[질문]
사용자 원문

[선택 evidence 메뉴]
E01 좌표·법명·조문·scope·전문
...
E28 좌표·법명·조문·scope·전문
```

제품 중간 모델은 `claude-haiku-4-5-20251001`이고, run-002의 compiler 출력 한도는 8,000 tokens다. run-001에서 장문 JSON이 4,000 tokens에서 절단된 문제가 있어 출력 예산만 확대한 재현 run이 v4b다.

### 5.3 compiler 출력 계약

```json
{
  "issues": [
    {"issue_id": "I1", "question_span": "질문의 연속 exact span"}
  ],
  "units": [
    {
      "unit_id": "U1",
      "evidence_id": "E01",
      "issue_ids": ["I1"],
      "role": "GOVERNING_RULE",
      "quote": "E01 원문의 연속 exact quote"
    }
  ],
  "reason": "짧은 컴파일 이유"
}
```

제약은 다음과 같다.

- issue는 최대 4개다.
- `question_span`은 질문에 실제로 존재하는 연속 문자열이어야 한다.
- soft unit은 최대 20개다.
- evidence ID는 E01~E28의 닫힌 목록 안에 있어야 한다.
- quote는 해당 evidence 전문에 존재하는 연속 원문이어야 한다.
- 질문이 특정 시장을 명시하면 다른 시장 규범을 soft unit으로 선택하지 않는다.
- requirement ID나 요약된 법률효과를 새로 만들지 않는다.

### 5.4 legal role

compiler가 사용할 수 있는 역할은 여덟 개다.

| role | 의미 | 답변에서의 용도 |
|---|---|---|
| `GOVERNING_RULE` | 질문을 직접 지배하는 본칙 | 주된 허용·금지·의무 근거 |
| `DEFINITION` | 법정 용어 의미 | 수범자·대상·행위 범위 고정 |
| `CONDITION` | 발생·허용 요건 | 사용자 사실과 대조 |
| `EXCEPTION` | 본칙 배제·변경 | 단정 결론의 범위 제한 |
| `PROCEDURE` | 승인·보고·기간·방식 | 실제 이행 행동 설명 |
| `SANCTION` | 위반 효과 | 위험·제재 설명 |
| `COMPANION` | 함께 읽어야 완성되는 조문 | 본칙과 시행세칙·위임규정 결속 |
| `CONTEXT` | 탐색 보조 원문 | 독립 법률효과로 오해하지 않음 |

role은 조문의 영구 단일 분류가 아니라 이 질문에서 해당 quote가 수행하는 역할이다. 같은 조문도 다른 질문에서는 다른 role이 될 수 있다.

### 5.5 non-destructive CONTEXT fallback

LLM compiler가 soft unit으로 고르지 않은 evidence도 삭제하지 않는다. 코드가 해당 조문의 앞부분에서 최대 1,000자의 exact quote를 가져와 `CONTEXT` unit을 만든다.

이 장치는 정답 조문이 compiler 선택 실수 때문에 사라지는 것을 막는다. 대신 compiler packet이 커지는 비용이 있다. ADR-0118에서는 전체 1,776 claims 중 1,489개가 deterministic CONTEXT였다. 따라서 관찰된 성능 향상에는 핵심 claim guide 효과와 28개 원문 재구조화 효과가 함께 섞여 있다.

### 5.6 compiler packet

최종적으로 각 Section의 `legal_meta.legal_compilation`에 같은 immutable packet이 붙는다.

```text
schema_version: integrated-atomic-claim-evidence-v4
answer_mode: ADVISORY
direct_rule_answer_allowed: true
selected_evidence_ids
issues
units
claims
coverage: []
missing: []
selected_scope_ids
reason
```

`claim.proposition`은 해석 결과가 아니라 `claim.quote`와 같은 원문이다. `coverage`와 `missing`이 비어 있다는 점도 중요하다. ADR-0118 compiler는 완성된 포섭·coverage 엔진이 아니라 근거 사용을 돕는 soft compiler다.

## 6. 답변 합성과 결정론 gate

### 6.1 답변 모델이 실제로 받는 것

답변 모델은 compiler가 선택한 unit만 받는 것이 아니다. 다음을 함께 받는다.

1. compiler packet 전체
2. 최종 28개 조문의 좌표·법명·조문 경로·원문 전문
3. 함께 선택된 인용·관계 간선
4. 법률 scope 정보
5. 선택 규정의 필요한 정의 부록
6. 활성화된 Wiki 읽기 방법

이 구조에서 compiler는 원문을 대체하지 않는다. 원문을 탐색하는 가이드다.

### 6.2 답변 프롬프트의 핵심 계약

- claims는 검증된 원문 span과 closed evidence ID의 목록이다.
- issues는 빠뜨리기 쉬운 쟁점의 soft checklist다.
- quote는 근거이지 자동 포섭 결론이 아니다.
- CONTEXT claim은 탐색 보조이며 요약된 법률효과로 취급하지 않는다.
- 핵심 결론에 실제 사용한 evidence ID만 `evidence_ids`에 선언한다.
- 목록 밖 evidence ID를 만들지 않는다.

답변 출력의 핵심 모양은 다음과 같다.

```json
{
  "answer": "근거가 허용하는 범위의 답변",
  "answerable": true,
  "conclusion_strength": "DIRECT | CONDITIONAL | INSUFFICIENT",
  "evidence_ids": ["E01", "E13"]
}
```

### 6.3 결정론 gate

LLM 답변 뒤에 추가 모델 judge를 부르지 않고 코드로 다음을 검사한다.

```text
답변 evidence_ids ⊆ compiler.selected_evidence_ids
answerable == true 이면 evidence_ids가 비어 있지 않음
```

위반하면 답변을 다음 상태로 강등한다.

```text
answerable = false
conclusion_strength = INSUFFICIENT
evidence_ids = []
```

이 gate는 닫힌 ID 무결성은 보장하지만, 고른 조문이 실제 정답인지까지 판단하지 않는다. E01이 목록 안에 있다는 사실과 E01이 질문의 지배규정이라는 사실은 다르다.

### 6.4 “최종 검색 제시”와 “답변 사용 선언”

두 지표는 시스템의 서로 다른 병목을 측정한다.

| 지표 | 집합 | 묻는 질문 |
|---|---|---|
| 최종 검색 제시 | 답변 모델에게 준 28개 좌표 | 필요한 조문을 찾고 끝까지 보존했는가 |
| 답변 사용 선언 | 답변의 `evidence_ids` 좌표 | 제시된 조문 중 실제 답에 쓸 것을 골랐는가 |

ADR-0118의 동일 28개 제시 단계에서 Golden61 v3 corpus-resolvable 필요 조문은 `95/116`, recall `81.90%`였다. 그러나 답변 사용 선언은 `67/116`, recall `57.76%`였다.

```text
필요 조문 116
  ├─ 최종 28개 안에 존재: 95
  │    ├─ 답변이 실제 선언: 67
  │    └─ 있었지만 사용하지 않음: 28
  └─ 최종 28개에 없음: 21
```

따라서 현재 가장 큰 병목은 회수만이 아니다. 이미 제시된 정답 조문을 답변 모델이 고르지 않는 선택 손실이 크다.

## 7. 실제 처리 예시: cm-008

{{FIGURE_CM008}}

### 7.1 질문

```text
국내 일반기업의 3개월 보유기간이 6개월로 연장되는 경우는?
(업무 문맥: 상장주선인의 의무인수 및 보유)
```

### 7.2 필요한 법률 구조

이 질문은 숫자 `3개월→6개월`만 찾으면 끝나지 않는다. 두 조문이 하나의 답을 만든다.

| evidence | 좌표 | 역할 | 필요한 이유 |
|---|---|---|---|
| E01 | 코스닥시장 상장규정 제13조 | `GOVERNING_RULE` | 국내 일반기업의 기본 3개월과 6개월 연장 관문을 규정 |
| E13 | 코스닥시장 상장규정 시행세칙 제15조 | `CONDITION/COMPANION` | “세칙으로 정하는 사유”의 구체적 요건을 규정 |

제13조만 보면 “혁신기술기업이고 상장주선인이 세칙으로 정하는 사유”라는 관문까지만 알 수 있다. 실제 어떤 사유인지 답하려면 시행세칙 제15조를 함께 읽어야 한다.

### 7.3 compiler가 하는 일

compiler는 질문 span을 하나의 issue로 만들고, E01의 단서 quote와 E13의 정의 quote를 각각 closed ID에 결속한다. 두 조문을 삭제하거나 하나의 요약문으로 합치지 않는다.

```text
I1: “3개월 보유기간이 6개월로 연장되는 경우”
  ├─ E01 / GOVERNING_RULE / 3개월·6개월 단서 exact quote
  └─ E13 / CONDITION / “세칙으로 정하는 사유” exact quote
```

원문만 준 ADR-0131에서는 모델이 E26 하나를 골라 TP 0, FP 1, FN 2가 되었다. ADR-0118 full compiler에서는 E01과 E13을 모두 선언해 TP 2, FP 0, FN 0으로 완전충족했다. 이 사례는 compiler의 장점이 “새 정답 조문을 찾는 것”이 아니라, 이미 28개 안에 있던 본칙과 세칙을 함께 사용하게 하는 것임을 보여준다.

### 7.4 법률 답변의 형태

답변은 단순히 “6개월이다”가 아니라 다음 구조를 가져야 한다.

1. 본칙: 국내 일반기업의 기본 의무보유 기간은 3개월이다.
2. 연장 관문: 상장신청인이 혁신기술기업이고 상장주선인이 세칙상 사유에 해당하면 6개월이다.
3. 세부 요건: 상장주선인의 최근 3년 내 기술성장기업 주선실적과 그 기업의 상장 후 2년 내 지정·상장폐지 관련 사건이 있어야 한다.
4. 부정 범위: 혁신기술기업이라는 사정만으로 자동 연장되는 것은 아니다.

## 8. 성능 결과의 정확한 읽는 법

{{FIGURE_PERFORMANCE}}

### 8.1 역사적 semantic 답변 평가

ADR-0118 run-002에서 같은 28개 evidence를 공유한 baseline 답변과 compiler 답변을 paired Haiku judge로 비교했다.

| arm | 정답 | 정확도 | 입력 tokens | product p95 |
|---|---:|---:|---:|---:|
| 동일 회수 + 기존 답변 | 26/61 | 42.62% | 11.51M | 153.6초 |
| 동일 회수 + atomic compiler | 38/61 | 62.30% | 19.19M | 188.8초 |

paired 결과는 candidate-only 정답 20건, baseline-only 정답 8건, 둘 다 정답 18건, 둘 다 오답 15건이다. required issue omission은 8건에서 1건으로 줄었다. 반면 오답 유형 중 unsupported inference는 8건에서 10건으로 늘었고, governing rule selection 오류도 4건에서 5건으로 늘었다. 별도 안전 플래그인 unsupported definitive conclusion은 20건에서 18건으로 줄었다.

따라서 compiler가 근거 활용률을 높인 것은 분명하지만, 모든 과잉 추론과 지배규정 선택 오류를 해결한 것은 아니다.

### 8.2 Golden61 v3 조문 집합 재평가

ADR-0128 이후에는 추가 judge 없이 답변이 선언한 evidence ID와 v3 필요 조문 집합을 결정론적으로 비교했다.

| 구분 | TP/필요 | FP | FN | Precision | Recall | F1 | 완전충족 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 전체 61 | 67/116 | 72 | 49 | 48.20% | 57.76% | 52.55% | 29/61 |
| core 51 | 55/98 | 58 | 43 | 48.67% | 56.12% | 52.15% | 24/51 |
| hard 10 | 12/18 | 14 | 6 | 46.15% | 66.67% | 54.55% | 5/10 |

난도균형 점수는 core `51.534`, hard `53.744`, 최종 `52.638970`이다. 이 점수가 최신 비교 구조 중 가장 높다.

### 8.3 회수 성능

ADR-0118이 상속한 28개 final-present 집합은 질문당 28개, 전체 1,708개 조문이다.

| 항목 | 값 |
|---|---:|
| 전체 corpus | 16,506 article roots |
| 질문당 최종 제시 | 28 |
| 제시 비율 | 0.16964% |
| decisive recall, 당시 v2 좌표 | 77/90 = 85.56% |
| Golden61 v3 corpus-resolvable recall | 95/116 = 81.90% |
| 답변 선언 recall | 67/116 = 57.76% |

제시 recall과 답변 선언 recall의 차이 `28개 조문`이 현재 selection/compiler 개선의 핵심 대상이다. 반대로 final-present에도 없는 `21개 조문`은 retrieval/data 개선의 대상이다.

### 8.4 비용과 지연

compiler arm은 baseline 대비 input token이 66.7% 늘었고 product p95가 35.2초 늘었다. 정확도 향상과 함께 이 비용 증가가 ADR-0118의 운영 `Rejected` 이유 중 하나다. 고정 기준으로 사용하되, 운영화 전에 packet 압축과 호출 구조 최적화가 필요하다.

## 9. 강점과 남은 구조적 문제

### 9.1 강점

- baseline floor를 삭제하지 않는 add-only 회수 계약이 있다.
- 법체계→법령→조문 진입과 법령 내부 page 탐색을 구분한다.
- semantic card를 검색 입구로 사용하고 원문 근거와 분리한다.
- 위임·준용·정의 등 typed relation을 질문 family에 따라 제한한다.
- 모든 최종 evidence를 current corpus 원문으로 다시 검증한다.
- atomic compiler가 closed evidence ID와 exact quote를 결속한다.
- compiler 오류가 조문 삭제로 이어지지 않는 non-destructive fallback이 있다.
- 답변이 실제 사용한 evidence ID를 명시하므로 selection 성능을 별도 측정할 수 있다.
- 목록 밖 ID와 무근거 answerable을 결정론 gate로 차단한다.

### 9.2 남은 문제

| 문제 | 관찰 | 의미 |
|---|---|---|
| final retrieval miss | 21/116 필요 조문이 28개에 없음 | 질문 진입·관계·cap 이전 회수 개선 필요 |
| answer selection loss | 제시된 95개 중 28개를 미선언 | LLM이 본칙·동반조문을 함께 고르지 못함 |
| excess evidence | FP 72 | compiler role·issue가 distractor 선택도 유도 |
| CONTEXT 과다 | 1,776 claims 중 1,489 | 비파괴성 대가로 packet이 크고 신호가 희석 |
| 실제 포섭 미완성 | coverage·missing이 비어 있음 | 사실→요건 충족→예외 적용의 기계적 검증 부족 |
| scope·지배규정 오류 | candidate 오답에서 지속 | closed ID만으로 법률적 적합성을 보장 못함 |
| 비용·지연 | +66.7% input, +35.2초 p95 | 운영 SLA 전에 압축 필요 |
| 일반화 미확인 | in-sample 단회 | holdout/OOS 전 운영 승격 불가 |

### 9.3 compiler가 잘못 가이드할 수 있는 지점

compiler의 issue와 role은 LLM이 만든 잠정 가이드다. exact quote는 검증되지만 “왜 이 quote가 이 질문에 필요한가”는 완전히 검증되지 않는다. ADR-0132에서는 guide에 올라온 unique evidence 151개 중 gold가 55개뿐이었고, 모델이 선택한 guided evidence 103개 중 51개가 FP였다.

따라서 향후 compiler를 강화할 때도 다음 불변조건은 유지해야 한다.

```text
가이드가 후보를 삭제하지 않음
가이드보다 원문을 우선함
본칙·필수 companion을 원자 묶음으로 보호함
free-form 설명보다 closed ID와 결정론 검증을 우선함
```

## 10. 고정 설정표

| 항목 | 고정값 |
|---|---|
| 기준 experiment/arm | `ADR-0118-experiment-v1/integrated-atomic-claim-v4b` |
| 기준 run | `run-002` |
| retrieval parent | ADR-0114 `integrated-seven-layer` |
| product/intermediate model | `claude-haiku-4-5-20251001` |
| dataset | Golden61 v3, core 51 + hard 10 |
| corpus-resolvable gold | 116 provisions |
| authority | `20260827` |
| corpus 규모 | 16,506 current article roots |
| internal candidate cap | 96 |
| normal presentation target | 28 |
| absolute evidence cap | 32 |
| issue cap | 4 |
| soft unit cap | 20 |
| fallback quote cap | evidence당 1,000 chars |
| compiler max output | 8,000 tokens |
| answer max output | 4,000 tokens |
| objective | FN 우선 legal Tversky + core/hard 50:50 |
| MAIN wiring | unchanged |
| decision eligibility | false, in-sample |

### 10.1 고정 hash와 원장

| 자산 | 식별값 |
|---|---|
| corrected input lock | `7636cc52ac0bd94a10baa1d75f3f381940981ff86beafa7f7ee91fedf9308452` |
| ADR-0118 run-002 capture seal | `2b50d2b2e13bbc96cf144ec8b93a6d0ccf16bf3fe4b34011f4b019c7d4ba3ba4` |
| ADR-0128 aggregate | `accea0282672f490ff03ac8faf06de9b394b74e3006c630dd97b90d1dc6b44a4` |

## 11. 구현 위치와 재현 경계

### 11.1 핵심 코드

| 역할 | 파일 |
|---|---|
| 12단계 통합 회수 | `lawrag/core/rag/integrated_legal_research.py` |
| 비파괴 atomic compiler | `lawrag/core/rag/integrated_atomic_claim_research.py` |
| 답변 packet 주입·closed ID gate | `lawrag/core/rag/answer.py` |
| ADR-0118 Golden61 runner | `scripts/rag_integrated_atomic_claim_golden_61.py` |
| 혼동행렬·난도균형 scorer | `lawrag/core/rag/evidence_confusion.py`, `scripts/rag_legal_evidence_confusion_objective.py` |

### 11.2 실험 정본

| 내용 | 경로 |
|---|---|
| 구조·semantic 평가 | `docs/adr/ADR-0118-integrated-atomic-claim-compiler-golden-61/README.md` |
| v3 목적함수 | `docs/adr/ADR-0128-legal-evidence-confusion-objective/README.md` |
| raw 직접선택 비교 | `docs/adr/ADR-0131-raw-evidence-id-selection-golden-61/README.md` |
| 선별 가이드 비교 | `docs/adr/ADR-0132-selective-legal-guide-evidence-selection-golden-61/README.md` |

### 11.3 재현 명령은 기록만 유지한다

현재는 사용자의 요청에 따라 추가 실험을 중단한다. 아래는 새 실행 권고가 아니라 기존 구조의 재현 위치를 명시하는 기록이다.

```text
.venv/bin/python scripts/rag_integrated_atomic_claim_golden_61.py --prepare-fixtures
.venv/bin/python scripts/rag_integrated_atomic_claim_golden_61.py --preflight-only
.venv/bin/python scripts/rag_integrated_atomic_claim_golden_61.py --workers 4
```

재실행은 새 결과를 기존 run에 덮어쓰지 않고, 실험 표준에 따라 새 ADR/run으로만 수행해야 한다.

## 12. 최종 운영 해석

이 구조의 핵심은 “LLM에게 잘 생각하라고 지시하는 프롬프트”가 아니다. 정답을 찾고 사용하는 일을 서로 다른 계약으로 나눈 것이다.

```text
법체계와 여러 검색 경로로 넓게 회수한다.
    ↓
정본 좌표·시점·원문을 검증한다.
    ↓
기존 회수 결과를 절대 삭제하지 않는다.
    ↓
질문 쟁점과 exact quote를 원자 claim으로 결속한다.
    ↓
28개 원문 전체와 가이드를 함께 준다.
    ↓
답변이 실제 사용한 closed evidence ID를 선언하게 한다.
    ↓
목록 밖 ID와 무근거 답변을 코드로 차단한다.
```

현재 기준에서 가장 잘 작동하는 지점은 본칙과 필수 동반조문을 함께 사용하도록 돕는 부분이다. 가장 약한 지점은 이미 제시된 정답 조문을 마지막 답변에서 고르는 부분과, 선택한 조문을 사용자 사실에 정확히 포섭하는 부분이다.

따라서 ADR-0118은 다음 비교의 출발점으로는 적합하지만, 운영 법률판단 엔진의 종착점은 아니다. 이후 변경이 필요할 때는 이 고정 구조를 통째로 교체하기보다 `회수 miss`, `answer selection loss`, `subsumption gap` 가운데 어느 병목을 바꾸는지 분리해 비교해야 한다.

## 부록 A. 상태와 용어

| 용어 | 이 문서에서의 뜻 |
|---|---|
| baseline floor | 기존 LegalClosure가 찾은 조문 중 새 구조가 삭제할 수 없는 집합 |
| final-present | 검증 후 답변 모델에게 제시한 최종 28개 조문 |
| answer-declared | 답변 모델이 실제 근거로 사용했다고 선언한 evidence ID 집합 |
| issue | 질문에서 빠뜨리기 쉬운 독립 쟁점의 exact span |
| unit | 하나의 issue·role·evidence ID·exact quote 결속 |
| claim | ADR-0118에서는 해석 결론이 아니라 unit의 원문 quote와 동일한 명제 |
| CONTEXT | compiler가 고르지 않은 조문도 삭제하지 않기 위한 탐색 보조 binding |
| coverage | 판단에 필요한 역할이 근거로 채워졌는지의 상태. ADR-0118 packet에서는 미완성 |
| complete | 질문의 corpus-resolvable 필요 조문을 답변 선언 집합이 모두 포함 |
| exact | 답변 선언 집합이 필요 조문 집합과 정확히 일치 |
| gate | LLM judge가 아니라 ID·빈 근거 등 구조 위반을 검사하는 결정론 코드 |

## 부록 B. 고정 결정 체크리스트

- [x] 최신 비교 실험 ADR-0131·0132의 결과를 포함했다.
- [x] 고정 목적함수에서 최고 점수 구조를 선택했다.
- [x] 정확한 experiment/arm/run을 기록했다.
- [x] MAIN 승격과 연구 기준선 고정을 구분했다.
- [x] 검색 제시 성능과 답변 사용 선언 성능을 구분했다.
- [x] 회수 12단계와 compiler·답변 gate를 분리해 설명했다.
- [x] 데이터·모델·authority·cap·hash를 기록했다.
- [x] 추가 실험은 중단하고 기존 봉인 결과만 사용했다.
