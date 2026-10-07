# RAG 멀티턴 체인 계약 강화 결과

ADR-0594 · WSL 로컬 · 합성 원문 6단위 · 연속 대화 6개·49턴/arm · Qwen3.8 · MAIN 미변경

**실제 RAG API/Coordinator·GENOS 연결 검증은 포함하지 않는다. 점수와 기계적 안전 검사·모델 텍스트 평가는 별개다.**

## 직접 원인과 수정

| 원인 | 수정 |
|---|---|
| 조건이 같으면 FOLLOW를 COMPOSE로 덮어씀 | 명시 stage를 유지하고 변경 조건·pending과 가장 이른 단계를 결정 |
| 원본 없는 복원 명령을 적용 | 명령 검증·동일 goal 원발언 참조를 확인하고 원기록 값으로 복원; 없으면 CLARIFY |
| INSPECT/REUSE 응답 필드 누락 | 실제 소비 route의 immutable nodes로 assessment·retrieval·goal·revision 응답 |
| 다른 질문의 마지막 검색을 집계 | final response의 route_id/goal을 관측하고 그 경로의 원문 집합으로 집계 |
| 답변 문장이 현재 판단과 다름 | 사실값 일치 검사와 별도 제품 text 검증; 1회 수리 실패 시 게시 차단 |
| 긴급 미확인을 false로 취급 | null/false/true 3상태 유지, 판단과 작성 계약에서 일치 검사 |
| native 기록 실패에도 chain head가 바뀔 수 있음 | native 실패 시 node·head 트랜잭션 롤백 |

## 사전 검사 결과

| 흐름 | PARENT | STRICT |
|---|---|---|
| SEQ01 | 52/71 | 71/71 |
| SEQ02 | 22/34 | 34/34 |
| SEQ03 | 27/41 | 41/41 |
| SEQ04 | 13/23 | 23/23 |
| SEQ05 | 25/37 | 32/37 |
| GUARD | 19/36 | 36/36 |

모델 0회 adversarial 계약: 21/21. 정확한 각 검사·실패 원문은 guard-result.json을 따른다.

score의 분모는 성공 응답의 필드 검사 수에 따라 달라질 수 있으므로, 모든 요청의 상태를 별도 diagnostic audit에서 확인해야 한다.

## 기능별 실제 관찰

### SEQ01

| 턴 | 사용자 발언 | STRICT 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규에서 국내 법인의 긴급 예외 적용 조건을 확인해줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 2 | 아니 외규에서 해외 법인의 필요 서류를 확인하는 것으로 바꿔줘. | READY / C | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 3 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 4 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 5 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 6 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | ASSESS,COMPOSE |
| 7 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | ASSESS,COMPOSE |
| 8 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | ASSESS,COMPOSE |
| 9 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | ASSESS,COMPOSE |
| 10 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | ASSESS,COMPOSE |
| 11 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | COMPOSE |
| 12 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | ASSESS,COMPOSE |
| 13 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | ASSESS,COMPOSE |
| 14 | 현재 조건과 결론은 유지하고, 방금 결론의 근거만 다시 설명해줘. | READY / C | ASSESS,COMPOSE |
| 15 | 앞의 전환은 잘못됐어. 첫 질문의 목적과 규정 범위와 당사자 조건 전부 원래대로 다시 봐줘. 그 최초 질문까지 거슬러 확인해. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 16 | 그러면 지금 조건에서 결론과 근거를 다시 알려줘. | READY / B | COMPOSE |
| 17 | 같은 조건으로 새 대화에서 물으면 이 최종 경로를 써줘. | REUSED / B | COMPOSE |

미충족 항목:
```json
[]
```

실제 오류:
```json
[]
```

### SEQ02

