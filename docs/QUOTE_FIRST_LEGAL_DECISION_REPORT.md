# 1~9 shadow 실험 보고서 — 10번 제외

## 결론

메인 배선은 유지한다. 1~9를 모두 독립 shadow로 구현·실행했지만 최종 답변 정확도는
동결 12건에서 **baseline 5/12, raw 5/12, guarded 5/12**로 개선되지 않았다.

이번 실험이 확인한 핵심은 다음과 같다.

- 최종 오류는 단순히 “엉뚱한 조문이 회수됨”만의 문제가 아니다.
- 원문 quote ID, 수치, 기간, 양태를 강하게 제한해도 **질문을 지배하는 규범 선택**을
  잘못하면 오답이 그대로 남는다.
- 후단 Haiku를 두 번 돌려 합의시키는 방식은 12/12에서 슬롯 불일치가 발생해 confidence
  신호나 비용 절감 수단이 되지 못했다.
- Wiki를 법률지식 근거가 아니라 검색계획에만 써도 recall은 늘지 않고 후보가 7.94%
  증가했다.

따라서 현재 병목은 `회수 recall`보다 `governing rule selection → 조건/예외 적용 →
결론 연산`이다.

## 아이디어별 판정

| 번호 | 실험 | 결과 | 판정 |
|---:|---|---|---|
| 1 | family-top8→조건부 broad | 64/70 유지, 44/51 broad 열림, 절감 0 | 기각 |
| 2 | 증거 충족 certificate | 유효 7/12, 필수 기준 10건 실패 | 진단만 보존 |
| 3 | quote-first 최소 인용 | 5/12 동률, 병렬 열거 누락 반례 | 답변 사용 기각 |
| 4 | 폐쇄형 결론 선택 | enum contract는 안정, 정답 개선 0 | 기각 |
| 5 | 법률 operator AST | 양태 3건·수량관계 1건 검출 | shadow 진단 보존 |
| 6 | 수치·기간 계산기 | unsupported 숫자 0, critical 표면 2건 차단 | shadow 진단 보존 |
| 7 | 슬롯 자기불일치 router | 12/12 tiebreak, 절약 0 | 기각 |
| 8 | 명시적 충돌만 filter | 명시 충돌 0, 오삭제 0, 효용 관측 없음 | shadow 정의만 보존 |
| 9 | Wiki 검색계획 한정 | recall 동률, 후보 +7.94%, 51 Haiku calls | 기각 |

10번 수작업 문맥 precision gold는 요청대로 수행하지 않았다.

## 회수 실험

### 조건부 cascade

`scope 없음`을 broad fallback 신호로 선등록했지만 51건 중 44건이 해당했다. 법령명이
질문에 직접 적히지 않은 것이 일반적이어서, 이 신호는 회수 부족이 아니라 질문 형식의
특성에 가까웠다.

- family-top8: 62/70, 후보 평균 964.88
- broad-or: 64/70, 후보 평균 1,905.41
- 선등록 cascade: 64/70, 후보 평균 1,905.41

recall은 지켰지만 후보 25% 절감 기준은 실패했다.

### Wiki 검색계획

Wiki 자유서술은 답변에 넣지 않고, Haiku가 쟁점 카드와 조문 문체 probe만 생성했다.

- 51 calls, input 257,400 tokens, 오류 0
- recall 64/70 → 64/70
- 후보 평균 1,905.41 → 2,056.76 (+7.94%)
- broad fallback 44 → 43

한 사례의 route는 좁혔지만 전체 비용 대비 효용이 없었다.

## 답변 실험

### 구조

1. 원문에서 최대 56개 line quote card를 결정론으로 만든다.
2. question-required slot을 만든다.
3. Haiku 두 번이 문자열 생성 없이 quote ID와 닫힌 enum만 고른다.
4. 다른 슬롯만 세 번째 Haiku가 판정한다.
5. 코드가 본문/단서, 양태, 각각/합산, 비교연산자, 수치·기간을 검사한다.
6. certificate가 유효할 때만 최소 quote 집합으로 답을 렌더링한다.
7. 지원되지 않은 critical surface나 invalid support ID가 있으면 기존 답을 보존한다.

모든 제품·검색계획·채점 호출은 `claude-haiku-4-5-20251001`이다.

### 결과

- 유효 plan 12/12, 유효 certificate 7/12
- replace 3, keep 9
- raw critical-surface flag 2, unsupported numeric value 0
- baseline/raw/guarded 모두 5/12
- baseline-only 0, candidate-only 0

안전 가드는 회귀를 막았지만 새 정답을 만들지는 못했다.

### 대표 실패

- `cm-022`: 최소 set-cover가 원문의 병렬 열거 네 개 중 두 개만 남겨 불완전 답변이 됐다.
- `cm-012`: 질문이 요구한 “사내규정 제정 시기” 대신 내부통제기준 제·개정 의결 절차를
  골랐다. 원문 기반이지만 governing scope가 틀렸다.
- `cm-027`: 값은 모두 원문에 있었으나 양태/연산자 검문이 raw 답변을 차단했다.

## 비용

같은 12건 baseline과 비교하면 quote-first shadow는 calls +258%, input +82.9%, wall p50
+71.1%였다. 후단 router로 붙이면 baseline 생성 비용에 추가되므로 운영성이 없다.

## 다음 판단

지금 더 유망한 방향은 후단 프롬프트를 한 번 더 조정하는 것이 아니라, 질문마다
`이 조문이 결론을 지배한다/보조한다/적용범위가 다르다`는 적용관계를 출처와 함께
승인하는 것이다. 다만 같은 51건을 보고 그 관계를 만들면 다시 인샘플 과적합이 된다.
다음 검증은 신규 blind 질문에서 관계를 먼저 생성·동결하고 답변을 평가해야 한다.

## 산출물

- ADR: `docs/adr/0037-quote-first-legal-decision-pipeline.md`
- 회수 artifact: `var/eval/e2e/cm_core_conditional_retrieval_cascade_51.json`
- 답변 artifact: `var/eval/e2e/cm_core_haiku_quote_decision_holdout12_frozen.json`
- 3표결 artifact: `var/eval/e2e/cm_core_haiku_quote_decision_holdout12_regrade3.json`
- 구현: `lawrag/core/rag/experiments/haiku_quote_decision.py`
