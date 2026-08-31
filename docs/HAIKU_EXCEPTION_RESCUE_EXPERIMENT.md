# Haiku `EXCEPTION_TO` 표적 복구 실험

## 결론

긴 mixed prompt를 한 번 더 읽히는 방식은 실패했다. 원문에서 `인용 조문 + 강한 적용배제
문언`을 먼저 deterministic하게 메뉴화하고 Haiku가 닫힌 후보만 판정하는 방식은 적은
비용으로 mixed가 놓친 예외 관계를 복구했다.

그러나 blind holdout의 2/2 합의 관계에도 1개의 거짓 양성이 남았다. 따라서 2회 합의는
필요하지만 충분하지 않다. 현재 결과는 자동 publish하지 않고 review candidate로만
보관한다. main wiring과 canonical graph는 변경하지 않았다.

## 고정 계약

- 모든 실제 LLM 호출: `claude-haiku-4-5-20251001`
- 생성 입력: 닫힌 source-target-quote 메뉴만 사용
- 질문, case ID, gold, reference answer: 생성 입력에서 제외
- candidate 생성: 같은 quote에서 target 조문 표면형과 `에도 불구하고` 또는
  `적용하지 아니`가 직접 결합된 경우
- validation: 기존 source-proof guard + candidate menu membership
- target 표기: 닫힌 target ID의 canonical path로 결정론적 정규화
- 후보가 없는 사례: LLM 호출 생략

## 결과

| 데이터 | mixed EXCEPTION union/stable | rescue union/stable | 수동감사 union | 수동감사 stable |
|---|---:|---:|---:|---:|
| probe 10 | 2 / 0 | 6 / 6 | 6/6 참 (100%) | 6/6 참 (100%) |
| blind holdout 12 | 1 / 0 | 12 / 9 | 9/12 참 (75%) | 8/9 참 (88.9%) |

probe의 mixed 2건 중 시행령이 법률상 예외 대상을 정의한 관계는 실제로는
`IMPLEMENTS/DEFINED_BY` 성격이었다. rescue의 강한 방향성 규칙은 이를 만들지 않았다.

holdout 거짓 양성은 다음 세 가지다.

1. `제49조의2`는 평가심의위원회 신청 경로인데 뒤의 `제54조·제55조 및 제56조에도
   불구하고`에 거리 기반으로 잘못 결합됨. 서로 다른 case batch에서 support 1과 2로
   각각 나타났다.
2. 국세기본법 `제47조의3`은 선행 가산세 부과 조건일 뿐, 실제 적용배제 대상은 source
   조문의 제1항·제2항이었다.

즉 단순 거리 창보다 `에도 불구하고` 바로 앞의 병렬 조문 목록을 문법적으로 추출해야
한다. holdout을 확인한 뒤 현재 구현은 수정하지 않았다.

## 비용과 지연

| 데이터 | 실제 rescue calls | input tokens | output tokens | mixed 1회 대비 추가 input | 활성 호출 p50 / p95 |
|---|---:|---:|---:|---:|---:|
| probe 10 × 2 | 6 | 13,448 | 3,908 | 5.6% | 5.39s / 8.53s |
| holdout 12 × 2 | 10 | 23,720 | 5,795 | 6.9% | 4.93s / 6.46s |

probe에서는 3개 사례, holdout에서는 5개 사례에만 deterministic 후보가 있어 각각
2회 호출했다. 전체 요청에 붙일 때 추가 wall latency를 피하려면 비동기 corpus 구축이나
offline relation compilation으로 사용해야 한다.

## Publish 정책

- union/support 1: shadow only
- support 2/2: human 또는 독립 clause-scope validator의 review candidate
- 자동 publish: 현재 금지
- 다음 자동화 gate: `에도 불구하고`의 즉시 병렬 목적어 목록 parser + 새 blind holdout에서
  중대 거짓 양성 0

2/2 합의는 holdout precision을 75.0%에서 88.9%로 높였으므로 필요하다. 하지만 동일한
거리 기반 오분류를 Haiku가 반복 재현하므로 합의만으로 진실성이 보장되지는 않는다.

## 재현

```bash
# probe 10
.venv/bin/python scripts/rag_haiku_exception_rescue_eval.py \
  --retrieval-ablation var/eval/e2e/cm_core_legalclosure_stage_ablation_51.json \
  --mixed-inputs var/eval/e2e/cm_core_haiku_source_relation_families_repeat2_v2.json \
  --out var/eval/e2e/cm_core_haiku_exception_rescue_probe10_final.json \
  --dataset-name probe10-final \
  --cases cm-004,cm-009,cm-017,cm-021,cm-031,cm-036,cm-039,cm-043,cm-045,cm-051 \
  --repetitions 2 --workers 4

# 사전등록 blind holdout 12
.venv/bin/python scripts/rag_haiku_exception_rescue_eval.py \
  --retrieval-ablation var/eval/e2e/cm_core_legalclosure_stage_ablation_51.json \
  --mixed-inputs \
    var/eval/e2e/cm_core_haiku_source_relations_holdout12_mixed_v1.json \
    var/eval/e2e/cm_core_haiku_source_relations_holdout12_mixed_v2.json \
  --out var/eval/e2e/cm_core_haiku_exception_rescue_holdout12_final.json \
  --dataset-name holdout12-blind \
  --cases cm-007,cm-005,cm-050,cm-019,cm-008,cm-026,cm-001,cm-032,cm-044,cm-022,cm-049,cm-014 \
  --repetitions 2 --workers 4
```