| 턴 | 사용자 발언 | STRICT 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규의 국내 법인 절차를 확인해줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 2 | 두 번째 질문은 내규의 해외 법인 절차야. | READY / A | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 3 | 두 번째 질문만 외규로 고쳐줘. | READY / C | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 4 | 두 번째 질문은 긴급 사건이라는 조건도 고려해줘. | READY / C | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 5 | 방금 긴급이라고 고친 건 잘못이야. 두 번째 질문은 긴급하지 않아. | READY / C | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 6 | 첫 번째 질문의 현재 결론은 뭐야? | INSPECTED / B |  |

미충족 항목:
```json
[]
```

실제 오류:
```json
[]
```

### SEQ03

| 턴 | 사용자 발언 | STRICT 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규의 본문만 검색해서 국내 법인 절차를 확인해줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 2 | 본문만 읽은 게 문제야. 단서와 서류도 포함하도록 검색 계획과 원문 읽기부터 고쳐줘. | READY / B | PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 3 | 이제 근거 선별 단계부터 다시 검토해서 단서도 근거로 유지해줘. | READY / B | SELECT,ASSESS,COMPOSE |
| 4 | 판단에서 긴급 여부가 빠졌어. 이 사건은 긴급이야. 다시 판단해줘. | READY / B | SELECT,ASSESS,COMPOSE |
| 5 | 지금 최종 답변만 표로 보여줘. | READY / B | COMPOSE |
| 6 | 같은 내용으로 표 대신 문장으로 자세하게 써줘. | READY / B | COMPOSE |
| 7 | 그럼 현재 적용 절차와 긴급 조건은 어떻게 돼? | INSPECTED / B |  |

미충족 항목:
```json
[]
```

실제 오류:
```json
[]
```

### SEQ04

| 턴 | 사용자 발언 | STRICT 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 첫 번째 경험은 내규 국내 법인의 절차 확인이야. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 2 | 두 번째 경험은 외규 해외 법인의 절차 확인이야. | READY / C | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 3 | 첫 번째 질문에 두 번째 경험을 잘못 연결했다고 가정하자. | FIXTURE /  |  |
| 4 | 가져온 경험이 잘못됐어. 첫 번째 질문은 첫 번째 경험으로 연결해. 두 번째 경험 자체는 유지해줘. | REUSED / B | COMPOSE |
| 5 | 첫 번째 질문에 해당하는 현재 경로로 다시 알려줘. | REUSED / B | COMPOSE |

미충족 항목:
```json
[]
```

실제 오류:
```json
[]
```

### SEQ05

| 턴 | 사용자 발언 | STRICT 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규에서 국내 법인 절차를 알려줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 2 | 외규로 고쳐줘. | READY / D | PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 3 | 그 정정은 잘못됐어. 다시 내규로 봐줘. | READY / B | PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 4 | 국내가 아니라 해외 법인이야. | READY / A | PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 5 | 두 번째 정정에서 내규로 돌린 게 잘못됐어. 외규 기준을 유지해줘. | CLARIFY /  |  |
| 6 | 중단된 정정을 이어서 처리해줘. | READY / A | COMPOSE |
| 7 | 지금 최종 경로로 다시 답해줘. | READY / A | COMPOSE |
| 8 | 옛 실행을 다시 수집해도 최종 경로를 사용해줘. | REUSED / A | COMPOSE |

미충족 항목:
```json
[
  {
    "turn": 6,
    "field": "scope",
    "expected": "EXTERNAL",
    "observed": "INTERNAL",
    "pass": false
  },
  {
    "turn": 6,
    "field": "procedure",
    "expected": "C",
    "observed": "A",
    "pass": false
  },
  {
    "turn": 7,
    "field": "procedure",
    "expected": "C",
    "observed": "A",
    "pass": false
  },
  {
    "turn": 8,
    "field": "procedure",
    "expected": "C",
    "observed": "A",
    "pass": false
  },
  {
    "field": "failed_correction_blocks_old_route",
    "expected": true,
    "observed": false,
    "pass": false
  }
]
```

실제 오류:
```json
[]
```

### GUARD

