# Haiku 원문 증명형 관계군 분리 반복 실험

## 결론

6개 관계를 3개 법률 기능군으로 분리한 전면 추출은 mixed 단일 호출보다 관계 후보를
더 많이 만들었지만, 반복 재현율은 낮고 입력 토큰은 3배였다. 따라서 전체 관계에 대한
family 분리는 채택하지 않는다. 다만 `EXCEPTION_TO`만 두 반복에서 동일 관계가
재현되어, 예외 관계만 표적 보강하는 후속 가설은 남긴다.

이 실험은 shadow 전용이다. main wiring과 canonical graph는 변경하지 않았다.

## 계약

- 모델: 모든 호출 `claude-haiku-4-5-20251001`
- 입력: frozen 10건의 selected evidence만 사용
- 생성 입력 제외: 질문, case ID, gold, reference answer
- 반복: mixed 2회, family 2회
- family:
  - `scope_and_actor`: `APPLIES_TO_MARKET`, `GOVERNS_ACTOR`
  - `normative_link`: `EXCEPTION_TO`, `IMPLEMENTS`
  - `semantic_and_temporal`: `DEFINED_BY`, `CURRENT_VERSION_OF`
- publish: 기존 deterministic source-proof validator를 그대로 통과한 후보만 허용

## 결과

| 지표 | mixed | family split |
|---|---:|---:|
| LLM calls | 20 | 60 |
| input tokens | 482,574 | 1,456,542 |
| output tokens | 41,682 | 50,740 |
| 후보 | 264 | 302 |
| publish | 174 | 197 |
| reject | 90 | 105 |
| guard acceptance | 65.9% | 65.2% |
| 두 반복 stable 관계 | 57 | 60 |
| 두 반복 union 관계 | 105 | 130 |
| stable / union | 54.3% | 46.2% |
| wall mean | 13.59s | 18.96s |
| wall p95 | 24.06s | 40.91s |

family split은 stable 관계를 3개 더 얻었지만 union이 25개 늘어 재현율은 8.1%p
하락했다. 입력 토큰은 3.018배, 평균 wall time은 1.395배였다.

관계별 `stable / union`은 다음과 같다.

| 관계 | mixed | family split |
|---|---:|---:|
| `APPLIES_TO_MARKET` | 30/34 (88.2%) | 35/42 (83.3%) |
| `GOVERNS_ACTOR` | 22/59 (37.3%) | 24/83 (28.9%) |
| `EXCEPTION_TO` | 0/2 (0%) | 1/1 (100%) |
| `IMPLEMENTS` | 3/6 (50.0%) | 0/3 (0%) |
| `DEFINED_BY` | 2/4 (50.0%) | 0/1 (0%) |
| `CURRENT_VERSION_OF` | 후보 없음 | 후보 없음 |

`cm-043`의 family `scope_and_actor`는 첫 반복 0개, 둘째 반복 15개여서 Haiku의
전수 열거 자체가 크게 흔들린다는 반례가 나왔다. 관계군 분리만으로 이 문제가 해결되지
않는다.

## Proof guard

두 변형 모두 publish된 관계의 validation error는 0건이었다. mixed 90개와 family
105개의 invalid 후보는 모두 publish에서 차단됐다. 이는 원문 증명 계약의 정합성이지,
관계 gold가 없는 상태에서의 의미 precision 측정값은 아니다.

기등록 핵심 사례도 두 반복 모두 통과했다.

- `cm-009`: 제16조 -> 제13조 가짜 `EXCEPTION_TO` 없음
- `cm-036`: 외부감사법 제8조의 `회사의 대표자` actor 재현
- `cm-045`: 상위 경로의 신설일을 버전으로 오인한 `CURRENT_VERSION_OF` 없음

## 판단 및 다음 가설

전체 family split은 비용과 변동성 때문에 기각한다. 후속 우선순위는 다음과 같다.

1. mixed 1회를 기본으로 두고 `EXCEPTION_TO`만 별도 Haiku 표적 복구한다.
2. `GOVERNS_ACTOR`는 LLM 전수 열거 대신 문장 의존구조/조사 기반 deterministic 후보를
   만든 뒤 Haiku가 주체 여부만 판정하도록 역할을 축소한다.
3. `IMPLEMENTS`, `DEFINED_BY`, `CURRENT_VERSION_OF`는 현재 frozen evidence 메뉴에
   실제 target 쌍이 부족하므로, 추출 프롬프트보다 먼저 명시적 인용 target/동일 좌표
   버전 pair를 deterministic하게 구성한다.

## 재현

```bash
.venv/bin/python scripts/rag_haiku_source_relation_families_eval.py \
  --retrieval-ablation var/eval/e2e/cm_core_legalclosure_stage_ablation_51.json \
  --out var/eval/e2e/cm_core_haiku_source_relation_families_repeat2_v2.json \
  --cases cm-004,cm-009,cm-017,cm-021,cm-031,cm-036,cm-039,cm-043,cm-045,cm-051 \
  --repetitions 2 --workers 4
```
