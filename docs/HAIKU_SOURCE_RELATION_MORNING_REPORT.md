# Haiku 법률 관계·답변 일반화 실험 아침 보고서

- 실행일: 2026-08-25
- 모델: 모든 데이터 생성, 답변 생성, 의미 채점에
  `claude-haiku-4-5-20251001`
- 제품 영향: main wiring / canonical 변경 없음
- 누출 통제: 관계 생성 입력에 질문, case ID, gold, reference answer 없음

## 한 줄 결론

법률 관계 데이터는 **원문 표지로 후보쌍을 먼저 만들고 Haiku가 판정**하면 안정적으로
만들 수 있다. 그러나 그 관계를 검색 가지치기나 답변 문맥에 그대로 넣는 방식은
최종답변을 안정적으로 개선하지 못했다. 다음 병목은 관계 회수가 아니라
**질문의 주장과 법문의 주체·행위·양태·요건·예외를 claim 단위로 정렬하는 것**이다.

## 최종 의사결정

| 항목 | 결과 | 결정 |
|---|---|---|
| 3-family split | 안정성 54.3%→46.2%, 입력 3.02배 | 기각 |
| mixed multi-pass | probe Jaccard 0.409~0.453, holdout 0.482 | support tier만 보존 |
| 관계 기반 hard prune | node -66.7%, gold recall 26.7% | 기각 |
| relation-first rerank | probe gold@3 9→7 | 기각 |
| targeted EXCEPTION rescue | holdout stable 9, 수동 precision 88.9% | review candidate |
| actor role refinement | 공통 41개 role 41/41 일치 | shadow metadata |
| pair-first relation builder | Jaccard 1.000, 입력 65% 절감 | shadow builder 채택 |
| 구조 관계 답변 주석 | unseen 1/5 vs baseline 2/5 | 메인 배선 기각 |
| Wiki 후단 추가 | 기존 평가에서 입력 +54%, 순증 없음 | 계속 기각 |

## 가장 중요한 발견: pair-first

기존 방식은 Haiku에게 6종 관계를 자유롭게 발견·생성하도록 했다. 새 방식은 법문에서
다음 표지를 결정론적으로 찾아 닫힌 후보쌍을 만든 뒤 Haiku에게 `RELATION/NONE`만
판정시켰다.

- 정의 표지: `이란`, `말한다`, `뜻한다`, `정의한다`
- 위임 표지: 명시 조문 인용 + `세칙으로 정하는`, `위임받은`
- 예외 표지: 명시 조문 인용 + `에도 불구하고`, 직접 적용배제
- 버전 표지: 동일 문서·조문 + revision/enforcement/current 메타데이터

fresh 12건 2회 결과:

| 지표 | pair-first | mixed |
|---|---:|---:|
| 반복 교집합/합집합 | 138/138 | 1/13 |
| Jaccard | **1.000** | 0.0769 |
| 입력 tokens | **226,670** | 646,882 |
| calls | 46 | 24 |
| p50 | 11.75초 | 13.01초 |
| p95 | 25.16초 | 21.16초 |

Haiku 호출 수는 늘었지만 작은 닫힌 후보만 읽어 입력은 mixed의 35.0%였다. 수동 proof
감사는 `IMPLEMENTS/EXCEPTION_TO` 27/27, `DEFINED_BY` 표본 20/20이었다.

제약도 분명하다. cap 초과 후보 69개가 fail-closed 폐기됐고, 과거 버전 양성이 없어
`CURRENT_VERSION_OF` recall은 검증하지 못했다. 따라서 아직 canonical 자동 반영은
아니다.

## 답변 성능: 관계가 정확해도 바로 좋아지지 않았다

### 사전 등록한 unseen remainder

기존 probe 10건과 hash holdout 12건을 제외한 29건에서 mixed 2-pass를 새로 돌렸다.
2/2 구조 관계가 있던 사례는 5건이었다. 동일 evidence로 답변을 생성하고 동결 답변을
Haiku 3표결했다.

| 변형 | correct | paired 결과 |
|---|---:|---|
| full context | 2/5 | 기준 |
| structural annotation | **1/5** | full-only 1, annotation-only 0 |
| all relation annotation | 3/5 | full-only 0, annotation-only 1 |

기존 탐색 12건의 structural 5/12→7/12 개선은 일반화되지 않았다. 사전 채택 기준을
실패했으므로 구조 관계 주석은 메인에 넣지 않는다.