| 턴 | 사용자 발언 | STRICT 상태·절차 | 실행 단계 |
|---|---|---|---|
| 1 | 내규에서 국내 법인 절차를 알려줘. 긴급 여부는 아직 몰라. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 2 | 긴급하지 않은 사건이라고 확인됐어. 그 조건을 반영해줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 3 | 방금 긴급하지 않다고 한 건 잘못이야. 긴급 사건으로 고쳐줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 4 | 그 정정도 잘못됐어. 긴급 여부는 아직 미확인이야. 미확인 상태로 되돌려줘. | READY / B | INTENT,PLAN,RECALL,READ,SELECT,ASSESS,COMPOSE |
| 5 | 현재 긴급 여부와 판단을 조회해줘. | INSPECTED / B |  |
| 6 | 같은 조건의 현재 경로로 다시 답해줘. | REUSED / B | COMPOSE |

미충족 항목:
```json
[]
```

실제 오류:
```json
[]
```


## 비용·지연·회수


```json
{
  "by_arm": {
    "PARENT": {
      "checks_passed": 158,
      "checks_total": 242,
      "sequences_passed": 0,
      "sequences_total": 6,
      "runtime_errors": 1
    },
    "STRICT": {
      "checks_passed": 237,
      "checks_total": 242,
      "sequences_passed": 5,
      "sequences_total": 6,
      "runtime_errors": 0
    }
  },
  "paired": {
    "candidate_only": 5,
    "baseline_only": 0,
    "both_correct": 0,
    "both_incorrect": 1
  },
  "usage": {
    "calls": 457,
    "product_calls": 363,
    "offline_evaluator_calls": 94,
    "input_tokens": 351293,
    "output_tokens": 53343,
    "reported_cost_usd": 0.20121804,
    "reasoning_tokens": 0
  },
  "turn_latency_seconds": {
    "PARENT": {
      "p50": 5.993444686988369,
      "p95": 8.72386802197434
    },
    "STRICT": {
      "p50": 11.211982139968313,
      "p95": 15.592108712997288
    }
  },
  "retrieval": {
    "PARENT": {
      "before_filter": 36,
      "after_filter": 18,
      "presented_total": 14,
      "presented_mean": 2.3333333333333335,
      "presented_p50": 2.0,
      "presented_p95": 3,
      "golden_recall": 1.0,
      "selectivity": 0.3888888888888889
    },
    "STRICT": {
      "before_filter": 36,
      "after_filter": 18,
      "presented_total": 13,
      "presented_mean": 2.1666666666666665,
      "presented_p50": 2.0,
      "presented_p95": 3,
      "golden_recall": 0.8888888888888888,
      "selectivity": 0.3611111111111111
    }
  },
  "judge_disagreements": 0
}
```

## 범위와 한계

- Local synthetic stage executor only; no production RAG API/Coordinator/GENOS wiring
- Fixed goal/link/exact configuration reuse; no independent semantic wiki matching
- No DB admin or legal approval; preservation and rejection contracts only
- One in-sample 43-turn set per arm; no generalized quality certification
- Product text verifier uses same model; an independent post-product evaluator records text drift and evaluator disagreement
- One explicitly bounded compose repair; no model/provider fallback or hidden experiment reruns
- 세션/경로용 SQLite와 Native WorkRepository 기록은 실제 실행했다. 원문 읽기·선별·판단·작성은 합성 stage executor다.
- 기본 네 port의 생산 Coordinator, 인증 adapter, 실제 READ/presentation ledger, two-DB worker·lease·SSE·캐시 서버는 붙이지 않았다.
- 현재 경로의 오래된 revision 거부를 검사했으며, 실제 동시 서버 경합·캐시 장애 시험은 아니다.
- 법률 승인·DB 관리 기능은 이번 실험 대상에서 제외했다.
- 정식 ADR graph 검사 결과는 별도 validation receipt에서 확인한다.

[ADR 기록](../../../04_EXPERIMENTS/ADR/ADR-0594-rag-chain-strict-contracts/README.md) · [원시 결과](../../../04_EXPERIMENTS/ADR/ADR-0594-rag-chain-strict-contracts/artifacts/run-001/result.json)
