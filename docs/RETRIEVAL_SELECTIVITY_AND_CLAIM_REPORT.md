# 회수 선택률·Claim 실험 종합 보고서

- 실행일: 2026-08-25
- 완료일: 2026-08-26
- 모든 LLM: `claude-haiku-4-5-20251001`
- main wiring / canonical 변경 없음

## 핵심 답변

현재 69/70 recall은 corpus 대부분을 답변에 넣어서 얻은 수치가 아니다.

- 전체 현행 조문: **17,370개**
- 질의당 최종 제시: 평균 **15.84개**, p50 16개, p95/최대 20개
- 조문 수 선택률: 평균 **0.0912%**
- 전체 조문 본문: **8,152,097자**
- 질의당 제시 본문: 평균 **28,265자**
- 본문 문자 선택률: 평균 **0.3467%**
- 실제 답변 API input: 평균 **36,466.7 tokens**
- 최종 gold recall: **69/70(98.57%)**

다만 초벌 후보 단계는 넓다.

- active assertion 좌표 universe: **20,793개 / 106문서**
- broad 후보: 평균 **1,905개(9.16%)**
- 후보 문서: 평균 84.25개, 중앙값 **97개(91.5%)**
- p95 후보: 4,485개(21.57%)
- 최대 후보: 4,743개(22.81%)

즉 질문의 예처럼 90%를 최종 답변에 넣는 것은 아니지만, upstream 문서 후보기는
중앙값 기준 91.5%의 문서를 건드린다. 좌표 수준으로는 평균 9.16%다.

## 실제 LLM 노출 funnel

broad 1,905개 후보 전체를 한 번에 Haiku에 넣지는 않는다. 계층 메뉴로 나누어
선택한다.

| 단계 | 질의당 평균 | p50 | p95 | 최대 |
|---|---:|---:|---:|---:|
| exact-structural option slot 노출 | 63.86 | 48 | 155 | 448 |
| Assertion-tree menu item 노출 | 173.02 | 150 | 525 | 567 |
| 두 채널 합계 노출 | 236.88 | 202 | 615 | 710 |
| 기록 navigation calls | 14.59 | 14 | 27 | 47 |
| 최종 답변 조문 | 15.84 | 16 | 20 | 20 |

menu item 합계는 문서→조문 등 계층별 반복 노출을 포함하므로 unique 후보 수가 아니다.

51건 전체에서는 최종 조문 presentation 808개, unique 393개 조문, 46개 문서가
사용됐다. gold 69/808=8.54%는 정답 조문 목록이 필요한 모든 보조 조문을 포괄하지
않으므로 precision이 아니라 gold density의 하한이다.

## 후보 축소 대안의 trade-off

| 후보 정책 | 좌표 평균 선택률 | 문서 중앙값 선택률 | candidate recall |
|---|---:|---:|---:|
| broad OR | 9.16% | 91.51% | 64/70 |
| family top8 | 4.64% | 14.15% | 62/70 |
| balanced join | 0.70% | 31.13% | 40/70 |
| strict join | 0.38% | 22.64% | 35/70 |

강하게 줄이면 recall 손실이 너무 크다. family top8은 문서를 크게 줄이면서 62/70을
보존하지만, 이것만으로 현재 여러 채널을 합친 final 69/70을 대체할 수는 없다.

## Claim edge·entailment matrix 결과

원문 card를 고정하고 Haiku가 actor·predicate·modality·condition·exception 슬롯만
채우게 했지만, 2-pass exact claim Jaccard는 **0.0365**였다. 12건 24 pass에서
publish claim 199개 중 2회 동일한 것은 7개뿐이었다. 같은 의미라도 span 경계를
다르게 잘랐기 때문이다.

consensus가 있던 4건의 matrix 답변도 3건은 존재하지 않는 claim ID를 반환해
fail-closed됐고, 남은 1건은 baseline 정답→matrix 오답이었다. 따라서 배선하지 않는다.

후속으로 원문 한 줄 전체를 claim span으로 고정한 pair-first 변형도 실행했다.

- Jaccard: 0.0365 → **0.6453**
- output tokens: 140,466 → **31,165**
- p50: 39.47초 → **8.77초**
- consensus claims: 7 → **231**

관계 데이터 생성 방향은 크게 개선됐지만 사전 기준 0.80에는 못 미쳤다. 12건 중
matrix render 10건이 유효했고 2건은 존재하지 않는 claim ID 때문에 차단됐다.
유효 답변 10건의 3표결은 baseline 4/10, matrix 3/10이었다. full-only 2건,
matrix-only 1건으로 순손실 1건이다. `cm-009`처럼 질문이 묻는 면제 규정에 다른
의무보유 예외를 섞고, `cm-023`처럼 불필요한 산식을 확장한 것이 회귀 원인이었다.

따라서 full-line claim은 다음 data compiler의 출발점으로는 남기되, 답변에는 배선하지
않는다.

다음 claim 방식은 Haiku가 span을 자유 생성하게 해서는 안 된다. 형태소·의존구문 또는
원문 token offset으로 `(actor, predicate, object, condition, exception)` 후보를 먼저
고정하고 Haiku는 닫힌 후보의 역할만 판정해야 한다.

## 저비용으로 남길 수 있는 것

수치·기간·비율·임계연산자·양태의 원문 exact support 감사는 유망했다.

- 51건 중 flag 5건
- 의미 오답 flag 4건, 정답 flag 1건
- precision 80%, 오답 recall 25%, 정답 false flag 2.86%
- LLM 호출 없음

recall이 낮아 자동 차단은 못 하지만, 답변 옆 경고와 검수 우선순위에는 사용할 수 있다.

## 산출물

- `var/eval/e2e/cm_core_retrieval_selectivity_funnel_51.json`
- `var/eval/e2e/cm_core_haiku_claim_edges_holdout12_repeat2.json`
- `var/eval/e2e/cm_core_claim_entailment_matrix_answer_ab_holdout12.json`
- `var/eval/e2e/cm_core_haiku_closed_line_claims_holdout12_repeat2.json`
- `var/eval/e2e/cm_core_closed_line_claim_matrix_answers_holdout12_frozen.json`
- `var/eval/e2e/cm_core_closed_line_claim_matrix_answers_holdout12_regrade3.json`
- `var/eval/e2e/cm_core_deterministic_critical_value_audit_51.json`
- `docs/adr/0036-haiku-claim-edge-entailment-matrix.md`