### 안정적인 pair-first 관계로 재시험

관계가 존재한 11건에서 전체 구조 관계 138개 주석은 full 6/11 대비 7/11이었다.
그러나 같은 주석의 반복 답변은 6/11이었고, `DEFINED_BY` 111개를 빼고
`IMPLEMENTS/EXCEPTION_TO` 27개만 준 재시험은 full 5/11, 주석 5/11이었다.
같은 재시험에서 정의까지 모두 준 변형은 2/11로 악화했다.

즉 +1은 생성 변동 범위이고, 대량 정의 주입은 오히려 문맥 오염이 될 수 있다.

## 왜 실패했는가

현재 관계의 대부분은 entity 또는 조문 단위다.

- `DEFINED_BY(A, B)`는 용어의 출처를 알려주지만 질문 결론의 조건을 검증하지 않는다.
- `IMPLEMENTS(A, B)`는 상하위 규범을 연결하지만 어떤 항·호의 어떤 요건을 구현하는지
  충분히 좁히지 못한다.
- `GOVERNS_ACTOR`는 같은 actor가 의무자, 권한자, 수익자, 절차대상 중 무엇인지 섞는다.
- 정확한 관계를 많이 넣으면 Haiku가 주변 설명을 확장하면서 핵심 수치·예외·양태에서
  벗어날 수 있다.

따라서 필요한 것은 더 큰 온톨로지가 아니라 더 작은 법률 명제다.

```text
(actor occurrence, predicate, modality, object,
 condition, exception, legal effect, source span)
```

질문 claim과 위 튜플을 먼저 정렬한 뒤, 답변의 각 문장을 어느 튜플이 지지하는지
제약해야 한다.

## Wiki 사용 판단

LLM Wiki는 버릴 필요는 없지만 용도가 다르다. 이미 ADR-0032에서 답변 후단 Wiki
추가는 정확도 순증 없이 입력을 약 54% 늘렸다. 이번에도 일반 정의와 actor 정보를
많이 주는 것이 답변 개선으로 이어지지 않았다.

권장 용도:

1. 질문 용어를 법문 surface로 정규화하는 전처리
2. 정확히 일치하는 정의조문 1~2개만 선택
3. claim schema의 actor/predicate 후보 생성
4. 답변 근거가 아니라 검색·해석 계획의 보조 메타데이터

비권장 용도는 Wiki 문단 전체를 최종 답변 prompt에 추가하는 것이다.

## 다음 실험 우선순위

1. **Claim edge compiler**: pair-first 후보 위에 Haiku가 주체·행위·양태·대상·조건·예외를
   closed schema로 추출하고 원문 span exact guard를 통과시킨다.
2. **Question-to-claim alignment**: 질문에서 요구하는 법적 효과와 조건을 뽑고, 관련
   claim만 답변 plan에 넣되 원문 evidence는 삭제하지 않는다.
3. **Entailment matrix**: 답변 전에 `결론/조건/예외/수치/기관권한` 슬롯별로 직접
   지지 조문을 하나씩 고르게 하고, 비어 있으면 단정하지 않게 한다.
4. **새 평가셋**: 현재 51건을 더 보며 튜닝하지 말고 새로운 법률·새 질문으로
   최소 30건 blind set을 만든다.
5. **결정론 평가 보강**: 수치, 기간, 부정/의무·재량 양태, 조문 인용은 LLM 채점과
   별도로 exact 검사한다.

마지막 router로 답변을 다시 쓰는 방식은 우선순위가 낮다. 현재 오답의 핵심은 문장
표현이 아니라 적용할 claim의 조건·효과 선택이기 때문이다.

## 산출물

- 결정 기록: `docs/adr/0035-haiku-source-relation-recall-stability.md`
- pair-first 상세 artifact: `var/eval/e2e/cm_core_haiku_pair_first_relations_fresh12_repeat2.json`
- unseen 답변 재채점: `var/eval/e2e/cm_core_source_relation_annotation_answer_abc_unseen29_regrade3.json`
- pair-first 답변 재채점: `var/eval/e2e/cm_core_pair_first_annotation_answer_abc_fresh12_regrade3.json`
- 계층 최소 주석 재채점: `var/eval/e2e/cm_core_pair_first_hierarchy_annotation_answer_abc_fresh12_regrade3.json`

